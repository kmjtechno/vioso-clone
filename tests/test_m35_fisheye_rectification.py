"""M35 fisheye rectification integrated into optical Gray-code decode.

Software-only synthetic frames; no projector, webcam, RTSP or device access.
"""
import json

import cv2
import numpy as np
import pytest

from vclone import capture
from vclone.__main__ import main
from vclone.capture_check import CaptureCheckError, check_capture
from vclone.fisheye_rectify import (
    FisheyeRectifier, FisheyeRectifyError, read_fisheye_profile,
)
from vclone.project import InvalidInput, Project, run_step


def profile(w=64, h=48):
    return {
        "schema": "kmj.fisheye.intrinsics.v1",
        "lens_model": "opencv_fisheye",
        "software_calibration": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "image_size": [w, h],
        "views_used": 18,
        "reprojection_rms_px": 0.12,
        "camera_matrix": [
            [float(w), 0.0, w / 2.0],
            [0.0, float(w), h / 2.0],
            [0.0, 0.0, 1.0],
        ],
        "fisheye_distortion_k1_k2_k3_k4": [0.0, 0.0, 0.0, 0.0],
    }


@pytest.fixture
def sample(tmp_path):
    state = [None]
    folder = tmp_path / "original-capture"

    def show(pattern):
        state[0] = pattern.copy()

    def grab():
        return state[0].copy()

    capture.capture_sequence(64, 48, folder, show, grab)
    fitted = folder / "fisheye-model.json"
    fitted.write_text(json.dumps(profile()), encoding="utf-8")
    return folder, fitted


