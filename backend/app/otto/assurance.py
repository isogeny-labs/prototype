"""The Otto ledger of one assessment (phase 5c): a hash-chained record, kept with Adam's harness, of every loop run.

One Otto lab per assessment, at <data>/otto/assessment-<id>/. It gets:

    a lock entry    when a person adds an advisory check: an objective that holds the locked test's fingerprint, the
                    design's SHA-256 and the pack's fingerprint. It is written before the check can run, so the chain
                    itself shows that the lock came first.
    a run entry     after each reviewed run of that check (a first run, a retest or a fix proof): a claim that binds
                    the run record's SHA-256 and the review's SHA-256 to that locked test, with who proposed and who
                    reviewed. Otto's harness then runs the pinned checker on it.
    a step entry    for each Claude step taken in the app (writing a change for the customer's own code): the full
                    prompt and answer, where the answer came from, the model, the tokens, the cost and the SHA-256.

What the ledger confirms is BINDING: that a run belongs to a test locked earlier, and that the reviewer was not the
proposer. It holds no result and decides none; its verdict ("accept": bound and consistent) is never shown as a
result. Evidence Lab's own read gate still re-reviews every result each time it is shown.

A lab is acted on only through the harness's own functions; the ledger file is never written by this code. The only
program the harness starts here is the pinned record checker (checker/recheck.py, copied into the lab).

A ledger that comes out of a file (the verify command reads one from an evidence file) is data. Asked to check
every entry again, Otto's harness starts the verifier that an entry names, and it looks that entry up by its id
without asking what kind of entry it is; a verifier can name a command. So such a ledger is never checked again by
the harness. Three things are done instead, and none of them starts anything the ledger names:

  1. `only_our_checker` holds every entry to the exact form this app writes: its kind, its fields, the one checker
     an objective may name, and each pointer to an earlier entry of the right kind;
  2. the harness audits the chain and the records without running any verifier;
  3. this app's own pinned record checker (the file that ships with the app, never a file or a command from the
     ledger) is run again on every checked entry, and its answer is compared with the stored one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from app.canonical import sha256_hex
from app.otto import harness

CHECKER_SOURCE = Path(__file__).with_name("checker") / "recheck.py"
CHECKER = "recheck.py"
CHECKER_TIMEOUT_SECONDS = 60
AUTHOR = "evidence-lab"
ENTRY_KINDS = ("objective", "claim", "verdict")      # the only kinds of entry an assessment's ledger holds
PARAM_KINDS = ("run", "step")                        # what the pinned checker checks: a bound run, or a Claude step
# The fields of each kind of entry, exactly as this app (through Otto's harness) writes them. An entry with any other
# field is not ours: in particular nothing but an objective may carry a verifier.
ENTRY_FIELDS = {"objective": frozenset({"type", "statement", "verifier", "author", "created_at"}),
                "claim": frozenset({"type", "objective_id", "artifact", "cites", "author", "created_at"}),
                "verdict": frozenset({"type", "claim_id", "objective_id", "status", "detail", "evidence", "tier", "attempt", "author",
                                      "created_at"})}
VERIFIER_FIELDS = frozenset({"kind", "checker", "checker_sha256", "params", "timeout_seconds"})
VERDICT_STATUSES = ("accept", "reject", "unavailable", "invalid_spec")
VERDICT_TIER = "V0-certificate"
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_RECORD_ID = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
OTHER_VERSION = "the ledger was written with a record checker that is not this version's (it may come from another version of the app)"
NOT_OUR_KIND = "the ledger holds an entry of a kind an assessment's ledger never holds"
NOT_OUR_FORM = "the ledger holds an entry that is not in the form this app writes"
NOT_OUR_CHECKER = "the ledger names something to run that is not this app's own pinned record checker"
NOT_OUR_ORDER = "the ledger holds an entry that points at something other than an earlier entry of the kind it must be"
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def lab_folder(data_dir: Path, assessment_id: int) -> Path:
    return Path(data_dir) / "otto" / f"assessment-{int(assessment_id)}"


def _lock_for(folder: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(folder), threading.Lock())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Ledger:
    """One assessment's Otto ledger. Every method raises harness.OttoNotInstalled when the pinned Otto is not here."""

    def __init__(self, data_dir: Path, assessment_id: int):
        self.folder = lab_folder(data_dir, assessment_id)
        self._guard = _lock_for(self.folder)

    def exists(self) -> bool:
        return (self.folder / "ledger.jsonl").is_file()

    def _lab(self):
        module = harness.module("lab")          # raises OttoNotInstalled with the plain reason
        self.folder.mkdir(parents=True, exist_ok=True)
        ledger = self.folder / "ledger.jsonl"
        if not ledger.exists():
            ledger.touch()
        target = self.folder / CHECKER
        if not target.exists():
            shutil.copyfile(CHECKER_SOURCE, target)
        return module.Lab(str(self.folder))

    def _verifier(self, params: dict) -> dict:
        return {"kind": "certificate", "checker": CHECKER, "checker_sha256": _sha256(self.folder / CHECKER), "params": params,
                "timeout_seconds": CHECKER_TIMEOUT_SECONDS}

    def lock_check(self, *, title: str, program: str, spec_hash: str, design_sha256: str, pack_fingerprint: str, pack_version: str,
                   advisory_id: str) -> str:
        """The lock entry of one advisory check. Returns its record id. Written before the check can run."""
        with self._guard:
            lab = self._lab()
            return lab.add({"type": "objective",
                            "statement": (f"Every run of “{title}” on {program} belongs to the test locked with fingerprint {spec_hash}, "
                                          "and was reviewed by a reviewer that did not propose it."),
                            "verifier": self._verifier({"kind": "run", "test": spec_hash, "design": design_sha256, "pack": pack_fingerprint,
                                                        "pack_version": pack_version, "advisory": advisory_id, "program": program})}, AUTHOR)

    def record_run(self, objective_id: str, *, spec_hash: str, run_id: int, run_sha256: str, review_sha256: str, proposed_by: str,
                   reviewer: str, phase: str, ran_on: dict) -> tuple[str, str]:
        """One reviewed run of a locked check. Returns (the claim's id, the checker's verdict: accept or reject).
        The entry holds fingerprints and names only, never whether the run passed or failed."""
        with self._guard:
            lab = self._lab()
            claim = lab.add({"type": "claim", "objective_id": objective_id, "cites": [],
                             "artifact": {"test": spec_hash, "run_id": int(run_id), "run_sha256": run_sha256, "review_sha256": review_sha256,
                                          "proposed_by": proposed_by, "reviewer": reviewer, "phase": phase, "ran_on": ran_on}}, AUTHOR)
            _, verdict = lab.verify(claim)
            return claim, verdict["status"]

    def record_step(self, advisory_id: str, step: dict, outcome: str, refusal: str | None) -> tuple[str, str]:
        """One Claude step taken in the app, in full. Returns (the claim's id, the checker's verdict)."""
        with self._guard:
            lab = self._lab()
            objective = lab.add({"type": "objective",
                                 "statement": (f"The record of Otto's {step['step'].replace('_', ' ')} step for {advisory_id} is whole: the prompt and "
                                               "the answer are there with their SHA-256, and the source of the answer is named."),
                                 "verifier": self._verifier({"kind": "step", "step": step["step"], "advisory": advisory_id})}, AUTHOR)
            artifact: dict = {"advisory": advisory_id, "step": step, "outcome": outcome}
            if refusal:
                artifact["refusal"] = refusal
            claim = lab.add({"type": "claim", "objective_id": objective, "artifact": artifact, "cites": []}, AUTHOR)
            _, verdict = lab.verify(claim)
            return claim, verdict["status"]

    # ---------------------------------------------------------------- reading

    def head(self) -> dict | None:
        if not self.exists():
            return None
        with self._guard:
            return self._lab().ledger.head()

    def entries(self) -> list[dict]:
        """Every entry, oldest first, exactly as the chain holds it."""
        if not self.exists():
            return []
        with self._guard:
            return list(self._lab().ledger.entries())

    @staticmethod
    def record_id(entry: dict) -> str:
        """The id of the record an entry holds (the SHA-256 of its canonical form, as Otto computes it)."""
        return harness.module("canonical").digest(entry["payload"])

    def lines(self) -> list[str]:
        """The ledger file's lines, exactly as written (for the evidence file)."""
        if not self.exists():
            return []
        with self._guard:
            return [line for line in (self.folder / "ledger.jsonl").read_text(encoding="utf-8").split("\n") if line]

    def audit(self) -> list[str]:
        """Otto's own audit of the chain and the records, and this app's pinned checker run again on every checked
        entry. An empty list means no problem. The ledger file is read as data here too: nothing it names is run."""
        if not self.exists():
            return []
        with self._guard:
            lab = self._lab()
            entries = list(lab.ledger.entries())
            foreign = only_our_checker(entries)
            if foreign is not None:
                return [f"{foreign}, so nothing was run"]
            return list(lab.audit(reverify=False)) + check_again(entries)

    def about(self, objective_id: str) -> list[dict]:
        """The entries about one locked check, oldest first: {"seq", "kind", "id", "at", "what"}. The words only say
        what the entry is; they never word a result."""
        if not self.exists():
            return []
        with self._guard:
            lab = self._lab()
            st = lab.state()
            claims = {cid for cid, c in st.of("claim") if c["objective_id"] == objective_id}
            out = []
            for entry in lab.ledger.entries():
                rid, record = lab.ledger.record_id(entry), entry["payload"]
                if rid == objective_id:
                    what = "Lock entry: the test's fingerprint, its design and its pack, written before any run"
                elif rid in claims:
                    what = f"Run {record['artifact']['run_id']} ({PHASE_WORDS.get(record['artifact']['phase'], record['artifact']['phase'])}) bound to the locked test"
                elif entry["kind"] == "verdict" and record.get("claim_id") in claims:
                    what = ("The pinned checker: bound and consistent" if record["status"] == "accept"
                            else f"The pinned checker did not accept the entry ({record['status']})")
                else:
                    continue
                out.append({"seq": entry["seq"], "kind": entry["kind"], "id": rid, "at": entry["ts"], "what": what})
            return out


