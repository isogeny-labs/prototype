"""Otto's research steps for a library the app has no pinned public copy of (sandbox research, a prototype).

`ottolab/research.py`, the research steps of the shipped packs, is not changed (the shipped packs name it by
fingerprint). This module adds, for an advisory whose library has no pinned copies, the steps between "a test was
designed" and "its trial is registered":

    1. versions   which versions the trial runs on, by fixed rules from the source's own version fields and the
                  registry's own list. Claude's reading of the fixed version must agree with the source's field.
    2. asking     the code that asks the library the test's questions. Claude writes it, twice, by two authors that
                  never see each other's work. (A library of the four families the app has asking code for keeps its
                  pinned copies and the pinned path; trying their unpinned versions is a later step.) A draft is used
                  only if the fixed rules let it through (ottolab/screens.py) AND it passes the known-answer check on
                  the fixed copy; a draft that does not gets the checker's lines back, at most three drafts in all.
                  A draft never touches the affected copy before it is frozen, and never sees a trial result.
    3. copies     each author's code is built into a copy set of its own (app/sandbox/maker.py), and each set goes
                  through the known-answer check on every version. A further version on which the frozen code does not
                  work is left out, with the reason, before anything is registered.
    4. register   the trial, in Otto's harness, before its first run: the four parts of every trial (reference,
                  affected, fixed, the control that accepts everything), the same two copies asked by the second
                  author's code (which must agree on every case), and the further versions. Every file is pinned by
                  its fingerprint: the design, both copy sets (so both pieces of asking code, every file of every copy
                  and both images), both known-answer files, the versions file and the two pinned scripts.

Nothing here judges a trial or decides a result. A run is decided by the separate reviewer; the trial by Otto's harness
against the thresholds frozen in the registration. What can't go on is said in one of two ways: a DEAD END is a fact in
the ledger with the plain reason (settled: "No test yet: ..."); a LATER leaves the ledger as it is (a registry could not
be read, no answer came): a stop, never a result, and a later run can take it up.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import load_settings
from app.otto import designs
from app.otto.model import ModelError, OttoModel
from app.sandbox import copies, maker, registries, versions
from ottolab import asking, prompts, research, screens

TRIAL, QUALIFY = "trial_sandbox.py", "qualify.py"
ENV_ON, ENV_FACTS, ENV_STORE = "OTTOLAB_SANDBOX", "OTTOLAB_SANDBOX_FACTS", "OTTOLAB_SANDBOX_STORE"
ENV_STOPS = "OTTOLAB_SANDBOX_STOPS"       # a small file of this run's stops, for the build command's "Left for a later run" lines
FACTS_SCHEMA = "isogeny.sandbox-facts/1"
VERSIONS_SCHEMA = "isogeny.sandbox-versions/1"
TAG = "sandbox-no-test"
QUALIFY_SECONDS = 900
SCOPE = ("These public copies, fetched from the public registry, and these published cases only. Nothing about any other system, and "
         "nothing about how serious the weakness is.")


class DeadEnd(Exception):
    """Settled: no test can be made for this advisory here. str(exc) is the plain reason."""


class Later(Exception):
    """Nothing was learned (a registry could not be read, a check could not run). A stop, never a result."""


def on() -> bool:
    return os.environ.get(ENV_ON) == "1"


def open_lab(root: Path):
    """The research lab, with the two sandbox scripts beside the two it always has."""
    lab = research.open_lab(root)
    for name in (TRIAL, QUALIFY):
        source, target = research.PINNED / name, Path(root) / name
        if not target.exists():
            shutil.copyfile(source, target)
        elif target.read_bytes() != source.read_bytes():
            raise research.ResearchError(f"The lab's {name} is not the one in ottolab/pinned. A changed instrument needs a new lab: "
                                         "earlier trials were registered with the old one.")
    return lab


def note_stop(advisory_id: str, reason: str) -> None:
    """Keep, for the build command, why this run could not go on with this advisory. A stop, never a result: nothing
    is put into the ledger for it."""
    path = os.environ.get(ENV_STOPS)
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps({"advisory": advisory_id, "reason": " ".join(str(reason).split())[:400]}) + "\n")


def stop_of(advisory_id: str) -> str | None:
    """The newest stop this run noted for this advisory, if any."""
    path = os.environ.get(ENV_STOPS)
    found = None
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines() if path else []:
            entry = json.loads(line)
            if isinstance(entry, dict) and entry.get("advisory") == advisory_id and isinstance(entry.get("reason"), str):
                found = entry["reason"]
    except (OSError, ValueError):
        return found
    return found


def facts_for(advisory_id: str) -> dict | None:
    """What the app knows about this advisory beside its text: the library, where it is published, the version ranges
    the source gives in its own fields, and the versions the assessment names. None: not for the sandbox path."""
    path = os.environ.get(ENV_FACTS)
    if not on() or not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = (data.get("advisories") or {}).get(advisory_id) if isinstance(data, dict) and data.get("schema") == FACTS_SCHEMA else None
    if not isinstance(entry, dict) or entry.get("registry") not in registries.HOSTS:
        return None
    return entry


def store() -> Path:
    return Path(os.environ[ENV_STORE])


def source():
    return registries.source_for(load_settings().registry_source_dir)


def wanted(lab, advisory: dict) -> bool:
    """Is this advisory one for the sandbox path? Sandbox research is on, the app has no pinned copies of its library,
    and the facts name a registry a copy can be made from."""
    if facts_for(advisory["id"]) is None:
        return False
    from app import real_libraries
    return advisory["package"]["name"] not in real_libraries.LIBRARIES


def is_sandbox_trial(hyp: dict) -> bool:
    return TRIAL in (hyp.get("code") or {})


# ---------------------------------------------------------------- what the ledger and the lab folder already hold

def dead_end(st, advisory_id: str) -> str | None:
    """The reason the sandbox path settled this advisory with no test, if it did."""
    for _, fact in st.of("fact"):
        if TAG in fact.get("tags", []) and f"advisory:{advisory_id}" in fact.get("tags", []):
            return str(fact["statement"])
    return None


def _say_dead_end(lab, advisory_id: str, reason: str, backing: list[str]) -> str:
    lab.add({"type": "fact", "statement": reason, "kind": "dead_end", "scope": SCOPE, "tags": [f"advisory:{advisory_id}", TAG],
             "backing": backing}, research.AGENT)
    return f"{advisory_id}: {reason}"


def _files(lab, advisory_id: str, prefix: str) -> list[str]:
    folder = Path(lab.path(f"sandbox/{advisory_id}"))
    return sorted(f"sandbox/{advisory_id}/{p.name}" for p in folder.glob(f"{prefix}-*.json")) if folder.is_dir() else []


def _read(lab, rel: str) -> dict:
    return json.loads(Path(lab.path(rel)).read_text(encoding="utf-8"))


def drafts_of(st, lab, advisory_id: str, author: str) -> list[tuple[str, dict]]:
    """Every draft this author wrote for this advisory's library that the pinned checker has seen: (claim id, the
    claim's artifact), oldest first."""
    out = []
    for cid, claim in research.step_claims(st, advisory_id):
        art = claim["artifact"]
        if art["step"]["step"] == "write_wrapper" and (art.get("parsed") or art.get("drafted") or {}).get("author") == author:
            out.append((cid, art))
    return out


