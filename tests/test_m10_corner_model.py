"""M10 camera-corner geometry and non-destructive GUI model regression."""
import json

import pytest

from vclone.corners import content_corners, validate_corners, validate_size
from vclone.gui_model import Session, SessionError
from vclone.project import Project


VALID = [[11, 10], [87, 13], [84, 64], [8, 60]]
SIZE = (100, 80)


def make_capture(tmp_path, *, manifest=True):
    folder = tmp_path / "new-capture"
    folder.mkdir()
    (folder / "p00.png").write_bytes(b"synthetic test frame")
    if manifest:
        (folder / "capture_manifest.json").write_text(json.dumps({
            "schema": "kmj.graycode.capture.v1",
            "projector_size": [80, 60],
            "camera_size": [100, 80],
            "pattern_pairs": 13
        }), encoding="utf-8")
    return folder


def test_valid_clockwise_image_corners_and_content_mapping():
    points = validate_corners(VALID, SIZE)
    assert points[0] == [11.0, 10.0]
    assert len(points) == 4
    assert content_corners([640, 480]) == [
        [0.0, 0.0], [639.0, 0.0], [639.0, 479.0], [0.0, 479.0]
    ]


@pytest.mark.parametrize("points", [
    [],
    VALID[:3],
    VALID + [[20, 20]],
    [VALID[0], VALID[3], VALID[2], VALID[1]],  # reverse winding
    [[10, 10], [80, 60], [80, 10], [10, 60]],  # crossing edges
    [[10, 10], [20, 11], [30, 12], [40, 13]], # collinear
    [[10, 10], [11, 10], [11, 11], [10, 11]], # too small
    [[-1, 10], [87, 13], [84, 64], [8, 60]],
    [[11, 10], [float("nan"), 13], [84, 64], [8, 60]],
    [[11, 10], [float("inf"), 13], [84, 64], [8, 60]],
])
def test_invalid_corner_geometry_fails_closed(points):
    with pytest.raises(ValueError):
        validate_corners(points, SIZE)


@pytest.mark.parametrize("size", [
    None, [1, 1080], [1920, 0], [4097, 20], [100, 2161],
    [True, 20], [40.5, 20], [100], [100, 80, 2],
])
def test_bad_image_dimensions_fails_closed(size):
    with pytest.raises(ValueError):
        validate_size(size)


def test_configure_and_select_four_corners_marks_session_dirty(tmp_path):
    folder = make_capture(tmp_path)
    session = Session(Project("camera-config"))
    session.configure_scan(folder, [80, 60], [640, 480])
    assert session.project.scan["dir"] == str(folder)
    assert session.project.scan["proj_size"] == [80, 60]
    assert session.dirty
    session.set_camera_corners(VALID, SIZE)
    assert session.project.scan["cam_corners"][2] == [84., 64.]
    assert session.project.scan["content_corners"][2] == [639., 479.]
    assert session.project.scan["corner_image"] == "p00.png"
    assert session.project.result == {}
    target = tmp_path / "saved-project.json"
    session.save(target)
    loaded = Project.load(target)
    assert loaded.scan["cam_corners"] == session.project.scan["cam_corners"]
    assert loaded.scan["content_corners"] == session.project.scan["content_corners"]


def test_invalid_click_does_not_corrupt_existing_project(tmp_path):
    folder = make_capture(tmp_path)
    session = Session(Project("safe"))
    session.configure_scan(folder, [80, 60], [640, 480])
    session.set_camera_corners(VALID, SIZE)
    before = json.dumps(session.project.scan, sort_keys=True)
    with pytest.raises(ValueError):
        session.set_camera_corners([VALID[0], VALID[2], VALID[1], VALID[3]], SIZE)
    assert json.dumps(session.project.scan, sort_keys=True) == before


def test_setup_change_invalidates_stale_mesh_and_corners(tmp_path):
    folder = make_capture(tmp_path)
    session = Session(Project("stale"))
    session.configure_scan(folder, [80, 60], [640, 480])
    session.set_camera_corners(VALID, SIZE)
    session.project.result = {"mesh": [[[0, 0]]] }
    session.project.steps_done = ["Design", "Calibrate", "Export"]
    session.configure_scan(folder, [80, 60], [800, 600])
    assert session.project.result == {}
    assert "cam_corners" not in session.project.scan
    assert "content_corners" not in session.project.scan
    assert session.project.steps_done == ["Design"]


def test_new_corners_invalidate_old_calibration(tmp_path):
    folder = make_capture(tmp_path)
    session = Session(Project("stale"))
    session.configure_scan(folder, [80, 60], [640, 480])
    session.project.result = {"mesh": [[[0, 0]]]}
    session.project.steps_done = ["Calibrate", "Export"]
    session.set_camera_corners(VALID, SIZE)
    assert not session.project.result and not session.project.steps_done


def test_manifest_mismatch_preserves_previous_project_state(tmp_path):
    folder = make_capture(tmp_path)
    session = Session(Project("safe"))
    before = json.dumps(session.project.scan, sort_keys=True)
    with pytest.raises(SessionError, match="manifest"):
        session.configure_scan(folder, [160, 120], [640, 480])
    assert json.dumps(session.project.scan, sort_keys=True) == before
    assert not session.dirty


def test_missing_capture_file_and_unsafe_path_rejected(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    s = Session(Project("no captures"))
    with pytest.raises(SessionError, match="p00"):
        s.configure_scan(folder, [80, 60], [640, 480])
    with pytest.raises(SessionError, match="directory"):
        s.configure_scan(tmp_path / "missing", [80, 60], [640, 480])
