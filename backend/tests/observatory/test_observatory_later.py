"""The Observatory's map after the things that come later in an assessment (slow set: each walk runs the whole demo).

- A retest on another version: the first result stays, and the retest's is beside it, labelled with the version it
  ran on. A server, which a retest does not change, was tested again as it is.
- A try of a server change on a test copy is not drawn: it is not the live system. The measurement the app makes right
  after Apply (and after Roll back) is of the live system, and is drawn.
- A run of Change watch is never drawn: the map is the same with it as without it.
- An advisory check is listed under "Checks signatures" by its own name, like every signature test of the plan.
- Reading the map of an assessment that has all of this still writes nothing."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from app.observatory import build
from app.web import models
from tests.assistant.assistant_walk import everything_kept
from tests.conftest import make_lab
from tests.observatory import observatory_walk as W
from tests.view_helpers import problems

pytestmark = pytest.mark.slow  # every test here reads a walk of the whole demo (Run all, a retest, an Apply)


@pytest.fixture(scope="module")
def walk(tmp_path_factory):
    lab = make_lab(tmp_path_factory.mktemp("observatory-later"))
    try:
        plan = W.start(lab)
        W.add_list(lab, plan)
        lab.verify(plan.imp["id"])
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        lab.measure_migration(plan.id)
        lab.wait_until_measured(plan.id, 300)
        at = {"measured": W.snapshot(lab, plan, overview=False)}
        lab.start_retest(plan.id, "1.4.3")
        lab.wait_until_idle(plan.id, 300)
        at["retested"] = W.snapshot(lab, plan)
        fix = next(f for f in lab.fixes_view(plan.id)["fixes"] if f["id"].startswith("fix-tls"))
        key = fix["change_box"]["id"]
        lab.try_change(plan.id, key)
        lab.wait_until_changes_idle(plan.id)
        at["tried"] = W.snapshot(lab, plan, panels=False, overview=False)
        lab.ask_approval(plan.id, key, ["you"])
        lab.approve_change(plan.id, key, "you")
        lab.apply_change(plan.id, key)
        lab.wait_until_changes_idle(plan.id)
        at["applied"] = W.snapshot(lab, plan)
        before = everything_kept(lab)
        again = W.snapshot(lab, plan)
        unchanged = everything_kept(lab) == before and again.view == at["applied"].view
        lab.rollback_change(plan.id, key)
        lab.wait_until_changes_idle(plan.id)
        at["rolled"] = W.snapshot(lab, plan, overview=False)
        yield SimpleNamespace(lab=lab, plan=plan, at=at, unchanged=unchanged, known=W.known(lab, plan))
    finally:
        lab.stop()


def _first_results(view: dict) -> dict:
    return {
        c["id"]: (c["word"], c["tone"], c["code"], c["tag"], c["link"]) for c in W.checks(view) if c["kind"] != "status"
    }


def test_after_a_retest_the_first_result_stays_and_the_retest_is_beside_it_with_its_version(walk):
    before, after, plan = walk.at["measured"].view, walk.at["retested"].view, walk.plan
    # every first result is exactly what it was: the box keeps the version the file names
    assert _first_results(after) == _first_results(before)
    assert W.box(after, plan.program)["title"] == "acme-sign 1.4.2"
    assert all(c["beside"] == [] for c in W.checks(before))
    rows = {f"test-{r['item_id']}": r for r in walk.at["retested"].lab["rows"]}
    program = {c["id"]: c for c in W.checks(W.box(after, plan.program)) if c["kind"] == "test"}
    assert len(program) == 3
    for check_id, c in program.items():
        first, retest = rows[check_id]["result"], rows[check_id]["after"]
        (beside,) = c["beside"]
        assert first["component"] == "acme-sign 1.4.2" and retest["component"] == "acme-sign 1.4.3"
        assert beside["label"] == "Retest on acme-sign 1.4.3"  # labelled with the version it ran on
        assert (beside["word"], beside["tone"], beside["code"]) == (retest["label"], retest["tone"], retest["code"])
        assert beside["tag"] == retest["source_tag"] and beside["link"] == {"page": "evidence", "item": check_id}
        assert (c["word"], c["code"]) == (first["label"], first["code"])  # never in its place
    exam = next(c for c in program.values() if c["name"].startswith("Independent exam"))
    assert (exam["word"], exam["beside"][0]["word"]) == ("Failed", "Passed")
    # a retest does not change the server: its two tests were run again on what it is
    for c in W.checks(W.box(after, plan.server)):
        if c["kind"] == "test":
            (beside,) = c["beside"]
            assert beside["label"] == "Retest, tested again as it is" and beside["word"] == c["word"]
            assert beside["tag"]["key"] == "live"
    # the claims and the status were not run again by a retest
    assert all(c["beside"] == [] for c in W.checks(after) if c["kind"] != "test")
    # both boxes still rest on one thing each
    assert W.box(after, plan.server)["tag"]["key"] == "live" and W.box(after, plan.program)["tag"]["key"] == "lab"


def test_the_panel_after_a_retest_counts_the_retests_words_apart_from_the_first_results(walk):
    at, plan = walk.at["retested"], walk.plan
    panel = at.panels[plan.program]
    assert panel["summary"] == (
        "1 claim: 1 True. 3 tests: 2 Failed, 1 Measured. Retest on acme-sign 1.4.3: 2 Passed, "
        "1 No slowdown beyond measured noise. Post-quantum status: Classical."
    )
    assert at.panels[plan.server]["summary"] == (
        "2 claims: 1 False, 1 True. 2 server tests: 1 Failed, 1 Passed. Retest, tested again as it is: 1 Failed, 1 Passed. "
        "Post-quantum status: Classical."
    )
    exam = next(c for s in panel["spots"] for c in s["checks"] if c["name"].startswith("Independent exam"))
    row = next(r for r in at.lab["rows"] if r["kind"] == "official_vectors")
    assert exam["plain"] == row["result"]["plain"] and exam["beside"][0]["plain"] == row["after"]["plain"]
    assert exam["beside"][0]["at"] == row["after"]["finished_at"] and panel["last"]["at"] >= exam["beside"][0]["at"]


def test_a_try_on_a_test_copy_is_not_drawn_on_the_live_servers_box(walk):
    retested, tried = walk.at["retested"], walk.at["tried"]
    # the try ran and Checks lists it; the map is exactly what it was, but for the counts and the time it changed
    tries = [r for g in tried.checks["groups"] for r in g["rows"] if r["id"].startswith("try-")]
    assert tries and all(r["result"] for r in tries)
    for part in ("services", "algorithms", "libraries", "lines", "gaps", "outside"):
        assert tried.view[part] == retested.view[part], part
    assert not [c for c in W.checks(tried.view) if "try" in c["id"] or "copy" in c["name"].lower()]
    # (the counts are the Overview's, which counts every check of the assessment: the try's rows are among them)
    assert W.counts(tried.view)["lab"] == W.counts(retested.view)["lab"] + len(tries)
    assert W.counts(tried.view) == W.summed(tried.checks["groups"])


def test_the_measurement_right_after_apply_is_of_the_live_system_and_is_drawn(walk):
    at, plan = walk.at["applied"], walk.plan
    tls = W.check(at.view, plan.server, "test-1")
    row = next(r for r in at.lab["rows"] if r["kind"] == "tls_versions")
    # the change was applied to the live demo server and measured again at once: that result is beside the first one
    (beside,) = tls["beside"]
    assert beside["label"] == "After Apply" and beside["word"] == row["after"]["label"] == "Passed"
    assert beside["tag"]["key"] == "live" and "right after the change was applied" in beside["tag"]["note"]
    assert (tls["word"], tls["came_from"]) == ("Failed", None)  # the first result stays
    # what was seen on the newest connections: TLS 1.2 is no longer accepted
    assert ("this_computer", plan.server, "live", "TLS · 1.3 accepted") in W.lines(at.view)
    assert ("this_computer", plan.server, "live", "TLS · 1.3 and 1.2 accepted") in W.lines(walk.at["tried"].view)
    assert "After Apply: 2 Passed." in at.panels[plan.server]["summary"]
    # ... and after Roll back the newest measurement is that one
    rolled = W.check(walk.at["rolled"].view, plan.server, "test-1")
    assert [(b["label"], b["word"]) for b in rolled["beside"]] == [("After Roll back", "Failed")]
    assert ("this_computer", plan.server, "live", "TLS · 1.3 and 1.2 accepted") in W.lines(walk.at["rolled"].view)
    # the program's box was not touched by any of it
    assert W.box(at.view, plan.program) == W.box(walk.at["retested"].view, plan.program)


@pytest.mark.parametrize("stage", ["measured", "retested", "tried", "applied", "rolled"])
def test_at_every_later_stage_the_words_are_the_pages_own_the_links_open_and_nothing_is_rated(walk, stage):
    at = walk.at[stage]
    rows = {f"test-{r['item_id']}": r for r in at.lab["rows"]}
    for c in W.checks(at.view):
        if c["kind"] == "test":
            assert c["word"] == rows[c["id"]]["result"]["label"]
            assert [b["word"] for b in c["beside"]] == [r["label"] for r in [rows[c["id"]]["after"]] if r]
    assert W.counts(at.view) == W.summed(at.checks["groups"])
    if at.overview is not None:
        assert W.summed(at.overview["groups"]) == W.counts(at.view)
    for link in W.every_link([at.view, at.panels]):
        assert W.opens(walk.known, link), link
    for text in W.texts([at.view, at.panels]):
        assert not W.NEVER.search(text), text


def test_reading_the_map_of_the_whole_demo_writes_nothing(walk):
    assert walk.unchanged  # (asked in the walk, between Apply and Roll back: every table and every file as it was)
    before = everything_kept(walk.lab)
    view = build.view_of_plan(walk.lab, walk.plan.id)
    for box in W.boxes(view):
        build.panel_of_plan(walk.lab, walk.plan.id, box["key"])
    build.place_of_plan(walk.lab, walk.plan.id, "test:1")
    assert everything_kept(walk.lab) == before and not walk.lab.jobs.live(walk.plan.id)


def test_without_a_retest_the_measurement_after_apply_is_the_live_servers_result_and_says_so(tmp_path):
    """With no retest in the assessment, the app measures the server again after Apply as a run of the test itself:
    Evidence shows that run as the test's result, and so does the map, saying where it came from."""
    lab = make_lab(tmp_path)
    try:
        plan = W.start(lab, small=True)
        lab.verify(plan.imp["id"])
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 240)
        before = build.view_of_plan(lab, plan.id)
        assert (
            W.check(before, plan.server, "test-1")["word"],
            W.check(before, plan.server, "test-1")["came_from"],
        ) == (
            "Failed",
            None,
        )
        fix = next(f for f in lab.fixes_view(plan.id)["fixes"] if f["id"].startswith("fix-tls"))
        key = fix["change_box"]["id"]
        lab.try_change(plan.id, key)
        lab.wait_until_changes_idle(plan.id)
        tried = build.view_of_plan(lab, plan.id)
        assert tried["services"] == before["services"] and tried["lines"] == before["lines"]  # a try is not drawn
        lab.ask_approval(plan.id, key, ["you"])
        lab.approve_change(plan.id, key, "you")
        lab.apply_change(plan.id, key)
        lab.wait_until_changes_idle(plan.id)
        view = build.view_of_plan(lab, plan.id)
        assert problems(view, models.ObservatoryView, "observatory") == []
        row = next(r for r in lab.lab_view(plan.id)["rows"] if r["kind"] == "tls_versions")
        tls = W.check(view, plan.server, "test-1")
        assert row["after"] is None and tls["beside"] == []
        assert tls["word"] == row["result"]["label"] == "Passed" and tls["came_from"] == "After Apply"
        assert tls["tag"]["key"] == "live" and "right after the change was applied" in tls["tag"]["note"]
        # Verify was not run again: its claim keeps Verify's own word, from before the change
        assert W.check(view, plan.server, "claim-1")["word"] == "False"
        # what was seen is read from the newest recorded handshakes, which are the ones made after Apply
        assert ("this_computer", plan.server, "live", "TLS · 1.3 accepted") in W.lines(view)
        assert W.box(view, plan.server)["tag"]["key"] == "live"
        assert W.box(view, plan.program) == W.box(before, plan.program)
    finally:
        lab.stop()


