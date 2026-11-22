"""The words of the Sandbox research block in Settings (prototype, 22 November 2026). Words only."""

from __future__ import annotations

from app.config import SANDBOX_ENV
from app.otto import model

TITLE = "Sandbox research (prototype)"
INTRO = (
    "A prototype for Isogeny's own sandbox. While it is on, the app looks for published weaknesses in the libraries your files "
    "name by itself, and a test can be designed and proven on public copies of a library that are fetched from its public "
    "package registry. Nothing is added to an assessment without your Accept."
)
SWITCH_LABEL = "Sandbox research"
BY_ITSELF_LABEL = "Design and prove tests by itself"
RUN_LIMIT_LABEL = "Most to spend in one research run (US dollars)"
DAY_LIMIT_LABEL = "Most to spend in a day (US dollars)"

NOT_MARKED = (
    "This computer is not marked as Isogeny's own sandbox: the " + SANDBOX_ENV + " setting is not set where the app "
    "starts. Sandbox research can be turned on only there."
)
NEEDS_ISOLATED = "It needs isolated mode"  # followed by the mode's own plain reason, as a sentence
NEEDS_OTTO = "It needs Otto's harness, and Otto is not installed on this computer."
BY_ITSELF_NEEDS_SWITCH = "This can be ticked only while Sandbox research is on."
BY_ITSELF_NEEDS_LIVE = "This can be ticked only while Live Otto is on."

# The box that opens before the switch is turned on. Nothing starts before the click in it.
BOX_TITLE = "Turn on Sandbox research?"
BOX_LINES = (
    "While it is on, the app looks for published weaknesses in the libraries your files name by itself, about once a day. "
    "This sends each library's name and where it is published, and nothing else.",
    "For a weakness with a fix, public copies of the library can be fetched from its public package registry and run in "
    "locked containers on this computer, with no network.",
    'Designing and proving a test still starts on a click, unless "' + BY_ITSELF_LABEL + '" is ticked.',
    "Nothing is added to an assessment without your Accept.",
)
BY_ITSELF_LINE = (
    "Uses Claude, within the limit for one run and the limit for a day. A proven test is proposed; you accept or reject it. "
    "A test pack such a run makes is installed without a click of its own, as the pack of a run you start is."
)
LIMITS_NOTE = (
    "A run is one research command. Each call's cost is added up from the tokens the API reports, and a request that could "
    "pass a limit is not sent. When the day's limit is reached, no run starts by itself until the next day."
)


def day_reached(next_at: str | None) -> str:
    """Said on Advisories and on the Watch list when the limit for a day leaves nothing for a run that asks Claude."""
    from app.present.otto import stamp

    return "Today's spending limit is reached." + (
        f" The next run can start after {stamp(next_at)}."
        if next_at
        else " Raise the limit for a day in Settings to start a run."
    )


def research_line(*, runs: int, by_itself: bool, spent_nano: int, day_limit_nano: int, reached: str | None) -> str:
    how = (
        "A research run starts by itself when a weakness with a fix can be tried."
        if by_itself
        else "A research run starts on a click (Design and prove tests)."
    )
    count = f"{runs} research {'run' if runs == 1 else 'runs'} in the last 24 hours"
    return (
        f"Sandbox research is on. {how} {count}; {dollars(spent_nano)} of {dollars(day_limit_nano)} US dollars spent on Claude in that time."
        + (f" {reached}" if reached else "")
    )


def dollars(nano: int) -> str:
    return f"{nano / model.NANO:.2f}"


def status_line(on: bool, by_itself: bool, blocked: list[str]) -> str:
    if not on:
        return (
            (
                "Sandbox research is off. The app behaves as it did before: nothing is looked for by itself, and only the pinned public "
                "copies can run."
            )
            if not blocked
            else "Sandbox research is off, and can't be turned on here."
        )
    if by_itself:
        return (
            "Sandbox research is on. The app looks for published weaknesses by itself, and designs and proves tests by itself "
            "within the spending limits. Every proposal waits for your Accept."
        )
    return (
        "Sandbox research is on. The app looks for published weaknesses by itself. Designing and proving a test starts on a "
        "click (Design and prove tests, on Advisories)."
    )


def spent_line(spent_nano: int, day_limit_nano: int) -> str:
    return f"{dollars(spent_nano)} of {dollars(day_limit_nano)} US dollars spent on research runs in the last 24 hours."


def section(
    *,
    on: bool,
    by_itself: bool,
    blocked: list[str],
    live_ready: bool,
    run_limit_nano: int,
    day_limit_nano: int,
    spent_nano: int,
) -> dict:
    can = not blocked
    tick_reason = None if (on and live_ready) else (BY_ITSELF_NEEDS_SWITCH if not on else BY_ITSELF_NEEDS_LIVE)
    return {
        "title": TITLE,
        "intro": INTRO,
        "switch": {"label": SWITCH_LABEL, "on": on, "can_turn_on": can, "blocked_reasons": list(blocked)},
        "box": {"title": BOX_TITLE, "lines": list(BOX_LINES), "confirm": "Turn on", "cancel": "Cancel"},
        "by_itself": {
            "label": BY_ITSELF_LABEL,
            "on": by_itself,
            "can_turn_on": tick_reason is None,
            "blocked_reason": tick_reason,
            "line": BY_ITSELF_LINE,
        },
        "run_limit": {"label": RUN_LIMIT_LABEL, "value": dollars(run_limit_nano), "save": "Save"},
        "day_limit": {"label": DAY_LIMIT_LABEL, "value": dollars(day_limit_nano), "save": "Save"},
        "limits_note": LIMITS_NOTE,
        "status_line": status_line(on, by_itself, blocked),
        "spent_line": spent_line(spent_nano, day_limit_nano) if on else None,
    }
