# M41 — Exact-main isolated Windows QA without touching the owner's checkout

**Purpose:** The owner's P520 CodeBridge is online but the shared
`E:\KMJ\Codex\VIOSO-Clone` checkout is on `feat/sps-container-m5`
with modified and untracked reverse-engineering notes. The gateway also
exposes only the preapproved `python_verify:test` and `rea_doctor:check`
commands. It would be unsafe to reset, clean, force checkout, or silently
overwrite that tree.

This milestone provides a separately reviewed Windows PowerShell script at
`scripts/windows/P520-VIOSO-EXACT-MAIN-ISOLATED-QA-M41.ps1`. It is **not**
automatically run on the owner's PC and does **not** extend the CodeBridge
administrator command allowlist.

## Workflow

1. An owner/admin independently determines the current 40-character GitHub
   `main` commit SHA and reviews the exact script source. Never download and
   execute a script using a pipeline into `Invoke-Expression`.
2. With a real, already existing workspace root (normally
   `E:\KMJ\Codex`), the script's default invocation without `-Execute`
   does **plan-only** verification: valid SHA, root directory and absence of
   the proposed sibling directory. No network access, Git commands or writes.
3. An explicit local `-Execute` uses a fixed, public GitHub repository URL.
   It checks that remote `main` still equals the caller's exact SHA. If main
   moves, execution stops without creating the target. It performs a
   shallow, no-checkout Git clone only into a **previously nonexistent** sibling
   folder `vioso-clone-isolated-<first12sha>`.
   The repository may be private: an already-authorized Git Credential Manager
   session can supply credentials noninteractively. On a trusted, private
   GitHub Actions job, the step instead provides a narrowly scoped, temporary
   `M41_GITHUB_READ_TOKEN` environment variable. The script derives a Git
   HTTP authorization header **in memory only** for the main-SHA lookup and
   no-checkout clone, then unsets it **before** checkout, Python dependencies
   or any test code runs. No token may be passed through command arguments,
   embedded in the URL, written to Git config or copied to output. A missing
   credential must fail safely; do not weaken Git authentication.
4. The new clone checks out a detached SHA with Git hooks disabled, verifies
   exact HEAD and clean status, creates only its own `.venv`, and installs
   Python `[gui,test]` dependencies into that environment. It runs the
   complete synthetic Python regression suite and an offscreen PySide6 GUI
   construction smoke test. No real webcam, RTSP camera or projector is
   opened.
5. It prints bounded receipts. Existing/partial target directory, invalid SHA,
   untrusted/missing root, failed remote check, unexpected dirty source,
   missing interpreter, or any test failure aborts. **No automatic deletion**
   occurs on a partial failure; inspect before any separate cleanup.

## Security & acceptance

- The original P520 checkout, REA notes, tokens, vendor installation and
  existing CodeBridge config stay untouched. No `git reset`, `git clean`,
  force push, and no copying private configuration into the fresh clone.
- The script does not disable or bypass Windows execution-policy controls.
  Run it only in an owner-approved PowerShell session after review; do not
  globally relax system signing policy.
- GitHub Actions M41 tests the script's PowerShell syntax, plan-only behavior,
  wrong-SHA refusal, existing-target refusal, and a genuine fresh isolated
  Windows runner build with full Python regression and offscreen GUI smoke.
  **CI on a hosted runner is not P520 physical acceptance.**
- Network access occurs only in explicit `-Execute`: Git remote lookup,
  fixed public clone, and Python package installation. Package downloads may
  use normal internet connectivity but require no paid services.
- This is a **Python alpha QA environment**, not an installed, signed,
  commercial Windows product. It does not prove native VIOSO 7 `.sps`
  interoperability, CP PLUS optical input, dual-projector synchronization,
  or physical edge-blend acceptance.

The companion hardware gates remain tracked in
[Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).
Owner projectors may remain **OFF**.
