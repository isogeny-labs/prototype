"""Phase 5c: what the Advisories page says, checked on the words themselves. The page decides nothing, so what matters
is that no line says more than was measured: a count of results never counts a program that has no result, the line
about the customer's own code shows only where there is such code, a replay is called what it was, Claude's notes are
labelled as Claude's, and Settings says when the recorded answers were made also before a pack is installed.

None of this needs the Otto harness: the presenter is given its rows directly."""
from types import SimpleNamespace

import otto_helpers as helpers
from app.otto import model
from app.present import advisory as present_advisory
from app.present import otto as present_otto

PACK = SimpleNamespace(version="2026.11.1")
STATUS = {"installed": True, "sentence": "Otto harness: version 0.1.0, commit aa4a6fd (pinned)."}
FAILED = {"label": "Failed", "tone": "fail", "plain": "It got 3 of 77 published cases wrong.", "component": "one 1.0", "finished_at": None,
          "code": "failed"}
PASSED = {"label": "Passed", "tone": "pass", "plain": "It got all 77 published cases right.", "component": "two 1.0", "finished_at": None,
          "code": "passed"}


def _here(program: str, item_id: int | None, result: dict | None, own_code: bool = False) -> dict:
    return {"program": program, "item_id": item_id, "result": result, "ledger": [], "own_code": own_code}


def _view(here: list[dict], fix: dict | None = None, entry: dict | None = None, made: dict | None = None) -> dict:
    if entry is None:
        entry, made = helpers.pack_advisory()
    rows = [{"pack": PACK, "advisory": entry, "design": made, "here": here, "fix": fix}]
    return present_otto.advisories_view(rows=rows, packs=[PACK], fitting=[h["program"] for h in here], closed=False,
                                        harness_status=STATUS, answers_line="Answers written for a test", assessment_id=1)


def _row(here: list[dict], **more) -> dict:
    return _view(here, **more)["rows"][0]


def test_a_count_of_results_never_counts_a_program_that_has_no_result():
    """One of four programs failed and three have not run: the row must not read "Failed, 1 of 4 programs"."""
    some = _row([_here("one 1.0", 11, FAILED), _here("two 1.0", 12, None), _here("three 1.0", 13, None), _here("four 1.0", None, None)])
    assert some["result"]["label"] == "Failed" and some["result"]["text"] == "1 of 1 run so far; 3 with no result yet"
    assert [h["status"] for h in some["panel"]["here"]["rows"]] == [None, "Not run yet", "Not run yet", "Not in the test plan"]
    # every program has a result: the count is of all of them, and it counts the ones with the shown label
    every = _row([_here("one 1.0", 11, FAILED), _here("two 1.0", 12, PASSED), _here("three 1.0", 13, PASSED), _here("four 1.0", 14, PASSED)])
    assert every["result"]["label"] == "Failed" and every["result"]["text"] == "1 of 4 programs"
    mixed = _row([_here("one 1.0", 11, PASSED), _here("two 1.0", 12, PASSED), _here("three 1.0", 13, None)])
    assert mixed["result"]["label"] == "Passed" and mixed["result"]["text"] == "2 of 2 run so far; 1 with no result yet"
    # one program: its result needs no count
    assert _row([_here("one 1.0", 11, FAILED)])["result"]["text"] is None


