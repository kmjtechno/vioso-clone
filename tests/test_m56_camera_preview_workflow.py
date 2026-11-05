"""M56 physical-proof UX remains opt-in, synthetic-only and zero hardware I/O."""
import os
import numpy as np
import pytest

from vclone import camera_frame_probe
from vclone.calibration_readiness import software_readiness, human_checklist
from vclone.project import Project


class _Camera:
    def __init__(self):
        self.released = False
        self.frames = 0
    def grab(self):
        return True
    def read(self):
        self.frames += 1
        yy, xx = np.ogrid[:256, :256]
        disk = (xx - 127) ** 2 + (yy - 127) ** 2 <= 115 ** 2
        return True, np.where(disk, 70 + self.frames, 0).astype("uint8")
    def release(self):
        self.released = True


PROFILE = {
    "schema": "kmj.camera.source.v1",
    "type": "onvif",
    "source": {"host": "192.168.22.50", "port": 80,
               "scheme": "http", "username": "", "password": ""},
    "backend": "ffmpeg",
}


def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_preview_opt_in_requires_existing_explicit_camera_consent(monkeypatch):
    monkeypatch.setattr(
        camera_frame_probe, "open_camera",
        lambda *_: (_ for _ in ()).throw(AssertionError("opened without consent")))
    with pytest.raises(camera_frame_probe.CameraProbeError, match="confirm-camera"):
        camera_frame_probe.camera_frame_probe(
            PROFILE, confirmed=False, frames=6, return_preview=True)


def test_preview_invalid_flag_refuses_even_with_consent(monkeypatch):
    monkeypatch.setattr(
        camera_frame_probe, "open_camera",
        lambda *_: (_ for _ in ()).throw(AssertionError("opened unsafe")))
    for value in (None, "true", 1, [], {}):
        with pytest.raises(camera_frame_probe.CameraProbeError, match="boolean"):
            camera_frame_probe.camera_frame_probe(
                PROFILE, confirmed=True, frames=6, return_preview=value)


