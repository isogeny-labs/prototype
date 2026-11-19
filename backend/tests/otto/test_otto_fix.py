"""Phase 5c, change 3: Otto writes the fix for a customer's own code. When an advisory check fails on the
assessment's own program, the change comes from Otto (Claude, recorded or live) through the same engine socket as
the fix template, and takes the same path: a copy on a branch, the byte-for-byte check, a proof that reruns every
locked test (the advisory check included), the separate reviewer, a person's approval and merge.

The answers used here were written for the tests (they are fixtures, not answers from Claude)."""
import json

import pytest
from sqlalchemy import select

import otto_helpers as helpers
from app.db import ChangeRow, OttoStepRow
from app.errors import BadRequest, Conflict
from app.otto import assurance, fixes, model
from app.run import components
from conftest import demo_plan, play_back_speed

pytestmark = [pytest.mark.needs_otto]
HOW = "Written for a test, not an answer from Claude"
# The change that turns acme-sign 1.4.2 into exactly our registered 1.4.3, as an answer in the shape Otto asks for.
GOOD = {"title": "Reject signatures whose r or s is out of range",
        "summary": "The verify command now refuses a signature whose two numbers are zero or not below the curve order.",
        "answers": [1, 2, 3],
        "edits": [{"file": "acme_sign.py", "title": "The range check", "why": "r and s must each be at least 1 and below n.",
                   "find": ["    except ValueError:", '        return {"valid": False}', "    e = digest_int(message)"],
                   "put": ["    except ValueError:", '        return {"valid": False}', "    if not (1 <= r < N and 1 <= s < N):",
                           '        return {"valid": False}', "    e = digest_int(message)"]},
                  {"file": "acme_sign.py", "title": "The version number", "why": "So the changed program can be told from the one before.",
                   "find": ['VERSION = "1.4.2"'], "put": ['VERSION = "1.4.3"']}]}


def _source() -> str:
    return components.lookup("acme-sign", "1.4.2").read_text(encoding="utf-8")


def test_the_fixture_change_gives_exactly_the_registered_fixed_program():
    """The premise of the tests below: applied to 1.4.2, the fixture's edits give 1.4.3 byte for byte."""
    change = fixes.check_change(json.dumps(GOOD), {"acme_sign.py": _source()}, 3)
    assert change["files"]["acme_sign.py"] == components.lookup("acme-sign", "1.4.3").read_text(encoding="utf-8")
    assert change["answers"] == [0, 1, 2] and len(change["edits"]) == 2 and change["edits"][0]["new_end"] - change["edits"][0]["new_start"] == 2


@pytest.mark.parametrize("spoil, words", [
    (lambda a: a.__setitem__("command", "rm -rf /"), "exactly the parts of a change"),
    (lambda a: a["edits"][0].__setitem__("file", "../../etc/passwd"), "names a file that is not in the code"),
    (lambda a: a["edits"][0].__setitem__("find", ["a line that is not there"]), "does not apply to the code"),
    (lambda a: a["edits"][1].__setitem__("find", ["    try:"]), "does not apply to the code"),          # there more than once
    (lambda a: a["edits"][0].__setitem__("put", a["edits"][0]["find"]), "changes nothing"),
    (lambda a: a.__setitem__("answers", [7]), "which of the failed tests"),
    (lambda a: a.__setitem__("answers", []), "which of the failed tests"),
    (lambda a: a.__setitem__("edits", []), "no edit, or too many"),
    (lambda a: a.__setitem__("summary", "This makes the program secure."), "never says about a system"),
    (lambda a: a["edits"][0].__setitem__("put", ["x = 1"] * 61), "not a short list of whole lines"),
    (lambda a: a["edits"][0].__setitem__("put", ["import os\nos.system('x')"]), "not a short list of whole lines"),
])
def test_an_answer_that_is_not_a_clean_change_is_refused(spoil, words):
    answer = json.loads(json.dumps(GOOD))
    spoil(answer)
    with pytest.raises(fixes.Refused) as refused:
        fixes.check_change(json.dumps(answer), {"acme_sign.py": _source()}, 3)
    assert words in str(refused.value)
    for not_json in ("", "Here is the change: ...", "[]"):
        with pytest.raises(fixes.Refused):
            fixes.check_change(not_json, {"acme_sign.py": _source()}, 3)


