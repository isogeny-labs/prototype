"""Autoresearcher: source extraction, inventory matching, and experiment proposals.

Sources and snapshots are untrusted data: tokenised and pattern-matched, never executed or followed.
Proposals are rule-based unless the optional AI adapter is configured; either way they are labelled and need human
approval before anything runs. Only allowlisted fixtures can execute.
"""
from __future__ import annotations

import re

from . import ai_adapter
from .models import Finding, InventoryItem, Implementation, ResearchSource, ExperimentProposal, Run

ALGO_ALIASES = {
    "RSA": [r"\brsa\b", r"\brsa-?\d{4}\b", r"pkcs ?#?1 ?v1\.5", r"\bpss\b"], "ECDSA": [r"\becdsa\b", r"\bp-?256\b", r"secp256r1"],
    "Ed25519": [r"\bed25519\b", r"\beddsa\b", r"rfc ?8032"], "ML-DSA": [r"\bml-?dsa(-?\d\d)?\b", r"\bdilithium\b", r"fips ?204"],
    "ML-KEM": [r"\bml-?kem\b", r"\bkyber\b", r"fips ?203"], "LMS/HSS": [r"\blms\b", r"\bhss\b", r"sp ?800-208"], "SLH-DSA": [r"\bslh-?dsa\b", r"sphincs"],
    "SHA-1": [r"\bsha-?1\b"], "SHA-256": [r"\bsha-?256\b"], "AES-GCM": [r"\baes-?\d{3}-?gcm\b", r"\bgcm\b"], "ChaCha20-Poly1305": [r"chacha20"],
}
LIB_ALIASES = {
    "mbedTLS": [r"mbed ?tls", r"polarssl"], "wolfSSL": [r"wolfssl"], "OpenSSL": [r"openssl"], "BoringSSL": [r"boringssl"], "liboqs": [r"liboqs"],
    "libsodium": [r"libsodium"], "cryptography": [r"\bpyca\b", r"python cryptography", r"\bcryptography\b"], "PyJWT": [r"pyjwt"],
}
PLATFORM_ALIASES = {"Cortex-M": [r"cortex-?m\d?", r"\bstm32\w*", r"\bmcu\b"], "Linux": [r"\blinux\b"], "x86-64": [r"x86[-_]?64", r"\bx86\b"],
                    "containers": [r"docker", r"kubernetes", r"container"]}
CLAIM_WORDS = r"(attack|vulnerab|forg|recover|break|broke|deprecat|disallow|side-?channel|timing|fault|cve-\d{4}-\d+|reproduc|weakness|flaw|exploit|leak|misuse|malleab|non-?canonical|trailing|lenient|parser|accept)"
REPRO_WORDS = r"(we (independently )?reproduced|independently (reproduced|verified|confirmed)|confirmed by (an )?independent|our reproduction)"
NEGATED_REPRO = r"\b(not|no|never|wasn't|was not|were not|without)\b[^.;]{0,40}(independent|reproduc)"


def _find(aliases, text):
    low = text.lower()
    return [name for name, pats in aliases.items() if any(re.search(p, low) for p in pats)]


def _versions_near_libs(text, libs):
    out, low = set(), text.lower()
    for lib in libs:
        for pat in LIB_ALIASES[lib]:
            for m in re.finditer(pat, low):
                window = low[m.end(): m.end() + 60]
                cmp = re.search(r"(<=?|before|prior to|up to|through)\s*v?(\d+\.\d+(?:\.\d+)?)", window)
                if cmp:
                    out.add(f"{lib} <{'=' if cmp.group(1) in ('<=', 'up to', 'through') else ''} {cmp.group(2)}")
                for v in re.findall(r"(?:<|<=|before|prior to|up to|through|=|\s)\s*v?(\d+\.\d+(?:\.\d+)?)", window):
                    out.add(f"{lib} {v}")
    return sorted(out)


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 20]


def rule_based_extract(text, title_hint=""):
    algos, libs, plats = _find(ALGO_ALIASES, text), _find(LIB_ALIASES, text), _find(PLATFORM_ALIASES, text)
    claims = []
    for s in _sentences(text):
        if re.search(CLAIM_WORDS, s, re.I):
            claims.append({"text": s[:300], "quote": s[:300],
                           "reproduced": "independently_reproduced" if (re.search(REPRO_WORDS, s, re.I) and not re.search(NEGATED_REPRO, s, re.I)) else "published"})
        if len(claims) >= 8:
            break
    first = _sentences(text)[:2]
    return {"title": title_hint or (first[0][:120] if first else "Untitled source"), "summary": " ".join(first)[:600], "claims": claims,
            "algorithms": algos, "libraries": libs, "versions": _versions_near_libs(text, libs), "platforms": plats,
            "uncertainty": "Rule-based extraction (keyword matching). Affected versions and claim strength must be confirmed by a reviewer.",
            "suggested_followup": None}


