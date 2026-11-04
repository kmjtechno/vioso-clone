"""Bounded read-only QA of this clone's Gray-code camera capture directory.

No camera or projector is opened and no owner file is changed. These checks
measure image/data usability, not optical alignment or VIOSO 7 compatibility.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import stat
import struct

import cv2
import numpy as np

from .capture import (MANIFEST_SCHEMA, MAX_CAMERA_PIXELS,
                      pattern_count, _size)
from .optical_roi import read_camera_mask
from .fisheye_rectify import FisheyeRectifier, read_fisheye_profile

MAX_MANIFEST_BYTES = 16 * 1024
MAX_CAPTURE_BYTES = 128 * 1024 * 1024


class CaptureCheckError(ValueError):
    """Untrusted, incomplete or low-quality synthetic/real camera capture."""


def _integer_pair(value, label, *, maximum):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(n) is not int or not 2 <= n <= maximum for n in value)
            or value[0] * value[1] > MAX_CAMERA_PIXELS):
        raise CaptureCheckError(f"invalid {label} dimensions")
    return tuple(value)


def _read_png(path: Path, expected_size: tuple[int, int]) -> np.ndarray:
    if path.is_symlink():
        raise CaptureCheckError("capture PNG symlinks are not allowed")
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CAPTURE_BYTES:
            raise CaptureCheckError("missing or oversized capture PNG")
        # Validate PNG's fixed-size IHDR before allocating decoded pixel buffers.
        with path.open("rb") as handle:
            header = handle.read(29)
        if (len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n"
                or header[8:16] != b"\x00\x00\x00\rIHDR"
                or header[24:29] != b"\x08\x00\x00\x00\x00"):
            raise CaptureCheckError("capture must be a non-interlaced 8-bit grayscale PNG")
        width, height = struct.unpack(">II", header[16:24])
        if (width, height) != expected_size:
            raise CaptureCheckError("capture camera resolution differs from manifest")
        frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if (frame is None or frame.dtype != np.uint8 or frame.ndim != 2
                or frame.shape != (height, width)):
            raise CaptureCheckError("capture PNG failed grayscale decoding")
        return frame
    except (OSError, cv2.error) as exc:
        raise CaptureCheckError("capture PNG unreadable") from exc


def _binary_from_gray(gray: np.ndarray) -> np.ndarray:
    value = gray.copy()
    shift = gray >> 1
    for _ in range(16):
        if not np.any(shift):
            break
        value ^= shift
        shift >>= 1
    return value


def check_capture(directory, *, margin=20, min_valid_fraction=0.30,
                  min_axis_span=0.25, camera_mask=None,
                  fisheye_profile=None, fisheye_balance=0.25) -> dict:
    """Inspect strict clone capture v1 manifest and all Gray-code pairs.

    Uses bounded streaming arrays rather than retaining every full-resolution
    image. Defaults are screening thresholds, not measured optical guarantees.
    """
    if type(margin) is not int or not 0 <= margin <= 254:
        raise CaptureCheckError("contrast margin must be an integer in 0..254")
    if (type(min_valid_fraction) not in (int, float)
            or not math.isfinite(min_valid_fraction)
            or not 0.01 <= min_valid_fraction <= 1.0):
        raise CaptureCheckError("minimum valid fraction must be 0.01..1")
    if (type(min_axis_span) not in (int, float)
            or not math.isfinite(min_axis_span)
            or not 0.01 <= min_axis_span <= 1.0):
        raise CaptureCheckError("minimum axis span must be 0.01..1")
    folder = Path(directory)
    if folder.is_symlink() or not folder.is_dir():
        raise CaptureCheckError("capture directory must be a regular non-symlink folder")
    manifest = folder / "capture_manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise CaptureCheckError("capture manifest is missing or linked")
    if not 0 < manifest.stat().st_size <= MAX_MANIFEST_BYTES:
        raise CaptureCheckError("capture manifest exceeds 16 KiB")
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"),
                         parse_constant=lambda _x: (_ for _ in ()).throw(
                             CaptureCheckError("manifest contains non-finite JSON")))
    except (ValueError, OSError, UnicodeError) as exc:
        raise CaptureCheckError("invalid capture manifest JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != MANIFEST_SCHEMA:
        raise CaptureCheckError("unexpected capture manifest schema")
    proj = _integer_pair(raw.get("projector_size"), "projector", maximum=1920)
    if proj[1] > 1080:
        raise CaptureCheckError("projector height exceeds 1080")
    try:
        _size(*proj)
    except ValueError as exc:
        raise CaptureCheckError("projector dimensions exceed capture limits") from exc
    camera = _integer_pair(raw.get("camera_size"), "camera", maximum=4096)
    # A native fisheye frame can be square (e.g. 2560x2560). Keep the
    # MAX_CAMERA_PIXELS total-pixel budget enforced by _integer_pair.
    count = pattern_count(*proj)
    expected = [f"{pol}{i:02d}.png" for i in range(count) for pol in ("p", "n")]
    if (type(raw.get("pattern_pairs")) is not int or raw["pattern_pairs"] != count
            or raw.get("image_files") != expected
            or raw.get("hardware_acceptance") != "NOT_VERIFIED"):
        raise CaptureCheckError("manifest pattern list, count or evidence status mismatch")

    w, h = camera
    roi = (np.ones((h, w), dtype=np.bool_) if camera_mask is None
           else read_camera_mask(camera_mask, (h, w)))
    rectifier = None
    if fisheye_profile is not None:
        rectifier = FisheyeRectifier(
            read_fisheye_profile(fisheye_profile), balance=fisheye_balance)
        if rectifier.size != camera:
            raise CaptureCheckError("fisheye profile camera resolution differs from capture")
        roi = rectifier.mask(roi)
    roi_pixels = int(np.count_nonzero(roi))
    valid = roi.copy()
    gx = np.zeros((h, w), dtype=np.uint16)
    gy = np.zeros((h, w), dtype=np.uint16)
    x_bits = max(1, (proj[0] - 1).bit_length())
    per_pair = []
    for i in range(count):
        pos = _read_png(folder / expected[2 * i], camera)
        neg = _read_png(folder / expected[2 * i + 1], camera)
        if rectifier is not None:
            pos, neg = rectifier.image(pos), rectifier.image(neg)
        diff = pos.astype(np.int16) - neg.astype(np.int16)
        reliable = np.abs(diff) > margin
        valid &= reliable
        per_pair.append(float(np.count_nonzero(reliable & roi) / roi_pixels))
        destination = gx if i < x_bits else gy
        destination[:] = (destination << 1) | (diff > 0)
        del pos, neg, diff, reliable
    x = _binary_from_gray(gx)
    y = _binary_from_gray(gy)
    valid &= (x < proj[0]) & (y < proj[1])
    valid_fraction = float(np.count_nonzero(valid) / roi_pixels)
    if valid_fraction < min_valid_fraction:
        raise CaptureCheckError("Gray-code decoded valid-pixel fraction below gate")
    xs, ys = x[valid], y[valid]
    x_span = float((int(xs.max()) - int(xs.min())) / max(1, proj[0] - 1))
    y_span = float((int(ys.max()) - int(ys.min())) / max(1, proj[1] - 1))
    if min(x_span, y_span) < min_axis_span:
        raise CaptureCheckError("decoded projector coordinate span below gate")

    report = {
        "schema": "kmj.graycode.capture-check.v1",
        "software_capture_quality": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "projector_size": list(proj),
        "camera_size": list(camera),
        "camera_mask_applied": camera_mask is not None,
        "camera_roi_fraction": round(float(roi_pixels / (w * h)), 6),
        "pattern_pairs_checked": count,
        "contrast_margin": margin,
        "min_pair_reliable_fraction": round(min(per_pair), 6),
        "decoded_valid_fraction": round(valid_fraction, 6),
        "projector_axis_span_fraction": [round(x_span, 6), round(y_span, 6)],
    }
    if rectifier is not None:
        report["fisheye_rectification"] = rectifier.report()
    return report
