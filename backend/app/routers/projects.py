from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth import current_user, accessible_project_ids
from ..models import (Project, ProjectMember, InventoryItem, Requirement, Implementation, Run, Finding, Recommendation, User, AuditEvent,
                      TestDefinition, ExperimentProposal, Approval)
from .. import audit
from .common import row, rows, viewer, editor, owner, get_or_404

router = APIRouter(prefix="/api", tags=["projects"])
PROVENANCE = {"user_reported", "detected", "independently_tested"}
PURPOSES = {"signatures", "key_establishment", "encryption"}


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    intended_use: str = ""
    threat_assumptions: str = ""
    runtime_environment: dict = {}
    workflow: str = "signature_library"


def _latest_runs(runs):
    """latest completed, non-duplicate, non-stale run per (implementation, test)."""
    out = {}
    for r in runs:
        if r.status in ("queued", "running") or r.duplicate_of_run_id or r.stale_reason:
            continue
        out[(r.implementation_id, r.test_definition_id)] = r
    return out


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = accessible_project_ids(db, user)
    out = []
    for p in (db.scalars(select(Project).where(Project.id.in_(ids))).all() if ids else []):
        runs = db.scalars(select(Run).where(Run.project_id == p.id)).all()
        latest = _latest_runs(runs)
        impls = db.scalars(select(Implementation).where(Implementation.project_id == p.id).order_by(Implementation.imported_at)).all()
        cur = impls[-1] if impls else None
        findings = db.scalars(select(Finding).where(Finding.project_id == p.id)).all()
        out.append({**row(p), "current_implementation": f"{cur.name} {cur.version}" if cur else None,
                    "counts": {"implementations": len(impls), "runs": len([r for r in runs if not r.duplicate_of_run_id]),
                               "failed": sum(1 for r in latest.values() if r.classification == "failed"),
                               "open_findings": sum(1 for f in findings if f.status not in ("resolved_within_tested_scope", "not_relevant")),
                               "proposals_awaiting": db.query(ExperimentProposal).filter_by(project_id=p.id, status="proposed").count(),
                               "recommendations_awaiting_implementation": db.query(Recommendation).filter(Recommendation.project_id == p.id, Recommendation.status == "approved",
                                                                                                           Recommendation.resulting_implementation_id.is_(None)).count()}})
    return out


@router.post("/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.workflow != "signature_library":
        raise HTTPException(400, "only the 'signature_library' workflow is supported in this MVP (IoT and application adapters are future placeholders)")
    p = Project(**body.model_dump(), created_by=user.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role="owner"))
    from ..seed import default_test_definitions
    for t in default_test_definitions(p.id):
        db.add(t)
    audit.record(db, user.id, "project.created", "project", p.id, p.id, {"name": p.name}, commit=True)
    return row(p)


@router.get("/projects/{project_id}")
def get_project(ctx=Depends(viewer)):
    project, db, user = ctx
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id)).all()
    return {**row(project), "members": [{**row(m), "email": db.get(User, m.user_id).email} for m in members]}


