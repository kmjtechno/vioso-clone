"""M59: physically present ONE calibrated still to one verified extended display.

The operator explicitly selects a non-primary display and confirms twice.
Neither constructing this dialog nor inspecting screens turns on projectors,
opens cameras, changes monitor configuration, or writes image files.
This is timed still output, NOT synchronized hardware calibration evidence.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QSpinBox, QVBoxLayout,
)
import numpy as np


class ProjectorStillError(ValueError):
    """User-facing fixed failure; never contain filenames or camera credentials."""


def _rect(screen):
    rect = screen.geometry()
    if (type(rect.x()) is not int or type(rect.y()) is not int
            or abs(rect.x()) > 32768 or abs(rect.y()) > 32768
            or not 2 <= rect.width() <= 1920
            or not 2 <= rect.height() <= 1080):
        raise ProjectorStillError("selected display geometry outside bounded still output")
    return rect


def eligible_secondary_screens(screens, primary):
    """Return only distinct non-overlapping secondary Extended display screens."""
    screens = tuple(screens)
    if primary is None or not any(s is primary for s in screens):
        return []
    result = []
    for index, candidate in enumerate(screens):
        if candidate is primary:
            continue
        try:
            area = _rect(candidate)
            # Mirrored/overlapping desktop rectangles are unsafe.
            if any(area.intersects(other.geometry())
                   for other in screens if other is not candidate):
                continue
        except (ProjectorStillError, RuntimeError):
            continue
        result.append((index, candidate))
    return result


def validate_target(screen, frame, *, confirmed=False, duration_ms=5000,
                    screens=None, primary=None):
    """Reject unsafe output BEFORE any window is created or camera is opened."""
    if confirmed is not True:
        raise ProjectorStillError("explicit projector presentation consent required")
    if type(duration_ms) is not int or not 1000 <= duration_ms <= 10000:
        raise ProjectorStillError("still display duration must be 1..10 seconds")
    available = (tuple(QGuiApplication.screens()) if screens is None
                 else tuple(screens))
    principal = QGuiApplication.primaryScreen() if primary is None else primary
    eligible = eligible_secondary_screens(available, principal)
    if not any(value is screen for _, value in eligible):
        raise ProjectorStillError("selected output is not a distinct extended display")
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3
            or not frame.flags.c_contiguous):
        raise ProjectorStillError("calibrated output must be a contiguous uint8 BGR image")
    area = _rect(screen)
    if frame.shape[:2] != (area.height(), area.width()):
        raise ProjectorStillError("calibrated frame size must match selected desktop display exactly")
    return area


class ProjectorStillDialog(QDialog):
    """Display-selection/consent form; no display output until explicit Yes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Present calibrated still — operator-selected projector")
        self._screens = tuple(QGuiApplication.screens())
        self._primary = QGuiApplication.primaryScreen()
        self._choices = eligible_secondary_screens(self._screens, self._primary)
        col = QVBoxLayout(self)
        caution = QLabel(
            "One calibrated still is shown for a bounded period only.\n"
            "Select the actual physically identified extended projector.\n"
            "Never select a mirrored or primary desktop. Escape stops output.\n"
            "This does not certify optical alignment or VIOSO 7 parity.")
        caution.setWordWrap(True)
        col.addWidget(caution)
        form = QFormLayout()
        self.displays = QComboBox()
        for index, screen in self._choices:
            r = screen.geometry()
            self.displays.addItem(
                f"Extended display {index + 1} — {r.width()}x{r.height()} "
                f"at ({r.x()}, {r.y()})", index)
        if not self._choices:
            self.displays.addItem("No safe extended projector display found")
        self.displays.setEnabled(bool(self._choices))
        form.addRow("Physically identified target", self.displays)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 10)
        self.seconds.setValue(5)
        form.addRow("Output time (seconds)", self.seconds)
        col.addLayout(form)
        self.confirm = QCheckBox(
            "I verified the exact projector/Extended desktop and authorize one timed still")
        col.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(
            lambda checked: self.ok_button.setEnabled(bool(checked and self._choices)))
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)

    def _accept_selection(self):
        if not self.confirm.isChecked() or not self._choices:
            return
        screen = self.selected_screen()
        if screen is not None and any(screen is current
                                     for _, current in eligible_secondary_screens(
                                         QGuiApplication.screens(),
                                         QGuiApplication.primaryScreen())):
            self.accept()

    def selected_screen(self):
        if not self._choices:
            return None
        row = self.displays.currentIndex()
        return self._choices[row][1] if 0 <= row < len(self._choices) else None

    def values(self):
        if self.result() != QDialog.DialogCode.Accepted or not self.confirm.isChecked():
            return None
        return self.selected_screen(), self.seconds.value() * 1000


class _FrameWindow(QDialog):
    """Single-shot Qt display; no OpenCV window or monitor-control API."""

    def __init__(self, pixmap, duration_ms):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setStyleSheet("background-color: black;")
        self._label = QLabel(self)
        self._label.setPixmap(pixmap)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resize(pixmap.width(), pixmap.height())
        self._label.setGeometry(0, 0, pixmap.width(), pixmap.height())
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.accept)
        self._duration_ms = duration_ms

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start(self._duration_ms)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


def present_calibrated_still(frame, screen, *, confirmed=False, duration_ms=5000):
    """Show one safely rendered still; returns only a non-hardware-verified receipt."""
    target = validate_target(
        screen, frame, confirmed=confirmed, duration_ms=duration_ms)
    h, w = frame.shape[:2]
    image = QImage(
        frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
    if image.isNull():
        raise ProjectorStillError("calibrated still conversion failed")
    pixmap = QPixmap.fromImage(image)
    if pixmap.isNull():
        raise ProjectorStillError("calibrated still pixmap is unavailable")
    output = _FrameWindow(pixmap, duration_ms)
    try:
        output.create()
        handle = output.windowHandle()
        if handle is None:
            raise ProjectorStillError("selected display window is unavailable")
        handle.setScreen(screen)
        output.setGeometry(target)
        # Revalidate after building the hidden window to refuse hot-unplug
        # before showing content on a possibly different desktop screen.
        validate_target(screen, frame, confirmed=True, duration_ms=duration_ms)
        output.showFullScreen()
        output.exec()
    finally:
        output.close()
        output.deleteLater()
    return {
        "projector_operation": "ONE_OPERATOR_CONFIRMED_TIMED_STILL",
        "software_output": "ATTEMPTED",
        "hardware_optical_acceptance": "NOT_VERIFIED",
        "synchronization": "NOT_VERIFIED",
    }
