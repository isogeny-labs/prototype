"""Exports: evidence package (zip), engineering handoff (JSON + HTML), compliance evidence template (JSON + HTML).

Printable exports use the supplied LIGHT logo on a white layout. Nothing here is a certification or legal opinion.
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from . import artifacts as artstore
from .config import FRONTEND_DIR
from .models import (Project, InventoryItem, Requirement, Implementation, TestDefinition, Run, Artifact, Recommendation, Approval,
                     Finding, ResearchSource, AttackAssessment, ExperimentProposal, ProtocolVersion, EvidenceBundle, TrustedKey, AuditEvent)

COMPLIANCE_DISCLAIMER = ("This export supports compliance review. It is not a certification, legal opinion or determination that the "
                         "organization meets the referenced requirements.")
COMPLIANCE_TEMPLATE_VERSION = "0.1-provisional"
CONTROLS = [
    {"control_ref": "PCI DSS v4.0.1 Requirement 12.3.3", "official_source": "PCI Security Standards Council, PCI DSS v4.0.1 (June 2024), Requirement 12.3.3",
     "summary": "Cryptographic cipher suites and protocols in use are documented and reviewed at least once every 12 months, including an inventory, "
                "active monitoring of industry trends, and a documented strategy to respond to anticipated changes.",
     "mapping_note": "Provisional: mapping must be reviewed against the official text by a qualified reviewer. The control concerns inventory, "
                     "periodic review and response planning; it does not by itself require post-quantum migration, attack-cost experiments or Isogeny testing."},
    {"control_ref": "Commission Delegated Regulation (EU) 2024/1774, Article 6(4)-(5) (supplementing DORA)",
     "official_source": "Official Journal of the European Union, Delegated Regulation (EU) 2024/1774, Article 6 (encryption and cryptographic controls)",
     "summary": "Financial entities' cryptographic policy shall provide for updating or changing cryptographic technology based on developments in "
                "cryptanalysis, with transparent identification and review of exceptions where leading practices cannot be adopted.",
     "mapping_note": "Provisional: paragraph-level mapping must be confirmed against the official text. The article addresses policy and review of "
                     "cryptographic technology; it does not mandate specific tests or vendors."},
]


def _row(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    out.pop("password_hash", None)
    return out


def _logo_light_b64() -> str:
    p = FRONTEND_DIR / "assets" / "isogeny-labs-light-trimmed.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def _doc_html(title: str, body: str, subtitle: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#1b1f24;background:#fff;margin:0;padding:32px;max-width:1000px}}
header{{display:flex;align-items:center;gap:18px;border-bottom:1px solid #d9dee5;padding-bottom:14px;margin-bottom:18px}}
header img{{height:54px;width:auto}} header .prod{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#5c6773}}
h1{{font-size:20px;margin:0}} h2{{font-size:15px;margin:22px 0 8px;border-bottom:1px solid #e4e8ee;padding-bottom:4px}} h3{{font-size:13px;margin:14px 0 4px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}} th,td{{text-align:left;border-bottom:1px solid #e4e8ee;padding:5px 6px;vertical-align:top}} th{{color:#5c6773}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:11px}} .note{{background:#f6f7f9;border-left:3px solid #9aa7b8;padding:8px 12px;margin:10px 0}}
.disc{{border:1px solid #d9dee5;padding:10px 12px;margin-top:24px;font-size:12px}} ul{{margin:4px 0;padding-left:18px}} @media print{{body{{padding:0}}}}</style></head>
<body><header><img src="data:image/png;base64,{_logo_light_b64()}" alt="Isogeny Labs logo: blue and ivory mathematical linework symbol with the ISOGENY LABS wordmark">
<div><div class="prod">Evidence Lab</div><h1>{html.escape(title)}</h1><div style="color:#5c6773">{html.escape(subtitle)}</div></div></header>{body}</body></html>"""


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return "<p><i>none</i></p>"
    return "<table><tr>" + "".join(f"<th>{_esc(h)}</th>" for _, h in cols) + "</tr>" + "".join(
        "<tr>" + "".join(f"<td>{_esc(r.get(k)) if not isinstance(r.get(k), (list, dict)) else '<ul>' + ''.join('<li>' + _esc(x) + '</li>' for x in (r.get(k) if isinstance(r.get(k), list) else [json.dumps(r.get(k))])) + '</ul>'}</td>" for k, _ in cols) + "</tr>" for r in rows) + "</table>"


