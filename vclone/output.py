"""Opt-in bounded still-frame presentation to a selected desktop projector.

This is an experimental OpenCV window, not a synchronized GPU swap-chain,
hardware-timed player, native VIOSO output backend or calibrated device driver.
"""
from __future__ import annotations

import cv2
import numpy as np

MAX_OUTPUT_PIXELS = 4096 * 2160


class PresentationError(RuntimeError):
    pass


def present_still(frame: np.ndarray, *, projector_x: int, projector_y: int,
                  duration_ms: int = 5000, confirmed: bool = False) -> None:
    """Display a pre-warped still frame, then always close the window.

    No window is created without explicit user confirmation. Duration is
    bounded; output coordinates must be selected by the local operator.
    """
    if not confirmed:
        raise PresentationError("projector display confirmation required: --confirm-display")
    if (type(projector_x) is not int or type(projector_y) is not int
            or abs(projector_x) > 32768 or abs(projector_y) > 32768
            or type(duration_ms) is not int or not 1 <= duration_ms <= 30000):
        raise ValueError("invalid projector origin or bounded duration")
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim not in (2, 3)
            or frame.ndim == 3 and frame.shape[2] not in (3, 4)
            or frame.shape[0] < 2 or frame.shape[1] < 2
            or frame.shape[0] * frame.shape[1] > MAX_OUTPUT_PIXELS):
        raise ValueError("projected frame must be bounded uint8 grayscale, BGR or BGRA")
    window = "KMJ Calibrated Projector Preview"
    created = False
    try:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        created = True
        cv2.moveWindow(window, projector_x, projector_y)
        cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow(window, frame)
        cv2.waitKey(duration_ms)
    finally:
        if created:
            cv2.destroyWindow(window)
