"""The reviewer's rule for the two post-quantum exams, on made-up raw records built from the official cases; and the
note for a library that crashes on the two older signing tests (an error counts as "not accepted", never as a result).
No Docker, no library is run: every answer here is written by hand."""
import copy

import pytest

from app import pq_vectors, vectors
from app.canonical import sha256_hex
from app.execute.pqvectors import control_cases
from app.importers import parse_csv
from app.research import RuleEngine, programs
from app.reviewer import RuleReviewer
from conftest import csv_bytes
from test_real_libraries import claims_of, real_claims

ENGINE = RuleEngine()
CLAIMS = real_claims()
REFS = {p["label"]: p["ref"] for p in programs(CLAIMS)}
SPECS = {"mlkem_vectors": ENGINE._design("mlkem_vectors", CLAIMS, REFS["openssl 3.5.9 (ML-KEM-768)"]),
         "mldsa_vectors": ENGINE._design("mldsa_vectors", CLAIMS, REFS["openssl 3.5.9 (ML-DSA-65)"])}
CASES = {kind: pq_vectors.load(kind) for kind in SPECS}
NO_ANSWER_SHA = "0" * 64


def review_spec(spec, raw, component=("openssl", "3.5.9")):
    spec_hash = sha256_hex(spec)
    run = {"schema": "isogeny.run/1", "spec_hash": spec_hash, "phase": "first", "component": {"name": component[0], "version": component[1]},
           "baseline_version": None, "mode": "isolated", "started_at": "t", "finished_at": "t", "duration_ms": 1, "raw": raw,
           "logs": "", "runner": "isogeny.runner/1"}
    out = RuleReviewer().review({"spec": spec, "spec_hash": spec_hash, "proposed_by": ENGINE.engine_id, "run": run})
    return out["verdict"]["code"], out["verdict"]["reason_code"], out["control"]["outcome"], out


# ---------------------------------------------------------------- hand-made answers

def right(case) -> dict:
    """The right answer to a case, as the exam run records it."""
    if case.command == "verify":
        return {"refused": False, "valid": case.expect == "accept", "sha256": None}
    if case.expect == "refuse":
        return {"refused": True, "valid": None, "sha256": None}
    if case.expect == "answer":
        return {"refused": False, "valid": None, "sha256": case.answer_sha256}
    return {"refused": False, "valid": None, "sha256": None}      # accept: a good key is not refused


def control_answers(kind, control_name, part, must):
    """What one broken copy says to the cases it is run on (the cases execute/pqvectors.py picks for it)."""
    mine = control_cases(control_name, part, CASES[kind])
    if control_name == "wrong_answer":      # a different answer to every case
        answers = {c.id: {"refused": False, "valid": None, "sha256": NO_ANSWER_SHA} for c in mine}
    elif control_name == "skip_key_check":   # right answers, except that the flagged bad keys are not refused
        answers = {c.id: ({"refused": False, "valid": None, "sha256": None} if must["accepts_flag"] in c.flags else right(c)) for c in mine}
    else:                                   # accept_all: says "genuine" to every signature
        answers = {c.id: {"refused": False, "valid": True, "sha256": None} for c in mine}
    return {"control": control_name, "answers": answers, "no_answer": {}}


def good_raw(kind) -> dict:
    spec = SPECS[kind]
    return {"subject": {"key": "openssl-3.5.9", "answers": {c.id: right(c) for c in CASES[kind]}, "no_answer": {}},
            "controls": {part: control_answers(kind, must["control"], part, must) for part, must in spec["control"]["must"].items()},
            "files": {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}, "batch": {"command": "x"}}


def review(kind, raw):
    return review_spec(SPECS[kind], raw)


def first(kind, part, expect, flagged=None):
    return next(c for c in CASES[kind] if c.part == part and c.expect == expect and (flagged is None or flagged in c.flags))


# ---------------------------------------------------------------- ML-KEM-768

