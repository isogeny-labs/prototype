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
    ("shows", r"what does (?P<rest>.+?) (?:show|prove|tell me|tell us)(?:,? and what (?:doesn't|does not|doesnt) it)?"),
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
_ITEM = re.compile(r"^(?:test|retest|proof)-(\d+)(?:-(?:on|in)-\d+)?$")


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


# ------------------------------------------------------------------ which questions fit, for the chips

def fitting(page: str, item: str | None, rows: list[dict], shown: list[dict]) -> list[str]:
    """Up to three of the fixed questions that fit this page and the open item, the most particular first."""
    out: list[str] = []
    row = _row_for(item, rows, [])
    failed = [r for r in rows if _failed(_newest(r))]
    if PAGE_THREAD.get(page) == "testing" and ((row is not None and _failed(_newest(row))) or (row is None and failed)):
        out.append(ASK["why_failed"])
    if row is not None and _newest(row) is not None:
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
        return _page_for(facts, rest, page, proposals, out)
    if question == "next":
        return _next(facts, page, proposals, out)
    if not facts.has_file:
        return out("answer", ASK[question], question=ASK[question], label=LABEL, facts=[fact(words.NO_FILE, _link("inventory/import"), "Open Import")])
    if question in ("why_failed", "shows"):
        rows = facts.lab().get("rows") or []
        picked = _pick_row(rest, item, rows, proposals, failed_first=question == "why_failed")
        if isinstance(picked, list):
            if not picked:
                none = ("No check of this assessment reads Failed now." if question == "why_failed" and rows else
                        "No check of this assessment has a result yet. Results come from running the test plan on Checks.")
                return out("answer", ASK[question], question=ASK[question], label=LABEL, thread="testing",
                           facts=[fact(none, _link("checks"), "Open Checks")])
            ask = "Why did {} fail?" if question == "why_failed" else "What does {} show?"
            return out("which", "Which one?", thread="testing",
                       options=[{"label": f"{r['title']} ({(_newest(r) or {}).get('label') or 'no result yet'})",
                                 "say": ask.format(commands.sayable(r["title"]))} for r in picked[:commands.MAX_OPTIONS]])
        return _why_failed(picked, out) if question == "why_failed" else _shows(picked, out)
    # the two questions about a suggestion
    picked_p = _pick_proposal(rest, item, proposals, shown)
    if isinstance(picked_p, list):
        if not picked_p:
            return out("answer", ASK[question], question=ASK[question], label=LABEL,
                       facts=[fact("Nothing is proposed in this assessment now, so there is no suggestion to ask about.")])
        ask = "Where did {} come from?" if question == "came_from" else "What happens if I accept {}?"
        return out("which", "Which one?", options=[{"label": f"{p['title']} (on {PAGE_LABELS[HOME.get(p['kind'], 'overview')]})",
                                                    "say": ask.format(commands.sayable(p["title"]))} for p in picked_p[:commands.MAX_OPTIONS]])
    return _came_from(picked_p, out) if question == "came_from" else _if_accept(copilot, picked_p, item, out)


def _newest(row: dict) -> dict | None:
    return row.get("after") or row.get("result")


def _failed(result: dict | None) -> bool:
    return result is not None and result.get("code") == "failed"


def _row_for(item: str | None, rows: list[dict], proposals: list[dict]) -> dict | None:
    """The result the open item is: a test of the plan (also as a retest's or a proof's row), or the advisory whose
    accepted check it is."""
    if not item:
        return None
    m = _ITEM.match(item)
    wanted: int | None = int(m.group(1)) if m else None
    if wanted is None:
        for p in proposals:
            if p["kind"] == "check" and (p.get("link") or {}).get("item") == item and (p.get("facts") or {}).get("item_id") is not None:
                wanted = int(p["facts"]["item_id"])
                break
    return next((r for r in rows if r["item_id"] == wanted), None) if wanted is not None else None


