"""What-if (phase 6e, first half): what the app knows about updating one library to one version.

`whatif_view` answers "what if I update elliptic to 6.5.7?" from what the app really holds, by fixed rules and with
no Claude step. It gives four parts:

1. What the app knows: seven kinds of fact, each line with where it comes from and a link to where it is shown.
   Where the app knows nothing on a point the line says so, in the words Dependencies already uses ("Not in our
   knowledge base yet", "Couldn't tell the version", "Doesn't apply"). Nothing is guessed, and nothing is worked out
   from a neighbouring version.
2. A try on a test copy: whether Evidence's own Retest new version can be pointed at that version, and if not, why.
   This module starts nothing; the panel offers the page's own button behind Confirm.
3. One sentence in place of an explanation in free words (that is the second half of 6e).
4. Hypothesis: what the facts do not show, in the app's own sentences where they apply.

It reads: the dependency list and its ties, the knowledge base, the installed test packs, this assessment's reviewed
results. It writes nothing, starts nothing and decides nothing; a fact repeats a record, and no result is worded here.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import real_libraries
from app.db import ImportRow, PlanRow
from app.engine import research
from app.knowledge import needs as needs_lists
from app.knowledge.base import knowledge_base
from app.knowledge.versions import key as version_key, read_version
from app.present import dependencies as present_deps
from app.present import otto as present_otto
from app.present import times
from app.present.lookup import CLOSED_SENTENCE

MAX_TEXT = 80
TITLES = {
    "used": "Where the library is used",
    "needs": "Dependencies added or removed by the new version",
    "advisories": "Published advisories and the new version",
    "trial": "What the test pack's own trial showed on public copies",
    "post_quantum": "Post-quantum support of both versions",
    "blocks": "The migration track it blocks today",
    "own_results": "Your own results on this library",
}
FROM_FILE, PACKAGE_FILE, DEPENDENCIES, OWN_RESULTS = "From your file", "Package file says", "From the Dependencies page", "This assessment's reviewed runs"
_LEADING_V = re.compile(r"^[vV](?=\d)")
NEEDS_WORDS = {"not_in_knowledge_base": "Not in our knowledge base yet", "couldnt_tell_version": "Couldn't tell the version",
               "doesnt_apply": "Doesn't apply"}
EXPLANATION_OFF = "Live Otto is off. This is what the app knows."
EXPLANATION_NOT_BUILT = "This is what the app knows. An explanation in plain sentences is not part of this version yet."
TRY_TITLE = "A try on a test copy"
TRY_CHANGES = ["It reruns this assessment's locked tests for that library on the public copy of the new version, on this computer.",
               "Its results become the newest results “after” for those tests in this assessment.",
               "A finding that passes on the new version can then read as closed.",
               "“Proven on your system” then reads this run.",
               "An accepted update for this library can then no longer be undone."]
HYPOTHESIS_NOTE = ("What the facts above do not show. Turning one of these into a test, or adding it to Change watch, is not part of "
                   "this version yet.")
H_LOADS = "Whether your system really loads this library needs your environment."
H_PUBLIC_COPY = "The app has tested the library's public copy, not the programs of yours that use it."
H_NO_DATA = "The app has no dependency data for this version."
H_NOT_KNOWN = "The app holds nothing about this library, so everything about the update is open."


def _plain(value: object, limit: int = MAX_TEXT) -> str:
    """Typed text made safe to repeat in a sentence: one line of printable characters, not too long, and never the
    mark this app itself puts around a time for a browser (a person's own words are not rewritten as a time)."""
    text = " ".join("".join(ch for ch in str(value or "") if ch.isprintable()).split()).replace(times.OPEN, "")
    return text if len(text) <= limit else text[:limit] + "..."


def _line(text: str, label: str | None = None, link: dict | None = None, source: dict | None = None) -> dict:
    return {"text": text, "label": label, "link": link, "source": source}


def _link(page: str, item: object = None) -> dict:
    return {"page": page, "item": str(item) if item is not None else None, "group": None}


def _group(key: str, lines: list[dict], none: str | None = None, plain: dict | None = None) -> dict:
    """`plain`: the same facts as plain values (names, ids, the answers' own words), for a check or a file. The card
    draws the lines, never these; they say nothing the lines do not say."""
    return {"key": key, "title": TITLES[key], "lines": lines, "none": none if not lines else None, "plain": plain or {}}


def _source(source: Any) -> dict:
    return {"title": source.title, "url": source.url, "quote": source.quote, "read_on": source.checked}


def _package_names(entry: Any) -> set[str]:
    """The names of a knowledge-base entry's packages ("pkg:pypi/ecdsa" is called "ecdsa"), lower case."""
    out = set()
    for package in entry.packages:
        tail = str(package.purl).split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1].split("@", 1)[0]
        if tail:
            out.add(tail.casefold())
    return out


