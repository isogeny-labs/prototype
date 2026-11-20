"""Phase 6a: what the Otto panel shows beside each page, read at each stage of one walk.

The panel makes one read: this assessment, this page, this open item. The answer holds the open tabs, what fits the
page, what waits elsewhere and the status line. It is worked out from the records the pages already show, so the same
proposal reads the same on its page and in the panel, and "On this page" plus "Elsewhere" is exactly what the
Overview counts as "Waiting for you". The walk is tests/assistant/assistant_walk.py."""
import pytest

from app.assistant import words
from app.assistant.threads import FITS, KIND_THREAD, PAGE_THREAD, PAGES, THREADS
from app.otto import harness, proposals
from app.web import models
from tests.assistant import assistant_walk as made
from tests.view_helpers import problems

pytestmark = [pytest.mark.needs_otto]
BANNED = ("secure", "score", "severity", "critical", "time to hack", "time-to-hack")
OPEN_STAGES = ("proposed", "decided", "ran", "measured", "accepted")


def _suggestions(view: dict) -> list[dict]:
    return [e for e in view["on_page"]["entries"] if e["kind"] == "suggestion"]


def _steps(view: dict, what: str | None = None) -> list[dict]:
    return [e for e in view["on_page"]["entries"] if e["kind"] == "next" and (what is None or e["what"] == what)]


def _undecided(view: dict) -> list[dict]:
    return [e for e in _suggestions(view) if e["proposal"]["status"]["key"] == "proposed"]


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


# ---------------------------------------------------------------- the shape, and the standing sentences

def test_every_read_fits_its_shape_at_every_stage(assistant_walk):
    for stage, snap in assistant_walk.at.items():
        for page, view in snap.pages.items():
            assert problems(view, models.AssistantView, f"assistant {stage} {page}") == []
            assert view["page"] == page and view["title"] == "Otto" and view["thread"] == PAGE_THREAD[page]


def test_with_no_file_the_panel_says_how_to_start_and_shows_no_tab(assistant_walk):
    for page, view in assistant_walk.at["empty"].pages.items():
        assert view["tabs"] == [] and view["on_page"]["entries"] == [] and view["waiting"] == 0
        assert view["on_page"]["empty"] == "Bring in a scanner file to start. Nothing is suggested yet."
        link = view["on_page"]["empty_link"]
        assert (link is None) == (page == "inventory/import")
        if link:
            assert link == {"label": "Open Import", "link": {"page": "inventory/import", "item": None, "group": None}}


def test_the_status_line_repeats_settings_and_live_otto_is_off_without_a_key(assistant_walk):
    for snap in assistant_walk.at.values():
        for view in snap.pages.values():
            assert view["status"]["text"] == "Live Otto is off." and view["status"]["live"] is False
            assert view["status"]["link"]["link"]["page"] == "settings" and view["status"]["link"]["label"] == "Settings"


# ---------------------------------------------------------------- what fits each page

def test_a_proposed_check_fits_advisories_and_checks_and_no_other_page(assistant_walk):
    snap = assistant_walk.at["proposed"]
    for page, view in snap.pages.items():
        found = _suggestions(view)
        if page in ("advisories", "checks"):
            assert len(found) == 3 and {e["what"] for e in found} == {"suggestion:check"}
            for e in found:
                assert e["mark"] == "From Otto" and e["thread"] == "testing" and e["badge"] == {"label": "Proposed", "tone": "warn"}
                assert e["where"] == {"label": "On Advisories", "link": e["proposal"]["link"]} and e["proposal"]["link"]["page"] == "advisories"
                assert [d["key"] for d in e["decisions"]] == ["accept", "reject"] and all(d["can"] for d in e["decisions"])
        else:
            assert found == [], page


def test_each_kind_of_suggestion_shows_on_the_pages_it_fits(assistant_walk):
    snap = assistant_walk.at["measured"]
    ids = assistant_walk.ids
    by_page = {page: {e["id"] for e in _suggestions(view)} for page, view in snap.pages.items()}
    assert ids["fix"] in by_page["fixes"] and ids["plan"] in by_page["migration/systems"] and ids["plan"] in by_page["migration/roadmap"]
    assert ids["dependency"] in by_page["migration/dependencies"]
    for page, view in snap.pages.items():
        for e in _suggestions(view):
            assert e["proposal"]["kind"] in FITS[page], f"{e['what']} does not fit {page}"
            assert e["thread"] == KIND_THREAD[e["proposal"]["kind"]]
    for page in ("overview", "inventory/import", "inventory/verify", "evidence"):
        assert by_page[page] == set()


