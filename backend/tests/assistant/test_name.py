"""Phase 6a: a person types their name once, and their decisions are recorded under it.

Until then a decision is recorded as "You", as before. The name is asked once (the Otto panel's first Confirm of a
decision, or Settings) and kept with the app's settings; the app has one login and does not check who is at the
keyboard, and says so. A decision already recorded keeps the name it was made under."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import OttoDecisionRow
from app.errors import BadRequest
from app.main import create_app
from app.otto import assurance
from app.web import models
from conftest import PASSWORD, free_port
from tests.assistant import assistant_walk as made
from tests.view_helpers import problems


@pytest.fixture
def lab(tmp_path, monkeypatch):
    started = made.start_lab(tmp_path, monkeypatch, record_prompts=False)
    yield started
    started.stop()


def test_until_a_name_is_typed_a_decision_is_recorded_as_you(lab):
    assert lab.decision_name() == "You"
    said = lab.decision_name_view()
    assert said["recorded_as"] == "You" and said["typed"] is False and said["value"] == "" and said["line"] == "Recorded as You, with the time."
    assert "one login" in said["note"] and "does not check who is at the keyboard" in said["note"]
    view = lab.assistant_view(lab.assessment_id, "checks")
    assert view["recorded_as"] == said and problems(view, models.AssistantView, "assistant") == []
    settings = lab.otto_view()
    assert settings["name"] == said and problems(settings, models.OttoSettingsView, "settings") == []


def test_a_typed_name_is_cleaned_kept_and_can_be_taken_back(lab):
    assert lab.set_decision_name("  Kevin\tSinguyen \n")["name"]["value"] == "Kevin Singuyen"
    assert lab.decision_name() == "Kevin Singuyen"
    said = lab.decision_name_view()
    assert said["typed"] is True and said["recorded_as"] == "Kevin Singuyen" and said["line"] == "Recorded as Kevin Singuyen, with the time."
    with pytest.raises(BadRequest) as too_long:
        lab.set_decision_name("x" * 61)
    assert "60 characters" in str(too_long.value) and lab.decision_name() == "Kevin Singuyen"
    with pytest.raises(BadRequest):
        lab.set_decision_name(None)
    # an empty name goes back to "You"
    assert lab.set_decision_name("   ")["name"]["typed"] is False and lab.decision_name() == "You"


@pytest.mark.needs_otto
def test_a_decision_is_recorded_under_the_typed_name_in_the_database_the_ledger_and_the_evidence(lab):
    pid = lab.plan.id
    first, second = [p["id"] for p in lab.otto_proposals(pid, ("check",))][:2]
    lab.otto_decide(pid, first, "accept")                       # before a name was typed
    lab.set_decision_name("Kevin Singuyen")
    lab.otto_decide(pid, second, "reject", "Not this quarter")
    lab.otto_decide(pid, first, "undo")
    with lab.db() as db:
        rows = list(db.scalars(select(OttoDecisionRow).where(OttoDecisionRow.plan_id == pid).order_by(OttoDecisionRow.id)))
        assert [(r.decision, r.by) for r in rows] == [("accept", "You"), ("reject", "Kevin Singuyen"), ("undo", "Kevin Singuyen")]
        objectives = {r.proposal_id: r.objective_id for r in rows}
    # the page words it with the name, and the earlier decision keeps the name it was made under
    shown = {p["id"]: p for p in lab.otto_proposals_view(pid)["proposals"]}
    assert shown[second]["decided_line"].startswith("Rejected by Kevin Singuyen on ")
    assert [row["by"] for row in shown[first]["history"]["rows"]] == ["You", "Kevin Singuyen"]
    # the assessment's Otto ledger, checked by the pinned record checker when each entry was written
    ledger = assurance.Ledger(lab.settings.data_dir, lab.assessment_id)
    said = " ".join(e["what"] for o in objectives.values() for e in ledger.about_proposal(o))
    assert "Kevin Singuyen" in said
    # the evidence part
    part = {p["id"]: p for p in lab.otto_proposals_evidence(pid)}
    assert [d["by"] for d in part[first]["decisions"]] == ["You", "Kevin Singuyen"] and part[second]["decisions"][0]["by"] == "Kevin Singuyen"
    # a name the record checker would not take can't be stored: it is one short printable line by the time it is kept
    lab.set_decision_name("Dr.\x00 Sam‮ Lee")
    assert lab.decision_name().isprintable() and len(lab.decision_name()) <= 60


def test_the_route_keeps_the_name_and_needs_the_login(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo", speed_rounds=25, speed_repeats=4)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/otto/name", json={"name": "Sam Lee"}).status_code == 401
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        kept = client.post("/api/otto/name", json={"name": "Sam Lee"})
        assert kept.status_code == 200 and kept.json()["name"]["recorded_as"] == "Sam Lee"
        assert client.get("/api/otto").json()["name"]["value"] == "Sam Lee"
        assert client.post("/api/otto/name", json={"name": "x" * 61}).status_code == 422
        assert client.post("/api/otto/name", json={}).status_code == 422
        assert client.post("/api/otto/name", json={"name": ""}).json()["name"]["recorded_as"] == "You"
