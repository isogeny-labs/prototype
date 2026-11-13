"""Fixes, through the same service path as the buttons: connect the demo code, the proof that starts by itself,
the pull request, approvals, merge and Retest now; what is refused when; and the read gate against tampering."""
import hashlib
import threading
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import components, demo_repo
from app.canonical import sha256_hex
from app.config import DEMO_CBOM
from app.db import (
    APPEND_ONLY_TABLES, ApprovalRow, ChangeRow, CodeConnectionRow, MergeRow, ProofReviewRow, ProofRow, PullRequestRow, RetestRow,
    ReviewRow, RunCodeRow, TestRunRow,
)
from app.errors import BadRequest, Conflict, NotFound
from app.gitrepo import GitRepo, GitRepoError
from app.testlab import run_record
from conftest import demo_plan, make_lab, result_of
from test_records import RUN_TABLES

FIX = "fix-ecdsa-range-check"
PROOF_RUNNING = "A proof is running in Fixes. Wait until it has finished."
RUN_FIRST = "Run every test in the plan first, so there is a result to compare with."
PROOF_CHANGED = "The stored proof no longer matches its fingerprint."
BUNDLED = GitRepo(demo_repo.bundled("acme-sign"))
OLD_FILE = components.lookup("acme-sign", "1.4.2").read_bytes()
NEW_FILE = components.lookup("acme-sign", "1.4.3").read_bytes()
SOFTWARE = ("official_vectors", "bad_signatures", "speed_size")


def refusal(call, kind=Conflict) -> str:
    with pytest.raises(kind) as caught:
        call()
    return str(caught.value)


def code_fix(states: list[dict]) -> dict:
    return next(f for f in states if f["id"] == FIX)


def repo_of(lab, fix: dict) -> GitRepo:
    return GitRepo(lab.settings.data_dir / fix["connection"]["folder"])


def listing(folder) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def small_plan(lab, without=("official_vectors", "speed_size")):
    """The demo plan without its two slow tests: old TLS versions, certificate strength, bad signatures."""
    plan = demo_plan(lab)
    for kind in without:
        lab.remove_test(plan.id, plan.item[kind])
    return plan


def proved(lab, plan) -> dict:
    """Run all, connect the demo code and wait for the proof that starts by itself."""
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    lab.connect_code(plan.id)
    lab.wait_until_idle(plan.id, 120)
    return code_fix(lab.fix_states(plan.id))


# ---------------------------------------------------------------- the whole flow, once

@pytest.fixture(scope="module")
def fix_flow(tmp_path_factory):
    """The demo fix from start to end: the five suggested tests plus the post-quantum check, Run all, Connect demo
    code, the proof, a pull request with two reviewers, both approvals, the merge, Retest now. Then the demo file is
    imported a second time and connected again. Tests that only read share it."""
    lab = make_lab(tmp_path_factory.mktemp("fix-flow"))
    try:
        bundled_before = listing(demo_repo.bundled("acme-sign"))
        plan = demo_plan(lab)
        plan.item = {t["kind"]: t["id"] for t in lab.add_test(plan.id, "pq_readiness")["tests"]}
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 300)
        first = lab.lab_view(plan.id)
        before = lab.fix_states(plan.id)
        connected = lab.connect_code(plan.id)
        during = SimpleNamespace(
            lab=lab.lab_view(plan.id), plan=lab.plan_view(plan.id),
            refusals=[refusal(lambda: lab.run_test(plan.id, plan.item["certificate"])), refusal(lambda: lab.run_all(plan.id)),
                      refusal(lambda: lab.start_retest(plan.id, "1.4.3")), refusal(lambda: lab.export_evidence(plan.id)),
                      refusal(lambda: lab.run_proof_again(plan.id, FIX))],
            remove=refusal(lambda: lab.remove_test(plan.id, plan.item["speed_size"])),
            early_pull_request=refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])))
        lab.wait_until_idle(plan.id, 300)
        ready = lab.fix_states(plan.id)
        lab_after_proof = lab.lab_view(plan.id)
        opened = lab.open_pull_request(plan.id, FIX, ["a", "you"])
        early_merge = refusal(lambda: lab.merge(plan.id, FIX))
        one = lab.approve(plan.id, FIX, "you")
        still_early_merge = refusal(lambda: lab.merge(plan.id, FIX))
        two = lab.approve(plan.id, FIX, "a")
        merged = lab.merge(plan.id, FIX)
        patch = lab.patch_file(plan.id, FIX)
        retest_started = lab.retest_now(plan.id, FIX)
        lab.wait_until_idle(plan.id, 300)
        final_lab, final = lab.lab_view(plan.id), lab.fix_states(plan.id)
        export = lab.export_evidence(plan.id)
        # the same file again: a new import, a new plan, its own copy of the code (and a report-only test in the plan)
        again = small_plan(lab)
        lab.add_test(again.id, "mldsa_compare")
        second = proved(lab, again)
        second_request = code_fix(lab.open_pull_request(again.id, FIX, ["b"]))["pull_request"]
        yield SimpleNamespace(lab=lab, plan=plan, first=first, before=before, connected=connected, during=during, ready=ready,
                              lab_after_proof=lab_after_proof, opened=opened, early_merge=early_merge, one=one,
                              still_early_merge=still_early_merge, two=two, merged=merged, patch=patch,
                              retest_started=retest_started, final_lab=final_lab, final=final, export=export, again=again,
                              second=second, second_request=second_request, bundled_before=bundled_before)
    finally:
        lab.stop()


def test_before_connecting_the_failed_signing_tests_share_one_code_fix(fix_flow):
    assert [(f["id"], f["kind"], f["status"]) for f in fix_flow.before] == [(FIX, "code", "not_connected"), ("fix-tls-versions", "text", "text_only")]
    code, server = fix_flow.before
    failed = {k: result_of(fix_flow.first, k)["run_id"] for k in ("official_vectors", "bad_signatures", "tls_versions")}
    assert code["answers"] == [{"item_id": fix_flow.plan.item[k], "kind": k, "run_id": failed[k], "phase": "first"}
                               for k in ("official_vectors", "bad_signatures")]
    assert server["answers"] == [{"item_id": fix_flow.plan.item["tls_versions"], "kind": "tls_versions", "run_id": failed["tls_versions"], "phase": "first"}]
    assert code["component"] == {"name": "acme-sign", "version": "1.4.2"} and code["template_id"] == "ecdsa-range-check"
    assert code["source_kind"] == server["source_kind"] == "failed_tests"
    assert code["connection"] is code["change"] is code["proof"] is code["pull_request"] is code["merge"] is None
    assert code["actions"]["connect"] is None and code["rerun_blocked"] is None  # every test has a result, nothing runs
    assert code["actions"]["open_pull_request"] == code["actions"]["run_proof_again"] == "Connect the demo code first."
    assert server["actions"] == {} and server["change"] is None  # a text-only suggestion has no buttons


