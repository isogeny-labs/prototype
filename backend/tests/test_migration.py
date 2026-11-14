"""Phase 4a: the migration plan. The probe, the status rule, the fixed rules for recommendations and the roadmap,
the CSV additions, and the whole flow on the migration demo file in demo mode (no Docker, no internet: every
server is a test server on this computer, on a spare port)."""
import dataclasses
import json
import socket
import threading
from datetime import date

import pytest

from app import migration_rules as rules
from app import migration_servers, pqprobe, pqtls, research
from app.compare import COULDNT, FALSE, TRUE
from app.config import DEMO_DIR
from app.errors import BadRequest, Conflict, NotFound
from app.importers import ImportFileError, parse_file
from app.reviewer import RuleReviewer, pq_status_of, signature_family
from app.tlsprobe import ProbeSession
from conftest import PASSWORD, csv_bytes, free_port, make_lab, play_back_speed, upload

ROLES = ("hybrid", "classical_internet", "classical_internal", "legacy_tls12", "pq_only")


def _ports(n=5):
    return tuple(free_port() for _ in range(n))


# ------------------------------------------------------------------ the probe

def test_the_hello_offers_one_family_and_attaches_no_key():
    hello = pqprobe.build_hello(pqprobe.FAMILIES["hybrid"], "example.test")
    assert hello[:3] == b"\x16\x03\x01" and hello[5] == 1                      # one handshake record: a ClientHello
    assert b"\x00\x0a\x00\x08\x00\x06\x11\xec\x11\xeb\x11\xed" in hello         # supported_groups: the three hybrids, nothing else
    assert b"\x00\x33\x00\x02\x00\x00" in hello                                 # key_share: empty, on purpose
    assert b"\x00\x2b\x00\x03\x02\x03\x04" in hello                             # TLS 1.3 only
    assert b"example.test" in hello


def test_the_probe_tells_a_hybrid_server_from_a_classical_one():
    with pqtls.control_servers() as ports:
        hybrid = pqprobe.offer_all(ProbeSession("127.0.0.1", ports["hybrid"], None))
        classical = pqprobe.offer_all(ProbeSession("127.0.0.1", ports["classical"], None))
    assert (hybrid["hybrid"]["state"], hybrid["hybrid"]["group"]) == ("offered", "X25519MLKEM768")
    assert hybrid["classical"]["state"] == "offered"
    assert [classical[f]["state"] for f in ("hybrid", "pure", "classical")] == ["refused", "refused", "offered"]
    assert classical["hybrid"]["alert"] in (40, 70, 71)


@pytest.mark.parametrize("answer", [b"", b"HTTP/1.1 400 Bad Request\r\n\r\n", b"\x15\x03\x03\x00\x02\x02\x50"])
def test_silence_or_an_answer_that_is_not_a_tls_refusal_is_unclear_never_a_status(answer):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)

    def serve():
        for _ in range(3):
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                conn.recv(4096)
                if answer:
                    conn.sendall(answer)
    threading.Thread(target=serve, daemon=True).start()
    try:
        probes = pqprobe.offer_all(ProbeSession("127.0.0.1", server.getsockname()[1], None))
    finally:
        server.close()
    assert [p["state"] for p in probes.values()] == ["unclear"] * 3


# ------------------------------------------------------------------ the status rule (reviewer.py)

def _probe(state, group=None):
    return {"state": state, "group": group if state == "offered" else None, "offered": [], "detail": ""}


def _hs(outcome, group=None, version="TLS 1.3"):
    return {"outcome": outcome, "group": group, "tls_version": version if outcome == "completed" else None, "client_hello_bytes": 300,
            "client_share_bytes": 32, "server_share_bytes": 32, "certificate_message_bytes": 400, "signature_bytes": 71}


GOOD_CONTROL = {"hybrid": {"probes": {"hybrid": _probe("offered", "X25519MLKEM768"), "pure": _probe("refused"), "classical": _probe("offered", "X25519")}},
                "classical": {"probes": {"hybrid": _probe("refused"), "pure": _probe("refused"), "classical": _probe("offered", "X25519")}},
                "reference": {"classical": _hs("completed", "X25519"), "hybrid": _hs("completed", "X25519MLKEM768"), "timing": None}}


def _raw(h="refused", p="refused", c="offered", full="refused", client="completed", versions=("TLS 1.3", "TLS 1.2"), control=GOOD_CONTROL,
         full_pure=None, client_version="TLS 1.3"):
    all_versions = {v: {"state": "accepted" if v in versions else "refused"} for v in ("TLS 1.3", "TLS 1.2", "TLS 1.1", "TLS 1.0")}
    return {"subject": {"probes": {"hybrid": _probe(h, "X25519MLKEM768"), "pure": _probe(p, "MLKEM768"), "classical": _probe(c, "X25519")},
                        "versions": all_versions, "classical_client": _hs(client, "X25519", client_version),
                        "hybrid_handshake": _hs(full, "X25519MLKEM768"), "pure_handshake": full_pure, "certificate": None,
                        "container": None, "timing": None},
            "control": control}


