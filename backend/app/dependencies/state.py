"""The Dependencies view (phase 4d), put together: a list added to an import, each library looked up (Level 1) and,
where a pinned public copy exists, measured (Level 2), and the blockers that follow for the systems of the file.

One path, the same as every test: a measurement is a locked test (kind "capability") kept as a hidden plan item,
run through the job runner, written to a run record and reviewed by the separate reviewer. An answer is only ever
read from that review, through the same read gate as every result. Lookups, ties, blockers and Fixes entries are
worked out again on every read and never stored. What IS stored, in tables that only accept new rows: the lists
(dependency_lists) and the person's own ties (dependency_ties).
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app import real_libraries
from app.canonical import canonical_bytes
from app.db import DependencyListRow, DependencyTieRow, ImportRow, PlanItemRow, PlanRow, ReviewRow, iso
from app.dependencies.target import label_of
from app.dependencies.tree import Tree, build_tree, from_store, label, to_store
from app.engine import research
from app.errors import BadRequest, Conflict, NotFound
from app.importer.sbom import read_dependency_list
from app.knowledge.base import ROLE_OF, knowledge_base
from app.knowledge.model import CAPABILITIES
from app.knowledge.versions import at_least, read_version
from app.lab.testlab import DEPENDENCY_ORIGIN
from app.present import dependencies as present_deps
from app.present import results as present

ANSWERS = ("yes", "no")
# Which question decides which track, and which kind of library a track looks at (docs/SPEC.md section 7e).
TRACKS = {"server": {"kex": ("x25519mlkem768", "tls"), "auth": ("ml_dsa_65", "tls")},
          "software": {"signatures": ("ml_dsa_65", "signatures")}}
NEEDS_ISOLATED = "needs isolated mode"


def fix_id_for(system_key: str, row_key: str) -> str:
    return "dependency-" + hashlib.sha256(f"{system_key}\0{row_key}".encode()).hexdigest()[:12]


class DependenciesMixin:
    """Mixed into Lab. Needs: db, jobs, engine, mode, runner and, from the other mixins: _plan, _claims, _lock_spec,
    _submit, _latest_run, _result, _result_cache, _plan_lock, ensure_plan, _systems (MigrationMixin)."""

    _dependency_cache: dict
    # Provided by Lab and its other mixins. Declared here for the type check only: nothing is assigned.
    db: Callable[..., Any]
    jobs: Any
    engine: Any
    mode: Any
    runner: Any
    _plan_lock: Any
    _result_cache: dict
    _plan: Callable[..., PlanRow]
    _claims: Callable[..., list[dict]]
    _systems: Callable[..., list[dict]]
    _lock_spec: Callable[..., str]
    _submit: Callable[..., Any]
    _latest_run: Callable[..., Any]
    _result: Callable[..., dict | None]
    ensure_plan: Callable[..., dict]

    # ---------------------------------------------------------------- the list, read and kept

    def _latest_list(self, db, import_id: int) -> DependencyListRow | None:
        return db.scalars(select(DependencyListRow).where(DependencyListRow.import_id == import_id)
                          .order_by(DependencyListRow.id.desc()).limit(1)).first()

    def _tree_of(self, row: DependencyListRow, programs: list[tuple[str, str]]) -> Tree:
        cache = self.__dict__.setdefault("_dependency_cache", {})
        key = (row.id, tuple(programs))
        if key not in cache:
            cache[key] = build_tree(from_store(row.parsed), programs)
        return cache[key]

    @staticmethod
    def _programs(claims: list[dict]) -> list[dict]:
        return [p for p in research.programs(claims) if p.get("role") != "key_exchange"]

    # ---------------------------------------------------------------- measurements: hidden plan items

    def _capability_request(self, name: str, version: str) -> dict | None:
        copy = real_libraries.capability_copy(name, version)
        if copy is None:
            return None
        cap = real_libraries.capability_copy(*real_libraries.CAPABLE_CONTROL)
        inc = real_libraries.capability_copy(*real_libraries.INCAPABLE_CONTROL)
        if cap is None or inc is None:      # (both are fixed in real_libraries.py)
            return None
        return {"name": name, "version": version, "label": copy["label"], "target_kind": "public_copy",
                "tls": copy.get("tls_client") is not None, "capable": cap["label"], "incapable": inc["label"]}

    def _capability_spec(self, name: str, version: str) -> tuple[dict, str] | None:
        request = self._capability_request(name, version)
        if request is None:
            return None
        spec = self.engine.design_capability(request)
        return spec, hashlib.sha256(canonical_bytes(spec)).hexdigest()

    def _ensure_capability_items(self, db, plan: PlanRow, copies: list[tuple[str, str]]) -> dict[tuple[str, str], PlanItemRow]:
        have = {r.spec_hash: r for r in db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan.id,
                                                                           PlanItemRow.origin == DEPENDENCY_ORIGIN)).all()}
        out = {}
        for n, (name, version) in enumerate(copies):
            made = self._capability_spec(name, version)
            if made is None:
                continue
            spec, key = made
            if key not in have:
                have[key] = PlanItemRow(plan_id=plan.id, spec_hash=self._lock_spec(db, spec), position=20_000 + n,
                                        origin=DEPENDENCY_ORIGIN, removed=False)
                db.add(have[key])
            out[(name, version)] = have[key]
        db.commit()
        return out

    def _measurement_of(self, db, plan: PlanRow, name: str, version: str) -> dict:
        """The newest reviewed capability check of this exact copy, through the read gate; {} when there is none."""
        made = self._capability_spec(name, version)
        if made is None:
            return {}
        _, key = made
        item = db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan.id, PlanItemRow.origin == DEPENDENCY_ORIGIN,
                                                    PlanItemRow.spec_hash == key)).first()
        if item is None:
            return {}
        out: dict = {"item_id": item.id}
        job = self.jobs.get((item.id, DEPENDENCY_ORIGIN))
        if job is not None and job.status != "done":
            out["job"] = present.status_view(job.status, job.progress_text, job.progress_percent, self.jobs.max_parallel)
        run = self._latest_run(db, item.id, DEPENDENCY_ORIGIN, None)
        result = self._result(db, run) if run is not None else None
        if result is not None:
            review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
            stands = self._result_cache[run.id][2] and result["code"] == review.code   # the read gate
            out.update(run_id=run.id, code=result["code"], result=result, finished_at=run.finished_at,
                       reason=review.reason if stands else None, detail=dict(review.detail or {}) if stands else {},
                       control=review.control_outcome if stands else None,
                       target_kind=(read_target_kind(db, run.spec_hash)))
        return out

    # ---------------------------------------------------------------- everything about the list, worked out now

    def _dependency_state(self, db, plan: PlanRow) -> dict | None:
        imp = db.get(ImportRow, plan.import_id)
        row = self._latest_list(db, imp.id)
        if row is None:
            return None
        claims = self._claims(imp)
        programs = self._programs(claims)
        tree = self._tree_of(row, [(p["component"], p["version"]) for p in programs])
        systems = {s["key"]: s for s in self._systems(claims)}
        by_program = {(p["component"].casefold(), p["version"]): "software:" + p["ref"] for p in programs}
        ties = {}
        for tie in db.scalars(select(DependencyTieRow).where(DependencyTieRow.list_id == row.id).order_by(DependencyTieRow.id)).all():
            ties[tie.top_key] = tie            # the newest row of a top entry is the one in force
        kb = knowledge_base()
        isolated = self.mode.name == "isolated"
        tops: list[dict[str, Any]] = []
        for top in tree.tops:
            mine = ties.get(top.key)
            auto = by_program.get((top.name.casefold(), top.version)) if top.program else None
            if mine is not None:
                system = mine.system_key or None
                tie = {"system": system if system in systems else None, "source": "user", "at": iso(mine.created_at)}
            elif auto is not None and auto in systems:
                tie = {"system": auto, "source": "name_version", "at": None}
            else:
                tie = {"system": None, "source": None, "at": None}
            tops.append({"key": top.key, "label": label(top), "tie": tie, "rows": []})
        top_of = {t["key"]: t for t in tops}
        rows: list[dict[str, Any]] = []
        for n, r in enumerate(tree.rows):
            entry = kb.find(r.purl, r.name)
            looked = kb.look_up(r.purl, r.name, r.version)
            copy = real_libraries.capability_copy(entry.library if entry else None, r.version) if entry else None
            measured = (self._measurement_of(db, plan, entry.library, r.version)
                        if (copy and isolated and entry is not None and r.version is not None) else {})
            spec_questions = (["ml_kem_768"] + (["x25519mlkem768"] if copy and copy.get("tls_client") else []) + ["ml_dsa_65"]) if copy else []
            answers = {q: self._answer(q, looked[q], copy is not None, q in spec_questions, isolated, measured, entry, kb, r.version)
                       for q in CAPABILITIES}
            item: dict[str, Any] = {"key": r.key, "id": f"row-{n + 1}", "name": r.name, "version": r.version, "purl": r.purl, "label": label(r),
                    "owner": r.owner, "via": r.via, "paths": r.paths, "library": entry.library if entry else None,
                    "library_label": entry.label if entry else None, "roles": list(entry.roles) if entry else [],
                    "measurable": copy is not None, "copy_label": copy["label"] if copy else None, "answers": answers,
                    "measurement": {k: measured.get(k) for k in ("item_id", "run_id", "code", "control", "job", "finished_at", "target_kind", "result")}
                    if measured else ({} if copy else None),
                    "same_copy_as_control": (measured.get("detail") or {}).get("same_copy_as_control") if measured else None}
            rows.append(item)
            if r.owner in top_of:
                top_of[r.owner]["rows"].append(item["id"])
        # blockers and things to check, per system of the file that a top entry is tied to
        per_system: dict[str, dict] = {}
        for shown_top in tops:
            system_key = shown_top["tie"]["system"]
            if not system_key:
                continue
            kind = systems[system_key]["kind"]
            slot = per_system.setdefault(system_key, {"key": system_key, "name": systems[system_key]["name"], "kind": kind,
                                                      "blockers": {t: [] for t in TRACKS[kind]}, "without_answer": 0, "tops": []})
            slot["tops"].append(shown_top["label"])
            for row_id in shown_top["rows"]:
                item = next(x for x in rows if x["id"] == row_id)
                applicable = [a for a in item["answers"].values() if a["answer"] != "doesnt_apply"]
                if not any(a["answer"] in ANSWERS for a in applicable):
                    slot["without_answer"] += 1
                for track, (question, role) in TRACKS[kind].items():
                    a = item["answers"][question]
                    if role in item["roles"] and a["answer"] == "no":
                        slot["blockers"][track].append({"row": item["id"], "row_key": item["key"], "library": item["name"],
                                                        "library_label": item["library_label"], "version": item["version"],
                                                        "label": item["label"], "via": item["via"], "question": question,
                                                        "answer_label": a["label"], "first_version": a["first_version"],
                                                        "fix_id": fix_id_for(system_key, item["key"])})
        return {"list": {"id": row.id, "filename": row.filename, "format": row.format, "sha256": row.sha256, "size": row.size,
                         "at": iso(row.created_at)},
                "described": present_deps.described_label(row.parsed), "tops": tops, "rows": rows, "systems": per_system,
                "system_choices": [{"key": s["key"], "name": s["name"], "kind": s["kind"]} for s in systems.values()],
                "not_libraries": tree.not_libraries, "isolated": isolated}

    @staticmethod
    def _answer(question: str, looked, has_copy: bool, asked: bool, isolated: bool, measured: dict, entry, kb,
                version: str | None = None) -> dict:
        lookup = looked.as_dict()
        out = {"question": question, "lookup": lookup, "answer": lookup["answer"], "label": lookup["label"],
               "first_version": lookup["first_version"], "state": "not_offered", "state_reason": None, "measured": None,
               "agreement": None, "library_says": None}
        if lookup["answer"] == "doesnt_apply" or not has_copy or not asked:
            out["state_reason"] = ("this question is not asked of this kind of library" if lookup["answer"] == "doesnt_apply"
                                   else "this version is not on the approved pinned list" if not has_copy
                                   else "this question is not measured on this copy in this version")
        elif not isolated:
            out["state"], out["state_reason"] = "couldnt_check", NEEDS_ISOLATED
        elif not measured.get("code"):
            out["state"] = "not_measured"
        elif measured["code"] == "couldnt_trust":
            out["state"], out["state_reason"] = "couldnt_trust", measured.get("reason") or "a control copy did not answer as it must"
        elif measured["code"] != "measured":
            out["state"], out["state_reason"] = "couldnt_check", measured.get("reason") or "the check could not run"
        else:
            detail = measured.get("detail") or {}
            said = (detail.get("answers") or {}).get(question)
            if said in ANSWERS:
                out.update(state="measured", measured=said, answer=said, label=label_of(measured.get("target_kind")) or "public_copy",
                           library_says=(detail.get("library_says") or {}).get(question))
                if said == "no":
                    known = kb.first_version(entry, question) if entry is not None else None
                    here = read_version(version)
                    if known and (here is None or at_least(here, known)):
                        known = None    # already at or past the version the release notes name: no newer version is known to help
                    out["first_version"] = known or "none_known"
                else:
                    out["first_version"] = None
                if lookup["answer"] in ANSWERS:
                    out["agreement"] = "agrees" if lookup["answer"] == said else "differs"
            else:
                out["state"], out["state_reason"] = "couldnt_check", (detail.get("why") or {}).get(question) or "no clear answer"
        if out["answer"] == "no" and out["first_version"] is None:
            out["first_version"] = "none_known"
        return out

    def _dependency_blockers(self, db, plan: PlanRow) -> dict[str, dict]:
        """system key -> {track: [blocker, ...]} for the Migration step. Empty when the import has no list."""
        state = self._dependency_state(db, plan)
        return {k: v["blockers"] for k, v in state["systems"].items()} if state else {}

    # ---------------------------------------------------------------- the screen

    def dependencies_view(self, plan_id: int, with_impact: bool = True) -> dict:
        """`with_impact` (phase 4e): each row's "Where it is used". The reads that only count leave it out."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            busy = self.jobs.busy((DEPENDENCY_ORIGIN, plan_id))
            state = self._dependency_state(db, plan)
            otto = self._dependency_otto(db, plan, state)
            impact = self._dependency_impact(db, plan, state) if with_impact else {}     # type: ignore[attr-defined]
            return present_deps.view(plan_id=plan.id, import_id=imp.id, is_demo=bool(imp.is_demo), state=state, busy=busy,
                                     isolated=self.mode.name == "isolated", otto=otto, impact=impact)

    def _dependency_otto(self, db, plan: PlanRow, state: dict | None) -> dict:
        """Phase 5c: for each library row (by its key), the published advisories that name it with what this assessment
        measured, and Otto's proposals for it as the screen shows them. Worked out from the installed packs, the list
        and the results; nothing is stored by looking, and no existing answer changes."""
        from app.present import otto as present_otto
        if state is None:
            return {}
        upto = self._closed_at(plan.id)                                       # type: ignore[attr-defined]
        named = self._named_by(db, plan, state, upto)                         # type: ignore[attr-defined]
        if not named:
            return {}
        proposals = self._proposals(db, plan, ("dependency",), dependency_state=state)   # type: ignore[attr-defined]
        out: dict[str, dict] = {}
        for row_key, entries in named.items():
            lines = []
            for n in entries:
                link = None
                if n["fix"].get("kind") == "update":
                    item_id = n["measured"].get("item_id") if n["measured"]["state"] == "affected" else None
                    fix_id = self._text_fix_id(db, plan, "advisory_cases", item_id) if item_id is not None else None   # type: ignore[attr-defined]
                    link = {"page": "fixes", "item": fix_id} if fix_id else {"page": "advisories", "item": n["advisory"]}
                lines.append(present_otto.named_line(n, link))
            # (only what Otto proposes now for this very library and version: a decision on a proposal that is no longer
            # made stays on the record, in the evidence, and is never laid on whatever row stands in that place now)
            mine = [present_otto.proposal_view(p, self.otto_ledger_about(plan.id, p.get("objective_id")))      # type: ignore[attr-defined]
                    for p in proposals if p["current"] and row_key in (p["facts"].get("row_keys") or [])]
            out[row_key] = {"advisories": lines, "proposals": mine, "status": present_otto.dependency_status(mine)}
        return out

    def dependencies_view_for_import(self, import_id: int) -> dict:
        return self.dependencies_view(self.ensure_plan(import_id)["id"])

    def wait_until_dependencies_measured(self, plan_id: int, timeout: float = 600.0) -> None:
        if not self.jobs.wait_idle(timeout, group=(DEPENDENCY_ORIGIN, plan_id)):
            raise TimeoutError("The measurement did not finish in time.")

    # ---------------------------------------------------------------- the person's actions

    def add_dependency_list(self, plan_id: int, filename: str, data: bytes) -> dict:
        """Read a CycloneDX or SPDX file and keep it for this import. Refused with one plain sentence if it can't be read;
        a refused file leaves the earlier list in place. Nothing in the file is run."""
        parsed = read_dependency_list(data)       # ImportFileError: shown as it is
        name = (filename or "dependencies.json").replace("\\", "/").rsplit("/", 1)[-1][:200] or "dependencies.json"
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            db.add(DependencyListRow(import_id=plan.import_id, filename=name, format=parsed.format, sha256=hashlib.sha256(data).hexdigest(),
                                     size=len(data), parsed=to_store(parsed)))
            db.commit()
        return self.dependencies_view(plan_id)

    def tie_dependency(self, plan_id: int, top_key: str, system_key: str | None) -> dict:
        """The person's own answer to "Part of": the system of the file this top entry belongs to, or none of these."""
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            state = self._dependency_state(db, plan)
            if state is None:
                raise Conflict("Add a dependency list first.")
            if top_key not in {t["key"] for t in state["tops"]}:
                raise NotFound("That entry is not in this list.")
            if system_key and system_key not in {s["key"] for s in state["system_choices"]}:
                raise BadRequest("That system is not in the imported file.", field="system")
            db.add(DependencyTieRow(list_id=state["list"]["id"], top_key=top_key, system_key=system_key or ""))
            db.commit()
        return self.dependencies_view(plan_id)

    def measure_dependencies(self, plan_id: int, row_id: str | None = None) -> dict:
        """Measure one library (row_id) or every library that can be (None) on its pinned public copy. Isolated mode only."""
        if self.mode.name != "isolated":
            raise Conflict("Measuring a library needs isolated mode (Docker). Lookups work as they are.")
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                state = self._dependency_state(db, plan)
                if state is None:
                    raise Conflict("Add a dependency list first.")
                rows = [r for r in state["rows"] if r["measurable"] and (row_id is None or r["id"] == row_id)]
                if row_id is not None and not rows:
                    raise BadRequest("That library can't be measured: it is not on the approved pinned list.", field="row")
                if not rows:
                    raise Conflict("No library in this list is on the approved pinned list, so there is nothing to measure.")
                copies = list(dict.fromkeys((r["library"], r["version"]) for r in rows))
                items = self._ensure_capability_items(db, plan, copies)
            for copy in copies:
                item = items.get(copy)
                job = self.jobs.get((item.id, DEPENDENCY_ORIGIN)) if item else None
                if item is not None and (job is None or job.status == "done"):
                    self._submit(plan, item, DEPENDENCY_ORIGIN, None)
        return self.dependencies_view(plan_id)

    # ---------------------------------------------------------------- Fixes and the evidence file

    def _fixes_for_dependencies(self, db, plan: PlanRow, items: list, shown: list[dict]) -> list[dict]:
        """One text-only entry for each library that blocks a track of a system: "Update <library> to <version> or later"."""
        state = self._dependency_state(db, plan)
        if state is None:
            return []
        fixes, seen = [], set()
        for system in state["systems"].values():
            for blockers in system["blockers"].values():
                for b in blockers:
                    if b["fix_id"] in seen:
                        continue
                    seen.add(b["fix_id"])
                    fixes.append({"id": b["fix_id"], "test_kind": "capability", "kind": "text", "status": "text_only",
                                  "source_kind": "dependency", "answers": [], "component": None, "template_id": None,
                                  "rerun_blocked": None, "connection": None, "change": None, "proofs": 0, "proof": None,
                                  "pull_request": None, "merge": None, "actions": {},
                                  "dependency": {"system": system["key"], "row_key": b["row_key"], "row": b["row"]}})
        return fixes

    def _dependency_fix_view(self, db, plan: PlanRow, fix: dict, is_demo: bool) -> dict:
        state = self._dependency_state(db, plan)
        system = state["systems"].get(fix["dependency"]["system"]) if state else None
        if state is None or system is None:
            raise NotFound("That fix is not in this plan.")
        blockers = [b for bs in system["blockers"].values() for b in bs if b["row_key"] == fix["dependency"]["row_key"]]
        if not blockers:
            raise NotFound("That fix is not in this plan.")
        row = next(r for r in state["rows"] if r["key"] == fix["dependency"]["row_key"])
        return present_deps.fix_view(fix, system, row, blockers, is_demo)

    def _dependencies_export(self, db, plan: PlanRow) -> dict | None:
        state = self._dependency_state(db, plan)
        return present_deps.export(state) if state else None


def read_target_kind(db, spec_hash: str) -> str | None:
    from app.db import TestSpecRow
    from app.lab.testlab import read_spec
    spec, _ = read_spec(db.get(TestSpecRow, spec_hash))
    return (spec.get("target") or {}).get("target_kind") if spec else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = ["DependenciesMixin", "ROLE_OF"]