def test_a_result_after_a_retest_says_which_version_it_is_of():
    """Found by the second review of 18 November 2026: after a retest, the row named for acme-sign 1.4.2 read "Passed",
    which was the result on the retested version. The row now says which version, and what the first run read."""
    after, first = {**PASSED, "component": "acme-sign 1.4.3-otto"}, {**FAILED, "component": "acme-sign 1.4.2"}
    row = _row([{**_here("acme-sign 1.4.2", 11, after), "first": first}])
    assert row["result"]["label"] == "Passed"
    assert row["result"]["text"] == "Retest on acme-sign 1.4.3-otto. First run on acme-sign 1.4.2: Failed."
    here, = row["panel"]["here"]["rows"]
    assert here["result"]["ran_on"] == "This is the retest, on acme-sign 1.4.3-otto. The first run, on acme-sign 1.4.2, read Failed."
    assert set(here["result"]) == {"label", "tone", "plain", "component", "finished_at", "ran_on", "source_tag", "sandbox_copy"}
    assert here["result"]["sandbox_copy"] is False        # (sandbox research is off: no run is on a sandbox copy)
    # (22 November 2026: an advisory check runs a copy of the program on this computer: Proven in the lab)
    assert here["result"]["source_tag"]["label"] == "Proven in the lab" and row["result"]["source_tag"] == here["result"]["source_tag"]
    # a first run is of the version the row names: no such line
    plain = _row([_here("acme-sign 1.4.2", 11, FAILED)])
    assert plain["result"]["text"] is None and plain["panel"]["here"]["rows"][0]["result"]["ran_on"] is None
    # with several programs the cell keeps its count; each program's own row in the panel says its version
    two = _row([{**_here("one 1.0", 11, after), "first": first}, _here("two 1.0", 12, PASSED)])
    assert two["result"]["text"] == "2 of 2 programs" and two["panel"]["here"]["rows"][0]["result"]["ran_on"]


def test_the_fix_block_says_what_the_pack_carries_and_where_it_is_a_proposal():
    """Found by the second review of 18 November 2026: the panel read "Proposed: update openjdk" with no Accept or
    Reject, for a library the file did not name, and with a proof line in other words than the two rows use."""
    entry, made = helpers.pack_advisory(fix_state="not_proven")
    block = _row([], entry=entry, made=made)["panel"]["fix"]
    fix = entry["fix"]
    assert block["label"] == "From Otto" and not any(line.startswith("Otto proposes") for line in block["lines"])
    assert block["lines"][0] == (f"The test pack carries a fix for {fix['library']}, the library this advisory is about: update it to "
                                 f"{fix['version']} or later.")
    # the first proof row, in the words Fixes, Evidence and the report use
    assert present_otto.public_copies_row(fix, entry)["line"] in block["lines"] and fix["reason"] not in block["lines"]
    assert any("only where it applies: on Fixes when this advisory's check has failed on" in line and "on Dependencies" in line
               for line in block["lines"])
    # where a fix of this assessment answers the check, the block links to it and leaves the general sentence out
    linked = _row([], entry=entry, made=made, fix={"id": "fix-9", "title": "Update acme-sign to 1.4.3", "status": {"word": "Text only"}})
    assert linked["panel"]["fix"]["here"]["line"] == "In this assessment: Update acme-sign to 1.4.3 (Text only)."
    assert not any("only where it applies" in line for line in linked["panel"]["fix"]["lines"])


def test_the_line_over_the_table_asks_for_no_decision_where_none_can_be_recorded():
    """Found by the second review of 18 November 2026: with Otto not installed the page read "2 proposed checks wait for
    your decision. Open an advisory to accept or reject" and, right under it, "nothing can be decided"."""
    waiting = {"id": "check-1", "kind": "check", "title": "A check", "why": "", "lines": [], "state": "proposed", "decisions": [],
               "actions": {"accept": "Otto is not installed on this computer.", "reject": "Otto is not installed on this computer."},
               "link": {"page": "advisories", "item": "CVE-2022-21449"}, "current": True, "facts": {}}
    entry, made = helpers.pack_advisory()
    rows = [{"pack": PACK, "advisory": entry, "design": made, "here": [{**_here("acme-sign 1.4.2", None, None), "proposal": waiting}], "fix": None}]
    def view(**status):
        return present_otto.advisories_view(rows=rows, packs=[PACK], fitting=["acme-sign 1.4.2"], answers_line="Answers written for a test",
                                            assessment_id=1, **status)["waiting"]
    absent = view(closed=False, harness_status={"installed": False, "sentence": "Otto is not installed on this computer."})
    assert absent["count"] == 1 and absent["line"] == "1 proposed check has no decision."
    assert "nothing can be decided" in absent["blocked_reason"] and "accept or reject" not in absent["line"]
    closed = view(closed=True, harness_status=STATUS)
    assert closed["line"] == "1 proposed check has no decision." and closed["blocked_reason"].startswith("This assessment is closed")
    open_ = view(closed=False, harness_status=STATUS)
    assert open_["line"] == "1 proposed check waits for your decision. Open an advisory to accept or reject its check."
    assert open_["blocked_reason"] is None


