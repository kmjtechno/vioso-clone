"""M25 software-only Gray-code capture quality gates (no camera or projector)."""
import json

import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone import capture
from vclone.capture_check import CaptureCheckError, check_capture


@pytest.fixture
def captured(tmp_path):
    folder = tmp_path / "session"
    shown = [None]

    def show(pattern):
        shown[0] = pattern.copy()

    def grab():
        return shown[0].copy()

    capture.capture_sequence(8, 6, folder, show, grab)
    return folder


def _all_bytes(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_ideal_synthetic_capture_has_full_validity_and_is_read_only(captured):
    before = _all_bytes(captured)
    report = check_capture(captured)
    assert report["schema"] == "kmj.graycode.capture-check.v1"
    assert report["software_capture_quality"] == "PASS"
    assert report["hardware_acceptance"] == "NOT_VERIFIED"
    assert report["native_vioso_sps_compatible"] is False
    assert report["projector_size"] == [8, 6]
    assert report["camera_size"] == [8, 6]
    assert report["pattern_pairs_checked"] == capture.pattern_count(8, 6)
    assert report["decoded_valid_fraction"] == 1.0
    assert report["projector_axis_span_fraction"] == [1.0, 1.0]
    assert report["min_pair_reliable_fraction"] == 1.0
    assert _all_bytes(captured) == before


def test_cli_success_and_failure_do_not_touch_capture_files(captured, capsys):
    before = _all_bytes(captured)
    assert main(["capture-check", str(captured)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hardware_acceptance"] == "NOT_VERIFIED"
    assert main(["capture-check", str(captured), "--margin", "255"]) == 2
    assert "margin" in capsys.readouterr().err.lower()
    assert _all_bytes(captured) == before


def test_missing_frame_is_refused(captured):
    (captured / "p01.png").unlink()
    with pytest.raises(CaptureCheckError, match="capture PNG"):
        check_capture(captured)


def test_low_contrast_capture_refused_before_calibration(captured):
    for path in captured.glob("*.png"):
        assert cv2.imwrite(str(path), np.full((6, 8), 128, dtype=np.uint8))
    with pytest.raises(CaptureCheckError, match="valid-pixel"):
        check_capture(captured)


def test_low_span_capture_refused(tmp_path):
    state = [None]
    folder = tmp_path / "narrow"
    def show(pattern):
        state[0] = pattern.copy()
    def grab():
        # Camera sees only a 2x2 projector region, replicated across its sensor.
        return np.tile(state[0][:2, :2], (3, 4))
    capture.capture_sequence(8, 6, folder, show, grab)
    with pytest.raises(CaptureCheckError, match="coordinate span"):
        check_capture(folder, min_axis_span=0.25)


def test_manifest_scope_mismatch_and_symlink_capture_refused(captured, tmp_path):
    manifest = captured / "capture_manifest.json"
    obj = json.loads(manifest.read_text())
    obj["image_files"][0] = "../secret.png"
    manifest.write_text(json.dumps(obj))
    with pytest.raises(CaptureCheckError, match="pattern list"):
        check_capture(captured)
    obj["image_files"][0] = "p00.png"
    manifest.write_text(json.dumps(obj))
    alias = captured / "p00.png"
    old = captured / "owner-reference.png"
    alias.rename(old)
    try:
        alias.symlink_to(old)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks not available")
    with pytest.raises(CaptureCheckError, match="symlink"):
        check_capture(captured)


@pytest.mark.parametrize("field,value", [
    ("schema", "some.other.capture"),
    ("pattern_pairs", 1),
    ("pattern_pairs", True),
    ("camera_size", [100000, 100000]),
    ("projector_size", [640, -1]),
    ("hardware_acceptance", "CERTIFIED"),
])
def test_invalid_manifest_is_fail_closed(captured, field, value):
    manifest = captured / "capture_manifest.json"
    obj = json.loads(manifest.read_text())
    obj[field] = value
    manifest.write_text(json.dumps(obj))
    with pytest.raises(CaptureCheckError):
        check_capture(captured)


def test_corrupted_png_header_and_wrong_size_rejected(captured):
    p = captured / "p02.png"
    p.write_bytes(b"not really a png")
    with pytest.raises(CaptureCheckError, match="PNG"):
        check_capture(captured)


@pytest.mark.parametrize("kwargs", [
    {"margin": -1}, {"margin": True}, {"margin": 255},
    {"min_valid_fraction": 0.0}, {"min_valid_fraction": float("nan")},
    {"min_valid_fraction": True}, {"min_axis_span": 1.1},
    {"min_axis_span": float("inf")},
])
def test_unsafe_thresholds_rejected_before_any_image_reads(captured, kwargs):
    with pytest.raises(CaptureCheckError):
        check_capture(captured, **kwargs)


def test_reference_directory_symlink_refused(captured, tmp_path):
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(captured, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks not available")
    with pytest.raises(CaptureCheckError, match="directory"):
        check_capture(alias)
