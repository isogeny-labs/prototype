from __future__ import annotations
import hashlib
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import ResearchSource, Finding, ExperimentProposal, ProtocolVersion, Approval, Implementation, TestDefinition, Run, AttackAssessment, utcnow
from .. import audit, jobs, services, ai_adapter, attackcost
from ..research import propose_experiments
from iel_tools import attest
from .common import row, rows, viewer, editor, reviewer, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}", tags=["research"])
ALLOWLIST = {
    "malformed_input_sweep": {"description": "Sweep malformed signature encodings against the implementation's adapter in the platform sandbox.",
                              "bounds": {"max_extra_bytes": (1, 256), "seed": (0, 2**31)}, "target_class": "owned", "needs_adapter": True},
    "toy_factoring": {"description": "Pollard rho on a synthetic <= 64-bit semiprime generated in-fixture (workflow demonstration only).",
                      "bounds": {"modulus_bits": (16, 64), "trials": (1, 20), "max_iterations": (1000, 20_000_000)}, "target_class": "synthetic", "needs_adapter": False},
}


class SourceIn(BaseModel):
    title: str = ""
    url: str | None = None
    content: str | None = None
    is_demo: bool = False
    review_now: bool = True
    wait: bool = False


def _fetch_url(url: str) -> str:
    import httpx
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "only http(s) URLs are accepted")
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "IsogenyEvidenceLab/0.2"}) as c:
            r = c.get(url)
            r.raise_for_status()
            text = r.text[:2_000_000]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"could not fetch URL ({type(e).__name__}); paste the document text instead")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


@router.get("/research/status")
def research_status(ctx=Depends(viewer)):
    return {"ai_adapter_available": ai_adapter.available(), "extraction_method": "ai_adapter" if ai_adapter.available() else "rule_based",
            "proposal_method": "ai_adapter + rules" if ai_adapter.available() else "rule_based",
            "note": ("AI adapter configured: model extraction validated by schema, then rule-matched." if ai_adapter.available() else
                     "No AI provider configured: rule-based extraction and proposals. Human review is required either way."),
            "monitoring": "manual submission only (no continuous monitoring implemented)"}


@router.get("/research/sources")
def list_sources(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(ResearchSource).where(ResearchSource.project_id == project.id).order_by(ResearchSource.created_at.desc())).all())


@router.post("/research/sources")
def submit_source(body: SourceIn, ctx=Depends(editor)):
    project, db, user = ctx
    content = body.content or ""
    if body.url and not content:
        content = _fetch_url(body.url)
    if not content.strip():
        raise HTTPException(400, "provide content or a fetchable url")
    src = ResearchSource(project_id=project.id, title=body.title or (body.url or "Untitled document")[:200], url=body.url, content=content,
                         content_sha256=hashlib.sha256(content.encode()).hexdigest(), source_type="url" if body.url else "document", is_demo=body.is_demo, submitted_by=user.id)
    db.add(src)
    db.flush()
    audit.record(db, user.id, "research.source_submitted", "research_source", src.id, project.id, {"sha256": src.content_sha256, "is_demo": src.is_demo})
    job = jobs.enqueue(db, "research_review", {"source_id": src.id, "actor_id": user.id}) if body.review_now else None
    db.commit()
    if job and body.wait:
        jobs.process_pending()
        db.expire_all()
        src = db.get(ResearchSource, src.id)
    return {**row(src), "job_id": job.id if job else None}


# ---------------------------------------------------------------- experiment proposals
@router.get("/experiments/allowlist")
def allowlist():
    return ALLOWLIST


@router.get("/experiments")
def list_proposals(ctx=Depends(viewer)):
    project, db, _ = ctx
    return rows(db.scalars(select(ExperimentProposal).where(ExperimentProposal.project_id == project.id).order_by(ExperimentProposal.created_at.desc())).all())


@router.post("/experiments/propose")
def propose(ctx=Depends(editor)):
    """Explicit 'Propose experiments' action (manual trigger; no continuous monitoring)."""
    project, db, user = ctx
    findings = db.scalars(select(Finding).where(Finding.project_id == project.id)).all()
    sources = db.scalars(select(ResearchSource).where(ResearchSource.project_id == project.id)).all()
    props = propose_experiments(db, project, findings, sources)
    audit.record(db, user.id, "experiments.proposed", "project", project.id, project.id, {"count": len(props), "method": "rule_based"}, commit=True)
    return rows(props)


class ProposalIn(BaseModel):
    title: str
    finding_id: str | None = None
    affected_implementation_id: str | None = None
    research_question: str = ""
    motivation: str = ""
    source_references: list = []
    hypothesis: str = ""
    baseline_controls: str = ""
    procedure: str = ""
    required_tools: list = []
    outcomes: dict = {}
    budget: dict = {}
    required_artifacts: list = []
    safety_boundaries: str = ""
    can_establish: str = ""
    cannot_establish: str = ""
    allowlisted_fixture: str | None = None
    parameters: dict = {}
    target_class: str = "owned"


