"""Phase 5c, second part: what Otto proposes besides checks, and the two proof rows of a library's fix.

  - A library's fix says whether it is proven in two plain rows, the same words wherever it shows: "Proven on public
    copies" (from the pack's trial) and "Proven on your system" (from this assessment's own retest).
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
    assert not_yet["line"] == "Proven on your system: Not yet. Update the library, then press Retest."
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
        assert "does not connect to the system you run" in row["note"] and row["note"] not in row["line"]
    assert present_otto.public_copies_row({**fix, "state": "proven", "trial": None}, None)["note"] is None


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
        "Proven on your system: Not yet. Update the library, then press Retest."]
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
    assert java["otto_fix"]["rows"][0]["line"] in words and "Fixes shows whether it is proven on your system" in words
    assert "every other locked test still passed" not in words                               # nothing the pack does not bear out


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
    assert "Marked “update first”: to 0.13.3. Accepted by You on" in rows["python-ecdsa 0.13.2"]["otto_status"]["lines"][0]
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
    assert len(box["otto_lines"]) == 1 and "Marked “update first”: to 6.5.7." in box["otto_lines"][0]
    assert [line["text"] for line in box["blocker_lines"]] == blockers            # the blockers the answer key grades are untouched


# ---------------------------------------------------------------- Migration: something to fix first, from a result

@pytest.fixture
def failed_check(tmp_path, monkeypatch):
    """The Acme Pay demo with a pack made for the test: its check accepted and run once (it fails on acme-sign 1.4.2)."""
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    lab.plan = demo_plan(lab)
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    lab.migration_view(lab.plan.id)                      # the Migration step, opened (nothing is measured by opening it)
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
def test_a_failed_advisory_check_proposes_something_to_fix_first_on_the_programs_track(failed_check):
    lab, plan_id = failed_check, failed_check.plan.id
    before = lab.migration_view(plan_id)
    assert all(s["otto"] is None for s in before["systems"])                       # no check yet: nothing is proposed
    assert lab.otto_proposals(plan_id, ("plan",)) == []
    helpers.accept_checks(lab, plan_id)
    item = next(t["id"] for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases")
    assert lab.otto_proposals(plan_id, ("plan",)) == []                            # accepted, not run: still nothing to propose
    lab.run_test(plan_id, item)
    lab.wait_until_idle(plan_id, 240)
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
    # everything the migration answer key grades reads exactly as before: the proposal only stands beside it
    assert _strip(view)["systems"] == _strip(before)["systems"] and _strip(view)["roadmap"] == _strip(before)["roadmap"]

    lab.otto_decide(plan_id, proposal["id"], "accept")
    accepted = lab.migration_view(plan_id)
    shown, = next(s for s in accepted["systems"] if s["name"] == "acme-sign 1.4.2")["otto"]["proposals"]
    assert shown["status"]["word"] == "Accepted" and shown["effect"] == "On the plan: something to fix first, on the Signatures track."
    assert [b["label"] for b in shown["buttons"]] == ["Undo"]
    mark = next(row["otto"] for band in accepted["roadmap"]["bands"] for row in band["rows"] if row["name"] == "acme-sign 1.4.2")
    assert mark["waiting"] == 0 and mark["text"] == "On the plan: something to fix first, on the Signatures track."
    assert _strip(accepted)["systems"] == _strip(before)["systems"] and _strip(accepted)["roadmap"] == _strip(before)["roadmap"]
    # Reject keeps the plan as it was, with the reason (shown here on the same proposal after an undo)
    lab.otto_decide(plan_id, proposal["id"], "undo")
    lab.otto_decide(plan_id, proposal["id"], "reject", "We retire this program in January")
    rejected = lab.migration_view(plan_id)
    shown, = next(s for s in rejected["systems"] if s["name"] == "acme-sign 1.4.2")["otto"]["proposals"]
    assert shown["status"]["word"] == "Not added (We retire this program in January)" and [b["label"] for b in shown["buttons"]] == ["Reconsider"]
    assert not any(word in json.dumps(program["otto"]).lower() for word in BANNED)


@pytest.mark.needs_otto
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
    assert shown["effect"].startswith("Done: a newer result of this check passed on acme-sign 1.4.3, on ")
    assert done["why"].startswith("acme-sign 1.4.2 gave the wrong answer on 2 published cases")     # still told from the failure it came from


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


def test_the_ids_of_proposals_do_not_change_with_what_else_is_in_the_plan():
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1") == proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1")
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1") != proposals.check_id("CVE-2022-21449", "a" * 64, "ref-2")
    assert proposals.check_id("CVE-2022-21449", "a" * 64, "ref-1").startswith("check-cve-2022-21449-")
    assert proposals.code_fix_id("otto-cve-2022-21449") == "fix-code-otto-cve-2022-21449" and proposals.update_fix_id(12) == "fix-update-12"
    assert proposals.plan_id_for("software:x", 3).startswith("plan-") and proposals.dependency_id("row", "CVE-1").startswith("dep-")
    for made in ("check-x", "fix-code-x", "fix-update-3", "plan-abc", "dep-abc"):
        assert proposals._kind_of_id(made) in proposals.KINDS
    assert proposals._kind_of_id("nonsense") is None
