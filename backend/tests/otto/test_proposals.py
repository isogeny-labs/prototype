"""Phase 5c, second part: Otto proposes; a person decides.

Everything Otto produces in an assessment is a proposal labelled "From Otto". A person accepts or rejects each one by
itself; a reject may carry a short reason and is never deleted ("Not added (reason)", and it can be taken up again);
an accept can be undone until what it led to has run or been applied. Every decision is kept in the database (rows
only ever added) and in the assessment's Otto ledger, with who and when. A decision runs nothing and is never a
result.

The first part of this file needs no harness: the second pinned checker (decisions.py) and the form a ledger may
have. The rest walks a demo-mode Lab with a pack made for the test."""
import hashlib
import json
import subprocess
import sys

import pytest
from sqlalchemy import func, select

import otto_helpers as helpers
from app.db import OttoCheckRow, OttoDecisionRow, PlanItemRow, TestRunRow
from app.errors import BadRequest, Conflict, NotFound
from app.otto import assurance, harness, proposals
from app.present import otto as present_otto
from conftest import demo_plan

# The first checker, exactly as the first build of phase 5c pinned it in every assessment's ledger. It must never
# change: a ledger written then names this fingerprint, and reads as "another version" if the file differs.
FIRST_CHECKER_SHA256 = "7ea0ba1f5b841ac4c1c6f71d5e52fa252b4247c7d4b385fb44515cc9c7c33305"
BANNED = ("secure", "score", "severity", "critical", "time to hack")
PARAMS = {"kind": "decision", "proposal": "check-cve-2022-21449-0123456789ab", "proposal_kind": "check"}


def _decision(**over) -> dict:
    """A decision entry exactly as the app writes one."""
    base = {"proposal": PARAMS["proposal"], "proposal_kind": "check", "proposal_sha256": "a" * 64,
            "title": "Advisory check: Blank signature accepted (CVE-2022-21449) on acme-sign 1.4.2", "decision": "accept",
            "before": "proposed", "after": "accepted", "by": "You", "at": "2026-11-18T10:02:00Z", "reason": None, "number": 1,
            "about": {"advisory": "CVE-2022-21449", "program": "acme-sign 1.4.2", "item": 12, "fix": None}}
    return {**base, **over}


def _check(artifact: dict, params: dict | None = None) -> str:
    return assurance.run_checker(params or PARAMS, artifact, assurance.DECISION_CHECKER)


# ---------------------------------------------------------------- the two pinned checkers

def test_the_first_checker_is_the_file_the_first_build_pinned():
    assert hashlib.sha256(assurance.CHECKER_SOURCE.read_bytes()).hexdigest() == FIRST_CHECKER_SHA256
    assert assurance.DECISION_CHECKER_SOURCE.name == "decisions.py" and assurance.DECISION_CHECKER_SOURCE != assurance.CHECKER_SOURCE
    assert set(assurance.CHECKERS) == {"recheck.py", "decisions.py"}
    assert assurance.CHECKERS["recheck.py"][1] == ("run", "step") and assurance.CHECKERS["decisions.py"][1] == ("decision",)


def test_the_decision_checker_accepts_each_step_the_app_has_and_no_other():
    steps = [("proposed", "accept", "accepted"), ("proposed", "reject", "rejected"), ("accepted", "undo", "proposed"),
             ("rejected", "reconsider", "proposed")]
    for number, (before, decision, after) in enumerate(steps, start=1):
        number = 1 if before == "proposed" else 2          # (a first decision starts from a proposal nobody decided)
        assert _check(_decision(before=before, decision=decision, after=after, number=number)) == "accept", decision
    assert _check(_decision(decision="reject", after="rejected", reason="Not this quarter")) == "accept"
    for before in ("proposed", "accepted", "rejected"):
        for decision in ("accept", "reject", "undo", "reconsider", "approve", ""):
            for after in ("proposed", "accepted", "rejected"):
                if (before, decision, after) not in steps:
                    assert _check(_decision(before=before, decision=decision, after=after, number=2)) == "reject", (before, decision, after)


@pytest.mark.parametrize("name, spoil", [
    ("a result beside the decision", lambda a: a.__setitem__("result", "passed")),
    ("a verdict beside the decision", lambda a: a.__setitem__("verdict", {"code": "passed"})),
    ("no name", lambda a: a.__setitem__("by", "")),
    ("a name that is not text", lambda a: a.__setitem__("by", ["You"])),
    ("no time", lambda a: a.__setitem__("at", "yesterday")),
    ("a reason on an accept", lambda a: a.__setitem__("reason", "because")),
    ("a reason of two lines", lambda a: a.update(decision="reject", after="rejected", reason="one\ntwo")),
    ("a reason too long", lambda a: a.update(decision="reject", after="rejected", reason="x" * 301)),
    ("another proposal", lambda a: a.__setitem__("proposal", "check-something-else")),
    ("another kind", lambda a: a.__setitem__("proposal_kind", "fix")),
    ("no fingerprint of what was proposed", lambda a: a.__setitem__("proposal_sha256", "abc")),
    ("no title", lambda a: a.__setitem__("title", "")),
    ("no place among the decisions", lambda a: a.__setitem__("number", 0)),
    ("a place that is not a number", lambda a: a.__setitem__("number", True)),
    ("a first decision that is an undo", lambda a: a.update(before="accepted", decision="undo", after="proposed")),
    ("something nested in what it is about", lambda a: a.__setitem__("about", {"advisory": {"deep": 1}})),
    ("too much in what it is about", lambda a: a.__setitem__("about", {f"k{n}": "v" for n in range(13)})),
    ("a field taken out", lambda a: a.pop("about")),
])
def test_the_decision_checker_refuses_anything_but_a_whole_decision(name, spoil):
    artifact = _decision()
    spoil(artifact)
    assert _check(artifact) == "reject", name