def test_a_suggestion_reads_in_the_panel_as_on_its_page(assistant_walk):
    lab, pid = assistant_walk.lab, assistant_walk.plan_id
    on_pages = {p["id"]: p for p in lab.otto_proposals_view(pid)["proposals"]}
    seen = 0
    for view in assistant_walk.at["closed"].pages.values():
        for e in _suggestions(view) + [x for tab in view["tabs"] for x in tab["so_far"] if x["kind"] == "suggestion"]:
            page_card = on_pages[e["id"]]
            for key in ("title", "why", "why_label", "lines", "status", "decided_line", "buttons", "note", "label", "link", "kind_label"):
                assert e["proposal"][key] == page_card[key], key
            assert e["title"] == page_card["title"] and e["badge"]["label"] == page_card["status"]["word"]
            seen += 1
    assert seen


def test_a_decided_suggestion_stays_on_its_page_while_it_can_still_be_decided_again(assistant_walk):
    ids = assistant_walk.ids
    decided = {e["id"]: e for e in _suggestions(assistant_walk.at["decided"].pages["checks"])}
    assert decided[ids["first"]]["badge"]["label"] == "Added" and [d["key"] for d in decided[ids["first"]]["decisions"]] == ["undo"]
    assert decided[ids["second"]]["badge"]["label"] == f"Not added ({made.REASON})"
    assert [d["key"] for d in decided[ids["second"]]["decisions"]] == ["reconsider"]
    # ... and once the check has run, its accept stands: it is told in the thread so far, and no longer under "On this page"
    after = {e["id"] for e in _suggestions(assistant_walk.at["ran"].pages["checks"])}
    assert ids["first"] not in after and ids["second"] in after
    testing = next(t for t in assistant_walk.at["ran"].pages["checks"]["tabs"] if t["key"] == "testing")
    told = next(e for e in testing["so_far"] if e["id"] == ids["first"])
    assert told["badge"]["label"] == "Added" and told["decisions"][0]["can"] is False
    assert told["decisions"][0]["blocked_reason"] == "This check has run, so it stays in the test plan."


# ---------------------------------------------------------------- elsewhere, and the count the Overview shows

def test_on_this_page_plus_elsewhere_is_what_the_overview_counts_as_waiting(assistant_walk):
    for stage in OPEN_STAGES:
        snap = assistant_walk.at[stage]
        for page, view in snap.pages.items():
            elsewhere = view["elsewhere"]
            assert sum(line["count"] for line in elsewhere["lines"]) == elsewhere["count"]
            assert len(_undecided(view)) + elsewhere["count"] == view["waiting"] == snap.waiting, f"{stage} {page}"
            assert elsewhere["title"] == f"Elsewhere: {elsewhere['count']} more"
    assert [assistant_walk.at[s].waiting for s in OPEN_STAGES] == [3, 1, 2, 4, 0]


def test_elsewhere_has_one_line_for_each_page_saying_what_it_is_and_where_it_lives(assistant_walk):
    view = assistant_walk.at["measured"].pages["evidence"]
    lines = view["elsewhere"]["lines"]
    assert [(line["link"]["page"], line["thread"], line["count"]) for line in lines] == [
        ("advisories", "testing", 1), ("fixes", "fixing", 1), ("migration/systems", "planning", 1), ("migration/dependencies", "fixing", 1)]
    assert lines[0]["text"].startswith("Advisories: 1 proposed check, Advisory check: ")
    assert lines[1]["text"].startswith("Fixes: 1 proposed fix, ")
    assert lines[2]["text"] == "Systems: 1 proposed plan change, Fix acme-sign 1.4.2 before its signatures move to post-quantum"
    assert lines[3]["text"] == "Dependencies: 1 proposed library update, Update python-ecdsa 0.13.2 to 0.13.3 before the move"
    # a line with one suggestion opens it; the page that shows a suggestion does not list it again
    assert lines[1]["link"]["item"] and lines[3]["link"]["item"]
    assert "fixes" not in [line["link"]["page"] for line in assistant_walk.at["measured"].pages["fixes"]["elsewhere"]["lines"]]
    several = assistant_walk.at["proposed"].pages["evidence"]["elsewhere"]["lines"]
    assert len(several) == 1 and several[0]["text"].endswith(" and 2 more") and several[0]["link"]["item"] is None


