"""Phase 3a-fixes: every target in the file is tested, with plain words on top and "Also noticed" notes.

The multi-target demo file names the Acme server, three local test servers and two signing programs
(acme-sign 1.4.2, one of ours, and acme-sign 9.9, which is not). Nothing here touches the internet: every
server is on this computer, on a spare port."""
import socket

import pytest

from app import extra_servers, research
from app.compare import COULDNT, FALSE, TRUE
from app.reviewer import RuleReviewer
from conftest import csv_bytes, free_port, make_lab, play_back_speed

ONLY_OURS = "This test couldn't run: only our own demo components can run in this version. So there is no result either way."
NOTE = "This server also accepts TLS 1.0 and TLS 1.1, both retired in 2021. The file didn't ask about this, so it doesn't change the result."


def _ports():
    return (free_port(), free_port(), free_port())


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """One lab, the multi-target file imported, its addresses confirmed, verified, planned and run once."""
    ports = _ports()
    lab = make_lab(tmp_path_factory.mktemp("multi"), extra_ports=ports)
    play_back_speed(lab)
    try:
        data = extra_servers.file_for(lab.settings.demo_tls_port, ports)
        imp = lab.import_file("multi-target-demo.csv", data)
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        verify = lab.verify(imp["id"])
        plan = lab.ensure_plan(imp["id"])
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 600)
        demo = f"localhost:{lab.settings.demo_tls_port}"
        addr = [f"localhost:{p}" for p in ports]
        yield type("Flow", (), dict(lab=lab, imp=imp, verify=verify, plan=plan, demo=demo, addr=addr, ports=ports))
    finally:
        lab.stop()


def _row(view, group, kind):
    return next(r for r in view["rows"] if r["group"] == group and r["kind"] == kind)


# ------------------------------------------------------------------ the engine


def test_every_server_and_every_program_gets_the_tests_that_apply():
    claims = [
        {"ref": "a", "location": "localhost:1", "location_kind": "server", "kind": "protocol_versions", "claimed_value": "TLS 1.3",
         "detail": {"versions": ["TLS 1.3"]}},
        {"ref": "b", "location": "localhost:2", "location_kind": "server", "kind": "certificate", "claimed_value": "ECDSA P-256",
         "detail": {"algorithm": "ECDSA P-256"}},
        {"ref": "c", "location": "acme-sign 1.4.2", "location_kind": "software", "kind": "signature_algorithm",
         "claimed_value": "ECDSA P-256", "detail": {"component": "acme-sign", "version": "1.4.2", "algorithm": "ECDSA P-256"}},
        {"ref": "d", "location": "acme-sign 9.9", "location_kind": "software", "kind": "signature_algorithm",
         "claimed_value": "ECDSA P-256", "detail": {"component": "acme-sign", "version": "9.9", "algorithm": "ECDSA P-256"}},
    ]
    plan = research.RuleEngine().propose_tests(claims)
    got = [(t["kind"], research.target_key(t["kind"], t["target"])) for t in plan["tests"]]
    assert got == [("tls_versions", "localhost:1"), ("certificate", "localhost:2"),
                   ("official_vectors", "c"), ("bad_signatures", "c"), ("speed_size", "c"),
                   ("official_vectors", "d"), ("bad_signatures", "d"), ("speed_size", "d")]
    # Two versions of the same program are two targets: their locked tests differ only by the claim they are for.
    assert len({research.RuleEngine().propose_tests(claims)["tests"][i]["target"]["claim"] for i in (2, 5)}) == 2
    assert [(s["kind"], s["target"]) for s in plan["not_suggested"]] == [("certificate", "localhost:1"), ("tls_versions", "localhost:2")]
    assert all("this server" in s["reason"] for s in plan["not_suggested"])


