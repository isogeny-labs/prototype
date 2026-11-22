"""Phase 4e: "Who can still connect" inside real tries on our own demo servers (demo mode, no Docker). The four demo
client stand-ins connect to the server as it is today and to the test copy, and the separate reviewer gives each its
word. It is information: the try is still decided by the system's own measurement, a Breaks holds nothing off, and the
run is on Checks, in Evidence, in the signed evidence file and in the report."""

from __future__ import annotations

import json

import pytest

from app.present import clients as words
from app.servers import migration_servers
from tests.conftest import free_port, make_lab


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    ports = tuple(free_port() for _ in range(5))
    lab = make_lab(tmp_path_factory.mktemp("clients"), migration_ports=ports, lab_nginx_port=free_port())
    try:
        imp = lab.import_file("migration-demo.csv", migration_servers.file_for(ports))
        for a in imp["addresses"]:
            lab.confirm_address(imp["id"], a["address"], True)
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.measure_migration(pid)
        lab.wait_until_measured(pid, 300)
        addr = dict(zip(("hybrid", "c1", "c2", "legacy", "pq"), [f"localhost:{p}" for p in ports]))  # noqa: B905
        # 8452 (classical, internet-facing, long-lived): its recommended change, Hybrid
        lab.try_change(pid, f"migration:server:{addr['c1']}")
        # 8451 (hybrid today): Full post-quantum, chosen by a person
        lab.choose_migration_option(pid, f"server:{addr['hybrid']}", "full_pq", "To see who breaks", None)
        lab.try_change(pid, f"migration:server:{addr['hybrid']}")
        lab.wait_until_changes_idle(pid)
        yield type("Flow", (), dict(lab=lab, pid=pid, addr=addr))
    finally:
        lab.stop()


def _box(flow, name: str) -> dict:
    return next(s for s in flow.lab.migration_view(flow.pid)["systems"] if s["name"] == name)["change"]


def _words(box: dict) -> dict:
    return {r["id"]: r["word"] for r in box["try"]["clients"]["rows"]}


@pytest.mark.slow
def test_hybrid_keeps_every_classical_client_and_the_new_firmware_takes_hybrid(flow):
    box = _box(flow, flow.addr["c1"])
    assert box["try"]["verdict"]["label"] == "Try passed."  # the try is the system's own measurement
    clients = box["try"]["clients"]
    assert _words(box) == {
        "old-terminal": "Falls back",
        "partner-classical": "Falls back",
        "new-terminal": "Connects",
        "pq-only": "Didn't connect before either",
    }
    assert clients["summary"] == (
        "None break. 1 connects with hybrid or post-quantum key exchange; 2 fall back to classical key "
        "exchange; 1 didn't connect before either."
    )
    assert clients["warning"] is None and clients["control"] == words.CONTROL_TEXT
    new = next(r for r in clients["rows"] if r["id"] == "new-terminal")
    assert (new["today"], new["on_copy"]) == ("TLS 1.3, classical (X25519)", "TLS 1.3, hybrid (X25519MLKEM768)")
    assert any(r["label"] == "who can still connect (the client stand-ins)" for r in box["try"]["results"])


@pytest.mark.slow
def test_full_post_quantum_breaks_three_and_apply_is_not_held_off(flow):
    lab, key = flow.lab, f"migration:server:{flow.addr['hybrid']}"
    box = _box(flow, flow.addr["hybrid"])
    assert box["try"]["verdict"]["label"] == "Try passed."
    assert _words(box) == {
        "old-terminal": "Breaks",
        "partner-classical": "Breaks",
        "new-terminal": "Breaks",
        "pq-only": "Connects",
    }
    clients = box["try"]["clients"]
    assert clients["summary"] == "3 break, 1 connects with hybrid or post-quantum key exchange."
    assert clients["warning"] == "Sort out the 3 that break before you apply this change."
    pq = next(r for r in clients["rows"] if r["id"] == "pq-only")
    assert pq["note"] == "New: it can't connect today." and pq["on_copy"] == "TLS 1.3, ML-KEM by itself (MLKEM768)"
    old = next(r for r in clients["rows"] if r["id"] == "old-terminal")
    assert old["today"].startswith("TLS 1.2, classical") and old["on_copy"] == "Refused (protocol version)"
    # a Breaks holds nothing off: approval can be asked, and Apply opens once it is given
    lab.ask_approval(flow.pid, key, ["you"])
    lab.approve_change(flow.pid, key, "you")
    apply = next(b for b in _box(flow, flow.addr["hybrid"])["buttons"] if b["action"] == "apply")
    assert apply["enabled"], apply


