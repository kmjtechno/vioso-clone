"""M33 modular camera sources: USB, RTSP/ONVIF, replay and SDK contracts.

All camera streams are mocks: no LAN scan, media server, lens or projector.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from vclone import camera_sources as cs, capture, capture_check, optical_roi
from vclone.__main__ import main


def profile(kind, source, backend="auto"):
    return {"schema": cs.SCHEMA, "type": kind, "source": source,
            "backend": backend}


class FakeStream:
    def __init__(self):
        self.released = False
        self.frames = 0
    def isOpened(self):
        return True
    def read(self):
        self.frames += 1
        return True, np.full((6, 8, 3), self.frames % 255, dtype=np.uint8)
    def grab(self):
        return True
    def release(self):
        self.released = True


@pytest.mark.parametrize("kind,source,backend", [
    ("usb", 0, "auto"),
    ("usb", 2, "dshow"),
    ("usb", 5, "msmf"),
    ("rtsp", "rtsp://camera.local:554/stream", "auto"),
    ("rtsps", "rtsps://camera.example.org:322/stream", "ffmpeg"),
    ("onvif_rtsp", "rtsp://cam.example.net:554/onvif-stream", "ffmpeg"),
    ("http_mjpeg", "http://localhost:8080/video.mjpg", "ffmpeg"),
    ("https_mjpeg", "https://camera.example.org/video", "auto"),
    ("sdk", "installed_genicam_camera0", "auto"),
])
def test_cross_vendor_source_profile_validation(kind, source, backend):
    data = cs.validate_profile(profile(kind, source, backend))
    assert data["type"] == kind
    status = cs.profile_status(data)
    assert status["camera_connection"] == "NOT_TESTED"
    assert status["no_network_or_camera_access"] is True
    assert source not in json.dumps(status)


@pytest.mark.parametrize("bad", [
    profile("usb", True),
    profile("usb", 16),
    profile("usb", -1),
    profile("usb", [1]),
    profile("onvif", "onvif://192.0.2.2"),
    profile("rtsp", "http://camera.local/stream"),
    profile("rtsps", "rtsp://camera.local/stream"),
    profile("http_mjpeg", "https://camera.local/stream"),
    profile("rtsp", "rtsp://bad host/stream"),
    profile("rtsp", "rtsp://camera.local:65536/stream"),
    profile("rtsp", "rtsp://camera.local:0/stream"),
    profile("rtsp", "rtsp://camera.local/stream#fragment"),
    profile("usb", 0, "ffmpeg"),
    profile("sdk", "this is a Python module: __import__", "auto"),
    profile("sdk", "trusted", "dshow"),
    {"schema": cs.SCHEMA, "type": "usb", "source": 0, "backend": "auto", "secret": "oops"},
])
def test_invalid_source_profiles_fail_without_camera_access(bad):
    with pytest.raises(cs.CameraSourceError):
        cs.validate_profile(bad)


def test_offline_profile_check_redacts_authenticated_rtsp_uri(tmp_path, capsys, monkeypatch):
    secret = "TEST_PRIVATE_PASS_SHOULD_NEVER_PRINT"
    uri = f"rtsp://owner:{secret}@192.0.2.42:554/private-feed"
    path = tmp_path / "private.json"
    path.write_text(json.dumps(profile("rtsp", uri)), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(cs.cv2, "VideoCapture",
                        lambda *_args: (_ for _ in ()).throw(
                            AssertionError("camera opened during profile check")))
    assert main(["camera-profile-check", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["camera_type"] == "rtsp"
    assert result["camera_connection"] == "NOT_TESTED"
    assert secret not in json.dumps(result)
    assert "192.0.2.42" not in json.dumps(result)
    assert path.read_bytes() == before


def test_invalid_json_and_symlink_profile_rejected(tmp_path):
    actual = tmp_path / "owner.json"
    actual.write_text('{"schema":NaN}', encoding="utf-8")
    with pytest.raises(cs.CameraSourceError):
        cs.read_profile(actual)
    actual.write_bytes(b"X" * (cs.MAX_PROFILE_BYTES + 1))
    with pytest.raises(cs.CameraSourceError, match="16 KiB"):
        cs.read_profile(actual)
    shortcut = tmp_path / "alias.json"
    try:
        shortcut.symlink_to(actual)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(cs.CameraSourceError, match="non-symlink"):
        cs.read_profile(shortcut)


def test_network_stream_uses_timeout_capable_backend_and_releases(monkeypatch):
    calls = []
    stream = FakeStream()
    monkeypatch.setattr(cs.cv2, "VideoCapture",
                        lambda *args: (calls.append(args), stream)[1])
    p = profile("rtsp", "rtsp://cam.example.org/live", "auto")
    opened = cs.open_camera(p)
    assert opened is stream
    assert calls[0][0].startswith("rtsp://")
    assert calls[0][1] == cv2.CAP_FFMPEG
    opts = calls[0][2]
    assert opts[opts.index(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC) + 1] == 4000
    assert opts[opts.index(cv2.CAP_PROP_READ_TIMEOUT_MSEC) + 1] == 4000
    opened.release()
    assert stream.released


def test_usb_source_uses_standard_capture_index_without_sdk(monkeypatch):
    calls = []
    monkeypatch.setattr(cs.cv2, "VideoCapture",
                        lambda *args: (calls.append(args), FakeStream())[1])
    opened = cs.open_camera(profile("usb", 1))
    assert calls == [(1,)]
    opened.release()


def test_sdk_extension_requires_explicit_trusted_registered_factory():
    p = profile("sdk", "my_camera_adapter")
    with pytest.raises(cs.CameraSourceError, match="not installed"):
        cs.open_camera(p)
    device = FakeStream()
    assert cs.open_camera(p, sdk_adapters={"my_camera_adapter": lambda: device}) is device


def test_replay_rejects_symlink_and_relative_path(tmp_path, monkeypatch):
    movie = tmp_path / "demo.mp4"
    movie.write_bytes(b"test video placeholder")
    p = profile("video_file", str(movie))
    monkeypatch.setattr(cs.cv2, "VideoCapture", lambda *_args: FakeStream())
    device = cs.open_camera(p)
    device.release()
    with pytest.raises(cs.CameraSourceError):
        cs.validate_profile(profile("video_file", "relative/path.mp4"))
    link = tmp_path / "shortcut.mp4"
    try:
        link.symlink_to(movie)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(cs.CameraSourceError):
        cs.validate_profile(profile("video_file", str(link)))


def test_capture_with_private_network_profile_never_writes_credentials(tmp_path, monkeypatch):
    uri = "rtsp://owner:HIDDEN_PWD@127.0.0.1:8554/stream"
    private = tmp_path / "private-camera.json"
    private.write_text(json.dumps(profile("rtsp", uri)), encoding="utf-8")
    original = private.read_bytes()
    opened = []
    device = FakeStream()
    monkeypatch.setattr(capture, "open_camera",
                        lambda p: (opened.append(p["type"]), device)[1])
    monkeypatch.setattr(cv2, "namedWindow", lambda *_: None)
    monkeypatch.setattr(cv2, "moveWindow", lambda *_: None)
    monkeypatch.setattr(cv2, "setWindowProperty", lambda *_: None)
    monkeypatch.setattr(cv2, "imshow", lambda *_: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_: -1)
    monkeypatch.setattr(cv2, "destroyWindow", lambda *_: None)
    out = tmp_path / "capture"
    result = capture.capture_opencv(
        8, 6, out, camera_index=0, projector_x=0, projector_y=0,
        confirmed=True, camera_profile_path=private)
    assert result.hardware_acceptance == "NOT_VERIFIED"
    receipt = (out / "capture_manifest.json").read_text(encoding="utf-8")
    assert json.loads(receipt)["camera_source_type"] == "rtsp"
    assert "HIDDEN_PWD" not in receipt and "127.0.0.1" not in receipt
    assert opened == ["rtsp"] and device.released
    assert private.read_bytes() == original


def test_confirmation_refused_before_reading_private_profile(tmp_path, monkeypatch):
    fake = tmp_path / "owner-camera.json"
    fake.write_text("not a valid profile")
    opened = []
    monkeypatch.setattr(capture, "read_profile", lambda *_: opened.append("read"))
    with pytest.raises(capture.CaptureError, match="confirmation"):
        capture.capture_opencv(8, 6, tmp_path / "new",
                               camera_index=0, projector_x=0, projector_y=0,
                               confirmed=False, camera_profile_path=fake)
    assert opened == []
    assert not (tmp_path / "new").exists()


def test_native_2560_square_camera_frame_within_pixel_budget():
    assert capture._grayscale(np.zeros((2560, 2560), dtype=np.uint8)).shape == (2560, 2560)
    assert capture_check._integer_pair(
        [2560, 2560], "camera", maximum=4096) == (2560, 2560)
    assert capture.MAX_CAMERA_PIXELS >= 2560 * 2560
    with pytest.raises(capture.CaptureError):
        capture._grayscale(np.zeros((4096, 4096), dtype=np.uint8))
