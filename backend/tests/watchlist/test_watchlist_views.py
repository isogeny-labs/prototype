"""The Watch list in the app (sandbox research): the view of one assessment, Look now, Stop watching and Watch again.
The history is the assessment's own looks; an item and its status are worked out on every read, and reading writes
nothing. With the switch off there is no Watch list, and every action is refused."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from watch_helpers import ITEM, record, rows, watch_lab, with_events, write_source

from app.db import OttoLookupRow, WatchListMarkRow
from app.errors import Conflict, NotFound
from app.web import models

FIXED_HERE = [{"introduced": "0"}, {"fixed": "0.13.3"}]            # a version the app has a pinned public copy of
FIXED_ELSEWHERE = [{"introduced": "0"}, {"fixed": "0.19.2"}]       # (made up for the test) no public copy of it here


def _view(lab, pid) -> dict:
    view = lab.watch_list_view(pid)
    models.WatchListView.model_validate(view)
    return view


def _counts(lab) -> dict:
    with lab.db() as db:
        return {table.__tablename__: db.scalar(select(func.count()).select_from(table)) for table in (OttoLookupRow, WatchListMarkRow)}


def test_with_the_switch_off_there_is_no_watch_list_and_every_action_is_refused(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch, on=False)
    try:
        view = _view(lab, pid)
        assert view["on"] is False and view["items"] == [] and view["look"] is None and "Sandbox research" in view["off_line"]
        assert lab.watch_list_summary(pid) is None
        for refused in (lambda: lab.watch_list_look(pid), lambda: lab.watch_list_mark(pid, ITEM, True)):
            with pytest.raises(Conflict) as said:
                refused()
            assert "Sandbox research" in str(said.value)
        assert _counts(lab) == {"otto_lookups": 0, "watchlist_marks": 0}
    finally:
        lab.stop()


def test_before_any_look_the_list_is_empty_and_says_what_look_now_would_send(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        view = _view(lab, pid)
        assert view["on"] is True and view["items"] == [] and view["looked_line"] == "Not looked at yet."
        assert view["empty_line"].startswith("Nothing is on the Watch list yet.")
        look = view["look"]
        assert (look["button"], look["can"], look["blocked_reason"]) == ("Look now", True, None)
        assert any("Nothing is sent anywhere" in line for line in look["box"]["lines"])      # the source here is a recorded folder
        assert any("Looking is free" in line for line in look["box"]["lines"])
        assert _counts(lab) == {"otto_lookups": 0, "watchlist_marks": 0}                     # reading wrote nothing
    finally:
        lab.stop()


def test_look_now_lists_the_real_weakness_with_no_fix_and_reading_writes_nothing(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        view = lab.watch_list_look(pid)
        models.WatchListView.model_validate(view)
        [row] = view["items"]
        assert (row["key"], row["id"], row["library"]) == (ITEM, "CVE-2024-23342", "python-ecdsa")
        assert row["title"] == "Minerva timing attack on P-256 in python-ecdsa"          # the publisher's own title
        assert row["status"] == {"key": "no_fix", "word": "No fix yet", "tone": "warn"} and row["new"] is True
        assert row["status_line"].startswith("No fix published for ") and row["status_line"].endswith(" days.")
        assert row["yours"] == "Your version is named: python-ecdsa 0.13.2, which your file lists."
        assert row["source"]["key"] == "published"                                       # where it came from: said, not measured
        panel = row["panel"]
        assert panel["ids_line"] == "CVE-2024-23342, also known as GHSA-WJ6H-64FC-37MP."
        assert panel["quote"]["tag"] == "quoted from the named source, not a result"
        assert panel["quote"]["lines"][0] == "Minerva timing attack on P-256 in python-ecdsa"
        assert all(not line.startswith('"introduced"') for line in panel["quote"]["lines"])
        assert panel["versions"]["lines"] == ["Every version. No fixed version is named."]
        assert len(panel["history"]["lines"]) == 1 and panel["history"]["lines"][0].startswith("First seen here on ")
        assert panel["test"] is None and panel["watch"] is None and panel["stop"]["can"] is True
        assert view["count_line"] == "1 published weakness in your libraries has no fix yet."
        assert view["looked_line"].startswith("Looked on ") and view["looked_line"].endswith(" by You.")
        # reading it again, and again, writes nothing and sends nothing
        before = _counts(lab)
        assert _view(lab, pid) == _view(lab, pid)
        assert _counts(lab) == before == {"otto_lookups": 1, "watchlist_marks": 0}
        summary = lab.watch_list_summary(pid)
        assert (summary["no_fix"], summary["fix_published"]) == (1, 0)
        assert summary["link"] == {"page": "change-watch", "item": None, "section": "watch-list"}
    finally:
        lab.stop()


def test_a_second_look_that_finds_nothing_new_says_so_in_the_history(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        [row] = lab.watch_list_look(pid)["items"]
        assert row["new"] is False and row["status"]["key"] == "no_fix"
        assert row["panel"]["history"]["lines"][-1] == "Looked at 1 more time; nothing about it had changed."
    finally:
        lab.stop()


def test_the_day_the_source_names_a_fixed_version_the_item_says_fix_published_and_where_a_test_stands(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        write_source(folder, [with_events(record(), FIXED_HERE)])          # (made up: the next day at the source)
        [row] = lab.watch_list_look(pid)["items"]
        assert row["status"] == {"key": "fix_published", "word": "Fix published", "tone": "neutral"} and row["new"] is True
        assert row["status_line"].startswith("Fixed in 0.13.3, first seen here on ")
        assert row["yours"] == "Your version is named: python-ecdsa 0.13.2, which your file lists. Fixed in 0.13.3."
        history = row["panel"]["history"]["lines"]
        assert len(history) == 2 and history[1].endswith(": the source names a fixed version: 0.13.3.")
        assert row["panel"]["versions"]["lines"] == ["Every version before 0.13.3. Fixed in 0.13.3."]
        # a test can be tried: the app has public copies of 0.13.2 and 0.13.3. It is not tried by looking.
        test = row["panel"]["test"]
        assert test["line"] == "A test can now be designed and proven (Design and prove tests, on Advisories)."
        assert test["link"] == {"page": "advisories", "item": None}
        summary = lab.watch_list_summary(pid)
        assert (summary["no_fix"], summary["fix_published"]) == (0, 1) and "has a fix published since" in summary["line"]
    finally:
        lab.stop()


def test_a_fix_in_a_version_the_app_has_no_public_copy_of_reads_no_test_possible_with_the_reason(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        write_source(folder, [with_events(record(), FIXED_ELSEWHERE)])
        [row] = lab.watch_list_look(pid)["items"]
        assert row["status"] == {"key": "no_test", "word": "No test possible", "tone": "neutral"}
        assert "0.19.2" in row["panel"]["test"]["line"]                    # the reason Advisories gives, word for word
    finally:
        lab.stop()


def test_a_withdrawn_record_and_one_that_is_no_longer_listed_say_so(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        write_source(folder, [{**record(), "withdrawn": "2026-11-22T10:00:00Z"}])
        [row] = lab.watch_list_look(pid)["items"]
        assert row["status"]["key"] == "withdrawn" and row["status"]["word"] == "Withdrawn by its publisher"
        assert row["panel"]["history"]["lines"][-1].endswith(": the publisher withdrew this record.")
        write_source(folder, [])                                            # the answer no longer holds it at all
        [row] = lab.watch_list_look(pid)["items"]
        assert row["status"]["key"] == "withdrawn"                          # withdrawn stays withdrawn: nothing new was learned
        write_source(folder, [record()])
        [row] = lab.watch_list_look(pid)["items"]
        assert row["status"]["key"] == "no_fix" and row["panel"]["history"]["lines"][-1].endswith(": it is in the source's answer again.")
    finally:
        lab.stop()


def test_stop_watching_and_watch_again_are_recorded_with_who_when_and_the_reason(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        with pytest.raises(NotFound):
            lab.watch_list_mark(pid, "CVE-1999-0001~python-ecdsa", True)
        with pytest.raises(Conflict):
            lab.watch_list_mark(pid, ITEM, False)                           # it is being watched already
        view = lab.watch_list_mark(pid, ITEM, True, "  We do not   sign with this library.  ")
        models.WatchListView.model_validate(view)
        assert view["items"] == [] and view["count_line"] is None
        [row] = view["stopped"]
        assert row["status"] == {"key": "not_watched", "word": "Not watched", "tone": "neutral"} and row["status_line"] == "No fix yet."
        assert row["new"] is False and row["panel"]["stop"] is None and row["panel"]["watch"]["can"] is True
        assert row["panel"]["history"]["lines"][-1].endswith(": You stopped watching it (We do not sign with this library.).")
        assert lab.watch_list_summary(pid)["no_fix"] == 0                   # a stopped item is counted nowhere
        with pytest.raises(Conflict):
            lab.watch_list_mark(pid, ITEM, True)
        view = lab.watch_list_mark(pid, ITEM, False)
        [row] = view["items"]
        assert view["stopped"] == [] and row["status"]["key"] == "no_fix"
        assert row["panel"]["history"]["lines"][-1].endswith(": You started watching it again.")
        with lab.db() as db:
            marks = db.scalars(select(WatchListMarkRow).order_by(WatchListMarkRow.id)).all()
            assert [(m.item, m.kind, m.by, m.reason) for m in marks] == [(ITEM, "stop", "You", "We do not sign with this library."),
                                                                         (ITEM, "watch", "You", None)]
    finally:
        lab.stop()


def test_a_closed_assessment_keeps_its_list_and_takes_no_action(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        lab.update_assessment(lab.assessment_for(plan_id=pid).id, {"close": True, "signed_off_by": "Test Closer"})
        view = _view(lab, pid)
        [row] = view["items"]
        assert view["look"]["can"] is False and "closed" in view["look"]["blocked_reason"]
        assert view["next_line"].startswith("This assessment is closed.") and row["panel"]["stop"]["can"] is False
        with pytest.raises(Conflict):
            lab.watch_list_mark(pid, ITEM, True)
    finally:
        lab.stop()


def test_no_sentence_of_the_list_rates_a_weakness_or_calls_anything_secure(tmp_path, monkeypatch):
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        write_source(folder, [with_events(record(), FIXED_HERE)])
        view = lab.watch_list_look(pid)
        [row] = rows(view).values()
        ours = {**view, "items": [], "stopped": []}, {k: v for k, v in row.items() if k != "panel"}, \
            {k: v for k, v in row["panel"].items() if k != "quote"}        # (the quote is the publisher's own text)
        words = str(ours).lower()
        for never in ("secure", "severity", "score", "critical", "otto wrote", "otto found", "otto proposes"):
            assert never not in words, never
    finally:
        lab.stop()


def test_the_routes_need_a_login_and_refuse_with_the_switch_off(client):
    imp = client.post("/api/import/demo").json()
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid = plan["id"]
    read = client.get(f"/api/plans/{pid}/watch-list")
    assert read.status_code == 200 and read.json()["on"] is False
    models.WatchListView.model_validate(read.json())
    for path, body in (("look", None), ("stop", {"item": ITEM}), ("watch", {"item": ITEM})):
        refused = client.post(f"/api/plans/{pid}/watch-list/{path}", json=body)
        assert refused.status_code == 409 and "Sandbox research" in refused.json()["error"]["message"], path
    assert client.post(f"/api/plans/{pid}/watch-list/stop", json={"item": 7}).status_code == 422
    client.cookies.clear()
    assert client.get(f"/api/plans/{pid}/watch-list").status_code == 401
    assert client.post(f"/api/plans/{pid}/watch-list/look").status_code == 401


def test_the_overview_says_how_many_have_no_fix_only_while_the_switch_is_on_and_the_list_holds_something(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch)
    try:
        import_id = lab.assessment_for(plan_id=pid).import_id
        assert "watch_list" not in lab.assessment_blocks(import_id, pid)            # on, and nothing on the list yet
        lab.watch_list_look(pid)
        blocks = lab.assessment_blocks(import_id, pid)
        models.OverviewBlocks.model_validate(blocks)
        assert blocks["watch_list"]["line"] == "1 published weakness in your libraries has no fix yet."
        assert blocks["watch_list"]["link"] == {"page": "change-watch", "item": None, "section": "watch-list"}
        lab.set_sandbox(on=False)
        assert "watch_list" not in lab.assessment_blocks(import_id, pid)            # off: the Overview is as before
    finally:
        lab.stop()
