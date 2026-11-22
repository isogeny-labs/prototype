"""The Watch list part of an evidence file (sandbox research, a prototype), checked after the file's own signature held.

The Watch list is worked out from an assessment's looks for advisories by a fixed rule (`backend/app/changewatch/
watchlist.py`, `derive`). The rule is written out again here, apart from the app, so the file is not checked with the
code that made it. For the part in the file:
  1. it is written as this app writes it: looks, items, marks;
  2. where the file also has the record of the looks (the Otto part), the two agree: the same number of looks, each at
     the same time, and every advisory a look of this part names is one that look found;
  3. every item is worked out again from the looks in the part, and is exactly what the file says: its key, its ids,
     its library, when it was first and last seen, its state, the ends its ranges name, its whole history, and how
     many looks changed nothing about it. No item is missing and none is extra;
  4. each item's word is the word of its state;
  5. every "Stop watching" and "Watch again" is about an item of the list, they follow one another in an order the
     app allows (never two stops in a row), and each item says "stopped" exactly when its newest mark is a stop;
  6. an item that says a test is proposed for it names an advisory that a test pack in the file holds a ready test for.

"Fix published" is the publisher's statement as the source gave it. Nothing here is a result, and this check says
nothing about whether a fix works. The file is read as data only: nothing it names is run or fetched.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.canonical import canonical_bytes

MAX_LOOKS, MAX_ITEMS, MAX_MARKS = 5000, 5000, 5000
STATE_WORDS = {"no_fix": "No fix yet", "fix_published": "Fix published", "withdrawn": "Withdrawn by its publisher",
               "gone": "No longer in the source's answer"}
TEST_KEYS = ("none", "being_tested", "test_proposed", "no_test", "waiting_pack", "left_open", "ready", "not_yours")


@dataclass
class WatchListOutcome:
    ok: bool
    problem: str | None = None
    lines: list[str] = field(default_factory=list)


class _Failed(Exception):
    """The part does not hold; the message says what, in one plain sentence."""


def _plain(value: object, limit: int = 80) -> str:
    text = "".join(ch if ch.isprintable() and ch not in "\x1b‮‭⁦⁧⁨⁩" else "?" for ch in str(value))
    return text if len(text) <= limit else text[:limit] + "..."


def _same(a: object, b: object) -> bool:
    try:
        return canonical_bytes(a) == canonical_bytes(b)
    except (ValueError, TypeError, RecursionError):
        return False


def _need(condition: bool, problem: str) -> None:
    if not condition:
        raise _Failed(problem)


# ---------------------------------------------------------------- the rule, written a second time

def _facts(ranges: object) -> list[list]:
    seen = set()
    for r in ranges if isinstance(ranges, list) else []:
        if isinstance(r, (list, tuple)) and len(r) == 3:
            seen.add((str(r[0] or ""), r[1] or None, r[2] or None))
    return [list(f) for f in sorted(seen, key=lambda f: (f[0], f[1] or "", f[2] or ""))]


def _open(facts: list[list]) -> bool:
    return any(f[1] is None and f[2] is None for f in facts)


def _ends(facts: list[list]) -> dict:
    return {"fixed": sorted({f[1] for f in facts if f[1]}), "last_affected": sorted({f[2] for f in facts if f[2]})}


def work_out(looks: list[dict]) -> list[dict]:
    """Every item, from the looks in order. (The app's `derive`, written again.)"""
    items: dict[str, dict] = {}
    names: dict[tuple[str, str], str] = {}
    for look in looks:
        number, at = look["number"], look["at"]
        seen_here: set[str] = set()
        for found in look.get("found") or []:
            library = found["library"]
            ids = list(dict.fromkeys(str(i).upper() for i in [found["id"], *(found.get("aliases") or [])]))
            key = next((names[(i, library)] for i in ids if (i, library) in names), None)
            facts = _facts(found.get("ranges"))
            open_now = _open(facts)
            item = items.get(key) if key is not None else None
            if item is None:
                if not open_now:
                    continue
                key = f"{ids[0]}~{library}"
                item = items[key] = {"key": key, "id": ids[0], "ids": [], "library": library, "first": {"look": number, "at": at},
                                     "facts": facts, "open": True, "there": True, "withdrawn": False, "quiet": 0,
                                     "events": [{"look": number, "at": at, "kind": "seen_no_fix"}]}
            else:
                events = []
                if item["withdrawn"] or not item["there"]:
                    events.append({"look": number, "at": at, "kind": "back"})
                if facts != item["facts"]:
                    before, after = _ends(item["facts"]), _ends(facts)
                    if item["open"] and not open_now:
                        events.append({"look": number, "at": at, "kind": "fix_published", "ends": after})
                    elif not item["open"] and open_now:
                        events.append({"look": number, "at": at, "kind": "fix_no_longer_named", "before": before})
                    elif before != after:
                        events.append({"look": number, "at": at, "kind": "fix_changed", "before": before, "ends": after})
                    else:
                        events.append({"look": number, "at": at, "kind": "versions_changed"})
                if events:
                    item["events"] += events
                else:
                    item["quiet"] += 1
                item.update(facts=facts, open=open_now, there=True, withdrawn=False)
            for i in ids:
                names[(i, library)] = item["key"]
                if i not in item["ids"]:
                    item["ids"].append(i)
            item["last"] = {"look": number, "at": at}
            seen_here.add(item["key"])
        for record in look.get("withdrawn") or []:
            library = record.get("library")
            key = next((names[(str(i).upper(), library)] for i in record.get("ids") or [] if (str(i).upper(), library) in names), None)
            if key is None or key in seen_here:
                continue
            item = items[key]
            if not item["withdrawn"]:
                item["events"].append({"look": number, "at": at, "kind": "withdrawn"})
            item.update(withdrawn=True, there=False)
            seen_here.add(key)
        for key, item in items.items():
            if key in seen_here or not item["there"] or item["library"] not in (look.get("asked") or []) or look.get("cut"):
                continue
            item["events"].append({"look": number, "at": at, "kind": "gone"})
            item["there"] = False
    out = []
    for item in items.values():
        state = "withdrawn" if item["withdrawn"] else "gone" if not item["there"] else "no_fix" if item["open"] else "fix_published"
        out.append({"key": item["key"], "id": item["id"], "ids": item["ids"], "library": item["library"], "first": item["first"],
                    "last": item["last"], "state": state, "ends": _ends(item["facts"]), "ranges": item["facts"], "events": item["events"],
                    "quiet": item["quiet"]})
    return out


# ---------------------------------------------------------------- the check

def _check_shape(part: object) -> tuple[list[dict], list[dict], list[dict]]:
    _need(isinstance(part, dict), "it is not written as this app writes it.")
    assert isinstance(part, dict)
    looks, items, marks = part.get("looks"), part.get("items"), part.get("marks")
    for value, most, what in ((looks, MAX_LOOKS, "looks"), (items, MAX_ITEMS, "items"), (marks, MAX_MARKS, "marks")):
        _need(isinstance(value, list) and len(value) <= most and all(isinstance(v, dict) for v in value),
              f"its {what} are not written as this app writes them.")
    assert isinstance(looks, list) and isinstance(items, list) and isinstance(marks, list)
    for n, look in enumerate(looks, start=1):
        _need(look.get("number") == n and isinstance(look.get("at"), str) and isinstance(look.get("asked"), list)
              and isinstance(look.get("found"), list) and isinstance(look.get("withdrawn"), list) and isinstance(look.get("cut"), bool),
              f"look {n} is not written as this app writes it.")
        for found in look["found"]:
            _need(isinstance(found, dict) and isinstance(found.get("id"), str) and isinstance(found.get("library"), str)
                  and isinstance(found.get("aliases"), list) and isinstance(found.get("ranges"), list)
                  and all(isinstance(r, list) and len(r) == 3 for r in found["ranges"]),
                  f"an advisory of look {n} is not written as this app writes it.")
        for record in look["withdrawn"]:
            _need(isinstance(record, dict) and isinstance(record.get("ids"), list), f"a withdrawn record of look {n} is not written as this app writes it.")
    return looks, items, marks


def _check(evidence: dict) -> list[str]:
    looks, items, marks = _check_shape(evidence.get("watch_list"))
    # 2. the looks are the looks the file records elsewhere
    recorded = ((evidence.get("otto") or {}).get("lookups") or {}).get("looks") if isinstance(evidence.get("otto"), dict) else None
    if recorded is not None:
        _need(isinstance(recorded, list) and len(recorded) == len(looks),
              "it does not hold the same number of looks as the file's own record of the looks.")
        for look, other in zip(looks, recorded, strict=True):
            _need(isinstance(other, dict) and other.get("at") == look["at"],
                  f"look {look['number']} is not at the time the file's own record of the looks gives.")
            there = {str(f.get("id")) for f in other.get("found") or [] if isinstance(f, dict)}
            missing = next((f["id"] for f in look["found"] if f["id"] not in there), None)
            _need(missing is None, f"look {look['number']} names {_plain(missing)}, which the file's own record of that look does not hold.")
    else:
        _need(not looks, "it holds looks, and the file has no record of any look.")
    # 3. every item, worked out again
    ours = {item["key"]: item for item in work_out(looks)}
    theirs: dict[str, dict] = {}
    for item in items:
        key = item.get("key")
        _need(isinstance(key, str) and key not in theirs, "an item is listed twice, or has no key.")
        theirs[str(key)] = item
    extra = next((k for k in theirs if k not in ours), None)
    _need(extra is None, f"it lists {_plain(extra)}, which the looks in the file do not give.")
    missing = next((k for k in ours if k not in theirs), None)
    _need(missing is None, f"the looks in the file give {_plain(missing)}, and the list leaves it out.")
    for key, mine in ours.items():
        item = theirs[key]
        for name in ("id", "ids", "library", "first", "last", "state", "ends", "ranges", "events", "quiet"):
            _need(_same(item.get(name), mine[name]),
                  f"{_plain(key)}: its {name.replace('_', ' ')} is not what the looks in the file give.")
        # 4. the word of its state
        _need(item.get("word") == STATE_WORDS[mine["state"]], f"{_plain(key)}: its word is not the word of where it stands.")
        test = item.get("test")
        _need(isinstance(test, dict) and test.get("key") in TEST_KEYS, f"{_plain(key)}: where a test for it stands is not written as this app writes it.")
        assert isinstance(test, dict)
        _need(test["key"] == "none" or mine["state"] == "fix_published", f"{_plain(key)}: it names a test, and no fixed version is published for it.")
    # 5. a person's stops and watch-agains
    standing: dict[str, str] = {}
    for mark in marks:
        key, kind = mark.get("item"), mark.get("kind")
        _need(key in ours, f"a stop or watch-again is about {_plain(key)}, which is not on the list.")
        _need(kind in ("stop", "watch") and isinstance(mark.get("at"), str) and isinstance(mark.get("by"), str) and bool(mark.get("by")),
              "a stop or watch-again does not say who and when.")
        _need(kind != standing.get(str(key), "watch"), f"{_plain(key)}: two stops, or two watch-agains, follow one another.")
        _need(kind == "stop" or mark.get("reason") is None, f"{_plain(key)}: a watch-again carries a reason.")
        standing[str(key)] = str(kind)
    for key, item in theirs.items():
        _need(item.get("stopped") is (standing.get(key) == "stop"), f"{_plain(key)}: it does not say stopped exactly when its newest mark is a stop.")
    # 6. a proposed test is in a pack of the file
    proposed = [item for item in items if (item.get("test") or {}).get("key") == "test_proposed"]
    if proposed:
        ready: set[str] = set()
        otto = evidence.get("otto") if isinstance(evidence.get("otto"), dict) else {}
        for envelope in (otto or {}).get("packs") or []:
            pack = envelope.get("pack") if isinstance(envelope, dict) else None
            for advisory in (pack or {}).get("advisories") or [] if isinstance(pack, dict) else []:
                if isinstance(advisory, dict) and isinstance(advisory.get("test"), dict) and advisory["test"].get("state") == "ready":
                    ready.update(str(i).upper() for i in [advisory.get("id"), *(advisory.get("aliases") or [])])
        for item in proposed:
            _need(any(str(i).upper() in ready for i in item.get("ids") or []),
                  f"{_plain(item.get('key'))}: it says a test is proposed, and no test pack in the file holds a ready test for it.")

    def count(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"

    by_state = {state: sum(1 for i in ours.values() if i["state"] == state) for state in STATE_WORDS}
    said = ", ".join(f"{n} {STATE_WORDS[s].lower()}" for s, n in by_state.items() if n) or "none"
    return [f"{count(len(ours), 'item', 'items')} worked out again from the {count(len(looks), 'look', 'looks')} in the file, each exactly as "
            f"the file says ({said}); {count(len(marks), 'stop or watch-again', 'stops and watch-agains')}, each about an item of the list. "
            "\"Fix published\" is the publisher's statement, not a result."]


def check_watch_list(evidence: dict) -> WatchListOutcome:
    """Check the Watch list part of a file whose own signature was already checked."""
    try:
        return WatchListOutcome(True, None, _check(evidence))
    except _Failed as failed:
        return WatchListOutcome(False, str(failed))
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, AssertionError):
        return WatchListOutcome(False, "it is not written as this app writes it.")