def _check_bounds(fixture: str, params: dict):
    for k, (lo, hi) in ALLOWLIST[fixture]["bounds"].items():
        v = params.get(k)
        if v is not None and not (lo <= int(v) <= hi):
            raise HTTPException(400, f"parameter {k}={v} outside allowlisted bounds [{lo}, {hi}]")


@router.post("/experiments")
def create_proposal(body: ProposalIn, ctx=Depends(editor)):
    project, db, user = ctx
    if body.allowlisted_fixture:
        if body.allowlisted_fixture not in ALLOWLIST:
            raise HTTPException(400, "fixture is not allowlisted; record the proposal with allowlisted_fixture=null (it cannot execute)")
        _check_bounds(body.allowlisted_fixture, body.parameters)
    p = ExperimentProposal(project_id=project.id, status="proposed", claim_status="proposal", proposed_by=user.email, **body.model_dump())
    db.add(p)
    db.flush()
    if p.finding_id:
        f = db.get(Finding, p.finding_id)
        if f:
            f.experiment_proposal_ids = (f.experiment_proposal_ids or []) + [p.id]
    audit.record(db, user.id, "experiment.proposed", "experiment_proposal", p.id, project.id, {"title": p.title}, commit=True)
    return row(p)


@router.get("/experiments/{pid}")
def get_proposal(pid: str, ctx=Depends(viewer)):
    project, db, _ = ctx
    p = get_or_404(db, ExperimentProposal, pid, project.id)
    pvs = db.scalars(select(ProtocolVersion).where(ProtocolVersion.proposal_id == p.id).order_by(ProtocolVersion.version)).all()
    runs = [db.get(Run, r) for r in p.run_ids]
    approvals = db.scalars(select(Approval).where(Approval.subject_type == "experiment_proposal", Approval.subject_id == p.id)).all()
    return {**row(p), "protocol_versions": rows(pvs), "runs": rows([r for r in runs if r]), "approvals": rows(approvals),
            "finding": row(db.get(Finding, p.finding_id)) if p.finding_id else None,
            "affected_implementation": row(db.get(Implementation, p.affected_implementation_id)) if p.affected_implementation_id else None,
            "allowlist_entry": ALLOWLIST.get(p.allowlisted_fixture) if p.allowlisted_fixture else None}


PROTOCOL_FIELDS = ("title", "research_question", "motivation", "source_references", "hypothesis", "baseline_controls", "procedure", "required_tools", "outcomes",
                   "budget", "required_artifacts", "safety_boundaries", "can_establish", "cannot_establish", "allowlisted_fixture", "parameters", "target_class",
                   "affected_implementation_id", "finding_id")


class DecisionIn(BaseModel):
    decision: str
    note: str = ""


@router.post("/experiments/{pid}/decide")
def decide(pid: str, body: DecisionIn, ctx=Depends(reviewer)):
    """Human approval freezes the proposal as protocol version N (never overwritten)."""
    project, db, user = ctx
    p = get_or_404(db, ExperimentProposal, pid, project.id)
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "bad decision")
    if p.status not in ("proposed",):
        raise HTTPException(409, f"cannot decide from status {p.status}; amend to create a new proposal version")
    db.add(Approval(project_id=project.id, subject_type="experiment_proposal", subject_id=p.id, decision=body.decision, reviewer_id=user.id, note=body.note))
    if body.decision == "approved":
        proto = {k: getattr(p, k) for k in PROTOCOL_FIELDS}
        v = p.current_protocol_version + 1
        db.add(ProtocolVersion(proposal_id=p.id, version=v, protocol=proto, protocol_sha256=attest.sha256_hex(attest.canonical(proto)), approved_by=user.id,
                               note=body.note, supersedes_version=p.current_protocol_version or None))
        p.current_protocol_version = v
    p.status = body.decision
    audit.record(db, user.id, f"experiment.{body.decision}", "experiment_proposal", p.id, project.id, {"protocol_version": p.current_protocol_version}, commit=True)
    return row(p)


class AmendIn(BaseModel):
    changes: dict
    note: str = ""


