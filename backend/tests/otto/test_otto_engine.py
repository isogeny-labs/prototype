"""Phase 5c: when Otto's engine offers a change it wrote, and when the fix template takes its place. These tests ask
the engine directly, with a stand-in for the lab and the real demo program as text, so they need no demo run and
no Otto: the whole path through a real assessment is in test_otto_fix.py (the slow set).

The answers used here were written for the tests (they are fixtures, not answers from Claude)."""
import json

import pytest

from app.engine import research
from app.otto import fixes, model
from app.otto.engine import NOT_REGISTERED, OttoCouldNot, OttoEngine
from app.run import components

HOW = "Written for a test, not an answer from Claude"
# The change that turns acme-sign 1.4.2 into exactly our registered 1.4.3, as an answer in the shape Otto asks for.
GOOD = {"title": "Reject signatures whose r or s is out of range",
        "summary": "The verify command now refuses a signature whose two numbers are zero or not below the curve order.",
        "answers": [1, 2],
        "edits": [{"file": "acme_sign.py", "title": "The range check", "why": "r and s must each be at least 1 and below n.",
                   "find": ["    except ValueError:", '        return {"valid": False}', "    e = digest_int(message)"],
                   "put": ["    except ValueError:", '        return {"valid": False}', "    if not (1 <= r < N and 1 <= s < N):",
                           '        return {"valid": False}', "    e = digest_int(message)"]},
                  {"file": "acme_sign.py", "title": "The version number", "why": "So the changed program can be told from the one before.",
                   "find": ['VERSION = "1.4.2"'], "put": ['VERSION = "1.4.3"']}]}
ADVISORY = {"id": "CVE-2022-21449", "plain_name": "Missing ECDSA signature range check", "pack": "2026.11.1",
            "quote": "if (rb.signum() == 0 || sb.signum() == 0"}
WRONG = [{"id": "r0-s0", "comment": "r = 0, s = 0", "flags": [], "expected": "invalid", "got": "accept"},
         {"id": "s-plus-n", "comment": "s above the allowed range", "flags": [], "expected": "invalid", "got": "accept"}]


def _other_way() -> dict:
    """A correct fix, written another way: one line differs from our own acme-sign 1.4.3."""
    other = json.loads(json.dumps(GOOD))
    other["edits"][0]["put"][2] = "    if not 1 <= r < N or not 1 <= s < N:"
    return other


def _request(mode: str, template_only: bool = False) -> dict:
    """The question the Fixes code asks: a failed server test (not Otto's business), a failed signing test and the
    failed advisory check, with the program's code as text; and, beside it, who is asking."""
    source = components.lookup("acme-sign", "1.4.2").read_text(encoding="utf-8")
    failed = [{"kind": "tls_versions", "reason_code": None, "detail": {"accepted_outside_claim": ["TLS 1.2"]}},
              {"kind": "bad_signatures", "reason_code": None, "detail": {"wrong": WRONG}},
              {"kind": research.ADVISORY_KIND, "reason_code": None, "detail": {"wrong": WRONG[:1]}, "advisory": ADVISORY,
               "title": "Advisory check: Missing ECDSA signature range check (CVE-2022-21449)"}]
    return {"component": {"name": "acme-sign", "version": "1.4.2"}, "failed": failed, "files": {"acme_sign.py": source},
            "asking": {"plan_id": 7, "mode": mode, "template_only": template_only}}


class StandInLab:
    """What the engine needs of the lab: the stored step, the recorded answer, a live call, and keeping a step."""

    def __init__(self, recorded: dict | None = None, live: object = None, live_ready: bool = False):
        self.recorded_answer, self.live_answer, self.live_ok = recorded, live, live_ready
        self.stored, self.asked, self.kept, self.prompts = None, 0, [], []

    def _step(self, answer: dict, source: str, prompt: str) -> model.Step:
        text = json.dumps(answer)
        return model.Step(step="write_fix", source=source, model="claude-opus-5-5" if source == "live" else None, prompt=prompt, answer=text,
                          prompt_sha256=model.sha256_text(prompt), answer_sha256=model.sha256_text(text), input_tokens=0, output_tokens=0,
                          cost_nano_usd=0, at="2026-11-17T12:00:00Z", how=HOW)

    def otto_stored_step(self, plan_id, step, digest):
        return self.stored

    def otto_live_ready(self) -> bool:
        return self.live_ok

    def otto_model(self, live: bool = True):
        lab = self

        class Client:
            live_ready = lab.live_ok and live

            def recorded(self, step, prompt):
                lab.prompts.append(prompt)
                return lab._step(lab.recorded_answer, "recorded", prompt) if lab.recorded_answer is not None else None

            def ask(self, step, prompt):
                lab.asked += 1
                if isinstance(lab.live_answer, Exception):
                    raise lab.live_answer
                return lab._step(lab.live_answer, "live", prompt)
        return Client()

    def otto_record_step(self, plan_id, advisory_id, step, outcome, refusal) -> int:
        self.kept.append({"plan_id": plan_id, "advisory": advisory_id, "source": step.source, "outcome": outcome, "refusal": refusal})
        self.stored = {"id": len(self.kept), "answer": step.answer, "source": step.source, "how": step.how, "model": step.model,
                       "at": step.at, "claim_id": "sha256:" + "0" * 64}
        return len(self.kept)


