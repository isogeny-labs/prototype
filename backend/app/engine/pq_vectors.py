"""The official post-quantum test sets (phase 4c): NIST's ACVP files and Project Wycheproof's files for
ML-KEM-768 and ML-DSA-65, stored whole in demo/vectors/ and read as data, each only if its SHA-256 matches
the value pinned here. A changed or missing file raises VectorFileChanged and the test does not run.

Every case becomes one call of the adapter (docs/ADAPTER.md) and one expectation:
    "answer"  the library must give exactly the published answer (compared by fingerprint)
    "refuse"  the library must refuse the input (a bad key, a wrong length)
    "accept"  the library must not refuse it (a key check on a good key), or must say the signature is genuine
    "reject"  the library must say the signature is not genuine
No verdict logic lives in this module."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.config import VECTORS_DIR
from app.engine.vectors import VectorFileChanged, _read_pinned

WYCHEPROOF_PQ_COMMIT = "65ca494727a52944c204441c860b039e6786b99b"
WYCHEPROOF_PQ_URL = f"https://github.com/C2SP/wycheproof/tree/{WYCHEPROOF_PQ_COMMIT}/testvectors_v1"
ACVP_COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"
ACVP_URL = f"https://github.com/usnistgov/ACVP-Server/tree/{ACVP_COMMIT}/gen-val/json-files"
NIST, WYCHEPROOF = "NIST ACVP", "Wycheproof"

# name -> (folder, file, sha256, where it comes from)
FILES = {
    "acvp_mlkem_keygen": (
        "acvp",
        "ML-KEM-keyGen-FIPS203.json",
        "d7a62a2c3476957f56dd8d24f9004ea6776ccfe995ffe71a65bb9506dc9c7b1b",
        NIST,
    ),
    "acvp_mlkem_encapdecap": (
        "acvp",
        "ML-KEM-encapDecap-FIPS203.json",
        "a556952ce869bb89c3a3196a701dad89647c193a34c86eafb61a9d710d5b810f",
        NIST,
    ),
    "acvp_mldsa_keygen": (
        "acvp",
        "ML-DSA-keyGen-FIPS204.json",
        "e67ee6540d40e11506c3c4e3b1f79fc1cefcd49820db99fc61f87cc8ba463baf",
        NIST,
    ),
    "acvp_mldsa_siggen": (
        "acvp",
        "ML-DSA-sigGen-FIPS204.json",
        "72dcaf5f69853ca267ccd16af9cb40949786aca0fcfbf05d1ebeba132b93af22",
        NIST,
    ),
    "acvp_mldsa_sigver": (
        "acvp",
        "ML-DSA-sigVer-FIPS204.json",
        "47cdd6314c7f746d02421ffcba89d4dbc7bb875ac49e07a029fdfc26fba55437",
        NIST,
    ),
    "wp_mlkem_keygen": (
        "wycheproof",
        "mlkem_768_keygen_seed_test.json",
        "fde5abe284396f4cb3c4610b90d680f0b57782e94c3365c97aee59e24881ebe4",
        WYCHEPROOF,
    ),
    "wp_mlkem_encaps": (
        "wycheproof",
        "mlkem_768_encaps_test.json",
        "9d4381f94c40853bba430245b94968b7390d9175aacd9f1ae4e250a71c78b713",
        WYCHEPROOF,
    ),
    "wp_mlkem_decaps": (
        "wycheproof",
        "mlkem_768_test.json",
        "c59c067ae794c343df575dd90f6f7458f51881b11a22d6e9d8677c8d9ee21e90",
        WYCHEPROOF,
    ),
    "wp_mlkem_expanded": (
        "wycheproof",
        "mlkem_768_semi_expanded_decaps_test.json",
        "e4438ab7d4dd7b6ace7165e45aeed4403082f981f86300c8369f69d3d071060a",
        WYCHEPROOF,
    ),
    "wp_mldsa_sign": (
        "wycheproof",
        "mldsa_65_sign_seed_test.json",
        "e26b2bb9ab8d45ed570ba6828c7e40b6fa3e1545bb8bc2c449c77531760133e0",
        WYCHEPROOF,
    ),
    "wp_mldsa_verify": (
        "wycheproof",
        "mldsa_65_verify_test.json",
        "1ca235f61928421a173a171780beb00264ae9155dc33c52a11e1766cc7979034",
        WYCHEPROOF,
    ),
}
# The two exams: which files each reads, its parts in order (id, title, how many cases), and what is left out.
EXAMS = {
    "mlkem_vectors": {
        "algorithm": "ML-KEM-768",
        "files": (
            "acvp_mlkem_keygen",
            "acvp_mlkem_encapdecap",
            "wp_mlkem_keygen",
            "wp_mlkem_encaps",
            "wp_mlkem_decaps",
            "wp_mlkem_expanded",
        ),
        "parts": (("keygen", "Key generation", 125), ("encaps", "Encapsulate", 300), ("decaps", "Decapsulate", 230)),
        "left_out": 0,
    },
    "mldsa_vectors": {
        "algorithm": "ML-DSA-65",
        "files": ("acvp_mldsa_keygen", "acvp_mldsa_siggen", "acvp_mldsa_sigver", "wp_mldsa_sign", "wp_mldsa_verify"),
        "parts": (("keygen", "Key generation", 25), ("sign", "Sign", 195), ("verify", "Verify", 255)),
        "left_out": 45,
    },
}
# The fields of an answer that are fingerprinted, per adapter command (the batch driver uses the same table).
ANSWER_FIELDS = {
    "keygen": ("public_key", "private_key"),
    "encaps": ("ciphertext", "shared_secret"),
    "decaps": ("shared_secret",),
    "sign": ("signature",),
}
# Marks the controls are judged by: a public key with a number out of range, a private key with a wrong fingerprint.
KEY_OUT_OF_RANGE, KEY_HASH_WRONG = "KeyOutOfRange", "KeyHashWrong"
_HEX = set("0123456789abcdefABCDEF")
MAX_HEX = 40000


@dataclass(frozen=True)
class PQCase:
    id: str  # unique within its exam, for example "nist-encaps-26" or "wycheproof-verify-135"
    part: str  # "keygen" | "encaps" | "decaps" | "sign" | "verify"
    source: str  # NIST or WYCHEPROOF
    file: str
    comment: str
    flags: tuple[str, ...]
    command: str  # the adapter command that is called
    input: dict  # its input (hex text, and for ML-DSA: deterministic, interface)
    expect: str  # "answer" | "refuse" | "accept" | "reject"
    answer_sha256: str | None  # fingerprint of the published answer when expect == "answer"


def answer_sha256(command: str, fields: dict) -> str:
    """The fingerprint of an answer: SHA-256 over its fields in a fixed order, as lowercase hex text."""
    text = "\n".join(f"{name}={str(fields[name]).lower()}" for name in ANSWER_FIELDS[command])
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def holds_number_out_of_range(public_key_hex: object) -> bool:
    """Is this an ML-KEM-768 public key of the right length that holds a number at or above the modulus 3329? (FIPS 203
    requires such a key to be refused. A fact about the test data, read from the key itself: the first 1152 bytes are
    768 twelve-bit numbers.) This is how the cases the key-check control is judged on are found."""
    try:
        raw = bytes.fromhex(str(public_key_hex))
    except ValueError:
        return False
    if len(raw) != 1184:
        return False
    packed = int.from_bytes(raw[:1152], "little")
    return any(((packed >> (12 * i)) & 0xFFF) >= 3329 for i in range(768))


def _is_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) % 2 == 0 and len(value) <= MAX_HEX and all(c in _HEX for c in value)


def _load(name: str) -> tuple[dict, str, str, str]:
    folder, file, sha256, source = FILES[name]
    return _read_pinned(VECTORS_DIR / folder / file, sha256), file, sha256, source


def file_pins(exam: str) -> list[dict]:
    """The files of one exam as they are written into its locked test: name, fingerprint, source."""
    return [{"file": FILES[n][1], "sha256": FILES[n][2], "source": FILES[n][3]} for n in EXAMS[exam]["files"]]


def source_url(file: str) -> str:
    for folder, name, _, source in FILES.values():  # noqa: B007
        if name == file:
            return f"{ACVP_URL}/{name[:-5]}" if source == NIST else f"{WYCHEPROOF_PQ_URL}/{name}"
    raise KeyError(file)


class _Builder:
    def __init__(self, algorithm: str):
        self.algorithm, self.cases, self.unusable = algorithm, [], 0

    def add(self, part, source, file, number, comment, flags, command, given, expect, answer=None):
        given = {k: v for k, v in given.items() if v is not None}
        prefix = "nist" if source == NIST else "wycheproof"
        if not all(_is_hex(v) for k, v in given.items() if k not in ("deterministic", "interface")):
            # An input that is not even hex text can't be handed to any library through the adapter. The pinned
            # files hold none; if one ever did, the count check below would stop the exam.
            self.unusable += 1
            return
        self.cases.append(
            PQCase(
                f"{prefix}-{part}-{number}",
                part,
                source,
                file,
                str(comment or "")[:160],
                tuple(flags or ()),
                command,
                {"algorithm": self.algorithm, **given},
                expect,
                answer_sha256(command, answer) if answer is not None else None,
            )
        )


def _groups(data: dict, parameter_set: str):
    return [g for g in data["testGroups"] if g.get("parameterSet") == parameter_set]


def load_mlkem() -> tuple[PQCase, ...]:
    b = _Builder("ML-KEM-768")
    data, file, _, _ = _load("acvp_mlkem_keygen")
    for g in _groups(data, "ML-KEM-768"):
        for t in g["tests"]:
            b.add(
                "keygen",
                NIST,
                file,
                t["tcId"],
                "key pair from the published seed",
                (),
                "keygen",
                {"seed": t["d"] + t["z"]},
                "answer",
                {"public_key": t["ek"], "private_key": t["dk"]},
            )
    data, file, _, _ = _load("wp_mlkem_keygen")
    for g in data["testGroups"]:
        for t in g["tests"]:
            b.add(
                "keygen",
                WYCHEPROOF,
                file,
                t["tcId"],
                t.get("comment") or "key pair from the published seed",
                (),
                "keygen",
                {"seed": t["seed"]},
                "answer",
                {"public_key": t["ek"], "private_key": t["dk"]},
            )
    data, file, _, _ = _load("acvp_mlkem_encapdecap")
    zero_ciphertext = "00" * 1088
    for g in _groups(data, "ML-KEM-768"):
        function = g["function"]
        for t in g["tests"]:
            if function == "encapsulation":
                b.add(
                    "encaps",
                    NIST,
                    file,
                    t["tcId"],
                    "ciphertext and shared secret from the published randomness",
                    (),
                    "encaps",
                    {"public_key": t["ek"], "randomness": t["m"]},
                    "answer",
                    {"ciphertext": t["c"], "shared_secret": t["k"]},
                )
            elif function == "encapsulationKeyCheck":
                bad = not t["testPassed"]
                b.add(
                    "encaps",
                    NIST,
                    file,
                    t["tcId"],
                    "key check: " + t["reason"],
                    (KEY_OUT_OF_RANGE,) if bad and holds_number_out_of_range(t["ek"]) else (),
                    "encaps",
                    {"public_key": t["ek"]},
                    "refuse" if bad else "accept",
                )
            elif function == "decapsulation":
                b.add(
                    "decaps",
                    NIST,
                    file,
                    t["tcId"],
                    t["reason"],
                    (),
                    "decaps",
                    {"private_key": t["dk"], "ciphertext": t["c"]},
                    "answer",
                    {"shared_secret": t["k"]},
                )
            elif function == "decapsulationKeyCheck":
                bad = not t["testPassed"]
                b.add(
                    "decaps",
                    NIST,
                    file,
                    t["tcId"],
                    "key check: " + t["reason"],
                    (KEY_HASH_WRONG,) if bad else (),
                    "decaps",
                    {"private_key": t["dk"], "ciphertext": zero_ciphertext},
                    "refuse" if bad else "accept",
                )
    data, file, _, _ = _load("wp_mlkem_encaps")
    for g in data["testGroups"]:
        for t in g["tests"]:
            valid = t["result"] == "valid"
            flags = tuple(t.get("flags") or ()) + (
                (KEY_OUT_OF_RANGE,) if not valid and holds_number_out_of_range(t["ek"]) else ()
            )
            b.add(
                "encaps",
                WYCHEPROOF,
                file,
                t["tcId"],
                t.get("comment") or ("published answer" if valid else "a public key that must be refused"),
                flags,
                "encaps",
                {"public_key": t["ek"], "randomness": t["m"]},
                "answer" if valid else "refuse",
                {"ciphertext": t["c"], "shared_secret": t["K"]} if valid else None,
            )
    data, file, _, _ = _load("wp_mlkem_decaps")
    for g in data["testGroups"]:
        for t in g["tests"]:
            valid = t["result"] == "valid"
            b.add(
                "decaps",
                WYCHEPROOF,
                file,
                t["tcId"],
                t.get("comment") or ("published answer" if valid else "an input that must be refused"),
                t.get("flags"),
                "decaps",
                {"private_key": t["seed"], "ciphertext": t["c"]},
                "answer" if valid else "refuse",
                {"shared_secret": t["K"]} if valid else None,
            )
    data, file, _, _ = _load("wp_mlkem_expanded")
    for g in data["testGroups"]:
        for t in g["tests"]:
            valid = t["result"] == "valid"
            flags = tuple(t.get("flags") or ()) + (
                (KEY_HASH_WRONG,) if "corrupted hash" in str(t.get("comment")) else ()
            )
            b.add(
                "decaps",
                WYCHEPROOF,
                file,
                f"x{t['tcId']}",
                t.get("comment"),
                flags,
                "decaps",  # "x": the expanded-key file
                {"private_key": t["dk"], "ciphertext": t["c"]},
                "answer" if valid else "refuse",
                {"shared_secret": t["K"]} if valid else None,
            )
    return _checked("mlkem_vectors", b)


def load_mldsa() -> tuple[PQCase, ...]:
    b = _Builder("ML-DSA-65")
    data, file, _, _ = _load("acvp_mldsa_keygen")
    for g in _groups(data, "ML-DSA-65"):
        for t in g["tests"]:
            b.add(
                "keygen",
                NIST,
                file,
                t["tcId"],
                "key pair from the published seed",
                (),
                "keygen",
                {"seed": t["seed"]},
                "answer",
                {"public_key": t["pk"], "private_key": t["sk"]},
            )

    def interface(
        g,
    ):  # which form of the message the case signs: the message itself, the inner form, or a ready-made digest (mu)
        if g.get("externalMu"):
            return "mu"
        return "internal" if g.get("signatureInterface") == "internal" else "external"

    left_out = 0
    data, file, _, _ = _load("acvp_mldsa_siggen")
    for g in _groups(data, "ML-DSA-65"):
        if g.get("preHash") == "preHash":  # HashML-DSA, the pre-hash variant: not part of this exam
            left_out += len(g["tests"])
            continue
        for t in g["tests"]:
            b.add(
                "sign",
                NIST,
                file,
                t["tcId"],
                f"published signature ({interface(g)} interface, {'fixed' if g['deterministic'] else 'given'} randomness)",
                (),
                "sign",
                {
                    "private_key": t["sk"],
                    "message": t.get("mu") if g.get("externalMu") else t["message"],
                    "context": t.get("context") or None,
                    "randomness": t.get("rnd"),
                    "deterministic": True if g["deterministic"] else None,
                    "interface": interface(g),
                },
                "answer",
                {"signature": t["signature"]},
            )
    data, file, _, _ = _load("acvp_mldsa_sigver")
    for g in _groups(data, "ML-DSA-65"):
        if g.get("preHash") == "preHash":
            left_out += len(g["tests"])
            continue
        for t in g["tests"]:
            b.add(
                "verify",
                NIST,
                file,
                t["tcId"],
                t["reason"],
                (),
                "verify",
                {
                    "public_key": t["pk"],
                    "message": t.get("mu") if g.get("externalMu") else t["message"],
                    "signature": t["signature"],
                    "context": t.get("context") or None,
                    "interface": interface(g),
                },
                "accept" if t["testPassed"] else "reject",
            )
    data, file, _, _ = _load("wp_mldsa_sign")
    for g in data["testGroups"]:
        for t in g["tests"]:
            valid, internal = t["result"] == "valid", "Internal" in (t.get("flags") or ())
            b.add(
                "sign",
                WYCHEPROOF,
                file,
                t["tcId"],
                t.get("comment"),
                t.get("flags"),
                "sign",
                {
                    "private_key": g["privateSeed"],
                    "message": t["mu"] if internal else t["msg"],
                    "context": None if internal else (t.get("ctx") or None),
                    "randomness": t.get("rnd"),
                    "deterministic": None if t.get("rnd") else True,
                    "interface": "mu" if internal else "external",
                },
                "answer" if valid else "refuse",
                {"signature": t["sig"]} if valid else None,
            )
    data, file, _, _ = _load("wp_mldsa_verify")
    for g in data["testGroups"]:
        for t in g["tests"]:
            b.add(
                "verify",
                WYCHEPROOF,
                file,
                t["tcId"],
                t.get("comment"),
                t.get("flags"),
                "verify",
                {
                    "public_key": g["publicKey"],
                    "message": t["msg"],
                    "signature": t["sig"],
                    "context": t.get("ctx") or None,
                    "interface": "external",
                },
                "accept" if t["result"] == "valid" else "reject",
            )
    if left_out != EXAMS["mldsa_vectors"]["left_out"]:
        raise VectorFileChanged("The NIST ML-DSA files do not hold the expected number of pre-hash cases.")
    return _checked("mldsa_vectors", b)


def _checked(exam: str, b: _Builder) -> tuple[PQCase, ...]:
    cases = tuple(b.cases)
    counts = {part: sum(1 for c in cases if c.part == part) for part, _, _ in EXAMS[exam]["parts"]}
    if (
        b.unusable
        or len({c.id for c in cases}) != len(cases)
        or any(counts[part] != n for part, _, n in EXAMS[exam]["parts"])
    ):
        raise VectorFileChanged("The official post-quantum test files do not hold the expected cases.")
    return cases


def load(exam: str) -> tuple[PQCase, ...]:
    """exam: "mlkem_vectors" | "mldsa_vectors"."""
    return load_mlkem() if exam == "mlkem_vectors" else load_mldsa()
