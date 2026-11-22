"""Phase 6e, first half, in isolated mode (real containers; skipped with a message where Docker or the elliptic image
is not ready): on a file that names elliptic 6.5.6 the what-if about 6.5.7 offers the try; the panel's card is
Retest new version's own request and nothing else; that retest runs the locked tests on the public copy of 6.5.7 in
its container; and the same question then shows the run's results as this assessment's own.

A test that needs Docker is slow by itself (tests/conftest.py)."""
from types import SimpleNamespace

import pytest

from app.web import models
from conftest import csv_bytes, make_lab
from test_real_flow import ELLIPTIC_ONLY, need

ASK = "What if I update elliptic to 6.5.7?"


def _own(view: dict) -> list[str]:
    return [line["text"] for line in next(g for g in view["facts"] if g["key"] == "own_results")["lines"]]


@pytest.fixture(scope="module")
def real(docker_ready, tmp_path_factory):
    """A file with only elliptic 6.5.6, verified and tested once in its container. What the what-if says then, the
    card the panel hands back, the retest that card asks for, and what the what-if says after it."""
    need(docker_ready, "elliptic")
    lab = make_lab(tmp_path_factory.mktemp("whatif-real"), force_mode=None, speed_rounds=40, speed_repeats=5)
    try:
        assert lab.mode.name == "isolated"
        imp = lab.import_file("elliptic.csv", csv_bytes(ELLIPTIC_ONLY))
        lab.verify(imp["id"])
        pid = lab.ensure_plan(imp["id"])["id"]
        early = lab.whatif_view(pid, "elliptic", "6.5.7")             # before any test has run
        lab.run_all(pid)
        lab.wait_until_idle(pid, 900)
        aid = lab.assessment_for(plan_id=pid).id
        before = lab.whatif_view(pid, "elliptic", "6.5.7")
        runs_before = len(lab.lab_view(pid)["rows"])
        reply = lab.assistant_answer(aid, "evidence", None, ASK)
        nothing_started = lab.jobs.live(pid) == [] and lab.lab_view(pid)["view"] != "before_after"
        # Confirm in the browser sends the card's action as the page button's own request (frontend/src/components/assistant/send.ts)
        action = reply["entry"]["step"]["action"] if reply.get("entry") else None
        if action is not None:
            lab.start_retest(action["plan_id"], action["version"], action["component"])
            lab.wait_until_idle(pid, 900)
        yield SimpleNamespace(lab=lab, pid=pid, aid=aid, early=early, before=before, reply=reply, action=action,
                              nothing_started=nothing_started, runs_before=runs_before, after=lab.whatif_view(pid, "elliptic", "6.5.7"))
    finally:
        lab.stop()


def test_before_any_test_has_run_the_try_is_off_with_evidences_own_reason(real):
    part = real.early["test_copy"]
    assert part["offered"] is False and part["reason"] and (part["button"], part["version"]) == ("Retest new version", "6.5.7")
    assert _own(real.early) == []                # no reviewed result on elliptic yet, and the part says so
    assert next(g for g in real.early["facts"] if g["key"] == "own_results")["none"] == "No test of the plan has a reviewed result on elliptic yet."


def test_with_first_results_on_6_5_6_the_what_if_shows_them_as_the_assessments_own_and_offers_the_try(real):
    models.WhatIf.model_validate(real.before)
    own = _own(real.before)
    assert own and all(" on elliptic 6.5.6: " in line for line in own)
    assert any(line.endswith(": Failed.") for line in own)           # the official vectors fail on 6.5.6 (one published case)
    part = real.before["test_copy"]
    assert (part["offered"], part["reason"], part["component"], part["version"]) == (True, None, "elliptic", "6.5.7")
    assert any("public copy of the new version" in line for line in part["changes"])


def test_the_panel_hands_back_retest_new_versions_own_card_and_asking_started_nothing(real):
    reply = real.reply
    assert (reply["kind"], reply["thread"], reply["text"]) == ("whatif", "fixing", "What if elliptic is updated to 6.5.7?")
    step = reply["entry"]["step"]
    assert (step["needs"], step["can"], step["blocked_reason"]) == ("confirm", True, None)
    assert {k: v for k, v in real.action.items() if v is not None} == {"type": "retest", "plan_id": real.pid, "version": "6.5.7", "component": "elliptic"}
    assert step["confirm"]["title"] and step["confirm"]["lines"]
    assert real.nothing_started is True


def test_the_retest_ran_on_the_public_copy_of_6_5_7_and_the_what_if_then_shows_its_results(real):
    view = real.lab.lab_view(real.pid)
    assert view["view"] == "before_after"
    assert (view["columns"]["before"], view["columns"]["after"]) == ("Before: elliptic 6.5.6", "After: elliptic 6.5.7")
    own = _own(real.after)
    on_new = [line for line in own if " on elliptic 6.5.7: " in line]
    assert on_new and len(own) == len(_own(real.before)) + len(on_new)       # the first results stay; the retest's are added
    # the official vectors and the tricks pass on 6.5.7 (the speed test reads one of its two words)
    assert sum(1 for line in on_new if line.endswith(": Passed.")) >= 2
    assert not any(line.endswith(": Failed.") for line in on_new)
    # every line still leads to its test on Evidence, and nothing here words a result of its own
    lines = next(g for g in real.after["facts"] if g["key"] == "own_results")["lines"]
    assert all(line["label"] == "This assessment's reviewed runs" and line["link"]["page"] == "evidence" for line in lines)
    words = str(real.after).lower()
    assert "secure" not in words and "severity" not in words and "score" not in words
