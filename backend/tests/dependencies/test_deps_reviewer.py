"""Phase 4d: the reviewer's capability rule, from made-up raw records (no library runs here): yes, no, a control
that does not behave, a crash, an unconfirmed result, and the same copy used as a control. The rule never asks
where the library came from (the target kind is not read)."""
import copy

import pytest

from app.canonical import sha256_hex
from app.engine.research import RuleEngine
from app.engine.reviewer import RuleReviewer

ENGINE = RuleEngine(2, 5)
QUESTIONS = ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")


def spec(name="openjdk", version="17.0.2", tls=True, target_kind="public_copy"):
    return ENGINE.design_capability({"name": name, "version": version, "label": f"{name} {version}", "target_kind": target_kind,
                                     "tls": tls, "capable": "OpenSSL 3.5.9", "incapable": "OpenSSL 3.0.22 (Debian's build)"})


MADE = {"state": "made", "confirmed": True, "classical_completed": True}
REFUSED = {"state": "refused", "note": "the library's own words", "handshakes": {"classical": {"completed": True}}}


def answers(kind: str, questions=QUESTIONS) -> dict:
    return {q: copy.deepcopy(MADE if kind == "yes" else REFUSED) for q in questions}


def raw(subject: dict, capable=None, incapable=None, questions=QUESTIONS, subject_copy=("openjdk", "17.0.2")):
    return {"target": {}, "questions": list(questions), "subject": subject,
            "controls": {"capable": {"copy": {"name": "openssl", "version": "3.5.9"}, "answers": capable or answers("yes", questions)},
                         "incapable": {"copy": {"name": "openssl", "version": "3.0.22"},
                                       "answers": incapable or answers("no", questions)}}}


def review(the_spec: dict, the_raw: dict):
    h = sha256_hex(the_spec)
    run = {"schema": "isogeny.run/1", "spec_hash": h, "phase": "dependencies", "component": None, "baseline_version": None,
           "mode": "isolated", "started_at": "t", "finished_at": "t", "duration_ms": 1, "raw": the_raw, "logs": "", "runner": "isogeny.runner/1"}
    out = RuleReviewer().review({"spec": the_spec, "spec_hash": h, "proposed_by": ENGINE.engine_id, "run": run})
    return out["verdict"]["code"], out["control"]["outcome"], out["detail"]


def test_yes_only_when_it_did_it_and_the_reference_library_agreed():
    code, control, detail = review(spec(), raw(answers("yes")))
    assert (code, control) == ("measured", "as_expected") and detail["answers"] == {q: "yes" for q in QUESTIONS}


def test_no_only_when_the_library_itself_refused_and_its_words_are_kept():
    code, control, detail = review(spec(), raw(answers("no")))
    assert code == "measured" and detail["answers"] == {q: "no" for q in QUESTIONS}
    assert detail["library_says"] == {q: "the library's own words" for q in QUESTIONS}


def test_a_result_the_reference_library_did_not_confirm_is_couldnt_check_never_yes():
    subject = answers("yes")
    subject["ml_dsa_65"] = {"state": "made", "confirmed": False}
    _, _, detail = review(spec(), raw(subject))
    assert detail["answers"]["ml_dsa_65"] == "couldnt_check" and "reference library did not agree" in detail["why"]["ml_dsa_65"]


def test_a_crash_or_time_out_is_couldnt_check_with_its_reason():
    subject = answers("no")
    subject["ml_kem_768"] = {"state": "no_answer", "why": "the keygen step: time-out"}
    _, _, detail = review(spec(), raw(subject))
    assert detail["answers"]["ml_kem_768"] == "couldnt_check" and detail["why"]["ml_kem_768"] == "the keygen step: time-out"


def test_a_hybrid_yes_needs_its_own_classical_handshake_too():
    subject = answers("yes")
    subject["x25519mlkem768"] = {**MADE, "classical_completed": False}
    _, _, detail = review(spec(), raw(subject))
    assert detail["answers"]["x25519mlkem768"] == "couldnt_check"


@pytest.mark.parametrize("which, broken", [
    ("capable", {"state": "refused", "note": "x"}),            # the copy that can do it said no
    ("incapable", {"state": "made", "confirmed": True}),       # the copy that can't do it said yes
    ("incapable", {"state": "no_answer", "why": "crashed"}),   # the copy that can't do it did not answer
])
def test_a_control_that_does_not_behave_means_the_run_cant_be_trusted(which, broken):
    controls = {"capable": answers("yes"), "incapable": answers("no")}
    controls[which]["ml_kem_768"] = broken
    code, control, detail = review(spec(), raw(answers("yes"), controls["capable"], controls["incapable"]))
    assert (code, control) == ("couldnt_trust", "not_as_expected") and detail["control_misses"]


def test_the_incapable_copy_must_still_make_an_ordinary_handshake():
    incapable = answers("no")
    incapable["x25519mlkem768"] = {"state": "refused", "note": "x", "handshakes": {"classical": {"completed": False}}}
    code, control, _ = review(spec(), raw(answers("no"), incapable=incapable))
    assert (code, control) == ("couldnt_trust", "not_as_expected")


def test_the_same_copy_as_a_control_is_said():
    _, _, detail = review(spec("openssl", "3.0.22"), raw(answers("no"), subject_copy=("openssl", "3.0.22")))
    assert detail["same_copy_as_control"] == "incapable"
    _, _, detail = review(spec("openssl", "3.5.9"), raw(answers("yes")))
    assert detail["same_copy_as_control"] == "capable"


def test_a_library_without_tls_is_asked_two_questions():
    two = ("ml_kem_768", "ml_dsa_65")
    s = spec("python-ecdsa", "0.13.2", tls=False)
    assert s["inputs"]["questions"] == list(two)
    code, _, detail = review(s, raw(answers("no", two), questions=two))
    assert code == "measured" and set(detail["answers"]) == set(two)


def test_the_rule_never_reads_where_the_library_came_from():
    """One test, swappable target: the same raw outcome gives the same review whatever the target kind says."""
    a = review(spec(target_kind="public_copy"), raw(answers("no")))
    b = review(spec(target_kind="your_environment"), raw(answers("no")))
    assert a == b


def test_a_problem_from_the_executor_is_couldnt_run():
    code, _, _ = review(spec(), {"problem": {"code": "needs_isolated_mode", "detail": "demo mode"}})
    assert code == "couldnt_run"