def test_the_two_signing_tests_are_titled_so_the_difference_is_plain():
    assert research.TITLES["official_vectors"] == "Independent exam (Wycheproof)"
    assert research.TITLES["bad_signatures"] == "Attacker tricks (our short list)"
    claims = [{"ref": "c", "location": "acme-sign 1.4.2", "location_kind": "software", "kind": "signature_algorithm",
               "claimed_value": "ECDSA P-256", "detail": {"component": "acme-sign", "version": "1.4.2", "algorithm": "ECDSA P-256"}}]
    tests = {t["kind"]: t for t in research.RuleEngine().propose_tests(claims)["tests"]}
    assert "outside exam" in tests["official_vectors"]["card"]["why"] and "484" in tests["official_vectors"]["card"]["why"]
    assert "Google" in tests["official_vectors"]["card"]["why"]
    assert "our own short list" in tests["bad_signatures"]["card"]["why"] and "14" in tests["bad_signatures"]["card"]["why"]


# ------------------------------------------------------------------ the test servers start only for that file


def test_the_test_servers_start_only_when_the_multi_target_file_is_imported(tmp_path):
    ports = _ports()
    lab = make_lab(tmp_path, extra_ports=ports)
    try:
        lab.import_demo()
        other = lab.import_file("mine.csv", csv_bytes(f"localhost:{ports[0]},tls,protocol_versions,TLS1.3"))
        assert lab.extra.running == [] and "notices" not in other  # a file of yours naming the same port starts nothing
        lab.verify(other["id"])
        assert lab.extra.running == []
        imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
        assert lab.extra.running == sorted(ports)
        assert imp["notices"] == [f"Demo data: started the three demo test servers for this file on this computer (ports {', '.join(map(str, ports))})."]
    finally:
        lab.stop()
    assert lab.extra.running == []


def test_a_taken_port_is_said_and_the_app_carries_on(tmp_path):
    ports = _ports()
    busy = socket.create_server(("127.0.0.1", ports[1]))
    lab = make_lab(tmp_path, extra_ports=ports)
    try:
        imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
        assert imp["claims"] and lab.extra.running == sorted([ports[0], ports[2]])
        assert imp["notices"] == [f"Port {ports[1]} on this computer is already used by another program, so the demo test server for "
                                  f"localhost:{ports[1]} could not start. Its claims will show Couldn't check."]
    finally:
        lab.stop()
        busy.close()


def test_after_a_restart_verify_starts_them_again_for_that_import(tmp_path):
    ports = _ports()
    lab = make_lab(tmp_path, extra_ports=ports)
    imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
    lab.stop()
    again = make_lab(tmp_path, extra_ports=ports, demo_tls_port=lab.settings.demo_tls_port)
    try:
        assert again.extra.running == []
        again.verify(imp["id"])
        assert again.extra.running == sorted(ports)
    finally:
        again.stop()


# ------------------------------------------------------------------ Verify: plain sentences and Also noticed


def test_verify_gives_every_row_one_plain_sentence_and_the_also_noticed_note(flow):
    rows = {r["claim"]["text"]: r for r in flow.verify["results"]}
    a, b, c = flow.addr
    assert {k: (r["result"], r["summary"], r["also_noticed"]) for k, r in rows.items()} == {
        f"{flow.demo} accepts TLS 1.3 only": (FALSE, "The server accepts TLS 1.2, so ‘TLS 1.3 only’ is not true.", []),
        f"{flow.demo} certificate is ECDSA P-256": (TRUE, "The server's ID card (its certificate) uses ECDSA P-256, which matches the claim.", []),
        f"{a} accepts TLS 1.3 only": (TRUE, "The server accepts TLS 1.3 and refused every other TLS version we tried, so ‘TLS 1.3 only’ is true.", []),
        f"{b} certificate is ECDSA P-256": (TRUE, "The server's ID card (its certificate) uses ECDSA P-256, which matches the claim.", [NOTE]),
        f"{c} certificate is RSA 2048": (FALSE, "The server's ID card (its certificate) uses RSA with a 1024-bit key, not RSA 2048 as the file claims.", []),
        "signing component is acme-sign 1.4.2 implementing ECDSA P-256":
            (TRUE, "acme-sign 1.4.2 says it uses ECDSA P-256, and a normal sign-and-check round trip worked, which matches the claim.", []),
        "signing component is acme-sign 9.9 implementing ECDSA P-256":
            (COULDNT, "We couldn't run acme-sign 9.9: only our own demo components can run in this version, so there is no answer either way.", []),
    }
    assert rows[f"{flow.demo} accepts TLS 1.3 only"]["found"].startswith("Accepts TLS 1.3 and TLS 1.2")  # the technical text stays