def _pick_row(rest: str, item: str | None, rows: list[dict], proposals: list[dict], failed_first: bool) -> dict | list[dict]:
    """The one result the question is about; or the list to choose from (empty: there is none)."""
    with_result = [r for r in rows if _newest(r) is not None]
    if _names(rest):
        found = [c["r"] for c in commands.match(rest, [{"names": [r["title"]], "r": r} for r in with_result], ignore=_POINTING)]
        if len(found) == 1:
            return found[0]
        if failed_first and len([r for r in found if _failed(_newest(r)) or _failed(r.get("result"))]) == 1:
            return next(r for r in found if _failed(_newest(r)) or _failed(r.get("result")))
        return found
    opened = _row_for(item, rows, proposals)
    if opened is not None and _newest(opened) is not None:
        return opened
    pool = [r for r in with_result if _failed(_newest(r))] if failed_first else with_result
    return pool[0] if len(pool) == 1 else pool


def _evidence(row: dict) -> dict:
    return _link("evidence", f"test-{row['item_id']}")


def _why_failed(row: dict, out: Any) -> dict:
    first, after = row.get("result"), row.get("after")
    result = after if _failed(after) else first if _failed(first) else (after or first)       # the one that failed, the newer one first
    assert result is not None
    on = f" on {result['component']}" if result.get("component") else ""
    where = _evidence(row)
    facts = []
    if not _failed(result):
        facts.append(fact(f"“{row['title']}” did not fail: it reads {result['label']}{on}.", where, "See the evidence"))
        facts.append(fact(result["plain"], where, "See the evidence"))
        return out("answer", f"{ASK['why_failed']} {row['title']}", question=ASK["why_failed"], label=LABEL, facts=facts, thread="testing")
    facts.append(fact(f"“{row['title']}” reads {result['label']}{on}.", where, "See the evidence"))
    facts.append(fact(result["plain"], where, "See the evidence"))
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
        facts.append(fact(f"Fixes lists a fix for this result. It reads “{listed}”.", _link("fixes", fix["fix_id"]), fix.get("button") or "View in Fixes"))
    elif result.get("suggested_fix"):
        facts.append(fact(f"{result.get('fix_title') or 'Suggested fix'}: {result['suggested_fix']}", where, "See the evidence"))
    if result is first and after is not None:
        again = f" on {after['component']}" if after.get("component") else ""
        facts.append(fact(f"In the retest{again} it reads {after['label']}.", where, "See the evidence"))
    return out("answer", f"{ASK['why_failed']} {row['title']}", question=ASK["why_failed"], label=LABEL, facts=facts, thread="testing")


def _shows(row: dict, out: Any) -> dict:
    result = _newest(row)
    assert result is not None
    on = f" on {result['component']}" if result.get("component") else ""
    where = _evidence(row)
    facts = [fact(f"“{row['title']}” reads {result['label']}{on}.", where, "See the evidence")]
    lines = result.get("shows") or []
    facts += [fact(line, where, "See the evidence") for line in lines[:8]]
    if not lines:
        facts.append(fact(result["plain"], where, "See the evidence"))
    return out("answer", f"{ASK['shows']} {row['title']}", question=ASK["shows"], label=LABEL, facts=facts, thread="testing")


def _pick_proposal(rest: str, item: str | None, proposals: list[dict], shown: list[dict]) -> dict | list[dict]:
    from app.assistant.engine import _about
    if _names(rest):
        # the whole title, word for word, whatever kind word it holds itself ("Fix acme-sign 1.4.2 before ..." is a plan change)
        whole = commands.exact(rest, [{"names": [str(p.get("title") or "")], "p": p} for p in proposals])
        if len(whole) == 1:
            return whole[0]["p"]
        kinds = commands.kinds_named(rest)
        pool = [p for p in proposals if kinds is None or p["kind"] in kinds]
        found = [c["p"] for c in commands.match(rest, [{"names": [str(p.get("title") or "")] + [str(v) for v in (p.get("about") or {}).values()
                                                                                                 if isinstance(v, (str, int)) and not isinstance(v, bool)],
                                                        "p": p} for p in pool], ignore=_POINTING)]
        return found[0] if len(found) == 1 else found
    about = [p for p in proposals if _about(p, item)]
    if len(about) == 1:
        return about[0]
    pool = about or shown or proposals
    return pool[0] if len(pool) == 1 else pool


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
        facts.append(fact("Accept waits for your Confirm, here and on its page. A decision is recorded with who and when; it words no result."))
    return out("answer", f"{ASK['if_accept']} {entry['title']}", question=ASK["if_accept"], label=LABEL, facts=facts, thread=KIND_THREAD[p["kind"]])


