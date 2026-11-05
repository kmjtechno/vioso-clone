"""M43 owner-local full-history clone safety, run on both Linux and Windows CI."""
from pathlib import Path
import re

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" / "windows" /
          "M43-VIOSO-P520-FULL-SOURCE-AND-QA.ps1")


def source():
    return SCRIPT.read_text(encoding="utf-8")


def test_m43_source_and_bounded_arguments():
    text = source()
    assert "M43" in text.splitlines()[0]
    assert "^[a-fA-F0-9]{40}$" in text
    assert "https://github.com/kmjtechno/vioso-clone.git" in text
    assert "$WorkspaceRoot = 'E:\\KMJ\\Codex\\VIOSO-Clone\\FullSource'" in text


def test_m43_default_has_no_network_and_no_writes():
    text = source()
    assert "[switch]$Execute" in text and "[switch]$RunQA" in text
    assert "if (-not $Execute)" in text
    assert "M43_PLAN_ONLY=PASS_NO_NETWORK_NO_WRITES" in text
    assert text.index("if (-not $Execute)") < text.index("ls-remote --heads")
    assert text.index("if (-not $Execute)") < text.index("clone --no-checkout")


def test_m43_exact_remote_sha_then_full_history():
    text = source()
    assert "M43_REMOTE_MAIN_CHANGED_NO_STALE_CHECKOUT" in text
    assert "M43_REMOTE_MAIN_EXACT_SHA=PASS" in text
    assert "clone --no-checkout -- $RepoUrl $Target" in text
    assert "--depth" not in text.split("clone --no-checkout")[1].splitlines()[0]
    assert "--single-branch" not in text
    assert "--is-shallow-repository" in text
    assert "M43_FULL_HISTORY_NOT_VERIFIED" in text
    assert "M43_CLONE_HEAD_MISMATCH" in text
    assert "M43_WRONG_ORIGIN" in text
    assert "M43_NEW_CLONE_NOT_CLEAN" in text


def test_m43_never_edits_existing_user_checkout_or_research():
    text = source()
    assert "VIOSO-Clone-FullSource-" in text
    assert "M43_TARGET_ALREADY_EXISTS_NO_OVERWRITE" in text
    assert "ReparsePoint" in text
    assert "M43_OWNER_CHECKOUT_AND_REA_NOTES=UNTOUCHED" in text
    assert not re.search(r"&\s*\$GitExe\b[^\n]*\b(?:reset|clean|pull|push)\b", text, re.I)
    assert "Remove-Item -Recurse" not in text
    assert "Invoke-Expression" not in text
    assert "Set-ExecutionPolicy" not in text


def test_m43_private_auth_in_memory_only_for_clone():
    text = source()
    assert "auth token 2>$null" in text
    assert "GIT_CONFIG_VALUE_0" in text
    assert "Remove-Item Env:\\GIT_CONFIG_VALUE_0" in text
    assert text.index("Remove-Item Env:\\GIT_CONFIG_VALUE_0") < text.index(
        "checkout --detach $Sha")
    assert "Write-Output $Token" not in text
    assert "M43_EXISTING_GIT_CONFIG_ENV_REFUSED" in text
    assert "Push-Location -LiteralPath $SafeGitCwd" in text
    assert "M45_SAFE_GIT_CONTEXT_UNAVAILABLE" in text
    assert "M45_GIT_CONTEXT_IS_INSIDE_OWNER_CHECKOUT" in text
    assert "[IO.Path]::GetTempPath()" in text


def test_m43_qa_runs_in_own_virtual_environment_only():
    text = source()
    assert "if (-not $RunQA)" in text
    assert "Join-Path $Target '.venv'" in text
    assert "-m pytest -q" in text
    assert "vclone.portable_entry --self-test" in text
    assert "QT_QPA_PLATFORM = 'offscreen'" in text
    assert "M43_LOCAL_GUI_OFFSCREEN=PASS" in text


def test_m43_hardware_parity_never_claimed():
    text = source()
    for item in [
        "M43_REAL_CAMERA_AND_PROJECTORS=NOT_TOUCHED",
        "M43_P520_LIVE_CAMERA=NOT_VERIFIED",
        "M43_DUAL_PROJECTOR_OPTICS=NOT_VERIFIED",
        "M43_VENDOR_VIOSO7_SPS_PARITY=NOT_VERIFIED",
    ]:
        assert item in text
