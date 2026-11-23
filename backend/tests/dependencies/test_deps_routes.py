"""Phase 4d: the four Dependencies routes, through the web, in demo mode. Every answer is checked against its shape
(tests/api_shapes.py). A broken file is refused with one plain sentence and the earlier list stays in place."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "demo"


def _add(client, pid: int, path: Path, name: str | None = None):
    return client.post(
        f"/api/plans/{pid}/dependencies",
        params={"filename": name or path.name},
        content=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )


@pytest.fixture
def plan(client):
    imp = client.post("/api/import/demo").json()
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    return imp, pid


def _answers(view: dict) -> dict:
    return {
        (g["label"], r["label"]): tuple((c["question"], c["answer"], c["label"], c["state"]) for c in r["cells"])
        for g in view["groups"]
        for r in g["rows"]
    }


def test_no_list_yet_says_so(client, plan):
    imp, _ = plan
    view = client.get(f"/api/import/{imp['id']}/dependencies").json()
    assert view["list_file"] is None and view["groups"] == [] and view["empty_text"] == "No dependency list added yet."
    assert view["upload"]["label"] == "Add dependency list"


def test_add_tie_and_measure_in_demo_mode(client, plan):
    imp, pid = plan
    view = _add(client, pid, DEMO / "dependencies-demo.cdx.json").json()
    assert [g["label"] for g in view["groups"]] == ["acme-sign 1.4.2", "acme-pay-server 1.0.0", "acme-ledger 5.1.0"]
    assert view["list_file"]["format"] == "CycloneDX 1.6"
    pay = next(g for g in view["groups"] if g["label"] == "acme-pay-server 1.0.0")
    assert pay["system"] is None and pay["picker"]["options"][0] == {"key": "", "name": "None of these"}
    server = next(o["key"] for o in pay["picker"]["options"] if o["key"].startswith("server:"))
    tied = client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": pay["key"], "system": server}).json()
    pay = next(g for g in tied["groups"] if g["label"] == "acme-pay-server 1.0.0")
    assert pay["system"] == server and pay["tie_source"] == "user"
    system = next(s for s in tied["systems"] if s["key"] == server)
    assert [line["text"].split(":")[0] for line in system["blocker_lines"]] == [
        "Blocks its key exchange track",
        "Blocks its authentication track",
    ]
    assert system["without_answer"] == 1
    # its text-only Fixes entry, through the web (its answer is checked against the Fixes shape)
    fixes = client.get(f"/api/plans/{pid}/fixes").json()["fixes"]
    assert [f["title"] for f in fixes if f["id"].startswith("dependency-")] == ["Update OpenSSL to 3.5.0 or later"]
    # Measure needs isolated mode: refused in plain words, nothing started
    refused = client.post(f"/api/plans/{pid}/dependencies/measure", json={})
    assert refused.status_code == 409 and "isolated mode" in refused.json()["error"]["message"]
    assert tied["measure_all"]["enabled"] is False
    # untie: "None of these"
    untied = client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": pay["key"], "system": ""}).json()
    assert next(g for g in untied["groups"] if g["label"] == "acme-pay-server 1.0.0")["system"] is None
    assert untied["systems"] == [s for s in untied["systems"] if not s["key"].startswith("server:")]


def test_tie_refuses_what_is_not_there(client, plan):
    _, pid = plan
    assert (
        client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": "x", "system": ""}).status_code == 409
    )  # no list yet
    view = _add(client, pid, DEMO / "dependencies-demo.cdx.json").json()
    top = view["groups"][1]["key"]
    assert (
        client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": "no-such-entry", "system": ""}).status_code
        == 404
    )
    bad = client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": top, "system": "server:example.com:443"})
    assert bad.status_code == 422 and bad.json()["error"]["field"] == "system"


@pytest.mark.parametrize("name", ["not-json.json", "not-a-dependency-list.json", "empty.json"])
def test_broken_files_are_refused_with_one_sentence_and_the_earlier_list_stays(client, plan, name):
    _, pid = plan
    before = _add(client, pid, DEMO / "dependencies-demo.cdx.json").json()
    refused = _add(client, pid, DEMO / "dependencies-broken" / name)
    assert refused.status_code == 422
    message = refused.json()["error"]["message"]
    assert message.endswith("Evidence Lab reads dependency lists in CycloneDX JSON (1.5 or 1.6) or SPDX JSON (2.3).")
    assert message.count(". ") <= 1 and "\n" not in message  # one plain sentence, then what it reads
    view = client.get(f"/api/import/{before['import_id']}/dependencies").json()
    assert view["list_file"] == before["list_file"] and _answers(view) == _answers(before)


def test_too_large_is_refused_before_reading(client, plan):
    _, pid = plan
    answer = client.post(
        f"/api/plans/{pid}/dependencies",
        params={"filename": "big.json"},
        content=b"{" + b" " * (16 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert answer.status_code == 422 and "16 MB" in answer.json()["error"]["message"]


def test_spdx_copy_gives_the_same_answers(client, plan):
    _, pid = plan
    cdx = _add(client, pid, DEMO / "dependencies-demo.cdx.json").json()
    spdx = _add(client, pid, DEMO / "dependencies-demo.spdx.json").json()
    assert spdx["list_file"]["format"] == "SPDX 2.3"
    assert _answers(spdx) == _answers(cdx) and len(_answers(cdx)) == 10


def test_routes_need_the_login(anon_client):
    for method, url in (
        ("get", "/api/import/1/dependencies"),
        ("post", "/api/plans/1/dependencies"),
        ("post", "/api/plans/1/dependencies/tie"),
        ("post", "/api/plans/1/dependencies/measure"),
    ):
        assert getattr(anon_client, method)(url).status_code == 401
