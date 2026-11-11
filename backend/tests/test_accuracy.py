import hashlib
import json
import subprocess
import sys
from pathlib import Path

from app import accuracy
from app.config import DEMO_CBOM, EXPECTED_JSON, Settings
from conftest import free_port

BACKEND = Path(__file__).resolve().parents[1]


def test_accuracy_is_3_of_3_and_never_touches_the_answer_key(tmp_path):
    before = hashlib.sha256(EXPECTED_JSON.read_bytes()).hexdigest()
    report = accuracy.run_accuracy(Settings(data_dir=tmp_path / "data", demo_tls_port=free_port()))
    assert [(line["id"], line["expected"], line["actual"], line["match"]) for line in report["lines"]] == [
        ("V1", "False", "False", True), ("V2", "True", "True", True), ("V3", "True", "True", True)]
    assert (report["matched"], report["total"], report["unmapped_claims"]) == (3, 3, [])
    assert any("Confirmed localhost:" in n for n in report["notes"])
    assert hashlib.sha256(EXPECTED_JSON.read_bytes()).hexdigest() == before
    assert not (tmp_path / "data" / "evidence-lab.sqlite3").exists()  # the app's own database is not used


def test_claim_mapping_points_at_real_bom_refs():
    refs = {c.get("bom-ref") for c in json.loads(DEMO_CBOM.read_text())["components"]}
    assert {ref for ref, _ in accuracy.DEMO_CLAIM_IDS} <= refs
    assert sorted(accuracy.DEMO_CLAIM_IDS.values()) == ["V1", "V2", "V3"]


def run_command(tmp_path, port):
    env = {"PATH": "/usr/bin:/bin", "EVIDENCE_LAB_DATA_DIR": str(tmp_path / "data"), "EVIDENCE_LAB_DEMO_TLS_PORT": str(port)}
    return subprocess.run([sys.executable, "-m", "app.accuracy"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)


def test_command_prints_each_line_and_exits_zero(tmp_path):
    done = run_command(tmp_path, free_port())
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Demo accuracy: 3 of 3 match" in done.stdout
    for vid in ("V1", "V2", "V3"):
        assert f"  {vid}  MATCH" in done.stdout
    assert "Confirmed localhost:" in done.stdout


def test_command_shows_mismatches_and_exits_non_zero_when_the_demo_server_cannot_be_reached(tmp_path):
    import socket
    blocker = socket.create_server(("127.0.0.1", 0))  # something else holds the port and is not the demo server
    try:
        done = run_command(tmp_path, blocker.getsockname()[1])
    finally:
        blocker.close()
    assert done.returncode != 0
    assert "Demo accuracy: 1 of 3 match" in done.stdout and "V1  MISMATCH" in done.stdout