# ---------------------------------------------------------------- engineering handoff
def build_handoff(db, project_id: str) -> dict:
    p = db.get(Project, project_id)
    findings = db.scalars(select(Finding).where(Finding.project_id == project_id).order_by(Finding.created_at)).all()
    recs = {r.id: r for r in db.scalars(select(Recommendation).where(Recommendation.project_id == project_id)).all()}
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.project_id == project_id)).all()}
    impls = {i.id: i for i in db.scalars(select(Implementation).where(Implementation.project_id == project_id)).all()}
    bundles = {b.run_id: b for b in db.scalars(select(EvidenceBundle).where(EvidenceBundle.project_id == project_id)).all()}
    items = []
    for f in findings:
        rec = recs.get(f.recommendation_id)
        ev = []
        for rid in f.evidence_run_ids or []:
            r = runs.get(rid)
            if r:
                b = bundles.get(r.id)
                ev.append({"run_id": r.id, "sequence": r.sequence, "implementation": f"{impls[r.implementation_id].name} {impls[r.implementation_id].version}" if r.implementation_id in impls else "?",
                           "execution_mode": r.execution_mode, "classification": r.classification, "labels": [l["label"] for l in r.evidence_labels],
                           "raw_output_sha256": r.artifact_hashes.get("raw_output"), "bundle_id": b.id if b else None, "bundle_sha256": b.envelope_sha256 if b else None})
        items.append({"finding": {"id": f.id, "title": f.title, "kind": f.kind, "status": f.status, "summary": f.summary, "failing_scenarios": f.failing_scenarios,
                                  "failing_requirements": f.failing_requirements, "affected_implementations": [f"{impls[i].name} {impls[i].version}" for i in f.affected_implementation_ids if i in impls],
                                  "reproduction_status": f.reproduction_status, "is_demo": f.is_demo},
                      "recommendation": ({"id": rec.id, "title": rec.title, "category": rec.category, "guidance_kind": rec.guidance_kind, "status": rec.status, **rec.body} if rec else None),
                      "evidence": ev, "retest_plan": (rec.body.get("required_retest") if rec else ["Define the retest once a recommendation exists."]),
                      "revised_implementation": (f"{impls[f.revised_implementation_id].name} {impls[f.revised_implementation_id].version}" if f.revised_implementation_id in impls else None)})
    return {"format": "iel-engineering-handoff/1", "generated_at": datetime.now(timezone.utc).isoformat(), "project": {"id": p.id, "name": p.name, "is_demo": p.is_demo},
            "items": items, "note": "Customers implement changes outside the platform. Nothing here is applied automatically. A reported fix does not "
                                    "resolve a finding until the revised implementation passes the required retest."}


