"""Change watch, the watch run: the picked tests run on a person's ask, on the registered program the change's code is;
"before" is a reviewed run on exactly the code the change starts from; the reviewer says what differs; and these runs
never stand in for a result of the assessment's own tests."""

import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import APPEND_ONLY_TABLES, ReviewRow, RunCodeRow, TestRunRow, WatchReviewRow, WatchRunRow
from app.engine.reviewer import WATCH_STATUSES, RuleReviewer
from app.errors import NotFound
from app.fixes.gitrepo import Person
from app.lab.testlab import BUSY
from app.run import components
from app.web import models
from conftest import make_lab
from test_changes import FIX, proved, small_plan
from test_changes_read import SOMEONE, V142, V143, one, refusal, repo_of

REVERT = "dev/revert-range-check"
WATCH_TABLES = {"watch_runs": "version", "watch_reviews": "status"}  # listed in tests/test_changes.py's cover test


def views(lab, plan) -> SimpleNamespace:
    """What the pages of the assessment's own results read, piece by piece: Evidence's results and the test plan as one
    text; Fixes entry by entry; Checks row by row; the Overview's findings, facts and counts; what Fixes, the Overview
    and the Projects row count as fixes, and the next step."""
    a = lab.assessment_for(plan_id=plan.id)
    text_of = lambda value: json.dumps(value, sort_keys=True, default=str)  # noqa: E731
    checks = lab.checks_view(plan.id)
    whole = lab.assessment_view(a.id)
    blocks = whole["blocks"]
    fixes_page = lab.fixes_view(plan.id)
    encryption = next(g for g in checks["groups"] if g["key"] == "encryption")
    return SimpleNamespace(
        counted_fixes=text_of(
            {
                "list_title": fixes_page["list_title"],
                "groups": {
                    g["key"]: {"counts": g["counts"], "fix_ids": g["fix_ids"], "empty_text": g["empty_text"]}
                    for g in fixes_page["groups"]
                },
                "assessment": whole["counts"]["fixes"],
                "next_step": whole["next_step"],
            }
        ),
        own=text_of({"lab": lab.lab_view(plan.id), "plan": lab.plan_view(plan.id)}),
        fixes={f["id"]: text_of(f) for f in lab.fix_states(plan.id)},
        rows={r["id"]: text_of(r) for g in checks["groups"] for r in g["rows"]},
        parts={key: text_of(part) for key, part in (encryption.get("parts") or {}).items()},
        counts={g["key"]: g["counts"] for g in checks["groups"]},
        findings=text_of(blocks["findings"]),
        overview={
            g["key"]: {"checks": g["checks"], "fixes": g["fixes"], "facts": text_of(g["facts"])}
            for g in blocks["groups"]
        },
        recorded=blocks["evidence"]["runs"],
    )


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    """The demo fix merged, the change that undoes it brought in, and its picked tests run once."""
    lab = make_lab(tmp_path_factory.mktemp("watch-run"))
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        listed = one(lab.bring_in_demo_change(plan.id, "revert-range-check"), REVERT)
        before = views(lab, plan)
        with lab.db() as db:
            runs_before = db.scalar(select(TestRunRow.id).order_by(TestRunRow.id.desc()).limit(1))
        started = one(lab.run_picked_tests(plan.id, listed["id"]), REVERT)
        during = SimpleNamespace(
            running=lab._running(plan.id),
            refusals=[
                refusal(lambda: lab.run_all(plan.id)),
                refusal(lambda: lab.start_retest(plan.id, "1.4.3")),
                refusal(lambda: lab.run_picked_tests(plan.id, listed["id"])),
            ],
        )
        lab.wait_until_idle(plan.id, 120)
        done = one(lab.change_watch_state(plan.id), REVERT)
        yield SimpleNamespace(
            lab=lab,
            plan=plan,
            listed=listed,
            before=before,
            runs_before=runs_before,
            started=started,
            during=during,
            done=done,
            after=views(lab, plan),
        )
    finally:
        lab.stop()


# ---------------------------------------------------------------- the run


def test_nothing_runs_until_it_is_asked_for_and_then_it_reads_running(ran):
    assert ran.listed["status"] == "not_run" and ran.listed["run"] is None
    assert ran.listed["gives"] == {"name": "acme-sign", "version": "1.4.2"} and ran.listed["starts_from"] == {
        "name": "acme-sign",
        "version": "1.4.3",
    }
    assert (
        ran.started["status"] == "running"
        and ran.started["run"]["state"] == "running"
        and ran.started["run"]["total"] == 2
    )
    assert ran.during.running == "watch"
    assert ran.during.refusals == [BUSY["watch"]] * 3 and "Change watch" in BUSY["watch"]


