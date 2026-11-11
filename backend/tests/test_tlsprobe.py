"""Live handshakes against throwaway TLS servers on this computer (spare ports)."""
from types import SimpleNamespace

from app import tlsprobe
from app.compare import COULDNT, FALSE, TRUE
from app.demo_server import DEMO_TLS12_CIPHER, certificate_fingerprint
from app.tlsprobe import ProbeSession, classify_s_client, describe_certificate
from app.verify import AddressCheck, DemoContext

NO_DEMO = DemoContext(False, "localhost", 1, False, None, None)


def row(port, confirmed=True, host="localhost", ip="127.0.0.1"):
    return SimpleNamespace(address=f"{host}:{port}", host=host, port=port, resolved_ip=ip, is_loopback=True,
                           confirmed=confirmed, error=None)


def check(port, **kw):
    return AddressCheck(row(port, **kw), NO_DEMO)


def test_demo_style_server_accepts_tls12_with_the_old_cipher_and_tls13(tls_server):
    session = ProbeSession("127.0.0.1", tls_server("demo"), "localhost")
    versions, evidence = session.versions()
    assert {v: o.status for v, o in versions.items()} == {
        "TLS 1.3": "accepted", "TLS 1.2": "accepted", "TLS 1.1": "refused", "TLS 1.0": "refused"}
    assert versions["TLS 1.2"].cipher == DEMO_TLS12_CIPHER == "ECDHE-ECDSA-AES128-SHA"
    assert session.handshakes == 4
    assert evidence[0].tool == "Python ssl module" and "OpenSSL" in evidence[0].tool_version
    assert "ALL:COMPLEMENTOFALL:@SECLEVEL=0" in evidence[0].command
    assert "TLS 1.2: accepted" in evidence[0].output and "ECDHE-ECDSA-AES128-SHA" in evidence[0].output


def test_tls13_only_claim_false_on_demo_style_server_and_names_what_it_found(tls_server):
    res = check(tls_server("demo")).protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == FALSE
    assert res["found"] == "Accepts TLS 1.3 and TLS 1.2 (with ECDHE-ECDSA-AES128-SHA). Refuses TLS 1.1 and TLS 1.0."
    assert res["evidence"][-1]["title"] == "Handshake count" and "4 handshakes" in res["evidence"][-1]["output"]
    for item in res["evidence"]:
        assert set(item) == {"title", "command", "output", "started_at", "duration_ms", "tool", "tool_version"}


def test_tls13_only_server_proves_true_and_false_both_ways(tls_server):
    c = check(tls_server("tls13only"))
    res = c.protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == TRUE and res["found"] == "Accepts TLS 1.3. Refuses TLS 1.2, TLS 1.1 and TLS 1.0."
    assert c.protocol_versions({"versions": ["TLS 1.2", "TLS 1.3"]})["result"] == FALSE  # claims 1.2, server refuses it
    assert c.session.handshakes == 4  # the version handshakes are made once per address and reused


def test_legacy_server_accepts_everything(tls_server):
    c = check(tls_server("legacy"))
    res = c.protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == FALSE
    assert res["found"].startswith("Accepts TLS 1.3, TLS 1.2 (with ") and "TLS 1.0 (with " in res["found"]
    assert c.protocol_versions({"versions": ["TLS 1.0", "TLS 1.1", "TLS 1.2", "TLS 1.3"]})["result"] == TRUE
    assert c.protocol_versions({"versions": ["TLS 1.2", "TLS 1.3"]})["result"] == FALSE


def test_certificate_is_read_from_the_live_handshake(tls_server, test_cert):
    c = check(tls_server("demo"))
    res = c.certificate({"algorithm": "ECDSA P-256"})
    assert res["result"] == TRUE and "P-256 (secp256r1), 256 bits" in res["found"]
    assert c.certificate({"algorithm": "RSA 2048"})["result"] == FALSE
    assert c.certificate({"algorithm": "ECDSA P-384"})["result"] == FALSE
    assert c.certificate({"algorithm": None})["result"] == COULDNT
    info = describe_certificate(c.session.first_certificate())
    assert info["sha256_fingerprint"] == certificate_fingerprint(test_cert[0])
    assert (info["key_type"], info["curve"], info["key_size"]) == ("EC", "secp256r1", 256)
    assert "ecdsa" in info["signature_algorithm"].lower()


