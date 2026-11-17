"""The research side's records in Otto's own terms, and the steps that need judgement.

Adam's harness does everything mechanical itself: it runs the arms of an experiment, judges them against the
thresholds frozen in the registration, replays them under a second author, and runs the pinned checker on a claim.
What it hands to an "agent" are the steps that need judgement. This module is that agent's work, and each step that
needs judgement asks Claude (recorded answers by default, live with a key):

    propose    for a question about an advisory's test: read the advisory, design a test, and register the trial of
               that design on public copies. For a question about its fix: ask for the publisher's fixed version and
               register the trial of the update.
    distill    after a trial is settled: state what was learned as a fact (a dead end when the trial was refuted).
    formalize  record that a measurement on public copies has nothing that can be proven exactly.

Every Claude step is put into the ledger as a claim: the full prompt, the full answer, where the answer came from,
the model, the tokens and the cost, and both SHA-256. A pinned checker confirms the record is whole.

Nothing here judges a trial and nothing here decides a test result. A lab is acted on only through the harness's own
functions (the ones its command line calls); the ledger file is never written by this code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from app.canonical import canonical_bytes
from app.otto import designs, harness
from app.otto.model import ModelError, OttoModel
from app.run import components
from ottolab import prompts, snapshot

PINNED = Path(__file__).with_name("pinned")
TRIAL, CHECKER = "trial.py", "check_model_step.py"
COORDINATOR, AGENT, EXECUTOR, VALIDATOR = "otto-coordinator", "otto-agent", "otto-executor", "otto-validator"
FIX_SCHEMA = "isogeny.advisory-fix/1"
STANDARD_TESTS = ["official_vectors", "bad_signatures"]     # the pass-or-fail tests every ECDSA P-256 program gets
PPM = 1_000_000
RUN_SECONDS = 900
_SCOPE = re.compile(r"^advisory=([A-Z0-9-]+); kind=(test|fix)(?:; test=(sha256:[0-9a-f]{64}))?;")


class ResearchError(Exception):
    """The research step can't go on. str(exc) is one plain sentence."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def open_lab(root: Path):
    """The Otto lab in this folder (made if it is not there yet), with the two pinned scripts in it."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / "ledger.jsonl"
    if not ledger.exists():
        ledger.touch()
    for name in (TRIAL, CHECKER):
        source, target = PINNED / name, root / name
        if not target.exists():
            shutil.copyfile(source, target)
        elif target.read_bytes() != source.read_bytes():
            raise ResearchError(f"The lab's {name} is not the one in ottolab/pinned. A changed instrument needs a new lab: "
                                "earlier trials were registered with the old one.")
    return harness.module("lab").Lab(str(root))


# ---------------------------------------------------------------- questions (the coordinator's)

def test_question(advisory: dict, snap: dict, snapshot_sha256: str) -> dict:
    package = advisory["package"]
    return {"type": "question",
            "title": f"Can the lab's runner show the weakness in {advisory['id']}?",
            "decision_target": f"Ship a tried test for {advisory['id']} in the next test pack, or say why there is none.",
            "scope": (f"advisory={advisory['id']}; kind=test; {package['name']} ({package['ecosystem']}); the published text in snapshot "
                      f"{snap['snapshot']} (SHA-256 {snapshot_sha256}); the building blocks of this version."),
            "motivation": "A published weakness should become a locked test with a control that must fail, tried on public copies before it ships.",
            "constraints": "Only published test cases the existing runner can run. No code in a design. Public copies only, never a customer's system."}


def fix_question(advisory: dict, test_hypothesis: str) -> dict:
    package = advisory["package"]
    return {"type": "question",
            "title": f"Does the publisher's fixed version of {package['name']} remove the weakness in {advisory['id']} and leave every other locked test passing?",
            "decision_target": f"Offer the publisher's fix for {advisory['id']} as proven in the next test pack, or as not proven with the reason.",
            "scope": (f"advisory={advisory['id']}; kind=fix; test={test_hypothesis}; public copies of {package['name']}; the pass-or-fail tests of the "
                      "plan and every advisory check that held its own trial."),
            "motivation": "A fix ships only if, on public copies, the advisory check passes after it and every other locked test still passes.",
            "constraints": "Only the publisher's own fixed version, with its quoted source. Other people's code is never changed. Speed is not part "
                           "of the trial: timings hold only for the computer they are measured on."}


def question_about(record: dict) -> tuple[str, str, str | None] | None:
    """(advisory id, "test" or "fix", the test hypothesis a fix question builds on) of one of our questions."""
    found = _SCOPE.match(str(record.get("scope") or ""))
    return (found.group(1), found.group(2), found.group(3)) if found else None


def find_question(st, advisory_id: str, kind: str) -> str | None:
    for qid, q in st.of("question"):
        about = question_about(q)
        if about and about[:2] == (advisory_id, kind):
            return qid
    return None


# ---------------------------------------------------------------- reading the ledger

def step_claims(st, advisory_id: str) -> list[tuple[str, dict]]:
    """Every Claude step recorded for one advisory: (claim id, claim), oldest first."""
    return [(cid, c) for cid, c in st.of("claim") if isinstance(c["artifact"].get("step"), dict) and c["artifact"].get("advisory") == advisory_id]


def used_step(st, lab, advisory_id: str, step: str) -> tuple[str, dict] | None:
    """The newest accepted, used Claude step of this kind for this advisory."""
    for cid, claim in reversed(step_claims(st, advisory_id)):
        art = claim["artifact"]
        if art["step"]["step"] == step and art.get("outcome") == "used" and lab._accepted(cid, st):
            return cid, claim
    return None


def same_check_as(st, advisory_id: str, design: dict) -> str | None:
    """The other advisory whose design already selects exactly these published cases, if there is one. Two advisories
    with the same cases would be one check under two names, and a trial on public copies could not tell their
    weaknesses apart: where the same release fixes both, the affected version fails and the fixed one passes for
    either. So only the first advisory gets the check."""
    def cases_of(made: dict) -> tuple:
        return made["cases"]["file"], made["cases"]["sha256"], tuple(sorted(made["cases"]["ids"]))
    mine = cases_of(design)
    for _, claim in st.of("claim"):
        art = claim["artifact"]
        if not isinstance(art.get("step"), dict) or art["step"].get("step") != "design_test" or art.get("outcome") != "used" \
                or art.get("advisory") == advisory_id:
            continue
        parsed = art.get("parsed") or {}
        if parsed.get("decision") == "test" and cases_of(parsed["design"]) == mine:
            return str(art["advisory"])
    return None


def trial_kind(hyp: dict) -> str:
    return "fix" if any(path.startswith("fixes/") for path in hyp["code"]) else "test"


def trial_file(lab, hyp: dict) -> dict:
    """The design file (a test trial) or the fix file (a fix trial) a registered experiment is about."""
    prefix = "fixes/" if trial_kind(hyp) == "fix" else "designs/"
    path = next(p for p in sorted(hyp["code"]) if p.startswith(prefix))
    return json.loads(Path(lab.path(path)).read_text(encoding="utf-8"))


def trials_of(st, advisory_id: str, kind: str, lab) -> list[tuple[str, dict]]:
    out = []
    for hid, hyp in st.of("hypothesis"):
        if trial_kind(hyp) == kind and trial_file(lab, hyp).get("advisory") == advisory_id:
            out.append((hid, hyp))
    return out


def held(st, lab, hid: str) -> bool:
    """Did this trial hold: supported by the harness's judgement and replayed by a second author with no mismatch?"""
    decision = st.decision(hid)
    return bool(decision and decision[1]["outcome"] == "supported" and lab.standing(hid, st) == "corroborated")