def test_the_picked_tests_ran_on_the_changes_code_and_each_run_records_that_code(ran):
    run = ran.done["run"]
    with ran.lab.db() as db:
        watch = db.get(WatchRunRow, run["id"])
        assert (watch.branch, watch.head_commit, watch.base_commit) == (REVERT, ran.listed["head"], ran.listed["base"])
        assert (watch.version, watch.base_version) == ("1.4.2", "1.4.3")
        assert [f["name"] for f in watch.files] == ["acme_sign.py"] and watch.files[0]["new_sha256"] != watch.files[0][
            "old_sha256"
        ]
        assert [e["kind"] for e in watch.items] == ["bad_signatures", "speed_size"]
        assert sorted(t["rule"] for t in watch.not_picked) == ["server_test", "server_test"]
        new = db.scalars(select(TestRunRow).where(TestRunRow.id > ran.runs_before).order_by(TestRunRow.id)).all()
        # one run for each picked test, on the registered program the change's code is byte for byte; nothing else ran
        assert (
            sorted((r.phase, r.retest_id, r.component_name, r.component_version) for r in new)
            == [("watch", watch.id, "acme-sign", "1.4.2")] * 2
        )
        assert {r.plan_item_id for r in new} == {e["item_id"] for e in watch.items}
        assert all(
            db.scalars(select(ReviewRow).where(ReviewRow.run_id == r.id)).first() is not None for r in new
        )  # each reviewed, as every run is
        for r in new:
            code = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == r.id)).one()
            assert (code.source, code.repository, code.branch, code.commit, code.change_id) == (
                "repository",
                "acme-sign",
                REVERT,
                watch.head_commit,
                None,
            )
            assert code.file_sha256 == watch.files[0]["new_sha256"]  # the registered file that ran is the change's file
        # the speed test compared the change with the code it starts from
        assert {r.baseline_version for r in new} == {"1.4.3"}
        # "before" is a reviewed run that was already there, on exactly the code the change starts from: nothing ran on that code again
        for entry in watch.items:
            earlier = db.get(TestRunRow, entry["before_run_id"])
            code = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == earlier.id)).one()
            assert (
                earlier.id <= ran.runs_before
                and earlier.plan_item_id == entry["item_id"]
                and earlier.spec_hash == entry["spec_hash"]
            )
            assert (code.component_version, code.file_sha256) == ("1.4.3", watch.files[0]["old_sha256"])


def test_the_reviewer_says_what_differs_and_that_sets_the_changes_status_word(ran):
    run = ran.done["run"]
    assert (
        ran.done["status"] == "passed_before_fails_now" and run["state"] == "reviewed" and run["covers_picked"] is True
    )
    review = run["review"]
    assert (
        review["believed"] is True
        and review["status"] == "passed_before_fails_now"
        and len(review["record_sha256"]) == 64
    )
    assert review["counts"] == {
        "tests": 2,
        "not_trusted": 0,
        "not_compared": 0,
        "fails_now": 1,
        "passes_now": 0,
        "same": 0,
        "slower_now": 0,
        "not_slower": 1,
    }
    by_kind = {t["kind"]: t for t in run["tests"]}
    assert (
        by_kind["bad_signatures"]["before"]["code"],
        by_kind["bad_signatures"]["now"]["code"],
        by_kind["bad_signatures"]["outcome"],
    ) == ("passed", "failed", "fails_now")
    # the speed test is placed by its run on the change alone: that run timed the change side by side with the code before
    assert (by_kind["speed_size"]["now"]["code"], by_kind["speed_size"]["outcome"]) == ("no_slowdown", "not_slower")
    assert all(t["before_made_here"] is False and t["job"] is None for t in run["tests"]) and (
        run["finished"],
        run["total"],
    ) == (2, 2)
    with ran.lab.db() as db:
        stored = db.scalars(select(WatchReviewRow).where(WatchReviewRow.watch_run_id == run["id"])).one()
        assert stored.reviewer == RuleReviewer.engine_id and stored.status == "passed_before_fails_now"


def test_a_watch_run_never_stands_in_for_a_result_of_the_assessments_own_tests(ran):
    before, after = ran.before, ran.after
    # Evidence's results and the test plan read exactly what they read before the watch run
    assert after.own == before.own
    # Fixes: every entry that was there is as it was. The change undoes a merged fix, so one entry is new: the
    # developer's change itself, text only (its own tests are below).
    assert {key: after.fixes[key] for key in before.fixes} == before.fixes
    assert [key for key in after.fixes if key not in before.fixes] == [f"fix-{ran.done['id']}"]
    # On Checks every row that was there is as it was. The watch run's rows are new rows of their own, each saying
    # where it came from and leading back to the change.
    assert {key: after.rows[key] for key in before.rows} == before.rows
    new = {key: json.loads(row) for key, row in after.rows.items() if key not in before.rows}
    assert sorted(new) == sorted(f"watch-{e['item_id']}" for e in ran.done["run"]["tests"])
    for row in new.values():
        assert row["came_from"] == {"key": "watch", "label": "Change watch"} and row["group"] == "encryption"
        assert row["link"] == {"page": "change-watch", "item": ran.done["id"]} and row["state"] == "done"
        assert row["ran_on"].startswith("acme-sign 1.4.2, the change on dev/revert-range-check (commit ")
    # the three parts that were there are untouched; the watch run has a part of its own
    assert {key: after.parts[key] for key in ("plan", "retests", "proofs")} == {
        key: before.parts[key] for key in ("plan", "retests", "proofs")
    }
    assert json.loads(before.parts["changes"]) is None and json.loads(after.parts["changes"])["count_label"] == "1 run"
    # The Overview: every finding, every fact and every count of fixes is as it was (the change's entry in Fixes is
    # listed apart and counted nowhere: its own test is below). Two figures move, both counts of runs and neither a
    # finding: the checks of Crypto tests that are done go up by the two runs on the change, and "runs recorded"
    # by the same two.
    assert after.findings == before.findings
    for key, group in before.overview.items():
        assert after.overview[key]["facts"] == group["facts"] and after.overview[key]["fixes"] == group["fixes"]
        if key != "encryption":
            assert after.overview[key]["checks"] == group["checks"] and after.counts[key] == before.counts[key]
    assert after.overview["encryption"]["checks"] == {
        **before.overview["encryption"]["checks"],
        "done": before.overview["encryption"]["checks"]["done"] + 2,
    }
    assert after.recorded == before.recorded + 2
    # what Fixes counts as findings with a fix, group by group, what the Projects row counts, and the next step
    assert after.counted_fixes == before.counted_fixes
    with ran.lab.db() as db:
        # (and the bad-signatures test of the plan still reads Failed on 1.4.2 from its own first run, not from the watch run)
        phases = {r.phase for r in db.scalars(select(TestRunRow).where(TestRunRow.plan_id == ran.plan.id)).all()}
    assert {"first", "proof", "watch"} <= phases


