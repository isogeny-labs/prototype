"""Phase 6c, first half: six fixed questions, answered by fixed rules from the assessment's own records.

An answer is a short list of facts, each a sentence a page already shows about the item, with the link to where it is
shown. No model is asked. These tests read the answers the shared walk got at its stages
(tests/assistant/assistant_walk.py, `ASKED`), and ask a few more of the walk's assessment, which is closed by then:
answering is a read, and a closed assessment still answers."""
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
                assert f["link"] is None or f["link"]["page"] in PAGES
                assert (f["label"] is None) == (f["link"] is None)
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
    assert links["Open the advisory"] == {"page": "advisories", "item": "CVE-2022-21449", "group": None}
    assert any(f["link"] and f["link"]["page"] == "fixes" for f in reply["facts"])
    # nothing in the answer is the assistant's own: every sentence between the first and the fix's is on the result, word for word
    on_the_result = {result["plain"], result["control"]["text"], result["otto"]["line"], *result["what_happened"]}
    fix = result["fix_line"]
    assert said[-1] == f"Fixes lists a fix for this result. It reads “{fix['lead']} {fix['rest']}”."
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
    # a check that did not fail: it says so, in the result's own words
    passed = _said(assistant_walk, "ran", "evidence", "why did the speed test fail?")
    assert passed["kind"] == "answer" and "did not fail: it reads" in passed["facts"][0]["text"]
    # before anything ran: there is no result to ask about, and it says where results come from
    none = _said(assistant_walk, "proposed", "checks", "why did this check fail?")
    assert none["kind"] == "answer" and _texts(none) == ["No check of this assessment has a result yet. Results come from running the test plan on Checks."]


@pytest.mark.needs_otto
def test_the_open_item_is_the_check_the_question_is_about(assistant_walk):
    lab, pid, aid = assistant_walk.lab, assistant_walk.plan_id, assistant_walk.assessment_id
    row = next(r for r in lab.lab_view(pid)["rows"] if "Blank signature accepted" in r["title"])
    for item in (f"test-{row['item_id']}", f"retest-{row['item_id']}", "CVE-2022-21449"):          # its row on Checks or Evidence, or its advisory
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
    assert lines[1:4] == words.ACCEPT_LINES["check"] and "waits for your Confirm" in lines[-1]
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
    assert "read Failed." in _texts(evidence)[1] or "reads Failed." in _texts(evidence)[1]
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