def ready_designs(st, lab) -> list[tuple[str, dict, str]]:
    """Every design whose trial held: (its file in the lab, the design, its SHA-256), in ledger order."""
    out = []
    for hid, hyp in st.of("hypothesis"):
        if trial_kind(hyp) == "test" and held(st, lab, hid):
            path = next(p for p in sorted(hyp["code"]) if p.startswith("designs/"))
            design = json.loads(Path(lab.path(path)).read_text(encoding="utf-8"))
            out.append((path, design, designs.design_sha256(design)))
    return out


def public_copies(package: str, fixed_version: str) -> tuple[str, str] | None:
    """(the affected version, the fixed version) this app has as runnable copies of that library, or None. The
    affected copy is the newest registered version older than the fixed one."""
    versions = components.versions_of(package)
    if fixed_version not in versions or versions.index(fixed_version) == 0:
        return None
    return versions[versions.index(fixed_version) - 1], fixed_version


# ---------------------------------------------------------------- one Claude step, into the ledger

def record_step(lab, question_id: str, advisory_id: str, step, outcome: str, parsed: dict | None, refusal: str | None) -> str:
    """One Claude step as an objective and a claim under the pinned checker. Returns the claim's id; the harness's
    verify step then runs the checker on it."""
    what = {"read_advisory": "reading of the advisory", "design_test": "design note for a test", "propose_fix": "proposed fix"}[step.step]
    objective = lab.add({"type": "objective", "question_id": question_id,
                         "statement": f"The record of Otto's {what} for {advisory_id} is whole: the prompt and the answer are there with their "
                                      "SHA-256, the source of the answer is named, and every line it quotes stands in the prompt.",
                         "verifier": {"kind": "certificate", "checker": CHECKER, "checker_sha256": file_sha256(Path(lab.root) / CHECKER),
                                      "params": {"step": step.step, "advisory": advisory_id}, "timeout_seconds": 60}}, AGENT)
    artifact: dict = {"advisory": advisory_id, "step": step.record(), "outcome": outcome}
    if parsed is not None:
        artifact["parsed"] = parsed
    if refusal is not None:
        artifact["refusal"] = refusal
    return lab.add({"type": "claim", "objective_id": objective, "artifact": artifact, "cites": []}, AGENT)


