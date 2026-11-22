"""Sandbox research: How this test was proven, and what the verify command checks about it.

The proof block shows counts, never Passed or Failed: those are the words of an assessment's own run. The verify
command reads a pack's sandbox part as data and holds it to rules that are written out a second time, apart from the
app's own pack reader."""
from __future__ import annotations

import copy
import json

import pytest
from sandbox_fixtures import advisory, envelope

from app.config import OTTO_PACKS_DIR
from app.present import proof
from evidence import otto as verify_otto
from evidence import sandbox as verify

NEVER = ("passed", "failed", "secure", "severity", "score", "critical", "high risk", "low risk")


def _strings(value, skip=("source",)):
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                yield from _strings(item, skip)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, skip)
    elif isinstance(value, str):
        yield value


# ---------------------------------------------------------------- the proof block

def test_the_proof_lays_out_every_part_of_the_trial_with_the_reviewers_count_and_what_had_to_happen():
    block = proof.block(advisory())
    assert block["title"] == "How this test was proven" and block["label"] == "Sandbox copy"
    rows = {r["key"]: r for r in block["table"]["rows"]}
    assert list(rows) == ["reference", "affected", "fixed", "control", "more-fixed-1", "more-fixed-2"]
    assert rows["affected"]["count"] == "1 of 64 cases wrong" and rows["fixed"]["count"] == "All 64 cases right"
    assert rows["control"]["count"] == "64 of 64 cases wrong" and rows["control"]["must"] == "Wrong on every case that must be refused"
    assert "starkbank-ecdsa 2.0.0" in rows["affected"]["label"] and "starkbank-ecdsa 2.0.1" in rows["fixed"]["label"]
    assert all(r["must"] for r in rows.values())


def test_it_never_words_a_result_and_never_rates_anything():
    block = proof.block(advisory())
    for text in _strings(block):
        low = text.lower()
        assert not any(word in low for word in NEVER), text
    assert "does not say how serious the weakness is" in block["not_shown"]
    # no sentence says what Otto did: the tag stays, and the code's author is named as Claude
    assert not any(text.startswith("Otto ") and " Otto's harness" not in text for text in _strings(block))
    assert block["code"]["label"] == "Written by Otto" and "Claude" in block["code"]["line"]


def test_the_registration_is_placed_before_the_first_run_by_the_ledgers_own_order():
    block = proof.block(advisory())
    line = block["registered"]["line"]
    assert "before the first run" in line and "the registration is entry 13 and the first run is entry 14" in line
    names = [p["name"] for p in block["registered"]["pins"]]
    assert "trial_sandbox.py" in names and "qualify.py" in names and any("/set-a-" in n for n in names) and any("/set-b-" in n for n in names)
    assert any(n.startswith("designs/") for n in names) and any("/known-a-" in n for n in names)


def test_the_code_is_shown_as_text_with_the_second_authors_version_and_the_check_it_had_to_pass():
    code = proof.block(advisory())["code"]
    assert code["source"].startswith('"""Asking code for starkbank-ecdsa') and code["second"]["source"] != code["source"]
    assert "gave the same answer on every case: 64 of 64 on starkbank-ecdsa 2.0.0 and 64 of 64 on starkbank-ecdsa 2.0.1" in code["agree_line"]
    assert "24 fresh questions" in code["known_lines"][0] and "12 of 12 accepted, 12 of 12 refused" in code["known_lines"][0]
    assert any("always says yes" in line and "were refused" in line for line in code["known_lines"])
    assert any("ran on the fixed copy only" in line for line in code["known_lines"])


def test_every_copy_says_where_it_came_from_and_a_version_left_out_says_why():
    copies = proof.block(advisory())["copies"]
    assert [r["version"] for r in copies["rows"]] == ["2.0.0", "2.0.1", "2.0.2", "2.3.1"]
    first = copies["rows"][0]
    assert "from PyPI" in first["line"] and "recorded registry answers on this computer" in first["line"] and "the same as the registry's own" in first["line"]
    assert first["sha256"] == "71dec991bf6f5bf80cb0a57141ca69aae87e12a0385105feca87e26e7efa3681"
    assert len(copies["left_out"]) == 2 and all("was left out before the trial was registered" in line for line in copies["left_out"])
    assert "no network" in copies["image_line"] and "first fetch of a version trusts the registry" in copies["trust_line"]


