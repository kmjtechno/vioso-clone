# M43: Full Git history, clean sibling P520 clone and optional offline GUI QA.
# REVIEW BEFORE RUNNING. Default = PLAN ONLY; -Execute is the sole write gate.
# No reset/clean or modification of the existing VIOSO-Clone owner checkout.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-fA-F0-9]{40}$')]
    [string]$ExpectedMainSha,
    [string]$WorkspaceRoot = 'E:\KMJ\Codex',
    [switch]$Execute,
    [switch]$RunQA
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/kmjtechno/vioso-clone.git'
$Sha = $ExpectedMainSha.ToLowerInvariant()

function Check-Exit {
    param([string]$Stage)
    if ($LASTEXITCODE -ne 0) {
        throw ('M43_' + $Stage + '_EXIT_' + [string]$LASTEXITCODE)
    }
}

$Root = [IO.Path]::GetFullPath($WorkspaceRoot)
$RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
if (-not $RootItem.PSIsContainer) {
    throw 'M43_WORKSPACE_ROOT_NOT_DIRECTORY'
}
if (($RootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'M43_WORKSPACE_ROOT_REPARSE_POINT_BLOCKED'
}
$Target = Join-Path $Root ('VIOSO-Clone-FullSource-' + $Sha.Substring(0, 12))
if ($null -ne (Get-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue)) {
    throw 'M43_TARGET_ALREADY_EXISTS_NO_OVERWRITE'
}
Write-Output 'M43_P520_FULL_SOURCE=V1'
Write-Output ('M43_SOURCE_SHA=' + $Sha)
Write-Output ('M43_FRESH_SIBLING=' + $Target)
Write-Output 'M43_OWNER_CHECKOUT_AND_REA_NOTES=UNTOUCHED'
Write-Output 'M43_REAL_CAMERA_AND_PROJECTORS=NOT_TOUCHED'
if (-not $Execute) {
    Write-Output 'M43_PLAN_ONLY=PASS_NO_NETWORK_NO_WRITES'
    return
}
if ($env:OS -ne 'Windows_NT') {
    throw 'M43_WINDOWS_ONLY'
}

$GitTool = Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1
$GitExe = $GitTool.Source
$env:GIT_TERMINAL_PROMPT = '0'

# Optional authenticated gh CLI avoids asking users to paste private tokens.
# Git Credential Manager's already-authorized cache also works without gh.
$Token = $null
$GhTool = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -ne $GhTool) {
    $Candidate = @(& $GhTool.Source auth token 2>$null)
    if ($LASTEXITCODE -eq 0 -and $Candidate.Count -eq 1) {
        $Token = [string]$Candidate[0]
    }
    $Candidate = $null
}
$HasToken = -not [string]::IsNullOrWhiteSpace($Token)
if ($HasToken) {
    # Refuse to collide with a preexisting Git ephemeral configuration.
    if (Test-Path Env:\GIT_CONFIG_COUNT) {
        throw 'M43_EXISTING_GIT_CONFIG_ENV_REFUSED'
    }
    $Encoded = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes('x-access-token:' + $Token))
    $Token = $null
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'http.https://github.com/.extraheader'
    $env:GIT_CONFIG_VALUE_0 = 'AUTHORIZATION: basic ' + $Encoded
    $Encoded = $null
}