def test_with_nothing_waiting_anywhere_the_panel_says_the_overviews_sentence(assistant_walk):
    for view in assistant_walk.at["accepted"].pages.values():
        assert view["elsewhere"]["empty"] == "Nothing from Otto is waiting for a decision." == assistant_walk.at["accepted"].overview["waiting"]["line"]
        assert view["elsewhere"]["lines"] == [] and view["waiting"] == 0
    assert all(v["elsewhere"]["empty"] is None for v in assistant_walk.at["measured"].pages.values())
    quiet = assistant_walk.at["accepted"].pages["inventory/verify"]
    assert quiet["on_page"]["entries"] == [] or quiet["on_page"]["empty"] is None
    assert assistant_walk.at["decided"].pages["evidence"]["on_page"]["empty"] == "Nothing is suggested on this page."


# ---------------------------------------------------------------- the tabs

def test_never_more_than_three_tabs_and_each_opens_when_its_thread_has_something(assistant_walk):
    opened = {stage: [t["key"] for t in assistant_walk.at[stage].pages["overview"]["tabs"]] for stage in assistant_walk.at if stage != "fix_accepted"}
    assert opened == {"empty": [], "proposed": ["testing"], "decided": ["testing"], "ran": ["testing", "fixing"],
                      "measured": ["testing", "fixing", "planning"], "accepted": ["testing", "fixing", "planning"],
                      "said": ["testing", "fixing", "planning"], "closed": ["testing", "fixing", "planning"]}
    for snap in assistant_walk.at.values():
        tabs = [[t["key"] for t in view["tabs"]] for view in snap.pages.values()]
        assert all(t == tabs[0] for t in tabs)                      # the same tabs beside every page
        assert len(tabs[0]) <= 3 and set(tabs[0]) <= set(THREADS)
        for view in snap.pages.values():
            for tab in view["tabs"]:
                assert {e["thread"] for e in tab["so_far"]} <= {tab["key"]}          # an entry never lands in another thread's tab
            for e in view["on_page"]["entries"]:
                assert e["thread"] in THREADS + (None,)


def test_a_tab_counts_its_undecided_suggestions(assistant_walk):
    waiting = {stage: {t["key"]: t["waiting"] for t in assistant_walk.at[stage].pages["checks"]["tabs"]} for stage in OPEN_STAGES}
    assert waiting["proposed"] == {"testing": 3} and waiting["decided"] == {"testing": 1}
    assert waiting["ran"] == {"testing": 1, "fixing": 1}
    assert waiting["measured"] == {"testing": 1, "fixing": 2, "planning": 1}
    assert waiting["accepted"] == {"testing": 0, "fixing": 0, "planning": 0}
    for stage in OPEN_STAGES:
        assert sum(waiting[stage].values()) == assistant_walk.at[stage].waiting


def test_a_thread_so_far_is_in_the_order_things_happened_and_the_same_on_every_read(assistant_walk):
    lab = assistant_walk.lab
    for stage, snap in assistant_walk.at.items():
        for view in snap.pages.values():
            for tab in view["tabs"]:
                timed = [e["at"] for e in tab["so_far"] if e["at"]]
                assert timed == sorted(timed), f"{stage} {tab['key']}"
                assert tab["so_far_title"] == "This thread so far"
    again = lab.assistant_view(assistant_walk.assessment_id, "checks")
    once_more = lab.assistant_view(assistant_walk.assessment_id, "checks")
    assert again == once_more == assistant_walk.at["closed"].pages["checks"]
    testing = next(t for t in again["tabs"] if t["key"] == "testing")
    kinds = [e["kind"] for e in testing["so_far"]]
    assert kinds.count("suggestion") == 3 and kinds.count("result") == 6          # three decided checks, the six tests' results
    results = {e["title"]: e for e in testing["so_far"] if e["kind"] == "result"}
    assert results["Old TLS versions"]["badge"] == {"label": "Failed", "tone": "fail"}
    assert all(e["links"][0]["label"] == "See the evidence" and e["links"][0]["link"]["page"] == "evidence" for e in results.values())