def test_the_decision_checker_knows_one_kind_of_entry_and_never_crashes():
    assert _check(_decision(), {**PARAMS, "kind": "run"}) == "reject"
    assert _check(_decision(), {"kind": "decision"}) == "reject"                       # it must name the proposal
    assert _check(_decision(), {**PARAMS, "proposal_kind": "something"}) == "reject"
    deep: dict = {}
    for _ in range(3000):
        deep = {"x": deep}
    assert _check(deep) in ("reject", "unavailable")
    # run by hand with input that is not JSON at all: it answers "reject", it does not fail
    done = subprocess.run([sys.executable, "-I", str(assurance.DECISION_CHECKER_SOURCE)], input=b"not json", capture_output=True, timeout=30)
    assert done.returncode == 0 and json.loads(done.stdout)["status"] == "reject"
    # a name that is not one of the app's two checkers is never looked for on disk
    assert assurance.run_checker(PARAMS, _decision(), "/bin/sh") == "unavailable"
    assert assurance.run_checker(PARAMS, _decision(), "../recheck.py") == "unavailable"


def test_the_checkers_answer_says_it_is_neither_a_result_nor_the_decision():
    sent = json.dumps({"params": PARAMS, "artifact": _decision()}).encode()
    done = subprocess.run([sys.executable, "-I", str(assurance.DECISION_CHECKER_SOURCE)], input=sent, capture_output=True, timeout=30)
    said = json.loads(done.stdout)
    assert said["status"] == "accept" and "not a result of a test" in said["detail"] and "not the decision itself" in said["detail"]


def _entry(seq: int, payload: dict) -> dict:
    return {"seq": seq, "kind": payload["type"], "payload": payload, "ts": "2026-11-18T10:00:00+00:00"}


def _objective(checker: str, params: dict, sha: str | None = None) -> dict:
    source = assurance.CHECKERS[checker][0] if checker in assurance.CHECKERS else assurance.CHECKER_SOURCE
    return {"type": "objective", "statement": "A statement.", "author": "evidence-lab", "created_at": "2026-11-18T10:00:00+00:00",
            "verifier": {"kind": "certificate", "checker": checker, "checker_sha256": sha or hashlib.sha256(source.read_bytes()).hexdigest(),
                         "params": params, "timeout_seconds": 60}}


def test_a_ledger_may_name_either_of_the_apps_two_checkers_each_for_its_own_kinds_of_entry():
    run_lock = _objective("recheck.py", {"kind": "run", "test": "a" * 64, "design": "b" * 64, "pack": "c" * 64})
    decided = _objective("decisions.py", PARAMS)
    claim = {"type": "claim", "objective_id": assurance.record_id(decided), "artifact": _decision(), "cites": [], "author": "evidence-lab",
             "created_at": "2026-11-18T10:00:01+00:00"}
    verdict = {"type": "verdict", "claim_id": assurance.record_id(claim), "objective_id": assurance.record_id(decided), "status": "accept",
               "detail": "whole", "evidence": {}, "tier": "V0-certificate", "attempt": 0, "author": "otto-verifier",
               "created_at": "2026-11-18T10:00:02+00:00"}
    both = [_entry(n, p) for n, p in enumerate([run_lock, decided, claim, verdict])]
    assert assurance.only_our_checker(both) is None
    # a ledger of the first build (the first checker only) reads exactly as before
    assert assurance.only_our_checker([_entry(0, run_lock)]) is None
    # a checker may be named only for a kind of entry it checks
    assert assurance.only_our_checker([_entry(0, _objective("recheck.py", PARAMS))]) == assurance.NOT_OUR_CHECKER
    assert assurance.only_our_checker([_entry(0, _objective("decisions.py", {"kind": "run"}))]) == assurance.NOT_OUR_CHECKER
    assert assurance.only_our_checker([_entry(0, _objective("decisions.py", {"kind": "step"}))]) == assurance.NOT_OUR_CHECKER
    # any other program is not ours, whatever it is called
    for name in ("other.py", "/bin/sh", "./decisions.py", "decisions.py ", ["decisions.py"]):
        entry = _entry(0, _objective("decisions.py", PARAMS))
        entry["payload"]["verifier"]["checker"] = name
        assert assurance.only_our_checker([entry]) == assurance.NOT_OUR_CHECKER, name
    # the second checker in another version is "another version", never a pass
    assert assurance.only_our_checker([_entry(0, _objective("decisions.py", PARAMS, sha="0" * 64))]) == assurance.OTHER_VERSION
    # checking again starts the checker the entry's kind belongs to: ours, by its own file
    assert assurance.check_again(both) == []
    tampered = json.loads(json.dumps(both))
    tampered[2]["payload"]["artifact"]["by"] = ""
    tampered[3]["payload"]["claim_id"] = assurance.record_id(tampered[2]["payload"])
    assert assurance.only_our_checker(tampered) is None
    assert any("now says reject" in problem for problem in assurance.check_again(tampered))


