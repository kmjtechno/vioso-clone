"""M21 GUI capture controller tests: synthetic-only; never access real hardware."""
import numpy as np
import pytest

from vclone import capture
from vclone.gui_model import Session, SessionError


def test_never_start_hardware_without_confirmation(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("camera must not open before confirmation")
    monkeypatch.setattr(capture, "capture_opencv", forbidden)
    dest = tmp_path / "new-capture"
    s = Session()
    with pytest.raises(SessionError, match="confirmation"):
        s.capture_camera_scan(dest, [8, 6], [16, 12], 0, 1920, 0)
    assert not dest.exists() and s.project.scan == {}


def test_existing_folder_refused_before_camera(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("camera opened before safety guard")
    monkeypatch.setattr(capture, "capture_opencv", forbidden)
    dest = tmp_path / "owner"
    dest.mkdir()
    marker = dest / "owner.txt"
    marker.write_text("private", encoding="utf-8")
    s = Session()
    with pytest.raises(SessionError, match="destination"):
        s.capture_camera_scan(dest, [8, 6], [16, 12], 0, 1920, 0, confirmed=True)
    assert marker.read_text(encoding="utf-8") == "private"
    assert s.project.scan == {}


def test_successful_synthetic_capture_updates_scan_only_after_manifest(monkeypatch, tmp_path):
    called = {}
    def synthetic(width, height, output_dir, **options):
        called.update(options)
        return capture.capture_sequence(
            width, height, output_dir, lambda _: None,
            lambda: np.full((6, 8), 127, dtype=np.uint8),
        )
    monkeypatch.setattr(capture, "capture_opencv", synthetic)
    dest = tmp_path / "new-capture"
    s = Session()
    receipt = s.capture_camera_scan(
        dest, [8, 6], [16, 12], 0, 1920, 0, confirmed=True)
    assert receipt.hardware_acceptance == "NOT_VERIFIED"
    assert called["confirmed"] is True and called["camera_index"] == 0
    assert s.project.scan["dir"] == str(dest)
    assert s.project.scan["proj_size"] == [8, 6]
    assert s.project.scan["content_size"] == [16, 12]
    assert (dest / "p00.png").exists()
    assert (dest / "capture_manifest.json").exists()
    assert s.dirty
    assert any("NOT_VERIFIED" in line for line in s.log)


def test_camera_failure_does_not_update_existing_project(monkeypatch, tmp_path):
    def failure(*args, **kwargs):
        raise capture.CaptureError("camera disconnected")
    monkeypatch.setattr(capture, "capture_opencv", failure)
    s = Session()
    s.project.scan = {"dir": "owner-untouched", "proj_size": [8, 6]}
    with pytest.raises(SessionError, match="disconnected"):
        s.capture_camera_scan(
            tmp_path / "new-capture", [8, 6], [16, 12],
            0, 1920, 0, confirmed=True)
    assert s.project.scan == {"dir": "owner-untouched", "proj_size": [8, 6]}


def test_dialog_refuses_to_enable_ok_without_explicit_consent(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vclone.capture_dialog import CaptureDialog
    app = QApplication.instance() or QApplication([])
    dialog = CaptureDialog({})
    dialog.output.setText(str(tmp_path / "new-capture"))
    assert not dialog.confirm.isChecked()
    assert not dialog.ok_button.isEnabled()
    dialog.confirm.setChecked(True)
    assert dialog.ok_button.isEnabled()
    args = dialog.values()
    assert args[-1] is True and args[0] == str(tmp_path / "new-capture")
    dialog.close()
