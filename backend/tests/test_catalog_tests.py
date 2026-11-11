"""The two catalog tests: post-quantum readiness (with fakes for every path, plus the real checker when
there is one) and the ML-DSA-65 comparison."""
import json
from contextlib import contextmanager

import pytest

from app.db import TestRunRow
from app.execute import pq
from app.tlsprobe import openssl_cli
from conftest import demo_plan, result_of

OFFERED = """Connecting to 127.0.0.1
CONNECTION ESTABLISHED
Protocol version: TLSv1.3
Ciphersuite: TLS_AES_256_GCM_SHA384
Negotiated TLS1.3 group: X25519MLKEM768
DONE
"""
ALERT_40 = "Connecting to 127.0.0.1\n28BB:error:0A000410:SSL routines:ssl3_read_bytes:ssl/tls alert handshake failure:ssl/record/rec_layer_s3.c:918:SSL alert number 40\n"
ALERT_70 = "Connecting to 127.0.0.1\n28BB:error:0A00042E:SSL routines:ssl3_read_bytes:tlsv1 alert protocol version:ssl/record/rec_layer_s3.c:918:SSL alert number 70\n"
REFUSED = "28BB:error:8000006F:system library:BIO_connect:Connection refused:crypto/bio/bio_sock2.c:178:calling connect()\nconnect:errno=111\n"
NORMAL_OK = "Connecting to 127.0.0.1\nCONNECTION ESTABLISHED\nProtocol version: TLSv1.3\nPeer Temp Key: ECDH, prime256v1, 256 bits\nDONE\n"
OTHER_GROUP = NORMAL_OK.replace("DONE", "Negotiated TLS1.3 group: X25519\nDONE")
TRICK = "Connecting to 127.0.0.1\nPeer certificate: CN=Negotiated TLS1.3 group: X25519MLKEM768\nSSL alert number 40\n"


class FakeChecker:
    """Stands in for openssl s_client: plays back recorded outputs and notes every address it was sent to."""
    kind, version = "local", "OpenSSL 3.5.9 (recorded)"

    def __init__(self, subject_pq, subject_normal=NORMAL_OK, control_pq=OFFERED, control_fails=False):
        self.subject_pq, self.subject_normal, self.control_pq, self.control_fails = subject_pq, subject_normal, control_pq, control_fails
        self.calls = []

    def s_client(self, ip, port, server_name, pq_only):
        self.calls.append((ip, port, server_name, pq_only))
        if port == 1:
            out = self.control_pq
        else:
            out = self.subject_pq if pq_only else self.subject_normal
        return {"command": "openssl s_client (recorded)", "exit": 0 if "ESTABLISHED" in out else 1, "output": out}

    @contextmanager
    def control_server(self):
        if self.control_fails:
            raise RuntimeError("the control server did not start")
        yield 1


def run_pq(lab, monkeypatch, checker, why="no checker"):
    monkeypatch.setattr(pq, "find_checker", lambda mode: (checker, None) if checker else (None, why))
    plan = demo_plan(lab)
    view = lab.add_test(plan.id, "pq_readiness")
    item = next(t["id"] for t in view["tests"] if t["kind"] == "pq_readiness")
    lab.run_test(plan.id, item)
    lab.wait_until_idle(plan.id, 60)
    return result_of(lab.lab_view(plan.id), "pq_readiness")


def test_offered_needs_the_literal_line(lab, monkeypatch):
    checker = FakeChecker(OFFERED)
    result = run_pq(lab, monkeypatch, checker)
    assert result["label"] == "Offered" and result["control"]["outcome"] == "as_expected"
    # only the pinned IP was contacted, the name only as the TLS server name
    assert checker.calls[0] == ("127.0.0.1", lab.settings.demo_tls_port, "localhost", True)
    assert {c[0] for c in checker.calls} == {"127.0.0.1"}


def test_not_offered_needs_alert_40_a_normal_handshake_and_the_control(lab, monkeypatch):
    result = run_pq(lab, monkeypatch, FakeChecker(ALERT_40))
    assert result["label"] == "Not offered"
    assert result["summary"] == "The server does not offer the quantum-resistant key exchange X25519MLKEM768."
    assert result["control"]["line"] == "Control: a test server that does offer the new key exchange was detected as offering it, as expected."


