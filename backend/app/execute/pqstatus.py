"""The post-quantum status measurement (phase 4a): where a server or a signing program stands today.
Used by the Migration step, by the Post-quantum readiness test and by Verify (a post_quantum claim), so the
three can never disagree. Raw outcomes only: reviewer.py decides the status.

A server measurement, all handshakes one at a time and counted against the address's limit:
  1. three hand-built hellos with no key attached (pqprobe): only hybrids, only ML-KEM by itself, only classical;
  2. the TLS version handshakes and the certificate the app already reads;
  3. one full handshake by a classical-only client, and one offering only hybrids, made by the copy of OpenSSL
     inside the `cryptography` library (pqtls); in isolated mode also one by the pinned OpenSSL 3.5 container;
  4. the control: the same three hellos against a hybrid and a classical test server started for this run;
  5. for the cost table (Migration only): 10 classical and 10 hybrid handshakes taken in turn, on the server when
     it offers hybrid, otherwise on our own hybrid control server ("measured on our test server").
If pqtls can't be used on this computer nothing is guessed: the measurement reports that problem."""
from __future__ import annotations

from .. import components, pqprobe, pqtls
from ..tlsprobe import Evidence, ProbeSession, _iso, _now, describe_certificate
from . import RunContext, problem
from .server import _certificate, _evidence, _ready, _versions, gate

HYBRID_GROUPS = "X25519MLKEM768:SecP256r1MLKEM768:SecP384r1MLKEM1024"
PURE_GROUPS = "MLKEM768:MLKEM1024:MLKEM512"
CLASSICAL_GROUPS = "X25519:P-256:P-384"
TIMING_ROUNDS = 10
ENGINE_TOOL = "OpenSSL inside the cryptography library"


def _compact(h) -> dict:
    """A pqtls handshake as plain data (the certificate itself is described separately)."""
    return {"outcome": h.outcome, "tls_version": h.tls_version, "group": h.group, "alert": h.alert, "detail": h.detail,
            "duration_ms": round(float(h.duration_ms), 3), "client_hello_bytes": h.client_hello_bytes,
            "client_share_bytes": h.client_share_bytes, "server_share_bytes": h.server_share_bytes,
            "certificate_message_bytes": h.certificate_message_bytes, "signature_bytes": h.signature_bytes,
            "messages": [{"direction": m["direction"], "type": m["type"], "bytes": m["bytes"]} for m in h.messages]}


def _full(session: ProbeSession, groups: str, min_version: str = "TLS 1.3"):
    """One full handshake by the built-in OpenSSL, counted like every other handshake. (compact dict, certificate DER)"""
    blocked = session._take()
    if blocked:
        return {"outcome": "unknown", "detail": blocked, "group": None, "tls_version": None, "alert": None, "duration_ms": 0,
                "client_hello_bytes": None, "client_share_bytes": None, "server_share_bytes": None,
                "certificate_message_bytes": None, "signature_bytes": None, "messages": []}, None
    h = pqtls.handshake(session.ip, session.port, session.server_name, groups, timeout=session.timeout,
                        min_version=min_version, max_version="TLS 1.3")
    return _compact(h), h.certificate_der


def _timing(session: ProbeSession, hybrid_too: bool, rounds: int = TIMING_ROUNDS) -> dict:
    """Classical handshakes and, when the server offers hybrid, hybrid ones taken in turn with them. Every one is
    listed; a failed one is listed as null."""
    classical, hybrid = [], []
    for _ in range(rounds):
        for groups, out, wanted in ((CLASSICAL_GROUPS, classical, True), (HYBRID_GROUPS, hybrid, hybrid_too)):
            if not wanted:
                continue
            h, _ = _full(session, groups, min_version="TLS 1.2" if groups == CLASSICAL_GROUPS else "TLS 1.3")
            out.append(h["duration_ms"] if h["outcome"] == "completed" else None)
    return {"rounds": rounds, "classical_ms": classical, "hybrid_ms": hybrid if hybrid_too else None,
            "clock": "time.perf_counter, connect and handshake"}