def test_mlkem_all_right_passes_and_every_broken_copy_was_caught():
    code, reason, control, out = review("mlkem_vectors", good_raw("mlkem_vectors"))
    assert (code, reason, control) == ("passed", None, "as_expected")
    assert out["control"]["reason"] == "every_broken_copy_failed_as_it_must"
    detail = out["detail"]
    assert detail["total"] == detail["right"] == 655 and detail["wrong"] == [] and detail["no_answer"] == 0 and detail["left_out"] == 0
    assert [(p["id"], p["cases"], p["right"]) for p in detail["parts"]] == [("keygen", 125, 125), ("encaps", 300, 300), ("decaps", 230, 230)]
    assert [(p["control"]["control"], p["control"]["caught"], p["control"]["of"]) for p in detail["parts"]] == [
        ("wrong_answer", 125, 125), ("skip_key_check", 117, 117), ("skip_key_check", 6, 6)]
    assert all(p["nist"] + p["wycheproof"] == p["cases"] for p in detail["parts"])


def test_mlkem_one_wrong_answer_fails_and_names_the_case():
    raw = good_raw("mlkem_vectors")
    case = first("mlkem_vectors", "encaps", "answer")
    raw["subject"]["answers"][case.id] = {"refused": False, "valid": None, "sha256": "f" * 64}
    code, reason, control, out = review("mlkem_vectors", raw)
    assert (code, reason, control) == ("failed", None, "as_expected")
    (wrong,) = out["detail"]["wrong"]
    assert wrong["id"] == case.id and wrong["part"] == "encaps" and wrong["expected"] == "answer" and wrong["got"] == "a different answer"
    assert out["detail"]["right"] == 654 and out["detail"]["total"] == 655
    encaps = next(p for p in out["detail"]["parts"] if p["id"] == "encaps")
    assert encaps["right"] == 299


@pytest.mark.parametrize("part, expect, given, said", [
    ("encaps", "refuse", {"refused": False, "valid": None, "sha256": None}, "not refused"),     # accepted a bad key
    ("decaps", "refuse", {"refused": False, "valid": None, "sha256": "f" * 64}, "not refused"),
    ("encaps", "answer", {"refused": True, "valid": None, "sha256": None}, "refused"),           # refused a good key
    ("encaps", "accept", {"refused": True, "valid": None, "sha256": None}, "refused"),
    ("keygen", "answer", {"refused": True, "valid": None, "sha256": None}, "refused"),
])
def test_mlkem_a_wrong_refusal_or_acceptance_is_a_failed_case(part, expect, given, said):
    raw = good_raw("mlkem_vectors")
    case = first("mlkem_vectors", part, expect)
    raw["subject"]["answers"][case.id] = given
    code, _, control, out = review("mlkem_vectors", raw)
    assert (code, control) == ("failed", "as_expected")
    assert [(w["id"], w["got"], w["expected"]) for w in out["detail"]["wrong"]] == [(case.id, said, expect)]


def test_mlkem_a_missing_answer_is_couldnt_run_never_a_pass():
    raw = good_raw("mlkem_vectors")
    case = first("mlkem_vectors", "decaps", "answer")
    del raw["subject"]["answers"][case.id]
    raw["subject"]["no_answer"][case.id] = "timeout"
    code, reason, _, out = review("mlkem_vectors", raw)
    assert (code, reason) == ("couldnt_run", "component_no_answer") and out["detail"]["no_answer"] == 1
    del raw["subject"]["no_answer"][case.id]            # missing without a stated reason: the same
    assert review("mlkem_vectors", raw)[:2] == ("couldnt_run", "component_no_answer")
    assert review("mlkem_vectors", {**good_raw("mlkem_vectors"), "subject": {"key": "x", "answers": {}, "no_answer": {}}})[:2] == \
        ("couldnt_run", "component_no_answer")


