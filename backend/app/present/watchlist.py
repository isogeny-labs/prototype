"""The words of the Watch list (sandbox research, prototype). Words only: nothing here decides anything.

No sentence says how serious a weakness is, and none says what Otto did. A status is information, never a result."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.names import join_and
from app.present import source as present_source
from app.present.otto import day, stamp

TITLE = "Watch list"
INTRO = "Published weaknesses in the libraries your files name that have no fix yet."
CLOCK_NAME = "The watch clock"            # the name a look by itself is recorded under, never a person's
OFF_SENTENCE = "The Watch list belongs to Sandbox research, which is off. It is turned on in Settings."
CLOSED_LINE = "This assessment is closed. Its Watch list stands as it was when it was signed off."
ALREADY_STOPPED = "This weakness is not being watched already."
ALREADY_WATCHED = "This weakness is being watched already."
EVIDENCE_NOTE = ("The Watch list is worked out from this assessment's looks for advisories by a fixed rule; the verify command works it "
                 "out again from the looks in this file. \"Fix published\" is the publisher's statement, as the source gives it. It is "
                 "not a result, and it does not say that the fix works.")

# The source's own facts, in a word (the rule's four states), and a status's look. Never "pass" or "fail": not a result.
STATE_WORDS = {"no_fix": ("No fix yet", "warn"), "fix_published": ("Fix published", "neutral"),
               "withdrawn": ("Withdrawn by its publisher", "neutral"), "gone": ("No longer in the source's answer", "neutral")}
BEING_TESTED, TEST_PROPOSED, NO_TEST, NOT_WATCHED = "Being tested", "Test proposed", "No test possible", "Not watched"
NOT_YOURS = "No longer names your version"
BEING_TESTED_LINE = "A research run has taken it up: a test is being designed and tried on public copies."
TEST_PROPOSED_LINE = "A test was proven on public copies and is proposed. Accepting or rejecting it is yours, on Advisories."
READY_LINE = "A test can now be designed and proven (Design and prove tests, on Advisories)."
QUOTE_TAG = "quoted from the named source, not a result"
PUBLISHED_NOTE = "Said by the publisher, as the source gives it. The app has not measured it, and it does not say that the fix works."
STOP = {"label": "Stop watching", "reason_label": "Reason (optional)", "max": 300,
        "note": "It stays on the record and can be watched again. Nothing about the weakness changes."}
WATCH = {"label": "Watch again"}


CLOCK_SOON = "It is looked at by itself within the next minutes, and then about once a day."
CLOCK_NOT_RUNNING = "The clock that looks by itself is not running in this copy of the app. Look now looks on a click."


def clock_next_line(at: str) -> str:
    return f"It is looked at again by itself, about once a day: next at about {stamp(at)}."


def clock_failed_line(at: str, reason: str, until: str) -> str:
    return f"Couldn't look by itself on {stamp(at)}: {reason} It is tried again at about {stamp(until)}."


def waiting_pack_line(version: object, made_here: bool) -> str:
    return (f"Test pack {version}, made on this computer, holds it and is not installed yet. Install it in Settings, under Test packs."
            if made_here else f"Built-in test pack {version} holds it and is not installed yet.")


def left_open_line(why: str) -> str:
    return f"The last research run could not settle it: {why} A later run can take it up."


def _ends(ends: dict) -> str:
    said = [*ends.get("fixed", []), *[f"a version after {v}" for v in ends.get("last_affected", [])]]
    return join_and(said) if said else "none"


def _range_line(fact: list) -> str:
    first, fixed, last = fact
    start = "Every version" if first in ("0", "") else f"From version {first} on"
    if fixed:
        return (f"Every version before {fixed}." if first in ("0", "") else f"From version {first} up to, and not including, {fixed}.") + f" Fixed in {fixed}."
    if last:
        return ((f"Every version up to and including {last}." if first in ("0", "") else f"From version {first} up to and including {last}.")
                + " A later version is not named.")
    return f"{start}. No fixed version is named."


def _yours(item: dict) -> list[str]:
    said = []
    for f in item.get("fits") or []:
        label, where = f["label"], f["where"]
        if f["state"] == "affected":
            said.append(f"Your version is named: {label}, which {where} lists." + (f" Fixed in {f['fixed']}." if f.get("fixed") else ""))
        elif f["state"] == "not_affected":
            said.append(f"Your version is not named: {label}, which {where} lists, is not among the versions it names.")
        else:
            said.append(f"It could not be told whether it names {label}: a version could not be read. Nothing is guessed.")
    return list(dict.fromkeys(said)) or [f"About {item['library']}."]


def _status(item: dict) -> tuple[str, str, str, str | None]:
    """(key, word, tone, the line under it)."""
    state, test = item["state"], item["test"]
    word, tone = STATE_WORDS[state]
    line = None
    key = state
    advisory = item.get("advisory") or {}
    if item["stopped"]:
        return "not_watched", NOT_WATCHED, "neutral", f"{word}."
    if state == "no_fix":
        since = _days_since(advisory.get("published"))
        line = (f"No fix published for {since} {'day' if since == 1 else 'days'}." if since is not None else "No fixed version is named.")
    elif state == "fix_published":
        seen = next((e for e in reversed(item["events"]) if e["kind"] in ("fix_published", "fix_changed")), None)
        line = f"Fixed in {_ends(item['ends'])}" + (f", first seen here on {stamp(seen['at'])}." if seen else ".")
        if test["word"]:
            key, word = test["key"], test["word"]
        elif (item.get("fits") or []) and not any(f["state"] in ("affected", "cant_tell") for f in item["fits"]) and \
                any(e["kind"] in ("fix_published", "fix_changed", "versions_changed") for e in item["events"]):
            key, word = "not_yours", NOT_YOURS
    elif state == "withdrawn":
        line = "The publisher took this record back."
    else:
        line = "The source's answer about this library no longer lists it. Nothing more is known."
    return key, word, tone, line


def _days_since(published: object) -> int | None:
    try:
        then = date.fromisoformat(str(published)[:10])
    except ValueError:
        return None
    days = (datetime.now(timezone.utc).date() - then).days
    return days if days >= 0 else None


def _event_line(event: dict) -> str:
    when, kind = stamp(event["at"]), event["kind"]
    if kind == "seen_no_fix":
        return f"First seen here on {when}, with no fixed version named."
    if kind == "fix_published":
        return f"{when}: the source names a fixed version: {_ends(event.get('ends') or {})}."
    if kind == "fix_no_longer_named":
        return f"{when}: the source no longer names a fixed version (it named {_ends(event.get('before') or {})})."
    if kind == "fix_changed":
        return f"{when}: the source changed the fixed version from {_ends(event.get('before') or {})} to {_ends(event.get('ends') or {})}."
    if kind == "versions_changed":
        return f"{when}: the source changed the versions it names."
    if kind == "withdrawn":
        return f"{when}: the publisher withdrew this record."
    if kind == "gone":
        return f"{when}: the source's answer no longer lists it."
    return f"{when}: it is in the source's answer again."


def _history(item: dict) -> list[str]:
    happened = [(e["at"], 0, _event_line(e)) for e in item["events"]]
    for m in item.get("marks") or []:
        who = m["by"]
        text = (f"{stamp(m['at'])}: {who} stopped watching it" + (f" ({m['reason']})." if m.get("reason") else ".") if m["kind"] == "stop"
                else f"{stamp(m['at'])}: {who} started watching it again.")
        happened.append((m["at"], 1, text))
    for gap in item.get("gaps") or []:
        happened.append((gap["to"], -1, f"No look was made between {stamp(gap['from'])} and {stamp(gap['to'])}."))
    lines = [text for _, _, text in sorted(happened, key=lambda h: (h[0], h[1]))]
    if item["quiet"]:
        n = item["quiet"]
        lines.append(f"Looked at {n} more {'time' if n == 1 else 'times'}; nothing about it had changed.")
    return lines


def _quote(advisory: dict) -> dict | None:
    sources = advisory.get("sources") or []
    if not sources:
        return None
    source = sources[0]
    said = [e for e in source.get("excerpts") or [] if not str(e).startswith(('"introduced"', '"fixed"', '"last_affected"'))]
    kept: list[str] = []
    total = 0
    for piece in said:
        if len(kept) >= 3 or total + len(piece) > 900:
            break
        kept.append(str(piece))
        total += len(piece)
    if not kept:
        return None
    return {"title": "What the publisher says", "lines": kept, "tag": QUOTE_TAG,
            "source_line": f"{source.get('publisher')}, read on {day(source.get('fetched'))}.", "url": source.get("url"),
            "link_label": "Open the record at its source"}


def _row(item: dict, closed: bool) -> dict:
    advisory = item.get("advisory") or {}
    source = (advisory.get("sources") or [{}])[0]
    key, word, tone, line = _status(item)
    test = item["test"]
    others = [i for i in item["ids"] if i != item["id"]]
    blocked = CLOSED_LINE if closed else None
    return {
        "key": item["key"], "id": item["id"], "title": str(source.get("title") or item["id"]), "library": item["library"],
        "yours": " ".join(_yours(item)),
        "status": {"key": key, "word": word, "tone": tone}, "status_line": line,
        "since": f"First seen here on {stamp(item['first']['at'])}.",
        "new": bool(item["new"]) and not item["stopped"],
        # Where it came from (22 November 2026): what this row says is the publisher's own statement, never a measurement.
        "source": present_source.tag(present_source.PUBLISHED, PUBLISHED_NOTE),
        "panel": {
            "ids_line": (f"{item['id']}, also known as {join_and(others)}." if others else f"{item['id']}."),
            "published_line": f"Published on {day(advisory.get('published'))}." if advisory.get("published") else None,
            "quote": _quote(advisory),
            "versions": {"title": "The versions it names", "lines": [_range_line(f) for f in item["ranges"]], "yours": _yours(item)},
            "test": ({"line": test["line"], "link": test["link"], "link_label": "On Advisories" if test["link"] else None}
                     if test.get("line") or test.get("link") else None),
            "history": {"title": "History", "lines": _history(item)},
            "stop": None if item["stopped"] else {**STOP, "can": blocked is None, "blocked_reason": blocked},
            "watch": {**WATCH, "can": blocked is None, "blocked_reason": blocked} if item["stopped"] else None,
        },
    }


_ORDER = {"fix_published": 0, "being_tested": 0, "test_proposed": 1, "no_fix": 2, "no_test": 3, "not_yours": 4, "withdrawn": 5, "gone": 6,
          "not_watched": 7}


def view(*, items: list[dict], look: dict | None, looks: int, closed: bool, packages: list[str], skipped: list[str], recorded: bool,
         next_look: str | None) -> dict:
    rows = sorted((_row(i, closed) for i in items), key=lambda r: (not r["new"], _ORDER.get(r["status"]["key"], 9), r["id"], r["library"]))
    watched = [r for r in rows if r["status"]["key"] != "not_watched"]
    stopped = [r for r in rows if r["status"]["key"] == "not_watched"]
    if look is None:
        looked = "Not looked at yet."
    elif look["by"] == CLOCK_NAME:
        looked = f"Looked on {stamp(look['at'])}, by itself."
    else:
        looked = f"Looked on {stamp(look['at'])} by {look['by']}."
    names = join_and(packages)
    if recorded:
        lines = ["Reads the recorded answers in a folder on this computer about the libraries this assessment names.", "Nothing is sent anywhere."]
    else:
        lines = ["Asks OSV (osv.dev), a public database of published advisories, about the libraries this assessment names.",
                 f"What is sent: {'this package name' if len(packages) == 1 else 'these package names'}, and nothing else: {names}.",
                 "No version, no address and no file leaves this computer."]
    if skipped:
        lines.append(f"Not asked about: {join_and(skipped)}. The source keeps {'it' if len(skipped) == 1 else 'them'} nowhere by name.")
    lines.append("Looking is free: Claude is not asked, nothing runs, and nothing is proposed by looking.")
    blocked = CLOSED_LINE if closed else (None if packages else
                                          "This assessment names no library the source keeps by name, so there is nothing to look for.")
    counts = summary(items_of(items))
    return {
        "on": True, "off_line": None, "title": TITLE, "intro": INTRO,
        "looked_line": looked,
        "next_line": CLOSED_LINE if closed else next_look,
        "look": {"button": "Look now", "can": blocked is None, "blocked_reason": blocked,
                 "box": {"title": "Look now?", "lines": lines, "confirm": "Look", "cancel": "Cancel"}},
        "count_line": counts["line"],
        "items": watched, "stopped": stopped,
        "empty_line": (None if rows else
                       "Nothing is on the Watch list. No look has found a published weakness in your libraries with no fixed version named."
                       if looks else "Nothing is on the Watch list yet. Look now reads what has been published about your libraries."),
        "note": ("\"Fix published\" repeats the publisher's statement, as the source gives it. It is not a result. A test for it is "
                 "designed and proven on public copies before anything is proposed, and every proposal waits for your Accept."),
    }


def items_of(items: list[dict]) -> list[dict]:
    return [i for i in items if not i["stopped"]]


def summary(items: list[dict]) -> dict:
    """For the page's count line and the Overview: plain counts of where the watched items stand by the source's facts."""
    no_fix = sum(1 for i in items if i["state"] == "no_fix")
    fixed = sum(1 for i in items if i["state"] == "fix_published")
    said = []
    if no_fix:
        said.append(f"{no_fix} published {'weakness' if no_fix == 1 else 'weaknesses'} in your libraries {'has' if no_fix == 1 else 'have'} no fix yet")
    if fixed:
        said.append(f"{fixed} that {'was' if fixed == 1 else 'were'} watched {'has' if fixed == 1 else 'have'} a fix published since")
    line = (join_and(said)[0].upper() + join_and(said)[1:] + ".") if said else None
    return {"no_fix": no_fix, "fix_published": fixed, "line": line,
            "link": {"page": "change-watch", "item": None, "section": "watch-list"}}


def off_view() -> dict:
    return {"on": False, "off_line": OFF_SENTENCE, "title": TITLE, "intro": INTRO, "looked_line": None, "next_line": None, "look": None,
            "count_line": None, "items": [], "stopped": [], "empty_line": None, "note": None}