PHASE_WORDS = {"first": "first run", "retest": "retest", "proof": "fix proof"}


def record_id(payload: object) -> str:
    """The id of the record an entry holds, worked out without the harness (the SHA-256 of its canonical form)."""
    return "sha256:" + sha256_hex(payload)


def only_our_checker(entries: list) -> str | None:
    """A ledger that came out of a file is data. This says, in one plain phrase, what in such a ledger is not what
    this app writes, or None when every entry is: one of the three kinds, with exactly the fields of its kind; an
    objective that names this app's own pinned record checker and nothing else; a claim that points at an earlier
    objective; a verdict that points at an earlier claim and at that claim's own objective. Nothing is run to find
    out. OTHER_VERSION is returned when the only difference is the checker's fingerprint."""
    ours = _sha256(CHECKER_SOURCE)
    other_version = False
    kinds: dict[str, str] = {}              # record id -> the kind of the entry that holds it
    objective_of: dict[str, str] = {}       # claim id -> the objective it was made under
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict) or not isinstance(entry.get("kind"), str) \
                or entry["kind"] not in ENTRY_KINDS or entry["payload"].get("type") != entry["kind"]:
            return NOT_OUR_KIND
        kind, payload = entry["kind"], entry["payload"]
        if set(payload) != ENTRY_FIELDS[kind]:
            return NOT_OUR_FORM
        try:
            rid = record_id(payload)
        except (TypeError, ValueError, RecursionError):
            return NOT_OUR_FORM
        if kind == "objective":
            verifier = payload["verifier"]
            if not isinstance(verifier, dict) or set(verifier) != VERIFIER_FIELDS \
                    or verifier["kind"] != "certificate" or verifier["checker"] != CHECKER \
                    or verifier["timeout_seconds"] != CHECKER_TIMEOUT_SECONDS or isinstance(verifier["timeout_seconds"], bool) \
                    or not isinstance(verifier["params"], dict) or verifier["params"].get("kind") not in PARAM_KINDS \
                    or not isinstance(verifier["checker_sha256"], str) or not _HEX64.match(verifier["checker_sha256"]):
                return NOT_OUR_CHECKER
            if verifier["checker_sha256"] != ours:
                other_version = True
        elif kind == "claim":
            if not isinstance(payload["artifact"], dict) or payload["cites"] != []:
                return NOT_OUR_FORM
            if not _is_id(payload["objective_id"]) or kinds.get(payload["objective_id"]) != "objective":
                return NOT_OUR_ORDER
            objective_of[rid] = payload["objective_id"]
        else:
            if payload["status"] not in VERDICT_STATUSES or payload["tier"] != VERDICT_TIER or not isinstance(payload["evidence"], dict) \
                    or not isinstance(payload["detail"], str) or not isinstance(payload["attempt"], int) or isinstance(payload["attempt"], bool):
                return NOT_OUR_FORM
            if not _is_id(payload["claim_id"]) or not _is_id(payload["objective_id"]) or kinds.get(payload["claim_id"]) != "claim" \
                    or kinds.get(payload["objective_id"]) != "objective" or objective_of.get(payload["claim_id"]) != payload["objective_id"]:
                return NOT_OUR_ORDER
        if kinds.setdefault(rid, kind) != kind:
            return NOT_OUR_ORDER
    return OTHER_VERSION if other_version else None


