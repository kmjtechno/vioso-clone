"""Packaging/entrypoint smoke tests; no hardware or proprietary files needed."""
import subprocess
import sys
import tomllib
from pathlib import Path

import vclone


ROOT = Path(__file__).resolve().parent.parent


def test_distribution_version_and_console_entrypoint_match_source():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "kmj-vioso-clone"
    assert data["project"]["version"] == vclone.__version__
    assert data["project"]["scripts"]["vclone"] == "vclone.__main__:main"
    assert data["project"]["requires-python"].startswith(">=")


def test_gui_is_optional_and_core_dependencies_explicit():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = " ".join(data["project"]["dependencies"])
    assert "numpy" in core and "opencv-python" in core
    assert any("PySide6" in x for x in data["project"]["optional-dependencies"]["gui"])
    assert "PySide6" not in core


def test_module_cli_help_without_hardware():
    r = subprocess.run([sys.executable, "-m", "vclone", "--help"],
                       capture_output=True, text=True, cwd=ROOT, timeout=20)
    assert r.returncode == 0, r.stderr
    for command in ("devices", "spaces", "preview", "capture-graycode",
                    "present-preview", "gui"):
        assert command in r.stdout
