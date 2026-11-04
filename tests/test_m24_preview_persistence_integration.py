"""M24: integrated M22 CPU preview and M23 atomic clone JSON persistence.

All tests are synthetic/software-only. No camera/projector, vendor format or
physical calibration acceptance is implied.
"""
import cv2
import numpy as np
import pytest

from vclone.gui_model import Session, SessionError
from vclone.project import Project


def test_atomic_saved_calibration_can_preview_and_export_without_owner_overwrite(tmp_path):
    mesh = [[[0.0, 0.0], [15.0, 0.0]], [[0.0, 11.0], [15.0, 11.0]]]
    original_project = Project(
        "integrated",
        scan={"proj_size": [16, 12]},
        result={"mesh": mesh, "coverage": 1.0},
    )
    project_file = tmp_path / "calibration.json"
    original_project.save(project_file)
    before_project_bytes = project_file.read_bytes()

    image = np.zeros((12, 16, 3), dtype=np.uint8)
    image[:, :, :] = (35, 115, 205)
    source_path = tmp_path / "content.png"
    assert cv2.imwrite(str(source_path), image)
    before_source_bytes = source_path.read_bytes()

    session = Session(Project.load(project_file))
    frame = session.preview_content(source_path)
    assert frame.shape == image.shape
    assert frame.dtype == np.uint8
    assert frame[5, 7].tolist() == [35, 115, 205]

    output_path = tmp_path / "cpu-preview.png"
    assert session.save_preview_png(frame, output_path) == output_path
    assert cv2.imread(str(output_path)).shape == image.shape
    existing_export = output_path.read_bytes()
    with pytest.raises(SessionError, match="new regular path"):
        session.save_preview_png(frame, output_path)
    assert output_path.read_bytes() == existing_export

    assert source_path.read_bytes() == before_source_bytes
    assert project_file.read_bytes() == before_project_bytes
    assert session.dirty is False
    assert list(tmp_path.glob(".*.pending")) == []


def test_malformed_project_cannot_be_previewed_or_replaced_by_export(tmp_path):
    invalid_project = tmp_path / "invalid.json"
    invalid_project.write_text('{"scan":[], "result": {}}', encoding="utf-8")
    unchanged = invalid_project.read_bytes()

    with pytest.raises(ValueError, match="invalid top-level"):
        Project.load(invalid_project)

    # Even a valid calibrated session must only write a NEW PNG, not an
    # existing owner's JSON project file.
    session = Session(Project("sample", scan={"proj_size": [16, 12]},
                              result={"mesh": [[[0., 0.], [15., 0.]],
                                               [[0., 11.], [15., 11.]]]}))
    frame = np.zeros((12, 16, 3), dtype=np.uint8)
    with pytest.raises(SessionError, match="png"):
        session.save_preview_png(frame, invalid_project)
    assert invalid_project.read_bytes() == unchanged
