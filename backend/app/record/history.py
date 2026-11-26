"""The history of one item, for its side panel: what happened to it, newest first, with who did it and what decided it.

The item is named by the key the Related block uses for its panel: `test:<id>` (a check of the plan), `claim:<id>`,
`fix:<id>`, `change:<key>`, `system:<key>`, `advisory:<id>`, `library:<row>`, and `check:<row id>` for any row of
Checks or Results by its own id. A row that is a claim's check, a test of the plan or a library of the dependency
list has the history of that claim, test or library; a row of one retest's, one fix proof's or one Change watch run's
block has the runs of that block. It is picked out of the timeline's own entries and runs, so a history never says
anything the timeline does not. It reads; it decides and writes nothing.
"""

from __future__ import annotations

import re

from app.errors import NotFound
from app.present import record as words
from app.present import times
from app.record.entries import Entries

_AREA = {
    "test": "checks",
    "check": "checks",
    "claim": "observe",
    "fix": "fixes",
    "change": "fixes",
    "system": "migration",
    "advisory": "advisories",
    "library": "dependencies",
}


def _line(
    line_id: str,
    at: str | None,
    icon: str,
    title: str,
    *,
    result: dict | None = None,
    results: list[dict] | None = None,
    who: dict | None = None,
    said: str | None = None,
    decided_by: str | None = None,
    note: str | None = None,
    fingerprint: str | None = None,
    source_tag: dict | None = None,
    marks: list[str] | None = None,
    link: dict | None = None,
) -> dict:
    return {
        "id": line_id,
        "at": at,
        "icon": icon,
        "title": title,
        "result": result,
        "results": list(results or []),
        "who": who,
        "said": said,
        "decided_by": decided_by,
        "note": note,
        "fingerprint": fingerprint,
        "source_tag": source_tag,
        "marks": list(marks or []),
        "link": link,
    }


# A row of Checks or Results that is the check of something with a history of its own: (its id, whose history).
_ROW_OF = (
    (re.compile(r"\Aclaim-(\d{1,12})\Z"), "claim"),
    (re.compile(r"\Atest-(\d{1,12})\Z"), "test"),
    (re.compile(r"\Alibrary-(?!item-)(.{1,200})\Z", re.S), "library"),
)


def _whose(kind: str, name: str) -> tuple[str, str]:
    """Whose history a key asks for: a check's row that is a claim's, a test's or a library's is sent to that one."""
    if kind == "check":
        for pattern, whose in _ROW_OF:
            found = pattern.match(name)
            if found is not None:
                return whose, found.group(1)
    return kind, name


