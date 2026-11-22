"""The "Who can still connect" test (phase 4e, first half): one locked test for one try of one change on one server.

It is written down here, not by the research engine (engine/research.py stays as it is), as Otto's designs are: a spec
of the same form as every test, locked before it runs (lab/testlab.py, `_lock_spec`), run through the job runner while
the try's test copy is up (run/execute/clients.py), and reviewed by the separate reviewer (engine/reviewer.py,
`RuleReviewer._client_reach`). The same change on the same server is the same test, and so the same plan item.

It decides nothing about the try: whether the try passed stays the system's own measurement. Its words per stand-in
(Connects, Falls back, Breaks, Didn't connect before either, Couldn't check) are information. A Breaks holds nothing
off: Apply works as before.
"""

from __future__ import annotations

from app.clients import profiles
from app.engine.research import SPEC_SCHEMA

KIND = "client_reach"
TITLE = "Who can still connect"
PROPOSED_BY = "client-stand-ins-1"  # who wrote the test down (never the reviewer)
# The changes that bring post-quantum key exchange (a classical connection to them "falls back").
POST_QUANTUM_OPTIONS = ("hybrid", "full_pq")
# What each stand-in must do on our own two control servers (pqtls.control_servers: hybrid offers X25519MLKEM768, then
# X25519 and P-256; classical offers X25519 and P-256; both TLS 1.2 to 1.3 with an ECDSA P-256 test certificate).
CONTROL_MUST = {
    "old-terminal": {
        "hybrid": {"kind": "classical", "version": "TLS 1.2"},
        "classical": {"kind": "classical", "version": "TLS 1.2"},
    },
    "partner-classical": {
        "hybrid": {"kind": "classical", "version": "TLS 1.3"},
        "classical": {"kind": "classical", "version": "TLS 1.3"},
    },
    "new-terminal": {
        "hybrid": {"kind": "hybrid", "version": "TLS 1.3"},
        "classical": {"kind": "classical", "version": "TLS 1.3"},
    },
    "pq-only": {"hybrid": {"kind": "refused", "version": None}, "classical": {"kind": "refused", "version": None}},
}
RULE_TEXT = (
    "For each stand-in, from its handshake with the server as it is today and with the test copy: Connects when the "
    "copy completes the handshake and, where the change brings post-quantum key exchange, uses it; Falls back when the "
    "copy completes it with classical key exchange on a change that brings post-quantum key exchange; Breaks when it "
    "completes today and the copy clearly refuses it; Didn't connect before either when both refuse it; Couldn't check "
    "for any answer that is not a clear completion or a clear refusal. Silence is never read as Breaks. Information "
    "only: it decides nothing about the try, and holds nothing off."
)


def design(*, address: str, change: dict) -> dict:
    """The locked test for one change (its key, fingerprint, option and kind) tried on one server."""
    stand_ins = profiles.stand_ins()
    option = str(change.get("option") or "")
    brings = option in POST_QUANTUM_OPTIONS
    return {
        "schema": SPEC_SCHEMA,
        "kind": KIND,
        "title": TITLE,
        "card": {
            "description": f"Connects four demo client stand-ins to {address} as it is today and to a test copy with the change.",
            "why": "Why it matters: a change to what a server offers can stop machines that connect to it today.",
        },
        "question": f"Which of the four demo client stand-ins can still connect to {address} with this change, and how?",
        "method": (
            "Each stand-in makes one full handshake to the server as it is today, one to the test copy with the change, "
            "and one to each of our two control servers: our own OpenSSL, offering exactly the TLS versions, key "
            "exchanges and signature types its profile lists. Handshakes only; no data is sent."
        ),
        "target": {"kind": "server", "address": address},
        "inputs": {
            "stand_ins": stand_ins,
            "stand_ins_sha256": profiles.fingerprint(),
            "change": {
                "key": change.get("key"),
                "fingerprint": change.get("fingerprint"),
                "option": option,
                "kind": change.get("kind"),
            },
            "brings_post_quantum": brings,
        },
        "inputs_text": [f"{p['name']} ({profiles.DEMO_LABEL}): {p['offers']}" for p in stand_ins]
        + [
            (
                "The change brings post-quantum key exchange, so a classical connection to it falls back."
                if brings
                else "The change brings no post-quantum key exchange, so any completed connection to it connects."
            )
        ],
        "control": {
            "kind": "client_stand_ins_on_control_servers",
            "must": CONTROL_MUST,
            "text": (
                "The same handshakes against our own hybrid and classical test servers, started for this run: the new "
                "firmware must take hybrid on the hybrid one, the classical stand-ins classical, the old firmware "
                "TLS 1.2, and the post-quantum-only client must be refused by both."
            ),
        },
        "rule": {"type": "client_reach_words"},
        "rule_text": RULE_TEXT,
    }


__all__ = ["design", "KIND", "TITLE", "PROPOSED_BY", "CONTROL_MUST"]
