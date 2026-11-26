"""Who did what in the signed evidence file and in the report, and the verify command's check of that part: its exact
form, its times, that every reference resolves in the same file, and that a press agrees with the record it made. A
file from before names were kept has no such part and verifies as it always did. Each way to bend the part is tried on
purpose and must be caught.

The everyday run reads a short walk (file in, Verify, Run, Run all, Mark reviewed, two downloads); the slow set reads
the long one, with a fix from Connect demo code to the merge and a developer's change."""

import copy
import json
import random
import time

import pytest
from sqlalchemy import func, select

import record_walk
from app.canonical import canonical_bytes
from app.db import TestRunRow
from app.evidence.export import sign_envelope
from app.lab import actions
from app.present import record as words
from app.record import part as record_part
from conftest import make_lab
from evidence import actions as verifier
from evidence.__main__ import main
from record_walk import FIX
from tests.changewatch.test_changewatch_fuzz import _damage_json

FIELDS = {"n", "at", "by", "by_source", "kind", "what", "button", "item", "refs", "runs_not_in_file", "facts"}


@pytest.fixture
def walked(request, tmp_path_factory):
    return record_walk.shared(request, tmp_path_factory)


@pytest.fixture
def short(request, tmp_path_factory):
    return record_walk.shared_short(request, tmp_path_factory)


def _verify(lab, raw: bytes, tmp_path, capsys) -> tuple[int, str]:
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)
    capsys.readouterr()
    code = main(["verify", str(path), "--data-dir", str(lab.settings.data_dir)])
    return code, capsys.readouterr().out


def _press(part: dict, kind: str, nth: int = 0) -> dict:
    return [a for a in part["actions"] if a["kind"] == kind][nth]


def _started(part: dict) -> int:
    """The runs of a file that a press started: every run reference but the one a Mark reviewed is merely on."""
    return sum(
        len([r for r in a["refs"] if r["kind"] == "run"]) for a in part["actions"] if a["kind"] in verifier.STARTS_RUNS
    )


# ---------------------------------------------------------------- what the file holds (the short walk: every day)


def test_the_file_holds_each_press_with_who_when_which_button_and_what_it_started(short, tmp_path, capsys):
    part = short.download.evidence["actions"]
    assert set(part) == {"schema", "note", "sources", "actions"} and part["schema"] == "isogeny.actions/1"
    assert part["note"] == words.EVIDENCE_NOTE and set(part["sources"]) == {"account", "typed", "default"}
    # every press up to this download; a download is recorded once its file is made, so it is in the next file
    assert [a["kind"] for a in part["actions"]] == [
        "assessment_started",
        "file_imported",
        "address_confirmed",
        "test_removed",
        "verify",
        "run",
        "run_all",
        "marked_reviewed",
        "evidence_downloaded",
    ]
    assert "evidence_downloaded" not in [a["kind"] for a in short.first_download.evidence["actions"]["actions"]]
    for a in part["actions"]:
        assert set(a) == FIELDS and (a["by"], a["by_source"]) == ("You", "default")
        assert a["what"] == words.action_words(a["kind"]) and verifier.well_formed_moment(a["at"])
    run_all = _press(part, "run_all")
    assert run_all["button"] == "Run all" and run_all["item"] is None and run_all["runs_not_in_file"] == 0
    assert [r["kind"] for r in run_all["refs"]] == ["run"] * 4 and len(run_all["facts"]["items"]) == 4
    assert _press(part, "run")["item"] == f"test:{short.item['certificate']}"
    assert {"kind": "test", "id": short.item["certificate"]} in _press(part, "run")["refs"]
    assert _press(part, "verify")["refs"] == [{"kind": "verify_run", "id": 1}]
    assert _press(part, "marked_reviewed")["refs"] == [{"kind": "run", "id": short.first["bad_signatures"]}]
    assert _press(part, "address_confirmed")["facts"]["was"] is False
    first_fingerprint = json.loads(short.first_download.raw)["fingerprint"]
    assert _press(part, "evidence_downloaded")["facts"]["fingerprint"] == first_fingerprint
    # a press on a test that is no longer in the plan still says which test: the file just holds nothing to point at
    removed = _press(part, "test_removed")
    assert removed["item"] == f"test:{short.item['official_vectors']}" and removed["refs"] == []
    # nothing in the part is a result, and no key of the app or token of a session is in it
    for word in ("Passed", "Failed", "PRIVATE KEY", "password", "token"):
        assert word not in repr(part)
    # every reference is to something this same file holds, and every run of the assessment is tied to a press, once
    held = record_part._held(short.download.evidence)
    assert all(r["id"] in held[r["kind"]] for a in part["actions"] for r in a["refs"])
    with short.lab.db() as db:
        assert _started(part) == db.scalar(select(func.count(TestRunRow.id))) == 5
    # the verify command checks the part, and says what it takes as given
    code, said = _verify(short.lab, short.download.raw, tmp_path, capsys)
    assert code == 0 and said.startswith("Evidence verified")
    assert "  Who did what: 9 recorded presses, under 1 name; 5 runs are tied to the press that started them" in said
    assert "every reference resolves in this file" in said
    assert "the app does not check who is at the keyboard beyond its login" in said
    outcome = verifier.check_actions(short.download.evidence)
    assert outcome.ok and outcome.problem is None and len(outcome.lines) == 2


