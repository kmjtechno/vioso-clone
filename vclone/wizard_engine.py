"""M62 independent guided calibration: strict read-only quality + detached warp solve.

The wizard calls this bounded CPU-only engine from a QThread. Never opens
cameras, starts projector output, writes owner files, or changes a live
Session until the GUI checks the exact source project signature.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import stat

from .capture import pattern_count
from .capture_check import check_capture
from .project import Project, run_step


class WizardSolveError(ValueError):
    """Public fixed-stage refusal; private capture paths must not be displayed."""


def project_signature(project):
    """Fingerprint all project settings before launching a detached solve."""
    if not isinstance(project, Project):
        raise WizardSolveError("WIZARD_INVALID_PROJECT")
    payload = json.dumps(
        asdict(project), sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload) > 32 * 1024 * 1024:
        raise WizardSolveError("WIZARD_PROJECT_TOO_LARGE")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _capture_root(scan):
    if not isinstance(scan, dict):
        raise WizardSolveError("WIZARD_SCAN_NOT_CONFIGURED")
    raw = scan.get("dir")
    if not isinstance(raw, str) or not raw:
        raise WizardSolveError("WIZARD_CAPTURE_REQUIRED")
    folder = Path(raw)
    if folder.is_symlink() or not folder.is_dir():
        raise WizardSolveError("WIZARD_CAPTURE_REQUIRED")
    return folder


def capture_fingerprint(scan):
    """Metadata snapshot of only the bounded required capture/manifest files.

    The full M25 parser independently validates file contents; this snapshot
    detects ordinary changes to captures between quality and warp solve.
    """
    folder = _capture_root(scan)
    dims = scan.get("proj_size")
    if (not isinstance(dims, (list, tuple)) or len(dims) != 2
            or any(type(v) is not int for v in dims)
            or not 2 <= dims[0] <= 1920 or not 2 <= dims[1] <= 1080):
        raise WizardSolveError("WIZARD_PROJECTOR_SIZE_REQUIRED")
    names = ["capture_manifest.json"]
    for i in range(pattern_count(*dims)):
        names.extend((f"p{i:02d}.png", f"n{i:02d}.png"))
    for key, suffix in (("camera_mask", ".png"), ("fisheye_profile", ".json")):
        opt = scan.get(key)
        if opt is not None:
            if (not isinstance(opt, str) or not opt
                    or Path(opt).name != opt or "/" in opt or "\\" in opt
                    or not opt.lower().endswith(suffix)):
                raise WizardSolveError("WIZARD_CAPTURE_PROFILE_REFUSED")
            names.append(opt)
    digest = hashlib.sha256()
    digest.update(json.dumps(dims).encode("ascii"))
    for name in names:
        file = folder / name
        if file.is_symlink() or not file.is_file():
            raise WizardSolveError("WIZARD_CAPTURE_INCOMPLETE")
        info = file.stat()
        if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128 * 1024 * 1024):
            raise WizardSolveError("WIZARD_CAPTURE_INCOMPLETE")
        digest.update(name.encode("ascii", "surrogateescape"))
        digest.update(str(info.st_size).encode("ascii"))
        digest.update(str(info.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _validated_options(scan):
    folder = _capture_root(scan)
    opts = {}
    for key, suffix, argument in (
        ("camera_mask", ".png", "camera_mask"),
        ("fisheye_profile", ".json", "fisheye_profile"),
    ):
        name = scan.get(key)
        if name is not None:
            if (not isinstance(name, str) or not name or Path(name).name != name
                    or "/" in name or "\\" in name
                    or not name.lower().endswith(suffix)):
                raise WizardSolveError("WIZARD_CAPTURE_PROFILE_REFUSED")
            file = folder / name
            if file.is_symlink() or not file.is_file():
                raise WizardSolveError("WIZARD_CAPTURE_PROFILE_REFUSED")
            opts[argument] = str(file)
    return opts


def inspect_capture(project):
    """Run real M25 Gray-code screening, never certify physical optics."""
    if not isinstance(project, Project):
        raise WizardSolveError("WIZARD_INVALID_PROJECT")
    scan = project.scan
    previous = capture_fingerprint(scan)
    try:
        report = check_capture(
            str(_capture_root(scan)), **_validated_options(scan))
    except Exception:
        # Native errors can contain private paths and camera data. Only fixed
        # public diagnostic codes may cross the worker/Qt signal boundary.
        raise WizardSolveError("WIZARD_CAPTURE_QUALITY_FAILED") from None
    if capture_fingerprint(scan) != previous:
        raise WizardSolveError("WIZARD_CAPTURE_CHANGED")
    if (report.get("software_capture_quality") != "PASS"
            or report.get("projector_size") != list(scan.get("proj_size", []))
            or report.get("hardware_acceptance") != "NOT_VERIFIED"):
        raise WizardSolveError("WIZARD_CAPTURE_MISMATCH")
    return {
        "software_capture_quality": "PASS",
        "pattern_pairs_checked": report["pattern_pairs_checked"],
        "decoded_valid_fraction": report["decoded_valid_fraction"],
        "min_pair_reliable_fraction": report["min_pair_reliable_fraction"],
        "projector_axis_span_fraction": list(
            report["projector_axis_span_fraction"]),
        "capture_fingerprint": previous,
        "hardware_optical_acceptance": "NOT_VERIFIED",
    }


def solve_detached(project):
    """Quality-check then calibrate an isolated Project; commit happens in Qt.

    No version-specific vendor code or proprietary format is used. A normal
    capture file change before/during solve causes failure instead of a
    stale UI PASS. Inputs remain unmodified.
    """
    if not isinstance(project, Project):
        raise WizardSolveError("WIZARD_INVALID_PROJECT")
    before = project_signature(project)
    frozen = deepcopy(project)
    scan = frozen.scan
    for key in ("dir", "proj_size", "content_size", "cam_corners",
                "content_corners"):
        if key not in scan:
            raise WizardSolveError("WIZARD_CORNERS_OR_SCAN_REQUIRED")
    receipt = inspect_capture(frozen)
    try:
        run_step(frozen, "Calibrate")
    except Exception:
        raise WizardSolveError("WIZARD_WARP_SOLVE_FAILED") from None
    if capture_fingerprint(scan) != receipt["capture_fingerprint"]:
        raise WizardSolveError("WIZARD_CAPTURE_CHANGED")
    mesh = frozen.result.get("mesh")
    coverage = frozen.result.get("coverage")
    if (not isinstance(mesh, list) or not mesh
            or type(coverage) not in (int, float)
            or not 0 < coverage <= 1):
        raise WizardSolveError("WIZARD_WARP_RESULT_INVALID")
    return {
        "original_project_signature": before,
        "result": deepcopy(frozen.result),
        "steps_done": list(frozen.steps_done),
        "software_capture_quality": "PASS",
        "decoded_valid_fraction": receipt["decoded_valid_fraction"],
        "capture_fingerprint": receipt["capture_fingerprint"],
        "coverage": float(coverage),
        "hardware_optical_acceptance": "NOT_VERIFIED",
    }
