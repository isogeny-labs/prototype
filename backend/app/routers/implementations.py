from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from ..models import Implementation, Task, Approval, Run, Recommendation, Artifact
from .. import audit, catalog
from .. import artifacts as artstore
from ..recommend import platform_warnings
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}/implementations", tags=["implementations"])
DELIVERY = {"remote", "customer_lab", "isogeny_lab", "onsite", "container"}


class ImplIn(BaseModel):
    name: str
    version: str
    role: str = "candidate"
    profile_id: str | None = None
    algorithm: str = ""
    parameters: dict = {}
    library: str = ""
    library_version: str = ""
    source_revision: str = ""
    configuration: dict = {}
    target_environment: dict = {}
    build_identity: dict = {}
    delivery_mode: str | None = None
    notes: str = ""
    parent_id: str | None = None
    recommendation_id: str | None = None


def compute_warnings(project, impl: Implementation) -> list[str]:
    prof = catalog.profile(impl.profile_id) if impl.profile_id else None
    warnings = platform_warnings(prof, project, None) if prof else []
    if project.kind == "iot" and not impl.target_environment.get("board") and impl.role == "candidate":
        warnings.append("Target board not recorded; on-device evidence cannot be matched to hardware.")
    return warnings


@router.get("")
def list_impls(ctx=Depends(viewer)):
    project, db, _ = ctx
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id).order_by(Implementation.created_at)).all()
    out = []
    for i in impls:
        runs = db.scalars(select(Run).where(Run.implementation_id == i.id)).all()
        out.append({**row(i), "run_count": len(runs), "latest_pass": next((r.overall_pass for r in sorted(runs, key=lambda r: -r.sequence) if r.status == "completed"), None),
                    "profile": catalog.profile(i.profile_id)})
    return out


