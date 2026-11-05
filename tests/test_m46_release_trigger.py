"""M46: prevent Windows prerelease from lagging the GUI/calibration source."""
from pathlib import Path


def test_main_push_release_covers_all_runtime_and_gui_sources():
    text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
            "m42-windows-prerelease.yml").read_text(encoding="utf-8")
    trigger = text.split("permissions:", 1)[0]
    assert "  push:" in trigger
    assert "    branches: [main]" in trigger
    assert '      - "vclone/**"' in trigger
    assert '      - "pyproject.toml"' in trigger
    assert '      - ".github/workflows/m42-windows-prerelease.yml"' in trigger
    # Never use GitHub Actions artifact storage after the verified quota block.
    assert "actions/upload-artifact" not in text
    assert "gh release create" in text
    assert "--prerelease --latest=false" in text


def test_windows_release_requires_real_extracted_binary_selftest():
    text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
            "m42-windows-prerelease.yml").read_text(encoding="utf-8")
    assert "M42_PRERELEASE_EXTRACTED_GUI_NO_HARDWARE=PASS" in text
    assert "M42_PRERELEASE_ZIP_SHA256=" in text
    assert "M42_PRERELEASE_BINARY_ASSET_UNVERIFIED" in text
    assert "M42_HARDWARE_OPTICAL_ACCEPTANCE=NOT_VERIFIED" in text
    assert "M42_NATIVE_VIOSO7_SPS_PARITY=NOT_VERIFIED" in text
    assert "M42_AUTHENTICODE_SIGNED=NO" in text