def test_connecting_makes_the_plans_own_copy_and_starts_the_proof_by_itself(fix_flow):
    code = code_fix(fix_flow.connected)
    assert code["status"] == "proving"
    connection, change, proof = code["connection"], code["change"], code["proof"]
    assert connection["repository"] == "acme-sign" and connection["folder"] == f"repos/plan-{fix_flow.plan.id}/acme-sign.git"
    assert connection["branch"] == "main" and connection["base_commit"] == BUNDLED.branch("main") and connection["is_demo"] is True
    assert connection["component"] == {"name": "acme-sign", "version": "1.4.2"}
    assert (change["fix_key"], change["template_id"], change["written_by"]) == ("ecdsa-range-check", "ecdsa-range-check", "fix_template")
    assert change["proposed_by"] == "isogeny.rule-engine/1" and change["source_kind"] == "failed_tests"
    assert change["title"] == "Reject signatures whose r or s is out of range" and change["branch"] == "fix/ecdsa-range-check"
    assert change["base_commit"] == connection["base_commit"] and change["head_commit"] != change["base_commit"]
    assert [r["kind"] for r in change["source"]["runs"]] == ["official_vectors", "bad_signatures"]
    assert [r["run_id"] for r in change["source"]["runs"]] == [a["run_id"] for a in code_fix(fix_flow.before)["answers"]]
    (changed,) = change["files"]
    assert (changed["name"], changed["added"], changed["removed"]) == ("acme_sign.py", 3, 1)
    assert changed["old_sha256"] == hashlib.sha256(OLD_FILE).hexdigest() and changed["new_sha256"] == hashlib.sha256(NEW_FILE).hexdigest()
    assert [p["title"] for p in changed["parts"]] == ["The check: reject a signature whose numbers are out of range", "The version number"]
    # the byte-for-byte check: the changed code is exactly our registered 1.4.3, so that is what the proof runs
    assert change["built"] == {"file": "acme_sign.py", "sha256": changed["new_sha256"], "matches": {"name": "acme-sign", "version": "1.4.3"}}
    assert (proof["state"], proof["baseline_version"], proof["version"], proof["total"]) == ("running", "1.4.2", "1.4.3", 6)
    assert proof["covers_plan"] is True and proof["review"] is None and code["proofs"] == 1
    assert [t["kind"] for t in proof["tests"]] == [r["kind"] for r in fix_flow.first["rows"]]
    for row in proof["tests"]:
        assert row["first"]["run_id"] == result_of(fix_flow.first, row["kind"])["run_id"]  # compared with what Evidence Lab shows
        assert (row["job"] is None) != (row["proof"] is None) and row["check"] is None
        assert row["job"] is None or row["job"]["status"] in ("waiting", "running")
    assert any(row["job"] is not None for row in proof["tests"])
    assert all(reason is not None for action, reason in code["actions"].items())  # nothing can be pressed while it proves
    # the repository: main untouched, the change on its own branch, one commit by the template
    repo = repo_of(fix_flow.lab, code)
    commit = repo.read_commit(change["head_commit"])
    assert commit.parents == (change["base_commit"],) and commit.author.name == "Evidence Lab fix template"
    assert commit.title == change["title"] and "From a fix template: ecdsa-range-check" in commit.message
    assert repo.files(change["base_commit"]) == {"acme_sign.py": OLD_FILE} and repo.files(change["head_commit"]) == {"acme_sign.py": NEW_FILE}
    assert repo.read_blob(changed["old_blob"]) == OLD_FILE and repo.read_blob(changed["new_blob"]) == NEW_FILE


def test_while_the_proof_runs_everything_else_waits_and_says_why(fix_flow):
    during = fix_flow.during
    assert during.refusals == [PROOF_RUNNING] * 5
    assert during.remove == "This test is waiting or running. Remove it when it has finished."
    assert during.early_pull_request == "A pull request can be opened only after the proof has passed."
    assert during.lab["retest"]["blocked_reason"] == during.lab["download"]["blocked_reason"] == PROOF_RUNNING
    assert during.lab["retest"]["running"] is False and during.lab["view"] == "results"
    subline = "".join(p["v"] for p in during.lab["subline"])
    assert "Tests are running" not in subline and "Run finished" in subline
    # Evidence Lab keeps showing the first results while the proof reruns the tests
    assert [r["result"]["run_id"] for r in during.lab["rows"]] == [r["result"]["run_id"] for r in fix_flow.first["rows"]]
    assert all(r["after"] is None and r["result_status"] is None for r in during.lab["rows"])
    assert during.plan["running"] is True and during.plan["can_run_all"] is False
    assert not any(t["can_run"] for t in during.plan["tests"])
    speed = next(t for t in during.plan["tests"] if t["kind"] == "speed_size")
    assert speed["can_remove"] is False and speed["result"]["label"] == "Measured"


def test_proof_runs_are_reviewed_runs_of_their_own_phase_with_the_code_they_ran_on(fix_flow):
    change = code_fix(fix_flow.ready)["change"]
    kinds = {i: k for k, i in fix_flow.plan.item.items()}
    with fix_flow.lab.db() as db:
        proof = db.query(ProofRow).filter_by(plan_id=fix_flow.plan.id).one()
        runs = db.query(TestRunRow).filter_by(plan_id=fix_flow.plan.id, phase="proof").all()
        assert sorted(kinds[r.plan_item_id] for r in runs) == sorted(kinds.values()) and len(runs) == 6
        assert [e["item_id"] for e in proof.items] == [r["item_id"] for r in fix_flow.first["rows"]]
        for run in runs:
            software = kinds[run.plan_item_id] in SOFTWARE
            assert run.retest_id == proof.id and run.spec_hash == next(e["spec_hash"] for e in proof.items if e["item_id"] == run.plan_item_id)
            assert (run.component_name, run.component_version, run.baseline_version) == (("acme-sign", "1.4.3", "1.4.2") if software else (None, None, None))
            review = db.query(ReviewRow).filter_by(run_id=run.id).one()
            assert review.reviewer == "isogeny.rule-reviewer/1" and review.spec_hash_ok is True
            code = db.query(RunCodeRow).filter_by(run_id=run.id).one_or_none()
            if not software:
                assert code is None  # a server test runs no code of ours
                continue
            assert (code.source, code.repository, code.branch, code.commit) == ("repository", "acme-sign", "fix/ecdsa-range-check", change["head_commit"])
            assert (code.component_name, code.component_version, code.change_id, code.pull_request_number) == ("acme-sign", "1.4.3", change["id"], None)
            assert code.file_sha256 == hashlib.sha256(NEW_FILE).hexdigest() == change["built"]["sha256"]
        speed = next(r for r in runs if kinds[r.plan_item_id] == "speed_size")
        assert speed.raw["subjects"] == {"old": "acme-sign-1.4.2", "new": "acme-sign-1.4.3", "control": "control-slow:acme-sign-1.4.3"}
        # the first runs were made before the code was connected: on the bundled component
        for run in db.query(TestRunRow).filter_by(plan_id=fix_flow.plan.id, phase="first").all():
            code = db.query(RunCodeRow).filter_by(run_id=run.id).one_or_none()
            if kinds[run.plan_item_id] in SOFTWARE:
                assert (code.source, code.component_version, code.repository, code.branch, code.commit, code.change_id) == ("bundled", "1.4.2", None, None, None, None)
                assert code.file_sha256 == hashlib.sha256(OLD_FILE).hexdigest()
            else:
                assert code is None


