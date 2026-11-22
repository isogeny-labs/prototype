"""Phase 5c, second part: what Otto proposes besides checks, and the two proof rows of a library's fix.

  - A library's fix says whether it is proven in two plain rows, the same words wherever it shows: "Proven on public
    copies" (from the pack's trial) and "Proven in this assessment" (from this assessment's own retest).
  - From fixed rules over the results (no model is asked): a failed advisory check on a signing program proposes
    something to fix first on that program's Signatures track; a library of the dependency list that a published
    advisory names proposes "update first".
  - Accept updates the plan or the library's status; Reject keeps it as it was, with the reason. Nothing that was
    graded before moves: a proposal only adds beside what was there.
"""
import json
from pathlib import Path

import pytest

import otto_helpers as helpers
from app.config import DEMO_DIR, OTTO_PACKS_DIR
from app.otto import packs, proposals
from app.present import advisory as present_advisory
from app.present import fixes as present_fixes
from app.present import otto as present_otto
from conftest import demo_plan, make_lab

BANNED = ("secure", "score", "severity", "critical", "time to hack")
DEPENDENCIES = DEMO_DIR / "dependencies-demo.cdx.json"


def _shipped() -> dict[str, dict]:
    """Every advisory of the two shipped packs, by its id (the packs are data in the repository)."""
    found, refused = packs.found_in(OTTO_PACKS_DIR, packs.trusted_keys(Path("/nonexistent")))
    assert not refused and [p.version for p in found] == ["2026.11.1", "2026.11.2"]
    return {a["id"]: a for pack in found for a in pack.pack["advisories"]}


# ---------------------------------------------------------------- the two proof rows (words; no harness needed)

def test_the_first_row_says_what_the_packs_trial_on_public_copies_showed_in_kevins_words():
    shipped = _shipped()
    elliptic = present_otto.public_copies_row(shipped["CVE-2024-42460"]["fix"], shipped["CVE-2024-42460"])
    assert elliptic["line"] == "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes."
    assert elliptic["key"] == "public" and elliptic["badge"] == {"label": "Passed", "tone": "pass"}
    assert elliptic["links"] == [{"label": "See the trial on Advisories", "link": {"page": "advisories", "item": "CVE-2024-42460"}}]
    # the Otto ledger entries behind it: the research ledger's, as the pack carries them
    assert elliptic["ledger"]["title"] == "Otto ledger entries" and elliptic["ledger"]["count"] == len(shipped["CVE-2024-42460"]["ledger"]) > 0
    ecdsa = present_otto.public_copies_row(shipped["CVE-2019-14859"]["fix"], shipped["CVE-2019-14859"])
    assert ecdsa["line"] == "Proven on public copies: Passed. 0.13.2 fails the advisory check; 0.13.3 passes."
    # Java: the advisory check passes on 17.0.3, another locked test still fails there, so it is not proven (Kevin's wording)
    java = present_otto.public_copies_row(shipped["CVE-2022-21449"]["fix"], shipped["CVE-2022-21449"])
    assert java["line"] == ("Proven on public copies: Not proven. 17.0.2 fails the advisory check and 17.0.3 passes it, "
                            "but another locked test still fails on 17.0.3.")
    assert java["badge"] == {"label": "Not proven", "tone": "warn"}
    # without the advisory at hand (only the fix): the same words, and no ledger
    bare = present_otto.public_copies_row(shipped["CVE-2022-21449"]["fix"], None)
    assert bare["text"] == java["text"] and bare["ledger"] is None and bare["links"] == []


def test_the_first_row_never_says_more_than_the_pack_bears_out():
    fix = {"state": "not_proven", "kind": "update", "library": "some-lib", "version": "2.0", "reason": "Not proven: the trial could not finish.",
           "trial": {"arms": {"affected": {"version": "1.9", "failing": 2, "tests": 3}, "fixed": {"version": "2.0", "failing": 0, "tests": 3}}}}
    # not proven with nothing failing on the fixed version: the pack's own sentence, never one of the app's
    assert present_otto.public_copies_row(fix, None)["text"] == "Not proven: the trial could not finish."
    several = {**fix, "trial": {"arms": {"affected": {"version": "1.9"}, "fixed": {"version": "2.0", "failing": 2}}}}
    assert "but 2 other locked tests still fail on 2.0." in present_otto.public_copies_row(several, None)["text"]
    # the advisory check itself still wrong on the fixed version: again the pack's own sentence
    advisory = {"id": "X-1", "ledger": [], "test": {"trial": {"arms": {"fixed": {"wrong": 1}}}}}
    one_failing = {**fix, "trial": {"arms": {"affected": {"version": "1.9"}, "fixed": {"version": "2.0", "failing": 1}}}}
    assert present_otto.public_copies_row(one_failing, advisory)["text"] == "Not proven: the trial could not finish."


def test_the_second_row_says_what_this_assessments_own_retest_showed():
    fix = {"library": "elliptic", "version": "6.5.7"}
    not_yet = present_otto.your_system_row(fix, {"state": "not_yet"})
    assert not_yet["line"] == "Proven in this assessment: Not yet. Update the library, then press Retest."
    assert not_yet["badge"] == {"label": "Not yet", "tone": "neutral"} and not_yet["links"] == [] and not_yet["key"] == "here"
    assert present_otto.your_system_row(fix, None)["line"] == not_yet["line"]
    passed = present_otto.your_system_row(fix, {"state": "passed", "item_id": 12, "finished_at": "2026-11-18T10:20:31Z",
                                                "check": {"code": "passed", "label": "Passed"}, "failing": 0})
    assert passed["badge"] == {"label": "Passed", "tone": "pass"}
    assert passed["text"] == ("On 18 November 2026, 10:20 UTC the retest on elliptic 6.5.7 passed: the advisory check and every other "
                              "locked pass-or-fail test.")
    assert passed["links"] == [{"label": "See the retest's result", "link": {"page": "evidence", "item": "test-12"}}]
    # the same rule as the first row: the check passed, another locked test did not, so it is not proven here either
    other = present_otto.your_system_row({"library": "openjdk", "version": "17.0.3"}, {
        "state": "not_proven", "item_id": 3, "finished_at": "2026-11-18T10:20:31Z", "check": {"code": "passed", "label": "Passed"}, "failing": 1})
    assert other["badge"]["label"] == "Not proven" and other["text"].endswith("the advisory check passed, but another locked test still fails on 17.0.3.")
    still = present_otto.your_system_row(fix, {"state": "not_proven", "item_id": 3, "finished_at": "2026-11-18T10:20:31Z",
                                               "check": {"code": "failed", "label": "Failed"}, "failing": 0})
    assert "the advisory check did not pass (Failed)" in still["text"]
    # every state of this row says plainly what a retest here runs on: a public copy, not the system the customer runs
    for row in (not_yet, passed, other, still):
        assert row["note"] == present_otto.HERE_NOTE and "public copy of the updated version" in row["note"]
        assert row["note"].startswith("This row is about a public copy, not the system you run.") and row["note"] not in row["line"]
        assert "The app has not checked that your own system was updated" in row["note"]
    assert present_otto.public_copies_row({**fix, "state": "proven", "trial": None}, None)["note"] is None
    # "press Retest": since the 5c fixes the button ("Retest new version") is on Checks too, under Retests by version, and
    # the row links there
    with_item = present_otto.your_system_row(fix, {"state": "not_yet", "item_id": 12, "live": False})
    assert with_item["links"] == [{"label": "Retest new version is on Checks", "link": {"page": "checks", "item": None, "group": "encryption"}}]
    assert with_item["line"] == not_yet["line"]                     # the row's own words stay Kevin's
    assert present_otto.your_system_row(fix, {"state": "not_yet", "item_id": 12, "live": True})["links"] == []


