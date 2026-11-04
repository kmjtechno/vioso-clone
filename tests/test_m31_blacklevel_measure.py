"""M31 camera-space black level measurements, independent software diagnostics."""
import json

import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone.blacklevel_measure import BlackLevelError, analyze_black_frames


@pytest.fixture
def frames(tmp_path):
    h, w = 8, 12
    out = tmp_path / "samples"
    out.mkdir()
    ambient = np.full((h, w), 10, np.uint8)
    p1 = np.full((h, w), 10, np.uint8)
    p2 = np.full((h, w), 10, np.uint8)
    p1[:, :8] = 20
    p2[:, 4:] = 30
    coverage1 = np.zeros((h, w), np.uint8)
    coverage1[:, :8] = 255
    coverage2 = np.zeros((h, w), np.uint8)
    coverage2[:, 4:] = 255
    for name, img in [
        ("ambient.png", ambient), ("p1-black.png", p1),
        ("p2-black.png", p2), ("p1-coverage.png", coverage1),
        ("p2-coverage.png", coverage2),
    ]:
        assert cv2.imwrite(str(out / name), img)
    manifest = {
        "schema": "kmj.blacklevel.frames.v1",
        "acquisition_mode": "single_projector_black_vs_ambient",
        "camera_size": [w, h],
        "ambient": "ambient.png",
        "projectors": [
            {"name": "left", "black_frame": "p1-black.png",
             "coverage_mask": "p1-coverage.png"},
            {"name": "right", "black_frame": "p2-black.png",
             "coverage_mask": "p2-coverage.png"},
        ],
    }
    source = out / "blacklevel.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    return out, source


def _files(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_blacklevel_overlap_diagnostic_is_read_only_and_has_correct_values(frames):
    folder, source = frames
    old = _files(folder)
    result = analyze_black_frames(source)
    assert result["software_blacklevel_analysis"] == "COMPUTED"
    assert result["hardware_acceptance"] == "NOT_VERIFIED"
    assert result["native_vioso_sps_compatible"] is False
    assert result["camera_response_units"] == "encoded_8bit_grayscale_not_cd_per_m2"
    assert result["ambient_median_code"] == 10.0
    assert result["projectors_checked"] == 2
    assert result["projectors"][0]["black_minus_ambient_median_code"] == 10.0
    assert result["projectors"][1]["black_minus_ambient_median_code"] == 20.0
    assert result["overlap_aggregate_black_p95_code"] == 40.0
    assert result["nonoverlap_aggregate_black_p95_code"] == 30.0
    assert abs(result["overlap_fraction_of_covered_pixels"] - 1/3) < 1e-6
    assert _files(folder) == old


def test_cli_prints_machine_readable_json_no_writes(frames, capsys):
    folder, source = frames
    original = _files(folder)
    assert main(["blacklevel-check", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["projectors_checked"] == 2
    assert report["interpretation"] == "approximate additive camera-space diagnostic only"
    assert _files(folder) == original


def test_optional_camera_roi_restricts_diagnostics(frames):
    folder, source = frames
    roi = np.zeros((8, 12), np.uint8)  # black included
    roi[:, :2] = 255                    # white excluded
    assert cv2.imwrite(str(folder / "camera-roi.png"), roi)
    data = json.loads(source.read_text())
    data["camera_roi"] = "camera-roi.png"
    source.write_text(json.dumps(data), encoding="utf-8")
    report = analyze_black_frames(source)
    assert abs(report["camera_roi_fraction"] - 10/12) < 1e-6
    assert report["overlap_aggregate_black_p95_code"] == 40.0


def test_negative_exposure_drift_refused(frames):
    folder, source = frames
    assert cv2.imwrite(str(folder / "p1-black.png"),
                       np.zeros((8, 12), np.uint8))
    with pytest.raises(BlackLevelError, match="below ambient"):
        analyze_black_frames(source)


def test_ambient_saturation_refused(frames):
    folder, source = frames
    assert cv2.imwrite(str(folder / "ambient.png"),
                       np.full((8, 12), 255, np.uint8))
    with pytest.raises(BlackLevelError, match="saturated"):
        analyze_black_frames(source)


@pytest.mark.parametrize("problem", [
    "invalid_schema", "unknown_key", "wrong_mode", "only_one_projector",
    "duplicate_label", "traversal", "wrong_size", "bad_coverage", "missing_frame"
])
def test_invalid_sample_manifest_or_png_fail_closed(frames, problem):
    folder, source = frames
    data = json.loads(source.read_text())
    if problem == "invalid_schema":
        data["schema"] = "vendor.levels"
    elif problem == "unknown_key":
        data["vendor_payload"] = []
    elif problem == "wrong_mode":
        data["acquisition_mode"] = "uncontrolled"
    elif problem == "only_one_projector":
        data["projectors"] = data["projectors"][:1]
    elif problem == "duplicate_label":
        data["projectors"][1]["name"] = "left"
    elif problem == "traversal":
        data["ambient"] = "../ambient.png"
    elif problem == "wrong_size":
        assert cv2.imwrite(str(folder / "p2-black.png"),
                           np.zeros((7, 12), np.uint8))
    elif problem == "bad_coverage":
        assert cv2.imwrite(str(folder / "p2-coverage.png"),
                           np.full((8, 12), 128, np.uint8))
    elif problem == "missing_frame":
        data["projectors"][0]["black_frame"] = "not-found.png"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((BlackLevelError, ValueError)):
        analyze_black_frames(source)


def test_manifest_symlink_and_nonfinite_json_refused(frames, tmp_path):
    folder, source = frames
    alias = folder / "linked.json"
    try:
        alias.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(BlackLevelError, match="non-symlink"):
        analyze_black_frames(alias)
    source.write_text('{"schema":NaN}', encoding="utf-8")
    with pytest.raises(BlackLevelError):
        analyze_black_frames(source)
