#!/usr/bin/env python3
"""Adapter wrapper for python-ecdsa (the library folder is the first argument; it holds the unpacked wheel).

It only translates the adapter's JSON to python-ecdsa's own calls and back. Every key, signature and check is
made by the library (ecdsa.SigningKey / VerifyingKey, NIST256p, SHA-256, DER signatures). No crypto of our own.

    python ecdsa_adapter.py <library folder> [--slow] keygen|sign|verify|info|bench   (JSON on stdin, JSON on stdout)

How a "no" is reported: any error the library raises while checking a signature means "not accepted":
{"valid": false}. The library's own "bad signature" errors add no note; any other error adds
"general error: <ClassName>" (that is how a crash is recorded without being counted as an answer).
--slow is the speed test's control: it adds 6 ms to every timed step of bench.
"""
import json
import sys
import time

LIBRARY_DIR = sys.argv[1] if len(sys.argv) > 1 else ""
sys.path.insert(0, LIBRARY_DIR)
import ecdsa                                                        # noqa: E402
from ecdsa import NIST256p, SigningKey, VerifyingKey               # noqa: E402
from ecdsa.util import sigdecode_der, sigencode_der                # noqa: E402
from hashlib import sha256                                         # noqa: E402

COMMANDS = ("keygen", "sign", "verify", "info", "bench")
USAGE = "usage: ecdsa_adapter.py <library folder> [--slow] " + "|".join(COMMANDS) + "  (JSON on stdin, JSON on stdout)"
SLOW_MS = 6.0
# The library's own "bad or malformed signature" errors (MalformedSignature does not exist in 0.13.2).
OWN_ERRORS = tuple(e for e in (ecdsa.BadSignatureError, ecdsa.der.UnexpectedDER, getattr(ecdsa.util, "MalformedSignature", None)) if e)


def make_keys(scalar=None):
    key = SigningKey.from_string(scalar, curve=NIST256p, hashfunc=sha256) if scalar else SigningKey.generate(curve=NIST256p, hashfunc=sha256)
    return key, key.get_verifying_key()


def public_hex(public):
    return (b"\x04" + public.to_string()).hex()


def cmd_info(_req):
    python = ".".join(map(str, sys.version_info[:3]))
    return {"name": "python-ecdsa", "version": ecdsa.__version__, "algorithm": "ECDSA P-256", "hash": "SHA-256",
            "signature_format": "DER", "public_key_format": "uncompressed point, hex (04 || X || Y)",
            "commands": list(COMMANDS), "library": f"python-ecdsa {ecdsa.__version__} on Python {python}"}


def cmd_keygen(req):
    algorithm = req.get("algorithm", "ECDSA P-256")
    if algorithm != "ECDSA P-256":
        # Phase 4d: asked for another algorithm, answer from the library's own list of the curves it offers.
        offered = sorted(c.name for c in ecdsa.curves.curves)
        if algorithm not in offered:
            return {"refused": True, "note": "not in the library's own list of curves: " + ", ".join(offered)}
        return {"error": "bad input: this wrapper only makes ECDSA P-256 keys"}
    key, public = make_keys()
    return {"private_key": key.to_string().hex(), "public_key": public_hex(public)}


def cmd_sign(req):
    key, _ = make_keys(bytes.fromhex(req["private_key"]))
    return {"signature": key.sign(bytes.fromhex(req["message"]), sigencode=sigencode_der).hex()}


def cmd_verify(req):
    point, message, signature = (bytes.fromhex(req[f]) for f in ("public_key", "message", "signature"))
    try:
        public = VerifyingKey.from_string(point[1:], curve=NIST256p, hashfunc=sha256)
        if point[:1] != b"\x04":
            raise ValueError("not an uncompressed point")
    except Exception:
        return {"valid": False, "note": "the library refused the public key"}
    try:
        return {"valid": bool(public.verify(signature, message, sigdecode=sigdecode_der))}
    except OWN_ERRORS:
        return {"valid": False}
    except Exception as exc:  # a crash inside the library: not an answer, recorded as a note
        return {"valid": False, "note": "general error: " + type(exc).__name__}


def wait(ms):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:  # busy-wait: steadier than sleep for a few milliseconds
        pass


def cmd_bench(req, slow=False):
    repeats = req.get("repeats", 100)
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 1000:
        raise ValueError("repeats must be 1 to 1000")
    message = bytes.fromhex(req.get("message", ""))
    key, public = make_keys(bytes.fromhex(req["private_key"]) if req.get("private_key") else None)
    for _ in range(2):  # warm-up, not timed
        public.verify(key.sign(message, sigencode=sigencode_der), message, sigdecode=sigdecode_der)
    sign_ms, verify_ms, all_verified, signature = [], [], True, b""
    for _ in range(repeats):
        t0 = time.perf_counter()
        if slow:
            wait(SLOW_MS)
        signature = key.sign(message, sigencode=sigencode_der)
        t1 = time.perf_counter()
        if slow:
            wait(SLOW_MS)
        ok = public.verify(signature, message, sigdecode=sigdecode_der)
        t2 = time.perf_counter()
        all_verified = all_verified and ok is True
        sign_ms.append(round((t1 - t0) * 1000, 4))
        verify_ms.append(round((t2 - t1) * 1000, 4))
    return {"repeats": repeats, "warmups": 2, "clock": "time.perf_counter", "sign_ms": sign_ms, "verify_ms": verify_ms,
            "signature_bytes": len(signature), "public_key_bytes": 65, "all_verified": all_verified}


HANDLERS = {"keygen": cmd_keygen, "sign": cmd_sign, "verify": cmd_verify, "info": cmd_info}


def main(argv):
    words = argv[2:]
    slow = words[:1] == ["--slow"]
    words = words[1:] if slow else words
    if len(words) != 1 or words[0] not in COMMANDS:
        print(json.dumps({"error": USAGE}))
        return 2
    try:
        text = sys.stdin.read()
        req = json.loads(text) if text.strip() else {}
        if not isinstance(req, dict):
            raise ValueError("input must be a JSON object")
        out = cmd_bench(req, slow) if words[0] == "bench" else HANDLERS[words[0]](req)
    except Exception as exc:
        # Never repeat the input here: it may hold a test private key.
        print(json.dumps({"error": "bad input: " + type(exc).__name__}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
