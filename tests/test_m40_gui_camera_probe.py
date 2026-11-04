"""M40 operator-controlled camera-only GUI probe without projection or URI leaks."""
import json
import os

import pytest

from vclone import camera_frame_probe as camera_probe


def _profile(tmp_path):
    secret = "P520_PRIVATE_RTSP_PASS"
    url = "rtsp://operator:" + secret + "@192.0.2.150:554/local"
    path = tmp_path / "private-camera-source.json"
    path.write_text(json.dumps({
        "schema": "kmj.camera.source.v1", "type": "rtsp",
        "source": url, "backend": "ffmpeg",
    }), encoding="utf-8")
    return path, secret, url


def _report(exposure="FRAME_DATA_PRESENT"):
    return {
        "schema": "kmj.camera.frame-probe.v1",
        "camera_connection": "OPENED_AND_FRAMES_READ",
        "camera_size": [1280, 720],
        "frames_observed": 6,
        "exposure_screening": exposure,
        "projector_operation": "NONE",
        "hardware_optical_acceptance": "NOT_VERIFIED",
    }


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, value=None):
        for slot in self.slots:
            if value is None:
                slot()
            else:
                slot(value)


class _FakeWorker:
    created = []
    report = _report()
    failure = None

    def __init__(self, path, parent=None):
        self.source_path = path
        self.report_ready = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.deleted = False
        self.created.append(self)

    def isRunning(self):
        return False

    def start(self):
        if self.failure:
            self.failed.emit(self.failure)
        else:
            self.report_ready.emit(self.report)
        self.finished.emit()

    def deleteLater(self):
        self.deleted = True


def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_never_opens_camera_without_explicit_yes(tmp_path, monkeypatch):
    _qt()
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    import vclone.gui as gui

    path, secret, uri = _profile(tmp_path)
    session = gui.Session()
    window = gui.MainWindow(session)
    before = path.read_bytes()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    monkeypatch.setattr(gui, "CameraProbeWorker",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("worker constructed without explicit Yes")))
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: messages.append(a[2]))
    try:
        actions = [a.text() for a in window.menuBar().actions()[1].menu().actions()]
        assert "Probe selected camera (explicit consent)..." in actions
        window.probe_selected_camera()
        assert window._camera_probe_worker is None
        assert path.read_bytes() == before
        assert session.dirty is False
        assert uri not in repr(session.log)
        assert secret not in repr(session.log)
        assert not messages
    finally:
        window.close()


def test_gui_explicit_yes_uses_one_async_worker_and_safe_receipt(tmp_path, monkeypatch):
    _qt()
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    import vclone.gui as gui

    path, secret, uri = _profile(tmp_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _FakeWorker.created = []
    _FakeWorker.report = _report()
    _FakeWorker.failure = None
    monkeypatch.setattr(gui, "CameraProbeWorker", _FakeWorker)
    messages = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: messages.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: messages.append(("warning", a[2])))
    session = gui.Session()
    window = gui.MainWindow(session)
    before = path.read_bytes()
    try:
        window.probe_selected_camera()
        assert len(_FakeWorker.created) == 1
        assert _FakeWorker.created[0].deleted
        assert window._camera_probe_worker is None
        assert messages[-1][0] == "info"
        assert "OPENED_AND_FRAMES_READ" in messages[-1][1]
        assert "Physical optical calibration: NOT VERIFIED" in messages[-1][1]
        assert "Projector operation: NONE" in messages[-1][1]
        assert path.read_bytes() == before
        assert not session.dirty
        assert all(x not in (repr(messages) + repr(session.log))
                   for x in (secret, uri, str(path), "192.0.2.150"))
    finally:
        window.close()


def test_gui_camera_failure_redacts_native_secret(tmp_path, monkeypatch):
    _qt()
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    import vclone.gui as gui

    path, secret, uri = _profile(tmp_path)
    _FakeWorker.created = []
    _FakeWorker.failure = "OpenCV exception: " + uri
    monkeypatch.setattr(gui, "CameraProbeWorker", _FakeWorker)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: messages.append(a[2]))
    session = gui.Session()
    window = gui.MainWindow(session)
    try:
        window.probe_selected_camera()
        assert messages and "could not be probed safely" in messages[-1]
        assert all(x not in (repr(messages) + repr(session.log))
                   for x in (secret, uri, str(path)))
        assert window._camera_probe_worker is None
    finally:
        _FakeWorker.failure = None
        window.close()


def test_real_worker_calls_bounded_engine_only_and_scrubs_backend_errors(tmp_path, monkeypatch):
    _qt()
    import vclone.gui as gui

    path, secret, uri = _profile(tmp_path)
    invocations = []
    def fake_probe(profile_path, *, confirmed, frames, warmup):
        invocations.append((profile_path, confirmed, frames, warmup))
        return _report()
    monkeypatch.setattr(camera_probe, "camera_frame_probe", fake_probe)
    w = gui.CameraProbeWorker(path)
    results, failures = [], []
    w.report_ready.connect(results.append)
    w.failed.connect(failures.append)
    w.run()  # run synchronously to test worker code without physical camera
    assert invocations == [(str(path), True, 6, 1)]
    assert results == [_report()] and not failures

    def explode(*_a, **_kw):
        raise RuntimeError("decoder opened " + uri)
    monkeypatch.setattr(camera_probe, "camera_frame_probe", explode)
    w.run()
    assert len(failures) == 1 and "failed" in failures[0]
    assert secret not in failures[0] and uri not in failures[0]


def test_close_is_blocked_while_camera_thread_active(monkeypatch):
    _qt()
    import vclone.gui as gui
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox

    window = gui.MainWindow()
    info = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: info.append(a[2]))
    class Active:
        def isRunning(self):
            return True
    window._camera_probe_worker = Active()
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert info and "running" in info[0]
    window._camera_probe_worker = None
    window.close()
