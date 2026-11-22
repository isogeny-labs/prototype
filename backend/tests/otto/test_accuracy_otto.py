"""Phase 5c: how the accuracy check grades Otto's loop against the fifth answer key (demo/expected-otto.json).

The key is written independently of the build, so it is not in the repository until its author adds it. These tests
use keys made up for the test, and a stand-in for the walk itself (the real walk is run by the command; it takes
minutes). They hold the rules of the grading: a missing answer is a mismatch, nothing is graded without a key, and
the command never writes the key."""
import json

import pytest

from app import accuracy, accuracy_otto
from app.otto import harness

ANSWERS = {"packs.order": ["2026.11.1", "2026.11.2"], "pack.2026.11.1.CVE-2022-21449.test": "ready",
           "acme.first.CVE-2022-21449.result": "Failed", "acme.first.CVE-2022-21449.wrong_cases": ["168", "171", "364"],
           "real.demo_mode.advisory_check_on_a_real_library": "Couldn't run (needs isolated mode)"}


def _walk(answers=ANSWERS, stopped=None):
    return lambda settings=None, say=None: {"mode": "demo", "notes": [], "stopped": stopped, "answers": dict(answers)}


def test_every_question_of_the_key_is_graded_and_a_missing_answer_is_a_mismatch():
    key = {"answers": {**ANSWERS, "acme.fix.status": "ready"}}
    report = accuracy_otto.compare_otto(key, ANSWERS)
    assert (report["matched"], report["total"], report["not_applicable"]) == (5, 6, 0)
    missing = next(line for line in report["lines"] if line["id"] == "acme.fix.status")
    assert missing["match"] is False and missing["actual"] == "(no answer)"
    wrong = accuracy_otto.compare_otto({"answers": {"acme.first.CVE-2022-21449.result": "Passed"}}, ANSWERS)
    assert (wrong["matched"], wrong["total"]) == (0, 1) and wrong["lines"][0]["expected"] == "Passed" and wrong["lines"][0]["actual"] == "Failed"
    # an answer the key does not ask about is not graded (the key decides what is asked)
    assert accuracy_otto.compare_otto({"answers": {"packs.order": ANSWERS["packs.order"]}}, ANSWERS)["total"] == 1


def test_a_question_for_the_other_mode_is_listed_as_not_graded_never_as_a_match():
    key = {"answers": {"real.first.elliptic 6.5.6.CVE-2024-42460.result": "Failed", "real.retest.elliptic 6.5.7.CVE-2024-42460.result": "Passed",
                       "real.demo_mode.advisory_check_on_a_real_library": "Couldn't run (needs isolated mode)"}}
    in_demo = accuracy_otto.compare_otto(key, ANSWERS)
    assert (in_demo["matched"], in_demo["total"], in_demo["not_applicable"]) == (1, 1, 2)
    isolated = {k: v for k, v in ANSWERS.items() if not k.startswith("real.")}
    isolated["real.first.elliptic 6.5.6.CVE-2024-42460.result"] = "Failed"
    in_isolated = accuracy_otto.compare_otto(key, isolated)
    # in isolated mode the demo-mode question does not apply, and the retest that was not answered is a mismatch
    assert (in_isolated["matched"], in_isolated["total"], in_isolated["not_applicable"]) == (1, 2, 1)


@pytest.mark.parametrize("key", [None, [], {"answers": []}, {"questions": {}}, "ready"])
def test_a_key_that_is_not_in_the_form_the_doc_describes_is_a_mismatch_not_silence(key):
    report = accuracy_otto.compare_otto(key, ANSWERS)
    assert (report["matched"], report["total"]) == (0, 1) and "OTTO-KEY.md" in report["lines"][0]["what"]