def test_bounded_grayscale_preview_never_embedded_in_receipt(monkeypatch, tmp_path):
    cameras = []
    def open_cam(*_args):
        camera = _Camera()
        cameras.append(camera)
        return camera
    monkeypatch.setattr(camera_frame_probe, "open_camera", open_cam)
    base = camera_frame_probe.camera_frame_probe(PROFILE, confirmed=True, frames=6)
    receipt, preview = camera_frame_probe.camera_frame_probe(
        PROFILE, confirmed=True, frames=6, return_preview=True)
    assert isinstance(base, dict) and isinstance(receipt, dict)
    assert receipt == base
    assert preview.dtype == np.uint8 and preview.ndim == 2
    assert 16 <= preview.shape[0] <= 240 and 16 <= preview.shape[1] <= 320
    assert preview[preview.shape[0]//2, preview.shape[1]//2] > 0
    assert preview[0, 0] == 0
    assert all(c.released for c in cameras)
    assert list(tmp_path.iterdir()) == []
    assert "192.168.22.50" not in repr(receipt)


def test_camera_worker_emits_image_only_when_enabled(monkeypatch):
    _qt()
    from PySide6.QtGui import QImage
    from vclone import gui, camera_frame_probe as mod
    emitted = []
    def fake_probe(*args, **kw):
        emitted.append(kw.get("return_preview", False))
        receipt = {"camera_connection": "OPENED_AND_FRAMES_READ",
                   "camera_size": [256,256], "frames_observed": 6}
        return (receipt, np.full((128,128), 170, dtype=np.uint8)) if kw.get("return_preview") else receipt
    monkeypatch.setattr(mod, "camera_frame_probe", fake_probe)
    worker = gui.CameraProbeWorker(PROFILE)
    frames, reports = [], []
    worker.preview_ready.connect(frames.append)
    worker.report_ready.connect(reports.append)
    worker.run()
    assert emitted == [False] and not frames and len(reports) == 1
    worker.preview_enabled = True
    worker.run()
    assert emitted == [False, True]
    assert len(frames) == 1 and isinstance(frames[0], QImage)
    assert frames[0].format() == QImage.Format.Format_Grayscale8
    assert frames[0].width() == frames[0].height() == 128


def test_gui_preview_dialog_does_not_enable_content_png_export(monkeypatch):
    _qt()
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QMessageBox
    from vclone import gui
    monkeypatch.setattr(QMessageBox, "exec", lambda *_: 0)
    w = gui.MainWindow()
    try:
        original_log = list(w.session.log)
        frame = QImage(128, 128, QImage.Format.Format_Grayscale8)
        frame.fill(77)
        w._camera_preview_ready(frame)
        assert w.session.log == original_log
        assert w.session.dirty is False
        assert w._preview_frame is None
        assert not w.preview_export_button.isEnabled()
        for frame in [QImage(), QImage(400,100,QImage.Format.Format_Grayscale8)]:
            w._camera_preview_ready(frame)
        assert w.session.log == original_log
    finally:
        w.close()


def test_readiness_empty_project_never_claims_pass_or_hardware_verification():
    p = Project()
    stages = software_readiness(p)
    assert len(stages) == 8
    assert [s.key for s in stages] == [
        "camera", "intrinsics", "rig", "capture",
        "corners", "calibration", "blend", "export"]
    assert stages[0].status == "OPERATOR_TEST_REQUIRED"
    assert stages[5].status == "CALIBRATION_REQUIRED"
    assert all(s.status != "HARDWARE_VERIFIED" for s in stages)
    assert "Multi-projector seam and blend" in human_checklist(p)
    assert not any(s.status == "PASS" for s in stages)


def test_readiness_with_configured_project_is_not_physical_acceptance():
    p = Project()
    p.scan = {"dir": "private-capture-no-read", "proj_size": [640,480],
              "content_size": [1920,1080], "cam_corners": [[0,0]]*4,
              "content_corners": [[0,0]]*4}
    p.displays = [{"id": 1}, {"id": 2}]
    p.result = {"mesh": [[[1,2]]]}
    out = {s.key: s.status for s in software_readiness(p)}
    assert out["rig"] == "CONFIGURED_NOT_VERIFIED"
    assert out["capture"] == "CONFIGURED_NOT_VERIFIED"
    assert out["corners"] == "CONFIGURED_NOT_VERIFIED"
    assert out["calibration"] == "SOFTWARE_RESULT_PRESENT_NOT_VERIFIED"
    assert out["export"] == "OFFLINE_EXPORT_ELIGIBLE_NOT_VERIFIED"
    assert out["camera"] == "OPERATOR_TEST_REQUIRED"


def test_empty_or_invalid_metadata_does_not_appear_ready():
    p = Project()
    p.scan = {"dir": "any", "proj_size": [True, 500],
              "content_size": [640, 480], "cam_corners": [], "content_corners": []}
    p.displays = [1]
    p.result = {"mesh": []}
    out = {s.key: s.status for s in software_readiness(p)}
    assert out["capture"] == "INPUT_REQUIRED"
    assert out["corners"] == "INPUT_REQUIRED"
    assert out["calibration"] == "CALIBRATION_REQUIRED"


def test_workflow_checklist_gui_action_never_accesses_devices(monkeypatch):
    _qt()
    from PySide6.QtWidgets import QMessageBox, QPushButton
    from vclone import gui
    dialogs = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *_a, **_k: dialogs.append(_a[-1]))
    w = gui.MainWindow()
    try:
        assert any(b.text() == "Workflow Checklist"
                   for b in w.findChildren(QPushButton))
        button = next(b for b in w.findChildren(QPushButton)
                      if b.text() == "Workflow Checklist")
        button.click()
        assert len(dialogs) == 1
        assert "Camera-only preflight" in dialogs[0]
        assert "Multi-projector seam and blend" in dialogs[0]
        assert not w.session.dirty and w._camera_probe_worker is None
    finally:
        w.close()
