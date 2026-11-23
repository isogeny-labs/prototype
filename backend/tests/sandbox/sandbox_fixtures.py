"""What the sandbox tests share: the pack and the lab files of one real run (tests/sandbox/fixtures), read as data."""

from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACK_FILE = FIXTURES / "pack-2026.11.3.json"
LAB = FIXTURES / "lab"
ADVISORY = "CVE-2021-43572"


def envelope() -> dict:
    return json.loads(PACK_FILE.read_text(encoding="utf-8"))


def raw_pack() -> bytes:
    return PACK_FILE.read_bytes().rstrip(b"\n")


def keys(made_here: bool = True) -> dict:
    """The key that signed the fixture pack, trusted the way a test wants it: as this computer's own, or as another's."""
    return {envelope()["public_key"]: ("A key made for a test run", made_here)}


def advisory() -> dict:
    return copy.deepcopy(envelope()["pack"]["advisories"][0])


def copy_set(author: str = "a") -> dict:
    path = next((LAB / "sandbox" / ADVISORY).glob(f"set-{author}-*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def lab_file(prefix: str) -> Path:
    folder = LAB / "designs" if prefix == "design" else LAB / "sandbox" / ADVISORY
    return next(folder.glob("*.json" if prefix == "design" else f"{prefix}-*.json"))
