"""A time inside a sentence the server words (the 5c fixes, 19 November 2026).

There are two readers, and they need different things.

  - A file keeps UTC, byte for byte: the signed evidence file, the report, every download and both of Otto's
    ledgers. So does every script, the accuracy check and every test that asks the app without the header below.
  - A screen shows a time in the viewer's own time zone ("18 November 2026, 7:46 pm EST"). The server can't know
    that zone. So a browser asks for marked times with one request header, the server then writes a mark with the
    exact instant where the UTC words would stand, and the browser writes the time there, with the one formatter
    every time on screen goes through (`frontend/src/time.ts`).

A mark is plain text: `[[time:2026-11-18T19:46:03Z]]`. It is only ever written into an answer to a browser that
asked for it; nothing that is stored or signed may hold one (`tests/test_times.py` walks the demo with the header
on and then reads the database, the ledgers and the evidence file for one).

A date with no time of day (a pack's build date, an advisory's publication date, a review date) is not a moment:
it is written as it is, for every reader.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

HEADER = "x-evidence-lab-times"
ASKS = "mark"
OPEN, CLOSE = "[[time:", "]]"

_marked: ContextVar[bool] = ContextVar("evidence_lab_times_marked", default=False)


def marked() -> bool:
    """Is this answer for a browser that asked for marked times?"""
    return _marked.get()


def instant(value: object) -> datetime | None:
    """A recorded time as a moment in UTC, or None when it can't be read. A time with no zone is UTC, as stored."""
    if value is None:
        return None
    if isinstance(value, datetime):
        when = value
    else:
        try:
            when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def mark(value: object) -> str | None:
    """The mark for one moment, to the second, or None when the value is no time."""
    when = instant(value)
    if when is None:
        return None
    return f"{OPEN}{when.strftime('%Y-%m-%dT%H:%M:%S')}Z{CLOSE}"


def written(value: object, utc_words: str) -> str:
    """A time for a sentence: the mark where a browser asked for marked times, and the UTC words everywhere else."""
    if _marked.get():
        return mark(value) or utc_words
    return utc_words


@contextmanager
def for_screen(on: bool = True) -> Iterator[None]:
    """Within this block, sentences are worded for a browser that asked for marked times (or, with False, for a file)."""
    token = _marked.set(bool(on))
    try:
        yield
    finally:
        _marked.reset(token)


def for_files():
    """Within this block every time is written in UTC words, whoever asked: for anything that is stored, signed or
    downloaded."""
    return for_screen(False)


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
_UTC_WORDS = re.compile(r"\b(\d{1,2}) (" + "|".join(_MONTHS) + r") (\d{4}), (\d{2}):(\d{2}) UTC\b")


def remarked(text: str) -> str:
    """A sentence the app stored in UTC words ("19 November 2026, 06:46 UTC"), for a reader: where a browser asked
    for marked times, each such time becomes its mark again, so the screen writes it in the viewer's own zone; for
    every other reader the sentence is returned as it was stored. Only for the app's own stored sentences (what the
    assistant answered): a person's own typed words are never passed through this."""
    if not _marked.get() or " UTC" not in text:
        return text

    def one(m: re.Match) -> str:
        try:
            when = datetime(int(m.group(3)), _MONTHS.index(m.group(2)) + 1, int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=timezone.utc)
        except ValueError:
            return m.group(0)
        return mark(when) or m.group(0)
    return _UTC_WORDS.sub(one, text)


class MarkTimes:
    """Web middleware: an /api request that carries the header gets its sentences with marked times."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and str(scope.get("path") or "").startswith("/api/"):
            asked = next((value for name, value in scope.get("headers") or [] if name == HEADER.encode("ascii")), b"")
            if asked == ASKS.encode("ascii"):
                with for_screen():
                    await self.app(scope, receive, send)
                return
        await self.app(scope, receive, send)


__all__ = ["HEADER", "ASKS", "OPEN", "CLOSE", "MarkTimes", "for_files", "for_screen", "instant", "mark", "marked", "remarked", "written"]