def test_mlkem_a_key_check_control_that_refuses_one_flagged_key_means_no_trust():
    for part, flag in (("encaps", pq_vectors.KEY_OUT_OF_RANGE), ("decaps", pq_vectors.KEY_HASH_WRONG)):
        raw = good_raw("mlkem_vectors")
        flagged = first("mlkem_vectors", part, "refuse", flag)
        raw["controls"][part]["answers"][flagged.id] = right(flagged)        # this broken copy did refuse it: it was not broken enough
        code, reason, control, out = review("mlkem_vectors", raw)
        assert (code, reason, control) == ("couldnt_trust", None, "not_as_expected"), part
        # and a subject that fails is not reported as failed on a run that can't be trusted
        raw["subject"]["answers"][flagged.id] = {"refused": False, "valid": None, "sha256": None}
        assert review("mlkem_vectors", raw)[0] == "couldnt_trust"


def test_mlkem_a_wrong_answer_control_that_is_right_on_one_case_means_no_trust():
    raw = good_raw("mlkem_vectors")
    case = first("mlkem_vectors", "keygen", "answer")
    raw["controls"]["keygen"]["answers"][case.id] = right(case)
    assert review("mlkem_vectors", raw)[:3] == ("couldnt_trust", None, "not_as_expected")


@pytest.mark.parametrize("how", ["problem", "missing_control", "missing_part", "not_a_dict", "no_answer", "missing_case", "no_controls"])
def test_mlkem_a_control_with_a_problem_or_missing_means_no_trust(how):
    raw = good_raw("mlkem_vectors")
    part = "encaps"
    if how == "problem":
        raw["controls"][part] = {"control": "skip_key_check", "problem": "the control did not run"}
    elif how == "missing_control":
        del raw["controls"][part]
    elif how == "missing_part":
        del raw["controls"]["keygen"]["answers"]
    elif how == "not_a_dict":
        raw["controls"][part] = "x"
    elif how == "no_answer":
        raw["controls"][part]["no_answer"] = {"nist-encaps-1": "timeout"}
    elif how == "missing_case":
        flagged = first("mlkem_vectors", part, "refuse", pq_vectors.KEY_OUT_OF_RANGE)
        del raw["controls"][part]["answers"][flagged.id]
    else:
        raw["controls"] = {}
    code, reason, control, _ = review("mlkem_vectors", raw)
    assert (code, reason, control) == ("couldnt_trust", None, "errored")


def test_mlkem_other_files_than_the_locked_ones_are_never_reviewed_as_the_locked_ones():
    for change in ({"x.json": "0" * 64}, {}, None):
        raw = good_raw("mlkem_vectors")
        raw["files"] = change
        assert review("mlkem_vectors", raw)[:2] == ("couldnt_run", "vector_file_changed")
    raw = good_raw("mlkem_vectors")
    name = next(iter(raw["files"]))
    raw["files"][name] = "0" * 64
    code, reason, control, out = review("mlkem_vectors", raw)
    assert (code, reason, control) == ("couldnt_run", "vector_file_changed", "not_run") and out["verdict"]["reason"]


def test_mlkem_a_changed_locked_test_is_never_trusted():
    spec = copy.deepcopy(SPECS["mlkem_vectors"])
    spec["inputs"]["cases"] = 654            # a locked test edited after the fact
    spec_hash = sha256_hex(SPECS["mlkem_vectors"])
    out = RuleReviewer().review({"spec": spec, "spec_hash": spec_hash, "proposed_by": ENGINE.engine_id,
                                 "run": {"spec_hash": spec_hash, "phase": "first", "raw": good_raw("mlkem_vectors")}})
    assert out["verdict"]["code"] == "couldnt_trust" and out["spec_hash_ok"] is False


# ---------------------------------------------------------------- ML-DSA-65

def test_mldsa_all_right_passes_and_every_broken_copy_was_caught():
    code, reason, control, out = review("mldsa_vectors", good_raw("mldsa_vectors"))
    assert (code, reason, control) == ("passed", None, "as_expected")
    detail = out["detail"]
    assert detail["total"] == detail["right"] == 475 and detail["wrong"] == [] and detail["left_out"] == 45
    assert [(p["id"], p["cases"], p["right"]) for p in detail["parts"]] == [("keygen", 25, 25), ("sign", 195, 195), ("verify", 255, 255)]
    assert [(p["control"]["control"], p["control"]["caught"], p["control"]["of"]) for p in detail["parts"]] == [
        ("wrong_answer", 25, 25), ("wrong_answer", 191, 191), ("accept_all", 167, 167)]


