"""The "who did what" part of an evidence file (design refactor, decision I), checked after the file's own signature held.

The part lists each recorded press of a button that decides or changes something in the assessment: who, when, which
button, what it was on, and references to the runs and records it started. What is checked here, in order:

  1. the part has exactly the form this app writes: its schema, its note, its three name sources, and for every press
     exactly the known fields, each of the right kind (a press of an unknown kind, a name from an unknown source, a
     fact that is not a plain value, or a field too many fails);
  2. every time is a well-formed moment in UTC, as the app writes one, and the presses are in time order, each with
     its own number;
  3. every reference resolves to something the same file holds: a run in the file's list of checks (also a Verify
     run), a test, a fix, a proof of a fix, a change to a system, a watch run or a developer's change. A run is tied
     to one press only;
  4. where the file holds the record a press made, the two agree: an approval is recorded in the fix it names under
     the name the press says it was given as; a merge and an opened pull request are in the fix they name; a run that
     a press started was started by a press that starts runs.

The lists of kinds, sources and references are written out again here, apart from the app's own
(app/lab/actions.py, app/record/part.py), so the file is not checked with the code that made it;
tests/record/test_record_evidence.py compares the two.

What is taken as given: that the name is the person. The app records the account that was logged in, or a typed name,
or "You"; it does not check who is at the keyboard beyond its login, and neither can a file. A file made before this
part existed has no such part and verifies as it always did.

This module reads the file as data only. Nothing the file names is run or opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCHEMA = "isogeny.actions/1"
SOURCES = ("account", "typed", "default")
# every button whose press the app records, by the name the record gives it
KINDS = (
    "assessment_started",
    "assessment_rerun",
    "assessment_changed",
    "closed",
    "file_imported",
    "dependency_list_added",
    "evidence_downloaded",
    "address_confirmed",
    "address_unconfirmed",
    "verify",
    "run",
    "run_all",
    "test_added",
    "test_removed",
    "tests_reordered",
    "retest",
    "retest_now",
    "measure_status",
    "measure_dependencies",
    "marked_reviewed",
    "dig_deeper",
    "code_connected",
    "proof_started",
    "pull_request_opened",
    "approved",
    "merged",
    "change_tried",
    "approval_asked",
    "change_approved",
    "applied",
    "rolled_back",
    "option_chosen",
    "setting_changed",
    "library_tied",
    "demo_change_brought_in",
    "picked_tests_run",
)
# the presses that can start a run (a run is tied to the press that queued it)
STARTS_RUNS = (
    "run",
    "run_all",
    "retest",
    "retest_now",
    "measure_status",
    "measure_dependencies",
    "code_connected",
    "proof_started",
    "change_tried",
    "applied",
    "rolled_back",
    "picked_tests_run",
)
REF_KINDS = ("run", "verify_run", "test", "fix", "proof", "change", "watch_run", "developer_change")
NUMBERED = ("run", "verify_run", "test", "proof", "watch_run")  # references that are a number; the others are a name
ITEM_KINDS = ("test", "fix", "change", "system", "run", "developer-change")
ACTION_KEYS = {"n", "at", "by", "by_source", "kind", "what", "button", "item", "refs", "runs_not_in_file", "facts"}
PART_KEYS = {"schema", "note", "sources", "actions"}
MAX_ACTIONS, MAX_REFS, MAX_FACTS, MAX_LIST = 100_000, 5_000, 40, 5_000
_MOMENT = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")
_FACT = re.compile(r"\A[a-z][a-z0-9_]{0,39}\Z")  # a fact's name, as the app writes them ("retest_id", "sha256")
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


@dataclass
class ActionsOutcome:
    ok: bool
    problem: str | None = None
    lines: list[str] = field(default_factory=list)


class _Failed(Exception):
    """The part does not hold; the message says what, in one plain sentence."""


def _plain(value: object, limit: int = 80) -> str:
    """Text from the file, made safe to print: plain printable characters only, and not too long."""
    text = "".join(ch if ch.isprintable() and ch not in "\x1b‮‭⁦⁧⁨⁩" else "?" for ch in str(value))
    return text if len(text) <= limit else text[:limit] + "..."


def _need(condition: bool, problem: str) -> None:
    if not condition:
        raise _Failed(problem)


def _text(value: object, most: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= most


def _whole(value: object) -> bool:
    """A whole number that is no yes-or-no (in JSON read by Python, true is also an int)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, bool)) or _whole(value)


def well_formed_moment(value: object) -> bool:
    """A moment as the app writes one: UTC, to the millisecond, and a date and time that exist."""
    if not isinstance(value, str) or not _MOMENT.match(value):
        return False
    from datetime import datetime

    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return False
    return True


def _list_of_dicts(value: object, most: int) -> list:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) and len(value) <= most else []


