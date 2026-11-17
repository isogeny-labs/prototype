"""Phase 4b: make it real. Two tracks and a target, the new measurements, a change ready to apply, Try on a test copy,
Apply with approval, Roll back, and the Acme Pay server's TLS fix (SPEC 7c). Demo mode unless a test asks for Docker;
no internet: every server is on this computer, on a spare port."""
import json

import pytest

from app.migration import change_builder
from app.migration import rules
from app.servers import migration_servers
from app.checks import pqtls
from app.errors import BadRequest, Conflict, NotFound
from app.engine.reviewer import apply_outcome, change_try_outcome, meets_promise, pq_status_of, rollback_outcome
from app.web import models
from conftest import csv_bytes, free_port, make_lab
from view_helpers import problems


def _ports(n=5):
    return tuple(free_port() for _ in range(n))


def _text(parts):
    return "".join(f"[{p['v']}]" if p["t"] == "tag" else p["v"] for p in parts)


# ------------------------------------------------------------------ the measurement

def test_the_handshake_signature_algorithm_is_read_on_every_kind_of_server():
    ports = _ports()
    servers = migration_servers.MigrationServers(ports)
    assert servers.start() == []
    try:
        seen = {}
        for port in ports:
            h = pqtls.handshake("127.0.0.1", port, "localhost", "X25519MLKEM768:MLKEM768:X25519:P-256", min_version="TLS 1.2")
            seen[port] = pqtls.SIGNATURE_SCHEMES.get(h.signature_scheme)
        assert [seen[p] for p in ports] == ["ECDSA P-256 with SHA-256"] * 3 + ["RSA-PSS with SHA-256", "ML-DSA-65"]
    finally:
        servers.stop()


def test_both_keys_at_once_shows_which_one_the_server_takes():
    cert, key, _ = pqtls.test_certificate("ecdsa-p256", "t")
    hybrid = pqtls.Server(groups="X25519MLKEM768:X25519:P-256", certificate_pem=cert, key_pem=key)
    classical = pqtls.Server(groups="X25519:P-256", certificate_pem=cert, key_pem=key)
    try:
        assert pqtls.handshake("127.0.0.1", hybrid.port, None, "*X25519MLKEM768:*X25519").group == "X25519MLKEM768"
        assert pqtls.handshake("127.0.0.1", hybrid.port, None, "*X25519:*X25519MLKEM768").group == "X25519"   # follows the client's order
        assert pqtls.handshake("127.0.0.1", classical.port, None, "*X25519MLKEM768:*X25519").group == "X25519"
    finally:
        hybrid.close()
        classical.close()


def _hs(outcome, group=None, scheme=None, version="TLS 1.3"):
    return {"outcome": outcome, "group": group, "tls_version": version if outcome == "completed" else None, "signature_scheme": scheme,
            "client_hello_bytes": 300, "client_share_bytes": 32, "server_share_bytes": 32, "certificate_message_bytes": 400, "signature_bytes": 71}


def _probe(state, group=None):
    return {"state": state, "group": group if state == "offered" else None, "offered": [], "detail": ""}


def _control(hybrid_pick="X25519MLKEM768", classical_pick="X25519", hybrid_second="X25519", classical_second="X25519"):
    return {"hybrid": {"probes": {"hybrid": _probe("offered", "X25519MLKEM768"), "pure": _probe("refused"), "classical": _probe("offered", "X25519")},
                       "default_choice": {"hybrid_first": _hs("completed", hybrid_pick), "classical_first": _hs("completed", hybrid_second)}},
            "classical": {"probes": {"hybrid": _probe("refused"), "pure": _probe("refused"), "classical": _probe("offered", "X25519")},
                          "default_choice": {"hybrid_first": _hs("completed", classical_pick), "classical_first": _hs("completed", classical_second)}},
            "reference": {}}


def _raw(cert, scheme, *, hybrid=True, control=None, versions=("TLS 1.3", "TLS 1.2")):
    probes = {"hybrid": _probe("offered" if hybrid else "refused", "X25519MLKEM768"), "pure": _probe("refused"), "classical": _probe("offered", "X25519")}
    return {"subject": {"probes": probes, "versions": {v: {"state": "accepted" if v in versions else "refused"} for v in ("TLS 1.3", "TLS 1.2", "TLS 1.1", "TLS 1.0")},
                        "classical_client": _hs("completed", "X25519", scheme), "hybrid_handshake": _hs("completed" if hybrid else "refused", "X25519MLKEM768", scheme),
                        "pure_handshake": None, "certificate": cert, "container": None, "timing": None,
                        "default_choice": {"hybrid_first": _hs("completed", "X25519MLKEM768"), "classical_first": _hs("completed", "X25519")} if hybrid else None},
            "control": control or _control()}