def test_also_noticed_never_changes_the_result(tls_server, tmp_path):
    """The same server that accepts TLS 1.0 and 1.1, with a matching and a mismatching claim: the note shows on both
    rows, and True and False come out exactly as they would without it."""
    port = tls_server("legacy")
    lab = make_lab(tmp_path)
    try:
        imp = lab.import_file("x.csv", csv_bytes(f"127.0.0.1:{port},tls,certificate,ECDSA P-256", f"127.0.0.1:{port},tls,certificate,RSA 2048"))
        lab.confirm_address(imp["id"], f"127.0.0.1:{port}", True)
        rows = lab.verify(imp["id"])["results"]
    finally:
        lab.stop()
    assert [r["result"] for r in rows] == [TRUE, FALSE]
    assert all(r["also_noticed"] == [NOTE] for r in rows)


def test_the_certificate_review_ignores_the_versions_it_also_saw(flow):
    """The reviewer decides from the certificate alone: taking the TLS versions out of the raw record changes nothing."""
    view = flow.lab.lab_view(flow.plan["id"])
    run_id = _row(view, f"server:{flow.addr[1]}", "certificate")["result"]["run_id"]
    from app.db import TestRunRow, TestSpecRow
    from app.testlab import read_spec, run_record
    with flow.lab.db() as db:
        run = db.get(TestRunRow, run_id)
        record = run_record(run)
        spec, _ = read_spec(db.get(TestSpecRow, run.spec_hash))
    assert "TLS 1.0" in record["raw"]["subject"]["versions"]
    with_versions = RuleReviewer().review({"spec": spec, "spec_hash": run.spec_hash, "proposed_by": "x", "run": record})
    record["raw"]["subject"].pop("versions")
    without = RuleReviewer().review({"spec": spec, "spec_hash": run.spec_hash, "proposed_by": "x", "run": record})
    assert with_versions["verdict"] == without["verdict"] and with_versions["verdict"]["code"] == "passed"


# ------------------------------------------------------------------ Tests and Evidence Lab


def test_the_tests_screen_groups_by_target_and_says_what_is_not_tested(flow):
    plan = flow.lab.plan_view(flow.plan["id"])
    a, b, c = flow.addr
    assert plan["grouped"] is True
    assert [(g["heading"], g["note"]) for g in plan["groups"]] == [
        (f"Server: {flow.demo}", None), (f"Server: {a}", None), (f"Server: {b}", None), (f"Server: {c}", None),
        ("Signing program: acme-sign 1.4.2", None),
        ("Signing program: acme-sign 9.9", "Its tests can't run: only our own demo components can run in this version.")]
    assert plan["not_tested"] == {"title": "Not tested, and why", "items": [
        f"{a}: no Certificate strength test. The file makes no claim about this server's certificate.",
        f"{b}: no Old TLS versions test. The file makes no claim about which TLS versions this server accepts.",
        f"{c}: no Old TLS versions test. The file makes no claim about which TLS versions this server accepts.",
        "acme-sign 9.9: its tests can't run. Only our own demo components can run in this version."]}
    keys = [t["group"] for t in plan["tests"]]
    assert keys == sorted(keys, key=[g["key"] for g in plan["groups"]].index)  # sent group by group
    assert len(plan["tests"]) == 11
    assert plan["subject"][:2] == [{"t": "text", "v": "Testing: "}, {"t": "text", "v": "four servers and two signing programs"}]


