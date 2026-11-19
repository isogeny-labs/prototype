"""Change watch in the signed evidence file and in the report, and the verify command's check of that part against
the runs in the file (phase 6d)."""
import copy
import itertools
import json
import random
import re
import time
from types import SimpleNamespace

import pytest

from app.canonical import canonical_bytes, sha256_hex
from app.db import WatchRunRow
from app.engine.reviewer import RuleReviewer
from app.evidence.export import CHANGE_WATCH_SCHEMA, sign_envelope
from conftest import make_lab
from evidence import changewatch as verifier
from evidence.__main__ import main
from test_changes import FIX, proved, small_plan
from test_changes_read import SOMEONE, V143, one, repo_of
from test_changewatch_fuzz import _damage_json

REVERT, TLS = "dev/revert-range-check", "dev/allow-tls-1-0-for-partner"
ZERO64, ZERO40 = "0" * 64, "0" * 40


def _download(lab, plan) -> SimpleNamespace:
    made = lab.export_evidence(plan.id)
    _, raw, _ = lab.evidence_file(made["id"], "json")
    _, report, _ = lab.evidence_file(made["id"], "html")
    return SimpleNamespace(raw=raw, evidence=json.loads(raw)["evidence"], report=report.decode())


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    """The demo fix merged; a file downloaded before any change is in; both demo changes brought in and the first one's
    picked tests run; a second file; then Run again, a branch whose run was cut off, and a third file."""
    lab = make_lab(tmp_path_factory.mktemp("watch-evidence"))
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        before = _download(lab, plan)
        for key in ("revert-range-check", "allow-tls-1-0"):
            lab.bring_in_demo_change(plan.id, key)
        listed = _download(lab, plan)                      # the changes are in, nothing has run
        change = one(lab.change_watch_state(plan.id), REVERT)
        lab.run_picked_tests(plan.id, change["id"])
        lab.wait_until_idle(plan.id, 120)
        ran = _download(lab, plan)
        lab.run_picked_tests(plan.id, change["id"])        # Run again: a second watch run of the same change
        lab.wait_until_idle(plan.id, 120)
        repo = repo_of(lab, plan.id)
        repo.branch_from("dev/again-the-fix", repo.branch("main"), {"acme_sign.py": V143 + b"# kept\n"}, "A branch", SOMEONE, int(time.time()))
        with lab.db() as db:        # a watch run whose jobs never wrote a run (the app was closed while they waited)
            items = {i.id: i for i in lab._items(db, plan.id)}
            db.add(WatchRunRow(plan_id=plan.id, branch=change["branch"], base_commit=change["base"], head_commit=change["head"], version="1.4.2",
                               base_version="1.4.3", files=change["digests"], not_picked=[],
                               items=[{"item_id": t["item_id"], "spec_hash": items[t["item_id"]].spec_hash, "kind": t["kind"], "before_run_id": None}
                                      for t in change["picked"]]))
            db.commit()
        later = _download(lab, plan)
        yield SimpleNamespace(lab=lab, plan=plan, data_dir=str(lab.settings.data_dir), before=before, listed=listed, ran=ran, later=later)
    finally:
        lab.stop()


def _verify(made, raw: bytes, tmp_path, capsys) -> tuple[int, str]:
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)
    capsys.readouterr()
    code = main(["verify", str(path), "--data-dir", made.data_dir])
    return code, capsys.readouterr().out


# ---------------------------------------------------------------- what the file holds

def test_a_file_made_before_any_change_is_in_has_no_change_watch_part_and_verifies_as_before(made, tmp_path, capsys):
    assert "change_watch" not in made.before.evidence
    code, said = _verify(made, made.before.raw, tmp_path, capsys)
    assert code == 0 and said.startswith("Evidence verified") and "Change watch" not in said
    assert "9. Change watch" not in made.before.report


