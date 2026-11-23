"""Sandbox research: a test pack that carries asking code (the second format). It is data, read strictly; it is taken
only when it was made on this computer, and installed only while Sandbox research is on."""

from __future__ import annotations

import copy
import json
import random

import pytest
from sandbox_fixtures import envelope, keys, raw_pack
from sandbox_helpers import sandbox_lab, turn_on

from app.canonical import canonical_bytes
from app.config import OTTO_PACKS_DIR
from app.errors import Conflict
from app.otto import packs
from app.present import proof


def _lab_with_the_pack(tmp_path, monkeypatch, on: bool = True):
    """A lab that holds the two built-in packs installed and the fixture pack in the folder of packs made here, signed by
    what this lab takes for its own key."""
    lab = sandbox_lab(tmp_path, monkeypatch)
    (lab.settings.data_dir / packs.LOCAL_KEY_FILE).write_text(envelope()["public_key"], encoding="ascii")
    lab.settings.otto_local_updates.mkdir(parents=True, exist_ok=True)
    (lab.settings.otto_local_updates / "2026.11.3.json").write_bytes(raw_pack() + b"\n")
    for version in ("2026.11.1", "2026.11.2"):
        lab.install_pack(version)
    if on:
        turn_on(lab)
    return lab


def test_the_pack_of_a_real_run_reads_and_holds_everything_its_proof_rests_on():
    pack = packs.read_envelope(raw_pack(), keys(made_here=True))
    assert pack.pack["schema"] == packs.PACK_SCHEMA_2 and pack.made_here
    entry = pack.pack["advisories"][0]
    block = entry["test"]["sandbox"]
    assert entry["test"]["state"] == "ready" and set(block) == {
        "set",
        "second",
        "known",
        "second_known",
        "versions",
        "screen_sha256",
        "registered",
    }
    assert block["set"]["asking"]["kind"] == "written" and block["second"]["sha256"] != block["set"]["asking"]["sha256"]
    assert {"affected-b", "fixed-b"} <= set(entry["test"]["trial"]["arms"])
    assert [s["step"] for s in entry["steps"]].count("write_wrapper") == 2
    # the scripts the harness ran are named by fingerprint, the two sandbox instruments among them
    assert {"trial_sandbox.py", "qualify.py", "ottolab/sandbox.py", "ottolab/screens.py"} <= set(
        pack.pack["otto"]["scripts"]
    )


def test_a_pack_that_carries_asking_code_is_taken_only_when_it_was_made_on_this_computer():
    with pytest.raises(packs.PackError) as refused:
        packs.read_envelope(
            raw_pack(), keys(made_here=False)
        )  # the same signature, from a key that is not this computer's
    assert str(refused.value) == packs.ONLY_MADE_HERE
    with pytest.raises(packs.PackError, match="does not trust"):
        packs.read_envelope(raw_pack(), {})


def test_a_pack_of_the_first_format_can_not_carry_a_sandbox_part():
    shipped = json.loads((OTTO_PACKS_DIR / "2026.11.2.json").read_text(encoding="utf-8"))["pack"]
    packs.check_pack(copy.deepcopy(shipped))  # (as shipped, it reads)
    ready = next(a for a in shipped["advisories"] if a["test"]["state"] == "ready")
    ready["test"]["sandbox"] = envelope()["pack"]["advisories"][0]["test"]["sandbox"]
    with pytest.raises(packs.PackError, match="does not have exactly the fields"):
        packs.check_pack(shipped)


def _content(change) -> dict:
    pack = copy.deepcopy(envelope()["pack"])
    change(pack["advisories"][0])
    return pack


