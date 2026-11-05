"""M44: GUI Gray-code capture may use one selected private M33 camera source.

No real camera, projector, LAN stream, credentials or image files are accessed
by these tests except synthetic local images under pytest's own tmp_path.
"""
import json
import os

import numpy as np
import pytest

from vclone import camera_sources, capture
from vclone.gui_model import Session, SessionError


SECRET = "M44_LOCAL_ONLY_PASSWORD_NEVER_EMIT"
RTSP = "rtsp://test:" + SECRET + "@192.0.2.154:554/raw-fisheye"


def private_profile(tmp_path):
    target = tmp_path / "owner-private-camera.json"
    target.write_text(json.dumps({
        "schema": camera_sources.SCHEMA, "type": "rtsp",
        "source": RTSP, "backend": "ffmpeg",
    }), encoding="utf-8")
    return target


def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_profile_selection_is_offline_and_retains_explicit_capture_consent(tmp_path, monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog, QFileDialog
    from vclone.capture_dialog import CaptureDialog

    path = private_profile(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(camera_sources.cv2, "VideoCapture",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AssertionError("no camera must open in capture dialog")))
    monkeypatch.setattr(capture.cv2, "namedWindow",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AssertionError("no projector window before consent")))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_a, **_k: (str(path), ""))
    dlg = CaptureDialog({})
    try:
        dlg.output.setText(str(tmp_path / "fresh-capture"))
        assert not dlg.ok_button.isEnabled()
        assert not dlg.use_profile.isChecked()
        assert dlg.camera.isEnabled()
        assert not dlg.profile_button.isEnabled()
        assert dlg.selected_camera_profile() is None
        dlg.use_profile.setChecked(True)
        assert not dlg.camera.isEnabled()
        assert dlg.profile_button.isEnabled()
        dlg.profile_button.click()
        assert dlg.selected_camera_profile() == str(path)
        visible = dlg.profile_label.text() + dlg.profile_button.text()
        assert all(secret not in visible for secret in (RTSP, SECRET, str(path)))
        assert not dlg.ok_button.isEnabled()
        dlg.confirm.setChecked(True)
        assert dlg.ok_button.isEnabled()
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.values()[-1] is True  # preserve old GUI capture positional API
        assert path.read_bytes() == before
    finally:
        dlg.close()


def test_gui_bad_profile_is_refused_without_hardware_or_credential_leak(tmp_path, monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog, QMessageBox
    from vclone.capture_dialog import CaptureDialog

    path = tmp_path / "private.json"
    path.write_text(json.dumps({
        "schema": "bad", "type": RTSP, "source": SECRET,
        "backend": "ffmpeg",
    }), encoding="utf-8")
    messages = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: messages.append(_args[2]))
    monkeypatch.setattr(camera_sources.cv2, "VideoCapture",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AssertionError("invalid source opened camera")))
    dlg = CaptureDialog({})
    try:
        dlg.output.setText(str(tmp_path / "new-dir"))
        dlg.use_profile.setChecked(True)
        dlg._camera_profile_path = str(path)
        dlg.confirm.setChecked(True)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert "offline validation" in messages[-1]
        assert all(x not in repr(messages) for x in (RTSP, SECRET, str(path)))
        assert not (tmp_path / "new-dir").exists()
    finally:
        dlg.close()


def test_private_profile_disabled_uses_legacy_usb_index(tmp_path):
    qt_app()
    from vclone.capture_dialog import CaptureDialog

    dlg = CaptureDialog({})
    try:
        dlg._camera_profile_path = str(tmp_path / "not-selected.json")
        assert dlg.selected_camera_profile() is None
        dlg.use_profile.setChecked(True)
        assert dlg.selected_camera_profile() is not None
        dlg.use_profile.setChecked(False)
        assert dlg.camera.isEnabled()
        assert dlg.selected_camera_profile() is None
    finally:
        dlg.close()


