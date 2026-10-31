#!/usr/bin/env python3
"""Application-service cryptographic regression fixture.

Evaluates a library/configuration change for a containerised service. Two purposes are supported and
are deliberately kept separate (a signature profile is never compared with an AEAD profile):

  purpose = "token_signing": profiles rs256 | ps256 | es256 | eddsa (JWS-style compact tokens)
  purpose = "payload_encryption": profiles aes128_gcm | aes256_gcm | chacha20_poly1305

Params: purpose, profile, repeat_count (default 200), payload_bytes (default 512)
"""
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import environment, summarize_ms, timed, peak_alloc_kb, read_params, emit, MEMORY_DEFINITION, TIME_DEFINITION  # noqa: E402

FIXTURE_VERSION = "1.0.0"


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


# ---------------------------------------------------------------- token signing
def signing_profile(profile):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, padding, utils

    if profile in ("rs256", "ps256"):
        sk = rsa.generate_private_key(65537, 2048)
        pad = padding.PKCS1v15() if profile == "rs256" else padding.PSS(padding.MGF1(hashes.SHA256()), 32)
        sign = lambda m: sk.sign(m, pad, hashes.SHA256())  # noqa: E731

        def verify(m, s):
            try:
                sk.public_key().verify(s, m, pad, hashes.SHA256())
                return True
            except Exception:
                return False
        pkb = sk.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return sign, verify, len(pkb), "RSA-2048 " + ("PKCS#1 v1.5" if profile == "rs256" else "PSS") + " SHA-256"
    if profile == "es256":
        sk = ec.generate_private_key(ec.SECP256R1())

        def sign(m):
            r, s = utils.decode_dss_signature(sk.sign(m, ec.ECDSA(hashes.SHA256())))
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")

        def verify(m, s):
            try:
                if len(s) != 64:
                    return False
                der = utils.encode_dss_signature(int.from_bytes(s[:32], "big"), int.from_bytes(s[32:], "big"))
                sk.public_key().verify(der, m, ec.ECDSA(hashes.SHA256()))
                return True
            except Exception:
                return False
        return sign, verify, 65, "ECDSA P-256 SHA-256"
    if profile == "eddsa":
        sk = ed25519.Ed25519PrivateKey.generate()

        def verify(m, s):
            try:
                sk.public_key().verify(s, m)
                return True
            except Exception:
                return False
        return sk.sign, verify, 32, "Ed25519"
    raise KeyError(profile)