def test_the_proof_is_offered_and_its_fingerprint_can_be_worked_out_again(fix_flow):
    lab, code = fix_flow.lab, code_fix(fix_flow.ready)
    proof = code["proof"]
    assert code["status"] == "ready" and (proof["state"], proof["finished"], proof["total"]) == ("passed", 6, 6)
    review = proof["review"]
    assert review["believed"] is True and review["offered"] is True and review["problem"] is None
    assert review["checks"] == {"code_is_ours": True, "changed_code_passed": True, "controls_behaved": True, "server_unchanged": True}
    assert review["counts"] == {"tests": 6, "code": 3, "code_ok": 3, "server": 3, "server_ok": 3}
    rows = {r["kind"]: r for r in proof["tests"]}
    assert {k: (r["target"], r["check"]["group"], r["check"]["ok"], r["check"]["reason"]) for k, r in rows.items()} == {
        "tls_versions": ("server", "server", True, "same_as_before"), "certificate": ("server", "server", True, "same_as_before"),
        "official_vectors": ("software", "code", True, "passed"), "bad_signatures": ("software", "code", True, "passed"),
        "speed_size": ("software", "code", True, "no_slowdown"), "pq_readiness": ("server", "server", True, "same_as_before")}
    assert [(rows[k]["first"]["code"], rows[k]["proof"]["code"]) for k in ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")] == [
        ("failed", "failed"), ("passed", "passed"), ("failed", "passed"), ("failed", "passed"), ("measured", "no_slowdown")]
    # the post-quantum check comes out the same both times, whatever this machine's OpenSSL can do
    assert (rows["pq_readiness"]["first"]["code"], rows["pq_readiness"]["first"]["reason_code"]) == \
           (rows["pq_readiness"]["proof"]["code"], rows["pq_readiness"]["proof"]["reason_code"])
    assert all(r["job"] is None for r in proof["tests"])
    assert code["actions"]["open_pull_request"] is None and code["actions"]["merge"] == "Open a pull request first."
    assert code["actions"]["run_proof_again"] == "The proof has passed. It can be run again only after it failed or was interrupted."
    # the fingerprint is the SHA-256 of the proof record, rebuilt here from the stored rows
    with lab.db() as db:
        row, change = db.query(ProofRow).filter_by(id=proof["id"]).one(), db.get(ChangeRow, code["change"]["id"])
        stored = db.query(ProofReviewRow).filter_by(proof_id=proof["id"]).one()
        record = lab._proof_record(row, change, lab._proof_tests(db, row))
        assert stored.record_sha256 == review["record_sha256"] == sha256_hex(record) and stored.offered is True
        assert stored.reviewer == "isogeny.rule-reviewer/1" and stored.detail["schema"] == "isogeny.proof-review/1"
        assert record["schema"] == "isogeny.proof/1" and record["proposed_by"] == "isogeny.rule-engine/1"
        assert record["built"]["matches"] == {"name": "acme-sign", "version": "1.4.3"} and len(record["tests"]) == 6
        assert all(len(t["first"]["run_sha256"]) == len(t["proof"]["run_sha256"]) == 64 for t in record["tests"])
        assert lab.reviewer.review_proof(record)["offered"] is True
    # Evidence Lab still shows the first results: a proof is not a retest
    assert fix_flow.lab_after_proof["view"] == "results" and fix_flow.lab_after_proof["retest"]["can_start"] is True
    assert [r["result"]["run_id"] for r in fix_flow.lab_after_proof["rows"]] == [r["result"]["run_id"] for r in fix_flow.first["rows"]]


def test_pull_request_approvals_and_the_merge(fix_flow):
    opened, one, two, merged = (code_fix(s) for s in (fix_flow.opened, fix_flow.one, fix_flow.two, fix_flow.merged))
    assert [f["status"] for f in (opened, one, two, merged)] == ["waiting", "waiting", "ready_to_merge", "merged"]
    request = opened["pull_request"]
    assert (request["number"], request["title"], request["reviewers"]) == (1, "Reject signatures whose r or s is out of range", ["you", "a"])
    assert request["proof_id"] == opened["proof"]["id"] and request["opened_at"]
    assert request["approvals"] == [{"reviewer": "you", "name": "You", "approved_at": None}, {"reviewer": "a", "name": "Demo reviewer A", "approved_at": None}]
    assert fix_flow.early_merge == fix_flow.still_early_merge == "Every picked reviewer must approve before the merge."
    assert [bool(a["approved_at"]) for a in one["pull_request"]["approvals"]] == [True, False]
    assert all(a["approved_at"] for a in two["pull_request"]["approvals"]) and two["actions"]["merge"] is None
    assert opened["actions"]["download_patch"] is None and opened["actions"]["retest_now"] == "Retest now is available after the merge."
    assert two["merge"] is None and merged["merge"]["merged_at"] and merged["actions"]["retest_now"] is None
    assert merged["actions"]["merge"] == "This pull request is already merged."
    # the merge: one commit with two parents on main, which then holds our registered 1.4.3 byte for byte
    repo, change = repo_of(fix_flow.lab, merged), merged["change"]
    commit = repo.read_commit(merged["merge"]["merge_commit"])
    assert commit.parents == (change["base_commit"], change["head_commit"]) and repo.branch("main") == commit.sha
    assert commit.message == "Merge pull request #1: Reject signatures whose r or s is out of range"
    assert (commit.author.name, commit.author.email) == ("Evidence Lab user", "user@example.invalid")
    assert repo.files(commit.sha) == {"acme_sign.py": NEW_FILE}
    assert repo.branch("fix/ecdsa-range-check") == change["head_commit"]
    with fix_flow.lab.db() as db:
        row = db.query(PullRequestRow).filter_by(plan_id=fix_flow.plan.id).one()
        approvals = db.query(ApprovalRow).filter_by(pull_request_id=row.id).order_by(ApprovalRow.id).all()
        assert [(a.reviewer, a.name) for a in approvals] == [("you", "You"), ("a", "Demo reviewer A")]
        assert db.query(MergeRow).filter_by(pull_request_id=row.id).one().merge_commit == commit.sha
        assert approvals[0].approved_at <= approvals[1].approved_at <= db.query(MergeRow).one().merged_at


