"""Test data shipped with the app: the vendored Project Wycheproof files and our fixed bad-signature
cases. Files are read as data with `json` only, and only if their SHA-256 matches the value pinned
here; a changed or missing file raises VectorFileChanged and the test does not run.
No verdict logic lives in this module."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import VECTORS_DIR


class VectorFileChanged(Exception):
    """The file is missing, unreadable, or its SHA-256 differs from the pinned value."""


@dataclass(frozen=True)
class Case:
    id: str
    comment: str
    flags: tuple[str, ...]
    public_key: str   # hex. ECDSA: uncompressed point (04 || X || Y). Ed25519: the raw 32 bytes.
    message: str      # hex
    signature: str    # hex
    expected: str     # "valid" (must be accepted) | "invalid" (must be rejected) | "acceptable" (either; not counted)


@dataclass(frozen=True)
class VectorSet:
    name: str
    path: Path
    sha256: str
    source: str
    cases: tuple[Case, ...]


WYCHEPROOF_COMMIT = "dab4ea2ed021eb633874959ca601004f3457d911"
WYCHEPROOF_SOURCE_URL = "https://github.com/C2SP/wycheproof/tree/dab4ea2ed021eb633874959ca601004f3457d911/testvectors_v1"
WYCHEPROOF = {
    "ecdsa_p256": {"file": "ecdsa_secp256r1_sha256_test.json",
                   "sha256": "182db4f3e230f6f9fa9f800d2a614dede30284b8e8438bbfe1171905402e9332", "cases": 484},
    "ed25519": {"file": "ed25519_test.json",
                "sha256": "ea80ffebac085e21cb9d3e903e7fa2b448d96702da5b31f061d0b83b430b74b3", "cases": 210},
}
BAD_SIGNATURES = {"file": "bad-signatures/cases.json",
                  "sha256": "d429e98c4618defad5761fad0129998a281943a3eec1092bfb9b7c7eac4dc216", "cases": 16}
BAD_SIGNATURE_IDS = ("good-1", "good-2", "changed-message", "changed-signature", "cut-short", "extra-byte", "empty",
                     "r0-s0", "r0", "s0", "r-equals-n", "s-equals-n", "s-plus-n", "r-plus-n", "extra-zero-padding",
                     "wrong-tag")
_RESULTS = ("valid", "invalid", "acceptable")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_pinned(path: Path, pinned: str) -> object:
    try:
        raw = path.read_bytes()
    except OSError:
        raise VectorFileChanged(f"The test data file {path.name} is missing.") from None
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise VectorFileChanged(f"The test data file {path.name} is not the pinned copy (its SHA-256 is different).")
    try:
        return json.loads(raw)
    except ValueError:  # cannot happen while the hash matches; kept so a bad pin never turns into a crash
        raise VectorFileChanged(f"The test data file {path.name} is not valid JSON.") from None


def load_wycheproof(which: str) -> VectorSet:
    """which: "ecdsa_p256" | "ed25519". Case ids are the file's tcId numbers as text (they are per file)."""
    pin = WYCHEPROOF[which]
    path = VECTORS_DIR / "wycheproof" / pin["file"]
    data = _read_pinned(path, pin["sha256"])
    key_field = "uncompressed" if which == "ecdsa_p256" else "pk"
    cases = []
    for group in data["testGroups"]:
        public_key = group["publicKey"][key_field]
        for t in group["tests"]:
            if t["result"] not in _RESULTS:
                raise VectorFileChanged(f"The test data file {path.name} has a result this version does not know.")
            cases.append(Case(str(t["tcId"]), t["comment"], tuple(t["flags"]), public_key, t["msg"], t["sig"], t["result"]))
    if len(cases) != pin["cases"] or len({c.id for c in cases}) != len(cases):
        raise VectorFileChanged(f"The test data file {path.name} does not hold the expected {pin['cases']} cases.")
    if which == "ecdsa_p256":
        headline = next(c for c in cases if c.id == "168")
        if "r=0 and s=0" not in headline.comment or headline.expected != "invalid" or headline.signature != "3006020100020100":
            raise VectorFileChanged(f"Case 168 in {path.name} is not the r=0, s=0 case.")
    return VectorSet(which, path, pin["sha256"], f"{WYCHEPROOF_SOURCE_URL}/{pin['file']}", tuple(cases))


def load_bad_signatures() -> VectorSet:
    """Our fixed bad-signature cases (ECDSA P-256). "valid" = must be accepted, "invalid" = must be rejected.
    `comment` is the plain description shown on screen."""
    path = VECTORS_DIR / BAD_SIGNATURES["file"]
    data = _read_pinned(path, BAD_SIGNATURES["sha256"])
    cases = tuple(Case(c["id"], c["what"], (), c["public_key"], c["message"], c["signature"], c["expected"])
                  for c in data["cases"])
    if tuple(c.id for c in cases) != BAD_SIGNATURE_IDS or any(c.expected not in ("valid", "invalid") for c in cases):
        raise VectorFileChanged(f"The test data file {path.name} does not hold the expected {BAD_SIGNATURES['cases']} cases.")
    return VectorSet("bad_signatures", path, BAD_SIGNATURES["sha256"], "built by backend/tools/build_bad_signature_cases.py", cases)