@pytest.mark.parametrize("raw, code", [
    (_raw(h="offered", full="completed"), "hybrid"),                                 # the server asked for a hybrid key
    (_raw(h="unclear", full="completed"), "hybrid"),                                 # or a full hybrid handshake completed: positive proof
    (_raw(h="offered", c="refused", client="refused", versions=()), "hybrid"),       # hybrid only is still Hybrid
    (_raw(), "classical"),
    (_raw(c="refused", client="completed", versions=("TLS 1.2",), client_version="TLS 1.2"), "classical"),   # TLS 1.2 only
    (_raw(p="offered", c="refused", client="refused", versions=(), full_pure=_hs("completed", "MLKEM768")), "pq_only"),
    (_raw(p="offered"), "couldnt_run"),                                              # ML-KEM by itself next to classical: not a status we name
    (_raw(h="unclear"), "couldnt_run"),                                              # silence is never read as "refused"
    (_raw(p="unclear"), "couldnt_run"),
    (_raw(full="unknown"), "couldnt_run"),                                           # the full handshake gave no TLS refusal
    (_raw(c="unclear", client="unknown", versions=()), "couldnt_run"),               # nothing classical was accepted either
    (_raw(client="unknown", versions=()), "couldnt_run"),                            # asked for a classical key, but no classical handshake completed
    (_raw(p="offered", c="refused", client="completed", versions=("TLS 1.2",), client_version="TLS 1.2"), "couldnt_run"),
])
def test_the_status_rule(raw, code):
    found = pq_status_of(raw)
    assert found["code"] == code
    assert found["control"]["outcome"] == "as_expected"
    assert (found["reason_code"] == "unclear_answer") == (code == "couldnt_run")


def test_the_sentence_names_the_proof_that_was_actually_seen():
    from app import present_pq
    probe = pq_status_of(_raw(h="offered", full="completed"))["detail"]
    assert probe["hybrid_proof"] == ["probe", "handshake"]
    assert present_pq.status_sentence("hybrid", probe).startswith("It asked for a hybrid key (X25519MLKEM768) when we offered only hybrid key exchanges")
    only_handshake = pq_status_of(_raw(h="unclear", full="completed"))["detail"]
    assert only_handshake["hybrid_proof"] == ["handshake"]
    assert present_pq.status_sentence("hybrid", only_handshake).startswith("It completed a full handshake with the hybrid key exchange X25519MLKEM768, so it is Hybrid.")
    classical = pq_status_of(_raw())["detail"]
    assert present_pq.status_sentence("classical", classical) == ("It refused every post-quantum key exchange we offered and completed a classical "
                                                                  "handshake, so it is Classical.")


def test_a_misread_control_server_means_the_run_is_not_trusted():
    misread = {**GOOD_CONTROL, "classical": {"probes": {"hybrid": _probe("offered", "X25519MLKEM768"), "pure": _probe("refused"),
                                                         "classical": _probe("offered", "X25519")}}}
    assert pq_status_of(_raw(control=misread))["control"]["outcome"] == "not_as_expected"
    assert pq_status_of(_raw(control={"error": "the control servers could not be started"}))["control"]["outcome"] == "errored"
    spec = research.RuleEngine().design_measurement({"kind": "pq_status", "target": "localhost:1", "claims": [
        {"ref": "r1", "location": "localhost:1", "location_kind": "server", "kind": "post_quantum", "detail": {"status": "Classical"}}]})
    from app.canonical import sha256_hex
    run = {"spec_hash": sha256_hex(spec), "raw": _raw(control=misread)}
    review = RuleReviewer().review({"spec": spec, "spec_hash": sha256_hex(spec), "proposed_by": "isogeny.rule-engine/1", "run": run})
    assert review["verdict"]["code"] == "couldnt_trust"
    run = {"spec_hash": sha256_hex(spec), "raw": {"problem": {"code": "pq_engine_unavailable", "text": "x"}}}
    review = RuleReviewer().review({"spec": spec, "spec_hash": sha256_hex(spec), "proposed_by": "isogeny.rule-engine/1", "run": run})
    assert (review["verdict"]["code"], review["verdict"]["reason_code"]) == ("couldnt_run", "pq_engine_unavailable")


def test_signature_families():
    assert [signature_family(a) for a in ("ECDSA P-256", "RSA 2048", "Ed25519", "ML-DSA-65", "SLH-DSA-128s", "Something new")] == \
        ["classical", "classical", "classical", "pq_only", "pq_only", None]


# ------------------------------------------------------------------ the fixed rules (migration_rules.py)

def _s(lifespan="long", exposure="internet", can_change="yes"):
    return {"lifespan": lifespan, "exposure": exposure, "can_change": can_change}


@pytest.mark.parametrize("kind, status, settings, option, in_place", [
    ("server", None, _s(), None, None),                                   # couldn't check: nothing is recommended
    ("server", "pq_only", _s(), "full_pq", True),
    ("server", "hybrid", _s("short", "internal"), "hybrid", True),
    ("server", "classical", _s("long", "internet", "no"), "wrap", False),
    ("server", "classical", _s("short", "internet", "no"), "wrap", False),
    ("server", "classical", _s("long", "internal", "no"), "wrap", False),
    ("server", "classical", _s("short", "internal", "no"), "keep", False),
    ("server", "classical", _s("long", "internal"), "hybrid", False),
    ("server", "classical", _s("short", "internet"), "hybrid", False),
    ("server", "classical", _s("short", "internal"), "keep", False),
    ("software", "classical", _s("long", "internal"), "hybrid", False),
    ("software", "classical", _s("short", "internal"), "keep", False),
    ("software", "classical", _s("long", "internet", "no"), "hybrid", False),  # wrapping never applies to a signing program
    ("software", "classical", _s("short", "internet", "no"), "keep", False),
    ("software", "pq_only", _s(), "full_pq", True),
])
def test_the_recommendation_rules(kind, status, settings, option, in_place):
    rec = rules.recommend(kind, status, settings)
    assert (rec and rec["option"], rec and rec["in_place"]) == (option, in_place)
    # full post-quantum is never recommended unless the system is already there
    assert not (rec and rec["option"] == "full_pq" and status != "pq_only")


