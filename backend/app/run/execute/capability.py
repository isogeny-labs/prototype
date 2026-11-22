"""Phase 4d: the post-quantum capability check of one library version, run on its target (the public pinned copy).

Raw outcomes only: what each copy answered, word for word, and whether the reference library agreed. The separate
reviewer (engine/reviewer.py, `_capability`) is the only place that turns this into an answer. Every question is
asked of the library under test and of the two control copies (real_libraries.CAPABLE_CONTROL and
INCAPABLE_CONTROL). No key, secret or signature is kept: the harness withholds private keys and only fingerprints
of secrets are compared.

Outcome of one question for one copy:
  {"state": "made", "confirmed": true | false, ...}   it did it, and whether the reference library agreed
  {"state": "refused", "note": "<the library's own words>"}   the library itself said it does not have it
  {"state": "no_answer", "why": "<what went wrong>"}           anything else: a crash, a time-out, no copy, no server
"""
from __future__ import annotations

import hashlib
import os
from contextlib import ExitStack

from app import real_libraries
from app.dependencies.target import PublicCopy
from app.names import clean_text
from app.run.execute import RunContext, problem

ALGORITHMS = {"ml_kem_768": "ML-KEM-768", "ml_dsa_65": "ML-DSA-65"}
HYBRID_GROUP, CLASSICAL_GROUP = "X25519MLKEM768", "X25519"
TIME_LIMIT = 60


def _short(value: object, limit: int = 200) -> str:
    return clean_text(str(value), limit)