def test_once_a_change_is_in_the_file_lists_it_with_its_files_its_tests_and_its_flags_before_anything_ran(made, tmp_path, capsys):
    part = made.listed.evidence["change_watch"]
    assert set(part) == {"schema", "note", "repository", "program", "changes", "runs"} and part["schema"] == CHANGE_WATCH_SCHEMA
    assert part["runs"] == [] and part["repository"] == {"state": "connected", "name": "acme-sign", "branch": "main"}
    assert part["program"] == {"name": "acme-sign", "version": "1.4.2", "file": "acme_sign.py"}
    by_branch = {c["branch"]: c for c in part["changes"]}
    revert, tls = by_branch[REVERT], by_branch[TLS]
    assert (revert["status"]["key"], revert["watch_run_id"], revert["is_demo"], revert["author"]) == ("not_run", None, True, "Demo developer")
    assert revert["gives"] == {"name": "acme-sign", "version": "1.4.2"} and revert["starts_from"] == {"name": "acme-sign", "version": "1.4.3"}
    # the fingerprint of its lines: each file before and after
    assert [(f["name"], f["state"]) for f in revert["files"]] == [("acme_sign.py", "changed")]
    assert all(re.fullmatch("[0-9a-f]{64}", revert["files"][0][k]) for k in ("old_sha256", "new_sha256"))
    assert [t["kind"] for t in revert["picked"]] == ["bad_signatures", "speed_size"]
    assert all(t["reason"] == "Runs acme-sign, and this change edits acme_sign.py." and t["rule"] == "runs_the_program" for t in revert["picked"])
    assert [t["rule"] for t in revert["not_picked"]] == ["server_test", "server_test"]
    # the other change touches no program file: nothing is picked, and its line that names TLS 1.0 is a flag, not a result
    assert (tls["status"]["key"], tls["picked"], tls["status"]["word"]) == ("nothing_to_run", [], "Nothing to run")
    flag, = tls["flags"]
    assert (flag["word"], flag["line"], flag["note"]) == ("TLS 1.0", 4, "The app has not tested what this line does.")
    assert flag["source"]["url"].startswith("https://")
    code, said = _verify(made, made.listed.raw, tmp_path, capsys)
    assert code == 0 and "Change watch: 2 changes, 0 runs of the picked tests (0 test runs)" in said


def test_after_a_watch_run_the_file_holds_both_runs_of_every_picked_test_the_watch_record_and_the_reviewers_word(made, tmp_path, capsys):
    part = made.ran.evidence["change_watch"]
    change = next(c for c in part["changes"] if c["branch"] == REVERT)
    run, = part["runs"]
    assert change["watch_run_id"] == run["watch_run_id"] and change["run_covers_picked"] is True
    assert change["status"] == {"key": "passed_before_fails_now", "word": "Passed before, fails now (1 test)",
                                "reason": "1 test passed on the code before and fails on this change."}
    assert (run["branch"], run["head_commit"], run["base_commit"]) == (change["branch"], change["head_commit"], change["base_commit"])
    assert (run["version"], run["base_version"], run["believed"]) == ("1.4.2", "1.4.3", True)
    for test in run["tests"]:
        for which, version, digest in (("before", "1.4.3", "old_sha256"), ("now", "1.4.2", "new_sha256")):
            entry = test[which]
            assert sha256_hex(entry["record"]) == entry["run_sha256"] == entry["review"]["run_sha256"]      # the run in full, with its review
            assert entry["record"]["spec_hash"] == test["spec_hash"] and entry["result"]["label"]
            assert (entry["code"]["component_version"], entry["code"]["file_sha256"]) == (version, run["files"][0][digest])
        assert (test["now"]["phase"], test["now"]["code"]["commit"], test["now"]["code"]["branch"]) == ("watch", run["head_commit"], REVERT)
        assert test["before"]["phase"] == "proof" and test["before_made_here"] is False
    record, review = run["record"], run["review"]
    assert sha256_hex(record) == run["record_sha256"] == review["record_sha256"] and record["matches"] == {"name": "acme-sign", "version": "1.4.2"}
    assert (review["status"], review["reviewer"], review["code_is_ours"]) == ("passed_before_fails_now", made.lab.reviewer.engine_id, True)
    assert {t["kind"]: t["outcome"] for t in review["tests"]} == {"bad_signatures": "fails_now", "speed_size": "not_slower"}
    # no time in the file is marked for a browser, and nothing in it is a key
    text = json.dumps(part)
    assert "[[time:" not in text and "PRIVATE" not in text
    code, said = _verify(made, made.ran.raw, tmp_path, capsys)
    assert code == 0 and said.startswith("Evidence verified")
    assert "Change watch: 2 changes, 1 run of the picked tests (4 test runs): each run matches its fingerprint and ran on the change's code." in said
    assert "Change watch: 1 reviewed run: the watch record is what the runs give, and the reviewer's word for the change follows from it." in said


