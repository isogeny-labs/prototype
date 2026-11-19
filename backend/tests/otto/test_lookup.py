"""Phase 6, Otto's research loop: reading published advisories from a public source (app/otto/lookup.py).

What is sent is a package's name and ecosystem and nothing else. What comes back is data: taken only in the shape the
source documents, with any score or severity dropped, and nothing in it is ever run. Whether an advisory names a
version you have is worked out on this computer. No test reaches the network: the answers here were written for the
tests, in the source's own shape."""
import json
import random
import time

import pytest

import otto_fuzz as fuzz
from app.knowledge.base import knowledge_base
from app.otto import lookup
from conftest import ReachedTheNetwork
from ottolab import snapshot

ELLIPTIC = lookup.Package(library="elliptic", ecosystem="npm", name="elliptic")
ECDSA = lookup.Package(library="python-ecdsa", ecosystem="PyPI", name="ecdsa")
TODAY = "2026-11-19"


def record(record_id="GHSA-test-0001-aaaa", cve="CVE-2099-0001", package=("npm", "elliptic"), introduced="2.0.0", fixed="6.5.7", **more) -> dict:
    """One record in OSV's documented shape. Written for a test: it is not a published advisory."""
    made = {
        "id": record_id, "summary": "Written for a test: a signature check is missing",
        "details": "Written for a test.\n\nIn versions before the fixed one, a signature whose two numbers are zero is accepted.",
        "aliases": [cve] if cve else [], "modified": "2099-01-03T00:00:00Z", "published": "2099-01-02T10:11:12Z",
        "database_specific": {"github_reviewed": True, "severity": "CRITICAL", "cwe_ids": ["CWE-347"]},
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}],
        "references": [{"type": "ADVISORY", "url": "https://example.invalid/advisory"}],
        "affected": [{"package": {"ecosystem": package[0], "name": package[1], "purl": f"pkg:{package[0].lower()}/{package[1]}"},
                      "ranges": [{"type": "SEMVER", "events": [{"introduced": introduced}, *([{"fixed": fixed}] if fixed else [])]}],
                      "database_specific": {"last_known_affected_version_range": "<= 6.5.6"}}],
        "schema_version": "1.6.0",
    }
    made.update(more)
    return made


def answer(*records, token=None) -> bytes:
    body: dict = {"vulns": list(records)}
    if token:
        body["next_page_token"] = token
    return json.dumps(body).encode("utf-8")


# ---------------------------------------------------------------- which libraries the source can be asked about

def test_a_library_is_asked_about_by_its_package_name_where_the_source_keeps_it_by_name():
    kb = knowledge_base()
    purls = {name: [p.purl for p in kb.files[name].packages] for name in kb.files}
    assert lookup.package_of("elliptic", purls["elliptic"]) == ELLIPTIC
    assert lookup.package_of("python-ecdsa", purls["python-ecdsa"]) == ECDSA
    assert lookup.package_of("go-stdlib", purls["go-stdlib"]) == lookup.Package("go-stdlib", "Go", "stdlib")
    # OpenSSL, OpenJDK and BoringSSL are published nowhere the source keeps by name: they are not asked about
    for name in ("openssl", "openjdk", "boringssl"):
        assert lookup.package_of(name, purls[name]) is None, name
    assert lookup.package_of("x", ["not a purl", "pkg:npm/", "pkg:deb/debian/libssl3", None]) is None        # type: ignore[list-item]
    assert lookup.package_of("x", ["pkg:maven/org.bouncycastle/bcprov-jdk18on@1.78"]) == lookup.Package("x", "Maven", "org.bouncycastle:bcprov-jdk18on")


