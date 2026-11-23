"""Phase 6b: commands. A typed sentence either takes you somewhere at once or comes back as a card with its Confirm
step. Nothing is decided or started by typing.

The first tests are about the fixed rules that read a sentence (no assessment is needed). The others read the answers
the shared walk got at each of its stages (tests/assistant/assistant_walk.py asks the sentences in `ASKED`), so they
cost no walk of their own."""

import random

import pytest

from app.assistant import answers, commands
from app.assistant.threads import ENTRY_KINDS, PAGE_LABELS, PAGES
from app.web import models
from tests.assistant import assistant_walk as made
from tests.view_helpers import problems

BANNED = ("secure", "score", "severity", "critical", "time to hack")


def _said(walk, stage: str, page: str, sentence: str) -> dict:
    return walk.at[stage].said[(page, sentence)]


# ---------------------------------------------------------------- the one list, and the rules that read a sentence


def test_the_one_list_has_three_kinds_and_every_start_names_a_kind_of_entry_and_its_page():
    kinds = {c["kind"] for c in commands.COMMANDS}
    assert kinds == {"go", "do", "page"} and len({c["key"] for c in commands.COMMANDS}) == len(commands.COMMANDS)
    for c in commands.COMMANDS:
        assert c["say"] and c["say"][0].isupper()
        if c["kind"] == "do" and c["key"] not in commands.DECISIONS:
            assert (
                c["what"] in ENTRY_KINDS and c["what"].startswith("next:") and c["page"] in PAGES
            )  # a page's own button, by its entry kind
        if c["kind"] == "page":
            assert c["done"].endswith(".") and (c["page"] in PAGES or c["page"] == "settings")
    # what is done on its page only is exactly what the panel never presses (SPEC section 2, 6b)
    assert {c["key"] for c in commands.COMMANDS if c["kind"] == "page"} == {
        "approve",
        "merge",
        "apply",
        "roll_back",
        "sign_off",
        "own_tick",
        "choose_option",
        "mark_reviewed",
        "download",
        "settings",
        "bring_in_demo_change",
    }  # (phase 6d: it runs nothing, and it is still the person's own click on Change watch)
    # every next step the panel of 6a can offer behind Confirm can also be asked for
    asked_for = {c["what"] for c in commands.COMMANDS if c.get("what")}
    assert asked_for == {k for k in ENTRY_KINDS if k.startswith("next:") and k != "next:open"}


@pytest.mark.parametrize(
    "sentence, key, pieces",
    [
        ("show me failed checks", "filter", {"page": "checks", "filter": "result", "value": "Failed"}),
        ("Show failed checks", "filter", {"page": "checks", "value": "Failed"}),
        ("show me the checks that failed", "filter", {"page": "checks", "value": "Failed"}),
        ("list all passed tests", "filter", {"page": "checks", "value": "Passed"}),
        ("show failed results", "filter", {"page": "evidence", "value": "failed"}),
        ("show proposed checks", "filter", {"page": "advisories", "filter": "decision", "value": "proposed"}),
        ("show retests", "filter", {"page": "checks", "filter": "from", "value": "retest"}),
        ("open evidence", "open_page", {"page": "evidence"}),
        ("go to the roadmap", "open_page", {"page": "migration/roadmap"}),
        ("take me to the dependencies page", "open_page", {"page": "migration/dependencies"}),
        ("show fixes", "open_page", {"page": "fixes"}),
        ("open the Java fix", "open_item", {"rest": "java fix"}),
        ("open CVE-2022-21449", "open_item", {"rest": "cve-2022-21449"}),
        ("what can you do?", "help", {}),
        ("help", "help", {}),
        # phase 6d: Change watch's own button, and the one that stays on its page
        ("run the picked tests", "run_picked_tests", {"rest": ""}),
        ("Run the picked tests for Revert the range check", "run_picked_tests", {"rest": "revert the range check"}),
        ("rerun the picked tests on dev/revert-range-check", "run_picked_tests", {"rest": "dev/revert-range-check"}),
        ("please run the tests picked for the revert", "run_picked_tests", {"rest": "the revert"}),
        ("bring in a demo change", "bring_in_demo_change", {}),
        ("add the demo change", "bring_in_demo_change", {}),
        ("bring in a change", "bring_in_demo_change", {}),
        ("run the tests", "run_all", {}),  # (still the plan's own Run all)
        ("apply the change", "apply", {}),  # (still the server change's Apply)
        ("close the fixing tab", "tab", {"thread": "fixing", "how": "close"}),
        ("open the planning tab", "tab", {"thread": "planning", "how": "open"}),
        ("accept the Java fix", "accept", {"rest": "the java fix", "reason": None}),
        (
            "reject the Java fix: we stay on 17.0.2 until January",
            "reject",
            {"rest": "the java fix", "reason": "we stay on 17.0.2 until January"},
        ),
        ("decline the second suggestion", "reject", {"rest": "the second suggestion", "reason": None}),
        ("undo the second suggestion", "undo", {"rest": "the second suggestion"}),
        ("reconsider the python fix", "reconsider", {"rest": "the python fix"}),
        ("run all", "run_all", {}),
        ("Otto, could you please run all the tests", "run_all", {}),
        ("rerun everything", "run_all", {}),
        ("run the speed test", "run", {"rest": "the speed test"}),
        ("verify claims", "verify", {}),
        ("please verify the claims", "verify", {}),
        ("retest on 1.4.3", "retest", {"rest": "1.4.3"}),
        ("retest", "retest", {"rest": ""}),
        ("retest now", "retest_now", {}),
        ("connect demo code", "connect", {}),
        ("connect the code", "connect", {}),
        ("run proof again", "run_proof_again", {}),
        ("open pull request", "open_pull_request", {}),
        ("open a pull request for the range check", "open_pull_request", {"rest": "the range check"}),
        ("try on a test copy", "try", {}),
        ("try the tls change", "try", {"rest": "the tls change"}),
        ("ask for approval", "ask_approval", {}),
        ("measure status", "measure_status", {}),
        ("measure all", "measure_all", {}),
        ("measure elliptic", "measure_library", {"rest": "elliptic"}),
        # done on its page only
        ("merge it", "merge", {}),
        ("approve the pull request", "approve", {}),
        ("apply", "apply", {}),
        ("roll back", "roll_back", {}),
        ("rollback the change", "roll_back", {}),
        ("close and sign off", "sign_off", {}),
        ("I own this system", "own_tick", {}),
        ("choose the hybrid option", "choose_option", {}),
        ("mark it reviewed", "mark_reviewed", {}),
        ("download evidence", "download", {}),
        ("turn on live otto", "settings", {}),
        # nothing the rules read
        ("make me a sandwich", None, {}),
        ("is this system secure?", None, {}),
        ("delete the assessment", None, {}),
        ("", None, {}),
    ],
)
def test_a_sentence_is_read_by_fixed_rules_into_one_line_of_the_list_and_its_pieces(sentence, key, pieces):
    read = commands.read(sentence)
    assert read["key"] == key, read
    for name, value in pieces.items():
        assert read.get(name) == value, (name, read)
    assert commands.read(sentence) == read  # the same sentence always reads the same
    assert key is None or key in commands.BY_KEY


