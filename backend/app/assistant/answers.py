"""Phase 6b: what Otto answers to one typed sentence, beside one page of one assessment.

A read, like the panel's own: it decides, starts, stores and changes nothing, and asks no model. The sentence is read
by the fixed rules of `commands.py`; this file finds what the words name among the assessment's own items and says
where to go, or hands back the card of phase 6a with its Confirm step. Only the browser's Confirm sends anything, and
it sends the page button's own request.

    went       moving around: the page (or the item, or the filtered table) to open, and one line that says where
    card       a decision or a start: the entry of phase 6a, and which of its buttons to show the Confirm step of
    which      several things fit the words: "Which one?", with a sentence for each that names it exactly
    cannot     nothing fits, or the button is off (then with the page's own reason), with what can be said here
    help       what can be said on this page, from the one list
    page_only  done on its page only: the page to open, and what it still needs
    tab        a tab of the panel to open or close
    closed     the assessment is closed: the closed sentence
"""
from __future__ import annotations

from typing import Any

from app.assistant import commands
from app.assistant.threads import FITS, KIND_THREAD, PAGE_LABELS, PAGE_THREAD, PAGES, THREAD_LABELS
from app.errors import BadRequest
from app.otto.proposals import CLOSED, HOME

CANNOT = "I can't do that."
WHICH = "Which one?"
NO_FILE = "Bring in a scanner file first. Until then there is nothing to decide or to start."
WAITS = "Nothing happens until you press Confirm."
VERBS = {"accept": "Accept", "reject": "Reject", "undo": "Undo", "reconsider": "Reconsider"}
# What "it" can be told about a button that lives on its page only: the page's own button, when one fix has it.
PAGE_BUTTONS = {"merge": "merge", "apply": "apply", "roll_back": "rollback"}


def answer(copilot: Any, lab: Any, assessment_id: int, page: str, item: str | None, text: str) -> dict:
    """The answer to one typed sentence. `copilot` is the engine of phase 6a: its cards are the cards shown here."""
    from app.assistant.engine import _Facts, settled, waits         # (the engine imports this module's caller)
    if page not in PAGES:
        raise BadRequest("That page is not part of an assessment.", field="page")
    said = commands.read(text)
    if not said["said"]:
        raise BadRequest("Type where to go or what to do.", field="text")
    item = (item or None) and str(item)[:200]
    core = lab.assessment_core(assessment_id)
    closed = core["status"]["key"] == "closed"
    key = said["key"]
    line: dict = commands.BY_KEY.get(key or "") or {}          # (empty only for a sentence no rule reads)
    here = PAGE_THREAD[page]

    def out(kind: str, text_: str, **more: Any) -> dict:
        return commands.reply(kind, text_, thread=more.pop("thread", here), **more)

    has_file = core["import_id"] is not None and core["plan_id"] is not None
    proposals = lab.otto_proposals(core["plan_id"]) if has_file else []
    can = commands.can_say(page, bool(proposals))
    if key is None:
        return out("cannot", CANNOT, can=can)
    if key == "help":
        return out("help", f"On {PAGE_LABELS[page]} you can tell Otto:", can=can)
    if key == "open_page":
        return out("went", f"Opened {PAGE_LABELS[said['page']]}.", go=commands.go(said["page"]), thread=PAGE_THREAD[said["page"]])
    if line and line["kind"] == "page" and key not in PAGE_BUTTONS and key != "approve":
        target = line["page"]
        return out("page_only", line["done"], go=commands.go(target), thread=PAGE_THREAD.get(target))
    if not has_file:
        return out("cannot", NO_FILE, can=can)

    facts = _Facts(lab, core, closed)
    # the suggestions as the panel shows them: those that fit this page first, in the panel's own order
    fits = FITS.get(page, ())
    shown = [p for p in proposals if p["kind"] in fits and not settled(p)]
    shown.sort(key=lambda p: (not _about(p, item), not waits(p)))
    others = [p for p in proposals if p not in shown]

    if key == "tab":
        suggestions = {p["id"]: copilot._suggestion(p, item) for p in proposals}
        open_tabs = {t["key"] for t in copilot._tabs(facts, proposals, suggestions)}
        label = THREAD_LABELS[said["thread"]]
        if said["thread"] not in open_tabs:
            return out("cannot", f"There is no {label} tab yet: nothing has happened in that thread.", can=can)
        return out("tab", f"{'Closed' if said['how'] == 'close' else 'Opened'} the {label} tab.",
                   tab={"thread": said["thread"], "how": said["how"]}, thread=said["thread"])

    if key == "filter":
        return _filter(lab, facts, said, out)

    if key == "open_item":
        return _open_item(copilot, facts, said, shown + others, item, out, can)

    if key in PAGE_BUTTONS or key == "approve":
        return _page_only(facts, key, line, said, item, out)

    # ---- from here on: a decision or a start. Nothing of it happens here: the answer is a card and its Confirm step.
    if closed:
        return out("closed", core["status"].get("closed_line") or CLOSED)

    if key in commands.DECISIONS:
        return _decision(copilot, said, key, shown, others, item, out, can)
    return _start(copilot, facts, said, line, page, item, out, can)


