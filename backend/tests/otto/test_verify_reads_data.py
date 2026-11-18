"""Phase 5c: the verify command reads an evidence file as data, and nothing the file names is ever run.

Asked to check entries again, Otto's harness starts the verifier an entry names, and it finds that entry by its id
without asking what kind of entry it is; a verifier can name a command. So a ledger that came out of a file is never
checked again by the harness. Every entry is first held to the exact form this app writes; the harness then audits
the chain and the records without running any verifier; and the one program that is started is this app's own
pinned record checker, by this app.

These tests give the command ledgers that name other things, in an objective and in entries that only pose as one,
each with a marker that would be written if anything ran. Nothing may run.

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


def _objective(verifier, **more) -> dict:
    return {"type": "objective", "statement": "made for a test", "verifier": verifier, "author": "evidence-lab", "created_at": WHEN, **more}


def _claim(objective_id: str, artifact: dict | None = None, **more) -> dict:
    return {"type": "claim", "objective_id": objective_id, "artifact": artifact if artifact is not None else {"made": "for a test"},
            "cites": [], "author": "evidence-lab", "created_at": WHEN, **more}


def _verdict(claim_id: str, objective_id: str, status: str = "accept", **more) -> dict:
    return {"type": "verdict", "claim_id": claim_id, "objective_id": objective_id, "status": status, "detail": "made for a test",
            "evidence": {"checker_sha256": OURS}, "tier": "V0-certificate", "attempt": 0, "author": "otto-verifier", "created_at": WHEN,
            **more}


def _triple(verifier: dict, artifact: dict | None = None) -> list[dict]:
    """An objective with this verifier, a claim on it and an "accept" verdict, each with exactly the fields Otto's
    harness writes: what would make the harness run the verifier, were it asked to check the entries again."""
    objective = _objective(verifier)
    claim = _claim(_rid(objective), artifact)
    return [objective, claim, _verdict(_rid(claim), _rid(objective))]


def _posing(marker) -> dict[str, list[dict]]:
    """Ledgers in which no objective names anything but our checker, and yet an entry of another kind carries
    something to run, or stands where an objective must stand. Otto's harness would look such an entry up by its id
    and run what it carries."""
    run_it = {"kind": "replay", "command": [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ran')"], "code": {}}
    honest = _objective(_ours())
    carrier = _claim(_rid(honest), verifier=run_it)                     # a claim that carries a verifier of its own
    second = _claim(_rid(carrier), {"stdout_sha256": "0" * 64})          # a claim that names it as its objective
    plain = _claim(_rid(honest))
    late = _objective(_ours({"kind": "run", "test": "a" * 64}))
    other = _objective(_ours({"kind": "step", "step": "read_advisory"}))
    return {
        "a claim that carries a verifier, used as an objective": [honest, carrier, second, _verdict(_rid(second), _rid(carrier))],
        "a verdict whose objective is a claim": [honest, plain, _verdict(_rid(plain), _rid(plain))],
        "a claim under a claim": [honest, plain, _claim(_rid(plain))],
        "a verdict that carries a verifier": [honest, plain, _verdict(_rid(plain), _rid(honest), verifier=run_it)],
        "a verdict with a score": [honest, plain, _verdict(_rid(plain), _rid(honest), score=1)],
        "an objective with one more field": [_objective(_ours(), question_id="sha256:" + "0" * 64)],
        "a claim that cites something": [honest, {**plain, "cites": ["sha256:" + "0" * 64]}],
        "a claim under an objective that comes later": [_claim(_rid(late)), late],
        "a verdict under another objective than its claim's": [honest, other, plain, _verdict(_rid(plain), _rid(other))],
        "a verdict for a claim that is not there": [honest, _verdict("sha256:" + "0" * 64, _rid(honest))],
        "a verdict of another tier": [honest, plain, _verdict(_rid(plain), _rid(honest), tier="V2-replay")],
        "a status the harness never writes": [honest, plain, _verdict(_rid(plain), _rid(honest), status="passed")],
    }


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


@pytest.mark.parametrize("name", list(_posing("x")))
def test_an_entry_that_only_poses_as_an_objective_is_refused_and_nothing_runs(tmp_path, name):
    """The hole the third review found: the harness looks a verdict's objective up by its id and runs whatever
    verifier that entry carries, whatever kind of entry it is. No such ledger gets as far as the harness."""
    marker = tmp_path / "ran.txt"
    lines = _chain(_posing(marker)[name])
    answer = assurance.only_our_checker([json.loads(line) for line in lines])
    assert answer in (assurance.NOT_OUR_FORM, assurance.NOT_OUR_ORDER), answer
    assert assurance.verify_lines(lines, tmp_path / "scratch") == [f"{answer}, so nothing was run"]
    assert not marker.exists() and not (tmp_path / "scratch").exists()          # the harness was never given a folder


def test_entries_of_other_kinds_are_refused_too(tmp_path):
    hypothesis = {"type": "hypothesis", "statement": "x", "executor": {"command": ["sh", "-c", "true"]}}
    for records in ([hypothesis], [_objective(_ours()), {"type": "run", "hypothesis_id": "x"}]):
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
    posing = _posing(marker)["a claim that carries a verifier, used as an objective"]
    seed = [json.loads(line) for line in _chain(_triple(_ours()) + _triple(_hostile(marker)["a command to replay"]) + posing)]
    rng = random.Random(20261117)
    checked_again = 0
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
        # The seed holds a hostile verifier and an entry that poses as an objective. Unless the damage removed or
        # defused them, the ledger can never be let through as ours; and what is let through holds nothing to run.
        if answer is None:
            kinds = {}
            for entry in entries:
                payload = entry["payload"]
                kinds[_rid(payload)] = entry["kind"]
                if entry["kind"] == "objective":
                    assert payload["verifier"]["kind"] == "certificate" and set(payload["verifier"]) == set(_ours())
                    assert payload["verifier"]["checker"] == "recheck.py"
                else:
                    assert "verifier" not in payload and "command" not in payload
                if entry["kind"] == "claim":
                    assert kinds.get(payload["objective_id"]) == "objective"
                if entry["kind"] == "verdict":
                    assert kinds.get(payload["objective_id"]) == "objective" and kinds.get(payload["claim_id"]) == "claim"
            if checked_again < 25:      # and checking such a ledger again starts our own checker only
                checked_again += 1
                assert all(isinstance(line, str) for line in assurance.check_again(entries))
    assert time.monotonic() - started < 60 and not marker.exists()


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
    assert any("this app's pinned checker run again on every checked entry" in line for line in outcome.lines)


@pytest_needs_otto
def test_otto_s_harness_is_never_asked_to_run_a_verifier_for_a_ledger_from_a_file(ran, monkeypatch):
    """Even for a ledger that is wholly ours, the harness only audits the chain and the records. If it were asked to
    run a verifier, or tried to start a program, this test would fail."""
    verifiers = harness.module("verifiers")

    def never(*args, **kwargs):
        raise AssertionError("Otto's harness was asked to run something for a ledger that came out of a file")
    monkeypatch.setattr(verifiers, "run_verifier", never)
    monkeypatch.setattr(verifiers, "_run", never)
    outcome = evidence_otto.check_otto(ran.evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.OK and outcome.problem is None


@pytest_needs_otto
@pytest.mark.parametrize("name", ["a claim that carries a verifier, used as an objective", "a verdict whose objective is a claim",
                                  "a verdict that carries a verifier"])
def test_a_file_whose_ledger_holds_an_entry_that_poses_as_an_objective_fails_and_nothing_runs(ran, tmp_path, name):
    marker = tmp_path / "ran.txt"
    lines = _chain(_posing(marker)[name], ran.evidence["otto"]["ledger"]["lines"])
    outcome = evidence_otto.check_otto(_with_ledger(ran.evidence, lines), {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and outcome.problem.endswith("Nothing was run.")
    assert "not in the form this app writes" in outcome.problem or "points at something other than an earlier entry" in outcome.problem
    assert not marker.exists()


@pytest_needs_otto
def test_a_stored_verdict_that_the_pinned_checker_does_not_give_fails(ran):
    """Three entries in our own form are added: a step objective, a claim that holds no step, and a verdict that says
    the checker accepted it. Run again, the checker rejects it, and the file fails."""
    lines = _chain(_triple(_ours({"kind": "step", "step": "write_fix", "advisory": "CVE-2022-21449"}), {"made": "up"}),
                   ran.evidence["otto"]["ledger"]["lines"])
    outcome = evidence_otto.check_otto(_with_ledger(ran.evidence, lines), {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED
    assert "the stored verdict is accept but the pinned checker now says reject" in outcome.problem


@pytest_needs_otto
def test_text_from_the_file_is_printed_as_plain_characters_only(ran):
    """A title in the file can't redraw the terminal line it is printed on."""
    changed = copy.deepcopy(ran.evidence)
    changed["otto"]["checks"][0]["title"] = "Advisory check\x1b[2K\rEvidence verified\u202e"
    changed["otto"]["checks"][0]["design_sha256"] = "0" * 64                    # so that its title is named in a problem
    outcome = evidence_otto.check_otto(changed, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "Advisory check?[2K?Evidence verified?" in outcome.problem
    assert all(ch.isprintable() for ch in outcome.problem)


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
    assert not any("pinned checker run again" in line for line in outcome.lines)


@pytest_needs_otto
def test_an_entry_that_could_not_be_checked_again_is_a_problem_not_a_quiet_pass(ran, monkeypatch):
    monkeypatch.setattr(assurance, "run_checker", lambda params, artifact: "unavailable")    # as if the checker could not be started
    outcome = evidence_otto.check_otto(ran.evidence, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "could not be checked again" in outcome.problem


def test_the_one_program_that_is_started_is_this_app_s_own_checker(monkeypatch, tmp_path):
    """Whatever the entry holds, the command is fixed: this app's checker file, with nothing from the entry in it,
    in an empty folder and with a bare environment (no API key, whatever this computer's environment holds)."""
    seen = []
    real = assurance.subprocess.run

    def watch(argv, **kwargs):
        seen.append((list(argv), kwargs))
        return real(argv, **kwargs)
    monkeypatch.setattr(assurance.subprocess, "run", watch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "made-up-key-for-tests-0123456789")
    marker = tmp_path / "ran.txt"
    hostile = {"kind": "step", "command": [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ran')"], "checker": "/bin/sh"}
    assert assurance.run_checker(hostile, {"command": ["sh", "-c", "true"], "step": {"prompt": "x"}}) == "reject"
    (argv, kwargs), = seen
    assert argv == [sys.executable, "-I", str(assurance.CHECKER_SOURCE)] and kwargs["shell"] is False
    assert kwargs["env"] == {"PATH": assurance.os.environ.get("PATH", "")} and "made-up-key" not in json.dumps(kwargs["env"])
    assert not marker.exists()
    # an entry too deep to read is rejected by the checker, or can't be given to it at all; it never raises here
    deep: dict = {}
    for _ in range(5000):
        deep = {"x": deep}
    assert assurance.run_checker({"kind": "step"}, deep) in ("reject", "unavailable")


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
