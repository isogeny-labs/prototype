"""Attack assessment rules.

Categories: reproduced_weakness | measured_experiment | estimated_effort | published_estimate | unknown.
* Breaking time is never derived from signing/verification speed (no helper exists; validation rejects it).
* Toy measurements can only inform estimates for synthetic targets within a bounded range.
* Classical and quantum models are separate records; no calendar date for quantum practicality is asserted.
"""
from __future__ import annotations

import math

NO_ESTIMATE = "No defensible estimate available"
CATEGORIES = {"reproduced_weakness": "Reproduced implementation weaknesses", "measured_experiment": "Measured attack experiments",
              "estimated_effort": "Estimated attack effort under stated assumptions", "published_estimate": "Published security estimates",
              "unknown": "Unknown or unsupported assessments"}
TOY_EXTRAPOLATION_MAX_BITS = 80


def rho_estimate_from_measurement(measured_iter_per_s: float, target_modulus_bits: int) -> dict:
    if target_modulus_bits > TOY_EXTRAPOLATION_MAX_BITS:
        return {"value": None, "unit": "seconds", "log2_work": None, "estimation_method": NO_ESTIMATE,
                "note": f"Pollard rho measured on toy parameters cannot be extrapolated to {target_modulus_bits}-bit moduli; the relevant "
                        "classical algorithm (GNFS) has different complexity and any number would be fabricated."}
    p_bits = target_modulus_bits // 2
    expected_iter = math.sqrt(math.pi * 2 ** p_bits / 2)
    return {"value": expected_iter / measured_iter_per_s, "unit": "seconds (expected, single core)", "log2_work": math.log2(expected_iter),
            "estimation_method": "E[iterations] = sqrt(pi*p/2) for smallest prime p, divided by measured iterations/s",
            "probability_model": "P(success by k iterations) ~ 1 - exp(-k^2/(2p)); an expectation, not a deadline."}


def apply_compute_price(expected_work, price):
    if not expected_work or not price or expected_work.get("value") is None or "second" not in expected_work.get("unit", ""):
        return None
    hours = expected_work["value"] / 3600.0
    return {"core_hours": hours, "usd": hours * float(price.get("price_usd", 0)), "price": price,
            "note": "Linear scaling assumes perfect parallelisation and ignores overheads; customer-supplied price."}


def validate_assessment(d: dict) -> list[str]:
    p = []
    if d.get("category") not in CATEGORIES:
        p.append(f"category must be one of {sorted(CATEGORIES)}")
    if d.get("attack_model") not in ("classical", "quantum"):
        p.append("attack_model must be classical or quantum")
    ew = d.get("expected_work") or {}
    if d.get("category") == "unknown" and ew.get("value") is not None:
        p.append("category 'unknown' must not carry a numeric expected work")
    if d.get("category") in ("measured_experiment", "reproduced_weakness") and not d.get("run_id") and not d.get("measured_components"):
        p.append(f"category '{d.get('category')}' requires a linked run or measured components")
    txt = (str(d.get("method", "")) + str(ew.get("estimation_method", ""))).lower()
    if ("verif" in txt or "sign" in txt) and "speed" in txt and ew.get("value") is not None:
        p.append("expected work must not be derived from signing/verification speed")
    if d.get("attack_model") == "quantum" and any(k in str(ew).lower() for k in ("year 20", "by 20")):
        p.append("do not assert a calendar date for quantum practicality")
    return p