def _page_for(facts: Any, rest: str, page: str, proposals: list[dict], out: Any) -> dict:
    named = commands.PAGE_WORDS.get(re.sub(r"(?: page| tab| screen)$", "", rest)) if rest else None
    if rest and named is None and _names(rest):
        return out("cannot", "I can't do that. There is no page of that name.")
    target = named or page
    label = PAGE_LABELS[target]
    told = [fact(words.PAGE_FOR[target], _link(target), f"Open {label}")]
    if facts.has_file:
        counted = _on_page(facts, target, proposals)
        if counted:
            told.append(fact(counted, _link(target), f"Open {label}"))
    else:
        told.append(fact(words.NO_FILE, _link("inventory/import"), "Open Import"))
    return out("answer", f"What is {label} for?", question=ASK["page_for"], label=LABEL, facts=told, thread=PAGE_THREAD.get(target))


def _on_page(facts: Any, page: str, proposals: list[dict]) -> str | None:
    """What is on a page now, counted from the views the pages draw from."""
    waiting = sum(1 for p in proposals if p["kind"] in FITS.get(page, ()) and p["state"] == "proposed")
    wait = f" {waiting} {'suggestion waits' if waiting == 1 else 'suggestions wait'} for a decision." if waiting else ""
    if page == "checks":
        tests = facts.plan().get("tests") or []
        ran = sum(1 for t in tests if t.get("result") is not None)
        return f"On it now: {len(tests)} {'test' if len(tests) == 1 else 'tests'} in the test plan, {ran} with a result.{wait}"
    if page == "evidence":
        rows = facts.lab().get("rows") or []
        failed = sum(1 for r in rows if _failed(_newest(r)))
        done = sum(1 for r in rows if _newest(r) is not None)
        return f"On it now: {done} {'result' if done == 1 else 'results'}, of which {failed} {'reads' if failed == 1 else 'read'} Failed."
    if page == "fixes":
        n = len(facts.fixes().get("fixes") or [])
        return f"On it now: {n} {'fix' if n == 1 else 'fixes'}.{wait}"
    return f"On it now:{wait}" if wait else None


def _next(facts: Any, page: str, proposals: list[dict], out: Any) -> dict:
    told = []
    step = facts.overview_step() if facts.has_file else None
    if not facts.has_file:
        told.append(fact(words.NO_FILE, _link("inventory/import"), "Open Import"))
    elif step and step.get("page"):
        told.append(fact(f"Next: {step['label']}. {step['text']}", _link(step["page"]), f"Open {PAGE_LABELS.get(step['page'], step['label'])}"))
    else:
        told.append(fact("The Overview names no next step now.", _link("overview"), "Open Overview"))
    for kind in dict.fromkeys(p["kind"] for p in proposals if p["state"] == "proposed"):
        same = [p for p in proposals if p["kind"] == kind and p["state"] == "proposed"]
        home = HOME.get(kind, "overview")
        if step and step.get("page") == home:
            continue                                      # (the next step already sends there, and says how many)
        told.append(fact(f"{words.counted(len(same), kind).capitalize()} {'waits' if len(same) == 1 else 'wait'} for a decision on {PAGE_LABELS[home]}.",
                         _link(home), f"Open {PAGE_LABELS[home]}"))
    return out("answer", ASK["next"], question=ASK["next"], label=LABEL, facts=told, thread=PAGE_THREAD.get(page))


__all__ = ["ASK", "LABEL", "QUESTIONS", "answer", "fitting", "read"]
