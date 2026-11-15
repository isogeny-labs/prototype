"""The Migration step (phase 4a), put together: measure where each system stands, keep the user's settings and
choices, and hand everything to the words (present_migration.py).

One path, the same as for tests: a measurement is a locked test (kinds "pq_status" and "signing_status") kept as a
hidden plan item, run through the job runner, written to a run record and reviewed by the separate reviewer. A
status is only ever read from that review, through the same read gate as every result. The recommendation, the
blockers and the roadmap come from the fixed rules in migration_rules.py, worked out again on every read, so they
follow a new measurement, setting or choice at once and are never stored.

What IS stored, and only ever added to: the settings the file or the user gave (system_settings) and the user's
own choices (migration_choices). Nothing the app works out is written to either. Since phase 4b the app changes a
system only when a person presses Apply, after a passing try on a test copy and every approval asked for, and only on
our own servers (system_changes.py); it measures again right after, and can roll back."""
from __future__ import annotations

import hashlib
import ipaddress
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.migration import rules
from app.present import results as present
from app.present import changes as present_changes
from app.present import migration as present_migration
from app.present import tracks as present_tracks
from app.engine import research
from app.canonical import canonical_bytes
from app.db import (
    AddressRow, ImportRow, MigrationChoiceRow, PlanItemRow, PlanRow, ReviewRow, SystemSettingRow, VerifyRunRow, iso,
)
from app.errors import BadRequest, Conflict, NotFound
from app.names import clean_text
from app.lab.testlab import MIGRATION_ORIGIN

STATUSES = ("classical", "hybrid", "pq_only")
REASON_LIMIT = 500


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _fix_id(item_id: int, what: str) -> str:
    return f"migration-{item_id}-{what.replace('_', '-')}"


