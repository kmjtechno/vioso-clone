"""M13 local-video warp tests: all projector and video devices mocked."""
import cv2
import numpy as np
import pytest

from vclone import video_output as video
from vclone.__main__ import main
from vclone.project import Project


def calibrated_project(width=40, height=24):
    x, y = np.meshgrid(np.linspace(0, width - 1, 5),
                       np.linspace(0, height - 1, 4))
    p = Project("calibrated")
    p.scan = {"proj_size": [width, height]}
    p.result = {"mesh": np.stack([x, y], axis=-1).tolist()}
    return p


def fake_frames(n=10, color=130):
    for i in range(n):
        yield np.full((24, 40, 3), color + i, np.uint8)


def test_bounded_video_frames_are_calibrated_and_not_overrun():
    shown, delays = [], []
    receipt = video.warp_frames(
        calibrated_project(), fake_frames(20),
        lambda img: shown.append(img.copy()),
        lambda ms: (delays.append(ms) or -1),
        fps=3, seconds=2, clock=lambda: 0.0
    )
    assert receipt.frames_presented == 6
    assert not receipt.stopped_by_escape
    assert receipt.hardware_acceptance == "NOT_VERIFIED"
    assert len(shown) == 6 and len(delays) == 6
    assert all(x.shape == (24, 40, 3) for x in shown)
    assert abs(int(shown[0][10, 20, 0]) - 130) <= 1
    assert all(1 <= delay <= 1000 for delay in delays)


def test_esc_stops_display_and_returns_receipt():
    shown = []
    receipt = video.warp_frames(
        calibrated_project(), fake_frames(),
        lambda img: shown.append(img), lambda _: 27,
        fps=24, seconds=2, clock=lambda: 0
    )
    assert len(shown) == 1
    assert receipt.frames_presented == 1 and receipt.stopped_by_escape


def test_missing_or_empty_video_stream_rejected():
    with pytest.raises(video.VideoPlaybackError, match="decodable"):
        video.warp_frames(calibrated_project(), iter(()),
                          lambda _: None, lambda _: -1)


@pytest.mark.parametrize("frame", [
    None, np.zeros((1, 4, 3), np.uint8),
    np.zeros((24, 40), np.uint8),
    np.zeros((24, 40, 2), np.uint8),
    np.zeros((24, 40, 3), np.float32),
    np.zeros((3000, 3000, 3), np.uint8),
])
def test_invalid_stream_frame_rejected_before_render(frame):
    with pytest.raises(video.VideoPlaybackError, match="frame"):
        video.warp_frames(calibrated_project(), [frame],
                          lambda _: pytest.fail("invalid frame shown"), lambda _: -1)


@pytest.mark.parametrize("fps,seconds", [
    (0, 2), (31, 2), (float("nan"), 2), (2, 0),
    (2, 31), (2, float("inf")), (True, 2), (2, True)
])
def test_bounded_video_params(fps, seconds):
    with pytest.raises(ValueError):
        video.warp_frames(calibrated_project(), fake_frames(),
                          lambda _: None, lambda _: -1,
                          fps=fps, seconds=seconds)


def test_calibration_and_output_limits_fail_closed():
    empty = Project()
    with pytest.raises(Exception, match="Calibrate"):
        video.warp_frames(empty, fake_frames(), lambda _: None, lambda _: -1)
    large = calibrated_project()
    large.scan["proj_size"] = [4000, 4000]
    with pytest.raises(video.VideoPlaybackError, match="dimensions"):
        video.warp_frames(large, fake_frames(), lambda _: None, lambda _: -1)


@pytest.mark.parametrize("suffix", [".txt", ".sps", ".exe", ".png"])
def test_not_video_file_refused(tmp_path, suffix):
    path = tmp_path / ("sample" + suffix)
    path.write_bytes(b"fake")
    with pytest.raises(video.VideoPlaybackError, match="local video"):
        video._video_source(path)


def test_missing_and_symlink_sources_rejected(tmp_path):
    with pytest.raises(video.VideoPlaybackError, match="unavailable"):
        video._video_source(tmp_path / "none.mp4")
    original = tmp_path / "original.mp4"
    original.write_bytes(b"fake")
    shortcut = tmp_path / "shortcut.mp4"
    try:
        shortcut.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(video.VideoPlaybackError, match="non-symlink"):
        video._video_source(shortcut)


def test_camera_and_window_never_open_without_confirmation(monkeypatch, tmp_path):
    def deny(*args):
        pytest.fail("video device opened before approval")
    monkeypatch.setattr(video.cv2, "VideoCapture", deny)
    with pytest.raises(video.VideoPlaybackError, match="confirmation"):
        video.play_file(calibrated_project(), tmp_path / "nothing.mp4",
                        projector_x=1920, projector_y=0)