def test_two_authors_that_disagree_are_said_as_that():
    bent = advisory()
    bent["test"]["trial"]["arms"]["affected-b"]["agree"] = 61
    assert "did not give the same answer on every case: 61 of 64" in proof.block(bent)["code"]["agree_line"]


def test_a_test_of_a_pinned_library_has_no_such_block():
    shipped = json.loads((OTTO_PACKS_DIR / "2026.11.2.json").read_text(encoding="utf-8"))["pack"]
    assert all(proof.block(a) is None for a in shipped["advisories"])


# ---------------------------------------------------------------- the verify command's second writing

def test_the_real_packs_sandbox_part_holds():
    lines = verify.check_packs([envelope()], set())
    assert len(lines) == 1 and "1 test tried on sandbox copies" in lines[0] and "second author's version that agreed on every case" in lines[0]
    assert verify.check_packs([json.loads((OTTO_PACKS_DIR / "2026.11.2.json").read_text(encoding="utf-8"))], set()) == []


def _bent(change) -> list[dict]:
    made = copy.deepcopy(envelope())
    change(made["pack"]["advisories"][0])
    return [made]


DRILLS = [
    ("the asking code was edited", lambda a: a["test"]["sandbox"]["set"]["asking"].__setitem__("source", a["test"]["sandbox"]["set"]["asking"]["source"] + "#"), "does not match its fingerprint"),
    ("the second code is the first over again", lambda a: a["test"]["sandbox"]["second"].update(
        source=a["test"]["sandbox"]["set"]["asking"]["source"], sha256=a["test"]["sandbox"]["set"]["asking"]["sha256"]), "first one over again"),
    ("a file of a copy was swapped", lambda a: a["test"]["sandbox"]["set"]["versions"][0]["files"][0].__setitem__("sha256", "0" * 64), "not named by the fingerprint"),
    ("a file without the registry's fingerprint", lambda a: a["test"]["sandbox"]["set"]["versions"][0]["files"][0].__setitem__("registry_fingerprint", "sha256:" + "1" * 64), "registry's own fingerprint"),
    ("the affected version got everything right", lambda a: a["test"]["trial"]["arms"]["affected"].update(right=64, wrong=0), "do not bear out"),
    ("the fixed version got one wrong", lambda a: a["test"]["trial"]["arms"]["fixed"].update(right=63, wrong=1), "do not bear out"),
    ("a further fixed version got one wrong", lambda a: a["test"]["trial"]["arms"]["more-fixed-1"].update(right=63, wrong=1), "do not bear out"),
    ("the control did not fail on every case", lambda a: a["test"]["trial"]["arms"]["accept-all"].update(right=1, wrong=63), "do not bear out"),
    ("the two authors' code disagreed", lambda a: a["test"]["trial"]["arms"]["fixed-b"].__setitem__("agree", 63), "do not bear out"),
    ("the second author's part is missing", lambda a: a["test"]["trial"]["arms"].pop("affected-b"), "do not bear out"),
    ("it was not replayed", lambda a: a["test"]["trial"].__setitem__("replayed", False), "do not bear out"),
    ("a part answered other cases", lambda a: a["test"]["trial"]["arms"]["fixed"].update(total=10, right=10), "exactly the cases of its design"),
    ("a run stands before the registration", lambda a: [e.__setitem__("seq", 999) for e in a["ledger"]
                                                        if e["id"] == a["test"]["sandbox"]["registered"]["hypothesis"]], "before the trial was registered"),
    ("the registration froze no copy set", lambda a: [a["test"]["sandbox"]["registered"]["pins"].pop(k) for k in list(a["test"]["sandbox"]["registered"]["pins"]) if "/set-b-" in k], "did not freeze everything"),
    ("the known-answer check failed on the affected copy", lambda a: a["test"]["sandbox"]["known"]["versions"]["2.0.0"].__setitem__("accepted_valid", 0), "did not pass the known-answer check"),
    ("the known-answer check did not refuse its controls", lambda a: a["test"]["sandbox"]["second_known"].__setitem__("controls_refused", False), "did not refuse its own two controls"),
    ("the sandbox part is not in its form", lambda a: a["test"]["sandbox"].pop("versions"), "not in the form this version writes"),
]


