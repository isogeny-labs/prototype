"""Change watch: a developer's change in the connected demo repository. Phase 6d, first part.

What is here reads, and one action writes a demo change into the assessment's own copy of the repository:

- `change_watch_state` reads the connected repository each time it is asked. Every branch that is neither the
  connected branch nor a branch of one of the app's own changes (the fix template's, Otto's) is a developer's change:
  a branch plus the commit it starts from. For each it says what the change touches, which locked tests of the plan
  are picked for it and why (fixed rules, by file; no Claude step), which registered demo program its code is (the
  byte-for-byte check), and which lines it adds that name old cryptography (flags; see `flags.py`).
- `bring_in_demo_change` writes one bundled demo change (`demo_changes.py`) as a push would: one branch with one
  commit by "Demo developer". It runs nothing.

Everything in a repository is data. Nothing read here is executed, and nothing here starts a test: that is the watch
run's job, on a person's click. This module words nothing either: `app/present/changewatch.py` does.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.changewatch import demo_changes, flags
from app.db import ChangeRow, CodeConnectionRow, ImportRow, MergeRow, PlanRow, PullRequestRow, TestSpecRow, iso
from app.engine import research
from app.errors import Conflict, NotFound
from app.fixes.gitrepo import Commit, GitRepo, GitRepoError, Person, changed_spots
from app.lab.testlab import read_spec
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


class ChangeWatchMixin:
    """Mixed into Lab. Needs: db, settings, _plan_lock and, from the other mixins: _plan, _items, _claims, _program_of, _repo."""

    # Declared for the type check only (nothing is assigned): from Lab and its other mixins.
    db: Callable[..., Any]
    _plan_lock: Any
    _plan: Callable[..., PlanRow]
    _items: Callable[..., list]
    _claims: Callable[..., list[dict]]
    _program_of: Callable[..., dict | None]
    _repo: Callable[[str], GitRepo]

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
                               "gives": None, "picked": [], "not_picked": [], "flags": [], "more_flags": 0, "status": "cant_run"}
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
        out.update(base=base, commits=start, files=files, touches_program=touched_program,
                   gives={"name": program["name"], "version": version} if version is not None else None,
                   picked=picked, not_picked=not_picked, flags=found[:flags.MAX_FLAGS], more_flags=max(0, len(found) - flags.MAX_FLAGS),
                   status="nothing_to_run" if not picked else "not_run" if version is not None else "cant_run")
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
            out.append(self._read_change(repo, name, head, main, code["program"], tests))
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