@pytest.mark.slow
def test_the_run_is_on_checks_and_in_the_signed_evidence_and_the_report(flow):
    from evidence import trusted_key_from_data_dir, verify_bytes

    lab = flow.lab
    lab.checks_view(flow.pid)  # the page reads (and words every row)
    rows = {r["id"]: r for r in lab.ledger(flow.pid)["rows"]}
    row = rows[f"try-migration:server:{flow.addr['c1']}-try_clients"]
    assert (
        row["name"] == f"Who can still connect: {flow.addr['c1']}" and row["came_from"]["label"] == "Try on a test copy"
    )
    assert row["group"] == "migration" and row["result"]["label"] == "Measured"
    assert row["ran_on"] == "a test copy with the change, and the server as it is today"
    assert row["link"] == {"page": "migration/systems", "item": f"server:{flow.addr['c1']}"}  # Open where it started
    export = lab.export_evidence(flow.pid)
    _, raw, _ = lab.evidence_file(export["id"], "json")
    _, report, _ = lab.evidence_file(export["id"], "html")
    assert verify_bytes(raw, trusted_key_from_data_dir(lab.settings.data_dir)).ok
    entry = next(
        e for e in json.loads(raw)["evidence"]["changes"] if e["change"]["system_key"] == f"server:{flow.addr['c1']}"
    )
    [tried] = entry["rounds"]["tries"]
    assert tried["outcome"] == "passed" and tried["clients"]["counts"]["falls_back"] == 2
    assert {s["id"]: s["word"] for s in tried["clients"]["stand_ins"]}["new-terminal"] == "connects"
    run = next(r for r in entry["runs"] if r["copy"] == "who can still connect (the client stand-ins)")
    assert run["run_id"] == tried["clients"]["run_id"]
    page = report.decode()
    assert "Who can still connect: " in page and "None break." in page
    assert b"PRIVATE KEY" not in raw + report


@pytest.mark.slow
def test_the_acme_pay_tls_fix_breaks_only_the_old_firmware_through_the_web(client):
    """TLS 1.3 only on the Acme Pay demo server, tried from Fixes through the web: the answer is checked against the Fixes
    shape (tests/api_shapes.py), and its row on Checks is in Crypto tests, under Tries on a test copy."""
    from tests.test_plan_api import start, wait

    imp = start(client)
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid = plan["id"]
    item = {t["kind"]: t["id"] for t in plan["tests"]}
    client.post(f"/api/plans/{pid}/tests/{item['tls_versions']}/run")
    wait(client, pid)
    fix = next(f for f in client.get(f"/api/plans/{pid}/fixes").json()["fixes"] if f["id"] == "fix-tls-versions")
    assert fix["change_box"]["try"] is None and fix["impact"]["connect"]["text"] == (
        "This change alters what the server offers on the network. Try on a test copy, in the change box below, also connects four "
        "demo client stand-ins and shows who can still connect."
    )
    assert client.post(f"/api/plans/{pid}/changes/try", json={"change": fix["change_box"]["id"]}).json() == {"ok": True}
    for _ in range(600):
        box = next(f for f in client.get(f"/api/plans/{pid}/fixes").json()["fixes"] if f["id"] == "fix-tls-versions")[
            "change_box"
        ]
        if not box["busy"] and box["try"] and box["try"]["clients"] and not box["try"]["clients"]["running"]:
            break
    clients = box["try"]["clients"]
    assert {r["id"]: r["word"] for r in clients["rows"]} == {
        "old-terminal": "Breaks",
        "partner-classical": "Connects",
        "new-terminal": "Connects",
        "pq-only": "Didn't connect before either",
    }
    assert clients["summary"] == "1 breaks, 2 connect, 1 didn't connect before either."
    assert clients["warning"] == "Sort out the 1 that breaks before you apply this change."
    assert box["try"]["verdict"]["label"] == "Try passed."
    checks = client.get(f"/api/plans/{pid}/checks").json()
    crypto = next(g for g in checks["groups"] if g["key"] == "encryption")
    tries = crypto["parts"]["tries"]
    names = [r["name"] for r in tries.get("rows") or []] + [
        r["name"] for b in tries.get("blocks") or [] for r in b.get("rows") or []
    ]
    assert any(name.startswith("Who can still connect: ") for name in names), names
