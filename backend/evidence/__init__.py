"""Check a downloaded evidence file:  cd backend && .venv/bin/python -m evidence verify file.json

The file passes only if ALL of this holds:
1. it is valid UTF-8 JSON with no duplicate keys, written in exactly the one form the app writes
   (so any added space, reordered key or changed letter fails);
2. it has exactly the four parts: evidence, fingerprint, public_key, signature;
3. the fingerprint is the SHA-256 of the evidence part;
4. the signature over the fingerprint is valid for the public key in the file;
5. that public key is the one you trust: the app's own key in its data folder, or --public-key.

Without a trusted key (5) the command does not report a pass: it exits with code 2 and says the signer
could not be confirmed. Exit codes: 0 verified, 1 failed, 2 consistent but signer not confirmed.

This package reads the file as data only. It imports nothing from the app except the canonical JSON
writer and the default data folder setting.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.canonical import canonical_bytes, loads_strict

SIGNING_CONTEXT = b"isogeny-evidence-lab/evidence/v1\n"
EVIDENCE_SCHEMA = "isogeny.evidence/1"
PUBLIC_KEY_FILE = "evidence-signing-public-key.txt"
MAX_FILE_BYTES = 64 * 1024 * 1024
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_HEX128 = re.compile(r"\A[0-9a-f]{128}\Z")

VERIFIED, FAILED, SIGNER_NOT_CONFIRMED = 0, 1, 2
NOT_CONFIRMED_TEXT = "The file is consistent with itself, but the signer could not be confirmed."


@dataclass(frozen=True)
class Outcome:
    code: int               # VERIFIED | FAILED | SIGNER_NOT_CONFIRMED
    message: str
    fingerprint: str | None = None
    signer: str | None = None   # SHA-256 of the public key in the file

    @property
    def ok(self) -> bool:
        return self.code == VERIFIED


def _fail(message: str) -> Outcome:
    return Outcome(FAILED, f"Evidence NOT verified: {message}")


def verify_bytes(raw: bytes, trusted_public_key: str | None) -> Outcome:
    """Check the exact bytes of an evidence file. `trusted_public_key` is 64 lowercase hex, or None."""
    if len(raw) > MAX_FILE_BYTES:
        return _fail("the file is too large to be an evidence file.")
    try:
        parsed = loads_strict(raw)
    except (ValueError, RecursionError):
        return _fail("the file is not valid JSON (or has a repeated key).")
    try:
        same = canonical_bytes(parsed) == bytes(raw)
    except (ValueError, TypeError, RecursionError):
        same = False
    if not same:
        return _fail("the file is not written exactly as the app writes it. It was changed after it was made.")
    if not isinstance(parsed, dict) or set(parsed) != {"evidence", "fingerprint", "public_key", "signature"}:
        return _fail("the file does not have exactly the four parts evidence, fingerprint, public_key and signature.")
    evidence, fingerprint, public_key, signature = (parsed[k] for k in ("evidence", "fingerprint", "public_key", "signature"))
    if not (isinstance(fingerprint, str) and _HEX64.match(fingerprint)):
        return _fail("the fingerprint is not 64 lowercase hex characters.")
    if not (isinstance(public_key, str) and _HEX64.match(public_key)):
        return _fail("the public key is not 64 lowercase hex characters.")
    if not (isinstance(signature, str) and _HEX128.match(signature)):
        return _fail("the signature is not 128 lowercase hex characters.")
    if not isinstance(evidence, dict) or evidence.get("schema") != EVIDENCE_SCHEMA:
        return _fail("the evidence part is not an Evidence Lab evidence record.")
    if hashlib.sha256(canonical_bytes(evidence)).hexdigest() != fingerprint:
        return _fail("the fingerprint does not match the evidence. The evidence was changed after it was signed.")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), SIGNING_CONTEXT + fingerprint.encode("ascii"))
    except (InvalidSignature, ValueError):
        return _fail("the signature is not valid for the public key in the file.")
    signer = hashlib.sha256(bytes.fromhex(public_key)).hexdigest()
    if evidence.get("signer_key_fingerprint") != signer:
        return _fail("the evidence names a different signing key than the one that signed it.")
    if trusted_public_key is None:
        return Outcome(SIGNER_NOT_CONFIRMED, NOT_CONFIRMED_TEXT, fingerprint, signer)
    if public_key != trusted_public_key:
        return _fail("it is signed, but not by the key you trust (this app's key, or the one given with --public-key).")
    return Outcome(VERIFIED, "Evidence verified", fingerprint, signer)


def read_public_key(text_or_path: str) -> str | None:
    """64 hex characters, given directly or in a file. None if it is neither."""
    value = text_or_path.strip()
    if _HEX64.match(value.lower()):
        return value.lower()
    try:
        value = Path(text_or_path).read_text(encoding="ascii").strip().lower()
    except (OSError, ValueError):
        return None
    return value if _HEX64.match(value) else None


def trusted_key_from_data_dir(data_dir: Path) -> str | None:
    return read_public_key(str(Path(data_dir) / PUBLIC_KEY_FILE))
