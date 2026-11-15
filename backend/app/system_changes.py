"""Try on a test copy, approve, Apply and Roll back (phase 4b), for the changes of the Migration step and for the Acme
Pay server's TLS fix (SPEC 7c). Mixed into Lab.

The rule: the app changes a system only when a person presses Apply, after a passing try on a test copy and every
approval the person asked for. It measures again right after, and Roll back is then always there. In this version
Apply works only on our own servers: the five demo test servers of the migration demo, the lab nginx of
demo/lab-nginx.csv (isolated mode) and the Acme Pay demo server. Any other server needs a connector (a later phase):
there Try and Apply are off and say so, and the change can be downloaded.

One path, as for tests: a try runs the system's own locked measurement (or its locked server protocol check) on a
copy this app starts with the change, and the separate reviewer reviews each run. Whether the try passed, whether the
measurement after Apply matches it, and whether Roll back put things back are fixed rules in reviewer.py, worked out
on every read from the reviewed runs, and never stored. What is stored, in tables that only accept new rows: each try
(with the change exactly as tried), each request for approval, each approval, each Apply and each Roll back."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select

from . import change_builder, lab_nginx, lab_servers, migration_rules as rules, research
from .changes import REVIEWERS
from .config import DEMO_HOSTNAME
from .db import (
    AddressRow, ApplyApprovalRow, ApplyRequestRow, ApplyRow, ChangeTryRow, ImportRow, PlanItemRow, PlanRow, RetestRow, ReviewRow,
    RollbackRow, TestRunRow, TestSpecRow, iso,
)
from .errors import BadRequest, Conflict, NotFound
from .reviewer import apply_outcome, change_try_outcome, meets_promise, rollback_outcome
from .testlab import MIGRATION_ORIGIN, read_spec

LAB_NGINX_SETTINGS = {"groups": "X25519:P-256", "versions": ["TLS 1.2", "TLS 1.3"], "certificate": "ecdsa-p256"}
DEMO_SERVER_SETTINGS = {"groups": "P-256", "versions": ["TLS 1.2", "TLS 1.3"], "certificate": "ecdsa-p256"}   # demo_server.DEMO_GROUP
TRY_PHASES = ("try", "try_nginx")
NO_CONNECTOR = ("Try on a test copy and Apply need a connector to this server, which comes in a later phase. Download the change "
                "and apply it yourself; then press Measure again.")
COPY_WORDS = {"demo_test_server": "a test copy with the change", "lab_nginx": "a copy of the lab nginx with the change",
              "demo_server": "a test copy with the change"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class SystemChangesMixin:
    """Mixed into Lab. Needs: db, jobs, mode, settings, demo, migration_servers, lab_nginx_server, and from the other
    mixins: _plan, _claims, _migration_states, _submit, _result, _result_cache, _latest_run, _run_one, _items."""

    # ---------------------------------------------------------------- settings in force on our own servers

    def _settings_history(self, db, address: str) -> tuple[ApplyRow | None, list]:
        """(the Apply in force on this address, every apply and roll back of it in time order)."""
        applies = db.scalars(select(ApplyRow).where(ApplyRow.address == address, ApplyRow.accepted.is_(True)).order_by(ApplyRow.id)).all()
        events, in_force = [], None
        for row in applies:
            back = db.scalars(select(RollbackRow).where(RollbackRow.apply_id == row.id)).first()
            events.append(("apply", row, row.applied_at))
            if back is not None and back.accepted:
                events.append(("rollback", back, back.rolled_back_at))
        events.sort(key=lambda e: e[2])
        for kind, row, _ in events:
            in_force = row if kind == "apply" else None
        return in_force, events

    def _settings_in_force(self, address: str) -> dict | None:
        """The settings an Apply put in force on one of our servers, or None (it runs as it started)."""
        with self.db() as db:
            in_force, events = self._settings_history(db, address)
            if in_force is not None:
                return dict(in_force.settings_after)
            return None

    # ---------------------------------------------------------------- where a change can be tried and applied

    def _target_of(self, db, imp: ImportRow, kind: str, address: str | None) -> tuple[str | None, dict | None, str | None, str | None]:
        """(target, the server's own settings before any Apply, words for the target, why there is none)."""
        if address is None:
            return None, None, None, "This is a signing program, not a server: there is no setting to apply here."
        port = int(address.rsplit(":", 1)[1]) if ":" in address else None
        host = address.rsplit(":", 1)[0]
        if host == DEMO_HOSTNAME and kind == "migration" and self._is_migration_demo(imp.id) and port in self.migration_servers.ports:
            if port not in self.migration_servers.running:
                return None, None, None, self.migration_servers.problems.get(port) or f"The demo test server for {address} is not running."
            return "demo_test_server", self.migration_servers.role_settings(port), f"our demo test server on {address}", None
        if host == DEMO_HOSTNAME and kind == "migration" and self._is_lab_nginx_file(imp.id) and port == self.settings.lab_nginx_port:
            usable, why = lab_nginx.ready(self.mode)
            if not usable:
                return None, None, None, why + " In demo mode, without Docker, the lab nginx can't run."
            if not self.lab_nginx_server.running:
                return None, None, None, "The lab nginx is not running. Import demo/lab-nginx.csv again to start it."
            return "lab_nginx", dict(LAB_NGINX_SETTINGS), f"the lab nginx on {address} ({lab_nginx.NGINX_VERSION_WORDS})", None
        if kind == "migration" and imp.is_demo and host == DEMO_HOSTNAME and port in tuple(self.settings.extra_ports):
            return None, None, None, ("This test server of the multi-target demo runs on Python's built-in TLS, which can't be set to "
                                      "post-quantum key exchange, so this change can't be tried or applied to it here. The test servers of "
                                      "the migration demo (demo/migration-demo.csv) can be.")
        if kind == "migration" and imp.is_demo and address == self.settings.demo_address:
            return None, None, None, ("This demo server runs on Python's built-in TLS, which can't be set to post-quantum key exchange, so "
                                      "this change can't be tried or applied to it here. The test servers of the migration demo "
                                      "(demo/migration-demo.csv) can be.")
        if kind == "tls" and imp.is_demo and address == self.settings.demo_address:
            if not self.demo.running:
                return None, None, None, (self.demo.error or "The demo server is not running.") + " Only the demo server this app runs can be changed."
            return "demo_server", dict(DEMO_SERVER_SETTINGS), f"the demo server on {address}", None
        return None, None, None, NO_CONNECTOR

    # ---------------------------------------------------------------- the current changes of a plan

    def _base_settings(self, db, address: str, initial: dict | None) -> dict | None:
        """What a change is built from: the settings before the Apply in force (so an applied change keeps its
        fingerprint), else the settings in force, else the server's own starting settings."""
        if initial is None:
            return None
        in_force, _ = self._settings_history(db, address)
        if in_force is not None:
            return dict(in_force.settings_before)
        return dict(initial)

    def _migration_changes(self, db, plan: PlanRow, states: list[dict]) -> list[dict]:
        imp = db.get(ImportRow, plan.import_id)
        out = []
        for state in states:
            option = state.get("plan_option")
            if not state["status"] or option is None:
                continue
            key = f"migration:{state['key']}"
            address = state["address"]
            if state["kind"] == "software":
                if option in ("hybrid", "full_pq") and not rules.in_place(state["status"], option):
                    change = change_builder.build(key=key, kind="migration", option="sign_both" if option == "hybrid" else "mldsa_only",
                                                  system_key=state["key"], address=None, name=state["name"], before=None, before_auth=None,
                                                  target=None, target_words=None,
                                                  no_target="This is a signing program: its change is to the program and its library.")
                    out.append(self._with_item(change, state))
                continue
            if option in ("keep", "wrap"):
                if state.get("plan_source") != "choice":
                    continue
                review = (state.get("review_date") or {}).get("value")
                seen = self._seen_settings(state)
                change = change_builder.build(key=key, kind="migration", option=option, system_key=state["key"], address=address,
                                              name=state["name"], before=None, before_auth=None, target=None, target_words=None,
                                              no_target="Nothing is applied for this option.",
                                              extra={"review_date": review,
                                                     "versions_words": lab_servers.versions_words(seen) if seen and seen["versions"] else None})
                out.append(self._with_item(change, state))
                continue
            target, initial, words, why = self._target_of(db, imp, "migration", address)
            in_force, _ = self._settings_history(db, address)
            applied_here = in_force is not None
            if rules.in_place(state["status"], option) and not applied_here and not self._ever_applied(db, key):
                continue
            before = self._base_settings(db, address, initial)
            seen_only = False
            if before is None and target is None:
                # a server this app can't read the settings of: build from what was measured, and say so
                before = self._seen_settings(state)
                seen_only = before is not None
            before_auth = ((state["detail"].get("auth") or {}).get("status") if state.get("detail") else None)
            if applied_here or self._ever_applied(db, key):
                before_auth = self._auth_before(db, key) or before_auth
            change = change_builder.build(key=key, kind="migration", option=option, system_key=state["key"], address=address,
                                          name=state["name"], before=before, before_auth=before_auth, target=target,
                                          target_words=words, no_target=why, extra={"seen_only": seen_only})
            out.append(self._with_item(change, state))
        return out

    @staticmethod
    def _seen_settings(state: dict) -> dict | None:
        """What a measurement saw of a server (not its settings): the TLS versions it accepted, the classical group it
        chose and its certificate key. None when it was not measured well enough to say."""
        detail = state.get("detail") or {}
        versions = [v for v in lab_servers.VERSION_ORDER if v in (detail.get("tls_versions") or [])]
        group = detail.get("classical_group")
        certificate = (detail.get("auth") or {}).get("certificate")
        if not versions or not group or not certificate:
            return None
        kinds = {words: kind for kind, words in lab_servers.CERTIFICATE_WORDS.items()}
        return lab_servers.normal({"groups": group, "versions": versions, "certificate": kinds.get(certificate, certificate)})

    @staticmethod
    def _with_item(change: dict, state: dict) -> dict:
        return {**change, "_item_id": state["item_id"], "_run_id": state.get("run_id"), "_plan_source": state.get("plan_source")}

    def _ever_applied(self, db, key: str) -> bool:
        return db.scalar(select(func.count(ApplyRow.id)).where(ApplyRow.change_key == key)) > 0

    def _auth_before(self, db, key: str) -> str | None:
        """The authentication status the first try of this change was compared with (kept with the change)."""
        row = db.scalars(select(ChangeTryRow).where(ChangeTryRow.change_key == key).order_by(ChangeTryRow.id)).first()
        return ((row.change or {}).get("promise") or {}).get("auth") if row else None

    def _tls_changes(self, db, plan: PlanRow) -> list[dict]:
        """The Acme Pay server's TLS fix (SPEC 7c): for a locked "Old TLS versions" test of the demo server whose claim is
        TLS 1.3 only and which failed (or whose fix was applied), the change that switches the older versions off."""
        imp = db.get(ImportRow, plan.import_id)
        if not imp.is_demo:
            return []
        out = []
        for item in self._items(db, plan.id):
            spec, ok = read_spec(db.get(TestSpecRow, item.spec_hash))
            if not ok or spec.get("kind") != "tls_versions" or (spec.get("target") or {}).get("address") != self.settings.demo_address:
                continue
            if list((spec.get("inputs") or {}).get("claimed") or []) != ["TLS 1.3"]:
                continue
            key = f"tls:server:{self.settings.demo_address}"
            failed = db.scalar(select(func.count(ReviewRow.id)).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                               .where(TestRunRow.plan_item_id == item.id, ReviewRow.code == "failed")) > 0
            if not failed and not self._ever_applied(db, key):
                continue
            target, initial, words, why = self._target_of(db, imp, "tls", self.settings.demo_address)
            before = self._base_settings(db, self.settings.demo_address, initial or dict(DEMO_SERVER_SETTINGS))
            change = change_builder.build(key=key, kind="tls", option="tls13", system_key="server:" + self.settings.demo_address,
                                          address=self.settings.demo_address, name=self.settings.demo_address, before=before,
                                          before_auth=None, target=target, target_words=words, no_target=why)
            latest = self._latest_run(db, item.id, "first", None)
            out.append({**change, "_item_id": item.id, "_run_id": latest.id if latest else None, "_plan_source": "fix"})
            break
        return out

    def _plan_changes(self, db, plan: PlanRow, states: list[dict] | None = None) -> list[dict]:
        states = self._migration_states(db, plan) if states is None else states
        return self._migration_changes(db, plan, states) + self._tls_changes(db, plan)

    def _change_by_key(self, db, plan: PlanRow, key: str) -> dict:
        change = next((c for c in self._plan_changes(db, plan) if c["key"] == key), None)
        if change is None:
            raise NotFound("There is no such change for this plan now. Measure again, or check the system's plan.")
        return change

    # ---------------------------------------------------------------- what has happened to a change

    def _measured(self, db, run: TestRunRow | None) -> dict | None:
        """One run as the read gate lets it through: {"code", "detail", "control", "result", "run_id", "finished_at"}."""
        if run is None:
            return None
        result = self._result(db, run)
        if result is None:
            return None
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run.id)).first()
        stands = self._result_cache[run.id][2] and result["code"] == review.code
        return {"code": result["code"], "detail": dict(review.detail or {}) if stands else {}, "control": review.control_outcome,
                "result": result, "run_id": run.id, "finished_at": run.finished_at, "raw": run.raw if stands else {}}

    def _first_after(self, db, item_id: int, phases: tuple[str, ...], after_run_id: int) -> TestRunRow | None:
        """The first reviewed run after an Apply or a Roll back of the same locked test (same fingerprint, so the same
        measurement of the same server), whichever import of the file ran it: a Roll back can be pressed from another
        import of the file than the Apply was (phase 4b)."""
        item = db.get(PlanItemRow, item_id)
        same = select(PlanItemRow.id).where(PlanItemRow.spec_hash == item.spec_hash) if item is not None else None
        where = TestRunRow.plan_item_id.in_(same) if same is not None else TestRunRow.plan_item_id == item_id
        return db.scalars(select(TestRunRow).join(ReviewRow, ReviewRow.run_id == TestRunRow.id)
                          .where(where, TestRunRow.phase.in_(phases), TestRunRow.id > after_run_id)
                          .order_by(TestRunRow.id).limit(1)).first()

    def _newest_in(self, db, item_id: int, phases: tuple[str, ...]) -> TestRunRow | None:
        return db.scalars(select(TestRunRow).join(ReviewRow, ReviewRow.run_id == TestRunRow.id)
                          .where(TestRunRow.plan_item_id == item_id, TestRunRow.phase.in_(phases))
                          .order_by(TestRunRow.id.desc()).limit(1)).first()

    @staticmethod
    def _remeasure_phases(change: dict) -> tuple[str, ...]:
        """Where the measurement after an Apply or a Roll back is kept. The TLS fix's server tests go in Evidence Lab's
        newest column: the first results, or the retest once there is one (so before and after keep reading in order)."""
        return ("first", "retest") if change["kind"] == "tls" else (MIGRATION_ORIGIN,)

    def _change_records(self, db, plan: PlanRow, change: dict) -> dict:
        key, fp, item_id = change["key"], change["fingerprint"], change["_item_id"]
        tries = db.scalars(select(ChangeTryRow).where(ChangeTryRow.plan_id == plan.id, ChangeTryRow.change_key == key,
                                                      ChangeTryRow.change_fp == fp).order_by(ChangeTryRow.id.desc())).all()
        latest = tries[0] if tries else None
        rec: dict = {"try": None, "try_outcome": None, "try_copies": [], "try_before": None, "request": None, "approvals": {},
                     "applies": [], "in_force": None, "apply": None, "apply_after": None, "apply_outcome": None, "rollback": None,
                     "rollback_after": None, "rollback_outcome": None, "busy": False, "latest": None, "in_place": None}
        live = {j.key for j in self.jobs.live(("changes", plan.id))} | {j.key for j in self.jobs.live(("migration", plan.id))} | \
               {j.key for j in self.jobs.live(plan.id)}
        rec["busy"] = any(k[0] == item_id for k in live)
        if latest is not None:
            rec["try"] = latest
            rec["try_before"] = self._measured(db, db.get(TestRunRow, latest.before_run_id)) if latest.before_run_id else None
            copies, running = [], False
            for copy in latest.copies:
                if copy.get("skipped"):
                    copies.append((copy["label"], None, copy["skipped"]))
                    rec["try_copies"].append({**copy, "measured": None})
                    continue
                run = self._latest_run(db, item_id, copy["phase"], latest.id)
                measured = self._measured(db, run)
                if measured is None:
                    running = True
                copies.append((copy["label"], measured, None))
                rec["try_copies"].append({**copy, "measured": measured})
            rec["try_outcome"] = {"code": "running"} if running else change_try_outcome(change["promise"], copies)
        req = db.scalars(select(ApplyRequestRow).where(ApplyRequestRow.plan_id == plan.id, ApplyRequestRow.change_key == key,
                                                       ApplyRequestRow.change_fp == fp).order_by(ApplyRequestRow.id.desc())).first()
        if req is not None:
            rec["request"] = req
            rec["approvals"] = {a.reviewer: a for a in db.scalars(select(ApplyApprovalRow).where(ApplyApprovalRow.request_id == req.id)).all()}
        if change.get("address"):
            in_force, events = self._settings_history(db, change["address"])
            rec["in_force"] = in_force
            rec["events"] = events
        rec["applies"] = db.scalars(select(ApplyRow).where(ApplyRow.change_key == key).order_by(ApplyRow.id.desc())).all()
        phases = self._remeasure_phases(change)
        if rec["applies"]:
            row = rec["applies"][0]
            rec["apply"] = row
            if row.accepted:
                tried = db.get(ChangeTryRow, row.try_id)
                tried_copy = next((c for c in rec_try_copies(self, db, tried, item_id)), None) if tried else None
                after = self._measured(db, self._first_after(db, item_id, phases, row.runs_before))
                rec["apply_after"] = after
                rec["apply_outcome"] = (apply_outcome(change["promise"], tried_copy, after) if after else {"code": "measuring"})
                back = db.scalars(select(RollbackRow).where(RollbackRow.apply_id == row.id)).first()
                if back is not None:
                    rec["rollback"] = back
                    if back.accepted:
                        before = self._measured(db, db.get(TestRunRow, tried.before_run_id)) if tried and tried.before_run_id else None
                        after_back = self._measured(db, self._first_after(db, item_id, phases, back.runs_before))
                        rec["rollback_after"] = after_back
                        rec["rollback_outcome"] = rollback_outcome(before, after_back) if after_back else {"code": "measuring"}
        rec["latest"] = self._measured(db, self._newest_in(db, item_id, phases))
        if change["promise"]:
            ok, _ = meets_promise(change["promise"], rec["latest"])
            rec["in_place"] = ok
        return rec

    # ---------------------------------------------------------------- the gates (one sentence each, when closed)

    def _change_gates(self, change: dict, rec: dict) -> dict:
        target, outcome = change.get("target"), (rec.get("try_outcome") or {}).get("code")
        triable = bool(change.get("settings_after"))
        gates = {"try": None, "ask": None, "approve": None, "apply": None, "rollback": None}
        if not triable:
            return {"try": "Nothing to try for this option.", "ask": "Nothing to approve for this option.",
                    "approve": "Nothing to approve for this option.", "apply": "Nothing is applied for this option.",
                    "rollback": "Nothing was applied."}
        if rec["busy"]:
            busy = "Wait: a try, an Apply, a measurement or a roll back of this system is running."
            gates.update({k: busy for k in gates})
            return gates
        if target is None:
            gates["try"] = change.get("no_target") or NO_CONNECTOR
            # a server that is not ours needs a connector; one of ours that can't take this change says why
            gates["apply"] = ("Apply needs a connector to this server, which comes in a later phase. Download the change and apply it yourself."
                              if change.get("no_target") in (None, NO_CONNECTOR) else change["no_target"])
        elif change.get("_run_id") is None:
            gates["try"] = "Measure this system first (Measure status), so there is something to compare the try with."
        in_force = rec.get("in_force")
        others_applied = in_force is not None and in_force.change_fp != change["fingerprint"]
        last_event = max([e[2] for e in rec.get("events") or []], default=None)
        stale_try = rec.get("try") is not None and last_event is not None and _aware(rec["try"].created_at) < _aware(last_event)
        if gates["apply"] is None:
            if stale_try and in_force is None:
                gates["apply"] = "The server changed since this try (an Apply or a Roll back). Try again on a test copy first."
            elif outcome != "passed":
                gates["apply"] = ("Apply unlocks after a try on a test copy has passed." if outcome in (None, "not_run")
                                  else "The latest try did not pass, so Apply stays off. Try again once the change is right.")
            elif rec["request"] is None:
                gates["apply"] = "Ask for approval first: Apply unlocks when every reviewer you pick has approved."
            elif any(r not in rec["approvals"] for r in rec["request"].reviewers):
                waiting = [REVIEWERS.get(r, r) for r in rec["request"].reviewers if r not in rec["approvals"]]
                gates["apply"] = f"Apply unlocks when every reviewer has approved: waiting for {' and '.join(waiting)}."
            elif others_applied:
                gates["apply"] = "Another change is applied to this server. Roll it back first."
            elif in_force is not None:
                gates["apply"] = "This change is applied. Roll back puts the earlier settings back."
        if outcome != "passed":
            gates["ask"] = "A try on a test copy must pass before approval can be asked for."
        elif rec["request"] is not None:
            gates["ask"] = "Approval has been asked for."
        gates["approve"] = None if rec["request"] is not None else "Ask for approval first."
        gates["rollback"] = None if in_force is not None else "Nothing applied to this server is in force."
        if target is None and in_force is not None:
            gates["rollback"] = change.get("no_target")
        return gates

    # ---------------------------------------------------------------- the person's actions

    def _locked(self, plan_id: int, key: str):
        with self.db() as db:
            plan = self._plan(db, plan_id)
            change = self._change_by_key(db, plan, key)
            rec = self._change_records(db, plan, change)
            return plan, change, rec, self._change_gates(change, rec)

    def try_change(self, plan_id: int, key: str) -> dict:
        """Try on a test copy: start a copy of the server with the change and run the system's own locked measurement on
        it; in isolated mode also on real nginx given the change's exact nginx lines. Nothing real changes."""
        with self._plan_lock:
            plan, change, rec, gates = self._locked(plan_id, key)
            if gates["try"]:
                raise Conflict(gates["try"])
            target, after = change["target"], change["settings_after"]
            copies = [{"label": COPY_WORDS[target], "phase": "try", "skipped": None}]
            if target in ("demo_test_server", "demo_server"):
                usable, why = lab_nginx.ready(self.mode)
                copies.append({"label": "real nginx (1.31.8, OpenSSL 3.5.9) with the same change", "phase": "try_nginx",
                               "skipped": None if usable else why})
            with self.db() as db:
                row = ChangeTryRow(plan_id=plan.id, change_key=key, change_fp=change["fingerprint"],
                                   change={k: v for k, v in change.items() if not k.startswith("_")}, item_id=change["_item_id"],
                                   before_run_id=change["_run_id"], copies=copies)
                db.add(row)
                db.commit()
                try_id = row.id
                item = db.get(PlanItemRow, change["_item_id"])
                db.expunge(item)
            for copy in copies:
                if copy["skipped"]:
                    continue
                starter = self._copy_starter(change, copy["phase"])
                self._submit_copy(plan, item, copy["phase"], try_id, copy["label"], starter)
        return {"ok": True}

    def _copy_starter(self, change: dict, phase: str):
        target, after = change["target"], change["settings_after"]
        if phase == "try_nginx" or target == "lab_nginx":
            return lambda: lab_nginx.nginx_copy(after)
        if target == "demo_server":
            return lambda: self._demo_copy(after)
        port = int(change["address"].rsplit(":", 1)[1])
        keep = self.migration_servers.certificate_of(port)
        return lambda: lab_servers.test_copy(after, keep if keep and lab_servers.keep_kind(keep) == after["certificate"] else None)

    @contextmanager
    def _demo_copy(self, settings: dict):
        """A test copy of the Acme Pay demo server: the same demo certificate, accepting only the new TLS versions."""
        from .demo_server import TlsServer
        server = TlsServer(self.demo.context_for(settings["versions"]), 0)
        try:
            yield {"port": server.port, "fingerprint": self.demo.fingerprint, "settings": settings, "accepted": "the copy started"}
        finally:
            server.close()

    def _submit_copy(self, plan: PlanRow, item: PlanItemRow, phase: str, try_id: int, label: str, starter) -> None:
        args = {"plan_id": plan.id, "import_id": plan.import_id, "item_id": item.id, "spec_hash": item.spec_hash, "phase": phase,
                "retest_id": try_id, "component_name": None, "component_version": None, "baseline_version": None, "own": False,
                "copy_label": label}

        def job_fn(job):
            job.progress("starting the copy", 5)
            try:
                with starter() as copy:
                    self._run_one(job, {**args, "copy": copy})
            except (lab_nginx.NginxUnavailable, OSError, Exception) as exc:   # the copy could not start: recorded, never a crash
                text = str(exc) if isinstance(exc, lab_nginx.NginxUnavailable) else f"the copy could not be started ({exc.__class__.__name__})"
                self._run_one(job, {**args, "copy_problem": text})
        try:
            self.jobs.submit((item.id, phase), job_fn, group=("changes", plan.id))
        except ValueError as exc:
            raise Conflict("A try of this system is already running.") from exc

    def ask_approval(self, plan_id: int, key: str, reviewers: list[str]) -> dict:
        if (not isinstance(reviewers, list) or not reviewers or len(set(reviewers)) != len(reviewers)
                or not all(isinstance(r, str) and r in REVIEWERS for r in reviewers)):
            raise BadRequest("Pick one or more reviewers from the list.", field="reviewers")
        with self._plan_lock:
            plan, change, rec, gates = self._locked(plan_id, key)
            if gates["ask"]:
                raise Conflict(gates["ask"])
            with self.db() as db:
                db.add(ApplyRequestRow(plan_id=plan.id, change_key=key, change_fp=change["fingerprint"],
                                       reviewers=[r for r in REVIEWERS if r in reviewers]))
                db.commit()
        return {"ok": True}

    def approve_change(self, plan_id: int, key: str, reviewer: str) -> dict:
        if not isinstance(reviewer, str) or reviewer not in REVIEWERS:
            raise BadRequest("That reviewer is not in the list.", field="reviewer")
        with self._plan_lock:
            plan, change, rec, gates = self._locked(plan_id, key)
            if gates["approve"]:
                raise Conflict(gates["approve"])
            if reviewer not in rec["request"].reviewers:
                raise BadRequest("That reviewer was not asked to approve this change.", field="reviewer")
            if reviewer not in rec["approvals"]:
                with self.db() as db:
                    db.add(ApplyApprovalRow(request_id=rec["request"].id, reviewer=reviewer, name=REVIEWERS[reviewer]))
                    db.commit()
        return {"ok": True}

    def _max_run_id(self) -> int:
        with self.db() as db:
            return db.scalar(select(func.max(TestRunRow.id))) or 0

    def _put_in_force(self, target: str, address: str, settings: dict, keep=None) -> tuple[bool, str]:
        port = int(address.rsplit(":", 1)[1])
        if target == "demo_test_server":
            return self.migration_servers.apply(port, settings, keep)
        if target == "lab_nginx":
            return self.lab_nginx_server.apply(settings, keep)
        return self.demo.set_versions(settings["versions"])

    def apply_change(self, plan_id: int, key: str) -> dict:
        """Apply, pressed by a person: put the tried and approved change in force on our own server, then measure again."""
        with self._plan_lock:
            plan, change, rec, gates = self._locked(plan_id, key)
            if gates["apply"]:
                raise Conflict(gates["apply"])
            address, target = change["address"], change["target"]
            with self.db() as db:
                before = dict(self._settings_in_force(address) or self._base_settings(db, address, change["settings_before"]) or {})
            runs_before = self._max_run_id()
            accepted, words = self._put_in_force(target, address, change["settings_after"])
            with self.db() as db:
                db.add(ApplyRow(plan_id=plan.id, change_key=key, change_fp=change["fingerprint"], address=address, target=target,
                                try_id=rec["try"].id, request_id=rec["request"].id, settings_before=before,
                                settings_after=change["settings_after"], accepted=bool(accepted), words=words[:500], runs_before=runs_before))
                db.commit()
            if accepted:
                self._remeasure(plan, change)
        return {"ok": True}

    def rollback_change(self, plan_id: int, key: str) -> dict:
        """Roll back, pressed by a person: put back the settings from before the Apply in force, then measure again."""
        with self._plan_lock:
            plan, change, rec, gates = self._locked(plan_id, key)
            if gates["rollback"]:
                raise Conflict(gates["rollback"])
            row = rec["in_force"]
            keep = None
            port = int(row.address.rsplit(":", 1)[1])
            if row.target == "demo_test_server":
                keep = self.migration_servers.previous_certificate(port)
            elif row.target == "lab_nginx":
                keep = self.lab_nginx_server.previous_certificate()
            runs_before = self._max_run_id()
            accepted, words = self._put_in_force(row.target, row.address, row.settings_before, keep)
            with self.db() as db:
                db.add(RollbackRow(apply_id=row.id, accepted=bool(accepted), words=words[:500], runs_before=runs_before))
                db.commit()
            if accepted:
                self._remeasure(plan, change)
        return {"ok": True}

    def _remeasure(self, plan: PlanRow, change: dict) -> None:
        """Measure again right after an Apply or a Roll back: the system's own measurement (Migration), or, for the Acme
        Pay server's TLS fix, its locked server tests (Old TLS versions, Certificate strength)."""
        with self.db() as db:
            items = []
            if change["kind"] == "tls":
                for item in self._items(db, plan.id):
                    spec, _ = read_spec(db.get(TestSpecRow, item.spec_hash))
                    if (spec.get("target") or {}).get("address") == change["address"] and spec.get("kind") in ("tls_versions", "certificate"):
                        db.expunge(item)
                        items.append(item)
            else:
                item = db.get(PlanItemRow, change["_item_id"])
                db.expunge(item)
                items.append(item)
        phase, rerun = MIGRATION_ORIGIN, None
        if change["kind"] == "tls":
            with self.db() as db:
                rerun = db.scalars(select(RetestRow).where(RetestRow.plan_id == plan.id).order_by(RetestRow.id.desc()).limit(1)).first()
                if rerun is not None:
                    db.expunge(rerun)
            phase = "retest" if rerun is not None else "first"
        for item in items:
            try:
                self._submit(plan, item, phase, rerun)
            except Conflict:
                pass   # already waiting or running: that run counts

    def wait_until_changes_idle(self, plan_id: int, timeout: float = 300.0) -> None:
        for group in (("changes", plan_id), ("migration", plan_id), plan_id):
            if not self.jobs.wait_idle(timeout, group=group):
                raise TimeoutError("The try, Apply or measurement did not finish in time.")

    def change_download(self, plan_id: int, key: str) -> tuple[str, bytes]:
        with self.db() as db:
            change = self._change_by_key(db, self._plan(db, plan_id), key)
        safe = "".join(ch if ch.isalnum() or ch in "-." else "-" for ch in change["name"])[:60]
        return f"evidence-lab-change-{safe}.txt", change_builder.download_text(change, _now()).encode("utf-8")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def change_history(lab, db, plan: PlanRow, current: list[dict] | None = None) -> dict[str, dict]:
    """Every round of every change acted on in this plan, straight from the records, for the evidence: every try (with
    its copies' runs and outcome), every approval request with its approvals, every Apply with the measurement right
    after it and its Roll back with the measurement after that. Changes that are no longer the plan's are in it too.
    {change key: {"change", "tries", "approval_requests", "applies"}}; the outcomes are the reviewer's."""
    out: dict[str, dict] = {}
    tries = db.scalars(select(ChangeTryRow).where(ChangeTryRow.plan_id == plan.id).order_by(ChangeTryRow.id)).all()
    by_id = {}
    for t in tries:
        h = out.setdefault(t.change_key, {"change": t.change, "tries": [], "approval_requests": [], "applies": []})
        h["change"] = t.change
        copies, shown = [], []
        for c in t.copies:
            if c.get("skipped"):
                copies.append((c["label"], None, c["skipped"]))
                shown.append({"label": c["label"], "phase": c["phase"], "skipped": c["skipped"], "measured": None})
                continue
            measured = lab._measured(db, lab._latest_run(db, t.item_id, c["phase"], t.id))
            copies.append((c["label"], measured, None))
            shown.append({"label": c["label"], "phase": c["phase"], "skipped": None, "measured": measured})
        running = any(c["measured"] is None and not c["skipped"] for c in shown)
        outcome = {"code": "running"} if running else change_try_outcome((t.change or {}).get("promise") or {}, copies)
        before = lab._measured(db, db.get(TestRunRow, t.before_run_id)) if t.before_run_id else None
        entry = {"row": t, "copies": shown, "outcome": outcome, "before": before}
        h["tries"].append(entry)
        by_id[t.id] = entry
    for change in current or []:
        if change["key"] not in out and db.scalar(select(func.count(ApplyRow.id)).where(ApplyRow.change_key == change["key"])):
            out[change["key"]] = {"change": {k: v for k, v in change.items() if not k.startswith("_")}, "tries": [],
                                  "approval_requests": [], "applies": []}
    for key, h in out.items():
        for req in db.scalars(select(ApplyRequestRow).where(ApplyRequestRow.plan_id == plan.id, ApplyRequestRow.change_key == key)
                              .order_by(ApplyRequestRow.id)).all():
            approvals = db.scalars(select(ApplyApprovalRow).where(ApplyApprovalRow.request_id == req.id).order_by(ApplyApprovalRow.id)).all()
            h["approval_requests"].append({"row": req, "approvals": approvals})
        phases = SystemChangesMixin._remeasure_phases(h["change"] or {"kind": "migration"})
        promise = (h["change"] or {}).get("promise") or {}
        # every Apply of this change, also one made from another import of the file (a Roll back can be pressed here)
        for row in db.scalars(select(ApplyRow).where(ApplyRow.change_key == key).order_by(ApplyRow.id)).all():
            tried = by_id.get(row.try_id)
            if tried is None:
                other = db.get(ChangeTryRow, row.try_id)
                tried = {"row": other, "copies": [{"label": c["label"], "phase": c["phase"], "skipped": c.get("skipped"),
                                                   "measured": None if c.get("skipped") else
                                                   lab._measured(db, lab._latest_run(db, other.item_id, c["phase"], other.id))}
                                                  for c in other.copies],
                         "before": lab._measured(db, db.get(TestRunRow, other.before_run_id)) if other.before_run_id else None}
            item_id = tried["row"].item_id
            tried_copy = next((c["measured"] for c in (tried or {}).get("copies", []) if c["measured"] is not None), None)
            after = lab._measured(db, lab._first_after(db, item_id, phases, row.runs_before)) if row.accepted and item_id else None
            back = db.scalars(select(RollbackRow).where(RollbackRow.apply_id == row.id)).first()
            after_back = (lab._measured(db, lab._first_after(db, item_id, phases, back.runs_before))
                          if back is not None and back.accepted and item_id else None)
            h["applies"].append({
                "row": row, "from_this_import": row.plan_id == plan.id, "after": after,
                "outcome": (apply_outcome(promise, tried_copy, after) if after else None) if row.accepted else None,
                "rollback": back, "after_rollback": after_back,
                "rollback_outcome": rollback_outcome((tried or {}).get("before"), after_back) if after_back else None})
    return out


def rec_try_copies(lab, db, tried: ChangeTryRow, item_id: int):
    """The reviewed measurements of a try's copies, first the test copy (the one the measurement after Apply is held to)."""
    for copy in tried.copies:
        if copy.get("skipped"):
            continue
        measured = lab._measured(db, lab._latest_run(db, item_id, copy["phase"], tried.id))
        if measured is not None:
            yield measured


__all__ = ["SystemChangesMixin", "LAB_NGINX_SETTINGS", "NO_CONNECTOR", "change_history"]
