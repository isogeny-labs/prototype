"""TLS checks. HANDSHAKES ONLY: connect, negotiate, close. No application data, no load, no attacks.

Every handshake has one of three outcomes:
  accepted - the handshake completed
  refused  - the server answered with a real TLS refusal alert (allow-list below)
  unknown  - we could not tell: our own tooling could not offer it, time-out, connection error, anything else

Decisions never come from a command's exit code; `openssl s_client` output is parsed.
Commands are run from argument lists (never a shell), with stdin closed and a time limit.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import socket
import ssl
import struct
import subprocess
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .names import GROUPS, TLS_VERSIONS

WIDEST_CIPHERS = "ALL:COMPLEMENTOFALL:@SECLEVEL=0"
MAX_HANDSHAKES_PER_ADDRESS = 80
CONNECT_TIMEOUT = 3.0
CLI_TIMEOUT = 8.0

_PY_VERSIONS = {
    "TLS 1.0": ssl.TLSVersion.TLSv1, "TLS 1.1": ssl.TLSVersion.TLSv1_1,
    "TLS 1.2": ssl.TLSVersion.TLSv1_2, "TLS 1.3": ssl.TLSVersion.TLSv1_3,
}
_RAW_VERSIONS = {"TLS 1.0": (3, 1), "TLS 1.1": (3, 2), "TLS 1.2": (3, 3)}
# Errors that come from OUR side (the checker could not make the offer): never proof of anything.
LOCAL_REASONS = {"NO_PROTOCOLS_AVAILABLE", "NO_CIPHERS_AVAILABLE", "NO_CIPHER_MATCH", "UNSUPPORTED_PROTOCOL",
                 "NO_SUITABLE_KEY_SHARE", "NO_SUITABLE_GROUPS", "LIBRARY_HAS_NO_CIPHERS"}
# Alerts a server sends to say "no" to what was offered (cipher-suite and group probes).
# For a per-VERSION probe only VERSION_REFUSAL_REASON counts: the other two can be about the cipher
# suites or anything else in the offer, so they do not prove the server refuses that TLS version.
VERSION_REFUSAL_REASON = "TLSV1_ALERT_PROTOCOL_VERSION"
NOT_ABOUT_VERSION = "the server said no to what we offered, but not specifically to this TLS version"
REFUSAL_REASONS = {"TLSV1_ALERT_PROTOCOL_VERSION", "SSLV3_ALERT_HANDSHAKE_FAILURE",
                   "TLSV1_ALERT_INSUFFICIENT_SECURITY"}
REFUSAL_ALERT_NUMBERS = {40: "handshake_failure", 70: "protocol_version", 71: "insufficient_security"}
TLS13_SUITES = ["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256",
                "TLS_AES_128_CCM_SHA256", "TLS_AES_128_CCM_8_SHA256"]

PY_TOOL = "Python ssl module"
PY_TOOL_VERSION = f"{ssl.OPENSSL_VERSION} (Python {platform.python_version()})"
RAW_TOOL = "Python socket (hand-built ClientHello)"
RAW_TOOL_VERSION = f"Python {platform.python_version()}"
CLI_TOOL = "openssl s_client"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Observation:
    status: str  # accepted | refused | unknown
    detail: str
    cipher: str | None = None
    der: bytes | None = None
    version: str | None = None


@dataclass
class Evidence:
    title: str
    command: str
    output: str
    started_at: str
    duration_ms: int
    tool: str
    tool_version: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CipherScan:
    accepted: list[str] = field(default_factory=list)
    complete: bool = False
    why_incomplete: str | None = None


_openssl_cli_cache: tuple[str | None, str] | None = None


def openssl_cli() -> tuple[str | None, str]:
    """(path to the openssl program or None, its `openssl version` output)."""
    global _openssl_cli_cache
    if _openssl_cli_cache is None:
        path = shutil.which("openssl")
        version = "not installed"
        if path:
            try:
                out = subprocess.run([path, "version"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                     timeout=5)
                version = (out.stdout or out.stderr).strip() or "unknown"
            except (OSError, subprocess.SubprocessError):
                path, version = None, "could not be run"
        _openssl_cli_cache = (path, version)
    return _openssl_cli_cache


def classify_s_client(output: str, want_version: str = "TLSv1.3", want_suite: str | None = None) -> tuple[str, str]:
    """Read `openssl s_client -brief` output. Returns (accepted|refused|unknown, short reason)."""
    if "CONNECTION ESTABLISHED" in output:
        m = re.search(r"Protocol version: (\S+)", output)
        s = re.search(r"Ciphersuite: (\S+)", output)
        if m and m.group(1) == want_version and (want_suite is None or (s and s.group(1) == want_suite)):
            return "accepted", f"handshake completed ({m.group(1)}, {s.group(1) if s else 'suite not shown'})"
        return "unknown", "handshake completed but not with what was offered"
    m = re.search(r"SSL alert number (\d+)", output)
    if m:
        number = int(m.group(1))
        if number in REFUSAL_ALERT_NUMBERS:
            return "refused", f"server alert {number} ({REFUSAL_ALERT_NUMBERS[number]})"
        return "unknown", f"unexpected server alert {number}"
    return "unknown", "no TLS answer we can interpret"


def describe_certificate(der: bytes) -> dict:
    """Key type, curve, key size and signature algorithm of a certificate (parsed with `cryptography`)."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa

    cert = x509.load_der_x509_certificate(der)
    key = cert.public_key()
    info: dict = {
        "subject": cert.subject.rfc4514_string(),
        "signature_algorithm": getattr(cert.signature_algorithm_oid, "_name", None) or cert.signature_algorithm_oid.dotted_string,
        "sha256_fingerprint": hashlib.sha256(der).hexdigest(),
        "curve": None, "key_size": None,
    }
    if isinstance(key, ec.EllipticCurvePublicKey):
        info.update(key_type="EC", curve=key.curve.name, key_size=key.key_size)
    elif isinstance(key, rsa.RSAPublicKey):
        info.update(key_type="RSA", key_size=key.key_size)
    elif isinstance(key, ed25519.Ed25519PublicKey):
        info.update(key_type="Ed25519", key_size=256)
    elif isinstance(key, ed448.Ed448PublicKey):
        info.update(key_type="Ed448", key_size=456)
    else:
        info.update(key_type=type(key).__name__)
    return info


