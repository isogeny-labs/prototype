"""The Change watch part of an evidence file (phase 6d), checked after the file's own signature held.

A watch run is the set of test runs made for one developer's change, on a person's click. For every watch run the
file holds, in order:
  1. both runs of every picked test are in the part in full. Each run record matches its fingerprint, its review is
     of that record, and both are of the locked test the watch run names;
  2. each run ran on the change's code, by the run record itself and by the note kept beside it: the record of the
     run on the change is a run made for a change (phase "watch") of the program and version the watch run names, the
     note says the same program and version, the head commit of the change's branch, and the program file has the
     fingerprint the change's own file list gives it (after the change for the run on the change, before it for the
     run it is compared with);
  3. the watch record is exactly what those runs give, and matches its fingerprint and the fingerprint the review of
     the watch run names;
  4. the reviewer's word for the change follows from the watch record by the rule. The rule is written out again
     here, apart from the app's reviewer, so the file is not checked with the code that made it.
Then, across the file:
  5. each change names the newest watch run of exactly its code that the file holds (or none, where there is none);
     that run is of the change's own files and versions; whether the run is of the tests picked now is worked out
     again from the two lists; the change's status is the one that run gives it; and its status word is the word of
     that status, with the count the run's review gives;
  6. every run that the file's list of checks says came from Change watch is a run of this part, with the same
     fingerprint; and a run of this part that the file also holds elsewhere has the same fingerprint there.

A file whose list of checks names a Change watch run and that has no Change watch part fails.

A run the app itself did not believe when the file was made (its stored review no longer matched its records, or
was not made by the reviewer the file names) is said as that in the file, and is accepted as that: the file is honest
about it, and the change then reads "Couldn't trust this run".

This module reads the file as data only. Nothing the file names is run, and no repository is opened: whether the
change's code was byte for byte a registered demo program is a fact the app established and wrote into the watch
record ("matches"); the check here is that everything in the file agrees with it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.canonical import canonical_bytes

SCHEMA = "isogeny.change-watch/1"
WATCH_SCHEMA = "isogeny.watch-run/1"
REVIEW_SCHEMA = "isogeny.watch-review/1"
CAME_FROM = "Change watch"                       # what the file's list of checks says of a run made for a change
FAIL_CODES = ("failed", "slowdown")
NO_RESULT_CODES = ("couldnt_run", "couldnt_trust")
SPEED_KIND = "speed_size"
OUTCOMES = ("not_trusted", "not_compared", "fails_now", "passes_now", "same", "slower_now", "not_slower")
# the word of each status of a change (the count in brackets that two of them carry comes after it)
STATUS_WORDS = {"not_run": "Not run yet", "running": "Running", "no_difference": "No difference found",
                "passed_before_fails_now": "Passed before, fails now", "failed_before_passes_now": "Failed before, passes now",
                "nothing_to_run": "Nothing to run", "cant_run": "Can't run", "couldnt_trust": "Couldn't trust this run"}
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_HEX40 = re.compile(r"\A[0-9a-f]{40}\Z")
MAX_RUNS, MAX_TESTS, MAX_CHANGES = 2000, 500, 500


@dataclass
class WatchOutcome:
    ok: bool
    problem: str | None = None
    lines: list[str] = field(default_factory=list)


class _Failed(Exception):
    """The part does not hold; the message says what, in one plain sentence."""


def _plain(value: object, limit: int = 80) -> str:
    """Text from the file, made safe to print: plain printable characters only, and not too long."""
    text = "".join(ch if ch.isprintable() and ch not in "\x1b‮‭⁦⁧⁨⁩" else "?" for ch in str(value))
    return text if len(text) <= limit else text[:limit] + "..."


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _same(a: object, b: object) -> bool:
    try:
        return canonical_bytes(a) == canonical_bytes(b)
    except (ValueError, TypeError, RecursionError):
        return False


def _need(condition: bool, problem: str) -> None:
    if not condition:
        raise _Failed(problem)


def _is_list_of_dicts(value: object, most: int) -> bool:
    return isinstance(value, list) and len(value) <= most and all(isinstance(v, dict) for v in value)


def needs_change_watch_part(evidence: object) -> bool:
    """Does the file's list of checks name a run made for a developer's change? Such a file always has the part."""
    checks = evidence.get("checks") if isinstance(evidence, dict) else None
    return isinstance(checks, list) and any(isinstance(c, dict) and _from_change_watch(c) for c in checks)


def _from_change_watch(check: dict) -> bool:
    name = check.get("check")
    return check.get("came_from") == CAME_FROM or (isinstance(name, str) and name.startswith(("watch-", "watchbase-")))


# ---------------------------------------------------------------- the rule, written out again

def place(test: dict) -> str:
    """Where one picked test stands, from its two sides in the watch record. The first that applies:
    not trusted (a side reads "Couldn't trust this run", or reached a result with a control that did not behave as
    expected); not compared (a side is missing or could not run); fails now; passes now; the same. The speed test is
    placed by its run on the change alone, which timed the change side by side with the code before."""
    before, now = test.get("before"), test.get("now")
    timed = test.get("kind") == SPEED_KIND
    sides = [s for s in ((now,) if timed else (before, now)) if isinstance(s, dict)]

    def control_held(side: dict) -> bool:
        return side.get("code") == "couldnt_run" or side.get("control_outcome") == "as_expected"
    if any(s.get("code") == "couldnt_trust" or not control_held(s) for s in sides):
        return "not_trusted"
    if len(sides) < (1 if timed else 2) or any(s.get("code") in NO_RESULT_CODES or not s.get("code") for s in sides):
        return "not_compared"
    if timed:
        return "slower_now" if now.get("code") == "slowdown" else "not_slower"       # type: ignore[union-attr]
    failed_before, fails_now = before.get("code") in FAIL_CODES, now.get("code") in FAIL_CODES       # type: ignore[union-attr]
    if fails_now and not failed_before:
        return "fails_now"
    if failed_before and not fails_now:
        return "passes_now"
    return "same"


def word_for(record: dict) -> dict:
    """The reviewer's word for the change, from the watch record alone: the status, whether the code was ours, the
    count of each placing and each test's placing."""
    tests = []
    for test in record.get("tests") or []:
        before, now = test.get("before"), test.get("now")
        tests.append({"item_id": test.get("item_id"), "kind": test.get("kind"), "outcome": place(test),
                      "before": before.get("code") if isinstance(before, dict) else None,
                      "now": now.get("code") if isinstance(now, dict) else None})
    counts = {name: sum(1 for t in tests if t["outcome"] == name) for name in OUTCOMES}
    matches = record.get("matches")
    ours = isinstance(matches, dict) and bool(matches.get("name")) and bool(matches.get("version")) and matches.get("version") == record.get("version")
    if not ours or counts["not_trusted"]:
        status = "couldnt_trust"
    elif not tests or counts["not_compared"]:
        status = "cant_run"
    elif counts["fails_now"] or counts["slower_now"]:
        status = "passed_before_fails_now"
    elif counts["passes_now"]:
        status = "failed_before_passes_now"
    else:
        status = "no_difference"
    return {"status": status, "code_is_ours": bool(ours), "counts": {"tests": len(tests), **counts}, "tests": tests}


