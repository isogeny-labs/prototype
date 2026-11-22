"""Phase 5a and 5b: assessments. One file each; New assessment closes nothing (phase 5b: any number open); closing is a
sign-off with a name and a time that can't be undone; a closed assessment is read-only (every changing request refused
with one sentence, downloads still work); imports with no assessment go to "Imported without a project"."""
import re

from fastapi.routing import APIRoute

from tests.conftest import api_routes, csv_bytes, upload

CLOSED = "This assessment is closed. Start a new one to continue."


def _project(client, name="Acme Pay"):
    made = client.post("/api/projects", json={"name": name}).json()
    return made["id"], made["assessment_id"]


def _import_demo(client, aid):
    r = client.post("/api/import/demo", params={"assessment_id": aid})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_new_project_opens_an_empty_assessment_that_takes_one_file(client):
    pid, aid = _project(client)
    view = client.get(f"/api/assessments/{aid}").json()
    assert view["status"]["key"] == "open" and view["import"] is None and view["file"] is None
    assert view["next_step"]["page"] == "inventory/import" and view["project"]["name"] == "Acme Pay"
    imp = _import_demo(client, aid)
    assert imp["assessment_id"] == aid
    view = client.get(f"/api/assessments/{aid}").json()
    assert view["import"]["id"] == imp["id"] and view["file"]["filename"] == "acme-pay-cbom.json" and view["file"]["is_demo"]
    assert view["next_step"]["label"] == "Verify claims"
    # A second file never goes into the same assessment: the screens start a new one first.
    again = client.post("/api/import/demo", params={"assessment_id": aid})
    assert again.status_code == 409 and "already has a file" in again.json()["error"]["message"]


def test_new_assessment_closes_nothing_and_keeps_the_one_before_whole(client):
    pid, first = _project(client)
    imp = _import_demo(client, first)
    client.post(f"/api/import/{imp['id']}/verify")
    before = client.get(f"/api/import/{imp['id']}/verify").json()
    second = client.post(f"/api/projects/{pid}/assessments").json()["id"]
    old = client.get(f"/api/assessments/{first}").json()
    assert old["status"]["key"] == "open" and old["status"]["closed_line"] is None          # phase 5b: both stay open
    assert client.get(f"/api/import/{imp['id']}/verify").json() == before          # kept exactly as it was
    # The first one still takes changes: it is open.
    assert client.post(f"/api/import/{imp['id']}/verify").status_code == 200
    new = client.get(f"/api/assessments/{second}").json()
    assert new["number"] == 2 and new["title"] == "Assessment 2" and new["status"]["key"] == "open" and new["file"] is None
    p = client.get(f"/api/projects/{pid}").json()
    assert [a["number"] for a in p["assessments"]] == [2, 1]                          # newest first, nothing gone
    assert [a["status"]["key"] for a in p["assessments"]] == ["open", "open"] and p["next_name"] == "Assessment 3"
    work = client.get("/api/workspace").json()
    row = next(r for r in work["projects"] if r["id"] == pid)
    assert row["open_count"] == 2 and row["closed_count"] == 0


def test_the_new_assessment_box_name_purpose_and_reference(client):
    pid, _ = _project(client)
    work = client.get("/api/workspace").json()
    assert [p["label"] for p in work["purposes"]] == ["Full review", "Compliance review", "Migration wave", "Release check",
                                                     "Advisory response", "Other"]
    made = client.post(f"/api/projects/{pid}/assessments",
                       json={"name": "PCI review", "purpose": "compliance_review", "reference": "PCI DSS 12.3.3"}).json()
    view = client.get(f"/api/assessments/{made['id']}").json()
    assert view["title"] == "PCI review" and view["purpose"] == {"key": "compliance_review", "label": "Compliance review"}
    assert view["reference"] == "PCI DSS 12.3.3"
    # The purpose is a label only; it can be changed while the assessment is open, and the change is kept as a new record.
    view = client.post(f"/api/assessments/{made['id']}", json={"purpose": "release_check"}).json()
    assert view["purpose"]["label"] == "Release check" and view["reference"] == "PCI DSS 12.3.3"
    bad = client.post(f"/api/projects/{pid}/assessments", json={"purpose": "audit"})
    assert bad.status_code == 422 and bad.json()["error"]["message"] == "Pick a purpose from the list."
    # A name left as the default is the plain "Assessment N".
    plain = client.post(f"/api/projects/{pid}/assessments", json={"name": "Assessment 3"}).json()
    assert client.get(f"/api/assessments/{plain['id']}").json()["name"] is None


def test_close_rename_move_and_archive_an_assessment(client):
    pid, aid = _project(client)
    other, _ = _project(client, "Other")
    client.post(f"/api/assessments/{aid}", json={"name": "Before the audit"})
    # Phase 5b: closing is a sign-off. Without a name it is refused and nothing changes.
    refused = client.post(f"/api/assessments/{aid}", json={"close": True})
    assert refused.status_code == 422 and "name" in refused.json()["error"]["message"]
    assert client.get(f"/api/assessments/{aid}").json()["status"]["key"] == "open"
    view = client.post(f"/api/assessments/{aid}", json={"close": True, "signed_off_by": "Sam Lee", "note": "Q4 sign-off"}).json()
    assert view["title"] == "Before the audit" and view["status"]["key"] == "closed"
    assert view["status"]["closed_line"] == f"Closed and signed off by Sam Lee. {CLOSED}"
    assert view["status"]["signoff"]["by"] == "Sam Lee" and view["status"]["signoff"]["note"] == "Q4 sign-off"
    assert view["status"]["signoff"]["at"] == view["closed_at"]
    # It can't be reopened or signed off again, and its purpose can't change.
    again = client.post(f"/api/assessments/{aid}", json={"close": True, "signed_off_by": "Someone else"})
    assert again.status_code == 409 and client.get(f"/api/assessments/{aid}").json()["status"]["signoff"]["by"] == "Sam Lee"
    assert client.post(f"/api/assessments/{aid}", json={"purpose": "other"}).json()["error"]["message"] == CLOSED
    moved = client.post(f"/api/assessments/{aid}", json={"project_id": other}).json()
    assert moved["project"]["id"] == other and moved["number"] == 2                  # takes the next number there
    assert client.post(f"/api/assessments/{aid}", json={"archived": True}).json()["archived"] is True
    # A closed assessment takes no file.
    assert client.post("/api/import/demo", params={"assessment_id": aid}).json()["error"]["message"] == CLOSED


