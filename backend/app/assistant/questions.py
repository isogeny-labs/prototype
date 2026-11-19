"""Phase 6c, first half: six fixed questions, answered by fixed rules from the assessment's own records.

An answer is a short list of facts. Every fact is a sentence a page of the app already shows about the item (the
reviewer's result and its plain sentence, what happened, the control, where an advisory check came from, a proposal's
own lines), or one of the assistant's own standing sentences about a page, each with the link to where it is shown.
Nothing here words a result, rates anything or guesses: where the records do not say, the answer says so. No model is
asked, with Live Otto on or off; answers in free words (Claude's, held to a fact sheet) are the second half.

    Why did this check fail?                              the reviewer's result, its plain sentence, what happened,
                                                          the control, where the check came from, the fix
    What does this result show, and what doesn't it?      the result's own lines on what it shows and what it doesn't
    Where did this suggestion come from?                  why it is proposed, its own lines, the decisions so far
    What happens if I accept this?                        the lines of its Confirm step, and the page's own note
    What is this page for?                                one sentence about the page, and what is on it now
    What should I do next?                                the Overview's next step, and what waits for a decision
"""
from __future__ import annotations

import re
from typing import Any

from app.assistant import commands, words
from app.assistant.threads import FITS, KIND_THREAD, PAGE_LABELS, PAGE_THREAD
from app.otto.proposals import HOME
from app.present import otto as present_otto

LABEL = "From this assessment's records"
QUESTIONS: tuple[dict[str, str], ...] = (
    {"key": "why_failed", "ask": "Why did this check fail?"},
    {"key": "shows", "ask": "What does this result show, and what doesn't it?"},
    {"key": "came_from", "ask": "Where did this suggestion come from?"},
    {"key": "if_accept", "ask": "What happens if I accept this?"},
    {"key": "page_for", "ask": "What is this page for?"},
    {"key": "next", "ask": "What should I do next?"},
)
ASK = {q["key"]: q["ask"] for q in QUESTIONS}
# How a question can be worded. `rest` names what it is about ("this check", "the blank signature check", "evidence").
ASKS: tuple[tuple[str, str], ...] = (
    ("why_failed", r"why (?:did|does|has|is|was) (?P<rest>.+?) (?:fail|failed|failing)"),
    ("why_failed", r"why (?:did|does|is|was) (?P<rest>.+?) not (?:pass|passing|passed)"),
    ("why_failed", r"what went wrong(?: (?:with|in|on) (?P<rest>.+))?"),
    ("why_failed", r"why (?:did|does) (?:it|this|that) fail"),
    ("shows", r"what does (?P<rest>.+?) (?:show|prove|tell me|tell us)(?:,? and what (?:(?:doesn't|does not|doesnt) it|does it not|it (?:doesn't|does not))(?: show| prove)?)?"),
    ("shows", r"what did (?P<rest>.+?) (?:show|prove)"),
    ("came_from", r"where (?:did|does) (?P<rest>.+?) come from"),
    ("came_from", r"why (?:is|was) (?P<rest>.+?) (?:proposed|suggested)"),
    ("came_from", r"who proposed (?P<rest>.+)"),
    ("if_accept", r"what (?:happens|will happen|would happen) (?:if|when) i accept(?: (?P<rest>.+))?"),
    ("if_accept", r"what (?:does|would|will) accepting (?P<rest>.+?) do"),
    ("page_for", r"what is (?:this page|this|the page|it) for"),
    ("page_for", r"what am i looking at"),
    ("page_for", r"what is (?:the )?(?P<rest>.+?)(?: page)? for"),
    ("next", r"what (?:should|do|can|shall) (?:i|we) do (?:next|now)"),
    ("next", r"what(?:'s| is) (?:next|the next step)|what now|what comes next|next step"),
)
# The words that only say "the thing I am looking at".
_POINTING = {"this", "that", "it", "check", "checks", "test", "result", "one", "suggestion", "proposal", "fix", "update", "change", "here"}
_TEST = re.compile(r"^test-(\d+)$")
_OTHER_RUN = re.compile(r"^(?:retest|proof)-\d+")


def read(low: str) -> dict | None:
    """One of the fixed questions, in whatever of its wordings, or None. `low`: the sentence in small letters."""
    for key, pattern in ASKS:
        m = re.fullmatch(pattern, low)
        if m:
            return {"key": "ask", "question": key, "rest": (m.groupdict().get("rest") or "").strip()}
    return None