# ---------------------------------------------------------------- one run of one test

def _side(entry: object, spec_hash: object, what: str) -> dict:
    """One run as the part holds it in full. Returns what the watch record may hold for it: {"stands": the side as the
    record holds a run whose review stands, "fingerprint": its record's fingerprint}."""
    _need(isinstance(entry, dict), f"{what} is not written as this app writes a run.")
    assert isinstance(entry, dict)
    record, review, fingerprint = entry.get("record"), entry.get("review"), entry.get("run_sha256")
    _need(isinstance(record, dict) and isinstance(review, dict) and isinstance(fingerprint, str) and bool(_HEX64.match(fingerprint)),
          f"{what} is not written as this app writes a run.")
    assert isinstance(record, dict) and isinstance(review, dict)
    _need(_sha(record) == fingerprint, f"{what}: the run record does not match its fingerprint.")
    _need(record.get("spec_hash") == spec_hash and review.get("spec_hash") == spec_hash,
          f"{what} is not a run of the locked test this watch run names.")
    _need(entry.get("phase") == record.get("phase"), f"{what}: the kind of run it is said to be is not the one its run record names.")
    verdict, control = review.get("verdict"), review.get("control")
    _need(isinstance(verdict, dict) and isinstance(control, dict), f"{what}: its review is not written as this app writes one.")
    assert isinstance(verdict, dict) and isinstance(control, dict)
    stands = None
    if review.get("run_sha256") == fingerprint:
        stands = {"run_sha256": fingerprint, "code": verdict.get("code"), "reason_code": verdict.get("reason_code"),
                  "control_outcome": control.get("outcome")}
    return {"stands": stands, "fingerprint": fingerprint, "code": entry.get("code"), "run_id": entry.get("run_id"),
            "phase": record.get("phase"), "component": record.get("component")}


