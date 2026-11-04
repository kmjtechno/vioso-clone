# M41 Windows owner-controlled exact-main isolated GUI QA.
# Default is plan only. This script NEVER edits the existing VIOSO checkout.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedMainSha,
    [string]$WorkspaceRoot = 'E:\KMJ\Codex',
    [switch]$Execute
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/kmjtechno/vioso-clone.git'

function Assert-NativeSuccess {
    param([string]$Stage)
    if ($LASTEXITCODE -ne 0) {
        throw ('M41_' + $Stage + '_FAILED_EXIT_' + [string]$LASTEXITCODE)
    }
}
if ($ExpectedMainSha -cnotmatch '^[0-9a-fA-F]{40}$') {
    throw 'M41_EXPECTED_MAIN_SHA_MUST_BE_40_HEX'
}
$Sha = $ExpectedMainSha.ToLowerInvariant()
$Root = [System.IO.Path]::GetFullPath($WorkspaceRoot)
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw 'M41_WORKSPACE_ROOT_MUST_ALREADY_EXIST'
}
$RootInfo = Get-Item -LiteralPath $Root -Force
if (($RootInfo.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'M41_WORKSPACE_ROOT_REPARSE_POINT_BLOCKED'
}
$TargetName = 'vioso-clone-isolated-' + $Sha.Substring(0, 12)
$Target = Join-Path -Path $Root -ChildPath $TargetName
# A prior partial run or a symlink must never be overwritten.
if ($null -ne (Get-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue)) {
    throw 'M41_TARGET_EXISTS_REFUSE_OVERWRITE_OR_RETRY'
}
if (Test-Path -LiteralPath $Target) {
    throw 'M41_TARGET_EXISTS_REFUSE_OVERWRITE_OR_RETRY'
}
Write-Output 'M41_P520_ISOLATED_QA=V1'
Write-Output ('M41_EXPECTED_MAIN_SHA=' + $Sha)
Write-Output ('M41_NEW_TARGET=' + $Target)
Write-Output 'M41_EXISTING_P520_CHECKOUT=UNTOUCHED'
Write-Output 'M41_CAMERA_AND_PROJECTOR_ACCESS=NONE'
Write-Output 'M41_VENDOR_BINARY_ACCESS=NONE'
Write-Output 'M41_NATIVE_VIOSO_SPS_PARITY=NOT_VERIFIED'
if (-not $Execute) {
    Write-Output 'M41_PLAN_ONLY=PASS_NO_NETWORK_NO_WRITES'
    return
}
if ($env:OS -ne 'Windows_NT') {
    throw 'M41_EXECUTION_REQUIRES_WINDOWS'
}
# Windows often exposes Git and Python through multiple PATH entries.
# Select one actual executable, never stringify an array of command paths.
$GitExe = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$PyLauncher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $PyLauncher) {
    $PythonExeForVenv = $PyLauncher.Source
    $PythonArgs = @('-3')
} else {
    $PythonExeForVenv = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $PythonArgs = @()
}
# Disable prompting and use only the fixed, owner-controlled repository URL.
$env:GIT_TERMINAL_PROMPT = '0'