def fact(text: str, link: dict | None = None, label: str | None = None) -> dict:
    """One fact of an answer: a sentence, and the link to where the app shows it (always in the same three-part shape)."""
    where = {"page": link["page"], "item": link.get("item"), "group": link.get("group")} if link else None
    return {"text": " ".join(str(text).split()), "link": where, "label": (label or "Open") if where else None}


def _link(page: str, item: object = None, group: str | None = None) -> dict:
    return {"page": page, "item": str(item) if item is not None else None, "group": group}


def _names(rest: str) -> bool:
    """Do the words name something, or only point at what is open?"""
    return any(t not in commands.SKIP and t not in _POINTING for t in commands.tokens(rest))


# ------------------------------------------------------------------ what the records say, and never more

def _newest(row: dict) -> dict | None:
    return row.get("after") or row.get("result")


def _failed(result: dict | None) -> bool:
    """Does the reviewer's own word for this result read as a failure on its page? The assistant never decides that:
    it reads the tone the page draws the result's badge in ("Failed", and also "Slowdown found" after a retest).
    "Couldn't run" and "Couldn't trust this run" are neither a pass nor a failure, and are not counted as one."""
    return result is not None and result.get("tone") == "fail"


def _row_names(lab_view: dict) -> dict[int, str]:
    """A name for each test of the plan that no other test has (where two share a title: with its target)."""
    headings = {g["key"]: g["heading"] for g in lab_view.get("groups") or []}
    return commands.distinct([(r["item_id"], r["title"], headings.get(r.get("group"))) for r in lab_view.get("rows") or []])


def _open(item: str | None, rows: list[dict], proposals: list[dict]) -> tuple[str, Any]:
    """What the open item is, for a question about "this check". Nothing is guessed:
      ("none", None)        nothing is open
      ("row", row)          a test of the plan that has a result
      ("no_result", row)    a test of the plan that has none yet
      ("rows", [row, ...])  an advisory with several accepted checks in the plan
      ("other_run", None)   the row of a retest or of a fix proof: its own run, which an answer here is not about
      ("not_a_test", None)  anything else: a claim, an advisory with no check in the plan, a fix, a system"""
    if not item:
        return "none", None
    m = _TEST.match(item)
    if m:
        row = next((r for r in rows if r["item_id"] == int(m.group(1))), None)
        if row is None:
            return "not_a_test", None
        return ("row" if _newest(row) is not None else "no_result"), row
    if _OTHER_RUN.match(item):
        return "other_run", None
    ids = [int(p["facts"]["item_id"]) for p in proposals
           if p["kind"] == "check" and (p.get("link") or {}).get("item") == item and (p.get("facts") or {}).get("item_id") is not None]
    mine = [r for r in rows if r["item_id"] in ids]
    if len(mine) == 1:
        return ("row" if _newest(mine[0]) is not None else "no_result"), mine[0]
    if len(mine) > 1:
        return "rows", mine
    return "not_a_test", None


NO_RESULTS = "No test of the plan has a result yet. Results come from running the test plan on Checks."
NONE_FAILED = "No test of the plan reads Failed now."
OTHER_RUN = ("The open row is the run of a retest or of a fix proof. An answer here is about a test's first result and its newest "
             "retest: open the test on Evidence, or name it.")
NOT_A_TEST = "The open item is not a test of the plan, so there is no test result to explain. Name the check you mean."
NO_SUCH_TEST = "I can't do that. No test of the plan is called that."
NO_SUCH_SUGGESTION = "I can't do that. No suggestion here is called that."


def _no_result(row: dict, name: str) -> tuple:
    return ("say", f"“{name}” has no result yet. It gets one when it is run, on Checks.", _link("checks", f"test-{row['item_id']}"), "Open it on Checks")


# ------------------------------------------------------------------ which questions fit, for the chips