def test_the_second_row_reads_passed_only_for_a_whole_retest():
    """Found by the independent review of 18 November 2026: "Passed" must wait for every pass-or-fail test of the
    library in that same retest. While one is running, or after one was interrupted, the row reads "Not yet"."""
    fix = {"library": "openjdk", "version": "17.0.3"}
    base = {"item_id": 9, "finished_at": "2026-11-18T10:20:31Z", "check": {"code": "passed", "label": "Passed"}, "failing": 0, "tests": 4}
    running = present_otto.your_system_row(fix, {**base, "state": "running", "done": 2, "live": True})
    assert running["badge"] == {"label": "Not yet", "tone": "neutral"}
    assert running["text"] == ("A retest on openjdk 17.0.3 is running: 2 of 4 pass-or-fail tests have a result so far. Nothing is proven "
                               "until it has finished.")
    unfinished = present_otto.your_system_row(fix, {**base, "state": "unfinished", "done": 1, "live": False})
    assert unfinished["badge"]["label"] == "Not yet"
    assert unfinished["text"] == "The retest on openjdk 17.0.3 did not finish: 1 of 4 pass-or-fail tests have a result. Press Retest again."
    assert unfinished["links"] == [{"label": "See the retest's result", "link": {"page": "evidence", "item": "test-9"}}]
    starting = present_otto.your_system_row(fix, {"state": "not_yet", "live": True})
    assert starting["badge"]["label"] == "Not yet" and starting["text"].startswith("A retest on openjdk 17.0.3 is running.")
    assert present_otto.your_system_row(fix, {"state": "not_yet", "live": False})["text"] == "Update the library, then press Retest."
    for row in (running, unfinished, starting):
        assert "Passed" not in row["line"] and row["note"] == present_otto.HERE_NOTE
    # a test that could not run did not pass either, and is not said to "fail"
    couldnt = present_otto.your_system_row(fix, {**base, "state": "not_proven", "failing": 1, "done": 4,
                                                  "others": [{"code": "couldnt_run", "label": "Couldn't run"}, {"code": "passed", "label": "Passed"}]})
    assert couldnt["text"].endswith("the advisory check passed, but another locked test did not pass on 17.0.3.")
    failed = present_otto.your_system_row(fix, {**base, "state": "not_proven", "failing": 1, "done": 4,
                                                 "others": [{"code": "failed", "label": "Failed"}]})
    assert failed["text"].endswith("the advisory check passed, but another locked test still fails on 17.0.3.")


def _update_fix(advisory_id: str, here: dict | None = None) -> dict:
    """A failed advisory check's fix as `fix_states` gives it for a library the advisory names."""
    advisory = _shipped()[advisory_id]
    fix = advisory["fix"]
    rows = [present_otto.public_copies_row(fix, advisory), present_otto.your_system_row(fix, here)]
    return {"id": "fix-advisory-cases", "kind": "text", "status": "text_only", "test_kind": "advisory_cases", "source_kind": "failed_tests",
            "answers": [{"item_id": 7, "kind": "advisory_cases", "run_id": 3, "phase": "first"}], "real_library": None,
            "otto_fix": {"advisory": advisory_id, "plain_name": advisory["reading"]["plain_name"], "pack": "2026.11.2", "state": fix["state"],
                         "kind": "update", "library": fix["library"], "version": fix["version"], "summary": fix["summary"], "reason": fix["reason"],
                         "quote": None, "rows": rows, "public": rows[0], "here": here}}


RESULT = {"label": "Failed", "component": "elliptic 6.5.6", "suggested_fix": "x", "advisories": None}


def test_a_librarys_fix_shows_the_two_rows_in_place_of_proof_none():
    """Kevin's review of "Update elliptic to 6.5.7": the title said "proven on public copies" and the row below said
    "Proof: None". Now the title says what to do, and two plain rows say what is proven where."""
    shown = present_fixes.text_fix(_update_fix("CVE-2024-42460"), titles=["Advisory check: Wrongly encoded signature accepted (CVE-2024-42460)"],
                                   is_demo=False, result=RESULT, address=None, tls=None)
    assert shown["title"] == "Update elliptic to 6.5.7" and "proven" not in shown["title"].lower()
    assert shown["status"]["word"] == "Text only" and shown["labels"] == ["From Otto"] and shown["actions"]["buttons"] == []
    assert [row["line"] for row in shown["proof_rows"]] == [
        "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
        "Proven in this assessment: Not yet. Update the library, then press Retest."]
    assert "None." not in shown["proof"]["text"] and "has not applied it or tested it" not in json.dumps(shown)
    said = json.dumps(shown)
    assert "the app offers no code change and no pull request" in said                     # still other people's code
    assert said.count("Proven on public copies: Passed.") == 2                              # the summary's row, and the suggestion's own line
    assert not any(word in said.lower() for word in BANNED)
    # every other text-only fix keeps its one Proof line, exactly as it was
    plain = present_fixes.text_fix({**_update_fix("CVE-2024-42460"), "otto_fix": None}, titles=["Attacker tricks (our short list)"],
                                   is_demo=True, result=RESULT, address=None, tls=None)
    assert plain["proof_rows"] is None and plain["proof"]["text"] == "None. This suggestion is text only: the app has not applied it or tested it."