def test_the_options_a_system_is_offered():
    assert rules.offered("server", "classical") == ("keep", "hybrid", "full_pq", "wrap")
    assert rules.offered("software", "classical") == ("keep", "hybrid", "full_pq")       # wrapping protects connections, not signatures
    assert rules.offered("server", "hybrid") == ("hybrid", "full_pq") and rules.offered("server", "pq_only") == ("full_pq",)
    assert rules.offered("server", None) == ()


def test_a_blocker_is_only_something_to_fix_before_the_change():
    fine = {"tls13": "on", "weak_certificate": False}
    assert rules.blockers("server", "hybrid", fine) == []                      # turning hybrid on is the change itself
    assert rules.blockers("server", "hybrid", {"tls13": "off", "weak_certificate": True}) == ["no_tls13", "weak_certificate"]
    assert rules.blockers("server", "keep", {"tls13": "off"}) == [] and rules.blockers("server", "wrap", {"tls13": "off"}) == []
    assert rules.blockers("server", "full_pq", fine) == []                     # "every client must support it" is a thing to check, not a blocker
    assert rules.blockers("software", "full_pq", {"post_quantum_signatures": False}) == ["no_pq_signature"]
    assert rules.blockers("software", "hybrid", {"post_quantum_signatures": False}) == ["no_pq_signature"]


def test_the_roadmap_bands():
    assert rules.band("server", "classical", "hybrid", _s(), []) == "phase1"
    assert rules.band("server", "classical", "hybrid", _s(), ["no_tls13"]) == "phase2"
    assert rules.band("server", "classical", "hybrid", _s("long", "internal"), []) == "phase2"
    assert rules.band("server", "classical", "hybrid", _s("short", "internet"), []) == "phase2"
    assert rules.band("software", "classical", "hybrid", _s(), ["no_pq_signature"]) == "phase2"
    assert rules.band("server", "hybrid", "hybrid", _s(), []) == "already"
    assert rules.band("server", "pq_only", "full_pq", _s(), []) == "already"
    assert rules.band("server", "classical", "full_pq", _s(), rules.blockers("server", "full_pq", {"tls13": "on"})) == "phase1"
    assert rules.band("server", "classical", "keep", _s(), []) == "later"
    assert rules.band("server", "classical", "wrap", _s(), []) == "wrapped"
    assert rules.band("server", None, None, _s(), []) == "not_placed"


def test_a_review_date_is_never_forever():
    assert rules.default_review_date(date(2026, 11, 14)) == date(2027, 11, 14)
    assert rules.default_review_date(date(2028, 2, 29)) == date(2029, 2, 28)
    assert rules.default_review_date(date(2030, 6, 1)) == rules.LATEST_REVIEW == date(2030, 12, 31)
    today = date(2026, 11, 14)
    assert rules.review_date_problem(None, today) == "missing" and rules.review_date_problem("never", today) == "missing"
    assert rules.review_date_problem("2026-11-14", today) == "past"
    assert rules.review_date_problem("2031-01-01", today) == "too_late"
    assert rules.review_date_problem("2030-12-31", today) is None


# ------------------------------------------------------------------ the CSV additions

def test_the_file_can_claim_a_post_quantum_status_and_give_settings():
    parsed = parse_file("m.csv", (DEMO_DIR / "migration-demo.csv").read_bytes())
    claims = {(c.location, c.kind): c for c in parsed.claims}
    assert claims[("localhost:8455", "post_quantum")].claimed_value == "Post-quantum only"
    assert claims[("localhost:8452", "post_quantum")].detail["status"] == "Hybrid"
    assert len(parsed.claims) == 7 and len(parsed.settings) == 11
    assert {(s.location, s.field, s.value) for s in parsed.settings} >= {
        ("localhost:8454", "can_change", "no"), ("localhost:8453", "lifespan", "short"), ("acme-sign 1.4.2", "lifespan", "long")}
    real = parse_file("r.csv", (DEMO_DIR / "migration-real-servers.csv").read_bytes())
    assert [c.location for c in real.claims] == ["pq.cloudflareresearch.com:443", "ecc256.badssl.com:443", "tls-v1-2.badssl.com:1012"]
    assert real.settings == []


@pytest.mark.parametrize("rows", [
    ("localhost:1,tls,post_quantum,quantum-proof",),                                   # not a status
    ("localhost:1,tls,post_quantum,hybrid", "localhost:2,system,exposure,internal"),   # a setting for a system with no claim
    ("localhost:1,tls,post_quantum,hybrid", "localhost:1,system,exposure,outside"),    # not a value
    ("localhost:1,tls,post_quantum,hybrid", "localhost:1,system,exposure,internal", "localhost:1,system,exposure,internal"),
    ("localhost:1,tls,post_quantum,hybrid", "localhost:1,system,colour,blue"),
])
def test_a_file_with_a_bad_migration_row_is_refused_with_its_line(rows):
    with pytest.raises(ImportFileError) as caught:
        parse_file("m.csv", csv_bytes(*rows))
    assert caught.value.line


# ------------------------------------------------------------------ the whole flow on the migration demo file

@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """One lab in demo mode: the migration demo file imported (which starts its five test servers), confirmed,
    verified and measured once."""
    ports = _ports()
    lab = make_lab(tmp_path_factory.mktemp("migration"), migration_ports=ports)
    play_back_speed(lab)
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        verify = lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        before = lab.migration_view_for_import(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 300)
        addr = dict(zip(ROLES, [f"localhost:{p}" for p in ports]))
        yield type("Flow", (), dict(lab=lab, imp=imp, verify=verify, plan=plan, before=before, addr=addr, ports=ports))
    finally:
        lab.stop()


def _system(view, name):
    return next(s for s in view["systems"] if s["name"] == name)