# ---------------------------------------------------------------- words (no harness needed)

def _made(kind: str = "check", **facts) -> dict:
    return proposals.make(kind, f"{'dep' if kind == 'dependency' else kind}-example-0123456789ab", title="A proposal made for a test",
                          why="Because the test says so.", lines=["One line.", ""], about={"advisory": "CVE-2022-21449", "item": 3},
                          proposed_at="2026-11-18T09:00:00Z", item="CVE-2022-21449", facts=facts)


def test_a_proposal_is_labelled_from_otto_and_its_fingerprint_covers_only_what_was_proposed():
    made = _made()
    assert made["label"] == "From Otto" == proposals.LABEL == present_otto.PROPOSAL_LABEL and made["lines"] == ["One line."]
    assert made["link"] == {"page": "advisories", "item": "CVE-2022-21449"}
    one = proposals.fingerprint(made)
    assert one == proposals.fingerprint({**made, "facts": {"runs": 3}, "proposed_at": None, "link": {}})       # not part of what was proposed
    assert one != proposals.fingerprint({**made, "why": "Because of something else."})
    assert set(proposals.content(made)) == {"id", "kind", "title", "why", "lines", "about"}
    assert [proposals.HOME[k] for k in proposals.KINDS] == ["advisories", "fixes", "migration/systems", "migration/dependencies"]


def test_a_reason_is_one_short_plain_line_or_none():
    assert proposals.clean_reason(None) is None and proposals.clean_reason("   ") is None
    assert proposals.clean_reason("  Not  this\nquarter\t ") == "Not this quarter"
    assert proposals.clean_reason("x" * 300) == "x" * 300
    for bad in ("x" * 301, 7, ["a"]):
        with pytest.raises(BadRequest):
            proposals.clean_reason(bad)


class _Row:
    def __init__(self, number, decision, before, after, reason=None):
        self.number, self.decision, self.before, self.after, self.reason = number, decision, before, after, reason
        self.by, self.at, self.proposal_sha256, self.claim_id, self.objective_id = "You", "2026-11-18T10:02:00Z", "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64
        self.proposal = {}


def _stands(kind: str, rows: list, blocked: str | None = None, **facts) -> dict:
    return proposals.ProposalsMixin._with_state(proposals.ProposalsMixin(), _made(kind, **facts), rows, blocked)


def test_the_buttons_follow_the_state_and_say_why_when_they_are_off():
    fresh = present_otto.proposal_view(_stands("check", []))
    assert fresh["status"] == {"key": "proposed", "word": "Proposed", "tone": "warn"} and fresh["decided_line"] == "Nobody has decided this yet."
    assert [(b["key"], b["label"], b["can"]) for b in fresh["buttons"]] == [("accept", "Accept", True), ("reject", "Reject", True)]
    assert fresh["reject_dialog"]["reason_label"] == "Reason (optional, one short line)" and "It runs nothing." in fresh["note"]
    assert fresh["why_label"] == "Why it applies" and fresh["effect"] is None and fresh["history"]["count"] == 0

    accepted = present_otto.proposal_view(_stands("check", [_Row(1, "accept", "proposed", "accepted")], in_plan=True))
    assert accepted["status"]["word"] == "Added" and accepted["decided_line"] == "Accepted by You on 18 November 2026, 10:02 UTC."
    assert [(b["key"], b["can"]) for b in accepted["buttons"]] == [("undo", True)] and accepted["reject_dialog"] is None
    assert accepted["effect"] == "It is in the test plan, on Checks. It has not run yet."
    assert accepted["history"]["rows"][0]["line"] == "1. Accepted by You on 18 November 2026, 10:02 UTC."
    assert "one login" in accepted["history"]["footnote"]

    ran = present_otto.proposal_view(_stands("check", [_Row(1, "accept", "proposed", "accepted")], in_plan=True, runs=1))
    assert ran["buttons"] == [{"key": "undo", "label": "Undo", "can": False, "blocked_reason": "This check has run, so it stays in the test plan."}]

    rejected = present_otto.proposal_view(_stands("fix", [_Row(1, "reject", "proposed", "rejected", "Not this quarter")]))
    assert rejected["status"] == {"key": "rejected", "word": "Not added (Not this quarter)", "tone": "neutral"}
    assert rejected["decided_line"] == "Rejected by You on 18 November 2026, 10:02 UTC. Reason: Not this quarter"
    assert [b["key"] for b in rejected["buttons"]] == ["reconsider"] and rejected["why_label"] == "Why Otto proposes it"
    no_reason = present_otto.proposal_view(_stands("plan", [_Row(1, "reject", "proposed", "rejected")]))
    assert no_reason["status"]["word"] == "Not added (no reason given)" and "No reason was given." in no_reason["decided_line"]

    again = present_otto.proposal_view(_stands("dependency", [_Row(1, "reject", "proposed", "rejected", "x"), _Row(2, "reconsider", "rejected", "proposed")]))
    assert again["status"]["word"] == "Proposed" and "Taken up again by You" in again["decided_line"] and again["history"]["count"] == 2

    closed = present_otto.proposal_view(_stands("check", [], blocked="This assessment is closed. Start a new one to continue."))
    assert all(not b["can"] and "closed" in b["blocked_reason"] for b in closed["buttons"]) and len(closed["buttons"]) == 2
    for kind, word in (("check", "Added"), ("fix", "Accepted"), ("plan", "Accepted"), ("dependency", "Accepted")):
        assert present_otto.proposal_view(_stands(kind, [_Row(1, "accept", "proposed", "accepted")]))["status"]["word"] == word
    said = json.dumps([fresh, accepted, ran, rejected, no_reason, again, closed]).lower()
    assert not any(word in said for word in BANNED)


