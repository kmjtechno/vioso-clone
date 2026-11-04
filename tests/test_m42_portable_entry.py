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
    # This security gate must pass on CLI-only platforms without PySide6.
    # No invalid argument is permitted to import/open the GUI at all.
    import builtins

    original_import = builtins.__import__

    def deny_gui(name, *args, **kwargs):
        if name in ("vclone.gui", "PySide6.QtWidgets") or name == "gui":
            raise AssertionError("invalid argument attempted GUI import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_gui)
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
    pytest.importorskip("PySide6")
    import vclone.gui as gui

    seen = []
    monkeypatch.setattr(gui, "main", lambda args: seen.append(args) or 0)
    assert portable_entry.portable_main([]) == 0
    assert len(seen) == 1
    assert isinstance(seen[0], list) and len(seen[0]) == 1


def test_portable_release_keeps_diagnosable_console_bootloader():
    """Avoid the CI-proven failure of PyInstaller --windowed frozen self-test."""
    from pathlib import Path
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" /
        "m42-windows-portable.yml").read_text(encoding="utf-8")
    assert "--console --hide-console hide-early" in workflow
    assert "--windowed" not in workflow
    assert "M42_EXTRACTED_GUI_NO_HARDWARE_SMOKE=PASS" in workflow


def test_private_prerelease_replaces_quota_blocked_actions_artifacts():
    """Source policy: no Actions artifact uploads when account storage is full."""
    from pathlib import Path
    workflows = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    pr = (workflows / "m42-windows-portable.yml").read_text(encoding="utf-8")
    release = (workflows / "m42-windows-prerelease.yml").read_text(encoding="utf-8")
    assert "actions/upload-artifact" not in pr
    assert "actions/upload-artifact" not in release
    assert "  pull_request:" in pr
    assert "  push:" not in pr
    assert "  push:" in release
    assert "    branches: [main]" in release
    assert "    permissions:\n      contents: write" in release
    assert "gh release create" in release
    assert "--prerelease --latest=false" in release
    assert "M42_PRERELEASE_EXTRACTED_GUI_NO_HARDWARE=PASS" in release
    assert "M42_AUTHENTICODE_SIGNED=NO" in release
    assert "M42_PRERELEASE_BINARY_ASSET_UNVERIFIED" in release
    assert "GITHUB_REF -ne 'refs/heads/main'" in release
