"""The cheating drills (sandbox research): each way to bend a proof, tried on purpose. Each must be caught.

A drill that needs a trial uses Otto's own harness, with our own registration (ottolab/sandbox.py) of a trial whose
files are the ones a real run registered (tests/sandbox/fixtures/lab). Only the measuring script is a stand-in: it
hands back the numbers a drill wants, where the real one would run containers and read the reviewer's reviews
(tests/sandbox/test_sandbox_real.py runs the real one). So what is tested is real: what we froze, how the harness
judges it against what we froze, and what the pack then says.

    1, 2   asking code that says yes (or no) to everything      test_sandbox_screens.py, and "the known-answer check" below
    3, 4   asking code that bends its answers                   test_sandbox_screens.py (the screen), and "the two authors" below
    5      the design changed after registration                below
    6      a copy changed after registration                    below (the frozen record), test_sandbox_copies.py (the image)
    7      the affected version gets everything right           below
    8      a design with no case that must be refused           test_sandbox_rules.py
    9      a second run to get a better draw                    below
    10     Claude declines, or no answer comes                  below
    11     a replay by the author who made the runs             below
    12     text that gives instructions                         test_sandbox_screens.py
    13     a pack of the second format signed by another key    test_sandbox_pack.py
    14     the reviewer file edited                             test_sandbox_rules.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from sandbox_fixtures import ADVISORY, LAB, lab_file

from app.otto import harness, model
from ottolab import build, prompts, research, sandbox
from tools import record_sandbox_answers as demo

# The stand-in for the measuring script: for each part of the trial, the numbers in a table beside it.
STUB = ('import json, os\nhere = os.path.dirname(os.path.abspath(__file__))\n'
        'table = json.load(open(os.path.join(here, "stub-metrics.json")))\n'
        'open(os.environ["OTTO_METRICS"], "w").write(json.dumps(table[os.environ["OTTO_ARM"]]))\n')
HONEST = {"reference": (64, 64), "affected": (63, 64), "fixed": (64, 64), "accept-all": (0, 64), "affected-b": (63, 64), "fixed-b": (64, 64),
          "more-fixed-1": (64, 64), "more-fixed-2": (64, 64)}


def _table(**changes) -> dict:
    out = {arm: {"right": right, "wrong": 64 - right, "total": 64, "agree": agree} for arm, (right, agree) in HONEST.items()}
    for arm, figures in changes.items():
        out[arm.replace("_", "-")].update(figures)
    return out


def _step(name: str, prompt: str, answer: str) -> model.Step:
    return model.Step(step=name, source="recorded", model=None, prompt=prompt, answer=answer, prompt_sha256=model.sha256_text(prompt),
                      answer_sha256=model.sha256_text(answer), input_tokens=0, output_tokens=0, cost_nano_usd=0, at=demo.AT, how=demo.HOW)


class Trial:
    """A lab with one registered trial on sandbox copies, ready to run."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lab = research.open_lab(root)
        (root / sandbox.TRIAL).write_text(STUB, encoding="utf-8")
        (root / sandbox.QUALIFY).write_text("# a stand-in: the known-answer files are the real run's\n", encoding="utf-8")
        shutil.copytree(LAB / "sandbox", root / "sandbox")
        self.advisory = demo.advisory()
        self.qid = self.lab.add(research.test_question(self.advisory, {"snapshot": "2026-11-22"}, "0" * 64), research.COORDINATOR)
        reading_answer = json.dumps(demo.READING)
        self.reading = prompts.check_reading(reading_answer, self.advisory)
        read = research.record_step(self.lab, self.qid, ADVISORY, _step("read_advisory", prompts.read_advisory_prompt(self.advisory), reading_answer),
                                    "used", self.reading, None)
        self.design = json.loads(lab_file("design").read_text(encoding="utf-8"))
        designed = research.record_step(self.lab, self.qid, ADVISORY, _step("design_test", "a design prompt", json.dumps(demo.DESIGN)), "used",
                                        {"decision": "test", "design": self.design, "expect": demo.DESIGN["expect"]}, None)
        drafts = []
        for author in ("a", "b"):
            answer = json.dumps(demo.ASKING[author])
            drafted = {"author": author, "attempt": 1, "screen_sha256": "0" * 64}
            drafts.append(sandbox._record_draft(self.lab, self.qid, ADVISORY, _step("write_wrapper", f"a prompt for author {author}", answer), "used",
                                                {"decision": "code", **demo.ASKING[author], **drafted}, None, drafted))
        for claim in (read, designed, *drafts):
            self.lab.verify(claim)             # the harness's own verify step: it runs the pinned checker on each record
        rel = {name: f"sandbox/{ADVISORY}/{lab_file(name).name}" for name in ("versions", "set-a", "known-a", "set-b", "known-b")}
        self.said = sandbox.register(self.lab, self.qid, self.advisory, self.reading, self.design, [read, designed, *drafts], rel["versions"],
                                     rel["set-a"], rel["known-a"], rel["set-b"], rel["known-b"])
        self.hid = research.trials_of(self.lab.state(), ADVISORY, "test", self.lab)[-1][0]
        self.files = rel

    def measure(self, table: dict) -> None:
        (self.root / "stub-metrics.json").write_text(json.dumps(table), encoding="utf-8")

    def go(self, table: dict, replay_by: str = research.VALIDATOR) -> dict:
        """Run every part once, have the harness judge, replay, and read what a pack would say of the test."""
        self.measure(table)
        self.lab.run(self.hid, research.EXECUTOR)
        self.lab.judge(self.hid)
        self.lab.replay(self.hid, replay_by)
        return self.entry()

    def entry(self) -> dict:
        return build.advisory_entry(self.lab, self.lab.state(), self.advisory)[0]["test"]


