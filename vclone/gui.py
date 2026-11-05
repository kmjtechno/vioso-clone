"""Thin PySide6 front end over gui_model.Session. PySide6 is imported lazily by main()."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .gui_model import Session, SessionError
from .corner_editor import CornerPicker, ScanSetupDialog
from .capture_dialog import CaptureDialog
from .onvif_quick_dialog import OnvifQuickProbeDialog
from .ui_shell import build_studio


class CameraProbeWorker(QThread):
    """Only the explicitly selected camera is opened, outside the UI thread."""

    report_ready = Signal(dict)
    preview_ready = Signal(QImage)
    failed = Signal(str)

    def __init__(self, private_profile, parent=None):
        super().__init__(parent)
        # Preserve one-shot ONVIF credentials in memory only, never render a
        # dictionary as its string representation or persist it in project log.
        self._private_profile = (dict(private_profile)
                                 if isinstance(private_profile, dict)
                                 else str(private_profile))
        self.preview_enabled = False

    def run(self):
        from .camera_frame_probe import CameraProbeError, camera_frame_probe

        try:
            if self.preview_enabled:
                receipt, thumbnail = camera_frame_probe(
                    self._private_profile, confirmed=True, frames=6,
                    warmup=1, return_preview=True)
                height, width = thumbnail.shape
                frame_image = QImage(
                    thumbnail.data, width, height, thumbnail.strides[0],
                    QImage.Format.Format_Grayscale8).copy()
            else:
                receipt = camera_frame_probe(
                    self._private_profile, confirmed=True, frames=6, warmup=1)
                frame_image = None
        except CameraProbeError as exc:
            # Exception contents, native URLs, account/credentials and host
            # must never traverse Qt threads. Only an allowlisted fixed code.
            self.failed.emit("failed: " + exc.code)
            return
        except Exception:
            self.failed.emit("failed: CAMERA_PROBE_FAILED")
            return
        self.report_ready.emit(receipt)
        if frame_image is not None and not frame_image.isNull():
            self.preview_ready.emit(frame_image)


class MainWindow(QMainWindow):
    def __init__(self, session=None):
        super().__init__()
        self.session = session or Session()
        # M51: premium dark UI shell; calibrated functionality stays in Session.
        build_studio(self)
        m = self.menuBar().addMenu("&File")
        m.addAction("&Open...", self.open_project)
        m.addAction("&Save", self.save_project)
        m.addAction("Save &As...", self.save_project_as)
        m.addAction("&Quit", self.close)
        calib_menu = self.menuBar().addMenu("&Calibration")
        calib_menu.addAction("&Setup capture folder and dimensions...", self.setup_scan)
        calib_menu.addAction("&Capture Gray-code from camera...", self.capture_camera)
        calib_menu.addAction("&Select camera corners...", self.select_corners)
        calib_menu.addAction("&Preview calibrated content (CPU)...", self.preview_content)
        calib_menu.addAction("Compare two-projector seam (offline)...", self.compare_two_projectors)
        calib_menu.addSeparator()
        calib_menu.addAction("Check camera profile (offline)...", self.check_camera_profile)
        calib_menu.addAction("Check Windows projector rig (read-only)...", self.check_display_rig)
        calib_menu.addAction("Probe selected camera (explicit consent)...", self.probe_selected_camera)
        calib_menu.addAction("Connect ONVIF camera (no saved credentials)...",
                             self.probe_onvif_camera_once)
        self.refresh()

    def refresh(self):
        s = self.session
        self.setWindowTitle(
            f"VIOSO Clone - {s.project.name}{' *' if s.dirty else ''} "
            "[M55 camera diagnostics · unsigned alpha]")
        self.log_view.setPlainText("\n".join(s.log))
        # A selected folder is not a calibrated rig, never display hardware PASS.
        if s.project.scan.get("dir"):
            self.scan_status_label.setText("CAPTURE FOLDER SELECTED")
        else:
            self.scan_status_label.setText("NOT VERIFIED")

    def _guard(self, fn, *a):
        try:
            fn(*a)
        except (SessionError, ValueError, OSError) as e:
            QMessageBox.warning(self, "VIOSO Clone", str(e))
        self.refresh()

    def clear_preview(self):
        """Drop stale previews whenever project calibration or identity may change."""
        self._preview_frame = None
        self.preview_export_button.setEnabled(False)
        self.preview_label.clear()
        self.preview_label.setText(
            "NO CALIBRATION PREVIEW\n\n"
            "CPU preview: choose Calibration > Preview calibrated content.")

    def run_step(self, name):
        self.clear_preview()
        self._guard(self.session.run, name)

    def open_project(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Project (*.json)")
        if f:
            self.clear_preview()
            self._guard(self.session.open, f)

    def save_project(self):
        if self.session.path is None:
            return self.save_project_as()
        self._guard(self.session.save)

    def save_project_as(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save project", "", "Project (*.json)")
        if f:
            self._guard(self.session.save, f)


    def setup_scan(self):
        dialog = ScanSetupDialog(self.session.project.scan, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            directory, projector_size, content_size = dialog.values()
            self.clear_preview()
            self._guard(self.session.configure_scan, directory, projector_size, content_size)

    def capture_camera(self):
        dialog = CaptureDialog(self.session.project.scan, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.clear_preview()
            # The dialog's existing positional arguments stay unchanged; the
            # selected private profile is supplied only for this confirmed run.
            # It is never serialized into the project or GUI log.
            self._guard(self.session.capture_camera_scan, *dialog.values(),
                        dialog.selected_camera_profile())

    def preview_content(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose local content image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            frame = self.session.preview_content(path)
            h, w = frame.shape[:2]
            image = QImage(
                frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
            if image.isNull():
                raise ValueError("could not display rendered preview")
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                raise ValueError("could not create preview pixmap")
            self.preview_label.setPixmap(
                pixmap.scaled(880, 500, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation))
            self._preview_frame = frame
            self.preview_export_button.setEnabled(True)
        except (SessionError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "VIOSO Clone", str(exc))
        self.refresh()

    def save_preview_png(self):
        if self._preview_frame is None:
            QMessageBox.warning(self, "VIOSO Clone", "Render a calibrated CPU preview first.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Save NEW CPU preview", "", "PNG image (*.png)")
        if not target:
            return
        self._guard(self.session.save_preview_png, self._preview_frame, target)

    def check_camera_profile(self):
        """Explicit file selection: validate credentials locally, never open camera."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose private camera source profile for OFFLINE validation",
            "", "Camera source JSON (*.json)")
        if not path:
            return
        try:
            report = self.session.inspect_camera_profile(path)
            QMessageBox.information(
                self, "Offline camera profile",
                f"Source type: {report['camera_type']}\n"
                f"Capture backend: {report['capture_backend']}\n"
                f"Profile validation: {report['source_validation']}\n"
                "Camera connection: NOT TESTED\n"
                "Physical optical acceptance: NOT VERIFIED\n"
                "No camera, network or projector was accessed.")
        except (SessionError, ValueError, OSError):
            # Do not display private path, stream URL or backend exceptions.
            QMessageBox.warning(
                self, "Offline camera profile", "Camera profile validation refused.")
        self.refresh()

    def check_display_rig(self):
        """Read only the local Windows display layout; no projector switch-on."""
        try:
            report = self.session.inspect_rig(expected_projectors=2)
            lines = [
                f"Desktop layout gate: {report['display_layout_gate']}",
                f"Desktop displays found: {report['desktop_displays_found']}",
                "Expected projectors: 2 (operator mapping required)",
                "Projector power/identity: NOT VERIFIED",
                "Physical optical acceptance: NOT VERIFIED",
                "Read-only screen rectangles:",
            ]
            for screen in report["desktop_rectangles"]:
                lines.append(
                    f"  #{screen['display_index']}: "
                    f"({screen['x']}, {screen['y']}) "
                    f"{screen['width']}x{screen['height']}"
                    + (" [primary]" if screen["primary"] else "")
                )
            lines.append("No camera or projector was started.")
            message = "\n".join(lines)
            if report["display_layout_gate"] == "OPERATOR_MAPPING_REQUIRED":
                self.display_status_label.setText("DETECTED · MAPPING REQUIRED")
                QMessageBox.information(self, "Read-only projector rig", message)
            else:
                QMessageBox.warning(self, "Read-only projector rig", message)
        except (SessionError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Read-only projector rig", str(exc))
        self.refresh()

    def probe_onvif_camera_once(self):
        """Prompt for a ONE-TIME private-LAN ONVIF probe with no JSON file."""
        if self._camera_probe_worker is not None:
            QMessageBox.warning(
                self, "ONVIF camera-only check", "Another camera probe is running.")
            return
        dialog = OnvifQuickProbeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.clear_transient_profile()
            return
        profile = dialog.profile()
        dialog.clear_transient_profile()
        if not isinstance(profile, dict):
            return
        # Double confirmation: the dialog checkbox is required to enable
        # OK and this independent Yes is required to open a network socket.
        consent = QMessageBox.question(
            self, "Confirm ONE ONVIF camera",
            "Open exactly ONE selected private-LAN ONVIF camera and sample "
            "6 frames after a 1-frame warmup?\n\n"
            "No projectors will be operated. A small grayscale image is "
            "shown locally only; no image files, credentials, network "
            "URLs or source profiles will be saved.\n"
            "Camera network access occurs only after Yes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if consent != QMessageBox.StandardButton.Yes:
            return
        worker = CameraProbeWorker(profile, self)
        worker.preview_enabled = True
        self._camera_probe_worker = worker
        worker.report_ready.connect(self._camera_probe_ready)
        worker.preview_ready.connect(self._camera_preview_ready)
        worker.failed.connect(self._camera_probe_failed)
        worker.finished.connect(self._camera_probe_finished)
        self.session._note(
            "one-time ONVIF camera-only probe running; projectors untouched")
        self.refresh()
        worker.start()

    def probe_selected_camera(self):
        """Require a new affirmative click before starting exactly one camera."""
        if self._camera_probe_worker is not None:
            QMessageBox.warning(self, "Camera-only preflight", "One camera probe is already running.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose ONE owner-managed private camera source profile",
            "", "Camera source JSON (*.json)")
        if not path:
            return
        try:
            profile = self.session.inspect_camera_profile(path)
        except (SessionError, ValueError, OSError):
            QMessageBox.warning(
                self, "Camera-only preflight", "Selected camera source profile is invalid.")
            self.refresh()
            return
        consent = QMessageBox.question(
            self, "Confirm camera-only probe",
            f"Open ONLY the selected {profile['camera_type']} camera source "
            "and sample 6 frames (1 warmup)?\n\n"
            "This does not turn on projectors, display patterns, save pixels "
            "or prove optical calibration.\n"
            "Camera or network access occurs only after you choose Yes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if consent != QMessageBox.StandardButton.Yes:
            self.refresh()
            return
        worker = CameraProbeWorker(path, self)
        self._camera_probe_worker = worker
        worker.report_ready.connect(self._camera_probe_ready)
        worker.failed.connect(self._camera_probe_failed)
        worker.finished.connect(self._camera_probe_finished)
        self.session._note("camera-only frame probe running; projectors untouched")
        self.refresh()
        worker.start()

    def _camera_probe_ready(self, report):
        """Show only pre-approved aggregate camera diagnostics (no images/URIs)."""
        if (not isinstance(report, dict)
                or report.get("camera_connection") != "OPENED_AND_FRAMES_READ"):
            self._camera_probe_failed("Camera probe did not return a validated frame report.")
            return
        size = report.get("camera_size", [])
        if (not isinstance(size, (list, tuple)) or len(size) != 2
                or any(type(x) is not int or x < 1 for x in size)):
            self._camera_probe_failed("Camera frame dimensions were invalid.")
            return
        exposure = report.get("exposure_screening", "NOT_VERIFIED")
        self.session._note(
            f"camera-only source frames: {report.get('frames_observed', 0)}; "
            f"exposure={exposure}; hardware_optical_acceptance=NOT_VERIFIED")
        details = (
            "Camera connection: OPENED_AND_FRAMES_READ\n"
            f"Camera dimensions: {size[0]} x {size[1]}\n"
            f"Frames observed: {report.get('frames_observed', 0)}\n"
            f"Exposure screening: {exposure}\n"
            "Physical optical calibration: NOT VERIFIED\n"
            "Projector operation: NONE\n"
            "Camera frame pixels were not saved.")
        self.camera_status_label.setText(
            "FRAMES READ · OPTICS NOT VERIFIED")
        if exposure == "FRAME_DATA_PRESENT":
            QMessageBox.information(self, "Camera-only preflight", details)
        else:
            QMessageBox.warning(self, "Camera-only preflight", details)
        self.refresh()

    def _camera_preview_ready(self, frame_image):
        """Display one non-exportable, explicitly consented ONVIF thumbnail."""
        if (not isinstance(frame_image, QImage) or frame_image.isNull()
                or frame_image.format() != QImage.Format.Format_Grayscale8
                or not 16 <= frame_image.width() <= 320
                or not 16 <= frame_image.height() <= 240):
            return
        preview = QMessageBox(self)
        preview.setWindowTitle("Camera-only raw fisheye visual review")
        preview.setText(
            "Inspect this local grayscale camera thumbnail. Is it the "
            "original 1O circular fisheye view, rather than a dewarped "
            "panorama? Visual similarity is not optical calibration. "
            "No image was saved and no projector was operated.")
        preview.setIconPixmap(QPixmap.fromImage(frame_image).scaled(
            420, 320, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        preview.setStandardButtons(QMessageBox.StandardButton.Ok)
        preview.exec()

    def _camera_probe_failed(self, _message):
        # Only fixed, reviewed codes are shown. `_message` might be supplied
        # by a synthetic worker, native OpenCV plugin or third-party adapter.
        # Never interpolate arbitrary error text, IPs, RTSP URLs or secrets.
        from .camera_diagnostics import SCHEMA, safe_failure
        code, stage, guidance = safe_failure(_message)
        self.camera_status_label.setText("PROBE FAILED · NOT VERIFIED")
        self.session._note(
            f"camera-only frame probe failed; code={code}; "
            "hardware acceptance NOT_VERIFIED")
        QMessageBox.warning(
            self, "Camera-only preflight",
            "Selected camera could not be probed safely.\n"
            f"Failure stage: {stage}\n"
            f"Diagnostic code: {code}\n\n"
            f"{guidance}\n\n"
            f"Schema: {SCHEMA}\n"
            "No projector operation. No optical calibration was accepted.")
        self.refresh()

    def _camera_probe_finished(self):
        if self._camera_probe_worker is not None:
            # Drop one-shot source credentials before the Qt object is deleted.
            # Older path-based probes keep their legacy behavior in tests.
            if isinstance(getattr(self._camera_probe_worker, "_private_profile", None), dict):
                self._camera_probe_worker._private_profile = None
            self._camera_probe_worker.deleteLater()
            self._camera_probe_worker = None

    def closeEvent(self, event):
        worker = self._camera_probe_worker
        if worker is not None and worker.isRunning():
            QMessageBox.information(
                self, "Camera-only preflight",
                "Camera frame probe is running. Close the application after it finishes.")
            event.ignore()
            return
        super().closeEvent(event)

    def compare_two_projectors(self):
        """Show a read-only software seam report; never activate projectors."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a DIFFERENT calibrated projector project", "", "Project (*.json)")
        if not path:
            return
        try:
            report = self.session.compare_projector_seam(path)
            gate = report["software_seam_gate"]
            details = (
                f"Software gate: {gate}\n"
                f"Overlap of smaller footprint: "
                f"{100 * report['overlap_fraction_of_smaller_projector']:.1f}%\n"
                f"Combined content coverage: "
                f"{100 * report['union_coverage_fraction']:.1f}%\n"
                f"Uncovered content: {100 * report['uncovered_fraction']:.1f}%\n\n"
                "Physical optical acceptance: NOT VERIFIED\n"
                "Projector identification and synchronization: NOT VERIFIED\n"
                "No cameras or projectors were opened."
            )
            if gate == "PASS_SOFTWARE_GEOMETRY_ONLY":
                QMessageBox.information(self, "Offline two-projector check", details)
            else:
                QMessageBox.warning(self, "Offline two-projector check", details)
        except (SessionError, ValueError, TypeError, OSError) as exc:
            QMessageBox.warning(self, "Offline two-projector check", str(exc))
        self.refresh()

    def select_corners(self):
        folder = self.session.project.scan.get("dir")
        if not folder:
            QMessageBox.warning(self, "Camera corner setup", "Configure a capture folder first.")
            return
        source = Path(folder) / "p00.png"
        try:
            dialog = CornerPicker(source, self)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Camera corner setup", str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.clear_preview()
            self._guard(self.session.set_camera_corners, dialog.points, dialog.image_size)


def main(argv=None):
    app = QApplication(argv or sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()
