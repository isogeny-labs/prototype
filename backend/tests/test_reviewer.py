"""The review step, rule by rule, from hand-made raw outcomes; and the read gate against tampering."""
import copy

import pytest
from sqlalchemy import text

from app import vectors
from app.canonical import sha256_hex
from app.db import TestRunRow
from app.guidance import NIST_GUIDANCE
from app.research import RuleEngine
from app.reviewer import RuleReviewer
from conftest import demo_plan, result_of, run_kind
from test_records import DEMO_CLAIMS

ENGINE = RuleEngine(2, 5)
SPECS = {s["kind"]: s for s in ENGINE.propose_tests(DEMO_CLAIMS)["tests"]}


def review(kind, raw, phase="first", spec=None, spec_hash=None):
    spec = spec or SPECS[kind]
    spec_hash = spec_hash or sha256_hex(SPECS[kind])
    run = {"schema": "isogeny.run/1", "spec_hash": spec_hash, "phase": phase, "component": {"name": "acme-sign", "version": "1.4.2"},
           "baseline_version": None, "mode": "demo", "started_at": "t", "finished_at": "t", "duration_ms": 1, "raw": raw,
           "logs": "", "runner": "isogeny.runner/1"}
    out = RuleReviewer().review({"spec": spec, "spec_hash": spec_hash, "proposed_by": ENGINE.engine_id, "run": run})
    return out["verdict"]["code"], out["verdict"]["reason_code"], out["control"]["outcome"], out


# ---------------------------------------------------------------- T1

def versions(**states):
    table = {"TLS 1.0": "refused", "TLS 1.1": "refused", "TLS 1.2": "refused", "TLS 1.3": "accepted"}
    table.update({k.replace("_", " ").replace("TLS ", "TLS ").replace("v", "."): v for k, v in states.items()})
    return {v: {"state": s, "detail": ""} for v, s in table.items()}


GOOD_TLS_CONTROL = {"port": 1, "versions": versions(**{"TLS 1v2": "accepted"})}


def tls_raw(subject, control=GOOD_TLS_CONTROL):
    return {"subject": {"address": "localhost:8443", "ip": "127.0.0.1", "versions": subject, "evidence": []}, "control": control}


def test_tls_rule():
    assert review("tls_versions", tls_raw(versions()))[:3] == ("passed", None, "as_expected")
    code, _, control, out = review("tls_versions", tls_raw(versions(**{"TLS 1v2": "accepted"})))
    assert (code, control) == ("failed", "as_expected") and out["detail"]["accepted_outside_claim"] == ["TLS 1.2"]
    # an older version we could not test means no verdict, never a pass
    assert review("tls_versions", tls_raw(versions(**{"TLS 1v0": "unknown"})))[:2] == ("couldnt_run", "unreadable_answer")
    assert review("tls_versions", tls_raw(versions(**{"TLS 1v3": "refused"})))[:2] == ("couldnt_run", "unreadable_answer")


@pytest.mark.parametrize("control, outcome", [
    ({"error": "the control server could not be run (OSError)"}, "errored"),          # crashed
    (None, "errored"),                                                               # missing
    ({"port": 1, "versions": versions()}, "not_as_expected"),                        # did not accept the older version
    ({"port": 1, "versions": versions(**{"TLS 1v1": "accepted"})}, "not_as_expected"),  # failed, but not for the stated reason
    ({"port": 1, "versions": versions(**{"TLS 1v2": "unknown"})}, "errored"),        # timed out
])
def test_a_tls_control_that_does_not_fail_for_the_stated_reason_means_no_trust(control, outcome):
    for subject in (versions(), versions(**{"TLS 1v2": "accepted"})):
        assert review("tls_versions", tls_raw(subject, control))[:3] == ("couldnt_trust", None, outcome)


# ---------------------------------------------------------------- T2

P256 = {"algorithm": "EC", "curve": "secp256r1", "key_bits": 256, "normalized": "ECDSA P-256", "sha256_fingerprint": "x"}
WEAK = {"algorithm": "RSA", "curve": None, "key_bits": 1024, "normalized": "RSA 1024", "sha256_fingerprint": "y"}


def cert_raw(cert, control=WEAK):
    return {"subject": {"certificate": cert, "evidence": []}, "control": {"port": 1, "certificate": control} if control else {"error": "x"}}


