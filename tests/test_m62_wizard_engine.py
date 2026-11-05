"""M62: real guided calibration engine, synthetic camera/projector only.

No real camera, GUI, monitor, network or owner data is touched.
"""
from copy import deepcopy
import os

import cv2
import numpy as np
import pytest

from vclone.capture import capture_sequence
from vclone.project import Project
from vclone.wizard_engine import (
    WizardSolveError, capture_fingerprint, inspect_capture, project_signature,
    solve_detached,
)


@pytest.fixture
def prepared(tmp_path):
    folder = tmp_path / "real-engine-synthetic-capture"
    projected = [None]

    def show(pattern):
        projected[0] = pattern.copy()

    def grab():
        return projected[0].copy()

    capture_sequence(64, 48, folder, show, grab)
    project = Project(
        name="projector-A",
        scan={
            "dir": str(folder), "proj_size": [64, 48],
            "content_size": [64, 48],
            "cam_corners": [[0., 0.], [63., 0.], [63., 47.], [0., 47.]],
            "content_corners": [[0., 0.], [63., 0.], [63., 47.], [0., 47.]],
            "nodes": [9, 7],
        })
    return folder, project


def _bytes(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_real_capture_check_reads_all_patterns_without_hardware(prepared):
    folder, project = prepared
    before = _bytes(folder)
    receipt = inspect_capture(project)
    assert receipt["software_capture_quality"] == "PASS"
    assert receipt["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert receipt["decoded_valid_fraction"] == 1.0
    assert receipt["min_pair_reliable_fraction"] == 1.0
    assert receipt["capture_fingerprint"] == capture_fingerprint(project.scan)
    assert _bytes(folder) == before


def test_detached_solver_runs_real_decode_and_warp_without_mutating_owner(prepared):
    folder, project = prepared
    before = _bytes(folder)
    signature = project_signature(project)
    receipt = solve_detached(project)
    assert receipt["original_project_signature"] == signature
    assert receipt["software_capture_quality"] == "PASS"
    assert receipt["result"]["mesh"]
    assert 0 < receipt["coverage"] <= 1
    assert "Calibrate" in receipt["steps_done"]
    assert project.result == {}
    assert project.steps_done == []
    assert project_signature(project) == signature
    assert _bytes(folder) == before


def test_changed_capture_invalidates_quality_receipt(prepared):
    folder, project = prepared
    first = capture_fingerprint(project.scan)
    file = folder / "p00.png"
    os.utime(file, ns=(file.stat().st_atime_ns, file.stat().st_mtime_ns + 2000000000))
    assert capture_fingerprint(project.scan) != first


def test_low_contrast_refused_and_project_not_mutated(prepared):
    folder, project = prepared
    for file in folder.glob("*.png"):
        assert cv2.imwrite(str(file), np.full((48, 64), 127, np.uint8))
    original = deepcopy(project)
    with pytest.raises(WizardSolveError, match="WIZARD_CAPTURE_QUALITY_FAILED"):
        solve_detached(project)
    assert project == original


def test_invalidated_missing_corners_refused_before_solve(prepared):
    _, project = prepared
    project.scan.pop("cam_corners")
    with pytest.raises(WizardSolveError, match="WIZARD_CORNERS_OR_SCAN_REQUIRED"):
        solve_detached(project)


def test_fisheye_corners_must_be_measured_in_rectified_space(prepared):
    _, project = prepared
    project.scan["fisheye_profile"] = "lens.json"
    with pytest.raises(WizardSolveError, match="WIZARD_RECTIFIED_CORNERS_REQUIRED"):
        solve_detached(project)


def test_manifest_or_png_symlink_not_followed(prepared, tmp_path):
    folder, project = prepared
    target = tmp_path / "outside.png"
    source = folder / "p00.png"
    target.write_bytes(source.read_bytes())
    source.unlink()
    try:
        source.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported")
    with pytest.raises(WizardSolveError, match="WIZARD_CAPTURE_INCOMPLETE"):
        capture_fingerprint(project.scan)


def test_changing_capture_during_screening_fails_closed(prepared, monkeypatch):
    folder, project = prepared
    from vclone import wizard_engine as engine
    real_check = engine.check_capture

    def changed(*args, **kw):
        value = real_check(*args, **kw)
        png = folder / "n00.png"
        os.utime(png, ns=(png.stat().st_atime_ns, png.stat().st_mtime_ns + 2000000000))
        return value

    monkeypatch.setattr(engine, "check_capture", changed)
    with pytest.raises(WizardSolveError, match="WIZARD_CAPTURE_CHANGED"):
        engine.inspect_capture(project)
