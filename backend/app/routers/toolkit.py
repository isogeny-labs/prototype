"""Cryptanalysis-suite toolkit (supporting component of Research & Experiments): tool catalog, one-step bounded tool
runs against an implementation, and the imported research portfolio. Each tool run is an append-only platform run
(through the tool's own runner: `cryptanalysis_suite` or `ct_audit`) under a per-project test definition named after
the tool."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..auth import current_user
from ..config import SEED_DIR
from ..models import TestDefinition, Implementation, Run, User
from .. import audit, controls, jobs, services
from runners import get_runner
from runners.suite_runner import suite_identity
from runners.suite_tools import FAMILIES, TOOLS, ParamError
from .common import editor, get_or_404, row, viewer

router = APIRouter(prefix="/api", tags=["toolkit"])


@router.get("/toolkit")
def toolkit(user: User = Depends(current_user)):
    generated = controls.describe()
    tools = []
    for t in TOOLS.values():
        d = t.describe()
        ok, why = get_runner(t.runner).available()
        d["available"], d["unavailable_reason"] = ok, ("" if ok else why)
        d["controls"] = [{**c, "generated": False} for c in d["controls"]] + [g for g in generated.values() if g["tool"] == t.id]
        tools.append(d)
    return {"suite": suite_identity(), "families": list(FAMILIES), "tools": tools,
            "boundary": ["Only the tools listed here can run; each builds its own argv from typed, bounded parameters.",
                         "No executable, subcommand, flag, path or environment value is accepted from callers.",
                         "Every run is an append-only evidence record with argv, binary SHA-256, raw JSON and limitations.",
                         "Secrets recovered from non-synthetic targets are redacted from stored evidence.",
                         "Tool runs analyse public material supplied as parameters; they never execute the customer's source snapshot."]}


class ToolRunIn(BaseModel):
    tool: str
    implementation_id: str
    params: dict = {}
    control: str | None = None       # a generated control id (server builds the params)
    name: str = ""


def tool_test_definition(db, project, tool) -> TestDefinition:
    """One versioned test definition per tool per project (test_id = tool id)."""
    t = db.scalar(select(TestDefinition).where(TestDefinition.project_id == project.id, TestDefinition.test_id == tool.id))
    if not t:
        t = TestDefinition(project_id=project.id, test_id=tool.id, version="1", name=f"Toolkit: {tool.title}", fixture=tool.id,
                           definition={"contract": tool.operation, "tool": tool.id, "params": {}}, acceptance_criteria=list(tool.acceptance),
                           resource_limits={"timeout_s": 120, "memory_mb": 1024, "cpu_s": 120}, description=tool.question)
        db.add(t)
        db.flush()
    return t


def create_tool_run(db, project, impl, user, tool_id: str, params: dict, name: str = "", control_note: dict | None = None):
    """Create a queued tool run; returns (test definition, run). Validation errors raise ParamError."""
    tool = TOOLS[tool_id]
    validated = tool.validate(params)
    tool.build(validated)  # surfaces cross-field errors before anything is recorded
    t = tool_test_definition(db, project, tool)
    runner = get_runner(tool.runner)
    run = services.create_run_record(db, project.id, t.id, impl.id, "platform_sandbox", runner.kind, runner.provenance, user.id)
    run.inputs = {"tool": tool.id, "params": params, "record_name": name or (f"Control: {control_note['name']}" if control_note else tool.title),
                  **({"control": control_note} if control_note else {})}
    run.correction_note = ""
    job = jobs.enqueue(db, "run_test", {"run_id": run.id, "runner_kind": runner.kind, "params": params, "actor_id": user.id})
    run.job_id = job.id
    audit.record(db, user.id, "toolkit.run_queued", "run", run.id, project.id, {"tool": tool.id, "control": (control_note or {}).get("control")})
    db.commit()
    return t, run


@router.post("/projects/{project_id}/toolkit/run")
def run_tool(body: ToolRunIn, ctx=Depends(editor)):
    project, db, user = ctx
    impl = get_or_404(db, Implementation, body.implementation_id, project.id)
    note = None
    tool_id, params = body.tool, body.params
    if body.control:
        if body.control not in controls.GENERATED:
            raise HTTPException(400, "unknown generated control")
        tool_id, params, note = controls.generate(body.control)
    if tool_id not in TOOLS:
        raise HTTPException(400, f"tool must be one of {sorted(TOOLS)}")
    ok, why = get_runner(TOOLS[tool_id].runner).available()
    if not ok:
        raise HTTPException(409, f"runner for {tool_id} unavailable: {why}")
    try:
        _, run = create_tool_run(db, project, impl, user, tool_id, params, body.name, note)
    except ParamError as exc:
        raise HTTPException(400, str(exc)) from exc
    jobs.process_pending()
    db.expire_all()
    return row(db.get(Run, run.id))


@router.get("/projects/{project_id}/toolkit/runs")
def tool_runs(ctx=Depends(viewer)):
    project, db, _ = ctx
    tests = {t.id: t for t in db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id, TestDefinition.fixture.in_(list(TOOLS)))).all()}
    if not tests:
        return []
    runs = db.scalars(select(Run).where(Run.project_id == project.id, Run.test_definition_id.in_(list(tests))).order_by(Run.sequence.desc())).all()
    impls = {i.id: i for i in db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()}
    out = []
    for r in runs:
        i = impls.get(r.implementation_id)
        inp = r.inputs or {}
        out.append({"id": r.id, "sequence": r.sequence, "status": r.status, "classification": r.classification, "overall_pass": r.overall_pass, "metrics": r.metrics,
                    "created_at": r.created_at.isoformat() if r.created_at else None, "tool": tests[r.test_definition_id].fixture,
                    "record_name": inp.get("record_name") or tests[r.test_definition_id].name, "control": inp.get("control"),
                    "implementation_label": f"{i.name} {i.version}" if i else "?", "scenarios_passed": sum(1 for s in r.scenarios or [] if s.get("pass")),
                    "scenarios_total": len(r.scenarios or []), "provenance": r.provenance, "runner_kind": r.runner_kind, "failures": r.failures, "exclusions": r.exclusions, "labels": [l["label"] for l in r.evidence_labels]})
    return out


@router.get("/research/portfolio")
def portfolio(user: User = Depends(current_user)):
    path = SEED_DIR / "research_portfolio.json"
    if not path.exists():
        raise HTTPException(404, "no research portfolio snapshot is installed (scripts/import_research_portfolio.py)")
    return json.loads(path.read_text())