@pytest.fixture
def failed(tmp_path, monkeypatch):
    """A demo-mode Lab with a pack installed, its check added, and every test of the plan run (so the advisory check
    and the two classic signing tests have failed on acme-sign 1.4.2). `prompts` collects what Otto would ask Claude."""
    monkeypatch.delenv(model.KEY_ENV, raising=False)
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    lab.prompts = []
    real = model.OttoModel.recorded

    def recorded(self, step, prompt):
        lab.prompts.append((step, prompt))
        return real(self, step, prompt)
    monkeypatch.setattr(model.OttoModel, "recorded", recorded)
    lab.plan = demo_plan(lab)
    lab.check_pack_updates()
    lab.install_pack("2026.11.1")
    helpers.accept_checks(lab, lab.plan.id)
    play_back_speed(lab)
    lab.run_all(lab.plan.id)
    lab.wait_until_idle(lab.plan.id, 300)
    yield lab
    lab.stop()


FIX_PROPOSAL = "fix-code-otto-cve-2022-21449"


def _accept_fix(lab) -> dict:
    """A person accepts Otto's proposed fix (the Accept button on Fixes). It runs nothing."""
    return lab.otto_decide(lab.plan.id, FIX_PROPOSAL, "accept")


def _record(lab, answer: dict) -> str:
    """Record an answer for exactly the prompt Otto asks for this assessment. Returns the prompt."""
    lab.fix_states(lab.plan.id)
    step, prompt = lab.prompts[-1]
    assert step == "write_fix"
    model.write_recorded(lab.settings.otto_recorded, "write_fix", prompt, json.dumps(answer, indent=1), "2026-11-17T12:00:00Z", HOW)
    return prompt


def test_with_no_answer_the_fix_template_is_offered_and_says_why(failed):
    lab = failed
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and fix["otto"] is None and fix["otto_note"] == "No recorded answer: this needs Live Otto."
    kinds = sorted(a["kind"] for a in fix["answers"])
    assert kinds == ["advisory_cases", "bad_signatures", "official_vectors"]          # the template answers the advisory check too
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["From a fix template"] and any("A change “Written by Otto” is not offered here" in part["v"] for p in shown["what"]["paragraphs"] for part in p)
    with lab.db() as db:
        assert db.scalars(select(OttoStepRow)).all() == []            # looking at the page asked nothing and wrote nothing
    prompt = lab.prompts[-1][1]
    assert "CVE-2022-21449" in prompt and "case 168" in prompt and 'VERSION = "1.4.2"' in prompt and "acme-sign 1.4.2" in prompt


