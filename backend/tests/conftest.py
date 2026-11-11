import socket
import ssl
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.demo_server import TlsServer, ensure_demo_certificate, make_server_context  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORD = "test-only-passphrase"  # a throwaway value for tests, not a real credential


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", demo_tls_port=free_port())


@pytest.fixture
def anon_client(settings):
    """The app with a fresh data folder and its demo server on a spare port. Not logged in."""
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def client(anon_client):
    assert anon_client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
    return anon_client


@pytest.fixture(scope="session")
def test_cert(tmp_path_factory):
    return ensure_demo_certificate(tmp_path_factory.mktemp("certs"))


@pytest.fixture
def tls_server(test_cert):
    """Start throwaway TLS servers on spare ports: kind = demo | legacy | tls13only."""
    started = []

    def start(kind: str = "demo") -> int:
        cert, key = test_cert
        if kind == "demo":
            ctx = make_server_context(cert, key)
        elif kind == "legacy":
            ctx = make_server_context(cert, key, ciphers="ALL:@SECLEVEL=0", minimum=ssl.TLSVersion.TLSv1, group=None)
        elif kind == "tls13only":
            ctx = make_server_context(cert, key, minimum=ssl.TLSVersion.TLSv1_3)
        else:
            raise ValueError(kind)
        server = TlsServer(ctx)
        started.append(server)
        return server.port

    yield start
    for server in started:
        server.close()


class CountingListener:
    """A plain TCP listener that never speaks TLS and counts connection attempts."""

    def __init__(self):
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]

    def connections(self) -> int:
        n = 0
        while True:
            try:
                conn, _ = self.sock.accept()
            except BlockingIOError:
                return n
            conn.close()
            n += 1

    def close(self):
        self.sock.close()


@pytest.fixture
def listener():
    item = CountingListener()
    yield item
    item.close()


def csv_bytes(*rows: str) -> bytes:
    return ("location,type,claim,value\n" + "\n".join(rows) + "\n").encode()


def upload(client, name: str, data: bytes):
    return client.post("/api/import/file", params={"filename": name}, content=data,
                       headers={"Content-Type": "application/octet-stream"})