def test_what_locks_an_accept_is_that_it_has_run_or_been_applied():
    locked = proposals.ProposalsMixin._otto_locked
    assert locked(_made("check")) is None and locked(_made("check", runs=0, live=False)) is None
    assert "has run" in locked(_made("check", runs=2)) and "has run" in locked(_made("check", live=True))
    assert locked(_made("fix", code=True, connected=False)) is None and "code is connected" in locked(_made("fix", code=True, connected=True))
    assert locked(_made("fix", code=False, retested=False)) is None and "retest has run" in locked(_made("fix", code=False, retested=True))
    # ... and from the moment a retest on the updated version is running, before it has any result
    assert locked(_made("fix", code=False, retested=False, live=True)) == "A retest on the updated version is running, so this accept stands."
    assert locked(_made("fix", code=False, retested=False, live=False)) is None
    assert locked(_made("plan")) is None and "passed since" in locked(_made("plan", done={"version": "1.4.3"}))
    assert locked(_made("dependency")) is None


def test_the_waiting_line_counts_each_kind_and_links_to_the_page_it_lives_on():
    view = present_otto.waiting_view({"check": 2, "fix": 1, "plan": 0, "dependency": 1})
    assert view["title"] == "Waiting for you" and view["total"] == 4 and view["line"] == "4 proposals from Otto wait for your decision."
    assert [(i["kind"], i["text"], i["link"]["page"]) for i in view["items"]] == [
        ("check", "2 proposed checks", "advisories"), ("fix", "1 proposed fix", "fixes"),
        ("dependency", "1 proposed dependency update", "migration/dependencies")]
    one = present_otto.waiting_view({"plan": 1})
    assert one["line"] == "1 proposal from Otto waits for your decision." and one["items"][0]["link"]["page"] == "migration/systems"
    none = present_otto.waiting_view({})
    assert none["total"] == 0 and none["items"] == [] and none["line"] == "Nothing from Otto is waiting for a decision."
    assert "a person decides" in none["note"]


def test_imports_line_counts_checks_that_may_apply_and_says_nothing_runs():
    found = present_otto.found_line(packs=1, ready=2, programs=["acme-sign 1.4.2"])
    assert found["count"] == 2 and found["label"] == "From Otto" and found["link"] == {"page": "advisories", "item": None}
    assert found["text"] == "Otto found 2 checks that may apply: 2 published weaknesses with a test, for acme-sign 1.4.2."
    assert "Nothing runs on import" in found["note"] and found["link_label"] == "Open Advisories"
    one = present_otto.found_line(packs=2, ready=1, programs=["one 1.0"])
    assert one["text"].startswith("Otto found 1 check that may apply: 1 published weakness with a test")
    assert present_otto.found_line(packs=0, ready=0, programs=["x 1"])["link"]["page"] == "settings"
    assert "no signing program in this file" in present_otto.found_line(packs=1, ready=2, programs=[])["text"]
    assert "has a test yet" in present_otto.found_line(packs=1, ready=0, programs=["x 1"])["text"]


# ---------------------------------------------------------------- a demo-mode Lab with one pack

def _pack_one():
    return helpers.make_pack("2026.11.1", None, [helpers.pack_advisory(),
                                                 helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",)),
                                                 helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")])


@pytest.fixture
def lab(tmp_path, monkeypatch):
    first, public = _pack_one()
    made = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    made.plan = demo_plan(made)
    made.check_pack_updates()
    made.install_pack("2026.11.1")
    yield made
    made.stop()


def _runs(lab) -> int:
    with lab.db() as db:
        return int(db.scalar(select(func.count(TestRunRow.id))) or 0)


def _ledger(lab):
    return assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=lab.plan.id).id)


@pytest.mark.needs_otto
def test_otto_proposes_a_check_for_each_ready_test_and_each_program_it_fits_and_says_why(lab):
    found = helpers.check_proposals(lab, lab.plan.id)
    assert [p["about"]["advisory"] for p in found] == ["CVE-2022-21449", "CVE-2024-42460"]            # the one with no test proposes nothing
    for p in found:
        assert p["kind"] == "check" and p["label"] == "From Otto" and p["state"] == "proposed" and p["decisions"] == [] and p["current"]
        assert p["about"]["program"] == "acme-sign 1.4.2" and p["about"]["pack"] == "2026.11.1" and p["proposed_at"]
        assert p["actions"] == {"accept": None, "reject": None}
        assert any("Control that must fail" in line for line in p["lines"]) and any("Tried on public copies" in line for line in p["lines"])
    # the test pack's advisories are about acme-sign itself, and the file lists it
    assert found[0]["why"] == "The advisory is about acme-sign, and your file lists acme-sign 1.4.2. Its publisher names 1.4.3 as the fixed version."
    # looking wrote nothing and ran nothing
    with lab.db() as db:
        assert db.scalars(select(OttoDecisionRow)).all() == [] and db.scalars(select(OttoCheckRow)).all() == []
    assert _runs(lab) == 0 and not _ledger(lab).exists()
    assert lab.assessment_view(lab.assessment_for(plan_id=lab.plan.id).id)["waiting"]["total"] == 2
    assert lab.import_json_for(lab.plan.imp["id"])["otto"]["count"] == 2


