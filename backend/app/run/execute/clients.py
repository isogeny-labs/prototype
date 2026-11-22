"""Who can still connect (phase 4e, first half): the demo client stand-ins' handshakes. Raw outcomes only: the separate
reviewer (engine/reviewer.py, `RuleReviewer._client_reach`) decides each stand-in's word.

It runs inside a try on a test copy, while the copy is up. For each stand-in of the locked test, ONE full handshake:
  1. to the server as it is today (its address, through the same gate as every test: this computer or confirmed);
  2. to the test copy with the change (through the copy's own gate: the port this app started it on, and the
     fingerprint of the test certificate it was given);
  3. to each of our own two control servers (hybrid and classical), started for this run, where the locked test says
     what each stand-in must do.
Handshakes only: no data is sent. Every handshake is made by the built-in OpenSSL (app/checks/pqtls.py) offering
exactly the stand-in's TLS versions, key-exchange groups and signature types. If that OpenSSL can't be used here,
nothing is guessed: the run reports that problem."""
from __future__ import annotations

from typing import Any

from app.checks import pqtls
from app.checks.tlsprobe import Evidence, ProbeSession, _iso, _now
from app.run.execute import RunContext, problem
from app.run.execute.pqstatus import ENGINE_TOOL, _compact
from app.run.execute.server import _evidence, _ready, gate


def _blocked(detail: str) -> dict:
    return {"outcome": "unknown", "detail": detail, "group": None, "tls_version": None, "alert": None, "duration_ms": 0,
            "client_hello_bytes": None, "client_share_bytes": None, "server_share_bytes": None,
            "certificate_message_bytes": None, "signature_bytes": None, "signature_scheme": None, "messages": []}


def _one(session: ProbeSession, stand_in: dict) -> dict:
    """One handshake by one stand-in, counted against the address's limit like every other handshake."""
    blocked = session._take()
    if blocked:
        return _blocked(blocked)
    versions = list(stand_in["versions"])
    h = pqtls.handshake(session.ip, session.port, session.server_name, ":".join(stand_in["groups"]), timeout=session.timeout,
                        min_version=versions[0], max_version=versions[-1], signatures=":".join(stand_in["signatures"]))
    return _compact(h)


def _side(session: ProbeSession, stand_ins: list[dict]) -> dict:
    return {s["id"]: _one(session, s) for s in stand_ins}


def _lines(title: str, session: ProbeSession, stand_ins: list[dict], seen: dict, engine: str) -> Evidence:
    out = [f"{s['name']}: {seen[s['id']]['outcome']} - {seen[s['id']]['detail']}" for s in stand_ins]
    return Evidence(title=title,
                    command=(f"OpenSSL (inside the cryptography library): one full TLS handshake per stand-in to {session.target}"
                             f"{session._sni_words()}, offering exactly its TLS versions, key-exchange groups and signature types, "
                             "no application data, then close"),
                    output="\n".join(out), started_at=_iso(_now()),
                    duration_ms=int(sum(seen[s["id"]].get("duration_ms") or 0 for s in stand_ins)), tool=ENGINE_TOOL, tool_version=engine)


def run_client_reach(spec: dict, ctx: RunContext) -> dict:
    usable, engine = pqtls.available()
    if not usable:
        return problem("pq_engine_unavailable", engine)
    address = spec["target"]["address"]
    stand_ins = list(spec["inputs"]["stand_ins"])
    if ctx.today_check is None:
        return problem("copy_unavailable", "This test runs only inside a try on a test copy.")
    copy, blocked = gate(ctx, address)                   # ctx.address_check is the copy's own gate
    if blocked:
        return blocked
    not_ready = _ready(copy)
    if not_ready:
        return not_ready
    try:
        ctx.progress("connecting the client stand-ins to the server as it is today", 20)
        today_check: Any = ctx.today_check(address)
        today: dict = {"reached": False, "problem": None, "handshakes": {}}
        evidence = []
        if today_check is None:
            today["problem"] = "This address is not in the imported file. No connection was attempted."
        elif today_check.blocked:
            today["problem"] = f"{today_check.blocked} No connection was attempted."
        else:
            why = _ready(today_check)
            if why:
                today["problem"] = (why.get("problem") or {}).get("text") or "The server did not answer."
            else:
                today["reached"] = True
                today["handshakes"] = _side(today_check.session, stand_ins)
                evidence.append(_lines("Client stand-ins: the server as it is today", today_check.session, stand_ins, today["handshakes"], engine))
        ctx.progress("connecting the client stand-ins to the test copy", 50)
        on_copy = _side(copy.session, stand_ins)
        evidence.append(_lines("Client stand-ins: the test copy with the change", copy.session, stand_ins, on_copy, engine))
        ctx.progress("running the control servers", 75)
        control = _control(stand_ins, engine)
        subject = {"address": address, "today": today, "copy": {"port": copy.row.port, "handshakes": on_copy},
                   "evidence": _evidence(copy.wrap(copy.base_evidence() + evidence + control.pop("_evidence", [])))}
        return {"engine": {"available": True, "text": engine}, "subject": subject, "control": control}
    except pqtls.PqTlsUnavailable as exc:
        return problem("pq_engine_unavailable", str(exc))


def _control(stand_ins: list[dict], engine: str) -> dict:
    """Every stand-in once on each of our own control servers (hybrid and classical), started for this run."""
    try:
        with pqtls.control_servers() as ports:
            out: dict = {"_evidence": []}
            for name in ("hybrid", "classical"):
                session = ProbeSession("127.0.0.1", ports[name], None)
                out[name] = _side(session, stand_ins)
                out["_evidence"].append(_lines(f"Control, our own {name} test server: the same stand-ins", session, stand_ins, out[name], engine))
            return out
    except pqtls.PqTlsUnavailable as exc:
        return {"error": f"the control servers could not be started ({exc})"}
    except OSError as exc:
        return {"error": f"the control servers could not be started ({exc.__class__.__name__})"}


__all__ = ["run_client_reach"]
