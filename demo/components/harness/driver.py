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

Real libraries (phase 4c). Inside a real-library container image the driver is started with
the one extra word --real. Only then does it also read that image's own fixed table,
/opt/evidence-lab/real/subjects.json, which was written into the image when it was built
(by `python -m app.prepare`) and names the wrappers of that one library. The table is part
of the image, never of a job.

Jobs:
  {"op": "call", "subject": K, "command": "info", "input": {}}
  {"op": "verify_batch", "subjects": [K, ...], "cases": [{"id", "public_key", "message", "signature"}, ...]}
  {"op": "bench_rounds", "keygen_with": K, "subjects": [K, ...], "rounds": 10, "repeats": 20, "message": "<hex>"}
  {"op": "roundtrip", "subject": K, "message": "<hex>"}
  {"op": "kat_batch", "subject": K, "cases": [{"id", "command", "input": {...}}, ...]}      (phase 4c)
  {"op": "kem_roundtrip", "subject": K, "algorithm": "ML-KEM-768", "peer_public_key": "<hex>"}   (phase 4c)
verify_batch, bench_rounds and roundtrip also take an optional "algorithm" (a library that offers several).
"""
import hashlib
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
# acme-sign 1.4.2 with the change Otto's recorded answer gives (phase 5c). It reports version 1.4.3 and differs from
# our own 1.4.3 in one line: the same range check, written another way.
ACME_143_OTTO = os.path.join(ROOT, "acme-sign-1.4.3-otto", "acme_sign.py")
ACCEPT_ALL = os.path.join(ROOT, "controls", "accept_all.py")
SLOW = os.path.join(ROOT, "controls", "slow.py")

# subject key -> the arguments that come before the command word. The whole list of what can run.
SUBJECTS = {
    "acme-sign-1.4.2": [ACME_142],
    "acme-sign-1.4.3": [ACME_143],
    "acme-sign-1.4.3-otto": [ACME_143_OTTO],
    "control-accept-all": [ACCEPT_ALL],
    "control-slow:acme-sign-1.4.2": [SLOW, ACME_142],
    "control-slow:acme-sign-1.4.3": [SLOW, ACME_143],
    "control-slow:acme-sign-1.4.3-otto": [SLOW, ACME_143_OTTO],
}
COMMANDS = ("keygen", "sign", "verify", "info", "bench", "encaps", "decaps")
CALL_COMMANDS = ("keygen", "sign", "verify", "info", "bench")  # what a plain "call" job may ask; its answer is written out
CALL_LIMIT_SECONDS = 10
BENCH_LIMIT_SECONDS = 60
MAX_CASES = 5000
MAX_HEX = 40000
# Phase 4c. The fixed table of a real-library image, read only when the driver is started with --real.
REAL_TABLE = os.path.join(os.path.dirname(ROOT), "real", "subjects.json")
REAL = {}  # subject key -> the whole command line that comes before the command word
ALGORITHMS = ("ECDSA P-256", "ML-DSA-65", "ML-KEM-768")
INTERFACES = ("external", "internal", "mu")
# What a known-answer case may carry, and which fields of an answer are fingerprinted, per command.
KAT_HEX_INPUTS = ("seed", "public_key", "private_key", "message", "signature", "ciphertext", "randomness", "context")
KAT_COMMANDS = ("keygen", "encaps", "decaps", "sign", "verify")
ANSWER_FIELDS = {"keygen": ("public_key", "private_key"), "encaps": ("ciphertext", "shared_secret"),
                 "decaps": ("shared_secret",), "sign": ("signature",)}
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
    if not isinstance(value, str) or (value not in SUBJECTS and value not in REAL):
        raise Refused("unknown subject")
    return value


def algorithm_of(job):
    """The optional "algorithm" of a job: one of a short fixed list, or None."""
    value = job.get("algorithm")
    if value is not None and value not in ALGORITHMS:
        raise Refused("unknown algorithm")
    return value


def with_algorithm(payload, algorithm):
    return payload if algorithm is None else {**payload, "algorithm": algorithm}


def load_real_table():
    """The real-library image's own table (see the top of this file). Anything unexpected in it stops the driver."""
    with open(REAL_TABLE, "r", encoding="utf-8") as handle:
        table = json.load(handle)
    if not isinstance(table, dict) or not table:
        raise ValueError("bad table")
    for key, argv in table.items():
        if key in SUBJECTS or not isinstance(key, str) or not isinstance(argv, list) or not argv \
                or not all(isinstance(a, str) and a for a in argv):
            raise ValueError("bad table")
    REAL.update(table)


