"""Opt-in Gray-code projector/camera acquisition for the clone's calibration engine.

Only captures image pairs. Requires an explicitly selected display origin and
a locally attached camera; it does not claim hardware or native VIOSO parity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from .projector_mask import read_projector_mask

MAX_PROJECTOR_PIXELS = 1920 * 1080
MAX_CAMERA_PIXELS = 4096 * 2160
MANIFEST_SCHEMA = "kmj.graycode.capture.v1"


class CaptureError(RuntimeError):
    """A hardware, projection, acquisition or file-output failure."""


@dataclass(frozen=True)
class CaptureReceipt:
    schema: str
    projector_size: tuple[int, int]
    camera_size: tuple[int, int]
    pattern_pairs: int
    image_files: tuple[str, ...]
    hardware_acceptance: str = "NOT_VERIFIED"


def _size(width: int, height: int) -> tuple[int, int]:
    if (type(width) is not int or type(height) is not int
            or not 2 <= width <= 1920 or not 2 <= height <= 1080
            or width * height > MAX_PROJECTOR_PIXELS):
        raise ValueError("projector dimensions must be positive, bounded integers (max 1920x1080)")
    return width, height


def pattern_count(width: int, height: int) -> int:
    w, h = _size(width, height)
    return max(1, (w - 1).bit_length()) + max(1, (h - 1).bit_length())


def iter_patterns(width: int, height: int) -> Iterator[tuple[str, np.ndarray]]:
    """Yield p00/n00, p01/n01, ... matching calib.graycode_patterns.

    Patterns are generated lazily to avoid retaining all full-screen images.
    """
    w, h = _size(width, height)
    index = 0
    for axis, n in (("x", w), ("y", h)):
        positions = np.arange(n, dtype=np.int64)
        gray = positions ^ (positions >> 1)
        for bit in range(max(1, (n - 1).bit_length()) - 1, -1, -1):
            line = (((gray >> bit) & 1) * 255).astype(np.uint8)
            pattern = (np.broadcast_to(line[None, :], (h, w)).copy()
                       if axis == "x" else
                       np.broadcast_to(line[:, None], (h, w)).copy())
            yield f"p{index:02d}.png", pattern
            yield f"n{index:02d}.png", 255 - pattern
            index += 1


def _grayscale(frame: np.ndarray) -> np.ndarray:
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
        raise CaptureError("camera must return uint8 image frames")
    if frame.ndim == 2:
        image = frame
    elif frame.ndim == 3 and frame.shape[2] == 3:
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        image = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    else:
        raise CaptureError("camera returned an unsupported channel layout")
    h, w = image.shape
    if h < 2 or w < 2 or h * w > MAX_CAMERA_PIXELS:
        raise CaptureError("camera frame size is invalid or exceeds safety bounds")
    return image


def capture_sequence(
    width: int,
    height: int,
    output_dir: str | os.PathLike[str],
    show: Callable[[np.ndarray], None],
    grab: Callable[[], np.ndarray],
    *,
    projector_mask: np.ndarray | None = None,
) -> CaptureReceipt:
    """Acquire a bounded camera image for each projected pattern.

    The destination directory must not exist; this never overwrites captures.
    Partial failures leave diagnostic images but never a success manifest.
    """
    w, h = _size(width, height)
    if not callable(show) or not callable(grab):
        raise TypeError("show and grab must be callable")
    # Validate projector-side mask before creating any output folder.
    mask = None
    if projector_mask is not None:
        if (not isinstance(projector_mask, np.ndarray)
                or projector_mask.dtype != np.uint8
                or projector_mask.shape != (h, w)
                or int(np.count_nonzero(projector_mask)) < 4):
            raise CaptureError("projector mask must be a bounded nonempty uint8 projector grayscale frame")
        mask = projector_mask.copy()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    names: list[str] = []
    camera_size: tuple[int, int] | None = None
    for name, pattern in iter_patterns(w, h):
        # Gray-code patterns are 0/255; this preserves exact grayscale mask
        # intensities only where the pattern is lit, including inverse pairs.
        show(pattern if mask is None else cv2.bitwise_and(pattern, mask))
        frame = _grayscale(grab())
        current_size = (frame.shape[1], frame.shape[0])
        if camera_size is None:
            camera_size = current_size
        elif current_size != camera_size:
            raise CaptureError("camera resolution changed mid-capture")
        target = out / name
        staging = out / (".staging-" + name)
        if not cv2.imwrite(str(staging), frame):
            raise CaptureError(f"cannot write camera frame {name}")
        os.replace(staging, target)
        names.append(name)
    assert camera_size is not None  # dimensions are >= 2, so there are patterns
    receipt = CaptureReceipt(MANIFEST_SCHEMA, (w, h), camera_size,
                             pattern_count(w, h), tuple(names))
    manifest = out / "capture_manifest.json"
    manifest_data = asdict(receipt)
    if mask is not None:
        manifest_data["projector_mask_applied"] = True
        manifest_data["projector_mask_pixel_sha256"] = hashlib.sha256(mask.tobytes()).hexdigest()
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    return receipt


def capture_opencv(
    width: int,
    height: int,
    output_dir: str | os.PathLike[str],
    *,
    camera_index: int,
    projector_x: int,
    projector_y: int,
    settle_ms: int = 250,
    warmup_frames: int = 2,
    confirmed: bool = False,
    projector_mask_path=None,
) -> CaptureReceipt:
    """Use OpenCV display + VideoCapture on a locally approved projector/camera.

    Caller must explicitly acknowledge that projector_x/y select the display.
    ESC aborts capture; no camera or window is opened without acknowledgement.
    """
    _size(width, height)
    if not confirmed:
        raise CaptureError("display confirmation required: pass --confirm-display")
    if (type(camera_index) is not int or not 0 <= camera_index <= 15
            or type(projector_x) is not int or type(projector_y) is not int
            or abs(projector_x) > 32768 or abs(projector_y) > 32768
            or type(settle_ms) is not int or not 1 <= settle_ms <= 10000
            or type(warmup_frames) is not int or not 0 <= warmup_frames <= 30):
        raise ValueError("invalid camera, projector origin or capture timing")
    # Unsafe masks are refused before opening camera or projector windows.
    mask = (None if projector_mask_path is None else
            read_projector_mask(projector_mask_path, (width, height)))
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        camera.release()
        raise CaptureError(f"camera index {camera_index} is not available")
    window = "KMJ Gray-code projector output"
    created = False
    try:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        created = True
        cv2.moveWindow(window, projector_x, projector_y)
        cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        def show(pattern: np.ndarray) -> None:
            cv2.imshow(window, pattern)
            if (cv2.waitKey(settle_ms) & 0xFF) == 27:
                raise CaptureError("capture aborted by Escape")

        def grab() -> np.ndarray:
            for _ in range(warmup_frames):
                if not camera.grab():
                    raise CaptureError("camera warmup frame failed")
            ok, frame = camera.read()
            if not ok or frame is None:
                raise CaptureError("camera capture failed")
            return frame

        return capture_sequence(width, height, output_dir, show, grab, projector_mask=mask)
    finally:
        camera.release()
        if created:
            cv2.destroyWindow(window)
