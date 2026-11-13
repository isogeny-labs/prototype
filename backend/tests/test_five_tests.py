"""Each of the five tests end to end on the demo, with its real control; and each against a control that
is not broken, or that breaks down, which must give "Couldn't trust this run"."""
import json
import ssl
from contextlib import contextmanager


from app.db import TestRunRow
from app.demo_server import TlsServer, make_server_context
from app.execute import controls, signing
from conftest import demo_plan, result_of, run_kind

FIVE = ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")


def raw_of(lab, result):
    with lab.db() as db:
        return db.get(TestRunRow, result["run_id"]).raw


def test_first_run_answers_match_the_answer_key(demo_flow):
    labels = [result_of(demo_flow.first, k)["label"] for k in FIVE]
    assert labels == ["Failed", "Passed", "Failed", "Failed", "Measured"]
    assert [r["result"] for r in demo_flow.verify["results"]] == ["False", "True", "True"]


def test_every_control_behaved_as_expected(demo_flow):
    for view, which in ((demo_flow.first, "result"), (demo_flow.after, "after")):
        for row in view["rows"]:
            result = row[which]
            assert result["control"]["outcome"] == "as_expected", row["kind"]
            assert result["code"] != "couldnt_trust"
    for row in demo_flow.first["rows"]:
        assert row["control_line"].endswith("as expected.")


def test_old_tls_versions_fails_and_its_control_is_derived_from_the_claim(demo_flow):
    result = result_of(demo_flow.first, "tls_versions")
    assert result["summary"] == "The server accepted TLS 1.2. The file claims TLS 1.3 only."
    assert result["control"]["line"] == "Control: a deliberately misconfigured test server failed this test, as expected."
    raw = raw_of(demo_flow.lab, result)
    assert raw["subject"]["versions"]["TLS 1.2"]["state"] == "accepted" and raw["subject"]["ip"] == "127.0.0.1"
    assert raw["control"]["accepts"] == "TLS 1.2" and raw["control"]["versions"]["TLS 1.2"]["state"] == "accepted"
    assert raw["control"]["versions"]["TLS 1.1"]["state"] == "refused"   # it accepts exactly one step too far
    assert raw["control"]["port"] != demo_flow.lab.settings.demo_tls_port
    # the fix is in the Fixes step: Evidence Lab shows one line that points to it, in place of the suggested fix
    assert result["suggested_fix"] is None
    assert result["fix_line"] == {"fix_id": "fix-tls-versions", "lead": "Text-only suggestion:", "rest": "a server setting",
                                  "look": "dashed", "busy": False, "button": "View in Fixes"}


def test_certificate_passes_with_the_nist_note_and_the_weak_certificate_is_really_served(demo_flow):
    result = result_of(demo_flow.first, "certificate")
    assert result["summary"] == "The certificate is ECDSA P-256, 256 bits, as claimed. Note, not a failure: NIST plans to retire P-256."
    links = [m.get("href") for block in result["evidence"] for m in block["meta"]]
    assert links == ["https://csrc.nist.gov/pubs/sp/800/131/a/r2/final", "https://csrc.nist.gov/pubs/ir/8547/final"]
    control = raw_of(demo_flow.lab, result)["control"]
    assert control["certificate"]["algorithm"] == "RSA" and control["certificate"]["key_bits"] == 1024
    assert len(control["certificate"]["sha256_fingerprint"]) == 64 and "handshake completed" in control["evidence"][0]["output"]
    assert "RSA 1024" in result["control"]["text"]


def test_official_vectors_fail_on_exactly_168_171_364(demo_flow):
    result = result_of(demo_flow.first, "official_vectors")
    assert result["summary"] == "3 of 484 official cases wrong. Headline: case 168, a signature made of zeros (r=0 and s=0) was accepted."
    assert result["short"] == "3 of 484 official cases wrong (168, 171, 364), all from one missing range check."
    table = result["evidence"][0]
    assert table["title"] == "The 3 cases it got wrong" and [r[0] for r in table["rows"]] == ["168", "171", "364"]
    assert all(r[2:] == ["reject", "accepted"] for r in table["rows"])
    assert "all 310 invalid cases wrong" in result["control"]["text"]
    assert result["suggested_fix"] is None
    assert result["fix_line"] == {"fix_id": "fix-ecdsa-range-check", "lead": "Fix available,", "rest": "code not connected",
                                  "look": "plain", "busy": False, "button": "View in Fixes"}
    raw = raw_of(demo_flow.lab, result)
    assert len(raw["subject"]["answers"]) == 484 and len(raw["reference"]["ed25519"]["answers"]) == 210
    assert "ed25519_test.json" in raw["files"]
    locked = result["locked_test"]
    assert len(locked["fingerprint"]) == 64 and [f["label"] for f in locked["fields"]] == ["Question", "Method", "Inputs", "Control", "Pass/fail rule"]
    assert "not used on this component" in locked["fields"][2]["lines"][1]
    # the box holds a summary the app wrote, and is labelled as one (not as raw output)
    box = result["run_record"]["outputs"]
    assert [o["title"] for o in box] == ["Output summary"] and box[0]["text"].endswith(
        "Summary written by the app from the stored run. The full raw output is in the downloaded evidence JSON.")


