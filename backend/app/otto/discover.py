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
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select

from app.db import ImportRow, OttoLookupRow, OttoResearchRow, PlanRow, iso
from app.engine import research
from app.errors import Conflict
from app.knowledge.base import knowledge_base
from app.knowledge.versions import read_version
from app.otto import harness, lookup, model, packs
from app.present import lookup as present_lookup
from app.run import components

BACKEND = Path(__file__).resolve().parents[2]
SNAPSHOT_SCHEMA = "isogeny.advisory-snapshot/1"
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
    _scan_updates: Callable[..., tuple]
    _trusted_pack_keys: Callable[..., dict]
    install_pack: Callable[..., dict]
    otto_live_ready: Callable[..., bool]
    _otto_limit: Callable[..., int]
    decision_name: Callable[..., str]

    def _init_discover(self) -> None:
        self._research_lock = threading.Lock()
        self._research_live: dict[int, dict] = {}        # research row id -> {"lines": [...], "thread": Thread}

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

    def look_for_advisories(self, plan_id: int) -> dict:
        """Ask the source once about every library this assessment names, and keep what came back. Nothing runs."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            libraries = self._named_libraries(db, plan)
        packages, _ = self._askable(libraries)
        if not packages:
            raise Conflict(present_lookup.LOOK_NOTHING_TO_ASK)
        source = self._advisory_source()
        try:
            look = lookup.read_source(source, packages)
        except lookup.LookupError_ as exc:
            raise Conflict(str(exc)) from None
        found = [{"advisory": f.advisory, "ranges": f.ranges, "versions": f.versions[:200], "record_id": f.record_id} for f in look["found"]]
        with self._otto_lock, self.db() as db:
            db.add(OttoLookupRow(plan_id=plan_id, at=_now(), by=self.decision_name(), source=look["source"], sent=look["sent"],
                                 asked=look["asked"], found=found, left_out=int(look["left_out"]), cut=bool(look["cut"])))
            db.commit()
        return self.advisories_view(plan_id)      # type: ignore[attr-defined]

    # ---------------------------------------------------------------- what a look found, as it stands now

    def _latest_lookup(self, db, plan_id: int) -> OttoLookupRow | None:
        return db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id.desc()).limit(1)).first()

    def _packs_by_advisory(self, db, upto=None) -> tuple[dict[str, dict], dict[str, str]]:
        """(advisories in installed packs by id and by other name: {"version", "entry"}; advisories in a built-in pack
        that is not installed yet: id -> that pack's version)."""
        installed: dict[str, dict] = {}
        for _, pack in self._installed_packs(db, upto):
            for entry in pack.pack["advisories"]:
                for name in (entry["id"], *entry.get("aliases", [])):
                    installed[str(name).upper()] = {"version": pack.version, "entry": entry}
        waiting: dict[str, str] = {}
        have = {pack.fingerprint for _, pack in self._installed_packs(db)}
        found, _ = packs.found_in(self.settings.otto_updates, self._trusted_pack_keys())
        for pack in sorted(found, key=lambda p: packs.version_key(p.version)):
            if pack.fingerprint in have:
                continue
            for entry in pack.pack["advisories"]:
                for name in (entry["id"], *entry.get("aliases", [])):
                    waiting.setdefault(str(name).upper(), pack.version)
        return installed, waiting

    def _lookup_rows(self, db, plan: PlanRow, row: OttoLookupRow) -> list[dict]:
        """Each advisory of one look with where it stands now: in a pack, new and able to be tried, or not."""
        libraries = self._named_libraries(db, plan)
        installed, waiting = self._packs_by_advisory(db, self._closed_at(plan.id))
        out = []
        for item in row.found or []:
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
            out.append({"advisory": advisory, "library": library, "fits": fits, "state": state, "why": why,
                        "pack": in_pack["version"] if in_pack else in_waiting, "entry": in_pack["entry"] if in_pack else None})
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
        if fixed is None:
            return "no_test", present_lookup.NO_FIXED_VERSION
        if fixed not in have or have.index(fixed) == 0 or read_version(fixed) is None:
            return "no_test", present_lookup.no_copy_of_version(library, fixed, have)
        return "new", None

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
        if any(v.get("thread") is not None and v["thread"].is_alive() for v in self._research_live.values()):
            return present_lookup.RESEARCH_RUNNING
        if not eligible:
            return present_lookup.RESEARCH_NOTHING
        if self.mode.name != "isolated":
            return present_lookup.RESEARCH_NEEDS_ISOLATED
        return None

    def start_research(self, plan_id: int) -> dict:
        """Design and prove tests for the new advisories of the newest look, in the background. The built-in packs
        that are not installed yet are installed first, in order: a pack made here follows the newest one."""
        with self.db() as db:
            plan = self._plan(db, plan_id)
            look = self._latest_lookup(db, plan_id)
            rows = self._lookup_rows(db, plan, look) if look is not None else []
            eligible = [r for r in rows if r["state"] == "new"]
            blocked = self._research_blocked(db, plan_id, eligible)
            if blocked or look is None:          # no look means nothing can be tried, which is one of the reasons above
                raise Conflict(blocked or present_lookup.RESEARCH_NOTHING)
            look_id = look.id
            live, limit = self.otto_live_ready(), self._otto_limit(db)
        installed_first = self._install_waiting_packs()
        run_key = f"{plan_id}-{_now()}"
        inbox = Path(self.settings.data_dir) / "otto-inbox" / run_key.replace(":", "")
        inbox.mkdir(parents=True, exist_ok=True)
        ids = [r["advisory"]["id"] for r in eligible]
        snapshot = {"schema": SNAPSHOT_SCHEMA, "snapshot": _now()[:10],
                    "about": "Advisories read by Look for new advisories. Every excerpt is a piece of the publisher's own text.",
                    "advisories": [r["advisory"] for r in eligible]}
        (inbox / "advisories.json").write_text(json.dumps(snapshot, indent=1, ensure_ascii=False), encoding="utf-8")
        with self._otto_lock, self.db() as db:
            started = OttoResearchRow(plan_id=plan_id, run_key=run_key, kind="started", at=_now(), by=self.decision_name(),
                                      lookup_id=look_id, advisories=ids, live=bool(live), limit_nano=int(limit),
                                      installed_first=installed_first, exit_code=None, pack_version=None, output=[])
            db.add(started)
            db.commit()
            row_id = started.id
        state: dict = {"lines": [], "thread": None}
        self._research_live[row_id] = state
        thread = threading.Thread(target=self._run_research, name=f"otto-research-{row_id}", daemon=True,
                                  args=(row_id, plan_id, run_key, inbox, live, limit, look_id, ids, installed_first))
        state["thread"] = thread
        thread.start()
        return self.advisories_view(plan_id)      # type: ignore[attr-defined]

    def _install_waiting_packs(self) -> list[str]:
        """Install every built-in pack that is ready and not installed yet, oldest first. Returns their versions."""
        done: list[str] = []
        for _ in range(20):
            with self.db() as db:
                update, _, _ = self._scan_updates(db)
            if update is None or update.made_here:
                break
            self.install_pack(update.version)
            done.append(update.version)
        return done

    def _research_command(self, inbox: Path, live: bool, limit_nano: int) -> list[str]:
        dollars = f"{limit_nano / model.NANO:.2f}"
        command = [sys.executable, "-m", "ottolab.build", "next", "--inbox", str(inbox), "--data-dir", str(self.settings.data_dir),
                   "--shipped", str(self.settings.otto_updates), "--recorded", str(self.settings.otto_recorded), "--limit", dollars]
        return command + (["--live"] if live else [])

    def _run_research(self, row_id: int, plan_id: int, run_key: str, inbox: Path, live: bool, limit_nano: int, lookup_id: int,
                      ids: list[str], installed_first: list[str]) -> None:
        """The research command, as a process of its own, with what it says kept line by line. Then the pack it made
        is installed. Whatever happens, one end row is written."""
        state = self._research_live[row_id]
        lines: list[str] = state["lines"]
        code, pack_version, reason = None, None, None
        try:
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(self._research_command(inbox, live, limit_nano), cwd=str(BACKEND), env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert process.stdout is not None
            for line in process.stdout:
                text = "".join(ch if ch.isprintable() else " " for ch in line.rstrip("\n"))[:500]
                if text.strip():
                    lines.append(text)
                    del lines[:-MAX_OUTPUT_LINES]
            code = process.wait(timeout=RESEARCH_TIMEOUT_SECONDS)
            if code == 0:
                with self.db() as db:
                    update, _, _ = self._scan_updates(db)
                if update is not None and update.made_here:
                    self.install_pack(update.version)
                    pack_version = update.version
                else:
                    reason = present_lookup.RESEARCH_NO_PACK
            else:
                reason = next((line for line in reversed(lines) if line.strip()), present_lookup.RESEARCH_STOPPED)
        except Exception as exc:        # (the end row must be written whatever went wrong; never the error's own words)
            reason = f"The research run stopped ({exc.__class__.__name__})."
        finally:
            try:
                with self._otto_lock, self.db() as db:
                    db.add(OttoResearchRow(plan_id=plan_id, run_key=run_key, kind="finished", at=_now(), by=None, lookup_id=lookup_id,
                                           advisories=ids, live=bool(live), limit_nano=int(limit_nano), installed_first=installed_first,
                                           exit_code=code, pack_version=pack_version, output=list(lines)[-MAX_OUTPUT_LINES:], reason=reason))
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
            waiting_packs = sorted(set(self._packs_by_advisory(db)[1].values()), key=packs.version_key)
            live, limit = self.otto_live_ready(), self._otto_limit(db)
        source = self._advisory_source()
        return present_lookup.lookup_view(
            libraries=libraries, packages=[p.words for p in packages], skipped=skipped, recorded=isinstance(source, lookup.RecordedSource),
            closed=closed, look=({"at": look.at, "by": look.by, "source": look.source, "sent": look.sent, "asked": look.asked,
                                  "left_out": look.left_out, "cut": look.cut} if look is not None else None),
            rows=rows, eligible=len(eligible), research_blocked=blocked, waiting_packs=waiting_packs, live=live,
            limit=f"{limit / model.NANO:.2f}", isolated=self.mode.name == "isolated",
            run=({"started_at": research_state["run"].at, "advisories": research_state["run"].advisories, "live": research_state["run"].live,
                  "running": research_state["live"], "lines": research_state["lines"],
                  "end": ({"at": research_state["end"].at, "exit_code": research_state["end"].exit_code,
                           "pack_version": research_state["end"].pack_version, "reason": research_state["end"].reason}
                          if research_state["end"] is not None else None)} if research_state["run"] is not None else None))

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
