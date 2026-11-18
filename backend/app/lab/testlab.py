"""The Tests and Evidence Lab actions, used by the web API, pytest and the accuracy command alike.

One path for everything: propose -> lock -> run through the job runner -> run record -> separate review.
A result is only ever shown from a Review row, and only while the stored test and run record still match
the fingerprints the review was made for."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.run import components
from app.present import results as present
from app.present import fixes as present_fixes
from app import real_libraries
from app.engine import research
from app.canonical import canonical_bytes, sha256_hex
from app.config import DEMO_HOSTNAME
from app.db import (
    AddressRow, ImportRow, PlanItemRow, PlanRow, ProofRow, ResearchRequestRow, RetestProgramRow, RetestRow, ReviewMarkRow,
    ReviewRow, RunCodeRow, TestRunRow, TestSpecRow, VerifyRunRow, iso,
)
from app.errors import BadRequest, Conflict, NotFound
from app.run.execute import RunContext, execute, problem
from app.jobs import Job
from app.checks.verify import AddressCheck, DemoContext

RUNNER_ID = "isogeny.runner/1"
MIGRATION_ORIGIN = "migration"   # a plan item that is a Migration measurement (phase 4a), and the phase of its runs
DEPENDENCY_ORIGIN = "dependencies"   # a plan item that is a library's capability check (phase 4d), and the phase of its runs
HIDDEN_ORIGINS = (MIGRATION_ORIGIN, DEPENDENCY_ORIGIN)   # measurements the Tests step never shows
RUN_SCHEMA = "isogeny.run/1"
SOFTWARE_KINDS = research.SOFTWARE_TEST_KINDS + ("signing_status",)
NOT_DEMO_PROGRAM = "Its tests can't run: only our own demo components can run in this version."
# Claims that no test in this version covers: what the "Not tested, and why" box says about them.
UNCOVERED = {"cipher_suites": "its cipher-suite claim is checked in Verify only. No test in this version covers cipher suites.",
             "key_exchange": "its key-exchange claim is checked in Verify only. No test in this version covers key exchange.",
             "post_quantum": ("its post-quantum claim is checked in Verify and measured in the Migration step. To test it here as well, "
                              "add the Post-quantum readiness test.")}
# Why nothing new can start for a plan while its jobs run. A proof (phase 3a, Fixes) has its own sentence.
BUSY = {"tests": "Tests are still running. Wait until they have finished.",
        "proof": "A proof is running in Fixes. Wait until it has finished."}
# What is kept about the code a run ran on (the columns of run_code, in the order they are shown and exported).
CODE_KEYS = ("source", "component_name", "component_version", "file_sha256", "repository", "branch", "commit", "change_id",
             "pull_request_number")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_spec(row: TestSpecRow | None) -> tuple[dict, bool]:
    """(the locked test, does it still match its fingerprint?). Recomputed every time a test is run or shown."""
    if row is None:
        return {}, False
    try:
        raw = row.canonical.encode("utf-8")
        spec = json.loads(row.canonical)
        ok = isinstance(spec, dict) and hashlib.sha256(raw).hexdigest() == row.hash and canonical_bytes(spec) == raw
    except (ValueError, TypeError, AttributeError):
        return {}, False
    return (spec if isinstance(spec, dict) else {}), bool(ok)


def run_record(row: TestRunRow) -> dict:
    """The run record exactly as it was fingerprinted (the row id is not part of it)."""
    return {"schema": RUN_SCHEMA, "spec_hash": row.spec_hash, "phase": row.phase,
            "component": {"name": row.component_name, "version": row.component_version},
            "baseline_version": row.baseline_version, "mode": row.mode, "started_at": row.started_at,
            "finished_at": row.finished_at, "duration_ms": row.duration_ms, "raw": row.raw, "logs": row.logs, "runner": row.runner}


def review_dict(row: ReviewRow) -> dict:
    return {"id": row.id, "schema": "isogeny.review/1", "reviewer": row.reviewer, "proposed_by": row.proposed_by,
            "spec_hash": row.spec_hash, "spec_hash_ok": row.spec_hash_ok, "run_sha256": row.run_sha256,
            "control": {"outcome": row.control_outcome, "reason": row.control_reason}, "reference_ok": row.reference_ok,
            "code": row.code, "reason_code": row.reason_code, "reason": row.reason, "detail": row.detail,
            "created_at": iso(row.created_at)}


class TestLabMixin:
    """Mixed into Lab. Needs: db, settings, mode, component_runner, jobs, engine, reviewer, demo, resolver, and
    from ChangesMixin: _code_for_run (which code a run runs on) and _proof_run_finished; from FixesMixin:
    _fix_lines (the one line about a fix) and _column_code (the code one side of before and after ran on)."""
    __test__ = False  # not a pytest class
    _dependency_blockers: Callable[..., dict[str, dict]]   # from DependenciesMixin (phase 4d); declared for the type check only
    _otto_cannot_run: Callable[..., str | None]            # from OttoMixin (phase 5c), as the two below; declared for the type check only
    _otto_after_review: Callable[..., None]
    otto_result_fix: Callable[..., dict | None]

    def _init_testlab(self) -> None:
        self._plan_lock = threading.Lock()
        self._result_cache: dict[int, tuple] = {}

    # ---------------------------------------------------------------- plans

    @staticmethod
    def _claims(imp: ImportRow) -> list[dict]:
        return [{"ref": c.ref, "location": c.location, "location_kind": c.location_kind, "kind": c.kind,
                 "claimed_value": c.claimed_value, "detail": dict(c.detail or {})} for c in imp.claims]

    def _lock_spec(self, db, spec: dict, proposed_by: str | None = None) -> str:
        """Write the test down and lock it. The same test proposed again is the same row (same fingerprint).
        `proposed_by` names who proposed it when that is not the rule engine (phase 5c: a test from a test pack)."""
        text = canonical_bytes(spec).decode("utf-8")
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if db.get(TestSpecRow, key) is None:
            db.add(TestSpecRow(hash=key, kind=spec["kind"], canonical=text, proposed_by=proposed_by or self.engine.engine_id))
            db.flush()
        return key

    def ensure_plan(self, import_id: int) -> dict:
        with self._plan_lock, self.db() as db:
            imp = db.get(ImportRow, import_id)
            if imp is None:
                raise NotFound("That import does not exist.")
            plan = db.scalars(select(PlanRow).where(PlanRow.import_id == import_id)).first()
            if plan is None:
                claims = self._claims(imp)
                proposal = self._proposal_for(claims)
                own = self._own_program(claims)
                plan = PlanRow(import_id=import_id, component_name=own["component"] if own else None,
                               component_version=own["version"] if own else None)
                db.add(plan)
                db.flush()
                for position, spec in enumerate(proposal["tests"]):
                    db.add(PlanItemRow(plan_id=plan.id, spec_hash=self._lock_spec(db, spec), position=position,
                                       origin="suggested", removed=False))
                db.commit()
            plan_id = plan.id
        return self.plan_view(plan_id)

    def _proposal_for(self, claims: list[dict]) -> dict:
        """The engine's suggested tests, without those for a signing program that can't run (only our own demo
        components can): such a program gets no test cards and no result rows, only its line under "Not tested,
        and why". So the count of tests leaves it out."""
        proposal = self.engine.propose_tests(claims)
        cant_run = {p["ref"] for p in research.programs(claims) if not components.kind_of(p["component"], p["version"])}
        tests = [t for t in proposal["tests"] if not ((t.get("target") or {}).get("kind") == "software" and t["target"].get("claim") in cant_run)]
        return {**proposal, "tests": tests}

    def get_plan_for_import(self, import_id: int) -> dict:
        with self.db() as db:
            plan = db.scalars(select(PlanRow).where(PlanRow.import_id == import_id)).first()
            if plan is None:
                raise NotFound("No test plan has been made for this import yet.")
            plan_id = plan.id
        return self.plan_view(plan_id)

    @staticmethod
    def _plan(db, plan_id: int) -> PlanRow:
        plan = db.get(PlanRow, plan_id)
        if plan is None:
            raise NotFound("That test plan does not exist.")
        return plan

    @staticmethod
    def _items(db, plan_id: int, include_removed: bool = False) -> list[PlanItemRow]:
        """The plan's tests, in order. The Migration step's own measurements (origin "migration", phase 4a) are kept
        as plan items too, so they are locked, run and reviewed the same way, but they are never among the tests:
        not in the plan, the results, a retest or a proof."""
        rows = db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan_id, PlanItemRow.origin.not_in(HIDDEN_ORIGINS))
                          .order_by(PlanItemRow.position, PlanItemRow.id)).all()
        return [r for r in rows if include_removed or not r.removed]

    def _specs(self, db, items: list[PlanItemRow]) -> dict[int, tuple[dict, bool, TestSpecRow]]:
        out = {}
        for item in items:
            row = db.get(TestSpecRow, item.spec_hash)
            spec, ok = read_spec(row)
            out[item.id] = (spec, ok, row)
        return out

    @staticmethod
    def _own_program(claims: list[dict]) -> dict | None:
        """The plan's own signing program: the one Retest, Connect demo code and the proof work on. The first
        program in the file that is one of our registered demo components, else the first program."""
        found = research.programs(claims)
        return next((p for p in found if components.kind_of(p["component"], p["version"])), found[0] if found else None)

    @staticmethod
    def _program_of(plan: PlanRow, claims: list[dict], spec: dict) -> dict | None:
        """The signing program a test runs: {"component", "version", "ref", "label", "own"} (own: it is the plan's
        own program, so a retest or a proof runs it on the version chosen there). None for a server test and for
        a test with no program (the ML-DSA-65 figures when the file names none). A test written before phase
        3a-fixes names no claim: it is for the plan's own program, as it always was."""
        target = spec.get("target") or {}
        if target.get("kind") != "software" or not target.get("component"):
            return None
        found = research.programs(claims)
        ref = target.get("claim")
        program = next((p for p in found if p["ref"] == ref), None) if ref is not None else \
            next((p for p in found if (p["component"], p["version"]) == (plan.component_name, plan.component_version)), None)
        if program is None:
            if ref is not None or plan.component_name is None:
                return {"component": str(target["component"]), "version": None, "ref": ref, "label": str(target["component"]), "own": False}
            program = {"ref": None, "component": plan.component_name, "version": plan.component_version,
                       "label": f"{plan.component_name} {plan.component_version}"}
        own = (program["component"], program["version"]) == (plan.component_name, plan.component_version)
        return {**{k: program[k] for k in ("component", "version", "ref", "label")}, "own": own}

    def _groups(self, plan: PlanRow, claims: list[dict], specs: dict, items: list[PlanItemRow]) -> tuple[bool, list[dict], dict[int, str]]:
        """(grouped?, the groups in file order, each item's group key). Grouped when the file names more than one
        server or more than one signing program; with one of each the list stays flat, as it always was."""
        grouped = len(research.servers(claims)) > 1 or len(research.programs(claims)) > 1
        order = [("server:" + a, "server", f"Server: {a}", a) for a in research.servers(claims)]
        order += [("software:" + p["ref"], "software",
                   f"{'Key exchange program' if p.get('role') == 'key_exchange' else 'Signing program'}: {p['label']}", p)
                  for p in research.programs(claims)]
        key_of = {item.id: self._item_key(plan, claims, specs[item.id][0]) for item in items}
        used = set(key_of.values())
        with self.db() as db:
            confirmed = {r.address: r.confirmed for r in db.scalars(select(AddressRow).where(AddressRow.import_id == plan.import_id)).all()}
        groups = []
        for key, side, heading, what in order:
            if key not in used:
                continue
            note = None
            if side == "server" and not confirmed.get(what, False):
                note = "Not confirmed yet: its tests can't run until you tick \u201cI own this system or am allowed to test it\u201d on Import."
            if side == "software" and not components.kind_of(what["component"], what["version"]):
                note = NOT_DEMO_PROGRAM
            elif side == "software":
                note = self._real_note(what)   # a real library that can't run here (demo mode, or its image is missing)
            groups.append({"key": key, "kind": side, "heading": heading, "note": note})
        if "reference" in used:
            groups.append({"key": "reference", "kind": "reference", "heading": "Reference figures (no signing program from the file)", "note": None})
        known = {g["key"] for g in groups}
        for item_id, key in key_of.items():  # a test whose program is no longer in the file still shows, on its own  # noqa: B007
            if key not in known:
                known.add(key)
                groups.append({"key": key, "kind": "software", "heading": "Signing program: " + key.split(":", 1)[-1], "note": None})
        return grouped, groups, key_of

    def _real_note(self, program: dict) -> str | None:
        """Why a real library named in the file can't run on this computer right now, or None when it can (and for
        our own demo components). Said plainly wherever the library shows; nothing of it ever runs as a local program."""
        family = real_libraries.family_of(program["component"], program["version"])
        if family is None:
            return None
        if self.mode.name != "isolated":
            return ("This is real software from outside. It runs only in isolated mode (Docker), and this run is in demo mode, "
                    "so its tests can't run here.")
        if not self.mode.real_images.get(family):
            return (f"This is real software from outside. Its container image ({real_libraries.FAMILIES[family]['label']}) is not prepared on "
                    "this computer, so its tests can't run. ./run-demo.sh prepares it (it needs internet once).")
        return None

    def _item_key(self, plan: PlanRow, claims: list[dict], spec: dict) -> str:
        """The group a test belongs to: "server:<address>", "software:<claim ref>", or "reference"."""
        target = spec.get("target") or {}
        if target.get("kind") == "server":
            return "server:" + str(target.get("address"))
        program = self._program_of(plan, claims, spec)
        return ("software:" + str(program["ref"])) if program and program["ref"] is not None else "reference"

    def _not_tested(self, plan: PlanRow, claims: list[dict], specs: dict, items: list[PlanItemRow], key_of: dict[int, str],
                    every: list[PlanItemRow] | None = None) -> dict | None:
        """What the plan leaves out and why, one plain line each: a suggested test a target doesn't get (with the
        engine's reason), a program whose tests can't run, a server not confirmed yet, a claim no test covers.
        None when nothing is left out. A test the user removed is not listed here: it is back in the catalog."""
        lines: list[str] = []
        have = {(key_of[i.id], specs[i.id][2].kind if specs[i.id][2] else specs[i.id][0].get("kind")) for i in items}
        proposal = self._proposal_for(claims)
        label = {p["ref"]: p["label"] for p in research.programs(claims)}
        for skip in proposal.get("not_suggested") or []:
            key = ("server:" if skip["target_kind"] == "server" else "software:") + str(skip["target"])
            if (key, skip["kind"]) not in have:
                name = skip["target"] if skip["target_kind"] == "server" else label.get(skip["target"], skip["target"])
                lines.append(f"{name}: no {present.TITLES[skip['kind']]} test. {skip['reason']}")
        # A plan made before every target was tested (phase 3a-fixes) can lack a test the engine suggests now. Unless
        # the user removed it (then it is back in the catalog), it is listed, so it is not skipped silently.
        if every is not None:
            def kind_of(i):
                return specs[i.id][2].kind if specs.get(i.id) and specs[i.id][2] else (specs.get(i.id) or ({},))[0].get("kind")
            known = {(self._item_key(plan, claims, specs[i.id][0]), kind_of(i)) for i in every if i.id in specs}
            for test in proposal.get("tests") or []:
                key = self._item_key(plan, claims, test)
                if (key, test["kind"]) not in known:
                    name = key.split(":", 1)[-1] if key.startswith("server:") else label.get(key.split(":", 1)[-1], key.split(":", 1)[-1])
                    lines.append(f"{name}: no {present.TITLES[test['kind']]} test. This test plan was made by an earlier "
                                 "version that tested only the first server and program. Import the file again to test it.")
        with self.db() as db:
            confirmed = {r.address: r.confirmed for r in db.scalars(select(AddressRow).where(AddressRow.import_id == plan.import_id)).all()}
        used = set(key_of.values())
        for address in research.servers(claims):
            if "server:" + address in used and not confirmed.get(address, False):
                lines.append(f"{address}: not confirmed yet, so its tests can't run. Tick \u201cI own this system or am allowed to test it\u201d on Import.")
        for program in research.programs(claims):
            if not components.kind_of(program["component"], program["version"]):
                lines.append(f"{program['label']}: its tests can't run. Only our own demo components can run in this version.")
            elif (note := self._real_note(program)) is not None:
                lines.append(f"{program['label']}: " + note[0].lower() + note[1:])
        tested_pq = {key.split(":", 1)[-1] for (key, kind) in have if kind == "pq_readiness"}
        for c in claims:
            where = c.get("location") or ""
            if c.get("location_kind") == "server" and c.get("kind") == "post_quantum" and where in tested_pq:
                continue   # phase 4b: covered by its Post-quantum readiness test
            if c.get("location_kind") == "server" and c.get("kind") in UNCOVERED:
                lines.append(f"{where}: {UNCOVERED[c['kind']]}")
            elif c.get("location_kind") == "server" and c.get("kind") not in ("protocol_versions", "certificate"):
                lines.append(f"{where}: its {str(c.get('kind')).replace('_', ' ')} claim is not covered by any test in this version.")
            elif c.get("location_kind") == "software" and c.get("kind") != "signature_algorithm" \
                    and str(c.get("ref")) not in label:   # (a key exchange program, phase 4c, has its own tests)
                lines.append(f"{where}: its {str(c.get('kind')).replace('_', ' ')} claim is not covered by any test in this version.")
            elif c.get("location_kind") not in ("server", "software"):
                lines.append(f"{c.get('claimed_value') or 'A claim'}: the file doesn't say where it is used, so nothing can be tested.")
        lines = list(dict.fromkeys(lines))
        return {"title": "Not tested, and why", "items": lines} if lines else None

    @staticmethod
    def _group_order(items: list, key_of: dict[int, str], groups: list[dict], grouped: bool) -> list:
        """Plan order, and when grouped: group by group in file order, plan order inside each group."""
        if not grouped:
            return items
        rank = {g["key"]: n for n, g in enumerate(groups)}
        return sorted(items, key=lambda i: (rank.get(key_of.get(i.id), len(rank)), i.position, i.id))

    @staticmethod
    def _counted_targets(claims: list[dict]) -> str:
        found = research.programs(claims)
        n_servers, n_programs = len(research.servers(claims)), sum(1 for p in found if p.get("role") != "key_exchange")
        n_kem = len(found) - n_programs
        parts = []
        if n_servers:
            parts.append(f"{present.number_word(n_servers)} {'server' if n_servers == 1 else 'servers'}")
        if n_programs:
            parts.append(f"{present.number_word(n_programs)} signing {'program' if n_programs == 1 else 'programs'}")
        if n_kem:
            parts.append(f"{present.number_word(n_kem)} key exchange {'program' if n_kem == 1 else 'programs'}")
        return research.join_and(parts) if len(parts) > 2 else " and ".join(parts)

    def _component_words(self, plan: PlanRow) -> str | None:
        return f"{plan.component_name} {plan.component_version}" if plan.component_name else None

    @staticmethod
    def _server_address(specs: dict) -> str | None:
        for spec, _, _ in specs.values():
            if (spec.get("target") or {}).get("kind") == "server":
                return spec["target"]["address"]
        return None

    def plan_view(self, plan_id: int) -> dict:
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            every = self._items(db, plan_id, include_removed=True)
            items = [i for i in every if not i.removed]
            specs = self._specs(db, every)
            claims = self._claims(imp)
            grouped, groups, key_of = self._groups(plan, claims, specs, items)
            running = self.jobs.busy(plan_id)
            tests = []
            for item in self._group_order(items, key_of, groups, grouped):
                spec, _, row = specs[item.id]
                kind = row.kind if row else spec.get("kind")
                job = self.jobs.get((item.id, "first"))
                reruns = (self.jobs.get((item.id, "retest")), self.jobs.get((item.id, "proof")))
                card = {"id": item.id, "kind": kind, "title": research.title_of(kind, spec), "origin": item.origin,
                        "tag": research.MLDSA_LABEL if kind == "mldsa_compare" else None,
                        "description": (spec.get("card") or {}).get("description", ""), "why": (spec.get("card") or {}).get("why", ""),
                        "group": key_of.get(item.id)}
                # Phase 5c: an advisory check says which advisory it came from, with the way to it (as its locked test names
                # it). Every other card is exactly as it was.
                came_from = ((spec.get("inputs") or {}).get("advisory") or {}).get("id") if kind == research.ADVISORY_KIND else None
                if came_from:
                    card["advisory"] = {"label": f"From advisory {came_from}", "link": {"page": "advisories", "item": str(came_from)}}
                # ... and since Otto's checks are proposals a person accepted: the mark "From Otto", and its remove button
                # is off (an accepted check is undone on Advisories, until it has run).
                kept = self.otto_keeps_in_plan(db, item.id) if came_from else None
                card["from_otto"] = "From Otto" if kept else None
                card["remove_blocked"] = kept
                live = job is not None and job.status != "done"
                if live:
                    state = present.status_view(job.status, job.progress_text, job.progress_percent, self.jobs.max_parallel)
                    card.update(state, result=None)
                else:
                    result = self._latest_result(db, item, "first", None, plan)
                    if result is None:
                        card.update(present.status_view("not_run"), result=None)
                    else:
                        b = {"code": result["code"], "label": result["label"], "tone": result["tone"]}
                        card.update(status="done", status_text=b["label"], progress=None, result=b)
                card["can_run"] = not running
                card["can_remove"] = not kept and not live and not any(j is not None and j.status != "done" for j in reruns)
                tests.append(card)
            has_results = bool(db.scalar(select(func.count(ReviewRow.id)).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                                         .where(TestRunRow.plan_id == plan_id, TestRunRow.phase.not_in(HIDDEN_ORIGINS))))
            # Does the migration plan have something for the Fixes step (a how-to or a blocker)? Then Fixes can be opened.
            # (phase 4b: a system's change is an entry too)
            has_migration = any(state["fix_ids"] for state in self._with_changes(db, plan, self._migration_states(db, plan)))
            # (phase 4d: a library of the dependency list that blocks a track has a Text only entry in Fixes too)
            has_migration = has_migration or any(b for tracks in self._dependency_blockers(db, plan).values() for b in tracks.values())
            suggested = [i for i in items if i.origin == "suggested"]
            added = [i for i in items if i.origin == "added"]
            first_suggested = [i for i in every if i.origin == "suggested"]
            changed = bool(added) or len(suggested) != len(first_suggested)
            subject: list[dict] = [{"t": "text", "v": "Testing: "}]
            address, component = self._server_address(specs), self._component_words(plan)
            if grouped:
                address = component = None
                subject.append({"t": "text", "v": self._counted_targets(claims)})
            if address:
                subject += [{"t": "text", "v": "server "}, {"t": "mono", "v": address}]
            if address and component:
                subject.append({"t": "text", "v": " and "})
            if component:
                subject += [{"t": "text", "v": "signing component "}, {"t": "mono", "v": component}]
            if not address and not component and not grouped:
                subject.append({"t": "text", "v": "nothing in this file can be tested"})
            subject += [{"t": "text", "v": " "}, {"t": "tag", "v": "from the file"}]
            return {"id": plan.id, "import_id": plan.import_id, "is_demo": bool(imp.is_demo),
                    "intro": present.intro(imp.filename, len(suggested), len(added), len(first_suggested), changed),
                    "subject": subject, "grouped": grouped, "groups": groups,
                    "not_tested": self._not_tested(plan, claims, specs, items, key_of, every),
                    "running": running, "can_run_all": bool(items) and not running,
                    "has_results": has_results, "has_migration": has_migration, "max_parallel": self.jobs.max_parallel, "tests": tests,
                    "catalog_title": "Tests you can add", "catalog": self._catalog(db, plan, imp, every, specs),
                    "catalog_note": "Tests you remove from the plan come back to this list."}

    @staticmethod
    def _targets_for(kind: str, claims: list[dict]) -> list[str | None]:
        """The targets a test of this kind can be for: every server address, or every program's claim ref
        (or just None, "the first that fits", for the ML-DSA-65 figures in a file that names no program)."""
        if kind in research.SERVER_KINDS:
            return list(research.servers(claims))
        found = research.programs(claims)
        refs = [p["ref"] for p in found if components.kind_of(p["component"], p["version"])]  # a program that can't run gets no test
        return refs or ([None] if kind == "mldsa_compare" and not found else [])

    def _missing_targets(self, kind: str, claims: list[dict], every: list[PlanItemRow], specs: dict) -> tuple[list, list]:
        """(the removed items of this kind that can come back, one per target; the targets this kind fits that have
        no item of it at all yet)."""
        first = research._software(claims)

        def key(item: PlanItemRow) -> str | None:
            found = research.target_key(kind, specs[item.id][0].get("target") or {})
            if found is None and kind in SOFTWARE_KINDS and first is not None:
                return first["claim"]  # a test written before phase 3a-fixes: for the first program
            return found
        mine = [i for i in every if (specs[i.id][2].kind if specs[i.id][2] else specs[i.id][0].get("kind")) == kind]
        active = {key(i) for i in mine if not i.removed}
        back, seen = [], set(active)
        for item in mine:
            if item.removed and key(item) not in seen:
                back.append(item)
                seen.add(key(item))
        new = []
        for target in self._targets_for(kind, claims):
            if target in seen:
                continue
            try:
                self.engine.design_test({"catalog_id": kind, "claims": claims, "target": target})
            except research.CannotDesign:
                continue  # this test does not fit this target
            new.append(target)
        return back, new

    def _catalog(self, db, plan: PlanRow, imp: ImportRow, every: list[PlanItemRow], specs: dict) -> list[dict]:
        """A test is offered while at least one target it fits doesn't have it in the plan. Adding it adds it to
        every such target. A suggested test only comes back here once removed; the two catalog tests are new."""
        claims = self._claims(imp)
        out = []
        for kind in research.ALL_KINDS:
            back, new = self._missing_targets(kind, claims, every, specs)
            if kind not in research.CATALOG:
                new = []  # a suggested test the engine didn't suggest for a target is listed under "Not tested, and why"
            if not back and not new:
                continue
            if back and not new:
                description = (specs[back[0].id][0].get("card") or {}).get("description", "")
            else:
                description = research.CATALOG_DESCRIPTIONS.get(kind, "").format(component=plan.component_name or "the signing component")
            if kind == "pq_readiness":
                description = research.CATALOG_DESCRIPTIONS[kind]
            out.append({"catalog_id": kind, "title": present.TITLES[kind],
                        "tag": research.MLDSA_LABEL if kind == "mldsa_compare" else None, "description": description})
        return out

    def reorder(self, plan_id: int, order: list[int]) -> dict:
        with self.db() as db:
            self._plan(db, plan_id)
            items = {i.id: i for i in self._items(db, plan_id)}
            if sorted(order) != sorted(items) or len(set(order)) != len(order):
                raise BadRequest("The new order must list every test in the plan exactly once.", field="order")
            for position, item_id in enumerate(order):
                items[item_id].position = position
            db.commit()
        return self.plan_view(plan_id)

    def add_test(self, plan_id: int, catalog_id: str) -> dict:
        if catalog_id not in research.ALL_KINDS:
            raise BadRequest("That test is not in the catalog.", field="catalog_id")
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            every = self._items(db, plan_id, include_removed=True)
            last = max([i.position for i in every], default=-1)
            imp = db.get(ImportRow, plan.import_id)
            claims = self._claims(imp)
            back, new = self._missing_targets(catalog_id, claims, every, self._specs(db, every))
            if catalog_id not in research.CATALOG:
                new = []
            if not back and not new:
                kind_items = [i for i in every if (db.get(TestSpecRow, i.spec_hash) or TestSpecRow(kind=None)).kind == catalog_id]
                if any(not i.removed for i in kind_items):
                    raise Conflict("That test is already in the plan.")
                try:  # say why it doesn't fit
                    self.engine.design_test({"catalog_id": catalog_id, "claims": claims})
                except research.CannotDesign as exc:
                    raise BadRequest(str(exc), field="catalog_id") from exc
                raise Conflict("That test is already in the plan.")
            for item in back:
                last += 1
                item.removed, item.position = False, last  # the same test comes back, with its runs
            for target in new:
                spec = self.engine.design_test({"catalog_id": catalog_id, "claims": claims, "target": target})
                last += 1
                db.add(PlanItemRow(plan_id=plan_id, spec_hash=self._lock_spec(db, spec), position=last,
                                   origin="added", removed=False))
            db.commit()
        return self.plan_view(plan_id)

    def remove_test(self, plan_id: int, item_id: int) -> dict:
        with self.db() as db:
            self._plan(db, plan_id)
            item = db.get(PlanItemRow, item_id)
            if item is None or item.plan_id != plan_id or item.removed or item.origin in HIDDEN_ORIGINS:
                raise NotFound("That test is not in this plan.")
            if any(j is not None and j.status != "done" for j in (self.jobs.get((item_id, phase)) for phase in ("first", "retest", "proof"))):
                raise Conflict("This test is waiting or running. Remove it when it has finished.")
            kept = self.otto_keeps_in_plan(db, item_id)   # phase 5c: a check from one of Otto's proposals is undone on Advisories
            if kept:
                raise Conflict(kept)
            item.removed = True
            db.commit()
        return self.plan_view(plan_id)

    # ---------------------------------------------------------------- running

    def run_test(self, plan_id: int, item_id: int) -> dict:
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                item = db.get(PlanItemRow, item_id)
                if item is None or item.plan_id != plan_id or item.removed or item.origin in HIDDEN_ORIGINS:
                    raise NotFound("That test is not in this plan.")
                running = self._running(plan_id)
                if running:
                    raise Conflict(BUSY[running])
                self._submit(plan, item, "first", None)
        return self.plan_view(plan_id)

    def run_all(self, plan_id: int) -> dict:
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                items = self._items(db, plan_id)
                if not items:
                    raise Conflict("There are no tests in the plan.")
                running = self._running(plan_id)
                if running:
                    raise Conflict(BUSY[running])
                for item in items:
                    self._submit(plan, item, "first", None)
        return self.plan_view(plan_id)

    def _running(self, plan_id: int) -> str | None:
        """What is running for this plan now: "proof", "tests" (first runs or a retest), or None."""
        live = self.jobs.live(plan_id)
        if not live:
            return None
        return "proof" if any(j.key[1] == "proof" for j in live) else "tests"

    def _compare_blocked(self, plan_id: int, items: list[PlanItemRow], missing: int) -> str | None:
        """Why the first results can't be compared with a rerun yet, or None. Retest, Connect demo code and
        Run proof again share this rule; `missing` is how many tests in the plan have no first result."""
        running = self._running(plan_id)
        if running:
            return BUSY[running]
        if missing or not items:
            return "Run every test in the plan first, so there is a result to compare with."
        return None

    def _submit(self, plan: PlanRow, item: PlanItemRow, phase: str, rerun: RetestRow | ProofRow | None) -> Job:
        """Queue one test. (For the multi-target demo file, its test servers are started first if they are not running.) `rerun` is the retest (phase "retest") or the proof (phase "proof") the run belongs to:
        it names the version to run, the plan's own version becomes the baseline, and its id is kept with the run."""
        self.ensure_extra_servers(plan.import_id)
        with self.db() as db:
            row = db.get(TestSpecRow, item.spec_hash)
            spec_row_kind = row.kind if row else None
            spec, _ = read_spec(row)
            claims = self._claims(db.get(ImportRow, plan.import_id))
        # Each test runs on its own target. Only the plan's own program is run on the version a retest or a proof
        # names; every other server and program is tested again as it is.
        program = self._program_of(plan, claims, spec) if spec_row_kind in SOFTWARE_KINDS else None
        if spec_row_kind in SOFTWARE_KINDS and program is None and not spec and plan.component_name is not None:
            program = {"component": plan.component_name, "version": plan.component_version, "own": True}  # unreadable test: as before
        own = bool(program and program["own"]) and phase not in HIDDEN_ORIGINS   # a measurement runs the program as it is
        # Which program a rerun swaps to the version it names: the plan's own program, or (phase 4c) the program a
        # retest was started for. Every other program is run again on the version the file names.
        swap = bool(rerun and own)
        other = self._retest_component(rerun.id) if (rerun is not None and phase == "retest") else None
        if other is not None:
            swap = bool(program) and program["component"] == other and program["version"] == rerun.baseline_version
        version = (rerun.version if swap else program["version"]) if program else None
        args = {"plan_id": plan.id, "import_id": plan.import_id, "item_id": item.id, "spec_hash": item.spec_hash, "phase": phase,
                "retest_id": rerun.id if rerun else None, "component_name": program["component"] if program else None,
                "component_version": version,
                "baseline_version": (rerun.baseline_version if other is not None else plan.component_version) if swap else None,
                "own": own}  # the plan's own program: in a proof, only it runs the changed code
        try:
            group = (phase, plan.id) if phase in HIDDEN_ORIGINS else plan.id   # measuring doesn't make Tests "busy"
            return self.jobs.submit((item.id, phase), lambda job: self._run_one(job, args), group=group)
        except ValueError as exc:
            raise Conflict("This test is already waiting or running.") from exc

    def _retest_component(self, retest_id: int) -> str | None:
        """The program a retest swaps when it is not the plan's own (phase 4c), else None."""
        with self.db() as db:
            row = db.get(RetestProgramRow, retest_id)
            return row.component_name if row is not None else None

    def _address_check(self, import_id: int, address: str) -> AddressCheck | None:
        """Phase 1's gate, rebuilt from the address as it is NOW: this computer or confirmed, and the IP pinned."""
        extra, problems = self.extra_identity(import_id)
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            row = db.scalars(select(AddressRow).where(AddressRow.import_id == import_id, AddressRow.address == address)).first()
            if imp is None or row is None:
                return None
            demo = DemoContext(is_demo_import=imp.is_demo, host=DEMO_HOSTNAME, port=self.settings.demo_tls_port,
                               running=self.demo.running, error=self.demo.error, fingerprint=self.demo.fingerprint,
                               allow_external=self.allow_external_demo_server and self.demo.port_in_use,
                               extra=extra, extra_problems=problems)
            db.expunge(row)
        return AddressCheck(row, demo, resolver=self.resolver)

    def _copy_check(self, copy: dict, address: str) -> AddressCheck:
        """Phase 4b: the gate for a run on a test copy. The copy is on this computer, started by this app for this run:
        its port, and the fingerprint of the test certificate it was given, so the run checks it is talking to it."""
        from types import SimpleNamespace
        row = SimpleNamespace(address=address, host=DEMO_HOSTNAME, port=int(copy["port"]), confirmed=True, resolved_ip="127.0.0.1",
                              is_loopback=True, error=None)
        demo = DemoContext(is_demo_import=False, host=DEMO_HOSTNAME, port=-1, running=True, error=None, fingerprint=None,
                           extra={int(copy["port"]): copy["fingerprint"]}, extra_problems={})
        return AddressCheck(row, demo, resolver=lambda host: ["127.0.0.1"], mode=self.mode)

    def _run_one(self, job: Job, a: dict) -> None:
        """One job: run the locked test, write the run record, then have it reviewed. Leaves a run and a review,
        except when the app is closing: an interrupted test leaves nothing, so it reads "Not run yet" afterwards."""
        if self._stopping:
            return
        started, t0 = _now(), time.perf_counter()
        with self.db() as db:
            spec_row = db.get(TestSpecRow, a["spec_hash"])
            spec, spec_ok = read_spec(spec_row)
            proposed_by = spec_row.proposed_by if spec_row else "unknown"
            # Phase 5c: an advisory check that a person added from a test pack runs only when its run can be recorded.
            no_otto = self._otto_cannot_run(db, a["item_id"])
        component = (a["component_name"], a["component_version"]) if a["component_name"] else None
        code = self._code_for_run(a)  # which code this run is about to run on (None when no component of ours runs)
        if not spec_ok:
            raw = problem("spec_changed", "The stored test no longer matches the fingerprint it was locked with, so it was not run.")
        elif a.get("copy_problem"):   # phase 4b: the test copy for a try could not be started
            raw = problem("copy_unavailable", a["copy_problem"])
        elif no_otto is not None:
            raw = problem("otto_not_installed", f"{no_otto} The run of an advisory check must be recorded in Otto's ledger, so it was not run.")
        else:
            # Phase 4b: a run "on a test copy" connects to the copy this app started for it, never to the real address.
            check_for = ((lambda address: self._copy_check(a["copy"], address)) if a.get("copy")
                         else (lambda address: self._address_check(a["import_id"], address)))
            ctx = RunContext(settings=self.settings, mode=self.mode, runner=self.component_runner, gate=self.jobs.gate,
                             progress=job.progress, log=job.log, address_check=check_for,
                             component=component, baseline_version=a["baseline_version"])
            try:
                raw = execute(spec, ctx)
            except BaseException as exc:  # execute() already catches; this is the last line of defence
                raw = problem("harness_error", f"The test stopped unexpectedly ({exc.__class__.__name__}).")
            if ctx.timing:  # time from when the work itself began, not counting the wait for its turn
                started, t0 = ctx.timing["started_at"], ctx.timing["t0"]
        if self._stopping:  # the app began closing while this test was waiting or running: its outcome means nothing
            return
        job.progress("checking the result", 98)
        if a.get("copy") or a.get("copy_problem"):   # which copy this run measured (part of the fingerprinted record)
            copy = a.get("copy") or {}
            raw = {**raw, "copy": {"label": a.get("copy_label"), "port": copy.get("port"), "settings": copy.get("settings"),
                                   "accepted": copy.get("accepted"), "problem": a.get("copy_problem")}}
        try:
            raw = json.loads(json.dumps(components.scrub(raw), allow_nan=False))  # redacted, and exactly what will be stored
        except (TypeError, ValueError):
            raw = problem("harness_error", "The test's raw outcome could not be stored.")
        logs = components.redact("\n".join(job.logs))[:20000]
        row = TestRunRow(plan_id=a["plan_id"], plan_item_id=a["item_id"], spec_hash=a["spec_hash"], phase=a["phase"],
                         retest_id=a["retest_id"], component_name=a["component_name"], component_version=a["component_version"],
                         baseline_version=a["baseline_version"], mode=self.mode.name, started_at=started, finished_at=_now(),
                         duration_ms=int((time.perf_counter() - t0) * 1000), raw=raw, logs=logs, runner=RUNNER_ID)
        with self.db() as db:
            db.add(row)
            db.flush()
            if code is not None:
                db.add(RunCodeRow(run_id=row.id, **code))
            db.commit()
            run_id = row.id
            record = run_record(row)
        # The separate review: a different module with a different engine id, working from the stored record only.
        try:
            review = self.reviewer.review({"spec": spec, "spec_hash": a["spec_hash"], "proposed_by": proposed_by, "run": record})
        except Exception as exc:
            review = {"reviewer": self.reviewer.engine_id, "proposed_by": proposed_by, "spec_hash": a["spec_hash"],
                      "spec_hash_ok": bool(spec_ok), "run_sha256": sha256_hex(record),
                      "control": {"outcome": "errored", "reason": f"the review could not be completed ({exc.__class__.__name__})"},
                      "reference_ok": None, "verdict": {"code": "couldnt_trust", "reason_code": None,
                                                        "reason": "The review step could not be completed, so this run can't be trusted."},
                      "detail": {}}
        with self.db() as db:
            db.add(ReviewRow(run_id=run_id, reviewer=review["reviewer"], proposed_by=review["proposed_by"],
                             spec_hash=review["spec_hash"], spec_hash_ok=review["spec_hash_ok"], run_sha256=review["run_sha256"],
                             control_outcome=review["control"]["outcome"], control_reason=review["control"]["reason"],
                             reference_ok=review["reference_ok"], code=review["verdict"]["code"],
                             reason_code=review["verdict"]["reason_code"], reason=review["verdict"]["reason"],
                             detail=review["detail"]))
            db.commit()
        try:
            # Phase 5c: a reviewed run of an advisory check is bound to its locked test in the assessment's Otto ledger.
            self._otto_after_review(run_id)
        except Exception as exc:  # the run and its review are already stored: a ledger problem never loses them
            job.log(f"the Otto ledger entry for this run could not be written ({exc.__class__.__name__})")
        job.run_id = run_id
        if a["phase"] == "proof":
            self._proof_run_finished(a["retest_id"])  # the proof itself is reviewed when its last run has been

    def wait_until_idle(self, plan_id: int, timeout: float = 300.0) -> None:
        if not self.jobs.wait_idle(timeout, group=plan_id):
            raise TimeoutError("The tests did not finish in time.")

    # ---------------------------------------------------------------- results (read gate)

    def _fix_version(self, name: str | None, version: str | None) -> str | None:
        versions = components.versions_of(name)
        if version in versions and versions.index(version) + 1 < len(versions):
            return f"{name} {versions[versions.index(version) + 1]}"
        return None

    def _result(self, db, run: TestRunRow) -> dict | None:
        """The worded result of one run, or None if it has no review (then nothing is shown for it)."""
        review_row = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
        if review_row is None:
            return None
        spec_row = db.get(TestSpecRow, run.spec_hash)
        spec, spec_ok = read_spec(spec_row)
        record = run_record(run)
        stored = review_dict(review_row)
        code = self._run_code(db, run.id)
        # Phase 5c: for an advisory check, the fix the installed test packs carry (words only; it changes no result).
        advisory_fix = (self.otto_result_fix(db, spec, run.component_name, run.component_version, run.plan_id)
                        if spec_row is not None and spec_row.kind == research.ADVISORY_KIND else None)
        key = (sha256_hex(record), sha256_hex({k: v for k, v in stored.items() if k != "created_at"}), spec_ok, spec_row.hash if spec_row else None,
               sha256_hex(code), sha256_hex(advisory_fix))
        cached = self._result_cache.get(run.id)
        if cached is not None and cached[0] == key:
            base = cached[1]
        else:
            trusted = spec_ok and key[0] == stored["run_sha256"] and stored["spec_hash"] == run.spec_hash
            if trusted:
                # Do the review again from the stored record: the stored verdict must be exactly what the record gives.
                try:
                    again = self.reviewer.review({"spec": spec, "spec_hash": run.spec_hash, "proposed_by": stored["proposed_by"], "run": record})
                    trusted = (again["verdict"]["code"], again["verdict"]["reason_code"], again["control"]["outcome"], again["reference_ok"],
                               again["spec_hash_ok"], canonical_bytes(again["detail"])) == \
                              (stored["code"], stored["reason_code"], stored["control"]["outcome"], stored["reference_ok"],
                               stored["spec_hash_ok"], canonical_bytes(stored["detail"]))
                except Exception:
                    trusted = False
            if not spec:
                spec = {"kind": spec_row.kind if spec_row else "tls_versions", "title": "", "question": "", "method": "", "inputs_text": [],
                        "control": {"text": ""}, "rule_text": "", "target": {}, "inputs": {}}
            base = present.lab_result(spec=spec, spec_hash=run.spec_hash, locked_at=iso(spec_row.locked_at) if spec_row else "",
                                      run_id=run.id, run=record, review=stored, trusted=bool(trusted),
                                      mark=None, research=None, fix_version=self._fix_version(run.component_name, run.component_version),
                                      code=code, advisory_fix=advisory_fix)
            self._result_cache[run.id] = (key, base, bool(trusted))
        result = dict(base)
        if result.get("also_noticed") and (spec_row.kind if spec_row else None) == "certificate":
            # The note is for what the file didn't ask about: none when the file also claims this server's TLS versions.
            plan = db.get(PlanRow, run.plan_id)
            imp = db.get(ImportRow, plan.import_id) if plan is not None else None
            address = ((spec or {}).get("target") or {}).get("address")
            if imp is not None and any(c.location_kind == "server" and c.kind == "protocol_versions" and c.location == address
                                       for c in imp.claims):
                result["also_noticed"] = []
        mark = db.scalars(select(ReviewMarkRow).where(ReviewMarkRow.run_id == run.id)).first()
        request = db.scalars(select(ResearchRequestRow).where(ResearchRequestRow.run_id == run.id)).first()
        if mark is not None:
            result["reviewed"] = {"at": iso(mark.created_at), "text": "You marked this result as reviewed."}
        if request is not None:
            result["research"] = present.research_view({"id": request.id, "status": request.status, "finding": request.finding,
                                                        "question": request.question, "created_at": iso(request.created_at)})
        return result

    def _verdict(self, db, run: TestRunRow) -> dict | None:
        """One run's verdict as the read gate lets it through, for code that needs the verdict and not the words:
        None without a review; otherwise the run record's fingerprint and the result code that is shown, with
        the review's reason code and control outcome only while the stored record and review still stand."""
        shown = self._result(db, run)
        if shown is None:
            return None
        key, _, trusted = self._result_cache[run.id]
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
        stands = trusted and shown["code"] == review.code
        return {"run_id": run.id, "run_sha256": key[0], "code": shown["code"],
                "reason_code": review.reason_code if stands else None,
                "control_outcome": review.control_outcome if stands else "not_run"}

    @staticmethod
    def _run_code(db, run_id: int) -> dict | None:
        """Which code a run ran on, as it was stored beside the run (None when no component of ours ran in it)."""
        row = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == run_id)).first()
        return {k: getattr(row, k) for k in CODE_KEYS} if row is not None else None

    @staticmethod
    def _latest_run(db, item_id: int, phase: str, rerun_id: int | None) -> TestRunRow | None:
        """The newest reviewed run of one test in one phase (for a retest or a proof: of that one)."""
        query = (select(TestRunRow).join(ReviewRow, ReviewRow.run_id == TestRunRow.id)
                 .where(TestRunRow.plan_item_id == item_id, TestRunRow.phase == phase))
        if rerun_id is not None:
            query = query.where(TestRunRow.retest_id == rerun_id)
        return db.scalars(query.order_by(TestRunRow.id.desc()).limit(1)).first()

    def _latest_result(self, db, item: PlanItemRow, phase: str, retest_id: int | None, plan: PlanRow) -> dict | None:
        run = self._latest_run(db, item.id, phase, retest_id)
        return self._result(db, run) if run is not None else None

    def _row_status(self, item_id: int, phase: str) -> dict:
        job = self.jobs.get((item_id, phase))
        if job is not None and job.status != "done":
            return present.status_view(job.status, job.progress_text, job.progress_percent, self.jobs.max_parallel)
        return present.status_view("not_run")

    def lab_view(self, plan_id: int) -> dict:
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            items = self._items(db, plan_id)
            every_items = self._items(db, plan_id, include_removed=True)
            specs = self._specs(db, every_items)
            claims = self._claims(imp)
            grouped, groups, key_of = self._groups(plan, claims, specs, items)
            retest = db.scalars(select(RetestRow).where(RetestRow.plan_id == plan_id).order_by(RetestRow.id.desc()).limit(1)).first()
            # What is running is asked FIRST, on purpose, and the answer carries it as "busy" (the Fixes view does the
            # same). The screen asks again for as long as an answer is busy. So if a job ends while the rest is put
            # together, this answer may still say "A proof is running in Fixes" or "Tests are still running" next to
            # results that are already settled, but it cannot stay on the screen: it is busy, the screen asks again,
            # and the next answer is the settled one. That holds whichever rows are shown, also when the tests a
            # fix is for are no longer in the plan and no row carries its line.
            running = self._running(plan_id)
            busy = running is not None
            retest_live = [j for j in self.jobs.live(plan_id) if j.key[1] == "retest"]
            rows, missing, finished, after_finished, after_done = [], 0, [], [], 0
            for item in self._group_order(items, key_of, groups, grouped):
                spec, _, spec_row = specs[item.id]
                kind = spec_row.kind if spec_row else spec.get("kind")
                first_job = self.jobs.get((item.id, "first"))
                first_live = first_job is not None and first_job.status != "done"
                result = None if first_live else self._latest_result(db, item, "first", None, plan)
                row = {"item_id": item.id, "kind": kind, "title": research.title_of(kind, spec), "control_line": "",
                       "result": result, "result_status": None if result else self._row_status(item.id, "first"),
                       "after": None, "after_status": None, "group": key_of.get(item.id)}
                if result is None:
                    missing += 1
                else:
                    finished.append(result["finished_at"])
                    row["control_line"] = result["control"]["line"]
                if retest is not None:
                    job = self.jobs.get((item.id, "retest"))
                    live = job is not None and job.status != "done"
                    after = None if live else self._latest_result(db, item, "retest", retest.id, plan)
                    row["after"], row["after_status"] = after, (None if after else self._row_status(item.id, "retest"))
                    if after is not None:
                        after_done += 1
                        after_finished.append(after["finished_at"])
                        if result is not None:
                            row["control_line"] = present.both_control_line(kind, result["control"]["outcome"], after["control"]["outcome"])
                rows.append(row)
            # Where a fix stands changes after a run, so its one line is laid over the worded result here, never
            # kept with it. A failed result with a fix shows that line in place of the "Suggested fix" text.
            # The lines are worked out AFTER the rows, so they cover every result a row shows, also one whose test
            # ended while the rows were being read.
            lines = self._fix_lines(db, plan)
            for row in rows:
                for shown in (row["result"], row["after"]):
                    if shown is not None:
                        shown["fix_line"] = lines.get(shown["run_id"])
                        if shown["fix_line"] is not None:
                            shown["suggested_fix"] = None
            address, component = self._server_address(specs), self._component_words(plan)
            n_word = present.number_word(len(items))
            choices = self._retest_choices(plan, claims)
            versions = components.VERSIONS.get(plan.component_name or "", [])
            if not choices:
                blocked = ("A retest needs one of our demo signing components, and this file doesn't name one." if not self._real_programs(claims)
                           else "A retest needs a program that has another version in this app, and this file names none.")
            else:
                blocked = BUSY[running] if busy else self._compare_blocked(plan_id, items, missing)
            menu = self._retest_menu(plan, choices, self._merged_versions(db, plan))
            only_demo = all(components.lookup(p["component"], p["version"]) for p in choices)
            tests_word = f"the same {n_word} locked {'test' if len(items) == 1 else 'tests'}"
            retest_view = {"can_start": blocked is None, "blocked_reason": blocked, "running": bool(retest_live),
                           "progress_text": (f"Retest running: {after_done} of {len(items)} tests finished." if retest_live else None),
                           "menu_title": "Choose the version to retest", "versions": menu,
                           "menu_note": (f"Choosing a version reruns {tests_word} on it and shows before and after. "
                                         f"Only our {present.number_word(len(versions))} demo versions can be chosen here." if only_demo else
                                         f"Choosing a version reruns {tests_word} with that library moved to it, and shows before and after. "
                                         "Every other program is tested again as it is. Only the versions listed here can be chosen.")}
            any_result = len(items) > missing or self._has_migration(db, plan_id)   # a migration measurement counts too
            # Phase 5b: evidence starts at the first Verify result, and any reviewed check of any kind counts.
            any_result = any_result or db.scalar(select(func.count(VerifyRunRow.id)).where(VerifyRunRow.import_id == plan.import_id)) > 0
            any_result = any_result or db.scalar(select(func.count(ReviewRow.id)).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                                                 .where(TestRunRow.plan_id == plan_id)) > 0
            download = {"can_start": any_result and not busy,
                        "blocked_reason": None if any_result and not busy else
                        (BUSY[running] if busy else "Verify the claims first, so there is something to download.")}
            if grouped:
                address = component = None
            if retest is None:
                subline: list[dict] = [{"t": "text", "v": "Results by test for "}]
                if grouped:
                    subline.append({"t": "text", "v": self._counted_targets(claims)})
                if address:
                    subline += [{"t": "text", "v": "server "}, {"t": "mono", "v": address}]
                if address and component:
                    subline.append({"t": "text", "v": " and "})
                if component:
                    subline += [{"t": "text", "v": "signing component "}, {"t": "mono", "v": component}]
                if running == "tests":  # a proof in Fixes reruns the tests too, but these results are not being replaced
                    subline.append({"t": "text", "v": ". Tests are running."})
                elif finished:
                    subline += [{"t": "text", "v": ". Run finished "}, {"t": "time", "v": max(finished)}, {"t": "text", "v": "."}]
                else:
                    subline.append({"t": "text", "v": ". No test has been run yet."})
                view, columns, code_line = "results", None, None
            else:
                swapped = self._retest_component(retest.id) or plan.component_name
                before, after_name = f"{swapped} {retest.baseline_version}", f"{swapped} {retest.version}"
                subline = [{"t": "text", "v": f"Before and after: the same {n_word} locked {'test' if len(items) == 1 else 'tests'}, run on "},
                           {"t": "mono", "v": before}, {"t": "text", "v": " and then on "}, {"t": "mono", "v": after_name}]
                if grouped:
                    subline.append({"t": "text", "v": ". Every other server and program was tested again as it is"})
                if retest_live:
                    subline.append({"t": "text", "v": ". Retest running."})
                elif after_finished:
                    subline += [{"t": "text", "v": ". Retest finished "}, {"t": "time", "v": max(after_finished)}, {"t": "text", "v": "."}]
                else:
                    subline.append({"t": "text", "v": "."})
                ran_on = self._column_code(db, rows, "result"), self._column_code(db, rows, "after")
                view, code_line = "before_after", present_fixes.code_line(*ran_on)
                columns = {"test": "Test", **present_fixes.code_columns(f"Before: {before}", f"After: {after_name}", *ran_on)}
            return {"plan_id": plan.id, "is_demo": bool(imp.is_demo), "view": view, "subline": subline, "code_line": code_line,
                    "grouped": grouped, "groups": groups,
                    "not_tested": self._not_tested(plan, claims, specs, items, key_of, every_items),
                    "disclaimer": present.DISCLAIMER, "columns": columns, "rows": rows, "retest": retest_view, "download": download,
                    # (asked once more at the end: work that another request started meanwhile also makes the screen ask again)
                    "busy": busy or any(line["busy"] for line in lines.values()) or self.jobs.busy(plan_id)}

    # ---------------------------------------------------------------- the user's own actions on a result

    def _reviewed_run(self, db, run_id: int) -> tuple[TestRunRow, ReviewRow]:
        run = db.get(TestRunRow, run_id)
        if run is None:
            raise NotFound("That result does not exist.")
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run_id)).first()
        if review is None:
            raise Conflict("This run has not been reviewed yet.")
        return run, review

    def mark_reviewed(self, run_id: int) -> dict:
        with self._plan_lock, self.db() as db:
            run, _ = self._reviewed_run(db, run_id)
            if db.scalars(select(ReviewMarkRow).where(ReviewMarkRow.run_id == run_id)).first() is None:
                db.add(ReviewMarkRow(run_id=run_id))
                db.commit()
            plan_id = run.plan_id
        return self.lab_view(plan_id)

    def dig_deeper(self, run_id: int) -> dict:
        """Save a research request for this result. Nothing is looked into and no answer is made up."""
        with self._plan_lock, self.db() as db:
            run, review = self._reviewed_run(db, run_id)
            plan_id = run.plan_id
            if db.scalars(select(ResearchRequestRow).where(ResearchRequestRow.run_id == run_id)).first() is None:
                spec, _ = read_spec(db.get(TestSpecRow, run.spec_hash))
                view = self._result(db, run) or {}
                request = self.engine.dig_deeper({"run_id": run_id, "spec": spec, "review": review_dict(review), "view": view})
                db.add(ResearchRequestRow(run_id=run_id, finding=request["finding"], question=request["question"],
                                          evidence=request["evidence"], status=request["status"], engine=self.engine.engine_id))
                db.commit()
        return self.lab_view(plan_id)

    # ---------------------------------------------------------------- retest

    @staticmethod
    def _real_programs(claims: list[dict]) -> list[dict]:
        return [p for p in research.programs(claims) if components.kind_of(p["component"], p["version"]) == "real"]

    @staticmethod
    def _retest_choices(plan: PlanRow, claims: list[dict]) -> list[dict]:
        """The programs in the file a retest can move to another version: each registered program (one of our demo
        components, or since phase 4c a real library) that has more than one version in this app. Once per name."""
        out, seen = [], set()
        for p in research.programs(claims):
            versions = components.versions_of(p["component"])
            if p["component"] in seen or p["version"] not in versions or len(versions) < 2 \
                    or not components.kind_of(p["component"], p["version"]):
                continue
            seen.add(p["component"])
            out.append(p)
        return out

    @staticmethod
    def _retest_menu(plan: PlanRow, choices: list[dict], merged: list[str] | None = None) -> list[dict]:
        """`merged`: the registered versions that a merged change of this plan gives and that are not in the general
        list (phase 5c: the program Otto's change gives). They are offered for the plan's own program only."""
        menu = []
        for p in choices:
            name, current, versions = p["component"], p["version"], components.versions_of(p["component"])
            demo = components.lookup(name, current) is not None
            if demo and name == plan.component_name:
                versions = versions + [v for v in (merged or []) if v not in versions]
            for v in sorted(versions, key=lambda v: (v == current, -versions.index(v))):
                if demo and v in (merged or []) and components.version_note(name, v):
                    note = "The version your merged change gives. " + str(components.version_note(name, v))
                elif demo:
                    note = ("The demo version these results are for." if v == current
                            else "The corrected demo version." if versions.index(v) > versions.index(current) else "An earlier demo version.")
                else:
                    fixes = [cve for cve in (real_libraries.LIBRARIES[name]["advisories"].get(current, ()))
                             if real_libraries.fixed_version(name, current) == v]
                    note = ("The version these results are for." if v == current
                            else f"The version its publisher fixed {research.join_and(fixes)} in." if fixes
                            else "A later version." if versions.index(v) > versions.index(current) else "An earlier version.")
                menu.append({"version": v, "component": name, "label": f"{name} {v}", "tag": "demo" if demo else "real software", "note": note})
        return menu

    def start_retest(self, plan_id: int, version: str, component: str | None = None) -> dict:
        """`component` names the program to move to `version` (phase 4c). Left out, it is the plan's own program."""
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                claims = self._claims(db.get(ImportRow, plan.import_id))
                choices = {p["component"]: p for p in self._retest_choices(plan, claims)}
                if not choices:
                    raise Conflict("A retest needs one of our demo signing components, and this file doesn't name one." if not self._real_programs(claims)
                                   else "A retest needs a program that has another version in this app, and this file names none.")
                name = component if component is not None else (plan.component_name if plan.component_name in choices else next(iter(choices)))
                if name not in choices:
                    raise BadRequest("That program can't be chosen for a retest of this file.", field="component")
                # (a registered version that only a change leads to can be chosen once that change is merged in this plan)
                allowed = components.versions_of(name) + (self._merged_versions(db, plan) if name == plan.component_name else [])
                if version not in allowed:
                    raise BadRequest("Only our demo versions can be chosen for a retest." if components.lookup(name, choices[name]["version"])
                                     else "Only the versions listed for this library can be chosen for a retest.", field="version")
                baseline = choices[name]["version"]
            view = self.lab_view(plan_id)
            if not view["retest"]["can_start"]:
                raise Conflict(view["retest"]["blocked_reason"] or "A retest can't start right now.")
            with self.db() as db:
                plan = self._plan(db, plan_id)
                retest = RetestRow(plan_id=plan_id, baseline_version=baseline, version=version)
                db.add(retest)
                db.flush()
                if name != plan.component_name:
                    db.add(RetestProgramRow(retest_id=retest.id, component_name=name))
                db.commit()
                for item in self._items(db, plan_id):
                    self._submit(plan, item, "retest", retest)
        return self.lab_view(plan_id)
