"""Synthetic, fail-closed tests for opt-in camera/projector capture.

These do not attest a physical projector, camera, display placement or latency.
"""
import json

import cv2
import numpy as np
import pytest

from vclone import calib, capture


def test_generated_pattern_order_matches_calibration_decoder():
    w, h = 13, 9
    pos, neg = calib.graycode_patterns(w, h)
    generated = list(capture.iter_patterns(w, h))
    assert len(generated) == 2 * len(pos) == 2 * capture.pattern_count(w, h)
    for i, (p, n) in enumerate(zip(pos, neg)):
        assert generated[2 * i][0] == f"p{i:02d}.png"
        assert generated[2 * i + 1][0] == f"n{i:02d}.png"
        np.testing.assert_array_equal(generated[2 * i][1], p)
        np.testing.assert_array_equal(generated[2 * i + 1][1], n)


def test_synthetic_capture_is_decoder_compatible(tmp_path):
    current = [None]
    def show(pattern):
        current[0] = pattern.copy()

    def grab():
        p = current[0]
        gray = np.where(p > 127, 210, 10).astype(np.uint8)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    out = tmp_path / "new-captures"
    receipt = capture.capture_sequence(8, 6, out, show, grab)
    assert receipt.image_files[0:2] == ("p00.png", "n00.png")
    assert receipt.pattern_pairs == capture.pattern_count(8, 6)
    assert len(receipt.image_files) == 2 * receipt.pattern_pairs
    assert receipt.camera_size == (8, 6)
    assert receipt.hardware_acceptance == "NOT_VERIFIED"
    manifest = json.loads((out / "capture_manifest.json").read_text())
    assert manifest["schema"] == capture.MANIFEST_SCHEMA
    assert manifest["pattern_pairs"] == receipt.pattern_pairs
    assert manifest["hardware_acceptance"] == "NOT_VERIFIED"

    positives = [cv2.imread(str(out / f"p{i:02d}.png"), cv2.IMREAD_GRAYSCALE)
                 for i in range(receipt.pattern_pairs)]
    negatives = [cv2.imread(str(out / f"n{i:02d}.png"), cv2.IMREAD_GRAYSCALE)
                 for i in range(receipt.pattern_pairs)]
    decoded = calib.decode_graycode(positives, negatives, (8, 6))
    gy, gx = np.indices((6, 8))
    assert decoded.valid.all()
    np.testing.assert_array_equal(decoded.px, gx)
    np.testing.assert_array_equal(decoded.py, gy)


def test_existing_output_directory_refused_without_overwrite(tmp_path):
    out = tmp_path / "saved"
    out.mkdir()
    marker = out / "p00.png"
    marker.write_bytes(b"owner bytes")
    with pytest.raises(FileExistsError):
        capture.capture_sequence(8, 6, out, lambda _: None,
                                 lambda: np.zeros((6, 8), dtype=np.uint8))
    assert marker.read_bytes() == b"owner bytes"


def test_failed_frame_leaves_no_success_manifest(tmp_path):
    out = tmp_path / "partial"
    calls = [0]
    def grab():
        calls[0] += 1
        if calls[0] == 3:
            raise capture.CaptureError("camera disconnected")
        return np.full((6, 8), 127, dtype=np.uint8)

    with pytest.raises(capture.CaptureError, match="disconnected"):
        capture.capture_sequence(8, 6, out, lambda _: None, grab)
    assert not (out / "capture_manifest.json").exists()
    assert (out / "p00.png").exists()


def test_resolution_change_is_fail_closed(tmp_path):
    n = [0]
    def grab():
        n[0] += 1
        return np.zeros((6, 8 if n[0] < 3 else 9), np.uint8)
    out = tmp_path / "changed"
    with pytest.raises(capture.CaptureError, match="resolution"):
        capture.capture_sequence(8, 6, out, lambda _: None, grab)
    assert not (out / "capture_manifest.json").exists()


@pytest.mark.parametrize("image", [
    np.zeros((1, 2), np.uint8),
    np.zeros((6, 8), np.float32),
    np.zeros((6, 8, 2), np.uint8),
    np.zeros((3000, 3000), np.uint8),
    None,
])
def test_bad_camera_frames_rejected(image):
    with pytest.raises(capture.CaptureError):
        capture._grayscale(image)


@pytest.mark.parametrize(("width", "height"), [
    (0, 6), (8, 0), (1, 2), (1921, 10), (8, 1081),
    (True, 2), (8.5, 6), (1920, 1081)
])
def test_invalid_projector_dimensions_rejected(width, height):
    with pytest.raises(ValueError):
        capture.pattern_count(width, height)


def test_camera_never_opened_without_explicit_confirmation(monkeypatch, tmp_path):
    def not_opened(*args, **kwargs):
        raise AssertionError("hardware must never start without confirmation")
    monkeypatch.setattr(capture.cv2, "VideoCapture", not_opened)
    with pytest.raises(capture.CaptureError, match="confirmation"):
        capture.capture_opencv(8, 6, tmp_path / "nope", camera_index=0,
                               projector_x=1920, projector_y=0)
    assert not (tmp_path / "nope").exists()


def test_local_hardware_adapter_sequence_with_mocked_camera_and_display(monkeypatch, tmp_path):
    shown = [None]
    log = []
    class FakeCamera:
        def isOpened(self):
            return True
        def grab(self):
            log.append("grab")
            return True
        def read(self):
            assert shown[0] is not None
            gray = np.where(shown[0] > 127, 200, 10).astype(np.uint8)
            return True, gray
        def release(self):
            log.append("release")

    monkeypatch.setattr(capture.cv2, "VideoCapture", lambda index: FakeCamera())
    monkeypatch.setattr(capture.cv2, "namedWindow", lambda *a: log.append("window"))
    monkeypatch.setattr(capture.cv2, "moveWindow", lambda *a: None)
    monkeypatch.setattr(capture.cv2, "setWindowProperty", lambda *a: None)
    monkeypatch.setattr(capture.cv2, "imshow", lambda _, im: shown.__setitem__(0, im.copy()))
    monkeypatch.setattr(capture.cv2, "waitKey", lambda _: -1)
    monkeypatch.setattr(capture.cv2, "destroyWindow", lambda *a: log.append("destroy"))

    out = tmp_path / "mock-hardware"
    result = capture.capture_opencv(8, 6, out, camera_index=1,
                                    projector_x=1920, projector_y=0,
                                    confirmed=True, warmup_frames=1)
    assert len(result.image_files) == 2 * result.pattern_pairs
    assert log[0] == "window" and log[-2:] == ["release", "destroy"]


def test_camera_open_failure_releases_device(monkeypatch, tmp_path):
    released = []
    class Unavailable:
        def isOpened(self):
            return False
        def release(self):
            released.append(True)
    monkeypatch.setattr(capture.cv2, "VideoCapture", lambda index: Unavailable())
    with pytest.raises(capture.CaptureError, match="not available"):
        capture.capture_opencv(8, 6, tmp_path / "missing", camera_index=0,
                               projector_x=1920, projector_y=0, confirmed=True)
    assert released == [True]
    assert not (tmp_path / "missing").exists()
