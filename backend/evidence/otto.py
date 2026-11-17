"""The Otto part of an evidence file (phase 5c), checked after the file's own signature held.

In order:
  1. every test pack in the file is whole (its fingerprint matches) and its signature holds, and its signer is a
     pack key you trust: the keys shipped with the app, this computer's own pack key, or one given with --pack-key;
  2. every advisory check names a pack that is in the file, its design is in that pack and matches its SHA-256, its
     locked test matches its fingerprint and names that design and that pack, and its lock entry is in the ledger
     with the same three fingerprints;
  3. the ledger is one unbroken hash chain, written exactly as Otto writes it, and its latest entry is the one the
     signed evidence names (so the evidence signature covers the whole ledger);
  4. every run the ledger binds is in the file with its record and its review, both matching the SHA-256 the ledger
     holds, bound to a lock entry of one of the file's checks, and accepted by the pinned checker; every run of an
     advisory check that the file holds is bound in the ledger (a run that never started because Otto was not
     installed is the one exception: it could not be recorded, and it says so); every Claude step in the file
     matches its SHA-256 and has its entry in the ledger;
  5. with --previous OLDER.json: the older file's latest ledger entry is still in this chain, at the same place, so
     the history the older file held was not cut or rewritten. Entries added after the older download are not
     covered by this comparison;
  6. Otto's own audit of the ledger, with the pinned record checker run again on every entry. This needs the pinned
     Otto harness on this computer. Without it, steps 1 to 5 are still made, the command says that Otto's own audit
     was not run, and it ends with the "not confirmed" code. That is not a pass.

What the ledger shows is binding: that each run belongs to a test locked before it and that the reviewer was not the
proposer. It holds no result.

This module reads the file as data only. Otto's audit runs the verifier each ledger entry names, so the ledger is
handed to it only after `assurance.only_our_checker` found that it names nothing to run but this app's own pinned
record checker. A ledger that names anything else fails here, and nothing is run.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.canonical import canonical_bytes, loads_strict

PACK_CONTEXT = b"isogeny-evidence-lab/test-pack/v1\n"
OTTO_SCHEMA = "isogeny.otto-evidence/1"
SHIPPED_KEYS_FILE = Path(__file__).resolve().parents[1] / "app" / "otto" / "trusted-pack-keys.json"
LOCAL_KEY_FILE = "otto-local-pack-key.pub"
PACK_ID = "isogeny.otto-pack/1"
NOT_RECORDED_REASON = "otto_not_installed"      # the reviewer's reason for an advisory check that could not start without Otto
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_HEX128 = re.compile(r"\A[0-9a-f]{128}\Z")
OK, FAILED, NOT_CONFIRMED = 0, 1, 2


@dataclass
class OttoOutcome:
    code: int = OK
    lines: list[str] = field(default_factory=list)       # what was checked, one plain line each
    problem: str | None = None                           # why it failed, or what could not be confirmed


class _Failed(Exception):
    pass


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _record_id(obj: object) -> str:
    return "sha256:" + _sha(obj)


def pack_keys(data_dir: Path | None, extra: list[str] | None = None) -> set[str]:
    """The pack signing keys you trust: the ones shipped with the app, this computer's own, and any given by hand."""
    keys = {k.lower() for k in extra or [] if _HEX64.match(k.lower())}
    try:
        shipped = json.loads(SHIPPED_KEYS_FILE.read_text(encoding="utf-8"))
        keys |= {str(k.get("public_key")) for k in shipped.get("keys") or [] if isinstance(k, dict) and _HEX64.match(str(k.get("public_key")))}
    except (OSError, ValueError, AttributeError):
        pass
    if data_dir is not None:
        try:
            local = (Path(data_dir) / LOCAL_KEY_FILE).read_text(encoding="ascii").strip()
            if _HEX64.match(local):
                keys.add(local)
        except (OSError, ValueError):
            pass
    return keys


