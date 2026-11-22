---
description: Pick up the next piece of work from docs/ACTIVE.md and the newest session-log open threads, or pin a new goal
argument-hint: "[new goal to pin, or empty to resume]"
allowed-tools: Bash(python3 tools/goal_brief.py:*)
---
Goal brief:

!`python3 tools/goal_brief.py`

Arguments: "$ARGUMENTS"

1. If the arguments are non-empty, make them the "Current goal" in
   `docs/ACTIVE.md` and break the goal into 3–7 ordered, checkable items
   under "Active items".
2. Otherwise take the first unchecked item in `docs/ACTIVE.md`. If there is
   none, take the most recent open thread in the brief that no open draft PR
   already covers.
3. State the choice and the first concrete step in at most three lines.
   Do not ask which item to take; ask only for a decision the brief marks as
   the owner's.
4. **First step, before any other work** (AGENTS.md, "First step of every
   task"): fetch the default branch, create the task branch, mark or add the
   task's line under "Active items" in `docs/ACTIVE.md`
   (`- [ ] <task> (claude, started <date>, branch <branch>)`), commit that
   alone, push, and open a **draft** PR named after the task. Add `PR #<n>`
   to the line. Then start the work.
5. Follow every CLAUDE.md / AGENTS.md rule that applies to the work itself.
6. Push to the draft PR as the work goes. When the task is finished and
   checked, tick its line in `docs/ACTIVE.md`, add follow-ups, then mark the
   PR ready for review and enable auto-merge. Blocked items stay unticked
   with the blocker under "Blocked / questions".