@pytest.mark.parametrize("subject_pq, normal, label", [
    (ALERT_70, NORMAL_OK, "Couldn't run (the server's answer could not be read)"),       # no TLS 1.3 at all: not our question
    (ALERT_40, ALERT_40, "Couldn't run (the server's answer could not be read)"),        # refuses everything
    (REFUSED, REFUSED, "Couldn't run (the checker could not reach the server)"),
    ("(no answer before the time limit)", "(no answer before the time limit)", "Couldn't run (the checker could not reach the server)"),
    (OTHER_GROUP, NORMAL_OK, "Couldn't run (the server's answer could not be read)"),    # a handshake, but another group
    (TRICK, REFUSED, "Couldn't run (the server's answer could not be read)"),            # the words inside another line don't count
    ("", "", "Couldn't run (the checker could not reach the server)"),
])
def test_anything_else_is_couldnt_run_never_a_guess(lab, monkeypatch, subject_pq, normal, label):
    result = run_pq(lab, monkeypatch, FakeChecker(subject_pq, normal))
    assert result["label"] == label and result["suggested_fix"] is None


@pytest.mark.parametrize("checker", [FakeChecker(ALERT_40, control_pq=ALERT_40), FakeChecker(ALERT_40, control_fails=True),
                                     FakeChecker(OFFERED, control_pq=REFUSED), FakeChecker(ALERT_40, control_pq=OTHER_GROUP)])
def test_control_not_detected_as_offered_means_couldnt_trust(lab, monkeypatch, checker):
    assert run_pq(lab, monkeypatch, checker)["label"] == "Couldn't trust this run"


def test_no_checker_gives_exactly_the_answer_key_wording(lab, monkeypatch):
    result = run_pq(lab, monkeypatch, None, "The openssl program on this computer is OpenSSL 3.0.13. Docker is not running.")
    assert result["label"] == "Couldn't run (needs OpenSSL 3.5 or newer)"
    assert result["control"]["line"] == "Control: not run, because the test couldn't run."
    with lab.db() as db:
        assert db.get(TestRunRow, result["run_id"]).raw["problem"]["code"] == "checker_too_old"


def test_checker_choice(monkeypatch):
    from app.runner import ModeInfo
    assert pq.parse_version("OpenSSL 3.5.9 29 Sep 2026 (Library: OpenSSL 3.5.9 29 Sep 2026)") == (3, 5)
    assert pq.parse_version("OpenSSL 3.0.13 30 Jan 2024") == (3, 0) and pq.parse_version("LibreSSL 4.0") is None
    no_docker = ModeInfo("demo", "x", None, False, None, None)
    monkeypatch.setattr(pq, "openssl_cli", lambda: ("/usr/bin/openssl", "OpenSSL 3.0.13 30 Jan 2024"))
    checker, why = pq.find_checker(no_docker)
    assert checker is None and "3.0.13" in why and "Docker is not running" in why
    checker, why = pq.find_checker(ModeInfo("demo", "x", None, True, None, None))  # Docker, but the image is not here
    assert checker is None and "not prepared" in why
    monkeypatch.setattr(pq, "openssl_cli", lambda: (None, "not installed"))
    assert pq.find_checker(no_docker)[0] is None
    monkeypatch.setattr(pq, "openssl_cli", lambda: ("/usr/bin/openssl", "OpenSSL 3.6.1 1 Jan 2026"))
    checker, _ = pq.find_checker(no_docker)
    assert checker.kind == "local"


def test_checker_commands_are_fixed_argument_lists():
    assert pq.client_args("127.0.0.1", 8443, "localhost", True) == [
        "s_client", "-connect", "127.0.0.1:8443", "-servername", "localhost", "-groups", "X25519MLKEM768", "-tls1_3", "-brief"]
    assert pq.client_args("::1", 8443, None, False) == ["s_client", "-connect", "[::1]:8443", "-noservername", "-brief"]
    flags = " ".join(pq.DOCKER_FLAGS)
    for needed in ("--rm", "--read-only", "--cap-drop ALL", "--user 65534:65534", "--security-opt no-new-privileges", "--pull never",
                   "--memory 128m", "--pids-limit 32", "--network host"):
        assert needed in flags
    assert "-v" not in pq.DOCKER_FLAGS and "--volume" not in pq.DOCKER_FLAGS and "--privileged" not in pq.DOCKER_FLAGS


