"""Optional PySide6 camera-corner selection UI (no camera or projector access).

Opens only the recorded p00.png camera frame. Four mouse clicks in order
TL, TR, BR, BL set the corresponding project coordinates on confirmation.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout
)

from .corners import validate_corners, validate_size


class _ImageClickView(QGraphicsView):
    clicked = Signal(float, float)

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._size = (pixmap.width(), pixmap.height())
        scene = QGraphicsScene(self)
        scene.addPixmap(pixmap)
        scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.setScene(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumSize(600, 370)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            x, y = point.x(), point.y()
            if 0 <= x <= self._size[0] - 1 and 0 <= y <= self._size[1] - 1:
                self.clicked.emit(x, y)
                event.accept()
                return
        super().mousePressEvent(event)


class CornerPicker(QDialog):
    LABELS = ("TL", "TR", "BR", "BL")

    def __init__(self, image_path, parent=None, *, rectified_frame=None):
        super().__init__(parent)
        self.setWindowTitle("Camera corners — click TL → TR → BR → BL")
        source = Path(image_path)
        if not source.is_file() or source.is_symlink() or source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("camera reference must be a regular image under 32 MiB")
        reader = QImageReader(str(source))
        size = reader.size()
        if not size.isValid():
            raise ValueError("cannot read camera reference image size")
        self.image_size = validate_size((size.width(), size.height()))
        image = reader.read()
        if image.isNull():
            raise ValueError("cannot decode camera reference image")
        if rectified_frame is not None:
            if (not isinstance(rectified_frame, np.ndarray)
                    or rectified_frame.dtype != np.uint8
                    or rectified_frame.ndim != 2
                    or rectified_frame.shape != (self.image_size[1], self.image_size[0])
                    or not rectified_frame.flags.c_contiguous):
                raise ValueError("rectified corner frame must match camera image")
            h, w = rectified_frame.shape
            image = QImage(rectified_frame.data, w, h, rectified_frame.strides[0],
                           QImage.Format.Format_Grayscale8).copy()
            if image.isNull():
                raise ValueError("rectified camera reference unavailable")
            self.setWindowTitle(
                "RECTIFIED fisheye camera corners — TL → TR → BR → BL")
        pixmap = QPixmap.fromImage(image)
        self.points = []
        self._items = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click the screen corners in order: top-left, top-right, bottom-right, bottom-left."))
        self.view = _ImageClickView(pixmap, self)
        layout.addWidget(self.view)
        self.view.clicked.connect(self.add_point)
        self.instructions = QLabel()
        layout.addWidget(self.instructions)
        actions = QHBoxLayout()
        self.undo_button = QPushButton("Undo last point")
        self.clear_button = QPushButton("Clear all")
        actions.addWidget(self.undo_button)
        actions.addWidget(self.clear_button)
        layout.addLayout(actions)
        self.undo_button.clicked.connect(self.undo)
        self.clear_button.clicked.connect(self.clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        n = len(self.points)
        self.instructions.setText(
            f"{n}/4 points selected — " +
            (f"next: {self.LABELS[n]}" if n < 4 else "click OK to validate")
        )
        self.ok_button.setEnabled(n == 4)
        self.undo_button.setEnabled(n > 0)
        self.clear_button.setEnabled(n > 0)

    def add_point(self, x, y):
        if len(self.points) >= 4:
            return
        self.points.append([float(x), float(y)])
        index = len(self.points) - 1
        marker = self.view.scene().addEllipse(x - 5, y - 5, 10, 10,
                                              QPen(QColor("red"), 2), QBrush(QColor("yellow")))
        label = self.view.scene().addText(self.LABELS[index])
        label.setDefaultTextColor(QColor("yellow"))
        label.setPos(x + 6, y - 20)
        self._items.append((marker, label))
        self._refresh()

    def undo(self):
        if self.points:
            self.points.pop()
            for item in self._items.pop():
                self.view.scene().removeItem(item)
            self._refresh()

    def clear(self):
        while self.points:
            self.undo()

    def _confirm(self):
        try:
            self.points = validate_corners(self.points, self.image_size)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid camera corners", str(exc))
            return
        self.accept()


class ScanSetupDialog(QDialog):
    """Non-destructive scan directory and projector/content dimensions editor."""

    def __init__(self, scan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibration capture setup")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.directory = QLineEdit(str(scan.get("dir", "")))
        browse = QPushButton("Browse…")
        choose_row = QHBoxLayout()
        choose_row.addWidget(self.directory)
        choose_row.addWidget(browse)
        form.addRow("Capture directory", choose_row)
        browse.clicked.connect(self._browse)

        pw, ph = scan.get("proj_size", [640, 480])
        cw, ch = scan.get("content_size", [1920, 1080])
        self.projector_width = QSpinBox()
        self.projector_width.setRange(2, 1920)
        self.projector_width.setValue(pw)
        self.projector_height = QSpinBox()
        self.projector_height.setRange(2, 1080)
        self.projector_height.setValue(ph)
        self.content_width = QSpinBox()
        self.content_width.setRange(2, 4096)
        self.content_width.setValue(cw)
        self.content_height = QSpinBox()
        self.content_height.setRange(2, 2160)
        self.content_height.setValue(ch)
        for text, field in (
            ("Projector width", self.projector_width),
            ("Projector height", self.projector_height),
            ("Content width", self.content_width),
            ("Content height", self.content_height),
        ):
            form.addRow(text, field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Capture folder", self.directory.text())
        if path:
            self.directory.setText(path)

    def values(self):
        return (self.directory.text().strip(),
                [self.projector_width.value(), self.projector_height.value()],
                [self.content_width.value(), self.content_height.value()])
