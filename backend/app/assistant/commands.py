"""Phase 6b: commands. The one list of what a person can tell Otto, and the fixed rules that read a typed sentence.

Nothing in this file decides, runs or changes anything, and no model is asked. A sentence is read into one line of the
list and the pieces of the sentence that fill it:

    moving around      a page, a filtered table, one item, a tab of the panel, "what can you do?": answered with where
                       to go. The browser goes there at once.
    a decision or a    answered with the card of phase 6a for that suggestion or that button, with its Confirm step.
    start              Nothing is sent until the person presses Confirm, and Confirm sends the page button's own request.
    done on its page   Approve, Merge pull request, Apply, Roll back, Close and sign off, the "I own this system" tick,
    only               a migration option, Mark reviewed, a download, Settings: the command opens the page and says so.

No guessing: where several things fit the words, the answer is "Which one?" with the list; where none fits, it is
"I can't do that." with what can be said on this page. A reason that rides along with a reject is cut from the
person's own words and never rewritten.
"""

from __future__ import annotations

import re
from typing import Any

from app.assistant import words
from app.assistant.threads import KIND_THREAD, PAGE_LABELS, PAGE_THREAD, PAGES, THREAD_LABELS, THREADS

MAX_TEXT = 500
MAX_OPTIONS = 8

