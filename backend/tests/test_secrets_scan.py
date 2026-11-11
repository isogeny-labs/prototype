"""After a full run and retest: no private key anywhere it could leak (database, evidence JSON, HTML report, logs).

The scan knows these secrets: the evidence signing key, the demo TLS test key, and every private key a demo
component handed to the backend during Verify (the test wraps the one function that receives them). Keys made
inside the test harness never reach the backend at all; that is checked by looking at what the harness sent.
Failure messages name the place, never the secret."""
import base64
import logging
import sqlite3
import stat

from cryptography.hazmat.primitives import serialization

from app import components, runner
from app.demo_server import KEY_FILE
from app.evidence_export import SIGNING_KEY_FILE
from conftest import demo_plan, make_lab, run_kind

MARKERS = ("PRIVATE KEY", "BEGIN EC PRIVATE", "BEGIN OPENSSH", "BEGIN RSA PRIVATE")


def key_forms(pem_path) -> list[str]:
    """Every way the key in this file could show up: its PEM body, and its secret number as hex and base64."""
    pem = pem_path.read_bytes()
    body = "".join(line for line in pem.decode("ascii").splitlines() if line and not line.startswith("-----"))
    key = serialization.load_pem_private_key(pem, password=None)
    try:
        secret = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    except (ValueError, TypeError):
        secret = key.private_numbers().private_value.to_bytes(32, "big")
    return [body, body[:40], body[-40:], secret.hex(), secret.hex().upper(), base64.b64encode(secret).decode(),
            base64.urlsafe_b64encode(secret).decode().rstrip("=")]


def database_text(path, tables=("test_runs", "reviews", "verify_runs", "evidence_exports", "research_requests")) -> str:
    """Every value of every table, as text (binary columns decoded, so the stored downloads are included)."""
    out = []
    with sqlite3.connect(path) as conn:
        found = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert set(tables) <= set(found)
        for table in found:
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                out += [v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v) for v in row]
    return "\n".join(out)


def test_no_private_key_in_database_evidence_report_or_logs(demo_flow, tmp_path, monkeypatch, capfd, caplog):
    lab, data_dir = demo_flow.lab, demo_flow.lab.settings.data_dir
    caplog.set_level(logging.DEBUG)

    # 1. Collect the secrets. Verify is the only step where a component's private key reaches the backend.
    handed_over, real_run = [], components.run_component

    def recording_run(path, command, payload=None, *args, **kwargs):
        done = real_run(path, command, payload, *args, **kwargs)
        if isinstance(done.data, dict) and isinstance(done.data.get("private_key"), str):
            handed_over.append(done.data["private_key"])
        return done

    harness_lines, real_job = [], runner.ComponentRunner.run_job

    def recording_job(self, job, **kwargs):
        result = real_job(self, job, **kwargs)
        harness_lines.append(str(result.lines) + result.stderr_tail)
        return result

    monkeypatch.setattr(components, "run_component", recording_run)
    monkeypatch.setattr(runner.ComponentRunner, "run_job", recording_job)
    lab.verify(demo_flow.plan.imp["id"])                       # a fresh Verify, recorded
    assert len(handed_over) == 1 and len(handed_over[0]) == 64
    # A speed test on a second, small lab: its test key is made inside the harness and must never come back.
    small = make_lab(tmp_path, speed_rounds=2)
    try:
        plan = demo_plan(small)
        run_kind(small, plan, "speed_size")
        run_kind(small, plan, "bad_signatures")
        small_database = database_text(small.settings.db_path, tables=())
    finally:
        small.stop()
    assert len(harness_lines) == 2 and "public_key_bytes" in harness_lines[0]
    assert "private_key" not in "".join(harness_lines).replace("[test private key withheld]", "")
    a_run = next(r["result"]["run_id"] for r in lab.lab_view(demo_flow.plan.id)["rows"] if r["kind"] == "bad_signatures")
    lab.mark_reviewed(a_run)
    lab.dig_deeper(a_run)

    secrets = {"evidence signing key": key_forms(data_dir / SIGNING_KEY_FILE), "demo TLS test key": key_forms(data_dir / KEY_FILE),
               "component test key from Verify": [handed_over[0], handed_over[0].upper()]}

    # 2. Make the download, then gather everything that is stored, shown or logged.
    made = lab.export_evidence(demo_flow.plan.id)
    evidence_json = lab.evidence_file(made["id"], "json")[1].decode("utf-8")
    report_html = lab.evidence_file(made["id"], "html")[1].decode("utf-8")
    captured = capfd.readouterr()
    places = {"database": database_text(lab.settings.db_path), "second database": small_database, "evidence JSON": evidence_json, "HTML report": report_html,
              "captured output": captured.out + captured.err, "captured log records": caplog.text,
              "harness output": "\n".join(harness_lines), "API session": str(lab.session_json(None)),
              "views": str(lab.lab_view(demo_flow.plan.id)) + str(lab.plan_view(demo_flow.plan.id)) + str(lab.latest_verify(demo_flow.plan.imp["id"]))}
    assert len(places["database"]) > 100_000 and len(evidence_json) > 50_000 and len(report_html) > 20_000

    # 3. Scan.
    for place, text in places.items():
        for name, forms in secrets.items():
            for i, form in enumerate(forms):
                assert len(form) >= 32
                leaked = form in text   # (kept out of the assert, so a failure never prints the key)
                assert not leaked, f"the {name} (form {i}) appears in the {place}"
        for marker in MARKERS:
            marked = marker in text
            assert not marked, f"a private-key marker ({marker}) appears in the {place}"
    # the Verify evidence shows that a key was used, with the key itself withheld
    assert "[test private key withheld]" in places["database"] and "[test private key withheld]" in evidence_json
    # only the public half of the signing key is in the download
    assert (data_dir / "evidence-signing-public-key.txt").read_text().strip() in evidence_json


def test_key_files_are_private_to_this_user(demo_flow):
    data_dir = demo_flow.lab.settings.data_dir
    for name in (SIGNING_KEY_FILE, KEY_FILE):
        assert stat.S_IMODE((data_dir / name).stat().st_mode) == 0o600, name
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700


def test_the_scan_itself_notices_a_planted_key(tmp_path):
    """The scan is only worth something if it can fail."""
    from app.evidence_export import ensure_signing_key
    ensure_signing_key(tmp_path)
    forms = key_forms(tmp_path / SIGNING_KEY_FILE)
    leaked = "log line: " + (tmp_path / SIGNING_KEY_FILE).read_text()
    assert any(form in leaked.replace("\n", "") or form in leaked for form in forms) and "PRIVATE KEY" in leaked
