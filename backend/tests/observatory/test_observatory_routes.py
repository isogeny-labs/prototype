"""The Observatory's three reads through the web, by the requests the screen will send. Every answer is checked against
the shape its route declares (tests/api_shapes.py does that for every test that talks to the app)."""

from __future__ import annotations

from urllib.parse import quote

from tests.assistant.assistant_walk import everything_kept
from tests.observatory import observatory_walk as W


def _demo(client) -> tuple[dict, int]:
    imp = client.post("/api/import/demo").json()
    address = imp["addresses"][0]["address"]
    confirmed = client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True})
    assert confirmed.status_code == 200
    return imp, client.post(f"/api/import/{imp['id']}/plan").json()["id"]


def test_the_map_a_box_and_a_place_through_the_web(client):
    import api_shapes

    lab = client.app.state.lab
    imp, pid = _demo(client)
    address = imp["addresses"][0]["address"]
    first = client.get(f"/api/plans/{pid}/observatory")
    assert first.status_code == 200 and first.json()["state"] == "file_only"
    assert client.post(f"/api/import/{imp['id']}/verify").status_code == 200
    added = client.post(
        f"/api/plans/{pid}/dependencies", params={"filename": W.DEMO_LIST.name}, content=W.DEMO_LIST.read_bytes()
    )
    assert added.status_code == 200
    before = everything_kept(lab)
    view = client.get(f"/api/plans/{pid}/observatory").json()
    assert view["state"] == "checked" and view["plan_id"] == pid and view["import_id"] == imp["id"]
    assert [b["key"] for b in W.boxes(view)] == [
        f"server:{address}",
        "software:lib-acme-sign",
        "top:acme-pay-server",
        "top:acme-ledger",
    ]
    # the same map by the assessment
    assert client.get(f"/api/assessments/{imp['assessment_id']}/observatory").json() == view
    # one box, by its key in the address (a key holds colons; the screen encodes it, and a plain one is read the same)
    for box in W.boxes(view):
        panel = client.get(f"/api/plans/{pid}/observatory/{quote(box['key'], safe='')}")
        assert panel.status_code == 200 and panel.json()["key"] == box["key"]
        assert panel.json()["title"] == box["title"] and panel.json()["link"] == box["link"]
        assert client.get(f"/api/plans/{pid}/observatory/{box['key']}").json() == panel.json()
    # where a result sits on the map; "place" is that read, never a box of that name
    place = client.get(f"/api/plans/{pid}/observatory/place", params={"key": "claim:1"})
    assert place.status_code == 200 and place.json()["place"]["box"] == f"server:{address}"
    assert place.json()["place"]["path"][-1] == "TLS versions"
    assert client.get(f"/api/plans/{pid}/observatory/place", params={"key": "fix:none"}).json() == {
        "key": "fix:none",
        "place": None,
    }
    assert client.get(f"/api/plans/{pid}/observatory/place").status_code == 422  # (a place needs its key)
    assert client.get(f"/api/plans/{pid}/observatory/place", params={"key": "x" * 701}).status_code == 422
    # reading through the web wrote nothing
    assert everything_kept(lab) == before
    # what is not there is said plainly
    missing = client.get(f"/api/plans/{pid}/observatory/server:nowhere.example:1")
    assert missing.status_code == 404 and missing.json()["error"]["message"] == "That box is not on this map."
    assert client.get("/api/plans/999/observatory").status_code == 404
    assert client.get("/api/plans/999/observatory/place", params={"key": "claim:1"}).status_code == 404
    assert client.get(f"/api/plans/999/observatory/server:{address}").status_code == 404
    assert client.get("/api/assessments/999/observatory").status_code == 404
    called = {
        ("GET", "/api/plans/{plan_id}/observatory"),
        ("GET", "/api/assessments/{assessment_id}/observatory"),
        ("GET", "/api/plans/{plan_id}/observatory/place"),
        ("GET", "/api/plans/{plan_id}/observatory/{box:path}"),
    }
    assert called <= api_shapes.DECLARED and called <= api_shapes.CHECKED, sorted(called - api_shapes.CHECKED)


def test_a_box_whose_key_holds_a_slash_is_opened_too(client):
    """A bom-ref is the file's own text, and package addresses with slashes are common ones."""
    lab = client.app.state.lab
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [
            {"type": "library", "bom-ref": "pkg:npm/@acme/sign@1.0", "name": "@acme/sign", "version": "1.0"},
            {
                "type": "cryptographic-asset",
                "bom-ref": "alg/ecdsa",
                "name": "ECDSA-P256",
                "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": {"primitive": "signature"}},
            },
        ],
        "dependencies": [{"ref": "pkg:npm/@acme/sign@1.0", "provides": ["alg/ecdsa"]}],
    }
    import json

    imp = client.post("/api/import/file", params={"filename": "slash.json"}, content=json.dumps(doc).encode()).json()
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    view = client.get(f"/api/plans/{pid}/observatory").json()
    (box,) = W.boxes(view)
    assert box["key"] == "software:pkg:npm/@acme/sign@1.0"
    for address in (box["key"], quote(box["key"], safe="")):
        panel = client.get(f"/api/plans/{pid}/observatory/{address}")
        assert panel.status_code == 200 and panel.json()["key"] == box["key"]
    assert W.lines(view, "uses") == {(box["key"], "algorithm:alg/ecdsa", "uses", "signs with")}
    assert lab.jobs.live(pid) == []


def test_an_assessment_with_no_file_yet_answers_with_the_way_to_import(client):
    made = client.post("/api/projects", json={"name": "Nothing yet"}).json()
    view = client.get(f"/api/assessments/{made['assessment_id']}/observatory").json()
    assert view["state"] == "empty" and view["plan_id"] is None and view["import_id"] is None
    assert view["empty"] == {
        "text": "No file has been brought in yet. The map is drawn from your scanner file, so bring one in on Import.",
        "link": {"page": "inventory/import", "item": None},
        "link_label": "Open Import",
    }
    assert view["services"] == [] and view["lines"] == [] and view["gaps"]["items"] == [] and view["banner"] is None
    assert [c["count"] for c in view["counts"]] == [0, 0, 0, 0]


def test_a_file_whose_test_plan_was_not_made_yet_is_drawn_from_its_claims_with_nothing_checked(client):
    imp = client.post("/api/import/demo").json()
    view = client.get(f"/api/assessments/{imp['assessment_id']}/observatory").json()
    assert view["state"] == "file_only" and view["plan_id"] is None and view["import_id"] == imp["id"]
    assert [b["kind"] for b in W.boxes(view)] == ["server", "program"]
    # no plan: no test is listed yet; the claims are not checked and the status is not measured
    assert {c["kind"] for c in W.checks(view)} == {"claim", "status"}
    assert all(not c["checked"] and c["word"] in W.NOT_YET for c in W.checks(view))
    assert W.counts(view) == {"live": 0, "lab": 0, "file": 5, "published": 0}  # three claims, two systems
    # ... the same five the map shows once the plan is there
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    assert W.counts(client.get(f"/api/plans/{pid}/observatory").json()) == W.counts(view)


def test_the_reads_need_a_login(anon_client):
    for address in (
        "/api/plans/1/observatory",
        "/api/plans/1/observatory/place?key=claim:1",
        "/api/plans/1/observatory/server:localhost:8443",
        "/api/assessments/1/observatory",
    ):
        assert anon_client.get(address).status_code == 401, address