def _public_key_bytes(der: bytes) -> int | None:
    """The size of the certificate's public key as it travels (an EC point, an RSA modulus, a raw ML-DSA key)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        key = x509.load_der_x509_certificate(der).public_key()
        if isinstance(key, ec.EllipticCurvePublicKey):
            return len(key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        if isinstance(key, rsa.RSAPublicKey):
            return (key.key_size + 7) // 8
        return len(key.public_bytes_raw())
    except Exception:
        return None


def _handshake_evidence(title: str, session: ProbeSession, items: list[tuple[str, dict]], engine: str) -> Evidence:
    lines = [f"{label}: {h['outcome']} - {h['detail']}" for label, h in items]
    return Evidence(title=title,
                    command=(f"OpenSSL (inside the cryptography library): one full TLS handshake per line to {session.target}"
                             f"{session._sni_words()}, offering exactly the groups named, no application data, then close"),
                    output="\n".join(lines), started_at=_iso(_now()),
                    duration_ms=int(sum(h.get("duration_ms") or 0 for _, h in items)), tool=ENGINE_TOOL, tool_version=engine)


def any_certificate(check) -> bytes | None:
    """The server's certificate: from the handshakes Python's own TLS library completed, or, for a server that only
    speaks post-quantum key exchange, from one handshake by the built-in OpenSSL."""
    der = check.session.first_certificate()
    if der is not None or not pqtls.available()[0]:
        return der
    cached = getattr(check, "_pq_certificate", False)
    if cached is not False:
        return cached
    try:
        _, der = _full(check.session, f"{HYBRID_GROUPS}:{PURE_GROUPS}:{CLASSICAL_GROUPS}")
    except pqtls.PqTlsUnavailable:
        der = None
    check._pq_certificate = der
    return der


def measure_server(check, mode, progress, log, costs: bool) -> dict:
    """The raw measurement of one server whose address has already passed the gate (`check` is its AddressCheck)."""
    usable, engine = pqtls.available()
    if not usable:
        return problem("pq_engine_unavailable", engine)
    not_ready = _ready(check)
    if not_ready:
        return not_ready
    session = check.session
    try:
        progress("offering hybrid, post-quantum and classical key exchange", 10)
        probes = pqprobe.offer_all(session)
        observed, _ = session.versions()
        classical_client, der_classical = _full(session, CLASSICAL_GROUPS, min_version="TLS 1.2")
        hybrid_handshake, der_hybrid = _full(session, HYBRID_GROUPS)
        pure_handshake, der_pure = (None, None)
        if probes["pure"]["state"] == "offered":
            pure_handshake, der_pure = _full(session, PURE_GROUPS)
        der = session.first_certificate() or der_classical or der_hybrid or der_pure
        certificate = None
        if der is not None:
            try:
                certificate = {**_certificate(der), "der_bytes": len(der), "public_key_bytes": _public_key_bytes(der)}
            except ValueError:
                certificate = None
        subject: dict = {"address": check.row.address, "ip": check.row.resolved_ip, "probes": probes, "versions": _versions(observed),
                         "classical_client": classical_client, "hybrid_handshake": hybrid_handshake, "pure_handshake": pure_handshake,
                         "certificate": certificate, "container": None, "timing": None}
        if mode is not None and getattr(mode, "name", None) == "isolated":
            progress("asking the OpenSSL 3.5 container", 35)
            subject["container"] = _container(mode, session)
        handshakes = [("classical-only client (X25519, P-256, P-384)", classical_client), ("hybrid groups only", hybrid_handshake)]
        if pure_handshake is not None:
            handshakes.append(("ML-KEM by itself", pure_handshake))
        if costs:
            progress("timing handshakes", 45)
            subject["timing"] = _timing(session, hybrid_too=hybrid_handshake["outcome"] == "completed")
        subject["evidence"] = _evidence(check.wrap(check.base_evidence() + [
            pqprobe.evidence(session, probes), _handshake_evidence("Full handshakes", session, handshakes, engine)]))
        raw: dict = {"engine": {"available": True, "text": engine}, "subject": subject}
        progress("running the control servers", 70)
        raw["control"] = _control(costs and hybrid_handshake["outcome"] != "completed", engine, session.server_name)
    except pqtls.PqTlsUnavailable as exc:
        return problem("pq_engine_unavailable", str(exc))
    return raw


def _control(with_reference_timing: bool, engine: str, server_name: str | None = None) -> dict:
    """The same hellos against our own hybrid and classical control servers, plus the reference handshakes on the
    hybrid one (the numbers shown as "measured on our test server"). The reference handshakes send the same server
    name as the handshakes to the server itself, so their message sizes can be compared like for like."""
    try:
        with pqtls.control_servers() as ports:
            out: dict = {}
            for name in ("hybrid", "classical"):
                session = ProbeSession("127.0.0.1", ports[name], None)
                probes = pqprobe.offer_all(session)
                out[name] = {"port": ports[name], "probes": probes, "evidence": _evidence([pqprobe.evidence(
                    session, probes, f"Control, our own {name} test server: the same three hellos")])}
            session = ProbeSession("127.0.0.1", ports["hybrid"], server_name)
            classical, _ = _full(session, CLASSICAL_GROUPS, min_version="TLS 1.2")
            hybrid, _ = _full(session, HYBRID_GROUPS)
            out["reference"] = {"classical": classical, "hybrid": hybrid,
                                "timing": _timing(session, hybrid_too=True) if with_reference_timing else None}
            out["hybrid"]["evidence"] += _evidence([_handshake_evidence(
                "Our own hybrid test server: full handshakes", session,
                [("classical-only client", classical), ("hybrid groups only", hybrid)], engine)])
            return out
    except pqtls.PqTlsUnavailable as exc:
        return {"error": f"the control servers could not be started ({exc})"}
    except OSError as exc:
        return {"error": f"the control servers could not be started ({exc.__class__.__name__})"}


def _container(mode, session: ProbeSession) -> dict | None:
    """Isolated mode: one more full hybrid handshake, by the pinned OpenSSL 3.5 container's own client."""
    from .pq import _read, find_checker
    try:
        checker, why_not = find_checker(mode)
        if checker is None:
            return {"ran": False, "why": why_not}
        blocked = session._take()
        if blocked:
            return {"ran": False, "why": blocked}
        return {"ran": True, "checker": {"kind": checker.kind, "version": checker.version},
                **_read(checker.s_client(session.ip, session.port, session.server_name, True))}
    except Exception as exc:  # a missing docker program, a time-out: the witness simply did not run
        return {"ran": False, "why": f"the container check could not be run ({exc.__class__.__name__})"}


