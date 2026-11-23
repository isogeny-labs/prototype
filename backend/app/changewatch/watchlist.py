"""Change watch, the Watch list (sandbox research, a prototype; Kevin's plan of 22 November 2026, part 5).

Published weaknesses in the libraries a file names that have NO FIX YET, kept in view and looked at again until their
publisher names a fixed version. This is the world-driven half of Change watch: something changed in the world, not in
the code. The change-driven half (`state.py`, `views.py`) is not touched by it.

What is kept, and what is worked out:
  - The history is the assessment's own looks for advisories (`otto_lookups`), which were already kept add-only. A look
    made by the Watch list's clock is the same look a click makes, under the clock's name. No second copy is kept.
  - An item, its status and its history are worked out from those looks on every read, by the fixed rule below, and
    never stored. (The same way a proposal is worked out and only a person's decision on it is stored.)
  - Stored: a person's "Stop watching" and "Watch again", add-only, with who, when and the reason (`watchlist_marks`).

The rule (`derive`) is written a second time in `backend/evidence/watchlist.py`, apart from the app: the verify command
works every item out again from the looks in the file. Change one, change the other; a test compares them.

Nothing here is a result. "Fix published" is the publisher's statement, as the source gives it; it never says the fix
works. A test for it still has to be designed, registered, run and reviewed before anything is proposed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.db import OttoLookupRow, PlanRow, WatchListMarkRow
from app.errors import BadRequest, Conflict, NotFound
from app.otto import lookup
from app.present import lookup as present_lookup
from app.present import watchlist as words

# What can happen to an item from one look to the next.
SEEN, FIX, FIX_GONE, FIX_CHANGED, VERSIONS_CHANGED, WITHDRAWN, GONE, BACK = (
    "seen_no_fix",
    "fix_published",
    "fix_no_longer_named",
    "fix_changed",
    "versions_changed",
    "withdrawn",
    "gone",
    "back",
)
# Where an item stands by the source's own facts.
NO_FIX, FIX_PUBLISHED, IS_WITHDRAWN, IS_GONE = "no_fix", "fix_published", "withdrawn", "gone"
SEPARATOR = "~"  # an item's key: the advisory's id, then the library
MAX_REASON = 300
GAP_DAYS = 3  # more days than this between two looks is said in an item's history


# ---------------------------------------------------------------- the rule (pure; no database, no network)


def facts_of(ranges: list) -> list[list]:
    """The version ranges of one record as plain facts in a fixed order: [first affected, fixed, last affected]. It
    takes the ranges as a look keeps them (one dict each) and facts that were already written this way."""
    seen = set()
    for r in ranges:
        if isinstance(r, dict):
            seen.add((str(r.get("introduced") or ""), r.get("fixed") or None, r.get("last_affected") or None))
        elif isinstance(r, (list, tuple)) and len(r) == 3:
            seen.add((str(r[0] or ""), r[1] or None, r[2] or None))
    return [list(f) for f in sorted(seen, key=lambda f: (f[0], f[1] or "", f[2] or ""))]


def is_open(facts: list[list]) -> bool:
    """Does at least one range name a first affected version and no end? Then no fixed version is named for it.
    (A record that gives no ranges at all is neither: it is not put on the list for that, and an item on the list does
    not move for that. "Fix published" needs the source to NAME an end.)"""
    return any(f[1] is None and f[2] is None for f in facts)


def ends_of(facts: list[list]) -> dict:
    """The ends the ranges name: the fixed versions, and the last affected versions (a fix is every version after one)."""
    return {"fixed": sorted({f[1] for f in facts if f[1]}), "last_affected": sorted({f[2] for f in facts if f[2]})}


def derive(looks: list[dict]) -> list[dict]:
    """Every watch item of one assessment, from its looks in order. A look is plain data: {"number", "at", "cut",
    "asked": [library], "found": [{"id", "aliases", "library", "ranges"}], "withdrawn": [{"library", "ids"}]}.

    A weakness becomes an item at the first look that finds it with no fixed version named. One that names a fixed
    version from the first time it is seen is not for this list. From then on every look either changes nothing about
    it, or adds one event to its history."""
    items: dict[str, dict] = {}
    index: dict[tuple[str, str], str] = {}  # (an id in capitals, the library) -> the item's key
    for look in looks:
        number, at = look["number"], look["at"]
        here: set[str] = set()

        def happened(item: dict, kind: str, number=number, at=at, **more) -> None:
            item["events"].append({"look": number, "at": at, "kind": kind, **more})

        for found in look.get("found") or []:
            library = found["library"]
            ids = list(dict.fromkeys(str(i).upper() for i in [found["id"], *(found.get("aliases") or [])]))
            key = next((index[(i, library)] for i in ids if (i, library) in index), None)
            facts = facts_of(found.get("ranges") or [])
            now_open = is_open(facts)
            item = items.get(key) if key is not None else None
            if item is None:
                if not now_open:
                    continue
                key = f"{ids[0]}{SEPARATOR}{library}"
                item = items[key] = {
                    "key": key,
                    "id": ids[0],
                    "ids": [],
                    "library": library,
                    "first": {"look": number, "at": at},
                    "facts": facts,
                    "given": facts,
                    "open": True,
                    "there": True,
                    "withdrawn": False,
                    "quiet": 0,
                    "events": [],
                }
                happened(item, SEEN)
            else:
                changed = False
                if item["withdrawn"] or not item["there"]:
                    happened(item, BACK)
                    changed = True
                if facts != item["given"]:
                    if not facts:
                        # The record gives no version ranges any more. That names no fixed version, and takes none
                        # back: the item stands where it stood, with the ranges that were last given.
                        happened(item, VERSIONS_CHANGED)
                    else:
                        before, after = ends_of(item["facts"]), ends_of(facts)
                        if item["open"] and not now_open:
                            happened(item, FIX, ends=after)
                        elif not item["open"] and now_open:
                            happened(item, FIX_GONE, before=before)
                        elif before != after:
                            happened(item, FIX_CHANGED, before=before, ends=after)
                        else:
                            happened(item, VERSIONS_CHANGED)
                        item.update(facts=facts, open=now_open)
                    changed = True
                if not changed:
                    item["quiet"] += 1
                item.update(given=facts, there=True, withdrawn=False)
            for i in ids:
                index[(i, library)] = item["key"]
                if i not in item["ids"]:
                    item["ids"].append(i)
            item["last"] = {"look": number, "at": at}
            here.add(item["key"])
        for record in look.get("withdrawn") or []:
            library = record.get("library")
            key = next(
                (
                    index[(str(i).upper(), library)]
                    for i in record.get("ids") or []
                    if (str(i).upper(), library) in index
                ),
                None,
            )
            if key is None or key in here:
                continue
            item = items[key]
            if not item["withdrawn"]:
                happened(item, WITHDRAWN)
            item.update(withdrawn=True, there=False)
            here.add(key)
        for key, item in items.items():
            # Not in this look's answer, and not withdrawn. That says something only where the look asked about its
            # library and kept everything it read: a look that was cut short may simply not list it.
            if key in here or not item["there"] or item["library"] not in (look.get("asked") or []) or look.get("cut"):
                continue
            happened(item, GONE)
            item["there"] = False
    newest = looks[-1]["number"] if looks else None
    out = []
    for item in items.values():
        state = (
            IS_WITHDRAWN
            if item["withdrawn"]
            else IS_GONE
            if not item["there"]
            else NO_FIX
            if item["open"]
            else FIX_PUBLISHED
        )
        out.append(
            {
                "key": item["key"],
                "id": item["id"],
                "ids": list(item["ids"]),
                "library": item["library"],
                "first": item["first"],
                "last": item["last"],
                "state": state,
                "ends": ends_of(item["facts"]),
                "ranges": item["facts"],
                "events": item["events"],
                "quiet": item["quiet"],
                # (the app's New tag, as Advisories uses it: what the newest look brought, or changed)
                "new": item["events"][-1]["look"] == newest,
            }
        )
    return out


def plain_look(number: int, row: OttoLookupRow) -> dict:
    """One stored look as the rule reads it (and as the evidence file holds it)."""
    return {
        "number": number,
        "at": row.at,
        "by": row.by,
        "source": row.source,
        "cut": bool(row.cut),
        "asked": [str(a.get("library")) for a in row.asked or [] if isinstance(a, dict)],
        "found": [
            {
                "id": f["advisory"]["id"],
                "aliases": list(f["advisory"].get("aliases") or []),
                "library": f["advisory"]["package"]["name"],
                "ranges": facts_of(f.get("ranges") or []),
            }
            for f in row.found or []
        ],
        "withdrawn": [
            {"library": w.get("library"), "ids": list(w.get("ids") or [])}
            for w in row.withdrawn or []
            if isinstance(w, dict)
        ],
    }


def facts_as_ranges(facts: list[list]) -> list[dict]:
    return [{"introduced": f[0], "fixed": f[1], "last_affected": f[2]} for f in facts]


# ---------------------------------------------------------------- in the app


class WatchListMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    settings: Any
    _plan: Callable[..., PlanRow]
    _closed_at: Callable[..., Any]
    _otto_lock: Any
    _named_libraries: Callable[..., list[dict]]
    _askable: Callable[..., tuple]
    _lookup_rows: Callable[..., list[dict]]
    _research_state: Callable[..., dict]
    _research_live: dict
    _left_open: Callable[[dict], dict]
    look_for_advisories: Callable[..., dict]
    decision_name: Callable[..., str]
    sandbox_on: Callable[[], bool]
    watch_clock_next: Callable[[int], str | None]

    # ---------------------------------------------------------------- reading

    def _watch_looks(self, db, plan_id: int) -> list[OttoLookupRow]:
        return list(
            db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id)).all()
        )

    def _watch_marks(self, db, plan_id: int) -> list[WatchListMarkRow]:
        return list(
            db.scalars(
                select(WatchListMarkRow).where(WatchListMarkRow.plan_id == plan_id).order_by(WatchListMarkRow.id)
            ).all()
        )

    def _watch_items(self, db, plan: PlanRow) -> tuple[list[dict], list[OttoLookupRow]]:
        """Every watch item of this assessment as it stands now: the rule's item, with what the app knows about it
        besides (its published words, what it says about the versions the file names, where a test for it stands, and
        whether a person stopped watching it). Worked out; nothing is written."""
        rows = self._watch_looks(db, plan.id)
        items = derive([plain_look(n, row) for n, row in enumerate(rows, start=1)])
        if not items:
            return [], rows
        libraries = self._named_libraries(db, plan)
        marks: dict[str, WatchListMarkRow] = {}
        history: dict[str, list[WatchListMarkRow]] = {}
        for mark in self._watch_marks(db, plan.id):
            marks[mark.item] = mark
            history.setdefault(mark.item, []).append(mark)
        newest = rows[-1]
        standing = {r["advisory"]["id"].upper(): r for r in self._lookup_rows(db, plan, newest)}
        research = self._research_state(db, plan.id)
        running = (
            set(a.upper() for a in (research["run"].advisories or []))
            if research["run"] is not None and research["live"]
            else set()
        )
        left_open = {
            str(k).upper(): v for k, v in self._left_open(research).items()
        }  # (what the last research run left open)
        for item in items:
            advisory = None
            for row in reversed(rows):  # its published words, as the newest look that held it read them
                advisory = next(
                    (
                        f["advisory"]
                        for f in row.found or []
                        if f["advisory"]["package"]["name"] == item["library"]
                        and (
                            f["advisory"]["id"].upper() in item["ids"]
                            or any(str(a).upper() in item["ids"] for a in f["advisory"].get("aliases") or [])
                        )
                    ),
                    None,
                )
                if advisory is not None:
                    break
            item["advisory"] = advisory
            # A stretch with no look at all (the app was off, or the switch): said in the history, never papered over.
            times = [row.at for n, row in enumerate(rows, start=1) if n >= item["first"]["look"]]
            item["gaps"] = [
                {"from": a, "to": b} for a, b in zip(times, times[1:], strict=False) if _days_between(a, b) > GAP_DAYS
            ]
            found = lookup.Found(
                advisory=advisory or {}, ranges=facts_as_ranges(item["ranges"]), versions=[], record_id=item["id"]
            )
            item["fits"] = [
                {**lib, **lookup.names_version(found, lib["version"])}
                for lib in libraries
                if lib["library"] == item["library"]
            ]
            listed = next((standing[i] for i in item["ids"] if i in standing), None)
            item["test"] = _test_stands(item, listed, running, left_open)
            newest_mark = marks.get(item["key"])
            item["stopped"] = newest_mark is not None and newest_mark.kind == "stop"
            item["marks"] = [
                {"kind": m.kind, "at": m.at, "by": m.by, "reason": m.reason} for m in history.get(item["key"], [])
            ]
        return items, rows

    def watch_list_view(self, plan_id: int) -> dict:
        """The Watch list of one assessment. Reading it sends nothing, starts nothing and writes nothing."""
        on = self.sandbox_on()
        with self.db() as db:
            plan = self._plan(db, plan_id)
            closed = self._closed_at(plan_id) is not None
            if not on:
                return words.off_view()
            items, rows = self._watch_items(db, plan)
            libraries = self._named_libraries(db, plan)
            packages, skipped = self._askable(libraries)
        return words.view(
            items=items,
            look=_look_words(rows[-1]) if rows else None,
            looks=len(rows),
            closed=closed,
            packages=[p.words for p in packages],
            skipped=skipped,
            recorded=self.settings.advisory_source_dir is not None,
            next_look=self.watch_clock_next(plan_id) if not closed else None,
        )

    def watch_list_summary(self, plan_id: int) -> dict | None:
        """For the Overview: how many watched weaknesses have no fix yet, and how many have a fix published and no
        test yet. None while Sandbox research is off (the Overview then says nothing about it, as before)."""
        if not self.sandbox_on():
            return None
        with self.db() as db:
            items, _ = self._watch_items(db, self._plan(db, plan_id))
        return words.summary([i for i in items if not i["stopped"]])

    # ---------------------------------------------------------------- a person's two actions, and Look now

    def watch_list_look(self, plan_id: int) -> dict:
        """Look now: the same look "Look for new advisories" makes, on a click."""
        self._watch_must_be_on()
        self.look_for_advisories(plan_id)
        return self.watch_list_view(plan_id)

    def watch_list_mark(self, plan_id: int, item_key: str, stop: bool, reason: str | None = None) -> dict:
        """Stop watching one weakness, or watch it again. Recorded with who, when and the reason; nothing is deleted,
        and nothing about the weakness itself changes."""
        self._watch_must_be_on()
        text = " ".join(str(reason or "").split())[:MAX_REASON] or None
        with self._otto_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            if self._closed_at(plan_id) is not None:
                raise Conflict(present_lookup.CLOSED_SENTENCE)
            items, _ = self._watch_items(db, plan)
            item = next((i for i in items if i["key"] == item_key), None)
            if item is None:
                raise NotFound("That weakness is not on this assessment's Watch list.")
            if item["stopped"] == stop:
                raise Conflict(words.ALREADY_STOPPED if stop else words.ALREADY_WATCHED)
            if not stop and text is not None:
                raise BadRequest("Watch again takes no reason.")
            db.add(
                WatchListMarkRow(
                    plan_id=plan_id,
                    item=item["key"],
                    kind="stop" if stop else "watch",
                    at=_now(),
                    by=self.decision_name(),
                    reason=text,
                )
            )
            db.commit()
        return self.watch_list_view(plan_id)

    def _watch_must_be_on(self) -> None:
        if not self.sandbox_on():
            raise Conflict(words.OFF_SENTENCE)

    # ---------------------------------------------------------------- the evidence file

    def watch_list_evidence(self, plan_id: int) -> dict | None:
        """For the signed evidence: the looks as the rule reads them, every item as it stands, and every stop and watch
        again. None when the assessment has no look (the file then has no such part, as before)."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            rows = self._watch_looks(db, plan_id)
            if not rows:
                return None
            looks = [plain_look(n, row) for n, row in enumerate(rows, start=1)]
            marks = self._watch_marks(db, plan_id)
            items, _ = self._watch_items(db, plan)
        return {
            "looks": looks,
            "items": [
                {
                    "key": i["key"],
                    "id": i["id"],
                    "ids": i["ids"],
                    "library": i["library"],
                    "first": i["first"],
                    "last": i["last"],
                    "state": i["state"],
                    "word": words.STATE_WORDS[i["state"]][0],
                    "ends": i["ends"],
                    "ranges": i["ranges"],
                    "events": i["events"],
                    "quiet": i["quiet"],
                    "stopped": i["stopped"],
                    "test": {"key": i["test"]["key"], "word": i["test"]["word"]},
                }
                for i in items
            ],
            "marks": [{"item": m.item, "kind": m.kind, "at": m.at, "by": m.by, "reason": m.reason} for m in marks],
            "note": words.EVIDENCE_NOTE,
        }


