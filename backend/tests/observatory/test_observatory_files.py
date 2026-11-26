"""The Observatory's map and the files it is drawn from: the one new matching rule (the service of the two files), the
ties Dependencies already has, a dependency list that describes something else, a person's own tie, a CSV scanner
file, an import with no kept copy, a scanner file that names the software of its endpoint, and a claim the file puts
on no system. No check is run in this file: everything here follows from the files alone."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from app.config import DEMO_CBOM
from app.importer.reader import parse_file
from app.observatory import build
from app.observatory.match import same_service
from app.present import observatory as words
from app.web import models
from tests.conftest import csv_bytes, make_lab
from tests.observatory import observatory_walk as W
from tests.view_helpers import problems


@pytest.fixture
def lab(tmp_path):
    lab = make_lab(tmp_path)
    yield lab
    lab.stop()


def _view(lab, plan_id: int) -> dict:
    view = build.view_of_plan(lab, plan_id)
    assert problems(view, models.ObservatoryView, "observatory") == []
    for box in W.boxes(view):
        assert problems(build.panel_of_plan(lab, plan_id, box["key"]), models.ObservatoryPanel, box["key"]) == []
    for text in W.texts(view):
        assert not W.NEVER.search(text), text
    return view


# ---------------------------------------------------------------- the one new matching rule


def test_the_service_of_the_two_files_is_one_box_only_with_the_same_name_and_the_same_version():
    acme = ("Acme Pay token-signing service (demo data)", "1.0.0")
    assert same_service(acme, acme)
    # the name without regard to capital letters, and runs of spaces as one: the rule Dependencies ties a program by
    assert same_service(acme, ("ACME pay  token-signing service (demo data)", "1.0.0"))
    assert same_service(("Shop", " 2 "), ("shop", "2"))
    # the version letter for letter
    assert not same_service(acme, (acme[0], "1.0.1")) and not same_service(acme, (acme[0], "1.0"))
    assert not same_service(acme, (acme[0], "v1.0.0")) and not same_service(("Shop", "1.0-RC"), ("Shop", "1.0-rc"))
    # another name, however close
    assert not same_service(acme, ("Acme Pay token-signing service", "1.0.0"))
    assert not same_service(acme, ("Acme Pay token signing service (demo data)", "1.0.0"))
    # a file that gives no version, or names nothing, is never matched: no version is not "the same version"
    for other in (None, (acme[0], None), (acme[0], ""), (None, "1.0.0"), ("", "1.0.0"), (acme[0], 1), (7, "1.0.0")):
        assert not same_service(acme, other) and not same_service(other, acme)
    assert not same_service(("Shop", None), ("Shop", None)) and not same_service(None, None)


def _listed(mutate) -> bytes:
    doc = copy.deepcopy(W.LISTED)
    mutate(doc)
    return json.dumps(doc).encode()


def test_a_dependency_list_that_describes_something_else_is_listed_apart_and_nothing_is_merged(lab):
    plan = W.start(lab)
    lab.add_dependency_list(
        plan.id, "other.cdx.json", _listed(lambda d: d["metadata"]["component"].update(version="2.0.0"))
    )
    view = _view(lab, plan.id)
    scanner, listed = view["services"]
    assert (scanner["key"], scanner["sub"], scanner["in_files"]) == (
        "service",
        "Named in your scanner file",
        ["scanner"],
    )
    assert (listed["key"], listed["title"], listed["version"]) == (
        "listed",
        W.LISTED["metadata"]["component"]["name"],
        "2.0.0",
    )
    assert listed["sub"] == "Named in your dependency list" and listed["in_files"] == ["dependencies"]
    assert listed["is_demo"] is False  # (only the scanner file is the demo's)
    # the list's own software is in its own box; the scanner file's parts stay where they were
    assert [b["key"] for b in scanner["boxes"]] == [plan.server, plan.program]
    assert [b["key"] for b in listed["boxes"]] == ["top:acme-pay-server", "top:acme-ledger"]
    # the one tie Dependencies itself makes (acme-sign 1.4.2, by name and version) still stands: it is that page's rule
    assert [t["source"] for t in W.box(view, plan.program)["ties"]] == ["name_version"]
    panel = build.panel_of_plan(lab, plan.id, "top:acme-ledger")
    assert panel["part_of"] == f"{listed['title']} 2.0.0"
    assert (
        build.place_of_plan(lab, plan.id, "claim:1")["place"]["path"][0] == f"{scanner['title']} {scanner['version']}"
    )
    # a newer list with the same name and version again: one box again (the newest list is the one in force)
    W.add_list(lab, plan)
    assert [s["key"] for s in _view(lab, plan.id)["services"]] == ["service"]


def test_a_dependency_list_that_does_not_say_what_it_describes_is_listed_apart_too(lab):
    plan = W.start(lab)

    def nameless(doc):
        del doc["metadata"]["component"]
        doc["dependencies"] = [d for d in doc["dependencies"] if d["ref"] != "acme-pay"]

    lab.add_dependency_list(plan.id, "nameless.cdx.json", _listed(nameless))
    view = _view(lab, plan.id)
    listed = view["services"][1]
    assert (listed["key"], listed["title"], listed["version"]) == ("listed", None, None)
    assert listed["sub"] == words.LIST_UNNAMED
    assert [b["key"] for b in listed["boxes"]] == ["top:acme-pay-server", "top:acme-ledger"]


def test_a_persons_own_tie_makes_the_entry_the_servers_box_and_closes_that_gap(lab):
    plan = W.start(lab)
    W.add_list(lab, plan)
    before = _view(lab, plan.id)
    assert "software" in {g["key"] for g in before["gaps"]["items"]}
    lab.tie_dependency(plan.id, "acme-pay-server", plan.server)
    view = _view(lab, plan.id)
    server = W.box(view, plan.server)
    assert (
        server["in_files"] == ["scanner", "dependencies"]
        and server["sub"] == f"Server · {plan.address} · in both files"
    )
    assert [(t["label"], t["source"]) for t in server["ties"]] == [("acme-pay-server 1.0.0", "user")]
    assert server["ties"][0]["words"] == (
        "In both files: acme-pay-server 1.0.0 in your dependency list is tied to it by you, with Part of on Dependencies."
    )
    # it is the same box now: no box of its own, and its libraries hang from the server
    assert [b["key"] for b in W.boxes(view)] == [plan.server, plan.program, "top:acme-ledger"]
    group = next(g for g in view["libraries"] if g["key"] == "libraries:acme-pay-server")
    assert group["owner"] == plan.server
    assert (plan.server, "libraries:acme-pay-server", "uses", "uses 2 libraries") in W.lines(view)
    # a person said which software answers on the address, so the map no longer lists it as missing
    assert [g["key"] for g in view["gaps"]["items"]] == ["clients", "data_flows"]
    panel = build.panel_of_plan(lab, plan.id, plan.server)
    assert [g["key"] for g in panel["gaps"]["items"]] == ["clients"]
    assert [f["title"] for f in panel["file_lines"]] == ["In your scanner file", "In your dependency list"]
    assert panel["libraries"][0]["count"] == 2
    assert W.box(view, "top:acme-ledger")["note"].startswith("Not tied to ")
    # "None of these" unties it again: its own box is back, and so is the gap
    lab.tie_dependency(plan.id, "acme-pay-server", None)
    again = _view(lab, plan.id)
    assert [b["key"] for b in W.boxes(again)] == [b["key"] for b in W.boxes(before)]
    assert again["gaps"] == before["gaps"] and W.lines(again) == W.lines(before)


# ---------------------------------------------------------------- a file with no structure


def test_a_csv_scanner_file_is_drawn_from_its_claims_alone(lab):
    address = lab.settings.demo_address
    imp = lab.import_file(
        "claims.csv",
        csv_bytes(
            f"{address},tls,protocol_versions,TLS1.3",
            f"{address},tls,certificate,ECDSA P-256",
            "10.0.0.9:8443,tls,certificate,RSA 2048",
            "10.0.0.9:8443,tls,key_exchange,X25519;P-256",
            "acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
        ),
    )
    plan_id = lab.ensure_plan(imp["id"])["id"]
    view = _view(lab, plan_id)
    assert view["structure_note"] == words.CSV_NOTE and view["state"] == "file_only"
    (service,) = view["services"]
    assert (service["title"], service["version"], service["sub"]) == (None, None, words.SERVICE_UNNAMED)
    # one box for each server and each signing program the claims name, titled with what the claim itself names
    program = next(c for c in imp["claims"] if c["location_kind"] == "software")
    assert [(b["key"], b["kind"], b["title"]) for b in service["boxes"]] == [
        (f"server:{address}", "server", address),
        ("server:10.0.0.9:8443", "server", "10.0.0.9:8443"),
        (f"software:{program['ref']}", "program", "acme-sign 1.4.2"),
    ]
    # the claims themselves say which algorithm is used where: nothing else does
    algorithms = {a["technical"]: a for a in view["algorithms"]}
    assert sorted(algorithms) == ["ECDSA P-256", "P-256", "RSA 2048", "X25519"]
    assert algorithms["ECDSA P-256"]["used"] == (
        f"Used in 2 places: the certificate on {address} and the signatures of acme-sign 1.4.2."
    )
    assert (
        algorithms["RSA 2048"]["plain"] == "Classical signatures"
        and algorithms["X25519"]["plain"] == "Classical key exchange"
    )
    assert W.lines(view, "uses") == {
        (f"server:{address}", "algorithm:ECDSA P-256", "uses", "its certificate"),
        (f"software:{program['ref']}", "algorithm:ECDSA P-256", "uses", "signs with"),
        ("server:10.0.0.9:8443", "algorithm:RSA 2048", "uses", "its certificate"),
        ("server:10.0.0.9:8443", "algorithm:X25519", "uses", "key exchange"),
        ("server:10.0.0.9:8443", "algorithm:P-256", "uses", "key exchange"),
    }
    assert W.lines(view, "ask") == {
        ("clients", f"server:{address}", "ask", "?"),
        ("clients", "server:10.0.0.9:8443", "ask", "?"),
    }
    spots = {s["key"]: s for s in W.box(view, "server:10.0.0.9:8443")["spots"]}
    assert spots["key_exchange"]["file_says"] == "The file says only X25519, P-256"
    assert [c["name"] for c in spots["key_exchange"]["checks"]] == ["The claim", "Post-quantum status"]
    # the panel's lines are the claims' own, with where each stands in the file
    panel = build.panel_of_plan(lab, plan_id, f"server:{address}")
    (lines,) = panel["file_lines"]
    assert lines["title"] == "The claims that name it" and [ln["where"] for ln in lines["lines"]] == [
        "line 2",
        "line 3",
    ]
    assert lines["lines"][0]["text"] == f"{address} accepts TLS 1.3 only"
    # no sentence says the file names no service as if that were read from it: the one note says how the map was drawn
    assert "service" not in {g["key"] for g in view["gaps"]["items"]}
    assert build.place_of_plan(lab, plan_id, f"claim:{program['id']}")["place"]["path"] == ["acme-sign 1.4.2", "Signs"]


def test_an_import_with_no_kept_copy_is_drawn_from_its_claims_alone_and_says_so(lab):
    # as a file was brought in before the app kept a copy of each (phase 5b): the claims, and no file beside them
    data = DEMO_CBOM.read_bytes()
    imp = lab._store(DEMO_CBOM.name, parse_file(DEMO_CBOM.name, data), is_demo=True)
    plan_id = lab.ensure_plan(imp["id"])["id"]
    view = _view(lab, plan_id)
    assert view["structure_note"] == words.NO_COPY_NOTE
    assert "before the app kept a copy" in view["structure_note"] and "claims alone" in view["structure_note"]
    (service,) = view["services"]
    assert service["title"] is None and service["sub"] == words.SERVICE_UNNAMED
    # the service's name and the endpoint's name were in the file, not in the claims: neither is drawn
    assert [(b["key"], b["title"]) for b in service["boxes"]] == [
        ("server:localhost:8443", "localhost:8443"),
        ("software:lib-acme-sign", "acme-sign 1.4.2"),
    ]
    (algorithm,) = view["algorithms"]
    assert algorithm["key"] == "algorithm:ECDSA P-256" and algorithm["used"].startswith("Used in 2 places: ")
    assert W.lines(view, "uses") == {
        ("server:localhost:8443", "algorithm:ECDSA P-256", "uses", "its certificate"),
        ("software:lib-acme-sign", "algorithm:ECDSA P-256", "uses", "signs with"),
    }
    # with the kept copy, the same file gives the names: the two maps differ only by what the copy adds
    kept = lab.import_demo()
    with_copy = _view(lab, lab.ensure_plan(kept["id"])["id"])
    assert with_copy["structure_note"] is None and with_copy["services"][0]["title"] is not None
    assert [len(b["spots"]) for b in W.boxes(with_copy)] == [len(b["spots"]) for b in W.boxes(view)]


def test_a_kept_copy_that_no_longer_matches_its_fingerprint_or_cannot_be_read_is_not_used(lab):
    data = DEMO_CBOM.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    found, note = build._structure(lab, 1, "cyclonedx-cbom", data, sha)
    assert found is not None and note is None and found.top is not None
    assert build._structure(lab, 1, "cyclonedx-cbom", data + b" ", sha) == (None, words.COPY_CHANGED_NOTE)
    assert build._structure(lab, 1, "cyclonedx-cbom", None, None) == (None, words.NO_COPY_NOTE)
    assert build._structure(lab, 1, "csv", b"location,type,claim,value\n", None) == (None, words.CSV_NOTE)
    broken = b'{"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []}'
    found, note = build._structure(lab, 2, "cyclonedx-cbom", broken, hashlib.sha256(broken).hexdigest())
    assert found is None and note.startswith(
        "The map is drawn from the file's claims alone, because its structure could not be read. "
    )
    assert "no cryptographic assets" in note  # the reader's own plain sentence


# ---------------------------------------------------------------- what another scanner file can say


def _asset(ref: str, name: str, kind: str, props: dict) -> dict:
    return {
        "type": "cryptographic-asset",
        "bom-ref": ref,
        "name": name,
        "cryptoProperties": {"assetType": kind, **props},
    }


OTHER = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "components": [
        {"type": "application", "bom-ref": "gateway", "name": "gateway", "version": "3.2"},
        {"type": "library", "bom-ref": "zlib", "name": "zlib", "version": "1.3"},
        {"type": "library", "bom-ref": "left-pad", "name": "left-pad", "version": "1.0"},
        _asset(
            "ecdsa",
            "ECDSA-P256",
            "algorithm",
            {"algorithmProperties": {"primitive": "signature", "curve": "secp256r1"}},
        ),
        _asset("sha", "SHA-256", "algorithm", {"algorithmProperties": {"primitive": "hash"}}),
        _asset("rsa", "RSA-2048", "algorithm", {"algorithmProperties": {"primitive": "signature"}}),
        _asset(
            "cert", "Front certificate", "certificate", {"certificateProperties": {"signatureAlgorithmRef": "ecdsa"}}
        ),
        _asset(
            "lost",
            "A certificate somewhere",
            "certificate",
            {"certificateProperties": {"signatureAlgorithmRef": "rsa"}},
        ),
    ],
    "services": [
        {"bom-ref": "front", "name": "Front door", "endpoints": ["https://front.example:8443"]},
        {"bom-ref": "queue", "name": "Queue"},
    ],
    "dependencies": [
        {"ref": "front", "dependsOn": ["cert", "gateway"]},
        {"ref": "gateway", "dependsOn": ["zlib"], "provides": ["ecdsa"]},
        {"ref": "ecdsa", "dependsOn": ["sha"]},
    ],
}


def test_a_scanner_file_that_names_the_software_of_its_endpoint_and_a_claim_on_no_system(lab):
    imp = lab.import_file("other.json", json.dumps(OTHER).encode())
    plan_id = lab.ensure_plan(imp["id"])["id"]
    view = _view(lab, plan_id)
    (service,) = view["services"]
    # the file names no top component: no box is drawn around the parts, and the map says the file names none
    assert service["title"] is None and "service" in {g["key"] for g in view["gaps"]["items"]}
    keys = {b["key"]: b for b in service["boxes"]}
    assert list(keys) == ["server:front.example:8443", "service:queue", "software:gateway"]
    assert keys["server:front.example:8443"]["title"] == "Front door"
    # a service with no address is a box with nothing to check; software with no cryptography is counted, not drawn
    assert (
        keys["service:queue"]["sub"] == "Service · no address in your scanner file"
        and keys["service:queue"]["spots"] == []
    )
    assert keys["service:queue"]["note"] == words.NO_CRYPTOGRAPHY_NAMED
    assert view["not_drawn"] == words.not_drawn(2) and "2 software components" in view["not_drawn"]
    # the file says the endpoint uses the gateway, so that line is drawn and "which software answers" is not a gap
    uses = W.lines(view, "uses")
    assert ("server:front.example:8443", "software:gateway", "uses", "uses") in uses
    assert "software" not in {g["key"] for g in view["gaps"]["items"]}
    assert ("server:front.example:8443", "algorithm:ecdsa", "uses", "its certificate") in uses
    assert ("software:gateway", "algorithm:ecdsa", "uses", "signs with") in uses
    assert ("algorithm:ecdsa", "algorithm:sha", "uses", "uses") in uses  # an algorithm the file builds on another
    assert len(uses) == 4
    algorithms = {a["technical"]: a for a in view["algorithms"]}
    assert algorithms["SHA-256"]["plain"] is None and algorithms["SHA-256"]["used"] == words.used_in([])
    assert algorithms["RSA 2048"]["uses"] == []  # its certificate is on no system the file names
    # the certificate the file puts nowhere: its claim is on no box, and the map says so with the way to Import
    unplaced = next(g for g in view["gaps"]["items"] if g["key"] == "unplaced")
    assert unplaced["text"].startswith("Where 1 claim applies.") and unplaced["link"] == {
        "page": "inventory/import",
        "item": None,
    }
    lost = next(c for c in imp["claims"] if c["location_kind"] == "unknown")
    assert build.place_of_plan(lab, plan_id, f"claim:{lost['id']}")["place"] is None
    assert sum(len(b["spots"]) for b in service["boxes"]) > 0
    # the program's box is the app's own system for it, so its panel has the Related block of that system
    panel = build.panel_of_plan(lab, plan_id, "software:gateway")
    assert panel["related_key"] == "system:software:gateway" and panel["title"] == "gateway 3.2"
    assert [g["key"] for g in panel["gaps"]["items"]] == ["libraries", "where"]