def _engine(**lab) -> tuple[OttoEngine, StandInLab]:
    stand_in = StandInLab(**lab)
    return OttoEngine(research.RuleEngine(25, 4), stand_in), stand_in


def _is_template(reply: dict) -> bool:
    return reply["template_id"] == research.RANGE_CHECK["id"] and reply.get("written_by") is None and reply.get("otto") is None


def test_ottos_change_is_offered_when_it_gives_a_registered_program():
    engine, lab = _engine(recorded=GOOD)
    reply = engine.propose_change(_request("view"))
    assert reply["written_by"] == "otto" and reply["proposed_by"] == fixes.OTTO_ID and reply["label"] == "Written by Otto"
    assert reply["template_id"] == "otto-cve-2022-21449" and reply["branch"] == "fix/otto-cve-2022-21449"
    assert reply["files"]["acme_sign.py"] == components.lookup("acme-sign", "1.4.3").read_text(encoding="utf-8")
    assert reply["answers"] == [1, 2]                  # places in the request: the signing test and the advisory check, never the server test
    assert reply["otto"]["source"] == "recorded" and reply["otto"]["advisory"] == "CVE-2022-21449" and reply["otto"]["pending"] is False
    assert lab.kept == [] and lab.asked == 0           # looking at a page keeps nothing and asks nothing
    # what Otto was shown: the program's failed tests only, the advisory and the code
    prompt = lab.prompts[-1]
    assert "CVE-2022-21449" in prompt and 'VERSION = "1.4.2"' in prompt and "case r0-s0" in prompt and "TLS 1.2" not in prompt
    # the click keeps the step, once, as used
    again = engine.propose_change(_request("connect"))
    assert again["files"] == reply["files"] and [k["outcome"] for k in lab.kept] == ["used"] and lab.asked == 0
    engine.propose_change(_request("connect"))
    assert len(lab.kept) == 1


def test_a_change_that_gives_no_registered_program_is_not_offered():
    """Only our registered demo programs may run, so such a change can't be proven. The page offers the fix template
    with the reason, and a click connects the template: the page had said so before the click."""
    engine, lab = _engine(recorded=_other_way())
    shown = engine.propose_change(_request("view"))
    assert _is_template(shown) and shown["otto_note"] == f"Otto wrote one, but it could not be used: {NOT_REGISTERED}"
    assert "byte for byte" in shown["otto_note"] and lab.kept == []
    connected = engine.propose_change(_request("connect"))
    assert _is_template(connected) and connected["otto_note"] == shown["otto_note"]
    assert [(k["outcome"], k["refusal"]) for k in lab.kept] == [("refused", NOT_REGISTERED)]
    engine.propose_change(_request("connect"))
    assert len(lab.kept) == 1 and lab.asked == 0


def test_an_answer_that_is_no_clean_change_is_not_offered_either():
    bad = json.loads(json.dumps(GOOD))
    bad["edits"][0]["find"] = ["    this line is not in the file"]
    engine, lab = _engine(recorded=bad)
    shown = engine.propose_change(_request("view"))
    assert _is_template(shown) and "could not be used" in shown["otto_note"] and "does not apply to the code" in shown["otto_note"]
    assert _is_template(engine.propose_change(_request("connect"))) and lab.kept[0]["outcome"] == "refused"