def _side_in_record(side: dict, in_record: object, what: str) -> None:
    """The watch record's line for one run is that run: its review as it stands, or, where the app did not trust the
    stored run when it read it, the line that says so (no reason, the control as not run)."""
    _need(isinstance(in_record, dict) and in_record.get("run_sha256") == side["fingerprint"],
          f"{what}: the watch record names another run than the one in the file.")
    assert isinstance(in_record, dict)
    if side["stands"] is not None and _same(in_record, side["stands"]):
        return
    # (the app writes exactly one such line: the result code "Couldn't trust this run", no reason, the control as not run)
    not_trusted = (set(in_record) == {"run_sha256", "code", "reason_code", "control_outcome"} and in_record.get("code") == "couldnt_trust"
                   and in_record.get("reason_code") is None and in_record.get("control_outcome") == "not_run")
    _need(not_trusted, f"{what}: the watch record does not say what the run's review says.")


def _ran_on(side: dict, run: dict, which: str, made_here: bool, what: str) -> None:
    """The code a run ran on is the change's: the program, the version, the commit and the fingerprint of the file."""
    code = side["code"]
    _need(isinstance(code, dict), f"{what}: the file does not say which code it ran on.")
    assert isinstance(code, dict)
    version = run.get("version") if which == "now" else run.get("base_version")
    # the run record itself: which program and version ran, and what the run was made for
    ran = side["component"]
    _need(isinstance(ran, dict) and ran.get("version") == version and bool(ran.get("name")),
          f"{what}: its run record is not of version {_plain(version)}, the one this watch run names.")
    assert isinstance(ran, dict)
    made_for = "watch" if which == "now" else "watch_base" if made_here else None
    _need(made_for is None or side["phase"] == made_for, f"{what}: its run record is not a run made for this change.")
    _need(side["phase"] in ("first", "retest", "proof", "watch", "watch_base"), f"{what}: its run record is of no kind of run this app makes.")
    # the note kept beside the run says the same program and version as the record
    _need(code.get("component_name") == ran.get("name") and code.get("component_version") == ran.get("version"),
          f"{what}: the code it is said to have run on is not the code its run record names.")
    _need(code.get("component_version") == version, f"{what} did not run on version {_plain(version)}, the one this watch run names.")
    wanted = {f.get("new_sha256" if which == "now" else "old_sha256") for f in run["files"]} - {None}
    _need(code.get("file_sha256") in wanted, f"{what}: the program that ran does not have the fingerprint the change's file list gives.")
    if which == "now" or made_here:
        commit = run.get("head_commit") if which == "now" else run.get("base_commit")
        _need(code.get("source") == "repository" and code.get("branch") == run.get("branch") and code.get("commit") == commit,
              f"{what} did not run on the commit this watch run names.")


# ---------------------------------------------------------------- one watch run

