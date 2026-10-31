"""Requirement evaluation: compare run metrics with customer-defined limits.

A requirement applies to a run only when the run's provenance matches `applies_to`
(e.g. an on-device verify-time limit applies to imported hardware measurements, not to host fixtures).
"""
from __future__ import annotations

OPS = {
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "==": lambda a, b: a == b,
}


def evaluate(requirements, metrics: dict, provenance: str) -> list[dict]:
    out = []
    for r in requirements:
        applicable = r.applies_to in ("all", provenance) or (r.applies_to == "imported" and provenance == "illustrative")
        observed = metrics.get(r.metric)
        res = {"requirement_id": r.id, "name": r.name, "metric": r.metric, "operator": r.operator,
               "threshold": r.threshold, "unit": r.unit, "observed": observed, "applicable": applicable}
        if not applicable:
            res["pass"] = None
            res["note"] = f"not applicable to provenance '{provenance}' (applies to {r.applies_to})"
        elif observed is None:
            res["pass"] = None
            res["note"] = "metric not reported by this run"
        else:
            try:
                res["pass"] = bool(OPS[r.operator](float(observed), float(r.threshold)))
            except Exception:
                res["pass"] = None
                res["note"] = "could not compare"
        out.append(res)
    return out


def overall(scenarios: list, requirement_results: list, status: str) -> bool | None:
    if status != "completed":
        return False
    if any(s.get("pass") is False for s in scenarios):
        return False
    if any(r.get("pass") is False for r in requirement_results):
        return False
    return True


def failed_requirements(requirement_results: list) -> list[dict]:
    return [r for r in requirement_results if r.get("pass") is False]
