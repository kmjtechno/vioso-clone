# VIOSO-Clone — Claude Code compact/restart checkpoint

> Short-lived factual handoff, not a task log. **Update after each verified milestone. Keep <=60 lines.**
> This file is deliberately separate from automatically loaded CLAUDE.md to save session context.

## Last verified from GitHub (2026-11-03)
- Repo: `kmjtechno/vioso-clone`, branch `main`.
- Base `main` SHA at preparation: `472b3c67d94e84495b8e8fc5d03e925c7c524477`.
- PR #13, #14 and #16 merged; PRs #17–25 open at preparation time.
- PR #25 documentation depends on #17; PR #24 README links #17 material. Check current merge bases before integration.
- Project has `vclone/calib.py`, `intrinsics.py`, `render.py`, `gui.py`, `project.py`, `script.py`, `remote.py`, `player.py` and tests. Do not delete wholesale.
- Repo `SPEC.md` and pending PR #17/#25 include *incomplete* static evidence for `.sps` save/load. No compatible format verified yet.

## Local environment (verify; not a live receipt)
- Owner P520 checkout: `E:\KMJ\Codex\VIOSO-Clone`
- Reference executable: `C:\Program Files\VIOSO7\SPCalibrator64.exe`
- Companion native library: `SPeASY64.dll` under the installed VIOSO7 location if present.
- REA/Ghidra: may require tool health and JDK/version checks. Never assume connected or successful.
- Current working branch: **UNKNOWN UNTIL CHECKED LOCALLY**.
- Current dirty/untracked files: **UNKNOWN UNTIL CHECKED LOCALLY**.
- Current tests: **NOT RUN BY THIS CHECKPOINT**.
- Hardware acceptance: **NOT VERIFIED**.

## Next bounded task
1. Check Git status, current PRs and REA tool/Java/Ghidra availability **without printing secrets or enormous outputs**.
2. Select one small item: validate current REA `.sps` evidence, or add an independent regression test for the selected open safety PR.
3. Make one focused change with tests. Record exact SHA, test counts and evidence type; then update this file.

## Keep here at next handoff
- `NEXT_TASK:` one sentence with an acceptance test.
- `BRANCH/HEAD:` exact git references, if verified.
- `FILES_CHANGED:` short list.
- `TESTS:` exact command and pass/fail counts or NOT_RUN.
- `REA_EVIDENCE:` file path + relevant binary SHA/addresses, no giant transcript.
- `BLOCKERS:` actionable, verified only.
- `NEXT_ACTION:` one concrete first command/tool call.

No tokens, credentials, proprietary decompilation or private owner content in this document. No blind reset/clean or deletion.
