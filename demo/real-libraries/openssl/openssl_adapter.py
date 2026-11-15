#!/usr/bin/env python3
"""Adapter wrapper for OpenSSL (the library that comes with this container image).

It only translates. Every key, signature, ciphertext and shared secret is made or checked by OpenSSL's own
library (libcrypto), called directly through its public EVP functions. There is no crypto in this file.

    python openssl_adapter.py [--slow] keygen|sign|verify|info|bench|encaps|decaps
    (one JSON object on standard input, one JSON object on standard output; see docs/ADAPTER.md)

Algorithms (the "algorithm" field of the input; ECDSA P-256 when it is left out):
    ECDSA P-256   sign, verify      SHA-256, DER signatures, public key 04 || X || Y, private key 32 bytes
    ML-DSA-65     sign, verify      FIPS 204; private key: the 32-byte seed or the 4032-byte expanded key
    ML-KEM-768    encaps, decaps    FIPS 203; private key: the 64-byte seed or the 2400-byte expanded key

How a "no" is reported: when OpenSSL refuses an input (a bad key, a wrong length) the answer is
{"refused": true, "note": "<OpenSSL's reason>"}, and verify answers {"valid": false}. {"error": ...} is only
for a mistake in the call itself. --slow is the speed test's control: it adds 6 ms to every timed step of bench.
"""
import ctypes
import json
import sys
import time
from ctypes import POINTER, byref, c_char_p, c_int, c_size_t, c_ulong, c_void_p, create_string_buffer

NAME = "openssl"
ALGORITHMS = ("ECDSA P-256", "ML-DSA-65", "ML-KEM-768")
COMMANDS = ("keygen", "sign", "verify", "info", "bench", "encaps", "decaps")
USAGE = "usage: openssl_adapter.py [--slow] " + "|".join(COMMANDS) + "  (JSON on stdin, JSON on stdout)"
SLOW_MS = 6.0
# What ECDSA P-256 keys look like on the wire for OpenSSL (standard DER wrappers; the key bytes follow).
P256_PUBLIC_DER = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")
P256_PRIVATE_DER = bytes.fromhex("3041020100301306072a8648ce3d020106082a8648ce3d03010704273025020101" "0420")

C = ctypes.CDLL("libcrypto.so.3")
for _name, _result, _arguments in [
    ("OpenSSL_version", c_char_p, [c_int]),
    ("ERR_peek_last_error", c_ulong, []), ("ERR_reason_error_string", c_char_p, [c_ulong]), ("ERR_clear_error", None, []),
    ("d2i_PUBKEY", c_void_p, [c_void_p, POINTER(c_char_p), ctypes.c_long]),
    ("d2i_AutoPrivateKey", c_void_p, [c_void_p, POINTER(c_char_p), ctypes.c_long]),
    ("EVP_PKEY_new_raw_public_key_ex", c_void_p, [c_void_p, c_char_p, c_char_p, c_char_p, c_size_t]),
    ("EVP_PKEY_new_raw_private_key_ex", c_void_p, [c_void_p, c_char_p, c_char_p, c_char_p, c_size_t]),
    ("EVP_PKEY_get_raw_public_key", c_int, [c_void_p, c_char_p, POINTER(c_size_t)]),
    ("EVP_PKEY_get_raw_private_key", c_int, [c_void_p, c_char_p, POINTER(c_size_t)]),
    ("EVP_PKEY_get_octet_string_param", c_int, [c_void_p, c_char_p, c_char_p, c_size_t, POINTER(c_size_t)]),
    ("EVP_PKEY_get_bn_param", c_int, [c_void_p, c_char_p, POINTER(c_void_p)]),
    ("BN_bn2binpad", c_int, [c_void_p, c_char_p, c_int]), ("BN_clear_free", None, [c_void_p]),
    ("EVP_PKEY_free", None, [c_void_p]),
    ("EVP_PKEY_CTX_new_from_name", c_void_p, [c_void_p, c_char_p, c_char_p]),
    ("EVP_PKEY_CTX_new_from_pkey", c_void_p, [c_void_p, c_void_p, c_char_p]),
    ("EVP_PKEY_CTX_free", None, [c_void_p]),
    ("EVP_PKEY_CTX_ctrl_str", c_int, [c_void_p, c_char_p, c_char_p]),
    ("EVP_PKEY_keygen_init", c_int, [c_void_p]), ("EVP_PKEY_generate", c_int, [c_void_p, POINTER(c_void_p)]),
    ("EVP_MD_CTX_new", c_void_p, []), ("EVP_MD_CTX_free", None, [c_void_p]),
    ("EVP_DigestSignInit_ex", c_int, [c_void_p, POINTER(c_void_p), c_char_p, c_void_p, c_char_p, c_void_p, c_void_p]),
    ("EVP_DigestSign", c_int, [c_void_p, c_char_p, POINTER(c_size_t), c_char_p, c_size_t]),
    ("EVP_DigestVerifyInit_ex", c_int, [c_void_p, POINTER(c_void_p), c_char_p, c_void_p, c_char_p, c_void_p, c_void_p]),
    ("EVP_DigestVerify", c_int, [c_void_p, c_char_p, c_size_t, c_char_p, c_size_t]),
    ("EVP_PKEY_encapsulate_init", c_int, [c_void_p, c_void_p]),
    ("EVP_PKEY_encapsulate", c_int, [c_void_p, c_char_p, POINTER(c_size_t), c_char_p, POINTER(c_size_t)]),
    ("EVP_PKEY_decapsulate_init", c_int, [c_void_p, c_void_p]),
    ("EVP_PKEY_decapsulate", c_int, [c_void_p, c_char_p, POINTER(c_size_t), c_char_p, c_size_t]),
]:
    _function = getattr(C, _name)
    _function.restype, _function.argtypes = _result, _arguments