def test_every_run_the_list_of_checks_says_came_from_change_watch_is_in_the_part_with_the_same_fingerprint(made):
    evidence = made.ran.evidence
    rows = [c for c in evidence["checks"] if c["came_from"] == "Change watch"]
    assert rows and verifier.needs_change_watch_part(evidence) and not verifier.needs_change_watch_part(made.before.evidence)
    in_part = {t["now"]["run_id"]: t["now"]["run_sha256"] for run in evidence["change_watch"]["runs"] for t in run["tests"]}
    listed = {r["run_id"]: r["run_sha256"] for row in rows for r in row["runs"]}
    assert listed == in_part


def test_earlier_runs_and_a_run_that_was_cut_off_are_kept_in_the_file_and_it_still_verifies(made, tmp_path, capsys):
    part = made.later.evidence["change_watch"]
    first, second, cut = part["runs"]
    change = next(c for c in part["changes"] if c["branch"] == REVERT)
    # the run that was cut off is the newest of this code: the change reads "Not run yet" again, and the file says why
    assert change["watch_run_id"] == cut["watch_run_id"] and change["status"]["key"] == "not_run"
    assert change["status"]["reason"] == "The last run was cut off before it finished. Run the picked tests again."
    assert (cut["record"], cut["review"], cut["believed"]) == (None, None, None)
    assert cut["tests"] and all(t["now"] is None and t["before"] is None for t in cut["tests"])        # none of its runs was ever written
    assert first["review"]["status"] == second["review"]["status"] == "passed_before_fails_now" and first["record_sha256"] != second["record_sha256"]
    other = next(c for c in part["changes"] if c["branch"] == "dev/again-the-fix")
    assert (other["status"]["key"], other["gives"], other["watch_run_id"]) == ("cant_run", None, None)     # not one of our programs: nothing of it runs
    code, said = _verify(made, made.later.raw, tmp_path, capsys)
    assert code == 0 and "Change watch: 3 changes, 3 runs of the picked tests (8 test runs)" in said and "2 reviewed runs" in said


# ---------------------------------------------------------------- the report

def test_the_report_has_part_9_with_each_change_its_tests_its_results_before_and_on_the_change_and_its_flags(made):
    report = made.ran.report
    at = report.index("9. Change watch")
    part = re.sub(r"<[^>]+>", " ", report[at:])
    part = re.sub(r"\s+", " ", part)
    for words in ("Revert the range check", "Passed before, fails now (1 test)", "Branch dev/revert-range-check, commit ",
                  "By Demo developer (demo data)", "Its code is, byte for byte, acme-sign 1.4.2", "Tests picked", "Not picked",
                  "Attacker tricks (our short list): Runs acme-sign, and this change edits acme_sign.py.",
                  "Attacker tricks (our short list): Passed before, fails now", "Speed and size: No slowdown against the code before",
                  "before, on the code the change starts from", "on the change", "Fingerprint of the watch record (SHA-256): ",
                  "Allow TLS 1.0 for an old partner", "Nothing to run", "names TLS 1.0. The app has not tested what this line does.",
                  "A flag is something to look at, never a result."):
        assert words in part, words
    assert "<script" not in report.lower() and "Earlier runs" not in part
    later = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", made.later.report))
    assert "Earlier runs" in later and "This run did not finish, so it was not reviewed. It is no result." in later
    for word in ("secure", "score", "severity"):
        assert word not in part.lower()


