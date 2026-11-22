"""Phase 4d: the knowledge base (every file against the schema and the rules), the version reader on real version
strings, and the lookup."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.knowledge.base import KNOWLEDGE_DIR, KnowledgeError, knowledge_base, load, purl_base, schema
from app.knowledge.model import LibraryFile
from app.knowledge.versions import read_version

SCHEMA_FILE = KNOWLEDGE_DIR.parent / "schema.json"
FILES = sorted(KNOWLEDGE_DIR.glob("*.json"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_file_follows_the_schema_and_the_rules(path):
    entry = LibraryFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert entry.library == path.stem
    for claim in entry.claims:
        assert claim.source.url.startswith("https://") and claim.source.quote and claim.source.checked
    if entry.needs_your_environment is None:
        assert entry.claims or entry.notes, f"{path.name}: no claims needs a note saying why"


def test_the_schema_file_is_up_to_date():
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == schema()


def test_the_whole_knowledge_base_loads():
    kb = load()
    assert set(kb.files) == {"boringssl", "elliptic", "go-stdlib", "openjdk", "openssl", "python-ecdsa", "starkbank-ecdsa"}


def _base():
    return json.loads((KNOWLEDGE_DIR / "openssl.json").read_text(encoding="utf-8"))


def test_a_no_without_its_mirror_yes_is_refused():
    data = _base()
    data["claims"] = [c for c in data["claims"] if not (c["capability"] == "ml_dsa_65" and c["answer"] == "yes")]
    with pytest.raises(ValidationError, match="matching \"yes\""):
        LibraryFile.model_validate(data)


def test_overlapping_claims_are_refused():
    data = _base()
    data["claims"].append(json.loads(json.dumps(next(c for c in data["claims"] if c["answer"] == "yes"))))
    with pytest.raises(ValidationError, match="overlap"):
        LibraryFile.model_validate(data)


def test_a_hybrid_claim_needs_the_tls_role():
    data = _base()
    data["roles"] = ["key_exchange", "signatures"]
    with pytest.raises(ValidationError, match="tls role"):
        LibraryFile.model_validate(data)


def test_an_environment_only_library_carries_no_claims():
    data = json.loads((KNOWLEDGE_DIR / "boringssl.json").read_text(encoding="utf-8"))
    data["claims"] = _base()["claims"][:2]
    with pytest.raises(ValidationError, match="carries no version claims"):
        LibraryFile.model_validate(data)


@pytest.mark.parametrize("url", ["http://example.org/notes", "https://exa mple.org", "ftp://x"])
def test_a_source_must_be_one_https_link(url):
    data = _base()
    data["claims"][0]["source"]["url"] = url
    with pytest.raises(ValidationError):
        LibraryFile.model_validate(data)


def test_a_broken_file_stops_the_load_naming_it(tmp_path):
    (tmp_path / "openssl.json").write_text(json.dumps({**_base(), "library": "other"}))
    with pytest.raises(KnowledgeError, match="openssl.json"):
        load(tmp_path)
    (tmp_path / "openssl.json").write_text("{")
    with pytest.raises(KnowledgeError, match="not a readable JSON file"):
        load(tmp_path)


@pytest.mark.parametrize("text, want", [
    ("3.0.22", ((3, 0, 22), "")), ("3.0.22-1~deb12u2", ((3, 0, 22), "")), ("3.5.9-r0", ((3, 5, 9), "")),
    ("1:3.0.13-0ubuntu3.5", ((3, 0, 13), "")), ("3.0.13-0ubuntu3.5", ((3, 0, 13), "")), ("v1.2.3", ((1, 2, 3), "")),
    ("go1.23.4", ((1, 23, 4), "")), ("1.1.1w", ((1, 1, 1), "w")), ("17.0.2+8", ((17, 0, 2), "")), ("24", ((24,), "")),
    ("17.0.2+8-Debian-1deb12u1", ((17, 0, 2), "")), ("6.5.6", ((6, 5, 6), "")),
    ("devel", None), ("4c8b1d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c", None), ("3.0.x", None), ("3.5.0-alpha1", None),
    ("17-ea", None), ("1.24rc1", None), ("", None), (None, None), ("latest", None), ("3.0.22 or newer", None),
])
def test_the_version_reader(text, want):
    assert read_version(text) == want


@pytest.mark.parametrize("purl, want", [
    ("pkg:deb/debian/libssl3@3.0.22-1~deb12u2?arch=amd64", "pkg:deb/debian/libssl3"),
    ("pkg:apk/alpine/libssl3@3.5.9-r0?arch=x86_64&upstream=openssl", "pkg:apk/alpine/libssl3"),
    ("pkg:Generic/OpenSSL@3.0.22", "pkg:generic/openssl"), ("not a purl", None), ("pkg:", None), (None, None)])
def test_purl_base(purl, want):
    assert purl_base(purl) == want


def _answers(purl, name, version):
    return {q: (a.answer, a.label, a.first_version) for q, a in knowledge_base().look_up(purl, name, version).items()}


def test_lookup_before_and_from_the_version_that_added_it():
    assert _answers("pkg:generic/openssl@3.0.22", "openssl", "3.0.22") == {q: ("no", "release_notes", "3.5.0") for q in
                                                                         ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")}
    assert _answers("pkg:generic/openssl@3.5.0", "openssl", "3.5.0") == {q: ("yes", "release_notes", None) for q in
                                                                       ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")}


def test_lookup_reads_a_distro_package_by_its_upstream_version():
    assert _answers("pkg:deb/debian/libssl3@3.0.22-1~deb12u2", "libssl3", "3.0.22-1~deb12u2")["ml_kem_768"] == ("no", "release_notes", "3.5.0")
    assert _answers("pkg:apk/alpine/libcrypto3@3.5.9-r0", "libcrypto3", "3.5.9-r0")["x25519mlkem768"] == ("yes", "release_notes", None)


def test_lookup_first_versions_per_question():
    jdk = _answers("pkg:generic/openjdk@17.0.2", "openjdk", "17.0.2")
    assert {q: v[2] for q, v in jdk.items()} == {"ml_kem_768": "24", "x25519mlkem768": "27", "ml_dsa_65": "24"}
    go = _answers("pkg:golang/stdlib@1.23.4", "Go standard library", "1.23.4")
    assert {q: v[2] for q, v in go.items()} == {"ml_kem_768": "1.24", "x25519mlkem768": "1.24", "ml_dsa_65": "1.27"}


def test_the_order_of_the_answers_without_a_yes_or_no():
    assert set(_answers("pkg:generic/wolfssl@5.7.2", "wolfssl", "5.7.2").values()) == {("not_in_knowledge_base", None, None)}
    assert set(_answers("pkg:generic/boringssl@abc", "boringssl", "abc").values()) == {("needs_your_environment", None, None)}
    assert set(_answers("pkg:golang/stdlib@devel", "Go standard library", "devel").values()) == {("couldnt_tell_version", None, None)}
    ecdsa = _answers("pkg:pypi/ecdsa@0.13.2", "ecdsa", "0.13.2")
    assert ecdsa["x25519mlkem768"][0] == "doesnt_apply" and ecdsa["ml_kem_768"][0] == "not_in_knowledge_base"


def test_a_name_is_matched_only_without_a_purl():
    assert _answers(None, "openssl", "3.0.22")["ml_kem_768"][0] == "no"
    assert _answers("pkg:pypi/openssl@3.0.22", "openssl", "3.0.22")["ml_kem_768"][0] == "not_in_knowledge_base"


def test_every_answer_has_a_reason_and_every_yes_or_no_its_source():
    for purl, name, version in (("pkg:generic/openssl@3.0.22", "openssl", "3.0.22"), ("pkg:golang/stdlib@devel", "x", "devel"),
                                ("pkg:generic/wolfssl@5", "wolfssl", "5")):
        for a in knowledge_base().look_up(purl, name, version).values():
            assert a.reason and (a.source is not None) == (a.answer in ("yes", "no")) == (a.label == "release_notes")


def test_the_knowledge_base_has_no_word_it_must_not_use():
    words = " ".join(p.read_text(encoding="utf-8").lower() for p in [*FILES, SCHEMA_FILE, KNOWLEDGE_DIR.parent / "README.md"])
    assert "score" not in words and "secure" not in words.replace("secure channel", "")


def test_the_knowledge_folder_is_data_only():
    folder = Path(KNOWLEDGE_DIR).parent
    assert {p.suffix for p in folder.rglob("*") if p.is_file()} <= {".json", ".md"}
