"""The three local test servers for the multi-target demo file (phase 3a-fixes). DEMO ONLY.

They exist so a file with several servers can be checked on this computer with no internet. Each binds
127.0.0.1 on a fixed port, with a throwaway test certificate made when it starts (the same code as the control
servers; the test key never leaves memory except for the instant it is loaded):
  8444  accepts TLS 1.3 only                            -> its "TLS 1.3 only" claim comes back True
  8445  accepts TLS 1.0 to 1.3, ECDSA P-256 certificate -> True, with an "Also noticed" note (TLS 1.0 and 1.1)
  8446  weak RSA-1024 certificate (the file says 2048)   -> False

They start only when the multi-target demo file is imported (and again, if the app was restarted, when that
import is verified or tested), never when the app starts. A port another program already uses is reported in
plain words and the app carries on."""
from __future__ import annotations

import errno
import hashlib
import socket
import ssl
import threading
import warnings

from cryptography.hazmat.primitives.asymmetric import ec, rsa

from .config import DEMO_CBOM_PORT, DEMO_DIR, DEMO_HOSTNAME
from .demo_server import TlsServer

MULTI_TARGET_FILE = DEMO_DIR / "multi-target-demo.csv"
DEFAULT_PORTS = (8444, 8445, 8446)
ROLES = ("tls13_only", "accepts_retired", "weak_certificate")


def _context(role: str) -> ssl.SSLContext:
    from .execute.controls import WEAK_RSA_BITS, _context_with_test_certificate
    if role == "weak_certificate":
        ctx = _context_with_test_certificate(rsa.generate_private_key(65537, WEAK_RSA_BITS), "demo-weak-certificate", True)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx
    old = role == "accepts_retired"
    ctx = _context_with_test_certificate(ec.generate_private_key(ec.SECP256R1()), f"demo-{role.replace('_', '-')}", old)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        ctx.minimum_version = ssl.TLSVersion.TLSv1 if old else ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    return ctx


def file_for(demo_port: int, ports: tuple[int, ...]) -> bytes:
    """The multi-target demo file as this app expects it, with the ports this app uses written in."""
    text = MULTI_TARGET_FILE.read_text(encoding="utf-8")
    for default, port in zip((DEMO_CBOM_PORT, *DEFAULT_PORTS), (demo_port, *ports)):
        text = text.replace(f"{DEMO_HOSTNAME}:{default},", f"{DEMO_HOSTNAME}:{port},")
    return text.encode("utf-8")


def _normal(data: bytes) -> bytes:
    return b"\n".join(line.rstrip() for line in data.replace(b"\r\n", b"\n").strip().split(b"\n"))


def is_multi_target_file(data: bytes, demo_port: int, ports: tuple[int, ...]) -> bool:
    """Is this exactly our multi-target demo file (line endings and trailing spaces aside)?"""
    try:
        return _normal(data) == _normal(file_for(demo_port, ports))
    except OSError:
        return False


def claims_match(claims: list[tuple[str, str, str]], demo_port: int, ports: tuple[int, ...]) -> bool:
    """Do these stored claims (location, kind, claimed value) come from the multi-target demo file?"""
    from .importers import parse_file
    try:
        expected = [(c.location, c.kind, c.claimed_value) for c in parse_file(MULTI_TARGET_FILE.name, file_for(demo_port, ports)).claims]
    except Exception:
        return False
    return claims == expected


def _fingerprint(port: int) -> str:
    """SHA-256 of the certificate our own test server sends (public information), read with one handshake."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    ctx.set_ciphers("ALL:@SECLEVEL=0")  # on this one client context only: the 8446 server's key is deliberately weak
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw, ctx.wrap_socket(raw) as tls:
        return hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()


class ExtraServers:
    """Owns the three test servers. start() is safe to call again; it never raises."""

    def __init__(self, ports: tuple[int, ...] = DEFAULT_PORTS):
        self.ports = tuple(ports)
        self._servers: dict[int, TlsServer] = {}
        self.fingerprints: dict[int, str] = {}  # so a check can tell our own test server from another program on the port
        self.problems: dict[int, str] = {}
        self._lock = threading.Lock()

    def start(self) -> list[str]:
        """Start whichever are not running. Returns one plain sentence per server that could not start."""
        with self._lock:
            for port, role in zip(self.ports, ROLES):
                if port in self._servers:
                    continue
                try:
                    server = TlsServer(_context(role), port)
                    try:
                        self.fingerprints[port] = _fingerprint(server.port)
                    except (OSError, ssl.SSLError):
                        server.close()
                        raise
                    self._servers[port] = server
                    self.problems.pop(port, None)
                except OSError as exc:
                    if exc.errno == errno.EADDRINUSE:
                        self.problems[port] = (f"Port {port} on this computer is already used by another program, so the demo test "
                                               f"server for {DEMO_HOSTNAME}:{port} could not start. Its claims will show Couldn't check.")
                    else:
                        self.problems[port] = (f"The demo test server for {DEMO_HOSTNAME}:{port} could not start "
                                               f"({exc.strerror or exc.__class__.__name__}). Its claims will show Couldn't check.")
                except (ValueError, ssl.SSLError) as exc:
                    self.problems[port] = (f"The demo test server for {DEMO_HOSTNAME}:{port} could not be set up "
                                           f"({exc.__class__.__name__}). Its claims will show Couldn't check.")
            return [self.problems[p] for p in self.ports if p in self.problems]

    @property
    def running(self) -> list[int]:
        return sorted(self._servers)

    def stop(self) -> None:
        with self._lock:
            for server in self._servers.values():
                server.close()
            self._servers.clear()
            self.fingerprints.clear()
