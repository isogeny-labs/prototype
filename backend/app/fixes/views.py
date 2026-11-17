"""The Fixes step, put together: every fix of a plan as the screen shows it, and what Evidence Lab says about a
fix and about the code each side of before and after ran on.

This module gathers and passes on. It decides nothing and holds no sentence: where a fix stands comes from
changes.fix_states (worked out from the stored records, every verdict through the read gate), and the words are
in present_fixes.py. What it reads from a plan's copy of the repository is text to show: nothing from it is run."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.fixes import changes
from app.run import components
from app.present import changes as present_changes
from app.present import fixes as present_fixes
from app.ledger.fixes import group_fixes
from app.engine import research
from app.db import ImportRow, PlanItemRow, PlanRow, ReviewRow, TestRunRow, TestSpecRow
from app.fixes.gitrepo import GitRepoError
from app.present.results import TITLES
from app.lab.testlab import read_spec

# How a completed handshake is written down by the TLS test: the version, then the cipher suite it used.
_HANDSHAKE = re.compile(r"handshake completed \([^,()]+, ([A-Za-z0-9_-]+)\)")


def _block(lines: list[str], start: int, end: int, mark: str, part: dict) -> list[dict]:
    """The lines start..end of a file (counted from 0, end not included) with the unchanged lines around them
    that the change asks to be shown, each with its line number as people count it (from 1)."""
    first, last = max(0, start - part["context_before"]), min(len(lines), end + part["context_after"])
    return [{"n": n + 1, "mark": mark if start <= n < end else " ", "text": lines[n]} for n in range(first, last)]


def _text_lines(data: bytes) -> list[str]:
    lines = data.decode("utf-8").split("\n")  # at line feeds only, the way the change's line positions were counted
    return lines[:-1] if lines and lines[-1] == "" else lines


class FixesMixin:
    """Mixed into Lab. Needs: db, jobs, mode, and from the other mixins: _plan, _items, _result, _run_code, _fixes, _repo."""

    # Declared for the type check only (nothing is assigned): from Lab, and from DependenciesMixin (phase 4d).
    jobs: Any
    _dependency_fix_view: Callable[..., dict]
    _dependency_state: Callable[..., dict | None]
    _migration_states: Callable[..., list[dict]]

    def fixes_view(self, plan_id: int) -> dict:
        """The Fixes step for one plan: every fix as the screen shows it, in list order."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            # Asked first, on purpose. If a job ends while the rest is put together, the screen is told to ask
            # again and the next answer is the settled one. Asked last, a proof that ended in between would be
            # shown as still running with nothing left to make the screen ask again.
            busy = (self.jobs.busy(plan.id) or self.jobs.busy(("changes", plan.id)) or self.jobs.busy(("migration", plan.id))
                    or self.jobs.busy(("dependencies", plan.id)))
            pairs = self._fix_details(db, plan)
            shown = [detail for _, detail in pairs]
            view = present_fixes.view(plan.id, bool(imp.is_demo), shown, busy or any(d["status"]["busy"] for d in shown))
            # Phase 5b: the four work groups, each fix's group and the links for where it came from.
            systems = {s["item_id"]: s["key"] for s in self._migration_states(db, plan)}
            # The libraries of the dependency list, asked only when a fix is about a real library.
            listed: set = set()
            if any(state.get("real_library") for state, _ in pairs):
                deps = self._dependency_state(db, plan)
                listed = {(str(r.get("library") or r.get("name") or "").casefold(), str(r.get("version") or ""))
                          for r in (deps or {}).get("rows") or []}
            return group_fixes(view, pairs, systems, listed)

    @staticmethod
    def _answer_title(db, answer: dict) -> str:
        """The title of a test a fix answers. An advisory check carries its own (it names its advisory)."""
        kind = answer["kind"]
        if kind == research.ADVISORY_KIND:
            item = db.get(PlanItemRow, answer["item_id"])
            spec, _ = read_spec(db.get(TestSpecRow, item.spec_hash)) if item is not None else ({}, False)
            return research.title_of(kind, spec)
        return TITLES.get(kind, str(kind))

    def _fix_details(self, db, plan: PlanRow) -> list[tuple[dict, dict]]:
        """Every fix of the plan as (where it stands, what the Fixes step shows for it). The download uses the
        same pairs, so the words in it are the words on the screen."""
        states = self._fixes(db, plan)
        is_demo = bool(db.get(ImportRow, plan.import_id).is_demo)
        answered = {fix["id"]: self._answered(db, fix) for fix in states
                    if fix["kind"] == "text" and fix["source_kind"] not in ("migration", "applied_change", "dependency")}
        server_findings = sum(1 for _, address in answered.values() if address is not None)
        claims = self._claims(db.get(ImportRow, plan.import_id))
        several = len(research.servers(claims)) > 1 or len(research.programs(claims)) > 1
        tls_changes = self._tls_changes(db, plan)
        out = []
        for fix in states:
            titles = list(dict.fromkeys(self._answer_title(db, a) for a in fix["answers"]))
            if fix["source_kind"] == "migration":
                shown = self._migration_fix_view(db, plan, fix, is_demo)   # phase 4a: the migration plan's how-to and blockers
            elif fix["source_kind"] == "dependency":
                shown = self._dependency_fix_view(db, plan, fix, is_demo)  # phase 4d: update a library that blocks a track
            elif fix["source_kind"] == "applied_change":
                change = next(c for c in tls_changes if c["key"] == fix["change_key"])     # phase 4b: an Apply still in force
                rec = self._change_records(db, plan, change)
                shown = present_fixes.applied_change_fix(fix, present_changes.change_view(change, rec, self._change_gates(change, rec)),
                                                         change["address"], is_demo)
            elif fix["kind"] == "code":
                shown = self._code_fix_detail(db, plan, fix, titles, server_findings)
            else:
                run, address = answered[fix["id"]]
                shown = present_fixes.text_fix(fix, titles=titles, is_demo=is_demo, result=self._result(db, run), address=address,
                                               tls=self._tls_outcome(db, run) if fix["answers"][-1]["kind"] == "tls_versions" else None,
                                               name_target=several)
                change = next((c for c in tls_changes if c["_item_id"] == fix["answers"][-1]["item_id"]), None)
                if change is not None:   # phase 4b (SPEC 7c): try, approve, Apply and Roll back on the demo server
                    rec = self._change_records(db, plan, change)
                    box = present_changes.change_view(change, rec, self._change_gates(change, rec))
                    shown = present_fixes.with_change_box(shown, box)
            shown.setdefault("change_box", None)
            shown.setdefault("advisories", None)   # phase 4c: only a text fix for a real library carries any
            out.append((fix, shown))
        return out

    @staticmethod
    def _answered(db, fix: dict) -> tuple[TestRunRow, str | None]:
        """The newest failed result a text-only fix answers (by when it was run, whichever column shows it): its
        run, and the server address when the test is about a server (None when it is about the signing component)."""
        run = db.get(TestRunRow, max(answer["run_id"] for answer in fix["answers"]))
        target = read_spec(db.get(TestSpecRow, run.spec_hash))[0].get("target") or {}
        return run, target.get("address") if target.get("kind") == "server" else None

    @staticmethod
    def _tls_outcome(db, run: TestRunRow) -> dict:
        """What a failed "Old TLS versions" run recorded: what the file claims, the versions outside the claim that
        the server accepted, and the cipher suite each of those handshakes used (None where the record names none)."""
        detail = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first().detail
        states = run.raw["subject"]["versions"]
        suites = {}
        for version in detail["accepted_outside_claim"]:
            found = _HANDSHAKE.fullmatch(str((states.get(version) or {}).get("detail")))
            suites[version] = found.group(1) if found else None
        return {"claimed": list(detail["claimed"]), "accepted": list(detail["accepted_outside_claim"]), "suites": suites}

    def _code_fix_detail(self, db, plan: PlanRow, fix: dict, titles: list[str], server_findings: int) -> dict:
        change, proof, request = fix["change"], fix["proof"], fix["pull_request"]
        rows, modes, ran_sha256 = [], [self.mode.name], None
        if proof is not None:
            runs = [db.get(TestRunRow, t["proof"]["run_id"]) for t in proof["tests"] if t["proof"] is not None]
            rows = [{"kind": t["kind"], "title": TITLES.get(t["kind"], str(t["kind"])), "group": "server" if t["target"] in ("server", "other_program") else "code", "target": t["target"],
                     "first": self._result(db, db.get(TestRunRow, t["first"]["run_id"])) if t["first"] is not None else None,
                     "proof": self._result(db, db.get(TestRunRow, t["proof"]["run_id"])) if t["proof"] is not None else None,
                     "job": t["job"], "check": t["check"]} for t in proof["tests"]]
            modes = list(dict.fromkeys(run.mode for run in runs)) or modes
            # What the tests ran on is what each run wrote down when it started: the registered component's own SHA-256.
            ran_sha256 = next((code["file_sha256"] for code in (self._run_code(db, run.id) for run in runs) if code is not None), None)
        if change is not None and ran_sha256 is None:
            ran_sha256 = self._registered_sha256(change["built"]["matches"])  # no run yet: what a run would run on
        return present_fixes.code_fix(
            fix, plan_id=plan.id, titles=titles, server_findings=server_findings, plan_tests=len(self._items(db, plan.id)),
            reviewers=changes.REVIEWERS, parts=self._changed_lines(fix) if change is not None else None, rows=rows, modes=modes,
            ran_sha256=ran_sha256,
            patch_name=changes.patch_name(fix["connection"]["repository"], request["number"]) if request is not None else None)

    @staticmethod
    def _registered_sha256(matches: dict | None) -> str | None:
        path = components.lookup(matches["name"], matches["version"]) if matches else None
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
        except OSError:
            return None

    def _changed_lines(self, fix: dict) -> list[dict] | None:
        """The before and after lines of each part of a change, read from the plan's own copy of the repository
        (None when they can't be read). They are text for the screen; nothing here is run."""
        out = []
        try:
            repo = self._repo(fix["connection"]["folder"])
            for file in fix["change"]["files"]:
                old, new = _text_lines(repo.read_blob(file["old_blob"])), _text_lines(repo.read_blob(file["new_blob"]))
                for part in file["parts"]:
                    out.append({"title": part["title"], "why": part["why"],
                                "removed": part["old_end"] - part["old_start"], "added": part["new_end"] - part["new_start"],
                                "before": _block(old, part["old_start"], part["old_end"], "-", part),
                                "after": _block(new, part["new_start"], part["new_end"], "+", part)})
        except (GitRepoError, OSError, UnicodeDecodeError):
            return None
        return out

    # ---------------------------------------------------------------- Evidence Lab

    def _fix_lines(self, db, plan: PlanRow) -> dict[int, dict]:
        """The one line Evidence Lab shows about a fix, for each failed result that has one (by run id)."""
        lines = {}
        tls_items = {c["_item_id"] for c in self._tls_changes(db, plan)}
        for fix in self._fixes(db, plan):
            line = present_fixes.fix_line(fix)
            if fix["kind"] != "code" and fix["answers"] and fix["answers"][-1]["item_id"] in tls_items:
                # phase 4b (SPEC 7c): on our own demo server the setting can be tried on a test copy and applied
                line = present_fixes.server_change_line(line)
            lines.update({answer["run_id"]: line for answer in fix["answers"]})
        return lines

    def _column_code(self, db, rows: list[dict], side: str) -> dict | None:
        """The code one side of before and after ran on ("result" or "after"), when every result on that side in
        which a component of ours ran did so on the same code; otherwise None, and nothing is said about it."""
        codes = [code for code in (self._run_code(db, row[side]["run_id"]) for row in rows if row[side] is not None) if code is not None]
        return codes[0] if codes and all(code == codes[0] for code in codes) else None
