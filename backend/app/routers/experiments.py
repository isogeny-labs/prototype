from __future__ import annotations
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from ..models import Experiment, Run, Implementation, Artifact, Requirement, Job
from .. import audit, jobs, services
from .. import artifacts as artstore
from runners import RunnerUnavailable, list_runners, get_runner, RunRequest
from .common import row, rows, viewer, editor, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["experiments", "runs"])
from runners.suite_tools import TOOLS as SUITE_TOOLS

FIXTURES = {"firmware_signing", "app_service_crypto", "toy_factoring", "external", *SUITE_TOOLS}


class ExperimentIn(BaseModel):
    name: str
    fixture: str
    definition: dict = {}
    acceptance_criteria: list = []
    description: str = ""


@router.get("/experiments")
def list_experiments(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Experiment).where(Experiment.project_id == project.id)).all())


@router.post("/experiments")
def create_experiment(body: ExperimentIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.fixture not in FIXTURES:
        raise HTTPException(400, f"fixture must be one of {sorted(FIXTURES)}")
    e = Experiment(project_id=project.id, **body.model_dump())
    db.add(e)
    db.flush()
    audit.record(db, user.id, "experiment.created", "experiment", e.id, project.id, {"name": e.name}, commit=True)
    return row(e)


# ---------------------------------------------------------------- runs
class RunIn(BaseModel):
    experiment_id: str
    implementation_id: str
    runner_kind: str = "local_fixture"
    params: dict = {}
    supersedes_run_id: str | None = None
    correction_note: str = ""
    wait: bool = False  # process synchronously (tests / small fixtures)


@router.get("/runs")
def list_runs(ctx=Depends(viewer)):
    project, db, _ = ctx
    runs = db.scalars(select(Run).where(Run.project_id == project.id).order_by(Run.sequence)).all()
    impls = {i.id: i for i in db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()}
    exps = {e.id: e for e in db.scalars(select(Experiment).where(Experiment.project_id == project.id)).all()}
    return [{**row(r), "implementation_label": f"{impls[r.implementation_id].name} {impls[r.implementation_id].version}" if r.implementation_id in impls else "?",
             "experiment_name": exps[r.experiment_id].name if r.experiment_id in exps else "?"} for r in runs]


@router.post("/runs")
def create_run(body: RunIn, ctx=Depends(editor)):
    """Queue a fixture run. Runs are append-only; `supersedes_run_id` records a correction without deleting anything."""
    project, db, user = ctx
    exp = get_or_404(db, Experiment, body.experiment_id, project.id)
    impl = get_or_404(db, Implementation, body.implementation_id, project.id)
    try:
        runner = get_runner(body.runner_kind)
    except RunnerUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    ok, why = runner.available()
    if not ok:
        raise HTTPException(409, f"runner '{body.runner_kind}' unavailable: {why}")
    if not runner.supports(exp.fixture):
        raise HTTPException(400, f"runner '{body.runner_kind}' does not support fixture '{exp.fixture}'")
    if exp.fixture == "external":
        raise HTTPException(400, "experiment is import-only; use /runs/import")
    if body.supersedes_run_id:
        prev = get_or_404(db, Run, body.supersedes_run_id, project.id)
        if not body.correction_note:
            raise HTTPException(400, "a correction must carry a correction_note")
    run = services.create_run_record(db, project.id, exp.id, impl.id, body.runner_kind, runner.provenance, user.id,
                                     body.supersedes_run_id, body.correction_note)
    job = jobs.enqueue(db, "run_fixture", {"run_id": run.id, "runner_kind": body.runner_kind, "params": body.params, "actor_id": user.id})
    run.job_id = job.id
    audit.record(db, user.id, "run.queued", "run", run.id, project.id, {"experiment": exp.name, "implementation": impl.version, "runner": body.runner_kind})
    db.commit()
    if body.wait:
        jobs.process_pending()
        db.expire_all()
        run = db.get(Run, run.id)
    return row(run)


class ImportIn(BaseModel):
    experiment_id: str
    implementation_id: str
    document: dict
    illustrative: bool = False
    supersedes_run_id: str | None = None
    correction_note: str = ""


@router.post("/runs/import")
def import_run(body: ImportIn, ctx=Depends(editor)):
    """Import externally produced results (hardware lab, customer lab, onsite). Synchronous; nothing executes."""
    project, db, user = ctx
    exp = get_or_404(db, Experiment, body.experiment_id, project.id)
    impl = get_or_404(db, Implementation, body.implementation_id, project.id)
    if body.supersedes_run_id and not body.correction_note:
        raise HTTPException(400, "a correction must carry a correction_note")
    runner = get_runner("import")
    run = services.create_run_record(db, project.id, exp.id, impl.id, "import", "imported", user.id, body.supersedes_run_id, body.correction_note)
    doc = dict(body.document)
    doc.setdefault("environment", {})
    doc["environment"].setdefault("imported_by", user.email)
    result = runner.run(RunRequest(fixture=exp.fixture, params={"document": doc, "illustrative": body.illustrative},
                                   implementation={}, experiment={}))
    services.persist_result(db, run, result, user.id)
    audit.record(db, user.id, "run.imported", "run", run.id, project.id, {"provenance": run.provenance, "sha256": run.artifact_hashes.get("raw_output")})
    db.commit()
    return row(run)


@router.get("/runs/{run_id}")
def get_run(run_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    run = get_or_404(db, Run, run_id, project.id)
    impl = db.get(Implementation, run.implementation_id)
    exp = db.get(Experiment, run.experiment_id)
    art = db.get(Artifact, run.raw_output_artifact_id) if run.raw_output_artifact_id else None
    corrections = db.scalars(select(Run).where(Run.supersedes_run_id == run.id)).all()
    job = db.get(Job, run.job_id) if run.job_id else None
    raw = None
    if art:
        try:
            raw = json.loads(artstore.read(art))
        except Exception:
            raw = None
    return {**row(run), "implementation": row(impl), "experiment": row(exp), "raw_artifact": row(art),
            "raw_artifact_integrity_ok": artstore.verify(art) if art else None, "raw": raw,
            "superseded_by": rows(corrections), "job": row(job)}


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    art = get_or_404(db, Artifact, artifact_id, project.id)
    return Response(artstore.read(art), media_type=art.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{re.sub(r"[^A-Za-z0-9._-]+", "_", art.filename)}"', "X-SHA256": art.sha256})


@router.get("/artifacts")
def list_artifacts(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Artifact).where(Artifact.project_id == project.id).order_by(Artifact.created_at)).all())


@router.get("/compare")
def compare(baseline_run_id: str, candidate_run_id: str, ctx=Depends(viewer)):
    """Baseline-versus-candidate comparison of two runs. Provenance of each side is stated explicitly."""
    project, db, _ = ctx
    a = get_or_404(db, Run, baseline_run_id, project.id)
    b = get_or_404(db, Run, candidate_run_id, project.id)
    keys = sorted(set(a.metrics) | set(b.metrics))
    rows_ = []
    for k in keys:
        va, vb = a.metrics.get(k), b.metrics.get(k)
        delta = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        rows_.append({"metric": k, "baseline": va, "candidate": vb, "delta": delta,
                      "delta_pct": (delta / va * 100.0) if delta is not None and va else None,
                      "definition": b.metric_definitions.get(k) or a.metric_definitions.get(k) or
                      next((v for kk, v in {**a.metric_definitions, **b.metric_definitions}.items() if kk.rstrip("*") and k.startswith(kk.rstrip("*"))), "")})
    comparable = a.provenance == b.provenance and a.runner_kind == b.runner_kind
    scen = {}
    for s in a.scenarios:
        scen.setdefault(s["id"], {})["baseline"] = s.get("pass")
    for s in b.scenarios:
        scen.setdefault(s["id"], {})["candidate"] = s.get("pass")
    return {"baseline": {**row(a), "implementation": row(db.get(Implementation, a.implementation_id))},
            "candidate": {**row(b), "implementation": row(db.get(Implementation, b.implementation_id))},
            "metrics": rows_, "scenarios": [{"id": k, **v} for k, v in scen.items()],
            "comparable": comparable,
            "comparability_note": ("Both runs share provenance and runner; numeric deltas are meaningful within the stated measurement definitions."
                                   if comparable else f"Runs differ in provenance/runner ({a.provenance}/{a.runner_kind} vs {b.provenance}/{b.runner_kind}); "
                                   "compare requirement outcomes, not raw numbers."),
            "requirements": {"baseline": a.requirement_results, "candidate": b.requirement_results}}


@router.get("/revalidation")
def revalidation_history(ctx=Depends(viewer)):
    """Version-to-version history: for each implementation version, every run with pass/fail and failed requirements."""
    project, db, _ = ctx
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project.id).order_by(Implementation.created_at)).all()
    runs = db.scalars(select(Run).where(Run.project_id == project.id).order_by(Run.sequence)).all()
    exps = {e.id: e.name for e in db.scalars(select(Experiment).where(Experiment.project_id == project.id)).all()}
    out = []
    for i in impls:
        rs = [r for r in runs if r.implementation_id == i.id]
        out.append({"implementation": row(i), "runs": [{"id": r.id, "sequence": r.sequence, "status": r.status, "provenance": r.provenance,
                                                        "runner_kind": r.runner_kind, "overall_pass": r.overall_pass, "experiment": exps.get(r.experiment_id),
                                                        "failed_requirements": [x["name"] for x in r.requirement_results if x.get("pass") is False],
                                                        "failed_scenarios": [s["id"] for s in r.scenarios if s.get("pass") is False],
                                                        "supersedes_run_id": r.supersedes_run_id, "created_at": r.created_at.isoformat(),
                                                        "fixture_version": r.fixture_version, "runner_version": r.runner_version} for r in rs]})
    return out