def match_inventory(ext, items, impls):
    algos = {a.lower() for a in ext.get("algorithms", [])}
    libs = ext.get("libraries", [])
    hit_items, hit_impls, notes = [], [], []

    def algo_hit(name):
        n = (name or "").lower().replace("-", "").replace("_", "")
        return any(a.split("/")[0].replace("-", "") in n for a in algos)

    def lib_hit(name):
        return any(l.lower().split(" ")[0] in (name or "").lower() for l in libs)

    for it in items:
        if (it.category == "algorithm" and algo_hit(it.name)) or (it.category == "library" and lib_hit(it.name)):
            hit_items.append(it.id)
            notes.append(f"Inventory '{it.name}{(' ' + it.version) if it.version else ''}' matches the source.")
    for i in impls:
        if i.status in ("retired",):
            continue
        if algo_hit(i.algorithm) or lib_hit(i.library):
            hit_impls.append(i.id)
    return {"inventory_ids": hit_items, "implementation_ids": hit_impls, "notes": notes}


def review_source(db, source: ResearchSource) -> Finding:
    items = db.query(InventoryItem).filter(InventoryItem.project_id == source.project_id).all()
    impls = db.query(Implementation).filter(Implementation.project_id == source.project_id).all()
    method, ext = "rule_based", None
    if ai_adapter.available():
        parsed = ai_adapter.extract(source.content)
        if parsed:
            ext, method = parsed.model_dump(), "ai_adapter"
    if ext is None:
        ext = rule_based_extract(source.content, source.title)
    m = match_inventory(ext, items, impls)
    relevant = bool(m["inventory_ids"] or m["implementation_ids"])
    f = Finding(project_id=source.project_id, kind="research_claim", origin="research", reproduction_status="literature_claim",
                title=ext["title"][:255], summary=ext["summary"], claims=ext["claims"],
                affected={"algorithms": ext["algorithms"], "libraries": ext["libraries"], "versions": ext["versions"], "platforms": ext["platforms"]},
                matched_inventory_ids=m["inventory_ids"], affected_implementation_ids=m["implementation_ids"],
                relevance=("Matches this project: " + " ".join(m["notes"])) if relevant else "No inventory or implementation matches the source.",
                uncertainty=ext["uncertainty"] + " Claims are as published; nothing here has been reproduced by this platform.",
                status="open", status_history=[{"status": "open", "by": "autoresearcher", "note": f"extraction={method}"}],
                source_id=source.id, is_demo=source.is_demo, extraction_method=method)
    source.review_status, source.extraction_method = "reviewed", method
    db.add(f)
    db.flush()
    return f


# ---------------------------------------------------------------- experiment proposals
def _impl_label(db, iid):
    i = db.get(Implementation, iid) if iid else None
    return f"{i.name} {i.version}" if i else "the affected implementation"


