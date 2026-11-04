"""Software calibrated still-output tests. No real display or hardware is used."""
import cv2
import numpy as np
import pytest

from vclone import output
from vclone.__main__ import main
from vclone.project import MissingInput, Project, render_frame, render_preview


def calibrated_project(width=60, height=40):
    xs, ys = np.meshgrid(np.linspace(0, width - 1, 5), np.linspace(0, height - 1, 4))
    project = Project("test")
    project.scan = {"proj_size": [width, height]}
    project.result = {"mesh": np.stack([xs, ys], -1).tolist()}
    return project


def test_render_frame_equals_existing_png_preview(tmp_path):
    project = calibrated_project()
    image = np.random.default_rng(44).integers(0, 255, (40, 60, 3), dtype=np.uint8)
    source = tmp_path / "input.png"
    dest = tmp_path / "preview.png"
    assert cv2.imwrite(str(source), image)
    frame = render_frame(project, source)
    assert frame.shape == (40, 60, 3)
    render_preview(project, source, dest)
    saved = cv2.imread(str(dest), cv2.IMREAD_COLOR)
    np.testing.assert_array_equal(frame, saved)
    assert np.abs(frame.astype(int) - image.astype(int)).max() <= 1


def test_missing_calibration_and_content_refuse_render(tmp_path):
    with pytest.raises(MissingInput, match="Calibrate"):
        render_frame(Project("no mesh"), tmp_path / "missing.png")
    with pytest.raises(MissingInput, match="cannot read"):
        render_frame(calibrated_project(), tmp_path / "missing.png")


def test_display_never_opened_without_confirmation(monkeypatch):
    def deny_window(*args, **kwargs):
        raise AssertionError("must not open a display without confirmation")
    monkeypatch.setattr(output.cv2, "namedWindow", deny_window)
    with pytest.raises(output.PresentationError, match="confirmation"):
        output.present_still(np.zeros((40, 60, 3), np.uint8),
                             projector_x=1920, projector_y=0)


@pytest.mark.parametrize("frame", [
    None, np.zeros((10, 10), np.float32),
    np.zeros((1, 10), np.uint8),
    np.zeros((10, 10, 2), np.uint8),
    np.zeros((4000, 4000), np.uint8),
    np.array(1, np.uint8),
])
def test_bad_frame_rejected_before_opening_display(frame, monkeypatch):
    monkeypatch.setattr(output.cv2, "namedWindow",
                        lambda *a: pytest.fail("window opened for bad image"))
    with pytest.raises(ValueError):
        output.present_still(frame, projector_x=1920, projector_y=0, confirmed=True)


@pytest.mark.parametrize(("x", "y", "ms"), [
    (True, 0, 10), (32769, 0, 10),
    (0, 0, 0), (0, 0, 30001), (0, 0, 1.5),
])
def test_invalid_display_coordinates_and_duration_rejected(x, y, ms, monkeypatch):
    monkeypatch.setattr(output.cv2, "namedWindow",
                        lambda *a: pytest.fail("window opened for bad display"))
    with pytest.raises(ValueError):
        output.present_still(np.zeros((40, 60, 3), np.uint8),
                             projector_x=x, projector_y=y, duration_ms=ms, confirmed=True)


def test_fake_display_presents_once_and_closes(monkeypatch):
    calls = []
    monkeypatch.setattr(output.cv2, "namedWindow", lambda *a: calls.append("open"))
    monkeypatch.setattr(output.cv2, "moveWindow", lambda *a: calls.append("move"))
    monkeypatch.setattr(output.cv2, "setWindowProperty", lambda *a: calls.append("fullscreen"))
    monkeypatch.setattr(output.cv2, "imshow", lambda *a: calls.append("show"))
    monkeypatch.setattr(output.cv2, "waitKey", lambda ms: calls.append(("wait", ms)))
    monkeypatch.setattr(output.cv2, "destroyWindow", lambda *a: calls.append("close"))
    output.present_still(np.full((40, 60, 3), 42, np.uint8),
                         projector_x=1920, projector_y=0, duration_ms=3000, confirmed=True)
    assert calls == ["open", "move", "fullscreen", "show", ("wait", 3000), "close"]


def test_window_cleanup_after_imshow_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(output.cv2, "namedWindow", lambda *a: calls.append("open"))
    monkeypatch.setattr(output.cv2, "moveWindow", lambda *a: None)
    monkeypatch.setattr(output.cv2, "setWindowProperty", lambda *a: None)
    def failed_imshow(*args):
        raise RuntimeError("simulated output loss")
    monkeypatch.setattr(output.cv2, "imshow", failed_imshow)
    monkeypatch.setattr(output.cv2, "destroyWindow", lambda *a: calls.append("close"))
    with pytest.raises(RuntimeError, match="output loss"):
        output.present_still(np.zeros((40, 60, 3), np.uint8),
                             projector_x=1920, projector_y=0, confirmed=True)
    assert calls == ["open", "close"]


def test_cli_requires_confirmation_without_reading_project(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(output.cv2, "namedWindow",
                        lambda *a: pytest.fail("display unexpectedly opened"))
    result = main(["present-preview", str(tmp_path / "not-found.json"),
                   str(tmp_path / "not-found.png"), "--projector-x", "1920",
                   "--projector-y", "0"])
    assert result == 2
    assert "--confirm-display required" in capsys.readouterr().err


def test_cli_prepares_real_calibrated_frame_then_presents_mocked(tmp_path, monkeypatch):
    project = calibrated_project()
    pfile = tmp_path / "project.json"
    project.save(pfile)
    source = tmp_path / "content.png"
    cv2.imwrite(str(source), np.full((40, 60, 3), 77, np.uint8))
    recorded = []
    monkeypatch.setattr(output, "present_still", lambda frame, **kw:
                        recorded.append((frame.copy(), kw)))
    result = main(["present-preview", str(pfile), str(source),
                   "--projector-x", "1920", "--projector-y", "0",
                   "--duration-ms", "1000", "--confirm-display"])
    assert result == 0 and len(recorded) == 1
    frame, kw = recorded[0]
    assert frame.shape == (40, 60, 3)
    assert kw == {"projector_x": 1920, "projector_y": 0,
                  "duration_ms": 1000, "confirmed": True}