class History:
    def __init__(self, found: Entries) -> None:
        self.e, self.r = found, found.r
        self.empty: str | None = None  # what to say where there is no line, when "nothing happened" would not be true

    # ---------------------------------------------------------------- lines

    def _run_line(self, run: dict, decided_by: str = words.BY_REVIEWER) -> dict:
        """One run of the item: what it ran on, the word its page gives it, who started it and with which button."""
        run_id = run.get("run_id")
        home = self.e.by_id.get(self.e.home_of_run.get(run_id, "")) if isinstance(run_id, int) else None
        if home is None and run.get("verify_run_id") is not None:
            home = self.e.by_id.get(f"verify-{run['verify_run_id']}")
        person = home["who"] if home is not None else words.nobody()
        line_id = (
            f"run-{run['run_id']}"
            if run.get("run_id") is not None
            else f"verify-{run['verify_run_id']}-{run.get('claim_id')}"
        )
        return _line(
            line_id,
            run["at"],
            "live" if (run.get("source_tag") or {}).get("key") == "live" else "flask",
            words.run_title(run["phase"], run.get("origin", ""), run["ran_on"]),
            result=words.chip(run["label"], run["tone"]),
            who=person,
            said=words.started_by(person),
            decided_by=decided_by,
            fingerprint=run.get("fingerprint"),
            source_tag=run.get("source_tag"),
            link=run["link"],
        )

    def _entry_line(self, entry: dict, only: set | None = None) -> dict:
        """One timeline entry as a line of a history. `only`: of its runs, the tests whose words are shown."""
        runs = [run for run in entry["runs"] if only is None or run.get("item_id") in only]
        person = entry["by"] if entry["decision"] else entry["who"]
        return _line(
            entry["id"],
            entry["at"],
            entry["icon"],
            entry["title"],
            result=entry["outcome"] and words.chip(entry["outcome"]["label"], entry["outcome"]["tone"]),
            results=[words.chip(run["label"], run["tone"], run["name"]) for run in runs],
            who=person,
            said=(words.started_by(entry["who"]) if entry["kind"] == "runs" else words.by(person)),
            decided_by=entry["decided_by"],
            note=words.plain("", entry["rest"]).lstrip(" :") or None,
            marks=entry["marks"],
            link=entry["link"],
        )

    def _about(self, *keys: str, only: set | None = None) -> list[dict]:
        wanted = set(keys)
        return [self._entry_line(e, only) for e in self.e.all if e["about"] & wanted and not e["apart"]]

    # ---------------------------------------------------------------- each kind of item

    def test(self, item_id: int) -> tuple[list[dict], list[str]]:
        r, item = self.r, self.r.items.get(item_id)
        if item is None or item["hidden"]:
            raise NotFound(words.UNKNOWN_ITEM)
        mine = [run for run in r.runs.values() if run["item_id"] == item_id]
        lines = [self._run_line(run) for run in mine if run["phase"] in ("first", "retest")]
        # what people did about it: Mark reviewed, Dig deeper, a change to the plan, a decision on Otto's proposed check
        key = f"test:{item_id}"
        lines += [
            self._entry_line(e)
            for e in self.e.all
            if key in e["about"] and e["id"].split("-", 1)[0] in ("mark", "dig", "action")
        ]
        check = r.otto_checks.get(item_id)
        if check is not None:
            lines += [
                self._entry_line(e)
                for e in self.e.all
                if e["id"].startswith("otto-")
                and any(
                    d["id"] == int(e["id"].split("-", 1)[1])
                    and d["kind"] == "check"
                    and d["about"].get("design") == check["design"]
                    for d in r.otto_decisions
                )
            ]
        # the fix it answers, once that was merged
        for pr in r.pull_requests.values():
            change = r.changes.get(pr["change_id"])
            if pr["merge"] is None or change is None or item_id not in {a.get("item_id") for a in change["runs"]}:
                continue
            merged = self.e.by_id.get(f"merge-{pr['merge']['id']}")
            if merged is not None:
                lines.append(
                    _line(
                        merged["id"],
                        merged["at"],
                        "merge",
                        words.FIX_MERGED,
                        who=merged["who"],
                        said=words.by(merged["who"]),
                        note=words.plain(merged["lead"], merged["rest"]),
                        link=merged["link"],
                    )
                )
        if item["locked_at"]:
            lines.append(
                _line(
                    f"locked-{item_id}",
                    item["locked_at"],
                    "clock",
                    words.LOCKED,
                    note=words.locked_line(item["spec_hash"]),
                )
            )
        notes = []
        if any(run["phase"] == "proof" for run in mine):
            notes.append(words.PROOF_IS_ITS_OWN)
        if any(run["phase"] in ("watch", "watch_base") for run in mine):
            notes.append(words.WATCH_IS_ITS_OWN)
        return lines, notes

    def claim(self, claim_id: int) -> tuple[list[dict], list[str]]:
        if not any(c["id"] == claim_id for c in self.r.imp["claims"]):
            raise NotFound(words.UNKNOWN_ITEM)
        lines = []
        for entry in self.e.all:
            if entry["id"].startswith("verify-"):
                lines += [
                    self._run_line(run, words.BY_RULES) for run in entry["runs"] if run.get("claim_id") == claim_id
                ]
        lines += [e for e in self._about(f"claim:{claim_id}") if e["id"].startswith("action-")]
        return lines, []

    def fix(self, fix_id: str) -> tuple[list[dict], list[str]]:
        r = self.r
        if fix_id not in r.fix_words and fix_id not in r.fix_states:
            raise NotFound(words.UNKNOWN_ITEM)
        shown, state = r.fix_words.get(fix_id) or {}, r.fix_states.get(fix_id) or {}
        answers = {a.get("item_id") for a in state.get("answers") or []}
        keys = [f"fix:{fix_id}"]
        if (shown.get("change_box") or {}).get("id"):
            keys.append(f"change:{shown['change_box']['id']}")  # its server change is acted on in this fix's own box
        lines = self._about(*keys, only=answers)
        have = {line["id"] for line in lines}
        # the retests after the merge, each with the words of the tests this fix answers
        merge = state.get("merge")
        then = times.instant(merge["merged_at"]) if merge else None
        for entry in self.e.all:
            when = times.instant(entry["at"])
            if (
                entry["id"].startswith("retest-")
                and entry["id"] not in have
                and then is not None
                and when is not None
                and when >= then
            ):
                lines.append(self._entry_line(entry, answers))
        if state.get("proposal") or shown.get("proposal"):
            lines.append(
                _line(
                    f"proposed-{fix_id}",
                    None,
                    "clock",
                    words.PROPOSED_BY_OTTO,
                    note=words.PROPOSAL_NO_TIME,
                    marks=[words.FROM_OTTO],
                )
            )
        return lines, []

    def change(self, key: str) -> tuple[list[dict], list[str]]:
        lines = self._about(f"change:{key}")
        if not lines and key not in self.r.change_history:
            raise NotFound(words.UNKNOWN_ITEM)
        return lines, []

    def system(self, key: str) -> tuple[list[dict], list[str]]:
        r = self.r
        if key not in r.system_names and key not in r.systems:
            raise NotFound(words.UNKNOWN_ITEM)
        lines = [
            self._run_line(run)
            for run in r.runs.values()
            if run.get("system_key") == key and run["phase"] == "migration"
        ]
        kind, _, name = key.partition(":")
        claims = {
            c["id"]
            for c in r.imp["claims"]
            if (c["location"] == name if kind == "server" else c["location_kind"] == "software" and c["ref"] == name)
        }
        for entry in self.e.all:
            if entry["id"].startswith("verify-"):
                lines += [
                    {**self._run_line(run, words.BY_RULES), "note": run["name"]}
                    for run in entry["runs"]
                    if run.get("claim_id") in claims
                ]
        have = {line["id"] for line in lines}
        lines += [
            line
            for line in self._about(f"system:{key}")
            if line["id"] not in have and not line["id"].startswith(("press-", "run-", "verify-"))
        ]
        return lines, []

    def advisory(self, advisory_id: str) -> tuple[list[dict], list[str]]:
        r = self.r
        lines = self._about(f"advisory:{advisory_id}")
        tests = {i["id"] for i in r.items.values() if i["advisory"] == advisory_id}
        lines += [
            self._run_line(run)
            for run in r.runs.values()
            if run["item_id"] in tests and run["phase"] in ("first", "retest")
        ]
        if tests or any(d["about"].get("advisory") == advisory_id for d in r.otto_decisions):
            # a proposal is worked out on every read and is not stored: it has no time of its own
            lines.append(
                _line(
                    f"proposed-{advisory_id}",
                    None,
                    "clock",
                    words.PROPOSED_BY_OTTO,
                    note=words.PROPOSAL_NO_TIME,
                    marks=[words.FROM_OTTO],
                )
            )
        return lines, []

    def library(self, row_id: str) -> tuple[list[dict], list[str]]:
        """A library of the dependency list: each measurement on a public copy, and each decision on a proposal for
        it. Where there is neither, the history says what is true of it instead of "nothing happened"."""
        r, row = self.r, self.r.libraries.get(row_id)
        lines = [self._run_line(run) for run in r.runs.values() if run.get("library_row") == row_id]
        if row is None and not lines:
            raise NotFound(words.UNKNOWN_ITEM)
        proposals = {p.get("id") for p in (row or {}).get("otto_proposals") or []}
        decided = {d["id"] for d in r.otto_decisions if d["kind"] == "dependency" and d["proposal"] in proposals}
        lines += [
            self._entry_line(e)
            for e in self.e.all
            if e["id"].startswith("otto-") and e["id"][5:].isdigit() and int(e["id"][5:]) in decided
        ]
        if proposals:
            # a proposal is worked out on every read and is not stored: it has no time of its own
            lines.append(
                _line(
                    f"proposed-{row_id}",
                    None,
                    "clock",
                    words.PROPOSED_BY_OTTO,
                    note=words.PROPOSAL_NO_TIME,
                    marks=[words.FROM_OTTO],
                )
            )
        if not lines:
            from_notes = bool((row or {}).get("lookups"))
            self.empty = words.LIBRARY_FROM_NOTES if from_notes else words.LIBRARY_NOTHING_RUN
        return lines, []

    def check(self, check_id: str) -> tuple[list[dict], list[str]]:
        """A row of Checks that is no claim, no test of the plan and no library of the list: its own runs. A row the
        ledger lists by itself (a try's row, a system's measurement, an earlier measurement of a library, the newest
        retest, proof or watch run of a test) has that row's runs; a row of one retest's, one fix proof's or one Change
        watch run's block ("retest-12-on-3", "proof-12-in-4", "watch-12-in-4") has the runs of that block."""
        row = next((row for row in self.r.rows if row["id"] == check_id), None)
        if row is not None:
            runs = [self.r.runs[i] for i in row.get("run_ids") or [] if i in self.r.runs]
        else:
            runs = [run for run in self.r.runs.values() if run["check_id"] == check_id]
            if not runs:
                raise NotFound(words.UNKNOWN_ITEM)
        return [self._run_line(run) for run in runs], []


