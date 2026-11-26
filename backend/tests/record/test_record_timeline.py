"""Evidence as the full record: the Timeline, one entry's story, Approvals and decisions, Evidence files and the history
in an item's panel. They repeat what the records say, with who and when: every result word is the one its own page
gives, a result's decider is the separate reviewer (fixed rules for a claim on Verify) and never a person, Change
watch stays apart, and what was done before names were kept says so."""

import copy
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

import record_walk
from app.assistant.threads import PAGES
from app.errors import BadRequest, NotFound
from app.present import record as words
from app.web import models
from conftest import PASSWORD, make_lab
from record_walk import FIX
from view_helpers import problems, texts

BANNED = ("secure", "score", "severity", "critical", "time to hack")
AREAS = ("observe", "advisories", "checks", "fixes", "migration", "dependencies", "watch", "assessment")
KINDS = ("runs", "people", "system", "files")


@pytest.fixture
def walked(request, tmp_path_factory):
    return record_walk.shared(request, tmp_path_factory)


@pytest.fixture
def short(request, tmp_path_factory):
    return record_walk.shared_short(request, tmp_path_factory)


def listed(view: dict) -> list[dict]:
    return [e for day in view["days"] for e in day["entries"]]


def entry(view: dict, prefix: str) -> dict:
    return next(e for e in listed(view) if e["id"].startswith(prefix))


def said(e: dict) -> str:
    return e["lead"] + "".join(part["v"] for part in e["rest"])


def on_the_pages(lab, plan_id: int) -> dict:
    """What each page holds that a link can open, read from the pages' own views (once for a lab that is not changing)."""
    kept = getattr(lab, "_pages_for_the_record_tests", None)
    if kept is None or kept[0] != plan_id:
        checks = lab.checks_view(plan_id)
        ids = {row["id"] for group in checks["groups"] for row in group["rows"]}  # a group's own rows
        in_blocks = set()  # the rows of one retest's, one fix proof's or one watch run's block: Checks only
        for group in checks["groups"]:
            for part in (group.get("parts") or {}).values():
                rows = [*part["rows"], *(row for block in part["blocks"] for row in block["rows"])] if part else []
                in_blocks |= {row["id"] for row in rows} | {row["alias"] for row in rows if row.get("alias")}
        claims = lab.import_json_for(lab.plan_view(plan_id)["import_id"])["claims"]
        kept = (
            plan_id,
            {
                # Results (frontend/src/components/EvidenceLabScreen.tsx) opens a test of the plan by "test-<id>" or by
                # the id of one of its retests (`opens`, below), a row of a group by its id, and a library of the list.
                # A row of a block of Checks is not among them.
                "evidence": ids | {library["id"] for library in checks["libraries"]},
                "evidence_tests": {row["item_id"] for row in lab.lab_view(plan_id)["rows"]},
                "checks": ids | in_blocks,
                "fixes": {f["id"] for f in lab.fixes_view(plan_id)["fixes"]},
                "inventory/verify": {f"claim-{c['id']}" for c in claims},
                # (the systems the file names, by the keys Migration gives them. Its own read is not asked: the first
                #  time it is, it writes each system's measurement down)
                "migration/systems": {
                    f"server:{c['location']}" if c["location_kind"] == "server" else f"software:{c['ref']}"
                    for c in claims
                },
                "change-watch": {c["id"] for c in lab.change_watch_view(plan_id)["changes"]},
            },
        )
        lab._pages_for_the_record_tests = kept
    return kept[1]


def opens(lab, plan_id: int, link: dict | None) -> bool:
    """Does this link open something that is there? A page of the app, and on it the item the link names."""
    if link is None:
        return True
    page, item = link["page"], link["item"]
    if page not in PAGES:
        return False
    if item is None:
        return True
    held = on_the_pages(lab, plan_id)
    if page == "evidence" and item.split("-")[0] in ("test", "retest"):
        number = item.split("-")[1]  # Results opens the test's own row, whichever of its runs the id names
        return number.isdigit() and int(number) in held["evidence_tests"]
    return item in held.get(page, ())


# ---------------------------------------------------------------- every day: the five reads on a short assessment