def _same_version(a: Any, b: Any) -> bool:
    """Two read versions are the same release (1.1.1 and 1.1.1.0 are; 6.5.7 and 6.5.70 are not)."""
    return a is not None and b is not None and version_key(a) == version_key(b)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


class WhatIfMixin:
    """Mixed into Lab (two reads over one private method; every other helper is a plain function of this module,
    because a mixin's private names are shared by the whole Lab). Needs: db and, from the other mixins: _plan, _claims, _dependency_state, _pack_advisories,
    _closed_at, lab_view, otto_live_ready."""

    # Declared for the type check only (nothing is assigned): from Lab and its other mixins.
    db: Callable[..., Any]
    mode: Any
    _plan: Callable[..., PlanRow]
    _claims: Callable[..., list]
    _dependency_state: Callable[..., dict | None]
    _pack_advisories: Callable[..., list]
    _closed_at: Callable[[int], Any]
    _real_note: Callable[[dict], str | None]
    lab_view: Callable[[int], dict]
    otto_live_ready: Callable[[], bool]

    def whatif_view(self, plan_id: int, library: object, version: object) -> dict:
        """What the app knows about updating `library` to `version` in this assessment. A read."""
        view = self._whatif_read(plan_id, library, version)
        for group in view["facts"]:
            del group["plain"]             # (the card draws the lines; the plain values are for `whatif_plain`)
        return view

    def whatif_plain(self, plan_id: int, library: object, version: object) -> dict:
        """The same read as plain values, for the accuracy check: what the card's lines say about the dependencies
        declared, the advisories and post-quantum support, as names, ids and each answer's own word, and whether the
        try is offered. Worked out in the same pass as the lines (`_whatif_read`), so the two cannot differ; a test
        holds every value to the line that says it."""
        view = self._whatif_read(plan_id, library, version)
        plain = {group["key"]: group["plain"] for group in view["facts"]}
        return {"library": view["library"]["label"], "version": view["version"], "have": view["have"], "known": view["known"],
                "needs": plain["needs"], "advisories": plain["advisories"], "post_quantum": plain["post_quantum"],
                "try_offered": view["test_copy"]["offered"]}

    def _whatif_read(self, plan_id: int, library: object, version: object) -> dict:
        asked_library, asked_version = _plain(library), _plain(version)
        kb = knowledge_base()
        asked = asked_library.casefold()
        # The library as the knowledge base knows it: by one of its names, its label, or the name of one of its packages
        # (PyPI calls python-ecdsa "ecdsa"). The review of 19 November 2026 found "ecdsa" answered as if nothing were known.
        entry = (kb.find(None, asked_library)
                 or next((f for f in kb.files.values() if asked in (f.library, f.label.casefold())), None)
                 or next((f for f in kb.files.values() if asked in _package_names(f)), None))
        read = read_version(asked_version)
        # The version as asked (only a leading "v" is dropped): "1.4.3-otto" is another program than "1.4.3", so the card
        # names and offers exactly the version asked about, never its upstream number in its place.
        new = _LEADING_V.sub("", asked_version)
        with self.db() as db:
            plan = self._plan(db, plan_id)
            state = self._dependency_state(db, plan)
            users = self._row_users(db, plan, state)   # type: ignore[attr-defined]  # phase 4e: every top entry that reaches a row
            programs = research.programs(self._claims(db.get(ImportRow, plan.import_id)))
            closed = self._closed_at(plan.id)
            pack_advisories = self._pack_advisories(db, closed)
        rows = [r for r in (state or {}).get("rows") or []
                if (entry is not None and r.get("library") == entry.library) or str(r.get("name") or "").casefold() == asked]
        if entry is None:          # an entry of the dependency list the knowledge base knows by its package address
            entry = next((kb.files[r["library"]] for r in rows if r.get("library") in kb.files), None)
            if entry is not None:
                rows = [r for r in (state or {}).get("rows") or [] if r.get("library") == entry.library or str(r.get("name") or "").casefold() == asked]
        label = entry.label if entry is not None else asked_library
        key = entry.library if entry is not None else None
        names = {asked, str(key or "").casefold(), label.casefold()} | (_package_names(entry) if entry is not None else set())
        names.discard("")
        advisories = [(pack, a) for pack, a in pack_advisories if a["package"]["name"].casefold() in names]
        named = [p for p in programs if p["component"].casefold() in names]
        # the versions this assessment has of the library, in the order they are met (the list first, then the file)
        have = list(dict.fromkeys([str(r["version"]) for r in rows if r.get("version")] + [str(p["version"]) for p in named if p.get("version")]))
        lab = self.lab_view(plan_id) if named else {}
        purl = next((r.get("purl") for r in rows if r.get("purl")), None)
        name = (rows[0]["name"] if rows else None) or (named[0]["component"] if named else None) or asked_library
        # why a real library of the file can't run here now (demo mode, or its image not prepared), in the page's words
        real_note = self._real_note({"component": named[0]["component"], "version": named[0]["version"]}) if named else None

        new_needs = kb.declared_needs(purl, name, asked_version) if (purl or entry is not None) else kb.declared_needs(None, asked_library, asked_version)
        facts = [_whatif_used(state, rows, label, users), _whatif_needs(kb, purl, name, label, have, new, new_needs),
                 _whatif_advisories(advisories, label, read, new), _whatif_trial(advisories, label, new),
                 _whatif_post_quantum(kb, purl, name, label, rows, have, asked_version, new), _whatif_blocks(kb, purl, name, state, rows, label, asked_version, new),
                 _whatif_own_results(lab, named, label)]
        known = entry is not None or bool(rows) or bool(named) or bool(advisories)
        hypotheses = [H_NOT_KNOWN] if not known else (
            [H_LOADS] + ([H_PUBLIC_COPY] if real_libraries.LIBRARIES.get(str(key)) else [])
            + ([H_NO_DATA] if new_needs.answer != "declared" else []))
        return {
            "plan_id": plan_id, "asked": {"library": asked_library, "version": asked_version}, "known": known,
            "library": {"key": key, "label": label}, "version": new, "version_read": read is not None, "have": have,
            "title": f"What if {label} is updated to {new}?",
            "facts_title": "What the app knows", "facts": facts,
            # (the try on a test copy: Evidence's own Retest new version, pointed at this version)
            "test_copy": _whatif_try(lab, named, key, label, new, read is not None, closed is not None, real_note),
            "explanation": EXPLANATION_NOT_BUILT if self.otto_live_ready() else EXPLANATION_OFF,
            "hypotheses_title": "Hypothesis", "hypotheses_note": HYPOTHESIS_NOTE, "hypotheses": [{"text": h} for h in hypotheses],
        }


