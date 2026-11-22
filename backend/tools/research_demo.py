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

    cd backend && .venv/bin/python tools/research_demo.py --sandbox DIR

Sandbox research (a prototype, only on a computer marked as Isogeny's own sandbox). It makes, in DIR:
    source/    what the advisory source says about starkbank-ecdsa, as recorded answers, for "day 1": the published
               record with its fixed version taken out, labelled Demo data (a weakness with no fix yet, for the Watch
               list). `--day 2` writes the record as it was published, with its fixed version: run it again with
               that, on the same DIR, to play the day the fix is published.
    registry/  what PyPI says about starkbank-ecdsa (the documents kept in demo/sandbox/registry, cut down to the
               fields the app reads) and the six public package files they name. The files are not in the
               repository: they are fetched once from files.pythonhosted.org, each checked against its pinned
               SHA-256, and kept in data/downloads like the pinned library files.
Then it prints the command that starts the app on that folder. In the app: Settings, turn Sandbox research on;
bring in demo/sandbox/starkbank-file.csv; open Change watch, Watch list, press Look now.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))       # (run as a script: the app's own modules, for the pinned download)
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


# ---------------------------------------------------------------- sandbox research (a prototype)

SANDBOX = REPO / "demo" / "sandbox"
SANDBOX_LIBRARY = "starkbank-ecdsa"
SANDBOX_ADVISORY = "GHSA-92vm-mxjf-jqf3"          # CVE-2021-43572, as the GitHub Advisory Database publishes it
SANDBOX_FILE = SANDBOX / "starkbank-file.csv"
SANDBOX_RECORDED_ON = "2026-11-22"                # the day the records in demo/sandbox/advisories were read
_PYPI = "https://files.pythonhosted.org/packages"
# The six public files the recorded PyPI documents name for the versions a trial of that advisory uses, each pinned
# by the SHA-256 PyPI itself gives for it.
SANDBOX_PINS = [
    {"file": "starkbank-ecdsa-1.1.0.tar.gz", "sha256": "423f81bb55c896a3c85ee98ac7da98826721eaee918f5c0c1dfff99e1972da0c",
     "url": f"{_PYPI}/4c/48/29de0f3876d8f89906372da49f132e5c5e46e2fa601a198a9eca6402f646/starkbank-ecdsa-1.1.0.tar.gz"},
    {"file": "starkbank-ecdsa-1.1.1.tar.gz", "sha256": "f7b434b4a1e0ba082fb1804b908b79523973fd17b1fde377078857f7cee299d1",
     "url": f"{_PYPI}/8c/1a/56b8dabc52dac3dd2c83def8f3dab666479ea1afe04a8b8e443ce62a2434/starkbank-ecdsa-1.1.1.tar.gz"},
    {"file": "starkbank-ecdsa-2.0.0.tar.gz", "sha256": "71dec991bf6f5bf80cb0a57141ca69aae87e12a0385105feca87e26e7efa3681",
     "url": f"{_PYPI}/2e/95/5c3453352eb01a8a0293ec6813e1c4318b62a853599e5e852b62d9a387dc/starkbank-ecdsa-2.0.0.tar.gz"},
    {"file": "starkbank-ecdsa-2.0.1.tar.gz", "sha256": "fe7e36b580da097cc8c0a120e3b7ba335e3901b970a484fd5ce856c026ef7714",
     "url": f"{_PYPI}/bf/03/e62f16fe4b5b565859d0d6b06a7b7b4b762a02d185e9e71baaa954ba14eb/starkbank-ecdsa-2.0.1.tar.gz"},
    {"file": "starkbank-ecdsa-2.0.2.tar.gz", "sha256": "4b60ebc493f024f2891516a6c140fcc711c16999468c8594bc1097ca5aed759f",
     "url": f"{_PYPI}/90/58/6fcffc262d2d90aba14878d22bf7d331a74f3190fdd79aa1df8700fd4f81/starkbank-ecdsa-2.0.2.tar.gz"},
    {"file": "starkbank_ecdsa-2.3.1-py3-none-any.whl", "sha256": "c6dcb0caeb5d7d181c3ef0a6b0185df700d4fa5d5e5669b40bc6d20816aa25a8",
     "url": f"{_PYPI}/68/f3/6d0a27fe51ba9cca11a1d5f44616ba384c1326ab704d74e4367839a67219/starkbank_ecdsa-2.3.1-py3-none-any.whl"},
]