def held(evidence: dict) -> dict[str, set]:
    """What the file holds that a press can point at, read from the file's own parts."""
    checks = _list_of_dicts(evidence.get("checks"), 100_000)
    fixes = _list_of_dicts(evidence.get("fixes"), 100_000)
    watch = evidence.get("change_watch") if isinstance(evidence.get("change_watch"), dict) else {}
    runs = [r for c in checks for r in _list_of_dicts(c.get("runs"), 100_000)]
    tests = {t.get("item_id") for t in _list_of_dicts(evidence.get("tests"), 100_000) if _whole(t.get("item_id"))}
    for part in ("migration", "dependencies"):
        inside = evidence.get(part) if isinstance(evidence.get(part), dict) else {}
        tests |= {
            m.get("item_id") for m in _list_of_dicts(inside.get("measurements"), 100_000) if _whole(m.get("item_id"))
        }
    changes = [c.get("change") for c in _list_of_dicts(evidence.get("changes"), 100_000)]
    return {
        "run": {r.get("run_id") for r in runs if _whole(r.get("run_id"))},
        "verify_run": {r.get("verify_run_id") for r in runs if _whole(r.get("verify_run_id"))},
        "test": tests,
        "fix": {f.get("id") for f in fixes if isinstance(f.get("id"), str)},
        "proof": {p.get("id") for f in fixes for p in _list_of_dicts(f.get("proofs"), 100_000) if _whole(p.get("id"))},
        "change": {c.get("key") for c in changes if isinstance(c, dict) and isinstance(c.get("key"), str)},
        "watch_run": {
            r.get("watch_run_id") for r in _list_of_dicts(watch.get("runs"), 100_000) if _whole(r.get("watch_run_id"))
        },
        "developer_change": {
            c.get("id") for c in _list_of_dicts(watch.get("changes"), 100_000) if isinstance(c.get("id"), str)
        },
    }


def _check_form(part: object) -> list[dict]:
    _need(
        isinstance(part, dict) and set(part) == PART_KEYS,
        "it does not have exactly the parts schema, note, sources and actions.",
    )
    assert isinstance(part, dict)
    _need(part["schema"] == SCHEMA, "it is not a who-did-what record this version knows.")
    _need(_text(part["note"], 4000), "its note is missing.")
    sources = part["sources"]
    _need(
        isinstance(sources, dict) and set(sources) == set(SOURCES) and all(_text(v, 400) for v in sources.values()),
        "it does not say what each of the three name sources is.",
    )
    actions = part["actions"]
    _need(
        isinstance(actions, list) and 0 < len(actions) <= MAX_ACTIONS,
        "it lists no press, or more than a file can hold.",
    )
    for action in actions:
        _need(
            isinstance(action, dict) and set(action) == ACTION_KEYS,
            "a press does not have exactly the fields this app writes.",
        )
        n = action["n"]
        _need(_whole(n) and n > 0, "a press has no number of its own.")
        _need(well_formed_moment(action["at"]), f"press {n} has a time that is not a well-formed moment in UTC.")
        _need(_text(action["by"], 100), f"press {n} names nobody.")
        _need(action["by_source"] in SOURCES, f"press {n} takes its name from a source this app does not have.")
        _need(action["kind"] in KINDS, f"press {n} is of a kind this app does not record: {_plain(action['kind'])}.")
        _need(_text(action["what"], 200), f"press {n} does not say what was done.")
        _need(action["button"] is None or _text(action["button"], 100), f"press {n} names a button that is not text.")
        item = action["item"]
        _need(
            item is None
            or (_text(item, 720) and item.partition(":")[0] in ITEM_KINDS and bool(item.partition(":")[2])),
            f"press {n} is on something this app does not name that way.",
        )
        _need(_whole(action["runs_not_in_file"]) and action["runs_not_in_file"] >= 0, f"press {n} miscounts its runs.")
        refs = action["refs"]
        _need(isinstance(refs, list) and len(refs) <= MAX_REFS, f"press {n} does not list its references.")
        for ref in refs:
            _need(
                isinstance(ref, dict) and set(ref) == {"kind", "id"},
                f"press {n} has a reference that is not a kind and an id.",
            )
            _need(ref["kind"] in REF_KINDS, f"press {n} points at a kind of record this app does not reference.")
            _need(
                _whole(ref["id"]) if ref["kind"] in NUMBERED else _text(ref["id"], 720),
                f"press {n} has a reference whose id is not the kind of value that record has.",
            )
        facts = action["facts"]
        _need(isinstance(facts, dict) and len(facts) <= MAX_FACTS, f"press {n} does not list its facts.")
        for key, value in facts.items():
            _need(
                isinstance(key, str) and bool(_FACT.match(key)),
                f"press {n} has a fact with a name this app does not write.",
            )
            _need(
                _scalar(value)
                or (isinstance(value, list) and len(value) <= MAX_LIST and all(_scalar(v) for v in value)),
                f"press {n} has a fact that is not a plain value: {_plain(key)}.",
            )
    return actions


