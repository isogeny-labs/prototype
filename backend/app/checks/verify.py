"""Verify: check each claim against the real system and say True, False or Couldn't check, with evidence.

Results come only from what the probes and the demo component actually returned. When something could
not be tested, the answer is Couldn't check with the reason - never a guess.
"""

from __future__ import annotations

import platform
import ssl
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.run import components
from app.present import plain
from app import real_libraries
from app.checks.addresses import AddressError, is_loopback_ip, resolve_all, validate_host, validate_port
from app.engine.compare import COULDNT, FALSE, TRUE, certificate_matches, compare_only_claim
from app.names import TLS_VERSIONS, join_and
from app.checks.tlsprobe import (
    PY_TOOL,
    PY_TOOL_VERSION,
    TLS13_SUITES,
    WIDEST_CIPHERS,
    Evidence,
    ProbeSession,
    describe_certificate,
    openssl_cli,
)

NOT_CONFIRMED = "You haven't confirmed you're allowed to test this address"
NOT_CHECKED = "Not checked."
_CURVE_WORDS = {"secp256r1": "P-256 (secp256r1)", "secp384r1": "P-384 (secp384r1)", "secp521r1": "P-521 (secp521r1)"}


@dataclass
class DemoContext:
    """What Verify needs to know about the demo server for a demo import."""

    is_demo_import: bool
    host: str
    port: int
    running: bool
    error: str | None
    fingerprint: str | None
    allow_external: bool = False  # only the accuracy command sets this (the app may already be serving the port)
    # Phase 3a-fixes, for the multi-target demo file only: port -> the fingerprint of our own test server there (None
    # when it is not running, with the reason in extra_problems). Like the demo server, they are checked to be ours.
    extra: dict | None = None
    extra_problems: dict | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _result(result: str, found: str, reason: str | None, evidence: list) -> dict:
    return {
        "result": result,
        "found": found,
        "reason": reason,
        "evidence": [e.as_dict() if isinstance(e, Evidence) else e for e in evidence],
    }


def _couldnt(reason: str, evidence: list | None = None, found: str = NOT_CHECKED) -> dict:
    return _result(COULDNT, found, reason, evidence or [])


