"""Otto in an installation of Evidence Lab (phase 5c): test packs, the Advisories page, the Live Otto setting, and
the entries each loop run leaves in the assessment's Otto ledger. (Otto's proposals, and a person's decisions on
them, are in `proposals.py`.)

Mixed into Lab. Rules kept here:
  - A pack is data. A person installs it (in order, never removed). Otto proposes its checks for an assessment, and a
    person accepts or rejects each one. Nothing is added or run by itself.
  - An advisory check is an ordinary locked test of the plan. The existing runner runs it and the existing reviewer
    decides it; this module only repeats the reviewer's words.
  - The lock entry is written to the assessment's Otto ledger before the check can run, and every reviewed run adds an
    entry. The ledger holds no result and its verdict is never shown as one.
  - When the pinned Otto is not installed, advisory checks can't be added or run, because their runs could not be
    recorded. Everything else works as before.
  - A closed assessment keeps showing the packs that were installed when it was signed off.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import func, select

from app.canonical import canonical_bytes, sha256_hex
from app.db import (
    AppSettingRow, AssessmentRow, ImportRow, OttoCheckRow, OttoDecisionRow, OttoPackRow, OttoStepRow, PlanItemRow, PlanRow, RetestRow,
    ReviewRow, RunCodeRow, TestRunRow, TestSpecRow, iso,
)
from app.engine import research
from app.errors import BadRequest, Conflict
from app.evidence.export import review_part
from app.lab.testlab import read_spec, review_dict, run_record
from app.otto import assurance, checks, harness, model, packs
from app.otto import proposals as otto_proposals
from app.present import otto as present_otto
from app.run import components

LIVE_KEY, LIMIT_KEY = "otto_live", "otto_limit_nano"
NAME_KEY, NAME_MAX = "decision_name", 60        # phase 6a: the name a person typed once, for the decisions they record
# The tests a fix is held to besides its own advisory check: the ones that say pass or fail. Speed is left out, as it is
# in the trial on public copies (timings hold only for the computer they are measured on).
PASS_OR_FAIL_KINDS = ("official_vectors", "bad_signatures", research.ADVISORY_KIND)
MAX_LIMIT_NANO = 1000 * model.NANO


class OttoMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    jobs: Any
    settings: Any
    _plan: Callable[..., PlanRow]
    _plan_lock: Any
    _claims: Callable[..., list[dict]]
    _items: Callable[..., list]
    _lock_spec: Callable[..., str]
    _latest_run: Callable[..., Any]
    _result: Callable[..., dict | None]
    lab_view: Callable[[int], dict]
    fixes_view: Callable[[int], dict]
    assessment_for: Callable[..., AssessmentRow | None]

    def _init_otto(self) -> None:
        self._otto_lock = threading.Lock()                 # one pack install, one decision on a proposal at a time
        self._otto_pack_cache: dict[str, packs.Pack] = {}  # installed packs as read, by fingerprint

    # ---------------------------------------------------------------- installed packs

    def _trusted_pack_keys(self) -> dict[str, tuple[str, bool]]:
        return packs.trusted_keys(self.settings.data_dir)

    def _pack_rows(self, db, upto: datetime | None = None) -> list[OttoPackRow]:
        rows = db.scalars(select(OttoPackRow).order_by(OttoPackRow.id)).all()
        return [r for r in rows if upto is None or _aware(r.installed_at) <= _aware(upto)]

    def _installed_packs(self, db, upto: datetime | None = None) -> list[tuple[OttoPackRow, packs.Pack]]:
        """Every installed pack, oldest first, read back from its stored file (checked again when first read)."""
        out = []
        for row in self._pack_rows(db, upto):
            pack = self._otto_pack_cache.get(row.fingerprint)
            if pack is None:
                try:
                    pack = packs.read_envelope(row.envelope.encode("utf-8"), {row.public_key: (row.signer, bool(row.made_here))})
                except packs.PackError:
                    continue      # a stored pack that no longer reads is left out, never half-used
                self._otto_pack_cache[row.fingerprint] = pack
            out.append((row, pack))
        return out

    def _unreadable_packs(self, db) -> list[str]:
        """The versions of installed packs whose stored file this version of the app can't read (a pack made by an
        earlier build, in a form that has changed since). They are left out everywhere, and Settings says so."""
        readable = {row.id for row, _ in self._installed_packs(db)}
        return [row.version for row in self._pack_rows(db) if row.id not in readable]

    def _pack_advisories(self, db, upto: datetime | None = None) -> list[tuple[packs.Pack, dict]]:
        """Every advisory of the installed packs, in pack order (a later pack's entry for the same id replaces an earlier one)."""
        seen: dict[str, tuple[packs.Pack, dict]] = {}
        for _, pack in self._installed_packs(db, upto):
            for advisory in pack.pack["advisories"]:
                seen[advisory["id"]] = (pack, advisory)
        return list(seen.values())

    def _scan_updates(self, db) -> tuple[packs.Pack | None, list[dict], str]:
        """Look in the updates folders on this computer: (the pack that can be installed next, the files that were
        refused, one plain line). Nothing is downloaded."""
        keys = self._trusted_pack_keys()
        found, refused = [], []
        for folder in (self.settings.otto_updates, self.settings.otto_local_updates):
            good, bad = packs.found_in(folder, keys)
            found += good
            refused += bad
        found.sort(key=lambda p: packs.version_key(p.version))
        rows = self._pack_rows(db)
        installed = {r.fingerprint for r in rows}
        newest = {"version": rows[-1].version, "fingerprint": rows[-1].fingerprint} if rows else None
        newer = [p for p in found if p.fingerprint not in installed and (newest is None or packs.version_key(p.version) > packs.version_key(newest["version"]))]
        if not newer:
            return None, refused, ("No newer test pack in the updates folder." if found or rows else "No test pack in the updates folder.")
        for pack in newer:
            if packs.follows(pack, newest) is None:
                more = len(newer) - 1
                return pack, refused, (f"Test pack {pack.version} is ready to install." +
                                       (f" {more} more {'pack follows' if more == 1 else 'packs follow'} it; packs install in order." if more else ""))
        return None, refused + [{"file": f"{newer[0].version}.json", "reason": packs.follows(newer[0], newest)}], \
            "A newer pack is in the updates folder, but it does not follow the installed one."

    def otto_view(self, scan: bool = False) -> dict:
        """Settings: the Test packs section, the two status lines, and the Live Otto section."""
        with self.db() as db:
            installed = self._installed_packs(db)
            update, refused, line = self._scan_updates(db) if scan else (None, [], None)
            live_on, limit = self._otto_live_on(db), self._otto_limit(db)
            answers = self._answers_line(db, installed)
            unreadable = self._unreadable_packs(db)
        return present_otto.settings_view(installed=[(iso(row.installed_at), pack) for row, pack in installed], update=update, refused=refused,
                                          unreadable=unreadable,
                                          scan_line=line, harness_status=harness.public_status(), live_on=live_on, limit_nano=limit,
                                          key_present=model.key_present(), answers_line=answers, name=self._typed_name())

    def check_pack_updates(self) -> dict:
        return self.otto_view(scan=True)

    def install_pack(self, version: str) -> dict:
        """Install update: the next pack in order, read and checked again at this moment. Packs are never removed."""
        with self._otto_lock, self.db() as db:
            update, _, line = self._scan_updates(db)
            if update is None or update.version != str(version):
                raise Conflict(f"Test pack {str(version)[:20]} can't be installed now. {line}")
            db.add(OttoPackRow(version=update.version, fingerprint=update.fingerprint, public_key=update.public_key, signer=update.signer,
                               made_here=update.made_here, built_at=update.pack["built_at"],
                               envelope=canonical_bytes(update.envelope).decode("utf-8")))
            db.commit()
        return self.otto_view(scan=True)

    # ---------------------------------------------------------------- who decides: a name typed once (phase 6a)

    def _typed_name(self) -> str | None:
        with self.db() as db:
            row = db.get(AppSettingRow, NAME_KEY)
        return row.value if row is not None and row.value else None

    def decision_name(self) -> str:
        """The name a decision on one of Otto's proposals is recorded under: the one a person typed (asked once, kept
        in Settings), or "You" until then. The app has one login and does not check who is at the keyboard."""
        return self._typed_name() or otto_proposals.BY

    def decision_name_view(self) -> dict:
        """For the Otto panel's Confirm step: the name decisions are recorded under now, and whether one was typed."""
        typed = self._typed_name()
        return present_otto.name_view(typed)

    def set_decision_name(self, name: object) -> dict:
        """Keep the name a person typed for their decisions (Settings, or the panel's first Confirm). An empty name
        goes back to "You". It changes no decision already recorded: each keeps the name it was made under."""
        if not isinstance(name, str):
            raise BadRequest("Type a name.", field="name")
        text = " ".join("".join(ch if ch.isprintable() else " " for ch in name).split())
        if len(text) > NAME_MAX:
            raise BadRequest(f"Keep the name to {NAME_MAX} characters or fewer.", field="name")
        with self.db() as db:
            _set(db, NAME_KEY, text)
            db.commit()
        return self.otto_view()

    # ---------------------------------------------------------------- Live Otto: the switch and the spending limit

    @staticmethod
    def _otto_live_on(db) -> bool:
        row = db.get(AppSettingRow, LIVE_KEY)
        return row is not None and row.value == "on"

    def otto_limit_words(self) -> str:
        """The spending limit per run, as Settings shows it ("2.00"). A read: nothing is written and Claude is not asked."""
        with self.db() as db:
            return f"{self._otto_limit(db) / model.NANO:.2f}"

    @staticmethod
    def _otto_limit(db) -> int:
        row = db.get(AppSettingRow, LIMIT_KEY)
        try:
            value = int(row.value) if row is not None else model.DEFAULT_LIMIT_NANO
        except ValueError:
            value = model.DEFAULT_LIMIT_NANO
        return value if 0 < value <= MAX_LIMIT_NANO else model.DEFAULT_LIMIT_NANO

    def set_live_otto(self, on: bool | None = None, limit: str | None = None) -> dict:
        """Turn Use live Claude on or off, and/or save the spending limit per run (US dollars). The switch can be
        turned on only when an API key is present on this computer; the key itself is never read here."""
        with self.db() as db:
            if limit is not None:
                nano = _dollars(limit)
                _set(db, LIMIT_KEY, str(nano))
            if on is not None:
                if on and not model.key_present():
                    raise Conflict(f"Live Otto needs an API key on this computer, and none is set ({model.KEY_ENV}). "
                                   "The answers recorded during the build go on being used.")
                _set(db, LIVE_KEY, "on" if on else "off")
            db.commit()
        return self.otto_view()

    def otto_model(self, live: bool = True) -> model.OttoModel:
        """Otto's Claude client for one run in the app (one fix request): recorded answers, and live calls only when
        this call allows them, the switch is on and a key is present. Each run has its own spending limit."""
        with self.db() as db:
            on, limit = self._otto_live_on(db), self._otto_limit(db)
        return model.OttoModel(recorded_dirs=(self.settings.otto_recorded,), live=bool(live and on), budget=model.Budget(limit_nano=limit))

    def otto_live_ready(self) -> bool:
        with self.db() as db:
            return self._otto_live_on(db) and model.key_present()

    def _answers_line(self, db, installed: list) -> str:
        """Settings: where an answer Otto needs from now on comes from."""
        if self._otto_live_on(db) and model.key_present():
            return "Live: Claude, through your key"
        notes = [pack.pack["research"]["answers_note"] for _, pack in installed]
        if notes:
            return notes[-1]
        # no pack yet: the answers Otto would use are the recorded ones on this computer, which say when they were made
        since = model.recorded_since((self.settings.otto_recorded,))
        return "Answers recorded during the build" + (f", {present_otto.day(since)}" if since else "")

    @staticmethod
    def _pack_answers_line(installed: list) -> str:
        """Advisories: where the answers on that page came from. They are in the installed packs, each of which says how
        its own answers were made; the Live Otto switch changes nothing about them."""
        notes = {pack.version: pack.pack["research"]["answers_note"] for _, pack in installed}
        if not notes:
            return "No test pack is installed, so there are no answers here yet."
        if len(set(notes.values())) == 1:
            return next(iter(notes.values()))
        return " ".join(f"Pack {version}: {note}." for version, note in notes.items())

    # ---------------------------------------------------------------- the Advisories page

    def _closed_at(self, plan_id: int) -> datetime | None:
        a = self.assessment_for(plan_id=plan_id)
        return a.closed_at if a is not None else None

    def _otto_checks(self, db, plan_id: int) -> list[OttoCheckRow]:
        return list(db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_id == plan_id).order_by(OttoCheckRow.id)).all())

    def advisories_view(self, plan_id: int) -> dict:
        """Every published advisory in the installed test packs, for one assessment. It words no result and decides
        none: a result shown here is the reviewer's, exactly as Evidence Lab words it."""
        upto = self._closed_at(plan_id)
        lab_rows = {r["item_id"]: r for r in self.lab_view(plan_id)["rows"]}
        fixes = self.fixes_view(plan_id).get("fixes") or []
        states = {f["id"]: f for f in self.fix_states(plan_id)}     # type: ignore[attr-defined]
        with self.db() as db:
            plan = self._plan(db, plan_id)
            claims = self._claims(db.get(ImportRow, plan.import_id))
            fitting = checks.programs_that_fit(claims)
            installed = self._installed_packs(db, upto)
            entries = self._pack_advisories(db, upto)
            added = {(c.advisory_id, c.plan_item_id): c for c in self._otto_checks(db, plan_id)}
            # Otto's proposals for this file: one for each ready test and each program it fits, with where a person's
            # decisions on it stand. (Worked out here; nothing is written by looking.)
            proposed = {p["id"]: p for p in self._proposals(db, plan, ("check",))}     # type: ignore[attr-defined]
            # The 5c fixes: an advisory is "New" when the pack it first arrived with is the newest one installed (for a
            # closed assessment: the newest one installed when it was closed). One that a later pack only updates
            # arrived earlier, so it is not new.
            arrived: dict[str, str] = {}
            for _, each in installed:
                for entry in each.pack["advisories"]:
                    arrived.setdefault(entry["id"], each.version)
            newest = installed[-1][1].version if installed else None
            rows = []
            for pack, advisory in entries:
                here = []
                design_sha: str | None = advisory["test"]["design_sha256"] if advisory["test"]["state"] == "ready" else None
                for program in fitting if design_sha is not None else []:
                    item = checks.existing_item(self, db, plan_id, design_sha or "", program["ref"])
                    shown, first, ledger = None, None, []
                    if item is not None and not item.removed:
                        row = lab_rows.get(item.id) or {}
                        shown = row.get("after") or row.get("result")
                        # after a retest the newest result is of another version than the file names: the first run's goes with it
                        first = row.get("result") if row.get("after") else None
                        check = added.get((advisory["id"], item.id))
                        if check is not None:
                            ledger = self._ledger_about(plan_id, check.objective_id)
                    proposal = proposed.get(otto_proposals.check_id(advisory["id"], design_sha or "", program["ref"]))
                    here.append({"program": program["label"], "item_id": item.id if item is not None and not item.removed else None,
                                 "result": shown, "first": first, "ledger": ledger, "proposal": proposal,
                                 "decision_ledger": (self.otto_ledger_about(plan_id, proposal["objective_id"])      # type: ignore[attr-defined]
                                                     if proposal is not None and proposal.get("objective_id") else []),
                                 # the assessment's own program (one of our demo components), not a real library
                                 "own_code": components.lookup(program["component"], program["version"]) is not None})
                item_ids = {h["item_id"] for h in here if h["item_id"] is not None}
                answering = [f for f in fixes if any(a.get("item_id") in item_ids for a in (states.get(f["id"]) or {}).get("answers") or [])]
                # where several programs failed this check, the link goes to a fix that Otto proposes, if there is one
                fix = next((f for f in answering if f.get("labels")), answering[0] if answering else None)
                rows.append({"pack": pack, "advisory": advisory, "design": pack.design(design_sha) if design_sha else None, "here": here, "fix": fix,
                             "arrived": arrived.get(advisory["id"]), "new": arrived.get(advisory["id"]) == newest})
            a = self.assessment_for(plan_id=plan_id)
            answers = self._pack_answers_line(installed)
        status = harness.public_status()
        view = present_otto.advisories_view(rows=rows, packs=[pack for _, pack in installed], fitting=[p["label"] for p in fitting],
                                            closed=upto is not None, harness_status=status, answers_line=answers,
                                            assessment_id=a.id if a is not None else None)
        # Phase 6, Otto's research loop: the block "New advisories" (Look for new advisories; Design and prove tests).
        view["lookup"] = self.lookup_view(plan_id)        # type: ignore[attr-defined]
        return view

    def otto_relations(self, plan_id: int) -> list[dict]:
        """For the Related block: every advisory of the installed packs with the plan's checks that came from it."""
        upto = self._closed_at(plan_id)
        out = []
        with self.db() as db:
            linked: dict[str, list[int]] = {}
            for item in self._items(db, plan_id):
                row = db.get(TestSpecRow, item.spec_hash)
                if row is None or row.kind != research.ADVISORY_KIND:
                    continue
                spec, _ = read_spec(row)
                advisory_id = ((spec.get("inputs") or {}).get("advisory") or {}).get("id")
                if advisory_id:
                    linked.setdefault(str(advisory_id), []).append(item.id)
            for _, advisory in self._pack_advisories(db, upto):
                name = (advisory["reading"] or {}).get("plain_name") or "An advisory that could not be read"
                out.append({"id": advisory["id"], "name": name, "sub": present_otto.TEST_LABELS[advisory["test"]["state"]][0],
                            "items": linked.get(advisory["id"], [])})
        return out

    def otto_found(self, db, imp: ImportRow) -> dict:
        """Import: how many checks of the installed test packs may apply to this file, with the way to Advisories.
        It counts pack tests and the signing programs they fit. It adds nothing and runs nothing."""
        a = db.scalars(select(AssessmentRow).where(AssessmentRow.import_id == imp.id)).first()
        upto = a.closed_at if a is not None else None
        fitting = checks.programs_that_fit(self._claims(imp))
        ready = [advisory for _, advisory in self._pack_advisories(db, upto) if advisory["test"]["state"] == "ready"]
        return present_otto.found_line(packs=len(self._installed_packs(db, upto)), ready=len(ready), programs=[p["label"] for p in fitting])

    def otto_new_checks(self, plan_id: int | None) -> int:
        """How many of Otto's proposed checks in this assessment nobody has decided yet (for the Overview's next step).
        It adds nothing."""
        if plan_id is None or not harness.status().installed or self._closed_at(plan_id) is not None:
            return 0
        return int(self.otto_waiting(plan_id)["check"])      # type: ignore[attr-defined]

    def _ledger_about(self, plan_id: int, objective_id: str) -> list[dict]:
        a = self.assessment_for(plan_id=plan_id)
        if a is None:
            return []
        try:
            return assurance.Ledger(self.settings.data_dir, a.id).about(objective_id)
        except harness.OttoNotInstalled:
            return []

    # ---------------------------------------------------------------- the fix a pack carries for an advisory

    def _pack_advisory(self, db, advisory_id: str, plan_id: int | None = None) -> tuple[packs.Pack, dict] | None:
        """What the installed packs say about one advisory. For a closed assessment: the packs that were installed when
        it was signed off, so nothing it shows changes when a later pack says more about the same advisory."""
        upto = self._closed_at(plan_id) if plan_id is not None else None
        return next(((pack, a) for pack, a in self._pack_advisories(db, upto) if a["id"] == advisory_id), None)

    def _otto_pack_fix(self, db, item_id: int, program: str | None = None) -> dict | None:
        """For a failed advisory check: the fix its test pack proposes for the advisory (the publisher's fixed version
        with its quoted source, and how the update did on public copies), as Fixes shows it. None when the check did
        not come from an installed pack. `program` is the program the check failed on: a fix for one library is never
        proposed for another program that fails the same check."""
        item = db.get(PlanItemRow, item_id)
        spec, _ = read_spec(db.get(TestSpecRow, item.spec_hash)) if item is not None else ({}, False)
        advisory_id = ((spec.get("inputs") or {}).get("advisory") or {}).get("id")
        found = self._pack_advisory(db, str(advisory_id), item.plan_id) if advisory_id else None
        if found is None:
            return None
        pack, advisory = found
        fix = advisory["fix"]
        about = {"advisory": advisory["id"], "plain_name": (advisory["reading"] or {}).get("plain_name"), "pack": pack.version,
                 "item_id": item_id}
        if fix["kind"] == "update" and program is not None and fix["library"] != program:
            # The advisory is about another library. Its publisher's fix is for that library and says nothing about this one.
            return {**about, "state": "none", "kind": "none", "library": fix["library"], "version": fix["version"], "summary": None,
                    "quote": None,
                    "reason": (f"The advisory is about {fix['library']}, and the fixed version its publisher names is a version of "
                               f"{fix['library']}. This check failed on {program}, and the test pack holds no fix for {program}.")}
        quote = None
        if fix["quote"] is not None:
            quote = present_otto._quoted(advisory, fix["quote"])
        out = {**about, "state": fix["state"], "kind": fix["kind"], "library": fix["library"], "version": fix["version"],
               "summary": fix["summary"], "reason": fix["reason"], "quote": quote}
        if fix["kind"] == "update":
            # The two proof rows of a library's fix: how the update did on public copies before the pack was signed (from
            # the pack, with the research ledger's entries), and what this assessment's own retests show.
            here = self._proven_here(db, item, fix["library"], fix["version"])
            out["public"] = present_otto.public_copies_row(fix, advisory)
            out["here"] = here
            out["rows"] = [out["public"], present_otto.your_system_row(fix, here)]
        return out

    def _proven_here(self, db, item: PlanItemRow, library: str, fixed: str) -> dict:
        """What this assessment's own retests show about a library's fix. It reads the newest retest on the fixed version in
        which this advisory check has a reviewed run, through the same gate as every result, with every other
        pass-or-fail test the plan holds for that same program:

          "passed"      the check passed there, and every one of those tests has a result in that same retest and passed
                        (the rule a fix is called proven by on public copies);
          "not_proven"  the check did not pass there, or one of those tests has a result there that is not a pass;
          "running"     nothing has failed so far, some of those tests have no result yet, and that retest is still running;
          "unfinished"  the same, and that retest is no longer running (it was interrupted): half a retest proves nothing;
          "not_yet"     no retest on the fixed version has a result for this check (`live`: one is running now)."""
        mine, _ = read_spec(db.get(TestSpecRow, item.spec_hash))
        program = (mine.get("target") or {}).get("claim")
        expected = []              # every pass-or-fail test of the plan for this same program, this check among them
        for other in self._items(db, item.plan_id):
            row = db.get(TestSpecRow, other.spec_hash)
            if row is None or row.kind not in PASS_OR_FAIL_KINDS:
                continue
            spec, _ = read_spec(row)
            if other.id == item.id or (program is not None and (spec.get("target") or {}).get("claim") == program):
                expected.append((other, row.kind, research.title_of(row.kind, spec)))
        # is a retest on that fixed version running right now? (the newest retest of the plan, and a job of it not done)
        newest_retest = db.scalars(select(RetestRow).where(RetestRow.plan_id == item.plan_id).order_by(RetestRow.id.desc()).limit(1)).first()
        live = False
        if newest_retest is not None and newest_retest.version == fixed:
            live = any((job := self.jobs.get((other.id, "retest"))) is not None and job.status != "done" for other, _, _ in expected)
        runs = db.scalars(select(TestRunRow).where(TestRunRow.plan_item_id == item.id, TestRunRow.phase == "retest",
                                                   TestRunRow.component_name == library, TestRunRow.component_version == fixed)
                          .order_by(TestRunRow.id.desc())).all()
        for run in runs:
            result = self._result(db, run)
            if result is None:
                continue
            same = db.scalars(select(TestRunRow).where(TestRunRow.plan_id == item.plan_id, TestRunRow.phase == "retest",
                                                       TestRunRow.retest_id == run.retest_id, TestRunRow.component_name == library,
                                                       TestRunRow.component_version == fixed).order_by(TestRunRow.id)).all()
            newest: dict[int, TestRunRow] = {}
            for other in same:
                newest[other.plan_item_id] = other
            others, missing = [], []
            for other, kind, title in expected:
                if other.id == item.id:
                    continue
                said = self._result(db, newest[other.id]) if other.id in newest else None
                if said is None:
                    missing.append({"item_id": other.id, "kind": kind, "title": title})
                else:
                    others.append({"item_id": other.id, "kind": kind, "title": title, "code": said["code"], "label": said["label"]})
            failing = [o for o in others if o["code"] != "passed"]
            still_running = live and newest_retest is not None and run.retest_id == newest_retest.id
            if result["code"] != "passed" or failing:
                state = "not_proven"
            elif missing:
                state = "running" if still_running else "unfinished"
            else:
                state = "passed"
            return {"state": state, "library": library, "version": fixed, "item_id": item.id, "run_id": run.id, "retest_id": run.retest_id,
                    "finished_at": run.finished_at, "check": {"code": result["code"], "label": result["label"]},
                    "tests": len(others) + len(missing) + 1, "done": len(others) + 1, "failing": len(failing), "others": others,
                    "missing": missing, "live": bool(still_running)}
        return {"state": "not_yet", "library": library, "version": fixed, "item_id": item.id, "live": bool(live)}

    def otto_result_fix(self, db, spec: dict, name: str | None, version: str | None, plan_id: int | None = None) -> dict | None:
        """What the Suggested fix line of an advisory check's result may say: Otto's fix for this program, when the
        installed packs carry one. For the assessment's own demo program it points to Fixes."""
        advisory_id = ((spec.get("inputs") or {}).get("advisory") or {}).get("id")
        found = self._pack_advisory(db, str(advisory_id), plan_id) if advisory_id else None
        if found is None or name is None:
            return None
        if components.lookup(name, version) is not None:
            return {"state": "own_code"}
        fix = found[1]["fix"]
        if fix["kind"] == "update" and fix["library"] == name:
            # (the first proof row only: it comes from the pack and never changes. The second row depends on later retests,
            #  so it is said in Fixes and on Evidence's fix line, not in a result's own words.)
            return {"state": fix["state"], "kind": "update", "library": fix["library"], "version": fix["version"], "reason": fix["reason"],
                    "public_line": present_otto.public_copies_row(fix, found[1])["line"]}
        return None

    # ---------------------------------------------------------------- hooks around a run of an advisory check

    def _otto_cannot_run(self, db, item_id: int) -> str | None:
        """Why an advisory check that a person added from a pack can't run right now, or None. Without the pinned
        Otto its run could not be recorded, so it does not run."""
        if db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_item_id == item_id)).first() is None:
            return None
        status = harness.status()
        return None if status.installed else status.sentence

    def _otto_after_review(self, run_id: int) -> None:
        """After a run of an added advisory check was reviewed: bind the run and its review to the locked test in the
        assessment's Otto ledger. The entry holds fingerprints and names, never the result."""
        with self.db() as db:
            run = db.get(TestRunRow, run_id)
            if run is None:
                return
            check = db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_item_id == run.plan_item_id)).first()
            review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == run_id)).first()
            if check is None or review is None:
                return
            record = run_record(run)
            stored = review_dict(review)
            code = db.scalars(select(RunCodeRow).where(RunCodeRow.run_id == run_id)).first()
            ran_on = {"name": run.component_name, "version": run.component_version, "mode": run.mode,
                      "commit": code.commit if code is not None else None}
            entry = dict(spec_hash=run.spec_hash, run_id=run.id, run_sha256=sha256_hex(record),
                         review_sha256=review_fingerprint(stored),
                         proposed_by=stored["proposed_by"], reviewer=stored["reviewer"], phase=run.phase, ran_on=ran_on)
            objective, plan_id = check.objective_id, run.plan_id
        a = self.assessment_for(plan_id=plan_id)
        if a is None:
            return
        try:
            assurance.Ledger(self.settings.data_dir, a.id).record_run(objective, **entry)
        except harness.OttoNotInstalled:
            pass      # (the run was refused before it started when Otto is missing; this only guards a removal in between)

    def otto_record_step(self, plan_id: int, advisory_id: str, step: model.Step, outcome: str, refusal: str | None) -> int:
        """Keep one Claude step taken in the app: in the database (so a view never asks twice) and, in full, in the
        assessment's Otto ledger. Returns the stored row's id."""
        record = step.record()
        claim = None
        a = self.assessment_for(plan_id=plan_id)
        if a is not None:
            try:
                claim, _ = assurance.Ledger(self.settings.data_dir, a.id).record_step(advisory_id, record, outcome, refusal)
            except harness.OttoNotInstalled:
                claim = None
        with self.db() as db:
            row = OttoStepRow(plan_id=plan_id, step=step.step, advisory_id=advisory_id, source=step.source, model=step.model, prompt=step.prompt,
                              answer=step.answer, prompt_sha256=step.prompt_sha256, answer_sha256=step.answer_sha256,
                              input_tokens=step.input_tokens, output_tokens=step.output_tokens, cost_nano_usd=step.cost_nano_usd, at=step.at,
                              how=step.how[:300], outcome=outcome, refusal=(refusal or None) and str(refusal)[:300], claim_id=claim)
            db.add(row)
            db.commit()
            return row.id

    def otto_stored_step(self, plan_id: int, step: str, prompt_sha256: str) -> dict | None:
        """The stored Claude step for exactly this prompt in this assessment, if one was taken before."""
        with self.db() as db:
            row = db.scalars(select(OttoStepRow).where(OttoStepRow.plan_id == plan_id, OttoStepRow.step == step,
                                                       OttoStepRow.prompt_sha256 == prompt_sha256).order_by(OttoStepRow.id.desc())).first()
            if row is None:
                return None
            return {"id": row.id, "answer": row.answer, "source": row.source, "model": row.model, "how": row.how, "at": row.at,
                    "outcome": row.outcome, "refusal": row.refusal, "prompt_sha256": row.prompt_sha256, "answer_sha256": row.answer_sha256,
                    "claim_id": row.claim_id, "cost_nano_usd": row.cost_nano_usd}

    # ---------------------------------------------------------------- what the evidence file gets

    def otto_evidence(self, plan_id: int) -> dict | None:
        """The Otto part of an assessment's evidence: the harness, the packs this assessment's checks came from (their
        signed files, whole), the assessment's ledger with the hash of its latest entry, each advisory check's links
        into the ledger, and every Claude step taken in the app. None when the assessment has nothing of Otto's."""
        a = self.assessment_for(plan_id=plan_id)
        # Phase 6, Otto's research loop: every look for new advisories and every research run of this assessment.
        lookups = self.lookups_evidence(plan_id)                 # type: ignore[attr-defined]
        made_by_runs = {str(run["pack_version"]) for run in lookups["research"] if run.get("pack_version")}
        with self.db() as db:
            added = self._otto_checks(db, plan_id)
            steps = db.scalars(select(OttoStepRow).where(OttoStepRow.plan_id == plan_id).order_by(OttoStepRow.id)).all()
            decided = db.scalar(select(func.count(OttoDecisionRow.id)).where(OttoDecisionRow.plan_id == plan_id)) or 0
            if not added and not steps and not decided and not lookups["looks"] and not lookups["research"]:
                return None
            # the packs this assessment's checks came from, and every pack a research run of this assessment made
            # (the proof of what that run found is in its pack, whether or not a check of it was accepted)
            wanted = {c.pack_fingerprint for c in added}
            envelopes = [json.loads(row.envelope) for row in self._pack_rows(db) if row.fingerprint in wanted or row.version in made_by_runs]
            checks_out = []
            for c in added:
                row = db.get(TestSpecRow, c.spec_hash)
                spec, _ = read_spec(row)
                item = db.get(PlanItemRow, c.plan_item_id)
                checks_out.append({"item_id": c.plan_item_id, "title": research.title_of(research.ADVISORY_KIND, spec), "advisory": c.advisory_id,
                                   "spec_hash": c.spec_hash, "spec": spec, "design_sha256": c.design_sha256, "pack": c.pack_version,
                                   "pack_fingerprint": c.pack_fingerprint, "lock_entry": c.objective_id, "added_at": iso(c.created_at),
                                   "in_plan": bool(item is not None and not item.removed)})
            steps_out = [{"step": s.step, "advisory": s.advisory_id, "source": s.source, "model": s.model, "prompt": s.prompt, "answer": s.answer,
                          "prompt_sha256": s.prompt_sha256, "answer_sha256": s.answer_sha256, "input_tokens": s.input_tokens,
                          "output_tokens": s.output_tokens, "cost_nano_usd": s.cost_nano_usd, "at": s.at, "how": s.how, "outcome": s.outcome,
                          "refusal": s.refusal, "ledger_entry": s.claim_id} for s in steps]
        status = harness.public_status()
        ledger: dict = {"height": 0, "head": None, "root": None, "lines": []}
        bound: list[dict] = []
        if a is not None:
            try:
                book = assurance.Ledger(self.settings.data_dir, a.id)
                head = book.head()
                if head is not None:
                    ledger = {**head, "lines": book.lines()}
                    bound = [{"ledger_entry": book.record_id(entry), "lock_entry": entry["payload"]["objective_id"],
                              "run_id": entry["payload"]["artifact"]["run_id"]}
                             for entry in book.entries() if entry["kind"] == "claim" and "run_id" in entry["payload"]["artifact"]]
            except harness.OttoNotInstalled:
                ledger["note"] = "The Otto harness was not installed when this file was made, so the ledger could not be read."
        runs_out = []
        with self.db() as db:
            for link in bound:
                # Every run the ledger binds, in full: its record as fingerprinted and its review, so the binding can be
                # recomputed from this file alone.
                run = db.get(TestRunRow, link["run_id"])
                review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == link["run_id"])).first() if run is not None else None
                if run is None or review is None:
                    continue
                runs_out.append({**link, "phase": run.phase, "record": run_record(run), "review": review_part(review_dict(review))})
        return {"schema": "isogeny.otto-evidence/1",
                "harness": {"repository": status["repository"], "commit": status["commit"], "version": status["version"],
                            "installed": status["installed"]},
                "packs": envelopes, "checks": checks_out, "ledger": ledger, "runs": runs_out, "steps": steps_out,
                # Otto proposes; a person decides: every proposal of this assessment as it stands, and every accept, reject,
                # undo and reconsider on it, each with who and when and its entry in the ledger.
                "proposals": self.otto_proposals_evidence(plan_id),      # type: ignore[attr-defined]
                "lookups": lookups,
                "decisions_note": ("Each proposal is decided by a person. A decision is recorded with who and when, in this file and in the "
                                   "ledger. This version has one login: whoever is at the keyboard records each decision, under the name "
                                   "shown. A decision is not a result."),
                "note": ("The ledger binds each run of an advisory check to the test that was locked before it, and shows that the reviewer was "
                         "not the proposer. It holds no result: results are in the checks of this file, decided by the reviewer.")}