def test_certificate_rule():
    code, _, control, out = review("certificate", cert_raw(P256))
    assert (code, control) == ("passed", "as_expected")
    assert out["detail"]["found"] == "ECDSA P-256" and out["detail"]["reasons"] == []
    note = out["detail"]["notes"][0]
    assert "NIST plans to retire" in note["text"] and note["source"]["url"] == NIST_GUIDANCE["notes"][0]["source"]["url"]
    # The owner-approved wording cites the final NIST IR 8547, not the draft.
    assert ("Under NIST IR 8547 (final, Oct 2026), ECDSA including P-256 is deprecated after 2030 "
            "and disallowed after 2035.") in note["text"]
    assert "draft" not in note["text"]
    assert note["source"]["url"] == "https://csrc.nist.gov/pubs/ir/8547/final"
    assert out["detail"]["control_reasons"] == ["algorithm_mismatch", "below_minimum"]
    p384 = dict(P256, curve="secp384r1", key_bits=384)
    assert review("certificate", cert_raw(p384))[3]["detail"]["reasons"] == ["algorithm_mismatch"]
    assert review("certificate", cert_raw(p384))[0] == "failed"
    assert review("certificate", cert_raw(dict(WEAK, key_bits=2048)))[3]["detail"]["reasons"] == ["algorithm_mismatch"]
    assert review("certificate", cert_raw(None))[:2] == ("couldnt_run", "unreadable_answer")


def test_the_minimum_comes_from_the_locked_guidance_not_from_code():
    spec = copy.deepcopy(SPECS["certificate"])
    spec["inputs"]["guidance"]["minimum_bits"]["EC"] = 384
    out = RuleReviewer().review({"spec": spec, "spec_hash": sha256_hex(spec), "proposed_by": "x",
                                 "run": {"spec_hash": sha256_hex(spec), "phase": "first", "raw": cert_raw(P256)}})
    assert out["verdict"]["code"] == "failed" and out["detail"]["reasons"] == ["below_minimum"]


@pytest.mark.parametrize("control, outcome", [(None, "errored"), (P256, "not_as_expected"),
                                              (dict(WEAK, key_bits=4096), "not_as_expected")])
def test_a_certificate_control_that_is_not_weak_means_no_trust(control, outcome):
    assert review("certificate", cert_raw(P256, control))[:3] == ("couldnt_trust", None, outcome)


# ---------------------------------------------------------------- T3 / T4 (the shared rule, on the bad-signature list)

CASES = vectors.load_bad_signatures().cases
RIGHT = {c.id: "accept" if c.expected == "valid" else "reject" for c in CASES}
ACCEPT_ALL = {c.id: "accept" for c in CASES}
FILES = {vectors.BAD_SIGNATURES["file"]: vectors.BAD_SIGNATURES["sha256"]}


def sig_raw(subject=RIGHT, control=ACCEPT_ALL, reference=RIGHT, no_answer=None):
    return {"subject": {"key": "acme-sign-1.4.2", "answers": subject, "no_answer": no_answer or {}},
            "control": {"key": "control-accept-all", "answers": control}, "files": FILES,
            "reference": {"library": "x", "bad_signatures": {"answers": reference}}, "batch": {"command": "x"}}


def test_signature_rule():
    code, _, control, out = review("bad_signatures", sig_raw())
    assert (code, control, out["reference_ok"]) == ("passed", "as_expected", True)
    assert out["detail"]["total"] == 16 and out["detail"]["control_wrong"] == 14
    wrong = dict(RIGHT, **{"r0-s0": "accept"})
    code, _, _, out = review("bad_signatures", sig_raw(wrong))
    assert code == "failed" and [w["id"] for w in out["detail"]["wrong"]] == ["r0-s0"]
    assert review("bad_signatures", sig_raw(dict(RIGHT, **{"good-1": "reject"})))[0] == "failed"  # must accept genuine ones too
    missing = {k: v for k, v in RIGHT.items() if k != "empty"}
    assert review("bad_signatures", sig_raw(missing, no_answer={"empty": "timeout"}))[:2] == ("couldnt_run", "component_no_answer")


@pytest.mark.parametrize("control, outcome", [
    (dict(ACCEPT_ALL, **{"r0-s0": "reject"}), "not_as_expected"),      # the broken signer got one right
    (RIGHT, "not_as_expected"),
    ({k: v for k, v in ACCEPT_ALL.items() if k != "wrong-tag"}, "errored"),  # it crashed or timed out on a case
    ({}, "errored"), (None, "errored"),
])
def test_a_broken_signer_that_does_not_fail_every_case_means_no_trust(control, outcome):
    for subject in (RIGHT, dict(RIGHT, **{"r0-s0": "accept"})):
        assert review("bad_signatures", sig_raw(subject, control))[:3] == ("couldnt_trust", None, outcome)


def test_a_wrong_reference_library_means_no_trust():
    code, _, control, out = review("bad_signatures", sig_raw(reference=dict(RIGHT, **{"s0": "accept"})))
    assert (code, control, out["reference_ok"]) == ("couldnt_trust", "as_expected", False)
    assert review("bad_signatures", sig_raw(reference={}))[0] == "couldnt_trust"


def test_a_different_case_file_is_not_reviewed_as_if_it_were_the_locked_one():
    raw = sig_raw()
    raw["files"] = {vectors.BAD_SIGNATURES["file"]: "0" * 64}
    assert review("bad_signatures", raw)[:2] == ("couldnt_run", "vector_file_changed")


# ---------------------------------------------------------------- the order of decisions

