"""Server settings in the lab (phase 4b): one small model of a TLS server's settings, used for the demo test servers,
their test copies, the real nginx in the lab and the change files a person downloads. DEMO AND LAB ONLY.

A setting is plain data:
    {"groups": "X25519MLKEM768:X25519:P-256",      # key-exchange groups, in the server's order of preference
     "versions": ["TLS 1.2", "TLS 1.3"],            # TLS versions it accepts
     "certificate": "ecdsa-p256"}                   # the kind of test certificate it presents: ecdsa-p256 | rsa-2048 | mldsa-65

The same settings are written out as nginx and Apache lines (the lines a person copies, and the exact lines the lab
nginx is given in a try or an Apply). Test keys live in memory only: a test server, a test copy and the lab nginx
each get a throwaway test certificate, and its key is never written to a file the app keeps, shown or exported."""
from __future__ import annotations

import errno
import hashlib
import socket
import threading
from contextlib import contextmanager

from . import pqtls
from .config import BIND_HOST

GROUP_ORDER = ("X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024", "MLKEM768", "MLKEM1024", "X25519", "P-256", "P-384")
VERSION_ORDER = ("TLS 1.0", "TLS 1.1", "TLS 1.2", "TLS 1.3")
CERTIFICATE_WORDS = {"ecdsa-p256": "ECDSA P-256", "rsa-2048": "RSA 2048", "mldsa-65": "ML-DSA-65"}
_NGINX_GROUP = {"P-256": "prime256v1", "P-384": "secp384r1"}
_NGINX_VERSION = {"TLS 1.0": "TLSv1", "TLS 1.1": "TLSv1.1", "TLS 1.2": "TLSv1.2", "TLS 1.3": "TLSv1.3"}


def normal(settings: dict) -> dict:
    """The settings in one fixed form (the same settings always give the same change fingerprint)."""
    groups = [g for g in str(settings.get("groups") or "").split(":") if g]
    versions = [v for v in VERSION_ORDER if v in (settings.get("versions") or [])]
    return {"groups": ":".join(groups), "versions": versions, "certificate": str(settings.get("certificate") or "ecdsa-p256")}


def groups_words(settings: dict) -> str:
    return ", ".join(g for g in normal(settings)["groups"].split(":")) or "the library's default"


def versions_words(settings: dict) -> str:
    vs = [v.replace("TLS ", "") for v in normal(settings)["versions"]]
    return (" and ".join(vs) if len(vs) <= 2 else ", ".join(vs[:-1]) + " and " + vs[-1]) or "none"


# ------------------------------------------------------------------ the lines a person copies

def nginx_lines(settings: dict, certificate_files: bool = False, versions_only: bool = False) -> str:
    """The nginx settings for these settings, in the order they go in a server block. `versions_only`: the TLS versions
    line alone (a change that touches nothing else, so a person's own groups line stays as it is)."""
    s = normal(settings)
    lines = [f"ssl_protocols {' '.join(_NGINX_VERSION[v] for v in s['versions'])};"]
    if not versions_only:
        lines.append(f"ssl_ecdh_curve {':'.join(_NGINX_GROUP.get(g, g) for g in s['groups'].split(':'))};")
    if certificate_files:
        lines += ["ssl_certificate     /etc/nginx/tls/server-mldsa65.crt;", "ssl_certificate_key /etc/nginx/tls/server-mldsa65.key;"]
    return "\n".join(lines)


def apache_lines(settings: dict, certificate_files: bool = False, versions_only: bool = False) -> str:
    s = normal(settings)
    lines = ["SSLProtocol -all " + " ".join("+" + _NGINX_VERSION[v] for v in s["versions"])]
    if not versions_only:
        lines.append(f"SSLOpenSSLConfCmd Groups {':'.join(_NGINX_GROUP.get(g, g) for g in s['groups'].split(':'))}")
    if certificate_files:
        lines += ["SSLCertificateFile    /etc/apache2/tls/server-mldsa65.crt", "SSLCertificateKeyFile /etc/apache2/tls/server-mldsa65.key"]
    return "\n".join(lines)