def test_a_reason_is_cut_from_the_persons_own_words_and_never_rewritten():
    typed = "Reject the Java fix:   We stay on 17.0.2 until January (CHANGE-FREEZE #12); see Ops' note."
    read = commands.read(typed)
    assert (
        read["key"] == "reject"
        and read["reason"] == "We stay on 17.0.2 until January (CHANGE-FREEZE #12); see Ops' note."
    )
    assert read["reason"] in " ".join(typed.split())  # letter for letter part of what was typed
    assert commands.read("accept the Java fix: because")["reason"] is None  # only a reject carries a reason


def test_a_name_finds_the_item_it_names_and_an_everyday_name_finds_what_the_app_calls_it():
    update = {"names": ["Update openjdk 17.0.2 to 17.0.3 before the move", "openjdk", "17.0.2"], "id": "java"}
    other = {"names": ["Update python-ecdsa 0.13.2 to 0.13.3 before the move", "python-ecdsa"], "id": "python"}
    check = {
        "names": ["Advisory check: Blank signature accepted (CVE-2022-21449) on acme-sign 1.4.2", "CVE-2022-21449"],
        "id": "check",
    }
    everything = [update, other, check]
    assert [c["id"] for c in commands.match("the java fix", everything)] == [
        "java"
    ]  # Java is what the app calls openjdk
    assert [c["id"] for c in commands.match("the jdk update", everything)] == ["java"]
    assert [c["id"] for c in commands.match("the python fix", everything)] == ["python"]
    assert [c["id"] for c in commands.match("the ecdsa fix", everything)] == ["python"]
    assert [c["id"] for c in commands.match("21449", everything)] == ["check"]  # an id may be typed in part
    assert [c["id"] for c in commands.match("the blank signature check", everything)] == ["check"]
    assert [c["id"] for c in commands.match("the fix", everything)] == [
        "java",
        "python",
        "check",
    ]  # no word narrows it down: all fit
    assert commands.match("the rust fix", everything) == []
    assert (
        commands.kinds_named("the java fix") == ("fix", "dependency")
        and commands.kinds_named("the second suggestion") is not None
    )
    assert (
        commands.kinds_named("21449") is None
        and commands.ordinal("the second suggestion") == 1
        and commands.ordinal("the last one") == -1
    )


def test_reading_any_text_at_all_gives_a_line_of_the_list_or_none_and_never_fails():
    """A seeded fuzz of the reader: what a person types is data."""
    rng = random.Random(20261119)
    pieces = [
        "accept",
        "reject",
        "run",
        "show",
        "open",
        ":",
        "the",
        "java",
        "fix",
        "all",
        "failed",
        "checks",
        "\u0000",
        "\n",
        "'",
        '"',
        "🙂",
        "%s",
        "{}",
        "../",
        "DROP TABLE",
        "<script>",
        "x" * 400,
        "second",
        "retest",
        "on",
        "1.4.3",
        "tab",
        "close",
        "merge",
        "undo",
        "ż",
        "؟",
        " ",
    ]
    for _ in range(600):
        text = " ".join(rng.choice(pieces) for _ in range(rng.randint(0, 12)))
        read = commands.read(text)
        assert read["key"] is None or read["key"] in commands.BY_KEY
        assert len(read["said"]) <= commands.MAX_TEXT
        if read.get("reason"):
            assert read["reason"] in " ".join(text.split())[: commands.MAX_TEXT + 1]


