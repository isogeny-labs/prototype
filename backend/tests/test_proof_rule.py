"""The offer rule: may a proposed change be offered? Case by case, from hand-made proof records only."""
import ast
import copy
from pathlib import Path

import pytest

from app import reviewer
from app.canonical import sha256_hex
from app.research import ReviewNotAllowed, RuleEngine
from app.reviewer import RuleReviewer
from test_speed_rule import SPEC as SPEED_SPEC, benches, timings

ENGINE = "isogeny.rule-engine/1"


def ran(code, reason_code=None, control="as_expected"):
    return {"run_sha256": "b" * 64, "code": code, "reason_code": reason_code, "control_outcome": control}


def first(code, reason_code=None):
    return {"run_sha256": "a" * 64, "code": code, "reason_code": reason_code}


def entry(item_id, kind, target, before, after):
    return {"item_id": item_id, "kind": kind, "spec_hash": f"{item_id:064d}", "target": target, "first": before, "proof": after}


def record(**changes):
    """A proof that should be offered: the demo plan plus the post-quantum check, as it comes out on the fixed code."""
    base = {
        "schema": "isogeny.proof/1",
        "change": {"fix_key": "ecdsa-range-check", "template_id": "ecdsa-range-check", "branch": "fix/ecdsa-range-check",
                   "base_commit": "1" * 40, "head_commit": "2" * 40,
                   "files": [{"name": "acme_sign.py", "added": 3, "removed": 1, "old_blob": "3" * 40, "new_blob": "4" * 40,
                              "old_sha256": "5" * 64, "new_sha256": "6" * 64}]},
        "built": {"file": "acme_sign.py", "sha256": "6" * 64, "matches": {"name": "acme-sign", "version": "1.4.3"}},
        "baseline_version": "1.4.2", "version": "1.4.3", "proposed_by": ENGINE,
        "tests": [
            entry(1, "tls_versions", "server", first("failed"), ran("failed")),
            entry(2, "certificate", "server", first("passed"), ran("passed")),
            entry(3, "official_vectors", "software", first("failed"), ran("passed")),
            entry(4, "bad_signatures", "software", first("failed"), ran("passed")),
            entry(5, "speed_size", "software", first("measured"), ran("no_slowdown")),
            entry(6, "pq_readiness", "server", first("not_offered"), ran("not_offered")),
        ],
    }
    base.update(changes)
    return base


def with_test(item_id, **changes):
    out = record()
    row = next(t for t in out["tests"] if t["item_id"] == item_id)
    row.update(changes)
    return out


def review(rec):
    return RuleReviewer().review_proof(rec)


def reasons(answer):
    return {t["kind"]: (t["ok"], t["reason"]) for t in answer["tests"]}


def test_a_proof_that_holds_is_offered():
    rec = record()
    answer = review(rec)
    assert answer["offered"] is True and answer["reviewer"] == "isogeny.rule-reviewer/1" and answer["schema"] == "isogeny.proof-review/1"
    assert answer["checks"] == {"code_is_ours": True, "changed_code_passed": True, "controls_behaved": True, "server_unchanged": True}
    assert answer["counts"] == {"tests": 6, "code": 3, "code_ok": 3, "server": 3, "server_ok": 3}
    assert [(t["item_id"], t["kind"], t["group"], t["ok"], t["reason"]) for t in answer["tests"]] == [
        (1, "tls_versions", "server", True, "same_as_before"), (2, "certificate", "server", True, "same_as_before"),
        (3, "official_vectors", "code", True, "passed"), (4, "bad_signatures", "code", True, "passed"),
        (5, "speed_size", "code", True, "no_slowdown"), (6, "pq_readiness", "server", True, "same_as_before")]
    # the fingerprint is the SHA-256 of the record's one exact form, and the same record always gets the same answer
    assert answer["record_sha256"] == sha256_hex(rec) == sha256_hex(copy.deepcopy(rec)) and len(answer["record_sha256"]) == 64
    assert review(rec) == answer and rec == record()  # nothing in the record was changed by reviewing it


@pytest.mark.parametrize("code, reason_code, control", [
    ("failed", None, "as_expected"),                    # the bug is still there
    ("couldnt_run", "component_no_answer", "not_run"),  # it could not run on the changed code
    ("couldnt_run", "timeout", "not_run"),
    ("measured", None, "as_expected"),                  # a result of another test's kind is not a pass
    ("slowdown", None, "as_expected"),
])
def test_a_software_test_that_did_not_pass_on_the_changed_code(code, reason_code, control):
    answer = review(with_test(4, proof=ran(code, reason_code, control)))
    assert answer["offered"] is False and answer["checks"]["changed_code_passed"] is False
    assert reasons(answer)["bad_signatures"] == (False, "did_not_pass")
    assert answer["checks"]["controls_behaved"] is True and answer["checks"]["server_unchanged"] is True
    assert answer["counts"]["code_ok"] == 2


