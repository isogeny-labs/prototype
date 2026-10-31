from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import current_user, accessible_project_ids
from ..models import (Project, ProjectMember, InventoryItem, Requirement, Implementation, Run, Finding, Recommendation,
                      User, AuditEvent, Approval)
from .. import audit
from .common import row, rows, viewer, editor, owner, get_or_404

router = APIRouter(prefix="/api", tags=["projects"])
PROVENANCE = {"user_reported", "imported", "verified"}


class ProjectIn(BaseModel):
    name: str
    kind: str
    business_purpose: str = ""
    deployment_environment: str = ""
    support_period_end: str | None = None
    data_protection_requirements: str = ""
    update_process: str = ""
    platform: dict = {}


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = accessible_project_ids(db, user)
    out = []
    for p in db.scalars(select(Project).where(Project.id.in_(ids))).all() if ids else []:
        runs = db.scalars(select(Run).where(Run.project_id == p.id)).all()
        findings = db.scalars(select(Finding).where(Finding.project_id == p.id)).all()
        last = max(runs, key=lambda r: r.sequence, default=None)
        out.append({**row(p),
                    "counts": {"implementations": db.query(Implementation).filter_by(project_id=p.id).count(),
                               "runs": len(runs), "runs_failed": sum(1 for r in runs if r.overall_pass is False),
                               "findings_open": sum(1 for f in findings if f.status not in ("closed", "not_relevant")),
                               "recommendations_pending": db.query(Recommendation).filter(Recommendation.project_id == p.id,
                                                                                          Recommendation.status.in_(["draft", "under_review"])).count()},
                    "last_run": row(last) and {"sequence": last.sequence, "overall_pass": last.overall_pass, "provenance": last.provenance,
                                               "created_at": last.created_at.isoformat()} if last else None})
    return out


@router.post("/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.kind not in ("iot", "application"):
        raise HTTPException(400, "kind must be iot|application")
    p = Project(**body.model_dump(), created_by=user.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role="owner"))
    audit.record(db, user.id, "project.created", "project", p.id, p.id, {"name": p.name}, commit=True)
    return row(p)


@router.get("/projects/{project_id}")
def get_project(ctx=Depends(viewer)):
    project, db, user = ctx
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id)).all()
    return {**row(project), "members": [{**row(m), "email": db.get(User, m.user_id).email, "name": db.get(User, m.user_id).name} for m in members]}


@router.patch("/projects/{project_id}")
def update_project(body: dict, ctx=Depends(editor)):
    project, db, user = ctx
    for k, v in body.items():
        if k in ProjectIn.model_fields:
            setattr(project, k, v)
    audit.record(db, user.id, "project.updated", "project", project.id, project.id, {"fields": list(body)}, commit=True)
    return row(project)


class MemberIn(BaseModel):
    email: str
    role: str


@router.post("/projects/{project_id}/members")
def add_member(body: MemberIn, ctx=Depends(owner)):
    project, db, user = ctx
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if not u:
        raise HTTPException(404, "user not found")
    if body.role not in ("owner", "editor", "reviewer", "viewer"):
        raise HTTPException(400, "bad role")
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == u.id))
    if m:
        m.role = body.role
    else:
        m = ProjectMember(project_id=project.id, user_id=u.id, role=body.role)
        db.add(m)
    audit.record(db, user.id, "member.set", "project", project.id, project.id, {"email": u.email, "role": body.role}, commit=True)
    return row(m)