def accepted_draft(st, lab, advisory_id: str, author: str) -> tuple[str, dict] | None:
    for cid, art in reversed(drafts_of(st, lab, advisory_id, author)):
        if art.get("outcome") == "used" and (art.get("parsed") or {}).get("decision") == "code" and lab._accepted(cid, st):
            return cid, art["parsed"]
    return None


# ---------------------------------------------------------------- step 1: the versions

def plan_versions(lab, advisory: dict, facts: dict, reading: dict) -> str:
    """Write the versions file once and return its place in the lab. Raises DeadEnd or Later."""
    aid = advisory["id"]
    have = _files(lab, aid, "versions")
    if have:
        return have[0]
    registry, package = facts["registry"], facts["package"]
    try:
        listed = registries.read_versions(registry, source().project(registry, package))
    except registries.RegistryError as exc:
        if exc.later:
            raise Later(str(exc)) from None
        raise DeadEnd(f"No test yet: a public copy could not be put together ({exc})") from None
    try:
        chosen = versions.choose(list(facts.get("ranges") or []), listed, list(facts.get("yours") or []))
    except versions.NoVersions as exc:
        raise DeadEnd(f"No test yet: {exc}.") from None
    said = (reading.get("fixed") or {}).get("version")
    if not chosen["after_last_affected"] and said != chosen["fixed"]:
        raise DeadEnd(f"No test yet: the publisher's text and the source's version list disagree about the fixed version "
                      f"({said or 'none read'} and {chosen['fixed']}).")
    order = [{"version": chosen["affected"], "role": "affected"}, {"version": chosen["fixed"], "role": "fixed"}]
    order += [{"version": v, "role": "yours"} for v in chosen["yours"]]
    order += [{"version": v, "role": "more_affected"} for v in chosen["more_affected"]]
    order += [{"version": v, "role": "more_fixed"} for v in chosen["more_fixed"]]
    data = {"schema": VERSIONS_SCHEMA, "advisory": aid, "library": facts["library"], "registry": registry, "package": package,
            "ranges": list(facts.get("ranges") or []), "yours": list(facts.get("yours") or []), "chosen": chosen,
            "wanted": order[:copies.MAX_VERSIONS]}
    return research._write_once(lab, f"sandbox/{aid}", "versions", data)


