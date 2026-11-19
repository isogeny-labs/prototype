"""Phase 6e, first half: a what-if typed to the Otto panel. Fixed rules read it; the answer is what the app knows, in
four parts, filed under Fixing; the one thing that could be started is Evidence's own Retest new version, as that
button's card with its Confirm step; and asking starts nothing and decides nothing."""
import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.assistant import commands
from app.config import DEMO_DIR
from app.web import models
from conftest import demo_plan, make_lab

DEPENDENCIES = DEMO_DIR / "dependencies-demo.cdx.json"
ASK = "If I update elliptic to 6.5.7, how does that affect my libraries and dependencies?"


def _kept(lab) -> dict:
    with lab.db() as db:
        tables = [r[0] for r in db.execute(text("select name from sqlite_master where type = 'table' order by name"))]
        return {t: hashlib.sha256(repr(db.execute(text(f'select * from "{t}"')).fetchall()).encode()).hexdigest() for t in tables}


@pytest.fixture(scope="module")
def asked(tmp_path_factory):
    lab = make_lab(tmp_path_factory.mktemp("whatif-answer"))
    try:
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])
        lab.remove_test(plan.id, plan.item["speed_size"])
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        lab.install_pack("2026.11.2")
        lab.add_dependency_list(plan.id, DEPENDENCIES.name, DEPENDENCIES.read_bytes())
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 120)
        aid = lab.assessment_for(plan_id=plan.id).id
        before = _kept(lab)
        replies = {s: lab.assistant_answer(aid, page, None, s) for s, page in (
            (ASK, "migration/dependencies"), ("what if we upgrade acme-sign to 1.4.3?", "evidence"), ("What if I update left-pad to 1.3.0?", "overview"),
            ("what if I update elliptic to 6.5.7 and python-ecdsa to 0.13.3?", "checks"), ("update elliptic to 6.5.7", "checks"),
            ("What can you do?", "migration/dependencies"))}
        yield SimpleNamespace(lab=lab, plan=plan, aid=aid, replies=replies, untouched=_kept(lab) == before, idle=lab.jobs.live(plan.id) == [])
    finally:
        lab.stop()


@pytest.mark.parametrize("sentence, library, version", [
    ("What if I update elliptic to 6.5.7?", "elliptic", "6.5.7"),
    (ASK, "elliptic", "6.5.7"),
    ("what happens if we upgrade python-ecdsa from 0.13.2 to 0.13.3", "python-ecdsa", "0.13.3"),
    ("Otto, what if we move openssl to 3.5.0?", "openssl", "3.5.0"),
    ("suppose I bump the elliptic package to v6.5.7", "elliptic", "6.5.7"),
    ("what would happen if someone updated bn.js to 5.2.1: does it break?", "bn.js", "5.2.1"),
    ("What if we update elliptic to 6.5.7. Does anything break?", "elliptic", "6.5.7"),
    ("What if I update @noble/curves to 1.4.0?", "@noble/curves", "1.4.0"),
])
def test_fixed_rules_read_a_what_if_and_cut_the_library_and_the_version_from_the_persons_own_words(sentence, library, version):
    read = commands.read(sentence)
    assert (read["key"], read["library"], read["version"], read["several"]) == ("what_if", library, version, False)


@pytest.mark.parametrize("sentence, key", [
    ("update elliptic to 6.5.7", None),                         # names no button of this app, and is no question
    ("what if i update elliptic", None),                        # no version
    ("what if I update elliptic to the newest version?", None),  # a version starts with a digit
    ("What happens if I accept this?", "ask"),                  # still the fixed question of 6c
    ("what if I accept the java fix", None),
    ("run all", "run_all"), ("show me failed checks", "filter"),
])
def test_what_is_no_what_if_is_not_read_as_one(sentence, key):
    assert commands.read(sentence)["key"] == key


def test_the_answer_is_what_the_app_knows_in_four_parts_filed_under_fixing(asked):
    reply = asked.replies[ASK]
    models.AssistantReply.model_validate(reply)
    assert (reply["kind"], reply["thread"], reply["text"], reply["label"]) == ("whatif", "fixing", "What if elliptic is updated to 6.5.7?", "From what the app knows")
    card = reply["whatif"]
    assert [g["key"] for g in card["facts"]] == ["used", "needs", "advisories", "trial", "post_quantum", "blocks", "own_results"]
    assert card["explanation"] == "Live Otto is off. This is what the app knows." and card["hypotheses"]
    # the scanner file does not name elliptic: nothing to rerun, so no card to press, and the reason is said
    assert reply["entry"] is None and card["test_copy"]["offered"] is False and "does not name elliptic" in card["test_copy"]["reason"]
    # the same facts as plain lines, for what is kept of the exchange
    assert len(reply["facts"]) == sum(len(g["lines"]) or 1 for g in card["facts"])
    assert reply["facts"][0]["text"].startswith("Where the library is used: elliptic 6.5.6 is in your dependency list")
    assert reply["facts"][0]["link"]["page"] == "migration/dependencies"


