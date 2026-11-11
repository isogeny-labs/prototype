"""The whole thing through the web API, with a temporary data folder and the demo server on a spare port."""
import hashlib
import json
import logging
import socket
import stat

from fastapi.testclient import TestClient

from app import components
from app.config import DEMO_CBOM, Settings
from app.main import create_app
from conftest import PASSWORD, csv_bytes, free_port, upload

NOT_CONFIRMED = "You haven't confirmed you're allowed to test this address"


def demo_verified(client, confirm=True):
    imp = client.post("/api/import/demo").json()
    if confirm:
        for a in imp["addresses"]:
            r = client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": a["address"], "confirmed": True})
            assert r.status_code == 200 and r.json()["confirmed"] is True
    run = client.post(f"/api/import/{imp['id']}/verify")
    assert run.status_code == 200
    return imp, run.json()


# ------------------------------------------------------------------ login

def test_first_start_asks_to_create_a_password_then_logs_in(anon_client, settings):
    c = anon_client
    s = c.get("/api/session").json()
    assert s == {"setup_required": True, "logged_in": False, "mode": "demo",
                 "mode_line": "Demo mode: running our own demo software, not isolated. Isolated mode is switched off for this run.",
                 "demo_server": {"address": f"localhost:{settings.demo_tls_port}", "running": True, "error": None}}
    assert c.post("/api/import/demo").status_code == 401
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 401  # nothing set up yet
    short = c.post("/api/setup", json={"password": "short"})
    assert short.status_code == 422 and short.json()["error"]["field"] == "password"
    assert c.get("/api/session").json()["setup_required"] is True
    r = c.post("/api/setup", json={"password": PASSWORD})
    assert r.status_code == 200 and r.json() == {"ok": True}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/api/session").json()["logged_in"] is True and c.get("/api/session").json()["setup_required"] is False
    second = c.post("/api/setup", json={"password": "another-passphrase"})
    assert second.status_code == 409 and set(second.json()["error"]) == {"message", "line", "field"}