EC = {"algorithm": "EC", "curve": "secp256r1", "key_bits": 256, "normalized": "ECDSA P-256", "signature_algorithm": "ecdsa-with-SHA256"}
MLDSA = {"algorithm": "MLDSA65", "key_bits": None, "signature_algorithm": "ML-DSA-65"}


@pytest.mark.parametrize("cert, scheme, status", [
    (EC, 0x0403, "classical"), (MLDSA, 0x0905, "post_quantum"),
    (EC, 0x0905, "couldnt_check"),          # one classical, one post-quantum: no single status
    (None, 0x0403, "couldnt_check"),        # no certificate read
    (EC, None, "couldnt_check"),            # no signature read
])
def test_the_authentication_track(cert, scheme, status):
    found = pq_status_of(_raw(cert, scheme), tracks=True)
    assert found["detail"]["auth"]["status"] == status


def test_the_default_choice_and_also_noticed_are_facts_never_a_status():
    found = pq_status_of(_raw(EC, 0x0403, versions=("TLS 1.3", "TLS 1.2", "TLS 1.1", "TLS 1.0")), tracks=True)
    assert found["code"] == "hybrid" and found["control"]["outcome"] == "as_expected"
    assert found["detail"]["default_choice"]["hybrid_first"] == "hybrid" and found["detail"]["default_choice"]["classical_first"] == "classical"
    assert found["detail"]["also_noticed"] == [{"code": "old_tls", "versions": ["TLS 1.0", "TLS 1.1"]}]


def test_a_control_misread_on_the_both_keys_hello_means_the_run_is_not_trusted():
    assert pq_status_of(_raw(EC, 0x0403, control=_control(classical_pick="X25519MLKEM768")), tracks=True)["control"]["outcome"] == "not_as_expected"
    assert pq_status_of(_raw(EC, 0x0403, control=_control(hybrid_pick="X25519")), tracks=True)["control"]["outcome"] == "not_as_expected"
    # the second hello (classical listed first) has its control too
    assert pq_status_of(_raw(EC, 0x0403, control=_control(hybrid_second="X25519MLKEM768")), tracks=True)["control"]["outcome"] == "not_as_expected"
    assert pq_status_of(_raw(EC, 0x0403, control=_control(classical_second="X25519MLKEM768")), tracks=True)["control"]["outcome"] == "not_as_expected"
    # the phase 4a rule (stored runs) ignores the new check, so its stored results read the same
    assert pq_status_of(_raw(EC, 0x0403, control=_control(classical_pick="X25519MLKEM768")))["control"]["outcome"] == "as_expected"


# ------------------------------------------------------------------ the rules

def _s(lifespan="long", exposure="internet", can_change="yes"):
    return {"lifespan": lifespan, "exposure": exposure, "can_change": can_change}


@pytest.mark.parametrize("kind, track, status, option, settings, blocking, band", [
    ("server", "kex", "hybrid", "hybrid", _s(), [], "done_for_now"),
    ("server", "kex", "hybrid", "full_pq", _s(), [], "phase2"),            # the person chose to go further: not "done for now"
    ("server", "kex", "classical", "hybrid", _s(), [], "phase1"),
    ("server", "kex", "classical", "hybrid", _s(), ["no_tls13"], "phase2"),
    ("server", "kex", "pq_only", "full_pq", _s(), [], "target"),
    ("server", "auth", "classical", "hybrid", _s(), [], "phase2"),
    ("server", "auth", "post_quantum", "full_pq", _s(), [], "target"),
    ("server", "auth", "classical", "keep", _s(), [], "later"),
    ("server", "kex", "classical", "wrap", _s(), [], "wrapped"),
    ("software", "signatures", "classical", "hybrid", _s(), ["no_pq_signature"], "phase2"),
    ("server", "kex", None, None, _s(), [], "not_placed"),
])
def test_each_track_has_its_own_place_and_hybrid_is_never_the_end(kind, track, status, option, settings, blocking, band):
    assert rules.track_band(kind, track, status, option, settings, blocking) == band
    assert "already" not in rules.TRACK_BANDS


