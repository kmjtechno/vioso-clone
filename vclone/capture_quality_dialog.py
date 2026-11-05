"""M58 read-only Gray-code capture quality GUI; no camera or projector APIs."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)


class CaptureQualityDialog(QDialog):
    """Select existing M8 camera captures; never writes a manifest or pixels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check Gray-code capture quality (offline)")
        root = QVBoxLayout(self)
        label = QLabel(
            "Inspect an existing clone Gray-code capture folder and manifest. "
            "This reads images for software quality checks only; it does not "
            "start cameras, projectors, or new captures.")
        label.setWordWrap(True)
        root.addWidget(label)
        form = QFormLayout()
        root.addLayout(form)
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Existing capture folder (must contain capture_manifest.json)")
        choose = QPushButton("Browse existing folder…")
        choose.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder)
        row.addWidget(choose)
        form.addRow("Capture folder", row)
        self.margin = QSpinBox()
        self.margin.setRange(0, 254)
        self.margin.setValue(20)
        form.addRow("Minimum Gray-code contrast", self.margin)
        self.valid_fraction = QDoubleSpinBox()
        self.valid_fraction.setRange(0.01, 1.0)
        self.valid_fraction.setDecimals(2)
        self.valid_fraction.setSingleStep(0.05)
        self.valid_fraction.setValue(0.30)
        form.addRow("Minimum reliable pixel fraction", self.valid_fraction)
        self.axis_span = QDoubleSpinBox()
        self.axis_span.setRange(0.01, 1.0)
        self.axis_span.setDecimals(2)
        self.axis_span.setSingleStep(0.05)
        self.axis_span.setValue(0.25)
        form.addRow("Minimum projector axis span", self.axis_span)
        self.mask = QLineEdit()
        self.mask.setPlaceholderText("Optional grayscale camera mask basename")
        self.fisheye = QLineEdit()
        self.fisheye.setPlaceholderText("Optional fisheye profile JSON basename")
        form.addRow("Camera mask (optional, in capture folder)", self.mask)
        form.addRow("Fisheye rectification (optional, in capture folder)", self.fisheye)
        self.confirm = QCheckBox(
            "Run READ-ONLY quality screening on this selected capture folder")
        root.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(self.ok_button.setEnabled)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select existing Gray-code camera capture")
        if path:
            self.folder.setText(path)

    @staticmethod
    def _optional_basename(folder, name, extension):
        if not name:
            return None
        if (len(name) > 128 or name in (".", "..")
                or Path(name).name != name
                or "/" in name or "\\" in name
                or not name.lower().endswith(extension)):
            raise ValueError("unsafe optional capture file")
        target = folder / name
        if target.is_symlink() or not target.is_file():
            raise ValueError("optional capture file missing")
        return str(target)

    def _validate(self):
        if not self.confirm.isChecked():
            return
        try:
            raw = self.folder.text().strip()
            p = Path(raw)
            if (not raw or not p.is_absolute() or p.is_symlink()
                    or not p.is_dir() or not (p / "capture_manifest.json").is_file()
                    or (p / "capture_manifest.json").is_symlink()):
                raise ValueError("capture directory invalid")
            self._optional_basename(p, self.mask.text().strip(), ".png")
            self._optional_basename(p, self.fisheye.text().strip(), ".json")
        except (ValueError, OSError):
            QMessageBox.warning(
                self, "Capture quality check refused",
                "Choose a regular existing capture directory with a manifest "
                "and optional PNG mask/JSON fisheye profile in that same folder. "
                "No camera or projector was used.")
            return
        self.accept()

    def values(self):
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        folder = Path(self.folder.text().strip())
        return {
            "directory": str(folder),
            "margin": self.margin.value(),
            "min_valid_fraction": self.valid_fraction.value(),
            "min_axis_span": self.axis_span.value(),
            "camera_mask": self._optional_basename(
                folder, self.mask.text().strip(), ".png"),
            "fisheye_profile": self._optional_basename(
                folder, self.fisheye.text().strip(), ".json"),
        }