@pytest.mark.needs_otto
def test_accept_reject_undo_and_reconsider_are_each_recorded_with_who_and_when(lab):
    plan_id = lab.plan.id
    first, second = (p["id"] for p in helpers.check_proposals(lab, plan_id))
    accepted = lab.otto_decide(plan_id, first, "accept")
    assert accepted["state"] == "accepted" and accepted["actions"] == {"undo": None}
    rejected = lab.otto_decide(plan_id, second, "reject", "  Not this quarter:\nwe test that library elsewhere ")
    assert rejected["state"] == "rejected" and rejected["actions"] == {"reconsider": None}
    assert rejected["decisions"][0]["reason"] == "Not this quarter: we test that library elsewhere"
    # the rejected one is still listed, as "Not added (reason)", with its reason: nothing was deleted
    row = next(r for r in lab.advisories_view(plan_id)["rows"] if r["id"] == "CVE-2024-42460")
    assert row["proposal"]["label"] == "Not added (Not this quarter: we test that library elsewhere)" and row["proposal"]["key"] == "rejected"
    assert row["panel"]["here"]["rows"][0]["status"] == row["proposal"]["label"] and row["result"]["label"] == "Not in the test plan"
    undone = lab.otto_decide(plan_id, first, "undo")
    assert undone["state"] == "proposed" and set(undone["actions"]) == {"accept", "reject"}
    assert not any(t["kind"] == "advisory_cases" for t in lab.plan_view(plan_id)["tests"])               # it left the test plan
    again = lab.otto_decide(plan_id, second, "reconsider")
    assert again["state"] == "proposed" and [d["decision"] for d in again["decisions"]] == ["reject", "reconsider"]
    lab.otto_decide(plan_id, second, "accept")
    lab.otto_decide(plan_id, first, "accept")
    assert sum(1 for t in lab.plan_view(plan_id)["tests"] if t["kind"] == "advisory_cases") == 2
    assert _runs(lab) == 0 and not lab.jobs.busy(plan_id)                                              # six decisions ran nothing
    with lab.db() as db:
        rows = db.scalars(select(OttoDecisionRow).order_by(OttoDecisionRow.id)).all()
        assert [(r.decision, r.before, r.after, r.number) for r in rows] == [
            ("accept", "proposed", "accepted", 1), ("reject", "proposed", "rejected", 1), ("undo", "accepted", "proposed", 2),
            ("reconsider", "rejected", "proposed", 2), ("accept", "proposed", "accepted", 3), ("accept", "proposed", "accepted", 3)]
        assert all(r.by == "You" and r.at.endswith("Z") and r.kind == "check" and r.claim_id.startswith("sha256:") for r in rows)
        assert all(r.proposal_sha256 == proposals.fingerprint(r.proposal) for r in rows)             # the copy decided on, with its fingerprint
        assert len(db.scalars(select(OttoCheckRow)).all()) == 2                                       # one lock entry each, also after the undo
    # ... and each one is in the assessment's Otto ledger, accepted by the pinned checker for decisions
    book = _ledger(lab)
    decided = [e["payload"]["artifact"] for e in book.entries() if e["kind"] == "claim" and "decision" in e["payload"]["artifact"]]
    assert [(a["decision"], a["by"], a["number"]) for a in decided] == [(r.decision, "You", r.number) for r in rows]
    assert [a["at"] for a in decided] == [r.at for r in rows] and decided[1]["reason"] == "Not this quarter: we test that library elsewhere"
    assert all(e["payload"]["status"] == "accept" for e in book.entries() if e["kind"] == "verdict") and book.audit() == []
    named = [e["payload"]["verifier"] for e in book.entries() if e["kind"] == "objective" and e["payload"]["verifier"]["params"]["kind"] == "decision"]
    assert len(named) == 2 and all(v["checker"] == "decisions.py" for v in named)                     # one entry names each proposal, once
    # the ledger words no result, and no decision is worded as one
    text = json.dumps(book.entries()).lower()
    assert "passed" not in text and "failed" not in text
    # the page lists the decisions and their ledger entries
    shown = lab.otto_proposals_view(plan_id)["proposals"][0]
    assert shown["history"]["count"] == 3 and [r["word"] for r in shown["history"]["rows"]] == ["Accepted", "Accept undone", "Accepted"]
    assert shown["history"]["ledger"]["count"] >= 7 and "holds no result" in shown["history"]["ledger"]["note"]
    assert {e["kind"] for e in shown["history"]["ledger"]["entries"]} == {"Opened", "Recorded", "Record checked"}


