"""Phase 6c, first half: six fixed questions, answered by fixed rules from the assessment's own records.

An answer is a short list of facts, each a sentence a page already shows about the item, with the link to where it is
shown. No model is asked. These tests read the answers the shared walk got at its stages
(tests/assistant/assistant_walk.py, `ASKED`), and ask a few more of the walk's assessment, which is closed by then:
answering is a read, and a closed assessment still answers."""
from pathlib import Path

import pytest

from app.assistant import commands, questions, words
from app.assistant.threads import PAGE_LABELS, PAGES
from app.web import models
from tests.view_helpers import problems

BANNED = ("secure", "score", "severity", "critical", "time to hack")


def _said(walk, stage: str, page: str, sentence: str) -> dict:
    return walk.at[stage].said[(page, sentence)]


def _texts(reply: dict) -> list[str]:
    return [f["text"] for f in reply["facts"]]


# ---------------------------------------------------------------- reading a question

@pytest.mark.parametrize("sentence, question, rest", [
    ("why did this check fail?", "why_failed", "this check"), ("Why did the blank signature check fail", "why_failed", "the blank signature check"),
    ("why is the speed test failing", "why_failed", "the speed test"), ("what went wrong?", "why_failed", ""),
    ("what went wrong with the range check", "why_failed", "the range check"), ("why did it not pass", "why_failed", "it"),
    ("what does this result show, and what doesn't it?", "shows", "this result"), ("what does the speed test prove", "shows", "the speed test"),
    ("where did this suggestion come from?", "came_from", "this suggestion"), ("why is the java fix proposed", "came_from", "the java fix"),
    ("what happens if I accept this?", "if_accept", "this"), ("what would accepting the java fix do", "if_accept", "the java fix"),
    ("what is this page for?", "page_for", ""), ("what is evidence for", "page_for", "evidence"), ("what am i looking at", "page_for", ""),
    ("what should I do next?", "next", ""), ("what now", "next", ""), ("what's next", "next", ""),
])
def test_a_fixed_question_is_read_in_its_wordings(sentence, question, rest):
    read = commands.read(sentence)
    assert (read["key"], read["question"], read["rest"]) == ("ask", question, rest)


def test_there_are_six_fixed_questions_and_each_reads_as_itself_and_a_command_is_still_a_command():
    assert [q["key"] for q in questions.QUESTIONS] == ["why_failed", "shows", "came_from", "if_accept", "page_for", "next"]
    for q in questions.QUESTIONS:
        read = commands.read(q["ask"])
        assert (read["key"], read["question"]) == ("ask", q["key"]), q["ask"]
    # a question is never taken for a command, and a command never for a question
    assert commands.read("what can you do?")["key"] == "help" and commands.read("show me failed checks")["key"] == "filter"
    assert commands.read("where is the java fix")["key"] == "open_item" and commands.read("run all")["key"] == "run_all"
    assert set(words.PAGE_FOR) == set(PAGES)
    for sentence in words.PAGE_FOR.values():
        assert sentence.endswith(".") and not any(word in sentence.lower() for word in BANNED)


# ---------------------------------------------------------------- the answers, at the stages of the walk

@pytest.mark.needs_otto
def test_every_answer_fits_its_shape_every_fact_has_a_link_that_opens_a_page_and_nothing_is_rated(assistant_walk):
    seen = 0
    for stage, snap in assistant_walk.at.items():
        for (_page, sentence), reply in getattr(snap, "said", {}).items():
            if reply["kind"] != "answer":
                continue
            seen += 1
            assert problems(reply, models.AssistantReply, f"{stage}: {sentence}") == []
            assert reply["label"] == "From this assessment's records" and reply["question"] in questions.ASK.values()
            assert reply["facts"] and reply["entry"] is None and reply["open"] is None and reply["go"] is None      # facts only: nothing to confirm
            for f in reply["facts"]:
                assert f["text"] and not any(word in f["text"].lower() for word in BANNED), f["text"]
                assert f["link"] is not None and f["link"]["page"] in PAGES and f["label"]        # every fact has its link
    assert seen >= 15