def test_otto_writes_the_change_and_a_view_asks_nothing(failed):
    lab = failed
    _record(lab, GOOD)
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-otto-cve-2022-21449" and fix["otto"]["advisory"] == "CVE-2022-21449" and fix["otto"]["source"] == "recorded"
    assert fix["status"] == "not_connected" and sorted(a["kind"] for a in fix["answers"]) == ["advisory_cases", "bad_signatures", "official_vectors"]
    # Otto's change is a proposal: nobody has decided it, so Connect demo code is off and says why
    assert fix["proposal"] == {"id": FIX_PROPOSAL, "state": "proposed"}
    assert fix["actions"]["connect"] == "This change is a proposal. Accept it first; accepting runs nothing."
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["Written by Otto"] and shown["title"] == "acme-sign: Reject signatures whose r or s is out of range"
    proposal = shown["proposal"]
    assert proposal["label"] == "From Otto" and proposal["status"]["word"] == "Proposed" and proposal["kind"] == "fix"
    assert [(b["label"], b["can"]) for b in proposal["buttons"]] == [("Accept", True), ("Reject", True)]
    assert "failed on acme-sign 1.4.2, which is your own code" in proposal["why"]
    connect = next(b for b in shown["actions"]["buttons"] if b["action"] == "connect")
    assert connect["enabled"] is False and shown["actions"]["note"].startswith("This change is a proposal. Accept it first")
    text = json.dumps(shown)
    assert "A change was written for CVE-2022-21449 (Blank signature accepted)" in text and "fix template" not in text.lower()
    # Claude's summary reads as if the change were in ("now rejects"): before any accept it is said as what it would do
    assert "What it would change:" in text and "Nothing is changed until you accept it and connect the code" in text
    # (the card's lines stay as they are after the change is connected and merged, so they claim nothing about the present)
    assert proposal["lines"][0].startswith("What it changes: ")
    assert proposal["lines"][1].startswith("Written by Otto. Accepting it runs nothing and changes nothing:")
    # (what follows "What it changes: " is the recorded answer's own sentence, which may say "now rejects"; the words the
    # app itself puts on the card say nothing about where things stand. Until the 5c fixes of 19 November 2026 the line
    # read "What it changes, in Otto's words: ...", and this test split on that.)
    own_words = [proposal["lines"][0][:len("What it changes: ")], *proposal["lines"][1:]]
    assert own_words[0] == "What it changes: " and not any("yet" in line or "now " in line for line in own_words)
    with lab.db() as db:
        assert db.scalars(select(OttoStepRow)).all() == []            # a page that is only shown writes nothing
    # the failed advisory check's result points to this fix
    row = lab.advisories_view(lab.plan.id)["rows"][0]
    assert row["panel"]["fix"]["here"]["link"] == {"page": "fixes", "item": "fix-otto-cve-2022-21449"}
    related = {line["kind"]: line for line in lab.related(lab.plan.id, "fix:fix-otto-cve-2022-21449")}
    assert related["advisory"]["title"] == "Advisory" and related["advisory"]["items"][0]["label"] == "Blank signature accepted (CVE-2022-21449)"
    assert related["advisory"]["items"][0]["link"] == {"page": "advisories", "item": "CVE-2022-21449"}


@pytest.mark.slow
def test_ottos_change_takes_the_same_proof_path_and_is_offered_only_after_it(failed):
    lab = failed
    _record(lab, GOOD)
    # before a person accepts Otto's proposal the code is not connected: nothing is written, proven or kept
    with pytest.raises(Conflict) as not_yet:
        lab.connect_code(lab.plan.id)
    assert str(not_yet.value) == "This change is a proposal. Accept it first; accepting runs nothing. The code was not connected."
    with lab.db() as db:
        assert db.scalars(select(ChangeRow)).all() == [] and db.scalars(select(OttoStepRow)).all() == []
    accepted = _accept_fix(lab)
    assert accepted["state"] == "accepted" and accepted["actions"] == {"undo": None}          # until the code is connected
    assert not lab.jobs.busy(lab.plan.id)                                                     # accepting ran nothing
    lab.connect_code(lab.plan.id)
    lab.wait_until_idle(lab.plan.id, 300)
    lab.jobs.wait_idle(300, group=("changes", lab.plan.id))
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-otto-cve-2022-21449" and fix["change"]["written_by"] == "otto" and fix["change"]["proposed_by"] == "isogeny.otto/1"
    # once the code is connected the accept stands: it led to something that ran
    locked = lab.otto_proposal(lab.plan.id, FIX_PROPOSAL)
    assert "The code is connected" in locked["actions"]["undo"]
    with pytest.raises(Conflict):
        lab.otto_decide(lab.plan.id, FIX_PROPOSAL, "undo")
    assert fix["change"]["built"]["matches"] == {"name": "acme-sign", "version": "1.4.3"}
    assert fix["status"] == "ready" and fix["proof"]["review"]["offered"] is True
    proved = {t["kind"] for t in fix["proof"]["review"]["tests"]}
    assert "advisory_cases" in proved and {"official_vectors", "bad_signatures", "speed_size"} <= proved      # every locked test was rerun
    assert all(a["ok"] for a in fix["proof"]["review"]["answers"]) and len(fix["proof"]["review"]["answers"]) == 3
    with lab.db() as db:
        change = db.scalars(select(ChangeRow)).one()
        assert change.source["otto"]["advisory"] == "CVE-2022-21449" and change.template_id == "otto-cve-2022-21449"
        step = db.scalars(select(OttoStepRow)).one()               # the click stored the step, once
        assert step.step == "write_fix" and step.source == "recorded" and step.model is None and step.outcome == "used" and step.how == HOW
        assert step.prompt and step.answer and step.claim_id.startswith("sha256:")
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["Written by Otto"] and shown["status"]["word"] == "Ready for review" and "Otto has no say in any result" in json.dumps(shown)
    # Second review, 18 November 2026: the proof's words are its own two groups. A server test that is rerun and still
    # reads Failed "came out the same as before"; the page no longer says that every locked test passed.
    said = json.dumps(shown)
    assert ("every locked test that runs the changed code did what the proof asks of it (each pass-or-fail test passed), and every "
            "test that does not run it came out the same as before") in said
    # the card of the accepted proposal is still on the page: none of its lines says that nothing has changed
    assert "Nothing is changed yet" not in json.dumps(shown["proposal"])
    assert "every locked test passed on the changed code" not in said
    # the Claude step is in the assessment's Otto ledger in full, and the proof run of the check is bound there
    book = assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=lab.plan.id).id)
    claims = [e["payload"] for e in book.entries() if e["kind"] == "claim"]
    steps = [c for c in claims if "step" in c["artifact"]]
    assert len(steps) == 1 and steps[0]["artifact"]["step"]["prompt"] == step.prompt and steps[0]["artifact"]["step"]["answer"] == step.answer
    assert [c["artifact"]["phase"] for c in claims if "run_id" in c["artifact"]] == ["first", "proof"]
    assert book.audit() == []
    # a person approves and merges; nothing merged by itself
    assert fix["pull_request"] is None and fix["merge"] is None