# ---------------------------------------------------------------- the seven kinds of fact

def _whatif_used(state: dict | None, rows: list[dict], label: str, users: dict | None = None) -> dict:
    """One line for each top entry that reaches each row (phase 4e: the walk of "Where it is used", so the two never
    disagree); a row no top entry reaches keeps the one line under its own heading."""
    if state is None:
        return _group("used", [], "This assessment has no dependency list, so the app can't say where the library is used.")
    tops = {t["key"]: t for t in state["tops"]}
    systems = {s["key"]: s["name"] for s in state["system_choices"]}
    lines = []
    for row in rows:
        reaching = (users or {}).get(row["key"]) or [{"key": row.get("owner"), "label": None, "via": row["via"]}]
        for user in reaching:
            top = tops.get(user["key"])
            top_label = top["label"] if top is not None else user["label"]
            under = f", under {top_label}" if top_label and top_label != row["label"] else ""
            tie = ""
            if top is not None:
                system = top["tie"]["system"]
                tie = (f" {top_label} is tied to {systems.get(system, system)}." if system else
                       f" {top_label} is not tied to a system of your scanner file.")
            lines.append(_line(f"{row['label']} is in your dependency list{under} ({present_deps._via_words({'via': user['via']})}).{tie}",
                               FROM_FILE, _link("migration/dependencies", row["id"])))
    return _group("used", lines, f"Your dependency list does not hold {label}.")

