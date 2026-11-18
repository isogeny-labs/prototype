"""Running OUR OWN demo components, and checking a software claim against one.

Only components in the fixed registry below can run. The registry maps an exact (name, version)
to a hard-coded path; no path is ever built from anything in an uploaded file.
In demo mode the Verify step runs the component as a local process ("Demo mode: running our own demo
software, not isolated."). In isolated mode it goes through the same container runner as the tests, and
never falls back to a local process.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.engine.compare import COULDNT, FALSE, TRUE
from app.config import DEMO_DIR, REPO_ROOT
from app import real_libraries
from app.names import clean_text, normalize_algorithm, same_algorithm

COMMANDS = ("keygen", "sign", "verify", "info", "bench")
TIME_LIMIT_SECONDS = 20
MAX_OUTPUT = 64 * 1024
WITHHELD = "[test private key withheld]"
NOT_A_DEMO_COMPONENT = "Only our demo components can run in demo mode"

OTTO_VERSION = "1.4.3-otto"
_REGISTRY: dict[tuple[str, str], Path] = {
    ("acme-sign", "1.4.2"): DEMO_DIR / "components" / "acme-sign-1.4.2" / "acme_sign.py",
    ("acme-sign", "1.4.3"): DEMO_DIR / "components" / "acme-sign-1.4.3" / "acme_sign.py",
    # Phase 5c (Kevin's decision, 18 November 2026): the program that Otto's recorded change for acme-sign 1.4.2 gives,
    # registered as one of our demo programs so that Otto's own change can be proven, merged and retested on the demo.
    # The file is exactly what the recorded answer's edits make of 1.4.2 (a test rebuilds it and compares). The program
    # reports version 1.4.3; the registry names it 1.4.3-otto, because it is not the same file as our own 1.4.3.
    ("acme-sign", OTTO_VERSION): DEMO_DIR / "components" / "acme-sign-1.4.3-otto" / "acme_sign.py",
}
# The demo versions a retest can choose between. There is no way to add software to this list from outside.
VERSIONS: dict[str, list[str]] = {"acme-sign": ["1.4.2", "1.4.3"]}
# Registered demo programs that only a change leads to: a retest can choose one once the change that gives it is
# merged in that assessment (and Retest now runs it). They are not in the general list of versions to retest on.
CHANGE_VERSIONS: dict[str, list[str]] = {"acme-sign": [OTTO_VERSION]}
# What a screen may say about a registered version beside its name.
VERSION_NOTES: dict[tuple[str, str], str] = {
    ("acme-sign", OTTO_VERSION): ("acme-sign 1.4.2 with the change Otto wrote, registered as one of our demo programs. It reports version "
                                  "1.4.3, and differs from our own acme-sign 1.4.3 in one line: the same range check, written another way."),
}
_PEM_PRIVATE = re.compile(r"-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----.*?(?:-----END \1PRIVATE KEY-----|\Z)", re.DOTALL)


def lookup(name: object, version: object) -> Path | None:
    """Exact match on (name, version) only. Anything else - including '../' tricks - is simply not found."""
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    return _REGISTRY.get((name, version))


def kind_of(name: object, version: object) -> str | None:
    """What a named program is to this app: "demo" (one of our own demo components), "real" (a registered real
    library, phase 4c: it runs only in isolated mode, in its own container image), or None (it can't run)."""
    if lookup(name, version) is not None:
        return "demo"
    return "real" if real_libraries.library(name, version) is not None else None


def registered_version(name: str | None, files: dict[str, bytes]) -> str | None:
    """The byte-for-byte check. Which registered version of our demo component is exactly this code (the same
    one file with the same bytes), or None. Nothing is run to find out."""
    for version in VERSIONS.get(name or "", []) + CHANGE_VERSIONS.get(name or "", []):
        path = lookup(name, version)
        if path is not None and files == {path.name: path.read_bytes()}:
            return version
    return None


def version_note(name: object, version: object) -> str | None:
    return VERSION_NOTES.get((name, version)) if isinstance(name, str) and isinstance(version, str) else None


def versions_of(name: object) -> list[str]:
    """The versions a retest can choose between for this program, oldest first. Nothing outside can add to it."""
    if isinstance(name, str) and name in VERSIONS:
        return list(VERSIONS[name])
    found = real_libraries.LIBRARIES.get(name) if isinstance(name, str) else None
    return list(found["versions"]) if found else []


def component_key(name: str, version: str) -> str:
    """The name the test harness knows a registered component by, for example "acme-sign-1.4.3" or "openjdk-17.0.2"."""
    if kind_of(name, version) is None:
        raise ValueError("not a registered component")
    return f"{name}-{version}"


@dataclass
class Run:
    command: str
    ok: bool
    data: dict | None
    stdout: str
    problem: str | None
    started_at: str
    duration_ms: int


def run_component(path: Path, command: str, payload: dict | None = None,
                  time_limit: float = TIME_LIMIT_SECONDS) -> Run:
    """Run one command of a demo component: argument list, no shell, time limit, minimal environment."""
    if command not in COMMANDS:
        raise ValueError("unknown component command")
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    t0 = time.perf_counter()
    data, stdout, problem = None, "", None
    with tempfile.TemporaryDirectory(prefix="evidence-lab-run-") as scratch:
        try:
            done = subprocess.run(
                [sys.executable, "-I", "-B", str(path), command],
                input=json.dumps(payload or {}), capture_output=True, text=True, errors="replace",
                timeout=time_limit, cwd=scratch, shell=False,
                env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"},
            )
            stdout = done.stdout[:MAX_OUTPUT]
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    problem = "its output was not a JSON object"
            except json.JSONDecodeError:
                problem = "its output was not JSON"
            if data is not None and "error" in data:
                problem = f"it reported an error: {clean_text(data['error'], 120)}"
        except subprocess.TimeoutExpired:
            problem = f"it did not finish within {int(time_limit)} seconds"
        except OSError as exc:
            problem = f"it could not be started ({exc.__class__.__name__})"
    return Run(command, problem is None, data, stdout, problem, started, int((time.perf_counter() - t0) * 1000))


def _mask_text(text: str) -> str:
    return _PEM_PRIVATE.sub(WITHHELD, text)


def scrub(obj: object) -> object:
    """A copy of a JSON-like value with every private key replaced: any field whose name contains "private",
    and any PEM private-key block inside any text. Everything stored or shown passes through this."""
    if isinstance(obj, dict):
        return {k: (WITHHELD if "private" in str(k).lower() else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return _mask_text(obj)
    return obj


def redact(value: object, secrets: list[str] | tuple[str, ...] = ()) -> str:
    """JSON text for evidence with every private key replaced. Keys never reach the database or the screen."""
    text = value if isinstance(value, str) else json.dumps(scrub(value))
    text = _mask_text(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, WITHHELD)
    return text


_redact = redact


def _evidence(path: Path, title: str, run: Run, payload: dict | None, secrets: list[str]) -> dict:
    try:
        shown = path.relative_to(REPO_ROOT)
    except ValueError:
        shown = path.name
    stdin_text = _redact(payload or {}, secrets)
    output = _redact(run.data, secrets) if run.data is not None else _redact(run.stdout, secrets)
    if run.problem:
        output = (output + "\n" if output.strip() else "") + f"(problem: {run.problem})"
    return {"title": title, "command": f"python {shown} {run.command}    (input on stdin: {stdin_text})",
            "output": output, "started_at": run.started_at, "duration_ms": run.duration_ms,
            "tool": "Demo component, run by Evidence Lab in demo mode (not isolated)",
            "tool_version": f"Python {platform.python_version()}"}


ISOLATED_TOOL = "Demo component, run by Evidence Lab in isolated mode (locked-down container, no network)"
STEP_TITLES = {"keygen": "Make a throwaway test key (keygen)", "sign": "Sign a random test message (sign)",
               "verify": "Check that signature with the component itself (verify)"}


def _isolated_claim(path: Path, claimed_name: str, claimed_version: str, claimed_algorithm: str, runner) -> dict:
    """The same check as below, with the component run by the container runner (isolated mode). The test key is
    made and used inside the harness and never comes back. If the container can't be used, the answer is
    Couldn't check: the component is never run as a local process instead."""
    evidence: list[dict] = []
    version_text = f"image {runner.mode.components_image}" if runner.mode.components_image else "no image"

    def out(result: str, found: str, reason: str | None = None) -> dict:
        return {"result": result, "found": found, "reason": reason, "evidence": evidence}

    def record(title: str, batch, line: dict | None, started: str | None = None) -> None:
        output = _redact(line) if line is not None else ""
        if line is None or line.get("error"):
            problem = (line or {}).get("error") or batch.problem or "no answer"
            output = (output + "\n" if output else "") + f"(problem: {clean_text(str(problem), 200)})"
        evidence.append({"title": title, "command": batch.command, "output": output, "started_at": started or batch.started_at,
                         "duration_ms": int(line["ms"]) if line and isinstance(line.get("ms"), (int, float)) else batch.duration_ms,
                         "tool": ISOLATED_TOOL, "tool_version": version_text})

    def unavailable(batch) -> dict | None:
        if batch.problem and batch.problem.startswith("isolated mode is not available"):
            evidence.clear()
            return out(COULDNT, "The component was not run.",
                       "Isolated mode is not available on this computer, so the component was not run.")
        return None

    subject = next((f"{n}-{v}" for (n, v), p in _REGISTRY.items() if p == path), None)
    if subject is None:
        return out(COULDNT, "The component was not run.", NOT_A_DEMO_COMPONENT)
    batch = runner.run_job({"op": "call", "subject": subject, "command": "info", "input": {}}, time_limit=TIME_LIMIT_SECONDS)
    if (stopped := unavailable(batch)) is not None:
        return stopped
    line = batch.lines[0] if batch.lines else None
    record("Ask the component what it is (info)", batch, line)
    data = line.get("out") if batch.ok and line and not line.get("error") else None
    if not isinstance(data, dict):
        return out(COULDNT, "The component did not answer the info command.",
                   f"The info command failed: {clean_text(str((line or {}).get('error') or batch.problem or 'no answer'), 120)}.")
    verdict = _info_verdict(data, claimed_name, claimed_version, claimed_algorithm, out)
    if isinstance(verdict, dict):
        return verdict
    reported = verdict

    message = os.urandom(32).hex()
    batch = runner.run_job({"op": "roundtrip", "subject": subject, "message": message}, time_limit=3 * TIME_LIMIT_SECONDS)
    if (stopped := unavailable(batch)) is not None:
        evidence.clear()
        return stopped
    steps = {line.get("step"): line for line in batch.lines}
    for name in ("keygen", "sign", "verify"):
        if name in steps:
            record(STEP_TITLES[name], batch, steps[name])

    def answer(name: str, field: str, kind: type):
        value = (steps.get(name, {}).get("out") or {}).get(field) if not steps.get(name, {}).get("error") else None
        return value if isinstance(value, kind) else None

    def failed(name: str, missing: str) -> str:
        return f"The {name} command failed: {clean_text(str(steps.get(name, {}).get('error') or batch.problem or missing), 120)}."

    public_key, signature, valid = answer("keygen", "public_key", str), answer("sign", "signature", str), answer("verify", "valid", bool)
    if public_key is None:
        return out(COULDNT, f"The component reports itself as {reported}, but could not make a test key.", failed("keygen", "no key in its answer"))
    if signature is None:
        return out(COULDNT, f"The component reports itself as {reported}, but could not sign a test message.",
                   failed("sign", "no signature in its answer"))
    if valid is None or not batch.ok:
        return out(COULDNT, f"The component reports itself as {reported}, but its verify command did not answer.",
                   failed("verify", "no yes/no in its answer"))
    return _independent_verdict(reported, public_key, message, signature, valid, evidence, out)


REAL_TOOL = "Real library, run by Evidence Lab in isolated mode (its own locked-down container, no network)"
REAL_ALGORITHMS = ("ECDSA P-256", "ML-DSA-65", "ML-KEM-768")
KEM_STEP_TITLES = {"keygen": "Make a throwaway test key pair (keygen)", "encaps": "Encapsulate to that key (encaps)",
                   "decaps": "Decapsulate with the test key (decaps): do both sides hold the same secret?",
                   "encaps_to_app": "Encapsulate to a key made by this app's reference library (encaps)"}


def _same_maker_note(family: str | None) -> str:
    """For OpenSSL the check below is not an outside opinion: the app's reference library (cryptography) is itself built
    on a release of OpenSSL. Said in the result, so nobody reads more into it than it shows."""
    if family != "openssl":
        return ""
    try:
        from cryptography.hazmat.backends.openssl import backend
        built_on = f" ({backend.openssl_version_text()})"
    except Exception:
        built_on = ""
    return (f" Note: the reference library (cryptography) is itself built on a release of OpenSSL{built_on}, so for this library the "
            "check shows that two releases of OpenSSL agree, not that an outside implementation agrees. The exams, whose right "
            "answers are NIST's and Wycheproof's, are the outside check.")


def verify_real_claim(name: str, version: str, claimed_algorithm: str, runner=None, key_exchange: bool = False) -> dict:
    """Check "library NAME VERSION uses ALGORITHM" for a real library (phase 4c). Isolated mode only: the library
    runs in its own container image, and is never run as a local program instead.

    1. `info`: name, version and algorithm must match the claim.
    2. One ordinary round trip: keygen -> sign -> verify, or for a key exchange keygen -> encaps -> decaps.
    3. Independently, with the `cryptography` library: the signature must verify, or (key exchange) this app
       decapsulates a ciphertext the library made for the app's own test key and must get the same secret.
    This says what the library IS, not whether it is built correctly - that is what the tests are for."""
    evidence: list[dict] = []

    def out(result: str, found: str, reason: str | None = None) -> dict:
        return {"result": result, "found": found, "reason": reason, "evidence": evidence}

    family = real_libraries.family_of(name, version)
    if runner is None or runner.mode.name != "isolated":
        return out(COULDNT, "The library was not run.", real_libraries.NEEDS_ISOLATED + ", and this run is in demo mode.")
    if not runner.mode.real_images.get(family):
        return out(COULDNT, "The library was not run.",
                   f"The container image for {real_libraries.FAMILIES[family]['label']} is not prepared on this computer "
                   "(./run-demo.sh prepares it; it needs internet once).")
    subject, tool_version = f"{name}-{version}", f"image {runner.mode.real_images[family]}"
    algorithm = normalize_algorithm(claimed_algorithm) or claimed_algorithm

    def record(title: str, batch, line: dict | None) -> None:
        output = _redact(line) if line is not None else ""
        if line is None or line.get("error"):
            problem = (line or {}).get("error") or batch.problem or "no answer"
            output = (output + "\n" if output else "") + f"(problem: {clean_text(str(problem), 200)})"
        evidence.append({"title": title, "command": batch.command, "output": output, "started_at": batch.started_at,
                         "duration_ms": int(line["ms"]) if line and isinstance(line.get("ms"), (int, float)) else batch.duration_ms,
                         "tool": REAL_TOOL, "tool_version": tool_version})

    ask = {"algorithm": algorithm} if algorithm in REAL_ALGORITHMS else {}
    batch = runner.run_job({"op": "call", "subject": subject, "command": "info", "input": ask}, time_limit=TIME_LIMIT_SECONDS, family=family)
    line = batch.lines[0] if batch.lines else None
    record("Ask the library what it is (info)", batch, line)
    data = line.get("out") if batch.ok and line and not line.get("error") else None
    if not isinstance(data, dict):
        return out(COULDNT, "The library did not answer the info command.",
                   f"The info command failed: {clean_text(str((line or {}).get('error') or batch.problem or 'no answer'), 120)}.")
    verdict = _info_verdict(data, name, version, claimed_algorithm, out, REAL_ALGORITHMS)
    if isinstance(verdict, dict):
        return verdict
    reported = verdict
    if key_exchange != (algorithm == "ML-KEM-768"):
        return out(COULDNT, f"The library reports itself as {reported}.",
                   "The file's claim and the algorithm are not the same kind (a signature and a key exchange), so the round trip was not run.")

    def failed(steps: dict, step: str, missing: str) -> str:
        return f"The {step} command failed: {clean_text(str(steps.get(step, {}).get('error') or batch.problem or missing), 120)}."

    if key_exchange:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import mlkem
        ours = mlkem.MLKEM768PrivateKey.generate()   # this app's own throwaway test key; it never leaves this function
        peer = ours.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        batch = runner.run_job({"op": "kem_roundtrip", "subject": subject, "algorithm": algorithm, "peer_public_key": peer},
                               time_limit=3 * TIME_LIMIT_SECONDS, family=family)
        steps = {line.get("step"): line for line in batch.lines}
        for step in ("keygen", "encaps", "decaps", "encaps_to_app"):
            if step in steps:
                record(KEM_STEP_TITLES[step], batch, steps[step])
        for step in ("keygen", "encaps", "decaps", "encaps_to_app"):
            if step not in steps or steps[step].get("error") or not isinstance(steps[step].get("out"), dict):
                return out(COULDNT, f"The library reports itself as {reported}, but its {step.split('_')[0]} command did not answer.",
                           failed(steps, step, "no answer"))
        if steps["decaps"]["out"].get("same_secret") is not True:
            return out(FALSE, f"The library reports itself as {reported}, but after one key exchange the two sides did not hold the same secret.")
        made = steps["encaps_to_app"]["out"]
        started, t0 = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), time.perf_counter()
        try:
            same = hashlib.sha256(ours.decapsulate(bytes.fromhex(str(made.get("ciphertext"))))).hexdigest() == made.get("shared_secret_sha256")
        except (ValueError, TypeError):
            same = False
        import cryptography
        evidence.append({"title": "Independent check with a reference library",
                         "command": "cryptography: MLKEM768PrivateKey.decapsulate(the library's ciphertext); compare SHA-256 of the two secrets",
                         "output": ("OK: " if same else "FAILED: ") + ("this app decapsulated the library's ciphertext and got the same shared secret."
                                                                      if same else "this app did not get the same shared secret from the library's ciphertext."),
                         "started_at": started, "duration_ms": int((time.perf_counter() - t0) * 1000),
                         "tool": "cryptography (pyca)", "tool_version": cryptography.__version__})
        if not same:
            return out(FALSE, f"The library reports itself as {reported}, but an independent check failed: a reference library did not get "
                              "the same shared secret from its ciphertext.")
        return out(TRUE, f"The library reports itself as {reported}. It made a test key pair, encapsulated and decapsulated, and both sides held "
                         "the same 32-byte secret. The app's reference library (cryptography) decapsulated a second ciphertext from it and got the "
                         "same secret." + _same_maker_note(family))

    message = os.urandom(32).hex()
    job = {"op": "roundtrip", "subject": subject, "message": message}
    if algorithm != "ECDSA P-256":
        job["algorithm"] = algorithm
    batch = runner.run_job(job, time_limit=3 * TIME_LIMIT_SECONDS, family=family)
    steps = {line.get("step"): line for line in batch.lines}
    for step in ("keygen", "sign", "verify"):
        if step in steps:
            record(STEP_TITLES[step].replace("component", "library"), batch, steps[step])

    def answer(step: str, field: str, kind: type):
        value = (steps.get(step, {}).get("out") or {}).get(field) if not steps.get(step, {}).get("error") else None
        return value if isinstance(value, kind) else None

    public_key, signature, valid = answer("keygen", "public_key", str), answer("sign", "signature", str), answer("verify", "valid", bool)
    if public_key is None:
        return out(COULDNT, f"The library reports itself as {reported}, but could not make a test key.", failed(steps, "keygen", "no key in its answer"))
    if signature is None:
        return out(COULDNT, f"The library reports itself as {reported}, but could not sign a test message.", failed(steps, "sign", "no signature in its answer"))
    if valid is None or not batch.ok:
        return out(COULDNT, f"The library reports itself as {reported}, but its verify command did not answer.", failed(steps, "verify", "no yes/no in its answer"))
    return _independent_verdict(reported, public_key, message, signature, valid, evidence, out, algorithm, "library", _same_maker_note(family))


def _info_verdict(data: dict, claimed_name: str, claimed_version: str, claimed_algorithm: str, out, known: tuple = ("ECDSA P-256",)):
    """From the info answer alone: a finished result (dict), or the text of what the component says it is."""
    name, version, algorithm = (data.get(k) for k in ("name", "version", "algorithm"))
    if not all(isinstance(v, str) and v for v in (name, version, algorithm)):
        return out(COULDNT, "The component's info answer is missing its name, version or algorithm.",
                   "The info answer was incomplete.")
    reported = f"{clean_text(name, 60)} {clean_text(version, 30)} using {clean_text(algorithm, 60)}"
    mismatches = []
    if name.strip().casefold() != claimed_name.strip().casefold():
        mismatches.append("name")
    if version.strip() != claimed_version.strip():
        mismatches.append("version")
    if not same_algorithm(algorithm, claimed_algorithm):
        mismatches.append("algorithm")
    if mismatches:
        return out(FALSE, f"The component reports itself as {reported}. The {' and '.join(mismatches)} "
                          f"{'does' if len(mismatches) == 1 else 'do'} not match the claim.")
    if normalize_algorithm(claimed_algorithm) not in known:
        return out(COULDNT, f"The component reports itself as {reported}, which matches the claim.",
                   "This version can only double-check signatures for ECDSA P-256, so the sign-and-verify check was not run.")
    return reported


def _independent_verdict(reported: str, public_key: str, message: str, signature: str, component_valid: bool,
                         evidence: list[dict], out, algorithm: str = "ECDSA P-256", what: str = "component", note: str = "") -> dict:
    if algorithm == "ML-DSA-65":
        independent_ok, independent_note, ref = _independent_mldsa_check(public_key, message, signature)
        real_words, confirmed = "ML-DSA-65", "confirmed the key is an ML-DSA-65 key and the signature is a valid ML-DSA-65 signature."
    else:
        independent_ok, independent_note, ref = _independent_p256_check(public_key, message, signature)
        real_words, confirmed = "ECDSA P-256", "confirmed the key is P-256 and the signature is valid ECDSA P-256 with SHA-256."
    evidence.append(ref)
    if independent_ok is None:
        return out(COULDNT, f"The {what} reports itself as {reported}.", independent_note)
    if not independent_ok:
        return out(FALSE, f"The {what} reports itself as {reported}, but an independent check failed: {independent_note}")
    if component_valid is not True:
        return out(FALSE, f"The {what} reports itself as {reported} and its signature is a real {real_words} "
                          f"signature, but the {what} rejected its own signature.")
    return out(TRUE, f"The {what} reports itself as {reported}. It signed a test message and verified it, and an "
                     f"independent library (cryptography) {confirmed}" + note)


def _independent_mldsa_check(public_key_hex: str, message_hex: str, signature_hex: str) -> tuple[bool | None, str, dict]:
    import cryptography
    from app.run import reference
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    t0 = time.perf_counter()
    try:
        ok = reference.verify_mldsa65(public_key_hex, message_hex, signature_hex)
        note = ("public key is a valid ML-DSA-65 key; signature verifies as ML-DSA-65." if ok
                else "the signature does not verify as ML-DSA-65 with that public key.")
    except Exception as exc:  # a cryptography build without ML-DSA: no answer either way
        ok, note = None, f"The reference library on this computer can't check ML-DSA-65 ({exc.__class__.__name__})."
    return ok, note, {
        "title": "Independent check with a reference library",
        "command": "cryptography: MLDSA65PublicKey.from_public_bytes(public_key); public_key.verify(signature, message)",
        "output": ("OK: " if ok else "FAILED: ") + note, "started_at": started,
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "tool": "cryptography (pyca)", "tool_version": cryptography.__version__,
    }


def verify_software_claim(path: Path, claimed_name: str, claimed_version: str, claimed_algorithm: str, runner=None) -> dict:
    """Check "component NAME VERSION implements ALGORITHM".

    `runner` is the app's ComponentRunner. In isolated mode the component runs through it, in the container;
    in demo mode (or without a runner) it runs as a local process, as described below.

    1. `info`: name, version and algorithm must match the claim exactly (after normalising spelling).
    2. One ordinary keygen -> sign -> verify round trip.
    3. Independently, with the `cryptography` library: the public key must be a P-256 key and the signature
       must verify over the same message.
    This says what the component IS, not whether it is built correctly - that is what the tests are for.
    """
    if runner is not None and runner.mode.name == "isolated":
        return _isolated_claim(path, claimed_name, claimed_version, claimed_algorithm, runner)
    evidence: list[dict] = []

    def out(result: str, found: str, reason: str | None = None) -> dict:
        return {"result": result, "found": found, "reason": reason, "evidence": evidence}

    info = run_component(path, "info")
    evidence.append(_evidence(path, "Ask the component what it is (info)", info, None, []))
    if not info.ok:
        return out(COULDNT, "The component did not answer the info command.", f"The info command failed: {info.problem}.")
    verdict = _info_verdict(info.data, claimed_name, claimed_version, claimed_algorithm, out)
    if isinstance(verdict, dict):
        return verdict
    reported = verdict

    keygen = run_component(path, "keygen")
    private_key = keygen.data.get("private_key") if keygen.data else None
    secrets = [private_key] if isinstance(private_key, str) else []
    evidence.append(_evidence(path, "Make a throwaway test key (keygen)", keygen, None, secrets))
    public_key = keygen.data.get("public_key") if keygen.data else None
    if not keygen.ok or not isinstance(private_key, str) or not isinstance(public_key, str):
        return out(COULDNT, f"The component reports itself as {reported}, but could not make a test key.",
                   f"The keygen command failed: {keygen.problem or 'no key in its answer'}.")
    message = os.urandom(32).hex()
    sign_in = {"private_key": private_key, "message": message}
    sign = run_component(path, "sign", sign_in)
    evidence.append(_evidence(path, "Sign a random test message (sign)", sign, sign_in, secrets))
    signature = sign.data.get("signature") if sign.data else None
    del sign_in, private_key  # the test private key is not kept beyond this point
    if not sign.ok or not isinstance(signature, str):
        return out(COULDNT, f"The component reports itself as {reported}, but could not sign a test message.",
                   f"The sign command failed: {sign.problem or 'no signature in its answer'}.")
    verify_in = {"public_key": public_key, "message": message, "signature": signature}
    verify = run_component(path, "verify", verify_in)
    evidence.append(_evidence(path, "Check that signature with the component itself (verify)", verify, verify_in, secrets))
    if not verify.ok or not isinstance(verify.data.get("valid"), bool):
        return out(COULDNT, f"The component reports itself as {reported}, but its verify command did not answer.",
                   f"The verify command failed: {verify.problem or 'no yes/no in its answer'}.")

    return _independent_verdict(reported, public_key, message, signature, verify.data["valid"], evidence, out)


def _independent_p256_check(public_key_hex: str, message_hex: str, signature_hex: str) -> tuple[bool | None, str, dict]:
    import cryptography
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    t0 = time.perf_counter()
    ok: bool | None
    try:
        public = bytes.fromhex(public_key_hex)
        message = bytes.fromhex(message_hex)
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        ok, note = False, "the component's key, message or signature was not hex text."
    else:
        try:
            key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        except ValueError:
            ok, note = False, "the public key is not a valid P-256 key."
        else:
            try:
                key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
                ok, note = True, "public key is a valid P-256 point; signature verifies as ECDSA P-256 with SHA-256."
            except InvalidSignature:
                ok, note = False, "the signature does not verify as ECDSA P-256 with SHA-256."
    return ok, note, {
        "title": "Independent check with a reference library",
        "command": ("cryptography: EllipticCurvePublicKey.from_encoded_point(SECP256R1, public_key); "
                    "public_key.verify(signature, message, ECDSA(SHA256))"),
        "output": ("OK: " if ok else "FAILED: ") + note, "started_at": started,
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "tool": "cryptography (pyca)", "tool_version": cryptography.__version__,
    }
