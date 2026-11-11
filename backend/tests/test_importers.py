import copy
import json

import pytest

from app.config import DEMO_CBOM, DEMO_DIR
from app.importers import ImportFileError, parse_cbom, parse_csv, parse_file

DEMO = json.loads(DEMO_CBOM.read_text())


def cbom(mutate=None) -> bytes:
    doc = copy.deepcopy(DEMO)
    if mutate:
        mutate(doc)
    return json.dumps(doc).encode()


def comp(doc, ref):
    return next(c for c in doc["components"] if c.get("bom-ref") == ref)


def err(fn, data) -> ImportFileError:
    with pytest.raises(ImportFileError) as info:
        fn(data)
    assert info.value.message
    return info.value


# ------------------------------------------------------------------ demo CBOM

def test_demo_cbom_gives_exactly_the_three_answer_key_claims():
    claims = parse_cbom(DEMO_CBOM.read_bytes())
    expected = json.loads((DEMO_DIR / "expected.json").read_text())["verify"]
    assert [c.text for c in claims] == [e["claim"] for e in expected]
    v1, v2, v3 = claims
    assert (v1.kind, v1.location, v1.location_kind, v1.claimed_value) == ("protocol_versions", "localhost:8443", "server", "TLS 1.3")
    assert (v2.kind, v2.location, v2.claimed_value) == ("certificate", "localhost:8443", "ECDSA P-256")
    assert (v3.kind, v3.location, v3.location_kind, v3.claimed_value) == ("signature_algorithm", "acme-sign 1.4.2", "software", "ECDSA P-256")
    assert v3.detail == {"component": "acme-sign", "version": "1.4.2", "algorithm": "ECDSA P-256"}
    assert "proto-tls13" in v1.source and "components[" in v1.source


def test_demo_cbom_is_labelled_demo_data():
    props = {p["name"]: p["value"] for p in DEMO["metadata"]["properties"]}
    assert props["isogeny:demo-data"] == "true"
    assert "demo" in DEMO["metadata"]["component"]["name"].lower()


def test_location_falls_back_to_occurrence_when_no_service_link():
    def m(doc):
        doc["services"] = []
        doc["dependencies"] = [d for d in doc["dependencies"] if d["ref"] != "svc-token-signing"]
        comp(doc, "proto-tls13")["evidence"]["occurrences"] = [{"location": "localhost:9443"}]
    claims = parse_cbom(cbom(m))
    assert claims[0].location == "localhost:9443"
    assert claims[1].location == "localhost:8443"  # the certificate's own occurrence


def test_asset_without_location_is_kept_as_unknown_never_dropped():
    def m(doc):
        doc["services"] = []
        for ref in ("proto-tls13", "cert-server"):
            comp(doc, ref).pop("evidence")
    claims = parse_cbom(cbom(m))
    assert len(claims) == 3
    assert [c.location_kind for c in claims] == ["unknown", "unknown", "software"]
    assert claims[0].kind == "protocol_versions" and claims[1].kind == "certificate"


def test_file_path_occurrence_is_not_treated_as_an_address():
    def m(doc):
        doc["services"] = []
        comp(doc, "proto-tls13")["evidence"]["occurrences"] = [{"location": "src/main/Tls.java"}]
    assert parse_cbom(cbom(m))[0].location_kind == "unknown"


def test_signature_algorithm_used_only_by_loose_key_material_is_kept_as_unknown():
    def m(doc):
        doc["components"].append({"type": "cryptographic-asset", "bom-ref": "alg-rsa", "name": "RSA-2048",
                                  "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": {"primitive": "signature"}}})
        doc["components"].append({"type": "cryptographic-asset", "bom-ref": "loose-key", "name": "some key",
                                  "cryptoProperties": {"assetType": "related-crypto-material",
                                                       "relatedCryptoMaterialProperties": {"type": "public-key", "algorithmRef": "alg-rsa"}}})
        doc["dependencies"].append({"ref": "loose-key", "dependsOn": ["alg-rsa"]})
    claims = parse_cbom(cbom(m))
    assert len(claims) == 4
    assert (claims[3].ref, claims[3].location_kind, claims[3].kind, claims[3].claimed_value) == \
           ("alg-rsa", "unknown", "signature_algorithm", "RSA 2048")