def handoff_html(doc: dict) -> str:
    body = f"<div class='note'>{_esc(doc['note'])}</div>"
    for it in doc["items"]:
        f, rec = it["finding"], it["recommendation"]
        body += f"<h2>{_esc(f['title'])} <small>[{_esc(f['status'])}{' · demonstration' if f['is_demo'] else ''}]</small></h2><p>{_esc(f['summary'])}</p>"
        body += f"<p><b>Kind:</b> {_esc(f['kind'])} · <b>Reproduction status:</b> {_esc(f['reproduction_status'])} · <b>Affected:</b> {_esc(', '.join(f['affected_implementations']))}</p>"
        if rec:
            body += (f"<h3>Recommendation ({_esc(rec['guidance_kind'])}, {_esc(rec['category'])}, review status {_esc(rec['status'])})</h3>"
                     f"<p><b>Observed issue:</b> {_esc(rec.get('observed_issue'))}</p><p><b>Proposed change:</b> {_esc(rec.get('proposed_change'))}</p>"
                     f"<p><b>Authoritative guidance:</b></p><ul>{''.join('<li>' + _esc(g) + '</li>' for g in rec.get('authoritative_guidance', []))}</ul>"
                     f"<p><b>Expected benefit:</b> {_esc(rec.get('expected_benefit'))}</p><p><b>Trade-offs:</b> {_esc('; '.join(rec.get('tradeoffs', [])))}</p>"
                     f"<p><b>Applicability limits:</b></p><ul>{''.join('<li>' + _esc(g) + '</li>' for g in rec.get('applicability_limits', []))}</ul>")
        else:
            body += "<p><i>No recommendation yet.</i></p>"
        body += "<h3>Evidence</h3>" + _table(it["evidence"], [("sequence", "Run #"), ("implementation", "Implementation"), ("execution_mode", "Mode"), ("classification", "Classification"), ("labels", "Labels"), ("raw_output_sha256", "Raw output SHA-256"), ("bundle_sha256", "Bundle SHA-256")])
        body += "<h3>Retest plan</h3><ul>" + "".join(f"<li>{_esc(x)}</li>" for x in it["retest_plan"]) + "</ul>"
        if it["revised_implementation"]:
            body += f"<p><b>Revised implementation linked:</b> {_esc(it['revised_implementation'])}</p>"
    return _doc_html("Engineering handoff", body, f"{doc['project']['name']} · generated {doc['generated_at'][:19]}Z")