def test_evidence_and_the_results_own_words_use_the_same_rows():
    java = _update_fix("CVE-2022-21449")
    line = present_fixes.fix_line(java)
    assert (line["lead"], line["rest"], line["button"]) == ("From Otto:", "update openjdk to 17.0.3", "View in Fixes")
    assert line["rows"] == [row["line"] for row in java["otto_fix"]["rows"]] and "Not proven. 17.0.2 fails" in line["rows"][0]
    # a fix that is not a library's from Otto has no rows on its line
    assert "rows" not in present_fixes.fix_line({**java, "otto_fix": None, "real_library": {"fixed": "17.0.3"}})
    # the Suggested fix words of the result itself: the first row, word for word; the second is where the fix is
    words = present_advisory.fix_words("openjdk 17.0.2", {"state": "not_proven", "kind": "update", "library": "openjdk", "version": "17.0.3",
                                                          "reason": "x", "public_line": java["otto_fix"]["rows"][0]["line"]})
    assert java["otto_fix"]["rows"][0]["line"] in words and "Fixes shows whether it is proven in this assessment" in words
    assert "every other locked test still passed" not in words                               # nothing the pack does not bear out


def test_a_program_is_named_with_its_whole_version_also_when_the_version_has_a_hyphen():
    """The speed test's sentence names the program it measured. Otto's registered program is acme-sign 1.4.3-otto."""
    from app.present.results import _version_label
    assert _version_label({"key": "acme-sign-1.4.2"}) == "acme-sign 1.4.2"
    assert _version_label({"key": "acme-sign-1.4.3-otto"}) == "acme-sign 1.4.3-otto"
    assert _version_label({"key": ""}) == "" and _version_label({}) == ""


# ---------------------------------------------------------------- Dependencies: named by an advisory, and "update first"

@pytest.fixture
def listed(tmp_path):
    """The Acme Pay demo with both shipped packs installed and the demo dependency list added. Demo mode; nothing runs."""
    lab = make_lab(tmp_path)
    lab.plan = demo_plan(lab)
    for version in ("2026.11.1", "2026.11.2"):
        lab.check_pack_updates()
        lab.install_pack(version)
    lab.add_dependency_list(lab.plan.id, DEPENDENCIES.name, DEPENDENCIES.read_bytes())
    yield lab
    lab.stop()


def _rows(view: dict) -> dict[str, dict]:
    return {row["label"]: row for group in view["groups"] for row in group["rows"]}


def test_a_library_that_an_advisory_names_says_so_with_what_was_measured_here(listed):
    rows = _rows(listed.dependencies_view(listed.plan.id))
    ecdsa = rows["python-ecdsa 0.13.2"]
    assert [a["line"] for a in ecdsa["advisories"]] == ["Named by advisory CVE-2019-14859: not yet checked",
                                                         "Named by advisory CVE-2019-14853: not yet checked"]
    first, second = ecdsa["advisories"]
    assert first["state"] == {"key": "not_checked", "label": "not yet checked", "tone": "neutral"}
    assert "No check has run on python-ecdsa 0.13.2 here" in first["detail"] and "in the dependency list only" in first["detail"]
    assert first["fixed_line"] == "Its publisher names 0.13.3 as the fixed version; your list has 0.13.2."
    assert first["advisory_link"] == {"page": "advisories", "item": "CVE-2019-14859"} and first["evidence_link"] is None
    assert first["fix_link"] == {"page": "advisories", "item": "CVE-2019-14859"} and first["fix_label"] == "See the proposed fix"
    assert second["detail"] == "This advisory has no test yet, so nothing can be measured." and second["fix_link"] is None
    assert [a["id"] for a in rows["openjdk 17.0.2"]["advisories"]] == ["CVE-2022-21449"]
    assert [a["id"] for a in rows["elliptic 6.5.6"]["advisories"]] == ["CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"]
    # a library no advisory of the packs is about, and one whose version can't be read, say nothing (never a guess)
    for label, row in rows.items():
        if not label.startswith(("python-ecdsa", "openjdk", "elliptic")):
            assert row["advisories"] == [] and row["otto_proposals"] == [] and row["otto_status"] is None, label
    said = json.dumps([row["advisories"] for row in rows.values()]).lower()
    assert not any(word in said for word in BANNED) and "affected" not in said.replace("measured affected", "")


def test_a_version_at_or_past_the_fixed_one_is_not_named(listed):
    doc = json.loads(DEPENDENCIES.read_text())
    text = json.dumps(doc).replace('"0.13.2"', '"0.13.3"').replace("python-ecdsa@0.13.2", "python-ecdsa@0.13.3").replace("ecdsa@0.13.2", "ecdsa@0.13.3")
    listed.add_dependency_list(listed.plan.id, "newer.cdx.json", text.encode())
    rows = _rows(listed.dependencies_view(listed.plan.id))
    assert rows["python-ecdsa 0.13.3"]["advisories"] == [] and rows["python-ecdsa 0.13.3"]["otto_proposals"] == []
    assert rows["openjdk 17.0.2"]["advisories"]                                   # the others are as before