class AddressCheck:
    """Everything for one host:port in one run: the safety gate first, then (only if it passes) the handshakes."""

    def __init__(
        self,
        row,
        demo: DemoContext,
        resolver: Callable[[str], list[str]] = resolve_all,
        session_factory: Callable[..., ProbeSession] = ProbeSession,
        mode=None,
    ):
        self.row = row
        self.demo = demo
        self.mode = mode  # the app's mode: in isolated mode the OpenSSL 3.5 container gives a second opinion
        self._pq_cache = None
        self.blocked: str | None = None
        self.evidence: list[Evidence] = []
        self.session: ProbeSession | None = None
        self._cipher_cache = None
        self._group_cache = None
        self._identity_done = False
        self.version_evidence: list[Evidence] = []
        self.identity_evidence: list[Evidence] = []
        self._gate(resolver, session_factory)

    def _gate(self, resolver, session_factory) -> None:
        row = self.row
        started = _now_iso()

        def note(text: str) -> None:
            self.evidence.append(
                Evidence(
                    "Address check (no connection made)",
                    "(checked by Evidence Lab before any handshake)",
                    text,
                    started,
                    0,
                    "Evidence Lab",
                    f"Python {platform.python_version()}",
                )
            )

        try:
            host, port = validate_host(row.host), validate_port(row.port)
        except AddressError as exc:
            self.blocked = f"This is not an address we can safely connect to: {exc}."
            return note(self.blocked + " No connection was attempted.")
        if not row.confirmed:
            self.blocked = NOT_CONFIRMED
            return note(f"{row.address}: not confirmed by you. No name lookup and no connection was attempted.")
        if not row.resolved_ip:
            self.blocked = row.error or "We could not find the IP address for this name."
            return note(self.blocked + " No connection was attempted.")
        try:
            current = resolver(host)
        except AddressError as exc:
            self.blocked = f"{exc}."
            return note(self.blocked + " No connection was attempted.")
        if row.resolved_ip not in current:
            self.blocked = (
                f"{host} now points to a different IP address ({', '.join(current[:3])}) than the one you "
                f"confirmed ({row.resolved_ip}). Confirm the address again before testing."
            )
            return note(self.blocked + " No connection was attempted.")
        loop = "this computer" if is_loopback_ip(row.resolved_ip) else "not this computer"
        note(
            f"{row.address} connects to {row.resolved_ip}, {loop}. You confirmed you are allowed to test it. "
            f"Every handshake connects to {row.resolved_ip}; the name is only sent as the TLS server name."
        )
        is_ip = host == row.resolved_ip or ":" in host
        if self._is_demo_address() and not (self.demo.running or self.demo.allow_external):
            self.blocked = self.demo.error or "The demo server is not running."
            return note(self.blocked + " No connection was attempted.")
        if self._is_extra_address() and not self.demo.extra.get(row.port):
            self.blocked = (self.demo.extra_problems or {}).get(
                row.port
            ) or f"The demo test server for {row.address} is not running."
            return note(self.blocked + " No connection was attempted.")
        self.session = session_factory(row.resolved_ip, port, None if is_ip else host)

    def _is_demo_address(self) -> bool:
        return self.demo.is_demo_import and self.row.host == self.demo.host and self.row.port == self.demo.port

    def _is_extra_address(self) -> bool:
        return bool(self.demo.extra) and self.row.host == self.demo.host and self.row.port in self.demo.extra

    def ready(self) -> str | None:
        """Run the version handshakes (once) and, for the demo address, make sure it really is our demo server.
        Returns a reason if nothing may be reported for this address."""
        if self.blocked:
            return self.blocked
        _, ev = self.session.versions()
        if not self._identity_done:
            self._identity_done = True
            self.version_evidence = ev
            if self._is_extra_address():
                from app.run.execute import pqstatus  # here, not at the top: that package imports this module

                der = pqstatus.any_certificate(
                    self
                )  # also reads the certificate of a server that only speaks post-quantum
                seen = describe_certificate(der)["sha256_fingerprint"] if der is not None else None
                if seen != self.demo.extra.get(self.row.port):
                    self.blocked = (
                        f"Something other than the Evidence Lab demo test server is answering on {self.row.address} "
                        "(its certificate is not the one this app made), so we did not report on it."
                    )
                self.identity_evidence.append(
                    Evidence(
                        "Demo test server identity check",
                        "compare SHA-256 of the certificate received in the handshake with the test certificate made by this app",
                        f"received: {seen}\nexpected: {self.demo.extra.get(self.row.port)}\n=> {'match' if seen == self.demo.extra.get(self.row.port) else 'DIFFERENT'}",
                        _now_iso(),
                        0,
                        PY_TOOL,
                        PY_TOOL_VERSION,
                    )
                )
            if self._is_demo_address():
                der = self.session.first_certificate()
                started = _now_iso()
                if der is None:
                    self.blocked = (
                        f"No TLS handshake with {self.row.address} completed, so we could not confirm it is "
                        "the demo server." + (f" {self.demo.error}" if self.demo.error else "")
                    )
                else:
                    seen = describe_certificate(der)["sha256_fingerprint"]
                    if seen != self.demo.fingerprint:
                        self.blocked = (
                            f"Something other than the Evidence Lab demo server is answering on "
                            f"{self.row.address} (its certificate is not the demo test certificate), so we did not report on it."
                        )
                    self.identity_evidence.append(
                        Evidence(
                            "Demo server identity check",
                            "compare SHA-256 of the certificate received in the handshake with the demo test certificate made by this app",
                            f"received: {seen}\nexpected: {self.demo.fingerprint}\n=> {'match' if seen == self.demo.fingerprint else 'DIFFERENT'}",
                            started,
                            0,
                            PY_TOOL,
                            PY_TOOL_VERSION,
                        )
                    )
        return self.blocked

    def base_evidence(self) -> list[Evidence]:
        return self.evidence + (self.version_evidence + self.identity_evidence if self.session else [])

    def wrap(self, evidence: list[Evidence]) -> list[Evidence]:
        return evidence + ([self.session.count_evidence()] if self.session else [])

    # ---------------------------------------------------------------- one claim kind each

    def protocol_versions(self, detail: dict) -> dict:
        if detail.get("unsupported_protocol"):
            return _couldnt("This version of Evidence Lab checks TLS only, not other protocols.")
        if detail.get("version_not_stated") or not detail.get("versions"):
            return _couldnt(
                "The file doesn't say which TLS versions the server should accept, so there is nothing exact to compare."
            )
        why = self.ready()
        if why:
            return _couldnt(why, self.wrap(self.base_evidence()))
        observed, _ = self.session.versions()
        claimed = [v for v in TLS_VERSIONS if v in detail.get("versions", [])]
        verdict = compare_only_claim(claimed, {v: o.status for v, o in observed.items()})
        newest_first = list(reversed(TLS_VERSIONS))
        accepted = [v for v in newest_first if observed[v].status == "accepted"]
        refused = [v for v in newest_first if observed[v].status == "refused"]
        unknown = [v for v in newest_first if observed[v].status == "unknown"]

        def with_suite(v: str) -> str:
            return f"{v} (with {observed[v].cipher})" if v not in claimed and observed[v].cipher else v

        parts = []
        if accepted:
            parts.append(f"Accepts {join_and([with_suite(v) for v in accepted])}.")
        if refused:
            parts.append(f"Refuses {join_and(refused)}.")
        if unknown:
            parts.append(f"The server didn't confirm or refuse {join_and(unknown)}.")
        reason = None
        if verdict.result == COULDNT:
            reason = (
                "The server didn't clearly accept or refuse "
                + "; ".join(f"{v} ({observed[v].detail})" for v in unknown)
                + ", so we can't say it accepts nothing else."
            )
        out = _result(verdict.result, " ".join(parts) or NOT_CHECKED, reason, self.wrap(self.base_evidence()))
        out["summary"] = plain.verify_tls(verdict.result, claimed, accepted, refused, unknown)
        return out

    def certificate(self, detail: dict, tls_claimed: bool = False) -> dict:
        """`tls_claimed`: the file also makes a TLS-version claim for this server, so its TLS versions are not
        something the file didn't ask about, and no "Also noticed" note is added."""
        claimed = detail.get("algorithm")
        if not claimed:
            return _couldnt(
                "The file does not name the certificate's algorithm in a form we can compare "
                "(for example ECDSA P-256 or RSA 2048)."
            )
        why = self.ready()
        if why:
            return _couldnt(why, self.wrap(self.base_evidence()))
        der = self.session.first_certificate()
        if der is None:
            return _couldnt(
                f"No TLS handshake with {self.row.address} completed, so no certificate was received.",
                self.wrap(self.base_evidence()),
            )
        started = _now_iso()
        import cryptography

        try:
            cert = describe_certificate(der)
        except ValueError:
            return _couldnt("The server sent a certificate we could not read.", self.wrap(self.base_evidence()))
        if cert["key_type"] == "EC":
            key_words = f"an EC key on curve {_CURVE_WORDS.get(cert['curve'], cert['curve'])}, {cert['key_size']} bits"
        elif cert["key_type"] == "RSA":
            key_words = f"an RSA key, {cert['key_size']} bits"
        else:
            key_words = f"a {cert['key_type']} key"
        found = (
            f"The certificate served by {self.row.address} has {key_words}. "
            f"It is signed with {cert['signature_algorithm']}."
        )
        ev = Evidence(
            "Certificate received in the live handshake",
            "python ssl: take the certificate the server sent in the handshake above; cryptography: x509.load_der_x509_certificate(...) and read its public key",
            "\n".join(
                f"{k}: {cert[k]}"
                for k in ("subject", "key_type", "curve", "key_size", "signature_algorithm", "sha256_fingerprint")
            ),
            started,
            0,
            f"{PY_TOOL} (handshake) + cryptography (reading the certificate)",
            f"{PY_TOOL_VERSION}; cryptography {cryptography.__version__}",
        )
        match = certificate_matches(claimed, cert)
        evidence = self.wrap(self.base_evidence() + [ev])
        observed, _ = self.session.versions()
        noticed = (
            [] if tls_claimed else plain.also_noticed_tls({v: o.status for v, o in observed.items()})
        )  # words only
        if match is None:
            out = _result(COULDNT, found, f"We don't know how to compare a certificate with {claimed!r}.", evidence)
        else:
            out = _result(TRUE if match else FALSE, found, None, evidence)
            name = names_for_certificate(cert)
            out["summary"] = plain.verify_certificate(out["result"], claimed, name)
        out["also_noticed"] = noticed
        return out

    def post_quantum(self, detail: dict) -> dict:
        """Is the server's key exchange Classical, Hybrid or Post-quantum only, as the file says (phase 4a)? The same
        measurement and the same rule as the Migration step and the Post-quantum readiness test."""
        from app.present import pq as present_pq
        from app.run.execute import pqstatus
        from app.engine.reviewer import pq_status_of

        claimed = str(detail.get("status") or "")
        if self.blocked:
            return _couldnt(self.blocked, self.wrap(self.base_evidence()))
        if self._pq_cache is None:
            try:
                self._pq_cache = pqstatus.measure_server(self, self.mode, lambda *_: None, lambda *_: None, costs=False)
            except Exception as exc:  # never a crash and never a guess
                self._pq_cache = {
                    "problem": {
                        "code": "harness_error",
                        "text": f"The check stopped unexpectedly ({exc.__class__.__name__}).",
                    }
                }
        raw = self._pq_cache
        if raw.get("problem"):
            return _couldnt(
                str(raw["problem"].get("text") or "The check could not be run."),
                raw.get("gate") or self.wrap(self.base_evidence()),
            )
        evidence = list(raw["subject"].get("evidence") or [])
        control = raw.get("control") if isinstance(raw.get("control"), dict) else {}
        for name in ("hybrid", "classical"):
            evidence += list((control.get(name) or {}).get("evidence") or [])
        try:
            found = pq_status_of(raw)
        except (KeyError, TypeError, ValueError, AttributeError):
            return _couldnt("The answers could not be read.", evidence)
        if found["control"]["outcome"] != "as_expected":
            return _couldnt(
                "The check did not read our own hybrid and classical test servers correctly, so its answer can't be relied on.",
                evidence,
            )
        code, d = found["code"], found["detail"]
        if code not in present_pq.STATUS_LABELS:
            out = _couldnt(present_pq.unclear_sentence(d), evidence)
            out["summary"] = present_pq.unclear_sentence(d)
            return out
        label = present_pq.STATUS_LABELS[code]
        sentence = present_pq.status_sentence(code, d)
        out = _result(TRUE if label == claimed else FALSE, f"Measured: {label}. {sentence}", None, evidence)
        out["summary"] = (
            f"{sentence} That matches the claim."
            if label == claimed
            else f"{sentence} The file says {claimed}, so the claim is not true."
        )
        return out

    def key_exchange(self, detail: dict) -> dict:
        if detail.get("from_algorithm_asset"):
            return _couldnt(
                "The file names a key-exchange algorithm, not the TLS groups the server offers, "
                "so there is nothing exact to compare."
            )
        why = self.ready()
        if why:
            return _couldnt(why, self.wrap(self.base_evidence()))
        versions, _ = self.session.versions()
        if versions["TLS 1.3"].status != "accepted":
            return _couldnt(
                "This version checks key-exchange groups on TLS 1.3 only, and the server did not complete a "
                f"TLS 1.3 handshake ({versions['TLS 1.3'].detail}).",
                self.wrap(self.base_evidence()),
            )
        if self._group_cache is None:
            self._group_cache = self.session.tls13_groups()
        observed, ev = self._group_cache
        verdict = compare_only_claim(detail.get("groups", []), observed)
        accepted = [g for g, s in observed.items() if s == "accepted"]
        unknown = [g for g, s in observed.items() if s == "unknown"]
        found = (
            f"On TLS 1.3 the server accepts {join_and(accepted)}."
            if accepted
            else "On TLS 1.3 the server accepted none of the groups we tried."
        )
        found += f" Groups tried: {', '.join(observed)}."
        reason = None
        if verdict.result == COULDNT:
            reason = f"The server didn't confirm or refuse {join_and(verdict.unknown or unknown)}, so we can't say it uses nothing else."
        elif verdict.result == TRUE:
            # The groups we try are a fixed, short list, not every group a server could accept. So an
            # "only these groups" claim can be shown False, but never True.
            claimed = set(detail.get("groups", []))
            others = [g for g in observed if g not in claimed]
            verdict.result = COULDNT
            reason = (
                "The server accepts the claimed groups and refused the others we tried"
                f"{' (' + ', '.join(others) + ')' if others else ''}, but there are groups this checker "
                "can't offer, so we can't say it uses nothing else."
            )
        return _result(verdict.result, found, reason, self.wrap(self.base_evidence() + [ev]))

    def cipher_suites(self, detail: dict) -> dict:
        why = self.ready()
        if why:
            return _couldnt(why, self.wrap(self.base_evidence()))
        if self._cipher_cache is None:
            self._cipher_cache = self._scan_ciphers()
        observed, complete, incomplete_why, evidence = self._cipher_cache
        claimed, unknown_names = [], []
        known = _known_suite_names()
        for name in detail.get("suites", []):
            mapped = name if name in known else _iana_names().get(name)
            (claimed if mapped else unknown_names).append(mapped or name)
        all_evidence = self.wrap(self.base_evidence() + evidence)
        accepted = [n for n, s in observed.items() if s == "accepted"]
        found = (
            f"The server accepts {join_and(accepted)}."
            if accepted
            else "The server accepted no cipher suite we offered."
        )
        if unknown_names:
            return _result(
                COULDNT,
                found,
                f"We don't recognise the cipher suite name {join_and(unknown_names)}, "
                "so we can't compare the list exactly.",
                all_evidence,
            )
        full = dict(observed)
        for name in claimed:
            full.setdefault(name, "refused" if complete else "unknown")
        verdict = compare_only_claim(claimed, full)
        reason = None
        if verdict.result == TRUE and complete:
            # We can only offer the suites this computer's OpenSSL knows, not every suite a server could
            # accept. So an "only these suites" claim can be shown False, but never True.
            verdict.result = COULDNT
            reason = (
                "The server accepts the claimed cipher suites and refused every other suite this computer could "
                "offer, but there are cipher suites this checker can't offer, so we can't say it accepts nothing else."
            )
        elif verdict.result in (TRUE, COULDNT):
            verdict.result = COULDNT
            reason = f"The list of accepted cipher suites may be incomplete ({incomplete_why or 'some suites could not be tested'})."
        elif verdict.result == FALSE and verdict.claimed_refused:
            found += f" It refused {join_and(verdict.claimed_refused)}."
        return _result(verdict.result, found, reason, all_evidence)

    def _scan_ciphers(self):
        versions, _ = self.session.versions()
        observed: dict[str, str] = {}
        evidence: list[Evidence] = []
        complete, why = True, None
        for version in TLS_VERSIONS:
            obs = versions[version]
            if obs.status == "unknown":
                complete, why = False, f"{version} could not be tested: {obs.detail}"
            if obs.status != "accepted":
                continue
            if version == "TLS 1.3":
                statuses, ev = self.session.tls13_ciphers()
                evidence.append(ev)
                for suite, status in statuses.items():
                    observed[suite] = status
                    if status == "unknown":
                        complete, why = False, f"TLS 1.3 suite {suite} could not be tested"
            else:
                scan, ev = self.session.old_version_ciphers(version)
                evidence.append(ev)
                for suite in scan.accepted:
                    observed[suite] = "accepted"
                if not scan.complete:
                    complete, why = False, f"{version}: {scan.why_incomplete}"
        return observed, complete, why, evidence


