#!/usr/bin/env python3
"""ALLOWLISTED EXPERIMENT: characterise which malformed signature encodings an adapter accepts.

Sweeps signature lengths and corruption patterns around a valid signature and records which are accepted.
A correct verifier accepts exactly the unmodified signature. Params: adapter, lengths (default 0..130 step 1 plus
larger), variants, seed. Output metrics: accepted_count, accepted_variants, total_cases.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import environment, read_params, emit  # noqa: E402
from adapters import load_adapter  # noqa: E402

FIXTURE_VERSION = "1.0.0"
TEST_ID = "malformed-input-sweep"


def main():
    p = read_params()
    rng = random.Random(int(p.get("seed", 3)))
    try:
        ad = load_adapter(p.get("adapter", {"kind": "profile", "profile": "ed25519"}))
    except Exception as e:  # noqa: BLE001
        emit({"fixture": "malformed_input_sweep", "fixture_version": FIXTURE_VERSION, "status": "failed", "metrics": {}, "scenarios": [],
              "failures": [f"adapter could not be loaded: {type(e).__name__}: {e}"], "environment": environment()})
        return 2
    msg = bytes(rng.getrandbits(8) for _ in range(256))
    pk, sk = ad.keygen()
    sig = ad.sign(sk, msg)
    n = len(sig)
    max_extra = int(p.get("max_extra_bytes", 64))
    cases = []
    for k in range(1, max_extra + 1):
        cases.append((f"append_zero_{k}", "append", k, sig + b"\x00" * k))
        cases.append((f"append_random_{k}", "append_random", k, sig + bytes(rng.getrandbits(8) for _ in range(k))))
    for k in range(1, min(n, 8) + 1):
        cases.append((f"truncate_{k}", "truncate", k, sig[:n - k]))
        cases.append((f"prefix_zero_{k}", "prefix", k, b"\x00" * k + sig))
    cases.append(("empty", "empty", n, b""))
    results, accepted = [], []
    for cid, variant, k, s in cases:
        try:
            acc = ad.verify(pk, msg, s)
            obs = "accept" if acc else "reject"
        except Exception as e:  # noqa: BLE001
            obs = "raised"
        results.append({"id": cid, "variant": variant, "k": k, "len": len(s), "observed": obs})
        if obs == "accept":
            accepted.append(cid)
    by_variant = {}
    for r in results:
        d = by_variant.setdefault(r["variant"], {"total": 0, "accepted": 0})
        d["total"] += 1
        d["accepted"] += r["observed"] == "accept"
    scen = [{"id": f"variant_{v}", "name": f"All '{v}' malformations rejected ({d['accepted']}/{d['total']} accepted)", "expected": "reject",
             "observed": "reject" if d["accepted"] == 0 else "accept", "pass": d["accepted"] == 0, "class": "rejection"} for v, d in by_variant.items()]
    emit({
        "fixture": "malformed_input_sweep", "fixture_version": FIXTURE_VERSION, "test_id": TEST_ID, "status": "completed",
        "adapter": {"kind": ad.kind, "name": ad.name, "version": ad.version, "algorithm": ad.algorithm, "library": ad.library},
        "environment": environment(), "repeat_count": 1,
        "parameters": {"seed": p.get("seed", 3), "max_extra_bytes": max_extra, "signature_bytes": n},
        "scenarios": scen,
        "metrics": {"total_cases": len(results), "accepted_count": len(accepted), "accepted_fraction": len(accepted) / len(results),
                    "by_variant": by_variant, "functional_pass": 1 if not accepted else 0, "rejection_scenarios_all_pass": 1 if not accepted else 0},
        "metric_definitions": {"accepted_count": "Number of malformed signature encodings the adapter's verify() returned True for.",
                               "by_variant": "Accepted/total per malformation class (append, append_random, truncate, prefix, empty)."},
        "raw": {"cases": results, "accepted": accepted},
        "failures": [], "exclusions": [],
        "limitations": ["Characterises encoding handling only; says nothing about the mathematical security of the scheme.",
                        "Synthetic keys and messages; one key pair; deterministic seed."],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