def test_a_tabs_mark_changes_when_its_thread_gets_a_new_entry_and_only_then(assistant_walk):
    def marks(stage):
        return {t["key"]: t["mark"] for t in assistant_walk.at[stage].pages["overview"]["tabs"]}
    for stage, snap in assistant_walk.at.items():       # one mark for a tab, whatever page is open
        for view in snap.pages.values():
            if stage != "fix_accepted":
                assert {t["key"]: t["mark"] for t in view["tabs"]} == {t["key"]: t["mark"] for t in snap.pages["overview"]["tabs"]}
    assert marks("proposed")["testing"] != marks("decided")["testing"] != marks("ran")["testing"]      # decisions, then results
    assert marks("ran")["testing"] == marks("measured")["testing"]                                    # nothing new in Testing
    assert marks("ran")["fixing"] != marks("measured")["fixing"] != marks("accepted")["fixing"]
    assert marks("measured")["planning"] != marks("accepted")["planning"]
    assert marks("said") == marks("closed")                                                           # closing adds no entry


def test_a_next_step_alone_opens_no_tab(tmp_path):
    from conftest import demo_plan, make_lab
    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        a = lab.assessment_for(plan_id=plan.id).id
        for page in PAGES:
            view = lab.assistant_view(a, page)
            assert view["tabs"] == [] and view["waiting"] == 0 and _suggestions(view) == []
        assert [e["title"] for e in _steps(lab.assistant_view(a, "checks"))] == ["Run all"]
        assert [e["title"] for e in _steps(lab.assistant_view(a, "inventory/import"))] == ["Verify claims"]
        assert [e["title"] for e in _steps(lab.assistant_view(a, "migration/systems"))] == ["Measure status"]
    finally:
        lab.stop()


# ---------------------------------------------------------------- the Confirm step

def test_the_confirm_step_of_a_suggestion_says_what_happens_what_does_not_and_which_button_it_presses(assistant_walk):
    check = _undecided(assistant_walk.at["proposed"].pages["checks"])[0]
    accept, reject = check["decisions"]
    assert accept["confirm"]["lines"] == ["Adds this check to the test plan, as “+ Add test” would.", "Runs nothing.",
                                          "You can undo it until the check has run."]
    assert accept["confirm"]["names"] == "This is the Accept button on Advisories." and accept["confirm"]["reason"] is None
    assert (accept["confirm"]["confirm"], accept["confirm"]["cancel"]) == ("Confirm", "Cancel")
    assert reject["confirm"]["reason"] == {"label": "Reason (optional, one short line)", "max": proposals.MAX_REASON}
    assert reject["confirm"]["names"] == "This is the Reject button on Advisories." and "Runs nothing." in reject["confirm"]["lines"]
    seen = set()
    for stage in OPEN_STAGES:
        for view in assistant_walk.at[stage].pages.values():
            for e in _suggestions(view):
                for d in e["decisions"]:
                    assert d["can"] and d["confirm"] is not None
                    said = " ".join(d["confirm"]["lines"])
                    assert "nothing" in said.lower() and d["confirm"]["names"].startswith(f"This is the {d['label']} button on ")
                    seen.add((e["proposal"]["kind"], d["key"]))
    assert {("check", "accept"), ("check", "reject"), ("check", "undo"), ("check", "reconsider"), ("fix", "accept"), ("plan", "accept"),
            ("dependency", "accept"), ("plan", "undo"), ("dependency", "undo")} <= seen


# ---------------------------------------------------------------- next steps: a button of the page, by its own name

