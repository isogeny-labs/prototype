# Agent instructions

## Goal: what to work on next

Sessions should never need a prompt to find their work. `docs/ACTIVE.md`
holds the owner's pinned goal and ordered active items; the newest session
logs in `docs/session-logs/` (where they exist) hold the open threads.
`python3 tools/goal_brief.py` prints both, pinned items first, capped at 120
lines.

- **Claude** gets the brief from the SessionStart hook in
  `.claude/settings.json`. `/goal` (`.claude/commands/goal.md`) re-reads it
  and starts the next item; `/goal <text>` pins a new goal.
- **Codex and other runtimes** run `python3 tools/goal_brief.py` at session
  start (Codex gets it from `.codex/hooks.json` where that file exists) and
  treat a bare `goal` or `/goal` message like Claude's `/goal`.
- With no other instruction, take the first unchecked item in
  `docs/ACTIVE.md`; if there is none, the most recent open thread that no
  open draft PR already covers. State the choice in one line and start; ask
  only for decisions the brief marks as the owner's.

### First step of every task: record it in `docs/ACTIVE.md` and open a draft PR

Owner instruction, 2026-11-16. Before any other work on a task, every
session, skill and agent, in every runtime, does these steps first:

1. Fetch the default branch and create the task branch.
2. Add one line for the task under "Active items" in `docs/ACTIVE.md`:
   `- [ ] <task> (<runtime>, started <YYYY-MM-DD>, branch <branch>)`. If the
   task is already listed, mark that line in progress instead.
3. Commit that change alone, push, and open a **draft** PR named after the
   task. Its body says what will be done and how it will be checked. Add
   `PR #<n>` to the line in the next commit.

The draft PR is the tracking record: push to it as the work goes and keep
the line current. When the work is finished and checked, tick the line
(`- [x]`) or remove it, then **mark the PR ready for review** and enable
auto-merge (`gh pr merge <n> --auto --merge`) where the repository allows it.
A task that stops unfinished keeps its draft and its unticked line, with the
blocker under "Blocked / questions". When `docs/ACTIVE.md` conflicts, merge
the default branch and keep every other session's line. A subagent working
inside the parent's task uses the parent's line and PR.
