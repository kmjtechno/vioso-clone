"""Independent projector-side grayscale mask for opt-in Gray-code capture.

This is NOT a camera ROI mask: black means no projected light, white means full
projected pattern, gray means bounded partial pattern brightness. No vendor
mask XML, proprietary binary or licensing code is accessed.
"""
from __future__ import annotations

from pathlib import Path
import stat
import struct

import cv2
import numpy as np

MAX_MASK_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 1920 * 1080


class ProjectorMaskError(ValueError):
    """Projector mask has unsafe data or mismatches intended display size."""


def read_projector_mask(path, projector_size) -> np.ndarray:
    """Read one 8-bit grayscale PNG with exact projector width/height.

    Returns fresh uint8 pixels, black=blocked, white=full. Reject symlinks,
    color images, interlaced PNGs and decompression-size mismatches before
    capture opens a camera or projector.
    """
    if (not isinstance(projector_size, (tuple, list))
            or len(projector_size) != 2
            or any(type(v) is not int for v in projector_size)
            or not 2 <= projector_size[0] <= 1920
            or not 2 <= projector_size[1] <= 1080
            or projector_size[0] * projector_size[1] > MAX_PIXELS):
        raise ProjectorMaskError("invalid bounded projector mask dimensions")
    width, height = projector_size
    source = Path(path)
    if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
        raise ProjectorMaskError("projector mask must be a regular non-symlink PNG")
    try:
        info = source.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MASK_BYTES:
            raise ProjectorMaskError("projector mask size exceeds limit")
        with source.open("rb") as reader:
            header = reader.read(29)
        if (len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n"
                or header[8:16] != b"\x00\x00\x00\rIHDR"
                or header[24:29] != b"\x08\x00\x00\x00\x00"):
            raise ProjectorMaskError("projector mask must be 8-bit non-interlaced grayscale PNG")
        if struct.unpack(">II", header[16:24]) != (width, height):
            raise ProjectorMaskError("projector mask dimensions differ from selected projector")
        mask = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    except (OSError, cv2.error) as exc:
        raise ProjectorMaskError("projector mask cannot be read") from exc
    if (mask is None or mask.dtype != np.uint8 or mask.ndim != 2
            or mask.shape != (height, width)):
        raise ProjectorMaskError("projector mask cannot be decoded safely")
    if int(np.count_nonzero(mask)) < 4:
        raise ProjectorMaskError("projector mask blocks the entire calibration pattern")
    return mask
