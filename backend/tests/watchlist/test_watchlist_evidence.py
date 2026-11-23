"""The Watch list in the signed evidence, and the verify command's own working-out of it (sandbox research). The rule is
written twice, once in the app and once in the verify command: these tests hold the two to each other, and show that a
changed part does not verify."""

from __future__ import annotations

import copy
import itertools
import random

import pytest
from watch_helpers import ITEM, record, watch_lab, with_events, write_source

from app.changewatch import watchlist as rule
from evidence import watchlist as check

FIXED = [{"introduced": "0"}, {"fixed": "0.13.3"}]


@pytest.fixture
def walked(tmp_path, monkeypatch):
    """A list with a history: seen with no fix, looked at again, a fix published, stopped, watched again."""
    lab, pid, folder = watch_lab(tmp_path, monkeypatch)
    try:
        lab.watch_list_look(pid)
        lab.watch_list_look(pid)
        write_source(folder, [with_events(record(), FIXED)])
        lab.watch_list_look(pid)
        lab.watch_list_mark(pid, ITEM, True, "Not used for signing here.")
        lab.watch_list_mark(pid, ITEM, False)
        from app.evidence.export import build_evidence

        yield lab, pid, build_evidence(lab, pid)
    finally:
        lab.stop()


@pytest.fixture(scope="module")
def walked_evidence(tmp_path_factory):
    """The evidence of that same history, made once for the tests that only read a copy of it. Its stand-ins are taken
    off again at once, and its lab is stopped: nothing of it is left for a later test."""
    with pytest.MonkeyPatch.context() as patch:
        lab, pid, folder = watch_lab(tmp_path_factory.mktemp("watch-evidence"), patch)
        try:
            lab.watch_list_look(pid)
            lab.watch_list_look(pid)
            write_source(folder, [with_events(record(), FIXED)])
            lab.watch_list_look(pid)
            lab.watch_list_mark(pid, ITEM, True, "Not used for signing here.")
            lab.watch_list_mark(pid, ITEM, False)
            from app.evidence.export import build_evidence

            return build_evidence(lab, pid)
        finally:
            lab.stop()


def test_the_file_holds_the_list_and_the_verify_commands_own_rule_gives_the_same(walked):
    _, _, evidence = walked
    part = evidence["watch_list"]
    [item] = part["items"]
    assert (item["key"], item["state"], item["word"], item["stopped"]) == (
        ITEM,
        "fix_published",
        "Fix published",
        False,
    )
    assert [e["kind"] for e in item["events"]] == ["seen_no_fix", "fix_published"] and item["quiet"] == 1
    assert [(m["kind"], m["by"], m["reason"]) for m in part["marks"]] == [
        ("stop", "You", "Not used for signing here."),
        ("watch", "You", None),
    ]
    assert len(part["looks"]) == 3 and "not a result" in part["note"]
    outcome = check.check_watch_list(evidence)
    assert outcome.ok, outcome.problem
    assert "1 item worked out again from the 3 looks" in outcome.lines[0] and "not a result" in outcome.lines[0]


@pytest.mark.parametrize(
    "what, change",
    [
        ("its state", lambda p: p["items"][0].update(state="no_fix", word="No fix yet")),
        ("its word", lambda p: p["items"][0].update(word="No fix yet")),
        ("its events", lambda p: p["items"][0]["events"].pop()),
        ("an event's time", lambda p: p["items"][0]["events"][1].update(at="2020-01-01T00:00:00Z")),
        ("the fixed version", lambda p: p["items"][0]["ends"].update(fixed=["9.9.9"])),
        ("a look's facts", lambda p: p["looks"][2]["found"][0].update(ranges=[["0", None, None]])),
        ("an item taken out", lambda p: p["items"].clear()),
        (
            "an item added",
            lambda p: p["items"].append({**copy.deepcopy(p["items"][0]), "key": "CVE-1999-0001~python-ecdsa"}),
        ),
        ("a look taken out", lambda p: p["looks"].pop()),
        (
            "a mark about nothing",
            lambda p: p["marks"].append(
                {"item": "CVE-1999-0001~x", "kind": "stop", "at": "2026-11-22T10:00:00Z", "by": "You", "reason": None}
            ),
        ),
        ("two stops in a row", lambda p: p["marks"].insert(1, copy.deepcopy(p["marks"][0]))),
        ("stopped though watched again", lambda p: p["items"][0].update(stopped=True)),
        ("a mark with nobody", lambda p: p["marks"][0].update(by="")),
        (
            "a test proposed with no pack",
            lambda p: p["items"][0].update(test={"key": "test_proposed", "word": "Test proposed"}),
        ),
        ("not a list", lambda p: p.update(items="none")),
    ],
)
def test_a_changed_part_does_not_verify(walked_evidence, what, change):
    changed = copy.deepcopy(walked_evidence)
    change(changed["watch_list"])
    outcome = check.check_watch_list(changed)
    assert not outcome.ok and outcome.problem, what