def test_a_short_assessment_read_through_the_five_reads(short):
    """The everyday run's walk: started, file in, ticked, a test taken out, Verify, Run, Run all, Mark reviewed, two
    downloads. (The long walk, with a fix and a developer's change, is read by the tests below, in the slow set.)"""
    lab, pid = short.lab, short.plan_id
    before = record_walk.everything_kept(lab)
    view = lab.timeline_view(pid)  # as a route reads it
    assert problems(view, models.TimelineView) == []
    entries = listed(view)
    kinds = ["start", "import", "action", "action", "verify", "press", "press", "mark", "export", "export"]
    assert [e["id"].split("-")[0] for e in reversed(entries)] == kinds and view["total"] == 10
    assert entries[-1]["who"]["button"] == "New project"  # (a project is made with its first assessment)
    run, run_all = entries[-6], entries[-7]
    assert said(run) == "Run: “Certificate strength”." and len(run["runs"]) == 1 and run["who"]["button"] == "Run"
    assert said(run_all) == "Run all: the 4 tests in the plan." and len(run_all["runs"]) == 4
    assert run_all["who"] == {**run_all["who"], "name": "You", "source": "default", "button": "Run all"}
    assert [(c["label"], c["count"]) for c in run_all["counts"]] == [("Failed", 2), ("Passed", 1), ("Measured", 1)]
    verify = entry(view, "verify-")
    assert verify["decided_by"] == words.BY_RULES and [(c["label"], c["count"]) for c in verify["counts"]] == [
        ("False", 1),
        ("True", 2),
    ]
    # every result word is the one Checks and Evidence give that run; what decides it is the reviewer, never a person
    on_checks = {
        h["run_id"]: (h["label"], h["tone"])
        for row in lab.ledger(pid)["rows"]
        for h in row.get("history") or []
        if h["run_id"] is not None
    }
    runs = [r for e in entries for r in e["runs"] if r["run_id"] is not None]
    assert {r["run_id"]: (r["result"]["label"], r["result"]["tone"]) for r in runs} == on_checks and len(runs) == 5
    for e in entries:
        assert e["decided_by"] == (
            None if not e["runs"] else words.BY_RULES if e["id"].startswith("verify-") else words.BY_REVIEWER
        )
        assert opens(lab, pid, e["link"]) and all(opens(lab, pid, r["link"]) for r in e["runs"]), e["id"]
        story = lab.timeline_entry_view(pid, e["id"], read=short.read)
        assert problems(story, models.TimelineEntryDetail, e["id"]) == [] and story["entry"] == e and story["people"]
    # the two filters, their counts and the search
    for area in ("all", *AREAS):
        for kind in ("all", *KINDS):
            chosen = lab.timeline_view(pid, area=area, kind=kind, read=short.read)
            assert next(f for f in chosen["areas"] if f["key"] == area)["count"] == chosen["total"], (area, kind)
            assert next(f for f in chosen["kinds"] if f["key"] == kind)["count"] == chosen["total"], (area, kind)
            assert all(area in ("all", e["area"]["key"]) and kind in ("all", e["kind"]["key"]) for e in listed(chosen))
    assert {f["key"]: f["count"] for f in view["areas"]} == {
        "all": 10,
        "observe": 2,
        "advisories": 0,
        "checks": 4,
        "fixes": 0,
        "migration": 0,
        "dependencies": 0,
        "watch": 0,
        "assessment": 4,
    }
    assert {f["key"]: f["count"] for f in view["kinds"]} == {"all": 10, "runs": 3, "people": 4, "system": 0, "files": 3}
    assert [e["id"].split("-")[0] for e in listed(lab.timeline_view(pid, q="RUN all", read=short.read))] == ["press"]
    assert view["apart"] is None and not any(e["apart"] for e in entries)
    with pytest.raises(BadRequest):
        lab.timeline_view(pid, area="elsewhere")
    with pytest.raises(NotFound):
        lab.timeline_entry_view(pid, "merge-1")
    # Approvals and decisions: what a person decided, and no result among them
    decisions = lab.decisions_view(pid, read=short.read)
    assert problems(decisions, models.DecisionsView) == []
    assert [r["decision"]["label"] for d in decisions["days"] for r in d["rows"]] == [
        "Marked reviewed",
        "Confirmed “I own this system”",
    ]
    assert [c["value"] for c in decisions["cards"]] == ["2", "0", "0", "Not yet"]
    # Evidence files
    files = lab.evidence_files_view(pid)
    assert problems(files, models.EvidenceFilesView) == []
    assert [f["id"] for f in files["files"]] == [short.download.id, short.first_download.id]
    assert files["files"][0]["who"]["button"] == "Download evidence"
    # the history of a check, and of a claim
    of_check = lab.history_view(pid, f"test:{short.item['bad_signatures']}", read=short.read)
    assert problems(of_check, models.HistoryView) == [] and of_check["decides"] == words.WHO_DECIDES
    assert [line["title"] for line in of_check["lines"]] == [
        "Marked reviewed",
        "First run on acme-sign 1.4.2",
        "Test details locked",
    ]
    first = of_check["lines"][1]
    assert (first["result"]["label"], first["said"], first["decided_by"]) == (
        "Failed",
        "started by You, with Run all",
        words.BY_REVIEWER,
    )
    claim = next(c for c in short.imp["claims"] if c["location_kind"] == "server")
    of_claim = lab.history_view(pid, f"claim:{claim['id']}", read=short.read)
    assert problems(of_claim, models.HistoryView) == [] and of_claim["decides"] == words.WHO_DECIDES_CLAIM
    assert of_claim["lines"][0]["decided_by"] == words.BY_RULES
    # asked by a row of Checks or Results, by the row's own id: a claim's check has the claim's history, with the line
    # that fixed rules decide a claim (not the reviewer); a test's row has the test's
    by_row = lab.history_view(pid, f"check:claim-{claim['id']}", read=short.read)
    assert problems(by_row, models.HistoryView) == [] and by_row["key"] == f"check:claim-{claim['id']}"
    assert by_row["lines"] == of_claim["lines"] and by_row["lines"] and by_row["empty_text"] is None
    assert by_row["decides"] == words.WHO_DECIDES_CLAIM and by_row["title"] == "History of this claim"
    assert by_row["timeline"] == {"area": "observe"}
    by_test = lab.history_view(pid, f"check:test-{short.item['bad_signatures']}", read=short.read)
    assert by_test["lines"] == of_check["lines"] and by_test["decides"] == words.WHO_DECIDES
    for missing in ("fix:no-such-fix", "check:claim-999", "check:test-999", "check:proof-999-in-9", "check:claim-x"):
        with pytest.raises(NotFound):
            lab.history_view(pid, missing, read=short.read)
    # no sentence rates anything, and reading changed nothing
    for shown in (view, decisions, files, of_check, of_claim):
        assert not any(w in text.lower() for text in texts(shown) for w in BANNED if text != view["disclaimer"])
    assert record_walk.everything_kept(lab) == before and not lab.jobs.live(pid)


# ---------------------------------------------------------------- 1. the Timeline


def test_the_timeline_lists_everything_that_happened_newest_first_one_entry_for_one_press(walked):
    lab, pid = walked.lab, walked.plan_id
    view = lab.timeline_view(pid)  # read here as a route reads it; the rest share the walk's one reading
    assert problems(view, models.TimelineView) == []
    entries = listed(view)
    assert view["total"] == len(entries) and sum(day["count"] for day in view["days"]) == len(entries)
    assert len({e["id"] for e in entries}) == len(entries)
    # in the order it happened (oldest first), by what each entry is
    assert [e["id"].split("-")[0] for e in reversed(entries)] == [
        "start",
        "import",
        "action",  # the "I own this system" tick
        "action",  # a test taken out of the plan
        "verify",
        "list",
        "tie",
        "action",  # the plan's order
        "press",  # Run
        "press",  # Run all
        "mark",
        "dig",
        "connect",
        "proof",
        "pr",
        "approval",
        "approval",
        "merge",
        "retest",
        "setting",
        "export",
        "export",
    ]
    assert said(entries[-1]) == "Assessment 1 started (Full review)."
    assert said(entries[-2]) == "Brought in acme-pay-cbom.json: 3 claims, 1 server and 1 program."
    assert entries[-2]["marks"] == ["Demo data"]
    run_all = entry(view, "press-10")
    assert said(run_all) == "Run all: the 4 tests in the plan." and len(run_all["runs"]) == 4
    assert run_all["who"]["name"] == "You" and run_all["who"]["button"] == "Run all" and run_all["pending"] == 0
    assert said(entry(view, "merge-")).startswith("Merged pull request #1 into main, commit ")
    assert said(entry(view, "retest-")) == "Retest on acme-sign 1.4.3: the 4 tests in the plan, on the merged fix."
    assert entry(view, "retest-")["who"]["button"] == "Retest now, on Fixes"
    # no sentence rates anything
    assert not any(word in text.lower() for text in texts(view) for word in BANNED if text != view["disclaimer"])


