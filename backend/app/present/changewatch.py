"""The words of Change watch (phase 6d). It decides nothing: it turns what `app/changewatch/state.py` read, and what
the reviewer's rule for a watch run said, into plain sentences. A status word is the change's, never a test result; a
flag is something to look at, never a result.
"""

from __future__ import annotations

from datetime import datetime

from app.changewatch.flags import NOT_TESTED
from app.present import times

TITLE = "Change watch"
SUBLINE = (
    "A developer's change in the connected demo repository, the tests picked for it, and what they show once you run them. "
    "Nothing runs by itself."
)
NOT_CONNECTED = "Connect the demo code first. Connect demo code is on Fixes."
NO_CODE = "This assessment has no code that can be connected, so no developer's change can come in here."
UNREADABLE = "The connected repository could not be read, so its changes are not listed."
EMPTY = "No developer's change is in the connected repository yet. Bring in a demo change adds one, and runs nothing."
MENU_BUTTON = "Bring in a demo change"
MENU_NOTE = (
    "Adds the chosen change to this assessment's own copy of the demo repository, as a push would: one branch with one commit by "
    "“Demo developer”. It runs nothing."
)
MENU_BLOCKED = {
    "not_connected": "Connect the demo code first.",
    "no_code": NO_CODE,
    "already_in": "Already in the repository.",
    "needs_merge": "Offered once a fix is merged: it undoes that fix.",
}
RUN_FIRST, RUN_AGAIN = "Run the picked tests", "Run again"
FLAG_TITLE = "Old cryptography is named in the change"
FLAGS_NOTE = "A flag is something to look at. It is never a result."

STATUS_WORDS = {
    "not_run": "Not run yet",
    "running": "Running",
    "no_difference": "No difference found",
    "passed_before_fails_now": "Passed before, fails now",
    "failed_before_passes_now": "Failed before, passes now",
    "nothing_to_run": "Nothing to run",
    "cant_run": "Can't run",
    "couldnt_trust": "Couldn't trust this run",
}
STATUS_TONES = {
    "not_run": "neutral",
    "running": "neutral",
    "no_difference": "neutral",
    "passed_before_fails_now": "fail",
    "failed_before_passes_now": "pass",
    "nothing_to_run": "neutral",
    "cant_run": "neutral",
    "couldnt_trust": "warn",
}
OUTCOME_WORDS = {
    "fails_now": "Passed before, fails now",
    "passes_now": "Failed before, passes now",
    "same": "No difference found",
    "slower_now": "Slower than the code before",
    "not_slower": "No slowdown against the code before",
    "not_compared": "Not compared: a run could not run",
    "not_trusted": "Not compared: a run can't be trusted",
}
FILE_WORDS = {"added": "Added", "changed": "Changed", "removed": "Removed"}
NOT_OURS = "The changed code is not the same as one of our registered demo programs, so nothing of it runs."
BASE_NOT_OURS = (
    "The code this change starts from is not one of our registered demo programs, so there is nothing to compare with."
)
PROBLEMS = {
    "no_start": "This branch does not start from the connected branch, so it can't be compared with it.",
    "unreadable": "This branch could not be read from the repository.",
}
NOTHING_PICKED = "This change edits no file of a program under test, so no test is picked."


def nothing_picked(change: dict, program: dict) -> str:
    """Why no test is picked: the change touches no program file, or it does and no test of the plan runs that program."""
    if change.get("touches_program"):
        return f"This change edits {program.get('file') or 'the program'}, but no test of the plan runs {program['name']}, so no test is picked."
    return NOTHING_PICKED


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def when_words(value: str | None) -> str | None:
    """A moment as a sentence part: marked for a browser, UTC words for a file."""
    when = times.instant(value)
    if when is None or not isinstance(when, datetime):
        return None
    return times.written(when, f"{when.day} {when.strftime('%B %Y')}, {when.strftime('%H:%M')} UTC")


def short_commit(sha: str | None) -> str:
    return (sha or "")[:7]


def pick_reason(test: dict, program: dict) -> str:
    """Why a test is picked, or not: one sentence for the rule that placed it."""
    name, file = program["name"], program.get("file") or "its file"
    rule = test["rule"]
    if rule == "runs_the_program":
        return f"Runs {name}, and this change edits {file}."
    if rule == "program_not_touched":
        return f"Runs {name}, and this change does not edit {file}."
    if rule == "other_program":
        return f"Runs {test.get('other') or 'another program'}, which this change does not touch."
    if rule == "server_test":
        return f"Tests the server {test.get('server')}. It does not run {name}."
    return "Runs no program of this file."


def file_view(file: dict) -> dict:
    counts = None
    if file["text"]:
        parts = ([_count(file["added"], "line") + " added"] if file["added"] else []) + (
            [_count(file["removed"], "line") + " removed"] if file["removed"] else []
        )
        counts = ", ".join(parts) or "No line changed"
    return {
        "name": file["name"],
        "what": FILE_WORDS[file["state"]],
        "counts": counts,
        "is_program": file["is_program"],
        "note": None if file["text"] else "This file is not text, or is very large, so its lines are not shown.",
        "blocks": file["blocks"],
    }


