"""Recommendations: turn validated findings into engineering guidance.

guidance_kind: best_practice (general), hypothesis (needs testing), project_specific (supported by this project's results).
Only vetted algorithms/libraries are recommended; nothing is claimed fixed until the revised version is retested.
"""
from __future__ import annotations

from . import catalog
from .models import Finding, Implementation, Run, ExperimentProposal

GUIDANCE = {
    "Ed25519": ["RFC 8032 §5.1.7: verification must reject signatures whose encoded length is not 64 bytes and whose S is not canonical.",
                "FIPS 186-5 §7.8 (EdDSA verification)."],
    "ECDSA": ["FIPS 186-5 §6.4.2 (ECDSA verification): reject r or s outside [1, n-1]; parse DER strictly.", "RFC 6979 for deterministic nonces (signer side)."],
    "RSA": ["RFC 8017 §8.2.2 / §9.2: verify the full encoded message, including padding and DigestInfo, with a constant comparison.",
            "FIPS 186-5 §5 (RSA)."],
    "ML-DSA": ["FIPS 204 Algorithm 3 (ML-DSA.Verify): reject on any decoding failure; do not accept partial inputs."],
}
GENERAL = ["Fail closed: any error path in verification returns 'invalid'.",
           "Validate input lengths before calling the library; do not normalise, pad or truncate signatures."]


def _family(impl: Implementation | None) -> str:
    a = ((impl.algorithm if impl else "") or "").lower()
    for fam, keys in (("Ed25519", ("ed25519", "eddsa")), ("ECDSA", ("ecdsa", "p-256", "p256")), ("RSA", ("rsa",)), ("ML-DSA", ("ml-dsa", "dilithium"))):
        if any(k in a for k in keys):
            return fam
    return ""


def recommendation_for_finding(db, finding: Finding, project) -> dict:
    impl = next((db.get(Implementation, i) for i in (finding.affected_implementation_ids or []) if db.get(Implementation, i)), None)
    fam = _family(impl)
    runs = [db.get(Run, r) for r in (finding.evidence_run_ids or [])]
    runs = [r for r in runs if r]
    exps = [db.get(ExperimentProposal, p) for p in (finding.experiment_proposal_ids or [])]
    executed = [e for e in exps if e and e.run_ids]  # executed results survive later amendments/re-approvals
    evidence = [{"run_id": r.id, "sequence": r.sequence, "execution_mode": r.execution_mode, "classification": r.classification,
                 "failing_scenarios": [s["id"] for s in r.scenarios if s.get("pass") is False]} for r in runs]
    evidence += [{"experiment_id": e.id, "title": e.title, "run_ids": e.run_ids, "result": e.result_summary} for e in executed]
    scen = set(finding.failing_scenarios or [])
    label = f"{impl.name} {impl.version}" if impl else "the implementation"
    if scen & {"trailing_byte", "trailing_garbage", "truncated_signature", "empty_signature", "zero_signature", "corrupted_signature", "random_signature"}:
        category = "input_validation"
        change = (f"In {label}, validate the signature encoding before calling the library: require the exact expected length "
                  f"({(impl.parameters or {}).get('signature_bytes', 'the scheme\'s fixed length')} bytes for {fam or 'this scheme'}), reject any trailing, "
                  "missing or prefixed bytes, and remove any 'normalisation' that truncates or pads signatures. Return invalid on every error path.")
        benefit = "Removes the accepted-malformed-input class entirely; no performance cost beyond a length check."
        tradeoffs = ["Clients that relied on legacy framing (padded signatures) will fail verification and must be fixed at the sender."]
        retest = ["signature-library-core: trailing_byte, trailing_garbage, truncated_signature, empty_signature, zero_signature must be rejected",
                  "malformed-input-sweep: accepted_count must be 0", "No regression in valid_signature, official_vector, timing requirements"]
        observed = (f"{label} accepted signatures with appended data (scenarios: {', '.join(sorted(scen))})."
                    + (f" Experiment '{executed[0].title}': {executed[0].result_summary}" if executed else ""))
    elif finding.kind == "requirement_failure":
        category = "parameter_selection"
        change = (f"Re-evaluate the parameter set / library build for {label} against the failed requirement "
                  f"'{(finding.failing_requirements or [''])[0]}'; consider the catalog alternatives for the same purpose only.")
        benefit, tradeoffs = "Meets the stated operational limit.", ["Changing parameters changes security margin and interoperability; see catalog entries."]
        retest = ["Re-run signature-library-core and compare the failed metric against the requirement"]
        observed = finding.summary
    else:
        category = "other"
        change = f"Review {label} against the source's claims; no code change is recommended until a test reproduces an issue."
        benefit, tradeoffs = "Avoids acting on unreproduced claims.", []
        retest = ["Define a fixture scenario that reproduces the claim before changing code"]
        observed = finding.summary
    kind = "project_specific" if (runs and any(r.classification == "failed" for r in runs)) else ("hypothesis" if finding.kind == "research_claim" else "best_practice")
    return {
        "title": f"{category.replace('_', ' ').title()}: {finding.title}"[:255], "category": category, "guidance_kind": kind,
        "body": {"observed_issue": observed, "supporting_evidence": evidence, "proposed_change": change,
                 "authoritative_guidance": GUIDANCE.get(fam, []) + GENERAL, "expected_benefit": benefit, "tradeoffs": tradeoffs,
                 "applicability_limits": [f"Applies to {label} as imported (source digest {impl.source_digest[:12] if impl and impl.source_digest else 'n/a'}…).",
                                          "Based on the listed runs and experiments only; other code paths were not tested.",
                                          "Not a claim that the implementation is otherwise secure."],
                 "required_retest": retest,
                 "status_note": "A reported fix does not close the finding; the revised version must pass the required retest."},
        "finding_id": finding.id, "target_implementation_id": impl.id if impl else None,
    }
