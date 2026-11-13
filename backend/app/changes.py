"""Fixes: connecting the demo code, the suggested change, its proof, the pull request and the merge.

What this module must never do: run anything it reads from a repository. Code from a repository is data. It is
compared byte for byte with our registered demo components, and a proof then runs the REGISTERED component,
through the same job runner, component runner and reviewer as every other test. The changed file itself is
never executed, compiled or written anywhere it could be run from.

It never merges on its own. Every step here is one explicit action by the user; the only thing that starts by
itself is the proof, when the code is connected. Whether a change may be offered is decided in reviewer.py
from stored records, and checked again every time it is shown or used.

Records are append-only and no status is stored: where a fix stands is worked out from the rows each time."""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
from pathlib import Path

from sqlalchemy import func, select

from . import components, demo_repo, research
from .canonical import canonical_bytes
from .db import (
    ApprovalRow, ChangeRow, CodeConnectionRow, MergeRow, PlanRow, ProofReviewRow, ProofRow, PullRequestRow, RetestRow,
    ReviewRow, TestRunRow, TestSpecRow, iso,
)
from .errors import BadRequest, Conflict, NotFound
from .gitrepo import GitRepo, GitRepoError, Person, count_changes, format_patch
from .reviewer import PROOF_SCHEMA, ReviewNotAllowed
from .testlab import BUSY, read_spec

# The fixed tick list of reviewers (SPEC 7b item 4). The app has one login, so whoever is at the keyboard
# records each approval; the two demo reviewers are demo data.
REVIEWERS = {"you": "You", "a": "Demo reviewer A", "b": "Demo reviewer B"}
TEMPLATE_AUTHOR = Person("Evidence Lab fix template", "fix-template@example.invalid")
MERGE_AUTHOR = Person("Evidence Lab user", "user@example.invalid")
PATCH_FOOTER = "Isogeny Evidence Lab (demo)"
PROOF_CHANGED = "The stored proof no longer matches its fingerprint."


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_name(repository: str, number: int) -> str:
    """The file name of a pull request's patch. The link in the Fixes step and the download itself both use it."""
    return f"{repository}-pull-request-{number}.patch"


def registered_version(name: str | None, files: dict[str, bytes]) -> str | None:
    """The byte-for-byte check. Which registered version of our demo component is exactly this code (the same
    one file with the same bytes), or None. Nothing is run to find out."""
    for version in components.VERSIONS.get(name or "", []):
        path = components.lookup(name, version)
        if path is not None and files == {path.name: path.read_bytes()}:
            return version
    return None


# ---------------------------------------------------------------- why an action is refused right now
# Each takes one code fix as fix_states describes it and gives a plain sentence, or None when the action is
# allowed. The actions and the description of a fix both use these, so a button and its refusal can't disagree.

def _no_new_proof(fix: dict) -> str | None:
    """Run proof again: after a proof that failed, was interrupted or no longer covers the plan. A pull request
    that is open does not stand in the way (its proof may have gone out of date); a merge does."""
    change, proof = fix["change"], fix["proof"]
    if change is None:
        return "Connect the demo code first."
    if fix["merge"] is not None:
        return "This pull request is already merged."
    if change["problem"]:
        return change["problem"]
    if change["built"]["matches"] is None:
        return "The changed code is not one of our demo components, so nothing can be run."
    if proof is not None and proof["state"] == "passed" and proof["covers_plan"]:
        return "The proof has passed. It can be run again only after it failed or was interrupted."
    return fix["rerun_blocked"]


def _no_pull_request(fix: dict) -> str | None:
    proof = fix["proof"]
    if fix["change"] is None:
        return "Connect the demo code first."
    if fix["pull_request"] is not None:
        return "A pull request is already open for this change."
    if fix["change"]["problem"] or proof is None or proof["state"] != "passed":
        return "A pull request can be opened only after the proof has passed."
    if not proof["covers_plan"]:
        return "The test plan has changed since the proof ran. Run the proof again first."
    return None


def _no_offer(fix: dict) -> str | None:
    """Why the change of an open pull request can't be acted on right now, or None while its offer stands: the
    latest proof has passed, is still what the stored records give, and covers the plan as it is now. Approve,
    Merge and Download patch all ask this, so an open pull request never shields a proof that no longer holds."""
    proof = fix["proof"]
    if fix["change"]["problem"] or proof is None:
        return PROOF_CHANGED
    if proof["state"] == "running":
        return BUSY["proof"]
    if proof["review"] is not None and not proof["review"]["believed"]:
        return proof["review"]["problem"]
    if proof["state"] != "passed":
        return "The proof has not passed. Run the proof again first."
    if not proof["covers_plan"]:
        return "The test plan has changed since the proof ran. Run the proof again first."
    return None


def _pull_request_closed(fix: dict) -> str | None:
    """Why nothing more can be recorded on this fix's pull request right now (shared by Approve and Merge)."""
    if fix["pull_request"] is None:
        return "Open a pull request first."
    if fix["merge"] is not None:
        return "This pull request is already merged."
    return _no_offer(fix)


