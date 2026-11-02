#!/usr/bin/env python3
"""Digital-signature library test: generation and verification correctness, malformed-input handling,
official test vectors where available, latency distributions, throughput, sizes and interpreter memory.

Params (JSON on stdin):
  adapter        {"kind": "profile", "profile": "ed25519"} | {"kind": "module", "path": "/abs/adapter.py"}
  repeat_count   verify repeats for timing (default 100)
  message_bytes  message size (default 1024)
  seed           deterministic RNG seed for messages / corruptions (default 1)

This is a library-level test. It does not validate a firmware-update protocol, a payment protocol or key management.
"""
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import environment, summarize_ms, timed, peak_alloc_kb, read_params, emit, MEMORY_DEFINITION, TIME_DEFINITION  # noqa: E402
from adapters import load_adapter  # noqa: E402
from vectors import VECTORS  # noqa: E402

FIXTURE_VERSION = "2.0.0"
TEST_ID = "signature-library-core"


def main():
    p = read_params()
    repeats = int(p.get("repeat_count", 100))
    msg_len = int(p.get("message_bytes", 1024))
    rng = random.Random(int(p.get("seed", 1)))
    failures, limitations, exclusions = [], [], []
    try:
        ad = load_adapter(p.get("adapter", {"kind": "profile", "profile": "ed25519"}))
    except Exception as e:  # noqa: BLE001
        emit({"fixture": "signature_library", "fixture_version": FIXTURE_VERSION, "status": "failed", "metrics": {}, "scenarios": [],
              "failures": [f"adapter could not be loaded: {type(e).__name__}: {e}"], "environment": environment()})
        return 2

    msg = bytes(rng.getrandbits(8) for _ in range(msg_len))
    pk, sk = ad.keygen()
    pk2, _ = ad.keygen()
    sig = ad.sign(sk, msg)
    scen = []

    def case(cid, name, expected, pk_, m, s, detail=""):
        try:
            observed = "accept" if ad.verify(pk_, m, s) else "reject"
        except Exception as e:  # noqa: BLE001
            observed = "raised"
            detail = (detail + " " + str(e)).strip()
        scen.append({"id": cid, "name": name, "expected": expected, "observed": observed, "pass": observed == expected, "detail": detail,
                     "class": "correctness" if expected == "accept" else "rejection"})

    case("valid_signature", "Valid signature over the message is accepted", "accept", pk, msg, sig)
    case("second_message", "A second valid signature over a different message is accepted", "accept", pk, msg[::-1] + b"x", ad.sign(sk, msg[::-1] + b"x"))
    m2 = bytearray(msg); m2[rng.randrange(len(m2))] ^= 0x01
    case("modified_message", "Signature over a message with one flipped bit is rejected", "reject", pk, bytes(m2), sig)
    case("wrong_key", "Signature verified under a different public key is rejected", "reject", pk2, msg, sig)
    case("random_signature", "Random bytes of the correct length are rejected", "reject", pk, msg, bytes(rng.getrandbits(8) for _ in range(len(sig))))
    case("corrupted_signature", "Signature with one flipped bit is rejected", "reject", pk, msg, bytes([sig[0] ^ 0x80]) + sig[1:])
    case("truncated_signature", "Signature missing its last byte is rejected", "reject", pk, msg, sig[:-1])
    case("trailing_byte", "Signature with one appended byte is rejected", "reject", pk, msg, sig + b"\x00")
    case("trailing_garbage", "Signature with 16 appended random bytes is rejected", "reject", pk, msg, sig + bytes(rng.getrandbits(8) for _ in range(16)))
    case("empty_signature", "Empty signature is rejected", "reject", pk, msg, b"")
    case("zero_signature", "All-zero signature is rejected", "reject", pk, msg, b"\x00" * len(sig))
    case("empty_message_wrong_sig", "Signature over the message does not verify the empty message", "reject", pk, b"", sig)

    # official test vectors
    vec_status = "unsupported"
    vectors = VECTORS.get(ad.algorithm) or VECTORS.get(getattr(ad, "name", ""))
    if vectors:
        try:
            ok_all = True
            for v in vectors:
                vpk = ad.public_key_from_bytes(bytes.fromhex(v["pk"]))
                vsk = ad.private_key_from_bytes(bytes.fromhex(v["sk"]))
                vm, vs = bytes.fromhex(v["msg"]), bytes.fromhex(v["sig"])
                acc = ad.verify(vpk, vm, vs)
                produced = ad.sign(vsk, vm) == vs
                derived = ad.public_key_bytes(vsk.public_key() if hasattr(vsk, "public_key") else ad.keygen()[0]) == bytes.fromhex(v["pk"]) if hasattr(vsk, "public_key") else None
                ok = bool(acc and produced)
                ok_all &= ok
                scen.append({"id": "official_vector", "name": f"Official test vector ({v['source']}) verifies and reproduces",
                             "expected": "accept", "observed": "accept" if ok else "reject", "pass": ok, "class": "vector",
                             "detail": f"verify={acc} sign_reproduces={produced} pubkey_derivation={derived}"})
            vec_status = "pass" if ok_all else "fail"
        except NotImplementedError as e:
            vec_status = "unsupported"
            exclusions.append(f"official vectors not checked: adapter lacks raw-key loading ({e})")
    else:
        exclusions.append(f"no official test vectors bundled for algorithm '{ad.algorithm}'")

    # timing
    ad.verify(pk, msg, sig)
    verify_ms = timed(lambda: ad.verify(pk, msg, sig), repeats)
    sign_ms = timed(lambda: ad.sign(sk, msg), max(5, repeats // 4))
    peak = peak_alloc_kb(lambda: ad.verify(pk, msg, sig))
    vs, ss = summarize_ms(verify_ms), summarize_ms(sign_ms)
    pkb = ad.public_key_bytes(pk)
    rejection = [s for s in scen if s["class"] == "rejection"]
    metrics = {
        "verify_time_ms_median": vs["median"], "verify_time_ms_p95": vs["p95"], "verify_time_ms_max": vs["max"],
        "sign_time_ms_median": ss["median"], "sign_time_ms_p95": ss["p95"],
        "verify_throughput_per_s": 1000.0 / vs["mean"], "sign_throughput_per_s": 1000.0 / ss["mean"],
        "signature_bytes": len(sig), "public_key_bytes": len(pkb), "message_bytes": msg_len,
        "verify_peak_alloc_kb": round(peak, 2),
        "scenario_pass_count": sum(1 for s in scen if s["pass"]), "scenario_total": len(scen),
        "rejection_scenarios_all_pass": 1 if all(s["pass"] for s in rejection) else 0,
        "rejection_scenarios_failed": sum(1 for s in rejection if not s["pass"]),
        "functional_pass": 1 if all(s["pass"] for s in scen) else 0,
        "official_vectors": vec_status,
    }
    if getattr(ad, "production_grade", None) is False:
        limitations.append(f"{ad.name}: {ad.notes}")
    if ad.kind == "module":
        limitations.append(ad.notes)
    limitations += [
        "Library-level test with synthetic keys and messages generated in the fixture; no production keys or protocol context.",
        "Host-interpreter timing and memory; not the customer's production hardware unless the customer-side runner was used there.",
        "Passing every scenario shows these specific inputs were handled as expected; it is not proof of security.",
    ]
    emit({
        "fixture": "signature_library", "fixture_version": FIXTURE_VERSION, "test_id": TEST_ID, "status": "completed",
        "adapter": {"kind": ad.kind, "name": ad.name, "version": ad.version, "algorithm": ad.algorithm, "library": ad.library},
        "environment": environment(), "repeat_count": repeats,
        "parameters": {"message_bytes": msg_len, "seed": p.get("seed", 1), "repeat_count": repeats},
        "scenarios": scen, "metrics": metrics,
        "metric_definitions": {
            "verify_time_ms_*": TIME_DEFINITION + " One verify() call of the adapter.", "sign_time_ms_*": TIME_DEFINITION + " One sign() call.",
            "verify_peak_alloc_kb": MEMORY_DEFINITION, "verify_throughput_per_s": "1000 / mean verify ms (single thread).",
            "signature_bytes": "Length of the signature returned by the adapter.", "public_key_bytes": "Length of the adapter's encoded public key.",
            "official_vectors": "pass | fail | unsupported (no bundled vector or adapter cannot load raw keys)."},
        "raw": {"verify_times_ms": verify_ms, "sign_times_ms": sign_ms, "verify_stats": vs, "sign_stats": ss,
                "message_sha256": hashlib.sha256(msg).hexdigest(), "signature_sha256": hashlib.sha256(sig).hexdigest()},
        "failures": failures, "exclusions": exclusions, "limitations": limitations,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
