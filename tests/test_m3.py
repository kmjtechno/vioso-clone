import json

import pytest

from vclone import cmdline, project


def calibrated(tmp_path):
    mesh = [[[0.0, 0.0], [10.0, 0.0]], [[0.0, 10.0], [None, None]]]
    return project.Project("p", content_space="cs", displays=[{"name": "d"}],
                           scan={"dir": str(tmp_path), "content_size": [20, 20]},
                           result={"mesh": mesh, "coverage": 0.5})


def test_design_requires_space_and_displays():
    with pytest.raises(project.MissingInput):
        project.run_step(project.Project("x"), "Design")
    p = project.run_step(project.Project("x", content_space="cs", displays=[{"name": "a"}]), "Design")
    assert p.result["design"] == {"content_space": "cs", "displays": 1} and p.steps_done == ["Design"]


def test_design_does_not_discard_calibration(tmp_path):
    p = calibrated(tmp_path)
    project.run_step(p, "Design")
    assert p.result["mesh"] and "design" in p.result


def test_edit_moves_node_and_rejects_bad_input(tmp_path):
    p = calibrated(tmp_path)
    p.scan["edits"] = [{"node": [0, 1], "dx": 2.5, "dy": -1.0}]
    project.run_step(p, "Edit")
    assert p.result["mesh"][0][1] == [12.5, -1.0] and p.result["edits_applied"] == 1
    for bad in ([{"node": [5, 0], "dx": 1, "dy": 1}], [{"node": [1, 1], "dx": 1, "dy": 1}], [{"dx": 1}]):
        q = calibrated(tmp_path)
        q.scan["edits"] = bad
        with pytest.raises(project.InvalidInput):
            project.run_step(q, "Edit")
        assert q.result["mesh"][0][1] == [10.0, 0.0]  # failed edit leaves mesh untouched
    with pytest.raises(project.MissingInput):
        project.run_step(project.Project("n"), "Edit")


def test_edit_mrd_sets_blend_gamma(tmp_path):
    p = calibrated(tmp_path)
    p.scan["blend_gamma"] = 1.8
    project.run_step(p, "Edit MRD")
    assert p.result["blend_gamma"] == 1.8
    p.scan["blend_gamma"] = 0
    with pytest.raises(project.InvalidInput):
        project.run_step(p, "Edit MRD")


def test_configure_merges_settings():
    p = project.Project("c")
    p.scan["configure"] = {"nodes": [9, 5]}
    project.run_step(p, "Configure")
    assert p.scan["nodes"] == [9, 5]
    p.scan["configure"] = {"dir": 3}
    with pytest.raises(project.InvalidInput):
        project.run_step(p, "Configure")


def test_recover_export_writes_from_saved_result(tmp_path):
    p = calibrated(tmp_path)
    project.run_step(p, "RecoverExport")
    assert json.loads((tmp_path / "warp.json").read_text())["coverage"] == 0.5
    with pytest.raises(project.MissingInput):
        project.run_step(project.Project("n"), "RecoverExport")


def test_licensing_steps_are_deliberately_unsupported():
    for s in ("Activate", "Deactivate"):
        with pytest.raises(project.NotImplementedStep, match="licens"):
            project.run_step(project.Project("n"), s)


def test_cmdline_exit_codes(tmp_path):
    p = calibrated(tmp_path)
    p.scan["edits"] = [{"node": [9, 9], "dx": 1, "dy": 1}]
    f = tmp_path / "p.json"
    p.save(f)
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Edit"'])) == 4
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Activate"'])) == 2
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Edit MRD"'])) == 0
