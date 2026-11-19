"""Prepare a folder that shows Otto's research loop from start to finish, with no internet and no API key.

    cd backend && .venv/bin/python tools/research_demo.py DIR

It makes, in DIR:
    updates/   the first built-in test pack only (2026.11.1), so the three elliptic advisories of the second one
               are "new" on this copy of the app;
    source/    those three advisories as a recorded advisory source: exactly the entries of the dated snapshot in
               research/snapshot/, so the answers recorded during the build fit them.
Then it prints the one command that starts the app on that folder. In the app: bring in demo/real-libraries.csv,
open Advisories, press Look for new advisories, then Design and prove tests (isolated mode: Docker must be running).
Nothing here is new data: both files are copied from the repository. Nothing is sent anywhere.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIRST_PACK = REPO / "research" / "packs" / "2026.11.1.json"
SNAPSHOT = REPO / "research" / "snapshot" / "2026-11-17" / "advisories.json"
LIBRARY = "elliptic"


def prepare(folder: Path) -> tuple[Path, Path]:
    """Make DIR/updates and DIR/source. Returns the two folders."""
    updates, source = folder / "updates", folder / "source"
    updates.mkdir(parents=True, exist_ok=True)
    source.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIRST_PACK, updates / FIRST_PACK.name)
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    kept = {**snapshot, "about": "The elliptic advisories of the dated snapshot in research/snapshot/, as a recorded advisory source.",
            "advisories": [a for a in snapshot["advisories"] if a["package"]["name"] == LIBRARY]}
    (source / "elliptic-advisories.json").write_text(json.dumps(kept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return updates, source


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python tools/research_demo.py DIR")
        return 1
    folder = Path(args[0]).resolve()
    updates, source = prepare(folder)
    print(f"Prepared {folder}.")
    print("Start the app on it with (from the repository's top folder):")
    print(f"  EVIDENCE_LAB_DATA_DIR={folder / 'data'} EVIDENCE_LAB_OTTO_UPDATES={updates} EVIDENCE_LAB_ADVISORY_SOURCE={source} ./run-demo.sh")
    print("Then: bring in demo/real-libraries.csv, open Advisories, press Look for new advisories, then Design and prove tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