# A correct fix, written a third way: one line differs from our own acme-sign 1.4.3, and it is not the program Otto's
# recorded answer gives either (that one is registered as acme-sign 1.4.3-otto).
def _other_way() -> dict:
    other = json.loads(json.dumps(GOOD))
    other["edits"][0]["put"][2] = "    if r < 1 or r >= N or s < 1 or s >= N:"
    return other


# The same fix as Otto's recorded answer writes it: it gives exactly the registered acme-sign 1.4.3-otto.
def _ottos_way() -> dict:
    other = json.loads(json.dumps(GOOD))
    other["edits"][0]["put"][2] = "    if not 1 <= r < N or not 1 <= s < N:"
    return other


def test_a_rejected_fix_is_kept_as_not_added_and_can_be_taken_up_again(failed):
    """Reject asks for an optional short reason. The proposal is not deleted: it reads "Not added (reason)", the code
    can't be connected, and Reconsider opens it for a decision again. Nothing takes its place by itself."""
    lab = failed
    _record(lab, GOOD)
    rejected = lab.otto_decide(lab.plan.id, FIX_PROPOSAL, "reject", "We ship our own patch\nthis week")
    assert rejected["state"] == "rejected" and rejected["decisions"][-1]["reason"] == "We ship our own patch this week"
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["id"] == "fix-otto-cve-2022-21449" and shown["labels"] == ["Written by Otto"]            # still Otto's, not the template
    assert shown["proposal"]["status"]["word"] == "Not added (We ship our own patch this week)"
    assert [b["label"] for b in shown["proposal"]["buttons"]] == ["Reconsider"]
    assert next(b for b in shown["actions"]["buttons"] if b["action"] == "connect")["enabled"] is False
    assert "This proposal was rejected" in shown["actions"]["note"]
    with pytest.raises(Conflict) as refused:
        lab.connect_code(lab.plan.id)
    assert "This proposal was rejected, so its change is not added" in str(refused.value)
    again = lab.otto_decide(lab.plan.id, FIX_PROPOSAL, "reconsider")
    assert again["state"] == "proposed" and set(again["actions"]) == {"accept", "reject"}
    assert [d["decision"] for d in again["decisions"]] == ["reject", "reconsider"]                        # both stay on the record


