"""Change watch and the Otto panel (phase 6d): beside the page the panel offers the page's own Run the picked tests
behind Confirm, a typed sentence can ask for it, and Bring in a demo change stays on its page. The panel's read and
its answers start nothing and write nothing."""

import time
from types import SimpleNamespace

import pytest

from app.assistant import commands
from app.fixes.gitrepo import Person
from app.lab.testlab import BUSY
from app.web import models
from conftest import make_lab
from test_changes import FIX, proved, small_plan
from test_changes_read import V142, kept, one, repo_of

REVERT, TLS = "dev/revert-range-check", "dev/allow-tls-1-0-for-partner"


def _steps(view: dict) -> list[dict]:
    return [e for e in view["on_page"]["entries"] if e["what"] == "next:run_picked_tests"]


@pytest.fixture(scope="module")
def beside(tmp_path_factory):
    """The demo fix merged and both demo changes brought in. What the panel reads and answers beside Change watch
    before anything ran, while the picked tests run, and after."""
    lab = make_lab(tmp_path_factory.mktemp("watch-panel"))
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        aid = lab.assessment_for(plan_id=plan.id).id
        for key in ("revert-range-check", "allow-tls-1-0"):
            lab.bring_in_demo_change(plan.id, key)
        change = one(lab.change_watch_state(plan.id), REVERT)
        other = one(lab.change_watch_state(plan.id), TLS)
        was = kept(lab)
        first = lab.assistant_view(aid, "change-watch")
        said = {
            s: lab.assistant_answer(aid, "change-watch", None, s)
            for s in (
                "Run the picked tests",
                "run the picked tests for Revert the range check",
                "rerun the picked tests on dev/revert-range-check",
                "run the picked tests for the allow tls change",
                "Bring in a demo change",
                "add the demo change",
                "open change watch",
            )
        }
        elsewhere = lab.assistant_answer(aid, "checks", None, "run the picked tests")
        untouched = (kept(lab) == was, lab.jobs.live(plan.id) == [])
        page = one_view(lab.change_watch_view(plan.id), change["id"])
        lab.run_picked_tests(plan.id, change["id"])
        running = lab.assistant_view(aid, "change-watch")
        refused = lab.assistant_answer(aid, "change-watch", None, "run the picked tests")
        lab.wait_until_idle(plan.id, 120)
        yield SimpleNamespace(
            lab=lab,
            plan=plan,
            aid=aid,
            change=change,
            other=other,
            first=first,
            said=said,
            elsewhere=elsewhere,
            untouched=untouched,
            page=page,
            running=running,
            refused=refused,
        )
    finally:
        lab.stop()


def one_view(view: dict, change_id: str) -> dict:
    return next(c for c in view["changes"] if c["id"] == change_id)


def test_beside_change_watch_the_panel_offers_the_pages_own_run_button_behind_confirm_for_a_change_that_has_not_run(
    beside,
):
    view = beside.first
    models.AssistantView.model_validate(view)
    (step,) = _steps(view)  # one card: nothing is picked for the other change, so it has no button to press
    assert (step["title"], step["mark"], step["thread"], step["kind"]) == (
        "Run the picked tests",
        "Next step",
        "testing",
        "next",
    )
    assert step["text"] == "The tests picked for “Revert the range check” have not run yet (2 of 4 tests picked)."
    assert step["where"] == {
        "label": "On Change watch",
        "link": {"page": "change-watch", "item": beside.change["id"], "group": None},
    }
    # the request is the page button's own: the same address, with the change's id
    action = {k: v for k, v in step["step"]["action"].items() if v is not None}
    assert action == {"type": "run_picked_tests", "plan_id": beside.plan.id, "change": beside.change["id"]}
    assert (step["step"]["needs"], step["step"]["can"], step["step"]["running"]) == ("confirm", True, False)
    # what Confirm says is what the page says under its button, and whose button it is
    confirm = step["step"]["confirm"]
    assert confirm["title"] == "Run the picked tests?" and confirm["lines"][0] == beside.page["panel"]["run"]["note"]
    assert confirm["lines"][1] == "The runner runs each test and the separate reviewer decides its result."
    assert confirm["names"] == "This is the Run the picked tests button on Change watch." and (
        confirm["confirm"],
        confirm["cancel"],
    ) == ("Confirm", "Cancel")
    assert view["box"]["chips"][0] == "Run the picked tests" and view["thread"] == "testing"