@pytest.mark.needs_otto
def test_a_step_the_state_does_not_allow_is_refused_and_changes_nothing(lab):
    plan_id = lab.plan.id
    first = helpers.check_proposals(lab, plan_id)[0]["id"]
    for decision in ("undo", "reconsider"):
        with pytest.raises(Conflict) as refused:
            lab.otto_decide(plan_id, first, decision)
        assert "has not been decided yet" in str(refused.value)
    with pytest.raises(BadRequest):
        lab.otto_decide(plan_id, first, "approve")
    with pytest.raises(BadRequest):
        lab.otto_decide(plan_id, first, "reject", "x" * 301)
    for unknown in ("check-cve-0000-0000-000000000000", "fix-code-nothing", "plan-000000000000", "dep-000000000000", "nonsense"):
        with pytest.raises(NotFound):
            lab.otto_decide(plan_id, unknown, "accept")
    lab.otto_decide(plan_id, first, "accept")
    for decision in ("accept", "reject", "reconsider"):
        with pytest.raises(Conflict) as refused:
            lab.otto_decide(plan_id, first, decision)
        assert "is accepted" in str(refused.value)
    with lab.db() as db:
        assert [r.decision for r in db.scalars(select(OttoDecisionRow)).all()] == ["accept"]        # only what was allowed is on record
    assert _ledger(lab).audit() == []


@pytest.mark.needs_otto
def test_an_accept_can_be_undone_until_the_check_has_run(lab):
    plan_id = lab.plan.id
    first = helpers.check_proposals(lab, plan_id)[0]["id"]
    lab.otto_decide(plan_id, first, "accept")
    with lab.db() as db:
        item_id = db.scalars(select(OttoCheckRow.plan_item_id)).one()
    lab.run_test(plan_id, item_id)                                       # the person's own click on Checks
    lab.wait_until_idle(plan_id, 240)
    proposal = lab.otto_proposal(plan_id, first)
    assert proposal["actions"] == {"undo": "This check has run, so it stays in the test plan."}
    with pytest.raises(Conflict) as refused:
        lab.otto_decide(plan_id, first, "undo")
    assert str(refused.value) == "This check has run, so it stays in the test plan."
    with lab.db() as db:
        assert db.get(PlanItemRow, item_id).removed is False
    view = present_otto.proposal_view(proposal)
    assert view["effect"] == "It is in the test plan, on Checks." and view["buttons"][0]["can"] is False


@pytest.mark.needs_otto
def test_a_closed_assessment_takes_no_decision_and_one_without_otto_neither(lab, monkeypatch):
    plan_id = lab.plan.id
    first, second = (p["id"] for p in helpers.check_proposals(lab, plan_id))
    lab.otto_decide(plan_id, first, "accept")
    missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
    with monkeypatch.context() as patch:
        patch.setattr(harness, "status", lambda *a, **k: missing)
        blocked = lab.otto_proposals_view(plan_id)
        assert "Otto is not installed on this computer" in blocked["blocked_reason"] and "nothing can be decided" in blocked["blocked_reason"]
        assert all(not b["can"] and "Otto is not installed" in b["blocked_reason"] for p in blocked["proposals"] for b in p["buttons"])
        with pytest.raises(Conflict):
            lab.otto_decide(plan_id, second, "reject", "no")
        # nothing waits for a decision that can't be made
        assert lab.assessment_view(lab.assessment_for(plan_id=plan_id).id)["waiting"]["total"] == 0
    lab.update_assessment(lab.assessment_for(plan_id=plan_id).id, {"close": True, "signed_off_by": "Sam Lee", "note": None})
    closed = lab.otto_proposals_view(plan_id)
    assert closed["blocked_reason"] == "This assessment is closed. Start a new one to continue."
    assert all(not b["can"] for p in closed["proposals"] for b in p["buttons"])
    for decision, proposal_id in (("undo", first), ("accept", second), ("reject", second)):
        with pytest.raises(Conflict) as refused:
            lab.otto_decide(plan_id, proposal_id, decision)
        assert str(refused.value) == "This assessment is closed. Start a new one to continue."
    with lab.db() as db:
        assert [r.decision for r in db.scalars(select(OttoDecisionRow)).all()] == ["accept"]


@pytest.mark.needs_otto
def test_a_check_added_before_decisions_were_recorded_reads_added_with_no_accept_to_undo(lab):
    """An assessment from the first build of phase 5c: its checks were added by the old bulk button, with a lock entry
    and no decision. They read "Added", and there is no accept on record to undo."""
    plan_id = lab.plan.id
    found = helpers.check_proposals(lab, plan_id)[0]
    with lab._otto_lock, lab._plan_lock, lab.db() as db:               # what the old button did: lock and add, no decision
        lab._accept_check(db, lab._plan(db, plan_id), found, _ledger(lab))
        db.commit()
    proposal = lab.otto_proposal(plan_id, found["id"])
    assert proposal["state"] == "accepted" and proposal["legacy"] is True and proposal["decisions"] == []
    assert "before decisions were recorded" in proposal["actions"]["undo"]
    shown = present_otto.proposal_view(proposal)
    assert shown["status"]["word"] == "Added" and shown["decided_line"] == "Added before decisions were recorded."
    with pytest.raises(Conflict):
        lab.otto_decide(plan_id, found["id"], "undo")
    # its evidence still verifies: the file says it is such a check, and the ledger holds no decision for it
    lab.run_test(plan_id, proposal["facts"]["item_id"])
    lab.wait_until_idle(plan_id, 240)
    from evidence import otto as evidence_otto
    made = lab.export_evidence(plan_id)
    evidence = json.loads(lab.evidence_file(made["id"], "json")[1])["evidence"]
    listed = next(p for p in evidence["otto"]["proposals"] if p["id"] == found["id"])
    assert listed["legacy"] is True and listed["state"] == "accepted" and listed["decisions"] == []
    outcome = evidence_otto.check_otto(evidence, {lab.pack_key} if hasattr(lab, "pack_key") else set())
    assert outcome.code in (evidence_otto.OK, evidence_otto.NOT_CONFIRMED) and "Decisions: 0 on 0" in " ".join(outcome.lines)