def test_the_report_has_the_same_rows_in_plain_words(short):
    report = short.download.report
    section = report[report.index("<h2>Who did what</h2>") :]
    assert section.index("Who did what") < section.index("End of report.")
    for cell in ("<th>When</th>", "<th>Who</th>", "Ran every test in the plan", "Run all", "Verified the claims"):
        assert cell in section, cell
    assert "No name was typed in Settings, so it reads “You”" in section
    assert section.count("<tr>") == len(short.download.evidence["actions"]["actions"]) + 1
    assert "<script" not in report


def test_a_file_with_no_press_on_record_has_no_such_part_and_verifies_as_before(tmp_path, capsys):
    lab = make_lab(tmp_path / "old")
    try:
        w = record_walk.old_walk(lab, with_fix=False)
        made = record_walk.before_names(lab, "export_evidence", w.plan_id)
        _, raw, _ = lab.evidence_file(made["id"], "json")
        _, report, _ = lab.evidence_file(made["id"], "html")
        evidence = json.loads(raw)["evidence"]
        assert "actions" not in evidence and "Who did what" not in report.decode()
        code, said = _verify(lab, raw, tmp_path, capsys)
        assert code == 0 and said.startswith("Evidence verified") and "Who did what" not in said
        # the next download is a press, and from then on the file says who made that download, and nothing about before
        lab.export_evidence(w.plan_id)
        later = record_walk.download(lab, w.plan_id)
        assert [a["kind"] for a in later.evidence["actions"]["actions"]] == ["evidence_downloaded"]
        assert _verify(lab, later.raw, tmp_path, capsys)[0] == 0
    finally:
        lab.stop()


# ---------------------------------------------------------------- the lists, written a second time


def test_the_verify_commands_own_lists_are_the_apps():
    assert verifier.SCHEMA == record_part.SCHEMA
    assert verifier.KINDS == actions.KINDS
    assert verifier.SOURCES == actions.SOURCES
    assert verifier.REF_KINDS == record_part.REF_KINDS
    assert verifier.ACTION_KEYS == FIELDS
    # a button that can queue a run: its record keeps the tests it queued
    queues = set()
    for name, what in actions.PRESSES.items():
        nothing = actions.Press("2026-11-26T00:00:00.000Z", {})
        told = actions.Told(None, None, nothing, {"version": "1", "row_id": None}, {})
        try:
            detail = what.detail(told) if what.detail is not None else {}
        except Exception:
            continue  # (its facts need the record it made: only the list of queued tests is asked for here)
        if "items" in detail:
            queues.add(what.kind if isinstance(what.kind, str) else name)
    assert {"run", "run_all", "retest", "retest_now", "measure_dependencies", "code_connected"} <= queues
    assert queues <= set(verifier.STARTS_RUNS) <= set(verifier.KINDS)
    assert set(verifier.ITEM_KINDS) == {"test", "fix", "change", "system", "run", "developer-change"}
    # a button that makes several presses at once: the app, its words and the verify command name the same ones
    assert verifier.THROUGH == actions.THROUGH and set(words.THROUGH) == set(actions.THROUGH)


# ---------------------------------------------------------------- each way to bend the part, tried on purpose


def _first(evidence: dict, kind: str) -> dict:
    return _press(evidence["actions"], kind)


def _someone_else(evidence):
    _first(evidence, "verify")["by_source"] = "administrator"


