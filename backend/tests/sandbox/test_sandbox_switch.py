"""Sandbox research (prototype): the switch. Off by default; on only on a marked computer, in isolated mode, with Otto
installed; the second tick only with the switch on and Live Otto ready; two spending limits; and with the switch off
nothing of it counts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import PASSWORD, make_lab
from sandbox_helpers import sandbox_lab, turn_on

from app.db import OttoResearchRow
from app.errors import BadRequest, Conflict
from app.otto import model
from app.web import models


def _section(lab) -> dict:
    view = lab.otto_view()
    models.OttoSettingsView.model_validate(view)
    return view["sandbox"]


def test_it_is_off_by_default_and_cannot_be_turned_on_on_a_computer_that_is_not_marked(tmp_path):
    lab = make_lab(tmp_path)                                   # no mark, demo mode: an ordinary install
    try:
        part = _section(lab)
        assert part["switch"]["on"] is False and part["switch"]["can_turn_on"] is False
        assert any("not marked" in reason for reason in part["switch"]["blocked_reasons"])
        assert part["by_itself"]["on"] is False and part["by_itself"]["can_turn_on"] is False
        assert part["spent_line"] is None and "off" in part["status_line"]
        assert lab.sandbox_on() is False and lab.sandbox_by_itself() is False
        with pytest.raises(Conflict) as refused:
            lab.set_sandbox(on=True)
        assert "can't be turned on here" in str(refused.value) and "not marked" in str(refused.value)
        assert lab.sandbox_on() is False                       # the refusal stored nothing
    finally:
        lab.stop()


@pytest.mark.parametrize("missing, word", [("marked", "not marked"), ("isolated", "isolated mode"), ("otto", "Otto")])
def test_each_of_the_three_conditions_is_needed_and_named(tmp_path, monkeypatch, missing, word):
    lab = sandbox_lab(tmp_path, monkeypatch, **{missing: False})
    try:
        reasons = _section(lab)["switch"]["blocked_reasons"]
        assert len(reasons) == 1 and word in reasons[0]
        with pytest.raises(Conflict):
            lab.set_sandbox(on=True)
        assert lab.sandbox_on() is False
    finally:
        lab.stop()


def test_where_all_three_hold_it_turns_on_and_off_and_off_ends_a_research_run(tmp_path, monkeypatch):
    lab = sandbox_lab(tmp_path, monkeypatch)
    try:
        assert _section(lab)["switch"] == {"label": "Sandbox research", "on": False, "can_turn_on": True, "blocked_reasons": []}
        part = lab.set_sandbox(on=True)["sandbox"]
        assert part["switch"]["on"] is True and lab.sandbox_on() is True
        assert part["spent_line"] and "0.00 of 10.00 US dollars" in part["spent_line"]
        stopped = []
        monkeypatch.setattr(lab, "stop_research", lambda: stopped.append(True))
        part = lab.set_sandbox(on=False)["sandbox"]
        assert part["switch"]["on"] is False and lab.sandbox_on() is False and stopped == [True]
    finally:
        lab.stop()


def test_a_switch_left_on_stops_counting_when_a_condition_no_longer_holds(tmp_path, monkeypatch):
    lab = sandbox_lab(tmp_path, monkeypatch)
    try:
        turn_on(lab)
        assert lab.sandbox_on() is True
        monkeypatch.setattr(lab, "mode", type(lab.mode)("demo", "Demo mode.", "Docker is not running.", False, None, None))
        assert lab.sandbox_on() is False                       # the stored value is still "on"; it no longer counts
        part = _section(lab)
        assert part["switch"]["on"] is False and part["switch"]["blocked_reasons"] == ["It needs isolated mode. Docker is not running."]
    finally:
        lab.stop()


def test_the_tick_needs_the_switch_on_and_live_otto_ready(tmp_path, monkeypatch):
    lab = sandbox_lab(tmp_path, monkeypatch, key=True)
    try:
        with pytest.raises(Conflict) as refused:
            lab.set_sandbox(by_itself=True)                    # the switch is off
        assert "only while Sandbox research is on" in str(refused.value)
        turn_on(lab)
        part = _section(lab)
        assert part["by_itself"]["can_turn_on"] is False and "Live Otto" in part["by_itself"]["blocked_reason"]
        with pytest.raises(Conflict) as refused:
            lab.set_sandbox(by_itself=True)                    # Live Otto is off
        assert "Live Otto" in str(refused.value)
        lab.set_live_otto(on=True)
        part = lab.set_sandbox(by_itself=True)["sandbox"]
        assert part["by_itself"]["on"] is True and lab.sandbox_by_itself() is True
        assert "by itself" in part["status_line"]
        lab.set_live_otto(on=False)                            # Live Otto goes off: the tick no longer counts
        assert lab.sandbox_by_itself() is False and _section(lab)["by_itself"]["on"] is False
        lab.set_live_otto(on=True)
        assert lab.sandbox_by_itself() is True
        lab.set_sandbox(on=False)                              # the tick never outlives the switch
        lab.set_sandbox(on=True)
        assert lab.sandbox_by_itself() is False
    finally:
        lab.stop()


def test_the_two_limits_are_saved_as_typed_and_a_bad_amount_is_refused(tmp_path, monkeypatch):
    lab = sandbox_lab(tmp_path, monkeypatch)
    try:
        part = _section(lab)
        assert (part["run_limit"]["value"], part["day_limit"]["value"]) == ("5.00", "10.00")      # Kevin's decision 4
        part = lab.set_sandbox(run_limit="3.5", day_limit="12")["sandbox"]
        assert (part["run_limit"]["value"], part["day_limit"]["value"]) == ("3.50", "12.00")
        assert lab.sandbox_limits() == (3_500_000_000, 12_000_000_000)
        for bad in ("", "0", "-1", "abc", "1.234", "1001", "1e3", "1,5"):
            with pytest.raises(BadRequest):
                lab.set_sandbox(day_limit=bad)
        assert lab.sandbox_limits() == (3_500_000_000, 12_000_000_000)
    finally:
        lab.stop()


def _research_row(lab, kind: str, run_key: str, at: datetime, *, live: bool = True, limit: int = 0, spent: int | None = None) -> None:
    with lab.db() as db:
        plan_id = lab.ensure_plan(lab.import_demo()["id"])["id"] if not hasattr(lab, "_test_plan") else lab._test_plan
        lab._test_plan = plan_id
        db.add(OttoResearchRow(plan_id=plan_id, run_key=run_key, kind=kind, at=at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                               by="You", lookup_id=0, advisories=[], live=live, limit_nano=limit, installed_first=[], exit_code=None,
                               pack_version=None, output=[], sandbox=True, spent_nano=spent))
        db.commit()


def test_a_days_spending_is_added_up_from_the_runs_own_records_and_a_running_run_counts_whole(tmp_path, monkeypatch):
    lab = sandbox_lab(tmp_path, monkeypatch)
    try:
        turn_on(lab)
        now = datetime.now(timezone.utc)
        dollar = model.NANO
        _research_row(lab, "started", "a", now - timedelta(hours=30), limit=5 * dollar)          # older than a day: not counted
        _research_row(lab, "finished", "a", now - timedelta(hours=29), spent=4 * dollar)
        _research_row(lab, "started", "b", now - timedelta(hours=3), limit=5 * dollar)
        _research_row(lab, "finished", "b", now - timedelta(hours=2), spent=dollar // 2)
        _research_row(lab, "started", "c", now - timedelta(hours=1), limit=5 * dollar, live=False)   # recorded answers only: free
        _research_row(lab, "finished", "c", now - timedelta(minutes=50), live=False, spent=0)
        assert lab.sandbox_spent_today(now) == dollar // 2
        assert lab.sandbox_run_limit(now) == 5 * dollar                                           # 10 - 0.5 is more than one run's 5
        _research_row(lab, "started", "d", now - timedelta(minutes=5), limit=5 * dollar)          # still going: its whole limit
        assert lab.sandbox_spent_today(now) == dollar // 2 + 5 * dollar
        assert lab.sandbox_run_limit(now) == 10 * dollar - (dollar // 2 + 5 * dollar)             # what is left of the day
        lab.set_sandbox(day_limit="5")
        assert lab.sandbox_run_limit(now) == 0                                                    # the day's limit is reached
        assert "5.50 of 5.00 US dollars" in _section(lab)["spent_line"]
    finally:
        lab.stop()


def test_the_route_needs_a_login_and_answers_with_the_whole_settings_view(anon_client):
    assert anon_client.post("/api/otto/sandbox", json={"on": True}).status_code == 401
    assert anon_client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
    refused = anon_client.post("/api/otto/sandbox", json={"on": True})
    assert refused.status_code == 409 and "can't be turned on here" in refused.json()["error"]["message"]
    saved = anon_client.post("/api/otto/sandbox", json={"day_limit": "7"})
    assert saved.status_code == 200
    models.OttoSettingsView.model_validate(saved.json())
    assert saved.json()["sandbox"]["day_limit"]["value"] == "7.00" and saved.json()["sandbox"]["switch"]["on"] is False
    assert anon_client.post("/api/otto/sandbox", json={"on": "yes"}).status_code == 422       # a switch is true or false
