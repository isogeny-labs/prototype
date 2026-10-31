"""Containerised-application loop: at least one actual supported test run (process-isolated fixture)."""
import json
from pathlib import Path

from conftest import ok, new_project

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def test_app_loop(engineer, reviewer):
    p = new_project(engineer, reviewer, name="Loop test service", kind="application", support_period_end="2032-01-01")
    pid = p["id"]
    inv = json.loads((SEEDS / "app_inventory.json").read_text())
    ok(engineer.post(f"/api/projects/{pid}/inventory/import", json=inv))
    base = ok(engineer.post(f"/api/projects/{pid}/implementations", json={"name": "token-service", "version": "1.4.2", "role": "baseline",
                                                                          "profile_id": "jws_rs256", "delivery_mode": "container",
                                                                          "configuration": {"fixture_params": {"payload_bytes": 256}},
                                                                          "build_identity": {"image": "python:3.13-slim"}}))
    fx = ok(engineer.post(f"/api/projects/{pid}/experiments", json={"name": "token fixture", "fixture": "app_service_crypto",
                                                                   "definition": {"params": {"repeat_count": 40, "payload_bytes": 256}}}))
    r0 = ok(engineer.post(f"/api/projects/{pid}/runs", json={"experiment_id": fx["id"], "implementation_id": base["id"], "wait": True}))
    assert r0["status"] == "completed" and r0["runner_kind"] == "local_fixture" and r0["environment"]["isolation"] == "subprocess+rlimit"
    assert r0["metrics"]["functional_pass"] == 1 and r0["metrics"]["rejection_scenarios_all_pass"] == 1
    assert r0["overall_pass"] is False  # RSA-2048 signing cannot reach 4000 tokens/s per core
    failed = {x["metric"] for x in r0["requirement_results"] if x["pass"] is False}
    assert "sign_throughput_per_s" in failed
    f = next(x for x in ok(engineer.get(f"/api/projects/{pid}/findings")) if "throughput" in x["title"].lower())
    # research finding with an independently reproduced claim
    ok(engineer.post(f"/api/projects/{pid}/research/sources", json={"title": "jws guidance", "content": (SEEDS / "research_docs" / "jws_alg_guidance.txt").read_text(), "wait": True}))
    rf = next(x for x in ok(engineer.get(f"/api/projects/{pid}/findings")) if x["origin"] == "research")
    assert {c["reproduced"] for c in rf["claims"]} >= {"published", "independently_reproduced"}
    assert "PyJWT" in rf["affected"]["libraries"]
    # remediation: EdDSA/ES256 within token_signing only
    rec = ok(engineer.post(f"/api/projects/{pid}/recommendations/from-finding/{f['id']}"))
    assert rec["purpose"] == "token_signing" and rec["catalog_profile_id"].startswith("jws_")
    ok(reviewer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/decide", json={"decision": "approved"}))
    cand = ok(engineer.post(f"/api/projects/{pid}/recommendations/{rec['id']}/implement", json={"name": "token-service", "version": "1.5.0", "delivery_mode": "container",
                                                                                                  "configuration": {"fixture_params": {"payload_bytes": 256}}}))
    ok(engineer.post(f"/api/projects/{pid}/implementations/{cand['id']}/propose"))
    ok(reviewer.post(f"/api/projects/{pid}/implementations/{cand['id']}/decide", json={"decision": "approved"}))
    r1 = ok(engineer.post(f"/api/projects/{pid}/runs", json={"experiment_id": fx["id"], "implementation_id": cand["id"], "wait": True}))
    assert r1["overall_pass"] is True, r1["requirement_results"]
    rt = ok(engineer.post(f"/api/projects/{pid}/findings/{f['id']}/retest", json={"run_id": r1["id"]}))
    assert rt["status"] == "retested"
    cmp_ = ok(engineer.get(f"/api/projects/{pid}/compare", params={"baseline_run_id": r0["id"], "candidate_run_id": r1["id"]}))
    tok = next(m for m in cmp_["metrics"] if m["metric"] == "token_bytes")
    assert tok["candidate"] < tok["baseline"]
    assert ok(reviewer.post(f"/api/projects/{pid}/findings/{f['id']}/resolve", json={"candidate_run_id": r1["id"], "decision": "close"}))["status"] == "closed"
    # catalog recommendations never cross purposes
    recs = ok(engineer.post(f"/api/projects/{pid}/recommendations/generate"))
    for r in recs:
        if r["kind"] == "migration":
            assert r["profile"]["purpose"] == r["purpose"]
    assert any(r["kind"] == "no_migration" for r in recs)  # AES-128-GCM: no immediate migration