@pytest.mark.slow
def test_ottos_recorded_way_is_proven_on_its_own_registered_program_merged_and_retested(failed):
    """Kevin's decision, 18 November 2026. The change as Otto's recorded answer writes it gives acme-sign 1.4.3-otto, a
    registered demo program. So it is proposed, accepted, proven on that program, approved, merged and retested; and
    only after the merge can a retest choose that program."""
    lab = failed
    _record(lab, _ottos_way())
    before = lab.lab_view(lab.plan.id)["retest"]
    assert [v["version"] for v in before["versions"]] == ["1.4.3", "1.4.2"] and "Only our two demo versions" in before["menu_note"]
    with pytest.raises(BadRequest) as refused:
        lab.start_retest(lab.plan.id, "1.4.3-otto")                       # not before its change is merged
    assert "Only our demo versions can be chosen for a retest." in str(refused.value)
    _accept_fix(lab)
    lab.connect_code(lab.plan.id)
    lab.wait_until_idle(lab.plan.id, 300)
    lab.jobs.wait_idle(300, group=("changes", lab.plan.id))
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["change"]["written_by"] == "otto" and fix["change"]["built"]["matches"] == {"name": "acme-sign", "version": "1.4.3-otto"}
    assert fix["status"] == "ready" and fix["proof"]["review"]["offered"] is True and fix["proof"]["version"] == "1.4.3-otto"
    # the program's own version line reads 1.4.3; "1.4.3-otto" is the registry's name for it, and is said as that
    said = json.dumps(next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code"))
    assert "byte for byte one of the app's registered demo programs, acme-sign 1.4.3-otto." in said and "reports version" not in said
    lab.open_pull_request(lab.plan.id, fix["id"], ["you"])
    lab.approve(lab.plan.id, fix["id"], "you")
    lab.merge(lab.plan.id, fix["id"])
    menu = lab.lab_view(lab.plan.id)["retest"]
    assert [v["version"] for v in menu["versions"]] == ["1.4.3-otto", "1.4.3", "1.4.2"] and "Only our three demo versions" in menu["menu_note"]
    assert menu["versions"][0]["note"].startswith("The version your merged change gives. ")
    lab.retest_now(lab.plan.id, fix["id"])
    lab.wait_until_idle(lab.plan.id, 300)
    rows = [r for r in lab.lab_view(lab.plan.id)["rows"] if r["kind"] in ("official_vectors", "bad_signatures", "advisory_cases")]
    assert rows and all(r["result"]["label"] == "Failed" and r["after"]["label"] == "Passed" for r in rows)
    assert all(r["after"]["component"] == "acme-sign 1.4.3-otto" for r in rows)
    # Advisories: the row is named for acme-sign 1.4.2, and its newest result is the retest's. It says which version.
    row = lab.advisories_view(lab.plan.id)["rows"][0]
    assert row["result"]["label"] == "Passed" and row["result"]["text"] == "Retest on acme-sign 1.4.3-otto. First run on acme-sign 1.4.2: Failed."
    assert row["panel"]["here"]["rows"][0]["result"]["ran_on"] == ("This is the retest, on acme-sign 1.4.3-otto. The first run, on "
                                                                   "acme-sign 1.4.2, read Failed.")
    book = assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=lab.plan.id).id)
    assert book.audit() == []


def test_a_change_that_gives_no_registered_program_is_not_offered_and_the_template_takes_its_place(failed):
    """Only our registered demo programs may run. A change whose program is not one of them, byte for byte, can't be
    proven, so it is not offered: the page says why and offers the fix template, and that is what a click connects."""
    lab = failed
    _record(lab, _other_way())
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and fix["otto"] is None
    assert "could not be used" in fix["otto_note"] and "byte for byte" in fix["otto_note"] and "only those can run" in fix["otto_note"]
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["From a fix template"] and "A change “Written by Otto” is not offered here" in json.dumps(shown, ensure_ascii=False)
    with lab.db() as db:
        assert db.scalars(select(OttoStepRow)).all() == []            # looking at the page wrote nothing
    lab.connect_code(lab.plan.id)                                     # the click connects what the page offered
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and fix["change"]["written_by"] == "fix_template"
    assert fix["change"]["built"]["matches"] == {"name": "acme-sign", "version": "1.4.3"} and "byte for byte" in fix["otto_note"]
    with lab.db() as db:
        step = db.scalars(select(OttoStepRow)).one()                 # the click kept Otto's step, with why it was not used
        assert step.outcome == "refused" and "byte for byte" in step.refusal and step.claim_id.startswith("sha256:")
        change = db.scalars(select(ChangeRow)).one()
        assert "1 <= r < N or not" not in json.dumps(change.files)   # nothing of the refused change is on a branch
    lab.fix_states(lab.plan.id)
    with lab.db() as db:
        assert len(db.scalars(select(OttoStepRow)).all()) == 1       # kept once


