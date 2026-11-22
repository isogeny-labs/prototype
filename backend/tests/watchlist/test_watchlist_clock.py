"""The Watch list's clock (sandbox research): it looks by itself, about once a day, only while the switch is on. A look
by itself is the look a click makes, under the clock's own name. It never asks Claude, starts no container, and by
itself starts no research run. The tests move time by hand: the clock's own thread is tried once, at the end."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from conftest import csv_bytes, make_lab
from sqlalchemy import select
from watch_helpers import ECDSA_ONLY, ITEM, record, watch_lab, with_events, write_source

from app.changewatch import clock
from app.db import OttoLookupRow
from app.otto import lookup, model
from app.present import watchlist as words

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
FIXED = [{"introduced": "0"}, {"fixed": "0.13.3"}]


def _looks(lab) -> list[tuple[int, str]]:
    with lab.db() as db:
        return [(r.plan_id, r.by) for r in db.scalars(select(OttoLookupRow).order_by(OttoLookupRow.id)).all()]


def _second_assessment(lab) -> int:
    imp = lab.import_file("more.csv", csv_bytes(*ECDSA_ONLY))
    return lab.ensure_plan(imp["id"])["id"]


def test_with_the_switch_off_the_clock_does_nothing_and_an_unmarked_computer_has_no_clock_at_all(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path / "a", monkeypatch, on=False)
    try:
        assert lab.watch_clock_tick(NOW) == {"did": "off", "looked": [], "failed": {}, "started": None}
        assert _looks(lab) == [] and lab.watch_clock_next(pid) is None
    finally:
        lab.stop()
    plain = make_lab(tmp_path / "b")  # an ordinary install: no mark
    try:
        assert plain._clock_thread is None and plain.watch_clock_tick(NOW)["did"] == "off"
    finally:
        plain.stop()


def test_it_looks_at_once_where_there_was_no_look_then_not_again_for_a_day(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        first = lab.watch_clock_tick(datetime.now(timezone.utc))
        assert first == {"did": "looked", "looked": [pid], "failed": {}, "started": None}
        assert _looks(lab) == [(pid, "The watch clock")]
        view = lab.watch_list_view(pid)
        assert view["looked_line"].endswith(", by itself.") and view["items"][0]["key"] == ITEM
        # (the helper starts the app without the clock's thread, and the page says so; a look still shows when it was)
        assert view["next_line"] == words.CLOCK_NOT_RUNNING
        assert lab.watch_clock_tick(datetime.now(timezone.utc))["did"] == "nothing"  # a minute later: not due
        assert lab.watch_clock_tick(datetime.now(timezone.utc) + timedelta(hours=23))["did"] == "nothing"
        later = lab.watch_clock_tick(datetime.now(timezone.utc) + timedelta(hours=24, minutes=1))
        assert later["did"] == "looked" and _looks(lab) == [(pid, "The watch clock")] * 2
    finally:
        lab.stop()


def test_a_look_by_a_person_counts_too_so_the_clock_waits_a_day_from_it(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        assert lab.watch_clock_tick(datetime.now(timezone.utc) + timedelta(hours=1))["did"] == "nothing"
        assert _looks(lab) == [(pid, "You")]
    finally:
        lab.stop()


def test_in_one_round_a_library_two_assessments_name_is_asked_about_once(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        other = _second_assessment(lab)
        asked = []
        real = lookup.RecordedSource.answers
        monkeypatch.setattr(
            lookup.RecordedSource, "answers", lambda self, package: asked.append(package.key) or real(self, package)
        )
        done = lab.watch_clock_tick(datetime.now(timezone.utc))
        assert done["looked"] == [pid, other] and asked == ["PyPI__ecdsa"]
        assert _looks(lab) == [(pid, "The watch clock"), (other, "The watch clock")]
    finally:
        lab.stop()


def test_a_closed_an_archived_and_an_assessment_with_nothing_to_ask_are_not_looked_at(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        closed, archived = _second_assessment(lab), _second_assessment(lab)
        lab.update_assessment(lab.assessment_for(plan_id=closed).id, {"close": True, "signed_off_by": "Test Closer"})
        lab.update_assessment(lab.assessment_for(plan_id=archived).id, {"archived": True})
        nothing = lab.ensure_plan(lab.import_demo()["id"])[
            "id"
        ]  # the Acme Pay file: no library the source keeps by name
        done = lab.watch_clock_tick(datetime.now(timezone.utc))
        assert done["looked"] == [pid] and done["failed"] == {}
        assert {plan for plan, _ in _looks(lab)} == {pid} and nothing not in done["looked"]
    finally:
        lab.stop()


def test_a_look_that_got_no_answer_records_nothing_says_so_and_waits_longer_each_time(tmp_path, monkeypatch):
    monkeypatch.setattr(
        clock, "START_DELAY_SECONDS", 3600.0
    )  # the clock's thread is there and sleeps; the test moves time by hand
    lab, pid, _ = watch_lab(tmp_path, monkeypatch, watch_clock=True)
    try:

        def down(self, package):
            raise lookup.LookupError_("OSV (osv.dev) could not be reached (TimeoutError). Nothing was changed.")

        real = lookup.RecordedSource.answers
        monkeypatch.setattr(lookup.RecordedSource, "answers", down)
        start = datetime.now(timezone.utc)
        first = lab.watch_clock_tick(start)
        assert first["did"] == "looked" and first["looked"] == [] and "could not be reached" in first["failed"][pid]
        assert _looks(lab) == []  # nothing is recorded as found, or as looked
        said = lab.watch_clock_next(pid)
        assert (
            said.startswith("Couldn't look by itself on ")
            and "could not be reached" in said
            and "tried again at about" in said
        )
        assert lab.watch_clock_tick(start + timedelta(minutes=59))["did"] == "nothing"  # one hour's wait
        second = lab.watch_clock_tick(start + timedelta(minutes=61))
        assert pid in second["failed"]
        assert lab.watch_clock_tick(start + timedelta(minutes=61 + 119))["did"] == "nothing"  # then two
        monkeypatch.setattr(lookup.RecordedSource, "answers", real)
        third = lab.watch_clock_tick(start + timedelta(minutes=61 + 121))
        assert third["looked"] == [pid] and third["failed"] == {} and _looks(lab) == [(pid, "The watch clock")]
        assert "Couldn't look" not in lab.watch_clock_next(pid)  # an answer clears it
    finally:
        lab.stop()


def test_the_day_a_fix_is_published_the_clock_finds_it_and_the_item_says_so(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        start = datetime.now(timezone.utc)
        lab.watch_clock_tick(start)
        write_source(folder, [with_events(record(), FIXED)])  # (made up: the next day at the source)
        lab.watch_clock_tick(start + timedelta(hours=25))
        [row] = lab.watch_list_view(pid)["items"]
        assert row["status"]["key"] == "fix_published" and row["new"] is True
        assert row["panel"]["history"]["lines"][-1].endswith(": the source names a fixed version: 0.13.3.")
        assert row["panel"]["test"]["line"].startswith("A test can now be designed and proven")
    finally:
        lab.stop()


def test_by_itself_the_clock_only_looks_no_claude_no_container_no_research_run(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        write_source(
            folder, [with_events(record(), FIXED)]
        )  # a fix is there from the first look: a test could be tried

        def never(*args, **kwargs):
            raise AssertionError("the clock must not do this by itself")

        monkeypatch.setattr(model.OttoModel, "ask", never, raising=False)
        monkeypatch.setattr(lab, "start_research", never)
        monkeypatch.setattr(lab.component_runner, "run_job", never)
        done = lab.watch_clock_tick(datetime.now(timezone.utc))
        assert done["looked"] == [pid] and done["started"] is None and lab.jobs.live(pid) == []
    finally:
        lab.stop()


def test_one_round_at_a_time(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        assert lab._clock_round.acquire(blocking=False)
        try:
            assert lab.watch_clock_tick(datetime.now(timezone.utc))["did"] == "busy" and _looks(lab) == []
        finally:
            lab._clock_round.release()
    finally:
        lab.stop()


def test_a_stretch_with_no_look_is_said_in_the_history(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        lab.watch_list_look(pid)
        with lab.db() as db:  # (the rows are add-only: the second look is read as made a week later)
            rows = db.scalars(select(OttoLookupRow).order_by(OttoLookupRow.id)).all()
            first, second = rows[0].at, rows[1].at
        week = (
            (datetime.fromisoformat(second.replace("Z", "+00:00")) + timedelta(days=7))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        real = lab._watch_looks

        def later(db, plan_id):
            found = real(db, plan_id)
            db.expunge_all()
            found[1].at = week
            return found

        monkeypatch.setattr(lab, "_watch_looks", later)
        [row] = lab.watch_list_view(pid)["items"]
        assert any(line.startswith("No look was made between ") for line in row["panel"]["history"]["lines"]), (
            first,
            row["panel"]["history"],
        )
    finally:
        lab.stop()


def test_the_clocks_own_thread_looks_shortly_after_the_app_starts_and_stops_with_it(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "START_DELAY_SECONDS", 0.05)
    monkeypatch.setattr(clock, "TICK_SECONDS", 0.05)
    lab, pid, _ = watch_lab(tmp_path, monkeypatch, on=False, watch_clock=True)
    try:
        assert lab._clock_thread is not None and lab._clock_thread.is_alive()
        time.sleep(0.4)
        assert _looks(lab) == []  # the switch is off: the thread runs and does nothing
        lab.set_sandbox(on=True)
        for _ in range(100):
            if _looks(lab):
                break
            time.sleep(0.05)
        assert _looks(lab) == [(pid, "The watch clock")]
        assert lab.watch_list_view(pid)["next_line"].startswith(
            "It is looked at again by itself, about once a day: next at about "
        )
    finally:
        thread = lab._clock_thread
        lab.stop()
        assert lab._clock_thread is None and thread is not None and not thread.is_alive()
