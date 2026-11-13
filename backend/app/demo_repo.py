"""The demo repository that ships with the app: demo/repos/acme-sign.git (Demo data).

This is what "Connect demo code" connects (SPEC 7b item 1): a small repository in git's own format with one
branch, `main`, and one commit that holds exactly our registered acme-sign 1.4.2 as `acme_sign.py`.

Only this module makes it, from fixed values (author, time, message), so making it again gives the same commit
id. After a change to the registered 1.4.2 file, make it again:

    cd backend && .venv/bin/python -m app.demo_repo

The component's file is copied as data: nothing is run here, and the git program is not needed.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import components
from .config import DEMO_DIR
from .gitrepo import GitRepo, GitRepoError, Person

REPOS_DIR = DEMO_DIR / "repos"
NAME, VERSION = "acme-sign", "1.4.2"   # the registered demo component the repository starts from
BRANCH = "main"
AUTHOR = Person("Acme Pay demo", "demo@example.invalid")
WHEN = 1794300000                      # a fixed time (10 November 2026, UTC), so the commit id never changes


def bundled(name: object) -> Path | None:
    """Where the bundled repository of a demo component is, or None when we ship none for it.
    Exact match on our one name only: no path is ever made from a name that came from outside."""
    return REPOS_DIR / f"{NAME}.git" if name == NAME else None


def make(folder: Path) -> str:
    """Make the demo repository in `folder` (new or empty) and return the id of its one commit."""
    source = components.lookup(NAME, VERSION)
    if source is None or not source.is_file():
        raise GitRepoError(f"The demo component {NAME} {VERSION} is missing, so the demo repository was not made.")
    repo = GitRepo.create(folder, BRANCH)
    return repo.commit(BRANCH, {source.name: source.read_bytes()}, f"{NAME} {VERSION} (demo software)", AUTHOR, WHEN, None)


def main(say=print) -> int:
    """Make the bundled repository again, in place. It is made next to the old one first and swapped in only
    when that worked, so a failure leaves the old one as it was."""
    target = REPOS_DIR / f"{NAME}.git"
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="making-", dir=REPOS_DIR))
    try:
        commit = make(scratch / target.name)
        if target.exists():
            shutil.rmtree(target)
        os.replace(scratch / target.name, target)
    except GitRepoError as exc:
        say(f"Demo repository: not made. {exc}")
        return 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    say(f"Demo repository: {target}")
    say(f"  branch {BRANCH}, commit {commit} ({NAME} {VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
