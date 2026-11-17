"""The four work groups (phase 5b), the same on Checks, Evidence, Fixes and the Overview, and how an item's state is
counted (Open, In progress, Done). The counts decide nothing: they sort what the pages already say."""
from __future__ import annotations

from typing import Iterable

# (key, label, the question it answers), in the one order every page uses.
GROUPS: tuple[tuple[str, str, str], ...] = (
    ("verification", "Verification", "Is the scanner file true?"),
    ("encryption", "Encryption tests", "Is the encryption built right?"),
    ("migration", "Migration", "Where does each system stand on the move to post-quantum, and what must change?"),
    ("dependencies", "Dependencies", "What can your libraries do?"),
)
GROUP_LABELS = {key: label for key, label, _ in GROUPS}
GROUP_KEYS = tuple(key for key, _, _ in GROUPS)

STATE_LABELS = {"open": "Open", "in_progress": "In progress", "done": "Done"}

# Said in a group with nothing in it, so it never just disappears.
EMPTY_CHECKS = {
    "verification": "Nothing verified yet. Verify claims is on Import.",
    "encryption": "No test has run yet. The test plan is on Checks.",
    "migration": "Nothing measured yet. Measure status is on Migration.",
    "dependencies": "No dependency list yet. Add one on Dependencies.",
}
EMPTY_DEPENDENCIES_LISTED = "No library has been measured on a public copy yet. Measure on a public copy is on Dependencies."
EMPTY_FIXES = {
    "verification": ("Verification has no fixes of its own. A false claim's fix sits with the test that checks it, "
                     "under Encryption tests."),
    "encryption": "No failed test has a fix.",
    "migration": "No system's plan needs a change yet.",
    "dependencies": "No library blocks a track.",
}
# Where the checks of a group are started (each group heading links there).
STARTED_ON = {
    "verification": {"label": "Started on Import", "page": "inventory/import"},
    "encryption": {"label": "The test plan is here", "page": "checks"},
    "migration": {"label": "Started on Migration", "page": "migration/systems"},
    "dependencies": {"label": "Started on Dependencies", "page": "migration/dependencies"},
}

# A fix's status word (exactly as the Fixes view shows it), sorted into the three counts (Kevin's decision 8,
# 17 November 2026). "Applied · matches the try" was not named in the plan: it is applied and not yet measured in
# place, so it counts as in progress.
FIX_STATE_BY_WORD = {
    "Code not connected": "open", "Text only": "open", "Ready to try": "open", "Ready to download": "open",
    "Proof failed": "open", "Try did not pass": "open", "Rolled back": "open",
    "Proving": "in_progress", "Ready for review": "in_progress", "Waiting for approval": "in_progress",
    "Ready to merge": "in_progress", "Try running": "in_progress", "Try passed": "in_progress",
    "Ready to apply": "in_progress", "Applied · measuring": "in_progress", "Applied · does not match the try": "in_progress",
    "Applied · matches the try": "in_progress",
    "Merged": "done", "In place (measured)": "done",
}


def fix_state(word: str) -> str:
    """Open, in progress or done for a fix's status word. An unknown word counts as open (nothing is called done
    without its word saying so)."""
    return FIX_STATE_BY_WORD.get(word, "open")


def group_of_fix(fix: dict) -> str:
    """The group of the work a fix came from (a fix state from `fix_states`)."""
    if fix.get("source_kind") == "dependency" or fix.get("test_kind") == "capability" or str(fix.get("id", "")).startswith("dependency-"):
        return "dependencies"
    if fix.get("source_kind") == "migration":
        return "migration"
    return "encryption"   # a failed test's fix: the code change, a server setting, a library's fixed version


def group_of_change(change_key: str | None) -> str:
    """A change's group: the Acme Pay server's TLS change came from a failed test; every other change is the migration
    plan's."""
    return "encryption" if str(change_key or "").startswith("tls") else "migration"


def counts(states: Iterable[str]) -> dict:
    out = {"open": 0, "in_progress": 0, "done": 0}
    for s in states:
        out[s if s in out else "open"] += 1
    return out


def group_frame(key: str) -> dict:
    """The fixed part of a group heading: its key, label and question."""
    return {"key": key, "label": GROUP_LABELS[key], "question": next(q for k, _, q in GROUPS if k == key)}