# GitHub Actions or the owner may supply an already-authorized read-only token
# through this process's environment. No token ever appears in argv, URLs,
# outputs, on-disk Git config, or the isolated source tree.
$HasEphemeralToken = -not [string]::IsNullOrWhiteSpace($env:M41_GITHUB_READ_TOKEN)
if ($HasEphemeralToken) {
    if (Test-Path Env:\GIT_CONFIG_COUNT) {
        throw 'M41_GIT_CONFIG_ENV_ALREADY_PRESENT_REFUSE_OVERRIDE'
    }
    $Auth = 'x-access-token:' + $env:M41_GITHUB_READ_TOKEN
    $Encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Auth))
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'http.https://github.com/.extraheader'
    $env:GIT_CONFIG_VALUE_0 = 'AUTHORIZATION: basic ' + $Encoded
    $Auth = $null
    $Encoded = $null
}
# Run Git outside the invoking checkout so its local extraheader/filters
# cannot add a second credential or affect the new, isolated clone.
Push-Location -LiteralPath $Root
try {
    $RemoteLines = @(& $GitExe ls-remote --heads $RepoUrl main)
    Assert-NativeSuccess 'REMOTE_MAIN_LOOKUP'
    if ($RemoteLines.Count -ne 1) {
        throw 'M41_REMOTE_MAIN_RESPONSE_REFUSED'
    }
    $RemoteMatch = [regex]::Match([string]$RemoteLines[0], '^([0-9a-fA-F]{40})\s+refs/heads/main$')
    if (-not $RemoteMatch.Success) {
        throw 'M41_REMOTE_MAIN_RESPONSE_REFUSED'
    }
    $ObservedSha = $RemoteMatch.Groups[1].Value.ToLowerInvariant()
    if ($ObservedSha -cne $Sha) {
        throw 'M41_REMOTE_MAIN_SHA_CHANGED_REFUSE_STALE_INSTALL'
    }
    Write-Output 'M41_REMOTE_MAIN_SHA=EXACT_MATCH'

    # Fresh, absent sibling only: no reset, clean, pull or checkout of owner files.
    # The clone does not populate its worktree until AFTER auth is cleared.
    & $GitExe -c core.hooksPath=NUL clone --no-checkout --single-branch --depth 1 --branch main -- $RepoUrl $Target
    Assert-NativeSuccess 'FRESH_CLONE'
} finally {
    Pop-Location
    if ($HasEphemeralToken) {
        # Never pass a repo access token to checkout filters, Python/pip, or tests.
        Remove-Item Env:\GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue
        Remove-Item Env:\GIT_CONFIG_KEY_0 -ErrorAction SilentlyContinue
        Remove-Item Env:\GIT_CONFIG_COUNT -ErrorAction SilentlyContinue
        Remove-Item Env:\M41_GITHUB_READ_TOKEN -ErrorAction SilentlyContinue
    }
}
& $GitExe -C $Target -c core.hooksPath=NUL checkout --detach $Sha
Assert-NativeSuccess 'DETACHED_CHECKOUT'
$ActualSha = ((& $GitExe -C $Target rev-parse HEAD) -join '').Trim().ToLowerInvariant()
Assert-NativeSuccess 'HEAD_CHECK'
if ($ActualSha -cne $Sha) {
    throw 'M41_ISOLATED_HEAD_MISMATCH'
}
$Dirty = @(& $GitExe -C $Target status --porcelain --untracked-files=all)
Assert-NativeSuccess 'ISOLATED_STATUS_CHECK'
if ($Dirty.Count -ne 0) {
    throw 'M41_ISOLATED_SOURCE_UNEXPECTEDLY_DIRTY'
}
Write-Output 'M41_EXACT_HEAD_ISOLATED_SOURCE=PASS'

# All package installation remains inside the isolated clone's virtualenv.
$Venv = Join-Path $Target '.venv'
& $PythonExeForVenv @PythonArgs -m venv $Venv
Assert-NativeSuccess 'VENV_CREATE'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw 'M41_VENV_PYTHON_MISSING'
}
& $VenvPython -m pip install --disable-pip-version-check --no-input -e ($Target + '[gui,test]')
Assert-NativeSuccess 'ISOLATED_DEPENDENCIES'
Write-Output 'M41_GUI_TEST_DEPENDENCIES=ISOLATED_VENV_ONLY'
try {
    Push-Location -LiteralPath $Target
    & $VenvPython -m pytest -q
    Assert-NativeSuccess 'FULL_REGRESSION'
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $VenvPython -c 'from PySide6.QtWidgets import QApplication; from vclone.gui import MainWindow; app=QApplication.instance() or QApplication([]); window=MainWindow(); assert window.windowTitle().startswith("VIOSO Clone"); window.close()'
    Assert-NativeSuccess 'OFFSCREEN_GUI_SMOKE'
} finally {
    Pop-Location
}
Write-Output 'M41_FULL_REGRESSION=PASS'
Write-Output 'M41_OFFSCREEN_GUI_SMOKE=PASS'
Write-Output 'M41_REAL_CAMERA_FRAME_TEST=NOT_ATTEMPTED'
Write-Output 'M41_REAL_PROJECTOR_TEST=NOT_ATTEMPTED'
Write-Output 'M41_SIGNED_WINDOWS_INSTALLER=NOT_CREATED'
Write-Output 'M41_EXISTING_P520_CHECKOUT=UNTOUCHED'
