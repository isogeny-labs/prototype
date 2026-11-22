"""Sandbox research: which versions a trial runs on, and what fits what a library says it needs. Fixed rules only."""

from __future__ import annotations

import random

import pytest

from app.sandbox import versions

RELEASES = [
    {"version": v, "published": f"2021-0{n + 1}-01"}
    for n, v in enumerate(["1.0.0", "1.1.0", "1.1.1", "2.0.0", "2.0.1", "2.0.2", "2.2.0"])
]


def test_the_closest_pair_is_tried_and_two_more_versions_on_each_side():
    chosen = versions.choose([{"introduced": "0", "fixed": "2.0.1", "last_affected": None}], RELEASES, ["2.0.0"])
    assert (chosen["affected"], chosen["fixed"]) == ("2.0.0", "2.0.1")  # the last release before the fix
    assert chosen["more_affected"] == ["1.1.1", "1.1.0"] and chosen["more_fixed"] == ["2.0.2", "2.2.0"]
    assert (
        chosen["yours"] == [] and chosen["after_last_affected"] is False
    )  # (your version is the affected one already)


def test_your_own_version_is_tried_too_when_it_is_another_affected_one():
    chosen = versions.choose([{"introduced": "0", "fixed": "2.0.1", "last_affected": None}], RELEASES, ["1.1.0"])
    assert chosen["affected"] == "2.0.0" and chosen["yours"] == ["1.1.0"] and chosen["more_affected"] == ["1.1.1"]


def test_a_range_that_starts_later_names_no_earlier_version_as_affected():
    chosen = versions.choose([{"introduced": "2.0.0", "fixed": "2.0.1", "last_affected": None}], RELEASES, ["2.0.0"])
    assert chosen["affected"] == "2.0.0" and chosen["more_affected"] == []


def test_a_last_affected_version_makes_the_next_release_the_fixed_side_and_says_so():
    chosen = versions.choose([{"introduced": "0", "fixed": None, "last_affected": "2.0.0"}], RELEASES, [])
    assert (chosen["affected"], chosen["fixed"], chosen["after_last_affected"]) == ("2.0.0", "2.0.1", True)


@pytest.mark.parametrize(
    "ranges, why",
    [
        ([{"introduced": "0", "fixed": None, "last_affected": None}], "no fixed version"),
        ([{"introduced": "0", "fixed": "9.9.9", "last_affected": None}], "not among the versions the registry lists"),
        ([{"introduced": "0", "fixed": "1.0.0", "last_affected": None}], "no affected version is published before"),
        ([{"introduced": "0", "fixed": None, "last_affected": "2.2.0"}], "no version after"),
    ],
)
def test_where_no_pair_can_be_chosen_the_reason_is_said(ranges, why):
    with pytest.raises(versions.NoVersions, match=why):
        versions.choose(ranges, RELEASES, [])


def test_a_version_another_range_still_names_is_not_taken_as_a_fixed_one():
    ranges = [
        {"introduced": "0", "fixed": "2.0.1", "last_affected": None},
        {"introduced": "2.2.0", "fixed": None, "last_affected": None},
    ]
    chosen = versions.choose(ranges, RELEASES, ["2.0.0"])
    assert "2.2.0" not in chosen["more_fixed"] and chosen["more_fixed"] == ["2.0.2"]


@pytest.mark.parametrize(
    "spec, version, fits",
    [
        (">=1.9.0", "1.16.0", True),
        (">=1.9.0", "1.8.0", False),
        ("", "0.1", True),
        ("==1.2.*", "1.2.9", True),
        ("==1.2.*", "1.3.0", False),
        ("~=1.4", "1.9", True),
        ("~=1.4", "2.0", False),
        (">=1.0,<2.0", "1.5", True),
        (">=1.0,<2.0", "2.0", False),
        ("!=1.5", "1.5", False),
    ],
)
def test_what_a_python_package_says_it_needs(spec, version, fits):
    assert versions.fits_pypi(spec, version) is fits


@pytest.mark.parametrize(
    "spec, version, fits",
    [
        ("^4.11.9", "4.12.0", True),
        ("^4.11.9", "5.0.0", False),
        ("^4.11.9", "4.11.8", False),
        ("~1.0.1", "1.0.9", True),
        ("~1.0.1", "1.1.0", False),
        ("1.x", "1.9.9", True),
        ("*", "3.0.0", True),
        (">=2.0.0 <3.0.0", "2.5.0", True),
        (">=2.0.0 <3.0.0", "3.0.0", False),
        ("^0.2.3", "0.2.9", True),
        ("^0.2.3", "0.3.0", False),
        ("1.2.3 || 2.x", "2.4.0", True),
    ],
)
def test_what_an_npm_package_says_it_needs(spec, version, fits):
    assert versions.fits_npm(spec, version) is fits


@pytest.mark.parametrize(
    "spec",
    [
        "git+https://example.com/x.git",
        "file:../x",
        "latest",
        "workspace:*",
        ">=1.0 ; python_version < '3'",
        "@scope/thing",
    ],
)
def test_what_can_not_be_read_is_never_guessed(spec):
    assert versions.fits_npm(spec, "1.0.0") is None or versions.fits_npm(spec, "1.0.0") is False
    assert versions.fits_pypi(spec, "1.0.0") in (None, False)


def test_seeded_fuzz_of_ranges_and_versions_never_raises_anything_but_the_plain_refusal():
    rng = random.Random(20261122)
    alphabet = "0123456789.xX*^~<>=!|, -+abv"
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
        version = "".join(rng.choice("0123456789.ab") for _ in range(rng.randint(1, 8)))
        assert versions.fits_npm(text, version) in (True, False, None)
        assert versions.fits_pypi(text, version) in (True, False, None)
        assert versions.order(text) is None or isinstance(versions.order(text), tuple)
        ranges = [
            {
                "introduced": rng.choice(["0", version, text]),
                "fixed": rng.choice([None, version, text]),
                "last_affected": rng.choice([None, version, text]),
            }
        ]
        try:
            chosen = versions.choose(ranges, RELEASES + [{"version": version, "published": None}], [version])
        except versions.NoVersions as reason:
            assert str(reason)
        else:
            assert chosen["affected"] != chosen["fixed"] and versions.order(chosen["affected"]) < versions.order(
                chosen["fixed"]
            )