def test_mldsa_a_wrong_signature_fails():
    raw = good_raw("mldsa_vectors")
    case = first("mldsa_vectors", "sign", "answer")
    raw["subject"]["answers"][case.id] = {"refused": False, "valid": None, "sha256": "e" * 64}
    code, _, control, out = review("mldsa_vectors", raw)
    assert (code, control) == ("failed", "as_expected") and [w["id"] for w in out["detail"]["wrong"]] == [case.id]


def test_mldsa_a_verify_case_answered_accept_when_it_must_be_rejected_fails():
    raw = good_raw("mldsa_vectors")
    case = first("mldsa_vectors", "verify", "reject")
    raw["subject"]["answers"][case.id] = {"refused": False, "valid": True, "sha256": None}
    code, _, control, out = review("mldsa_vectors", raw)
    assert (code, control) == ("failed", "as_expected")
    (wrong,) = out["detail"]["wrong"]
    assert (wrong["id"], wrong["expected"], wrong["got"], wrong["part"]) == (case.id, "reject", "accepted", "verify")
    # the other way round: a genuine signature said to be false
    raw = good_raw("mldsa_vectors")
    genuine = first("mldsa_vectors", "verify", "accept")
    raw["subject"]["answers"][genuine.id] = {"refused": False, "valid": False, "sha256": None}
    (wrong,) = review("mldsa_vectors", raw)[3]["detail"]["wrong"]
    assert (wrong["expected"], wrong["got"]) == ("accept", "rejected")
    # and a library that refuses to answer a verify case has not said "genuine"
    raw["subject"]["answers"][genuine.id] = {"refused": True, "valid": None, "sha256": None}
    assert review("mldsa_vectors", raw)[0] == "failed"


def test_mldsa_a_sign_case_that_must_be_refused_but_is_signed_fails():
    raw = good_raw("mldsa_vectors")
    case = first("mldsa_vectors", "sign", "refuse")
    raw["subject"]["answers"][case.id] = {"refused": False, "valid": None, "sha256": "d" * 64}
    assert review("mldsa_vectors", raw)[0] == "failed"


def test_mldsa_a_missing_answer_is_couldnt_run():
    raw = good_raw("mldsa_vectors")
    case = first("mldsa_vectors", "keygen", "answer")
    del raw["subject"]["answers"][case.id]
    raw["subject"]["no_answer"][case.id] = "no answer"
    assert review("mldsa_vectors", raw)[:2] == ("couldnt_run", "component_no_answer")


def test_mldsa_an_accept_all_control_that_rejects_one_bad_signature_means_no_trust():
    raw = good_raw("mldsa_vectors")
    bad = first("mldsa_vectors", "verify", "reject")
    raw["controls"]["verify"]["answers"][bad.id] = {"refused": False, "valid": False, "sha256": None}
    assert review("mldsa_vectors", raw)[:3] == ("couldnt_trust", None, "not_as_expected")


@pytest.mark.parametrize("part", ["keygen", "sign", "verify"])
def test_mldsa_a_control_with_a_problem_or_missing_means_no_trust(part):
    raw = good_raw("mldsa_vectors")
    raw["controls"][part] = {"control": raw["controls"][part]["control"], "problem": "the harness did not answer"}
    assert review("mldsa_vectors", raw)[:3] == ("couldnt_trust", None, "errored")
    raw = good_raw("mldsa_vectors")
    del raw["controls"][part]
    assert review("mldsa_vectors", raw)[:3] == ("couldnt_trust", None, "errored")


def test_mldsa_other_files_than_the_locked_ones_mean_the_test_did_not_run():
    raw = good_raw("mldsa_vectors")
    raw["files"] = dict(raw["files"], **{next(iter(raw["files"])): "1" * 64})
    assert review("mldsa_vectors", raw)[:2] == ("couldnt_run", "vector_file_changed")