def test_a_change_that_makes_passing_tests_fail_has_a_text_only_entry_in_fixes_that_names_them_and_shows_the_lines_taken_out(
    ran,
):
    lab, plan, change = ran.lab, ran.plan, ran.done
    state = next(f for f in lab.fix_states(plan.id) if f["source_kind"] == "developer_change")
    assert (state["id"], state["kind"], state["status"], state["answers"], state["actions"]) == (
        f"fix-{change['id']}",
        "text",
        "text_only",
        [],
        {},
    )
    assert [(t["kind"], t["outcome"]) for t in state["developer_change"]["tests"]] == [("bad_signatures", "fails_now")]
    view = lab.fixes_view(plan.id)
    models.FixesView.model_validate(view)
    entry = next(f for f in view["fixes"] if f["id"] == state["id"])
    assert entry["title"] == "Revert the range check: 1 test that passed now fails"
    assert entry["list_source"] == "Came from: developer's change dev/revert-range-check"
    assert (entry["status"]["word"], entry["kind"], entry["group"], entry["fix_state"], entry["is_demo"]) == (
        "Text only",
        "text",
        "encryption",
        "open",
        True,
    )
    # It sits in the group of the tests it reruns, under a heading of its own, and is counted nowhere: not in the
    # page's own count, not in its group's counts or list, not on the Overview and not in the Projects row.
    assert entry["apart"] is True and [f["id"] for f in view["fixes"] if f["apart"]] == [state["id"]]
    counted = [f for f in view["fixes"] if not f["apart"]]
    assert view["list_title"] == f"Open findings with a fix ({len(counted)})" and len(counted) == len(view["fixes"]) - 1
    by_group = {g["key"]: g for g in view["groups"]}
    assert by_group["encryption"]["apart"] == {
        "label": "From a developer's change",
        "note": (
            "A developer's change is not the system until someone merges it. A suggestion listed here is not counted with "
            "the assessment's findings."
        ),
        "fix_ids": [state["id"]],
    }
    assert all(g["apart"] is None for key, g in by_group.items() if key != "encryption")
    assert state["id"] not in by_group["encryption"]["fix_ids"]
    assert sum(by_group["encryption"]["counts"].values()) == len(by_group["encryption"]["fix_ids"])
    whole = lab.assessment_view(lab.assessment_for(plan_id=plan.id).id)
    assert whole["counts"]["fixes"]["total"] == len(counted)
    assert sum(
        g["fixes"]["open"] + g["fixes"]["in_progress"] + g["fixes"]["done"]
        for g in whole["blocks"]["groups"]
        if g["fixes"]
    ) == len(counted)
    # it offers nothing to press: the app has made no change for a developer's branch, and never merges one
    assert (
        entry["actions"] == {"buttons": [], "note": None}
        and entry["pull_request"] is None
        and entry["patch"] is None
        and entry["proposal"] is None
    )
    assert entry["proof"]["text"].startswith(
        "None. This suggestion is text only: the app has not applied it or tested it."
    )
    assert "The app never merges a developer's change." in entry["approvers"]["text"]
    # where it came from: the change on Change watch, and the failing run on the change (a row of that watch run on Checks)
    assert entry["came_from_links"] == [
        {"label": "The developer's change", "link": {"page": "change-watch", "item": change["id"]}},
        {
            "label": "Attacker tricks (our short list) on the change",
            "link": {
                "page": "checks",
                "item": f"watch-{state['developer_change']['tests'][0]['item_id']}-in-{change['run']['id']}",
            },
        },
    ]
    suggestion, taken_out = entry["sections"]
    assert (suggestion["key"], taken_out["key"]) == ("suggestion", "change")
    assert suggestion["suggestion"]["intro"][0] == (
        "Attacker tricks (our short list) passed on the code before (acme-sign 1.4.3) and fails on this "
        "change (acme-sign 1.4.2)."
    )
    # the lines the change takes out are the lines the merged fix added: every one of them is marked as removed
    removed = [line["text"] for part in taken_out["parts"] for line in part["before"] if line["mark"] == "-"]
    assert removed and taken_out["line"] == f"{len(removed)} lines removed, in {len(taken_out['parts'])} places"
    assert any("r" in text and "s" in text and "<" in text for text in removed)  # the range check itself
    assert all(
        part["title"].startswith("acme_sign.py, from line ") and part["before_label"]["strong"] == "acme-sign 1.4.3"
        for part in taken_out["parts"]
    )
    words = json.dumps(entry).lower()
    assert "secure" not in words and "severity" not in words and "score" not in words
    # the change's own panel leads to it, and no other change's does
    page = lab.change_watch_view(plan.id)
    shown = next(c for c in page["changes"] if c["id"] == change["id"])
    assert shown["panel"]["fix_line"] == "A suggestion for this change is in Fixes. It is text only."
    assert shown["panel"]["fix"] == {"page": "fixes", "item": state["id"], "group": None}
    assert all(
        c["panel"]["fix"] is None and c["panel"]["fix_line"] is None for c in page["changes"] if c["id"] != change["id"]
    )


