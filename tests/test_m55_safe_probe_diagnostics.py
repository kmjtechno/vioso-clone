"""M55 failure-stage regression: synthetic signals only, NO physical cameras."""
import os
import pytest

from vclone import camera_frame_probe, camera_sources, onvif_client
from vclone.camera_diagnostics import FAILURE_HINTS, SCHEMA, safe_failure

SECRET = "M55_DO_NOT_LOG_TEST_PASSWORD"
PROFILE = {
    "schema": camera_sources.SCHEMA,
    "type": "onvif",
    "source": {"host": "192.168.50.66", "port": 80,
               "scheme": "http", "username": "operator",
               "password": SECRET},
    "backend": "ffmpeg",
}


def test_all_codes_are_constant_reviewed_and_never_echo_untrusted_values():
    assert SCHEMA == "M55_CAMERA_PROBE_DIAGNOSTIC_V1"
    assert "ONVIF_AUTH_REJECTED" in FAILURE_HINTS
    assert "RTSP_DECODER_OPEN_FAILED" in FAILURE_HINTS
    assert "CAMERA_FRAME_READ_FAILED" in FAILURE_HINTS
    for supplied in (
        SECRET, "http://192.168.50.66/user:secret", None, [], {},
        "ONVIF_AUTH_REJECTED " + SECRET,
    ):
        assert safe_failure(supplied)[0] == "CAMERA_PROBE_FAILED"
    all_output = repr(FAILURE_HINTS)
    assert SECRET not in all_output and "192.168.50.66" not in all_output
    assert all(safe_failure(code)[0] == code for code in FAILURE_HINTS)
    assert safe_failure("failed: ONVIF_AUTH_REJECTED")[0] == "ONVIF_AUTH_REJECTED"


@pytest.mark.parametrize(("message", "expected"), [
    ("ONVIF selected camera rejected authentication", "ONVIF_AUTH_REJECTED"),
    ("ONVIF selected camera could not complete media request", "ONVIF_CONTROL_UNREACHABLE_OR_TLS"),
    ("no raw-square ONVIF profile; set profile_token locally", "ONVIF_PROFILE_SELECTION_FAILED"),
    ("selected ONVIF media profile not found", "ONVIF_PROFILE_SELECTION_FAILED"),
    ("ONVIF Media1 did not return an RTSP stream URI", "ONVIF_STREAM_URI_UNAVAILABLE"),
    ("http://192.168.50.66/?pass=" + SECRET, "ONVIF_NEGOTIATION_FAILED"),
    ("ONVIF SOAP envelope mismatch", "ONVIF_NEGOTIATION_FAILED"),
])
def test_onvif_resolution_failure_is_classified_without_native_details(
        monkeypatch, message, expected):
    monkeypatch.setattr(
        onvif_client, "resolve_stream_uri",
        lambda *_args: (_ for _ in ()).throw(onvif_client.OnvifError(message)))
    with pytest.raises(camera_sources.CameraSourceStageError) as captured:
        camera_sources.open_camera(PROFILE)
    assert captured.value.code == expected
    assert SECRET not in str(captured.value)
    assert "192.168" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_rtsp_decoder_failure_is_not_wrongly_classified_as_onvif_auth(monkeypatch):
    from vclone import camera_sources as cs
    class Closed:
        released = False
        def isOpened(self): return False
        def release(self): self.released = True
    closed = Closed()
    monkeypatch.setattr(
        onvif_client, "resolve_stream_uri",
        lambda *_args: "rtsp://192.168.50.66/live")
    monkeypatch.setattr(cs.cv2, "VideoCapture", lambda *args: closed)
    with pytest.raises(cs.CameraSourceStageError) as captured:
        cs.open_camera(PROFILE)
    assert captured.value.code == "RTSP_DECODER_OPEN_FAILED"
    assert closed.released


