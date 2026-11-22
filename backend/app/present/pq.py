"""Words for the post-quantum status measurement (phase 4a): the plain sentence, the facts list and the evidence
of a server's or a signing program's status, and the Post-quantum readiness test that shares the measurement.

Words only. The status is decided in reviewer.py; everything here is written from the stored review and run.
Never "secure", never a score, nothing beyond what was measured."""
from __future__ import annotations

import json

from app.names import join_and

STATUS_LABELS = {"hybrid": "Hybrid", "pq_only": "Post-quantum only", "classical": "Classical"}
FAMILY_LABELS = {"hybrid": "Hybrid key exchange", "pure": "ML-KEM by itself", "classical": "Classical key exchange"}
MEASURED = "measured"


def group_words(name: str | None) -> str:
    """ML-KEM groups as people write them (MLKEM768 -> ML-KEM-768); the hybrid names stay as TLS spells them."""
    name = str(name or "")
    return "ML-KEM-" + name[5:] if name.startswith("MLKEM") else name


def _probe(raw: dict, family: str) -> dict:
    probe = ((raw.get("subject") or {}).get("probes") or {}).get(family)
    return probe if isinstance(probe, dict) else {}


def _others(offered: list, named: str | None) -> str:
    rest = len([g for g in offered if g != named])
    return "" if not rest else f" and {'one other' if rest == 1 else ['two', 'three', 'four'][rest - 2] + ' others' if rest <= 4 else str(rest) + ' others'}"


def status_sentence(code: str, detail: dict) -> str:
    """The one plain sentence beside the status: what was found and why that gives this status."""
    if code == "hybrid":
        group = (detail.get("hybrid_groups") or ["a hybrid key exchange"])[0]
        tail = {"connects": " A classical-only client still connects.",
                "cannot": " A classical-only client could not connect."}.get(detail.get("classical_client"), "")
        proof = detail.get("hybrid_proof") or ["probe"]
        how = (f"It asked for a hybrid key ({group}) when we offered only hybrid key exchanges" if "probe" in proof else
               f"It completed a full handshake with the hybrid key exchange {group}" if "handshake" in proof else
               f"The OpenSSL 3.5 container's own client completed a handshake with the hybrid key exchange {group}")
        return f"{how}, so it is Hybrid.{tail}"
    if code == "pq_only":
        return (f"It accepted {group_words(detail.get('pure_group'))} by itself and refused both the hybrid and the classical "
                "key exchanges we offered, so it is Post-quantum only. A classical-only client can't connect.")
    if code == "classical":
        tail = " It doesn't accept TLS 1.3, which post-quantum key exchange needs." if detail.get("tls13") == "off" else ""
        return f"It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical.{tail}"
    return ""


def unclear_sentence(detail: dict) -> str:
    what = join_and(list(detail.get("unclear") or [])) or "our handshakes"
    return f"The server gave no clear answer to {what}, so its status couldn't be checked. Silence is never read as a status."


def server_facts(detail: dict, raw: dict) -> list[dict]:
    """The facts list: one line per thing measured, each tagged "measured"."""
    def fact(label: str, text: str, tag: str | None = MEASURED) -> dict:
        return {"label": label, "text": text, "tag": tag}

    out = []
    for family in ("hybrid", "pure", "classical"):
        probe = _probe(raw, family)
        offered, state, group = list(probe.get("offered") or []), probe.get("state"), probe.get("group")
        if state == "offered":
            verb = "Accepted" if family == "classical" else "Offered"
            text = f"{verb}: {group_words(group) if family == 'pure' else group}"
        elif state == "refused":
            first = offered[0] if offered else ""
            text = "Refused" + (f": {group_words(first) if family == 'pure' else first}{_others(offered, first)}" if family != "pure" and first else "")
            if family == "classical" and detail.get("classical_accepted"):
                versions = join_and([v for v in detail.get("tls_versions") or [] if v != "TLS 1.3"])
                text = f"Refused in TLS 1.3; accepted in {versions}" if versions else text
        else:
            text = f"No clear answer ({probe.get('detail') or 'nothing recorded'})"
        out.append(fact(FAMILY_LABELS[family], text))
    client = detail.get("classical_client")
    client_version = ((raw.get("subject") or {}).get("classical_client") or {}).get("tls_version")
    out.append(fact("A classical-only client connects",
                    (f"Yes, with {client_version}" if client_version else "Yes") if client == "connects"
                    else "No: the server refused it" if client == "cannot" else "Not clear"))
    versions = [v.replace("TLS ", "") for v in detail.get("tls_versions") or []]
    if not versions and detail.get("tls13") == "on":
        versions = ["1.3"]
    out.append(fact("TLS versions", join_and(versions) if versions else "None confirmed"))
    cert = detail.get("certificate")
    out.append(fact("Certificate", str(cert["name"]) if isinstance(cert, dict) and cert.get("name") else "Not read", MEASURED if cert else None))
    witness = (detail.get("witnesses") or {}).get("container")
    if witness in ("completed", "refused", "unclear"):
        out.append(fact("Second opinion (OpenSSL 3.5 container)",
                        {"completed": "Its own client completed a hybrid handshake", "refused": "Its own client was refused a hybrid handshake",
                         "unclear": "No clear answer"}[witness]))
    return out