# ------------------------------------------------------------------ moving around

def _filter(lab: Any, facts: Any, said: dict, out: Any) -> dict:
    page, value, label, one = said["page"], said["value"], said["label"], said["one"]
    name = PAGE_LABELS[page]
    count: int | None = None
    if page == "checks":
        count = _checks_listed(lab.checks_view(facts.plan_id), said["filter"], value)
        where = commands.go(page, result=value) if said["filter"] == "result" else commands.go(page, came_from=value)
    elif page == "advisories":
        rows = lab.advisories_view(facts.plan_id).get("rows") or []
        count = sum(1 for r in rows if r["proposal"]["key"] == value or value in (r["proposal"].get("keys") or []))
        where = commands.go(page, decision=value)
    else:
        where = commands.go(page, result=value)
    if count is None:
        return out("went", f"Opened {name}, filtered to {label}.", go=where, thread=PAGE_THREAD[page])
    many = {"check": "checks", "advisory": "advisories", "result": "results"}[one]
    told = f"{count} {one if count == 1 else many}" if count else f"no {one} reads {label} now"
    return out("went", f"Opened {name}, filtered to {label}: {told}.", go=where, thread=PAGE_THREAD[page])


def _checks_listed(view: dict, which: str, value: str) -> int:
    """How many checks the Checks page lists under this filter: each test of the plan once, then the rows of each
    retest and each proof block, the tries, and the rows of the other groups."""
    def fits(row: dict) -> bool:
        if which == "result":
            return ((row.get("result") or {}).get("label")) == value
        return (row.get("came_from") or {}).get("key") == value
    n = 0
    for group in view.get("groups") or []:
        parts = group.get("parts")
        if not parts:
            n += sum(1 for r in group.get("rows") or [] if fits(r))
            continue
        n += sum(1 for r in group.get("rows") or [] if str(r["id"]).startswith("test-") and fits(r))
        for part in ("retests", "proofs"):
            n += sum(1 for block in (parts.get(part) or {}).get("blocks") or [] for r in block.get("rows") or [] if fits(r))
        n += sum(1 for r in (parts.get("tries") or {}).get("rows") or [] if fits(r))
    return n


def _open_item(copilot: Any, facts: Any, said: dict, proposals: list[dict], item: str | None, out: Any, can: list[dict]) -> dict:
    rest = said["rest"]
    kinds = commands.kinds_named(rest)
    candidates: list[dict] = []
    for p in proposals:
        if kinds is None or p["kind"] in kinds:
            candidates.append({"names": _names_of(p), "title": p["title"], "go": {**commands.go(HOME.get(p["kind"], "overview")), **_link_of(p)},
                               "thread": KIND_THREAD[p["kind"]], "where": PAGE_LABELS[HOME.get(p["kind"], "overview")]})
    if kinds is None or "check" in kinds:
        for t in facts.plan().get("tests") or []:
            candidates.append({"names": [t["title"]], "title": t["title"], "go": commands.go("checks", f"test-{t['id']}"), "thread": "testing",
                               "where": "Checks"})
    if kinds is None or "fix" in kinds:
        for fix in facts.fixes().get("fixes") or []:
            candidates.append({"names": [fix["title"], fix.get("list_source") or ""], "title": fix["title"], "go": commands.go("fixes", fix["id"]),
                               "thread": "fixing", "where": "Fixes"})
    found = commands.match(rest, candidates) if [t for t in commands.tokens(rest) if t not in commands.SKIP and t not in commands.KIND_WORDS] else []
    found = _once(found, lambda c: (c["go"]["page"], c["go"]["item"]))
    if len(found) == 1:
        one = found[0]
        return out("went", f"Opened “{one['title']}” on {one['where']}.", go=one["go"], thread=one["thread"])
    if len(found) > 1:
        return out("which", WHICH, options=[{"label": f"{c['title']} (on {c['where']})", "say": f"Open {c['title']}"}
                                             for c in found[:commands.MAX_OPTIONS]])
    return out("cannot", CANNOT + " Nothing here is called that.", can=can)


