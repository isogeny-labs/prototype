from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import Finding, Recommendation, Approval, Run, Implementation, ResearchSource, ExperimentProposal, FINDING_STATUSES
from .. import audit, services
from ..recommend import recommendation_for_finding
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["findings", "recommendations"])


@router.get("/findings")
def list_findings(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Finding).where(Finding.project_id == project.id).order_by(Finding.created_at.desc())).all())


class FindingIn(BaseModel):
    title: str
    summary: str = ""
    kind: str = "manual"
    affected_implementation_ids: list = []
    failing_scenarios: list = []
    is_demo: bool = False


@router.post("/findings")
def create_finding(body: FindingIn, ctx=Depends(editor)):
    project, db, user = ctx
    f = Finding(project_id=project.id, origin="manual", reproduction_status="literature_claim", status="open", extraction_method="manual",
                status_history=[{"status": "open", "by": user.id, "note": "manual"}], **body.model_dump())
    db.add(f)
    db.flush()
    audit.record(db, user.id, "finding.created", "finding", f.id, project.id, {"title": f.title}, commit=True)
    return row(f)


@router.get("/findings/{fid}")
def get_finding(fid: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    f = get_or_404(db, Finding, fid, project.id)
    runs = [db.get(Run, r) for r in (f.evidence_run_ids or [])]
    impls = [db.get(Implementation, i) for i in (f.affected_implementation_ids or [])]
    props = [db.get(ExperimentProposal, p) for p in (f.experiment_proposal_ids or [])]
    return {**row(f), "source": row(db.get(ResearchSource, f.source_id)) if f.source_id else None,
            "recommendation": row(db.get(Recommendation, f.recommendation_id)) if f.recommendation_id else None,
            "evidence_runs": rows([r for r in runs if r]), "affected_implementations": rows([i for i in impls if i]),
            "revised_implementation": row(db.get(Implementation, f.revised_implementation_id)) if f.revised_implementation_id else None,
            "experiments": rows([p for p in props if p]), "lifecycle": FINDING_STATUSES}


class StatusIn(BaseModel):
    status: str
    note: str = ""


MANUAL_TRANSITIONS = {"open": {"not_relevant"}, "not_relevant": {"open"}, "inconclusive": {"awaiting_retest"}, "still_failing": {"awaiting_retest"},
                      "recommendation_proposed": {"not_relevant"}}


@router.post("/findings/{fid}/status")
def set_status(fid: str, body: StatusIn, ctx=Depends(reviewer)):
    """Only triage-type transitions are manual. Resolution requires a valid retest (see /retest)."""
    project, db, user = ctx
    f = get_or_404(db, Finding, fid, project.id)
    if body.status not in FINDING_STATUSES:
        raise HTTPException(400, "unknown status")
    if body.status not in MANUAL_TRANSITIONS.get(f.status, set()):
        raise HTTPException(409, f"cannot move finding from {f.status} to {body.status} manually; resolution happens only through a valid retest")
    services.set_finding_status(db, f, body.status, user.id, body.note)
    db.commit()
    return row(f)


class ChangeIn(BaseModel):
    revised_implementation_id: str
    change_report: str = ""


@router.post("/findings/{fid}/report-change")
def report_change(fid: str, body: ChangeIn, ctx=Depends(editor)):
    """Customer reports that a change was made externally and links the revised (imported) implementation version."""
    project, db, user = ctx
    f = get_or_404(db, Finding, fid, project.id)
    impl = get_or_404(db, Implementation, body.revised_implementation_id, project.id)
    if impl.id in (f.affected_implementation_ids or []):
        raise HTTPException(400, "the revised implementation must be a new version, not the affected one")
    f.revised_implementation_id = impl.id
    if body.change_report:
        impl.change_report = body.change_report
    services.set_finding_status(db, f, "external_change_reported", user.id, body.change_report[:200])
    services.set_finding_status(db, f, "awaiting_retest", user.id, f"awaiting retest of {impl.name} {impl.version}")
    db.commit()
    return row(f)


class RetestIn(BaseModel):
    run_id: str


@router.post("/findings/{fid}/retest")
def retest(fid: str, body: RetestIn, ctx=Depends(editor)):
    """Evaluate a run of the revised implementation as the retest. Outcome: resolved_within_tested_scope | still_failing | inconclusive.
    A reported fix never closes a finding without a valid retest; failed or invalid retests keep it open."""
    project, db, user = ctx
    f = get_or_404(db, Finding, fid, project.id)
    run = get_or_404(db, Run, body.run_id, project.id)
    if f.status not in ("awaiting_retest", "still_failing", "inconclusive", "external_change_reported"):
        raise HTTPException(409, f"finding is '{f.status}'; report the external change and link the revised implementation first")
    if not f.revised_implementation_id:
        raise HTTPException(409, "no revised implementation linked to this finding")
    ev = services.evaluate_retest(db, f, run)
    if ev.get("outcome") is None:
        raise HTTPException(409, ev["reason"])
    if run.id not in f.evidence_run_ids:
        f.evidence_run_ids = f.evidence_run_ids + [run.id]
    services.set_finding_status(db, f, ev["outcome"], user.id, f"retest run #{run.sequence}: {ev['reason']}")
    db.commit()
    return {**row(f), "retest": ev}


# ---------------------------------------------------------------- recommendations
@router.get("/recommendations")
def list_recs(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Recommendation).where(Recommendation.project_id == project.id).order_by(Recommendation.created_at.desc())).all())


