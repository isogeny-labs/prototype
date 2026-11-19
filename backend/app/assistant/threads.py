"""The panel's three threads, and the one table that says where every kind of entry belongs.

Never more than three tabs: Testing, Fixing and Planning. A page belongs to one thread (the Overview to none), and
every kind of entry the panel can hold is one line of `ENTRY_KINDS`, with its one thread. A test walks that table and
fails on a fourth thread, and the engine refuses to build an entry whose kind is not in it.
"""
from __future__ import annotations

THREADS = ("testing", "fixing", "planning")
THREAD_LABELS = {"testing": "Testing", "fixing": "Fixing", "planning": "Planning"}

PAGES = ("overview", "inventory/import", "inventory/verify", "advisories", "checks", "evidence", "fixes", "change-watch",
         "migration/systems", "migration/roadmap", "migration/dependencies")
# (as the sidebar names them)
PAGE_LABELS = {"overview": "Overview", "inventory/import": "Import", "inventory/verify": "Verify", "advisories": "Advisories",
               "checks": "Checks", "evidence": "Evidence", "fixes": "Fixes", "change-watch": "Change watch", "migration/systems": "Systems",
               "migration/roadmap": "Roadmap", "migration/dependencies": "Dependencies"}
# The thread whose tab a page selects. The Overview has no thread of its own: it keeps the tab you had.
PAGE_THREAD: dict[str, str | None] = {
    "overview": None,
    "inventory/import": "testing", "inventory/verify": "testing", "advisories": "testing", "checks": "testing", "evidence": "testing",
    "change-watch": "testing",      # phase 6d: the tests picked for a developer's change, and their runs
    "fixes": "fixing", "migration/dependencies": "fixing",
    "migration/systems": "planning", "migration/roadmap": "planning",
}
# Which kinds of Otto's proposals fit a page. A proposal lives on one page (the one with its own buttons) and can fit
# a second one: a proposed check lives on Advisories and also fits Checks, which holds the test plan it would join.
FITS: dict[str, tuple[str, ...]] = {
    "advisories": ("check",), "checks": ("check",), "fixes": ("fix",), "migration/dependencies": ("dependency",),
    "migration/systems": ("plan",), "migration/roadmap": ("plan",),
}
# A proposal's kind and the thread it arrives in.
KIND_THREAD = {"check": "testing", "fix": "fixing", "dependency": "fixing", "plan": "planning"}

# Every kind of entry, and its one thread. "page": the thread of the page the entry's button is on (a next step that
# only opens a page belongs to the page it opens; where that is the Overview it has no thread, and opens no tab).
ENTRY_KINDS: dict[str, str] = {
    # a suggestion: one of Otto's proposals, undecided or decided
    "suggestion:check": "testing", "suggestion:fix": "fixing", "suggestion:dependency": "fixing", "suggestion:plan": "planning",
    # a next step: a button of a page, under that button's own name
    "next:verify": "testing", "next:run": "testing", "next:run_all": "testing", "next:retest": "testing",
    "next:connect": "fixing", "next:run_proof_again": "fixing", "next:open_pull_request": "fixing", "next:retest_now": "fixing",
    "next:try": "fixing", "next:ask_approval": "fixing", "next:measure_library": "fixing", "next:measure_all": "fixing",
    "next:measure_status": "planning",
    "next:open": "page",
    # what this means: a result's own plain sentence
    "meaning:found": "testing", "meaning:result": "testing", "meaning:text_only": "fixing", "meaning:blocks": "fixing",
    # the thread so far: a reviewed result, and where a fix stands
    "result": "testing", "fix_step": "fixing",
    # phase 6b: something a person typed, with Otto's answer. It is filed under one thread when it is said (the thread
    # of what it named, or of the page it was typed beside); "said:testing" and so on are that record's own word.
    "said:testing": "testing", "said:fixing": "fixing", "said:planning": "planning",
}


def thread_of(kind: str, page: str | None = None) -> str | None:
    """The one thread an entry of this kind belongs to (None: no thread, for a next step that opens the Overview)."""
    thread = ENTRY_KINDS[kind]
    if thread == "page":
        return PAGE_THREAD.get(page or "overview")
    return thread