def test_a_change_is_built_from_the_servers_settings_and_its_fingerprint_is_stable():
    before = migration_servers.ROLE_SETTINGS["classical_internet"]
    a = change_builder.build(key="k", kind="migration", option="hybrid", system_key="server:x", address="localhost:1", name="x",
                             before=before, before_auth="classical", target="demo_test_server", target_words="ours", no_target=None)
    b = change_builder.build(key="k", kind="migration", option="hybrid", system_key="server:x", address="localhost:1", name="x",
                             before=before, before_auth="classical", target="demo_test_server", target_words="ours", no_target=None)
    assert a["fingerprint"] == b["fingerprint"]
    assert a["settings_after"] == {"groups": "X25519MLKEM768:X25519", "versions": ["TLS 1.2", "TLS 1.3"], "certificate": "ecdsa-p256"}
    assert a["promise"] == {"kex": "hybrid", "auth": "classical", "classical_client": "connects"}
    lines = {line["place"]: line for line in a["lines"]}
    assert lines["nginx"]["code"] == "ssl_protocols TLSv1.2 TLSv1.3;\nssl_ecdh_curve X25519MLKEM768:X25519;"
    assert lines["nginx"]["lead"] == "Checked on nginx 1.31.8 with OpenSSL 3.5.9:"
    assert lines["Apache"]["lead"] == "Checked on Apache 2.4.71 with OpenSSL 3.5.9:"
    assert lines["Your own application"]["lead"].startswith("Not checked on real software.")
    legacy = change_builder.settings_after("hybrid", migration_servers.ROLE_SETTINGS["legacy_tls12"])
    assert legacy["versions"] == ["TLS 1.2", "TLS 1.3"] and legacy["groups"].startswith("X25519MLKEM768")    # TLS 1.3 turned on with it
    full = change_builder.build(key="k", kind="migration", option="full_pq", system_key="s", address="a:1", name="a", before=before, before_auth="classical",
                                target=None, target_words=None, no_target="n")
    assert full["settings_after"] == {"groups": "MLKEM768", "versions": ["TLS 1.3"], "certificate": "mldsa-65"}
    assert "genpkey -algorithm ML-DSA-65" in full["certificate"]["code"] and "PRIVATE" not in json.dumps(full)
    keep = change_builder.build(key="k", kind="migration", option="keep", system_key="s", address="a:1", name="a", before=None, before_auth=None,
                                target=None, target_words=None, no_target="n", extra={"review_date": "2027-11-14"})
    assert keep["settings_after"] is None and keep["recheck"] and "31 December 2030" in " ".join(keep["recheck"])
    text = change_builder.download_text(full, "2026-11-14T00:00:00Z")
    assert "ssl_ecdh_curve MLKEM768;" in text and "PRIVATE KEY" not in text and "Nothing in it has been applied" in text


def test_the_verdicts_of_a_try_an_apply_and_a_roll_back():
    promise = {"kex": "hybrid", "auth": "classical", "classical_client": "connects"}
    good = {"code": "hybrid", "detail": {"auth": {"status": "classical"}, "classical_client": "connects"}}
    bad = {"code": "classical", "detail": {"auth": {"status": "classical"}, "classical_client": "connects"}}
    none = {"code": "couldnt_run", "detail": {}}
    assert change_try_outcome(promise, [("copy", good, None), ("nginx", None, "needs isolated mode")])["code"] == "passed"
    assert change_try_outcome(promise, [("copy", good, None), ("nginx", bad, None)])["code"] == "failed"   # real nginx must agree
    assert change_try_outcome(promise, [("copy", none, None)])["code"] == "couldnt_run"
    assert change_try_outcome(promise, [("nginx", None, "needs isolated mode")])["code"] == "not_run"
    assert apply_outcome(promise, good, good)["code"] == "matches"
    differs = apply_outcome(promise, good, bad)
    assert differs["code"] == "differs" and differs["differences"] == [{"fact": "kex", "tried": "hybrid", "after": "classical"}]
    assert rollback_outcome(bad, bad)["code"] == "as_before" and rollback_outcome(bad, good)["code"] == "differs"
    assert meets_promise({"tls": "passed"}, {"code": "passed", "detail": {}})[0] is True