def propose_experiments(db, project, findings, sources) -> list[ExperimentProposal]:
    """Rule-based proposals from open findings and submitted sources. Each proposal is complete but is NOT an experiment
    result: it needs human approval, and only allowlisted fixtures can run."""
    proposals = []
    existing = {(p.finding_id, p.allowlisted_fixture or p.title) for p in db.query(ExperimentProposal).filter(ExperimentProposal.project_id == project.id).all()}
    src_refs = [{"id": s.id, "title": s.title, "sha256": s.content_sha256[:16]} for s in sources]
    for f in findings:
        if f.status in ("resolved_within_tested_scope", "not_relevant"):
            continue
        impl_id = (f.affected_implementation_ids or [None])[0]
        label = _impl_label(db, impl_id)
        if f.kind == "implementation_defect" and any(s in ("trailing_byte", "trailing_garbage", "truncated_signature", "empty_signature", "zero_signature",
                                                           "corrupted_signature") for s in f.failing_scenarios):
            if (f.id, "malformed_input_sweep") in existing:
                continue
            proposals.append(ExperimentProposal(
                project_id=project.id, finding_id=f.id, affected_implementation_id=impl_id,
                title=f"Characterise malformed-signature acceptance in {label}",
                research_question=f"Which malformed signature encodings does {label} accept, and is acceptance a function of length, position or content?",
                motivation=f"The core test showed {label} accepted: {', '.join(f.failing_scenarios)}. A length/variant sweep tells engineering whether the "
                           "defect is a trailing-data tolerance, a length-check omission, or something broader, which changes the fix.",
                source_references=[{"id": f.id, "title": f.title, "kind": "finding"}] + [r for r in src_refs if r["id"] == f.source_id],
                hypothesis="H1: every signature whose first 64 bytes are a valid signature is accepted regardless of appended data; truncated, "
                           "prefixed, empty and zero signatures are rejected. If H1 holds, the defect is confined to trailing-data handling.",
                baseline_controls="Control: the catalog Ed25519 profile (cryptography/OpenSSL) run through the same sweep must accept 0 malformed cases. "
                                  "Baseline: the unmodified valid signature must be accepted by both.",
                procedure="Run the allowlisted fixture malformed_input_sweep against the implementation's source snapshot in the platform sandbox: "
                          "one synthetic key pair, one 256-byte message, variants append_zero/append_random (1..64 bytes), truncate (1..8), prefix (1..8), empty.",
                required_tools=["platform sandbox", "fixture malformed_input_sweep 1.0.0", "source snapshot of the implementation"],
                outcomes={"success": "H1 confirmed: only append variants accepted, all other variants rejected; control accepts none.",
                          "failure": "H1 refuted: truncated/prefixed/zero signatures are also accepted, or the control accepts malformed inputs (fixture problem).",
                          "inconclusive": "Adapter raises on malformed input in the sandbox, or the run hits resource limits."},
                budget={"compute": "single core, < 1 minute", "time": "same day"},
                required_artifacts=["raw fixture output (JSON)", "per-case acceptance table", "signed platform evidence bundle"],
                safety_boundaries="Synthetic keys and messages only; no customer keys; sandbox with networking disabled; allowlisted fixture only.",
                can_establish="The set of malformed encodings accepted by this specific adapter version under this fixture.",
                cannot_establish="Whether the scheme itself is weak, whether other code paths validate inputs, or production exploitability.",
                allowlisted_fixture="malformed_input_sweep", parameters={"max_extra_bytes": 64, "seed": 3}, target_class="owned",
                status="proposed", claim_status="proposal"))
        elif f.kind == "research_claim" and re.search(r"(timing|side-?channel)", (f.summary + " ".join(c["text"] for c in f.claims)), re.I):
            key = (f.id, f"Timing-variance measurement for {label}")
            if key in existing:
                continue
            proposals.append(ExperimentProposal(
                project_id=project.id, finding_id=f.id, affected_implementation_id=impl_id, title=f"Timing-variance measurement for {label}",
                research_question="Does verification time depend on the signature or message content in a statistically detectable way?",
                motivation="The submitted source claims timing behaviour matters for this library family; the current fixture reports distributions only.",
                source_references=[r for r in src_refs if r["id"] == f.source_id] or src_refs[:1],
                hypothesis="H1: verify latency distributions for valid vs. invalid signatures are statistically indistinguishable (Welch t-test p > 0.01, n=10k).",
                baseline_controls="Baseline: catalog profile of the same algorithm. Control: identical inputs replayed in shuffled order.",
                procedure="Requires a timing harness that is not yet allowlisted; this is a PROPOSAL ONLY until a fixture exists.",
                required_tools=["timing harness (not available)", "quiet host"], outcomes={"success": "No detectable dependence at the stated power.",
                "failure": "Detectable dependence.", "inconclusive": "Host noise exceeds effect size."},
                budget={"compute": "single core, ~10 minutes", "time": "after harness is approved"},
                required_artifacts=["timing samples", "statistical summary"], safety_boundaries="Synthetic inputs; no production hosts.",
                can_establish="Host-level timing variance of this adapter.", cannot_establish="Exploitability over a network or on other hardware.",
                allowlisted_fixture=None, parameters={}, target_class="owned", status="proposed", claim_status="proposal"))
    for p in proposals:
        db.add(p)
    db.flush()
    for p in proposals:
        if p.finding_id:
            f = db.get(Finding, p.finding_id)
            f.experiment_proposal_ids = (f.experiment_proposal_ids or []) + [p.id]
    return proposals


def summarize_experiment(run: Run, proposal: ExperimentProposal) -> str:
    if run.status != "completed":
        return "inconclusive: " + "; ".join(run.failures[:2])
    m = run.metrics
    if proposal.allowlisted_fixture == "malformed_input_sweep":
        bv = m.get("by_variant", {})
        acc = {v: d for v, d in bv.items() if d.get("accepted")}
        if not acc:
            return "No malformed encoding accepted (0 of %d cases)." % m.get("total_cases", 0)
        only_append = set(acc) <= {"append", "append_random"}
        return (f"{m.get('accepted_count')} of {m.get('total_cases')} malformed cases accepted; classes: " +
                ", ".join(f"{v} {d['accepted']}/{d['total']}" for v, d in acc.items()) +
                (". H1 confirmed: acceptance confined to trailing data." if only_append else ". H1 refuted: acceptance is broader than trailing data."))
    return f"completed; functional_pass={m.get('functional_pass')}"
