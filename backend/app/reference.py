"""The reference library: pyca `cryptography`. It is our own trusted yardstick, so it runs here in the
backend, not in the sandbox. Every test of a signing component also asks the reference for its answers;
if the reference gets a case wrong, the run can't be trusted. No verdict is decided in this module."""
from __future__ import annotations

import time

import cryptography
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

LIBRARY = f"cryptography {cryptography.__version__}"


def verify_ecdsa_p256(public_key_hex: str, message_hex: str, signature_hex: str) -> bool:
    """True only if the signature is a valid ECDSA P-256 / SHA-256 signature (DER). Anything unreadable is False."""
    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), bytes.fromhex(message_hex), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_ed25519(public_key_hex: str, message_hex: str, signature_hex: str) -> bool:
    try:
        key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), bytes.fromhex(message_hex))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


_VERIFIERS = {"ecdsa_p256": verify_ecdsa_p256, "ed25519": verify_ed25519, "bad_signatures": verify_ecdsa_p256}


def answers(algorithm: str, cases) -> dict[str, str]:
    """{case id: "accept" | "reject"} from the reference library. algorithm: "ecdsa_p256" | "ed25519"
    | "bad_signatures" (ECDSA P-256); cases: vectors.Case items."""
    check = _VERIFIERS[algorithm]
    return {c.id: ("accept" if check(c.public_key, c.message, c.signature) else "reject") for c in cases}


def bench_ecdsa_p256(repeats: int, message_hex: str, warmups: int = 2) -> dict:
    """The same measurement as the adapter's `bench`, done in this process with the reference library.
    For scale only: an optimised library in-process is not comparable like for like with the component."""
    message = bytes.fromhex(message_hex)
    key = ec.generate_private_key(ec.SECP256R1())  # throwaway test key; never leaves this function
    public = key.public_key()
    algorithm = ec.ECDSA(hashes.SHA256())
    for _ in range(warmups):
        public.verify(key.sign(message, algorithm), message, algorithm)
    sign_ms, verify_ms = [], []
    signature = b""
    for _ in range(repeats):
        t0 = time.perf_counter()
        signature = key.sign(message, algorithm)
        t1 = time.perf_counter()
        public.verify(signature, message, algorithm)
        t2 = time.perf_counter()
        sign_ms.append(round((t1 - t0) * 1000, 4))
        verify_ms.append(round((t2 - t1) * 1000, 4))
    point = public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"library": LIBRARY, "repeats": repeats, "warmups": warmups, "clock": "time.perf_counter",
            "sign_ms": sign_ms, "verify_ms": verify_ms, "signature_bytes": len(signature),
            "public_key_bytes": len(point), "all_verified": True}