def review_fingerprint(stored: dict) -> str:
    """The SHA-256 the Otto ledger binds a run's review by: the review as the evidence file holds it, without its time.
    So anyone holding the evidence file can recompute it."""
    return sha256_hex({k: v for k, v in review_part(stored).items() if k != "created_at"})


def _aware(value: datetime) -> datetime:
    from datetime import timezone
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _set(db, key: str, value: str) -> None:
    row = db.get(AppSettingRow, key)
    if row is None:
        db.add(AppSettingRow(key=key, value=value))
    else:
        row.value = value


def _dollars(text: object) -> int:
    """A spending limit typed by a person, in US dollars, as an exact number of billionths of a dollar."""
    raw = str(text or "").strip().replace("$", "").replace(",", ".")
    try:
        whole, _, cents = raw.partition(".")
        if not whole.isdigit() or (cents and not cents.isdigit()) or len(cents) > 2:
            raise ValueError
        nano = int(whole) * model.NANO + int((cents + "00")[:2]) * (model.NANO // 100)
    except ValueError:
        raise BadRequest("The spending limit is a number of US dollars, for example 2 or 2.50.", field="limit") from None
    if not 0 < nano <= MAX_LIMIT_NANO:
        raise BadRequest("The spending limit must be more than 0 and at most 1000 US dollars.", field="limit")
    return nano
