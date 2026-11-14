"""Phase 4a: real TLS with post-quantum key exchange through the OpenSSL inside the `cryptography` library."""
import socket
import ssl
import tempfile
import types

import pytest

from app import pqtls
from app.tlsprobe import describe_certificate
from conftest import free_port

LOCAL = "127.0.0.1"


def make_server(groups, kind="ecdsa-p256", **more):
    cert_pem, key_pem, der = pqtls.test_certificate(kind, f"test-{kind}")
    return pqtls.Server(groups=groups, certificate_pem=cert_pem, key_pem=key_pem, **more), der


@pytest.fixture
def servers():
    started = []

    def start(groups, kind="ecdsa-p256", **more):
        server, der = make_server(groups, kind, **more)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


def python_ssl_client(port: int) -> str:
    """A classical client: Python's own ssl module (this computer's OpenSSL). Returns the TLS version."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection((LOCAL, port), timeout=5) as raw, ctx.wrap_socket(raw) as tls:
        return tls.version()


def test_available_here():
    usable, text = pqtls.available()
    assert usable, text
    assert "OpenSSL" in text and "inside cryptography" in text


def test_hybrid_server_hybrid_and_classical_clients(servers):
    server = servers(pqtls.HYBRID_GROUPS)
    h = pqtls.handshake(LOCAL, server.port, "localhost", "X25519MLKEM768")
    assert h.outcome == "completed", h.detail
    assert (h.tls_version, h.group) == ("TLS 1.3", "X25519MLKEM768")
    assert h.client_share_bytes == 1216 and h.server_share_bytes == 1120
    assert h.detail == "handshake completed (TLS 1.3, X25519MLKEM768)"
    assert [m["type"] for m in h.messages] == ["ClientHello", "ServerHello", "EncryptedExtensions", "Certificate",
                                               "CertificateVerify", "Finished", "Finished"]
    assert h.messages[0] == {"direction": "sent", "type": "ClientHello", "bytes": h.client_hello_bytes}
    assert h.client_hello_bytes > 1216 and h.duration_ms > 0
    info = describe_certificate(h.certificate_der)
    assert info["key_type"] == "EC" and info["curve"] == "secp256r1"
    assert "test certificate" in info["subject"]
    assert h.certificate_message_bytes == next(m["bytes"] for m in h.messages if m["type"] == "Certificate")
    assert h.signature_bytes and 64 <= h.signature_bytes <= 72  # an ECDSA P-256 signature

    c = pqtls.handshake(LOCAL, server.port, None, "X25519")
    assert (c.outcome, c.group, c.client_share_bytes, c.server_share_bytes) == ("completed", "X25519", 32, 32)

    p = pqtls.handshake(LOCAL, server.port, None, "MLKEM768")
    assert (p.outcome, p.alert) == ("refused", 40)
    assert p.detail == "server alert 40 (handshake_failure)"
    assert p.group is None and p.tls_version is None


def test_hello_retry_request_is_named(servers):
    server = servers(pqtls.CLASSICAL_GROUPS)
    h = pqtls.handshake(LOCAL, server.port, None, "P-384:X25519")  # key share for P-384, which the server lacks
    assert h.outcome == "completed" and h.group == "X25519"
    types_ = [m["type"] for m in h.messages]
    assert types_[:3] == ["ClientHello", "HelloRetryRequest", "ClientHello"]
    assert h.client_hello_bytes == h.messages[0]["bytes"]
    assert h.client_share_bytes == 32 and h.server_share_bytes == 32


def test_classical_server_refuses_hybrid(servers):
    server = servers(pqtls.CLASSICAL_GROUPS)
    h = pqtls.handshake(LOCAL, server.port, None, "X25519MLKEM768")
    assert (h.outcome, h.alert) == ("refused", 40)
    assert pqtls.handshake(LOCAL, server.port, None, "X25519:P-256").outcome == "completed"


def test_pq_only_server_with_mldsa_certificate(servers):
    server = servers("MLKEM768", kind="mldsa-65", min_version="TLS 1.3", max_version="TLS 1.3")
    h = pqtls.handshake(LOCAL, server.port, None, "MLKEM768")
    assert h.outcome == "completed", h.detail
    assert h.group == "MLKEM768"
    assert h.client_share_bytes == 1184 and h.server_share_bytes == 1088
    assert h.signature_bytes == 3309
    assert h.certificate_message_bytes > 5000
    assert describe_certificate(h.certificate_der)["key_type"] != "EC"
    for groups in ("X25519", "X25519:P-256:P-384"):
        c = pqtls.handshake(LOCAL, server.port, None, groups)
        assert (c.outcome, c.alert) == ("refused", 40)
    c = pqtls.handshake(LOCAL, server.port, None, "X25519", min_version="TLS 1.2")
    assert c.outcome == "refused"


def test_python_ssl_client_against_our_servers(servers):
    hybrid = servers(pqtls.HYBRID_GROUPS)
    assert python_ssl_client(hybrid.port) == "TLSv1.3"
    pq_only = servers("MLKEM768", kind="mldsa-65", min_version="TLS 1.3", max_version="TLS 1.3")
    with pytest.raises(ssl.SSLError):
        python_ssl_client(pq_only.port)


def test_tls12_only_server(servers):
    server = servers(pqtls.CLASSICAL_GROUPS, max_version="TLS 1.2")
    # TLS 1.2 with an ECDSA P-256 certificate needs P-256 in the client's group list
    h = pqtls.handshake(LOCAL, server.port, None, "X25519:P-256", min_version="TLS 1.2", max_version="TLS 1.2")
    assert h.outcome == "completed", h.detail
    assert h.tls_version == "TLS 1.2" and h.group == "X25519"
    assert h.client_share_bytes == 32 and h.server_share_bytes == 32
    assert "ServerKeyExchange" in [m["type"] for m in h.messages]
    assert describe_certificate(h.certificate_der)["key_type"] == "EC"
    refused = pqtls.handshake(LOCAL, server.port, None, "X25519:P-256")  # TLS 1.3 only
    assert (refused.outcome, refused.alert) == ("refused", 70)


def test_closed_port_is_unknown_not_an_error():
    h = pqtls.handshake(LOCAL, free_port(), None, "X25519MLKEM768", timeout=2)
    assert h.outcome == "unknown"
    assert h.detail.startswith("could not connect")
    assert h.messages == [] and h.group is None


def test_silent_server_hits_the_time_limit():
    with socket.create_server((LOCAL, 0)) as silent:  # accepts the connection but never answers
        h = pqtls.handshake(LOCAL, silent.getsockname()[1], None, "X25519", timeout=0.5)
    assert h.outcome == "unknown"
    assert h.detail == "no answer before the time limit"


def test_control_servers():
    with pqtls.control_servers() as ports:
        assert set(ports) == {"hybrid", "classical"}
        assert pqtls.handshake(LOCAL, ports["hybrid"], None, "X25519MLKEM768").group == "X25519MLKEM768"
        assert pqtls.handshake(LOCAL, ports["classical"], None, "X25519MLKEM768").outcome == "refused"
        assert pqtls.handshake(LOCAL, ports["classical"], None, "X25519").outcome == "completed"
    for port in ports.values():
        assert pqtls.handshake(LOCAL, port, None, "X25519", timeout=2).detail.startswith("could not connect")


def test_server_port_taken(servers):
    first = servers(pqtls.CLASSICAL_GROUPS)
    with pytest.raises(OSError):
        servers(pqtls.CLASSICAL_GROUPS, port=first.port)


def test_no_private_key_left_on_disk(tmp_path, monkeypatch):
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    server, _ = make_server(pqtls.HYBRID_GROUPS)
    try:
        assert pqtls.handshake(LOCAL, server.port, None, "X25519MLKEM768").outcome == "completed"
    finally:
        server.close()
    for path in folder.rglob("*"):
        assert not (path.is_file() and b"PRIVATE KEY" in path.read_bytes()), path


def test_test_certificates():
    for kind, key_type in (("ecdsa-p256", "EC"), ("rsa-2048", "RSA")):
        cert_pem, key_pem, der = pqtls.test_certificate(kind, "cn-here")
        info = describe_certificate(der)
        assert info["key_type"] == key_type
        assert info["subject"] == "O=Evidence Lab test server (test certificate),CN=cn-here"
        assert b"BEGIN CERTIFICATE" in cert_pem and b"PRIVATE KEY" in key_pem
    _, _, der = pqtls.test_certificate("mldsa-65", "pq")
    assert len(der) > 5000


# ---------------------------------------------------------------------------------------------- unavailable

@pytest.fixture
def fresh_state():
    pqtls._reset()
    yield
    pqtls._reset()


def _check_everything_unavailable(reason_part: str):
    usable, reason = pqtls.available()
    assert usable is False and reason_part in reason
    with pytest.raises(pqtls.PqTlsUnavailable) as exc:
        pqtls.handshake(LOCAL, 1, None, "X25519MLKEM768")
    assert str(exc.value) == reason
    cert_pem, key_pem, _ = pqtls.test_certificate("ecdsa-p256", "still-works")  # certificates don't need the binding
    with pytest.raises(pqtls.PqTlsUnavailable):
        pqtls.Server(groups=None, certificate_pem=cert_pem, key_pem=key_pem)
    with pytest.raises(pqtls.PqTlsUnavailable):
        with pqtls.control_servers():
            pass


def test_binding_import_fails(fresh_state, monkeypatch):
    def broken():
        raise ImportError("no binding in this build")

    monkeypatch.setattr(pqtls, "_load_binding", broken)
    _check_everything_unavailable("could not be loaded")


def test_needed_function_missing(fresh_state, monkeypatch):
    real_ffi, real_lib = pqtls._load_binding()

    class WithoutGroupName:
        def __getattr__(self, name):
            if name == "SSL_get0_group_name":
                raise AttributeError(name)
            return getattr(real_lib, name)

    monkeypatch.setattr(pqtls, "_load_binding", lambda: (real_ffi, WithoutGroupName()))
    _check_everything_unavailable("SSL_get0_group_name")


def test_hybrid_group_not_accepted(fresh_state, monkeypatch):
    real_ffi, real_lib = pqtls._load_binding()
    lib = types.SimpleNamespace(**{name: getattr(real_lib, name) for name in pqtls._REQUIRED})
    lib.SSL_CTX_set1_curves_list = lambda ctx, groups: 0
    monkeypatch.setattr(pqtls, "_load_binding", lambda: (real_ffi, lib))
    _check_everything_unavailable("X25519MLKEM768")


def test_trial_handshake_fails(fresh_state, monkeypatch):
    monkeypatch.setattr(pqtls, "_self_test", lambda ffi, lib: False)
    _check_everything_unavailable("trial post-quantum handshake")


def test_back_to_available_after_reset(fresh_state):
    assert pqtls.available()[0]