def _evidence_text(items: list | None) -> str:
    parts = []
    for e in items or []:
        if isinstance(e, dict):
            parts.append(f"{e.get('title', '')}\n$ {e.get('command', '')}\n{e.get('output', '')}".strip())
    return "\n\n".join(parts) or "(nothing recorded)"


def _server_evidence(w, spec, run, review) -> None:
    d, raw = review["detail"], run["raw"]
    address = spec["target"]["address"]
    rows = [[f["label"], f["text"]] for f in server_facts(d, raw)]
    w.evidence = [{"type": "table", "title": "What the server did with each kind of key exchange", "tag": MEASURED,
                   "columns": [{"label": "What we tried", "align": "left"}, {"label": "The server\n(measured)", "align": "left"}],
                   "rows": rows, "meta": [], "note": None}]
    w.command = (f"Three TLS 1.3 hellos with no key attached to {address} (connected to {(raw.get('subject') or {}).get('ip')}), "
                 "then one full hybrid and one classical-only handshake; handshakes only")
    control = raw.get("control") or {}
    w.outputs = [{"title": "Raw output", "text": _evidence_text((raw.get("subject") or {}).get("evidence"))},
                 {"title": "Raw output, our hybrid test server", "text": _evidence_text((control.get("hybrid") or {}).get("evidence"))},
                 {"title": "Raw output, our classical test server", "text": _evidence_text((control.get("classical") or {}).get("evidence"))}]
    engine = (raw.get("engine") or {}).get("text")
    if engine:
        w.meta = [{"label": "Checker", "value": f"hand-built hellos, and {engine}", "tag": MEASURED}]
    w.control_text = ("The same check read our own hybrid test server as Hybrid and our own classical test server as Classical, as expected. "
                      "That tells us this check can tell the two apart.")


def pq_status(w, spec, run, review, ctx) -> None:
    d, code = review["detail"], review["code"]
    address = spec["target"]["address"]
    w.plain = status_sentence(code, d)
    label = STATUS_LABELS[code]
    w.summary = f"The key exchange of {address} is {label} today."
    w.short = f"{label}."
    w.what = [f"We sent {address} three first messages that each offered one kind of key exchange and no key: hybrid, ML-KEM by itself, and classical. "
              "A server that supports a kind asks for a key for it; one that doesn't refuses.",
              "Then we made one full handshake that offered only hybrids, and one as a client that knows only classical key exchange."]
    w.shows = [f"It shows what kind of key exchange this server accepts today: {label}.",
               "It doesn't show which key exchange your real clients end up using, and it says nothing about the rest of the server's setup."]
    _server_evidence(w, spec, run, review)
    w.fix = None


def present_pq_status_line(status: str | None, detail: dict) -> str:
    return status_sentence(str(status), detail) if status in STATUS_LABELS else ""