def _page_only(facts: Any, key: str, line: dict, said: dict, item: str | None, out: Any) -> dict:
    """Approve, Merge pull request, Apply and Roll back stay on Fixes. The command opens the fix that has the button
    and says, in the page's own words, what it still needs."""
    fixes = facts.fixes().get("fixes") or []
    action = PAGE_BUTTONS.get(key)
    having = []
    for fix in fixes:
        buttons = list((fix.get("actions") or {}).get("buttons") or []) + list((fix.get("change_box") or {}).get("buttons") or [])
        if key == "approve":
            rows = list((fix.get("approvers") or {}).get("rows") or []) + list(((fix.get("change_box") or {}).get("approvals") or {}).get("rows") or [])
            waiting = [r for r in rows if not r.get("approved") and r.get("state") != "approved"]
            if rows and waiting:
                having.append((fix, None, f"{_count(len(waiting), 'approval is', 'approvals are')} still missing."))
            continue
        for b in buttons:
            if b.get("action") == action:
                why = None if b.get("enabled") else (b.get("reason") or (fix.get("actions") or {}).get("note") or "Its page says what it still needs.")
                having.append((fix, b, f"The button is ready on the page: {b['label']}." if why is None else str(why)))
    open_fix = [h for h in having if h[0]["id"] == item]
    chosen = open_fix or having
    if len(chosen) == 1:
        fix, _, told = chosen[0]
        return out("page_only", f"{line['done']} {told}", go=commands.go("fixes", fix["id"]), thread="fixing")
    if not chosen:
        return out("page_only", f"{line['done']} Nothing on Fixes is waiting for that now.", go=commands.go("fixes"), thread="fixing")
    return out("page_only", f"{line['done']} {_count(len(chosen), 'fix has', 'fixes have')} that button: open the one you mean on Fixes.",
               go=commands.go("fixes"), thread="fixing")


# ------------------------------------------------------------------ a decision on a suggestion

def _decision(copilot: Any, said: dict, verb: str, shown: list[dict], others: list[dict], item: str | None, out: Any, can: list[dict]) -> dict:
    rest = said["rest"]
    kinds = commands.kinds_named(rest)
    pool = [p for p in shown + others if kinds is None or p["kind"] in kinds]
    place = commands.ordinal(rest)
    if place is not None:
        # "the second suggestion": counted down the cards as the panel shows them on this page
        listed = [p for p in shown if kinds is None or p["kind"] in kinds]
        try:
            pool = [listed[place]]
        except IndexError:
            return out("cannot", f"{CANNOT} There {'is' if len(listed) == 1 else 'are'} {_count(len(listed), 'suggestion', 'suggestions')} "
                                 "on this page to count down.", can=can)
    else:
        named = commands.match(rest, [{"names": _names_of(p), "p": p} for p in pool])
        pool = [c["p"] for c in named]
    if not pool:
        return out("cannot", CANNOT + " No suggestion here is called that.", can=can)
    if len(pool) > 1:
        # narrow it down without guessing: the open item's suggestion, then the ones this button is offered for
        about = [p for p in pool if _about(p, item)]
        offered = [p for p in pool if verb in (p.get("actions") or {})]
        for narrower in (about, [p for p in about if p in offered], offered):
            if len(narrower) == 1:
                pool = narrower
                break
    if len(pool) > 1:
        return out("which", WHICH, options=[{"label": f"{p['title']} (on {PAGE_LABELS[HOME.get(p['kind'], 'overview')]})",
                                             "say": f"{VERBS[verb]} {p['title']}" + (f": {said['reason']}" if said.get("reason") else "")}
                                            for p in pool[:commands.MAX_OPTIONS]])
    proposal = pool[0]
    entry = copilot._suggestion(proposal, item)
    thread = KIND_THREAD[proposal["kind"]]
    button = next((d for d in entry["decisions"] if d["key"] == verb), None)
    where = PAGE_LABELS[HOME.get(proposal["kind"], "overview")]
    if button is None:
        return out("cannot", f"{VERBS[verb]} is not offered for “{entry['title']}” now. It reads “{entry['badge']['label']}”.",
                   entry=entry, thread=thread)
    if not button["can"] or not button.get("confirm"):
        return out("cannot", str(button.get("blocked_reason") or f"{VERBS[verb]} can't be pressed for this suggestion now."), entry=entry, thread=thread)
    return out("card", f"{VERBS[verb]} “{entry['title']}”, on {where}. {WAITS}", entry=entry,
               open={"key": verb, "reason": said.get("reason") if verb == "reject" else None}, thread=thread)