def test_every_result_word_is_the_one_its_own_page_gives_and_no_person_decides_one(walked):
    lab, pid = walked.lab, walked.plan_id
    view = lab.timeline_view(pid, read=walked.read)
    # what each run reads on Checks and Evidence (the ledger words every run as its own page does), and on Verify
    on_checks = {
        h["run_id"]: (h["label"], h["tone"])
        for row in lab.ledger(pid)["rows"]
        for h in row.get("history") or []
        if h["run_id"] is not None
    }
    on_verify = {r["claim"]["text"]: r for r in lab.latest_verify(walked.imp["id"])["results"]}
    seen = 0
    for e in listed(lab.timeline_view(pid, read=walked.read)) + listed(
        lab.timeline_view(pid, area="watch", read=walked.read)
    ):
        if not e["runs"]:
            assert e["decided_by"] is None and e["counts"] == [] and e["source_tags"] == []
            continue
        # what decides a result is the separate reviewer (fixed rules for a Verify claim): never the person who pressed
        assert e["decided_by"] == (words.BY_RULES if e["id"].startswith("verify-") else words.BY_REVIEWER)
        assert sum(c["count"] for c in e["counts"]) == len(e["runs"])
        for run in e["runs"]:
            seen += 1
            if run["run_id"] is None:
                on_page = on_verify[run["name"]]
                assert run["result"]["label"] == on_page["result"] and run["source_tag"] == on_page["source_tag"]
                continue
            assert (run["result"]["label"], run["result"]["tone"]) == on_checks[run["run_id"]]
            assert {c["label"] for c in e["counts"]} >= {run["result"]["label"]}
            if run["source_tag"] is not None:
                assert run["source_tag"]["key"] in {t["key"] for t in e["source_tags"]}
    assert seen >= 15 and seen == len(on_checks) + len(on_verify)  # every reviewed run of the assessment, once
    # a run's link opens the check that holds that very run, also in a retest's and a proof's own block on Checks
    for prefix in ("retest-", "proof-"):
        run = entry(view, prefix)["runs"][0]
        assert run["run_id"] in {h["run_id"] for h in lab.check_detail(pid, run["link"]["item"])["runs"]}
    verify = entry(view, "verify-")
    assert [(c["label"], c["count"]) for c in verify["counts"]] == [("False", 1), ("True", 2)]
    assert {t["label"] for t in verify["source_tags"]} == {"Observed live", "Proven in the lab"}
    # a proof says what the Fixes page says of it
    proof = entry(view, "proof-")
    on_fixes = next(f for f in lab.fixes_view(pid)["fixes"] if f["id"] == FIX)["proof"]["badge"]
    assert (
        proof["outcome"]
        == {"label": on_fixes["label"], "tone": on_fixes["tone"]}
        == {"label": "Proof passed", "tone": "pass"}
    )
    for text in texts(view):
        assert "decided by You" not in text and "approved the result" not in text.lower()


def test_the_two_filters_their_counts_and_the_search_agree_with_what_is_listed(walked):
    lab, pid = walked.lab, walked.plan_id
    everything = lab.timeline_view(pid, read=walked.read)
    assert [f["key"] for f in everything["areas"]] == ["all", *AREAS] and [f["key"] for f in everything["kinds"]] == [
        "all",
        *KINDS,
    ]
    assert everything["areas"][0]["label"] == "All" and everything["kinds"][0]["label"] == "Everything"
    for area in ("all", *AREAS):
        for kind in ("all", *KINDS):
            view = lab.timeline_view(pid, area=area, kind=kind, read=walked.read)
            assert view["chosen"] == {"area": area, "kind": kind, "q": ""}
            assert next(f for f in view["areas"] if f["key"] == area)["count"] == view["total"], (area, kind)
            assert next(f for f in view["kinds"] if f["key"] == kind)["count"] == view["total"], (area, kind)
            assert all(area in ("all", e["area"]["key"]) and kind in ("all", e["kind"]["key"]) for e in listed(view))
            assert (view["empty_text"] is None) == bool(view["total"])
    by_area = {f["key"]: f["count"] for f in everything["areas"]}
    assert by_area["all"] == sum(n for key, n in by_area.items() if key not in ("all", "watch"))
    assert (by_area["fixes"], by_area["observe"], by_area["dependencies"], by_area["migration"]) == (6, 2, 2, 1)
    by_kind = {f["key"]: f["count"] for f in everything["kinds"]}
    assert by_kind["all"] == sum(n for key, n in by_kind.items() if key != "all") == everything["total"]
    # the search reads the sentence, the names, the tests and their result words
    found = lab.timeline_view(pid, q="  MERGED pull  ", read=walked.read)
    assert found["chosen"]["q"] == "merged pull" and [e["id"] for e in listed(found)] == ["merge-1"]
    assert {
        e["id"].split("-")[0] for e in listed(lab.timeline_view(pid, q="certificate strength", read=walked.read))
    } == {
        "press",
        "proof",
        "retest",
        "action",
    }
    nothing = lab.timeline_view(pid, q="no such words anywhere", read=walked.read)
    assert nothing["total"] == 0 and nothing["days"] == [] and nothing["empty_text"] == words.TIMELINE_NOTHING_FITS
    for bad in ({"area": "elsewhere"}, {"kind": "results"}):
        with pytest.raises(BadRequest):
            lab.timeline_view(pid, **bad, read=walked.read)
    with pytest.raises(NotFound):
        lab.timeline_view(pid + 1000)


def test_days_are_the_viewers_days_and_the_times_stay_exact_moments(walked):
    lab, pid = walked.lab, walked.plan_id
    utc = lab.timeline_view(pid, read=walked.read)
    assert utc["zone"] == "UTC" and all(e["at"].startswith(day["date"]) for day in utc["days"] for e in day["entries"])
    assert (
        lab.timeline_view(pid, tz="Not/A_Zone", read=walked.read)["zone"] == "UTC"
        and lab.timeline_view(pid, tz="../etc/passwd", read=walked.read)["zone"] == "UTC"
    )
    try:
        zone = ZoneInfo(
            "Pacific/Kiritimati"
        )  # fourteen hours ahead of UTC: every entry of the walk is on another day there
    except ZoneInfoNotFoundError:
        pytest.skip("This computer has no time zone data.")
    far = lab.timeline_view(pid, tz="Pacific/Kiritimati", read=walked.read)
    assert far["zone"] == "Pacific/Kiritimati" and [e["at"] for e in listed(far)] == [e["at"] for e in listed(utc)]
    from app.present import times

    for day in far["days"]:
        assert all(times.instant(e["at"]).astimezone(zone).date().isoformat() == day["date"] for e in day["entries"])
    assert [d["date"] for d in far["days"]] == sorted((d["date"] for d in far["days"]), reverse=True)
    assert (
        lab.decisions_view(pid, tz="Pacific/Kiritimati", read=walked.read)["days"][0]["date"] == far["days"][0]["date"]
    )


def test_every_entry_and_every_run_links_to_where_it_lives(walked):
    lab, pid = walked.lab, walked.plan_id
    checked = 0
    for e in listed(lab.timeline_view(pid, read=walked.read)) + listed(
        lab.timeline_view(pid, area="watch", read=walked.read)
    ):
        assert e["link"] is not None and opens(lab, pid, e["link"]), (e["id"], e["link"])
        for run in e["runs"]:
            checked += 1
            assert opens(lab, pid, run["link"]), (e["id"], run["link"])
        detail = lab.timeline_entry_view(pid, e["id"], read=walked.read)
        for line in detail["rested"] + detail["after"]:
            assert opens(lab, pid, line["link"]), (e["id"], line)
    for row in [r for d in lab.decisions_view(pid, read=walked.read)["days"] for r in d["rows"]]:
        assert opens(lab, pid, row["link"]), row
    assert checked >= 15
    # A run of a fix proof and a run made for a developer's change are rows of one block of Checks; Results holds no
    # such row, so their links open Checks. A first run and a retest open the test's row on Results.
    view = lab.timeline_view(pid, read=walked.read)
    held = on_the_pages(lab, pid)
    for prefix, page, row_id in (
        ("proof-", "checks", r"proof-\d+-in-\d+"),
        ("retest-", "evidence", r"retest-\d+-on-\d+"),
        ("press-", "evidence", r"test-\d+"),
    ):
        runs = entry(view, prefix)["runs"]
        assert runs and all(r["link"]["page"] == page and re.fullmatch(row_id, r["link"]["item"]) for r in runs), prefix
    watch_runs = entry(lab.timeline_view(pid, area="watch", read=walked.read), "watch-")["runs"]
    assert watch_runs and all(
        r["link"]["page"] == "checks" and re.fullmatch(r"watch(base)?-\d+-in-\d+", r["link"]["item"])
        for r in watch_runs
    )
    assert not any(r["link"]["item"] in held["evidence"] for r in [*watch_runs, *entry(view, "proof-")["runs"]])