def pq_readiness(w, spec, run, review, ctx) -> None:
    """The Post-quantum readiness test since phase 4a: the same measurement, worded as Offered / Not offered."""
    d, code = review["detail"], review["code"]
    address, status = spec["target"]["address"], d.get("status")
    if code == "not_offered":
        w.plain = ("The server doesn't offer a quantum-resistant key exchange: it refused the hybrid and the ML-KEM hellos, "
                   "while a classical handshake worked.")
        w.summary = "The server does not offer a quantum-resistant key exchange (hybrid or ML-KEM)."
        w.short = "Server does not offer a quantum-resistant key exchange."
        w.what = [f"We sent {address} first messages that offered only hybrid key exchanges, and only ML-KEM by itself. It refused both with a TLS refusal, "
                  "and it refused a full handshake that offered only hybrids.",
                  "A full classical handshake to the same server completed, so the refusal is about these key exchanges, not about reaching the server."]
        w.shows = ["It shows this server does not offer a quantum-resistant key exchange today.",
                   "It doesn't show a weakness today: this is about readiness for the post-quantum move."]
        w.fix = ("Nothing is broken today. The Migration step shows the options for this server, what each costs, and how to turn "
                 "hybrid key exchange on.")
    else:
        group = d.get("group")
        named = f" ({group_words(group) if status == 'pq_only' else group})" if group else ""
        proof = d.get("hybrid_proof") or []
        how = ("it asked for a key for it when we offered nothing else" if status == "pq_only" or "probe" in proof else
               "a handshake that offered nothing else completed")
        w.plain = f"The server offers a quantum-resistant key exchange{named}: {how}."
        w.summary = f"The server offers a quantum-resistant key exchange{named}."
        w.short = f"Server offers a quantum-resistant key exchange{named}."
        w.what = [line for line in (
            f"We sent {address} first messages that offered only quantum-resistant key exchanges, and made one full handshake offering only hybrids.",
            present_pq_status_line(status, d)) if line]
        w.shows = ["It shows this server offers a quantum-resistant key exchange today.",
                   "It doesn't show that every client will use it, or anything about the rest of the server's setup."]
        w.fix = "None needed."
    if ctx["phase"] == "retest":
        w.short += " The server was tested again as it is; only the signing component was updated."
    elif ctx["phase"] == "proof":
        w.short += " This change doesn't touch the server."
    _server_evidence(w, spec, run, review)


def signing_status(w, spec, run, review, ctx) -> None:
    d, code = review["detail"], review["code"]
    name, algorithm = d.get("component") or ctx["component"], d.get("algorithm")
    kind = "a classical algorithm" if code == "classical" else "a post-quantum algorithm"
    # For OpenSSL the second opinion is not an outside one: the app's reference library is itself built on OpenSSL (phase 4c).
    same_maker = str(name).split(" ")[0] == "openssl"
    checker = "the app's reference library, which is itself built on OpenSSL," if same_maker else "an independent library"
    w.plain = (f"{name} says it signs with {algorithm}, and {checker} confirmed its signature. {algorithm} is {kind}, "
               f"so it is {STATUS_LABELS[code]}.")
    w.summary = f"{name} signs with {algorithm} today: {STATUS_LABELS[code]}."
    w.short = f"{STATUS_LABELS[code]} ({algorithm})."
    w.what = [f"We asked {name} what it signs with, had it sign one test message, and checked that signature with "
              + ("the app's reference library (itself built on a release of OpenSSL, so not an outside opinion here)." if same_maker
                 else "an independent library.")]
    if "can_make_pq" in d:   # phase 4c, a real library: it was also asked to make one post-quantum signature
        pq = d.get("pq_algorithm") or "ML-DSA-65"
        w.what.append(f"We also asked it to make one {pq} signature. " + (
            "It did, and the reference library confirmed that signature, so it can make post-quantum signatures today." if d["can_make_pq"] is True
            else f"It does not offer {pq}, so it can't make post-quantum signatures today." if d["can_make_pq"] is False
            else "That could not be checked."))
    if d.get("cost") is not None or code != "pq_only":
        w.what.append("Then we timed its bench command next to ML-DSA-65 on the reference library, for the cost table.")
    else:   # it already signs with a post-quantum algorithm: there is nothing to compare it with
        w.what.append("No cost comparison was made: it already signs with a post-quantum algorithm.")
    w.shows = [f"It shows the algorithm this program signs with today: {algorithm}.",
               "It doesn't show where its signatures are used, or how long they must stay trusted: that is the Data lifespan setting."]
    subject = run["raw"].get("subject") or {}
    w.evidence = [{"type": "text", "title": "What the program reported, and what the independent library found", "tag": MEASURED,
                   "text": str(d.get("found") or "")}]
    w.command = f"{str(name).split(' ')[0]}: report the algorithm, sign one test message; an independent library checks the signature"
    w.outputs = [{"title": "Raw output", "text": _evidence_text(subject.get("evidence"))},
                 {"title": "Raw output, cost measurement", "text": json.dumps(d.get("cost") or {"note": "not measured"}, indent=1)}]
    w.control_text = (("The app's reference library confirmed the program's key and signature, as expected. That library is itself built "
                       "on OpenSSL, so this shows two releases of OpenSSL agree; the exams are the outside check." if same_maker else
                       "An independent library confirmed the program's key and signature, as expected. "
                       "That tells us the program really signs with what it reports."))
    w.fix = None
