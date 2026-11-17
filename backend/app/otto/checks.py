"""Putting an advisory check into an assessment's test plan (phase 5c).

One function, used wherever a design becomes a locked test for a program: by Add new checks on the Advisories page,
and by the research side's trial script when it tries a design on a public copy before a pack is signed. The check
joins the plan like a test added with "+ Add test" (origin "added"), is locked like every test, and is stamped as
proposed by the pack, never by the rule engine or the reviewer. Nothing here runs anything.
"""
from __future__ import annotations

from app.db import PlanItemRow, PlanRow, TestSpecRow
from app.engine import research
from app.lab.testlab import read_spec
from app.otto import designs

TRIAL_PACK = {"version": "trial", "fingerprint": "0" * 64}    # a design tried on a public copy before any pack holds it


def programs_that_fit(claims: list[dict]) -> list[dict]:
    """The signing programs of a file that an advisory check can run on: the ones that check ECDSA P-256 signatures."""
    return [p for p in research.programs(claims) if designs.fits(p)]


def advisory_info(advisory: dict) -> dict:
    """What a locked advisory check keeps about where it came from: the publisher's own line and where it stands.
    `advisory` is a pack's advisory entry (it has a reading; a check is only ever made for one that does)."""
    reading = advisory["reading"]
    quote = reading["weakness_quote"]
    source = next((s for s in advisory["sources"] if s["label"] == quote["source"]), advisory["sources"][0])
    return {"plain_name": reading["plain_name"], "quote": quote["text"],
            # the link is the address the quoted text was read from (for a file in a repository: the file at its pinned commit)
            "source": {"title": source["title"], "url": source["read_from"], "published": advisory["published"], "checked": source["fetched"]}}


def existing_item(lab, db, plan_id: int, design_sha256: str, program_ref: str) -> PlanItemRow | None:
    """The plan's item for this design and this program, if it was ever added (also when it was removed since)."""
    for item in lab._items(db, plan_id, include_removed=True):
        row = db.get(TestSpecRow, item.spec_hash)
        if row is None or row.kind != research.ADVISORY_KIND:
            continue
        spec, _ = read_spec(row)
        if ((spec.get("inputs") or {}).get("advisory") or {}).get("design_sha256") == design_sha256 \
                and (spec.get("target") or {}).get("claim") == program_ref:
            return item
    return None


def add_design_item(lab, db, plan: PlanRow, design: dict, pack: dict, info: dict, program: dict) -> tuple[PlanItemRow, str, bool]:
    """Lock the check of this design for this program and put it at the end of the plan. Returns (the plan item, the
    locked test's fingerprint, was it new?). A check that was removed from the plan comes back, with its runs."""
    digest = designs.design_sha256(design)
    found = existing_item(lab, db, plan.id, digest, program["ref"])
    last = max([i.position for i in lab._items(db, plan.id, include_removed=True)], default=-1)
    if found is not None:
        if found.removed:
            found.removed, found.position = False, last + 1
        return found, found.spec_hash, False
    target = {"component": program["component"], "algorithm": program["algorithm"], "claim": program["ref"]}
    spec = designs.spec_for(design, pack, target, info)
    spec_hash = lab._lock_spec(db, spec, proposed_by=designs.PROPOSED_BY)
    item = PlanItemRow(plan_id=plan.id, spec_hash=spec_hash, position=last + 1, origin="added", removed=False)
    db.add(item)
    db.flush()
    return item, spec_hash, True