# ---------------------------------------------------------------- compliance evidence template
def build_compliance(db, project_id: str, applicability: dict | None = None) -> dict:
    """applicability: {control_ref: {"confirmed": bool, "scope": str, "owner": str, "next_review": str}} supplied by the customer."""
    p = db.get(Project, project_id)
    applicability = applicability or {}
    impls = db.scalars(select(Implementation).where(Implementation.project_id == project_id)).all()
    items = db.scalars(select(InventoryItem).where(InventoryItem.project_id == project_id)).all()
    findings = db.scalars(select(Finding).where(Finding.project_id == project_id)).all()
    recs = {r.id: r for r in db.scalars(select(Recommendation).where(Recommendation.project_id == project_id)).all()}
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.project_id == project_id)).all()}
    sources = db.scalars(select(ResearchSource).where(ResearchSource.project_id == project_id)).all()
    assets = [{"asset": f"{i.name} {i.version}", "purpose": i.purpose, "algorithm": i.algorithm, "library": f"{i.library} {i.library_version}".strip(),
               "usage_location": (i.runtime_environment or {}).get("deployment", i.intended_use or "not stated"), "source_digest": i.source_digest, "status": i.status} for i in impls]
    assets += [{"asset": it.name, "purpose": it.purpose, "version": it.version, "provenance": it.provenance} for it in items if it.category in ("algorithm", "library")]
    controls = []
    for c in CONTROLS:
        a = applicability.get(c["control_ref"], {})
        entries, gaps = [], []
        for f in findings:
            rec = recs.get(f.recommendation_id)
            evidence_ids = [rid for rid in f.evidence_run_ids if rid in runs]
            retests = [runs[rid] for rid in evidence_ids if f.revised_implementation_id and runs[rid].implementation_id == f.revised_implementation_id]
            if not evidence_ids:
                status, reason = "insufficient_evidence", "finding has no linked run evidence"
            elif f.kind == "research_claim" and f.status == "not_relevant":
                status, reason = "not_applicable", "finding triaged as not relevant to this project"
            elif not a.get("confirmed"):
                status, reason = "not_mapped", "customer has not confirmed applicability and scope for this control"
            else:
                status, reason = "mapped", ""
            remaining = []
            if f.status not in ("resolved_within_tested_scope", "not_relevant"):
                remaining.append(f"finding status is '{f.status}'; no valid retest resolves it yet")
            if rec and rec.status != "approved":
                remaining.append(f"recommendation review status is '{rec.status}'")
            if not retests and f.kind != "research_claim":
                remaining.append("no retest run of a revised implementation is linked")
            entries.append({"finding_id": f.id, "title": f.title, "status": status, "status_reason": reason, "evidence_ids": evidence_ids,
                            "research_references": [{"id": f.source_id, "review_date": (f.status_history or [{}])[-1].get("at")}] if f.source_id else [],
                            "recommended_response": (rec.body.get("proposed_change") if rec else None), "rationale": (rec.body.get("observed_issue") if rec else None),
                            "customer_reported_changes": (db.get(Implementation, f.revised_implementation_id).change_report if f.revised_implementation_id else None),
                            "retest_results": [{"run_id": r.id, "classification": r.classification} for r in retests], "remaining_gaps": remaining, "is_demo": f.is_demo})
            gaps += remaining
        controls.append({**c, "template_version": COMPLIANCE_TEMPLATE_VERSION, "mapping_status": "provisional — not yet reviewed against the official text",
                         "customer_confirmed_applicability": bool(a.get("confirmed")), "scope": a.get("scope", "not confirmed"),
                         "responsible_owner": a.get("owner", "not assigned"), "next_review_date": a.get("next_review", "not set"), "entries": entries,
                         "missing_evidence": sorted(set(gaps))})
    return {"format": "iel-compliance-evidence-template/1", "template_version": COMPLIANCE_TEMPLATE_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": COMPLIANCE_DISCLAIMER, "project": {"id": p.id, "name": p.name, "is_demo": p.is_demo}, "cryptographic_assets": assets,
            "research_sources": [{"id": s.id, "title": s.title, "sha256": s.content_sha256, "reviewed": s.review_status, "is_demo": s.is_demo} for s in sources],
            "controls": controls,
            "notes": ["Statuses: mapped | not_mapped | not_applicable | insufficient_evidence. Findings are not forced into both frameworks.",
                      "These controls do not universally require post-quantum cryptography, attack-cost experiments or Isogeny testing."]}


def compliance_html(doc: dict) -> str:
    body = f"<div class='note'><b>Template {_esc(doc['template_version'])}.</b> {_esc(doc['disclaimer'])}</div>"
    body += "<h2>Cryptographic assets</h2>" + _table(doc["cryptographic_assets"], [("asset", "Asset"), ("purpose", "Purpose"), ("algorithm", "Algorithm"), ("library", "Library"), ("usage_location", "Usage location"), ("status", "Status"), ("provenance", "Provenance")])
    for c in doc["controls"]:
        body += (f"<h2>{_esc(c['control_ref'])}</h2><p><b>Official source:</b> {_esc(c['official_source'])}<br><b>Summary (paraphrase):</b> {_esc(c['summary'])}<br>"
                 f"<b>Mapping status:</b> {_esc(c['mapping_status'])} · <b>Applicability confirmed by customer:</b> {'yes' if c['customer_confirmed_applicability'] else 'no'} · "
                 f"<b>Scope:</b> {_esc(c['scope'])} · <b>Owner:</b> {_esc(c['responsible_owner'])} · <b>Next review:</b> {_esc(c['next_review_date'])}</p><div class='note'>{_esc(c['mapping_note'])}</div>")
        body += _table(c["entries"], [("title", "Finding"), ("status", "Mapping"), ("status_reason", "Reason"), ("evidence_ids", "Evidence IDs"), ("recommended_response", "Recommended response"), ("customer_reported_changes", "Customer-reported change"), ("retest_results", "Retest"), ("remaining_gaps", "Remaining gaps")])
        body += "<p><b>Missing evidence identified:</b></p><ul>" + ("".join(f"<li>{_esc(g)}</li>" for g in c["missing_evidence"]) or "<li>none</li>") + "</ul>"
    body += "<div class='disc'>" + _esc(doc["disclaimer"]) + "<br>" + "<br>".join(_esc(n) for n in doc["notes"]) + "</div>"
    return _doc_html("Compliance evidence export", body, f"{doc['project']['name']} · generated {doc['generated_at'][:19]}Z")