def test_an_answer_that_does_not_apply_is_refused_and_recorded(failed):
    lab = failed
    bad = json.loads(json.dumps(GOOD))
    bad["edits"][0]["find"] = ["    this line is not in the file"]
    _record(lab, bad)
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and "could not be used" in fix["otto_note"]       # the template, with the reason
    lab.connect_code(lab.plan.id)                                     # the page offered the template, so that is connected
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["change"]["written_by"] == "fix_template" and "could not be used" in fix["otto_note"]
    with lab.db() as db:
        step = db.scalars(select(OttoStepRow)).one()
        assert step.outcome == "refused" and "does not apply to the code" in step.refusal


def test_a_live_change_that_gives_no_registered_program_is_refused_at_the_click_and_connects_nothing(failed, monkeypatch):
    """With Live Otto on, the page lists the fix as Otto's, not yet written. The click asks Claude; when the answer
    gives a program that is not one of ours, the app says so, connects nothing and keeps the step. After that the
    page offers the fix template, and the next click connects it without asking Claude again."""
    lab = failed
    calls = []

    def transport(body, headers, timeout):
        calls.append(1)
        data = {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(_other_way())}],
                "usage": {"input_tokens": 9000, "output_tokens": 700}}
        return 200, json.dumps(data).encode()
    monkeypatch.setattr(model, "_http_transport", transport)
    monkeypatch.setenv(model.KEY_ENV, "made-up-key-for-tests-0123456789")
    lab.set_live_otto(on=True)
    assert next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")["otto"]["pending"] is True and calls == []
    with pytest.raises(Conflict) as not_yet:                             # nobody accepted Otto's proposal: Claude is not asked
        lab.connect_code(lab.plan.id)
    assert "Accept it first" in str(not_yet.value) and calls == []
    assert "Have Otto write a change" in _accept_fix(lab)["title"] and calls == []                       # accepting asks nothing either
    with pytest.raises(Conflict) as refused:
        lab.connect_code(lab.plan.id)
    assert "The written change could not be used" in str(refused.value) and "byte for byte" in str(refused.value)
    assert "The code was not connected" in str(refused.value) and calls == [1]
    with lab.db() as db:
        step = db.scalars(select(OttoStepRow)).one()
        assert step.source == "live" and step.outcome == "refused" and "byte for byte" in step.refusal
        assert db.scalars(select(ChangeRow)).all() == []
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and "byte for byte" in fix["otto_note"]
    lab.connect_code(lab.plan.id)
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["change"]["written_by"] == "fix_template" and calls == [1]            # Claude was asked once, by the first click
    with lab.db() as db:
        assert len(db.scalars(select(OttoStepRow)).all()) == 1


def test_live_otto_asks_claude_only_when_a_person_connects_the_code(failed, monkeypatch):
    """With a key and the switch on, a page lists the fix as Otto's (not yet written); the live call is made by the
    click, once, within the limit. The network is a stand-in: no test ever reaches the API."""
    lab = failed
    calls = []

    def transport(body, headers, timeout):
        calls.append(json.loads(body))
        data = {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(GOOD)}],
                "usage": {"input_tokens": 9000, "output_tokens": 700}}
        return 200, json.dumps(data).encode()
    monkeypatch.setattr(model, "_http_transport", transport)
    monkeypatch.setenv(model.KEY_ENV, "made-up-key-for-tests-0123456789")
    lab.set_live_otto(on=True)
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-otto-cve-2022-21449" and fix["otto"]["pending"] is True and calls == []       # looking asked nothing
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    # nothing is written yet, so nothing is labelled as Otto's; the card says what the click sends and when an answer is refused
    said = json.dumps(shown)
    assert shown["labels"] == ["Not written yet"] and "Written by Otto" not in said and calls == []
    assert "sends this program's source file" in said and "Otherwise it is refused and nothing is connected" in said
    assert shown["proposal"]["status"]["word"] == "Proposed" and "nothing is written yet" in json.dumps(shown["proposal"]["lines"])
    _accept_fix(lab)
    assert calls == []                                                   # the accept itself asked nothing
    lab.connect_code(lab.plan.id)
    assert len(calls) == 1 and 'VERSION = \\"1.4.2\\"' in json.dumps(calls[0]["messages"])
    with lab.db() as db:
        step = db.scalars(select(OttoStepRow)).one()
        assert step.source == "live" and step.model == "claude-opus-5-5" and step.cost_nano_usd == 9000 * 5000 + 700 * 25000
        assert "made-up-key" not in json.dumps([step.prompt, step.answer, step.how])
    lab.fix_states(lab.plan.id)
    lab.fixes_view(lab.plan.id)
    assert len(calls) == 1                                           # the stored answer is used from then on
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["change"]["written_by"] == "otto" and fix["change"]["built"]["matches"] == {"name": "acme-sign", "version": "1.4.3"}


