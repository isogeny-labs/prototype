"""Builds demo/vectors/bad-signatures/cases.json, the fixed case list of the bad-signature test.

Kept for transparency. The app never runs this. It was run ONCE; every run makes a fresh throwaway
test key (never written anywhere, gone when the script ends), so running it again would produce a
different file whose SHA-256 no longer matches the value pinned in backend/app/vectors.py.

    cd backend && .venv/bin/python tools/build_bad_signature_cases.py [output file]

Without an output file it only prints the case ids (it never overwrites the shipped file by default).
"""
from __future__ import annotations

import json
import sys

import cryptography
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def der_int(value: int, extra_zero: bool = False) -> bytes:
    raw = value.to_bytes((value.bit_length() + 8) // 8 or 1, "big")  # minimal, non-negative
    if extra_zero:
        raw = b"\x00" + raw
    return b"\x02" + bytes([len(raw)]) + raw


def der(r: int, s: int, tag: int = 0x30, pad_r: bool = False) -> bytes:
    body = der_int(r, pad_r) + der_int(s)
    return bytes([tag, len(body)]) + body


def build() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())  # throwaway test key: used below, never stored or printed
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint).hex()
    message_1 = b"Acme Pay demo token 0001: pay 10.00 to account 12345"
    message_2 = b"Acme Pay demo token 0002: pay 25.50 to account 67890"
    changed = b"Acme Pay demo token 0001: pay 90.00 to account 12345"
    while True:  # a first signature whose r has room for a leading zero and whose s + n still fits
        good_1 = key.sign(message_1, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(good_1)
        if good_1 == der(r, s) and len(der_int(r)) == 34 and len(der_int(s + N)) <= 35 and len(der(r, s + N)) < 128:
            break
    good_2 = key.sign(message_2, ec.ECDSA(hashes.SHA256()))
    del key
    flipped = bytearray(good_1)
    flipped[-1] ^= 0x01

    def case(case_id: str, what: str, signature: bytes, expected: str = "invalid", message: bytes = message_1) -> dict:
        return {"id": case_id, "what": what, "public_key": public, "message": message.hex(),
                "signature": signature.hex(), "expected": expected}

    return {
        "schema": "isogeny.bad-signatures/1",
        "algorithm": "ECDSA P-256 with SHA-256",
        "built_with": f"cryptography {cryptography.__version__}",
        "note": ("Test data only. Built once from a throwaway test key that was never stored. "
                 "Two genuine signatures that must be accepted and fourteen bad ones that must be rejected."),
        "cases": [
            case("good-1", "a genuine signature", good_1, "valid"),
            case("good-2", "a second genuine signature, on another message", good_2, "valid", message_2),
            case("changed-message", "a genuine signature, but the message was changed afterwards", good_1, message=changed),
            case("changed-signature", "a genuine signature with one bit changed", bytes(flipped)),
            case("cut-short", "a signature with its last byte cut off (wrong length)", good_1[:-1]),
            case("extra-byte", "a signature with one extra byte on the end (wrong length)", good_1 + b"\x00"),
            case("empty", "an empty signature", b""),
            case("r0-s0", "r = 0, s = 0", der(0, 0)),
            case("r0", "r = 0, with a genuine s", der(0, s)),
            case("s0", "s = 0, with a genuine r", der(r, 0)),
            case("r-equals-n", "r equal to the curve order n", der(N, s)),
            case("s-equals-n", "s equal to the curve order n", der(r, N)),
            case("s-plus-n", "a genuine signature with the curve order n added to s (s above the allowed range)", der(r, s + N)),
            case("r-plus-n", "a genuine signature with the curve order n added to r (r above the allowed range)", der(r + N, s)),
            case("extra-zero-padding", "a genuine signature with a needless extra zero byte in front of r (broken encoding)",
                 der(r, s, pad_r=True)),
            case("wrong-tag", "a genuine signature with the wrong type marker at the start (broken encoding)", der(r, s, tag=0x31)),
        ],
    }


if __name__ == "__main__":
    built = build()
    if len(sys.argv) == 2:
        with open(sys.argv[1], "x", encoding="utf-8") as handle:  # "x": refuses to overwrite an existing file
            json.dump(built, handle, indent=1)
            handle.write("\n")
    print("\n".join(c["id"] for c in built["cases"]))