# ------------------------------------------------------------------ the whole flow on the migration demo (demo mode)

@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    ports = _ports()
    lab = make_lab(tmp_path_factory.mktemp("phase4b"), migration_ports=ports, lab_nginx_port=free_port())
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        lab.measure_migration(plan["id"])
        lab.wait_until_measured(plan["id"], 300)
        addr = dict(zip(("hybrid", "c1", "c2", "legacy", "pq"), [f"localhost:{p}" for p in ports]))  # noqa: B905
        yield type("Flow", (), dict(lab=lab, imp=imp, pid=plan["id"], addr=addr, ports=ports))
    finally:
        lab.stop()


def _system(flow, name):
    return next(s for s in flow.lab.migration_view(flow.pid)["systems"] if s["name"] == name)


@pytest.mark.slow  # over 5 s on a slow machine (17 November 2026); runs with --full
def test_two_tracks_with_a_next_step_and_why_on_every_track(flow):
    view = flow.lab.migration_view(flow.pid)
    for system in view["systems"]:
        for track in system["tracks"]:
            if track["status"]["code"] not in ("couldnt_check", "not_measured"):
                assert _text(track["next"]).strip() and _text(track["why"]).strip(), (system["name"], track["key"])
    hybrid = _system(flow, flow.addr["hybrid"])
    assert [(t["short_title"], t["status"]["label"]) for t in hybrid["tracks"]] == [("Key exchange", "Hybrid (interim)"), ("Authentication", "Classical")]
    assert _text(hybrid["tracks"][1]["next"]) == "an ML-DSA certificate, once your clients can check one."
    facts = {f["label"]: _text(f["value"]) for f in hybrid["tracks"][0]["facts"]}
    assert facts["Chosen by default?"].startswith("Yes: offered both keys in one hello with hybrid listed first")
    assert facts["If the client lists classical first"].startswith("It takes X25519: this server follows the client's order")
    assert facts["Hybrid-only clients"].startswith("Connect")
    pq = _system(flow, flow.addr["pq"])
    assert all("keep it there" in _text(t["next"]) for t in pq["tracks"]) and pq["plan_line"] == "At the target · keep measuring"
    assert "Already there" not in json.dumps(view)
    nine = _system(flow, "acme-sign 9.9")      # a track that couldn't be checked says why (e2e finding)
    assert nine["tracks"][0]["sentence"].startswith("Couldn't check: only our own demo components can run in this version.")
    bands = {b["key"] for b in view["roadmap"]["bands"]}
    assert bands == {"target", "done_for_now", "phase1", "phase2", "later", "wrapped", "not_placed"}


def test_apply_is_off_until_the_try_passed_and_every_reviewer_approved(flow):
    lab, key = flow.lab, f"migration:server:{flow.addr['c1']}"
    with pytest.raises(Conflict, match="try on a test copy"):
        lab.apply_change(flow.pid, key)
    with pytest.raises(Conflict):
        lab.ask_approval(flow.pid, key, ["you"])              # not before a passing try
    lab.try_change(flow.pid, key)
    lab.wait_until_changes_idle(flow.pid)
    box = _system(flow, flow.addr["c1"])["change"]
    assert box["try"]["verdict"]["look"] == "pass" and box["badge"]["label"] == "Try passed"     # nobody asked yet
    rows = {r["label"]: [_text(c) for c in r["cells"]] for r in box["try"]["rows"]}
    assert rows["Key exchange"][:2] == ["Classical [measured]", "Hybrid (interim) [measured on the copy]"]
    assert rows["Key share, client to server"][1] == "1,216 bytes [measured on the copy]"
    assert rows["Key exchange"][2].startswith("Not tried: real nginx in the lab needs isolated mode")
    with pytest.raises(BadRequest):
        lab.ask_approval(flow.pid, key, ["somebody"])
    lab.ask_approval(flow.pid, key, ["you", "a"])
    assert _system(flow, flow.addr["c1"])["change"]["badge"]["label"] == "Waiting for approval"
    lab.approve_change(flow.pid, key, "you")
    with pytest.raises(Conflict, match="waiting for Demo reviewer A"):
        lab.apply_change(flow.pid, key)
    with pytest.raises(BadRequest):
        lab.approve_change(flow.pid, key, "b")                 # was not asked
    lab.approve_change(flow.pid, key, "a")
    assert _system(flow, flow.addr["c1"])["change"]["badge"]["label"] == "Ready to apply"


