"""Phase 5b: Rerun as new assessment (the same scanner file in a fresh assessment, the file only), the kept copy of each
scanner file, and a phase 5a database opening unchanged."""
import hashlib
import sqlite3

from sqlalchemy import select

from app.db import AssessmentRow, ImportFileRow, ImportRow, ProjectRow, make_session_factory
from tests.conftest import csv_bytes, make_lab, upload


def _project(client, name="Acme Pay"):
    made = client.post("/api/projects", json={"name": name}).json()
    return made["id"], made["assessment_id"]


def test_rerun_brings_the_same_file_into_a_new_open_assessment_and_copies_nothing_else(client):
    pid, first = _project(client)
    imp = client.post("/api/import/demo", params={"assessment_id": first}).json()
    address = imp["addresses"][0]["address"]
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True})
    client.post(f"/api/import/{imp['id']}/verify")
    made = client.post(f"/api/assessments/{first}/rerun", json={"name": "Q4 again", "purpose": "release_check"}).json()
    new = client.get(f"/api/assessments/{made['id']}").json()
    assert new["project"]["id"] == pid and new["title"] == "Q4 again" and new["purpose"]["label"] == "Release check"
    assert new["status"]["key"] == "open" and new["file"]["filename"] == "acme-pay-cbom.json"
    assert new["import"]["id"] != imp["id"]
    assert [c["text"] for c in new["import"]["claims"]] == [c["text"] for c in imp["claims"]]
    # The file only: no Verify run, no results, and the address must be confirmed again.
    assert new["has_verify"] is False and new["counts"]["claims"] is None
    assert all(a["confirmed"] is False for a in new["import"]["addresses"])
    # The one it came from is untouched and still open.
    old = client.get(f"/api/assessments/{first}").json()
    assert old["status"]["key"] == "open" and old["has_verify"] is True


def test_rerun_works_on_a_closed_assessment_and_reads_the_kept_copy_of_an_uploaded_file(client):
    pid, first = _project(client)
    data = csv_bytes("localhost:9443, tls, protocol_versions, TLS1.3")
    r = client.post("/api/import/file", params={"filename": "mine.csv", "assessment_id": first}, content=data,
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    client.post(f"/api/assessments/{first}", json={"close": True, "signed_off_by": "Sam Lee"})
    made = client.post(f"/api/assessments/{first}/rerun").json()
    new = client.get(f"/api/assessments/{made['id']}").json()
    assert new["status"]["key"] == "open" and new["file"]["filename"] == "mine.csv"
    assert new["purpose"]["label"] == "Full review"                       # the box's default
    lab = client.app.state.lab
    with lab.db() as db:
        copies = db.scalars(select(ImportFileRow).order_by(ImportFileRow.id)).all()
        assert [c.sha256 for c in copies] == [hashlib.sha256(data).hexdigest()] * 2
        assert all(bytes(c.data) == data for c in copies)


def test_an_assessment_with_no_file_has_nothing_to_rerun(client):
    _, first = _project(client)
    r = client.post(f"/api/assessments/{first}/rerun")
    assert r.status_code == 409 and "no file" in r.json()["error"]["message"]


def test_a_file_from_before_phase_5b_reruns_only_when_it_is_a_bundled_demo_file(client):
    pid, first = _project(client)
    assert upload(client, "x.csv", csv_bytes("localhost:9443, tls, protocol_versions, TLS1.3")).status_code == 200
    lab = client.app.state.lab
    with lab.db() as db:
        # As before phase 5b: an import with no kept copy, in an assessment of this project.
        old = ImportRow(filename="theirs.csv", format="csv", is_demo=False)
        demo = ImportRow(filename="migration-demo.csv", format="csv", is_demo=True)
        db.add_all([old, demo])
        db.flush()
        a1 = AssessmentRow(project_id=pid, number=7, import_id=old.id)
        a2 = AssessmentRow(project_id=pid, number=8, import_id=demo.id)
        db.add_all([a1, a2])
        db.commit()
        a1_id, a2_id = a1.id, a2.id
    refused = client.post(f"/api/assessments/{a1_id}/rerun")
    assert refused.status_code == 409 and "Bring the file in again" in refused.json()["error"]["message"]
    made = client.post(f"/api/assessments/{a2_id}/rerun").json()
    assert client.get(f"/api/assessments/{made['id']}").json()["file"]["filename"] == "migration-demo.csv"


def test_a_phase_5a_database_opens_unchanged(tmp_path):
    """A database made before phase 5b has no purpose, sign-off or file-copy tables. It opens with its data as it was;
    the new tables are added empty and an older assessment shows no purpose."""
    lab = make_lab(tmp_path)
    try:
        made = lab.create_project("Before", None)
        lab.import_demo(assessment_id=made["assessment_id"])
    finally:
        lab.stop()
    path = tmp_path / "data" / "evidence-lab.sqlite3"
    if not path.exists():
        path = next((tmp_path / "data").glob("*.sqlite*"))
    con = sqlite3.connect(path)
    for table in ("assessment_details", "assessment_signoffs", "import_files"):
        for verb in ("update", "delete"):
            con.execute(f"DROP TRIGGER IF EXISTS {table}_no_{verb}")
        con.execute(f"DROP TABLE {table}")
    con.commit()
    con.close()
    factory = make_session_factory(path)
    with factory() as db:
        assert db.scalars(select(ProjectRow.name)).all() == ["Before"]
    lab = make_lab(tmp_path)
    try:
        view = lab.assessment_view(made["assessment_id"])
        assert view["purpose"] is None and view["file"]["filename"] == "acme-pay-cbom.json"
        assert view["status"]["key"] == "open"
        # Rerun still works for it: the demo file is bundled.
        again = lab.rerun_assessment(made["assessment_id"])
        assert lab.assessment_view(again["id"])["file"]["filename"] == "acme-pay-cbom.json"
    finally:
        lab.stop()


def test_raw_sql_cannot_change_or_delete_a_purpose_a_sign_off_or_a_kept_file(client):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    import pytest
    pid, first = _project(client)
    client.post("/api/import/demo", params={"assessment_id": first})
    client.post(f"/api/assessments/{first}", json={"close": True, "signed_off_by": "Sam Lee"})
    lab = client.app.state.lab
    for table, column in (("assessment_details", "purpose"), ("assessment_signoffs", "signed_off_by"), ("import_files", "filename")):
        with lab.db() as db:
            assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() >= 1
            for statement in (f"UPDATE {table} SET {column} = 'x'", f"DELETE FROM {table}"):
                with pytest.raises(DBAPIError, match="append-only"):
                    db.execute(text(statement))
                db.rollback()