# ------------------------------------------------------------------ the one list
# kind "go": moving around, done at once. "do": a decision or a start, answered with a card and its Confirm step.
# "page": done on its page only. `say` is an example a person could type (the chips and "What can you do?" show it).
COMMANDS: tuple[dict[str, Any], ...] = (
    {"key": "help", "kind": "go", "say": "What can you do?", "about": "Lists what you can tell Otto here."},
    {"key": "open_page", "kind": "go", "say": "Open Evidence", "about": "Opens a page of this assessment."},
    {"key": "filter", "kind": "go", "say": "Show failed checks", "about": "Opens a page with its table filtered."},
    {
        "key": "open_item",
        "kind": "go",
        "say": "Open the Java fix",
        "about": "Opens one suggestion, test or fix on its page.",
    },
    {"key": "tab", "kind": "go", "say": "Close the Fixing tab", "about": "Opens or closes a tab of this panel."},
    # phase 6e, first half: a what-if is answered from what the app knows, at once; it runs nothing
    {
        "key": "what_if",
        "kind": "go",
        "say": "What if I update elliptic to 6.5.7?",
        "about": "Shows what the app knows about that update, and what it does not. It runs nothing.",
    },
    {
        "key": "accept",
        "kind": "do",
        "say": "Accept the Java fix",
        "about": "Shows the suggestion's card. Accept waits for Confirm.",
    },
    {
        "key": "reject",
        "kind": "do",
        "say": "Reject the Java fix: not this quarter",
        "about": "Shows the suggestion's card with your reason filled in. Reject waits for Confirm.",
    },
    {"key": "undo", "kind": "do", "say": "Undo the Java fix", "about": "Shows the card. Undo waits for Confirm."},
    {
        "key": "reconsider",
        "kind": "do",
        "say": "Reconsider the Java fix",
        "about": "Shows the card. Reconsider waits for Confirm.",
    },
    {"key": "verify", "kind": "do", "say": "Verify claims", "what": "next:verify", "page": "inventory/import"},
    {"key": "run_all", "kind": "do", "say": "Run all", "what": "next:run_all", "page": "checks"},
    {"key": "run", "kind": "do", "say": "Run the speed test", "what": "next:run", "page": "checks"},
    {"key": "retest", "kind": "do", "say": "Retest on 1.4.3", "what": "next:retest", "page": "evidence"},
    {
        "key": "run_picked_tests",
        "kind": "do",
        "say": "Run the picked tests",
        "what": "next:run_picked_tests",
        "page": "change-watch",
    },
    {"key": "connect", "kind": "do", "say": "Connect demo code", "what": "next:connect", "page": "fixes"},
    {"key": "run_proof_again", "kind": "do", "say": "Run proof again", "what": "next:run_proof_again", "page": "fixes"},
    {
        "key": "open_pull_request",
        "kind": "do",
        "say": "Open pull request",
        "what": "next:open_pull_request",
        "page": "fixes",
    },
    {"key": "retest_now", "kind": "do", "say": "Retest now", "what": "next:retest_now", "page": "fixes"},
    {"key": "try", "kind": "do", "say": "Try on a test copy", "what": "next:try", "page": "fixes"},
    {"key": "ask_approval", "kind": "do", "say": "Ask for approval", "what": "next:ask_approval", "page": "fixes"},
    {
        "key": "measure_status",
        "kind": "do",
        "say": "Measure status",
        "what": "next:measure_status",
        "page": "migration/systems",
    },
    {
        "key": "measure_all",
        "kind": "do",
        "say": "Measure all",
        "what": "next:measure_all",
        "page": "migration/dependencies",
    },
    {
        "key": "measure_library",
        "kind": "do",
        "say": "Measure elliptic",
        "what": "next:measure_library",
        "page": "migration/dependencies",
    },
    {"key": "approve", "kind": "page", "say": "Approve", "page": "fixes", "done": "Approving is done on the page."},
    {
        "key": "merge",
        "kind": "page",
        "say": "Merge pull request",
        "page": "fixes",
        "done": "Merging is done on the page.",
    },
    {"key": "apply", "kind": "page", "say": "Apply", "page": "fixes", "done": "Applying a change is done on the page."},
    {
        "key": "roll_back",
        "kind": "page",
        "say": "Roll back",
        "page": "fixes",
        "done": "Rolling back is done on the page.",
    },
    {
        "key": "sign_off",
        "kind": "page",
        "say": "Close and sign off",
        "page": "overview",
        "done": "Closing and signing off is done on the page.",
    },
    {
        "key": "own_tick",
        "kind": "page",
        "say": "I own this system",
        "page": "inventory/import",
        "done": "The “I own this system” tick is yours to make, on Import.",
    },
    {
        "key": "choose_option",
        "kind": "page",
        "say": "Choose a migration option",
        "page": "migration/systems",
        "done": "Choosing a migration option is done on the page.",
    },
    {
        "key": "mark_reviewed",
        "kind": "page",
        "say": "Mark reviewed",
        "page": "evidence",
        "done": "Marking a result reviewed is done on the page.",
    },
    {
        "key": "download",
        "kind": "page",
        "say": "Download evidence",
        "page": "evidence",
        "done": "A download is started on the page.",
    },
    {
        "key": "bring_in_demo_change",
        "kind": "page",
        "say": "Bring in a demo change",
        "page": "change-watch",
        "done": "Bringing in a demo change is done on the page.",
    },
    {
        "key": "settings",
        "kind": "page",
        "say": "Turn on Live Otto",
        "page": "settings",
        "done": "Settings are changed in Settings.",
    },
)
BY_KEY = {c["key"]: c for c in COMMANDS}
DECISIONS = ("accept", "reject", "undo", "reconsider")

# Up to three examples fitted to a page (a chip sends its own words). The last one is the same everywhere.
HELP = "What can you do?"
CHIPS: dict[str, tuple[str, ...]] = {
    "overview": ("Open Checks", "Show failed checks", HELP),
    "inventory/import": ("Verify claims", "Open Checks", HELP),
    "inventory/verify": ("Open Checks", "Show failed checks", HELP),
    "advisories": ("Show proposed checks", "Open Checks", HELP),
    "checks": ("Show failed checks", "Run all", HELP),
    "observatory": ("Verify claims", "Open Checks", HELP),
    "evidence": ("Show failed results", "Open Fixes", HELP),
    "evidence/timeline": ("Open Evidence", "Show failed checks", HELP),
    "evidence/decisions": ("Open Evidence", "Open Fixes", HELP),
    "evidence/files": ("Open Evidence", "Open Checks", HELP),
    "fixes": ("Connect demo code", "Show failed checks", HELP),
    "change-watch": ("Run the picked tests", "Open Fixes", HELP),
    "migration/systems": ("Measure status", "Open Roadmap", HELP),
    "migration/roadmap": ("Open Systems", "Open Dependencies", HELP),
    "migration/dependencies": ("Measure all", "Open Systems", HELP),
}
BOX = {"label": "Ask Otto, or tell it what to do", "send": "Send", "max": MAX_TEXT}

