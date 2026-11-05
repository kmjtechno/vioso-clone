"""M60: present checksum-verified 2..8 projector PNGs via the Studio GUI.

No projection during import, dialog construction, project selection or tests.
The owner must identify distinct Extended screens and confirm twice.
This reuses M14 checksum verification and M15 actual still output (not genlock).
"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QSpinBox, QVBoxLayout,
)

import numpy as np

from .multi_present import MultiDisplayError, load_verified_frames, present_multi
from .projector_still_gui import eligible_secondary_screens


class MultiStillError(ValueError):
    """Fixed safe validation message, with no owner directory or camera URI."""


def _size(frame):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3):
        raise MultiStillError("selected blend preview image is invalid")
    h, w = frame.shape[:2]
    if not 2 <= w <= 1920 or not 2 <= h <= 1080:
        raise MultiStillError("blend image outside projector output bounds")
    return w, h


def validate_mapping(sizes, targets, *, screens=None, primary=None):
    """Match every SHA-verified projector output to a distinct secondary screen."""
    if not isinstance(sizes, (list, tuple)) or not 2 <= len(sizes) <= 8:
        raise MultiStillError("multi still needs 2..8 calibrated projector images")
    if not isinstance(targets, (list, tuple)) or len(sizes) != len(targets):
        raise MultiStillError("one selected Extended screen required per projector")
    available = (tuple(QGuiApplication.screens()) if screens is None
                 else tuple(screens))
    principal = QGuiApplication.primaryScreen() if primary is None else primary
    eligible = tuple(screen for _, screen in
                     eligible_secondary_screens(available, principal))
    if len({id(screen) for screen in targets}) != len(targets):
        raise MultiStillError("projector screens must be distinct")
    origins = []
    for size, screen in zip(sizes, targets):
        if (not isinstance(size, (list, tuple)) or len(size) != 2
                or any(type(v) is not int for v in size)):
            raise MultiStillError("invalid calibrated projector dimensions")
        if not any(screen is candidate for candidate in eligible):
            raise MultiStillError("selected screen is not a distinct Extended display")
        rect = screen.geometry()
        if (rect.width(), rect.height()) != tuple(size):
            raise MultiStillError("projector PNG must exactly match its selected display")
        origins.append((rect.x(), rect.y()))
    if len(set(origins)) != len(origins):
        raise MultiStillError("duplicate projector screen position")
    return origins


class MultiStillDialog(QDialog):
    """Read-only mapping UI for 2..8 PNG outputs, never powers a device."""

    def __init__(self, sizes, parent=None):
        super().__init__(parent)
        self._sizes = tuple(tuple(s) for s in sizes)
        if not 2 <= len(self._sizes) <= 8:
            raise MultiStillError("select a verified 2..8 projector blend export")
        self._screens = tuple(QGuiApplication.screens())
        self._primary = QGuiApplication.primaryScreen()
        self._choices = eligible_secondary_screens(self._screens, self._primary)
        self.setWindowTitle("Present verified 2-projector/multi-projector blend — opt in")
        root = QVBoxLayout(self)
        caution = QLabel(
            "Choose the physical Extended desktop screen for EACH exported PNG.\n"
            "Primary/mirrored screens and wrong native output dimensions are refused.\n"
            "Both projectors must already be on and independently identified.\n"
            "This displays still images, NOT synchronized video or optical PASS.")
        caution.setWordWrap(True)
        root.addWidget(caution)
        form = QFormLayout()
        self.screen_selectors = []
        for slot, (w, h) in enumerate(self._sizes, 1):
            combo = QComboBox()
            for index, screen in self._choices:
                geometry = screen.geometry()
                if (geometry.width(), geometry.height()) == (w, h):
                    combo.addItem(
                        f"Extended screen {index + 1} / {w}x{h} "
                        f"at ({geometry.x()}, {geometry.y()})", index)
            combo.currentIndexChanged.connect(self._update_valid)
            form.addRow(f"Projector {slot} ({w}x{h})", combo)
            self.screen_selectors.append(combo)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 10)
        self.seconds.setValue(5)
        form.addRow("Output seconds", self.seconds)
        root.addLayout(form)
        self.confirm = QCheckBox(
            "I verified every projector screen and authorize ONE timed multi-display still")
        root.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(self._update_valid)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._update_valid()

    def selected_screens(self):
        if not self.screen_selectors or any(c.currentIndex() < 0 for c in self.screen_selectors):
            return None
        targets = []
        for combo in self.screen_selectors:
            candidate = next(
                (screen for index, screen in self._choices
                 if index == combo.currentData()), None)
            if candidate is None:
                return None
            targets.append(candidate)
        return targets

    def _update_valid(self, *_args):
        targets = self.selected_screens()
        valid = False
        if targets is not None:
            try:
                validate_mapping(
                    self._sizes, targets,
                    screens=QGuiApplication.screens(),
                    primary=QGuiApplication.primaryScreen())
                valid = True
            except (MultiStillError, RuntimeError):
                pass
        self.ok_button.setEnabled(bool(valid and self.confirm.isChecked()))

    def _accept_selection(self):
        self._update_valid()
        if self.ok_button.isEnabled():
            self.accept()

    def values(self):
        if self.result() != QDialog.DialogCode.Accepted or not self.confirm.isChecked():
            return None
        targets = self.selected_screens()
        if targets is None:
            return None
        # Guard again against hotplug and GUI state changes.
        validate_mapping(self._sizes, targets)
        return targets, self.seconds.value() * 1000


def load_sizes(directory):
    """Checksum-check exported preview files without starting projector output."""
    frames = load_verified_frames(directory)
    return [_size(frame) for frame in frames]


def present_verified_blend(directory, targets, *, confirmed=False, duration_ms=5000):
    """Re-validate M14 PNG hashes, selected screens and consent before output."""
    if confirmed is not True:
        raise MultiStillError("explicit multi-display physical output consent required")
    if type(duration_ms) is not int or not 1000 <= duration_ms <= 10000:
        raise MultiStillError("multi still duration must be 1..10 seconds")
    sizes = load_sizes(directory)
    origins = validate_mapping(sizes, targets)
    # M15 re-opens/re-checks manifest and all SHA-256 PNG hashes before
    # displaying OpenCV windows at these operator-confirmed Extended origins.
    receipt = present_multi(
        directory, origins, duration_ms=duration_ms, confirmed=True)
    return {
        "projectors_attempted": receipt.displays_presented,
        "escape_pressed": bool(receipt.escape_pressed),
        "hardware_optical_acceptance": "NOT_VERIFIED",
        "synchronization": "NOT_VERIFIED",
    }
