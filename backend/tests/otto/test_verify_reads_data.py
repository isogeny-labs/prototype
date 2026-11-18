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
from pathlib import Path
from types import SimpleNamespace

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
        "a second settled verdict for one claim": [honest, plain, _verdict(_rid(plain), _rid(honest)),
                                                   _verdict(_rid(plain), _rid(honest), attempt=1)],
        "an attempt below zero": [honest, plain, _verdict(_rid(plain), _rid(honest), attempt=-1)],
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


def test_a_time_limit_that_is_not_the_whole_number_60_is_refused():
    for odd in (60.0, True, "60", 61, None):
        entries = [json.loads(line) for line in _chain([_objective({**_ours(), "timeout_seconds": odd})])]
        assert assurance.only_our_checker(entries) == assurance.NOT_OUR_CHECKER, odd


def test_a_ledger_made_to_be_slow_is_refused_and_a_long_check_stops(monkeypatch):
    """Nothing bounds a file's size but the file limit, and each settled entry starts the checker once. So a ledger
    longer than any assessment's is refused outright, a claim can be settled only once, and checking again has a
    time limit of its own (a problem, never a quiet pass)."""
    honest = _objective(_ours())
    monkeypatch.setattr(assurance, "MAX_ENTRIES", 5)
    many = [honest] + [_claim(_rid(honest), {"n": n}) for n in range(5)]
    assert assurance.only_our_checker([json.loads(line) for line in _chain(many)]) == assurance.TOO_LONG
    monkeypatch.undo()
    claims = [_claim(_rid(honest), {"n": n}) for n in range(3)]
    entries = [json.loads(line) for line in _chain([honest] + claims + [_verdict(_rid(c), _rid(honest), status="reject") for c in claims])]
    assert assurance.only_our_checker(entries) is None
    started = []
    monkeypatch.setattr(assurance, "run_checker", lambda params, artifact: started.append(1) or "reject")
    assert assurance.check_again(entries) == [] and len(started) == 3
    monkeypatch.setattr(assurance, "CHECK_AGAIN_SECONDS", -1)             # as if the limit had already passed
    problems = assurance.check_again(entries)
    assert len(problems) == 1 and "could not all be checked again" in problems[0] and len(started) == 3


