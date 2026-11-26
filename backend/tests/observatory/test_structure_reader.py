"""The reader of a scanner file's structure (the Observatory's map): what it takes from the demo file, checked against
the file itself; which references it follows and where the walk stops; and that it refuses what the claim reader
refuses, in the same words, and a file with more references than it reads. The file is data: nothing in it runs."""

from __future__ import annotations

import copy
import json

import pytest

from app.config import DEMO_CBOM
from app.importer import structure as S
from app.importer.cbom import read_cbom
from app.importer.common import ImportFileError

DEMO = json.loads(DEMO_CBOM.read_text())


def cbom(mutate=None) -> bytes:
    doc = copy.deepcopy(DEMO)
    if mutate:
        mutate(doc)
    return json.dumps(doc).encode()


def refusal(data: bytes) -> str:
    with pytest.raises(ImportFileError) as info:
        S.read_structure(data)
    assert info.value.message and "\n" not in info.value.message
    return info.value.message


# ---------------------------------------------------------------- the demo file, against the file itself


def test_the_demo_file_gives_the_service_its_endpoint_its_program_and_its_assets():
    found = S.read_structure(DEMO_CBOM.read_bytes())
    described = DEMO["metadata"]["component"]
    assert found.top is not None
    assert (found.top.key, found.top.name, found.top.version, found.top.where) == (
        described["bom-ref"],
        described["name"],
        described["version"],
        "metadata.component",
    )
    # one service, with the one endpoint the file gives it, as host:port
    (service,) = found.services
    assert (service.key, service.name) == (DEMO["services"][0]["bom-ref"], DEMO["services"][0]["name"])
    assert service.endpoints == tuple(DEMO["services"][0]["endpoints"]) == ("https://localhost:8443",)
    assert service.addresses == ("localhost:8443",)
    # every component that is no cryptographic asset is software; every other one an asset of its kind
    software = [c for c in DEMO["components"] if c["type"] != "cryptographic-asset"]
    assert (
        [(p.key, p.name, p.version, p.type) for p in found.software]
        == [(c["bom-ref"], c["name"], c["version"], c["type"]) for c in software]
        == [("lib-acme-sign", "acme-sign", "1.4.2", "library")]
    )
    assets = [c for c in DEMO["components"] if c["type"] == "cryptographic-asset"]
    assert [(a.key, a.kind) for a in found.assets] == [
        (c["bom-ref"], c["cryptoProperties"]["assetType"]) for c in assets
    ]
    algorithm = next(a for a in found.assets if a.kind == S.ALGORITHM)
    assert (algorithm.algorithm, algorithm.primitive) == ("ECDSA P-256", "signature")
    assert next(a for a in found.assets if a.kind == S.PROTOCOL).protocol == "TLS 1.3"
    assert found.refs == {key: key for key in [service.key, found.top.key, *(c["bom-ref"] for c in DEMO["components"])]}


def test_every_reference_kept_is_one_the_file_states_and_every_one_the_file_states_is_kept():
    found = S.read_structure(DEMO_CBOM.read_bytes())
    stated = set()
    for n, dep in enumerate(DEMO["dependencies"]):
        for how in ("dependsOn", "provides"):
            for target in dep.get(how, []):
                stated.add((dep["ref"], target, how, f"dependencies[{n}]"))
    for n, comp in enumerate(DEMO["components"]):
        props = comp.get("cryptoProperties") or {}
        for target in (props.get("protocolProperties") or {}).get("cryptoRefArray", []):
            stated.add((comp["bom-ref"], target, "cryptoRefArray", f"components[{n}]"))
        for how in ("signatureAlgorithmRef", "subjectPublicKeyRef"):
            if how in (props.get("certificateProperties") or {}):
                stated.add((comp["bom-ref"], props["certificateProperties"][how], how, f"components[{n}]"))
        if "algorithmRef" in (props.get("relatedCryptoMaterialProperties") or {}):
            stated.add(
                (
                    comp["bom-ref"],
                    props["relatedCryptoMaterialProperties"]["algorithmRef"],
                    "algorithmRef",
                    f"components[{n}]",
                )
            )
    assert {(e.source, e.target, e.how, e.where) for e in found.edges} == stated and len(found.edges) == len(stated)