@pytest.mark.needs_otto
def test_why_did_this_check_fail_is_answered_from_the_results_own_words(assistant_walk):
    lab, pid = assistant_walk.lab, assistant_walk.plan_id
    reply = _said(assistant_walk, "ran", "evidence", "why did the blank signature check fail?")
    assert reply["kind"] == "answer" and reply["question"] == "Why did this check fail?" and reply["thread"] == "testing"
    row = next(r for r in lab.lab_view(pid)["rows"] if "Blank signature accepted" in r["title"])
    result = row["result"]
    said = _texts(reply)
    # the reviewer's word, then the result's own plain sentence, what happened, the control: word for word what Evidence shows
    assert said[0] == f"“{row['title']}” reads Failed on {result['component']}." and result["label"] == "Failed"
    assert said[1] == result["plain"]
    for line in result["what_happened"][:3]:
        assert line in said
    assert result["control"]["text"] in said
    # where the check came from, with the way to its advisory; and the fix, with the way to it
    assert result["otto"]["line"] in said
    links = {f["label"]: f["link"] for f in reply["facts"] if f["link"]}
    assert links["See the evidence"] == {"page": "evidence", "item": f"test-{row['item_id']}", "group": None}
    # each link opens where its sentence stands: the plain sentence is in the Evidence table (a result's open panel
    # does not repeat it), what happened is in the result's own panel
    where = {f["text"]: (f["label"], f["link"]["item"]) for f in reply["facts"]}
    assert where[result["plain"]] == ("See the Evidence table", None) and links["See the Evidence table"]["page"] == "evidence"
    assert all(where[line] == ("See the evidence", f"test-{row['item_id']}") for line in result["what_happened"][:3])
    assert links["Open the advisory"] == {"page": "advisories", "item": "CVE-2022-21449", "group": None}
    assert any(f["link"] and f["link"]["page"] == "fixes" for f in reply["facts"])
    # nothing in the answer is the assistant's own: every sentence between the first and the fix's is on the result, word for word
    on_the_result = {result["plain"], result["control"]["text"], result["otto"]["line"], *result["what_happened"]}
    fix = result["fix_line"]
    assert said[-1] == f"Evidence says of its fix: “{fix['lead']} {fix['rest']}”."
    assert all(text in on_the_result for text in said[1:-1]) and len(said) >= 5


@pytest.mark.needs_otto
def test_with_several_failed_checks_and_none_named_it_asks_which_one(assistant_walk):
    which = _said(assistant_walk, "ran", "evidence", "why did this check fail?")
    failed = [r["title"] for r in assistant_walk.lab.lab_view(assistant_walk.plan_id)["rows"] if (r["result"] or {}).get("code") == "failed"]
    assert which["kind"] == "which" and len(failed) >= 2
    assert [o["say"] for o in which["options"]] == [f"Why did {commands.sayable(title)} fail?" for title in failed]
    assert [o["label"] for o in which["options"]] == [f"{title} (Failed)" for title in failed]
    for option, title in zip(which["options"], failed, strict=True):          # each option names exactly one, and answers about it
        assert commands.read(option["say"])["question"] == "why_failed"
        settled = assistant_walk.at["ran"].said[("evidence", option["say"])]
        assert settled["kind"] == "answer" and settled["facts"][0]["text"].startswith(f"“{title}” reads Failed")
    # a check whose result is no failure: the answer repeats the result's own word and plain sentence, and says nothing
    # of its own about failing or not failing
    measured = _said(assistant_walk, "ran", "evidence", "why did the speed test fail?")
    speed = next(r for r in assistant_walk.lab.lab_view(assistant_walk.plan_id)["rows"] if r["title"] == "Speed and size")
    assert measured["kind"] == "answer" and _texts(measured) == ["“Speed and size” reads Measured on acme-sign 1.4.2.", speed["result"]["plain"]]
    # before anything ran: there is no result to ask about, and it says where results come from
    none = _said(assistant_walk, "proposed", "checks", "why did this check fail?")
    assert none["kind"] == "answer" and _texts(none) == ["No test of the plan has a result yet. Results come from running the test plan on Checks."]


