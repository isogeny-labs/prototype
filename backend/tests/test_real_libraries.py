"""Real libraries as test subjects (phase 4c): the fixed registry, its exact pins, the names and the import, the programs a
file names and the tests suggested for each. No Docker, no network: this reads tables and the pinned files on disk."""
import base64
import json
import re
from urllib.parse import urlsplit

import pytest

from app.run import components
from app.evidence import export as evidence_export
from app import real_libraries
from app.config import DEMO_DIR
from app.importer.common import ImportFileError
from app.importer.csv_file import parse_csv
from app.names import normalize_algorithm
from app.engine.research import CannotDesign, RuleEngine, programs
from conftest import csv_bytes

REAL_CSV = (DEMO_DIR / "real-libraries.csv").read_bytes()
HEX64 = re.compile(r"[0-9a-f]{64}")


def claims_of(parsed) -> list[dict]:
    """ParsedClaim objects as the claim dicts the research engine takes."""
    return [{"ref": c.ref, "location": c.location, "location_kind": c.location_kind, "kind": c.kind,
             "claimed_value": c.claimed_value, "detail": c.detail} for c in parsed]


def real_claims() -> list[dict]:
    return claims_of(parse_csv(REAL_CSV))


# ---------------------------------------------------------------- the registry

def test_exactly_four_libraries_with_their_versions():
    assert list(real_libraries.LIBRARIES) == ["openjdk", "python-ecdsa", "elliptic", "openssl"]
    assert {n: lib["versions"] for n, lib in real_libraries.LIBRARIES.items()} == {
        "openjdk": ["17.0.2", "17.0.3"], "python-ecdsa": ["0.13.2", "0.13.3"], "elliptic": ["6.5.6", "6.5.7"], "openssl": ["3.5.9"]}
    assert set(real_libraries.FAMILIES) == {"openssl", "java", "python-ecdsa", "elliptic"}
    assert {lib["family"] for lib in real_libraries.LIBRARIES.values()} == set(real_libraries.FAMILIES)


def test_the_registry_answers_exactly_for_registered_names_and_versions():
    assert real_libraries.library("openjdk", "17.0.2") is real_libraries.LIBRARIES["openjdk"]
    assert [real_libraries.family_of(n, v) for n, v in (("openjdk", "17.0.2"), ("openjdk", "17.0.3"), ("python-ecdsa", "0.13.2"),
                                                       ("elliptic", "6.5.7"), ("openssl", "3.5.9"))] == \
        ["java", "java", "python-ecdsa", "elliptic", "openssl"]
    assert real_libraries.fixed_version("openjdk", "17.0.2") == "17.0.3"
    assert real_libraries.fixed_version("python-ecdsa", "0.13.2") == "0.13.3"
    assert real_libraries.fixed_version("elliptic", "6.5.6") == "6.5.7"
    assert real_libraries.fixed_version("openjdk", "17.0.3") is None      # already the fixed one
    assert real_libraries.fixed_version("openssl", "3.5.9") is None
    assert [a["id"] for a in real_libraries.advisories("openjdk", "17.0.2")] == ["CVE-2022-21449"]
    assert [a["id"] for a in real_libraries.advisories("python-ecdsa", "0.13.2")] == ["CVE-2019-14859", "CVE-2019-14853"]
    assert [a["id"] for a in real_libraries.advisories("elliptic", "6.5.6")] == ["CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"]
    assert real_libraries.advisories("openjdk", "17.0.3") == [] and real_libraries.advisories("openssl", "3.5.9") == []
    assert real_libraries.offers("openssl", "3.5.9", "ML-DSA-65") and real_libraries.offers("openssl", "3.5.9", "ML-KEM-768")
    assert real_libraries.offers("openjdk", "17.0.2", "ECDSA P-256") and not real_libraries.offers("openjdk", "17.0.2", "ML-DSA-65")
    assert real_libraries.subject_key("openjdk", "17.0.2") == "openjdk-17.0.2"
    with pytest.raises(ValueError):
        real_libraries.subject_key("openjdk", "9.9")


