"""Comparing two lists of what is needed (phase 6e): what was added, removed or changed between them.

One function for two uses. A what-if compares what two versions of one library declare they need (the knowledge
base's `declared` entries). The Watch list (not built yet) will compare two dependency lists of one assessment. A
list is pairs of (name, what is written about it): for a declared need the version range as its package file writes
it, for a dependency list the version. Nothing is worked out about ranges: "^4.11.9" and "^4.12.0" are different
texts, and that is all this says. Names are compared without regard to upper and lower case.
"""
from __future__ import annotations

MAX_ITEMS = 5000


class ListError(Exception):
    """A list that is not pairs of a name and a text. Said in plain words."""


def read_list(raw: object) -> list[tuple[str, str]]:
    """A list held to its form: [(name, text)] or [{"name": ..., "wants": ...}], each name once. Anything else is
    refused with ListError."""
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_ITEMS:
        raise ListError("The list is not a list of names.")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            name, text = item.get("name"), item.get("wants", item.get("version", ""))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            name, text = item
        else:
            raise ListError("An entry of the list is not a name with its text.")
        if not isinstance(name, str) or not name.strip() or len(name) > 300 or not isinstance(text, str) or len(text) > 300:
            raise ListError("An entry of the list is not a name with its text.")
        if name.lower() in seen:
            raise ListError("A name is in the list twice.")
        seen.add(name.lower())
        out.append((name, text))
    return out


def compare(before: object, after: object) -> dict:
    """What differs between two lists: {"added": [{name, wants}], "removed": [...], "changed": [{name, before, after}],
    "same": [names]}, each in the order of the list it comes from."""
    old, new = read_list(before), read_list(after)
    old_by, new_by = {n.lower(): (n, t) for n, t in old}, {n.lower(): (n, t) for n, t in new}
    return {"added": [{"name": n, "wants": t} for n, t in new if n.lower() not in old_by],
            "removed": [{"name": n, "wants": t} for n, t in old if n.lower() not in new_by],
            "changed": [{"name": n, "before": old_by[n.lower()][1], "after": t} for n, t in new
                        if n.lower() in old_by and old_by[n.lower()][1] != t],
            "same": [n for n, t in new if n.lower() in old_by and old_by[n.lower()][1] == t]}


__all__ = ["ListError", "MAX_ITEMS", "compare", "read_list"]