def test_apply_measures_again_closes_the_fix_and_roll_back_reopens_it(flow):
    lab, key, name = flow.lab, f"migration:server:{flow.addr['c1']}", flow.addr["c1"]
    lab.apply_change(flow.pid, key)
    lab.wait_until_changes_idle(flow.pid)
    system = _system(flow, name)
    assert [t["status"]["label"] for t in system["tracks"]] == ["Hybrid (interim)", "Classical"]
    assert system["change"]["applied"]["badge"]["label"] == "Applied · matches the try"
    assert system["change"]["badge"]["label"] == "In place (measured)"
    fix = next(f for f in lab.fixes_view(flow.pid)["fixes"] if (f.get("change_box") or {}).get("id") == key)
    assert fix["status"]["word"] == "In place (measured)" and fix["title"] == f"Turn on hybrid key exchange on {name}"
    assert {r["track"]: b["title"] for b in lab.migration_view(flow.pid)["roadmap"]["bands"] for r in b["rows"] if r["name"] == name} == \
        {"Key exchange": "Done for now", "Authentication": "Phase 2"}
    # the views, with a try, an Apply and the measurement after it, have exactly the shape the screens receive (phase 4c+)
    assert problems(lab.migration_view(flow.pid), models.MigrationView, "migration") == []
    assert problems(lab.fixes_view(flow.pid), models.FixesView, "fixes") == []
    with pytest.raises(Conflict, match="applied"):
        lab.apply_change(flow.pid, key)                        # not twice
    lab.rollback_change(flow.pid, key)
    lab.wait_until_changes_idle(flow.pid)
    system = _system(flow, name)
    assert system["tracks"][0]["status"]["label"] == "Classical"
    assert system["change"]["applied"]["badge"]["label"] == "Rolled back · measured as before"
    with pytest.raises(Conflict, match="Try again on a test copy first"):
        lab.apply_change(flow.pid, key)                        # the server changed since the try
    fix = next(f for f in lab.fixes_view(flow.pid)["fixes"] if (f.get("change_box") or {}).get("id") == key)
    assert fix["status"]["word"] == "Rolled back"
    assert problems(lab.migration_view(flow.pid), models.MigrationView, "migration") == []


def test_every_step_is_in_the_signed_evidence_and_no_key_is(flow, tmp_path):
    from evidence import trusted_key_from_data_dir, verify_bytes
    lab = flow.lab
    export = lab.export_evidence(flow.pid)
    _, raw, _ = lab.evidence_file(export["id"], "json")
    _, report, _ = lab.evidence_file(export["id"], "html")
    assert verify_bytes(raw, trusted_key_from_data_dir(lab.settings.data_dir)).ok
    changes = json.loads(raw)["evidence"]["changes"]
    entry = next(e for e in changes if e["change"]["system_key"] == f"server:{flow.addr['c1']}")
    assert entry["try"]["outcome"] == "passed" and entry["approval_request"]["approvals"] and entry["applies"][0]["accepted"]
    assert entry["after_apply"]["outcome"] == "matches" and entry["rollback"]["outcome"] == "as_before"
    # every round, not only the latest (review finding 2)
    assert [t["outcome"] for t in entry["rounds"]["tries"]] == ["passed"] and len(entry["rounds"]["approval_requests"]) == 1
    assert [(a["after_apply"], a["rollback"]["outcome"]) for a in entry["rounds"]["applies"]] == [("matches", "as_before")]
    assert any(run["copy"] == "a test copy with the change" for run in entry["runs"])
    page = report.decode()
    assert "6. Changes: tried, approved, applied, rolled back" in page and "<script" not in page
    blob = raw + report + lab.change_download(flow.pid, entry["change"]["key"])[1]
    assert b"PRIVATE KEY" not in blob


def test_the_records_only_accept_new_rows(flow):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    with flow.lab.db() as db:
        for table, column in (("change_tries", "change_key"), ("apply_requests", "change_key"), ("apply_approvals", "name"),
                              ("applies", "words"), ("rollbacks", "words")):
            assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() > 0, table
            for statement in (f"UPDATE {table} SET {column} = 'x'", f"DELETE FROM {table}"):
                with pytest.raises(DBAPIError, match="append-only"):
                    db.execute(text(statement))
                db.rollback()