# ---------------------------------------------------------------- a change inside the part is caught

def _refit(run: dict) -> None:
    """Make the watch record's fingerprint and the review's name for it fit the (changed) watch record again."""
    run["record_sha256"] = run["review"]["record_sha256"] = sha256_hex(run["record"])


CHANGED = {
    "a run record changed": "the run record does not match its fingerprint",
    "a run record changed with its fingerprint": "the watch record names another run than the one in the file",
    "the reviewer's word changed": "does not follow from the runs in the file",
    "a test's placing changed": "does not follow from the runs in the file",
    "the count of a placing changed": "does not follow from the runs in the file",
    "the watch record's line for a run changed": "the watch record does not say what the run's review says",
    "a test dropped from the watch record": "the watch record does not list the tests of the watch run",
    "the watch record of another change": "the watch record is of another change",
    "the watch record changed without its fingerprint": "the watch record does not match its fingerprint",
    "the review names another watch record": "its review is of another watch record",
    "the run on the change ran another commit": "did not run on the commit this watch run names",
    "the run on the change ran another program file": "does not have the fingerprint the change's file list gives",
    "the run on the change ran another version": "the code it is said to have run on is not the code its run record names",
    "the run before ran another version": "the code it is said to have run on is not the code its run record names",
    # what the second review of 6d showed was not held (19 November 2026): each of these verified before
    "the run left out of the change's entry": "does not name the newest watch run of its code that the file holds",
    "the run said to be of other tests": "whether its watch run is of the tests picked now is not what the two lists show",
    "the count in the status word changed": "its status word is not the word of its status (Passed before, fails now (1 test))",
    "the run before put where the run on the change stands": "its run record is not of version 1.4.2",
    "a run record of another kind of run where the run on the change stands": "its run record is not a run made for this change",
    "the change's own version changed": "its files or versions are not the ones its watch run was made for",
    "the change's own files changed": "its files or versions are not the ones its watch run was made for",
    "a not-trusted line with another result code": "the watch record does not say what the run's review says",
    "the review under another reviewer's name": "its review was not made by the reviewer this file names",
    "the kind of run said beside a run changed": "the kind of run it is said to be is not the one its run record names",
    "the watch record names another program": "its runs are not all of the one program the watch record names",
    "the part is said to be about another program": "holds a run of another program than the one this part is about",
    "the entry in Fixes for the change taken out": "the file's list of fixes has no text-only entry for it",
    "an entry in Fixes for a change that does not read so": "has an entry for a developer's change that does not read",
    "a run of another locked test": "is not a run of the locked test this watch run names",
    "the change's status changed": "is not the one its watch run gives",
    "the status word changed": "its status word is not the word of its status",
    "the change names a watch run that is not there": "names a watch run that is not in the file",
    "the change names a watch run of other code": "names a watch run of other code",
    "the part taken out": "has no Change watch part",
    "a check row with another fingerprint": "the part does not hold that run with that fingerprint",
    "a check row for a run the part does not hold": "the part does not hold that run with that fingerprint",
    "believed turned off": "the file says its review was not believed, and the review matches",
    "the review taken out": "is not the one a change has while its watch run does not count",
    "a key added to the part": "it is not written as this app writes it",
    "the same watch run twice": "is in the file twice",
    "a run that is also the test's own, with another fingerprint there": "has another fingerprint in the file's own tests",
}


