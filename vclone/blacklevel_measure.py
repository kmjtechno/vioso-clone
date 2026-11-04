"""Read-only black-frame optical diagnostic for independent multi-projector QA.

Uses owner-supplied camera measurements, not vendor blacklevel algorithms.
Reports encoded camera pixel intensity, never certified luminance (cd/m2).
"""
from __future__ import annotations

import json
from pathlib import Path
import stat

import numpy as np

from .capture_check import _read_png
from .optical_roi import read_camera_mask

SCHEMA = "kmj.blacklevel.frames.v1"
MAX_MANIFEST_BYTES = 64 * 1024


class BlackLevelError(ValueError):
    """Unsafe black-frame samples, masks or inconsistent measured input."""


def _png_name(name):
    if (not isinstance(name, str) or not name
            or not name.lower().endswith(".png") or name in (".", "..")
            or Path(name).name != name or "/" in name or "\\" in name
            or len(name) > 160):
        raise BlackLevelError("frame names must be plain PNG basenames in capture folder")
    return name


def _image(folder, name, size):
    try:
        return _read_png(folder / _png_name(name), size)
    except (ValueError, OSError) as exc:
        raise BlackLevelError("invalid or unsafe grayscale camera PNG") from exc


def analyze_black_frames(manifest_path):
    """Screen grayscale blackframes and approximate overlap dark-level buildup.

    The result is a **camera encoded-value diagnostic**, not a projector
    correction texture or physically measured cd/m2 map. Fixed camera
    exposure/photometry and frame acquisition must be independently verified.
    """
    path = Path(manifest_path)
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise BlackLevelError("black-frame manifest must be regular non-symlink JSON")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MANIFEST_BYTES:
        raise BlackLevelError("black-frame manifest exceeds 64 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          parse_constant=lambda _x: (_ for _ in ()).throw(
                              BlackLevelError("non-finite JSON constant")))
    except (ValueError, OSError, UnicodeError) as exc:
        raise BlackLevelError("invalid black-frame manifest JSON") from exc
    keys = {"schema", "acquisition_mode", "camera_size", "ambient", "projectors"}
    if (not isinstance(data, dict)
            or set(data) not in (keys, keys | {"camera_roi"})
            or data.get("schema") != SCHEMA
            or data.get("acquisition_mode") != "single_projector_black_vs_ambient"):
        raise BlackLevelError("unexpected black-frame manifest schema")
    size = data["camera_size"]
    if (not isinstance(size, list) or len(size) != 2
            or any(type(n) is not int for n in size)
            or not 2 <= size[0] <= 4096 or not 2 <= size[1] <= 2160
            or size[0] * size[1] > 4096 * 2160):
        raise BlackLevelError("camera frame dimensions are invalid")
    width, height = size
    projects = data["projectors"]
    if not isinstance(projects, list) or not 2 <= len(projects) <= 8:
        raise BlackLevelError("need between 2 and 8 projector black frames")
    names = []
    for item in projects:
        if not isinstance(item, dict) or set(item) != {
            "name", "black_frame", "coverage_mask"
        }:
            raise BlackLevelError("invalid projector measurement entry")
        name = item["name"]
        if (not isinstance(name, str) or not 1 <= len(name) <= 60
                or not name.isprintable() or name in names):
            raise BlackLevelError("projector labels must be distinct printable names")
        names.append(name)
        _png_name(item["black_frame"])
        _png_name(item["coverage_mask"])
    ambient_name = _png_name(data["ambient"])
    folder = path.parent
    roi = (np.ones((height, width), dtype=np.bool_)
           if "camera_roi" not in data else
           read_camera_mask(folder / _png_name(data["camera_roi"]),
                            (height, width)))
    ambient = _image(folder, ambient_name, (width, height))
    ambient_values = ambient[roi]
    if len(ambient_values) < 4:
        raise BlackLevelError("camera ROI is empty")
    if float(np.percentile(ambient_values, 99)) >= 254:
        raise BlackLevelError("ambient frame saturated: cannot measure dark levels")
    composite = ambient.astype(np.float32)
    coverage_count = np.zeros((height, width), dtype=np.uint8)
    entries = []
    for item in projects:
        white_mask = _image(folder, item["coverage_mask"], (width, height))
        if not np.logical_or(white_mask == 0, white_mask == 255).all():
            raise BlackLevelError("coverage mask must be binary: white=covered, black=not covered")
        covered = (white_mask == 255) & roi
        coverage_pixels = int(np.count_nonzero(covered))
        if coverage_pixels < 4:
            raise BlackLevelError("projector has no usable camera-space coverage")
        captured = _image(folder, item["black_frame"], (width, height))
        darkening = float(np.count_nonzero((captured < ambient) & covered)
                          / coverage_pixels)
        if darkening > 0.25:
            raise BlackLevelError("black frame intensity below ambient on too many pixels")
        residual = np.maximum(0, captured.astype(np.float32) -
                             ambient.astype(np.float32))
        values = residual[covered]
        coverage_count[covered] += 1
        composite[covered] += residual[covered]
        entries.append({
            "projector": item["name"],
            "covered_camera_pixels": coverage_pixels,
            "black_minus_ambient_median_code": round(float(np.median(values)), 4),
            "black_minus_ambient_p95_code": round(float(np.percentile(values, 95)), 4),
            "negative_vs_ambient_fraction": round(darkening, 6),
        })
    union = coverage_count > 0
    overlap = coverage_count > 1
    if not union.any():
        raise BlackLevelError("no measured projection coverage")
    nonoverlap = union & ~overlap
    overlap_stats = (
        round(float(np.percentile(composite[overlap], 95)), 4)
        if overlap.any() else None
    )
    separate_stats = (
        round(float(np.percentile(composite[nonoverlap], 95)), 4)
        if nonoverlap.any() else None
    )
    return {
        "schema": "kmj.blacklevel.analysis.v1",
        "software_blacklevel_analysis": "COMPUTED",
        "camera_response_units": "encoded_8bit_grayscale_not_cd_per_m2",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "projectors_checked": len(projects),
        "camera_roi_fraction": round(float(roi.mean()), 6),
        "overlap_fraction_of_covered_pixels": round(
            float(np.count_nonzero(overlap) / np.count_nonzero(union)), 6),
        "ambient_median_code": round(float(np.median(ambient_values)), 4),
        "overlap_aggregate_black_p95_code": overlap_stats,
        "nonoverlap_aggregate_black_p95_code": separate_stats,
        "projectors": entries,
        "interpretation": "approximate additive camera-space diagnostic only",
    }
