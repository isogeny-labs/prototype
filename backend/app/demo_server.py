"""The demo TLS server ("Acme Pay"), started by the app on 127.0.0.1.

DEMO ONLY. It deliberately accepts TLS 1.2 with an older cipher as well as TLS 1.3, so the demo
claim "TLS 1.3 only" comes back False. Its certificate is a self-signed TEST certificate that is
generated on first start; the test key stays in the data folder (file mode 0600) and is never
printed, logged or stored as evidence.
"""
from __future__ import annotations

import datetime
import errno
import hashlib
import ipaddress
import os
import socket
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .config import BIND_HOST

DEMO_TLS12_CIPHER = "ECDHE-ECDSA-AES128-SHA"  # the "older cipher" (CBC with SHA-1)
DEMO_GROUP = "prime256v1"  # pinned so behaviour is the same on every machine
CERT_FILE = "demo-tls-test-cert.pem"
KEY_FILE = "demo-tls-test-key.pem"


def ensure_demo_certificate(data_dir: Path) -> tuple[Path, Path]:
    """Create the self-signed ECDSA P-256 test certificate if it isn't there (or has expired)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = data_dir / CERT_FILE, data_dir / KEY_FILE
    if cert_path.exists() and key_path.exists():
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            if cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1):
                os.chmod(key_path, 0o600)
                return cert_path, key_path
        except ValueError:
            pass
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Acme Pay Demo (test certificate)"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    for path in (key_path, cert_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem_key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def certificate_fingerprint(cert_path: Path) -> str:
    """SHA-256 of the certificate (public information), hex."""
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def make_server_context(cert_path: Path, key_path: Path, *, ciphers: str = DEMO_TLS12_CIPHER,
                        minimum: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2,
                        maximum: ssl.TLSVersion = ssl.TLSVersion.TLSv1_3,
                        group: str | None = DEMO_GROUP) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = minimum
    ctx.maximum_version = maximum
    ctx.set_ciphers(ciphers)  # TLS 1.2 and older; TLS 1.3 suites are OpenSSL's standard three
    if group:
        ctx.set_ecdh_curve(group)
    ctx.load_cert_chain(str(cert_path), str(key_path))
    return ctx


class TlsServer:
    """A tiny TLS listener: completes the handshake, then closes. It serves no data."""

    def __init__(self, ctx: ssl.SSLContext, port: int = 0, host: str = BIND_HOST):
        self._ctx = ctx
        self._sock = socket.create_server((host, port))
        self._sock.listen(64)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._loop, name="demo-tls-server", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5)
            with self._ctx.wrap_socket(conn, server_side=True):
                pass
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self) -> None:
        for step in (lambda: self._sock.shutdown(socket.SHUT_RDWR), self._sock.close):
            try:
                step()  # shutdown first, so the waiting accept() wakes up and the port is really released
            except OSError:
                pass
        self._thread.join(timeout=2)


class DemoServer:
    """Owns the demo certificate and the demo listener. Never raises if the port is taken."""

    def __init__(self, data_dir: Path, port: int):
        self.data_dir = data_dir
        self.port = port
        self.running = False
        self.error: str | None = None
        self.port_in_use = False
        self.fingerprint: str | None = None
        self._server: TlsServer | None = None

    def start(self) -> None:
        if self.running:
            return
        try:
            cert_path, key_path = ensure_demo_certificate(self.data_dir)
            self.fingerprint = certificate_fingerprint(cert_path)
            ctx = make_server_context(cert_path, key_path)
        except (OSError, ValueError, ssl.SSLError) as exc:
            self.error = f"The demo server could not be set up ({exc.__class__.__name__}). Restart Evidence Lab."
            return
        try:
            self._server = TlsServer(ctx, self.port)
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                self.port_in_use = True
                self.error = (f"Port {self.port} on this computer is already used by another program, so the demo "
                              "server could not start. Close that program and restart Evidence Lab.")
            else:
                self.error = (f"The demo server could not start on port {self.port} "
                              f"({exc.strerror or exc.__class__.__name__}).")
            return
        self.running, self.error = True, None

    def stop(self) -> None:
        if self._server:
            self._server.close()
        self._server, self.running = None, False
