"""M63 measured fisheye camera UI, no hardware, all owner data isolated."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from vclone.project import Project
from vclone.gui_model import Session


def app():
    return QApplication.instance() or QApplication([])


def setup(tmp_path):
    captures = tmp_path / "capture"
    captures.mkdir()
    (captures / "capture_manifest.json").write_text(json.dumps({
        "schema": "kmj.graycode.capture.v1", "camera_size": [64, 64]}))
    photos = tmp_path / "photos"
    photos.mkdir()
    for i in range(12):
        (photos / f"view-{i:02d}.png").write_bytes(b"synthetic-photo-content")
    return captures, photos


def profile(size=(64, 64)):
    return {
        "schema": "kmj.fisheye.intrinsics.v1",
        "lens_model": "opencv_fisheye",
        "software_calibration": "PASS",
        "hardware_acceptance": "NOT_VERIFIED",
        "native_vioso_sps_compatible": False,
        "image_size": list(size),
        "views_used": 12,
        "reprojection_rms_px": 0.75,
        "camera_matrix": [
            [64.0, 0.0, size[0] / 2],
            [0.0, 64.0, size[1] / 2],
            [0.0, 0.0, 1.0]],
        "fisheye_distortion_k1_k2_k3_k4": [0.1, 0.02, 0.0, 0.0],
    }


def test_lens_photo_input_requires_12_regular_files_new_json_and_capture_size(tmp_path):
    from vclone.fisheye_wizard import validate_destination
    capture, photos = setup(tmp_path)
    target, size = validate_destination(capture, "lens-measured.json", photos)
    assert target.parent == capture and size == (64, 64)
    target.write_text("{}")
    with pytest.raises(ValueError, match="NEW"):
        validate_destination(capture, "lens-measured.json", photos)
    with pytest.raises(ValueError, match="basename"):
        validate_destination(capture, "../outside.json", photos)
    (photos / "view-00.png").unlink()
    with pytest.raises(ValueError):
        validate_destination(capture, "other.json", photos)


def test_verified_new_profile_is_exclusive_and_lens_size_checked(tmp_path):
    from vclone.fisheye_wizard import write_new_measured_profile
    capture, photos = setup(tmp_path)
    target = capture / "lens.json"
    saved = write_new_measured_profile(target, profile(), (64, 64))
    assert saved == target
    obj = json.loads(target.read_text())
    assert obj["software_calibration"] == "PASS"
    assert obj["hardware_acceptance"] == "NOT_VERIFIED"
    with pytest.raises(ValueError):
        write_new_measured_profile(target, profile(), (64, 64))
    with pytest.raises(ValueError):
        write_new_measured_profile(capture / "wrong.json", profile(), (800, 600))
    assert not (capture / "wrong.json").exists()


def test_lens_worker_failure_never_prints_secret_path_or_backend_exception(monkeypatch):
    app()
    from vclone import fisheye_wizard as mod
    monkeypatch.setattr(mod, "calibrate_photo_folder",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            RuntimeError("private/C:/RTSP-url?password=SECRET")))
    worker = mod.LensFitWorker("C:/private", 9, 6, 25.0, 1.5)
    output = []
    worker.failed.connect(output.append)
    worker.run()
    assert output == ["FISHEYE_FIT_FAILED"]


def test_fisheye_dialog_is_inert_until_owner_authorizes(tmp_path):
    app()
    from vclone.fisheye_wizard import FisheyeCalibrationDialog
    capture, photos = setup(tmp_path)
    d = FisheyeCalibrationDialog(capture)
    try:
        assert not d.run_button.isEnabled()
        assert d.values() is None
        assert d._worker is None
        assert len(list(capture.iterdir())) == 1
        d.photos.setText(str(photos))
        d.confirm.setChecked(True)
        assert d.run_button.isEnabled()
    finally:
        d.close()


def test_synthetic_solved_profile_written_only_after_worker_success(tmp_path):
    app()
    from vclone.fisheye_wizard import FisheyeCalibrationDialog
    capture, photos = setup(tmp_path)
    d = FisheyeCalibrationDialog(capture)
    try:
        d._target = capture / "fit.json"
        d._expected_size = (64, 64)
        d._fitted(profile())
        assert d._profile_saved
        assert d.values() is None  # not Accepted before worker.finished
        assert (capture / "fit.json").is_file()
        d._finished()
        assert d.result() == QDialog.DialogCode.Accepted
        assert d.values() == capture / "fit.json"
    finally:
        d.close()


def test_wizard_real_lens_action_wires_profile_to_existing_attach_consent(monkeypatch, tmp_path):
    app()
    from vclone import calibration_wizard as mod
    from vclone.gui import MainWindow
    from vclone.calibration_wizard import CalibrationWizard
    class FakeDialog:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return tmp_path / "lens.json"
    monkeypatch.setattr(mod, "FisheyeCalibrationDialog", FakeDialog)
    w = MainWindow()
    wizard = CalibrationWizard(w)
    seen = []
    monkeypatch.setattr(wizard, "attach_fisheye",
                        lambda preferred_path=None: seen.append(preferred_path))
    try:
        wizard.measure_fisheye()
        assert seen == [str(tmp_path / "lens.json")]
        assert w._camera_probe_worker is None
    finally:
        wizard.close()
        w.close()


def test_binary_camera_roi_mask_in_wizard_invalidates_old_mesh_and_corners(tmp_path, monkeypatch):
    app()
    from vclone.gui import MainWindow
    from vclone.calibration_wizard import CalibrationWizard
    capture, _ = setup(tmp_path)
    mask = np.zeros((64, 64), np.uint8)
    mask[:3, :] = 255
    source = capture / "camera-roi.png"
    assert cv2.imwrite(str(source), mask)
    p = Project(scan={
        "dir": str(capture), "proj_size": [64, 64],
        "content_size": [64, 64], "cam_corners": [[1, 1]] * 4,
        "content_corners": [[1, 1]] * 4,
    }, result={"mesh": [[[0, 0], [1, 0]], [[0, 1], [1, 1]]]},
       steps_done=["Calibrate", "Export"])
    w = MainWindow(Session(p))
    wizard = CalibrationWizard(w)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_: (str(source), ""))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_: QMessageBox.StandardButton.Yes)
    try:
        wizard.attach_camera_mask()
        assert p.scan["camera_mask"] == source.name
        assert "cam_corners" not in p.scan
        assert p.result == {}
        assert p.steps_done == []
        assert w.session.dirty
        assert wizard._quality is None
    finally:
        wizard.close()
        w.close()