@pytest.mark.parametrize("name, version", [
    ("openjdk", "17.0.9"), ("openjdk", ""), ("openjdk ", "17.0.2"), (" openjdk", "17.0.2"), ("openjdk", "17.0.2 "), ("OpenJDK", "17.0.2"),
    ("../x", "17.0.2"), ("openjdk", "../x"), ("../openjdk", "17.0.2"), ("openjdk/../openssl", "3.5.9"), ("acme-sign", "9.9"),
    (None, "17.0.2"), ("openjdk", None), (17, "17.0.2"), ("openjdk", 17), (["openjdk"], "17.0.2"), ("openjdk", ["17.0.2"]),
])
def test_anything_not_exactly_registered_is_nothing(name, version):
    assert real_libraries.library(name, version) is None
    assert real_libraries.family_of(name, version) is None
    assert real_libraries.fixed_version(name, version) is None
    assert real_libraries.advisories(name, version) == []
    assert real_libraries.offers(name, version, "ECDSA P-256") is False
    assert components.kind_of(name, version) is None


def test_the_family_of_a_subject_key_including_its_controls():
    assert real_libraries.family_of_subject("openjdk-17.0.2") == "java"
    assert real_libraries.family_of_subject("control-slow:openjdk-17.0.3") == "java"
    assert real_libraries.family_of_subject("python-ecdsa-0.13.2") == "python-ecdsa"
    assert real_libraries.family_of_subject("elliptic-6.5.7") == "elliptic"
    assert real_libraries.family_of_subject("control-slow:openssl-3.5.9") == "openssl"
    for key in ("acme-sign-1.4.2", "openjdk-17.0.9", "openjdk", "", "control-accept-all", "../openjdk-17.0.2", "openjdk-17.0.2 "):
        assert real_libraries.family_of_subject(key) is None, key


def test_what_a_program_is_to_this_app():
    assert components.kind_of("acme-sign", "1.4.2") == "demo"
    assert components.kind_of("acme-sign", "1.4.3") == "demo"
    assert components.kind_of("openjdk", "17.0.2") == "real"
    assert components.kind_of("openssl", "3.5.9") == "real"
    assert components.kind_of("acme-sign", "9.9") is None
    assert components.lookup("openjdk", "17.0.2") is None and components.lookup("openssl", "3.5.9") is None   # a real library is never a local file
    assert components.component_key("openjdk", "17.0.2") == "openjdk-17.0.2"
    assert components.component_key("acme-sign", "1.4.3") == "acme-sign-1.4.3"
    with pytest.raises(ValueError):
        components.component_key("acme-sign", "9.9")


def test_the_versions_a_retest_can_choose_between():
    assert components.versions_of("acme-sign") == ["1.4.2", "1.4.3"]
    assert components.versions_of("openjdk") == ["17.0.2", "17.0.3"]
    assert components.versions_of("python-ecdsa") == ["0.13.2", "0.13.3"]
    assert components.versions_of("elliptic") == ["6.5.6", "6.5.7"]
    assert components.versions_of("openssl") == ["3.5.9"]
    assert components.versions_of("nope") == [] and components.versions_of(None) == [] and components.versions_of(5) == []
    components.versions_of("openjdk").append("x")       # a copy: nobody can add to the registry through it
    assert components.versions_of("openjdk") == ["17.0.2", "17.0.3"]


# ---------------------------------------------------------------- every pin is exact

def _images():
    return [(family, name, ref) for family, pins in real_libraries.FAMILIES.items() for name, ref in pins["images"].items()]


def test_every_image_is_pinned_by_digest_never_by_a_bare_tag():
    found = _images()
    assert {f for f, _, _ in found} == {"openssl", "java", "elliptic"}      # python-ecdsa copies pure Python files only
    for family, name, ref in found:
        assert re.search(r"@sha256:[0-9a-f]{64}$", ref), (family, name, ref)
        assert ":" not in ref.split("@")[0], ref                         # no tag next to the digest


