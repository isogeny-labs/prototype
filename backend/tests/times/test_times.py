"""The 5c fixes: a time on screen is written in the viewer's own time zone; a file keeps UTC.

The server can't know the viewer's zone. A browser asks for marked times with one request header; the server then
writes a mark with the exact instant where the UTC words would stand, and the browser writes the time there
(frontend/src/time.ts). Without the header every sentence is, byte for byte, what it was. Nothing that is stored,
signed or downloaded may ever hold a mark: the last test walks the demo as a browser would, with the header on every
request, and then reads the evidence file, the report, the database and the ledgers for one."""

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "otto"))

import otto_helpers as helpers  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.present import changes as present_changes  # noqa: E402
from app.present import migration as present_migration  # noqa: E402
from app.present import otto as present_otto  # noqa: E402
from app.present import times  # noqa: E402
from conftest import PASSWORD, free_port  # noqa: E402

MARK = re.compile(r"\[\[time:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\]\]")
UTC_WORDS = re.compile(r"\d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2} UTC")
ASK = {times.HEADER: times.ASKS}


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


# ---------------------------------------------------------------- the mark itself


def test_a_mark_holds_the_exact_moment_in_utc_to_the_second():
    assert times.mark("2026-11-18T19:46:03Z") == "[[time:2026-11-18T19:46:03Z]]"
    assert times.mark("2026-11-18T14:46:03-05:00") == "[[time:2026-11-18T19:46:03Z]]"  # another zone: the same moment
    assert times.mark("2026-11-18T19:46:03") == "[[time:2026-11-18T19:46:03Z]]"  # no zone: UTC, as stored
    assert times.mark("2026-11-18T19:46:03.987654+00:00") == "[[time:2026-11-18T19:46:03Z]]"
    assert times.mark(None) is None and times.mark("not a time") is None and times.mark("") is None
    assert MARK.fullmatch(times.mark("2026-03-08T07:00:00Z"))


def test_without_the_header_every_writer_keeps_its_utc_words():
    assert not times.marked()
    assert present_otto.stamp("2026-11-18T19:46:03Z") == "18 November 2026, 19:46 UTC"
    assert present_changes.when("2026-11-14T17:14:59+00:00") == "14 Nov 2026, 17:14 UTC"
    assert present_changes.when(None) == "" and present_otto.stamp("nonsense") == "nonsense"
    line = present_migration.choice_line("server", {"option": "hybrid", "at": "2026-11-18T19:46:03Z", "reason": None})
    assert "saved 18 Nov 2026 (UTC)." in line and "[[" not in line


def test_for_a_browser_that_asked_each_writer_marks_the_moment_and_a_file_never_does():
    with times.for_screen():
        assert times.marked()
        assert present_otto.stamp("2026-11-18T19:46:03Z") == "[[time:2026-11-18T19:46:03Z]]"
        assert present_changes.when("2026-11-14T17:14:59+00:00") == "[[time:2026-11-14T17:14:59Z]]"
        assert present_changes.when(None) == "" and present_otto.stamp("nonsense") == "nonsense"  # nothing is made up
        line = present_migration.choice_line(
            "server", {"option": "hybrid", "at": "2026-11-18T19:46:03Z", "reason": None}
        )
        assert "saved [[time:2026-11-18T19:46:03Z]]." in line and "UTC" not in line
        # a date with no time of day is not a moment: it is written as it is, for every reader
        assert present_otto.day("2026-11-17T08:00:00Z") == "17 November 2026"
        assert present_migration.day("2027-11-14") == "14 Nov 2027"
        with times.for_files():
            assert not times.marked()
            assert present_otto.stamp("2026-11-18T19:46:03Z") == "18 November 2026, 19:46 UTC"
        assert times.marked()
    assert not times.marked()