@pytest.mark.needs_otto
def test_otto_proposes_update_first_and_a_person_accepts_or_rejects_it(listed):
    lab, plan_id = listed, listed.plan.id
    before = lab.dependencies_view(plan_id)
    found = lab.otto_proposals(plan_id, ("dependency",))
    assert [(p["about"]["library"], p["about"]["version"], p["about"]["fixed"], p["about"]["advisory"]) for p in found] == [
        ("python-ecdsa", "0.13.2", "0.13.3", "CVE-2019-14859"), ("openjdk", "17.0.2", "17.0.3", "CVE-2022-21449"),
        ("elliptic", "6.5.6", "6.5.7", "CVE-2024-42460")]
    ecdsa, java, _ = found
    assert ecdsa["title"] == "Update python-ecdsa 0.13.2 to 0.13.3 before the move" and ecdsa["label"] == "From Otto"
    assert "Proven on public copies: Passed. 0.13.2 fails the advisory check; 0.13.3 passes." in ecdsa["lines"]
    # Second review, 18 November 2026: the same row's post-quantum answer can name a later version than the advisory's
    # fix (openjdk: 17.0.3 for the advisory, 24 for ML-DSA). The proposal says so, so nobody reads two targets as a clash.
    assert ("This answers the advisory only. For post-quantum, this row's own answers name later versions (24 or later, 27 or later): "
            "an update to one of those is past 17.0.3 too.") in java["lines"]
    assert not any(line.startswith("This answers the advisory only.") for line in ecdsa["lines"])     # no later version is known for it
    assert any("Not proven. 17.0.2 fails the advisory check and 17.0.3 passes it" in line for line in java["lines"])
    assert ecdsa["link"]["page"] == "migration/dependencies" and ecdsa["actions"] == {"accept": None, "reject": None}
    row = _rows(before)["python-ecdsa 0.13.2"]
    assert [p["status"]["word"] for p in row["otto_proposals"]] == ["Proposed"] and row["otto_status"] is None
    assert lab.assessment_view(lab.assessment_for(plan_id=plan_id).id)["waiting"]["items"][-1]["text"] == "3 proposed dependency updates"

    lab.otto_decide(plan_id, ecdsa["id"], "accept")
    lab.otto_decide(plan_id, java["id"], "reject", "Java moves with the platform team")
    after = lab.dependencies_view(plan_id)
    rows = _rows(after)
    assert rows["python-ecdsa 0.13.2"]["otto_status"]["label"] == "Update first"
    # (the line names the library and its version: it is also read on the system's box, far from the library's own row)
    assert "Marked “update first”: python-ecdsa 0.13.2 to 0.13.3. Accepted by You on" in rows["python-ecdsa 0.13.2"]["otto_status"]["lines"][0]
    assert rows["python-ecdsa 0.13.2"]["otto_proposals"][0]["buttons"][0]["label"] == "Undo"
    assert rows["openjdk 17.0.2"]["otto_proposals"][0]["status"]["word"] == "Not added (Java moves with the platform team)"
    assert rows["openjdk 17.0.2"]["otto_status"] is None
    # nothing that was there before moved: every answer, block and blocker line reads exactly as it did
    for label, row in _rows(before).items():
        kept = {k: v for k, v in rows[label].items() if k not in ("advisories", "otto_proposals", "otto_status")}
        assert kept == {k: v for k, v in row.items() if k not in ("advisories", "otto_proposals", "otto_status")}, label
    def without_ottos_lines(view: dict) -> list[dict]:
        return [{k: v for k, v in s.items() if k != "otto_lines"} for s in view["systems"]]
    assert without_ottos_lines(after) == without_ottos_lines(before)
    # accepting ran nothing and measured nothing
    assert not lab.jobs.busy(plan_id) and all(row["job"] is None for row in rows.values())
    # undo takes the mark off again; the decisions stay on the record
    lab.otto_decide(plan_id, ecdsa["id"], "undo")
    undone = _rows(lab.dependencies_view(plan_id))["python-ecdsa 0.13.2"]
    assert undone["otto_status"] is None and undone["otto_proposals"][0]["status"]["word"] == "Proposed"
    assert undone["otto_proposals"][0]["history"]["count"] == 2


def _list_with(change) -> bytes:
    """The demo dependency list after `change(doc)`, as a file's bytes."""
    doc = json.loads(DEPENDENCIES.read_text())
    change(doc)
    return json.dumps(doc).encode()


def _without(doc: dict, name: str) -> None:
    gone = {c.get("bom-ref") for c in doc["components"] if c["name"] == name}
    doc["components"] = [c for c in doc["components"] if c["name"] != name]
    for d in doc.get("dependencies", []):
        d["dependsOn"] = [ref for ref in d.get("dependsOn", []) if ref not in gone]
    doc["dependencies"] = [d for d in doc.get("dependencies", []) if d.get("ref") not in gone]


def test_a_package_of_the_same_name_from_another_place_is_not_named(listed):
    """Found by the independent review of 18 November 2026. The advisories about elliptic are about the npm package. A
    package called elliptic from PyPI is another program: the knowledge base does not recognise it, so it is not named,
    and Otto proposes nothing for it. A name is never matched by itself."""
    def to_pypi(doc):
        for c in doc["components"]:
            if c["name"] == "elliptic":
                c["purl"] = "pkg:pypi/elliptic@6.5.6"
    listed.add_dependency_list(listed.plan.id, "other.cdx.json", _list_with(to_pypi))
    rows = _rows(listed.dependencies_view(listed.plan.id))
    assert rows["elliptic 6.5.6"]["advisories"] == [] and rows["elliptic 6.5.6"]["otto_proposals"] == []
    assert rows["python-ecdsa 0.13.2"]["advisories"] and rows["openjdk 17.0.2"]["advisories"]          # recognised by their own addresses
    assert not any(p["about"]["library"] == "elliptic" for p in listed.otto_proposals(listed.plan.id, ("dependency",)))


@pytest.mark.needs_otto
def test_a_decision_stays_with_its_library_and_version_when_a_newer_list_is_added(listed):
    """Found by the independent review of 18 November 2026: a decision was tied to a row's place in the list, so with a
    newer list "Update first" could land on whatever library stood in that place. It is tied to the library, its
    version and the advisory. A decision on a library that is no longer in the list stays on the record and marks no row."""
    lab, plan_id = listed, listed.plan.id
    ecdsa, java, _ = lab.otto_proposals(plan_id, ("dependency",))
    lab.otto_decide(plan_id, java["id"], "accept")
    lab.otto_decide(plan_id, ecdsa["id"], "accept")
    assert _rows(lab.dependencies_view(plan_id))["openjdk 17.0.2"]["otto_status"]["label"] == "Update first"
    # a newer list, without openjdk: every row after it moves up one place
    lab.add_dependency_list(plan_id, "newer.cdx.json", _list_with(lambda doc: _without(doc, "openjdk")))
    rows = _rows(lab.dependencies_view(plan_id))
    assert "openjdk 17.0.2" not in rows
    marked = sorted(label for label, row in rows.items() if row["otto_status"])
    assert marked == ["python-ecdsa 0.13.2"]                           # its own decision came along; nothing else is marked
    assert rows["python-ecdsa 0.13.2"]["otto_proposals"][0]["id"] == ecdsa["id"]
    assert all(not row["otto_proposals"] for label, row in rows.items() if not label.startswith(("python-ecdsa", "elliptic")))
    # the decision on openjdk is still on the record, as a proposal Otto no longer makes here
    kept = next(p for p in lab.otto_proposals(plan_id, ("dependency",)) if p["id"] == java["id"])
    assert kept["current"] is False and kept["state"] == "accepted" and len(kept["decisions"]) == 1
    assert all(reason for reason in kept["actions"].values())
    assert lab.otto_waiting(plan_id)["dependency"] == 1                 # elliptic's, still undecided
    # and it comes back with its library: the first list again, and openjdk reads "Update first" as decided
    lab.add_dependency_list(plan_id, DEPENDENCIES.name, DEPENDENCIES.read_bytes())
    assert _rows(lab.dependencies_view(plan_id))["openjdk 17.0.2"]["otto_status"]["label"] == "Update first"