def test_a_slowdown_or_a_first_run_style_measurement_is_not_a_pass_for_the_speed_test():
    for code in ("slowdown", "measured", "passed", "couldnt_run"):
        answer = review(with_test(5, proof=ran(code, control="not_run" if code == "couldnt_run" else "as_expected")))
        assert answer["offered"] is False and reasons(answer)["speed_size"] == (False, "did_not_pass"), code


@pytest.mark.parametrize("item_id, kind", [(1, "tls_versions"), (3, "official_vectors"), (5, "speed_size")])
@pytest.mark.parametrize("outcome", ["not_as_expected", "errored", "not_run"])
def test_a_control_that_misbehaved_in_any_test(item_id, kind, outcome):
    """Even when the stated result would count, a run whose control did not behave shows nothing."""
    rec = record()
    row = next(t for t in rec["tests"] if t["item_id"] == item_id)
    row["proof"]["control_outcome"] = outcome
    answer = review(rec)
    assert answer["offered"] is False and answer["checks"]["controls_behaved"] is False
    assert reasons(answer)[kind] == (False, "control_misbehaved")
    # as the reviewer really stores such a run: "Couldn't trust this run"
    answer = review(with_test(item_id, proof=ran("couldnt_trust", None, outcome)))
    assert answer["offered"] is False and reasons(answer)[kind] == (False, "control_misbehaved")


@pytest.mark.parametrize("before, after", [
    (first("failed"), ran("passed")),                                                   # even a change for the better
    (first("passed"), ran("failed")),
    (first("failed"), ran("couldnt_run", "address_not_confirmed", "not_run")),          # it could not run this time
    (first("couldnt_run", "checker_too_old"), ran("couldnt_run", "server_unreachable", "not_run")),  # another reason
    (first("couldnt_run", "checker_too_old"), ran("not_offered")),
])
def test_a_server_test_that_changed(before, after):
    answer = review(with_test(1, first=before, proof=after))
    assert answer["offered"] is False and answer["checks"]["server_unchanged"] is False
    assert reasons(answer)["tls_versions"] == (False, "changed")
    assert answer["checks"]["changed_code_passed"] is True and answer["counts"]["server_ok"] == 2


def test_a_server_test_that_could_not_run_both_times_for_the_same_reason_counts_as_unchanged():
    """No OpenSSL 3.5 here, before or after: nothing about the server changed, and its control never ran."""
    rec = with_test(6, first=first("couldnt_run", "checker_too_old"), proof=ran("couldnt_run", "checker_too_old", "not_run"))
    answer = review(rec)
    assert answer["offered"] is True and reasons(answer)["pq_readiness"] == (True, "same_as_before")
    assert answer["checks"]["controls_behaved"] is True


def test_a_missing_run():
    for item_id, kind, check in ((2, "certificate", "server_unchanged"), (3, "official_vectors", "changed_code_passed")):
        answer = review(with_test(item_id, proof=None))
        assert answer["offered"] is False and answer["checks"][check] is False
        assert reasons(answer)[kind] == (False, "no_run")
    nothing_ran = record()
    for row in nothing_ran["tests"]:
        row["proof"] = None
    answer = review(nothing_ran)
    assert answer["offered"] is False and answer["counts"] == {"tests": 6, "code": 3, "code_ok": 0, "server": 3, "server_ok": 0}
    assert review(record(tests=[]))["offered"] is False  # and a proof with no tests at all proves nothing


def test_a_server_test_with_no_first_result_has_nothing_to_compare_with():
    answer = review(with_test(2, first=None))
    assert answer["offered"] is False and reasons(answer)["certificate"] == (False, "nothing_to_compare")


@pytest.mark.parametrize("built", [
    {"file": "acme_sign.py", "sha256": "7" * 64, "matches": None},                                   # no registered component is this code
    {"file": "acme_sign.py", "sha256": "6" * 64, "matches": {"name": "acme-sign", "version": "1.4.2"}},  # not the version that ran
    {"file": "acme_sign.py", "sha256": "6" * 64, "matches": {"name": "", "version": "1.4.3"}},
    {"file": "acme_sign.py", "sha256": "6" * 64, "matches": "acme-sign 1.4.3"},
    {},
])
def test_code_that_matches_no_registered_component_is_never_offered(built):
    answer = review(record(built=built))
    assert answer["offered"] is False and answer["checks"]["code_is_ours"] is False
    assert answer["checks"]["changed_code_passed"] is True  # every test did pass: it is the code check alone that stops it