@pytest.mark.needs_otto
def test_the_open_item_is_the_check_the_question_is_about(assistant_walk):
    lab, pid, aid = assistant_walk.lab, assistant_walk.plan_id, assistant_walk.assessment_id
    row = next(r for r in lab.lab_view(pid)["rows"] if "Blank signature accepted" in r["title"])
    for item in (f"test-{row['item_id']}", "CVE-2022-21449"):                  # its row on Checks or Evidence, or its advisory
        reply = lab.assistant_answer(aid, "evidence", item, "why did this check fail?")
        assert reply["kind"] == "answer" and row["title"] in reply["facts"][0]["text"], item
    shows = lab.assistant_answer(aid, "evidence", f"test-{row['item_id']}", "what does this result show, and what doesn't it?")
    assert _texts(shows)[1:] == row["result"]["shows"][:8] and shows["question"] == "What does this result show, and what doesn't it?"


@pytest.mark.needs_otto
def test_what_a_result_shows_is_the_results_own_lines(assistant_walk):
    reply = _said(assistant_walk, "ran", "evidence", "what does the blank signature check show, and what doesn't it?")
    row = next(r for r in assistant_walk.lab.lab_view(assistant_walk.plan_id)["rows"] if "Blank signature accepted" in r["title"])
    assert reply["kind"] == "answer" and _texts(reply)[1:] == row["result"]["shows"][:8] and row["result"]["shows"]


@pytest.mark.needs_otto
def test_where_a_suggestion_came_from_and_what_accepting_it_does_are_the_proposals_own_lines(assistant_walk):
    from app.present import otto as present_otto
    came = _said(assistant_walk, "proposed", "checks", "where did the blank signature check come from?")
    assert came["kind"] == "answer" and came["thread"] == "testing"
    said = _texts(came)
    assert "is a proposal marked From Otto, on Advisories. It reads “Proposed”." in said[0]
    assert said[1].startswith("Why it applies: ")
    assert any(line.startswith("Tried on public copies before the pack was signed") for line in said)
    assert said[-1] == "Nobody has decided this yet."
    assert all(f["link"] == {"page": "advisories", "item": "CVE-2022-21449", "group": None} for f in came["facts"])
    # several suggestions on the page and none named: which one? Each option then answers about its own.
    several = _said(assistant_walk, "proposed", "checks", "where did this suggestion come from?")
    assert several["kind"] == "which" and len(several["options"]) == 3
    for option in several["options"]:
        settled = assistant_walk.at["proposed"].said[("checks", option["say"])]
        assert settled["kind"] == "answer" and option["label"].rsplit(" (on ", 1)[0] in settled["facts"][0]["text"]
    # the one fix on Fixes: "this" is it
    one = _said(assistant_walk, "ran", "fixes", "where did this suggestion come from?")
    assert one["kind"] == "answer" and one["thread"] == "fixing"
    accept = _said(assistant_walk, "proposed", "checks", "what happens if i accept the blank signature check?")
    lines = _texts(accept)
    assert lines[0].startswith("Accepting “Advisory check: Blank signature accepted") and lines[0].endswith(", on Advisories:")
    assert lines[1:4] == words.ACCEPT_LINES["check"]
    # (what the page really does: there, Accept records at the click; only in this panel does it wait for Confirm)
    assert lines[-1] == ("In this panel Accept waits for your Confirm. On Advisories the Accept button records the decision at the click. "
                         "Either way it is recorded with who and when, and it words no result.")
    assert present_otto.ACCEPT_NOTES["check"].startswith("Accept adds this check to the test plan")
    assert _said(assistant_walk, "ran", "fixes", "what happens if i accept this?")["facts"][1]["text"] == words.ACCEPT_LINES["fix"][0]