# ---------------------------------------------------------------- overview
@router.get("/projects/{project_id}/overview")
def overview(ctx=Depends(viewer)):
    """What changed, what did we test, what did we learn, what should engineering do next."""
    project, db, user = ctx
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id).order_by(Implementation.created_at)).all()
    runs = db.scalars(select(Run).where(Run.project_id == project.id).order_by(Run.sequence)).all()
    findings = db.scalars(select(Finding).where(Finding.project_id == project.id).order_by(Finding.created_at)).all()
    recs = db.scalars(select(Recommendation).where(Recommendation.project_id == project.id).order_by(Recommendation.created_at)).all()
    approvals = db.scalars(select(Approval).where(Approval.project_id == project.id).order_by(Approval.created_at.desc()).limit(10)).all()
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project.id)).all()
    audit_ev = db.scalars(select(AuditEvent).where(AuditEvent.project_id == project.id).order_by(AuditEvent.created_at.desc()).limit(15)).all()
    impl_by = {i.id: i for i in impls}
    latest_by_impl = {}
    for r in runs:
        if r.status == "completed":
            latest_by_impl[r.implementation_id] = r
    what_changed = [{"implementation": f"{i.name} {i.version}", "status": i.status, "role": i.role, "created_at": i.created_at.isoformat(),
                     "parent": (impl_by.get(i.parent_id).version if i.parent_id in impl_by else None)} for i in impls[-6:]]
    what_tested = [{"run": r.sequence, "implementation": f"{impl_by[r.implementation_id].name} {impl_by[r.implementation_id].version}" if r.implementation_id in impl_by else "?",
                    "provenance": r.provenance, "overall_pass": r.overall_pass, "status": r.status,
                    "failed_requirements": [x["name"] for x in r.requirement_results if x.get("pass") is False],
                    "created_at": r.created_at.isoformat()} for r in runs[-8:]]
    what_learned = [{"id": f.id, "title": f.title, "origin": f.origin, "status": f.status, "is_demo": f.is_demo} for f in findings if f.status not in ("closed",)][-8:]
    next_actions = []
    for f in findings:
        if f.status in ("new", "triage"):
            next_actions.append({"action": "Triage research/measurement finding", "ref": f.id, "kind": "finding", "label": f.title})
        elif f.status in ("relevant", "experiment_proposed") and not f.recommendation_id:
            next_actions.append({"action": "Generate remediation proposal", "ref": f.id, "kind": "finding", "label": f.title})
        elif f.status == "action_approved":
            next_actions.append({"action": "Rerun / import tests for the approved candidate", "ref": f.id, "kind": "finding", "label": f.title})
        elif f.status == "retested":
            next_actions.append({"action": "Compare evidence and close or reopen", "ref": f.id, "kind": "finding", "label": f.title})
    for rc in recs:
        if rc.status in ("draft", "under_review"):
            next_actions.append({"action": "Human review of recommendation", "ref": rc.id, "kind": "recommendation", "label": rc.title})
        elif rc.status == "approved" and not rc.resulting_implementation_id:
            next_actions.append({"action": "Create implementation candidate from approved recommendation", "ref": rc.id, "kind": "recommendation", "label": rc.title})
    for i in impls:
        if i.status == "proposed":
            next_actions.append({"action": "Approve or reject implementation candidate", "ref": i.id, "kind": "implementation", "label": f"{i.name} {i.version}"})
        if i.status in ("approved", "proposed") and i.id not in latest_by_impl:
            next_actions.append({"action": "No evidence yet: run fixture or import measurements", "ref": i.id, "kind": "implementation", "label": f"{i.name} {i.version}"})
    req_status = []
    for rq in reqs:
        obs = []
        for impl_id, r in latest_by_impl.items():
            for x in r.requirement_results:
                if x["requirement_id"] == rq.id and x.get("pass") is not None:
                    obs.append({"implementation": f"{impl_by[impl_id].name} {impl_by[impl_id].version}", "observed": x["observed"], "pass": x["pass"], "provenance": r.provenance})
        req_status.append({**row(rq), "latest": obs})
    return {"project": row(project), "what_changed": what_changed, "what_tested": what_tested, "what_learned": what_learned,
            "next_actions": next_actions[:12], "requirements": req_status, "recent_approvals": rows(approvals),
            "recent_audit": rows(audit_ev)}


@router.get("/projects/{project_id}/audit")
def audit_log(ctx=Depends(viewer)):
    project, db, user = ctx
    evs = db.scalars(select(AuditEvent).where(AuditEvent.project_id == project.id).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    return [{**row(e), "actor": users.get(e.actor_id)} for e in evs]


# ---------------------------------------------------------------- inventory
class InventoryIn(BaseModel):
    category: str
    name: str
    purpose: str | None = None
    parameters: dict = {}
    version: str | None = None
    notes: str = ""
    provenance: str = "user_reported"
    provenance_detail: str = ""


@router.get("/projects/{project_id}/inventory")
def list_inventory(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(InventoryItem).where(InventoryItem.project_id == project.id).order_by(InventoryItem.category)).all())


