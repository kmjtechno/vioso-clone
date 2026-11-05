# M43 — Pull FULL Git source history onto the owner P520, no clobber

Always independently verify the current 40-character GitHub `main` SHA
before owner-local execution. M45 corrects the default destination after
the owner explicitly chose a nested `FullSource` folder.
The owner P520 is online through CodeBridge, but its existing branch
`feat/sps-container-m5` contains modified files and untracked REA research.
**CodeBridge cannot fetch remotely**: the opt-in
`worktree_lane_prepare_cached_main` returned
`WORKTREE_REMOTE_HEAD_MISMATCH`; the only registered local commands are
`python_verify:test` and `rea_doctor:check`. Do not use those commands to
smuggle an unapproved Git fetch.

## Owner-controlled local execution (Windows, non-admin)

A script is available at
`scripts/windows/M43-VIOSO-P520-FULL-SOURCE-AND-QA.ps1`. Review it before
running. The file can be downloaded via ChatGPT or the authenticated GitHub
repository. It requires the already-created directory
`E:\KMJ\Codex\VIOSO-Clone\FullSource`, Git for Windows and, for
optional QA, an installed Python 3 interpreter.

- The default invocation **without** `-Execute` only validates and prints
  the proposed target. No network or file modifications.
- An explicitly approved `-Execute` verifies GitHub remote main's
  **exact 40-character SHA** before clone. Any moved SHA fails closed.
- The clone is a fresh **child of the owner-selected project folder**:
  `E:\KMJ\Codex\VIOSO-Clone\FullSource\VIOSO-Clone-FullSource-<first12SHA>`.
  If the destination exists (including a partial prior attempt), refuse to
  overwrite it.
  No `reset`, `clean`, `pull` or mutation of the original dirty checkout.
- Git remote operations run from a separate, verified regular OS temporary
  directory, outside the original checkout's inherited local Git settings.
- It uses `git clone --no-checkout` **without** `--depth` or
  `--single-branch`, verifying that the Git database is **not shallow** and
  that detached HEAD equals the verified SHA. This retains remote branch
  history/tags in the new clone.
- Private repo authentication uses an already-authorized GitHub CLI token
  (if present) as a process-only Git HTTP header, removed before checkout;
  otherwise it uses existing Git Credential Manager authorization. No
  secrets are printed, written to Git config or pasted into this chat.
- Explicit `-RunQA` creates a Python virtualenv **only inside** the
  new clone, installs `[gui,test]`, executes full local pytest and an
  offscreen GUI self-test. No real camera or projector is accessed.

Example *after obtaining and reviewing the script*, from the directory
containing the script, with the exact SHA independently verified as current:

```powershell
.\M43-VIOSO-P520-FULL-SOURCE-AND-QA.ps1 -ExpectedMainSha <CURRENT_VERIFIED_MAIN_40_HEX> -Execute -RunQA
```

If local PowerShell prevents an unsigned script, respect the owner's
execution/signing policy. On systems configured for RemoteSigned, inspect
the downloaded file and explicitly unblock that known file if trusted.
Do not globally change execution policies or disable system defenses.

## Results and remaining barriers

M43 hosted Windows CI runs PowerShell parsing and plan-only negative gates,
a genuine **full-history private repository clone** and full synthetic GUI
regression on an isolated GitHub Windows runner. Hosted CI is **not** P520
hardware execution.

Even with full source and GUI QA locally green, actual CP PLUS RTSP stream,
USB webcam, raw fisheye calibration, two physical projectors, real optical
coverage/color blend and native proprietary VIOSO 7 SPS parity remain
**NOT VERIFIED**. See
[Issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).

The original P520 checkout is never altered, and both projectors can remain
OFF for initial installation and camera-only checks. No paid AI provider,
extra storage tier or unsafe source overwrite is required.