def _chain(lines: object) -> list[dict]:
    """The ledger's entries, if the lines are one unbroken chain written exactly as Otto writes it."""
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        raise _Failed("the ledger in the file is not a list of lines.")
    entries, prev = [], None
    for number, raw in enumerate(lines):
        try:
            entry = loads_strict(raw.encode("utf-8"))
        except ValueError:
            raise _Failed(f"ledger line {number + 1} is not valid JSON.") from None
        if not isinstance(entry, dict) or set(entry) != {"seq", "prev", "kind", "payload", "ts", "hash"}:
            raise _Failed(f"ledger line {number + 1} does not have the parts of a ledger entry.")
        if canonical_bytes(entry).decode("utf-8") != raw:
            raise _Failed(f"ledger line {number + 1} is not written exactly as the ledger writes it.")
        if entry["seq"] != number or entry["prev"] != prev:
            raise _Failed(f"the ledger's chain is broken at line {number + 1}: an entry was removed, added or moved.")
        if entry["hash"] != _record_id({k: entry[k] for k in ("seq", "prev", "kind", "payload", "ts")}):
            raise _Failed(f"ledger line {number + 1} was changed after it was written (its hash does not match).")
        prev = entry["hash"]
        entries.append(entry)
    return entries


def _pack(envelope: object, trusted: set[str]) -> tuple[dict, str, bool]:
    """(the pack's content, its fingerprint, is its signer trusted?) if the pack is whole and its signature holds."""
    if not isinstance(envelope, dict) or set(envelope) != {"pack", "fingerprint", "public_key", "signature"}:
        raise _Failed("a test pack in the file does not have the four parts of a signed pack.")
    fingerprint, key, signature = envelope["fingerprint"], envelope["public_key"], envelope["signature"]
    if not (isinstance(fingerprint, str) and _HEX64.match(fingerprint) and isinstance(key, str) and _HEX64.match(key)
            and isinstance(signature, str) and _HEX128.match(signature)) or not isinstance(envelope["pack"], dict):
        raise _Failed("a test pack in the file has a fingerprint, key or signature that is not in the form it must have.")
    if _sha(envelope["pack"]) != fingerprint:
        raise _Failed(f"test pack {envelope['pack'].get('version')} was changed after it was signed (its fingerprint does not match).")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(bytes.fromhex(signature), PACK_CONTEXT + fingerprint.encode("ascii"))
    except (InvalidSignature, ValueError):
        raise _Failed(f"the signature of test pack {envelope['pack'].get('version')} does not hold.") from None
    return envelope["pack"], fingerprint, key in trusted


def _runs_in_file(evidence: dict) -> list[tuple[object, dict]]:
    """Every reviewed run of a test that the file holds, as (the test's plan item id, the run): the runs shown for each
    test, its earlier runs, and the runs of every fix proof."""
    out: list[tuple[object, dict]] = []
    for test in evidence.get("tests") or []:
        if isinstance(test, dict):
            for run in list(test.get("runs") or []) + list(test.get("earlier_runs") or []):
                if isinstance(run, dict):
                    out.append((test.get("item_id"), run))

    def proofs(value: object) -> None:           # a fix's proofs hold one row per test, each with its proof run
        if isinstance(value, dict):
            if "item_id" in value and isinstance(value.get("run"), dict):
                out.append((value["item_id"], value["run"]))
            for inner in value.values():
                proofs(inner)
        elif isinstance(value, list):
            for inner in value:
                proofs(inner)
    proofs(evidence.get("fixes"))
    return out