@pytest.mark.parametrize("what, change, word", DRILLS, ids=[d[0] for d in DRILLS])
def test_a_pack_whose_proof_was_bent_is_caught_by_the_verify_command(what, change, word):
    with pytest.raises(verify.SandboxProblem) as caught:
        verify.check_packs(_bent(change), set())
    assert word in str(caught.value), str(caught.value)


def test_a_pack_that_carries_asking_code_under_a_shipped_key_is_caught():
    with pytest.raises(verify.SandboxProblem, match="signed by a key shipped with the app"):
        verify.check_packs([envelope()], {envelope()["public_key"]})


def _run(image: str, name: str = "starkbank-ecdsa", version: str = "2.0.0") -> dict:
    return {"record": {"component": {"name": name, "version": version},
                       "raw": {"batch": {"command": f"docker run --rm -i --pull never --network none {image} python"}}}}


def test_a_run_on_a_sandbox_copy_must_be_in_an_image_a_pack_in_the_file_describes():
    tag = envelope()["pack"]["advisories"][0]["test"]["sandbox"]["set"]["image"]["tag"]
    assert "1 run on a sandbox copy" in verify.check_runs([_run(tag)], [envelope()])[0]
    assert verify.check_runs([_run("evidence-lab-real-python-ecdsa:abc")], [envelope()]) == []        # a pinned library's image is not this module's business
    with pytest.raises(verify.SandboxProblem, match="no test pack in the file says what"):
        verify.check_runs([_run(tag)], [])                                                           # the pack is not in the file
    with pytest.raises(verify.SandboxProblem, match="no test pack in the file says what"):
        verify.check_runs([_run("evidence-lab-sandbox-starkbank-ecdsa:" + "0" * 16)], [envelope()])  # another image
    with pytest.raises(verify.SandboxProblem, match="does not hold the library version the run names"):
        verify.check_runs([_run(tag, version="1.1.0x")], [envelope()])
    with pytest.raises(verify.SandboxProblem, match="does not hold the library version the run names"):
        verify.check_runs([_run(tag, name="python-ecdsa")], [envelope()])


def test_a_damaged_run_or_copy_set_is_a_plain_refusal_never_an_error_of_the_program():
    """The file is data, and so is every part of it: a run that is no table, a version that is a list, a copy set whose
    versions are not a list of tables. Each is refused in a sentence or read as usual."""
    tag = envelope()["pack"]["advisories"][0]["test"]["sandbox"]["set"]["image"]["tag"]
    assert "1 run on a sandbox copy" in verify.check_runs([7, "text", None, [tag], _run(tag)], [envelope()])[0]
    for odd in ([], {}, ["2.0.0"], 2, None, True):
        with pytest.raises(verify.SandboxProblem, match="does not hold the library version the run names"):
            verify.check_runs([_run(tag, version=odd)], [envelope()])
        with pytest.raises(verify.SandboxProblem, match="does not hold the library version the run names"):
            verify.check_runs([_run(tag, name=odd)], [envelope()])
    for odd in ("2.0.0", 7, None, ["2.0.0"], [7, None], {"version": "2.0.0"}):
        bent = envelope()
        bent["pack"]["advisories"][0]["test"]["sandbox"]["set"]["versions"] = odd
        with pytest.raises(verify.SandboxProblem, match="does not hold the library version the run names"):
            verify.check_runs([_run(tag)], [bent])
    assert verify.check_runs([_run(tag)], [7, None, "text", {"pack": 7}, {"pack": {"schema": verify.PACK_SCHEMA_2, "advisories": [7, {"test": 7}]}},
                                           envelope()])[0].startswith("Sandbox research: 1 run")


def test_a_file_with_a_sandbox_run_must_have_its_otto_part():
    tag = envelope()["pack"]["advisories"][0]["test"]["sandbox"]["set"]["image"]["tag"]
    evidence = {"tests": [{"item_id": 1, "kind": "official_vectors", "runs": [_run(tag)]}]}
    assert verify_otto.needs_otto_part(evidence) is True
    assert verify_otto.needs_otto_part({"tests": [{"item_id": 1, "kind": "official_vectors", "runs": [_run("some-other-image:1")]}]}) is False