BENT = [
    (
        "the second code is the first one over again",
        lambda a: a["test"]["sandbox"]["second"].update(
            source=a["test"]["sandbox"]["set"]["asking"]["source"],
            sha256=a["test"]["sandbox"]["set"]["asking"]["sha256"],
        ),
        "first one over again",
    ),
    (
        "the asking code was edited",
        lambda a: a["test"]["sandbox"]["set"]["asking"].__setitem__("source", "import os\n"),
        "copy set",
    ),
    (
        "a file of a copy was swapped",
        lambda a: a["test"]["sandbox"]["set"]["versions"][0]["files"][0].__setitem__("sha256", "0" * 64),
        "copy set",
    ),
    ("written code with no second author", lambda a: a["test"]["sandbox"].__setitem__("second", None), "second author"),
    (
        "the known-answer check failed on the affected version",
        lambda a: a["test"]["sandbox"]["known"]["versions"]["2.0.0"].__setitem__("accepted_valid", 3),
        "did not pass the known-answer check",
    ),
    (
        "the known-answer check did not refuse its controls",
        lambda a: a["test"]["sandbox"]["known"].__setitem__("controls_refused", False),
        "did not refuse its own controls",
    ),
    (
        "a version that is not in the copy set",
        lambda a: a["test"]["sandbox"]["versions"].__setitem__("fixed", "9.9.9"),
        "not in its copy set",
    ),
    (
        "the registration is of another trial",
        lambda a: a["test"]["sandbox"]["registered"].__setitem__("hypothesis", "sha256:" + "0" * 64),
        "not of its own trial",
    ),
    (
        "a run stands before the registration",
        lambda a: [
            e.__setitem__("seq", 999)
            for e in a["ledger"]
            if e["id"] == a["test"]["sandbox"]["registered"]["hypothesis"]
        ],
        "not registered before its first run",
    ),
    (
        "no screen is named for written code",
        lambda a: a["test"]["sandbox"].__setitem__("screen_sha256", None),
        "screened by",
    ),
    (
        "an arm this version does not know",
        lambda a: a["test"]["trial"]["arms"].__setitem__("extra-arm", {"right": 1}),
        "exactly the fields",
    ),
]


@pytest.mark.parametrize("what, change, word", BENT, ids=[b[0] for b in BENT])
def test_a_sandbox_part_that_does_not_hold_together_is_refused(what, change, word):
    with pytest.raises(packs.PackError) as refused:
        packs.check_pack(_content(change))
    assert word in str(refused.value), str(refused.value)


def test_a_pack_changed_after_it_was_signed_does_not_read_whatever_was_changed():
    changed = envelope()
    changed["pack"]["advisories"][0]["test"]["sandbox"]["set"]["asking"]["source"] += "\n"
    with pytest.raises(packs.PackError, match="changed after it was signed"):
        packs.read_envelope(canonical_bytes(changed), keys())


def test_it_is_installed_only_while_sandbox_research_is_on(tmp_path, monkeypatch):
    lab = _lab_with_the_pack(tmp_path, monkeypatch, on=False)
    try:
        view = lab.otto_view(scan=True)["packs"]
        assert view["update"] is None
        assert {"file": "2026.11.3.json", "reason": packs.NEEDS_SANDBOX} in view["refused"]
        with pytest.raises(Conflict):
            lab.install_pack("2026.11.3")
        turn_on(lab)
        assert lab.otto_view(scan=True)["packs"]["update"]["version"] == "2026.11.3"
        lab.install_pack("2026.11.3")
        assert [c["version"] for c in lab.otto_view()["packs"]["installed"]] == ["2026.11.1", "2026.11.2", "2026.11.3"]
        assert lab.otto_view()["packs"]["installed"][-1]["made_here"] is True
    finally:
        lab.stop()


@pytest.mark.needs_otto  # (a decision is written into the assessment's Otto ledger)
def test_the_proposal_carries_the_proof_and_a_decision_is_not_made_on_it(tmp_path, monkeypatch):
    from app.otto import proposals

    lab = _lab_with_the_pack(tmp_path, monkeypatch)
    try:
        lab.install_pack("2026.11.3")
        imp = lab.import_file(
            "libraries.csv",
            b"location,type,claim,value\nstarkbank-ecdsa 2.0.0,software,signature_algorithm,ECDSA P-256\n",
        )
        plan = lab.ensure_plan(imp["id"])["id"]
        mine = next(p for p in lab.otto_proposals(plan, ("check",)) if "CVE-2021-43572" in p["title"])
        assert mine["proof"]["title"] == proof.TITLE and "proof" not in proposals.content(mine)
        row = next(r for r in lab.advisories_view(plan)["rows"] if r["id"] == "CVE-2021-43572")
        card = row["panel"]["here"]["rows"][0]["proposal"]
        assert card["proof"]["code"]["label"] == "Written by Otto" and card["status"]["key"] == "proposed"
        # another pack's proposal for the same program has no such part
        other = next(p for p in lab.otto_proposals(plan, ("check",)) if "CVE-2022-21449" in p["title"])
        assert other["proof"] is None
        # accepting runs nothing: the check is in the plan with no run
        lab.otto_decide(plan, mine["id"], "accept")
        added = next(r for r in lab.lab_view(plan)["rows"] if "CVE-2021-43572" in str(r.get("title")))
        assert added["result"] is None
    finally:
        lab.stop()


