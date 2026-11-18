"""A made-up snapshot about our own demo program, with answers written for the tests (they are test fixtures, not
answers from Claude), so the whole research loop can run in demo mode, with no Docker and no key."""
from __future__ import annotations

import json
from pathlib import Path

from app.otto import model
from ottolab import prompts, snapshot

HOW = "Written for a test, not an answer from Claude"
AT = "2026-11-17T12:00:00Z"
TEXT = ("acme-sign 1.4.2 and earlier accept an ECDSA signature whose two numbers are zero or out of range.\n"
        "The check was added in acme-sign 1.4.3.")


def _advisory(number: int) -> dict:
    return {"id": f"TEST-2026-000{number}", "aliases": [], "package": {"name": "acme-sign", "ecosystem": "demo"}, "published": "2026-11-01",
            "sources": [{"title": "A made-up advisory for a test", "publisher": "The test suite", "url": "https://example.com/advisory",
                         "fetched_from": "https://example.com/advisory", "fetched": "2026-11-17", "sha256": "0" * 64, "license": None,
                         "excerpts": [TEXT]}]}


SNAPSHOT = {"schema": snapshot.SCHEMA, "snapshot": "2026-11-17", "about": "A made-up snapshot for the tests.",
            "advisories": [_advisory(n) for n in (1, 2, 3, 4, 5, 6)]}

READING = {"plain_name": "Out-of-range signature accepted",
           "weakness": "The program accepts a signature whose two numbers are zero or outside the allowed range.",
           "weakness_quote": {"source": "S1", "text": "accept an ECDSA signature whose two numbers are zero or out of range"},
           "kind": "accepts_bad_signature", "area": "ecdsa_signature_check",
           "affected": {"versions": "1.4.2 and earlier", "quote": {"source": "S1", "text": "acme-sign 1.4.2 and earlier"}},
           "fixed": {"version": "1.4.3", "quote": {"source": "S1", "text": "The check was added in acme-sign 1.4.3."}},
           "notes": ""}


def _note(flags: list[str]) -> dict:
    return {"decision": "test", "block": "signature_cases", "control": "accept_all_verifier",
            "question": "Does {program} reject signatures whose numbers are zero or out of range?",
            "why": "Why it matters: a program that accepts them takes a forged signature for a genuine one.",
            "select": {"flags": flags}, "expect": "The affected version accepts the special-value cases."}


# What each made-up advisory's answers are: 1 a design that works, 2 a design that can't catch the affected version,
# 3 "no test fits", 4 a reading that quotes a line the publisher never wrote, 5 a design that selects exactly the
# cases of 1's check (the same library: the same check under a second name), 6 a design that selects exactly the cases
# of 2's design (which failed its trial and is no check, so 6 is tried in its own right).
NOTES = {1: _note(["InvalidSignature"]), 2: _note(["MissingZero"]),
         3: {"decision": "no_test", "reason": "The weakness is in a part of the program the building block cannot reach."},
         5: _note(["InvalidSignature"]), 6: _note(["MissingZero"])}
FIX = {"fix": "update", "version": "1.4.3", "quote": {"source": "S1", "text": "The check was added in acme-sign 1.4.3."},
       "summary": "Update acme-sign to 1.4.3, which checks that both numbers of a signature are in range."}
BAD_READING = {**READING, "weakness_quote": {"source": "S1", "text": "a line that is not in the advisory"}}


def write(folder: Path) -> Path:
    """Write the snapshot and every answer the loop will ask for. Returns the snapshot's path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "advisories.json"
    path.write_text(json.dumps(SNAPSHOT, indent=1), encoding="utf-8")
    recorded = folder / "recorded"
    for number, advisory in enumerate(SNAPSHOT["advisories"], 1):
        answer = json.dumps(BAD_READING if number == 4 else READING, indent=1)
        model.write_recorded(recorded, "read_advisory", prompts.read_advisory_prompt(advisory), answer, AT, HOW)
        if number == 4:
            continue
        reading = prompts.check_reading(answer, advisory)
        model.write_recorded(recorded, "design_test", prompts.design_test_prompt(advisory, reading), json.dumps(NOTES[number], indent=1), AT, HOW)
        if number == 1:
            model.write_recorded(recorded, "propose_fix", prompts.propose_fix_prompt(advisory, reading), "```json\n" + json.dumps(FIX, indent=1) + "\n```", AT, HOW)
    return path