def test_change_watch_is_listed_only_under_change_watch_and_counted_nowhere_else(walked):
    lab, pid = walked.lab, walked.plan_id
    before, now = walked.before_watch["timeline"], lab.timeline_view(pid, read=walked.read)
    apart = lab.timeline_view(pid, area="watch", read=walked.read)
    assert [e["id"].split("-")[0] for e in listed(apart)] == ["watch", "devchange"] and all(
        e["apart"] for e in listed(apart)
    )
    assert apart["apart"] is None and next(f for f in apart["areas"] if f["key"] == "watch")["count"] == 2
    run, change = listed(apart)
    assert (
        run["outcome"] == {"label": "Passed before, fails now", "tone": "fail"}
        and run["decided_by"] == words.BY_REVIEWER
    )
    assert run["who"]["button"] == "Run the picked tests" and run["link"] == {
        "page": "change-watch",
        "item": walked.change["id"],
    }
    assert len(run["runs"]) >= 1 and all(r["link"]["item"].startswith(("watch-", "watchbase-")) for r in run["runs"])
    # the change came in by a commit of the demo developer; the press says who brought it in
    assert change["marks"] == ["Demo data"] and change["who"]["button"] == "Bring in a demo change"
    assert [(p["name"], p["source"], p["demo"]) for p in change["also"]] == [("Demo developer", "author", True)]
    # everywhere else nothing of it shows and nothing of it is counted: the only new entry is the second download
    ids_before, ids_now = [e["id"] for e in listed(before)], [e["id"] for e in listed(now)]
    assert ids_now == ["export-2", *ids_before] and not any(e["apart"] for e in listed(now))
    counts = {f["key"]: f["count"] for f in now["areas"] + now["kinds"] if f["key"] != "watch"}
    was = {f["key"]: f["count"] for f in before["areas"] + before["kinds"] if f["key"] != "watch"}
    assert counts == {**was, "all": was["all"] + 1, "assessment": was["assessment"] + 1, "files": was["files"] + 1}
    assert now["apart"] == {"count": 2, "label": "From a developer's change", "text": words.APART_NOTE, "area": "watch"}
    for area in AREAS[:-2] + AREAS[-1:]:
        assert not any(e["apart"] for e in listed(lab.timeline_view(pid, area=area, read=walked.read)))
    assert "watch" not in " ".join(e["id"] for e in listed(lab.timeline_view(pid, kind="runs", read=walked.read)))
    # nor in the decisions, nor in a check's own history
    assert walked.before_watch["decisions"]["total"] == lab.decisions_view(pid, read=walked.read)["total"]
    history = lab.history_view(pid, f"test:{walked.item['bad_signatures']}", read=walked.read)
    assert (
        not any("developer" in line["title"] for line in history["lines"])
        and words.WATCH_IS_ITS_OWN in history["notes"]
    )


# ---------------------------------------------------------------- 2. one entry's story


def test_the_story_of_a_merge_says_who_what_it_rested_on_and_what_came_after(walked):
    lab, pid = walked.lab, walked.plan_id
    for e in listed(lab.timeline_view(pid, read=walked.read)) + listed(
        lab.timeline_view(pid, area="watch", read=walked.read)
    ):
        detail = lab.timeline_entry_view(pid, e["id"], read=walked.read)
        assert problems(detail, models.TimelineEntryDetail, e["id"]) == []
        assert detail["entry"] == e and detail["summary"] == said(e) and detail["people"]
        assert detail["record"][0] == {"label": "Entry", "value": e["id"], "mono": True}
        if not e["id"].startswith("merge-"):
            assert detail["rested"] == [] and detail["after"] == []  # (an Apply has both: the slow set walks one)
    story = lab.timeline_entry_view(pid, "merge-1", read=walked.read)
    assert story["title"] == "Merged pull request #1" and story["link_label"] == "Open in Fixes"
    assert [(p["role"], p["who"]["name"], p["who"]["demo"]) for p in story["people"]] == [
        ("Merged by", "You", False),
        ("Approved by", "You", False),
        ("Approved as", "Demo reviewer A", True),
        ("Pressed by", "You", False),
    ]
    assert story["people"][0]["note"] == "after the box “Merge pull request?” was confirmed"
    proof, findings = story["rested"]
    assert proof["title"] == "Proof on acme-sign 1.4.3" and proof["chips"] == [
        {"name": None, "label": "Proof passed", "tone": "pass"}
    ]
    assert (
        proof["link"] == {"page": "fixes", "item": FIX, "section": "proof"}
        and "Decided by the separate reviewer." in proof["text"]
    )
    assert findings["title"] == "The 1 failed result it answers"
    assert findings["chips"] == [{"name": "Attacker tricks (our short list)", "label": "Failed", "tone": "fail"}]
    (after,) = story["after"]
    assert after["title"] == "Retest on acme-sign 1.4.3"
    assert after["chips"] == [{"name": "Attacker tricks (our short list)", "label": "Passed", "tone": "pass"}]
    labels = [f["label"] for f in story["record"]]
    assert labels == [
        "Entry",
        "Repository",
        "Branch",
        "Merge commit",
        "The change's commit",
        "The commit it starts from",
        "Pull request",
        "Proof",
    ]
    with pytest.raises(NotFound):
        lab.timeline_entry_view(pid, "merge-99", read=walked.read)


# ---------------------------------------------------------------- 3. Approvals and decisions


