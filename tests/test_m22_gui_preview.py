"""M22 calibrated CPU preview GUI integration; no camera/projector hardware."""
import os

import cv2
import numpy as np
import pytest

from vclone.gui_model import Session, SessionError
from vclone.project import Project


def _calibrated_session():
    mesh = [[[0.0, 0.0], [15.0, 0.0]], [[0.0, 11.0], [15.0, 11.0]]]
    p = Project("demo", scan={"proj_size": [16, 12]}, result={"mesh": mesh})
    return Session(p)


def _source(tmp_path):
    path = tmp_path / "content.png"
    image = np.zeros((12, 16, 3), dtype=np.uint8)
    image[:, :, 0] = 30
    image[:, :, 1] = 120
    image[:, :, 2] = 210
    assert cv2.imwrite(str(path), image)
    return path


def test_software_preview_renders_without_projector_and_does_not_dirty(tmp_path):
    s = _calibrated_session()
    path = _source(tmp_path)
    original = path.read_bytes()
    frame = s.preview_content(path)
    assert frame.shape == (12, 16, 3) and frame.dtype == np.uint8
    assert frame[5, 7].tolist() == [30, 120, 210]
    assert path.read_bytes() == original
    assert s.dirty is False and s.path is None
    assert any("NOT_VERIFIED" in msg for msg in s.log)


def test_export_new_png_then_refuse_overwrite(tmp_path):
    s = _calibrated_session()
    frame = s.preview_content(_source(tmp_path))
    dest = tmp_path / "preview.png"
    assert s.save_preview_png(frame, dest) == dest
    assert cv2.imread(str(dest)).shape == (12, 16, 3)
    original = dest.read_bytes()
    with pytest.raises(SessionError, match="new regular path"):
        s.save_preview_png(frame, dest)
    assert dest.read_bytes() == original
    assert s.dirty is False


def test_refuse_preview_when_calibration_absent(tmp_path):
    s = Session(Project())
    with pytest.raises(SessionError, match="Calibrate first"):
        s.preview_content(_source(tmp_path))
    assert not s.dirty


def test_refuse_missing_preview_file_without_mutating_project(tmp_path):
    s = _calibrated_session()
    before = dict(s.project.result)
    with pytest.raises(SessionError, match="regular non-symlink"):
        s.preview_content(tmp_path / "missing.png")
    assert s.project.result == before and not s.dirty


def test_reject_new_preview_wrong_extension_and_invalid_frame(tmp_path):
    s = _calibrated_session()
    frame = np.zeros((12, 16, 3), dtype=np.uint8)
    with pytest.raises(SessionError, match="png"):
        s.save_preview_png(frame, tmp_path / "preview.jpg")
    with pytest.raises(SessionError, match="uint8 BGR"):
        s.save_preview_png(frame.astype(np.float32), tmp_path / "preview.png")
    assert not (tmp_path / "preview.png").exists()


def test_qt_preview_and_save_ui_smoke(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog
    from vclone.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    s = _calibrated_session()
    window = MainWindow(s)
    assert not window.preview_export_button.isEnabled()
    src = _source(tmp_path)
    dest = tmp_path / "ui-preview.png"
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(src), "PNG"))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(dest), "PNG"))
    window.preview_content()
    assert window.preview_export_button.isEnabled()
    assert window.preview_label.pixmap() is not None
    window.save_preview_png()
    assert dest.is_file()
    assert s.dirty is False
    window.close()


def test_switching_project_invalidates_old_preview(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog
    from vclone.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    old = _calibrated_session()
    window = MainWindow(old)
    src = _source(tmp_path)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(src), "PNG"))
    window.preview_content()
    assert window.preview_export_button.isEnabled()
    next_project = tmp_path / "another.json"
    Project("other").save(next_project)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(next_project), "JSON"))
    window.open_project()
    assert old.project.name == "other"
    assert not window.preview_export_button.isEnabled()
    assert window._preview_frame is None
    assert "CPU preview" in window.preview_label.text()
    window.close()
