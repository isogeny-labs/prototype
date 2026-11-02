"""acme-signer 1.1.0 — SAMPLE corrected customer adapter (demonstration).

Change relative to 1.0.0: the legacy "normalise to 64 bytes" step was removed. verify() now rejects any signature
whose length is not exactly 64 bytes and fails closed on every error.
"""
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ADAPTER = {"name": "acme-signer", "version": "1.1.0", "algorithm": "Ed25519", "library": "cryptography (OpenSSL)"}
SIGNATURE_LEN = 64


def keygen():
    sk = ed25519.Ed25519PrivateKey.generate()
    return sk.public_key(), sk


def sign(sk, msg: bytes) -> bytes:
    return sk.sign(msg)


def verify(pk, msg: bytes, sig: bytes) -> bool:
    if not isinstance(sig, (bytes, bytearray)) or len(sig) != SIGNATURE_LEN:
        return False
    try:
        pk.verify(bytes(sig), msg)
        return True
    except (InvalidSignature, Exception):
        return False


def public_key_bytes(pk) -> bytes:
    return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key_from_bytes(b: bytes):
    return ed25519.Ed25519PublicKey.from_public_bytes(b)


def private_key_from_bytes(b: bytes):
    return ed25519.Ed25519PrivateKey.from_private_bytes(b)
