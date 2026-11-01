"""Recommendation generation from the curated catalog.

Produces complete implementation approaches (not just algorithm names) with every field the UI shows:
what changes & why, threat model, references, compatibility, trade-offs, integration, evidence needed,
limitations, retest plan, operational requirements. Human-review status is tracked on the record.
"""
from __future__ import annotations

from . import catalog

SIZE_METRICS = ("signature_bytes", "public_key_bytes", "key_bytes", "overhead_bytes")
# encoded-size metrics that grow with the signature size but are not catalog fields themselves
SIZE_PROXY_METRICS = ("token_bytes", "update_package_bytes", "update_overhead_bytes")

THREAT_MODELS = {
    "firmware_signing": ("Attacker can supply arbitrary update packages to the device (compromised update server, "
                         "MITM, local access) and wants the bootloader to accept unauthorised firmware. Signing keys are "
                         "assumed to be protected; this does not cover a compromised signing key or bootloader bugs."),
    "token_signing": ("Attacker can observe and replay tokens and wants to forge a token the service accepts. "
                      "Private key assumed protected; does not cover token leakage or authorisation logic bugs."),
    "payload_encryption": ("Attacker can read and modify stored/transmitted payloads and wants to learn or alter content. "
                           "Key management is out of scope of the primitive choice."),
    "key_establishment": "Attacker records traffic (harvest-now-decrypt-later) or actively interferes with key exchange.",
}


def _size_checks(profile: dict, requirements) -> list[dict]:
    """Compare definitional sizes against size requirements (the only thing we know before running)."""
    checks = []
    sizes = profile.get("sizes", {})
    for r in requirements:
        if r.metric in sizes:
            from .evaluate import OPS
            ok = OPS[r.operator](float(sizes[r.metric]), float(r.threshold))
            checks.append({"requirement": r.name, "metric": r.metric, "catalog_value": sizes[r.metric],
                           "threshold": r.threshold, "operator": r.operator, "pass": bool(ok)})
    return checks


def _year(s: str | None) -> int | None:
    try:
        return int(str(s)[:4])
    except Exception:
        return None


def platform_warnings(profile: dict, project, current_profile: dict | None) -> list[str]:
    warnings = []
    plat = project.platform or {}
    boot = (plat.get("bootloader_supported_families") or [])
    fam = profile.get("family")
    if boot and fam not in boot:
        warnings.append(f"The deployed bootloader reports support for {', '.join(boot)} only. Adopting {fam} requires a "
                        "bootloader update; devices whose bootloader is immutable (ROM/OTP) cannot adopt this change "
                        "without hardware replacement.")
    slot = plat.get("signature_slot_bytes")
    sig = profile.get("sizes", {}).get("signature_bytes")
    if slot and sig and sig > slot:
        warnings.append(f"Signature ({sig} B) exceeds the bootloader signature slot ({slot} B); manifest layout and "
                        "bootloader must change.")
    if profile.get("fixture") is None:
        warnings.append("No fixture is available for this profile in the MVP; evidence must be imported from an external run.")
    return warnings


def build_body(profile: dict, project, current: dict | None, requirements, reason: str, kind: str) -> dict:
    purpose = profile["purpose"]
    checks = _size_checks(profile, requirements)
    cur_label = current["label"] if current else "the current implementation"
    tradeoffs = []
    if current:
        cs, ns = current.get("sizes", {}), profile.get("sizes", {})
        for k in SIZE_METRICS:
            if k in cs and k in ns:
                tradeoffs.append(f"{k.replace('_', ' ')}: {cs[k]} B -> {ns[k]} B ({'+' if ns[k] >= cs[k] else ''}{ns[k] - cs[k]} B)")
    if profile["family"] == "ML-DSA":
        tradeoffs.append("Verification on MCUs is typically fast with optimised code, but RAM/stack during verify and flash for the verifier must be measured on the target.")
    if profile["family"] in ("LMS/HSS",):
        tradeoffs.append("Verify-side code is tiny (SHA-256 only) but the signer must manage one-time-key state in an HSM.")
    if profile["family"] == "RSA" and current and current.get("family") == "RSA":
        tradeoffs.append("Larger modulus increases verify time roughly cubically in modulus size for schoolbook implementations.")
    return {
        "what_changes": f"Replace {cur_label} with {profile['label']} for {catalog.PURPOSES.get(purpose, purpose).rstrip(".")}. "
                        f"Library/profile: {', '.join(profile['libraries'][:3])}. The deliverable is a versioned candidate "
                        "implementation plus a proposed change record; nothing is deployed automatically.",
        "why": reason,
        "threat_model": THREAT_MODELS.get(purpose, ""),
        "references": profile["standards"] + ([profile["transition_note"]] if profile.get("transition_note") else []),
        "compatibility": {"libraries": profile["libraries"], "platforms": profile["platforms"],
                          "warnings": platform_warnings(profile, project, current)},
        "tradeoffs": tradeoffs or ["To be established by the benchmark comparison."],
        "integration": profile["implementation_notes"] + [
            "Update the manifest/packaging format and the verifier; keep the old verifier available for rollback testing.",
            "Add the new public key / trust anchor through the existing key-provisioning process (human-controlled; not automated here).",
        ],
        "evidence_needed": [
            "Functional acceptance and rejection scenarios on the reference fixture (measured).",
            "On-target timing and memory from a hardware or lab run (imported), compared against the customer limits.",
            "Independent review of the chosen library version and build flags.",
        ] + (["Catalog sizes already violate a size requirement — see size_checks; expect a failed requirement unless the limit changes."]
             if any(not c["pass"] for c in checks) else []),
        "size_checks": checks,
        "limitations": [
            "Identifying and benchmarking an algorithm does not establish that a specific implementation is secure.",
            "Passing fixture scenarios is not proof of security; side-channel and fault behaviour on the target are not measured here.",
            profile.get("quantum", ""),
        ],
        "retest_plan": ["Re-run the firmware-signing fixture against the new candidate.",
                        "Re-import device measurements for the new candidate.",
                        "Compare baseline vs candidate and re-evaluate every requirement."] if purpose == "firmware_signing" else
                       ["Re-run the application fixture for the new profile.", "Compare against baseline and re-evaluate requirements."],
        "operational_requirements": [f"{r.name}: {r.metric} {r.operator} {r.threshold} {r.unit}" for r in requirements],
        "kind": kind,
    }