def _no_approval(fix: dict, reviewer: str) -> str | None:
    closed = _pull_request_closed(fix)
    if closed:
        return closed
    row = next((a for a in fix["pull_request"]["approvals"] if a["reviewer"] == reviewer), None)
    if row is None:
        return "That reviewer was not picked for this pull request."
    if row["approved_at"] is not None:
        return "That reviewer has already approved."
    return None


def _no_merge(fix: dict) -> str | None:
    closed = _pull_request_closed(fix)
    if closed:
        return closed
    if any(a["approved_at"] is None for a in fix["pull_request"]["approvals"]):
        return "Every picked reviewer must approve before the merge."
    return None


def _no_patch(fix: dict) -> str | None:
    """Download patch: only while the change is offered. Before the merge that is the question Approve and Merge
    ask too. A merged change keeps its patch for as long as the proof it was merged on is still believed."""
    if fix["pull_request"] is None:
        return "The patch can be downloaded once a pull request is open."
    if fix["merge"] is None:
        return _no_offer(fix)
    proof = fix["proof"]
    return None if not fix["change"]["problem"] and proof is not None and proof["state"] == "passed" else PROOF_CHANGED


def _no_retest_now(fix: dict) -> str | None:
    return fix["rerun_blocked"] if fix["merge"] is not None else "Retest now is available after the merge."


def _status(fix: dict) -> str:
    """The status key of a code fix (contract 3.8), from its records. A merge is a fact and stays. Before it,
    the latest proof leads, with or without a pull request: only a proof that has passed, is still believed and
    covers the plan as it is now makes a change ready, waiting for approval or ready to merge."""
    change, proof, pull_request = fix["change"], fix["proof"], fix["pull_request"]
    if change is None:
        return "not_connected"
    if fix["merge"] is not None:
        return "merged"
    if change["problem"] or change["built"]["matches"] is None or proof is None:
        return "failed"
    if proof["state"] == "running":
        return "proving"
    if proof["state"] != "passed" or not proof["covers_plan"]:
        return "failed"
    if pull_request is None:
        return "ready"
    return "waiting" if any(a["approved_at"] is None for a in pull_request["approvals"]) else "ready_to_merge"


