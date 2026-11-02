"""Generate inputs for the suite toolkit's negative and positive controls.

Negative controls use the same production library the fixtures use (`cryptography` / OpenSSL): a real ES256 signing
transcript and freshly generated RSA-2048 public keys. A correct auditor must report nothing on them.

Positive controls plant a known weakness so a reviewer can see the auditor detect it: RSA moduli sharing a prime,
a modulus with close primes, and a modulus with a small private exponent. Every planted key is synthetic, generated
here, labelled as such, and never used for anything else.
"""
from __future__ import annotations

import hashlib
import math
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa, utils

_CURVES = {"p256": ec.SECP256R1, "secp256k1": ec.SECP256K1}


def es256_transcript(count: int = 32, curve: str = "p256") -> dict:
    """Sign `count` distinct token payloads with a fresh key; return Q and (r, s, z) as decimal strings."""
    key = ec.generate_private_key(_CURVES[curve]())
    pub = key.public_key().public_numbers()
    sigs = []
    for i in range(count):
        msg = f'{{"sub":"device-{i:04d}","iat":{1730000000 + i}}}'.encode()
        r, s = utils.decode_dss_signature(key.sign(msg, ec.ECDSA(hashes.SHA256())))
        z = int.from_bytes(hashlib.sha256(msg).digest(), "big")
        sigs.append({"r": str(r), "s": str(s), "z": str(z)})
    return {"curve": curve, "public_key": f"{pub.x},{pub.y}", "signatures": sigs,
            "source": f"cryptography {_lib_version()} ECDSA-{curve}-SHA256, {count} signatures, fresh key (discarded)"}


def rsa_public_moduli(count: int = 6, bits: int = 2048) -> dict:
    ns = [str(rsa.generate_private_key(65537, bits).public_key().public_numbers().n) for _ in range(count)]
    return {"moduli": ns, "public_exponent": "65537",
            "source": f"cryptography {_lib_version()} RSA-{bits} key generation, {count} keys (private halves discarded)"}


def _is_probable_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _next_prime(n: int) -> int:
    n |= 1
    while not _is_probable_prime(n):
        n += 2
    return n


def _primes(bits: int) -> tuple[int, int]:
    k = rsa.generate_private_key(65537, bits * 2).private_numbers()
    return k.p, k.q


def weak_rsa_moduli() -> dict:
    """Shared-prime pair + close-primes modulus + two honest moduli, all 1024-bit, e = 65537."""
    p, q1 = _primes(512)
    _, q2 = _primes(512)
    a, _ = _primes(512)
    b = _next_prime(a + (1 << 40) + secrets.randbelow(1 << 20))
    honest = [str(rsa.generate_private_key(65537, 1024).public_key().public_numbers().n) for _ in range(2)]
    return {"moduli": [str(p * q1), str(p * q2), str(a * b), *honest], "public_exponent": "65537",
            "planted": ["#0 and #1 share a prime", "#2 has |p − q| ≈ 2^40 (Fermat)", "#3, #4 honest"],
            "source": "synthetic 1024-bit moduli generated for this control"}


def wiener_rsa_modulus() -> dict:
    """One 1024-bit modulus whose private exponent is below N^0.25 / 3 (Wiener-vulnerable)."""
    while True:
        p, q = _primes(512)
        n, phi = p * q, (p - 1) * (q - 1)
        d = secrets.randbits(240) | 1
        if math.gcd(d, phi) == 1 and 3 * d < math.isqrt(math.isqrt(n)):
            return {"moduli": [str(n)], "public_exponent": str(pow(d, -1, phi)),
                    "planted": ["#0 has a ~240-bit private exponent"], "source": "synthetic 1024-bit Wiener control"}


def _lib_version() -> str:
    import cryptography
    return cryptography.__version__


def firmware_digest_kat(size: int = 4096) -> dict:
    """A deterministic pseudo-firmware image hashed by Python's hashlib; the suite must reproduce the digest."""
    image = hashlib.shake_256(b"FG-200 firmware image 3.0.0-rc1").digest(size)
    return {"algorithm": "sha256", "hex": image.hex(), "expected_hex": hashlib.sha256(image).hexdigest(),
            "source": f"{size}-byte deterministic test image; expected digest from Python hashlib"}


# Server-side generated controls: material that must be fresh (keys, transcripts), so it cannot be a static preset.
# id -> (tool id, kind, display name, generator returning tool params)
GENERATED = {
    "es256_transcript": ("suite_ecdsa_audit", "negative", "Real ES256 transcript from cryptography/OpenSSL (32 signatures, full sweep)",
                         lambda: {**es256_transcript(32), "mode": "transcript", "full_sweep": True, "expect": "no_bias"}),
    "rsa_real_keys": ("suite_rsa_key_audit", "negative", "Six fresh RSA-2048 keys from cryptography/OpenSSL",
                      lambda: {**rsa_public_moduli(6), "expect": "no_weakness"}),
    "rsa_weak_moduli": ("suite_rsa_key_audit", "positive", "Planted shared-prime pair + close-primes modulus (synthetic)",
                        lambda: {**weak_rsa_moduli(), "synthetic": True, "expect": "weakness_detected"}),
    "rsa_wiener": ("suite_rsa_key_audit", "positive", "Planted small private exponent (synthetic, Wiener)",
                   lambda: {**wiener_rsa_modulus(), "synthetic": True, "expect": "weakness_detected"}),
    "firmware_digest": ("suite_hash_kat", "negative", "SHA-256 of a 4 KiB test image vs Python hashlib",
                        lambda: firmware_digest_kat()),
}


def generate(control_id: str) -> tuple[str, dict, dict]:
    """Return (tool id, tool params, provenance note) for a generated control."""
    tool, kind, name, fn = GENERATED[control_id]
    params = fn()
    note = {"control": control_id, "kind": kind, "name": name, "source": params.pop("source", ""), "planted": params.pop("planted", None)}
    return tool, params, note


def describe() -> dict:
    return {cid: {"tool": t, "kind": k, "name": n, "generated": True, "id": cid} for cid, (t, k, n, _) in GENERATED.items()}
