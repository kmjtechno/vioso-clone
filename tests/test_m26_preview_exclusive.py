"""M26 CLI calibrated preview never overwrites existing owner PNGs."""
import cv2
import numpy as np
import pytest

from vclone.__main__ import main
from vclone.project import MissingInput, Project, render_preview


def _scene(tmp_path):
    x, y = np.meshgrid(np.linspace(0, 15, 3), np.linspace(0, 11, 3))
    p = Project("preview", scan={"proj_size": [16, 12]},
                result={"mesh": np.stack([x, y], axis=-1).tolist()})
    source = tmp_path / "content.png"
    assert cv2.imwrite(str(source), np.full((12, 16, 3), (40, 90, 180), np.uint8))
    return p, source


def test_export_creates_new_png_and_preserves_source_and_project(tmp_path):
    p, source = _scene(tmp_path)
    before_input = source.read_bytes()
    before_project = (dict(p.scan), dict(p.result))
    output = tmp_path / "new.png"
    render_preview(p, source, output)
    image = cv2.imread(str(output))
    assert image.shape == (12, 16, 3)
    assert image[5, 7].tolist() == [40, 90, 180]
    assert source.read_bytes() == before_input
    assert (p.scan, p.result) == before_project


def test_cli_existing_owner_file_not_overwritten(tmp_path, capsys):
    p, source = _scene(tmp_path)
    project_path = tmp_path / "project.json"
    p.save(project_path)
    project_bytes = project_path.read_bytes()
    output = tmp_path / "owner.png"
    original = b"EXISTING OWNER DATA"
    output.write_bytes(original)
    assert main(["preview", str(project_path), str(source), str(output)]) == 2
    assert "new .png" in capsys.readouterr().err
    assert output.read_bytes() == original
    assert project_path.read_bytes() == project_bytes


def test_no_extension_or_missing_parent_refused_without_side_effect(tmp_path):
    p, src = _scene(tmp_path)
    for output in (tmp_path / "out.jpg", tmp_path / "missing" / "out.png"):
        with pytest.raises(ValueError, match="new .png"):
            render_preview(p, src, output)
        assert not output.exists()


def test_symlink_target_refused(tmp_path):
    p, src = _scene(tmp_path)
    owner = tmp_path / "owner.png"
    owner.write_bytes(b"owner untouched")
    linked = tmp_path / "linked.png"
    try:
        linked.symlink_to(owner)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this runner")
    with pytest.raises(ValueError, match="new .png"):
        render_preview(p, src, linked)
    assert owner.read_bytes() == b"owner untouched"


def test_failed_encoding_does_not_create_output(tmp_path, monkeypatch):
    p, src = _scene(tmp_path)
    output = tmp_path / "out.png"
    monkeypatch.setattr(cv2, "imencode", lambda *a, **k: (False, None))
    with pytest.raises(MissingInput, match="encode"):
        render_preview(p, src, output)
    assert not output.exists()


def test_missing_calibration_cannot_create_new_output(tmp_path):
    _, src = _scene(tmp_path)
    dest = tmp_path / "out.png"
    with pytest.raises(MissingInput):
        render_preview(Project("uncalibrated"), src, dest)
    assert not dest.exists()


def test_xml_preview_existing_target_reports_script_error_without_overwrite(tmp_path):
    from vclone import script
    p, src = _scene(tmp_path)
    dest = tmp_path / "owner.png"
    dest.write_bytes(b"EXISTING_OWNER")
    xml = ('<?xml version="1.0"?><VIOSO><File version="1.0.0"/>'
           '<task action="Execute" typ="Preview">'
           '<param content="content.png" out="owner.png"/></task></VIOSO>')
    with pytest.raises(script.ScriptError, match="new .png"):
        script.run_script(xml, project=p, base_dir=tmp_path)
    assert dest.read_bytes() == b"EXISTING_OWNER"
