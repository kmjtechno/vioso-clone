"""Thin PySide6 front end over gui_model.Session. PySide6 is imported lazily by main()."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .gui_model import Session, SessionError
from .corner_editor import CornerPicker, ScanSetupDialog
from .capture_dialog import CaptureDialog


class MainWindow(QMainWindow):
    def __init__(self, session=None):
        super().__init__()
        self.session = session or Session()
        central = QWidget()
        self.setCentralWidget(central)
        col = QVBoxLayout(central)
        row = QHBoxLayout()
        col.addLayout(row)
        self.step_buttons = []
        for name, ok in self.session.steps():
            b = QPushButton(name)
            b.setEnabled(ok)
            if not ok:
                b.setToolTip("not implemented in the clone yet")
            b.clicked.connect(lambda _=False, n=name: self.run_step(n))
            row.addWidget(b)
            self.step_buttons.append(b)
        self.log_view = QPlainTextEdit(readOnly=True)
        col.addWidget(self.log_view)
        self.preview_label = QLabel("CPU preview: choose Calibration > Preview calibrated content")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(180)
        col.addWidget(self.preview_label)
        self._preview_frame = None
        self.preview_export_button = QPushButton("Save CPU preview as new PNG...")
        self.preview_export_button.setEnabled(False)
        self.preview_export_button.clicked.connect(self.save_preview_png)
        col.addWidget(self.preview_export_button)
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
        self.refresh()

    def refresh(self):
        s = self.session
        self.setWindowTitle(f"VIOSO Clone - {s.project.name}{' *' if s.dirty else ''}")
        self.log_view.setPlainText("\n".join(s.log))

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
        self.preview_label.setText("CPU preview: choose Calibration > Preview calibrated content")

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
            self._guard(self.session.capture_camera_scan, *dialog.values())

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