def test_next_steps_are_the_pages_own_buttons_and_can_be_pressed_when_the_page_can(assistant_walk):
    lab, at = assistant_walk.lab, assistant_walk.at
    run_all = _steps(at["proposed"].pages["checks"], "next:run_all")
    assert len(run_all) == 1 and run_all[0]["title"] == "Run all" and run_all[0]["step"]["can"] and run_all[0]["mark"] == "Next step"
    assert run_all[0]["step"]["action"]["type"] == "run_all" and run_all[0]["step"]["action"]["plan_id"] == assistant_walk.plan_id
    assert run_all[0]["step"]["confirm"]["names"] == "This is the Run all button on Checks."
    assert run_all[0]["step"]["confirm"]["lines"][0] == "Runs every test in the plan (5), on this computer."
    # an accepted check that has not run gets a Run card of its own
    run = _steps(at["decided"].pages["checks"], "next:run")
    assert len(run) == 1 and run[0]["title"] == "Run" and "Advisory check" in run[0]["text"] and run[0]["step"]["action"]["type"] == "run"
    assert isinstance(run[0]["step"]["action"]["item_id"], int)
    # once every test has a result, running is not the next step any more
    assert _steps(at["ran"].pages["checks"]) == []
    # Evidence: Retest new version, one card for each version the page's menu offers
    retests = _steps(at["ran"].pages["evidence"], "next:retest")
    offered = lab.lab_view(assistant_walk.plan_id)["retest"]["versions"]
    assert [(e["step"]["action"]["version"], e["title"]) for e in retests] == [(v["version"], "Retest new version") for v in offered]
    assert all(e["step"]["confirm"]["names"] == "This is the Retest new version button on Evidence." for e in retests)
    # Migration: Measure status until every system has one
    assert [e["title"] for e in _steps(at["ran"].pages["migration/systems"])] == ["Measure status"]
    assert _steps(at["measured"].pages["migration/systems"]) == [] == _steps(at["measured"].pages["migration/roadmap"])
    # the Overview: its own next step, which only opens a page and so needs no Confirm
    for stage in OPEN_STAGES:
        steps = _steps(at[stage].pages["overview"])
        want = at[stage].overview["next_step"]
        assert [(e["title"], e["text"], e["step"]["action"]["link"]["page"]) for e in steps] == [(want["label"], want["text"], want["page"])]
        assert steps[0]["step"]["needs"] == "nothing" and steps[0]["step"]["confirm"] is None and steps[0]["what"] == "next:open"


def test_the_confirm_step_of_measure_status_says_what_the_two_locked_measurements_do(assistant_walk):
    """Confirm lists exactly what will happen. The measurement is more than one handshake: its own method says so."""
    from app.engine import research
    [step] = _steps(assistant_walk.at["ran"].pages["migration/systems"], "next:measure_status")
    lines = " ".join(step["step"]["confirm"]["lines"])
    assert "one handshake to each server" not in lines
    # the server measurement, in its method's own words (hellos, full handshakes, the timing rounds of the cost table)
    assert "three first messages (TLS hellos)" in lines and "Handshakes only; no data is sent." in lines
    assert "Handshakes only; no data is sent." in research.PQ_METHOD and "Send three first messages (TLS 1.3 hellos)" in research.PQ_METHOD
    assert "10 classical and 10 hybrid handshakes taken in turn" in lines
    spec = research.RuleEngine()._pq_status([{"location_kind": "server", "location": "localhost:1", "kind": "tls_version"}], "localhost:1")
    assert "10 classical and 10 hybrid handshakes taken in turn" in spec["method"] and spec["inputs"]["timing_rounds"] == 10
    # the signing program: it is run (it signs a test message and its bench command is timed), not only looked at
    assert "signs one test message" in lines and "bench command is timed" in lines and "a look at each signing program" not in lines
    assert "localhost or at an address you confirmed" in lines and step["step"]["confirm"]["lines"][-1] == "It changes nothing on any system."