def test_mocked_video_capture_and_projector_cleanup(tmp_path, monkeypatch):
    source = tmp_path / "valid.mp4"
    source.write_bytes(b"fake video")
    events = []
    class FakeVideo:
        def __init__(self):
            self.n = 0
        def isOpened(self):
            return True
        def read(self):
            self.n += 1
            return (True, np.full((24, 40, 3), 155, np.uint8)) if self.n <= 3 else (False, None)
        def release(self):
            events.append("release")
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: FakeVideo())
    monkeypatch.setattr(video.cv2, "namedWindow", lambda *args: events.append("window"))
    monkeypatch.setattr(video.cv2, "moveWindow", lambda *args: None)
    monkeypatch.setattr(video.cv2, "setWindowProperty", lambda *args: None)
    monkeypatch.setattr(video.cv2, "imshow", lambda *args: events.append("frame"))
    monkeypatch.setattr(video.cv2, "waitKey", lambda *_: -1)
    monkeypatch.setattr(video.cv2, "destroyWindow", lambda *_: events.append("close"))
    receipt = video.play_file(calibrated_project(), source,
                              projector_x=1920, projector_y=0,
                              fps=4, seconds=1, confirmed=True)
    assert receipt.frames_presented == 3
    assert events[:2] == ["window", "frame"]
    assert events[-2:] == ["release", "close"]


def test_video_and_window_released_after_display_failure(tmp_path, monkeypatch):
    source = tmp_path / "valid.mp4"
    source.write_bytes(b"fake")
    events = []
    class Fake:
        def isOpened(self):
            return True
        def read(self):
            return True, np.full((24, 40, 3), 123, np.uint8)
        def release(self):
            events.append("release")
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: Fake())
    monkeypatch.setattr(video.cv2, "namedWindow", lambda *args: events.append("window"))
    monkeypatch.setattr(video.cv2, "moveWindow", lambda *args: None)
    monkeypatch.setattr(video.cv2, "setWindowProperty", lambda *args: None)
    monkeypatch.setattr(video.cv2, "imshow", lambda *args: (_ for _ in ()).throw(RuntimeError("device lost")))
    monkeypatch.setattr(video.cv2, "destroyWindow", lambda *args: events.append("close"))
    with pytest.raises(RuntimeError, match="device lost"):
        video.play_file(calibrated_project(), source,
                        projector_x=1920, projector_y=0, confirmed=True)
    assert events == ["window", "release", "close"]


def test_cli_confirmation_fails_before_project_read(tmp_path, capsys):
    result = main(["present-video", str(tmp_path / "missing.json"),
                   str(tmp_path / "missing.mp4"),
                   "--projector-x", "1920", "--projector-y", "0"])
    assert result == 2
    assert "--confirm-display required" in capsys.readouterr().err


def test_cli_uses_calibrated_project_and_mock_output(tmp_path, monkeypatch):
    pfile = tmp_path / "project.json"
    calibrated_project().save(pfile)
    source = tmp_path / "local.mp4"
    source.write_bytes(b"mock")
    observed = []
    monkeypatch.setattr(video, "play_file", lambda project, path, **kw:
                        observed.append((project, path, kw)) or video.VideoReceipt(2, True))
    assert main(["present-video", str(pfile), str(source),
                 "--projector-x", "1920", "--projector-y", "0",
                 "--fps", "12", "--seconds", "2", "--confirm-display"]) == 0
    assert len(observed) == 1
    assert observed[0][0].name == "calibrated"
    assert observed[0][2]["fps"] == 12


def test_frame_budget_never_decodes_extra_frame():
    read_count = []
    def counted():
        for index in range(100):
            read_count.append(index)
            yield np.full((24, 40, 3), 75, np.uint8)
    receipt = video.warp_frames(calibrated_project(), counted(),
                                lambda _: None, lambda _: -1,
                                fps=3, seconds=2, clock=lambda: 0)
    assert receipt.frames_presented == 6
    assert len(read_count) == 6


def test_real_video_codec_read_with_fake_projector(tmp_path, monkeypatch):
    """Actual OpenCV MJPEG encode/decode, but no projector hardware."""
    source = tmp_path / "local.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 5, (40, 24))
    if not writer.isOpened():
        writer.release()
        pytest.skip("OpenCV bundled build lacks MJPEG writer")
    for color in (40, 80, 120, 160):
        writer.write(np.full((24, 40, 3), color, np.uint8))
    writer.release()
    assert source.exists() and source.stat().st_size > 0
    names = []
    monkeypatch.setattr(video.cv2, "namedWindow", lambda *a: names.append("open"))
    monkeypatch.setattr(video.cv2, "moveWindow", lambda *a: None)
    monkeypatch.setattr(video.cv2, "setWindowProperty", lambda *a: None)
    monkeypatch.setattr(video.cv2, "imshow", lambda _name, image: names.append("frame"))
    monkeypatch.setattr(video.cv2, "waitKey", lambda *_: -1)
    monkeypatch.setattr(video.cv2, "destroyWindow", lambda *a: names.append("close"))
    receipt = video.play_file(calibrated_project(), source, confirmed=True,
                              projector_x=1920, projector_y=0, fps=5, seconds=2)
    assert receipt.frames_presented == 4
    assert names == ["open", "frame", "frame", "frame", "frame", "close"]