@pytest.fixture
def trial(tmp_path):
    return Trial(tmp_path / "lab")


pytestmark = pytest.mark.needs_otto         # (each drill drives the real harness through a whole trial; the file takes a few seconds)


def test_what_we_register_before_the_first_run(trial):
    hyp = trial.lab.state().get(trial.hid, "hypothesis")
    assert set(hyp["arms"]) == set(HONEST) and hyp["baseline"] == "reference"
    # everything a proof rests on is frozen by fingerprint: the design, both copy sets (so both pieces of asking code,
    # every file of every copy and both images), both known-answer checks, the chosen versions and the two scripts
    pinned = set(hyp["code"])
    assert {sandbox.TRIAL, sandbox.QUALIFY, *trial.files.values()} <= pinned and any(p.startswith("designs/") for p in pinned)
    assert any("/arms-" in p for p in pinned)
    for rel, digest in hyp["code"].items():
        assert hashlib.sha256((trial.root / rel).read_bytes()).hexdigest() == digest
    # the thresholds: the affected copy must get at least one case wrong (kill line: none wrong); the fixed copy and
    # every further fixed version exactly as many right as the reference; the control wrong on every must-reject case;
    # the second author's code the same answer on every case
    affected = next(p for p in hyp["predictions"] if p["arm"] == "affected")
    assert (affected["metric"], affected["direction"], affected["kill_below_ppm"]) == ("right", "decrease", 1)
    negatives = {(c["arm"], c["metric"]) for c in hyp["controls"] if c["kind"] == "negative" and c["max_abs_effect_ppm"] == 0}
    assert negatives == {("fixed", "right"), ("affected-b", "agree"), ("fixed-b", "agree"), ("more-fixed-1", "right"), ("more-fixed-2", "right")}
    positive = next(c for c in hyp["controls"] if c["kind"] == "positive")
    assert positive["arm"] == "accept-all" and positive["minimum_effect_ppm"] == research.PPM          # all 64 are must-reject cases
    assert hyp["budget"]["max_runs"] == 2 * len(hyp["arms"]) + 2
    assert any("written for this library by Claude" in c for c in hyp["confounders"])
    assert "a statement about how serious the weakness is" in hyp["claim_ceiling"]["forbids"]
    # the versions the frozen asking code does not work on were left out before, with the reason
    arms = json.loads(next((trial.root / "sandbox" / ADVISORY).glob("arms-*.json")).read_text())
    assert [v["version"] for v in arms["left_out"]] == ["1.1.0", "1.1.1"] or {v["version"] for v in arms["left_out"]} == {"1.1.0", "1.1.1"}


def test_a_trial_that_holds_is_offered(trial):
    test = trial.go(_table())
    assert test["state"] == "ready" and test["trial"]["outcome"] == "supported" and test["trial"]["replayed"] is True
    assert test["sandbox"]["registered"]["hypothesis"] == trial.hid and test["sandbox"]["second"] is not None


def test_drill_3_and_4_two_authors_whose_code_gives_different_answers_stop_the_trial(trial):
    """Asking code that bends its answers (it "knows" which copy it runs on, or does the checking itself for some
    inputs) can't bend them the same way as code written apart: one case of difference is enough."""
    test = trial.go(_table(affected_b={"agree": 63}))
    assert test["state"] == "not_offered" and test["trial"]["outcome"] != "supported"
    assert test["reason"] == ("Not offered: the two versions of the asking code gave different answers on 1 of 64 cases on "
                              "starkbank-ecdsa 2.0.0, so neither is relied on.")


def test_drill_5_a_design_changed_after_registration_is_not_run(trial):
    design = next((trial.root / "designs").glob("*.json"))
    design.write_text(design.read_text().replace('"InvalidSignature"', '"MissingZero"'), encoding="utf-8")
    trial.measure(_table())
    with pytest.raises(harness.module("lab").LabError, match="the instrument changed after preregistration"):
        trial.lab.run(trial.hid, research.EXECUTOR)
    assert trial.lab.state().runs(trial.hid) == []
    assert trial.entry()["state"] == "not_offered" and "did not finish" in trial.entry()["reason"]


