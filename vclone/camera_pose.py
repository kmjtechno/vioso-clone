"""Independent 3D-marker to camera pose fit with reprojection quality gates.

A clean-room optical geometry tool inspired only by public capability
descriptions, not proprietary pose routines or calibration binaries.
No camera/projector, installed VIOSO code or owner file is changed.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import stat

import cv2
import numpy as np

SCHEMA = "kmj.camera-pose.markers.v1"
MAX_JSON_BYTES = 64 * 1024
MAX_MARKERS = 128


class CameraPoseError(ValueError):
    """Untrusted marker geometry or a reprojection-gate failure."""


def _bounded_float(v, label, lo, hi):
    if type(v) not in (float, int) or not math.isfinite(v) or not lo <= v <= hi:
        raise CameraPoseError(f"{label} outside finite permitted range")
    return float(v)


def _vector(value, n, label, low, high):
    if not isinstance(value, list) or len(value) != n:
        raise CameraPoseError(f"{label} must have {n} values")
    return [_bounded_float(v, label, low, high) for v in value]


def load_markers(path):
    """Read strict non-symlink owner-supplied correspondence JSON, no writes."""
    p = Path(path)
    if p.is_symlink() or p.parent.is_symlink() or not p.is_file():
        raise CameraPoseError("marker input must be regular non-symlink JSON file")
    info = p.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_JSON_BYTES:
        raise CameraPoseError("marker JSON must be below 64 KiB")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"),
                         parse_constant=lambda _v: (_ for _ in ()).throw(
                             CameraPoseError("non-finite JSON constant")))
    except (OSError, UnicodeError, ValueError) as exc:
        raise CameraPoseError("marker JSON cannot be decoded") from exc
    return obj


def estimate_pose(data, *, max_rms_px=1.5, min_inlier_fraction=0.70):
    """Fit world->camera extrinsics from >=6 non-coplanar correspondences.

    RANSAC removes inconsistent markers, followed by bounded LM refinement on
    the inliers. Result is an initial mathematical pose, not optical acceptance.
    """
    _bounded_float(max_rms_px, "max_rms_px", 0.1, 10.0)
    _bounded_float(min_inlier_fraction, "min_inlier_fraction", 0.5, 1.0)
    if not isinstance(data, dict) or set(data) != {
        "schema", "world_units", "image_size", "intrinsics", "markers"
    } or data.get("schema") != SCHEMA or data.get("world_units") not in ("mm", "m"):
        raise CameraPoseError("unexpected marker input schema or world units")
    size = data["image_size"]
    if (not isinstance(size, list) or len(size) != 2
            or any(type(v) is not int for v in size)
            or not 2 <= size[0] <= 4096 or not 2 <= size[1] <= 2160
            or size[0] * size[1] > 4096 * 2160):
        raise CameraPoseError("invalid bounded camera resolution")
    width, height = size
    intr = data["intrinsics"]
    if not isinstance(intr, dict) or set(intr) != {"fx", "fy", "cx", "cy", "distortion"}:
        raise CameraPoseError("invalid camera intrinsics schema")
    fx = _bounded_float(intr["fx"], "fx", 1.0, 100000.0)
    fy = _bounded_float(intr["fy"], "fy", 1.0, 100000.0)
    cx = _bounded_float(intr["cx"], "cx", 0.0, float(width))
    cy = _bounded_float(intr["cy"], "cy", 0.0, float(height))
    dist = np.asarray(_vector(intr["distortion"], 5, "distortion", -2.0, 2.0),
                      dtype=np.float64)
    camera_matrix = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
                             dtype=np.float64)
    markers = data["markers"]
    if not isinstance(markers, list) or not 6 <= len(markers) <= MAX_MARKERS:
        raise CameraPoseError("six to 128 marker correspondences required")
    world, pixels = [], []
    for marker in markers:
        if not isinstance(marker, dict) or set(marker) != {"world", "image"}:
            raise CameraPoseError("invalid marker fields")
        w = _vector(marker["world"], 3, "world", -1e6, 1e6)
        p = _vector(marker["image"], 2, "image", 0.0, float(max(width, height)))
        if not (p[0] < width and p[1] < height):
            raise CameraPoseError("marker pixel outside camera image")
        world.append(w)
        pixels.append(p)
    w = np.asarray(world, dtype=np.float64)
    q = np.asarray(pixels, dtype=np.float64)
    if np.unique(w, axis=0).shape[0] != len(w):
        raise CameraPoseError("duplicate world marker coordinates")
    if np.unique(q, axis=0).shape[0] != len(q):
        raise CameraPoseError("duplicate camera marker coordinates")
    singular = np.linalg.svd(w - w.mean(axis=0), compute_uv=False)
    if singular[0] <= 0 or singular[-1] / singular[0] < 1e-3:
        raise CameraPoseError("3D markers are coplanar or poorly distributed")
    if np.ptp(q[:, 0]) < 5.0 or np.ptp(q[:, 1]) < 5.0:
        raise CameraPoseError("camera markers are too narrowly distributed")
    try:
        found, rot, translation, inliers = cv2.solvePnPRansac(
            w, q, camera_matrix, dist, iterationsCount=400,
            reprojectionError=float(max_rms_px) * 2.0,
            confidence=0.999, flags=cv2.SOLVEPNP_EPNP)
        if not found or inliers is None or len(inliers) < 6:
            raise CameraPoseError("insufficient PnP marker consensus")
        ids = inliers.reshape(-1)
        if len(ids) / len(w) < min_inlier_fraction:
            raise CameraPoseError("PnP marker inlier fraction below gate")
        if hasattr(cv2, "solvePnPRefineLM"):
            rot, translation = cv2.solvePnPRefineLM(
                w[ids], q[ids], camera_matrix, dist, rot, translation)
        projected, _ = cv2.projectPoints(w[ids], rot, translation,
                                         camera_matrix, dist)
        reproj = np.linalg.norm(projected.reshape(-1, 2) - q[ids], axis=1)
        rotation, _ = cv2.Rodrigues(rot)
    except cv2.error as exc:
        raise CameraPoseError("OpenCV pose fit failed") from exc
    if (not np.isfinite(rotation).all() or not np.isfinite(translation).all()
            or not np.isfinite(reproj).all()
            or abs(float(np.linalg.det(rotation)) - 1.0) > 1e-3):
        raise CameraPoseError("invalid or unstable PnP solution")
    rms = float(np.sqrt(np.mean(reproj ** 2)))
    if rms > max_rms_px or float(reproj.max()) > 3 * max_rms_px:
        raise CameraPoseError("marker reprojection error above quality gate")
    cam_points = (rotation @ w[ids].T + translation.reshape(3, 1)).T
    if not (cam_points[:, 2] > 0).all():
        raise CameraPoseError("PnP places observed markers behind camera")
    center = -(rotation.T @ translation.reshape(3))
    return {
        "schema": "kmj.camera-pose.solution.v1",
        "software_pose_quality": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "world_units": data["world_units"],
        "markers_total": len(w),
        "markers_inlier": len(ids),
        "inlier_fraction": round(len(ids) / len(w), 6),
        "reprojection_rms_px": round(rms, 6),
        "max_reprojection_px": round(float(reproj.max()), 6),
        "rotation_vector_world_to_camera": [float(v) for v in rot.reshape(3)],
        "translation_world_to_camera": [float(v) for v in translation.reshape(3)],
        "rotation_matrix_world_to_camera": rotation.tolist(),
        "camera_center_world": [float(v) for v in center],
    }
