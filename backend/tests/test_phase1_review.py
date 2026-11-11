"""Tests for the gaps found in the phase 1 review."""
import json
import socket
import threading
from types import SimpleNamespace

import pytest

from app import addresses, importers, tlsprobe
from app.compare import COULDNT, FALSE, TRUE
from app.config import DEMO_CBOM, DEMO_DIR
from app.tlsprobe import NOT_ABOUT_VERSION, ProbeSession
from app.verify import AddressCheck, DemoContext
from conftest import csv_bytes, upload

NO_DEMO = DemoContext(False, "localhost", 1, False, None, None)


def check(port, session_factory=ProbeSession):
    row = SimpleNamespace(address=f"localhost:{port}", host="localhost", port=port, resolved_ip="127.0.0.1",
                          is_loopback=True, confirmed=True, error=None)
    return AddressCheck(row, NO_DEMO, session_factory=session_factory)


# ------------------------------------------------------------------ 1. "only these" claims are never True from a short list

def test_only_these_groups_is_never_true(tls_server):
    c = check(tls_server("demo"))  # this server is pinned to P-256 and really refuses every other group we try
    res = c.key_exchange({"groups": ["P-256"]})
    assert res["result"] == COULDNT
    assert res["reason"] == ("The server accepts the claimed groups and refused the others we tried "
                             "(X25519, P-384, P-521, X448, ffdhe2048, ffdhe3072), but there are groups this checker "
                             "can't offer, so we can't say it uses nothing else.")
    # False is unchanged: a claimed group positively refused, or an unclaimed group positively accepted
    assert c.key_exchange({"groups": ["X25519"]})["result"] == FALSE
    assert c.key_exchange({"groups": ["P-256", "X25519"]})["result"] == FALSE


@pytest.mark.parametrize("claimed", [["P-256"], ["X25519", "P-256"], list(tlsprobe.GROUPS)])
def test_no_group_probe_outcome_gives_true(claimed):
    """Whatever the probes say - even every claimed group accepted and all others refused - the answer is not True."""
    class Fake:
        def __init__(self, *a):
            self.handshakes = 0

        def versions(self):
            return {v: tlsprobe.Observation("accepted" if v == "TLS 1.3" else "refused", "x")
                    for v in tlsprobe.TLS_VERSIONS}, []

        def tls13_groups(self):
            statuses = {g: "accepted" if g in claimed else "refused" for g in tlsprobe.GROUPS}
            return statuses, tlsprobe.Evidence("t", "c", "o", "2026-01-01T00:00:00.000Z", 0, "tool", "v")

        def count_evidence(self):
            return tlsprobe.Evidence("Handshake count", "c", "o", "2026-01-01T00:00:00.000Z", 0, "tool", "v")
    res = check(1, session_factory=Fake).key_exchange({"groups": claimed})
    assert res["result"] == COULDNT and "can't offer" in res["reason"]


def test_only_these_cipher_suites_is_never_true_because_this_computer_cannot_offer_every_suite(tls_server):
    c = check(tls_server("demo"))
    real = ["ECDHE-ECDSA-AES128-SHA", "TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256"]
    res = c.cipher_suites({"suites": real})
    assert res["result"] == COULDNT
    assert "refused every other suite this computer could offer" in res["reason"] and "can't offer" in res["reason"]
    assert c.cipher_suites({"suites": real[1:]})["result"] == FALSE  # False is unchanged


# ------------------------------------------------------------------ 2. only a protocol_version alert refuses a VERSION

class AlertServer:
    """Answers every ClientHello with one fatal TLS alert, then closes."""

    def __init__(self, alert: int):
        self.alert = alert
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                conn.settimeout(2)
                conn.recv(4096)
                conn.sendall(b"\x15\x03\x03\x00\x02\x02" + bytes([self.alert]))
            except OSError:
                pass
            finally:
                conn.close()

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


@pytest.fixture
def alert_server():
    started = []

    def start(alert: int) -> int:
        started.append(AlertServer(alert))
        return started[-1].port
    yield start
    for s in started:
        s.close()


