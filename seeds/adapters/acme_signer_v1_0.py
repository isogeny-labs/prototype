"""acme-signer 1.0.0 — SAMPLE customer adapter (demonstration).

Wraps Ed25519 from the `cryptography` library behind the project's signing interface.

*** SEEDED DEFECT (for demonstration; clearly labelled in the platform) ***
`verify()` tolerates trailing data: it keeps only the first 64 bytes of the signature "for legacy framing".
A signature with appended bytes therefore verifies. This is a real class of input-validation bug.
"""
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ADAPTER = {"name": "acme-signer", "version": "1.0.0", "algorithm": "Ed25519", "library": "cryptography (OpenSSL)"}
SIGNATURE_LEN = 64


def keygen():
    sk = ed25519.Ed25519PrivateKey.generate()
    return sk.public_key(), sk


def sign(sk, msg: bytes) -> bytes:
    return sk.sign(msg)


def verify(pk, msg: bytes, sig: bytes) -> bool:
    # Legacy framing used to pad signatures to 80 bytes; normalise by keeping the first 64 bytes.  <-- DEFECT
    sig = bytes(sig)[:SIGNATURE_LEN]
    try:
        pk.verify(sig, msg)
        return True
    except InvalidSignature:
        return False


def public_key_bytes(pk) -> bytes:
    return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key_from_bytes(b: bytes):
    return ed25519.Ed25519PublicKey.from_public_bytes(b)


def private_key_from_bytes(b: bytes):
    return ed25519.Ed25519PrivateKey.from_private_bytes(b)