# ---------------------------------------------------------------- Change watch


def test_a_change_watch_run_is_never_drawn(tmp_path):
    """The demo fix merged, a developer's change that undoes it brought in, and its picked tests run: the runs are kept
    apart from the assessment's own results, so the map is the same with them as without."""
    from test_changes import FIX, proved, small_plan

    lab = make_lab(tmp_path)
    try:
        plan = small_plan(lab)
        plan.server = "server:" + plan.imp["addresses"][0]["address"]
        proved(lab, plan)
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        change = next(c for c in lab.bring_in_demo_change(plan.id, "revert-range-check")["changes"])
        before = copy.deepcopy(build.view_of_plan(lab, plan.id))
        panels_before = {b["key"]: build.panel_of_plan(lab, plan.id, b["key"]) for b in W.boxes(before)}
        lab.run_picked_tests(plan.id, change["id"])
        lab.wait_until_idle(plan.id, 120)
        # the watch run is there, and Checks lists its rows under "Came from: Change watch" ...
        checks = lab.checks_view(plan.id)
        watch = [r for g in checks["groups"] for r in g["rows"] if r["came_from"]["key"] == "watch"]
        assert watch and all(r["result"] for r in watch)
        after = build.view_of_plan(lab, plan.id)
        assert problems(after, models.ObservatoryView, "observatory") == []
        # ... and nothing on the map moved: no box, spot, check, word, tag, line or gap
        for part in (
            "services",
            "algorithms",
            "libraries",
            "lines",
            "gaps",
            "outside",
            "state",
            "banner",
            "built_from",
        ):
            assert after[part] == before[part], part
        assert {b["key"]: build.panel_of_plan(lab, plan.id, b["key"]) for b in W.boxes(after)} == panels_before
        assert not [c for c in W.checks(after) if "watch" in c["id"]]
        # (the four counts are the Overview's, which counts every row of Checks, a watch run's too: said in the report)
        assert W.counts(after) == W.summed(checks["groups"])
        assert W.counts(after)["lab"] == W.counts(before)["lab"] + len(watch)
    finally:
        lab.stop()


