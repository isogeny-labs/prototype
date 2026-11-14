"""The five local test servers for the migration demo file (phase 4a). DEMO ONLY.

They exist so the post-quantum migration file can be checked on this computer with no internet. Each binds
127.0.0.1 on a fixed port, with a throwaway test certificate made when it starts:
  8451  hybrid: offers X25519MLKEM768 first, also X25519 and P-256; TLS 1.2 to 1.3; ECDSA P-256 certificate.
        A classical-only client still connects.
  8452  classical: TLS 1.2 to 1.3, key exchange pinned to X25519, ECDSA P-256 certificate (the file says hybrid)
  8453  classical: TLS 1.2 to 1.3, key exchange pinned to P-256, ECDSA P-256 certificate
  8454  legacy: TLS 1.2 only, RSA 2048 certificate, P-256 key exchange, two older ECDHE-RSA ciphers
  8455  post-quantum only: MLKEM768 only, TLS 1.3 only, ML-DSA-65 certificate. Classical-only clients can't connect.

8451 and 8455 run on the copy of OpenSSL inside the `cryptography` library (app.pqtls); 8452 to 8454 on Python's
own ssl module, so they start even when post-quantum TLS is not available here. They start only when asked (when
the migration demo file is imported), never when the app starts. A port another program already uses, or anything
else that stops a server, is reported in plain words and the app carries on.
"""
from __future__ import annotations

import errno
import hashlib
import os
import ssl
import tempfile
import threading

from . import pqtls
from .config import DEMO_DIR, DEMO_HOSTNAME
from .demo_server import TlsServer

MIGRATION_FILE = DEMO_DIR / "migration-demo.csv"
DEFAULT_PORTS = (8451, 8452, 8453, 8454, 8455)
ROLES = ("hybrid", "classical_internet", "classical_internal", "legacy_tls12", "pq_only")

LEGACY_CIPHERS = "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA"


