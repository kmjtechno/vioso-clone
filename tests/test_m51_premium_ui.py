"""M51 real dark workspace shell with safe, wired device actions.

Synthetic/offscreen only: never opens camera, projects patterns, or writes files.
"""
import os
from pathlib import Path

import pytest


def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window():
    _qt()
    from vclone.gui import MainWindow
    return MainWindow()


def test_shell_has_premium_dark_workspace_and_true_not_verified_states():
    from vclone.ui_shell import DARK_THEME
    assert "#0B111C" in DARK_THEME
    assert "#4EDBBE" in DARK_THEME
    assert "StepButton" in DARK_THEME
    assert "StatusCard" in DARK_THEME
    assert "PreviewContent" in DARK_THEME

    window = _window()
    try:
        assert window.centralWidget().objectName() == "StudioRoot"
        assert window.minimumWidth() >= 1000
        assert window.minimumHeight() >= 640
        assert "HARDWARE NOT VERIFIED" in [
            label.text() for label in window.findChildren(type(window.camera_status_label))
        ]
        assert window.camera_status_label.text() == "NOT TESTED"
        assert window.display_status_label.text() == "NOT MAPPED"
        assert window.scan_status_label.text() == "NOT VERIFIED"
        assert window._camera_probe_worker is None
        assert not window.session.dirty
        assert window._preview_frame is None
        assert not window.preview_export_button.isEnabled()
    finally:
        window.close()


def test_legacy_session_steps_and_menus_preserved():
    window = _window()
    try:
        original = window.session.steps()
        assert len(window.step_buttons) == len(original)
        for button, (name, available) in zip(window.step_buttons, original):
            assert button.objectName() == "StepButton"
            assert button.text() == name
            assert button.isEnabled() == bool(available)
        menus = [action.menu() for action in window.menuBar().actions()]
        assert len(menus) >= 2
        assert menus[0].title().replace("&", "") == "File"
        assert menus[1].title().replace("&", "") == "Calibration"
        names = [action.text() for action in menus[1].actions()]
        assert "Connect ONVIF camera (no saved credentials)..." in names
        assert "Check Windows projector rig (read-only)..." in names
        assert "Capture Gray-code from camera..." in names
    finally:
        window.close()


def test_primary_workflow_button_calls_real_existing_method_not_fake_stub(monkeypatch):
    _qt()
    from PySide6.QtWidgets import QPushButton
    from vclone import gui
    invoked = []
    # Patch before constructing so Qt connects the real method slot explicitly.
    for method, value in (
        ("probe_onvif_camera_once", "ONVIF"),
        ("check_display_rig", "DISPLAYS"),
        ("capture_camera", "CAPTURE"),
        ("preview_content", "PREVIEW"),
    ):
        monkeypatch.setattr(gui.MainWindow, method,
                            (lambda v: lambda self: invoked.append(v))(value))
    window = gui.MainWindow()
    try:
        buttons = {
            button.text(): button for button in window.findChildren(QPushButton)
        }
        for title, marker in (
            ("Connect ONVIF Camera", "ONVIF"),
            ("Check Displays", "DISPLAYS"),
            ("Capture Gray-code", "CAPTURE"),
            ("Preview Content", "PREVIEW"),
        ):
            assert title in buttons and buttons[title].isEnabled()
            buttons[title].click()
            assert invoked[-1] == marker
        assert len(invoked) == 4
        assert window.session.dirty is False
    finally:
        window.close()


def test_capture_folder_status_never_claims_optical_acceptance():
    window = _window()
    try:
        assert window.scan_status_label.text() == "NOT VERIFIED"
        # A folder selected in a loaded project is NOT a measured scan.
        window.session.project.scan["dir"] = "nonexistent-owner-test-folder"
        window.refresh()
        assert window.scan_status_label.text() == "CAPTURE FOLDER SELECTED"
        window.session.project.scan.pop("dir")
        window.refresh()
        assert window.scan_status_label.text() == "NOT VERIFIED"
    finally:
        window.close()


def test_camera_report_status_marks_frames_without_lying_about_optics(monkeypatch):
    _qt()
    from PySide6.QtWidgets import QMessageBox
    from vclone import gui
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_kw: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_kw: None)
    window = gui.MainWindow()
    try:
        window._camera_probe_ready({
            "camera_connection": "OPENED_AND_FRAMES_READ",
            "camera_size": [2560, 2560],
            "frames_observed": 6,
            "exposure_screening": "FRAME_DATA_PRESENT",
        })
        assert window.camera_status_label.text() == "FRAMES READ · OPTICS NOT VERIFIED"
        assert window.display_status_label.text() == "NOT MAPPED"
        window._camera_probe_failed("native backend SECRET")
        assert window.camera_status_label.text() == "PROBE FAILED · NOT VERIFIED"
        assert "SECRET" not in repr(window.session.log)
    finally:
        window.close()


def test_preview_reset_is_not_exportable_and_does_not_use_hardware():
    window = _window()
    try:
        window.clear_preview()
        assert "NO CALIBRATION PREVIEW" in window.preview_label.text()
        assert window._preview_frame is None
        assert not window.preview_export_button.isEnabled()
    finally:
        window.close()


def test_basic_shell_source_never_contains_a_fake_calibration_success():
    source = (Path(__file__).resolve().parents[1] / "vclone" /
              "ui_shell.py").read_text(encoding="utf-8")
    assert "hardware not verified" in source.lower()
    assert "window.probe_onvif_camera_once" in source
    assert "window.check_display_rig" in source
    assert "window.capture_camera" in source
    assert "window.preview_content" in source
    assert "QFrame" in source
    assert "QScrollArea" in source