def application_lines(settings: dict, versions_only: bool = False) -> str:
    s = normal(settings)
    low = s["versions"][0] if s["versions"] else "TLS 1.3"
    first = f'SSL_CTX_set_min_proto_version(ctx, {_NGINX_VERSION[low].replace("TLSv", "TLS").replace(".", "_")}_VERSION);'
    return first if versions_only else first + f'\nSSL_CTX_set1_groups_list(ctx, "{s["groups"]}");'


def nginx_config(settings: dict, port: int) -> str:
    """A whole nginx configuration for the lab nginx: one TLS listener on 127.0.0.1:port that answers every request
    with "204 No Content". The TLS part is exactly nginx_lines(settings)."""
    tls = "\n".join("    " + line for line in nginx_lines(settings).splitlines())
    return f"""worker_processes 1;
pid /run/lab/nginx.pid;
error_log stderr warn;
events {{ worker_connections 64; }}
http {{
  access_log off;
  client_body_temp_path /run/lab/body; proxy_temp_path /run/lab/proxy; fastcgi_temp_path /run/lab/fastcgi;
  uwsgi_temp_path /run/lab/uwsgi; scgi_temp_path /run/lab/scgi;
  server {{
    listen 127.0.0.1:{int(port)} ssl;
    server_name localhost;
    ssl_certificate /run/lab/cert.pem;
    ssl_certificate_key /run/lab/key.pem;
{tls}
    location / {{ return 204; }}
  }}
}}
"""


# ------------------------------------------------------------------ test servers from settings

class LabServer:
    """A test server started from settings, on 127.0.0.1. Keeps its test certificate and key in memory, so a rollback
    can put back exactly the certificate it had."""

    def __init__(self, settings: dict, port: int = 0, common_name: str = "lab-server", keep: tuple[bytes, bytes, bytes] | None = None):
        s = normal(settings)
        if keep is None or keep_kind(keep) != s["certificate"]:
            keep = pqtls.test_certificate(s["certificate"], common_name)
        self.settings, self.certificate = s, keep
        cert_pem, key_pem, der = keep
        versions = s["versions"] or ["TLS 1.3"]
        self.server = pqtls.Server(groups=s["groups"] or None, certificate_pem=cert_pem, key_pem=key_pem,
                                   min_version=versions[0], max_version=versions[-1], port=port)
        self.port = self.server.port
        self.fingerprint = hashlib.sha256(der).hexdigest()

    def close(self) -> None:
        self.server.close()


def keep_kind(keep: tuple[bytes, bytes, bytes]) -> str:
    """The kind of a kept test certificate (from its DER), to know whether it can be reused for new settings."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    key = x509.load_der_x509_certificate(keep[2]).public_key()
    if isinstance(key, ec.EllipticCurvePublicKey):
        return "ecdsa-p256"
    if isinstance(key, rsa.RSAPublicKey):
        return "rsa-2048"
    return "mldsa-65"


@contextmanager
def test_copy(settings: dict, keep: tuple[bytes, bytes, bytes] | None = None):
    """A test copy of a demo test server with these settings, on a spare port of this computer, closed on exit.
    Yields {"port", "fingerprint", "settings"}. Raises pqtls.PqTlsUnavailable or OSError."""
    server = LabServer(settings, 0, "test-copy", keep)
    try:
        yield {"port": server.port, "fingerprint": server.fingerprint, "settings": server.settings}
    finally:
        server.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind((BIND_HOST, 0))
        return s.getsockname()[1]


def port_taken(exc: OSError) -> bool:
    return exc.errno == errno.EADDRINUSE


_lock = threading.Lock()

__all__ = ["normal", "nginx_lines", "apache_lines", "application_lines", "nginx_config", "LabServer", "test_copy",
           "groups_words", "versions_words", "CERTIFICATE_WORDS", "free_port"]
