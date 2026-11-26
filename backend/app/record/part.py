"""Who did what, as the signed evidence file holds it (design refactor, decision I).

One entry for each press kept for the assessment: who, when, which button, what it was on, and references to the runs
and records it started. A reference is written only where the file itself holds what it points at (a run in the file's
list of checks, a fix, a proof, a change, a watch run), so the verify command can follow every one of them
(backend/evidence/actions.py); a run a press started that the file does not list (its test was taken out of the plan
since, or it has no review yet) is counted, and said as that.

It reads the records and the evidence that is being put together. It decides nothing and words no result.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from app.db import ActionRow, ActionRunRow, AssessmentRow
from app.present import record as words

SCHEMA = "isogeny.actions/1"
REF_KINDS = ("run", "verify_run", "test", "fix", "proof", "change", "watch_run", "developer_change")


def _held(evidence: dict) -> dict[str, set]:
    """What the file holds that a press can point at, by kind of reference."""
    checks = evidence.get("checks") or []
    fixes = evidence.get("fixes") or []
    watch = evidence.get("change_watch") or {}
    tests = {t.get("item_id") for t in evidence.get("tests") or []}
    for part in ("migration", "dependencies"):
        tests |= {m.get("item_id") for m in (evidence.get(part) or {}).get("measurements") or []}
    return {
        "run": {r.get("run_id") for c in checks for r in c.get("runs") or [] if r.get("run_id") is not None},
        "verify_run": {
            r.get("verify_run_id") for c in checks for r in c.get("runs") or [] if r.get("verify_run_id") is not None
        },
        "test": {t for t in tests if t is not None},
        "fix": {f.get("id") for f in fixes},
        "proof": {p.get("id") for f in fixes for p in f.get("proofs") or []},
        "change": {(c.get("change") or {}).get("key") for c in evidence.get("changes") or []},
        "watch_run": {r.get("watch_run_id") for r in watch.get("runs") or []},
        "developer_change": {c.get("id") for c in watch.get("changes") or []},
    }


def _facts(detail: dict) -> dict:
    """The few facts of a press, flat: words, numbers, yes or no, and plain lists of them."""
    out: dict[str, Any] = {}
    for key, value in sorted((detail or {}).items()):
        if key == "moved":
            value = [m.get("item") for m in value or [] if isinstance(m, dict)]
        elif key == "changed" and isinstance(value, dict):
            value = sorted(str(k) for k in value)
        if isinstance(value, (str, int, bool)) or value is None:
            out[str(key)] = value
        elif isinstance(value, list) and all(isinstance(v, (str, int, bool)) or v is None for v in value):
            out[str(key)] = list(value)
    return out


def _refs(action: ActionRow, runs: list[int], held: dict[str, set]) -> tuple[list[dict], int]:
    """(the references of one press that the file can resolve, how many of its runs the file does not list)."""
    refs: list[dict] = []

    def add(kind: str, value: Any) -> bool:
        if value is None or value not in held[kind]:
            return False
        if {"kind": kind, "id": value} not in refs:
            refs.append({"kind": kind, "id": value})
        return True

    missing = sum(0 if add("run", run_id) else 1 for run_id in runs)
    detail = action.detail or {}
    add("verify_run", detail.get("verify_run_id"))
    add("proof", detail.get("proof_id"))
    add("watch_run", detail.get("watch_run_id"))
    kind, _, name = str(action.item or "").partition(":")
    if kind in ("test", "run") and name.isdigit():
        add(kind, int(name))
    elif kind in ("fix", "change"):
        add(kind, name)
    elif kind == "developer-change":
        add("developer_change", name)
    return refs, missing


def actions_part(db, plan, evidence: dict) -> dict | None:
    """The part, or None when no press is on record for this assessment (it was all done before names were kept, and
    the file then reads as it did before this part existed)."""
    assessment = db.scalars(select(AssessmentRow.id).where(AssessmentRow.import_id == plan.import_id)).first()
    mine = [ActionRow.plan_id == plan.id, ActionRow.import_id == plan.import_id]
    if assessment is not None:
        mine.append(ActionRow.assessment_id == assessment)
    rows = db.scalars(select(ActionRow).where(or_(*mine)).order_by(ActionRow.at, ActionRow.id)).all()
    if not rows:
        return None
    started: dict[int, list[int]] = {}
    for tie in db.scalars(
        select(ActionRunRow).where(ActionRunRow.action_id.in_([a.id for a in rows])).order_by(ActionRunRow.id)
    ):
        started.setdefault(tie.action_id, []).append(tie.run_id)
    held = _held(evidence)
    actions = []
    for action in rows:
        refs, missing = _refs(action, started.get(action.id, []), held)
        actions.append(
            {
                "n": action.id,
                "at": action.at,
                "by": action.by,
                "by_source": action.by_source,
                "kind": action.kind,
                "what": words.action_words(action.kind),
                "button": words.button(action.kind, action.detail),
                "item": action.item,
                "refs": refs,
                "runs_not_in_file": missing,
                "facts": _facts(action.detail),
            }
        )
    return {
        "schema": SCHEMA,
        "note": words.EVIDENCE_NOTE,
        "sources": {key: words.SOURCE_LABELS[key] for key in ("account", "typed", "default")},
        "actions": actions,
    }


__all__ = ["REF_KINDS", "SCHEMA", "actions_part"]