@pytest.mark.parametrize("name", sorted(CHANGED))
def test_a_change_inside_the_part_is_caught_even_when_the_file_is_signed_again(made, tmp_path, capsys, name):
    evidence = copy.deepcopy(made.ran.evidence)                # this case's own copy
    part = evidence["change_watch"]
    run = part["runs"][0]
    change = next(c for c in part["changes"] if c["branch"] == REVERT)
    test = next(t for t in run["tests"] if t["kind"] == "bad_signatures")
    listed = next(t for t in run["record"]["tests"] if t["kind"] == "bad_signatures")
    if name == "a run record changed":
        test["now"]["record"]["duration_ms"] += 1
    elif name == "a run record changed with its fingerprint":
        test["now"]["record"]["duration_ms"] += 1
        test["now"]["run_sha256"] = sha256_hex(test["now"]["record"])
    elif name == "the reviewer's word changed":
        run["review"]["status"] = "no_difference"
    elif name == "a test's placing changed":
        next(t for t in run["review"]["tests"] if t["kind"] == "bad_signatures")["outcome"] = "same"
    elif name == "the count of a placing changed":
        run["review"]["counts"].update(fails_now=0, same=1)
    elif name == "the watch record's line for a run changed":
        listed["now"]["code"] = "passed"
        _refit(run)
    elif name == "a test dropped from the watch record":
        run["record"]["tests"].pop()
        _refit(run)
    elif name == "the watch record of another change":
        run["record"]["change"]["head_commit"] = ZERO40
        _refit(run)
    elif name == "the watch record changed without its fingerprint":
        run["record"]["matches"] = None
    elif name == "the review names another watch record":
        run["review"]["record_sha256"] = ZERO64
    elif name == "the run on the change ran another commit":
        test["now"]["code"]["commit"] = ZERO40
    elif name == "the run on the change ran another program file":
        test["now"]["code"]["file_sha256"] = ZERO64
    elif name == "the run on the change ran another version":
        test["now"]["code"]["component_version"] = "1.4.3"
    elif name == "the run before ran another version":
        test["before"]["code"]["component_version"] = "1.4.2"
    elif name == "a run of another locked test":
        test["spec_hash"] = ZERO64
    elif name == "the change's status changed":
        change["status"].update(key="no_difference", word="No difference found")
    elif name == "the status word changed":
        change["status"]["word"] = "No difference found"
    elif name == "the change names a watch run that is not there":
        change["watch_run_id"] = 99
    elif name == "the change names a watch run of other code":
        change["head_commit"] = ZERO40
    elif name == "the part taken out":
        del evidence["change_watch"]
    elif name == "a check row with another fingerprint":
        next(c for c in evidence["checks"] if c["came_from"] == "Change watch")["runs"][0]["run_sha256"] = ZERO64
    elif name == "a check row for a run the part does not hold":
        next(c for c in evidence["checks"] if c["came_from"] == "Change watch")["runs"][0]["run_id"] = 9999
    elif name == "believed turned off":
        run["believed"] = False
    elif name == "the review taken out":
        run["review"], run["believed"] = None, None
    elif name == "a key added to the part":
        part["more"] = 1
    elif name == "the same watch run twice":
        part["runs"].append(copy.deepcopy(run))
    elif name == "the run left out of the change's entry":
        change.update(watch_run_id=None, run_covers_picked=None)
        change["status"].update(key="not_run", word="Not run yet", reason=None)
    elif name == "the run said to be of other tests":
        change["run_covers_picked"] = False
        change["status"].update(key="not_run", word="Not run yet", reason=None)
    elif name == "the count in the status word changed":
        change["status"]["word"] = "Passed before, fails now (9 tests)"
    elif name == "the run before put where the run on the change stands":
        # no run record and no test review is altered: the run on the code before stands in for the run on the change,
        # under the note of the run it replaces, and the watch record, its fingerprint, the review and the status are
        # made to fit
        kept_note = test["now"]["code"]
        test["now"] = copy.deepcopy(test["before"])
        test["now"]["code"] = kept_note
        listed["now"] = copy.deepcopy(listed["before"])
        again = verifier.word_for(run["record"])
        run["review"].update(status=again["status"], counts=again["counts"], tests=again["tests"])
        _refit(run)
        change["status"].update(key=again["status"], word=verifier.STATUS_WORDS[again["status"]])
    elif name == "a run record of another kind of run where the run on the change stands":
        test["now"]["record"]["phase"] = test["now"]["phase"] = "retest"
        test["now"]["run_sha256"] = test["now"]["review"]["run_sha256"] = listed["now"]["run_sha256"] = sha256_hex(test["now"]["record"])
        _refit(run)
    elif name == "the change's own version changed":
        change["gives"]["version"] = "1.4.3"
    elif name == "the change's own files changed":
        change["files"][0]["new_sha256"] = ZERO64
    elif name == "a not-trusted line with another result code":
        listed["now"].update(code="couldnt_run", reason_code=None, control_outcome="not_run")
        again = verifier.word_for(run["record"])
        run["review"].update(status=again["status"], counts=again["counts"], tests=again["tests"])
        _refit(run)
        change["status"].update(key=again["status"], word=verifier.STATUS_WORDS[again["status"]])
    elif name == "the review under another reviewer's name":
        run["review"]["reviewer"] = "isogeny.rule-reviewer/0"
    elif name == "the kind of run said beside a run changed":
        test["now"]["phase"] = "retest"
    elif name == "the watch record names another program":
        run["record"]["matches"]["name"] = "acme-kex"
        _refit(run)
    elif name == "the part is said to be about another program":
        part["program"]["name"] = "acme-kex"
    elif name == "the entry in Fixes for the change taken out":
        evidence["fixes"] = [f for f in evidence["fixes"] if f["source"]["kind"] != "developer_change"]
    elif name == "an entry in Fixes for a change that does not read so":
        other = next(c for c in part["changes"] if c["branch"] == TLS)
        entry = copy.deepcopy(next(f for f in evidence["fixes"] if f["source"]["kind"] == "developer_change"))
        entry["id"] = f"fix-{other['id']}"
        evidence["fixes"].append(entry)
    elif name == "a run that is also the test's own, with another fingerprint there":
        own = next(t for t in evidence["tests"] if t["kind"] == "bad_signatures")
        own["earlier_runs"].append({"run_id": test["now"]["run_id"], "run_sha256": ZERO64})
    code, said = _verify(made, sign_envelope(evidence, made.lab.settings.data_dir), tmp_path, capsys)
    assert code == 1 and said.startswith("Evidence NOT verified: ") and CHANGED[name] in said, said
    assert "Traceback" not in said


