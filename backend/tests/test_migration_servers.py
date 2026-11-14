"""Phase 4a: the five local test servers of the migration demo file."""
import hashlib
import socket
import ssl
import tempfile
import types

import pytest

from app import migration_servers, pqtls
from app.migration_servers import DEFAULT_PORTS, MigrationServers
from conftest import free_port

LOCAL = "127.0.0.1"

DEMO_FILE = """location,type,claim,value
localhost:8451,tls,post_quantum,hybrid
localhost:8451,system,exposure,internet-facing
localhost:8451,system,data_lifespan,long-lived
localhost:8452,tls,post_quantum,hybrid
localhost:8452,system,exposure,internet-facing
localhost:8452,system,data_lifespan,long-lived
localhost:8453,tls,post_quantum,classical
localhost:8453,system,exposure,internal
localhost:8453,system,data_lifespan,short
localhost:8454,tls,post_quantum,classical
localhost:8454,system,exposure,internal
localhost:8454,system,data_lifespan,long-lived
localhost:8454,system,can_change,no
localhost:8455,tls,post_quantum,post-quantum only
localhost:8455,system,data_lifespan,long-lived
acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256
acme-sign 1.4.2,system,data_lifespan,long-lived
acme-sign 9.9,software,signature_algorithm,ECDSA P-256
"""


@pytest.fixture(autouse=True)
def demo_file(tmp_path, monkeypatch):
    path = tmp_path / "migration-demo.csv"
    path.write_text(DEMO_FILE, encoding="utf-8")
    monkeypatch.setattr(migration_servers, "MIGRATION_FILE", path)
    return path


def spare_ports() -> tuple[int, ...]:
    ports: list[int] = []
    while len(ports) < 5:
        port = free_port()
        if port not in ports:
            ports.append(port)
    return tuple(ports)


@pytest.fixture
def started(tmp_path, monkeypatch):
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    servers = MigrationServers(spare_ports())
    problems = servers.start()
    yield servers, problems, folder
    servers.stop()


def python_client(port: int, *, maximum=ssl.TLSVersion.TLSv1_3, minimum=ssl.TLSVersion.TLSv1_2):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    ctx.minimum_version, ctx.maximum_version = minimum, maximum
    with socket.create_connection((LOCAL, port), timeout=5) as raw, ctx.wrap_socket(raw) as tls:
        return tls.version(), tls.cipher()[0], hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()


def test_five_servers_behave_as_specified(started):
    servers, problems, folder = started
    hybrid, internet, internal, legacy, pq_only = servers.ports
    assert problems == [] and servers.problems == {}
    assert servers.running == sorted(servers.ports)
    assert set(servers.fingerprints) == set(servers.ports)

    # 1. hybrid: post-quantum first, a classical-only client still connects
    h = pqtls.handshake(LOCAL, hybrid, "localhost", "X25519MLKEM768")
    assert (h.outcome, h.group) == ("completed", "X25519MLKEM768")
    assert hashlib.sha256(h.certificate_der).hexdigest() == servers.fingerprints[hybrid]
    assert pqtls.handshake(LOCAL, hybrid, None, "X25519").group == "X25519"
    assert python_client(hybrid)[0] == "TLSv1.3"
    assert python_client(hybrid, maximum=ssl.TLSVersion.TLSv1_2)[0] == "TLSv1.2"

    # 2 and 3. classical: no post-quantum key exchange, pinned groups
    for port, group in ((internet, "X25519"), (internal, "P-256")):
        refused = pqtls.handshake(LOCAL, port, None, "X25519MLKEM768")
        assert (refused.outcome, refused.alert) == ("refused", 40)
        ok = pqtls.handshake(LOCAL, port, None, "X25519MLKEM768:X25519:P-256")
        assert (ok.outcome, ok.group, ok.tls_version) == ("completed", group, "TLS 1.3")
        assert hashlib.sha256(ok.certificate_der).hexdigest() == servers.fingerprints[port]
        assert python_client(port, maximum=ssl.TLSVersion.TLSv1_2)[0] == "TLSv1.2"
    assert pqtls.handshake(LOCAL, internal, None, "X25519").outcome == "refused"

    # 4. legacy: TLS 1.2 only, RSA certificate, the two older ciphers
    version, cipher, fingerprint = python_client(legacy)
    assert version == "TLSv1.2" and cipher in migration_servers.LEGACY_CIPHERS.split(":")
    assert fingerprint == servers.fingerprints[legacy]
    assert pqtls.handshake(LOCAL, legacy, None, "X25519MLKEM768:X25519:P-256").alert == 70
    old = pqtls.handshake(LOCAL, legacy, None, "X25519MLKEM768:X25519:P-256", min_version="TLS 1.2", max_version="TLS 1.2")
    assert (old.outcome, old.tls_version, old.group) == ("completed", "TLS 1.2", "P-256")
    from app.tlsprobe import describe_certificate
    assert describe_certificate(old.certificate_der)["key_type"] == "RSA"
    assert describe_certificate(old.certificate_der)["key_size"] == 2048

    # 5. post-quantum only: ML-KEM key exchange, ML-DSA-65 certificate, classical clients can't connect
    pq = pqtls.handshake(LOCAL, pq_only, None, "MLKEM768")
    assert (pq.outcome, pq.group, pq.signature_bytes) == ("completed", "MLKEM768", 3309)
    assert hashlib.sha256(pq.certificate_der).hexdigest() == servers.fingerprints[pq_only]
    assert pqtls.handshake(LOCAL, pq_only, None, "X25519MLKEM768:X25519:P-256").outcome == "refused"
    with pytest.raises(ssl.SSLError):
        python_client(pq_only)

    # start() again changes nothing
    before = dict(servers.fingerprints)
    assert servers.start() == []
    assert servers.fingerprints == before

    # the Python-ssl servers loaded their keys from a temporary file that is gone
    for path in folder.rglob("*"):
        assert not (path.is_file() and b"PRIVATE KEY" in path.read_bytes()), path


