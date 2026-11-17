"""The advisory snapshot: a dated file of real published advisories, each with pieces of its official text copied
word for word. It is DATA. This reader takes it only when it is exactly the shape below; anything else is refused
with one plain sentence, and nothing in it is ever run."""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA = "isogeny.advisory-snapshot/1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ADVISORIES = 50
MAX_SOURCES = 20
MAX_EXCERPTS = 12
MAX_EXCERPT_CHARS = 4000
MAX_ADVISORY_CHARS = 16000
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{3,39}$")   # e.g. GHSA-cj8x-r9fp-q656
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,59}$")


class SnapshotError(ValueError):
    """The snapshot can't be used. str(exc) is one plain sentence."""


def _text(value: object, what: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SnapshotError(f"The snapshot's {what} is missing, empty or too long.")
    return value


def _date(value: object, what: str) -> str:
    if not isinstance(value, str) or not _DATE.match(value):
        raise SnapshotError(f"The snapshot's {what} is not a date (year-month-day).")
    return value


def _link(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.startswith("https://") or len(value) > 400 or any(ch.isspace() for ch in value):
        raise SnapshotError(f"The snapshot's {what} is not an https address.")
    return value


def _keys(value: object, wanted: set, what: str) -> dict:
    if not isinstance(value, dict) or set(value) != wanted:
        raise SnapshotError(f"The snapshot's {what} does not have exactly the fields it must have.")
    return value


def check_snapshot(data: object) -> dict:
    """The snapshot, if it is exactly what a snapshot must be. Raises SnapshotError otherwise."""
    top = _keys(data, {"schema", "snapshot", "about", "advisories"}, "top level")
    if top["schema"] != SCHEMA:
        raise SnapshotError("This is not an advisory snapshot this version knows.")
    _date(top["snapshot"], "date")
    _text(top["about"], "description", 1000)
    advisories = top["advisories"]
    if not isinstance(advisories, list) or not 1 <= len(advisories) <= MAX_ADVISORIES:
        raise SnapshotError("The snapshot holds no advisories, or too many.")
    seen = set()
    for advisory in advisories:
        a = _keys(advisory, {"id", "aliases", "package", "published", "sources"}, "advisory")
        if not isinstance(a["id"], str) or not _ID.match(a["id"]) or a["id"] in seen:
            raise SnapshotError("An advisory in the snapshot has no plain id, or its id is there twice.")
        seen.add(a["id"])
        what = f"advisory {a['id']}"
        if not isinstance(a["aliases"], list) or len(a["aliases"]) > 8 or not all(isinstance(x, str) and _ALIAS.match(x) for x in a["aliases"]):
            raise SnapshotError(f"The other names of {what} are not plain ids.")
        package = _keys(a["package"], {"name", "ecosystem"}, f"package of {what}")
        if not all(isinstance(package[k], str) and _NAME.match(package[k]) for k in ("name", "ecosystem")):
            raise SnapshotError(f"The package of {what} is not a plain name.")
        _date(a["published"], f"publication date of {what}")
        sources = a["sources"]
        if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
            raise SnapshotError(f"{what.capitalize()} has no source, or too many.")
        total = 0
        for source in sources:
            s = _keys(source, {"title", "publisher", "url", "fetched_from", "fetched", "sha256", "license", "excerpts"}, f"source of {what}")
            _text(s["title"], f"source title of {what}", 300)
            _text(s["publisher"], f"publisher of {what}", 200)
            _link(s["url"], f"link of {what}")
            _link(s["fetched_from"], f"download address of {what}")
            _date(s["fetched"], f"date {what} was read")
            if not isinstance(s["sha256"], str) or not _HEX64.match(s["sha256"]):
                raise SnapshotError(f"A source of {what} has no SHA-256 of the page that was read.")
            if s["license"] is not None and (not isinstance(s["license"], str) or not s["license"].strip() or len(s["license"]) > 100):
                raise SnapshotError(f"The licence of a source of {what} is not plain text.")
            excerpts = s["excerpts"]
            if not isinstance(excerpts, list) or not 1 <= len(excerpts) <= MAX_EXCERPTS:
                raise SnapshotError(f"A source of {what} has no quoted text, or too many pieces.")
            for excerpt in excerpts:
                total += len(_text(excerpt, f"quoted text of {what}", MAX_EXCERPT_CHARS))
        if total > MAX_ADVISORY_CHARS:
            raise SnapshotError(f"The quoted text of {what} is longer than this version takes.")
    return top


def read_snapshot(path: Path) -> dict:
    """Read one snapshot file. Raises SnapshotError with a plain sentence when it can't be used."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise SnapshotError("The snapshot file can't be opened.") from None
    if len(raw) > MAX_BYTES:
        raise SnapshotError("The snapshot file is larger than this version takes.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):   # (UnicodeDecodeError is a ValueError)
        raise SnapshotError("The snapshot file is not valid JSON.") from None
    return check_snapshot(data)


def advisory_of(snapshot: dict, advisory_id: str) -> dict:
    for advisory in snapshot["advisories"]:
        if advisory["id"] == advisory_id:
            return advisory
    raise SnapshotError(f"The snapshot has no advisory {advisory_id}.")


def source_label(index: int) -> str:
    """How a prompt and an answer name a source: S1, S2, ... in the order the snapshot lists them."""
    return f"S{index + 1}"


def excerpt_holds(advisory: dict, label: object, text: object) -> bool:
    """Is this text, character for character, inside one excerpt of the source with this label?"""
    if not isinstance(label, str) or not isinstance(text, str) or not text.strip():
        return False
    for index, source in enumerate(advisory["sources"]):
        if source_label(index) == label:
            return any(text in excerpt for excerpt in source["excerpts"])
    return False
