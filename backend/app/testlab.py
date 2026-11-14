"""The Tests and Evidence Lab actions, used by the web API, pytest and the accuracy command alike.

One path for everything: propose -> lock -> run through the job runner -> run record -> separate review.
A result is only ever shown from a Review row, and only while the stored test and run record still match
the fingerprints the review was made for."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from . import components, present, present_fixes, research
from .canonical import canonical_bytes, sha256_hex
from .config import DEMO_HOSTNAME
from .db import (
    AddressRow, ImportRow, PlanItemRow, PlanRow, ProofRow, ResearchRequestRow, RetestRow, ReviewMarkRow, ReviewRow,
    RunCodeRow, TestRunRow, TestSpecRow, iso,
)
from .errors import BadRequest, Conflict, NotFound
from .execute import RunContext, execute, problem
from .jobs import Job
from .verify import AddressCheck, DemoContext

RUNNER_ID = "isogeny.runner/1"
RUN_SCHEMA = "isogeny.run/1"
SOFTWARE_KINDS = ("official_vectors", "bad_signatures", "speed_size", "mldsa_compare")
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

    def _init_testlab(self) -> None:
        self._plan_lock = threading.Lock()
        self._result_cache: dict[int, tuple] = {}

    # ---------------------------------------------------------------- plans

    @staticmethod
    def _claims(imp: ImportRow) -> list[dict]:
        return [{"ref": c.ref, "location": c.location, "location_kind": c.location_kind, "kind": c.kind,
                 "claimed_value": c.claimed_value, "detail": dict(c.detail or {})} for c in imp.claims]

    def _lock_spec(self, db, spec: dict) -> str:
        """Write the test down and lock it. The same test proposed again is the same row (same fingerprint)."""
        text = canonical_bytes(spec).decode("utf-8")
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if db.get(TestSpecRow, key) is None:
            db.add(TestSpecRow(hash=key, kind=spec["kind"], canonical=text, proposed_by=self.engine.engine_id))
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
                proposal = self.engine.propose_tests(claims)
                software = research._software(claims)
                version = next((str(c["detail"].get("version")) for c in claims if c["location_kind"] == "software"
                                and c["kind"] == "signature_algorithm" and c["detail"].get("version")), None)
                plan = PlanRow(import_id=import_id, component_name=software["component"] if software else None,
                               component_version=version if software else None)
                db.add(plan)
                db.flush()
                for position, spec in enumerate(proposal["tests"]):
                    db.add(PlanItemRow(plan_id=plan.id, spec_hash=self._lock_spec(db, spec), position=position,
                                       origin="suggested", removed=False))
                db.commit()
            plan_id = plan.id
        return self.plan_view(plan_id)

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
        rows = db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan_id).order_by(PlanItemRow.position, PlanItemRow.id)).all()
        return [r for r in rows if include_removed or not r.removed]

    def _specs(self, db, items: list[PlanItemRow]) -> dict[int, tuple[dict, bool, TestSpecRow]]:
        out = {}
        for item in items:
            row = db.get(TestSpecRow, item.spec_hash)
            spec, ok = read_spec(row)
            out[item.id] = (spec, ok, row)
        return out

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
            running = self.jobs.busy(plan_id)
            tests = []
            for item in items:
                spec, _, row = specs[item.id]
                kind = row.kind if row else spec.get("kind")
                job = self.jobs.get((item.id, "first"))
                reruns = (self.jobs.get((item.id, "retest")), self.jobs.get((item.id, "proof")))
                card = {"id": item.id, "kind": kind, "title": present.TITLES.get(kind, str(kind)), "origin": item.origin,
                        "tag": research.MLDSA_LABEL if kind == "mldsa_compare" else None,
                        "description": (spec.get("card") or {}).get("description", ""), "why": (spec.get("card") or {}).get("why", "")}
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
                card["can_remove"] = not live and not any(j is not None and j.status != "done" for j in reruns)
                tests.append(card)
            has_results = bool(db.scalar(select(func.count(ReviewRow.id)).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                                         .where(TestRunRow.plan_id == plan_id)))
            suggested = [i for i in items if i.origin == "suggested"]
            added = [i for i in items if i.origin == "added"]
            first_suggested = [i for i in every if i.origin == "suggested"]
            changed = bool(added) or len(suggested) != len(first_suggested)
            subject: list[dict] = [{"t": "text", "v": "Testing: "}]
            address, component = self._server_address(specs), self._component_words(plan)
            if address:
                subject += [{"t": "text", "v": "server "}, {"t": "mono", "v": address}]
            if address and component:
                subject.append({"t": "text", "v": " and "})
            if component:
                subject += [{"t": "text", "v": "signing component "}, {"t": "mono", "v": component}]
            if not address and not component:
                subject.append({"t": "text", "v": "nothing in this file can be tested"})
            subject += [{"t": "text", "v": " "}, {"t": "tag", "v": "from the file"}]
            return {"id": plan.id, "import_id": plan.import_id, "is_demo": bool(imp.is_demo),
                    "intro": present.intro(imp.filename, len(suggested), len(added), len(first_suggested), changed),
                    "subject": subject, "running": running, "can_run_all": bool(items) and not running,
                    "has_results": has_results, "max_parallel": self.jobs.max_parallel, "tests": tests,
                    "catalog_title": "Tests you can add", "catalog": self._catalog(db, plan, imp, every, specs),
                    "catalog_note": "Tests you remove from the plan come back to this list."}

    def _catalog(self, db, plan: PlanRow, imp: ImportRow, every: list[PlanItemRow], specs: dict) -> list[dict]:
        by_kind = {(specs[i.id][2].kind if specs[i.id][2] else None): i for i in every}
        claims = self._claims(imp)
        out = []
        for kind in research.ALL_KINDS:
            item = by_kind.get(kind)
            if item is not None and not item.removed:
                continue
            if item is not None:
                description = (specs[item.id][0].get("card") or {}).get("description", "")
            else:
                try:
                    self.engine.design_test({"catalog_id": kind, "claims": claims})
                except research.CannotDesign:
                    continue  # this test does not fit the imported file
                if kind not in research.CATALOG:
                    continue
                description = research.CATALOG_DESCRIPTIONS[kind].format(component=plan.component_name or "the signing component")
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
            existing = next((i for i in every if (db.get(TestSpecRow, i.spec_hash) or TestSpecRow(kind=None)).kind == catalog_id), None)
            if existing is not None and not existing.removed:
                raise Conflict("That test is already in the plan.")
            if existing is not None:
                existing.removed, existing.position = False, last + 1  # the same test comes back, with its runs
            else:
                imp = db.get(ImportRow, plan.import_id)
                try:
                    spec = self.engine.design_test({"catalog_id": catalog_id, "claims": self._claims(imp)})
                except research.CannotDesign as exc:
                    raise BadRequest(str(exc), field="catalog_id") from exc
                db.add(PlanItemRow(plan_id=plan_id, spec_hash=self._lock_spec(db, spec), position=last + 1,
                                   origin="added", removed=False))
            db.commit()
        return self.plan_view(plan_id)

    def remove_test(self, plan_id: int, item_id: int) -> dict:
        with self.db() as db:
            self._plan(db, plan_id)
            item = db.get(PlanItemRow, item_id)
            if item is None or item.plan_id != plan_id or item.removed:
                raise NotFound("That test is not in this plan.")
            if any(j is not None and j.status != "done" for j in (self.jobs.get((item_id, phase)) for phase in ("first", "retest", "proof"))):
                raise Conflict("This test is waiting or running. Remove it when it has finished.")
            item.removed = True
            db.commit()
        return self.plan_view(plan_id)

    # ---------------------------------------------------------------- running

    def run_test(self, plan_id: int, item_id: int) -> dict:
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                item = db.get(PlanItemRow, item_id)
                if item is None or item.plan_id != plan_id or item.removed:
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
        """Queue one test. `rerun` is the retest (phase "retest") or the proof (phase "proof") the run belongs to:
        it names the version to run, the plan's own version becomes the baseline, and its id is kept with the run."""
        spec_row_kind = None
        with self.db() as db:
            row = db.get(TestSpecRow, item.spec_hash)
            spec_row_kind = row.kind if row else None
        software = spec_row_kind in SOFTWARE_KINDS and plan.component_name is not None
        version = (rerun.version if rerun else plan.component_version) if software else None
        args = {"plan_id": plan.id, "import_id": plan.import_id, "item_id": item.id, "spec_hash": item.spec_hash, "phase": phase,
                "retest_id": rerun.id if rerun else None, "component_name": plan.component_name if software else None,
                "component_version": version,
                "baseline_version": plan.component_version if (rerun and software) else None}
        try:
            return self.jobs.submit((item.id, phase), lambda job: self._run_one(job, args), group=plan.id)
        except ValueError as exc:
            raise Conflict("This test is already waiting or running.") from exc

    def _address_check(self, import_id: int, address: str) -> AddressCheck | None:
        """Phase 1's gate, rebuilt from the address as it is NOW: this computer or confirmed, and the IP pinned."""
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            row = db.scalars(select(AddressRow).where(AddressRow.import_id == import_id, AddressRow.address == address)).first()
            if imp is None or row is None:
                return None
            demo = DemoContext(is_demo_import=imp.is_demo, host=DEMO_HOSTNAME, port=self.settings.demo_tls_port,
                               running=self.demo.running, error=self.demo.error, fingerprint=self.demo.fingerprint,
                               allow_external=self.allow_external_demo_server and self.demo.port_in_use)
            db.expunge(row)
        return AddressCheck(row, demo, resolver=self.resolver)

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
        component = (a["component_name"], a["component_version"]) if a["component_name"] else None
        code = self._code_for_run(a)  # which code this run is about to run on (None when no component of ours runs)
        if not spec_ok:
            raw = problem("spec_changed", "The stored test no longer matches the fingerprint it was locked with, so it was not run.")
        else:
            ctx = RunContext(settings=self.settings, mode=self.mode, runner=self.component_runner, gate=self.jobs.gate,
                             progress=job.progress, log=job.log,
                             address_check=lambda address: self._address_check(a["import_id"], address),
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
        job.run_id = run_id
        if a["phase"] == "proof":
            self._proof_run_finished(a["retest_id"])  # the proof itself is reviewed when its last run has been

    def wait_until_idle(self, plan_id: int, timeout: float = 300.0) -> None:
        if not self.jobs.wait_idle(timeout, group=plan_id):
            raise TimeoutError("The tests did not finish in time.")

    # ---------------------------------------------------------------- results (read gate)

    def _fix_version(self, name: str | None, version: str | None) -> str | None:
        versions = components.VERSIONS.get(name or "", [])
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
        key = (sha256_hex(record), sha256_hex({k: v for k, v in stored.items() if k != "created_at"}), spec_ok, spec_row.hash if spec_row else None,
               sha256_hex(code))
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
                                      code=code)
            self._result_cache[run.id] = (key, base, bool(trusted))
        result = dict(base)
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
            specs = self._specs(db, items)
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
            for item in items:
                spec, _, spec_row = specs[item.id]
                kind = spec_row.kind if spec_row else spec.get("kind")
                first_job = self.jobs.get((item.id, "first"))
                first_live = first_job is not None and first_job.status != "done"
                result = None if first_live else self._latest_result(db, item, "first", None, plan)
                row = {"item_id": item.id, "kind": kind, "title": present.TITLES.get(kind, str(kind)), "control_line": "",
                       "result": result, "result_status": None if result else self._row_status(item.id, "first"),
                       "after": None, "after_status": None}
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
            versions = components.VERSIONS.get(plan.component_name or "", [])
            demo_component = plan.component_version in versions
            if not demo_component:
                blocked = "A retest needs one of our demo signing components, and this file doesn't name one."
            else:
                blocked = BUSY[running] if busy else self._compare_blocked(plan_id, items, missing)
            menu = [{"version": v, "label": f"{plan.component_name} {v}", "tag": "demo",
                     "note": ("The demo version these results are for." if v == plan.component_version
                              else "The corrected demo version." if versions.index(v) > versions.index(plan.component_version)
                              else "An earlier demo version.")}
                    for v in sorted(versions, key=lambda v: (v == plan.component_version, -versions.index(v)))] if demo_component else []
            retest_view = {"can_start": blocked is None, "blocked_reason": blocked, "running": bool(retest_live),
                           "progress_text": (f"Retest running: {after_done} of {len(items)} tests finished." if retest_live else None),
                           "menu_title": "Choose the version to retest", "versions": menu,
                           "menu_note": (f"Choosing a version reruns the same {n_word} locked {'test' if len(items) == 1 else 'tests'} on it and shows before and after. "
                                         f"Only our {present.number_word(len(versions))} demo versions can be chosen here.")}
            any_result = len(items) > missing
            download = {"can_start": any_result and not busy,
                        "blocked_reason": None if any_result and not busy else
                        (BUSY[running] if busy else "Run a test first, so there is something to download.")}
            if retest is None:
                subline: list[dict] = [{"t": "text", "v": "Results by test for "}]
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
                before, after_name = f"{plan.component_name} {retest.baseline_version}", f"{plan.component_name} {retest.version}"
                subline = [{"t": "text", "v": f"Before and after: the same {n_word} locked {'test' if len(items) == 1 else 'tests'}, run on "},
                           {"t": "mono", "v": before}, {"t": "text", "v": " and then on "}, {"t": "mono", "v": after_name}]
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

    def start_retest(self, plan_id: int, version: str) -> dict:
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                versions = components.VERSIONS.get(plan.component_name or "", [])
                if plan.component_version not in versions:
                    raise Conflict("A retest needs one of our demo signing components, and this file doesn't name one.")
                if version not in versions:
                    raise BadRequest("Only our demo versions can be chosen for a retest.", field="version")
            view = self.lab_view(plan_id)
            if not view["retest"]["can_start"]:
                raise Conflict(view["retest"]["blocked_reason"] or "A retest can't start right now.")
            with self.db() as db:
                plan = self._plan(db, plan_id)
                retest = RetestRow(plan_id=plan_id, baseline_version=plan.component_version, version=version)
                db.add(retest)
                db.commit()
                for item in self._items(db, plan_id):
                    self._submit(plan, item, "retest", retest)
        return self.lab_view(plan_id)
