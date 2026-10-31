import os

import pytest

from vclone.gui_model import Session, SessionError
from vclone.project import Project


def test_new_session_is_clean_and_untitled():
    s = Session()
    assert s.project.name == "untitled" and not s.dirty and s.path is None


def test_save_load_and_dirty(tmp_path):
    s = Session()
    s.rename("demo")
    assert s.dirty
    s.save(tmp_path / "p.json")
    assert not s.dirty and s.path == tmp_path / "p.json"
    t = Session()
    t.open(tmp_path / "p.json")
    assert t.project.name == "demo" and not t.dirty


def test_save_without_path_fails():
    with pytest.raises(SessionError):
        Session().save()


def test_open_bad_file(tmp_path):
    (tmp_path / "bad.json").write_text("{nope")
    with pytest.raises(SessionError):
        Session().open(tmp_path / "bad.json")
    with pytest.raises(SessionError):
        Session().open(tmp_path / "missing.json")


def test_step_availability_reports_unimplemented():
    s = Session()
    avail = dict(s.steps())
    assert avail["Calibrate"] is True and avail["Export"] is True
    assert avail["Design"] is False


def test_run_step_errors_are_reported_not_faked():
    s = Session()
    with pytest.raises(SessionError, match="missing"):
        s.run("Calibrate")
    with pytest.raises(SessionError, match="not implemented"):
        s.run("Design")
    assert s.project.steps_done == [] and "Calibrate" not in s.log[-1]


def test_log_records_actions():
    s = Session()
    s.rename("x")
    assert any("x" in line for line in s.log)


def test_qt_window_smoke():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from vclone.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(Session(Project("smoke")))
    assert "smoke" in w.windowTitle()
    assert {b.text() for b in w.step_buttons} >= {"Calibrate", "Export", "Design"}
    assert not w.step_buttons[[b.text() for b in w.step_buttons].index("Design")].isEnabled()
    w.close()
