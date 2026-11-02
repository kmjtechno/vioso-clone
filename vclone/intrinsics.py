"""Camera intrinsic calibration from planar-target observations (OpenCV)."""
from __future__ import annotations

import numpy as np
import cv2

from .configs import CameraIntrinsics


MIN_VIEWS = 12
MAX_RMS_PX = 1.0
MIN_TILT_VIEWS = 5
MIN_TILT_DEG = 15.0
MIN_MAX_TILT_DEG = 25.0
GRID_COLS, GRID_ROWS = 4, 3
MIN_COVERAGE = 0.5


class IntrinsicsRejected(ValueError):
    """Capture failed the quality gates; no profile is produced."""

    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def _solve(object_points, image_points, size, name):
    """Returns (CameraIntrinsics, rms, rvecs)."""
    if len(object_points) < 3 or len(object_points) != len(image_points):
        raise ValueError("need >=3 matching views")
    obj = [np.asarray(o, np.float32).reshape(-1, 3) for o in object_points]
    img = [np.asarray(i, np.float32).reshape(-1, 2) for i in image_points]
    w, h = size
    k0 = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], np.float64)
    flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_K3
    rms, k, d, rvecs, _ = cv2.calibrateCamera(obj, img, (w, h), k0, np.zeros(5), flags=flags)
    d = d.ravel()
    cam = CameraIntrinsics(name, w, h, float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2]),
                           float(d[0]), float(d[1]), 0.0, float(d[2]), float(d[3]))
    return cam, float(rms), rvecs


def calibrate_intrinsics(object_points, image_points, size, name="calibrated"):
    """object_points/image_points: lists of (N,3)/(N,2) arrays per view; size=(width,height).

    Returns (CameraIntrinsics, rms_reprojection_error). Needs >=3 views for a stable fit.
    No quality gates: use calibrate_checked for anything that becomes a profile.
    """
    cam, rms, _ = _solve(object_points, image_points, size, name)
    return cam, rms


def view_tilts_deg(rvecs):
    out = []
    for rv in rvecs:
        R, _ = cv2.Rodrigues(np.asarray(rv, np.float64))
        out.append(float(np.degrees(np.arccos(min(1.0, abs(R[2, 2]))))))
    return out


def coverage_fraction(image_points, size):
    """Count only finite, actually visible image points in the coverage grid.

    Off-screen pixels must never be clamped to an edge cell: this would let a
    completely invalid calibration falsely pass the minimum coverage gate.
    """
    dimensions = np.asarray(size, dtype=np.float64)
    if dimensions.shape != (2,) or not np.isfinite(dimensions).all() or np.any(dimensions <= 0):
        raise ValueError("positive finite image dimensions required")
    width, height = dimensions
    hit = set()
    for v in image_points:
        points = np.asarray(v, dtype=np.float64).reshape(-1, 2)
        for x, y in points:
            if not (np.isfinite(x) and np.isfinite(y)
                    and 0 <= x < width and 0 <= y < height):
                continue
            hit.add((min(GRID_COLS - 1, int(x * GRID_COLS / width)),
                     min(GRID_ROWS - 1, int(y * GRID_ROWS / height))))
    return len(hit) / float(GRID_COLS * GRID_ROWS)


def quality_reasons(rms, rvecs, image_points, size, max_rms=MAX_RMS_PX):
    """Reasons a capture must not become a profile (empty list = passes). Gates follow the
    user's own KMJ CalibrationNew tooling: view count, board tilt diversity, image coverage, RMS."""
    reasons = []
    n = len(image_points)
    if n < MIN_VIEWS:
        reasons.append(f"too few views: {n} < {MIN_VIEWS}")
    tilts = view_tilts_deg(rvecs)
    if sum(t >= MIN_TILT_DEG for t in tilts) < MIN_TILT_VIEWS or max(tilts, default=0.0) < MIN_MAX_TILT_DEG:
        reasons.append(f"insufficient board tilt diversity: need >={MIN_TILT_VIEWS} views tilted >={MIN_TILT_DEG:.0f} deg "
                       f"and one >={MIN_MAX_TILT_DEG:.0f} deg (max seen {max(tilts, default=0.0):.1f} deg)")
    cov = coverage_fraction(image_points, size)
    if cov < MIN_COVERAGE:
        reasons.append(f"image coverage {cov * 100:.0f}% < {MIN_COVERAGE * 100:.0f}% "
                       f"({GRID_COLS}x{GRID_ROWS} grid): move the board toward all corners/edges")
    if not rms <= max_rms:
        reasons.append(f"rms reprojection {rms:.3f} px > {max_rms:.2f} px")
    return reasons


def calibrate_with_gates(object_points, image_points, size, name="calibrated", max_rms=MAX_RMS_PX):
    """Returns (CameraIntrinsics, rms, reasons); reasons == [] means every gate passed."""
    cam, rms, rvecs = _solve(object_points, image_points, size, name)
    return cam, rms, quality_reasons(rms, rvecs, image_points, size, max_rms)


def calibrate_checked(object_points, image_points, size, name="calibrated", max_rms=MAX_RMS_PX):
    """Like calibrate_with_gates but raises IntrinsicsRejected (listing every failed gate) instead
    of returning a profile that did not pass."""
    cam, rms, reasons = calibrate_with_gates(object_points, image_points, size, name, max_rms)
    if reasons:
        raise IntrinsicsRejected(reasons)
    return cam, rms


def project(cam: CameraIntrinsics, pts3d, rvec, tvec):
    pts, _ = cv2.projectPoints(np.asarray(pts3d, np.float64), np.asarray(rvec, np.float64),
                               np.asarray(tvec, np.float64), np.array(cam.matrix),
                               np.array(cam.dist_coeffs))
    return pts.reshape(-1, 2)
