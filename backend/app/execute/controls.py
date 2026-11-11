"""The deliberately broken control servers for the server tests. Each binds 127.0.0.1 on a port the
system picks, uses a throwaway test certificate made for this one run, and is closed when the test ends.
The test key is written to a private temporary folder only long enough to be loaded, then deleted."""
from __future__ import annotations

import datetime
import os
import ssl
import tempfile
import warnings
from contextlib import contextmanager

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from ..demo_server import TlsServer

_VERSIONS = {"TLS 1.0": ssl.TLSVersion.TLSv1, "TLS 1.1": ssl.TLSVersion.TLSv1_1, "TLS 1.2": ssl.TLSVersion.TLSv1_2,
             "TLS 1.3": ssl.TLSVersion.TLSv1_3}
WEAK_RSA_BITS = 1024
# OpenSSL's security level is lowered ONLY on a control server's own context, and only where the control
# cannot exist otherwise: the weak RSA-1024 certificate, and a control that must accept TLS 1.0 or 1.1.
LOWERED_CIPHERS = "ALL:@SECLEVEL=0"


def _context_with_test_certificate(key, common_name: str, lower_security_level: bool) -> ssl.SSLContext:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Evidence Lab control (test certificate)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2)).sign(key, hashes.SHA256()))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if lower_security_level:
        ctx.set_ciphers(LOWERED_CIPHERS)
    with tempfile.TemporaryDirectory(prefix="evidence-lab-control-") as folder:
        os.chmod(folder, 0o700)
        key_path, cert_path = os.path.join(folder, "k.pem"), os.path.join(folder, "c.pem")
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
        with open(cert_path, "wb") as fh:
            fh.write(cert.public_bytes(serialization.Encoding.PEM))
        ctx.load_cert_chain(cert_path, key_path)
    return ctx


@contextmanager
def tls_server_accepting(version: str, claimed: list[str]):
    """A misconfigured test server: it accepts `version` (which the claim says must be refused) as well as
    everything the claim allows."""
    ctx = _context_with_test_certificate(ec.generate_private_key(ec.SECP256R1()), "control-old-tls",
                                         lower_security_level=version in ("TLS 1.0", "TLS 1.1"))
    wanted = [_VERSIONS[v] for v in [version, *claimed] if v in _VERSIONS]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        ctx.minimum_version, ctx.maximum_version = min(wanted), max(wanted)
    server = TlsServer(ctx)
    try:
        yield server.port
    finally:
        server.close()


@contextmanager
def weak_certificate_server():
    """A test server whose certificate has a deliberately weak key (RSA, 1024 bits)."""
    ctx = _context_with_test_certificate(rsa.generate_private_key(65537, WEAK_RSA_BITS), "control-weak-certificate",
                                         lower_security_level=True)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    server = TlsServer(ctx)
    try:
        yield server.port
    finally:
        server.close()
