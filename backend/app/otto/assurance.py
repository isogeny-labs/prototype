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

A ledger that comes out of a file (the verify command reads one from an evidence file) is data. Otto's audit runs
the verifier each entry names, and a verifier can name a command. So before the harness is given such a ledger,
`only_our_checker` makes sure it names nothing to run but this app's own pinned record checker; otherwise nothing is
run at all.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from pathlib import Path

from app.otto import harness

CHECKER_SOURCE = Path(__file__).with_name("checker") / "recheck.py"
CHECKER = "recheck.py"
CHECKER_TIMEOUT_SECONDS = 60
AUTHOR = "evidence-lab"
ENTRY_KINDS = ("objective", "claim", "verdict")      # the only kinds of entry an assessment's ledger holds
PARAM_KINDS = ("run", "step")                        # what the pinned checker checks: a bound run, or a Claude step
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
OTHER_VERSION = "the ledger was written with a record checker that is not this version's (it may come from another version of the app)"
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
        """Otto's own audit, with the pinned checker run again on every entry. An empty list means no problem."""
        if not self.exists():
            return []
        with self._guard:
            lab = self._lab()
            problems = list(lab.audit(reverify=True))
            return problems + [f"an entry could not be checked again ({note})" for note in getattr(lab, "audit_notes", []) or []]

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


def only_our_checker(entries: list) -> str | None:
    """A ledger that came out of a file is data, and Otto's audit runs what its entries name. This says, in one plain
    phrase, what such a ledger names that is not this app's own pinned record checker, or None when it names nothing
    else. Nothing is run to find out. OTHER_VERSION is returned when the only difference is the checker's fingerprint."""
    ours = _sha256(CHECKER_SOURCE)
    other_version = False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") not in ENTRY_KINDS or not isinstance(entry.get("payload"), dict) \
                or entry["payload"].get("type") != entry["kind"]:
            return "the ledger holds an entry of a kind an assessment's ledger never holds"
        if entry["kind"] != "objective":
            continue
        verifier = entry["payload"].get("verifier")
        if not isinstance(verifier, dict) or set(verifier) != {"kind", "checker", "checker_sha256", "params", "timeout_seconds"} \
                or verifier["kind"] != "certificate" or verifier["checker"] != CHECKER \
                or verifier["timeout_seconds"] != CHECKER_TIMEOUT_SECONDS or isinstance(verifier["timeout_seconds"], bool) \
                or not isinstance(verifier["params"], dict) or verifier["params"].get("kind") not in PARAM_KINDS \
                or not isinstance(verifier["checker_sha256"], str) or not _HEX64.match(verifier["checker_sha256"]):
            return "the ledger names something to run that is not this app's own pinned record checker"
        if verifier["checker_sha256"] != ours:
            other_version = True
    return OTHER_VERSION if other_version else None


def verify_lines(lines: list[str], scratch: Path) -> list[str]:
    """Check a ledger given as its lines (from an evidence file): write it into a scratch lab with the pinned checker
    and run Otto's own audit on it. Returns the problems found (empty when there are none). Raises OttoNotInstalled.

    The lines are data from a file. Unless they name nothing to run but our own pinned checker, the harness is not
    given them and nothing is run. An entry the audit could not check again is a problem too, never a quiet pass."""
    try:
        entries = [json.loads(line) for line in lines]
    except (TypeError, ValueError):
        return ["the ledger's lines could not be read"]
    foreign = only_our_checker(entries)
    if foreign is not None:
        return [f"{foreign}, so nothing was run"]
    module = harness.module("lab")
    ledger_module = harness.module("ledger")
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "ledger.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    shutil.copyfile(CHECKER_SOURCE, scratch / CHECKER)
    try:
        lab = module.Lab(str(scratch))
        problems = list(lab.audit(reverify=True))
    except ledger_module.LedgerError as exc:
        return [f"the chain does not hold: {exc}"]
    return problems + [f"an entry could not be checked again ({note})" for note in getattr(lab, "audit_notes", []) or []]