def check_otto(evidence: dict, trusted_pack_keys: set[str], previous: dict | None = None) -> OttoOutcome:
    """Check the Otto part of an evidence record whose own signature already held. `previous` is the evidence record
    of an older download of the same assessment (or None)."""
    out = OttoOutcome()
    otto = evidence.get("otto")
    try:
        if not isinstance(otto, dict) or otto.get("schema") != OTTO_SCHEMA:
            raise _Failed("the Otto part of the file is not in the form this version knows.")
        # 1. the packs
        packs, untrusted = {}, []
        for envelope in otto.get("packs") or []:
            pack, fingerprint, trusted = _pack(envelope, trusted_pack_keys)
            packs[fingerprint] = pack
            if not trusted:
                untrusted.append(str(pack.get("version")))
        out.lines.append(f"Test packs: {len(packs)} in the file, each whole and with a signature that holds"
                         + (" from a pack key you trust." if not untrusted else "."))
        # 3. the chain (needed by 2 and 4)
        ledger = otto.get("ledger") or {}
        entries = _chain(ledger.get("lines"))
        head = entries[-1]["hash"] if entries else None
        if ledger.get("height") != len(entries) or ledger.get("head") != head:
            raise _Failed("the ledger's lines are not the ledger the signed evidence names (its latest entry or its length differs).")
        records = {_record_id(e["payload"]): e for e in entries}
        objectives = {rid: e["payload"] for rid, e in records.items() if e["kind"] == "objective"}
        claims = {rid: e["payload"] for rid, e in records.items() if e["kind"] == "claim"}
        accepted = {e["payload"].get("claim_id") for e in entries if e["kind"] == "verdict" and e["payload"].get("status") == "accept"}
        # 2. the checks
        checks = otto.get("checks") or []
        locks = set()
        for check in checks:
            title = str(check.get("title"))
            came_from = packs.get(check.get("pack_fingerprint"))
            if came_from is None:
                raise _Failed(f"the pack that “{title}” came from is not in the file.")
            design = next((t.get("design") for t in came_from.get("tests") or [] if t.get("design_sha256") == check.get("design_sha256")), None)
            if design is None or _sha(design) != check.get("design_sha256"):
                raise _Failed(f"the design of “{title}” is not in its test pack.")
            spec = check.get("spec")
            if not isinstance(spec, dict) or _sha(spec) != check.get("spec_hash"):
                raise _Failed(f"the locked test of “{title}” does not match its fingerprint.")
            named = ((spec.get("inputs") or {}).get("advisory") or {})
            if named.get("design_sha256") != check.get("design_sha256") or named.get("pack_fingerprint") != check.get("pack_fingerprint") \
                    or (spec.get("inputs") or {}).get("cases") != (design.get("cases") or {}).get("ids"):
                raise _Failed(f"the locked test of “{title}” does not name its design and its pack.")
            lock = objectives.get(check.get("lock_entry"))
            params = ((lock or {}).get("verifier") or {}).get("params") or {}
            if (params.get("test"), params.get("design"), params.get("pack")) != (check.get("spec_hash"), check.get("design_sha256"), check.get("pack_fingerprint")):
                raise _Failed(f"the lock entry of “{title}” is not in the ledger with the same fingerprints.")
            locks.add(check.get("lock_entry"))
        out.lines.append(f"Advisory checks: {len(checks)}, each with its design in its pack and its lock entry in the ledger.")
        # 4. the bound runs and the Claude steps
        run_claims = {rid: c for rid, c in claims.items() if isinstance(c.get("artifact"), dict) and "run_id" in c["artifact"]}
        shown = {r.get("ledger_entry"): r for r in otto.get("runs") or [] if isinstance(r, dict)}
        for rid, claim in run_claims.items():
            art, run = claim["artifact"], shown.get(rid)
            if claim.get("objective_id") not in locks:
                raise _Failed("the ledger binds a run to a lock entry that is not one of the file's advisory checks.")
            if run is None:
                raise _Failed(f"the ledger binds run {art.get('run_id')}, and that run is not in the file.")
            review = {k: v for k, v in (run.get("review") or {}).items() if k != "created_at"}
            if _sha(run.get("record")) != art.get("run_sha256") or _sha(review) != art.get("review_sha256"):
                raise _Failed(f"run {art.get('run_id')} or its review is not the one the ledger binds (a SHA-256 differs).")
            lock_params = objectives[claim["objective_id"]]["verifier"]["params"]
            if (run.get("record") or {}).get("spec_hash") != lock_params.get("test") or art.get("test") != lock_params.get("test"):
                raise _Failed(f"run {art.get('run_id')} is not a run of the test its lock entry locked.")
            if art.get("proposed_by") != PACK_ID or not art.get("reviewer") or art.get("reviewer") == art.get("proposed_by"):
                raise _Failed(f"run {art.get('run_id')} was not reviewed by someone other than its proposer.")
            if rid not in accepted:
                raise _Failed(f"the ledger entry of run {art.get('run_id')} was not accepted by the pinned checker.")
        if set(shown) - set(run_claims):
            raise _Failed("the file lists a run as bound that the ledger does not bind.")
        # ... and the other way round: every run of an advisory check that the file holds is bound in the ledger
        bound_runs = {art.get("run_id") for art in (c["artifact"] for c in run_claims.values())}
        titles = {check.get("item_id"): str(check.get("title")) for check in checks}
        for item_id, run in _runs_in_file(evidence):
            if item_id not in titles or run.get("run_id") in bound_runs:
                continue
            if ((run.get("review") or {}).get("verdict") or {}).get("reason_code") == NOT_RECORDED_REASON:
                continue      # it never started: without Otto it could not be recorded, and its result says so
            raise _Failed(f"run {run.get('run_id')} of “{titles[item_id]}” is in the file, but Otto's ledger does not bind it.")
        out.lines.append(f"Ledger: {len(entries)} entries in one unbroken chain; {len(run_claims)} runs, each bound to a test locked before it.")
        steps = otto.get("steps") or []
        for step in steps:
            if hashlib.sha256(str(step.get("prompt")).encode("utf-8")).hexdigest() != step.get("prompt_sha256") \
                    or hashlib.sha256(str(step.get("answer")).encode("utf-8")).hexdigest() != step.get("answer_sha256"):
                raise _Failed("a Claude step in the file does not match its SHA-256.")
            kept = ((claims.get(step.get("ledger_entry")) or {}).get("artifact") or {}).get("step") or {}
            if (kept.get("prompt_sha256"), kept.get("answer_sha256")) != (step.get("prompt_sha256"), step.get("answer_sha256")):
                raise _Failed("a Claude step in the file has no matching entry in the ledger.")
        if steps:
            out.lines.append(f"Claude steps: {len(steps)}, each with its prompt and answer matching its SHA-256 and its entry in the ledger.")
        # 5. an older download
        if previous is not None:
            older = (previous.get("otto") or {}).get("ledger") if isinstance(previous, dict) else None
            if not isinstance(older, dict) or not isinstance(older.get("height"), int):
                raise _Failed("the older file has no Otto ledger to compare with.")
            height, old_head = older["height"], older.get("head")
            if height > len(entries) or (height > 0 and entries[height - 1]["hash"] != old_head):
                raise _Failed("the older file's latest ledger entry is not in this ledger at the same place: history was cut or rewritten "
                              "between the two downloads.")
            out.lines.append(f"Compared with the older file: its {height} ledger entries are still here, unchanged; "
                             f"{len(entries) - height} were added since (those are not covered by this comparison).")
        # 6. Otto's own audit. Its harness runs the verifier each entry names, so first: does this ledger name anything
        #    to run but our own pinned record checker? If it does, nothing is run.
        try:
            from app.otto import assurance, harness
            foreign = assurance.only_our_checker(entries)
            if foreign == assurance.OTHER_VERSION:
                out.code = NOT_CONFIRMED
                out.problem = f"Otto's own audit of the ledger was not run: {foreign}. The checks above were made without it."
                return out
            if foreign is not None:
                raise _Failed(f"{foreign}. Nothing was run.")
            with tempfile.TemporaryDirectory(prefix="evidence-otto-") as scratch:
                problems = assurance.verify_lines(list(ledger.get("lines") or []), Path(scratch) / "lab")
            if problems:
                raise _Failed("Otto's own audit of the ledger found a problem: " + "; ".join(problems[:3]))
            pinned = harness.status()
            out.lines.append(f"Otto's own audit (harness {pinned.version}, commit {str(pinned.commit)[:7]}): chain intact, the pinned checker "
                             "run again on every entry.")
            named = otto.get("harness") or {}
            if named.get("commit") and named.get("commit") != pinned.commit:
                out.lines.append(f"Note: the file was made with Otto commit {str(named.get('commit'))[:7]}; this computer has {str(pinned.commit)[:7]}.")
        except ImportError:
            out.code, out.problem = NOT_CONFIRMED, "Otto's own audit was not run: the app's Otto adapter is not available here."
        except Exception as exc:
            if isinstance(exc, _Failed):
                raise
            if exc.__class__.__name__ == "OttoNotInstalled":
                out.code = NOT_CONFIRMED
                out.problem = (f"Otto's own audit of the ledger was not run: Otto is not installed on this computer ({exc}). "
                               "The checks above were made without it.")
            else:
                raise _Failed(f"Otto's own audit could not be completed ({exc.__class__.__name__}).") from None
        if untrusted and out.code == OK:
            out.code = NOT_CONFIRMED
            out.problem = (f"The signer of test pack {', '.join(untrusted)} could not be confirmed: its key is not one you trust. Give it "
                           "with --pack-key, or use the app that installed the pack.")
    except _Failed as exc:
        out.code, out.problem = FAILED, str(exc)
    except (KeyError, TypeError, AttributeError, ValueError):
        out.code, out.problem = FAILED, "the Otto part of the file could not be read."
    return out
