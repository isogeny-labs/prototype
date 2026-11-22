"""Helpers for the Watch list tests: a folder of recorded answers that stands in for the public source, made from the
real published records kept in demo/sandbox/advisories, and from changed copies of them that a test writes to play a
later day (a fix is published, the record is withdrawn). The changed copies are made up for the tests."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from conftest import csv_bytes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sandbox"))
from sandbox_helpers import sandbox_lab, turn_on  # noqa: E402

from app.config import DEMO_DIR  # noqa: E402

RECORDS = DEMO_DIR / "sandbox" / "advisories"
NO_FIX = "GHSA-wj6h-64fc-37mp"            # CVE-2024-23342, python-ecdsa: "introduced": "0" and no end
ITEM = "CVE-2024-23342~python-ecdsa"
ECDSA_ONLY = ("python-ecdsa 0.13.2,software,signature_algorithm,ECDSA P-256",)


def record(name: str = NO_FIX) -> dict:
    return json.loads((RECORDS / f"{name}.json").read_text(encoding="utf-8"))


def with_events(base: dict, events: list[dict], **changes) -> dict:
    """A copy of a record whose first range has these events (made up for a test: a later day at the source)."""
    made = copy.deepcopy(base)
    made["affected"][0]["ranges"][0]["events"] = events
    made.update(changes)
    return made


def write_source(folder: Path, records: list[dict], name: str = "PyPI__ecdsa") -> Path:
    """What the source answers about one package from now on."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({"vulns": records}), encoding="utf-8")
    return folder


def watch_lab(tmp_path, monkeypatch, records: list[dict] | None = None, on: bool = True, claims=ECDSA_ONLY, **overrides):
    """A started lab with Sandbox research on (stand-ins for the mode and the harness), a recorded source that answers
    with the real no-fix record about python-ecdsa, and a file that names python-ecdsa 0.13.2. Returns (lab, plan id,
    the source folder)."""
    folder = write_source(tmp_path / "source", [record()] if records is None else records)
    lab = sandbox_lab(tmp_path, monkeypatch, advisory_source_dir=folder, **overrides)
    if on:
        turn_on(lab)
    imp = lab.import_file("libraries.csv", csv_bytes(*claims))
    return lab, lab.ensure_plan(imp["id"])["id"], folder


def rows(view: dict) -> dict[str, dict]:
    return {r["key"]: r for r in [*view["items"], *view["stopped"]]}
