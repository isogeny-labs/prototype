"""Change watch: a developer's change in the connected demo repository. Phase 6d, first part.

What is here reads, one action writes a demo change into the assessment's own copy of the repository, and one
starts the tests picked for a change (the watch run):

- `change_watch_state` reads the connected repository each time it is asked. Every branch that is neither the
  connected branch nor a branch of one of the app's own changes (the fix template's, Otto's) is a developer's change:
  a branch plus the commit it starts from. For each it says what the change touches, which locked tests of the plan
  are picked for it and why (fixed rules, by file; no Claude step), which registered demo program its code is (the
  byte-for-byte check), and which lines it adds that name old cryptography (flags; see `flags.py`).
- `bring_in_demo_change` writes one bundled demo change (`demo_changes.py`) as a push would: one branch with one
  commit by "Demo developer". It runs nothing.

- `run_picked_tests` is the watch run. It starts only when a person asks. After the byte-for-byte check it runs
  the picked tests on the change's code, through the same runner and the same locked tests as every other run. "Before"
  is each test's newest reviewed run on exactly the code the change starts from; where there is none, that test also
  runs on that code. The separate reviewer reviews every run, and then says what differs from before
  (`RuleReviewer.review_watch`): that sets the change's status word and nothing else. These runs are kept apart. They
  never stand in for a result of the assessment's own tests.

Everything in a repository is data. Nothing read here is executed; what runs in a watch run is the registered demo
program the change's code is byte for byte, never a file from the repository. This module words nothing:
`app/present/changewatch.py` does.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable

from sqlalchemy import select

from app.canonical import canonical_bytes
from app.changewatch import demo_changes, flags
from app.db import (
    ChangeRow, CodeConnectionRow, ImportRow, MergeRow, PlanRow, PullRequestRow, ReviewRow, RunCodeRow, TestRunRow, TestSpecRow, WatchReviewRow,
    WatchRunRow, iso,
)
from app.engine import research
from app.engine.reviewer import WATCH_NO_RESULT_CODES, WATCH_SCHEMA
from app.errors import Conflict, NotFound
from app.fixes.gitrepo import Commit, GitRepo, GitRepoError, Person, changed_spots
from app.lab.testlab import BUSY, WATCH_PHASES, read_spec
from app import demo_repo
from app.run import components

DEMO_DEVELOPER = Person("Demo developer", "demo-developer@example.invalid")
MAX_CHANGES = 50            # branches listed; a demo repository holds a handful
MAX_COMMITS = 100           # how far back a branch is followed to find where it starts
MAX_TEXT_BYTES = 200_000    # a larger file is listed, but its lines are not lined up
CONTEXT = 3                 # unchanged lines shown around a changed place


def change_id(head: str) -> str:
    """The id of a change in addresses and links: it names the exact code, so a branch that moves is another change."""
    return f"change-{head[:12]}"


def _lines(data: bytes) -> list[str]:
    lines = data.decode("utf-8").split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _block(lines: list[str], start: int, end: int, mark: str) -> list[dict]:
    first, last = max(0, start - CONTEXT), min(len(lines), end + CONTEXT)
    return [{"n": n + 1, "mark": mark if start <= n < end else " ", "text": lines[n]} for n in range(first, last)]


def _file(name: str, old: bytes | None, new: bytes | None, program_file: str | None) -> dict:
    """What a change does to one file: added, changed or removed, how many lines, the changed places with the lines
    around them, and the lines it adds (for the flags)."""
    state = "added" if old is None else "removed" if new is None else "changed"
    out: dict[str, Any] = {"name": name, "state": state, "is_program": name == program_file, "text": False, "added": None, "removed": None,
                           "blocks": [], "added_lines": []}
    if len(old or b"") > MAX_TEXT_BYTES or len(new or b"") > MAX_TEXT_BYTES:
        return out
    try:
        before, after = (old or b"").decode("utf-8"), (new or b"").decode("utf-8")
    except UnicodeDecodeError:
        return out
    old_lines, new_lines = _lines((old or b"")), _lines((new or b""))
    spots = changed_spots(before, after)
    out.update(text=True, added=sum(s.added for s in spots), removed=sum(s.removed for s in spots))
    for spot in spots:
        # (a spot's end can lie one past the last line when only the last line break changed)
        old_end, new_end = min(spot.old_end, len(old_lines)), min(spot.new_end, len(new_lines))
        out["blocks"].append({"before": _block(old_lines, spot.old_start, old_end, "-"), "after": _block(new_lines, spot.new_start, new_end, "+")})
        out["added_lines"] += [(n + 1, new_lines[n]) for n in range(spot.new_start, new_end)]
    return out


def _watch_detail(review: dict) -> dict:
    """What is stored of a watch review beside its status (and compared again at every read)."""
    return {k: review[k] for k in ("schema", "code_is_ours", "counts", "tests")}


class ChangeWatchMixin:
    """Mixed into Lab. Needs: db, settings, jobs, reviewer, _plan_lock, _proof_lock and, from the other mixins: _plan, _items,
    _claims, _program_of, _repo, _running, _submit, _latest_run, _verdict."""

    # Declared for the type check only (nothing is assigned): from Lab and its other mixins.
    db: Callable[..., Any]
    _plan_lock: Any
    _plan: Callable[..., PlanRow]
    _items: Callable[..., list]
    _claims: Callable[..., list[dict]]
    _program_of: Callable[..., dict | None]
    _repo: Callable[[str], GitRepo]
    _running: Callable[[int], str | None]
    _submit: Callable[..., Any]
    _verdict: Callable[..., dict | None]
    _latest_run: Callable[..., TestRunRow | None]
    _proof_lock: Any
    _stopping: bool
    jobs: Any
    reviewer: Any

    # ---------------------------------------------------------------- where the code stands

    @staticmethod
    def _watch_program(plan: PlanRow) -> dict | None:
        """The plan's own program, when it is one of our demo programs whose code can be connected."""
        path = components.lookup(plan.component_name, plan.component_version)
        if path is None or demo_repo.bundled(plan.component_name) is None:
            return None
        return {"name": plan.component_name, "version": plan.component_version, "file": path.name}

    def _watch_code(self, db, plan: PlanRow) -> dict:
        """{"state": "no_code" | "not_connected" | "connected", "program", "connection", "merged"}."""
        program = self._watch_program(plan)
        connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == plan.id)).first()
        if connection is None:
            return {"state": "no_code" if program is None else "not_connected", "program": program, "connection": None, "merged": False}
        merged = db.scalars(select(MergeRow).join(PullRequestRow, MergeRow.pull_request_id == PullRequestRow.id)
                            .where(PullRequestRow.plan_id == plan.id)).first() is not None
        if program is None:      # (connected for a program we name: the registry has not lost it since)
            program = {"name": connection.component_name, "version": connection.component_version, "file": None}
        return {"state": "connected", "program": program, "connection": connection, "merged": merged}

    # ---------------------------------------------------------------- reading the changes

    def _tests_for(self, db, plan: PlanRow) -> list[dict]:
        """Every test of the plan with the program it runs, for the picking rules."""
        claims = self._claims(db.get(ImportRow, plan.import_id))
        out = []
        for item in self._items(db, plan.id):
            row = db.get(TestSpecRow, item.spec_hash)
            spec, _ = read_spec(row)
            kind = row.kind if row is not None else None
            target = spec.get("target") or {}
            out.append({"item_id": item.id, "kind": kind, "title": research.title_of(kind, spec), "program": self._program_of(plan, claims, spec),
                        "server": str(target.get("address")) if target.get("kind") == "server" and target.get("address") else None})
        return out

    @staticmethod
    def _pick(tests: list[dict], program: dict, touched_program: bool) -> tuple[list[dict], list[dict]]:
        """The picking rules (fixed; by file). A change that touches the file of the program under test picks every
        test of the plan that runs that program. A test that does not run that code is not picked. A change that
        touches no such file picks nothing. Each test comes with the rule that placed it."""
        picked, not_picked = [], []
        for test in tests:
            runs = test["program"]
            entry = {"item_id": test["item_id"], "kind": test["kind"], "title": test["title"]}
            if runs is not None and runs["own"]:
                if touched_program:
                    picked.append({**entry, "rule": "runs_the_program"})
                else:
                    not_picked.append({**entry, "rule": "program_not_touched"})
            elif runs is not None:
                not_picked.append({**entry, "rule": "other_program", "other": runs["label"]})
            elif test["server"]:
                not_picked.append({**entry, "rule": "server_test", "server": test["server"]})
            else:
                not_picked.append({**entry, "rule": "no_program"})
        return picked, not_picked

    def _read_change(self, repo: GitRepo, name: str, head: str, main: str, program: dict, tests: list[dict]) -> dict:
        """One developer's change, read from the repository. A branch that can't be read is still listed, with why."""
        out: dict[str, Any] = {"id": change_id(head), "branch": name, "head": head, "base": None, "commits": 0, "title": name, "message": "",
                               "author": None, "is_demo": False, "when": None, "files": [], "problem": None, "touches_program": False,
                               "gives": None, "starts_from": None, "picked": [], "not_picked": [], "flags": [], "more_flags": 0,
                               "status": "cant_run", "digests": [], "run": None}
        try:
            history: list[Commit] = repo.history(head, MAX_COMMITS)
            tip = history[0]
            out.update(title=tip.title[:200] or name, message=tip.message[:2000], author=tip.author.name[:100],
                       is_demo=tip.author == DEMO_DEVELOPER, when=iso(datetime.fromtimestamp(tip.author_time, timezone.utc)))
            start = next((n for n, c in enumerate(history) if n > 0 and repo.is_ancestor(c.sha, main)), None)
            if start is None:
                out["problem"] = "no_start"       # it does not start from the connected branch (or starts too far back)
                return out
            base = history[start].sha
            old, new = repo.files(base), repo.files(head)
        except (GitRepoError, OSError, OverflowError, ValueError):
            out["problem"] = "unreadable"
            return out
        files = [_file(n, old.get(n), new.get(n), program["file"]) for n in sorted(set(old) | set(new)) if old.get(n) != new.get(n)]
        touched_program = any(f["is_program"] for f in files)
        picked, not_picked = self._pick(tests, program, touched_program)
        found = [flag for f in files for flag in flags.named_in(f["name"], f["added_lines"])]
        for f in files:
            del f["added_lines"]
        # The byte-for-byte check: which registered demo program is exactly the code this change leaves. Nothing is run to find out.
        version = components.registered_version(program["name"], new)
        # the code the change starts from: which registered demo program it is (a watch run compares with runs on exactly it)
        base_version = components.registered_version(program["name"], old)
        out.update(base=base, commits=start, files=files, touches_program=touched_program,
                   gives={"name": program["name"], "version": version} if version is not None else None,
                   starts_from={"name": program["name"], "version": base_version} if base_version is not None else None,
                   picked=picked, not_picked=not_picked, flags=found[:flags.MAX_FLAGS], more_flags=max(0, len(found) - flags.MAX_FLAGS),
                   status="nothing_to_run" if not picked else "not_run" if version is not None and base_version is not None else "cant_run",
                   digests=[{"name": f["name"], "state": f["state"],
                             "old_sha256": hashlib.sha256(old[f["name"]]).hexdigest() if f["name"] in old else None,
                             "new_sha256": hashlib.sha256(new[f["name"]]).hexdigest() if f["name"] in new else None} for f in files])
        return out

    def _developer_changes(self, db, plan: PlanRow, code: dict) -> tuple[list[dict], bool]:
        """(every developer's change in the connected repository, could the repository be read?)."""
        connection = code["connection"]
        try:
            repo = self._repo(connection.folder)
            main = repo.branch(connection.branch)
            branches = repo.branches()
        except (GitRepoError, OSError):
            return [], False
        if main is None:
            return [], False
        ours = set(db.scalars(select(ChangeRow.branch).where(ChangeRow.plan_id == plan.id)).all()) | {connection.branch}
        tests = self._tests_for(db, plan)
        out = []
        for name, head in branches.items():
            if name in ours:
                continue
            try:
                if repo.is_ancestor(head, main):
                    continue                      # nothing on it that the connected branch does not have
            except (GitRepoError, OSError):
                pass                              # listed below, with why it can't be read
            change = self._read_change(repo, name, head, main, code["program"], tests)
            self._with_watch_run(db, plan, change)
            out.append(change)
            if len(out) >= MAX_CHANGES:
                break
        out.sort(key=lambda c: (c["when"] or "", c["branch"]), reverse=True)     # newest first
        return out, True

    def _demo_menu(self, code: dict, changes: list[dict]) -> list[dict]:
        """The bundled demo changes, each with whether it can be brought in now and, if not, why not (as a key)."""
        there = {c["branch"] for c in changes}
        out = []
        for change in demo_changes.bundled():
            blocked = None
            if code["state"] != "connected":
                blocked = code["state"]
            elif change.branch in there:
                blocked = "already_in"
            elif change.offered == "after_merge" and not code["merged"]:
                blocked = "needs_merge"
            out.append({"key": change.key, "title": change.title, "what_it_does": change.what_it_does, "branch": change.branch, "blocked": blocked})
        return out

    def change_watch_state(self, plan_id: int) -> dict:
        """Where Change watch stands for this plan, as plain data with no wording. It only reads."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            code = self._watch_code(db, plan)
            changes, readable = self._developer_changes(db, plan, code) if code["state"] == "connected" else ([], True)
            connection = code["connection"]
            return {"plan_id": plan.id,
                    "code": {"state": code["state"] if readable else "unreadable", "program": code["program"], "merged": code["merged"],
                             "repository": connection.repository if connection is not None else None,
                             "branch": connection.branch if connection is not None else None},
                    "changes": changes, "menu": self._demo_menu(code, changes)}

    # ---------------------------------------------------------------- the watch run: record, review, read gate

    def _watch_before(self, db, entry: dict, name: str, base_version: str, base_sha256: str) -> int | None:
        """The newest reviewed run of this locked test on exactly the code the change starts from (the same registered
        program, the same bytes), whatever it was run for; None when there is none, or when the newest one is no result
        (it could not run, or can't be trusted): then the test runs on that code again."""
        row = db.execute(select(TestRunRow.id, ReviewRow.code)
                         .join(RunCodeRow, RunCodeRow.run_id == TestRunRow.id).join(ReviewRow, ReviewRow.run_id == TestRunRow.id)
                         .where(TestRunRow.plan_item_id == entry["item_id"], TestRunRow.spec_hash == entry["spec_hash"],
                                RunCodeRow.component_name == name, RunCodeRow.component_version == base_version,
                                RunCodeRow.file_sha256 == base_sha256)
                         .order_by(TestRunRow.id.desc()).limit(1)).first()
        return row[0] if row is not None and row[1] not in WATCH_NO_RESULT_CODES else None

    def _watch_tests(self, db, watch: WatchRunRow) -> list[dict]:
        """For each test of a watch run, in its order: the run it is compared with and its run on the change's code,
        each as the read gate lets it through (None where there is no reviewed run yet)."""
        out = []
        for entry in watch.items:
            before = (db.get(TestRunRow, entry["before_run_id"]) if entry.get("before_run_id") is not None
                      else self._latest_run(db, entry["item_id"], "watch_base", watch.id))
            now = self._latest_run(db, entry["item_id"], "watch", watch.id)
            out.append({"item_id": entry["item_id"], "kind": entry["kind"], "spec_hash": entry["spec_hash"],
                        "before_made_here": entry.get("before_run_id") is None,
                        "before": self._verdict(db, before) if before is not None else None,
                        "now": self._verdict(db, now) if now is not None else None})
        return out

    def _watch_matches(self, db, watch: WatchRunRow) -> dict | None:
        """The byte-for-byte check, made again from the repository as it is now: is the change's code still exactly the
        registered demo program that ran? None when it is not, or when the repository can't be read."""
        plan = db.get(PlanRow, watch.plan_id)
        connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == watch.plan_id)).first()
        if plan is None or connection is None:
            return None
        try:
            version = components.registered_version(plan.component_name, self._repo(connection.folder).files(watch.head_commit))
        except (GitRepoError, OSError):
            return None
        return {"name": plan.component_name, "version": version} if version is not None else None

    @staticmethod
    def _watch_record(watch: WatchRunRow, tests: list[dict], matches: dict | None) -> dict:
        """The watch record: what the reviewer is given and what the watch run's fingerprint is made from. Stored facts
        only, in the form they are read back, so it comes out the same on every read."""
        def part(verdict: dict | None) -> dict | None:
            return {k: verdict[k] for k in ("run_sha256", "code", "reason_code", "control_outcome")} if verdict is not None else None
        return {"schema": WATCH_SCHEMA,
                "change": {"branch": watch.branch, "base_commit": watch.base_commit, "head_commit": watch.head_commit, "files": watch.files},
                "matches": matches, "version": watch.version, "base_version": watch.base_version,
                "tests": [{"item_id": t["item_id"], "kind": t["kind"], "spec_hash": t["spec_hash"],
                           "before": part(t["before"]), "now": part(t["now"])} for t in tests]}

    def _watch_run_finished(self, watch_id: int) -> None:
        """Called by every job of a watch run once its run is reviewed. When every picked test has both its runs, the
        watch run itself is reviewed and the answer stored, once. Nothing is written while the app is closing."""
        with self._proof_lock, self.db() as db:
            watch = db.get(WatchRunRow, watch_id)
            if self._stopping or watch is None or db.scalars(select(WatchReviewRow).where(WatchReviewRow.watch_run_id == watch_id)).first():
                return
            tests = self._watch_tests(db, watch)
            if any(t["before"] is None or t["now"] is None for t in tests):
                return  # other runs of this watch run are still waiting or running
            review = self.reviewer.review_watch(self._watch_record(watch, tests, self._watch_matches(db, watch)))
            db.add(WatchReviewRow(watch_run_id=watch_id, reviewer=review["reviewer"], record_sha256=review["record_sha256"],
                                  status=review["status"], detail=_watch_detail(review)))
            db.commit()

    def _watch_review(self, db, watch: WatchRunRow, tests: list[dict]) -> dict | None:
        """The read gate for a watch run. None while it has no review. Otherwise the stored review, believed only if
        reviewing the stored records again gives exactly it; if not, the run reads "Couldn't trust this run"."""
        stored = db.scalars(select(WatchReviewRow).where(WatchReviewRow.watch_run_id == watch.id)).first()
        if stored is None:
            return None
        try:
            again = self.reviewer.review_watch(self._watch_record(watch, tests, self._watch_matches(db, watch)))
            believed = ((stored.reviewer, stored.record_sha256, stored.status, canonical_bytes(stored.detail))
                        == (again["reviewer"], again["record_sha256"], again["status"], canonical_bytes(_watch_detail(again))))
        except Exception:
            believed = False
        if not believed:
            return {"reviewed_at": iso(stored.created_at), "believed": False, "status": "couldnt_trust", "record_sha256": None,
                    "counts": None, "tests": []}
        return {"reviewed_at": iso(stored.created_at), "believed": True, "status": stored.status, "record_sha256": stored.record_sha256,
                "counts": stored.detail["counts"], "tests": stored.detail["tests"]}

    def _watch_state(self, db, plan: PlanRow, watch: WatchRunRow) -> dict:
        """One watch run: each test's run before and now, its live jobs, and the review."""
        # (the live jobs are read BEFORE the stored records, for the reason given at ChangesMixin._proof_state)
        live = {(job.key[0], job.key[1]): job for job in self.jobs.live(plan.id) if job.key[1] in WATCH_PHASES}
        tests = self._watch_tests(db, watch)
        review = self._watch_review(db, watch, tests)
        placed = {t["item_id"]: t for t in review["tests"]} if review is not None else {}
        rows = []
        for t in tests:
            jobs = [live.get((t["item_id"], phase)) for phase, side in (("watch_base", "before"), ("watch", "now")) if t[side] is None]
            job = next((j for j in jobs if j is not None), None)
            rows.append({"item_id": t["item_id"], "kind": t["kind"], "before_made_here": t["before_made_here"],
                         "before": {k: t["before"][k] for k in ("run_id", "code")} if t["before"] is not None else None,
                         "now": {k: t["now"][k] for k in ("run_id", "code")} if t["now"] is not None else None,
                         "job": {"status": job.status, "progress_text": job.progress_text, "progress_percent": job.progress_percent} if job is not None else None,
                         "outcome": placed[t["item_id"]]["outcome"] if t["item_id"] in placed else None})
        state = "running" if live else "interrupted" if review is None else "reviewed"
        return {"id": watch.id, "started_at": iso(watch.started_at), "state": state, "version": watch.version, "base_version": watch.base_version,
                "finished": sum(1 for t in tests if t["before"] is not None and t["now"] is not None), "total": len(tests),
                "tests": rows, "review": review}

    def _with_watch_run(self, db, plan: PlanRow, change: dict) -> None:
        """Put the change's newest watch run on it, and let that run decide the status: a run counts for the change only
        while it is a run of exactly this code and of exactly the tests picked now."""
        if change["problem"] is not None or change["base"] is None:
            return
        watch = db.scalars(select(WatchRunRow).where(WatchRunRow.plan_id == plan.id, WatchRunRow.branch == change["branch"],
                                                     WatchRunRow.head_commit == change["head"], WatchRunRow.base_commit == change["base"])
                           .order_by(WatchRunRow.id.desc()).limit(1)).first()
        if watch is None:
            return
        run = self._watch_state(db, plan, watch)
        items = {i.id: i.spec_hash for i in self._items(db, plan.id)}
        run["covers_picked"] = ({(e["item_id"], e["spec_hash"]) for e in watch.items}
                                == {(t["item_id"], items.get(t["item_id"])) for t in change["picked"]})
        change["run"] = run
        if run["state"] == "running":
            change["status"] = "running"
        elif run["state"] == "reviewed" and run["covers_picked"] and change["status"] == "not_run":
            change["status"] = run["review"]["status"]

    def run_picked_tests(self, plan_id: int, change: str) -> dict:
        """Run the picked tests (then: Run again). The one way a watch run starts, and only when a person asks.
        First the byte-for-byte check: the changed code must be exactly one of our registered demo programs, and so must
        the code it starts from; that registered program is what then runs. Nothing from the repository runs."""
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            code = self._watch_code(db, plan)
            if code["state"] != "connected":
                raise Conflict("Connect the demo code first. Connect demo code is on Fixes.")
            changes, readable = self._developer_changes(db, plan, code)
            found = next((c for c in changes if c["id"] == change), None) if readable and isinstance(change, str) else None
            if found is None:
                raise NotFound("That change is not in the connected repository.")
            running = self._running(plan_id)
            if running:
                raise Conflict(BUSY[running])
            if found["problem"] is not None:
                raise Conflict("This change could not be read from the repository, so nothing was run.")
            if not found["picked"]:
                raise Conflict("No test is picked for this change, so there is nothing to run.")
            if found["gives"] is None:
                raise Conflict("The changed code is not the same as one of our registered demo programs, so nothing was run.")
            if found["starts_from"] is None:
                raise Conflict("The code this change starts from is not one of our registered demo programs, so there is nothing to compare with. Nothing was run.")
            name, version, base_version = code["program"]["name"], found["gives"]["version"], found["starts_from"]["version"]
            path = components.lookup(name, base_version)
            try:
                base_sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
            except OSError:
                base_sha256 = None
            if base_sha256 is None:
                raise Conflict("The demo program this change starts from could not be read, so nothing was run.")
            items = {i.id: i for i in self._items(db, plan.id)}
            entries = []
            for test in found["picked"]:
                entry = {"item_id": test["item_id"], "spec_hash": items[test["item_id"]].spec_hash, "kind": test["kind"]}
                entries.append({**entry, "before_run_id": self._watch_before(db, entry, name, base_version, base_sha256)})
            watch = WatchRunRow(plan_id=plan.id, branch=found["branch"], base_commit=found["base"], head_commit=found["head"],
                                version=version, base_version=base_version, files=found["digests"], items=entries,
                                not_picked=[{k: t[k] for k in ("item_id", "kind", "rule")} for t in found["not_picked"]])
            db.add(watch)
            db.commit()
            for entry in entries:
                item = items[entry["item_id"]]
                # on the change's code; the speed test compares with the code the change starts from
                self._submit(plan, item, "watch", SimpleNamespace(id=watch.id, version=version), baseline=base_version)
                if entry["before_run_id"] is None:      # no reviewed run on exactly the code before: it runs on that code too
                    self._submit(plan, item, "watch_base", SimpleNamespace(id=watch.id, version=base_version), keep_baseline=False)
        return self.change_watch_state(plan_id)

    # ---------------------------------------------------------------- the one action: a demo change comes in

    def bring_in_demo_change(self, plan_id: int, key: str) -> dict:
        """Bring in a demo change (Demo data): write the bundled change into this plan's own copy of the repository as
        a push would, one new branch with one commit by "Demo developer" on top of the connected branch. Nothing is
        run, and nothing else is written."""
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            change = demo_changes.find(key)
            if change is None:
                raise NotFound("That demo change does not exist.")
            code = self._watch_code(db, plan)
            if code["state"] == "no_code":
                raise Conflict("This assessment has no code that can be connected, so no developer's change can come in here.")
            if code["state"] != "connected":
                raise Conflict("Connect the demo code first. Connect demo code is on Fixes.")
            if change.offered == "after_merge" and not code["merged"]:
                raise Conflict("This demo change undoes a merged fix, so it is offered once a fix is merged.")
            connection = code["connection"]
            try:
                repo = self._repo(connection.folder)
                main = repo.branch(connection.branch)
                if main is None:
                    raise GitRepoError("The connected branch is missing.")
                if repo.branch(change.branch) is not None:
                    raise Conflict("This demo change is already in the repository.")
                files = {**repo.files(main), **demo_changes.content(change)}
                if files == repo.files(main):
                    raise Conflict("This demo change would change nothing in the repository as it stands, so it was not brought in.")
                repo.branch_from(change.branch, main, files, change.message, DEMO_DEVELOPER, int(time.time()))
            except (GitRepoError, OSError, demo_changes.DemoChangeError) as exc:
                raise Conflict("The demo change could not be written into the repository. Nothing was changed.") from exc
        return self.change_watch_state(plan_id)


__all__ = ["ChangeWatchMixin", "DEMO_DEVELOPER", "change_id"]
