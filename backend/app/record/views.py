"""The five reads of Evidence as the full record (design refactor, section 6): the Timeline, one entry's story,
Approvals and decisions, Evidence files, and the history of one item.

Each only reads: it decides nothing, writes nothing and starts nothing (`tests/record/test_record_reads_only.py` reads
this package's code and compares everything the app keeps before and after). The words are in `app/present/record.py`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import EvidenceExportRow, ImportRow
from app.errors import BadRequest, NotFound
from app.evidence.export import VERIFY_COMMAND, export_view
from app.present import record as words
from app.present import source as present_source
from app.present import times
from app.present.results import DISCLAIMER
from app.record.entries import Entries, entries
from app.record.history import history_of

_ZONE = re.compile(r"\A[A-Za-z0-9_+\-/]{1,64}\Z")
_TONES = ("fail", "warn", "pass", "neutral")
MAX_SEARCH = 100


def _zone(name: str | None) -> tuple[tzinfo, str]:
    """The viewer's time zone, for sorting entries into days (the times themselves stay exact moments). UTC when the
    name is not one this computer knows."""
    if name and _ZONE.match(name) and name != "UTC":
        try:
            return ZoneInfo(name), name
        except Exception:  # an unknown zone, or no zone data on this computer: days are UTC days
            pass
    return timezone.utc, "UTC"


def _day(at: str, zone: tzinfo) -> str:
    when = times.instant(at)
    return when.astimezone(zone).date().isoformat() if when is not None else ""


def _run(run: dict) -> dict:
    return {
        "run_id": run.get("run_id"),
        "verify_run_id": run.get("verify_run_id"),
        "name": run["name"],
        "ran_on": run["ran_on"],
        "result": {"label": run["label"], "tone": run["tone"]},
        "source_tag": run.get("source_tag"),
        "link": run["link"],
    }


def _counts(runs: list[dict]) -> list[dict]:
    """How many of an entry's runs read each result word, in the words their own pages gave them."""
    found: dict[tuple[str, str], int] = {}
    for run in runs:
        key = (str(run["label"]), run["tone"])
        found[key] = found.get(key, 0) + 1
    order = sorted(found, key=lambda key: (_TONES.index(key[1]) if key[1] in _TONES else len(_TONES), key[0]))
    return [{"label": label, "tone": tone, "count": found[(label, tone)]} for label, tone in order]


def _source_tags(runs: list[dict]) -> list[dict]:
    keys = list(dict.fromkeys((run.get("source_tag") or {}).get("key") for run in runs))
    return [present_source.tag(key) for key in present_source.KEYS if key in keys]


def _entry(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "at": entry["at"],
        "area": {"key": entry["area"], "label": words.AREA_LABELS[entry["area"]]},
        "kind": {"key": entry["kind"], "label": words.KIND_LABELS[entry["kind"]]},
        "icon": entry["icon"],
        "lead": entry["lead"],
        "rest": entry["rest"],
        "who": entry["who"],
        "also": entry["also"],
        "decided_by": entry["decided_by"],
        "marks": entry["marks"],
        "source_tags": _source_tags(entry["runs"]),
        "runs": [_run(run) for run in entry["runs"]],
        "counts": _counts(entry["runs"]),
        "outcome": entry["outcome"],
        "pending": entry["pending"],
        "link": entry["link"],
        "apart": entry["apart"],
    }


def _text(entry: dict) -> str:
    """Everything an entry says, as one lower-case line: what the search reads."""
    parts = [words.plain(entry["lead"], entry["rest"]), words.AREA_LABELS[entry["area"]], entry["who"]["name"]]
    parts += [person["name"] for person in entry["also"]] + list(entry["marks"])
    parts += [(entry["outcome"] or {}).get("label") or ""]
    for run in entry["runs"]:
        parts += [run["name"], run["ran_on"], str(run["label"])]
    return " ".join(str(p) for p in parts if p).casefold()


def _matches(entry: dict, terms: list[str]) -> bool:
    text = _text(entry) if terms else ""
    return all(term in text for term in terms)


def _days(rows: list[dict], zone: tzinfo, key: str) -> list[dict]:
    """Rows (newest first) by the day each happened on, in the viewer's time zone."""
    days: list[dict] = []
    for row in rows:
        day = _day(row["at"], zone)
        if not days or days[-1]["date"] != day:
            days.append({"date": day, "count": 0, key: []})
        days[-1][key].append(row)
        days[-1]["count"] += 1
    return days


def _filter(label_all: str, labels: tuple, counts: dict, total: int) -> list[dict]:
    return [{"key": "all", "label": label_all, "count": total}] + [
        {"key": key, "label": label, "count": counts.get(key, 0)} for key, label in labels
    ]


class RecordMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    _plan: Callable[..., Any]
    lab_view: Callable[[int], dict]

    def _record_frame(self, plan_id: int) -> dict:
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            return {"plan_id": plan.id, "is_demo": bool(imp.is_demo)}

    @staticmethod
    def _record_choice(area: str | None, kind: str | None) -> tuple[str | None, str | None]:
        area, kind = (None if area in (None, "", "all") else area), (None if kind in (None, "", "all") else kind)
        if area is not None and area not in words.AREA_KEYS:
            raise BadRequest("That is not one of the places a timeline is sorted by.", field="area")
        if kind is not None and kind not in words.KIND_KEYS:
            raise BadRequest("That is not one of the kinds a timeline is sorted by.", field="kind")
        return area, kind

    # ---------------------------------------------------------------- 1. the Timeline

    def timeline_view(
        self,
        plan_id: int,
        area: str | None = None,
        kind: str | None = None,
        q: str | None = None,
        tz: str | None = None,
    ) -> dict:
        """Everything that happened in the assessment, newest first, by day. Change watch's runs and changes are listed
        only when Change watch is chosen, and are counted in no other number."""
        frame = self._record_frame(plan_id)
        area, kind = self._record_choice(area, kind)
        terms = str(q or "")[:MAX_SEARCH].casefold().split()
        found = entries(self, plan_id)
        zone, zone_name = _zone(tz)

        def listed(entry: dict, in_area: str | None) -> bool:
            """Is this entry in the list when this place is chosen? An entry kept apart shows under Change watch only."""
            if entry["apart"]:
                return in_area == "watch"
            return in_area is None or entry["area"] == in_area

        searched = [e for e in found.all if _matches(e, terms)]
        of_kind = [e for e in searched if kind is None or e["kind"] == kind]
        shown = [e for e in of_kind if listed(e, area)]
        area_counts = {key: sum(1 for e in of_kind if listed(e, key)) for key in words.AREA_KEYS}
        in_area = [e for e in searched if listed(e, area)]
        kind_counts = {key: sum(1 for e in in_area if e["kind"] == key) for key in words.KIND_KEYS}
        apart = [e for e in of_kind if e["apart"]]
        nothing = words.TIMELINE_EMPTY if not found.all else words.TIMELINE_NOTHING_FITS
        return {
            **frame,
            "title": words.TIMELINE_TITLE,
            "subline": words.TIMELINE_SUBLINE,
            "chosen": {"area": area or "all", "kind": kind or "all", "q": " ".join(terms)},
            "areas": _filter(words.ALL_AREAS, words.AREAS, area_counts, sum(1 for e in of_kind if listed(e, None))),
            "kinds": _filter(words.EVERYTHING, words.KINDS, kind_counts, len(in_area)),
            "total": len(shown),
            "days": _days([_entry(e) for e in shown], zone, "entries"),
            "zone": zone_name,
            "empty_text": None if shown else nothing,
            # what is kept apart, said wherever it is not listed
            "apart": (
                {"count": len(apart), "label": words.APART_LABEL, "text": words.APART_NOTE, "area": "watch"}
                if apart and area != "watch"
                else None
            ),
            "names_note": words.NAMES_NOTE,
            "disclaimer": DISCLAIMER,
            "busy": found.r.busy,
        }

    # ---------------------------------------------------------------- 2. one entry's story

    def timeline_entry_view(self, plan_id: int, entry_id: str) -> dict:
        """One entry for a side panel: who, what it rested on, what came after, and the facts of its record."""
        frame = self._record_frame(plan_id)
        entry = entries(self, plan_id).by_id.get(str(entry_id))
        if entry is None:
            raise NotFound("That entry is not in this assessment's timeline.")
        record = list(entry["record"])
        for run in entry["runs"]:
            if run.get("run_id") is not None and run.get("fingerprint"):
                record.append(
                    words.fact(f"Run {run['run_id']} fingerprint (SHA-256): {run['name']}", run["fingerprint"])
                )
            elif run.get("verify_run_id") is not None:
                record.append(words.fact(f"Verify run {run['verify_run_id']}: {run['name']}", run["label"], mono=False))
        return {
            **frame,
            "entry": _entry(entry),
            "title": entry["title"],
            "summary": words.plain(entry["lead"], entry["rest"]),
            "people": entry["people"],
            "names_note": words.NAMES_NOTE,
            "rested_title": words.RESTED_ON,
            "rested": entry["rested"],
            "after_title": words.CAME_AFTER,
            "after": entry["after"],
            "record_title": words.TECHNICAL_RECORD,
            "record": [words.fact("Entry", entry["id"]), *record],
            "link_label": words.open_in(entry["area"]) if entry["link"] else None,
        }

    # ---------------------------------------------------------------- 3. Approvals and decisions

    def decisions_view(self, plan_id: int, area: str | None = None, tz: str | None = None) -> dict:
        """Every decision a person made in the assessment, newest first, by day. No result is in this list: no person
        decides one."""
        frame = self._record_frame(plan_id)
        area, _ = self._record_choice(area, None)
        found = entries(self, plan_id)
        zone, zone_name = _zone(tz)
        decided = [e for e in found.all if e["decision"] is not None]
        shown = [e for e in decided if area is None or e["area"] == area]
        otto = {key: sum(1 for e in decided if e["decision"] == key) for key in words.OTTO_DECIDED}
        rows = [self._decision_row(e) for e in shown]
        return {
            **frame,
            "title": words.DECISIONS_TITLE,
            "subline": words.DECISIONS_SUBLINE,
            "cards": words.decision_cards(
                len(decided), sum(1 for e in decided if e["decision"] in words.APPROVALS), otto, found.r.signoff
            ),
            "names_note": words.NAMES_NOTE,
            "results_note": words.RESULTS_ARE_NOT_HERE,
            "chosen": {"area": area or "all"},
            "areas": _filter(
                words.ALL_AREAS,
                words.AREAS,
                {key: sum(1 for e in decided if e["area"] == key) for key in words.AREA_KEYS},
                len(decided),
            ),
            "total": len(rows),
            "days": _days(rows, zone, "rows"),
            "zone": zone_name,
            "empty_text": None if rows else (words.DECISIONS_EMPTY if not decided else words.TIMELINE_NOTHING_FITS),
            "disclaimer": DISCLAIMER,
        }

    @staticmethod
    def _decision_row(entry: dict) -> dict:
        by = entry["by"]
        pressed = (
            entry["who"]
            if by is not entry["who"]
            else (entry["also"][0] if entry["decision"] == "signed_off" and entry["also"] else None)
        )
        return {
            "id": entry["id"],
            "at": entry["at"],
            "decision": {"key": entry["decision"], "label": words.DECISIONS[entry["decision"]]},
            "on": entry["on"] or words.plain("", entry["rest"]),
            "marks": entry["marks"],
            "who": by,
            "pressed_by": pressed,
            "area": {"key": entry["area"], "label": words.AREA_LABELS[entry["area"]]},
            "link": entry["link"],
        }

    # ---------------------------------------------------------------- 4. Evidence files

    def evidence_files_view(self, plan_id: int) -> dict:
        """Every download of the signed evidence file, newest first, how to check a file and what it holds."""
        frame = self._record_frame(plan_id)
        found = entries(self, plan_id)
        with self.db() as db:
            rows = db.scalars(
                select(EvidenceExportRow)
                .where(EvidenceExportRow.plan_id == plan_id)
                .order_by(EvidenceExportRow.id.desc())
            ).all()
            files = []
            for row in rows:
                shown = export_view(row)
                entry = found.by_id.get(f"export-{row.id}")
                files.append(
                    {
                        "id": row.id,
                        "at": shown["created_at"],
                        "fingerprint": shown["fingerprint"],
                        "fingerprint_label": shown["fingerprint_label"],
                        "who": entry["who"] if entry is not None else words.nobody(),
                        "json": shown["json"],
                        "html": shown["html"],
                    }
                )
        return {
            **frame,
            "title": words.FILES_TITLE,
            "subline": words.FILES_SUBLINE,
            "files": files,
            "empty_text": None if files else words.FILES_EMPTY,
            "download": dict(self.lab_view(plan_id)["download"]),  # the Download evidence button, as Evidence gives it
            "check": {
                "title": words.HOW_TO_CHECK_TITLE,
                "text": words.HOW_TO_CHECK,
                "command": VERIFY_COMMAND,
                "report_note": words.REPORT_NOTE,
            },
            "holds": {"title": words.WHAT_IT_HOLDS_TITLE, "items": list(words.WHAT_IT_HOLDS)},
            "names_note": words.NAMES_NOTE,
        }

    # ---------------------------------------------------------------- 5. the history of one item

    def history_view(self, plan_id: int, key: str) -> dict:
        """What happened to one item, newest first, keyed as the Related block keys its panel."""
        frame = self._record_frame(plan_id)
        return {**frame, **history_of(entries(self, plan_id), str(key)[:720])}

    def record_entries(self, plan_id: int) -> Entries:
        """The timeline's entries as plain data (for the evidence file's part and the tests)."""
        return entries(self, plan_id)


__all__ = ["RecordMixin"]
