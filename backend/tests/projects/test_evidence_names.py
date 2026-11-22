"""Phase 5a: evidence names the organization, folder, project and assessment, in the signed file and the report, and
the evidence check still passes (and still fails when one byte changes)."""

import json

from evidence import trusted_key_from_data_dir, verify_bytes  # the separate checking command (backend/evidence)


def _assessment_with_results(client):
    client.post("/api/organization", json={"name": "Acme Corp"})
    top = client.post("/api/folders", json={"name": "Payments"}).json()["id"]
    sub = client.post("/api/folders", json={"name": "EU", "parent_id": top}).json()["id"]
    made = client.post("/api/projects", json={"name": "Acme Pay", "folder_id": sub}).json()
    imp = client.post("/api/import/demo", params={"assessment_id": made["assessment_id"]}).json()
    client.post(
        f"/api/import/{imp['id']}/confirm-address", json={"address": imp["addresses"][0]["address"], "confirmed": True}
    )
    client.post(f"/api/import/{imp['id']}/verify")
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    item = next(t for t in plan["tests"] if t["kind"] == "tls_versions")["id"]
    client.post(f"/api/plans/{plan['id']}/tests/{item}/run")
    for _ in range(300):
        lab = client.get(f"/api/plans/{plan['id']}/lab").json()
        if not lab["busy"] and any(r["result"] for r in lab["rows"]):
            break
    return made, plan["id"]


def test_the_file_and_the_report_name_where_the_pass_belongs_and_stay_signed(client, settings, tmp_path):
    made, plan_id = _assessment_with_results(client)
    export = client.post(f"/api/plans/{plan_id}/evidence").json()
    raw = client.get(export["json"]["url"]).content
    envelope = json.loads(raw)
    where = envelope["evidence"]["assessment"]
    assert where == {
        "organization": "Acme Corp",
        "folders": ["Payments", "EU"],
        "project": "Acme Pay",
        "assessment": "Assessment 1",
        "assessment_number": 1,
        "opened_at": where["opened_at"],
        "closed_at": None,
        "status": "open",
        "purpose": "Full review",
        "reference": None,
        "signed_off_by": None,
        "signed_off_at": None,
        "signoff_note": None,
    }
    html = client.get(export["html"]["url"]).text
    assert "Acme Corp / Payments / EU / Acme Pay / Assessment 1" in html
    key = trusted_key_from_data_dir(settings.data_dir)
    assert verify_bytes(raw, key).ok
    assert not verify_bytes(raw.replace(b'"Acme Pay"', b'"Acme Pax"', 1), key).ok


def test_a_closed_assessment_says_closed_in_its_evidence(client):
    made, plan_id = _assessment_with_results(client)
    client.post(f"/api/assessments/{made['assessment_id']}", json={"close": True, "signed_off_by": "Sam Lee"})
    export = client.post(f"/api/plans/{plan_id}/evidence").json()
    envelope = json.loads(client.get(export["json"]["url"]).content)
    assert envelope["evidence"]["assessment"]["status"] == "closed"
    assert (
        envelope["evidence"]["assessment"]["signed_off_by"] == "Sam Lee"
    )  # phase 5b: the sign-off is in the signed file
    html = client.get(export["html"]["url"]).text
    assert "Acme Pay / Assessment 1 (closed)" in html and "Signed off by: </strong>Sam Lee" in html
    assert "Purpose: </strong>Full review" in html
