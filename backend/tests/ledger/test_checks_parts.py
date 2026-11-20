"""The 5c fixes: on Checks the Crypto tests group is in four labelled parts.

Test plan (the first runs, on the version the file names), Retests by version (one block for each version a retest ran
on, the newest open), Fix proofs (one block for each proof) and Tries on a test copy (only when a server change was
tried). The parts sort rows the page already has: a run shows in one part only, and nothing is decided here. The walk
is the shared demo (Run all, then Retest on 1.4.3); a proof's block is read in tests/test_changes.py, on its own walk."""
import pytest

from app.errors import NotFound
from app.ledger import checks
from app.web import models
from conftest import demo_plan
from tests.view_helpers import problems

SERVER_TESTS = ("tls_versions", "certificate", "pq_readiness")
PROGRAM_TESTS = ("official_vectors", "bad_signatures", "speed_size", "mldsa_compare")


def _parts(view: dict) -> dict:
    return next(g for g in view["groups"] if g["key"] == "encryption")["parts"]


def test_only_the_encryption_tests_group_has_parts_and_the_other_groups_are_as_they_were(demo_flow):
    view = demo_flow.lab.checks_view(demo_flow.plan.id)
    assert problems(view, models.ChecksView, "checks") == []
    assert [g["key"] for g in view["groups"] if g["parts"] is not None] == ["encryption"]
    parts = _parts(view)
    assert [parts[k]["label"] for k in ("plan", "retests", "proofs")] == ["Test plan", "Retests by version", "Fix proofs"]
    assert parts["tries"] is None                          # no server change was tried in this walk


def test_the_test_plan_part_counts_the_plans_tests_and_names_the_version_the_file_names(demo_flow):
    plan = _parts(demo_flow.lab.checks_view(demo_flow.plan.id))["plan"]
    assert plan["count"] == 7 and plan["count_label"] == "7 tests"
    assert plan["note"] == "First runs, on the version the file names: acme-sign 1.4.2."
    assert plan["blocks"] == [] and plan["rows"] == []     # the plan itself is drawn from the plan view, with its buttons


@pytest.mark.parametrize("file_name, said", [
    # four libraries: the first runs are on all four, not on the plan's own program only
    ("real-libraries.csv", "First runs, on the versions the file names: openjdk 17.0.2, python-ecdsa 0.13.2, elliptic 6.5.6 and openssl 3.5.9."),
    # two versions of one program are two programs
    ("multi-target-demo.csv", "First runs, on the versions the file names: acme-sign 1.4.2 and acme-sign 9.9."),
    # a file that names servers only
    ("lab-nginx.csv", "First runs, on what the file names."),
])
def test_the_test_plan_part_names_every_version_the_file_names_when_it_names_several(lab, file_name, said):
    from app.config import DEMO_DIR
    source = DEMO_DIR / file_name
    plan_id = lab.ensure_plan(lab.import_file(source.name, source.read_bytes())["id"])["id"]
    assert _parts(lab.checks_view(plan_id))["plan"]["note"] == said


def test_a_retest_sits_in_the_block_of_the_version_it_ran_on(demo_flow):
    retests = _parts(demo_flow.lab.checks_view(demo_flow.plan.id))["retests"]
    assert retests["count"] == 1 and retests["count_label"] == "1 version" and retests["empty_text"] is None
    [block] = retests["blocks"]
    assert block["title"] == "acme-sign 1.4.3" and block["newest"] is True and block["key"].startswith("on-")
    assert block["line"].startswith("One retest on this version. The newest started ")
    by_kind = {r["kind"]: r for r in block["rows"]}
    assert set(by_kind) == set(SERVER_TESTS + PROGRAM_TESTS)
    for kind in PROGRAM_TESTS:                              # the program the retest moved: it ran on the new version
        row = by_kind[kind]
        assert row["ran_on"] == "acme-sign 1.4.3" and row["mark"] is None and row["came_from"]["key"] == "retest"
    for kind in SERVER_TESTS:                               # a server was not moved: it is run again on what it was
        row = by_kind[kind]
        assert row["mark"] == checks.AS_IT_IS == "tested again as it is" and row["ran_on"] == f"localhost:{demo_flow.lab.settings.demo_tls_port}"
    for row in block["rows"]:
        item = row["id"].split("-")[1]
        assert checks.BLOCK_ROW.match(row["id"]) and row["alias"] == f"retest-{item}"     # the older id still opens it
        assert row["state"] == "done" and row["result"] is not None and row["runs"] == 1


def test_nothing_shows_twice_a_first_run_is_in_the_plan_only_and_a_retest_in_its_block_only(demo_flow):
    lab, plan_id = demo_flow.lab, demo_flow.plan.id
    view = lab.checks_view(plan_id)
    group = next(g for g in view["groups"] if g["key"] == "encryption")
    with lab.db() as db:
        from app.db import TestRunRow
        retest_runs = {r.plan_item_id: r.id for r in db.query(TestRunRow).filter(TestRunRow.phase == "retest").all()}
    [block] = group["parts"]["retests"]["blocks"]
    for row in block["rows"]:
        detail = lab.check_detail(plan_id, row["id"])
        assert problems(detail, models.CheckDetail, "check") == []
        item = int(row["id"].split("-")[1])
        # the block's row is read on the retest's own run, and lists no first run
        assert [r["run_id"] for r in detail["runs"]] == [retest_runs[item]] and detail["result"]["run_id"] == retest_runs[item]
        assert detail["check"]["id"] == row["id"] and detail["check"]["result"] == row["result"]
        # the plan's own row for the same test holds the first run and not the retest
        first = lab.check_detail(plan_id, f"test-{item}")
        assert retest_runs[item] not in [r["run_id"] for r in first["runs"]]
    # the older ids still open the same checks
    older = lab.check_detail(plan_id, block["rows"][0]["alias"])
    assert older["check"]["id"] == block["rows"][0]["alias"] and older["result"]["run_id"] == lab.check_detail(plan_id, block["rows"][0]["id"])["result"]["run_id"]
    with pytest.raises(NotFound):
        lab.check_detail(plan_id, "retest-1-on-999")
    with pytest.raises(NotFound):
        lab.check_detail(plan_id, "retest-999999-on-1")


def test_before_any_retest_the_part_says_so(lab):
    plan = demo_plan(lab)
    parts = _parts(lab.checks_view(plan.id))
    assert parts["retests"]["count"] == 0 and parts["retests"]["blocks"] == []
    assert parts["retests"]["empty_text"] == "No retest yet. Retest new version reruns every test in the plan on another version."
    assert parts["proofs"]["count"] == 0 and parts["proofs"]["empty_text"].startswith("No fix proof yet.")
    assert parts["plan"]["count"] == 5 and parts["tries"] is None


def test_the_blocks_time_is_marked_for_a_browser_and_in_utc_words_for_a_script(demo_flow):
    from app.present import times
    plain = _parts(demo_flow.lab.checks_view(demo_flow.plan.id))["retests"]["blocks"][0]["line"]
    assert plain.endswith(" UTC.") and "[[" not in plain
    with times.for_screen():
        marked = _parts(demo_flow.lab.checks_view(demo_flow.plan.id))["retests"]["blocks"][0]["line"]
    assert "[[time:" in marked and "UTC" not in marked