# ---------------------------------------------------------------- answers, at the stages of one walk


@pytest.mark.needs_otto
def test_every_answer_fits_its_shape_words_no_result_and_asking_changed_nothing(assistant_walk):
    asked = options = 0
    for stage, snap in assistant_walk.at.items():
        if stage in ("fix_accepted", "said"):
            continue
        assert snap.asking_changed_nothing, stage  # every table row, every file and the running jobs: as before
        listed = set(made.ASKED.get(stage, ()))
        for (page, sentence), reply in snap.said.items():
            asked += (page, sentence) in listed
            options += (
                page,
                sentence,
            ) not in listed  # (the sentence behind a "Which one?" option, said by the walk too)
            assert problems(reply, models.AssistantReply, f"{stage}: {sentence}") == []
            assert reply["text"] and not any(word in reply["text"].lower() for word in BANNED), reply["text"]
            assert "Otto " not in reply["text"] or reply["kind"] == "help"  # no sentence says what Otto did
            for f in reply.get("facts") or []:
                assert not any(word in f["text"].lower() for word in BANNED), f["text"]
    assert asked == sum(len(v) for v in made.ASKED.values()) >= 60 and options >= 10


@pytest.mark.needs_otto
def test_moving_around_is_answered_with_where_to_go(assistant_walk):
    went = _said(assistant_walk, "ran", "checks", "show me failed checks")
    assert went["kind"] == "went" and went["go"] == {
        "page": "checks",
        "item": None,
        "group": None,
        "result": "Failed",
        "came_from": None,
        "decision": None,
    }
    # the line says where it went and how many checks the page then lists
    listed = sum(
        1
        for g in assistant_walk.lab.checks_view(assistant_walk.plan_id)["groups"]
        for r in g["rows"]
        if (r.get("result") or {}).get("label") == "Failed"
    )
    assert (
        went["text"] == f"Opened Checks, filtered to Failed: {listed} checks."
        and listed >= 2
        and went["entry"] is None
        and went["open"] is None
    )
    assert (
        _said(assistant_walk, "proposed", "checks", "show me failed checks")["text"]
        == "Opened Checks, filtered to Failed: no check reads Failed now."
    )
    assert (
        _said(assistant_walk, "ran", "evidence", "show failed results")["go"]["result"] == "failed"
    )  # Evidence's own filter value
    assert _said(assistant_walk, "proposed", "advisories", "show proposed checks")["go"]["decision"] == "proposed"
    assert _said(assistant_walk, "ran", "checks", "show retests")["go"]["came_from"] == "retest"
    page = _said(assistant_walk, "proposed", "overview", "open evidence")
    assert (page["kind"], page["text"], page["go"]["page"], page["thread"]) == (
        "went",
        "Opened Evidence.",
        "evidence",
        "testing",
    )
    one = _said(assistant_walk, "proposed", "checks", "open the blank signature check")
    assert one["kind"] == "went" and one["go"]["page"] == "advisories" and one["go"]["item"] == "CVE-2022-21449"
    tab = _said(assistant_walk, "proposed", "checks", "close the testing tab")
    assert (
        tab["kind"] == "tab"
        and tab["tab"] == {"thread": "testing", "how": "close"}
        and tab["text"] == "Closed the Testing tab."
    )
    assert (
        _said(assistant_walk, "proposed", "checks", "close the planning tab")["kind"] == "cannot"
    )  # there is no such tab yet


@pytest.mark.needs_otto
def test_a_decision_comes_back_as_the_suggestions_own_card_with_its_confirm_step_and_nothing_is_decided(assistant_walk):
    reply = _said(assistant_walk, "proposed", "checks", "accept the blank signature check")
    assert reply["kind"] == "card" and reply["open"] == {"key": "accept", "reason": None}
    card = reply["entry"]
    on_the_page = next(
        e for e in assistant_walk.at["proposed"].pages["checks"]["on_page"]["entries"] if e["id"] == card["id"]
    )
    assert card == on_the_page  # the very card the panel shows for it: same words, same buttons
    step = next(d for d in card["decisions"] if d["key"] == "accept")["confirm"]
    assert step["names"] == "This is the Accept button on Advisories." and step["lines"][1] == "Runs nothing."
    # the line names the proposal and its page, and says that nothing happens before Confirm
    assert reply["text"] == f"Accept “{card['title']}”, on Advisories. Nothing happens until you press Confirm."
    # typed beside any page, the same card comes back; an id typed in part names it too
    for page, sentence in (("overview", "accept the blank signature check"), ("checks", "accept 21449")):
        assert _said(assistant_walk, "proposed", page, sentence)["entry"]["id"] == card["id"]
    # "the second suggestion" counts down the cards as the panel shows them on that page
    shown = [
        e for e in assistant_walk.at["proposed"].pages["checks"]["on_page"]["entries"] if e["kind"] == "suggestion"
    ]
    second = _said(assistant_walk, "proposed", "checks", "reject the second suggestion: not this quarter")
    assert second["entry"]["id"] == shown[1]["id"] and second["open"] == {"key": "reject", "reason": "not this quarter"}
    assert _said(assistant_walk, "proposed", "checks", "accept the first suggestion")["entry"]["id"] == shown[0]["id"]
    assert _said(assistant_walk, "proposed", "checks", "accept the fifth suggestion")["kind"] == "cannot"
    # at that stage nobody had decided anything: the walk's own decisions came after the sentences
    assert all(e["proposal"]["status"]["key"] == "proposed" for e in shown)