def test_a_step_that_is_off_while_jobs_run_gives_the_servers_own_reason(assistant_walk):
    """Rule: a button that is off says its page's own reason. While tests or a proof run, that is the sentence the
    server refuses the click with."""
    from app.assistant.engine import _Facts
    from app.lab import testlab
    assert (words.BUSY_TESTS, words.BUSY_PROOF) == (testlab.BUSY["tests"], testlab.BUSY["proof"])
    lab, plan_id = assistant_walk.lab, assistant_walk.plan_id

    def reason_when(said):
        facts = _Facts(lab, {"plan_id": plan_id, "import_id": None}, False)
        facts._seen["lab"] = {"retest": {"blocked_reason": said}}       # what Evidence would say beside Retest new version
        return facts.busy_reason()
    assert reason_when(testlab.BUSY["proof"]) == "A proof is running in Fixes. Wait until it has finished."
    assert reason_when(testlab.BUSY["tests"]) == "Tests are still running. Wait until they have finished."
    # Evidence gives another reason for its own button (no program to retest): for a test, tests are what is running
    assert reason_when("A retest needs one of our demo signing components, and this file doesn't name one.") == testlab.BUSY["tests"]
    assert reason_when(None) == testlab.BUSY["tests"] and plan_id


def test_a_tabs_mark_follows_the_word_a_fix_carries_not_only_its_status_key(assistant_walk, monkeypatch):
    """A server change keeps one status key ("text_only") through Try passed, Waiting for approval and Applied: only
    its word tells them apart, and each is something new in the Fixing tab."""
    lab = assistant_walk.lab
    engine = lab.copilot
    real = type(engine)._fix_steps

    def with_word(word):
        def steps(self, facts):
            out = real(self, facts)
            return [{**e, "badge": {**e["badge"], "label": word}} for e in out]
        monkeypatch.setattr(type(engine), "_fix_steps", steps)
        view = lab.assistant_view(assistant_walk.assessment_id, "fixes", None)
        return next(t["mark"] for t in view["tabs"] if t["key"] == "fixing"), [e["id"] for t in view["tabs"] if t["key"] == "fixing" for e in t["so_far"]]
    tried, ids_tried = with_word("Try passed")
    waiting, ids_waiting = with_word("Waiting for approval")
    assert ids_tried == ids_waiting and tried != waiting          # the same entries, another word: the mark moves
    assert with_word("Try passed")[0] == tried                      # and the same word gives the same mark


def _facts(assistant_walk, **views):
    """The engine's facts with the views a page would give, for a state the walk does not stop in."""
    from app.assistant.engine import _Facts
    facts = _Facts(assistant_walk.lab, {"plan_id": assistant_walk.plan_id, "import_id": None}, False)
    facts._seen.update(views)
    return facts


def test_a_run_card_stays_while_its_test_runs_and_says_so(assistant_walk):
    """The card does not vanish at the click: it reads as running, and its button is off until the test has finished."""
    engine = assistant_walk.lab.copilot
    test = {"id": 7, "title": "Advisory check: Blank signature accepted (CVE-2022-21449)", "kind": "advisory_cases", "result": None,
            "status": "not_run", "status_text": None, "can_run": True}
    done = {"id": 3, "title": "Official test vectors", "kind": "vectors", "result": {"label": "Passed"}, "status": "done", "can_run": True}
    [before] = engine._next_checks(_facts(assistant_walk, plan={"tests": [done, test], "can_run_all": True}, lab={}), "checks", None)
    assert before["id"] == "next:run:7" and before["text"].endswith("has not run yet.") and before["step"]["can"] and not before["step"]["running"]
    going = {**test, "status": "running", "status_text": "Running", "can_run": False}
    during = [e for e in engine._next_checks(_facts(assistant_walk, plan={"tests": [done, going], "can_run_all": False, "running": True}, lab={}), "checks", None)
              if e["what"] == "next:run"]
    assert [e["id"] for e in during] == ["next:run:7"]                       # the same card, still there
    step = during[0]["step"]
    assert during[0]["text"].endswith("is running.") and step["running"] and step["progress"] == "Running"
    assert step["can"] is False and step["confirm"] is None and step["blocked_reason"] == words.BUSY_TESTS
    # once it has a result the card is gone: the result is in the Testing tab
    after = {**test, "status": "done", "result": {"label": "Failed"}}
    assert [e for e in engine._next_checks(_facts(assistant_walk, plan={"tests": [done, after], "can_run_all": True}, lab={}), "checks", None)
            if e["what"] == "next:run"] == []