def test_every_other_endpoint_needs_login(client):
    client.cookies.clear()
    assert client.get("/api/session").json()["logged_in"] is False
    for method, url in [("post", "/api/import/demo"), ("post", "/api/import/file?filename=a.csv"),
                        ("get", "/api/import/current"), ("post", "/api/import/1/confirm-address"),
                        ("post", "/api/import/1/verify"), ("get", "/api/import/1/verify")]:
        r = getattr(client, method)(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["message"]
    client.cookies.set("evidence_lab_session", "made-up-token")
    assert client.get("/api/import/current").status_code == 401
    client.cookies.clear()
    assert client.post("/api/login", json={"password": "wrong-passphrase"}).status_code == 401
    assert client.get("/api/import/current").status_code == 401
    assert client.post("/api/login", json={"password": PASSWORD}).json() == {"ok": True}
    assert client.get("/api/import/current").status_code == 404  # logged in, nothing imported yet


def test_password_is_stored_only_as_a_salted_hash_and_never_logged(client, settings, caplog):
    with caplog.at_level(logging.DEBUG):
        client.post("/api/login", json={"password": PASSWORD})
        client.post("/api/login", json={"password": "wrong-" + PASSWORD})
    assert PASSWORD not in caplog.text
    raw = settings.db_path.read_bytes()
    assert PASSWORD.encode() not in raw
    token = client.cookies.get("evidence_lab_session")
    assert token and token.encode() not in raw  # only a hash of the session token is stored
    lab = client.app.state.lab
    with lab.db() as db:
        from app.db import AuthRow
        row = db.get(AuthRow, 1)
        assert len(row.salt) == 16 and len(row.password_hash) == 32
        assert row.password_hash == hashlib.scrypt(PASSWORD.encode(), salt=row.salt, n=2 ** 15, r=8, p=1, dklen=32, maxmem=2 ** 27)


def test_requests_for_other_host_names_are_refused(client):
    assert client.get("/api/session", headers={"Host": "evil.example"}).status_code == 400


# ------------------------------------------------------------------ the demo: V1 False, V2 True, V3 True

def test_demo_import_and_verify_match_the_answer_key(client, settings):
    imp, run = demo_verified(client)
    addr = f"localhost:{settings.demo_tls_port}"
    assert imp["is_demo"] is True and imp["format"] == "cyclonedx-cbom" and imp["filename"] == "acme-pay-cbom.json"
    assert [c["kind"] for c in imp["claims"]] == ["protocol_versions", "certificate", "signature_algorithm"]
    assert imp["addresses"] == [{"address": addr, "host": "localhost", "port": settings.demo_tls_port,
                                 "resolved_ip": "127.0.0.1", "is_loopback": True, "confirmed": False, "error": None}]
    assert set(imp["claims"][0]) == {"id", "ref", "location", "location_kind", "kind", "claimed_value", "text", "source"}
    v1, v2, v3 = run["results"]
    assert (v1["result"], v2["result"], v3["result"]) == ("False", "True", "True")
    assert v1["found"] == "Accepts TLS 1.3 and TLS 1.2 (with ECDHE-ECDSA-AES128-SHA). Refuses TLS 1.1 and TLS 1.0."
    assert "P-256" in v2["found"] and "acme-sign 1.4.2 using ECDSA P-256" in v3["found"]
    assert v1["claim"] == imp["claims"][0] and v1["claim_id"] == imp["claims"][0]["id"]
    assert run["import_id"] == imp["id"] and run["started_at"] <= run["finished_at"]
    for res in run["results"]:
        assert res["reason"] is None and res["evidence"]
        for item in res["evidence"]:
            assert set(item) == {"title", "command", "output", "started_at", "duration_ms", "tool", "tool_version"}
            assert item["tool"] and item["tool_version"]
    titles = [e["title"] for e in v1["evidence"]]
    assert "Demo server identity check" in titles and "Handshake count" in titles
    assert client.get(f"/api/import/{imp['id']}/verify").json() == run
    assert client.get("/api/import/current").json()["id"] == imp["id"]
    assert client.get("/api/import/current").json()["addresses"][0]["confirmed"] is True


def test_demo_file_on_disk_names_port_8443():
    assert b"localhost:8443" in DEMO_CBOM.read_bytes()


def test_localhost_is_not_auto_confirmed_and_unconfirmed_means_no_connection(client, listener):
    imp, run = demo_verified(client, confirm=False)
    v1, v2, v3 = run["results"]
    assert v1["result"] == v2["result"] == "Couldn't check"
    assert v1["reason"] == v2["reason"] == NOT_CONFIRMED
    assert v3["result"] == "True"  # the software claim does not involve the address
    data = csv_bytes(f"127.0.0.1:{listener.port},tls,protocol_versions,TLS1.3", f"127.0.0.1:{listener.port},tls,certificate,RSA 2048")
    imp = upload(client, "claims.csv", data).json()
    run = client.post(f"/api/import/{imp['id']}/verify").json()
    assert [r["result"] for r in run["results"]] == ["Couldn't check"] * 2
    assert all(r["reason"] == NOT_CONFIRMED for r in run["results"])
    assert listener.connections() == 0
    # ...and after un-ticking the box it is blocked again
    url = f"/api/import/{imp['id']}/confirm-address"
    assert client.post(url, json={"address": f"127.0.0.1:{listener.port}", "confirmed": True}).json()["confirmed"] is True
    assert client.post(url, json={"address": f"127.0.0.1:{listener.port}", "confirmed": False}).json()["confirmed"] is False
    run = client.post(f"/api/import/{imp['id']}/verify").json()
    assert all(r["reason"] == NOT_CONFIRMED for r in run["results"]) and listener.connections() == 0


def test_confirm_address_rejects_hostile_and_unknown_addresses(client):
    imp = client.post("/api/import/demo").json()
    url = f"/api/import/{imp['id']}/confirm-address"
    for bad in ["-connect:443", "a b:443", "x;rm:443", "../:443", "localhost", "localhost:99999"]:
        r = client.post(url, json={"address": bad, "confirmed": True})
        assert r.status_code == 422 and r.json()["error"]["field"] == "address", bad
    assert client.post(url, json={"address": "localhost:1", "confirmed": True}).status_code == 404  # not in this import
    assert client.post(url, json={"address": imp["addresses"][0]["address"], "confirmed": "yes"}).status_code == 422
    assert client.post("/api/import/9999/verify").status_code == 404
    assert client.get(f"/api/import/{imp['id']}/verify").status_code == 404


def test_confirmation_is_pinned_to_the_ip_and_refused_if_the_name_moves(client, tls_server, listener):
    lab = client.app.state.lab
    port = tls_server("tls13only")
    lab.resolver = lambda host: ["127.0.0.1"]
    imp = upload(client, "claims.csv", csv_bytes(f"shop.example.test:{port},tls,protocol_versions,TLS1.3")).json()
    assert imp["addresses"][0]["resolved_ip"] is None  # a name from a file is not looked up until you tick it
    r = client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": f"shop.example.test:{port}", "confirmed": True})
    assert r.json()["resolved_ip"] == "127.0.0.1" and r.json()["confirmed"] is True
    assert client.post(f"/api/import/{imp['id']}/verify").json()["results"][0]["result"] == "True"
    lab.resolver = lambda host: ["127.0.0.2"]  # the name now points somewhere else
    res = client.post(f"/api/import/{imp['id']}/verify").json()["results"][0]
    assert res["result"] == "Couldn't check" and "different IP" in res["reason"]


def test_name_that_does_not_resolve_cannot_be_confirmed_or_checked(client):
    imp = upload(client, "claims.csv", csv_bytes("no-such-host.invalid:443,tls,protocol_versions,TLS1.3")).json()
    a = imp["addresses"][0]
    assert a["resolved_ip"] is None and a["error"] is None and a["is_loopback"] is False  # not looked up on import
    r = client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": a["address"], "confirmed": True}).json()
    assert r["confirmed"] is False and r["resolved_ip"] is None and r["error"]
    assert client.post(f"/api/import/{imp['id']}/verify").json()["results"][0]["result"] == "Couldn't check"


# ------------------------------------------------------------------ demo server safety

def test_port_in_use_does_not_crash_or_move_ports_and_gives_couldnt_check(tmp_path):
    blocker = socket.create_server(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    blocker.setblocking(False)
    try:
        with TestClient(create_app(Settings(data_dir=tmp_path / "data", demo_tls_port=port))) as c:
            c.post("/api/setup", json={"password": PASSWORD})
            s = c.get("/api/session").json()["demo_server"]
            assert s["running"] is False and s["address"] == f"localhost:{port}" and str(port) in s["error"]
            imp, run = demo_verified(c)
            v1, v2, v3 = run["results"]
            assert v1["result"] == v2["result"] == "Couldn't check"
            assert "already used by another program" in v1["reason"]
            assert v3["result"] == "True"
            try:
                blocker.accept()
                raise AssertionError("a connection was made to someone else's program")
            except BlockingIOError:
                pass
    finally:
        blocker.close()


def test_something_else_on_the_demo_port_is_not_reported_as_the_demo_server(client, settings, tls_server, tmp_path):
    """If what answers on the demo address is not our demo certificate, say Couldn't check."""
    from app.demo_server import TlsServer, ensure_demo_certificate, make_server_context
    lab = client.app.state.lab
    lab.demo.stop()
    cert, key = ensure_demo_certificate(tmp_path / "other")  # a different certificate
    impostor = TlsServer(make_server_context(cert, key), settings.demo_tls_port)
    lab.demo.running = True  # pretend our server is up; an impostor holds the port
    try:
        _, run = demo_verified(client)
        v1, v2, _ = run["results"]
        assert v1["result"] == v2["result"] == "Couldn't check"
        assert "Something other than the Evidence Lab demo server" in v1["reason"]
    finally:
        impostor.close()
        lab.demo.running = False


def test_demo_test_key_is_private_to_the_data_folder(client, settings):
    key = settings.data_dir / "demo-tls-test-key.pem"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    cert_before = (settings.data_dir / "demo-tls-test-cert.pem").read_bytes()
    with TestClient(create_app(Settings(data_dir=settings.data_dir, demo_tls_port=free_port()))):
        pass
    assert (settings.data_dir / "demo-tls-test-cert.pem").read_bytes() == cert_before  # made once, then reused


def test_no_private_key_material_reaches_evidence_or_the_database(client, settings, monkeypatch):
    real, private = components.run_component, []

    def spy(path, command, payload=None, **kw):
        run = real(path, command, payload, **kw)
        if command == "keygen":
            private.append(run.data["private_key"])
        return run
    monkeypatch.setattr(components, "run_component", spy)
    imp, run = demo_verified(client)
    tls_key_lines = [line for line in (settings.data_dir / "demo-tls-test-key.pem").read_text().splitlines()
                     if line and not line.startswith("-----")]
    haystacks = [json.dumps(run), json.dumps(client.get(f"/api/import/{imp['id']}/verify").json()),
                 settings.db_path.read_bytes().decode("latin-1")]
    assert len(private) == 1
    for text in haystacks:
        assert private[0] not in text
        assert "PRIVATE KEY" not in text
        assert not any(line in text for line in tls_key_lines)
    assert components.WITHHELD in haystacks[0] and components.WITHHELD in haystacks[2]
    for res in run["results"]:
        for item in res["evidence"]:
            assert '"private_key": "' not in item["output"].replace(f'"private_key": "{components.WITHHELD}"', "")
            assert '"private_key": "' not in item["command"].replace(f'"private_key": "{components.WITHHELD}"', "")


# ------------------------------------------------------------------ uploads

def test_upload_csv_and_software_claims(client, tls_server):
    port = tls_server("legacy")
    data = csv_bytes(f"127.0.0.1:{port},tls,protocol_versions,TLS1.3",
                     f"127.0.0.1:{port},tls,certificate,ECDSA P-256",
                     "acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
                     "acme-sign 1.4.2,software,signature_algorithm,Ed25519",
                     "acme-sign 1.4.4,software,signature_algorithm,ECDSA P-256",  # not a demo version (1.4.3 became one in phase 2)
                     "../acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
                     "other-signer 2.0,software,signature_algorithm,ECDSA P-256")
    r = upload(client, "C:\\Users\\me\\my claims.csv", data)
    assert r.status_code == 200
    imp = r.json()
    assert imp["filename"] == "my claims.csv" and imp["format"] == "csv"
    assert imp["is_demo"] is True  # it names acme-sign 1.4.2, one of our own demo components
    assert len(imp["claims"]) == 7 and len(imp["addresses"]) == 1
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": f"127.0.0.1:{port}", "confirmed": True})
    results = client.post(f"/api/import/{imp['id']}/verify").json()["results"]
    assert [r["result"] for r in results] == ["False", "True", "True", "False", "Couldn't check", "Couldn't check", "Couldn't check"]
    assert "TLS 1.0 (with " in results[0]["found"]
    assert all(r["reason"] == "Only our demo components can run in demo mode" for r in results[4:])
    assert all(r["evidence"] == [] for r in results[4:])  # nothing was run


def test_uploaded_cbom_with_unlocated_and_unknown_things_is_couldnt_check(client):
    doc = json.loads(DEMO_CBOM.read_text())
    doc["services"] = []
    for comp in doc["components"]:
        comp.pop("evidence", None)
        if comp["bom-ref"] == "lib-acme-sign":
            comp["name"] = "../../demo/components/acme-sign-1.4.2/acme_sign.py"
    imp = upload(client, "scan.json", json.dumps(doc).encode()).json()
    assert imp["addresses"] == [] and [c["location_kind"] for c in imp["claims"]] == ["unknown", "unknown", "software"]
    results = client.post(f"/api/import/{imp['id']}/verify").json()["results"]
    assert [r["result"] for r in results] == ["Couldn't check"] * 3
    assert "doesn't say where" in results[0]["reason"]
    assert results[2]["reason"] == "Only our demo components can run in demo mode"


def test_upload_errors_name_the_line_or_field(client):
    r = upload(client, "bad.csv", b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions,TLS9\n")
    assert r.status_code == 422 and r.json()["error"]["line"] == 2 and r.json()["error"]["field"] == "value"
    r = upload(client, "bad.json", b'{"specVersion": "1.6"}')
    assert r.status_code == 422 and r.json()["error"] == {
        "message": 'This doesn\'t look like a CycloneDX file: the "bomFormat" field is missing.', "line": None, "field": "bomFormat"}
    r = upload(client, "bad.json", b'{\n"bomFormat": \n')
    assert r.status_code == 422 and r.json()["error"]["line"] == 3
    r = upload(client, "huge.csv", b"location,type,claim,value\n" + b"x" * (1024 * 1024))
    assert r.status_code == 422 and "1 MB" in r.json()["error"]["message"]
    r = upload(client, "", b"\x00\x01\x02")
    assert r.status_code == 422 and r.json()["error"]["field"] == "filename"
    assert client.get("/api/import/current").status_code == 404  # none of those were stored


def test_file_content_is_only_ever_data(client, tmp_path):
    marker = tmp_path / "was-executed"
    doc = json.loads(DEMO_CBOM.read_text())
    for comp in doc["components"]:
        if comp["bom-ref"] == "lib-acme-sign":
            comp["name"], comp["version"] = f"$(touch {marker})", f"`touch {marker}`; touch {marker}"
    imp = upload(client, f"x; touch {marker}.json", json.dumps(doc).encode()).json()
    res = client.post(f"/api/import/{imp['id']}/verify").json()["results"][2]
    assert res["result"] == "Couldn't check" and not marker.exists()


def test_unknown_api_paths_give_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and "error" in r.json()