def fitting(page: str, item: str | None, lab_view: dict, proposals: list[dict], shown: list[dict]) -> list[str]:
    """Up to three of the fixed questions that fit this page and the open item, the most particular first. Worked out
    by the rule the answers use, so a chip is only offered where its answer is about what it says."""
    out: list[str] = []
    rows = lab_view.get("rows") or []
    kind, what = _open(item, rows, proposals)
    mine = [what] if kind == "row" else list(what) if kind == "rows" else []
    failing_here = any(_failed(_newest(r)) or _failed(r.get("result")) for r in mine)
    failing_anywhere = kind == "none" and any(_failed(_newest(r)) for r in rows)
    if PAGE_THREAD.get(page) == "testing" and (failing_here or failing_anywhere):
        out.append(ASK["why_failed"])
    if kind == "row":
        out.append(ASK["shows"])
    if shown:
        out.append(ASK["came_from"])
        if any(p["state"] == "proposed" for p in shown):
            out.append(ASK["if_accept"])
    out += [ASK["next"], ASK["page_for"]]
    return out[:3]


# ------------------------------------------------------------------ the answers

def answer(copilot: Any, facts: Any, said: dict, page: str, item: str | None, proposals: list[dict], shown: list[dict], out: Any, can: list[dict]) -> dict:
    question, rest = said["question"], said.get("rest") or ""
    if question == "page_for":
        return _page_for(facts, rest, page, proposals, out, can, "page" in commands.tokens(said.get("said") or ""))
    if question == "next":
        return _next(facts, page, out)
    if not facts.has_file:
        return out("answer", ASK[question], question=ASK[question], label=LABEL, facts=[fact(words.NO_FILE, _link("inventory/import"), "Open Import")])
    if question in ("why_failed", "shows"):
        lab_view = facts.lab()
        names = _row_names(lab_view)
        picked = _pick_row(rest, item, lab_view, names, proposals, failed_first=question == "why_failed")
        if picked[0] == "cannot":
            return out("cannot", picked[1], can=can, thread="testing")
        if picked[0] == "say":
            return out("answer", ASK[question], question=ASK[question], label=LABEL, thread="testing", facts=[fact(picked[1], picked[2], picked[3])])
        if picked[0] == "which":
            ask = "Why did {} fail?" if question == "why_failed" else "What does {} show?"
            listed = picked[1][:commands.MAX_OPTIONS]
            return out("which", commands.which_text(len(listed), len(picked[1])), thread="testing",
                       options=[{"label": f"{names[r['item_id']]} ({(_newest(r) or {}).get('label') or 'no result yet'})",
                                 "say": ask.format(commands.sayable(names[r["item_id"]]))} for r in listed])
        row = picked[1]
        return _why_failed(row, names[row["item_id"]], out) if question == "why_failed" else _shows(row, names[row["item_id"]], out)
    # the two questions about a suggestion
    chosen = _pick_proposal(rest, item, proposals, shown)
    if chosen[0] == "cannot":
        return out("cannot", chosen[1], can=can)
    if chosen[0] == "none":
        return out("answer", ASK[question], question=ASK[question], label=LABEL,
                   facts=[fact("Nothing is proposed in this assessment now, so there is no suggestion to ask about.", _link("advisories"), "Open Advisories")])
    if chosen[0] == "which":
        ask = "Where did {} come from?" if question == "came_from" else "What happens if I accept {}?"
        listed = chosen[1][:commands.MAX_OPTIONS]
        return out("which", commands.which_text(len(listed), len(chosen[1])),
                   options=[{"label": f"{p['title']} (on {PAGE_LABELS[HOME.get(p['kind'], 'overview')]})",
                             "say": ask.format(commands.sayable(p["title"]))} for p in listed])
    return _came_from(chosen[1], out) if question == "came_from" else _if_accept(copilot, chosen[1], item, out)


