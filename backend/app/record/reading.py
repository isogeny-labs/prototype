"""One assessment's records, read once, as plain data: what the timeline, the decisions and the histories are made from.

It reads; it writes nothing and starts nothing. Every run here carries the result word and tone its own page gives it
(the ledger of `app/ledger/checks.py`, which words each run with `Lab._result`), and each Verify result the word Verify
gave it. Nothing is worded or decided here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from app.db import (
    ActionRow,
    ActionRunRow,
    ApplyApprovalRow,
    ApplyRequestRow,
    ApplyRow,
    ApprovalRow,
    AssessmentDetailRow,
    AssessmentRow,
    AssessmentSignoffRow,
    ChangeRow,
    CodeConnectionRow,
    DependencyListRow,
    DependencyTieRow,
    EvidenceExportRow,
    ImportRow,
    MergeRow,
    MigrationChoiceRow,
    OttoCheckRow,
    OttoDecisionRow,
    OttoLookupRow,
    OttoResearchRow,
    PlanItemRow,
    ProofRow,
    PullRequestRow,
    ResearchRequestRow,
    RetestProgramRow,
    RetestRow,
    ReviewMarkRow,
    RollbackRow,
    SystemSettingRow,
    TestRunRow,
    TestSpecRow,
    VerifyRunRow,
    WatchListMarkRow,
    WatchRunRow,
    iso,
)
from app.engine import research
from app.errors import NotFound
from app.lab.testlab import HIDDEN_ORIGINS, read_spec
from app.ledger.checks import BLOCK_ROW, ORIGINS
from app.present import source as present_source
from app.present import times
from app.projects.store import PURPOSE_LABELS, assessment_title


def run_link(check_id: str) -> dict:
    """Where the row of one run is shown. Results holds a test of the plan (its retests with it) and every other
    check by its own id; a row of one fix proof's block or of one Change watch run's block ("proof-12-in-4",
    "watch-12-in-4") is a row of Checks only, linked as Checks links its own rows."""
    block = BLOCK_ROW.match(check_id)
    if block is not None and block.group(1) in ("proof", "watch", "watchbase"):
        return {"page": "checks", "item": check_id}
    return {"page": "evidence", "item": check_id}


def stamp(value: Any) -> str | None:
    """A recorded time as the ISO text every view carries, or None when the record holds none."""
    when = times.instant(value)
    return iso(when) if when is not None else None


class Reading:
    """Everything one assessment's records say, read once. The fields are plain dicts and lists."""

    def __init__(self, lab: Any, plan_id: int) -> None:
        from app.lab.hub import run_json  # Verify's own words (as the ledger reads them)
        from app.migration.system_changes import change_history

        self.lab, self.plan_id = lab, plan_id
        ledger = lab.ledger(plan_id)  # NotFound for a plan that does not exist
        self.rows: list[dict] = ledger["rows"]
        # each library of the dependency list, by its row, as Dependencies shows it (its answers, its proposals)
        self.libraries: dict[str, dict] = {
            row_id: info["row"] for row_id, info in ((ledger.get("dependencies") or {}).get("rows") or {}).items()
        }
        try:
            self.watch = lab.change_watch_state(plan_id)  # the developer's changes, read from the connected repository
        except NotFound:
            self.watch = {"changes": [], "code": {"state": "no_code", "program": None}}
        # one row of a retest's, a proof's or a watch run's block on Checks, for each run that has one
        encryption = [r for r in self.rows if r["group"] == "encryption"]
        retests, proofs, _, watches = lab._blocks(plan_id, encryption)
        self.check_of_run = {
            run_id: row["id"]
            for block in (*retests, *proofs, *watches)
            for row in block["rows"]
            for run_id in row["run_ids"]
        }
        with lab.db() as db:
            plan = lab._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            self.plan = {"id": plan.id, "import_id": plan.import_id, "component": plan.component_name}
            self.imp = {
                "id": imp.id,
                "filename": imp.filename,
                "format": imp.format,
                "is_demo": bool(imp.is_demo),
                "at": stamp(imp.created_at),
                "claims": [
                    {
                        "id": c.id,
                        "ref": c.ref,
                        "text": c.text,
                        "location": c.location,
                        "location_kind": c.location_kind,
                        "kind": c.kind,
                    }
                    for c in imp.claims
                ],
            }
            self._assessment(db, imp.id)
            self._tests(db, plan_id)
            # each fix where it stands and as Fixes words it (its change box, whether it is a proposal of Otto's)
            fixes = lab._fix_details(db, plan)
            self.fix_states = {state["id"]: state for state, _ in fixes}
            self.fix_words = {state["id"]: shown for state, shown in fixes}
            self.systems = {s["key"]: s for s in lab._migration_states(db, plan)}
            self.system_of_item = {s["item_id"]: s["key"] for s in self.systems.values()}
            self.system_names = {s["key"]: s["name"] for s in lab._systems(lab._claims(imp))}
            self.verify_runs = [
                run_json(r)
                for r in db.scalars(
                    select(VerifyRunRow).where(VerifyRunRow.import_id == imp.id).order_by(VerifyRunRow.id)
                )
            ]
            self._people(db, plan_id, imp.id)
            self.change_history = change_history(lab, db, plan, lab._plan_changes(db, plan))
            self.tries = self._tries()
            self._proofs(db, plan_id)
            self._watch_runs(db, plan_id)
            self._actions(db, plan_id, imp.id)
        self._runs()
        self.busy = any(r.get("state") == "in_progress" for r in self.rows)

    # ---------------------------------------------------------------- the assessment and the plan

    def _assessment(self, db, import_id: int) -> None:
        a = db.scalars(select(AssessmentRow).where(AssessmentRow.import_id == import_id)).first()
        self.assessment: dict | None = None
        self.details: list[dict] = []
        self.signoff: dict | None = None
        if a is None:
            return
        self.assessment = {
            "id": a.id,
            "title": assessment_title(a),
            "at": stamp(a.created_at),
            "closed_at": stamp(a.closed_at),
        }
        self.details = [
            {
                "id": d.id,
                "purpose": PURPOSE_LABELS.get(d.purpose, d.purpose),
                "reference": d.reference,
                "at": stamp(d.created_at),
            }
            for d in db.scalars(
                select(AssessmentDetailRow)
                .where(AssessmentDetailRow.assessment_id == a.id)
                .order_by(AssessmentDetailRow.id)
            )
        ]
        signed = db.scalars(select(AssessmentSignoffRow).where(AssessmentSignoffRow.assessment_id == a.id)).first()
        if signed is not None:
            self.signoff = {
                "id": signed.id,
                "by": signed.signed_off_by,
                "note": signed.note,
                "at": stamp(signed.signed_at),
            }

    def _tests(self, db, plan_id: int) -> None:
        """Every test of the plan (also one taken out since), with its title, its lock and what it runs on."""
        self.items: dict[int, dict] = {}
        for item in db.scalars(
            select(PlanItemRow).where(PlanItemRow.plan_id == plan_id).order_by(PlanItemRow.position)
        ):
            row = db.get(TestSpecRow, item.spec_hash)
            spec, _ = read_spec(row)
            kind = row.kind if row is not None else spec.get("kind")
            self.items[item.id] = {
                "id": item.id,
                "kind": kind,
                "title": research.title_of(kind, spec) if spec else str(kind or "A test"),
                "origin": item.origin,
                "hidden": item.origin in HIDDEN_ORIGINS,
                "removed": bool(item.removed),
                "spec_hash": item.spec_hash,
                "locked_at": stamp(row.locked_at) if row is not None else None,
                "advisory": ((spec.get("inputs") or {}).get("advisory") or {}).get("id")
                if kind == research.ADVISORY_KIND
                else None,
                "target": dict(spec.get("target") or {}),
            }
        self.run_rows = {
            r.id: {
                "phase": r.phase,
                "rerun": r.retest_id,
                "item_id": r.plan_item_id,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in db.scalars(select(TestRunRow).where(TestRunRow.plan_id == plan_id))
        }
        self.otto_checks = {
            c.plan_item_id: {"advisory": c.advisory_id, "design": c.design_sha256, "at": stamp(c.created_at)}
            for c in db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_id == plan_id))
        }

    # ---------------------------------------------------------------- what people did, as the records keep it

    def _people(self, db, plan_id: int, import_id: int) -> None:
        moved = {m.retest_id: m.component_name for m in db.scalars(select(RetestProgramRow))}
        self.retests = [
            {
                "id": r.id,
                "version": r.version,
                "baseline": r.baseline_version,
                "component": moved.get(r.id) or self.plan["component"],
                "at": stamp(r.created_at),
            }
            for r in db.scalars(select(RetestRow).where(RetestRow.plan_id == plan_id).order_by(RetestRow.id))
        ]
        runs = select(TestRunRow.id).where(TestRunRow.plan_id == plan_id)
        self.marks = [
            {"id": m.id, "run_id": m.run_id, "at": stamp(m.created_at)}
            for m in db.scalars(select(ReviewMarkRow).where(ReviewMarkRow.run_id.in_(runs)).order_by(ReviewMarkRow.id))
        ]
        self.digs = [
            {"id": d.id, "run_id": d.run_id, "at": stamp(d.created_at)}
            for d in db.scalars(
                select(ResearchRequestRow).where(ResearchRequestRow.run_id.in_(runs)).order_by(ResearchRequestRow.id)
            )
        ]
        connection = db.scalars(select(CodeConnectionRow).where(CodeConnectionRow.plan_id == plan_id)).first()
        self.connection = (
            {
                "id": connection.id,
                "repository": connection.repository,
                "branch": connection.branch,
                "base_commit": connection.base_commit,
                "at": stamp(connection.created_at),
            }
            if connection is not None
            else None
        )
        self.changes = {
            c.id: {
                "id": c.id,
                "fix_id": "fix-" + c.fix_key,
                "title": c.title,
                "branch": c.branch,
                "head_commit": c.head_commit,
                "base_commit": c.base_commit,
                "written_by": c.written_by,
                "runs": list((c.source or {}).get("runs") or []),
                "at": stamp(c.created_at),
            }
            for c in db.scalars(select(ChangeRow).where(ChangeRow.plan_id == plan_id).order_by(ChangeRow.id))
        }
        self.pull_requests = {}
        for pr in db.scalars(
            select(PullRequestRow).where(PullRequestRow.plan_id == plan_id).order_by(PullRequestRow.id)
        ):
            merge = db.scalars(select(MergeRow).where(MergeRow.pull_request_id == pr.id)).first()
            self.pull_requests[pr.id] = {
                "id": pr.id,
                "number": pr.number,
                "title": pr.title,
                "change_id": pr.change_id,
                "proof_id": pr.proof_id,
                "reviewers": list(pr.reviewers or []),
                "at": stamp(pr.opened_at),
                "approvals": [
                    {"id": a.id, "reviewer": a.reviewer, "name": a.name, "at": stamp(a.approved_at)}
                    for a in db.scalars(
                        select(ApprovalRow).where(ApprovalRow.pull_request_id == pr.id).order_by(ApprovalRow.id)
                    )
                ],
                "merge": {"id": merge.id, "commit": merge.merge_commit, "at": stamp(merge.merged_at)}
                if merge is not None
                else None,
            }
        self.requests = [
            {
                "id": r.id,
                "change_key": r.change_key,
                "reviewers": list(r.reviewers or []),
                "at": stamp(r.created_at),
                "approvals": [
                    {"id": a.id, "reviewer": a.reviewer, "name": a.name, "at": stamp(a.approved_at)}
                    for a in db.scalars(
                        select(ApplyApprovalRow)
                        .where(ApplyApprovalRow.request_id == r.id)
                        .order_by(ApplyApprovalRow.id)
                    )
                ],
            }
            for r in db.scalars(
                select(ApplyRequestRow).where(ApplyRequestRow.plan_id == plan_id).order_by(ApplyRequestRow.id)
            )
        ]
        self.applies = []
        for a in db.scalars(select(ApplyRow).where(ApplyRow.plan_id == plan_id).order_by(ApplyRow.id)):
            back = db.scalars(select(RollbackRow).where(RollbackRow.apply_id == a.id)).first()
            self.applies.append(
                {
                    "id": a.id,
                    "change_key": a.change_key,
                    "change_fp": a.change_fp,
                    "address": a.address,
                    "try_id": a.try_id,
                    "request_id": a.request_id,
                    "accepted": bool(a.accepted),
                    "at": stamp(a.applied_at),
                    "rollback": {"id": back.id, "accepted": bool(back.accepted), "at": stamp(back.rolled_back_at)}
                    if back is not None
                    else None,
                }
            )
        self.choices = [
            {
                "id": c.id,
                "system": c.system_key,
                "option": c.option,
                "reason": c.reason,
                "review_date": c.review_date,
                "at": stamp(c.created_at),
            }
            for c in db.scalars(
                select(MigrationChoiceRow).where(MigrationChoiceRow.plan_id == plan_id).order_by(MigrationChoiceRow.id)
            )
        ]
        self.settings = [
            {"id": s.id, "system": s.system_key, "field": s.field, "value": s.value, "at": stamp(s.created_at)}
            for s in db.scalars(
                select(SystemSettingRow)
                .where(SystemSettingRow.import_id == import_id, SystemSettingRow.source == "user")
                .order_by(SystemSettingRow.id)
            )
        ]
        self.lists = [
            {
                "id": d.id,
                "filename": d.filename,
                "format": d.format,
                "sha256": d.sha256,
                "libraries": len((d.parsed or {}).get("components") or []),
                "at": stamp(d.created_at),
            }
            for d in db.scalars(
                select(DependencyListRow).where(DependencyListRow.import_id == import_id).order_by(DependencyListRow.id)
            )
        ]
        lists = [d["id"] for d in self.lists]
        self.ties = [
            {"id": t.id, "top": t.top_key, "system": t.system_key, "at": stamp(t.created_at)}
            for t in (
                db.scalars(
                    select(DependencyTieRow).where(DependencyTieRow.list_id.in_(lists)).order_by(DependencyTieRow.id)
                )
                if lists
                else []
            )
        ]
        self.otto_decisions = [
            {
                "id": d.id,
                "proposal": d.proposal_id,
                "kind": d.kind,
                "decision": d.decision,
                "reason": d.reason,
                "by": d.by,
                "at": stamp(d.at),
                "made": stamp(d.created_at),  # (its row's own time, finer than the second `at` is kept to: to sort by)
                "title": str((d.proposal or {}).get("title") or "A proposal from Otto"),
                "about": dict((d.proposal or {}).get("about") or {}),
            }
            for d in db.scalars(
                select(OttoDecisionRow).where(OttoDecisionRow.plan_id == plan_id).order_by(OttoDecisionRow.id)
            )
        ]
        self.lookups = [
            {
                "id": look.id,
                "by": look.by,
                "source": look.source,
                "at": stamp(look.at),
                "made": stamp(look.created_at),
                "libraries": len(look.asked or []),
                "advisories": [str(((f or {}).get("advisory") or {}).get("id")) for f in look.found or []],
            }
            for look in db.scalars(
                select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id)
            )
        ]
        self.research: dict[str, dict] = {}
        for r in db.scalars(
            select(OttoResearchRow).where(OttoResearchRow.plan_id == plan_id).order_by(OttoResearchRow.id)
        ):
            run = self.research.setdefault(
                r.run_key,
                {"key": r.run_key, "by": None, "at": None, "made": None, "advisories": [], "ended": None, "pack": None},
            )
            if r.kind == "started":
                run.update(
                    by=r.by, at=stamp(r.at), made=stamp(r.created_at), advisories=[str(a) for a in r.advisories or []]
                )
            else:
                run.update(ended=stamp(r.at), pack=r.pack_version)
                run["at"], run["made"] = run["at"] or stamp(r.at), run["made"] or stamp(r.created_at)
        self.watch_marks = [
            {
                "id": m.id,
                "item": m.item,
                "kind": m.kind,
                "by": m.by,
                "reason": m.reason,
                "at": stamp(m.at),
                "made": stamp(m.created_at),
            }
            for m in db.scalars(
                select(WatchListMarkRow).where(WatchListMarkRow.plan_id == plan_id).order_by(WatchListMarkRow.id)
            )
        ]
        self.exports = [
            {"id": e.id, "fingerprint": e.fingerprint, "at": stamp(e.created_at)}
            for e in db.scalars(
                select(EvidenceExportRow).where(EvidenceExportRow.plan_id == plan_id).order_by(EvidenceExportRow.id)
            )
        ]

    def _tries(self) -> list[dict]:
        """Every try on a test copy, with its outcome as the reviewer's rule gives it (system_changes.change_history)."""
        out = []
        for key, history in self.change_history.items():
            for entry in history["tries"]:
                row = entry["row"]
                out.append(
                    {
                        "id": row.id,
                        "change_key": key,
                        "change_fp": row.change_fp,
                        "item_id": row.item_id,
                        "title": str((row.change or {}).get("title") or "A change"),
                        "address": (row.change or {}).get("address"),
                        "outcome": (entry.get("outcome") or {}).get("code"),
                        "at": stamp(row.created_at),
                    }
                )
        return sorted(out, key=lambda t: t["id"])

    def _proofs(self, db, plan_id: int) -> None:
        """Every proof of a change, with the reviewer's answer as the read gate lets it through."""
        self.proofs = []
        for proof in db.scalars(select(ProofRow).where(ProofRow.plan_id == plan_id).order_by(ProofRow.id)):
            change = db.get(ChangeRow, proof.change_id)
            review = (
                self.lab._proof_review(db, proof, change, self.lab._proof_tests(db, proof))
                if change is not None
                else None
            )
            if review is None:
                live = any(j.key[1] == "proof" for j in self.lab.jobs.live(plan_id))
                state = "running" if live else "unfinished"
            elif not review["believed"]:
                state = "untrusted"
            else:
                state = "passed" if review["offered"] else "failed"
            self.proofs.append(
                {
                    "id": proof.id,
                    "change_id": proof.change_id,
                    "version": proof.version,
                    "baseline": proof.baseline_version,
                    "tests": len(proof.items or []),
                    "state": state,
                    "record_sha256": (review or {}).get("record_sha256"),
                    "at": stamp(proof.started_at),
                }
            )

    def _watch_runs(self, db, plan_id: int) -> None:
        self.watch_runs = []
        for watch in db.scalars(select(WatchRunRow).where(WatchRunRow.plan_id == plan_id).order_by(WatchRunRow.id)):
            review = self.lab._watch_review(db, watch, self.lab._watch_tests(db, watch))
            self.watch_runs.append(
                {
                    "id": watch.id,
                    "branch": watch.branch,
                    "head_commit": watch.head_commit,
                    "base_commit": watch.base_commit,
                    "version": watch.version,
                    "tests": len(watch.items or []),
                    "status": (review or {}).get("status"),
                    "record_sha256": (review or {}).get("record_sha256"),
                    "at": stamp(watch.started_at),
                }
            )

    def _actions(self, db, plan_id: int, import_id: int) -> None:
        """The presses kept for this assessment, and which press started which run."""
        mine = [ActionRow.plan_id == plan_id, ActionRow.import_id == import_id]
        if self.assessment is not None:
            mine.append(ActionRow.assessment_id == self.assessment["id"])
        self.actions = [
            {
                "id": a.id,
                "at": a.at,
                "by": a.by,
                "by_source": a.by_source,
                "kind": a.kind,
                "item": a.item,
                "detail": dict(a.detail or {}),
            }
            for a in db.scalars(select(ActionRow).where(or_(*mine)).order_by(ActionRow.id))
        ]
        ids = [a["id"] for a in self.actions]
        self.press_of_run: dict[int, int] = {}
        self.runs_of_press: dict[int, list[int]] = {}
        if ids:
            for tie in db.scalars(
                select(ActionRunRow).where(ActionRunRow.action_id.in_(ids)).order_by(ActionRunRow.id)
            ):
                self.press_of_run[tie.run_id] = tie.action_id
                self.runs_of_press.setdefault(tie.action_id, []).append(tie.run_id)
        self.action_by_id = {a["id"]: a for a in self.actions}

    def action(self, kinds: tuple[str, ...] | str, key: str, value: Any) -> dict | None:
        """The press that made one record: the action of one of these kinds whose detail names it."""
        kinds = (kinds,) if isinstance(kinds, str) else kinds
        if value is None:
            return None
        return next((a for a in self.actions if a["kind"] in kinds and a["detail"].get(key) == value), None)

    # ---------------------------------------------------------------- the runs, each as its own page words it

    def _runs(self) -> None:
        """Every reviewed run of the assessment: {run id: its facts}. The word and tone are the ones its page shows."""
        self.runs: dict[int, dict] = {}
        for row in self.rows:
            said, prints = row.get("said") or {}, {h["run_id"]: h.get("fingerprint") for h in row.get("history") or []}
            for run_id in row.get("run_ids") or []:
                told, kept = said.get(run_id), self.run_rows.get(run_id)
                if told is None or kept is None:
                    continue  # no review, so no result: nothing is shown for it
                origin, change_key = (row.get("origins") or {}).get(run_id, (row["came_from"]["key"], None))
                ran_on = told.get("ran_on") or row.get("ran_on") or ""
                if kept["phase"] == "proof" and told.get("ran_on"):
                    ran_on = f"{ran_on} (the changed code)"
                check_id = self.check_of_run.get(run_id, row["id"])
                tagged = {
                    **row,
                    "ran_on": ran_on,
                    "came_from": {"key": origin},
                    "result": {"code": told["code"], "label": told["label"], "tone": told["tone"]},
                }
                self.runs[run_id] = {
                    "run_id": run_id,
                    "verify_run_id": None,
                    "item_id": kept["item_id"],
                    "phase": kept["phase"],
                    "rerun": kept["rerun"],
                    "name": row["name"],
                    "ran_on": ran_on,
                    "label": told["label"],
                    "tone": told["tone"],
                    "code": told["code"],
                    "at": stamp(told["at"]) or stamp(kept["finished_at"]),
                    "origin": origin,
                    "origin_label": ORIGINS.get(origin, origin),
                    "change_key": change_key or row.get("change_key"),
                    "group": row["group"],
                    "kind": row["kind"],
                    "fingerprint": prints.get(run_id),
                    "source_tag": present_source.of_check_row(tagged),
                    "check_id": check_id,
                    "system_key": row.get("system_key"),
                    "library_row": row.get("library_row"),
                    "link": run_link(check_id),
                }


__all__ = ["Reading", "stamp"]
