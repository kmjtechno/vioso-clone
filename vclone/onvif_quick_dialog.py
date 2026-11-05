"""M49 owner-operated ONVIF camera-only quick probe with NO secret file.

The dialog collects exactly one private-LAN endpoint and ONVIF account in
memory, validates offline, then requires explicit confirmation before any
network/camera access. Credentials never appear in GUI reports or project
persistence. Neither camera nor projectors are contacted during construction.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout,
)

from .camera_sources import validate_profile, SCHEMA


class OnvifQuickProbeDialog(QDialog):
    """Read-only ONVIF Media1 connection setup; no on-disk credential store."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted_profile = None
        self.setWindowTitle("ONVIF camera-only check — private credentials")
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Connect ONE CP PLUS or compatible ONVIF camera on your private LAN.\n"
            "Projectors remain OFF. No camera settings or passwords are saved."))
        form = QFormLayout()
        root.addLayout(form)
        self.host = QLineEdit()
        self.host.setPlaceholderText("Private IPv4 camera address, e.g. 192.168.1.50")
        self.host.setMaxLength(64)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(80)
        self.scheme = QComboBox()
        self.scheme.addItems(["http", "https"])
        self.scheme.currentTextChanged.connect(self._scheme_changed)
        self.username = QLineEdit()
        self.username.setMaxLength(128)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMaxLength(512)
        self.token = QLineEdit()
        self.token.setPlaceholderText("Optional exact profile token; blank = unique largest square")
        self.token.setMaxLength(128)
        for name, widget in (
            ("ONVIF camera IPv4", self.host),
            ("ONVIF service port", self.port),
            ("Control protocol", self.scheme),
            ("ONVIF username", self.username),
            ("ONVIF password", self.password),
            ("Optional raw fisheye profile token", self.token),
        ):
            form.addRow(name, widget)

        self.confirm = QCheckBox(
            "I authorize one camera-only ONVIF/RTSP probe (6 frames); no projectors")
        root.addWidget(self.confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.confirm.toggled.connect(self.ok_button.setEnabled)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _scheme_changed(self, scheme):
        if scheme == "https" and self.port.value() == 80:
            self.port.setValue(443)
        elif scheme == "http" and self.port.value() == 443:
            self.port.setValue(80)

    def _source_profile(self):
        source = {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "scheme": self.scheme.currentText(),
            "username": self.username.text(),
            "password": self.password.text(),
        }
        if self.token.text().strip():
            source["profile_token"] = self.token.text().strip()
        return {
            "schema": SCHEMA, "type": "onvif",
            "source": source, "backend": "ffmpeg",
        }

    def _validate_and_accept(self):
        if not self.confirm.isChecked():
            return
        try:
            data = validate_profile(self._source_profile())  # OFFLINE
        except Exception:
            # Never surface the account, password, host or backend exception.
            QMessageBox.warning(
                self, "ONVIF camera-only check",
                "Private camera details are invalid or unsupported. "
                "Use an RFC1918 IPv4 camera, valid ONVIF port and local account.")
            return
        self._accepted_profile = data
        self.password.clear()  # remove retained plaintext from Qt's input widget
        self.accept()

    def profile(self):
        if (self.result() != QDialog.DialogCode.Accepted
                or self._accepted_profile is None):
            return None
        source = self._accepted_profile["source"]
        return {**self._accepted_profile, "source": dict(source)}

    def clear_transient_profile(self):
        self._accepted_profile = None
        self.password.clear()
