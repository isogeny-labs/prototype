"""Phase 5b: every check in an assessment, wherever it was started, in the four work groups.

A check is one locked test run in one place: a claim checked by Verify, a test of the plan, its retest, its run in a fix
proof, a system's own measurement, a try of a change on a test copy, a library measured on a public copy. A row shows
its newest run, worded by `Lab._result` exactly as the page it came from words it, and keeps its earlier runs. Each run
belongs to one row only. Nothing here runs anything or decides anything.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from sqlalchemy import select

from app.db import (
    ApplyRow, ChangeTryRow, ImportRow, PlanItemRow, PlanRow, ProofRow, RetestProgramRow, RetestRow, ReviewRow, RollbackRow,
    TestRunRow, TestSpecRow, VerifyRunRow, WatchRunRow, iso,
)
from app.engine import research
from app.errors import NotFound
from app.lab.testlab import HIDDEN_ORIGINS, WATCH_PHASES, read_spec
from app.ledger import groups as G
from app.names import join_and
from app.present.results import status_view

ORIGINS = {
    "verify": "Verify", "plan": "Test plan", "retest": "Retest", "proof": "Fix proof", "try": "Try on a test copy",
    "after_apply": "After Apply", "after_rollback": "After Roll back", "measure": "Measure status",
    "public_copy": "Measure on a public copy",
    "watch": "Change watch",        # phase 6d: a run of the tests picked for a developer's change
}
VERIFY_TONES = {"True": "pass", "False": "fail"}
PHASE_ORIGIN = {"first": "plan", "retest": "retest", "proof": "proof", "migration": "measure", "dependencies": "public_copy",
                "try": "try", "try_nginx": "try", "watch": "watch", "watch_base": "watch"}
# The claim kinds a server test checks (a software test names its claim by ref).
TEST_CLAIM_KINDS = {"tls_versions": ("protocol_versions", "cipher_suites"), "certificate": ("certificate",),
                    "pq_readiness": ("post_quantum",)}


def _measure_key(row: dict) -> list | None:
    """What a check measures, when the same measurement is also made elsewhere (see `_mark_same_measurements`)."""
    if row.get("kind") == "verify":
        claim = (row.get("verify") or {}).get("claim") or {}
        if claim.get("location_kind") == "server" and claim.get("kind") == "post_quantum":
            row["pq_claim"] = True
            return ["server", claim.get("location")]
        if claim.get("location_kind") == "software":
            return ["software", claim.get("location")]
        return None
    if row.get("kind") == "pq_readiness" and str(row.get("id", "")).startswith("test-"):
        return ["server", row.get("ran_on")]
    if row.get("kind") == "pq_status" and str(row.get("id", "")).startswith("system-"):
        return ["server", row.get("ran_on")]
    if row.get("kind") == "signing_status" and str(row.get("id", "")).startswith("system-"):
        return ["software", row.get("ran_on")]
    return None


# The 5c fixes: on Checks the Crypto tests group is in four labelled parts. A retest's row sits in the block of the
# version that retest ran on, and a proof's row in the block of its proof: "retest-12-on-3" is test 12 in the block that
# retest 3 opened, "proof-12-in-2" is test 12 in proof 2. The older ids ("retest-12", "proof-12") still open the newest.
# Phase 6d: "watch-12-in-4" is test 12 on a developer's change in watch run 4, and "watchbase-12-in-4" the same test on the
# code that change starts from, where it had to be run for the comparison.
BLOCK_ROW = re.compile(r"^(retest|proof|watch|watchbase)-(\d+)-(on|in)-(\d+)$")
ON_THE_CODE_BEFORE = "on the code before the change"
AS_IT_IS = "tested again as it is"
NO_RETEST = "No retest yet. Retest new version reruns every test in the plan on another version."


def _watch_ran_on(words: str | None, watch: WatchRunRow, before: bool) -> str:
    """Where a run of a developer's change ran: the program, and which code of the change (its own, or the code it starts from)."""
    which = (f"the code before the change on {watch.branch} (commit {watch.base_commit[:7]})" if before
             else f"the change on {watch.branch} (commit {watch.head_commit[:7]})")
    return f"{words}, {which}" if words else which[0].upper() + which[1:]


def short(text: str | None, limit: int = 12) -> str | None:
    """A long id shortened for a table: its first characters (the full value is in the panel)."""
    return text if text is None or len(text) <= limit else text[:limit]


class LedgerMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    jobs: Any
    _plan: Callable[..., PlanRow]
    _result: Callable[..., dict | None]
    otto_result_blocks: Callable[..., dict[int, dict]]     # from ProposalsMixin (phase 5c)
    _migration_states: Callable[..., list[dict]]
    dependencies_view: Callable[..., dict]
    fix_states: Callable[[int], list[dict]]

    # ---------------------------------------------------------------- the rows

    def ledger(self, plan_id: int) -> dict:
        """Every check of one plan: {"rows": [...], "claims": n, "verified": n, "open": {group: n}}. Rows carry their run
        ids (newest first) so a detail can be built; the views drop them."""
        deps = self._ledger_dependencies(plan_id)
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            rows: list[dict] = []
            claims = list(imp.claims) if imp is not None else []
            verified = self._ledger_verify(db, imp, rows)
            items = db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan_id).order_by(PlanItemRow.position)).all()
            specs = {i.id: read_spec(db.get(TestSpecRow, i.spec_hash))[0] for i in items}
            systems = {s["item_id"]: s for s in self._migration_states(db, plan)}
            runs = db.scalars(select(TestRunRow).where(TestRunRow.plan_id == plan_id).order_by(TestRunRow.id)).all()
            reviewed = set(db.scalars(select(ReviewRow.run_id).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                                      .where(TestRunRow.plan_id == plan_id)).all())
            after = self._after_change_runs(db, plan, items, specs, runs)
            tries = {t.id: t for t in db.scalars(select(ChangeTryRow).where(ChangeTryRow.plan_id == plan_id)).all()}
            by_key: dict[str, dict] = {}
            for run in runs:
                item = next((i for i in items if i.id == run.plan_item_id), None)
                if item is None or (item.removed and run.phase == "first"):
                    continue
                key, base = self._row_key(run, item, specs.get(item.id) or {}, systems, tries, deps, claims)
                if key is None:
                    continue
                row = by_key.get(key)
                if row is None:
                    row = by_key[key] = {**base, "run_ids": [], "origins": {}}
                    rows.append(row)
                row["run_ids"].insert(0, run.id)
                row["origins"][run.id] = after.get(run.id, (PHASE_ORIGIN.get(run.phase, "plan"), None))
            # Tests of the plan that have not run yet, and measurements running for the first time, are rows too.
            for item in items:
                if item.removed or item.origin in HIDDEN_ORIGINS:
                    continue
                key = f"test-{item.id}"
                if key not in by_key:
                    spec = specs.get(item.id) or {}
                    by_key[key] = {**self._test_base(item, spec, claims, "plan"), "run_ids": [], "origins": {}}
                    rows.append(by_key[key])
            for state in systems.values():
                key = f"system-{state['key']}"
                if key not in by_key and self._job_live(state["item_id"], "migration"):
                    by_key[key] = {**self._system_base(state), "run_ids": [], "origins": {}}
                    rows.append(by_key[key])
            for row in rows:
                if row.get("verify") is not None:
                    continue
                self._finish_row(db, row, reviewed)
            # The order of each page: claims as the file lists them, tests in the plan's order (then their retests, proofs
            # and tries), systems as Migration lists them, libraries as Dependencies lists them.
            position = {i.id: n for n, i in enumerate(items)}
            claim_order = {c.id: n for n, c in enumerate(claims)}
            system_order = {s["key"]: n for n, s in enumerate(systems.values())}
            library_order = {rid: n for n, rid in enumerate(deps["rows"])}
            rank = {"claim": 0, "test": 1, "retest": 2, "proof": 3, "watch": 3.4, "watchbase": 3.6, "try": 4, "system": 5, "library": 6}

            def order(row: dict) -> tuple:
                kind = row["id"].split("-", 1)[0]
                if kind == "claim":
                    return (rank[kind], claim_order.get(row.get("claim_id"), 0), row["id"])
                if kind == "system":
                    return (rank[kind], system_order.get(row.get("system_key"), 0), row["id"])
                if kind == "library":
                    return (rank[kind], library_order.get(row.get("library_row"), 10**6), row["id"])
                return (rank.get(kind, 9), position.get(row.get("item_id"), 0), row["id"])
            rows.sort(key=order)
        return {"rows": rows, "claims": len(claims), "verified": verified, "dependencies": deps}

    def _ledger_verify(self, db, imp: ImportRow | None, rows: list[dict]) -> bool:
        """One row per claim of the newest Verify run (earlier runs kept with it)."""
        if imp is None:
            return False
        runs = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == imp.id).order_by(VerifyRunRow.id.desc())).all()
        if not runs:
            return False
        from app.lab.hub import run_json   # the Verify page's own words
        newest = run_json(runs[0])
        earlier = [run_json(r) for r in runs[1:]]
        for res in newest["results"]:
            if not isinstance(res, dict):
                continue
            claim = res.get("claim") or {}
            history = [{"run_id": None, "verify_run_id": newest["id"], "at": newest["finished_at"],
                        "came_from": ORIGINS["verify"], "label": res.get("result"),
                        "tone": VERIFY_TONES.get(res.get("result", ""), "warn"), "fingerprint": None}]
            for r in earlier:
                same = next((x for x in r["results"] if isinstance(x, dict) and x.get("claim_id") == res.get("claim_id")), None)
                if same is not None:
                    history.append({"run_id": None, "verify_run_id": r["id"], "at": r["finished_at"], "came_from": ORIGINS["verify"],
                                    "label": same.get("result"), "tone": VERIFY_TONES.get(same.get("result", ""), "warn"),
                                    "fingerprint": None})
            rows.append({"id": f"claim-{res.get('claim_id')}", "group": "verification", "kind": "verify",
                         "name": claim.get("text") or "", "ran_on": claim.get("location") or "",
                         "came_from": {"key": "verify", "label": ORIGINS["verify"]},
                         "link": {"page": "inventory/verify", "item": f"claim-{res.get('claim_id')}"},
                         "evidence_link": {"page": "evidence", "item": f"claim-{res.get('claim_id')}"},
                         "state": "done", "status": None,
                         "result": {"label": res.get("result"), "tone": VERIFY_TONES.get(res.get("result", ""), "warn"),
                                    "code": {"True": "true", "False": "false"}.get(res.get("result", ""), "couldnt_check")},
                         "plain": res.get("summary"), "last_run_at": newest["finished_at"], "runs": len(history),
                         "claim_id": res.get("claim_id"), "verify": res, "history": history, "run_ids": [], "origins": {}})
        return True

    def _ledger_dependencies(self, plan_id: int) -> dict:
        """The Dependencies view's libraries: which measured run belongs to which row, and how many were answered."""
        try:
            view = self.dependencies_view(plan_id, with_impact=False)
        except NotFound:
            return {"rows": {}, "answered": 0, "listed": False, "libraries": 0, "measurable": 0, "by_run": {}}
        rows, by_run, answered, measurable = {}, {}, 0, 0
        for g in view.get("groups") or []:
            for r in g.get("rows") or []:
                rows[r["id"]] = {"row": r, "group_label": g.get("label"), "system": g.get("system")}
                if any(c.get("answer") in ("yes", "no") for c in r.get("cells") or []):
                    answered += 1
                if (r.get("measure") or {}).get("label") and r.get("measurement") is None:
                    measurable += 1
                if r.get("measurement"):
                    by_run[r["measurement"]["run_id"]] = r["id"]
        return {"rows": rows, "answered": answered, "listed": view.get("list_file") is not None,
                "libraries": len(rows), "measurable": measurable, "by_run": by_run}

    def _after_change_runs(self, db, plan: PlanRow, items: list[PlanItemRow], specs: dict, runs: list[TestRunRow]) -> dict:
        """The runs the app made by itself right after an Apply or a Roll back: {run id: (origin, change key)}."""
        out: dict[int, tuple[str, str | None]] = {}
        applies = db.scalars(select(ApplyRow).where(ApplyRow.plan_id == plan.id).order_by(ApplyRow.id)).all()
        for apply in applies:
            tried = db.get(ChangeTryRow, apply.try_id)
            tls = str(apply.change_key).startswith("tls")
            if tls:
                ids = [i.id for i in items if (specs.get(i.id) or {}).get("kind") in ("tls_versions", "certificate")
                       and ((specs.get(i.id) or {}).get("target") or {}).get("address") == apply.address]
                phases: tuple[str, ...] = ("first", "retest")
            else:
                ids, phases = ([tried.item_id] if tried is not None else []), ("migration",)
            marks = [("after_apply", apply.runs_before)]
            rollback = db.scalars(select(RollbackRow).where(RollbackRow.apply_id == apply.id)).first()
            if rollback is not None:
                marks.append(("after_rollback", rollback.runs_before))
            for origin, before in marks:
                for item_id in ids:
                    first = next((r for r in runs if r.plan_item_id == item_id and r.phase in phases and r.id > before), None)
                    if first is not None:
                        out[first.id] = (origin, apply.change_key)
        return out

    def _row_key(self, run: TestRunRow, item: PlanItemRow, spec: dict, systems: dict, tries: dict, deps: dict,
                 claims: list) -> tuple[str | None, dict]:
        phase = run.phase
        if phase in ("first", "retest", "proof"):
            origin = PHASE_ORIGIN[phase]
            key = {"first": "test", "retest": "retest", "proof": "proof"}[phase] + f"-{item.id}"
            base = self._test_base(item, spec, claims, origin)
            if phase == "retest":
                base["ran_on"] = self._ledger_component_words(run) or base["ran_on"]
            if phase == "proof":
                version = run.component_version
                base["ran_on"] = (f"{run.component_name} {version} (the changed code)" if run.component_name and version
                                  else base["ran_on"])
            return key, base
        if phase in WATCH_PHASES:
            # Phase 6d: a run that belongs to a developer's change. It is a row of its own, never the test's own result.
            key = ("watch" if phase == "watch" else "watchbase") + f"-{item.id}"
            base = self._test_base(item, spec, claims, "watch")
            base.update(id=key, evidence_link={"page": "evidence", "item": key}, ran_on=self._ledger_component_words(run) or base["ran_on"])
            return key, base
        if phase == "migration":
            state = systems.get(item.id)
            if state is None:
                return None, {}
            return f"system-{state['key']}", self._system_base(state)
        if phase == "dependencies":
            row_id = deps["by_run"].get(run.id)
            if row_id is None:
                # an earlier measurement of a library still in the list: find its row by the same plan item
                return f"library-item-{item.id}", self._library_base(None, spec, deps, item.id)
            return f"library-{row_id}", self._library_base(row_id, spec, deps, item.id)
        if phase in ("try", "try_nginx"):
            tried = tries.get(run.retest_id) if run.retest_id is not None else None
            change_key = tried.change_key if tried is not None else None
            copy: dict = next((c for c in (tried.copies or []) if c.get("phase") == phase), {}) if tried is not None else {}
            title = ((tried.change or {}).get("title") if tried is not None else None) or spec.get("title") or "The change"
            group = G.group_of_change(change_key)
            return f"try-{change_key}-{phase}", {
                "id": f"try-{change_key}-{phase}", "group": group, "kind": spec.get("kind") or "try",
                "name": title, "ran_on": copy.get("label") or ("Real nginx" if phase == "try_nginx" else "A test copy"),
                "came_from": {"key": "try", "label": ORIGINS["try"]}, "change_key": change_key, "item_id": item.id,
                "link": self._change_link(change_key, systems, item),
                "evidence_link": {"page": "evidence", "item": f"try-{change_key}-{phase}"}}
        return None, {}

    @staticmethod
    def _ledger_component_words(run: TestRunRow) -> str | None:
        return f"{run.component_name} {run.component_version}" if run.component_name and run.component_version else None

    def _test_base(self, item: PlanItemRow, spec: dict, claims: list, origin: str) -> dict:
        target = spec.get("target") or {}
        ran_on = target.get("address")
        if ran_on is None and target.get("claim"):
            claim = next((c for c in claims if c.ref == target.get("claim")), None)
            ran_on = claim.location if claim is not None else target.get("component")
        prefix = {"plan": "test", "retest": "retest", "proof": "proof", "watch": "watch"}[origin]
        row_id = f"{prefix}-{item.id}"
        link = ({"page": "checks", "item": row_id} if origin == "plan" else
                {"page": "evidence", "item": f"test-{item.id}"} if origin == "retest" else
                {"page": "change-watch", "item": None} if origin == "watch" else
                {"page": "fixes", "item": None, "section": "proof"})
        # Phase 5c: an advisory check came from one of Otto's proposals that a person accepted. Its row says so, with
        # the way to its advisory.
        advisory = ((spec.get("inputs") or {}).get("advisory") or {}).get("id") if spec.get("kind") == "advisory_cases" else None
        from_otto = ({"label": "From Otto", "advisory": f"Advisory {advisory}", "link": {"page": "advisories", "item": str(advisory)}}
                     if advisory else None)
        return {"id": row_id, "group": "encryption", "kind": spec.get("kind") or "test", "name": spec.get("title") or "",
                "ran_on": ran_on or "", "came_from": {"key": origin, "label": ORIGINS[origin]}, "item_id": item.id,
                "link": link, "evidence_link": {"page": "evidence", "item": row_id}, "from_otto": from_otto}

    @staticmethod
    def _system_base(state: dict) -> dict:
        return {"id": f"system-{state['key']}", "group": "migration", "kind": "pq_status" if state["kind"] == "server" else "signing_status",
                "name": "Post-quantum status", "ran_on": state["name"], "came_from": {"key": "measure", "label": ORIGINS["measure"]},
                "item_id": state["item_id"], "system_key": state["key"],
                "link": {"page": "migration/systems", "item": state["key"]},
                "evidence_link": {"page": "evidence", "item": f"system-{state['key']}"}}

    @staticmethod
    def _library_base(row_id: str | None, spec: dict, deps: dict, item_id: int) -> dict:
        target = spec.get("target") or {}
        label = (deps["rows"].get(row_id, {}).get("row", {}).get("label") if row_id else None) or \
            " ".join(str(x) for x in (target.get("name"), target.get("version")) if x)
        rid = f"library-{row_id}" if row_id else f"library-item-{item_id}"
        return {"id": rid, "group": "dependencies", "kind": "capability", "name": label or "A library",
                "ran_on": "its pinned public copy", "came_from": {"key": "public_copy", "label": ORIGINS["public_copy"]},
                "item_id": item_id, "library_row": row_id,
                "link": {"page": "migration/dependencies", "item": row_id}, "evidence_link": {"page": "evidence", "item": rid}}

    @staticmethod
    def _change_link(change_key: str | None, systems: dict, item: PlanItemRow) -> dict:
        if str(change_key or "").startswith("tls"):
            return {"page": "fixes", "item": "change:" + str(change_key)}
        state = systems.get(item.id)
        return {"page": "migration/systems", "item": state["key"] if state else None}

    def _job_live(self, item_id: int, phase: str) -> bool:
        job = self.jobs.get((item_id, phase))
        return job is not None and job.status != "done"

    def _finish_row(self, db, row: dict, reviewed: set) -> None:
        """Word the newest reviewed run, list the earlier ones, and say whether it is open, in progress or done."""
        phase = {"plan": "first", "retest": "retest", "proof": "proof", "measure": "migration",
                 "public_copy": "dependencies", "try": None,
                 "watch": "watch_base" if row["id"].startswith("watchbase-") else "watch"}.get(row["came_from"]["key"])
        live = None
        if row.get("item_id") is not None:
            if row["came_from"]["key"] == "try":
                for p in ("try", "try_nginx"):
                    job = self.jobs.get((row["item_id"], p))
                    if job is not None and job.status != "done" and row["id"].endswith(p):
                        live = job
            elif phase is not None:
                job = self.jobs.get((row["item_id"], phase))
                live = job if job is not None and job.status != "done" else None
        history = []
        said: dict[int, dict] = {}       # what each reviewed run said (for the blocks of the Crypto tests group)
        newest = None
        for run_id in row["run_ids"]:
            if run_id not in reviewed:
                continue
            run = db.get(TestRunRow, run_id)
            shown = self._result(db, run)
            if shown is None:
                continue
            origin, _ = row["origins"].get(run_id, (row["came_from"]["key"], None))
            entry = {"run_id": run_id, "verify_run_id": None, "at": run.finished_at or run.started_at,
                     "came_from": ORIGINS.get(origin, origin), "label": shown["label"], "tone": shown["tone"],
                     "fingerprint": self._result_cache[run_id][0][0] if run_id in self._result_cache else None}
            history.append(entry)
            said[run_id] = {"label": shown["label"], "tone": shown["tone"], "code": shown["code"], "plain": shown.get("plain"),
                            "at": run.finished_at or run.started_at, "rerun": run.retest_id,
                            "ran_on": self._ledger_component_words(run), "component": run.component_name}
            if newest is None:
                newest = (run, shown, origin)
        row["history"] = history
        row["said"] = said
        row["runs"] = len(history)
        if newest is not None:
            run, shown, origin = newest
            row["result"] = {"label": shown["label"], "tone": shown["tone"], "code": shown["code"]}
            row["plain"] = shown.get("plain")
            row["last_run_at"] = run.finished_at or run.started_at
            row["newest_run_id"] = run.id
            if origin == "watch" and run.retest_id is not None:
                # which developer's change this run belongs to: said where it ran, and linked
                watch = db.get(WatchRunRow, run.retest_id)
                if watch is not None:
                    row["ran_on"] = _watch_ran_on(self._ledger_component_words(run), watch, row["id"].startswith("watchbase-"))
                    row["link"] = {"page": "change-watch", "item": f"change-{watch.head_commit[:12]}"}
            if origin in ("after_apply", "after_rollback"):
                change_key = row["origins"][run.id][1]
                row["came_from"] = {"key": origin, "label": ORIGINS[origin]}
                row["link"] = ({"page": "fixes", "item": "change:" + str(change_key)} if G.group_of_change(change_key) == "encryption"
                               else row["link"])
        else:
            row["result"], row["plain"], row["last_run_at"], row["newest_run_id"] = None, None, None, None
        row["state"] = "in_progress" if live is not None else ("done" if newest is not None else "open")
        row["status"] = (status_view(live.status, live.progress_text, live.progress_percent, self.jobs.max_parallel)
                         if live is not None else None)

    # ---------------------------------------------------------------- the views

    _result_cache: dict

    def _resolve_rows(self, plan_id: int, rows: list[dict]) -> None:
        """Links that name a change open its change box (the fix in Fixes, or the system); a proof opens its fix."""
        changes = [r for r in rows if str((r.get("link") or {}).get("item") or "").startswith("change:")]
        proofs = [r for r in rows if r["came_from"]["key"] == "proof" or r["id"].startswith("proof-")]
        if changes:
            graph = self.relation_graph(plan_id)   # type: ignore[attr-defined]
            for r in changes:
                r["link"] = self.resolve_link(plan_id, r["link"], graph)   # type: ignore[attr-defined]
        if proofs:
            code = next((f["id"] for f in self.fix_states(plan_id) if f["kind"] == "code"), None)
            for r in proofs:
                if r["id"].startswith("proof-"):
                    r["link"] = {"page": "fixes", "item": code, "section": "proof"}

    def checks_view(self, plan_id: int) -> dict:
        """The Checks page (phase 5b): every check, in the four groups, each with its counts and why it is empty."""
        led = self.ledger(plan_id)
        rows = led["rows"]
        self._resolve_rows(plan_id, rows)
        # For Evidence: one row per library of the dependency list, with its answers as Dependencies words them. A library
        # is done once it is answered (release notes or a measurement), in progress while it is measured, open otherwise.
        libraries = []
        for rid, info in led["dependencies"]["rows"].items():
            r = info["row"]
            answered = any(cell.get("answer") in ("yes", "no") for cell in r.get("cells") or [])
            libraries.append({"id": f"library-{rid}", "row_id": rid, "name": r["label"], "via_words": r.get("via_words") or "",
                              "answers_short": r.get("answers_short") or "", "blocks": r.get("blocks") or [],
                              "measured": bool(r.get("measurement")), "lookups": r.get("lookups") or [],
                              "cells": r.get("cells") or [],
                              "state": "in_progress" if r.get("job") else ("done" if answered or r.get("measurement") else "open")})
        groups = []
        for key in G.GROUP_KEYS:
            in_group = [r for r in rows if r["group"] == key]
            states = [r["state"] for r in in_group]
            if key == "verification" and not led["verified"]:
                states = ["open"] * led["claims"]
            if key == "migration":
                with self.db() as db:
                    plan = self._plan(db, plan_id)
                    every = self._systems(self._claims(db.get(ImportRow, plan.import_id)))   # type: ignore[attr-defined]
                measured = {r.get("system_key") for r in in_group if r["id"].startswith("system-")}
                states += ["open" for s in every if s["key"] not in measured]
            if key == "dependencies" and libraries:
                # One rule on every page (Checks, Evidence, the Overview): the Dependencies group counts the list's
                # libraries by the rule above, so the same group never shows two different counts.
                states = [lib["state"] for lib in libraries]
            empty = None
            if not in_group:
                empty = (G.EMPTY_DEPENDENCIES_LISTED if key == "dependencies" and led["dependencies"]["listed"]
                         else G.EMPTY_CHECKS[key])
            note = None
            if key == "dependencies" and led["dependencies"]["listed"]:
                n = led["dependencies"]["answered"]
                note = (f"{n} {'library was' if n == 1 else 'libraries were'} answered from release notes or a measurement; "
                        "every answer is on Dependencies.")
            groups.append({**G.group_frame(key), "counts": G.counts(states), "empty_text": empty, "note": note,
                           "started_on": G.STARTED_ON[key], "rows": [self._public_row(r) for r in in_group],
                           "parts": self._encryption_parts(plan_id, in_group) if key == "encryption" else None})
        self._mark_same_measurements(groups)
        busy = any(r["state"] == "in_progress" for r in rows)
        evidence_counts = {g["key"]: g["counts"] for g in groups}
        return {"plan_id": plan_id, "title": "Checks", "groups": groups, "busy": busy,
                "libraries": libraries, "evidence_counts": evidence_counts,
                "came_from_options": [{"key": k, "label": v} for k, v in ORIGINS.items()],
                "subline": ("Every check in this assessment, wherever it was started. The test plan is under Crypto tests; "
                            "every other check is started where it is today, and its result reads as it does there.")}

    @staticmethod
    def _public_row(row: dict) -> dict:
        keep = ("id", "group", "kind", "name", "ran_on", "came_from", "link", "evidence_link", "state", "status", "result",
                "plain", "last_run_at", "runs", "from_otto")
        out = {k: row.get(k) for k in keep}
        if row.get("mark") is not None or row.get("alias") is not None:      # a row of a retest's or a proof's block
            out["mark"], out["alias"] = row.get("mark"), row.get("alias")
        out["measures"] = _measure_key(row)
        if row.get("pq_claim"):
            out["pq_claim"] = True
        return out

    @staticmethod
    def _mark_same_measurements(groups: list[dict]) -> None:
        """Plan decisions 3 and 4: one measurement made in more than one place. Verify's post-quantum claim on a server,
        that server's Post-quantum readiness test and Migration's Measure status of it use the same probe and the same
        rule; a signing program's Verify claims and its Measure status run the same `info` and round trip. Each keeps its
        own run and its own result (each answer key grades its own); each row names the others ("the same measurement
        as"), with links, and Migration's foot links the ones that sit in another group ("Also relates to this group")."""
        label_of = {g["key"]: g["label"] for g in groups}
        by_key: dict[tuple, list[dict]] = {}
        for g in groups:
            for r in g["rows"]:
                key = r.pop("measures", None)
                if key is not None:
                    by_key.setdefault(tuple(key), []).append(r)
        for g in groups:
            g["also"] = []
        migration = next(g for g in groups if g["key"] == "migration")
        for same in by_key.values():
            for r in same:
                r["same_as"] = [{"id": o["id"], "name": o["name"], "ran_on": o["ran_on"], "group_label": label_of[o["group"]],
                                 "link": {"page": "checks", "item": o["id"]}, "evidence_link": o["evidence_link"]}
                                for o in same if o is not r]
            # Linked from Migration: the Post-quantum readiness test (Crypto tests) and Verify's post-quantum claim
            # (Verification), as the same measurement as Measure status.
            for r in same:
                if r["group"] != "migration" and (r["kind"] == "pq_readiness" or r.get("pq_claim")):
                    migration["also"].append({"id": r["id"], "name": r["name"], "ran_on": r["ran_on"],
                                              "group_label": label_of[r["group"]], "link": {"page": "checks", "item": r["id"]},
                                              "evidence_link": r["evidence_link"]})
        for g in groups:
            for r in g["rows"]:
                r.pop("pq_claim", None)
                r.setdefault("same_as", [])

    # ---------------------------------------------------------------- the 5c fixes: Crypto tests in four parts

    def _blocks(self, plan_id: int, rows: list[dict]) -> tuple[list[dict], list[dict], list[str] | None, list[dict]]:
        """The retests of this plan by the version each ran on (newest first), and its fix proofs (newest first), each
        with the rows of its own runs; the versions the file names; and (phase 6d) the runs of the tests picked for a
        developer's change, newest first. A row here is a copy of the retest's, the proof's or the watch run's row, read
        on the runs of that block only. `rows`: the Crypto tests rows of `ledger`, resolved."""
        from app.present import otto as present_otto      # (only `stamp`: a time in a sentence, marked for a browser)
        with self.db() as db:
            plan = self._plan(db, plan_id)
            retests = db.scalars(select(RetestRow).where(RetestRow.plan_id == plan_id).order_by(RetestRow.id)).all()
            moved = {m.retest_id: m.component_name for m in db.scalars(
                select(RetestProgramRow).where(RetestProgramRow.retest_id.in_([r.id for r in retests]))).all()} if retests else {}
            proofs = db.scalars(select(ProofRow).where(ProofRow.plan_id == plan_id).order_by(ProofRow.id)).all()
            watches = db.scalars(select(WatchRunRow).where(WatchRunRow.plan_id == plan_id).order_by(WatchRunRow.id)).all()
            # every program and version the file names, once each (a file can name several: four libraries, or two
            # versions of one program); the plan's first runs are on all of them, not on the plan's own program only
            named = list(dict.fromkeys(
                f"{p['component']} {p['version']}" if p["version"] else str(p["component"])
                for p in research.programs(self._claims(db.get(ImportRow, plan.import_id)))))     # type: ignore[attr-defined]
            if not named and plan.component_name:
                named = [f"{plan.component_name} {plan.component_version}"]
            names_first = named or None
            program = plan.component_name
        # one block for each (program, version) a retest moved to; a retest belongs to the block its version opened
        by_version: dict[tuple, dict] = {}
        block_of: dict[int, dict] = {}
        for r in retests:
            name = moved.get(r.id) or program or ""
            block = by_version.setdefault((name, r.version), {"key": f"on-{r.id}", "number": r.id, "name": name, "version": r.version,
                                                             "reruns": [], "started": None, "rows": []})
            block["reruns"].append(r.id)
            block["started"] = iso(r.created_at)
            block_of[r.id] = block
        proof_blocks = {p.id: {"key": f"proof-{p.id}", "number": p.id, "name": program or "", "version": p.version, "reruns": [p.id],
                               "started": iso(p.started_at), "rows": []} for p in proofs}
        watch_blocks = {w.id: {"key": f"watch-{w.id}", "number": w.id, "name": program or "", "version": w.version, "reruns": [w.id],
                               "started": iso(w.started_at), "rows": [], "watch": w} for w in watches}
        for row in rows:
            kind = row["id"].split("-", 1)[0]
            if kind not in ("retest", "proof", "watch", "watchbase") or BLOCK_ROW.match(row["id"]):
                continue
            where = block_of if kind == "retest" else proof_blocks if kind == "proof" else watch_blocks
            seen: dict[str, list[int]] = {}
            for run_id in row["run_ids"]:                    # newest first
                told = (row.get("said") or {}).get(run_id)
                found = where.get(told["rerun"]) if told is not None else None
                if found is not None:
                    seen.setdefault(found["key"], []).append(run_id)
            for block in where.values():
                mine = seen.get(block["key"])
                if not mine:
                    continue
                told = row["said"][mine[0]]
                its_own = told["component"] is not None and told["component"] == block["name"]
                copy = {**row, "id": f"{row['id']}-{'on' if kind == 'retest' else 'in'}-{block['number']}",
                        "alias": row["id"] if mine[0] == row.get("newest_run_id") else None,
                        "ran_on": (told["ran_on"] if its_own and kind == "retest" else
                                   f"{told['ran_on']} (the changed code)" if kind == "proof" and told["ran_on"] else
                                   _watch_ran_on(told["ran_on"], block["watch"], kind == "watchbase") if kind in ("watch", "watchbase") else
                                   told["ran_on"] or self._first_ran_on(rows, row)),
                        # (a server, or a program the retest did not move, is run again on what it was)
                        "mark": (AS_IT_IS if kind == "retest" and not its_own else ON_THE_CODE_BEFORE if kind == "watchbase" else None),
                        **({"link": {"page": "change-watch", "item": f"change-{block['watch'].head_commit[:12]}"}}
                           if kind in ("watch", "watchbase") else {}),
                        "result": {"label": told["label"], "tone": told["tone"], "code": told["code"]}, "plain": told["plain"],
                        "last_run_at": told["at"], "runs": len(mine), "newest_run_id": mine[0], "state": "done", "status": None,
                        "history": [h for h in row.get("history") or [] if h["run_id"] in mine], "run_ids": mine}
                block["rows"].append(copy)
        def finish(blocks: list[dict], kind: str) -> list[dict]:
            out = []
            for n, block in enumerate(sorted(blocks, key=lambda b: max(b["reruns"]), reverse=True)):
                times = len(block["reruns"])
                if kind == "retest":
                    title = f"{block['name']} {block['version']}".strip()
                    line = (f"{'One retest' if times == 1 else f'{times} retests'} on this version. "
                            f"The newest started {present_otto.stamp(block['started'])}.")
                elif kind == "watch":
                    watch = block["watch"]
                    title = f"From a developer's change: {watch.branch}, commit {watch.head_commit[:7]}"
                    line = (f"The tests picked for this change ran on its code, {block['name']} {block['version']}. "
                            f"The run started {present_otto.stamp(block['started'])}.")
                else:
                    title = f"{block['name']} {block['version']} (the changed code)".strip()
                    line = f"The proof reran the plan's locked tests on the changed code. It started {present_otto.stamp(block['started'])}."
                out.append({"key": block["key"], "title": title, "line": line, "newest": n == 0, "rows": block["rows"]})
            return out
        return (finish(list(by_version.values()), "retest"), finish(list(proof_blocks.values()), "proof"), names_first,
                finish([b for b in watch_blocks.values() if b["rows"]], "watch"))

    @staticmethod
    def _first_ran_on(rows: list[dict], row: dict) -> str:
        """What a test's first run ran on (a server's address, a program and its version), for a retest that ran it
        again as it is."""
        first = next((r for r in rows if r["id"] == f"test-{row.get('item_id')}"), None)
        return (first or row)["ran_on"]

    def _block_rows(self, plan_id: int, rows: list[dict]) -> list[dict]:
        retests, proofs, _, watches = self._blocks(plan_id, rows)
        return [r for block in retests + proofs + watches for r in block["rows"]]

    def _encryption_parts(self, plan_id: int, rows: list[dict]) -> dict:
        """Checks, the Crypto tests group in four labelled parts (the 5c fixes): the test plan with its first runs,
        the retests by the version each ran on, the fix proofs, and the tries of a server change on a test copy. It
        sorts rows this page already has: a run shows in one part only, and nothing here runs or decides anything."""
        retests, proofs, names_first, watches = self._blocks(plan_id, rows)
        plan_rows = [r for r in rows if r["id"].startswith("test-")]
        tries = [self._public_row(r) for r in rows if r["id"].startswith("try-")]

        def counted(n: int, one: str, many: str | None = None) -> str:
            return f"{n} {one if n == 1 else (many or one + 's')}"

        def public(blocks: list[dict]) -> list[dict]:
            out = []
            for b in blocks:
                shown = [self._public_row(r) for r in b["rows"]]
                for r in shown:
                    r.pop("measures", None)
                    r.setdefault("same_as", [])
                    r.setdefault("mark", None)
                    r.setdefault("alias", None)
                out.append({**b, "rows": shown})
            return out
        for r in tries:
            r.pop("measures", None)
            r.setdefault("same_as", [])
        return {
            "plan": {"key": "plan", "label": "Test plan", "count": len(plan_rows), "count_label": counted(len(plan_rows), "test"),
                     "note": ("First runs, on what the file names." if not names_first else
                              f"First runs, on the version the file names: {names_first[0]}." if len(names_first) == 1 else
                              f"First runs, on the versions the file names: {join_and(names_first)}."),
                     "empty_text": None, "blocks": [], "rows": []},
            "retests": {"key": "retests", "label": "Retests by version", "count": len(retests),
                        "count_label": counted(len(retests), "version"),
                        "note": "One block for each version a retest ran on, the newest first." if retests else None,
                        "empty_text": None if retests else NO_RETEST, "blocks": public(retests), "rows": []},
            "proofs": {"key": "proofs", "label": "Fix proofs", "count": len(proofs), "count_label": counted(len(proofs), "proof"),
                       "note": "One block for each proof of a change, the newest first. A proof is started in Fixes." if proofs else None,
                       "empty_text": None if proofs else "No fix proof yet. A proof starts in Fixes, when the code of a fix is connected.",
                       "blocks": public(proofs), "rows": []},
            # (only when a server change was tried)
            "tries": ({"key": "tries", "label": "Tries on a test copy", "count": len(tries), "count_label": counted(len(tries), "try", "tries"),
                       "note": "A try of a server setting change on a test copy. A try is started where the change is.",
                       "empty_text": None, "blocks": [], "rows": tries} if tries else None),
            # (phase 6d; only when the tests picked for a developer's change were run)
            "changes": ({"key": "changes", "label": "Change watch", "count": len(watches), "count_label": counted(len(watches), "run"),
                         "note": ("One block for each run of the tests picked for a developer's change, the newest first. A run is started on "
                                  "Change watch. These runs never replace a result of the test plan."),
                         "empty_text": None, "blocks": public(watches), "rows": []} if watches else None),
        }

    def check_detail(self, plan_id: int, check_id: str) -> dict:
        """One check: its newest result as its page words it, its earlier runs, and what it relates to."""
        led = self.ledger(plan_id)
        row = next((r for r in led["rows"] if r["id"] == check_id), None)
        if row is None and BLOCK_ROW.match(check_id):
            # a row of one retest's or one proof's block (the 5c fixes): the same test, read on that block's runs only
            self._resolve_rows(plan_id, led["rows"])
            row = next((r for r in self._block_rows(plan_id, [r for r in led["rows"] if r["group"] == "encryption"])
                        if r["id"] == check_id), None)
        if row is None:
            raise NotFound("That check is not in this assessment.")
        self._resolve_rows(plan_id, [row])
        result = None
        if row.get("newest_run_id") is not None:
            with self.db() as db:
                result = self._result(db, db.get(TestRunRow, row["newest_run_id"]))
                if result is not None:
                    # (the line about a fix is laid over a result on Evidence only; here the shape just says there is none)
                    result.setdefault("fix_line", None)
                if result is not None and row.get("item_id") is not None:
                    # phase 5c: where an advisory check came from, and the decisions on Otto's proposal (records only)
                    came_from_otto = self.otto_result_blocks(db, self._plan(db, plan_id)).get(row["item_id"])
                    if came_from_otto is not None:
                        result["otto"] = came_from_otto
        related = self.related(plan_id, self.relation_key(row))   # type: ignore[attr-defined]
        shown = self._public_row(row)
        shown.pop("measures", None)        # (only the list uses it, to say which checks are the same measurement)
        return {"check": shown, "result": result, "verify": row.get("verify"),
                "runs": row.get("history") or [], "related": related}

    @staticmethod
    def relation_key(row: dict) -> str:
        if row["id"].startswith("claim-"):
            return row["id"].replace("claim-", "claim:", 1)
        if row["id"].startswith("system-"):
            return "system:" + row["system_key"]
        if row["id"].startswith("library-") and row.get("library_row"):
            return "library:" + row["library_row"]
        if row.get("item_id") is not None and row["group"] == "encryption" and not row["id"].startswith("try-"):
            return f"test:{row['item_id']}"
        if row["id"].startswith("try-"):
            return "change:" + str(row.get("change_key"))
        return "check:" + row["id"]
