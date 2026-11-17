"""Phase 5b: the Assessment Overview's blocks and the Project overview (every assessment side by side, what changed
between two, shared systems). Counts only, read from the pages they link to; no score."""
from types import SimpleNamespace


def _project(client, name="Acme Pay"):
    made = client.post("/api/projects", json={"name": name}).json()
    return made["id"], made["assessment_id"]


def _demo_verified(client, aid):
    imp = client.post("/api/import/demo", params={"assessment_id": aid}).json()
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True})
    client.post(f"/api/import/{imp['id']}/verify")
    return imp


def test_the_overview_blocks_after_a_verify_count_only_what_the_pages_show(client):
    _, aid = _project(client)
    assert client.get(f"/api/assessments/{aid}").json()["blocks"] is None          # before a file: nothing to count
    _demo_verified(client, aid)
    view = client.get(f"/api/assessments/{aid}").json()
    blocks = view["blocks"]
    assert [g["label"] for g in blocks["groups"]] == ["Verification", "Encryption tests", "Migration", "Dependencies"]
    verification = blocks["groups"][0]
    assert [(f["label"], f["value"]) for f in verification["facts"]] == [("True", 2), ("False", 1), ("Couldn't check", 0)]
    assert all(f["link"]["page"] == "inventory/verify" for f in verification["facts"])
    findings = {f["label"]: f["value"] for f in blocks["findings"]}
    assert findings == {"False claims": 1, "Failed tests": 0, "Dependency blockers": 0}
    assert blocks["evidence"]["runs"] == 1 and blocks["evidence"]["last_download"] is None
    # Each group with nothing yet says why, in the words of Checks.
    assert blocks["groups"][3]["empty_text"] == "No dependency list yet. Add one on Dependencies."
    text = str(blocks).lower()
    assert "score" not in text and "secure" not in text


def test_the_project_overview_lists_every_assessment_open_first_and_the_systems_they_share(client):
    pid, first = _project(client)
    _demo_verified(client, first)
    second = client.post(f"/api/assessments/{first}/rerun", json={"name": "Second pass"}).json()["id"]
    imp2 = client.get(f"/api/assessments/{second}").json()["import"]
    client.post(f"/api/import/{imp2['id']}/confirm-address", json={"address": imp2["addresses"][0]["address"], "confirmed": True})
    client.post(f"/api/import/{imp2['id']}/verify")
    client.post(f"/api/assessments/{first}", json={"close": True, "signed_off_by": "Sam Lee"})
    view = client.get(f"/api/projects/{pid}/overview").json()
    assert [r["title"] for r in view["rows"]] == ["Second pass", "Assessment 1"]        # open ones first
    assert view["rows"][1]["status"]["signoff"]["by"] == "Sam Lee"
    assert view["rows"][0]["headline"]["claims"]["false"] == 1
    shared = {s["name"]: s for s in view["shared"]}
    assert set(shared) == {imp2["addresses"][0]["address"], "acme-sign 1.4.2"}
    assert {a["title"] for a in shared["acme-sign 1.4.2"]["assessments"]} == {"Second pass", "Assessment 1"}
    compare = view["compare"]
    assert (compare["from_id"], compare["to_id"]) == (first, second)
    assert [lst["title"] for lst in compare["lists"]] == ["New findings", "No longer findings", "Tracks that moved", "Not checked in both"]
    assert all(lst["items"] == [] for lst in compare["lists"])                            # the same file, the same answers
    picked = client.get(f"/api/projects/{pid}/overview", params={"from_id": second, "to_id": first}).json()["compare"]
    assert (picked["from_id"], picked["to_id"]) == (first, second)                       # always older to newer


def test_what_changed_names_only_what_both_checked_and_what_the_newer_check_says(lab):
    def facts(claims=None, tests=None, tracks=None):
        return {"claims": claims or {}, "tests": tests or {}, "tracks": tracks or {}, "blockers": {}, "systems": {},
                "has_results": True, "deps_listed": False}
    old = SimpleNamespace(id=1, name="Q3", number=1)
    new = SimpleNamespace(id=2, name="Q4", number=2)
    claim = ("localhost:8443", "protocol_versions", "TLS 1.3")
    test = ("tls_versions", "", "Old TLS versions")
    track = ("localhost:8443", "Key exchange")
    entry = lambda label, result, finding=False: {"label": label, "result": result, "finding": finding,  # noqa: E731
                                                  "cleared": result in ("True", "Passed"), "item": "x", "page": "evidence"}
    table = {
        1: facts(claims={claim: entry("TLS 1.3 only", "False", True)}, tests={test: entry("Old TLS versions", "Passed")},
                 tracks={track: entry("localhost:8443 · Key exchange", "Classical")}),
        2: facts(claims={claim: entry("TLS 1.3 only", "True")}, tests={test: entry("Old TLS versions", "Failed", True),
                 ("speed_size", "", "Speed and size"): entry("Speed and size", "Measured")},
                 tracks={track: entry("localhost:8443 · Key exchange", "Hybrid (interim)")}),
    }
    lab._assessment_facts = lambda a: table[a.id]
    lists = {lst["key"]: lst["items"] for lst in lab.compare_assessments(old, new)["lists"]}
    assert [i["label"] for i in lists["new"]] == ["Old TLS versions"]                # failed now, passed before
    assert [(i["label"], i["sub"]) for i in lists["gone"]] == [("TLS 1.3 only", "False before, True now")]
    assert [(i["label"], i["sub"]) for i in lists["moved"]] == [("localhost:8443 · Key exchange", "Classical to Hybrid (interim)")]
    assert [(i["label"], i["sub"]) for i in lists["single"]] == [("Speed and size", "Checked only in Q4")]


def test_a_finding_that_now_reads_couldnt_check_is_not_called_gone(lab):
    """Only the newer assessment's own True or Passed clears a finding. A False claim that now reads Couldn't check, or
    a failed test that now reads Couldn't trust this run, was not answered there: it is listed under Not checked in both."""
    def facts(claims=None, tests=None):
        return {"claims": claims or {}, "tests": tests or {}, "tracks": {}, "blockers": {}, "systems": {},
                "has_results": True, "deps_listed": False}
    old = SimpleNamespace(id=1, name="Q3", number=1)
    new = SimpleNamespace(id=2, name="Q4", number=2)
    claim = ("localhost:8443", "protocol_versions", "TLS 1.3")
    test = ("tls_versions", "", "Old TLS versions")
    entry = lambda label, result, finding=False: {"label": label, "result": result, "finding": finding,  # noqa: E731
                                                  "cleared": result in ("True", "Passed"), "item": "x", "page": "evidence"}
    table = {
        1: facts(claims={claim: entry("TLS 1.3 only", "False", True)}, tests={test: entry("Old TLS versions", "Failed", True)}),
        2: facts(claims={claim: entry("TLS 1.3 only", "Couldn't check")}, tests={test: entry("Old TLS versions", "Couldn't trust this run")}),
    }
    lab._assessment_facts = lambda a: table[a.id]
    lists = {lst["key"]: lst["items"] for lst in lab.compare_assessments(old, new)["lists"]}
    assert lists["gone"] == []
    assert [(i["label"], i["sub"]) for i in lists["single"]] == [
        ("TLS 1.3 only", "False before, Couldn't check now: not answered in Q4"),
        ("Old TLS versions", "Failed before, Couldn't trust this run now: not answered in Q4"),
    ]

