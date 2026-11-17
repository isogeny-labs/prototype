"""Shared by the Otto tests: a design made the way a pack makes one, and its check put into a plan."""
from __future__ import annotations

from app.db import PlanItemRow
from app.engine import research
from app.otto import designs

STEP = {"prompt_sha256": "a" * 64, "answer_sha256": "b" * 64}
PACK = {"version": "2026.11.1", "fingerprint": "c" * 64}
ADVISORY = {"plain_name": "Blank signature accepted",
            "quote": "ECDSA signatures with r = 0 and s = 0 are accepted.",
            "source": {"title": "OpenJDK advisory, 19 April 2022", "url": "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
                       "published": "2022-04-19", "checked": "2026-11-17"}}


def note(flags=("InvalidSignature",), ids=(), **more) -> dict:
    """A design note as a model writes one."""
    select = {k: list(v) for k, v in (("flags", flags), ("ids", ids)) if v}
    return {"decision": "test", "block": "signature_cases", "control": "accept_all_verifier",
            "question": "Does {program} reject the signatures that advisory CVE-2022-21449 describes?",
            "why": "Why it matters: a program that accepts these signatures takes a forged one for genuine.",
            "select": select, **more}


def design(flags=("InvalidSignature",), ids=(), advisory_id="CVE-2022-21449", plain_name="Blank signature accepted") -> dict:
    return designs.compile_note(note(flags, ids), advisory_id, plain_name, STEP)


def spec_for(lab, plan_id: int, made: dict, program_ref: str | None = None) -> dict:
    """The locked test of this design for one signing program of the plan's file (the first one by default)."""
    with lab.db() as db:
        from app.db import ImportRow, PlanRow
        claims = lab._claims(db.get(ImportRow, db.get(PlanRow, plan_id).import_id))
    program = next(p for p in research.programs(claims) if program_ref is None or p["ref"] == program_ref)
    target = {"component": program["component"], "algorithm": program["algorithm"], "claim": program["ref"]}
    return designs.spec_for(made, PACK, target, ADVISORY)


def add_check(lab, plan_id: int, made: dict, program_ref: str | None = None) -> int:
    """Lock the check and put it in the plan, the way Add new checks does (without Otto's ledger): returns the plan item id."""
    spec = spec_for(lab, plan_id, made, program_ref)
    with lab._plan_lock, lab.db() as db:
        last = max([i.position for i in lab._items(db, plan_id, include_removed=True)], default=-1)
        item = PlanItemRow(plan_id=plan_id, spec_hash=lab._lock_spec(db, spec, proposed_by=designs.PROPOSED_BY), position=last + 1,
                           origin="added", removed=False)
        db.add(item)
        db.commit()
        return item.id


def result_for(lab, plan_id: int, item_id: int, which: str = "result") -> dict:
    return next(r for r in lab.lab_view(plan_id)["rows"] if r["item_id"] == item_id)[which]