def sandbox_record(day: int) -> dict:
    """What the source says about the weakness. Day 2: the record exactly as it was published. Day 1 is DEMO DATA: the
    same record with its fixed version taken out and its title marked, to show a weakness that has no fix yet."""
    record = json.loads((SANDBOX / "advisories" / f"{SANDBOX_ADVISORY}.json").read_text(encoding="utf-8"))
    if day >= 2:
        return record
    for affected in record["affected"]:
        for each in affected.get("ranges") or []:
            each["events"] = [event for event in each["events"] if "fixed" not in event and "last_affected" not in event]
    record["summary"] = "Demo data: " + str(record.get("summary") or "")
    return record


def sandbox_source(folder: Path, day: int) -> Path:
    """The recorded advisory source for one day. Written over what was there: a later day at the source."""
    folder.mkdir(parents=True, exist_ok=True)
    # ("recorded_on": the day these records were read, so a replay on a later day shows that day and the recorded answers still fit)
    (folder / f"PyPI__{SANDBOX_LIBRARY}.json").write_text(
        json.dumps({"recorded_on": SANDBOX_RECORDED_ON, "vulns": [sandbox_record(day)]}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder


def sandbox_files(downloads: Path | None = None) -> list[Path] | None:
    """The six pinned public files, from the kept copies or fetched once. None when one could not be had."""
    from app import prepare
    found = [prepare.fetch(pin, downloads or prepare.DOWNLOADS_DIR) for pin in SANDBOX_PINS]
    return None if any(path is None for path in found) else found     # type: ignore[return-value]


def sandbox_registry(folder: Path, downloads: Path | None = None) -> Path | None:
    """The recorded registry: the documents kept in the repository, and the six files. None when a file is missing."""
    files = sandbox_files(downloads)
    if files is None:
        return None
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(SANDBOX / "registry", folder, ignore=shutil.ignore_patterns("README.md"))
    (folder / "files").mkdir(exist_ok=True)
    for path in files:
        shutil.copyfile(path, folder / "files" / path.name)
    return folder


def prepare_sandbox(folder: Path, day: int = 1, downloads: Path | None = None) -> tuple[Path, Path | None]:
    """Make DIR/source for this day and DIR/registry. Returns the two folders (the second is None when a public file
    could not be fetched: the Watch list can still be seen, a research run can't make its copies)."""
    return sandbox_source(folder / "source", day), sandbox_registry(folder / "registry", downloads)


def main_sandbox(args: list[str]) -> int:
    day = 1
    if "--day" in args:
        at = args.index("--day")
        day = 2 if args[at + 1:at + 2] == ["2"] else 1
        del args[at:at + 2]
    if len(args) != 1:
        print("Usage: python tools/research_demo.py --sandbox [--day 2] DIR")
        return 1
    folder = Path(args[0]).resolve()
    source, registry = prepare_sandbox(folder, day)
    print(f"Prepared {folder} for day {day}: " + ("the weakness has no fix yet (Demo data)." if day == 1 else "the fix is published (the record as published)."))
    if registry is None:
        print("The public package files could not be fetched (files.pythonhosted.org), so a research run can't make its copies yet.")
    if day == 1:
        print("Start the app on it with (from the repository's top folder):")
        print(f"  EVIDENCE_LAB_SANDBOX_RESEARCH=1 EVIDENCE_LAB_DATA_DIR={folder / 'data'} EVIDENCE_LAB_ADVISORY_SOURCE={source} "
              f"EVIDENCE_LAB_REGISTRY_SOURCE={folder / 'registry'} ./run-demo.sh")
        print(f"Then: Settings, turn Sandbox research on; bring in {SANDBOX_FILE.relative_to(REPO)}; open Change watch, Watch list, "
              "press Look now. Run this command again with --day 2 and press Look now again to see the fix arrive.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--sandbox" in args:
        args.remove("--sandbox")
        return main_sandbox(args)
    if len(args) != 1:
        print("Usage: python tools/research_demo.py DIR   (or: --sandbox [--day 2] DIR)")
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