def _is_id(value: object) -> bool:
    return isinstance(value, str) and bool(_RECORD_ID.match(value))


def run_checker(params: dict, artifact: dict) -> str:
    """This app's own pinned record checker, run on one entry: "accept", "reject", or "unavailable" when it gave no
    usable answer. The program started is always the checker file that ships with the app, with a fixed command, an
    empty folder to work in and a bare environment. Nothing in a ledger can name another program, a file or a setting."""
    try:
        sent = json.dumps({"params": params, "artifact": artifact}).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="evidence-otto-check-") as empty:
            done = subprocess.run([sys.executable, "-I", str(CHECKER_SOURCE)], input=sent, capture_output=True, cwd=empty,
                                  timeout=CHECKER_TIMEOUT_SECONDS, env={"PATH": os.environ.get("PATH", "")}, shell=False)
        if done.returncode != 0:
            return "unavailable"
        said = json.loads(done.stdout)
        status = said.get("status") if isinstance(said, dict) else None
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, RecursionError):
        return "unavailable"
    return status if status in ("accept", "reject") else "unavailable"


def check_again(entries: list[dict]) -> list[str]:
    """Run this app's pinned checker again on every entry it once accepted or rejected, and compare. `entries` must
    have passed `only_our_checker` (so every pointer leads to an earlier entry of the right kind). Returns the
    problems: a different answer, or an entry that could not be checked again (never a quiet pass)."""
    records = {record_id(e["payload"]): e["payload"] for e in entries}
    problems = []
    for entry in entries:
        verdict = entry["payload"]
        if entry["kind"] != "verdict" or verdict["status"] not in ("accept", "reject"):
            continue
        claim, objective = records[verdict["claim_id"]], records[verdict["objective_id"]]
        now = run_checker(objective["verifier"]["params"], claim["artifact"])
        if now == "unavailable":
            problems.append(f"entry {entry.get('seq')} could not be checked again (the pinned checker gave no usable answer)")
        elif now != verdict["status"]:
            problems.append(f"entry {entry.get('seq')}: the stored verdict is {verdict['status']} but the pinned checker now says {now}")
    return problems


def verify_lines(lines: list[str], scratch: Path) -> list[str]:
    """Check a ledger given as its lines (from an evidence file). Returns the problems found (empty when there are
    none). Raises OttoNotInstalled.

    The lines are data from a file. Unless every entry is in the exact form this app writes, nothing is run and the
    harness is not given them. Then Otto's harness audits the chain and the records, WITHOUT running any verifier,
    and this app's own pinned checker is run again on every checked entry."""
    try:
        entries = [json.loads(line) for line in lines]
    except (TypeError, ValueError, RecursionError):
        return ["the ledger's lines could not be read"]
    foreign = only_our_checker(entries)
    if foreign is not None:
        return [f"{foreign}, so nothing was run"]
    module = harness.module("lab")
    ledger_module = harness.module("ledger")
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "ledger.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    try:
        problems = list(module.Lab(str(scratch)).audit(reverify=False))
    except ledger_module.LedgerError as exc:
        return [f"the chain does not hold: {exc}"]
    return problems + check_again(entries)
