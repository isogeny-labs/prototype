"""Phase 5c: the verify command reads an evidence file as data. Otto's audit runs the verifier each ledger entry
names, and a verifier can name a command or start a program. So a ledger that came out of a file is handed to Otto's
harness only when it names nothing to run but this app's own pinned record checker. These tests give the command
ledgers that name other things, each with a marker that would be written if anything ran. Nothing may run.

Most of this needs no Otto: the refusal comes before the harness is asked for anything."""
import copy
import hashlib
import json
import random
import sys
import time

import pytest

import otto_helpers as helpers
from app.canonical import canonical_bytes
from app.otto import assurance, harness
from conftest import demo_plan
from evidence import otto as evidence_otto

OURS = hashlib.sha256(assurance.CHECKER_SOURCE.read_bytes()).hexdigest()
WHEN = "2026-11-17T12:00:00+00:00"


def _rid(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _chain(records: list[dict], lines: list[str] | None = None) -> list[str]:
    """Ledger lines for these records, chained after `lines`, written exactly as Otto writes them."""
    out = list(lines or [])
    prev = json.loads(out[-1])["hash"] if out else None
    for record in records:
        body = {"seq": len(out), "prev": prev, "kind": record["type"], "payload": record, "ts": WHEN}
        entry = {**body, "hash": _rid(body)}
        out.append(canonical_bytes(entry).decode("utf-8"))
        prev = entry["hash"]
    return out


def _ours(params=None) -> dict:
    return {"kind": "certificate", "checker": "recheck.py", "checker_sha256": OURS, "params": params or {"kind": "step", "step": "write_fix"},
            "timeout_seconds": 60}


def _triple(verifier: dict, artifact: dict | None = None) -> list[dict]:
    """An objective with this verifier, a claim on it and an "accept" verdict: what makes Otto's audit run the verifier."""
    objective = {"type": "objective", "statement": "made for a test", "verifier": verifier}
    claim = {"type": "claim", "objective_id": _rid(objective), "artifact": artifact or {"made": "for a test"}, "cites": []}
    verdict = {"type": "verdict", "claim_id": _rid(claim), "objective_id": _rid(objective), "status": "accept", "detail": "made for a test",
               "tier": "certificate"}
    return [objective, claim, verdict]


def _hostile(marker) -> dict[str, dict]:
    """Verifiers a hostile file could name. Each would do something if Otto's harness were given it."""
    run_it = [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ran')"]
    return {
        "a command to replay": {"kind": "replay", "command": run_it, "code": {"recheck.py": OURS}},
        "a model judge": {"kind": "judge", "rubric": "anything", "model": "any"},
        "an experiment": {"kind": "experiment", "command": run_it},
        "another checker file": {**_ours(), "checker": "../recheck.py"},
        "our checker with one more part": {**_ours(), "command": run_it},
        "our checker with code to pin": {**_ours(), "code": {"other.py": "0" * 64}},
        "a longer time limit": {**_ours(), "timeout_seconds": 86400},
        "params of an unknown kind": _ours({"kind": "shell", "command": run_it}),
        "an evaluator": {**_ours(), "kind": "evaluator"},
        "no verifier at all": None,                                      # type: ignore[dict-item]
    }


@pytest.mark.parametrize("name", list(_hostile("x")))
def test_a_ledger_that_names_anything_but_our_own_checker_is_not_given_to_otto_and_nothing_runs(tmp_path, name):
    marker = tmp_path / "ran.txt"
    lines = _chain(_triple(_hostile(marker)[name]))
    entries = [json.loads(line) for line in lines]
    assert assurance.only_our_checker(entries) == "the ledger names something to run that is not this app's own pinned record checker"
    problems = assurance.verify_lines(lines, tmp_path / "scratch")
    assert problems == ["the ledger names something to run that is not this app's own pinned record checker, so nothing was run"]
    assert not marker.exists() and not (tmp_path / "scratch").exists()          # the harness was never given a folder


def test_entries_of_other_kinds_are_refused_too(tmp_path):
    hypothesis = {"type": "hypothesis", "statement": "x", "executor": {"command": ["sh", "-c", "true"]}}
    for records in ([hypothesis], [{"type": "objective", "verifier": _ours()}, {"type": "run", "hypothesis_id": "x"}]):
        lines = _chain(records)
        assert "of a kind an assessment's ledger never holds" in assurance.only_our_checker([json.loads(line) for line in lines])
        assert "nothing was run" in assurance.verify_lines(lines, tmp_path / "scratch")[0]
    mismatch = [json.loads(line) for line in _chain(_triple(_ours()))]
    mismatch[0]["kind"] = "claim"                                           # an entry that says it is one kind and holds another
    assert "never holds" in assurance.only_our_checker(mismatch)
    assert assurance.verify_lines(["{not json"], tmp_path / "scratch") == ["the ledger's lines could not be read"]


def test_our_own_shape_is_accepted_and_another_versions_checker_is_named_as_that():
    good = [json.loads(line) for line in _chain(_triple(_ours()) + _triple(_ours({"kind": "run", "test": "a" * 64})))]
    assert assurance.only_our_checker(good) is None and assurance.only_our_checker([]) is None
    other = [json.loads(line) for line in _chain(_triple({**_ours(), "checker_sha256": "0" * 64}))]
    assert assurance.only_our_checker(other) == assurance.OTHER_VERSION


def test_damaged_ledgers_are_refused_or_read_and_never_run_anything(tmp_path):
    """Seeded fuzz of the reader that stands between a file's ledger and Otto's harness."""
    marker = tmp_path / "ran.txt"
    seed = [json.loads(line) for line in _chain(_triple(_ours()) + _triple(_hostile(marker)["a command to replay"]))]
    rng = random.Random(20261117)
    odd = [None, True, 0, -1, 1.5, "", "x" * 2000, [], {}, [[]], {"kind": "replay"}, "replay", "certificate", 60, "60", OURS, "0" * 64]
    started = time.monotonic()
    for _ in range(1500):
        entries = copy.deepcopy(seed)
        for _ in range(rng.randint(1, 4)):
            target = rng.choice(entries)
            spot = rng.choice([target, target.get("payload") if isinstance(target.get("payload"), dict) else target,
                               (target.get("payload") or {}).get("verifier") if isinstance(target.get("payload"), dict)
                               and isinstance(target["payload"].get("verifier"), dict) else target])
            action = rng.choice(["set", "drop", "add"])
            if action == "set" and spot:
                spot[rng.choice(list(spot))] = rng.choice(odd)
            elif action == "drop" and spot:
                spot.pop(rng.choice(list(spot)))
            else:
                spot[rng.choice(["command", "kind", "checker", "code", "type", "x"])] = rng.choice(odd)
        if rng.random() < 0.2:
            entries.insert(rng.randrange(len(entries) + 1), rng.choice(odd))
        answer = assurance.only_our_checker(entries)
        assert answer is None or (isinstance(answer, str) and answer)
        # the seed always holds the hostile verifier unless the damage removed or defused it: it can never be let through as ours
        if answer is None:
            for entry in entries:
                if isinstance(entry, dict) and entry.get("kind") == "objective":
                    assert entry["payload"]["verifier"]["kind"] == "certificate" and set(entry["payload"]["verifier"]) == set(_ours())
    assert time.monotonic() - started < 20 and not marker.exists()


# ---------------------------------------------------------------- through the verify command's own check, on a real file

pytest_needs_otto = pytest.mark.needs_otto


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    """A demo-mode Lab with a pack installed, its check added and run once; built once, only read afterwards."""
    patch = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("ran")
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, patch, {"2026.11.1.json": first}, [public])
    lab.pack_key = public
    lab.plan = demo_plan(lab)
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    lab.add_new_checks(lab.plan.id)
    item = next(t for t in lab.plan_view(lab.plan.id)["tests"] if t["kind"] == "advisory_cases")["id"]
    lab.run_test(lab.plan.id, item)
    lab.wait_until_idle(lab.plan.id, 240)
    made = lab.export_evidence(lab.plan.id)
    lab.evidence = json.loads(lab.evidence_file(made["id"], "json")[1])["evidence"]
    yield lab
    lab.stop()
    patch.undo()


def _with_ledger(evidence: dict, lines: list[str]) -> dict:
    changed = copy.deepcopy(evidence)
    changed["otto"]["ledger"].update(lines=lines, height=len(lines), head=json.loads(lines[-1])["hash"])
    return changed


@pytest_needs_otto
def test_the_real_file_passes_and_says_what_was_checked(ran):
    outcome = evidence_otto.check_otto(ran.evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.OK and outcome.problem is None
    assert any("the pinned checker run again on every entry" in line for line in outcome.lines)


@pytest_needs_otto
@pytest.mark.parametrize("name", ["a command to replay", "a model judge", "our checker with one more part"])
def test_a_file_whose_ledger_names_something_to_run_fails_and_nothing_runs(ran, tmp_path, name):
    """Everything else in the file is real and whole: only three entries were added to the end of its ledger."""
    marker = tmp_path / "ran.txt"
    lines = _chain(_triple(_hostile(marker)[name]), ran.evidence["otto"]["ledger"]["lines"])
    outcome = evidence_otto.check_otto(_with_ledger(ran.evidence, lines), {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED
    assert outcome.problem == "the ledger names something to run that is not this app's own pinned record checker. Nothing was run."
    assert not marker.exists()


@pytest_needs_otto
def test_a_ledger_that_pins_a_checker_this_version_does_not_have_is_not_confirmed_never_a_pass(ran):
    """Before this was checked, such a ledger passed: Otto could not run the checker and only noted it."""
    lines = _chain(_triple({**_ours(), "checker_sha256": "0" * 64}), ran.evidence["otto"]["ledger"]["lines"])
    outcome = evidence_otto.check_otto(_with_ledger(ran.evidence, lines), {ran.pack_key})
    assert outcome.code == evidence_otto.NOT_CONFIRMED and "Otto's own audit of the ledger was not run" in outcome.problem
    assert "another version of the app" in outcome.problem
    assert not any("the pinned checker run again" in line for line in outcome.lines)


@pytest_needs_otto
def test_an_entry_the_audit_could_not_check_again_is_a_problem_not_a_quiet_pass(ran, monkeypatch):
    verifiers = harness.module("verifiers")
    monkeypatch.setattr(verifiers, "_run", lambda *a, **k: None)          # as if the checker could not be started
    outcome = evidence_otto.check_otto(ran.evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "could not be checked again" in outcome.problem


@pytest_needs_otto
def test_a_run_of_an_advisory_check_that_the_ledger_does_not_bind_fails(ran):
    """The run is in the file's own list of tests. Its two ledger entries (the run entry and the checker's verdict)
    and its line in the Otto part were cut out, and the ledger's length and latest entry set to match."""
    lines = ran.evidence["otto"]["ledger"]["lines"]
    assert len(lines) == 3 and len(ran.evidence["otto"]["runs"]) == 1
    cut = _with_ledger(ran.evidence, lines[:1])
    cut["otto"]["runs"] = []
    outcome = evidence_otto.check_otto(cut, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "is in the file, but Otto's ledger does not bind it" in outcome.problem
    # a run that never started because Otto was not installed could not be recorded: it is the one exception
    not_started = copy.deepcopy(cut)
    test = next(t for t in not_started["tests"] if t["kind"] == "advisory_cases")
    test["runs"][0]["review"]["verdict"]["reason_code"] = "otto_not_installed"
    assert evidence_otto.check_otto(not_started, {ran.pack_key}).code == evidence_otto.OK


@pytest_needs_otto
def test_a_damaged_otto_part_is_refused_or_read_within_a_time_limit_and_never_raises(ran):
    """Seeded fuzz of the verify command's reader of the Otto part."""
    rng = random.Random(5150)
    odd = [None, True, 0, -1, "", "x", [], {}, [[]], {"a": {"b": []}}, "sha256:" + "0" * 64, 10 ** 9]
    started = time.monotonic()
    seen = set()
    for _ in range(120):
        evidence = copy.deepcopy(ran.evidence)
        spot = evidence["otto"]
        for _ in range(rng.randint(1, 3)):
            path = spot
            for _ in range(rng.randint(0, 3)):                 # walk a few steps down
                inner = [v for v in (path.values() if isinstance(path, dict) else path) if isinstance(v, (dict, list)) and v]
                if not inner:
                    break
                path = rng.choice(inner)
            if isinstance(path, dict) and path:
                key = rng.choice(list(path))
                if rng.random() < 0.3:
                    path.pop(key)
                else:
                    path[key] = rng.choice(odd)
            elif isinstance(path, list) and path:
                path[rng.randrange(len(path))] = rng.choice(odd)
        outcome = evidence_otto.check_otto(evidence, {ran.pack_key})
        assert outcome.code in (evidence_otto.OK, evidence_otto.FAILED, evidence_otto.NOT_CONFIRMED)
        assert outcome.code == evidence_otto.OK or (isinstance(outcome.problem, str) and outcome.problem)
        seen.add(outcome.code)
    assert evidence_otto.FAILED in seen and time.monotonic() - started < 240