def test_checks_and_evidence_list_the_watch_runs_under_their_change_with_every_run_behind_each_row(ran):
    lab, plan, run = ran.lab, ran.plan, ran.done["run"]
    encryption = next(g for g in lab.checks_view(plan.id)["groups"] if g["key"] == "encryption")
    part = encryption["parts"]["changes"]
    assert (part["key"], part["label"]) == (
        "changes",
        "Change watch",
    ) and "never replace a result of the test plan" in part["note"]
    block = part["blocks"][0]
    assert block["key"] == f"watch-{run['id']}" and block["newest"] is True
    assert block["title"] == f"From a developer's change: dev/revert-range-check, commit {ran.listed['head'][:7]}"
    assert block["line"].startswith(
        "The tests picked for this change ran on its code, acme-sign 1.4.2. The run started "
    )
    by_kind = {r["kind"]: r for r in block["rows"]}
    assert sorted(by_kind) == ["bad_signatures", "speed_size"]
    tricks = by_kind["bad_signatures"]
    item = next(t["item_id"] for t in run["tests"] if t["kind"] == "bad_signatures")
    assert (
        tricks["id"] == f"watch-{item}-in-{run['id']}" and tricks["result"]["label"] == "Failed" and tricks["runs"] == 1
    )
    assert tricks["came_from"] == {"key": "watch", "label": "Change watch"} and tricks["link"] == {
        "page": "change-watch",
        "item": ran.done["id"],
    }
    assert (
        tricks["ran_on"] == f"acme-sign 1.4.2, the change on dev/revert-range-check (commit {ran.listed['head'][:7]})"
    )
    assert tricks["evidence_link"] == {"page": "evidence", "item": f"watch-{item}"}
    # the row opens like every check: its newest result as its own page words it, and its run's record
    detail = lab.check_detail(plan.id, tricks["id"])
    assert detail["check"]["id"] == tricks["id"] and detail["result"]["label"] == "Failed" and len(detail["runs"]) == 1
    assert detail["result"]["run_record"] and detail["result"]["component"] == "acme-sign 1.4.2"
    # the test's own row on Checks still reads its own first result, with its own count of runs
    own = next(r for r in lab.ledger(plan.id)["rows"] if r["id"] == f"test-{item}")
    assert own["result"]["label"] == "Failed" and own["came_from"]["key"] == "plan" and own["runs"] == 1
    # and the Change watch panel links each side of before and now to its row
    change = next(c for c in lab.change_watch_view(plan.id)["changes"] if c["id"] == ran.done["id"])
    shown = next(r for r in change["panel"]["results"] if r["item_id"] == item)
    assert shown["now"]["link"] == {"page": "checks", "item": tricks["id"], "group": None}
    assert shown["before"]["link"]["page"] == "checks" and shown["before"]["link"]["item"].startswith(
        f"proof-{item}-in-"
    )
    assert lab.check_detail(plan.id, shown["before"]["link"]["item"])["result"]["label"] == "Passed"


def test_run_again_makes_a_second_watch_run_and_the_newest_one_counts(ran):
    again = one(ran.lab.run_picked_tests(ran.plan.id, ran.listed["id"]), REVERT)
    assert again["status"] == "running" and again["run"]["id"] > ran.done["run"]["id"]
    ran.lab.wait_until_idle(ran.plan.id, 120)
    newest = one(ran.lab.change_watch_state(ran.plan.id), REVERT)
    assert newest["status"] == "passed_before_fails_now" and newest["run"]["id"] == again["run"]["id"]
    with ran.lab.db() as db:
        assert (
            len(db.scalars(select(WatchRunRow).where(WatchRunRow.plan_id == ran.plan.id)).all()) == 2
        )  # the first one is kept


def test_the_stored_review_is_believed_only_while_reviewing_again_gives_exactly_it(ran, monkeypatch):
    real = ran.lab.reviewer.review_watch
    monkeypatch.setattr(ran.lab.reviewer, "review_watch", lambda record: {**real(record), "status": "no_difference"})
    doubted = one(ran.lab.change_watch_state(ran.plan.id), REVERT)
    assert (
        doubted["status"] == "couldnt_trust"
        and doubted["run"]["review"]["believed"] is False
        and doubted["run"]["review"]["tests"] == []
    )
    monkeypatch.undo()
    assert one(ran.lab.change_watch_state(ran.plan.id), REVERT)["status"] == "passed_before_fails_now"
    # the byte-for-byte check is made again at every read: a registry that no longer holds that program is not believed
    monkeypatch.setattr(components, "registered_version", lambda name, files: None)
    assert (
        one(ran.lab.change_watch_state(ran.plan.id), REVERT)["status"] == "cant_run"
    )  # (nothing of it may run any more)
    assert one(ran.lab.change_watch_state(ran.plan.id), REVERT)["run"]["review"]["believed"] is False


