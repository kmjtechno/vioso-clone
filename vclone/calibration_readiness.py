"""Camera-to-projector software readiness checklist (metadata-only).

This cannot certify hardware: a project file can be edited without a camera,
projector, or captured image. Never open paths, media, or network from here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessStage:
    key: str
    title: str
    status: str
    next_action: str


def _size(value, max_width=4096, max_height=2160):
    return (
        isinstance(value, (list, tuple)) and len(value) == 2
        and all(type(x) is int for x in value)
        and 1 <= value[0] <= max_width and 1 <= value[1] <= max_height
    )


def _corners(value):
    return isinstance(value, (list, tuple)) and len(value) == 4


def software_readiness(project):
    """Describe progress without reading potentially private project paths.

    Avoid percentages: synthetic/persisted metadata is not hardware proof.
    """
    scan = getattr(project, "scan", None)
    if not isinstance(scan, dict):
        scan = {}
    result = getattr(project, "result", None)
    if not isinstance(result, dict):
        result = {}
    displays = getattr(project, "displays", None)
    if not isinstance(displays, list):
        displays = []
    cam = getattr(project, "camera", None)
    capture_configured = (
        bool(scan.get("dir"))
        and _size(scan.get("proj_size"), 1920, 1080)
        and _size(scan.get("content_size"))
    )
    corners_configured = (
        _corners(scan.get("cam_corners"))
        and _corners(scan.get("content_corners"))
    )
    mesh_present = isinstance(result.get("mesh"), list) and bool(result["mesh"])
    out = (
        ReadinessStage(
            "camera", "1  Camera-only preflight",
            "OPERATOR_TEST_REQUIRED",
            "Connect one camera and inspect six live frames; do not save the login.",
        ),
        ReadinessStage(
            "intrinsics", "2  Fisheye intrinsics",
            "PROFILE_CONFIGURED_NOT_VERIFIED" if cam is not None or
            bool(scan.get("fisheye_profile")) else "INPUT_REQUIRED",
            "Collect a real diverse checkerboard set, verify lens fit and native raw 1O.",
        ),
        ReadinessStage(
            "rig", "3  Two-projector Windows layout",
            "CONFIGURED_NOT_VERIFIED" if len(displays) >= 2 else
            "OPERATOR_MAPPING_REQUIRED",
            "Check Extended displays and physically identify left/right after camera QA.",
        ),
        ReadinessStage(
            "capture", "4  Gray-code capture setup",
            "CONFIGURED_NOT_VERIFIED" if capture_configured else "INPUT_REQUIRED",
            "Choose capture directory, content/projector sizes and confirm each physical projector.",
        ),
        ReadinessStage(
            "corners", "5  Camera/content correspondence",
            "CONFIGURED_NOT_VERIFIED" if corners_configured else "INPUT_REQUIRED",
            "Set four actual camera-space corners and four content-space corners.",
        ),
        ReadinessStage(
            "calibration", "6  Warp mesh calibration",
            "SOFTWARE_RESULT_PRESENT_NOT_VERIFIED" if mesh_present else
            "CALIBRATION_REQUIRED",
            "Run validated calibration on captured images; inspect coverage and geometry.",
        ),
        ReadinessStage(
            "blend", "7  Multi-projector seam and blend",
            "OFFLINE_TOOLS_AVAILABLE_NOT_VERIFIED",
            "Use offline overlap/seam, black level and color-balance checks; "
            "verify physically after projector power-on.",
        ),
        ReadinessStage(
            "export", "8  Clone project export",
            "OFFLINE_EXPORT_ELIGIBLE_NOT_VERIFIED" if mesh_present else
            "CALIBRATION_REQUIRED",
            "Export independent clone JSON/PNG only after reviewing the mesh; "
            "native VIOSO 7 SPS parity is not established.",
        ),
    )
    return out


def human_checklist(project):
    """Deterministic operator-readable status text, no private values."""
    return "\n\n".join(
        f"{s.title}\n  {s.status}\n  {s.next_action}"
        for s in software_readiness(project)
    )