def generate_for_project(project, inventory_items, requirements, implementations) -> list[dict]:
    """Return candidate recommendation drafts for every signing/encryption inventory algorithm."""
    out = []
    support_year = _year(project.support_period_end)
    for item in inventory_items:
        if item.category != "algorithm":
            continue
        pid = catalog.guess_profile(item.name, item.parameters, item.purpose)
        cur = catalog.profile(pid) if pid else None
        purpose = item.purpose or (cur or {}).get("purpose")
        if not purpose or purpose not in catalog.PURPOSES:
            continue
        candidates = catalog.profiles_for_purpose(purpose)  # same purpose only — never cross-purpose
        quantum_concern = bool(pid and catalog.quantum_vulnerable(pid) and support_year and support_year > 2030)
        weak = bool(cur and (cur.get("classical_security_bits") or 128) < 128)
        if not quantum_concern and not weak:
            out.append({
                "title": f"No immediate migration recommended for {item.name} ({purpose})",
                "kind": "no_migration", "catalog_profile_id": pid, "purpose": purpose,
                "body": {
                    "what_changes": "Nothing now. Keep the current implementation under continuous assurance.",
                    "why": (f"{cur['label'] if cur else item.name} meets the catalog's baseline for its purpose and the "
                            f"declared support period ({project.support_period_end or 'not set'}) does not extend past the "
                            "NIST IR 8547 draft deprecation horizon, or the algorithm is not quantum-vulnerable."),
                    "threat_model": THREAT_MODELS.get(purpose, ""),
                    "references": (cur or {}).get("standards", []),
                    "compatibility": {"libraries": (cur or {}).get("libraries", []), "platforms": (cur or {}).get("platforms", []), "warnings": []},
                    "tradeoffs": ["None: no change."],
                    "integration": ["Keep library versions patched; re-evaluate when research findings or requirements change."],
                    "evidence_needed": ["A baseline run to anchor future comparisons.", "Library version review."],
                    "limitations": ["Identifying the algorithm says nothing about implementation quality.",
                                    "This verdict is re-opened automatically when a relevant research finding is accepted."],
                    "retest_plan": ["Baseline fixture run; re-run on every library upgrade."],
                    "operational_requirements": [f"{r.name}: {r.metric} {r.operator} {r.threshold} {r.unit}" for r in requirements],
                    "kind": "no_migration",
                },
            })
            continue
        reasons = []
        if weak:
            reasons.append(f"{cur['label']} provides about {cur['classical_security_bits']}-bit classical strength (NIST SP 800-57).")
        if quantum_concern:
            reasons.append(f"The product support period ends {project.support_period_end}, beyond the NIST IR 8547 draft "
                           "timeline (deprecate 112-bit after 2030, disallow quantum-vulnerable signatures after 2035). "
                           "Firmware signed today must be verifiable by devices for the whole support period.")
        reason = " ".join(reasons)
        ranked = []
        for cid, cp in candidates.items():
            if cid == pid:
                continue
            if quantum_concern and catalog.quantum_vulnerable(cid):
                continue  # don't recommend another quantum-vulnerable scheme to solve a transition problem
            prof = {"id": cid, **cp}
            body = build_body(prof, project, cur, requirements, reason, "migration")
            score = sum(1 for c in body["size_checks"] if c["pass"]) - sum(2 for c in body["size_checks"] if not c["pass"])
            score -= 1 if cp.get("fixture") is None else 0
            score -= len(body["compatibility"]["warnings"]) * 0.5
            ranked.append((score, {"title": f"Migrate {item.name} -> {cp['label']} ({purpose})", "kind": "migration",
                                   "catalog_profile_id": cid, "purpose": purpose, "body": body}))
        ranked.sort(key=lambda t: -t[0])
        out.extend([r for _, r in ranked[:3]])
    return out