def _whatif_needs(kb: Any, purl: object, name: object, label: str, have: list[str], new: str, new_needs: Any) -> dict:
    def unknown(found: Any) -> dict:
        return _line(f"{NEEDS_WORDS[found.answer]}. {found.reason}", None, None)
    if new_needs.answer != "declared":
        return _group("needs", [unknown(new_needs)], plain={"answer": NEEDS_WORDS[new_needs.answer], "declares": None, "compared": []})
    entry = new_needs.entry
    listed = [f"{n.name} {n.wants}".strip() for n in entry.needs]
    plain: dict[str, Any] = {"answer": PACKAGE_FILE, "declares": listed, "compared": []}
    lines = []
    for old in [v for v in have if v != new_needs.version]:
        old_needs = kb.declared_needs(purl, name, old)
        if old_needs.answer != "declared":
            lines.append(_line(f"Compared with {label} {old}: {NEEDS_WORDS[old_needs.answer]}. {old_needs.reason}", None, None))
            plain["compared"].append({"with": old, "answer": NEEDS_WORDS[old_needs.answer], "added": None, "removed": None, "changed": None})
            continue
        diff = needs_lists.compare([n.model_dump() for n in old_needs.entry.needs], [n.model_dump() for n in entry.needs])
        plain["compared"].append({"with": old, "answer": PACKAGE_FILE, "added": [f"{a['name']} {a['wants']}".strip() for a in diff["added"]],
                                  "removed": [r["name"] for r in diff["removed"]], "changed": [c["name"] for c in diff["changed"]]})
        parts = ([f"added: {_join([a['name'] + ' ' + a['wants'] for a in diff['added']])}"] if diff["added"] else []) + \
                ([f"removed: {_join([r['name'] for r in diff['removed']])}"] if diff["removed"] else []) + \
                ([f"changed: {_join([c['name'] + ' from ' + c['before'] + ' to ' + c['after'] for c in diff['changed']])}"] if diff["changed"] else [])
        count = len(entry.needs)
        same = (f"{label} {new_needs.version} declares the same {count} {'package' if count == 1 else 'packages'} as {old}: nothing added, "
                "nothing removed, no range changed." if count else
                f"{label} {new_needs.version} declares no package it needs, and neither does {old}.")
        lines.append(_line(same if not parts else f"From {label} {old} to {new_needs.version}, {'; '.join(parts)}.", PACKAGE_FILE,
                           None, _source(entry.source)))
        lines.append(_line(f"What {old} declares was read from its own package file too.", PACKAGE_FILE, None, _source(old_needs.entry.source)))
    if not lines:   # no other version of it is in this assessment: what the new version declares, by itself
        lines.append(_line((f"{label} {new_needs.version} declares {len(listed)} {'package' if len(listed) == 1 else 'packages'} it needs: "
                            f"{_join(listed)}." if listed else f"{label} {new_needs.version} declares no package it needs."),
                           PACKAGE_FILE, None, _source(entry.source)))
    if entry.note:
        lines.append(_line(entry.note, PACKAGE_FILE, None, None))
    return _group("needs", lines, plain=plain)