@pytest.mark.parametrize("table", WATCH_TABLES)
def test_raw_sql_cannot_change_or_delete_a_watch_run_or_its_review(ran, table):
    assert table in APPEND_ONLY_TABLES
    with ran.lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {WATCH_TABLES[table]} = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


def test_before_is_the_newest_reviewed_run_on_exactly_the_code_the_change_starts_from(ran):
    """Several runs of "Attacker tricks" are there by now: its first run (on 1.4.2), the proof's run (on 1.4.3) and the
    watch runs (on 1.4.2, the newest of all). After a retest on 1.4.3 the next watch run must compare with that
    retest's run: the newest reviewed one on exactly the code the change starts from, whatever it was run for."""
    lab, plan = ran.lab, ran.plan
    lab.start_retest(plan.id, "1.4.3")
    lab.wait_until_idle(plan.id, 120)
    change = one(lab.change_watch_state(plan.id), REVERT)
    lab.run_picked_tests(plan.id, change["id"])
    lab.wait_until_idle(plan.id, 120)
    done = one(lab.change_watch_state(plan.id), REVERT)
    assert done["status"] == "passed_before_fails_now"
    for test in done["run"]["tests"]:
        with lab.db() as db:
            before = db.get(TestRunRow, test["before"]["run_id"])
            code = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == before.id)).one()
            candidates = db.scalars(
                select(TestRunRow)
                .join(RunCodeRow, RunCodeRow.run_id == TestRunRow.id)
                .where(TestRunRow.plan_item_id == test["item_id"], RunCodeRow.component_version == "1.4.3")
                .order_by(TestRunRow.id)
            ).all()
            newer_on_other_code = db.scalars(
                select(TestRunRow)
                .join(RunCodeRow, RunCodeRow.run_id == TestRunRow.id)
                .where(
                    TestRunRow.plan_item_id == test["item_id"],
                    RunCodeRow.component_version == "1.4.2",
                    TestRunRow.id > before.id,
                    TestRunRow.id < test["now"]["run_id"],
                )
            ).all()
        assert (before.phase, code.component_version) == ("retest", "1.4.3") and test["before_made_here"] is False
        assert [r.phase for r in candidates] == ["proof", "retest"] and before.id == candidates[-1].id
        assert (
            newer_on_other_code == []
        )  # (nothing ran in between; the watch runs on 1.4.2 before the retest are older)
    with lab.db() as db:  # and runs on the change's own code (1.4.2), however new, were never taken as "before"
        watch_runs = [r.id for r in db.scalars(select(TestRunRow).where(TestRunRow.phase == "watch")).all()]
    assert not {t["before"]["run_id"] for t in done["run"]["tests"]} & set(watch_runs)
    # the entry in Fixes is about what the change reads now: one entry, however many runs said so ...
    assert [f["id"] for f in lab.fix_states(plan.id) if f["source_kind"] == "developer_change"] == [f"fix-{done['id']}"]
    # ... and it goes when the change no longer reads "Passed before, fails now": after the plan changes, the last run
    # is no longer a run of the tests picked now, the change reads "Not run yet", and Fixes has no entry for it
    lab.add_test(plan.id, "mldsa_compare")
    assert one(lab.change_watch_state(plan.id), REVERT)["status"] == "not_run"
    assert not [f for f in lab.fix_states(plan.id) if f["source_kind"] == "developer_change"]


# ---------------------------------------------------------------- other changes, and what is refused


@pytest.fixture(scope="module")
def connected(tmp_path_factory):
    """An assessment with its demo code connected and the proof passed, not merged: the connected branch holds 1.4.2."""
    lab = make_lab(tmp_path_factory.mktemp("watch-run-branches"))
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        yield SimpleNamespace(lab=lab, plan=plan, repo=repo_of(lab, plan.id))
    finally:
        lab.stop()


