from __future__ import annotations
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from ..models import TestDefinition, Run, Implementation, Artifact, Job, EvidenceBundle
from .. import audit, jobs, services
from .. import artifacts as artstore
from runners import list_runners, get_runner, RunRequest
from .common import row, rows, viewer, editor, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["tests", "runs"])
FIXTURES = {"signature_library", "malformed_input_sweep", "toy_factoring", "external"}


class TestIn(BaseModel):
    test_id: str
    version: str = "1"
    name: str
    fixture: str
    definition: dict = {}
    acceptance_criteria: list = []
    resource_limits: dict = {}
    description: str = ""


@router.get("/tests")
def list_tests(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id).order_by(TestDefinition.created_at)).all())


@router.post("/tests")
def create_test(body: TestIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.fixture not in FIXTURES:
        raise HTTPException(400, f"fixture must be one of {sorted(FIXTURES)}")
    if db.scalar(select(TestDefinition).where(TestDefinition.project_id == project.id, TestDefinition.test_id == body.test_id, TestDefinition.version == body.version)):
        raise HTTPException(409, "that test_id/version already exists; test definitions are versioned, create a new version")
    t = TestDefinition(project_id=project.id, **body.model_dump())
    db.add(t)
    db.flush()
    audit.record(db, user.id, "test.created", "test_definition", t.id, project.id, {"test_id": t.test_id, "version": t.version}, commit=True)
    return row(t)


@router.get("/tests/{test_id}/preflight")
def preflight(test_id: str, implementation_id: str, execution_mode: str = "platform_sandbox", ctx=Depends(viewer)):
    project, db, _ = ctx
    t = get_or_404(db, TestDefinition, test_id, project.id)
    i = get_or_404(db, Implementation, implementation_id, project.id)
    return services.preflight(db, t, i, execution_mode)


# ---------------------------------------------------------------- runs
class RunIn(BaseModel):
    test_definition_id: str
    implementation_id: str
    runner_kind: str = "platform_sandbox"
    params: dict = {}
    supersedes_run_id: str | None = None
    correction_note: str = ""
    wait: bool = False


@router.get("/runs")
def list_runs(ctx=Depends(viewer)):
    project, db, _ = ctx
    runs = db.scalars(select(Run).where(Run.project_id == project.id).order_by(Run.sequence)).all()
    impls = {i.id: i for i in db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()}
    tests = {t.id: t for t in db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id)).all()}
    return [{**row(r), "implementation_label": f"{impls[r.implementation_id].name} {impls[r.implementation_id].version}" if r.implementation_id in impls else "?",
             "test_label": f"{tests[r.test_definition_id].test_id}@{tests[r.test_definition_id].version}" if r.test_definition_id in tests else "?",
             "test_name": tests[r.test_definition_id].name if r.test_definition_id in tests else "?"} for r in runs]


@router.post("/runs")
def create_run(body: RunIn, ctx=Depends(editor)):
    """Queue a platform-sandbox run. Append-only; a correction references the superseded run and needs a note."""
    project, db, user = ctx
    t = get_or_404(db, TestDefinition, body.test_definition_id, project.id)
    i = get_or_404(db, Implementation, body.implementation_id, project.id)
    if t.fixture == "external":
        raise HTTPException(400, "this test definition is import-only")
    if body.runner_kind not in ("platform_sandbox", "docker_sandbox"):
        raise HTTPException(400, "runner_kind must be platform_sandbox or docker_sandbox")
    runner = get_runner(body.runner_kind)
    ok, why = runner.available()
    if not ok:
        raise HTTPException(409, f"runner '{body.runner_kind}' unavailable: {why}")
    pf = services.preflight(db, t, i, "platform_sandbox")
    if not pf["can_execute"]:
        raise HTTPException(409, "cannot execute: " + "; ".join(pf["problems"]) + ". Use the results-import or customer-runner path.")
    if body.supersedes_run_id:
        get_or_404(db, Run, body.supersedes_run_id, project.id)
        if not body.correction_note:
            raise HTTPException(400, "a correction must carry a correction_note")
    run = services.create_run_record(db, project.id, t.id, i.id, "platform_sandbox", body.runner_kind, "measured", user.id, body.supersedes_run_id, body.correction_note)
    job = jobs.enqueue(db, "run_test", {"run_id": run.id, "runner_kind": body.runner_kind, "params": body.params, "actor_id": user.id})
    run.job_id = job.id
    audit.record(db, user.id, "run.queued", "run", run.id, project.id, {"test": t.test_id, "implementation": i.version, "preflight": {k: pf[k] for k in ("execution_mode", "resource_limits", "result_provenance")}})
    db.commit()
    if body.wait:
        jobs.process_pending()
        db.expire_all()
        run = db.get(Run, run.id)
    return row(run)


