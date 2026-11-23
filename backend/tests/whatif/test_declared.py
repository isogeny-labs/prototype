"""Phase 6e, first part: what one version of a library itself declares it needs (a new kind of knowledge-base entry,
read from the publisher's own package file), the honest answers where that is not known, and the comparison of two
lists."""

import copy
import json
import random
import time

import pytest
from pydantic import ValidationError

from app import real_libraries
from app.knowledge import needs
from app.knowledge.base import KNOWLEDGE_DIR, KnowledgeBase, knowledge_base, load
from app.knowledge.model import LibraryFile

ELLIPTIC = ["bn.js", "brorand", "hash.js", "hmac-drbg", "inherits", "minimalistic-assert", "minimalistic-crypto-utils"]


def _file(name: str) -> dict:
    return json.loads((KNOWLEDGE_DIR / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the entries that are filled


def test_what_the_pinned_versions_of_elliptic_and_python_ecdsa_declare_is_in_the_knowledge_base():
    kb = load()
    for version in ("6.5.6", "6.5.7"):
        found = kb.declared_needs("pkg:npm/elliptic", None, version)
        assert (
            found.answer == "declared" and found.version == version and [n.name for n in found.entry.needs] == ELLIPTIC
        )
        assert (
            found.reason
            == f"The package.json of elliptic {version} (npm registry) lists 7 packages that elliptic {version} needs."
        )
    for version in ("0.13.2", "0.13.3"):
        found = kb.declared_needs(None, "python-ecdsa", version)
        assert found.answer == "declared" and found.entry.needs == []
        assert (
            found.reason
            == f"The METADATA file of ecdsa {version} (the wheel on PyPI) lists no package that python-ecdsa {version} needs."
        )
        assert found.entry.note == "The file has no Requires-Dist line: it lists no package that this version needs."


def test_every_entry_names_its_package_file_its_fingerprint_the_lines_quoted_and_the_day_it_was_read():
    pinned = {d["url"] for family in real_libraries.FAMILIES.values() for d in family["downloads"]}
    seen = 0
    for path in sorted(KNOWLEDGE_DIR.glob("*.json")):
        entry = LibraryFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for declared in entry.declared:
            seen += 1
            source = declared.source
            assert (
                source.kind == "package_file" and source.url.startswith("https://") and source.checked == "2026-11-19"
            )
            assert len(declared.file_sha256) == 64 and declared.file and declared.version in source.title
            # the publisher's own package: the very download this app pins and checks before it uses it
            assert source.url in pinned, f"{path.name}: {source.url} is not one of the pinned downloads"
            # the quoted lines hold every need the entry lists, exactly as written
            for need in declared.needs:
                assert f'"{need.name}": "{need.wants}"' in source.quote
            if not declared.needs:
                assert declared.note  # the quote can't show that a line is absent: the entry says so
    assert seen == 4


def test_what_is_not_known_is_said_in_the_words_dependencies_uses_and_nothing_is_worked_out_from_another_version():
    kb = load()
    other = kb.declared_needs(None, "elliptic", "6.5.4")  # a version the knowledge base holds nothing about
    assert (other.answer, other.entry) == ("not_in_knowledge_base", None)
    assert other.reason == "Our knowledge base does not hold what elliptic 6.5.4 declares it needs."
    unknown = kb.declared_needs("pkg:npm/left-pad", None, "1.3.0")
    assert (unknown.answer, unknown.reason) == (
        "not_in_knowledge_base",
        "This library has no file in our knowledge base yet.",
    )
    unreadable = kb.declared_needs(None, "elliptic", "the newest")
    assert unreadable.answer == "couldnt_tell_version" and unreadable.entry is None
    for args in ((None, "openjdk", "17.0.2"), ("pkg:deb/debian/libssl3", None, "3.0.11-1~deb12u2")):
        no_file = kb.declared_needs(*args)
        assert (
            no_file.answer == "doesnt_apply"
            and "not a package with a file that declares what it needs" in no_file.reason
        )
    for found in (other, unknown, unreadable):
        assert found.as_dict()["needs"] is None and found.as_dict()["source"] is None


def test_the_same_answers_as_plain_data_for_a_screen_or_a_file():
    found = knowledge_base().declared_needs("pkg:npm/elliptic", None, "6.5.7").as_dict()
    assert found["answer"] == "declared" and found["file"] == "package/package.json" and found["version"] == "6.5.7"
    assert found["needs"][0] == {"name": "bn.js", "wants": "^4.11.9"}
    assert (
        found["source"]["url"] == "https://registry.npmjs.org/elliptic/-/elliptic-6.5.7.tgz"
        and found["source"]["kind"] == "package_file"
    )
    json.dumps(found)


# ---------------------------------------------------------------- the rules of the new entry


def _with(change) -> dict:
    data = _file("elliptic")
    change(data)
    return data


@pytest.mark.parametrize(
    "problem, change",
    [
        ("not a version the reader can read", lambda d: d["declared"][0].__setitem__("version", "newest")),
        ("kind must be package_file", lambda d: d["declared"][0]["source"].__setitem__("kind", "release_notes")),
        ("listed twice", lambda d: d["declared"][0]["needs"].append({"name": "BN.js", "wants": "^5"})),
        ("the same version", lambda d: d["declared"].append(copy.deepcopy(d["declared"][0]))),
        (
            "carries no declared needs",
            lambda d: d.__setitem__("no_package_file", "It is not a package with a package file."),
        ),
        (
            "one https address",
            lambda d: d["declared"][0]["source"].__setitem__("url", "http://registry.npmjs.org/elliptic"),
        ),
        ("should match pattern", lambda d: d["declared"][0].__setitem__("file_sha256", "abc")),
        ("should match pattern", lambda d: d["declared"][0]["needs"][0].__setitem__("name", "bn.js; rm -rf /")),
        ("one line", lambda d: d["declared"][0]["needs"][0].__setitem__("wants", "^4\n^5")),
        ("Extra inputs are not permitted", lambda d: d["declared"][0].__setitem__("run", "npm install")),
    ],
)
def test_an_entry_that_breaks_a_rule_is_refused(problem, change):
    with pytest.raises(ValidationError, match=problem):
        LibraryFile.model_validate(_with(change))


def test_an_entry_for_one_version_says_nothing_about_another(tmp_path):
    data = _file("elliptic")
    data["declared"] = [d for d in data["declared"] if d["version"] == "6.5.6"]
    kb = KnowledgeBase({"elliptic": LibraryFile.model_validate(data)})
    assert kb.declared_needs(None, "elliptic", "6.5.6").answer == "declared"
    assert kb.declared_needs(None, "elliptic", "6.5.7").answer == "not_in_knowledge_base"
    assert kb.declared_needs(None, "elliptic", "6.5.6.1").answer == "not_in_knowledge_base"


# ---------------------------------------------------------------- comparing two lists


def test_two_versions_that_declare_the_same_needs_differ_in_nothing():
    kb = load()
    old, new = (kb.declared_needs(None, "elliptic", v).as_dict()["needs"] for v in ("6.5.6", "6.5.7"))
    assert needs.compare(old, new) == {"added": [], "removed": [], "changed": [], "same": ELLIPTIC}


def test_what_was_added_removed_or_changed_between_two_lists():
    before = [("bn.js", "^4.11.9"), ("brorand", "^1.1.0"), ("Inherits", "^2.0.1")]
    after = [
        {"name": "bn.js", "wants": "^5.2.1"},
        {"name": "inherits", "wants": "^2.0.1"},
        {"name": "hash.js", "wants": "^1.0.0"},
    ]
    assert needs.compare(before, after) == {
        "added": [{"name": "hash.js", "wants": "^1.0.0"}],
        "removed": [{"name": "brorand", "wants": "^1.1.0"}],
        "changed": [{"name": "bn.js", "before": "^4.11.9", "after": "^5.2.1"}],
        "same": ["inherits"],
    }
    # a dependency list's entries carry a version where a declared need carries a range: the same comparison
    assert needs.compare([{"name": "elliptic", "version": "6.5.6"}], [{"name": "elliptic", "version": "6.5.7"}])[
        "changed"
    ] == [{"name": "elliptic", "before": "6.5.6", "after": "6.5.7"}]
    assert needs.compare([], []) == {"added": [], "removed": [], "changed": [], "same": []}


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "bn.js",
        7,
        [("a",)],
        [("a", 1)],
        [(1, "a")],
        [("", "a")],
        [{"wants": "x"}],
        [("a", "1"), ("A", "2")],
        [("a" * 301, "1")],
        [("a", "1" * 301)],
        [["a", "1", "2"]],
        [("a", "1")] * 2,
    ],
)
def test_a_list_that_is_not_names_with_their_text_is_refused(bad):
    with pytest.raises(needs.ListError):
        needs.compare(bad, [])
    with pytest.raises(needs.ListError):
        needs.compare([], bad)


