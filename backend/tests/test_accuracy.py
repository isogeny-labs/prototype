"""The accuracy command: all 15 answers, through the same service path as the buttons, read from reviewed results."""
import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from app import accuracy
from app.config import DEMO_CBOM, EXPECTED_JSON
from conftest import free_port

BACKEND = Path(__file__).resolve().parents[1]
EXPECTED = json.loads(EXPECTED_JSON.read_text(encoding="utf-8"))
ALL_IDS = ["V1", "V2", "V3", "T1", "T2", "T3", "T4", "T5", "R1", "R2", "R3", "R4", "R5", "controls", "A1"]


def right_answers() -> dict:
    """Answers shaped like accuracy.collect() returns them, all agreeing with the answer key."""
    verify = {e["id"]: {"result": e["expected"], "found": "x", "reason": None, "claim": {"text": e["claim"]}} for e in EXPECTED["verify"]}
    tests = {}
    for entry in EXPECTED["tests_on_1_4_2"] + EXPECTED["tests_on_1_4_3"] + EXPECTED["add_on"]:
        code = {"Failed": "failed", "Passed": "passed", "Measured": "measured", "Not offered": "not_offered",
                "No slowdown beyond measured noise": "no_slowdown"}[entry["expected"]]
        tests[accuracy.TEST_IDS[entry["id"]]] = {"label": entry["expected"], "code": code, "summary": "s", "control": "as_expected",
                                                 "mode": "demo", "reason_code": None}
    tests[("pq_readiness", "retest")] = dict(tests[("pq_readiness", "first")])
    return {"notes": [], "mode_line": "Demo mode", "verify": verify, "unmapped_claims": [], "tests": tests, "stopped": None}


def report_for(change) -> dict:
    answers = right_answers()
    change(answers)
    return accuracy.compare(copy.deepcopy(EXPECTED), answers)


def lines_of(report) -> dict:
    return {line["id"]: line for line in report["lines"]}


def test_the_answer_key_has_fifteen_entries_and_each_is_mapped():
    report = report_for(lambda a: None)
    assert [line["id"] for line in report["lines"]] == ALL_IDS
    assert (report["matched"], report["total"]) == (15, 15) and accuracy.print_report(report, say=lambda s: None) == 0
    refs = {c.get("bom-ref") for c in json.loads(DEMO_CBOM.read_text())["components"]}
    assert {ref for ref, _ in accuracy.DEMO_CLAIM_IDS} <= refs
    assert sorted(accuracy.DEMO_CLAIM_IDS.values()) == ["V1", "V2", "V3"]
    assert sorted(accuracy.TEST_IDS) == sorted(i for i in ALL_IDS if i[0] in "TRA")


def test_a_wrong_answer_is_reported_and_gives_exit_code_1(monkeypatch, capsys):
    def wrong(a):
        a["tests"][("official_vectors", "first")].update(label="Passed", code="passed")
    report = report_for(wrong)
    assert (report["matched"], report["total"]) == (14, 15)
    assert lines_of(report)["T3"]["match"] is False and lines_of(report)["T3"]["actual"] == "Passed"
    said = []
    assert accuracy.print_report(report, say=said.append) == 1
    assert any(s.startswith("  T3  MISMATCH  expected 'Failed', app says 'Passed'") for s in said)
    assert said[-1] == "Demo accuracy: 14 of 15 match"
    # and through the command's own entry point
    answers = right_answers()
    wrong(answers)
    monkeypatch.setattr(accuracy, "collect", lambda settings=None: answers)
    assert accuracy.main([]) == 1
    out = capsys.readouterr().out
    assert "T3  MISMATCH" in out and out.strip().endswith("Demo accuracy: 14 of 15 match")
    monkeypatch.setattr(accuracy, "collect", lambda settings=None: right_answers())
    assert accuracy.main(["--mode", "demo"]) == 0 and capsys.readouterr().out.strip().endswith("Demo accuracy: 15 of 15 match")


def test_missing_answers_and_an_early_stop_are_mismatches_not_silence():
    report = report_for(lambda a: (a["tests"].pop(("speed_size", "retest")), a["verify"].pop("V2")))
    got = lines_of(report)
    assert got["R5"]["match"] is False and got["R5"]["actual"] == "(no answer)"
    assert got["V2"]["match"] is False and got["controls"]["match"] is False and "speed_size (retest)" in got["controls"]["actual"]
    assert report["matched"] == 12
    stopped = report_for(lambda a: a.update(stopped="The check stopped early: boom"))
    said = []
    assert accuracy.print_report(stopped, say=said.append) == 1 and any("PROBLEM" in s and "boom" in s for s in said)
    extra = report_for(lambda a: a["unmapped_claims"].append("a claim nobody listed"))
    assert accuracy.print_report(extra, say=lambda s: None) == 1
    nothing = accuracy.compare(copy.deepcopy(EXPECTED), {"notes": [], "verify": {}, "tests": {}, "unmapped_claims": [], "stopped": None, "mode_line": None})
    assert nothing["matched"] == 0 and nothing["total"] == 15


def test_controls_line_fails_on_any_untrusted_run_or_misbehaving_control():
    untrusted = report_for(lambda a: a["tests"][("certificate", "retest")].update(label="Couldn't trust this run", code="couldnt_trust", control="not_as_expected"))
    got = lines_of(untrusted)
    assert got["controls"]["match"] is False and "Couldn't trust this run: certificate (retest)" in got["controls"]["actual"]
    assert got["R2"]["match"] is False
    misbehaved = report_for(lambda a: a["tests"][("speed_size", "first")].update(control="not_as_expected"))
    assert lines_of(misbehaved)["controls"]["match"] is False and lines_of(misbehaved)["T5"]["match"] is True
    # a test that honestly could not run has no control outcome to judge; its own line is the mismatch
    couldnt = report_for(lambda a: a["tests"][("tls_versions", "first")].update(label="Couldn't run (the server did not answer)", code="couldnt_run", control="not_run"))
    assert lines_of(couldnt)["controls"]["match"] is True and lines_of(couldnt)["T1"]["match"] is False


