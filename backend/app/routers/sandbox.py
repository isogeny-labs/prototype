from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import SandboxExperiment, Approval, Experiment, Implementation, Run
from .. import audit, jobs, services
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}/sandbox", tags=["sandbox"])

# The ONLY things the sandbox can execute. Each entry bounds parameters so generated proposals cannot escalate.
ALLOWLIST = {
    "toy_factoring": {
        "description": "Pollard rho factoring of a synthetic <= 64-bit semiprime generated in-fixture (workflow demonstration only).",
        "bounds": {"modulus_bits": (16, 64), "trials": (1, 20), "max_iterations": (1000, 20_000_000)},
        "target_class": "synthetic",
    },
}


class ProposalIn(BaseModel):
    title: str
    kind: str
    hypothesis: str = ""
    method: str = ""
    allowlisted_fixture: str | None = None
    parameters: dict = {}
    target_class: str = "synthetic"
    resource_limits: dict = {}
    proposed_by: str = "user"
    finding_id: str | None = None


def _check_bounds(fixture: str, params: dict):
    spec = ALLOWLIST[fixture]["bounds"]
    for k, (lo, hi) in spec.items():
        v = params.get(k)
        if v is not None and not (lo <= int(v) <= hi):
            raise HTTPException(400, f"parameter {k}={v} outside allowlisted bounds [{lo}, {hi}]")


@router.get("/allowlist")
def allowlist():
    return ALLOWLIST


@router.get("")
def list_proposals(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(SandboxExperiment).where(SandboxExperiment.project_id == project.id).order_by(SandboxExperiment.created_at.desc())).all())


@router.post("")
def propose(body: ProposalIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.kind not in ("reproduction", "attack_improvement", "hypothesis", "weakness_harness"):
        raise HTTPException(400, "bad kind")
    if body.allowlisted_fixture:
        if body.allowlisted_fixture not in ALLOWLIST:
            raise HTTPException(400, "fixture is not allowlisted; proposal can be recorded without an executable fixture (set allowlisted_fixture=null)")
        _check_bounds(body.allowlisted_fixture, body.parameters)
    if body.target_class not in ("synthetic", "owned", "authorized"):
        raise HTTPException(400, "target_class must be synthetic|owned|authorized")
    sx = SandboxExperiment(project_id=project.id, status="proposed", **body.model_dump())
    db.add(sx)
    db.flush()
    audit.record(db, user.id, "sandbox.proposed", "sandbox_experiment", sx.id, project.id, {"title": sx.title, "executable": bool(sx.allowlisted_fixture)}, commit=True)
    return row(sx)


class DecisionIn(BaseModel):
    decision: str
    note: str = ""


@router.post("/{sid}/decide")
def decide(sid: str, body: DecisionIn, ctx=Depends(reviewer)):
    project, db, user = ctx
    sx = get_or_404(db, SandboxExperiment, sid, project.id)
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "bad decision")
    if sx.status != "proposed":
        raise HTTPException(409, f"cannot decide from {sx.status}")
    db.add(Approval(project_id=project.id, subject_type="sandbox_experiment", subject_id=sx.id, decision=body.decision, reviewer_id=user.id, note=body.note))
    sx.status = body.decision
    audit.record(db, user.id, f"sandbox.{body.decision}", "sandbox_experiment", sx.id, project.id, {}, commit=True)
    return row(sx)


@router.post("/{sid}/execute")
def execute(sid: str, wait: bool = False, ctx=Depends(editor)):
    """Execute an APPROVED, ALLOWLISTED experiment against a synthetic target in the isolated runner. Nothing else runs."""
    project, db, user = ctx
    sx = get_or_404(db, SandboxExperiment, sid, project.id)
    if sx.status != "approved":
        raise HTTPException(409, "experiment must be approved by a reviewer before execution")
    if not sx.allowlisted_fixture or sx.allowlisted_fixture not in ALLOWLIST:
        raise HTTPException(409, "experiment has no allowlisted fixture; it cannot be executed (proposal only)")
    if sx.target_class != ALLOWLIST[sx.allowlisted_fixture]["target_class"]:
        raise HTTPException(409, "target class does not match the allowlisted fixture")
    _check_bounds(sx.allowlisted_fixture, sx.parameters)
    exp = db.scalar(select(Experiment).where(Experiment.project_id == project.id, Experiment.fixture == sx.allowlisted_fixture))
    if not exp:
        exp = Experiment(project_id=project.id, name=f"Sandbox: {ALLOWLIST[sx.allowlisted_fixture]['description'][:80]}", fixture=sx.allowlisted_fixture,
                         definition={"sandbox": True}, description="Research-only sandbox experiment; not part of product assurance.")
        db.add(exp)
        db.flush()
    impl = db.scalar(select(Implementation).where(Implementation.project_id == project.id, Implementation.name == "Sandbox synthetic target"))
    if not impl:
        impl = Implementation(project_id=project.id, name="Sandbox synthetic target", version="n/a", role="candidate", status="retired",
                              algorithm="synthetic toy parameters", notes="Placeholder target for research-only sandbox runs.", created_by=user.id)
        db.add(impl)
        db.flush()
    run = services.create_run_record(db, project.id, exp.id, impl.id, "local_fixture", "measured", user.id)
    job = jobs.enqueue(db, "sandbox_execute", {"sandbox_id": sx.id, "run_id": run.id, "actor_id": user.id})
    run.job_id = job.id
    audit.record(db, user.id, "sandbox.executed", "sandbox_experiment", sx.id, project.id, {"run_id": run.id})
    db.commit()
    if wait:
        jobs.process_pending()
        db.expire_all()
        sx = db.get(SandboxExperiment, sx.id)
    return {**row(sx), "run_id": run.id, "job_id": job.id}


@router.post("/{sid}/verify")
def verify(sid: str, body: DecisionIn, ctx=Depends(reviewer)):
    """Mark an executed result as verified (human). Executed != verified."""
    project, db, user = ctx
    sx = get_or_404(db, SandboxExperiment, sid, project.id)
    if sx.status != "executed":
        raise HTTPException(409, "only executed experiments can be verified")
    db.add(Approval(project_id=project.id, subject_type="sandbox_experiment", subject_id=sx.id, decision="reviewed", reviewer_id=user.id, note=body.note))
    sx.status = "verified"
    audit.record(db, user.id, "sandbox.verified", "sandbox_experiment", sx.id, project.id, {}, commit=True)
    return row(sx)
