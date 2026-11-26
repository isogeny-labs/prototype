"""Who did what (design refactor, decision I): every press of a button that decides or changes something in an
assessment leaves one row in `actions`, with the name it was made under, taken at the press from one source; a run is
tied to the press that started it beside the run, which is not touched; and rows are only ever added."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

import record_walk
from app.canonical import sha256_hex
from app.db import (
    APPEND_ONLY_TABLES,
    ActionRow,
    ActionRunRow,
    ApprovalRow,
    AssessmentRow,
    MergeRow,
    ProofRow,
    RetestRow,
    ReviewRow,
    TestRunRow,
    VerifyRunRow,
    WatchRunRow,
)
from app.errors import Conflict
from app.lab import actions
from app.lab.hub import Lab
from app.lab.testlab import run_record
from conftest import held, make_lab
from evidence.actions import well_formed_moment
from record_walk import FIX

# Every press of the shared walk, in the order it was made.
WALKED = [
    "assessment_started",
    "file_imported",
    "address_confirmed",
    "test_removed",
    "verify",
    "dependency_list_added",
    "library_tied",
    "tests_reordered",
    "run",
    "run_all",
    "marked_reviewed",
    "dig_deeper",
    "code_connected",
    "pull_request_opened",
    "approved",
    "approved",
    "merged",
    "retest_now",
    "setting_changed",
    "evidence_downloaded",
    "demo_change_brought_in",
    "picked_tests_run",
    "evidence_downloaded",
]
# The kinds the shared walk does not make. Each has a test of its own, here or (the measurements of the migration demo,
# which take a while) in the slow set.
ELSEWHERE = {
    "assessment_rerun",
    "assessment_changed",
    "closed",
    "address_unconfirmed",
    "test_added",
    "retest",
    "proof_started",
    "measure_dependencies",
}
SLOW_SET = {
    "measure_status",
    "option_chosen",
    "change_tried",
    "approval_asked",
    "change_approved",
    "applied",
    "rolled_back",
}


@pytest.fixture
def walked(request, tmp_path_factory):
    return record_walk.shared(request, tmp_path_factory)


def presses(lab, plan_id: int | None = None) -> list[ActionRow]:
    with lab.db() as db:
        query = select(ActionRow).order_by(ActionRow.id)
        if plan_id is not None:
            query = query.where(ActionRow.plan_id == plan_id)
        return list(db.scalars(query))


def kinds(lab) -> list[str]:
    return [a.kind for a in presses(lab)]


def ties(lab) -> dict[int, int]:
    with lab.db() as db:
        return {t.run_id: t.action_id for t in db.scalars(select(ActionRunRow))}


# ---------------------------------------------------------------- the list of recorded buttons


def test_the_recorded_buttons_are_methods_of_the_lab_and_every_kind_has_a_button():
    for name, what in actions.PRESSES.items():
        assert getattr(Lab, name).records is what, name  # wrapped, and a renamed method fails at import
        assert callable(getattr(Lab, name).__wrapped__)
    assert callable(Lab._run_one.__wrapped__)  # the one function that stores a run is as it was, with the tie around it
    named = {w.kind for w in actions.PRESSES.values() if isinstance(w.kind, str)}
    assert named | {"address_confirmed", "address_unconfirmed", "assessment_changed", "closed"} == set(actions.KINDS)
    assert len(actions.KINDS) == len(set(actions.KINDS))
    # between them the tests of this folder make every kind
    assert set(WALKED) | ELSEWHERE | SLOW_SET == set(actions.KINDS)
    # what already keeps a name is left as it is: none of these leaves a row here
    for name in ("otto_decide", "otto_decide_view", "look_for_advisories", "start_research", "watch_list_mark"):
        assert name not in actions.PRESSES and not hasattr(getattr(Lab, name), "records")
    assert "actions" in APPEND_ONLY_TABLES and "action_runs" in APPEND_ONLY_TABLES


# ---------------------------------------------------------------- the shared walk: one row for one press


def test_every_press_of_the_walk_left_one_row_with_who_when_and_where(walked):
    rows = presses(walked.lab)
    assert [a.kind for a in rows] == WALKED
    for a in rows:
        assert (a.by, a.by_source, a.by_account) == ("You", "default", None), a.kind
        assert well_formed_moment(a.at)
        assert a.assessment_id == walked.assessment_id
    assert [a.at for a in rows] == sorted(a.at for a in rows)
    started, brought, ticked = rows[0], rows[1], rows[2]
    # an assessment that was just started has no file, and a file has no test plan until Checks is opened
    assert (started.import_id, started.plan_id) == (None, None)
    assert (brought.import_id, brought.plan_id) == (walked.imp["id"], None)
    assert (ticked.import_id, ticked.plan_id) == (walked.imp["id"], None)
    assert all((a.import_id, a.plan_id) == (walked.imp["id"], walked.plan_id) for a in rows[3:])


def test_a_press_names_what_it_was_on_and_the_records_it_made(walked):
    lab = walked.lab
    by_kind: dict[str, list[ActionRow]] = {}
    for a in presses(lab):
        by_kind.setdefault(a.kind, []).append(a)

    def one(kind: str) -> ActionRow:
        return by_kind[kind][0]

    assert one("file_imported").detail == {"filename": "acme-pay-cbom.json", "claims": 3, "demo_file": True}
    tick = one("address_confirmed")
    assert tick.item == f"system:server:{walked.address}"
    # the tick is overwritten in place, with no time: the row is its history, with what it was before
    assert tick.detail == {"address": walked.address, "confirmed": True, "resolved_ip": "127.0.0.1", "was": False}
    removed = one("test_removed")
    assert removed.item == f"test:{walked.item['official_vectors']}"
    assert removed.detail["removed"] == [walked.item["official_vectors"]]
    order = one("tests_reordered").detail
    assert order["order"][:2] == [walked.item["certificate"], walked.item["tls_versions"]] and order["moved"]
    assert one("run").item == f"test:{walked.item['certificate']}"
    assert one("run").detail == {"items": [walked.item["certificate"]]}
    assert sorted(one("run_all").detail["items"]) == sorted(
        walked.item[k] for k in ("tls_versions", "certificate", "bad_signatures", "speed_size")
    )
    assert one("marked_reviewed").item == f"run:{walked.first['bad_signatures']}"
    assert one("dig_deeper").item == f"run:{walked.first['tls_versions']}"
    assert {
        a.item
        for k in ("code_connected", "pull_request_opened", "approved", "merged", "retest_now")
        for a in by_kind[k]
    } == {f"fix:{FIX}"}
    # the approvals: ApprovalRow is as it always was; the press adds who pressed, and for which reviewer
    assert [(a.detail["reviewer"], a.detail["as"]) for a in by_kind["approved"]] == [
        ("you", "You"),
        ("a", "Demo reviewer A"),
    ]
    assert one("setting_changed").item == f"system:{walked.server}"
    assert (one("setting_changed").detail["field"], one("setting_changed").detail["value"]) == ("exposure", "internal")
    change = one("demo_change_brought_in")
    assert change.item == f"developer-change:{walked.change['id']}" and change.detail["commit"] == walked.change["head"]
    assert one("picked_tests_run").item == change.item and one("picked_tests_run").detail["again"] is False
    assert [a.detail["fingerprint"] for a in by_kind["evidence_downloaded"]] == [
        sha256_hex(walked.first_download.evidence),
        sha256_hex(walked.download.evidence),
    ]
    # every record a press names is in its own table
    with lab.db() as db:
        for kind, key, table in (
            ("verify", "verify_run_id", VerifyRunRow),
            ("code_connected", "proof_id", ProofRow),
            ("approved", "approval_id", ApprovalRow),
            ("merged", "merge_id", MergeRow),
            ("retest_now", "retest_id", RetestRow),
            ("picked_tests_run", "watch_run_id", WatchRunRow),
        ):
            for a in by_kind[kind]:
                assert db.get(table, a.detail[key]) is not None, (kind, a.detail)
        assert db.scalar(select(func.count(ApprovalRow.id))) == 2  # nothing was added to the approvals themselves


def test_each_run_is_tied_to_the_press_that_started_it_and_the_runs_are_untouched(walked):
    lab = walked.lab
    by_id = {a.id: a for a in presses(lab)}
    tied = ties(lab)
    expected = {
        "first": {"run", "run_all"},
        "proof": {"code_connected"},
        "retest": {"retest_now"},
        "watch": {"picked_tests_run"},
        "watch_base": {"picked_tests_run"},
    }
    with lab.db() as db:
        runs = list(db.scalars(select(TestRunRow).order_by(TestRunRow.id)))
        assert runs and set(tied) == {r.id for r in runs}  # every run, once (the tie's run id is unique)
        for run in runs:
            press = by_id[tied[run.id]]
            assert press.kind in expected[run.phase], (run.phase, press.kind)
            assert run.plan_item_id in press.detail["items"]
            assert press.at <= run.started_at  # pressed before the run began
            # the run record is what it was: its fingerprint is still the one its review was made for
            review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).one()
            assert sha256_hex(run_record(run)) == review.run_sha256
    for press in by_id.values():  # each run-starting press of the walk has exactly the runs it queued
        if press.kind in ("run", "run_all", "retest_now"):
            assert len([r for r, a in tied.items() if a == press.id]) == len(press.detail["items"])


@pytest.mark.parametrize("table", ["actions", "action_runs"])
def test_raw_sql_cannot_change_or_delete_a_press_or_its_tie(walked, table):
    column = {"actions": "by = 'Someone else'", "action_runs": "action_id = 1"}[table]
    with walked.lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {column}", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


def test_a_button_inside_a_button_is_one_row(walked, lab):
    # Retest now calls the retest: one press, one row, and the retest's runs are its runs
    assert "retest" not in kinds(walked.lab) and kinds(walked.lab).count("retest_now") == 1
    # Rerun as new assessment starts an assessment and brings the file in again: one row, in the new assessment
    first = record_walk.start(lab, "Rerun")
    made = lab.rerun_assessment(first.assessment_id)
    rows = [a for a in presses(lab) if a.assessment_id == made["id"]]
    assert [a.kind for a in rows] == ["assessment_rerun"]
    assert rows[0].detail["rerun_of"] == first.assessment_id and rows[0].import_id == rows[0].detail["import_id"]
    with lab.db() as db:
        assert db.get(AssessmentRow, made["id"]).import_id == rows[0].import_id


# ---------------------------------------------------------------- the kinds the shared walk does not make


def test_the_other_presses_of_an_assessment_are_recorded_too(lab):
    w = record_walk.start(lab, "Other presses")
    pid = w.plan_id
    before = len(presses(lab))
    lab.confirm_address(w.imp["id"], w.address, False)  # untick
    lab.confirm_address(w.imp["id"], w.address, True)
    lab.remove_test(pid, w.item["certificate"])
    lab.add_test(pid, "certificate")  # a test that was taken out comes back, with its runs
    lab.add_test(pid, "pq_readiness")  # a test from the catalog is new
    lab.run_all(pid)
    lab.wait_until_idle(pid, 240)
    lab.start_retest(pid, "1.4.3")
    lab.wait_until_idle(pid, 240)
    lab.update_assessment(w.assessment_id, {"name": "Renamed"})
    lab.update_assessment(w.assessment_id, {"purpose": "release_check", "reference": "TICKET-1"})
    lab.update_assessment(w.assessment_id, {"close": True, "signed_off_by": "Kevin", "note": "Done."})
    rows = presses(lab)[before:]
    assert [a.kind for a in rows] == [
        "address_unconfirmed",
        "address_confirmed",
        "test_removed",
        "test_added",
        "test_added",
        "run_all",
        "retest",
        "assessment_changed",
        "assessment_changed",
        "closed",
    ]
    untick, _, _, back, added, _, retest, renamed, purpose, closed = rows
    assert untick.detail["confirmed"] is False and untick.detail["was"] is True
    assert (back.detail["catalog_id"], back.detail["back"], back.detail["added"]) == (
        "certificate",
        [w.item["certificate"]],
        [],
    )
    assert (
        added.detail["catalog_id"] == "pq_readiness" and len(added.detail["added"]) == 1 and added.detail["back"] == []
    )
    assert retest.detail["version"] == "1.4.3" and len(retest.detail["items"]) == 5
    assert renamed.detail == {"changed": {"name": "Renamed"}}
    assert (
        purpose.detail["changed"] == {"purpose": "release_check", "reference": "TICKET-1"}
        and purpose.detail["detail_id"]
    )
    # the sign-off keeps its own name (typed in the Close box); the press says who pressed Close
    assert closed.detail == {"signoff_id": 1} and (closed.by, closed.by_source) == ("You", "default")
    assert lab.evidence_names(w.imp["id"])["signed_off_by"] == "Kevin"


def test_run_proof_again_is_a_press_of_its_own_tied_to_its_proof_runs(lab):
    w = record_walk.start(lab, "Proof again")
    pid = w.plan_id
    lab.played_back_new_version_slower_by_ms = 30.0  # the changed code plays back slower: the first proof does not pass
    lab.run_all(pid)
    lab.wait_until_idle(pid, 120)
    lab.connect_code(pid)
    lab.wait_until_idle(pid, 120)
    lab.played_back_new_version_slower_by_ms = 0.0
    lab.run_proof_again(pid, FIX)
    lab.wait_until_idle(pid, 120)
    again = presses(lab)[-1]
    assert again.kind == "proof_started" and again.item == f"fix:{FIX}"
    assert again.detail["proof_id"] == 2 and len(again.detail["items"]) == 4
    with lab.db() as db:
        mine = {
            r.id for r in db.scalars(select(TestRunRow).where(TestRunRow.phase == "proof", TestRunRow.retest_id == 2))
        }
    assert mine and {r for r, a in ties(lab).items() if a == again.id} == mine


def test_a_measurement_on_a_public_copy_is_recorded_with_the_runs_it_queued(lab, monkeypatch):
    """Measuring a library needs isolated mode. Here the button's own method is stood in for by one that queues a run
    in the phase a measurement runs in, so its record and its tie are checked without a container."""
    w = record_walk.start(lab, "Public copy")
    pid = w.plan_id
    from app.db import PlanItemRow, PlanRow

    def measure(self, plan_id: int, row_id: str | None = None) -> dict:
        with self.db() as db:
            plan, item = db.get(PlanRow, plan_id), db.get(PlanItemRow, w.item["certificate"])
        self._submit(plan, item, "dependencies", None)
        return {}

    monkeypatch.setattr(Lab, "measure_dependencies", actions._pressed(measure, actions.PRESSES["measure_dependencies"]))
    lab.measure_dependencies(pid, "row-1")
    assert lab.jobs.wait_idle(60)
    press = presses(lab)[-1]
    assert press.kind == "measure_dependencies" and press.detail == {"row": "row-1", "items": [w.item["certificate"]]}
    with lab.db() as db:
        run = db.scalars(select(TestRunRow).where(TestRunRow.phase == "dependencies")).one()
    assert ties(lab)[run.id] == press.id
    # in demo mode the real button is refused, and a refused press leaves no row
    monkeypatch.undo()
    with pytest.raises(Conflict, match="isolated mode"):
        lab.measure_dependencies(pid, None)
    assert presses(lab)[-1].id == press.id


@pytest.mark.slow
def test_the_presses_of_the_migration_demo_are_recorded_with_the_measurements_they_started(tmp_path):
    from conftest import free_port, free_ports

    ports = free_ports(5)
    lab = make_lab(tmp_path, migration_ports=ports, lab_nginx_port=free_port())
    try:
        w = record_walk.migration_walk(lab, ports)
        rows = presses(lab, w.plan_id)
        found = [a.kind for a in rows]
        assert SLOW_SET <= set(found)
        measures = [a for a in rows if a.kind == "measure_status"]
        assert [a.detail["again"] for a in measures] == [False, True]
        assert len(measures[0].detail["items"]) >= 5 and measures[0].detail["items"] == measures[1].detail["items"]
        by_kind = {a.kind: a for a in rows}
        assert by_kind["option_chosen"].item == f"system:{w.system}"
        assert by_kind["option_chosen"].detail["option"] == "hybrid"
        for kind in ("change_tried", "approval_asked", "applied", "rolled_back"):
            assert by_kind[kind].item == f"change:{w.key}", kind
        approvals = [a for a in rows if a.kind == "change_approved"]
        assert [(a.detail["reviewer"], a.detail["as"]) for a in approvals] == [("you", "You"), ("a", "Demo reviewer A")]
        # the try's runs, and the measurement the app makes right after an Apply and a Roll back, are tied to those presses
        tied = ties(lab)
        with lab.db() as db:
            phases = {r.id: r.phase for r in db.scalars(select(TestRunRow).where(TestRunRow.plan_id == w.plan_id))}
        assert set(tied) == set(phases)
        for kind, phase in (("change_tried", "try"), ("applied", "migration"), ("rolled_back", "migration")):
            mine = [phases[r] for r, a in tied.items() if a == by_kind[kind].id]
            assert mine and all(p.startswith(phase) for p in mine), (kind, mine)
    finally:
        lab.stop()


# ---------------------------------------------------------------- what leaves no row


def test_a_press_that_is_refused_or_changes_nothing_leaves_no_row(lab):
    w = record_walk.start(lab, "Refused")
    pid = w.plan_id
    with held(lab) as go:
        lab.run_all(pid)
        count = len(presses(lab))
        with pytest.raises(Conflict):
            lab.run_all(pid)  # tests are still running
        with pytest.raises(Conflict):
            lab.export_evidence(pid)  # nothing to download while they run
        assert len(presses(lab)) == count
        go.set()
    lab.wait_until_idle(pid, 120)
    run_id = lab.lab_view(pid)["rows"][0]["result"]["run_id"]
    lab.mark_reviewed(run_id)
    lab.dig_deeper(run_id)
    with lab.db() as db:
        order = [i.id for i in lab._items(db, pid)]
    lab.reorder(pid, order)  # (start() left a gap where it took a test out: this first time the places are renumbered)
    count = len(presses(lab))
    lab.mark_reviewed(run_id)  # marked already
    lab.dig_deeper(run_id)  # asked already
    lab.reorder(pid, order)  # the order it has
    with pytest.raises(Conflict):
        lab.merge(pid, FIX)  # there is no pull request
    assert len(presses(lab)) == count
    # reads leave none either
    lab.plan_view(pid), lab.lab_view(pid), lab.fixes_view(pid), lab.timeline_view(pid), lab.decisions_view(pid)
    assert len(presses(lab)) == count


# ---------------------------------------------------------------- the one name source


def test_the_name_is_the_typed_one_or_you_and_is_taken_at_the_press(lab):
    assert lab.actor() == {"name": "You", "source": "default", "account": None}
    w = record_walk.start(lab, "Names")
    pid = w.plan_id
    with held(lab) as go:
        lab.run_all(pid)  # pressed as "You"; its runs finish later, in job threads
        lab.set_decision_name("Kevin Bacon")
        assert lab.actor() == {"name": "Kevin Bacon", "source": "typed", "account": None}
        go.set()
    lab.wait_until_idle(pid, 120)
    lab.verify(w.imp["id"])
    lab.set_decision_name("")
    lab.run_test(pid, w.item["certificate"])
    lab.wait_until_idle(pid, 120)
    rows = presses(lab)
    run_all, verify, run = rows[-3], rows[-2], rows[-1]
    assert (run_all.kind, run_all.by, run_all.by_source) == ("run_all", "You", "default")
    assert (verify.kind, verify.by, verify.by_source) == ("verify", "Kevin Bacon", "typed")
    assert (run.kind, run.by, run.by_source) == ("run", "You", "default")
    tied = ties(lab)
    assert (
        len([r for r, a in tied.items() if a == run_all.id]) == 4
    )  # tied when they finished, under the name at the press
    # a record keeps the name it was made under: the timeline says the same after the name changed
    said = {e["id"]: e["who"] for d in lab.timeline_view(pid)["days"] for e in d["entries"]}
    assert said[f"press-{run_all.id}"]["name"] == "You" and said[f"press-{run_all.id}"]["source"] == "default"
    assert (said["verify-1"]["name"], said["verify-1"]["source"]) == ("Kevin Bacon", "typed")


@pytest.mark.needs_otto
def test_a_decision_on_a_proposal_of_ottos_keeps_its_own_name_and_gets_no_second_row(tmp_path, monkeypatch):
    from conftest import demo_plan
    from tests.otto import otto_helpers as helpers

    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        lab.set_decision_name("Kevin")
        before = len(presses(lab))
        proposal = helpers.check_proposals(lab, plan.id)[0]
        lab.otto_decide(plan.id, proposal["id"], "accept")
        lab.otto_decide(plan.id, proposal["id"], "undo")
        lab.otto_decide(plan.id, proposal["id"], "reject", "Not this quarter.")
        assert len(presses(lab)) == before  # the decisions are in otto_decisions, with their own name and time
        decided = [r for d in lab.decisions_view(plan.id, "advisories")["days"] for r in d["rows"]]
        assert [r["decision"]["label"] for r in decided] == ["Not added", "Undone", "Accepted"]
        assert all(
            r["who"] == {**r["who"], "name": "Kevin", "source": "decides"} and r["marks"] == ["From Otto"]
            for r in decided
        )
        assert "Reason: Not this quarter." in decided[0]["on"]
        cards = {c["key"]: c for c in lab.decisions_view(plan.id)["cards"]}
        assert cards["otto"]["value"] == "3" and cards["otto"]["small"] == "1 accepted, 1 not added, 1 undone"
        # the advisory's history: the decisions on its proposal, and that a proposal has no time of its own
        history = lab.history_view(plan.id, f"advisory:{proposal['about']['advisory']}")
        assert [line["title"] for line in history["lines"]][-1] == "Proposed by Otto"
        assert (
            history["lines"][-1]["at"] is None
            and "not stored, so it has no time of its own" in history["lines"][-1]["note"]
        )
        assert len([line for line in history["lines"] if line["id"].startswith("otto-")]) == 3
    finally:
        lab.stop()