@pytest.mark.needs_otto
def test_a_check_added_before_decisions_keeps_its_own_remove_button(lab):
    """It has no accept on record, so Advisories has nothing to undo: its own × works as it always did. A check a
    person accepted has no × of its own (Undo on Advisories takes it out, until it has run)."""
    plan_id = lab.plan.id
    older, accepted = helpers.check_proposals(lab, plan_id)[:2]
    with lab._otto_lock, lab._plan_lock, lab.db() as db:               # what the old button did: lock and add, no decision
        lab._accept_check(db, lab._plan(db, plan_id), older, _ledger(lab))
        db.commit()
    lab.otto_decide(plan_id, accepted["id"], "accept")
    cards = {lab.otto_proposal(plan_id, p["id"])["facts"]["item_id"]: p["id"] for p in (older, accepted)}
    shown = {c["id"]: c for c in lab.plan_view(plan_id)["tests"] if c["id"] in cards}
    old_item, new_item = (next(i for i, pid in cards.items() if pid == p["id"]) for p in (older, accepted))
    assert shown[old_item]["can_remove"] is True and "remove_blocked" not in shown[old_item]
    assert shown[new_item]["can_remove"] is False and "Undo on Advisories" in shown[new_item]["remove_blocked"]
    with pytest.raises(Conflict):
        lab.remove_test(plan_id, new_item)
    lab.remove_test(plan_id, old_item)                                 # the older one leaves the plan by its own button
    assert old_item not in {c["id"] for c in lab.plan_view(plan_id)["tests"]}
    again = lab.otto_proposal(plan_id, older["id"])
    assert again["state"] == "proposed" and again["legacy"] is False and set(again["actions"]) == {"accept", "reject"}


@pytest.mark.needs_otto
def test_nothing_is_written_anywhere_when_the_record_checker_does_not_take_the_entry(lab, monkeypatch):
    """The entry a decision would make is shown to the app's own pinned checker before anything is written. If it is
    not taken, the ledger, the database and the test plan are exactly as they were: "Nothing was changed" is true."""
    plan_id = lab.plan.id
    found = helpers.check_proposals(lab, plan_id)[0]
    lab.otto_decide(plan_id, helpers.check_proposals(lab, plan_id)[1]["id"], "reject", "Not needed")   # so that a ledger exists
    height, tests = len(_ledger(lab).entries()), [c["id"] for c in lab.plan_view(plan_id)["tests"]]
    monkeypatch.setattr(assurance, "run_checker", lambda params, artifact, checker=assurance.CHECKER: "unavailable")
    with pytest.raises(Conflict) as refused:
        lab.otto_decide(plan_id, found["id"], "accept")
    assert str(refused.value) == "The decision could not be recorded: the record checker did not take it. Nothing was changed."
    monkeypatch.undo()
    assert len(_ledger(lab).entries()) == height and [c["id"] for c in lab.plan_view(plan_id)["tests"]] == tests
    with lab.db() as db:
        assert [r.decision for r in db.scalars(select(OttoDecisionRow)).all()] == ["reject"]
    assert lab.otto_proposal(plan_id, found["id"])["state"] == "proposed"


@pytest.mark.needs_otto
def test_an_entry_the_checker_did_not_accept_is_an_attempt_and_not_a_decision(lab):
    """The ledger can hold an entry for a decision that the pinned checker did not accept (the app writes no database
    row for it, and the proposal stands as it was). The verify command says it is there and that it is no decision;
    the file still verifies, with its real decisions counted."""
    from evidence import otto as evidence_otto
    plan_id = lab.plan.id
    lab.run_test(plan_id, lab.plan.item["bad_signatures"])             # a first result, so that there is evidence to download
    lab.wait_until_idle(plan_id, 240)
    first, second = helpers.check_proposals(lab, plan_id)[:2]
    lab.otto_decide(plan_id, first["id"], "reject", "Not needed")
    # an entry that is not a step the app allows (an undo of something that was never accepted): the checker rejects it
    _, _, verdict = _ledger(lab).record_decision(
        objective_id=None, proposal_id=second["id"], kind="check", title=second["title"], proposal_sha256=second["fingerprint"],
        decision="undo", before="proposed", after="proposed", by="You", at="2026-11-18T10:00:00Z", reason=None, number=1, about=second["about"])
    assert verdict == "reject"
    assert lab.otto_proposal(plan_id, second["id"])["state"] == "proposed"
    evidence = json.loads(lab.evidence_file(lab.export_evidence(plan_id)["id"], "json")[1])["evidence"]
    outcome = evidence_otto.check_otto(evidence, set())
    said = " ".join(outcome.lines)
    assert outcome.code != evidence_otto.FAILED, outcome.problem
    assert "Decisions: 1 on 1 of Otto's" in said and "1 attempted entry for a decision that the pinned checker did not accept" in said
    # but it can't be passed off as a decision in the file
    forged = json.loads(json.dumps(evidence))
    target = next(p for p in forged["otto"]["proposals"] if p["id"] == second["id"])
    attempt = next(json.loads(line) for line in forged["otto"]["ledger"]["lines"] if '"decision":"undo"' in line)
    target["decisions"] = [{"number": 1, "decision": "undo", "by": "You", "at": "2026-11-18T10:00:00Z", "reason": None, "before": "proposed",
                            "after": "proposed", "proposal_sha256": second["fingerprint"], "proposal": proposals.content(second),
                            "ledger_entry": assurance.record_id(attempt["payload"])}]
    refused = evidence_otto.check_otto(forged, set())
    assert refused.code == evidence_otto.FAILED and refused.problem


