"""The two tests that ask a signing component "is this signature genuine?" once per case: the official
Wycheproof cases, and our fixed list of bad signatures. One harness run covers the component and the
accept-everything control. The reference library answers the same cases here in the backend.
Raw answers only: nothing in this file says which answer is right."""
from __future__ import annotations

from app.run import components
from app import real_libraries
from app.run import reference
from app.engine import vectors
from app.run.execute import RunContext, batch_info, batch_problem, problem

CONTROL = "control-accept-all"
NOT_DEMO = "Only our own demo components can be run in this version."
GENERAL_ERROR = "general error: "   # how a wrapper marks a crash that was not the library's own "bad signature" answer


def component_key(spec: dict, ctx: RunContext) -> str | None:
    """The harness name of the component to run, or None if it is not a registered component (one of our demo
    components, or since phase 4c a real library)."""
    if ctx.component is None or spec["target"].get("component") != ctx.component[0]:
        return None
    try:
        return components.component_key(*ctx.component)
    except ValueError:
        return None


def family_of(ctx: RunContext, version: str | None = None) -> str | None:
    """The real-library image a run needs (phase 4c), or None for one of our own demo components."""
    if ctx.component is None:
        return None
    return real_libraries.family_of(ctx.component[0], version or ctx.component[1])


def family_args(ctx: RunContext) -> dict:
    """The extra argument a harness run needs for a real library: {"family": ...}. Empty for our own demo components,
    so their runs are started exactly as they always were."""
    family = family_of(ctx)
    return {"family": family} if family is not None else {}


def real_problem(ctx: RunContext) -> dict | None:
    """Why a real library can't run here, said before anything is started: it never runs as a local program."""
    family = family_of(ctx)
    if family is None:
        return None
    if ctx.mode.name != "isolated":
        return problem("needs_isolated_mode", real_libraries.NEEDS_ISOLATED + ", and this run is in demo mode.")
    if not ctx.mode.real_images.get(family):
        return problem("real_image_missing", f"The container image for {real_libraries.family_label(family)} is not prepared on this computer.")
    return None


def _run(spec: dict, ctx: RunContext, subject_set: vectors.VectorSet, files: dict, progress_text, reference_sets: dict) -> dict:
    key = component_key(spec, ctx)
    if key is None:
        return problem("not_a_demo_component", NOT_DEMO)
    if (stopped := real_problem(ctx)) is not None:
        return stopped
    cases = subject_set.cases
    total = len(cases)
    seen = {"n": 0}

    def on_line(line: dict) -> None:
        seen["n"] += 1
        n = seen["n"]
        if n <= total:
            if n == total or n % 4 == 0:
                ctx.progress(progress_text(n, total), int(n * 50 / total))
        elif n == total + 1 or n % 16 == 0:
            ctx.progress("running the control", 50 + int((n - total) * 45 / total))

    ctx.progress(progress_text(0, total), 0)
    job = {"op": "verify_batch", "subjects": [key, CONTROL],
           "cases": [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in cases]}
    result = ctx.runner.run_job(job, time_limit=240.0, on_line=on_line, **family_args(ctx))
    if not result.ok:
        ctx.log(f"harness: {result.problem}")
        return batch_problem(result)
    answers: dict[str, dict] = {key: {}, CONTROL: {}}
    no_answer: dict[str, dict] = {key: {}, CONTROL: {}}
    crashes: dict[str, str] = {}   # phase 4c: cases the library did not accept by crashing, not by its own "no"
    position = 0
    for line in result.lines:
        # Lines come per subject in the order asked, each subject's cases in order (also when both subjects are the same).
        subject = key if position < total else CONTROL
        position += 1
        if line.get("subject") != subject:
            return problem("harness_error", "The test harness answered out of order.")
        case_id = str(line.get("id"))
        if line.get("valid") is True:
            answers[subject][case_id] = "accept"
        elif line.get("valid") is False:
            answers[subject][case_id] = "reject"
        else:
            no_answer[subject][case_id] = str(line.get("error") or "no answer")[:120]
        note = line.get("note")
        if subject == key and line.get("valid") is False and isinstance(note, str) and note.startswith(GENERAL_ERROR):
            crashes[case_id] = note[len(GENERAL_ERROR):][:60]
    ctx.progress("checking the result", 97)
    raw = {"subject": {"key": key, "answers": answers[key], "no_answer": no_answer[key]},
           "control": {"key": CONTROL, "answers": answers[CONTROL], "no_answer": no_answer[CONTROL]},
           "reference": {"library": reference.LIBRARY}, "files": files, "batch": batch_info(result)}
    for name, (algorithm, case_list) in reference_sets.items():
        raw["reference"][name] = {"answers": reference.answers(algorithm, case_list)}
    if crashes:   # only when there are any, so a run of our own demo components is recorded exactly as before
        raw["subject"]["general_errors"] = crashes
    return raw


