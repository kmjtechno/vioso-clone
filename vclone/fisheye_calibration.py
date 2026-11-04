"""Independent offline fisheye camera lens calibration from checkerboard images.

This uses OpenCV's mathematical fisheye model; unlike a normal pinhole
CameraIntrinsics, its four distortion coefficients must not be silently
reinterpreted as k1/k2/p1/p2/k3. No cameras, streams or projectors are opened.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import stat

import cv2
import numpy as np

MIN_VIEWS = 12
MAX_VIEWS = 48
MAX_INPUT_BYTES = 40 * 1024 * 1024
MAX_IMAGE_PIXELS = 4096 * 4096
MODEL = "opencv_fisheye"
SCHEMA = "kmj.fisheye.intrinsics.v1"


class FisheyeCalibrationError(ValueError):
    """Unsafe frame, degenerate geometry or low-confidence lens calibration."""


def _board(cols, rows, square_mm):
    if (type(cols) is not int or type(rows) is not int or
            not 4 <= cols <= 16 or not 3 <= rows <= 12 or cols * rows > 150):
        raise FisheyeCalibrationError("checkerboard requires 4..16 by 3..12 inner corners")
    if (type(square_mm) not in (int, float) or not math.isfinite(square_mm)
            or not 1 <= square_mm <= 200):
        raise FisheyeCalibrationError("checker square size must be finite 1..200 mm")
    return np.asarray([(i * square_mm, j * square_mm, 0.0)
                       for j in range(rows) for i in range(cols)],
                      dtype=np.float64).reshape(-1, 1, 3)


def _size(size):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(x) is not int for x in size)
            or not 64 <= size[0] <= 4096 or not 64 <= size[1] <= 4096
            or size[0] * size[1] > MAX_IMAGE_PIXELS):
        raise FisheyeCalibrationError("invalid bounded fisheye camera image dimensions")
    return tuple(size)


def calibrate_observations(image_points, size, *, cols=9, rows=6,
                           square_mm=25.0, max_rms_px=1.5):
    """Fit an OpenCV fisheye model to 12..48 verified (N,2) camera observations.

    No acceptance is claimed for field-of-view, full lens circle, camera rig
    stability or true projector calibration without owner hardware evidence.
    """
    obj = _board(cols, rows, square_mm)
    width, height = _size(size)
    if (type(max_rms_px) not in (float, int) or
            not math.isfinite(max_rms_px) or not 0.1 <= max_rms_px <= 5):
        raise FisheyeCalibrationError("max_rms_px must be finite 0.1..5")
    if not isinstance(image_points, (tuple, list)) or not MIN_VIEWS <= len(image_points) <= MAX_VIEWS:
        raise FisheyeCalibrationError("need 12..48 distinct checkerboard views")
    points = []
    seen = set()
    cells = set()
    n = cols * rows
    for view in image_points:
        image = np.asarray(view)
        if image.shape not in ((n, 2), (n, 1, 2)) or image.dtype.kind not in "fi":
            raise FisheyeCalibrationError("checkerboard corners must have expected numeric shape")
        image = np.asarray(image, np.float64).reshape(n, 1, 2)
        if (not np.isfinite(image).all()
                or np.any(image[..., 0] < 0) or np.any(image[..., 0] >= width)
                or np.any(image[..., 1] < 0) or np.any(image[..., 1] >= height)):
            raise FisheyeCalibrationError("checkerboard pixels outside the camera image")
        digest = hashlib.sha256(np.round(image.reshape(-1), 3).tobytes()).digest()
        if digest in seen:
            raise FisheyeCalibrationError("duplicate checkerboard observation")
        seen.add(digest)
        for x, y in image.reshape(-1, 2):
            cells.add((min(3, int(x * 4 / width)), min(2, int(y * 3 / height))))
        points.append(np.ascontiguousarray(image, dtype=np.float64))
    coverage = len(cells) / 12.0
    if coverage < 0.5:
        raise FisheyeCalibrationError("checkerboard observations do not cover enough camera image regions")
    objects = [obj.copy() for _ in points]
    K = np.array([[float(max(width, height)), 0, width / 2],
                  [0, float(max(width, height)), height / 2],
                  [0, 0, 1]], np.float64)
    D = np.zeros((4, 1), np.float64)
    # The two highest-order coefficients are fixed to reduce overfitting on
    # moderate-FOV observations; do not extrapolate this into 180° parity.
    flags = (cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC |
             cv2.fisheye.CALIB_FIX_SKEW |
             cv2.fisheye.CALIB_FIX_K3 |
             cv2.fisheye.CALIB_FIX_K4)
    try:
        rms, fitted, distortion, rotations, translations = cv2.fisheye.calibrate(
            objects, points, (width, height), K, D, flags=flags,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 120, 1e-7))
        per_view = []
        tilts = []
        for world, corners, r, t in zip(objects, points, rotations, translations):
            projected, _ = cv2.fisheye.projectPoints(world, r, t, fitted, distortion)
            residual = np.linalg.norm(projected.reshape(-1, 2) - corners.reshape(-1, 2), axis=1)
            per_view.append(float(np.sqrt(np.mean(residual ** 2))))
            rotation, _ = cv2.Rodrigues(r)
            tilts.append(float(np.degrees(np.arccos(np.clip(abs(rotation[2, 2]), 0.0, 1.0)))))
    except (cv2.error, ValueError, np.linalg.LinAlgError) as exc:
        raise FisheyeCalibrationError("OpenCV fisheye calibration failed or was degenerate") from exc
    if not (math.isfinite(rms) and np.isfinite(fitted).all()
            and np.isfinite(distortion).all()
            and all(math.isfinite(v) for v in per_view)):
        raise FisheyeCalibrationError("non-finite fisheye lens model")
    if (rms > max_rms_px or max(per_view) > max_rms_px * 2.5):
        raise FisheyeCalibrationError("fisheye reprojection error exceeds software gate")
    if sum(t >= 15 for t in tilts) < 5 or max(tilts) < 25:
        raise FisheyeCalibrationError("insufficient checkerboard tilt diversity")
    if not (0.05 * width <= fitted[0, 0] <= 5 * width
            and 0.05 * height <= fitted[1, 1] <= 5 * height
            and 0 <= fitted[0, 2] < width and 0 <= fitted[1, 2] < height
            and np.max(np.abs(distortion)) <= 2):
        raise FisheyeCalibrationError("fitted fisheye intrinsics are implausible or unstable")
    return {
        "schema": SCHEMA,
        "lens_model": MODEL,
        "software_calibration": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "image_size": [width, height],
        "checkerboard_inner_corners": [cols, rows],
        "square_mm": float(square_mm),
        "views_used": len(points),
        "image_coverage_fraction": round(coverage, 6),
        "tilted_views_15deg": sum(t >= 15 for t in tilts),
        "max_tilt_deg": round(max(tilts), 4),
        "reprojection_rms_px": round(float(rms), 6),
        "worst_view_rms_px": round(max(per_view), 6),
        "camera_matrix": fitted.tolist(),
        "fisheye_distortion_k1_k2_k3_k4": distortion.reshape(4).tolist(),
    }


def _safe_photos(folder):
    root = Path(folder)
    if root.is_symlink() or root.parent.is_symlink() or not root.is_dir():
        raise FisheyeCalibrationError("fisheye photo folder must be a regular non-symlink directory")
    files = sorted(p for p in root.iterdir()
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if not MIN_VIEWS <= len(files) <= MAX_VIEWS:
        raise FisheyeCalibrationError("need 12..48 checkerboard image files")
    for p in files:
        if p.is_symlink() or not p.is_file() or not stat.S_ISREG(p.stat().st_mode):
            raise FisheyeCalibrationError("unsafe fisheye photo file")
        if not 0 < p.stat().st_size <= MAX_INPUT_BYTES:
            raise FisheyeCalibrationError("fisheye photo exceeds file-size bound")
    return files


def calibrate_photo_folder(folder, *, cols=9, rows=6, square_mm=25.0,
                           max_rms_px=1.5):
    """Offline checkerboard photo analysis; no device access and no writes."""
    _board(cols, rows, square_mm)
    files = _safe_photos(folder)
    views = []
    size = None
    for p in files:
        photo = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if photo is None or photo.dtype != np.uint8 or photo.ndim != 2:
            raise FisheyeCalibrationError("fisheye photo cannot be decoded")
        h, w = photo.shape
        _size((w, h))
        if size is None:
            size = (w, h)
        elif size != (w, h):
            raise FisheyeCalibrationError("fisheye photos must share one exact resolution")
        found, corners = cv2.findChessboardCornersSB(
            photo, (cols, rows), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
        if not found or corners is None:
            # Exact-count requirement avoids silently accepting blurred/missing boards.
            raise FisheyeCalibrationError("checkerboard detection failed in one or more photos")
        views.append(np.asarray(corners, np.float64).reshape(cols * rows, 1, 2))
    assert size is not None
    return calibrate_observations(
        views, size, cols=cols, rows=rows, square_mm=square_mm, max_rms_px=max_rms_px)
