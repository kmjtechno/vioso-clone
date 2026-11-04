"""Read-only two-projector content-space seam preflight.

This is a software-only sanity check on independently calibrated clone meshes,
not measured projector illumination, synchronized output or VIOSO 7 format
compatibility. It never opens a camera, display, image file or output folder.
"""
from __future__ import annotations

from math import isfinite

import numpy as np

from . import calib
from .multi_output import MAX_CONTENT_PIXELS, MultiExportError, _validated_mesh
from .project import Project


class TwoProjectorError(ValueError):
    """Invalid two-projector calibration bundle or quantitative thresholds."""


def _threshold(value, label, lo=0.0, hi=1.0):
    if type(value) not in (int, float) or not isfinite(value) or not lo <= value <= hi:
        raise TwoProjectorError(f"{label} must be a finite value in {lo}..{hi}")
    return float(value)


def _content_size(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(x) is not int for x in value)
            or not 64 <= value[0] <= 4096 or not 64 <= value[1] <= 2160
            or value[0] * value[1] > MAX_CONTENT_PIXELS):
        raise TwoProjectorError("two-projector content dimensions exceed safety bounds")
    return tuple(value)


def _bbox(mask):
    y, x = np.nonzero(mask)
    if x.size == 0:
        raise TwoProjectorError("a calibrated projector has no content coverage")
    x0, x1 = int(x.min()), int(x.max())
    y0, y1 = int(y.min()), int(y.max())
    return [x0, y0, x1 - x0 + 1, y1 - y0 + 1]


def check_two_projectors(
    projects,
    *,
    min_overlap=0.05,
    max_overlap=0.85,
    min_union_coverage=0.50,
):
    """Compare two bounded, independently supplied clone optical meshes.

    Thresholds use overlap as a *fraction of the smaller projector footprint*,
    and union coverage as a fraction of the content image. Mirrored or completely
    duplicate meshes must not silently pass as a valid two-projector blend.
    """
    if (not isinstance(projects, (tuple, list)) or len(projects) != 2
            or any(not isinstance(p, Project) for p in projects)
            or projects[0] is projects[1]):
        raise TwoProjectorError("supply two distinct calibrated clone projects")
    lower = _threshold(min_overlap, "minimum overlap")
    upper = _threshold(max_overlap, "maximum overlap")
    coverage_floor = _threshold(min_union_coverage, "minimum union coverage")
    if not 0 < lower < upper < 1 or not 0 < coverage_floor <= 1:
        raise TwoProjectorError("overlap thresholds must be strictly ordered within 0..1")
    if any(not isinstance(p.scan, dict) for p in projects):
        raise TwoProjectorError("project scan metadata must be an object")
    identifiers = [p.content_space for p in projects]
    if (all(isinstance(x, str) and x for x in identifiers)
            and identifiers[0] != identifiers[1]):
        raise TwoProjectorError("project content space identifiers do not match")
    size = _content_size(projects[0].scan.get("content_size"))
    if projects[1].scan.get("content_size") not in (list(size), tuple(size)):
        raise TwoProjectorError("both projects must share exactly one content coordinate system")
    try:
        meshes = [_validated_mesh(p, size) for p in projects]
        if any(mesh.shape[0] * mesh.shape[1] > 65536
               for mesh, _ in meshes):
            raise TwoProjectorError("calibration mesh exceeds 65536 nodes")
        masks = [calib.coverage_mask(mesh, size) for mesh, _ in meshes]
    except (MultiExportError, ValueError, TypeError, IndexError) as exc:
        if isinstance(exc, TwoProjectorError):
            raise
        raise TwoProjectorError("invalid or incomplete calibrated projector mesh") from None
    if any(mask.dtype != np.bool_ or mask.shape != (size[1], size[0])
           or not mask.any() for mask in masks):
        raise TwoProjectorError("a calibrated projector has no valid content coverage")
    a, b = masks
    a_count, b_count = int(np.count_nonzero(a)), int(np.count_nonzero(b))
    both = a & b
    union = a | b
    same_pixels = int(np.count_nonzero(both))
    total = size[0] * size[1]
    footprint = min(a_count, b_count)
    overlap_small = same_pixels / footprint
    overlap_content = same_pixels / total
    union_content = int(np.count_nonzero(union)) / total

    # No optical acceptance: even a good mesh can be from mock images, stale
    # cameras, wrong projector coordinates or different exposure.
    if overlap_small < lower:
        gate = "BLOCKED_INSUFFICIENT_SEAM_OVERLAP"
    elif overlap_small > upper:
        gate = "BLOCKED_EXCESSIVE_OR_DUPLICATE_OVERLAP"
    elif union_content < coverage_floor:
        gate = "BLOCKED_LOW_CONTENT_COVERAGE"
    else:
        gate = "PASS_SOFTWARE_GEOMETRY_ONLY"

    return {
        "schema": "kmj.two-projector.seam-check.v1",
        "read_only": True,
        "projector_operation": "NONE",
        "camera_operation": "NONE",
        "content_size": list(size),
        "projector_sizes": [list(dims) for _, dims in meshes],
        "content_space_identity": (
            "MATCHING"
            if all(isinstance(x, str) and x for x in identifiers)
            else "NOT_VERIFIED"
        ),
        "coverage_fractions": [round(a_count / total, 6), round(b_count / total, 6)],
        "content_bounds_xywh": [_bbox(a), _bbox(b)],
        "overlap_fraction_of_smaller_projector": round(overlap_small, 6),
        "overlap_fraction_of_content": round(overlap_content, 6),
        "union_coverage_fraction": round(union_content, 6),
        "uncovered_fraction": round(1 - union_content, 6),
        "min_overlap_fraction": lower,
        "max_overlap_fraction": upper,
        "min_union_coverage_fraction": coverage_floor,
        "software_seam_gate": gate,
        "hardware_optical_acceptance": "NOT_VERIFIED",
        "projector_identity_mapping": "NOT_VERIFIED",
        "projection_synchronization": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
    }