# ---------------------------------------------------------------- damaged copies (seeded)

ODD = [
    None,
    0,
    -1,
    1e308,
    True,
    "",
    "x" * 5000,
    [],
    {},
    [None],
    {"a": {"b": []}},
    "../../etc/passwd",
    "a\x00b",
    "6.5.6",
    "^4.11.9",
    {"name": "bn.js", "wants": "^4.11.9"},
    "https://example.com/x",
    "package_file",
    "\ud800",
]


def _damage(rng: random.Random, value):
    if isinstance(value, dict) and value and rng.random() < 0.85:
        k = rng.choice(list(value))
        return {**value, k: _damage(rng, value[k])}
    if isinstance(value, list) and value and rng.random() < 0.85:
        i = rng.randrange(len(value))
        return value[:i] + [_damage(rng, value[i])] + value[i + 1 :]
    return rng.choice(ODD)


def test_damaged_copies_of_a_library_file_are_read_or_refused_plainly_and_a_lookup_never_fails():
    rng = random.Random(20261124)
    outcomes = {"read": 0, "refused": 0}
    for n in range(400):
        original = _file("elliptic" if n % 2 else "python-ecdsa")
        damaged = {**original, "declared": _damage(rng, original["declared"])} if n % 3 else _damage(rng, original)
        start = time.monotonic()
        try:
            entry = LibraryFile.model_validate(damaged)
        except ValidationError as refusal:
            outcomes["refused"] += 1
            assert refusal.errors(include_url=False)[0]["msg"]
        except (TypeError, ValueError, RecursionError):
            outcomes["refused"] += 1
        else:
            outcomes["read"] += 1
            kb = KnowledgeBase({entry.library: entry})
            for version in ("6.5.6", "6.5.7", "0.13.3", "nope", None, 7):
                found = kb.declared_needs(None, entry.label, version)
                assert (
                    found.answer in ("declared", "doesnt_apply", "not_in_knowledge_base", "couldnt_tell_version")
                    and found.reason
                )
                json.dumps(found.as_dict())
                if found.entry is not None:  # what was read can be compared with itself
                    listed = [n.model_dump() for n in found.entry.needs]
                    assert needs.compare(listed, listed)["same"] == [n.name for n in found.entry.needs]
        assert time.monotonic() - start < 2.0
    assert outcomes["refused"] > 100 and outcomes["read"] >= 1, outcomes
    # the comparison on odd lists: a plain refusal or an answer, quickly
    for _ in range(300):
        a, b = (
            _damage(rng, [{"name": "a", "wants": "1"}, {"name": "b", "wants": "2"}]),
            _damage(rng, [("a", "1"), ("c", "3")]),
        )
        start = time.monotonic()
        try:
            out = needs.compare(a, b)
        except needs.ListError as refusal:
            assert str(refusal) and len(str(refusal)) < 100
        else:
            assert set(out) == {"added", "removed", "changed", "same"}
        assert time.monotonic() - start < 2.0