def run_signing(profile, repeats, payload_bytes):
    sign, verify, pk_len, label = signing_profile(profile)
    header = b64u(json.dumps({"alg": profile.upper(), "typ": "JWT"}).encode())
    claims = b64u(json.dumps({"sub": "svc", "scope": "x" * max(0, payload_bytes - 40)}).encode())
    signing_input = header + b"." + claims
    sig = sign(signing_input)
    token = signing_input + b"." + b64u(sig)

    def parse_and_verify(tok):
        try:
            h, c, s = tok.split(b".")
            raw = base64.urlsafe_b64decode(s + b"=" * (-len(s) % 4))
            return verify(h + b"." + c, raw)
        except Exception:
            return False

    scen = []

    def case(cid, name, expected, tok):
        obs = "accept" if parse_and_verify(tok) else "reject"
        scen.append({"id": cid, "name": name, "expected": expected, "observed": obs, "pass": obs == expected})

    case("valid_token", "Valid token verifies", "accept", token)
    case("tampered_claims", "Token with modified claims is rejected", "reject",
         header + b"." + b64u(json.dumps({"sub": "admin"}).encode()) + b"." + b64u(sig))
    case("tampered_signature", "Token with corrupted signature is rejected", "reject",
         signing_input + b"." + b64u(bytes([sig[0] ^ 1]) + sig[1:]))
    case("truncated_signature", "Truncated signature is rejected", "reject", signing_input + b"." + b64u(sig[:-2]))
    case("empty_signature", "Empty signature is rejected", "reject", signing_input + b".")
    case("alg_none_shape", "Token with no signature segment is rejected", "reject", signing_input)
    case("garbage", "Non-token bytes are rejected", "reject", b"\x00\xff\x10garbage")

    parse_and_verify(token)
    verify_ms = timed(lambda: parse_and_verify(token), repeats)
    sign_ms = timed(lambda: sign(signing_input), max(5, repeats // 4))
    peak = peak_alloc_kb(lambda: parse_and_verify(token))
    vs, ss = summarize_ms(verify_ms), summarize_ms(sign_ms)
    metrics = {
        "verify_time_ms_median": vs["median"], "verify_time_ms_p95": vs["p95"],
        "sign_time_ms_median": ss["median"], "sign_time_ms_p95": ss["p95"],
        "verify_throughput_per_s": 1000.0 / vs["mean"], "sign_throughput_per_s": 1000.0 / ss["mean"],
        "signature_bytes": len(sig), "public_key_bytes": pk_len, "token_bytes": len(token),
        "verify_peak_alloc_kb": round(peak, 2),
        "scenario_pass_count": sum(1 for s in scen if s["pass"]), "scenario_total": len(scen),
        "rejection_scenarios_all_pass": 1 if all(s["pass"] for s in scen if s["expected"] == "reject") else 0,
        "functional_pass": 1 if all(s["pass"] for s in scen) else 0,
    }
    return label, scen, metrics, {"verify_times_ms": verify_ms, "sign_times_ms": sign_ms}


# ---------------------------------------------------------------- payload encryption (AEAD)
def run_aead(profile, repeats, payload_bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    import os as _os
    if profile == "aes128_gcm":
        key = AESGCM.generate_key(128); aead = AESGCM(key); label = "AES-128-GCM"
    elif profile == "aes256_gcm":
        key = AESGCM.generate_key(256); aead = AESGCM(key); label = "AES-256-GCM"
    elif profile == "chacha20_poly1305":
        key = ChaCha20Poly1305.generate_key(); aead = ChaCha20Poly1305(key); label = "ChaCha20-Poly1305"
    else:
        raise KeyError(profile)
    pt = _os.urandom(payload_bytes)
    aad = b"ctx:v1"
    nonce = _os.urandom(12)
    ct = aead.encrypt(nonce, pt, aad)

    def dec(n, c, a):
        try:
            return aead.decrypt(n, c, a) == pt
        except Exception:
            return False

    scen = []

    def case(cid, name, expected, ok):
        obs = "accept" if ok else "reject"
        scen.append({"id": cid, "name": name, "expected": expected, "observed": obs, "pass": obs == expected})

    case("roundtrip", "Ciphertext decrypts to the plaintext", "accept", dec(nonce, ct, aad))
    case("tampered_ciphertext", "Flipped ciphertext bit is rejected", "reject", dec(nonce, bytes([ct[0] ^ 1]) + ct[1:], aad))
    case("tampered_tag", "Flipped tag bit is rejected", "reject", dec(nonce, ct[:-1] + bytes([ct[-1] ^ 1]), aad))
    case("wrong_aad", "Wrong associated data is rejected", "reject", dec(nonce, ct, b"ctx:v2"))
    case("wrong_nonce", "Wrong nonce is rejected", "reject", dec(bytes(12), ct, aad))
    case("truncated", "Truncated ciphertext is rejected", "reject", dec(nonce, ct[:8], aad))

    enc_ms = timed(lambda: aead.encrypt(nonce, pt, aad), repeats)
    dec_ms = timed(lambda: dec(nonce, ct, aad), repeats)
    es, ds = summarize_ms(enc_ms), summarize_ms(dec_ms)
    metrics = {
        "encrypt_time_ms_median": es["median"], "decrypt_time_ms_median": ds["median"],
        "decrypt_time_ms_p95": ds["p95"],
        "encrypt_throughput_mb_s": payload_bytes / (es["mean"] / 1000.0) / 1e6,
        "ciphertext_overhead_bytes": len(ct) - payload_bytes + len(nonce),
        "key_bytes": len(key),
        "scenario_pass_count": sum(1 for s in scen if s["pass"]), "scenario_total": len(scen),
        "rejection_scenarios_all_pass": 1 if all(s["pass"] for s in scen if s["expected"] == "reject") else 0,
        "functional_pass": 1 if all(s["pass"] for s in scen) else 0,
    }
    return label, scen, metrics, {"encrypt_times_ms": enc_ms, "decrypt_times_ms": dec_ms}


def main():
    p = read_params()
    purpose = p.get("purpose", "token_signing")
    profile = p.get("profile", "rs256")
    repeats = int(p.get("repeat_count", 200))
    payload = int(p.get("payload_bytes", 512))
    try:
        if purpose == "token_signing":
            label, scen, metrics, raw = run_signing(profile, repeats, payload)
        elif purpose == "payload_encryption":
            label, scen, metrics, raw = run_aead(profile, repeats, payload)
        else:
            raise KeyError(f"unsupported purpose {purpose}")
    except Exception as e:
        emit({"fixture": "app_service_crypto", "fixture_version": FIXTURE_VERSION, "status": "failed",
              "failures": [f"{type(e).__name__}: {e}"], "environment": environment()})
        return 2
    emit({
        "fixture": "app_service_crypto", "fixture_version": FIXTURE_VERSION, "status": "completed",
        "purpose": purpose, "profile": profile, "label": label, "library": "cryptography/OpenSSL",
        "environment": environment(), "repeat_count": repeats,
        "parameters": {"payload_bytes": payload},
        "scenarios": scen, "metrics": metrics,
        "metric_definitions": {
            "*_time_ms_*": TIME_DEFINITION,
            "verify_peak_alloc_kb": MEMORY_DEFINITION,
            "token_bytes": "Compact JWS-style token length (header.claims.signature, base64url).",
            "ciphertext_overhead_bytes": "nonce + tag bytes added to the plaintext.",
            "encrypt_throughput_mb_s": "payload_bytes / mean encrypt seconds, in MB/s (decimal).",
        },
        "raw": raw, "failures": [],
        "limitations": [
            "Measured inside the runner process (host CPU); production service latency depends on deployment.",
            "Correctness scenarios check that the library rejects these malformed inputs; this is not a security proof.",
        ],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
