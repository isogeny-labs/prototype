"""Evidence attestation: in-toto Statement v1 wrapped in a DSSE envelope, signed with Ed25519.

Format (documented in docs/ATTESTATION.md):
  Statement  {"_type": "https://in-toto.io/Statement/v1", "subject": [{"name", "digest": {"sha256"}}],
              "predicateType": PREDICATE_RUN, "predicate": {...}}
  Envelope   {"payloadType": "application/vnd.in-toto+json", "payload": b64(statement JSON),
              "signatures": [{"keyid": <sha256 hex of raw Ed25519 public key>, "sig": b64(Ed25519(PAE))}]}
  PAE        "DSSEv1" SP len(type) SP type SP len(payload) SP payload       (DSSE pre-authentication encoding)
Bundle file {"format": "iel-evidence-bundle/1", "envelope": {...}, "artifacts": {"<name>": "<base64 bytes>"}}

Signing uses the maintained `cryptography` library; nothing cryptographic is implemented here.
A key is NEVER trusted because it appears inside a bundle; callers pass explicitly trusted keys.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PAYLOAD_TYPE = "application/vnd.in-toto+json"
PREDICATE_RUN = "https://isogeny-labs.example/evidence/run/v1"
PREDICATE_RECEIPT = "https://isogeny-labs.example/evidence/ingestion-receipt/v1"
BUNDLE_FORMAT = "iel-evidence-bundle/1"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def pae(payload_type: str, payload: bytes) -> bytes:
    return b"DSSEv1 %d %s %d %s" % (len(payload_type), payload_type.encode(), len(payload), payload)


# ---------------------------------------------------------------- keys
def generate_private_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def private_key_to_pem(key: ed25519.Ed25519PrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def private_key_from_pem(pem: bytes) -> ed25519.Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise ValueError("only Ed25519 signing keys are supported")
    return key


def public_key_to_pem(key: ed25519.Ed25519PublicKey) -> str:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def public_key_from_pem(pem: str | bytes) -> ed25519.Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise ValueError("only Ed25519 public keys are supported")
    return key


def key_id(public_key: ed25519.Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sha256_hex(raw)


# ---------------------------------------------------------------- statements / envelopes
def build_statement(subjects: list[dict], predicate_type: str, predicate: dict) -> dict:
    for s in subjects:
        assert "name" in s and "digest" in s and "sha256" in s["digest"], "subject needs name + digest.sha256"
    return {"_type": STATEMENT_TYPE, "subject": subjects, "predicateType": predicate_type, "predicate": predicate}


def sign_statement(statement: dict, private_key: ed25519.Ed25519PrivateKey) -> dict:
    payload = canonical(statement)
    sig = private_key.sign(pae(PAYLOAD_TYPE, payload))
    return {"payloadType": PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
            "signatures": [{"keyid": key_id(private_key.public_key()), "sig": base64.b64encode(sig).decode()}]}


def decode_statement(envelope: dict) -> dict:
    return json.loads(base64.b64decode(envelope["payload"]))


@dataclass
class VerifyResult:
    structure_ok: bool = False
    signature_verified: bool = False
    signer_trusted: bool = False
    keyid: str | None = None
    signer_name: str | None = None
    digests_checked: dict = field(default_factory=dict)   # subject name -> True/False/None(missing)
    digests_ok: bool | None = None
    statement: dict | None = None
    problems: list = field(default_factory=list)
    verified: list = field(default_factory=list)
    unverified: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.structure_ok and self.signature_verified and self.signer_trusted and self.digests_ok is True


def verify_envelope(envelope: dict, trusted_keys: dict[str, tuple[str, ed25519.Ed25519PublicKey]],
                    artifacts: dict[str, bytes] | None = None, expected_predicate: str | None = None) -> VerifyResult:
    """trusted_keys: keyid -> (display name, public key). Keys found inside the bundle are never consulted."""
    r = VerifyResult()
    try:
        assert isinstance(envelope, dict) and envelope.get("payloadType") == PAYLOAD_TYPE, "payloadType must be application/vnd.in-toto+json"
        payload = base64.b64decode(envelope["payload"])
        sigs = envelope.get("signatures") or []
        assert sigs and all("keyid" in s and "sig" in s for s in sigs), "envelope has no usable signatures"
        stmt = json.loads(payload)
        assert stmt.get("_type") == STATEMENT_TYPE, "not an in-toto Statement v1"
        assert isinstance(stmt.get("subject"), list) and stmt["subject"], "statement has no subjects"
        assert isinstance(stmt.get("predicate"), dict), "statement has no predicate"
        if expected_predicate:
            assert stmt.get("predicateType") == expected_predicate, f"unexpected predicateType {stmt.get('predicateType')}"
        r.structure_ok = True
        r.statement = stmt
        r.verified.append("envelope and statement structure")
    except Exception as e:  # noqa: BLE001
        r.problems.append(f"structure: {e}")
        return r
    for s in sigs:
        entry = trusted_keys.get(s["keyid"])
        if not entry:
            r.problems.append(f"signer keyid {s['keyid'][:16]}… is not in the supplied trust policy")
            continue
        name, pub = entry
        try:
            pub.verify(base64.b64decode(s["sig"]), pae(envelope["payloadType"], payload))
            r.signature_verified, r.signer_trusted, r.keyid, r.signer_name = True, True, s["keyid"], name
            r.verified.append(f"DSSE signature by trusted key '{name}'")
            break
        except InvalidSignature:
            r.problems.append(f"signature by trusted key '{name}' does NOT verify")
        except Exception as e:  # noqa: BLE001
            r.problems.append(f"signature check error: {type(e).__name__}")
    if not r.signature_verified:
        r.unverified.append("signature (no valid signature by a trusted key)")
    if artifacts is not None:
        ok, attached, referenced = True, [], []
        names = {s["name"] for s in stmt["subject"]}
        for subj in stmt["subject"]:
            data = artifacts.get(subj["name"])
            if data is None:
                r.digests_checked[subj["name"]] = None   # referenced by digest only (e.g. source kept local)
                referenced.append(subj["name"])
            else:
                match = sha256_hex(data) == subj["digest"]["sha256"]
                r.digests_checked[subj["name"]] = match
                attached.append(subj["name"])
                if not match:
                    r.problems.append(f"artifact '{subj['name']}' digest does not match the statement")
                    ok = False
        for extra in sorted(set(artifacts) - names):
            r.problems.append(f"artifact '{extra}' is attached but not referenced by the statement")
            ok = False
        if not attached:
            r.problems.append("no statement subject is attached as an artifact; nothing could be hash-checked")
            ok = False
        r.digests_ok = ok
        (r.verified if ok else r.unverified).append(f"artifact digests of attached subjects ({', '.join(attached) or 'none'})")
        if referenced:
            r.unverified.append("subjects referenced by digest only, not attached: " + ", ".join(referenced))
    else:
        r.unverified.append("artifact digests (no artifacts supplied)")
    r.unverified.append("that the reported environment/execution was genuine (a signature proves integrity and attribution only)")
    return r


# ---------------------------------------------------------------- bundle files
def make_bundle(envelope: dict, artifacts: dict[str, bytes]) -> dict:
    return {"format": BUNDLE_FORMAT, "envelope": envelope,
            "artifacts": {k: base64.b64encode(v).decode() for k, v in artifacts.items()}}


def load_bundle(doc: dict) -> tuple[dict, dict[str, bytes]]:
    if not isinstance(doc, dict) or doc.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"not an {BUNDLE_FORMAT} document")
    arts = {k: base64.b64decode(v) for k, v in (doc.get("artifacts") or {}).items()}
    return doc["envelope"], arts
