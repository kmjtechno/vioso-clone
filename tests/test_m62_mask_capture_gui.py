"""M62 real mask-backed capture UI tests, all synthetic and offline."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from vclone.gui_model import Session


def app():
    return QApplication.instance() or QApplication([])


def test_projector_mask_stays_opt_in_and_is_offline_verified(tmp_path, monkeypatch):
    app()
    from vclone.capture_dialog import CaptureDialog
    source = tmp_path / "safe-mask.png"
    assert cv2.imwrite(str(source), np.full((48, 64), 255, np.uint8))
    d = CaptureDialog()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a: warnings.append(True))
    try:
        d.output.setText(str(tmp_path / "new-capture"))
        d.pw.setValue(64)
        d.ph.setValue(48)
        d.cw.setValue(64)
        d.ch.setValue(48)
        d.confirm.setChecked(True)
        assert d.selected_projector_mask() is None
        assert d.result() != QDialog.DialogCode.Accepted
        d.use_projector_mask.setChecked(True)
        d._validate_and_accept()
        assert warnings and d.result() != QDialog.DialogCode.Accepted
        d._projector_mask_path = str(source)
        d._validate_and_accept()
        assert d.result() == QDialog.DialogCode.Accepted
        assert d.selected_projector_mask() == str(source)
        assert not (tmp_path / "new-capture").exists()
    finally:
        d.close()


def test_projector_mask_wrong_dimensions_refused_before_hardware(tmp_path, monkeypatch):
    app()
    from vclone.capture_dialog import CaptureDialog
    source = tmp_path / "wrong.png"
    assert cv2.imwrite(str(source), np.full((96, 96), 255, np.uint8))
    d = CaptureDialog()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a: warnings.append(True))
    try:
        d.output.setText(str(tmp_path / "new-capture"))
        d.pw.setValue(64)
        d.ph.setValue(48)
        d.confirm.setChecked(True)
        d.use_projector_mask.setChecked(True)
        d._projector_mask_path = str(source)
        d._validate_and_accept()
        assert d.result() != QDialog.DialogCode.Accepted
        assert warnings
    finally:
        d.close()


def test_gui_session_forwards_opt_in_mask_without_camera_or_display(tmp_path, monkeypatch):
    from vclone import capture
    import vclone.gui_model as model
    session = Session()
    directory = tmp_path / "new-capture"
    options = {}
    class Receipt:
        pattern_pairs = 12
    def fake_capture(*args, **kwargs):
        options.update(kwargs)
        return Receipt()
    monkeypatch.setattr(capture, "capture_opencv", fake_capture)
    monkeypatch.setattr(session, "configure_scan", lambda *_args: None)
    session.capture_camera_scan(
        str(directory), [64, 48], [64, 48], 0, 640, 0,
        confirmed=True, projector_mask_path="safe-mask.png")
    assert options["projector_mask_path"] == "safe-mask.png"
    assert options["confirmed"] is True
    assert not directory.exists()


def test_private_mask_backend_errors_are_sanitized(tmp_path, monkeypatch):
    from vclone import capture
    session = Session()
    monkeypatch.setattr(capture, "capture_opencv",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            ValueError("C:/private owner-mask path /token=secret")))
    with pytest.raises(Exception) as caught:
        session.capture_camera_scan(
            str(tmp_path / "new-capture"), [64, 48], [64, 48], 0, 640, 0,
            confirmed=True, projector_mask_path="secret-path.png")
    assert "secret" not in str(caught.value)