@router.post("/projects/{project_id}/inventory")
def add_inventory(body: InventoryIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.provenance not in PROVENANCE:
        raise HTTPException(400, f"provenance must be one of {sorted(PROVENANCE)}")
    if body.provenance == "verified" and not body.provenance_detail:
        raise HTTPException(400, "verified facts must say how they were verified (provenance_detail)")
    if body.category == "key_storage" and any(k in str(body.parameters).lower() for k in ("private_key", "-----begin")):
        raise HTTPException(400, "do not upload private key material")
    it = InventoryItem(project_id=project.id, **body.model_dump())
    db.add(it)
    db.flush()
    audit.record(db, user.id, "inventory.added", "inventory_item", it.id, project.id, {"name": it.name, "provenance": it.provenance}, commit=True)
    return row(it)


@router.post("/projects/{project_id}/inventory/import")
def import_inventory(body: dict, ctx=Depends(editor)):
    """Structured JSON inventory import. Format: {"items": [InventoryIn...], "requirements": [RequirementIn...], "platform": {...}}.
    Every imported fact is labelled provenance=imported unless the document says user_reported."""
    project, db, user = ctx
    created, reqs = [], []
    for raw in body.get("items", []):
        item = InventoryIn(**raw)
        if item.provenance == "verified":
            item.provenance = "imported"  # an import cannot assert verification
            item.provenance_detail = (item.provenance_detail + " (downgraded from 'verified' on import)").strip()
        if item.provenance not in PROVENANCE:
            item.provenance = "imported"
        if "-----begin" in str(raw).lower():
            raise HTTPException(400, "import contains key material; rejected")
        it = InventoryItem(project_id=project.id, **item.model_dump())
        db.add(it)
        created.append(it)
    for raw in body.get("requirements", []):
        rq = Requirement(project_id=project.id, **RequirementIn(**raw).model_dump())
        db.add(rq)
        reqs.append(rq)
    if body.get("platform"):
        project.platform = {**(project.platform or {}), **body["platform"]}
    db.flush()
    audit.record(db, user.id, "inventory.imported", "project", project.id, project.id, {"items": len(created), "requirements": len(reqs)}, commit=True)
    return {"items": rows(created), "requirements": rows(reqs), "platform": project.platform}


@router.patch("/projects/{project_id}/inventory/{item_id}")
def update_inventory(item_id: str, body: dict, ctx=Depends(editor)):
    project, db, user = ctx
    it = get_or_404(db, InventoryItem, item_id, project.id)
    if body.get("provenance") == "verified" and not body.get("provenance_detail", it.provenance_detail):
        raise HTTPException(400, "verified facts must say how they were verified")
    for k, v in body.items():
        if k in InventoryIn.model_fields:
            setattr(it, k, v)
    audit.record(db, user.id, "inventory.updated", "inventory_item", it.id, project.id, {"fields": list(body)}, commit=True)
    return row(it)


@router.delete("/projects/{project_id}/inventory/{item_id}")
def delete_inventory(item_id: str, ctx=Depends(editor)):
    project, db, user = ctx
    it = get_or_404(db, InventoryItem, item_id, project.id)
    db.delete(it)
    audit.record(db, user.id, "inventory.deleted", "inventory_item", item_id, project.id, {"name": it.name}, commit=True)
    return {"ok": True}


# ---------------------------------------------------------------- requirements
class RequirementIn(BaseModel):
    name: str
    metric: str
    operator: str
    threshold: float
    unit: str = ""
    rationale: str = ""
    applies_to: str = "all"


@router.get("/projects/{project_id}/requirements")
def list_requirements(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Requirement).where(Requirement.project_id == project.id)).all())


@router.post("/projects/{project_id}/requirements")
def add_requirement(body: RequirementIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.operator not in ("<=", ">=", "<", ">", "=="):
        raise HTTPException(400, "bad operator")
    rq = Requirement(project_id=project.id, **body.model_dump())
    db.add(rq)
    db.flush()
    audit.record(db, user.id, "requirement.added", "requirement", rq.id, project.id, {"name": rq.name}, commit=True)
    return row(rq)


@router.delete("/projects/{project_id}/requirements/{req_id}")
def delete_requirement(req_id: str, ctx=Depends(editor)):
    project, db, user = ctx
    rq = get_or_404(db, Requirement, req_id, project.id)
    db.delete(rq)
    audit.record(db, user.id, "requirement.deleted", "requirement", req_id, project.id, {"name": rq.name}, commit=True)
    return {"ok": True}
