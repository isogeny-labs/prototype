"""The application's actions (import, confirm an address, verify), used by the web API and the accuracy command."""
from __future__ import annotations

import ipaddress
import os
import threading
from pathlib import Path

from sqlalchemy import func, select

from . import auth, components, plain, runner
from .addresses import AddressError, is_loopback_ip, parse_address, resolve_all
from .changes import ChangesMixin
from .config import DEMO_CBOM, DEMO_CBOM_PORT, DEMO_HOSTNAME, Settings
from .db import (
    AddressRow, ClaimRow, ImportClearedRow, ImportRow, SkippedRow, VerifyRunRow, iso, make_session_factory, now_utc,
)
from .demo_server import DemoServer
from .extra_servers import ExtraServers, claims_match, is_multi_target_file
from .errors import BadRequest, Conflict, NotFound
from .evidence_export import EvidenceMixin, SigningKeyError, ensure_signing_key
from .fixes import FixesMixin
from .importers import ImportFileError, ParsedFile, parse_file
from .jobs import JobRunner
from .names import clean_text
from .research import RuleEngine
from .reviewer import RuleReviewer
from .testlab import TestLabMixin
from .verify import DemoContext, verify_claims

_swept = False  # containers left by an earlier crash are cleared once per process


def claim_json(c: ClaimRow) -> dict:
    return {"id": c.id, "ref": c.ref, "location": c.location, "location_kind": c.location_kind, "kind": c.kind,
            "claimed_value": c.claimed_value, "text": c.text, "source": c.source}


def address_json(a: AddressRow) -> dict:
    return {"address": a.address, "host": a.host, "port": a.port, "resolved_ip": a.resolved_ip,
            "is_loopback": a.is_loopback, "confirmed": a.confirmed, "error": a.error}


def import_json(i: ImportRow) -> dict:
    return {"id": i.id, "filename": i.filename, "format": i.format, "is_demo": i.is_demo,
            "claims": [claim_json(c) for c in i.claims], "addresses": [address_json(a) for a in i.addresses],
            "skipped": [{"name": s.name, "what": s.what, "source": s.source, "reason": s.reason} for s in i.skipped]}


def run_json(r: VerifyRunRow) -> dict:
    # A row stored before phase 3a-fixes has no plain sentence or notes of its own: it gets a plain fallback.
    results = [{**res, "summary": res.get("summary") or plain.verify_fallback(res.get("result", ""), res.get("found", "")),
                "also_noticed": res.get("also_noticed") or []} if isinstance(res, dict) else res for res in r.results or []]
    return {"id": r.id, "import_id": r.import_id, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "results": results}