def _unknown_button(evidence):
    _first(evidence, "run_all")["kind"] = "ran_everything_quietly"


def _nobody(evidence):
    _first(evidence, "verify")["by"] = ""


def _bad_time(evidence):
    _first(evidence, "verify")["at"] = "2026-13-45T25:61:00.000Z"


def _time_without_zone(evidence):
    press = _first(evidence, "verify")
    press["at"] = press["at"].rstrip("Z")


def _out_of_order(evidence):
    listed = evidence["actions"]["actions"]
    listed[1], listed[6] = listed[6], listed[1]


def _same_number_twice(evidence):
    listed = evidence["actions"]["actions"]
    listed[1]["n"] = listed[0]["n"]


def _run_that_is_not_in_the_file(evidence):
    _first(evidence, "run_all")["refs"][0]["id"] = 99_999


def _verify_run_that_is_not_in_the_file(evidence):
    _first(evidence, "verify")["refs"][0]["id"] = 99


def _someone_elses_run(evidence):
    _first(evidence, "run")["refs"].append(dict(_first(evidence, "run_all")["refs"][0]))


def _a_run_from_a_button_that_starts_none(evidence):
    _first(evidence, "verify")["refs"].append(_first(evidence, "run_all")["refs"].pop(0))


def _unknown_reference(evidence):
    _first(evidence, "run_all")["refs"][0]["kind"] = "secret_run"


def _a_reference_with_a_name_for_a_number(evidence):
    _first(evidence, "run_all")["refs"][0]["id"] = "1"


def _the_same_reference_twice(evidence):
    refs = _first(evidence, "run_all")["refs"]
    refs.append(dict(refs[0]))


def _one_field_more(evidence):
    _first(evidence, "verify")["approved_the_result"] = True


def _one_field_less(evidence):
    del _first(evidence, "verify")["button"]


def _a_fact_that_is_not_plain(evidence):
    _first(evidence, "verify")["facts"]["note"] = {"inside": {"inside": "something"}}


def _a_tick_that_does_not_say_how_it_stands(evidence):
    del _first(evidence, "address_confirmed")["facts"]["confirmed"]


def _a_download_with_no_fingerprint(evidence):
    _first(evidence, "evidence_downloaded")["facts"]["fingerprint"] = "not-a-fingerprint"


def _no_note(evidence):
    evidence["actions"]["note"] = ""


def _no_presses(evidence):
    evidence["actions"]["actions"] = []


def _another_schema(evidence):
    evidence["actions"]["schema"] = "isogeny.actions/2"


def _a_name_source_more(evidence):
    evidence["actions"]["sources"]["administrator"] = "Whoever the file says"


def _an_item_of_no_known_kind(evidence):
    _first(evidence, "run")["item"] = "result:passed"


def _an_apply_that_does_not_say_whether_the_server_took_it(evidence):
    # (a press of Apply, as the app writes one, but for the one fact that says whether anything was applied)
    press = _first(evidence, "address_confirmed")
    press.update(kind="applied", what="Applied a change", button="Apply", facts={"apply_id": 1, "items": []})


def _a_roll_back_whose_answer_is_not_yes_or_no(evidence):
    press = _first(evidence, "address_confirmed")
    press.update(kind="rolled_back", what="Rolled a change back", button="Roll back")
    press["facts"] = {"rollback_id": 1, "accepted": "yes", "items": []}


def _made_through_a_button_the_app_does_not_have(evidence):
    _first(evidence, "assessment_started")["facts"]["through"] = "a_back_door"