def test_every_result_has_its_plain_line_and_nothing_is_skipped(flow):
    view = flow.lab.lab_view(flow.plan["id"])
    a, b, c = flow.addr
    assert view["grouped"] is True and view["not_tested"]["items"]
    assert all(r["result"] is not None for r in view["rows"])  # all eleven ran
    assert _row(view, f"server:{flow.demo}", "tls_versions")["result"]["plain"] == "The server accepts TLS 1.2, so ‘TLS 1.3 only’ is not true."
    assert _row(view, f"server:{a}", "tls_versions")["result"]["label"] == "Passed"
    cert_b = _row(view, f"server:{b}", "certificate")["result"]
    assert cert_b["label"] == "Passed" and cert_b["also_noticed"] == [NOTE]
    cert_c = _row(view, f"server:{c}", "certificate")["result"]
    assert cert_c["label"] == "Failed" and cert_c["plain"] == ("The server's ID card (its certificate) uses RSA with a 1024-bit key: "
                                                               "not RSA 2048 as claimed, and below NIST's minimum of 2048 bits.")
    ours = [r for r in view["rows"] if r["group"] == "software:line-7"]
    theirs = [r for r in view["rows"] if r["group"] == "software:line-8"]
    assert [r["result"]["label"] for r in ours] == ["Failed", "Failed", "Measured"]
    assert [r["result"]["component"] for r in ours] == ["acme-sign 1.4.2"] * 3
    assert all(r["result"]["code"] == "couldnt_run" and r["result"]["plain"] == ONLY_OURS for r in theirs)
    for row in view["rows"]:
        text = row["result"]["plain"].lower()
        assert text and "secure" not in text and "score" not in text


def test_each_failing_server_has_its_own_text_fix_and_the_code_fix_is_for_our_program(flow):
    fixes = flow.lab.fixes_view(flow.plan["id"])["fixes"]
    assert [(f["kind"], f["list_source"]) for f in fixes] == [
        ("code", "Came from 2 failed tests: Independent exam (Wycheproof), Attacker tricks (our short list)"),
        ("text", f"Came from 1 failed test: Old TLS versions on {flow.demo}"),
        ("text", f"Came from 1 failed test: Certificate strength on {flow.addr[2]}")]


def test_add_test_adds_it_to_every_server(flow):
    before = flow.lab.plan_view(flow.plan["id"])
    after = flow.lab.add_test(flow.plan["id"], "pq_readiness")
    added = [t["group"] for t in after["tests"] if t["kind"] == "pq_readiness"]
    assert added == [f"server:{a}" for a in [flow.demo, *flow.addr]]
    assert "pq_readiness" not in [c["catalog_id"] for c in after["catalog"]]
    pq = [t["id"] for t in after["tests"] if t["kind"] == "pq_readiness"]
    flow.lab.remove_test(flow.plan["id"], pq[1])
    back = flow.lab.plan_view(flow.plan["id"])
    assert "pq_readiness" in [c["catalog_id"] for c in back["catalog"]]  # one server is missing it again
    again = flow.lab.add_test(flow.plan["id"], "pq_readiness")
    assert sorted(t["id"] for t in again["tests"] if t["kind"] == "pq_readiness") == sorted(pq)  # the same test came back
    for item in pq:
        flow.lab.remove_test(flow.plan["id"], item)
    assert len(flow.lab.plan_view(flow.plan["id"])["tests"]) == len(before["tests"])