def test_every_download_has_a_fixed_https_address_and_a_fingerprint():
    downloads = [d for pins in real_libraries.FAMILIES.values() for d in pins["downloads"]]
    assert len(downloads) == 2 + 9
    for pin in downloads:
        url = urlsplit(pin["url"])
        assert url.scheme == "https" and url.hostname in ("files.pythonhosted.org", "registry.npmjs.org"), pin["file"]
        assert pin["url"].endswith(pin["file"]) and "/" not in pin["file"] and ".." not in pin["file"]
        assert ("sha256" in pin) != ("sha512_base64" in pin), pin["file"]       # exactly one kind of fingerprint
        if "sha256" in pin:
            assert HEX64.fullmatch(pin["sha256"]), pin["file"]
        else:
            assert len(base64.b64decode(pin["sha512_base64"], validate=True)) == 64, pin["file"]


def test_elliptic_has_both_versions_and_exactly_seven_dependencies():
    files = [d["file"] for d in real_libraries.FAMILIES["elliptic"]["downloads"]]
    assert "elliptic-6.5.6.tgz" in files and "elliptic-6.5.7.tgz" in files
    assert len([f for f in files if not f.startswith("elliptic-")]) == 7 and len(files) == 9
    assert [d["file"] for d in real_libraries.FAMILIES["python-ecdsa"]["downloads"]] == \
        ["ecdsa-0.13.2-py2.py3-none-any.whl", "ecdsa-0.13.3-py2.py3-none-any.whl"]
    assert len(real_libraries.FAMILIES["java"]["images"]) == 2        # the affected and the fixed Java


def test_every_family_has_its_wrapper_folder_and_a_table_that_names_its_libraries():
    for family in real_libraries.FAMILIES:
        folder = real_libraries.REAL_DIR / family
        assert (folder / "Dockerfile").is_file(), family
        table = json.loads((folder / "subjects.json").read_text())
        assert isinstance(table, dict) and table
        assert all(isinstance(v, list) and v and all(isinstance(a, str) and a for a in v) for v in table.values())
        for name, lib in real_libraries.LIBRARIES.items():
            if lib["family"] == family:
                for version in lib["versions"]:
                    assert f"{name}-{version}" in table and f"control-slow:{name}-{version}" in table
    assert {"control-pq-wrong-answer", "control-pq-skip-key-check"} <= set(json.loads((real_libraries.REAL_DIR / "openssl" / "subjects.json").read_text()))


# ---------------------------------------------------------------- advisories

def test_every_advisory_has_an_https_link_the_report_may_carry():
    assert set(real_libraries.ADVISORY_LINKS) <= set(evidence_export.REPORT_LINKS)
    for cve, advisory in real_libraries.ADVISORIES.items():
        assert advisory["url"].startswith("https://") and advisory["url"] in evidence_export.REPORT_LINKS, cve
        assert advisory["text"] and advisory["covered"] and advisory["link"]
    named = {cve for lib in real_libraries.LIBRARIES.values() for cves in lib["advisories"].values() for cve in cves}
    assert named <= set(real_libraries.ADVISORIES)
    for lib in real_libraries.LIBRARIES.values():          # an advisory is about a version the library really has
        assert set(lib["advisories"]) <= set(lib["versions"]) and set(lib["fixed_in"]) <= set(lib["versions"])


# ---------------------------------------------------------------- names and the import

@pytest.mark.parametrize("spelled, normal", [("ML-DSA-65", "ML-DSA-65"), ("mldsa65", "ML-DSA-65"), ("ML-KEM-768", "ML-KEM-768"),
                                             ("MLKEM768", "ML-KEM-768"), ("ml_kem_768", "ML-KEM-768")])
def test_post_quantum_names_are_recognised(spelled, normal):
    assert normalize_algorithm(spelled) == normal


@pytest.mark.parametrize("spelled", ["ML-DSA-99", "ML-KEM-65", "ML-DSA-768", "ML-KEM-44", "ML-DSA", "MLDSA"])
def test_a_post_quantum_name_that_does_not_exist_is_nothing(spelled):
    assert normalize_algorithm(spelled) is None