def _test_stands(item: dict, row: dict | None, running: set[str], left_open: dict) -> dict:
    """Where a test for a watched weakness stands, in the words of the look that listed it. Only an item whose fix is
    published can have one; it repeats what Advisories says and decides nothing."""
    if item["state"] != FIX_PUBLISHED or row is None:
        return {"key": "none", "word": None, "line": None, "link": None}
    state, entry = row["state"], row.get("entry")
    link = {"page": "advisories", "item": entry["id"] if entry else None}
    if any(i in running for i in item["ids"]):
        return {"key": "being_tested", "word": words.BEING_TESTED, "line": words.BEING_TESTED_LINE, "link": link}
    if state == "in_pack" and entry is not None:
        test = entry.get("test") or {}
        if test.get("state") == "ready":
            return {"key": "test_proposed", "word": words.TEST_PROPOSED, "line": words.TEST_PROPOSED_LINE, "link": link}
        reason = str(test.get("reason") or entry.get("reading_refused") or "").strip()
        return {"key": "no_test", "word": words.NO_TEST, "line": reason or None, "link": link}
    if state == "in_waiting_pack":
        return {
            "key": "waiting_pack",
            "word": None,
            "line": words.waiting_pack_line(row.get("pack"), bool(row.get("pack_made_here"))),
            "link": None,
        }
    if state == "new":
        opened = next((left_open[i] for i in item["ids"] if i in left_open), None)
        if opened:
            return {"key": "left_open", "word": None, "line": words.left_open_line(opened), "link": None}
        return {"key": "ready", "word": None, "line": words.READY_LINE, "link": {"page": "advisories", "item": None}}
    if state == "no_test":
        return {"key": "no_test", "word": words.NO_TEST, "line": row.get("why"), "link": None}
    return {"key": "not_yours", "word": None, "line": None, "link": None}


def _look_words(row: OttoLookupRow) -> dict:
    return {"at": row.at, "by": row.by, "source": row.source, "sent": list(row.sent or []), "cut": bool(row.cut)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _days_between(a: str, b: str) -> float:
    try:
        return (
            datetime.fromisoformat(b.replace("Z", "+00:00")) - datetime.fromisoformat(a.replace("Z", "+00:00"))
        ).total_seconds() / 86400
    except ValueError:
        return 0.0