DRILLS = [
    (_someone_else, "takes its name from a source this app does not have"),
    (_unknown_button, "is of a kind this app does not record"),
    (_nobody, "names nobody"),
    (_bad_time, "has a time that is not a well-formed moment in UTC"),
    (_time_without_zone, "has a time that is not a well-formed moment in UTC"),
    (_out_of_order, "the presses are not in time order"),
    (_same_number_twice, "two presses have the number"),
    (_run_that_is_not_in_the_file, "this file holds no such record"),
    (_verify_run_that_is_not_in_the_file, "this file holds no such record"),
    (_someone_elses_run, "is tied to two presses"),
    (_a_run_from_a_button_that_starts_none, "that button starts no run"),
    (_unknown_reference, "points at a kind of record this app does not reference"),
    (_a_reference_with_a_name_for_a_number, "whose id is not the kind of value that record has"),
    (_the_same_reference_twice, "lists the same reference twice"),
    (_one_field_more, "does not have exactly the fields this app writes"),
    (_one_field_less, "does not have exactly the fields this app writes"),
    (_a_fact_that_is_not_plain, "has a fact that is not a plain value"),
    (_a_tick_that_does_not_say_how_it_stands, "is a tick that does not say how the tick stands"),
    (_a_download_with_no_fingerprint, "with no fingerprint of the file that was downloaded"),
    (_no_note, "its note is missing"),
    (_no_presses, "it lists no press"),
    (_another_schema, "it is not a who-did-what record this version knows"),
    (_a_name_source_more, "it does not say what each of the three name sources is"),
    (_an_item_of_no_known_kind, "is on something this app does not name that way"),
    (_an_apply_that_does_not_say_whether_the_server_took_it, "does not say whether the server took the settings"),
    (_a_roll_back_whose_answer_is_not_yes_or_no, "does not say whether the server took the settings"),
    (_made_through_a_button_the_app_does_not_have, "says it was made through a button this app does not have"),
]


def _bent(whole: dict, bend) -> dict:
    evidence = {**whole, "actions": copy.deepcopy(whole["actions"]), "fixes": copy.deepcopy(whole["fixes"])}
    bend(evidence)
    return evidence


@pytest.mark.parametrize(("bend", "caught"), DRILLS, ids=[bend.__name__.strip("_") for bend, _ in DRILLS])
def test_a_bent_part_is_refused_and_the_command_says_what_does_not_hold(short, tmp_path, capsys, bend, caught):
    evidence = _bent(short.download.evidence, bend)
    outcome = verifier.check_actions(evidence)
    assert outcome.ok is False and caught in outcome.problem, outcome.problem
    if DRILLS.index((bend, caught)) % 4:
        return  # (every fourth drill also goes through the whole command, below; it is the same check)
    # signed again with the app's own key, so only the part's own check stands between it and "verified"
    code, said = _verify(short.lab, sign_envelope(evidence, short.lab.settings.data_dir), tmp_path, capsys)
    assert code == 1 and said.startswith("Evidence NOT verified: the who did what part: ") and caught in said
    assert "Evidence verified" not in said


def test_a_part_changed_without_signing_again_fails_on_the_signature_first(short, tmp_path, capsys):
    raw = short.download.raw.replace(b'"by":"You"', b'"by":"Eve"', 1)
    assert raw != short.download.raw
    code, said = _verify(short.lab, raw, tmp_path, capsys)
    assert code == 1 and "the fingerprint does not match the evidence" in said


# ---------------------------------------------------------------- damaged copies of the part


def test_damaged_copies_are_checked_or_refused_plainly_within_a_time_limit(short, tmp_path, capsys):
    rng = random.Random(20261126)
    outcomes = {"holds": 0, "refused": 0}
    for n in range(400):
        whole = short.download.evidence if n % 2 else short.first_download.evidence
        # the part itself, or one of the parts its references are followed into (the damage copies what it changes)
        where = "actions" if n % 4 else rng.choice(["checks", "fixes", "tests", "changes", "change_watch", "migration"])
        evidence = {**whole, where: _damage_json(rng, whole.get(where))}
        try:
            canonical_bytes(evidence[where])
        except (ValueError, TypeError):
            continue  # (a value no file can hold: the file's own reader refuses it first)
        start = time.monotonic()
        outcome = verifier.check_actions(evidence)
        assert time.monotonic() - start < 2.0
        if outcome.ok:
            outcomes["holds"] += 1
            assert outcome.problem is None and len(outcome.lines) == 2
        else:
            outcomes["refused"] += 1
            assert outcome.problem and "Traceback" not in outcome.problem and len(outcome.problem) < 400
            assert outcome.problem.isprintable()
    assert outcomes["refused"] > 100 and outcomes["holds"] >= 1, outcomes
    # a few of them through the whole command, signed again: it ends with 0 or 1 and one plain line
    for _ in range(4):
        evidence = {**short.first_download.evidence}
        evidence["actions"] = _damage_json(rng, evidence["actions"])
        try:
            raw = sign_envelope(evidence, short.lab.settings.data_dir)
        except (ValueError, TypeError):
            continue
        code, said = _verify(short.lab, raw, tmp_path, capsys)
        assert code in (0, 1) and "Traceback" not in said
        assert said.startswith("Evidence verified" if code == 0 else "Evidence NOT verified: the who did what part: ")
    # the part as something else entirely
    for odd in (None, [], "x", 7, {"schema": "isogeny.actions/1"}, {"schema": "other"}):
        assert verifier.check_actions({**short.download.evidence, "actions": odd}).ok is False
    assert verifier.well_formed_moment("2026-11-26T04:17:05.178Z")
    assert not verifier.well_formed_moment("2026-11-26 04:17")