class MigrationMixin:
    """Mixed into Lab. Needs: db, jobs, engine, and from TestLabMixin: _plan, _claims, _lock_spec, _submit, _latest_run,
    _result, _result_cache, _plan_lock, ensure_plan, lab_view."""

    # ---------------------------------------------------------------- the systems and their measurements

    @staticmethod
    def _systems(claims: list[dict]) -> list[dict]:
        """Every system the file names, servers first, in file order."""
        out = [{"key": "server:" + a, "kind": "server", "name": a, "target": a, "measure": "pq_status"} for a in research.servers(claims)]
        out += [{"key": "software:" + p["ref"], "kind": "software", "name": p["label"], "target": p["ref"], "measure": "signing_status",
                 "program": p} for p in research.programs(claims) if p.get("role") != "key_exchange"]   # (a key exchange program has no track yet)
        return out

    def _measurement_hash(self, claims: list[dict], system: dict) -> tuple[dict, str]:
        spec = self.engine.design_measurement({"kind": system["measure"], "claims": claims, "target": system["target"]})
        return spec, hashlib.sha256(canonical_bytes(spec)).hexdigest()

    def _ensure_migration_items(self, db, plan: PlanRow) -> list[PlanItemRow]:
        """Write down and lock each system's measurement, once. They are plan items the Tests step never shows."""
        claims = self._claims(db.get(ImportRow, plan.import_id))
        have = {r.spec_hash: r for r in db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan.id,
                                                                           PlanItemRow.origin == MIGRATION_ORIGIN)).all()}
        items = []
        for n, system in enumerate(self._systems(claims)):
            spec, key = self._measurement_hash(claims, system)
            if key not in have:
                have[key] = PlanItemRow(plan_id=plan.id, spec_hash=self._lock_spec(db, spec), position=10_000 + n,
                                        origin=MIGRATION_ORIGIN, removed=False)
                db.add(have[key])
            items.append(have[key])
        db.commit()
        return items

    # ---------------------------------------------------------------- everything about each system, worked out now

    def _migration_states(self, db, plan: PlanRow) -> list[dict]:
        imp = db.get(ImportRow, plan.import_id)
        claims = self._claims(imp)
        items = {r.spec_hash: r for r in db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan.id,
                                                                            PlanItemRow.origin == MIGRATION_ORIGIN)).all()}
        addresses = {a.address: a for a in db.scalars(select(AddressRow).where(AddressRow.import_id == imp.id)).all()}
        given: dict[tuple[str, str], SystemSettingRow] = {}
        for row in db.scalars(select(SystemSettingRow).where(SystemSettingRow.import_id == imp.id).order_by(SystemSettingRow.id)).all():
            given[(row.system_key, row.field)] = row   # the newest row of a field is the one in force
        verify = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == imp.id).order_by(VerifyRunRow.id.desc()).limit(1)).first()
        verified = {r.get("claim_id"): r.get("result") for r in (verify.results or []) if isinstance(r, dict)} if verify else {}
        today = _today()
        states = []
        for system in self._systems(claims):
            _, key = self._measurement_hash(claims, system)
            item = items.get(key)
            if item is None:
                continue   # not written down yet (the step has not been opened)
            kind = system["kind"]
            state: dict = {"key": system["key"], "kind": kind, "name": system["name"], "item_id": item.id,
                           "address": system["target"] if kind == "server" else None, "program": system.get("program"),
                           "job": None, "result": None, "run_id": None, "measured_at": None, "code": None, "reason_code": None,
                           "reason": None, "detail": {}, "raw": {}, "status": None}
            job = self.jobs.get((item.id, MIGRATION_ORIGIN))
            if job is not None and job.status != "done":
                state["job"] = present.status_view(job.status, job.progress_text, job.progress_percent, self.jobs.max_parallel)
            # The last reviewed measurement stands while a new one runs (phase 4b: so a system's change, and its entry in
            # Fixes, stays on screen during the measurement right after an Apply or a Roll back).
            run = self._latest_run(db, item.id, MIGRATION_ORIGIN, None)
            result = self._result(db, run) if run is not None else None
            if result is not None:
                review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
                stands = self._result_cache[run.id][2] and result["code"] == review.code   # the read gate
                state.update(result=result, run_id=run.id, measured_at=run.finished_at, code=result["code"],
                             reason_code=review.reason_code if stands else None, reason=review.reason if stands else None,
                             detail=dict(review.detail or {}) if stands else {}, raw=run.raw if stands and isinstance(run.raw, dict) else {})
                state["status"] = result["code"] if stands and result["code"] in STATUSES else None
            # the three settings: what the user set, else what the file gave, else the default ("assumed")
            row = addresses.get(system["target"]) if kind == "server" else None
            defaults = rules.default_settings(kind, self._public_address(row))
            state["settings"] = {}
            for field in rules.FIELDS:
                stored = given.get((system["key"], field))
                ok = stored is not None and stored.value in rules.FIELDS[field]
                state["settings"][field] = {"value": stored.value if ok else defaults[field], "source": stored.source if ok else "assumed"}
            values = {f: s["value"] for f, s in state["settings"].items()}
            # what the file says about it, and what Verify made of that claim
            wanted = "post_quantum" if kind == "server" else "signature_algorithm"
            claim = next((c for c in imp.claims if c.kind == wanted and
                          (c.location == system["target"] if kind == "server" else c.ref == system["target"])), None)
            state["claim"] = {"claimed": claim.claimed_value, "verify": verified.get(claim.id)} if claim is not None else None
            # the fixed rules
            status = state["status"]
            detail = state["detail"]
            facts = ({"tls13": detail.get("tls13"), "weak_certificate": bool((detail.get("certificate") or {}).get("weak"))} if kind == "server"
                     else {"post_quantum_signatures": status == "pq_only" or detail.get("can_make_pq") is True})   # phase 4c: measured on a real library
            state["offered"] = rules.offered(kind, status)
            state["recommendation"] = rules.recommend(kind, status, values)
            state["blockers"] = {o: rules.blockers(kind, o, facts) for o in rules.OPTIONS}
            measured_on = self._date_of(state["measured_at"]) or today
            state["default_review_date"] = rules.default_review_date(measured_on).isoformat() if status else None
            # the user's own choices: the newest one in force, the older ones kept
            chosen = [{"option": c.option, "reason": c.reason, "review_date": c.review_date, "at": iso(c.created_at)}
                      for c in db.scalars(select(MigrationChoiceRow).where(MigrationChoiceRow.plan_id == plan.id,
                                                                          MigrationChoiceRow.system_key == system["key"])
                                          .order_by(MigrationChoiceRow.id.desc())).all()]
            state["choice"], state["history"] = (chosen[0], chosen[1:]) if chosen else (None, [])
            applies = bool(state["choice"]) and state["choice"]["option"] in state["offered"]
            state["choice_applies"] = applies
            rec = state["recommendation"]
            state["plan_option"] = state["choice"]["option"] if applies else rec["option"] if rec else None
            state["plan_source"] = "choice" if applies else "recommendation" if rec else None
            option = state["plan_option"]
            state["band"] = rules.band(kind, status, option, values, state["blockers"].get(option, []) if option else [])
            state["review_date"] = None
            if option == "keep":
                mine = state["choice"]["review_date"] if applies and state["choice"].get("review_date") else None
                state["review_date"] = {"value": mine or state["default_review_date"], "source": "chosen" if mine else "assumed"}
            # Phase 4b: two tracks (key exchange and authentication for a server, signatures for a program), each placed on
            # the roadmap by itself. The Fixes entries (the change, and a weak certificate) are added by _with_changes.
            state["tracks"] = present_tracks.tracks_of(state)
            state["track_bands"] = present_tracks.track_bands(state)
            state["fix_ids"] = {}
            if status and option in ("hybrid", "full_pq") and "weak_certificate" in state["blockers"][option]:
                state["fix_ids"]["weak_certificate"] = _fix_id(item.id, "weak_certificate")
            state["change"], state["change_view"] = None, None
            states.append(state)
        return states

    def _with_changes(self, db, plan: PlanRow, states: list[dict]) -> list[dict]:
        """Attach each system's change (phase 4b): what it is, what happened to it, and its box for the screens."""
        by_key = {c["system_key"]: c for c in self._migration_changes(db, plan, states)}
        for state in states:
            change = by_key.get(state["key"])
            if change is None:
                continue
            rec = self._change_records(db, plan, change)
            gates = self._change_gates(change, rec)
            state["change"], state["change_rec"] = change, rec
            state["change_view"] = present_changes.change_view(change, rec, gates)
            state["fix_ids"]["howto"] = f"change-{state['item_id']}"
            if state["kind"] == "software":
                state["fix_ids"]["no_pq_signature"] = f"change-{state['item_id']}"
        return states

    @staticmethod
    def _public_address(row: AddressRow | None) -> bool:
        """Is this server's address one on the public internet (as far as the address itself says)?"""
        if row is None:
            return False
        try:
            return ipaddress.ip_address(row.resolved_ip or row.host).is_global
        except ValueError:
            return row.host != "localhost"   # a name that has not been looked up yet: not this computer

    @staticmethod
    def _date_of(stamp: str | None) -> date | None:
        try:
            return date.fromisoformat(str(stamp)[:10])
        except (TypeError, ValueError):
            return None

    # ---------------------------------------------------------------- the screen

    def migration_view_for_import(self, import_id: int) -> dict:
        return self.migration_view(self.ensure_plan(import_id)["id"])

    def migration_view(self, plan_id: int) -> dict:
        with self._plan_lock, self.db() as db:
            self._ensure_migration_items(db, self._plan(db, plan_id))
        lab = self.lab_view(plan_id)   # for the download button: the same rule as Evidence Lab's
        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            busy = self.jobs.busy(("migration", plan_id)) or self.jobs.busy(("changes", plan_id))   # asked first: the screen asks again
            states = self._with_changes(db, plan, self._migration_states(db, plan))
            measured = [s["measured_at"] for s in states if s["measured_at"]]
            return present_migration.view(
                plan_id=plan.id, import_id=imp.id, is_demo=bool(imp.is_demo), filename=imp.filename, states=states,
                busy=busy or self.jobs.busy(("migration", plan_id)), finished=sum(1 for s in states if s["job"] is None),
                measured_at=max(measured) if measured else None, today=_today(),
                download={"can_start": lab["download"]["can_start"] and not busy, "blocked_reason": lab["download"]["blocked_reason"]
                          if not lab["download"]["can_start"] else ("A measurement is running." if busy else None)})

    def wait_until_measured(self, plan_id: int, timeout: float = 300.0) -> None:
        if not self.jobs.wait_idle(timeout, group=("migration", plan_id)):
            raise TimeoutError("The measurement did not finish in time.")

    # ---------------------------------------------------------------- the user's actions

    def measure_migration(self, plan_id: int) -> dict:
        """Measure every system in the file again. Handshakes only, and only where the address gate lets them."""
        with self._plan_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                items = self._ensure_migration_items(db, plan)
                if not items:
                    raise Conflict("The file names nothing that can be measured.")
                if self.jobs.busy(("migration", plan_id)):
                    raise Conflict("A measurement is already running. Wait until it has finished.")
                for item in items:
                    self._submit(plan, item, MIGRATION_ORIGIN, None)
        return self.migration_view(plan_id)

    def _system_state(self, db, plan: PlanRow, system_key: str) -> dict:
        state = next((s for s in self._migration_states(db, plan) if s["key"] == system_key), None)
        if state is None:
            raise NotFound("That system is not in this file.")
        return state

    def set_migration_setting(self, plan_id: int, system_key: str, field: str, value: str) -> dict:
        if field not in rules.FIELDS:
            raise BadRequest("That setting is not known.", field="field")
        if value not in rules.FIELDS[field]:
            raise BadRequest("That is not a value for this setting.", field="value")
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            self._ensure_migration_items(db, plan)
            self._system_state(db, plan, system_key)
            db.add(SystemSettingRow(import_id=plan.import_id, system_key=system_key, field=field, value=value, source="user"))
            db.commit()
        return self.migration_view(plan_id)

    def choose_migration_option(self, plan_id: int, system_key: str, option: str, reason: str, review_date: str | None) -> dict:
        """Record the user's own choice for one system, with why and when. A new row every time: nothing is overwritten."""
        if option not in rules.OPTIONS:
            raise BadRequest("That option is not known.", field="option")
        with self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            self._ensure_migration_items(db, plan)
            state = self._system_state(db, plan, system_key)
            if state["job"] is not None:
                raise Conflict("This system is being measured. Choose when the measurement has finished.")
            if not state["status"]:
                raise Conflict("This system's status has not been measured, so there is nothing to choose between yet.")
            if option not in state["offered"]:
                raise BadRequest("That option doesn't apply to this system.", field="option")
            why = clean_text(reason or "", REASON_LIMIT)
            rec = state["recommendation"]
            if not why and (rec is None or rec["option"] != option):
                raise BadRequest("Say why, because this differs from the recommendation.", field="reason")
            kept = None
            if option == "keep":
                problem = rules.review_date_problem(review_date, _today())
                if problem:
                    latest = present_migration.day(rules.LATEST_REVIEW)
                    raise BadRequest({"missing": "Give a review date. Keeping classical always has one, never “forever”.",
                                      "past": "The review date must be after today.",
                                      "too_late": f"The review date can't be later than {latest}, NIST's date."}[problem], field="review_date")
                kept = date.fromisoformat(str(review_date)).isoformat()
            db.add(MigrationChoiceRow(plan_id=plan.id, system_key=system_key, option=option, reason=why, review_date=kept,
                                      basis={"status": state["status"], "run_id": state["run_id"],
                                             "recommended": rec["option"] if rec else None, "rule": rec["rule"] if rec else None,
                                             "settings": {f: dict(s) for f, s in state["settings"].items()}}))
            db.commit()
        return self.migration_view(plan_id)

    # ---------------------------------------------------------------- into Fixes and the evidence download

    def _fixes_for_migration(self, db, plan: PlanRow, items: list, shown: list[dict]) -> list[dict]:
        """The Fixes step's entries from the migration plan as it stands now (phase 4b): each system's change (with its
        try, approvals, Apply and Roll back where it can be applied here), and a weak certificate that must be replaced
        first. A change stays listed once it was applied, with Roll back; it reads "In place (measured)" only when a new
        measurement shows it in place."""
        fixes = []
        for state in self._with_changes(db, plan, self._migration_states(db, plan)):
            entries = dict(state["fix_ids"])
            entries.pop("no_pq_signature", None)            # the program's change is that entry
            for what, fix_id in entries.items():
                fixes.append({"id": fix_id, "test_kind": "pq_status" if state["kind"] == "server" else "signing_status", "kind": "text",
                              "status": "text_only", "source_kind": "migration",
                              "answers": [{"item_id": state["item_id"], "kind": "pq_status" if state["kind"] == "server" else "signing_status",
                                           "run_id": state["run_id"], "phase": MIGRATION_ORIGIN}],
                              "component": None, "template_id": None, "rerun_blocked": None, "connection": None, "change": None,
                              "proofs": 0, "proof": None, "pull_request": None, "merge": None, "actions": {},
                              "migration": {"system": state["key"], "what": what, "option": state["plan_option"]}})
        return fixes

    def _migration_fix_view(self, db, plan: PlanRow, fix: dict, is_demo: bool) -> dict:
        state = next((s for s in self._with_changes(db, plan, self._migration_states(db, plan)) if s["key"] == fix["migration"]["system"]), None)
        if state is None:
            raise NotFound("That system is not in this file.")
        if fix["migration"]["what"] == "howto":
            return present_migration.change_fix_view(fix, state, is_demo)
        return present_migration.fix_view(fix, state, is_demo)

    def _has_migration(self, db, plan_id: int) -> bool:
        return any(s["code"] is not None for s in self._migration_states(db, self._plan(db, plan_id)))

    def _migration_export(self, db, plan: PlanRow) -> tuple[dict | None, list[dict]]:
        """(the plan in words, each system's state) for the evidence download; (None, []) when nothing was measured."""
        states = self._migration_states(db, plan)
        if not any(s["code"] is not None for s in states):
            return None, []
        return present_migration.export(states), states


__all__ = ["MigrationMixin", "STATUSES"]
