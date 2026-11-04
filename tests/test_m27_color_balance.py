"""M27 independent bounded color-balance preview, not photometric hardware QA."""
import json

import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone import color_balance, multi_output
from vclone.project import Project


def _projects():
    mesh = np.stack(np.meshgrid(np.linspace(0, 19, 3), np.linspace(0, 11, 3)), -1)
    return [
        Project(name, scan={"proj_size": [20, 12], "content_size": [20, 12]},
                result={"mesh": mesh.tolist()})
        for name in ("left", "right")
    ]


def _profile():
    return {
        "schema": color_balance.SCHEMA,
        "projectors": [
            {"gain_bgr": [0.5, 1, 1], "black_subtract_bgr": [10, 0, 0]},
            {"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, 0]},
        ]
    }


def _input(tmp_path):
    p = tmp_path / "content.png"
    assert cv2.imwrite(str(p), np.full((12, 20, 3), 200, dtype=np.uint8))
    return p


def test_color_balance_pixel_math_bgr_and_zero_remains_black():
    frame = np.asarray([[[0, 50, 200], [100, 200, 255]]], np.uint8)
    output = color_balance.apply_preview(frame, {
        "gain_bgr": [2, .5, 1], "black_subtract_bgr": [10, 20, 30]})
    assert output.tolist() == [[[0, 15, 170], [180, 90, 225]]]


def test_profile_file_strict_and_read_only(tmp_path):
    path = tmp_path / "balance.json"
    path.write_text(json.dumps(_profile()), encoding="utf-8")
    before = path.read_bytes()
    parsed = color_balance.load_profile(path, 2)
    assert parsed[0]["gain_bgr"] == [0.5, 1.0, 1.0]
    assert color_balance.load_profile(path, 2) == parsed
    assert path.read_bytes() == before


def test_opt_in_export_adjusts_only_requested_projector_and_records_not_verified(tmp_path):
    content = _input(tmp_path)
    plain = multi_output.export_multi(_projects(), content, tmp_path / "plain")
    profiles = color_balance.validate_profiles(_profile()["projectors"], 2)
    tuned = multi_output.export_multi(
        _projects(), content, tmp_path / "tuned", color_balance_profiles=profiles)
    assert "color_balance_preview" not in plain
    assert tuned["color_balance_preview"]["hardware_photometric_acceptance"] == "NOT_VERIFIED"
    assert tuned["color_balance_preview"]["schema"] == color_balance.SCHEMA
    p1 = cv2.imread(str(tmp_path / "plain" / "projector_01.png"))
    p2 = cv2.imread(str(tmp_path / "plain" / "projector_02.png"))
    t1 = cv2.imread(str(tmp_path / "tuned" / "projector_01.png"))
    t2 = cv2.imread(str(tmp_path / "tuned" / "projector_02.png"))
    assert int(t1[5, 9, 0]) < int(p1[5, 9, 0])
    assert int(t1[5, 9, 1]) == int(p1[5, 9, 1])
    np.testing.assert_array_equal(t2, p2)
    assert json.loads((tmp_path / "tuned" / "manifest.json").read_text()) == tuned


def test_cli_with_profile_and_existing_output_refuses_overwrite(tmp_path, capsys):
    content = _input(tmp_path)
    project_paths = []
    for i, obj in enumerate(_projects()):
        path = tmp_path / f"p{i}.json"
        obj.save(path)
        project_paths.append(str(path))
    profile = tmp_path / "balance.json"
    profile.write_text(json.dumps(_profile()), encoding="utf-8")
    output = tmp_path / "preview"
    args = ["export-multi", str(content), str(output), *project_paths,
            "--color-balance", str(profile)]
    assert main(args) == 0
    assert "NOT_VERIFIED" in capsys.readouterr().out
    prior = (output / "projector_01.png").read_bytes()
    assert main(args) == 2
    assert "exists" in capsys.readouterr().err.lower()
    assert (output / "projector_01.png").read_bytes() == prior


@pytest.mark.parametrize("projectors", [
    [],
    [{"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, 0]}],
    [{"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, 0]}] * 9,
    [{"gain_bgr": [2.01, 1, 1], "black_subtract_bgr": [0, 0, 0]}] * 2,
    [{"gain_bgr": [True, 1, 1], "black_subtract_bgr": [0, 0, 0]}] * 2,
    [{"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, -1]}] * 2,
    [{"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, 0], "unexpected": 5}] * 2,
    [{"gain_bgr": [1, 1, 1], "black_subtract_bgr": [0, 0, 0]} , None],
])
def test_bad_profiles_rejected_before_output_is_created(tmp_path, projectors):
    out = tmp_path / "bad"
    with pytest.raises(color_balance.ColorBalanceError):
        multi_output.export_multi(_projects(), _input(tmp_path), out,
                                  color_balance_profiles=projectors)
    assert not out.exists()


def test_encoded_black_subtraction_cannot_raise_black_pixel():
    black = np.zeros((2, 3, 3), dtype=np.uint8)
    out = color_balance.apply_preview(black, {
        "gain_bgr": [2, 2, 2], "black_subtract_bgr": [64, 64, 64]})
    assert not out.any()


@pytest.mark.parametrize("change", [
    {"schema": "vendor.photometry.v7"},
    {"projectors": []},
    {"unexpected": True},
])
def test_strict_profile_schema_rejects_mismatch(tmp_path, change):
    obj = _profile()
    obj.update(change)
    path = tmp_path / "balance.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(color_balance.ColorBalanceError):
        color_balance.load_profile(path, 2)


def test_symlink_profile_refused(tmp_path):
    original = tmp_path / "original.json"
    original.write_text(json.dumps(_profile()), encoding="utf-8")
    alias = tmp_path / "linked.json"
    try:
        alias.symlink_to(original)
    except (NotImplementedError, OSError):
        pytest.skip("symlink unavailable")
    with pytest.raises(color_balance.ColorBalanceError, match="non-symlink"):
        color_balance.load_profile(alias, 2)


def test_nonfinite_json_and_wrong_count_rejected(tmp_path):
    path = tmp_path / "wrong.json"
    path.write_text('{"schema":"kmj.color-balance.preview.v1","projectors":NaN}')
    with pytest.raises(color_balance.ColorBalanceError):
        color_balance.load_profile(path, 2)
    path.write_text(json.dumps(_profile()))
    with pytest.raises(color_balance.ColorBalanceError, match="count"):
        color_balance.load_profile(path, 3)
