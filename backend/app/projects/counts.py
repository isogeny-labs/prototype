"""The real counts of one assessment, for the Projects table and the Overview page.

Every number is read from the same views the pages draw (latest Verify run, Evidence, Fixes, Migration), so the
counts can never say more than the pages. No score, no made-up number: a part that has not happened yet is None.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db import PlanRow, VerifyRunRow

IN_PLACE = "In place (measured)"
STATUS_ORDER = ("classical", "hybrid", "pq_only", "couldnt_check", "not_measured")


def assessment_counts(lab: Any, import_id: int | None) -> dict:
    out: dict = {"claims": None, "tests": None, "fixes": None, "systems": None}
    if import_id is None:
        return out
    with lab.db() as db:
        run = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == import_id)
                         .order_by(VerifyRunRow.id.desc()).limit(1)).first()
        results = [r for r in (run.results or []) if isinstance(r, dict)] if run is not None else None
        plan = db.scalars(select(PlanRow).where(PlanRow.import_id == import_id)).first()
        plan_id = plan.id if plan is not None else None
    if results is not None:
        out["claims"] = {"checked": len(results),
                         "false": sum(1 for r in results if r.get("result") == "False"),
                         "true": sum(1 for r in results if r.get("result") == "True"),
                         "couldnt_check": sum(1 for r in results if r.get("result") == "Couldn't check")}
    if plan_id is None:
        return out
    summary = lab.plan_view(plan_id)
    if summary.get("has_results"):
        rows = lab.lab_view(plan_id)["rows"]
        newest = [row.get("after") or row.get("result") for row in rows]
        ran = [r for r in newest if r]
        out["tests"] = {"run": len(ran), "failed": sum(1 for r in ran if r.get("code") == "failed"),
                        "passed": sum(1 for r in ran if r.get("code") == "passed")}
    if summary.get("has_results") or summary.get("has_migration"):
        fixes = lab.fixes_view(plan_id)["fixes"]
        open_ = [f for f in fixes if f["status"]["key"] != "merged"
                 and not (f.get("change_box") and f["change_box"]["badge"]["label"] == IN_PLACE)]
        out["fixes"] = {"total": len(fixes), "open": len(open_)}
    if summary.get("has_migration"):
        systems = lab.migration_view(plan_id)["systems"]
        by = {code: 0 for code in STATUS_ORDER}
        for s in systems:
            code = s["status"]["code"]
            by[code] = by.get(code, 0) + 1
        out["systems"] = {"total": len(systems), **by}
    return out