# ------------------------------------------------------------------ the words the rules know
PAGE_WORDS: dict[str, str] = {
    "overview": "overview",
    "home": "overview",
    "start": "overview",
    "inventory": "inventory/import",
    "file": "inventory/import",
    "scanner file": "inventory/import",
    "verify": "inventory/verify",
    "claims": "inventory/verify",
    "verification": "inventory/verify",
    "advisories": "advisories",
    "advisory": "advisories",
    "checks": "checks",
    "tests": "checks",
    "test plan": "checks",
    "plan": "checks",
    "evidence": "evidence",
    "results": "evidence",
    "evidence lab": "evidence",
    "observatory": "observatory",
    "map": "observatory",
    "the map": "observatory",
    "timeline": "evidence/timeline",
    "history": "evidence/timeline",
    "approvals": "evidence/decisions",
    "decisions": "evidence/decisions",
    "approvals and decisions": "evidence/decisions",
    "evidence files": "evidence/files",
    "fixes": "fixes",
    "fix": "fixes",
    "change watch": "change-watch",
    "changes": "change-watch",
    "developer changes": "change-watch",
    "systems": "migration/systems",
    "migration": "migration/systems",
    "migration plan": "migration/systems",
    "roadmap": "migration/roadmap",
    "dependencies": "migration/dependencies",
    "libraries": "migration/dependencies",
    "dependency list": "migration/dependencies",
}
# Every page is also known by the last word of its own address (Import, Verify, Systems, ...). Worked out here, not
# written out: the app's source is scanned for the words of a container command, and a page's name is not one.
PAGE_WORDS.update({page.rsplit("/", 1)[-1]: page for page in PAGES})
# What a table can be filtered by, as a person says it, and the page's own word for it. The pages with these filters in
# their address: Checks (result, where a check came from), Evidence (result) and Advisories (decision).
RESULT_WORDS: dict[str, str] = {
    "failed": "Failed",
    "failing": "Failed",
    "fail": "Failed",
    "broken": "Failed",
    "passed": "Passed",
    "passing": "Passed",
    "pass": "Passed",
    "true": "True",
    "false": "False",
    "couldn't check": "Couldn't check",
    "couldnt check": "Couldn't check",
    "could not check": "Couldn't check",
    "unchecked": "Couldn't check",
    "not checked": "Couldn't check",
    "inconclusive": "Couldn't check",
}
# The value each page's own Result filter uses for a result word (Checks filters by the word itself, Evidence by its code).
RESULT_VALUES: dict[str, dict[str, str]] = {
    "checks": {
        "Failed": "Failed",
        "Passed": "Passed",
        "True": "True",
        "False": "False",
        "Couldn't check": "Couldn't check",
    },
    "evidence": {"Failed": "failed", "Passed": "passed"},
}
DECISION_WORDS: dict[str, str] = {
    "proposed": "proposed",
    "undecided": "proposed",
    "waiting": "proposed",
    "accepted": "accepted",
    "rejected": "rejected",
    "not added": "rejected",
    "declined": "rejected",
}
# (the Decision control's own words on Advisories)
DECISION_LABELS = {"proposed": "Proposed", "accepted": "Added", "rejected": "Not added"}
FROM_WORDS: dict[str, tuple[str, str]] = {
    "retests": ("retest", "Retest"),
    "retest": ("retest", "Retest"),
    "fix proofs": ("proof", "Fix proof"),
    "proofs": ("proof", "Fix proof"),
    "tries": ("try", "Try on a test copy"),
}
# What a table holds, as a person says it: the page, and what one row of it is called.
THING_WORDS: dict[str, tuple[str, str]] = {
    "checks": ("checks", "check"),
    "check": ("checks", "check"),
    "tests": ("checks", "check"),
    "test": ("checks", "check"),
    "results": ("evidence", "result"),
    "result": ("evidence", "result"),
    "evidence": ("evidence", "result"),
    "advisories": ("advisories", "advisory"),
    "advisory": ("advisories", "advisory"),
    "suggestions": ("advisories", "advisory"),
    "proposals": ("advisories", "advisory"),
}
# The words that say which kind of suggestion is meant. A "fix" can be a fix on Fixes or a library update on Dependencies.
KIND_WORDS: dict[str, tuple[str, ...]] = {
    "fix": ("fix", "dependency"),
    "fixes": ("fix", "dependency"),
    "update": ("fix", "dependency"),
    "upgrade": ("fix", "dependency"),
    "check": ("check",),
    "test": ("check",),
    "advisory": ("check",),
    "plan": ("plan",),
    "change": ("fix", "plan"),
    "suggestion": ("check", "fix", "plan", "dependency"),
    "proposal": ("check", "fix", "plan", "dependency"),
}
# Everyday names for what the app calls something else.
ALIASES: dict[str, tuple[str, ...]] = {
    "java": ("openjdk",),
    "jdk": ("openjdk",),
    "python": ("python-ecdsa",),
    "ecdsa": ("python-ecdsa",),
    "pq": ("post-quantum",),
    "pqc": ("post-quantum",),
    "speed": ("speed",),
    "tls": ("tls",),
}
_FOR = r"(?: (?:for|on|of|to|in) (?P<rest>.+))?"
# The buttons a command can name, in the order the rules try them (the general "run <a test>" comes last).
STARTS: tuple[tuple[str, str], ...] = (
    ("run_picked_tests", r"(?:run|start|rerun)(?: the| its| their)? picked tests(?: again)?" + _FOR),
    ("run_picked_tests", r"(?:run|start|rerun)(?: the)? tests picked" + _FOR),
    (
        "run_all",
        r"(?:run|start|rerun) (?:all|everything|every test|all (?:the )?(?:tests|checks)|the (?:whole )?(?:test )?plan|the tests|the checks)(?: again)?",
    ),
    ("verify", r"(?:verify|check)(?: the)?(?: claims| file)?"),
    ("retest_now", r"retest now" + _FOR),
    ("retest", r"retest(?: new version| a new version| another version)?(?: (?:on|with|to|against|at) (?P<rest>.+))?"),
    ("connect", r"connect(?: the)?(?: demo)? code" + _FOR),
    ("run_proof_again", r"(?:(?:run|start)(?: the)? proof again|prove(?: it)? again|rerun the proof)" + _FOR),
    ("open_pull_request", r"open(?: a| the)? pull request" + _FOR),
    ("try", r"try(?: it| this| the change| the fix)?(?: again)?(?: on a test copy| out)?" + _FOR),
    ("try", r"try (?P<rest>.+?)(?: again)?(?: on a test copy| out)?"),
    ("ask_approval", r"ask for(?: an)? approval" + _FOR),
    ("measure_status", r"measure(?: the)? status|measure again|measure(?: the)? systems"),
    ("measure_all", r"measure (?:all|everything|every library|all (?:the )?libraries|the libraries)"),
    ("measure_library", r"measure (?P<rest>.+?)(?: on (?:a|its) public copy)?"),
    ("run", r"(?:run|start|rerun)(?: again)? (?P<rest>.+?)(?: again)?"),
)
ORDINALS = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "last": -1,
}
SKIP = {
    "the",
    "a",
    "an",
    "this",
    "that",
    "it",
    "its",
    "my",
    "our",
    "of",
    "for",
    "to",
    "on",
    "in",
    "at",
    "from",
    "with",
    "and",
    "please",
    "one",
    "me",
    "all",
    "only",
    "just",
    "now",
    "again",
    "page",
    "tab",
    "otto",
    "s",
}
POLITE = re.compile(
    r"^(?:(?:hey|hi|ok|okay)\s+)?(?:otto[,:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:i\s+(?:want|would\s+like|need)\s+to\s+)?(?:let'?s\s+)?"
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
_GREETING = re.compile(r"(?i)^\s*(?:(?:hey|hi|ok|okay)\s+)?otto\s*[:,]\s*")
_PLEASE = re.compile(r"[ ,]+please$")
_WHAT_IF = re.compile(
    r"(?:(?:and |so |ok |okay )?(?:what (?:would |will |could |does )?(?:happens?|changes?|breaks?)? ?if|what if|what about if|if|suppose|say) )"
    r"(?:i|we|you|someone|somebody|the team) "
    r"(?:were to |would |do |did |could |can )?(?:updated?|upgraded?|moved?|bump(?:ed)?|switch(?:ed)?|change[d]?|go|went) "
    r"(?:the |my |our )?(?P<library>[a-z0-9@][a-z0-9@._/+-]{0,79}?)(?: library| package)?"
    # (a version starts with a digit: "to the newest version" names none, and is not read as a what-if)
    r"(?: from (?:version )?v?[0-9][0-9a-z.+_-]{0,39})? (?:to|up to|onto) (?:version )?v?(?P<version>[0-9][0-9a-z.+_-]{0,39})"
    r"(?:[ ,;:?!].{0,300})?"
)

# A second "to <version>" after the first one, joined by any word ("and", "then", "or", "&", "/", "with" ...): a version
# with a dot ("to 0.13.3"), or a bare number where the sentence ends or goes on to another clause ("and java to 18?").
# "the move to 2027 plans" and "up to 3 years" are no second update (the review of 19 November 2026).
_SECOND_UPDATE = re.compile(
    r"\b(?:to|onto) (?:version )?v?(?:\d+\.\d|\d+(?=\s*(?:[?!.,;:]|$)|\s+(?:and|or|then|plus|too|also)\b))"
)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("’", "'").replace("'s", " "))


