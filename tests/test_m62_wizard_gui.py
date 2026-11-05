"""M62 guided wizard Qt tests: no real camera, projector or display output."""
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog, QPushButton

from vclone.project import Project
from vclone.gui_model import Session


def app():
    return QApplication.instance() or QApplication([])


def fresh():
    app()
    from vclone.gui import MainWindow
    from vclone.calibration_wizard import CalibrationWizard
    studio = MainWindow()
    wizard = CalibrationWizard(studio)
    return studio, wizard


def test_wizard_starts_with_ten_real_stages_without_hardware():
    studio, wizard = fresh()
    try:
        assert "KMJ Calibration Wizard" in wizard.windowTitle()
        assert len(wizard.nav) == 10
        assert wizard._index == 0
        assert "Project & Surface" in wizard.heading.text()
        assert "OPTICS" in wizard.nav[0].parentWidget().findChildren(
            type(wizard.heading))[-1].text() or "NOT VERIFIED" in wizard.qa_label.text()
        for index in range(10):
            wizard.goto(index)
            assert wizard._index == index
            assert wizard.heading.text().startswith(f"STEP {index + 1:02d}")
        assert not wizard.next_button.isEnabled()
        assert studio.session.dirty is False
        assert studio._camera_probe_worker is None
    finally:
        wizard.close()
        studio.close()


def test_no_blank_project_can_claim_warp_calibration():
    studio, wizard = fresh()
    try:
        wizard.goto(6)
        assert "Run strict quality check + automatic warp solve" in [
            b.text() for b in wizard.findChildren(QPushButton)
        ]
        assert "quality-gated" in wizard.stage_status("solve").lower()
        assert "NOT VERIFIED" in wizard.stage_status("export")
    finally:
        wizard.close()
        studio.close()


def test_dirty_project_new_project_is_refused_without_discard(monkeypatch):
    studio, wizard = fresh()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: warnings.append(_args[-1]))
    studio.session.project.scan["dir"] = "existing-capture-owner-data"
    studio.session.dirty = True
    before = studio.session.project
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *_a: (_ for _ in ()).throw(
                            AssertionError("prompt should not appear on dirty project")))
    try:
        wizard.create_project()
        assert warnings
        assert studio.session.project is before
        assert studio.session.dirty
    finally:
        wizard.close()
        studio.close()


def test_new_isolated_project_preserves_saved_project_file(monkeypatch, tmp_path):
    studio, wizard = fresh()
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *_a: ("Projector 2", True))
    studio.session.path = tmp_path / "projector1.json"
    old = studio.session
    try:
        wizard.create_project()
        assert studio.session is not old
        assert studio.session.project.name == "Projector 2"
        assert studio.session.project.result == {}
        assert studio.session.path is None
        assert old.path == tmp_path / "projector1.json"
        assert studio._camera_probe_worker is None
    finally:
        wizard.close()
        studio.close()


def test_wizard_refuses_blank_capture_without_starting_worker(monkeypatch):
    studio, wizard = fresh()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: warnings.append(_args[-1]))
    try:
        wizard.run_quality()
        wizard.run_solve()
        assert len(warnings) == 2
        assert wizard._task is None
        assert all("WIZARD_CAPTURE_REQUIRED" in x for x in warnings)
    finally:
        wizard.close()
        studio.close()


def test_quality_result_is_bound_to_unmodified_exact_source(monkeypatch, tmp_path):
    app()
    from vclone import wizard_engine
    from vclone.capture import capture_sequence
    from vclone.gui import MainWindow
    from vclone.calibration_wizard import CalibrationWizard
    directory = tmp_path / "capture"
    state = [None]
    capture_sequence(16, 12, directory, lambda frame: state.__setitem__(0, frame),
                     lambda: state[0])
    studio = MainWindow(session=Session(Project(
        scan={"dir": str(directory), "proj_size": [16, 12],
              "content_size": [16, 12]})))
    wizard = CalibrationWizard(studio)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a: None)
    try:
        s = studio.session.project
        receipt = wizard_engine.inspect_capture(s)
        wizard._task_kind = "quality"
        wizard._task_source = s
        wizard._task_signature = wizard_engine.project_signature(s)
        wizard._task_succeeded(receipt)
        assert wizard._quality_current()
        assert "QUALITY PASS" in wizard.stage_status("quality")
        studio.session.project.scan["content_size"] = [32, 24]
        assert not wizard._quality_current()
        assert "required" in wizard.stage_status("quality").lower()
    finally:
        wizard._task_kind = None
        wizard._task_source = None
        wizard._task_signature = None
        wizard.close()
        studio.close()


def test_rectified_corner_picker_uses_memory_frame_not_raw_for_clicks(tmp_path):
    app()
    from vclone.corner_editor import CornerPicker
    reference = tmp_path / "p00.png"
    assert cv2.imwrite(str(reference), np.zeros((64, 64), np.uint8))
    frame = np.full((64, 64), 180, np.uint8)
    picker = CornerPicker(reference, rectified_frame=frame)
    try:
        assert "RECTIFIED" in picker.windowTitle()
        assert picker.image_size == (64, 64)
        assert picker.points == []
        assert not picker.ok_button.isEnabled()
        for x, y in [(3, 3), (60, 3), (60, 60), (3, 60)]:
            picker.add_point(x, y)
        assert picker.ok_button.isEnabled()
    finally:
        picker.close()


def test_wizard_camera_and_rig_are_not_fake_hardware_passes():
    studio, wizard = fresh()
    try:
        studio.camera_status_label.setText("FRAMES READ · OPTICS NOT VERIFIED")
        studio.display_status_label.setText("DETECTED · MAPPING REQUIRED")
        assert "optics unverified" in wizard.stage_status("camera")
        assert "physical mapping required" in wizard.stage_status("rig")
        assert "NOT VERIFIED" in wizard.stage_status("blend") or (
            "Save TWO" in wizard.stage_status("blend"))
    finally:
        wizard.close()
        studio.close()
