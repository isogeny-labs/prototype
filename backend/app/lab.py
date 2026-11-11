"""The application's actions (import, confirm an address, verify), used by the web API and the accuracy command."""
from __future__ import annotations

import ipaddress
import os
import threading
from pathlib import Path

from sqlalchemy import func, select

from . import auth, components
from .addresses import AddressError, is_loopback_ip, parse_address, resolve_all
from .config import DEMO_CBOM, DEMO_CBOM_PORT, DEMO_HOSTNAME, MODE, Settings
from .db import (
    AddressRow, ClaimRow, ImportClearedRow, ImportRow, SkippedRow, VerifyRunRow, iso, make_session_factory, now_utc,
)
from .demo_server import DemoServer
from .importers import ImportFileError, ParsedFile, parse_file
from .names import clean_text
from .verify import DemoContext, verify_claims


class NotFound(Exception):
    pass


class BadRequest(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message, self.field = message, field


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
    return {"id": r.id, "import_id": r.import_id, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "results": r.results}


class Lab:
    def __init__(self, settings: Settings, db_path: Path | None = None, allow_external_demo_server: bool = False):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings.data_dir, 0o700)  # the data folder (database, demo test key) is for this user only
        except OSError:
            pass
        self.db = make_session_factory(db_path or settings.db_path)
        self.demo = DemoServer(settings.data_dir, settings.demo_tls_port)
        self.allow_external_demo_server = allow_external_demo_server
        self._verify_lock = threading.Lock()
        self.resolver = resolve_all  # tests replace this to simulate a name that changes

    def start(self) -> None:
        self.demo.start()

    def stop(self) -> None:
        self.demo.stop()

    # ---------------------------------------------------------------- session / login

    def session_json(self, token: str | None) -> dict:
        with self.db() as db:
            return {
                "setup_required": auth.setup_required(db),
                "logged_in": auth.session_valid(db, token),
                "mode": MODE,
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
        return self._store(shown, parsed, is_demo=self._targets_demo(parsed))

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
        with self._verify_lock, self.db() as db:
            imp = db.get(ImportRow, import_id)
            if imp is None:
                raise NotFound("That import does not exist.")
            started = now_utc()
            demo = DemoContext(is_demo_import=imp.is_demo, host=DEMO_HOSTNAME, port=self.settings.demo_tls_port,
                               running=self.demo.running, error=self.demo.error, fingerprint=self.demo.fingerprint,
                               allow_external=self.allow_external_demo_server and self.demo.port_in_use)
            outcomes = verify_claims(list(imp.claims), list(imp.addresses), demo, resolver=self.resolver)
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


__all__ = ["Lab", "NotFound", "BadRequest", "ImportFileError"]