def _text(parts):
    return "".join(f"[{p['v']}]" if p["t"] == "tag" else p["v"] for p in parts)


def test_importing_the_file_starts_its_servers_and_lists_its_settings(flow):
    assert flow.imp["is_demo"] is True
    assert flow.imp["notices"] == [f"Demo data: started the five demo test servers for this file on this computer (ports {', '.join(map(str, flow.ports))})."]
    assert {"location": flow.addr["legacy_tls12"], "text": "Exposure: internal. Data lifespan: long-lived. Can it be changed: no."} in flow.imp["settings"]
    assert sorted(flow.lab.migration_servers.running) == sorted(flow.ports)


def test_no_other_file_starts_the_migration_servers(tmp_path):
    lab = make_lab(tmp_path, migration_ports=_ports())
    try:
        lab.import_demo()
        lab.import_file("other.csv", csv_bytes(f"localhost:{lab.settings.migration_ports[0]},tls,post_quantum,hybrid"))
        assert lab.migration_servers.running == []
    finally:
        lab.stop()


def test_a_file_that_only_makes_the_same_claims_never_starts_the_servers(tmp_path):
    """Our demo file without its settings rows (or with one changed) is somebody's own file: nothing starts for it,
    not on import and not later on Verify or Measure, and its addresses are checked like any other."""
    ports = _ports()
    lab = make_lab(tmp_path, migration_ports=ports)
    try:
        ours = migration_servers.file_for(ports).decode()
        for theirs in ("\n".join(line for line in ours.splitlines() if ",system," not in line) + "\n",
                       ours.replace(f"localhost:{ports[0]},system,exposure,internet-facing", f"localhost:{ports[0]},system,exposure,internal")):
            imp = lab.import_file("my-own.csv", theirs.encode())
            assert "notices" not in imp
            for a in imp["addresses"]:
                lab.confirm_address(imp["id"], a["address"], True)
            results = lab.verify(imp["id"])["results"]
            plan = lab.ensure_plan(imp["id"])
            lab.measure_migration(plan["id"])
            lab.wait_until_measured(plan["id"], 120)
            assert lab.migration_servers.running == []
            assert {r["result"] for r in results if r["claim"]["kind"] == "post_quantum"} == {COULDNT}   # nothing answers on those ports
    finally:
        lab.stop()


def test_verify_checks_the_post_quantum_claims_and_finds_the_planted_false_one(flow):
    got = {r["claim"]["location"]: r for r in flow.verify["results"]}
    assert [got[flow.addr[r]]["result"] for r in ROLES] == [TRUE, FALSE, TRUE, TRUE, TRUE]
    wrong = got[flow.addr["classical_internet"]]
    assert wrong["summary"] == ("It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical. "
                                "The file says Hybrid, so the claim is not true.")
    assert got["acme-sign 1.4.2"]["result"] == TRUE and got["acme-sign 9.9"]["result"] == COULDNT
    assert all(r["evidence"] for r in flow.verify["results"] if r["claim"]["kind"] == "post_quantum")


def test_nothing_is_measured_until_the_button_is_pressed(flow):
    assert flow.before["measure"]["label"] == "Measure status"
    assert {s["status"]["code"] for s in flow.before["systems"]} == {"not_measured"}
    assert all(s["options"] == [] and s["recommendation"]["none_text"] for s in flow.before["systems"])
    assert flow.before["roadmap"]["bands"][0]["key"] == "not_placed"


def test_each_system_gets_its_measured_status_recommendation_and_place_on_the_roadmap(flow):
    view = flow.lab.migration_view(flow.plan["id"])
    assert view["measure"]["label"] == "Measure again" and view["busy"] is False and view["is_demo"] is True
    assert view["tabs"]["systems"] == "Systems · 7"
    got = {s["name"]: (s["status"]["label"], s["recommendation"]["title"], s["plan_line"]) for s in view["systems"]}
    a = flow.addr
    assert got[a["hybrid"]] == ("Hybrid", "Recommended: Hybrid (in place today)", "Plan: Hybrid · already there")
    assert got[a["classical_internet"]] == ("Classical", "Recommended: Hybrid", "Plan: Hybrid · Phase 1")
    assert got[a["classical_internal"]][:2] == ("Classical", "Recommended: Keep classical for now")
    assert got[a["classical_internal"]][2].startswith("Plan: Keep classical · review ")
    assert got[a["legacy_tls12"]] == ("Classical", "Recommended: Wrap the connection", "Plan: Wrap the connection")
    assert got[a["pq_only"]] == ("Post-quantum only", "Recommended: Full post-quantum (in place today)", "Plan: Full post-quantum · already there")
    assert got["acme-sign 1.4.2"] == ("Classical", "Recommended: Hybrid: sign with both", "Plan: Hybrid · Phase 2")
    assert got["acme-sign 9.9"] == ("Couldn't check", "No recommendation yet", "No plan yet: couldn't check")
    bands = {b["key"]: [r["name"] for r in b["rows"]] for b in view["roadmap"]["bands"]}
    assert bands == {"already": [a["hybrid"], a["pq_only"]], "phase1": [a["classical_internet"]], "phase2": ["acme-sign 1.4.2"],
                     "later": [a["classical_internal"]], "wrapped": [a["legacy_tls12"]], "not_placed": ["acme-sign 9.9"]}
    assert all(r["plan_tag"] == "recommended, not yet chosen by you" for b in view["roadmap"]["bands"] for r in b["rows"] if b["key"] != "not_placed")