@pytest.mark.parametrize("alert", [40, 71])
def test_handshake_failure_or_insufficient_security_on_a_version_probe_is_unknown(alert_server, alert):
    port = alert_server(alert)
    versions, evidence = ProbeSession("127.0.0.1", port, "localhost").versions()
    for version, obs in versions.items():
        assert obs.status == "unknown", version
        assert obs.detail.startswith(NOT_ABOUT_VERSION) and "cannot offer" not in obs.detail
    assert len(evidence) == 1  # not treated as a local problem: no second try with the hand-built hello
    res = check(port).protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == COULDNT and res["found"] == "Could not test TLS 1.3, TLS 1.2, TLS 1.1 and TLS 1.0."
    assert "the server said no to what we offered, but not specifically to this TLS version" in res["reason"]
    # the same alert still counts as "refused" where it is the right answer: a cipher-suite offer
    assert ProbeSession("127.0.0.1", port, "localhost").handshake("TLS 1.2").status == "refused"


def test_protocol_version_alert_on_a_version_probe_is_refused(alert_server):
    versions, _ = ProbeSession("127.0.0.1", alert_server(70), "localhost").versions()
    assert {o.status for o in versions.values()} == {"refused"}
    assert all("PROTOCOL_VERSION" in o.detail for o in versions.values())


def test_real_servers_refuse_old_versions_with_protocol_version_alerts(tls_server):
    demo, _ = ProbeSession("127.0.0.1", tls_server("demo"), "localhost").versions()
    assert [demo[v].status for v in ("TLS 1.3", "TLS 1.2", "TLS 1.1", "TLS 1.0")] == ["accepted", "accepted", "refused", "refused"]
    assert demo["TLS 1.1"].detail == demo["TLS 1.0"].detail == "server alert TLSV1_ALERT_PROTOCOL_VERSION"
    only13 = check(tls_server("tls13only"))
    versions, _ = only13.session.versions()
    for v in ("TLS 1.2", "TLS 1.1", "TLS 1.0"):  # a TLS 1.3-only OpenSSL server answers protocol_version to older hellos
        assert (versions[v].status, versions[v].detail) == ("refused", "server alert TLSV1_ALERT_PROTOCOL_VERSION")
    assert only13.protocol_versions({"versions": ["TLS 1.3"]})["result"] == TRUE
    res = check(tls_server("demo")).protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == FALSE and res["reason"] is None  # False because TLS 1.2 completed a handshake
    assert res["found"] == "Accepts TLS 1.3 and TLS 1.2 (with ECDHE-ECDSA-AES128-SHA). Refuses TLS 1.1 and TLS 1.0."


# ------------------------------------------------------------------ 3. importing a file makes no name lookups

def test_import_makes_no_dns_lookup_for_names_in_the_file(client, monkeypatch):
    lab = client.app.state.lab
    resolver_calls, dns_calls = [], []
    real_getaddrinfo = socket.getaddrinfo

    def spy_resolver(host):
        resolver_calls.append(host)
        return ["127.0.0.1"] if host == "localhost" else ["203.0.113.9"]

    def spy_getaddrinfo(host, *a, **kw):
        dns_calls.append(host)
        return real_getaddrinfo(host, *a, **kw)
    lab.resolver = spy_resolver
    monkeypatch.setattr(addresses.socket, "getaddrinfo", spy_getaddrinfo)
    data = csv_bytes("shop.example.test:443,tls,protocol_versions,TLS1.3", "tracker.example.test:8443,tls,certificate,RSA 2048",
                     "192.0.2.7:443,tls,protocol_versions,TLS1.3", "[::1]:443,tls,protocol_versions,TLS1.3",
                     "127.0.0.1:9,tls,protocol_versions,TLS1.3", "localhost:9,tls,protocol_versions,TLS1.3")
    imp = upload(client, "claims.csv", data).json()
    assert resolver_calls == ["localhost"]
    assert [h for h in dns_calls if h not in ("localhost", "testserver")] == []
    rows = {a["host"]: a for a in imp["addresses"]}
    for name in ("shop.example.test", "tracker.example.test"):
        assert (rows[name]["resolved_ip"], rows[name]["is_loopback"], rows[name]["error"], rows[name]["confirmed"]) == (None, False, None, False)
    assert (rows["192.0.2.7"]["resolved_ip"], rows["192.0.2.7"]["is_loopback"]) == ("192.0.2.7", False)
    assert (rows["::1"]["resolved_ip"], rows["::1"]["is_loopback"]) == ("::1", True)
    assert (rows["127.0.0.1"]["resolved_ip"], rows["127.0.0.1"]["is_loopback"]) == ("127.0.0.1", True)
    assert (rows["localhost"]["resolved_ip"], rows["localhost"]["is_loopback"]) == ("127.0.0.1", True)
    # verifying without ticking still looks nothing up
    client.post(f"/api/import/{imp['id']}/verify")
    assert resolver_calls == ["localhost"]
    # the name is looked up only when the user ticks its box, and the confirmation is pinned to that IP
    r = client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": "shop.example.test:443", "confirmed": True}).json()
    assert resolver_calls == ["localhost", "shop.example.test"]
    assert (r["resolved_ip"], r["is_loopback"], r["confirmed"]) == ("203.0.113.9", False, True)


