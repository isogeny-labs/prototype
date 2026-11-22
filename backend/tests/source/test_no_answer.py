"""Where it came from (22 November 2026), the review's points 1 to 3: a try on a test copy, a copy, the measurement after
Roll back and a fix proof that gave no answer observed or proved nothing, so they carry no tag (Kevin: "a test that has not
run, or couldn't run, has no tag"). The words of each stay exactly as before."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.present import changes as present_changes
from app.present import source as present_source

AT = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
CHANGE = {"name": "localhost:8443", "kind": "tls", "option": "tls13", "target": None}


def _try(code: str, before: dict | None, copy: dict | None) -> dict:
    rec = {"try": SimpleNamespace(created_at=AT), "try_outcome": {"code": code, "checks": []}, "try_before": before,
           "try_copies": [{"phase": "try", "label": "a test copy with the change", "measured": copy, "skipped": None}]}
    return present_changes._try_view(CHANGE, rec)


def test_a_try_that_gave_no_answer_and_a_copy_that_couldnt_be_checked_have_no_tag():
    view = _try("couldnt_run", {"code": "failed", "detail": {}}, {"code": "couldnt_run", "detail": {}})
    assert view["verdict"]["label"] == "No answer from the try."
    assert view["source_tag"] is None
    assert [t and t["key"] for t in view["column_source_tags"]] == [None, "live", None]   # before was read; the copy was not


def test_a_try_that_passed_or_failed_is_proven_in_the_lab_and_its_before_column_observed_live():
    for code in ("passed", "failed"):
        view = _try(code, {"code": "failed", "detail": {}}, {"code": "passed", "detail": {}})
        assert view["source_tag"]["key"] == "lab", code
        assert [t and t["key"] for t in view["column_source_tags"]] == [None, "live", "lab"], code
    view = _try("passed", {"code": "couldnt_run", "detail": {}}, {"code": "passed", "detail": {}})
    assert view["column_source_tags"][1] is None       # a before that couldn't be read observed nothing


def _rolled_back(code: str) -> dict:
    rec = {"apply": SimpleNamespace(accepted=True, applied_at=AT, words=""), "events": [],
           "rollback": SimpleNamespace(accepted=True, rolled_back_at=AT), "rollback_outcome": {"code": code, "differences": []},
           "rollback_after": {"code": "passed", "finished_at": "2026-11-22T09:01:00Z", "detail": {}}}
    return present_changes._applied(CHANGE, rec)


def test_after_roll_back_with_no_answer_has_no_tag_and_a_measured_one_is_observed_live():
    assert _rolled_back("no_answer")["source_tag"] is None
    assert _rolled_back("as_before")["source_tag"]["key"] == "live"
    assert _rolled_back("not_as_before")["source_tag"]["key"] == "live"


def _proof(state: str, label: str | None, tone: str | None) -> dict:
    return {"state": state, "badge": {"label": label, "tone": tone} if label else None, "text": "", "muted": None}


def test_a_fix_proof_is_proven_in_the_lab_only_when_it_ran_and_was_believed():
    assert present_source.of_proof(_proof("passed", "Proof passed", "pass"))["key"] == "lab"
    assert present_source.of_proof(_proof("failed", "Proof did not pass", "fail"))["key"] == "lab"
    for label in ("Nothing was run", "Proof can't be trusted", "Proof did not finish"):
        assert present_source.of_proof(_proof("failed", label, "warn")) is None, label
    assert present_source.of_proof(_proof("running", None, None)) is None
    assert present_source.of_proof(_proof("not_started", None, None)) is None
    assert present_source.of_proof(None) is None