def test_drill_6_a_copy_or_its_asking_code_changed_after_registration_is_not_run(trial):
    record = trial.root / trial.files["set-a"]
    record.write_text(record.read_text().replace("Ecdsa.verify(", "Ecdsa.verify (", 1), encoding="utf-8")      # one character of the asking code
    trial.measure(_table())
    with pytest.raises(harness.module("lab").LabError, match="the instrument changed after preregistration"):
        trial.lab.run(trial.hid, research.EXECUTOR)
    assert trial.lab.state().runs(trial.hid) == []


def test_drill_7_a_trial_in_which_the_affected_version_gets_everything_right_is_not_offered(trial):
    test = trial.go(_table(affected={"right": 64, "wrong": 0}, affected_b={"right": 64, "wrong": 0}))
    assert test["state"] == "not_offered" and test["trial"]["outcome"] == "refuted"
    assert "starkbank-ecdsa 2.0.0, the affected version, got all 64 selected cases right" in test["reason"]


def test_a_fixed_version_that_gets_a_case_wrong_means_the_check_is_not_offered(trial):
    test = trial.go(_table(more_fixed_1={"right": 63, "wrong": 1}))
    assert test["state"] == "not_offered"
    assert test["reason"] == ("Not offered: starkbank-ecdsa 2.0.2, a fixed version, got 1 of the 64 selected cases wrong, so this check does "
                              "not tell the fix from the weakness.")


def test_a_control_that_does_not_fail_on_every_case_means_the_run_can_catch_nothing(trial):
    test = trial.go(_table(accept_all={"right": 1, "wrong": 63}))
    assert test["state"] == "not_offered" and test["reason"] == "Not offered: the control that must fail did not fail on every case that must be rejected."


def test_drill_9_a_second_run_to_get_a_better_draw_is_not_made(trial):
    trial.measure(_table(affected={"right": 64, "wrong": 0}))                        # the first draw: the affected copy got all right
    first = trial.lab.run(trial.hid, research.EXECUTOR)
    assert len(first) == len(HONEST)
    trial.measure(_table())                                                          # "try again": better numbers this time
    assert trial.lab.run(trial.hid, research.EXECUTOR) == []                         # every part has its one completed run: nothing is rerun
    kept = {r["arm"]: r["metrics"] for _, r in trial.lab.state().runs(trial.hid)}
    assert kept["affected"]["wrong"] == 0 and len(trial.lab.state().runs(trial.hid)) == len(HONEST)
    trial.lab.judge(trial.hid)
    with pytest.raises(harness.module("lab").LabError, match="already has a decision"):
        trial.lab.run(trial.hid, research.EXECUTOR)
    with pytest.raises(harness.module("lab").LabError, match="already has a decision"):
        trial.lab.judge(trial.hid)
    assert trial.entry()["state"] == "not_offered"


def test_drill_11_a_replay_by_the_author_who_made_the_runs_does_not_count(trial):
    test = trial.go(_table(), replay_by=research.EXECUTOR)
    assert test["trial"]["outcome"] == "supported" and test["trial"]["replayed"] is False
    assert test["state"] == "not_offered" and "did not repeat when it was run again in a separate replay step" in test["reason"]


def test_a_replay_that_gives_other_numbers_does_not_count(trial):
    trial.measure(_table())
    trial.lab.run(trial.hid, research.EXECUTOR)
    trial.lab.judge(trial.hid)
    trial.measure(_table(affected={"right": 62, "wrong": 2}))
    trial.lab.replay(trial.hid, research.VALIDATOR)
    assert trial.entry()["state"] == "not_offered" and trial.entry()["trial"]["replayed"] is False


# ---------------------------------------------------------------- drill 10: no answer is a stop, never a result

class _NoAnswer:
    def ask(self, step, prompt):
        raise model.NoRecordedAnswer("No recorded answer: this needs Live Otto.")