def test_seeded_fuzz_of_a_damaged_pack_file_is_a_plain_refusal_or_a_normal_read():
    rng = random.Random(20261122)
    seed = raw_pack()
    read = 0
    for _ in range(300):
        raw = bytearray(seed)
        for _ in range(rng.randint(1, 4)):
            at = rng.randrange(len(raw))
            how = rng.random()
            if how < 0.5:
                raw[at] = rng.randrange(256)
            elif how < 0.8:
                del raw[at : at + rng.randint(1, 60)]
            else:
                raw[at:at] = bytes(rng.randrange(32, 127) for _ in range(rng.randint(1, 12)))
        try:
            packs.read_envelope(bytes(raw), keys())
            read += 1
        except packs.PackError as refused:
            assert str(refused)
    assert read == 0  # one changed byte anywhere breaks the fingerprint or the form
    # the content itself, damaged and never signed again: the shape check alone must refuse it or read it, never crash
    content = envelope()["pack"]
    paths = []

    def walk(value, path):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, path + [k])
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, path + [i])
        else:
            paths.append(path)

    walk(content, [])
    for _ in range(400):
        damaged = copy.deepcopy(content)
        for _ in range(rng.randint(1, 3)):
            path = rng.choice(paths)
            node = damaged
            try:
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = rng.choice([None, 0, -1, "", "x" * 50, [], {}, True, 10**12, {"a": 1}, ["x"]])
            except (KeyError, IndexError, TypeError):
                continue
        try:
            packs.check_pack(damaged)
        except packs.PackError as refused:
            assert str(refused)


@pytest.mark.needs_otto
def test_the_pack_a_watched_items_test_proposed_rests_on_is_in_the_evidence_file_whoever_made_it(tmp_path, monkeypatch):
    """The separate review of 22 November 2026: an assessment whose Watch list read "Test proposed" from a pack another
    assessment's run had made, for a library version that pack's copies do not hold, got an evidence file that did not
    verify: the list named a proposed test, and no pack in the file held one."""
    from app.evidence.export import build_evidence
    from evidence import watchlist as check
    from tools import research_demo

    source = research_demo.sandbox_source(tmp_path / "source", 1)
    lab = sandbox_lab(tmp_path, monkeypatch, advisory_source_dir=source)
    try:
        (lab.settings.data_dir / packs.LOCAL_KEY_FILE).write_text(envelope()["public_key"], encoding="ascii")
        lab.settings.otto_local_updates.mkdir(parents=True, exist_ok=True)
        (lab.settings.otto_local_updates / "2026.11.3.json").write_bytes(raw_pack() + b"\n")
        turn_on(lab)
        for version in ("2026.11.1", "2026.11.2", "2026.11.3"):
            lab.install_pack(version)
        # this assessment names a version the pack's copies do not hold; it accepted nothing, and none of its runs made the pack
        imp = lab.import_file(
            "libraries.csv",
            b"location,type,claim,value\nstarkbank-ecdsa 1.2.1,software,signature_algorithm,ECDSA P-256\n",
        )
        plan = lab.ensure_plan(imp["id"])["id"]
        lab.watch_list_look(plan)  # day 1: no fix yet
        research_demo.sandbox_source(source, 2)
        item = next(i for i in lab.watch_list_look(plan)["items"] if i["key"] == "CVE-2021-43572~starkbank-ecdsa")
        assert item["status"]["key"] == "test_proposed", item["status"]
        copies_held = {v["version"] for v in envelope()["pack"]["advisories"][0]["test"]["sandbox"]["set"]["versions"]}
        assert "1.2.1" not in copies_held
        evidence = build_evidence(lab, plan)
        assert "2026.11.3" in [e["pack"]["version"] for e in evidence["otto"]["packs"]]
        assert [i["test"]["key"] for i in evidence["watch_list"]["items"]] == ["test_proposed"]
        outcome = check.check_watch_list(evidence)
        assert outcome.ok, outcome
        # (and with that pack taken out of the file, the same list does not hold: the word has to rest on something in the file)
        evidence["otto"]["packs"] = [e for e in evidence["otto"]["packs"] if e["pack"]["version"] != "2026.11.3"]
        assert not check.check_watch_list(evidence).ok
        # with the switch off the file is what it always was: no Watch list in it, and no pack because of one
        lab.set_sandbox(on=False)
        plain = build_evidence(lab, plan)
        assert "watch_list" not in plain
        assert "2026.11.3" not in [e["pack"]["version"] for e in (plain.get("otto") or {}).get("packs") or []]
    finally:
        lab.stop()
