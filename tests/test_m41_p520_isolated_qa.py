"""M41 regression: source-level safety of the owner-run isolated Windows QA lane.

Actual native PowerShell parse/plan and isolated end-to-end execution are in
.github/workflows/m41-p520-isolated-qa.yml on a disposable Windows runner.
"""
from pathlib import Path
import re

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" / "windows" /
          "P520-VIOSO-EXACT-MAIN-ISOLATED-QA-M41.ps1")


def source():
    return SCRIPT.read_text(encoding="utf-8")


def test_m41_source_present_and_powershell_not_a_shell_downloader():
    data = source()
    assert data.startswith("# M41")
    assert "[CmdletBinding()]" in data
    assert "Invoke-Expression" not in data
    assert "iex " not in data.lower()
    assert "Start-Process" not in data
    assert "cmd.exe" not in data


def test_m41_exact_sha_and_fixed_repo_not_tainted():
    data = source()
    assert "ExpectedMainSha" in data
    assert "^[0-9a-fA-F]{40}$" in data
    assert "https://github.com/kmjtechno/vioso-clone.git" in data
    assert "ls-remote --heads $RepoUrl main" in data
    assert "M41_REMOTE_MAIN_SHA_CHANGED_REFUSE_STALE_INSTALL" in data
    assert "M41_ISOLATED_HEAD_MISMATCH" in data


def test_m41_plan_only_is_explicit_default_and_precedes_git_network():
    data = source()
    assert "[switch]$Execute" in data
    assert "if (-not $Execute)" in data
    assert "M41_PLAN_ONLY=PASS_NO_NETWORK_NO_WRITES" in data
    assert data.index("if (-not $Execute)") < data.index("ls-remote --heads")


def test_m41_isolated_destination_cannot_overwrite_existing_directory():
    data = source()
    assert "'vioso-clone-isolated-'" in data
    assert "M41_TARGET_EXISTS_REFUSE_OVERWRITE_OR_RETRY" in data
    assert "-LiteralPath $Target" in data
    assert "ReparsePoint" in data
    assert "--no-checkout --single-branch --depth 1" in data
    assert "checkout --detach $Sha" in data
    assert "M41_ISOLATED_SOURCE_UNEXPECTEDLY_DIRTY" in data


def test_m41_never_resets_or_cleans_shared_checkout():
    data = source()
    assert not re.search(r"\b(?:git|\$GitExe)\s+(?:reset|clean|pull|push|switch)\b", data, re.I)
    assert "Remove-Item" not in data
    assert "Clear-Content" not in data
    assert "Set-Content" not in data
    assert "M41_EXISTING_P520_CHECKOUT=UNTOUCHED" in data



def test_m41_git_python_path_multiplicity_is_resolved_to_one_binary():
    data = source()
    for name in ("git", "py", "python"):
        expected = "Get-Command " + name + " -CommandType Application"
        assert expected in data
    assert data.count("Select-Object -First 1") == 3
    assert "$GitExe = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source" in data



def test_m41_ephemeral_private_repo_auth_never_reaches_checkout_or_pip():
    data = source()
    assert "M41_GITHUB_READ_TOKEN" in data
    assert "AUTHORIZATION: basic " in data
    assert "GIT_CONFIG_VALUE_0" in data
    assert "M41_GIT_CONFIG_ENV_ALREADY_PRESENT_REFUSE_OVERRIDE" in data
    assert "Remove-Item Env:\\GIT_CONFIG_VALUE_0" in data
    assert "Remove-Item Env:\\M41_GITHUB_READ_TOKEN" in data
    assert data.index("Remove-Item Env:\\GIT_CONFIG_VALUE_0") < data.index(
        "checkout --detach $Sha")
    assert data.index("Remove-Item Env:\\GIT_CONFIG_VALUE_0") < data.index(
        "-m pip install")
    assert 'Write-Output $env:M41_GITHUB_READ_TOKEN' not in data


def test_m41_gui_regression_runs_only_in_isolated_virtualenv():
    data = source()
    assert "Join-Path $Target '.venv'" in data
    assert "Scripts\\python.exe" in data
    assert "-e ($Target + '[gui,test]')" in data
    assert "-m pytest -q" in data
    assert "QT_QPA_PLATFORM = 'offscreen'" in data
    assert "MainWindow" in data


def test_m41_never_claims_real_hardware_or_vendor_parity():
    data = source()
    for receipt in (
        "M41_CAMERA_AND_PROJECTOR_ACCESS=NONE",
        "M41_VENDOR_BINARY_ACCESS=NONE",
        "M41_NATIVE_VIOSO_SPS_PARITY=NOT_VERIFIED",
        "M41_REAL_CAMERA_FRAME_TEST=NOT_ATTEMPTED",
        "M41_REAL_PROJECTOR_TEST=NOT_ATTEMPTED",
        "M41_SIGNED_WINDOWS_INSTALLER=NOT_CREATED",
    ):
        assert receipt in data
