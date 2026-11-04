"""Opt-in offline fisheye camera rectification for Gray-code calibration.

Never changes source photos or captures, cameras, display state, private source
profiles or the owner's optical project. Fisheye coefficients are explicitly
OpenCV fisheye (k1,k2,k3,k4), NOT pinhole (k1,k2,p1,p2,k3).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import stat

import cv2
import numpy as np

SCHEMA = "kmj.fisheye.intrinsics.v1"
MAX_PROFILE_BYTES = 65536
MAX_CAMERA_PIXELS = 4096 * 2160


class FisheyeRectifyError(ValueError):
    """Invalid lens-model evidence, dimensions or rectification map."""


def _finite(value, label, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise FisheyeRectifyError(f"invalid finite {label}")
    return float(value)


def _matrix(value, rows, columns, label):
    if not isinstance(value, list) or len(value) != rows:
        raise FisheyeRectifyError(f"invalid {label} matrix")
    if any(not isinstance(row, list) or len(row) != columns for row in value):
        raise FisheyeRectifyError(f"invalid {label} matrix")
    if any(type(c) not in (int, float) or not math.isfinite(c)
           for row in value for c in row):
        raise FisheyeRectifyError(f"non-finite {label} matrix")
    return np.asarray(value, dtype=np.float64)


def validate_fisheye_profile(profile):
    """Validate the exact critical fields from M32 output (no file reads)."""
    if (not isinstance(profile, dict) or profile.get("schema") != SCHEMA
            or profile.get("lens_model") != "opencv_fisheye"
            or profile.get("software_calibration") != "PASS"
            or profile.get("hardware_acceptance") != "NOT_VERIFIED"
            or profile.get("native_vioso_sps_compatible") is not False):
        raise FisheyeRectifyError("incompatible or unverified fisheye profile")
    size = profile.get("image_size")
    if (not isinstance(size, list) or len(size) != 2
            or any(type(n) is not int or not 64 <= n <= 4096 for n in size)
            or size[0] * size[1] > MAX_CAMERA_PIXELS):
        raise FisheyeRectifyError("invalid bounded fisheye image dimensions")
    n = profile.get("views_used")
    if type(n) is not int or not 12 <= n <= 48:
        raise FisheyeRectifyError("fisheye profile has insufficient checkerboard evidence")
    rms = _finite(profile.get("reprojection_rms_px"), "fisheye reprojection RMS", 0, 5)
    K = _matrix(profile.get("camera_matrix"), 3, 3, "fisheye camera")
    d = profile.get("fisheye_distortion_k1_k2_k3_k4")
    if (not isinstance(d, list) or len(d) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or abs(v) > 2 for v in d)):
        raise FisheyeRectifyError("invalid OpenCV fisheye distortion coefficients")
    w, h = size
    if (not 0.05 * w <= K[0, 0] <= 5 * w
            or not 0.05 * h <= K[1, 1] <= 5 * h
            or not 0 <= K[0, 2] <= w or not 0 <= K[1, 2] <= h
            or abs(K[0, 1]) > 1e-6 or abs(K[1, 0]) > 1e-6
            or abs(K[2, 0]) > 1e-6 or abs(K[2, 1]) > 1e-6
            or abs(K[2, 2] - 1) > 1e-6):
        raise FisheyeRectifyError("physically implausible fisheye camera matrix")
    return {"size": (w, h), "K": K, "D": np.asarray(d, dtype=np.float64).reshape(4, 1),
            "rms": rms, "views": n}


def read_fisheye_profile(path):
    """Load an existing M32 stdout JSON file, never following a profile link."""
    file = Path(path)
    if file.is_symlink() or file.parent.is_symlink() or not file.is_file():
        raise FisheyeRectifyError("fisheye profile must be a regular non-symlink JSON")
    try:
        info = file.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PROFILE_BYTES:
            raise FisheyeRectifyError("fisheye profile exceeds 64 KiB")
        data = json.loads(file.read_text(encoding="utf-8"),
                          parse_constant=lambda _v: (_ for _ in ()).throw(
                              FisheyeRectifyError("non-finite fisheye JSON")))
    except (ValueError, UnicodeError, OSError) as exc:
        raise FisheyeRectifyError("fisheye profile JSON invalid") from exc
    validate_fisheye_profile(data)
    return data


def _balance(value):
    return _finite(value, "fisheye rectification balance", 0, 1)


class FisheyeRectifier:
    """Reusable raw-fisheye -> virtual pinhole remap, including validity mask."""

    def __init__(self, profile, *, balance=0.25):
        model = validate_fisheye_profile(profile)
        w, h = model["size"]
        value = _balance(balance)
        try:
            K, D = model["K"], model["D"]
            new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                K, D, (w, h), np.eye(3), balance=value, new_size=(w, h))
            self.map_x, self.map_y = cv2.fisheye.initUndistortRectifyMap(
                K, D, np.eye(3), new_K, (w, h), cv2.CV_32FC1)
        except (cv2.error, TypeError, ValueError) as exc:
            raise FisheyeRectifyError("fisheye rectification map computation failed") from exc
        if (self.map_x.shape != (h, w) or self.map_y.shape != (h, w)
                or not np.isfinite(self.map_x).all()
                or not np.isfinite(self.map_y).all()
                or not np.isfinite(new_K).all()):
            raise FisheyeRectifyError("invalid fisheye rectification mapping")
        # Linear interpolation must not sample outside the raw image.
        self.valid = ((self.map_x >= 0) & (self.map_y >= 0)
                      & (self.map_x < w - 1) & (self.map_y < h - 1))
        self.valid_pixels = int(np.count_nonzero(self.valid))
        if self.valid_pixels < max(4, w * h // 10):
            raise FisheyeRectifyError("fisheye rectification has insufficient valid sensor area")
        self.size = (w, h)
        self.balance = value

    def image(self, raw):
        w, h = self.size
        if (not isinstance(raw, np.ndarray) or raw.dtype != np.uint8
                or raw.shape != (h, w)):
            raise FisheyeRectifyError("raw fisheye frame must match 8-bit calibration dimensions")
        out = cv2.remap(raw, self.map_x, self.map_y, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out[~self.valid] = 0
        return out

    def mask(self, raw_mask):
        w, h = self.size
        if (not isinstance(raw_mask, np.ndarray) or raw_mask.dtype != np.bool_
                or raw_mask.shape != (h, w)):
            raise FisheyeRectifyError("raw fisheye camera ROI must be a matching boolean mask")
        remapped = cv2.remap(raw_mask.astype(np.uint8), self.map_x, self.map_y,
                             cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                             borderValue=0).astype(np.bool_)
        remapped &= self.valid
        if int(np.count_nonzero(remapped)) < 4:
            raise FisheyeRectifyError("fisheye camera ROI has no valid rectified pixels")
        return remapped

    def report(self):
        w, h = self.size
        return {
            "schema": "kmj.fisheye.rectification.v1",
            "rectification": "APPLIED",
            "camera_size": [w, h],
            "balance": self.balance,
            "valid_rectified_fraction": round(self.valid_pixels / (w * h), 6),
            "hardware_optical_acceptance": "NOT_VERIFIED",
            "native_vioso_sps_compatible": False,
        }


def export_rectified_preview(raw_path, profile_path, destination, *, balance=0.25):
    """Write a NEW rectified grayscale PNG exclusively; never overwrite owner data.

    Useful for measuring virtual-pinhole camera corners before Calibrate. The
    raw fisheye PNG, calibration profile and original capture are read-only.
    """
    from .capture_check import _read_png

    target = Path(destination)
    if (target.suffix.lower() != ".png" or target.is_symlink()
            or target.exists() or not target.parent.is_dir()
            or target.parent.is_symlink()):
        raise FisheyeRectifyError("preview destination must be a new PNG in a regular directory")
    rectifier = FisheyeRectifier(read_fisheye_profile(profile_path), balance=balance)
    raw = _read_png(Path(raw_path), rectifier.size)
    preview = rectifier.image(raw)
    try:
        ok, payload = cv2.imencode(".png", preview)
    except cv2.error as exc:
        raise FisheyeRectifyError("fisheye PNG preview encoding failed") from exc
    if not ok:
        raise FisheyeRectifyError("fisheye PNG preview encoding failed")
    # Reject an existing owner file even if it appears between path checking
    # and output open (without truncating either image or project file).
    with target.open("xb") as file:
        file.write(payload.tobytes())
    return rectifier.report()
