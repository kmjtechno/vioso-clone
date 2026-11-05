"""M49: one-shot ONVIF owner GUI, explicit double consent and no secrets on disk.

All network, decoder and camera operations use mocks; no projectors ever run.
"""
import json
import os

import numpy as np
import pytest

from vclone import camera_frame_probe as probe, onvif_client as onvif


PASS = "M49_PRIVATE_PASSWORD_NOT_FOR_LOGS"
HOST = "192.168.2.90"
SRC = {"host": HOST, "port": 80, "scheme": "http",
       "username": "operator", "password": PASS}


def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def setup_dialog():
    app()
    from vclone.onvif_quick_dialog import OnvifQuickProbeDialog
    dialog = OnvifQuickProbeDialog()
    dialog.host.setText(HOST)
    dialog.username.setText("operator")
    dialog.password.setText(PASS)
    return dialog


def test_initial_dialog_never_opens_device_or_writes_profile(monkeypatch, tmp_path):
    from vclone import onvif_client
    monkeypatch.setattr(
        onvif_client, "_post",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("ONVIF accessed during dialog construction")))
    d = setup_dialog()
    try:
        assert d.profile() is None
        assert not d.confirm.isChecked()
        assert not d.ok_button.isEnabled()
        assert d.password.echoMode() == d.password.EchoMode.Password
        assert list(tmp_path.iterdir()) == []
    finally:
        d.close()


def test_offline_input_requires_explicit_consent_and_rejects_public_host(monkeypatch):
    app()
    from PySide6.QtWidgets import QMessageBox, QDialog
    d = setup_dialog()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_a, **_kw: warnings.append("generic"))
    try:
        d._validate_and_accept()
        assert d.result() != QDialog.DialogCode.Accepted
        d.host.setText("8.8.8.8")
        d.confirm.setChecked(True)
        d._validate_and_accept()
        assert d.result() != QDialog.DialogCode.Accepted
        assert warnings == ["generic"]
        assert d.profile() is None
    finally:
        d.close()


def test_in_memory_profile_from_user_not_saved_anywhere(tmp_path, monkeypatch):
    app()
    from PySide6.QtWidgets import QDialog
    d = setup_dialog()
    before = sorted(p.name for p in tmp_path.iterdir())
    try:
        d.token.setText("original-1O")
        d.confirm.setChecked(True)
        d._validate_and_accept()
        assert d.result() == QDialog.DialogCode.Accepted
        report = d.profile()
        assert report["type"] == "onvif"
        assert report["source"]["host"] == HOST
        assert report["source"]["password"] == PASS
        assert report["source"]["profile_token"] == "original-1O"
        assert d.password.text() == ""
        assert sorted(p.name for p in tmp_path.iterdir()) == before
        d.clear_transient_profile()
        assert d.profile() is None
    finally:
        d.close()


class _Signal:
    def __init__(self):
        self.listeners = []
    def connect(self, fn):
        self.listeners.append(fn)
    def emit(self, *args):
        for fn in self.listeners:
            fn(*args)


class _MockWorker:
    created = []
    def __init__(self, private_profile, parent=None):
        self._private_profile = private_profile
        self.report_ready = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.created.append(self)
    def start(self):
        self.report_ready.emit({
            "camera_connection": "OPENED_AND_FRAMES_READ",
            "camera_size": [2560, 2560],
            "frames_observed": 6,
            "exposure_screening": "FRAME_DATA_PRESENT",
        })
        self.finished.emit()
    def isRunning(self):
        return False
    def deleteLater(self):
        pass