@router.post("/recommendations/from-finding/{fid}")
def from_finding(fid: str, ctx=Depends(editor)):
    project, db, user = ctx
    f = get_or_404(db, Finding, fid, project.id)
    if f.recommendation_id and db.get(Recommendation, f.recommendation_id) and db.get(Recommendation, f.recommendation_id).status not in ("rejected", "superseded"):
        raise HTTPException(409, "finding already has an active recommendation")
    d = recommendation_for_finding(db, f, project)
    rec = Recommendation(project_id=project.id, generated_by="platform (rule-based)", created_by=user.id, status="draft", **d)
    db.add(rec)
    db.flush()
    f.recommendation_id = rec.id
    if f.status == "open":
        services.set_finding_status(db, f, "recommendation_proposed", user.id, f"recommendation {rec.id} drafted")
    audit.record(db, user.id, "recommendation.created", "recommendation", rec.id, project.id, {"finding_id": f.id, "guidance_kind": rec.guidance_kind}, commit=True)
    return row(rec)


class RecIn(BaseModel):
    title: str
    category: str = "other"
    guidance_kind: str = "best_practice"
    body: dict = {}
    finding_id: str | None = None
    target_implementation_id: str | None = None


@router.post("/recommendations")
def create_rec(body: RecIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.guidance_kind not in ("best_practice", "hypothesis", "project_specific"):
        raise HTTPException(400, "bad guidance_kind")
    if body.guidance_kind == "project_specific" and not body.finding_id:
        raise HTTPException(400, "project_specific guidance must reference a finding with evidence")
    rec = Recommendation(project_id=project.id, generated_by="user", created_by=user.id, status="draft", **body.model_dump())
    db.add(rec)
    db.flush()
    audit.record(db, user.id, "recommendation.created", "recommendation", rec.id, project.id, {"title": rec.title}, commit=True)
    return row(rec)


@router.get("/recommendations/{rid}")
def get_rec(rid: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    r = get_or_404(db, Recommendation, rid, project.id)
    approvals = db.scalars(select(Approval).where(Approval.subject_type == "recommendation", Approval.subject_id == r.id)).all()
    return {**row(r), "approvals": rows(approvals), "finding": row(db.get(Finding, r.finding_id)) if r.finding_id else None,
            "target_implementation": row(db.get(Implementation, r.target_implementation_id)) if r.target_implementation_id else None,
            "resulting_implementation": row(db.get(Implementation, r.resulting_implementation_id)) if r.resulting_implementation_id else None}


class DecisionIn(BaseModel):
    decision: str
    note: str = ""


@router.post("/recommendations/{rid}/decide")
def decide(rid: str, body: DecisionIn, ctx=Depends(reviewer)):
    project, db, user = ctx
    r = get_or_404(db, Recommendation, rid, project.id)
    if body.decision not in ("approved", "rejected", "needs_changes", "reviewed"):
        raise HTTPException(400, "bad decision")
    if body.decision == "approved" and r.created_by == user.id and not user.is_admin:
        raise HTTPException(403, "the author of a recommendation cannot approve it (separation of duties)")
    db.add(Approval(project_id=project.id, subject_type="recommendation", subject_id=r.id, decision=body.decision, reviewer_id=user.id, note=body.note))
    r.status = {"approved": "approved", "rejected": "rejected", "needs_changes": "draft", "reviewed": "under_review"}[body.decision]
    audit.record(db, user.id, f"recommendation.{body.decision}", "recommendation", r.id, project.id, {"note": body.note}, commit=True)
    return row(r)
