"""The two measuring tests: speed and size of the signing component, and the ML-DSA-65 comparison.
Both take the gate exclusively while they measure, so no other test job is running component work at the
same moment. Raw timings only; the slowdown rule is applied by the reviewer."""
from __future__ import annotations

import time

from .. import components, reference
from . import RunContext, batch_info, batch_problem, problem
from .signing import NOT_DEMO, component_key

WAITING = "waiting for the other tests to finish, so the timing is clean"


def _benches(lines: list[dict], roles: list[str]) -> tuple[dict | None, list[dict]]:
    """Turn the harness lines into bench records with a role. Within a round the harness goes through the
    subjects in the order given on even rounds and in reverse on odd rounds."""
    keygen, benches, seen = None, [], {}
    for line in lines:
        if "keygen" in line:
            keygen = line
            continue
        number = line.get("round")
        index = seen.get(number, 0)
        seen[number] = index + 1
        if not isinstance(number, int) or index >= len(roles):
            continue
        role = roles[index] if number % 2 == 0 else roles[len(roles) - 1 - index]
        out = line.get("out") if isinstance(line.get("out"), dict) else {}
        bench = {"round": number, "subject": line.get("subject"), "role": role, "rc": line.get("rc"),
                 "sign_ms": out.get("sign_ms"), "verify_ms": out.get("verify_ms"),
                 "signature_bytes": out.get("signature_bytes"), "public_key_bytes": out.get("public_key_bytes"),
                 "all_verified": out.get("all_verified")}
        if line.get("error"):
            bench["error"] = str(line["error"])[:120]
        benches.append(bench)
    return keygen, benches


def run_speed_size(spec: dict, ctx: RunContext) -> dict:
    new_key = component_key(spec, ctx)
    if new_key is None:
        return problem("not_a_demo_component", NOT_DEMO)
    inputs = spec["inputs"]
    rounds, repeats = inputs["rounds"], inputs["repeats"]
    if ctx.baseline_version is not None:
        try:
            old_key = components.component_key(ctx.component[0], ctx.baseline_version)
        except ValueError:
            return problem("not_a_demo_component", NOT_DEMO)
        subjects, roles, keygen_with = [old_key, new_key, f"control-slow:{new_key}"], ["old", "new", "control"], old_key
    else:
        subjects, roles, keygen_with = [new_key, f"control-slow:{new_key}"], ["subject", "control"], new_key
    done = {"lines": 0}

    def on_line(line: dict) -> None:
        if "round" in line:
            done["lines"] += 1
            number = int(line["round"]) + 1
            ctx.progress(f"measuring, round {number} of {rounds}", int(done["lines"] * 95 / (rounds * len(subjects))))

    ctx.progress(WAITING, None)
    with ctx.gate.exclusive():
        ctx.begin()
        ctx.progress(f"measuring, round 1 of {rounds}", 0)
        job = {"op": "bench_rounds", "keygen_with": keygen_with, "subjects": subjects, "rounds": rounds,
               "repeats": repeats, "message": inputs["message"]}
        result = ctx.runner.run_job(job, time_limit=300.0, on_line=on_line)
        if not result.ok:
            ctx.log(f"harness: {result.problem}")
            return batch_problem(result)
        keygen, benches = _benches(result.lines, roles)
        if keygen is None or keygen.get("rc") != 0 or not keygen.get("public_key_bytes"):
            out = problem("component_no_answer", "The component did not make a test key.")
            out["batch"] = batch_info(result)
            return out
        measured = reference.bench_ecdsa_p256(rounds * repeats, inputs["message"])
    ctx.progress("checking the result", 97)
    return {"benches": benches, "subjects": dict(zip(roles, subjects)),
            "reference": {k: measured[k] for k in ("library", "sign_ms", "verify_ms", "signature_bytes", "public_key_bytes")},
            "exclusive": True, "batch": batch_info(result)}


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 4)


def measure_mldsa65(repeats: int, message: bytes) -> tuple[dict, dict]:
    """(timings and sizes, control outcome) for ML-DSA-65 from the cryptography library: reference
    figures, labelled "reference, not production". Test keys only; they never leave this function."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import mldsa

    def accepted(public, signature: bytes) -> bool:
        try:
            public.verify(signature, message)
            return True
        except InvalidSignature:
            return False

    keygen_ms, sign_ms, verify_ms = [], [], []
    key = mldsa.MLDSA65PrivateKey.generate()
    public, signature = key.public_key(), b""
    public.verify(key.sign(message), message)  # warm-up, not timed
    for _ in range(repeats):
        t0 = time.perf_counter()
        key = mldsa.MLDSA65PrivateKey.generate()
        t1 = time.perf_counter()
        signature = key.sign(message)
        t2 = time.perf_counter()
        public = key.public_key()
        t3 = time.perf_counter()
        public.verify(signature, message)
        t4 = time.perf_counter()
        keygen_ms.append(_ms(t1 - t0))
        sign_ms.append(_ms(t2 - t1))
        verify_ms.append(_ms(t4 - t3))
    altered = bytearray(signature)
    altered[len(altered) // 2] ^= 0x01
    control = {"genuine_accepted": accepted(public, signature), "altered_rejected": not accepted(public, bytes(altered)),
               "what": "one byte in the middle of a genuine signature was changed"}
    timings = {"library": reference.LIBRARY, "repeats": repeats, "clock": "time.perf_counter", "keygen_ms": keygen_ms,
               "sign_ms": sign_ms, "verify_ms": verify_ms, "public_key_bytes": len(public.public_bytes_raw()),
               "signature_bytes": len(signature)}
    return timings, control


def run_mldsa_compare(spec: dict, ctx: RunContext) -> dict:
    inputs = spec["inputs"]
    key = component_key(spec, ctx) if spec["target"].get("kind") == "software" else None
    ctx.progress(WAITING, None)
    with ctx.gate.exclusive():
        ctx.begin()
        ctx.progress("measuring ML-DSA-65", 10)
        try:
            timings, control = measure_mldsa65(inputs["repeats"], bytes.fromhex(inputs["message"]))
        except Exception as exc:  # for example: a cryptography build without ML-DSA
            return problem("harness_error", f"ML-DSA-65 is not available in the reference library on this computer ({exc.__class__.__name__}).")
        component = None
        if key is not None:
            ctx.progress("measuring the signing component", 60)
            result = ctx.runner.run_job({"op": "bench_rounds", "keygen_with": key, "subjects": [key], "rounds": 1,
                                         "repeats": inputs["component_repeats"], "message": inputs["message"]}, time_limit=120.0)
            _, benches = _benches(result.lines, ["subject"])
            component = {"key": key, "benches": benches, "batch": batch_info(result)}
            if not result.ok:
                component["error"] = result.problem
    ctx.progress("checking the result", 97)
    return {"mldsa65": timings, "component": component, "control": control, "exclusive": True}