@pytest.mark.slow
def test_an_applied_change_stays_in_force_after_the_app_restarts(tmp_path):
    ports = _ports()
    settings = dict(migration_ports=ports, lab_nginx_port=free_port())
    lab = make_lab(tmp_path, **settings)
    data_dir, demo_port = lab.settings.data_dir, lab.settings.demo_tls_port
    key = f"migration:server:localhost:{ports[1]}"
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        lab.try_change(pid, key)
        lab.wait_until_changes_idle(pid)
        lab.ask_approval(pid, key, ["you"])
        lab.approve_change(pid, key, "you")
        lab.apply_change(pid, key)
        lab.wait_until_changes_idle(pid)
    finally:
        lab.stop()
    lab = make_lab(tmp_path, data_dir=data_dir, demo_tls_port=demo_port, **settings)
    try:
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        assert _first(lab, pid, f"localhost:{ports[1]}")["tracks"][0]["status"]["label"] == "Hybrid (interim)"
        assert lab.migration_servers.settings[ports[1]]["groups"].startswith("X25519MLKEM768")
    finally:
        lab.stop()


def _first(lab, pid, name):
    return next(s for s in lab.migration_view(pid)["systems"] if s["name"] == name)


def test_a_server_that_is_not_ours_gets_a_change_to_download_and_no_apply(tmp_path):
    cert, key, _ = pqtls.test_certificate("ecdsa-p256", "not-ours")
    other = pqtls.Server(groups="X25519:P-256", certificate_pem=cert, key_pem=key)
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port())
    try:
        imp = lab.import_file("other.csv", csv_bytes(f"localhost:{other.port},tls,post_quantum,classical"))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        box = lab.migration_view(pid)["systems"][0]["change"]
        buttons = {b["action"]: b for b in box["buttons"]}
        assert buttons["try"]["enabled"] is False and "connector" in buttons["try"]["reason"]
        assert buttons["apply"]["enabled"] is False and "connector" in buttons["apply"]["reason"]
        assert buttons["download"]["enabled"] is True and box["badge"]["label"] == "Ready to download" and box["steps"] == []
        # built from what was measured, and saying so (review finding 3)
        table = next(sec for sec in box["sections"] if sec["kind"] == "table")
        now = {_text(r[0]): _text(r[1]) for r in table["rows"]}
        assert now["Key-exchange groups"].startswith("X25519 (the one it chose, measured;") and now["Certificate"] == "ECDSA P-256 (measured)"
        assert "built from what it measured" in json.dumps(box)
        with pytest.raises(Conflict):
            lab.try_change(pid, box["id"])
        assert lab.change_download(pid, box["id"])[0].endswith(".txt")
    finally:
        other.close()
        lab.stop()


