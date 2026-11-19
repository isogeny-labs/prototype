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

- [ ] Overnight run: the 5c fixes, then phase 6 (the Otto assistant, 6a to 6e) and Otto's research loop — **in progress** (claude, started 2026-11-19, branch overnight/fixes-and-phase6, PR #7). Kevin approved the plan in advance and reviews the next day; `docs/HANDOFF-overnight.md` says after every step what is done, what is left and the exact next action. Never merged into `mvp/crypto-simple` by the session.
- [x] Phase 5c: Otto in Evidence Lab — **done and merged** (claude, started 2026-11-17, finished 2026-11-18; branch wip/5c-otto, PR #6). The first build, and the owner's acceptance criteria of 2026-11-18 (Otto proposes, a person accepts or rejects; two proof rows; Otto on every tab), are built, checked and reviewed three times; counts and what the reviews found are in docs/HANDOFF.md, the walk's pictures in docs/screenshots/phase5c/, and the plain-English report is the doc "Phase 5c report: Otto in Evidence Lab". What is left is the owner's: the questions below.

## Blocked / questions for the owner

From phase 5c (details in `docs/HANDOFF.md` and in the doc "Phase 5c report: Otto in Evidence Lab", under "Yours to decide"). None blocked the merge of PR #6; each is the owner's to decide:

- "Who" is recorded as "You", the name approvals already record. A sign-off at closing takes a typed name, so the two differ; a typed name asked once would be a small change.
- The row name "Proven on your system": the row is a retest on a public copy of the updated version (the app does not connect to the system a customer runs), and a note under the row says so. Another name, for example "Proven in this assessment", may be wanted.
- A library's fix whose retest passed still counts as Open on Fixes, because its status word stays "Text only".
- Plan changes come from one rule (a failed advisory check on a signing program whose status is measured). "Measured" on Dependencies counts only this assessment's own check on the same library and version. A rejected fix of Otto's has no stand-in.
- The fast test set is at the five-minute limit on a slow day: allow parallel test runs (pytest-xdist, a new dev-only package), or move older flows to the slow set.
- Still open from the first build: the default spending limit of Live Otto (2 US dollars per run); Anthropic's official package, or the standard-library call as built; the fifth answer key, `demo/expected-otto.json`: who writes it and when (`docs/OTTO-KEY.md` has the questions).