def test_turning_hybrid_on_is_the_change_itself_not_a_blocker(flow):
    view = flow.lab.migration_view(flow.plan["id"])
    server = _system(view, flow.addr["classical_internet"])
    hybrid = next(o for o in server["options"] if o["key"] == "hybrid")
    sections = {s["title"]: s["lines"] for s in hybrid["sections"]}
    assert [_text(line["text"]) for line in sections["Blockers"]] == ["None measured."]
    assert sections["To do"][0]["fix_id"] and "the change itself, not a blocker" in _text(sections["To do"][0]["text"])
    cost = [_text(line["text"]) for line in sections["Cost"]]
    assert cost[0] == "Key shares today: 32 bytes (client) and 32 bytes (server) [measured]."               # each number under its own source
    assert cost[1] == "Key shares with hybrid: 1,216 bytes (client) and 1,120 bytes (server) [published: FIPS 203 + X25519]."
    full = {s["title"]: [_text(line["text"]) for line in s["lines"]] for s in next(o for o in server["options"] if o["key"] == "full_pq")["sections"]}
    assert full["Blockers"] == ["None measured."]                                # what can't be measured is not called a blocker
    assert full["To do"][0] == "Check that every client supports it. This app can't see your clients [not measured]."
    row = next(r for b in view["roadmap"]["bands"] if b["key"] == "phase1" for r in b["rows"])
    assert _text(row["note"]["text"]) == "To do: turn on hybrid key exchange." and row["note"]["fix_id"] == sections["To do"][0]["fix_id"]
    # the old TLS 1.2 server does have a blocker for hybrid: no TLS 1.3
    legacy = next(o for o in _system(view, flow.addr["legacy_tls12"])["options"] if o["key"] == "hybrid")
    blockers = [_text(line["text"]) for s in legacy["sections"] if s["title"] == "Blockers" for line in s["lines"]]
    assert blockers == ["It doesn't accept TLS 1.3, which post-quantum key exchange needs (it accepts TLS 1.2) [measured]."]


def test_every_number_says_where_it_came_from(flow):
    view = flow.lab.migration_view(flow.plan["id"])
    allowed = ("measured", "measured on our test server", "measured on the reference library", "this program plus the reference library",
               "published: FIPS 203", "published: FIPS 203 + X25519", "published: FIPS 204")
    for system in view["systems"]:
        if system["cost"] is None:
            assert system["status"]["code"] == "couldnt_check"
            continue
        for row in system["cost"]["rows"]:
            for cell in row["cells"]:
                text, tags = _text(cell), [p["v"] for p in cell if p["t"] == "tag"]
                if any(ch.isdigit() for ch in cell[0]["v"]):
                    assert len(tags) == 1 and tags[0] in allowed, (system["name"], row["label"], text)
    classical = _system(view, flow.addr["classical_internet"])["cost"]
    cells = {r["label"]: [_text(c) for c in r["cells"]] for r in classical["rows"]}
    assert classical["columns"] == ["", "Classical (today)", "Hybrid", "Full post-quantum"]
    assert cells["Key share, client to server"] == ["32 bytes [measured]", "1,216 bytes [published: FIPS 203 + X25519]", "1,184 bytes [published: FIPS 203]"]
    assert cells["Certificate public key"] == ["65 bytes [measured]", "no change", "1,952 bytes [published: FIPS 204]"]
    assert cells["A classical-only client still connects"] == ["Yes [measured]", "Yes [measured on our test server]", "No: there is no classical fallback"]
    hybrid = {r["label"]: [_text(c) for c in r["cells"]] for r in _system(view, flow.addr["hybrid"])["cost"]["rows"]}
    assert hybrid["Key share, client to server"][:2] == ["32 bytes [measured]", "1,216 bytes [measured]"]     # both measured on the server itself
    pq = {r["label"]: [_text(c) for c in r["cells"]] for r in _system(view, flow.addr["pq_only"])["cost"]["rows"]}
    assert pq["Key share, client to server"][2] == "1,184 bytes [measured]" and pq["Handshake signature"][2] == "3,309 bytes [measured]"
    assert pq["A classical-only client still connects"][2] == "No [measured]"
    program = {r["label"]: [_text(c) for c in r["cells"]] for r in _system(view, "acme-sign 1.4.2")["cost"]["rows"]}
    assert program["Public key size"] == ["65 bytes [measured]", "2,017 bytes [this program plus the reference library]",
                                          "1,952 bytes [measured on the reference library]"]


def test_the_reasons_name_their_sources_and_link_to_the_evidence(flow):
    view = flow.lab.migration_view(flow.plan["id"])
    server = _system(view, flow.addr["classical_internet"])
    reasons = [_text(r) for r in server["recommendation"]["reasons"]]
    assert reasons[0].startswith("Long-lived data [from the file]:") and reasons[1].startswith("Internet-facing [from the file]:")
    assert "a classical-only client still connects [measured on our test server]" in reasons[2]
    assert reasons[3] == "NIST dates: today's public-key algorithms are deprecated after 2030 and disallowed after 2035 [reference: NIST IR 8547]."
    assert server["recommendation"]["tag"] == "from fixed rules, no AI model"
    assert server["today"]["result"]["run_id"] and server["today"]["result"]["locked_test"]["fingerprint"]
    assert server["today"]["file_note"] == "The file says: this server is Hybrid. Verify marked that claim False."
    assert server["today"]["control_line"].endswith("as expected.")
    pq = _system(view, flow.addr["pq_only"])
    assert [f["source"] for f in pq["settings"]["fields"]] == ["from the file", "assumed", "assumed"]
    assert [f["value"] for f in pq["settings"]["fields"]] == ["long", "internal", "yes"]


