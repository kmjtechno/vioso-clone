"""M60 real multi-projector GUI still: synthetic safety/consent tests.

No camera, display window, network, or file write occurs in this suite.
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
    def __init__(self, x, y, w=640, h=480):
        self.rect = QRect(x, y, w, h)

    def geometry(self):
        return self.rect


def test_requires_two_distinct_extended_projectors_in_correct_resolution():
    from vclone.multi_still_gui import validate_mapping, MultiStillError
    primary, a, b = Screen(0, 0), Screen(640, 0), Screen(1280, 0)
    kw = {"screens": [primary, a, b], "primary": primary}
    assert validate_mapping([(640, 480), (640, 480)], [a, b], **kw) == [
        (640, 0), (1280, 0)]
    for targets in ([a, a], [primary, b], [a, Screen(1280, 0)]):
        with pytest.raises(MultiStillError):
            validate_mapping([(640, 480), (640, 480)], targets, **kw)
    with pytest.raises(MultiStillError, match="exactly match"):
        validate_mapping([(640, 480), (800, 600)], [a, b], **kw)
    with pytest.raises(MultiStillError):
        validate_mapping([(640, 480)], [a], **kw)
    mirror = Screen(0, 0)
    with pytest.raises(MultiStillError):
        validate_mapping([(640, 480), (640, 480)], [mirror, b],
                         screens=[primary, mirror, b], primary=primary)


def test_consent_and_duration_gate_before_manifest_or_projection(monkeypatch):
    from vclone import multi_still_gui as mod
    monkeypatch.setattr(mod, "load_sizes", lambda *_: (_ for _ in ()).throw(
        AssertionError("read private blend folder without operator consent")))
    p, a, b = Screen(0, 0), Screen(640, 0), Screen(1280, 0)
    for value in (False, None, "yes", 1):
        with pytest.raises(mod.MultiStillError, match="consent"):
            mod.present_verified_blend("private", [a, b], confirmed=value)
    for duration in (0, 100, 10001, "5000", True):
        with pytest.raises(mod.MultiStillError, match="duration"):
            mod.present_verified_blend(
                "private", [a, b], confirmed=True, duration_ms=duration)


def test_verified_engine_used_once_only_after_actual_screen_checks(monkeypatch):
    from vclone import multi_still_gui as mod
    from vclone.multi_present import MultiDisplayReceipt
    p, a, b = Screen(0, 0), Screen(640, 0), Screen(1280, 0)
    class Qt:
        screens = staticmethod(lambda: [p, a, b])
        primaryScreen = staticmethod(lambda: p)
    monkeypatch.setattr(mod, "QGuiApplication", Qt)
    monkeypatch.setattr(mod, "load_sizes", lambda path: [(640, 480), (640, 480)])
    called = []
    def real_engine(path, origins, **kwargs):
        called.append((path, origins, kwargs))
        return MultiDisplayReceipt(2, False)
    monkeypatch.setattr(mod, "present_multi", real_engine)
    out = mod.present_verified_blend(
        "owner-existing-hashed-M14-folder", [a, b], confirmed=True, duration_ms=3000)
    assert called == [("owner-existing-hashed-M14-folder",
                       [(640, 0), (1280, 0)],
                       {"duration_ms": 3000, "confirmed": True})]
    assert out["projectors_attempted"] == 2
    assert out["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert out["synchronization"] == "NOT_VERIFIED"


def test_dialog_disables_duplicate_mapping_until_distinct_owner_choice(monkeypatch):
    app()
    from vclone import multi_still_gui as mod
    p, a, b = Screen(0, 0), Screen(640, 0), Screen(1280, 0)
    class Qt:
        screens = staticmethod(lambda: [p, a, b])
        primaryScreen = staticmethod(lambda: p)
    monkeypatch.setattr(mod, "QGuiApplication", Qt)
    d = mod.MultiStillDialog([(640, 480), (640, 480)])
    try:
        assert not d.ok_button.isEnabled()
        assert d.values() is None
        d.confirm.setChecked(True)
        assert not d.ok_button.isEnabled()  # two same initial screen
        d.screen_selectors[1].setCurrentIndex(1)
        assert d.ok_button.isEnabled()
        d._accept_selection()
        assert d.result() == QDialog.DialogCode.Accepted
        targets, duration = d.values()
        assert targets == [a, b]
        assert duration == 5000
    finally:
        d.close()


def test_no_verified_blend_never_opens_mapping_dialog(monkeypatch):
    app()
    from vclone import gui
    w = gui.MainWindow()
    warnings = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: "unsafe-directory")
    monkeypatch.setattr(gui, "load_sizes", lambda *_: (_ for _ in ()).throw(
        ValueError("sensitive path 192.168.10.10 credential")))
    monkeypatch.setattr(gui, "MultiStillDialog", lambda *_: (_ for _ in ()).throw(
        AssertionError("dialog must not open for bad manifest")))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: warnings.append(_args[-1]))
    try:
        w.present_multi_still()
        assert warnings and "192.168" not in warnings[0]
        assert not w.session.dirty
    finally:
        w.close()


def test_owner_decline_never_starts_multi_display(monkeypatch):
    app()
    from vclone import gui
    a, b = Screen(640, 0), Screen(1280, 0)
    class Select:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return [a, b], 5000
    monkeypatch.setattr(gui, "MultiStillDialog", Select)
    monkeypatch.setattr(gui, "load_sizes", lambda *_: [(640, 480)] * 2)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: "private-M14")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_: QMessageBox.StandardButton.No)
    monkeypatch.setattr(gui, "present_verified_blend", lambda *_a, **_kw: (
        _ for _ in ()).throw(AssertionError("output without Yes")))
    w = gui.MainWindow()
    try:
        w.present_multi_still()
        assert not w.session.dirty
    finally:
        w.close()


def test_studio_button_calls_exact_confirmed_multi_engine(monkeypatch):
    app()
    from vclone import gui
    from PySide6.QtWidgets import QPushButton
    a, b = Screen(640, 0), Screen(1280, 0)
    class Select:
        def __init__(self, *_): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return [a, b], 2000
    monkeypatch.setattr(gui, "MultiStillDialog", Select)
    monkeypatch.setattr(gui, "load_sizes", lambda *_: [(640, 480)] * 2)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: "private-M14")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_: QMessageBox.StandardButton.Yes)
    actions = []
    monkeypatch.setattr(gui, "present_verified_blend",
                        lambda folder, screens, **kwargs: (
                            actions.append((folder, screens, kwargs)) or {
                                "projectors_attempted": 2}))
    w = gui.MainWindow()
    try:
        button = next(b for b in w.findChildren(QPushButton)
                      if b.text() == "Present Multi Still")
        assert button.isEnabled()
        button.click()
        assert actions == [("private-M14", [a, b],
                            {"confirmed": True, "duration_ms": 2000})]
        assert any("physical seam" in note for note in w.session.log)
        assert not w.session.dirty
    finally:
        w.close()
