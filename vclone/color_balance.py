"""Opt-in bounded per-projector color-balance preview (not physical color calibration).

This independently implemented software filter subtracts a bounded encoded
black offset, then applies per-channel gains to already warped/blended BGR
uint8 frames. It cannot measure or certify real projector black level, gamma,
brightness matching, gamut or white point.
"""
from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
import stat

import numpy as np

SCHEMA = "kmj.color-balance.preview.v1"
MAX_PROFILE_BYTES = 16384


class ColorBalanceError(ValueError):
    """Unsafe or incompatible preview color-balance configuration."""


def _triple(value, label, low, high):
    if not isinstance(value, list) or len(value) != 3:
        raise ColorBalanceError(f"{label} must be three BGR numbers")
    if any(type(v) not in (int, float) or not isfinite(v)
           or not low <= v <= high for v in value):
        raise ColorBalanceError(f"{label} must contain finite BGR values in {low}..{high}")
    return [float(v) for v in value]


def validate_profiles(profiles, count):
    """Validate exact, versioned per-projector settings without external data."""
    if type(count) is not int or not 2 <= count <= 8:
        raise ColorBalanceError("color-balance requires 2..8 projectors")
    if not isinstance(profiles, list) or len(profiles) != count:
        raise ColorBalanceError("color-balance profile count must match projector count")
    normalized = []
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {"gain_bgr", "black_subtract_bgr"}:
            raise ColorBalanceError("profile needs exactly gain_bgr and black_subtract_bgr")
        normalized.append({
            "gain_bgr": _triple(item["gain_bgr"], "gain_bgr", 0.25, 2.0),
            "black_subtract_bgr": _triple(
                item["black_subtract_bgr"], "black_subtract_bgr", 0.0, 64.0),
        })
    return normalized


def load_profile(path, count):
    """Read strict JSON from a bounded regular file, with no hardware access."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ColorBalanceError("color-balance profile must be a regular non-symlink file")
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PROFILE_BYTES:
        raise ColorBalanceError("color-balance profile exceeds 16 KiB size bound")
    try:
        data = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ColorBalanceError("invalid JSON constant")))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ColorBalanceError("invalid color-balance JSON file") from exc
    if not isinstance(data, dict) or set(data) != {"schema", "projectors"} or data["schema"] != SCHEMA:
        raise ColorBalanceError("unexpected color-balance profile schema")
    return validate_profiles(data["projectors"], count)


def apply_preview(frame, profile):
    """Apply a software-only BGR correction. Black pixels remain black."""
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ColorBalanceError("preview must be uint8 BGR")
    if frame.size == 0:
        raise ColorBalanceError("empty projector preview")
    # Internal application accepts a single validated profile without the
    # multi-projector count requirement.
    if not isinstance(profile, dict) or set(profile) != {"gain_bgr", "black_subtract_bgr"}:
        raise ColorBalanceError("invalid projector color-balance item")
    gain = np.asarray(_triple(profile["gain_bgr"], "gain_bgr", 0.25, 2.0), dtype=np.float32)
    offset = np.asarray(
        _triple(profile["black_subtract_bgr"], "black_subtract_bgr", 0.0, 64.0),
        dtype=np.float32)
    balanced = np.maximum(0, frame.astype(np.float32) - offset.reshape((1, 1, 3)))
    balanced *= gain.reshape((1, 1, 3))
    return np.clip(np.rint(balanced), 0, 255).astype(np.uint8)