def _check_run(run: dict, reviewer: object) -> dict:
    """One watch run. Returns {"reviewed": the status it gives the change (None while it has no review), "sides": the
    runs it holds as (run id, fingerprint, is it a run on the change or one made here for the code before?)}."""
    name = f"watch run {_plain(run.get('watch_run_id'))}"
    _need(isinstance(run.get("watch_run_id"), int) and not isinstance(run.get("watch_run_id"), bool), "a watch run has no number.")
    for key in ("branch", "version", "base_version"):
        _need(isinstance(run.get(key), str) and bool(run.get(key)), f"{name} does not name its {key.replace('_', ' ')}.")
    for key in ("base_commit", "head_commit"):
        _need(isinstance(run.get(key), str) and bool(_HEX40.match(run[key])), f"{name} does not name its {key.replace('_', ' ')}.")
    _need(_is_list_of_dicts(run.get("files"), 500) and _is_list_of_dicts(run.get("tests"), MAX_TESTS), f"{name} is not written as this app writes one.")
    sides, in_record, whole = [], [], bool(run["tests"])
    for test in run["tests"]:
        about = f"{name}, test {_plain(test.get('item_id'))}"
        made_here = test.get("before_made_here") is True
        line: dict = {"item_id": test.get("item_id"), "kind": test.get("kind"), "spec_hash": test.get("spec_hash")}
        for which, label in (("before", "the run on the code before"), ("now", "the run on the change")):
            if test.get(which) is None:
                whole = False
                line[which] = None
                continue
            side = _side(test[which], test.get("spec_hash"), f"{about}, {label}")
            _ran_on(side, run, which, made_here, f"{about}, {label}")
            line[which] = side
            sides.append({"run_id": side["run_id"], "run_sha256": side["fingerprint"], "of_this_run": which == "now" or made_here,
                          "base": which == "before"})
        in_record.append(line)
    record, review, believed = run.get("record"), run.get("review"), run.get("believed")
    if not whole:
        _need(record is None and review is None and believed is None, f"{name} is not finished, and still carries a record or a review.")
        return {"reviewed": None, "believed": None, "counts": None, "sides": sides}
    _need(isinstance(record, dict), f"{name} has every run and no watch record.")
    assert isinstance(record, dict)
    _need(run.get("record_sha256") == _sha(record), f"{name}: the watch record does not match its fingerprint.")
    # the watch record is exactly what the watch run and its runs give
    _need(record.get("schema") == WATCH_SCHEMA and set(record) == {"schema", "change", "matches", "version", "base_version", "tests"},
          f"{name}: the watch record is not written as this app writes one.")
    _need(_same(record.get("change"), {"branch": run["branch"], "base_commit": run["base_commit"], "head_commit": run["head_commit"], "files": run["files"]})
          and record.get("version") == run["version"] and record.get("base_version") == run["base_version"],
          f"{name}: the watch record is of another change than the one the watch run names.")
    listed = record.get("tests")
    _need(isinstance(listed, list) and _is_list_of_dicts(listed, MAX_TESTS) and len(listed) == len(in_record),
          f"{name}: the watch record does not list the tests of the watch run.")
    assert isinstance(listed, list)
    for line, written in zip(in_record, listed, strict=True):
        about = f"{name}, test {_plain(line['item_id'])}"
        _need(set(written) == {"item_id", "kind", "spec_hash", "before", "now"} and
              all(written.get(k) == line[k] for k in ("item_id", "kind", "spec_hash")), f"{about}: the watch record names another test.")
        for which in ("before", "now"):
            _side_in_record(line[which], written.get(which), f"{about}")
    matches = record.get("matches")
    _need(matches is None or (isinstance(matches, dict) and set(matches) == {"name", "version"}), f"{name}: the watch record is not written as this app writes one.")
    # the program the app found the change's code to be is the program whose runs these are
    programs = {(line[which]["component"] or {}).get("name") for line in in_record for which in ("before", "now")}
    _need(len(programs) == 1 and (matches is None or matches.get("name") in programs),
          f"{name}: its runs are not all of the one program the watch record names.")
    if review is None:
        _need(believed is None, f"{name} has no review, and the file says whether its review was believed.")
        return {"reviewed": None, "believed": None, "counts": None, "sides": sides}
    _need(isinstance(review, dict) and isinstance(believed, bool), f"{name}: its review is not written as this app writes one.")
    assert isinstance(review, dict)
    again = word_for(record)
    # (the app believes a stored review only if reviewing again gives exactly it, the reviewer's own name included; the
    #  file names its reviewer in "app")
    holds = (review.get("schema") == REVIEW_SCHEMA and review.get("record_sha256") == run["record_sha256"]
             and review.get("status") == again["status"] and review.get("code_is_ours") == again["code_is_ours"]
             and _same(review.get("counts"), again["counts"]) and _same(review.get("tests"), again["tests"])
             and isinstance(reviewer, str) and review.get("reviewer") == reviewer)
    if believed:
        _need(review.get("record_sha256") == run["record_sha256"], f"{name}: its review is of another watch record than the one in the file.")
        _need(isinstance(reviewer, str) and review.get("reviewer") == reviewer, f"{name}: its review was not made by the reviewer this file names.")
        _need(holds, f"{name}: the reviewer's word for the change ({_plain(review.get('status'))}) does not follow from the runs in the file "
                     f"(they give {again['status']}).")
        return {"reviewed": again["status"], "believed": True, "counts": again["counts"], "sides": sides}
    _need(not holds, f"{name}: the file says its review was not believed, and the review matches the runs in the file.")
    return {"reviewed": "couldnt_trust", "believed": False, "counts": None, "sides": sides}


# ---------------------------------------------------------------- the part