# ------------------------------------------------------------------ a start: a page's own button

def _start(copilot: Any, facts: Any, said: dict, line: dict, page: str, item: str | None, out: Any, can: list[dict]) -> dict:
    home = line["page"]
    if line["key"] == "measure_status" and page == "migration/roadmap":
        home = page
    entries = [e for e in copilot._next_steps(facts, home, item if page == home else None, asked=True) if e["what"] == line["what"]]
    button = line["say"] if line["key"] not in ("run", "retest", "measure_library") else commands._button(line["key"])
    thread = PAGE_THREAD[home]
    if not entries:
        return out("cannot", f"{PAGE_LABELS[home]} has no {button} button to press now.", can=can, thread=thread)
    rest = said.get("rest") or ""
    names = _step_names(facts, line["key"], entries)
    if rest:
        entries = [c["e"] for c in commands.match(rest, [{"names": names[e["id"]], "e": e} for e in entries])]
        if not entries:
            return out("cannot", f"{CANNOT} {PAGE_LABELS[home]} has no {button} button for that.", can=can, thread=thread)
    if len(entries) > 1:
        opened = [e for e in entries if e.get("open_item")]
        pressable = [e for e in entries if e["step"]["can"]]
        for narrower in (opened, pressable):
            if len(narrower) == 1:
                entries = narrower
                break
    if len(entries) > 1:
        return out("which", WHICH, thread=thread, options=[{"label": names[e["id"]][0], "say": _say_again(line, names[e["id"]][0])}
                                                            for e in entries[:commands.MAX_OPTIONS]])
    entry = entries[0]
    step = entry["step"]
    if step["needs"] == "nothing":
        return out("went", f"Opened {PAGE_LABELS[home]}.", go=commands.go(home), thread=thread)
    if not step["can"] or not step.get("confirm"):
        return out("cannot", str(step.get("blocked_reason") or (step.get("progress") if step.get("running") else None)
                                 or f"{entry['title']} can't be pressed now."), entry=entry, thread=thread)
    # (which test, version or library the button is for, where the button's own name does not say)
    named = names[entry["id"]][0]
    what = f"{entry['title']}: {named}" if line["key"] in ("run", "retest", "measure_library") and named and named != entry["title"] else entry["title"]
    return out("card", f"{what}, on {PAGE_LABELS[home]}. {WAITS}", entry=entry, open={"key": "step", "reason": None}, thread=thread)


def _step_names(facts: Any, key: str, entries: list[dict]) -> dict[str, list[str]]:
    """What each button's card can be called in a sentence: the test, the version, the library or the fix it is for."""
    out: dict[str, list[str]] = {}
    tests = {f"test-{t['id']}": t["title"] for t in (facts.plan().get("tests") or [])} if key == "run" else {}
    for e in entries:
        action = e["step"]["action"]
        if key == "run":
            out[e["id"]] = [tests.get(f"test-{action.get('item_id')}", e.get("text") or e["title"])]
        elif key == "retest":
            version = " ".join(str(x) for x in (action.get("component"), action.get("version")) if x)
            out[e["id"]] = [version or e["title"], e.get("text") or ""]
        else:
            out[e["id"]] = [e.get("text") or e["title"], e["title"]]
    return out


def _say_again(line: dict, name: str) -> str:
    """A sentence that names exactly this one, for "Which one?"."""
    key = line["key"]
    if key == "run":
        return f"Run {name}"
    if key == "retest":
        return f"Retest on {name}"
    if key == "measure_library":
        return f"Measure {name}"
    return f"{line['say']} for {name}"


# ------------------------------------------------------------------ small things

def _names_of(p: dict) -> list[str]:
    """What a suggestion can be called: its title, and what it is about (the advisory, the library, the program)."""
    about = p.get("about") or {}
    return [str(p.get("title") or "")] + [str(v) for v in about.values() if isinstance(v, (str, int)) and not isinstance(v, bool)]


def _link_of(p: dict) -> dict:
    link = p.get("link") or {}
    return {"item": link.get("item"), "group": link.get("group")}


def _about(p: dict, item: str | None) -> bool:
    from app.assistant.engine import _about as about
    return about(p, item)


def _once(found: list[dict], key: Any) -> list[dict]:
    seen: set = set()
    out = []
    for c in found:
        k = key(c)
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def _count(n: int, one: str, many: str) -> str:
    return f"{'One' if n == 1 else n} {one if n == 1 else many}"


__all__ = ["CANNOT", "WHICH", "answer"]