@pytest.mark.needs_otto
def test_what_a_page_is_for_and_what_to_do_next(assistant_walk):
    page = _said(assistant_walk, "ran", "checks", "what is this page for?")
    assert page["kind"] == "answer" and page["text"] == "What is Checks for?" and _texts(page)[0] == words.PAGE_FOR["checks"]
    assert _texts(page)[1].startswith("On it now: 6 tests in the test plan, 6 with a result.")
    other = _said(assistant_walk, "proposed", "overview", "what is evidence for?")
    assert other["text"] == "What is Evidence for?" and other["facts"][0]["link"] == {"page": "evidence", "item": None, "group": None}
    assert _said(assistant_walk, "proposed", "checks", "what is the moon for?")["kind"] == "cannot"
    evidence = _said(assistant_walk, "ran", "evidence", "what is this page for?")
    assert _texts(evidence)[1] == "On it now, of the test plan: 6 tests have a result, and 4 of them read as failed."
    # what to do next is the Overview's own next step, at every stage
    for stage in ("proposed", "ran"):
        nxt = _said(assistant_walk, stage, "overview", "what should i do next?")
        want = assistant_walk.at[stage].overview["next_step"]
        assert nxt["kind"] == "answer" and _texts(nxt)[0] == f"Next: {want['label']}. {want['text']}"
        assert nxt["facts"][0]["link"]["page"] == want["page"]
    # what else waits for a decision, by page; not said twice where the next step already sends there
    assert len(_texts(_said(assistant_walk, "proposed", "overview", "what should i do next?"))) == 1
    assert _texts(_said(assistant_walk, "ran", "overview", "what should i do next?"))[1:] == ["1 proposed fix waits for a decision on Fixes."]
    # before a file is in
    assert _texts(_said(assistant_walk, "empty", "overview", "what should i do next?")) == [words.NO_FILE]
    assert _texts(_said(assistant_walk, "empty", "inventory/import", "what is this page for?"))[0] == words.PAGE_FOR["inventory/import"]
    assert _texts(_said(assistant_walk, "empty", "checks", "why did this check fail?")) == [words.NO_FILE]


@pytest.mark.needs_otto
def test_a_closed_assessment_still_answers_and_the_chips_are_the_questions_that_fit(assistant_walk):
    closed = assistant_walk.at["closed"]
    assert closed.said[("evidence", "why did the blank signature check fail?")]["kind"] == "answer"
    assert closed.said[("overview", "what should i do next?")]["kind"] == "answer"
    assert closed.asking_changed_nothing
    # the chips: up to three of the six, the most particular first
    for stage in ("empty", "proposed", "ran", "closed"):
        for page in PAGES:
            fit = assistant_walk.at[stage].pages[page]["box"]["questions"]
            assert 1 <= len(fit) <= 3 and set(fit) <= set(questions.ASK.values()), (stage, page)
    assert assistant_walk.at["empty"].pages["overview"]["box"]["questions"] == ["What should I do next?", "What is this page for?"]
    assert assistant_walk.at["proposed"].pages["checks"]["box"]["questions"][:2] == ["Where did this suggestion come from?", "What happens if I accept this?"]
    assert assistant_walk.at["ran"].pages["evidence"]["box"]["questions"][0] == "Why did this check fail?"
    assert "Why did this check fail?" not in assistant_walk.at["proposed"].pages["evidence"]["box"]["questions"]
    assert PAGE_LABELS["evidence"] == "Evidence"


@pytest.mark.needs_otto
def test_a_question_asked_in_an_open_assessment_is_kept_with_the_facts_of_its_answer(assistant_walk):
    said = assistant_walk.at["said"]
    page, sentence, reply = said.sent[-1]
    assert (page, sentence, reply["kind"]) == ("evidence", "why did the blank signature check fail?", "answer")
    kept = assistant_walk.lab.assistant_messages(assistant_walk.plan_id)[-1]
    # what is kept is what was answered: the one line, and the facts as they were then, each with its link
    assert (kept["said"], kept["kind"], kept["reply"], kept["thread"]) == (sentence, "answer", reply["text"], "testing")
    assert kept["facts"] == reply["facts"] and len(kept["facts"]) >= 5
    # in the Testing tab it stands under "This thread so far", as "You said", with its facts and nothing to press
    entry = next(e for t in said.pages["evidence"]["tabs"] if t["key"] == "testing" for e in t["so_far"] if e["kind"] == "said" and e["title"] == sentence)
    assert entry["mark"] == "You said" and entry["text"] == reply["text"] and entry["facts"] == reply["facts"]
    assert entry["decisions"] == [] and entry["step"] is None
    assert problems(said.pages["evidence"], models.AssistantView, "the panel with a kept answer") == []
    # an exchange that is not an answer keeps no facts
    assert all(m["facts"] == [] for m in assistant_walk.lab.assistant_messages(assistant_walk.plan_id)[:-1])



