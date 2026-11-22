"""Phase 4e: "What this change touches" on every kind of fix of the Acme Pay demo, through the web, with its answer
checked against the Fixes shape. Each fix says where the part it changes is used, whether the parts that use it take
the new version (Not known, and why), and whether a client check applies (docs/SPEC.md, the table of changes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.present import impact as words
from tests.test_plan_api import wait

REPO = Path(__file__).resolve().parents[3]
DEMO_LIST = REPO / "demo" / "dependencies-demo.cdx.json"


@pytest.fixture
def acme(client):
    """Acme Pay in a project of its own, with the demo dependency list (acme-pay-server tied to the demo server), a
    second project that names the same server and program, and the two tests run that have a fix."""
    made = client.post("/api/projects", json={"name": "Acme Pay", "folder_id": None}).json()
    imp = client.post("/api/import/demo", params={"assessment_id": made["assessment_id"]}).json()
    address = imp["addresses"][0]["address"]
    client.post(f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True})
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid = plan["id"]
    view = client.post(
        f"/api/plans/{pid}/dependencies",
        params={"filename": DEMO_LIST.name},
        content=DEMO_LIST.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    pay = next(g for g in view["groups"] if g["label"] == "acme-pay-server 1.0.0")
    client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": pay["key"], "system": f"server:{address}"})
    other = client.post("/api/projects", json={"name": "Multi", "folder_id": None}).json()
    csv = f"location,type,claim,value\n{address},tls,protocol_versions,TLS1.3\nacme-sign 1.4.2,software,signature_algorithm,ECDSA P-256\n"
    client.post(
        "/api/import/file",
        params={"filename": "multi.csv", "assessment_id": other["assessment_id"]},
        content=csv.encode(),
        headers={"Content-Type": "application/octet-stream"},
    )
    item = {t["kind"]: t["id"] for t in plan["tests"]}
    for kind in ("tls_versions", "bad_signatures"):
        client.post(f"/api/plans/{pid}/tests/{item[kind]}/run")
        wait(client, pid, 240)
    fixes = {f["id"]: f for f in client.get(f"/api/plans/{pid}/fixes").json()["fixes"]}
    return address, other, fixes


def test_every_fix_says_what_it_touches(acme):
    address, other, fixes = acme
    # the code fix for acme-sign: the program here, and the other assessment that names it
    code = fixes["fix-ecdsa-range-check"]["impact"]
    assert code["title"] == "What this change touches" and code["part"] == "acme-sign 1.4.2"
    assert [line["text"] for line in code["here"]["lines"]] == [
        "acme-sign 1.4.2",
        "acme-sign 1.4.2",
        "Acme Pay token-signing service (demo data) 1.0.0",
    ]
    assert (
        code["here"]["lines"][2]["sub"]
        == "The thing your dependency list describes. Uses it directly. Not tied to a system of your file."
    )
    [elsewhere] = code["elsewhere"]["lines"]
    assert elsewhere["text"] == "Multi › Assessment 1" and elsewhere["link"]["assessment_id"] == other["assessment_id"]
    assert code["count_line"] == "Re-check these 2 after the change."
    assert code["compatible"]["title"] == "Can the parts that use it take the fixed version?"
    assert code["compatible"]["text"] == words.COMPATIBLE_UNKNOWN
    assert code["connect"]["text"] == words.CONNECT_PROGRAM.format(what="a signing program")
    # the server's TLS setting fix: the server, the software tied to it, the other assessment, Apply's reach, the try
    tls = fixes["fix-tls-versions"]["impact"]
    assert tls["part"] == address and [line["text"] for line in tls["here"]["lines"]] == [
        address,
        "acme-pay-server 1.0.0",
    ]
    assert tls["elsewhere"]["lines"][0]["sub"] == f"Names {address} as a server (the same address)."
    assert tls["notes"] == [words.APPLY_NOTE] and tls["compatible"] is None
    assert tls["connect"]["text"] == words.CONNECT_SEE_TRY
    # the library update a blocker calls for: the path to the server, and what a TLS library update can change
    dep = next(f for f in fixes.values() if f["id"].startswith("dependency-"))["impact"]
    assert dep["part"] == "openssl 3.0.22" and dep["count"] == 1
    assert dep["compatible"]["title"] == "Can the parts that use it take 3.5.0 or later?"
    assert dep["connect"]["text"] == words.CONNECT_TLS_LIBRARY
    for block in (code, tls, dep):
        for line in block["here"]["lines"] + block["elsewhere"]["lines"]:
            assert line["tag"] == "from your file" and line["sub"]


def test_no_block_on_a_developer_change_and_no_client_check_on_a_program(lab):
    assert lab._fix_impact(None, None, {"source_kind": "developer_change"}, {}, {}) is None
    assert words.connect_line(
        {"kind": "software", "roles": ["signatures"]}, change=None
    ) == words.CONNECT_PROGRAM.format(what="a program")
    assert (
        words.connect_line({"kind": "software", "roles": []}, change=None, signing_change=True) == words.CONNECT_SIGNING
    )
    assert words.connect_line({"kind": "server"}, change={"settings_after": None}) == words.CONNECT_NO_SETTING
    assert (
        words.connect_line({"kind": "server"}, change={"settings_after": {"versions": []}, "target": None})
        == words.CONNECT_NO_TRY
    )
    assert words.count_line(0, True) == "No system of yours to re-check was found."
    assert words.count_line(3, False) == "Re-check these 3 if you change it."
