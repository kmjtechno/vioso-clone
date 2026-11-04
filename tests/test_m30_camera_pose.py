"""M30 clean-room camera pose tests: synthetic markers, outliers, guardrails."""
import json

import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone.camera_pose import CameraPoseError, SCHEMA, estimate_pose, load_markers


def synthetic(seed=420, *, outlier=False):
    rng = np.random.default_rng(seed)
    world = rng.uniform([-100, -80, -40], [100, 80, 40], (16, 3))
    intr = np.array([[900.0, 0.0, 640.0],
                     [0.0, 895.0, 360.0],
                     [0.0, 0.0, 1.0]], dtype=np.float64)
    rotation = np.array([[0.08], [-0.04], [0.02]], dtype=np.float64)
    translation = np.array([[20.0], [-10.0], [900.0]], dtype=np.float64)
    projected, _ = cv2.projectPoints(world, rotation, translation, intr,
                                     np.zeros(5, dtype=np.float64))
    pixels = projected.reshape(-1, 2)
    pixels += rng.normal(0.0, 0.08, size=pixels.shape)
    if outlier:
        pixels[0] = [20.0, 20.0]  # one wrong but syntactically in-bounds marker
    payload = {
        "schema": SCHEMA,
        "world_units": "mm",
        "image_size": [1280, 720],
        "intrinsics": {
            "fx": 900.0, "fy": 895.0, "cx": 640.0, "cy": 360.0,
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "markers": [
            {"world": w.tolist(), "image": p.tolist()}
            for w, p in zip(world, pixels)
        ],
    }
    return payload, rotation.reshape(3), translation.reshape(3)


def test_synthetic_pose_meets_reprojection_gate_without_hardware():
    data, expected_rot, expected_translation = synthetic()
    report = estimate_pose(data, max_rms_px=1.5)
    assert report["schema"] == "kmj.camera-pose.solution.v1"
    assert report["software_pose_quality"] == "PASS"
    assert report["hardware_acceptance"] == "NOT_VERIFIED"
    assert report["native_vioso_sps_compatible"] is False
    assert report["world_units"] == "mm"
    assert report["markers_inlier"] == report["markers_total"] == 16
    assert report["reprojection_rms_px"] < 0.20
    np.testing.assert_allclose(report["rotation_vector_world_to_camera"],
                               expected_rot, atol=0.02)
    np.testing.assert_allclose(report["translation_world_to_camera"],
                               expected_translation, atol=2.0)
    rotation = np.asarray(report["rotation_matrix_world_to_camera"])
    center = np.asarray(report["camera_center_world"])
    camera_translation = np.asarray(report["translation_world_to_camera"])
    np.testing.assert_allclose(rotation @ center + camera_translation, 0,
                               atol=1e-5)


def test_incorrect_marker_can_be_rejected_by_ransac():
    data, _, _ = synthetic(outlier=True)
    report = estimate_pose(data)
    assert 6 <= report["markers_inlier"] < report["markers_total"]
    assert report["reprojection_rms_px"] < 0.3


def test_cli_json_report_and_owner_file_unchanged(tmp_path, capsys):
    data, _, _ = synthetic()
    path = tmp_path / "markers.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    owner_before = path.read_bytes()
    assert main(["estimate-camera-pose", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["software_pose_quality"] == "PASS"
    assert path.read_bytes() == owner_before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["markers.json"]


def test_missing_or_symlink_marker_file_refused(tmp_path):
    source = tmp_path / "original.json"
    source.write_text(json.dumps(synthetic()[0]))
    with pytest.raises(CameraPoseError, match="non-symlink"):
        load_markers(tmp_path / "missing.json")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(CameraPoseError, match="non-symlink"):
        load_markers(linked)


@pytest.mark.parametrize("problem", [
    "too_few_markers", "coplanar", "duplicate_world", "duplicate_pixel",
    "nonfinite", "negative_focal", "out_of_bounds", "bad_units", "unknown_key"
])
def test_bad_marker_data_rejected(problem):
    data, _, _ = synthetic()
    if problem == "too_few_markers":
        data["markers"] = data["markers"][:5]
    elif problem == "coplanar":
        for marker in data["markers"]:
            marker["world"][2] = 0
    elif problem == "duplicate_world":
        data["markers"][0]["world"] = data["markers"][1]["world"].copy()
    elif problem == "duplicate_pixel":
        data["markers"][0]["image"] = data["markers"][1]["image"].copy()
    elif problem == "nonfinite":
        data["markers"][3]["world"][0] = float("nan")
    elif problem == "negative_focal":
        data["intrinsics"]["fx"] = -100
    elif problem == "out_of_bounds":
        data["markers"][1]["image"][0] = 5000
    elif problem == "bad_units":
        data["world_units"] = "unknown"
    elif problem == "unknown_key":
        data["vendor_payload"] = "not allowed"
    with pytest.raises(CameraPoseError):
        estimate_pose(data)


@pytest.mark.parametrize("kwargs", [
    {"max_rms_px": float("nan")},
    {"max_rms_px": 0},
    {"max_rms_px": 1000},
    {"min_inlier_fraction": True},
    {"min_inlier_fraction": 0.4},
    {"min_inlier_fraction": 1.1},
])
def test_invalid_quality_gates_fail_before_fit(kwargs):
    data, _, _ = synthetic()
    with pytest.raises(CameraPoseError):
        estimate_pose(data, **kwargs)


def test_inlier_gate_blocks_too_many_outliers():
    data, _, _ = synthetic()
    for i, marker in enumerate(data["markers"][:9]):
        marker["image"] = [float(i * 40 + 10), float(20 + i * 20)]
    with pytest.raises(CameraPoseError):
        estimate_pose(data, min_inlier_fraction=0.90)


def test_json_rejects_nonfinite_and_oversized(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"schema":NaN}', encoding="utf-8")
    with pytest.raises(CameraPoseError):
        load_markers(path)
    path.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(CameraPoseError, match="64 KiB"):
        load_markers(path)
