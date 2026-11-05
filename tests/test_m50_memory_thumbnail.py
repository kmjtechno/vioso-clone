"""M50 explicit, memory-only thumbnail for owner ONVIF fisheye QA.

All frames are generated with NumPy mocks. No hardware, network, or image file.
"""
import base64
import hashlib
import os
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from vclone import camera_frame_probe, onvif_client


PASSWORD = "M50_PRIVATE_IN_MEMORY_NOT_FOR_LOGS"
CAMERA = {
    "schema": "kmj.camera.source.v1",
    "type": "onvif",
    "source": {
        "host": "192.168.52.11", "port": 80, "scheme": "http",
        "username": "read-only", "password": PASSWORD,
    },
    "backend": "ffmpeg",
}


def qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class DummyCamera:
    def __init__(self):
        self.released = False
        self.reads = 0
    def grab(self):
        return True
    def read(self):
        self.reads += 1
        # 256x256 synthetic circular fisheye-like image; nothing recorded.
        yy, xx = np.ogrid[:256, :256]
        radius = (xx - 128) ** 2 + (yy - 128) ** 2
        raw = np.where(radius <= 115**2, 90 + self.reads, 0).astype("uint8")
        return True, raw
    def release(self):
        self.released = True


def test_no_consent_refuses_thumbnail_before_network(monkeypatch, tmp_path):
    monkeypatch.setattr(camera_frame_probe, "open_camera",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("camera accessed without consent")))
    with pytest.raises(camera_frame_probe.CameraProbeError, match="confirm-camera"):
        camera_frame_probe.camera_frame_probe(
            CAMERA, confirmed=False, frames=6, return_preview=True)
    assert list(tmp_path.iterdir()) == []


def test_thumbnail_is_only_opt_in_and_report_never_contains_pixels(monkeypatch, tmp_path):
    devices = []
    def open_mock(*_):
        d = DummyCamera()
        devices.append(d)
        return d
    monkeypatch.setattr(camera_frame_probe, "open_camera", open_mock)
    report = camera_frame_probe.camera_frame_probe(CAMERA, confirmed=True, frames=6)
    assert type(report) is dict
    assert report["camera_size"] == [256, 256]
    assert report["projector_operation"] == "NONE"
    assert devices[-1].released
    safe, thumbnail = camera_frame_probe.camera_frame_probe(
        CAMERA, confirmed=True, frames=6, return_preview=True)
    assert isinstance(safe, dict)
    assert safe == report
    assert thumbnail.dtype == np.uint8
    assert thumbnail.ndim == 2
    assert 16 <= thumbnail.shape[0] <= 240
    assert 16 <= thumbnail.shape[1] <= 320
    assert thumbnail[thumbnail.shape[0] // 2, thumbnail.shape[1] // 2] > 0
    assert thumbnail[0, 0] == 0
    assert devices[-1].released
    assert all(x not in repr(safe) for x in (
        PASSWORD, CAMERA["source"]["host"], CAMERA["source"]["username"]))
    assert list(tmp_path.iterdir()) == []


def test_unsafe_preview_argument_refused_without_camera_open(monkeypatch):
    monkeypatch.setattr(camera_frame_probe, "open_camera",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("opened before preview argument validation")))
    for value in ("true", None, 1, [], {}):
        with pytest.raises(camera_frame_probe.CameraProbeError, match="boolean"):
            camera_frame_probe.camera_frame_probe(
                CAMERA, confirmed=True, frames=6, return_preview=value)


def test_actual_worker_emits_one_in_memory_qimage_only_when_opted_in(monkeypatch):
    qt()
    from PySide6.QtGui import QImage
    from vclone import gui
    calls = []
    def synthetic_probe(profile, *, confirmed, frames, warmup, return_preview=False):
        calls.append((confirmed, frames, warmup, return_preview))
        receipt = {"camera_connection": "OPENED_AND_FRAMES_READ",
                   "camera_size": [256, 256], "frames_observed": 6}
        if return_preview:
            return receipt, np.full((128, 128), 125, dtype=np.uint8)
        return receipt
    monkeypatch.setattr(camera_frame_probe, "camera_frame_probe", synthetic_probe)
    worker = gui.CameraProbeWorker(CAMERA)
    previews, receipts = [], []
    worker.preview_ready.connect(previews.append)
    worker.report_ready.connect(receipts.append)
    worker.run()
    assert calls == [(True, 6, 1, False)]
    assert len(receipts) == 1 and not previews
    worker.preview_enabled = True
    worker.run()
    assert calls[-1] == (True, 6, 1, True)
    assert len(previews) == 1 and isinstance(previews[0], QImage)
    assert previews[0].width() == 128 and previews[0].height() == 128
    assert len(receipts) == 2
    assert all(PASSWORD not in repr(r) for r in receipts)


def test_preview_dialog_never_enables_saved_preview_or_touch_projectors(monkeypatch):
    qt()
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QImage
    from vclone import gui

    monkeypatch.setattr(QMessageBox, "exec", lambda *_: 0)
    window = gui.MainWindow()
    try:
        before = list(window.session.log)
        grayscale = QImage(128, 128, QImage.Format.Format_Grayscale8)
        grayscale.fill(125)
        window._camera_preview_ready(grayscale)
        assert window.session.log == before
        assert not window.session.dirty
        assert window._preview_frame is None
        assert not window.preview_export_button.isEnabled()
        for invalid in [QImage(), QImage(321, 100, QImage.Format.Format_Grayscale8)]:
            window._camera_preview_ready(invalid)
        assert window.session.log == before
    finally:
        window.close()


def test_ws_security_identifiers_and_digest_match_oasis_standard():
    payload = onvif_client._soap(
        onvif_client.DEVICE + "/GetCapabilities",
        "operator", PASSWORD, "<tds:GetCapabilities/>")
    root = ET.fromstring(payload)
    ns = {
        "wsse": onvif_client.WSSE,
        "wsu": onvif_client.WSU,
    }
    token = root.find(".//wsse:UsernameToken", ns)
    assert token is not None
    password = token.find("wsse:Password", ns)
    nonce = token.find("wsse:Nonce", ns)
    created = token.find("wsu:Created", ns)
    assert password.get("Type") == (
        "http://docs.oasis-open.org/wss/2004/01/"
        "oasis-200401-wss-username-token-profile-1.0#PasswordDigest")
    assert nonce.get("EncodingType") == (
        "http://docs.oasis-open.org/wss/2004/01/"
        "oasis-200401-wss-soap-message-security-1.0#Base64Binary")
    calculated = base64.b64encode(hashlib.sha1(
        base64.b64decode(nonce.text) +
        created.text.encode("utf-8") +
        PASSWORD.encode("utf-8")).digest()).decode("ascii")
    assert password.text == calculated
    assert PASSWORD.encode() not in payload