def test_what_is_sent_is_the_package_name_and_ecosystem_and_nothing_else():
    assert json.loads(lookup.request_body(ELLIPTIC)) == {"package": {"name": "elliptic", "ecosystem": "npm"}}
    assert json.loads(lookup.request_body(ECDSA, "next-page")) == {"package": {"name": "ecdsa", "ecosystem": "PyPI"}, "page_token": "next-page"}
    sent = []

    def transport(body, timeout):
        sent.append(json.loads(body))
        return 200, answer(record())
    look = lookup.read_source(lookup.OsvSource(transport), [ELLIPTIC, ECDSA])
    assert sent == [{"package": {"name": "elliptic", "ecosystem": "npm"}}, {"package": {"name": "ecdsa", "ecosystem": "PyPI"}}]
    assert look["sent"] == ["elliptic (npm)", "ecdsa (PyPI)"] and look["source"] == "osv"
    # no version, no address and nothing else of an assessment is in a request
    assert all(set(body) == {"package"} and set(body["package"]) == {"name", "ecosystem"} for body in sent)


def test_without_a_stand_in_a_test_cannot_reach_the_network():
    with pytest.raises(ReachedTheNetwork):
        lookup.read_source(lookup.OsvSource(), [ELLIPTIC])
    assert lookup.SOURCE_URL == "https://api.osv.dev/v1/query" and lookup.SOURCE_URL.startswith(f"https://{lookup.SOURCE_HOST}/")


# ---------------------------------------------------------------- reading an answer

def test_a_record_becomes_an_advisory_in_the_snapshots_own_shape_with_the_publishers_words():
    found, left_out = lookup.read_answer(answer(record()), ELLIPTIC, TODAY)
    assert left_out == 0 and len(found) == 1
    one = found[0]
    a = one.advisory
    assert a["id"] == "CVE-2099-0001" and a["aliases"] == ["GHSA-test-0001-aaaa"]           # the CVE names it; the record's id is its other name
    assert a["package"] == {"name": "elliptic", "ecosystem": "npm"} and a["published"] == "2099-01-02"
    source = a["sources"][0]
    assert source["publisher"] == "GitHub Advisory Database, reviewed" and source["license"] == "CC-BY-4.0"
    assert source["url"] == "https://osv.dev/vulnerability/GHSA-test-0001-aaaa" and source["fetched_from"] == lookup.SOURCE_URL
    assert source["fetched"] == TODAY and len(source["sha256"]) == 64
    assert source["excerpts"] == ["Written for a test: a signature check is missing", "Written for a test.",
                                  "In versions before the fixed one, a signature whose two numbers are zero is accepted.",
                                  '"introduced": "2.0.0"', '"fixed": "6.5.7"']
    assert one.ranges == [{"introduced": "2.0.0", "fixed": "6.5.7", "last_affected": None}] and one.record_id == "GHSA-test-0001-aaaa"
    # the research side's own reader takes it as it is
    snapshot.check_snapshot({"schema": snapshot.SCHEMA, "snapshot": TODAY, "about": "Read for a test.", "advisories": [a]})


def test_how_serious_an_advisory_is_is_never_read():
    found, _ = lookup.read_answer(answer(record()), ELLIPTIC, TODAY)
    kept = json.dumps([f.advisory for f in found]).lower()
    for word in ("critical", "severity", "cvss", "score", "cwe-"):
        assert word not in kept, word


def test_records_that_are_not_about_the_package_or_not_in_the_documented_shape_are_left_out():
    other = record("GHSA-test-0002-bbbb", "CVE-2099-0002", package=("npm", "some-other-package"))
    withdrawn = record("GHSA-test-0003-cccc", "CVE-2099-0003", withdrawn="2099-02-01T00:00:00Z")
    commits_only = record("GHSA-test-0004-dddd", "CVE-2099-0004")
    commits_only["affected"][0]["ranges"] = [{"type": "GIT", "events": [{"introduced": "0"}, {"fixed": "abc123"}]}]
    no_text = record("GHSA-test-0005-eeee", "CVE-2099-0005", summary=None, details=None)
    no_date = record("GHSA-test-0006-ffff", "CVE-2099-0006", published="yesterday")
    found, left_out = lookup.read_answer(answer(record(), other, withdrawn, commits_only, no_text, no_date, "nonsense", {"id": 5}), ELLIPTIC, TODAY)
    assert [f.advisory["id"] for f in found] == ["CVE-2099-0001"] and left_out == 7
    for bad in (b"", b"not json", b"[]", b'{"vulns": 5}', b"\xff\xfe"):
        with pytest.raises(lookup.LookupError_) as said:
            lookup.read_answer(bad, ELLIPTIC, TODAY)
        assert str(said.value).startswith("The answer of OSV (osv.dev) is not ")
    assert lookup.read_answer(b"{}", ELLIPTIC, TODAY) == ([], 0)            # the source has nothing about this package