@pytest.mark.slow
def test_the_acme_pay_tls_fix_is_tried_applied_and_rolled_back(tmp_path):
    from conftest import play_back_speed
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port(), speed_rounds=4, speed_repeats=2)
    play_back_speed(lab)
    try:
        imp = lab.import_demo()
        lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.run_all(pid)
        lab.wait_until_idle(pid, 300)
        lab.start_retest(pid, "1.4.3")          # as in the demo walk: the retest first, then the server fix
        lab.wait_until_idle(pid, 300)
        fix = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("fix-tls"))
        key = fix["change_box"]["id"]
        assert key == f"tls:server:{lab.settings.demo_address}" and fix["change_box"]["badge"]["label"] == "Ready to try"
        lines = {r["place"]: r["code"] for sec in fix["change_box"]["sections"] if sec["kind"] == "lines" for r in sec["rows"]}
        assert lines == {"nginx": "ssl_protocols TLSv1.3;", "Apache": "SSLProtocol -all +TLSv1.3",          # TLS 1.3 only (finding 4)
                         "Your own application": "SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);"}
        table = next(sec for sec in fix["change_box"]["sections"] if sec["kind"] == "table")
        assert [_text(c) for c in table["rows"][0]] == ["Key-exchange groups", "P-256", "P-256 (no change)"]
        lab.try_change(pid, key)
        lab.wait_until_changes_idle(pid)
        box = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("fix-tls"))["change_box"]
        rows = {r["label"]: [_text(c) for c in r["cells"]] for r in box["try"]["rows"]}
        assert rows["Server protocol check"][:2] == ["Failed [measured]", "Passed [measured on the copy]"]      # S1
        lab.ask_approval(pid, key, ["you"])
        lab.approve_change(pid, key, "you")
        lab.apply_change(pid, key)
        lab.wait_until_changes_idle(pid)
        assert lab.verify(imp["id"])["results"][0]["result"] == "True"                                          # S2
        row = next(r for r in lab.lab_view(pid)["rows"] if r["kind"] == "tls_versions")
        assert (row["result"]["label"], row["after"]["label"]) == ("Failed", "Passed")   # S3, in the newest column: before and after in order
        fix = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("fix-tls"))
        assert fix["status"]["word"] == "In place (measured)"
        # The demo file imported again without a Roll back: Import says the change is still in force, and the new
        # file's Fixes step has an entry with Roll back, so it can always be reached (review finding 1).
        again = lab.import_demo()
        assert any(n.startswith(f"Demo data: a change this app applied to {lab.settings.demo_address} is still in force (TLS 1.3")
                   for n in again["notices"])
        lab.confirm_address(again["id"], again["addresses"][0]["address"], True)
        pid2 = lab.ensure_plan(again["id"])["id"]
        entry = next(f for f in lab.fixes_view(pid2)["fixes"] if f["id"] == "fix-tls-versions-applied")
        assert entry["title"] == f"TLS 1.3 only is applied to {lab.settings.demo_address}"
        assert {b["action"]: b["enabled"] for b in entry["change_box"]["buttons"]}["rollback"] is True
        lab.rollback_change(pid2, key)
        lab.wait_until_changes_idle(pid2)
        assert lab.demo.versions == ("TLS 1.2", "TLS 1.3")
        assert not any(f["id"] == "fix-tls-versions-applied" for f in lab.fixes_view(pid2)["fixes"])
        # both files' signed evidence hold the Apply and its Roll back, each saying which import made the Apply
        for plan_id, own in ((pid, True), (pid2, False)):
            _, raw, _ = lab.evidence_file(lab.export_evidence(plan_id)["id"], "json")
            (entry,) = [e for e in json.loads(raw)["evidence"]["changes"] if e["change"]["key"] == key]
            (applied,) = entry["rounds"]["applies"]
            assert applied["from_this_import"] is own and applied["rollback"]["accepted"] is True
            assert applied["rollback"]["outcome"] == "as_before" and applied["after_apply"] == "matches"
        assert lab.verify(imp["id"])["results"][0]["result"] == "False"
        # the first file's records still read right: the Apply it made was rolled back
        assert next(f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("fix-tls"))["change_box"]["applied"]["badge"]["label"] \
            == "Rolled back · measured as before"
    finally:
        lab.stop()


def test_the_tls_fix_on_a_server_that_is_not_ours_stays_text_only(tls_server, tmp_path):
    """SPEC 7c: only our own demo server gets the change box. Anyone else's server keeps the text-only suggestion."""
    port = tls_server("demo")          # a throwaway server that accepts TLS 1.2 and 1.3, like the demo server
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port())
    try:
        imp = lab.import_file("theirs.csv", csv_bytes(f"127.0.0.1:{port},tls,protocol_versions,TLS1.3"))
        lab.confirm_address(imp["id"], f"127.0.0.1:{port}", True)
        plan = lab.ensure_plan(imp["id"])
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 120)
        (fix,) = [f for f in lab.fixes_view(plan["id"])["fixes"] if f["id"].startswith("fix-tls")]
        assert fix["change_box"] is None and fix["status"]["word"] == "Text only"
        assert fix["approvers"]["text"] == "Your own server team, outside this app. The app never changes your server."
        row = next(r for r in lab.lab_view(plan["id"])["rows"] if r["kind"] == "tls_versions")
        assert (row["result"]["fix_line"]["lead"], row["result"]["fix_line"]["rest"]) == ("Text-only suggestion:", "a server setting")
        with pytest.raises((Conflict, NotFound)):
            lab.try_change(plan["id"], f"tls:server:127.0.0.1:{port}")
    finally:
        lab.stop()


def test_without_the_post_quantum_engine_nothing_can_be_tried_or_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(pqtls, "available", lambda: (False, "no ML-KEM here"))
    ports = _ports()
    lab = make_lab(tmp_path, migration_ports=ports, lab_nginx_port=free_port())
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        servers = [s for s in lab.migration_view(pid)["systems"] if s["kind_label"] == "Server"]
        assert all(s["change"] is None and s["tracks"][0]["status"]["code"] == "couldnt_check" for s in servers)
    finally:
        lab.stop()


