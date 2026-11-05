"""M61 offline mesh editing engine: real project modifications and safety gates."""
from copy import deepcopy
import math

import pytest

from vclone.gui_model import Session, SessionError
from vclone.project import Project


def _mesh():
    return [
        [[0.0, 0.0], [32.0, 0.0], [63.0, 0.0]],
        [[0.0, 32.0], [32.0, 32.0], [63.0, 32.0]],
        [[0.0, 63.0], [32.0, 63.0], [63.0, 63.0]],
    ]


def _session(mesh=None):
    project = Project(scan={"content_size": [64, 64]},
                      result={"mesh": _mesh() if mesh is None else deepcopy(mesh),
                              "coverage": 1.0},
                      steps_done=["Calibrate", "Export"])
    return Session(project)


def test_selected_node_edit_updates_actual_mesh_coverage_and_invalidates_export():
    s = _session()
    modified = deepcopy(s.project.result["mesh"])
    modified[1][1] = [34.0, 31.0]
    count = s.apply_manual_mesh(modified)
    assert count == 1
    assert s.dirty
    assert s.project.result["mesh"][1][1] == [34.0, 31.0]
    assert s.project.result["manual_edit_nodes"] == 1
    assert 0 <= s.project.result["coverage"] <= 1
    assert "Edit" in s.project.steps_done
    assert "Export" not in s.project.steps_done
    assert all("hardware optical acceptance NOT_VERIFIED" in x
               for x in s.log[-1:])


def test_no_op_never_marks_project_dirty_or_drops_export():
    s = _session()
    proposal = deepcopy(s.project.result["mesh"])
    assert s.apply_manual_mesh(proposal) == 0
    assert not s.dirty
    assert "Export" in s.project.steps_done


@pytest.mark.parametrize("mutator", [
    lambda m: m.pop(),
    lambda m: m[0].pop(),
    lambda m: m[1].__setitem__(1, [200.0, 32.0]),
    lambda m: m[1].__setitem__(1, [float("nan"), 30.0]),
    lambda m: m[1].__setitem__(1, [True, 30.0]),
    lambda m: m[1].__setitem__(1, [1.0]),
])
def test_invalid_mesh_refused_atomically(mutator):
    s = _session()
    prior = deepcopy(s.project.result)
    original_steps = list(s.project.steps_done)
    proposal = deepcopy(prior["mesh"])
    mutator(proposal)
    with pytest.raises(SessionError):
        s.apply_manual_mesh(proposal)
    assert s.project.result == prior
    assert s.project.steps_done == original_steps
    assert s.dirty is False


def test_unobserved_mesh_points_cannot_be_fabricated_or_deleted():
    mesh = _mesh()
    mesh[0][0] = [None, None]
    s = _session(mesh)
    candidate = deepcopy(mesh)
    candidate[0][0] = [1.0, 1.0]
    with pytest.raises(SessionError, match="unobserved"):
        s.apply_manual_mesh(candidate)
    assert s.project.result["mesh"][0][0] == [None, None]


def test_multiple_edits_and_second_round_are_bounded_from_current_mesh():
    s = _session()
    proposed = deepcopy(s.project.result["mesh"])
    proposed[1][1] = [36.0, 36.0]
    proposed[0][1] = [33.0, 0.0]
    assert s.apply_manual_mesh(proposed) == 2
    further = deepcopy(s.project.result["mesh"])
    further[1][1] = [37.0, 35.0]
    assert s.apply_manual_mesh(further) == 1
    assert s.project.result["manual_edit_nodes"] == 3


def test_unconfigured_calibration_cannot_be_edited():
    s = Session(Project())
    with pytest.raises(SessionError):
        s.apply_manual_mesh(_mesh())