@router.post("/experiments/{pid}/amend")
def amend(pid: str, body: AmendIn, ctx=Depends(editor)):
    """Amendment: update proposal fields and return it to 'proposed' so a reviewer can approve a NEW protocol version.
    Earlier protocol versions and raw results are preserved. Acceptance criteria (outcomes) may only change through this human path."""
    project, db, user = ctx
    p = get_or_404(db, ExperimentProposal, pid, project.id)
    bad = [k for k in body.changes if k not in PROTOCOL_FIELDS]
    if bad:
        raise HTTPException(400, f"cannot amend fields {bad}")
    if "allowlisted_fixture" in body.changes and body.changes["allowlisted_fixture"] not in (None, *ALLOWLIST):
        raise HTTPException(400, "fixture is not allowlisted")
    for k, v in body.changes.items():
        setattr(p, k, v)
    if p.allowlisted_fixture:
        _check_bounds(p.allowlisted_fixture, p.parameters)
    p.status = "proposed"
    audit.record(db, user.id, "experiment.amended", "experiment_proposal", p.id, project.id, {"fields": list(body.changes), "note": body.note}, commit=True)
    return row(p)


@router.post("/experiments/{pid}/execute")
def execute(pid: str, wait: bool = False, ctx=Depends(editor)):
    """Execute the APPROVED protocol version of an allowlisted experiment in the platform sandbox."""
    project, db, user = ctx
    p = get_or_404(db, ExperimentProposal, pid, project.id)
    if p.status != "approved" or not p.current_protocol_version:
        raise HTTPException(409, "experiment must have an approved protocol version before execution")
    if not p.allowlisted_fixture or p.allowlisted_fixture not in ALLOWLIST:
        raise HTTPException(409, "experiment has no allowlisted fixture; it is a proposal only and cannot execute")
    entry = ALLOWLIST[p.allowlisted_fixture]
    if p.target_class != entry["target_class"] and not (entry["target_class"] == "owned" and p.target_class == "authorized"):
        raise HTTPException(409, "target class does not match the allowlisted fixture")
    impl = db.get(Implementation, p.affected_implementation_id) if p.affected_implementation_id else None
    if entry["needs_adapter"]:
        if not impl:
            raise HTTPException(409, "this experiment needs an affected implementation with an executable adapter")
        if (impl.compatibility or {}).get("status") != "compatible":
            raise HTTPException(409, "the affected implementation is not executable in the sandbox")
    if not impl:
        impl = db.scalar(select(Implementation).where(Implementation.project_id == project.id, Implementation.name == "Synthetic experiment target"))
        if not impl:
            impl = Implementation(project_id=project.id, name="Synthetic experiment target", version="n/a", status="retired", algorithm="synthetic toy parameters",
                                  adapter_kind="results_only", notes="Placeholder target for research-only experiments.", created_by=user.id)
            db.add(impl)
            db.flush()
    t = db.scalar(select(TestDefinition).where(TestDefinition.project_id == project.id, TestDefinition.fixture == p.allowlisted_fixture))
    if not t:
        t = TestDefinition(project_id=project.id, test_id=p.allowlisted_fixture.replace("_", "-"), version="1", name=f"Experiment: {entry['description'][:70]}",
                           fixture=p.allowlisted_fixture, definition={"experiment": True}, acceptance_criteria=["per approved protocol"],
                           description="Research experiment fixture; not part of the core test coverage.")
        db.add(t)
        db.flush()
    run = services.create_run_record(db, project.id, t.id, impl.id, "platform_sandbox", "platform_sandbox", "measured", user.id, proposal_id=p.id, protocol_version=p.current_protocol_version)
    job = jobs.enqueue(db, "execute_experiment", {"proposal_id": p.id, "run_id": run.id, "actor_id": user.id})
    run.job_id = job.id
    audit.record(db, user.id, "experiment.executed", "experiment_proposal", p.id, project.id, {"run_id": run.id, "protocol_version": p.current_protocol_version})
    db.commit()
    if wait:
        jobs.process_pending()
        db.expire_all()
        p = db.get(ExperimentProposal, p.id)
    return {**row(p), "run_id": run.id, "job_id": job.id}


@router.post("/experiments/{pid}/review")
def review_result(pid: str, body: DecisionIn, ctx=Depends(reviewer)):
    project, db, user = ctx
    p = get_or_404(db, ExperimentProposal, pid, project.id)
    if p.status != "executed":
        raise HTTPException(409, "only executed experiments can be reviewed")
    db.add(Approval(project_id=project.id, subject_type="experiment_proposal", subject_id=p.id, decision="reviewed", reviewer_id=user.id, note=body.note))
    p.status = "reviewed"
    audit.record(db, user.id, "experiment.reviewed", "experiment_proposal", p.id, project.id, {"note": body.note}, commit=True)
    return row(p)


