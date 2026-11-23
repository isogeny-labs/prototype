"""Change watch through its three web routes: what the page reads at each stage, in its shape and its words; the two
actions; and every refusal with its sentence."""

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.present import changewatch as words
from app.present import times
from app.web import models
from conftest import PASSWORD, free_port
from test_changes import FIX, proved, small_plan
from view_helpers import problems

BANNED = ("secure", "score", "severity", "safe to", "risk level")
NOT_CONNECTED = "Connect the demo code first. Connect demo code is on Fixes."
TRICKS = "Attacker tricks (our short list)"
MARKS = {times.HEADER: times.ASKS}


def refused(response, status=409) -> str:
    assert response.status_code == status, (response.status_code, response.text[:200])
    assert set(response.json()) == {"error"} and set(response.json()["error"]) == {"message", "line", "field"}
    return response.json()["error"]["message"]


def texts(value) -> list[str]:
    """Every sentence of a view."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in texts(v)]
    return []


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """One assessment driven through the page's routes: the view before the code is connected, connected, with the
    settings change brought in, with the change that undoes the merged fix, while its picked tests run, and after."""
    folder = tmp_path_factory.mktemp("change-watch-page")
    with TestClient(
        create_app(
            Settings(
                data_dir=folder / "data", demo_tls_port=free_port(), force_mode="demo", speed_rounds=25, speed_repeats=4
            )
        )
    ) as client:
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        lab = client.app.state.lab
        plan = small_plan(lab)
        url = f"/api/plans/{plan.id}/change-watch"
        get = lambda **more: client.get(url, **more).json()  # noqa: E731
        before = get()
        early = [
            refused(client.post(f"{url}/demo/allow-tls-1-0")),
            refused(client.post(f"{url}/change-0123456789ab/run")),
        ]
        proved(lab, plan)
        connected = get()
        tls = client.post(f"{url}/demo/allow-tls-1-0")
        with_tls = tls.json()
        twice = refused(client.post(f"{url}/demo/allow-tls-1-0"))
        nothing = refused(client.post(f"{url}/{with_tls['changes'][0]['id']}/run"))
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        with_revert = client.post(f"{url}/demo/revert-range-check").json()
        revert_id = with_revert["changes"][0]["id"]
        running = client.post(f"{url}/{revert_id}/run").json()
        while_running = refused(client.post(f"{url}/{revert_id}/run"))
        lab.wait_until_idle(plan.id, 120)
        done, marked = get(), get(headers=MARKS)
        yield SimpleNamespace(
            client=client,
            lab=lab,
            plan=plan,
            url=url,
            before=before,
            early=early,
            connected=connected,
            tls_status=tls.status_code,
            with_tls=with_tls,
            twice=twice,
            nothing=nothing,
            with_revert=with_revert,
            revert_id=revert_id,
            running=running,
            while_running=while_running,
            done=done,
            marked=marked,
        )


def test_every_answer_has_the_pages_shape_and_no_word_that_rates(page):
    for stage in ("before", "connected", "with_tls", "with_revert", "running", "done", "marked"):
        view = getattr(page, stage)
        assert problems(view, models.ChangeWatchView, stage) == []
        assert view["title"] == "Change watch" and "Nothing runs by itself." in view["subline"]
        for sentence in texts(view):
            assert not any(word in sentence.lower() for word in BANNED), sentence
            assert "otto" not in sentence.lower(), sentence  # fixed rules pick the tests: nothing here is Otto's


def test_until_the_code_is_connected_the_page_says_what_to_do_first(page):
    view = page.before
    assert view["code"] == {
        "state": "not_connected",
        "line": NOT_CONNECTED,
        "link": {"page": "fixes", "item": None, "group": None},
        "connected_line": None,
    }
    assert view["changes"] == [] and view["empty"] is None and view["busy"] is False
    assert view["menu"]["button"] == "Bring in a demo change" and "It runs nothing." in view["menu"]["note"]
    assert [(m["title"], m["can"], m["blocked_reason"]) for m in view["menu"]["items"]] == [
        ("Revert the range check", False, "Connect the demo code first."),
        ("Allow TLS 1.0 for an old partner", False, "Connect the demo code first."),
    ]
    assert page.early == [NOT_CONNECTED, NOT_CONNECTED]


def test_connected_with_no_change_it_says_so_and_offers_the_demo_changes(page):
    view = page.connected
    assert view["code"]["state"] == "connected" and view["code"]["line"] is None
    assert view["code"]["connected_line"] == "Connected: the demo repository acme-sign, branch main."
    assert view["changes"] == [] and view["empty"] == words.EMPTY
    assert [(m["key"], m["can"], m["blocked_reason"]) for m in view["menu"]["items"]] == [
        ("revert-range-check", False, "Offered once a fix is merged: it undoes that fix."),
        ("allow-tls-1-0", True, None),
    ]


def test_the_settings_change_reads_nothing_to_run_with_its_flag_and_its_lines(page):
    assert page.tls_status == 200 and page.twice == "This demo change is already in the repository."
    change = page.with_tls["changes"][0]
    assert (change["title"], change["branch"], change["author"], change["is_demo"]) == (
        "Allow TLS 1.0 for an old partner",
        "dev/allow-tls-1-0-for-partner",
        "Demo developer",
        True,
    )
    assert re.fullmatch(r"change-[0-9a-f]{12}", change["id"]) and re.fullmatch(r"[0-9a-f]{7}", change["commit"])
    assert re.fullmatch(
        r"\d{1,2} [A-Z][a-z]+ 20\d\d, \d\d:\d\d UTC", change["when"]
    )  # a file, a script and a test read UTC words
    assert change["files_line"] == "partner-gateway.conf (added)" and change["picked_line"] == "0 of 4 tests picked"
    assert change["status"] == {
        "key": "nothing_to_run",
        "word": "Nothing to run",
        "tone": "neutral",
        "busy": False,
        "reason": "This change edits no file of a program under test, so no test is picked.",
    }
    panel = change["panel"]
    assert panel["picked"] == [] and panel["picked_empty"] == words.NOTHING_PICKED and len(panel["not_picked"]) == 4
    reasons = {t["title"]: t["reason"] for t in panel["not_picked"]}
    assert reasons[TRICKS] == "Runs acme-sign, and this change does not edit acme_sign.py."
    assert reasons["Old TLS versions"].startswith("Tests the server localhost:") and reasons[
        "Old TLS versions"
    ].endswith("It does not run acme-sign.")
    assert all(
        t["link"] == {"page": "checks", "item": f"test-{t['item_id']}", "group": None} for t in panel["not_picked"]
    )
    assert panel["run"] == {
        "label": "Run the picked tests",
        "can": False,
        "blocked_reason": words.NOTHING_PICKED,
        "will_run": [],
        "note": None,
    }
    assert page.nothing == "No test is picked for this change, so there is nothing to run."
    assert (
        panel["files"][0]["what"] == "Added"
        and panel["files"][0]["counts"] == "5 lines added"
        and panel["files"][0]["is_program"] is False
    )
    assert panel["files"][0]["blocks"][0]["after"][3] == {"n": 4, "mark": "+", "text": "minimum_protocol = TLS 1.0"}
    assert change["flags_count"] == 1 and panel["flags_note"] == "A flag is something to look at. It is never a result."
    assert panel["flags"] == [
        {
            "title": "Old cryptography is named in the change",
            "text": "partner-gateway.conf, line 4: \u201cminimum_protocol = TLS 1.0\u201d names TLS 1.0.",
            "note": "The app has not tested what this line does.",
            "source": {
                "title": "RFC 8996, Deprecating TLS 1.0 and TLS 1.1",
                "url": "https://www.rfc-editor.org/rfc/rfc8996",
            },
        }
    ]
    assert panel["results"] == [] and panel["last_run"] is None


def test_the_change_that_undoes_the_fix_lists_its_picked_tests_and_nothing_has_run(page):
    change = page.with_revert["changes"][0]
    assert (
        change["title"] == "Revert the range check"
        and change["status"]["key"] == "not_run"
        and change["status"]["word"] == "Not run yet"
    )
    assert change["picked_line"] == "2 of 4 tests picked" and change["flags_count"] == 0
    panel = change["panel"]
    assert [(t["title"], t["reason"]) for t in panel["picked"]] == [
        (TRICKS, "Runs acme-sign, and this change edits acme_sign.py."),
        ("Speed and size", "Runs acme-sign, and this change edits acme_sign.py."),
    ]
    assert panel["gives"] == "Its code is, byte for byte, acme-sign 1.4.2, one of our registered demo programs."
    assert re.fullmatch(
        r"Starts from commit [0-9a-f]{7} \(acme-sign 1\.4\.3\), 1 commit on the branch\.", panel["starts_from"]
    )
    run = panel["run"]
    assert (run["label"], run["can"], run["blocked_reason"], run["will_run"]) == (
        "Run the picked tests",
        True,
        None,
        [TRICKS, "Speed and size"],
    )
    assert run["note"].startswith(
        "Runs Attacker tricks (our short list) and Speed and size on acme-sign 1.4.2: the registered demo program"
    )
    assert "never replace a result of this assessment's own tests" in run["note"]
    assert panel["results"] == [] and panel["files"][0]["is_program"] is True and panel["files"][0]["what"] == "Changed"
    assert [m["can"] for m in page.with_revert["menu"]["items"]] == [False, False]


def test_run_the_picked_tests_starts_them_and_the_page_reads_running(page):
    change = page.running["changes"][0]
    assert page.running["busy"] is True and change["status"]["key"] == "running" and change["status"]["busy"] is True
    assert change["status"]["reason"] in ("0 of 2 tests have run.", "1 of 2 tests have run.", "2 of 2 tests have run.")
    assert page.running["busy"] is True
    assert change["panel"]["run"]["can"] is False and "Change watch" in change["panel"]["run"]["blocked_reason"]
    assert [r["title"] for r in change["panel"]["results"]] == [TRICKS, "Speed and size"]
    assert (
        page.while_running
        == "The tests picked for a change are running in Change watch. Wait until they have finished."
    )


def test_after_the_run_the_page_repeats_the_reviewers_words_before_and_now(page):
    change = page.done["changes"][0]
    assert page.done["busy"] is False
    assert change["status"] == {
        "key": "passed_before_fails_now",
        "word": "Passed before, fails now (1 test)",
        "tone": "fail",
        "busy": False,
        "reason": "1 test passed on the code before and fails on this change.",
    }
    panel = change["panel"]
    assert panel["run"]["label"] == "Run again" and panel["run"]["can"] is True and panel["last_run"]
    tricks, speed = panel["results"]
    assert (tricks["before"]["label"], tricks["now"]["label"], tricks["differs"], tricks["outcome"]) == (
        "Passed",
        "Failed",
        "Passed before, fails now",
        "fails_now",
    )
    assert (tricks["before"]["ran_on"], tricks["now"]["ran_on"]) == ("acme-sign 1.4.3", "acme-sign 1.4.2")
    assert tricks["before_note"] == "From the proof of a fix." and re.fullmatch(
        r"proof-\d+-in-\d+", tricks["before"]["link"]["item"]
    )
    assert tricks["now"]["plain"] and tricks["before"]["plain"] and tricks["job"] is None
    assert (speed["now"]["label"], speed["differs"], speed["outcome"]) == (
        "No slowdown beyond measured noise",
        "No slowdown against the code before",
        "not_slower",
    )
    # the words are the reviewer's own for those runs: the page words no result of its own
    with page.lab.db() as db:
        from app.db import TestRunRow

        shown = page.lab._result(db, db.get(TestRunRow, tricks["now"]["run_id"]))
    assert (shown["label"], shown["plain"]) == (tricks["now"]["label"], tricks["now"]["plain"])


def test_a_browser_gets_its_times_marked_and_a_file_never_does(page):
    marked, plain = page.marked["changes"][0], page.done["changes"][0]
    assert re.fullmatch(
        r"\[\[time:20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ\]\]", marked["when"]
    ) and "[[time:" not in json.dumps(page.done)
    assert marked["panel"]["last_run"].startswith("[[time:") and plain["panel"]["last_run"].endswith("UTC")


def test_the_three_routes_need_a_login_and_refuse_what_is_not_theirs(page, tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo"))
    ) as stranger:
        for method, tail in (("GET", ""), ("POST", "/demo/allow-tls-1-0"), ("POST", f"/{page.revert_id}/run")):
            assert stranger.request(method, f"/api/plans/1/change-watch{tail}").status_code == 401
    client, url = page.client, page.url
    for key in ("nope", "Revert", "revert_range_check", "a" * 60, "revert-range-check.json", "-x"):
        assert refused(client.post(f"{url}/demo/{key}"), 404) == "That demo change does not exist."
    assert (
        client.post(f"{url}/demo/..%2Frevert-range-check").status_code == 404
    )  # (a path with a slash in it is no route of the app)
    for change in ("change-zzzzzzzzzzzz", "change-0123", "dev", "change-0123456789abcdef"):
        assert refused(client.post(f"{url}/{change}/run"), 404) == "That change is not in the connected repository."
    assert (
        refused(client.post(f"{url}/change-0123456789ab/run"), 404) == "That change is not in the connected repository."
    )
    assert refused(client.get("/api/plans/99999/change-watch"), 404) == "That test plan does not exist."
    # neither action takes a body: nothing can be handed to them
    assert (
        client.post(f"{url}/demo/allow-tls-1-0", json={"files": {"acme_sign.py": "x"}}).status_code == 409
    )  # (already in; the body is not read)


def test_a_closed_assessment_still_reads_and_changes_nothing(page):
    lab, client = page.lab, page.client
    a = lab.assessment_for(plan_id=page.plan.id)
    lab.update_assessment(a.id, {"close": True, "signed_off_by": "A reviewer", "note": ""})
    assert client.get(page.url).status_code == 200
    for tail in ("/demo/allow-tls-1-0", f"/{page.revert_id}/run"):
        assert "closed" in refused(client.post(f"{page.url}{tail}")).lower()
    with lab.db() as db:
        from app.db import WatchRunRow

        assert db.query(WatchRunRow).count() == 1


# ---------------------------------------------------------------- the status sentence, case by case


@pytest.mark.parametrize(
    "counts,word,reason",
    [
        (
            {"fails_now": 1},
            "Passed before, fails now (1 test)",
            "1 test passed on the code before and fails on this change.",
        ),
        (
            {"fails_now": 2},
            "Passed before, fails now (2 tests)",
            "2 tests passed on the code before and fail on this change.",
        ),
        (
            {"slower_now": 1},
            "Passed before, fails now (1 test)",
            "The speed test reads “Slowdown found” on this change, timed against the code before.",
        ),
        (
            {"fails_now": 1, "slower_now": 1},
            "Passed before, fails now (2 tests)",
            "1 test passed on the code before and fails on this change. The speed test reads “Slowdown found” on this change, timed against the code before.",
        ),
    ],
)
def test_the_status_sentence_counts_a_slowdown_found_on_the_change_with_the_tests_that_fail_now(counts, word, reason):
    change = {
        "status": "passed_before_fails_now",
        "run": {"review": {"counts": counts}, "state": "reviewed", "total": 2, "finished": 2},
    }
    shown = words.status_view(change)
    assert (shown["word"], shown["reason"], shown["tone"], shown["busy"]) == (word, reason, "fail", False)


def test_a_change_to_the_program_with_no_test_that_runs_it_says_so_instead_of_claiming_no_program_file_was_edited():
    program = {"name": "acme-sign", "version": "1.4.2", "file": "acme_sign.py"}
    touched = {"status": "nothing_to_run", "touches_program": True, "run": None}
    assert (
        words.status_view(touched, program)["reason"]
        == "This change edits acme_sign.py, but no test of the plan runs acme-sign, so no test is picked."
    )
    untouched = {"status": "nothing_to_run", "touches_program": False, "run": None}
    assert (
        words.status_view(untouched, program)["reason"]
        == "This change edits no file of a program under test, so no test is picked."
    )
