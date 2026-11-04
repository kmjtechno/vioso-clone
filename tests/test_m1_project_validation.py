import cv2
import numpy as np
import pytest

from vclone import calib, cmdline, project

PW, PH = 64, 48


@pytest.fixture(scope="module")
def capdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("caps")
    pats, invs = calib.graycode_patterns(PW, PH)
    for i, (p, n) in enumerate(zip(pats, invs)):
        cv2.imwrite(str(d / f"p{i:02d}.png"), np.where(p > 127, 200, 10).astype(np.uint8))
        cv2.imwrite(str(d / f"n{i:02d}.png"), np.where(n > 127, 200, 10).astype(np.uint8))
    return d


def _proj(capdir, **over):
    sc = dict(dir=str(capdir), proj_size=[PW, PH], content_size=[640, 480], nodes=[5, 4],
              cam_corners=[[0, 0], [63, 0], [63, 47], [0, 47]],
              content_corners=[[0, 0], [639, 0], [639, 479], [0, 479]])
    sc.update(over)
    return project.Project("t", scan=sc)


def _calibrated(capdir):
    p = _proj(capdir)
    project.run_step(p, "Calibrate")
    return p


def test_good_calibration_still_works(capdir):
    assert _calibrated(capdir).result["coverage"] > 0.5


@pytest.mark.parametrize("over", [
    {"proj_size": [0, 48]}, {"proj_size": "ab"}, {"proj_size": [64]}, {"content_size": [-1, 5]},
    {"cam_corners": [[0, 0], [1, 0], [1, 1]]},
    {"cam_corners": [[0, 0], [1, 1], [2, 2], [3, 3]]},
    {"cam_corners": [[0, 0], [1, 0], [1, 1], [float("nan"), 1]]},
])
def test_bad_scan_values_become_invalid_input_not_a_crash(capdir, over):
    with pytest.raises(project.InvalidInput):
        project.run_step(_proj(capdir, **over), "Calibrate")


def test_cmdline_maps_bad_scan_to_exit_4(capdir, tmp_path):
    f = tmp_path / "p.json"
    _proj(capdir, proj_size=[0, 48]).save(f)
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Calibrate"'])) == 4


def test_failed_step_does_not_record_itself_as_done(capdir):
    p = _proj(capdir, content_size=[-1, 5])
    with pytest.raises(project.InvalidInput):
        project.run_step(p, "Calibrate")
    assert p.steps_done == [] and p.result == {}


@pytest.mark.parametrize("edit", [
    {"node": [1, 1], "dx": float("nan"), "dy": 0},
    {"node": [1, 1], "dx": 0, "dy": float("inf")},
    {"node": [True, 1], "dx": 1, "dy": 1},
    {"node": [1, False], "dx": 1, "dy": 1},
    {"node": [1, 1], "dx": True, "dy": 1},
])
def test_bad_edits_are_rejected_and_mesh_untouched(capdir, edit):
    p = _calibrated(capdir)
    before = p.result["mesh"]
    p.scan["edits"] = [edit]
    with pytest.raises(project.InvalidInput):
        project.run_step(p, "Edit")
    assert p.result["mesh"] == before and "edits_applied" not in p.result


def test_valid_edit_still_applies(capdir):
    p = _calibrated(capdir)
    x0, y0 = p.result["mesh"][1][1]
    p.scan["edits"] = [{"node": [1, 1], "dx": 2.5, "dy": -1}]
    project.run_step(p, "Edit")
    assert p.result["mesh"][1][1] == [x0 + 2.5, y0 - 1] and p.result["edits_applied"] == 1


@pytest.mark.parametrize("g", [True, False, float("nan"), float("inf"), "2.2", None, 0.4, 4.1])
def test_blend_gamma_rejects_bool_and_nonfinite(capdir, g):
    p = _calibrated(capdir)
    p.scan["blend_gamma"] = g
    with pytest.raises(project.InvalidInput):
        project.run_step(p, "Edit MRD")