# ---------------------------------------------------------------- after the separate review of 6c (19 November 2026)

def _out(kind, text, **more):
    return {"kind": kind, "text": text, **more}


def _result(label: str, tone: str, **more) -> dict:
    return {"code": "x", "label": label, "tone": tone, "run_id": 1, "component": "acme-sign 1.4.3", "plain": f"The plain sentence of a result that reads {label}.",
            "what_happened": ["What happened, line one.", "What happened, line two."], "control": {"text": "The control's own line."},
            "shows": ["It shows one thing.", "It doesn't show another."], **more}


def test_a_failure_is_read_from_the_results_own_tone_and_the_answer_never_words_one_itself():
    """ "Slowdown found" after a retest is the reviewer's failure (red on its page); "Couldn't run" is neither a pass
    nor a failure. The answer repeats the word; it never says of its own that something failed or did not."""
    slow = {"item_id": 5, "title": "Speed and size", "result": _result("Measured", "neutral"), "after": _result("Slowdown found", "fail")}
    told = [f["text"] for f in questions._why_failed(slow, "Speed and size", _out)["facts"]]
    assert told[0] == "“Speed and size” reads Slowdown found on acme-sign 1.4.3." and "What happened, line one." in told and "The control's own line." in told
    for label, tone in (("Couldn't run", "warn"), ("Couldn't trust this run", "warn"), ("Passed", "pass"), ("Measured", "neutral")):
        row = {"item_id": 5, "title": "Speed and size", "result": _result(label, tone), "after": None}
        told = [f["text"] for f in questions._why_failed(row, "Speed and size", _out)["facts"]]
        assert told == [f"“Speed and size” reads {label} on acme-sign 1.4.3.", f"The plain sentence of a result that reads {label}."]
    assert questions._failed(_result("Slowdown found", "fail")) and not questions._failed(_result("Couldn't run", "warn")) and not questions._failed(None)
    # no sentence the module can say holds "did not fail" or "didn't fail"
    source = Path(questions.__file__).read_text(encoding="utf-8")
    said = [line for line in source.splitlines() if ("did not fail" in line or "didn't fail" in line) and not line.lstrip().startswith(("#", '"""', "it never", "nor"))]
    assert said == [], said


@pytest.mark.needs_otto
def test_a_name_no_test_or_suggestion_has_gets_i_cant_do_that_never_a_false_there_is_none(assistant_walk):
    lab, aid = assistant_walk.lab, assistant_walk.assessment_id
    failed = [r for r in lab.lab_view(assistant_walk.plan_id)["rows"] if (r["result"] or {}).get("tone") == "fail"]
    assert len(failed) >= 2                                    # there are failed checks: "there is none" would be untrue
    for sentence in ("why did the moon check fail?", "what does the moon check show?", "why did the proof fail?"):
        reply = lab.assistant_answer(aid, "evidence", None, sentence)
        assert (reply["kind"], reply["text"]) == ("cannot", "I can't do that. No test of the plan is called that.") and reply["can"], sentence
    assert len(lab.otto_proposals(assistant_walk.plan_id)) >= 3
    for sentence in ("where did the moon fix come from?", "what happens if i accept the moon check?"):
        reply = lab.assistant_answer(aid, "checks", None, sentence)
        assert (reply["kind"], reply["text"]) == ("cannot", "I can't do that. No suggestion here is called that."), sentence
    # question 2 in a few more words is still question 2 about the open item
    for sentence in ("what does this result show, and what does it not show?", "what does this result show and what doesn't it show",
                     "what does this result show, and what it doesn't?"):
        read = commands.read(sentence)
        assert (read["question"], read["rest"]) == ("shows", "this result"), sentence