@pytest.mark.needs_otto
def test_an_option_of_which_one_never_asks_again_it_names_exactly_one(assistant_walk):
    """The walk said every option of every "Which one?" too, as a click on it does. Each must settle it: a card, an
    answer or a page, about the one thing its label names; never "Which one?" again and never "I can't do that."."""
    followed = 0
    for stage, snap in assistant_walk.at.items():
        for (page, sentence), reply in getattr(snap, "said", {}).items():
            for option in reply.get("options") or []:
                again = snap.said[(page, option["say"])]
                followed += 1
                assert again["kind"] in ("card", "answer", "went"), (
                    stage,
                    page,
                    sentence,
                    option["say"],
                    again["kind"],
                    again["text"],
                )
                assert (
                    ":" not in option["say"].split(": ", 1)[0]
                    and commands.read(option["say"])["key"] == commands.read(sentence)["key"]
                )
                # it is about the one thing the option names: the title before " (" of its label
                named = option["label"].rsplit(" (", 1)[0]
                told = " ".join(
                    [again["text"]]
                    + [(again.get("entry") or {}).get("title") or ""]
                    + [(again.get("entry") or {}).get("text") or ""]
                    + [f["text"] for f in again.get("facts") or []]
                )
                assert named in told or commands.sayable(named) in told, (stage, option["say"], told[:200])
    assert followed >= 10


def test_a_title_is_said_without_its_colon_and_an_exact_title_wins():
    assert (
        commands.sayable("Advisory check: Blank signature accepted (CVE-2022-21449)")
        == "Advisory check Blank signature accepted (CVE-2022-21449)"
    )
    short = {"names": ["Update openjdk 17.0.2 to 17.0.3"], "id": "fix"}
    long = {"names": ["Update openjdk 17.0.2 to 17.0.3 before the move"], "id": "dependency"}
    # every word of the short title is in the long one: said exactly, it is the short one; said in part, both fit
    assert commands.match("update openjdk 17.0.2 to 17.0.3", [short, long]) == [short]
    assert commands.match("update openjdk 17.0.2 to 17.0.3 before the move", [short, long]) == [long]
    assert commands.match("the openjdk update", [short, long]) == [short, long]
    # the reason still rides after the first colon; a question is read whole, its colon belongs to a name
    said = commands.read(
        "Reject Advisory check Blank signature accepted (CVE-2022-21449) on acme-sign 1.4.2: not this quarter"
    )
    assert (said["key"], said["reason"]) == ("reject", "not this quarter") and "blank signature accepted" in said[
        "rest"
    ]
    asked = commands.read("Why did Advisory check: Blank signature accepted (CVE-2022-21449) fail?")
    assert (asked["key"], asked["question"]) == ("ask", "why_failed") and "cve-2022-21449" in asked["rest"]


@pytest.mark.needs_otto
def test_where_several_things_fit_otto_asks_which_one_and_never_guesses(assistant_walk):
    which = _said(assistant_walk, "proposed", "checks", "accept the check")
    assert (
        which["kind"] == "which" and which["text"] == "Which one?" and which["entry"] is None and which["open"] is None
    )
    # (an option's sentence says the title without its colon: in a typed sentence a colon starts a reason)
    assert len(which["options"]) == 3 and all(
        o["say"].startswith("Accept Advisory check ") and ":" not in o["say"] for o in which["options"]
    )
    assert all(o["label"].startswith("Advisory check: ") for o in which["options"])
    lab = assistant_walk.lab
    fits = _said(assistant_walk, "measured", "fixes", "accept the fix")
    assert fits["kind"] == "which" and {o["say"].split(" ", 1)[1] for o in fits["options"]} == {
        commands.sayable(p["title"])
        for p in lab.otto_proposals(assistant_walk.plan_id)
        if p["kind"] in ("fix", "dependency")
    }
    versions = _said(assistant_walk, "ran", "evidence", "retest")
    assert versions["kind"] == "which" and [o["say"] for o in versions["options"]] == [
        "Retest on acme-sign 1.4.3",
        "Retest on acme-sign 1.4.2",
    ]
    named = _said(assistant_walk, "ran", "evidence", "retest on 1.4.3")
    assert (
        named["kind"] == "card"
        and named["entry"]["step"]["action"]["version"] == "1.4.3"
        and named["open"]["key"] == "step"
    )