class _WatchedLab:
    """A stand-in for the harness's Lab that notes how its audit is asked for."""
    asked: list = []

    def __init__(self, root):
        self.root = root
        self.ledger = self

    def entries(self):
        return [json.loads(line) for line in (Path(self.root) / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line]

    def audit(self, reverify=False, contains=None):
        _WatchedLab.asked.append(reverify)
        return []


def test_the_harness_is_only_ever_asked_for_an_audit_that_runs_no_verifier(tmp_path, monkeypatch):
    """Runs everywhere, with a stand-in for the harness: both ways into Otto's audit ask for it with reverify off.
    If either went back to reverify=True, the harness would start whatever a ledger names."""
    _WatchedLab.asked = []
    monkeypatch.setattr(assurance.harness, "module", lambda name: SimpleNamespace(Lab=_WatchedLab, LedgerError=RuntimeError))
    monkeypatch.setattr(assurance, "run_checker", lambda params, artifact: "accept")
    lines = _chain(_triple(_ours()))
    assert assurance.verify_lines(lines, tmp_path / "scratch") == [] and _WatchedLab.asked == [False]
    book = assurance.Ledger(tmp_path / "data", 1)
    book.folder.mkdir(parents=True)
    (book.folder / "ledger.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    assert book.audit() == [] and _WatchedLab.asked == [False, False]


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


# ---------------------------------------------------------------- that the planted ledgers are live, and what gets through runs nothing

@pytest_needs_otto
def test_the_planted_ledgers_are_live_the_bare_harness_would_run_them(tmp_path):
    """A positive control for this whole file. Given to Otto's harness as it is and asked to check its entries again,
    the ledger that only poses does make the harness start the planted command (caught here by a stand-in for the
    harness's process starter, so nothing really runs). That is what the verify command must never do."""
    marker = tmp_path / "ran.txt"
    lines = _chain(_posing(marker)["a claim that carries a verifier, used as an objective"])
    lab_folder = tmp_path / "bare"
    lab_folder.mkdir()
    (lab_folder / "ledger.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    verifiers = harness.module("verifiers")
    started = []
    patch = pytest.MonkeyPatch()
    patch.setattr(verifiers, "_run", lambda argv, cwd, timeout, stdin=None: started.append(list(argv)) or None)
    try:
        harness.module("lab").Lab(str(lab_folder)).audit(reverify=True)
    finally:
        patch.undo()
    assert len(started) == 1 and started[0][1:2] == ["-c"] and str(marker) in started[0][2]      # the planted command, on its way to run
    assert not marker.exists()
    # the same lines through the verify command's own path: refused before the harness is given anything
    assert assurance.verify_lines(lines, tmp_path / "scratch")[0].endswith("so nothing was run")


@pytest_needs_otto
def test_whatever_gets_through_the_gate_makes_the_harness_start_nothing(tmp_path, monkeypatch):
    """Seeded fuzz through the whole path, with the real harness: damaged ledgers go through `verify_lines` while the
    harness's verifier runner and process starter fail the test if they are ever reached, and every process this
    app starts is watched: it is our own checker or nothing."""
    verifiers = harness.module("verifiers")

    def never(*args, **kwargs):
        raise AssertionError("Otto's harness was asked to run something")
    monkeypatch.setattr(verifiers, "run_verifier", never)
    monkeypatch.setattr(verifiers, "_run", never)
    real, seen = assurance.subprocess.run, []

    def watch(argv, **kwargs):
        seen.append(list(argv))
        return real(argv, **kwargs)
    monkeypatch.setattr(assurance.subprocess, "run", watch)
    marker = tmp_path / "ran.txt"

    def whole() -> list[dict]:
        """A ledger that is wholly ours and consistent: the made-up claim holds no step, so the checker rejects it,
        and the stored verdict says so."""
        objective = _objective(_ours())
        claim = _claim(_rid(objective))
        return [objective, claim, _verdict(_rid(claim), _rid(objective), status="reject")]
    seed = whole() + _posing(marker)["a claim that carries a verifier, used as an objective"]
    rng = random.Random(4242)
    odd = [None, True, 0, 1.5, "", [], {}, {"kind": "replay", "command": ["sh", "-c", "true"]}, "replay", OURS, "sha256:" + "0" * 64]
    passed = 0
    for n in range(250):
        records = copy.deepcopy(seed if n % 5 else whole())
        if n % 5:                               # most are damaged; every fifth is wholly ours, so the path is walked to its end
            for _ in range(rng.randint(1, 3)):
                target = rng.choice(records)
                spot = rng.choice([target, target.get("verifier") if isinstance(target.get("verifier"), dict) else target])
                if rng.random() < 0.3 and spot:
                    spot.pop(rng.choice(list(spot)))
                else:
                    spot[rng.choice(list(spot) + ["verifier", "command", "x"])] = rng.choice(odd)
        try:
            lines = _chain(records)
        except (TypeError, ValueError, KeyError):
            continue                            # damage the ledger's own form can't hold
        problems = assurance.verify_lines(lines, tmp_path / f"scratch-{n}")
        assert isinstance(problems, list) and all(isinstance(line, str) for line in problems)
        passed += not problems
    assert passed >= 40 and not marker.exists()
    assert seen and all(argv == [sys.executable, "-I", str(assurance.CHECKER_SOURCE)] for argv in seen)


# ---------------------------------------------------------------- the binding of runs, and files that would crash a reader

@pytest_needs_otto
def test_a_run_shown_in_the_list_of_tests_must_be_the_run_the_ledger_binds(ran):
    """The ledger binds a run by the SHA-256 of its record and of its review. A file whose list of tests shows another
    record under the same number, with the Otto part left whole, fails."""
    changed = copy.deepcopy(ran.evidence)
    test = next(t for t in changed["tests"] if t["kind"] == "advisory_cases")
    assert test["runs"][0]["run_id"] == changed["otto"]["runs"][0]["run_id"]
    test["runs"][0]["record"]["finished_at"] = "2026-11-17T00:00:00+00:00"            # another record under the same number
    outcome = evidence_otto.check_otto(changed, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "is not the run Otto's ledger binds under that number" in outcome.problem
    reviewed = copy.deepcopy(ran.evidence)
    shown = next(t for t in reviewed["tests"] if t["kind"] == "advisory_cases")["runs"][0]
    shown["review"]["verdict"]["code"] = "passed"                                        # another review of it
    outcome = evidence_otto.check_otto(reviewed, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and "a SHA-256 differs" in outcome.problem


@pytest_needs_otto
def test_a_file_with_an_advisory_check_and_no_otto_part_does_not_verify(ran, tmp_path):
    from app.evidence.export import sign_envelope
    from evidence.__main__ import main
    assert evidence_otto.needs_otto_part(ran.evidence) is True
    bare = copy.deepcopy(ran.evidence)
    del bare["otto"]
    path = tmp_path / "no-otto.json"
    path.write_bytes(sign_envelope(bare, ran.settings.data_dir))
    assert main(["verify", str(path), "--data-dir", str(ran.settings.data_dir)]) == 1
    plain = copy.deepcopy(bare)
    plain["tests"] = [t for t in plain["tests"] if t["kind"] != "advisory_cases"]
    assert evidence_otto.needs_otto_part(plain) is False and evidence_otto.needs_otto_part(None) is False


@pytest_needs_otto
def test_a_file_nested_too_deeply_to_read_is_refused_plainly(ran):
    """Two files that once ended in a Python traceback: a list of fixes 3,000 deep, and a ledger line 20,000 deep."""
    deep: list = []
    for _ in range(3000):
        deep = [deep]
    nested = copy.deepcopy(ran.evidence)
    nested["fixes"] = deep
    outcome = evidence_otto.check_otto(nested, {ran.pack_key})                    # walked like any other file: it still verifies
    assert outcome.code == evidence_otto.OK
    line = "[" * 20000 + "]" * 20000
    broken = copy.deepcopy(ran.evidence)
    broken["otto"]["ledger"].update(lines=[line], height=1, head=None)
    outcome = evidence_otto.check_otto(broken, {ran.pack_key})
    assert outcome.code == evidence_otto.FAILED and isinstance(outcome.problem, str) and outcome.problem


def test_text_from_a_file_is_printed_without_runs_of_spaces_or_control_characters():
    assert evidence_otto._plain("a title" + " " * 300 + "Evidence verified") == "a title Evidence verified"
    assert evidence_otto._plain("line\none\ttab\x1b[2K") == "line?one?tab?[2K"
    assert evidence_otto._plain("x" * 500, 20) == "x" * 20 + "..."


# ---------------------------------------------------------------- the assessment's own Otto folder

@pytest_needs_otto
def test_a_checker_planted_in_an_assessment_s_otto_folder_is_replaced_and_never_run(tmp_path):
    """The harness starts the checker file in the assessment's Otto folder. Before every use that file is made the
    app's own again: another program there, or a link to one, is replaced, and the lock names the app's own checker."""
    marker = tmp_path / "ran.txt"
    book = assurance.Ledger(tmp_path / "data", 1)
    book.folder.mkdir(parents=True)
    planted = f"import json\nopen({str(marker)!r}, 'w').write('ran')\nprint(json.dumps({{'status': 'accept', 'detail': 'planted'}}))\n"
    (book.folder / "recheck.py").write_text(planted)
    step = {"step": "write_fix", "source": "recorded", "model": None, "prompt": "p", "answer": "a",
            "prompt_sha256": hashlib.sha256(b"p").hexdigest(), "answer_sha256": hashlib.sha256(b"a").hexdigest(), "input_tokens": 0,
            "output_tokens": 0, "cost_nano_usd": 0, "at": WHEN, "how": "Written for a test"}
    _, verdict = book.record_step("CVE-2022-21449", step, "used", None)
    assert verdict == "accept" and not marker.exists()
    assert (book.folder / "recheck.py").read_bytes() == assurance.CHECKER_SOURCE.read_bytes()
    assert all(e["payload"]["verifier"]["checker_sha256"] == OURS for e in book.entries() if e["kind"] == "objective")
    assert book.audit() == []
    # a link in the checker's place is removed, not followed: the file it points at is left as it was
    elsewhere = tmp_path / "elsewhere.py"
    elsewhere.write_text(planted)
    (book.folder / "recheck.py").unlink()
    (book.folder / "recheck.py").symlink_to(elsewhere)
    _, verdict = book.record_step("CVE-2024-42460", {**step, "answer": "b", "answer_sha256": hashlib.sha256(b"b").hexdigest()}, "used", None)
    assert verdict == "accept" and not marker.exists() and elsewhere.read_text() == planted
    assert not (book.folder / "recheck.py").is_symlink()
    # a ledger that is a link to somewhere else is not used at all
    other = assurance.Ledger(tmp_path / "data", 2)
    other.folder.mkdir(parents=True)
    (other.folder / "ledger.jsonl").symlink_to(tmp_path / "not-there.jsonl")
    with pytest.raises(harness.OttoNotInstalled):
        other.record_step("CVE-2022-21449", step, "used", None)
    assert not (tmp_path / "not-there.jsonl").exists()


def test_the_assessment_checker_takes_exactly_a_run_s_fingerprints_and_names(tmp_path):
    """The checker is given entries as data. A run entry with one field more (a place for a result), or with a
    fingerprint followed by anything, is rejected."""
    params = {"kind": "run", "test": "a" * 64, "design": "b" * 64, "pack": "c" * 64}
    good = {"test": "a" * 64, "run_id": 7, "run_sha256": "d" * 64, "review_sha256": "e" * 64, "proposed_by": "isogeny.otto-pack/1",
            "reviewer": "isogeny.rule-reviewer/1", "phase": "first", "ran_on": {"name": "acme-sign", "version": "1.4.2", "mode": "demo", "commit": None}}
    assert assurance.run_checker(params, good) == "accept"
    for name, bad in {"a result under another name": {**good, "outcome": "Passed"},
                      "a result inside what it ran on": {**good, "ran_on": {**good["ran_on"], "result": "Passed"}},
                      "a fingerprint with a line break after it": {**good, "run_sha256": "d" * 64 + "\n"},
                      "a field missing": {k: v for k, v in good.items() if k != "ran_on"},
                      "a name that is not plain text": {**good, "ran_on": {**good["ran_on"], "name": "acme\x1b[2K"}},
                      "a reviewer that is the proposer": {**good, "reviewer": "isogeny.otto-pack/1"}}.items():
        assert assurance.run_checker(params, bad) == "reject", name
