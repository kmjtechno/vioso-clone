"""M32: CP PLUS-class fisheye and webcam offline lens-model QA.

Uses generated checkerboard pixel coordinates, NOT real camera access.
"""
import json

import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone import fisheye_calibration as fish


def synthetic_views(n=18):
    rng = np.random.default_rng(17)
    size = (640, 480)
    intrinsic = np.array([
        [430.0, 0.0, 320.0], [0.0, 435.0, 240.0], [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    distortion = np.array([0.016, -0.003, 0.0001, 0.00001], np.float64)
    board = np.zeros((9 * 6, 1, 3), dtype=np.float64)
    board[:, 0, :2] = np.array(
        [(col, row) for row in range(6) for col in range(9)]) * 22.0
    points = []
    for _ in range(n):
        rotation = rng.uniform(-0.42, 0.42, 3).reshape(3, 1)
        translation = np.array([
            rng.uniform(-115, 40), rng.uniform(-75, 30),
            rng.uniform(390, 590)], np.float64).reshape(3, 1)
        pixels, _ = cv2.fisheye.projectPoints(
            board, rotation, translation, intrinsic, distortion)
        pixels = pixels + rng.normal(0, 0.08, size=pixels.shape)
        assert (pixels[:, :, 0] >= 0).all() and (pixels[:, :, 0] < 640).all()
        assert (pixels[:, :, 1] >= 0).all() and (pixels[:, :, 1] < 480).all()
        points.append(pixels)
    return points, size, intrinsic


def test_synthetic_fisheye_model_passes_without_hardware():
    points, size, expected = synthetic_views()
    result = fish.calibrate_observations(
        points, size, square_mm=22.0)
    assert result["schema"] == "kmj.fisheye.intrinsics.v1"
    assert result["lens_model"] == "opencv_fisheye"
    assert result["software_calibration"] == "PASS"
    assert result["hardware_acceptance"] == "NOT_VERIFIED"
    assert result["native_vioso_sps_compatible"] is False
    assert result["views_used"] == 18
    assert result["image_coverage_fraction"] >= 0.5
    assert result["reprojection_rms_px"] < 0.3
    assert result["worst_view_rms_px"] < 0.4
    fitted = np.asarray(result["camera_matrix"])
    np.testing.assert_allclose(fitted[0, 0], expected[0, 0], atol=10)
    np.testing.assert_allclose(fitted[1, 1], expected[1, 1], atol=10)
    assert len(result["fisheye_distortion_k1_k2_k3_k4"]) == 4
    assert result["fisheye_distortion_k1_k2_k3_k4"][2:] == [0.0, 0.0]


@pytest.mark.parametrize("mode", [
    "too_few", "duplicate", "outside", "bad_shape",
    "nonnumeric", "nan", "limited_coverage"
])
def test_invalid_fisheye_inputs_fail_closed(mode):
    points, size, _ = synthetic_views()
    if mode == "too_few":
        points = points[:11]
    elif mode == "duplicate":
        points[1] = points[0].copy()
    elif mode == "outside":
        points[0][0, 0, 0] = -1
    elif mode == "bad_shape":
        points[0] = np.zeros((3, 2))
    elif mode == "nonnumeric":
        points[0] = np.full((54, 2), "oops")
    elif mode == "nan":
        points[0][0, 0, 0] = float("nan")
    elif mode == "limited_coverage":
        points = [p * 0.10 + np.array([[[260.0, 180.0]]])
                  for p in points]
    with pytest.raises(fish.FisheyeCalibrationError):
        fish.calibrate_observations(points, size, square_mm=22.0)


@pytest.mark.parametrize("kwargs", [
    {"cols": 3}, {"cols": 17}, {"rows": 2},
    {"square_mm": 0}, {"square_mm": float("nan")},
    {"max_rms_px": 0.0}, {"max_rms_px": 100},
    {"max_rms_px": float("inf")},
])
def test_invalid_board_and_quality_bounds_rejected(kwargs):
    points, size, _ = synthetic_views()
    with pytest.raises(fish.FisheyeCalibrationError):
        fish.calibrate_observations(points, size, square_mm=22.0, **kwargs)


def test_offline_photo_loader_read_only_on_calibration(monkeypatch, tmp_path):
    points, size, _ = synthetic_views()
    folder = tmp_path / "owner-checkerboard"
    folder.mkdir()
    originals = {}
    for i in range(18):
        path = folder / f"board-{i:03d}.png"
        assert cv2.imwrite(str(path), np.full(
            (size[1], size[0]), i + 45, dtype=np.uint8))
        originals[path.name] = path.read_bytes()
    counter = iter(points)

    def detect(_image, _pattern_size, flags):
        assert _pattern_size == (9, 6)
        return True, next(counter).copy()

    monkeypatch.setattr(fish.cv2, "findChessboardCornersSB", detect)
    output = fish.calibrate_photo_folder(
        folder, square_mm=22.0)
    assert output["software_calibration"] == "PASS"
    assert output["hardware_acceptance"] == "NOT_VERIFIED"
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == originals


def test_no_photos_rejects_before_opening_camera(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    with pytest.raises(fish.FisheyeCalibrationError, match="12..48"):
        fish.calibrate_photo_folder(folder)


def test_linked_photos_refused_without_modifying_owner_bytes(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    orig = folder / "camera01.png"
    orig.write_bytes(b"untrusted-but-unchanged")
    alias = folder / "camera02.png"
    try:
        alias.symlink_to(orig)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    for i in range(3, 13):
        (folder / f"camera{i:02d}.png").write_bytes(b"same")
    with pytest.raises(fish.FisheyeCalibrationError, match="unsafe"):
        fish.calibrate_photo_folder(folder)
    assert orig.read_bytes() == b"untrusted-but-unchanged"


def test_cli_refuses_missing_photos_and_emits_no_success(tmp_path, capsys):
    folder = tmp_path / "frames"
    folder.mkdir()
    assert main(["fisheye-calibrate", str(folder)]) == 2
    cap = capsys.readouterr()
    assert "12..48" in cap.err
    assert "software_calibration" not in cap.out


def test_cli_returns_json_without_writes_when_calibration_succeeds(monkeypatch, tmp_path, capsys):
    report = {
        "schema": "kmj.fisheye.intrinsics.v1",
        "lens_model": "opencv_fisheye",
        "software_calibration": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
    }
    monkeypatch.setattr(fish, "calibrate_photo_folder",
                        lambda *_args, **_kwargs: report.copy())
    assert main(["fisheye-calibrate", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert list(tmp_path.iterdir()) == []