def test_bad_signatures_fail_with_r0_s0_shown(demo_flow):
    result = result_of(demo_flow.first, "bad_signatures")
    assert result["summary"].startswith("acme-sign 1.4.2 accepts the signature r=0, s=0, which it must reject.")
    rows = {r[0]: r for r in result["evidence"][0]["rows"]}
    assert rows["r0-s0"][1:] == ["r = 0, s = 0", "reject", "accepted  (wrong)"]
    assert [k for k, r in rows.items() if "(wrong)" in r[3]] == ["r0-s0", "s-plus-n"]
    assert rows["good-1"][3] == "accepted" and len(rows) == 16
    assert [o["title"] for o in result["run_record"]["outputs"]] == ["Output summary"]
    # the cause is stated from this test's own cases; it never points at another result
    assert result["summary"].endswith("One cause: it never checks that the two signature numbers are inside the allowed range.")
    assert "official test vectors result" not in json.dumps(result)


def test_bad_signatures_run_alone_cites_no_other_result(lab):
    plan = demo_plan(lab)
    lab.remove_test(plan.id, plan.item["official_vectors"])
    result = run_kind(lab, plan, "bad_signatures")
    assert result["label"] == "Failed" and result["short"] == "Accepts the signature r=0, s=0. One cause: no range check."
    assert "official" not in result["summary"] and "official" not in result["short"]
    assert result["suggested_fix"] is None and result["fix_line"]["lead"] == "Fix available,"


def test_speed_is_measured_with_its_numbers_labelled(demo_flow):
    result = result_of(demo_flow.first, "speed_size")
    assert result["label"] == "Measured" and "medians over 100 repeats" in result["summary"]
    table = result["evidence"][0]
    assert table["title"] == "Timings and sizes" and [r[0] for r in table["rows"]][:2] == ["Sign, median", "Sign, slowest 1 in 100"]
    assert "for scale only" in table["note"] and {"measured", "reference"} <= {m["tag"] for m in table["meta"]}
    assert "Measured noise" in [m["label"] for m in table["meta"]]
    # one signature's length, said as such: this format is 70 to 72 bytes from one signature to the next
    assert "Signature size, this run" in [r[0] for r in table["rows"]] and "bytes in this run, public key 65 bytes" in result["summary"]
    assert "70 to 72 bytes" in table["note"] and "not a real difference" in table["note"]
    assert [o["title"] for o in result["run_record"]["outputs"]] == ["Output summary, acme-sign 1.4.2"]
    raw = raw_of(demo_flow.lab, result)
    assert raw["exclusive"] is True and {b["role"] for b in raw["benches"]} == {"subject", "control"}
    assert all(len(b["sign_ms"]) == 4 for b in raw["benches"]) and len(raw["benches"]) == 50
    assert "private" not in str(raw).lower()


def test_wording_rules_hold_on_every_result(demo_flow):
    import json
    for view in (demo_flow.first, demo_flow.after):
        assert view["disclaimer"] == "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
        text = json.dumps(view).lower()
        assert text.count("secure") == 1 and "score" not in text and "time-to-hack" not in text and "time to hack" not in text
        for row in view["rows"]:
            for which in ("result", "after"):
                r = row[which]
                if r:
                    assert r["shows_title"] == "What this shows, and what it doesn't" and len(r["shows"]) == 2
                    assert r["shows"][0].startswith("It shows") and r["shows"][1].startswith("It doesn't")
                    assert r["what_happened"] and r["run_record"]["outputs"]
                    # a suggested fix, or the one line that points to the fix in the Fixes step: never both, never neither
                    assert bool(r["suggested_fix"]) != bool(r["fix_line"])
                    assert (r["fix_line"] is not None) == (r["tone"] == "fail")


# ---------------------------------------------------------------- a control that is not broken, or that breaks down

def test_tls_control_that_crashes_means_couldnt_trust(lab, monkeypatch):
    @contextmanager
    def crash(*_args):
        raise OSError("no port")
        yield
    monkeypatch.setattr(controls, "tls_server_accepting", crash)
    result = run_kind(lab, demo_plan(lab), "tls_versions")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "errored"
    assert result["suggested_fix"] is None and "did not behave as expected" in result["control"]["line"]


