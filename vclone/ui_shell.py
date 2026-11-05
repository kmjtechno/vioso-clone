"""M51 premium independent calibration workspace shell for PySide6.

Pure UI construction only: no camera, projector or file-system operations.
Every action delegates to existing MainWindow methods and retains legacy
menu names, step_buttons, log_view and preview_label for test compatibility.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

DARK_THEME = """
QMainWindow, QWidget#StudioRoot {
    background-color: #0B111C;
    color: #E7EEF9;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 12px;
}
QFrame#StudioSidebar {
    background-color: #111C2C;
    border-right: 1px solid #26374E;
}
QLabel#Brand {
    font-size: 23px;
    font-weight: 800;
    color: #F6FAFF;
    letter-spacing: 1px;
}
QLabel#BrandCaption, QLabel#SectionHeading {
    font-size: 10px;
    font-weight: 700;
    color: #8294AE;
    letter-spacing: 1.3px;
}
QLabel#Hero {
    font-size: 25px;
    font-weight: 700;
    color: #F7FAFF;
}
QLabel#Subtitle, QLabel#Muted, QLabel#FooterLabel {
    color: #8EA1B9;
    font-size: 12px;
}
QLabel#AlphaTag {
    color: #F8D08E;
    background-color: #47371E;
    padding: 6px 10px;
    border: 1px solid #68502E;
    border-radius: 7px;
    font-weight: 700;
}
QFrame#StatusCard, QFrame#Canvas, QFrame#ActivityCard {
    background-color: #141F30;
    border: 1px solid #2B3D55;
    border-radius: 12px;
}
QLabel#CardHeading {
    font-size: 10px;
    font-weight: 700;
    color: #829DB8;
}
QLabel#CardValue {
    color: #E5EFFD;
    font-size: 13px;
    font-weight: 700;
}
QLabel#CanvasTitle {
    color: #ECF5FF;
    font-size: 17px;
    font-weight: 700;
}
QLabel#PreviewContent {
    color: #91A8C5;
    padding: 18px;
    font-size: 14px;
}
QPushButton#StepButton {
    text-align: left;
    padding: 11px 12px;
    background: transparent;
    border: 1px solid transparent;
    color: #D2DFF0;
    border-radius: 8px;
    min-height: 20px;
}
QPushButton#StepButton:hover:enabled {
    background-color: #1C3049;
    border-color: #345777;
}
QPushButton#StepButton:disabled {
    color: #677991;
}
QPushButton#PrimaryAction {
    color: #07151E;
    font-weight: 700;
    background-color: #4EDBBE;
    border: 1px solid #65E8CB;
    border-radius: 8px;
    min-height: 32px;
    padding: 5px 13px;
}
QPushButton#PrimaryAction:hover:enabled {
    background-color: #88F4D8;
}
QPushButton#SecondaryAction, QPushButton#ExportButton {
    color: #E3EDFC;
    font-weight: 600;
    background-color: #1D2C42;
    border: 1px solid #3C526C;
    border-radius: 8px;
    min-height: 32px;
    padding: 5px 13px;
}
QPushButton#SecondaryAction:hover:enabled,
QPushButton#ExportButton:hover:enabled {
    background-color: #293F5B;
    border-color: #5B7596;
}
QPushButton:disabled {
    color: #6C7D92;
    background-color: #1C293C;
    border-color: #27384C;
}
QPlainTextEdit#ActivityLog {
    color: #B5C8E3;
    background-color: #0E1725;
    border: 0px;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #2D6E7D;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 11px;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: 0px;
}
QMenuBar {
    background-color: #101B2B;
    color: #DAE6F7;
    border-bottom: 1px solid #26374E;
    padding: 3px 6px;
}
QMenuBar::item { padding: 6px 12px; border-radius: 5px; }
QMenuBar::item:selected { background-color: #2B4562; }
QMenu {
    background-color: #16243A;
    color: #E7EEF9;
    border: 1px solid #38506E;
    padding: 5px;
}
QMenu::item { padding: 8px 25px; border-radius: 5px; }
QMenu::item:selected { background-color: #28536B; }
QMenu::separator {
    height: 1px;
    background: #344862;
    margin: 5px 8px;
}
QToolTip { background: #1A2C40; color: #ECF8FF; border: 1px solid #50768B; }
QMessageBox, QDialog { background-color: #142136; color: #F2F7FF; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #192A40;
    border: 1px solid #496078;
    color: #EDF5FF;
    border-radius: 6px;
    padding: 5px;
}
QCheckBox { color: #E6F1FF; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
"""


def _label(value, name=None):
    widget = QLabel(value)
    if name is not None:
        widget.setObjectName(name)
    return widget


def _card(title, initial):
    frame = QFrame()
    frame.setObjectName("StatusCard")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(15, 13, 15, 12)
    lay.setSpacing(6)
    lay.addWidget(_label(title, "CardHeading"))
    status = _label(initial, "CardValue")
    status.setWordWrap(True)
    lay.addWidget(status)
    return frame, status


def _action(caption, callback, *, primary=False, tip=None):
    button = QPushButton(caption)
    button.setObjectName("PrimaryAction" if primary else "SecondaryAction")
    button.setAccessibleName(caption)
    if tip:
        button.setToolTip(tip)
    button.clicked.connect(callback)
    return button


def build_studio(window):
    """Replace placeholder gray form with a real workflow/navigation shell.

    No fake device state: status cards start NOT VERIFIED/NOT TESTED, not PASS.
    """
    window.resize(1360, 840)
    window.setMinimumSize(1000, 660)
    window.setStyleSheet(DARK_THEME)
    root = QWidget()
    root.setObjectName("StudioRoot")
    window.setCentralWidget(root)
    shell = QHBoxLayout(root)
    shell.setContentsMargins(0, 0, 0, 0)
    shell.setSpacing(0)

    side = QFrame()
    side.setObjectName("StudioSidebar")
    side.setFixedWidth(235)
    shell.addWidget(side)
    side_col = QVBoxLayout(side)
    side_col.setContentsMargins(16, 20, 16, 17)
    side_col.setSpacing(7)
    side_col.addWidget(_label("KMJ  /  VIOSO", "Brand"))
    side_col.addWidget(_label("CALIBRATION STUDIO  •  ALPHA", "BrandCaption"))
    spacer = _label("WORKSPACE", "SectionHeading")
    spacer.setContentsMargins(1, 27, 0, 8)
    side_col.addWidget(spacer)

    nav_scroll = QScrollArea()
    nav_scroll.setWidgetResizable(True)
    nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    nav_container = QWidget()
    nav = QVBoxLayout(nav_container)
    nav.setContentsMargins(0, 0, 0, 0)
    nav.setSpacing(5)
    window.step_buttons = []
    for name, available in window.session.steps():
        button = QPushButton(name)
        button.setObjectName("StepButton")
        button.setEnabled(bool(available))
        button.setAccessibleName(name)
        if not available:
            button.setToolTip("Feature not available in this alpha build")
        else:
            button.setToolTip("Open this workflow step")
        button.clicked.connect(lambda _checked=False, step=name: window.run_step(step))
        nav.addWidget(button)
        window.step_buttons.append(button)
    nav.addStretch(1)
    nav_scroll.setWidget(nav_container)
    side_col.addWidget(nav_scroll, 1)
    side_col.addWidget(_action(
        "Offline Blend Export", window.export_offline_multi_blend,
        tip="Render 2–8 existing calibrated clone projects to new PNGs; never power projectors"))
    side_col.addWidget(_action(
        "Check Capture Quality", window.check_capture_quality,
        tip="Read-only existing Gray-code PNG/manifest analysis; no camera or projector"))
    side_col.addWidget(_label("DEVICE CONTROL", "SectionHeading"))
    side_col.addWidget(_label(
        "Camera and projector actions always\nrequire operator confirmation.",
        "Muted",
    ))
    side_col.addWidget(_label("UNSIGNED ALPHA  ·  LAB BUILD", "FooterLabel"))

    main = QWidget()
    main.setObjectName("StudioRoot")
    shell.addWidget(main, 1)
    col = QVBoxLayout(main)
    col.setContentsMargins(25, 22, 25, 17)
    col.setSpacing(14)

    header = QHBoxLayout()
    titles = QVBoxLayout()
    titles.setSpacing(4)
    titles.addWidget(_label("Projection Calibration", "Hero"))
    titles.addWidget(_label(
        "Camera acquisition  /  projector mapping  /  warping  /  edge blend",
        "Subtitle",
    ))
    header.addLayout(titles, 1)
    header.addWidget(_label("HARDWARE NOT VERIFIED", "AlphaTag"), 0)
    col.addLayout(header)

    statuses = QHBoxLayout()
    statuses.setSpacing(11)
    camera, window.camera_status_label = _card("CAMERA SOURCE", "NOT TESTED")
    projectors, window.display_status_label = _card(
        "PROJECTOR RIG", "NOT MAPPED")
    scan, window.scan_status_label = _card(
        "OPTICAL CALIBRATION", "NOT VERIFIED")
    statuses.addWidget(camera, 1)
    statuses.addWidget(projectors, 1)
    statuses.addWidget(scan, 1)
    col.addLayout(statuses)

    actions = QHBoxLayout()
    actions.setSpacing(9)
    actions.addWidget(_action(
        "Connect ONVIF Camera", window.probe_onvif_camera_once,
        primary=True,
        tip="Camera-only probe with two explicit confirmations; no projector output"))
    actions.addWidget(_action(
        "Check Displays", window.check_display_rig,
        tip="Read-only Windows display-layout inspection"))
    actions.addWidget(_action(
        "Capture Gray-code", window.capture_camera,
        tip="Requires an independently confirmed projector and capture directory"))
    actions.addWidget(_action(
        "Preview Content", window.preview_content,
        tip="Preview already configured calibration locally"))
    actions.addWidget(_action(
        "Workflow Checklist", window.show_workflow_checklist,
        tip="Read-only metadata and next software steps; no devices accessed"))
    actions.addStretch(1)
    col.addLayout(actions)

    canvas = QFrame()
    canvas.setObjectName("Canvas")
    canvas_col = QVBoxLayout(canvas)
    canvas_col.setContentsMargins(19, 16, 19, 14)
    canvas_col.setSpacing(7)
    canvas_col.addWidget(_label("CALIBRATION VIEWPORT", "CardHeading"))
    canvas_col.addWidget(_label("Scene & Projection Preview", "CanvasTitle"))
    window.preview_label = _label(
        "NO CALIBRATION PREVIEW\n\n"
        "1  Connect the camera       2  Check displays\n"
        "3  Capture patterns         4  Preview & refine",
        "PreviewContent",
    )
    window.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.preview_label.setMinimumHeight(200)
    window.preview_label.setWordWrap(True)
    canvas_col.addWidget(window.preview_label, 1)
    col.addWidget(canvas, 1)

    activity = QFrame()
    activity.setObjectName("ActivityCard")
    activity_col = QVBoxLayout(activity)
    activity_col.setContentsMargins(15, 12, 15, 12)
    activity_col.setSpacing(8)
    activity_col.addWidget(_label("SESSION ACTIVITY", "CardHeading"))
    window.log_view = QPlainTextEdit(readOnly=True)
    window.log_view.setObjectName("ActivityLog")
    window.log_view.setPlaceholderText(
        "No actions yet. Device tests and calibration results appear here.")
    window.log_view.setFixedHeight(110)
    activity_col.addWidget(window.log_view)
    col.addWidget(activity)

    footer = QHBoxLayout()
    footer.addWidget(_label(
        "No physical projector, optical or VIOSO 7 parity acceptance implied.",
        "FooterLabel"), 1)
    window.preview_export_button = _action(
        "Export CPU Preview as PNG…",
        window.save_preview_png,
    )
    window.preview_export_button.setObjectName("ExportButton")
    window.preview_export_button.setEnabled(False)
    footer.addWidget(window.preview_export_button)
    col.addLayout(footer)
    window._preview_frame = None
    window._camera_probe_worker = None
    window._blend_worker = None
    window._capture_check_worker = None