def _whatif_advisories(advisories: list, label: str, read: Any, new: str) -> dict:
    """What each advisory of the installed packs says about the version asked about. A conclusion is drawn only where
    the version asked about is exactly the version the publisher names as fixed. A pack holds the affected versions as
    words, and a range can have gaps (OpenJDK 18 is affected although its number is past the fix, and versions before a
    flaw was introduced were never affected), so for any other version the line quotes the pack's reading and works
    nothing out from it (the review of 19 November 2026)."""
    lines = []
    plain: dict[str, list[str]] = {"answered": [], "not_worked_out": [], "cant_say": []}
    for pack, advisory in advisories:
        reading = advisory.get("reading") or {}
        fixed = (reading.get("fixed") or {}).get("version")
        affected = reading.get("affected") or {}
        name = f"{advisory['id']} ({reading.get('plain_name') or 'an advisory'})"
        fixed_quote = (reading.get("fixed") or {}).get("quote") or {}
        affected_quote = affected.get("quote") or {}
        by = f"Test pack {pack.version}"

        def source(quote: dict, version: str = pack.version) -> dict | None:
            return ({"title": f"The publisher's line, as test pack {version} holds it", "url": None, "quote": quote.get("text"), "read_on": None}
                    if quote.get("text") else None)
        link = _link("advisories", advisory["id"])
        fixed_read = read_version(fixed) if fixed else None
        if fixed_read is None:
            plain["cant_say"].append(str(advisory["id"]))
            lines.append(_line(f"{name}: the test pack names no fixed version the app can read, so it can't say whether {new} answers it.",
                               by, link, source(affected_quote)))
        elif read is None:
            plain["cant_say"].append(str(advisory["id"]))
            lines.append(_line(f"{name}: its publisher names {fixed} as the fixed version. Couldn't tell the version you asked about.",
                               by, link, source(fixed_quote)))
        elif _same_version(read, fixed_read):
            plain["answered"].append(str(advisory["id"]))
            lines.append(_line(f"{name}: its publisher names {fixed} as the fixed version, so updating to {new} answers this advisory by "
                               "the publisher's own statement.", by, link, source(fixed_quote)))
        else:
            plain["not_worked_out"].append(str(advisory["id"]))
            versions = _plain(affected.get("versions"), 300)
            reading_line = (f" The test pack reads the affected versions as “{versions}”." if versions else "")
            lines.append(_line(f"{name}: its publisher names {fixed} as the fixed version.{reading_line} Whether {new} is among them is not "
                               "worked out here.", by, link, source(affected_quote) or source(fixed_quote)))
    return _group("advisories", lines, f"No advisory in the installed test packs is about {label}.", plain)

def _whatif_trial(advisories: list, label: str, new: str) -> dict:
    lines = []
    for pack, advisory in advisories:
        fix = advisory.get("fix") or {}
        if fix.get("kind") != "update":
            continue
        row = present_otto.public_copies_row(fix, advisory)
        link = _link("advisories", advisory["id"])
        if str(fix.get("version")) == new:
            lines.append(_line(f"{advisory['id']}: {row['line']}", f"Test pack {pack.version}", link))
        else:
            lines.append(_line(f"{advisory['id']}: the pack's trial was made for {label} {fix.get('version')}. It says nothing about {new}.",
                               f"Test pack {pack.version}", link))
    return _group("trial", lines, f"The installed test packs hold no trial of an update of {label}.")

