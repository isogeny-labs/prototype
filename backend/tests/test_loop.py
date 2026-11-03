"""Required 12-step demonstration and the automated acceptance checks, through the HTTP API."""
import base64
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from conftest import ok, new_project

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / "seeds"
sys.path.insert(0, str(ROOT))
from iel_tools import attest  # noqa: E402

B64_V10 = base64.b64encode((SEEDS / "adapters" / "acme_signer_v1_0.py").read_bytes()).decode()
B64_V11 = base64.b64encode((SEEDS / "adapters" / "acme_signer_v1_1.py").read_bytes()).decode()


def manifest(version):
    m = json.loads((SEEDS / f"sample_manifest_v{version.replace('.', '_')}.json").read_text())
    m["adapter_kind"] = "module"
    return m


def runner_bundle(project_id, key_path, out, adapter=SEEDS / "adapters" / "acme_signer_v1_0.py", version="1.0.0", run_id=None, test_version="1"):
    cmd = [sys.executable, str(ROOT / "iel_tools" / "runner.py"), "run", "--project", project_id, "--impl-name", "acme-signer", "--impl-version", version,
           "--adapter", str(adapter), "--key", str(key_path), "--out", str(out), "--params", '{"repeat_count": 10}', "--test-version", test_version,
           "--fixture-dir", str(ROOT / "backend" / "fixtures")]
    if run_id:
        cmd += ["--run-id", run_id]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return json.loads(Path(out).read_text())