def test_a_record_with_no_cve_keeps_its_own_id_and_a_pypa_record_names_its_publisher():
    found, _ = lookup.read_answer(answer(record("PYSEC-2099-12", None, package=("PyPI", "ecdsa"), fixed="0.13.3", introduced="0")), ECDSA, TODAY)
    a = found[0].advisory
    assert a["id"] == "PYSEC-2099-12" and a["aliases"] == [] and a["package"] == {"name": "python-ecdsa", "ecosystem": "PyPI"}
    assert a["sources"][0]["publisher"] == "PyPA Advisory Database"


# ---------------------------------------------------------------- does it name a version you have?

def test_whether_an_advisory_names_your_version_is_worked_out_here_and_never_guessed():
    one = lookup.read_answer(answer(record()), ELLIPTIC, TODAY)[0][0]
    assert lookup.names_version(one, "6.5.6") == {"state": "affected", "fixed": "6.5.7"}
    assert lookup.names_version(one, "6.5.7")["state"] == "not_affected" and lookup.names_version(one, "1.9.9")["state"] == "not_affected"
    assert lookup.names_version(one, "devel")["state"] == "cant_tell" and lookup.names_version(one, None)["state"] == "cant_tell"
    open_ended = lookup.read_answer(answer(record(fixed=None, introduced="0")), ELLIPTIC, TODAY)[0][0]
    assert lookup.names_version(open_ended, "9.9.9") == {"state": "affected", "fixed": None}
    last = record(fixed=None)
    last["affected"][0]["ranges"][0]["events"].append({"last_affected": "6.6.0"})
    closed = lookup.read_answer(answer(last), ELLIPTIC, TODAY)[0][0]
    assert lookup.names_version(closed, "6.6.0")["state"] == "affected" and lookup.names_version(closed, "6.6.1")["state"] == "not_affected"
    odd = lookup.read_answer(answer(record(fixed="next release")), ELLIPTIC, TODAY)[0][0]
    assert lookup.names_version(odd, "6.5.6")["state"] == "cant_tell"         # a range that can't be read is not guessed at
    listed = record()
    listed["affected"][0]["ranges"] = []
    listed["affected"][0]["versions"] = ["6.5.5", "6.5.6"]
    by_list = lookup.read_answer(answer(listed), ELLIPTIC, TODAY)[0][0]
    assert lookup.names_version(by_list, "6.5.6")["state"] == "affected" and lookup.names_version(by_list, "6.5.7")["state"] == "not_affected"


# ---------------------------------------------------------------- one look

def test_one_look_asks_each_package_once_follows_pages_and_keeps_each_advisory_once_newest_first():
    calls = []

    def transport(body, timeout):
        asked = json.loads(body)
        calls.append(asked)
        if asked["package"]["name"] == "ecdsa":
            return 200, answer(record("PYSEC-2099-12", None, package=("PyPI", "ecdsa"), fixed="0.13.3", published="2099-03-01T00:00:00Z"))
        if "page_token" not in asked:
            return 200, answer(record(), token="page-2")
        return 200, answer(record(), record("GHSA-test-0009-zzzz", "CVE-2099-0009", published="2099-06-01T00:00:00Z"))
    look = lookup.read_source(lookup.OsvSource(transport), [ELLIPTIC, ECDSA])
    assert [c.get("page_token") for c in calls] == [None, "page-2", None]
    assert [f.advisory["id"] for f in look["found"]] == ["CVE-2099-0009", "PYSEC-2099-12", "CVE-2099-0001"]
    assert [(a["library"], a["records"], len(a["sha256"])) for a in look["asked"]] == [("elliptic", 3, 2), ("python-ecdsa", 1, 1)]
    assert look["left_out"] == 0 and look["cut"] is False


