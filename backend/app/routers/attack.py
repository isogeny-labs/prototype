from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..models import AttackAssessment, Run
from .. import audit, attackcost
from .common import row, rows, viewer, editor, get_or_404

router = APIRouter(prefix="/api/projects/{project_id}/attack-assessments", tags=["attack-cost"])


class AssessmentIn(BaseModel):
    category: str
    attack_model: str
    target: str
    target_parameters: dict = {}
    objective: str = ""
    attacker_capabilities: str = ""
    method: str = ""
    source: str = ""
    hardware_assumptions: str = ""
    measured_throughput: dict | None = None
    expected_work: dict | None = None
    probability_model: str = ""
    parallelization: str = ""
    overhead_assumptions: str = ""
    compute_price: dict | None = None
    uncertainty: str = ""
    applicability_limits: str = ""
    run_id: str | None = None
    is_demo: bool = False


def _present(a: AttackAssessment) -> dict:
    d = row(a)
    ew = a.expected_work or {}
    d["display_work"] = (attackcost.NO_ESTIMATE if a.category == "D" or ew.get("value") is None and not ew.get("log2") else
                         (f"2^{ew['log2']:.1f} {ew.get('unit', 'operations')}" if ew.get("log2") is not None and ew.get("value") is None else
                          f"{ew.get('value')} {ew.get('unit', '')}"))
    d["cost"] = attackcost.apply_compute_price(a.expected_work, a.compute_price)
    return d


@router.get("")
def list_assessments(ctx=Depends(viewer)):
    project, db, _ = ctx
    items = db.scalars(select(AttackAssessment).where(AttackAssessment.project_id == project.id).order_by(AttackAssessment.category, AttackAssessment.created_at)).all()
    return {"categories": {"A": "Directly measured attack experiments", "B": "Estimated attack effort derived from measured components",
                           "C": "Published security estimates", "D": "Unknown or unsupported estimates"},
            "items": [_present(a) for a in items]}


@router.post("")
def create_assessment(body: AssessmentIn, ctx=Depends(editor)):
    project, db, user = ctx
    problems = attackcost.validate_assessment(body.model_dump())
    if problems:
        raise HTTPException(400, "; ".join(problems))
    if body.run_id:
        get_or_404(db, Run, body.run_id, project.id)
    a = AttackAssessment(project_id=project.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit.record(db, user.id, "attack_assessment.created", "attack_assessment", a.id, project.id, {"category": a.category}, commit=True)
    return _present(a)


class PriceIn(BaseModel):
    compute_price: dict | None


@router.patch("/{aid}/price")
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


@router.post("/estimate-from-run")
def estimate_from_run(body: EstimateIn, ctx=Depends(editor)):
    """Category-B estimate for a SYNTHETIC modulus from a measured toy run. Refuses targets beyond the toy range."""
    project, db, user = ctx
    run = get_or_404(db, Run, body.measured_run_id, project.id)
    ips = run.metrics.get("iterations_per_second")
    if not ips:
        raise HTTPException(400, "run has no measured iterations_per_second")
    est = attackcost.rho_estimate_from_measurement(ips, body.target_modulus_bits)
    cat = "D" if est["value"] is None else "B"
    a = AttackAssessment(
        project_id=project.id, category=cat, attack_model="classical",
        target=f"Synthetic {body.target_modulus_bits}-bit semiprime (hypothetical, not a deployed key)",
        target_parameters={"modulus_bits": body.target_modulus_bits},
        objective="Recover a prime factor (toy extrapolation).", attacker_capabilities="Single core, same software as measured run.",
        method="Pollard rho; expected iterations scaled from measured throughput" if cat == "B" else "Pollard rho extrapolation refused",
        source=f"Derived from run #{run.sequence} ({run.provenance}).", hardware_assumptions=str(run.environment.get("processor", "runner host")),
        measured_throughput={"value": ips, "unit": "iterations/s", "run_id": run.id},
        expected_work=est if cat == "B" else {"value": None, "unit": "", "estimation_method": attackcost.NO_ESTIMATE, "note": est["note"]},
        probability_model=est.get("probability_model", ""), parallelization="Linear speed-up assumed if parallelised (idealised).",
        overhead_assumptions="No I/O or coordination overhead.", compute_price=body.compute_price,
        uncertainty="Birthday-paradox variance; constant factors of the implementation; toy-only.",
        applicability_limits=est.get("note", "Synthetic targets only; not applicable to any deployed key."), run_id=run.id)
    db.add(a)
    db.flush()
    audit.record(db, user.id, "attack_assessment.estimated", "attack_assessment", a.id, project.id, {"category": cat}, commit=True)
    return _present(a)
