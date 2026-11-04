"""M37 two-projector seam validation without opening displays or cameras."""
import json

import numpy as np
import pytest

from vclone.__main__ import main
from vclone.project import Project
from vclone.two_projector_check import TwoProjectorError, check_two_projectors


def calibrated(name, x0, x1, *, w=160, h=80):
    p = Project(name)
    p.scan = {"proj_size": [96, 80], "content_size": [w, h]}
    mx, my = np.meshgrid(np.linspace(x0, x1, 6),
                         np.linspace(0, h - 1, 4))
    p.result = {"mesh": np.stack([mx, my], axis=-1).tolist()}
    return p


def test_partially_overlapping_two_projector_seam_passes_software_only():
    report = check_two_projectors([
        calibrated("left", 0, 100), calibrated("right", 70, 159)])
    assert report["schema"] == "kmj.two-projector.seam-check.v1"
    assert report["software_seam_gate"] == "PASS_SOFTWARE_GEOMETRY_ONLY"
    assert report["read_only"] is True
    assert report["projector_operation"] == "NONE"
    assert report["camera_operation"] == "NONE"
    assert report["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert report["projection_synchronization"] == "NOT_VERIFIED"
    assert report["projector_identity_mapping"] == "NOT_VERIFIED"
    assert report["native_vioso_sps_compatible"] is False
    assert report["content_size"] == [160, 80]
    assert report["projector_sizes"] == [[96, 80], [96, 80]]
    assert 0.20 < report["overlap_fraction_of_smaller_projector"] < 0.50
    assert report["uncovered_fraction"] < 0.01
    assert report["content_bounds_xywh"][0][0] == 0


def test_disjoint_projectors_refused_even_if_both_have_coverage():
    report = check_two_projectors([
        calibrated("left", 0, 60), calibrated("right", 100, 159)])
    assert report["software_seam_gate"] == "BLOCKED_INSUFFICIENT_SEAM_OVERLAP"
    assert report["overlap_fraction_of_content"] == 0


def test_nearly_identical_or_mirrored_meshes_refused():
    report = check_two_projectors([
        calibrated("left", 0, 159), calibrated("right", 0, 159)])
    assert report["software_seam_gate"] == "BLOCKED_EXCESSIVE_OR_DUPLICATE_OVERLAP"
    assert report["overlap_fraction_of_smaller_projector"] == 1.0
    assert report["union_coverage_fraction"] == 1.0


def test_low_union_coverage_blocked_even_when_overlap_is_healthy():
    report = check_two_projectors([
        calibrated("left", 0, 20), calibrated("right", 10, 30)])
    assert 0.20 < report["overlap_fraction_of_smaller_projector"] < 0.80
    assert report["software_seam_gate"] == "BLOCKED_LOW_CONTENT_COVERAGE"


@pytest.mark.parametrize("thresholds", [
    {"min_overlap": float("nan")},
    {"min_overlap": True},
    {"min_overlap": -0.1},
    {"max_overlap": float("inf")},
    {"min_overlap": 0},
    {"max_overlap": 1},
    {"min_overlap": 0.8, "max_overlap": 0.2},
    {"min_union_coverage": 0},
    {"min_union_coverage": 1.1},
])
def test_invalid_thresholds_fail_closed_before_mesh_access(thresholds):
    with pytest.raises(TwoProjectorError, match="overlap|coverage"):
        check_two_projectors([calibrated("a", 0, 100),
                              calibrated("b", 70, 159)], **thresholds)


def test_insufficient_distinct_projects_refused():
    p = calibrated("single", 0, 100)
    for projects in ([], [p], [p, p], [p, p, p], [p, None]):
        with pytest.raises(TwoProjectorError, match="two distinct"):
            check_two_projectors(projects)


def test_mismatched_content_or_invalid_mesh_blocks_without_output():
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    p2.scan["content_size"] = [200, 80]
    with pytest.raises(TwoProjectorError, match="one content coordinate"):
        check_two_projectors([p1, p2])
    p2.scan["content_size"] = [160, 80]
    p2.result["mesh"] = [[[None, None]] * 5] * 4
    with pytest.raises(TwoProjectorError, match="mesh"):
        check_two_projectors([p1, p2])


@pytest.mark.parametrize("bad_size", [
    [0, 80], [True, 80], [4096, 4096], [32, 80],
    [4097, 80], ["160", 80], [160, 80, 1],
])
def test_invalid_content_dimensions_fail_before_rasterization(bad_size):
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    p1.scan["content_size"] = bad_size
    with pytest.raises(TwoProjectorError, match="content"):
        check_two_projectors([p1, p2])


def test_cli_read_only_pass_and_source_json_bytes_untouched(tmp_path, capsys):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    calibrated("left", 0, 100).save(left)
    calibrated("right", 70, 159).save(right)
    first, second = left.read_bytes(), right.read_bytes()
    assert main(["two-projector-check", str(left), str(right)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["software_seam_gate"] == "PASS_SOFTWARE_GEOMETRY_ONLY"
    assert report["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert left.read_bytes() == first and right.read_bytes() == second
    assert sorted(p.name for p in tmp_path.iterdir()) == ["left.json", "right.json"]


def test_cli_insufficient_overlap_returns_nonzero_and_still_prints_summary(tmp_path, capsys):
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    calibrated("left", 0, 60).save(left)
    calibrated("right", 100, 159).save(right)
    assert main(["two-projector-check", str(left), str(right)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["software_seam_gate"] == "BLOCKED_INSUFFICIENT_SEAM_OVERLAP"
    assert "camera_source" not in report


def test_cli_duplicate_path_and_symlink_cannot_be_used_as_second_project(tmp_path, capsys):
    left = tmp_path / "left.json"
    calibrated("left", 0, 100).save(left)
    before = left.read_bytes()
    assert main(["two-projector-check", str(left), str(left)]) == 2
    assert not capsys.readouterr().out
    alias = tmp_path / "alias.json"
    try:
        alias.symlink_to(left)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    assert main(["two-projector-check", str(left), str(alias)]) == 2
    assert not capsys.readouterr().out
    assert left.read_bytes() == before



def test_named_content_space_mismatch_refused_without_projectors():
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    p1.content_space = "content-canvas-a"
    p2.content_space = "content-canvas-b"
    with pytest.raises(TwoProjectorError, match="space identifiers"):
        check_two_projectors([p1, p2])
    p2.content_space = "content-canvas-a"
    assert check_two_projectors([p1, p2])["content_space_identity"] == "MATCHING"


def test_missing_named_content_space_cannot_claim_identity_verified():
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    p1.content_space = "canvas"
    p2.content_space = ""
    report = check_two_projectors([p1, p2])
    assert report["content_space_identity"] == "NOT_VERIFIED"


def test_oversized_mesh_grid_refused_before_memory_heavy_rasterization():
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    # This source-level test deliberately uses a >65k-node grid; no devices
    # or image output is touched.
    p2.result["mesh"] = np.zeros((257, 256, 2), dtype=np.float64).tolist()
    with pytest.raises(TwoProjectorError, match="65536"):
        check_two_projectors([p1, p2])


def test_scan_metadata_must_be_mapping():
    p1 = calibrated("a", 0, 100)
    p2 = calibrated("b", 70, 159)
    p2.scan = None
    with pytest.raises(TwoProjectorError, match="metadata"):
        check_two_projectors([p1, p2])
