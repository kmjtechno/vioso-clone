"""M61: operator-controlled, software-only warp mesh refinement in Studio.

Selected observed mesh nodes can be adjusted by bounded content-space
pixel offsets. A detached copy is held until the owner presses Save; cancel
never alters project state. No camera, projector, network or file access.
"""
from __future__ import annotations

from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFormLayout, QGraphicsItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


class MeshEditorError(ValueError):
    pass


def _node(value):
    if (value is None or isinstance(value, (list, tuple)) and len(value) == 2
            and value[0] is None and value[1] is None):
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(x) not in (int, float) for x in value)):
        raise MeshEditorError("invalid calibrated mesh node")
    pair = [float(value[0]), float(value[1])]
    if not all(math.isfinite(x) for x in pair):
        raise MeshEditorError("non-finite calibrated mesh node")
    return pair


class MeshEditorDialog(QDialog):
    """Select nodes visually, apply finite ±64 px deltas, save explicitly."""

    def __init__(self, mesh, content_size, parent=None):
        super().__init__(parent)
        if (not isinstance(mesh, list) or not 2 <= len(mesh) <= 65
                or not isinstance(mesh[0], list) or not 2 <= len(mesh[0]) <= 65):
            raise MeshEditorError("a bounded calibrated mesh is required")
        if (not isinstance(content_size, (list, tuple)) or len(content_size) != 2
                or any(type(v) is not int or not 1 <= v <= 4096
                       for v in content_size)):
            raise MeshEditorError("content space dimensions invalid")
        cols = len(mesh[0])
        self._original = []
        for row in mesh:
            if not isinstance(row, list) or len(row) != cols:
                raise MeshEditorError("calibrated warp grid must be rectangular")
            self._original.append([_node(n) for n in row])
        self._working = deepcopy(self._original)
        self._size = tuple(content_size)
        self._selected = None
        self._node_items = {}
        self.setWindowTitle("Manual Warp Mesh Refinement — clone project only")
        self.resize(980, 630)
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel(
            "Select an observed cyan warp node. Apply small content-space X/Y "
            "offsets and inspect the wireframe before Save. "
            "All changes are local software edits; no projector output."))
        contents = QHBoxLayout()
        outer.addLayout(contents, 1)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 760, 490)
        self.scene.selectionChanged.connect(self._on_selected)
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumWidth(580)
        self.view.setRenderHint(self.view.renderHints().__class__.Antialiasing, True)
        contents.addWidget(self.view, 1)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        self.selected_label = QLabel("Select one observed control point")
        self.selected_label.setWordWrap(True)
        side.addWidget(self.selected_label)
        form = QFormLayout()
        self.dx = QDoubleSpinBox()
        self.dy = QDoubleSpinBox()
        for spin in (self.dx, self.dy):
            spin.setRange(-64.0, 64.0)
            spin.setSingleStep(0.5)
            spin.setDecimals(2)
            spin.setEnabled(False)
        form.addRow("ΔX content pixels", self.dx)
        form.addRow("ΔY content pixels", self.dy)
        side.addLayout(form)
        self.apply_button = QPushButton("Apply node adjustment")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_node)
        side.addWidget(self.apply_button)
        side.addWidget(QLabel(
            "Maximum total offset per node: 64 px on each axis. "
            "Unobserved (empty) warp nodes cannot be created."))
        side.addStretch(1)
        contents.addWidget(sidebar)
        row = QHBoxLayout()
        self.save_button = QPushButton("Save reviewed mesh corrections")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        row.addWidget(self.save_button)
        cancel = QPushButton("Cancel — discard changes")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        outer.addLayout(row)
        self._draw()

    def _position(self, node):
        x, y = node
        return (20 + 720 * (x - self._minimum_x) / self._span_x,
                20 + 450 * (y - self._minimum_y) / self._span_y)

    def _draw(self, selected=None):
        self.scene.blockSignals(True)
        try:
            self.scene.clear()
            self._node_items.clear()
            cw, ch = self._size
            coords = [value for row in self._working for value in row
                      if value is not None]
            if not coords:
                return
            self._minimum_x = min(0.0, min(n[0] for n in coords))
            self._minimum_y = min(0.0, min(n[1] for n in coords))
            xmax = max(float(cw), max(n[0] for n in coords))
            ymax = max(float(ch), max(n[1] for n in coords))
            self._span_x = max(1.0, xmax - self._minimum_x)
            self._span_y = max(1.0, ymax - self._minimum_y)
            line_pen = QPen(QColor("#315d79"))
            dot_pen = QPen(QColor("#86e4d6"))
            for i, row in enumerate(self._working):
                for j, node in enumerate(row):
                    if node is None:
                        continue
                    x1, y1 = self._position(node)
                    for ni, nj in ((i+1, j), (i, j+1)):
                        if (ni < len(self._working)
                                and nj < len(self._working[ni])
                                and self._working[ni][nj] is not None):
                            x2, y2 = self._position(self._working[ni][nj])
                            self.scene.addLine(x1, y1, x2, y2, line_pen)
                    marker = self.scene.addEllipse(
                        x1 - 5, y1 - 5, 10, 10, dot_pen, QBrush(QColor("#3fc8b0")))
                    marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    marker.setData(0, (i, j))
                    marker.setToolTip(f"Node {i},{j}; content ({node[0]:.2f},{node[1]:.2f})")
                    self._node_items[(i, j)] = marker
            if selected in self._node_items:
                self._node_items[selected].setSelected(True)
        finally:
            self.scene.blockSignals(False)
        if selected is not None:
            self._set_selected(selected)

    def _set_selected(self, item):
        self._selected = item if item in self._node_items else None
        if self._selected is None:
            self.selected_label.setText("Select one observed control point")
        else:
            i, j = self._selected
            x, y = self._working[i][j]
            self.selected_label.setText(
                f"Node row {i}, column {j}\nContent X={x:.2f}, Y={y:.2f}")
        for spin in (self.dx, self.dy):
            spin.setValue(0.0)
            spin.setEnabled(self._selected is not None)
        self.apply_button.setEnabled(self._selected is not None)

    def _on_selected(self):
        selected = self.scene.selectedItems()
        self._set_selected(selected[0].data(0) if selected else None)

    def apply_node(self):
        if self._selected not in self._node_items:
            return
        i, j = self._selected
        base, current = self._original[i][j], self._working[i][j]
        if base is None or current is None:
            return
        desired = [current[0] + self.dx.value(),
                   current[1] + self.dy.value()]
        if (not all(math.isfinite(v) for v in desired)
                or abs(desired[0] - base[0]) > 64
                or abs(desired[1] - base[1]) > 64):
            QMessageBox.warning(
                self, "Manual mesh", "Node offset exceeds 64 px total per axis.")
            return
        self._working[i][j] = desired
        self._draw(selected=(i, j))
        self.save_button.setEnabled(self._working != self._original)

    def _save(self):
        if self._working != self._original:
            self.accept()

    def values(self):
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        return deepcopy(self._working)