def test_a_reported_problem_is_couldnt_run_with_its_reason():
    for code in ("address_not_confirmed", "checker_too_old", "timeout", "isolated_unavailable", "not_a_demo_component"):
        got = review("tls_versions", {"problem": {"code": code, "text": "x"}})
        assert got[:3] == ("couldnt_run", code, "not_run")
    assert review("tls_versions", {"problem": {"code": "made-up", "text": "x"}})[:2] == ("couldnt_run", "harness_error")


def test_a_changed_test_is_never_trusted():
    changed = copy.deepcopy(SPECS["tls_versions"])
    changed["inputs"]["claimed"] = ["TLS 1.2", "TLS 1.3"]  # the claim loosened after the fact
    raw = tls_raw(versions(**{"TLS 1v2": "accepted"}))
    code, _, _, out = review("tls_versions", raw, spec=changed)
    assert code == "couldnt_trust" and out["spec_hash_ok"] is False


def test_unreadable_raw_outcome_is_never_a_pass():
    for kind in SPECS:
        for raw in ({}, {"subject": 5, "control": "x"}, {"benches": "nope"}):
            assert review(kind, raw)[0] in ("couldnt_trust", "couldnt_run"), kind


# ---------------------------------------------------------------- the read gate, against a tampered database

def _tamper(lab, *statements):
    with lab.db() as db:
        for table in ("test_specs", "test_runs", "reviews"):
            db.execute(text(f"DROP TRIGGER IF EXISTS {table}_no_update"))
        for statement in statements:
            assert db.execute(text(statement)).rowcount >= 1
        db.commit()


def test_changing_one_stored_answer_is_caught(lab):
    plan = demo_plan(lab)
    before = run_kind(lab, plan, "bad_signatures")
    assert before["label"] == "Failed"
    # make the stored raw output say the component rejected r=0, s=0 after all
    _tamper(lab, """UPDATE test_runs SET raw = json_set(raw, '$.subject.answers."r0-s0"', 'reject', '$.subject.answers."s-plus-n"', 'reject')""")
    after = result_of(lab.lab_view(plan.id), "bad_signatures")
    assert after["label"] == "Couldn't trust this run" and after["summary"] == "The stored record no longer matches its fingerprint."
    assert after["suggested_fix"] is None
    assert lab.plan_view(plan.id)["tests"][3]["result"]["code"] == "couldnt_trust"


def test_changing_the_stated_verdict_or_control_result_is_caught(lab):
    plan = demo_plan(lab)
    assert run_kind(lab, plan, "bad_signatures")["label"] == "Failed"
    _tamper(lab, "UPDATE reviews SET code = 'passed'")
    assert result_of(lab.lab_view(plan.id), "bad_signatures")["label"] == "Couldn't trust this run"
    _tamper(lab, "UPDATE reviews SET code = 'failed', control_outcome = 'not_as_expected'")
    assert result_of(lab.lab_view(plan.id), "bad_signatures")["label"] == "Couldn't trust this run"
    _tamper(lab, "UPDATE reviews SET control_outcome = 'as_expected'")  # put back exactly: trusted again
    assert result_of(lab.lab_view(plan.id), "bad_signatures")["label"] == "Failed"
    _tamper(lab, """UPDATE reviews SET detail = json_set(detail, '$.wrong', json('[]'))""")
    assert result_of(lab.lab_view(plan.id), "bad_signatures")["label"] == "Couldn't trust this run"


def test_changing_the_locked_test_text_is_caught(lab):
    plan = demo_plan(lab)
    assert run_kind(lab, plan, "certificate")["label"] == "Passed"
    _tamper(lab, "UPDATE test_specs SET canonical = replace(canonical, 'Passed only if', 'Passed if') WHERE kind = 'certificate'")
    assert result_of(lab.lab_view(plan.id), "certificate")["label"] == "Couldn't trust this run"


def test_nothing_is_shown_without_a_review(lab):
    plan = demo_plan(lab)
    with lab.db() as db:  # a run record that looks like a pass, but that no review step has looked at
        spec_hash = db.execute(text("SELECT spec_hash FROM plan_items WHERE id = :i"), {"i": plan.item["certificate"]}).scalar()
        db.add(TestRunRow(plan_id=plan.id, plan_item_id=plan.item["certificate"], spec_hash=spec_hash, phase="first",
                          retest_id=None, component_name=None, component_version=None, baseline_version=None, mode="demo",
                          started_at="2026-11-11T00:00:00.000Z", finished_at="2026-11-11T00:00:01.000Z", duration_ms=1000,
                          raw=cert_raw(P256), logs="", runner="someone-else"))
        db.commit()
    row = next(r for r in lab.lab_view(plan.id)["rows"] if r["kind"] == "certificate")
    assert row["result"] is None and row["result_status"]["status_text"] == "Not run yet" and row["control_line"] == ""
    card = next(t for t in lab.plan_view(plan.id)["tests"] if t["kind"] == "certificate")
    assert card["status"] == "not_run" and card["result"] is None
    assert lab.plan_view(plan.id)["has_results"] is False