# Avoid Git's inherited checkout-specific extra headers when running from
# the owner's dirty repo. Git runs from a separate, already existing root.
Push-Location -LiteralPath $Root
try {
    $Lines = @(& $GitExe ls-remote --heads $RepoUrl main)
    Check-Exit 'REMOTE_MAIN_LOOKUP'
    if ($Lines.Count -ne 1) {
        throw 'M43_MAIN_REF_AMBIGUOUS'
    }
    $Match = [regex]::Match([string]$Lines[0],
        '^([a-fA-F0-9]{40})\s+refs/heads/main$')
    if (-not $Match.Success) {
        throw 'M43_MAIN_REF_INVALID'
    }
    if ($Match.Groups[1].Value.ToLowerInvariant() -cne $Sha) {
        throw 'M43_REMOTE_MAIN_CHANGED_NO_STALE_CHECKOUT'
    }
    Write-Output 'M43_REMOTE_MAIN_EXACT_SHA=PASS'
    # FULL clone: all remote branch history and tags, without --depth.
    # --no-checkout means no source tree is populated until auth is cleared.
    & $GitExe -c core.hooksPath=NUL clone --no-checkout -- $RepoUrl $Target
    Check-Exit 'FULL_CLONE'
} finally {
    Pop-Location
    if ($HasToken) {
        Remove-Item Env:\GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue
        Remove-Item Env:\GIT_CONFIG_KEY_0 -ErrorAction SilentlyContinue
        Remove-Item Env:\GIT_CONFIG_COUNT -ErrorAction SilentlyContinue
    }
    $Token = $null
}
$Origin = ((& $GitExe -C $Target remote get-url origin) -join '').Trim()
Check-Exit 'ORIGIN_LOOKUP'
if ($Origin -cne $RepoUrl) {
    throw 'M43_WRONG_ORIGIN'
}
$IsShallow = ((& $GitExe -C $Target rev-parse --is-shallow-repository) -join '').Trim()
Check-Exit 'SHALLOW_CHECK'
if ($IsShallow -ne 'false') {
    throw 'M43_FULL_HISTORY_NOT_VERIFIED'
}
& $GitExe -C $Target -c core.hooksPath=NUL checkout --detach $Sha
Check-Exit 'EXACT_SHA_CHECKOUT'
$Head = ((& $GitExe -C $Target rev-parse HEAD) -join '').Trim().ToLowerInvariant()
Check-Exit 'HEAD_CHECK'
if ($Head -cne $Sha) {
    throw 'M43_CLONE_HEAD_MISMATCH'
}
$Dirty = @(& $GitExe -C $Target status --porcelain --untracked-files=all)
Check-Exit 'CLONE_STATUS'
if ($Dirty.Count -ne 0) {
    throw 'M43_NEW_CLONE_NOT_CLEAN'
}
Write-Output 'M43_FULL_HISTORY_AND_EXACT_MAIN=PASS'
Write-Output 'M43_OWNER_CHECKOUT_AND_REA_NOTES=UNTOUCHED'

if (-not $RunQA) {
    Write-Output 'M43_LOCAL_FULL_SOURCE_PULL=PASS'
    Write-Output 'M43_LOCAL_GUI_QA=NOT_REQUESTED'
    return
}

$Py = Get-Command py -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -ne $Py) {
    $PythonExe = $Py.Source
    $PythonArgs = @('-3')
} else {
    $PythonExe = (Get-Command python -CommandType Application -ErrorAction Stop |
        Select-Object -First 1).Source
    $PythonArgs = @()
}
$Venv = Join-Path $Target '.venv'
& $PythonExe @PythonArgs -m venv $Venv
Check-Exit 'VENV_CREATE'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw 'M43_VENV_PYTHON_MISSING'
}
& $VenvPython -m pip install --disable-pip-version-check --no-input -e ($Target + '[gui,test]')
Check-Exit 'LOCAL_GUI_TEST_DEPENDENCIES'
$PriorQt = $env:QT_QPA_PLATFORM
try {
    Push-Location -LiteralPath $Target
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $VenvPython -m pytest -q
    Check-Exit 'FULL_PYTEST'
    & $VenvPython -m vclone.portable_entry --self-test
    Check-Exit 'GUI_OFFSCREEN'
} finally {
    Pop-Location
    if ($null -eq $PriorQt) {
        Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    } else {
        $env:QT_QPA_PLATFORM = $PriorQt
    }
}
Write-Output 'M43_LOCAL_FULL_SOURCE_PULL=PASS'
Write-Output 'M43_LOCAL_FULL_PYTEST=PASS'
Write-Output 'M43_LOCAL_GUI_OFFSCREEN=PASS'
Write-Output 'M43_P520_LIVE_CAMERA=NOT_VERIFIED'
Write-Output 'M43_DUAL_PROJECTOR_OPTICS=NOT_VERIFIED'
Write-Output 'M43_VENDOR_VIOSO7_SPS_PARITY=NOT_VERIFIED'