# ---------------------------------------------------------------- step 2: the asking code, and its known-answer check

def qualify(lab, set_rel: str, out_rel: str, only: str | None = None) -> dict:
    """Run the pinned known-answer script on one copy set. The seed is drawn now, after the set (and so the asking
    code) is frozen. `only`: ask one copy and no other (a draft is checked on the fixed copy alone). Raises Later when
    the check itself could not run."""
    path = Path(lab.path(out_rel))
    if not path.exists():
        env = dict(os.environ)
        env["EVIDENCE_LAB_BACKEND"] = str(Path(__file__).resolve().parents[1])
        try:
            done = subprocess.run([sys.executable, str(Path(lab.root) / QUALIFY), "--set", set_rel, "--seed", secrets.token_hex(32),
                                   "--out", out_rel, *(["--only", only] if only else [])], cwd=str(lab.root), env=env,
                                  capture_output=True, text=True, errors="replace", timeout=QUALIFY_SECONDS, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            raise Later("the known-answer check could not be run") from None
        if done.returncode != 0 or not path.exists():
            said = (done.stderr or "").strip().splitlines()[-1:] or ["it stopped"]
            raise Later(f"the known-answer check could not be run ({said[0][:200]})")
    return json.loads(path.read_text(encoding="utf-8"))


def full_marks(known: dict, version: str, which: str | None = None) -> bool:
    """The fixed rule of the known-answer check: every fresh signature our reference library made was accepted, and
    every spoiled one was refused. (`which`: one of the two dummy controls, which must NOT get full marks.)"""
    counts = (known.get("dummies") or {}).get(version, {}).get(which) if which else (known.get("versions") or {}).get(version)
    return bool(counts) and counts["accepted_valid"] == known["valid"] and counts["rejected_spoiled"] == known["spoiled"] and counts["no_answer"] == 0


def known_line(known: dict, version: str) -> str:
    counts = known["versions"].get(version) or {"accepted_valid": 0, "rejected_spoiled": 0, "notes": {}}
    notes = "; ".join(f"{note} ({n} times)" for note, n in counts.get("notes", {}).items())
    return (f"On the fixed copy it accepted {counts['accepted_valid']} of {known['valid']} fresh signatures that a reference library made, "
            f"and refused {counts['rejected_spoiled']} of {known['spoiled']} spoiled ones." + (f" Seen: {notes}." if notes else ""))


def _record_draft(lab, question_id: str, advisory_id: str, step, outcome: str, parsed: dict | None, refusal: str | None, drafted: dict) -> str:
    """One draft as an objective and a claim under the research side's pinned checker, like every Claude step."""
    # (the author and the number of the draft are part of the objective: two drafts recorded in the same second are
    #  then still two different records, which the ledger asks of every entry)
    objective = lab.add({"type": "objective", "question_id": question_id,
                         "statement": (f"The record of draft {drafted['attempt']} of the asking code by author {drafted['author']} for the library "
                                       f"of {advisory_id} is whole: the prompt and the answer are there with their SHA-256, and the source of "
                                       "the answer is named."),
                         "verifier": {"kind": "certificate", "checker": research.CHECKER,
                                      "checker_sha256": research.file_sha256(Path(lab.root) / research.CHECKER),
                                      "params": {"step": "write_wrapper", "advisory": advisory_id, "author": drafted["author"],
                                                 "attempt": drafted["attempt"]}, "timeout_seconds": 60}}, research.AGENT)
    artifact: dict = {"advisory": advisory_id, "step": step.record(), "outcome": outcome, "drafted": drafted}
    if parsed is not None:
        artifact["parsed"] = parsed
    if refusal is not None:
        artifact["refusal"] = refusal[:280]
    return lab.add({"type": "claim", "objective_id": objective, "artifact": artifact, "cites": []}, research.AGENT)


def write_asking(lab, model: OttoModel, question_id: str, advisory: dict, plan_rel: str, author: str) -> str:
    """One draft by one author: ask, screen, build its copy set, check it on the fixed copy, and record it either way.
    Returns one plain line. Raises DeadEnd or Later."""
    aid = advisory["id"]
    st = lab.state()
    plan = _read(lab, plan_rel)
    library, registry, package = plan["library"], plan["registry"], plan["package"]
    language = registries.LANGUAGES[registry]
    earlier = drafts_of(st, lab, aid, author)
    cannot = next((art for _, art in earlier if art.get("outcome") == "used" and (art.get("parsed") or {}).get("decision") == "cannot"), None)
    if cannot is not None:
        raise DeadEnd(f"No test yet: the library can't be asked this question. Claude noted: {cannot['parsed']['notes']}")
    if len(earlier) >= asking.MAX_ATTEMPTS:
        raise DeadEnd(f"No test yet: the code that asks the library could not be made to work on {library} "
                      f"(after {asking.MAX_ATTEMPTS} drafts by one author).")
    fixed = plan["chosen"]["fixed"]
    try:
        tree, readme, _ = maker.library_files(store(), source(), registry, package, fixed)
    except registries.RegistryError as exc:
        if exc.later:
            raise Later(str(exc)) from None
        raise DeadEnd(f"No test yet: a public copy could not be put together ({exc})") from None
    except copies.CopyError as exc:
        raise DeadEnd(f"No test yet: a public copy could not be put together ({exc})") from None
    names = asking.modules_of(tree) if language == "python" else {package}
    template = (maker.TEMPLATES / language / maker.LANGUAGE_FILES[language][0]).read_text(encoding="utf-8")
    feedback = [str(art.get("refusal") or "it was not used") for _, art in earlier]
    text = asking.prompt(library=library, package=package, registry_words=registries.WORDS[registry], language=language, template=template,
                         library_material=asking.material(tree, readme, language), author=author, feedback=feedback or None)
    step = model.ask("write_wrapper", text)          # raises ModelError when no answer comes: nothing is recorded, nothing is settled
    drafted = {"author": author, "attempt": len(earlier) + 1, "screen_sha256": screens.fingerprint()}
    try:
        answer = asking.check_answer(step.answer, language, names)
    except prompts.Refused as refused:
        _record_draft(lab, question_id, aid, step, "refused", None, str(refused), drafted)
        return f"{aid}: a draft of the asking code (author {author}) was not let through: {refused}"
    if answer["decision"] == "cannot":
        _record_draft(lab, question_id, aid, step, "used", {**answer, **drafted}, None, drafted)
        return f"{aid}: the author says the library can't be asked this question."
    try:
        record, left_out = maker.make_set(root=store(), source=source(), library=library, registry=registry, package=package,
                                          wanted=plan["wanted"], asking={"kind": "written", "author": f"Claude (author {author})",
                                                                         "source": answer["asking_code"]}, say=lambda line: None)
    except registries.RegistryError as exc:
        if exc.later:
            raise Later(str(exc)) from None
        raise DeadEnd(f"No test yet: a public copy could not be put together ({exc})") from None
    except copies.CopyError as exc:
        raise DeadEnd(f"No test yet: a public copy could not be put together ({exc}).") from None
    set_rel = research._write_once(lab, f"sandbox/{aid}", f"set-{author}", record)
    # A draft is checked on the fixed copy and on no other: it never runs on the affected copy, and what its author is
    # told back (the line below) is about the fixed copy alone.
    draft = qualify(lab, set_rel, f"sandbox/{aid}/draft-{author}-{record['id']}.json", only=fixed)
    if full_marks(draft, fixed, "yes") or full_marks(draft, fixed, "no"):
        raise Later("the known-answer check did not refuse its own two controls, so it can't be relied on")
    if not full_marks(draft, fixed):
        _record_draft(lab, question_id, aid, step, "refused", None, "It did not work on the fixed copy. " + known_line(draft, fixed), drafted)
        return f"{aid}: a draft of the asking code (author {author}) did not pass the known-answer check on the fixed copy."
    # From here on the code is frozen (the copy set's record holds its fingerprint). It is now checked on every copy of
    # its set, with fresh questions from a new seed. What that shows decides only which versions the trial runs on.
    known_rel = f"sandbox/{aid}/known-{author}-{record['id']}.json"
    qualify(lab, set_rel, known_rel)
    parsed = {**answer, **drafted, "asking_sha256": record["asking"]["sha256"], "set": record["id"], "set_file": set_rel,
              "known_file": known_rel, "left_out": left_out}
    _record_draft(lab, question_id, aid, step, "used", parsed, None, drafted)
    return f"{aid}: the asking code by author {author} passed the fixed rules and the known-answer check on the fixed copy."


# ---------------------------------------------------------------- step 4: the registration

def _pins(lab, *rels: str) -> dict:
    pins = {TRIAL: research.file_sha256(Path(lab.root) / TRIAL), QUALIFY: research.file_sha256(Path(lab.root) / QUALIFY)}
    pins.update({rel: research.file_sha256(Path(lab.path(rel))) for rel in rels})
    return pins


def register(lab, question_id: str, advisory: dict, reading: dict, design: dict, cites: list[str], plan_rel: str, set_a: str, known_a: str,
             set_b: str | None, known_b: str | None) -> str:
    aid = advisory["id"]
    plan = _read(lab, plan_rel)
    library = plan["library"]
    record_a = copies.check_set(_read(lab, set_a))
    known = [_read(lab, known_a)] + ([_read(lab, known_b)] if known_b else [])
    if set_b is not None and copies.check_set(_read(lab, set_b))["asking"]["sha256"] == record_a["asking"]["sha256"]:
        raise DeadEnd("No test yet: the two authors wrote the same asking code word for word, so the second is no second look.")
    in_set = {v["version"]: v["role"] for v in record_a["versions"]}
    works = {v: all(full_marks(k, v) for k in known) for v in in_set}
    affected, fixed = plan["chosen"]["affected"], plan["chosen"]["fixed"]
    if not works.get(fixed):
        raise DeadEnd(f"No test yet: the code that asks the library could not be shown to work on {library} {fixed}, the fixed version.")
    if not works.get(affected):
        raise DeadEnd(f"No test yet: the code that asks the library does not work on {library} {affected}, the affected version "
                      "(it did not take fresh signatures a reference library made), so nothing can be shown on it.")
    more_affected = [v for v, role in in_set.items() if role in ("yours", "more_affected") and works[v]]
    more_fixed = [v for v, role in in_set.items() if role == "more_fixed" and works[v]]
    left_out = [{"version": v, "reason": "the asking code does not work on it (it did not accept fresh signatures that a reference library made)"}
                for v, role in in_set.items() if not works[v]]
    left_out += [{"version": w["version"], "reason": "it could not be put together with the fixed version's helper libraries"}
                 for w in plan["wanted"] if w["version"] not in in_set]
    rel = research._write_once(lab, "designs", aid, design)
    total, invalid = len(design["cases"]["ids"]), design["cases"]["must_reject"]
    arms_file = research._write_once(lab, f"sandbox/{aid}", "arms", {
        "schema": "isogeny.sandbox-arms/1", "advisory": aid, "library": library, "affected": affected, "fixed": fixed,
        "more_affected": more_affected, "more_fixed": more_fixed, "left_out": left_out, "set_a": record_a["id"],
        "set_b": copies.check_set(_read(lab, set_b))["id"] if set_b else None})

    def arm(version: str, report: str, description: str, second: bool = False) -> dict:
        command = ["python3", TRIAL, "check", "--design", rel, "--set", set_b if second and set_b else set_a, "--library", library,
                   "--version", version, "--report", report]
        if second and set_b:
            command += ["--agree-with", set_a]
        return {"command": command, "seeds": [0], "description": description}

    arms = {"reference": arm(fixed, "reference", "The app's reference library answering the same cases (read from the run on the fixed version)."),
            "affected": arm(affected, "subject", f"{library} {affected}, the affected public copy."),
            "fixed": arm(fixed, "subject", f"{library} {fixed}, the publisher's fixed version."),
            "accept-all": arm(fixed, "control", "The accept-everything control program (read from the run on the fixed version).")}
    predictions = [{"metric": "right", "arm": "affected", "relative_to": "reference", "direction": "decrease",
                    "minimum_effect_ppm": research.PPM // total, "kill_below_ppm": 1}]
    controls = [{"kind": "negative", "metric": "right", "arm": "fixed", "relative_to": "reference", "max_abs_effect_ppm": 0},
                {"kind": "positive", "metric": "right", "arm": "accept-all", "relative_to": "reference", "direction": "decrease",
                 "minimum_effect_ppm": invalid * research.PPM // total}]
    if set_b is not None:
        arms["affected-b"] = arm(affected, "subject", f"{library} {affected} again, asked by the second author's code.", second=True)
        arms["fixed-b"] = arm(fixed, "subject", f"{library} {fixed} again, asked by the second author's code.", second=True)
        for name in ("affected-b", "fixed-b"):       # the two pieces of asking code must hand back the same answer on every case
            controls.append({"kind": "negative", "metric": "agree", "arm": name, "relative_to": "reference", "max_abs_effect_ppm": 0})
    for n, version in enumerate(more_affected, start=1):
        arms[f"more-affected-{n}"] = arm(version, "subject", f"{library} {version}, a further version the advisory names as affected.")
        predictions.append({"metric": "right", "arm": f"more-affected-{n}", "relative_to": "reference", "direction": "decrease",
                            "minimum_effect_ppm": research.PPM // total, "kill_below_ppm": 1})
    for n, version in enumerate(more_fixed, start=1):
        arms[f"more-fixed-{n}"] = arm(version, "subject", f"{library} {version}, a further version after the fix.")
        controls.append({"kind": "negative", "metric": "right", "arm": f"more-fixed-{n}", "relative_to": "reference", "max_abs_effect_ppm": 0})
    written = record_a["asking"]["kind"] == "written"
    further = (f" Every further affected version ({', '.join(more_affected)}) gives at least one wrong answer too." if more_affected else "") + \
              (f" Every further fixed version ({', '.join(more_fixed)}) gives none." if more_fixed else "")
    lab.add({
        "type": "hypothesis", "question_id": question_id, "cites": cites,
        "title": f"The check designed for {aid} catches the affected public copy of {library}",
        "claim": (f"On the {total} published cases the design selects, {library} {affected} gives at least one wrong answer, {library} {fixed} "
                  f"gives none, and the accept-everything program is wrong on all {invalid} cases that must be rejected." + further
                  + (" The second author's asking code hands back the same answer as the first on every case." if set_b else "")),
        "mechanism": reading["weakness"],
        "novelty_status": "known",
        "prior_art": f"The advisory itself, and Project Wycheproof's published cases (commit {design['cases']['commit'][:12]}).",
        "arms": arms, "baseline": "reference", "predictions": predictions, "controls": controls,
        "confounders": [("The asking code, written for this library by Claude, could give a wrong answer where the library gave a right one. "
                         "It was screened by fixed rules and checked against known answers before this registration, and a second "
                         "author's code must agree with it on every case." if written else
                         "The wrapper around the library, not the library itself, could give a wrong answer."),
                        "A case could be answered wrongly for a reason other than the weakness the advisory describes.",
                        "Something else that changed between the two versions, not the fix, could make the difference. The further "
                        "versions narrow this; they do not rule it out.",
                        "The copies come from the public registry, checked against the registry's own fingerprint; the first fetch "
                        "trusts the registry."],
        "falsification_criterion": (f"If {library} {affected} gets every selected case right, the design does not catch the weakness on a public "
                                    "copy and is not shipped. The same holds for each further version the advisory names as affected."),
        "claim_ceiling": {"tier": "public-copy", "forbids": ["a statement about any system other than these public copies",
                                                            "a statement about how serious the weakness is",
                                                            "a statement that a version passing this check is free of the weakness"]},
        "interpretation_limits": "The check reruns published cases only. It says nothing about inputs outside them.",
        "budget": {"wall_clock_seconds_per_run": research.RUN_SECONDS, "max_runs": 2 * len(arms) + 2},
        "code": _pins(lab, rel, plan_rel, arms_file, set_a, known_a, *([set_b, known_b] if set_b and known_b else [])),
    }, research.AGENT)
    return (f"{aid}: the trial of its design is registered ({library} {affected} against {fixed}, {total} cases, "
            f"{len(arms)} parts" + (", two authors' asking code" if set_b else ", the app's own asking code") + ").")


# ---------------------------------------------------------------- the two steps the agent takes

def propose_test(lab, model: OttoModel, question_id: str, advisory: dict, snap: dict) -> str:
    """Take the next step towards a registered trial on sandbox copies. Returns one plain line; leaves the ledger as it
    is when there is nothing it can honestly add."""
    st = lab.state()
    aid = advisory["id"]
    steps = [c["artifact"]["step"]["step"] for _, c in research.step_claims(st, aid)]
    read, designed = research.used_step(st, lab, aid, "read_advisory"), research.used_step(st, lab, aid, "design_test")
    if "read_advisory" not in steps or "design_test" not in steps or read is None or designed is None \
            or designed[1]["artifact"]["parsed"]["decision"] != "test":
        return research.propose_test(lab, model, question_id, advisory, snap)      # the reading and the design are the steps they always were
    if research.trials_of(st, aid, "test", lab):
        return f"{aid}: its trial is already registered."
    settled = dead_end(st, aid)
    if settled is not None:
        return f"{aid}: {settled}"
    facts = facts_for(aid)
    if facts is None:
        return research.propose_test(lab, model, question_id, advisory, snap)
    reading = read[1]["artifact"]["parsed"]
    design = designs.check_design(designed[1]["artifact"]["parsed"]["design"])
    try:
        plan_rel = plan_versions(lab, advisory, facts, reading)
        for author in asking.AUTHORS:
            if accepted_draft(st, lab, aid, author) is None:
                return write_asking(lab, model, question_id, advisory, plan_rel, author)
        (claim_a, a), (claim_b, b) = accepted_draft(st, lab, aid, "a"), accepted_draft(st, lab, aid, "b")     # type: ignore[misc]
        return register(lab, question_id, advisory, reading, design, [read[0], designed[0], claim_a, claim_b], plan_rel,
                        a["set_file"], a["known_file"], b["set_file"], b["known_file"])
    except DeadEnd as settled_now:
        return _say_dead_end(lab, aid, str(settled_now), [designed[0]])
    except Later as stop:
        reason = str(stop)
        note_stop(aid, reason[0].upper() + reason[1:] + ("" if reason.endswith(".") else "."))
        return f"{aid}: left for a later run ({stop})"
    except ModelError as no_answer:          # no answer came for the asking code: nothing is recorded, nothing is settled
        note_stop(aid, str(no_answer))
        return f"{aid}: {no_answer}"


def propose_fix(lab, model: OttoModel, question_id: str, advisory: dict) -> str:
    """The publisher's fixed version as the fix, tried on the sandbox copies: the same steps as for a pinned library,
    with the sandbox trial script."""
    st = lab.state()
    aid = advisory["id"]
    read = research.used_step(st, lab, aid, "read_advisory")
    proposed = research.used_step(st, lab, aid, "propose_fix")
    if read is None or proposed is None or proposed[1]["artifact"]["parsed"]["fix"] != "update":
        return research.propose_fix(lab, model, question_id, advisory)      # the question to Claude is the one it always was
    if research.trials_of(st, aid, "fix", lab):
        return f"{aid}: its fix trial is already registered."
    test = next(((hid, hyp) for hid, hyp in research.trials_of(st, aid, "test", lab) if is_sandbox_trial(hyp) and research.held(st, lab, hid)), None)
    if test is None:
        return research.propose_fix(lab, model, question_id, advisory)
    fix = proposed[1]["artifact"]["parsed"]
    arms = _read(lab, next(p for p in test[1]["code"] if p.startswith(f"sandbox/{aid}/arms-")))
    set_a = next(p for p in sorted(test[1]["code"]) if p.startswith(f"sandbox/{aid}/set-a-"))
    library, affected, fixed = arms["library"], arms["affected"], arms["fixed"]
    if fix["version"] != fixed:
        return f"{aid}: the fix names version {fix['version']}, and the test was tried on {fixed}; no fix trial is registered."
    ready = research.ready_designs(st, lab)
    plan = {"schema": research.FIX_SCHEMA, "advisory": aid, "kind": "update", "library": library, "from": affected, "to": fixed,
            "tests": list(research.STANDARD_TESTS),
            "checks": [{"advisory": design["advisory"], "file": path, "design_sha256": digest} for path, design, digest in ready]}
    rel = research._write_once(lab, "fixes", aid, plan)
    tests = len(plan["tests"]) + len(plan["checks"])

    def arm(version: str, description: str) -> dict:
        return {"command": ["python3", TRIAL, "fix", "--fix", rel, "--set", set_a, "--version", version], "seeds": [0], "description": description}
    pins = _pins(lab, rel, set_a, *[path for path, _, _ in ready])
    lab.add({
        "type": "hypothesis", "question_id": question_id, "cites": [read[0], proposed[0]],
        "title": f"Updating {library} from {affected} to {fixed} fixes {aid} and leaves every other locked test passing",
        "claim": (f"On public copies, all {tests} pass-or-fail tests (the Independent exam, Attacker tricks and the {len(plan['checks'])} advisory "
                  f"{'check' if len(plan['checks']) == 1 else 'checks'} that held their own trial) read Passed on {library} {fixed}, and at least one "
                  f"fails on {library} {affected}."),
        "mechanism": f"The publisher's fixed version holds the correction: {fix['summary']}",
        "novelty_status": "known",
        "arms": {"affected": arm(affected, f"{library} {affected}, before the update."),
                 "fixed": arm(fixed, f"{library} {fixed}, after the update."),
                 "affected-again": arm(affected, f"{library} {affected} once more: the same count is expected.")},
        "baseline": "affected",
        "predictions": [{"metric": "failing", "arm": "fixed", "relative_to": "affected", "direction": "decrease",
                         "minimum_effect_ppm": research.PPM, "kill_below_ppm": research.PPM - 1}],
        "controls": [{"kind": "negative", "metric": "failing", "arm": "affected-again", "relative_to": "affected", "max_abs_effect_ppm": 0}],
        "confounders": ["A test could fail on the fixed version for a reason that has nothing to do with this advisory; the fix is then still "
                        "not offered as proven, because every locked test must pass.",
                        "The asking code, not the library itself, could give a wrong answer."],
        "falsification_criterion": f"If any of the {tests} tests does not read Passed on {library} {fixed}, the update is not offered as a proven fix.",
        "claim_ceiling": {"tier": "public-copy", "forbids": ["a statement about any system other than these public copies",
                                                            "a statement about speed: timings hold only for the computer they are measured on",
                                                            "a statement that the fixed version has no other fault"]},
        "interpretation_limits": "Pass-or-fail tests only.",
        "budget": {"wall_clock_seconds_per_run": research.RUN_SECONDS, "max_runs": 6},
        "code": pins,
    }, research.AGENT)
    return f"{aid}: the trial of the update is registered ({library} {affected} to {fixed}, {tests} tests)."


def failed_control(st, hid: str) -> dict | None:
    """The first control of a judged trial that did not hold, as the harness recorded it."""
    decision = st.decision(hid)
    for row in ((decision or (None, {}))[1].get("controls") or []):
        if row.get("passed") is False or row.get("degenerate"):
            return row
    return None


def killed_prediction(st, hid: str) -> dict | None:
    decision = st.decision(hid)
    for row in ((decision or (None, {}))[1].get("effects") or []):
        if row.get("result") != "met":
            return row
    return None


def distill(lab, decision_id: str) -> str:
    """State what a settled sandbox trial showed, as a fact (a dead end when it did not hold)."""
    st = lab.state()
    decision = st.get(decision_id, "decision")
    hid = decision["hypothesis_id"]
    hyp = st.get(hid, "hypothesis")
    if research.trial_kind(hyp) != "test":
        return research.distill(lab, decision_id)          # (a fix trial has the same parts as ever)
    aid = research.trial_file(lab, hyp)["advisory"]
    metrics = research._run_metrics(st, hid)

    def of(arm: str) -> tuple[str, str]:
        command = hyp["arms"][arm]["command"]
        return command[command.index("--library") + 1], command[command.index("--version") + 1]
    library, v_a = of("affected")
    _, v_f = of("fixed")
    a, f, c = metrics["affected"], metrics["fixed"], metrics["accept-all"]
    outcome = decision["outcome"]
    if outcome == "supported":
        statement = (f"On public copies, the check designed for {aid} catches the affected version: {library} {v_a} got {a['wrong']} of "
                     f"{a['total']} selected cases wrong, {library} {v_f} got {f['wrong']} wrong, and the accept-everything control got "
                     f"{c['wrong']} wrong.")
        tags, kind = [f"advisory:{aid}", "test-trial", "ships", "sandbox"], "observation"
    else:
        statement = f"The trial of the check designed for {aid} on public copies of {library} did not hold ({outcome.replace('_', ' ')}). It is not shipped."
        tags, kind = [f"advisory:{aid}", "test-trial", "not-offered", "sandbox"], "dead_end"
    lab.add({"type": "fact", "statement": statement, "kind": kind, "scope": SCOPE, "tags": tags, "backing": [decision_id]}, research.AGENT)
    return statement


def fingerprints() -> dict[str, str]:
    """The fingerprints of the sandbox research scripts, as a pack made by a sandbox run names them."""
    here = Path(__file__).resolve().parent
    return {TRIAL: research.file_sha256(research.PINNED / TRIAL), QUALIFY: research.file_sha256(research.PINNED / QUALIFY),
            "ottolab/sandbox.py": research.file_sha256(here / "sandbox.py"), "ottolab/asking.py": research.file_sha256(here / "asking.py"),
            "ottolab/screens.py": research.file_sha256(here / "screens.py")}