def test_where_the_page_offers_the_retest_the_answer_hands_back_that_buttons_own_card(asked):
    reply = asked.replies["what if we upgrade acme-sign to 1.4.3?"]
    models.AssistantReply.model_validate(reply)
    assert reply["kind"] == "whatif" and reply["whatif"]["test_copy"]["offered"] is True
    entry = reply["entry"]
    assert (entry["what"], entry["title"]) == ("next:retest", "Retest new version") and entry["where"]["label"] == "On Evidence"
    action = {k: v for k, v in entry["step"]["action"].items() if v is not None}
    assert action == {"type": "retest", "plan_id": asked.plan.id, "version": "1.4.3", "component": "acme-sign"}
    assert entry["step"]["can"] is True and entry["step"]["confirm"]["names"] == "This is the Retest new version button on Evidence."
    # it is the very card the panel shows beside Evidence
    beside = [e for e in asked.lab.assistant_view(asked.aid, "evidence")["on_page"]["entries"] if e["id"] == entry["id"]]
    assert beside and beside[0]["step"] == entry["step"]
    assert reply["open"] is None                          # the Confirm step is not opened for the person: they press the button first


def test_asking_started_nothing_and_changed_nothing(asked):
    assert asked.untouched and asked.idle


def test_a_library_the_app_knows_nothing_about_gets_an_answer_that_says_so(asked):
    reply = asked.replies["What if I update left-pad to 1.3.0?"]
    assert reply["kind"] == "whatif" and reply["whatif"]["known"] is False and reply["entry"] is None
    assert reply["whatif"]["hypotheses"] == [{"text": "The app holds nothing about this library, so everything about the update is open."}]


def test_two_updates_in_one_sentence_are_not_answered_for_the_first_alone_and_a_bare_update_is_no_command(asked):
    two = asked.replies["what if I update elliptic to 6.5.7 and python-ecdsa to 0.13.3?"]
    assert two["kind"] == "cannot" and two["text"].startswith("I can't do that. A what-if is about one library and one version at a time.")
    assert two["whatif"] is None
    bare = asked.replies["update elliptic to 6.5.7"]
    assert bare["kind"] == "cannot" and "What if I update elliptic to 6.5.7?" in [c["say"] for c in bare["can"]]
    assert "What if I update elliptic to 6.5.7?" in [c["say"] for c in asked.replies["What can you do?"]["can"]]


def test_the_exchange_is_kept_with_its_facts_and_shows_in_the_fixing_thread(asked):
    lab, plan, aid = asked.lab, asked.plan, asked.aid
    said = lab.assistant_say(plan.id, "migration/dependencies", None, ASK)
    assert said["kind"] == "whatif"
    kept = lab.assistant_messages(plan.id)[-1]
    assert (kept["said"], kept["thread"], kept["reply"]) == (ASK, "fixing", "What if elliptic is updated to 6.5.7?")
    assert kept["facts"] and kept["facts"][0]["text"].startswith("Where the library is used: ")
    assert "[[time:" not in json.dumps(kept)
    view = lab.assistant_view(aid, "migration/dependencies")
    models.AssistantView.model_validate(view)
    fixing = next(t for t in view["tabs"] if t["key"] == "fixing")
    said_entry = next(e for e in fixing["so_far"] if e["what"] == "said:fixing" and ASK in json.dumps(e))
    assert said_entry["facts"] and said_entry["facts"][0]["text"].startswith("Where the library is used: ")


def test_in_a_closed_assessment_the_facts_are_given_and_nothing_can_be_started(asked):
    lab, aid = asked.lab, asked.aid
    lab.update_assessment(aid, {"close": True, "signed_off_by": "A reviewer", "note": ""})
    reply = lab.assistant_answer(aid, "evidence", None, "what if we upgrade acme-sign to 1.4.3?")
    models.AssistantReply.model_validate(reply)
    assert reply["kind"] == "whatif" and reply["whatif"]["facts"]
    assert reply["whatif"]["test_copy"]["offered"] is False and "closed" in reply["whatif"]["test_copy"]["reason"].lower()
    assert reply["entry"] is None or reply["entry"]["step"]["can"] is False
