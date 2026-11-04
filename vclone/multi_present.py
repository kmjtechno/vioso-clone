"""Opt-in multi-display still preview from verified M14 PNG export.

Separate OpenCV fullscreen windows on operator-selected display origins.
No frame lock, genlock, GPU swap chains or native VIOSO hardware parity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat

import cv2
import numpy as np

MAX_PROJECTORS = 8
MAX_IMAGE_BYTES = 32 * 1024 * 1024


class MultiDisplayError(ValueError):
    """Untrusted manifest, unsafe display selection or hardware failure."""


@dataclass(frozen=True)
class MultiDisplayReceipt:
    displays_presented: int
    escape_pressed: bool
    hardware_acceptance: str = "NOT_VERIFIED"
    synchronization: str = "NOT_VERIFIED"


def _origins(origins, count):
    if not isinstance(origins, (list, tuple)) or len(origins) != count:
        raise MultiDisplayError("provide one distinct desktop origin per projector")
    validated = []
    for pair in origins:
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or any(type(v) is not int or abs(v) > 32768 for v in pair)):
            raise MultiDisplayError("desktop origins must be bounded integer x,y pairs")
        validated.append(tuple(pair))
    if len(set(validated)) != len(validated):
        raise MultiDisplayError("desktop origins cannot be duplicated")
    return validated


def load_verified_frames(directory):
    """Load and checksum 2..8 generated M14 files; reject path traversal."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise MultiDisplayError("export path must be a regular directory")
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise MultiDisplayError("missing safe M14 manifest")
    if manifest.stat().st_size > 64 * 1024:
        raise MultiDisplayError("M14 manifest exceeds inspection limit")
    try:
        obj = json.loads(manifest.read_text(encoding="utf-8"))
        records = obj["projectors"]
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise MultiDisplayError(f"cannot read M14 manifest: {exc}") from exc
    if (obj.get("schema") != "kmj.multi-projector.offline.v1"
            or obj.get("software_preview_only") is not True
            or obj.get("hardware_acceptance") != "NOT_VERIFIED"
            or not isinstance(records, list) or not 2 <= len(records) <= MAX_PROJECTORS):
        raise MultiDisplayError("unexpected M14 preview schema")
    images, seen = [], set()
    for i, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise MultiDisplayError("invalid projector record")
        filename = record.get("image_file")
        if (not isinstance(filename, str) or filename != f"projector_{i:02d}.png"
                or filename in seen or re.fullmatch(r"projector_[0-9]{2}\.png", filename) is None):
            raise MultiDisplayError("invalid projector filename/order")
        seen.add(filename)
        digest = record.get("sha256")
        dims = record.get("projector_size")
        if (not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None
                or not isinstance(dims, list) or len(dims) != 2
                or any(type(v) is not int for v in dims)
                or not 2 <= dims[0] <= 1920 or not 2 <= dims[1] <= 1080):
            raise MultiDisplayError("invalid projector size or digest")
        source = directory / filename
        if source.is_symlink() or not source.is_file():
            raise MultiDisplayError("unsafe projector image path")
        info = source.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_IMAGE_BYTES:
            raise MultiDisplayError("invalid projector PNG size")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise MultiDisplayError("projector PNG digest mismatch; export again")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if (image is None or image.dtype != np.uint8 or image.ndim != 3
                or image.shape != (dims[1], dims[0], 3)):
            raise MultiDisplayError("projector PNG dimensions/format mismatch")
        images.append(image)
    return images


def present_multi(directory, origins, *, duration_ms=5000, confirmed=False):
    """Display all verified projector PNGs, then always close opened windows."""
    if not confirmed:
        raise MultiDisplayError("operator confirmation required: --confirm-display")
    if type(duration_ms) is not int or not 1 <= duration_ms <= 30000:
        raise MultiDisplayError("display time must be bounded to 1..30000 ms")
    images = load_verified_frames(directory)
    positions = _origins(origins, len(images))
    opened = []
    try:
        for i, (image, (x, y)) in enumerate(zip(images, positions), start=1):
            name = f"KMJ Projector {i:02d}"
            cv2.namedWindow(name, cv2.WINDOW_NORMAL)
            opened.append(name)
            cv2.moveWindow(name, x, y)
            cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            cv2.imshow(name, image)
        code = cv2.waitKey(duration_ms)
        return MultiDisplayReceipt(len(images), (code & 0xFF) == 27)
    finally:
        for name in reversed(opened):
            cv2.destroyWindow(name)
