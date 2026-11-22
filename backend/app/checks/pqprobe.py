"""The post-quantum key-exchange probe (phase 4a). HANDSHAKES ONLY, and less: one hand-built first message
(a TLS 1.3 ClientHello) per question, then the server's first answer is read and the connection is closed.

Each hello offers ONE family of key exchange and attaches no key. A server that supports any group of that
family must then name the group it wants (a HelloRetryRequest: "send me a key for X"). A server that supports
none answers with a TLS refusal alert. So the question "does this server offer hybrid post-quantum key
exchange?" is answered without any post-quantum crypto on our side: it works in demo mode with no Docker.

Three outcomes, as everywhere in the TLS checks:
  offered - the server named a group of the family we offered (HelloRetryRequest or ServerHello, TLS 1.3)
  refused - the server answered with a real TLS refusal alert (40, 70 or 71)
  unclear - anything else: no answer, a closed connection, a time-out, another alert, an answer we can't read
Nothing here decides a status: reviewer.py does, from these raw answers."""
from __future__ import annotations

import os
import socket
import struct
import time

from app.checks.tlsprobe import REFUSAL_ALERT_NUMBERS, RAW_TOOL, RAW_TOOL_VERSION, Evidence, ProbeSession, _iso, _now, _os_reason, _recv_exact

# TLS supported-group numbers (IANA registry) and the names shown on screen.
GROUPS = {
    0x11EC: "X25519MLKEM768", 0x11EB: "SecP256r1MLKEM768", 0x11ED: "SecP384r1MLKEM1024",
    0x0201: "MLKEM768", 0x0202: "MLKEM1024", 0x0200: "MLKEM512",
    0x001D: "X25519", 0x0017: "P-256", 0x0018: "P-384",
}
FAMILIES = {
    "hybrid": [0x11EC, 0x11EB, 0x11ED],     # classical and post-quantum combined in one exchange
    "pure": [0x0201, 0x0202, 0x0200],       # ML-KEM by itself
    "classical": [0x001D, 0x0017, 0x0018],
}
FAMILY_WORDS = {"hybrid": "only hybrid key exchanges", "pure": "only ML-KEM by itself", "classical": "only classical key exchanges"}
HYBRID_NAMES = tuple(GROUPS[g] for g in FAMILIES["hybrid"])
PURE_NAMES = tuple(GROUPS[g] for g in FAMILIES["pure"])
CLASSICAL_NAMES = ("X25519", "P-256", "P-384", "P-521", "X448")
# A ServerHello whose random is this value is a HelloRetryRequest (RFC 8446, section 4.1.3).
HRR_RANDOM = bytes.fromhex("CF21AD74E59A6111BE1D8C021E65B891C2A211167ABB8C5E079E09E2C8A8339C")
# Signature types the hello says it understands. ML-DSA is listed too (we never have to check a signature here),
# or a server with only a post-quantum certificate would refuse the hello for that reason alone.
_SIGNATURES = (0x0905, 0x0904, 0x0906, 0x0403, 0x0503, 0x0603, 0x0807, 0x0808, 0x0804, 0x0805, 0x0806, 0x0401, 0x0501, 0x0601)
_SUITES = (0x1301, 0x1302, 0x1303)


def family_of(group: str | None) -> str | None:
    if group in HYBRID_NAMES:
        return "hybrid"
    if group in PURE_NAMES:
        return "pure"
    return "classical" if group in CLASSICAL_NAMES else None


def build_hello(groups: list[int], server_name: str | None) -> bytes:
    """One TLS record holding a TLS 1.3 ClientHello that offers exactly these groups and no key share."""
    def ext(kind: int, data: bytes) -> bytes:
        return struct.pack("!HH", kind, len(data)) + data

    exts = b""
    if server_name:
        name = server_name.encode("ascii", "ignore")
        exts += ext(0, struct.pack("!HBH", len(name) + 3, 0, len(name)) + name)
    exts += ext(43, b"\x02\x03\x04")                                                    # supported_versions: TLS 1.3 only
    listed = b"".join(struct.pack("!H", g) for g in groups)
    exts += ext(10, struct.pack("!H", len(listed)) + listed)                            # supported_groups
    sigs = b"".join(struct.pack("!H", s) for s in _SIGNATURES)
    exts += ext(13, struct.pack("!H", len(sigs)) + sigs)                                # signature_algorithms
    exts += ext(51, b"\x00\x00")                                                        # key_share: none, on purpose
    suites = b"".join(struct.pack("!H", s) for s in _SUITES)
    body = b"\x03\x03" + os.urandom(32) + b"\x20" + os.urandom(32) + struct.pack("!H", len(suites)) + suites + b"\x01\x00"
    body += struct.pack("!H", len(exts)) + exts
    message = b"\x01" + struct.pack("!I", len(body))[1:] + body
    return b"\x16\x03\x01" + struct.pack("!H", len(message)) + message