def test_connect_demo_code_names_the_most_a_live_click_can_cost(assistant_walk):
    """With Live Otto on and no change written yet, the click asks Claude. The Confirm step says the most it can spend."""
    engine, lab = assistant_walk.lab.copilot, assistant_walk.lab
    assert lab.otto_limit_words() == "2.00"                                  # the limit Settings shows until it is changed
    asks = "Live Otto is on. When you connect the code, Claude is asked to write a change for CVE-2022-21449 in acme-sign's code."
    fix = {"id": "fix-x", "title": "acme-sign accepts out-of-range signatures", "proposal": {"lines": [asks, "Why it is proposed: a test failed."]}}
    button = {"action": "connect", "label": "Connect demo code", "enabled": True}
    where = {"label": "On Fixes", "link": {"page": "fixes", "item": "fix-x", "group": None}}
    live = engine._fix_step(_facts(assistant_walk), fix, button, None, where, True)["step"]["confirm"]["lines"]
    assert asks in live and live[-1] == "The most this click can spend on Claude: 2.00 US dollars, the spending limit per run (Settings)."
    # with a recorded change (nothing asks Claude) no amount is named: nothing can be spent
    recorded = engine._fix_step(_facts(assistant_walk), {**fix, "proposal": {"lines": ["Why it is proposed: a test failed."]}}, button, None, where, True)
    assert not any("spend" in line or "Claude" in line for line in recorded["step"]["confirm"]["lines"])


def test_fixes_offers_connect_only_after_the_proposal_is_accepted_as_its_page_does(assistant_walk):
    before = _steps(assistant_walk.at["ran"].pages["fixes"], "next:connect")
    after = _steps(assistant_walk.at["fix_accepted"].pages["fixes"], "next:connect")
    assert before == []                      # the page's button is off until the accept, and an off button is only listed for the open fix
    # (and off again, as on the page, once a check that has not run joins the plan: "Run every test in the plan first")
    assert _steps(assistant_walk.at["accepted"].pages["fixes"], "next:connect") == []
    assert len(after) == 1 and after[0]["title"] == "Connect demo code" and after[0]["step"]["can"]
    assert after[0]["step"]["confirm"]["names"] == "This is the Connect demo code button on Fixes."
    assert any("merges nothing" in line.lower() for line in after[0]["step"]["confirm"]["lines"])
    # with the fix open on the page, the off button is listed with the page's own reason and no Confirm
    lab = assistant_walk.lab
    fix_id = next(f["id"] for f in lab.fixes_view(assistant_walk.plan_id)["fixes"] if f["kind"] == "code")
    opened = _steps(lab.assistant_view(assistant_walk.assessment_id, "fixes", fix_id), "next:connect")
    assert len(opened) == 1 and opened[0]["open_item"] and not opened[0]["step"]["can"] and opened[0]["step"]["confirm"] is None
    assert opened[0]["step"]["blocked_reason"] == proposals.CLOSED
    # Try on a test copy is offered for the server change; Approve, Apply, Merge and the downloads are never offered
    kinds = {e["what"] for snap in assistant_walk.at.values() for view in snap.pages.values() for e in _steps(view)}
    assert "next:try" in kinds
    assert not {k for k in kinds if any(x in k for x in ("approve", "apply", "merge", "rollback", "download", "close"))}


# ---------------------------------------------------------------- what this means

def test_evidence_says_what_each_result_that_is_not_a_pass_means_in_the_results_own_sentence(assistant_walk):
    lab = assistant_walk.lab
    view = assistant_walk.at["ran"].pages["evidence"]
    meanings = [e for e in view["on_page"]["entries"] if e["what"] == "meaning:result"]
    rows = {r["title"]: (r["after"] or r["result"]) for r in lab.lab_view(assistant_walk.plan_id)["rows"]}
    not_passed = {title for title, r in rows.items() if r and r["tone"] != "pass"}
    assert {e["title"] for e in meanings} == not_passed and len(meanings) >= 4
    assert [e["badge"]["tone"] for e in meanings] == sorted((e["badge"]["tone"] for e in meanings), key=lambda t: {"fail": 0, "warn": 1}.get(t, 2))
    for e in meanings:
        result = rows[e["title"]]
        assert e["mark"] == "What this means" and e["text"].startswith(result["plain"]) and e["badge"]["label"] == result["label"]
        assert e["links"][0]["label"] == "See the evidence" and e["decisions"] == [] and e["step"] is None      # links, and nothing else
        if result["fix_line"]:
            assert e["text"].endswith("A fix is suggested: see Fixing.") and e["links"][1]["link"] == {
                "page": "fixes", "item": result["fix_line"]["fix_id"], "group": None}
    assert any(rows[e["title"]]["fix_line"] for e in meanings)