@pytest.mark.needs_otto
def test_a_file_from_before_decisions_has_no_such_part_and_still_verifies(lab):
    """An evidence file of the first build has no list of proposals. It is checked as before; but a ledger that holds a
    decision and a file that shows none is refused."""
    from evidence import otto as evidence_otto
    plan_id = lab.plan.id
    found = helpers.check_proposals(lab, plan_id)[0]
    with lab._otto_lock, lab._plan_lock, lab.db() as db:
        lab._accept_check(db, lab._plan(db, plan_id), found, _ledger(lab))
        db.commit()
    lab.run_test(plan_id, lab.otto_proposal(plan_id, found["id"])["facts"]["item_id"])
    lab.wait_until_idle(plan_id, 240)
    evidence = json.loads(lab.evidence_file(lab.export_evidence(plan_id)["id"], "json")[1])["evidence"]
    older = json.loads(json.dumps(evidence))
    del older["otto"]["proposals"], older["otto"]["decisions_note"]
    assert evidence_otto.check_otto(older, set()).code != evidence_otto.FAILED
    assert not any(line.startswith("Decisions:") for line in evidence_otto.check_otto(older, set()).lines)
    # now a decision is made; a file that drops the list while its ledger holds the decision fails
    second = helpers.check_proposals(lab, plan_id)[1]
    lab.otto_decide(plan_id, second["id"], "reject", "Not needed")
    newer = json.loads(lab.evidence_file(lab.export_evidence(plan_id)["id"], "json")[1])["evidence"]
    del newer["otto"]["proposals"]
    outcome = evidence_otto.check_otto(newer, set())
    assert outcome.code == evidence_otto.FAILED and "the file does not show them" in outcome.problem


@pytest.mark.needs_otto
def test_a_rejected_proposal_alone_is_in_the_evidence_with_its_reason(lab):
    """Nothing of Otto's was taken into the assessment, but a person decided: that is on the record, signed."""
    plan_id = lab.plan.id
    lab.run_test(plan_id, lab.plan.item["bad_signatures"])
    lab.wait_until_idle(plan_id, 240)
    first = helpers.check_proposals(lab, plan_id)[0]["id"]
    lab.otto_decide(plan_id, first, "reject", "Out of scope for this review")
    evidence = json.loads(lab.evidence_file(lab.export_evidence(plan_id)["id"], "json")[1])["evidence"]
    otto = evidence["otto"]
    assert otto["checks"] == [] and otto["packs"] == [] and otto["ledger"]["height"] == 3
    rejected = next(p for p in otto["proposals"] if p["id"] == first)
    assert rejected["state"] == "rejected" and rejected["status"] == "Not added (Out of scope for this review)"
    assert rejected["decisions"][0]["reason"] == "Out of scope for this review" and rejected["decisions"][0]["by"] == "You"
    from evidence import otto as evidence_otto
    outcome = evidence_otto.check_otto(evidence, set())
    assert outcome.code == evidence_otto.OK and any(line.startswith("Decisions: 1 on 1 of Otto's 2 proposals") for line in outcome.lines)
    report = lab.evidence_file(lab.export_evidence(plan_id)["id"], "html")[1].decode()
    assert "Rejected by You" in report and "Out of scope for this review" in report and "Not added (Out of scope for this review)" in report


@pytest.mark.needs_otto
def test_the_project_overview_counts_what_waits_and_what_changed_since_the_newest_pack(lab):
    plan_id = lab.plan.id
    assessment = lab.assessment_for(plan_id=plan_id)
    block = lab.project_overview(assessment.project_id)["otto"]
    assert block["title"] == "Otto in this project" and "Newest test pack: 2026.11.1, installed on" in block["pack_line"]
    row = next(r for r in block["rows"] if r["assessment_id"] == assessment.id)
    assert row["waiting"] == 2 and row["waiting_text"] == "2 proposals waiting for a decision: 2 proposed checks"     # said by kind
    assert row["since"] == ["It brought 2 proposed checks for this assessment: 2 waiting."]
    first, second = (p["id"] for p in helpers.check_proposals(lab, plan_id))
    lab.otto_decide(plan_id, first, "accept")
    lab.otto_decide(plan_id, second, "reject", "Later")
    row = next(r for r in lab.project_overview(assessment.project_id)["otto"]["rows"] if r["assessment_id"] == assessment.id)
    assert row["waiting"] == 0 and row["waiting_text"] == "Nothing waiting"
    assert row["since"] == ["It brought 2 proposed checks for this assessment: 1 added, 1 not added.", "2 decisions recorded since."]
    assert not any(word in json.dumps(block).lower() for word in BANNED)