def test_the_csv_accepts_a_key_exchange_claim_for_software_and_still_refuses_other_names():
    (claim,) = parse_csv(csv_bytes("openssl 3.5.9,software,key_exchange,ML-KEM-768"))
    assert (claim.kind, claim.location_kind, claim.location, claim.claimed_value) == ("key_exchange", "software", "openssl 3.5.9", "ML-KEM-768")
    assert claim.detail == {"component": "openssl", "version": "3.5.9", "algorithm": "ML-KEM-768"}
    with pytest.raises(ImportFileError) as info:
        parse_csv(csv_bytes("openssl 3.5.9,software,cipher_suites,TLS_AES_128_GCM_SHA256"))
    assert "can't be used with type software" in info.value.message and info.value.line == 2
    with pytest.raises(ImportFileError) as info:
        parse_csv(csv_bytes("openssl 3.5.9,software,made_up_claim,ML-KEM-768"))
    assert "made_up_claim" in info.value.message and info.value.field == "claim"


def test_the_real_libraries_file_reads_as_six_software_claims():
    claims = real_claims()
    assert len(claims) == 6 and {c["location_kind"] for c in claims} == {"software"}
    assert sorted(c["kind"] for c in claims) == ["key_exchange"] + ["signature_algorithm"] * 5


# ---------------------------------------------------------------- programs and suggested tests

def test_the_real_libraries_file_names_six_programs():
    found = programs(real_claims())
    assert [p["label"] for p in found] == ["openjdk 17.0.2", "python-ecdsa 0.13.2", "elliptic 6.5.6", "openssl 3.5.9 (ECDSA P-256)",
                                           "openssl 3.5.9 (ML-DSA-65)", "openssl 3.5.9 (ML-KEM-768)"]
    assert [p["role"] for p in found] == ["signing"] * 5 + ["key_exchange"]
    assert [p["algorithm"] for p in found] == ["ECDSA P-256"] * 4 + ["ML-DSA-65", "ML-KEM-768"]
    assert all({"ref", "component", "version", "algorithm", "label", "role"} <= set(p) for p in found)
    assert len({p["ref"] for p in found}) == 6


def test_fifteen_tests_are_suggested_for_the_six_programs():
    claims = real_claims()
    proposal = RuleEngine().propose_tests(claims)
    assert proposal["not_suggested"] == []
    tests = proposal["tests"]
    assert len(tests) == 15
    by_label = {}
    for p in programs(claims):
        by_label[p["label"]] = [t["kind"] for t in tests if t["target"]["claim"] == p["ref"]]
    ecdsa = ["official_vectors", "bad_signatures", "speed_size"]
    assert by_label == {"openjdk 17.0.2": ecdsa, "python-ecdsa 0.13.2": ecdsa, "elliptic 6.5.6": ecdsa, "openssl 3.5.9 (ECDSA P-256)": ecdsa,
                        "openssl 3.5.9 (ML-DSA-65)": ["mldsa_vectors", "speed_size"], "openssl 3.5.9 (ML-KEM-768)": ["mlkem_vectors"]}
    assert all(t["target"]["kind"] == "software" for t in tests)         # no server in this file
    assert {t["target"]["algorithm"] for t in tests if t["kind"] == "mlkem_vectors"} == {"ML-KEM-768"}
    assert {t["target"]["algorithm"] for t in tests if t["kind"] == "mldsa_vectors"} == {"ML-DSA-65"}


def test_a_file_with_two_versions_of_one_demo_program_is_as_it_was():
    claims = claims_of(parse_csv(csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
                                           "acme-sign 9.9,software,signature_algorithm,ECDSA P-256")))
    found = programs(claims)
    assert [p["label"] for p in found] == ["acme-sign 1.4.2", "acme-sign 9.9"]          # no algorithm in the label
    assert [p["role"] for p in found] == ["signing", "signing"]
    tests = RuleEngine().propose_tests(claims)["tests"]
    assert [t["kind"] for t in tests] == ["official_vectors", "bad_signatures", "speed_size"] * 2
    assert [t["target"]["claim"] for t in tests] == [found[0]["ref"]] * 3 + [found[1]["ref"]] * 3


