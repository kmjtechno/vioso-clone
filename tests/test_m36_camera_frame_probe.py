"""M36 camera-only optical preflight with no projected patterns or pixel writes."""
import json

import cv2
import numpy as np
import pytest

from vclone import camera_frame_probe as probe
from vclone.__main__ import main


class FakeCapture:
    def __init__(self, frames=None, *, fail_warmup=False, fail_after=None):
        self.frames = list(frames or [])
        self.fail_warmup = fail_warmup
        self.fail_after = fail_after
        self.position = 0
        self.released = False
        self.warmups = 0

    def isOpened(self):
        return True

    def grab(self):
        self.warmups += 1
        return not self.fail_warmup

    def read(self):
        if self.fail_after is not None and self.position >= self.fail_after:
            return False, None
        image = self.frames[self.position % len(self.frames)].copy()
        self.position += 1
        return True, image

    def release(self):
        self.released = True


def _frames(count=8, *, offset=70, size=(64, 64)):
    h, w = size
    x = np.arange(w, dtype=np.uint8)[None, :]
    y = np.arange(h, dtype=np.uint8)[:, None]
    return [np.stack([
        np.broadcast_to((x + offset + i) % 255, (h, w)),
        np.broadcast_to((y + offset + i) % 255, (h, w)),
        np.broadcast_to(((x // 2 + y // 2 + offset + i) % 255), (h, w)),
    ], axis=2).astype(np.uint8) for i in range(count)]


def _profile(tmp_path, *, source_type="rtsp"):
    secret = "DO_NOT_PRINT_THIS_RTSP_TOKEN"
    uri = "rtsp://owner:" + secret + "@192.0.2.82:554/cp-plus-raw"
    data = {
        "schema": "kmj.camera.source.v1",
        "type": source_type,
        "source": 0 if source_type == "usb" else uri,
        "backend": "auto",
    }
    path = tmp_path / "private-camera-source.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, uri


def test_requires_confirmation_before_private_profile_read(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(probe, "read_profile", lambda *_: opened.append("read"))
    with pytest.raises(probe.CameraProbeError, match="confirm-camera"):
        probe.camera_frame_probe(tmp_path / "private.json")
    assert not opened


def test_camera_only_probe_returns_safe_metrics_and_releases(tmp_path, monkeypatch):
    path, uri = _profile(tmp_path)
    camera = FakeCapture(_frames())
    monkeypatch.setattr(probe, "open_camera", lambda p: camera)
    monkeypatch.setattr(cv2, "namedWindow", lambda *_: (_ for _ in ()).throw(
        AssertionError("unexpected projector window")))
    monkeypatch.setattr(cv2, "imshow", lambda *_: (_ for _ in ()).throw(
        AssertionError("unexpected projected pattern")))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = probe.camera_frame_probe(path, confirmed=True, frames=8, warmup=2)
    assert result["camera_connection"] == "OPENED_AND_FRAMES_READ"
    assert result["camera_size"] == [64, 64]
    assert result["frames_observed"] == 8
    assert result["projector_operation"] == "NONE"
    assert result["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert result["optical_calibration"] == "NOT_VERIFIED"
    assert result["exposure_screening"] == "FRAME_DATA_PRESENT"
    assert result["mean_frame_change_fraction"] > 0
    assert result["min_sharpness_laplacian_variance"] > 0
    assert camera.released is True
    assert camera.warmups == 2
    report = json.dumps(result)
    assert uri not in report
    assert "192.0.2.82" not in report
    assert "DO_NOT_PRINT_THIS_RTSP_TOKEN" not in report
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_cli_probe_outputs_json_and_never_writes_file(tmp_path, capsys, monkeypatch):
    path, uri = _profile(tmp_path, source_type="usb")
    camera = FakeCapture(_frames(6))
    monkeypatch.setattr(probe, "open_camera", lambda p: camera)
    before = path.read_bytes()
    assert main(["camera-frame-probe", str(path), "--confirm-camera",
                 "--frames", "6", "--warmup", "1"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["camera_source_type"] == "usb"
    assert report["frames_observed"] == 6
    assert report["read_only_no_capture_files"] is True
    assert camera.released
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_cli_without_confirmation_never_opens_camera(tmp_path, capsys, monkeypatch):
    path, _ = _profile(tmp_path)
    monkeypatch.setattr(probe, "open_camera", lambda *_: (_ for _ in ()).throw(
        AssertionError("must not open camera")))
    assert main(["camera-frame-probe", str(path)]) == 2
    captured = capsys.readouterr()
    assert "--confirm-camera" in captured.err
    assert not captured.out


@pytest.mark.parametrize("count,warmup", [
    (0, 0), (3, 0), (17, 0), (True, 0), (8, -1),
    (8, 7), (8, True), (8, 0.5),
])
def test_bad_bounded_settings_refused_before_device_open(
        tmp_path, monkeypatch, count, warmup):
    monkeypatch.setattr(probe, "read_profile", lambda *_: (_ for _ in ()).throw(
        AssertionError("profile should not open before settings validation")))
    with pytest.raises(probe.CameraProbeError):
        probe.camera_frame_probe(tmp_path / "private.json", confirmed=True,
                                 frames=count, warmup=warmup)


def test_read_failure_releases_camera_without_claiming_success(tmp_path, monkeypatch):
    path, _ = _profile(tmp_path)
    cam = FakeCapture(_frames(8), fail_after=2)
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    with pytest.raises(probe.CameraProbeError, match="could not be read"):
        probe.camera_frame_probe(path, confirmed=True)
    assert cam.released


def test_camera_warmup_failure_releases_camera(tmp_path, monkeypatch):
    path, _ = _profile(tmp_path)
    cam = FakeCapture(_frames(8), fail_warmup=True)
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    with pytest.raises(probe.CameraProbeError, match="warmup"):
        probe.camera_frame_probe(path, confirmed=True)
    assert cam.released


def test_resolution_change_refused_and_released(tmp_path, monkeypatch):
    path, _ = _profile(tmp_path)
    cam = FakeCapture([_frames(1)[0], _frames(1, size=(64, 80))[0]])
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    with pytest.raises(probe.CameraProbeError, match="resolution changed"):
        probe.camera_frame_probe(path, confirmed=True)
    assert cam.released


@pytest.mark.parametrize("bad_frame", [
    np.zeros((32, 32), dtype=np.uint8),
    np.zeros((64, 64), dtype=np.float32),
    np.zeros((64, 64, 2), dtype=np.uint8),
])
def test_malformed_or_tiny_camera_frame_refused(tmp_path, monkeypatch, bad_frame):
    path, _ = _profile(tmp_path)
    cam = FakeCapture([bad_frame])
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    with pytest.raises(probe.CameraProbeError):
        probe.camera_frame_probe(path, confirmed=True)
    assert cam.released


def test_dark_scene_is_screening_warning_not_false_calibration_pass(tmp_path, monkeypatch):
    path, _ = _profile(tmp_path)
    cam = FakeCapture([np.zeros((64, 64), dtype=np.uint8)])
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    result = probe.camera_frame_probe(path, confirmed=True)
    assert result["exposure_screening"] == "LOW_LIGHT_CHECK_EXPOSURE"
    assert result["mean_frame_change_fraction"] == 0
    assert result["optical_calibration"] == "NOT_VERIFIED"


def test_bright_scene_is_screening_warning_not_false_calibration_pass(tmp_path, monkeypatch):
    path, _ = _profile(tmp_path)
    cam = FakeCapture([np.full((64, 64), 255, dtype=np.uint8)])
    monkeypatch.setattr(probe, "open_camera", lambda _: cam)
    result = probe.camera_frame_probe(path, confirmed=True)
    assert result["exposure_screening"] == "HIGH_BRIGHTNESS_CHECK_EXPOSURE"
    assert result["mean_clipped_white_fraction"] == 1.0


def test_error_from_camera_adapter_never_discloses_private_uri(tmp_path, monkeypatch, capsys):
    path, uri = _profile(tmp_path)
    monkeypatch.setattr(probe, "open_camera",
                        lambda _: (_ for _ in ()).throw(RuntimeError(
                            "Cannot connect " + uri)))
    assert main(["camera-frame-probe", str(path), "--confirm-camera"]) == 2
    report = capsys.readouterr()
    assert "camera could not be opened safely" in report.err
    assert "DO_NOT_PRINT_THIS_RTSP_TOKEN" not in report.err
    assert "192.0.2.82" not in report.err
    assert not report.out