def test_camera_probe_preserves_predefined_stage_code_without_secret(monkeypatch):
    def raise_stage(_profile):
        raise camera_sources.CameraSourceStageError("ONVIF_AUTH_REJECTED")
    monkeypatch.setattr(camera_frame_probe, "open_camera", raise_stage)
    with pytest.raises(camera_frame_probe.CameraProbeError) as err:
        camera_frame_probe.camera_frame_probe(PROFILE, confirmed=True, frames=6)
    assert err.value.code == "ONVIF_AUTH_REJECTED"
    assert SECRET not in str(err.value)
    assert err.value.__cause__ is None


def test_camera_probe_invalid_source_fails_before_network(monkeypatch):
    monkeypatch.setattr(
        camera_frame_probe, "open_camera",
        lambda *_a: (_ for _ in ()).throw(AssertionError("network was touched")))
    data = dict(PROFILE, source={**PROFILE["source"], "host": "8.8.8.8"})
    with pytest.raises(camera_frame_probe.CameraProbeError) as err:
        camera_frame_probe.camera_frame_probe(data, confirmed=True, frames=6)
    assert err.value.code == "PROFILE_INVALID"


def test_camera_probe_warmup_failure_code_and_cleanup(monkeypatch):
    class BadWarmup:
        released = False
        def grab(self): return False
        def release(self): self.released = True
    cam = BadWarmup()
    monkeypatch.setattr(camera_frame_probe, "open_camera", lambda *_: cam)
    with pytest.raises(camera_frame_probe.CameraProbeError) as err:
        camera_frame_probe.camera_frame_probe(PROFILE, confirmed=True, frames=6)
    assert err.value.code == "CAMERA_WARMUP_FAILED"
    assert cam.released


def test_camera_probe_frame_read_failure_code_and_cleanup(monkeypatch):
    class BadRead:
        released = False
        def grab(self): return True
        def read(self): return False, None
        def release(self): self.released = True
    cam = BadRead()
    monkeypatch.setattr(camera_frame_probe, "open_camera", lambda *_: cam)
    with pytest.raises(camera_frame_probe.CameraProbeError) as err:
        camera_frame_probe.camera_frame_probe(PROFILE, confirmed=True, frames=6)
    assert err.value.code == "CAMERA_FRAME_READ_FAILED"
    assert cam.released


def test_error_code_allowlist_rejects_secret_shaped_code():
    wrong = camera_frame_probe.CameraProbeError(
        "safe marker", code="CAMERA_FRAME_READ_FAILED/" + SECRET)
    assert wrong.code == "CAMERA_PROBE_FAILED"


def test_dark_gui_shows_stage_and_no_native_error_or_credentials(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vclone import gui
    app = QApplication.instance() or QApplication([])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: warnings.append(_args[-1]))
    window = gui.MainWindow()
    try:
        assert "M55 camera diagnostics" in window.windowTitle()
        window._camera_probe_failed("ONVIF_AUTH_REJECTED")
        assert warnings and "ONVIF authentication" in warnings[-1]
        assert "ONVIF_AUTH_REJECTED" in warnings[-1]
        assert "No projector operation" in warnings[-1]
        assert window.camera_status_label.text() == "PROBE FAILED · NOT VERIFIED"
        assert window.session.log[-1].find("ONVIF_AUTH_REJECTED") != -1
        window._camera_probe_failed("RTSP://camera/password=" + SECRET)
        assert "CAMERA_PROBE_FAILED" in warnings[-1]
        assert SECRET not in repr(warnings)
        assert SECRET not in repr(window.session.log)
        assert "192.168" not in repr(warnings)
    finally:
        window.close()


def test_gui_worker_only_emits_reviewed_code_when_native_error_is_unsafe(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vclone import gui, camera_frame_probe as module
    app = QApplication.instance() or QApplication([])
    failures = []
    worker = gui.CameraProbeWorker(PROFILE)
    worker.failed.connect(failures.append)
    def opaque(*_args, **_kw):
        raise ValueError("rtsp://operator:" + SECRET + "@192.168.50.66")
    monkeypatch.setattr(module, "camera_frame_probe", opaque)
    worker.run()
    assert failures == ["failed: CAMERA_PROBE_FAILED"]
    assert SECRET not in repr(failures)
    worker.deleteLater()