def sayable(title: str) -> str:
    """A title as a sentence can carry it. In a typed sentence the first colon starts a reason, so a title is said
    without its colons ("Advisory check: Blank signature accepted" as "Advisory check Blank signature accepted"): the
    words are the same, and `match` finds the one thing that is called exactly that."""
    return " ".join(str(title).replace(":", " ").split())


# ------------------------------------------------------------------ reading a sentence


def read(text: str) -> dict:
    """One typed sentence as a line of the list and its pieces: {"key", ...}. `key` is None when no rule reads it.
    Only fixed rules: the same sentence always reads the same."""
    plain = " ".join(str(text or "").replace("’", "'").split())[:MAX_TEXT]
    if not plain:
        return {"key": None, "said": ""}
    # A reason rides along after the first colon. It is the person's own words, as typed. ("Otto: run all" greets with
    # a colon: that one is not the start of a reason.)
    head, _, tail = _GREETING.sub("", plain).partition(":")
    low = _PLEASE.sub("", POLITE.sub("", head.strip().lower()).strip(" .!?"))
    reason = tail.strip() or None
    said = {"said": plain}

    if re.fullmatch(
        r"(what can (you|i|we) do( here| on this page| for me)?|help|commands|what can i say|what can i tell you)", low
    ):
        return {**said, "key": "help"}
    # Phase 6c: one of the six fixed questions, in any of its wordings (answered from the assessment's records).
    # A question carries no reason, so the whole sentence is read first: a colon in it belongs to a name.
    from app.assistant import questions

    whole = _PLEASE.sub("", POLITE.sub("", _GREETING.sub("", plain).strip().lower()).strip(" .!?"))
    asked = questions.read(whole) or questions.read(low)
    if asked is not None:
        return {**said, **asked}
    # Phase 6e: a what-if about one library and one version ("what if I update elliptic to 6.5.7?", "if we upgrade
    # elliptic to 6.5.7, how does that affect my libraries and dependencies?"). The lead-in is what makes it a question:
    # "update elliptic to 6.5.7" by itself names no button of this app, and is not read as one.
    m = _WHAT_IF.fullmatch(whole)
    if m:
        # (a sentence that goes on to a second update is not answered for the first one alone, whatever joins the two)
        several = _SECOND_UPDATE.search(whole[m.end("version") :]) is not None
        return {
            **said,
            "key": "what_if",
            "library": m.group("library"),
            "version": m.group("version").rstrip(".+_-"),
            "several": several,
        }
    m = re.fullmatch(
        r"(close|hide|open|show|switch to|go to|select) (?:the )?(testing|fixing|planning)(?: tab| thread)?", low
    )
    if m and (m.group(1) in ("close", "hide") or low.endswith((" tab", " thread"))):
        return {
            **said,
            "key": "tab",
            "thread": m.group(2),
            "how": "close" if m.group(1) in ("close", "hide") else "open",
        }

    # ---- done on its page only (read before the decisions: "approve" is not "accept")
    for key, pattern in (
        ("approve", r"approve\b.*"),
        ("merge", r"merge\b.*"),
        # (only what names the button's own thing: "apply the filter" and "sign off the fix" are not these buttons)
        ("apply", r"apply(?: it| this| that| the (?:fix|change|setting|update|try))?(?: to .+)?(?: now)?"),
        ("roll_back", r"roll ?back\b.*|undo the apply.*"),
        (
            "sign_off",
            r"(?:close and sign off|sign off|sign it off|close (?:the|this) assessment)(?: (?:the|this) assessment)?(?: now)?",
        ),
        (
            "own_tick",
            r"(i own (this|the) system|tick (?:that )?i own.*|tick (?:the )?(?:box|ownership|owner)\b.*|confirm (the|this|my) address.*|confirm ownership.*)",
        ),
        ("choose_option", r"(choose|pick|select|take) .*\boption\b.*|keep .* classical.*"),
        ("mark_reviewed", r"mark .*\breviewed\b.*|mark reviewed"),
        ("download", r"download\b.*|export(?: the)? (?:evidence|report)\b.*"),
        (
            "bring_in_demo_change",
            r"(?:bring in|add|push|load)(?: a| the| another)? (?:demo|developer(?:'s)?) change\b.*|"
            r"bring in(?: a| the| another)? change\b.*",
        ),
        (
            "settings",
            r"(turn|switch) (on|off) live otto|(turn|switch) live otto (on|off)|(open |go to |show )?settings|install .*pack.*|set .*limit.*",
        ),
    ):
        if re.fullmatch(pattern, low):
            return {**said, "key": key, "rest": low}

    # ---- a decision on a suggestion
    m = re.fullmatch(r"(accept|reject|decline|dismiss|undo|take back|reconsider|reopen)\b\s*(.*)", low)
    if m:
        verb = {"decline": "reject", "dismiss": "reject", "take back": "undo", "reopen": "reconsider"}.get(
            m.group(1), m.group(1)
        )
        return {**said, "key": verb, "rest": m.group(2).strip(), "reason": reason if verb == "reject" else None}

    # ---- a start: a page's button (where several fixes have the button, "... for <which fix>" says which one)
    for key, pattern in STARTS:
        m = re.fullmatch(pattern, low)
        if m:
            return {**said, "key": key, "rest": (m.groupdict().get("rest") or "").strip()}

    # ---- moving around: a filtered table, a page, one item
    m = re.fullmatch(
        r"(?:show|list|find|see|filter|open|go to|take me to|back to|view|where (?:is|are))(?: me)?(?: to)? (.+)", low
    )
    if m:
        rest = re.sub(r"^(?:all |only |just |the )+", "", m.group(1).strip())
        found = _filtered(rest)
        if found is not None:
            return {**said, "key": "filter", **found}
        page = PAGE_WORDS.get(re.sub(r"(?: page| tab| screen| list| table)$", "", rest))
        if page is not None:
            return {**said, "key": "open_page", "page": page}
        return {**said, "key": "open_item", "rest": rest}
    return {**said, "key": None}