def history_of(found: Entries, key: str) -> dict:
    """The history of the item with this key, newest first. NotFound for an item that is not in the assessment."""
    kind, _, name = str(key).partition(":")
    reader = History(found)
    if kind not in words.HISTORY_TITLES or not name:
        raise NotFound(words.UNKNOWN_ITEM)
    kind, name = _whose(kind, name)
    if kind in ("test", "claim"):
        if not name.isdigit() or len(name) > 12:
            raise NotFound(words.UNKNOWN_ITEM)
        lines, notes = (reader.test if kind == "test" else reader.claim)(int(name))
    else:
        lines, notes = getattr(reader, kind)(name)
    seen, unique = set(), []
    for line in lines:
        if line["id"] not in seen:
            seen.add(line["id"])
            unique.append(line)

    def order(line: dict) -> float:
        when = times.instant(line["at"]) if line["at"] else None
        return when.timestamp() if when is not None else float("-inf")

    unique.sort(key=order, reverse=True)
    return {
        "key": key,
        "title": words.HISTORY_TITLES[kind],
        # what decides a result is said on top of an item that has results of its own
        "decides": words.WHO_DECIDES_CLAIM
        if kind == "claim"
        else words.WHO_DECIDES
        if kind in ("test", "check", "system", "advisory", "library")
        else None,
        "lines": unique,
        "notes": notes,
        "empty_text": None if unique else (reader.empty or words.NO_HISTORY),
        "names_note": words.NAMES_NOTE,
        "timeline": {"area": _AREA[kind]},
    }


__all__ = ["history_of"]