def test_tls_control_that_is_configured_correctly_means_couldnt_trust(lab, monkeypatch, test_cert):
    @contextmanager
    def well_configured(*_args):
        server = TlsServer(make_server_context(*test_cert, minimum=ssl.TLSVersion.TLSv1_3))
        try:
            yield server.port
        finally:
            server.close()
    monkeypatch.setattr(controls, "tls_server_accepting", well_configured)
    result = run_kind(lab, demo_plan(lab), "tls_versions")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "not_as_expected"


def test_certificate_control_with_a_strong_certificate_means_couldnt_trust(lab, monkeypatch, test_cert):
    @contextmanager
    def strong(*_args):
        server = TlsServer(make_server_context(*test_cert))
        try:
            yield server.port
        finally:
            server.close()
    monkeypatch.setattr(controls, "weak_certificate_server", strong)
    result = run_kind(lab, demo_plan(lab), "certificate")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "not_as_expected"


def test_certificate_control_that_cannot_be_read_means_couldnt_trust(lab, monkeypatch, listener):
    @contextmanager
    def silent(*_args):
        yield listener.port  # something that never speaks TLS
    monkeypatch.setattr(controls, "weak_certificate_server", silent)
    result = run_kind(lab, demo_plan(lab), "certificate")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "errored"


def test_signature_control_that_checks_properly_means_couldnt_trust(lab, monkeypatch):
    monkeypatch.setattr(signing, "CONTROL", "acme-sign-1.4.3")  # a "broken signer" that is not broken
    result = run_kind(lab, demo_plan(lab), "bad_signatures")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "not_as_expected"


def test_harness_timeout_is_couldnt_run_not_a_guess(lab, monkeypatch):
    from app import runner
    monkeypatch.setattr(lab.component_runner, "run_job", lambda job, **_k: runner.BatchResult(
        False, [], runner.PROBLEM_TIMEOUT, "demo", "x", "2026-11-11T00:00:00.000Z", 1, ""))
    plan = demo_plan(lab)
    assert run_kind(lab, plan, "bad_signatures")["label"] == "Couldn't run (it took too long)"
    assert run_kind(lab, plan, "speed_size")["label"] == "Couldn't run (it took too long)"


def test_speed_control_that_is_not_slower_means_couldnt_trust(lab, monkeypatch):
    real = lab.component_runner.run_job

    def swap(job, **kwargs):  # the "slowed" signer is quietly replaced by the ordinary one
        job = dict(job, subjects=[s.replace("control-slow:", "") for s in job["subjects"]])
        return real(job, **kwargs)
    monkeypatch.setattr(lab.component_runner, "run_job", swap)
    result = run_kind(lab, demo_plan(lab), "speed_size")
    assert result["label"] == "Couldn't trust this run" and result["control"]["outcome"] == "not_as_expected"


def test_a_component_that_is_not_ours_is_never_run(client):
    from conftest import csv_bytes, upload
    lab = client.app.state.lab
    imp = upload(client, "claims.csv", csv_bytes("other-signer 2.0,software,signature_algorithm,ECDSA P-256")).json()
    plan = lab.ensure_plan(imp["id"])
    assert [t["kind"] for t in plan["tests"]] == ["official_vectors", "bad_signatures", "speed_size"]
    lab.run_all(plan["id"])
    lab.wait_until_idle(plan["id"], 60)
    view = lab.lab_view(plan["id"])
    assert {r["result"]["label"] for r in view["rows"]} == {"Couldn't run (only our demo components can be run in this version)"}
    assert view["retest"]["can_start"] is False and view["retest"]["versions"] == []


def test_control_servers_are_local_throwaway_and_closed_afterwards():
    import socket
    from app.tlsprobe import ProbeSession, describe_certificate
    with controls.weak_certificate_server() as port:
        session = ProbeSession("127.0.0.1", port, None)
        cert = describe_certificate(session.first_certificate())
        assert (cert["key_type"], cert["key_size"]) == ("RSA", 1024) and "control" in cert["subject"]
    with controls.tls_server_accepting("TLS 1.1", ["TLS 1.2", "TLS 1.3"]) as old_port:  # a claim of "1.2 and 1.3 only"
        seen, _ = ProbeSession("127.0.0.1", old_port, None).versions()
        assert seen["TLS 1.1"].status == "accepted" and seen["TLS 1.0"].status != "accepted"
    for closed in (port, old_port):
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", closed)) != 0  # nothing is left listening
    import inspect
    source = inspect.getsource(controls)
    assert "0.0.0.0" not in source and source.count("SECLEVEL=0") == 1