def test_without_a_key_the_answers_are_shown_and_nothing_is_graded(monkeypatch, tmp_path):
    said = []
    monkeypatch.setattr(accuracy_otto, "EXPECTED_OTTO_JSON", tmp_path / "expected-otto.json")
    monkeypatch.setattr(accuracy_otto, "collect_otto", _walk())
    monkeypatch.setattr(harness, "status", lambda *a, **k: harness.OttoStatus(True, None, "isogeny-labs/otto", "a" * 40, "0.1.0", tmp_path))
    assert accuracy_otto.print_otto_report(None, said.append, required=True) == accuracy_otto.NO_KEY == 2
    assert accuracy_otto.print_otto_report(None, said.append) == 0          # in a run of everything, a key that is not there yet fails nothing
    text = "\n".join(said)
    assert 'acme.first.CVE-2022-21449.result = "Failed"' in text and "NOT COMPARED" in text and "MATCH" not in text.replace("MISMATCH", "")
    assert not (tmp_path / "expected-otto.json").exists()                  # the command never writes the key
    # a walk that stopped early is a failure even without a key
    monkeypatch.setattr(accuracy_otto, "collect_otto", _walk(stopped="The check stopped early: something broke"))
    assert accuracy_otto.print_otto_report(None, said.append) == 1 and any("PROBLEM" in line for line in said)


def test_with_a_key_the_exit_code_is_0_only_if_every_answer_matches_and_the_walk_finished(monkeypatch, tmp_path):
    key_file = tmp_path / "expected-otto.json"
    key_file.write_text(json.dumps({"answers": ANSWERS}), encoding="utf-8")
    before = key_file.read_bytes()
    monkeypatch.setattr(accuracy_otto, "EXPECTED_OTTO_JSON", key_file)
    monkeypatch.setattr(harness, "status", lambda *a, **k: harness.OttoStatus(True, None, "isogeny-labs/otto", "a" * 40, "0.1.0", tmp_path))
    said = []
    monkeypatch.setattr(accuracy_otto, "collect_otto", _walk())
    assert accuracy_otto.print_otto_report(None, said.append, required=True) == 0 and said[-1] == "Otto accuracy (demo mode): 5 of 5 match"
    monkeypatch.setattr(accuracy_otto, "collect_otto", _walk({**ANSWERS, "acme.first.CVE-2022-21449.result": "Passed"}))
    assert accuracy_otto.print_otto_report(None, said.append) == 1 and any(line.startswith("  MISMATCH  acme.first.CVE-2022-21449.result") for line in said)
    monkeypatch.setattr(accuracy_otto, "collect_otto", _walk(stopped="The check stopped early: something broke"))
    assert accuracy_otto.print_otto_report(None, said.append) == 1
    key_file.write_text("{not json", encoding="utf-8")
    assert accuracy_otto.print_otto_report(None, said.append) == 1 and any("could not be read" in line for line in said)
    key_file.write_bytes(before)
    assert key_file.read_bytes() == before


def test_without_otto_nothing_is_graded_and_asking_for_this_part_alone_says_so_with_its_own_exit_code(monkeypatch, tmp_path):
    missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
    monkeypatch.setattr(harness, "status", lambda *a, **k: missing)
    monkeypatch.setattr(accuracy_otto, "collect_otto", lambda *a, **k: pytest.fail("the walk must not start without Otto"))
    said = []
    assert accuracy_otto.print_otto_report(None, said.append, required=True) == accuracy_otto.NO_OTTO == 3
    assert accuracy_otto.print_otto_report(None, said.append) == 0
    assert any("NOT RUN" in line and "Otto is not installed on this computer" in line for line in said)