def _real_checker_available(lab) -> bool:
    path, version = openssl_cli()
    parsed = pq.parse_version(version)
    return bool((path and parsed and parsed >= (3, 5)) or (lab.mode.docker_running and lab.mode.openssl_image))


def test_live_not_offered_with_the_control_offered(demo_flow):
    if not _real_checker_available(demo_flow.lab):
        result = result_of(demo_flow.first, "pq_readiness")
        assert result["label"] == "Couldn't run (needs OpenSSL 3.5 or newer)"
        pytest.skip("Skipped: no OpenSSL 3.5 checker here (neither a local openssl 3.5+ nor Docker with the prepared OpenSSL image).")
    result = result_of(demo_flow.first, "pq_readiness")
    assert result["label"] == "Not offered" and result["control"]["outcome"] == "as_expected"
    with demo_flow.lab.db() as db:
        raw = db.get(TestRunRow, result["run_id"]).raw
    assert "SSL alert number 40" in raw["subject"]["pq_only"]["output"]
    assert "CONNECTION ESTABLISHED" in raw["subject"]["normal"]["output"]
    assert "Negotiated TLS1.3 group: X25519MLKEM768" in raw["control"]["pq_only"]["output"].splitlines()
    assert raw["control"]["port"] != demo_flow.lab.settings.demo_tls_port and raw["checker"]["version"].startswith("OpenSSL 3.")
    assert "PRIVATE KEY" not in str(raw)


def test_mldsa_comparison_is_measured_and_labelled(demo_flow):
    result = result_of(demo_flow.first, "mldsa_compare")
    assert result["label"] == "Measured" and result["control"]["outcome"] == "as_expected"
    assert "signature 3309 bytes, public key 1952 bytes" in result["summary"] and "reference, not production" in result["summary"]
    assert result["control"]["line"] == "Control: a deliberately altered signature was rejected, as expected."
    table = result["evidence"][0]
    assert "reference, not production" in table["columns"][1]["label"] and "reference, not production" in table["note"]
    assert table["columns"][2]["label"] == "acme-sign 1.4.2"
    with demo_flow.lab.db() as db:
        raw = db.get(TestRunRow, result["run_id"]).raw
    assert raw["mldsa65"]["public_key_bytes"] == 1952 and raw["mldsa65"]["signature_bytes"] == 3309
    assert len(raw["mldsa65"]["sign_ms"]) == 200 and raw["control"] == {
        "genuine_accepted": True, "altered_rejected": True, "what": "one byte in the middle of a genuine signature was changed"}
    card = next(t for t in demo_flow.lab.plan_view(demo_flow.plan.id)["tests"] if t["kind"] == "mldsa_compare")
    assert card["tag"] == "reference, not production" and card["origin"] == "added"
    # The library is the same production library the speed test calls its reference: the words must not say otherwise.
    said = json.dumps(result)
    assert "reference implementation" not in said and "not production code" not in said and "different kinds of software" not in said
    assert "They are not a measurement of any ML-DSA software of yours." in result["what_happened"][0]
    assert "different algorithms measured in different ways" in result["shows"][1] and "for scale only" in result["shows"][1]


def test_mldsa_control_that_accepts_an_altered_signature_means_couldnt_trust(lab, monkeypatch):
    from app.execute import speed
    real = speed.measure_mldsa65

    def broken(repeats, message):
        timings, control = real(repeats, message)
        return timings, dict(control, altered_rejected=False)
    monkeypatch.setattr(speed, "measure_mldsa65", broken)
    plan = demo_plan(lab)
    view = lab.add_test(plan.id, "mldsa_compare")
    lab.run_test(plan.id, next(t["id"] for t in view["tests"] if t["kind"] == "mldsa_compare"))
    lab.wait_until_idle(plan.id, 120)
    assert result_of(lab.lab_view(plan.id), "mldsa_compare")["label"] == "Couldn't trust this run"
