#!/usr/bin/env python3
"""control-pq -- DELIBERATELY BROKEN CONTROLS. DO NOT USE FOR ANYTHING REAL.

Part of the Isogeny Evidence Lab. The two post-quantum exams also run these broken copies of the OpenSSL
wrapper next door (openssl_adapter.py). Each breaks one step on purpose, and the exam must catch it:
if a control "passes", the test run can't be trusted. The crypto is still OpenSSL's; only the fault is ours.

    python pq_controls.py wrong-answer|skip-key-check keygen|sign|encaps|decaps

wrong-answer     Every answer (a key, a signature, a ciphertext, a shared secret) has its last byte changed.
skip-key-check   Skips two checks that FIPS 203 requires before a key is used:
                 - encaps: a public key holding a number that is too large must be refused. This copy quietly
                   brings each number back into range and carries on.
                 - decaps: a private key carries a fingerprint (hash) of its public half, and a key whose
                   fingerprint is wrong must be refused. This copy quietly puts the right fingerprint back.
"""
import hashlib
import importlib.util
import json
import os
import sys

MODES = ("wrong-answer", "skip-key-check")
USAGE = "usage: pq_controls.py wrong-answer|skip-key-check keygen|sign|encaps|decaps  (JSON on stdin, JSON on stdout)"
Q = 3329            # ML-KEM's modulus: every number in a public key must be below it
PUBLIC_NUMBERS = 768   # an ML-KEM-768 public key is 768 twelve-bit numbers (1152 bytes), then a 32-byte seed
DK_PARTS = (1152, 1184, 32, 32)   # an expanded ML-KEM-768 private key: secret numbers, public key, its hash, a secret value


def repair_public_key(hex_text):
    raw = bytes.fromhex(hex_text)
    if len(raw) != 1184:
        return hex_text
    packed, fixed = int.from_bytes(raw[:1152], "little"), 0
    for i in range(PUBLIC_NUMBERS):
        fixed |= (((packed >> (12 * i)) & 0xFFF) % Q) << (12 * i)
    return (fixed.to_bytes(1152, "little") + raw[1152:]).hex()


def repair_private_key(hex_text):
    raw = bytes.fromhex(hex_text)
    if len(raw) != sum(DK_PARTS):
        return hex_text
    public = raw[1152:1152 + 1184]
    return (raw[:1152] + public + hashlib.sha3_256(public).digest() + raw[-32:]).hex()


def spoil(answer):
    """Change the last byte of every hex answer."""
    out = dict(answer)
    for name, value in answer.items():
        if name in ("public_key", "private_key", "signature", "ciphertext", "shared_secret") and isinstance(value, str) and value:
            out[name] = value[:-2] + format(int(value[-2:], 16) ^ 0x01, "02x")
    return out


def main(argv):
    if len(argv) != 3 or argv[1] not in MODES or argv[2] not in ("keygen", "sign", "encaps", "decaps"):
        print(json.dumps({"error": USAGE}))
        return 2
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("openssl_adapter", os.path.join(here, "openssl_adapter.py"))
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    mode, command = argv[1], argv[2]
    try:
        text = sys.stdin.read()
        req = json.loads(text) if text.strip() else {}
        if mode == "skip-key-check" and command == "encaps":
            req = {**req, "public_key": repair_public_key(req["public_key"])}
        if mode == "skip-key-check" and command == "decaps":
            req = {**req, "private_key": repair_private_key(req["private_key"])}
        out = real.HANDLERS[command](req)
        if mode == "wrong-answer":
            out = spoil(out)
    except real.Refused as refusal:
        print(json.dumps({"refused": True, "note": str(refusal)[:120]}))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"error": "bad input: " + exc.__class__.__name__}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