def test_the_proof_and_the_retest_change_only_our_program(flow):
    """The code fix's proof reruns all eleven tests: acme-sign 9.9 couldn't run before and after, which counts as
    unchanged, so it does not stop the change being offered. A retest then runs 1.4.3 for our program only."""
    lab, plan_id = flow.lab, flow.plan["id"]
    lab.connect_code(plan_id)
    lab.wait_until_idle(plan_id, 900)
    code = next(f for f in lab.fix_states(plan_id) if f["kind"] == "code")
    targets = {t["item_id"]: t["target"] for t in code["proof"]["tests"]}
    assert sorted(targets.values()).count("other_program") == 3 and sorted(targets.values()).count("server") == 5
    assert code["proof"]["state"] == "passed" and code["status"] == "ready", code["proof"]["review"]
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 900)
    view = lab.lab_view(plan_id)
    assert [r["after"]["component"] for r in view["rows"] if r["group"] == "software:line-7"] == ["acme-sign 1.4.3"] * 3
    assert [r["after"]["label"] for r in view["rows"] if r["group"] == "software:line-7"][:2] == ["Passed", "Passed"]
    assert all(r["after"]["code"] == "couldnt_run" for r in view["rows"] if r["group"] == "software:line-8")
    assert any(part.get("v") == ". Every other server and program was tested again as it is" for part in view["subline"])


def test_the_evidence_file_carries_the_plain_lines_and_notes(flow):
    import json

    from app.evidence_export import build_evidence
    text = json.dumps(build_evidence(flow.lab, flow.plan["id"]), ensure_ascii=False)
    assert NOTE in text and "\u2018TLS 1.3 only\u2019 is not true" in text
    assert '"plain": "acme-sign 1.4.2 got 3 of the 484 exam cases wrong' in text


# ------------------------------------------------------------------ review findings (phase 3a-fixes review)


def test_a_second_demo_program_is_run_again_as_it_is_on_retest_and_proof(tmp_path):
    """A file naming acme-sign 1.4.2 and acme-sign 1.4.3, both ours. The plan's own program is 1.4.2. On a retest
    and in the proof, 1.4.3's tests run again as they are: its speed test is measured like a first run (not
    "Couldn't run"), it is recorded as running our bundled file (never the change's code), and it does not stop
    the code fix being offered."""
    lab = make_lab(tmp_path)
    play_back_speed(lab)
    try:
        imp = lab.import_file("two.csv", csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
                                                   "acme-sign 1.4.3,software,signature_algorithm,ECDSA P-256"))
        plan = lab.ensure_plan(imp["id"])
        assert plan["grouped"] is True and len(plan["tests"]) == 6
        lab.run_all(plan["id"])
        lab.wait_until_idle(plan["id"], 600)
        lab.connect_code(plan["id"])
        lab.wait_until_idle(plan["id"], 600)
        code = next(f for f in lab.fix_states(plan["id"]) if f["kind"] == "code")
        assert code["status"] == "ready", code["proof"]["review"]
        from app.db import RunCodeRow, TestRunRow
        with lab.db() as db:
            proof_runs = db.query(TestRunRow).filter(TestRunRow.phase == "proof", TestRunRow.component_version == "1.4.3").all()
            sources = {db.query(RunCodeRow).filter(RunCodeRow.run_id == r.id).one().source for r in proof_runs}
        assert sources == {"repository", "bundled"}  # 1.4.2's tests ran the change; the other program its bundled file
        lab.start_retest(plan["id"], "1.4.3")
        lab.wait_until_idle(plan["id"], 600)
        view = lab.lab_view(plan["id"])
        other = [r for r in view["rows"] if r["group"] == "software:line-3"]
        assert [r["after"]["label"] for r in other] == ["Passed", "Passed", "Measured"]
        assert all(r["after"]["component"] == "acme-sign 1.4.3" for r in other)
    finally:
        lab.stop()


