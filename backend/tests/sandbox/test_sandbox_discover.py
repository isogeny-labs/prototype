"""Sandbox research in the app: which advisories can be tried on public copies from a registry, what the box says
before the click, what the research command is handed, the limits, and the second tick.

With the switch off the app is exactly what it was: the same rows, the same words, the same command."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sandbox_helpers import sandbox_lab, turn_on
from sqlalchemy import select

from app.db import OttoResearchRow
from app.otto import model
from app.present import lookup as words
from app.present import watchlist as watch_words
from tools import research_demo

ID = "CVE-2021-43572"
# A stand-in for the research command (the real one needs Docker; tests/sandbox/test_sandbox_real.py runs it): it writes
# down what it was started with, says it spent 1.25 US dollars, and ends as a run that settled nothing does.
STAND_IN = ("import json, sys, pathlib; a = sys.argv[1:]; out = pathlib.Path(a[0]).parent / 'seen.json'; "
            "seen = json.loads(out.read_text()) if out.exists() else []; seen.append(a); out.write_text(json.dumps(seen)); "
            "'--summary' in a and pathlib.Path(a[a.index('--summary') + 1]).write_text(json.dumps({'spent_nano': 1250000000})); "
            "print('Left for a later run: %s: No recorded answer: this needs Live Otto.'); "
            "print('No test pack was made: this run settled none of its advisories.'); sys.exit(3)" % ID)


def _lab(tmp_path, monkeypatch, day: int = 2, on: bool = True, key: bool = False, records: list[dict] | None = None, **overrides):
    folder = research_demo.sandbox_source(tmp_path / "source", day)
    if records is not None:
        (folder / "PyPI__starkbank-ecdsa.json").write_text(json.dumps({"vulns": records}), encoding="utf-8")
    lab = sandbox_lab(tmp_path, monkeypatch, advisory_source_dir=folder, key=key, **overrides)
    if on:
        turn_on(lab)
    imp = lab.import_file("starkbank-file.csv", research_demo.SANDBOX_FILE.read_bytes())
    return lab, lab.ensure_plan(imp["id"])["id"]


def _stand_in(lab, monkeypatch) -> list[list[str]]:
    base: list[list[str]] = []
    real = lab._research_command

    def command(inbox, live, limit_nano):
        base.append(real(inbox, live, limit_nano))
        return [sys.executable, "-c", STAND_IN, str(inbox)]
    monkeypatch.setattr(lab, "_research_command", command)
    return base


def _row(lab, plan: int) -> dict:
    return lab.lookup_view(plan)["last"]["rows"][0]


# ---------------------------------------------------------------- what can be tried

def test_with_the_switch_on_a_weakness_with_a_fix_in_a_pypi_library_can_be_tried_on_public_copies(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch)
    try:
        lab.look_for_advisories(plan)
        row = _row(lab, plan)
        assert (row["id"], row["state"]["key"], row["sandbox"]) == (ID, "new", True)
        assert row["reason"] == "A test can be tried on public copies from PyPI: starkbank-ecdsa 2.0.1, the fixed version, and the release before it."
        view = lab.lookup_view(plan)
        lines = view["research"]["dialog"]["lines"]
        at = lines.index("What will be fetched, from the public package registry and nowhere else:")
        assert lines[at + 1].startswith("From PyPI: starkbank-ecdsa 2.0.1 (the fixed version) and the release before it; starkbank-ecdsa 2.0.0, which your file names")
        assert any("Nothing of your assessment is sent" in line for line in lines) and any("the separate reviewer decides every run" in line for line in lines)
        assert words.SANDBOX_COVERS in view["covers"] and view["sandbox_line"].startswith("Sandbox research is on. A research run starts on a click")
        # reading the page fetched nothing and started nothing
        with lab.db() as db:
            assert db.scalars(select(OttoResearchRow)).all() == []
        assert not (lab.settings.data_dir / "sandbox").exists() and not (lab.settings.data_dir / "sandbox-research").exists()
    finally:
        lab.stop()


def test_with_the_switch_off_the_same_look_reads_exactly_as_it_always_did(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch, on=False)
    try:
        lab.look_for_advisories(plan)
        row = _row(lab, plan)
        assert row["state"]["key"] == "no_test" and row["reason"] == words.no_copy_of("starkbank-ecdsa")
        assert row["sandbox"] is False and row["watch"] is None
        view = lab.lookup_view(plan)
        assert view["covers"] == words.COVERS and view["sandbox_line"] is None
        assert not any("fetched" in line for line in view["research"]["dialog"]["lines"])
        assert view["research"]["can"] is False
    finally:
        lab.stop()


def test_a_weakness_with_no_fix_yet_can_not_be_tried_and_points_to_the_watch_list(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch, day=1)
    try:
        lab.look_for_advisories(plan)
        row = _row(lab, plan)
        assert row["state"]["key"] == "no_test" and row["reason"] == words.NO_FIXED_VERSION and row["sandbox"] is False
        assert row["watch"]["label"] == "On the Watch list"
        assert (row["watch"]["link"]["page"], row["watch"]["link"]["item"], row["watch"]["link"]["section"]) == \
            ("change-watch", f"{ID}~starkbank-ecdsa", "watch-list")
        assert any(i["key"] == f"{ID}~starkbank-ecdsa" for i in lab.watch_list_view(plan)["items"])
    finally:
        lab.stop()


def _record(**changes) -> dict:
    made = copy.deepcopy(research_demo.sandbox_record(2))
    made.update(changes)
    return made


@pytest.mark.parametrize("record, reason", [
    (_record(id="MAL-2026-1234", aliases=[]), words.HARMFUL_PACKAGE),
    (_record(aliases=["MAL-2026-1234"]), words.HARMFUL_PACKAGE),
], ids=["a record of a harmful package", "known under a harmful-package id too"])
def test_a_package_published_to_do_harm_is_never_fetched(tmp_path, monkeypatch, record, reason):
    lab, plan = _lab(tmp_path, monkeypatch, records=[record])
    try:
        lab.look_for_advisories(plan)
        row = _row(lab, plan)
        assert row["state"]["key"] == "no_test" and row["reason"] == reason and row["sandbox"] is False
        assert lab.lookup_view(plan)["research"]["can"] is False
    finally:
        lab.stop()


def test_a_last_affected_version_is_enough_and_the_row_says_which_side_is_which(tmp_path, monkeypatch):
    record = _record()
    record["affected"][0]["ranges"][0]["events"] = [{"introduced": "0"}, {"last_affected": "2.0.0"}]
    lab, plan = _lab(tmp_path, monkeypatch, records=[record])
    try:
        lab.look_for_advisories(plan)
        row = _row(lab, plan)
        assert row["state"]["key"] == "new"
        assert row["reason"] == ("A test can be tried on public copies from PyPI: starkbank-ecdsa 2.0.0, the last version the source names as "
                                 "affected, and the release after it.")
    finally:
        lab.stop()


# ---------------------------------------------------------------- what the research command is handed

@pytest.mark.needs_otto
@pytest.mark.slow          # (starts a process and waits on it)
def test_a_sandbox_run_is_handed_the_version_facts_and_its_own_limit_and_what_it_spent_is_kept(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch)
    try:
        lab.look_for_advisories(plan)
        base = _stand_in(lab, monkeypatch)
        lab.start_research(plan)
        lab.wait_until_research_done(60)
        with lab.db() as db:
            started, finished = db.scalars(select(OttoResearchRow).order_by(OttoResearchRow.id)).all()
        assert (started.sandbox, finished.sandbox, started.live) == (True, True, False)
        assert finished.spent_nano == 1_250_000_000 and started.limit_nano == 5 * model.NANO
        assert base[0][base[0].index("--limit") + 1] == "5.00" and "--live" not in base[0] and "--sandbox" not in base[0]
        inbox = lab.settings.data_dir / "otto-inbox"
        seen = json.loads(next(inbox.glob("seen.json")).read_text())[0]
        assert seen[1:2] == ["--sandbox"] and "--facts" in seen and "--summary" in seen
        facts = json.loads(open(seen[seen.index("--facts") + 1], encoding="utf-8").read())
        assert facts == {"schema": "isogeny.sandbox-facts/1", "advisories": {ID: {
            "library": "starkbank-ecdsa", "registry": "pypi", "package": "starkbank-ecdsa", "yours": ["2.0.0"],
            "ranges": [{"introduced": "0", "fixed": "2.0.1", "last_affected": None}]}}}
        # the inbox itself holds the one snapshot file and nothing else, as the research command asks
        assert [p.name for p in next(d for d in inbox.iterdir() if d.is_dir() and not d.name.endswith("-sandbox")).iterdir()] == ["advisories.json"]
        # the run settled nothing: the advisory is open again, with what the run said, and nothing is proposed
        row = _row(lab, plan)
        assert row["state"]["key"] == "new" and "No recorded answer: this needs Live Otto." in row["reason"]
        assert lab.otto_proposals(plan, ("check",)) == [] or all(ID not in p["title"] for p in lab.otto_proposals(plan, ("check",)))
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_the_days_limit_stops_a_run_that_asks_claude_and_never_one_on_recorded_answers(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch, key=True)
    try:
        lab.look_for_advisories(plan)
        lab.set_sandbox(day_limit="1.00")
        now = datetime.now(timezone.utc)
        at = (now - timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
        with lab.db() as db:
            for kind, spent in (("started", 0), ("finished", model.NANO)):
                db.add(OttoResearchRow(plan_id=plan, run_key="earlier", kind=kind, at=at, by="You", lookup_id=1, advisories=[ID], live=True,
                                       limit_nano=model.NANO, installed_first=[], exit_code=None if kind == "started" else 3, pack_version=None,
                                       output=[], sandbox=True, spent_nano=spent))
            db.commit()
        assert lab.sandbox_spent_today() == model.NANO and lab.sandbox_run_limit() == 0
        assert lab.lookup_view(plan)["research"]["can"] is True                   # Live Otto is off: recorded answers cost nothing
        lab.set_live_otto(on=True)
        blocked = lab.lookup_view(plan)["research"]
        assert blocked["can"] is False and blocked["blocked_reason"].startswith("Today's spending limit is reached. The next run can start after ")
        assert "Today's spending limit is reached." in lab.lookup_view(plan)["sandbox_line"]
        lab.set_sandbox(day_limit="10.00")
        assert lab.lookup_view(plan)["research"]["can"] is True and lab.sandbox_run_limit() == 5 * model.NANO
        lab.set_sandbox(day_limit="3.00")
        assert lab.sandbox_run_limit() == 2 * model.NANO                          # the smaller of the two: what is left of the day
    finally:
        lab.stop()


# ---------------------------------------------------------------- the second tick: a run the clock starts

@pytest.mark.needs_otto
@pytest.mark.slow
def test_only_with_the_second_tick_does_the_clock_start_a_research_run_and_it_is_kept_under_the_clocks_name(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch, key=True)
    try:
        lab.look_for_advisories(plan)
        base = _stand_in(lab, monkeypatch)
        now = datetime.now(timezone.utc)
        assert lab.watch_clock_tick(now)["started"] is None                        # the switch alone: looking only
        lab.set_live_otto(on=True)
        assert lab.watch_clock_tick(now)["started"] is None                        # Live Otto alone is not the tick
        lab.set_sandbox(by_itself=True)
        assert lab.watch_clock_tick(now)["started"] == plan
        lab.wait_until_research_done(60)
        with lab.db() as db:
            started = db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "started")).one()
        assert started.by == watch_words.CLOCK_NAME and started.live is True and started.sandbox is True and started.advisories == [ID]
        assert "--live" in base[0] and base[0][base[0].index("--limit") + 1] == "5.00"
        assert "A research run starts by itself" in lab.lookup_view(plan)["sandbox_line"]
        # it proposes nothing by starting, accepts nothing, and adds no check
        assert lab.lab_view(plan)["rows"] == []
        # an advisory its runs left open three times waits for a person's click
        for _ in range(2):
            assert lab.watch_clock_tick(now)["started"] == plan
            lab.wait_until_research_done(60)
        assert lab.watch_clock_tick(now)["started"] is None
        with lab.db() as db:
            assert len(db.scalars(select(OttoResearchRow).where(OttoResearchRow.kind == "started")).all()) == 3
        assert lab.lookup_view(plan)["research"]["can"] is True                    # a person can still start it
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_the_clock_starts_no_run_when_the_days_limit_is_reached(tmp_path, monkeypatch):
    lab, plan = _lab(tmp_path, monkeypatch, key=True)
    try:
        lab.look_for_advisories(plan)
        _stand_in(lab, monkeypatch)
        turn_on(lab, by_itself=True)
        lab.set_sandbox(day_limit="1.00")
        at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        with lab.db() as db:
            for kind in ("started", "finished"):
                db.add(OttoResearchRow(plan_id=plan, run_key="earlier", kind=kind, at=at, by="You", lookup_id=1, advisories=["CVE-1999-0001"],
                                       live=True, limit_nano=model.NANO, installed_first=[], exit_code=None if kind == "started" else 3,
                                       pack_version=None, output=[], sandbox=True, spent_nano=0 if kind == "started" else model.NANO))
            db.commit()
        assert lab.watch_clock_tick(datetime.now(timezone.utc))["started"] is None
    finally:
        lab.stop()