@pytest.mark.needs_otto
def test_this_check_is_the_open_item_and_nothing_else(assistant_walk):
    """With something open that has no test result of its own, the answer says that. It never answers about another
    check that happens to have failed elsewhere."""
    lab, aid, pid = assistant_walk.lab, assistant_walk.assessment_id, assistant_walk.plan_id
    rows = lab.lab_view(pid)["rows"]
    not_run = next(r for r in rows if r["result"] is None)                       # the third check: accepted, never run
    failing = next(r for r in rows if "Blank signature accepted" in r["title"])
    for question in ("why did this check fail?", "what does this result show, and what doesn't it?"):
        waiting = lab.assistant_answer(aid, "checks", f"test-{not_run['item_id']}", question)
        assert waiting["kind"] == "answer" and [f["text"] for f in waiting["facts"]] == [f"“{not_run['title']}” has no result yet. It gets one when it is run, on Checks."]
        assert waiting["facts"][0]["link"] == {"page": "checks", "item": f"test-{not_run['item_id']}", "group": None}
        other = lab.assistant_answer(aid, "checks", f"retest-{failing['item_id']}-on-1", question)
        assert [f["text"] for f in other["facts"]] == [questions.OTHER_RUN]
        proof = lab.assistant_answer(aid, "checks", f"proof-{failing['item_id']}-in-1", question)
        assert [f["text"] for f in proof["facts"]] == [questions.OTHER_RUN]
        for item in ("claim-1", "fix-otto-cve-2022-21449", "CVE-2019-14853"):       # a claim, a fix, an advisory with no check in the plan
            reply = lab.assistant_answer(aid, "checks", item, question)
            assert [f["text"] for f in reply["facts"]] == [questions.NOT_A_TEST], (item, question)
    # and the chips follow the same rule: no "Why did this check fail?" beside an open item that has no failed result of its own
    view = lab.lab_view(pid)
    proposals = lab.otto_proposals(pid)
    assert questions.ASK["why_failed"] in questions.fitting("evidence", None, view, proposals, [])                        # nothing open: one of them failed
    assert questions.fitting("evidence", f"test-{failing['item_id']}", view, proposals, [])[:2] == [questions.ASK["why_failed"], questions.ASK["shows"]]
    for item in (f"test-{not_run['item_id']}", f"proof-{failing['item_id']}-in-1", "claim-1", "CVE-2019-14853"):
        offered = questions.fitting("checks", item, view, proposals, [])
        assert questions.ASK["why_failed"] not in offered and questions.ASK["shows"] not in offered, item
    assert questions._open("CVE-2022-21449", view["rows"], proposals) == ("row", failing)


def test_tests_that_share_a_title_can_each_be_named_and_which_one_settles():
    """The multi-target demo file has one "Old TLS versions" for each server. An option must name exactly one."""
    groups = [{"key": "a", "kind": "server", "heading": "Server: localhost:8443", "note": None},
              {"key": "b", "kind": "server", "heading": "Server: localhost:8444", "note": None}]
    rows = [{"item_id": 1, "title": "Old TLS versions", "group": "a", "result": _result("Failed", "fail"), "after": None},
            {"item_id": 2, "title": "Old TLS versions", "group": "b", "result": _result("Failed", "fail"), "after": None},
            {"item_id": 3, "title": "Certificate strength", "group": "a", "result": _result("Passed", "pass"), "after": None}]
    view = {"rows": rows, "groups": groups}
    names = questions._row_names(view)
    assert names == {1: "Old TLS versions on Server: localhost:8443", 2: "Old TLS versions on Server: localhost:8444", 3: "Certificate strength"}
    kind, pool = questions._pick_row("the tls test", None, view, names, [], failed_first=True)
    assert kind == "which" and [r["item_id"] for r in pool] == [1, 2]
    for row in pool:                                            # the sentence an option sends names exactly its own test
        sentence = f"Why did {commands.sayable(names[row['item_id']])} fail?"
        read = commands.read(sentence)
        assert read["question"] == "why_failed"
        assert questions._pick_row(read["rest"], None, view, names, [], failed_first=True) == ("row", row), sentence
    # two that still read the same get their number
    assert commands.distinct([(7, "Same", None), (8, "Same", None), (9, "Other", "x")]) == {7: "Same (number 7)", 8: "Same (number 8)", 9: "Other"}
    # the bare title, which both share, still asks
    assert questions._pick_row("old tls versions", None, view, names, [], failed_first=True)[0] == "which"