def _closed_with_everything(client):
    """A closed assessment whose import has a verify run, a plan and a run, so every id kind exists."""
    pid, aid = _project(client)
    imp = _import_demo(client, aid)
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True})
    client.post(f"/api/import/{imp['id']}/verify")
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    item = next(t for t in plan["tests"] if t["kind"] == "tls_versions")["id"]
    client.post(f"/api/plans/{plan['id']}/tests/{item}/run")
    for _ in range(200):
        lab = client.get(f"/api/plans/{plan['id']}/lab").json()
        if not lab["busy"] and any(r["result"] for r in lab["rows"]):
            break
    run_id = next(r["result"]["run_id"] for r in lab["rows"] if r["result"])
    client.post(f"/api/assessments/{aid}", json={"close": True, "signed_off_by": "Sam Lee"})
    return imp["id"], plan["id"], run_id


def test_every_changing_request_on_a_closed_assessment_is_refused_except_downloads(client):
    import_id, plan_id, run_id = _closed_with_everything(client)
    allowed = {"/api/plans/{plan_id}/evidence", "/api/import/{import_id}/plan"}
    checked = []
    for route in api_routes(client.app):
        if not isinstance(route, APIRoute) or "POST" not in route.methods:
            continue
        if not re.search(r"\{(import_id|plan_id|run_id)\}", route.path):
            continue
        path = (route.path.replace("{import_id}", str(import_id)).replace("{plan_id}", str(plan_id))
                .replace("{run_id}", str(run_id)).replace("{fix_id}", "fix-tls-versions").replace("{item_id}", "1"))
        r = client.post(path, json={})
        if route.path in allowed:
            assert r.status_code != 409, (route.path, r.text)
        else:
            assert r.status_code == 409 and r.json()["error"]["message"] == CLOSED, (route.path, r.status_code, r.text)
        checked.append(route.path)
    assert len(checked) >= 29                           # every step's changing routes were walked (29 in phase 5a)
    # Looking still works.
    for path in (f"/api/import/{import_id}/verify", f"/api/plans/{plan_id}/lab", f"/api/plans/{plan_id}/fixes",
                 f"/api/import/{import_id}/migration", f"/api/import/{import_id}/dependencies"):
        assert client.get(path).status_code == 200, path


def test_download_evidence_still_works_on_a_closed_assessment(client):
    import_id, plan_id, _ = _closed_with_everything(client)
    r = client.post(f"/api/plans/{plan_id}/evidence")
    assert r.status_code == 200, r.text


def test_a_stranger_gets_please_log_in_not_the_closed_sentence(client, anon_client):
    import_id, plan_id, _ = _closed_with_everything(client)
    client.cookies.clear()
    assert client.post(f"/api/plans/{plan_id}/run-all").status_code == 401


def test_a_failed_upload_puts_nothing_into_the_assessment(client):
    pid, aid = _project(client)
    r = client.post("/api/import/file", params={"filename": "broken.csv", "assessment_id": aid},
                    content=csv_bytes("localhost:8443,tls,protocol_versions,TLS9.9"))
    assert r.status_code == 422
    view = client.get(f"/api/assessments/{aid}").json()
    assert view["file"] is None and view["status"]["key"] == "open"
    assert client.get("/api/import/current").status_code == 404          # the old global rule is unchanged


def test_imports_with_no_assessment_go_to_one_project_and_none_closes_another(client):
    a = client.post("/api/import/demo").json()
    b = upload(client, "two.csv", csv_bytes("localhost:8443,tls,protocol_versions,TLS1.3")).json()
    assert a["assessment_id"] != b["assessment_id"]
    w = client.get("/api/workspace").json()
    unfiled = [p for p in w["projects"] if p["name"] == "Imported without a project"]
    assert len(unfiled) == 1 and unfiled[0]["assessments"] == 2 and unfiled[0]["is_demo"] is False
    for aid in (a["assessment_id"], b["assessment_id"]):
        assert client.get(f"/api/assessments/{aid}").json()["status"]["key"] == "open"
    assert client.post(f"/api/import/{a['id']}/verify").status_code == 200          # the first one still takes actions
    assert client.get("/api/import/current").json()["assessment_id"] == b["assessment_id"]


def test_imports_from_before_projects_are_adopted_on_start(tmp_path):
    from app.db import AssessmentRow, ImportRow
    from tests.conftest import make_lab
    lab = make_lab(tmp_path)
    try:
        with lab.db() as db:   # an import as phase 4d left it: no assessment
            db.add(ImportRow(filename="old.csv", format="csv", is_demo=False))
            db.commit()
    finally:
        lab.stop()
    again = make_lab(tmp_path, demo_tls_port=lab.settings.demo_tls_port)
    try:
        with again.db() as db:
            rows = db.query(AssessmentRow).all()
            assert len(rows) == 1 and rows[0].import_id == db.query(ImportRow).one().id and rows[0].closed_at is None
        assert [p["name"] for p in again.workspace_view()["projects"]] == ["Imported without a project"]
    finally:
        again.stop()
