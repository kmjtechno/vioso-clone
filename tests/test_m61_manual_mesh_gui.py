"""M61 visual Qt mesh editor tests; no cameras, projection or file changes."""
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from vclone.project import Project
from vclone.gui_model import Session


def app():
    return QApplication.instance() or QApplication([])


def mesh():
    return [
        [[0.0, 0.0], [32.0, 0.0], [63.0, 0.0]],
        [[0.0, 32.0], [32.0, 32.0], [63.0, 32.0]],
        [[0.0, 63.0], [32.0, 63.0], [63.0, 63.0]],
    ]


def test_dialog_has_real_selectable_wireframe_and_cancel_discards_everything():
    app()
    from vclone.manual_mesh_editor import MeshEditorDialog
    original = mesh()
    s = Session(Project(scan={"content_size": [64, 64]},
                        result={"mesh": deepcopy(original), "coverage": 1.0}))
    d = MeshEditorDialog(s.project.result["mesh"], [64, 64])
    try:
        assert len(d._node_items) == 9
        assert not d.save_button.isEnabled()
        assert d.values() is None
        item = d._node_items[(1, 1)]
        item.setSelected(True)
        assert d._selected == (1, 1)
        d.dx.setValue(2.5)
        d.dy.setValue(-1.5)
        d.apply_button.click()
        assert d._working[1][1] == [34.5, 30.5]
        assert s.project.result["mesh"] == original
        assert d.save_button.isEnabled()
        d.reject()
        assert d.values() is None
        assert s.project.result["mesh"] == original
        assert not s.dirty
    finally:
        d.close()


def test_save_only_after_owner_accepts_and_session_still_validates():
    app()
    from vclone.manual_mesh_editor import MeshEditorDialog
    source = mesh()
    d = MeshEditorDialog(source, [64, 64])
    try:
        d._set_selected((1, 1))
        d.dx.setValue(5)
        d.apply_node()
        assert d._working[1][1] == [37, 32]
        assert source[1][1] == [32, 32]
        assert d.values() is None
        d.save_button.click()
        assert d.result() == QDialog.DialogCode.Accepted
        edited = d.values()
        assert edited[1][1] == [37, 32]
        edited[1][1] = [100, 100]
        assert d._working[1][1] == [37, 32]  # deep-copy isolation
    finally:
        d.close()


def test_cumulative_offset_above_bound_is_refused_without_corrupting_preview(monkeypatch):
    app()
    from vclone.manual_mesh_editor import MeshEditorDialog
    d = MeshEditorDialog(mesh(), [64, 64])
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(True))
    try:
        d._set_selected((1, 1))
        d.dx.setValue(64)
        d.apply_node()
        assert d._working[1][1][0] == 96
        d._set_selected((1, 1))
        d.dx.setValue(1)
        d.apply_node()
        assert errors
        assert d._working[1][1][0] == 96
    finally:
        d.close()


def test_gui_button_edits_actual_project_in_memory_not_camera_or_projector(monkeypatch):
    app()
    from vclone import gui
    class FakeDialog:
        def __init__(self, original, size, parent=None):
            assert size == [64, 64]
            self.modified = deepcopy(original)
            self.modified[1][1] = [35.0, 30.0]
        def exec(self):
            return QDialog.DialogCode.Accepted
        def values(self):
            return self.modified
    monkeypatch.setattr(gui, "MeshEditorDialog", FakeDialog)
    s = Session(Project(scan={"content_size": [64, 64]},
                        result={"mesh": mesh(), "coverage": 1.0}))
    w = gui.MainWindow(session=s)
    try:
        button = next(b for b in w.findChildren(QPushButton)
                      if b.text() == "Edit Warp Mesh")
        assert button.isEnabled()
        button.click()
        assert w.session.project.result["mesh"][1][1] == [35, 30]
        assert w.session.project.result["manual_edit_nodes"] == 1
        assert w.session.dirty
        assert w._camera_probe_worker is None
    finally:
        w.close()


def test_gui_refuses_manual_editor_until_calibrated(monkeypatch):
    app()
    from vclone import gui
    errors = []
    monkeypatch.setattr(gui, "MeshEditorDialog", lambda *_: (
        _ for _ in ()).throw(AssertionError("mesh editor launched on blank project")))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: errors.append(True))
    w = gui.MainWindow()
    try:
        w.edit_warp_mesh()
        assert errors
        assert not w.session.dirty
    finally:
        w.close()
