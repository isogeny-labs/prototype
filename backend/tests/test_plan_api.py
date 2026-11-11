"""The Tests and Evidence Lab web API: every route, its errors, its login, and that nothing accepts software."""
import time

import pytest
from fastapi.routing import APIRoute

from conftest import csv_bytes, upload


def start(client):
    imp = client.post("/api/import/demo").json()
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True})
    return imp


def wait(client, plan_id, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        plan = client.get(f"/api/plans/{plan_id}").json()
        if not plan["running"]:
            return plan
        time.sleep(0.1)
    raise AssertionError("tests did not finish")


def test_session_reports_the_mode_and_its_line(client):
    session = client.get("/api/session").json()
    assert session["mode"] == "demo"
    assert session["mode_line"] == "Demo mode: running our own demo software, not isolated. Isolated mode is switched off for this run."


def test_plan_is_proposed_once_and_then_stays(client):
    imp = start(client)
    assert client.get(f"/api/import/{imp['id']}/plan").status_code == 404
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    assert plan["import_id"] == imp["id"] and plan["is_demo"] is True
    assert [t["title"] for t in plan["tests"]] == ["Old TLS versions", "Certificate strength", "Official test vectors", "Bad signatures", "Speed and size"]
    assert plan["intro"] == ("Five tests suggested from the claims in acme-pay-cbom.json. Drag to change the order, remove any you "
                             "don't want, then run them.")
    address = imp["addresses"][0]["address"]
    assert plan["subject"] == [{"t": "text", "v": "Testing: "}, {"t": "text", "v": "server "}, {"t": "mono", "v": address},
                               {"t": "text", "v": " and "}, {"t": "text", "v": "signing component "}, {"t": "mono", "v": "acme-sign 1.4.2"},
                               {"t": "text", "v": " "}, {"t": "tag", "v": "from the file"}]
    first = plan["tests"][0]
    assert first == {"id": first["id"], "kind": "tls_versions", "title": "Old TLS versions", "origin": "suggested", "tag": None,
                     "description": f"Checks whether the server at {address} accepts any TLS version older than the file claims (TLS 1.3 only).",
                     "why": "Why it matters: older versions have known weaknesses and are easy to leave switched on.",
                     "status": "not_run", "status_text": "Not run yet", "progress": None, "result": None, "can_run": True, "can_remove": True}
    assert plan["tests"][2]["description"] == ("Gives acme-sign 484 published signature cases with known right answers "
                                               "(Project Wycheproof, ECDSA P-256) and counts any it gets wrong.")
    assert plan["tests"][4]["description"].startswith("Times signing and checking inside the program (100 repeats each)")
    assert (plan["running"], plan["can_run_all"], plan["has_results"], plan["max_parallel"]) == (False, True, False, 4)
    assert plan["catalog_title"] == "Tests you can add" and plan["catalog_note"] == "Tests you remove from the plan come back to this list."
    assert plan["catalog"] == [
        {"catalog_id": "pq_readiness", "title": "Post-quantum readiness", "tag": None,
         "description": "Checks whether the server offers the newer quantum-resistant key exchange (X25519MLKEM768)."},
        {"catalog_id": "mldsa_compare", "title": "ML-DSA-65 comparison", "tag": "reference, not production",
         "description": "Shows the speed and sizes of a post-quantum signature (ML-DSA-65) from a reference implementation, next to acme-sign's."}]
    again = client.post(f"/api/import/{imp['id']}/plan").json()
    assert again["id"] == plan["id"] and [t["id"] for t in again["tests"]] == [t["id"] for t in plan["tests"]]
    assert client.get(f"/api/import/{imp['id']}/plan").json()["id"] == plan["id"]
    assert client.get(f"/api/plans/{plan['id']}").json() == again
    assert client.post("/api/import/999/plan").status_code == 404 and client.get("/api/plans/999").status_code == 404


def test_reorder_add_remove_and_add_back(client):
    imp = start(client)
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid, ids = plan["id"], [t["id"] for t in plan["tests"]]
    swapped = [ids[1], ids[0], *ids[2:]]
    assert [t["id"] for t in client.post(f"/api/plans/{pid}/order", json={"order": swapped}).json()["tests"]] == swapped
    assert [t["id"] for t in client.get(f"/api/plans/{pid}").json()["tests"]] == swapped  # it is stored
    for bad in ({"order": ids[:-1]}, {"order": ids + [999]}, {"order": [ids[0]] * 5}, {"order": "x"}, {}, {"order": ["1"]}):
        assert client.post(f"/api/plans/{pid}/order", json=bad).status_code == 422
    added = client.post(f"/api/plans/{pid}/tests", json={"catalog_id": "pq_readiness"}).json()
    new = added["tests"][-1]
    assert (new["kind"], new["origin"], new["title"]) == ("pq_readiness", "added", "Post-quantum readiness")
    assert new["description"].startswith("Checks whether the server at localhost:")
    assert added["intro"].startswith("Six tests in the plan: five suggested from the claims, one added by you.")
    assert [c["catalog_id"] for c in added["catalog"]] == ["mldsa_compare"]
    assert client.post(f"/api/plans/{pid}/tests", json={"catalog_id": "pq_readiness"}).status_code == 409  # already there
    for bad in ({"catalog_id": "upload"}, {"catalog_id": 5}, {}, {"catalog_id": "x" * 100}):
        assert client.post(f"/api/plans/{pid}/tests", json=bad).status_code == 422
    removed = client.post(f"/api/plans/{pid}/tests/{ids[3]}/remove").json()
    assert ids[3] not in [t["id"] for t in removed["tests"]] and len(removed["tests"]) == 5
    assert removed["catalog"][0]["catalog_id"] == "bad_signatures" and removed["catalog"][0]["title"] == "Bad signatures"
    assert removed["intro"].startswith("Five tests in the plan: four suggested from the claims, one added by you.")
    assert client.post(f"/api/plans/{pid}/tests/{ids[3]}/remove").status_code == 404
    back = client.post(f"/api/plans/{pid}/tests", json={"catalog_id": "bad_signatures"}).json()
    assert back["tests"][-1]["id"] == ids[3] and back["tests"][-1]["origin"] == "suggested"  # the same test, at the end
    assert client.post(f"/api/plans/{pid}/tests/999/remove").status_code == 404
    assert client.post(f"/api/plans/999/tests", json={"catalog_id": "pq_readiness"}).status_code == 404


def test_run_one_then_the_lab_then_mark_and_dig(client):
    imp = start(client)
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid = plan["id"]
    cert, bad = plan["tests"][1]["id"], plan["tests"][3]["id"]
    lab0 = client.get(f"/api/plans/{pid}/lab").json()
    assert lab0["view"] == "results" and lab0["columns"] is None and all(r["result"] is None for r in lab0["rows"])
    assert lab0["rows"][0]["result_status"] == {"status": "not_run", "status_text": "Not run yet", "progress": None}
    assert lab0["disclaimer"] == "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
    started = client.post(f"/api/plans/{pid}/tests/{bad}/run")
    assert started.status_code == 200
    card = next(t for t in started.json()["tests"] if t["id"] == bad)
    assert card["status"] in ("waiting", "running") and card["result"] is None and card["can_remove"] is False
    assert started.json()["running"] is True and started.json()["can_run_all"] is False
    assert all(t["can_run"] is False for t in started.json()["tests"])
    # while it runs: nothing else can be started, and the running test cannot be removed
    assert client.post(f"/api/plans/{pid}/tests/{cert}/run").status_code == 409
    assert client.post(f"/api/plans/{pid}/run-all").status_code == 409
    assert client.post(f"/api/plans/{pid}/tests/{bad}/remove").status_code == 409
    assert client.post(f"/api/plans/{pid}/retest", json={"version": "1.4.3"}).status_code == 409
    done = wait(client, pid)
    card = next(t for t in done["tests"] if t["id"] == bad)
    assert card["status"] == "done" and card["status_text"] == "Failed" and card["result"] == {"code": "failed", "label": "Failed", "tone": "fail"}
    assert done["has_results"] is True and done["can_run_all"] is True
    lab = client.get(f"/api/plans/{pid}/lab").json()
    row = next(r for r in lab["rows"] if r["item_id"] == bad)
    result = row["result"]
    assert set(result) == {"run_id", "component", "mode", "finished_at", "duration_ms", "code", "label", "tone", "summary", "short",
                           "control", "what_happened", "shows_title", "shows", "evidence", "run_record", "locked_test", "fix_title",
                           "suggested_fix", "reviewed", "research"}
    assert result["component"] == "acme-sign 1.4.2" and result["mode"] == "demo" and result["reviewed"] is None and result["research"] is None
    assert row["control_line"] == "Control: a deliberately broken signer failed this test, as expected."
    assert lab["retest"]["can_start"] is False  # not every test has a result yet
    assert client.post(f"/api/plans/{pid}/retest", json={"version": "1.4.3"}).status_code == 409
    assert lab["download"] == {"can_start": True, "blocked_reason": None}
    run_id = result["run_id"]
    marked = client.post(f"/api/runs/{run_id}/mark-reviewed").json()
    assert next(r for r in marked["rows"] if r["item_id"] == bad)["result"]["reviewed"]["text"] == "You marked this result as reviewed."
    dug = client.post(f"/api/runs/{run_id}/dig-deeper").json()
    box = next(r for r in dug["rows"] if r["item_id"] == bad)["result"]["research"]
    assert box["status"] == "waiting for research engine" and box["title"] == "Research request saved"
    assert client.post("/api/runs/999/mark-reviewed").status_code == 404 and client.post("/api/runs/999/dig-deeper").status_code == 404
    for bad_body in ({"version": "9.9.9"}, {"version": 3}, {}):
        assert client.post(f"/api/plans/{pid}/retest", json=bad_body).status_code == 422
    assert client.get("/api/plans/999/lab").status_code == 404
    assert client.post("/api/plans/999/run-all").status_code == 404 and client.post(f"/api/plans/{pid}/tests/999/run").status_code == 404


def test_a_file_with_no_server_gets_no_server_tests(client):
    imp = upload(client, "claims.csv", csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256")).json()
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    assert [t["kind"] for t in plan["tests"]] == ["official_vectors", "bad_signatures", "speed_size"]
    assert plan["intro"].startswith("Three tests suggested from the claims in claims.csv.")
    assert [c["catalog_id"] for c in plan["catalog"]] == ["mldsa_compare"]  # no server, so no post-quantum readiness test
    assert client.post(f"/api/plans/{plan['id']}/tests", json={"catalog_id": "pq_readiness"}).status_code == 422


NEW_ROUTES = [
    ("GET", "/api/import/1/plan"), ("POST", "/api/import/1/plan"), ("GET", "/api/plans/1"), ("POST", "/api/plans/1/order"),
    ("POST", "/api/plans/1/tests"), ("POST", "/api/plans/1/tests/1/remove"), ("POST", "/api/plans/1/tests/1/run"),
    ("POST", "/api/plans/1/run-all"), ("GET", "/api/plans/1/lab"), ("POST", "/api/runs/1/mark-reviewed"),
    ("POST", "/api/runs/1/dig-deeper"), ("POST", "/api/plans/1/retest"),
]


@pytest.mark.parametrize("method, path", NEW_ROUTES)
def test_every_new_route_needs_a_login(anon_client, method, path):
    response = anon_client.request(method, path, json={"order": [1], "catalog_id": "pq_readiness", "version": "1.4.3"})
    assert response.status_code == 401 and response.json()["error"]["message"] == "Please log in."


def test_there_is_no_route_that_accepts_software(client):
    """The only route that takes a file is phase 1's claims import. Every other POST takes no body or one of
    three tiny JSON bodies. Nothing takes a component, an archive, a Dockerfile or a path."""
    routes = [r for r in client.app.routes if isinstance(r, APIRoute)]
    posts = sorted(r.path for r in routes if "POST" in r.methods and r.path != "/api/{rest:path}")
    with_json_body = {r.path: r.body_field.field_info.annotation.__name__ for r in routes if r.body_field is not None}
    allowed_bodies = {"/api/setup": "PasswordBody", "/api/login": "PasswordBody", "/api/import/{import_id}/confirm-address": "ConfirmBody",
                      "/api/plans/{plan_id}/order": "OrderBody", "/api/plans/{plan_id}/tests": "AddTestBody",
                      "/api/plans/{plan_id}/retest": "RetestBody"}
    assert {k: v for k, v in with_json_body.items() if k in allowed_bodies} == allowed_bodies
    extra = set(with_json_body) - set(allowed_bodies)
    assert all(p.startswith("/api/evidence") or p.endswith("/evidence") for p in extra), extra
    for path in posts:
        assert not any(word in path for word in ("upload", "software", "component", "image", "docker", "file")) or path == "/api/import/file"
    reads_raw_body = [r.path for r in routes if "request" in r.endpoint.__code__.co_varnames and "POST" in r.methods
                      and r.endpoint.__name__ == "import_file"]
    assert reads_raw_body == ["/api/import/file"]
    for attempt in ("/api/upload", "/api/components", "/api/software", "/api/plans/1/component", "/api/import/software"):
        r = client.post(attempt, content=b"print('x')", headers={"Content-Type": "application/octet-stream"})
        assert r.status_code in (404, 405, 422) and "error" in r.json()
    # a retest cannot smuggle anything in either: the body is one short version string checked against our own list
    imp = start(client)
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    for sneaky in ({"version": "1.4.3", "path": "/tmp/x.py"}, {"version": "../../evil"}, {"version": "1.4.3\n"}):
        r = client.post(f"/api/plans/{pid}/retest", json=sneaky)
        assert r.status_code in (409, 422)
    from app import components
    assert components.VERSIONS == {"acme-sign": ["1.4.2", "1.4.3"]}