class Refused(Exception):
    """OpenSSL itself said no to an input. Carries OpenSSL's own reason."""


def refuse(what):
    code = C.ERR_peek_last_error()
    reason = C.ERR_reason_error_string(code) if code else None
    C.ERR_clear_error()
    raise Refused(what + (": " + reason.decode("ascii", "replace") if reason else ""))


def must(ok, what):
    if not ok:
        refuse(what)


# ---------------------------------------------------------------- keys in, keys out

def from_der(der, private):
    pointer = c_char_p(der)
    return (C.d2i_AutoPrivateKey if private else C.d2i_PUBKEY)(None, byref(pointer), len(der))


def public_key(algorithm, raw):
    key = from_der(P256_PUBLIC_DER + raw, False) if algorithm == "ECDSA P-256" else \
        C.EVP_PKEY_new_raw_public_key_ex(None, algorithm.encode(), None, raw, len(raw))
    must(key, "OpenSSL did not accept the public key")
    return key


def private_key(algorithm, raw):
    if algorithm == "ECDSA P-256":
        key = from_der(P256_PRIVATE_DER + raw, True)
    elif len(raw) == (32 if algorithm == "ML-DSA-65" else 64):       # the seed form
        return generate(algorithm, [(b"hexseed", raw.hex().encode())])
    else:                                                             # the expanded form; OpenSSL checks its length
        key = C.EVP_PKEY_new_raw_private_key_ex(None, algorithm.encode(), None, raw, len(raw))
    must(key, "OpenSSL did not accept the private key")
    return key


def generate(algorithm, options=()):
    ctx = C.EVP_PKEY_CTX_new_from_name(None, b"EC" if algorithm == "ECDSA P-256" else algorithm.encode(), None)
    must(ctx and C.EVP_PKEY_keygen_init(ctx) == 1, "OpenSSL could not start key generation")
    if algorithm == "ECDSA P-256":
        options = [(b"ec_paramgen_curve", b"P-256")]
    key = c_void_p()
    ok = all(C.EVP_PKEY_CTX_ctrl_str(ctx, name, value) == 1 for name, value in options) and C.EVP_PKEY_generate(ctx, byref(key)) == 1
    C.EVP_PKEY_CTX_free(ctx)
    must(ok, "OpenSSL could not make the key")
    return key


def export(algorithm, key):
    """(public key bytes, private key bytes) of a key pair, in the forms described at the top of this file."""
    size, out = c_size_t(8192), create_string_buffer(8192)
    if algorithm == "ECDSA P-256":
        must(C.EVP_PKEY_get_octet_string_param(key, b"pub", out, 8192, byref(size)) == 1, "OpenSSL could not export the public key")
        public, number, scalar = out.raw[:size.value], c_void_p(), create_string_buffer(32)
        must(C.EVP_PKEY_get_bn_param(key, b"priv", byref(number)) == 1 and C.BN_bn2binpad(number, scalar, 32) == 32,
             "OpenSSL could not export the private key")
        C.BN_clear_free(number)
        return public, scalar.raw
    must(C.EVP_PKEY_get_raw_public_key(key, out, byref(size)) == 1, "OpenSSL could not export the public key")
    public, size = out.raw[:size.value], c_size_t(8192)
    must(C.EVP_PKEY_get_raw_private_key(key, out, byref(size)) == 1, "OpenSSL could not export the private key")
    return public, out.raw[:size.value]


# ---------------------------------------------------------------- the operations