def test_the_certificate_and_the_program_both_use_the_one_algorithm_and_nothing_else_does():
    found = S.read_structure(DEMO_CBOM.read_bytes())
    assert found.uses == [
        S.Use(S.SERVICE, "svc-token-signing", "alg-ecdsa-p256", S.THROUGH_CERTIFICATE),
        S.Use(S.SOFTWARE, "lib-acme-sign", "alg-ecdsa-p256", S.THROUGH_SIGNATURE),
    ]
    # what the file's references lead to from each place, nearest first
    assert found.reached == {
        (S.SERVICE, "svc-token-signing"): ["proto-tls13", "cert-server", "alg-ecdsa-p256", "key-server-cert-public"],
        (S.SOFTWARE, "lib-acme-sign"): ["alg-ecdsa-p256"],
    }
    # the lines of the file that name the service: its own entry, and the two `dependencies` lines that name it
    assert [where for where, _ in found.lines["svc-token-signing"]] == [
        "services[0]",
        "dependencies[0]",
        "dependencies[1]",
    ]
    assert json.loads(found.lines["svc-token-signing"][2][1]) == {
        "ref": "svc-token-signing",
        "dependsOn": ["proto-tls13", "cert-server"],
    }
    assert all(len(text) <= S.LINE_LIMIT for lines in found.lines.values() for _, text in lines)


# ---------------------------------------------------------------- small files written here


def _small(components: list[dict], dependencies: list[dict], services: list[dict] | None = None, top=True) -> bytes:
    doc = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": components, "dependencies": dependencies}
    if services is not None:
        doc["services"] = services
    if top:
        doc["metadata"] = {"component": {"type": "application", "bom-ref": "app", "name": "Shop", "version": "2"}}
    return json.dumps(doc).encode()


def _algorithm(ref: str, name: str, primitive: str) -> dict:
    return {
        "type": "cryptographic-asset",
        "bom-ref": ref,
        "name": name,
        "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": {"primitive": primitive}},
    }


TLS = {
    "type": "cryptographic-asset",
    "bom-ref": "tls",
    "name": "TLS 1.3",
    "cryptoProperties": {
        "assetType": "protocol",
        "protocolProperties": {
            "type": "tls",
            "version": "1.3",
            "cipherSuites": [{"name": "TLS_AES_128_GCM_SHA256", "algorithms": ["aes"]}],
        },
    },
}


def test_how_a_place_uses_an_algorithm_is_read_from_the_last_certificate_or_protocol_on_the_way():
    found = S.read_structure(
        _small(
            [
                {"type": "library", "bom-ref": "lib", "name": "signer", "version": "1"},
                {"type": "library", "bom-ref": "other", "name": "unused", "version": "9"},
                _algorithm("ecdsa", "ECDSA-P256", "signature"),
                _algorithm("kem", "ML-KEM-768", "kem"),
                _algorithm("aes", "AES-128-GCM", "ae"),
                _algorithm("sha", "SHA-256", "hash"),
                TLS,
            ],
            [
                {"ref": "svc", "dependsOn": ["tls", "lib", "no-such-ref"]},
                {"ref": "lib", "provides": ["ecdsa", "kem", "sha"]},
                {"ref": "ecdsa", "dependsOn": ["sha"]},
                {"ref": "no-such-ref", "dependsOn": ["ecdsa"]},
            ],
            [
                {
                    "bom-ref": "svc",
                    "name": "Front door",
                    "endpoints": ["https://shop.example:8443", "http://shop.example/"],
                }
            ],
        )
    )
    # an http endpoint is no address the app would connect to; the https one is
    assert found.services[0].addresses == ("shop.example:8443",)
    assert found.uses == [
        S.Use(S.SERVICE, "svc", "aes", S.THROUGH_PROTOCOL),  # through its TLS cipher suite
        S.Use(S.SOFTWARE, "lib", "ecdsa", S.THROUGH_SIGNATURE),
        S.Use(S.SOFTWARE, "lib", "kem", S.THROUGH_KEY_EXCHANGE),
        S.Use(S.SOFTWARE, "lib", "sha", S.THROUGH_DIRECT),
    ]
    # the walk never passes through another part: the service names the library, but does not use ECDSA itself
    assert not [u for u in found.uses if u.place == "svc" and u.algorithm == "ecdsa"]
    # ... and stops at an algorithm: the library's use of SHA-256 is its own line, not one through ECDSA
    assert ("svc", "lib", "dependsOn") in {(e.source, e.target, e.how) for e in found.edges}
    assert ("ecdsa", "sha", "dependsOn") in {(e.source, e.target, e.how) for e in found.edges}
    # a reference to something the file does not hold is not kept
    assert not [e for e in found.edges if "no-such-ref" in (e.source, e.target)]


def test_an_asset_seen_at_an_address_is_used_there_only_when_no_service_reaches_it():
    cert = {
        "type": "cryptographic-asset",
        "bom-ref": "cert",
        "name": "A certificate",
        "cryptoProperties": {"assetType": "certificate", "certificateProperties": {"signatureAlgorithmRef": "rsa"}},
        "evidence": {"occurrences": [{"location": "10.0.0.5:443"}, {"location": "/etc/ssl/cert.pem"}]},
    }
    alone = S.read_structure(_small([cert, _algorithm("rsa", "RSA-2048", "signature")], []))
    assert alone.uses == [S.Use(S.ADDRESS, "10.0.0.5:443", "rsa", S.THROUGH_CERTIFICATE)]
    reached = S.read_structure(
        _small(
            [cert, _algorithm("rsa", "RSA-2048", "signature")],
            [{"ref": "svc", "dependsOn": ["cert"]}],
            [{"bom-ref": "svc", "name": "Front door", "endpoints": ["front.example:443"]}],
        )
    )
    assert reached.uses == [S.Use(S.SERVICE, "svc", "rsa", S.THROUGH_CERTIFICATE)]