def ask(lab, model: OttoModel, question_id: str, advisory: dict, step_name: str, prompt: str, check) -> tuple[str, dict | None, dict]:
    """Ask Claude one step, check the answer, and put the step into the ledger whichever way the check went.
    Returns (the claim id, the checked answer or None when it was refused, the step's record)."""
    step = model.ask(step_name, prompt)          # raises ModelError when there is no answer at all: nothing is recorded
    try:
        parsed = check(step)
        return record_step(lab, question_id, advisory["id"], step, "used", parsed, None), parsed, step.record()
    except prompts.Refused as exc:
        return record_step(lab, question_id, advisory["id"], step, "refused", None, str(exc)), None, step.record()


# ---------------------------------------------------------------- the steps that need judgement

def _write_once(lab, folder: str, name: str, data: dict) -> str:
    """Write a design or a fix file into the lab under a name that holds its own fingerprint. An existing file is
    never changed: frozen means frozen."""
    text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    digest = hashlib.sha256(canonical_bytes(data)).hexdigest()
    rel = f"{folder}/{name}-{digest[:12]}.json"
    path = Path(lab.path(rel))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    elif path.read_text(encoding="utf-8") != text:
        raise ResearchError(f"{rel} exists with other content.")
    return rel


def propose_test(lab, model: OttoModel, question_id: str, advisory: dict) -> str:
    """Read the advisory, design a test, and register its trial on public copies. Returns one plain line."""
    st = lab.state()
    aid, package = advisory["id"], advisory["package"]["name"]
    if not any(c["artifact"]["step"]["step"] == "read_advisory" for _, c in step_claims(st, aid)):
        claim, reading, _ = ask(lab, model, question_id, advisory, "read_advisory", prompts.read_advisory_prompt(advisory),
                                lambda step: prompts.check_reading(step.answer, advisory))
        if reading is None:
            return f"{aid}: the reading was refused; nothing more is asked."
        return f"{aid}: the advisory was read ({reading['plain_name']}). The record goes to the checker next."
    found = used_step(st, lab, aid, "read_advisory")
    if found is None:     # asked once already: a refused reading, or a record the checker did not accept, is not asked again
        return f"{aid}: there is no usable reading of this advisory; nothing more is asked."
    read_claim, read = found
    reading = read["artifact"]["parsed"]
    if not any(c["artifact"]["step"]["step"] == "design_test" for _, c in step_claims(st, aid)):
        prompt = prompts.design_test_prompt(advisory, reading)

        def checked(step) -> dict:
            made = prompts.check_design_note(step.answer, advisory, reading,
                                             {"prompt_sha256": step.prompt_sha256, "answer_sha256": step.answer_sha256})
            twin = same_check_as(st, aid, made["design"]) if made["decision"] == "test" else None
            if twin is not None:
                raise prompts.Refused(f"The design selects exactly the published cases of the check for {twin}. That would be the same "
                                      "check under a second name: it could not tell this advisory's weakness from that one's.")
            return made
        claim, note, record = ask(lab, model, question_id, advisory, "design_test", prompt, checked)
        if note is None:
            return f"{aid}: the design note was refused; no test is registered."
        if note["decision"] == "no_test":
            return f"{aid}: no test fits ({note['reason']})"
        return f"{aid}: a test was designed ({len(note['design']['cases']['ids'])} cases). The record goes to the checker next."
    design_claim, designed = used_step(st, lab, aid, "design_test") or (None, None)
    if designed is None or designed["artifact"]["parsed"]["decision"] != "test":
        return f"{aid}: no design to try."
    if trials_of(st, aid, "test", lab):
        return f"{aid}: its trial is already registered."
    design = designs.check_design(designed["artifact"]["parsed"]["design"])
    fixed = (reading.get("fixed") or {}).get("version")
    copies = public_copies(package, fixed) if fixed else None
    if copies is None:
        return f"{aid}: no public copies of an affected and a fixed version of {package} to try the design on; no trial is registered."
    affected, fixed = copies
    rel = _write_once(lab, "designs", aid, design)
    total, invalid = len(design["cases"]["ids"]), design["cases"]["must_reject"]

    def arm(version: str, report: str, description: str) -> dict:
        return {"command": ["python3", TRIAL, "check", "--design", rel, "--library", package, "--version", version, "--report", report],
                "seeds": [0], "description": description}
    lab.add({
        "type": "hypothesis", "question_id": question_id, "cites": [read_claim, design_claim],
        "title": f"The check designed for {aid} catches the affected public copy of {package}",
        "claim": (f"On the {total} published cases the design selects, {package} {affected} gives at least one wrong answer, {package} {fixed} "
                  f"gives none, and the accept-everything program is wrong on all {invalid} cases that must be rejected."),
        "mechanism": reading["weakness"],
        "novelty_status": "known",
        "prior_art": f"The advisory itself, and Project Wycheproof's published cases (commit {design['cases']['commit'][:12]}).",
        "arms": {"reference": arm(fixed, "reference", "The app's reference library answering the same cases (read from the run on the fixed version)."),
                 "affected": arm(affected, "subject", f"{package} {affected}, the affected public copy."),
                 "fixed": arm(fixed, "subject", f"{package} {fixed}, the publisher's fixed version."),
                 "accept-all": arm(fixed, "control", "The accept-everything control program (read from the run on the fixed version).")},
        "baseline": "reference",
        "predictions": [{"metric": "right", "arm": "affected", "relative_to": "reference", "direction": "decrease",
                         "minimum_effect_ppm": PPM // total, "kill_below_ppm": 1}],
        "controls": [{"kind": "negative", "metric": "right", "arm": "fixed", "relative_to": "reference", "max_abs_effect_ppm": 0},
                     {"kind": "positive", "metric": "right", "arm": "accept-all", "relative_to": "reference", "direction": "decrease",
                      "minimum_effect_ppm": invalid * PPM // total}],
        "confounders": ["The wrapper around the library, not the library itself, could give a wrong answer.",
                        "A case could be answered wrongly for a reason other than the weakness the advisory describes."],
        "falsification_criterion": (f"If {package} {affected} gets every selected case right, the design does not catch the weakness on a public "
                                    "copy and is not shipped."),
        "claim_ceiling": {"tier": "public-copy", "forbids": ["a statement about any system other than these pinned public copies",
                                                            "a statement about how serious the weakness is",
                                                            "a statement that a version passing this check is free of the weakness"]},
        "interpretation_limits": "The check reruns published cases only. It says nothing about inputs outside them.",
        "budget": {"wall_clock_seconds_per_run": RUN_SECONDS, "max_runs": 8},
        "code": {TRIAL: file_sha256(Path(lab.root) / TRIAL), rel: file_sha256(Path(lab.path(rel)))},
    }, AGENT)
    return f"{aid}: the trial of its design is registered ({package} {affected} against {fixed}, {total} cases)."


def propose_fix(lab, model: OttoModel, question_id: str, advisory: dict) -> str:
    """Ask for the publisher's fixed version and register the trial of the update. Returns one plain line."""
    st = lab.state()
    aid, package = advisory["id"], advisory["package"]["name"]
    read = used_step(st, lab, aid, "read_advisory")
    if read is None:
        return f"{aid}: no reading to propose a fix from."
    reading = read[1]["artifact"]["parsed"]
    if not any(c["artifact"]["step"]["step"] == "propose_fix" for _, c in step_claims(st, aid)):
        claim, fix, _ = ask(lab, model, question_id, advisory, "propose_fix", prompts.propose_fix_prompt(advisory, reading),
                            lambda step: prompts.check_fix(step.answer, advisory))
        if fix is None:
            return f"{aid}: the proposed fix was refused; no fix trial is registered."
        if fix["fix"] == "none":
            return f"{aid}: no fixed version is shown by the sources ({fix['reason']})"
        return f"{aid}: the publisher's fix was proposed (update to {fix['version']}). The record goes to the checker next."
    fix_claim, proposed = used_step(st, lab, aid, "propose_fix") or (None, None)
    if proposed is None or proposed["artifact"]["parsed"]["fix"] != "update":
        return f"{aid}: no fix to try."
    if trials_of(st, aid, "fix", lab):
        return f"{aid}: its fix trial is already registered."
    fix = proposed["artifact"]["parsed"]
    copies = public_copies(package, fix["version"])
    if copies is None:
        return f"{aid}: this app has no public copy of {package} {fix['version']} and the version before it; no fix trial is registered."
    affected, fixed = copies
    ready = ready_designs(st, lab)
    if not any(design["advisory"] == aid for _, design, _ in ready):
        return f"{aid}: its own test did not hold its trial, so there is nothing to prove a fix with."
    plan = {"schema": FIX_SCHEMA, "advisory": aid, "kind": "update", "library": package, "from": affected, "to": fixed,
            "tests": list(STANDARD_TESTS),
            "checks": [{"advisory": design["advisory"], "file": path, "design_sha256": digest} for path, design, digest in ready]}
    rel = _write_once(lab, "fixes", aid, plan)
    tests = len(plan["tests"]) + len(plan["checks"])

    def arm(version: str, description: str) -> dict:
        return {"command": ["python3", TRIAL, "fix", "--fix", rel, "--version", version], "seeds": [0], "description": description}
    pins = {TRIAL: file_sha256(Path(lab.root) / TRIAL), rel: file_sha256(Path(lab.path(rel)))}
    pins.update({path: file_sha256(Path(lab.path(path))) for path, _, _ in ready})
    lab.add({
        "type": "hypothesis", "question_id": question_id, "cites": [read[0], fix_claim],
        "title": f"Updating {package} from {affected} to {fixed} fixes {aid} and leaves every other locked test passing",
        "claim": (f"On public copies, all {tests} pass-or-fail tests (the Independent exam, Attacker tricks and the {len(plan['checks'])} advisory "
                  f"{'check' if len(plan['checks']) == 1 else 'checks'} that held their own trial) read Passed on {package} {fixed}, and at least one "
                  f"fails on {package} {affected}."),
        "mechanism": f"The publisher's fixed version holds the correction: {fix['summary']}",
        "novelty_status": "known",
        "arms": {"affected": arm(affected, f"{package} {affected}, before the update."),
                 "fixed": arm(fixed, f"{package} {fixed}, after the update."),
                 "affected-again": arm(affected, f"{package} {affected} once more: the same count is expected.")},
        "baseline": "affected",
        "predictions": [{"metric": "failing", "arm": "fixed", "relative_to": "affected", "direction": "decrease",
                         "minimum_effect_ppm": PPM, "kill_below_ppm": PPM - 1}],
        "controls": [{"kind": "negative", "metric": "failing", "arm": "affected-again", "relative_to": "affected", "max_abs_effect_ppm": 0}],
        "confounders": ["A test could fail on the fixed version for a reason that has nothing to do with this advisory; the fix is then still "
                        "not offered as proven, because every locked test must pass.",
                        "The wrapper around the library, not the library itself, could give a wrong answer."],
        "falsification_criterion": f"If any of the {tests} tests does not read Passed on {package} {fixed}, the update is not offered as a proven fix.",
        "claim_ceiling": {"tier": "public-copy", "forbids": ["a statement about any system other than these pinned public copies",
                                                            "a statement about speed: timings hold only for the computer they are measured on",
                                                            "a statement that the fixed version has no other fault"]},
        "interpretation_limits": "Pass-or-fail tests only. Speed and size is measured by Retest on the customer's own computer.",
        "budget": {"wall_clock_seconds_per_run": RUN_SECONDS, "max_runs": 6},
        "code": pins,
    }, AGENT)
    return f"{aid}: the trial of the update is registered ({package} {affected} to {fixed}, {tests} tests)."


def _run_metrics(st, hid: str) -> dict[str, dict]:
    return {r["arm"]: r["metrics"] for _, r in st.runs(hid) if r["status"] == "completed"}


def distill(lab, decision_id: str) -> str:
    """State what a settled trial showed as a fact (a dead end when it was refuted)."""
    st = lab.state()
    decision = st.get(decision_id, "decision")
    hid = decision["hypothesis_id"]
    hyp = st.get(hid, "hypothesis")
    about = trial_file(lab, hyp)
    aid, arms = about["advisory"], _run_metrics(st, hid)
    refuted = decision["outcome"] == "refuted"
    scope = "These pinned public copies and these published cases only. Nothing about any other system, and nothing about how serious the weakness is."
    if trial_kind(hyp) == "test":
        a, f, c = arms["affected"], arms["fixed"], arms["accept-all"]
        library = hyp["arms"]["affected"]["command"][hyp["arms"]["affected"]["command"].index("--library") + 1]
        v_a = hyp["arms"]["affected"]["command"][hyp["arms"]["affected"]["command"].index("--version") + 1]
        v_f = hyp["arms"]["fixed"]["command"][hyp["arms"]["fixed"]["command"].index("--version") + 1]
        if refuted:
            statement = (f"The design for {aid} does not catch the affected public copy: {library} {v_a} got all {a['total']} selected cases right. "
                         "The design is not shipped.")
            tags = [f"advisory:{aid}", "test-trial", "not-offered"]
        else:
            statement = (f"On public copies, the check designed for {aid} catches the affected version: {library} {v_a} got {a['wrong']} of "
                         f"{a['total']} selected cases wrong, {library} {v_f} got {f['wrong']} wrong, and the accept-everything control got "
                         f"{c['wrong']} wrong.")
            tags = [f"advisory:{aid}", "test-trial", "ships"]
    else:
        a, f = arms["affected"], arms["fixed"]
        if refuted:
            statement = (f"On public copies, {about['library']} {about['to']} still fails {f['failing']} of {f['tests']} pass-or-fail tests "
                         f"({a['failing']} failed on {about['from']}). The update is not offered as a proven fix for {aid}.")
            tags = [f"advisory:{aid}", "fix-trial", "not-proven"]
        else:
            statement = (f"On public copies, all {f['tests']} pass-or-fail tests read Passed on {about['library']} {about['to']}; "
                         f"{a['failing']} failed on {about['from']}. The update is offered as a proven fix for {aid}.")
            tags = [f"advisory:{aid}", "fix-trial", "proven"]
    lab.add({"type": "fact", "statement": statement, "kind": "dead_end" if refuted else "observation", "scope": scope, "tags": tags,
             "backing": [decision_id]}, AGENT)
    return statement


def formalize(lab, fact_id: str) -> str:
    lab.add({"type": "correction", "target": fact_id,
             "note": "Not formalized: this is a measurement on public copies. Nothing in it can be proven exactly."}, AGENT)
    return "recorded why no formal statement is posted"


# ---------------------------------------------------------------- the agent step, as the loop asks for it

def act(lab, model: OttoModel, snap: dict, action: str, target: str) -> str:
    """Do one step that needs judgement. Returns one plain line; leaves the ledger unchanged when there is nothing
    it can honestly add (the loop then marks the step as impeded, and nothing is retried blindly)."""
    st = lab.state()
    record = st.get(target)
    if action == "propose":
        about = question_about(record)
        if about is None:
            return "This question is not one of the research side's; nothing was added."
        advisory = snapshot.advisory_of(snap, about[0])
        try:
            lines, before = [], None
            # Read, design and register follow one another; each needs the checker's verdict on the step before it.
            while before != lab.ledger.head()["head"]:
                before = lab.ledger.head()["head"]
                lines.append(propose_test(lab, model, target, advisory) if about[1] == "test" else propose_fix(lab, model, target, advisory))
                for cid, _ in step_claims(lab.state(), about[0]):
                    if not lab.state().settled(cid):
                        lab.verify(cid)          # the harness's own verify step: it runs the pinned checker
            return " ".join(dict.fromkeys(lines))
        except ModelError as exc:
            return f"{about[0]}: {exc}"
    if action == "distill":
        return distill(lab, target)
    if action == "formalize":
        return formalize(lab, target)
    return f"No step of this kind ({action}) is taken by the research agent; nothing was added."


# The build command sets the agent command up through the environment: where the snapshot and the recorded answers
# are, whether live calls may be made, the spending limit of this run, and a small file in which the run's spending
# is added up across the agent's steps (each step is its own process). The API key is never among these.
ENV_SNAPSHOT, ENV_RECORDED, ENV_LIVE, ENV_LIMIT, ENV_SPENT = (
    "OTTOLAB_SNAPSHOT", "OTTOLAB_RECORDED", "OTTOLAB_LIVE", "OTTOLAB_LIMIT_NANO", "OTTOLAB_SPENT_FILE")


def _spent(path: str | None) -> tuple[int, int]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
        return int(data.get("spent_nano") or 0), int(data.get("calls") or 0)
    except (OSError, ValueError, TypeError):
        return 0, 0


def env_model() -> OttoModel:
    """The model as the build command set it up for this run."""
    from app.otto.model import Budget
    spent, calls = _spent(os.environ.get(ENV_SPENT))
    budget = Budget(limit_nano=int(os.environ.get(ENV_LIMIT) or 0), spent_nano=spent, calls=calls)
    return OttoModel(recorded_dirs=(Path(os.environ[ENV_RECORDED]),), live=os.environ.get(ENV_LIVE) == "1", budget=budget)


def save_spent(model: OttoModel) -> None:
    path = os.environ.get(ENV_SPENT)
    if path:
        Path(path).write_text(json.dumps({"spent_nano": model.budget.spent_nano, "calls": model.budget.calls}), encoding="utf-8")