def _filtered(rest: str) -> dict | None:
    """ "failed checks", "checks that failed", "proposed checks", "retests": the page and the filter, or None."""
    words_ = (
        rest.replace("that ", "")
        .replace("which ", "")
        .replace("have ", "")
        .replace("are ", "")
        .replace("were ", "")
        .strip()
    )
    for thing, (page, one) in THING_WORDS.items():
        for where in (rf"(.+) {thing}", rf"{thing} (.+)"):
            m = re.fullmatch(where, words_)
            if not m:
                continue
            how = m.group(1).strip()
            if how in RESULT_WORDS and page in RESULT_VALUES and RESULT_WORDS[how] in RESULT_VALUES[page]:
                return {
                    "page": page,
                    "one": one,
                    "filter": "result",
                    "value": RESULT_VALUES[page][RESULT_WORDS[how]],
                    "label": RESULT_WORDS[how],
                }
            if how in DECISION_WORDS:
                return {
                    "page": "advisories",
                    "one": "advisory",
                    "filter": "decision",
                    "value": DECISION_WORDS[how],
                    "label": DECISION_LABELS[DECISION_WORDS[how]],
                }
    if words_ in FROM_WORDS:
        key, label = FROM_WORDS[words_]
        return {"page": "checks", "one": "check", "filter": "from", "value": key, "label": label}
    return None