def _import_results_doc(db, project, impl: Implementation, document: dict, user, test: TestDefinition | None = None, illustrative=False):
    """Unsigned existing-results import (execution_mode imported_results)."""
    if test is None:
        tid = document.get("test_id") or "signature-library-core"
        test = next((t for t in db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id)).all() if t.test_id == tid), None)
        if not test:
            test = TestDefinition(project_id=project.id, test_id="external-results", version="1", name="Imported results (external)", fixture="external",
                                  definition={}, acceptance_criteria=["schema validated only"], description="Results imported from outside the platform.")
            db.add(test)
            db.flush()
    runner = get_runner("imported_results")
    run = services.create_run_record(db, project.id, test.id, impl.id, "imported_results", "imported_results", "imported", user.id)
    run.received_at = __import__("app.models", fromlist=["utcnow"]).utcnow()
    doc = dict(document)
    doc.setdefault("environment", {})["imported_by"] = user.email
    res = runner.run(RunRequest(fixture=test.fixture, params={"document": doc, "illustrative": illustrative}, implementation={}, experiment={}))
    services.persist_result(db, run, res, user.id, sign_platform=False)
    services.add_label(run, "imported", f"unsigned result document imported by {user.email}", user.email)
    audit.record(db, user.id, "run.imported_results", "run", run.id, project.id, {"provenance": run.provenance, "sha256": run.artifact_hashes.get("raw_output")})
    return run


class ResultsImportIn(BaseModel):
    implementation_id: str
    test_definition_id: str | None = None
    document: dict
    illustrative: bool = False


@router.post("/runs/import-results")
def import_results(body: ResultsImportIn, ctx=Depends(editor)):
    """Import an existing, unsigned result document. Labelled imported; never signature-verified or replayed."""
    project, db, user = ctx
    i = get_or_404(db, Implementation, body.implementation_id, project.id)
    t = get_or_404(db, TestDefinition, body.test_definition_id, project.id) if body.test_definition_id else None
    run = _import_results_doc(db, project, i, body.document, user, t, body.illustrative)
    db.commit()
    return row(run)


class BundleImportIn(BaseModel):
    bundle: dict
    test_definition_id: str | None = None


@router.post("/runs/import-bundle")
def import_bundle(body: BundleImportIn, ctx=Depends(editor)):
    """Import a signed customer-runner bundle. Signature, expected signer, digests, schema and binding are verified before acceptance."""
    project, db, user = ctx
    t = get_or_404(db, TestDefinition, body.test_definition_id, project.id) if body.test_definition_id else None
    try:
        run, bundle, info = services.import_bundle(db, project, body.bundle, user.id, user.email, t)
    except ValueError as e:
        audit.record(db, user.id, "bundle.rejected", "project", project.id, project.id, {"reason": str(e)[:300]}, commit=True)
        raise HTTPException(422, str(e))
    db.commit()
    return {**row(run), "bundle_id": bundle.id, "import_info": info}


@router.get("/runs/{run_id}")
def get_run(run_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    r = get_or_404(db, Run, run_id, project.id)
    art = db.get(Artifact, r.raw_output_artifact_id) if r.raw_output_artifact_id else None
    raw = None
    if art:
        try:
            raw = json.loads(artstore.read(art))
        except Exception:
            raw = None
    bundle = db.get(EvidenceBundle, r.bundle_id) if r.bundle_id else None
    return {**row(r), "implementation": row(db.get(Implementation, r.implementation_id)), "test": row(db.get(TestDefinition, r.test_definition_id)),
            "raw_artifact": row(art), "raw_artifact_integrity_ok": artstore.verify(art) if art else None, "raw": raw,
            "superseded_by": rows(db.scalars(select(Run).where(Run.supersedes_run_id == r.id)).all()), "job": row(db.get(Job, r.job_id)) if r.job_id else None,
            "bundle": ({**row(bundle), "bundle_artifact": row(db.get(Artifact, bundle.bundle_artifact_id)) if bundle.bundle_artifact_id else None} if bundle else None),
            "duplicate_of": row(db.get(Run, r.duplicate_of_run_id)) if r.duplicate_of_run_id else None}


@router.post("/runs/{run_id}/replay")
def replay_run(run_id: str, wait: bool = False, ctx=Depends(editor)):
    """Platform re-executes an imported run's test against the same implementation; a matching outcome earns `independently_replayed`."""
    project, db, user = ctx
    r = get_or_404(db, Run, run_id, project.id)
    if r.execution_mode == "platform_sandbox":
        raise HTTPException(400, "platform runs are not replayed through this path; queue a new run instead")
    t, i = db.get(TestDefinition, r.test_definition_id), db.get(Implementation, r.implementation_id)
    pf = services.preflight(db, t, i, "platform_sandbox")
    if not pf["can_execute"]:
        raise HTTPException(409, "cannot replay: " + "; ".join(pf["problems"]))
    job = jobs.enqueue(db, "replay_run", {"target_run_id": r.id, "actor_id": user.id})
    db.commit()
    if wait:
        jobs.process_pending()
        db.expire_all()
        r = db.get(Run, r.id)
    return {"job_id": job.id, "target": row(r)}


@router.get("/compare")
def compare(baseline_run_id: str, candidate_run_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    a = get_or_404(db, Run, baseline_run_id, project.id)
    b = get_or_404(db, Run, candidate_run_id, project.id)
    return {"baseline": {**row(a), "implementation": row(db.get(Implementation, a.implementation_id))},
            "candidate": {**row(b), "implementation": row(db.get(Implementation, b.implementation_id))}, **services.compare_runs(db, a, b)}


@router.get("/artifacts")
def list_artifacts(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(Artifact).where(Artifact.project_id == project.id).order_by(Artifact.created_at)).all())


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    art = get_or_404(db, Artifact, artifact_id, project.id)
    return Response(artstore.read(art), media_type=art.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{re.sub(r"[^A-Za-z0-9._-]+", "_", art.filename)}"', "X-SHA256": art.sha256})
