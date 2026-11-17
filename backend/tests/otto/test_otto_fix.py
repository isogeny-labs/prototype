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
from app.errors import Conflict
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
    lab.add_new_checks(lab.plan.id)
    play_back_speed(lab)
    lab.run_all(lab.plan.id)
    lab.wait_until_idle(lab.plan.id, 300)
    yield lab
    lab.stop()


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
    assert shown["labels"] == ["From a fix template"] and any("Otto's own change is not offered here" in part["v"] for p in shown["what"]["paragraphs"] for part in p)
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
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["Written by Otto"] and shown["title"] == "acme-sign: Reject signatures whose r or s is out of range"
    text = json.dumps(shown)
    assert "Otto wrote a change for CVE-2022-21449 (Blank signature accepted)" in text and "fix template" not in text.lower()
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
    lab.connect_code(lab.plan.id)
    lab.wait_until_idle(lab.plan.id, 300)
    lab.jobs.wait_idle(300, group=("changes", lab.plan.id))
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-otto-cve-2022-21449" and fix["change"]["written_by"] == "otto" and fix["change"]["proposed_by"] == "isogeny.otto/1"
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
    # the Claude step is in the assessment's Otto ledger in full, and the proof run of the check is bound there
    book = assurance.Ledger(lab.settings.data_dir, lab.assessment_for(plan_id=lab.plan.id).id)
    claims = [e["payload"] for e in book.entries() if e["kind"] == "claim"]
    steps = [c for c in claims if "step" in c["artifact"]]
    assert len(steps) == 1 and steps[0]["artifact"]["step"]["prompt"] == step.prompt and steps[0]["artifact"]["step"]["answer"] == step.answer
    assert [c["artifact"]["phase"] for c in claims if "run_id" in c["artifact"]] == ["first", "proof"]
    assert book.audit() == []
    # a person approves and merges; nothing merged by itself
    assert fix["pull_request"] is None and fix["merge"] is None


# A correct fix, written another way: one line differs from our own acme-sign 1.4.3.
def _other_way() -> dict:
    other = json.loads(json.dumps(GOOD))
    other["edits"][0]["put"][2] = "    if not 1 <= r < N or not 1 <= s < N:"
    return other


def test_a_change_that_gives_no_registered_program_is_not_offered_and_the_template_takes_its_place(failed):
    """Only our registered demo programs may run. A change whose program is not one of them, byte for byte, can't be
    proven, so it is not offered: the page says why and offers the fix template, and that is what a click connects."""
    lab = failed
    _record(lab, _other_way())
    fix = next(f for f in lab.fix_states(lab.plan.id) if f["kind"] == "code")
    assert fix["id"] == "fix-ecdsa-range-check" and fix["otto"] is None
    assert "could not be used" in fix["otto_note"] and "byte for byte" in fix["otto_note"] and "only those can run" in fix["otto_note"]
    shown = next(f for f in lab.fixes_view(lab.plan.id)["fixes"] if f["kind"] == "code")
    assert shown["labels"] == ["From a fix template"] and "Otto's own change is not offered here" in json.dumps(shown)
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
    with pytest.raises(Conflict) as refused:
        lab.connect_code(lab.plan.id)
    assert "Otto's change could not be used" in str(refused.value) and "byte for byte" in str(refused.value)
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