def read_answer(sock: socket.socket) -> dict:
    """The server's first answer: {"kind", "group", "alert", "tls13", "detail"}."""
    head = _recv_exact(sock, 5)
    if len(head) < 5:
        return {"kind": "closed", "group": None, "alert": None, "tls13": None, "detail": "connection closed without a TLS answer"}
    payload = _recv_exact(sock, min(struct.unpack("!H", head[3:5])[0], 16384))
    if head[0] == 0x15 and len(payload) >= 2:
        number = payload[1]
        name = REFUSAL_ALERT_NUMBERS.get(number)
        return {"kind": "alert", "group": None, "alert": number, "tls13": None,
                "detail": f"server alert {number} ({name})" if name else f"server alert {number}"}
    if head[0] == 0x16 and payload[:1] == b"\x02" and len(payload) >= 44:
        try:
            p = 4 + 2
            random = payload[p:p + 32]
            p += 32
            p += 1 + payload[p]          # session id echo
            p += 2 + 1                   # cipher suite, compression
            end = p + 2 + struct.unpack("!H", payload[p:p + 2])[0]
            p += 2
            version, group = None, None
            while p + 4 <= min(end, len(payload)):
                kind, length = struct.unpack("!HH", payload[p:p + 4])
                data = payload[p + 4:p + 4 + length]
                p += 4 + length
                if kind == 43 and len(data) == 2:
                    version = data
                if kind == 51 and len(data) >= 2:
                    group = struct.unpack("!H", data[:2])[0]
        except (IndexError, struct.error):
            return {"kind": "other", "group": None, "alert": None, "tls13": None, "detail": "a ServerHello we could not read"}
        retry = random == HRR_RANDOM
        name = GROUPS.get(group, f"group {group:#06x}") if group is not None else None
        words = "asked for a key for" if retry else "chose"
        return {"kind": "hello_retry_request" if retry else "server_hello", "group": name, "alert": None,
                "tls13": version == b"\x03\x04",
                "detail": f"server {words} {name}" if name else "server answered without naming a key-exchange group"}
    return {"kind": "other", "group": None, "alert": None, "tls13": None, "detail": "the answer was not a TLS handshake message"}


def offer(session: ProbeSession, family: str) -> dict:
    """Send one hello that offers only `family` to the session's address. Returns the raw answer and its state."""
    offered = [GROUPS[g] for g in FAMILIES[family]]
    out = {"family": family, "offered": offered, "state": "unclear", "group": None, "alert": None, "kind": "not_sent",
           "detail": "", "hello_bytes": 0, "duration_ms": 0, "started_at": _iso(_now())}
    blocked = session._take()
    if blocked:
        out["detail"] = blocked
        return out
    hello = build_hello(FAMILIES[family], session.server_name)
    out["hello_bytes"] = len(hello) - 5
    t0 = time.perf_counter()
    try:
        with socket.create_connection((session.ip, session.port), timeout=session.timeout) as sock:
            sock.sendall(hello)
            answer = read_answer(sock)
    except (socket.timeout, TimeoutError):
        answer = {"kind": "timeout", "group": None, "alert": None, "tls13": None, "detail": "no answer before the time limit"}
    except OSError as exc:
        answer = {"kind": "error", "group": None, "alert": None, "tls13": None, "detail": f"could not connect ({_os_reason(exc)})"}
    out.update(kind=answer["kind"], group=answer["group"], alert=answer["alert"], detail=answer["detail"],
               duration_ms=int((time.perf_counter() - t0) * 1000))
    if answer["kind"] in ("hello_retry_request", "server_hello") and answer["tls13"] and answer["group"] in offered:
        out["state"] = "offered"
    elif answer["kind"] == "alert" and answer["alert"] in REFUSAL_ALERT_NUMBERS:
        out["state"] = "refused"
    elif answer["kind"] in ("hello_retry_request", "server_hello"):
        out["detail"] += " (not one we offered, or not TLS 1.3)"
    return out


def offer_all(session: ProbeSession) -> dict[str, dict]:
    return {family: offer(session, family) for family in ("hybrid", "pure", "classical")}


def evidence(session: ProbeSession, probes: dict[str, dict], title: str = "Key-exchange probe: three hellos with no key attached") -> Evidence:
    lines = [f"offered {FAMILY_WORDS[f]} ({', '.join(p['offered'])}): {p['state']} - {p['detail']}" for f, p in probes.items()]
    started = min((p["started_at"] for p in probes.values()), default=_iso(_now()))
    return Evidence(
        title=title,
        command=(f"python socket: for each family send one hand-built TLS 1.3 ClientHello to {session.target}{session._sni_words()} "
                 "that offers only that family's groups and no key share, read the server's first answer, close"),
        output="\n".join(lines), started_at=started, duration_ms=sum(p["duration_ms"] for p in probes.values()),
        tool=RAW_TOOL, tool_version=RAW_TOOL_VERSION)
