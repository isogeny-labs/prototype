"""The application's actions (import, confirm an address, verify), used by the web API and the accuracy command."""

from __future__ import annotations

import dataclasses
import hashlib
import ipaddress
import os
import threading
from pathlib import Path

from sqlalchemy import func, select

from app.names import join_and as names_join_and
from app import auth
from app.run import components
from app.servers import lab_nginx
from app.servers import lab_servers
from app.servers import migration_servers
from app.present import plain
from app.present import source as present_source
from app.present import migration as present_migration
from app import real_libraries
from app.run import runner
from app.checks.addresses import AddressError, is_loopback_ip, parse_address, resolve_all
from app.changewatch.state import ChangeWatchMixin
from app.changewatch.views import ChangeWatchViewMixin
from app.changewatch.clock import WatchClockMixin
from app.changewatch.watchlist import WatchListMixin
from app.whatif.facts import WhatIfMixin
from app.impact.reach import ImpactMixin
from app.fixes.changes import ChangesMixin
from app.infra.cache import make_cache
from app.infra.storage import make_store, put_quietly, safe_name
from app.config import DEMO_CBOM, DEMO_CBOM_PORT, DEMO_HOSTNAME, Settings
from app.db import (
    AddressRow,
    AssessmentRow,
    ClaimRow,
    ImportClearedRow,
    ImportFileRow,
    ImportRow,
    SkippedRow,
    SystemSettingRow,
    VerifyRunRow,
    iso,
    make_session_factory,
    now_utc,
)
from app.servers.demo_server import DemoServer
from app.servers.extra_servers import ExtraServers, claims_match, is_multi_target_file
from app.errors import BadRequest, Conflict, NotFound
from app.evidence.export import EvidenceMixin, SigningKeyError, ensure_signing_key
from app.ledger.checks import LedgerMixin
from app.ledger.relations import RelationsMixin
from app.projects.overview import OverviewMixin
from app.fixes.views import FixesMixin
from app.migration.state import MigrationMixin
from app.dependencies.state import DependenciesMixin
from app.migration.system_changes import LAB_NGINX_SETTINGS, SystemChangesMixin
from app.importer.common import ImportFileError, ParsedFile
from app.importer.reader import parse_file
from app.jobs import JobRunner
from app.names import clean_text
from app.engine.research import RuleEngine
from app.engine.reviewer import RuleReviewer
from app.lab.testlab import TestLabMixin
from app.lab.actions import ActionsMixin, recorded
from app.assistant.engine import CopilotEngine, RuleCopilot
from app.lab.said import SaidMixin
from app.otto.discover import DiscoverMixin
from app.otto.engine import OttoEngine
from app.otto.proposals import ProposalsMixin
from app.otto.state import OttoMixin
from app.sandbox import copies as sandbox_copies
from app.sandbox.state import SandboxMixin
from app.projects.store import ProjectsMixin
from app.checks.verify import DemoContext, verify_claims

_swept = False  # containers left by an earlier crash are cleared once per process


def claim_json(c: ClaimRow) -> dict:
    return {
        "id": c.id,
        "ref": c.ref,
        "location": c.location,
        "location_kind": c.location_kind,
        "kind": c.kind,
        "claimed_value": c.claimed_value,
        "text": c.text,
        "source": c.source,
    }


def address_json(a: AddressRow) -> dict:
    return {
        "address": a.address,
        "host": a.host,
        "port": a.port,
        "resolved_ip": a.resolved_ip,
        "is_loopback": a.is_loopback,
        "confirmed": a.confirmed,
        "error": a.error,
    }


def import_json(i: ImportRow, settings: list[dict] | None = None) -> dict:
    """`settings`: the system settings the file gave (phase 4a), one line per system, for the Import screen."""
    return {
        "id": i.id,
        "filename": i.filename,
        "format": i.format,
        "is_demo": i.is_demo,
        "claims": [claim_json(c) for c in i.claims],
        "addresses": [address_json(a) for a in i.addresses],
        "skipped": [{"name": s.name, "what": s.what, "source": s.source, "reason": s.reason} for s in i.skipped],
        "settings_title": present_migration.FILE_SETTINGS_TITLE,
        "settings": settings or [],
        # where a claim came from (22 November 2026): the file; Verify then checks it
        "claim_source_tag": present_source.of_claim(i.filename),
    }