def run_pq_status(spec: dict, ctx: RunContext) -> dict:
    address = spec["target"]["address"]
    check, blocked = gate(ctx, address)
    if blocked:
        return blocked
    return measure_server(check, ctx.mode, ctx.progress, ctx.log, costs=bool(spec["inputs"].get("costs")))


def run_signing_status(spec: dict, ctx: RunContext) -> dict:
    """A signing program: what it says it signs with, confirmed by one sign-and-check round trip that an independent
    library checks (exactly Verify's check), then its own bench next to ML-DSA-65 on the reference library."""
    from .signing import NOT_DEMO, component_key
    from .speed import run_mldsa_compare
    if component_key(spec, ctx) is None:
        return problem("not_a_demo_component", NOT_DEMO)
    name, version = ctx.component
    path = components.lookup(name, version)
    ctx.progress("waiting for a timing measurement to finish", None)
    with ctx.gate.shared():
        ctx.begin()
        ctx.progress("asking the program what it signs with", 10)
        check = components.verify_software_claim(path, name, version, spec["inputs"]["claimed_algorithm"], runner=ctx.runner)
    raw: dict = {"subject": {"component": f"{name} {version}", "claimed_algorithm": spec["inputs"]["claimed_algorithm"],
                             "check": {k: check.get(k) for k in ("result", "found", "reason")},
                             "evidence": list(check.get("evidence") or [])}, "cost": None}
    if check.get("result") == "True":
        raw["cost"] = run_mldsa_compare({"inputs": spec["inputs"]["mldsa"], "target": spec["target"]}, ctx)
    return raw


__all__ = ["measure_server", "run_pq_status", "run_signing_status", "any_certificate", "describe_certificate",
           "HYBRID_GROUPS", "PURE_GROUPS", "CLASSICAL_GROUPS"]