def signature_options(req):
    """The optional inputs of an ML-DSA call, as the option names OpenSSL itself uses."""
    options = []
    if req.get("context"):
        options.append((b"hexcontext-string", req["context"].encode()))
    if req.get("randomness"):
        options.append((b"hextest-entropy", req["randomness"].encode()))
    elif req.get("deterministic"):
        options.append((b"deterministic", b"1"))
    if req.get("interface") == "internal":
        options.append((b"message-encoding", b"0"))
    elif req.get("interface") == "mu":
        options.append((b"mu", b"1"))
    return options


def sign(algorithm, key, message, options=()):
    ctx, pctx = C.EVP_MD_CTX_new(), c_void_p()
    try:
        must(C.EVP_DigestSignInit_ex(ctx, byref(pctx), b"SHA256" if algorithm == "ECDSA P-256" else None, None, None, key, None) == 1,
             "OpenSSL could not start signing")
        for name, value in options:
            must(C.EVP_PKEY_CTX_ctrl_str(pctx, name, value) == 1, "OpenSSL did not accept " + name.decode())
        size, out = c_size_t(8192), create_string_buffer(8192)
        must(C.EVP_DigestSign(ctx, out, byref(size), message, len(message)) == 1, "OpenSSL could not sign")
        return out.raw[:size.value]
    finally:
        C.EVP_MD_CTX_free(ctx)


def verify(algorithm, key, message, signature, options=()):
    ctx, pctx = C.EVP_MD_CTX_new(), c_void_p()
    try:
        ok = C.EVP_DigestVerifyInit_ex(ctx, byref(pctx), b"SHA256" if algorithm == "ECDSA P-256" else None, None, None, key, None) == 1
        ok = ok and all(C.EVP_PKEY_CTX_ctrl_str(pctx, name, value) == 1 for name, value in options)
        ok = ok and C.EVP_DigestVerify(ctx, signature, len(signature), message, len(message)) == 1
        C.ERR_clear_error()
        return bool(ok)
    finally:
        C.EVP_MD_CTX_free(ctx)


def kem(key, start, options=()):
    ctx = C.EVP_PKEY_CTX_new_from_pkey(None, key, None)
    must(ctx and start(ctx, None) == 1, "OpenSSL could not start the key exchange")
    for name, value in options:
        must(C.EVP_PKEY_CTX_ctrl_str(ctx, name, value) == 1, "OpenSSL did not accept " + name.decode())
    return ctx


# ---------------------------------------------------------------- the commands

def algorithm_of(req):
    algorithm = req.get("algorithm", "ECDSA P-256")
    if algorithm not in ALGORITHMS:
        raise ValueError("unknown algorithm")
    return algorithm


def cmd_info(req):
    algorithm = algorithm_of(req)
    library = C.OpenSSL_version(0).decode("ascii", "replace")
    details = {"ECDSA P-256": ("SHA-256", "DER", "uncompressed point, hex (04 || X || Y)"),
               "ML-DSA-65": ("built in (SHAKE256)", "FIPS 204, 3309 bytes", "FIPS 204, 1952 bytes"),
               "ML-KEM-768": ("built in (SHA-3)", "none: a key exchange", "FIPS 203 encapsulation key, 1184 bytes")}[algorithm]
    return {"name": NAME, "version": library.split(" ")[1], "algorithm": algorithm, "algorithms": list(ALGORITHMS), "hash": details[0],
            "signature_format": details[1], "public_key_format": details[2], "commands": list(COMMANDS), "library": library}


def cmd_keygen(req):
    algorithm = algorithm_of(req)
    key = generate(algorithm, [(b"hexseed", req["seed"].encode())] if req.get("seed") else ())
    public, private = export(algorithm, key)
    C.EVP_PKEY_free(key)
    return {"public_key": public.hex(), "private_key": private.hex()}


def cmd_sign(req):
    algorithm = algorithm_of(req)
    if algorithm == "ML-KEM-768":
        raise ValueError("ML-KEM-768 does not sign")
    key = private_key(algorithm, bytes.fromhex(req["private_key"]))
    try:
        options = signature_options(req) if algorithm == "ML-DSA-65" else ()
        return {"signature": sign(algorithm, key, bytes.fromhex(req["message"]), options).hex()}
    finally:
        C.EVP_PKEY_free(key)


def cmd_verify(req):
    algorithm = algorithm_of(req)
    if algorithm == "ML-KEM-768":
        raise ValueError("ML-KEM-768 does not verify")
    message, signature = bytes.fromhex(req["message"]), bytes.fromhex(req["signature"])
    try:
        key = public_key(algorithm, bytes.fromhex(req["public_key"]))
    except Refused as refusal:
        return {"valid": False, "note": str(refusal)[:120]}
    try:
        return {"valid": verify(algorithm, key, message, signature, signature_options(req) if algorithm == "ML-DSA-65" else ())}
    finally:
        C.EVP_PKEY_free(key)