def test_every_decision_a_person_made_is_listed_with_who_and_no_result_is_among_them(walked):
    lab, pid = walked.lab, walked.plan_id
    view = lab.decisions_view(pid, read=walked.read)
    assert problems(view, models.DecisionsView) == []
    rows = [r for d in view["days"] for r in d["rows"]]
    assert [(r["decision"]["label"], r["area"]["label"]) for r in rows] == [
        ("Changed a system setting", "Migration plan"),
        ("Merged", "Fixes"),
        ("Approved", "Fixes"),
        ("Approved", "Fixes"),
        ("Marked reviewed", "Checks"),
        ("Tied a library", "Dependencies"),
        ("Confirmed “I own this system”", "Observatory and Verify"),
    ]
    as_demo, as_you = rows[2], rows[3]
    assert as_demo["who"]["name"] == "Demo reviewer A" and as_demo["who"]["demo"] and as_demo["marks"] == ["Demo data"]
    assert as_demo["pressed_by"]["name"] == "You" and as_demo["pressed_by"]["button"] == "Approve"
    assert as_you["who"]["name"] == "You" and as_you["pressed_by"] is None
    assert as_you["on"] == "Pull request #1: Reject signatures whose r or s is out of range"
    assert rows[4]["on"] == "Attacker tricks (our short list) on acme-sign 1.4.2: Failed"
    assert rows[-1]["on"] == f"“I own this system” for {walked.address}"
    assert {c["key"]: (c["value"], c["small"]) for c in view["cards"]} == {
        "decisions": ("7", "by people, in this assessment"),
        "approvals": ("2", "of a pull request or a change"),
        "otto": ("0", "none decided yet"),
        "signoff": ("Not yet", "Close assessment records who and when"),
    }
    assert view["names_note"] == words.NAMES_NOTE and "no person decides one" in view["results_note"]
    # no run and no result word is a decision
    assert not any(r["id"].split("-")[0] in ("press", "retest", "proof", "verify", "run", "watch") for r in rows)
    fixes = lab.decisions_view(pid, "fixes", read=walked.read)
    assert fixes["total"] == 3 and next(f for f in fixes["areas"] if f["key"] == "fixes")["count"] == 3
    assert fixes["cards"] == view["cards"]  # the counts on top are of the whole assessment
    assert lab.decisions_view(pid, "advisories", read=walked.read)["empty_text"] == words.TIMELINE_NOTHING_FITS


# ---------------------------------------------------------------- 4. Evidence files


def test_evidence_files_lists_every_download_with_who_and_how_to_check_one(walked):
    lab, pid = walked.lab, walked.plan_id
    view = lab.evidence_files_view(pid)
    assert problems(view, models.EvidenceFilesView) == []
    assert [f["id"] for f in view["files"]] == [walked.download.id, walked.first_download.id]
    newest = view["files"][0]
    assert newest["who"]["name"] == "You" and newest["who"]["button"] == "Download evidence"
    assert newest["json"]["url"] == f"/api/evidence/{newest['id']}/json" and newest["html"]["url"].endswith("/html")
    assert len(newest["fingerprint"]) == 64 and newest["fingerprint_label"] == "Fingerprint (SHA-256)"
    assert view["check"]["command"] == "cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>"
    assert "Who did what" in " ".join(view["holds"]["items"]) and view["download"] == lab.lab_view(pid)["download"]


# ---------------------------------------------------------------- 5. the history in an item's panel


def test_a_checks_history_has_each_run_who_started_it_and_when_its_details_were_locked(walked):
    lab, pid, item = walked.lab, walked.plan_id, walked.item["bad_signatures"]
    view = lab.history_view(pid, f"test:{item}", read=walked.read)
    assert problems(view, models.HistoryView) == []
    assert view["title"] == "History of this check" and view["decides"] == words.WHO_DECIDES
    assert view["timeline"] == {"area": "checks"} and words.PROOF_IS_ITS_OWN in view["notes"]
    lines = view["lines"]
    assert [line["title"] for line in lines] == [
        "Retest on acme-sign 1.4.3",
        "The fix it answers was merged",
        "Marked reviewed",
        "First run on acme-sign 1.4.2",
        "Test details locked",
    ]
    retest, merged, marked, first, locked = lines
    assert (retest["result"]["label"], retest["said"]) == ("Passed", "started by You, with Retest now, on Fixes")
    assert (first["result"]["label"], first["said"]) == ("Failed", "started by You, with Run all")
    assert first["decided_by"] == retest["decided_by"] == words.BY_REVIEWER and len(first["fingerprint"]) == 64
    assert first["source_tag"]["label"] == "Proven in the lab" and first["link"] == {
        "page": "evidence",
        "item": f"test-{item}",
    }
    assert (
        marked["said"] == "by You" and marked["decided_by"] is None and merged["link"] == {"page": "fixes", "item": FIX}
    )
    # a locked test is shared by every assessment that runs it: this is its first lock on this computer
    assert locked["note"].startswith("before its first run on this computer") and locked["who"] is None
    assert [line["at"] for line in lines] == sorted((line["at"] for line in lines), reverse=True)
    # a claim: each Verify result, decided by fixed rules, and the tick before it
    claim = next(c for c in walked.imp["claims"] if c["location_kind"] == "server")
    of_claim = lab.history_view(pid, f"claim:{claim['id']}", read=walked.read)
    assert of_claim["decides"] == words.WHO_DECIDES_CLAIM and of_claim["title"] == "History of this claim"
    assert [(line["title"], line["decided_by"]) for line in of_claim["lines"]] == [
        (f"Verify on {walked.address}", words.BY_RULES),
        ("Confirmed “I own this system”", None),
    ]
    assert of_claim["lines"][0]["said"] == "started by You, with Verify claims"


def test_a_fixs_history_runs_from_connecting_the_code_to_the_retest_on_the_merged_code(walked):
    lab, pid = walked.lab, walked.plan_id
    view = lab.history_view(pid, f"fix:{FIX}", read=walked.read)
    assert (
        problems(view, models.HistoryView) == [] and view["decides"] is None and view["timeline"] == {"area": "fixes"}
    )
    assert [line["title"] for line in view["lines"]] == [
        "Retest on acme-sign 1.4.3",
        "Merged pull request #1",
        "Approved pull request #1",
        "Approved pull request #1",
        "Opened pull request #1",
        "Proof on acme-sign 1.4.3",
        "Connected the demo code",
    ]
    retest, _, as_demo, as_you, _, proof, connected = view["lines"]
    # of a retest, the words of the tests this fix answers
    assert retest["results"] == [{"name": "Attacker tricks (our short list)", "label": "Passed", "tone": "pass"}]
    assert retest["said"] == "started by You, with Retest now, on Fixes" and retest["decided_by"] == words.BY_REVIEWER
    assert (as_demo["said"], as_demo["marks"], as_you["said"]) == ("by Demo reviewer A", ["Demo data"], "by You")
    assert proof["result"] == {"name": None, "label": "Proof passed", "tone": "pass"}
    assert proof["said"] == "started by You, with Connect demo code" and connected["said"] == "by You"
    # a system: its claims' Verify results and what people set for it
    system = lab.history_view(pid, f"system:{walked.server}", read=walked.read)
    assert {line["title"] for line in system["lines"]} >= {
        f"Verify on {walked.address}",
        "Changed a system setting",
        "Confirmed “I own this system”",
    }
    for key in (
        "fix:no-such-fix",
        "test:9999",
        "claim:9999",
        "system:server:nowhere:1",
        "nothing",
        "change:none",
        "test:abc",
    ):
        with pytest.raises(NotFound):
            lab.history_view(pid, key, read=walked.read)
    assert lab.history_view(pid, "advisory:CVE-0000-0000", read=walked.read)["empty_text"] == words.NO_HISTORY