def test_full_loop(engineer, reviewer, admin, outsider, tmp_path):
    # 1. import an existing signature implementation --------------------------------------------------
    p = new_project(engineer, reviewer, name="Loop test", intended_use="API signing")
    pid = p["id"]
    assert outsider.get(f"/api/projects/{pid}/overview").status_code == 403
    assert engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": manifest("1.0"), "source_snapshot_b64": base64.b64encode(b"-----BEGIN PRIVATE KEY-----\nabc").decode(), "source_snapshot_filename": "adapter.py"}).status_code == 400
    v10 = ok(engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": manifest("1.0"), "source_snapshot_b64": B64_V10, "source_snapshot_filename": "adapter.py"}))
    assert v10["compatibility"]["status"] == "compatible" and v10["source_digest"] and v10["adapter_kind"] == "module"
    assert v10["latest_classification"] == "not_tested"
    tests = ok(engineer.get(f"/api/projects/{pid}/tests"))
    core = next(t for t in tests if t["test_id"] == "signature-library-core")
    # importing code did not execute it: no runs exist
    assert ok(engineer.get(f"/api/projects/{pid}/runs")) == []
    # 2. run actual correctness and performance tests (platform sandbox) --------------------------------
    pf = ok(engineer.get(f"/api/projects/{pid}/tests/{core['id']}/preflight", params={"implementation_id": v10["id"]}))
    assert pf["can_execute"] and pf["networking"] == "disabled" and pf["result_provenance"] == "measured" and pf["resource_limits"]["memory_mb"]
    r1 = ok(engineer.post(f"/api/projects/{pid}/runs", json={"test_definition_id": core["id"], "implementation_id": v10["id"], "wait": True}))
    assert r1["status"] == "completed" and r1["execution_mode"] == "platform_sandbox" and r1["provenance"] == "measured"
    assert "unshare" in r1["environment"]["isolation"] or "socket-block" in r1["environment"]["isolation"]
    assert r1["metrics"]["official_vectors"] == "pass" and r1["metrics"]["verify_time_ms_median"] > 0
    # 3. seeded defect identified -----------------------------------------------------------------------
    assert r1["classification"] == "failed"
    failing = {s["id"] for s in r1["scenarios"] if s["pass"] is False}
    assert failing == {"trailing_byte", "trailing_garbage"}
    assert r1["bundle_id"]  # platform-signed bundle
    findings = ok(engineer.get(f"/api/projects/{pid}/findings"))
    defect = next(f for f in findings if f["kind"] == "implementation_defect")
    assert defect["status"] == "open" and defect["reproduction_status"] == "reproduced" and set(defect["failing_scenarios"]) == failing
    assert not [f for f in findings if f["kind"] == "requirement_failure"]  # derived pass-flags do not duplicate the defect
    ov = ok(engineer.get(f"/api/projects/{pid}/overview"))
    assert ov["coverage"][0]["tests"]["signature-library-core"]["status"] == "failed"
    # 4. generate an experiment proposal ------------------------------------------------------------------
    ok(engineer.post(f"/api/projects/{pid}/research/sources", json={"title": "src", "content": (SEEDS / "research_docs" / "noncanonical_signature_encodings.txt").read_text(), "wait": True}))
    props = ok(engineer.post(f"/api/projects/{pid}/experiments/propose"))
    prop = next(x for x in props if x["allowlisted_fixture"] == "malformed_input_sweep")
    for k in ("research_question", "motivation", "hypothesis", "baseline_controls", "procedure", "safety_boundaries", "can_establish", "cannot_establish"):
        assert prop[k]
    assert prop["outcomes"]["success"] and prop["outcomes"]["failure"] and prop["outcomes"]["inconclusive"] and prop["budget"] and prop["required_artifacts"]
    assert prop["claim_status"] == "proposal" and prop["status"] == "proposed"
    # 5. approve and execute it ----------------------------------------------------------------------------
    assert engineer.post(f"/api/projects/{pid}/experiments/{prop['id']}/execute").status_code == 409  # not approved
    assert engineer.post(f"/api/projects/{pid}/experiments/{prop['id']}/decide", json={"decision": "approved"}).status_code == 403  # editor
    ap = ok(reviewer.post(f"/api/projects/{pid}/experiments/{prop['id']}/decide", json={"decision": "approved", "note": "ok"}))
    assert ap["current_protocol_version"] == 1
    ex = ok(engineer.post(f"/api/projects/{pid}/experiments/{prop['id']}/execute?wait=true"))
    assert ex["status"] == "executed" and ex["claim_status"] == "reproduced" and "H1 confirmed" in ex["result_summary"]
    # amendment creates protocol v2 without overwriting v1 or results
    ok(engineer.post(f"/api/projects/{pid}/experiments/{prop['id']}/amend", json={"changes": {"parameters": {"max_extra_bytes": 8, "seed": 3}}, "note": "smaller sweep"}))
    ok(reviewer.post(f"/api/projects/{pid}/experiments/{prop['id']}/decide", json={"decision": "approved"}))
    d = ok(engineer.get(f"/api/projects/{pid}/experiments/{prop['id']}"))
    assert [v["version"] for v in d["protocol_versions"]] == [1, 2] and d["protocol_versions"][0]["protocol"]["parameters"]["max_extra_bytes"] == 64 and len(d["runs"]) == 1
    # 6. evidence-backed recommendation ----------------------------------------------------------------------
    rec = ok(engineer.post(f"/api/projects/{pid}/recommendations/from-finding/{defect['id']}"))
    assert rec["guidance_kind"] == "project_specific" and rec["category"] == "input_validation"
    b = rec["body"]
    for k in ("observed_issue", "supporting_evidence", "proposed_change", "authoritative_guidance", "expected_benefit", "tradeoffs", "applicability_limits", "required_retest"):
        assert b[k]
    assert any(e.get("experiment_id") for e in b["supporting_evidence"]) and any("RFC 8032" in g for g in b["authoritative_guidance"])
    assert engineer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "approved"}).status_code == 403
    ok(reviewer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "approved"}))
    assert ok(engineer.get(f"/api/projects/{pid}/findings/{defect['id']}"))["status"] == "recommendation_proposed"
    # 7. import a separately corrected version --------------------------------------------------------------
    m11 = manifest("1.1")
    m11.update({"parent_id": v10["id"], "recommendation_id": rec["id"]})
    v11 = ok(engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": m11, "source_snapshot_b64": B64_V11, "source_snapshot_filename": "adapter.py"}))
    assert v11["source_digest"] != v10["source_digest"]
    assert ok(engineer.get(f"/api/projects/{pid}/implementations/{v10['id']}"))["status"] == "superseded"
    f = ok(engineer.get(f"/api/projects/{pid}/findings/{defect['id']}"))
    assert f["status"] == "awaiting_retest" and f["revised_implementation_id"] == v11["id"]
    # a reported fix does not resolve the finding; a failed retest keeps it open
    assert reviewer.post(f"/api/projects/{pid}/findings/{defect['id']}/status", json={"status": "resolved_within_tested_scope"}).status_code == 409
    bad = ok(engineer.post(f"/api/projects/{pid}/runs/import-results", json={"implementation_id": v11["id"], "test_definition_id": core["id"],
                                                                              "document": {"fixture": "signature_library", "fixture_version": "x", "status": "completed", "metrics": {},
                                                                                           "scenarios": [{"id": "trailing_byte", "expected": "reject", "observed": "accept", "pass": False}]}}))
    rt = ok(engineer.post(f"/api/projects/{pid}/findings/{defect['id']}/retest", json={"run_id": bad["id"]}))
    assert rt["status"] == "still_failing" and rt["retest"]["still_failing"] == ["trailing_byte"]
    r_old = ok(engineer.post(f"/api/projects/{pid}/runs", json={"test_definition_id": core["id"], "implementation_id": v10["id"], "wait": True}))
    assert engineer.post(f"/api/projects/{pid}/findings/{defect['id']}/retest", json={"run_id": r_old["id"]}).status_code == 409  # wrong version
    # 8. retest and compare ------------------------------------------------------------------------------------
    r2 = ok(engineer.post(f"/api/projects/{pid}/runs", json={"test_definition_id": core["id"], "implementation_id": v11["id"], "wait": True}))
    assert r2["classification"] == "passed_defined_checks"
    rt = ok(engineer.post(f"/api/projects/{pid}/findings/{defect['id']}/retest", json={"run_id": r2["id"]}))
    assert rt["status"] == "resolved_within_tested_scope" and set(rt["retest"]["fixed"]) == failing and rt["retest"]["new_regressions"] == []
    cmp_ = ok(engineer.get(f"/api/projects/{pid}/compare", params={"baseline_run_id": r1["id"], "candidate_run_id": r2["id"]}))
    assert cmp_["comparable"] and set(cmp_["fixed"]) == failing and cmp_["new_regressions"] == []
    ov = ok(engineer.get(f"/api/projects/{pid}/overview"))
    assert ov["changes_since_previous"]["test_outcomes"]["signature-library-core"]["fixed"]
    assert defect["id"] not in [x["id"] for x in ov["open_findings"]]
    # the deliberately failing imported document for 1.1.0 opened its own (imported) finding — imported failures are not hidden
    assert any(x["kind"] == "implementation_defect" and x["id"] != defect["id"] for x in ov["open_findings"])
    # 9. export handoff + signed evidence bundle ---------------------------------------------------------------
    hand = ok(engineer.get(f"/api/projects/{pid}/export/handoff"))
    item = next(i for i in hand["items"] if i["finding"]["id"] == defect["id"])
    assert item["recommendation"]["guidance_kind"] == "project_specific" and item["retest_plan"] and item["revised_implementation"]
    assert "Isogeny" in engineer.get(f"/api/projects/{pid}/export/handoff", params={"format": "html"}).text
    run2 = ok(engineer.get(f"/api/projects/{pid}/runs/{r2['id']}"))
    bundle_art = run2["bundle"]["bundle_artifact"]
    bundle = json.loads(engineer.get(f"/api/projects/{pid}/artifacts/{bundle_art['id']}/download").content)
    assert bundle["format"] == attest.BUNDLE_FORMAT
    # 10. verify with the standalone verifier --------------------------------------------------------------------
    pk = ok(engineer.get("/api/platform-key"))
    (tmp_path / "b.json").write_text(json.dumps(bundle))
    (tmp_path / "platform.pub").write_text(pk["public_key_pem"])
    v = subprocess.run([sys.executable, str(ROOT / "iel_tools" / "verify.py"), str(tmp_path / "b.json"), "--trusted-key", str(tmp_path / "platform.pub"), "--json"], capture_output=True, text=True)
    assert v.returncode == 0, v.stdout + v.stderr
    rep = json.loads(v.stdout)
    assert rep["ok"] and rep["statement"]["run_id"] == r2["id"] and rep["statement"]["classification"] == "passed_defined_checks"
    # tampering => verification failure (artifact)
    t = json.loads(json.dumps(bundle))
    t["artifacts"]["raw_output.json"] = base64.b64encode(base64.b64decode(t["artifacts"]["raw_output.json"]) + b" ").decode()
    (tmp_path / "t.json").write_text(json.dumps(t))
    assert subprocess.run([sys.executable, str(ROOT / "iel_tools" / "verify.py"), str(tmp_path / "t.json"), "--trusted-key", str(tmp_path / "platform.pub")], capture_output=True).returncode == 1
    # tampering => verification failure (statement)
    t2 = json.loads(json.dumps(bundle))
    stmt = json.loads(base64.b64decode(t2["envelope"]["payload"]))
    stmt["predicate"]["results"]["classification"] = "passed_defined_checks_forged"
    t2["envelope"]["payload"] = base64.b64encode(json.dumps(stmt, sort_keys=True, separators=(",", ":")).encode()).decode()
    (tmp_path / "t2.json").write_text(json.dumps(t2))
    assert subprocess.run([sys.executable, str(ROOT / "iel_tools" / "verify.py"), str(tmp_path / "t2.json"), "--trusted-key", str(tmp_path / "platform.pub")], capture_output=True).returncode == 1
    # 11. import a customer-side runner bundle ----------------------------------------------------------------------
    subprocess.run([sys.executable, str(ROOT / "iel_tools" / "runner.py"), "keygen", "--out", str(tmp_path / "rk.pem")], check=True, capture_output=True)
    pem = (tmp_path / "rk.pem.pub").read_text()
    assert admin.post(f"/api/projects/{pid}/trusted-keys", json={"name": "lab runner", "public_key_pem": (tmp_path / "rk.pem").read_text()}).status_code == 400  # private key refused
    cb = runner_bundle(pid, tmp_path / "rk.pem", tmp_path / "cb.json")
    # unexpected signer fails the trust-policy check (key not registered yet)
    r = engineer.post(f"/api/projects/{pid}/runs/import-bundle", json={"bundle": cb})
    assert r.status_code == 422 and "trust policy" in r.text
    assert engineer.post(f"/api/projects/{pid}/trusted-keys", json={"name": "lab runner", "public_key_pem": pem}).status_code == 403  # owner only
    ok(admin.post(f"/api/projects/{pid}/trusted-keys", json={"name": "lab runner", "public_key_pem": pem}))
    imp = ok(engineer.post(f"/api/projects/{pid}/runs/import-bundle", json={"bundle": cb}))
    assert imp["execution_mode"] == "customer_runner" and imp["classification"] == "failed"
    labels = {l["label"] for l in imp["evidence_labels"]}
    assert labels == {"imported", "hash_checked", "signature_verified"}  # signed imports are NOT labelled independently replayed
    assert imp["received_at"] and imp["runner_reported_executed_at"] and imp["received_at"] != imp["runner_reported_executed_at"]
    assert imp["import_info"]["duplicate_of"] is None
    assert any("superseded" in s for s in imp["import_info"]["stale"])  # 1.0.0 is superseded by now: flagged, not hidden
    bd = ok(engineer.get(f"/api/projects/{pid}/bundles/{imp['bundle_id']}"))
    assert bd["countersignature"]["payloadType"] == attest.PAYLOAD_TYPE and bd["live_verification"]["ok"]
    assert "NOT an independent endorsement" in json.dumps(attest.decode_statement(bd["countersignature"]))
    # both execution modes produce compatible evidence (same schema, comparable)
    cmp2 = ok(engineer.get(f"/api/projects/{pid}/compare", params={"baseline_run_id": r1["id"], "candidate_run_id": imp["id"]}))
    assert {s["id"] for s in cmp2["scenarios"]} == {s["id"] for s in r1["scenarios"]} and cmp2["previously_failing_now"]
    assert any("execution modes differ" in l for l in cmp2["comparison_limits"])
    # duplicate runs are not counted twice
    dup = ok(engineer.post(f"/api/projects/{pid}/runs/import-bundle", json={"bundle": cb}))
    assert dup["duplicate_of_run_id"] == imp["id"]
    counts = next(x for x in ok(engineer.get("/api/projects")) if x["id"] == pid)["counts"]
    runs_all = ok(engineer.get(f"/api/projects/{pid}/runs"))
    assert counts["runs"] == len([x for x in runs_all if not x["duplicate_of_run_id"]]) == len(runs_all) - 1
    assert not any(f["evidence_run_ids"] and dup["id"] in f["evidence_run_ids"] for f in ok(engineer.get(f"/api/projects/{pid}/findings")))
    # tampered bundle rejected at import; wrong signer rejected
    tb = json.loads(json.dumps(cb))
    tb["artifacts"]["raw_output.json"] = base64.b64encode(base64.b64decode(tb["artifacts"]["raw_output.json"]) + b" ").decode()
    assert engineer.post(f"/api/projects/{pid}/runs/import-bundle", json={"bundle": tb}).status_code == 422
    # independent replay: platform re-executes the same test; matching outcomes earn the label on the imported run
    ok(admin.post(f"/api/projects/{pid}/trusted-keys/{[k for k in ok(engineer.get(f'/api/projects/{pid}/trusted-keys')) if k['name'] == 'lab runner'][0]['id']}/revoke"))
    assert engineer.post(f"/api/projects/{pid}/runs/import-bundle", json={"bundle": runner_bundle(pid, tmp_path / "rk.pem", tmp_path / "cb2.json")}).status_code == 422  # revoked key
    ok(engineer.post(f"/api/projects/{pid}/runs/{imp['id']}/replay?wait=true"))
    imp2 = ok(engineer.get(f"/api/projects/{pid}/runs/{imp['id']}"))
    assert "independently_replayed" in {l["label"] for l in imp2["evidence_labels"]}
    # 12. optional compliance export with missing evidence identified -----------------------------------------------
    comp = ok(engineer.post(f"/api/projects/{pid}/export/compliance", json={"applicability": {}}))
    assert comp["disclaimer"].startswith("This export supports compliance review.")
    for c in comp["controls"]:
        assert "provisional" in c["mapping_status"] and c["customer_confirmed_applicability"] is False
        assert all(e["status"] in ("not_mapped", "insufficient_evidence", "not_applicable") for e in c["entries"])  # nothing claimed without confirmation
        research = next(e for e in c["entries"] if e["finding_id"] != defect["id"])
        assert research["status"] == "insufficient_evidence"
    comp2 = ok(engineer.post(f"/api/projects/{pid}/export/compliance", json={"applicability": {"PCI DSS v4.0.1 Requirement 12.3.3": {"confirmed": True, "scope": "signing svc", "owner": "x", "next_review": "2027-01-01"}}}))
    pci = comp2["controls"][0]
    assert next(e for e in pci["entries"] if e["finding_id"] == defect["id"])["status"] == "mapped" and pci["customer_confirmed_applicability"]
    assert comp2["controls"][1]["entries"][0]["status"] != "mapped"
    html = engineer.post(f"/api/projects/{pid}/export/compliance", json={"applicability": {}, "format": "html"}).text
    assert "not a certification" in html and "data:image/png;base64" in html
    # evidence package integrity
    pkg = engineer.get(f"/api/projects/{pid}/export/package")
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    man = json.loads(z.read("manifest.json"))
    assert len([n for n in man["members"] if n.startswith("bundles/")]) >= 4
    assert ok(engineer.post("/api/export/verify-package", files={"file": ("p.zip", pkg.content, "application/zip")}))["ok"]
    actions = {e["action"] for e in ok(engineer.get(f"/api/projects/{pid}/audit"))}
    for a in ("implementation.imported", "run.completed", "finding.opened", "experiment.approved", "experiment.executed", "recommendation.approved",
              "bundle.imported", "bundle.rejected", "trusted_key.revoked", "run.replayed", "finding.status", "compliance.exported"):
        assert a in actions, a


def test_results_only_and_unsupported(engineer, reviewer):
    p = new_project(engineer, reviewer, name="unsupported")
    pid = p["id"]
    m = manifest("1.0")
    m["adapter_kind"] = "module"
    bad = base64.b64encode(b"import subprocess\ndef keygen():\n    return None, None\n").decode()
    u = ok(engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": m, "source_snapshot_b64": bad, "source_snapshot_filename": "adapter.py"}))
    assert u["compatibility"]["status"] == "unsupported" and any("subprocess" in x for x in u["compatibility"]["problems"])
    core = next(t for t in ok(engineer.get(f"/api/projects/{pid}/tests")) if t["test_id"] == "signature-library-core")
    pf = ok(engineer.get(f"/api/projects/{pid}/tests/{core['id']}/preflight", params={"implementation_id": u["id"]}))
    assert pf["can_execute"] is False
    assert engineer.post(f"/api/projects/{pid}/runs", json={"test_definition_id": core["id"], "implementation_id": u["id"], "wait": True}).status_code == 409
    # results-only path still works and is labelled imported
    m2 = dict(manifest("1.1")); m2["adapter_kind"] = "results_only"
    ro = ok(engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": m2, "existing_results": {"fixture": "signature_library", "fixture_version": "ext", "status": "completed",
                                                                                                                           "metrics": {"signature_bytes": 64}, "scenarios": [{"id": "valid_signature", "expected": "accept", "observed": "accept", "pass": True}]}}))
    run = ok(engineer.get(f"/api/projects/{pid}/runs/{ro['existing_results_run_id']}"))
    assert run["execution_mode"] == "imported_results" and run["provenance"] == "imported" and {l["label"] for l in run["evidence_labels"]} == {"imported"}
    assert engineer.post(f"/api/projects/{pid}/runs/{run['id']}/replay").status_code == 409  # cannot replay without an adapter
    # catalog profile implementation executes
    prof = ok(engineer.post(f"/api/projects/{pid}/implementations/import", json={"manifest": {"name": "ref", "version": "1", "adapter_kind": "profile", "profile_id": "ed25519", "algorithm": "Ed25519"}}))
    r = ok(engineer.post(f"/api/projects/{pid}/runs", json={"test_definition_id": core["id"], "implementation_id": prof["id"], "wait": True}))
    assert r["classification"] == "passed_defined_checks" and r["metrics"]["official_vectors"] == "pass"
