"""Explicit, bounded camera-only live frame diagnostic for VIOSO Clone.

This never displays projector patterns, inspects unrelated devices or writes
camera images. It opens ONLY the source from an existing private M33 profile
after local operator --confirm-camera consent. Camera credentials, hostnames,
stream paths, pixel data and device IDs are never included in its receipts.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .camera_sources import CameraSourceError, open_camera, read_profile
from .capture import CaptureError, MAX_CAMERA_PIXELS, _grayscale


class CameraProbeError(ValueError):
    """A camera-only preflight was refused; messages contain no source URI."""


def _settings(*, confirmed, frames, warmup):
    # Refuse without confirmation before even touching a local private profile.
    if confirmed is not True:
        raise CameraProbeError("camera-only test requires --confirm-camera")
    if type(frames) is not int or not 4 <= frames <= 16:
        raise CameraProbeError("frames must be an integer in 4..16")
    if type(warmup) is not int or not 0 <= warmup <= 6:
        raise CameraProbeError("warmup must be an integer in 0..6")


def _summarize_frame(frame):
    """Read aggregate optical screening values, never return pixels or metadata."""
    try:
        gray = _grayscale(frame)
    except (CaptureError, cv2.error, TypeError, ValueError) as exc:
        raise CameraProbeError("camera frame format or pixel budget invalid") from None
    height, width = gray.shape
    if (not 64 <= width <= 4096 or not 64 <= height <= 4096
            or width * height > MAX_CAMERA_PIXELS):
        raise CameraProbeError("camera frame dimensions outside bounded scan support")
    scale = min(1.0, 320.0 / width, 240.0 / height)
    sw = max(16, int(width * scale))
    sh = max(16, int(height * scale))
    small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
    pixels = small.astype(np.float32)
    mean = float(np.mean(pixels))
    black = float(np.mean(small <= 2))
    white = float(np.mean(small >= 253))
    sharpness = float(cv2.Laplacian(pixels, cv2.CV_32F).var())
    if not all(math.isfinite(v) for v in (mean, black, white, sharpness)):
        raise CameraProbeError("camera frame optical metrics were non-finite")
    return (width, height), small, (mean, black, white, sharpness)


def camera_frame_probe(camera_profile_path, *, confirmed=False, frames=8, warmup=1):
    """Sample one explicitly chosen camera; no filesystem writes or projection.

    The report is suitable for preflight screening while projectors are OFF.
    This does NOT validate geometric calibration, calibration exposure or lens
    correction, nor does an RTSP profile imply camera model compatibility.
    """
    _settings(confirmed=confirmed, frames=frames, warmup=warmup)
    try:
        profile = read_profile(camera_profile_path)
    except (CameraSourceError, OSError, ValueError, TypeError) as exc:
        raise CameraProbeError("private camera source profile refused") from None

    source_type = profile["type"]
    # The only network access is to the single user-selected camera URL.
    try:
        stream = open_camera(profile)
    except Exception:
        raise CameraProbeError("selected camera could not be opened safely") from None

    shapes = []
    brightness, black_fraction, white_fraction, sharpness = [], [], [], []
    temporal_changes = []
    previous = None
    try:
        for _ in range(warmup):
            try:
                ready = stream.grab()
            except Exception:
                # Native decoder/SDK exceptions may contain the private URI.
                raise CameraProbeError("camera warmup decoder failed") from None
            if not ready:
                raise CameraProbeError("camera warmup failed")
        for _ in range(frames):
            try:
                ok, frame = stream.read()
                if not ok or frame is None:
                    raise CameraProbeError("camera frame could not be read")
                shape, small, metrics = _summarize_frame(frame)
            except CameraProbeError:
                raise
            except Exception:
                # Any untrusted backend can raise an exception with its source
                # URI/username in the message; do not echo it to the CLI.
                raise CameraProbeError("camera decoder or frame acquisition failed") from None
            if shapes and shape != shapes[0]:
                raise CameraProbeError("camera resolution changed during bounded probe")
            shapes.append(shape)
            brightness.append(metrics[0])
            black_fraction.append(metrics[1])
            white_fraction.append(metrics[2])
            sharpness.append(metrics[3])
            if previous is not None:
                difference = np.abs(small.astype(np.int16) - previous.astype(np.int16))
                temporal_changes.append(float(np.mean(difference > 2)))
            previous = small
    finally:
        try:
            stream.release()
        except Exception:
            pass

    # No automatic PASS claim for scene exposure, motion, focus or hardware.
    # A still scene can legitimately have unchanged frames.
    mean_luma = float(np.mean(brightness))
    if mean_luma < 12:
        signal = "LOW_LIGHT_CHECK_EXPOSURE"
    elif mean_luma > 245:
        signal = "HIGH_BRIGHTNESS_CHECK_EXPOSURE"
    else:
        signal = "FRAME_DATA_PRESENT"
    width, height = shapes[0]
    return {
        "schema": "kmj.camera.frame-probe.v1",
        "read_only_no_capture_files": True,
        "projector_operation": "NONE",
        "camera_source_type": source_type,
        "camera_connection": "OPENED_AND_FRAMES_READ",
        "frames_observed": len(shapes),
        "camera_size": [width, height],
        "resolution_consistent": True,
        "mean_luma_code": round(mean_luma, 4),
        "min_frame_mean_luma_code": round(min(brightness), 4),
        "max_frame_mean_luma_code": round(max(brightness), 4),
        "mean_clipped_black_fraction": round(float(np.mean(black_fraction)), 6),
        "mean_clipped_white_fraction": round(float(np.mean(white_fraction)), 6),
        "min_sharpness_laplacian_variance": round(min(sharpness), 4),
        "mean_frame_change_fraction": round(float(np.mean(temporal_changes)), 6),
        "exposure_screening": signal,
        "optical_calibration": "NOT_VERIFIED",
        "hardware_optical_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
    }