def test_no_score_and_no_verdict_beyond_what_was_measured(flow):
    plan_id = flow.plan["id"]
    text = json.dumps([flow.lab.migration_view(plan_id), flow.lab.fixes_view(plan_id)]).lower()
    text = text.replace("doesn't prove a system secure", "")
    for word in ("secure", "score", "safe", "unbreakable", "quantum-proof", "years to break"):
        assert word not in text, word


def test_the_measurements_are_not_tests(flow):
    plan = flow.lab.plan_view(flow.plan["id"])
    assert plan["has_migration"] is True and plan["has_results"] is False
    # only acme-sign 1.4.2's three tests: the servers' claims have no suggested test, and a program that can't run gets no cards
    assert [t["kind"] for t in plan["tests"]] == ["official_vectors", "bad_signatures", "speed_size"]
    assert "Three tests suggested" in plan["intro"]
    assert "acme-sign 9.9: its tests can't run. Only our own demo components can run in this version." in plan["not_tested"]["items"]
    assert all(g["heading"] != "Signing program: acme-sign 9.9" for g in plan["groups"])
    lab_view = flow.lab.lab_view(plan["id"])
    assert len(lab_view["rows"]) == 3 and lab_view["download"]["can_start"] is True
    view = flow.lab.migration_view(plan["id"])
    hidden = _system(view, flow.addr["hybrid"])["today"]["result"]["run_id"]
    from app.db import TestRunRow
    with flow.lab.db() as db:
        item_id = db.get(TestRunRow, hidden).plan_item_id
    with pytest.raises(NotFound):
        flow.lab.run_test(plan["id"], item_id)
    with pytest.raises(NotFound):
        flow.lab.remove_test(plan["id"], item_id)


def test_the_fixes_step_gets_the_how_to_and_the_blocker_as_text_only(flow):
    view = flow.lab.fixes_view(flow.plan["id"])
    assert view["subline"].startswith("Fixes for the findings in Evidence Lab, and what the migration plan needs done.")
    fixes = view["fixes"]
    titles = [f["title"] for f in fixes]
    assert titles == [f"Turn on hybrid key exchange on {flow.addr['classical_internet']}", "acme-sign 1.4.2 can't make post-quantum signatures"]
    howto = fixes[0]
    assert howto["kind"] == "text" and howto["status"]["key"] == "text_only" and howto["actions"]["buttons"] == []
    assert "the app has not applied it or tested it" in howto["proof"]["text"]
    suggestion = howto["sections"][0]["suggestion"]
    assert suggestion["intro"][0] == "This is the change itself, not a blocker: nothing that was measured stands in its way."
    rows = {r["place"]: r for r in suggestion["where"]["rows"]}
    assert (rows["nginx"]["lead"], rows["nginx"]["code"]) == ("Checked on nginx 1.31.8 with OpenSSL 3.5.9:", "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;")
    assert rows["Apache"]["lead"].startswith("Checked on Apache ") and rows["Your own application"]["lead"].startswith("Not checked on real software")
    assert all(r["lead"].startswith(("Checked on ", "Not checked on real software")) for r in rows.values())   # every line says which
    assert "stops nginx from starting" in suggestion["where"]["after"][1] and "Measure again" in suggestion["where"]["after"][2]
    assert "can't make post-quantum signatures" in fixes[1]["title"] and fixes[1]["approvers"]["text"].startswith("Whoever looks after this software")


def test_the_readiness_test_and_the_migration_step_never_disagree(flow):
    lab = flow.lab
    lab.add_test(flow.plan["id"], "pq_readiness")
    plan = lab.plan_view(flow.plan["id"])
    cards = [t for t in plan["tests"] if t["kind"] == "pq_readiness"]
    assert len(cards) == 5
    for card in cards:
        lab.run_test(flow.plan["id"], card["id"])
        lab.wait_until_idle(flow.plan["id"], 120)
    rows = {r["group"]: r["result"] for r in lab.lab_view(flow.plan["id"])["rows"] if r["kind"] == "pq_readiness"}
    status = {s["name"]: s["status"]["code"] for s in lab.migration_view(flow.plan["id"])["systems"]}
    for address in flow.addr.values():
        want = "offered" if status[address] in ("hybrid", "pq_only") else "not_offered"
        assert rows["server:" + address]["code"] == want, address
        assert rows["server:" + address]["mode"] == "demo"        # no Docker and no OpenSSL program needed
    for card in cards:
        lab.remove_test(flow.plan["id"], card["id"])


def test_a_setting_changes_the_recommendation_and_the_file_value_is_kept(flow):
    lab, plan_id, key = flow.lab, flow.plan["id"], "server:" + flow.addr["classical_internal"]
    view = lab.set_migration_setting(plan_id, key, "lifespan", "long")
    system = _system(view, flow.addr["classical_internal"])
    assert system["recommendation"]["title"] == "Recommended: Hybrid" and system["plan_line"] == "Plan: Hybrid · Phase 2"
    assert [f["source"] for f in system["settings"]["fields"]] == ["set by you", "from the file", "assumed"]
    assert len(lab.fixes_view(plan_id)["fixes"]) == 3                       # its how-to joined the list
    from app.db import SystemSettingRow
    with lab.db() as db:
        rows = [(r.value, r.source) for r in db.query(SystemSettingRow).filter_by(system_key=key, field="lifespan").order_by(SystemSettingRow.id)]
    assert rows == [("short", "file"), ("long", "user")]                    # added to, never overwritten
    view = lab.set_migration_setting(plan_id, key, "lifespan", "short")
    assert _system(view, flow.addr["classical_internal"])["recommendation"]["title"] == "Recommended: Keep classical for now"
    assert len(lab.fixes_view(plan_id)["fixes"]) == 2
    with pytest.raises(BadRequest):
        lab.set_migration_setting(plan_id, key, "lifespan", "forever")
    with pytest.raises(NotFound):
        lab.set_migration_setting(plan_id, "server:localhost:1", "lifespan", "long")