def test_gui_session_routes_profile_to_existing_opencv_pipeline_without_leak(tmp_path, monkeypatch):
    path = private_profile(tmp_path)
    logged = []
    original = path.read_bytes()
    def fake_capture(w, h, output_dir, **kw):
        logged.append(kw)
        assert kw["camera_profile_path"] == str(path)
        assert kw["confirmed"] is True
        return capture.capture_sequence(
            w, h, output_dir, lambda _frame: None,
            lambda: np.full((6, 8), 110, dtype=np.uint8),
            camera_source_kind="rtsp")

    monkeypatch.setattr(capture, "capture_opencv", fake_capture)
    s = Session()
    dest = tmp_path / "new-rtsp-scan"
    result = s.capture_camera_scan(
        dest, [8, 6], [16, 12], 0, 1920, 0,
        confirmed=True, camera_profile_path=str(path))
    assert result.hardware_acceptance == "NOT_VERIFIED"
    assert logged and logged[0]["camera_profile_path"] == str(path)
    manifest = (dest / "capture_manifest.json").read_text()
    assert json.loads(manifest)["camera_source_type"] == "rtsp"
    assert s.project.scan["dir"] == str(dest)
    assert path.read_bytes() == original
    output = manifest + repr(s.log) + repr(s.project.scan)
    assert all(x not in output for x in (RTSP, SECRET, str(path)))
    assert not any("camera source" in x.lower() for x in s.project.scan)


def test_private_profile_capture_error_scrubs_backend_uri_and_path(tmp_path, monkeypatch):
    path = private_profile(tmp_path)
    def fail(*_args, **_kw):
        raise RuntimeError("OpenCV backend failed while opening " + RTSP + " in " + str(path))
    monkeypatch.setattr(capture, "capture_opencv", fail)
    s = Session()
    dest = tmp_path / "new"
    with pytest.raises(SessionError, match="private camera source") as exc:
        s.capture_camera_scan(
            dest, [8, 6], [16, 12], 0, 1920, 0,
            confirmed=True, camera_profile_path=str(path))
    assert all(x not in str(exc.value) for x in (RTSP, SECRET, str(path)))
    assert not dest.exists() and not s.dirty and not s.log


def test_no_consent_refuses_before_private_profile_or_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "capture_opencv",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            AssertionError("private source accessed without approval")))
    s = Session()
    with pytest.raises(SessionError, match="confirmation"):
        s.capture_camera_scan(
            tmp_path / "new", [8, 6], [16, 12], 0, 1920, 0,
            confirmed=False, camera_profile_path=str(tmp_path / "secret.json"))
    assert not s.log and not s.dirty


def test_main_window_passes_selected_profile_only_after_dialog_acceptance(tmp_path, monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog
    from vclone import gui

    path = private_profile(tmp_path)
    session = gui.Session()
    seen = []
    monkeypatch.setattr(session, "capture_camera_scan",
                        lambda *a: seen.append(a))
    class FakeDialog:
        def __init__(self, *_a, **_kw):
            pass
        def exec(self):
            return QDialog.DialogCode.Accepted
        def values(self):
            return (str(tmp_path / "new"), [8, 6], [16, 12],
                    0, 1920, 0, 250, 2, True)
        def selected_camera_profile(self):
            return str(path)
    monkeypatch.setattr(gui, "CaptureDialog", FakeDialog)
    window = gui.MainWindow(session)
    try:
        window.capture_camera()
        assert len(seen) == 1
        assert seen[0][-2:] == (True, str(path))
        assert not session.dirty
    finally:
        window.close()


def test_main_window_cancel_never_starts_capture(tmp_path, monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog
    from vclone import gui

    s = gui.Session()
    monkeypatch.setattr(s, "capture_camera_scan",
                        lambda *_args: (_ for _ in ()).throw(
                            AssertionError("cancelled dialog accessed hardware")))
    class CancelDialog:
        def __init__(self, *_a, **_kw):
            pass
        def exec(self):
            return QDialog.DialogCode.Rejected
        def values(self):
            raise AssertionError("cancelled dialog collected capture args")
    monkeypatch.setattr(gui, "CaptureDialog", CancelDialog)
    w = gui.MainWindow(s)
    try:
        w.capture_camera()
    finally:
        w.close()
