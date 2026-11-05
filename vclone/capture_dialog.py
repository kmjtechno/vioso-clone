"""Opt-in camera/projector capture dialog; never starts hardware during construction."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)


def _spin(low, high, value):
    s = QSpinBox()
    s.setRange(low, high)
    s.setValue(value)
    return s


class CaptureDialog(QDialog):
    """Collect bounded capture configuration and explicit projector authorization."""

    def __init__(self, scan=None, parent=None):
        super().__init__(parent)
        scan = scan or {}
        self.setWindowTitle("Capture Gray-code from camera and projector")
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Use an extended-desktop projector; verify its actual X/Y position."))
        form = QFormLayout()
        root.addLayout(form)
        self.output = QLineEdit()
        self.output.setPlaceholderText("New capture folder; it must not exist")
        browse = QPushButton("Choose parent folder...")
        choose = QHBoxLayout()
        choose.addWidget(self.output)
        choose.addWidget(browse)
        form.addRow("New capture folder", choose)
        browse.clicked.connect(self._browse)

        proj = scan.get("proj_size", [640, 480])
        content = scan.get("content_size", [1920, 1080])
        if not isinstance(proj, (tuple, list)) or len(proj) != 2:
            proj = [640, 480]
        if not isinstance(content, (tuple, list)) or len(content) != 2:
            content = [1920, 1080]
        self.pw = _spin(2, 1920, int(proj[0]))
        self.ph = _spin(2, 1080, int(proj[1]))
        self.cw = _spin(2, 4096, int(content[0]))
        self.ch = _spin(2, 2160, int(content[1]))
        self.camera = _spin(0, 15, 0)
        self._camera_profile_path = None
        self.use_profile = QCheckBox(
            "Use ONE private camera source profile (ONVIF / RTSP / fisheye / USB / replay)")
        self.profile_button = QPushButton("Select private camera profile...")
        self.profile_button.setEnabled(False)
        self.profile_label = QLabel("No private camera profile selected")
        self.use_profile.toggled.connect(self.profile_button.setEnabled)
        self.use_profile.toggled.connect(lambda enabled: self.camera.setEnabled(not enabled))
        self.profile_button.clicked.connect(self._browse_profile)
        self.x = _spin(-32768, 32768, 0)
        self.y = _spin(-32768, 32768, 0)
        self.settle = _spin(1, 10000, 250)
        self.warmup = _spin(0, 30, 2)
        for label, field in (
            ("Projector width", self.pw), ("Projector height", self.ph),
            ("Content width", self.cw), ("Content height", self.ch),
            ("Camera index", self.camera), ("Projector X", self.x),
            ("Projector Y", self.y), ("Settle per frame (ms)", self.settle),
            ("Discard camera frames per pattern", self.warmup),
        ):
            form.addRow(label, field)

        form.addRow("Camera source mode", self.use_profile)
        form.addRow("Select existing private profile", self.profile_button)
        form.addRow("Selected profile status", self.profile_label)

        self.confirm = QCheckBox(
            "I verified the physical projector and X/Y; start camera/output only after OK")
        root.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(self.ok_button.setEnabled)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self):
        parent = QFileDialog.getExistingDirectory(self, "Choose capture parent folder")
        if parent:
            self.output.setText(str(Path(parent) / "new-vclone-capture"))

    def _browse_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose ONE owner-managed PRIVATE camera profile",
            "", "Camera source JSON (*.json)")
        if path:
            # Never display a private network source, password or local path.
            # No network or camera is accessed by selecting this file.
            self._camera_profile_path = path
            self.profile_label.setText("One private profile selected; OFFLINE validation on OK")

    def selected_camera_profile(self):
        """Only selected local file path, never persisted in project/log."""
        return self._camera_profile_path if self.use_profile.isChecked() else None

    def _validate_and_accept(self):
        if not self.confirm.isChecked():
            return
        output = Path(self.output.text().strip())
        if (not self.output.text().strip() or output.exists() or output.is_symlink()
                or not output.parent.is_dir() or output.parent.is_symlink()):
            QMessageBox.warning(
                self, "Capture refused", "Choose a NEW directory under an existing regular folder.")
            return
        if self.use_profile.isChecked():
            if not self._camera_profile_path:
                QMessageBox.warning(
                    self, "Capture refused", "Select a private camera profile first.")
                return
            from .camera_sources import read_profile
            try:
                read_profile(self._camera_profile_path)  # OFFLINE; no camera call
            except (OSError, ValueError, TypeError):
                QMessageBox.warning(
                    self, "Capture refused",
                    "Private camera profile failed offline validation.")
                return
        self.accept()

    def values(self):
        return (
            self.output.text().strip(),
            [self.pw.value(), self.ph.value()],
            [self.cw.value(), self.ch.value()],
            self.camera.value(), self.x.value(), self.y.value(),
            self.settle.value(), self.warmup.value(), self.confirm.isChecked(),
        )