# ---------------------------------------------------------------- an advisory check


@pytest.mark.needs_otto
def test_an_advisory_check_is_listed_under_checks_signatures_by_its_own_name(tmp_path, monkeypatch):
    from conftest import play_back_speed
    from tests.assistant import assistant_walk as made

    lab = made.start_lab(tmp_path, monkeypatch, record_prompts=False)
    try:
        play_back_speed(lab)
        pid = lab.plan.id
        proposal = made.proposals(lab, "check")[0]
        lab.otto_decide(pid, proposal["id"], "accept")
        before = build.view_of_plan(lab, pid)
        lab.run_all(pid)
        lab.wait_until_idle(pid, 300)
        view = build.view_of_plan(lab, pid)
        assert problems(view, models.ObservatoryView, "observatory") == []
        row = next(r for r in lab.lab_view(pid)["rows"] if r["kind"] == "advisory_cases")
        spot = W.spot(view, "software:lib-acme-sign", "checks_signatures")
        check = next(c for c in spot["checks"] if c["id"] == f"test-{row['item_id']}")
        # by its own name (it names its advisory), with Evidence's own word, in the lab like the other signature tests
        assert check["name"] == row["title"] and "CVE-" in check["name"]
        assert (check["word"], check["code"]) == (row["result"]["label"], row["result"]["code"])
        assert check["tag"]["key"] == "lab" and W.box(view, "software:lib-acme-sign")["tag"]["key"] == "lab"
        assert [c["name"] for c in spot["checks"]][:2] == [
            "Independent exam (Wycheproof)",
            "Attacker tricks (our short list)",
        ]
        # accepted and not run yet, it was listed by the same name, not checked
        waiting = next(c for c in W.checks(before) if c["id"] == check["id"])
        assert (waiting["name"], waiting["word"], waiting["checked"]) == (check["name"], "Not checked yet", False)
        place = build.place_of_plan(lab, pid, f"test:{row['item_id']}")["place"]
        assert place["path"][-2:] == ["acme-sign 1.4.2", "Checks signatures"]
    finally:
        lab.stop()