def test_reading_the_panel_and_asking_it_started_nothing_and_wrote_nothing(beside):
    assert beside.untouched == (True, True)


def test_a_typed_sentence_gets_the_card_with_its_confirm_step_and_names_the_change_it_is_for(beside):
    for sentence in (
        "Run the picked tests",
        "run the picked tests for Revert the range check",
        "rerun the picked tests on dev/revert-range-check",
    ):
        reply = beside.said[sentence]
        assert (
            reply["kind"] == "card"
            and reply["text"] == "Run the picked tests, on Change watch. Nothing happens until you press Confirm."
        ), sentence
        assert reply["entry"]["id"] == f"next:run_picked_tests:{beside.change['id']}" and reply["open"] == {
            "key": "step",
            "reason": None,
        }
        assert reply["entry"]["step"]["confirm"] is not None and reply["thread"] == "testing"
    # asked from another page, the card is the same one
    assert (
        beside.elsewhere["kind"] == "card"
        and beside.elsewhere["entry"]["id"] == f"next:run_picked_tests:{beside.change['id']}"
    )
    # a change with nothing to run: the page's own reason, and nothing to confirm
    off = beside.said["run the picked tests for the allow tls change"]
    assert (
        off["kind"] == "cannot"
        and off["text"] == "This change edits no file of a program under test, so no test is picked."
    )
    assert off["entry"]["step"]["can"] is False and off["entry"]["step"]["confirm"] is None


def test_bring_in_a_demo_change_stays_on_its_page(beside):
    for sentence in ("Bring in a demo change", "add the demo change"):
        reply = beside.said[sentence]
        assert reply["kind"] == "page_only" and reply["text"] == "Bringing in a demo change is done on the page."
        assert reply["go"]["page"] == "change-watch" and reply["entry"] is None and reply["open"] is None
    line = commands.BY_KEY["bring_in_demo_change"]
    assert (line["kind"], line["page"]) == ("page", "change-watch")
    assert beside.said["open change watch"]["kind"] == "went"


def test_while_the_picked_tests_run_the_card_says_so_and_cannot_be_pressed(beside):
    (step,) = _steps(beside.running)
    assert step["text"] == "The tests picked for “Revert the range check” are running."
    assert (step["step"]["can"], step["step"]["running"], step["step"]["confirm"]) == (False, True, None)
    assert step["step"]["blocked_reason"] == BUSY["watch"] and step["step"]["progress"] in (
        "0 of 2 tests have run.",
        "1 of 2 tests have run.",
    )
    assert beside.refused["kind"] == "cannot" and beside.refused["text"] == BUSY["watch"]


def test_after_the_run_the_card_is_there_for_the_open_change_and_when_asked_for_and_fixes_has_the_entry_in_the_fixing_thread(
    beside,
):
    lab, aid, change = beside.lab, beside.aid, beside.change
    assert _steps(lab.assistant_view(aid, "change-watch")) == []  # it has run: the result is on the page
    (step,) = _steps(lab.assistant_view(aid, "change-watch", change["id"]))
    assert (step["title"], step["open_item"]) == ("Run again", True)
    assert (
        step["text"]
        == "“Revert the range check” reads Passed before, fails now (1 test). Its picked tests would run again."
    )
    assert step["step"]["can"] is True and step["step"]["confirm"]["title"] == "Run again?"
    asked = lab.assistant_answer(aid, "change-watch", None, "run the picked tests for revert the range check")
    assert asked["kind"] == "card" and asked["entry"]["title"] == "Run again"
    # the change's entry in Fixes arrives in the Fixing thread, as a text-only suggestion with nothing to press
    fixes = lab.assistant_view(aid, "fixes")
    models.AssistantView.model_validate(fixes)
    entry = next(
        e for e in fixes["on_page"]["entries"] if e["title"] == "Revert the range check: 1 test that passed now fails"
    )
    assert (entry["what"], entry["thread"], entry["step"], entry["decisions"]) == (
        "meaning:text_only",
        "fixing",
        None,
        [],
    )
    # asked what is on Fixes, the panel counts as the page does: the change's suggestion is said apart, not with the fixes
    counted = sum(1 for f in lab.fixes_view(beside.plan.id)["fixes"] if not f["apart"])
    told = [f["text"] for f in lab.assistant_answer(aid, "fixes", None, "What is this page for?")["facts"]]
    assert told[1].startswith(
        f"On it now: {counted} {'fix' if counted == 1 else 'fixes'}. Listed apart: 1 suggestion for a developer's change."
    )


