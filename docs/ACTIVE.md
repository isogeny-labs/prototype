# Active goal and items

Owner-pinned work queue. `tools/goal_brief.py` prints this file at the start
of every Claude and Codex session (SessionStart hooks) and for `/goal`
(AGENTS.md, "Goal: what to work on next"). When this file has no unchecked
item, sessions fall back to the newest "Open threads" in `docs/session-logs/`.

Keep it short: one goal, a few ordered items. Sessions add their task here as
the first step of the task (AGENTS.md, "First step of every task"), keep the
line current, and tick it when done; history belongs in the session log or the
PR, not in this file.

## Current goal

_(none pinned — set one with `/goal <text>`)_

## Active items (top = next)

<!-- One line per task, added as the task's first step with its draft PR:
- [ ] <task> (<runtime>, started YYYY-MM-DD, branch <branch>, PR #<n>) -->

- [ ] Phase 5c: Otto in Evidence Lab (claude, started 2026-11-17; first build checked 2026-11-18 on branch claude/trusting-goodall-m2i9g6, PR #6). On 2026-11-18 the owner set new acceptance criteria for the whole phase (Otto proposes, a person accepts or rejects; two proof rows; Otto on every tab). None of that is started. Continue from branch wip/5c-otto and read docs/HANDOFF-5c.md first. Don't merge PR #6 as it stands.

## Blocked / questions for the owner

From phase 5c (details in `docs/HANDOFF.md`, "Decisions waiting for Kevin", and in the doc "Phase 5c report: Otto in Evidence Lab"). None blocks the merge of PR #6; each is the owner's to decide:

- Otto's own change for `acme-sign` is not offered (its program is not byte for byte a registered demo program): keep that, register the program, or allow running a change Claude wrote (needs a sandbox design).
- The strict reading of "every other locked test still passes" (so "update Java to 17.0.3" reads "not proven").
- The default spending limit of Live Otto (2 US dollars per run).
- Anthropic's official package, or the standard-library call as built.
- Information-only lines on Advisories and Settings beyond the approved wording (SPEC 2 lists them).
- The packs were rebuilt before the merge ("a shipped pack is never rebuilt" was read as "once merged").
- The fifth answer key, `demo/expected-otto.json`: who writes it and when (`docs/OTTO-KEY.md` has the questions).
