"""The type check (mypy), compared with a baseline, so only NEW problems fail (phase 4c+, development-only).

    .venv/bin/python tools/typecheck.py                    check; exit code 1 if there is a problem not in the baseline
    .venv/bin/python tools/typecheck.py --write-baseline   record today's problems as the baseline (after a fix, or
                                                           when a move changes file names; never to hide a new one)

The baseline (mypy-baseline.txt) lists each problem by file, message and code, without its line number, so moving
code around does not break it. A problem found more often than the baseline allows counts as new.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BASELINE = BACKEND / "mypy-baseline.txt"
LINE = re.compile(r"^(?P<path>[^:\s]+\.py):(?P<line>\d+): error: (?P<msg>.*?)\s+\[(?P<code>[a-z-]+)\]$")


def run_mypy() -> tuple[Counter, dict[str, list[str]], str]:
    proc = subprocess.run([sys.executable, "-m", "mypy", "--config-file", "mypy.ini"], cwd=BACKEND,
                          capture_output=True, text=True)
    found: Counter = Counter()
    where: dict[str, list[str]] = {}
    for raw in proc.stdout.splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        key = f"{m['path']}: {m['msg']} [{m['code']}]"
        found[key] += 1
        where.setdefault(key, []).append(f"{m['path']}:{m['line']}")
    # mypy exits 1 when it finds problems and 2 when it could not run at all
    if proc.returncode not in (0, 1):
        return found, where, proc.stdout + proc.stderr
    return found, where, ""


def read_baseline() -> Counter:
    allowed: Counter = Counter()
    if BASELINE.is_file():
        for line in BASELINE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                count, key = line.split("\t", 1)
                allowed[key] = int(count)
    return allowed


def main(argv: list[str]) -> int:
    found, where, failure = run_mypy()
    if failure:
        print("The type checker could not run:\n" + failure)
        return 2
    if "--write-baseline" in argv:
        lines = ["# Type-check problems that were already there (count, then file: message [code]). "
                 "Made by tools/typecheck.py --write-baseline."]
        lines += [f"{n}\t{key}" for key, n in sorted(found.items())]
        BASELINE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Baseline written: {sum(found.values())} problems in {len(found)} kinds.")
        return 0
    allowed = read_baseline()
    new = {key: n - allowed.get(key, 0) for key, n in found.items() if n > allowed.get(key, 0)}
    gone = sum(max(0, n - found.get(key, 0)) for key, n in allowed.items())
    if new:
        print(f"Type check: {sum(new.values())} new problem(s), not in the baseline:")
        for key in sorted(new):
            print(f"  {key}   (at {', '.join(where[key])})")
        return 1
    note = f" ({gone} fewer than the baseline: run with --write-baseline to record that)" if gone else ""
    print(f"Type check: no new problems{note}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
