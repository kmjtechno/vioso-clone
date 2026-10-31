"""Camera intrinsic calibration from planar-target observations (OpenCV)."""
from __future__ import annotations

import numpy as np
import cv2

from .configs import CameraIntrinsics


def calibrate_intrinsics(object_points, image_points, size, name="calibrated"):
    """object_points/image_points: lists of (N,3)/(N,2) arrays per view; size=(width,height).

    Returns (CameraIntrinsics, rms_reprojection_error). Needs >=3 views for a stable fit.
    """
    if len(object_points) < 3 or len(object_points) != len(image_points):
        raise ValueError("need >=3 matching views")
    obj = [np.asarray(o, np.float32).reshape(-1, 3) for o in object_points]
    img = [np.asarray(i, np.float32).reshape(-1, 2) for i in image_points]
    w, h = size
    k0 = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], np.float64)
    flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_K3
    rms, k, d, _, _ = cv2.calibrateCamera(obj, img, (w, h), k0, np.zeros(5), flags=flags)
    d = d.ravel()
    return CameraIntrinsics(name, w, h, float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2]),
                            float(d[0]), float(d[1]), 0.0, float(d[2]), float(d[3])), float(rms)


def project(cam: CameraIntrinsics, pts3d, rvec, tvec):
    pts, _ = cv2.projectPoints(np.asarray(pts3d, np.float64), np.asarray(rvec, np.float64),
                               np.asarray(tvec, np.float64), np.array(cam.matrix),
                               np.array(cam.dist_coeffs))
    return pts.reshape(-1, 2)
