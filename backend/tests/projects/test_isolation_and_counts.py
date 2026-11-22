"""Phase 5a: every assessment keeps its own data (switching shows each exactly as it was left), and the counts on the
Projects table and Overview are the pages' own numbers, never more."""


def _demo_assessment(client, name):
    made = client.post("/api/projects", json={"name": name}).json()
    imp = client.post("/api/import/demo", params={"assessment_id": made["assessment_id"]}).json()
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True})
    return made, imp


def test_two_assessments_keep_their_own_data(client):
    a, imp_a = _demo_assessment(client, "A")
    b, imp_b = _demo_assessment(client, "B")
    client.post(f"/api/import/{imp_a['id']}/verify")
    seen_a = client.get(f"/api/assessments/{a['assessment_id']}").json()
    # Work in B (verify, plan, reorder) changes nothing in A.
    client.post(f"/api/import/{imp_b['id']}/verify")
    plan_b = client.post(f"/api/import/{imp_b['id']}/plan").json()
    client.post(f"/api/plans/{plan_b['id']}/order", json={"order": list(reversed([t["id"] for t in plan_b["tests"]]))})
    assert client.get(f"/api/assessments/{a['assessment_id']}").json() == seen_a
    assert seen_a["import"]["id"] == imp_a["id"] and seen_a["plan_id"] is None
    view_b = client.get(f"/api/assessments/{b['assessment_id']}").json()
    assert view_b["import"]["id"] == imp_b["id"] and view_b["plan_id"] == plan_b["id"]


def test_counts_are_the_pages_own_numbers(client):
    a, imp = _demo_assessment(client, "Acme Pay")
    aid = a["assessment_id"]
    assert client.get(f"/api/assessments/{aid}").json()["counts"]["claims"] is None     # not verified: no number
    run = client.post(f"/api/import/{imp['id']}/verify").json()
    view = client.get(f"/api/assessments/{aid}").json()
    words = [r["result"] for r in run["results"]]
    assert view["counts"]["claims"] == {"checked": len(words), "false": words.count("False"), "true": words.count("True"),
                                        "couldnt_check": words.count("Couldn't check")}
    assert view["counts"]["claims"]["false"] == 1                                       # TLS 1.3 only is false (expected.json)
    assert view["counts"]["tests"] is None and view["counts"]["fixes"] is None and view["counts"]["systems"] is None
    assert view["next_step"]["page"] == "checks" and view["next_step"]["label"] == "Open checks"
    row = next(p for p in client.get("/api/workspace").json()["projects"] if p["id"] == a["id"])
    assert row["counts"] == view["counts"]
