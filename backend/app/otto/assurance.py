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
    a decision      for each decision a person records on one of Otto's proposals (accept, reject, undo, reconsider):
    entry           what was proposed (by its SHA-256), what was decided, by whom and when. The first decision on a
                    proposal opens an entry that names the proposal; each decision is a claim under it.

What the ledger confirms is BINDING: that a run belongs to a test locked earlier, and that the reviewer was not the
proposer. It holds no result and decides none; its verdict ("accept": bound and consistent) is never shown as a
result. Evidence Lab's own read gate still re-reviews every result each time it is shown.

A lab is acted on only through the harness's own functions; the ledger file is never written by this code. The only
programs the harness starts here are this app's two pinned record checkers, copied into the lab: checker/recheck.py
(runs and Claude steps) and checker/decisions.py (decisions on proposals). The second one was added later and stands
beside the first, which is unchanged: a ledger written before it existed names only recheck.py and reads as before.

A ledger that comes out of a file (the verify command reads one from an evidence file) is data. Asked to check
every entry again, Otto's harness starts the verifier that an entry names, and it looks that entry up by its id
without asking what kind of entry it is; a verifier can name a command. So such a ledger is never checked again by
the harness. Three things are done instead, and none of them starts anything the ledger names:

  1. `only_our_checker` holds every entry to the exact form this app writes: its kind, its fields, the checker
     an objective may name (one of this app's own two, each for its own kinds of entry), and each pointer to an
     earlier entry of the right kind;
  2. the harness audits the chain and the records without running any verifier;
  3. this app's own pinned record checker for that kind of entry (a file that ships with the app, never a file or
     a command from the ledger) is run again on every checked entry, and its answer is compared with the stored one.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from app.canonical import sha256_hex
from app.otto import harness

CHECKER_SOURCE = Path(__file__).with_name("checker") / "recheck.py"
CHECKER = "recheck.py"
DECISION_CHECKER_SOURCE = Path(__file__).with_name("checker") / "decisions.py"
DECISION_CHECKER = "decisions.py"
CHECKER_TIMEOUT_SECONDS = 60
AUTHOR = "evidence-lab"
ENTRY_KINDS = ("objective", "claim", "verdict")      # the only kinds of entry an assessment's ledger holds
PARAM_KINDS = ("run", "step")                        # what the first pinned checker checks: a bound run, or a Claude step
DECISION_KINDS = ("decision",)                       # what the second one checks: a decision on one of Otto's proposals
# The only programs an objective may name, each with the file that ships with the app and the kinds of entry it
# checks. A name from a ledger is looked up here and nowhere else: it never becomes a path.
CHECKERS = {CHECKER: (CHECKER_SOURCE, PARAM_KINDS), DECISION_CHECKER: (DECISION_CHECKER_SOURCE, DECISION_KINDS)}
# The fields of each kind of entry, exactly as this app (through Otto's harness) writes them. An entry with any other
# field is not ours: in particular nothing but an objective may carry a verifier.
ENTRY_FIELDS = {"objective": frozenset({"type", "statement", "verifier", "author", "created_at"}),
                "claim": frozenset({"type", "objective_id", "artifact", "cites", "author", "created_at"}),
                "verdict": frozenset({"type", "claim_id", "objective_id", "status", "detail", "evidence", "tier", "attempt", "author",
                                      "created_at"})}
