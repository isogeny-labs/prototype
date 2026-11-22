"""Flags: old cryptography creeping back in. Phase 6d.

A flag is something to look at. It is never a result, and it rates nothing. This module finds one kind of flag: a
line that a developer's change ADDS names an algorithm or a protocol from the short list in
`app/engine/guidance.py` (`OLD_CRYPTOGRAPHY`, each name with its source). It reads text and runs nothing: the app
has not tested what such a line does, and every flag says so.

A removed line never gives a flag, and neither does a line that was already there.
"""

from __future__ import annotations

import re

from app.engine.guidance import OLD_CRYPTOGRAPHY

NOT_TESTED = "The app has not tested what this line does."
MAX_LINE = 2000  # a longer line is read up to here
MAX_FLAGS = 50  # for one change; more are counted, not listed

_BEFORE = r"(?<![A-Za-z0-9])"  # the name starts here: "RC4" is not found inside "src4"


def _compiled(words: list[dict]) -> list[tuple[dict, list[re.Pattern]]]:
    return [(w, [re.compile(_BEFORE + "(?:" + p + ")", re.IGNORECASE) for p in w["written"]]) for w in words]


_WORDS = _compiled(OLD_CRYPTOGRAPHY)


def named_in(
    file: str, added: list[tuple[int, str]], words: list[tuple[dict, list[re.Pattern]]] | None = None
) -> list[dict]:
    """The names of old cryptography in the lines a change adds to one file. `added` is (line number as people count
    it, the line's text). One flag for each name on each line, in the order of the lines."""
    out = []
    for n, text in added:
        line = text[:MAX_LINE]
        for word, patterns in _WORDS if words is None else words:
            found = next((m for p in patterns if (m := p.search(line)) is not None), None)
            if found is not None:
                out.append(
                    {
                        "kind": "old_cryptography",
                        "word": word["word"],
                        "as_written": found.group(0),
                        "file": file,
                        "line": n,
                        "text": line.strip()[:200],
                        "source": dict(word["source"]),
                    }
                )
    return out


def read_words(raw: object) -> list[tuple[dict, list[re.Pattern]]]:
    """A word list held to the form of OLD_CRYPTOGRAPHY (used for the built-in list, and by its fuzz test): a list of
    {"word", "written": [patterns], "source": {"title", "url"}}. Anything else is refused with ValueError."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("The word list is not a list of names.")
    for w in raw:
        if not isinstance(w, dict) or set(w) != {"word", "written", "source"}:
            raise ValueError("A name of the word list is not written as this app expects.")
        source = w["source"]
        if not isinstance(w["word"], str) or not w["word"].strip() or len(w["word"]) > 40:
            raise ValueError("A name of the word list is empty or too long.")
        if (
            not isinstance(w["written"], list)
            or not 1 <= len(w["written"]) <= 10
            or not all(isinstance(p, str) and 0 < len(p) <= 100 for p in w["written"])
        ):
            raise ValueError("A name of the word list does not say how it is written.")
        if (
            not isinstance(source, dict)
            or set(source) != {"title", "url"}
            or not all(isinstance(v, str) and v for v in source.values())
        ):
            raise ValueError("A name of the word list has no source.")
    try:
        return _compiled(raw)
    except (re.error, RecursionError, OverflowError) as exc:
        raise ValueError("A name of the word list is written in a way this app cannot read.") from exc


__all__ = ["MAX_FLAGS", "NOT_TESTED", "named_in", "read_words"]