def test_a_run_the_app_did_not_believe_is_said_as_that_and_accepted_as_that(made, tmp_path, capsys):
    """The stored review no longer fits the records (a damaged database): the app reads the run as "Couldn't trust this
    run" and writes that into the file. The file is honest about it, so it verifies; it would not if it claimed the
    review's own word for the change."""
    evidence = copy.deepcopy(made.ran.evidence)
    part = evidence["change_watch"]
    run, change = part["runs"][0], next(c for c in part["changes"] if c["branch"] == REVERT)
    run["review"]["status"] = "no_difference"            # what a changed review row would hold
    run["believed"] = False
    assert _verify(made, sign_envelope(evidence, made.lab.settings.data_dir), tmp_path, capsys)[0] == 1     # the change still claims a word of the run
    change["status"].update(key="couldnt_trust", word="Couldn't trust this run")
    assert _verify(made, sign_envelope(evidence, made.lab.settings.data_dir), tmp_path, capsys)[0] == 1     # Fixes still lists an entry for it
    # (the app lists an entry in Fixes only while a change reads "Passed before, fails now": a file it makes in this state has none)
    evidence["fixes"] = [f for f in evidence["fixes"] if f["source"]["kind"] != "developer_change"]
    code, said = _verify(made, sign_envelope(evidence, made.lab.settings.data_dir), tmp_path, capsys)
    assert code == 0 and "Change watch: 2 changes, 1 run of the picked tests" in said
    # such a run is not counted among the reviewed ones, and the line says what it is
    assert "Change watch: 0 reviewed runs:" in said and "1 run more: the app did not believe the stored review when the file was made, and the file says so." in said


