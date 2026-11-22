"""The bundled demo changes (Demo data): demo/changes/<key>.json. Phase 6d.

Connecting a real repository host is not in this version. On the demo a developer's change comes in through "Bring in
a demo change": the app writes the chosen change into the assessment's own copy of the demo repository as a push
would, one branch with one commit by "Demo developer". Each file here describes one such change: its branch, its
commit message and the files it leaves in the repository.

A file's content is either a short text written in the change itself, or the name of one of our registered demo
programs: then the bytes are that program's, read from the registry (`app/run/components.py`). So no change adds a
program, and none holds program text of its own. A demo change is data: nothing in it runs. Whether the code a
change leaves behind may run is decided later, by the byte-for-byte check, exactly as for any other change.

Only the keys in `ORDER` are read. No path is ever made from a name that came from outside.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import DEMO_DIR
from app.fixes.gitrepo import GitRepoError, check_branch_name, check_file_name
from app.run import components

CHANGES_DIR = DEMO_DIR / "changes"
SCHEMA = "evidence-lab-demo-change-1"
ORDER = ("revert-range-check", "allow-tls-1-0")  # the menu's order
OFFERED = (
    "connected",
    "after_merge",
)  # when the menu offers a change: once the code is connected, or once a fix is merged

MAX_BYTES = 64 * 1024
MAX_FILES = 5
MAX_TEXT = 4000
_KEY = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_FIELDS = {"schema", "key", "title", "what_it_does", "branch", "message", "offered", "files"}
_PROGRAM_ENDINGS = (".py", ".pyc", ".pyw", ".sh", ".js", ".mjs", ".rb", ".pl", ".php", ".exe", ".so", ".jar", ".class")


def _program_files() -> set[str]:
    """The file names of our registered demo programs: a text file of a change may not take one of them."""
    names = set(components.VERSIONS) | set(components.CHANGE_VERSIONS)
    paths = (
        components.lookup(n, v)
        for n in sorted(names)
        for v in components.VERSIONS.get(n, []) + components.CHANGE_VERSIONS.get(n, [])
    )
    return {path.name for path in paths if path is not None}


class DemoChangeError(Exception):
    """A demo change file could not be read. The message is plain and safe to show."""


@dataclass(frozen=True)
class DemoFile:
    name: str
    text: str | None  # the content, written in the change
    registered: tuple[str, str] | None  # or: one of our registered demo programs (name, version)


@dataclass(frozen=True)
class DemoChange:
    key: str
    title: str
    what_it_does: str
    branch: str
    message: str
    offered: str
    files: tuple[DemoFile, ...]


def _text(value: object, what: str, most: int, lines: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > most:
        raise DemoChangeError(f"The demo change has no usable {what}.")
    if any(ord(ch) < 32 and not (lines and ch == "\n") for ch in value) or "\x7f" in value:
        raise DemoChangeError(f"The demo change's {what} holds a character that is not text.")
    return value


def _file(entry: object) -> DemoFile:
    if not isinstance(entry, dict) or "name" not in entry or len(entry) != 2:
        raise DemoChangeError("A file of the demo change is not written as this app expects.")
    try:
        name = check_file_name(entry["name"])
    except GitRepoError as exc:
        raise DemoChangeError("A file of the demo change has a name this app does not accept.") from exc
    if "text" in entry:
        # (a program is never written out in a change: it comes only by the name of one of our registered demo programs)
        if name.lower().endswith(_PROGRAM_ENDINGS) or name in _program_files():
            raise DemoChangeError(
                "A file of the demo change is a program written out in the change, which this app does not accept."
            )
        text = _text(entry["text"], "file text", MAX_TEXT, lines=True)
        if not text.endswith("\n"):
            raise DemoChangeError("A file of the demo change does not end with a line break.")
        return DemoFile(name, text, None)
    named = entry.get("registered")
    if (
        not isinstance(named, dict)
        or set(named) != {"name", "version"}
        or not all(isinstance(v, str) for v in named.values())
    ):
        raise DemoChangeError("A file of the demo change is not written as this app expects.")
    path = components.lookup(named["name"], named["version"])
    # (the file must be that program's own file: a change cannot put a registered program under another name)
    if path is None or path.name != name:
        raise DemoChangeError(
            "A file of the demo change names a program that is not one of our registered demo programs."
        )
    return DemoFile(name, None, (named["name"], named["version"]))


def read_change(data: bytes) -> DemoChange:
    """One demo change from the bytes of its file, held to the exact form this app writes. Anything else is refused."""
    if not isinstance(data, bytes | bytearray) or len(data) > MAX_BYTES:
        raise DemoChangeError("The demo change file is too large.")
    try:
        raw = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise DemoChangeError("The demo change file is not readable JSON.") from exc
    if not isinstance(raw, dict) or set(raw) != _FIELDS or raw.get("schema") != SCHEMA:
        raise DemoChangeError("The demo change file is not written as this app expects.")
    key = raw["key"]
    if not isinstance(key, str) or len(key) > 40 or not _KEY.fullmatch(key):
        raise DemoChangeError("The demo change has no usable key.")
    try:
        branch = check_branch_name(raw["branch"])
    except GitRepoError as exc:
        raise DemoChangeError("The demo change names a branch this app does not accept.") from exc
    if raw["offered"] not in OFFERED:
        raise DemoChangeError("The demo change does not say when it is offered.")
    files = raw["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise DemoChangeError("The demo change must leave between one and five files.")
    read = tuple(_file(entry) for entry in files)
    if len({f.name for f in read}) != len(read):
        raise DemoChangeError("The demo change names a file twice.")
    return DemoChange(
        key=key,
        title=_text(raw["title"], "title", 80),
        what_it_does=_text(raw["what_it_does"], "description", 300),
        branch=branch,
        message=_text(raw["message"], "commit message", 1000, lines=True),
        offered=raw["offered"],
        files=read,
    )


def bundled(folder: Path | None = None) -> list[DemoChange]:
    """The demo changes that ship with the app, in the menu's order. One that is missing or cannot be read is left
    out (the menu then does not offer it); nothing is made up in its place."""
    out = []
    for key in ORDER:
        try:
            change = read_change(((folder or CHANGES_DIR) / f"{key}.json").read_bytes())
        except (OSError, DemoChangeError):
            continue
        if change.key == key:
            out.append(change)
    return out


def find(key: object, folder: Path | None = None) -> DemoChange | None:
    """Exact match on one of our own keys only."""
    return next((c for c in bundled(folder) if c.key == key), None) if isinstance(key, str) and key in ORDER else None


def content(change: DemoChange) -> dict[str, bytes]:
    """The bytes of each file the change leaves in the repository. A registered program's bytes are read from the
    registry now; nothing is run to get them."""
    out = {}
    for file in change.files:
        if file.registered is not None:
            path = components.lookup(*file.registered)
            if path is None:
                raise DemoChangeError(
                    "The demo change names a program that is not one of our registered demo programs."
                )
            try:
                out[file.name] = path.read_bytes()
            except OSError as exc:
                raise DemoChangeError("The demo program the change names could not be read.") from exc
        else:
            out[file.name] = (file.text or "").encode("utf-8")
    return out


__all__ = [
    "CHANGES_DIR",
    "DemoChange",
    "DemoChangeError",
    "DemoFile",
    "OFFERED",
    "ORDER",
    "SCHEMA",
    "bundled",
    "content",
    "find",
    "read_change",
]