def test_the_patch_is_the_change_and_the_same_bytes_every_time(fix_flow):
    name, data = fix_flow.patch
    assert name == "acme-sign-pull-request-1.patch" and fix_flow.lab.patch_file(fix_flow.plan.id, FIX) == (name, data)
    patch = data.decode()
    assert patch.startswith(f"From {code_fix(fix_flow.merged)['change']['head_commit']} ")
    assert "Subject: [PATCH] Reject signatures whose r or s is out of range" in patch and "From a fix template: ecdsa-range-check" in patch
    assert " 1 file changed, 3 insertions(+), 1 deletion(-)" in patch
    added = [line for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
    removed = [line for line in patch.splitlines() if line.startswith("-") and not line.startswith(("---", "-- "))]
    assert added == ['+VERSION = "1.4.3"', "+    if not (1 <= r < N and 1 <= s < N):", '+        return {"valid": False}']
    assert removed == ['-VERSION = "1.4.2"']


def test_retest_now_is_the_same_retest_and_its_runs_ran_on_the_merged_fix(fix_flow):
    lab, final = fix_flow.lab, fix_flow.final_lab
    assert fix_flow.retest_started["view"] == "before_after" and fix_flow.retest_started["retest"]["running"] is True
    assert final["view"] == "before_after" and final["columns"]["before"] == "Before: acme-sign 1.4.2" and final["columns"]["after"] == "After: acme-sign 1.4.3"
    kinds = ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")
    assert [result_of(final, k, "after")["label"] for k in kinds] == ["Failed", "Passed", "Passed", "Passed", "No slowdown beyond measured noise"]
    assert [result_of(final, k)["label"] for k in kinds] == ["Failed", "Passed", "Failed", "Failed", "Measured"]
    assert result_of(final, "pq_readiness")["label"] == result_of(final, "pq_readiness", "after")["label"]
    merged = code_fix(fix_flow.final)
    with lab.db() as db:
        retest = db.query(RetestRow).filter_by(plan_id=fix_flow.plan.id).one()
        assert (retest.baseline_version, retest.version) == ("1.4.2", "1.4.3")
        runs = db.query(TestRunRow).filter_by(plan_id=fix_flow.plan.id, phase="retest").all()
        assert len(runs) == 6 and all(r.retest_id == retest.id for r in runs)
        codes = [db.query(RunCodeRow).filter_by(run_id=r.id).one() for r in runs if r.component_name]
        assert len(codes) == 3
        for code in codes:  # "the merged fix": main at the merge commit, from pull request #1
            assert (code.source, code.repository, code.branch, code.commit) == ("repository", "acme-sign", "main", merged["merge"]["merge_commit"])
            assert (code.component_version, code.change_id, code.pull_request_number) == ("1.4.3", merged["change"]["id"], 1)
            assert code.file_sha256 == hashlib.sha256(NEW_FILE).hexdigest()
    # the merged fix stays listed, still answering the failures it came from; the server finding is still open
    assert [(f["id"], f["status"]) for f in fix_flow.final] == [(FIX, "merged"), ("fix-tls-versions", "text_only")]
    assert merged["answers"] == code_fix(fix_flow.before)["answers"]
    assert [(a["kind"], a["phase"]) for a in fix_flow.final[1]["answers"]] == [("tls_versions", "first"), ("tls_versions", "retest")]
    assert fix_flow.export["fingerprint"]  # Download evidence still works with the new records in place


def test_a_second_import_gets_its_own_fresh_copy_and_the_same_results(fix_flow):
    lab, first, second = fix_flow.lab, code_fix(fix_flow.final), fix_flow.second
    assert fix_flow.again.id != fix_flow.plan.id
    assert second["connection"]["folder"] == f"repos/plan-{fix_flow.again.id}/acme-sign.git" != first["connection"]["folder"]
    # the first copy was merged; the second starts from the bundled commit again
    assert second["connection"]["base_commit"] == BUNDLED.branch("main") == first["connection"]["base_commit"]
    assert repo_of(lab, first).branch("main") == first["merge"]["merge_commit"]
    assert repo_of(lab, second).branch("main") == second["connection"]["base_commit"]
    assert repo_of(lab, second).files(second["change"]["head_commit"]) == {"acme_sign.py": NEW_FILE}
    assert second["status"] == "ready" and second["proof"]["review"]["offered"] is True and second["pull_request"] is None
    assert second["change"]["files"] == first["change"]["files"] and second["change"]["built"] == first["change"]["built"]
    same = {r["kind"]: (r["first"]["code"], r["proof"]["code"], r["check"]) for r in first["proof"]["tests"]}
    again = {r["kind"]: (r["first"]["code"], r["proof"]["code"], r["check"]) for r in second["proof"]["tests"]}
    # the report-only test has no pass or fail: in a proof it only has to run
    assert again.pop("mldsa_compare") == ("measured", "measured", {"group": "code", "ok": True, "reason": "ran"})
    assert again == {k: same[k] for k in ("tls_versions", "certificate", "bad_signatures")}
    assert second["proof"]["review"]["counts"] == {"tests": 4, "code": 2, "code_ok": 2, "server": 2, "server_ok": 2}
    assert (fix_flow.second_request["number"], fix_flow.second_request["reviewers"]) == (1, ["b"])  # numbered for each file
    assert listing(demo_repo.bundled("acme-sign")) == fix_flow.bundled_before  # the bundled repository is never written to


FIX_TABLES = {"code_connections": "repository", "changes": "title", "proofs": "version", "proof_reviews": "offered",
              "pull_requests": "title", "approvals": "name", "merges": "merge_commit", "run_code": "source"}


def test_every_append_only_table_is_covered_by_a_test():
    assert set(RUN_TABLES) | set(FIX_TABLES) == set(APPEND_ONLY_TABLES) and not set(RUN_TABLES) & set(FIX_TABLES)


@pytest.mark.parametrize("table", FIX_TABLES)
def test_raw_sql_cannot_change_or_delete_the_records_of_a_fix(fix_flow, table):
    with fix_flow.lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {FIX_TABLES[table]} = 1", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


# ---------------------------------------------------------------- refusals

def test_connect_is_refused_until_every_test_has_a_result_and_nothing_runs(lab):
    plan = small_plan(lab, without=("speed_size",))
    assert lab.fix_states(plan.id) == []
    assert refusal(lambda: lab.connect_code(plan.id)) == RUN_FIRST
    lab.run_test(plan.id, plan.item["official_vectors"])
    assert refusal(lambda: lab.connect_code(plan.id)) == "Tests are still running. Wait until they have finished."
    lab.wait_until_idle(plan.id, 120)
    (code,) = lab.fix_states(plan.id)  # one failed test is enough for the fix to be listed, not for connecting
    assert (code["id"], code["status"], [a["kind"] for a in code["answers"]]) == (FIX, "not_connected", ["official_vectors"])
    assert code["actions"]["connect"] == code["rerun_blocked"] == RUN_FIRST == refusal(lambda: lab.connect_code(plan.id))
    lab.remove_test(plan.id, plan.item["official_vectors"])  # (out of the plan again, to keep this test short)
    for kind in ("tls_versions", "certificate"):
        lab.run_test(plan.id, plan.item[kind])
        lab.wait_until_idle(plan.id, 120)
    assert refusal(lambda: lab.connect_code(plan.id)) == RUN_FIRST  # one test in the plan still has no result
    with lab.db() as db:
        assert db.query(CodeConnectionRow).count() == db.query(ChangeRow).count() == db.query(ProofRow).count() == 0
    assert not (lab.settings.data_dir / "repos").exists()  # nothing was copied
    lab.run_test(plan.id, plan.item["bad_signatures"])
    lab.wait_until_idle(plan.id, 120)
    assert code_fix(lab.fix_states(plan.id))["actions"]["connect"] is None
    connected = code_fix(lab.connect_code(plan.id))
    assert connected["status"] in ("proving", "ready") and connected["proof"]["total"] == 3  # it started by itself
    assert refusal(lambda: lab.connect_code(plan.id)) == "The demo code is already connected for this file."
    lab.wait_until_idle(plan.id, 120)
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"


def test_each_step_is_refused_before_its_time(lab):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    for fix_id in ("fix-nothing", "fix-certificate", "FIX", "../x", ""):
        assert refusal(lambda: lab.open_pull_request(plan.id, fix_id, ["you"]), NotFound) == "That fix does not exist."
        assert refusal(lambda: lab.patch_file(plan.id, fix_id), NotFound) == "That fix does not exist."
    for call in (lambda: lab.run_proof_again(plan.id, "fix-tls-versions"), lambda: lab.merge(plan.id, "fix-tls-versions"),
                 lambda: lab.approve(plan.id, "fix-tls-versions", "you"), lambda: lab.retest_now(plan.id, "fix-tls-versions")):
        assert refusal(call) == "This fix is a text-only suggestion: there is no code change to act on."
    with pytest.raises(NotFound):
        lab.connect_code(plan.id + 100)
    # before the code is connected
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "Connect the demo code first."
    assert refusal(lambda: lab.run_proof_again(plan.id, FIX)) == "Connect the demo code first."
    assert refusal(lambda: lab.approve(plan.id, FIX, "you")) == refusal(lambda: lab.merge(plan.id, FIX)) == "Open a pull request first."
    assert refusal(lambda: lab.patch_file(plan.id, FIX)) == "The patch can be downloaded once a pull request is open."
    assert refusal(lambda: lab.retest_now(plan.id, FIX)) == "Retest now is available after the merge."
    lab.connect_code(plan.id)
    lab.wait_until_idle(plan.id, 120)
    # the proof has passed: no second proof, and still nothing to approve or merge
    assert refusal(lambda: lab.run_proof_again(plan.id, FIX)) == "The proof has passed. It can be run again only after it failed or was interrupted."
    assert refusal(lambda: lab.approve(plan.id, FIX, "you")) == refusal(lambda: lab.merge(plan.id, FIX)) == "Open a pull request first."
    for reviewers in ([], ["you", "you"], ["you", "c"], ["everyone"], "you", None, [["you"]], [1]):
        assert refusal(lambda: lab.open_pull_request(plan.id, FIX, reviewers), BadRequest) == "Pick one or more reviewers from the list, each of them once."
    with lab.db() as db:
        assert db.query(PullRequestRow).count() == 0
    assert code_fix(lab.open_pull_request(plan.id, FIX, ["a"]))["status"] == "waiting"
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "A pull request is already open for this change."
    assert refusal(lambda: lab.run_proof_again(plan.id, FIX)) == "A pull request is already open for this change, so its proof stays as it is."
    # approvals: only someone who was picked, and only once
    assert refusal(lambda: lab.approve(plan.id, FIX, "you")) == refusal(lambda: lab.approve(plan.id, FIX, "b")) == "That reviewer was not picked for this pull request."
    for reviewer in ("c", "You", "", None, ["a"]):
        assert refusal(lambda: lab.approve(plan.id, FIX, reviewer), BadRequest) == "That reviewer is not in the list."
    assert refusal(lambda: lab.merge(plan.id, FIX)) == "Every picked reviewer must approve before the merge."
    assert refusal(lambda: lab.retest_now(plan.id, FIX)) == "Retest now is available after the merge."
    assert code_fix(lab.approve(plan.id, FIX, "a"))["status"] == "ready_to_merge"
    assert refusal(lambda: lab.approve(plan.id, FIX, "a")) == "That reviewer has already approved."
    assert code_fix(lab.merge(plan.id, FIX))["status"] == "merged"
    # after the merge: no second merge, no more approvals
    assert refusal(lambda: lab.merge(plan.id, FIX)) == refusal(lambda: lab.approve(plan.id, FIX, "a")) == "This pull request is already merged."
    with lab.db() as db:
        assert (db.query(PullRequestRow).count(), db.query(ApprovalRow).count(), db.query(MergeRow).count()) == (1, 1, 1)
        assert db.query(RetestRow).count() == 0  # the merge started nothing by itself
    main = repo_of(lab, code_fix(lab.fix_states(plan.id))).branch("main")
    assert lab.retest_now(plan.id, FIX)["view"] == "before_after"
    lab.wait_until_idle(plan.id, 120)
    assert repo_of(lab, code_fix(lab.fix_states(plan.id))).branch("main") == main


def test_a_failed_proof_is_not_offered_and_can_be_run_again(lab):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    address = plan.imp["addresses"][0]["address"]
    lab.confirm_address(plan.imp["id"], address, False)  # the server tests can't run now, so they do not come out as before
    lab.connect_code(plan.id)
    lab.wait_until_idle(plan.id, 120)
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "failed" and code["proof"]["state"] == "failed" and code["proof"]["finished"] == 3
    review = code["proof"]["review"]
    assert review["believed"] is True and review["offered"] is False and review["problem"] is None
    assert review["checks"] == {"code_is_ours": True, "changed_code_passed": True, "controls_behaved": True, "server_unchanged": False}
    rows = {r["kind"]: r for r in code["proof"]["tests"]}
    assert rows["tls_versions"]["check"] == rows["certificate"]["check"] == {"group": "server", "ok": False, "reason": "changed"}
    assert (rows["tls_versions"]["proof"]["code"], rows["tls_versions"]["proof"]["reason_code"]) == ("couldnt_run", "address_not_confirmed")
    assert rows["bad_signatures"]["check"] == {"group": "code", "ok": True, "reason": "passed"}
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "A pull request can be opened only after the proof has passed."
    assert code["actions"]["run_proof_again"] is None and code["actions"]["open_pull_request"] is not None
    # Evidence Lab is untouched by the failed proof
    assert [r["result"]["label"] for r in lab.lab_view(plan.id)["rows"]] == ["Failed", "Passed", "Failed"]
    lab.confirm_address(plan.imp["id"], address, True)
    again = code_fix(lab.run_proof_again(plan.id, FIX))
    assert again["status"] == "proving" and again["proofs"] == 2 and again["proof"]["id"] != code["proof"]["id"]
    lab.wait_until_idle(plan.id, 120)
    done = code_fix(lab.fix_states(plan.id))
    assert done["status"] == "ready" and done["proof"]["review"]["offered"] is True
    with lab.db() as db:  # the failed proof and its runs are still on record
        assert db.query(ProofRow).count() == db.query(ProofReviewRow).count() == 2
        assert db.query(TestRunRow).filter_by(phase="proof").count() == 6
        assert [r.offered for r in db.query(ProofReviewRow).order_by(ProofReviewRow.id)] == [False, True]


def test_nothing_runs_when_the_changed_code_is_not_a_registered_component(lab, monkeypatch):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    propose, seen = lab.engine.propose_change, []

    def not_ours(request):  # the template's output with one more line: no longer byte for byte our 1.4.3
        seen.append(request)
        reply = propose(request)
        reply["files"]["acme_sign.py"] += "NOT_OURS = 'marker-7f3a'\n"
        return reply

    submitted = []
    submit = lab.jobs.submit
    monkeypatch.setattr(lab.engine, "propose_change", not_ours)
    monkeypatch.setattr(lab.jobs, "submit", lambda *a, **k: submitted.append(a) or submit(*a, **k))
    code = code_fix(lab.connect_code(plan.id))
    assert code["status"] == "failed" and code["proof"] is None and code["proofs"] == 0
    assert code["change"]["built"]["matches"] is None and code["change"]["built"]["sha256"] != hashlib.sha256(NEW_FILE).hexdigest()
    assert submitted == [] and not lab.jobs.busy(plan.id)  # no job was queued: nothing ran
    with lab.db() as db:
        assert db.query(ProofRow).count() == 0 and db.query(TestRunRow).filter_by(phase="proof").count() == 0
    assert refusal(lambda: lab.run_proof_again(plan.id, FIX)) == code["actions"]["run_proof_again"] == \
           "The changed code is not one of our demo components, so nothing can be run."
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "A pull request can be opened only after the proof has passed."
    assert submitted == []
    # the changed code exists only as data inside the repository copy: no plain file holds it anywhere in the data folder
    files = [p for p in lab.settings.data_dir.rglob("*") if p.is_file()]
    assert files and not any(b"marker-7f3a" in p.read_bytes() for p in files)
    assert repo_of(lab, code).files(code["change"]["head_commit"])["acme_sign.py"].endswith(b"NOT_OURS = 'marker-7f3a'\n")
    # what the engine was given, once: the component, every failed first result with its review detail, and the code as text
    (request,) = seen
    assert request["component"] == {"name": "acme-sign", "version": "1.4.2"} and request["files"] == {"acme_sign.py": OLD_FILE.decode()}
    assert [(r["kind"], r["reason_code"]) for r in request["failed"]] == [("tls_versions", None), ("bad_signatures", None)]
    assert request["failed"][0]["detail"]["accepted_outside_claim"] == ["TLS 1.2"]
    assert sorted(w["id"] for w in request["failed"][1]["detail"]["wrong"]) == ["r0-s0", "s-plus-n"]
    assert [r["kind"] for r in code["change"]["source"]["runs"]] == ["bad_signatures"]  # it answers only the signing failure


def test_an_interrupted_proof_counts_as_failed_and_can_be_run_again(lab, monkeypatch):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    with monkeypatch.context() as patch:  # as if the app was closed before the proof's tests ran: they leave nothing
        patch.setattr(lab, "_submit", lambda *a, **k: None)
        lab.connect_code(plan.id)
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "failed" and (code["proof"]["state"], code["proof"]["finished"], code["proof"]["review"]) == ("interrupted", 0, None)
    assert all(r["proof"] is None and r["job"] is None and r["check"] is None for r in code["proof"]["tests"])
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "A pull request can be opened only after the proof has passed."
    assert code["actions"]["run_proof_again"] is None
    lab.run_proof_again(plan.id, FIX)
    lab.wait_until_idle(plan.id, 120)
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"


def test_a_plan_that_changed_after_the_proof_needs_a_new_proof(lab):
    plan = small_plan(lab)
    assert proved(lab, plan)["status"] == "ready"
    order = [t["id"] for t in lab.plan_view(plan.id)["tests"]]
    lab.reorder(plan.id, order[::-1])
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"  # the same tests in another order: still covered
    added = next(t["id"] for t in lab.add_test(plan.id, "mldsa_compare")["tests"] if t["kind"] == "mldsa_compare")  # a test the proof never ran
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "failed" and code["proof"]["state"] == "passed" and code["proof"]["covers_plan"] is False
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "The test plan has changed since the proof ran. Run the proof again first."
    assert refusal(lambda: lab.run_proof_again(plan.id, FIX)) == code["actions"]["run_proof_again"] == RUN_FIRST
    lab.run_test(plan.id, added)
    lab.wait_until_idle(plan.id, 120)
    lab.run_proof_again(plan.id, FIX)
    lab.wait_until_idle(plan.id, 120)
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "ready" and code["proof"]["total"] == 4 and code["proof"]["covers_plan"] is True
    # once a pull request is open it stands on the proof it was opened with, whatever happens to the plan later
    lab.open_pull_request(plan.id, FIX, ["you"])
    lab.remove_test(plan.id, plan.item["certificate"])
    assert code_fix(lab.fix_states(plan.id))["status"] == "waiting"


# ---------------------------------------------------------------- the read gate, against a tampered database

def tamper(lab, *statements):
    with lab.db() as db:
        for table in APPEND_ONLY_TABLES:
            db.execute(text(f"DROP TRIGGER IF EXISTS {table}_no_update"))
        for statement in statements:
            assert db.execute(text(statement)).rowcount >= 1
        db.commit()


def test_a_changed_proof_review_is_not_believed(lab):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    address = plan.imp["addresses"][0]["address"]
    lab.confirm_address(plan.imp["id"], address, False)
    lab.connect_code(plan.id)
    lab.wait_until_idle(plan.id, 120)
    assert code_fix(lab.fix_states(plan.id))["proof"]["review"]["offered"] is False  # an honest failed proof
    # someone edits the database so that the stored answer says "offered"
    tamper(lab, "UPDATE proof_reviews SET offered = 1")
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "failed" and code["proof"]["state"] == "failed"
    assert code["proof"]["review"] == {"reviewed_at": code["proof"]["review"]["reviewed_at"], "believed": False, "offered": False,
                                       "problem": PROOF_CHANGED, "record_sha256": None, "checks": None, "counts": None, "tests": []}
    assert all(r["check"] is None for r in code["proof"]["tests"])  # nothing of the unverified answer is passed on
    assert refusal(lambda: lab.open_pull_request(plan.id, FIX, ["you"])) == "A pull request can be opened only after the proof has passed."
    # ... and makes the details agree with it: still not what the records give
    tamper(lab, """UPDATE proof_reviews SET detail = json_set(detail, '$.checks.server_unchanged', json('true'))""")
    assert code_fix(lab.fix_states(plan.id))["proof"]["review"]["believed"] is False
    tamper(lab, """UPDATE proof_reviews SET offered = 0, detail = json_set(detail, '$.checks.server_unchanged', json('false'))""")
    restored = code_fix(lab.fix_states(plan.id))["proof"]["review"]  # put back exactly: believed again, and still not offered
    assert restored["believed"] is True and restored["offered"] is False
    tamper(lab, "UPDATE proof_reviews SET record_sha256 = replace(record_sha256, substr(record_sha256, 1, 1), 'g')")
    assert code_fix(lab.fix_states(plan.id))["proof"]["review"]["problem"] == PROOF_CHANGED


def test_changing_what_a_passed_proof_stands_on_is_caught(lab):
    plan = small_plan(lab)
    ready = proved(lab, plan)
    assert ready["status"] == "ready"
    run_id = next(r["proof"]["run_id"] for r in ready["proof"]["tests"] if r["kind"] == "bad_signatures")

    def not_believed():
        code = code_fix(lab.fix_states(plan.id))
        return (code["status"], code["proof"]["state"], code["proof"]["review"]["believed"], code["proof"]["review"]["problem"]) == \
               ("failed", "failed", False, PROOF_CHANGED)

    # a proof run's stored answers
    tamper(lab, f"""UPDATE test_runs SET raw = json_set(raw, '$.subject.answers."r0-s0"', 'accept') WHERE id = {run_id}""")
    assert not_believed()
    tamper(lab, f"""UPDATE test_runs SET raw = json_set(raw, '$.subject.answers."r0-s0"', 'reject') WHERE id = {run_id}""")
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"
    # a proof run's stored review
    tamper(lab, f"UPDATE reviews SET control_outcome = 'errored' WHERE run_id = {run_id}")
    assert not_believed()
    tamper(lab, f"UPDATE reviews SET control_outcome = 'as_expected' WHERE run_id = {run_id}")
    # the first result it was compared with
    first_id = next(r["first"]["run_id"] for r in ready["proof"]["tests"] if r["kind"] == "tls_versions")
    tamper(lab, f"UPDATE reviews SET code = 'passed' WHERE run_id = {first_id}")
    assert not_believed()
    tamper(lab, f"UPDATE reviews SET code = 'failed' WHERE run_id = {first_id}")
    # the stored change and its code check
    tamper(lab, """UPDATE changes SET built = json_set(built, '$.sha256', 'f00d')""")
    assert not_believed()
    tamper(lab, f"""UPDATE changes SET built = json_set(built, '$.sha256', '{ready["change"]["built"]["sha256"]}')""")
    tamper(lab, "UPDATE changes SET head_commit = base_commit")
    assert not_believed()
    tamper(lab, f"""UPDATE changes SET head_commit = '{ready["change"]["head_commit"]}'""")
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"  # everything put back exactly: believed again
    # with a pull request open, a proof that is no longer believed stops the approvals and the merge
    lab.open_pull_request(plan.id, FIX, ["you"])
    tamper(lab, "UPDATE proofs SET version = '1.4.2'")
    code = code_fix(lab.fix_states(plan.id))
    assert code["status"] == "failed" and code["actions"]["merge"] == PROOF_CHANGED
    assert refusal(lambda: lab.approve(plan.id, FIX, "you")) == refusal(lambda: lab.merge(plan.id, FIX)) == PROOF_CHANGED
    tamper(lab, "UPDATE proofs SET version = '1.4.3'")
    lab.approve(plan.id, FIX, "you")
    assert code_fix(lab.merge(plan.id, FIX))["status"] == "merged"


def test_merge_is_refused_when_the_repository_moved(lab):
    plan = small_plan(lab)
    ready = proved(lab, plan)
    lab.open_pull_request(plan.id, FIX, ["you"])
    lab.approve(plan.id, FIX, "you")
    repo = repo_of(lab, ready)
    base = ready["change"]["base_commit"]
    moved = repo.commit("main", {"acme_sign.py": OLD_FILE + b"# edited\n"}, "someone else's commit", demo_repo.AUTHOR, 1794300001, base)
    assert refusal(lambda: lab.merge(plan.id, FIX)) == "The repository has changed since this change was proved. Nothing was merged."
    assert repo.branch("main") == moved and code_fix(lab.fix_states(plan.id))["status"] == "ready_to_merge"
    with lab.db() as db:
        assert db.query(MergeRow).count() == 0


# ---------------------------------------------------------------- which code a run ran on, and other edges

def run_codes(lab, phase):
    with lab.db() as db:
        rows = db.query(RunCodeRow, TestRunRow).join(TestRunRow, TestRunRow.id == RunCodeRow.run_id).filter(TestRunRow.phase == phase).order_by(TestRunRow.id).all()
        return [(code.source, code.component_version, code.branch, code.commit, code.change_id, code.pull_request_number) for code, _ in rows]


def test_first_runs_and_retests_say_which_code_they_ran_on(lab):
    plan = small_plan(lab)
    ready = proved(lab, plan)
    base, change_id = ready["connection"]["base_commit"], ready["change"]["id"]
    assert run_codes(lab, "first") == [("bundled", "1.4.2", None, None, None, None)]  # run before the code was connected
    lab.run_test(plan.id, plan.item["bad_signatures"])  # now the repository's main branch holds exactly this code
    lab.wait_until_idle(plan.id, 120)
    assert run_codes(lab, "first")[-1] == ("repository", "1.4.2", "main", base, None, None)
    lab.start_retest(plan.id, "1.4.3")  # before the merge: main does not hold 1.4.3 yet, so this is the bundled version
    lab.wait_until_idle(plan.id, 120)
    assert run_codes(lab, "retest") == [("bundled", "1.4.3", None, None, None, None)]
    lab.open_pull_request(plan.id, FIX, ["you"])
    lab.approve(plan.id, FIX, "you")
    merge_commit = code_fix(lab.merge(plan.id, FIX))["merge"]["merge_commit"]
    lab.retest_now(plan.id, FIX)
    lab.wait_until_idle(plan.id, 120)
    assert run_codes(lab, "retest")[-1] == ("repository", "1.4.3", "main", merge_commit, change_id, 1)
    lab.run_test(plan.id, plan.item["bad_signatures"])  # 1.4.2 again: no longer what main holds
    lab.wait_until_idle(plan.id, 120)
    assert run_codes(lab, "first")[-1] == ("bundled", "1.4.2", None, None, None, None)
    with lab.db() as db:  # the fingerprinted run record itself did not grow
        run = db.query(TestRunRow).order_by(TestRunRow.id.desc()).first()
        assert set(run_record(run)) == {"schema", "spec_hash", "phase", "component", "baseline_version", "mode", "started_at",
                                        "finished_at", "duration_ms", "raw", "logs", "runner"}
    # the merged fix answers the failed result it came from and the failed first result that is shown now (the same
    # test, run again); the retest that passed needs no fix
    code = code_fix(lab.fix_states(plan.id))
    shown_now = result_of(lab.lab_view(plan.id), "bad_signatures")["run_id"]
    assert code["status"] == "merged" and [(a["kind"], a["phase"]) for a in code["answers"]] == [("bad_signatures", "first")] * 2
    assert [a["run_id"] for a in code["answers"]] == [code["change"]["source"]["runs"][0]["run_id"], shown_now]


def test_the_proof_is_reviewed_once_when_its_jobs_finish_together_and_never_while_closing(lab, monkeypatch):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    finished = lab._proof_run_finished
    with monkeypatch.context() as patch:  # hold the proof's review back until every run is stored
        patch.setattr(lab, "_proof_run_finished", lambda proof_id: None)
        lab.connect_code(plan.id)
        lab.wait_until_idle(plan.id, 120)
    code = code_fix(lab.fix_states(plan.id))
    assert (code["proof"]["state"], code["proof"]["finished"]) == ("interrupted", 3)
    lab._stopping = True  # the app is closing: nothing is written
    finished(code["proof"]["id"])
    with lab.db() as db:
        assert db.query(ProofReviewRow).count() == 0
    lab._stopping = False
    threads = [threading.Thread(target=finished, args=(code["proof"]["id"],)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    with lab.db() as db:
        assert db.query(ProofReviewRow).count() == 1
    assert code_fix(lab.fix_states(plan.id))["status"] == "ready"


def test_a_folder_left_by_an_earlier_database_is_neither_reused_nor_removed(lab):
    plan = small_plan(lab)
    leftover = lab.settings.data_dir / "repos" / f"plan-{plan.id}" / "acme-sign.git"
    leftover.mkdir(parents=True)
    (leftover / "HEAD").write_text("ref: refs/heads/somewhere-else\n")
    ready = proved(lab, plan)
    assert ready["connection"]["folder"] == f"repos/plan-{plan.id}-2/acme-sign.git" and ready["status"] == "ready"
    assert listing(leftover) == {"HEAD": b"ref: refs/heads/somewhere-else\n"}
    for folder in ("../elsewhere.git", "repos", "repos/../../x", str(demo_repo.bundled("acme-sign"))):
        with pytest.raises(GitRepoError):  # only a folder inside the app's own repos folder is ever opened
            lab._repo(folder)


def test_connect_needs_the_bundled_repository_to_be_there(lab, monkeypatch, tmp_path):
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    assert [f["id"] for f in lab.fix_states(plan.id)] == [FIX, "fix-tls-versions"]
    with monkeypatch.context() as patch:  # we ship no repository for this component
        patch.setattr(demo_repo, "bundled", lambda name: None)
        assert [(f["id"], f["kind"]) for f in lab.fix_states(plan.id)] == [("fix-tls-versions", "text"), ("fix-bad-signatures", "text")]
        assert refusal(lambda: lab.connect_code(plan.id)) == "There is no demo repository for this signing component."
    with monkeypatch.context() as patch:  # ... or it is not on the disk
        patch.setattr(demo_repo, "bundled", lambda name: tmp_path / "gone" / "acme-sign.git")
        assert [f["id"] for f in lab.fix_states(plan.id)] == ["fix-tls-versions", "fix-bad-signatures"]
        assert refusal(lambda: lab.connect_code(plan.id)) == "The demo repository could not be copied. The code was not connected."
    with lab.db() as db:
        assert db.query(CodeConnectionRow).count() == 0
    assert list((lab.settings.data_dir / "repos").iterdir()) == []
    assert code_fix(lab.connect_code(plan.id))["connection"]["folder"] == f"repos/plan-{plan.id}/acme-sign.git"
    lab.wait_until_idle(plan.id, 120)


def test_connect_needs_a_registered_demo_component_that_the_demo_repository_holds(lab):
    def plan_for(version):
        data = DEMO_CBOM.read_bytes().replace(b"localhost:8443", lab.settings.demo_address.encode()).replace(b'"1.4.2"', f'"{version}"'.encode())
        imp = lab.import_file("acme-pay-cbom.json", data)
        lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
        view = lab.ensure_plan(imp["id"])
        for test in view["tests"]:
            if test["kind"] in ("official_vectors", "speed_size"):
                lab.remove_test(view["id"], test["id"])
        lab.run_all(view["id"])
        lab.wait_until_idle(view["id"], 120)
        return view["id"]

    unknown = plan_for("9.9.9")  # not one of ours: its tests could not run, and there is nothing to connect
    assert lab.fix_states(unknown)[0]["id"] == "fix-tls-versions" and len(lab.fix_states(unknown)) == 1
    assert refusal(lambda: lab.connect_code(unknown)) == "Connecting code needs one of our demo signing components, and this file doesn't name one."
    newer = plan_for("1.4.3")  # ours, but the demo repository holds 1.4.2
    assert [f["id"] for f in lab.fix_states(newer)] == ["fix-tls-versions"]
    assert refusal(lambda: lab.connect_code(newer)) == "The demo repository does not hold the demo component this file names. The code was not connected."
    with lab.db() as db:
        assert db.query(CodeConnectionRow).count() == 0
    assert list((lab.settings.data_dir / "repos").iterdir()) == []  # the copy that was started is gone again
