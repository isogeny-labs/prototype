"""Auto-researcher: extraction, inventory matching, finding creation.

Documents are untrusted data. The rule-based extractor only tokenises and pattern-matches; it never evaluates
or executes any content. The optional AI adapter returns a validated schema which is then matched the same way.
"""
from __future__ import annotations

import re

from . import ai_adapter
from .models import Finding, InventoryItem, Implementation, ResearchSource

ALGO_ALIASES = {
    "RSA": [r"\brsa\b", r"\brsa-?\d{4}\b", r"pkcs ?#?1 ?v1\.5", r"\bpss\b"],
    "ECDSA": [r"\becdsa\b", r"\bp-?256\b", r"secp256r1"],
    "Ed25519": [r"\bed25519\b", r"\beddsa\b"],
    "ML-DSA": [r"\bml-?dsa(-?\d\d)?\b", r"\bdilithium\b", r"fips ?204"],
    "ML-KEM": [r"\bml-?kem\b", r"\bkyber\b", r"fips ?203"],
    "LMS/HSS": [r"\blms\b", r"\bhss\b", r"sp ?800-208"],
    "SLH-DSA": [r"\bslh-?dsa\b", r"sphincs"],
    "SHA-1": [r"\bsha-?1\b"],
    "SHA-256": [r"\bsha-?256\b"],
    "AES-GCM": [r"\baes-?\d{3}-?gcm\b", r"\bgcm\b"],
    "ChaCha20-Poly1305": [r"chacha20"],
}
LIB_ALIASES = {
    "mbedTLS": [r"mbed ?tls", r"polarssl"], "wolfSSL": [r"wolfssl"], "OpenSSL": [r"openssl"],
    "BoringSSL": [r"boringssl"], "liboqs": [r"liboqs"], "pqm4": [r"pqm4"], "libsodium": [r"libsodium"],
    "cryptography (Python)": [r"\bpyca\b", r"python cryptography", r"cryptography \d"],
    "PyJWT": [r"pyjwt"], "dilithium-py": [r"dilithium-py"],
}
PLATFORM_ALIASES = {
    "Cortex-M": [r"cortex-?m\d?", r"\bstm32\w*", r"nrf52", r"\bmcu\b"], "ESP32": [r"esp32"],
    "Linux": [r"\blinux\b"], "x86-64": [r"x86[-_]?64", r"\bx86\b"], "containers": [r"docker", r"kubernetes", r"container"],
}
CLAIM_WORDS = r"(attack|vulnerab|forg|recover|break|broke|deprecat|disallow|side-?channel|timing|fault|cve-\d{4}-\d+|reproduc|weakness|flaw|exploit|leak|misuse|downgrade|withdraw|retire|key recovery|collision)"
REPRO_WORDS = r"(we (independently )?reproduced|independently (reproduced|verified|confirmed)|confirmed by (an )?independent|our reproduction)"
NEGATED_REPRO = r"\b(not|no|never|wasn't|was not|were not|without)\b[^.;]{0,40}(independent|reproduc)"
VERSION_RE = r"(?:v|version\s*)?(\d+\.\d+(?:\.\d+)?)"


def _find(aliases: dict, text: str) -> list[str]:
    low = text.lower()
    return [name for name, pats in aliases.items() if any(re.search(p, low) for p in pats)]


def _versions_near_libs(text: str, libs: list[str]) -> list[str]:
    out = set()
    low = text.lower()
    for lib in libs:
        for pat in LIB_ALIASES[lib]:
            for m in re.finditer(pat, low):
                window = low[m.end(): m.end() + 60]
                for v in re.findall(r"(?:<|<=|before|prior to|up to|through|=|\s)\s*v?(\d+\.\d+(?:\.\d+)?)", window):
                    out.add(f"{lib} {v}")
                cmp = re.search(r"(<=?|before|prior to|up to|through)\s*v?(\d+\.\d+(?:\.\d+)?)", window)
                if cmp:
                    out.add(f"{lib} <{'=' if cmp.group(1) in ('<=', 'up to', 'through') else ''} {cmp.group(2)}")
    return sorted(out)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 20]


def rule_based_extract(text: str, title_hint: str = "") -> dict:
    algos, libs, plats = _find(ALGO_ALIASES, text), _find(LIB_ALIASES, text), _find(PLATFORM_ALIASES, text)
    claims = []
    for s in _sentences(text):
        if re.search(CLAIM_WORDS, s, re.I):
            claims.append({"text": s[:300], "quote": s[:300],
                           "reproduced": "independently_reproduced" if (re.search(REPRO_WORDS, s, re.I) and not re.search(NEGATED_REPRO, s, re.I)) else "published"})
        if len(claims) >= 8:
            break
    first = _sentences(text)[:2]
    return {
        "title": title_hint or (first[0][:120] if first else "Untitled source"),
        "summary": " ".join(first)[:600],
        "claims": claims, "algorithms": algos, "libraries": libs,
        "versions": _versions_near_libs(text, libs), "platforms": plats,
        "uncertainty": ("Rule-based extraction: keyword matching only; affected versions and the strength of each claim "
                        "must be confirmed by a human reviewer against the source."),
        "suggested_followup": None,
    }


def _version_tuple(v: str):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
    except Exception:
        return ()


