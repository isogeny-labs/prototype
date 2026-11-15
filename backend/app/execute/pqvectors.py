"""The two post-quantum exams (phase 4c): ML-KEM-768 and ML-DSA-65 against the official NIST and Wycheproof
cases. One harness run puts every case to the library; further runs put the cases of each part to that part's
deliberately broken control. Per case the harness reports only whether the input was refused, a yes/no, and
the SHA-256 of the answer. Raw answers only: nothing in this file says which answer is right."""
from __future__ import annotations

from .. import pq_vectors, vectors
from . import RunContext, batch_info, batch_problem, problem
from .signing import NOT_DEMO, component_key, family_of, real_problem

# Which broken copy runs which cases. "wrong_answer" and "skip_key_check" are wrappers around OpenSSL
# (demo/real-libraries/openssl/pq_controls.py); "accept_all" is the accept-everything signer of every signing test.
# The controls always run in the OpenSSL image, whatever library is being examined, so the exams work for any
# library whose wrapper offers the algorithm.
CONTROL_FAMILY = "openssl"
CONTROL_SUBJECTS = {"wrong_answer": "control-pq-wrong-answer", "skip_key_check": "control-pq-skip-key-check",
                    "accept_all": "control-accept-all"}


def control_cases(control: str, part: str, cases) -> list:
    """The cases of one part that its control is run on."""
    mine = [c for c in cases if c.part == part]
    if control == "wrong_answer":
        return [c for c in mine if c.expect == "answer"]
    if control == "accept_all":
        return [c for c in mine if c.command == "verify"]
    return mine   # skip_key_check: every case of the part; it is judged on the bad keys among them


def _answers(lines: list[dict], cases) -> tuple[dict, dict]:
    """Per case: {"refused", "valid", "sha256"} as the harness reported it, or why there was no answer."""
    answers, no_answer = {}, {}
    by_id = {str(line.get("id")): line for line in lines}
    for case in cases:
        line = by_id.get(case.id)
        if line is None or line.get("error") or not isinstance(line.get("declined"), bool):
            no_answer[case.id] = str((line or {}).get("error") or "no answer")[:120]
        else:
            answers[case.id] = {"refused": line["declined"], "valid": line.get("valid"), "sha256": line.get("answer_sha256")}
    return answers, no_answer


def run_pq_exam(spec: dict, ctx: RunContext) -> dict:
    key = component_key(spec, ctx)
    if key is None:
        return problem("not_a_demo_component", NOT_DEMO)
    if (stopped := real_problem(ctx)) is not None:
        return stopped
    family = family_of(ctx)
    if family is None:
        return problem("harness_error", "This exam runs on a real library only.")
    exam = spec["kind"]
    try:
        cases = pq_vectors.load(exam)
    except vectors.VectorFileChanged as exc:
        return problem("vector_file_changed", str(exc))
    files = {f["file"]: f["sha256"] for f in pq_vectors.file_pins(exam)}   # the hashes the loader checked just now
    if files != {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}:
        return problem("vector_file_changed", "The official test files are not the ones this test was locked with.")
    total, seen = len(cases), {"n": 0}

    def on_line(line: dict) -> None:
        seen["n"] += 1
        if seen["n"] == total or seen["n"] % 8 == 0:
            ctx.progress(f"{seen['n']} of {total} cases", int(seen["n"] * 60 / total))

    def ask(subject: str, some, progress=None, where: str = family):
        job = {"op": "kat_batch", "subject": subject, "cases": [{"id": c.id, "command": c.command, "input": c.input} for c in some]}
        return ctx.runner.run_job(job, time_limit=280.0, on_line=progress, family=where)

    ctx.progress(f"0 of {total} cases", 0)
    result = ask(key, cases, on_line)
    if not result.ok:
        ctx.log(f"harness: {result.problem}")
        return batch_problem(result)
    answers, no_answer = _answers(result.lines, cases)
    controls: dict[str, dict] = {}
    musts = spec["control"]["must"]
    for number, (part, must) in enumerate(musts.items()):
        ctx.progress(f"running the control for {part}", 60 + int(number * 35 / len(musts)))
        mine = control_cases(must["control"], part, cases)
        answer = ask(CONTROL_SUBJECTS[must["control"]], mine, where=CONTROL_FAMILY)
        if answer.ok:
            got, missing = _answers(answer.lines, mine)
            controls[part] = {"control": must["control"], "answers": got, "no_answer": missing}
        else:
            ctx.log(f"control for {part}: {answer.problem}")
            controls[part] = {"control": must["control"], "problem": answer.problem}
    ctx.progress("checking the result", 97)
    return {"subject": {"key": key, "answers": answers, "no_answer": no_answer}, "controls": controls, "files": files,
            "batch": batch_info(result)}