@pytest.mark.parametrize("fails, words", [
    (lambda body, timeout: (_ for _ in ()).throw(OSError("no route to host 10.0.0.7")), "could not be reached (OSError). Nothing was changed."),
    (lambda body, timeout: (_ for _ in ()).throw(ValueError("header X-Secret: abc")), "did not come back whole (ValueError). Nothing was changed."),
    (lambda body, timeout: (503, b"try later"), "answered with an error (HTTP 503). Nothing was changed."),
    (lambda body, timeout: (200, b"x" * (lookup.MAX_ANSWER_BYTES + 1)), "is larger than this version takes."),
])
def test_a_source_that_cannot_be_read_says_so_in_one_plain_sentence_and_never_in_the_errors_own_words(fails, words):
    with pytest.raises(lookup.LookupError_) as said:
        lookup.read_source(lookup.OsvSource(fails), [ELLIPTIC])
    assert str(said.value).endswith(words) and "10.0.0.7" not in str(said.value) and "X-Secret" not in str(said.value)


def test_a_recorded_source_sends_nothing_and_reads_both_kinds_of_file(tmp_path):
    (tmp_path / "npm__elliptic.json").write_bytes(answer(record()))
    shipped = snapshot.read_snapshot(__import__("ottolab.build", fromlist=["SNAPSHOT"]).SNAPSHOT)
    (tmp_path / "a-snapshot.json").write_text(json.dumps(shipped))
    (tmp_path / "not-json.json").write_text("{")
    source = lookup.RecordedSource(tmp_path)
    look = lookup.read_source(source, [ELLIPTIC, ECDSA])
    assert look["source"] == "recorded" and look["sent"] == []
    ids = [f.advisory["id"] for f in look["found"]]
    assert "CVE-2099-0001" in ids and {"CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459", "CVE-2019-14859", "CVE-2019-14853"} <= set(ids)
    assert "CVE-2022-21449" not in ids                    # about openjdk, which was not asked about
    # a snapshot's advisory is used exactly as it is, so a recorded answer for its prompt still fits
    kept = next(f.advisory for f in look["found"] if f.advisory["id"] == "CVE-2024-42460")
    assert kept == snapshot.advisory_of(shipped, "CVE-2024-42460")
    assert lookup.read_source(lookup.RecordedSource(tmp_path / "nothing-here"), [ELLIPTIC])["found"] == []


# ---------------------------------------------------------------- damaged answers: a plain refusal or a normal read

def test_fuzz_damaged_answers_are_refused_plainly_or_read_normally_and_quickly():
    rng = random.Random(20261119)
    good = json.loads(answer(record(), record("PYSEC-2099-12", None)))
    raw = answer(record(), record("PYSEC-2099-12", None))
    started = time.monotonic()
    for n in range(400):
        damaged = fuzz.damage_bytes(rng, raw) if n % 2 else json.dumps(fuzz.damage_json(rng, good)).encode("utf-8")
        try:
            found, left_out = lookup.read_answer(damaged, ELLIPTIC, TODAY)
        except lookup.LookupError_ as exc:
            assert str(exc).startswith("The answer of OSV (osv.dev) ") and len(str(exc)) < 200
            continue
        assert left_out >= 0
        for one in found:               # whatever was kept is a usable advisory, and nothing about how serious it is
            snapshot.check_snapshot({"schema": snapshot.SCHEMA, "snapshot": TODAY, "about": "x", "advisories": [one.advisory]})
            assert "cvss" not in json.dumps(one.advisory).lower()
            assert lookup.names_version(one, "6.5.6")["state"] in ("affected", "not_affected", "cant_tell")
    assert time.monotonic() - started < 20