@pytest.mark.needs_otto
def test_a_start_comes_back_as_the_page_buttons_own_card_and_an_off_button_gives_the_pages_reason(assistant_walk):
    run_all = _said(assistant_walk, "proposed", "checks", "run all")
    assert run_all["kind"] == "card" and run_all["open"] == {"key": "step", "reason": None}
    step = run_all["entry"]["step"]
    assert (
        step["action"]["type"] == "run_all"
        and step["confirm"]["names"] == "This is the Run all button on Checks."
        and step["can"]
    )
    # also once every test has a result (it is then not a "next step", but the page's button is still there)
    again = _said(assistant_walk, "ran", "checks", "run all")
    assert again["kind"] == "card" and "run again" in " ".join(again["entry"]["step"]["confirm"]["lines"])
    one = _said(assistant_walk, "proposed", "checks", "run the speed test")
    assert (
        one["kind"] == "card"
        and one["text"].startswith("Run: Speed and size, on Checks.")
        and one["entry"]["step"]["action"]["type"] == "run"
    )
    verify = _said(assistant_walk, "proposed", "inventory/import", "verify claims")
    assert verify["entry"]["step"]["action"]["type"] == "verify"
    measure = _said(assistant_walk, "measured", "migration/systems", "measure status")
    assert (
        measure["kind"] == "card" and measure["entry"]["title"] == "Measure again"
    )  # the page button's own name by then
    # a button that is off: the page's own reason, the card with the button off, and no Confirm step
    off = _said(assistant_walk, "ran", "fixes", "connect demo code")
    assert (
        off["kind"] == "cannot"
        and off["open"] is None
        and off["text"].startswith("This change is a proposal. Accept it first")
    )
    assert off["entry"]["step"]["can"] is False and off["entry"]["step"]["confirm"] is None
    demo = _said(assistant_walk, "measured", "migration/dependencies", "measure all")
    assert demo["kind"] == "cannot" and "isolated mode" in demo["text"]
    none = _said(assistant_walk, "proposed", "checks", "retest on 1.4.3")
    assert (
        none["kind"] == "cannot"
        and none["text"] == "Evidence has no Retest new version button to press now."
        and none["can"]
    )


@pytest.mark.needs_otto
def test_what_is_done_on_its_page_only_opens_the_page_and_says_so(assistant_walk):
    for page, sentence, where, starts in (
        ("fixes", "merge it", "fixes", "Merging is done on the page."),
        ("fixes", "approve the pull request", "fixes", "Approving is done on the page."),
    ):
        reply = _said(assistant_walk, "ran", page, sentence)
        assert reply["kind"] == "page_only" and reply["go"]["page"] == where and reply["text"].startswith(starts)
        assert reply["entry"] is None and reply["open"] is None  # never a card: there is nothing to confirm here
    for page, sentence, where, text in (
        (
            "migration/systems",
            "choose the hybrid option",
            "migration/systems",
            "Choosing a migration option is done on the page.",
        ),
        ("overview", "close and sign off", "overview", "Closing and signing off is done on the page."),
        ("evidence", "download evidence", "evidence", "A download is started on the page."),
        ("evidence", "mark it reviewed", "evidence", "Marking a result reviewed is done on the page."),
        ("overview", "turn on live otto", "settings", "Settings are changed in Settings."),
        (
            "inventory/import",
            "i own this system",
            "inventory/import",
            "The “I own this system” tick is yours to make, on Import.",
        ),
    ):
        reply = _said(assistant_walk, "measured", page, sentence)
        assert (reply["kind"], reply["go"]["page"], reply["text"]) == ("page_only", where, text) and reply[
            "entry"
        ] is None
    # Apply: the page's own button says what it still needs (here two changes have one, so the page is where to pick)
    assert _said(assistant_walk, "measured", "fixes", "apply")["text"].startswith(
        "Applying a change is done on the page."
    )


@pytest.mark.needs_otto
def test_where_nothing_fits_it_says_so_and_lists_what_can_be_said_here_from_the_one_list(assistant_walk):
    nothing = _said(assistant_walk, "proposed", "checks", "make me a sandwich")
    assert nothing["kind"] == "cannot" and nothing["text"] == answers.CANNOT == "I can't do that."
    says = [c["say"] for c in nothing["can"]]
    assert (
        "Show failed checks" in says
        and "Run all" in says
        and "What can you do?" in says
        and "Accept the Java fix" in says
    )
    assert "Connect demo code" not in says  # a button of another page is not listed here
    assert set(says) <= {c["say"] for c in commands.COMMANDS}  # from the one list, and nothing else
    help_ = _said(assistant_walk, "proposed", "checks", "what can you do?")
    assert (
        help_["kind"] == "help" and help_["text"] == "On Checks you can tell Otto:" and help_["can"] == nothing["can"]
    )
    # every example of the list is read by the rules as its own line
    for c in commands.COMMANDS:
        assert commands.read(c["say"])["key"] == c["key"], c["say"]
    # with no file in yet: moving around works, and a decision or a start says what is missing
    # (with no file the app shows only the Overview and Import: another page is not "opened", the answer says what is missing)
    assert _said(assistant_walk, "empty", "overview", "open import")["kind"] == "went"
    no_file = _said(assistant_walk, "empty", "overview", "open checks")
    assert (
        no_file["kind"] == "cannot"
        and no_file["go"] is None
        and no_file["text"].startswith("Bring in a scanner file first.")
    )
    assert (
        _said(assistant_walk, "empty", "overview", "open settings")["kind"] == "page_only"
    )  # Settings is not part of an assessment
    assert _said(assistant_walk, "empty", "overview", "run all")["text"].startswith("Bring in a scanner file first.")
    listed = _said(assistant_walk, "empty", "overview", "what can you do?")["can"]
    assert listed and all(
        c["kind"] == "go" for c in listed
    )  # only the lines that move: nothing can be decided or started yet