def _bytes(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_fisheye_rectifier_maps_without_touching_raw_image():
    lens = FisheyeRectifier(profile())
    raw = np.tile(np.arange(64, dtype=np.uint8), (48, 1))
    before = raw.copy()
    rectified = lens.image(raw)
    assert rectified.shape == raw.shape
    assert rectified.dtype == np.uint8
    assert np.count_nonzero(rectified) > 0
    np.testing.assert_array_equal(raw, before)
    assert lens.report()["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert lens.report()["native_vioso_sps_compatible"] is False
    assert lens.valid_pixels > 64 * 48 // 2


def test_fisheye_rectifier_does_not_interpret_pinhole_coefficients():
    data = profile()
    data.pop("fisheye_distortion_k1_k2_k3_k4")
    data["pinhole_distortion_k1_k2_p1_p2_k3"] = [0, 0, 0, 0, 0]
    with pytest.raises(FisheyeRectifyError, match="fisheye distortion"):
        FisheyeRectifier(data)


@pytest.mark.parametrize("field,value", [
    ("schema", "vioso.native.sps.v7"),
    ("lens_model", "opencv_pinhole"),
    ("software_calibration", "NOT_VERIFIED"),
    ("hardware_acceptance", "PASS"),
    ("native_vioso_sps_compatible", True),
    ("views_used", 5),
    ("views_used", True),
    ("reprojection_rms_px", float("nan")),
    ("image_size", [2560, 2560 + 2000]),
    ("image_size", [True, 48]),
    ("fisheye_distortion_k1_k2_k3_k4", [0, 0, 0, float("nan")]),
    ("fisheye_distortion_k1_k2_k3_k4", [0, 0, 0]),
    ("camera_matrix", [[1, 0], [0, 1]]),
])
def test_fail_closed_for_invalid_model_and_profile_metadata(field, value):
    data = profile()
    data[field] = value
    with pytest.raises(FisheyeRectifyError):
        FisheyeRectifier(data)


def test_raw_frame_shape_dtype_and_balance_guard():
    rect = FisheyeRectifier(profile())
    for image in (np.zeros((47, 64), dtype=np.uint8),
                  np.zeros((48, 64), dtype=np.float32),
                  np.zeros((48, 64, 3), dtype=np.uint8)):
        with pytest.raises(FisheyeRectifyError, match="raw fisheye"):
            rect.image(image)
    for balance in (-0.01, 1.01, float("nan"), True):
        with pytest.raises(FisheyeRectifyError, match="balance"):
            FisheyeRectifier(profile(), balance=balance)


def test_rectified_raw_camera_roi_only_includes_safe_sensor_pixels():
    rect = FisheyeRectifier(profile())
    raw = np.zeros((48, 64), dtype=bool)
    raw[5:-5, 20:44] = True
    result = rect.mask(raw)
    assert result.shape == raw.shape
    assert result.dtype == np.bool_
    assert result.any() and not np.any(result & ~rect.valid)
    assert not raw[0].any()
    with pytest.raises(FisheyeRectifyError, match="camera ROI"):
        rect.mask(np.zeros((48, 64), bool))


def test_read_only_profile_loader_rejects_links_and_oversized_json(sample):
    folder, fitted = sample
    before = fitted.read_bytes()
    assert read_fisheye_profile(fitted)["lens_model"] == "opencv_fisheye"
    assert fitted.read_bytes() == before
    link = folder / "linked-profile.json"
    try:
        link.symlink_to(fitted)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported")
    with pytest.raises(FisheyeRectifyError, match="non-symlink"):
        read_fisheye_profile(link)
    assert fitted.read_bytes() == before
    oversized = folder / "oversized-profile.json"
    oversized.write_bytes(b"X" * 65537)
    with pytest.raises(FisheyeRectifyError, match="64 KiB"):
        read_fisheye_profile(oversized)


def test_capture_quality_uses_fisheye_rectification_without_writing_originals(sample, capsys):
    folder, fitted = sample
    before = _bytes(folder)
    report = check_capture(folder, fisheye_profile=fitted, min_valid_fraction=0.25)
    assert report["software_capture_quality"] == "PASS"
    assert report["hardware_acceptance"] == "NOT_VERIFIED"
    assert report["fisheye_rectification"]["rectification"] == "APPLIED"
    assert report["camera_size"] == [64, 48]
    assert report["decoded_valid_fraction"] >= 0.25
    assert main(["capture-check", str(folder), "--fisheye-profile",
                 str(fitted), "--min-valid-fraction", "0.25"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["fisheye_rectification"]["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert _bytes(folder) == before


def test_raw_roi_plus_fisheye_rectification_correctly_combined(sample):
    folder, fitted = sample
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[:, :13] = 255  # M28 black=included, white=excluded
    roi_path = folder / "raw-roi.png"
    assert cv2.imwrite(str(roi_path), mask)
    report = check_capture(
        folder, camera_mask=roi_path, fisheye_profile=fitted,
        min_valid_fraction=0.25)
    assert report["camera_mask_applied"] is True
    assert report["fisheye_rectification"]["rectification"] == "APPLIED"
    assert 0.50 < report["camera_roi_fraction"] < 1.0


def test_calibrate_path_uses_fisheye_and_preserves_all_owner_capture_bytes(sample):
    folder, fitted = sample
    before = _bytes(folder)
    project = Project("optical-fisheye")
    project.scan = {
        "dir": str(folder), "proj_size": [64, 48],
        "content_size": [64, 48], "nodes": [5, 4],
        # Measured in virtual, rectified camera pixel coordinates.
        "cam_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "content_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "fisheye_profile": fitted.name,
    }
    run_step(project, "Calibrate")
    assert "mesh" in project.result
    assert project.result["fisheye_rectification"]["rectification"] == "APPLIED"
    assert project.result["fisheye_rectification"]["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert _bytes(folder) == before


@pytest.mark.parametrize("name", [
    "../outside.json", "/secret/fisheye.json", r"..\owner.json", "other.txt", ""
])
def test_bad_calibrate_profile_path_preserves_result_and_source(sample, name):
    folder, _ = sample
    project = Project("guarded")
    project.scan = {
        "dir": str(folder), "proj_size": [64, 48],
        "content_size": [64, 48],
        "cam_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "content_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "fisheye_profile": name,
    }
    with pytest.raises(InvalidInput, match="fisheye_profile"):
        run_step(project, "Calibrate")
    assert project.result == {}


def test_mismatched_camera_resolution_refused_before_calibration(sample):
    folder, fitted = sample
    bad = profile(w=256, h=192)
    fitted.write_text(json.dumps(bad))
    project = Project("bad-source")
    project.scan = {
        "dir": str(folder), "proj_size": [64, 48],
        "content_size": [64, 48],
        "cam_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "content_corners": [[0, 0], [63, 0], [63, 47], [0, 47]],
        "fisheye_profile": fitted.name,
    }
    with pytest.raises(InvalidInput, match="resolution"):
        run_step(project, "Calibrate")
    with pytest.raises(CaptureCheckError, match="resolution"):
        check_capture(folder, fisheye_profile=fitted)
    assert project.result == {}


def test_rectified_preview_new_png_is_exclusive_and_leaves_owner_files_unchanged(sample, capsys):
    from vclone.fisheye_rectify import FisheyeRectifyError, export_rectified_preview

    folder, fitted = sample
    raw = folder / "p00.png"
    original = _bytes(folder)
    target = folder / "rectified-preview.png"
    report = export_rectified_preview(raw, fitted, target)
    assert report["rectification"] == "APPLIED"
    assert report["hardware_optical_acceptance"] == "NOT_VERIFIED"
    output = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
    assert output.shape == (48, 64)
    assert all((folder / filename).read_bytes() == value
               for filename, value in original.items())
    old_output = target.read_bytes()
    with pytest.raises(FisheyeRectifyError, match="new PNG"):
        export_rectified_preview(raw, fitted, target)
    assert target.read_bytes() == old_output
    assert main(["fisheye-rectify-preview", str(raw), str(fitted),
                 str(folder / "second-rectified.png")]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview_created"] is True
    assert receipt["hardware_optical_acceptance"] == "NOT_VERIFIED"


def test_rectified_preview_refuses_owner_symlink_and_non_png_without_writes(sample):
    from vclone.fisheye_rectify import FisheyeRectifyError, export_rectified_preview
    folder, fitted = sample
    source = folder / "p00.png"
    before = source.read_bytes()
    owner_target = folder / "owner.json"
    owner_target.write_bytes(b"KEEP_OWNER_DATA")
    bad = folder / "preview.txt"
    with pytest.raises(FisheyeRectifyError, match="new PNG"):
        export_rectified_preview(source, fitted, bad)
    assert not bad.exists()
    link = folder / "linked.png"
    try:
        link.symlink_to(owner_target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(FisheyeRectifyError, match="new PNG"):
        export_rectified_preview(source, fitted, link)
    assert owner_target.read_bytes() == b"KEEP_OWNER_DATA"
    assert source.read_bytes() == before


def test_original_webcam_capture_quality_default_has_no_fisheye_receipt(sample):
    folder, fitted = sample
    result = check_capture(folder)
    assert result["software_capture_quality"] == "PASS"
    assert "fisheye_rectification" not in result
    assert "fisheye_rectification" not in Project("default").result
