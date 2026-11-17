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
FAILED = {"label": "Failed", "tone": "fail", "plain": "It got 3 of 77 published cases wrong.", "component": "one 1.0", "finished_at": None}
PASSED = {"label": "Passed", "tone": "pass", "plain": "It got all 77 published cases right.", "component": "two 1.0", "finished_at": None}


def _here(program: str, item_id: int | None, result: dict | None, own_code: bool = False) -> dict:
    return {"program": program, "item_id": item_id, "result": result, "ledger": [], "own_code": own_code}


def _view(here: list[dict], fix: dict | None = None, entry: dict | None = None, made: dict | None = None) -> dict:
    if entry is None:
        entry, made = helpers.pack_advisory()
    rows = [{"pack": PACK, "advisory": entry, "design": made, "here": here, "fix": fix}]
    return present_otto.advisories_view(rows=rows, packs=[PACK], to_add=0, fitting=[h["program"] for h in here], closed=False,
                                        harness_status=STATUS, answers_line="Answers written for a test", assessment_id=1)


def _row(here: list[dict], **more) -> dict:
    return _view(here, **more)["rows"][0]


def test_a_count_of_results_never_counts_a_program_that_has_no_result():
    """One of four programs failed and three have not run: the row must not read "Failed, 1 of 4 programs"."""
    some = _row([_here("one 1.0", 11, FAILED), _here("two 1.0", 12, None), _here("three 1.0", 13, None), _here("four 1.0", None, None)])
    assert some["result"]["label"] == "Failed" and some["result"]["text"] == "1 of 1 run so far; 3 with no result yet"
    assert [h["status"] for h in some["panel"]["here"]["rows"]] == [None, "Not run yet", "Not run yet", "Not added yet"]
    # every program has a result: the count is of all of them, and it counts the ones with the shown label
    every = _row([_here("one 1.0", 11, FAILED), _here("two 1.0", 12, PASSED), _here("three 1.0", 13, PASSED), _here("four 1.0", 14, PASSED)])
    assert every["result"]["label"] == "Failed" and every["result"]["text"] == "1 of 4 programs"
    mixed = _row([_here("one 1.0", 11, PASSED), _here("two 1.0", 12, PASSED), _here("three 1.0", 13, None)])
    assert mixed["result"]["label"] == "Passed" and mixed["result"]["text"] == "2 of 2 run so far; 1 with no result yet"
    # one program: its result needs no count
    assert _row([_here("one 1.0", 11, FAILED)])["result"]["text"] is None


def test_the_line_about_your_own_code_shows_only_where_there_is_such_code_with_this_check():
    def lines(here, **more):
        return " ".join(_row(here, **more)["panel"]["fix"]["lines"])
    own = lines([_here("acme-sign 1.4.2", 11, None, own_code=True)])
    assert "For your own code (acme-sign 1.4.2)" in own
    # it promises only what holds whatever the failure: Otto's change if it can be proven, else the template if it
    # answers the failure, else the reason
    assert "only when it can be proven on this computer" in own and "if it answers the failure" in own and "Fixes says why no change is offered" in own
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
    assert "if it answers this failure" in said and "Fixes says why no change is offered" in said and "takes its place" not in said
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
    assert notes["kind_line"] == ("Kind of weakness, as Otto recorded it: the affected software accepts a signature it must reject, "
                                  "when checking ECDSA signatures.")
    assert notes["text"] == entry["reading"]["notes"]
    assert notes["caption"].startswith("Claude's words from reading the advisory (Written for a test, not an answer from Claude)")
    assert "S1, S2 and so on are the sources listed above" in notes["caption"] and notes["caption"].endswith("Information, not a result.")
    # no notes: the kind is still said; a kind this version has no words for is not guessed at
    entry["reading"].update(notes="", kind="other", area="other")
    plain = _row([], entry=entry, made=made)["panel"]["notes"]
    assert plain["text"] is None and "has a weakness of another kind, outside signature checking" in plain["kind_line"]
    # an advisory Otto could not read has no notes at all
    entry["reading"], entry["reading_refused"] = None, "Otto could not read this advisory: the quote is not in the publisher's text."
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