@pytest.mark.needs_otto
def test_in_a_closed_assessment_the_text_box_only_moves_and_anything_else_gets_the_closed_sentence(assistant_walk):
    closed = assistant_walk.at["closed"]
    for page, sentence in (("migration/dependencies", "accept the python fix"), ("checks", "run all")):
        reply = closed.said[(page, sentence)]
        assert (
            reply["kind"] == "closed"
            and "This assessment is closed." in reply["text"]
            and reply["entry"] is None
            and reply["open"] is None
        )
    assert closed.said[("checks", "show me failed checks")]["kind"] == "went"
    assert (
        closed.said[("overview", "open evidence")]["kind"] == "went"
        and closed.said[("checks", "what can you do?")]["kind"] == "help"
    )
    # a button that is done on its page only: the page opens, and the answer is the closed sentence, never "the button is ready"
    for sentence, starts in (
        ("merge it", "Merging is done on the page. "),
        ("approve it", "Approving is done on the page. "),
        ("apply", "Applying a change is done on the page. "),
    ):
        reply = closed.said[("fixes", sentence)]
        assert reply["kind"] == "page_only" and reply["go"]["page"] == "fixes" and reply["text"].startswith(starts)
        assert (
            "This assessment is closed" in reply["text"]
            and "ready" not in reply["text"]
            and "missing" not in reply["text"]
        )
    # what can be said there: only the lines that move
    assert all(c["kind"] == "go" for c in closed.said[("checks", "what can you do?")]["can"])
    # and nothing typed there is kept, also when the keeping call is made directly
    from app.errors import Conflict

    before = len(assistant_walk.lab.assistant_messages(assistant_walk.plan_id))
    with pytest.raises(Conflict):
        assistant_walk.lab.assistant_say(assistant_walk.plan_id, "checks", None, "open evidence")
    assert len(assistant_walk.lab.assistant_messages(assistant_walk.plan_id)) == before
    box = closed.pages["checks"]["box"]
    assert box["kept"] is False and "not kept" in box["kept_note"]


# ---------------------------------------------------------------- the text box, and what is kept


@pytest.mark.needs_otto
def test_the_text_box_has_its_label_and_up_to_three_examples_fitted_to_the_page(assistant_walk):
    for page in PAGES:
        box = assistant_walk.at["proposed"].pages[page]["box"]
        assert (
            box["label"] == "Ask Otto, or tell it what to do"
            and box["send"] == "Send"
            and box["kept"] is True
            and box["kept_note"] is None
        )
        assert 1 <= len(box["chips"]) <= 3 and box["chips"][-1] == "What can you do?"
        for chip in box["chips"]:
            assert commands.read(chip)["key"] is not None, (page, chip)  # a chip sends its own words, and they are read
    assert assistant_walk.at["proposed"].pages["checks"]["box"]["chips"] == [
        "Show failed checks",
        "Run all",
        "What can you do?",
    ]
    assert assistant_walk.at["empty"].pages["overview"]["box"]["chips"][-1] == "What can you do?"


@pytest.mark.needs_otto
def test_what_is_typed_in_an_open_assessment_is_kept_with_it_and_shows_in_its_thread_and_nothing_else_changes(
    assistant_walk,
):
    said = assistant_walk.at["said"]
    # sending the sentences changed one table, the one that keeps what was said, and no file but the database
    assert said.changed_tables == ["assistant_messages"] and all(
        name.endswith((".sqlite3", ".db")) for name in said.changed_files
    )
    kept = assistant_walk.lab.assistant_messages(assistant_walk.plan_id)
    assert [(m["page"], m["said"], m["kind"], m["thread"]) for m in kept] == [
        ("checks", "show me failed checks", "went", "testing"),
        ("migration/dependencies", "undo the python fix", "card", "fixing"),
        ("checks", "make me a sandwich", "cannot", "testing"),
        ("evidence", "why did the blank signature check fail?", "answer", "testing"),
    ]  # (phase 6c: tests/assistant/test_questions.py)
    assert all(m["by"] == "You" and m["at"].endswith("Z") for m in kept)
    # the answer that was sent back is the one a read gives, and it is what was kept
    for (_page, sentence, reply), row in zip(said.sent, kept, strict=True):
        assert problems(reply, models.AssistantReply, sentence) == [] and (reply["kind"], reply["text"]) == (
            row["kind"],
            row["reply"],
        )
    # in the tabs: each exchange under "This thread so far" of the thread it was filed under, as "You said"
    tabs = {t["key"]: [e for e in t["so_far"] if e["kind"] == "said"] for t in said.pages["checks"]["tabs"]}
    assert [(e["mark"], e["title"]) for e in tabs["testing"]] == [
        ("You said", "show me failed checks"),
        ("You said", "make me a sandwich"),
        ("You said", "why did the blank signature check fail?"),
    ]
    assert [(e["title"], e["text"].split(".")[0]) for e in tabs["fixing"]][0][0] == "undo the python fix" and tabs[
        "planning"
    ] == []
    assert tabs["testing"][0]["links"] == [
        {"label": "Open where it led", "link": {"page": "checks", "item": None, "group": None}}
    ]
    assert all(
        e["decisions"] == [] and e["step"] is None for line in tabs.values() for e in line
    )  # a record: nothing to press
    assert problems(said.pages["checks"], models.AssistantView, "the panel with what was said") == []
    # the undo that was asked for was not done: the suggestion still reads as it did (only Confirm in the browser sends it)
    assert said.sent[1][2]["kind"] == "card" and said.sent[1][2]["open"]["key"] == "undo"
    fix = next(
        p
        for p in assistant_walk.lab.otto_proposals(assistant_walk.plan_id)
        if p["id"] == assistant_walk.ids["dependency"]
    )
    assert fix["state"] == "accepted" and len(fix["decisions"]) == 1