def file_for(ports: tuple[int, ...]) -> bytes:
    """The migration demo file as this app expects it, with the ports this app uses written in."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")
    marks = [f"\x00{i}\x00" for i in range(len(DEFAULT_PORTS))]
    for default, mark in zip(DEFAULT_PORTS, marks):  # two steps, so a port that is another default isn't replaced twice
        text = text.replace(f"{DEMO_HOSTNAME}:{default},", mark)
    for mark, port in zip(marks, ports):
        text = text.replace(mark, f"{DEMO_HOSTNAME}:{port},")
    return text.encode("utf-8")


def _normal(data: bytes) -> bytes:
    return b"\n".join(line.rstrip() for line in data.replace(b"\r\n", b"\n").strip().split(b"\n"))


def is_migration_file(data: bytes, ports: tuple[int, ...]) -> bool:
    """Is this exactly our migration demo file (line endings and trailing spaces aside)?"""
    try:
        return _normal(data) == _normal(file_for(tuple(ports)))
    except (OSError, ValueError):
        return False


def claims_match(claims: list[tuple[str, str, str]], ports: tuple[int, ...]) -> bool:
    """Do these stored claims (location, kind, claimed value) come from the migration demo file?"""
    try:
        from .importers import parse_file
        parsed = parse_file(MIGRATION_FILE.name, file_for(tuple(ports)))
        expected = [(c.location, c.kind, c.claimed_value) for c in parsed.claims]
    except Exception:
        return False
    return list(claims) == expected


def _python_ssl_context(kind: str, common_name: str, *, maximum: ssl.TLSVersion, curves: tuple[str, ...],
                        ciphers: str | None = None) -> tuple[ssl.SSLContext, bytes]:
    """A Python-ssl server context with a fresh test certificate, and that certificate (DER). Python's ssl can
    only load a key from a file: it is written to a private temporary folder and deleted right after loading."""
    cert_pem, key_pem, der = pqtls.test_certificate(kind, common_name)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = maximum
    if ciphers:
        ctx.set_ciphers(ciphers)
    for i, curve in enumerate(curves):  # pinned, so the server stays classical whatever this computer's OpenSSL offers
        try:
            ctx.set_ecdh_curve(curve)
            break
        except (ValueError, ssl.SSLError):
            if i == len(curves) - 1:
                raise
    with tempfile.TemporaryDirectory(prefix="evidence-lab-migration-") as folder:
        os.chmod(folder, 0o700)
        key_path, cert_path = os.path.join(folder, "k.pem"), os.path.join(folder, "c.pem")
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key_pem)
        with open(cert_path, "wb") as fh:
            fh.write(cert_pem)
        ctx.load_cert_chain(cert_path, key_path)
    return ctx, der


def _start(role: str, port: int):
    """Start one server. Returns (server, certificate DER). Raises OSError, ValueError, ssl.SSLError or
    pqtls.PqTlsUnavailable."""
    name = f"demo-{role.replace('_', '-')}"
    if role == "hybrid":
        cert_pem, key_pem, der = pqtls.test_certificate("ecdsa-p256", name)
        return pqtls.Server(groups=pqtls.HYBRID_GROUPS, certificate_pem=cert_pem, key_pem=key_pem,
                            min_version="TLS 1.2", max_version="TLS 1.3", port=port), der
    if role == "pq_only":
        pqtls._require()  # say "can't run post-quantum TLS" before trying to make an ML-DSA key
        cert_pem, key_pem, der = pqtls.test_certificate("mldsa-65", name)
        return pqtls.Server(groups="MLKEM768", certificate_pem=cert_pem, key_pem=key_pem,
                            min_version="TLS 1.3", max_version="TLS 1.3", port=port), der
    if role == "classical_internet":
        ctx, der = _python_ssl_context("ecdsa-p256", name, maximum=ssl.TLSVersion.TLSv1_3, curves=("X25519", "prime256v1"))
    elif role == "classical_internal":
        ctx, der = _python_ssl_context("ecdsa-p256", name, maximum=ssl.TLSVersion.TLSv1_3, curves=("prime256v1",))
    elif role == "legacy_tls12":
        ctx, der = _python_ssl_context("rsa-2048", name, maximum=ssl.TLSVersion.TLSv1_2, curves=("prime256v1",),
                                       ciphers=LEGACY_CIPHERS)
    else:
        raise ValueError(role)
    return TlsServer(ctx, port), der


def file_settings(ports: tuple[int, ...]) -> list[tuple[str, str, str]]:
    """The settings rows of the migration demo file, as (system, field, value), sorted. With claims_match this tells
    a stored import of exactly our demo file from a file that only makes the same claims."""
    try:
        from .importers import parse_file
        parsed = parse_file(MIGRATION_FILE.name, file_for(tuple(ports)))
        return sorted((s.location, s.field, s.value) for s in parsed.settings)
    except Exception:
        return []


class MigrationServers:
    """Owns the five test servers. start() is safe to call again; it never raises."""

    def __init__(self, ports: tuple[int, ...] = DEFAULT_PORTS):
        self.ports = tuple(ports)
        self._servers: dict[int, object] = {}
        self.fingerprints: dict[int, str] = {}  # so a check can tell our own test server from another program on the port
        self.problems: dict[int, str] = {}
        self._lock = threading.Lock()

    def start(self) -> list[str]:
        """Start whichever are not running. Returns one plain sentence per server that could not start."""
        with self._lock:
            for port, role in zip(self.ports, ROLES):
                if port in self._servers:
                    continue
                where = f"{DEMO_HOSTNAME}:{port}"
                try:
                    server, der = _start(role, port)
                    self._servers[port] = server
                    self.fingerprints[port] = hashlib.sha256(der).hexdigest()
                    self.problems.pop(port, None)
                except pqtls.PqTlsUnavailable as exc:
                    reason = str(exc).strip().rstrip(".")
                    self.problems[port] = (f"The demo test server for {where} could not start: this computer's copy of "
                                           f"the cryptography library can't run post-quantum TLS ({reason}). "
                                           "Its row will show Couldn't check.")
                except OSError as exc:
                    if exc.errno == errno.EADDRINUSE:
                        self.problems[port] = (f"Port {port} on this computer is already used by another program, so the "
                                               f"demo test server for {where} could not start. Its row will show Couldn't check.")
                    else:
                        self.problems[port] = (f"The demo test server for {where} could not start "
                                               f"({exc.strerror or exc.__class__.__name__}). Its row will show Couldn't check.")
                except Exception as exc:
                    self.problems[port] = (f"The demo test server for {where} could not be set up "
                                           f"({exc.__class__.__name__}). Its row will show Couldn't check.")
            return [self.problems[p] for p in self.ports if p in self.problems]

    @property
    def running(self) -> list[int]:
        return sorted(self._servers)

    def stop(self) -> None:
        with self._lock:
            for server in self._servers.values():
                try:
                    server.close()
                except Exception:
                    pass
            self._servers.clear()
            self.fingerprints.clear()