@pytest.mark.slow
def test_a_change_to_a_system_from_its_try_to_its_roll_back(tmp_path, monkeypatch):
    from conftest import free_port, free_ports

    ports = free_ports(5)
    lab = make_lab(tmp_path, migration_ports=ports, lab_nginx_port=free_port())
    try:
        w = record_walk.migration_walk(lab, ports)
        pid = w.plan_id
        view = lab.timeline_view(pid, area="migration")
        assert problems(view, models.TimelineView) == []
        entries = listed(view)
        kinds = [e["id"].split("-")[0] for e in reversed(entries)]
        assert kinds == ["press", "choice", "try", "ask", "okay", "okay", "apply", "rollback", "press"]
        assert [e["kind"]["key"] for e in reversed(entries)] == [
            "runs",
            "people",
            "runs",
            "people",
            "people",
            "people",
            "system",
            "system",
            "runs",
        ]
        newest, oldest = entry(view, "press-"), entries[-1]
        assert oldest["who"]["button"] == "Measure status" and newest["who"]["button"] == "Measure again"
        tried, applied, back = entry(view, "try-"), entry(view, "apply-"), entry(view, "rollback-")
        assert (
            tried["outcome"] == {"label": "Try passed", "tone": "pass"}
            and tried["who"]["button"] == "Try on a test copy"
        )
        # the measurement the app makes right after an Apply and a Roll back is in that press's own entry, and nowhere else
        assert len(applied["runs"]) == 1 and len(back["runs"]) == 1 and applied["decided_by"] == words.BY_REVIEWER
        assert applied["runs"][0]["run_id"] not in {
            r["run_id"] for e in entries if e["id"].startswith("press-") for r in e["runs"]
        }
        assert (applied["who"]["button"], back["who"]["button"]) == ("Apply", "Roll back")
        for e in entries:
            assert opens(lab, pid, e["link"]) and all(opens(lab, pid, r["link"]) for r in e["runs"]), e["id"]
        story = lab.timeline_entry_view(pid, applied["id"])
        assert problems(story, models.TimelineEntryDetail) == []
        assert [(p["role"], p["who"]["name"]) for p in story["people"]] == [
            ("Applied by", "You"),
            ("Approved by", "You"),
            ("Approved as", "Demo reviewer A"),
            ("Pressed by", "You"),
        ]
        assert [r["title"] for r in story["rested"]] == ["Try on a test copy", "Approvals"]
        assert story["rested"][0]["chips"] == [{"name": None, "label": "Try passed", "tone": "pass"}]
        assert story["rested"][1]["text"].startswith("Approved by You and Demo reviewer A.")
        assert [r["title"] for r in story["after"]] == ["Measured right after Apply"] and len(
            story["after"][0]["chips"]
        ) == 1
        assert lab.timeline_entry_view(pid, back["id"])["after"][0]["title"] == "Measured right after Roll back"
        decided = [r["decision"]["label"] for d in lab.decisions_view(pid, "migration")["days"] for r in d["rows"]]
        assert decided == ["Rolled back", "Applied", "Approved", "Approved", "Chose an option"]
        # the change's own history, and its system's
        history = lab.history_view(pid, f"change:{w.key}")
        assert [line["title"] for line in history["lines"]] == [
            "Rolled back",
            "Applied",
            "Approved the change",
            "Approved the change",
            "Asked for approval",
            "Try on a test copy",
        ]
        assert history["lines"][-1]["result"]["label"] == "Try passed"
        of_system = [line["title"] for line in lab.history_view(pid, f"system:{w.system}")["lines"]]
        assert of_system.count(f"Measure status on {w.address}") == 2 and "Chose Hybrid" in of_system
        assert f"Measured right after Apply on {w.address}" in of_system and "Applied" in of_system
        # An Apply the server refuses. (The server's answer is stood in for; the button, its records and the reads are
        # the real ones.) It is pressed and recorded, nothing was applied, and nothing reads "Applied".
        from app.db import ActionRow
        from evidence import actions as verifier

        lab.try_change(pid, w.key)  # (the server changed since the first try; the approvals of this change stand)
        lab.wait_until_changes_idle(pid)
        monkeypatch.setattr(lab, "_put_in_force", lambda *args, **kwargs: (False, "the stand-in server said no"))
        lab.apply_change(pid, w.key)
        monkeypatch.undo()
        lab.wait_until_changes_idle(pid)
        refused = listed(lab.timeline_view(pid, area="migration"))[0]
        assert refused["id"].startswith("apply-") and refused["lead"] == "Not applied:" and refused["runs"] == []
        assert refused["kind"]["key"] == "people" and refused["who"]["button"] == "Apply"
        assert "the server refused the settings" in said(refused)
        newest = [r for d in lab.decisions_view(pid, "migration")["days"] for r in d["rows"]][0]
        assert newest["id"] == refused["id"]
        assert newest["decision"] == {"key": "apply_refused", "label": "Not applied: the server refused the settings"}
        assert lab.timeline_entry_view(pid, refused["id"])["after"] == []
        with lab.db() as db:
            press = db.query(ActionRow).order_by(ActionRow.id.desc()).first()
        assert (press.kind, press.detail["accepted"], press.detail["items"]) == ("applied", False, [])
        # the change's own page says the same, and so does the signed file
        assert "Not applied" in lab.history_view(pid, f"change:{w.key}")["lines"][0]["title"]
        evidence = record_walk.download(lab, pid).evidence
        in_file = [a for a in evidence["actions"]["actions"] if a["kind"] == "applied"]
        assert [(a["facts"]["accepted"], a["what"]) for a in in_file] == [
            (True, "Applied a change"),
            (False, "Pressed Apply; the server refused the settings"),
        ]
        assert verifier.check_actions(evidence).ok
    finally:
        lab.stop()


# ---------------------------------------------------------------- a row's history, asked by the row's own id


def test_a_row_of_a_retests_a_proofs_or_a_watch_runs_block_has_the_runs_of_that_block(walked):
    """Checks lists a retest's, a fix proof's and a Change watch run's rows in blocks ("retest-12-on-3",
    "proof-12-in-4", "watch-12-in-4"). Its panel asks the history by that id, and gets the runs of that block."""
    lab, pid = walked.lab, walked.plan_id
    parts = next(g for g in lab.checks_view(pid)["groups"] if g["key"] == "encryption")["parts"]
    seen = {}
    for part, button in (
        ("retests", "Retest now, on Fixes"),
        ("proofs", "Connect demo code"),
        ("changes", "Run the picked tests"),
    ):
        for block in parts[part]["blocks"]:
            for row in block["rows"]:
                history = lab.history_view(pid, f"check:{row['id']}", read=walked.read)
                assert problems(history, models.HistoryView, row["id"]) == [] and history["empty_text"] is None
                assert len(history["lines"]) == row["runs"] >= 1, row["id"]
                newest = history["lines"][0]
                assert newest["result"]["label"] == row["result"]["label"], row["id"]
                assert newest["decided_by"] == words.BY_REVIEWER and history["decides"] == words.WHO_DECIDES
                assert newest["who"]["button"] == button and newest["said"] == f"started by You, with {button}"
                assert opens(lab, pid, newest["link"]) and newest["fingerprint"]
                seen[part] = seen.get(part, 0) + 1
    assert seen["retests"] == 4 and seen["proofs"] == 4 and seen["changes"] >= 2
    # the older ids, which open the newest block's row, are rows of the ledger itself: they are found as before
    for older in ("retest", "proof"):
        row_id = f"{older}-{walked.item['bad_signatures']}"
        assert len(lab.history_view(pid, f"check:{row_id}", read=walked.read)["lines"]) == 1
    with pytest.raises(NotFound):
        lab.history_view(pid, "check:watch-999-in-1", read=walked.read)