@pytest.mark.needs_otto
def test_the_project_overview_says_which_updates_the_newest_pack_brought(listed):
    """What changed since the last pack: the checks it brought, and the updates it brought for libraries its advisories
    name. Counts only, from the same proposals the pages show."""
    lab, plan_id = listed, listed.plan.id
    a = lab.assessment_for(plan_id=plan_id)
    row, = lab.otto_project_block([a])["rows"]
    # the newest pack (2026.11.2) brought one check for acme-sign and one update (elliptic); the first pack's are not counted here
    assert row["since"] == ["It brought 1 proposed check for this assessment: 1 waiting.",
                            "It also brought 1 proposed dependency update for libraries its advisories name: 1 waiting."]
    elliptic = next(p for p in lab.otto_proposals(plan_id, ("dependency",)) if p["about"]["library"] == "elliptic")
    lab.otto_decide(plan_id, elliptic["id"], "accept")
    row, = lab.otto_project_block([a])["rows"]
    assert row["since"][1] == "It also brought 1 proposed dependency update for libraries its advisories name: 1 accepted."
    assert row["since"][2] == "1 decision recorded since."


@pytest.mark.needs_otto
def test_an_accepted_update_shows_on_the_system_its_entry_is_tied_to_and_never_among_the_blockers(listed):
    lab, plan_id = listed, listed.plan.id
    view = lab.dependencies_view(plan_id)
    ledger_top = next(g for g in view["groups"] if g["label"].startswith("acme-ledger"))
    system = next(o["key"] for o in ledger_top["picker"]["options"] if o["key"].startswith("software:"))
    lab.tie_dependency(plan_id, ledger_top["key"], system)
    tied = lab.dependencies_view(plan_id)
    box = next(s for s in tied["systems"] if s["key"] == system)
    blockers = [line["text"] for line in box["blocker_lines"]]
    assert box["otto_lines"] == []
    proposal = next(p for p in lab.otto_proposals(plan_id, ("dependency",)) if p["about"]["library"] == "elliptic")
    lab.otto_decide(plan_id, proposal["id"], "accept")
    box = next(s for s in lab.dependencies_view(plan_id)["systems"] if s["key"] == system)
    assert len(box["otto_lines"]) == 1 and "Marked “update first”: elliptic 6.5.6 to 6.5.7." in box["otto_lines"][0]
    assert [line["text"] for line in box["blocker_lines"]] == blockers            # the blockers the answer key grades are untouched


# ---------------------------------------------------------------- Migration: something to fix first, from a result

@pytest.fixture
def failed_check(tmp_path, monkeypatch, request):
    """The Acme Pay demo with a pack made for the test (its check fails on acme-sign 1.4.2), and the migration status
    measured, as a plan change needs a plan. `indirect` with "not_measured" leaves the status unmeasured."""
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    lab.plan = demo_plan(lab)
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    lab.migration_view(lab.plan.id)                      # the Migration step, opened (nothing is measured by opening it)
    if getattr(request, "param", "measured") == "measured":
        lab.measure_migration(lab.plan.id)               # Measure status: every system has its place on the plan
        lab.wait_until_measured(lab.plan.id, 300)
    yield lab
    lab.stop()


def _strip(view: dict) -> dict:
    """The migration view without what phase 5c added beside it."""
    out = json.loads(json.dumps(view))
    for system in out["systems"]:
        system.pop("otto", None)
    for band in out["roadmap"]["bands"]:
        for row in band["rows"]:
            row.pop("otto", None)
    out["roadmap"].pop("download", None)      # Download evidence opens with the first result of any test: not Otto's doing
    return out