# ------------------------------------------------------------------ finding the item a person named


def _alias(token: str) -> set[str]:
    return {token, *ALIASES.get(token, ())}


def match(rest: str, candidates: list[dict], ignore: frozenset[str] | set[str] = frozenset()) -> list[dict]:
    """The candidates whose names hold every word of `rest` that says which one is meant. Each candidate is
    {"names": [text, ...], ...}. No word that narrows it down means every candidate fits ("the fix": every fix).
    Where several fit and exactly one of them is called exactly what was said, word for word, it is that one: the
    sentence behind a "Which one?" option says a whole title, and one title may hold every word of another.
    `ignore`: more words that only point ("this check"), for the questions."""
    wanted = [
        t for t in tokens(rest) if t not in SKIP and t not in KIND_WORDS and t not in ORDINALS and t not in ignore
    ]
    if not wanted:
        return list(candidates)
    out = []
    for c in candidates:
        have: set[str] = set()
        for name in c["names"]:
            have |= set(tokens(str(name)))
        # (a version or an id may be typed in part: "42460" for CVE-2024-42460, "17.0.3" for openjdk 17.0.3)
        if all(
            any(a in have or any(h.endswith("-" + a) or h.startswith(a + "-") for h in have) for a in _alias(t))
            for t in wanted
        ):
            out.append(c)
    if len(out) > 1:
        # (a title only: a library's bare name, or a stored value such as "yes", is no title, and must not pick one)
        said = tokens(rest)
        exact = [c for c in out if any(tokens(str(title)) == said for title in c.get("titles", c["names"][:1]))]
        if len(exact) == 1:
            return exact
    return out


