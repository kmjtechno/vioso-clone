"""M14 offline multi-output and overlap blending regression; no physical devices."""
import hashlib
import json

import cv2
import numpy as np
import pytest

from vclone import multi_output as multi
from vclone.__main__ import main
from vclone.project import Project


def calibrated(name="test", width=40, height=24):
    x, y = np.meshgrid(np.linspace(0, width - 1, 5),
                       np.linspace(0, height - 1, 4))
    p = Project(name)
    p.scan = {"proj_size": [width, height], "content_size": [width, height]}
    p.result = {"mesh": np.stack([x, y], axis=-1).tolist()}
    return p


def content_image(tmp_path, value=200):
    path = tmp_path / "content.png"
    assert cv2.imwrite(str(path), np.full((24, 40, 3), value, np.uint8))
    return path


def test_two_calibrated_projectors_generate_hashed_blended_outputs(tmp_path):
    content = content_image(tmp_path)
    result = multi.export_multi([calibrated("p1"), calibrated("p2")], content,
                                tmp_path / "new-output")
    assert result["schema"] == "kmj.multi-projector.offline.v1"
    assert result["hardware_acceptance"] == "NOT_VERIFIED"
    assert result["software_preview_only"] is True
    assert result["content_size"] == [40, 24]
    assert result["overlap_fraction"] > 0.90
    assert result["uncovered_fraction"] < 0.01
    assert len(result["projectors"]) == 2
    images = []
    for i in range(2):
        info = result["projectors"][i]
        assert info["project_index"] == i + 1
        file = tmp_path / "new-output" / info["image_file"]
        assert file.is_file()
        assert info["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
        images.append(cv2.imread(str(file), cv2.IMREAD_COLOR))
    np.testing.assert_array_equal(images[0], images[1])
    assert 120 <= int(images[0][12, 20, 0]) <= 180
    assert json.loads((tmp_path / "new-output" / "manifest.json").read_text()) == result


def test_output_directory_must_not_exist_and_owner_files_are_untouched(tmp_path):
    src = content_image(tmp_path)
    output = tmp_path / "owner"
    output.mkdir()
    marker = output / "projector_01.png"
    marker.write_bytes(b"owner data")
    with pytest.raises(FileExistsError):
        multi.export_multi([calibrated(), calibrated()], src, output)
    assert marker.read_bytes() == b"owner data"
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("n", [0, 1, 9])
def test_projector_count_bounded_before_creating_files(tmp_path, n):
    src = content_image(tmp_path)
    out = tmp_path / ("out" + str(n))
    with pytest.raises(multi.MultiExportError, match="2 and 8"):
        multi.export_multi([calibrated()] * n, src, out)
    assert not out.exists()


@pytest.mark.parametrize("gamma", [float("nan"), 0, 0.49, 4.1, float("inf"), True])
def test_blend_gamma_bounds(gamma, tmp_path):
    src = content_image(tmp_path)
    with pytest.raises(multi.MultiExportError, match="gamma"):
        multi.export_multi([calibrated(), calibrated()], src, tmp_path / "bad", gamma=gamma)
    assert not (tmp_path / "bad").exists()


def test_content_resolution_mismatch_refused_before_output(tmp_path):
    src = content_image(tmp_path)
    other = calibrated("p2")
    other.scan["content_size"] = [120, 80]
    with pytest.raises(multi.MultiExportError, match="share"):
        multi.export_multi([calibrated(), other], src, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_invalid_calibration_refused_without_writing_output(tmp_path):
    src = content_image(tmp_path)
    p2 = calibrated("bad")
    p2.result["mesh"] = [[[None, None]] * 5] * 4
    with pytest.raises(multi.MultiExportError, match="valid projector"):
        multi.export_multi([calibrated(), p2], src, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_invalid_projector_dimensions_refused(tmp_path):
    src = content_image(tmp_path)
    p2 = calibrated("bad")
    p2.scan["proj_size"] = [10000, 10000]
    with pytest.raises(multi.MultiExportError, match="dimensions"):
        multi.export_multi([calibrated(), p2], src, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_bad_content_file_and_symlink_refused(tmp_path):
    missing = tmp_path / "none.png"
    with pytest.raises(multi.MultiExportError, match="not available"):
        multi.export_multi([calibrated(), calibrated()], missing, tmp_path / "bad")
    source = content_image(tmp_path)
    alias = tmp_path / "alias.png"
    try:
        alias.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(multi.MultiExportError, match="symlink"):
        multi.export_multi([calibrated(), calibrated()], alias, tmp_path / "bad")


def test_failed_second_png_leaves_no_manifest(tmp_path, monkeypatch):
    src = content_image(tmp_path)
    real = multi.cv2.imwrite
    def fail_second(name, img):
        if name.endswith("projector_02.png"):
            return False
        return real(name, img)
    monkeypatch.setattr(multi.cv2, "imwrite", fail_second)
    out = tmp_path / "partial"
    with pytest.raises(multi.MultiExportError, match="write"):
        multi.export_multi([calibrated(), calibrated()], src, out)
    assert (out / "projector_01.png").is_file()
    assert not (out / "manifest.json").exists()


def test_multiple_meshes_produce_distinct_preview_images(tmp_path):
    src = content_image(tmp_path)
    p2 = calibrated("offset")
    p2.result["mesh"] = (np.asarray(p2.result["mesh"]) + [400, 0]).tolist()
    with pytest.raises(multi.MultiExportError, match="no content coverage"):
        multi.export_multi([calibrated(), p2], src, tmp_path / "bad")


def test_cli_export_multi_and_refuse_existing_output(tmp_path, capsys):
    src = content_image(tmp_path)
    paths = []
    for n in (1, 2):
        file = tmp_path / f"p{n}.json"
        calibrated(f"p{n}").save(file)
        paths.append(str(file))
    out = tmp_path / "multi"
    args = ["export-multi", str(src), str(out), *paths, "--gamma", "2.2"]
    assert main(args) == 0
    assert "NOT_VERIFIED" in capsys.readouterr().out
    assert (out / "manifest.json").is_file()
    assert main(args) == 2
    assert "File exists" in capsys.readouterr().err


def test_cli_rejects_single_project_before_file_read(tmp_path, capsys):
    assert main(["export-multi", str(tmp_path / "no.png"),
                 str(tmp_path / "out"), str(tmp_path / "missing.json")]) == 2
    assert "2..8" in capsys.readouterr().err
