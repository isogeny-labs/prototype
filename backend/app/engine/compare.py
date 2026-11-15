"""The comparison rules, as pure functions (no network, no files).

A result is only ever True or False when the server positively showed it:
  accepted = the handshake completed;  refused = the server sent a real TLS refusal alert;
  unknown  = we could not tell (our own tooling could not offer it, time-out, connection error...).
"""
from __future__ import annotations

from dataclasses import dataclass, field

TRUE, FALSE, COULDNT = "True", "False", "Couldn't check"


@dataclass
class SetVerdict:
    result: str
    outside_accepted: list[str] = field(default_factory=list)  # accepted although not claimed
    claimed_refused: list[str] = field(default_factory=list)   # claimed but the server refused it
    unknown: list[str] = field(default_factory=list)           # could not be tested either way


def compare_only_claim(claimed: list[str], observed: dict[str, str]) -> SetVerdict:
    """Claim: "the server accepts exactly these items and nothing else".

    False  - anything outside the claimed set was positively accepted, or a claimed item was positively refused.
    True   - every claimed item was accepted AND every other probed item was positively refused.
    Couldn't check - anything else (some item could not be tested), listing which.
    """
    claimed_set = set(claimed)
    outside_accepted = [i for i, s in observed.items() if s == "accepted" and i not in claimed_set]
    claimed_refused = [i for i in claimed if observed.get(i) == "refused"]
    unknown = [i for i in claimed if observed.get(i) not in ("accepted", "refused")]
    unknown += [i for i, s in observed.items() if i not in claimed_set and s not in ("accepted", "refused")]
    if outside_accepted or claimed_refused:
        return SetVerdict(FALSE, outside_accepted, claimed_refused, unknown)
    if unknown or not claimed:
        return SetVerdict(COULDNT, unknown=unknown)
    return SetVerdict(TRUE)


def certificate_matches(claimed_algorithm: str, cert: dict) -> bool | None:
    """Does the live certificate's key match the claim? None = we don't know how to compare this claim.

    "ECDSA P-256" means an EC key on curve secp256r1 with 256 bits. "RSA 2048" means an RSA key of 2048 bits.
    """
    curves = {"ECDSA P-256": ("secp256r1", 256), "ECDSA P-384": ("secp384r1", 384), "ECDSA P-521": ("secp521r1", 521)}
    if claimed_algorithm in curves:
        curve, bits = curves[claimed_algorithm]
        return cert.get("key_type") == "EC" and cert.get("curve") == curve and cert.get("key_size") == bits
    if claimed_algorithm.startswith("RSA "):
        try:
            bits = int(claimed_algorithm.split()[1])
        except (IndexError, ValueError):
            return None
        return cert.get("key_type") == "RSA" and cert.get("key_size") == bits
    if claimed_algorithm in ("Ed25519", "Ed448"):
        return cert.get("key_type") == claimed_algorithm
    return None