def exact(rest: str, candidates: list[dict]) -> list[dict]:
    """The candidates that are called exactly what was said, word for word (their whole title). Looked for before any
    word of the sentence is read as a kind of thing: a title may hold such a word itself ("Fix acme-sign 1.4.2 before
    its signatures move to post-quantum" is a change to the migration plan, not a fix)."""
    said = tokens(rest)
    return [
        c for c in candidates if said and any(tokens(str(title)) == said for title in c.get("titles", c["names"][:1]))
    ]


# What a suggestion can be called besides its title: the advisory, the program, the library and its versions it is
# about. Never a fingerprint, an id of the app's own or a stored flag ("written: yes").
NAMING = ("advisory", "program", "library", "version", "fixed")


def names_of(p: dict) -> list[str]:
    """What a suggestion can be called: its title first, then what it is about."""
    about = p.get("about") or {}
    return [str(p.get("title") or "")] + [
        str(about[k]) for k in NAMING if isinstance(about.get(k), (str, int)) and not isinstance(about.get(k), bool)
    ]


def distinct(named: list[tuple[Any, str, str | None]]) -> dict[Any, str]:
    """A name for each thing that no other in the list has. `named`: (its key, its title, what tells it apart from
    others of the same title: the heading of its target, or None). A title nobody shares stays as it is; a shared one
    gets "on <target>"; and if two still read the same, their number, so that a sentence can always name exactly one
    (the multi-target demo file has one "Old TLS versions" for each server)."""
    shared = {title for _, title, _ in named if sum(1 for _, t, _ in named if t == title) > 1}
    out = {key: (f"{title} on {apart}" if title in shared and apart else title) for key, title, apart in named}
    still = {name for name in out.values() if sum(1 for other in out.values() if other == name) > 1}
    return {key: (f"{name} (number {key})" if name in still else name) for key, name in out.items()}