class ChangesMixin:
    """Mixed into Lab. Needs: db, settings, jobs, engine, reviewer, _stopping, and from TestLabMixin: _plan_lock,
    _plan, _items, _latest_run, _result, _verdict, _compare_blocked, _submit, start_retest."""

    def _init_changes(self) -> None:
        self._proof_lock = threading.Lock()  # so that a proof is reviewed once when two of its jobs finish together

    # ---------------------------------------------------------------- reading what is stored

    @staticmethod
    def _kind(db, spec_hash: str) -> str | None:
        row = db.get(TestSpecRow, spec_hash)
        return row.kind if row else None

    def _shown(self, db, plan: PlanRow, items: list) -> list[dict]:
        """The results Evidence Lab has for each test now, in plan order: the newest reviewed first run and, once
        a retest exists, the newest reviewed run of the latest retest. Each as the read gate lets it through."""
        retest = db.scalars(select(RetestRow).where(RetestRow.plan_id == plan.id).order_by(RetestRow.id.desc()).limit(1)).first()
        phases = [("first", None)] + ([("retest", retest.id)] if retest is not None else [])
        out = []
        for item in items:
            kind = self._kind(db, item.spec_hash)
            for phase, rerun_id in phases:
                run = self._latest_run(db, item.id, phase, rerun_id)
                if run is not None:
                    result = self._result(db, run)
                    out.append({"item_id": item.id, "kind": kind, "phase": phase, "run_id": run.id,
                                "version": run.component_version, "code": result["code"], "tone": result["tone"]})
        return out

    def _repo(self, folder: str) -> GitRepo:
        """Open a plan's own copy of the code. Only a folder inside the app's own repos folder is ever opened."""
        root = (self.settings.data_dir / "repos").resolve()
        path = (self.settings.data_dir / folder).resolve()
        if root not in path.parents:
            raise GitRepoError("The connected repository is not in the app's own folder.")
        return GitRepo(path)

    @staticmethod
    def _bundled_files(plan: PlanRow) -> dict[str, bytes] | None:
        """The code in the bundled demo repository for the plan's component, or None unless its main branch
        holds exactly the registered component the file names (only then can it be connected)."""
        folder = demo_repo.bundled(plan.component_name)
        if folder is None or components.lookup(plan.component_name, plan.component_version) is None:
            return None
        try:
            repo = GitRepo(folder)
            files = repo.files(repo.branch(demo_repo.BRANCH) or "")
        except (GitRepoError, OSError):
            return None
        return files if registered_version(plan.component_name, files) == plan.component_version else None

    def _proposal(self, db, plan: PlanRow, shown: list[dict], files: dict[str, bytes]) -> tuple[dict, list[dict]] | None:
        """Ask the engine for a change that answers the plan's failed first results, giving it the code as text.
        Returns (the proposal, the results it answers), or None. A change may only edit files already there."""
        failed = [r for r in shown if r["phase"] == "first" and r["code"] == "failed"]
        request = []
        for result in failed:
            review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == result["run_id"])).first()
            request.append({"kind": result["kind"], "reason_code": review.reason_code, "detail": review.detail})
        try:
            texts = {name: data.decode("utf-8") for name, data in files.items()}
        except UnicodeDecodeError:
            return None
        proposal = self.engine.propose_change({"component": {"name": plan.component_name, "version": plan.component_version},
                                               "failed": request, "files": texts})
        if not proposal or set(proposal["files"]) != set(texts):
            return None
        answered = [failed[i] for i in proposal["answers"] if isinstance(i, int) and 0 <= i < len(failed)]
        return (proposal, answered) if answered else None  # a change that answers none of the failures is not a fix for them

    # ---------------------------------------------------------------- where every fix stands

    def fix_states(self, plan_id: int) -> list[dict]:
        """Where every fix of this plan stands, as plain data with no wording (the Fixes view words it).
        Code fixes first, then text-only ones in plan order. Every verdict in here has passed the read gate:
        a result or a proof whose stored records no longer match is given as not trusted, never as it was stored."""
        with self.db() as db:
            return self._fixes(db, self._plan(db, plan_id))

    def _fix_sources(self) -> list:
        """Where fixes come from, as an explicit list. Phase 3a has one source; phase 3c adds a developer's change."""
        return [self._fixes_for_failed_tests]

    def _fixes(self, db, plan: PlanRow) -> list[dict]:
        items = self._items(db, plan.id)
        shown = self._shown(db, plan, items)
        fixes = [fix for source in self._fix_sources() for fix in source(db, plan, items, shown)]
        return sorted(fixes, key=lambda fix: fix["kind"] != "code")  # stable: code fixes first, the rest as found

    def _fixes_for_failed_tests(self, db, plan: PlanRow, items: list, shown: list[dict]) -> list[dict]:
        """One code fix for the failed signing tests a change answers (it stays listed once its change is on record);
        a text-only fix for every other test whose newest shown result that says pass or fail is a failure."""
        failed = [r for r in shown if r["tone"] == "fail"]
        fixes = []
        code = self._code_fix(db, plan, items, shown, failed)
        if code is not None:
            fixes.append(code)
        answered = {a["run_id"] for a in code["answers"]} if code is not None else set()
        # A finding counts as open until a newer result of its test shows it gone. What counts for each test is the
        # newest of the results Evidence Lab shows now (`shown`) that says pass or fail. Everything else shows
        # nothing either way and is passed over: "Couldn't run", "Couldn't trust this run", and results that only
        # report ("Measured", "Not offered"). So a retest that could not reach the server does not close a finding
        # that comes from a first result, and a new "Measured" does not close a "Slowdown found". And "newest" is
        # by when the run was made (run ids only grow), whichever column shows it: a first result that was run
        # again after a retest is newer than that retest's result. Only what is shown now is looked at: a finding
        # that only a retest found leaves the list once the next retest starts (docs/LIMITS.md says so).
        newest: dict[int, dict] = {}
        for r in shown:
            if r["tone"] in ("pass", "fail") and (r["item_id"] not in newest or r["run_id"] > newest[r["item_id"]]["run_id"]):
                newest[r["item_id"]] = r
        for kind in dict.fromkeys(r["kind"] for r in failed):
            answers = [r for r in failed if r["kind"] == kind and r["run_id"] not in answered and newest[r["item_id"]]["tone"] == "fail"]
            if answers:
                fixes.append({"id": "fix-" + str(kind).replace("_", "-"), "kind": "text", "status": "text_only",
                              "source_kind": "failed_tests", "answers": [_answer(r) for r in answers], "component": None,
                              "template_id": None, "rerun_blocked": None, "connection": None, "change": None, "proofs": 0,
                              "proof": None, "pull_request": None, "merge": None, "actions": {}})
        return fixes

    def _code_fix(self, db, plan: PlanRow, items: list, shown: list[dict], failed: list[dict]) -> dict | None:
        connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == plan.id)).first()
        change = None
        if connection is None:
            # Not connected yet: would the engine make a change to the bundled code for these failures?
            files = self._bundled_files(plan) if any(r["phase"] == "first" and r["code"] == "failed" for r in failed) else None
            proposed = self._proposal(db, plan, shown, files) if files is not None else None
            if proposed is None:
                return None
            fix_key, came_from = proposed[0]["template_id"], [_answer(r) for r in proposed[1]]
        else:
            change = db.scalars(select(ChangeRow).where(ChangeRow.plan_id == plan.id, ChangeRow.source_kind == "failed_tests")
                                .order_by(ChangeRow.id.desc()).limit(1)).first()
            if change is None:
                return None
            fix_key, came_from = change.fix_key, [{**run, "phase": "first"} for run in change.source["runs"]]
            came_from = came_from + self._also_answered(db, plan, shown, change, {run["item_id"] for run in came_from})
        # The fix answers the results it came from, and every failed result shown now for the same tests on the same code.
        tests, seen = {a["item_id"] for a in came_from}, {a["run_id"] for a in came_from}
        answers = came_from + [_answer(r) for r in failed
                               if r["item_id"] in tests and r["run_id"] not in seen and r["version"] == plan.component_version]
        missing = len(items) - sum(1 for r in shown if r["phase"] == "first")
        fix = {"id": "fix-" + fix_key, "kind": "code", "source_kind": "failed_tests", "answers": answers,
               "component": {"name": plan.component_name, "version": plan.component_version},
               "template_id": change.template_id if change is not None else fix_key,
               "rerun_blocked": self._compare_blocked(plan.id, items, missing),
               "connection": None, "change": None, "proofs": 0, "proof": None, "pull_request": None, "merge": None}
        if change is not None:
            fix.update(self._change_state(db, plan, items, connection, change))
        fix["status"] = _status(fix)
        fix["actions"] = {"connect": "The demo code is already connected for this file." if change is not None else fix["rerun_blocked"],
                          "run_proof_again": _no_new_proof(fix), "open_pull_request": _no_pull_request(fix), "merge": _no_merge(fix),
                          "download_patch": _no_patch(fix), "retest_now": _no_retest_now(fix)}
        return fix

    def _also_answered(self, db, plan: PlanRow, shown: list[dict], change: ChangeRow, have: set[int]) -> list[dict]:
        """The failed first results of other tests in the plan that this change answers too: a failing test that
        joined the plan after the code was connected (for example one that was removed and added back). The
        engine is asked the same question as before connecting, about the same starting code, and only its answer
        for the change's own fix template counts. The stored change is not touched: what it was made for stays on
        record, and the proof still has to rerun and pass every such test before anything is called ready."""
        if not _known_template(change):
            return []
        files = self._bundled_files(plan)
        proposed = self._proposal(db, plan, shown, files) if files is not None else None
        if proposed is None or proposed[0]["template_id"] != change.template_id:
            return []
        return [_answer(r) for r in proposed[1] if r["item_id"] not in have]

    def _change_state(self, db, plan: PlanRow, items: list, connection: CodeConnectionRow, change: ChangeRow) -> dict:
        """The connection, the change, its latest proof, the pull request, the approvals and the merge."""
        proofs = db.scalars(select(ProofRow).where(ProofRow.change_id == change.id).order_by(ProofRow.id)).all()
        pull_request = db.scalars(select(PullRequestRow).where(PullRequestRow.change_id == change.id)).first()
        state = {
            "connection": {"id": connection.id, "repository": connection.repository, "folder": connection.folder,
                           "branch": connection.branch, "base_commit": connection.base_commit,
                           "component": {"name": connection.component_name, "version": connection.component_version},
                           "is_demo": bool(connection.is_demo), "connected_at": iso(connection.created_at)},
            "change": {"id": change.id, "fix_key": change.fix_key, "source_kind": change.source_kind, "source": change.source,
                       "written_by": change.written_by, "template_id": change.template_id, "proposed_by": change.proposed_by,
                       "title": change.title, "branch": change.branch, "base_commit": change.base_commit,
                       "head_commit": change.head_commit, "files": change.files, "built": change.built,
                       "created_at": iso(change.created_at), "problem": None if _known_template(change) else PROOF_CHANGED},
            "proofs": len(proofs),
            "proof": self._proof_state(db, plan, items, change, proofs[-1]) if proofs else None,
            "pull_request": None, "merge": None,
        }
        if pull_request is not None:
            approved = {a.reviewer: a for a in db.scalars(select(ApprovalRow).where(ApprovalRow.pull_request_id == pull_request.id)).all()}
            merge = db.scalars(select(MergeRow).where(MergeRow.pull_request_id == pull_request.id)).first()
            state["pull_request"] = {
                "id": pull_request.id, "number": pull_request.number, "title": pull_request.title, "proof_id": pull_request.proof_id,
                "reviewers": list(pull_request.reviewers), "opened_at": iso(pull_request.opened_at),
                "approvals": [{"reviewer": r, "name": approved[r].name if r in approved else REVIEWERS.get(r, r),
                               "approved_at": iso(approved[r].approved_at) if r in approved else None}
                              for r in pull_request.reviewers]}
            if merge is not None:
                state["merge"] = {"merge_commit": merge.merge_commit, "merged_at": iso(merge.merged_at)}
        return state

    # ---------------------------------------------------------------- the proof: record, review, read gate

    def _proof_tests(self, db, proof: ProofRow) -> list[dict]:
        """For each test of a proof, in its order: where it runs, the first result it is compared with and its
        proof run, each as the read gate lets it through (None where there is no reviewed run)."""
        out = []
        for entry in proof.items:
            spec, _ = read_spec(db.get(TestSpecRow, entry["spec_hash"]))
            first = db.get(TestRunRow, entry["first_run_id"])
            run = self._latest_run(db, entry["item_id"], "proof", proof.id)
            out.append({"item_id": entry["item_id"], "kind": entry["kind"], "spec_hash": entry["spec_hash"],
                        "target": "server" if (spec.get("target") or {}).get("kind") == "server" else "software",
                        "first": self._verdict(db, first) if first is not None else None,
                        "proof": self._verdict(db, run) if run is not None else None})
        return out

    @staticmethod
    def _proof_record(proof: ProofRow, change: ChangeRow, tests: list[dict]) -> dict:
        """The proof record: what the reviewer is given and what the proof's fingerprint is made from. Stored
        facts only, in the form they are read back from the database, so it comes out the same on every read."""
        def part(verdict: dict | None, keys: tuple) -> dict | None:
            return {k: verdict[k] for k in keys} if verdict is not None else None
        return {"schema": PROOF_SCHEMA,
                "change": {"fix_key": change.fix_key, "template_id": change.template_id, "branch": change.branch,
                           "base_commit": change.base_commit, "head_commit": change.head_commit, "files": change.files},
                "built": change.built, "baseline_version": proof.baseline_version, "version": proof.version,
                "proposed_by": change.proposed_by,
                # the failed tests the change was made for: the reviewer asks that each of them was rerun and passed
                "answers": [{"item_id": run["item_id"], "kind": run["kind"]} for run in (change.source or {}).get("runs") or []],
                "tests": [{"item_id": t["item_id"], "kind": t["kind"], "spec_hash": t["spec_hash"], "target": t["target"],
                           "first": part(t["first"], ("run_sha256", "code", "reason_code")),
                           "proof": part(t["proof"], ("run_sha256", "code", "reason_code", "control_outcome"))} for t in tests]}

    def _proof_review(self, db, proof: ProofRow, change: ChangeRow, tests: list[dict]) -> dict | None:
        """The read gate for a proof. None while it has no review. Otherwise the stored review, believed only if
        reviewing the stored records again gives exactly it; if not, the proof counts as not offered."""
        stored = db.scalars(select(ProofReviewRow).where(ProofReviewRow.proof_id == proof.id)).first()
        if stored is None:
            return None
        try:
            again = self.reviewer.review_proof(self._proof_record(proof, change, tests))
            believed = (_known_template(change)
                        and (stored.reviewer, stored.record_sha256, bool(stored.offered), canonical_bytes(stored.detail))
                        == (again["reviewer"], again["record_sha256"], again["offered"], canonical_bytes(_detail(again))))
        except Exception:
            believed = False
        if not believed:
            return {"reviewed_at": iso(stored.created_at), "believed": False, "offered": False, "problem": PROOF_CHANGED,
                    "record_sha256": None, "checks": None, "counts": None, "tests": [], "answers": [], "speed": None}
        return {"reviewed_at": iso(stored.created_at), "believed": True, "offered": bool(stored.offered), "problem": None,
                "record_sha256": stored.record_sha256, "checks": stored.detail["checks"], "counts": stored.detail["counts"],
                "tests": stored.detail["tests"], "answers": stored.detail["answers"], "speed": stored.detail["speed"]}

    def _proof_state(self, db, plan: PlanRow, items: list, change: ChangeRow, proof: ProofRow) -> dict:
        """The latest proof of a change: each test's first result and proof run, its live job, and the review."""
        # The live jobs are read BEFORE the stored records. A job is live until its run, its review and (for the
        # last one) the proof's review are stored, so: jobs live now means "running", whatever is stored a moment
        # later; no job live now means everything they wrote is already there to be read. Read the other way
        # round, a proof that ended between the two reads would look interrupted or changed for one answer.
        live = {job.key[0]: job for job in self.jobs.live(plan.id) if job.key[1] == "proof"}
        tests = self._proof_tests(db, proof)
        review = self._proof_review(db, proof, change, tests)
        checks = {t["item_id"]: t for t in review["tests"]} if review is not None else {}
        rows = []
        for t in tests:
            # (a test whose reviewed run is stored by now is finished, even if its job was still live a moment ago)
            job, check = (live.get(t["item_id"]) if t["proof"] is None else None), checks.get(t["item_id"])
            rows.append({"item_id": t["item_id"], "kind": t["kind"], "target": t["target"],
                         "first": _shown_verdict(t["first"]), "proof": _shown_verdict(t["proof"]),
                         "job": {"status": job.status, "progress_text": job.progress_text,
                                 "progress_percent": job.progress_percent} if job is not None else None,
                         "check": {k: check[k] for k in ("group", "report_only", "ok", "reason")} if check is not None else None})
        state = "running" if live else "interrupted" if review is None else "passed" if review["offered"] else "failed"
        return {"id": proof.id, "baseline_version": proof.baseline_version, "version": proof.version,
                "started_at": iso(proof.started_at), "state": state,
                "covers_plan": {(e["item_id"], e["spec_hash"]) for e in proof.items} == {(i.id, i.spec_hash) for i in items},
                "finished": sum(1 for t in tests if t["proof"] is not None), "total": len(tests), "tests": rows, "review": review}

    def _proof_run_finished(self, proof_id: int) -> None:
        """Called by every proof job once its run is reviewed. When the last test of the proof has its reviewed
        run, the proof itself is reviewed and the answer stored, once. Nothing is written while the app is closing."""
        with self._proof_lock, self.db() as db:
            proof = db.get(ProofRow, proof_id)
            if self._stopping or proof is None or db.scalars(select(ProofReviewRow).where(ProofReviewRow.proof_id == proof_id)).first():
                return
            tests = self._proof_tests(db, proof)
            if any(t["proof"] is None for t in tests):
                return  # other tests of this proof are still waiting or running
            try:
                review = self.reviewer.review_proof(self._proof_record(proof, db.get(ChangeRow, proof.change_id), tests))
            except ReviewNotAllowed:
                return  # never reviewed by the engine that proposed it: it then stays not offered
            db.add(ProofReviewRow(proof_id=proof_id, reviewer=review["reviewer"], record_sha256=review["record_sha256"],
                                  offered=review["offered"], detail=_detail(review)))
            db.commit()

    def _start_proof(self, db, plan: PlanRow, change: ChangeRow) -> None:
        """Write down a new proof of a change (this commits) and queue every test in the plan for it. First the
        byte-for-byte check, again: the code the change holds must be exactly a registered demo component, and
        that registered component is what the tests then run. Nothing from the repository runs."""
        connection = db.get(CodeConnectionRow, change.connection_id)
        matches = change.built["matches"]
        try:
            files = self._repo(connection.folder).files(change.head_commit)
        except (GitRepoError, OSError) as exc:
            raise Conflict("The changed code could not be read from the repository, so nothing was run.") from exc
        if matches is None or registered_version(matches["name"], files) != matches["version"]:
            raise Conflict("The changed code is not the same as one of our demo components, so nothing was run.")
        items = self._items(db, plan.id)
        first = {r["item_id"]: r["run_id"] for r in self._shown(db, plan, items) if r["phase"] == "first"}
        proof = ProofRow(plan_id=plan.id, change_id=change.id, baseline_version=plan.component_version, version=matches["version"],
                         items=[{"item_id": item.id, "spec_hash": item.spec_hash, "kind": self._kind(db, item.spec_hash),
                                 "first_run_id": first[item.id]} for item in items])
        db.add(proof)
        db.commit()
        for item in items:
            self._submit(plan, item, "proof", proof)

    # ---------------------------------------------------------------- which code a run runs on

    def _code_for_run(self, a: dict) -> dict | None:
        """The run_code values for a run that is about to start (testlab stores them with the run), or None when
        no registered component of ours runs in it. Worked out before the test starts, so a merge made while
        it runs does not change what it says."""
        name, version = a["component_name"], a["component_version"]
        path = components.lookup(name, version)
        try:
            data = path.read_bytes() if path is not None else None
        except OSError:
            data = None
        if data is None:
            return None
        code = {"source": "bundled", "component_name": name, "component_version": version, "file_sha256": _sha256(data),
                "repository": None, "branch": None, "commit": None, "change_id": None, "pull_request_number": None}
        with self.db() as db:
            if a["phase"] == "proof":
                change = db.get(ChangeRow, db.get(ProofRow, a["retest_id"]).change_id)
                connection = db.get(CodeConnectionRow, change.connection_id)
                code.update(source="repository", repository=connection.repository, branch=change.branch,
                            commit=change.head_commit, change_id=change.id)
                return code
            connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == a["plan_id"])).first()
            if connection is None:
                return code
            try:
                repo = self._repo(connection.folder)
                head = repo.branch(connection.branch)
                same = head is not None and repo.files(head) == {path.name: data}
            except (GitRepoError, OSError):
                same = False
            if not same:
                return code  # the repository does not hold this code now: the run is on the bundled component
            code.update(source="repository", repository=connection.repository, branch=connection.branch, commit=head)
            merged = db.scalars(select(PullRequestRow).join(MergeRow, MergeRow.pull_request_id == PullRequestRow.id)
                                .where(PullRequestRow.plan_id == a["plan_id"], MergeRow.merge_commit == head)).first()
            if merged is not None:
                code.update(change_id=merged.change_id, pull_request_number=merged.number)
        return code

    # ---------------------------------------------------------------- the user's actions

    def _fix(self, db, plan: PlanRow, fix_id: str) -> dict:
        """One code fix of the plan, by its id."""
        fix = next((f for f in self._fixes(db, plan) if f["id"] == fix_id), None)
        if fix is None:
            raise NotFound("That fix does not exist.")
        if fix["kind"] != "code":
            raise Conflict("This fix is a text-only suggestion: there is no code change to act on.")
        return fix

    def _fresh_folder(self, plan_id: int) -> Path:
        """A new, empty folder for this plan's own copy of the code: <data>/repos/plan-<id>. A folder of that
        name that is already there (left by an earlier database in the same data folder) is neither reused nor
        removed: the copy goes next to it, and only the folder stored with the connection is trusted later."""
        repos = self.settings.data_dir / "repos"
        repos.mkdir(parents=True, exist_ok=True)
        for n in range(1, 1000):
            folder = repos / (f"plan-{plan_id}" if n == 1 else f"plan-{plan_id}-{n}")
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                continue
        raise OSError("no free folder for the copy")

    def connect_code(self, plan_id: int) -> list[dict]:
        """Connect demo code: make this plan's own copy of the bundled demo repository, ask the engine for a
        change that answers the failed first results, put it on a new branch, check it byte for byte against
        our registered components, and start its proof. The copy and its records (the connection, the change and
        the proof) are made together or not at all."""
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            if db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == plan_id)).first() is not None:
                raise Conflict("The demo code is already connected for this file.")
            if components.lookup(plan.component_name, plan.component_version) is None:
                raise Conflict("Connecting code needs one of our demo signing components, and this file doesn't name one.")
            bundled = demo_repo.bundled(plan.component_name)
            if bundled is None:
                raise Conflict("There is no demo repository for this signing component.")
            items = self._items(db, plan_id)
            shown = self._shown(db, plan, items)
            blocked = self._compare_blocked(plan_id, items, len(items) - sum(1 for r in shown if r["phase"] == "first"))
            if blocked:
                raise Conflict(blocked)
            folder = None
            try:
                folder = self._fresh_folder(plan_id)
                shutil.copytree(bundled, folder / bundled.name)
                repo = GitRepo(folder / bundled.name)
                base = repo.branch(demo_repo.BRANCH)
                files = repo.files(base or "")
                if registered_version(plan.component_name, files) != plan.component_version:
                    raise GitRepoError("The demo repository does not hold the demo component this file names.")
                proposed = self._proposal(db, plan, shown, files)
                change = self._write_change(repo, base, files, proposed, plan) if proposed is not None else None
            except (GitRepoError, OSError) as exc:
                if folder is not None:
                    shutil.rmtree(folder, ignore_errors=True)
                why = str(exc) if isinstance(exc, GitRepoError) else "The demo repository could not be copied."
                raise Conflict(f"{why} The code was not connected.") from exc
            connection = CodeConnectionRow(plan_id=plan_id, repository=plan.component_name, branch=demo_repo.BRANCH, base_commit=base,
                                           folder=(folder / bundled.name).relative_to(self.settings.data_dir).as_posix(),
                                           component_name=plan.component_name, component_version=plan.component_version, is_demo=True)
            db.add(connection)
            db.flush()
            if change is not None:
                change.plan_id, change.connection_id = plan_id, connection.id
                db.add(change)
                db.flush()
            if change is None or change.built["matches"] is None:
                db.commit()  # connected; there is no change, or its code is not ours, so nothing is proved and nothing runs
            else:
                try:
                    self._start_proof(db, plan, change)  # stores the connection, the change and the proof together
                except Conflict:
                    shutil.rmtree(folder, ignore_errors=True)
                    raise
        return self.fix_states(plan_id)

    def _write_change(self, repo: GitRepo, base: str, files: dict[str, bytes], proposed: tuple[dict, list[dict]], plan: PlanRow) -> ChangeRow:
        """Put a proposed change on its own branch (one commit on top of `base`) and describe it: what changed in
        each file, and whether the code it holds is byte for byte one of our registered components."""
        proposal, answered = proposed
        new_files = {name: text.encode("utf-8") for name, text in proposal["files"].items()}
        head = repo.branch_from(proposal["branch"], base, new_files, f"{proposal['title']}\n\n{proposal['label']}: {proposal['template_id']}",
                                TEMPLATE_AUTHOR, int(time.time()))
        old_ids, new_ids = repo.file_ids(base), repo.file_ids(head)
        changed = []
        for name in sorted(new_files):
            if new_files[name] != files[name]:
                added, removed = count_changes(files[name].decode("utf-8"), new_files[name].decode("utf-8"))
                changed.append({"name": name, "added": added, "removed": removed, "old_blob": old_ids[name], "new_blob": new_ids[name],
                                "old_sha256": _sha256(files[name]), "new_sha256": _sha256(new_files[name]),
                                "parts": [{k: v for k, v in edit.items() if k != "file"} for edit in proposal["edits"] if edit["file"] == name]})
        registered = components.lookup(plan.component_name, plan.component_version)
        version = registered_version(plan.component_name, new_files)
        built = {"file": registered.name, "sha256": _sha256(new_files[registered.name]) if registered.name in new_files else None,
                 "matches": {"name": plan.component_name, "version": version} if version is not None else None}
        return ChangeRow(fix_key=proposal["template_id"], source_kind="failed_tests",
                         source={"runs": [{"run_id": r["run_id"], "item_id": r["item_id"], "kind": r["kind"]} for r in answered]},
                         written_by="fix_template", template_id=proposal["template_id"], proposed_by=self.engine.engine_id,
                         title=proposal["title"], branch=proposal["branch"], base_commit=base, head_commit=head,
                         files=changed, built=built)

    def run_proof_again(self, plan_id: int, fix_id: str) -> list[dict]:
        """Run proof again: only after a proof that failed, was interrupted or no longer covers the plan. Until the
        merge, also with a pull request open: its approvals stay on record, and count again once a proof has passed."""
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            fix = self._fix(db, plan, fix_id)
            refused = _no_new_proof(fix)
            if refused:
                raise Conflict(refused)
            self._start_proof(db, plan, db.get(ChangeRow, fix["change"]["id"]))
        return self.fix_states(plan_id)

    def open_pull_request(self, plan_id: int, fix_id: str, reviewers: list[str]) -> list[dict]:
        """Open pull request: inside the app, for a change whose proof has passed, with the reviewers who must approve."""
        if (not isinstance(reviewers, list) or not reviewers or not all(isinstance(r, str) and r in REVIEWERS for r in reviewers)
                or len(set(reviewers)) != len(reviewers)):
            raise BadRequest("Pick one or more reviewers from the list, each of them once.", field="reviewers")
        with self._plan_lock, self.db() as db:
            fix = self._fix(db, self._plan(db, plan_id), fix_id)
            refused = _no_pull_request(fix)
            if refused:
                raise Conflict(refused)
            number = 1 + (db.scalar(select(func.count(PullRequestRow.id)).where(PullRequestRow.plan_id == plan_id)) or 0)
            db.add(PullRequestRow(plan_id=plan_id, change_id=fix["change"]["id"], proof_id=fix["proof"]["id"], number=number,
                                  title=fix["change"]["title"], reviewers=[r for r in REVIEWERS if r in reviewers]))
            db.commit()
        return self.fix_states(plan_id)

    def approve(self, plan_id: int, fix_id: str, reviewer: str) -> list[dict]:
        """Approve: record one picked reviewer's approval, with the name and the time."""
        if not isinstance(reviewer, str) or reviewer not in REVIEWERS:
            raise BadRequest("That reviewer is not in the list.", field="reviewer")
        with self._plan_lock, self.db() as db:
            fix = self._fix(db, self._plan(db, plan_id), fix_id)
            refused = _no_approval(fix, reviewer)
            if refused:
                raise Conflict(refused)
            db.add(ApprovalRow(pull_request_id=fix["pull_request"]["id"], reviewer=reviewer, name=REVIEWERS[reviewer]))
            db.commit()
        return self.fix_states(plan_id)

    def merge(self, plan_id: int, fix_id: str) -> list[dict]:
        """Merge pull request (after Confirm merge): a two-parent commit on the connected branch of the app's own
        copy. Only when every picked reviewer has approved. Nothing is deployed and nothing else changes."""
        with self._plan_lock, self.db() as db:
            fix = self._fix(db, self._plan(db, plan_id), fix_id)
            refused = _no_merge(fix)
            if refused:
                raise Conflict(refused)
            connection, change, pull_request = fix["connection"], fix["change"], fix["pull_request"]
            try:
                repo = self._repo(connection["folder"])
                if repo.branch(change["branch"]) != change["head_commit"] or repo.branch(connection["branch"]) != change["base_commit"]:
                    raise GitRepoError("The repository has changed since this change was proved. Nothing was merged.")
                commit = repo.merge(connection["branch"], change["branch"], f"Merge pull request #{pull_request['number']}: {pull_request['title']}",
                                    MERGE_AUTHOR, int(time.time()))
            except GitRepoError as exc:
                raise Conflict(str(exc)) from exc
            except OSError as exc:
                raise Conflict("The repository could not be read. Nothing was merged.") from exc
            db.add(MergeRow(pull_request_id=pull_request["id"], merge_commit=commit))
            db.commit()
        return self.fix_states(plan_id)

    def patch_file(self, plan_id: int, fix_id: str) -> tuple[str, bytes]:
        """Download patch: (file name, bytes) of the pull request's change, in the layout git itself reads.
        Made from the repository each time, and the same bytes every time. Only while the change is offered."""
        with self._plan_lock, self.db() as db:
            fix = self._fix(db, self._plan(db, plan_id), fix_id)
            refused = _no_patch(fix)
            if refused:
                raise Conflict(refused)
            try:
                patch = self._patch_text(fix)
            except (GitRepoError, OSError) as exc:
                raise Conflict("The patch could not be made from the repository.") from exc
            return patch_name(fix["connection"]["repository"], fix["pull_request"]["number"]), patch.encode("utf-8")

    def _patch_text(self, fix: dict) -> str:
        """The change of one code fix as a patch, made from the plan's copy of the repository. The download of
        the evidence holds the same text."""
        change = fix["change"]
        repo = self._repo(fix["connection"]["folder"])
        return format_patch(repo.read_commit(change["head_commit"]), repo.files(change["base_commit"]),
                            repo.files(change["head_commit"]), PATCH_FOOTER)

    def retest_now(self, plan_id: int, fix_id: str) -> dict:
        """Retest now: exactly what Retest new version does, on the version the merged change is identical to.
        Returns the Evidence Lab view, where before and after then show."""
        with self._plan_lock, self.db() as db:
            fix = self._fix(db, self._plan(db, plan_id), fix_id)
            if fix["merge"] is None:
                raise Conflict(_no_retest_now(fix))
            version = fix["change"]["built"]["matches"]["version"]
        return self.start_retest(plan_id, version)  # takes the plan lock itself


def _answer(result: dict) -> dict:
    return {k: result[k] for k in ("item_id", "kind", "run_id", "phase")}


def _detail(review: dict) -> dict:
    """The part of a proof review that is stored as its detail."""
    return {k: review[k] for k in ("schema", "checks", "counts", "tests", "answers", "speed")}


def _known_template(change: ChangeRow) -> bool:
    """Does a stored change that says it came from a fix template name one this app has? If not, the record was
    changed (or was written by another version), and nothing about the change is believed."""
    return change.written_by != "fix_template" or change.template_id in research.TEMPLATE_IDS


def _shown_verdict(verdict: dict | None) -> dict | None:
    return {k: verdict[k] for k in ("run_id", "code", "reason_code", "control_outcome")} if verdict is not None else None
