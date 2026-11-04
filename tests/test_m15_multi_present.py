"""M15 manifest-verified multi-display smoke; real files, mocked displays."""
import json

import cv2
import numpy as np
import pytest

from vclone import multi_output, multi_present
from vclone.__main__ import main
from vclone.project import Project


def project(name="p", w=40, h=24):
    x, y = np.meshgrid(np.linspace(0, w - 1, 5), np.linspace(0, h - 1, 4))
    p = Project(name)
    p.scan = {"proj_size": [w, h], "content_size": [w, h]}
    p.result = {"mesh": np.stack([x, y], -1).tolist()}
    return p


@pytest.fixture
def export_dir(tmp_path):
    src = tmp_path / "content.png"
    assert cv2.imwrite(str(src), np.full((24, 40, 3), 160, np.uint8))
    out = tmp_path / "multi"
    multi_output.export_multi([project("one"), project("two")], src, out)
    return out


def fake_displays(monkeypatch, wait_result=-1):
    events = []
    monkeypatch.setattr(multi_present.cv2, "namedWindow",
                        lambda name, mode: events.append(("open", name)))
    monkeypatch.setattr(multi_present.cv2, "moveWindow",
                        lambda name, x, y: events.append(("move", name, x, y)))
    monkeypatch.setattr(multi_present.cv2, "setWindowProperty",
                        lambda *args: None)
    monkeypatch.setattr(multi_present.cv2, "imshow",
                        lambda name, im: events.append(("show", name, im.shape)))
    monkeypatch.setattr(multi_present.cv2, "waitKey",
                        lambda ms: (events.append(("wait", ms)) or wait_result))
    monkeypatch.setattr(multi_present.cv2, "destroyWindow",
                        lambda name: events.append(("close", name)))
    return events


def test_load_actual_pngs_with_hashes(export_dir):
    images = multi_present.load_verified_frames(export_dir)
    assert len(images) == 2
    assert all(image.shape == (24, 40, 3) for image in images)
    assert all(image.dtype == np.uint8 for image in images)


def test_multiple_displays_show_and_cleanup(export_dir, monkeypatch):
    events = fake_displays(monkeypatch)
    receipt = multi_present.present_multi(
        export_dir, [(1920, 0), (3840, 0)],
        duration_ms=1234, confirmed=True)
    assert receipt.displays_presented == 2
    assert not receipt.escape_pressed
    assert receipt.hardware_acceptance == "NOT_VERIFIED"
    assert receipt.synchronization == "NOT_VERIFIED"
    assert events[0] == ("open", "KMJ Projector 01")
    assert events[1] == ("move", "KMJ Projector 01", 1920, 0)
    assert ("move", "KMJ Projector 02", 3840, 0) in events
    assert ("wait", 1234) in events
    assert events[-2:] == [("close", "KMJ Projector 02"),
                           ("close", "KMJ Projector 01")]


def test_escape_is_reported_without_claiming_hardware_acceptance(export_dir, monkeypatch):
    fake_displays(monkeypatch, wait_result=27)
    receipt = multi_present.present_multi(
        export_dir, [(1920, 0), (3840, 0)], confirmed=True)
    assert receipt.escape_pressed
    assert receipt.hardware_acceptance == "NOT_VERIFIED"


def test_unconfirmed_request_opens_no_window(monkeypatch):
    monkeypatch.setattr(multi_present.cv2, "namedWindow",
                        lambda *a: pytest.fail("window opened without permission"))
    with pytest.raises(multi_present.MultiDisplayError, match="confirmation"):
        multi_present.present_multi("/not/existing", [], confirmed=False)


@pytest.mark.parametrize("origins", [
    [], [(1920, 0)], [(0, 0), (0, 0)],
    [(True, 0), (1920, 0)], [(40000, 0), (1920, 0)],
    [(0.5, 0), (1920, 0)], [(0, 0), ("wrong", 1)],
])
def test_reject_bad_display_origins_before_opening(export_dir, monkeypatch, origins):
    monkeypatch.setattr(multi_present.cv2, "namedWindow",
                        lambda *a: pytest.fail("bad origins opened a window"))
    with pytest.raises(multi_present.MultiDisplayError):
        multi_present.present_multi(export_dir, origins, confirmed=True)


@pytest.mark.parametrize("duration", [0, 30001, -1, 1.2, True])
def test_bounded_duration_required(export_dir, duration):
    with pytest.raises(multi_present.MultiDisplayError, match="bounded"):
        multi_present.present_multi(export_dir, [(0, 0), (1920, 0)],
                                    duration_ms=duration, confirmed=True)


def test_tampered_png_is_refused_before_windows(export_dir, monkeypatch):
    png = export_dir / "projector_01.png"
    png.write_bytes(png.read_bytes() + b"unauthorized change")
    monkeypatch.setattr(multi_present.cv2, "namedWindow",
                        lambda *a: pytest.fail("window opened with tampered image"))
    with pytest.raises(multi_present.MultiDisplayError, match="digest"):
        multi_present.present_multi(export_dir, [(0, 0), (1920, 0)], confirmed=True)


def test_manifest_path_traversal_refused(export_dir):
    path = export_dir / "manifest.json"
    obj = json.loads(path.read_text())
    obj["projectors"][0]["image_file"] = "../outside.png"
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(multi_present.MultiDisplayError, match="filename"):
        multi_present.load_verified_frames(export_dir)


def test_manifest_wrong_schema_and_shape_refused(export_dir):
    path = export_dir / "manifest.json"
    obj = json.loads(path.read_text())
    obj["software_preview_only"] = False
    path.write_text(json.dumps(obj))
    with pytest.raises(multi_present.MultiDisplayError, match="schema"):
        multi_present.load_verified_frames(export_dir)


def test_window_cleanup_after_second_display_failure(export_dir, monkeypatch):
    events = fake_displays(monkeypatch)
    def fail_second(name, image):
        if name.endswith("02"):
            raise RuntimeError("second projector lost")
        events.append(("show", name, image.shape))
    monkeypatch.setattr(multi_present.cv2, "imshow", fail_second)
    with pytest.raises(RuntimeError, match="lost"):
        multi_present.present_multi(export_dir, [(0, 0), (1920, 0)],
                                    duration_ms=100, confirmed=True)
    assert events[-2:] == [("close", "KMJ Projector 02"),
                           ("close", "KMJ Projector 01")]


def test_cli_requires_confirmation_without_touching_files(tmp_path, capsys):
    assert main(["present-multi", str(tmp_path / "missing"),
                 "--origin", "0,0", "--origin", "1920,0"]) == 2
    assert "--confirm-display required" in capsys.readouterr().err


def test_cli_two_display_origin_flow(export_dir, monkeypatch, capsys):
    events = fake_displays(monkeypatch)
    assert main(["present-multi", str(export_dir),
                 "--origin", "1920,0", "--origin", "3840,0",
                 "--duration-ms", "300", "--confirm-display"]) == 0
    assert "NOT_VERIFIED" in capsys.readouterr().out
    assert ("wait", 300) in events