def which_text(shown: int, fitting: int) -> str:
    """ "Which one?", and where more fit than are listed, a plain word about it."""
    if fitting <= shown:
        return "Which one?"
    return f"Which one? The first {shown} of {fitting} that fit are listed. Say more of its name to narrow it down."


def kinds_named(rest: str) -> tuple[str, ...] | None:
    """Which kinds of suggestion the words name ("the Java fix": a fix or a library update), or None when they name none."""
    named = [KIND_WORDS[t] for t in tokens(rest) if t in KIND_WORDS]
    if not named:
        return None
    out = [k for k in named[0] if all(k in other for other in named)]
    return tuple(out) or named[0]


def ordinal(rest: str) -> int | None:
    found = [ORDINALS[t] for t in tokens(rest) if t in ORDINALS]
    return found[0] if found else None


# ------------------------------------------------------------------ what can be said on a page


def can_say(page: str, has_suggestions: bool, moving_only: bool = False) -> list[dict]:
    """The lines of the one list that fit this page, each with an example: moving around, the decisions (where a
    suggestion can be named), the page's own buttons, and what is done on a page only. `moving_only`: a closed
    assessment, or one with no file yet, where nothing can be decided or started: only the lines that move."""
    out = []
    for c in COMMANDS:
        if c["kind"] == "go":
            out.append({"say": c["say"], "about": c["about"], "kind": "go"})
        elif moving_only:
            continue
        elif c["key"] in DECISIONS:
            if has_suggestions:
                out.append({"say": c["say"], "about": c["about"], "kind": "do"})
        elif c["kind"] == "do" and c["page"] == page:
            out.append(
                {
                    "say": c["say"],
                    "about": f"The {c['say'] if c['key'] not in ('run', 'retest', 'measure_library') else _button(c['key'])} "
                    f"button of {PAGE_LABELS[page]}. It waits for Confirm.",
                    "kind": "do",
                }
            )
    return out


def _button(key: str) -> str:
    return {"run": "Run", "retest": "Retest new version", "measure_library": "Measure on a public copy"}[key]


def reply(kind: str, text: str, **more: Any) -> dict:
    """One answer to a typed sentence. `kind`: went, card, which, cannot, help, page_only, tab, closed, (phase 6c)
    answer: a fixed question, with its facts, and (phase 6e) whatif: what the app knows about an update, in four parts."""
    return {
        "kind": kind,
        "text": text,
        "go": more.get("go"),
        "entry": more.get("entry"),
        "open": more.get("open"),
        "options": more.get("options") or [],
        "can": more.get("can") or [],
        "tab": more.get("tab"),
        "thread": more.get("thread"),
        "question": more.get("question"),
        "label": more.get("label"),
        "facts": more.get("facts") or [],
        "whatif": more.get("whatif"),
    }


def go(page: str, item: str | None = None, **filters: str | None) -> dict:
    return {
        "page": page,
        "item": item,
        "group": filters.get("group"),
        "result": filters.get("result"),
        "came_from": filters.get("came_from"),
        "decision": filters.get("decision"),
    }


__all__ = [
    "BOX",
    "BY_KEY",
    "CHIPS",
    "COMMANDS",
    "DECISIONS",
    "HELP",
    "KIND_THREAD",
    "MAX_OPTIONS",
    "PAGE_THREAD",
    "THREADS",
    "THREAD_LABELS",
    "can_say",
    "go",
    "kinds_named",
    "match",
    "ordinal",
    "read",
    "reply",
    "tokens",
    "words",
]