def run_official_vectors(spec: dict, ctx: RunContext) -> dict:
    if component_key(spec, ctx) is None:
        return problem("not_a_demo_component", NOT_DEMO)
    try:
        ecdsa, ed = vectors.load_wycheproof("ecdsa_p256"), vectors.load_wycheproof("ed25519")
    except vectors.VectorFileChanged as exc:
        return problem("vector_file_changed", str(exc))
    pins = {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}
    files = {ecdsa.path.name: ecdsa.sha256, ed.path.name: ed.sha256}  # the hashes the loader checked just now
    if files != pins:
        return problem("vector_file_changed", "The official test files are not the ones this test was locked with.")
    return _run(spec, ctx, ecdsa, files, lambda n, total: f"{n} of {total} cases",
                {"ecdsa_p256": ("ecdsa_p256", ecdsa.cases), "ed25519": ("ed25519", ed.cases)})


def run_bad_signatures(spec: dict, ctx: RunContext) -> dict:
    if component_key(spec, ctx) is None:
        return problem("not_a_demo_component", NOT_DEMO)
    try:
        cases = vectors.load_bad_signatures()
    except vectors.VectorFileChanged as exc:
        return problem("vector_file_changed", str(exc))
    files = {spec["inputs"]["file"]: cases.sha256}
    if cases.sha256 != spec["inputs"]["sha256"]:
        return problem("vector_file_changed", "The bad-signature list is not the one this test was locked with.")
    return _run(spec, ctx, cases, files, lambda n, total: f"checking {n} of {total} signatures",
                {"bad_signatures": ("bad_signatures", cases.cases)})


def run_advisory_cases(spec: dict, ctx: RunContext) -> dict:
    """Phase 5c: an advisory check. The cases its locked test names, taken from the pinned official file, run on the
    program and on the accept-everything control; the reference library answers the same cases."""
    if component_key(spec, ctx) is None:
        return problem("not_a_demo_component", NOT_DEMO)
    try:
        ecdsa = vectors.load_wycheproof("ecdsa_p256")
    except vectors.VectorFileChanged as exc:
        return problem("vector_file_changed", str(exc))
    pins = {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}
    files = {ecdsa.path.name: ecdsa.sha256}  # the hash the loader checked just now
    if files != pins:
        return problem("vector_file_changed", "The official test file is not the one this test was locked with.")
    wanted = spec["inputs"]["cases"]
    by_id = {c.id: c for c in ecdsa.cases}
    if not isinstance(wanted, list) or not wanted or len(set(wanted)) != len(wanted) or any(i not in by_id for i in wanted):
        return problem("vector_file_changed", "The locked test names cases that are not in the pinned official file.")
    chosen = vectors.VectorSet(ecdsa.name, ecdsa.path, ecdsa.sha256, ecdsa.source, tuple(c for c in ecdsa.cases if c.id in set(wanted)))
    return _run(spec, ctx, chosen, files, lambda n, total: f"{n} of {total} cases", {"ecdsa_p256": ("ecdsa_p256", chosen.cases)})
