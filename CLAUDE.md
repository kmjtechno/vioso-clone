# Claude Code — VIOSO-Clone durable context (short by design)

## Project / mission
- Repo: `kmjtechno/vioso-clone`; owner P520 checkout: `E:\KMJ\Codex\VIOSO-Clone`.
- Reference software, for permitted *read-only research*: `C:\Program Files\VIOSO7\SPCalibrator64.exe` and companion `SPeASY64.dll`.
- Build a **separately authored** projector-calibration tool. Preserve existing working modules and tests. Do not claim original vendor source recovery, hardware parity, or .sps compatibility without evidence.
- Never copy decompiled/proprietary source or assets, bypass activation/license/security checks, or distribute original binaries. Zero additional paid services; P520 only, leave P720 and other agents alone.

## On EVERY session start OR after compaction
1. Read `docs/CLAUDE_HANDOFF.md` (short durable checkpoint). Treat its SHA/status as a snapshot; recheck `git rev-parse HEAD`, `git status --short`, and currently open PRs before edits.
2. Select **one** bounded, testable task from the checkpoint. Do not re-read all source, full chat history, all PR diffs, or giant REA output just to resume.
3. Work on a dedicated branch/worktree; preserve dirty and untracked owner files. No git reset/clean, force push, mass deletion, or unsafe production actions.

## Context budget — prevent compaction loops
- **Do not paste entire functions, decompilation reports, cross-reference graphs, binary dumps or long test logs into the chat.** Search narrow targets and request bounded output. For REA: one DLL/function family at a time, ~1–3 functions per investigation; report a short findings table with binary SHA, addresses, confidence, and next test.
- Keep bulky read-only raw observations **local and private**; put only concise original-language findings (no copied proprietary code) into a scoped evidence note.
- For extensive REA reconnaissance, use a focused subagent (see `.claude/agents/rea-scout.md`) that returns **at most 10 findings**; parent session handles implementation and tests. If tools are missing, report actual error codes.
- Prefer targeted file slices and `pytest -q` summaries over recursive file dumps. Inspect failure details only as needed.
- Do NOT repeatedly issue `/compact` or re-send the full master prompt. Auto-compaction can still occur; keep work recoverable. When a completed milestone needs a fresh session, update handoff first.

## Milestone completion contract
1. Repro/test first, modify minimal affected files, run relevant + full tests when feasible.
2. Commit or open a focused PR, then **update `docs/CLAUDE_HANDOFF.md`** with branch, last tested SHA, relevant test results, blockers, and the single next task. Cap the handoff to ~60 lines; replace stale entries rather than appending history.
3. Distinguish synthetic/CI/P520 physical evidence. Preserve open PR dependencies (#25 is stacked on #17 until retargeted).
4. Continue to the next independent milestone; never claim a tool, test or process is running unless verified.