def test_a1_alternative_only_counts_when_the_recorded_reason_is_the_checker_version():
    alternative = EXPECTED["add_on"][0]["or_if_checker_too_old"]
    assert alternative == "Couldn't run (needs OpenSSL 3.5 or newer)"
    old = report_for(lambda a: a["tests"][("pq_readiness", "first")].update(label=alternative, code="couldnt_run", control="not_run", reason_code="checker_too_old"))
    assert lines_of(old)["A1"]["match"] is True and "checker is too old" in lines_of(old)["A1"]["reason"]
    assert old["matched"] == 15
    for reason in (None, "checker_cannot_reach", "timeout"):
        other = report_for(lambda a: a["tests"][("pq_readiness", "first")].update(label=alternative, code="couldnt_run", control="not_run", reason_code=reason))
        assert lines_of(other)["A1"]["match"] is False and other["matched"] == 14
    another_label = report_for(lambda a: a["tests"][("pq_readiness", "first")].update(label="Couldn't run (it took too long)", code="couldnt_run", reason_code="checker_too_old"))
    assert lines_of(another_label)["A1"]["match"] is False
    offered = report_for(lambda a: a["tests"][("pq_readiness", "first")].update(label="Offered", code="offered"))
    assert lines_of(offered)["A1"]["match"] is False


def run_command(tmp_path, port, *args, rounds="25"):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "EVIDENCE_LAB_DATA_DIR": str(tmp_path / "data"),
           "EVIDENCE_LAB_DEMO_TLS_PORT": str(port), "EVIDENCE_LAB_SPEED_ROUNDS": rounds}
    if os.environ.get("DOCKER_HOST"):
        env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]
    return subprocess.run([sys.executable, "-m", "app.accuracy", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600)


def check_15_of_15(done, tmp_path):
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().endswith("Demo accuracy: 15 of 15 match")
    for answer_id in ALL_IDS:
        assert f"  {answer_id}  MATCH" in done.stdout, answer_id
    assert "MISMATCH" not in done.stdout and "PROBLEM" not in done.stdout
    assert "Confirmed localhost:" in done.stdout
    assert "3 of 484 official cases wrong" in done.stdout and "484 of 484 official cases right" in done.stdout
    assert not (tmp_path / "data" / "evidence-lab.sqlite3").exists()  # the app's own database is not used
    # nothing secret is printed: the keys this run made live in its data folder
    from test_secrets_scan import MARKERS, key_forms
    for name in ("evidence-signing-key.pem", "demo-tls-test-key.pem"):
        for form in key_forms(tmp_path / "data" / name):
            leaked = form in done.stdout + done.stderr   # (kept out of the assert, so a failure never prints the key)
            assert not leaked, name
    assert not any(marker in done.stdout + done.stderr for marker in MARKERS)


def test_command_is_15_of_15_in_demo_mode_and_never_touches_the_answer_key(tmp_path):
    before = hashlib.sha256(EXPECTED_JSON.read_bytes()).hexdigest()
    done = run_command(tmp_path, free_port(), "--mode", "demo")
    check_15_of_15(done, tmp_path)
    assert "  mode: Demo mode: running our own demo software, not isolated." in done.stdout
    assert hashlib.sha256(EXPECTED_JSON.read_bytes()).hexdigest() == before


def test_command_is_15_of_15_in_isolated_mode(tmp_path, docker_ready):
    """Skipped with a clear message when Docker is not running or the images are not prepared."""
    done = run_command(tmp_path, free_port(), "--mode", "isolated")
    check_15_of_15(done, tmp_path)
    assert "  mode: Isolated mode: our demo software runs in a locked-down container with no network." in done.stdout


def test_command_shows_mismatches_and_exits_non_zero_when_the_demo_server_cannot_be_reached(tmp_path):
    blocker = socket.create_server(("127.0.0.1", 0))  # something else holds the port and is not the demo server
    try:
        done = run_command(tmp_path, blocker.getsockname()[1], "--mode", "demo", rounds="2")
    finally:
        blocker.close()
    assert done.returncode != 0
    assert "V1  MISMATCH" in done.stdout and "T1  MISMATCH" in done.stdout and "V3  MATCH" in done.stdout
    last = done.stdout.strip().splitlines()[-1]
    assert last.startswith("Demo accuracy: ") and last.endswith(" of 15 match") and last != "Demo accuracy: 15 of 15 match"


def test_isolated_mode_asked_for_but_missing_is_a_mismatch_not_a_quiet_fallback(tmp_path, monkeypatch):
    from app import runner
    from app.config import Settings
    monkeypatch.setattr(runner, "_probe", lambda: (False, None, None))
    report = accuracy.run_accuracy(Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="isolated", speed_rounds=2))
    got = lines_of(report)
    assert report["mode_line"].startswith("Isolated mode was asked for, but it is not available")
    assert got["T3"]["actual"] == "Couldn't run (isolated mode is not available)" and got["T3"]["match"] is False
    assert got["V1"]["match"] is True and report["matched"] < 15
    assert accuracy.print_report(report, say=lambda s: None) == 1


@pytest.mark.parametrize("bad", [["--mode", "upload"], ["--file", "x"]])
def test_command_takes_nothing_but_the_mode(bad):
    with pytest.raises(SystemExit):
        accuracy.main(bad)