def test_a_developers_own_fix_reads_failed_before_passes_now_against_the_first_results(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    repo.branch_from(
        "dev/own-fix",
        repo.branch("main"),
        {"acme_sign.py": V143},
        "Check the range of r and s",
        SOMEONE,
        int(time.time()),
    )
    change = one(lab.change_watch_state(plan.id), "dev/own-fix")
    assert change["gives"] == {"name": "acme-sign", "version": "1.4.3"} and change["starts_from"] == {
        "name": "acme-sign",
        "version": "1.4.2",
    }
    lab.run_picked_tests(plan.id, change["id"])
    lab.wait_until_idle(plan.id, 120)
    done = one(lab.change_watch_state(plan.id), "dev/own-fix")
    assert done["status"] == "failed_before_passes_now" and done["run"]["review"]["counts"]["passes_now"] == 1
    by_kind = {t["kind"]: t for t in done["run"]["tests"]}
    assert (by_kind["bad_signatures"]["before"]["code"], by_kind["bad_signatures"]["now"]["code"]) == (
        "failed",
        "passed",
    )
    with lab.db() as db:
        # "before" here is the assessment's own first run of that test: it ran on exactly the code the change starts from
        assert db.get(TestRunRow, by_kind["bad_signatures"]["before"]["run_id"]).phase == "first"
        assert not db.scalars(select(TestRunRow).where(TestRunRow.phase == "watch_base")).all()
    # the plan's own result is still the first one
    row = next(r for r in lab.lab_view(plan.id)["rows"] if r["kind"] == "bad_signatures")
    assert row["result"]["code"] == "failed" and row["after"] is None


def test_while_one_changes_tests_run_every_other_change_keeps_what_its_own_run_found(connected):
    """Two changes pick the same tests of the plan. While the second one's run is going, a job of each of those tests is
    live: the first change must still read what its own finished run found, never "Running" (the review of 6d)."""
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    first = one(lab.change_watch_state(plan.id), "dev/own-fix")
    assert (
        first["status"] == "failed_before_passes_now" and first["run"]["state"] == "reviewed"
    )  # (its run finished in the test above)
    repo.branch_from(
        "dev/other-fix",
        repo.branch("main"),
        {"acme_sign.py": V143},
        "The same fix by someone else",
        Person("C", "c@example.invalid"),
        int(time.time()),
    )
    other = one(lab.change_watch_state(plan.id), "dev/other-fix")
    started = lab.run_picked_tests(plan.id, other["id"])
    assert one(started, "dev/other-fix")["status"] == "running"
    still = one(started, "dev/own-fix")
    assert still["status"] == "failed_before_passes_now" and still["run"] == first["run"]
    assert all(t["job"] is None for t in still["run"]["tests"])
    page = lab.change_watch_view(plan.id)
    shown = {c["branch"]: c for c in page["changes"]}
    assert page["busy"] is True and shown["dev/other-fix"]["status"]["busy"] is True
    assert (
        shown["dev/own-fix"]["status"]["word"] == "Failed before, passes now (1 test)"
        and shown["dev/own-fix"]["status"]["busy"] is False
    )
    # neither can be started meanwhile, and the page says why
    assert {shown[b]["panel"]["run"]["can"] for b in ("dev/own-fix", "dev/other-fix")} == {False}
    assert shown["dev/own-fix"]["panel"]["run"]["blocked_reason"] == BUSY["watch"]
    # the test plan's own card says the same as its Remove button: a test with a live job of a watch run can't be removed
    card = next(t for t in lab.plan_view(plan.id)["tests"] if t["kind"] == "bad_signatures")
    assert card["can_remove"] is False
    assert (
        refusal(lambda: lab.remove_test(plan.id, card["id"]))
        == "This test is waiting or running. Remove it when it has finished."
    )
    lab.wait_until_idle(plan.id, 120)
    after = lab.change_watch_state(plan.id)
    assert (
        one(after, "dev/other-fix")["status"] == "failed_before_passes_now"
        and one(after, "dev/own-fix")["run"] == first["run"]
    )
    assert next(t for t in lab.plan_view(plan.id)["tests"] if t["kind"] == "bad_signatures")["can_remove"] is True
    assert lab.change_watch_view(plan.id)["busy"] is False


def test_the_page_keeps_asking_while_anything_else_runs_for_the_assessment(connected):
    """Run is off with the reason while a test of the plan runs. The page must ask again until it has finished, or the
    button would stay off (the review of 6d): the view says so with `busy`."""
    lab, plan = connected.lab, connected.plan
    card = next(t for t in lab.plan_view(plan.id)["tests"] if t["kind"] == "bad_signatures")
    lab.run_test(plan.id, card["id"])
    page = lab.change_watch_view(plan.id)
    change = next(c for c in page["changes"] if c["branch"] == "dev/own-fix")
    assert page["busy"] is True and change["status"]["busy"] is False
    assert (change["panel"]["run"]["can"], change["panel"]["run"]["blocked_reason"]) == (False, BUSY["tests"])
    lab.wait_until_idle(plan.id, 120)
    page = lab.change_watch_view(plan.id)
    change = next(c for c in page["changes"] if c["branch"] == "dev/own-fix")
    assert (
        page["busy"] is False
        and change["panel"]["run"]["can"] is True
        and change["panel"]["run"]["blocked_reason"] is None
    )
    # the rerun of the first result changed nothing for the change: its "before" was a reviewed run on exactly that code
    assert change["status"]["key"] == "failed_before_passes_now"
    # a change whose tests pass now has no entry in Fixes: an entry is only for tests that passed and fail on the change
    assert not [f for f in lab.fix_states(plan.id) if f["source_kind"] == "developer_change"]
    assert change["panel"]["fix"] is None


def test_what_cannot_run_is_refused_with_the_reason_and_nothing_is_written(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    main = repo.branch("main")
    repo.branch_from(
        "dev/not-ours", main, {"acme_sign.py": V142 + b"\n# edited\n"}, "Edit the signer", SOMEONE, int(time.time())
    )
    repo.branch_from(
        "dev/notes", main, {"acme_sign.py": V142, "notes.txt": b"hello\n"}, "Add notes", SOMEONE, int(time.time())
    )
    state = lab.change_watch_state(plan.id)
    with lab.db() as db:
        before = (
            len(db.scalars(select(WatchRunRow)).all()),
            db.scalar(select(TestRunRow.id).order_by(TestRunRow.id.desc()).limit(1)),
        )
    assert (
        refusal(lambda: lab.run_picked_tests(plan.id, one(state, "dev/not-ours")["id"]))
        == "The changed code is not the same as one of our registered demo programs, so nothing was run."
    )
    assert (
        refusal(lambda: lab.run_picked_tests(plan.id, one(state, "dev/notes")["id"]))
        == "No test is picked for this change, so there is nothing to run."
    )
    for unknown in ("change-000000000000", "dev/notes", "", None, 7):
        assert (
            refusal(lambda unknown=unknown: lab.run_picked_tests(plan.id, unknown), NotFound)
            == "That change is not in the connected repository."
        )
    with lab.db() as db:
        assert before == (
            len(db.scalars(select(WatchRunRow)).all()),
            db.scalar(select(TestRunRow.id).order_by(TestRunRow.id.desc()).limit(1)),
        )
    assert lab.jobs.live(plan.id) == []


def test_a_run_that_was_cut_off_reads_not_run_yet_and_a_run_of_other_tests_no_longer_counts(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    repo.branch_from(
        "dev/second-fix",
        repo.branch("main"),
        {"acme_sign.py": V143},
        "The same fix, again",
        Person("B", "b@example.invalid"),
        int(time.time()),
    )
    change = one(lab.change_watch_state(plan.id), "dev/second-fix")
    with lab.db() as db:  # a watch run whose jobs never wrote a run (the app was closed while they waited)
        items = {i.id: i for i in lab._items(db, plan.id)}
        db.add(
            WatchRunRow(
                plan_id=plan.id,
                branch=change["branch"],
                base_commit=change["base"],
                head_commit=change["head"],
                version="1.4.3",
                base_version="1.4.2",
                files=change["digests"],
                not_picked=[],
                items=[
                    {
                        "item_id": t["item_id"],
                        "spec_hash": items[t["item_id"]].spec_hash,
                        "kind": t["kind"],
                        "before_run_id": None,
                    }
                    for t in change["picked"]
                ],
            )
        )
        db.commit()
    cut = one(lab.change_watch_state(plan.id), "dev/second-fix")
    assert (
        cut["status"] == "not_run"
        and cut["run"]["state"] == "interrupted"
        and cut["run"]["review"] is None
        and cut["run"]["finished"] == 0
    )
    # Run again works after it, and the plan changing afterwards puts the finished run out of date
    lab.run_picked_tests(plan.id, change["id"])
    lab.wait_until_idle(plan.id, 120)
    assert one(lab.change_watch_state(plan.id), "dev/second-fix")["status"] == "failed_before_passes_now"
    lab.add_test(plan.id, "mldsa_compare")
    stale = one(lab.change_watch_state(plan.id), "dev/second-fix")
    assert "mldsa_compare" in [t["kind"] for t in stale["picked"]]
    assert (
        stale["status"] == "not_run" and stale["run"]["state"] == "reviewed" and stale["run"]["covers_picked"] is False
    )


@pytest.mark.slow
def test_a_test_with_no_result_on_the_code_before_also_runs_on_that_code_in_the_same_watch_run(tmp_path):
    lab = make_lab(tmp_path)
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        repo = repo_of(lab, plan.id)
        added = lab.add_test(plan.id, "official_vectors")  # in the plan now, and never run: no result on any code
        item = next(t["id"] for t in added["tests"] if t["kind"] == "official_vectors")
        repo.branch_from(
            "dev/own-fix",
            repo.branch("main"),
            {"acme_sign.py": V143},
            "Check the range of r and s",
            SOMEONE,
            int(time.time()),
        )
        change = one(lab.change_watch_state(plan.id), "dev/own-fix")
        assert "official_vectors" in [t["kind"] for t in change["picked"]]
        lab.run_picked_tests(plan.id, change["id"])
        lab.wait_until_idle(plan.id, 300)
        done = one(lab.change_watch_state(plan.id), "dev/own-fix")
        vectors = next(t for t in done["run"]["tests"] if t["kind"] == "official_vectors")
        assert vectors["before_made_here"] is True and (
            vectors["before"]["code"],
            vectors["now"]["code"],
            vectors["outcome"],
        ) == ("failed", "passed", "passes_now")
        with lab.db() as db:
            base = db.scalars(select(TestRunRow).where(TestRunRow.phase == "watch_base")).all()
            assert [(r.plan_item_id, r.component_version, r.baseline_version, r.retest_id) for r in base] == [
                (item, "1.4.2", None, done["run"]["id"])
            ]
            code = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == base[0].id)).one()
            assert (code.source, code.branch, code.commit) == (
                "repository",
                "dev/own-fix",
                change["base"],
            )  # the commit the change starts from
        assert done["status"] == "failed_before_passes_now" and done["run"]["review"]["counts"]["passes_now"] == 2
        # the plan's own test still has no result of its own: the two runs belong to the watch run
        row = next(r for r in lab.lab_view(plan.id)["rows"] if r["kind"] == "official_vectors")
        assert row["result"] is None
    finally:
        lab.stop()


# ---------------------------------------------------------------- the reviewer's rule by itself


def _run(code, control="as_expected"):
    return {"run_sha256": "ab" * 32, "code": code, "reason_code": None, "control_outcome": control}


def _record(tests, matches=True, kind="bad_signatures"):
    return {
        "schema": "isogeny.watch-run/1",
        "change": {"branch": "dev/x", "base_commit": "a" * 40, "head_commit": "b" * 40, "files": []},
        "matches": {"name": "acme-sign", "version": "1.4.2"} if matches else None,
        "version": "1.4.2",
        "base_version": "1.4.3",
        "tests": [
            {"item_id": n + 1, "kind": kind, "spec_hash": "c" * 64, "before": b, "now": a}
            for n, (b, a) in enumerate(tests)
        ],
    }


@pytest.mark.parametrize(
    "before,now,outcome,status",
    [
        (_run("passed"), _run("failed"), "fails_now", "passed_before_fails_now"),
        (_run("failed"), _run("passed"), "passes_now", "failed_before_passes_now"),
        (_run("passed"), _run("passed"), "same", "no_difference"),
        (_run("failed"), _run("failed"), "same", "no_difference"),
        (_run("passed"), _run("couldnt_run", "not_run"), "not_compared", "cant_run"),  # a stop is not a result
        (_run("couldnt_run", "not_run"), _run("failed"), "not_compared", "cant_run"),
        (None, _run("failed"), "not_compared", "cant_run"),
        (_run("passed"), None, "not_compared", "cant_run"),
        (_run("passed"), _run("couldnt_trust"), "not_trusted", "couldnt_trust"),
        (
            _run("passed"),
            _run("failed", "not_as_expected"),
            "not_trusted",
            "couldnt_trust",
        ),  # a control that did not fail
        (_run("passed", "errored"), _run("passed"), "not_trusted", "couldnt_trust"),
    ],
)
def test_the_watch_rule_places_each_test(before, now, outcome, status):
    review = RuleReviewer().review_watch(_record([(before, now)]))
    assert (
        review["tests"][0]["outcome"] == outcome and review["status"] == status and review["status"] in WATCH_STATUSES
    )
    assert (
        review["counts"][outcome] == 1
        and review["counts"]["tests"] == 1
        and review["reviewer"] == RuleReviewer.engine_id
    )


@pytest.mark.parametrize(
    "before,now,outcome,status",
    [
        # the run on the change is timed side by side with the code before: its own verdict is the comparison
        (_run("measured"), _run("no_slowdown"), "not_slower", "no_difference"),
        (_run("no_slowdown"), _run("no_slowdown"), "not_slower", "no_difference"),
        (_run("no_slowdown"), _run("slowdown"), "slower_now", "passed_before_fails_now"),
        (_run("measured"), _run("slowdown"), "slower_now", "passed_before_fails_now"),
        # a slowdown the code before had against something older says nothing about this change
        (_run("slowdown"), _run("no_slowdown"), "not_slower", "no_difference"),
        (_run("slowdown"), _run("slowdown"), "slower_now", "passed_before_fails_now"),
        (None, _run("no_slowdown"), "not_slower", "no_difference"),  # (its "before" is not needed)
        (_run("couldnt_trust"), _run("no_slowdown"), "not_slower", "no_difference"),
        (_run("no_slowdown"), _run("couldnt_run", "not_run"), "not_compared", "cant_run"),
        (_run("no_slowdown"), None, "not_compared", "cant_run"),
        (
            _run("no_slowdown"),
            _run("no_slowdown", "not_as_expected"),
            "not_trusted",
            "couldnt_trust",
        ),  # the slowed control was not flagged
    ],
)
def test_the_watch_rule_places_the_speed_test_by_its_run_on_the_change_alone(before, now, outcome, status):
    review = RuleReviewer().review_watch(_record([(before, now)], kind="speed_size"))
    assert review["tests"][0]["outcome"] == outcome and review["status"] == status and review["counts"][outcome] == 1


def test_the_most_telling_outcome_among_the_tests_is_the_status_and_code_that_is_not_ours_is_never_trusted():
    review = RuleReviewer()
    mixed = [(_run("passed"), _run("failed")), (_run("failed"), _run("passed")), (_run("passed"), _run("passed"))]
    assert review.review_watch(_record(mixed))["status"] == "passed_before_fails_now"
    assert (
        review.review_watch(_record(mixed + [(_run("passed"), _run("couldnt_run", "not_run"))]))["status"] == "cant_run"
    )
    assert (
        review.review_watch(
            _record(mixed + [(_run("passed"), _run("couldnt_run", "not_run")), (_run("passed"), _run("couldnt_trust"))])
        )["status"]
        == "couldnt_trust"
    )
    assert (
        review.review_watch(_record([(_run("failed"), _run("passed")), (_run("passed"), _run("passed"))]))["status"]
        == "failed_before_passes_now"
    )
    assert review.review_watch(_record([]))["status"] == "cant_run"
    not_ours = review.review_watch(_record([(_run("passed"), _run("passed"))], matches=False))
    assert not_ours["status"] == "couldnt_trust" and not_ours["code_is_ours"] is False
    other_version = _record([(_run("passed"), _run("passed"))])
    other_version["matches"]["version"] = "1.4.3"
    assert review.review_watch(other_version)["status"] == "couldnt_trust"
    # the same record gives the same review, with the record's fingerprint in it
    one_record = _record(mixed)
    assert review.review_watch(one_record) == review.review_watch(json.loads(json.dumps(one_record)))
    assert len(review.review_watch(one_record)["record_sha256"]) == 64