def test_a_choice_needs_a_reason_when_it_differs_and_a_review_date_when_it_keeps(flow):
    lab, plan_id, key = flow.lab, flow.plan["id"], "server:" + flow.addr["classical_internet"]
    with pytest.raises(BadRequest) as no_reason:
        lab.choose_migration_option(plan_id, key, "keep", "  ", "2027-06-30")
    assert no_reason.value.field == "reason"
    for bad in (None, "2020-01-01", "2031-01-01", "forever"):
        with pytest.raises(BadRequest) as no_date:
            lab.choose_migration_option(plan_id, key, "keep", "Replaced next year.", bad)
        assert no_date.value.field == "review_date"
    with pytest.raises(BadRequest):
        lab.choose_migration_option(plan_id, "software:" + _program_ref(flow, "acme-sign 1.4.2"), "wrap", "why not", None)
    with pytest.raises(Conflict):   # no status, so nothing to choose between
        lab.choose_migration_option(plan_id, "software:" + _program_ref(flow, "acme-sign 9.9"), "keep", "x", "2027-06-30")


def _program_ref(flow, label):
    return next(c["ref"] for c in flow.imp["claims"] if c["location"] == label)


def test_the_users_choice_is_recorded_followed_and_never_overwritten(flow):
    lab, plan_id, address = flow.lab, flow.plan["id"], flow.addr["classical_internet"]
    key = "server:" + address
    view = lab.choose_migration_option(plan_id, key, "keep", "Server is replaced in Q2 2027.", "2027-06-30")
    system = _system(view, address)
    assert system["plan_line"] == "Plan: Keep classical · review 30 Jun 2027"
    assert system["choice"]["line"].startswith("Your choice: Keep classical for now, saved ") and "Server is replaced in Q2 2027." in system["choice"]["line"]
    assert system["recommendation"]["title"] == "Recommended: Hybrid"             # the recommendation still says what the rules say
    keep = next(o for o in system["options"] if o["key"] == "keep")
    assert keep["tags"] == ["Your choice"] and keep["highlighted"] is True
    later = next(b for b in view["roadmap"]["bands"] if b["key"] == "later")
    row = next(r for r in later["rows"] if r["name"] == address)
    assert row["plan_tag"] == "chosen by you" and _text(row["note"]["text"]).startswith("Review by 30 Jun 2027 [chosen by you]")
    assert all(f["title"] != f"Turn on hybrid key exchange on {address}" for f in lab.fixes_view(plan_id)["fixes"])   # the roadmap follows the choice
    # a new measurement changes nothing about the choice
    lab.measure_migration(plan_id)
    lab.wait_until_measured(plan_id, 300)
    assert _system(lab.migration_view(plan_id), address)["plan_line"] == "Plan: Keep classical · review 30 Jun 2027"
    # a second choice is a new record; the first one is kept
    view = lab.choose_migration_option(plan_id, key, "hybrid", "", None)
    system = _system(view, address)
    assert system["plan_line"] == "Plan: Hybrid · Phase 1" and len(system["choice"]["history"]) == 1
    assert "Keep classical for now" in system["choice"]["history"][0]
    from app.db import MigrationChoiceRow
    with lab.db() as db:
        rows = db.query(MigrationChoiceRow).filter_by(system_key=key).order_by(MigrationChoiceRow.id).all()
        assert [(r.option, r.review_date) for r in rows] == [("keep", "2027-06-30"), ("hybrid", None)]
        assert rows[0].basis["recommended"] == "hybrid" and rows[0].basis["status"] == "classical"
        with pytest.raises(Exception):     # the table itself refuses a change
            rows[0].reason = "edited"
            db.commit()