def test_import_repeats_the_line_about_the_checks_that_may_apply_and_fixes_says_why_a_fix_is_text_only(assistant_walk):
    found = [e for e in assistant_walk.at["proposed"].pages["inventory/import"]["on_page"]["entries"] if e["what"] == "meaning:found"]
    line = assistant_walk.at["proposed"].overview["import"]["otto"]
    assert len(found) == 1 and found[0]["title"] == line["text"] and found[0]["links"][0]["link"] == line["link"]
    text_only = [e for e in assistant_walk.at["measured"].pages["fixes"]["on_page"]["entries"] if e["what"] == "meaning:text_only"]
    assert text_only and all(e["thread"] == "fixing" and e["text"] and e["links"][0]["label"] == "Open the fix" for e in text_only)
    assert any(e["text"].startswith("A server setting, not a code change") for e in text_only)


# ---------------------------------------------------------------- nothing can be decided: closed, and without Otto

def test_in_a_closed_assessment_everything_is_listed_and_nothing_can_be_pressed(assistant_walk):
    snap = assistant_walk.at["closed"]
    for view in snap.pages.values():
        assert view["notices"] and view["notices"][0].endswith("This assessment is closed. Start a new one to continue.")
        for e in view["on_page"]["entries"] + [x for tab in view["tabs"] for x in tab["so_far"]]:
            for d in e["decisions"]:
                assert d["can"] is False and d["confirm"] is None and d["blocked_reason"]
            if e["step"] is not None and e["step"]["needs"] == "confirm":
                assert e["step"]["can"] is False and e["step"]["confirm"] is None and e["step"]["blocked_reason"]
    listed = _suggestions(snap.pages["advisories"])
    assert {e["id"] for e in listed} == {assistant_walk.ids["second"], assistant_walk.ids["third"]}
    assert all(d["blocked_reason"] == proposals.CLOSED for e in listed for d in e["decisions"])
    assert len(snap.pages["overview"]["tabs"]) == 3


def test_without_otto_the_panel_says_what_settings_says_and_no_decision_can_be_made(tmp_path, monkeypatch):
    lab = made.start_lab(tmp_path, monkeypatch, record_prompts=False)
    try:
        missing = harness.OttoStatus(False, harness.NOT_FETCHED, "isogeny-labs/otto", "a" * 40, "0.1.0", None)
        monkeypatch.setattr(harness, "status", lambda *a, **k: missing)
        view = lab.assistant_view(lab.assessment_id, "advisories")
        assert problems(view, models.AssistantView, "assistant without Otto") == []
        assert view["notices"] == [missing.sentence] and missing.sentence.startswith("Otto is not installed on this computer")
        listed = _suggestions(view)
        assert len(listed) == 3
        for e in listed:
            assert [d["key"] for d in e["decisions"]] == ["accept", "reject"]
            assert all(not d["can"] and d["confirm"] is None and "Otto is not installed" in d["blocked_reason"] for d in e["decisions"])
        # the rest works as before: the page's own buttons are still offered as next steps
        assert [e["title"] for e in _steps(lab.assistant_view(lab.assessment_id, "checks"), "next:run_all")] == ["Run all"]
    finally:
        lab.stop()


# ---------------------------------------------------------------- wording

def test_the_panel_never_says_secure_gives_no_score_and_rates_nothing(assistant_walk):
    for stage, snap in assistant_walk.at.items():
        for page, view in snap.pages.items():
            for text in _texts(view):
                low = text.lower()
                assert not any(word in low for word in BANNED), f"{stage} {page}: {text}"
    assert words.NOTHING_WAITING == "Nothing from Otto is waiting for a decision."
    assert "runs nothing" in words.LOOKING.lower()
