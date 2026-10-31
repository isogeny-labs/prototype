from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import Recommendation, Approval, InventoryItem, Requirement, Implementation, Finding
from .. import audit, catalog, recommend, services
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}/recommendations", tags=["recommendations"])


@router.get("")
def list_recs(ctx=Depends(viewer)):
    project, db, _ = ctx
    recs = db.scalars(select(Recommendation).where(Recommendation.project_id == project.id).order_by(Recommendation.created_at)).all()
    return [{**row(r), "profile": catalog.profile(r.catalog_profile_id)} for r in recs]


@router.post("/generate")
def generate(ctx=Depends(editor)):
    """Generate candidate recommendations from the curated catalog for every inventory algorithm. Status: draft (needs human review)."""
    project, db, user = ctx
    items = db.scalars(select(InventoryItem).where(InventoryItem.project_id == project.id)).all()
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project.id)).all()
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()
    drafts = recommend.generate_for_project(project, items, reqs, impls)
    created = []
    existing = {(r.title) for r in db.scalars(select(Recommendation).where(Recommendation.project_id == project.id, Recommendation.status.notin_(["rejected", "superseded"]))).all()}
    for d in drafts:
        if d["title"] in existing:
            continue
        rec = Recommendation(project_id=project.id, generated_by="catalog", created_by=user.id, status="draft", **d)
        db.add(rec)
        created.append(rec)
    db.flush()
    audit.record(db, user.id, "recommendation.generated", "project", project.id, project.id, {"count": len(created)}, commit=True)
    return [{**row(r), "profile": catalog.profile(r.catalog_profile_id)} for r in created]


class ManualRecIn(BaseModel):
    title: str
    kind: str = "configuration"
    catalog_profile_id: str | None = None
    purpose: str | None = None
    body: dict = {}
    finding_id: str | None = None
    target_implementation_id: str | None = None


@router.post("")
def create_manual(body: ManualRecIn, ctx=Depends(editor)):
    project, db, user = ctx
    rec = Recommendation(project_id=project.id, generated_by="user", created_by=user.id, status="draft", **body.model_dump())
    db.add(rec)
    db.flush()
    audit.record(db, user.id, "recommendation.created", "recommendation", rec.id, project.id, {"title": rec.title}, commit=True)
    return row(rec)


@router.post("/from-finding/{finding_id}")
def remediation_from_finding(finding_id: str, ctx=Depends(editor)):
    """Assisted remediation: build a proposal from a finding and link it. Human approval is still required."""
    project, db, user = ctx
    f = get_or_404(db, Finding, finding_id, project.id)
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project.id)).all()
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()
    target = next((db.get(Implementation, i) for i in (f.affected_implementation_ids or []) if db.get(Implementation, i)), None)
    draft = recommend.remediation_for_finding(f, project, reqs, target, impls)
    if not draft:
        raise HTTPException(409, "cannot build a remediation: finding has no affected implementation with a known purpose")
    rec = Recommendation(project_id=project.id, generated_by="researcher" if f.origin == "research" else "catalog", created_by=user.id,
                         status="draft", finding_id=f.id, target_implementation_id=target.id if target else None, **draft)
    db.add(rec)
    db.flush()
    f.recommendation_id = rec.id
    if f.status in ("new", "triage", "relevant"):
        services.set_finding_status(db, f, "experiment_proposed", user.id, f"remediation proposal {rec.id} drafted")
    audit.record(db, user.id, "recommendation.remediation", "recommendation", rec.id, project.id, {"finding_id": f.id}, commit=True)
    return {**row(rec), "profile": catalog.profile(rec.catalog_profile_id)}


@router.get("/{rec_id}")
def get_rec(rec_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    rec = get_or_404(db, Recommendation, rec_id, project.id)
    approvals = db.scalars(select(Approval).where(Approval.subject_type == "recommendation", Approval.subject_id == rec.id)).all()
    return {**row(rec), "profile": catalog.profile(rec.catalog_profile_id), "approvals": rows(approvals),
            "finding": row(db.get(Finding, rec.finding_id)) if rec.finding_id else None,
            "target_implementation": row(db.get(Implementation, rec.target_implementation_id)) if rec.target_implementation_id else None,
            "resulting_implementation": row(db.get(Implementation, rec.resulting_implementation_id)) if rec.resulting_implementation_id else None}


class DecisionIn(BaseModel):
    decision: str  # approved | rejected | needs_changes | reviewed
    note: str = ""


@router.post("/{rec_id}/decide")
def decide(rec_id: str, body: DecisionIn, ctx=Depends(reviewer)):
    project, db, user = ctx
    rec = get_or_404(db, Recommendation, rec_id, project.id)
    if body.decision not in ("approved", "rejected", "needs_changes", "reviewed"):
        raise HTTPException(400, "bad decision")
    if body.decision == "approved" and rec.created_by == user.id and not user.is_admin:
        raise HTTPException(403, "the author of a recommendation cannot approve it (separation of duties)")
    db.add(Approval(project_id=project.id, subject_type="recommendation", subject_id=rec.id, decision=body.decision, reviewer_id=user.id, note=body.note))
    rec.status = {"approved": "approved", "rejected": "rejected", "needs_changes": "draft", "reviewed": "under_review"}[body.decision]
    if rec.finding_id:
        f = db.get(Finding, rec.finding_id)
        if f and body.decision == "reviewed" and f.status in ("experiment_proposed", "relevant"):
            services.set_finding_status(db, f, "reviewed", user.id, "recommendation reviewed")
        if f and body.decision == "approved" and f.status in ("experiment_proposed", "reviewed", "relevant"):
            services.set_finding_status(db, f, "action_approved", user.id, f"recommendation {rec.id} approved")
    audit.record(db, user.id, f"recommendation.{body.decision}", "recommendation", rec.id, project.id, {"note": body.note}, commit=True)
    return row(rec)


class ImplementIn(BaseModel):
    name: str
    version: str
    source_revision: str = ""
    library: str = ""
    library_version: str = ""
    configuration: dict = {}
    target_environment: dict = {}
    build_identity: dict = {}
    delivery_mode: str | None = None
    notes: str = ""


@router.post("/{rec_id}/implement")
def implement(rec_id: str, body: ImplementIn, ctx=Depends(editor)):
    """Create a new implementation candidate version from an APPROVED recommendation (the human gate)."""
    project, db, user = ctx
    rec = get_or_404(db, Recommendation, rec_id, project.id)
    if rec.status != "approved":
        raise HTTPException(409, "recommendation must be approved before implementation")
    prof = catalog.profile(rec.catalog_profile_id) if rec.catalog_profile_id else None
    impl = Implementation(project_id=project.id, created_by=user.id, role="candidate", status="draft",
                          profile_id=rec.catalog_profile_id, algorithm=prof["label"] if prof else "",
                          parent_id=rec.target_implementation_id, recommendation_id=rec.id, **body.model_dump())
    db.add(impl)
    db.flush()
    from .implementations import compute_warnings
    impl.compatibility_warnings = compute_warnings(project, impl)
    rec.resulting_implementation_id = impl.id
    rec.status = "implemented"
    audit.record(db, user.id, "implementation.from_recommendation", "implementation", impl.id, project.id, {"recommendation_id": rec.id}, commit=True)
    return row(impl)
