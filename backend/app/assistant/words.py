"""The sentences of the Otto panel that no page already says: the Confirm step, the standing sentences and the marks.

Everything else in the panel is a page's own sentence, repeated. Nothing here words a result.
"""
from __future__ import annotations

TITLE = "Otto"
ON_PAGE = "On this page"
SO_FAR = "This thread so far"
# Phase 6c: one sentence about each page, for "What is this page for?" (the assistant's own words; each says what the
# page holds, never how well anything did).
PAGE_FOR = {
    "overview": "The Overview says where this assessment stands: what was verified, what was tested, what waits for a decision, and the next step.",
    "inventory/import": "Import brings in a scanner file (a CBOM or a CSV). A file is data: nothing in it runs. Its claims are listed here.",
    "inventory/verify": "Verify checks each claim of the file against the real system and says True, False or Couldn't check, with the evidence.",
    "advisories": "Advisories lists published advisories that fit this assessment's programs and libraries, and the checks proposed from them.",
    "checks": "Checks lists every check of this assessment in four groups. The test plan is here, under Encryption tests.",
    "evidence": "Evidence holds every result: what was run, what came back, what it shows and what it doesn't. The signed evidence file is downloaded here.",
    "fixes": "Fixes lists what can be done about a failed result: a change with its proof, or a suggestion in words.",
    "migration/systems": "Systems shows where each system stands on the move to post-quantum cryptography, with its options and its plan.",
    "migration/roadmap": "Roadmap puts the next step of each system in order.",
    "migration/dependencies": "Dependencies lists the libraries a dependency list names, and what is known about each.",
}
# Phase 6b: the text box.
MARK_SAID = "You said"
SAID_LINK = "Open where it led"
BOX_CLOSED = "This assessment is closed. The text box can still take you places and answer the fixed questions. What you type is not kept."
# Why nothing new can start for a plan while its jobs run: the two sentences the server refuses such a click with, word
# for word (`BUSY` in app/lab/testlab.py; a test holds them equal). The panel says the one that applies.
BUSY_TESTS = "Tests are still running. Wait until they have finished."
BUSY_PROOF = "A proof is running in Fixes. Wait until it has finished."
CONFIRM, CANCEL = "Confirm", "Cancel"
MARK_NEXT, MARK_MEANING, MARK_RESULT, MARK_FIX = "Next step", "What this means", "Result", "Fix"

NO_FILE = "Bring in a scanner file to start. Nothing is suggested yet."
NOTHING_HERE = "Nothing is suggested on this page."
NOTHING_WAITING = "Nothing from Otto is waiting for a decision."
SO_FAR_EMPTY = "Nothing has been decided or run in this thread yet."
LOOKING = "Looking at this panel runs nothing. Each button here first shows what it will do and waits for Confirm."

LIVE_OFF, LIVE_ON = "Live Otto is off.", "Live Otto is on."
SETTINGS_LINK = {"label": "Settings", "link": {"page": "settings", "item": None, "section": "live-otto"}}

KIND_WORDS = {"check": ("proposed check", "proposed checks"), "fix": ("proposed fix", "proposed fixes"),
              "plan": ("proposed plan change", "proposed plan changes"),
              "dependency": ("proposed library update", "proposed library updates")}

# What a decision does, and what it does not: the Confirm step of a suggestion.
ACCEPT_LINES = {
    "check": ["Adds this check to the test plan, as “+ Add test” would.", "Runs nothing.", "You can undo it until the check has run."],
    "fix": ["Records your decision to take this fix.", "Runs nothing and changes nothing on any system.",
            "You can undo it until the fix has run or been applied."],
    "plan": ["Adds this to the migration plan as something to fix first.", "Runs nothing and changes nothing on any system.",
             "You can undo it until a newer result of the check passes."],
    "dependency": ["Marks this library “update first”.", "Runs nothing and changes nothing on any system.", "You can undo it at any time."],
}
REJECT_LINES = ["It is not deleted: it stays on the record as “Not added”, with your reason, and can be taken up again later.",
                "Runs nothing."]
UNDO_LINES = {
    "check": ["Takes this check out of the test plan again.", "Runs nothing. The proposal is open for a decision again."],
    "fix": ["Takes your accept back.", "Runs nothing. The proposal is open for a decision again."],
    "plan": ["Takes this off the migration plan again.", "Runs nothing. The proposal is open for a decision again."],
    "dependency": ["Takes the mark “update first” off again.", "Runs nothing. The proposal is open for a decision again."],
}
RECONSIDER_LINES = ["Opens this proposal for a decision again.", "Runs nothing. The earlier decisions stay on the record."]
DECISION_TITLES = {"accept": "Accept this {kind}?", "reject": "Reject this {kind}?", "undo": "Undo this accept?",
                   "reconsider": "Take this {kind} up again?"}
REASON = {"label": "Reason (optional, one short line)", "max": 300}


def status(live: bool) -> dict:
    """The one line under the title: what Settings says about Live Otto, with the way there when it is off."""
    return {"text": LIVE_ON if live else LIVE_OFF, "live": bool(live), "link": None if live else SETTINGS_LINK}


def names_button(button: str, page_label: str) -> str:
    return f"This is the {button} button on {page_label}."


def decision_confirm(kind: str, decision: str, kind_label: str, button: str, page_label: str) -> dict:
    """The Confirm step of one decision on a suggestion: what it does, what it does not, and which button it presses."""
    lines = {"accept": ACCEPT_LINES[kind], "reject": REJECT_LINES, "undo": UNDO_LINES[kind], "reconsider": RECONSIDER_LINES}[decision]
    return {"title": DECISION_TITLES[decision].format(kind=kind_label), "lines": list(lines), "names": names_button(button, page_label),
            "confirm": CONFIRM, "cancel": CANCEL, "reason": dict(REASON) if decision == "reject" else None}


def step_confirm(title: str, lines: list[str], button: str, page_label: str) -> dict:
    """The Confirm step of a next step: what the page's button will do, in a few plain lines."""
    return {"title": title, "lines": [line for line in lines if line], "names": names_button(button, page_label),
            "confirm": CONFIRM, "cancel": CANCEL, "reason": None}


def counted(n: int, kind: str) -> str:
    one, many = KIND_WORDS[kind]
    return f"{n} {one if n == 1 else many}"


def elsewhere_title(n: int) -> str:
    return f"Elsewhere: {n} more"


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