def _whatif_post_quantum(kb: Any, purl: object, name: object, label: str, rows: list[dict], have: list[str], asked_version: str, new: str) -> dict:
    after = kb.look_up(purl, name, asked_version)
    # (where the dependency list already holds exactly the version asked about, its answer is the one Dependencies shows
    # for that entry, a measurement on a public copy included; only otherwise is it the knowledge base's answer)
    listed = next((r for r in rows if str(r.get("version")) == new), None)
    lines = []
    plain: dict[str, dict] = {}
    for question, words in present_deps.QUESTION_WORDS.items():
        a = after[question]
        if listed is not None:
            shown_now = listed["answers"][question]
            now_label = present_deps.LABEL_WORDS.get(shown_now.get("label") or "")
            said = f"{label} {new}: {present_deps.ANSWER_WORDS[shown_now['answer']]}" + (f" ({now_label})" if now_label else "")
            plain[question] = {"question": words, "new": present_deps.ANSWER_WORDS[shown_now["answer"]], "have": {}}
        else:
            said = f"{label} {new}: {present_deps.ANSWER_WORDS[a.answer]}"
            said += f" ({present_deps.LABEL_WORDS[a.label]})" if a.label else ""
            plain[question] = {"question": words, "new": present_deps.ANSWER_WORDS[a.answer], "have": {}}
        before = []
        for version in [v for v in have if v != new]:
            row = next((r for r in rows if str(r.get("version")) == version), None)
            if row is not None:              # as Dependencies shows it now: the lookup, or a measurement on a public copy
                answer = row["answers"][question]
                label_words = present_deps.LABEL_WORDS.get(answer.get("label") or "")
                before.append(f"{label} {version}: {present_deps.ANSWER_WORDS[answer['answer']]}" + (f" ({label_words})" if label_words else ""))
                plain[question]["have"][version] = present_deps.ANSWER_WORDS[answer["answer"]]
            else:
                b = kb.look_up(purl, name, version)[question]
                before.append(f"{label} {version}: {present_deps.ANSWER_WORDS[b.answer]}" + (f" ({present_deps.LABEL_WORDS[b.label]})" if b.label else ""))
                plain[question]["have"][version] = present_deps.ANSWER_WORDS[b.answer]
        if listed is not None:
            lines.append(_line(f"{words}. {'; '.join(before + [said])}. Each is as Dependencies shows it for that entry of your list.",
                               now_label or DEPENDENCIES, _link("migration/dependencies", listed["id"]), None))
        else:
            lines.append(_line(f"{words}. {'; '.join(before + [said])}. {a.reason}", present_deps.LABEL_WORDS.get(a.label or ""),
                               _link("migration/dependencies", rows[0]["id"]) if rows else None,
                               _source(a.source) if a.source is not None else None))
    return _group("post_quantum", lines, plain=plain)

def _whatif_blocks(kb: Any, purl: object, name: object, state: dict | None, rows: list[dict], label: str, asked_version: str, new: str) -> dict:
    if state is None or not rows:
        return _group("blocks", [], f"{label} is not in a dependency list of this assessment, so it blocks no migration track here.")
    keys = {r["key"] for r in rows}
    after = kb.look_up(purl, name, asked_version)
    lines = []
    for system in state["systems"].values():
        for track, blockers in system["blockers"].items():
            for b in blockers:
                if b["row_key"] not in keys:
                    continue
                question = present_deps.QUESTION_WORDS[b["question"]]
                a = after[b["question"]]
                then = {"yes": f"For {new} the knowledge base's answer is Yes ({present_deps.LABEL_WORDS.get(a.label or '', 'Release notes say')}), "
                               "so by that answer it would no longer block the track.",
                        "no": f"For {new} the answer is still No, so it would still block the track."}.get(
                    a.answer, f"For {new} the answer is “{present_deps.ANSWER_WORDS[a.answer]}”, so whether it would still block is not known.")
                lines.append(_line(f"{b['label']} blocks the {present_deps.TRACK_WORDS[track]} track of {system['name']}: “{question}” reads No. {then}",
                                   DEPENDENCIES, _link("migration/dependencies", b["row"])))
    tied = {t["key"] for t in state["tops"] if t["tie"]["system"]}
    loose = [r for r in rows if r.get("owner") not in tied]
    none = (f"{label} blocks no migration track today." if not loose else
            f"{label} blocks no migration track today: its entry in the dependency list is not tied to a system of your scanner file.")
    return _group("blocks", lines, none)