def test_a_library_that_nothing_was_run_for_says_what_is_true_of_it(lab):
    w = record_walk.start(lab, "Libraries")
    pid = w.plan_id
    name = "dependencies-demo.cdx.json"
    lab.add_dependency_list(pid, name, (record_walk.DEMO / name).read_bytes())
    rows = {info["row"]["label"]: row_id for row_id, info in lab.ledger(pid)["dependencies"]["rows"].items()}
    # answered from release notes alone: nothing was run, and the history says where its answers come from
    from_notes = lab.history_view(pid, f"library:{rows['openssl 3.0.22']}")
    assert problems(from_notes, models.HistoryView) == [] and from_notes["lines"] == []
    assert from_notes["empty_text"] == words.LIBRARY_FROM_NOTES != words.NO_HISTORY
    assert "release notes" in from_notes["empty_text"] and "Nothing was run" in from_notes["empty_text"]
    # not in the knowledge base: nothing was run, and no source is claimed for it
    unknown = lab.history_view(pid, f"library:{rows['python 3.12.3']}")
    assert unknown["empty_text"] == words.LIBRARY_NOTHING_RUN and "release notes" not in unknown["empty_text"]
    # Results lists a library by "library-<row>": its panel asks by that id and gets the library's history
    by_row = lab.history_view(pid, f"check:library-{rows['openssl 3.0.22']}")
    assert by_row["empty_text"] == words.LIBRARY_FROM_NOTES and by_row["title"] == "History of this library"
    for missing in ("library:row-999", "check:library-row-999"):
        with pytest.raises(NotFound):
            lab.history_view(pid, missing)


@pytest.mark.needs_otto
def test_a_librarys_history_lists_each_decision_on_its_proposal(tmp_path):
    from conftest import demo_plan

    lab = make_lab(tmp_path)
    try:
        plan = demo_plan(lab)
        for version in ("2026.11.1", "2026.11.2"):
            lab.check_pack_updates()
            lab.install_pack(version)
        name = "dependencies-demo.cdx.json"
        lab.add_dependency_list(plan.id, name, (record_walk.DEMO / name).read_bytes())
        rows = {info["row"]["label"]: row_id for row_id, info in lab.ledger(plan.id)["dependencies"]["rows"].items()}
        key = f"library:{rows['python-ecdsa 0.13.2']}"
        proposal = next(
            p for p in lab.otto_proposals(plan.id, ("dependency",)) if p["about"]["library"] == "python-ecdsa"
        )
        # proposed and not decided yet: the proposal has no time of its own, and the history says so
        waiting = lab.history_view(plan.id, key)
        assert [line["title"] for line in waiting["lines"]] == ["Proposed by Otto"] and waiting["empty_text"] is None
        assert waiting["lines"][0]["at"] is None and waiting["lines"][0]["marks"] == ["From Otto"]
        lab.set_decision_name("Kevin")
        lab.otto_decide(plan.id, proposal["id"], "accept")
        lab.otto_decide(plan.id, proposal["id"], "undo")
        history = lab.history_view(plan.id, key)
        assert problems(history, models.HistoryView) == []
        assert [line["title"] for line in history["lines"]] == [
            "Undone: Otto's proposed dependency update",
            "Accepted: Otto's proposed dependency update",
            "Proposed by Otto",
        ]
        assert all(line["who"]["name"] == "Kevin" and line["said"] == "by Kevin" for line in history["lines"][:2])
        # a library nobody decided anything about lists none of them
        other = lab.history_view(plan.id, f"library:{rows['openssl 3.0.22']}")
        assert other["lines"] == [] and other["empty_text"] == words.LIBRARY_FROM_NOTES
    finally:
        lab.stop()


# ---------------------------------------------------------------- an Apply or a Roll back the server refused


def test_an_apply_or_a_roll_back_the_server_refused_never_reads_as_applied(short):
    """Apply is pressed either way. Where the server refused the settings nothing changed, and the change's own page
    says "Not applied: the server refused the settings". The record says the same: such a press is no change to a
    system, and Approvals and decisions does not list it as Applied. (The records of three Applies as the database
    keeps them, laid on the short walk's reading; the migration demo's real one is in the slow set.)"""
    from app.record.entries import Entries

    lab, pid = short.lab, short.plan_id
    reading = copy.copy(short.read.r)
    key, server = "migration:server:localhost:9", "localhost:9"

    def apply(n: int, accepted: bool, back: tuple[int, bool] | None = None) -> dict:
        return {
            "id": n,
            "change_key": key,
            "change_fp": "f" * 64,
            "address": server,
            "try_id": None,
            "request_id": None,
            "accepted": accepted,
            "at": f"2026-11-26T10:0{n}:00.000Z",
            "rollback": {"id": back[0], "accepted": back[1], "at": f"2026-11-26T10:0{n}:30.000Z"} if back else None,
        }

    reading.tries, reading.requests = [], []
    reading.applies = [apply(1, False), apply(2, True, (1, False)), apply(3, True, (2, True))]
    found = Entries(reading)
    refused, taken, not_back, back = (found.by_id[i] for i in ("apply-1", "apply-2", "rollback-1", "rollback-2"))
    assert refused["lead"] == "Not applied:" and refused["title"] == "Not applied"
    assert "Apply was pressed, and the server refused the settings" in words.plain(refused["lead"], refused["rest"])
    assert (refused["kind"], refused["decision"], refused["after"]) == ("people", "apply_refused", [])
    assert (taken["lead"], taken["kind"], taken["decision"]) == ("Applied:", "system", "applied")
    assert not_back["lead"] == "Not rolled back:" and "refused the earlier settings" in not_back["rest"][-1]["v"]
    assert (not_back["kind"], not_back["decision"], not_back["after"]) == ("people", "rollback_refused", [])
    assert (back["lead"], back["kind"], back["decision"]) == ("Rolled back:", "system", "rolled_back")
    # Approvals and decisions: each has its own word, in the page's words
    decisions = lab.decisions_view(pid, read=found)
    assert problems(decisions, models.DecisionsView) == []
    said = {r["id"]: r["decision"] for d in decisions["days"] for r in d["rows"]}
    assert said["apply-1"] == {"key": "apply_refused", "label": "Not applied: the server refused the settings"}
    assert said["rollback-1"] == {
        "key": "rollback_refused",
        "label": "Not rolled back: the server refused the settings",
    }
    labels = [word["label"] for word in said.values()]
    assert labels.count("Applied") == 2 and labels.count("Rolled back") == 1
    # the Timeline: a refused press changed no system, so "Changes to a system" does not hold it
    timeline = lab.timeline_view(pid, kind="system", read=found)
    assert problems(timeline, models.TimelineView) == []
    assert {e["id"] for e in listed(timeline)} == {"apply-2", "apply-3", "rollback-2"}
    story = lab.timeline_entry_view(pid, "apply-1", read=found)
    assert problems(story, models.TimelineEntryDetail) == [] and story["after"] == []
    assert [p["role"] for p in story["people"]] == ["Pressed by"] and story["title"] == "Not applied"
    assert [p["role"] for p in lab.timeline_entry_view(pid, "apply-2", read=found)["people"]] == ["Applied by"]
    # and in the signed file's words
    assert words.action_words("applied", {"accepted": False}) == "Pressed Apply; the server refused the settings"
    assert words.action_words("rolled_back", {"accepted": False}).startswith("Pressed Roll back; the server refused")
    assert words.action_words("applied", {"accepted": True}) == words.action_words("applied") == "Applied a change"