def test_tls13_groups_pinned_on_demo_style_server(tls_server):
    c = check(tls_server("demo"))
    res = c.key_exchange({"groups": ["P-256"]})
    assert res["result"] == COULDNT, res  # the groups we try are not every group there is: never True
    assert res["found"].startswith("On TLS 1.3 the server accepts P-256.")
    assert c.key_exchange({"groups": ["X25519"]})["result"] == FALSE
    ev = [e for e in res["evidence"] if e["tool"] == "openssl s_client"][0]
    assert ev["tool_version"].startswith("OpenSSL ") and "-groups P-256" in ev["command"]
    assert "-connect 127.0.0.1:" in ev["command"] and "-servername localhost" in ev["command"]


def test_cipher_suites_per_version(tls_server):
    c = check(tls_server("demo"))
    real = ["ECDHE-ECDSA-AES128-SHA", "TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256"]
    res = c.cipher_suites({"suites": real})
    assert res["result"] == COULDNT and "can't offer" in res["reason"], res  # never True: see test_phase1_review.py
    assert res["found"] == f"The server accepts {', '.join(real[:3])} and {real[3]}."
    assert c.cipher_suites({"suites": real[1:]})["result"] == FALSE  # the old TLS 1.2 suite is accepted too
    iana = ["TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA"] + real[1:]
    assert c.cipher_suites({"suites": iana})["result"] == COULDNT
    assert c.cipher_suites({"suites": real + ["ECDHE-RSA-AES256-GCM-SHA384"]})["result"] == FALSE
    assert c.cipher_suites({"suites": ["MADE-UP-SUITE"]})["result"] == COULDNT
    assert c.session.handshakes <= c.session.max_handshakes


def test_port_with_no_tls_or_nothing_listening_is_couldnt_check(listener):
    res = AddressCheck(row(listener.port), NO_DEMO, session_factory=lambda *a: ProbeSession(*a, timeout=0.5)) \
        .protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == COULDNT and "Could not test" in res["found"]
    assert listener.connections() == 1  # no answer to the first handshake, so we did not keep trying
    port = listener.port
    listener.close()
    res = check(port).protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == COULDNT and "could not connect" in res["reason"]
    assert check(port).certificate({"algorithm": "ECDSA P-256"})["result"] == COULDNT


def test_local_tooling_errors_are_never_a_refusal(tls_server, monkeypatch):
    """If this computer's TLS library cannot offer an old version, we fall back to a hand-built hello;
    and if that cannot tell either, the answer is Couldn't check - not True."""
    import ssl
    real = ProbeSession._context

    def broken(self, version, ciphers):
        if version in ("TLS 1.0", "TLS 1.1"):
            raise ssl.SSLError("NO_PROTOCOLS_AVAILABLE")
        return real(self, version, ciphers)
    monkeypatch.setattr(ProbeSession, "_context", broken)
    c = check(tls_server("tls13only"))
    res = c.protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == TRUE  # the hand-built hello got a real protocol_version alert for 1.0 and 1.1
    assert any(e["tool"] == tlsprobe.RAW_TOOL for e in res["evidence"])
    monkeypatch.setattr(ProbeSession, "raw_hello", lambda self, v: tlsprobe.Observation("unknown", "no answer"))
    res = check(tls_server("tls13only")).protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == COULDNT and "TLS 1.0" in res["reason"]
    legacy = check(tls_server("legacy"))
    monkeypatch.undo()
    monkeypatch.setattr(ProbeSession, "_context", broken)
    assert legacy.protocol_versions({"versions": ["TLS 1.3"]})["result"] == FALSE
    assert legacy.session.versions()[0]["TLS 1.0"].status == "accepted"  # seen by the hand-built hello