def test_a_stored_review_under_another_reviewers_name_is_not_believed_by_the_app_and_the_file_it_makes_verifies(made, tmp_path, capsys):
    """The app believes a stored review only if reviewing again gives exactly it, the reviewer's own name included. A
    row whose name differs (a damaged row, or a reviewer whose id has moved since) reads "Couldn't trust this run" in
    the app, and the file the app then makes says so. That file is honest and must verify (the second review of 6d
    found that it did not)."""
    from sqlalchemy import text as sql
    lab, plan = made.lab, made.plan
    with lab.db() as db:
        row = db.execute(sql("select id, reviewer from watch_reviews order by id limit 1")).first()
    # (watch_reviews is add-only: the row is changed with the triggers off, as a damaged file would be, and put back after)
    import sqlite3
    path = lab.settings.db_path
    def set_reviewer(value: str) -> None:
        raw = sqlite3.connect(path)
        try:
            triggers = raw.execute("select name, sql from sqlite_master where type = 'trigger' and tbl_name = 'watch_reviews'").fetchall()
            for trigger, _ in triggers:
                raw.execute(f'drop trigger "{trigger}"')
            raw.execute("update watch_reviews set reviewer = ? where id = ?", (value, row[0]))
            for _, made_by in triggers:
                raw.execute(made_by)
            raw.commit()
        finally:
            raw.close()
    set_reviewer("isogeny.rule-reviewer/0")
    try:
        download = _download(lab, plan)
        first = next(r for r in download.evidence["change_watch"]["runs"] if r["watch_run_id"] == row[0])
        assert first["believed"] is False and first["review"]["reviewer"] == "isogeny.rule-reviewer/0"
        code, said = _verify(made, download.raw, tmp_path, capsys)
        assert code == 0, said
    finally:
        set_reviewer(row[1])
    assert _verify(made, _download(lab, plan).raw, tmp_path, capsys)[0] == 0


# ---------------------------------------------------------------- the rule, written twice

def test_the_rule_written_out_for_the_verify_command_gives_what_the_reviewer_gives_for_every_combination():
    codes = ("passed", "failed", "measured", "no_slowdown", "slowdown", "couldnt_run", "couldnt_trust", None)
    controls = ("as_expected", "not_as_expected", "not_run")
    sides = [None] + [{"run_sha256": "a" * 64, "code": c, "reason_code": None, "control_outcome": o} for c in codes for o in controls]
    reviewer, seen = RuleReviewer(), set()
    for kind in ("bad_signatures", "speed_size"):
        for before, now in itertools.product(sides, sides):
            for matches in ({"name": "acme-sign", "version": "1.4.2"}, {"name": "acme-sign", "version": "1.4.3"}, None):
                record = {"schema": "isogeny.watch-run/1", "change": {"branch": "dev/x", "base_commit": "a" * 40, "head_commit": "b" * 40, "files": []},
                          "matches": matches, "version": "1.4.2", "base_version": "1.4.3",
                          "tests": [{"item_id": 1, "kind": kind, "spec_hash": "c" * 64, "before": before, "now": now},
                                    {"item_id": 2, "kind": "bad_signatures", "spec_hash": "d" * 64, "before": sides[1], "now": sides[1]}]}
                theirs, ours = reviewer.review_watch(record), verifier.word_for(record)
                assert {k: theirs[k] for k in ("status", "code_is_ours", "counts", "tests")} == ours
                seen.add((theirs["status"], theirs["tests"][0]["outcome"]))
    assert {status for status, _ in seen} == set(verifier.STATUS_WORDS) - {"not_run", "running", "nothing_to_run"}
    assert {outcome for _, outcome in seen} == set(verifier.OUTCOMES)
    # with no test at all a watch run can't be compared
    empty = {"schema": "isogeny.watch-run/1", "matches": {"name": "a", "version": "1"}, "version": "1", "base_version": "0", "tests": []}
    assert verifier.word_for(empty)["status"] == reviewer.review_watch(empty)["status"] == "cant_run"