def test_after_a_live_step_the_key_is_nowhere(failed, monkeypatch, caplog, capsys):
    """The (made-up) key is in the environment for one live step, and Claude's answer even repeats it. Afterwards
    it is in no file of the data folder (the database and the assessment's Otto ledger among them), not in the
    evidence file or its report, and in nothing that was logged or printed."""
    import logging
    lab = failed
    key = "made-up-key-for-tests-0123456789"
    echoing = json.loads(json.dumps(GOOD))
    echoing["summary"] = f"The verify command now refuses a signature whose two numbers are out of range. ({key})"

    def transport(body, headers, timeout):
        assert headers["x-api-key"] == key                      # the one place the key goes: the request's own header
        data = {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(echoing)}],
                "usage": {"input_tokens": 9000, "output_tokens": 700}}
        return 200, json.dumps(data).encode()
    monkeypatch.setattr(model, "_http_transport", transport)
    monkeypatch.setenv(model.KEY_ENV, key)
    with caplog.at_level(logging.DEBUG):
        lab.set_live_otto(on=True)
        _accept_fix(lab)
        lab.connect_code(lab.plan.id)
        lab.wait_until_idle(lab.plan.id, 300)
        lab.jobs.wait_idle(300, group=("changes", lab.plan.id))
        lab.fixes_view(lab.plan.id)
        lab.advisories_view(lab.plan.id)
        lab.otto_view()
        made = lab.export_evidence(lab.plan.id)
        files = {which: lab.evidence_file(made["id"], which)[1] for which in ("json", "html")}
    with lab.db() as db:
        step = db.scalars(select(OttoStepRow)).one()
        assert step.source == "live" and "[API key removed]" in step.answer          # what Claude repeated was taken out
    needle = key.encode("utf-8")
    assert b"[API key removed]" in files["json"] and all(needle not in data for data in files.values())
    holding = [str(path) for path in lab.settings.data_dir.rglob("*") if path.is_file() and needle in path.read_bytes()]
    assert holding == []
    printed = capsys.readouterr()
    assert key not in caplog.text and key not in printed.out and key not in printed.err
    assert key not in json.dumps([lab.fixes_view(lab.plan.id), lab.advisories_view(lab.plan.id), lab.otto_view()])


def test_live_otto_that_fails_says_so_and_connects_nothing(failed, monkeypatch):
    lab = failed
    calls = []

    def refused(body, headers, timeout):
        calls.append(1)
        return 401, json.dumps({"error": {"type": "authentication_error", "message": "the stand-in says no to made-up-key-for-tests-0123456789"}}).encode()
    monkeypatch.setattr(model, "_http_transport", refused)
    monkeypatch.setenv(model.KEY_ENV, "made-up-key-for-tests-0123456789")
    lab.set_live_otto(on=True, limit="0.01")           # a limit too small for even one request
    _accept_fix(lab)
    with pytest.raises(Conflict) as limited:
        lab.connect_code(lab.plan.id)
    assert "spending limit for this run is $0.01" in str(limited.value) and "The code was not connected" in str(limited.value)
    assert calls == []                                              # the request that could pass the limit was never sent
    lab.set_live_otto(limit="2")
    with pytest.raises(Conflict) as failed_call:
        lab.connect_code(lab.plan.id)
    assert "answered with an error (401" in str(failed_call.value) and "the stand-in says no" in str(failed_call.value)
    assert "made-up-key" not in str(failed_call.value) and "[API key removed]" in str(failed_call.value) and calls == [1]
    with lab.db() as db:
        assert db.scalars(select(OttoStepRow)).all() == [] and db.scalars(select(ChangeRow)).all() == []