_iana_cache: dict[str, str] | None = None
_known_cache: set[str] | None = None


def _known_suite_names() -> set[str]:
    global _known_cache
    if _known_cache is None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            ctx.set_ciphers(WIDEST_CIPHERS)
            _known_cache = {c["name"] for c in ctx.get_ciphers()} | set(TLS13_SUITES)
        except ssl.SSLError:
            _known_cache = set(TLS13_SUITES)
    return _known_cache


def _iana_names() -> dict[str, str]:
    """Standard (IANA) cipher suite name -> OpenSSL name, read from `openssl ciphers -stdname`."""
    global _iana_cache
    if _iana_cache is None:
        _iana_cache = {}
        path, _ = openssl_cli()
        if path:
            try:
                out = subprocess.run(
                    [path, "ciphers", "-stdname", WIDEST_CIPHERS],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == "-":
                        _iana_cache[parts[0]] = parts[2]
            except (OSError, subprocess.SubprocessError):
                pass
    return _iana_cache


def verify_claims(
    claims: list,
    address_rows: list,
    demo: DemoContext,
    resolver: Callable[[str], list[str]] = resolve_all,
    session_factory: Callable[..., ProbeSession] = ProbeSession,
    component_runner=None,
    mode=None,
) -> list[dict]:
    """Check every claim, one address at a time and one handshake at a time. Returns one result per claim.
    `component_runner` is the app's ComponentRunner: a software claim's component runs in the app's own mode."""
    rows = {r.address: r for r in address_rows}
    checks: dict[str, AddressCheck] = {}
    tls_claimed = {c.location for c in claims if c.location_kind == "server" and c.kind == "protocol_versions"}
    results = []
    for claim in claims:
        detail = claim.detail or {}
        if claim.location_kind == "server":
            row = rows.get(claim.location)
            if row is None:
                res = _couldnt("This is not an address we can safely connect to.")
            else:
                if claim.location not in checks:
                    checks[claim.location] = AddressCheck(row, demo, resolver, session_factory, mode=mode)
                check = checks[claim.location]
                if claim.kind == "protocol_versions":
                    res = check.protocol_versions(detail)
                elif claim.kind == "certificate":
                    res = check.certificate(detail, tls_claimed=claim.location in tls_claimed)
                elif claim.kind == "cipher_suites":
                    res = check.cipher_suites(detail)
                elif claim.kind == "key_exchange":
                    res = check.key_exchange(detail)
                elif claim.kind == "post_quantum":
                    res = check.post_quantum(detail)
                else:
                    res = _couldnt(
                        "This version checks signature algorithms on software components only, not on servers."
                    )
        elif claim.location_kind == "software":
            known = components.kind_of(detail.get("component"), detail.get("version"))
            # Phase 4c: a real library's key exchange claim (ML-KEM-768) is checked too; any other is not.
            kem = claim.kind == "key_exchange" and known == "real" and str(detail.get("algorithm", "")) == "ML-KEM-768"
            if claim.kind != "signature_algorithm" and not kem:
                res = _couldnt("This version checks signing components only.")
            elif known == "real":
                res = components.verify_real_claim(
                    detail["component"],
                    detail["version"],
                    str(detail.get("algorithm", "")),
                    runner=component_runner,
                    key_exchange=kem,
                )
            else:
                path = components.lookup(detail.get("component"), detail.get("version"))
                if path is None:
                    res = _couldnt(components.NOT_A_DEMO_COMPONENT)
                else:
                    res = components.verify_software_claim(
                        path,
                        detail["component"],
                        detail["version"],
                        str(detail.get("algorithm", "")),
                        runner=component_runner,
                    )
        else:
            res = _couldnt("The file doesn't say where this is used, so there is nothing to connect to or run.")
        results.append(_with_summary(claim, res))
    return results


def names_for_certificate(cert: dict) -> str:
    """A certificate's key in the same words a claim uses ("ECDSA P-256", "RSA 2048"), or plain words if not."""
    from app.names import normalize_algorithm

    name = normalize_algorithm(
        "ECDSA" if cert.get("key_type") == "EC" else cert.get("key_type"), cert.get("curve"), cert.get("key_size")
    )
    if cert.get("key_type") == "RSA":
        return f"RSA with a {cert.get('key_size')}-bit key"
    return name or f"a {cert.get('key_type')} key"


def _with_summary(claim, res: dict) -> dict:
    """Every row gets its one plain sentence (phase 3a-fixes) and a list of Also noticed notes (often empty)."""
    detail = claim.detail or {}
    res.setdefault("also_noticed", [])
    if res.get("summary"):
        return res
    if res["result"] == COULDNT:
        if claim.location_kind == "software" and res.get("reason") == components.NOT_A_DEMO_COMPONENT:
            label = f"{detail.get('component', '')} {detail.get('version', '')}".strip() or "this program"
            res["summary"] = (
                f"We couldn't run {label}: only our own demo components can run in this version, "
                "so there is no answer either way."
            )
        elif claim.location_kind == "software" and str(res.get("reason") or "").startswith(
            real_libraries.NEEDS_ISOLATED
        ):
            label = f"{detail.get('component', '')} {detail.get('version', '')}".strip() or "this library"
            res["summary"] = (
                f"We couldn't run {label}: it is real software from outside, which runs only in isolated mode (Docker), "
                "and this run is in demo mode. So there is no answer either way."
            )
        else:
            res["summary"] = plain.couldnt(res.get("reason"))
    elif claim.location_kind == "software":
        label = f"{detail.get('component', '')} {detail.get('version', '')}".strip()
        res["summary"] = plain.verify_software(
            res["result"],
            label,
            str(detail.get("algorithm", "")),
            res.get("found", ""),
            key_exchange=claim.kind == "key_exchange",
        )
    elif claim.kind in ("cipher_suites", "key_exchange") and res["result"] == FALSE:
        res["summary"] = f"{res.get('found', '').strip()} That doesn't match the claim, so it is not true."
    else:
        res["summary"] = plain.verify_fallback(res["result"], res.get("found", ""))
    return res
