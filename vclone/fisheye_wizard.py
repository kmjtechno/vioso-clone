"""M63 real camera lens checkerboard calibration from an owner-selected photo set.

Runs existing M32 rigorous OpenCV fisheye solver in a QThread. Writes only a
new operator-approved JSON profile in the current capture folder, never
touching any camera, projector, original photo, calibration mesh, or login.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from .fisheye_calibration import calibrate_photo_folder
from .fisheye_rectify import validate_fisheye_profile


class LensFitWorker(QThread):
    """Offline CPU-only OpenCV fit; all errors are sanitized before signal."""

    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, directory, cols, rows, square_mm, max_rms_px, parent=None):
        super().__init__(parent)
        self.inputs = (directory, cols, rows, square_mm, max_rms_px)

    def run(self):
        try:
            directory, cols, rows, square_mm, max_rms_px = self.inputs
            fitted = calibrate_photo_folder(
                directory, cols=cols, rows=rows,
                square_mm=square_mm, max_rms_px=max_rms_px)
            validate_fisheye_profile(fitted)
            self.succeeded.emit(fitted)
        except Exception:
            # The exception may contain private paths, worker frame data or
            # native OpenCV details. Never print or propagate it to the UI.
            self.failed.emit("FISHEYE_FIT_FAILED")


def validate_destination(folder, basename, photo_folder):
    """Strict target and photo metadata checks; no source frame decoding."""
    from .fisheye_calibration import _safe_photos

    root = Path(folder)
    if root.is_symlink() or root.parent.is_symlink() or not root.is_dir():
        raise ValueError("unsafe capture folder")
    manifest = root / "capture_manifest.json"
    if (manifest.is_symlink() or not manifest.is_file()
            or not 0 < manifest.stat().st_size <= 16384):
        raise ValueError("capture manifest missing")
    raw = json.loads(
        manifest.read_text(encoding="utf-8"),
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    size = raw.get("camera_size")
    if (raw.get("schema") != "kmj.graycode.capture.v1"
            or not isinstance(size, list) or len(size) != 2
            or any(type(v) is not int for v in size)
            or not 64 <= size[0] <= 4096 or not 64 <= size[1] <= 4096
            or size[0] * size[1] > 4096 * 2160):
        raise ValueError("capture camera size or schema invalid")
    if (not isinstance(basename, str) or not 6 <= len(basename) <= 128
            or basename in (".", "..") or Path(basename).name != basename
            or "/" in basename or "\\" in basename
            or not basename.lower().endswith(".json")):
        raise ValueError("new lens file must be a simple JSON basename")
    target = root / basename
    if target.exists() or target.is_symlink():
        raise ValueError("lens output must be NEW; overwrites are forbidden")
    photos = Path(photo_folder)
    if photos.is_symlink() or not photos.is_dir():
        raise ValueError("source photo folder invalid")
    # This only validates count/file metadata, not image pixels or camera.
    _safe_photos(photos)
    return target, tuple(size)


def write_new_measured_profile(target, profile, expected_camera_size):
    """Bounded exclusive-create JSON; do not update source project or overwrite."""
    model = validate_fisheye_profile(profile)
    if model["size"] != tuple(expected_camera_size):
        raise ValueError("measured lens size differs from capture camera")
    payload = (json.dumps(
        profile, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("fitted lens profile exceeds file size cap")
    path = Path(target)
    if (path.suffix.lower() != ".json" or path.exists() or path.is_symlink()
            or path.parent.is_symlink() or not path.parent.is_dir()):
        raise ValueError("lens output path changed")
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError):
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return path


class FisheyeCalibrationDialog(QDialog):
    """Owner opt-in photo -> M32 lens solve -> new JSON profile only."""

    def __init__(self, capture_folder, parent=None):
        super().__init__(parent)
        self._capture_folder = Path(capture_folder) if capture_folder else None
        self._output = None
        self._expected_size = None
        self._target = None
        self._worker = None
        self._profile_saved = False
        self.setWindowTitle("Measure Fisheye Camera Lens — Checkerboard Photos")
        self.resize(650, 420)
        root = QVBoxLayout(self)
        title = QLabel(
            "Provide 12–48 different sharp checkerboard images from the SAME "
            "camera resolution as this Gray-code capture. Aim for broad "
            "sensor coverage and varied camera/board tilt.\n"
            "This fits an independent OpenCV fisheye lens, NOT a guessed "
            "CP PLUS preset. No camera, network or projector will be started.")
        title.setWordWrap(True)
        root.addWidget(title)
        form = QFormLayout()
        root.addLayout(form)
        self.photos = QLineEdit()
        self.photos.setPlaceholderText("Select folder with 12–48 checkerboard JPG/PNG images")
        browse = QPushButton("Browse photos…")
        browse.clicked.connect(self._choose_photos)
        choose = QHBoxLayout()
        choose.addWidget(self.photos)
        choose.addWidget(browse)
        form.addRow("Checkerboard photo folder", choose)
        self.cols = QSpinBox()
        self.cols.setRange(4, 16)
        self.cols.setValue(9)
        self.rows = QSpinBox()
        self.rows.setRange(3, 12)
        self.rows.setValue(6)
        self.square = QDoubleSpinBox()
        self.square.setRange(1, 200)
        self.square.setDecimals(2)
        self.square.setValue(25.0)
        self.max_rms = QDoubleSpinBox()
        self.max_rms.setRange(0.1, 5.0)
        self.max_rms.setDecimals(2)
        self.max_rms.setValue(1.50)
        form.addRow("Checkerboard INNER columns", self.cols)
        form.addRow("Checkerboard INNER rows", self.rows)
        form.addRow("Square width (millimetres)", self.square)
        form.addRow("Max reprojection RMS (pixels)", self.max_rms)
        self.filename = QLineEdit("measured-fisheye.json")
        form.addRow("NEW profile filename (capture folder)", self.filename)
        self.confirm = QCheckBox(
            "I authorize offline lens fitting and exclusive creation of ONE new "
            "JSON profile; originals remain unchanged")
        root.addWidget(self.confirm)
        self.status_label = QLabel("NOT STARTED · physical lens QA NOT VERIFIED")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        row = QHBoxLayout()
        self.run_button = QPushButton("Measure lens from photos")
        self.run_button.clicked.connect(self.start_measurement)
        self.run_button.setEnabled(False)
        self.confirm.toggled.connect(self.run_button.setEnabled)
        row.addWidget(self.run_button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        root.addLayout(row)

    def _choose_photos(self):
        choice = QFileDialog.getExistingDirectory(
            self, "Choose 12–48 measured fisheye checkerboard images")
        if choice:
            self.photos.setText(choice)

    def start_measurement(self):
        if self._worker is not None or not self.confirm.isChecked():
            return
        if self.cols.value() * self.rows.value() > 150:
            QMessageBox.warning(
                self, "Fisheye lens fit",
                "Checkerboard has too many inner corners (maximum 150).")
            return
        try:
            self._target, self._expected_size = validate_destination(
                self._capture_folder,
                self.filename.text().strip(), self.photos.text().strip())
        except (ValueError, TypeError, OSError, UnicodeError):
            QMessageBox.warning(
                self, "Fisheye lens fit",
                "LENS_INPUT_REFUSED. Select 12–48 existing regular checkerboard "
                "photos and a NEW JSON filename inside the capture folder. "
                "Capture camera dimensions must be valid.")
            return
        self.run_button.setEnabled(False)
        self.status_label.setText(
            "FITTING OPENCV FISHEYE · read-only CPU worker; no projector output")
        worker = LensFitWorker(
            self.photos.text().strip(), self.cols.value(), self.rows.value(),
            self.square.value(), self.max_rms.value(), self)
        self._worker = worker
        worker.succeeded.connect(self._fitted)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._finished)
        worker.start()

    def _fitted(self, report):
        try:
            # A good solve needs measured size match; no output path overwrite.
            self._output = write_new_measured_profile(
                self._target, report, self._expected_size)
        except (OSError, TypeError, ValueError):
            self._failed("LENS_OUTPUT_REFUSED")
            return
        self._profile_saved = True
        self.status_label.setText(
            f"SOFTWARE FISHEYE FIT PASS · {report['views_used']} views, "
            f"RMS {report['reprojection_rms_px']:.3f} px. "
            "Saved NEW JSON, physical optics NOT VERIFIED.")

    def _failed(self, code):
        self._profile_saved = False
        self.status_label.setText(
            "FISHEYE FIT REFUSED · no verified lens profile written")
        code = code if code in ("FISHEYE_FIT_FAILED", "LENS_OUTPUT_REFUSED") else "FISHEYE_FIT_FAILED"
        QMessageBox.warning(
            self, "Fisheye lens fit", code +
            ". Check camera image dimensions, checkerboard detection, "
            "view/tilt diversity and reprojection RMS. No device was opened.")

    def _finished(self):
        if self._worker is not None:
            self._worker.inputs = None
            self._worker.deleteLater()
            self._worker = None
        if self._profile_saved:
            self.accept()
        else:
            self.run_button.setEnabled(self.confirm.isChecked())

    def values(self):
        if self.result() == QDialog.DialogCode.Accepted and self._profile_saved:
            return self._output
        return None

    def reject(self):
        if self._worker is not None:
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            event.ignore()
            return
        super().closeEvent(event)
