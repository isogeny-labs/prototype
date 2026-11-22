"""Look for new advisories, and prove a test for each on public copies (phase 6, Otto's research loop).

Two clicks on the Advisories page, each behind a box that says what it will do:

  1. **Look for new advisories.** The app asks one public source (app/otto/lookup.py: OSV, or recorded answers in a
     folder on this computer) about the libraries this assessment names, and keeps what it finds: which advisories
     name a version the assessment has, which a test pack already holds, and which are new. Reading is free: no
     Claude step is in it, nothing runs, and nothing is proposed.
  2. **Design and prove tests.** For the new advisories that can be tried here, the research side (backend/ottolab,
     started as a command of its own: the app never imports it) reads each advisory, designs a test from published
     cases, and tries it on public copies in isolated mode: it must fail on the affected version, pass on the fixed
     one, and the control must fail. What it finds is signed into a test pack made on this computer, exactly as the
     research command has done since phase 5c, and that pack is installed by this same click (after any built-in pack
     that is not installed yet, in order). A proven check then arrives on Advisories as a proposal like any other; an
     advisory with no proven test says why.

Rules kept here:
  - Nothing is proposed that was not proven on public copies. The proof is the pack's own trial, recorded in the
    research ledger and signed with the pack, so the evidence file and the verify command check it like any pack's.
  - A test is only designed where it can be tried: where this version of the app has no public copy of the affected and
    the fixed version, the advisory says so, and Claude is not asked.
  - Claude is asked only by the second click, through the research command, with Live Otto on and within the spending
    limit; with Live Otto off only recorded answers are used. Looking, and reading this page, never ask Claude.
  - What a look found and what a research run did are kept, add-only (otto_lookups, otto_research). An answer of the
    source is data: nothing in it runs.
  - A decision stays with a person: a proven check is proposed, never added. Nothing of the customer's is run.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select

from app import real_libraries
from app.db import ImportRow, OttoLookupRow, OttoResearchRow, PlanRow, iso
from app.engine import research
from app.errors import Conflict
from app.knowledge.base import knowledge_base
from app.knowledge.versions import read_version
from app.otto import harness, lookup, model, packs
from app.present import lookup as present_lookup
from app.run import components
from app.sandbox import registries as sandbox_registries      # (its tables of names only: the app never reads a registry)

BACKEND = Path(__file__).resolve().parents[2]
SNAPSHOT_SCHEMA = "isogeny.advisory-snapshot/1"
FACTS_SCHEMA = "isogeny.sandbox-facts/1"          # (sandbox research: what the research command is told beside an advisory's text)
MAX_OUTPUT_LINES = 400
RESEARCH_TIMEOUT_SECONDS = 4 * 60 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class DiscoverMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    settings: Any
    mode: Any
    _plan: Callable[..., PlanRow]
    _claims: Callable[..., list[dict]]
    _otto_lock: Any
    _closed_at: Callable[..., Any]
    _dependency_state: Callable[..., dict | None]
    _installed_packs: Callable[..., list]
    _pack_rows: Callable[..., list]
    _trusted_pack_keys: Callable[..., dict]
    install_pack: Callable[..., dict]
    otto_live_ready: Callable[..., bool]
    _otto_limit: Callable[..., int]
    decision_name: Callable[..., str]
    sandbox_on: Callable[..., bool]
    sandbox_refresh: Callable[..., None]
    sandbox_run_limit: Callable[..., int]
    sandbox_limits: Callable[..., tuple[int, int]]
    sandbox_day_reached: Callable[..., str | None]
    sandbox_research_line: Callable[..., str]

    def _init_discover(self) -> None:
        self._research_lock = threading.Lock()
        self._research_live: dict[int, dict] = {}        # research row id -> {"lines": [...], "thread": Thread, "process": Popen}

    def stop_research(self) -> None:
        """When the app stops: end a research run that is still going, with everything it started. Its end row then
        says it stopped, nothing is installed, and the block says the run can be started again. A run is never left
        behind to go on working after the app is gone."""
        for state in list(self._research_live.values()):
            state["stopped"] = True
            process = state.get("process")
            if process is None or process.poll() is not None:
                continue
            try:
                os.killpg(process.pid, signal.SIGTERM)       # (the command and what it started: it runs in a group of its own)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        for state in list(self._research_live.values()):
            thread = state.get("thread")
            if thread is not None:
                thread.join(15)

    # ---------------------------------------------------------------- which libraries, and what the source can be asked

    def _named_libraries(self, db, plan: PlanRow) -> list[dict]:
        """Every library this assessment names that the knowledge base recognises, once per name and version: from the
        scanner file's programs, and from the newest dependency list."""
        known = knowledge_base().files
        out: dict[tuple[str, str | None], dict] = {}
        for program in research.programs(self._claims(db.get(ImportRow, plan.import_id))):
            name, version = str(program["component"]), program.get("version")
            if name in known:
                out.setdefault((name, version), {"library": name, "version": version, "where": "your file", "label": program["label"]})
        state = self._dependency_state(db, plan)
        for row in (state or {}).get("rows") or []:
            name, version = row.get("library"), row.get("version")
            if name in known:
                out.setdefault((str(name), version), {"library": str(name), "version": version, "where": "your dependency list",
                                                      "label": row.get("label") or f"{name} {version or ''}".strip()})
        return list(out.values())

    def _advisory_source(self):
        folder = self.settings.advisory_source_dir
        return lookup.RecordedSource(folder) if folder else lookup.OsvSource()

    def _askable(self, libraries: list[dict]) -> tuple[list[lookup.Package], list[str]]:
        """(the packages the source can be asked about, the libraries it keeps nowhere by name), each once."""
        known = knowledge_base().files
        asked: dict[str, lookup.Package] = {}
        skipped: list[str] = []
        for lib in libraries:
            package = lookup.package_of(lib["library"], [p.purl for p in known[lib["library"]].packages])
            if package is None:
                if lib["library"] not in skipped:
                    skipped.append(lib["library"])
            else:
                asked.setdefault(package.key, package)
        return list(asked.values()), skipped

    # ---------------------------------------------------------------- the first click: look

    def look_for_advisories(self, plan_id: int, by: str | None = None, source=None) -> dict:
        """Ask the source once about every library this assessment names, and keep what came back. Nothing runs.
        (`by`: the Watch list's clock looks under its own name, never a person's. `source`: the clock hands in one
        source for all the assessments of one round, so a library two of them name is asked about once.)"""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            libraries = self._named_libraries(db, plan)
        packages, _ = self._askable(libraries)
        if not packages:
            raise Conflict(present_lookup.LOOK_NOTHING_TO_ASK)
        source = source or self._advisory_source()

        def fits(found: lookup.Found) -> bool:
            """Does this advisory name a version the assessment has (or could it: its versions are not read yet)?"""
            mine = [lib for lib in libraries if lib["library"] == found.advisory["package"]["name"]]
            if not (found.ranges or found.versions):
                return bool(mine)
            return any(lookup.names_version(found, lib["version"])["state"] != "not_affected" for lib in mine)
        try:
            look = lookup.read_source(source, packages, fits=fits)
        except lookup.LookupError_ as exc:
            raise Conflict(str(exc)) from None
        found = [{"advisory": f.advisory, "ranges": f.ranges, "versions": f.versions[:200], "record_id": f.record_id} for f in look["found"]]
        # (kept with each package: whether its answer had more pages than this version reads. `cut`: more usable
        #  advisories were read than one look keeps; those that fit were ranked first.)
        asked = [{**a, "more_pages": f"{a['name']} ({a['ecosystem']})" in look["more_pages"]} for a in look["asked"]]
        with self._otto_lock, self.db() as db:
            db.add(OttoLookupRow(plan_id=plan_id, at=_now(), by=by or self.decision_name(), source=look["source"], sent=look["sent"],
                                 asked=asked, found=found, left_out=int(look["left_out"]), cut=bool(look["not_listed"]),
                                 withdrawn=list(look.get("withdrawn") or [])))
            db.commit()
        return self.advisories_view(plan_id)      # type: ignore[attr-defined]

    # ---------------------------------------------------------------- what a look found, as it stands now

    def _latest_lookup(self, db, plan_id: int) -> OttoLookupRow | None:
        return db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id.desc()).limit(1)).first()

    def _waiting_chain(self, db) -> list[packs.Pack]:
        """The packs in the updates folders on this computer (built-in, and made here) that can be installed after the
        installed ones, in the order they install. A pack that does not follow is not among them."""
        keys = self._trusted_pack_keys()
        found: list[packs.Pack] = []
        for folder in (self.settings.otto_updates, self.settings.otto_local_updates):
            found += packs.found_in(folder, keys)[0]
        if not self.sandbox_on():           # (a pack that carries asking code is taken only while Sandbox research is on)
            found = [p for p in found if p.pack["schema"] != packs.PACK_SCHEMA_2]
        found.sort(key=lambda p: packs.version_key(p.version))          # (stable: at one version a built-in pack comes first)
        rows = self._pack_rows(db)
        have = {r.fingerprint for r in rows}
        newest: packs.Pack | dict | None = {"version": rows[-1].version, "fingerprint": rows[-1].fingerprint} if rows else None
        chain: list[packs.Pack] = []
        for _ in range(50):
            following = next((p for p in found if p.fingerprint not in have and packs.follows(p, newest) is None), None)
            if following is None:
                break
            chain.append(following)
            have.add(following.fingerprint)
            newest = following
        return chain

    def _packs_by_advisory(self, db, upto=None) -> tuple[dict[str, dict], dict[str, dict]]:
        """(advisories in installed packs by id and by other name: {"version", "entry"}; advisories in a pack that is
        ready and not installed yet: id -> {"version", "made_here"})."""
        installed: dict[str, dict] = {}
        for _, pack in self._installed_packs(db, upto):
            for entry in pack.pack["advisories"]:
                for name in (entry["id"], *entry.get("aliases", [])):
                    installed[str(name).upper()] = {"version": pack.version, "entry": entry}
        waiting: dict[str, dict] = {}
        for pack in self._waiting_chain(db):
            for entry in pack.pack["advisories"]:
                for name in (entry["id"], *entry.get("aliases", [])):
                    waiting.setdefault(str(name).upper(), {"version": pack.version, "made_here": bool(pack.made_here)})
        return installed, waiting

    def _lookup_rows(self, db, plan: PlanRow, row: OttoLookupRow) -> list[dict]:
        """Each advisory of one look with where it stands now: in a pack, new and able to be tried, or not."""
        libraries = self._named_libraries(db, plan)
        installed, waiting = self._packs_by_advisory(db, self._closed_at(plan.id))
        sandbox = self.sandbox_on()
        # (the name each library has where it is published, as this look asked about it)
        asked_names = {str(a.get("library")): str(a.get("name")) for a in row.asked or [] if isinstance(a, dict)}
        out = []
        for item in row.found or []:
            copies: dict | None = None
            advisory = item["advisory"]
            library = advisory["package"]["name"]
            mine = [lib for lib in libraries if lib["library"] == library]
            found = lookup.Found(advisory=advisory, ranges=item.get("ranges") or [], versions=item.get("versions") or [],
                                 record_id=item.get("record_id") or advisory["id"])
            # (a recorded snapshot carries no ranges: the reading step reads the versions from the publisher's text)
            fits = [{**lib, **(lookup.names_version(found, lib["version"]) if found.ranges or found.versions else {"state": "unread", "fixed": None})}
                    for lib in mine]
            names = [advisory["id"].upper(), *[str(a).upper() for a in advisory.get("aliases") or []]]
            in_pack = next((installed[n] for n in names if n in installed), None)
            in_waiting = next((waiting[n] for n in names if n in waiting), None)
            affected = [f for f in fits if f["state"] in ("affected", "unread")]
            unsure = [f for f in fits if f["state"] == "cant_tell"]
            if in_pack is not None:
                state, why = "in_pack", None
            elif in_waiting is not None:
                state, why = "in_waiting_pack", None
            elif not affected and not unsure:
                state, why = "not_yours", None
            else:
                state, why = self._can_try(library, affected or unsure)
                if sandbox and not self._pinned_versions(library):
                    # Sandbox research (a prototype): the app has no pinned copy of this library, and a copy can be made
                    # from its public registry. Decided by fixed rules from the source's own fields; nothing is fetched here.
                    state, why, copies = self._can_try_sandbox(advisory, found, affected or unsure, asked_names)
            out.append({"advisory": advisory, "library": library, "fits": fits, "state": state, "why": why, "sandbox": copies,
                        # (sandbox research: a weakness the source names no fixed version for is on the Watch list)
                        "watch_item": f"{advisory['id']}~{library}" if sandbox and state == "no_test" and why == present_lookup.NO_FIXED_VERSION else None,
                        "pack": in_pack["version"] if in_pack else (in_waiting or {}).get("version"),
                        "pack_made_here": bool(in_waiting and in_waiting["made_here"]) if not in_pack else False,
                        "entry": in_pack["entry"] if in_pack else None})
        return out

    @staticmethod
    def _can_try(library: str, fits: list[dict]) -> tuple[str, str | None]:
        """("new", None) when a test for this advisory could be tried on public copies here; ("no_test", why) when
        not. The rule the research step itself uses: a public copy of the fixed version, and an older one."""
        have = components.versions_of(library)
        if not have:
            return "no_test", present_lookup.no_copy_of(library)
        fixed = next((f["fixed"] for f in fits if f.get("fixed")), None)
        if any(f["state"] == "unread" for f in fits):
            return "new", None               # the reading step reads the fixed version from the publisher's text
        if all(f["state"] == "cant_tell" for f in fits):
            return "no_test", present_lookup.CANT_TELL_VERSION      # (not "no fixed version": the record may well name one)
        if fixed is None:
            return "no_test", present_lookup.NO_FIXED_VERSION
        if fixed not in have or have.index(fixed) == 0 or read_version(fixed) is None:
            return "no_test", present_lookup.no_copy_of_version(library, fixed, have)
        return "new", None

    @staticmethod
    def _pinned_versions(library: str) -> list[str]:
        """The versions of this library the app itself holds: a demo program's, or a pinned real library's. Never a
        sandbox copy's."""
        if library in components.VERSIONS:
            return list(components.VERSIONS[library])
        found = real_libraries.LIBRARIES.get(library)
        return list(found["versions"]) if found else []

    @staticmethod
    def _can_try_sandbox(advisory: dict, found: lookup.Found, fits: list[dict], asked_names: dict[str, str]) -> tuple[str, str | None, dict | None]:
        """Sandbox research: can a test for this advisory be tried on public copies made from the library's registry?
        ("new", None, what would be fetched) or ("no_test", why, None). Fixed rules over the source's own fields."""
        library, ecosystem = advisory["package"]["name"], advisory["package"]["ecosystem"]
        names = [str(advisory["id"]).upper(), *[str(a).upper() for a in advisory.get("aliases") or []], str(found.record_id).upper()]
        if any(name.startswith("MAL-") for name in names):
            return "no_test", present_lookup.HARMFUL_PACKAGE, None       # a package published to do harm is never fetched
        registry = sandbox_registries.ECOSYSTEMS.get(ecosystem)
        package = asked_names.get(library)
        if registry is None or not package:
            return "no_test", present_lookup.no_registry(library, ecosystem), None
        if not found.ranges:
            return "no_test", present_lookup.NO_VERSION_FIELDS, None
        if all(f["state"] == "cant_tell" for f in fits):
            return "no_test", present_lookup.CANT_TELL_VERSION, None
        ends = [r for r in found.ranges if r.get("fixed") or r.get("last_affected")]
        if not ends:
            return "no_test", present_lookup.NO_FIXED_VERSION, None
        fixed = next((f["fixed"] for f in fits if f.get("fixed")), None) or next((r["fixed"] for r in ends if r.get("fixed")), None)
        yours = sorted({str(f["version"]) for f in fits if f.get("version") and f["state"] == "affected"})
        return "new", None, {"library": library, "registry": registry, "registry_words": sandbox_registries.WORDS[registry], "package": package,
                             "fixed": fixed, "after": None if fixed else ends[0]["last_affected"], "yours": yours,
                             "ranges": [{"introduced": r["introduced"], "fixed": r.get("fixed"), "last_affected": r.get("last_affected")}
                                        for r in found.ranges]}

    # ---------------------------------------------------------------- the second click: design and prove

    def _research_rows(self, db, plan_id: int) -> list[OttoResearchRow]:
        return list(db.scalars(select(OttoResearchRow).where(OttoResearchRow.plan_id == plan_id).order_by(OttoResearchRow.id)).all())

    def _research_state(self, db, plan_id: int) -> dict:
        """The newest research run of this assessment: {"run": its start row, "end": its end row or None, "live": is
        it running in this process, "lines": what it has said so far}."""
        rows = self._research_rows(db, plan_id)
        starts = [r for r in rows if r.kind == "started"]
        if not starts:
            return {"run": None, "end": None, "live": False, "lines": []}
        run = starts[-1]
        end = next((r for r in rows if r.kind == "finished" and r.run_key == run.run_key), None)
        live = self._research_live.get(run.id)
        return {"run": run, "end": end, "live": live is not None and end is None,
                "lines": list((live or {}).get("lines") or (end.output if end is not None else []) or [])}

    def _research_blocked(self, db, plan_id: int, eligible: list[dict]) -> str | None:
        """Why Design and prove tests can't be pressed now, or None."""
        if self._closed_at(plan_id) is not None:
            return present_lookup.CLOSED_SENTENCE
        status = harness.status()
        if not status.installed:
            return status.sentence
        if self._research_live:               # (registered under the lock before its thread starts, removed when its end row is written)
            return present_lookup.RESEARCH_RUNNING
        made_here = next((pack for pack in self._waiting_chain(db) if pack.made_here), None)
        if made_here is not None:
            # A pack made on this computer that was never installed (made by hand with the research command, or by a
            # run that was cut off after signing). The click installs only the pack its own run makes: this one is
            # installed by a person, in Settings, like every pack.
            return present_lookup.waiting_made_here(made_here.version)
        if not eligible:
            return present_lookup.RESEARCH_NOTHING
        if self.mode.name != "isolated":
            return present_lookup.RESEARCH_NEEDS_ISOLATED
        if self.sandbox_on() and self.otto_live_ready():
            return self.sandbox_day_reached()        # (the limit for a day counts only what Claude is paid: a run on recorded answers is free)
        return None

    def start_research(self, plan_id: int, by: str | None = None, only: set[str] | None = None) -> dict:
        """Design and prove tests for the new advisories of the newest look, in the background. The built-in packs
        that are not installed yet are installed first, in order: a pack made here follows the newest one.
        (`by`: a run the Watch list's clock started is kept under the clock's name, never a person's. `only`: the
        advisories such a run takes up; a run a person starts takes every new one.)"""
        # One research run at a time, on this computer: from the check to the moment the run is registered, a second
        # click (another tab, a repeated request) waits here, and then finds the first one running.
        with self._research_lock:
            with self.db() as db:
                plan = self._plan(db, plan_id)
                look = self._latest_lookup(db, plan_id)
                rows = self._lookup_rows(db, plan, look) if look is not None else []
                eligible = [r for r in rows if r["state"] == "new" and (only is None or r["advisory"]["id"] in only)]
                blocked = self._research_blocked(db, plan_id, eligible)
                if blocked or look is None:          # no look means nothing can be tried, which is one of the reasons above
                    raise Conflict(blocked or present_lookup.RESEARCH_NOTHING)
                look_id = look.id
                live, limit = self.otto_live_ready(), self._otto_limit(db)
                sandbox = self.sandbox_on()
                if sandbox:
                    # A sandbox run has its own limit for one run, and a run that asks Claude never more than is left
                    # of the day's. A run on recorded answers pays nothing, so the day's limit does not hold it back.
                    limit = self.sandbox_run_limit() if live else self.sandbox_limits()[0]
                number = sum(1 for r in self._research_rows(db, plan_id) if r.kind == "started") + 1
            installed_first = self._install_waiting_packs()
            run_key = f"{plan_id}-{_now()}-{number}"          # (the count makes it this run's alone: the time is to the second)
            inbox = Path(self.settings.data_dir) / "otto-inbox" / run_key.replace(":", "")
            inbox.mkdir(parents=True, exist_ok=True)
            ids = [r["advisory"]["id"] for r in eligible]
            snapshot = {"schema": SNAPSHOT_SCHEMA, "snapshot": _now()[:10],
                        "about": "Advisories read by Look for new advisories. Every excerpt is a piece of the publisher's own text.",
                        "advisories": [r["advisory"] for r in eligible]}
            (inbox / "advisories.json").write_text(json.dumps(snapshot, indent=1, ensure_ascii=False), encoding="utf-8")
            extras: Path | None = None
            if sandbox:
                # What the research command is told beside each advisory's text: where its library is published, the
                # version ranges the source gives in its own fields, and the versions this assessment names. Kept
                # outside the inbox, which holds the one snapshot file and nothing else.
                extras = inbox.parent / (inbox.name + "-sandbox")
                extras.mkdir(parents=True, exist_ok=True)
                facts = {"schema": FACTS_SCHEMA,
                         "advisories": {r["advisory"]["id"]: {k: r["sandbox"][k] for k in ("library", "registry", "package", "ranges", "yours")}
                                        for r in eligible if r.get("sandbox")}}
                (extras / "facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False), encoding="utf-8")
            with self._otto_lock, self.db() as db:
                started = OttoResearchRow(plan_id=plan_id, run_key=run_key, kind="started", at=_now(), by=by or self.decision_name(),
                                          lookup_id=look_id, advisories=ids, live=bool(live), limit_nano=int(limit),
                                          installed_first=installed_first, exit_code=None, pack_version=None, output=[],
                                          sandbox=bool(sandbox), spent_nano=0)
                db.add(started)
                db.commit()
                row_id = started.id
            state: dict = {"lines": [], "thread": None}
            self._research_live[row_id] = state
            thread = threading.Thread(target=self._run_research, name=f"otto-research-{row_id}", daemon=True,
                                      args=(row_id, plan_id, run_key, inbox, live, limit, look_id, ids, installed_first, extras))
            state["thread"] = thread
            thread.start()
        return self.advisories_view(plan_id)      # type: ignore[attr-defined]

    def research_tries_by_itself(self, db, plan_id: int, advisory_id: str, by: str) -> int:
        """How often a run started under this name (the Watch list's clock) has taken this advisory up already."""
        return sum(1 for r in self._research_rows(db, plan_id) if r.kind == "started" and r.by == by and advisory_id in (r.advisories or []))

    def _install_waiting_packs(self) -> list[str]:
        """Install every built-in pack that is ready and not installed yet, oldest first. Returns their versions.
        (A waiting pack made here blocks the run before this is reached: `_research_blocked`.)"""
        done: list[str] = []
        for _ in range(20):
            with self.db() as db:
                chain = self._waiting_chain(db)
            if not chain or chain[0].made_here:
                break
            self.install_pack(chain[0].version)
            done.append(chain[0].version)
        return done

    def _research_command(self, inbox: Path, live: bool, limit_nano: int) -> list[str]:
        dollars = f"{limit_nano / model.NANO:.2f}"
        command = [sys.executable, "-m", "ottolab.build", "next", "--inbox", str(inbox), "--data-dir", str(self.settings.data_dir),
                   "--shipped", str(self.settings.otto_updates), "--recorded", str(self.settings.otto_recorded), "--limit", dollars]
        return command + (["--live"] if live else [])

    @staticmethod
    def _sandbox_arguments(extras: Path | None) -> list[str]:
        """What a research run started with Sandbox research on is given besides: public copies beyond the pinned set,
        and asking code. Empty with the switch off: the command is then exactly the one it always was."""
        if extras is None:
            return []
        return ["--sandbox", "--facts", str(extras / "facts.json"), "--summary", str(extras / "summary.json")]

    @staticmethod
    def _spent_by(extras: Path | None) -> int | None:
        """What a sandbox research run spent on Claude, from the small file the command keeps while it runs (written at
        its start with nothing spent, and again after every step): what was paid, and what requests with no answer may
        have cost. None: the file is not there or is not exactly that, so what the run spent is not known. The file is
        data, and a number in it that can't be a sum of money is not taken."""
        if extras is None:
            return 0
        try:
            data = json.loads((extras / "summary.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        total = 0
        for name in ("spent_nano", "unanswered_nano"):
            value = data.get(name, 0)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 10 ** 15:
                return None
            total += value
        return total

    def _counted_spent(self, extras: Path | None, live: bool, limit_nano: int) -> int:
        """What a finished run counts for against the limit for a day. A run that could ask Claude and did not leave
        word of what it spent (it was cut off before it could, or its file is not what the command writes) counts with
        its whole limit: the day's limit is never passed because a run ended badly."""
        spent = self._spent_by(extras)
        if spent is None:
            return int(limit_nano) if live else 0
        return min(int(spent), int(limit_nano))

    def _run_research(self, row_id: int, plan_id: int, run_key: str, inbox: Path, live: bool, limit_nano: int, lookup_id: int,
                      ids: list[str], installed_first: list[str], extras: Path | None = None) -> None:
        """The research command, as a process of its own, with what it says kept line by line. Then the pack it made
        is installed. Whatever happens, one end row is written."""
        state = self._research_live[row_id]
        lines: list[str] = state["lines"]
        code, pack_version, reason = None, None, None
        try:
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            command = self._research_command(inbox, live, limit_nano) + self._sandbox_arguments(extras)
            process = subprocess.Popen(command, cwd=str(BACKEND), env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", start_new_session=True)
            state["process"] = process

            def too_long() -> None:
                """The time limit: a run that is still going after it is ended, with everything it started."""
                state["timed_out"] = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            limit_timer = threading.Timer(RESEARCH_TIMEOUT_SECONDS, too_long)
            limit_timer.daemon = True
            limit_timer.start()
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    text = "".join(ch if ch.isprintable() else " " for ch in line.rstrip("\n"))[:500]
                    if text.strip():
                        lines.append(text)
                        del lines[:-MAX_OUTPUT_LINES]
                code = process.wait(timeout=60)
            finally:
                limit_timer.cancel()
            if state.get("stopped"):
                reason = present_lookup.INTERRUPTED
            elif state.get("timed_out"):
                reason = present_lookup.RESEARCH_TOO_LONG
            elif code == 0:
                if extras is not None:
                    self.sandbox_refresh()           # (the copies this run made for its proven tests are known from here on)
                # The pack this run made: the one pack made here that is ready to install now (none was before the run
                # started, or the run would not have started), and it holds only advisories of this run.
                with self.db() as db:
                    chain = self._waiting_chain(db)
                mine = chain[0] if chain and chain[0].made_here and {a["id"] for a in chain[0].pack["advisories"]} <= set(ids) else None
                if mine is not None:
                    self.install_pack(mine.version)
                    pack_version = mine.version
                else:
                    reason = present_lookup.RESEARCH_NO_PACK
            else:
                # (what the command said last: "No test pack was made: ..." when it settled nothing, or why it stopped)
                reason = next((line.strip() for line in reversed(lines) if line.strip()), present_lookup.RESEARCH_STOPPED)[:600]
        except Exception as exc:        # (the end row must be written whatever went wrong; never the error's own words)
            reason = f"The research run stopped ({exc.__class__.__name__})."
        finally:
            try:
                with self._otto_lock, self.db() as db:
                    db.add(OttoResearchRow(plan_id=plan_id, run_key=run_key, kind="finished", at=_now(), by=None, lookup_id=lookup_id,
                                           advisories=ids, live=bool(live), limit_nano=int(limit_nano), installed_first=installed_first,
                                           exit_code=code, pack_version=pack_version, output=list(lines)[-MAX_OUTPUT_LINES:], reason=reason,
                                           sandbox=extras is not None, spent_nano=self._counted_spent(extras, live, limit_nano)))
                    db.commit()
            finally:
                self._research_live.pop(row_id, None)

    def wait_until_research_done(self, timeout: float = 3600.0) -> None:
        for state in list(self._research_live.values()):
            thread = state.get("thread")
            if thread is not None:
                thread.join(timeout)
                if thread.is_alive():
                    raise TimeoutError("The research run did not finish in time.")

    # ---------------------------------------------------------------- the view, and the evidence

    def lookup_view(self, plan_id: int) -> dict:
        """The block "New advisories" of the Advisories page. Worked out on every read from what was kept."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            libraries = self._named_libraries(db, plan)
            packages, skipped = self._askable(libraries)
            look = self._latest_lookup(db, plan_id)
            rows = self._lookup_rows(db, plan, look) if look is not None else []
            research_state = self._research_state(db, plan_id)
            eligible = [r for r in rows if r["state"] == "new"]
            blocked = self._research_blocked(db, plan_id, eligible)
            closed = self._closed_at(plan_id) is not None
            waiting_packs = [pack.version for pack in self._waiting_chain(db) if not pack.made_here]
            live, limit = self.otto_live_ready(), self._otto_limit(db)
            sandbox = self.sandbox_on()
            if sandbox:      # (the limit the box names is the one the run will be given: see `start_research`)
                limit = self.sandbox_run_limit() if live else self.sandbox_limits()[0]
            left_open = self._left_open(research_state)
        source = self._advisory_source()
        return present_lookup.lookup_view(
            libraries=libraries, packages=[p.words for p in packages], skipped=skipped, recorded=isinstance(source, lookup.RecordedSource),
            closed=closed, look=({"at": look.at, "by": look.by, "source": look.source, "sent": look.sent, "asked": look.asked,
                                  "left_out": look.left_out, "cut": look.cut} if look is not None else None),
            rows=rows, eligible=len(eligible), research_blocked=blocked, waiting_packs=waiting_packs, left_open=left_open, live=live,
            limit=f"{limit / model.NANO:.2f}", isolated=self.mode.name == "isolated", sandbox=sandbox,
            sandbox_line=self.sandbox_research_line() if sandbox else None,
            run=({"started_at": research_state["run"].at, "advisories": research_state["run"].advisories, "live": research_state["run"].live,
                  "running": research_state["live"], "lines": research_state["lines"],
                  "installed_first": list(research_state["run"].installed_first or []),
                  "end": ({"at": research_state["end"].at, "exit_code": research_state["end"].exit_code,
                           "pack_version": research_state["end"].pack_version, "reason": research_state["end"].reason}
                          if research_state["end"] is not None else None)} if research_state["run"] is not None else None))

    @staticmethod
    def _left_open(research_state: dict) -> dict[str, str]:
        """What the newest finished run left for a later run, and why: advisory id -> one sentence. Read from what the
        research command said, in lines of one exact form (`present_lookup.LEFT_PREFIX`); only for advisories that were
        handed to that run. What the command said is data: a line in another form is not read."""
        run, end = research_state.get("run"), research_state.get("end")
        if run is None or end is None:
            return {}
        handed = {str(a) for a in run.advisories or []}
        out: dict[str, str] = {}
        for line in end.output or []:
            text = str(line).strip()
            if not text.startswith(present_lookup.LEFT_PREFIX):
                continue
            advisory_id, _, why = text[len(present_lookup.LEFT_PREFIX):].partition(": ")
            if advisory_id in handed and why.strip():
                out[advisory_id] = why.strip()[:400]
        return out

    def lookups_evidence(self, plan_id: int) -> dict:
        """For the evidence file: every look of this assessment (what was asked, of which source, the fingerprint of
        each answer, the advisories found) and every research run (which advisories, with Live Otto or not, how it
        ended, the pack it made). Records only: a result is never in them."""
        with self.db() as db:
            looks = db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id)).all()
            runs = self._research_rows(db, plan_id)
            return {"looks": [{"number": n, "at": r.at, "by": r.by, "source": r.source, "sent": list(r.sent or []),
                               "asked": list(r.asked or []), "left_out": r.left_out, "cut": bool(r.cut),
                               "found": [{"id": f["advisory"]["id"], "library": f["advisory"]["package"]["name"],
                                          "published": f["advisory"]["published"], "source_sha256": f["advisory"]["sources"][0]["sha256"]}
                                         for f in r.found or []]} for n, r in enumerate(looks, start=1)],
                    "research": [{"run": r.run_key, "what": r.kind, "at": r.at, "by": r.by, "advisories": list(r.advisories or []),
                                  "live": bool(r.live), "installed_first": list(r.installed_first or []), "exit_code": r.exit_code,
                                  "pack_version": r.pack_version, "reason": r.reason} for r in runs],
                    "note": ("A look reads published advisories from a public source: it sends package names only, and what comes back "
                             "is data. A research run tries a test on public copies before anything is proposed; its proof is in the "
                             "test pack it made, which is in this file with its signature.")}


def iso_or_none(value) -> str | None:
    return iso(value) if value is not None else None