def test_the_proof_row_about_a_retest_is_marked_for_a_browser_and_in_utc_for_a_file():
    fix = {"library": "elliptic", "version": "6.5.7"}
    here = {"state": "passed", "item_id": 7, "finished_at": "2026-11-18T19:46:03Z"}
    for_file = present_otto.your_system_row(fix, here)
    assert for_file["text"].startswith("On 18 November 2026, 19:46 UTC the retest on elliptic 6.5.7 passed")
    with times.for_screen():
        for_screen = present_otto.your_system_row(fix, here)
    assert for_screen["text"].startswith("On [[time:2026-11-18T19:46:03Z]] the retest on elliptic 6.5.7 passed")
    assert (
        for_screen["text"].replace("[[time:2026-11-18T19:46:03Z]]", "18 November 2026, 19:46 UTC") == for_file["text"]
    )


# ---------------------------------------------------------------- through the web, as a browser and as a script


def _client(tmp_path, monkeypatch) -> TestClient:
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    updates = tmp_path / "updates"
    updates.mkdir()
    (updates / "2026.11.1.json").write_bytes(first)
    helpers.trust(monkeypatch, tmp_path, [public])
    settings = Settings(
        data_dir=tmp_path / "data",
        demo_tls_port=free_port(),
        force_mode="demo",
        speed_rounds=25,
        speed_repeats=4,
        otto_updates_dir=updates,
        otto_recorded_dir=tmp_path / "recorded",
    )
    return TestClient(create_app(settings))


def test_the_header_is_only_honoured_under_api_and_only_with_its_one_value(tmp_path, monkeypatch):
    seen = []

    async def app(scope, receive, send):
        seen.append(times.marked())

    import asyncio

    def call(path, headers):
        asyncio.run(times.MarkTimes(app)({"type": "http", "path": path, "headers": headers}, None, None))
        return seen[-1]

    name = times.HEADER.encode()
    assert call("/api/plans/1/otto/proposals", [(name, b"mark")]) is True
    assert call("/api/plans/1/otto/proposals", []) is False
    assert call("/api/plans/1/otto/proposals", [(name, b"yes")]) is False
    assert call("/index.html", [(name, b"mark")]) is False
    assert not times.marked()


