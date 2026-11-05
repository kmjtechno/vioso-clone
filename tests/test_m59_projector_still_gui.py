"""M59 timed real projector still: negative gates and GUI path (no hardware).

The actual display is never opened in tests. All image data is synthetic.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox


def app():
    return QApplication.instance() or QApplication([])


class Screen:
    def __init__(self, x, y, width=640, height=480):
        self.area = QRect(x, y, width, height)

    def geometry(self):
        return self.area


def test_primary_and_mirrored_displays_never_become_candidates():
    from vclone.projector_still_gui import eligible_secondary_screens
    primary = Screen(0, 0)
    mirrored = Screen(0, 0)
    extra = Screen(640, 0)
    assert eligible_secondary_screens([primary, mirrored], primary) == []
    assert eligible_secondary_screens([primary, mirrored, extra], primary) == [(2, extra)]


def test_no_consent_or_bad_screen_refused_before_window(monkeypatch):
    from vclone import projector_still_gui as mod
    primary, secondary = Screen(0, 0), Screen(640, 0)
    good = np.full((480, 640, 3), 140, dtype=np.uint8)
    monkeypatch.setattr(mod, "_FrameWindow", lambda *_: (_ for _ in ()).throw(
        AssertionError("real output window constructed without validated consent")))
    for consent in (False, None, 1, "yes"):
        with pytest.raises(mod.ProjectorStillError, match="consent"):
            mod.validate_target(
                secondary, good, confirmed=consent, screens=[primary, secondary],
                primary=primary)
    with pytest.raises(mod.ProjectorStillError, match="extended"):
        mod.validate_target(
            primary, good, confirmed=True, screens=[primary, secondary],
            primary=primary)
    with pytest.raises(mod.ProjectorStillError, match="extended"):
        mod.validate_target(
            Screen(640, 0), good, confirmed=True, screens=[primary, secondary],
            primary=primary)


def test_wrong_size_dtype_and_duration_refused():
    from vclone.projector_still_gui import ProjectorStillError, validate_target
    p, s = Screen(0, 0), Screen(640, 0)
    kw = {"confirmed": True, "screens": [p, s], "primary": p}
    for frame in (np.zeros((480, 639, 3), np.uint8),
                  np.zeros((480, 640, 4), np.uint8),
                  np.zeros((480, 640, 3), np.float32),
                  np.zeros((480, 640, 3), np.uint8)[:, ::-1, :]):
        with pytest.raises(ProjectorStillError):
            validate_target(s, frame, **kw)
    frame = np.zeros((480, 640, 3), np.uint8)
    for duration in (0, 500, 10001, True, "5000"):
        with pytest.raises(ProjectorStillError, match="duration"):
            validate_target(s, frame, duration_ms=duration, **kw)
    assert validate_target(s, frame, **kw).width() == 640


def test_no_projector_selection_dialog_is_inert_without_second_display():
    app()
    from vclone.projector_still_gui import ProjectorStillDialog
    d = ProjectorStillDialog()
    try:
        # One-screen offscreen CI cannot silently map the primary.
        if not d._choices:
            assert d.selected_screen() is None
            assert not d.ok_button.isEnabled()
            assert d.values() is None
    finally:
        d.close()


def test_main_window_never_prompts_for_content_without_calibrated_mesh(monkeypatch):
    app()
    from vclone import gui
    w = gui.MainWindow()
    msgs = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: msgs.append(True))
    monkeypatch.setattr(gui, "ProjectorStillDialog", lambda *_: (
        _ for _ in ()).throw(AssertionError("selection opened without calibration")))
    try:
        assert not w.session.project.result
        w.present_calibrated_still()
        assert msgs
        assert not w.session.dirty
    finally:
        w.close()


def test_cancel_before_content_does_not_operate_projector(monkeypatch):
    app()
    from vclone import gui
    class CancelDialog:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Rejected
    w = gui.MainWindow()
    w.session.project.result["mesh"] = [[[0.0, 0.0]]]
    monkeypatch.setattr(gui, "ProjectorStillDialog", CancelDialog)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("content opened after cancel")))
    try:
        w.present_calibrated_still()
        assert not w.session.dirty
    finally:
        w.close()


def test_confirmed_gui_wires_real_renderer_to_timed_output_without_saving(monkeypatch):
    app()
    from vclone import gui
    from PySide6.QtWidgets import QPushButton
    screen = Screen(640, 0)
    class Selected:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return screen, 3000
    events = []
    monkeypatch.setattr(gui, "ProjectorStillDialog", Selected)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_: ("C:/owner/content-test.png", ""))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(gui, "validate_target",
                        lambda sc, frame, **kw: events.append(("validated", kw)))
    monkeypatch.setattr(gui, "present_calibrated_still",
                        lambda frame, sc, **kw: (
                            events.append(("output", kw)) or {
                                "projector_operation": "ONE_OPERATOR_CONFIRMED_TIMED_STILL"}))
    frame = np.full((480, 640, 3), 110, dtype=np.uint8)
    w = gui.MainWindow()
    w.session.project.result["mesh"] = [[[0.0, 0.0]]]
    monkeypatch.setattr(w.session, "preview_content",
                        lambda path: (
                            events.append(("render", path)) or frame))
    try:
        button = next(b for b in w.findChildren(QPushButton)
                      if b.text() == "Present Still")
        assert button.isEnabled()
        button.click()
        assert [x[0] for x in events] == ["render", "validated", "output"]
        assert events[-1][1] == {"confirmed": True, "duration_ms": 3000}
        assert any("physical optics NOT_VERIFIED" in s for s in w.session.log)
        assert not w.session.dirty
    finally:
        w.close()


def test_second_yes_decline_never_calls_renderer_or_output(monkeypatch):
    app()
    from vclone import gui
    class Selected:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return Screen(640, 0), 2000
    w = gui.MainWindow()
    w.session.project.result["mesh"] = [[[0.0, 0.0]]]
    monkeypatch.setattr(gui, "ProjectorStillDialog", Selected)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_: ("C:/owner/content-test.png", ""))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_: QMessageBox.StandardButton.No)
    monkeypatch.setattr(w.session, "preview_content", lambda *_: (
        _ for _ in ()).throw(AssertionError("rendered without final consent")))
    try:
        w.present_calibrated_still()
        assert not w.session.dirty
    finally:
        w.close()