@pytest.mark.needs_otto
def test_raw_sql_cannot_change_or_delete_what_was_said(assistant_walk):
    """What was said is only ever added: the database itself refuses a change or a removal."""
    from sqlalchemy import text

    with assistant_walk.lab.db() as db:
        before = db.execute(text("SELECT COUNT(*) FROM assistant_messages")).scalar()
        assert before == 4
        for statement in ("UPDATE assistant_messages SET said = 'x'", "DELETE FROM assistant_messages"):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(statement))
                db.commit()
            db.rollback()
        assert db.execute(text("SELECT COUNT(*) FROM assistant_messages")).scalar() == before


def test_the_two_routes_answer_alike_one_keeps_the_exchange_and_a_closed_assessment_keeps_nothing(client):
    """Through the routes, as the browser sends them (no pack is needed for moving around)."""
    imported = client.post("/api/import/demo")
    assert imported.status_code == 200
    aid = imported.json()["assessment_id"]
    plan_id = client.post(f"/api/import/{imported.json()['id']}/plan").json()["id"]
    read = client.get(f"/api/assessments/{aid}/assistant/answer", params={"text": "open evidence", "page": "checks"})
    assert read.status_code == 200 and read.json()["kind"] == "went" and read.json()["go"]["page"] == "evidence"
    assert problems(read.json(), models.AssistantReply, "the read") == []
    sent = client.post(f"/api/plans/{plan_id}/assistant/messages", json={"text": "open evidence", "page": "checks"})
    assert sent.status_code == 200 and sent.json() == read.json()
    # what is not a sentence, or names no page of an assessment, is refused, and nothing of it is kept
    assert client.post(f"/api/plans/{plan_id}/assistant/messages", json={"text": "", "page": "checks"}).status_code in (
        400,
        422,
    )
    assert client.post(
        f"/api/plans/{plan_id}/assistant/messages", json={"text": "x" * 501, "page": "checks"}
    ).status_code in (400, 422)
    assert client.post(
        f"/api/plans/{plan_id}/assistant/messages", json={"text": "open evidence", "page": "nowhere"}
    ).status_code in (400, 422)
    assert client.get(
        f"/api/assessments/{aid}/assistant/answer", params={"text": "open evidence", "page": "nowhere"}
    ).status_code in (400, 422)
    assert client.get(f"/api/assessments/{aid}/assistant/answer", params={"page": "checks"}).status_code in (400, 422)
    # closed: the write is refused with the closed sentence, and the read still takes you places
    assert client.post(f"/api/assessments/{aid}", json={"close": True, "signed_off_by": "A tester"}).status_code == 200
    closed = client.post(f"/api/plans/{plan_id}/assistant/messages", json={"text": "open evidence", "page": "checks"})
    assert closed.status_code == 409 and "closed" in closed.json()["error"]["message"]
    still = client.get(f"/api/assessments/{aid}/assistant/answer", params={"text": "open evidence", "page": "checks"})
    assert still.status_code == 200 and still.json()["kind"] == "went"
    assert (
        client.get(f"/api/assessments/{aid}/assistant/answer", params={"text": "run all", "page": "checks"}).json()[
            "kind"
        ]
        == "closed"
    )


def test_the_page_labels_the_answers_use_are_the_pages_own():
    assert PAGE_LABELS["checks"] == "Checks" and set(commands.CHIPS) == set(PAGES)


# ---------------------------------------------------------------- after the separate review of 6b (19 November 2026)


@pytest.mark.parametrize(
    "sentence, key",
    [
        ("Otto: run all", "run_all"),
        ("otto, show me failed checks", "filter"),
        ("hey otto: open evidence", "open_page"),
        ("open the plan", "open_page"),
        ("open the test plan", "open_page"),
        ("open the file", "open_page"),
        ("open the checks page please", "open_page"),
        ("run the checks", "run_all"),
        ("run all the checks", "run_all"),
        ("open evidence, please", "open_page"),
        # read as nothing the list knows, not as a button of another page
        ("apply the filter", None),
        ("sign off the fix", None),
        ("export the plan", None),
        ("tick Dana as reviewer", None),
        # still what they were
        ("apply", "apply"),
        ("apply it", "apply"),
        ("apply the change to localhost:8443", "apply"),
        ("sign off", "sign_off"),
        ("close and sign off", "sign_off"),
        ("download evidence", "download"),
        ("export the report", "download"),
        ("tick the box", "own_tick"),
        ("i own this system", "own_tick"),
        ("confirm the address", "own_tick"),
    ],
)
def test_sentences_the_review_found_read_into_something_else(sentence, key):
    assert commands.read(sentence)["key"] == key, sentence


def test_open_and_added_are_not_read_as_a_decision_filter_and_the_decision_words_are_the_controls_own():
    # "Open" is Checks' own count word and "added by you" the plan's: neither opens Advisories filtered
    assert (
        commands.read("show open checks")["key"] == "open_item"
        and commands.read("show added tests")["key"] == "open_item"
    )
    accepted = commands.read("show accepted checks")
    assert (accepted["key"], accepted["page"], accepted["value"], accepted["label"]) == (
        "filter",
        "advisories",
        "accepted",
        "Added",
    )
    assert commands.read("otto: reject the java fix: not this quarter")["reason"] == "not this quarter"