def flag_view(flag: dict) -> dict:
    return {
        "title": FLAG_TITLE,
        "text": f"{flag['file']}, line {flag['line']}: “{flag['text']}” names {flag['word']}.",
        "note": NOT_TESTED,
        "source": flag["source"],
    }


def status_view(change: dict, program: dict | None = None) -> dict:
    """The change's status word, with one sentence under it that says why."""
    key = change["status"]
    run, review = change.get("run"), (change.get("run") or {}).get("review")
    counts = (review or {}).get("counts") or {}
    word, reason = STATUS_WORDS[key], None
    if key == "running" and run is not None:
        reason = f"{run['finished']} of {_count(run['total'], 'test')} {'has' if run['total'] == 1 else 'have'} run."
    elif key == "passed_before_fails_now":
        n, slower = counts.get("fails_now", 0), counts.get("slower_now", 0)
        word = f"{word} ({_count(n + slower, 'test')})"
        parts = (
            [f"{_count(n, 'test')} passed on the code before and {'fails' if n == 1 else 'fail'} on this change."]
            if n
            else []
        )
        # (the speed test's run on the change times it side by side with the code before: the reviewer's own word for that run)
        parts += (
            ["The speed test reads “Slowdown found” on this change, timed against the code before."] if slower else []
        )
        reason = " ".join(parts)
    elif key == "failed_before_passes_now":
        n = counts.get("passes_now", 0)
        word = f"{word} ({_count(n, 'test')})"
        reason = f"{_count(n, 'test')} failed on the code before and {'passes' if n == 1 else 'pass'} on this change."
    elif key == "no_difference":
        reason = "No picked test that passed on the code before fails on this change, and none that failed passes."
    elif key == "couldnt_trust":
        reason = (
            "A control did not behave as expected in at least one run, or a stored record no longer matches its fingerprint, "
            "so nothing is said about this change."
        )
    elif key == "nothing_to_run":
        reason = nothing_picked(change, program) if program is not None else NOTHING_PICKED
    elif key == "cant_run":
        if change.get("problem"):
            reason = PROBLEMS[change["problem"]]
        elif change.get("gives") is None:
            reason = NOT_OURS
        elif change.get("starts_from") is None:
            reason = BASE_NOT_OURS
        else:
            n = counts.get("not_compared", 0)
            reason = (
                f"{_count(n, 'picked test')} could not run, so the change could not be compared. A test that could not run is not a result."
                if n
                else "The picked tests could not be compared."
            )
    elif key == "not_run" and run is not None:
        if run["state"] == "interrupted":
            reason = "The last run was cut off before it finished. Run the picked tests again."
        elif run["state"] == "reviewed" and not run.get("covers_picked", True):
            reason = "The tests picked for this change are not the ones its last run ran. Run the picked tests again."
    return {"key": key, "word": word, "tone": STATUS_TONES[key], "busy": key == "running", "reason": reason}


def run_view(change: dict, program: dict, titles: list[str], blocked: str | None) -> dict:
    """The Run button of a change's panel: its name, whether it can be pressed and why not, and what it will run."""
    key, run = change["status"], change.get("run")
    reason = blocked
    if (
        reason is None
        and key in ("nothing_to_run", "cant_run")
        and not (key == "cant_run" and change.get("gives") and change.get("starts_from") and not change.get("problem"))
    ):
        reason = status_view(change, program)["reason"]
    note = None
    if change.get("gives") and change.get("starts_from") and titles:
        note = (
            f"Runs {_join(titles)} on {program['name']} {change['gives']['version']}: the registered demo program this change's code is, byte for "
            f"byte. Each is compared with its newest reviewed result on the code before, {program['name']} {change['starts_from']['version']}; "
            "a test with no result on that code also runs on it. These runs are kept apart: they never replace a result of this assessment's own tests."
        )
    return {
        "label": RUN_AGAIN if run is not None and run["state"] != "interrupted" else RUN_FIRST,
        "can": reason is None,
        "blocked_reason": reason,
        "will_run": titles,
        "note": note,
    }


def _join(items: list[str]) -> str:
    return "".join(items) if len(items) <= 1 else ", ".join(items[:-1]) + " and " + items[-1]


__all__ = [
    "BASE_NOT_OURS",
    "EMPTY",
    "FLAGS_NOTE",
    "FLAG_TITLE",
    "MENU_BLOCKED",
    "MENU_BUTTON",
    "MENU_NOTE",
    "NOTHING_PICKED",
    "NOT_CONNECTED",
    "NOT_OURS",
    "NO_CODE",
    "OUTCOME_WORDS",
    "RUN_AGAIN",
    "RUN_FIRST",
    "STATUS_WORDS",
    "SUBLINE",
    "TITLE",
    "UNREADABLE",
    "file_view",
    "flag_view",
    "pick_reason",
    "run_view",
    "short_commit",
    "status_view",
    "when_words",
]
