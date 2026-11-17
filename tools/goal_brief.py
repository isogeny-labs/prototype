#!/usr/bin/env python3
"""Print what the next session should work on.

Sources, in priority order:
  1. docs/ACTIVE.md  - the owner's pinned goal and active items (optional).
  2. The "Open threads" sections of the newest dated session logs in
     docs/session-logs/ (YYYY-MM-DD.md and YYYY-MM-DD-<slug>.md).

Used by the SessionStart hook (so every Claude session starts with it in
context), the /goal command, and the Codex SessionStart hook (--hook-json). Read-only and never fatal: a missing file prints a
note and exits 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-[\w.-]+)?\.md$")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
OPEN = re.compile(r"open threads", re.I)
STANDARD = re.compile(r"^(what was done|decisions made|open threads|errors)", re.I)


def repo_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def dated_logs(log_dir: Path) -> dict[str, list[Path]]:
    by_date: dict[str, list[Path]] = {}
    if not log_dir.is_dir():
        return by_date
    for p in log_dir.iterdir():
        m = DATED.match(p.name)
        if m and p.is_file():
            by_date.setdefault(m.group(1), []).append(p)
    for files in by_date.values():
        # Topic logs first, the shared daily file last, so its newest entries end the list.
        files.sort(key=lambda p: (p.name == f"{p.name[:10]}.md", p.name))
    return by_date


def open_threads(path: Path) -> list[tuple[str, list[str]]]:
    """Return (entry title, open-thread lines) for each entry in a log file."""
    out: list[tuple[str, list[str]]] = []
    entry = path.name
    capture_level = 0
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = [l for l in buf if l.strip()]
        if body and not all(re.fullmatch(r"[-*]?\s*(none\.?|n/a|-)", l.strip(), re.I) for l in body):
            out.append((entry, body))
        buf = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        h = HEADING.match(line)
        if h:
            level = len(h.group(1))
            if capture_level and level <= capture_level:
                flush()
                capture_level = 0
            if OPEN.search(h.group(2)):
                capture_level = level
                continue
            if level <= 3 and not STANDARD.match(h.group(2)):
                entry = f"{path.name} :: {h.group(2)}"
            continue
        if capture_level:
            buf.append(line.rstrip())
    if capture_level:
        flush()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--entries", type=int, default=6,
                    help="most recent entries with open threads to show (default 6)")
    ap.add_argument("--max-lines", type=int, default=120,
                    help="cap on printed lines, to keep session context small (default 120)")
    ap.add_argument("--hook-json", action="store_true",
                    help="emit SessionStart hookSpecificOutput JSON (Codex hooks)")
    args = ap.parse_args()

    root = repo_root()
    lines: list[str] = ["# Goal brief (tools/goal_brief.py)", ""]

    active = root / "docs" / "ACTIVE.md"
    if active.is_file():
        text = active.read_text(encoding="utf-8", errors="replace")
        # Skip the file's preamble; the brief needs only the goal and items.
        i = text.find("## Current goal")
        text = (text[i:] if i >= 0 else text).strip()
        lines += ["## Pinned goal and active items (docs/ACTIVE.md)", "", text, ""]
    else:
        lines += ["No docs/ACTIVE.md: no pinned goal; falling back to open threads.", ""]

    by_date = dated_logs(root / "docs" / "session-logs")
    found: list[tuple[str, list[str]]] = []
    for date in sorted(by_date)[-2:]:  # oldest first, so the list tail is newest
        for f in by_date[date]:
            found += open_threads(f)
    recent = found[-args.entries:] if len(found) > args.entries else found
    if recent:
        dates = ", ".join(sorted(by_date, reverse=True)[:2])
        lines += [f"## Open threads from the newest session logs ({dates})", ""]
        for title, body in reversed(recent):
            lines += [f"### {title}", *body, ""]
    else:
        lines += ["No open threads found in docs/session-logs/.", ""]

    lines += [
        "## Protocol",
        "Work the first unchecked item in docs/ACTIVE.md; if there is none, pick the",
        "open thread above that is most recent and not owned by another live session",
        "(check the open draft PRs). State the choice in one line. First step,",
        "before any other work: add or mark the task's line in docs/ACTIVE.md,",
        "commit it alone, push, and open a draft PR named after the task",
        "(AGENTS.md, \"First step of every task\"). Mark the PR ready when done.",
    ]
    if len(lines) > args.max_lines:
        lines = lines[: args.max_lines - 1] + [f"... (truncated at {args.max_lines} lines; rerun with --max-lines)"]
    text = "\n".join(lines)
    if args.hook_json:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": text}}))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never block a session start
        print(f"goal_brief: {exc}", file=sys.stderr)
        sys.exit(0)