def _check_change(change: dict, runs: dict[int, dict], checked: dict[int, dict]) -> None:
    name = f"the change on {_plain(change.get('branch'))}"
    status = change.get("status")
    _need(isinstance(status, dict) and status.get("key") in STATUS_WORDS and isinstance(status.get("word"), str),
          f"{name} has no status this app writes.")
    assert isinstance(status, dict)
    key, word = status["key"], status["word"]
    _need(_is_list_of_dicts(change.get("picked"), MAX_TESTS), f"{name} is not written as this app writes one.")
    # where the change stands before any run is looked at
    if change.get("problem") is not None:
        resting = "cant_run"
    elif not change["picked"]:
        resting = "nothing_to_run"
    else:
        resting = "not_run" if change.get("gives") is not None and change.get("starts_from") is not None else "cant_run"
    # the run that counts for a change is the newest one of exactly its code: the same branch, head commit and base commit
    code = (change.get("branch"), change.get("head_commit"), change.get("base_commit"))
    of_this_code = [n for n, run in runs.items() if (run.get("branch"), run.get("head_commit"), run.get("base_commit")) == code]
    newest = max(of_this_code) if of_this_code and change.get("problem") is None else None
    number = change.get("watch_run_id")
    if number is not None:
        _need(isinstance(number, int) and not isinstance(number, bool) and number in runs, f"{name} names a watch run that is not in the file.")
        _need(number in of_this_code, f"{name} names a watch run of other code.")
    _need(number == newest, f"{name} does not name the newest watch run of its code that the file holds.")
    if newest is None:
        _need(key == resting and word == STATUS_WORDS[key], f"{name} has no watch run, and its status is not the one a change has before a run.")
        return
    run = runs[newest]
    # that run is a run of this change: its files, and the versions its code is and starts from
    _need(_same(change.get("files"), run.get("files"))
          and (change.get("gives") or {}).get("version") == run.get("version")
          and (change.get("starts_from") or {}).get("version") == run.get("base_version"),
          f"{name}: its files or versions are not the ones its watch run was made for.")
    # is the run of exactly the tests picked now? Worked out again from the two lists, not taken from the file's word
    covers = ({(t.get("item_id"), t.get("spec_hash")) for t in run["tests"]}
              == {(t.get("item_id"), t.get("spec_hash")) for t in change["picked"]})
    _need(change.get("run_covers_picked") is covers, f"{name}: whether its watch run is of the tests picked now is not what the two lists show.")
    result = checked[newest]
    reviewed = result["reviewed"]
    if reviewed is None or not covers or resting != "not_run":
        # no review yet, or a run of other tests than the ones picked now: the run does not set the status
        _need(key == resting and word == STATUS_WORDS[key], f"{name}: its status is not the one a change has while its watch run does not count.")
        return
    _need(key == reviewed, f"{name}: its status ({_plain(key)}) is not the one its watch run gives ({reviewed}).")
    # the word of that status, with the count the run's own review gives
    counts = result["counts"] or {}
    n = {"passed_before_fails_now": counts.get("fails_now", 0) + counts.get("slower_now", 0),
         "failed_before_passes_now": counts.get("passes_now", 0)}.get(key)
    wanted = STATUS_WORDS[key] if n is None else f"{STATUS_WORDS[key]} ({n} {'test' if n == 1 else 'tests'})"
    _need(word == wanted, f"{name}: its status word is not the word of its status ({wanted}).")


def _elsewhere(evidence: dict) -> tuple[dict[int, str], list[tuple[int, str]]]:
    """The fingerprints the rest of the file gives for runs of tests: (every run of a locked test by its number, the
    runs the list of checks says came from Change watch)."""
    known: dict[int, str] = {}
    from_watch: list[tuple[int, str]] = []
    for test in evidence.get("tests") or []:
        if not isinstance(test, dict):
            continue
        for entry in [*(test.get("runs") or []), *(test.get("earlier_runs") or [])]:
            if isinstance(entry, dict) and isinstance(entry.get("run_id"), int) and isinstance(entry.get("run_sha256"), str):
                known[entry["run_id"]] = entry["run_sha256"]
    for check in evidence.get("checks") or []:
        if not isinstance(check, dict) or not _from_change_watch(check):
            continue
        for entry in check.get("runs") or []:
            _need(isinstance(entry, dict) and isinstance(entry.get("run_id"), int) and isinstance(entry.get("run_sha256"), str),
                  "the list of checks has a Change watch run without its number or its fingerprint.")
            from_watch.append((entry["run_id"], entry["run_sha256"]))
    return known, from_watch


