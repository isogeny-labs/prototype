"""Change watch and Otto: a watch run of an advisory check is kept apart from Otto's side too. It is a run of a
developer's change, not of the assessment: no proposal is made or moved by it, the Project overview's line about
advisory checks does not count it, and the check's own result on Advisories stays (the review of phase 6d)."""
import json

import pytest
from sqlalchemy import select

from app.db import TestRunRow
from app.errors import Conflict
from conftest import demo_plan, play_back_speed
from tests.otto import otto_helpers as helpers

pytestmark = [pytest.mark.needs_otto, pytest.mark.slow]
REVERT = "dev/revert-range-check"


def _what_otto_shows(lab, plan_id: int) -> dict:
    """Everything Otto shows for the assessment: its proposals of every kind, Advisories, and the Project overview."""
    project = lab.assessment_for(plan_id=plan_id).project_id
    text = lambda value: json.dumps(value, sort_keys=True, default=str)          # noqa: E731
    return {"proposals": {kind: text(lab.otto_proposals(plan_id, (kind,))) for kind in ("check", "fix", "plan", "dependency")},
            "advisories": text(lab.advisories_view(plan_id)), "project": text(lab.project_overview(project)["otto"]),
            "own": [(r["title"], (r["after"] or r["result"] or {}).get("label")) for r in lab.lab_view(plan_id)["rows"] if r["kind"] == "advisory_cases"]}


def test_a_watch_run_of_an_advisory_check_changes_nothing_otto_shows(tmp_path, monkeypatch):
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    try:
        play_back_speed(lab)
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        helpers.accept_checks(lab, plan.id)
        lab.migration_view(plan.id)
        lab.measure_migration(plan.id)
        lab.wait_until_measured(plan.id, 100)
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 100)
        for proposal in lab.otto_proposals(plan.id, ("plan",)):
            lab.otto_decide(plan.id, proposal["id"], "accept")
        try:
            lab.connect_code(plan.id)
        except Conflict:            # (the change is Otto's proposal: a person accepts it before the code can be connected)
            for proposal in lab.otto_proposals(plan.id, ("fix",)):
                if proposal["state"] == "proposed" and proposal["current"]:
                    lab.otto_decide(plan.id, proposal["id"], "accept")
            lab.connect_code(plan.id)
        lab.wait_until_idle(plan.id, 100)
        fix = next(f for f in lab.fix_states(plan.id) if f["kind"] == "code")
        lab.open_pull_request(plan.id, fix["id"], ["you"])
        lab.approve(plan.id, fix["id"], "you")
        lab.merge(plan.id, fix["id"])
        lab.retest_now(plan.id, fix["id"])
        lab.wait_until_idle(plan.id, 100)

        listed = lab.bring_in_demo_change(plan.id, "revert-range-check")
        change = next(c for c in listed["changes"] if c["branch"] == REVERT)
        assert "advisory_cases" in [t["kind"] for t in change["picked"]]          # the advisory check runs acme-sign: it is picked
        before = _what_otto_shows(lab, plan.id)
        assert before["own"] and all(label == "Passed" for _, label in before["own"])    # on the fixed version, after the retest
        with lab.db() as db:
            newest = db.scalar(select(TestRunRow.id).order_by(TestRunRow.id.desc()).limit(1))

        lab.run_picked_tests(plan.id, change["id"])
        lab.wait_until_idle(plan.id, 100)
        done = next(c for c in lab.change_watch_state(plan.id)["changes"] if c["branch"] == REVERT)
        by_kind = {t["kind"]: t for t in done["run"]["tests"]}
        # the change undoes the fix, and the watch run shows it: the advisory check passed before and fails on the change
        assert done["status"] == "passed_before_fails_now" and by_kind["advisory_cases"]["outcome"] == "fails_now"
        with lab.db() as db:
            made = db.scalars(select(TestRunRow).where(TestRunRow.id > newest)).all()
            assert made and {r.phase for r in made} <= {"watch", "watch_base"}
        # ... and nothing Otto shows has moved: no proposal is new, changed or about another run; the Project overview
        # counts no advisory check as run since; the check's own result is still the retest's
        assert _what_otto_shows(lab, plan.id) == before
        with lab.db() as db:
            for proposal in lab.otto_proposals(plan.id, ("plan", "fix", "check", "dependency")):
                run = (proposal.get("about") or {}).get("run")
                if run is not None:
                    assert db.get(TestRunRow, run).phase not in ("watch", "watch_base")
    finally:
        lab.stop()