class ProbeSession:
    """All handshakes for ONE address in one Verify run: sequential, counted and capped.

    Connections always go to `ip` (the address the user confirmed). `server_name` is only sent as SNI.
    """

    def __init__(self, ip: str, port: int, server_name: str | None, max_handshakes: int = MAX_HANDSHAKES_PER_ADDRESS,
                 timeout: float = CONNECT_TIMEOUT):
        self.ip, self.port, self.server_name = ip, port, server_name
        self.max_handshakes = max_handshakes
        self.timeout = timeout
        self.handshakes = 0
        self.target = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
        self._versions: dict[str, Observation] | None = None
        self._versions_evidence: list[Evidence] = []
        self._unreachable: str | None = None  # set when the address does not answer at all; we then stop trying

    # ---------------------------------------------------------------- single handshakes

    def _take(self) -> str | None:
        """Count one more handshake. Returns a reason instead if this handshake must not be made."""
        if self._unreachable:
            return f"not tried again, because an earlier handshake got no answer: {self._unreachable}"
        if self.handshakes >= self.max_handshakes:
            return f"handshake limit of {self.max_handshakes} for this address reached"
        self.handshakes += 1
        return None

    def _context(self, version: str, ciphers: str) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # we only look at what the server offers; trust is not the question here
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx.minimum_version = ctx.maximum_version = _PY_VERSIONS[version]
        ctx.set_ciphers(ciphers)
        return ctx

    def handshake(self, version: str, ciphers: str = WIDEST_CIPHERS, version_probe: bool = False) -> Observation:
        """One handshake offering exactly `version`, made with Python's ssl module.

        `version_probe=True` asks "does the server accept this TLS version?": only a protocol_version alert
        is then a refusal. Otherwise (cipher scans) the wider list of refusal alerts applies."""
        try:
            ctx = self._context(version, ciphers)
        except (ssl.SSLError, ValueError) as exc:
            return Observation("unknown", f"this computer's TLS library cannot offer {version} ({_reason(exc)})")
        blocked = self._take()
        if blocked:
            return Observation("unknown", blocked)
        try:
            sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        except OSError as exc:
            self._unreachable = f"could not connect ({_os_reason(exc)})"
            return Observation("unknown", self._unreachable)
        try:
            with ctx.wrap_socket(sock, server_hostname=self.server_name) as tls:
                name = tls.cipher()[0] if tls.cipher() else None
                return Observation("accepted", f"handshake completed ({tls.version()}, {name})", cipher=name,
                                   der=tls.getpeercert(True), version=tls.version())
        except ssl.SSLError as exc:
            reason = _reason(exc)
            if reason in REFUSAL_REASONS:
                if version_probe and reason != VERSION_REFUSAL_REASON:
                    return Observation("unknown", f"{NOT_ABOUT_VERSION} (server alert {reason})")
                return Observation("refused", f"server alert {reason}")
            if reason in LOCAL_REASONS:
                return Observation("unknown", f"this computer's TLS library cannot offer {version} ({reason})")
            return Observation("unknown", f"handshake failed in a way we can't interpret ({reason})")
        except (socket.timeout, TimeoutError):
            self._unreachable = "no answer before the time limit"
            return Observation("unknown", self._unreachable)
        except OSError as exc:
            return Observation("unknown", f"connection closed without a TLS answer ({_os_reason(exc)})")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def raw_hello(self, version: str) -> Observation:
        """Fallback when the local TLS library cannot offer an old version: send one hand-built ClientHello
        and read the server's first answer. Only a protocol_version alert counts as a refusal here, because
        this hello offers a short cipher list."""
        ver = _RAW_VERSIONS[version]
        blocked = self._take()
        if blocked:
            return Observation("unknown", blocked)
        suites = [0xC009, 0xC00A, 0xC013, 0xC014, 0x002F, 0x0035, 0x000A, 0xC02B, 0xC02F, 0x009C, 0x0033, 0x0039,
                  0x0016, 0xC012, 0xC008, 0x0005, 0x0004]
        cs = b"".join(struct.pack("!H", c) for c in suites)
        ext = struct.pack("!HHH", 0x000A, 8, 6) + struct.pack("!HHH", 23, 24, 29)
        ext += struct.pack("!HHBB", 0x000B, 2, 1, 0)
        ext += struct.pack("!HHH", 0x000D, 10, 8) + bytes([4, 3, 4, 1, 2, 3, 2, 1])
        if self.server_name:
            sni = self.server_name.encode("ascii")
            ext += struct.pack("!HHHBH", 0, len(sni) + 5, len(sni) + 3, 0, len(sni)) + sni
        body = bytes(ver) + os.urandom(32) + b"\x00" + struct.pack("!H", len(cs)) + cs + b"\x01\x00"
        body += struct.pack("!H", len(ext)) + ext
        hs = b"\x01" + struct.pack("!I", len(body))[1:] + body
        record = b"\x16\x03\x01" + struct.pack("!H", len(hs)) + hs
        try:
            with socket.create_connection((self.ip, self.port), timeout=self.timeout) as s:
                s.sendall(record)
                head = _recv_exact(s, 5)
                if len(head) < 5:
                    return Observation("unknown", "connection closed without a TLS answer")
                payload = _recv_exact(s, min(struct.unpack("!H", head[3:5])[0], 16384))
        except OSError as exc:
            return Observation("unknown", f"could not connect ({_os_reason(exc)})")
        if head[0] == 0x15 and len(payload) >= 2:
            if payload[1] == 70:
                return Observation("refused", "server alert 70 (protocol_version)")
            return Observation("unknown", f"server alert {payload[1]} to a short cipher list (not proof of refusal)")
        if head[0] == 0x16 and payload[:1] == b"\x02" and len(payload) >= 6:
            got = tuple(payload[4:6])
            if got == ver:
                return Observation("accepted", f"server answered ServerHello choosing {version}", version=version)
            return Observation("unknown", f"server answered with a different version {got}")
        return Observation("unknown", "the answer was not a TLS handshake message")

    def s_client(self, args: list[str]) -> tuple[list[str], str | None, str | None]:
        """Run one `openssl s_client` handshake. Returns (argument list, combined output, why it was not run)."""
        path, _ = openssl_cli()
        argv = ["openssl", "s_client", "-connect", self.target, "-brief"]
        argv += ["-servername", self.server_name] if self.server_name else ["-noservername"]
        argv += args
        if not path:
            return argv, None, "the openssl command-line tool is not installed on this computer"
        blocked = self._take()
        if blocked:
            return argv, None, blocked
        try:
            done = subprocess.run([path, *argv[1:]], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=CLI_TIMEOUT, errors="replace")
        except subprocess.TimeoutExpired:
            return argv, "(no answer before the time limit)", None
        except OSError as exc:
            return argv, f"(openssl could not be run: {exc.__class__.__name__})", None
        return argv, (done.stdout + done.stderr)[:4000], None

    # ---------------------------------------------------------------- checks made of several handshakes

    def versions(self) -> tuple[dict[str, Observation], list[Evidence]]:
        """Which of TLS 1.0-1.3 the server accepts. Run once per session and reused."""
        if self._versions is not None:
            return self._versions, self._versions_evidence
        started, t0 = _now(), time.perf_counter()
        results: dict[str, Observation] = {}
        lines, raw_lines = [], []
        for version in reversed(TLS_VERSIONS):  # newest first
            obs = self.handshake(version, version_probe=True)
            lines.append(f"{version}: {obs.status} - {obs.detail}")
            if obs.status == "unknown" and "cannot offer" in obs.detail and version in _RAW_VERSIONS:
                t1 = time.perf_counter()
                obs = self.raw_hello(version)
                raw_lines.append((version, obs, _now(), int((time.perf_counter() - t1) * 1000)))
            results[version] = obs
        evidence = [Evidence(
            title="TLS versions: one handshake per version",
            command=(f"python ssl: connect to {self.target}{self._sni_words()}, offer exactly one TLS version per "
                     f"handshake (1.3, 1.2, 1.1, 1.0), cipher list {WIDEST_CIPHERS}, then close"),
            output="\n".join(lines), started_at=_iso(started),
            duration_ms=int((time.perf_counter() - t0) * 1000), tool=PY_TOOL, tool_version=PY_TOOL_VERSION)]
        for version, obs, when, ms in raw_lines:
            evidence.append(Evidence(
                title=f"{version}: second try with a hand-built ClientHello",
                command=f"python socket: send one {version} ClientHello to {self.target}{self._sni_words()}, read the first answer, close",
                output=f"{version}: {obs.status} - {obs.detail}", started_at=_iso(when), duration_ms=ms,
                tool=RAW_TOOL, tool_version=RAW_TOOL_VERSION))
        self._versions, self._versions_evidence = results, evidence
        return results, evidence

    def first_certificate(self) -> bytes | None:
        versions, _ = self.versions()
        for version in reversed(TLS_VERSIONS):
            if versions[version].der:
                return versions[version].der
        return None

    def old_version_ciphers(self, version: str) -> tuple[CipherScan, Evidence]:
        """Every cipher suite the server accepts on TLS 1.2 or older: handshake, remove the suite the server
        chose, repeat until the server refuses what is left."""
        started, t0 = _now(), time.perf_counter()
        scan, lines = CipherScan(), []
        try:
            names = [c["name"] for c in self._context(version, WIDEST_CIPHERS).get_ciphers()
                     if c.get("protocol") != "TLSv1.3"]
        except (ssl.SSLError, ValueError) as exc:
            names, scan.why_incomplete = [], f"this computer's TLS library cannot offer {version} ({_reason(exc)})"
        offered = len(names)
        while names and scan.why_incomplete is None:
            obs = self.handshake(version, ":".join(names) + ":@SECLEVEL=0")
            lines.append(f"offered {len(names)} suites: {obs.status} - {obs.detail}")
            if obs.status == "accepted" and obs.cipher in names:
                scan.accepted.append(obs.cipher)
                names.remove(obs.cipher)
            elif obs.status == "refused":
                scan.complete = True
                break
            else:
                scan.why_incomplete = obs.detail
        if not names and scan.why_incomplete is None:
            scan.complete = True
        if not scan.complete:
            lines.append(f"stopped early: {scan.why_incomplete}")
        return scan, Evidence(
            title=f"{version} cipher suites",
            command=(f"python ssl: connect to {self.target}{self._sni_words()}, offer {version} with all {offered} suites "
                     f"this computer knows ({WIDEST_CIPHERS}); after each completed handshake remove the chosen suite and repeat"),
            output="\n".join(lines) or "(nothing offered)", started_at=_iso(started),
            duration_ms=int((time.perf_counter() - t0) * 1000), tool=PY_TOOL, tool_version=PY_TOOL_VERSION)

    def _cli_series(self, title: str, items: list[tuple[str, list[str], str | None]]) -> tuple[dict[str, str], Evidence]:
        started, t0 = _now(), time.perf_counter()
        _, cli_version = openssl_cli()
        statuses: dict[str, str] = {}
        commands, outputs = [], []
        for label, args, want_suite in items:
            argv, output, not_run = self.s_client(args)
            commands.append(" ".join(argv))
            if output is None:
                status, why, output = "unknown", not_run, "(not run)"
            else:
                status, why = classify_s_client(output, "TLSv1.3", want_suite)
            statuses[label] = status
            outputs.append(f"$ {' '.join(argv)}\n{output.strip()}\n=> {label}: {status} - {why}")
        return statuses, Evidence(title=title, command="\n".join(commands), output="\n\n".join(outputs),
                                  started_at=_iso(started), duration_ms=int((time.perf_counter() - t0) * 1000),
                                  tool=CLI_TOOL, tool_version=cli_version)

    def tls13_ciphers(self) -> tuple[dict[str, str], Evidence]:
        return self._cli_series("TLS 1.3 cipher suites: one handshake per suite",
                                [(s, ["-tls1_3", "-ciphersuites", s], s) for s in TLS13_SUITES])

    def tls13_groups(self) -> tuple[dict[str, str], Evidence]:
        return self._cli_series("TLS 1.3 key-exchange groups: one handshake per group",
                                [(g, ["-tls1_3", "-groups", cli_name], None) for g, cli_name in GROUPS.items()])

    def count_evidence(self) -> Evidence:
        return Evidence(
            title="Handshake count",
            command="(count kept by Evidence Lab)",
            output=(f"{self.handshakes} handshakes were made to {self.target} in this run, one at a time. "
                    f"The limit is {self.max_handshakes} per address. Handshakes only: no data was sent or requested."),
            started_at=_iso(_now()), duration_ms=0, tool="Evidence Lab", tool_version="phase 1")

    def _sni_words(self) -> str:
        return f" (server name {self.server_name})" if self.server_name else ""


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _reason(exc: Exception) -> str:
    return getattr(exc, "reason", None) or exc.__class__.__name__


def _os_reason(exc: OSError) -> str:
    return exc.strerror or exc.__class__.__name__
