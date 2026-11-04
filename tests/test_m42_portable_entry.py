"""M42 portable executable smoke and hardware-non-invocation regression."""
import os

import pytest

from vclone import __version__
from vclone import portable_entry


def test_portable_version_does_not_import_qt_or_connect_hardware(capsys, monkeypatch):
    imports = []
    original_import = __import__

    def monitor(name, *args, **kwargs):
        if name.startswith(("cv2", "PySide6")):
            imports.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", monitor)
    assert portable_entry.portable_main(["--version"]) == 0
    assert __version__ in capsys.readouterr().out
    assert not imports


@pytest.mark.parametrize("params", [
    ["--probe-camera"], ["--projector-on"], ["--self-test", "--fake"],
    ["--version", "unexpected"], ["--help"], ["--execute"],
])
def test_unknown_arguments_fail_closed_without_hardware(params, monkeypatch):
    from vclone import gui

    monkeypatch.setattr(gui, "main",
                        lambda *_a: (_ for _ in ()).throw(
                            AssertionError("unapproved arguments launched GUI")))
    assert portable_entry.portable_main(params) == 2


def test_portable_gui_self_test_is_offscreen_and_has_four_safety_actions(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import cv2
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(
        cv2, "VideoCapture",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("self-test must never access cameras")))
    monkeypatch.setattr(
        cv2, "namedWindow",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("self-test must never display projector patterns")))
    app = QApplication.instance() or QApplication([])
    assert portable_entry.portable_main(["--self-test"]) == 0
    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"


def test_portable_gui_launch_dispatch_is_explicit(monkeypatch):
    import vclone.gui as gui

    seen = []
    monkeypatch.setattr(gui, "main", lambda args: seen.append(args) or 0)
    assert portable_entry.portable_main([]) == 0
    assert len(seen) == 1
    assert isinstance(seen[0], list) and len(seen[0]) == 1