# ---------------------------------------------------------------- the long walk: a fix, a developer's change (slow set)


def test_the_long_walks_file_names_the_fix_its_proof_and_the_watch_run(walked, tmp_path, capsys):
    part = walked.download.evidence["actions"]
    kinds = [a["kind"] for a in part["actions"]]
    assert kinds[:5] == ["assessment_started", "file_imported", "address_confirmed", "test_removed", "verify"]
    assert kinds[-3:] == ["evidence_downloaded", "demo_change_brought_in", "picked_tests_run"]
    connected = _press(part, "code_connected")
    assert {"kind": "fix", "id": FIX} in connected["refs"] and {"kind": "proof", "id": 1} in connected["refs"]
    assert len([r for r in connected["refs"] if r["kind"] == "run"]) == 4  # the proof that starts by itself
    assert _press(part, "approved", 1)["facts"] == {"approval_id": 2, "as": "Demo reviewer A", "reviewer": "a"}
    picked = _press(part, "picked_tests_run")
    assert {"kind": "watch_run", "id": 1} in picked["refs"]
    assert {"kind": "developer_change", "id": walked.change["id"]} in picked["refs"]
    order = _press(part, "tests_reordered")["facts"]["order"]
    assert order[:2] == [walked.item["certificate"], walked.item["tls_versions"]]
    held = record_part._held(walked.download.evidence)
    assert all(r["id"] in held[r["kind"]] for a in part["actions"] for r in a["refs"])
    with walked.lab.db() as db:
        started = db.scalar(select(func.count(TestRunRow.id)))
    assert _started(part) == started  # every run of the assessment is tied to a press, once
    code, said = _verify(walked.lab, walked.download.raw, tmp_path, capsys)
    assert code == 0 and f"22 recorded presses, under 1 name; {started} runs are tied to the press" in said
    report = walked.download.report
    assert "Merged a pull request" in report[report.index("<h2>Who did what</h2>") :]


def _proof_that_is_not_in_the_file(evidence):
    next(r for r in _first(evidence, "code_connected")["refs"] if r["kind"] == "proof")["id"] = 42


def _fix_that_is_not_in_the_file(evidence):
    next(r for r in _first(evidence, "merged")["refs"] if r["kind"] == "fix")["id"] = "fix-something-else"


def _approved_as_someone_who_did_not(evidence):
    _first(evidence, "approved")["facts"]["as"] = "Demo reviewer B"


def _merged_with_no_merge(evidence):
    next(f for f in evidence["fixes"] if f["id"] == FIX)["merge"] = None


def _a_pull_request_the_fix_does_not_have(evidence):
    next(f for f in evidence["fixes"] if f["id"] == FIX)["pull_request"] = None


FIX_DRILLS = [
    (_proof_that_is_not_in_the_file, "this file holds no such record"),
    (_fix_that_is_not_in_the_file, "this file holds no such record"),
    (_approved_as_someone_who_did_not, "the fix it names holds no such approval"),
    (_merged_with_no_merge, "the fix it names holds no merge"),
    (_a_pull_request_the_fix_does_not_have, "the fix it names holds no pull request"),
]


@pytest.mark.parametrize(("bend", "caught"), FIX_DRILLS, ids=[bend.__name__.strip("_") for bend, _ in FIX_DRILLS])
def test_a_press_that_does_not_agree_with_the_fix_it_names_is_refused(walked, tmp_path, capsys, bend, caught):
    evidence = _bent(walked.download.evidence, bend)
    outcome = verifier.check_actions(evidence)
    assert outcome.ok is False and caught in outcome.problem, outcome.problem
    code, said = _verify(walked.lab, sign_envelope(evidence, walked.lab.settings.data_dir), tmp_path, capsys)
    assert code == 1 and said.startswith("Evidence NOT verified: the who did what part: ") and caught in said