def _pick_row(rest: str, item: str | None, lab_view: dict, names: dict[int, str], proposals: list[dict], failed_first: bool) -> tuple:
    """The one test the question is about: ("row", row); or ("which", rows) to choose from; or ("say", sentence, link,
    label) where the records hold nothing to answer from, said as that; or ("cannot", sentence) where the words name
    something no test is called. Never another test than the one that was named or is open."""
    rows = lab_view.get("rows") or []
    if _names(rest):
        candidates = [{"names": [r["title"], names[r["item_id"]]], "titles": [names[r["item_id"]]], "r": r} for r in rows]
        found = [c["r"] for c in commands.match(rest, candidates, ignore=_POINTING)]
        if not found:
            return ("cannot", NO_SUCH_TEST)
        have = [r for r in found if _newest(r) is not None]
        if not have:
            if len(found) == 1:
                return _no_result(found[0], names[found[0]["item_id"]])
            return ("say", f"None of the {len(found)} tests that fit has a result yet. Results come from running the test plan on Checks.",
                    _link("checks"), "Open Checks")
        if len(have) == 1:
            return ("row", have[0])
        if failed_first:
            failing = [r for r in have if _failed(_newest(r)) or _failed(r.get("result"))]
            if len(failing) == 1:
                return ("row", failing[0])
        return ("which", have)
    kind, what = _open(item, rows, proposals)
    if kind == "row":
        return ("row", what)
    if kind == "no_result":
        return _no_result(what, names[what["item_id"]])
    if kind == "rows":
        have = [r for r in what if _newest(r) is not None]
        if not have:
            return ("say", "The checks of this advisory have no result yet. They get one when they are run, on Checks.", _link("checks"), "Open Checks")
        return ("row", have[0]) if len(have) == 1 else ("which", have)
    if kind == "other_run":
        return ("say", OTHER_RUN, _link("evidence"), "Open Evidence")
    if kind == "not_a_test":
        return ("say", NOT_A_TEST, _link("checks"), "Open Checks")
    # nothing is open
    with_result = [r for r in rows if _newest(r) is not None]
    pool = [r for r in with_result if _failed(_newest(r))] if failed_first else with_result
    if len(pool) == 1:
        return ("row", pool[0])
    if pool:
        return ("which", pool)
    return ("say", NONE_FAILED if failed_first and with_result else NO_RESULTS, _link("checks"), "Open Checks")


def _evidence(row: dict) -> dict:
    return _link("evidence", f"test-{row['item_id']}")


# A result's one-line sentence stands in the Evidence table (its Result column). The result's own panel, once open,
# does not repeat it. So that one fact links to the table, and every other fact of a result to the result.
IN_TABLE = "See the Evidence table"


def _plain(result: dict) -> dict:
    return fact(result["plain"], _link("evidence"), IN_TABLE)


def _why_failed(row: dict, name: str, out: Any) -> dict:
    """The reviewer's result and what the result's own page says about it. The first line repeats the result's word;
    it never says of its own that something did or did not fail."""
    first, after = row.get("result"), row.get("after")
    result = after if _failed(after) else first if _failed(first) else (after or first)       # the one that failed, the newer one first
    assert result is not None
    on = f" on {result['component']}" if result.get("component") else ""
    where = _evidence(row)
    facts = [fact(f"“{name}” reads {result['label']}{on}.", where, "See the evidence"), _plain(result)]
    if _failed(result):
        for line in (result.get("what_happened") or [])[:3]:
            facts.append(fact(line, where, "See the evidence"))
        control = result.get("control") or {}
        if control.get("text"):
            facts.append(fact(control["text"], where, "See the run record"))
        block = result.get("otto")
        if block:
            facts.append(fact(block["line"], block["advisory"]["link"], block["advisory"]["label"]))
        fix = result.get("fix_line")
        if fix:
            listed = f"{fix['lead']} {fix['rest']}".strip()
            facts.append(fact(f"Evidence says of its fix: “{listed}”.", _link("fixes", fix["fix_id"]), fix.get("button") or "View in Fixes"))
        elif result.get("suggested_fix"):
            facts.append(fact(f"{result.get('fix_title') or 'Suggested fix'}: {result['suggested_fix']}", where, "See the evidence"))
    if result is first and after is not None:
        again = f" on {after['component']}" if after.get("component") else ""
        facts.append(fact(f"In the retest{again} it reads {after['label']}.", where, "See the evidence"))
    return out("answer", f"{ASK['why_failed']} {name}", question=ASK["why_failed"], label=LABEL, facts=facts, thread="testing")


def _shows(row: dict, name: str, out: Any) -> dict:
    result = _newest(row)
    assert result is not None
    on = f" on {result['component']}" if result.get("component") else ""
    where = _evidence(row)
    facts = [fact(f"“{name}” reads {result['label']}{on}.", where, "See the evidence")]
    lines = result.get("shows") or []
    facts += [fact(line, where, "See the evidence") for line in lines[:8]]
    if not lines:
        facts.append(_plain(result))
    return out("answer", f"{ASK['shows']} {name}", question=ASK["shows"], label=LABEL, facts=facts, thread="testing")