@pytest.fixture
def before_the_asking_code(tmp_path, monkeypatch):
    """A lab in which the advisory was read and a test designed, as the research steps leave it; the next step is the
    asking code. The registry and the library's files are stand-ins (the real ones are in the slow real test)."""
    root = tmp_path / "lab"
    lab = research.open_lab(root)
    advisory = demo.advisory()
    qid = lab.add(research.test_question(advisory, {"snapshot": "2026-11-22"}, "0" * 64), research.COORDINATOR)
    reading_answer = json.dumps(demo.READING)
    reading = prompts.check_reading(reading_answer, advisory)
    read = research.record_step(lab, qid, ADVISORY, _step("read_advisory", prompts.read_advisory_prompt(advisory), reading_answer), "used", reading, None)
    design = json.loads(lab_file("design").read_text(encoding="utf-8"))
    designed = research.record_step(lab, qid, ADVISORY, _step("design_test", "a design prompt", json.dumps(demo.DESIGN)), "used",
                                    {"decision": "test", "design": design, "expect": "x"}, None)
    for claim in (read, designed):
        lab.verify(claim)
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"schema": sandbox.FACTS_SCHEMA, "advisories": {ADVISORY: {
        "library": "starkbank-ecdsa", "registry": "pypi", "package": "starkbank-ecdsa", "yours": ["2.0.0"],
        "ranges": [{"introduced": "0", "fixed": "2.0.1", "last_affected": None}]}}}), encoding="utf-8")
    for name, value in ((sandbox.ENV_ON, "1"), (sandbox.ENV_FACTS, str(facts)), (sandbox.ENV_STORE, str(tmp_path / "store")),
                        (sandbox.ENV_STOPS, str(tmp_path / "stops.jsonl"))):
        monkeypatch.setenv(name, value)
    versions = json.loads(lab_file("versions").read_text(encoding="utf-8"))
    monkeypatch.setattr(sandbox, "plan_versions", lambda lab_, advisory_, facts_, reading_: research._write_once(lab_, f"sandbox/{ADVISORY}", "versions", versions))
    from pathlib import PurePosixPath
    monkeypatch.setattr(sandbox.maker, "library_files", lambda *args: ({PurePosixPath("ellipticcurve/__init__.py"): b"x = 1\n"}, "A read-me.", {}))
    return lab, qid, advisory


def test_drill_10_no_answer_for_the_asking_code_is_a_stop_and_nothing_is_recorded_or_proposed(before_the_asking_code):
    lab, qid, advisory = before_the_asking_code
    head = lab.ledger.head()["head"]
    said = sandbox.propose_test(lab, _NoAnswer(), qid, advisory, {})
    assert said == f"{ADVISORY}: No recorded answer: this needs Live Otto."
    assert lab.ledger.head()["head"] == head                                         # nothing was added: not a refusal, not a dead end
    assert sandbox.stop_of(ADVISORY) == "No recorded answer: this needs Live Otto."
    assert build.unsettled(lab, lab.state(), ADVISORY, live=False) == "No recorded answer: this needs Live Otto."
    test = build.advisory_entry(lab, lab.state(), advisory)[0]["test"]
    assert test["state"] != "ready" and test["trial"] is None


class _Says:
    def __init__(self, answer: dict) -> None:
        self.answer = json.dumps(answer)

    def ask(self, step, prompt):
        return _step(step, prompt, self.answer)


def test_an_author_who_says_the_library_cant_be_asked_settles_it_with_the_reason(before_the_asking_code):
    lab, qid, advisory = before_the_asking_code
    cannot = _Says({"asking_code": "", "notes": "The library has no function that reads a signature in DER form."})
    sandbox.propose_test(lab, cannot, qid, advisory, {})
    for claim, _ in research.step_claims(lab.state(), ADVISORY):
        if not lab.state().settled(claim):
            lab.verify(claim)
    said = sandbox.propose_test(lab, cannot, qid, advisory, {})
    assert "No test yet: the library can't be asked this question." in said
    test = build.advisory_entry(lab, lab.state(), advisory)[0]["test"]
    assert test["state"] == "none" and test["reason"].startswith("No test yet: the library can't be asked this question.")
    assert build.unsettled(lab, lab.state(), ADVISORY, live=True) is None            # settled: it goes into the pack with its reason


def test_a_draft_the_screen_refuses_is_recorded_with_the_reason_and_three_drafts_are_the_most(before_the_asking_code):
    lab, qid, advisory = before_the_asking_code
    cheat = _Says({"asking_code": "from ellipticcurve import x\n\nOWN_REFUSALS = ()\n\n\ndef check_signature(public_key, message, signature):\n    return True\n",
                   "notes": ""})
    for _ in range(3):
        said = sandbox.propose_test(lab, cheat, qid, advisory, {})
        assert "was not let through" in said and "must return the library's own answer" in said
        for claim, _ in research.step_claims(lab.state(), ADVISORY):
            if not lab.state().settled(claim):
                lab.verify(claim)
    drafts = sandbox.drafts_of(lab.state(), lab, ADVISORY, "a")
    assert [art["outcome"] for _, art in drafts] == ["refused"] * 3 and all("must return" in art["refusal"] for _, art in drafts)
    said = sandbox.propose_test(lab, cheat, qid, advisory, {})
    assert "No test yet: the code that asks the library could not be made to work on starkbank-ecdsa (after 3 drafts by one author)." in said
    assert build.advisory_entry(lab, lab.state(), advisory)[0]["test"]["state"] == "none"
