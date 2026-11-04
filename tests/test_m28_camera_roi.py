"""M28 optical camera ROI: clean-room mask, scan decoder and capture QA."""
import cv2
import numpy as np
import pytest

from vclone import calib, capture
from vclone.__main__ import main
from vclone.capture_check import CaptureCheckError, check_capture
from vclone.optical_roi import CameraMaskError, read_camera_mask
from vclone.project import InvalidInput, Project, run_step


@pytest.fixture
def fixture(tmp_path):
    state = [None]
    folder = tmp_path / "scan"
    def show(pattern):
        state[0] = pattern.copy()
    def grab():
        return state[0].copy()
    capture.capture_sequence(8, 6, folder, show, grab)
    camera = np.zeros((6, 8), dtype=np.uint8)  # black = include
    camera[:, :4] = 255                         # white = exclude
    roi_file = folder / "camera-roi.png"
    assert cv2.imwrite(str(roi_file), camera)
    return folder, roi_file


def test_binary_roi_reader_and_source_bytes_unchanged(fixture):
    folder, file = fixture
    before = file.read_bytes()
    mask = read_camera_mask(file, (6, 8))
    assert mask.dtype == np.bool_
    assert mask.shape == (6, 8)
    assert not mask[:, :4].any()
    assert mask[:, 4:].all()
    assert file.read_bytes() == before
    assert len(list(folder.glob(".*.pending"))) == 0


def test_graycode_decoder_respects_mask_and_keeps_captured_images(fixture):
    folder, file = fixture
    captures = [cv2.imread(str(folder / f"p{i:02d}.png"), 0)
                for i in range(capture.pattern_count(8, 6))]
    inverses = [cv2.imread(str(folder / f"n{i:02d}.png"), 0)
                for i in range(capture.pattern_count(8, 6))]
    before = [frame.copy() for frame in captures + inverses]
    roi = read_camera_mask(file, (6, 8))
    decoded = calib.decode_graycode(captures, inverses, (8, 6), camera_mask=roi)
    assert decoded.valid[:, 4:].all() and not decoded.valid[:, :4].any()
    for a, b in zip(captures + inverses, before):
        np.testing.assert_array_equal(a, b)


def test_camera_mask_excludes_unlit_pixels_from_quality_denominator(fixture, capsys):
    folder, file = fixture
    originals = {}
    for name in [p.name for p in folder.glob("[pn][0-9][0-9].png")]:
        path = folder / name
        frame = cv2.imread(str(path), 0)
        frame[:, :4] = 128
        assert cv2.imwrite(str(path), frame)
        originals[name] = path.read_bytes()
    with pytest.raises(CaptureCheckError, match="valid-pixel"):
        check_capture(folder, min_valid_fraction=0.90)
    report = check_capture(folder, camera_mask=file, min_valid_fraction=0.90)
    assert report["camera_mask_applied"] is True
    assert report["camera_roi_fraction"] == 0.5
    assert report["decoded_valid_fraction"] == 1.0
    assert report["projector_axis_span_fraction"][0] > 0.40
    assert main(["capture-check", str(folder), "--camera-mask", str(file),
                 "--min-valid-fraction", "0.90"]) == 0
    assert '"software_capture_quality": "PASS"' in capsys.readouterr().out
    assert {name: (folder / name).read_bytes() for name in originals} == originals


@pytest.mark.parametrize("invalid", [
    np.full((6, 8), 255, np.uint8),
    np.full((6, 8), 128, np.uint8),
    np.zeros((5, 8), np.uint8),
    np.zeros((6, 9), np.uint8),
])
def test_unsafe_camera_roi_refused(fixture, invalid):
    _, file = fixture
    assert cv2.imwrite(str(file), invalid)
    with pytest.raises(CameraMaskError):
        read_camera_mask(file, (6, 8))


def test_color_png_and_symlinks_refused(fixture):
    folder, path = fixture
    assert cv2.imwrite(str(path), np.zeros((6, 8, 3), np.uint8))
    with pytest.raises(CameraMaskError, match="grayscale"):
        read_camera_mask(path, (6, 8))
    target = folder / "owner-roi.png"
    assert cv2.imwrite(str(target), np.zeros((6, 8), np.uint8))
    link = folder / "link.png"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(CameraMaskError, match="non-symlink"):
        read_camera_mask(link, (6, 8))


def test_decoder_refuses_wrong_type_or_shape_without_mutation(fixture):
    folder, _ = fixture
    n = capture.pattern_count(8, 6)
    captures = [cv2.imread(str(folder / f"p{i:02d}.png"), 0) for i in range(n)]
    inverses = [cv2.imread(str(folder / f"n{i:02d}.png"), 0) for i in range(n)]
    for invalid in (np.zeros((6, 8), np.uint8), np.zeros((5, 8), bool),
                    np.zeros((6, 8), bool)):
        with pytest.raises(ValueError, match="camera mask"):
            calib.decode_graycode(captures, inverses, (8, 6), camera_mask=invalid)


def test_scan_project_uses_safe_mask_filename(fixture, monkeypatch):
    folder, file = fixture
    seen = []
    original = calib.decode_graycode
    def recording(captures, inverses, proj_size, margin=20, camera_mask=None):
        seen.append(camera_mask)
        return original(captures, inverses, proj_size, margin=margin,
                        camera_mask=camera_mask)
    monkeypatch.setattr(calib, "decode_graycode", recording)
    # Synthetic identity geometry; mask excludes half the camera field.
    project = Project("masked")
    project.scan = {
        "dir": str(folder), "proj_size": [8, 6], "content_size": [8, 6],
        "cam_corners": [[0, 0], [7, 0], [7, 5], [0, 5]],
        "content_corners": [[0, 0], [7, 0], [7, 5], [0, 5]],
        "nodes": [4, 3], "camera_mask": file.name,
    }
    run_step(project, "Calibrate")
    assert len(seen) == 1
    assert seen[0].shape == (6, 8)
    assert not seen[0][:, :4].any() and seen[0][:, 4:].all()
    assert "mesh" in project.result


@pytest.mark.parametrize("name", ["../mask.png", "/tmp/mask.png", r"..\mask.png", "bad.txt", ""])
def test_scan_rejects_external_mask_paths(fixture, name):
    folder, _ = fixture
    proj = Project("unsafe")
    proj.scan = {
        "dir": str(folder), "proj_size": [8, 6], "content_size": [8, 6],
        "cam_corners": [[0, 0], [7, 0], [7, 5], [0, 5]],
        "content_corners": [[0, 0], [7, 0], [7, 5], [0, 5]],
        "camera_mask": name,
    }
    with pytest.raises(InvalidInput, match="camera_mask"):
        run_step(proj, "Calibrate")
    assert proj.result == {}