VERIFIER_FIELDS = frozenset({"kind", "checker", "checker_sha256", "params", "timeout_seconds"})
VERDICT_STATUSES = ("accept", "reject", "unavailable", "invalid_spec")
VERDICT_TIER = "V0-certificate"
# Bounds on a ledger that is checked again. An assessment's ledger holds a lock entry for each advisory check and a
# few entries for each run and each Claude step, so these are far above anything this app writes; they keep a file
# made to be slow from holding the verify command for hours.
MAX_ENTRIES = 20_000
CHECK_AGAIN_SECONDS = 300
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_RECORD_ID = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
OTHER_VERSION = "the ledger was written with a record checker that is not this version's (it may come from another version of the app)"
NOT_OUR_KIND = "the ledger holds an entry of a kind an assessment's ledger never holds"
NOT_OUR_FORM = "the ledger holds an entry that is not in the form this app writes"
NOT_OUR_CHECKER = "the ledger names something to run that is not this app's own pinned record checker"
NOT_OUR_ORDER = "the ledger holds an entry that points at something other than an earlier entry of the kind it must be"
TOO_LONG = "the ledger is longer than an assessment's ledger can be"
NOT_OUR_FOLDER = "this assessment's Otto folder holds something that is not a regular file the app wrote"
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
        """The harness's lab on this folder. Before every use the folder is made what the app wrote: the ledger is a
        regular file (never a link to somewhere else), and the checker in it is a regular file with exactly the bytes
        of the checker that ships with the app. The harness starts that file, so no other may stand in its place."""
        module = harness.module("lab")          # raises OttoNotInstalled with the plain reason
        self.folder.mkdir(parents=True, exist_ok=True)
        ledger = self.folder / "ledger.jsonl"
        if self.folder.is_symlink() or ledger.is_symlink() or (ledger.exists() and not ledger.is_file()):
            raise harness.OttoNotInstalled(NOT_OUR_FOLDER)
        if not ledger.exists():
            ledger.touch()
        for name, (source, _) in CHECKERS.items():
            target = self.folder / name
            ours = source.read_bytes()
            if target.is_symlink() or not target.is_file() or target.read_bytes() != ours:
                if target.is_symlink() or target.exists():
                    if target.is_dir() and not target.is_symlink():
                        raise harness.OttoNotInstalled(NOT_OUR_FOLDER)
                    target.unlink()                 # a link is removed, never followed
                with open(target, "xb") as fh:      # a new regular file, made here
                    fh.write(ours)
        return module.Lab(str(self.folder))

    def _verifier(self, params: dict, checker: str = CHECKER) -> dict:
        # the pin is the checker that ships with the app, which is also what _lab keeps in the folder
        return {"kind": "certificate", "checker": checker, "checker_sha256": _sha256(CHECKERS[checker][0]), "params": params,
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

    def record_decision(self, *, objective_id: str | None, proposal_id: str, kind: str, title: str, proposal_sha256: str, decision: str,
                        before: str, after: str, by: str, at: str, reason: str | None, number: int, about: dict) -> tuple[str, str, str]:
        """One decision a person recorded on one of Otto's proposals. Returns (the entry that names the proposal, the
        decision's own entry, the checker's verdict: accept or reject). `objective_id` is the entry that names this
        proposal, from its earlier decisions; None for its first one. The checker's verdict says the entry is whole
        and in order. It is not the decision and never a result."""
        with self._guard:
            lab = self._lab()
            if objective_id is None:
                objective_id = lab.add({"type": "objective",
                                        "statement": (f"Every decision a person records on Otto's proposal “{title}” names what was proposed by "
                                                      "its SHA-256, says who decided and when, and is a step the state before it allows."),
                                        "verifier": self._verifier({"kind": "decision", "proposal": proposal_id, "proposal_kind": kind},
                                                                   DECISION_CHECKER)}, AUTHOR)
            claim = lab.add({"type": "claim", "objective_id": objective_id, "cites": [],
                             "artifact": {"proposal": proposal_id, "proposal_kind": kind, "proposal_sha256": proposal_sha256, "title": title,
                                          "decision": decision, "before": before, "after": after, "by": by, "at": at, "reason": reason,
                                          "number": int(number), "about": about}}, AUTHOR)
            _, verdict = lab.verify(claim)
            return objective_id, claim, verdict["status"]

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


    def about_proposal(self, objective_id: str) -> list[dict]:
        """The entries about one proposal's decisions, oldest first, in the same form as `about`. The words say what
        each entry is; the checker's answer is worded as a check of the record, never as a decision or a result."""
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
                    what = "Proposal entry: names what was proposed, written with the first decision on it"
                elif rid in claims:
                    art = record["artifact"]
                    what = f"Decision {art.get('number')}: {DECISION_WORDS.get(art.get('decision'), 'recorded')} by {art.get('by')}"
                elif entry["kind"] == "verdict" and record.get("claim_id") in claims:
                    what = ("The pinned checker: the entry is whole and in order" if record["status"] == "accept"
                            else f"The pinned checker did not accept the entry ({record['status']})")
                else:
                    continue
                out.append({"seq": entry["seq"], "kind": entry["kind"], "id": rid, "at": entry["ts"], "what": what})
            return out


PHASE_WORDS = {"first": "first run", "retest": "retest", "proof": "fix proof"}
DECISION_WORDS = {"accept": "accepted", "reject": "rejected", "undo": "accept undone", "reconsider": "taken up again"}


def record_id(payload: object) -> str:
    """The id of the record an entry holds, worked out without the harness (the SHA-256 of its canonical form)."""
    return "sha256:" + sha256_hex(payload)


def only_our_checker(entries: list) -> str | None:
    """A ledger that came out of a file is data. This says, in one plain phrase, what in such a ledger is not what
    this app writes, or None when every entry is: one of the three kinds, with exactly the fields of its kind; an
    objective that names one of this app's own pinned record checkers, for a kind of entry that checker checks, and
    nothing else; a claim that points at an earlier objective; a verdict that points at an earlier claim and at that
    claim's own objective. Nothing is run to find out. OTHER_VERSION is returned when the only difference is a
    checker's fingerprint."""
    ours = {name: _sha256(source) for name, (source, _) in CHECKERS.items()}
    other_version = False
    kinds: dict[str, str] = {}              # record id -> the kind of the entry that holds it
    objective_of: dict[str, str] = {}       # claim id -> the objective it was made under
    settled: set[str] = set()               # the claims that already have an accept or a reject
    if len(entries) > MAX_ENTRIES:
        return TOO_LONG
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
                    or verifier["kind"] != "certificate" or not isinstance(verifier["checker"], str) or verifier["checker"] not in CHECKERS \
                    or type(verifier["timeout_seconds"]) is not int or verifier["timeout_seconds"] != CHECKER_TIMEOUT_SECONDS \
                    or not isinstance(verifier["params"], dict) or verifier["params"].get("kind") not in CHECKERS[verifier["checker"]][1] \
                    or not isinstance(verifier["checker_sha256"], str) or not _HEX64.match(verifier["checker_sha256"]):
                return NOT_OUR_CHECKER
            if verifier["checker_sha256"] != ours[verifier["checker"]]:
                other_version = True
        elif kind == "claim":
            if not isinstance(payload["artifact"], dict) or payload["cites"] != []:
                return NOT_OUR_FORM
            if not _is_id(payload["objective_id"]) or kinds.get(payload["objective_id"]) != "objective":
                return NOT_OUR_ORDER
            objective_of[rid] = payload["objective_id"]
        else:
            if payload["status"] not in VERDICT_STATUSES or payload["tier"] != VERDICT_TIER or not isinstance(payload["evidence"], dict) \
                    or not isinstance(payload["detail"], str) or type(payload["attempt"]) is not int or payload["attempt"] < 0:
                return NOT_OUR_FORM
            if not _is_id(payload["claim_id"]) or not _is_id(payload["objective_id"]) or kinds.get(payload["claim_id"]) != "claim" \
                    or kinds.get(payload["objective_id"]) != "objective" or objective_of.get(payload["claim_id"]) != payload["objective_id"]:
                return NOT_OUR_ORDER
            if payload["status"] in ("accept", "reject"):
                if payload["claim_id"] in settled:      # the harness never settles an entry twice
                    return NOT_OUR_ORDER
                settled.add(payload["claim_id"])
        if kinds.setdefault(rid, kind) != kind:
            return NOT_OUR_ORDER
    return OTHER_VERSION if other_version else None


def _is_id(value: object) -> bool:
    return isinstance(value, str) and bool(_RECORD_ID.match(value))


def run_checker(params: dict, artifact: dict, checker: str = CHECKER) -> str:
    """One of this app's own pinned record checkers, run on one entry: "accept", "reject", or "unavailable" when it
    gave no usable answer. `checker` is the name an entry gave; it is only looked up among this app's own two, and
    the program started is always that checker file as it ships with the app, with a fixed command, an empty folder to
    work in and a bare environment. Nothing in a ledger can name another program, a file or a setting."""
    source = CHECKERS[checker][0] if isinstance(checker, str) and checker in CHECKERS else None
    if source is None:
        return "unavailable"
    try:
        sent = json.dumps({"params": params, "artifact": artifact}).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="evidence-otto-check-") as empty:
            done = subprocess.run([sys.executable, "-I", str(source)], input=sent, capture_output=True, cwd=empty,
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
    started = time.monotonic()
    for entry in entries:
        verdict = entry["payload"]
        if entry["kind"] != "verdict" or verdict["status"] not in ("accept", "reject"):
            continue
        if time.monotonic() - started > CHECK_AGAIN_SECONDS:
            problems.append(f"the entries could not all be checked again within {CHECK_AGAIN_SECONDS // 60} minutes; "
                            f"entry {entry.get('seq')} and those after it were not")
            break
        claim, objective = records[verdict["claim_id"]], records[verdict["objective_id"]]
        now = run_checker(objective["verifier"]["params"], claim["artifact"], objective["verifier"]["checker"])
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
        foreign = only_our_checker(entries)
    except (TypeError, ValueError, RecursionError):
        return ["the ledger's lines could not be read"]
    if foreign is not None:
        return [f"{foreign}, so nothing was run"]
    module = harness.module("lab")
    ledger_module = harness.module("ledger")
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "ledger.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    try:
        problems = list(module.Lab(str(scratch)).audit(reverify=False))     # never reverify=True: see the note at the top
    except ledger_module.LedgerError as exc:
        return [f"the chain does not hold: {exc}"]
    except (ValueError, RecursionError) as exc:
        return [f"the ledger could not be read by Otto's harness ({exc.__class__.__name__})"]
    return problems + check_again(entries)
