"""Attack-cost research view helpers.

Categories: A measured experiment | B estimated from measured components | C published estimate | D unknown.
Rules enforced here:
* Signing/verification speed is never converted into breaking time (no helper exists for it).
* A toy measurement (category A) may only inform a category-B estimate for a target that is itself synthetic/toy
  and within a bounded parameter range; anything larger returns "No defensible estimate available".
* Classical and quantum models are separate records.
"""
from __future__ import annotations

import math

NO_ESTIMATE = "No defensible estimate available"
TOY_EXTRAPOLATION_MAX_BITS = 80  # Pollard rho estimates are only offered for synthetic moduli up to this size


def rho_estimate_from_measurement(measured_iter_per_s: float, target_modulus_bits: int) -> dict:
    """Category-B estimate for a SYNTHETIC modulus using measured toy throughput. Refuses large targets."""
    if target_modulus_bits > TOY_EXTRAPOLATION_MAX_BITS:
        return {"value": None, "unit": "seconds", "log2_work": None, "estimation_method": NO_ESTIMATE,
                "note": (f"Pollard rho measured on toy parameters cannot be extrapolated to {target_modulus_bits}-bit moduli; "
                         "the relevant classical algorithm (GNFS) has different complexity and this would be a fabricated number.")}
    p_bits = target_modulus_bits // 2
    expected_iter = math.sqrt(math.pi * 2 ** p_bits / 2)
    seconds = expected_iter / measured_iter_per_s
    return {"value": seconds, "unit": "seconds (expected, single core)", "log2_work": math.log2(expected_iter),
            "estimation_method": "E[iterations] = sqrt(pi*p/2) for smallest prime p, divided by measured iterations/s",
            "probability_model": "P(success by k iterations) ~ 1 - exp(-k^2/(2p)); expected value, not a deadline."}


def apply_compute_price(expected_work: dict | None, price: dict | None) -> dict | None:
    """Optional user-supplied price: {unit: 'core_hour', price_usd: x}. Only applies when work is numeric in seconds."""
    if not expected_work or not price or expected_work.get("value") is None:
        return None
    unit = expected_work.get("unit", "")
    if "second" not in unit:
        return None
    hours = expected_work["value"] / 3600.0
    return {"core_hours": hours, "usd": hours * float(price.get("price_usd", 0)), "price": price,
            "note": "Linear scaling assumes perfect parallelisation and ignores overheads; user-supplied price."}


def validate_assessment(data: dict) -> list[str]:
    problems = []
    if data.get("category") not in ("A", "B", "C", "D"):
        problems.append("category must be A, B, C or D")
    if data.get("attack_model") not in ("classical", "quantum"):
        problems.append("attack_model must be classical or quantum")
    ew = data.get("expected_work") or {}
    if data.get("category") == "D" and ew.get("value") is not None:
        problems.append("category D (unknown) must not carry a numeric expected work")
    if data.get("category") == "A" and not data.get("run_id") and not data.get("measured_throughput"):
        problems.append("category A requires a measured run or throughput")
    txt = (str(data.get("method", "")) + str(ew.get("estimation_method", ""))).lower()
    if "verify" in txt and "speed" in txt and ew.get("value") is not None:
        problems.append("expected work must not be derived from signing/verification speed")
    if data.get("attack_model") == "quantum" and any(k in str(ew).lower() for k in ("year 20", "by 20")):
        problems.append("do not assert a calendar date for quantum practicality")
    return problems
