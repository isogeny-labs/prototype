"""Phase 6a: never more than three panel tabs, and every kind of entry belongs to exactly one of them.

These tests read the one table (app/assistant/threads.py). No Lab is needed."""

import pytest

from app.assistant import engine, threads


def test_there_are_three_threads_and_no_fourth():
    assert threads.THREADS == ("testing", "fixing", "planning")
    assert set(threads.THREAD_LABELS) == set(threads.THREADS)
    assert [threads.THREAD_LABELS[t] for t in threads.THREADS] == ["Testing", "Fixing", "Planning"]


def test_every_kind_of_entry_maps_to_exactly_one_of_the_three_threads():
    for kind, thread in threads.ENTRY_KINDS.items():
        if thread == "page":
            # a next step that only opens a page belongs to the page it opens (the Overview has no thread)
            assert {threads.thread_of(kind, page) for page in threads.PAGES} <= set(threads.THREADS) | {None}, kind
            assert threads.thread_of(kind, "overview") is None
        else:
            assert thread in threads.THREADS, f"{kind} is filed under a fourth thread: {thread}"
            assert threads.thread_of(kind) == thread


def test_every_page_of_an_assessment_has_its_thread_and_the_overview_has_none():
    assert set(threads.PAGE_THREAD) == set(threads.PAGES) == set(threads.PAGE_LABELS)
    assert threads.PAGE_THREAD["overview"] is None
    assert {p for p, t in threads.PAGE_THREAD.items() if t == "testing"} == {
        "inventory/import",
        "observatory",  # the design refactor (26 November 2026): the map of the systems, under Observe
        "inventory/verify",
        "advisories",
        "checks",
        "evidence",
        "change-watch",
    }
    assert {p for p, t in threads.PAGE_THREAD.items() if t == "fixing"} == {"fixes", "migration/dependencies"}
    assert {p for p, t in threads.PAGE_THREAD.items() if t == "planning"} == {"migration/systems", "migration/roadmap"}
    # The three views of Evidence that only read the record keep the tab you had, as the Overview does.
    assert {p for p, t in threads.PAGE_THREAD.items() if t is None} == {
        "overview",
        "evidence/timeline",
        "evidence/decisions",
        "evidence/files",
    }


def test_each_kind_of_proposal_arrives_in_one_thread_and_fits_the_pages_the_plan_names():
    from app.otto import proposals

    assert set(threads.KIND_THREAD) == set(proposals.KINDS)
    assert threads.KIND_THREAD == {"check": "testing", "fix": "fixing", "dependency": "fixing", "plan": "planning"}
    for kind in proposals.KINDS:
        assert threads.ENTRY_KINDS[f"suggestion:{kind}"] == threads.KIND_THREAD[kind]
        # a proposal fits the page it lives on (the one with its own buttons); a check also fits Checks
        assert kind in threads.FITS[proposals.HOME[kind]]
        # ... and every page it fits is a page of its own thread
        assert {threads.PAGE_THREAD[page] for page, kinds in threads.FITS.items() if kind in kinds} == {
            threads.KIND_THREAD[kind]
        }
    assert threads.FITS["checks"] == ("check",) and threads.FITS["migration/roadmap"] == ("plan",)
    # no suggestion fits Import, Verify, Evidence or the Overview
    assert not set(threads.FITS) & {"overview", "inventory/import", "inventory/verify", "evidence"}


def test_an_entry_of_a_kind_that_is_not_in_the_table_cannot_be_made():
    with pytest.raises(ValueError):
        engine._entry("suggestion:watch", "x", mark="From Otto", title="A fourth kind")
    with pytest.raises(ValueError):
        engine._entry("answer", "x", mark="Answer", title="Not in phase 6a")
    made = engine._entry("next:run_all", "next:run_all", mark="Next step", title="Run all")
    assert made["thread"] == "testing" and made["kind"] == "next" and made["what"] == "next:run_all"
