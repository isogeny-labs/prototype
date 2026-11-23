"""Phase 5c, step 2: the advisory snapshot and its reader."""

import json
import random
import time
from pathlib import Path

import pytest

import otto_fuzz
from ottolab import snapshot

SNAPSHOT = Path(__file__).resolve().parents[3] / "research" / "snapshot" / "2026-11-17" / "advisories.json"
THE_SIX = ["CVE-2022-21449", "CVE-2019-14859", "CVE-2019-14853", "CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"]
COPIES = 300
TIME_LIMIT = 2.0


def test_the_snapshot_holds_the_six_advisories_each_with_a_link_a_quote_and_both_dates():
    data = snapshot.read_snapshot(SNAPSHOT)
    assert [a["id"] for a in data["advisories"]] == THE_SIX and data["snapshot"] == "2026-11-17"
    for advisory in data["advisories"]:
        assert advisory["published"] <= data["snapshot"]  # when it was published
        for source in advisory["sources"]:
            assert source["url"].startswith("https://") and source["fetched_from"].startswith("https://")
            assert source["fetched"] == "2026-11-17"  # when the page was opened
            assert len(source["sha256"]) == 64 and source["excerpts"] and all(e.strip() for e in source["excerpts"])
            assert source["publisher"] and source["title"]
    # the app's real libraries are the packages the advisories are about
    assert {a["package"]["name"] for a in data["advisories"]} == {"openjdk", "python-ecdsa", "elliptic"}


def test_a_quote_counts_only_when_it_is_in_the_named_source_character_for_character():
    advisory = snapshot.advisory_of(snapshot.read_snapshot(SNAPSHOT), "CVE-2022-21449")
    line = "The affected versions are 18, 17.0.2, 15.0.6,"
    assert snapshot.excerpt_holds(advisory, "S1", line)
    assert not snapshot.excerpt_holds(advisory, "S2", line)  # another source
    assert not snapshot.excerpt_holds(advisory, "S1", line.replace("17.0.2", "17.0.1"))
    assert not snapshot.excerpt_holds(advisory, "S1", line.upper())
    for odd in ("", "   ", None, 7):
        assert not snapshot.excerpt_holds(advisory, "S1", odd)
    assert not snapshot.excerpt_holds(advisory, "S99", line) and not snapshot.excerpt_holds(advisory, None, line)


@pytest.mark.parametrize(
    "change, words",
    [
        (lambda d: d.__setitem__("schema", "isogeny.advisory-snapshot/2"), "not an advisory snapshot"),
        (lambda d: d.__setitem__("extra", 1), "top level"),
        (lambda d: d["advisories"].append(d["advisories"][0]), "id is there twice"),
        (lambda d: d["advisories"][0]["sources"][0].__setitem__("url", "http://openjdk.org/x"), "not an https address"),
        (lambda d: d["advisories"][0]["sources"][0].__setitem__("excerpts", []), "no quoted text"),
        (lambda d: d["advisories"][0]["sources"][0].__setitem__("fetched", "yesterday"), "not a date"),
        (lambda d: d["advisories"][0].__setitem__("published", None), "not a date"),
        (lambda d: d["advisories"][0]["sources"][0].__setitem__("sha256", "abc"), "SHA-256"),
        (lambda d: d["advisories"][0]["sources"][0]["excerpts"].append("x" * 4001), "missing, empty or too long"),
        (lambda d: d["advisories"][0].__setitem__("command", "rm -rf /"), "exactly the fields"),
        (lambda d: d.__setitem__("advisories", []), "no advisories"),
    ],
)
def test_a_snapshot_that_is_not_exactly_the_shape_is_refused_in_plain_words(change, words):
    data = json.loads(SNAPSHOT.read_bytes())
    change(data)
    with pytest.raises(snapshot.SnapshotError) as refused:
        snapshot.check_snapshot(data)
    assert words in str(refused.value)


def test_a_file_that_is_missing_too_large_or_not_json_is_refused(tmp_path):
    for name, data in (
        ("none.json", None),
        ("big.json", b" " * (snapshot.MAX_BYTES + 1)),
        ("bad.json", b"{not json"),
        ("bytes.json", b"\xff\xfe\x00"),
        ("list.json", b"[]"),
    ):
        path = tmp_path / name
        if data is not None:
            path.write_bytes(data)
        with pytest.raises(snapshot.SnapshotError):
            snapshot.read_snapshot(path)


def test_damaged_copies_are_read_or_refused_plainly(tmp_path):
    """Seeded fuzz: every damaged copy is either read as a valid snapshot or refused with one SnapshotError, in time."""
    original = SNAPSHOT.read_bytes()
    doc = json.loads(original)
    rng = random.Random(20261117)
    outcomes = {"read": 0, "refused": 0}
    path = tmp_path / "copy.json"
    for n in range(COPIES):
        data = otto_fuzz.damage_bytes(rng, original) if n % 2 else json.dumps(otto_fuzz.damage_json(rng, doc)).encode()
        path.write_bytes(data)
        start = time.monotonic()
        try:
            got = snapshot.read_snapshot(path)
            assert got["schema"] == snapshot.SCHEMA and got["advisories"]
            outcomes["read"] += 1
        except snapshot.SnapshotError as exc:
            assert str(exc) and len(str(exc)) < 300 and "Traceback" not in str(exc)
            outcomes["refused"] += 1
        assert time.monotonic() - start < TIME_LIMIT
    assert outcomes["refused"] > COPIES // 2 and sum(outcomes.values()) == COPIES