def _version_affected(item_version: str | None, constraints: list[str], lib: str) -> bool | None:
    """True/False when a constraint for `lib` can be evaluated against the inventory version, else None."""
    if not item_version:
        return None
    iv = _version_tuple(item_version)
    verdict = None
    for c in constraints:
        if not c.lower().startswith(lib.lower()):
            continue
        m = re.search(r"(<=|<)\s*([\d.]+)", c)
        if m and iv:
            bound = _version_tuple(m.group(2))
            n = min(len(iv), len(bound))
            hit = iv[:n] < bound[:n] or (m.group(1) == "<=" and iv[:n] == bound[:n])
            verdict = hit if verdict is None else (verdict or hit)
        else:
            m2 = re.search(r"\s([\d.]+)$", c)
            if m2 and iv and _version_tuple(m2.group(1))[:len(iv)] == iv[:len(_version_tuple(m2.group(1)))]:
                verdict = True
    return verdict


def match_inventory(extraction: dict, items: list[InventoryItem], impls: list[Implementation]) -> dict:
    matched_items, matched_impls, notes = [], [], []
    algos = {a.lower() for a in extraction.get("algorithms", [])}
    libs = extraction.get("libraries", [])
    versions = extraction.get("versions", [])

    def algo_hit(name: str) -> bool:
        n = (name or "").lower()
        return any(a.split("/")[0].replace("-", "") in n.replace("-", "").replace("_", "") for a in algos)

    for it in items:
        hit = False
        if it.category == "algorithm" and algo_hit(it.name):
            hit = True
            notes.append(f"Inventory algorithm '{it.name}' matches an algorithm named in the source.")
        if it.category == "library" and any(l.lower().split(" ")[0] in it.name.lower() for l in libs):
            lib = next(l for l in libs if l.lower().split(" ")[0] in it.name.lower())
            va = _version_affected(it.version, versions, lib)
            if va is False:
                notes.append(f"Library '{it.name} {it.version}' is named but the inventory version is outside the stated affected range.")
            else:
                hit = True
                notes.append(f"Library '{it.name} {it.version or ''}' matches; version check: "
                             f"{'affected' if va else 'range not stated — verify manually'}.")
        if hit:
            matched_items.append(it.id)
    for impl in impls:
        if impl.status in ("rejected", "retired"):
            continue
        if algo_hit(impl.algorithm) or algo_hit(impl.profile_id or ""):
            matched_impls.append(impl.id)
        elif impl.library and any(l.lower().split(" ")[0] in impl.library.lower() for l in libs):
            matched_impls.append(impl.id)
    return {"inventory_ids": matched_items, "implementation_ids": matched_impls, "notes": notes}


def propose_followup(extraction: dict, match: dict) -> dict:
    if not match["implementation_ids"] and not match["inventory_ids"]:
        return {"type": "none", "description": "No inventory match; no follow-up proposed. Triage may mark this not relevant."}
    txt = " ".join(c["text"] for c in extraction.get("claims", [])).lower()
    if re.search(r"(timing|side-?channel|fault|forg|parser|padding|malformed)", txt):
        return {"type": "experiment", "description": "Add a fixture scenario or test harness that exercises the described input/behaviour "
                                                    "against the affected implementation and record the result as evidence."}
    if re.search(r"(deprecat|disallow|transition|withdraw|retire)", txt):
        return {"type": "implementation_review", "description": "Review whether the affected implementation remains acceptable for the product "
                                                               "support period and generate a migration recommendation if not."}
    return {"type": "implementation_review", "description": "Human review of the affected implementation against the source's claims."}


def review_source(db, source: ResearchSource) -> Finding:
    items = db.query(InventoryItem).filter(InventoryItem.project_id == source.project_id).all()
    impls = db.query(Implementation).filter(Implementation.project_id == source.project_id).all()
    method = "rule_based"
    ext = None
    if ai_adapter.available():
        parsed = ai_adapter.extract(source.content)
        if parsed:
            ext = parsed.model_dump()
            method = "ai_adapter"
    if ext is None:
        ext = rule_based_extract(source.content, source.title)
    match = match_inventory(ext, items, impls)
    followup = propose_followup(ext, match)
    relevant = bool(match["inventory_ids"] or match["implementation_ids"])
    relevance = (("Matches project inventory: " + " ".join(match["notes"])) if relevant
                 else "No inventory or implementation in this project matches the algorithms/libraries named in the source.")
    finding = Finding(
        project_id=source.project_id, source_id=source.id, origin="research", title=ext["title"][:255],
        summary=ext["summary"], claims=ext["claims"],
        affected={"algorithms": ext["algorithms"], "libraries": ext["libraries"], "versions": ext["versions"], "platforms": ext["platforms"]},
        matched_inventory_ids=match["inventory_ids"], affected_implementation_ids=match["implementation_ids"],
        relevance=relevance, uncertainty=ext["uncertainty"] + (" Claims are as published; none have been reproduced by this platform."
                                                                 if all(c["reproduced"] == "published" for c in ext["claims"]) else ""),
        proposed_followup=followup, status="new", status_history=[{"status": "new", "by": "auto-researcher", "note": f"extraction={method}"}],
        is_demo=source.is_demo, extraction_method=method)
    source.review_status = "reviewed"
    source.extraction_method = method
    db.add(finding)
    db.flush()
    return finding
