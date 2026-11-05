"""M57 operator-controlled, offline 2..8 projector blend export dialog.

This never opens a camera, window on a projector, or network endpoint.
Input paths remain UI-local and are never printed to session logs.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout,
)


class OfflineBlendDialog(QDialog):
    """Select 2..8 calibrated clone projects and a NEW offline output folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Offline multi-projector blend export (no projection)")
        self._project_paths = []
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Render 2–8 existing calibrated clone projects into individual PNGs "
            "with normalized overlap weights.\n"
            "No camera, physical projector or fullscreen window will start. "
            "The output folder must NOT exist.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        layout.addLayout(form)

        select = QPushButton("Select 2–8 calibrated project JSON files…")
        select.clicked.connect(self._select_projects)
        self.selected = QLabel("No projects selected")
        form.addRow("Projects", select)
        form.addRow("Selection", self.selected)

        self.content = QLineEdit()
        self.content.setPlaceholderText("Existing content image (.png / .jpg)")
        choose_image = QPushButton("Browse image…")
        choose_image.clicked.connect(self._select_content)
        image_row = QHBoxLayout()
        image_row.addWidget(self.content)
        image_row.addWidget(choose_image)
        form.addRow("Content image", image_row)

        self.output = QLineEdit()
        self.output.setPlaceholderText("New output directory under an existing folder")
        browse_parent = QPushButton("Choose parent…")
        browse_parent.clicked.connect(self._select_output_parent)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output)
        out_row.addWidget(browse_parent)
        form.addRow("New output folder", out_row)

        self.gamma = QDoubleSpinBox()
        self.gamma.setDecimals(2)
        self.gamma.setRange(0.5, 4.0)
        self.gamma.setSingleStep(0.1)
        self.gamma.setValue(2.2)
        form.addRow("Overlap blend gamma", self.gamma)

        self.confirm = QCheckBox(
            "I authorize OFFLINE rendering to a NEW folder; NO physical output")
        layout.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(self.ok_button.setEnabled)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select 2–8 existing clone calibration projects",
            "", "Clone Project JSON (*.json)")
        if paths:
            self._project_paths = list(paths)
            self.selected.setText(str(len(paths)) +
                                  " local project files selected")

    def _select_content(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select content image for OFFLINE blend",
            "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.content.setText(path)

    def _select_output_parent(self):
        parent = QFileDialog.getExistingDirectory(
            self, "Choose existing parent folder for a NEW blend export")
        if parent:
            self.output.setText(str(Path(parent) / "vclone-offline-blend-output"))

    def _validate_and_accept(self):
        if not self.confirm.isChecked():
            return
        try:
            paths = [Path(p) for p in self._project_paths]
            image = Path(self.content.text().strip())
            out = Path(self.output.text().strip())
            if (not 2 <= len(paths) <= 8
                    or len({str(p.resolve(strict=True)) for p in paths}) != len(paths)
                    or any(p.is_symlink() or not p.is_file() for p in paths)):
                raise ValueError("projects")
            if (not self.content.text().strip() or image.is_symlink()
                    or not image.is_file()
                    or image.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp")):
                raise ValueError("image")
            if (not self.output.text().strip() or not out.is_absolute()
                    or out.exists() or out.is_symlink()
                    or not out.parent.is_dir() or out.parent.is_symlink()):
                raise ValueError("output")
            if out == image.parent or out in paths:
                raise ValueError("unsafe output")
        except (OSError, ValueError, RuntimeError):
            QMessageBox.warning(
                self, "Offline export refused",
                "Select 2–8 DISTINCT existing project JSON files, one "
                "regular image and a NEW output folder under a regular parent. "
                "No file was written by this dialog.")
            return
        self.accept()

    def values(self):
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        return (
            list(self._project_paths), self.content.text().strip(),
            self.output.text().strip(), float(self.gamma.value()),
        )