def test_tls_without_a_version_is_kept_and_will_be_couldnt_check():
    claims = parse_cbom(cbom(lambda d: comp(d, "proto-tls13")["cryptoProperties"]["protocolProperties"].pop("version")))
    assert len(claims) == 3 and claims[0].claimed_value == "TLS (version not stated)"
    assert claims[0].detail["version_not_stated"] is True and claims[0].location == "localhost:8443"


def test_two_tls_versions_at_one_address_become_one_claim():
    def m(doc):
        extra = copy.deepcopy(comp(doc, "proto-tls13"))
        extra["bom-ref"] = "proto-tls12"
        extra["cryptoProperties"]["protocolProperties"]["version"] = "1.2"
        doc["components"].append(extra)
        next(d for d in doc["dependencies"] if d["ref"] == "svc-token-signing")["dependsOn"].append("proto-tls12")
    claims = parse_cbom(cbom(m))
    assert claims[0].text == "localhost:8443 accepts TLS 1.2 and TLS 1.3 only"
    assert len(claims) == 3


def test_unknown_software_and_other_library_names_are_just_data():
    def m(doc):
        comp(doc, "lib-acme-sign")["name"] = "../../etc/passwd"
        comp(doc, "lib-acme-sign")["version"] = "$(rm -rf /)"
    claim = parse_cbom(cbom(m))[2]
    assert claim.detail["component"] == "../../etc/passwd"
    assert claim.location_kind == "software"


@pytest.mark.parametrize("mutate,field", [
    (lambda d: d.pop("bomFormat"), "bomFormat"),
    (lambda d: d.update(bomFormat="SPDX"), "bomFormat"),
    (lambda d: d.pop("specVersion"), "specVersion"),
    (lambda d: d.update(specVersion="1.4"), "specVersion"),
    (lambda d: d.update(components={"a": 1}), "components"),
    (lambda d: d.update(components=[]), "components"),
    (lambda d: d["components"].__setitem__(1, "text"), "components[1]"),
    (lambda d: comp(d, "proto-tls13")["cryptoProperties"].update(assetType="magic"), "components[4].cryptoProperties.assetType"),
    (lambda d: comp(d, "proto-tls13").pop("cryptoProperties"), "components[4].cryptoProperties"),
    (lambda d: comp(d, "proto-tls13")["cryptoProperties"]["protocolProperties"].update(version="9.9"),
     "components[4].cryptoProperties.protocolProperties.version"),
    (lambda d: d["services"][0].update(endpoints=["https://localhost:99999"]), "services[0].endpoints[0]"),
    (lambda d: d["services"][0].update(endpoints=["https://localhost:0"]), "services[0].endpoints[0]"),
    (lambda d: d["services"][0].update(endpoints=["https://bad host:8443"]), "services[0].endpoints[0]"),
    (lambda d: d["services"][0].update(endpoints=[42]), "services[0].endpoints[0]"),
    (lambda d: d.update(services="nope"), "services"),
    (lambda d: d.update(dependencies=[{"dependsOn": ["x"]}]), "dependencies[0].ref"),
    (lambda d: d.update(dependencies=[{"ref": "a", "dependsOn": "x"}]), "dependencies[0].dependsOn"),
    (lambda d: comp(d, "cert-server").update({"bom-ref": "proto-tls13"}), "components[4].bom-ref"),
])
def test_broken_cbom_names_the_field(mutate, field):
    e = err(parse_cbom, cbom(mutate))
    assert e.field == field


def test_bad_port_in_occurrence_names_the_field():
    def m(doc):
        doc["services"] = []
        comp(doc, "proto-tls13")["evidence"]["occurrences"] = [{"location": "localhost:70000"}]
    e = err(parse_cbom, cbom(m))
    assert e.field == "components[4].evidence.occurrences[0].location" and "70000" in e.message


def test_json_syntax_error_names_the_line():
    e = err(parse_cbom, b'{\n  "bomFormat": "CycloneDX",\n  "specVersion": "1.6",,\n}')
    assert e.line == 3


@pytest.mark.parametrize("data", [b"", b"   \n", b"[1, 2]", b'"text"', b"\xff\xfe\x00bad", b"{" * 100000])
def test_not_a_cbom_at_all(data):
    e = err(parse_cbom, data)
    assert e.line is not None or e.field is not None


def test_cbom_without_crypto_assets():
    e = err(parse_cbom, json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6",
                                    "components": [{"type": "library", "name": "x"}]}).encode())
    assert e.field == "components"


def test_file_larger_than_1mb_is_refused():
    with pytest.raises(ImportFileError) as info:
        parse_file("big.json", b" " * (1024 * 1024 + 1))
    assert "1 MB" in info.value.message