@pytest.mark.needs_otto
def test_a_browser_gets_marks_a_script_gets_utc_and_no_file_or_record_ever_holds_a_mark(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        browser = dict(ASK)
        assert client.post("/api/setup", json={"password": PASSWORD}, headers=browser).status_code == 200
        client.post("/api/otto/packs/check", headers=browser)
        assert client.post("/api/otto/packs/install", json={"version": "2026.11.1"}, headers=browser).status_code == 200
        imp = client.post("/api/import/demo", headers=browser).json()
        address = imp["addresses"][0]["address"]
        assert (
            client.post(
                f"/api/import/{imp['id']}/confirm-address",
                json={"address": address, "confirmed": True},
                headers=browser,
            ).status_code
            == 200
        )
        plan = client.post(f"/api/import/{imp['id']}/plan", headers=browser).json()
        base = f"/api/plans/{plan['id']}/otto/proposals"
        proposal = client.get(base, headers=browser).json()["proposals"][0]
        # three decisions, each made as the browser makes it: with the header on the request
        for decision in ("accept", "undo", "accept"):
            answer = client.post(f"{base}/{proposal['id']}/{decision}", json={}, headers=browser)
            assert answer.status_code == 200, answer.text
            assert MARK.search(answer.json()["decided_line"])  # the answer to the click is marked too

        # --- the same read, by a browser and by a script
        marked = client.get(base, headers=browser).json()["proposals"][0]
        plain = client.get(base).json()["proposals"][0]
        assert MARK.search(marked["decided_line"]) and not UTC_WORDS.search(marked["decided_line"])
        assert UTC_WORDS.search(plain["decided_line"]) and "[[" not in plain["decided_line"]
        assert [bool(MARK.fullmatch(r["at_text"])) for r in marked["history"]["rows"]] == [True, True, True]
        assert all(UTC_WORDS.fullmatch(r["at_text"]) for r in plain["history"]["rows"])
        # the mark holds exactly the recorded moment, and nothing else of the answer differs
        for shown, written in zip(marked["history"]["rows"], plain["history"]["rows"], strict=True):
            assert shown["at"] == written["at"] and shown["at_text"] == f"[[time:{shown['at']}]]"
            assert shown["line"].replace(shown["at_text"], written["at_text"]) == written["line"]
        assert not any("[[time:" in text for text in _texts(client.get(base).json()))
        # a browser's answer has no time left in UTC words anywhere in that view
        assert not any(UTC_WORDS.search(text) for text in _texts(client.get(base, headers=browser).json()))
        assert not any(
            UTC_WORDS.search(text)
            for text in _texts(client.get(f"/api/plans/{plan['id']}/advisories", headers=browser).json())
        )

        # --- phase 6c: an answer of the Otto panel that holds a time, asked as the browser asks it (and so kept with the
        #     assessment). The answer to the browser is marked; what is kept is in UTC words, like every record; and the
        #     kept answer, read again by a browser, has its time marked again.
        asked = client.post(
            f"/api/plans/{plan['id']}/assistant/messages",
            headers=browser,
            json={"text": "where did this suggestion come from?", "page": "advisories", "item": None},
        )
        assert asked.status_code == 200, asked.text
        told = [f["text"] for f in asked.json()["facts"]]
        assert (
            asked.json()["kind"] == "answer"
            and any(MARK.search(t) for t in told)
            and not any(UTC_WORDS.search(t) for t in told)
        )
        kept = client.app.state.lab.assistant_messages(plan["id"])[-1]  # (read with no browser asking: as stored)
        assert any(UTC_WORDS.search(f["text"]) for f in kept["facts"]) and "[[time:" not in json.dumps(kept)
        assert len(kept["facts"]) == len(told) and all(set(f) == {"text", "link", "label"} for f in kept["facts"])
        # beside each stored fact: the moments the app itself wrote in it (and nothing else of the browser's wording)
        from sqlalchemy import select as select_

        from app.db import AssistantMessageRow

        with client.app.state.lab.db() as db:
            stored = db.scalars(select_(AssistantMessageRow).order_by(AssistantMessageRow.id.desc())).first().facts
        assert "[[time:" not in json.dumps(stored) and any(f["times"] for f in stored)
        for fact_, shown in zip(stored, asked.json()["facts"], strict=True):
            assert fact_["times"] == times.moments(shown["text"])
            with times.for_screen():
                assert (
                    times.remarked(fact_["text"], fact_["times"]) == shown["text"]
                )  # the same sentence the browser got, mark for mark
            assert times.remarked(fact_["text"], fact_["times"]) == fact_["text"]  # and for a file: as stored
        for headers, wanted, unwanted in ((browser, MARK, UTC_WORDS), ({}, UTC_WORDS, MARK)):
            panel = client.get(
                f"/api/assessments/{imp['assessment_id']}/assistant", params={"page": "advisories"}, headers=headers
            ).json()
            line = next(e for t in panel["tabs"] for e in t["so_far"] if e["kind"] == "said")
            assert any(wanted.search(f["text"]) for f in line["facts"]) and not any(
                unwanted.search(f["text"]) for f in line["facts"]
            )

        # --- the files: built on a browser's click (the header is on that request too), and still in UTC
        lab = client.app.state.lab
        lab.verify(imp["id"])
        export = client.post(f"/api/plans/{plan['id']}/evidence", headers=browser)
        assert export.status_code == 200, export.text
        signed = client.get(f"/api/evidence/{export.json()['id']}/json", headers=browser).content
        report = client.get(f"/api/evidence/{export.json()['id']}/html", headers=browser).content
        assert b"[[time:" not in signed and b"[[time:" not in report
        assert signed.count(b"2026-") > 3 and b"(UTC)" in report  # the report still says UTC
        # the same file, asked for by a script: apart from when each was made, the two are the same
        again = client.post(f"/api/plans/{plan['id']}/evidence").json()
        other = client.get(f"/api/evidence/{again['id']}/json").content
        a, b = json.loads(signed)["evidence"], json.loads(other)["evidence"]
        a.pop("generated_at"), b.pop("generated_at")
        assert a == b
        decisions = [d for p in a["otto"]["proposals"] for d in p["decisions"]]
        assert len(decisions) == 3 and all(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", d["at"]) for d in decisions
        )

    # --- what is stored: the database, both kinds of ledger file, everything in the data folder
    holding = [str(p) for p in (tmp_path / "data").rglob("*") if p.is_file() and b"[[time:" in p.read_bytes()]
    assert holding == []
