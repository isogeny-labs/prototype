"""The two server tests: old TLS versions, and certificate strength. Handshakes only, and only after the
address has passed the same gate as Verify (this computer, or an address the user has confirmed, with the
IP address pinned). Raw outcomes only."""
from __future__ import annotations

from .. import names
from ..tlsprobe import ProbeSession, describe_certificate
from ..verify import NOT_CONFIRMED
from . import RunContext, controls, problem


def gate(ctx: RunContext, address: str):
    """(AddressCheck, None) if this address may be contacted now, else (None, problem). No connection is made
    unless the gate passes."""
    check = ctx.address_check(address)
    if check is None:
        return None, problem("address_not_confirmed", "This address is not in the imported file. No connection was attempted.")
    if check.blocked:
        demo_down = check.row.confirmed and check.blocked == (check.demo.error or "The demo server is not running.")
        code = "server_unreachable" if demo_down else "address_not_confirmed"
        text = f"{NOT_CONFIRMED}." if check.blocked == NOT_CONFIRMED else check.blocked
        out = problem(code, f"{text} No connection was attempted.")
        out["gate"] = [e.as_dict() for e in check.evidence]
        return None, out
    return check, None


def _ready(check):
    why = check.ready()  # the version handshakes, and for the demo address: is it really our demo server?
    if why:
        out = problem("server_unreachable", why)
        out["gate"] = [e.as_dict() for e in check.wrap(check.base_evidence())]
        return out
    observed, _ = check.session.versions()
    if not any(o.status in ("accepted", "refused") for o in observed.values()):
        out = problem("server_unreachable", "The server gave no TLS answer to any handshake.")
        out["gate"] = [e.as_dict() for e in check.wrap(check.base_evidence())]
        return out
    return None


def _versions(observed: dict) -> dict:
    return {v: {"state": o.status, "detail": o.detail} for v, o in observed.items()}


def _evidence(items) -> list[dict]:
    return [e.as_dict() for e in items]


def run_tls_versions(spec: dict, ctx: RunContext) -> dict:
    address = spec["target"]["address"]
    check, blocked = gate(ctx, address)
    if blocked:
        return blocked
    ctx.progress("trying TLS 1.3, 1.2, 1.1 and 1.0", 10)
    not_ready = _ready(check)
    if not_ready:
        return not_ready
    observed, _ = check.session.versions()
    raw = {"subject": {"address": address, "ip": check.row.resolved_ip, "versions": _versions(observed),
                       "evidence": _evidence(check.wrap(check.base_evidence()))}}
    ctx.progress("running the control server", 60)
    accepts = spec["control"]["accepts"]
    try:
        with controls.tls_server_accepting(accepts, spec["inputs"]["claimed"]) as port:
            session = ProbeSession("127.0.0.1", port, None)
            seen, evidence = session.versions()
            raw["control"] = {"port": port, "accepts": accepts, "versions": _versions(seen),
                              "evidence": _evidence(evidence + [session.count_evidence()])}
    except Exception as exc:  # a control that cannot be run is recorded as such; the reviewer will not trust the run
        ctx.log(f"control server failed ({exc.__class__.__name__})")
        raw["control"] = {"error": f"the control server could not be run ({exc.__class__.__name__})"}
    return raw


def _certificate(der: bytes) -> dict:
    cert = describe_certificate(der)
    return {"algorithm": cert["key_type"], "curve": cert["curve"], "key_bits": cert["key_size"],
            "normalized": names.normalize_algorithm(
                "ECDSA" if cert["key_type"] == "EC" else cert["key_type"], cert["curve"], cert["key_size"]),
            "signature_algorithm": cert["signature_algorithm"], "sha256_fingerprint": cert["sha256_fingerprint"]}


def run_certificate(spec: dict, ctx: RunContext) -> dict:
    address = spec["target"]["address"]
    check, blocked = gate(ctx, address)
    if blocked:
        return blocked
    ctx.progress("reading the certificate", 10)
    not_ready = _ready(check)
    if not_ready:
        return not_ready
    der = check.session.first_certificate()
    subject: dict = {"address": address, "ip": check.row.resolved_ip, "certificate": None,
                     "evidence": _evidence(check.wrap(check.base_evidence()))}
    if der is not None:
        try:
            subject["certificate"] = _certificate(der)
        except ValueError:
            subject["certificate"] = None
    raw: dict = {"subject": subject}
    ctx.progress("comparing with NIST guidance", 60)
    try:
        with controls.weak_certificate_server() as port:
            session = ProbeSession("127.0.0.1", port, None)
            _, evidence = session.versions()
            control_der = session.first_certificate()
            raw["control"] = {"port": port, "certificate": _certificate(control_der) if control_der else None,
                              "evidence": _evidence(evidence + [session.count_evidence()])}
    except Exception as exc:
        ctx.log(f"control server failed ({exc.__class__.__name__})")
        raw["control"] = {"error": f"the control server could not be run ({exc.__class__.__name__})"}
    return raw