def _pick_proposal(rest: str, item: str | None, proposals: list[dict], shown: list[dict]) -> tuple:
    """The one suggestion the question is about: ("one", p), ("which", [p, ...]), ("none",) when nothing is proposed
    at all, or ("cannot", sentence) when the words name something no suggestion is called."""
    from app.assistant.engine import _about
    if _names(rest):
        # the whole title, word for word, whatever kind word it holds itself ("Fix acme-sign 1.4.2 before ..." is a plan change)
        whole = commands.exact(rest, [{"names": [str(p.get("title") or "")], "p": p} for p in proposals])
        if len(whole) == 1:
            return ("one", whole[0]["p"])
        kinds = commands.kinds_named(rest)
        pool = [p for p in proposals if kinds is None or p["kind"] in kinds]
        found = [c["p"] for c in commands.match(rest, [{"names": commands.names_of(p), "p": p} for p in pool], ignore=_POINTING)]
        if not found:
            return ("cannot", NO_SUCH_SUGGESTION)
        return ("one", found[0]) if len(found) == 1 else ("which", found)
    about = [p for p in proposals if _about(p, item)]
    if len(about) == 1:
        return ("one", about[0])
    pool = about or shown or proposals
    if not pool:
        return ("none",)
    return ("one", pool[0]) if len(pool) == 1 else ("which", pool)


def _came_from(p: dict, out: Any) -> dict:
    view = present_otto.proposal_view(p)
    home = HOME.get(p["kind"], "overview")
    where = view["link"]
    facts = [fact(f"“{view['title']}” is a proposal marked {view['label']}, on {PAGE_LABELS[home]}. It reads “{view['status']['word']}”.", where, "Open it"),
             fact(f"{view['why_label']}: {view['why']}", where, "Open it")]
    facts += [fact(line, where, "Open it") for line in (view.get("lines") or [])[:6]]
    rows = (view.get("history") or {}).get("rows") or []
    facts += [fact(view["decided_line"], where, "Open it")] if not rows and view.get("decided_line") else []
    facts += [fact(row["line"], where, "Open it") for row in rows[-4:]]
    if not p.get("current", True):
        # (its page's own note: what it was about has changed since, so it is no longer proposed there)
        facts.append(fact(present_otto.NO_LONGER_PROPOSED, where, "Open it"))
    return out("answer", f"{ASK['came_from']} {view['title']}", question=ASK["came_from"], label=LABEL, facts=facts, thread=KIND_THREAD[p["kind"]])


def _if_accept(copilot: Any, p: dict, item: str | None, out: Any) -> dict:
    entry = copilot._suggestion(p, item)
    home = PAGE_LABELS[HOME.get(p["kind"], "overview")]
    where = entry["where"]["link"]
    button = next((d for d in entry["decisions"] if d["key"] == "accept"), None)
    facts = []
    if button is None:
        facts.append(fact(f"“{entry['title']}” reads “{entry['badge']['label']}”: there is nothing to accept now.", where, "Open it"))
        if entry["proposal"].get("decided_line"):
            facts.append(fact(entry["proposal"]["decided_line"], where, "Open it"))
    else:
        facts.append(fact(f"Accepting “{entry['title']}”, on {home}:", where, "Open it"))
        facts += [fact(line, where, "Open it") for line in words.ACCEPT_LINES[p["kind"]]]
        if not button["can"] and button.get("blocked_reason"):
            facts.append(fact(f"It can't be accepted now: {button['blocked_reason']}", where, "Open it"))
        facts.append(fact(f"In this panel Accept waits for your Confirm. On {home} the Accept button records the decision at the click. Either way it "
                          "is recorded with who and when, and it words no result.", where, "Open it"))
    return out("answer", f"{ASK['if_accept']} {entry['title']}", question=ASK["if_accept"], label=LABEL, facts=facts, thread=KIND_THREAD[p["kind"]])