def test_the_line_about_your_own_code_shows_only_where_there_is_such_code_with_this_check():
    def lines(here, **more):
        return " ".join(_row(here, **more)["panel"]["fix"]["lines"])
    own = lines([_here("acme-sign 1.4.2", 11, None, own_code=True)])
    assert "For your own code (acme-sign 1.4.2)" in own
    # it promises only what holds whatever the failure: Otto's change if it can be proven, else the template if it
    # answers the failure, else the reason
    assert "only when it can be proven on this computer" in own and "if it answers the failure" in own and "offers no code change" in own
    assert "says why" not in own             # where no template answers, Fixes has no reason of Otto's to give
    assert "takes its place" not in own                      # the template does not always answer
    # a real library is not the customer's own code: the app writes no code for other people's software
    assert "your own code" not in lines([_here("elliptic 6.5.6", 11, FAILED), _here("openjdk 17.0.2", 12, None)])
    # the check is not in the plan yet: nothing can fail here, so nothing is said about it
    assert "your own code" not in lines([_here("acme-sign 1.4.2", None, None, own_code=True)])
    # a fix in Fixes answers this check now: the panel points to it and says nothing more
    fix_view = {"id": "fix-ecdsa-range-check", "title": "acme-sign accepts out-of-range signatures", "status": {"word": "Ready to try"}}
    shown = _row([_here("acme-sign 1.4.2", 11, FAILED, own_code=True)], fix=fix_view)["panel"]["fix"]
    assert "your own code" not in " ".join(shown["lines"]) and shown["here"]["link"] == {"page": "fixes", "item": "fix-ecdsa-range-check"}
    # an advisory with no test has no check that could fail
    entry, made = helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")
    assert "your own code" not in lines([], entry=entry, made=made)


def test_a_failed_check_on_your_own_code_points_to_fixes_without_promising_a_template():
    said = present_advisory.fix_words("acme-sign 1.4.2", {"state": "own_code"})
    assert said.startswith("Open Fixes") and "acme-sign" in said
    assert "if it answers this failure" in said and "offers no code change" in said and "takes its place" not in said and "says why" not in said
    assert "only after every locked test passes on the changed code" in said


def test_a_replay_is_called_what_it_was():
    """The replay is a second step of the same build on the same computer. It is not an outside check, and the page
    does not let it read as one."""
    trial = " ".join(_row([])["panel"]["test"]["trial"]["lines"])
    assert "run again as a separate replay step of the same build, on the same computer" in trial and "same numbers" in trial
    assert "second author" not in trial and "independent" not in trial.lower()
    entry, made = helpers.pack_advisory()
    entry["test"]["trial"]["replayed"] = False
    assert "It was not replayed." in " ".join(_row([], entry=entry, made=made)["panel"]["test"]["trial"]["lines"])


def test_claudes_notes_are_labelled_as_claudes_and_say_which_kind_of_weakness_was_recorded():
    entry, made = helpers.pack_advisory()
    entry["reading"]["notes"] = "The advisory covers two problems, and the kind above records only the first (S1)."
    notes = _row([], entry=entry, made=made)["panel"]["notes"]
    assert set(notes) == {"title", "kind_line", "text", "caption"} and notes["title"] == "Otto's notes on reading it"
    # "the kind" the notes speak of is on the screen with them
    assert notes["kind_line"] == ("Kind of weakness, as recorded: the affected software accepts a signature it must reject, "
                                  "when checking ECDSA signatures.")
    assert notes["text"] == entry["reading"]["notes"]
    assert notes["caption"].startswith("Claude's words from reading the advisory (Written for a test, not an answer from Claude)")
    assert "S1, S2 and so on are the sources listed above" in notes["caption"] and notes["caption"].endswith("Information, not a result.")
    # no notes: the kind is still said; a kind this version has no words for is not guessed at
    entry["reading"].update(notes="", kind="other", area="other")
    plain = _row([], entry=entry, made=made)["panel"]["notes"]
    assert plain["text"] is None and "has a weakness of another kind, outside signature checking" in plain["kind_line"]
    # an advisory that could not be read has no notes at all
    entry["reading"], entry["reading_refused"] = None, "This advisory could not be read: the quote is not in the publisher's text."
    assert _row([], entry=entry, made=None)["panel"]["notes"] is None