@pytest.mark.parametrize("table, column", [("system_settings", "value"), ("migration_choices", "reason")])
def test_raw_sql_cannot_change_or_delete_a_setting_or_a_choice(flow, table, column):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    flow.lab.choose_migration_option(flow.plan["id"], "software:" + _program_ref(flow, "acme-sign 1.4.2"), "hybrid", "", None)
    with flow.lab.db() as db:
        before = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        assert before > 0
        for statement in (f"UPDATE {table} SET {column} = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == before


def test_the_plan_goes_into_the_evidence_file_and_the_report(flow, tmp_path):
    from evidence import trusted_key_from_data_dir, verify_bytes
    lab = flow.lab
    export = lab.export_evidence(flow.plan["id"])
    _, raw, _ = lab.evidence_file(export["id"], "json")
    _, report, _ = lab.evidence_file(export["id"], "html")
    assert verify_bytes(raw, trusted_key_from_data_dir(lab.settings.data_dir)).ok
    migration = json.loads(raw)["evidence"]["migration"]
    by_name = {s["system"]: s for s in migration["systems"]}
    server = by_name[flow.addr["classical_internet"]]
    assert server["status"] == "Classical" and server["recommendation"]["option"] == "Hybrid"
    assert server["recommendation"]["made_by"] == "from fixed rules, no AI model" and server["recommendation"]["reasons"]
    assert server["your_choice"]["option"] == "Hybrid" and server["earlier_choices"][0]["reason"] == "Server is replaced in Q2 2027."
    assert server["plan"]["roadmap"] == "Phase 1" and server["plan"]["from"] == "your choice"
    assert by_name["acme-sign 9.9"]["recommendation"] is None and by_name["acme-sign 9.9"]["plan"] is None
    assert [b["phase"] for b in migration["roadmap"]] == ["Already there", "Phase 1", "Phase 2", "Later", "Wrapped", "Not placed yet"]
    measured = {m["system"]: m for m in migration["measurements"]}
    run = measured[flow.addr["pq_only"]]["runs"][0]
    assert run["review"]["verdict"]["code"] == "pq_only" and run["record"]["raw"]["subject"]["probes"]["pure"]["state"] == "offered"
    page = report.decode()
    assert "5. Migration plan" in page and "Recommended: Hybrid" in page and "Server is replaced in Q2 2027." in page
    assert "<script" not in page


def test_an_unconfirmed_address_is_not_contacted_and_reads_couldnt_check(tmp_path):
    lab = make_lab(tmp_path, migration_ports=_ports())
    try:
        calls = []
        lab.resolver = lambda host: calls.append(host) or ["127.0.0.1"]
        imp = lab.import_file("real.csv", (DEMO_DIR / "migration-real-servers.csv").read_bytes())
        assert imp["is_demo"] is False and lab.migration_servers.running == [] and calls == []   # a file makes this computer contact nothing
        plan = lab.ensure_plan(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 120)
        view = lab.migration_view(plan["id"])
        assert calls == []
        assert {s["status"]["code"] for s in view["systems"]} == {"couldnt_check"}
        assert all("you haven't confirmed" in s["today"]["sentence"] for s in view["systems"])
        assert all(s["options"] == [] for s in view["systems"])
        assert [f["value"] for f in view["systems"][0]["settings"]["fields"]] == ["long", "internet", "yes"]   # a public name: assumed internet-facing
        assert {f["source"] for f in view["systems"][0]["settings"]["fields"]} == {"assumed"}
        assert lab.fixes_view(plan["id"])["fixes"] == []
        assert lab.plan_view(plan["id"])["has_migration"] is False      # nothing for the Fixes step, so it does not open for this
        assert lab.lab_view(plan["id"])["download"]["can_start"] is True  # but the measurements can be downloaded
    finally:
        lab.stop()


def test_without_the_post_quantum_engine_it_says_couldnt_check_and_never_crashes_or_guesses(tmp_path, monkeypatch):
    monkeypatch.setattr(pqtls, "available", lambda: (False, "this copy of the cryptography library has no ML-KEM"))
    ports = _ports()
    lab = make_lab(tmp_path, migration_ports=ports)
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        results = {r["claim"]["location"]: r["result"] for r in lab.verify(imp["id"])["results"] if r["claim"]["kind"] == "post_quantum"}
        assert set(results.values()) == {COULDNT}
        plan = lab.ensure_plan(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 120)
        view = lab.migration_view(plan["id"])
        servers = [s for s in view["systems"] if s["kind_label"] == "Server"]
        assert {s["status"]["code"] for s in servers} == {"couldnt_check"}
        assert all(s["recommendation"]["title"] == "No recommendation yet" and s["options"] == [] for s in servers)
        assert {b["key"] for b in view["roadmap"]["bands"]} == {"not_placed", "phase2"}      # only the signing program still has a status
        lab.add_test(plan["id"], "pq_readiness")
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 300)
        rows = [r["result"] for r in lab.lab_view(plan["id"])["rows"] if r["kind"] == "pq_readiness"]
        assert rows and all(r["code"] == "couldnt_run" for r in rows)
    finally:
        lab.stop()


def test_the_api_routes(client, settings):
    ports = _ports()
    object.__setattr__(settings, "migration_ports", ports)
    assert upload(client, "migration-demo.csv", migration_servers.file_for(ports)).status_code == 200
    imp = client.get("/api/import/current").json()
    assert imp["settings_title"] and len(imp["settings"]) == 6
    view = client.get(f"/api/import/{imp['id']}/migration").json()
    plan_id = view["plan_id"]
    assert client.post(f"/api/plans/{plan_id}/migration/measure", json={}).status_code == 200
    key = view["systems"][0]["key"]
    assert client.post(f"/api/plans/{plan_id}/migration/settings", json={"system": key, "field": "exposure", "value": "internal"}).status_code == 200
    bad = client.post(f"/api/plans/{plan_id}/migration/settings", json={"system": key, "field": "exposure", "value": "moon"})
    assert bad.status_code == 422 and bad.json()["error"]["field"] == "value"
    assert client.post(f"/api/plans/{plan_id}/migration/choice", json={"system": "server:nowhere:1", "option": "keep", "reason": "x",
                                                                       "review_date": "2027-01-01"}).status_code == 404
    client.post("/api/logout")
    assert client.get(f"/api/import/{imp['id']}/migration").status_code in (200, 401)


def test_the_routes_need_a_login(anon_client):
    assert anon_client.get("/api/import/1/migration").status_code == 401
    assert anon_client.post("/api/plans/1/migration/measure", json={}).status_code == 401


def test_isolated_mode_adds_the_openssl_container_as_a_second_opinion(docker_ready, tmp_path):
    ports = _ports()
    lab = make_lab(tmp_path, migration_ports=ports, force_mode="isolated")
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        plan = lab.ensure_plan(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 600)
        view = lab.migration_view(plan["id"])
        assert [s["status"]["code"] for s in view["systems"]] == ["hybrid", "classical", "classical", "classical", "pq_only", "classical", "couldnt_check"]
        facts = {f["label"]: _text(f["value"]) for f in view["systems"][0]["today"]["facts"]}
        assert facts["Second opinion (OpenSSL 3.5 container)"] == "Its own client completed a hybrid handshake [measured]"
        facts = {f["label"]: _text(f["value"]) for f in view["systems"][1]["today"]["facts"]}
        assert facts["Second opinion (OpenSSL 3.5 container)"] == "Its own client was refused a hybrid handshake [measured]"
    finally:
        lab.stop()