def test_with_no_answer_and_live_otto_off_the_template_is_offered_and_says_why():
    engine, lab = _engine()
    for mode in ("view", "connect"):
        reply = engine.propose_change(_request(mode))
        assert _is_template(reply) and reply["otto_note"] == "No recorded answer: this needs Live Otto."
    assert lab.kept == [] and lab.asked == 0


def test_live_otto_asks_only_at_the_click():
    engine, lab = _engine(live=GOOD, live_ready=True)
    pending = engine.propose_change(_request("view"))
    assert pending["written_by"] == "otto" and pending["otto"]["pending"] is True and pending["edits"] == [] and lab.asked == 0
    assert pending["files"] == _request("view")["files"]              # it holds no change yet
    assert pending["label"] == "Not written yet"                      # and is not labelled as Otto's before it is written
    connected = engine.propose_change(_request("connect"))
    assert lab.asked == 1 and connected["otto"]["source"] == "live" and connected["otto"]["pending"] is False
    assert connected["files"]["acme_sign.py"] == components.lookup("acme-sign", "1.4.3").read_text(encoding="utf-8")
    assert [(k["source"], k["outcome"]) for k in lab.kept] == [("live", "used")]
    engine.propose_change(_request("view"))
    engine.propose_change(_request("connect"))
    assert lab.asked == 1 and len(lab.kept) == 1                      # the stored answer is used from then on


def test_with_live_otto_on_the_recorded_answer_is_not_used():
    """Live means live: with the switch on and a key present, the answer comes from Claude at the person's click, even
    where an answer was recorded for exactly this prompt."""
    engine, lab = _engine(recorded=_other_way(), live=GOOD, live_ready=True)
    assert engine.propose_change(_request("view"))["otto"]["pending"] is True and lab.asked == 0
    connected = engine.propose_change(_request("connect"))
    assert lab.asked == 1 and connected["otto"]["source"] == "live" and connected["written_by"] == "otto"
    assert connected["files"]["acme_sign.py"] == components.lookup("acme-sign", "1.4.3").read_text(encoding="utf-8")
    # with the switch off again, an assessment that has no stored step works on the recorded answer
    engine, lab = _engine(recorded=_other_way(), live=GOOD, live_ready=False)
    assert _is_template(engine.propose_change(_request("connect"))) and lab.asked == 0 and lab.kept[0]["source"] == "recorded"


def test_a_live_answer_that_cannot_be_used_is_refused_at_the_click_and_then_the_template_is_offered():
    engine, lab = _engine(live=_other_way(), live_ready=True)
    assert engine.propose_change(_request("view"))["otto"]["pending"] is True
    with pytest.raises(OttoCouldNot) as refused:
        engine.propose_change(_request("connect"))      # the person asked for Otto's change and there is none to connect
    assert str(refused.value) == f"Otto's change could not be used: {NOT_REGISTERED}"
    assert [(k["source"], k["outcome"], k["refusal"]) for k in lab.kept] == [("live", "refused", NOT_REGISTERED)] and lab.asked == 1
    shown = engine.propose_change(_request("view"))
    assert _is_template(shown) and "byte for byte" in shown["otto_note"]
    assert _is_template(engine.propose_change(_request("connect")))          # the next click connects what the page offers
    assert lab.asked == 1 and len(lab.kept) == 1


def test_a_live_call_that_fails_says_so_at_the_click_and_keeps_nothing():
    engine, lab = _engine(live=model.LiveCallFailed("Claude answered with an error (401)."), live_ready=True)
    with pytest.raises(OttoCouldNot) as failed:
        engine.propose_change(_request("connect"))
    assert str(failed.value) == "Otto could not write the change: Claude answered with an error (401)." and lab.kept == []


def test_the_fix_template_is_asked_about_alone_and_a_plan_without_an_advisory_check_never_reaches_otto():
    engine, lab = _engine(recorded=GOOD)
    assert _is_template(engine.propose_change(_request("view", template_only=True))) and lab.prompts == []
    no_check = _request("view")
    no_check["failed"] = no_check["failed"][:2]
    reply = engine.propose_change(no_check)
    assert _is_template(reply) and "otto_note" not in reply and lab.prompts == []
    # the rule engine is given the question only, never who is asking
    seen = []
    real = engine.rules.propose_change
    engine.rules.propose_change = lambda request: seen.append(request) or real(request)
    engine.propose_change(no_check)
    assert seen and "asking" not in seen[0] and set(seen[0]) == {"component", "failed", "files"}