def test_no_also_noticed_when_the_file_claims_that_servers_tls_versions(tls_server, tmp_path):
    port = tls_server("legacy")
    lab = make_lab(tmp_path)
    try:
        imp = lab.import_file("x.csv", csv_bytes(f"127.0.0.1:{port},tls,protocol_versions,TLS1.2;TLS1.3",
                                                 f"127.0.0.1:{port},tls,certificate,ECDSA P-256"))
        lab.confirm_address(imp["id"], f"127.0.0.1:{port}", True)
        rows = lab.verify(imp["id"])["results"]
        assert rows[0]["result"] == FALSE and rows[1]["result"] == TRUE
        assert rows[1]["also_noticed"] == []  # the file did ask: the TLS row already says it
        plan = lab.ensure_plan(imp["id"])
        cert = next(t["id"] for t in plan["tests"] if t["kind"] == "certificate")
        lab.run_test(plan["id"], cert)
        lab.wait_until_idle(plan["id"], 300)
        result = next(r for r in lab.lab_view(plan["id"])["rows"] if r["kind"] == "certificate")["result"]
        assert result["label"] == "Passed" and result["also_noticed"] == []
    finally:
        lab.stop()


def test_another_program_on_a_test_server_port_is_not_reported_on(tmp_path, test_cert):
    """A TLS program of someone else holds 8445's port: the import says so, and Verify gives Couldn't check for
    that address instead of reporting on the other program as if it were our test server."""
    from app.demo_server import TlsServer, make_server_context
    ports = _ports()
    other = TlsServer(make_server_context(*test_cert, ciphers="ALL:@SECLEVEL=0", minimum=__import__("ssl").TLSVersion.TLSv1_2), ports[1])
    lab = make_lab(tmp_path, extra_ports=ports)
    try:
        imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
        assert "already used by another program" in imp["notices"][0]
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        rows = {r["claim"]["location"]: r for r in lab.verify(imp["id"])["results"]}
        taken = rows[f"localhost:{ports[1]}"]
        assert taken["result"] == COULDNT and "already used by another program" in taken["reason"]
        assert rows[f"localhost:{ports[0]}"]["result"] == TRUE  # ours, and checked to be ours
        plan = lab.ensure_plan(imp["id"])
        item = next(t["id"] for t in plan["tests"] if t["group"] == f"server:localhost:{ports[1]}")
        lab.run_test(plan["id"], item)
        lab.wait_until_idle(plan["id"], 300)
        row = next(r for r in lab.lab_view(plan["id"])["rows"] if r["item_id"] == item)
        assert row["result"]["label"] == "Couldn't run (the server did not answer)"
    finally:
        lab.stop()
        other.close()


def test_fix_ids_come_from_the_plan_not_from_which_tests_have_run(tmp_path):
    ports = _ports()
    lab = make_lab(tmp_path, extra_ports=ports)
    try:
        imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        plan = lab.ensure_plan(imp["id"])
        demo_tls = next(t["id"] for t in plan["tests"] if t["kind"] == "tls_versions")
        lab.run_test(plan["id"], demo_tls)
        lab.wait_until_idle(plan["id"], 300)
        assert [f["id"] for f in lab.fix_states(plan["id"])] == [f"fix-tls-versions-{demo_tls}"]
    finally:
        lab.stop()


def test_a_plan_from_before_every_target_was_tested_says_what_it_lacks(tmp_path):
    """Simulate a plan made by the earlier version: the second program's tests are not in it. They are listed under
    "Not tested, and why", never skipped silently."""
    ports = _ports()
    lab = make_lab(tmp_path, extra_ports=ports)
    try:
        imp = lab.import_file("multi-target-demo.csv", extra_servers.file_for(lab.settings.demo_tls_port, ports))
        plan = lab.ensure_plan(imp["id"])
        from app.db import PlanItemRow
        with lab.db() as db:
            for t in plan["tests"]:
                if t["group"] == "software:line-8":
                    db.delete(db.get(PlanItemRow, t["id"]))
            db.commit()
        items = lab.plan_view(plan["id"])["not_tested"]["items"]
        assert ("acme-sign 9.9: no Independent exam (Wycheproof) test. This test plan was made by an earlier version that "
                "tested only the first server and program. Import the file again to test it.") in items
    finally:
        lab.stop()