def _whatif_own_results(lab: dict, named: list[dict], label: str) -> dict:
    if not named:
        return _group("own_results", [], f"Your scanner file does not name {label}, so this assessment has no result of its own on it.")
    # every reviewed result on this library that Evidence shows now, on whichever version: the first results on the
    # version the file names, and a retest's results on the version it was pointed at
    wanted = tuple(f"{p['component']} ".casefold() for p in named)
    lines = []
    for row in lab.get("rows") or []:
        for side in (row.get("result"), row.get("after")):
            if side and str(side.get("component") or "").casefold().startswith(wanted):
                lines.append(_line(f"{row['title']} on {side['component']}: {side['label']}.", OWN_RESULTS, _link("evidence", f"test-{row['item_id']}")))
    return _group("own_results", lines, f"No test of the plan has a reviewed result on {label} yet.")

# ---------------------------------------------------------------- the try

def _whatif_try(lab: dict, named: list[dict], key: str | None, label: str, new: str, version_read: bool, closed: bool,
                real_note: str | None) -> dict:
    """Whether Evidence's Retest new version can be pointed at the asked version, and if not, why. Nothing is started.
    It is offered only where that button would run the retest for exactly that version (the review of 19 November 2026:
    not in a closed assessment, and not for a real library while the app can't run it, in demo mode for one)."""
    out: dict[str, Any] = {"title": TRY_TITLE, "button": "Retest new version", "offered": False, "reason": None, "component": None,
                           "version": new, "changes": TRY_CHANGES}
    if closed:
        return {**out, "reason": CLOSED_SENTENCE}
    if not named:
        return {**out, "reason": f"Your scanner file does not name {label}, so there is no locked test of this assessment to rerun on it."}
    if not version_read:
        return {**out, "reason": "Couldn't tell the version you asked about, so there is nothing to retest on."}
    if real_note:
        return {**out, "reason": real_note}
    retest = lab.get("retest") or {}
    components = {p["component"].casefold() for p in named}
    offered = [v for v in retest.get("versions") or [] if str(v.get("component") or "").casefold() in components]
    choice = next((v for v in offered if str(v.get("version")) == new), None)
    if choice is None:
        pinned = (real_libraries.LIBRARIES.get(str(key)) or {}).get("versions") or []
        if pinned and new not in pinned:
            return {**out, "reason": f"The app holds no public copy of {label} {new}. It holds {_join([f'{label} {v}' for v in pinned])}."}
        if not pinned:     # one of our own demo programs: Retest new version offers the registered versions only
            listed = _join([f"{v.get('component')} {v.get('version')}" for v in offered]) if offered else None
            return {**out, "reason": f"Retest new version does not offer {label} {new} for this assessment."
                                     + (f" It offers {listed}." if listed else "")}
        return {**out, "reason": str(retest.get("blocked_reason") or f"Retest new version does not offer {label} {new} for this assessment now.")}
    if not retest.get("can_start"):
        return {**out, "component": choice.get("component"), "reason": str(retest.get("blocked_reason") or "Retest new version can't be started now.")}
    return {**out, "offered": True, "component": choice.get("component")}


__all__ = ["EXPLANATION_OFF", "TITLES", "WhatIfMixin"]