def remediation_for_finding(finding, project, requirements, target_impl, implementations) -> dict | None:
    """Build an assisted-remediation proposal for a finding tied to a failed requirement or affected implementation."""
    cur_pid = target_impl.profile_id if target_impl else None
    cur = catalog.profile(cur_pid) if cur_pid else None
    purpose = (cur or {}).get("purpose") or (finding.affected or {}).get("purpose")
    if not purpose:
        return None
    failed_metric = (finding.affected or {}).get("metric") or ""
    # which operation does the failed timing/throughput metric concern? (sign_, verify_, encrypt_, decrypt_)
    import re as _re
    _m = _re.match(r"^(sign|verify|encrypt|decrypt)_(time|throughput)", failed_metric)
    perf_op = _m.group(1) if _m else None
    cur_class = (cur or {}).get("perf_class", {}).get(perf_op) if perf_op else None
    reqs = list(requirements)
    options = []
    for cid, cp in catalog.profiles_for_purpose(purpose).items():
        if cid == cur_pid:
            continue
        if cur and catalog.quantum_vulnerable(cid) and not catalog.quantum_vulnerable(cur_pid):
            continue  # do not regress a PQ candidate back to a quantum-vulnerable scheme
        prof = {"id": cid, **cp}
        body = build_body(prof, project, cur, reqs, "", "remediation")
        if failed_metric and any(c["metric"] == failed_metric and not c["pass"] for c in body["size_checks"]):
            continue  # still violates the failed size requirement
        if failed_metric in SIZE_PROXY_METRICS and cur:
            cs, ns = cur.get("sizes", {}).get("signature_bytes"), cp.get("sizes", {}).get("signature_bytes")
            if cs and ns and ns >= cs:
                continue  # an encoded-size metric failed; a candidate with an equal or larger signature cannot improve it
            body["expected_performance_basis"] = (f"'{failed_metric}' includes the encoded signature: catalog signature size {cs} B -> {ns} B. "
                                                  "The requirement must still be confirmed by a run.")
        if perf_op:
            cls = cp.get("perf_class", {}).get(perf_op)
            if cls == "slow" or (cur_class and cls == cur_class):
                continue  # same (or worse) catalog cost class for the failing operation; would likely fail again
            body["expected_performance_basis"] = (f"Catalog cost class for '{perf_op}': {cur_class or 'unknown'} -> {cls}. "
                                                  "This is a qualitative hint; the requirement must be confirmed by a run.")
        score = -len(body["compatibility"]["warnings"]) - (2 if cp.get("fixture") is None else 0)
        if cur and cp.get("family") == cur.get("family") and not perf_op:
            score += 1  # smallest change within the same family (only when performance is not the problem)
        options.append((score, prof, body))
    options.sort(key=lambda t: -t[0])
    if not options:
        return {"title": f"Remediation for: {finding.title}", "kind": "remediation", "catalog_profile_id": None, "purpose": purpose,
                "body": {"what_changes": "No catalog profile satisfies the failed requirement for this purpose.",
                         "why": finding.summary, "observed_problem": finding.summary, "supporting_evidence": finding.evidence_run_ids,
                         "proposed_remediation": "Revisit the requirement (e.g. enlarge the signature slot via a bootloader change) or accept the finding as a known limitation.",
                         "retest": [], "operational_requirements_hold": False, "limitations": ["Human decision required."], "kind": "remediation"}}
    _, best, body = options[0]
    evidence = finding.evidence_run_ids or []
    observed = finding.summary
    body.update({
        "observed_problem": observed,
        "supporting_evidence": evidence,
        "proposed_remediation": f"Create a new candidate implementation using {best['label']} "
                                f"({', '.join(best['libraries'][:2])}), supersede the affected candidate, and retest.",
        "what_must_be_retested": body["retest_plan"] + ([f"Requirement on '{failed_metric}' must pass on the new run."] if failed_metric else []),
        "operational_requirements_hold": all(c["pass"] for c in body["size_checks"]),
        "security_tradeoff": (f"Security category changes from {cur.get('security_category')} to {best.get('security_category')}."
                              if cur and cur.get("security_category") and best.get("security_category") and cur.get("security_category") != best.get("security_category") else ""),
        "alternatives": [{"profile_id": p["id"], "label": p["label"], "warnings": b["compatibility"]["warnings"]} for _, p, b in options[1:4]],
    })
    return {"title": f"Remediation for: {finding.title}", "kind": "remediation", "catalog_profile_id": best["id"],
            "purpose": purpose, "body": body}
