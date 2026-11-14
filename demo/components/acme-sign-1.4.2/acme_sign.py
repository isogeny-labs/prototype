#!/usr/bin/env python3
"""acme-sign -- DEMO SOFTWARE. DO NOT USE FOR ANYTHING REAL.

This is fictional software shipped with the Isogeny Evidence Lab demo ("Acme Pay").
It signs and verifies with ECDSA on the P-256 curve with SHA-256 (DER signatures).

How it is called: one command word (keygen | sign | verify | info | bench) as the first
argument, a JSON object on standard input, a JSON object on standard output.
Byte strings are hex text. Keys made by `keygen` are throwaway TEST keys.
Standard library only.
"""
import hashlib
import hmac
import json
import secrets
import sys
import time

NAME = "acme-sign"
VERSION = "1.4.2"
ALGORITHM = "ECDSA P-256"

# NIST P-256 (secp256r1) domain parameters
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
G = (GX, GY)
INFINITY = None


def on_curve(pt):
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def add(p1, p2):
    if p1 is INFINITY:
        return p2
    if p2 is INFINITY:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return INFINITY
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def mul(k, pt):
    result = INFINITY
    while k > 0:
        if k & 1:
            result = add(result, pt)
        pt = add(pt, pt)
        k >>= 1
    return result


def digest_int(message):
    return int.from_bytes(hashlib.sha256(message).digest(), "big") % N


def rfc6979_k(d, message):
    """Deterministic nonce (RFC 6979, HMAC-SHA-256)."""
    h1 = hashlib.sha256(message).digest()
    x = d.to_bytes(32, "big")
    h = (int.from_bytes(h1, "big") % N).to_bytes(32, "big")
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def der_int(value):
    raw = value.to_bytes((value.bit_length() + 8) // 8 or 1, "big")
    return b"\x02" + bytes([len(raw)]) + raw


def der_encode(r, s):
    body = der_int(r) + der_int(s)
    return b"\x30" + bytes([len(body)]) + body


def der_decode(sig):
    """Strict DER: SEQUENCE { INTEGER r, INTEGER s }, short-form lengths, minimal non-negative integers."""
    def read_int(buf, pos):
        if pos + 2 > len(buf) or buf[pos] != 0x02:
            raise ValueError("bad signature encoding")
        length = buf[pos + 1]
        end = pos + 2 + length
        if length == 0 or length > 33 or end > len(buf):
            raise ValueError("bad signature encoding")
        body = buf[pos + 2:end]
        if body[0] & 0x80:
            raise ValueError("bad signature encoding")  # a negative number
        if length > 1 and body[0] == 0 and not body[1] & 0x80:
            raise ValueError("bad signature encoding")  # a needless leading zero
        return int.from_bytes(body, "big"), end

    if len(sig) < 8 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise ValueError("bad signature encoding")
    r, pos = read_int(sig, 2)
    s, pos = read_int(sig, pos)
    if pos != len(sig):
        raise ValueError("bad signature encoding")
    return r, s


def public_from_hex(text):
    raw = bytes.fromhex(text)
    if len(raw) != 65 or raw[0] != 4:
        raise ValueError("public key must be 65 bytes: 04 || X || Y")
    pt = (int.from_bytes(raw[1:33], "big"), int.from_bytes(raw[33:], "big"))
    if not on_curve(pt):
        raise ValueError("public key is not a point on P-256")
    return pt


def cmd_info(_req):
    return {"name": NAME, "version": VERSION, "algorithm": ALGORITHM, "hash": "SHA-256",
            "signature_format": "DER", "public_key_format": "uncompressed point, hex (04 || X || Y)",
            "commands": ["keygen", "sign", "verify", "info", "bench"]}


def cmd_keygen(_req):
    d = secrets.randbelow(N - 1) + 1
    x, y = mul(d, G)
    return {"private_key": d.to_bytes(32, "big").hex(),
            "public_key": (b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")).hex()}


def cmd_sign(req):
    d = int(req["private_key"], 16)
    if not 1 <= d < N:
        raise ValueError("private key out of range")
    message = bytes.fromhex(req["message"])
    e = digest_int(message)
    k = rfc6979_k(d, message)
    while True:
        r = mul(k, G)[0] % N
        s = pow(k, -1, N) * (e + r * d) % N
        if r and s:
            return {"signature": der_encode(r, s).hex()}
        k = k % (N - 1) + 1


def cmd_verify(req):
    q = public_from_hex(req["public_key"])
    message = bytes.fromhex(req["message"])
    try:
        r, s = der_decode(bytes.fromhex(req["signature"]))
    except ValueError:
        return {"valid": False}
    e = digest_int(message)
    w = pow(s, N - 2, N)
    u1 = e * w % N
    u2 = r * w % N
    pt = add(mul(u1, G), mul(u2, q))
    x = 0 if pt is INFINITY else pt[0]
    return {"valid": x % N == r}


def cmd_bench(req):
    """Sign and verify `repeats` times inside this one process and report each timing, so that
    program start-up is not counted. The private key is never part of the answer."""
    repeats = req.get("repeats", 100)
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 1000:
        raise ValueError("repeats must be a whole number from 1 to 1000")
    message = req.get("message", "")
    bytes.fromhex(message)
    keys = cmd_keygen({})
    if "private_key" in req:
        d = int(req["private_key"], 16)
        if not 1 <= d < N:
            raise ValueError("private key out of range")
        x, y = mul(d, G)
        keys = {"private_key": req["private_key"],
                "public_key": (b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")).hex()}
    sign_in = {"private_key": keys["private_key"], "message": message}
    warmups = 2
    for _ in range(warmups):
        signature = cmd_sign(sign_in)["signature"]
        cmd_verify({"public_key": keys["public_key"], "message": message, "signature": signature})
    sign_ms, verify_ms, all_verified = [], [], True
    for _ in range(repeats):
        t0 = time.perf_counter()
        signature = cmd_sign(sign_in)["signature"]
        t1 = time.perf_counter()
        valid = cmd_verify({"public_key": keys["public_key"], "message": message, "signature": signature})["valid"]
        t2 = time.perf_counter()
        sign_ms.append(round((t1 - t0) * 1000, 4))
        verify_ms.append(round((t2 - t1) * 1000, 4))
        all_verified = all_verified and valid is True
    return {"repeats": repeats, "warmups": warmups, "clock": "time.perf_counter", "sign_ms": sign_ms,
            "verify_ms": verify_ms, "signature_bytes": len(signature) // 2,
            "public_key_bytes": len(keys["public_key"]) // 2, "all_verified": all_verified}


COMMANDS = {"info": cmd_info, "keygen": cmd_keygen, "sign": cmd_sign, "verify": cmd_verify, "bench": cmd_bench}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(json.dumps({"error": "usage: acme_sign.py keygen|sign|verify|info|bench  (JSON on stdin, JSON on stdout)"}))
        return 2
    try:
        text = sys.stdin.read()
        req = json.loads(text) if text.strip() else {}
        if not isinstance(req, dict):
            raise ValueError("input must be a JSON object")
        out = COMMANDS[argv[1]](req)
    except (ValueError, KeyError, TypeError) as exc:
        # Never echo the input back: it may hold a private key.
        print(json.dumps({"error": "bad input: " + type(exc).__name__}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