def _keygen(target, algorithm: str) -> tuple[dict | None, dict]:
    """Ask the library for a key pair of this algorithm. (None, outcome) when it refused or did not answer."""
    batch = target.run_job({"op": "call", "command": "keygen", "input": {"algorithm": algorithm}}, TIME_LIMIT)
    line = batch.lines[0] if batch.lines else None
    step = {"title": f"Ask the library for an {algorithm} key pair", "command": batch.command, "started_at": batch.started_at,
            "duration_ms": batch.duration_ms}
    if not batch.ok or line is None:
        return None, {"state": "no_answer", "why": _short(batch.problem or "no answer"), "steps": [step]}
    out = line.get("out")
    if line.get("error"):
        return None, {"state": "no_answer", "why": _short(line["error"]), "steps": [step]}
    if isinstance(out, dict) and out.get("refused") is True:
        step["output"] = {"refused": True, "note": _short(out.get("note") or "no reason given", 300)}
        return None, {"state": "refused", "note": _short(out.get("note") or "no reason given", 300), "steps": [step]}
    if isinstance(out, dict) and out.get("error"):
        return None, {"state": "no_answer", "why": _short(out["error"]), "steps": [step]}
    if not (isinstance(out, dict) and isinstance(out.get("public_key"), str) and out["public_key"]):
        return None, {"state": "no_answer", "why": "the answer held no key", "steps": [step]}
    step["output"] = {"public_key_bytes": len(out["public_key"]) // 2, "private_key": "[test private key withheld]"}
    return out, {"steps": [step]}


def _kem(target) -> dict:
    key, outcome = _keygen(target, "ML-KEM-768")
    if key is None:
        return outcome
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import mlkem
    ours = mlkem.MLKEM768PrivateKey.generate()   # the app's own throwaway test key; it never leaves this function
    peer = ours.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    batch = target.run_job({"op": "kem_roundtrip", "algorithm": "ML-KEM-768", "peer_public_key": peer}, 3 * TIME_LIMIT)
    steps = {line.get("step"): line for line in batch.lines}
    outcome["steps"].append({"title": "One key exchange: key pair, encapsulate, decapsulate, and a message for the app",
                             "command": batch.command, "started_at": batch.started_at, "duration_ms": batch.duration_ms,
                             "output": {s: (one.get("error") or "ok") for s, one in steps.items()}})
    for step in ("keygen", "encaps", "decaps", "encaps_to_app"):
        line = steps.get(step)
        if line is None or line.get("error") or not isinstance(line.get("out"), dict):
            why = (line or {}).get("error") or batch.problem or "no answer"
            if isinstance(why, str) and why.startswith("the library refused"):
                return {**outcome, "state": "refused", "note": _short(why, 300)}
            return {**outcome, "state": "no_answer", "why": f"the {step} step: {_short(why)}"}
    made = steps["encaps_to_app"]["out"]
    try:
        same = hashlib.sha256(ours.decapsulate(bytes.fromhex(str(made.get("ciphertext"))))).hexdigest() == made.get("shared_secret_sha256")
    except (ValueError, TypeError):
        same = False
    both = steps["decaps"]["out"].get("same_secret") is True
    outcome["steps"].append({"title": "Reference library (cryptography) decapsulates the library's message to the app",
                             "output": "same shared secret" if same else "not the same shared secret"})
    return {**outcome, "state": "made", "confirmed": bool(same and both), "same_secret_inside": both, "reference_agrees": same}


def _dsa(target) -> dict:
    key, outcome = _keygen(target, "ML-DSA-65")
    if key is None:
        return outcome
    message = os.urandom(32).hex()
    batch = target.run_job({"op": "roundtrip", "algorithm": "ML-DSA-65", "message": message}, 3 * TIME_LIMIT)
    steps = {line.get("step"): line for line in batch.lines}
    outcome["steps"].append({"title": "One signature: key pair, sign, verify", "command": batch.command,
                             "started_at": batch.started_at, "duration_ms": batch.duration_ms,
                             "output": {s: (one.get("error") or "ok") for s, one in steps.items()}})
    for step in ("keygen", "sign", "verify"):
        line = steps.get(step)
        if line is None or line.get("error") or not isinstance(line.get("out"), dict):
            why = (line or {}).get("error") or batch.problem or "no answer"
            return {**outcome, "state": "no_answer", "why": f"the {step} step: {_short(why)}"}
    public, signature = steps["keygen"]["out"].get("public_key"), steps["sign"]["out"].get("signature")
    own = steps["verify"]["out"].get("valid") is True
    from app.run import reference
    try:
        agrees = bool(reference.verify_mldsa65(str(public), message, str(signature)))
    except Exception as exc:  # a reference library without ML-DSA: no answer either way
        return {**outcome, "state": "no_answer", "why": f"the reference library can't check ML-DSA-65 here ({exc.__class__.__name__})"}
    outcome["steps"].append({"title": "Reference library (cryptography) checks the same signature",
                             "output": "the signature verifies as ML-DSA-65" if agrees else "the signature does not verify as ML-DSA-65"})
    return {**outcome, "state": "made", "confirmed": bool(own and agrees), "own_check": own, "reference_agrees": agrees}


def _tls(target, ports: dict | None, why_no_server: str | None) -> dict:
    if ports is None:
        return {"state": "no_answer", "why": why_no_server or "the test server could not be started"}
    hybrid = target.tls_client(ports["hybrid"], HYBRID_GROUP)
    classical = target.tls_client(ports["classical"], CLASSICAL_GROUP)
    if hybrid is None or classical is None:
        return {"state": "no_answer", "why": "this copy has no TLS client to measure with"}
    classical_done = classical["exit"] == 0 and "CONNECTION ESTABLISHED" in classical["output"]
    text = hybrid["output"]
    refusal = next((line.strip() for line in text.splitlines() if "cannot be set" in line or "SSL_CONF_cmd(-groups" in line), None)
    group_line = next((line.strip() for line in text.splitlines() if "Negotiated TLS1.3 group" in line), None)
    out = {"hybrid": {"command": hybrid["command"], "exit": hybrid["exit"], "output": text[-1500:]},
           "classical": {"command": classical["command"], "exit": classical["exit"], "output": classical["output"][-800:],
                         "completed": classical_done}}
    if refusal is not None:
        return {"state": "refused", "note": _short(refusal, 300), "handshakes": out}
    if hybrid["exit"] == 0 and "CONNECTION ESTABLISHED" in text:
        # the test server accepts only X25519MLKEM768, so a completed handshake with it used that group
        return {"state": "made", "confirmed": True, "group_line": group_line, "classical_completed": classical_done, "handshakes": out}
    return {"state": "no_answer", "why": "the handshake neither completed nor was refused by the library", "handshakes": out}


def _ask(target, questions: list[str], ports: dict | None, why_no_server: str | None) -> dict:
    asked = {}
    for q in questions:
        if q == "ml_kem_768":
            asked[q] = _kem(target)
        elif q == "ml_dsa_65":
            asked[q] = _dsa(target)
        elif q == "x25519mlkem768":
            asked[q] = _tls(target, ports, why_no_server)
    return asked


def run_capability(spec: dict, ctx: RunContext) -> dict:
    target_spec = spec["target"]
    questions = list(spec["inputs"]["questions"])
    if ctx.mode.name != "isolated":
        return problem("needs_isolated_mode", real_libraries.NEEDS_ISOLATED + ", and this run is in demo mode.")
    if target_spec.get("target_kind") != "public_copy":
        return problem("harness_error", "Only the public pinned copy can be measured in this version.")
    copies = {"subject": (target_spec["name"], target_spec["version"]), "capable": real_libraries.CAPABLE_CONTROL,
              "incapable": real_libraries.INCAPABLE_CONTROL}
    targets = {}
    for role, (name, version) in copies.items():
        try:
            targets[role] = PublicCopy(name, version, ctx.runner)
        except ValueError:
            return problem("harness_error", f"{name} {version} has no pinned copy.")
        if not (ctx.mode.real_images or {}).get(targets[role].family):
            return problem("real_image_missing", f"The container image of {targets[role].copy['label']} is not prepared on this computer.")
    raw: dict = {"target": targets["subject"].describe(), "questions": questions}
    with ExitStack() as stack:
        ports, why = None, None
        if "x25519mlkem768" in questions:
            from app.checks import pqtls
            ok, text = pqtls.available()
            if ok:
                try:
                    ports = stack.enter_context(pqtls.control_servers())
                except Exception as exc:
                    why = f"the app's own test server could not be started ({exc.__class__.__name__})"
            else:
                why = text
        ctx.progress("asking the library", 10)
        raw["subject"] = _ask(targets["subject"], questions, ports, why)
        ctx.progress("asking the two control copies", 60)
        raw["controls"] = {"capable": {"copy": targets["capable"].describe(), "answers": _ask(targets["capable"], questions, ports, why)},
                           "incapable": {"copy": targets["incapable"].describe(), "answers": _ask(targets["incapable"], questions, ports, why)}}
    return raw
