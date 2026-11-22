"""The pin of Adam's Otto harness (backend/otto.lock.json), moved on purpose and never by itself.

    .venv/bin/python tools/otto_pin.py show                      what is pinned, and whether it is on this computer
    .venv/bin/python tools/otto_pin.py bump COMMIT [--source DIR]   pin another commit (40 hex characters)
    .venv/bin/python tools/otto_pin.py check                     Otto's own tests and audit, from the pinned copy

`bump` fetches that commit (from a local checkout given with --source, else from the repository with this
computer's own git access), works out its fingerprint and version, writes the lock and installs the copy. After a
bump, run `check`, then the backend tests and the accuracy check: a failed audit of a ledger we keep stops the bump.
Changing the pin needs Kevin's OK, like any dependency change.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.otto import harness  # noqa: E402


def show() -> int:
    found = harness.status()
    print(found.sentence)
    if found.commit:
        print(f"Pinned: {found.repository} at {found.commit} (version {found.version}).")
    return 0 if found.installed else 1


def bump(commit: str, source: str | None) -> int:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        print("Give the full commit id: 40 hex characters.")
        return 2
    try:
        url = harness.read_lock().url
        repository = harness.read_lock().repository
    except harness.OttoNotInstalled:
        url, repository = "https://github.com/isogeny-labs/otto", "isogeny-labs/otto"
    archive = harness.archive_of(commit, Path(source) if source else None, url)
    if archive is None:
        print("Could not fetch that commit (no access to the repository, no internet, or git is missing).")
        return 1
    with tempfile.TemporaryDirectory(prefix="otto-pin-") as folder:
        work = Path(folder)
        if not harness._unpack(archive, work):
            print("The fetched files could not be unpacked.")
            return 1
        try:
            text = (work / "otto" / "__init__.py").read_text(encoding="utf-8")
            found = re.search(r'__version__\s*=\s*"([^"]+)"', text)
            if found is None:
                raise OSError("no version")
            version = found.group(1)
        except OSError:
            print("That commit has no otto/__init__.py with a version in it.")
            return 1
        lock = {"repository": repository, "url": url, "commit": commit, "version": version,
                "tree_sha256": harness.tree_sha256(work),
                "note": "One exact commit of Adam's Otto harness. Fetched by app.prepare into backend/.otto/<commit>/, "
                        "never copied into this repository. Move it with tools/otto_pin.py, on purpose."}
    harness.LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    harness._forget()
    ok = harness.fetch(harness.read_lock(), say=print)
    print(f"Pinned {repository} at {commit} (version {version}). Installed: {'yes' if ok else 'no'}.")
    return 0 if ok else 1


def check() -> int:
    """Adam's own two checks, run on a throwaway copy of the pinned files: his unit tests and the audit of his worked example."""
    try:
        done = harness.own_checks()
    except harness.OttoNotInstalled:
        print(harness.status().sentence)
        return 1
    print("Otto's own tests:", done["tests_line"])
    print("Otto's audit of its worked example:", done["audit_line"])
    return 0 if done["tests_ok"] and done["audit_ok"] else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["show"]:
        return show()
    if argv[:1] == ["bump"] and len(argv) >= 2:
        source = argv[argv.index("--source") + 1] if "--source" in argv and argv.index("--source") + 1 < len(argv) else None
        return bump(argv[1], source)
    if argv[:1] == ["check"]:
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
