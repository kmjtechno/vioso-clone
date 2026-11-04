"""M10 real Qt offscreen corner-picker and calibration menu tests."""
import os

import cv2
import numpy as np
import pytest

from vclone.gui_model import Session
from vclone.project import Project


def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_corner_picker_clicks_undo_clear_and_accept(tmp_path):
    app = qt_app()
    from PySide6.QtWidgets import QDialog
    from vclone.corner_editor import CornerPicker

    path = tmp_path / "p00.png"
    assert cv2.imwrite(str(path), np.full((80, 100), 180, np.uint8))
    dlg = CornerPicker(path)
    assert dlg.image_size == (100, 80)
    assert not dlg.ok_button.isEnabled()
    dlg.add_point(11, 10)
    dlg.add_point(87, 13)
    assert dlg.instructions.text().startswith("2/4")
    dlg.undo()
    assert len(dlg.points) == 1
    dlg.add_point(87, 13)
    dlg.add_point(84, 64)
    dlg.add_point(8, 60)
    assert dlg.ok_button.isEnabled()
    dlg._confirm()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.points == [[11.0, 10.0], [87.0, 13.0],
                          [84.0, 64.0], [8.0, 60.0]]
    dlg.close()


def test_corner_picker_clear_is_non_destructive(tmp_path):
    app = qt_app()
    from vclone.corner_editor import CornerPicker

    path = tmp_path / "p00.png"
    assert cv2.imwrite(str(path), np.zeros((80, 100), np.uint8))
    dlg = CornerPicker(path)
    dlg.add_point(11, 10)
    dlg.add_point(87, 13)
    dlg.clear()
    assert dlg.points == []
    assert dlg.instructions.text().startswith("0/4")
    assert not dlg.ok_button.isEnabled()
    dlg.reject()
    assert dlg.points == []


def test_main_window_has_calibration_setup_and_corner_selection():
    app = qt_app()
    from vclone.gui import MainWindow
    window = MainWindow(Session(Project("editor")))
    menus = [a.menu() for a in window.menuBar().actions() if a.menu()]
    calibration = [m for m in menus if m.title() == "&Calibration"]
    assert len(calibration) == 1
    titles = [a.text() for a in calibration[0].actions()]
    assert any("Setup capture" in title for title in titles)
    assert any("Select camera corners" in title for title in titles)
    window.close()


def test_dialog_rejects_out_of_bounds_image_size(tmp_path):
    app = qt_app()
    from vclone.corner_editor import CornerPicker
    path = tmp_path / "too-large.png"
    assert cv2.imwrite(str(path), np.zeros((2200, 25), dtype=np.uint8))
    with pytest.raises(ValueError, match="bounds"):
        CornerPicker(path)


def test_scan_setup_dialog_returns_dimensions(tmp_path):
    app = qt_app()
    from vclone.corner_editor import ScanSetupDialog
    d = ScanSetupDialog({"dir": str(tmp_path),
                         "proj_size": [640, 480],
                         "content_size": [1920, 1080]})
    assert d.values() == (str(tmp_path), [640, 480], [1920, 1080])
    d.projector_width.setValue(1280)
    assert d.values()[1] == [1280, 480]
    d.reject()
