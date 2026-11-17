"""Phase 5c, step 5: Otto on the customer's side. Advisories of the installed packs, Add new checks (a person's
click; it runs nothing), the lock entry in the assessment's Otto ledger before any run, one entry per reviewed run,
and what happens when Otto is not installed or the assessment is closed."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

import otto_helpers as helpers
from app.config import Settings
from app.db import OttoCheckRow, PlanItemRow, ReviewRow, TestRunRow, TestSpecRow
from app.errors import Conflict
from app.main import create_app
from app.otto import assurance, harness, model, packs
from conftest import PASSWORD, demo_plan, free_port, play_back_speed

pytestmark = [pytest.mark.needs_otto]
BANNED = ("secure", "score", "severity", "critical", "time to hack")


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def _pack_one():
    return helpers.make_pack("2026.11.1", None, [helpers.pack_advisory(),
                                                 helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")])


@pytest.fixture
def otto_lab(tmp_path, monkeypatch):
    """A demo-mode Lab with one pack in its updates folder (not installed yet) and the demo plan made."""
    first, public = _pack_one()
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    lab.plan = demo_plan(lab)
    yield lab
    lab.stop()


def _installed(lab):
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    return lab


def test_with_no_pack_the_page_says_so_and_nothing_can_be_added(otto_lab):
    view = otto_lab.advisories_view(otto_lab.plan.id)
    assert view["rows"] == [] and "No test pack is installed yet" in view["empty"]
    assert view["add"]["can"] is False and view["add"]["count"] == 0 and "Install one in Settings" in view["add"]["blocked_reason"]
    with pytest.raises(Conflict):
        otto_lab.add_new_checks(otto_lab.plan.id)


def test_the_page_lists_every_advisory_of_the_installed_packs(otto_lab):
    view = _installed(otto_lab).advisories_view(otto_lab.plan.id)
    assert [r["id"] for r in view["rows"]] == ["CVE-2022-21449", "CVE-2019-14853"]
    ready, none = view["rows"]
    assert ready["name"] == "Blank signature accepted" and ready["test"] == {"key": "ready", "label": "Test ready", "tone": "pass", "reason": ready["test"]["reason"]}
    assert ready["fits"] == ["acme-sign 1.4.2"] and ready["result"]["label"] == "Not added yet" and ready["pack"] == "2026.11.1"
    assert none["test"]["label"] == "No test yet" and none["result"]["label"] == "No check" and none["fits"] == []
    assert none["panel"]["test"] is None and none["panel"]["no_test"]["reason"].startswith("No test yet")
    panel = ready["panel"]
    assert panel["publisher"]["tag"] == "from the advisory, not a result" and panel["publisher"]["href"].startswith("https://openjdk.org/")
    assert panel["test"]["question"] and "accepts every signature" in panel["test"]["control"] and "Any wrong answer means Failed" in panel["test"]["rule"]
    assert any("acme-sign 1.4.2 (affected): 2 of 64 cases wrong" in line for line in panel["test"]["trial"]["lines"])
    assert panel["test"]["ledger"]["entries"] and panel["here"]["rows"][0]["status"] == "Not added yet"
    assert panel["fix"]["label"] == "From Otto" and panel["fix"]["state"] == "proven" and panel["related_key"] == "advisory:CVE-2022-21449"
    assert [s["source"] for s in panel["claude"]["steps"]] == ["recorded", "recorded", "recorded"]
    assert view["add"] == {"button": "Add new checks (1)", "count": 1, "can": True, "blocked_reason": None, "note": view["add"]["note"]}
    assert view["standing_line"] == "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
    assert view["answers_line"] == "Answers written for a test, 17 November 2026" and view["otto"]["installed"] is True
    shown = [t for t in _texts(view) if t != view["standing_line"]]
    assert not any(word in t.lower() for t in shown for word in BANNED)


def test_add_new_checks_locks_and_adds_and_runs_nothing(otto_lab):
    lab, plan_id = _installed(otto_lab), otto_lab.plan.id
    before = len(lab.plan_view(plan_id)["tests"])
    view = lab.add_new_checks(plan_id)
    tests = lab.plan_view(plan_id)["tests"]
    added = tests[-1]
    assert len(tests) == before + 1 and added["title"] == "Advisory check: Blank signature accepted (CVE-2022-21449)"
    assert added["origin"] == "added" and added["status"] == "not_run"
    assert view["add"]["can"] is False and view["add"]["count"] == 0 and "already in the test plan" in view["add"]["blocked_reason"]
    row = view["rows"][0]
    assert row["result"]["label"] == "Not run yet" and row["panel"]["here"]["rows"][0]["status"] == "Not run yet"
    assert row["panel"]["here"]["rows"][0]["checks_link"] == {"page": "checks", "item": f"test-{added['id']}"}
    with lab.db() as db:
        assert db.scalar(select(TestRunRow.id).where(TestRunRow.plan_item_id == added["id"])) is None      # it ran nothing
        check = db.scalars(select(OttoCheckRow)).one()
        spec_row = db.get(TestSpecRow, check.spec_hash)
        assert spec_row.proposed_by == "isogeny.otto-pack/1" and check.pack_version == "2026.11.1" and check.plan_item_id == added["id"]
        spec = json.loads(spec_row.canonical)
        assert spec["inputs"]["advisory"]["pack_fingerprint"] == check.pack_fingerprint
    with pytest.raises(Conflict):
        lab.add_new_checks(plan_id)                                         # nothing left to add
    # the check shows on Checks, under Encryption tests, with its advisory in the name
    groups = {g["key"]: g for g in lab.checks_view(plan_id)["groups"]}
    assert any(r["name"].startswith("Advisory check: Blank signature accepted") for r in groups["encryption"]["rows"])


def test_the_lock_entry_is_in_the_ledger_before_the_first_run(otto_lab):
    lab, plan_id = _installed(otto_lab), otto_lab.plan.id
    lab.add_new_checks(plan_id)
    assessment = lab.assessment_for(plan_id=plan_id)
    book = assurance.Ledger(lab.settings.data_dir, assessment.id)
    with lab.db() as db:
        check = db.scalars(select(OttoCheckRow)).one()
    entries = book.entries()
    assert [e["kind"] for e in entries] == ["objective"] and book.record_id(entries[0]) == check.objective_id
    params = entries[0]["payload"]["verifier"]["params"]
    assert params["kind"] == "run" and params["test"] == check.spec_hash and params["design"] == check.design_sha256
    assert params["pack"] == check.pack_fingerprint and params["advisory"] == "CVE-2022-21449"
    lab.run_test(plan_id, check.plan_item_id)
    lab.wait_until_idle(plan_id, 240)
    entries = book.entries()
    assert [e["kind"] for e in entries] == ["objective", "claim", "verdict"]            # the lock came first; the chain shows it
    with lab.db() as db:
        run = db.scalars(select(TestRunRow).where(TestRunRow.plan_item_id == check.plan_item_id)).one()
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).one()
    artifact = entries[1]["payload"]["artifact"]
    assert artifact["test"] == check.spec_hash and artifact["run_id"] == run.id and artifact["run_sha256"] == review.run_sha256
    assert artifact["proposed_by"] == "isogeny.otto-pack/1" and artifact["reviewer"] == "isogeny.rule-reviewer/1" and artifact["phase"] == "first"
    assert entries[2]["payload"]["status"] == "accept"
    # the ledger holds no result: not the review's code, not the word
    text = json.dumps(entries)
    assert review.code == "failed" and '"failed"' not in text and "Failed" not in text and "passed" not in text.lower()
    assert book.audit() == []
    # the page repeats the reviewer's result, and lists the ledger entries for this check
    row = lab.advisories_view(plan_id)["rows"][0]
    assert row["result"] == {"key": "fail", "label": "Failed", "tone": "fail", "text": None}
    here = row["panel"]["here"]["rows"][0]
    assert here["result"]["label"] == "Failed" and here["result"]["plain"].startswith("acme-sign 1.4.2 got 2 of the 64")
    assert here["evidence_link"] == {"page": "evidence", "item": f"test-{check.plan_item_id}"}
    # each entry is named in plain words; Otto's own record names (one is "verdict") never reach the page
    assert [e["kind"] for e in here["ledger"]["entries"]] == ["Opened", "Recorded", "Record checked"]
    assert "verdict" not in json.dumps(row["panel"]).lower()
    assert row["panel"]["fix"]["here"]["label"] == "View in Fixes"


@pytest.mark.slow
def test_every_retest_and_proof_run_of_the_check_gets_its_own_entry(otto_lab):
    lab, plan_id = _installed(otto_lab), otto_lab.plan.id
    lab.add_new_checks(plan_id)
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    book = assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=plan_id).id)
    phases = [e["payload"]["artifact"]["phase"] for e in book.entries() if e["kind"] == "claim"]
    assert phases == ["first", "retest"] and all(e["payload"]["status"] == "accept" for e in book.entries() if e["kind"] == "verdict")
    row = lab.advisories_view(plan_id)["rows"][0]
    assert row["result"]["label"] == "Passed" and row["panel"]["here"]["rows"][0]["result"]["component"] == "acme-sign 1.4.3"
    assert book.audit() == []


def test_a_librarys_fix_is_never_proposed_for_another_program_that_fails_the_same_check(otto_lab):
    """An advisory is about one library, and its publisher's fixed version is a version of that library. Another
    program can fail the same check (Java fails the check made for an elliptic advisory): the pack holds no fix
    for it, and Fixes says so. It never proposes updating a library the program does not use."""
    lab = _installed(otto_lab)
    lab.add_new_checks(lab.plan.id)
    with lab.db() as db:
        item_id = db.scalars(select(OttoCheckRow.plan_item_id)).one()
        own = lab._otto_pack_fix(db, item_id, "acme-sign")               # the test pack's advisory is about acme-sign
        other = lab._otto_pack_fix(db, item_id, "openjdk")
        unnamed = lab._otto_pack_fix(db, item_id)
    assert own["kind"] == "update" and own["library"] == "acme-sign" and own["state"] == "proven" and own == unnamed
    assert other["kind"] == "none" and other["state"] == "none" and other["summary"] is None and other["quote"] is None
    assert "The advisory is about acme-sign" in other["reason"] and "holds no fix for openjdk" in other["reason"]


OTTO_TABLES = {"otto_packs": "version", "otto_checks": "advisory_id", "otto_steps": "answer"}


@pytest.mark.parametrize("table", OTTO_TABLES)
def test_raw_sql_cannot_change_or_delete_ottos_records(otto_lab, table):
    """An installed pack, an added check and a Claude step are kept for good: the database itself refuses a change or
    a removal (tests/test_changes.py counts these three tables as covered here)."""
    lab = _installed(otto_lab)
    lab.add_new_checks(lab.plan.id)
    step = model.Step(step="write_fix", source="recorded", model=None, prompt="a prompt", answer="an answer",
                      prompt_sha256=model.sha256_text("a prompt"), answer_sha256=model.sha256_text("an answer"), input_tokens=0,
                      output_tokens=0, cost_nano_usd=0, at="2026-11-17T12:00:00Z", how="Written for a test, not an answer from Claude")
    lab.otto_record_step(lab.plan.id, "CVE-2022-21449", step, "refused", "Written for a test.")
    with lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {OTTO_TABLES[table]} = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


def test_without_otto_a_check_cannot_be_added_and_an_added_one_cannot_run(otto_lab, monkeypatch):
    lab, plan_id = _installed(otto_lab), otto_lab.plan.id
    missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
    lab.add_new_checks(plan_id)                       # added while Otto was here
    with lab.db() as db:
        item_id = db.scalars(select(OttoCheckRow.plan_item_id)).one()
    monkeypatch.setattr(harness, "status", lambda *a, **k: missing)
    view = lab.advisories_view(plan_id)
    assert view["otto"]["installed"] is False and "Otto is not installed on this computer" in view["otto"]["line"]
    assert "could not be recorded" in view["otto"]["line"]          # the reason, once, in the Otto line
    assert view["add"]["can"] is False and view["add"]["blocked_reason"] == "Otto is not installed on this computer, so nothing can be added."
    with pytest.raises(Conflict) as refused:
        lab.add_new_checks(plan_id)
    assert "Otto is not installed on this computer" in str(refused.value)
    lab.run_test(plan_id, item_id)
    lab.wait_until_idle(plan_id, 240)
    result = next(r for r in lab.lab_view(plan_id)["rows"] if r["item_id"] == item_id)["result"]
    assert result["label"] == "Couldn't run (Otto is not installed on this computer)" and "no result either way" in result["plain"]
    # every other test still runs as before
    lab.run_test(plan_id, lab.plan.item["bad_signatures"])
    lab.wait_until_idle(plan_id, 240)
    assert next(r for r in lab.lab_view(plan_id)["rows"] if r["kind"] == "bad_signatures")["result"]["label"] == "Failed"
    settings = lab.otto_view()
    assert settings["harness"]["installed"] is False and "can't be added or run" in settings["harness"]["line"]


def test_a_check_removed_from_the_plan_can_be_added_back_with_its_lock(otto_lab):
    lab, plan_id = _installed(otto_lab), otto_lab.plan.id
    lab.add_new_checks(plan_id)
    with lab.db() as db:
        check = db.scalars(select(OttoCheckRow)).one()
    lab.remove_test(plan_id, check.plan_item_id)
    view = lab.advisories_view(plan_id)
    assert view["add"]["count"] == 1 and view["rows"][0]["result"]["label"] == "Not added yet"
    lab.add_new_checks(plan_id)
    with lab.db() as db:
        assert db.get(PlanItemRow, check.plan_item_id).removed is False
        assert len(db.scalars(select(OttoCheckRow)).all()) == 1            # the same check, the same lock entry
    book = assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=plan_id).id)
    assert [e["kind"] for e in book.entries()] == ["objective"]


def _client(tmp_path, monkeypatch):
    first, public = _pack_one()
    updates = tmp_path / "updates"
    updates.mkdir()
    (updates / "2026.11.1.json").write_bytes(first)
    helpers.trust(monkeypatch, tmp_path, [public])
    settings = Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo", speed_rounds=25, speed_repeats=4,
                        otto_updates_dir=updates, otto_recorded_dir=tmp_path / "recorded")
    return TestClient(create_app(settings))


def test_the_routes_and_a_closed_assessment(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/otto").status_code == 401                       # every route needs the login
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        assert client.get("/api/otto").json()["packs"]["installed"] == []
        found = client.post("/api/otto/packs/check").json()
        assert found["packs"]["update"]["version"] == "2026.11.1"
        assert client.post("/api/otto/packs/install", json={"version": "2026.11.9"}).status_code == 409
        assert client.post("/api/otto/packs/install", json={"version": "2026.11.1"}).json()["packs"]["installed"][0]["version"] == "2026.11.1"
        assert client.post("/api/otto/live", json={"limit": "5"}).json()["live"]["limit"]["value"] == "5.00"
        assert client.post("/api/otto/live", json={"limit": "nonsense"}).status_code == 422
        imp = client.post("/api/import/demo").json()
        plan = client.post(f"/api/import/{imp['id']}/plan").json()
        view = client.get(f"/api/plans/{plan['id']}/advisories").json()
        assert view["add"]["count"] == 1 and len(view["rows"]) == 2
        added = client.post(f"/api/plans/{plan['id']}/advisories/add").json()
        assert added["add"]["count"] == 0 and added["rows"][0]["result"]["label"] == "Not run yet"
        # a second pack arrives after the assessment is closed: the closed assessment keeps showing what it had
        client.post(f"/api/assessments/{imp['assessment_id']}", json={"close": True, "signed_off_by": "Sam Lee"})
        closed = client.get(f"/api/plans/{plan['id']}/advisories").json()
        assert closed["add"]["can"] is False and "closed" in closed["add"]["blocked_reason"] and "when this assessment was closed" in closed["packs_line"]
        refused = client.post(f"/api/plans/{plan['id']}/advisories/add")
        assert refused.status_code == 409 and refused.json()["error"]["message"] == "This assessment is closed. Start a new one to continue."
        assert client.get(f"/api/plans/{plan['id']}/related", params={"key": "advisory:CVE-2022-21449"}).status_code == 200


def test_a_closed_assessment_shows_the_packs_it_had_when_it_was_signed_off(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()], key)
    one = packs.read_envelope(first, {public: (helpers.SIGNER, False)})
    second, _ = helpers.make_pack("2026.11.2", one.fingerprint, [helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",))], key)
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first, "2026.11.2.json": second}, [public])
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        assessment = lab.assessment_for(plan_id=plan.id)
        lab.update_assessment(assessment.id, {"close": True, "signed_off_by": "Sam Lee", "note": None})
        lab.install_pack("2026.11.2")                                      # the installation moves on
        closed = lab.advisories_view(plan.id)
        assert [r["id"] for r in closed["rows"]] == ["CVE-2022-21449"] and "2026.11.2" not in closed["packs_line"]
        newer = demo_plan(lab)                                             # a new assessment sees both packs
        assert [r["id"] for r in lab.advisories_view(newer.id)["rows"]] == ["CVE-2022-21449", "CVE-2024-42460"]
        assert lab.advisories_view(newer.id)["add"]["count"] == 2
    finally:
        lab.stop()