def test_the_words_the_verify_command_knows_are_the_apps_own():
    from app.engine import reviewer
    from app.present import changewatch as words
    assert verifier.STATUS_WORDS == words.STATUS_WORDS and verifier.SCHEMA == CHANGE_WATCH_SCHEMA
    assert (verifier.WATCH_SCHEMA, verifier.REVIEW_SCHEMA) == (reviewer.WATCH_SCHEMA, reviewer.WATCH_REVIEW_SCHEMA)
    assert (verifier.FAIL_CODES, verifier.NO_RESULT_CODES, verifier.SPEED_KIND) == (reviewer.WATCH_FAIL_CODES, reviewer.WATCH_NO_RESULT_CODES, reviewer.SPEED_KIND)
    from app.ledger.checks import ORIGINS
    assert verifier.CAME_FROM == ORIGINS["watch"]


# ---------------------------------------------------------------- damaged copies of the part

def test_damaged_copies_of_the_part_are_checked_or_refused_plainly_within_a_time_limit(made, tmp_path, capsys):
    rng = random.Random(20261123)
    outcomes = {"holds": 0, "refused": 0}
    for n in range(400):
        evidence = copy.deepcopy(made.later.evidence if n % 2 else made.ran.evidence)
        evidence["change_watch"] = _damage_json(rng, evidence["change_watch"])
        try:
            canonical_bytes(evidence)
        except (ValueError, TypeError):
            continue                                   # (a value no file can hold: the file's own reader refuses it first)
        start = time.monotonic()
        outcome = verifier.check_change_watch(evidence)
        assert time.monotonic() - start < 2.0
        if outcome.ok:
            outcomes["holds"] += 1
            assert outcome.problem is None and len(outcome.lines) == 2
        else:
            outcomes["refused"] += 1
            assert outcome.problem and "Traceback" not in outcome.problem and len(outcome.problem) < 400 and outcome.problem.isprintable()
    assert outcomes["refused"] > 100 and outcomes["holds"] >= 1, outcomes
    # a few of them through the whole command, signed again: it ends with 0 or 1 and one plain line
    for _ in range(8):
        evidence = copy.deepcopy(made.ran.evidence)
        evidence["change_watch"] = _damage_json(rng, evidence["change_watch"])
        try:
            raw = sign_envelope(evidence, made.lab.settings.data_dir)
        except (ValueError, TypeError):
            continue
        code, said = _verify(made, raw, tmp_path, capsys)
        assert code in (0, 1) and "Traceback" not in said
        assert said.startswith("Evidence verified" if code == 0 else "Evidence NOT verified: the Change watch part: ")
    # the part as something else entirely
    for odd in (None, [], "x", 7, {"schema": CHANGE_WATCH_SCHEMA}, {"schema": "other"}):
        evidence = {**made.ran.evidence, "change_watch": odd}
        assert verifier.check_change_watch(evidence).ok is False


def test_a_change_that_names_an_older_run_of_its_code_is_caught(made, tmp_path, capsys):
    """Three runs of the same code are in the later file: two reviewed, then one that was cut off. The newest one counts.
    A file whose change names an earlier run and takes that run's word verified before the second review of 6d."""
    evidence = copy.deepcopy(made.later.evidence)
    part = evidence["change_watch"]
    first = part["runs"][0]
    change = next(c for c in part["changes"] if c["branch"] == REVERT)
    change.update(watch_run_id=first["watch_run_id"], run_covers_picked=True)
    change["status"].update(key="passed_before_fails_now", word="Passed before, fails now (1 test)", reason="1 test passed on the code before and fails on this change.")
    code, said = _verify(made, sign_envelope(evidence, made.lab.settings.data_dir), tmp_path, capsys)
    assert code == 1 and "does not name the newest watch run of its code that the file holds" in said