def test_gui_no_password_file_and_no_probe_without_second_yes(monkeypatch):
    app()
    from PySide6.QtWidgets import QMessageBox, QDialog
    from vclone import gui
    class FakeDialog:
        profile_data = {"schema": "kmj.camera.source.v1",
                        "type": "onvif", "source": dict(SRC),
                        "backend": "ffmpeg"}
        def __init__(self, *_a, **_kw):
            pass
        def exec(self):
            return QDialog.DialogCode.Accepted
        def profile(self):
            return self.profile_data
        def clear_transient_profile(self):
            pass
    monkeypatch.setattr(gui, "OnvifQuickProbeDialog", FakeDialog)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_kw: QMessageBox.StandardButton.No)
    monkeypatch.setattr(gui, "CameraProbeWorker",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            AssertionError("ONVIF opened without second consent")))
    w = gui.MainWindow()
    try:
        w.probe_onvif_camera_once()
        assert w._camera_probe_worker is None
        assert PASS not in repr(w.session.log)
        assert HOST not in repr(w.session.log)
    finally:
        w.close()


def test_gui_yes_runs_one_worker_and_clears_memory_secrets(monkeypatch):
    app()
    from PySide6.QtWidgets import QMessageBox, QDialog
    from vclone import gui
    class FakeDialog:
        def __init__(self, *_a, **_kw):
            pass
        def exec(self):
            return QDialog.DialogCode.Accepted
        def profile(self):
            return {"schema": "kmj.camera.source.v1",
                    "type": "onvif", "source": dict(SRC), "backend": "ffmpeg"}
        def clear_transient_profile(self):
            pass
    monkeypatch.setattr(gui, "OnvifQuickProbeDialog", FakeDialog)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_kw: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_kw: None)
    monkeypatch.setattr(gui, "CameraProbeWorker", _MockWorker)
    _MockWorker.created = []
    window = gui.MainWindow()
    try:
        labels = [a.text() for a in window.menuBar().actions()[1].menu().actions()]
        assert "Connect ONVIF camera (no saved credentials)..." in labels
        window.probe_onvif_camera_once()
        assert len(_MockWorker.created) == 1
        assert _MockWorker.created[0]._private_profile is None
        assert window._camera_probe_worker is None
        assert window.session.dirty is False
        assert all(x not in repr(window.session.log) for x in (HOST, PASS, "operator"))
    finally:
        window.close()


def test_frame_probe_accepts_in_memory_profile_only_after_confirm(monkeypatch):
    profile = {"schema": "kmj.camera.source.v1",
               "type": "onvif", "source": dict(SRC), "backend": "ffmpeg"}
    from vclone import camera_frame_probe
    read = []
    class Camera:
        def grab(self):
            return True
        def read(self):
            read.append(True)
            return True, np.full((64, 64, 3), 120, dtype=np.uint8)
        def release(self):
            pass
    monkeypatch.setattr(camera_frame_probe, "open_camera",
                        lambda source: (read.append("open"), Camera())[1])
    with pytest.raises(probe.CameraProbeError, match="confirm-camera"):
        probe.camera_frame_probe(profile, confirmed=False, frames=6)
    assert read == []
    report = probe.camera_frame_probe(profile, confirmed=True, frames=6)
    assert read[0] == "open" and read.count(True) == 6
    assert report["camera_connection"] == "OPENED_AND_FRAMES_READ"
    assert report["projector_operation"] == "NONE"
    assert all(x not in json.dumps(report) for x in (PASS, HOST, "operator"))


def test_private_lan_onvif_transport_disables_environment_proxies(monkeypatch):
    created = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, n):
            return ('<soap:Envelope xmlns:soap="' + onvif.SOAP +
                    '"><soap:Body><ok/></soap:Body></soap:Envelope>').encode()
    class Opener:
        def open(self, request, timeout):
            assert timeout == 4
            return Response()
    def build(*handlers):
        created.extend(handlers)
        return Opener()
    monkeypatch.setattr(onvif, "build_opener", build)
    onvif._post("http://" + HOST + ":80/onvif/device_service",
                SRC, onvif.DEVICE + "/GetCapabilities",
                "<tds:GetCapabilities/>")
    from urllib.request import ProxyHandler
    proxies = [h for h in created if isinstance(h, ProxyHandler)]
    assert len(proxies) == 1 and proxies[0].proxies == {}
    assert any(isinstance(h, onvif._NoRedirect) for h in created)