def test_the_lab_nginx_needs_isolated_mode_and_says_so(tmp_path):
    from app.config import DEMO_DIR
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port())
    try:
        data = (DEMO_DIR / "lab-nginx.csv").read_text().replace("localhost:8461,", f"localhost:{lab.settings.lab_nginx_port},").encode()
        imp = lab.import_file("lab-nginx.csv", data)
        assert imp["notices"][0].startswith("Real nginx in the lab needs isolated mode (Docker).") and imp["is_demo"] is True
        assert lab.lab_nginx_server.running is False
    finally:
        lab.stop()


def test_real_nginx_takes_the_change_on_apply_and_gives_it_back_on_roll_back(docker_ready, tmp_path):
    from app.config import DEMO_DIR
    from app.servers import lab_nginx
    if not lab_nginx.ready(docker_ready)[0]:
        pytest.skip("Skipped: the pinned nginx lab image is not prepared (run: cd backend && .venv/bin/python -m app.prepare).")
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port(), force_mode="isolated")
    try:
        data = (DEMO_DIR / "lab-nginx.csv").read_text().replace("localhost:8461,", f"localhost:{lab.settings.lab_nginx_port},").encode()
        imp = lab.import_file("lab-nginx.csv", data)
        assert imp["notices"][0].startswith("Lab data: started the lab nginx")
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        key = lab.migration_view(pid)["systems"][0]["change"]["id"]
        lab.try_change(pid, key)
        lab.wait_until_changes_idle(pid)
        lab.ask_approval(pid, key, ["you"])
        lab.approve_change(pid, key, "you")
        lab.apply_change(pid, key)
        lab.wait_until_changes_idle(pid)
        system = lab.migration_view(pid)["systems"][0]
        assert system["tracks"][0]["status"]["label"] == "Hybrid (interim)" and system["change"]["applied"]["badge"]["label"] == "Applied · matches the try"
        lab.rollback_change(pid, key)
        lab.wait_until_changes_idle(pid)
        assert lab.migration_view(pid)["systems"][0]["tracks"][0]["status"]["label"] == "Classical"
        refused, words = lab.lab_nginx_server.apply({"groups": "NOSUCHGROUP", "versions": ["TLS 1.3"], "certificate": "ecdsa-p256"})
        assert refused is False and words
        lab.measure_migration(pid)
        lab.wait_until_measured(pid)
        assert lab.migration_view(pid)["systems"][0]["tracks"][0]["status"]["label"] == "Classical"   # the earlier settings stayed
    finally:
        lab.stop()


def test_a_post_quantum_claim_suggests_the_readiness_test(tmp_path):
    lab = make_lab(tmp_path, migration_ports=_ports(), lab_nginx_port=free_port())
    try:
        imp = lab.import_file("pq.csv", csv_bytes("localhost:1,tls,post_quantum,hybrid"))
        plan = lab.ensure_plan(imp["id"])
        assert [t["kind"] for t in plan["tests"]] == ["pq_readiness"]
        assert not any("post-quantum claim" in line for line in (plan["not_tested"] or {}).get("items", []))
    finally:
        lab.stop()


@pytest.mark.parametrize("method, path", [("POST", "/api/plans/1/changes/try"), ("POST", "/api/plans/1/changes/ask-approval"),
                                          ("POST", "/api/plans/1/changes/approve"), ("POST", "/api/plans/1/changes/apply"),
                                          ("POST", "/api/plans/1/changes/rollback"), ("GET", "/api/plans/1/changes/download?change=x")])
def test_the_change_routes_need_a_login(anon_client, method, path):
    response = anon_client.request(method, path, json={"change": "x", "reviewers": ["you"], "reviewer": "you"})
    assert response.status_code == 401 and response.json()["error"]["message"] == "Please log in."


def test_the_change_routes_refuse_what_they_must(client):
    assert client.post("/api/plans/999/changes/try", json={"change": "x"}).status_code == 404
    assert client.post("/api/plans/999/changes/ask-approval", json={"change": "x", "reviewers": ["m" * 20]}).status_code == 422
    assert client.get("/api/plans/999/changes/download", params={"change": "x"}).status_code == 404