def test_two_changes_that_can_run_get_which_one_and_each_option_settles_it(beside):
    lab, plan, aid = beside.lab, beside.plan, beside.aid
    repo = repo_of(lab, plan.id)
    repo.branch_from(
        "dev/undo-again",
        repo.branch("main"),
        {"acme_sign.py": V142},
        "Undo the range check again",
        Person("B", "b@example.invalid"),
        int(time.time()),
    )
    was = kept(lab)
    reply = lab.assistant_answer(aid, "change-watch", None, "run the picked tests")
    assert reply["kind"] == "which" and [o["label"] for o in reply["options"]] == [
        "Undo the range check again",
        "Revert the range check",
    ]
    for option in reply["options"]:
        settled = lab.assistant_answer(aid, "change-watch", None, option["say"])
        assert settled["kind"] == "card" and option["say"].startswith("Run the picked tests for "), option
    # with one of them open on the page, the sentence means that one
    newer = one(lab.change_watch_state(plan.id), "dev/undo-again")
    opened = lab.assistant_answer(aid, "change-watch", newer["id"], "run the picked tests")
    assert opened["kind"] == "card" and opened["entry"]["id"] == f"next:run_picked_tests:{newer['id']}"
    assert kept(lab) == was and lab.jobs.live(plan.id) == []


def test_in_a_closed_assessment_the_card_is_off_with_the_closed_sentence(beside):
    lab, aid, change = beside.lab, beside.aid, beside.change
    lab.update_assessment(aid, {"close": True, "signed_off_by": "A reviewer", "note": ""})
    view = lab.assistant_view(aid, "change-watch", change["id"])
    step = next(e for e in _steps(view) if e["open_item"])
    assert step["step"]["can"] is False and step["step"]["confirm"] is None
    assert "closed" in step["step"]["blocked_reason"].lower()


def test_for_a_change_whose_code_is_not_a_registered_program_the_card_says_the_pages_word_alone_and_cannot_be_pressed(
    tmp_path,
):
    """Nothing of such a change ran and nothing of it can: the card must not say that its picked tests would run again
    (the second review of phase 6d, finding 7). Why the button is off is the page's own sentence."""
    lab = make_lab(tmp_path)
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        repo = repo_of(lab, plan.id)
        repo.branch_from(
            "dev/not-ours",
            repo.branch("main"),
            {"acme_sign.py": V142 + b"\n# edited\n"},
            "Edit the signer",
            Person("Sam Dev", "sam@example.test"),
            int(time.time()),
        )
        aid = lab.assessment_for(plan_id=plan.id).id
        change = one(lab.change_watch_state(plan.id), "dev/not-ours")
        page = one_view(lab.change_watch_view(plan.id), change["id"])
        not_ours = "The changed code is not the same as one of our registered demo programs, so nothing of it runs."
        assert (page["status"]["key"], page["status"]["reason"], page["panel"]["last_run"]) == (
            "cant_run",
            not_ours,
            None,
        )
        assert (page["panel"]["run"]["can"], page["panel"]["run"]["blocked_reason"]) == (False, not_ours)
        was = kept(lab)
        # by itself the panel offers nothing for it: there is no button to press
        assert _steps(lab.assistant_view(aid, "change-watch")) == []
        # with the change open, and when it is asked for: the page's word, and the button off with the page's reason
        opened = next(e for e in _steps(lab.assistant_view(aid, "change-watch", change["id"])) if e["open_item"])
        asked = lab.assistant_answer(aid, "change-watch", None, "run the picked tests for Edit the signer")
        assert (asked["kind"], asked["text"]) == ("cannot", not_ours)
        for card in (opened, asked["entry"]):
            assert card["text"] == "“Edit the signer” reads Can't run."
            assert "run again" not in card["text"] and "would run" not in card["text"]
            assert (card["step"]["can"], card["step"]["blocked_reason"], card["step"]["confirm"]) == (
                False,
                not_ours,
                None,
            )
        assert kept(lab) == was and lab.jobs.live(plan.id) == []
    finally:
        lab.stop()