# ------------------------------------------------------------------ 4. deeply nested components

def nested_cbom(levels: int) -> bytes:
    """The demo file with a chain of components nested `levels` lists deep (the top-level list is level 1)."""
    doc = json.loads(DEMO_CBOM.read_text())
    node = doc["components"][0]
    for i in range(levels - 1):
        child = {"type": "library", "name": f"n{i}"}
        node["components"] = [child]
        node = child
    return json.dumps(doc).encode()


def test_components_nested_too_deeply_give_a_clear_error_naming_the_field(client):
    assert len(importers.parse_cbom(nested_cbom(50))) == 3  # 50 levels is still read
    with pytest.raises(importers.ImportFileError) as exc:
        importers.parse_cbom(nested_cbom(51))
    assert exc.value.field.startswith("components[0].components[0]") and exc.value.field.endswith(".components")
    assert "more than 50 levels deep" in exc.value.message
    for levels in (51, 300, 450):
        r = upload(client, "deep.json", nested_cbom(levels))
        assert r.status_code == 422, levels
        err = r.json()["error"]
        assert "components" in err["field"] and "nested" in err["message"]
    assert client.get("/api/import/current").status_code == 404  # nothing was stored


def test_a_recursion_error_while_reading_a_file_is_a_422_not_a_crash(client, monkeypatch):
    def boom(data):
        raise RecursionError("maximum recursion depth exceeded")
    monkeypatch.setattr(importers, "read_cbom", boom)
    r = upload(client, "deep.json", DEMO_CBOM.read_bytes())
    assert r.status_code == 422 and r.json()["error"]["message"] == "This file is nested too deeply to read."


# ------------------------------------------------------------------ 5. "Demo data" whenever the file points at our demo

def test_uploading_the_csv_template_is_labelled_demo_data(client):
    imp = upload(client, "claims-template.csv", (DEMO_DIR / "claims-template.csv").read_bytes()).json()
    assert imp["is_demo"] is True and set(imp) == {"id", "filename", "format", "is_demo", "claims", "addresses", "skipped"}


def test_is_demo_follows_what_the_file_points_at(client, settings, listener):
    demo_addr = f"localhost:{settings.demo_tls_port}"
    assert upload(client, "a.csv", csv_bytes(f"{demo_addr},tls,protocol_versions,TLS1.3")).json()["is_demo"] is True
    assert upload(client, "b.csv", csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256")).json()["is_demo"] is True
    not_demo = csv_bytes(f"localhost:{listener.port},tls,protocol_versions,TLS1.3",
                         "acme-sign 9.9.9,software,signature_algorithm,ECDSA P-256",
                         "other-signer 2.0,software,signature_algorithm,ECDSA P-256")
    assert upload(client, "c.csv", not_demo).json()["is_demo"] is False


def test_uploaded_demo_cbom_is_demo_data_and_gets_the_same_answers_as_the_button(client, settings):
    data = DEMO_CBOM.read_bytes().replace(b"localhost:8443", f"localhost:{settings.demo_tls_port}".encode())
    imp = upload(client, "acme-pay-cbom.json", data).json()
    assert imp["is_demo"] is True
    for a in imp["addresses"]:
        client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": a["address"], "confirmed": True})
    results = client.post(f"/api/import/{imp['id']}/verify").json()["results"]
    assert [r["result"] for r in results] == ["False", "True", "True"]
    assert "Demo server identity check" in [e["title"] for e in results[0]["evidence"]]