def test_claims_with_nothing_exact_to_compare_make_no_connection(listener):
    c = check(listener.port)
    assert c.protocol_versions({"version_not_stated": True})["result"] == COULDNT
    assert c.protocol_versions({"unsupported_protocol": "ssh"})["result"] == COULDNT
    assert c.certificate({"algorithm": None})["result"] == COULDNT
    assert c.key_exchange({"from_algorithm_asset": True, "algorithm": "ECDH"})["result"] == COULDNT
    assert listener.connections() == 0


def test_handshake_cap_is_enforced(tls_server):
    session = ProbeSession("127.0.0.1", tls_server("demo"), "localhost", max_handshakes=2)
    versions, _ = session.versions()
    assert session.handshakes == 2
    assert versions["TLS 1.1"].status == "unknown" and "limit" in versions["TLS 1.1"].detail
    argv, output, why = session.s_client(["-tls1_3"])
    assert output is None and "limit" in why and session.handshakes == 2


def test_unconfirmed_address_makes_no_connection(listener):
    made = []
    c = AddressCheck(row(listener.port, confirmed=False), NO_DEMO, session_factory=lambda *a: made.append(a))
    res = c.protocol_versions({"versions": ["TLS 1.3"]})
    assert res["result"] == COULDNT and res["reason"] == "You haven't confirmed you're allowed to test this address"
    assert c.certificate({"algorithm": "ECDSA P-256"})["result"] == COULDNT
    assert made == [] and listener.connections() == 0


def test_hostile_stored_address_is_blocked_before_any_connection():
    for host in ("-connect", "a b", "x;rm", "../"):
        made = []
        c = AddressCheck(row(443, host=host), NO_DEMO, session_factory=lambda *a: made.append(a))
        assert c.protocol_versions({"versions": ["TLS 1.3"]})["result"] == COULDNT
        assert made == []
    c = AddressCheck(SimpleNamespace(address="localhost:70000", host="localhost", port=70000, resolved_ip="127.0.0.1",
                                     is_loopback=True, confirmed=True, error=None), NO_DEMO)
    assert c.session is None and "65535" in c.blocked


def test_probes_connect_to_the_pinned_ip_not_the_name(tls_server):
    port = tls_server("demo")
    c = AddressCheck(row(port, host="pinned.example.test"), NO_DEMO, resolver=lambda h: ["127.0.0.1"])
    assert (c.session.ip, c.session.server_name) == ("127.0.0.1", "pinned.example.test")
    assert c.protocol_versions({"versions": ["TLS 1.3"]})["result"] == FALSE
    moved = AddressCheck(row(port, host="pinned.example.test"), NO_DEMO, resolver=lambda h: ["203.0.113.9"])
    assert moved.session is None and "different IP" in moved.blocked


def test_s_client_output_is_parsed_not_exit_codes():
    ok = "CONNECTION ESTABLISHED\nProtocol version: TLSv1.3\nCiphersuite: TLS_AES_256_GCM_SHA384\n"
    assert classify_s_client(ok)[0] == "accepted"
    assert classify_s_client(ok, want_suite="TLS_AES_128_GCM_SHA256")[0] == "unknown"
    assert classify_s_client(ok.replace("TLSv1.3", "TLSv1.2"))[0] == "unknown"
    assert classify_s_client("error:0A000410:SSL routines::sslv3 alert handshake failure:SSL alert number 40\n")[0] == "refused"
    assert classify_s_client("tlsv1 alert protocol version: SSL alert number 70")[0] == "refused"
    assert classify_s_client("SSL alert number 80")[0] == "unknown"  # internal_error is not a refusal
    assert classify_s_client("Call to SSL_CONF_cmd(-groups, X25519MLKEM768) failed")[0] == "unknown"
    assert classify_s_client("connect: Connection refused\nconnect:errno=111")[0] == "unknown"
    assert classify_s_client("")[0] == "unknown"