def test_a_part_without_a_bom_ref_is_named_by_its_place_and_a_file_without_a_top_component_has_none():
    found = S.read_structure(
        _small(
            [{"type": "library", "name": "nameless"}, _algorithm("ecdsa", "ECDSA-P256", "signature")],
            [],
            [{"name": "No ref", "endpoints": []}],
            top=False,
        )
    )
    assert found.top is None
    assert [(p.key, p.where) for p in found.software] == [("components[0]", "components[0]")]
    assert [(p.key, p.addresses) for p in found.services] == [("services[0]", ())]
    # a component listed inside another is a reference of the file too
    nested = S.read_structure(
        _small(
            [
                {
                    "type": "application",
                    "bom-ref": "outer",
                    "name": "outer",
                    "components": [_algorithm("ecdsa", "ECDSA-P256", "signature")],
                }
            ],
            [{"ref": "outer", "provides": ["ecdsa"]}],
        )
    )
    assert ("outer", "ecdsa", "contains", "components[0].components[0]") in {
        (e.source, e.target, e.how, e.where) for e in nested.edges
    }
    assert nested.uses == [S.Use(S.SOFTWARE, "outer", "ecdsa", S.THROUGH_SIGNATURE)]


def test_what_the_file_says_is_kept_as_text_and_shortened():
    long = "x" * 5000

    def mutate(doc):
        doc["metadata"]["component"]["name"] = "Shop\n\x00<script>alert(1)</script> " + long
        doc["metadata"]["component"]["version"] = long
        doc["services"][0]["name"] = ["not", "text"]
        doc["components"][0]["version"] = 7

    found = S.read_structure(cbom(mutate))
    assert found.top is not None and len(found.top.name) <= 100 and "\n" not in found.top.name
    assert "\x00" not in found.top.name and found.top.name.startswith("Shop <script>")  # text, shown as text
    assert found.top.version is not None and len(found.top.version) <= 50
    assert found.services[0].name == "(no name)" and found.software[0].version is None
    assert all(len(text) <= S.LINE_LIMIT for lines in found.lines.values() for _, text in lines)


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"{ not json",
        b"[]",
        json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.4", "components": []}).encode(),
        cbom(lambda d: d.update(components=[c for c in d["components"] if c["type"] != "cryptographic-asset"])),
        cbom(lambda d: d["services"][0].update(endpoints=["https://localhost:99999"])),
        cbom(lambda d: d.update(dependencies="none")),
        b"x" * (1024 * 1024 + 1),
    ],
)
def test_what_the_claim_reader_refuses_is_refused_here_in_the_same_words(data):
    with pytest.raises(ImportFileError) as wanted:
        read_cbom(data)
    assert refusal(data) == wanted.value.message


def test_a_file_with_more_references_or_services_than_the_reader_takes_is_refused_plainly(monkeypatch):
    assert "more than" in refusal(
        cbom(lambda d: d.update(services=[{"name": f"s{n}"} for n in range(S.MAX_SERVICES + 1)]))
    )
    monkeypatch.setattr(S, "MAX_REFERENCES", 5)
    assert refusal(DEMO_CBOM.read_bytes()) == S.TOO_MANY
    monkeypatch.setattr(S, "MAX_REFERENCES", 50_000)
    monkeypatch.setattr(S, "MAX_STEPS", 3)
    assert refusal(DEMO_CBOM.read_bytes()) == S.TOO_MANY


def test_references_that_go_round_in_a_ring_end_the_walk():
    found = S.read_structure(
        _small(
            [
                {"type": "library", "bom-ref": "lib", "name": "signer", "version": "1"},
                _algorithm("ecdsa", "ECDSA-P256", "signature"),
                {
                    "type": "cryptographic-asset",
                    "bom-ref": "key",
                    "name": "A key",
                    "cryptoProperties": {
                        "assetType": "related-crypto-material",
                        "relatedCryptoMaterialProperties": {"type": "public-key", "algorithmRef": "ecdsa"},
                    },
                },
            ],
            [{"ref": "lib", "dependsOn": ["key", "lib"]}, {"ref": "key", "dependsOn": ["key", "ecdsa"]}],
        )
    )
    assert found.uses == [S.Use(S.SOFTWARE, "lib", "ecdsa", S.THROUGH_KEY)]
