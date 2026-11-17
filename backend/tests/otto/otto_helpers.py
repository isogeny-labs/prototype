"""Shared by the Otto tests: a design made the way a pack makes one, and its check put into a plan."""
from __future__ import annotations

from app.db import PlanItemRow
from app.engine import research
from app.otto import designs

STEP = {"prompt_sha256": "a" * 64, "answer_sha256": "b" * 64}
PACK = {"version": "2026.11.1", "fingerprint": "c" * 64}
ADVISORY = {"plain_name": "Blank signature accepted",
            "quote": "ECDSA signatures with r = 0 and s = 0 are accepted.",
            "source": {"title": "OpenJDK advisory, 19 April 2022", "url": "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
                       "published": "2022-04-19", "checked": "2026-11-17"}}


def note(flags=("InvalidSignature",), ids=(), **more) -> dict:
    """A design note as a model writes one."""
    select = {k: list(v) for k, v in (("flags", flags), ("ids", ids)) if v}
    return {"decision": "test", "block": "signature_cases", "control": "accept_all_verifier",
            "question": "Does {program} reject the signatures that advisory CVE-2022-21449 describes?",
            "why": "Why it matters: a program that accepts these signatures takes a forged one for genuine.",
            "select": select, **more}


def design(flags=("InvalidSignature",), ids=(), advisory_id="CVE-2022-21449", plain_name="Blank signature accepted") -> dict:
    return designs.compile_note(note(flags, ids), advisory_id, plain_name, STEP)


def spec_for(lab, plan_id: int, made: dict, program_ref: str | None = None) -> dict:
    """The locked test of this design for one signing program of the plan's file (the first one by default)."""
    with lab.db() as db:
        from app.db import ImportRow, PlanRow
        claims = lab._claims(db.get(ImportRow, db.get(PlanRow, plan_id).import_id))
    program = next(p for p in research.programs(claims) if program_ref is None or p["ref"] == program_ref)
    target = {"component": program["component"], "algorithm": program["algorithm"], "claim": program["ref"]}
    return designs.spec_for(made, PACK, target, ADVISORY)


def add_check(lab, plan_id: int, made: dict, program_ref: str | None = None) -> int:
    """Lock the check and put it in the plan, the way Add new checks does (without Otto's ledger): returns the plan item id."""
    spec = spec_for(lab, plan_id, made, program_ref)
    with lab._plan_lock, lab.db() as db:
        last = max([i.position for i in lab._items(db, plan_id, include_removed=True)], default=-1)
        item = PlanItemRow(plan_id=plan_id, spec_hash=lab._lock_spec(db, spec, proposed_by=designs.PROPOSED_BY), position=last + 1,
                           origin="added", removed=False)
        db.add(item)
        db.commit()
        return item.id


def result_for(lab, plan_id: int, item_id: int, which: str = "result") -> dict:
    return next(r for r in lab.lab_view(plan_id)["rows"] if r["item_id"] == item_id)[which]


# ---------------------------------------------------------------- a signed pack made for a test (no research loop)

import hashlib  # noqa: E402
import json  # noqa: E402

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app.canonical import canonical_bytes, sha256_hex  # noqa: E402
from app.otto import harness, packs  # noqa: E402

RID = "sha256:" + "1" * 64
SIGNER = "A key made for a test"


def _step(name: str, answer: str = '{"made": "for a test"}') -> dict:
    return {"step": name, "source": "recorded", "model": None, "prompt_sha256": "a" * 64, "answer": answer,
            "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(), "input_tokens": 0, "output_tokens": 0, "cost_nano_usd": 0,
            "at": "2026-11-17T12:00:00Z", "how": "Written for a test, not an answer from Claude", "outcome": "used", "refusal": None, "claim": RID}


