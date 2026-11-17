"""Domain services: run persistence (append-only), classification, evidence bundles, bundle import, replay,
findings lifecycle, retest evaluation and job handlers."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
import runners.all  # noqa: E402,F401
from runners import get_runner, RunRequest, RunResult, list_runners  # noqa: E402
from iel_tools import attest  # noqa: E402

from . import artifacts as artstore  # noqa: E402
from . import audit, evaluate, jobs, compat, signing  # noqa: E402
from .config import RUNNER_TIMEOUT_SECONDS, RUNNER_MEMORY_LIMIT_MB, RUNNER_CPU_SECONDS  # noqa: E402
from .models import (Run, TestDefinition, Implementation, Requirement, Finding, ResearchSource, Project, utcnow, EvidenceBundle,  # noqa: E402
                     ExperimentProposal, ProtocolVersion, AttackAssessment, Artifact)
from .research import review_source, summarize_experiment  # noqa: E402

CLASSIFICATIONS = ("not_tested", "passed_defined_checks", "failed", "inconclusive", "unsupported", "awaiting_review")
LABELS = ("imported", "hash_checked", "signature_verified", "cairn_verified", "independently_replayed")


def _snapshot(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if not c.name.endswith("_at")}


def next_sequence(db, project_id: str) -> int:
    return (db.scalar(select(func.max(Run.sequence)).where(Run.project_id == project_id)) or 0) + 1


def classify(run: Run) -> str:
    if run.status in ("queued", "running"):
        return "not_tested"
    if run.status == "failed":
        if any("not allowlisted" in f or "adapter could not be loaded" in f or "unsupported" in f.lower() for f in run.failures):
            return "unsupported"
        return "inconclusive"
    if any(s.get("pass") is False for s in run.scenarios) or any(r.get("pass") is False for r in run.requirement_results):
        return "failed"
    if not run.scenarios and not run.metrics:
        return "inconclusive"
    return "passed_defined_checks"


def add_label(run: Run, label: str, claim: str, by: str, ref: str | None = None):
    assert label in LABELS
    run.evidence_labels = run.evidence_labels + [{"label": label, "claim": claim, "by": by, "at": utcnow().isoformat(), "ref": ref}]


def create_run_record(db, project_id, test_definition_id, implementation_id, execution_mode, runner_kind, provenance, actor_id,
                      supersedes_run_id=None, correction_note="", proposal_id=None, protocol_version=None) -> Run:
    run = Run(project_id=project_id, test_definition_id=test_definition_id, implementation_id=implementation_id,
              sequence=next_sequence(db, project_id), status="queued", execution_mode=execution_mode, provenance=provenance,
              runner_kind=runner_kind, supersedes_run_id=supersedes_run_id, correction_note=correction_note, created_by=actor_id,
              experiment_proposal_id=proposal_id, protocol_version=protocol_version)
    db.add(run)
    db.flush()
    return run


def adapter_spec(db, impl: Implementation) -> tuple[dict, list[str]]:
    """Return (params fragment, problems). Loads the snapshot bytes for the sandbox; never executes anything here."""
    if impl.adapter_kind == "profile" and impl.profile_id:
        return {"adapter": {"kind": "profile", "profile": impl.profile_id}}, []
    if impl.adapter_kind == "module" and impl.source_snapshot_artifact_id:
        if (impl.compatibility or {}).get("status") != "compatible":
            return {}, ["implementation is not marked compatible; use the results-import path"]
        art = db.get(Artifact, impl.source_snapshot_artifact_id)
        files = compat.extract_snapshot(artstore.read(art), art.filename)
        return {"source_snapshot": {"files": files, "entry": "adapter.py"}}, []
    return {}, ["implementation has no executable adapter (results-only); import results instead"]


def preflight(db, test: TestDefinition, impl: Implementation, execution_mode: str) -> dict:
    """What the UI shows before execution."""
    from runners.suite_tools import TOOLS as SUITE_TOOLS
    if test.fixture in SUITE_TOOLS:
        runner = get_runner(SUITE_TOOLS[test.fixture].runner)
        ok, why = runner.available()
        spec, problems = {"adapter": "none (suite tool: typed public parameters only)"}, ([] if ok else [f"runner {runner.kind} unavailable: {why}"])
    else:
        spec, problems = adapter_spec(db, impl)
        runner = get_runner("platform_sandbox")
    limits = {"timeout_s": RUNNER_TIMEOUT_SECONDS, "memory_mb": RUNNER_MEMORY_LIMIT_MB, "cpu_s": RUNNER_CPU_SECONDS, **(test.resource_limits or {})}
    return {"implementation": {"id": impl.id, "name": impl.name, "version": impl.version, "source_digest": impl.source_digest, "adapter_kind": impl.adapter_kind,
                               "compatibility": impl.compatibility},
            "test": {"id": test.id, "test_id": test.test_id, "version": test.version, "fixture": test.fixture, "definition": test.definition,
                     "acceptance_criteria": test.acceptance_criteria, "definition_sha256": attest.sha256_hex(attest.canonical(test.definition))},
            "runner": {"kind": runner.kind, "version": runner.version, "isolation": runner.describe()["description"]},
            "inputs": {k: v for k, v in (test.definition.get("params") or {}).items()} | ({"adapter": spec["adapter"]} if "adapter" in spec else {"adapter": "customer source snapshot (module)"}),
            "resource_limits": limits, "execution_mode": execution_mode,
            "result_provenance": "measured" if execution_mode in ("platform_sandbox", "customer_runner") else "imported",
            "networking": "disabled", "can_execute": not problems, "problems": problems,
            "requirements": [{"name": r.name, "metric": r.metric, "operator": r.operator, "threshold": r.threshold, "applies_to": r.applies_to}
                             for r in db.scalars(select(Requirement).where(Requirement.project_id == impl.project_id))]}


def build_run_request(db, test: TestDefinition, impl: Implementation, extra_params=None, fixture=None, params=None, limits=None) -> RunRequest:
    from runners.suite_tools import TOOLS as SUITE_TOOLS
    p = dict((test.definition or {}).get("params", {}))
    if (fixture or test.fixture) in SUITE_TOOLS:
        # Suite tools analyse public material passed as typed parameters; they never load the customer adapter and take
        # only the parameters the test definition / call recorded, so no profile or snapshot value can change the argv.
        p.update(params or {})
        p.update(extra_params or {})
    else:
        spec, problems = adapter_spec(db, impl)
        if problems:
            raise RuntimeError("unsupported: " + "; ".join(problems))
        p.update(spec)
        p.update(params or {})
        p.update(extra_params or {})
    lim = {"timeout_s": RUNNER_TIMEOUT_SECONDS, "memory_mb": RUNNER_MEMORY_LIMIT_MB, "cpu_s": RUNNER_CPU_SECONDS, **(test.resource_limits or {}), **(limits or {})}
    return RunRequest(fixture=fixture or test.fixture, params=p, implementation=_snapshot(impl), experiment=_snapshot(test), limits=lim)


# ---------------------------------------------------------------- persistence
def persist_result(db, run: Run, result: RunResult, actor_id=None, sign_platform=True):
    project_id = run.project_id
    run.status, run.provenance, run.runner_kind, run.runner_version = result.status, result.provenance, result.runner_kind, result.runner_version
    run.fixture_version, run.environment, run.commands = result.fixture_version, result.environment, result.commands
    run.repeat_count, run.metrics, run.metric_definitions = result.repeat_count, result.metrics, result.metric_definitions
    run.scenarios, run.failures, run.exclusions, run.limitations = result.scenarios, result.failures, result.exclusions, result.limitations
    inputs = dict(run.inputs or {})  # keep what was recorded at creation (tool, typed params, control note)
    inputs.update(result.extra.get("parameters", {}))
    if "adapter" in result.extra:
        inputs["adapter"] = result.extra["adapter"]
    run.inputs = inputs
    run.resource_limits = (result.commands[0].get("limits") if result.commands else {}) or run.resource_limits
    run.completed_at = utcnow()
    if result.raw_output:
        art = artstore.store(db, project_id, "raw_output", f"run_{run.sequence}_raw_output.json", result.raw_output, "application/json",
                             label=f"raw output of run #{run.sequence}")
        run.raw_output_artifact_id = art.id
        run.artifact_hashes = {**run.artifact_hashes, "raw_output": art.sha256}
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()
    # operational requirements apply to the core test, not to research experiments
    test_fixture = db.get(TestDefinition, run.test_definition_id).fixture
    run.requirement_results = ([] if (run.experiment_proposal_id or test_fixture not in ("signature_library", "external"))
                               else evaluate.evaluate(reqs, run.metrics, run.provenance))
    run.overall_pass = evaluate.overall(run.scenarios, run.requirement_results, run.status)
    run.classification = classify(run)
    db.flush()
    if sign_platform and run.execution_mode == "platform_sandbox":
        create_platform_bundle(db, run)
    _open_findings(db, run, actor_id)
    audit.record(db, actor_id, "run.completed", "run", run.id, project_id,
                 {"classification": run.classification, "execution_mode": run.execution_mode, "provenance": run.provenance})
    return run


def _test_subject(test: TestDefinition) -> dict:
    return {"name": f"test-definition:{test.test_id}@{test.version}", "digest": {"sha256": attest.sha256_hex(attest.canonical(test.definition))}}


def run_predicate(db, run: Run) -> dict:
    impl, test = db.get(Implementation, run.implementation_id), db.get(TestDefinition, run.test_definition_id)
    return {"project_id": run.project_id, "run_id": run.id, "sequence": run.sequence, "execution_mode": run.execution_mode,
            "implementation": {"id": impl.id, "name": impl.name, "version": impl.version, "source_digest": impl.source_digest, "source_revision": impl.source_revision},
            "test": {"test_id": test.test_id, "version": test.version, "fixture": test.fixture, "fixture_version": run.fixture_version},
            "runner": {"kind": run.runner_kind, "version": run.runner_version}, "environment": run.environment, "commands": run.commands,
            "inputs": run.inputs, "resource_limits": run.resource_limits,
            "results": {"classification": run.classification, "status": run.status, "metrics": run.metrics, "scenarios": run.scenarios,
                        "requirement_results": run.requirement_results, "failures": run.failures, "exclusions": run.exclusions,
                        "limitations": run.limitations},
            "executed_at": run.completed_at.isoformat() if run.completed_at else None, "protocol_version": run.protocol_version,
            "experiment_proposal_id": run.experiment_proposal_id}


def create_platform_bundle(db, run: Run) -> EvidenceBundle:
    impl, test = db.get(Implementation, run.implementation_id), db.get(TestDefinition, run.test_definition_id)
    artifacts = {}
    subjects = [_test_subject(test)]
    if run.raw_output_artifact_id:
        a = db.get(Artifact, run.raw_output_artifact_id)
        artifacts["raw_output.json"] = artstore.read(a)
        subjects.append({"name": "raw_output.json", "digest": {"sha256": a.sha256}})
    if impl.source_snapshot_artifact_id:
        sa = db.get(Artifact, impl.source_snapshot_artifact_id)
        subjects.append({"name": f"source-snapshot:{sa.filename}", "digest": {"sha256": sa.sha256}})
    stmt = attest.build_statement(subjects, attest.PREDICATE_RUN, run_predicate(db, run))
    env = attest.sign_statement(stmt, signing.platform_private_key())
    bundle_doc = attest.make_bundle(env, artifacts)
    data = json.dumps(bundle_doc, indent=1, sort_keys=True).encode()
    bart = artstore.store(db, run.project_id, "bundle", f"run_{run.sequence}_evidence_bundle.json", data, "application/json", label=f"signed evidence bundle of run #{run.sequence}")
    b = EvidenceBundle(project_id=run.project_id, run_id=run.id, kind="platform", envelope=env, statement=stmt,
                       envelope_sha256=attest.sha256_hex(attest.canonical(env)), signer_keyid=signing.platform_key_id(), signer_name="platform signing key",
                       verification={"signature_verified": True, "signer_trusted": True, "digests_ok": True, "binding_ok": True, "problems": [],
                                     "note": "Signed by the platform at creation; re-verify with iel_tools/verify.py and the platform public key."},
                       artifact_ids=[run.raw_output_artifact_id] if run.raw_output_artifact_id else [], bundle_artifact_id=bart.id)
    db.add(b)
    db.flush()
    run.bundle_id = b.id
    run.artifact_hashes = {**run.artifact_hashes, "bundle": bart.sha256}
    return b


# ---------------------------------------------------------------- findings
DERIVED_METRICS = {"functional_pass", "rejection_scenarios_all_pass", "scenario_pass_count", "rejection_scenarios_failed"}


def _open_findings(db, run: Run, actor_id):
    if run.duplicate_of_run_id or run.experiment_proposal_id:
        return  # duplicates never count; experiment runs attach to their proposal's finding instead
    impl, test = db.get(Implementation, run.implementation_id), db.get(TestDefinition, run.test_definition_id)
    failing = [s["id"] for s in run.scenarios if s.get("pass") is False]
    if failing and run.status == "completed":
        title = f"{test.name}: {len(failing)} scenario(s) failed in {impl.name} {impl.version}"
        existing = next((f for f in db.scalars(select(Finding).where(Finding.project_id == run.project_id, Finding.kind == "implementation_defect",
                                                                     Finding.status.notin_(["resolved_within_tested_scope", "not_relevant"]))).all()
                         if impl.id in (f.affected_implementation_ids or []) and (f.affected or {}).get("test_id") == test.test_id), None)
        if existing:
            if run.id not in existing.evidence_run_ids:
                existing.evidence_run_ids = existing.evidence_run_ids + [run.id]
            existing.failing_scenarios = sorted(set(existing.failing_scenarios) | set(failing))
        else:
            names = {s["id"]: s.get("name", s["id"]) for s in run.scenarios}
            f = Finding(project_id=run.project_id, kind="implementation_defect", origin="test_run", reproduction_status="reproduced", title=title,
                        summary=(f"Run #{run.sequence} ({run.execution_mode}, {run.provenance}) of {impl.name} {impl.version} failed: " +
                                 "; ".join(f"{s} ({names.get(s)})" for s in failing) + "."),
                        claims=[{"text": f"{names.get(s)}: expected {next(x['expected'] for x in run.scenarios if x['id'] == s)}, observed "
                                         f"{next(x['observed'] for x in run.scenarios if x['id'] == s)}", "quote": "", "reproduced": "internal_measurement"} for s in failing],
                        affected={"test_id": test.test_id, "test_version": test.version, "scenarios": failing, "implementation": f"{impl.name} {impl.version}",
                                  "algorithm": impl.algorithm, "library": impl.library},
                        affected_implementation_ids=[impl.id], failing_scenarios=failing,
                        relevance="Measured directly against this project's implementation.",
                        uncertainty=("Imported evidence: depends on the external execution's validity." if run.provenance != "measured" else
                                     "Reproduced in the platform sandbox; scope limited to the fixture's scenarios."),
                        status="open", status_history=[{"status": "open", "by": "platform", "note": f"opened by run #{run.sequence}", "at": utcnow().isoformat()}],
                        evidence_run_ids=[run.id], is_demo=bool(impl.seeded_defect) or run.provenance == "illustrative", extraction_method="measurement")
            db.add(f)
            db.flush()
            audit.record(db, actor_id, "finding.opened", "finding", f.id, run.project_id, {"run_id": run.id, "scenarios": failing})
    for r in evaluate.failed_requirements(run.requirement_results):
        if r["metric"] in DERIVED_METRICS:
            continue  # derived from scenarios; the implementation_defect finding already covers them
        title = f"Requirement failed: {r['name']} ({impl.name} {impl.version})"
        existing = next((f for f in db.scalars(select(Finding).where(Finding.project_id == run.project_id, Finding.kind == "requirement_failure", Finding.title == title,
                                                                     Finding.status.notin_(["resolved_within_tested_scope", "not_relevant"]))).all()), None)
        if existing:
            if run.id not in existing.evidence_run_ids:
                existing.evidence_run_ids = existing.evidence_run_ids + [run.id]
            continue
        f = Finding(project_id=run.project_id, kind="requirement_failure", origin="test_run", reproduction_status="reproduced", title=title,
                    summary=f"Run #{run.sequence} ({run.execution_mode}) measured {r['metric']} = {r['observed']} {r['unit']}, violating {r['metric']} {r['operator']} {r['threshold']} {r['unit']}.",
                    claims=[{"text": title, "quote": "", "reproduced": "internal_measurement"}], affected={"metric": r["metric"], "implementation": f"{impl.name} {impl.version}"},
                    affected_implementation_ids=[impl.id], failing_requirements=[r["name"]], relevance="Customer-defined limit.",
                    uncertainty="Host-side or imported measurement; see the run's limitations.", status="open",
                    status_history=[{"status": "open", "by": "platform", "note": f"opened by run #{run.sequence}", "at": utcnow().isoformat()}],
                    evidence_run_ids=[run.id], requirement_id=r["requirement_id"], is_demo=run.provenance == "illustrative", extraction_method="measurement")
        db.add(f)
        db.flush()
        audit.record(db, actor_id, "finding.opened", "finding", f.id, run.project_id, {"run_id": run.id, "requirement": r["name"]})


def set_finding_status(db, f: Finding, status: str, actor_id, note: str = ""):
    f.status = status
    f.status_history = f.status_history + [{"status": status, "by": actor_id or "system", "note": note, "at": utcnow().isoformat()}]
    audit.record(db, actor_id, "finding.status", "finding", f.id, f.project_id, {"status": status, "note": note})


def evaluate_retest(db, f: Finding, run: Run) -> dict:
    """Decide the finding outcome from a retest run of the revised implementation. Never resolves on an invalid run."""
    run_test = db.get(TestDefinition, run.test_definition_id)
    orig = [db.get(Run, rid) for rid in f.evidence_run_ids]
    orig = [r for r in orig if r and r.status == "completed" and r.implementation_id in (f.affected_implementation_ids or []) and not r.duplicate_of_run_id]
    same = [r for r in orig if db.get(TestDefinition, r.test_definition_id).test_id == run_test.test_id]
    base = max(same or orig, key=lambda r: r.sequence, default=None)
    out = {"run_id": run.id, "revised_implementation_ok": run.implementation_id == f.revised_implementation_id, "comparison_limits": []}
    if run.implementation_id != f.revised_implementation_id:
        out["outcome"], out["reason"] = None, "run is not on the revised implementation linked to this finding"
        return out
    if run.duplicate_of_run_id or run.stale_reason:
        out["outcome"], out["reason"] = "inconclusive", "run is flagged duplicate/stale and cannot count as a retest"
        return out
    if run.status != "completed" or run.classification in ("inconclusive", "unsupported", "awaiting_review"):
        out["outcome"], out["reason"] = "inconclusive", f"retest run classification is '{run.classification}'"
        return out
    base_test = db.get(TestDefinition, base.test_definition_id) if base else None
    if base_test and base_test.test_id != run_test.test_id:
        out["outcome"], out["reason"] = "inconclusive", f"retest used test {run_test.test_id}, original evidence used {base_test.test_id}"
        return out
    if base and base.execution_mode != run.execution_mode:
        out["comparison_limits"].append(f"execution mode differs ({base.execution_mode} vs {run.execution_mode}); numeric metrics are not directly comparable")
    if base and base_test and base_test.version != run_test.version:
        out["comparison_limits"].append(f"test definition version differs ({base_test.version} vs {run_test.version})")
    now_fail = {s["id"] for s in run.scenarios if s.get("pass") is False}
    prev_fail = set(f.failing_scenarios or [])
    if base:
        prev_fail |= {s["id"] for s in base.scenarios if s.get("pass") is False}
    req_fail = {r["name"] for r in run.requirement_results if r.get("pass") is False}
    still = sorted((prev_fail & now_fail) | ({r for r in (f.failing_requirements or []) if r in req_fail}))
    regressions = sorted(now_fail - prev_fail)
    out.update({"previously_failing": sorted(prev_fail), "still_failing": still, "fixed": sorted(prev_fail - now_fail), "new_regressions": regressions,
                "requirement_failures": sorted(req_fail)})
    if still:
        out["outcome"], out["reason"] = "still_failing", "previously failing cases still fail"
    elif regressions or req_fail:
        out["outcome"], out["reason"] = "still_failing", "previously failing cases pass, but the retest shows regressions or requirement failures"
    else:
        out["outcome"], out["reason"] = "resolved_within_tested_scope", "all previously failing cases pass and no regressions in the tested scope"
    return out


# ---------------------------------------------------------------- comparison
def compare_runs(db, a: Run, b: Run) -> dict:
    keys = sorted(set(a.metrics) | set(b.metrics))
    rows = []
    for k in keys:
        va, vb = a.metrics.get(k), b.metrics.get(k)
        num = isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool)
        delta = (vb - va) if num else None
        rows.append({"metric": k, "baseline": va, "candidate": vb, "delta": delta, "delta_pct": (delta / va * 100.0) if num and va else None,
                     "definition": b.metric_definitions.get(k) or a.metric_definitions.get(k) or next((v for kk, v in {**a.metric_definitions, **b.metric_definitions}.items() if kk.endswith("*") and k.startswith(kk[:-1])), "")})
    sa = {s["id"]: s.get("pass") for s in a.scenarios}
    sb = {s["id"]: s.get("pass") for s in b.scenarios}
    limits = []
    ta, tb = db.get(TestDefinition, a.test_definition_id), db.get(TestDefinition, b.test_definition_id)
    if a.execution_mode != b.execution_mode:
        limits.append(f"execution modes differ ({a.execution_mode} vs {b.execution_mode}): timing/memory numbers come from different environments")
    if a.environment.get("platform") != b.environment.get("platform") or a.environment.get("processor") != b.environment.get("processor"):
        limits.append("reported environments differ; compare correctness outcomes, treat numeric deltas with caution")
    if ta.test_id != tb.test_id or ta.version != tb.version:
        limits.append(f"test definitions differ ({ta.test_id}@{ta.version} vs {tb.test_id}@{tb.version})")
    if a.fixture_version != b.fixture_version:
        limits.append(f"fixture versions differ ({a.fixture_version} vs {b.fixture_version})")
    ids = sorted(set(sa) | set(sb))
    return {"metrics": rows,
            "scenarios": [{"id": i, "baseline": sa.get(i), "candidate": sb.get(i)} for i in ids],
            "previously_failing_now": [{"id": i, "candidate": sb.get(i)} for i in ids if sa.get(i) is False],
            "new_regressions": [i for i in ids if sa.get(i) is True and sb.get(i) is False],
            "fixed": [i for i in ids if sa.get(i) is False and sb.get(i) is True],
            "remaining_uncertainty": sorted(set(a.exclusions + b.exclusions + [f"{s}: {sb.get(s)}" for s in ids if sb.get(s) is None])),
            "requirements": {"baseline": a.requirement_results, "candidate": b.requirement_results},
            "comparison_limits": limits, "comparable": not limits}


# ---------------------------------------------------------------- customer-runner bundle import
def import_bundle(db, project: Project, doc: dict, actor_id: str, actor_email: str, test: TestDefinition | None = None) -> tuple[Run, EvidenceBundle, dict]:
    envelope, artifacts = attest.load_bundle(doc)
    trusted = signing.trusted_keys_for(db, project.id, "customer_runner")
    vr = attest.verify_envelope(envelope, trusted, artifacts, expected_predicate=attest.PREDICATE_RUN)
    problems = list(vr.problems)
    if not vr.structure_ok:
        raise ValueError("bundle rejected: " + "; ".join(problems))
    if not (vr.signature_verified and vr.signer_trusted):
        raise ValueError("bundle rejected (signature / trust policy): " + "; ".join(problems))
    if vr.digests_ok is not True:
        raise ValueError("bundle rejected (artifact digests): " + "; ".join(problems))
    pred = vr.statement["predicate"]
    if pred.get("project_id") != project.id:
        raise ValueError(f"bundle rejected (binding): predicate project_id {pred.get('project_id')} is not this project")
    pi = pred.get("implementation") or {}
    impl = next((i for i in db.scalars(select(Implementation).where(Implementation.project_id == project.id)).all()
                 if i.version == pi.get("version") and i.name == pi.get("name")), None)
    if not impl:
        raise ValueError(f"bundle rejected (binding): implementation {pi.get('name')} {pi.get('version')} is not registered in this project")
    pt = pred.get("test") or {}
    if test is None:
        test = next((t for t in db.scalars(select(TestDefinition).where(TestDefinition.project_id == project.id)).all() if t.test_id == pt.get("test_id")), None)
    if not test:
        raise ValueError(f"bundle rejected (binding): test {pt.get('test_id')} is not defined in this project")
    ext_run_id = pred.get("run_id")
    if not ext_run_id:
        raise ValueError("bundle rejected (schema): predicate.run_id missing")
    if "raw_output.json" not in artifacts:
        raise ValueError("bundle rejected (schema): raw_output.json artifact missing")
    raw = json.loads(artifacts["raw_output.json"])
    from runners.base import validate_fixture_output
    sp = validate_fixture_output(raw)
    if sp:
        raise ValueError("bundle rejected (schema): " + "; ".join(sp))
    # duplicate / stale detection
    dup = db.scalar(select(Run).where(Run.project_id == project.id, Run.external_run_id == ext_run_id).order_by(Run.sequence))
    stale = []
    if impl.status in ("superseded", "retired"):
        stale.append(f"implementation {impl.name} {impl.version} is {impl.status}")
    if pi.get("source_digest") and impl.source_digest and pi["source_digest"] != impl.source_digest:
        stale.append("runner-reported source digest differs from the registered snapshot of this version")
    if pt.get("version") and pt["version"] != test.version:
        stale.append(f"bundle used test definition version {pt['version']}; project defines {test.version}")
    run = create_run_record(db, project.id, test.id, impl.id, "customer_runner", "customer_runner", "measured", actor_id)
    run.external_run_id = ext_run_id
    run.runner_reported_executed_at = pred.get("executed_at")
    run.received_at = utcnow()
    run.duplicate_of_run_id = dup.id if dup else None
    run.stale_reason = "; ".join(stale)
    res = RunResult(status=raw.get("status", "completed"), provenance="measured", runner_kind="customer_runner",
                    runner_version=str((pred.get("runner") or {}).get("version", "")), fixture_version=str(raw.get("fixture_version", "")),
                    environment={**raw.get("environment", {}), **(pred.get("environment") or {}), "execution": "customer-side runner; environment as reported by the runner"},
                    commands=pred.get("commands", []), repeat_count=int(raw.get("repeat_count", 0)), metrics=raw.get("metrics", {}),
                    metric_definitions=raw.get("metric_definitions", {}), scenarios=raw.get("scenarios", []), raw_output=artifacts["raw_output.json"],
                    failures=list(raw.get("failures", [])), exclusions=raw.get("exclusions", []),
                    limitations=list(raw.get("limitations", [])) + ["Customer-side execution: the signature establishes integrity and attribution under the trust policy; "
                                                                     "it does not independently prove the claimed environment or that execution was genuine."],
                    extra={"adapter": raw.get("adapter", {}), "parameters": raw.get("parameters", {})})
    persist_result(db, run, res, actor_id, sign_platform=False)
    add_label(run, "imported", f"bundle received from signer '{vr.signer_name}' at {run.received_at.isoformat()}", actor_email)
    add_label(run, "hash_checked", "all statement subjects matched the attached artifacts", "platform")
    add_label(run, "signature_verified", f"DSSE signature by trusted customer-runner key '{vr.signer_name}' ({vr.keyid[:16]}…)", "platform")
    # preserve original bundle + countersign an ingestion receipt (NOT an endorsement)
    data = json.dumps(doc, sort_keys=True).encode()
    bart = artstore.store(db, project.id, "import", f"run_{run.sequence}_customer_bundle.json", data, "application/json", label=f"original customer bundle of run #{run.sequence}")
    env_digest = attest.sha256_hex(attest.canonical(envelope))
    receipt_stmt = attest.build_statement([{"name": "customer-envelope", "digest": {"sha256": env_digest}}], attest.PREDICATE_RECEIPT,
                                          {"purpose": "ingestion receipt: the platform received and stored this envelope; this is NOT an independent endorsement of its contents",
                                           "project_id": project.id, "run_id": run.id, "external_run_id": ext_run_id, "received_at": run.received_at.isoformat(),
                                           "received_by": actor_email, "verification": {"signature_verified": True, "signer": vr.signer_name, "digests_ok": True}})
    receipt = attest.sign_statement(receipt_stmt, signing.platform_private_key())
    b = EvidenceBundle(project_id=project.id, run_id=run.id, kind="customer_runner", envelope=envelope, statement=vr.statement, envelope_sha256=env_digest,
                       signer_keyid=vr.keyid, signer_name=vr.signer_name,
                       verification={"signature_verified": True, "signer_trusted": True, "digests_ok": True, "binding_ok": True, "problems": [],
                                     "duplicate_of": dup.id if dup else None, "stale": stale, "verified": vr.verified, "unverified": vr.unverified},
                       countersignature=receipt, artifact_ids=[run.raw_output_artifact_id], bundle_artifact_id=bart.id)
    db.add(b)
    db.flush()
    run.bundle_id = b.id
    run.artifact_hashes = {**run.artifact_hashes, "customer_bundle": bart.sha256, "envelope": env_digest}
    audit.record(db, actor_id, "bundle.imported", "evidence_bundle", b.id, project.id, {"signer": vr.signer_name, "duplicate": bool(dup), "stale": stale, "external_run_id": ext_run_id})
    return run, b, {"duplicate_of": dup.id if dup else None, "stale": stale, "verified": vr.verified, "unverified": vr.unverified}


# ---------------------------------------------------------------- replay
def replay(db, target: Run, actor_id) -> Run:
    """Platform re-executes the same test definition against the same implementation. If scenario outcomes match, the
    target run gets the `independently_replayed` label for that claim."""
    test, impl = db.get(TestDefinition, target.test_definition_id), db.get(Implementation, target.implementation_id)
    run = create_run_record(db, target.project_id, test.id, impl.id, "platform_sandbox", "platform_sandbox", "measured", actor_id)
    run.correction_note = f"independent replay of run #{target.sequence}"
    req = build_run_request(db, test, impl)
    res = get_runner("platform_sandbox").run(req)
    persist_result(db, run, res, actor_id)
    if run.status == "completed":
        a = {s["id"]: s.get("pass") for s in target.scenarios}
        b = {s["id"]: s.get("pass") for s in run.scenarios}
        if a == b:
            add_label(target, "independently_replayed", f"scenario outcomes of {test.test_id}@{test.version} reproduced by platform run #{run.sequence}", "platform", run.id)
        else:
            add_label(target, "imported", f"replay run #{run.sequence} produced DIFFERENT scenario outcomes; not replayed", "platform", run.id)
    audit.record(db, actor_id, "run.replayed", "run", target.id, target.project_id, {"replay_run_id": run.id, "matched": run.evidence_labels and run.status == "completed"})
    return run


# ---------------------------------------------------------------- job handlers
@jobs.handler("run_test")
def _job_run_test(db, payload: dict):
    run = db.get(Run, payload["run_id"])
    run.status = "running"
    db.commit()
    test, impl = db.get(TestDefinition, run.test_definition_id), db.get(Implementation, run.implementation_id)
    try:
        req = build_run_request(db, test, impl, payload.get("params"))
        result = get_runner(payload.get("runner_kind", "platform_sandbox")).run(req)
    except RuntimeError as e:
        result = RunResult(status="failed", provenance="measured", runner_kind="platform_sandbox", runner_version="", failures=[str(e)])
    persist_result(db, run, result, payload.get("actor_id"))
    db.commit()
    return {"run_id": run.id, "classification": run.classification}


@jobs.handler("research_review")
def _job_research_review(db, payload: dict):
    src = db.get(ResearchSource, payload["source_id"])
    f = review_source(db, src)
    audit.record(db, payload.get("actor_id"), "finding.created", "finding", f.id, src.project_id, {"source_id": src.id, "method": f.extraction_method})
    db.commit()
    return {"finding_id": f.id}


@jobs.handler("execute_experiment")
def _job_execute_experiment(db, payload: dict):
    prop = db.get(ExperimentProposal, payload["proposal_id"])
    pv = db.scalar(select(ProtocolVersion).where(ProtocolVersion.proposal_id == prop.id, ProtocolVersion.version == prop.current_protocol_version))
    run = db.get(Run, payload["run_id"])
    run.status = "running"
    db.commit()
    test, impl = db.get(TestDefinition, run.test_definition_id), db.get(Implementation, run.implementation_id)
    proto = pv.protocol
    try:
        req = build_run_request(db, test, impl, fixture=proto["allowlisted_fixture"], params=proto.get("parameters", {}),
                                limits={"timeout_s": 120, "memory_mb": 512, "cpu_s": 90})
        result = get_runner("platform_sandbox").run(req)
    except RuntimeError as e:
        result = RunResult(status="failed", provenance="measured", runner_kind="platform_sandbox", runner_version="", failures=[str(e)])
    persist_result(db, run, result, payload.get("actor_id"))
    prop.status = "executed"
    prop.run_ids = prop.run_ids + [run.id]
    prop.result_summary = summarize_experiment(run, prop)
    prop.claim_status = "reproduced" if run.status == "completed" else "proposal"
    if prop.finding_id:
        f = db.get(Finding, prop.finding_id)
        if run.id not in f.evidence_run_ids:
            f.evidence_run_ids = f.evidence_run_ids + [run.id]
    if run.status == "completed" and proto["allowlisted_fixture"] == "toy_factoring":
        m = run.metrics
        db.add(AttackAssessment(project_id=prop.project_id, implementation_id=None, category="measured_experiment", attack_model="classical",
                                target=f"Synthetic {m.get('modulus_bits')}-bit semiprime (toy, generated in-fixture)", target_parameters={"modulus_bits": m.get("modulus_bits")},
                                objective="Recover a prime factor of a toy modulus (workflow demonstration).", attacker_capabilities="Single core, pure Python.",
                                method="Pollard rho (Brent), isolated runner.", source="Executed here.", hardware_assumptions=json.dumps(run.environment),
                                measured_components={"iterations_per_second": m.get("iterations_per_second"), "run_id": run.id},
                                expected_work={"value": m.get("iterations_mean"), "unit": "iterations (mean observed)", "estimation_method": "directly observed"},
                                probability_model=result.extra.get("probability_model", ""), uncertainty=f"{m.get('trials')} trials; high variance.",
                                applicability_limits="Toy parameters only; not applicable to any deployed key.", run_id=run.id, review_date=utcnow().date().isoformat()))
    db.commit()
    return {"run_id": run.id, "summary": prop.result_summary}


@jobs.handler("replay_run")
def _job_replay(db, payload: dict):
    target = db.get(Run, payload["target_run_id"])
    run = replay(db, target, payload.get("actor_id"))
    db.commit()
    return {"replay_run_id": run.id}