def test_a_report_only_test_only_has_to_run():
    rec = record()
    rec["tests"].append(entry(7, "mldsa_compare", "software", first("measured"), ran("measured")))
    answer = review(rec)
    assert answer["offered"] is True and reasons(answer)["mldsa_compare"] == (True, "ran")
    assert answer["counts"] == {"tests": 7, "code": 4, "code_ok": 4, "server": 3, "server_ok": 3}
    for after, reason in ((ran("couldnt_run", "harness_error", "not_run"), "did_not_pass"), (None, "no_run"),
                          (ran("couldnt_trust", None, "not_as_expected"), "control_misbehaved")):
        rec["tests"][-1]["proof"] = after
        answer = review(rec)
        assert answer["offered"] is False and reasons(answer)["mldsa_compare"] == (False, reason)


def test_a_proof_in_which_no_test_runs_the_changed_code_proves_nothing_about_it():
    rec = record()
    rec["tests"] = [t for t in rec["tests"] if t["target"] == "server"]
    answer = review(rec)
    assert answer["offered"] is False and answer["checks"]["changed_code_passed"] is False
    assert answer["checks"]["server_unchanged"] is True and answer["counts"]["code"] == 0


def test_a_kind_of_test_the_rule_does_not_know_never_counts_as_passed():
    rec = record()
    rec["tests"].append(entry(8, "some_new_test", "software", first("passed"), ran("passed")))
    assert review(rec)["offered"] is False


def test_the_reviewer_never_reviews_a_change_it_proposed_itself():
    with pytest.raises(ReviewNotAllowed):
        review(record(proposed_by=RuleReviewer.engine_id))
    assert RuleReviewer.engine_id != RuleEngine.engine_id
    with pytest.raises(NotImplementedError):
        RuleReviewer().propose_change({})


def test_any_change_to_the_record_changes_its_fingerprint():
    base = review(record())["record_sha256"]
    changed = [record(version="1.4.4"), record(baseline_version="1.4.1"), with_test(3, spec_hash="9" * 64),
               with_test(1, first=dict(first("failed"), run_sha256="c" * 64)), with_test(4, proof=dict(ran("passed"), run_sha256="d" * 64))]
    moved = record()
    moved["change"]["head_commit"] = "8" * 40
    assert len({base, *(review(r)["record_sha256"] for r in changed + [moved])}) == 7


def test_the_offer_rule_reads_no_file_and_imports_nothing_new():
    """It is decided from the record alone: the reviewer still imports only what it did before."""
    tree = ast.parse(Path(reviewer.__file__).read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"open", "read_bytes", "read_text", "Path", "components", "GitRepo", "subprocess"}


# ---------------------------------------------------------------- the speed rule on a proof run

def speed_review(phase, roles=("old", "new", "control")):
    series = {"old": benches("old", "acme-sign-1.4.2", timings(1, 7.0), timings(2, 13.0)),
              "new": benches("new", "acme-sign-1.4.3", timings(3, 7.0), timings(4, 13.0)),
              "subject": benches("subject", "acme-sign-1.4.3", timings(3, 7.0), timings(4, 13.0)),
              "control": benches("control", "control-slow:acme-sign-1.4.3", timings(5, 7.0, 3.0), timings(6, 13.0, 3.0))}
    raw = {"benches": [b for role in roles for b in series[role]], "reference": None, "exclusive": True}
    run = {"spec_hash": sha256_hex(SPEED_SPEC), "phase": phase, "raw": raw}
    out = RuleReviewer().review({"spec": SPEED_SPEC, "spec_hash": sha256_hex(SPEED_SPEC), "proposed_by": ENGINE, "run": run})
    return out["verdict"]["code"], out["control"]["outcome"], out["detail"]


def test_a_proof_run_of_the_speed_test_is_judged_exactly_like_a_retest():
    proof, retest = speed_review("proof"), speed_review("retest")
    assert proof == retest and proof[:2] == ("no_slowdown", "as_expected")
    assert proof[2]["comparison"] and proof[2]["old"]["key"] == "acme-sign-1.4.2" and proof[2]["new"]["key"] == "acme-sign-1.4.3"
    # timings of the changed code alone, with nothing to compare them with, never count as "no slowdown"
    assert speed_review("proof", roles=("subject", "control"))[0] == "couldnt_run"
    assert speed_review("first", roles=("subject", "control"))[0] == "measured"