def pack_advisory(advisory_id: str = "CVE-2022-21449", name: str = "Blank signature accepted", package: str = "acme-sign",
                  flags=("InvalidSignature",), ids=(), state: str = "ready", fix_state: str = "proven",
                  versions: tuple[str, str] = ("1.4.2", "1.4.3")) -> tuple[dict, dict | None]:
    """One advisory as a pack holds it, with made-up trial figures: (the entry, its design when the test is ready)."""
    made = design(flags, ids, advisory_id, name) if state != "none" else None
    total = len(made["cases"]["ids"]) if made else 0
    quote = {"source": "S1", "text": "accepts a signature whose two numbers are zero"}
    reading = {"plain_name": name, "weakness": "The program accepts a signature whose two numbers are zero or out of range.",
               "weakness_quote": quote, "kind": "accepts_bad_signature", "area": "ecdsa_signature_check",
               "affected": {"versions": f"{versions[0]} and earlier", "quote": quote},
               "fixed": {"version": versions[1], "quote": quote}, "notes": ""}

    def arms(wrong_affected: int) -> dict:
        def one(version: str, wrong: int) -> dict:
            return {"library": package, "version": version, "right": total - wrong, "wrong": wrong, "total": total}
        return {"reference": one(versions[1], 0), "affected": one(versions[0], wrong_affected), "fixed": one(versions[1], 0),
                "accept-all": one(versions[1], made["cases"]["must_reject"] if made else 0)}
    test = {"state": state, "reason": {"ready": "Test ready: tried on public copies before this pack was signed.",
                                       "not_offered": "Not offered: the design failed its own trial.",
                                       "none": "No test yet: no building block can show this weakness."}[state],
            "design_sha256": designs.design_sha256(made) if made else None,
            "trial": ({"hypothesis": RID, "decision": RID, "outcome": "supported" if state == "ready" else "refuted", "replayed": True,
                       "arms": arms(2 if state == "ready" else 0)} if made else None)}
    if state != "ready" or fix_state == "none":
        fix = {"state": "none", "reason": "No fix is offered: there is no test for this advisory to prove one with.", "kind": None,
               "library": None, "version": None, "quote": None, "summary": None, "trial": None}
    else:
        failing = 0 if fix_state == "proven" else 1
        fix = {"state": fix_state, "kind": "update", "library": package, "version": versions[1], "quote": quote,
               "summary": f"Update {package} to {versions[1]}, which checks that both numbers of a signature are in range.",
               "reason": ("Proven on public copies: this advisory's check passed and all 3 pass-or-fail tests read Passed." if fix_state == "proven"
                          else "Not proven: on public copies 1 of 3 pass-or-fail tests still did not pass."),
               "trial": {"hypothesis": RID, "decision": RID, "outcome": "supported" if fix_state == "proven" else "refuted", "replayed": True,
                         "arms": {"affected": {"version": versions[0], "failing": 3, "tests": 3},
                                  "fixed": {"version": versions[1], "failing": failing, "tests": 3},
                                  "affected-again": {"version": versions[0], "failing": 3, "tests": 3}}}}
    entry = {"id": advisory_id, "aliases": [], "package": {"name": package, "ecosystem": "demo"}, "published": "2026-11-01",
             "sources": [{"label": "S1", "title": "A made-up advisory for a test", "publisher": "The test suite",
                          "url": "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
                          "read_from": "https://openjdk.org/groups/vulnerability/advisories/2022-04-19", "fetched": "2026-11-17"}],
             "reading": reading, "reading_refused": None, "test": test, "fix": fix,
             "steps": [_step("read_advisory"), _step("design_test")] + ([_step("propose_fix")] if fix["kind"] else []),
             "ledger": [{"seq": 0, "kind": "question", "id": RID, "at": "2026-11-17T12:00:00+00:00", "what": "Question asked: a test"}]}
    return entry, (made if state == "ready" else None)


def make_pack(version: str, previous: str | None, entries: list[tuple[dict, dict | None]], key: Ed25519PrivateKey | None = None) -> tuple[bytes, str]:
    """A signed pack file for a test: (its bytes, the signer's public key in hex)."""
    key = key or Ed25519PrivateKey.generate()
    lock = harness.read_lock()
    pack = {"schema": packs.PACK_SCHEMA, "version": version, "built_at": "2026-11-17T12:00:00Z", "previous": previous, "signer": SIGNER,
            "research": {"snapshot": "2026-11-17", "snapshot_sha256": "0" * 64, "answers": "recorded",
                         "answers_note": "Answers written for a test, 17 November 2026"},
            "otto": {"repository": lock.repository, "commit": lock.commit, "version": lock.version,
                     "ledger": {"height": 1, "head": RID, "root": RID}, "scripts": {"trial.py": "0" * 64}},
            "advisories": [entry for entry, _ in entries],
            "tests": [{"design": made, "design_sha256": designs.design_sha256(made)} for _, made in entries if made is not None]}
    return sign_pack(pack, key), public_hex(key)


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def sign_pack(pack: object, key: Ed25519PrivateKey) -> bytes:
    """Sign this content exactly as it is, whatever it holds (for tests of what a signed pack may hold)."""
    fingerprint = sha256_hex(pack)
    envelope = {"pack": pack, "fingerprint": fingerprint, "public_key": public_hex(key),
                "signature": key.sign(packs.SIGNING_CONTEXT + fingerprint.encode("ascii")).hex()}
    return canonical_bytes(envelope)


def trust(monkeypatch, tmp_path, public_keys: list[str]) -> None:
    """Make this installation trust these pack keys (the app's own key list is replaced for the test)."""
    path = tmp_path / "trusted-pack-keys.json"
    path.write_text(json.dumps({"schema": packs.KEYS_SCHEMA, "keys": [{"public_key": k, "label": SIGNER} for k in public_keys]}))
    monkeypatch.setattr(packs, "TRUSTED_KEYS_FILE", path)


def lab_with_packs(tmp_path, monkeypatch, files: dict[str, bytes], keys: list[str], **overrides):
    """A started demo-mode Lab whose updates folder holds these pack files and which trusts these keys."""
    from conftest import make_lab
    updates = tmp_path / "updates"
    updates.mkdir(exist_ok=True)
    for name, data in files.items():
        (updates / name).write_bytes(data)
    trust(monkeypatch, tmp_path, keys)
    return make_lab(tmp_path, otto_updates_dir=updates, otto_recorded_dir=tmp_path / "recorded", **overrides)
