"""An address that is not confirmed right now is never contacted by a test, at run time or at retest time."""

from app.db import TestRunRow
from conftest import csv_bytes, result_of, upload

NOT_CONFIRMED = "Couldn't run (address not confirmed)"
NETWORK = ("tls_versions", "certificate", "pq_readiness")


def plan_for(client, host, port):
    data = csv_bytes(f"{host}:{port},tls,protocol_versions,TLS1.3", f"{host}:{port},tls,certificate,ECDSA P-256",
                     "acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256")
    imp = upload(client, "claims.csv", data).json()
    lab = client.app.state.lab
    plan = lab.ensure_plan(imp["id"])
    for kind in ("official_vectors", "speed_size"):  # not needed here; keeps the test quick
        lab.remove_test(plan["id"], next(t["id"] for t in plan["tests"] if t["kind"] == kind))
    lab.add_test(plan["id"], "pq_readiness")
    return lab, imp, plan["id"]


def labels(view, which="result"):
    return {k: result_of(view, k, which)["label"] for k in NETWORK}


def test_unconfirmed_address_is_never_contacted_at_run_time(client, listener):
    lab, imp, pid = plan_for(client, "127.0.0.1", listener.port)
    lab.run_all(pid)
    lab.wait_until_idle(pid, 60)
    view = lab.lab_view(pid)
    assert labels(view) == dict.fromkeys(NETWORK, NOT_CONFIRMED)
    assert listener.connections() == 0
    assert result_of(view, "bad_signatures")["label"] == "Failed"  # tests that need no network still run
    for kind in NETWORK:
        r = result_of(view, kind)
        assert r["control"]["line"] == "Control: not run, because the test couldn't run." and r["suggested_fix"] is None
        assert "No connection was attempted" in r["evidence"][0]["text"]
    with lab.db() as db:
        for run in db.query(TestRunRow).all():
            if "problem" in run.raw:
                assert run.raw["problem"]["code"] == "address_not_confirmed" and "control" not in run.raw


def test_unticking_between_run_and_retest_blocks_the_retest(client, listener):
    lab, imp, pid = plan_for(client, "127.0.0.1", listener.port)
    address = imp["addresses"][0]["address"]
    lab.confirm_address(imp["id"], address, True)
    lab.run_all(pid)
    lab.wait_until_idle(pid, 90)
    assert listener.connections() > 0  # confirmed: it was contacted (it does not speak TLS, so there is no answer to judge)
    first = labels(lab.lab_view(pid))
    assert first["tls_versions"] == first["certificate"] == "Couldn't run (the server did not answer)"
    lab.confirm_address(imp["id"], address, False)
    lab.start_retest(pid, "1.4.3")
    lab.wait_until_idle(pid, 90)
    view = lab.lab_view(pid)
    assert labels(view, "after") == dict.fromkeys(NETWORK, NOT_CONFIRMED)
    assert listener.connections() == 0
    assert result_of(view, "bad_signatures", "after")["label"] == "Passed"


def test_a_name_that_now_points_elsewhere_is_blocked(client, listener):
    lab = client.app.state.lab
    lab.resolver = lambda host: ["127.0.0.1"]
    lab, imp, pid = plan_for(client, "shop.example.test", listener.port)
    lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
    lab.resolver = lambda host: ["127.0.0.2"]  # after the tick, the name moves
    lab.run_all(pid)
    lab.wait_until_idle(pid, 60)
    view = lab.lab_view(pid)
    assert labels(view) == dict.fromkeys(NETWORK, NOT_CONFIRMED)
    assert listener.connections() == 0
    assert "now points to a different IP address" in result_of(view, "tls_versions")["evidence"][0]["text"]


def test_tests_connect_only_to_the_pinned_ip(client, tls_server):
    """The name is looked up once, at the tick. Tests connect to that IP and send the name only as the TLS server name."""
    port = tls_server("demo")
    lab = client.app.state.lab
    lab.resolver = lambda host: ["127.0.0.1"]
    lab, imp, pid = plan_for(client, "shop.example.test", port)
    lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
    lab.run_all(pid)
    lab.wait_until_idle(pid, 90)
    view = lab.lab_view(pid)
    assert result_of(view, "tls_versions")["label"] == "Failed" and result_of(view, "certificate")["label"] == "Passed"
    with lab.db() as db:
        for run in db.query(TestRunRow).all():
            if "subject" in run.raw and "ip" in run.raw["subject"]:
                assert run.raw["subject"]["ip"] == "127.0.0.1"
    pq_result = result_of(view, "pq_readiness")
    assert pq_result["label"] in ("Not offered", "Couldn't run (needs OpenSSL 3.5 or newer)")
    if pq_result["label"] == "Not offered":
        assert "-connect 127.0.0.1:" in pq_result["run_record"]["command"] and "-servername shop.example.test" in pq_result["run_record"]["command"]