def test_the_command_takes_otto_as_a_part_and_leaves_the_four_keys_as_they_were(monkeypatch, capsys, tmp_path):
    """`--only otto` runs this part alone. A run of everything grades the four keys as before, and Otto's only once
    its key is there."""
    asked = []
    monkeypatch.setattr(accuracy_otto, "print_otto_report", lambda settings, say=print, required=False: asked.append(required) or 2)
    assert accuracy.main(["--only", "otto", "--mode", "demo"]) == 2 and asked == [True]
    for name in ("print_report", "print_migration_report"):
        monkeypatch.setattr(accuracy, name, lambda *a, **k: 0)
    monkeypatch.setattr(accuracy, "run_accuracy", lambda settings: {})
    monkeypatch.setattr("app.accuracy_real.print_real_report", lambda settings: 0)
    monkeypatch.setattr("app.accuracy_deps.print_dependencies_report", lambda settings: 0)
    monkeypatch.setattr(accuracy_otto, "EXPECTED_OTTO_JSON", tmp_path / "expected-otto.json")
    assert accuracy.main(["--mode", "demo"]) == 0 and asked == [True]       # no key: Otto's part is not run, and says so
    assert "Otto accuracy: not graded here" in capsys.readouterr().out
    (tmp_path / "expected-otto.json").write_text("{}", encoding="utf-8")
    assert accuracy.main(["--mode", "demo"]) == 2 and asked == [True, False]


# ---------------------------------------------------------------- sandbox research (a prototype): its questions

def test_the_sandbox_questions_are_graded_in_isolated_mode_and_the_switch_in_both():
    """docs/OTTO-KEY.md, "Sandbox research". Its walk needs containers; only the switch can be asked about everywhere,
    and whether it can be turned on in demo mode is a question for demo mode."""
    key = {"answers": {"sandbox.switch.default": False, "sandbox.demo_mode.can_turn_on": False,
                       "sandbox.trial.CVE-2021-43572.affected.wrong": 1, "sandbox.check.CVE-2021-43572.result": "Failed",
                       "sandbox.evidence.verify": 0}}
    in_demo = {**ANSWERS, "sandbox.switch.default": False, "sandbox.demo_mode.can_turn_on": False}
    report = accuracy_otto.compare_otto(key, in_demo)
    assert (report["matched"], report["total"], report["not_applicable"]) == (2, 2, 3)
    isolated = {k: v for k, v in ANSWERS.items() if not k.startswith("real.")}
    isolated.update({"sandbox.switch.default": False, "sandbox.trial.CVE-2021-43572.affected.wrong": 1, "sandbox.evidence.verify": 0})
    report = accuracy_otto.compare_otto(key, isolated)
    assert (report["matched"], report["total"], report["not_applicable"]) == (3, 4, 1)          # the check's result has no answer: a mismatch
    assert next(line for line in report["lines"] if line["id"] == "sandbox.check.CVE-2021-43572.result")["actual"] == "(no answer)"


def test_in_demo_mode_the_sandbox_walk_asks_about_the_switch_only_and_leaves_the_computer_as_it_was(settings, monkeypatch):
    """The plan asked for the new questions in `--only otto`. In demo mode two of them have an answer; the walk marks its
    own scratch copy as the sandbox and takes the mark off again."""
    import os

    from app.config import SANDBOX_ENV
    monkeypatch.delenv(SANDBOX_ENV, raising=False)
    monkeypatch.setenv("EVIDENCE_LAB_REGISTRY_SOURCE", "/a/folder/that/was/set/before")
    answers: dict = {}
    notes: list[str] = []
    accuracy_otto._sandbox_walk(settings, answers, notes, lambda text: None)
    assert answers == {"sandbox.switch.default": False, "sandbox.demo_mode.can_turn_on": False}
    assert len(notes) == 1 and "need isolated mode" in notes[0]
    assert SANDBOX_ENV not in os.environ and os.environ["EVIDENCE_LAB_REGISTRY_SOURCE"] == "/a/folder/that/was/set/before"
    # every question docs/OTTO-KEY.md lists for sandbox research is one the walk can answer (by its name)
    from app.config import REPO_ROOT
    doc = (REPO_ROOT / "docs" / "OTTO-KEY.md").read_text(encoding="utf-8")
    listed = {line.split("`")[1] for line in doc.splitlines() if line.startswith("| `sandbox.")}
    source = open(accuracy_otto.__file__, encoding="utf-8").read()
    for question in listed:
        stem = question.replace("<item>", "{SANDBOX_ITEM}").replace("<advisory>", "{SANDBOX_ID}")
        tail = stem.split("}")[-1] if "}" in stem else stem
        assert stem in source or (tail and tail in source), question
