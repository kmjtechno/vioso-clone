"""Read-only bounded camera ROI masks for optical Gray-code calibration.

Uses a clone-defined strict raster contract matching the documented camera
mask convention: black (0) includes a camera pixel in the scan; white (255)
excludes it. No vendor file/algorithm is loaded, and no camera is opened.
"""
from __future__ import annotations

from pathlib import Path
import stat
import struct

import cv2
import numpy as np

MAX_MASK_BYTES = 32 * 1024 * 1024
MAX_CAMERA_PIXELS = 4096 * 2160


class CameraMaskError(ValueError):
    """Invalid or unsafe camera region-of-interest mask."""


def read_camera_mask(path, shape) -> np.ndarray:
    """Return boolean (camera_y,camera_x) inclusion mask, without any writes.

    Only 8-bit grayscale noninterlaced PNGs containing exact 0 and 255 values
    are accepted. Reject ambiguous inverted/antialiased masks rather than
    silently selecting the wrong optical region.
    """
    if (not isinstance(shape, (tuple, list)) or len(shape) != 2
            or any(type(v) not in (int, np.int32, np.int64) or not 2 <= v <= 4096
                   for v in shape)
            or shape[0] > 2160 or shape[0] * shape[1] > MAX_CAMERA_PIXELS):
        raise CameraMaskError("camera ROI requires bounded camera frame shape")
    height, width = int(shape[0]), int(shape[1])
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.parent.is_symlink():
        raise CameraMaskError("camera mask must be a regular non-symlink PNG")
    try:
        info = source.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MASK_BYTES:
            raise CameraMaskError("camera mask exceeds size bound")
        with source.open("rb") as reader:
            hdr = reader.read(29)
        if (len(hdr) < 29
                or hdr[:8] != b"\x89PNG\r\n\x1a\n"
                or hdr[8:16] != b"\x00\x00\x00\rIHDR"
                or hdr[24:29] != b"\x08\x00\x00\x00\x00"):
            raise CameraMaskError("camera mask must be 8-bit non-interlaced grayscale PNG")
        if struct.unpack(">II", hdr[16:24]) != (width, height):
            raise CameraMaskError("camera mask dimensions do not match captured frame")
        pixels = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    except (OSError, cv2.error) as exc:
        raise CameraMaskError("camera mask PNG cannot be read") from exc
    if (pixels is None or pixels.dtype != np.uint8 or
            pixels.ndim != 2 or pixels.shape != (height, width)):
        raise CameraMaskError("camera mask could not be decoded")
    if not np.logical_or(pixels == 0, pixels == 255).all():
        raise CameraMaskError("camera mask pixels must be 0=include or 255=exclude")
    included = (pixels == 0)
    if np.count_nonzero(included) < 4:
        raise CameraMaskError("camera mask excludes entire useful camera ROI")
    return included