# ---------------------------------------------------------------- evidence package
def build_package(db, project_id: str, runner_descriptions: list[dict]) -> tuple[bytes, dict]:
    project = db.get(Project, project_id)
    buf, members = io.BytesIO(), {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name, data):
            z.writestr(name, data)
            members[name] = hashlib.sha256(data).hexdigest()

        def add_json(name, obj):
            add(name, json.dumps(obj, indent=1, sort_keys=True, default=str).encode())
        tables = {n: [_row(x) for x in db.scalars(select(M).where(M.project_id == project_id))] for n, M in (
            ("inventory", InventoryItem), ("requirements", Requirement), ("implementations", Implementation), ("test_definitions", TestDefinition),
            ("runs", Run), ("recommendations", Recommendation), ("approvals", Approval), ("findings", Finding), ("research_sources", ResearchSource),
            ("attack_assessments", AttackAssessment), ("experiment_proposals", ExperimentProposal), ("evidence_bundles", EvidenceBundle), ("audit", AuditEvent))}
        tables["project"] = [_row(project)]
        tables["protocol_versions"] = [_row(x) for x in db.scalars(select(ProtocolVersion)) if db.get(ExperimentProposal, x.proposal_id) and db.get(ExperimentProposal, x.proposal_id).project_id == project_id]
        tables["trusted_keys"] = [_row(x) for x in db.scalars(select(TrustedKey)) if x.project_id in (None, project_id)]
        for name, rows in tables.items():
            add_json(f"records/{name}.json", rows)
        for b in db.scalars(select(EvidenceBundle).where(EvidenceBundle.project_id == project_id)):
            add_json(f"bundles/{b.id}.envelope.json", b.envelope)  # original, unmodified
        art_index = []
        for a in db.scalars(select(Artifact).where(Artifact.project_id == project_id)):
            data = artstore.read(a)
            add(f"artifacts/{a.sha256[:12]}_{a.filename}", data)
            art_index.append({**_row(a), "integrity_ok": hashlib.sha256(data).hexdigest() == a.sha256})
        add_json("records/artifacts.json", art_index)
        add_json("runners.json", runner_descriptions)
        add_json("engineering_handoff.json", build_handoff(db, project_id))
        add("README.txt", (f"Isogeny Evidence Lab — evidence package\nProject: {project.name}\nExported: {datetime.now(timezone.utc).isoformat()}\n\n"
                           "records/*.json      append-only records (runs are never edited; corrections reference supersedes_run_id)\n"
                           "bundles/*.json      original signed DSSE envelopes (verify with iel_tools/verify.py and your trusted keys)\n"
                           "artifacts/          raw outputs, snapshots, imports (file names carry the first 12 hex of the SHA-256)\n"
                           "manifest.json       SHA-256 of every member\n\nHashes support integrity checking, not scientific validity. "
                           "Passing tests is not proof of security.\n").encode())
        z.writestr("manifest.json", json.dumps({"format": "iel-evidence-package/2", "project_id": project_id,
                                                "exported_at": datetime.now(timezone.utc).isoformat(), "members": members}, indent=1, sort_keys=True))
    data = buf.getvalue()
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "members": len(members), "size": len(data)}


def verify_package(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        bad = [n for n, h in manifest["members"].items() if hashlib.sha256(z.read(n)).hexdigest() != h]
    return {"ok": not bad, "bad_members": bad, "members": len(manifest["members"])}
