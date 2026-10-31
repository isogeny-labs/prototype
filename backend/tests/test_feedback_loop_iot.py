"""Required end-to-end demonstration (IoT): the 10 steps of the traceable feedback loop.

Finding -> affected implementation -> proposed change -> human approval -> new implementation version ->
rerun tests -> compare evidence -> close (or stay open on a failed retest) -> export evidence package.
"""
import io
import json
import zipfile
from pathlib import Path

from conftest import ok, new_project

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def load(name):
    return json.loads((SEEDS / name).read_text())


def test_iot_feedback_loop(engineer, reviewer, outsider, admin):
    # 1. Create an IoT project and import its inventory -------------------------------------------
    p = new_project(engineer, reviewer, name="Loop test gateway", kind="iot", support_period_end="2038-12-31", business_purpose="test", platform={})
    pid = p["id"]
    inv = load("iot_inventory.json")
    imp = ok(engineer.post(f"/api/projects/{pid}/inventory/import", json=inv))
    assert len(imp["items"]) == len(inv["items"]) and all(i["provenance"] in ("imported", "user_reported") for i in imp["items"])
    assert imp["platform"]["signature_slot_bytes"] == 2560
    # access control: an outsider sees nothing
    assert outsider.get(f"/api/projects/{pid}/inventory").status_code == 403
    # provenance rule: 'verified' requires a detail
    assert engineer.post(f"/api/projects/{pid}/inventory", json={"category": "algorithm", "name": "X", "provenance": "verified"}).status_code == 400

    # 2. Record baseline and candidate implementations -------------------------------------------
    base = ok(engineer.post(f"/api/projects/{pid}/implementations", json={
        "name": "verifier", "version": "2.3.0", "role": "baseline", "profile_id": "rsa2048_pkcs1v15_sha256", "library": "mbedTLS",
        "library_version": "2.16.12", "source_revision": "a1b2c3d", "delivery_mode": "customer_lab", "target_environment": {"board": "EVT2"}}))
    cand = ok(engineer.post(f"/api/projects/{pid}/implementations", json={
        "name": "verifier", "version": "3.0.0-rc1", "role": "candidate", "profile_id": "ml_dsa_65", "library": "pqm4",
        "source_revision": "9f8e7d6", "delivery_mode": "customer_lab", "parent_id": base["id"], "target_environment": {"board": "EVT2"}}))
    # explicit warning: bootloader supports RSA/ECDSA only and the slot is too small
    assert any("bootloader" in w.lower() for w in cand["compatibility_warnings"])
    assert any("slot" in w.lower() for w in cand["compatibility_warnings"])
    fx = ok(engineer.post(f"/api/projects/{pid}/experiments", json={"name": "fw fixture", "fixture": "firmware_signing",
                                                                   "definition": {"params": {"image_bytes": 8192, "repeat_count": 5}}}))
    hw = ok(engineer.post(f"/api/projects/{pid}/experiments", json={"name": "device lab", "fixture": "external"}))

    # 3. Run the labelled fixture and import hardware measurements -------------------------------
    r_base = ok(engineer.post(f"/api/projects/{pid}/runs", json={"experiment_id": fx["id"], "implementation_id": base["id"], "wait": True}))
    r_cand = ok(engineer.post(f"/api/projects/{pid}/runs", json={"experiment_id": fx["id"], "implementation_id": cand["id"], "wait": True}))
    assert r_base["status"] == "completed" and r_base["provenance"] == "measured" and r_base["overall_pass"] is True
    assert r_cand["status"] == "completed" and r_cand["metrics"]["signature_bytes"] == 3309
    assert r_cand["metrics"]["functional_pass"] == 1  # all rejection scenarios pass...
    hw_cand = ok(engineer.post(f"/api/projects/{pid}/runs/import", json={"experiment_id": hw["id"], "implementation_id": cand["id"],
                                                                        "document": load("hw_candidate_mldsa65.json"), "illustrative": True}))
    assert hw_cand["provenance"] == "illustrative" and any("ILLUSTRATIVE" in l for l in hw_cand["limitations"])

    # 4. Detect a failed requirement ----------------------------------------------------------------
    assert r_cand["overall_pass"] is False
    failed = [x for x in r_cand["requirement_results"] if x["pass"] is False]
    assert [x["metric"] for x in failed] == ["signature_bytes"]
    # device-only requirements are not applied to host measurements
    assert next(x for x in r_cand["requirement_results"] if x["metric"] == "verify_time_ms_median")["pass"] is None
    findings = ok(engineer.get(f"/api/projects/{pid}/findings"))
    slot = next(f for f in findings if f["origin"] == "measurement" and "slot" in f["title"].lower())
    assert slot["status"] == "triage" and cand["id"] in slot["affected_implementation_ids"]
    assert r_cand["id"] in slot["evidence_run_ids"] and hw_cand["id"] in slot["evidence_run_ids"]  # one finding, both runs linked
    # the overview answers "what should engineering do next"
    ov = ok(engineer.get(f"/api/projects/{pid}/overview"))
    assert any(a["kind"] == "finding" for a in ov["next_actions"]) and ov["what_tested"]

    # 5. Add a research finding relevant to the project ---------------------------------------------
    src = ok(engineer.post(f"/api/projects/{pid}/research/sources", json={
        "title": "transition guidance", "content": (SEEDS / "research_docs" / "pqc_transition_guidance.txt").read_text(), "is_demo": True, "wait": True}))
    assert src["review_status"] == "reviewed" and src["extraction_method"] == "rule_based"
    rf = next(f for f in ok(engineer.get(f"/api/projects/{pid}/findings")) if f["origin"] == "research")
    assert rf["status"] == "new" and rf["is_demo"] is True
    assert "RSA" in rf["affected"]["algorithms"] and "mbedTLS" in rf["affected"]["libraries"]
    assert rf["matched_inventory_ids"] and base["id"] in rf["affected_implementation_ids"]
    assert all(c["reproduced"] == "published" for c in rf["claims"])
    # human triage, with gate: cannot jump to action_approved without an approved recommendation
    ok(reviewer.post(f"/api/projects/{pid}/findings/{rf['id']}/status", json={"status": "triage"}))
    ok(reviewer.post(f"/api/projects/{pid}/findings/{rf['id']}/status", json={"status": "relevant"}))
    assert reviewer.post(f"/api/projects/{pid}/findings/{rf['id']}/status", json={"status": "action_approved"}).status_code == 409

    # 6. Generate and review a remediation proposal for the failed requirement ----------------------
    rec = ok(engineer.post(f"/api/projects/{pid}/recommendations/from-finding/{slot['id']}"))
    assert rec["kind"] == "remediation" and rec["status"] == "draft" and rec["catalog_profile_id"] == "ml_dsa_44"
    body = rec["body"]
    for k in ("observed_problem", "supporting_evidence", "proposed_remediation", "what_must_be_retested", "operational_requirements_hold",
              "threat_model", "references", "compatibility", "tradeoffs", "integration", "evidence_needed", "limitations"):
        assert k in body, k
    assert body["operational_requirements_hold"] is True and "category" in body["security_tradeoff"].lower()
    # purpose separation: no KEM / cipher offered as a signature remediation
    assert not any(a["profile_id"].startswith(("kem_", "aead_")) for a in body["alternatives"])
    assert engineer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/implement", json={"name": "verifier", "version": "x"}).status_code == 409
    assert engineer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "approved"}).status_code == 403  # editor cannot approve
    ok(reviewer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "reviewed", "note": "looks right"}))
    ok(reviewer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "approved", "note": "go"}))
    slot = ok(engineer.get(f"/api/projects/{pid}/findings/{slot['id']}"))
    assert slot["status"] == "action_approved" and slot["recommendation_id"] == rec["id"]

    # 7. Approve a new implementation candidate -------------------------------------------------------
    cand2 = ok(engineer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/implement", json={
        "name": "verifier", "version": "3.0.0-rc2", "source_revision": "c0ffee1", "library": "pqm4", "delivery_mode": "customer_lab",
        "target_environment": {"board": "EVT2"}}))
    assert cand2["profile_id"] == "ml_dsa_44" and cand2["parent_id"] == cand["id"] and cand2["recommendation_id"] == rec["id"]
    assert not any("slot" in w.lower() for w in cand2["compatibility_warnings"])  # fits the slot
    assert any("bootloader" in w.lower() for w in cand2["compatibility_warnings"])  # still needs a bootloader change
    ok(engineer.post(f"/api/projects/{pid}/implementations/{cand2['id']}/propose"))
    assert engineer.post(f"/api/projects/{pid}/implementations/{cand2['id']}/decide", json={"decision": "approved"}).status_code == 403  # author/editor
    appr = ok(reviewer.post(f"/api/projects/{pid}/implementations/{cand2['id']}/decide", json={"decision": "approved", "note": "lab only"}))
    assert appr["status"] == "approved"
    assert ok(engineer.get(f"/api/projects/{pid}/implementations/{cand['id']}"))["status"] == "superseded"
    art = ok(engineer.post(f"/api/projects/{pid}/implementations/{cand2['id']}/change-artifact"))
    doc = json.loads(engineer.get(f"/api/projects/{pid}/artifacts/{art['id']}/download").content)
    assert "NOT PERFORMED" in doc["deployment"] and doc["replaces"]["version"] == "3.0.0-rc1"

    # 8. Rerun tests, with a FAILED retest first (must keep the finding open) --------------------------
    bad_doc = load("hw_candidate_mldsa44.json")
    bad_doc["metrics"]["verify_stack_bytes"] = 70000  # exceeds the 40 KB stack limit
    bad_rt = ok(engineer.post(f"/api/projects/{pid}/runs/import", json={"experiment_id": hw["id"], "implementation_id": cand2["id"], "document": bad_doc, "illustrative": True}))
    assert bad_rt["overall_pass"] is False
    rt = ok(engineer.post(f"/api/projects/{pid}/findings/{slot['id']}/retest", json={"run_id": bad_rt["id"]}))
    assert rt["retest_passed"] is False and rt["status"] == "action_approved"  # stays open
    assert reviewer.post(f"/api/projects/{pid}/findings/{slot['id']}/resolve", json={"candidate_run_id": bad_rt["id"], "decision": "close"}).status_code == 409
    # the bad import is corrected by a NEW record (append-only), not an edit
    good_rt = ok(engineer.post(f"/api/projects/{pid}/runs/import", json={"experiment_id": hw["id"], "implementation_id": cand2["id"],
                                                                        "document": load("hw_candidate_mldsa44.json"), "illustrative": True,
                                                                        "supersedes_run_id": bad_rt["id"], "correction_note": "lab re-measured stack with correct paint"}))
    assert good_rt["overall_pass"] is True and good_rt["supersedes_run_id"] == bad_rt["id"]
    assert ok(engineer.get(f"/api/projects/{pid}/runs/{bad_rt['id']}"))["overall_pass"] is False  # old record untouched
    r_cand2 = ok(engineer.post(f"/api/projects/{pid}/runs", json={"experiment_id": fx["id"], "implementation_id": cand2["id"], "wait": True}))
    assert r_cand2["overall_pass"] is True and r_cand2["metrics"]["signature_bytes"] == 2420
    rt = ok(engineer.post(f"/api/projects/{pid}/findings/{slot['id']}/retest", json={"run_id": r_cand2["id"]}))
    assert rt["retest_passed"] is True and rt["status"] == "retested"

    # 9. Compare results and close the finding ---------------------------------------------------------
    cmp_ = ok(engineer.get(f"/api/projects/{pid}/compare", params={"baseline_run_id": r_cand["id"], "candidate_run_id": r_cand2["id"]}))
    assert cmp_["comparable"] is True
    sig = next(m for m in cmp_["metrics"] if m["metric"] == "signature_bytes")
    assert sig["baseline"] == 3309 and sig["candidate"] == 2420 and sig["delta"] == -889
    closed = ok(reviewer.post(f"/api/projects/{pid}/findings/{slot['id']}/resolve", json={"baseline_run_id": r_cand["id"], "candidate_run_id": r_cand2["id"], "decision": "close"}))
    assert closed["status"] == "closed" and [h["status"] for h in closed["status_history"]][-3:] == ["action_approved", "retested", "closed"]
    hist = ok(engineer.get(f"/api/projects/{pid}/revalidation"))
    assert [len(h["runs"]) for h in hist] == [1, 2, 3]  # baseline, rc1 (fixture + hw), rc2 (bad hw, corrected hw, fixture)

    # 10. Export a reproducible evidence package ---------------------------------------------------------
    r = engineer.get(f"/api/projects/{pid}/export")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("manifest.json"))
    import hashlib
    for name, h in manifest["members"].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == h
    runs = json.loads(z.read("records/runs.json"))
    assert len(runs) == 6 and any(x["supersedes_run_id"] == bad_rt["id"] for x in runs)
    assert json.loads(z.read("records/approvals.json"))
    v = ok(engineer.post("/api/export/verify", files={"file": ("ev.zip", r.content, "application/zip")}))
    assert v["ok"] is True
    # audit trail covers the loop
    actions = {e["action"] for e in ok(engineer.get(f"/api/projects/{pid}/audit"))}
    for a in ("inventory.imported", "run.completed", "finding.opened", "recommendation.approved", "implementation.approved", "finding.status", "evidence.exported"):
        assert a in actions, a
