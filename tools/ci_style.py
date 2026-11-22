#!/usr/bin/env python3
"""Code style check for the files a change adds or edits (the GitHub check "Lint and code style").

Python files are checked with `ruff format` (backend/ruff.toml), TypeScript and JavaScript with Prettier
(.prettierrc.json, installed in lint/). Only the files that differ from BASE are looked at, so the code that was
already there does not have to be reformatted all at once:

  - a file the change ADDS must already be formatted: the check fails otherwise;
  - a file the change EDITS that is not formatted gets a warning, and the check still passes.

Usage (from anywhere in the repository):
  python3 tools/ci_style.py BASE         # BASE: a commit, e.g. origin/mvp/crypto-simple
  python3 tools/ci_style.py BASE --fix   # format those files in place instead of checking

The fix for a finding is the command it prints. Formatting changes layout only, never what the code does.
Standard library only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIRS = ("backend/",)
PRETTIER_DIRS = ("frontend/", "e2e/", "lint/")
PRETTIER_SUFFIXES = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".css")
# Generated files have their own up-to-date checks.
SKIP = {"frontend/src/api.gen.ts"}

IN_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"


def changed(base: str) -> dict[str, str]:
    """Path -> 'A' (added) or 'M' (edited) for every file that differs between BASE and the working tree."""
    out = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", "--diff-filter=AM", base, "--"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    files: dict[str, str] = {}
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path and path not in SKIP and (ROOT / path).is_file():
            files[path] = status[0]
    return files


def unformatted(tool: list[str], cwd: Path, paths: list[str], prefix: str = "") -> set[str]:
    """The paths (relative to the root) that the formatter would change. Each file is asked about by itself."""
    bad: set[str] = set()
    for path in paths:
        rel = path[len(prefix):] if prefix else path
        result = subprocess.run([*tool, rel], cwd=cwd, capture_output=True, text=True)
        if result.returncode == 1:
            bad.add(path)
        elif result.returncode != 0:
            sys.stderr.write(result.stdout + result.stderr)
            raise SystemExit(f"The formatter could not read {path} (exit code {result.returncode}).")
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="the commit to compare with")
    parser.add_argument("--fix", action="store_true", help="format the added and edited files in place")
    args = parser.parse_args()

    files = changed(args.base)
    python = sorted(p for p in files if p.endswith(".py") and p.startswith(PYTHON_DIRS))
    web = sorted(p for p in files if p.endswith(PRETTIER_SUFFIXES) and p.startswith(PRETTIER_DIRS))

    ruff = str(ROOT / "backend/.venv/bin/ruff")
    prettier = str(ROOT / "lint/node_modules/.bin/prettier")
    for tool, needed in ((ruff, python), (prettier, web)):
        if needed and not Path(tool).exists():
            raise SystemExit(f"{tool} is not installed (see CLAUDE.md, Commands).")

    if args.fix:
        if python:
            subprocess.run([ruff, "format", *(p.removeprefix("backend/") for p in python)], cwd=ROOT / "backend", check=True)
        if web:
            subprocess.run([prettier, "--write", *web], cwd=ROOT, check=True)
        print(f"Formatted {len(python)} Python and {len(web)} TypeScript/JavaScript/CSS files.")
        return 0

    bad = unformatted([ruff, "format", "--check", "--quiet"], ROOT / "backend", python, "backend/")
    bad |= unformatted([prettier, "--check", "--log-level", "silent"], ROOT, web)

    failures = sorted(p for p in bad if files[p] == "A")
    warnings = sorted(p for p in bad if files[p] == "M")
    print(f"Code style: {len(python)} Python and {len(web)} TypeScript/JavaScript/CSS files differ from {args.base}.")
    for path in warnings:
        msg = "Edited file is not formatted (a warning; the code that was there before is not held to the style yet)."
        print(f"::warning file={path}::{msg}" if IN_GITHUB else f"warning: {path}: {msg}")
    for path in failures:
        msg = "New file is not formatted."
        print(f"::error file={path}::{msg}" if IN_GITHUB else f"error: {path}: {msg}")
    if bad:
        print(f"To format them: python3 tools/ci_style.py {args.base} --fix")
    if failures:
        print(f"{len(failures)} new file(s) not formatted: the check fails.")
        return 1
    print(f"Passed ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