def test_a_quote_is_tagged_by_where_it_was_read_not_as_the_advisorys_own_text():
    """A reading may quote the publisher's source file where the advisory itself does not put the weakness into words,
    so the tag names what is always true of it."""
    quote = _row([])["panel"]["publisher"]
    assert quote["tag"] == "quoted from the named source, not a result" == present_advisory.BOX_TAG
    assert quote["source"] == "A made-up advisory for a test" and quote["read_on"] == "17 November 2026"


def test_the_recorded_answers_say_when_they_were_made(tmp_path):
    assert model.recorded_since((tmp_path,)) is None and model.recorded_since((tmp_path / "missing",)) is None
    model.write_recorded(tmp_path, "read_advisory", "one prompt", "{}", "2026-11-17T19:42:14Z", "Recorded for a test")
    model.write_recorded(tmp_path, "design_test", "another prompt", "{}", "2026-11-17T19:35:32Z", "Recorded for a test")
    (tmp_path / "damaged.json").write_text("{not json")
    assert model.recorded_since((tmp_path,)) == "2026-11-17T19:35:32Z"            # the earliest one that can be read


def test_settings_dates_the_recorded_answers_before_any_pack_is_installed(tmp_path, monkeypatch):
    """SPEC section 2: the status line reads "Answers recorded during the build, 17 November 2026". It must, also on a
    new computer where no pack is installed yet: the day comes from the recorded answers themselves."""
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()])
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first}, [public])
    try:
        assert lab.otto_view()["answers"]["line"] == "Answers recorded during the build"        # this folder holds none
        model.write_recorded(lab.settings.otto_recorded, "read_advisory", "one prompt", "{}", "2026-11-17T19:42:14Z", "Recorded for a test")
        assert lab.otto_view()["answers"]["line"] == "Answers recorded during the build, 17 November 2026"
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        assert lab.otto_view()["answers"]["line"] == "Answers written for a test, 17 November 2026"   # then the pack's own line
    finally:
        lab.stop()


def test_a_trial_line_counts_one_case_as_one_case():
    entry, made = helpers.pack_advisory("CVE-2024-42460", "Wrongly encoded signature accepted", flags=("MissingZero",))
    arms = entry["test"]["trial"]["arms"]
    assert len(made["cases"]["ids"]) == 1
    arms["affected"].update(right=0, wrong=1, total=1)
    arms["fixed"].update(right=1, wrong=0, total=1)
    arms["accept-all"].update(right=0, wrong=1, total=1)
    lines = _row([], entry=entry, made=made)["panel"]["test"]["trial"]["lines"]
    assert lines[0].endswith("(affected): 1 of 1 case wrong.") and lines[1].endswith("0 of 1 case wrong.")
    assert not any("1 cases" in line for line in lines)
    assert any("2 of 64 cases wrong" in line for line in _row([])["panel"]["test"]["trial"]["lines"])      # several stay "cases"


def test_the_advisory_box_counts_one_case_as_one_case():
    """The box on a check's result panel says how many published cases the check reruns. The check for
    CVE-2024-42460 reruns exactly one."""
    def covered(cases: int) -> str:
        spec = {"inputs": {"advisory": {"id": "CVE-2024-42460", "quote": "a line of the publisher's", "pack": "2026.11.2",
                                        "source": {"title": "the record", "url": "https://github.com/advisories/GHSA-977x-g7h5-7qgw"}},
                           "cases": [{"id": str(n)} for n in range(cases)]}}
        return present_advisory.box(spec)["items"][0]["covered"]
    one, many = covered(1), covered(77)
    assert "the 1 published test case that matches it" in one and "1 published test cases" not in one and "case that match it" not in one
    assert "the 77 published test cases that match it" in many and "cases that matches" not in many
    for line in (one, many):
        assert "from test pack 2026.11.2" in line and line.endswith("the result comes only from the test.")