# Phase 5c: Verify is unchanged (its trust gap is the next phase), and Otto proposes nothing on it yet. The page says so.
VERIFY_OTTO_NOTE = (
    "Nothing is proposed here yet. In this version the proposed checks are for signing programs and libraries; "
    "checks of servers come in a later phase. Verify works as before."
)


def run_json(r: VerifyRunRow) -> dict:
    # A row stored before phase 3a-fixes has no plain sentence or notes of its own: it gets a plain fallback.
    # (since 22 November 2026 each result also says where it came from: live for a server, lab for a program, the file
    # where it couldn't be checked; worked out on every read, never stored)
    results = [
        {
            **res,
            "summary": res.get("summary") or plain.verify_fallback(res.get("result", ""), res.get("found", "")),
            "also_noticed": res.get("also_noticed") or [],
            "source_tag": present_source.of_verify(res),
        }
        if isinstance(res, dict)
        else res
        for res in r.results or []
    ]
    return {
        "id": r.id,
        "import_id": r.import_id,
        "started_at": iso(r.started_at),
        "finished_at": iso(r.finished_at),
        "results": results,
        "otto_note": VERIFY_OTTO_NOTE,
    }


@recorded  # who did what (design refactor, decision I): the presses listed in app/lab/actions.py leave a row
class Lab(
    TestLabMixin,
    ChangesMixin,
    FixesMixin,
    MigrationMixin,
    SystemChangesMixin,
    DependenciesMixin,
    EvidenceMixin,
    ProjectsMixin,
    LedgerMixin,
    RelationsMixin,
    OverviewMixin,
    OttoMixin,
    ProposalsMixin,
    DiscoverMixin,
    SaidMixin,
    ChangeWatchMixin,
    ChangeWatchViewMixin,
    WhatIfMixin,
    ImpactMixin,
    SandboxMixin,
    WatchListMixin,
    WatchClockMixin,
    ActionsMixin,
):
    def __init__(self, settings: Settings, db_path: Path | None = None, allow_external_demo_server: bool = False):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings.data_dir, 0o700)  # the data folder (database, demo test key) is for this user only
        except OSError:
            pass
        factory = make_session_factory(db_path or settings.database)
        self.db = factory
        self.db_engine = factory.kw["bind"]  # hosting: the health check pings it; stop() gives its connections back
        # Hosting (app/infra/): a cache (Redis, or memory) and, when one is named, a place for copies of stored files
        # (S3, GCS or a folder; None by default).
        self.cache = make_cache(settings.redis_url)
        self.store = make_store(settings.storage_url)
        self.adopt_unfiled_imports()  # phase 5a: imports from before projects existed get an assessment, so nothing disappears
        self.demo = DemoServer(settings.data_dir, settings.demo_tls_port)
        self.extra = ExtraServers(
            settings.extra_ports
        )  # the multi-target demo file's test servers, started on import only
        # The migration demo file's five test servers (phase 4a): also started only when that file is imported.
        self.migration_servers = migration_servers.MigrationServers(settings.migration_ports)
        # Phase 4b: a server an Apply changed starts again with the settings in force (they are kept in the records).
        self.migration_servers.settings_for = lambda port: self._settings_in_force(f"{DEMO_HOSTNAME}:{port}")
        # The lab nginx of demo/lab-nginx.csv (real nginx, isolated mode only), started only when that file is imported.
        self.lab_nginx_server = lab_nginx.LabNginx(settings.lab_nginx_port)
        self.allow_external_demo_server = allow_external_demo_server
        self._verify_lock = threading.Lock()
        self._stopping = False  # set when the app is closing: a test still unfinished then writes no record
        self.resolver = resolve_all  # tests replace this to simulate a name that changes
        # Phase 2: the mode is decided once, here, and recorded in every run. It never changes while the app runs.
        self.mode = runner.detect_mode(settings)
        # (its own copy of the table of real-library images: Sandbox research adds the images of this computer's copy
        #  sets to it while the switch is on, and nothing else about the mode ever changes)
        self.mode = dataclasses.replace(self.mode, real_images=dict(self.mode.real_images))
        self.component_runner = runner.ComponentRunner(self.mode)
        self.jobs = JobRunner(settings.max_jobs)
        # Proposes and designs tests. Since phase 5c the rule engine sits behind Otto's engine, which passes everything
        # to it unchanged and is asked first only for a code change after an advisory check failed.
        self.engine = OttoEngine(RuleEngine(settings.speed_rounds, settings.speed_repeats), self)
        self.reviewer = RuleReviewer()  # the separate review step
        # Phase 6a: the Otto panel. Rule-based, behind CopilotEngine; it reads and decides nothing.
        self.copilot: CopilotEngine = RuleCopilot()
        self._init_actions()  # a job queued by a press carries it; the rows a press adds are noted
        self._init_testlab()
        self._init_changes()
        self._init_otto()
        self._init_discover()  # phase 6: Look for new advisories, and the research run it can start
        self._init_watch_clock()  # sandbox research: the Watch list's clock (it runs only on a marked computer, with the switch on)
        try:
            # The evidence signing key: made once, on first start, kept in the data folder (mode 0600).
            ensure_signing_key(settings.data_dir)
        except (SigningKeyError, OSError):
            pass  # Download evidence then says plainly that the key could not be read

    def start(self) -> None:
        global _swept
        self._stopping = False
        applied = self._settings_in_force(
            self.settings.demo_address
        )  # phase 4b: an Apply to the demo server stays in force
        if applied:
            self.demo.versions = tuple(applied.get("versions") or self.demo.versions)
        self.demo.start()
        self.jobs.start()
        sandbox_copies.register(self.settings.sandbox_dir, self.sandbox_on)  # (seen only while the switch is on)
        self.sandbox_refresh()
        self.watch_clock_start()
        if self.mode.docker_running and not _swept:
            _swept = True
            runner.sweep_stale_containers()

    def stop(self) -> None:
        self.jobs.wait_idle(20)  # let a running test write its record; then stop
        # A test still unfinished now is interrupted, not answered: it must write nothing, or it would record
        # "the server did not answer" about a demo server that we ourselves are about to stop.
        self._stopping = True
        self.watch_clock_stop()
        sandbox_copies.unregister(self.settings.sandbox_dir)
        self.stop_research()  # (phase 6: a research run that is still going is ended with the app, never left behind)
        self.jobs.stop()
        self.demo.stop()
        self.extra.stop()
        self.migration_servers.stop()
        self.lab_nginx_server.stop()
        self.db_engine.dispose()  # hosting: give the database connections back (PostgreSQL counts them)

    # ---------------------------------------------------------------- session / login

    def session_json(self, token: str | None) -> dict:
        with self.db() as db:
            methods = self.settings.login_methods
            user = auth.session_user(db, token, methods)
            github = self.settings.github
            return {
                "setup_required": self.settings.password_login and auth.setup_required(db),
                "logged_in": auth.session_valid(db, token, methods),
                "login": {
                    "password": self.settings.password_login,
                    "github": github is not None,
                    "github_install_url": (
                        f"{github.web_url}/apps/{github.app_slug}/installations/new"
                        if github and github.app_slug
                        else None
                    ),
                },
                "user": ({"login": user.login, "name": user.name, "avatar_url": user.avatar_url} if user else None),
                "mode": self.mode.name,
                "mode_line": self.mode.line,
                "demo_server": {
                    "address": self.settings.demo_address,
                    "running": self.demo.running,
                    "error": self.demo.error,
                },
            }

    # ---------------------------------------------------------------- import

    def import_demo(self, assessment_id: int | None = None) -> dict:
        self.check_assessment_takes_a_file(assessment_id)
        data = DEMO_CBOM.read_bytes()
        if self.settings.demo_tls_port != DEMO_CBOM_PORT:
            # The demo server was moved with EVIDENCE_LAB_DEMO_TLS_PORT; point the demo file at the same port.
            data = data.replace(f"{DEMO_HOSTNAME}:{DEMO_CBOM_PORT}".encode(), self.settings.demo_address.encode())
        return self._with_in_force_notices(
            self._store(
                DEMO_CBOM.name, parse_file(DEMO_CBOM.name, data), is_demo=True, assessment_id=assessment_id, data=data
            )
        )

    def _with_in_force_notices(self, stored: dict) -> dict:
        """Phase 4b: a change this app applied to one of our own servers stays in force until it is rolled back, also
        for a new import of the same file. Say so on Import, so its results are not a surprise."""
        notes = []
        for entry in stored.get("addresses") or []:
            settings = self._settings_in_force(entry["address"])
            if settings is not None:
                notes.append(
                    f"Demo data: a change this app applied to {entry['address']} is still in force (TLS "
                    f"{lab_servers.versions_words(settings)}; key exchange {lab_servers.groups_words(settings)}). Its results "
                    "show it as changed until it is rolled back: Roll back is in its change box."
                )
        if notes:
            stored["notices"] = list(stored.get("notices") or []) + notes
        return stored

    def _real_notice(self, parsed: ParsedFile) -> str | None:
        """One line on Import when the file names real libraries (phase 4c): where they run, or plainly why they can't."""
        names, families = [], []
        for c in parsed.claims:
            family = (
                real_libraries.family_of(c.detail.get("component"), c.detail.get("version"))
                if c.location_kind == "software"
                else None
            )
            if family is not None and c.location not in names:
                names.append(c.location)
                families.append(family)
        if not names:
            return None
        listed = names_join_and(names)
        if self.mode.name != "isolated":
            return (
                f"Real software: {listed}. These are real libraries from outside, not demo data. They run only in isolated mode "
                "(Docker), and this run is in demo mode, so their claims can't be checked and their tests can't run here. "
                "Nothing of theirs is ever run as a local program."
            )
        missing = [real_libraries.family_label(f) for f in dict.fromkeys(families) if not self.mode.real_images.get(f)]
        if missing:
            return (
                f"Real software: {listed}. These are real libraries from outside, not demo data. The container "
                f"{'image' if len(missing) == 1 else 'images'} for {names_join_and(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} not prepared on this computer, so "
                f"{'that library' if len(missing) == 1 else 'those libraries'} can't run; ./run-demo.sh prepares "
                f"{'it' if len(missing) == 1 else 'them'} (it needs internet once). The others run isolated."
            )
        return (
            f"Real software: {listed}. These are real libraries from outside, not demo data. Each runs in its own locked-down "
            "container with no network."
        )

    def _targets_demo(self, parsed: ParsedFile) -> bool:
        """Does this file point at our own demo: the demo TLS server's address, or a registered demo component?"""
        for c in parsed.claims:
            if c.location_kind == "server" and c.location == self.settings.demo_address:
                return True
            if c.location_kind == "software" and components.lookup(c.detail.get("component"), c.detail.get("version")):
                return True
        return False

    def import_file(self, filename: str, data: bytes, assessment_id: int | None = None) -> dict:
        self.check_assessment_takes_a_file(assessment_id)
        shown = clean_text(os.path.basename((filename or "").replace("\\", "/")), 120) or "uploaded file"
        parsed = parse_file(shown, data)
        stored = self._store(
            shown,
            parsed,
            is_demo=self._targets_demo(parsed) or self._lab_nginx_data(data),
            assessment_id=assessment_id,
            data=data,
        )
        if is_multi_target_file(data, self.settings.demo_tls_port, self.settings.extra_ports):
            # Only our own multi-target demo file starts the three test servers. A taken port is said, never fatal.
            problems = self.extra.start()
            ports = ", ".join(str(p) for p in self.settings.extra_ports)
            stored["notices"] = problems or [
                f"Demo data: started the three demo test servers for this file on this computer (ports {ports})."
            ]
        if self._lab_nginx_data(data):
            # Phase 4b: real nginx in the lab, for Apply and Roll back on real server software. Isolated mode only.
            stored["notices"] = [self._start_lab_nginx()]
        real = self._real_notice(parsed)
        if real:  # phase 4c: real libraries named in the file, and whether they can run on this computer now
            stored["notices"] = list(stored.get("notices") or []) + [real]
        if migration_servers.is_migration_file(data, self.settings.migration_ports):
            # Only our own migration demo file starts its five test servers. One that can't start is said, never fatal.
            problems = self.migration_servers.start()
            ports = ", ".join(str(p) for p in self.settings.migration_ports)
            stored["notices"] = problems or [
                f"Demo data: started the five demo test servers for this file on this computer (ports {ports})."
            ]
        return self._with_in_force_notices(stored)

    def ensure_extra_servers(self, import_id: int) -> None:
        """If this import is the multi-target demo file, make sure its test servers are running (after a restart
        of the app they are not). Anything else starts nothing."""
        if len(self.extra.running) == len(self.settings.extra_ports) and len(self.migration_servers.running) == len(
            self.settings.migration_ports
        ):
            return
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims] if imp is not None else []
        if claims and claims_match(claims, self.settings.demo_tls_port, self.settings.extra_ports):
            self.extra.start()
        if self._is_migration_demo(import_id):
            self.migration_servers.start()

    def _lab_nginx_data(self, data: bytes) -> bool:
        """Is this exactly demo/lab-nginx.csv (with this app's lab nginx port written in)?"""
        return _normal_text(data) == _normal_text(self._lab_nginx_file())

    def _lab_nginx_file(self) -> bytes:
        from app.config import DEMO_DIR

        text = (DEMO_DIR / "lab-nginx.csv").read_text(encoding="utf-8")
        return text.replace("localhost:8461,", f"localhost:{self.settings.lab_nginx_port},").encode()

    def _is_lab_nginx_file(self, import_id: int) -> bool:
        """Is this stored import exactly demo/lab-nginx.csv (claims and settings rows)?"""
        from app.importer.reader import parse_file

        try:
            parsed = parse_file("lab-nginx.csv", self._lab_nginx_file())
        except Exception:
            return False
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            if imp is None:
                return False
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims]
            rows = db.scalars(
                select(SystemSettingRow).where(SystemSettingRow.import_id == imp.id, SystemSettingRow.source == "file")
            ).all()
            given = sorted((r.system_key.split(":", 1)[-1], r.field, r.value) for r in rows)
        return claims == [(c.location, c.kind, c.claimed_value) for c in parsed.claims] and given == sorted(
            (s.location, s.field, s.value) for s in parsed.settings
        )

    def _start_lab_nginx(self) -> str:
        """Start the lab nginx (with the settings an Apply put in force, if any). One plain sentence about it."""
        address = f"{DEMO_HOSTNAME}:{self.settings.lab_nginx_port}"
        usable, why = lab_nginx.ready(self.mode)
        if not usable:
            return f"{why} So {address} is not started, and its row will show Couldn't check. In demo mode, without Docker, it can't run."
        if self.lab_nginx_server.running:
            return f"Lab data: the lab nginx is running on {address} ({lab_nginx.NGINX_VERSION_WORDS}, in a locked-down container)."
        try:
            self.lab_nginx_server.start(self._settings_in_force(address) or LAB_NGINX_SETTINGS)
        except lab_nginx.NginxUnavailable as exc:
            return f"The lab nginx could not start: {exc} Its row will show Couldn't check."
        return f"Lab data: started the lab nginx on {address} ({lab_nginx.NGINX_VERSION_WORDS}, in a locked-down container)."

    def _is_migration_demo(self, import_id: int) -> bool:
        """Is this stored import exactly our migration demo file: the same claims AND the same settings rows? Only then
        are its five test servers ours to start and to vouch for. A file that merely makes the same claims is not."""
        ports = self.settings.migration_ports
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            if imp is None:
                return False
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims]
            if not claims or not migration_servers.claims_match(claims, ports):
                return False
            names = {"software:" + c.ref: c.location for c in imp.claims if c.location_kind == "software"}
            rows = db.scalars(
                select(SystemSettingRow).where(SystemSettingRow.import_id == imp.id, SystemSettingRow.source == "file")
            ).all()
            given = sorted((names.get(r.system_key, r.system_key.split(":", 1)[-1]), r.field, r.value) for r in rows)
        wanted = migration_servers.file_settings(ports)
        return bool(wanted) and given == wanted

    def extra_identity(self, import_id: int) -> tuple[dict | None, dict | None]:
        """For the multi-target demo file: (port -> our test server's fingerprint or None, port -> why it is not
        running). (None, None) for any other import: then those ports are checked like any other address."""
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims] if imp is not None else []
        if self._is_lab_nginx_file(import_id):
            port, nginx = self.settings.lab_nginx_port, self.lab_nginx_server
            if not nginx.running and lab_nginx.ready(self.mode)[0]:
                self._start_lab_nginx()
            return (
                {port: nginx.fingerprint if nginx.running else None},
                {port: lab_nginx.ready(self.mode)[1] or "The lab nginx is not running."} if not nginx.running else {},
            )
        if self._is_migration_demo(import_id):
            ours = self.migration_servers
            return (
                {p: ours.fingerprints.get(p) if p in ours.running else None for p in self.settings.migration_ports},
                dict(ours.problems),
            )
        if not claims or not claims_match(claims, self.settings.demo_tls_port, self.settings.extra_ports):
            return None, None
        return (
            {p: self.extra.fingerprints.get(p) if p in self.extra.running else None for p in self.settings.extra_ports},
            dict(self.extra.problems),
        )

    def _store(
        self,
        filename: str,
        parsed: ParsedFile,
        is_demo: bool,
        assessment_id: int | None = None,
        data: bytes | None = None,
    ) -> dict:
        with self.db() as db:
            row = ImportRow(filename=filename, format=parsed.format, is_demo=is_demo)
            seen: dict[str, AddressRow] = {}
            for c in parsed.claims:
                row.claims.append(
                    ClaimRow(
                        ref=c.ref,
                        location=c.location,
                        location_kind=c.location_kind,
                        kind=c.kind,
                        claimed_value=c.claimed_value,
                        text=c.text,
                        source=c.source,
                        detail=c.detail,
                    )
                )
                if c.location_kind == "server" and c.location not in seen:
                    seen[c.location] = self._new_address(c.location, c.detail["host"], c.detail["port"])
                    row.addresses.append(seen[c.location])
            for s in parsed.skipped:
                row.skipped.append(SkippedRow(name=s.name, what=s.what, source=s.source, reason=s.reason))
            db.add(row)
            db.flush()
            # Settings the file gives for a system (phase 4a). They are data for the migration plan: nothing checks them.
            # (A library the file names with more than one algorithm, phase 4c, is more than one system: each gets the setting.)
            refs: dict[str, list[str]] = {}
            for c in parsed.claims:
                if c.location_kind == "software":
                    refs.setdefault(c.location, []).append(c.ref)
            for setting in getattr(parsed, "settings", None) or []:
                keys = (
                    ["server:" + setting.location]
                    if setting.location_kind == "server"
                    else ["software:" + ref for ref in refs.get(setting.location, [])] or ["software:None"]
                )
                for key in keys:
                    db.add(
                        SystemSettingRow(
                            import_id=row.id, system_key=key, field=setting.field, value=setting.value, source="file"
                        )
                    )
            if data is not None:
                # Phase 5b: keep the file itself (data, at most 1 MB, never run), so Rerun as new assessment can read it again.
                db.add(
                    ImportFileRow(
                        import_id=row.id, filename=filename, data=bytes(data), sha256=hashlib.sha256(data).hexdigest()
                    )
                )
            # Phase 5a: the import goes into its assessment (or, with none given, the "Imported without a project" project).
            placed = self.attach_import(db, row.id, assessment_id)
            db.commit()
            if data is not None and self.store is not None:
                # Hosting: a copy in the file store named by EVIDENCE_LAB_STORAGE_URL, once the record is in the
                # database (which stays the record). None is named by default: then nothing is copied.
                put_quietly(
                    self.store,
                    f"imports/{hashlib.sha256(data).hexdigest()}/{safe_name(filename)}",
                    bytes(data),
                    "application/octet-stream",
                )
            return {
                **import_json(row, self._file_settings(db, row)),
                "assessment_id": placed,
                "otto": self.otto_found(db, row),
            }

    def assistant_view(self, assessment_id: int, page: str, item: str | None = None) -> dict:
        """Phase 6a: what the Otto panel shows beside one page of an assessment. A read: nothing is started or stored."""
        return self.copilot.read(self, assessment_id, page, item)

    def import_json_for(self, import_id: int) -> dict:
        with self.db() as db:
            row = db.get(ImportRow, import_id)
            if row is None:
                raise NotFound("That import does not exist.")
            return {**import_json(row, self._file_settings(db, row)), "otto": self.otto_found(db, row)}

    @staticmethod
    def _file_settings(db, imp: ImportRow) -> list[dict]:
        rows = db.scalars(
            select(SystemSettingRow)
            .where(SystemSettingRow.import_id == imp.id, SystemSettingRow.source == "file")
            .order_by(SystemSettingRow.id)
        ).all()
        names = {"software:" + c.ref: c.location for c in imp.claims if c.location_kind == "software"}
        # (once per system name: a library named with several algorithms carries the same setting for each)
        return present_migration.file_settings(
            list(
                dict.fromkeys((names.get(r.system_key, r.system_key.split(":", 1)[-1]), r.field, r.value) for r in rows)
            )
        )

    def _new_address(self, address: str, host: str, port: int) -> AddressRow:
        """No name lookups (DNS) when a file is imported: a file must not make this computer contact anything.
        Only IP addresses and exactly "localhost" (answered by this computer itself) are filled in now.
        Any other name is looked up when the user ticks the box for it (confirm_address)."""
        row = AddressRow(address=address, host=host, port=port, confirmed=False, resolved_ip=None, is_loopback=False)
        try:
            ip = str(ipaddress.ip_address(host))
            row.resolved_ip, row.is_loopback = ip, is_loopback_ip(ip)
        except ValueError:
            if host == "localhost":
                self._resolve_into(row)
        return row

    def _resolve_into(self, row: AddressRow) -> None:
        try:
            ip = self.resolver(row.host)[0]
            row.resolved_ip, row.is_loopback, row.error = ip, is_loopback_ip(ip), None
        except AddressError as exc:
            row.resolved_ip, row.is_loopback, row.error = None, False, f"{exc}."

    def clear_current_import(self) -> None:
        """After a failed upload there is no current import, so the previous file's claims don't come back."""
        with self.db() as db:
            latest = db.scalar(select(func.max(ImportRow.id)))
            if latest is not None and (db.scalar(select(func.max(ImportClearedRow.after_import_id))) or 0) < latest:
                db.add(ImportClearedRow(after_import_id=latest))
                db.commit()

    def current_import(self) -> dict:
        with self.db() as db:
            row = db.scalars(select(ImportRow).order_by(ImportRow.id.desc()).limit(1)).first()
            cleared = db.scalar(select(func.max(ImportClearedRow.after_import_id))) or 0
            if row is None or row.id <= cleared:
                raise NotFound("Nothing is imported at the moment.")
            placed = db.scalars(select(AssessmentRow.id).where(AssessmentRow.import_id == row.id)).first()
            return {
                **import_json(row, self._file_settings(db, row)),
                "assessment_id": placed,
                "otto": self.otto_found(db, row),
            }

    def confirm_address(self, import_id: int, address: str, confirmed: bool) -> dict:
        try:
            hp = parse_address(address)
        except AddressError as exc:
            raise BadRequest(f"{exc}.", field="address") from exc
        with self.db() as db:
            row = db.scalars(
                select(AddressRow).where(AddressRow.import_id == import_id, AddressRow.address == hp.address)
            ).first()
            if row is None:
                raise NotFound("That address is not in this import.")
            if confirmed:
                # Look the name up once, now, and pin the confirmation to host + port + this IP.
                self._resolve_into(row)
                row.confirmed = row.resolved_ip is not None
            else:
                row.confirmed = False
            db.commit()
            return address_json(row)

    # ---------------------------------------------------------------- verify

    def verify(self, import_id: int) -> dict:
        self.ensure_extra_servers(import_id)
        with self._verify_lock, self.db() as db:
            imp = db.get(ImportRow, import_id)
            if imp is None:
                raise NotFound("That import does not exist.")
            started = now_utc()
            extra, problems = self.extra_identity(import_id)
            demo = DemoContext(
                is_demo_import=imp.is_demo,
                host=DEMO_HOSTNAME,
                port=self.settings.demo_tls_port,
                running=self.demo.running,
                error=self.demo.error,
                fingerprint=self.demo.fingerprint,
                allow_external=self.allow_external_demo_server and self.demo.port_in_use,
                extra=extra,
                extra_problems=problems,
            )
            outcomes = verify_claims(
                list(imp.claims),
                list(imp.addresses),
                demo,
                resolver=self.resolver,
                component_runner=self.component_runner,
                mode=self.mode,
            )
            results = [{"claim_id": c.id, "claim": claim_json(c), **o} for c, o in zip(imp.claims, outcomes)]  # noqa: B905
            run = VerifyRunRow(import_id=imp.id, started_at=started, finished_at=now_utc(), results=results)
            db.add(run)
            db.commit()
            return run_json(run)

    def latest_verify(self, import_id: int) -> dict:
        with self.db() as db:
            run = db.scalars(
                select(VerifyRunRow)
                .where(VerifyRunRow.import_id == import_id)
                .order_by(VerifyRunRow.id.desc())
                .limit(1)
            ).first()
            if run is None:
                raise NotFound("These claims have not been verified yet.")
            return run_json(run)


def _normal_text(data: bytes) -> bytes:
    return b"\n".join(line.rstrip() for line in data.replace(b"\r\n", b"\n").strip().split(b"\n"))


__all__ = ["Lab", "NotFound", "BadRequest", "Conflict", "ImportFileError"]