def test_the_whole_title_is_found_before_a_word_of_it_is_read_as_a_kind():
    plan = {"names": ["Fix acme-sign 1.4.2 before its signatures move to post-quantum"], "kind": "plan"}
    fix = {"names": ["Reject signatures whose r or s is out of range (acme-sign)"], "kind": "fix"}
    assert commands.exact("fix acme-sign 1.4.2 before its signatures move to post-quantum", [plan, fix]) == [plan]
    assert commands.exact("fix acme-sign", [plan, fix]) == [] and commands.exact("", [plan, fix]) == []
    assert commands.kinds_named("fix acme-sign 1.4.2 before its signatures move to post-quantum") == (
        "fix",
        "dependency",
    )  # why the look comes first
    assert commands.which_text(3, 3) == "Which one?"
    assert (
        commands.which_text(8, 12)
        == "Which one? The first 8 of 12 that fit are listed. Say more of its name to narrow it down."
    )


@pytest.mark.needs_otto
def test_a_title_that_holds_a_kind_word_is_still_that_one_thing(assistant_walk):
    from assistant_walk import PLAN_CHANGE

    plan = next(p for p in assistant_walk.lab.otto_proposals(assistant_walk.plan_id) if p["kind"] == "plan")
    assert plan["title"] == PLAN_CHANGE
    card = _said(assistant_walk, "measured", "migration/systems", "accept " + PLAN_CHANGE)
    assert (
        card["kind"] == "card"
        and card["entry"]["title"] == PLAN_CHANGE
        and card["open"]["key"] == "accept"
        and card["thread"] == "planning"
    )
    went = _said(assistant_walk, "measured", "overview", "open " + PLAN_CHANGE)
    assert (
        went["kind"] == "went"
        and went["go"]["page"] == "migration/systems"
        and went["text"] == f"Opened “{PLAN_CHANGE}” on Systems."
    )
    asked = _said(assistant_walk, "measured", "overview", "where did " + PLAN_CHANGE + " come from?")
    assert asked["kind"] == "answer" and PLAN_CHANGE in asked["facts"][0]["text"] and asked["thread"] == "planning"


@pytest.mark.needs_otto
def test_a_button_offered_for_nothing_that_fits_says_so_and_a_reason_that_is_too_long_is_refused_before_any_card(
    assistant_walk,
):
    from app.otto import proposals
    from assistant_walk import LONG_REJECT

    nothing = _said(
        assistant_walk, "proposed", "checks", "undo the check"
    )  # nothing was accepted yet: there is nothing to undo
    assert nothing["kind"] == "cannot" and nothing["options"] == [] and nothing["entry"] is None
    assert (
        nothing["text"]
        == "Undo is not offered for any of the 3 suggestions that fit now. Each card says where it stands."
    )
    long = _said(assistant_walk, "proposed", "checks", LONG_REJECT)
    assert long["kind"] == "cannot" and long["entry"] is None and long["open"] is None
    assert (
        long["text"]
        == "A reason is one short line, 300 characters at most. Yours has 301. Say it again with a shorter reason."
    )
    assert answers.MAX_REASON == proposals.MAX_REASON == 300


def test_approve_counts_the_approvals_that_are_missing_from_the_rows_own_field():
    """A reviewer's row carries when it was approved, or nothing. (The first version read a field the rows do not have,
    and so counted every reviewer as missing, also after the merge.)"""
    line = commands.BY_KEY["approve"]

    def told(rows) -> str:
        fixes = [{"id": "fix-1", "title": "A fix", "approvers": {"rows": rows}}]
        facts = type("Facts", (), {"fixes": lambda self: {"fixes": fixes}})()
        return answers._page_only(
            facts,
            "approve",
            line,
            {"rest": "approve it"},
            None,
            lambda kind, text, **more: {"kind": kind, "text": text, **more},
        )["text"]

    none, one, both = (
        [{"name": "A", "approved_at": None}, {"name": "B", "approved_at": None}],
        [{"name": "A", "approved_at": "2026-11-19T07:00:00Z"}, {"name": "B", "approved_at": None}],
        [{"name": "A", "approved_at": "2026-11-19T07:00:00Z"}, {"name": "B", "approved_at": "2026-11-19T07:01:00Z"}],
    )
    assert told(none) == "Approving is done on the page. 2 approvals are still missing."
    assert told(one) == "Approving is done on the page. One approval is still missing."
    assert told(both) == "Approving is done on the page. Nothing on Fixes is waiting for that now."


@pytest.mark.needs_otto
def test_what_a_person_typed_does_not_change_a_tabs_mark(assistant_walk):
    """A tab that was closed comes back, with a dot, when its thread has something new. A person's own sentence is not
    that: "close the Fixing tab" is filed under Fixing, and must not bring the tab back."""
    before = {t["key"]: t["mark"] for t in assistant_walk.at["accepted"].pages["checks"]["tabs"]}
    after = {t["key"]: t["mark"] for t in assistant_walk.at["said"].pages["checks"]["tabs"]}
    assert before == after and before
    said = [e for t in assistant_walk.at["said"].pages["checks"]["tabs"] for e in t["so_far"] if e["kind"] == "said"]
    assert len(said) >= 3  # the sentences are listed in their threads all the same
