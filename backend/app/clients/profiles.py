"""The demo client stand-ins (phase 4e, first half). DEMO DATA.

Four fictional clients of a payments server, the same four for every server in this version (a list of your own clients
comes later). A stand-in is NOT the device it is named after: it is our own built-in OpenSSL (the copy inside the
`cryptography` library, app/checks/pqtls.py) making one handshake that offers exactly what its profile lists here:
the TLS versions, the key-exchange groups in this order, and the certificate signature types it accepts. It checks no
certificate's trust: like every handshake of the app, trust is not the question.

The profiles are data. They are copied into each "Who can still connect" test when it is locked, so the run record
and its fingerprint hold exactly what each stand-in offered. Changing one here makes a new test, never a changed one.
"""

from __future__ import annotations

from app.canonical import sha256_hex

# The certificate signature types a client that knows only classical cryptography accepts (OpenSSL's names).
CLASSICAL_SIGNATURES = (
    "ecdsa_secp256r1_sha256",
    "ecdsa_secp384r1_sha384",
    "rsa_pss_rsae_sha256",
    "rsa_pss_rsae_sha384",
    "rsa_pkcs1_sha256",
    "rsa_pkcs1_sha384",
    "ed25519",
)
# ... and one that also knows post-quantum signatures (ML-DSA, FIPS 204), first.
POST_QUANTUM_SIGNATURES = ("mldsa65", "mldsa44", "mldsa87") + CLASSICAL_SIGNATURES

STAND_INS: tuple[dict, ...] = (
    {
        "id": "old-terminal",
        "name": "Payment terminal, old firmware",
        "offers": "TLS 1.2 only; classical key exchange (X25519, P-256); classical certificates only.",
        "versions": ["TLS 1.2"],
        "groups": ["X25519", "P-256"],
        "signatures": list(CLASSICAL_SIGNATURES),
    },
    {
        "id": "partner-classical",
        "name": "Partner system, classical only",
        "offers": "TLS 1.2 and 1.3; classical key exchange (X25519, P-256, P-384); classical certificates only.",
        "versions": ["TLS 1.2", "TLS 1.3"],
        "groups": ["X25519", "P-256", "P-384"],
        "signatures": list(CLASSICAL_SIGNATURES),
    },
    {
        "id": "new-terminal",
        "name": "Payment terminal, new firmware",
        "offers": "TLS 1.2 and 1.3; hybrid key exchange first (X25519MLKEM768), then classical (X25519, P-256); classical certificates only.",
        "versions": ["TLS 1.2", "TLS 1.3"],
        "groups": ["X25519MLKEM768", "X25519", "P-256"],
        "signatures": list(CLASSICAL_SIGNATURES),
    },
    {
        "id": "pq-only",
        "name": "Post-quantum-only client",
        "offers": "TLS 1.3 only; ML-KEM-768 key exchange by itself; post-quantum (ML-DSA) and classical certificates.",
        "versions": ["TLS 1.3"],
        "groups": ["MLKEM768"],
        "signatures": list(POST_QUANTUM_SIGNATURES),
    },
)
DEMO_LABEL = "Demo data"
STAND_IN_NOTE = (
    "Stand-ins are our own OpenSSL offering what each profile says, not your devices. They check no certificate's "
    "trust, and accept only the signature types their profile lists."
)


def stand_ins() -> list[dict]:
    """A fresh copy of the four profiles, in their fixed order."""
    return [
        dict(p, versions=list(p["versions"]), groups=list(p["groups"]), signatures=list(p["signatures"]))
        for p in STAND_INS
    ]


def fingerprint() -> str:
    return sha256_hex(stand_ins())