def _page_for(facts: Any, rest: str, page: str, proposals: list[dict], out: Any, can: list[dict], said_page: bool) -> dict:
    """One sentence about a page (its own header sentence, as closely as one line can say it) and what is on it now.
    A page is named by its own name ("Evidence", "the roadmap"); another word for it counts only with "page" said
    ("the tests page"), so "What is the fix for?" is not read as a question about Fixes."""
    named = None
    if rest:
        word = re.sub(r"(?: page| tab| screen)$", "", rest)
        own = {label.lower(): key for key, label in PAGE_LABELS.items()}
        named = own.get(word) or (commands.PAGE_WORDS.get(word) if said_page else None)
        # (words that only point at the page that is open; anything else that is no page's name is not guessed at)
        if named is None and any(t not in commands.SKIP and t not in ("here", "one") for t in commands.tokens(word)):
            return out("cannot", "I can't do that. There is no page of that name.", can=can)
    target = named or page
    label = PAGE_LABELS[target]
    told = [fact(words.PAGE_FOR[target], _link(target), f"Open {label}")]
    if facts.has_file:
        counted = _on_page(facts, target)
        if counted:
            told.append(fact(counted, _link(target), f"Open {label}"))
    else:
        told.append(fact(words.NO_FILE, _link("inventory/import"), "Open Import"))
    return out("answer", f"What is {label} for?", question=ASK["page_for"], label=LABEL, facts=told, thread=PAGE_THREAD.get(target))


def _waiting(facts: Any, kinds: tuple[str, ...]) -> int:
    """How many suggestions of these kinds wait for a decision, counted as the Overview counts them: where nothing can
    be decided (a closed assessment, Otto not installed, a proposal that is no longer made) nothing waits."""
    return sum(int(facts.waiting.get(kind) or 0) for kind in kinds)


def _on_page(facts: Any, page: str) -> str | None:
    """What is on a page now, counted from the views the pages draw from."""
    waiting = _waiting(facts, tuple(FITS.get(page, ())))
    wait = f" {waiting} {'suggestion waits' if waiting == 1 else 'suggestions wait'} for a decision." if waiting else ""
    if page == "checks":
        tests = facts.plan().get("tests") or []
        ran = sum(1 for t in tests if t.get("result") is not None)
        return f"On it now: {len(tests)} {'test' if len(tests) == 1 else 'tests'} in the test plan, {ran} with a result.{wait}"
    if page == "evidence":
        # (the tests of the plan only: Evidence also lists verified claims, measurements and proofs, which are not counted here)
        rows = facts.lab().get("rows") or []
        failed = sum(1 for r in rows if _failed(_newest(r)))
        done = sum(1 for r in rows if _newest(r) is not None)
        return (f"On it now, of the test plan: {done} {'test has' if done == 1 else 'tests have'} a result, and {failed} of them "
                f"{'reads' if failed == 1 else 'read'} as failed.")
    if page == "fixes":
        n = len(facts.fixes().get("fixes") or [])
        return f"On it now: {n} {'fix' if n == 1 else 'fixes'}.{wait}"
    return f"On it now:{wait}" if wait else None


def _next(facts: Any, page: str, out: Any) -> dict:
    told = []
    step = facts.overview_step() if facts.has_file else None
    if not facts.has_file:
        told.append(fact(words.NO_FILE, _link("inventory/import"), "Open Import"))
    elif step and step.get("page"):
        told.append(fact(f"Next: {step['label']}. {step['text']}", _link(step["page"]), f"Open {PAGE_LABELS.get(step['page'], step['label'])}"))
    else:
        told.append(fact("The Overview names no next step now.", _link("overview"), "Open Overview"))
    for kind in KIND_THREAD:
        n = _waiting(facts, (kind,)) if facts.has_file else 0
        home = HOME.get(kind, "overview")
        if not n or (step and step.get("page") == home):
            continue                                      # (nothing waits; or the next step already sends there, and says how many)
        told.append(fact(f"{words.counted(n, kind).capitalize()} {'waits' if n == 1 else 'wait'} for a decision on {PAGE_LABELS[home]}.",
                         _link(home), f"Open {PAGE_LABELS[home]}"))
    # (filed under the thread of the page the next step sends to, so a kept answer is listed in that tab)
    thread = PAGE_THREAD.get(page) or (PAGE_THREAD.get(step["page"]) if step and step.get("page") else None)
    return out("answer", ASK["next"], question=ASK["next"], label=LABEL, facts=told, thread=thread)


__all__ = ["ASK", "LABEL", "QUESTIONS", "answer", "fitting", "read"]
