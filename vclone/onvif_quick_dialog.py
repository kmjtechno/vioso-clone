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
    QPushButton, QInputDialog,
)

from .camera_sources import validate_profile, SCHEMA


class OnvifQuickProbeDialog(QDialog):
    """Read-only ONVIF Media1 connection setup; no on-disk credential store."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accepted_profile = None
        self._detected_endpoint = None
        self.setWindowTitle("ONVIF Auto Detect / camera-only check")
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Connect ONE CP PLUS or compatible ONVIF camera on your private LAN.\n"
            "Projectors remain OFF. ONVIF login is optional; no passwords saved."))
        self.detect_button = QPushButton("Auto Detect ONVIF Camera (no ID/password)")
        self.detect_button.setToolTip(
            "Explicit click sends one bounded LAN multicast discovery probe; "
            "does NOT start the video stream or projector")
        self.detect_button.clicked.connect(self._discover)
        root.addWidget(self.detect_button)
        self.discovery_status = QLabel(
            "No LAN scan yet. Auto Detect, or enter the private IP manually.")
        self.discovery_status.setWordWrap(True)
        root.addWidget(self.discovery_status)
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
            ("ONVIF username (optional)", self.username),
            ("ONVIF password (optional)", self.password),
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

    def _discover(self):
        """Explicit short WS-Discovery click, not an application startup scan."""
        from .onvif_discovery import discover_cameras
        self.detect_button.setEnabled(False)
        try:
            candidates = discover_cameras()
        except Exception:
            QMessageBox.warning(
                self, "ONVIF Auto Detect",
                "No discoverable camera found. Check private LAN, UDP 3702 "
                "and Windows firewall; or enter the IP manually.")
            self.discovery_status.setText("Auto Detect unavailable; no video opened.")
            return
        finally:
            self.detect_button.setEnabled(True)
        if not candidates:
            self.discovery_status.setText(
                "No ONVIF camera answered; manual private IP still supported.")
            return
        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            # Choose ONE local endpoint; never connect to all results.
            choices = [
                "Camera " + str(i + 1) + " - " + item["host"] + ":" +
                str(item["port"]) for i, item in enumerate(candidates)
            ]
            label, approved = QInputDialog.getItem(
                self, "Select ONE ONVIF camera",
                "Cameras detected on the private LAN:", choices, 0, False)
            if not approved:
                return
            chosen = candidates[choices.index(label)]
        self._detected_endpoint = chosen.copy()
        self.host.setText(chosen["host"])
        self.scheme.setCurrentText(chosen["scheme"])
        self.port.setValue(chosen["port"])
        self.discovery_status.setText(
            "Detected ONE camera: " + chosen["host"] + ". "
            "Login optional. Confirm camera-only probe to try video.")

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
        found = self._detected_endpoint
        if (found and source["host"] == found["host"]
                and source["port"] == found["port"]
                and source["scheme"] == found["scheme"]):
            source["device_path"] = found["device_path"]
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
                "Use a private IPv4 camera and port. "
                "Provide BOTH username/password or leave BOTH empty.")
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
