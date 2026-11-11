#!/usr/bin/env python3
"""Evidence Lab batch driver. Our own code; standard library only.

Started ONCE per test run (as one local process in demo mode, or as the one process of a
locked-down container in isolated mode). It reads ONE JSON job from standard input, runs the
component command line once per case - every call is its own child process, exactly as the
adapter describes (docs/ADAPTER.md) - and writes one JSON line per answer to standard output.
The last line is always {"done": true, "lines": <count>}.

What it will run is fixed by the SUBJECTS table below. Nothing in a job is ever used as a
path, a program name or an argument: a job only names a subject key from that table and
carries test data (hex strings and small numbers). A job that does not fit is refused with
one {"refused": "..."} line and exit code 2, before anything is run.

Jobs:
  {"op": "call", "subject": K, "command": "info", "input": {}}
  {"op": "verify_batch", "subjects": [K, ...], "cases": [{"id", "public_key", "message", "signature"}, ...]}
  {"op": "bench_rounds", "keygen_with": K, "subjects": [K, ...], "rounds": 10, "repeats": 20, "message": "<hex>"}
  {"op": "roundtrip", "subject": K, "message": "<hex>"}
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ACME_142 = os.path.join(ROOT, "acme-sign-1.4.2", "acme_sign.py")
ACME_143 = os.path.join(ROOT, "acme-sign-1.4.3", "acme_sign.py")
ACCEPT_ALL = os.path.join(ROOT, "controls", "accept_all.py")
SLOW = os.path.join(ROOT, "controls", "slow.py")

# subject key -> the arguments that come before the command word. The whole list of what can run.
SUBJECTS = {
    "acme-sign-1.4.2": [ACME_142],
    "acme-sign-1.4.3": [ACME_143],
    "control-accept-all": [ACCEPT_ALL],
    "control-slow:acme-sign-1.4.2": [SLOW, ACME_142],
    "control-slow:acme-sign-1.4.3": [SLOW, ACME_143],
}
COMMANDS = ("keygen", "sign", "verify", "info", "bench")
CALL_LIMIT_SECONDS = 10
BENCH_LIMIT_SECONDS = 60
MAX_CASES = 5000
MAX_HEX = 20000
MAX_CHILD_OUTPUT = 256 * 1024
WITHHELD = "[test private key withheld]"
HEX = set("0123456789abcdefABCDEF")

# Children share the driver's own bytecode cache folder (the app points it at the scratch folder, which makes
# each call start faster). Started by hand without one, nothing is cached and no folder is created.
CACHE_FLAGS = ["-X", "pycache_prefix=" + sys.pycache_prefix] if sys.pycache_prefix else ["-B"]

_lines = 0


class Refused(Exception):
    pass


def emit(obj):
    global _lines
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()
    _lines += 1


def is_hex(value, limit=MAX_HEX):
    return isinstance(value, str) and len(value) <= limit and len(value) % 2 == 0 and all(c in HEX for c in value)


def whole(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Refused(f"{name} must be a whole number from {low} to {high}")
    return value


def subject_key(value):
    if not isinstance(value, str) or value not in SUBJECTS:
        raise Refused("unknown subject")
    return value


def subject_list(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise Refused("subjects must be a list of one to four subject keys")
    return [subject_key(v) for v in value]


def run_command(subject, command, payload):
    """One component call = one child process. Returns (rc, parsed JSON object or None, error text or None, ms)."""
    argv = [sys.executable, "-I", *CACHE_FLAGS, *SUBJECTS[subject], command]
    limit = BENCH_LIMIT_SECONDS if command == "bench" else CALL_LIMIT_SECONDS
    t0 = time.perf_counter()
    try:
        done = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True, errors="replace",
                              timeout=limit, shell=False, env={"PATH": os.defpath, "LANG": "C.UTF-8",
                                                               "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        return None, None, "timeout", round((time.perf_counter() - t0) * 1000, 1)
    except OSError:
        return None, None, "could not start", round((time.perf_counter() - t0) * 1000, 1)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    out = None
    if len(done.stdout) <= MAX_CHILD_OUTPUT:
        try:
            out = json.loads(done.stdout)
        except ValueError:
            out = None
    if not isinstance(out, dict):
        return done.returncode, None, "bad output", ms
    if "error" in out:
        return done.returncode, out, str(out["error"])[:120], ms
    return done.returncode, out, None, ms


def op_call(job):
    subject = subject_key(job.get("subject"))
    command = job.get("command")
    if command not in COMMANDS:
        raise Refused("unknown command")
    payload = job.get("input", {})
    if not isinstance(payload, dict):
        raise Refused("input must be a JSON object")

    def work():
        rc, out, error, ms = run_command(subject, command, payload)
        if error is not None:
            out = None
        elif "private_key" in out:
            out = {**out, "private_key": WITHHELD}
        emit({"subject": subject, "command": command, "rc": rc, "out": out, "error": error, "ms": ms})
    return work


def op_verify_batch(job):
    subjects = subject_list(job.get("subjects"))
    cases = job.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise Refused(f"cases must be a list of 1 to {MAX_CASES} cases")
    clean = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not 1 <= len(case["id"]) <= 64:
            raise Refused("every case needs a short text id")
        if not all(is_hex(case.get(k)) for k in ("public_key", "message", "signature")):
            raise Refused("public_key, message and signature must be hex text")
        clean.append((case["id"], {"public_key": case["public_key"], "message": case["message"],
                                   "signature": case["signature"]}))

    def one(subject, payload):
        rc, out, error, ms = run_command(subject, "verify", payload)
        valid = None
        if error is None:
            if isinstance(out.get("valid"), bool):
                valid = out["valid"]
            else:
                error = "bad output"
        return rc, valid, error, ms

    def work():
        # A few calls at a time to keep a 484-case run short; answers are still written in case order.
        workers = max(1, min(4, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for subject in subjects:
                answers = pool.map(lambda item: one(subject, item[1]), clean)
                for (case_id, _), (rc, valid, error, ms) in zip(clean, answers):
                    emit({"subject": subject, "id": case_id, "rc": rc, "valid": valid, "error": error, "ms": ms})
    return work


def op_bench_rounds(job):
    keygen_with = subject_key(job.get("keygen_with"))
    subjects = subject_list(job.get("subjects"))
    rounds = whole(job.get("rounds"), 1, 50, "rounds")
    repeats = whole(job.get("repeats"), 1, 1000, "repeats")
    message = job.get("message", "")
    if not is_hex(message):
        raise Refused("message must be hex text")

    def work():
        rc, out, error, _ = run_command(keygen_with, "keygen", {})
        key = out.get("private_key") if error is None else None
        public = out.get("public_key") if error is None else None
        if not is_hex(key, 200) or not key or not is_hex(public, 400):
            emit({"keygen": keygen_with, "rc": rc, "public_key_bytes": None, "error": error or "bad output"})
            return
        emit({"keygen": keygen_with, "rc": rc, "public_key_bytes": len(public) // 2})
        # The test key lives only in this process and in the stdin of each bench call. It is never written out.
        payload = {"repeats": repeats, "message": message, "private_key": key}
        for number in range(rounds):
            order = subjects if number % 2 == 0 else list(reversed(subjects))
            for subject in order:  # one at a time, never in parallel: these are timings
                rc, out, error, _ = run_command(subject, "bench", payload)
                if error is None and key in json.dumps(out):
                    out, error = None, "bench output contained the test private key"
                emit({"round": number, "subject": subject, "rc": rc, "out": out if error is None else None, "error": error})
    return work


def op_roundtrip(job):
    """One ordinary keygen -> sign -> verify on one subject. The test key is made here and handed only to the
    sign call's stdin; it is never written out. One line per step; it stops at the first step that fails."""
    subject = subject_key(job.get("subject"))
    message = job.get("message", "")
    if not is_hex(message):
        raise Refused("message must be hex text")

    def work():
        def step(name, rc, out, error, ms):
            emit({"subject": subject, "step": name, "rc": rc, "out": out if error is None else None, "error": error, "ms": ms})
            return error is None

        rc, out, error, ms = run_command(subject, "keygen", {})
        key = out.get("private_key") if error is None else None
        public = out.get("public_key") if error is None else None
        if error is None and (not is_hex(key, 200) or not key or not is_hex(public, 400) or not public):
            error = "bad output"
        if not step("keygen", rc, {"public_key": public, "private_key": WITHHELD}, error, ms):
            return
        rc, out, error, ms = run_command(subject, "sign", {"private_key": key, "message": message})
        signature = out.get("signature") if error is None else None
        if error is None and key in json.dumps(out):
            error = "sign output contained the test private key"
        elif error is None and (not is_hex(signature) or not signature):
            error = "bad output"
        if not step("sign", rc, {"signature": signature}, error, ms):
            return
        rc, out, error, ms = run_command(subject, "verify", {"public_key": public, "message": message, "signature": signature})
        if error is None and not isinstance(out.get("valid"), bool):
            error = "bad output"
        step("verify", rc, {"valid": out.get("valid")} if error is None else None, error, ms)
    return work


OPS = {"call": op_call, "verify_batch": op_verify_batch, "bench_rounds": op_bench_rounds, "roundtrip": op_roundtrip}


def main():
    try:
        job = json.loads(sys.stdin.read())
        if not isinstance(job, dict) or job.get("op") not in OPS:
            raise Refused("unknown job")
        work = OPS[job["op"]](job)  # checks the whole job first; nothing has run yet
    except Refused as exc:
        emit({"refused": str(exc)})
        return 2
    except ValueError:
        emit({"refused": "the job was not JSON"})
        return 2
    work()
    emit({"done": True, "lines": _lines})
    return 0


if __name__ == "__main__":
    sys.exit(main())