@router.patch("/projects/{project_id}")
def update_project(body: dict, ctx=Depends(editor)):
    project, db, user = ctx
    for k, v in body.items():
        if k in ProjectIn.model_fields and k != "workflow":
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
    project, db, _ = ctx
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id).order_by(Implementation.imported_at)).all()
    tests = db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id)).all()
    runs = db.scalars(select(Run).where(Run.project_id == project.id).order_by(Run.sequence)).all()
    findings = db.scalars(select(Finding).where(Finding.project_id == project.id).order_by(Finding.created_at)).all()
    recs = db.scalars(select(Recommendation).where(Recommendation.project_id == project.id)).all()
    props = db.scalars(select(ExperimentProposal).where(ExperimentProposal.project_id == project.id)).all()
    latest = _latest_runs(runs)
    cur = next((i for i in reversed(impls) if i.status not in ("retired",)), None)
    prev = next((i for i in reversed(impls) if cur and i.id == cur.parent_id), None) or (impls[-2] if len(impls) > 1 else None)
    core_tests = [t for t in tests if t.fixture == "signature_library"]  # core coverage only; experiments and toolkit tools are tracked elsewhere

    def status_for(impl, test):
        r = latest.get((impl.id, test.id))
        if not r:
            return {"status": "not_tested"}
        return {"status": r.classification, "run_id": r.id, "sequence": r.sequence, "execution_mode": r.execution_mode, "labels": [l["label"] for l in r.evidence_labels],
                "failing": [s["id"] for s in r.scenarios if s.get("pass") is False]}

    coverage = [{"implementation": {"id": i.id, "label": f"{i.name} {i.version}", "status": i.status}, "tests": {t.test_id: status_for(i, t) for t in core_tests}} for i in impls]
    untested = []
    if cur:
        for t in core_tests:
            if (cur.id, t.id) not in latest:
                untested.append(f"{t.name} not run against {cur.name} {cur.version}")
        if cur.adapter_kind == "results_only":
            untested.append("implementation is results-only: no sandbox execution possible")
        if cur.compatibility.get("status") == "unsupported":
            untested.append("source snapshot is unsupported; only imported results are available")
    untested += ["Key management, protocol integration and side-channel behaviour are outside the test definitions."]
    latest_bench = None
    if cur:
        for t in core_tests:
            r = latest.get((cur.id, t.id))
            if r and r.metrics:
                latest_bench = {"run_id": r.id, "sequence": r.sequence, "execution_mode": r.execution_mode, "classification": r.classification,
                                "metrics": {k: r.metrics.get(k) for k in ("sign_time_ms_median", "verify_time_ms_median", "verify_time_ms_p95", "sign_throughput_per_s",
                                                                           "verify_throughput_per_s", "signature_bytes", "public_key_bytes", "verify_peak_alloc_kb", "official_vectors") if k in r.metrics},
                                "requirement_results": r.requirement_results}
    changes = None
    if cur and prev:
        diff = {}
        for k in ("algorithm", "library", "library_version", "source_revision", "source_digest", "dependencies", "configuration"):
            a, b = getattr(prev, k), getattr(cur, k)
            if a != b:
                diff[k] = {"previous": a, "current": b}
        sc = {}
        for t in core_tests:
            ra, rb = latest.get((prev.id, t.id)), latest.get((cur.id, t.id))
            if ra and rb:
                sa, sb = {s["id"]: s.get("pass") for s in ra.scenarios}, {s["id"]: s.get("pass") for s in rb.scenarios}
                sc[t.test_id] = {"fixed": [i for i in sa if sa[i] is False and sb.get(i) is True], "regressed": [i for i in sa if sa[i] is True and sb.get(i) is False],
                                 "classification": {"previous": ra.classification, "current": rb.classification}}
        changes = {"previous": f"{prev.name} {prev.version}", "current": f"{cur.name} {cur.version}", "manifest_diff": diff, "test_outcomes": sc,
                   "change_report": cur.change_report}
    open_f = [f for f in findings if f.status not in ("resolved_within_tested_scope", "not_relevant")]
    next_experiment = next(({"id": p.id, "title": p.title, "status": p.status, "executable": bool(p.allowlisted_fixture)} for p in props if p.status in ("proposed", "approved")), None)
    consider = [{"id": r.id, "title": r.title, "guidance_kind": r.guidance_kind, "status": r.status, "awaiting_external_implementation": r.status == "approved" and not r.resulting_implementation_id} for r in recs if r.status in ("approved", "under_review", "draft")]
    return {"project": row(project),
            "current_implementation": ({**row(cur), "seeded_defect": cur.seeded_defect} if cur else None),
            "coverage": coverage, "untested": untested, "latest_benchmark": latest_bench,
            "open_findings": [{"id": f.id, "title": f.title, "kind": f.kind, "status": f.status, "is_demo": f.is_demo, "reproduction_status": f.reproduction_status} for f in open_f],
            "proposals_awaiting_approval": [{"id": p.id, "title": p.title, "executable": bool(p.allowlisted_fixture)} for p in props if p.status == "proposed"],
            "recommendations": consider, "next_experiment": next_experiment, "changes_since_previous": changes,
            "status_legend": {"not_tested": "No run of this test against this version", "passed_defined_checks": "All defined scenarios and applicable limits passed",
                              "failed": "At least one scenario or limit failed", "inconclusive": "The run did not complete or could not be interpreted",
                              "unsupported": "The implementation cannot be executed by this test", "awaiting_review": "Imported evidence pending human review"}}


@router.get("/projects/{project_id}/audit")
def audit_log(ctx=Depends(viewer)):
    project, db, _ = ctx
    evs = db.scalars(select(AuditEvent).where(AuditEvent.project_id == project.id).order_by(AuditEvent.created_at.desc()).limit(300)).all()
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    return [{**row(e), "actor": users.get(e.actor_id)} for e in evs]


# ---------------------------------------------------------------- inventory / requirements
class InventoryIn(BaseModel):
    category: str
    name: str
    purpose: str | None = None
    parameters: dict = {}
    version: str | None = None
    notes: str = ""
    provenance: str = "user_reported"
    provenance_detail: str = ""
    implementation_id: str | None = None


@router.get("/projects/{project_id}/inventory")
def list_inventory(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(InventoryItem).where(InventoryItem.project_id == project.id).order_by(InventoryItem.category)).all())


@router.post("/projects/{project_id}/inventory")
def add_inventory(body: InventoryIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.provenance not in PROVENANCE:
        raise HTTPException(400, f"provenance must be one of {sorted(PROVENANCE)}")
    if body.provenance == "independently_tested" and not body.provenance_detail:
        raise HTTPException(400, "independently_tested facts must reference the run or review that established them")
    if body.purpose and body.purpose not in PURPOSES:
        raise HTTPException(400, f"purpose must be one of {sorted(PURPOSES)}")
    from ..compat import scan_secrets
    if scan_secrets(str(body.model_dump()).encode()):
        raise HTTPException(400, "inventory entries must not contain private keys or credentials")
    it = InventoryItem(project_id=project.id, **body.model_dump())
    db.add(it)
    db.flush()
    audit.record(db, user.id, "inventory.added", "inventory_item", it.id, project.id, {"name": it.name, "provenance": it.provenance}, commit=True)
    return row(it)


@router.delete("/projects/{project_id}/inventory/{item_id}")
def delete_inventory(item_id: str, ctx=Depends(editor)):
    project, db, user = ctx
    it = get_or_404(db, InventoryItem, item_id, project.id)
    db.delete(it)
    audit.record(db, user.id, "inventory.deleted", "inventory_item", item_id, project.id, {"name": it.name}, commit=True)
    return {"ok": True}


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