# ---------------------------------------------------------------- attack assessments
class AssessmentIn(BaseModel):
    category: str
    attack_model: str
    target: str
    implementation_id: str | None = None
    target_parameters: dict = {}
    target_version: str = ""
    objective: str = ""
    attacker_capabilities: str = ""
    method: str = ""
    source: str = ""
    hardware_assumptions: str = ""
    measured_components: dict | None = None
    expected_work: dict | None = None
    probability_model: str = ""
    parallelization: str = ""
    overhead_assumptions: str = ""
    compute_price: dict | None = None
    uncertainty: str = ""
    applicability_limits: str = ""
    review_date: str | None = None
    run_id: str | None = None
    finding_id: str | None = None
    is_demo: bool = False


def _present(a: AttackAssessment) -> dict:
    d = row(a)
    ew = a.expected_work or {}
    if a.category == "unknown" or (ew.get("value") is None and ew.get("log2_work") is None and ew.get("log2") is None):
        d["display_work"] = attackcost.NO_ESTIMATE
    elif ew.get("value") is None:
        d["display_work"] = f"2^{(ew.get('log2_work') or ew.get('log2')):.1f} {ew.get('unit', 'operations')}"
    else:
        d["display_work"] = f"{ew.get('value')} {ew.get('unit', '')}"
    d["cost"] = attackcost.apply_compute_price(a.expected_work, a.compute_price)
    return d


@router.get("/attack-assessments")
def list_assessments(ctx=Depends(viewer)):
    project, db, _ = ctx
    items = db.scalars(select(AttackAssessment).where(AttackAssessment.project_id == project.id).order_by(AttackAssessment.created_at)).all()
    return {"categories": attackcost.CATEGORIES, "items": [_present(a) for a in items]}


@router.post("/attack-assessments")
def create_assessment(body: AssessmentIn, ctx=Depends(editor)):
    project, db, user = ctx
    problems = attackcost.validate_assessment(body.model_dump())
    if problems:
        raise HTTPException(400, "; ".join(problems))
    if body.run_id:
        get_or_404(db, Run, body.run_id, project.id)
    a = AttackAssessment(project_id=project.id, **body.model_dump())
    if not a.review_date:
        a.review_date = utcnow().date().isoformat()
    db.add(a)
    db.flush()
    audit.record(db, user.id, "attack_assessment.created", "attack_assessment", a.id, project.id, {"category": a.category}, commit=True)
    return _present(a)


class PriceIn(BaseModel):
    compute_price: dict | None


@router.patch("/attack-assessments/{aid}/price")
def set_price(aid: str, body: PriceIn, ctx=Depends(editor)):
    project, db, user = ctx
    a = get_or_404(db, AttackAssessment, aid, project.id)
    a.compute_price = body.compute_price
    audit.record(db, user.id, "attack_assessment.price", "attack_assessment", a.id, project.id, {}, commit=True)
    return _present(a)


class EstimateIn(BaseModel):
    measured_run_id: str
    target_modulus_bits: int
    compute_price: dict | None = None


@router.post("/attack-assessments/estimate-from-run")
def estimate_from_run(body: EstimateIn, ctx=Depends(editor)):
    project, db, user = ctx
    run = get_or_404(db, Run, body.measured_run_id, project.id)
    ips = run.metrics.get("iterations_per_second")
    if not ips:
        raise HTTPException(400, "run has no measured iterations_per_second")
    est = attackcost.rho_estimate_from_measurement(ips, body.target_modulus_bits)
    cat = "unknown" if est["value"] is None else "estimated_effort"
    a = AttackAssessment(project_id=project.id, category=cat, attack_model="classical", target=f"Synthetic {body.target_modulus_bits}-bit semiprime (hypothetical, not a deployed key)",
                         target_parameters={"modulus_bits": body.target_modulus_bits}, objective="Recover a prime factor (toy extrapolation).",
                         attacker_capabilities="Single core, same software as the measured run.", method=("Pollard rho; expected iterations scaled from measured throughput" if cat == "estimated_effort" else "Pollard rho extrapolation refused"),
                         source=f"Derived from run #{run.sequence}.", hardware_assumptions=str(run.environment.get("processor", "runner host")),
                         measured_components={"iterations_per_second": ips, "run_id": run.id},
                         expected_work=est if cat == "estimated_effort" else {"value": None, "unit": "", "estimation_method": attackcost.NO_ESTIMATE, "note": est["note"]},
                         probability_model=est.get("probability_model", ""), parallelization="Linear speed-up assumed if parallelised (idealised).", overhead_assumptions="None.",
                         compute_price=body.compute_price, uncertainty="Birthday-paradox variance; implementation constants; toy-only.",
                         applicability_limits=est.get("note", "Synthetic targets only; not applicable to any deployed key."), run_id=run.id, review_date=utcnow().date().isoformat())
    db.add(a)
    db.flush()
    audit.record(db, user.id, "attack_assessment.estimated", "attack_assessment", a.id, project.id, {"category": cat}, commit=True)
    return _present(a)