def _check(evidence: dict) -> list[str]:
    part = evidence.get("change_watch")
    _need(isinstance(part, dict) and part.get("schema") == SCHEMA, "it is not written as this app writes it.")
    assert isinstance(part, dict)
    _need(set(part) == {"schema", "note", "repository", "program", "changes", "runs"}, "it is not written as this app writes it.")
    _need(_is_list_of_dicts(part["runs"], MAX_RUNS) and _is_list_of_dicts(part["changes"], MAX_CHANGES), "it is not written as this app writes it.")
    runs: dict[int, dict] = {}
    checked: dict[int, dict] = {}
    app = evidence.get("app")
    reviewer = app.get("reviewed_by") if isinstance(app, dict) else None
    for run in part["runs"]:
        result = _check_run(run, reviewer)
        _need(run["watch_run_id"] not in runs, f"watch run {run['watch_run_id']} is in the file twice.")
        runs[run["watch_run_id"]], checked[run["watch_run_id"]] = run, result
    for change in part["changes"]:
        _check_change(change, runs, checked)
    # the program of the part is the program whose runs these are
    program = part.get("program")
    for run in part["runs"]:
        for test in run["tests"]:
            for which in ("before", "now"):
                ran = ((test.get(which) or {}).get("record") or {}).get("component") or {}
                _need(test.get(which) is None or (isinstance(program, dict) and ran.get("name") == program.get("name")),
                      f"watch run {run['watch_run_id']} holds a run of another program than the one this part is about.")
    # a change that makes passing tests fail has its entry in the file's list of fixes, text only; and no entry there
    # is for a change that does not read so
    fixes = {f.get("id"): f for f in evidence.get("fixes") or [] if isinstance(f, dict)}
    failing = {f"fix-{c.get('id')}" for c in part["changes"] if (c.get("status") or {}).get("key") == "passed_before_fails_now"}
    for wanted in sorted(failing):
        _need(wanted in fixes and fixes[wanted].get("status") == "Text only" and (fixes[wanted].get("source") or {}).get("kind") == "developer_change",
              "a change reads “Passed before, fails now”, and the file's list of fixes has no text-only entry for it.")
    for fix_id, fix in fixes.items():
        if (fix.get("source") or {}).get("kind") == "developer_change" or str(fix_id).startswith("fix-change-"):
            _need(fix_id in failing, "the file's list of fixes has an entry for a developer's change that does not read “Passed before, fails now”.")
    # across the file
    in_part: dict[int, str] = {}
    of_a_watch_run: dict[int, str] = {}
    for result in checked.values():
        for side in result["sides"]:
            _need(isinstance(side["run_id"], int), "a run of a watch run has no number.")
            _need(in_part.setdefault(side["run_id"], side["run_sha256"]) == side["run_sha256"], f"run {side['run_id']} is in the part with two fingerprints.")
            if side["of_this_run"]:
                of_a_watch_run[side["run_id"]] = side["run_sha256"]
    known, from_watch = _elsewhere(evidence)
    for number, fingerprint in from_watch:
        _need(of_a_watch_run.get(number) == fingerprint,
              f"the list of checks names run {number} as made for a developer's change, and the part does not hold that run with that fingerprint.")
    for number, fingerprint in in_part.items():
        _need(known.get(number, fingerprint) == fingerprint, f"run {number} has another fingerprint in the file's own tests.")
    reviewed = sum(1 for result in checked.values() if result["believed"] is True)
    not_believed = sum(1 for result in checked.values() if result["believed"] is False)
    test_runs = sum(len(result["sides"]) for result in checked.values())

    def count(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"
    return [f"{count(len(part['changes']), 'change', 'changes')}, {count(len(runs), 'run of the picked tests', 'runs of the picked tests')} "
            f"({count(test_runs, 'test run', 'test runs')}): each run matches its fingerprint and ran on the change's code.",
            f"{count(reviewed, 'reviewed run', 'reviewed runs')}: the watch record is what the runs give, and the reviewer's word for the change follows from it."
            + (f" {count(not_believed, 'run', 'runs')} more: the app did not believe the stored review when the file was made, and the "
               "file says so." if not_believed else "")]


def check_change_watch(evidence: dict) -> WatchOutcome:
    """Check the Change watch part of a file whose own signature was already checked."""
    try:
        return WatchOutcome(True, None, _check(evidence))
    except _Failed as failed:
        return WatchOutcome(False, str(failed))
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return WatchOutcome(False, "it is not written as this app writes it.")