def test_the_pack_builder_counts_one_case_as_one_case():
    """The sentence a pack carries about a ready test. Pack 2026.11.2 was signed with "1 of 1 cases wrong" and stays
    as it is; the builder words the next pack right, and the sentences of the shipped packs with several cases are
    the ones it would still write."""
    import json

    from ottolab import build
    one = build.ready_reason("elliptic", {"version": "6.5.6", "wrong": 1, "total": 1}, {"version": "6.5.7"})
    assert "elliptic 6.5.6 got 1 of 1 case wrong, elliptic 6.5.7 got none wrong" in one and "1 cases" not in one
    shipped = json.loads((build.PACKS / "2026.11.1.json").read_text())
    body = shipped.get("pack", shipped)
    java = next(a for a in body["advisories"] if a["id"] == "CVE-2022-21449")
    arms = java["test"]["trial"]["arms"]
    assert build.ready_reason("openjdk", arms["affected"], arms["fixed"]) == java["test"]["reason"]


def test_the_overviews_next_step_points_to_where_a_proposal_waits():
    """It opens a page and runs nothing. The plan's own tests come first, and a closed assessment is never sent there.
    A proposed check comes before a proposed fix; a plan change and a dependency update come after the open fixes."""
    from app.projects.store import ProjectsMixin
    brief = {"status": {"key": "open"}, "file": {"name": "acme-pay-cbom.json"}}
    counts = {"claims": 3, "tests": 5, "fixes": {"open": 1}}
    step = ProjectsMixin._next_step
    one = step(brief, counts, None, {"check": 1})
    assert one["page"] == "advisories" and one["label"] == "Open advisories"
    assert one["text"] == ("1 advisory check is proposed from the installed test packs. Accept or reject it: accepting runs nothing.")
    two = step(brief, counts, None, {"check": 2, "fix": 1})
    assert two["page"] == "advisories" and "2 advisory checks are proposed" in two["text"] and "each one" in two["text"]
    fix = step(brief, counts, None, {"check": 0, "fix": 1})
    assert fix["page"] == "fixes" and "A fix is proposed for a failed advisory check" in fix["text"] and "accepting runs nothing" in fix["text"]
    assert step(brief, counts, None, {"check": 0})["page"] == "fixes"                               # nothing waiting: as before
    assert step(brief, counts, None, None)["text"] == "Some failed tests or migration steps have a suggested fix waiting."
    no_fixes = {**counts, "fixes": {"open": 0}}
    assert step(brief, no_fixes, {"has_migration": True}, {"plan": 1})["page"] == "migration/systems"
    assert step(brief, no_fixes, {"has_migration": True}, {"dependency": 1})["page"] == "migration/dependencies"
    # Before the first run a proposed check comes first (second review, 18 November 2026): an accepted one runs with the
    # suggested tests. With nothing proposed, the first run is the next step, as before.
    assert step(brief, {**counts, "tests": None}, None, {"check": 2})["page"] == "advisories"
    assert step(brief, {**counts, "tests": None}, None, {"check": 0, "fix": 0})["page"] == "checks"
    assert step(brief, {**counts, "claims": None, "tests": None}, None, {"check": 2})["page"] == "inventory/import"     # Verify still comes first
    assert step({**brief, "status": {"key": "closed"}}, counts, None, {"check": 2})["page"] == "overview"
    words = " ".join(step(brief, no_fixes, {"has_migration": True}, {kind: 1})["text"] for kind in ("check", "fix", "plan", "dependency"))
    assert not any(banned in words.lower() for banned in ("secure", "score", "severity", "critical"))