def cmd_encaps(req):
    if algorithm_of(req) != "ML-KEM-768":
        raise ValueError("encaps needs ML-KEM-768")
    key = public_key("ML-KEM-768", bytes.fromhex(req["public_key"]))
    ctx = None
    try:
        ctx = kem(key, C.EVP_PKEY_encapsulate_init, [(b"hexikme", req["randomness"].encode())] if req.get("randomness") else ())
        ciphertext, secret = create_string_buffer(4096), create_string_buffer(256)
        sizes = c_size_t(4096), c_size_t(256)
        must(C.EVP_PKEY_encapsulate(ctx, ciphertext, byref(sizes[0]), secret, byref(sizes[1])) == 1, "OpenSSL could not encapsulate")
        return {"ciphertext": ciphertext.raw[:sizes[0].value].hex(), "shared_secret": secret.raw[:sizes[1].value].hex()}
    finally:
        C.EVP_PKEY_CTX_free(ctx)
        C.EVP_PKEY_free(key)


def cmd_decaps(req):
    if algorithm_of(req) != "ML-KEM-768":
        raise ValueError("decaps needs ML-KEM-768")
    ciphertext = bytes.fromhex(req["ciphertext"])
    key = private_key("ML-KEM-768", bytes.fromhex(req["private_key"]))
    ctx = None
    try:
        ctx = kem(key, C.EVP_PKEY_decapsulate_init)
        secret, size = create_string_buffer(256), c_size_t(256)
        must(C.EVP_PKEY_decapsulate(ctx, secret, byref(size), ciphertext, len(ciphertext)) == 1, "OpenSSL could not decapsulate")
        return {"shared_secret": secret.raw[:size.value].hex()}
    finally:
        C.EVP_PKEY_CTX_free(ctx)
        C.EVP_PKEY_free(key)


def wait(ms):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:  # busy-wait: steadier than sleep for a few milliseconds
        pass


def cmd_bench(req, slow=False):
    """Sign and verify `repeats` times inside this one run and report each timing, so start-up is not counted."""
    algorithm = algorithm_of(req)
    if algorithm == "ML-KEM-768":
        raise ValueError("bench times signing; ML-KEM-768 does not sign")
    repeats = req.get("repeats", 100)
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 1000:
        raise ValueError("repeats must be 1 to 1000")
    message = bytes.fromhex(req.get("message", ""))
    key = private_key(algorithm, bytes.fromhex(req["private_key"])) if req.get("private_key") else generate(algorithm)
    public_bytes, _ = export(algorithm, key)
    public = public_key(algorithm, public_bytes)
    for _ in range(2):  # warm-up, not timed
        verify(algorithm, public, message, sign(algorithm, key, message))
    sign_ms, verify_ms, all_verified, signature = [], [], True, b""
    for _ in range(repeats):
        t0 = time.perf_counter()
        if slow:
            wait(SLOW_MS)
        signature = sign(algorithm, key, message)
        t1 = time.perf_counter()
        if slow:
            wait(SLOW_MS)
        ok = verify(algorithm, public, message, signature)
        t2 = time.perf_counter()
        all_verified = all_verified and ok
        sign_ms.append(round((t1 - t0) * 1000, 4))
        verify_ms.append(round((t2 - t1) * 1000, 4))
    C.EVP_PKEY_free(key)
    C.EVP_PKEY_free(public)
    return {"repeats": repeats, "warmups": 2, "clock": "time.perf_counter", "sign_ms": sign_ms, "verify_ms": verify_ms,
            "signature_bytes": len(signature), "public_key_bytes": len(public_bytes), "all_verified": all_verified}


HANDLERS = {"keygen": cmd_keygen, "sign": cmd_sign, "verify": cmd_verify, "info": cmd_info, "bench": cmd_bench,
            "encaps": cmd_encaps, "decaps": cmd_decaps}


def main(argv):
    slow = argv[1:2] == ["--slow"]
    words = argv[2:] if slow else argv[1:]
    if len(words) != 1 or words[0] not in HANDLERS:
        print(json.dumps({"error": USAGE}))
        return 2
    try:
        text = sys.stdin.read()
        req = json.loads(text) if text.strip() else {}
        if not isinstance(req, dict):
            raise ValueError("input must be a JSON object")
        out = cmd_bench(req, slow) if words[0] == "bench" else HANDLERS[words[0]](req)
    except Refused as refusal:  # OpenSSL said no to an input: a clear answer, not a failure of the call
        print(json.dumps({"refused": True, "note": str(refusal)[:120]}))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        # Never repeat the input here: it may hold a test private key.
        print(json.dumps({"error": "bad input: " + exc.__class__.__name__}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