def _check_order(actions: list[dict]) -> None:
    seen: set[int] = set()
    before = None
    for action in actions:
        _need(action["n"] not in seen, f"two presses have the number {action['n']}.")
        seen.add(action["n"])
        now = (action["at"], action["n"])
        _need(
            before is None or before <= now,
            f"press {action['n']} is listed before an earlier one: the presses are not in time order.",
        )
        before = now


def _check_references(actions: list[dict], evidence: dict) -> int:
    """Every reference resolves in this file, and a run belongs to one press. Returns how many runs are tied."""
    holds = held(evidence)
    tied: dict[int, int] = {}
    for action in actions:
        n, seen = action["n"], set()
        for ref in action["refs"]:
            kind, ident = ref["kind"], ref["id"]
            _need((kind, ident) not in seen, f"press {n} lists the same reference twice.")
            seen.add((kind, ident))
            _need(
                ident in holds[kind],
                f"press {n} points at {kind.replace('_', ' ')} {_plain(ident)}, and this file holds no such record.",
            )
        item_kind, _, name = (action["item"] or "").partition(":")
        runs = [r["id"] for r in action["refs"] if r["kind"] == "run"]
        on_a_result = [int(name)] if item_kind == "run" and name.isdigit() else []
        started = [r for r in runs if r not in on_a_result]
        _need(
            not started or action["kind"] in STARTS_RUNS,
            f"press {n} ({_plain(action['what'])}) is tied to a run, and that button starts no run.",
        )
        for run_id in started:
            _need(run_id not in tied, f"run {run_id} is tied to two presses ({tied.get(run_id)} and {n}).")
            tied[run_id] = n
    return len(tied)


def _fix_of(action: dict, evidence: dict) -> dict | None:
    name = next((r["id"] for r in action["refs"] if r["kind"] == "fix"), None)
    return (
        next((f for f in _list_of_dicts(evidence.get("fixes"), 100_000) if f.get("id") == name), None) if name else None
    )


def _check_records(actions: list[dict], evidence: dict) -> None:
    """Where the file holds the record a press made, the press and the record agree."""
    for action in actions:
        n, kind, facts = action["n"], action["kind"], action["facts"]
        fix = _fix_of(action, evidence)
        if kind == "approved" and fix is not None:
            names = {
                a.get("name")
                for a in _list_of_dicts(fix.get("approvals"), 1000)
                if a.get("approved_at") and isinstance(a.get("name"), str)
            }
            _need(
                isinstance(facts.get("as"), str) and facts.get("as") in names,
                f"press {n} says a pull request was approved as {_plain(facts.get('as'))}, and the fix it names holds no such approval.",
            )
        if kind == "merged" and fix is not None:
            _need(
                isinstance(fix.get("merge"), dict),
                f"press {n} says a pull request was merged, and the fix it names holds no merge.",
            )
        if kind == "pull_request_opened" and fix is not None:
            _need(
                isinstance(fix.get("pull_request"), dict),
                f"press {n} says a pull request was opened, and the fix it names holds no pull request.",
            )
        if kind == "evidence_downloaded":
            fingerprint = facts.get("fingerprint")
            _need(
                isinstance(fingerprint, str) and bool(_HEX64.match(fingerprint)),
                f"press {n} is an evidence download with no fingerprint of the file that was downloaded.",
            )
        if kind in ("address_confirmed", "address_unconfirmed"):
            _need(
                isinstance(facts.get("confirmed"), bool), f"press {n} is a tick that does not say how the tick stands."
            )


def check_actions(evidence: dict) -> ActionsOutcome:
    """Check the who-did-what part of an evidence record whose own signature was already verified."""
    try:
        actions = _check_form(evidence.get("actions"))
        _check_order(actions)
        tied = _check_references(actions, evidence)
        _check_records(actions, evidence)
    except _Failed as exc:
        return ActionsOutcome(False, str(exc))
    names = sorted({a["by"] for a in actions})
    return ActionsOutcome(
        True,
        None,
        [
            f"{len(actions)} recorded {'press' if len(actions) == 1 else 'presses'}, under {len(names)} "
            f"{'name' if len(names) == 1 else 'names'}; {tied} {'run is' if tied == 1 else 'runs are'} tied to the press that started "
            "them, and every reference resolves in this file.",
            "A name is the account that was logged in, a typed name or “You”: the app does not check who is at the keyboard "
            "beyond its login, and this check takes the name as recorded.",
        ],
    )


__all__ = [
    "KINDS",
    "REF_KINDS",
    "SCHEMA",
    "SOURCES",
    "STARTS_RUNS",
    "ActionsOutcome",
    "check_actions",
    "held",
    "well_formed_moment",
]