@router.post("")
def create_impl(body: ImplIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.role not in ("baseline", "candidate"):
        raise HTTPException(400, "role must be baseline|candidate")
    if body.delivery_mode and body.delivery_mode not in DELIVERY:
        raise HTTPException(400, f"delivery_mode must be one of {sorted(DELIVERY)}")
    if body.profile_id and not catalog.profile(body.profile_id):
        raise HTTPException(400, "unknown catalog profile")
    data = body.model_dump()
    if body.profile_id and not body.algorithm:
        data["algorithm"] = catalog.profile(body.profile_id)["label"]
    impl = Implementation(project_id=project.id, created_by=user.id, status="draft" if body.role == "candidate" else "approved", **data)
    db.add(impl)
    db.flush()
    impl.compatibility_warnings = compute_warnings(project, impl)
    if body.recommendation_id:
        rec = db.get(Recommendation, body.recommendation_id)
        if rec and rec.project_id == project.id:
            rec.resulting_implementation_id = impl.id
            if rec.status == "approved":
                rec.status = "implemented"
    audit.record(db, user.id, "implementation.created", "implementation", impl.id, project.id,
                 {"name": impl.name, "version": impl.version, "role": impl.role}, commit=True)
    return row(impl)


@router.get("/{impl_id}")
def get_impl(impl_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    tasks = db.scalars(select(Task).where(Task.implementation_id == impl.id)).all()
    approvals = db.scalars(select(Approval).where(Approval.subject_type == "implementation", Approval.subject_id == impl.id)).all()
    runs = db.scalars(select(Run).where(Run.implementation_id == impl.id).order_by(Run.sequence)).all()
    children = db.scalars(select(Implementation).where(Implementation.parent_id == impl.id)).all()
    return {**row(impl), "tasks": rows(tasks), "approvals": rows(approvals), "runs": rows(runs), "children": rows(children),
            "profile": catalog.profile(impl.profile_id), "compatibility_warnings": compute_warnings(project, impl),
            "change_artifact": row(db.get(Artifact, impl.change_artifact_id)) if impl.change_artifact_id else None}


@router.patch("/{impl_id}")
def update_impl(impl_id: str, body: dict, ctx=Depends(editor)):
    project, db, user = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    if impl.status in ("approved", "superseded", "retired") and any(k in body for k in ("source_revision", "configuration", "profile_id", "library_version")):
        raise HTTPException(409, "an approved/superseded implementation is immutable; create a new version instead")
    for k, v in body.items():
        if k in ImplIn.model_fields:
            setattr(impl, k, v)
    impl.compatibility_warnings = compute_warnings(project, impl)
    audit.record(db, user.id, "implementation.updated", "implementation", impl.id, project.id, {"fields": list(body)}, commit=True)
    return row(impl)


class StatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/{impl_id}/propose")
def propose(impl_id: str, body: StatusIn | None = None, ctx=Depends(editor)):
    project, db, user = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    if impl.status != "draft":
        raise HTTPException(409, f"cannot propose from status {impl.status}")
    impl.status = "proposed"
    audit.record(db, user.id, "implementation.proposed", "implementation", impl.id, project.id, {}, commit=True)
    return row(impl)


class DecisionIn(BaseModel):
    decision: str  # approved | rejected | needs_changes
    note: str = ""


@router.post("/{impl_id}/decide")
def decide(impl_id: str, body: DecisionIn, ctx=Depends(reviewer)):
    """Human approval of an implementation candidate. Creates an Approval record; never deploys anything."""
    project, db, user = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    if body.decision not in ("approved", "rejected", "needs_changes"):
        raise HTTPException(400, "bad decision")
    if impl.status not in ("proposed", "draft"):
        raise HTTPException(409, f"cannot decide from status {impl.status}")
    if impl.created_by == user.id and not user.is_admin and body.decision == "approved":
        raise HTTPException(403, "the author cannot approve their own candidate")
    db.add(Approval(project_id=project.id, subject_type="implementation", subject_id=impl.id, decision=body.decision,
                    reviewer_id=user.id, note=body.note))
    if body.decision == "approved":
        impl.status = "approved"
        if impl.parent_id:
            parent = db.get(Implementation, impl.parent_id)
            if parent and parent.role == "candidate" and parent.status in ("approved", "proposed", "draft"):
                parent.status = "superseded"
    elif body.decision == "rejected":
        impl.status = "rejected"
    else:
        impl.status = "draft"
    audit.record(db, user.id, f"implementation.{body.decision}", "implementation", impl.id, project.id, {"note": body.note}, commit=True)
    return row(impl)


@router.post("/{impl_id}/change-artifact")
def change_artifact(impl_id: str, ctx=Depends(editor)):
    """Create a downloadable proposed-change record (configuration/patch description). Nothing is deployed."""
    project, db, user = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    parent = db.get(Implementation, impl.parent_id) if impl.parent_id else None
    prof = catalog.profile(impl.profile_id) if impl.profile_id else None
    doc = {
        "format": "iel-proposed-change/1",
        "project": {"id": project.id, "name": project.name, "kind": project.kind},
        "implementation": {"id": impl.id, "name": impl.name, "version": impl.version, "status": impl.status,
                           "source_revision": impl.source_revision, "configuration": impl.configuration,
                           "target_environment": impl.target_environment, "build_identity": impl.build_identity,
                           "library": impl.library, "library_version": impl.library_version, "delivery_mode": impl.delivery_mode},
        "replaces": {"id": parent.id, "name": parent.name, "version": parent.version, "algorithm": parent.algorithm} if parent else None,
        "profile": prof, "compatibility_warnings": compute_warnings(project, impl),
        "deployment": "NOT PERFORMED BY THIS PLATFORM. Apply through the customer's existing change process after human approval.",
        "notes": impl.notes,
    }
    content = json.dumps(doc, indent=1, sort_keys=True).encode()
    art = artstore.store(db, project.id, "patch", f"proposed_change_{impl.name}_{impl.version}.json".replace(" ", "_"), content,
                         "application/json", label=f"proposed change record for {impl.name} {impl.version}")
    impl.change_artifact_id = art.id
    audit.record(db, user.id, "implementation.change_artifact", "implementation", impl.id, project.id, {"sha256": art.sha256}, commit=True)
    return row(art)


class TaskIn(BaseModel):
    title: str
    owner: str = ""
    status: str = "open"
    notes: str = ""


@router.post("/{impl_id}/tasks")
def add_task(impl_id: str, body: TaskIn, ctx=Depends(editor)):
    project, db, user = ctx
    impl = get_or_404(db, Implementation, impl_id, project.id)
    t = Task(project_id=project.id, implementation_id=impl.id, **body.model_dump())
    db.add(t)
    db.flush()
    audit.record(db, user.id, "task.created", "task", t.id, project.id, {"title": t.title}, commit=True)
    return row(t)


@router.patch("/{impl_id}/tasks/{task_id}")
def update_task(impl_id: str, task_id: str, body: dict, ctx=Depends(editor)):
    project, db, user = ctx
    t = get_or_404(db, Task, task_id, project.id)
    for k, v in body.items():
        if k in TaskIn.model_fields:
            setattr(t, k, v)
    audit.record(db, user.id, "task.updated", "task", t.id, project.id, {"fields": list(body)}, commit=True)
    return row(t)