def test_the_exam_rule_never_reads_a_result_from_the_run_itself():
    for kind in SPECS:
        raw = good_raw(kind)
        raw["verdict"] = "failed"
        raw["subject"]["verdict"] = "failed"
        assert review(kind, raw)[0] == "passed"


# ---------------------------------------------------------------- a library that crashes on the two older signing tests

DEMO = claims_of(parse_csv(csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256")))
SIGNING_SPECS = {"official_vectors": ENGINE._design("official_vectors", DEMO, None), "bad_signatures": ENGINE._design("bad_signatures", DEMO, None)}


def right_for(cases) -> dict:
    return {c.id: "reject" if c.expected == "invalid" else "accept" for c in cases}


def signing_raw(kind):
    """A passing raw record for one of the two older signing tests: the library right on every case, the accept-everything
    control wrong on every invalid case, the reference library right."""
    spec = SIGNING_SPECS[kind]
    if kind == "official_vectors":
        ecdsa, ed = vectors.load_wycheproof("ecdsa_p256"), vectors.load_wycheproof("ed25519")
        cases = ecdsa.cases
        files = {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}
        reference = {"library": "x", "ecdsa_p256": {"answers": right_for(ecdsa.cases)}, "ed25519": {"answers": right_for(ed.cases)}}
    else:
        cases = vectors.load_bad_signatures().cases
        files = {spec["inputs"]["file"]: spec["inputs"]["sha256"]}
        reference = {"library": "x", "bad_signatures": {"answers": right_for(cases)}}
    raw = {"subject": {"key": "acme-sign-1.4.2", "answers": right_for(cases), "no_answer": {}},
           "control": {"key": "control-accept-all", "answers": {c.id: "accept" for c in cases}},
           "files": files, "reference": reference, "batch": {"command": "x"}}
    return spec, cases, raw


@pytest.mark.parametrize("kind", ["official_vectors", "bad_signatures"])
def test_an_older_record_without_crash_notes_is_reviewed_exactly_as_before(kind):
    spec, _, raw = signing_raw(kind)
    code, reason, control, out = review_spec(spec, raw, ("acme-sign", "1.4.2"))
    assert (code, reason, control) == ("passed", None, "as_expected")
    assert "general_errors" not in out["detail"]
    raw["subject"]["general_errors"] = {}          # an empty note is no note
    assert "general_errors" not in review_spec(spec, raw, ("acme-sign", "1.4.2"))[3]["detail"]


@pytest.mark.parametrize("kind", ["official_vectors", "bad_signatures"])
def test_a_crash_is_a_note_never_a_result(kind):
    spec, cases, raw = signing_raw(kind)
    invalid = next(c for c in cases if c.expected == "invalid")
    raw["subject"]["general_errors"] = {invalid.id: "IndexError"}
    code, reason, control, out = review_spec(spec, raw, ("openjdk", "17.0.2"))
    assert (code, reason, control) == ("passed", None, "as_expected")           # the verdict is what it was without the note
    assert out["detail"]["general_errors"] == [{"id": invalid.id, "error": "IndexError", "comment": invalid.comment, "expected": "invalid"}]
    assert out["detail"]["right"] == out["detail"]["total"] and out["detail"]["wrong"] == []


@pytest.mark.parametrize("kind", ["official_vectors", "bad_signatures"])
def test_a_crash_does_not_hide_a_wrong_answer_and_the_note_is_cut_short(kind):
    spec, cases, raw = signing_raw(kind)
    invalid = [c for c in cases if c.expected == "invalid"]
    raw["subject"]["answers"][invalid[0].id] = "accept"                           # a real wrong answer
    raw["subject"]["general_errors"] = {invalid[1].id: "E" * 200}
    code, _, control, out = review_spec(spec, raw, ("openjdk", "17.0.2"))
    assert (code, control) == ("failed", "as_expected") and [w["id"] for w in out["detail"]["wrong"]] == [invalid[0].id]
    (note,) = out["detail"]["general_errors"]
    assert note["id"] == invalid[1].id and len(note["error"]) == 60
