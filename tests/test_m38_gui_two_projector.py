"""M38 GUI seam preflight: read-only model and offscreen UI dispatch."""
import json
import os

import numpy as np
import pytest

from vclone.gui_model import Session, SessionError
from vclone.project import Project


def _project(name, left, right):
    project = Project(name)
    project.content_space = "rig-shared-canvas"
    project.scan = {"proj_size": [96, 80], "content_size": [160, 80]}
    x, y = np.meshgrid(np.linspace(left, right, 6), np.linspace(0, 79, 4))
    project.result = {"mesh": np.stack([x, y], axis=-1).tolist()}
    return project


def test_session_seam_check_read_only_and_no_dirty_state(tmp_path):
    first = _project("left", 0, 100)
    second = _project("right", 70, 159)
    right_path = tmp_path / "second.json"
    second.save(right_path)
    before = right_path.read_bytes()
    state = json.dumps(first.result, sort_keys=True)
    session = Session(first)
    report = session.compare_projector_seam(right_path)
    assert report["software_seam_gate"] == "PASS_SOFTWARE_GEOMETRY_ONLY"
    assert report["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert report["camera_operation"] == report["projector_operation"] == "NONE"
    assert right_path.read_bytes() == before
    assert json.dumps(first.result, sort_keys=True) == state
    assert session.path is None and session.dirty is False
    assert "NOT_VERIFIED" in session.log[-1]


def test_session_does_not_claim_pass_for_duplicate_coverage(tmp_path):
    second = _project("duplicate", 0, 159)
    second_path = tmp_path / "second.json"
    second.save(second_path)
    session = Session(_project("first", 0, 159))
    session.dirty = True
    report = session.compare_projector_seam(second_path)
    assert report["software_seam_gate"] == "BLOCKED_EXCESSIVE_OR_DUPLICATE_OVERLAP"
    assert session.dirty is True
    assert "BLOCKED" in session.log[-1]


def test_session_refuses_same_file_and_malformed_other_project(tmp_path):
    first = _project("first", 0, 100)
    path = tmp_path / "first.json"
    first.save(path)
    session = Session()
    session.open(path)
    with pytest.raises(SessionError, match="different second-projector"):
        session.compare_projector_seam(path)
    assert session.path == path and session.dirty is False
    assert session.log == [f"opened {path}"]
    bad_path = tmp_path / "bad.json"
    bad_path.write_text('{"scan": "invalid"}', encoding="utf-8")
    before = bad_path.read_bytes()
    with pytest.raises(SessionError, match="refused"):
        session.compare_projector_seam(bad_path)
    assert bad_path.read_bytes() == before
    assert session.path == path and session.dirty is False


def test_session_rejects_mismatched_content_space_without_mutation(tmp_path):
    left = _project("left", 0, 100)
    right = _project("right", 70, 159)
    right.content_space = "unrelated-projection-canvas"
    path = tmp_path / "other.json"
    right.save(path)
    before = path.read_bytes()
    session = Session(left)
    with pytest.raises(SessionError, match="space identifiers do not match"):
        session.compare_projector_seam(path)
    assert path.read_bytes() == before
    assert session.project is left
    assert session.dirty is False
    assert session.log == []


def test_gui_seam_action_offscreen_displays_explicit_software_limit(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from vclone.gui import MainWindow

    path = tmp_path / "right.json"
    _project("right", 70, 159).save(path)
    app = QApplication.instance() or QApplication([])
    session = Session(_project("left", 0, 100))
    window = MainWindow(session)
    actions = [a.text() for a in window.menuBar().actions()[1].menu().actions()]
    assert "Compare two-projector seam (offline)..." in actions

    messages = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: (str(path), "Project (*.json)"))
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **kw: messages.append(("pass", a[2])))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **kw: messages.append(("warning", a[2])))
    try:
        window.compare_two_projectors()
        assert len(messages) == 1
        assert messages[0][0] == "pass"
        assert "PASS_SOFTWARE_GEOMETRY_ONLY" in messages[0][1]
        assert "Physical optical acceptance: NOT VERIFIED" in messages[0][1]
        assert "\n" in messages[0][1]
        assert not session.dirty

        _project("duplicate", 0, 100).save(tmp_path / "duplicate.json")
        monkeypatch.setattr(QFileDialog, "getOpenFileName",
                            lambda *a, **kw: (str(tmp_path / "duplicate.json"), ""))
        window.compare_two_projectors()
        assert messages[-1][0] == "warning"
        assert "BLOCKED_EXCESSIVE_OR_DUPLICATE_OVERLAP" in messages[-1][1]
    finally:
        window.close()