def test_stop_frees_the_ports(started):
    servers, _, _ = started
    servers.stop()
    assert servers.running == [] and servers.fingerprints == {}
    for port in servers.ports:
        with socket.create_server((LOCAL, port)):
            pass


def test_a_taken_port_is_one_plain_sentence():
    ports = spare_ports()
    with socket.create_server((LOCAL, ports[2])):
        servers = MigrationServers(ports)
        try:
            problems = servers.start()
            assert problems == [f"Port {ports[2]} on this computer is already used by another program, so the demo "
                                f"test server for localhost:{ports[2]} could not start. Its row will show Couldn't check."]
            assert servers.running == sorted(p for p in ports if p != ports[2])
            assert ports[2] not in servers.fingerprints
        finally:
            servers.stop()


def test_without_post_quantum_tls_the_classical_servers_still_run(monkeypatch):
    reason = "The copy of OpenSSL inside the cryptography library could not be loaded."

    def unavailable(*args, **kwargs):
        raise pqtls.PqTlsUnavailable(reason)

    monkeypatch.setattr(pqtls, "_require", unavailable)
    monkeypatch.setattr(pqtls, "Server", unavailable)
    ports = spare_ports()
    servers = MigrationServers(ports)
    try:
        problems = servers.start()
        assert servers.running == sorted(ports[1:4])
        assert problems == [
            f"The demo test server for localhost:{port} could not start: this computer's copy of the cryptography "
            f"library can't run post-quantum TLS (The copy of OpenSSL inside the cryptography library could not be "
            f"loaded). Its row will show Couldn't check." for port in (ports[0], ports[4])]
        for port in ports[1:4]:
            assert python_client(port)[2] == servers.fingerprints[port]
    finally:
        servers.stop()


def test_never_raises_on_an_unexpected_failure(monkeypatch):
    def broken(role, port):
        raise RuntimeError("something odd")

    monkeypatch.setattr(migration_servers, "_start", broken)
    servers = MigrationServers(spare_ports())
    problems = servers.start()
    assert len(problems) == 5 and all("could not be set up (RuntimeError)" in p for p in problems)
    assert servers.running == []


def test_file_for_and_is_migration_file():
    assert migration_servers.file_for(DEFAULT_PORTS) == DEMO_FILE.encode()
    ports = (8452, 8453, 8454, 8455, 9000)  # shifted onto each other: each line moves exactly once
    text = migration_servers.file_for(ports).decode()
    assert text.count("localhost:8452,") == 3 and text.count("localhost:9000,") == 2
    assert text.count("localhost:8451,") == 0
    data = migration_servers.file_for(ports)
    assert migration_servers.is_migration_file(data, ports)
    assert migration_servers.is_migration_file(data.replace(b"\n", b"  \r\n"), ports)
    assert not migration_servers.is_migration_file(data, DEFAULT_PORTS)
    assert not migration_servers.is_migration_file(data.replace(b"internal\n", b"internet-facing\n", 1), ports)
    assert not migration_servers.is_migration_file(data + b"localhost:1,tls,post_quantum,hybrid\n", ports)


def test_is_migration_file_when_the_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(migration_servers, "MIGRATION_FILE", tmp_path / "not-there.csv")
    assert not migration_servers.is_migration_file(DEMO_FILE.encode(), DEFAULT_PORTS)


def _fake_parse(filename, data):
    claims = []
    for line in data.decode().strip().split("\n")[1:]:
        location, kind, claim, value = line.split(",")
        claims.append(types.SimpleNamespace(location=location, kind=f"{kind}:{claim}", claimed_value=value))
    return types.SimpleNamespace(claims=claims)


def test_claims_match(monkeypatch):
    from app import importers
    monkeypatch.setattr(importers, "parse_file", _fake_parse)
    ports = spare_ports()
    claims = [(c.location, c.kind, c.claimed_value) for c in _fake_parse("x", migration_servers.file_for(ports)).claims]
    assert migration_servers.claims_match(claims, ports)
    assert not migration_servers.claims_match(claims[:-1], ports)
    assert not migration_servers.claims_match(claims, DEFAULT_PORTS)

    def broken(filename, data):
        raise ValueError("can't read")

    monkeypatch.setattr(importers, "parse_file", broken)
    assert not migration_servers.claims_match(claims, ports)