def subject_list(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise Refused("subjects must be a list of one to four subject keys")
    return [subject_key(v) for v in value]


def run_command(subject, command, payload):
    """One component call = one child process. Returns (rc, parsed JSON object or None, error text or None, ms)."""
    if subject in REAL:
        argv = [*REAL[subject], command]
    else:
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
    if command not in CALL_COMMANDS:
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
    algorithm = algorithm_of(job)
    cases = job.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise Refused(f"cases must be a list of 1 to {MAX_CASES} cases")
    clean = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not 1 <= len(case["id"]) <= 64:
            raise Refused("every case needs a short text id")
        if not all(is_hex(case.get(k)) for k in ("public_key", "message", "signature")):
            raise Refused("public_key, message and signature must be hex text")
        clean.append((case["id"], with_algorithm({"public_key": case["public_key"], "message": case["message"],
                                                  "signature": case["signature"]}, algorithm)))

    def one(subject, payload):
        rc, out, error, ms = run_command(subject, "verify", payload)
        valid, note = None, None
        if error is None:
            if isinstance(out.get("valid"), bool):
                valid, note = out["valid"], short_note(out.get("note"))
            else:
                error = "bad output"
        return rc, valid, error, ms, note

    def work():
        # A few calls at a time to keep a 484-case run short; answers are still written in case order.
        workers = max(1, min(4, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for subject in subjects:
                answers = pool.map(lambda item: one(subject, item[1]), clean)
                for (case_id, _), (rc, valid, error, ms, note) in zip(clean, answers):
                    line = {"subject": subject, "id": case_id, "rc": rc, "valid": valid, "error": error, "ms": ms}
                    if note is not None:  # how the library said no, when the wrapper passes it on (phase 4c)
                        line["note"] = note
                    emit(line)
    return work


def short_note(value):
    """A wrapper's optional note (how its library said no), cut to a short plain text. Anything else: None."""
    if not isinstance(value, str) or not value:
        return None
    return "".join(ch if ch.isprintable() else " " for ch in value)[:120]


def op_kat_batch(job):
    """Known-answer cases (phase 4c): one adapter call per case on one subject. Per case the line says whether the
    library declined the input, its yes/no (verify), and the SHA-256 of its answer. The answer itself (a key, a shared
    secret, a signature) is never written out: the reviewer compares fingerprints."""
    subject = subject_key(job.get("subject"))
    cases = job.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise Refused(f"cases must be a list of 1 to {MAX_CASES} cases")
    clean = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not 1 <= len(case["id"]) <= 64:
            raise Refused("every case needs a short text id")
        command, given = case.get("command"), case.get("input")
        if command not in KAT_COMMANDS or not isinstance(given, dict):
            raise Refused("every case needs a known command and an input object")
        payload = {}
        for key, value in given.items():
            if key in KAT_HEX_INPUTS and is_hex(value):
                payload[key] = value
            elif key == "algorithm" and value in ALGORITHMS:
                payload[key] = value
            elif key == "interface" and value in INTERFACES:
                payload[key] = value
            elif key == "deterministic" and isinstance(value, bool):
                payload[key] = value
            else:
                raise Refused("a case input holds something this driver does not pass on")
        clean.append((case["id"], command, payload))

    def one(item):
        case_id, command, payload = item
        rc, out, error, ms = run_command(subject, command, payload)
        # "declined": the library itself said no to this input. (Not "refused": that word, on a line of its own, means
        # the driver refused the whole job.)
        line = {"subject": subject, "id": case_id, "rc": rc, "error": error, "declined": None, "valid": None,
                "answer_sha256": None, "ms": ms}
        if error is not None:
            return line
        note = short_note(out.get("note"))
        if note is not None:
            line["note"] = note
        if out.get("refused") is True:        # the library itself refused this input (a bad key, a wrong length)
            line["declined"] = True
        elif command == "verify":
            if isinstance(out.get("valid"), bool):
                line["declined"], line["valid"] = False, out["valid"]
            else:
                line["error"] = "bad output"
        else:
            fields = [out.get(name) for name in ANSWER_FIELDS[command]]
            if all(is_hex(f) and f for f in fields):
                text = "\n".join(f"{name}={value.lower()}" for name, value in zip(ANSWER_FIELDS[command], fields))
                line["declined"], line["answer_sha256"] = False, hashlib.sha256(text.encode("ascii")).hexdigest()
            else:
                line["error"] = "bad output"
        return line

    def work():
        workers = max(1, min(4, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for line in pool.map(one, clean):  # answers are written in case order
                emit(line)
    return work


def op_kem_roundtrip(job):
    """One ordinary key exchange on one subject (phase 4c), for the Verify step: make a test key pair, encapsulate
    to it, decapsulate, and say whether both sides hold the same secret. Then encapsulate to a public key the app
    made with its own reference library, so the app can confirm the result independently. No key and no shared
    secret is written out: sizes, a yes/no, one ciphertext and one fingerprint only."""
    subject = subject_key(job.get("subject"))
    algorithm = algorithm_of(job)
    peer = job.get("peer_public_key")
    if not is_hex(peer) or not peer:
        raise Refused("peer_public_key must be hex text")

    def work():
        def step(name, rc, out, error, ms):
            emit({"subject": subject, "step": name, "rc": rc, "out": out if error is None else None, "error": error, "ms": ms})
            return error is None

        def ask(command, payload):
            rc, out, error, ms = run_command(subject, command, with_algorithm(payload, algorithm))
            if error is None and out.get("refused") is True:
                error = "the library refused: " + (short_note(out.get("note")) or "no reason given")
            return rc, out, error, ms

        rc, out, error, ms = ask("keygen", {})
        public = out.get("public_key") if error is None else None
        private = out.get("private_key") if error is None else None
        if error is None and not (is_hex(public) and public and is_hex(private) and private):
            error = "bad output"
        if not step("keygen", rc, {"public_key_bytes": len(public or "") // 2, "private_key": WITHHELD}, error, ms):
            return
        rc, out, error, ms = ask("encaps", {"public_key": public})
        ciphertext = out.get("ciphertext") if error is None else None
        secret = out.get("shared_secret") if error is None else None
        if error is None and not (is_hex(ciphertext) and ciphertext and is_hex(secret) and secret):
            error = "bad output"
        if not step("encaps", rc, {"ciphertext_bytes": len(ciphertext or "") // 2, "shared_secret_bytes": len(secret or "") // 2}, error, ms):
            return
        rc, out, error, ms = ask("decaps", {"private_key": private, "ciphertext": ciphertext})
        again = out.get("shared_secret") if error is None else None
        if error is None and not (is_hex(again) and again):
            error = "bad output"
        if not step("decaps", rc, {"same_secret": error is None and again.lower() == secret.lower()}, error, ms):
            return
        rc, out, error, ms = ask("encaps", {"public_key": peer})
        ciphertext = out.get("ciphertext") if error is None else None
        secret = out.get("shared_secret") if error is None else None
        if error is None and not (is_hex(ciphertext) and ciphertext and is_hex(secret) and secret):
            error = "bad output"
        step("encaps_to_app", rc, {"ciphertext": ciphertext,
                                   "shared_secret_sha256": hashlib.sha256(bytes.fromhex(secret or "")).hexdigest()}, error, ms)
    return work


def op_bench_rounds(job):
    keygen_with = subject_key(job.get("keygen_with"))
    subjects = subject_list(job.get("subjects"))
    algorithm = algorithm_of(job)
    rounds = whole(job.get("rounds"), 1, 50, "rounds")
    repeats = whole(job.get("repeats"), 1, 1000, "repeats")
    message = job.get("message", "")
    if not is_hex(message):
        raise Refused("message must be hex text")

    def work():
        rc, out, error, _ = run_command(keygen_with, "keygen", with_algorithm({}, algorithm))
        key = out.get("private_key") if error is None else None
        public = out.get("public_key") if error is None else None
        limit = (200, 400) if algorithm is None else (MAX_HEX, MAX_HEX)  # a post-quantum key is longer
        if not is_hex(key, limit[0]) or not key or not is_hex(public, limit[1]):
            emit({"keygen": keygen_with, "rc": rc, "public_key_bytes": None, "error": error or "bad output"})
            return
        emit({"keygen": keygen_with, "rc": rc, "public_key_bytes": len(public) // 2})
        # The test key lives only in this process and in the stdin of each bench call. It is never written out.
        # (The public key goes along too: a library that can't work it out from the private key needs it to verify.)
        payload = with_algorithm({"repeats": repeats, "message": message, "private_key": key, "public_key": public}, algorithm)
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
    algorithm = algorithm_of(job)
    message = job.get("message", "")
    if not is_hex(message):
        raise Refused("message must be hex text")

    def work():
        def step(name, rc, out, error, ms):
            emit({"subject": subject, "step": name, "rc": rc, "out": out if error is None else None, "error": error, "ms": ms})
            return error is None

        rc, out, error, ms = run_command(subject, "keygen", with_algorithm({}, algorithm))
        key = out.get("private_key") if error is None else None
        public = out.get("public_key") if error is None else None
        limit = (200, 400) if algorithm is None else (MAX_HEX, MAX_HEX)  # a post-quantum key is longer
        if error is None and (not is_hex(key, limit[0]) or not key or not is_hex(public, limit[1]) or not public):
            error = "bad output"
        if not step("keygen", rc, {"public_key": public, "private_key": WITHHELD}, error, ms):
            return
        rc, out, error, ms = run_command(subject, "sign", with_algorithm({"private_key": key, "message": message}, algorithm))
        signature = out.get("signature") if error is None else None
        if error is None and key in json.dumps(out):
            error = "sign output contained the test private key"
        elif error is None and (not is_hex(signature) or not signature):
            error = "bad output"
        if not step("sign", rc, {"signature": signature}, error, ms):
            return
        rc, out, error, ms = run_command(subject, "verify", with_algorithm({"public_key": public, "message": message, "signature": signature}, algorithm))
        if error is None and not isinstance(out.get("valid"), bool):
            error = "bad output"
        step("verify", rc, {"valid": out.get("valid")} if error is None else None, error, ms)
    return work


OPS = {"call": op_call, "verify_batch": op_verify_batch, "bench_rounds": op_bench_rounds, "roundtrip": op_roundtrip,
       "kat_batch": op_kat_batch, "kem_roundtrip": op_kem_roundtrip}


def main():
    if sys.argv[1:] == ["--real"]:
        try:
            load_real_table()
        except (OSError, ValueError):
            emit({"refused": "this image's table of real-library subjects could not be read"})
            return 2
    elif sys.argv[1:]:
        emit({"refused": "unknown argument"})
        return 2
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