@pytest.mark.needs_otto
def test_nothing_waits_where_nothing_can_be_decided_and_a_proposal_that_is_no_longer_made_says_so(assistant_walk):
    closed = assistant_walk.at["closed"]
    told = _texts(closed.said[("overview", "what should i do next?")])
    assert len(told) == 1 and not any("wait" in line for line in told)                 # a closed assessment: nothing waits for a decision
    assert closed.waiting == 0                                                           # ... as the Overview counts it
    page = assistant_walk.lab.assistant_answer(assistant_walk.assessment_id, "checks", None, "what is this page for?")
    assert not any("waits for a decision" in f["text"] or "wait for a decision" in f["text"] for f in page["facts"])
    # in an open assessment the counts are the Overview's own
    at = assistant_walk.at["ran"]
    lines = _texts(at.said[("checks", "what is this page for?")])
    assert lines[1].endswith("1 suggestion waits for a decision.") and at.waiting >= 1
    # a proposal that is no longer made: its page's own note is among the facts
    from app.present import otto as present_otto
    p = next(p for p in assistant_walk.lab.otto_proposals(assistant_walk.plan_id) if p["kind"] == "check")
    told = [f["text"] for f in questions._came_from({**p, "current": False}, _out)["facts"]]
    assert told[-1] == present_otto.NO_LONGER_PROPOSED == "This is no longer proposed here: what it was about has changed since. It stays on the record."
    assert present_otto.NO_LONGER_PROPOSED not in [f["text"] for f in questions._came_from(p, _out)["facts"]]


def test_the_page_sentences_say_what_the_pages_own_headers_say():
    import inspect

    from app.present import fixes as present_fixes
    from app.present import migration as present_migration
    from app.present import otto as present_otto_
    assert "every published advisory in the installed test packs" in words.PAGE_FOR["advisories"].lower()
    assert "Every published advisory in the installed test packs." in inspect.getsource(present_otto_)
    for phrase in ("what the migration plan needs done", "A code change is ready for review only after its proof has passed."):
        assert phrase in words.PAGE_FOR["fixes"] and phrase in present_fixes.SUBLINE_WITH_MIGRATION
    assert "every track of every system" in words.PAGE_FOR["migration/roadmap"].lower()
    assert "Every track of every system has a place" in inspect.getsource(present_migration)
    assert "wherever it was started" in words.PAGE_FOR["checks"] and "The test plan is under Encryption tests" in words.PAGE_FOR["checks"]


def test_a_page_is_named_by_its_own_name_and_another_word_for_it_needs_the_word_page():
    class NoFile:
        has_file = False
        waiting: dict = {}

    def ask(sentence: str, page: str = "checks") -> dict:
        read = commands.read(sentence)
        assert read["question"] == "page_for", sentence
        return questions._page_for(NoFile(), read["rest"], page, [], _out, [{"say": "Open Evidence"}], "page" in commands.tokens(sentence))
    assert ask("what is evidence for?")["text"] == "What is Evidence for?" and ask("what is the roadmap for")["text"] == "What is Roadmap for?"
    assert ask("what is the tests page for?")["text"] == "What is Checks for?"                 # another word for it, with "page"
    fix = ask("what is the fix for?")                                                          # not a question about the Fixes page
    assert fix["kind"] == "cannot" and fix["text"] == "I can't do that. There is no page of that name." and fix["can"]
    assert ask("what is this page for?", "fixes")["text"] == "What is Fixes for?"