def test_a_runs_link_names_the_page_that_holds_its_row():
    from app.record.reading import run_link

    assert run_link("test-12") == {"page": "evidence", "item": "test-12"}
    assert run_link("retest-12-on-3") == {"page": "evidence", "item": "retest-12-on-3"}  # (Results opens test 12)
    assert run_link("try-tls:localhost:1-try") == {"page": "evidence", "item": "try-tls:localhost:1-try"}
    assert (
        run_link("system-server:localhost:1")["page"] == "evidence" and run_link("library-row-1")["page"] == "evidence"
    )
    for block_row in ("proof-12-in-4", "watch-12-in-4", "watchbase-12-in-4"):
        assert run_link(block_row) == {"page": "checks", "item": block_row}
    assert run_link("proof-12") == {"page": "evidence", "item": "proof-12"}  # (the ledger's own row: Results holds it)


# ---------------------------------------------------------------- before names were kept


def test_what_was_done_before_names_were_kept_says_so_and_nothing_is_filled_in(tmp_path):
    lab = make_lab(tmp_path)
    try:
        w = record_walk.old_walk(lab)
        pid = w.plan_id
        with lab.db() as db:
            from sqlalchemy import func, select

            from app.db import ActionRow, ActionRunRow

            assert (
                db.scalar(select(func.count(ActionRow.id))) == 0 and db.scalar(select(func.count(ActionRunRow.id))) == 0
            )
        view = lab.timeline_view(pid)
        assert problems(view, models.TimelineView) == []
        entries = listed(view)
        # the records are all there: an old assessment has a timeline too. Runs that no record ties are listed one by one.
        kinds = [e["id"].split("-")[0] for e in reversed(entries)]
        assert kinds == [
            "import",
            "start",
            "verify",
            "run",
            "run",
            "run",
            "run",
            "connect",
            "proof",
            "pr",
            "approval",
            "approval",
            "merge",
        ]
        for e in entries:
            if e["id"].startswith("approval-"):
                continue
            assert e["who"] == {
                "name": "Not recorded (before names were kept)",
                "source": "none",
                "source_label": "This was recorded before names were kept",
                "demo": False,
                "recorded": False,
                "button": None,
            }, e["id"]
        # an approval always kept the reviewer's label: that is shown as it was recorded, and nothing more
        assert [
            (e["who"]["name"], e["who"]["source"], e["also"]) for e in entries if e["id"].startswith("approval-")
        ] == [
            ("Demo reviewer A", "reviewer", []),
            ("You", "reviewer", []),
        ]
        alone = [e for e in entries if e["id"].startswith("run-")]
        assert all(
            len(e["runs"]) == 1 and e["lead"] == "Test plan:" and e["decided_by"] == words.BY_REVIEWER for e in alone
        )
        history = lab.history_view(pid, f"test:{w.item['bad_signatures']}")
        assert history["lines"][-2]["said"] == "Who started it: not recorded (before names were kept)"
        story = lab.timeline_entry_view(pid, "merge-1")
        assert [(p["role"], p["who"]["name"]) for p in story["people"]] == [
            ("Merged by", "Not recorded (before names were kept)"),
            ("Approved by", "You"),
            ("Approved as", "Demo reviewer A"),
        ]
        merged = next(r for d in lab.decisions_view(pid)["days"] for r in d["rows"] if r["decision"]["key"] == "merged")
        assert merged["who"]["recorded"] is False and merged["pressed_by"] is None
        # from now on a press is recorded, and what came before stays as it was
        made = lab.export_evidence(pid)
        again = {e["id"]: e["who"]["name"] for e in listed(lab.timeline_view(pid))}
        assert again[f"export-{made['id']}"] == "You" and again["merge-1"] == "Not recorded (before names were kept)"
        assert lab.evidence_files_view(pid)["files"][0]["who"]["name"] == "You"
    finally:
        lab.stop()


# ---------------------------------------------------------------- through the web


def test_the_five_reads_through_the_web(walked):
    from fastapi.testclient import TestClient

    from app.main import create_app

    lab, pid = walked.lab, walked.plan_id
    app = create_app(lab.settings)  # a second app on the walk's own data folder: it only reads here
    with app.state.lab.db() as db:
        from app import auth

        if auth.setup_required(db):
            auth.create_password(db, PASSWORD)
    c = TestClient(app)  # (not started: no demo server and no job runner of its own are needed to read)
    assert c.get(f"/api/plans/{pid}/timeline").status_code == 401
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 200
    timeline = c.get(
        f"/api/plans/{pid}/timeline", params={"area": "fixes", "kind": "people", "q": "pull request"}
    ).json()
    assert timeline["chosen"] == {"area": "fixes", "kind": "people", "q": "pull request"} and timeline["total"] == 4
    assert c.get(f"/api/plans/{pid}/timeline", params={"tz": "Europe/Paris"}).status_code == 200
    assert c.get(f"/api/plans/{pid}/timeline/merge-1").json()["title"] == "Merged pull request #1"
    assert c.get(f"/api/plans/{pid}/decisions", params={"area": "fixes"}).json()["total"] == 3
    assert len(c.get(f"/api/plans/{pid}/evidence-files").json()["files"]) == 2
    assert c.get(f"/api/plans/{pid}/history", params={"key": f"fix:{FIX}"}).json()["title"] == "History of this fix"
    assert c.get(f"/api/plans/{pid}/timeline", params={"area": "elsewhere"}).status_code == 422
    assert c.get(f"/api/plans/{pid}/timeline/no-such-entry").status_code == 404
    assert c.get(f"/api/plans/{pid}/history", params={"key": "fix:none"}).status_code == 404
    assert c.get(f"/api/plans/{pid}/history").status_code == 422
    assert c.get(f"/api/plans/{pid + 1000}/decisions").status_code == 404
    # a time in these reads is an exact moment for the screen to write: no sentence carries one, marked or in words
    marked = c.get(f"/api/plans/{pid}/timeline", headers={"x-evidence-lab-times": "mark"}).json()
    assert "[[time:" not in repr(marked) and ", 2026" not in repr(marked)
