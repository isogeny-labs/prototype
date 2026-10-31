"""Domain services: run persistence (append-only), finding lifecycle, job handlers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select, func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runners.all  # noqa: E402,F401
from runners import get_runner, RunRequest, RunResult, list_runners  # noqa: E402

from . import artifacts as artstore  # noqa: E402
from . import audit, evaluate, jobs  # noqa: E402
from .config import RUNNER_TIMEOUT_SECONDS, RUNNER_MEMORY_LIMIT_MB, RUNNER_CPU_SECONDS  # noqa: E402
from .models import (Run, Experiment, Implementation, Requirement, Finding, ResearchSource, Project, utcnow,  # noqa: E402
                     SandboxExperiment, AttackAssessment)
from .research import review_source  # noqa: E402


def _snapshot(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if not c.name.endswith("_at")}


def next_sequence(db, project_id: str) -> int:
    return (db.scalar(select(func.max(Run.sequence)).where(Run.project_id == project_id)) or 0) + 1


def create_run_record(db, project_id, experiment_id, implementation_id, runner_kind, provenance, actor_id,
                      supersedes_run_id=None, correction_note="") -> Run:
    run = Run(project_id=project_id, experiment_id=experiment_id, implementation_id=implementation_id,
              sequence=next_sequence(db, project_id), status="queued", provenance=provenance, runner_kind=runner_kind,
              supersedes_run_id=supersedes_run_id, correction_note=correction_note, created_by=actor_id)
    db.add(run)
    db.flush()
    return run


def persist_result(db, run: Run, result: RunResult, actor_id=None):
    """Fill an append-only run record from a RunResult, evaluate requirements, and open findings on failure."""
    project_id = run.project_id
    run.status = result.status
    run.provenance = result.provenance
    run.runner_kind = result.runner_kind
    run.runner_version = result.runner_version
    run.fixture_version = result.fixture_version
    run.environment = result.environment
    run.commands = result.commands
    run.repeat_count = result.repeat_count
    run.metrics = result.metrics
    run.metric_definitions = result.metric_definitions
    run.scenarios = result.scenarios
    run.failures = result.failures
    run.exclusions = result.exclusions
    run.limitations = result.limitations
    run.completed_at = utcnow()
    if result.raw_output:
        art = artstore.store(db, project_id, "raw_output", f"run_{run.sequence}_raw.json", result.raw_output,
                             "application/json", label=f"raw output of run #{run.sequence}")
        run.raw_output_artifact_id = art.id
        run.artifact_hashes = {"raw_output": art.sha256}
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()
    run.requirement_results = evaluate.evaluate(reqs, run.metrics, run.provenance)
    run.overall_pass = evaluate.overall(run.scenarios, run.requirement_results, run.status)
    db.flush()
    _open_measurement_findings(db, run, actor_id)
    audit.record(db, actor_id, "run.completed", "run", run.id, project_id,
                 {"status": run.status, "overall_pass": run.overall_pass, "provenance": run.provenance})
    return run


def _open_measurement_findings(db, run: Run, actor_id):
    """A failed applicable requirement (or failed scenario) opens a measurement finding unless one is already open."""
    impl = db.get(Implementation, run.implementation_id)
    exp = db.get(Experiment, run.experiment_id)
    problems = []
    for r in evaluate.failed_requirements(run.requirement_results):
        problems.append((r["requirement_id"], f"Requirement failed: {r['name']}",
                         f"Run #{run.sequence} ({run.provenance}) of '{impl.name} {impl.version}' measured {r['metric']} = "
                         f"{r['observed']} {r['unit']}, violating {r['metric']} {r['operator']} {r['threshold']} {r['unit']}.",
                         {"metric": r["metric"], "purpose": None, "threshold": r["threshold"], "observed": r["observed"]}))
    failed_scen = [s for s in run.scenarios if s.get("pass") is False]
    if failed_scen:
        problems.append((None, f"Functional scenario failure in {exp.name}",
                         f"Run #{run.sequence} of '{impl.name} {impl.version}' failed scenarios: " +
                         ", ".join(s["id"] for s in failed_scen), {"scenarios": [s["id"] for s in failed_scen]}))
    for req_id, title, summary, affected in problems:
        # keep one open finding per (requirement, implementation)
        existing = next((f for f in db.scalars(select(Finding).where(
            Finding.project_id == run.project_id, Finding.origin == "measurement", Finding.title == title,
            Finding.status.notin_(["closed", "not_relevant"]))).all() if impl.id in (f.affected_implementation_ids or [])), None)
        if existing:
            if run.id not in existing.evidence_run_ids:
                existing.evidence_run_ids = existing.evidence_run_ids + [run.id]
            continue
        f = Finding(project_id=run.project_id, origin="measurement", title=title, summary=summary,
                    claims=[{"text": summary, "quote": "", "reproduced": "internal_measurement"}],
                    affected={**affected, "purpose": _purpose_of(impl), "implementation": f"{impl.name} {impl.version}"},
                    affected_implementation_ids=[impl.id], relevance="Directly measured against this project's own requirements.",
                    uncertainty=("Imported/illustrative evidence: depends on the external measurement's validity." if run.provenance != "measured"
                                 else "Host-side fixture measurement; device figures may differ."),
                    proposed_followup={"type": "implementation_review", "description": "Generate a remediation proposal and retest."},
                    status="triage", status_history=[{"status": "triage", "by": "platform", "note": f"opened by run #{run.sequence}"}],
                    evidence_run_ids=[run.id], requirement_id=req_id, is_demo=run.provenance == "illustrative",
                    extraction_method="measurement")
        db.add(f)
        db.flush()
        audit.record(db, actor_id, "finding.opened", "finding", f.id, run.project_id, {"run_id": run.id})


def _purpose_of(impl: Implementation) -> str | None:
    from . import catalog
    p = catalog.profile(impl.profile_id) if impl.profile_id else None
    return (p or {}).get("purpose") or (impl.configuration or {}).get("purpose")


def set_finding_status(db, finding: Finding, status: str, actor_id, note: str = ""):
    finding.status = status
    finding.status_history = finding.status_history + [{"status": status, "by": actor_id or "system", "note": note,
                                                        "at": utcnow().isoformat()}]
    audit.record(db, actor_id, "finding.status", "finding", finding.id, finding.project_id, {"status": status, "note": note})


def build_run_request(db, experiment: Experiment, impl: Implementation, extra_params: dict | None = None) -> RunRequest:
    from . import catalog
    params = dict(experiment.definition.get("params", {}))
    prof = catalog.profile(impl.profile_id) if impl.profile_id else None
    if prof:
        params.update(prof.get("fixture_params", {}))
    params.update(impl.configuration.get("fixture_params", {}))
    params.update(extra_params or {})
    return RunRequest(fixture=experiment.fixture, params=params, implementation=_snapshot(impl),
                      experiment=_snapshot(experiment),
                      limits={"timeout_s": RUNNER_TIMEOUT_SECONDS, "memory_mb": RUNNER_MEMORY_LIMIT_MB, "cpu_s": RUNNER_CPU_SECONDS})


# ------------------------------------------------------------------ job handlers
@jobs.handler("run_fixture")
def _job_run_fixture(db, payload: dict):
    run = db.get(Run, payload["run_id"])
    run.status = "running"
    db.commit()
    exp = db.get(Experiment, run.experiment_id)
    impl = db.get(Implementation, run.implementation_id)
    runner = get_runner(payload.get("runner_kind", "local_fixture"))
    req = build_run_request(db, exp, impl, payload.get("params"))
    result = runner.run(req)
    persist_result(db, run, result, payload.get("actor_id"))
    db.commit()
    return {"run_id": run.id, "status": run.status, "overall_pass": run.overall_pass}


@jobs.handler("research_review")
def _job_research_review(db, payload: dict):
    src = db.get(ResearchSource, payload["source_id"])
    finding = review_source(db, src)
    audit.record(db, payload.get("actor_id"), "finding.created", "finding", finding.id, src.project_id,
                 {"source_id": src.id, "method": finding.extraction_method})
    db.commit()
    return {"finding_id": finding.id, "method": finding.extraction_method}


@jobs.handler("sandbox_execute")
def _job_sandbox_execute(db, payload: dict):
    sx = db.get(SandboxExperiment, payload["sandbox_id"])
    run = db.get(Run, payload["run_id"])
    run.status = "running"
    db.commit()
    runner = get_runner("local_fixture")
    exp = db.get(Experiment, run.experiment_id)
    impl = db.get(Implementation, run.implementation_id)
    req = RunRequest(fixture=sx.allowlisted_fixture, params=sx.parameters, implementation=_snapshot(impl),
                     experiment=_snapshot(exp), limits={**{"timeout_s": 120, "memory_mb": 512, "cpu_s": 90}, **(sx.resource_limits or {})})
    result = runner.run(req)
    persist_result(db, run, result, payload.get("actor_id"))
    sx.status = "executed"
    sx.run_id = run.id
    # Category A assessment: directly measured toy experiment.
    if result.status == "completed" and sx.allowlisted_fixture == "toy_factoring":
        m = result.metrics
        a = AttackAssessment(
            project_id=sx.project_id, category="A", attack_model="classical",
            target=f"Synthetic {m.get('modulus_bits')}-bit RSA-style semiprime (toy, generated in-fixture)",
            target_parameters={"modulus_bits": m.get("modulus_bits"), "trials": m.get("trials")},
            objective="Recover a prime factor of a toy modulus (demonstrates workflow only).",
            attacker_capabilities="Single CPU core, pure Python, no precomputation.",
            method="Pollard's rho (Brent cycle finding), executed by the isolated local runner.",
            source="Pollard (1975); Brent (1980). Executed here, not merely cited.",
            hardware_assumptions=json.dumps(result.environment),
            measured_throughput={"value": m.get("iterations_per_second"), "unit": "iterations/s", "run_id": run.id},
            expected_work={"value": m.get("iterations_mean"), "unit": "iterations (mean observed)",
                           "log2": (m.get("iterations_mean") or 1) and __import__("math").log2(max(1, m.get("iterations_mean") or 1)),
                           "estimation_method": "directly observed; heuristic expectation sqrt(pi*p/2) = %.0f" % (m.get("expected_iterations_heuristic") or 0)},
            probability_model=result.extra.get("probability_model", ""),
            parallelization="Not parallelised.", overhead_assumptions="None; wall-clock measured in-process.",
            uncertainty=f"{m.get('trials')} trials; variance between trials is large (birthday-paradox process).",
            applicability_limits="Toy parameters only. Says nothing about RSA-2048 or any deployed key. Do not extrapolate.",
            run_id=run.id, is_demo=False)
        db.add(a)
        db.flush()
        sx.assessment_id = a.id
    db.commit()
    return {"run_id": run.id, "status": run.status}