def test_only_a_title_counts_as_an_exact_name_and_a_stored_value_names_nothing():
    update = {"names": ["Update python-ecdsa 0.13.2 to 0.13.3 before the move", "python-ecdsa", "0.13.2"], "id": "update"}
    check = {"names": ["Advisory check: Malformed signature accepted (CVE-2019-14859) on python-ecdsa 0.13.2", "CVE-2019-14859", "python-ecdsa 0.13.2"], "id": "check"}
    assert commands.match("python-ecdsa", [update, check]) == [update, check]                  # a library's bare name is no title: both fit, so it asks
    assert commands.exact("python-ecdsa", [update, check]) == []
    assert commands.names_of({"title": "A fix", "about": {"advisory": "CVE-2022-21449", "program": "acme-sign 1.4.2", "fix": "fix-otto-1", "written": "yes",
                                                          "design": "ab" * 32, "pack": "2026.11.1", "item": 7}}) == ["A fix", "CVE-2022-21449", "acme-sign 1.4.2"]
    assert commands.match("yes", [{"names": commands.names_of({"title": "A fix", "about": {"written": "yes"}})}]) == []


def test_only_a_time_the_app_itself_wrote_is_shown_in_the_viewers_zone():
    from app.present import times
    text = "2. Rejected by A tester on 19 November 2026, 06:46 UTC: call them back on 1 December 2026, 09:00 UTC."
    with times.for_screen():
        shown = times.remarked(text, ["2026-11-19T06:46:03Z"])
        assert shown == "2. Rejected by A tester on [[time:2026-11-19T06:46:03Z]]: call them back on 1 December 2026, 09:00 UTC."
        assert times.remarked(text, []) == text and times.remarked(text, None) == text
        # the typed reason holds the very same minute: only one place is the app's
        twice = "Rejected by A on 19 November 2026, 06:46 UTC: as agreed on 19 November 2026, 06:46 UTC."
        assert times.remarked(twice, ["2026-11-19T06:46:00Z"]).count("[[time:") == 1
    assert times.remarked(text, ["2026-11-19T06:46:03Z"]) == text                             # for a file: as stored
    assert times.moments("on [[time:2026-11-19T06:46:03Z]] and [[time:2026-11-20T01:02:03Z]]") == ["2026-11-19T06:46:03Z", "2026-11-20T01:02:03Z"]


def test_a_data_folder_made_before_the_facts_column_gets_it_when_opened(tmp_path):
    """Phase 6b's build made `assistant_messages` without `facts`. Opening such a folder adds the column; its rows stay."""
    import sqlite3

    from sqlalchemy import select

    from app.db import AssistantMessageRow, make_session_factory
    path = tmp_path / "evidence-lab.sqlite3"
    make_session_factory(path)                                                               # today's tables ...
    raw = sqlite3.connect(path)
    raw.executescript("DROP TRIGGER IF EXISTS assistant_messages_no_update; DROP TRIGGER IF EXISTS assistant_messages_no_delete; "
                      "DROP TABLE assistant_messages; "
                      "CREATE TABLE assistant_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL, at VARCHAR(40) NOT NULL, "
                      "by VARCHAR(100) NOT NULL, page VARCHAR(60) NOT NULL, item VARCHAR(200), thread VARCHAR(20), said TEXT NOT NULL, "
                      "kind VARCHAR(20) NOT NULL, reply TEXT NOT NULL, go JSON, created_at DATETIME); "
                      "INSERT INTO assistant_messages (plan_id, at, by, page, said, kind, reply) VALUES (1, '2026-11-19T06:00:00Z', 'You', 'checks', "
                      "'show me failed checks', 'went', 'Opened Checks.');")
    raw.commit()
    assert "facts" not in [row[1] for row in raw.execute("PRAGMA table_info(assistant_messages)")]          # ... as the 6b build left it
    raw.close()
    session = make_session_factory(path)
    with session() as db:
        row = db.scalars(select(AssistantMessageRow)).one()
        assert row.said == "show me failed checks" and row.facts is None
    raw = sqlite3.connect(path)
    assert "facts" in [row[1] for row in raw.execute("PRAGMA table_info(assistant_messages)")]
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):                                         # and it is add-only again
        raw.execute("DELETE FROM assistant_messages")
    raw.close()