@pytest.mark.needs_otto
@pytest.mark.slow          # (about five seconds: it runs a check and measures the migration status)
@pytest.mark.parametrize("failed_check", ["not_measured"], indirect=True)
def test_a_failed_advisory_check_proposes_something_to_fix_first_on_the_programs_track(failed_check, monkeypatch):
    """The one rule for plan changes. Also (second review, 18 November 2026): with the status not measured, the Overview
    counted "1 proposed change to the migration plan" while the Roadmap read "there is no plan". A change to a plan
    needs a plan: nothing is proposed until Measure status has placed the system, and then the same result proposes it."""
    lab, plan_id = failed_check, failed_check.plan.id
    assert lab.otto_proposals(plan_id, ("plan",)) == []                            # no check yet: nothing is proposed
    helpers.accept_checks(lab, plan_id)
    item = next(t["id"] for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases")
    assert lab.otto_proposals(plan_id, ("plan",)) == []                            # accepted, not run: still nothing to propose
    lab.run_test(plan_id, item)
    lab.wait_until_idle(plan_id, 240)
    # the check has failed, and the status is not measured: the system has no place on the plan, so nothing is proposed
    assert lab.otto_proposals(plan_id, ("plan",)) == [] and lab.otto_waiting(plan_id)["plan"] == 0
    unplaced = lab.migration_view(plan_id)
    assert all(s["otto"] is None for s in unplaced["systems"])
    assert all(row["otto"] is None for band in unplaced["roadmap"]["bands"] for row in band["rows"])
    lab.measure_migration(plan_id)                                                 # Measure status, as a person presses it
    lab.wait_until_measured(plan_id, 300)
    assert lab.otto_waiting(plan_id)["plan"] == 1
    proposal, = lab.otto_proposals(plan_id, ("plan",))
    assert proposal["title"] == "Fix acme-sign 1.4.2 before its signatures move to post-quantum" and proposal["label"] == "From Otto"
    assert proposal["why"].startswith("acme-sign 1.4.2 gave the wrong answer on 2 published cases of the kind CVE-2022-21449 describes")
    assert proposal["about"]["track"] == "signatures" and proposal["about"]["item"] == item and proposal["link"]["page"] == "migration/systems"
    view = lab.migration_view(plan_id)
    program = next(s for s in view["systems"] if s["name"] == "acme-sign 1.4.2")
    assert program["otto"]["title"] == "From Otto: proposed changes to this system's plan"
    shown, = program["otto"]["proposals"]
    assert shown["status"]["word"] == "Proposed" and [b["label"] for b in shown["buttons"]] == ["Accept", "Reject"]
    assert all(s["otto"] is None for s in view["systems"] if s["name"] != "acme-sign 1.4.2")
    marks = [row["otto"] for band in view["roadmap"]["bands"] for row in band["rows"] if row["name"] == "acme-sign 1.4.2"]
    assert marks and all(m == {"label": "From Otto", "text": "1 proposal waiting for your decision", "tone": "warn", "waiting": 1} for m in marks)
    # everything the migration answer key grades reads exactly as the same page does with Otto's part left out: the
    # proposal only stands beside it
    with monkeypatch.context() as without:
        without.setattr(lab, "_otto_checks", lambda db, plan_id: [])
        plain = lab.migration_view(plan_id)
    assert all(s["otto"] is None for s in plain["systems"]) and all(r["otto"] is None for b in plain["roadmap"]["bands"] for r in b["rows"])
    before = _strip(plain)
    assert _strip(view)["systems"] == before["systems"] and _strip(view)["roadmap"] == before["roadmap"]
    # Fixes lists no entry for a plan change: it is decided on Migration
    assert not any(f.get("title") == proposal["title"] for f in lab.fixes_view(plan_id)["fixes"])

    lab.otto_decide(plan_id, proposal["id"], "accept")
    accepted = lab.migration_view(plan_id)
    shown, = next(s for s in accepted["systems"] if s["name"] == "acme-sign 1.4.2")["otto"]["proposals"]
    assert shown["status"]["word"] == "Accepted" and shown["effect"] == "On the plan: something to fix first, on the Signatures track."
    assert [b["label"] for b in shown["buttons"]] == ["Undo"]
    mark = next(row["otto"] for band in accepted["roadmap"]["bands"] for row in band["rows"] if row["name"] == "acme-sign 1.4.2")
    assert mark["waiting"] == 0 and mark["text"] == "On the plan: something to fix first, on the Signatures track."
    assert _strip(accepted)["systems"] == before["systems"] and _strip(accepted)["roadmap"] == before["roadmap"]       # accepting changed none of it
    # Reject keeps the plan as it was, with the reason (shown here on the same proposal after an undo)
    lab.otto_decide(plan_id, proposal["id"], "undo")
    lab.otto_decide(plan_id, proposal["id"], "reject", "We retire this program in January")
    rejected = lab.migration_view(plan_id)
    shown, = next(s for s in rejected["systems"] if s["name"] == "acme-sign 1.4.2")["otto"]["proposals"]
    assert shown["status"]["word"] == "Not added (We retire this program in January)" and [b["label"] for b in shown["buttons"]] == ["Reconsider"]
    assert not any(word in json.dumps(program["otto"]).lower() for word in BANNED)


@pytest.mark.needs_otto
@pytest.mark.parametrize("failed_check", ["not_measured"], indirect=True)       # (nothing here needs a measured status)
def test_a_result_of_an_advisory_check_says_where_the_check_came_from_and_who_decided(failed_check):
    """Kevin, 18 November 2026: "Evidence: each result from an Otto check shows the advisory, the test design, the trial on
    public copies, the ledger entries, and the accept/reject decisions with who and when." The block repeats records;
    the result stays the test's own."""
    lab, plan_id = failed_check, failed_check.plan.id
    proposal, = lab.otto_proposals(plan_id, ("check",))
    lab.otto_decide(plan_id, proposal["id"], "reject", "Not this quarter")
    lab.otto_decide(plan_id, proposal["id"], "reconsider")
    lab.otto_decide(plan_id, proposal["id"], "accept")
    item = next(t["id"] for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases")
    lab.run_test(plan_id, item)
    lab.wait_until_idle(plan_id, 240)
    rows = lab.lab_view(plan_id)["rows"]
    result = next(r for r in rows if r["item_id"] == item)["result"]
    block = result["otto"]
    assert (block["label"], block["title"]) == ("From Otto", "Where this check came from")
    assert "CVE-2022-21449" in block["line"] and "in test pack 2026.11.1." in block["line"] and "Accepted by You on " in block["line"]
    assert block["advisory"] == {"label": "Open the advisory", "link": {"page": "advisories", "item": "CVE-2022-21449"}}
    assert block["design"]["lines"][0] == f"Design fingerprint (SHA-256): {proposal['about']['design']}"
    # the trial on public copies, in the counts its signed pack records
    assert block["trial"]["lines"][0] == "acme-sign 1.4.2 (affected): 2 of 64 cases wrong."
    assert any("control that must fail" in line and "64 of 64" in line for line in block["trial"]["lines"])
    # every decision, with who and when, and the reason of the rejection
    decisions = block["decisions"]["rows"]
    assert [d["word"] for d in decisions] == ["Rejected", "Taken up again", "Accepted"] and block["decisions"]["count"] == 3
    assert decisions[0]["reason"] == "Not this quarter" and all(d["by"] == "You" and d["at"] and d["ledger_entry"] for d in decisions)
    assert "one login" in block["decisions"]["footnote"]
    # the Otto ledger entries of the check and of those decisions, in the order they were written
    entries = block["ledger"]["entries"]
    assert [e["seq"] for e in entries] == sorted(e["seq"] for e in entries) and block["ledger"]["count"] == len(entries)
    whats = [e["what"] for e in entries]
    assert whats[0].startswith("Proposal entry") and sum(w.startswith("Decision ") for w in whats) == 3
    lock, bound = (next(n for n, w in enumerate(whats) if w.startswith(head)) for head in ("Lock entry", "Run "))
    assert lock < bound                                                    # locked before it could run
    assert "holds no result" in block["ledger"]["note"] and block["note"].endswith("The result comes only from the test.")
    # the result itself is the reviewer's, untouched; and only an advisory check carries the block
    assert result["label"] == "Failed" and all("otto" not in (r["result"] or {}) for r in rows if r["item_id"] != item)
    assert not any(word in json.dumps(block).lower() for word in BANNED)
    # the same block on the check's own panel (Checks), which reads the result the same way
    check_id = next(r["id"] for r in lab.ledger(plan_id)["rows"] if r.get("item_id") == item)
    assert lab.check_detail(plan_id, check_id)["result"]["otto"] == block


@pytest.mark.needs_otto
@pytest.mark.slow
def test_an_accepted_plan_change_reads_done_once_the_check_passes_and_an_undecided_one_is_no_longer_proposed(failed_check):
    from conftest import play_back_speed
    lab, plan_id = failed_check, failed_check.plan.id
    helpers.accept_checks(lab, plan_id)
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    proposal, = lab.otto_proposals(plan_id, ("plan",))
    lab.otto_decide(plan_id, proposal["id"], "accept")
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    done, = lab.otto_proposals(plan_id, ("plan",))
    assert done["id"] == proposal["id"] and done["state"] == "accepted" and done["facts"]["done"]["version"] == "1.4.3"
    assert "passed since" in done["actions"]["undo"]
    shown = present_otto.proposal_view(done)
    assert shown["effect"].startswith("Done: the check for CVE-2022-21449 passed on acme-sign 1.4.3, on ")      # names the check
    assert done["why"].startswith("acme-sign 1.4.2 gave the wrong answer on 2 published cases")     # still told from the failure it came from


@pytest.mark.needs_otto
@pytest.mark.slow
def test_a_check_added_after_a_retest_is_not_said_to_have_run_on_the_retested_version(failed_check):
    """Found by the second review of 18 November 2026: Evidence read "the same eight locked tests, run on A and then on
    B" while a check accepted after the retest had run on A only."""
    from conftest import play_back_speed
    lab, plan_id = failed_check, failed_check.plan.id
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    whole = "".join(p["v"] for p in lab.lab_view(plan_id)["subline"] if p["t"] != "time")
    assert whole == "Before and after: the same five locked tests, run on acme-sign 1.4.2 and then on acme-sign 1.4.3. Retest finished ."
    helpers.accept_checks(lab, plan_id)
    item = next(t["id"] for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases")
    lab.run_test(plan_id, item)
    lab.wait_until_idle(plan_id, 240)
    view = lab.lab_view(plan_id)
    partly = "".join(p["v"] for p in view["subline"] if p["t"] != "time")
    assert partly == ("Before and after: five of the six locked tests were run on acme-sign 1.4.2 and then on acme-sign 1.4.3. "
                      "Retest finished . The other one has no result after yet: retest again to run every test in the plan on "
                      "acme-sign 1.4.3.")
    row = next(r for r in view["rows"] if r["item_id"] == item)
    assert row["result"]["label"] == "Failed" and row["after"] is None
    # Advisories says the same thing: this result is of the version the row names, so it carries no line about a retest
    shown = lab.advisories_view(plan_id)["rows"][0]
    assert shown["result"]["label"] == "Failed" and shown["result"]["text"] is None
    assert shown["panel"]["here"]["rows"][0]["result"]["ran_on"] is None


@pytest.mark.needs_otto
@pytest.mark.slow
def test_an_undecided_plan_change_is_no_longer_proposed_once_the_check_passes(failed_check):
    from conftest import play_back_speed
    lab, plan_id = failed_check, failed_check.plan.id
    helpers.accept_checks(lab, plan_id)
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    assert len(lab.otto_proposals(plan_id, ("plan",))) == 1
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    assert lab.otto_proposals(plan_id, ("plan",)) == []
    assert lab.otto_waiting(plan_id)["plan"] == 0


@pytest.mark.needs_otto
@pytest.mark.slow
def test_a_plan_change_that_is_open_again_is_no_longer_proposed_once_the_check_passes(failed_check):
    """Found by the independent review of 18 November 2026: accepted and then undone, it was still proposed after the
    check had passed (and accepting it then read "Done" at once). It is open, so it is no longer proposed; its two
    decisions stay on the record."""
    from conftest import play_back_speed
    lab, plan_id = failed_check, failed_check.plan.id
    helpers.accept_checks(lab, plan_id)
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    proposal, = lab.otto_proposals(plan_id, ("plan",))
    lab.otto_decide(plan_id, proposal["id"], "accept")
    lab.otto_decide(plan_id, proposal["id"], "undo")
    assert lab.otto_waiting(plan_id)["plan"] == 1                       # open again while the check still fails
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    after, = lab.otto_proposals(plan_id, ("plan",))
    assert after["id"] == proposal["id"] and after["state"] == "proposed" and after["current"] is False
    assert [d["decision"] for d in after["decisions"]] == ["accept", "undo"]
    assert after["actions"] and all(reason for reason in after["actions"].values())
    assert lab.otto_waiting(plan_id)["plan"] == 0
    view = lab.migration_view(plan_id)
    assert all(s["otto"] is None for s in view["systems"])
    assert all(row["otto"] is None for band in view["roadmap"]["bands"] for row in band["rows"])


@pytest.mark.needs_otto
@pytest.mark.slow
def test_proven_here_needs_every_pass_or_fail_test_of_the_program_in_the_same_retest(failed_check, monkeypatch):
    """The rule behind "Proven in this assessment", on the app's own runs (found by the independent review of 18 November
    2026: the row read "Passed" as soon as the advisory check's own retest run had passed, while the others were
    still running, and stayed so when a retest was interrupted)."""
    from app.db import PlanItemRow, RetestRow
    from conftest import play_back_speed
    lab, plan_id = failed_check, failed_check.plan.id
    helpers.accept_checks(lab, plan_id)
    play_back_speed(lab)
    lab.run_all(plan_id)
    lab.wait_until_idle(plan_id, 300)
    check = next(t["id"] for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases")

    def here() -> dict:
        with lab.db() as db:
            return lab._proven_here(db, db.get(PlanItemRow, check), "acme-sign", "1.4.3")
    assert here() == {"state": "not_yet", "library": "acme-sign", "version": "1.4.3", "item_id": check, "live": False}
    lab.start_retest(plan_id, "1.4.3")
    lab.wait_until_idle(plan_id, 300)
    whole = here()
    assert whole["state"] == "passed" and (whole["tests"], whole["done"], whole["failing"]) == (3, 3, 0) and whole["missing"] == []
    assert sorted(o["kind"] for o in whole["others"]) == ["bad_signatures", "official_vectors"]
    # a second retest of which only this check's run exists (as when the app is stopped part-way): nothing is proven by it
    with lab._plan_lock, lab.db() as db:
        retest = RetestRow(plan_id=plan_id, baseline_version="1.4.2", version="1.4.3")
        db.add(retest)
        db.commit()
        lab._submit(lab._plan(db, plan_id), db.get(PlanItemRow, check), "retest", retest)
    lab.wait_until_idle(plan_id, 300)
    half = here()
    assert half["state"] == "unfinished" and (half["tests"], half["done"]) == (3, 1) and len(half["missing"]) == 2 and half["live"] is False
    row = present_otto.your_system_row({"library": "acme-sign", "version": "1.4.3"}, half)
    assert row["badge"]["label"] == "Not yet" and "did not finish: 1 of 3 pass-or-fail tests have a result. Press Retest again." in row["text"]

    # ... and while the others of that retest are still running, it reads as running
    class Busy:
        status = "running"
    missing = {m["item_id"] for m in half["missing"]}
    monkeypatch.setattr(lab.jobs, "get", lambda key: Busy() if key[0] in missing and key[1] == "retest" else None)
    going = here()
    assert going["state"] == "running" and going["live"] is True and going["done"] == 1


def test_a_later_version_is_named_only_when_it_can_be_read_and_is_past_the_fixed_one():
    row = {"answers": {"mldsa": {"answer": "no", "first_version": "24"}, "hybrid": {"answer": "no", "first_version": "none_known"},
                       "other": {"answer": "yes", "first_version": None}, "older": {"answer": "no", "first_version": "21.0.1"},
                       "again": {"answer": "no", "first_version": "24"}}}
    assert proposals._later_targets(row, "17.0.3") == ["21.0.1", "24"]        # oldest first, each once, only the ones that can be read
    assert proposals._later_targets(row, "21.0.1") == ["24"] and proposals._later_targets(row, "24") == [] == proposals._later_targets(row, "25.0.1")
    assert proposals._later_targets({"answers": {"q": {"answer": "yes", "first_version": "30"}}}, "17.0.3") == []     # not a "no": nothing to update for
    assert proposals._later_targets(None, "17.0.3") == [] == proposals._later_targets(row, "not a version")
    assert proposals._later_targets({"answers": {"q": {"answer": "no", "first_version": "soon"}}}, "17.0.3") == []    # never guessed
    assert proposals._later_line(row, "21.0.1") == ("This answers the advisory only. For post-quantum, this row's own answer names 24 or "
                                                    "later: an update to that version is past 21.0.1 too.")
    assert proposals._later_line(row, "24") == ""


def test_fixes_says_where_a_plan_change_is_decided_and_asks_for_no_decision_where_none_can_be_recorded():
    """Fixes lists no entry for a plan change. Where its Migration group is empty it says where they are; where the
    buttons are off (a closed assessment, Otto not installed) it counts and asks for nothing (third review, 18 November
    2026: the same fault had just been taken out of Advisories)."""
    def proposal(state: str, accept: str | None = None) -> dict:
        return {"state": state, "actions": ({"accept": accept, "reject": accept} if state == "proposed" else {"undo": None})}
    line = present_otto.fixes_plan_line
    assert line([]) is None and line([proposal("rejected")]) is None
    assert line([proposal("proposed")]) == ("1 change to the migration plan is proposed from a result. You accept or reject it on "
                                            "Migration, under Systems.")
    assert line([proposal("proposed"), proposal("proposed")]).startswith("2 changes to the migration plan are proposed from a result. You "
                                                                         "accept or reject each one")
    off = "This assessment is closed, so nothing more can be decided in it."
    blocked = line([proposal("proposed", off)])
    assert blocked == "1 change to the migration plan, proposed from a result, has no decision: it is on Migration, under Systems."
    assert "accept or reject" not in blocked
    assert line([proposal("accepted")]) == "1 proposed change to the plan is accepted: it is on Migration, under Systems."
    both = line([proposal("proposed"), proposal("accepted"), proposal("accepted")])
    assert both.startswith("1 change to the migration plan is proposed") and both.endswith("2 proposed changes to the plan are accepted: they are on Migration, under Systems.")


def test_two_entries_for_the_same_update_of_a_library_name_each_other():
    """Found by the second review of 18 November 2026: Fixes listed "Update elliptic to the fixed version (6.5.7)" and
    Otto's "Update elliptic to 6.5.7" as two entries, with nothing to say they are one update."""
    from app.present import fixes as present_fixes

    def shown(title: str) -> dict:
        return {"title": title, "what": {"paragraphs": [[{"t": "text", "v": "What it suggests."}]]}}
    ottos = ({"kind": "text", "otto_fix": {"kind": "update", "library": "elliptic", "version": "6.5.7"}}, shown("Update elliptic to 6.5.7"))
    older = ({"kind": "text", "real_library": {"name": "Elliptic", "version": "6.5.6", "fixed": "6.5.7"}},
             shown("Update elliptic to the fixed version (6.5.7)"))
    other = ({"kind": "text", "real_library": {"name": "python-ecdsa", "version": "0.13.2", "fixed": "0.13.3"}}, shown("Update python-ecdsa"))
    another_version = ({"kind": "text", "real_library": {"name": "elliptic", "version": "6.5.4", "fixed": "6.5.5"}}, shown("Update elliptic (6.5.5)"))
    present_fixes.link_same_updates([ottos, older, other, another_version])
    said = [p[0]["v"] for p in ottos[1]["what"]["paragraphs"]]
    assert len(said) == 2 and "“Update elliptic to the fixed version (6.5.7)”" in said[1] and said[1].endswith("It is one update, not two.")
    back = [p[0]["v"] for p in older[1]["what"]["paragraphs"]]
    assert len(back) == 2 and "“Update elliptic to 6.5.7”" in back[1] and back[1].endswith("It is one update, not two.")
    assert "accept or reject" not in back[1]                  # it names the entry; the entry's own card has the buttons, or says why not
    assert len(other[1]["what"]["paragraphs"]) == 1 and len(another_version[1]["what"]["paragraphs"]) == 1      # another library, another version


def test_the_ids_of_proposals_do_not_change_with_what_else_is_in_the_plan():
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1") == proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1")
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1") != proposals.check_id("CVE-2022-21449", "a" * 64, "ref-2")
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1").startswith("check-cve-2022-21449-")
    assert proposals.code_fix_id("otto-cve-2022-21449") == "fix-code-otto-cve-2022-21449" and proposals.update_fix_id(12) == "fix-update-12"
    assert proposals.plan_id_for("software:x", 3).startswith("plan-") and proposals.dependency_id("elliptic", "6.5.6", "CVE-1").startswith("dep-")
    # a dependency proposal is for a library in a version and an advisory, wherever the list names it
    assert proposals.dependency_id("Elliptic", "6.5.6", "CVE-1") == proposals.dependency_id("elliptic", "6.5.6", "CVE-1")
    assert proposals.dependency_id("elliptic", "6.5.6", "CVE-1") != proposals.dependency_id("elliptic", "6.5.5", "CVE-1")
    for made in ("check-x", "fix-code-x", "fix-update-3", "plan-abc", "dep-abc"):
        assert proposals._kind_of_id(made) in proposals.KINDS
    assert proposals._kind_of_id("nonsense") is None