def test_format_detection():
    assert parse_file("x.json", DEMO_CBOM.read_bytes()).format == "cyclonedx-cbom"
    assert parse_file("x.csv", (DEMO_DIR / "claims-template.csv").read_bytes()).format == "csv"
    assert parse_file("noextension", DEMO_CBOM.read_bytes()).format == "cyclonedx-cbom"
    assert parse_file("claims.txt", b"location,type,claim,value\nlocalhost:1,tls,certificate,RSA 2048\n").format == "csv"
    with pytest.raises(ImportFileError) as info:
        parse_file("photo.png", b"\x89PNG....")
    assert info.value.field == "filename"


# ------------------------------------------------------------------ CSV template

def test_csv_template_gives_the_same_three_claims_as_the_demo_cbom():
    a = parse_csv((DEMO_DIR / "claims-template.csv").read_bytes())
    b = parse_cbom(DEMO_CBOM.read_bytes())
    assert [(c.kind, c.location, c.claimed_value, c.text, c.detail) for c in a] == \
           [(c.kind, c.location, c.claimed_value, c.text, c.detail) for c in b]
    assert [c.source for c in a] == ["line 2", "line 3", "line 4"]


def test_csv_accepts_spaces_blank_lines_and_several_values():
    data = b"location, type, claim, value\n\n localhost:8443 , tls , protocol_versions , TLS1.2;TLSv1.3\n" \
           b"10.0.0.5:443,tls,key_exchange,x25519;secp256r1\n" \
           b"[::1]:8443,tls,cipher_suites,TLS_AES_128_GCM_SHA256;ECDHE-ECDSA-AES128-SHA\n"
    claims = parse_csv(data)
    assert claims[0].detail["versions"] == ["TLS 1.2", "TLS 1.3"]
    assert claims[0].text == "localhost:8443 accepts TLS 1.2 and TLS 1.3 only"
    assert claims[1].detail["suites"] == ["TLS_AES_128_GCM_SHA256", "ECDHE-ECDSA-AES128-SHA"]
    assert claims[1].location == "[::1]:8443"
    assert claims[2].detail["groups"] == ["X25519", "P-256"]


@pytest.mark.parametrize("body,line,field", [
    (b"where,type,claim,value\nlocalhost:1,tls,certificate,RSA 2048\n", 1, "header"),
    (b"location,type,claim\nlocalhost:1,tls,certificate\n", 1, "header"),
    (b"localhost:8443,tls,protocol_versions,TLS1.3\n", 1, "header"),
    (b"location,type,claim,value\n", 2, None),
    (b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions\n", 2, None),
    (b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions,TLS1.3,extra\n", 2, None),
    (b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions,TLS1.3\nlocalhost:8443,ssh,protocol_versions,2\n", 3, "type"),
    (b"location,type,claim,value\nlocalhost:8443,tls,signature_algorithm,ECDSA P-256\n", 2, "claim"),
    (b"location,type,claim,value\nacme-sign 1.4.2,software,certificate,ECDSA P-256\n", 2, "claim"),
    (b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions,SSL3\n", 2, "value"),
    (b"location,type,claim,value\nlocalhost:8443,tls,protocol_versions,\n", 2, "value"),
    (b"location,type,claim,value\nlocalhost:8443,tls,certificate,Quantum 9000\n", 2, "value"),
    (b"location,type,claim,value\nlocalhost:8443,tls,key_exchange,kyber\n", 2, "value"),
    (b"location,type,claim,value\nlocalhost:8443,tls,cipher_suites,AES 128!\n", 2, "value"),
    (b"location,type,claim,value\nlocalhost:99999,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\nlocalhost,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\n-connect:443,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\na b:443,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\nx;rm:443,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\n../:443,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b"location,type,claim,value\nacme-sign,software,signature_algorithm,ECDSA P-256\n", 2, "location"),
    (b"location,type,claim,value\n,tls,protocol_versions,TLS1.3\n", 2, "location"),
    (b'location,type,claim,value\nlocalhost:1,tls,certificate,"RSA 2048\n', 2, None),
    (b"location,type,claim,value\n\n\nlocalhost:8443,tls,protocol_versions,TLS9\n", 4, "value"),
    (b"\xff\xfelocation", 1, None),
    (b"", 1, None),
])
def test_broken_csv_names_the_line(body, line, field):
    e = err(parse_csv, body)
    assert e.line == line
    assert e.field == field