def test_without_the_switch_and_without_a_mark_the_file_has_no_such_part(tmp_path, monkeypatch):
    lab, pid, _ = watch_lab(tmp_path, monkeypatch, on=False)
    try:
        lab.look_for_advisories(pid)  # the look Advisories has had since phase 6; the switch is off
        from app.evidence.export import build_evidence

        assert "watch_list" not in build_evidence(lab, pid)
    finally:
        lab.stop()


RANGES = (
    [["0", None, None]],
    [["0", "1.2.5", None]],
    [["0", "1.3.0", None]],
    [["0", None, "1.2.4"]],
    [["1.0.0", None, None]],
    [["1.0.0", "1.2.5", None], ["2.0.0", None, None]],
    [],
)


def _look(number: int, rng: random.Random) -> dict:
    found = []
    for library in ("lib", "other"):
        for id_ in ("CVE-2026-0001", "GHSA-AAAA-BBBB-CCCC", "CVE-2026-0002"):
            if rng.random() < 0.6:
                aliases = ["CVE-2026-0001"] if id_.startswith("GHSA") and rng.random() < 0.5 else []
                found.append({"id": id_, "aliases": aliases, "library": library, "ranges": rng.choice(RANGES)})
    withdrawn = (
        [
            {
                "library": rng.choice(("lib", "other")),
                "ids": [rng.choice(("CVE-2026-0001", "CVE-2026-0002", "GHSA-AAAA-BBBB-CCCC"))],
            }
        ]
        if rng.random() < 0.2
        else []
    )
    return {
        "number": number,
        "at": f"2026-11-{number:02d}T09:00:00Z",
        "cut": rng.random() < 0.15,
        "asked": rng.choice((["lib", "other"], ["lib"], ["other"])),
        "found": found,
        "withdrawn": withdrawn,
    }


def test_the_two_writings_of_the_rule_agree_on_many_made_up_histories():
    """The app's rule and the verify command's are written apart. Over a few thousand seeded histories (every kind of
    change, in every order the generator reaches) they must give the same items, field for field."""
    rng = random.Random(20261122)
    compared = 0
    for _ in range(3000):
        looks = [_look(n, rng) for n in range(1, rng.randint(1, 7) + 1)]
        ours = rule.derive(copy.deepcopy(looks))
        theirs = check.work_out(copy.deepcopy(looks))
        assert len(ours) == len(theirs)
        for mine, other in zip(ours, theirs, strict=True):
            for name in ("key", "id", "ids", "library", "first", "last", "state", "ends", "ranges", "events", "quiet"):
                assert mine[name] == other[name], (name, looks)
            compared += 1
    assert compared > 3000
    # and every three facts in turn, as three looks: each kind of change is reached
    kinds = set()
    for facts in itertools.product(RANGES, repeat=3):
        looks = [
            {
                "number": n,
                "at": f"t{n}",
                "cut": False,
                "asked": ["lib"],
                "withdrawn": [],
                "found": [{"id": "X-1234", "aliases": [], "library": "lib", "ranges": ranges}],
            }
            for n, ranges in enumerate(facts, start=1)
        ]
        ours, theirs = rule.derive(copy.deepcopy(looks)), check.work_out(copy.deepcopy(looks))
        assert [(i["state"], i["events"]) for i in ours] == [(i["state"], i["events"]) for i in theirs]
        kinds.update(e["kind"] for i in ours for e in i["events"])
    assert {"seen_no_fix", "fix_published", "fix_changed", "fix_no_longer_named", "versions_changed"} <= kinds


def test_the_verify_command_reads_the_part_from_a_signed_file_and_fails_on_a_changed_one(walked, tmp_path, capsys):
    """The command itself, on the file the app signs: the Watch list line is printed with the others, and a file whose
    list was changed (and signed again with the same key, so only the list's own check can catch it) does not verify."""
    import json

    from app.evidence.export import sign_envelope
    from evidence import FAILED, VERIFIED
    from evidence.__main__ import main

    lab, _, evidence = walked
    data_dir = lab.settings.data_dir
    good = tmp_path / "good.json"
    good.write_bytes(sign_envelope(evidence, data_dir))
    assert main(["verify", str(good), "--data-dir", str(data_dir)]) == VERIFIED
    said = capsys.readouterr().out
    assert "Watch list: 1 item worked out again from the 3 looks in the file" in said
    changed = copy.deepcopy(evidence)
    changed["watch_list"]["items"][0].update(
        state="no_fix", word="No fix yet"
    )  # "no fix yet", though the looks say fixed
    bad = tmp_path / "bad.json"
    bad.write_bytes(sign_envelope(changed, data_dir))
    assert json.loads(bad.read_bytes())["evidence"]["watch_list"]["items"][0]["state"] == "no_fix"
    assert main(["verify", str(bad), "--data-dir", str(data_dir)]) == FAILED
    assert "Evidence NOT verified: the Watch list part:" in capsys.readouterr().out