def test_a_software_key_exchange_for_another_algorithm_is_not_a_program():
    claims = claims_of(parse_csv(csv_bytes("acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256",
                                           "acme-sign 1.4.2,software,key_exchange,X25519")))
    assert [(p["label"], p["role"]) for p in programs(claims)] == [("acme-sign 1.4.2", "signing")]
    assert [t["kind"] for t in RuleEngine().propose_tests(claims)["tests"]] == ["official_vectors", "bad_signatures", "speed_size"]
    only = claims_of(parse_csv(csv_bytes("acme-sign 1.4.2,software,key_exchange,X25519")))
    assert programs(only) == [] and RuleEngine().propose_tests(only)["tests"] == []


def test_a_test_that_does_not_fit_the_program_is_refused():
    claims = real_claims()
    by_label = {p["label"]: p["ref"] for p in programs(claims)}
    engine = RuleEngine()

    def ask(kind, label):
        return engine.design_test({"catalog_id": kind, "claims": claims, "target": by_label[label]})

    for kind, label in (("official_vectors", "openssl 3.5.9 (ML-DSA-65)"), ("bad_signatures", "openssl 3.5.9 (ML-DSA-65)"),
                        ("mldsa_compare", "openssl 3.5.9 (ML-DSA-65)"), ("mlkem_vectors", "openjdk 17.0.2"),
                        ("mldsa_vectors", "openjdk 17.0.2"), ("official_vectors", "openssl 3.5.9 (ML-KEM-768)"),
                        ("speed_size", "openssl 3.5.9 (ML-KEM-768)")):
        with pytest.raises(CannotDesign):
            ask(kind, label)
    assert ask("mlkem_vectors", "openssl 3.5.9 (ML-KEM-768)")["kind"] == "mlkem_vectors"
    assert ask("mldsa_compare", "openjdk 17.0.2")["kind"] == "mldsa_compare"


# ---------------------------------------------------------------- the two exam specs

def _exam_specs() -> dict:
    tests = RuleEngine().propose_tests(real_claims())["tests"]
    return {t["kind"]: t for t in tests if t["kind"] in ("mlkem_vectors", "mldsa_vectors")}


def _keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _keys(v, found)
    return found


@pytest.mark.parametrize("kind, cases, parts, left_out", [("mlkem_vectors", 655, [125, 300, 230], 0), ("mldsa_vectors", 475, [25, 195, 255], 45)])
def test_an_exam_spec_states_its_files_parts_and_what_it_leaves_out(kind, cases, parts, left_out):
    from app.engine import pq_vectors
    spec = _exam_specs()[kind]
    inputs = spec["inputs"]
    assert inputs["cases"] == cases and sum(p["cases"] for p in inputs["parts"]) == cases
    assert [p["cases"] for p in inputs["parts"]] == parts
    assert inputs["files"] == pq_vectors.file_pins(kind) and len(inputs["files"]) == len(pq_vectors.EXAMS[kind]["files"])
    assert inputs["left_out"] == left_out and inputs["algorithm"] == pq_vectors.EXAMS[kind]["algorithm"]
    assert "timing is not looked at" in spec["rule_text"].lower() and "timing attacks" in spec["rule_text"]
    assert spec["control"]["kind"] == "pq_broken_copies" and set(spec["control"]["must"]) == {p["id"] for p in inputs["parts"]}
    # a locked test names no version: the same test is rerun on a new version
    assert "version" not in _keys(spec) and "3.5.9" not in json.dumps(spec)
    assert spec["target"]["component"] == "openssl"


def test_the_exam_specs_say_what_is_left_out_only_when_something_is():
    specs = _exam_specs()
    assert any("45 NIST cases" in line for line in specs["mldsa_vectors"]["inputs_text"])
    assert not any("Left out" in line for line in specs["mlkem_vectors"]["inputs_text"])
    assert specs["mlkem_vectors"]["control"]["must"]["encaps"]["count"] == 117 and specs["mlkem_vectors"]["control"]["must"]["decaps"]["count"] == 6