class Lab(TestLabMixin, ChangesMixin, FixesMixin, EvidenceMixin):
    def __init__(self, settings: Settings, db_path: Path | None = None, allow_external_demo_server: bool = False):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings.data_dir, 0o700)  # the data folder (database, demo test key) is for this user only
        except OSError:
            pass
        self.db = make_session_factory(db_path or settings.db_path)
        self.demo = DemoServer(settings.data_dir, settings.demo_tls_port)
        self.extra = ExtraServers(settings.extra_ports)  # the multi-target demo file's test servers, started on import only
        self.allow_external_demo_server = allow_external_demo_server
        self._verify_lock = threading.Lock()
        self._stopping = False  # set when the app is closing: a test still unfinished then writes no record
        self.resolver = resolve_all  # tests replace this to simulate a name that changes
        # Phase 2: the mode is decided once, here, and recorded in every run. It never changes while the app runs.
        self.mode = runner.detect_mode(settings)
        self.component_runner = runner.ComponentRunner(self.mode)
        self.jobs = JobRunner(settings.max_jobs)
        self.engine = RuleEngine(settings.speed_rounds, settings.speed_repeats)   # proposes and designs tests
        self.reviewer = RuleReviewer()                                             # the separate review step
        self._init_testlab()
        self._init_changes()
        try:
            # The evidence signing key: made once, on first start, kept in the data folder (mode 0600).
            ensure_signing_key(settings.data_dir)
        except (SigningKeyError, OSError):
            pass  # Download evidence then says plainly that the key could not be read

    def start(self) -> None:
        global _swept
        self._stopping = False
        self.demo.start()
        self.jobs.start()
        if self.mode.docker_running and not _swept:
            _swept = True
            runner.sweep_stale_containers()

    def stop(self) -> None:
        self.jobs.wait_idle(20)  # let a running test write its record; then stop
        # A test still unfinished now is interrupted, not answered: it must write nothing, or it would record
        # "the server did not answer" about a demo server that we ourselves are about to stop.
        self._stopping = True
        self.jobs.stop()
        self.demo.stop()
        self.extra.stop()

    # ---------------------------------------------------------------- session / login

    def session_json(self, token: str | None) -> dict:
        with self.db() as db:
            return {
                "setup_required": auth.setup_required(db),
                "logged_in": auth.session_valid(db, token),
                "mode": self.mode.name,
                "mode_line": self.mode.line,
                "demo_server": {"address": self.settings.demo_address, "running": self.demo.running,
                                "error": self.demo.error},
            }

    # ---------------------------------------------------------------- import

    def import_demo(self) -> dict:
        data = DEMO_CBOM.read_bytes()
        if self.settings.demo_tls_port != DEMO_CBOM_PORT:
            # The demo server was moved with EVIDENCE_LAB_DEMO_TLS_PORT; point the demo file at the same port.
            data = data.replace(f"{DEMO_HOSTNAME}:{DEMO_CBOM_PORT}".encode(), self.settings.demo_address.encode())
        return self._store(DEMO_CBOM.name, parse_file(DEMO_CBOM.name, data), is_demo=True)

    def _targets_demo(self, parsed: ParsedFile) -> bool:
        """Does this file point at our own demo: the demo TLS server's address, or a registered demo component?"""
        for c in parsed.claims:
            if c.location_kind == "server" and c.location == self.settings.demo_address:
                return True
            if c.location_kind == "software" and components.lookup(c.detail.get("component"), c.detail.get("version")):
                return True
        return False

    def import_file(self, filename: str, data: bytes) -> dict:
        shown = clean_text(os.path.basename((filename or "").replace("\\", "/")), 120) or "uploaded file"
        parsed = parse_file(shown, data)
        stored = self._store(shown, parsed, is_demo=self._targets_demo(parsed))
        if is_multi_target_file(data, self.settings.demo_tls_port, self.settings.extra_ports):
            # Only our own multi-target demo file starts the three test servers. A taken port is said, never fatal.
            problems = self.extra.start()
            ports = ", ".join(str(p) for p in self.settings.extra_ports)
            stored["notices"] = problems or [f"Demo data: started the three demo test servers for this file on this computer (ports {ports})."]
        return stored

    def ensure_extra_servers(self, import_id: int) -> None:
        """If this import is the multi-target demo file, make sure its test servers are running (after a restart
        of the app they are not). Anything else starts nothing."""
        if len(self.extra.running) == len(self.settings.extra_ports):
            return
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims] if imp is not None else []
        if claims and claims_match(claims, self.settings.demo_tls_port, self.settings.extra_ports):
            self.extra.start()

    def extra_identity(self, import_id: int) -> tuple[dict | None, dict | None]:
        """For the multi-target demo file: (port -> our test server's fingerprint or None, port -> why it is not
        running). (None, None) for any other import: then those ports are checked like any other address."""
        with self.db() as db:
            imp = db.get(ImportRow, import_id)
            claims = [(c.location, c.kind, c.claimed_value) for c in imp.claims] if imp is not None else []
        if not claims or not claims_match(claims, self.settings.demo_tls_port, self.settings.extra_ports):
            return None, None
        return ({p: self.extra.fingerprints.get(p) if p in self.extra.running else None for p in self.settings.extra_ports},
                dict(self.extra.problems))

    def _store(self, filename: str, parsed: ParsedFile, is_demo: bool) -> dict:
        with self.db() as db:
            row = ImportRow(filename=filename, format=parsed.format, is_demo=is_demo)
            seen: dict[str, AddressRow] = {}
            for c in parsed.claims:
                row.claims.append(ClaimRow(ref=c.ref, location=c.location, location_kind=c.location_kind, kind=c.kind,
                                           claimed_value=c.claimed_value, text=c.text, source=c.source, detail=c.detail))
                if c.location_kind == "server" and c.location not in seen:
                    seen[c.location] = self._new_address(c.location, c.detail["host"], c.detail["port"])
                    row.addresses.append(seen[c.location])
            for s in parsed.skipped:
                row.skipped.append(SkippedRow(name=s.name, what=s.what, source=s.source, reason=s.reason))
            db.add(row)
            db.commit()
            return import_json(row)

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
            return import_json(row)

    def confirm_address(self, import_id: int, address: str, confirmed: bool) -> dict:
        try:
            hp = parse_address(address)
        except AddressError as exc:
            raise BadRequest(f"{exc}.", field="address") from exc
        with self.db() as db:
            row = db.scalars(select(AddressRow).where(AddressRow.import_id == import_id,
                                                      AddressRow.address == hp.address)).first()
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
            demo = DemoContext(is_demo_import=imp.is_demo, host=DEMO_HOSTNAME, port=self.settings.demo_tls_port,
                               running=self.demo.running, error=self.demo.error, fingerprint=self.demo.fingerprint,
                               allow_external=self.allow_external_demo_server and self.demo.port_in_use,
                               extra=extra, extra_problems=problems)
            outcomes = verify_claims(list(imp.claims), list(imp.addresses), demo, resolver=self.resolver,
                                     component_runner=self.component_runner)
            results = [{"claim_id": c.id, "claim": claim_json(c), **o} for c, o in zip(imp.claims, outcomes)]
            run = VerifyRunRow(import_id=imp.id, started_at=started, finished_at=now_utc(), results=results)
            db.add(run)
            db.commit()
            return run_json(run)

    def latest_verify(self, import_id: int) -> dict:
        with self.db() as db:
            run = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == import_id)
                             .order_by(VerifyRunRow.id.desc()).limit(1)).first()
            if run is None:
                raise NotFound("These claims have not been verified yet.")
            return run_json(run)


__all__ = ["Lab", "NotFound", "BadRequest", "Conflict", "ImportFileError"]
