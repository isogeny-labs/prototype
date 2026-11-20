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

from app.assistant import commands, questions
from app.assistant.threads import FITS, KIND_THREAD, PAGE_LABELS, PAGE_THREAD, PAGES, THREAD_LABELS
from app.errors import BadRequest
from app.otto.proposals import CLOSED, HOME

CANNOT = "I can't do that."
WHICH = "Which one?"
NO_FILE = "Bring in a scanner file first. Until then there is nothing to decide or to start."
WAITS = "Nothing happens until you press Confirm."
VERBS = {"accept": "Accept", "reject": "Reject", "undo": "Undo", "reconsider": "Reconsider"}
MAX_REASON = 300          # (the page's own limit for a reject reason: app/otto/proposals.py; a test holds the two equal)
# What "it" can be told about a button that lives on its page only: the page's own button, when one fix has it.
PAGE_BUTTONS = {"merge": "merge", "apply": "apply", "roll_back": "rollback"}
ONLY_WITH_SOMETHING_TO_RUN = ("run_picked_tests",)


def answer(copilot: Any, lab: Any, assessment_id: int, page: str, item: str | None, text: str) -> dict:
    """The answer to one typed sentence. `copilot` is the engine of phase 6a: its cards are the cards shown here."""
    from app.assistant.engine import facts_of, settled, waits       # (the engine imports this module's caller)
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
    can = commands.can_say(page, bool(proposals), moving_only=closed or not has_file)
    if key is None:
        return out("cannot", CANNOT, can=can)
    if key == "ask":
        # Phase 6c: a fixed question. Answering reads; it is the same in a closed assessment.
        facts_ = facts_of(lab, core, closed, proposals)
        fits_ = FITS.get(page, ())
        shown_ = [p for p in proposals if p["kind"] in fits_ and not settled(p)]
        shown_.sort(key=lambda p: (not _about(p, item), not waits(p)))
        return questions.answer(copilot, facts_, said, page, item, proposals, shown_, out, can)
    if key == "what_if":
        # Phase 6e, first half: what the app knows about updating one library to one version. A read: the facts are the
        # pages' own records, and the one thing that could be started (Evidence's Retest new version, pointed at that
        # version) is handed back as that button's own card, which waits for Confirm. A closed assessment gets the facts
        # too, and its button is off with the closed sentence.
        if not has_file:
            return out("cannot", NO_FILE, can=can)
        if said.get("several"):
            return out("cannot", "I can't do that. A what-if is about one library and one version at a time. Ask about the first, then "
                                 "about the other.", can=can, thread="fixing")
        return _what_if(copilot, lab, facts_of(lab, core, closed, proposals), said, out)
    if key == "help":
        return out("help", f"On {PAGE_LABELS[page]} you can tell Otto:", can=can)
    # With no file in, the app shows only the Overview and Import: nothing else can be opened yet, and it says so.
    reachable = has_file or key in ("settings",)
    if key == "open_page":
        if not has_file and said["page"] not in ("overview", "inventory/import"):
            return out("cannot", NO_FILE, can=can)
        return out("went", f"Opened {PAGE_LABELS[said['page']]}.", go=commands.go(said["page"]), thread=PAGE_THREAD[said["page"]])
    if line and line["kind"] == "page" and key not in PAGE_BUTTONS and key != "approve":
        target = line["page"]
        if not reachable and target not in ("overview", "inventory/import"):
            return out("cannot", NO_FILE, can=can)
        return out("page_only", line["done"], go=commands.go(target), thread=PAGE_THREAD.get(target))
    if not has_file:
        return out("cannot", NO_FILE, can=can)

    facts = facts_of(lab, core, closed, proposals)
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
        if closed:
            # (nothing can be approved, merged, applied or rolled back in a closed assessment: the page opens, and the
            #  answer is the closed sentence, never "the button is ready")
            return out("page_only", f"{line['done']} {core['status'].get('closed_line') or CLOSED}", go=commands.go("fixes"), thread="fixing")
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
        # (Evidence: its Result filter is the Crypto tests table's own; the other groups list every row)
        return out("went", f"Opened {name}, with the Crypto tests table filtered to {label}.", go=where, thread=PAGE_THREAD[page])
    many = {"check": "checks", "advisory": "advisories", "result": "results"}[one]
    none = f"no {one} is listed there now" if said["filter"] == "from" else f"no {one} reads {label} now"
    told = f"{count} {one if count == 1 else many}" if count else none
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
    test_names = _test_names(facts.plan())
    if kinds is None or "check" in kinds:
        for t in facts.plan().get("tests") or []:
            candidates.append({"names": [t["title"], test_names[t["id"]]], "titles": [test_names[t["id"]]], "title": test_names[t["id"]],
                               "go": commands.go("checks", f"test-{t['id']}"), "thread": "testing", "where": "Checks"})
    if kinds is None or "fix" in kinds:
        for fix in facts.fixes().get("fixes") or []:
            candidates.append({"names": [fix["title"], fix.get("list_source") or ""], "title": fix["title"], "go": commands.go("fixes", fix["id"]),
                               "thread": "fixing", "where": "Fixes"})
    found = commands.match(rest, candidates) if [t for t in commands.tokens(rest) if t not in commands.SKIP and t not in commands.KIND_WORDS] else []
    if len(found) != 1:
        # the whole title, word for word, whatever kind word it holds itself (looked for among everything, of any kind)
        everything = [{"names": [p["title"]], "title": p["title"], "go": {**commands.go(HOME.get(p["kind"], "overview")), **_link_of(p)},
                       "thread": KIND_THREAD[p["kind"]], "where": PAGE_LABELS[HOME.get(p["kind"], "overview")]} for p in proposals]
        everything += [{"names": [test_names[t["id"]]], "title": test_names[t["id"]], "go": commands.go("checks", f"test-{t['id']}"),
                        "thread": "testing", "where": "Checks"} for t in facts.plan().get("tests") or []]
        everything += [{"names": [fix["title"]], "title": fix["title"], "go": commands.go("fixes", fix["id"]), "thread": "fixing", "where": "Fixes"}
                       for fix in facts.fixes().get("fixes") or []]
        whole = _once(commands.exact(rest, everything), lambda c: (c["go"]["page"], c["go"]["item"]))
        if len(whole) == 1:
            found = whole
    found = _once(found, lambda c: (c["go"]["page"], c["go"]["item"]))
    if len(found) == 1:
        one = found[0]
        return out("went", f"Opened “{one['title']}” on {one['where']}.", go=one["go"], thread=one["thread"])
    if len(found) > 1:
        listed = found[:commands.MAX_OPTIONS]
        return out("which", commands.which_text(len(listed), len(found)),
                   options=[{"label": f"{c['title']} (on {c['where']})", "say": f"Open {commands.sayable(c['title'])}"} for c in listed])
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
            waiting = [r for r in rows if not r.get("approved_at")]          # (a row carries when it was approved, or nothing)
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
    if verb == "reject" and said.get("reason") and len(said["reason"]) > MAX_REASON:
        return out("cannot", f"A reason is one short line, {MAX_REASON} characters at most. Yours has {len(said['reason'])}. "
                             "Say it again with a shorter reason.", can=can)
    kinds = commands.kinds_named(rest)
    pool = [p for p in shown + others if kinds is None or p["kind"] in kinds]
    place = commands.ordinal(rest)
    # the whole title, word for word, whatever kind word it holds itself
    whole = commands.exact(rest, [{"names": [p["title"]], "p": p} for p in shown + others])
    if len(whole) == 1:
        pool, place = [whole[0]["p"]], None
    elif place is not None:
        # "the second suggestion": counted down the cards as the panel shows them on this page
        listed = [p for p in shown if kinds is None or p["kind"] in kinds]
        try:
            pool = [listed[place]]
        except IndexError:
            there = ("There is no suggestion" if not listed else "There is 1 suggestion" if len(listed) == 1
                     else f"There are {len(listed)} suggestions")
            return out("cannot", f"{CANNOT} {there} on this page to count down.", can=can)
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
        # only the ones this button is offered for are worth choosing between
        offered = [p for p in pool if verb in (p.get("actions") or {})]
        if not offered:
            return out("cannot", f"{VERBS[verb]} is not offered for any of the {len(pool)} suggestions that fit now. Each card says where "
                                 "it stands.", can=can)
        listed = offered[:commands.MAX_OPTIONS]
        return out("which", commands.which_text(len(listed), len(offered)),
                   options=[{"label": f"{p['title']} (on {PAGE_LABELS[HOME.get(p['kind'], 'overview')]})",
                             "say": f"{VERBS[verb]} {commands.sayable(p['title'])}" + (f": {said['reason']}" if said.get("reason") else "")}
                            for p in listed])
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
    if len(entries) > 1 and not rest and line["key"] in ONLY_WITH_SOMETHING_TO_RUN:
        # (phase 6d: every change of the page has the button, also one with nothing picked, where it is off for good.
        # Unless a person named it, such a change is not what the sentence means while another one can run or is running.)
        entries = [e for e in entries if e["step"]["can"] or e["step"].get("running")] or entries
    if len(entries) > 1:
        opened = [e for e in entries if e.get("open_item")]
        pressable = [e for e in entries if e["step"]["can"]]
        for narrower in (opened, pressable):
            if len(narrower) == 1:
                entries = narrower
                break
    if len(entries) > 1:
        listed = entries[:commands.MAX_OPTIONS]
        return out("which", commands.which_text(len(listed), len(entries)), thread=thread,
                   options=[{"label": names[e["id"]][0], "say": _say_again(line, names[e["id"]][0])} for e in listed])
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


WHAT_IF_LABEL = "From what the app knows"


# Everyday names a what-if is not read under: "Python" is also the language ("update Python to 3.12" is about the
# interpreter, which the app knows nothing about), so it is not read as python-ecdsa.
WHAT_IF_NOT_ALIASED = frozenset({"python"})


def _what_if(copilot: Any, lab: Any, facts: Any, said: dict, out: Any) -> dict:
    view = lab.whatif_view(facts.plan_id, said["library"], said["version"])
    typed = str(said["library"]).casefold()
    if not view["known"] and typed not in WHAT_IF_NOT_ALIASED:
        # an everyday name of the panel's own table ("Java" for openjdk, "ecdsa" for python-ecdsa), read only where the
        # name itself is unknown and the library it stands for is known (the review of 19 November 2026)
        for other in commands.ALIASES.get(typed, ()):
            known = lab.whatif_view(facts.plan_id, other, said["version"])
            if known["known"]:
                view = known
                break
    tried = view["test_copy"]
    entry = None
    if tried["offered"]:
        # the page's own button, as the panel offers it beside Evidence: same request, same Confirm step
        entry = next((e for e in copilot._next_steps(facts, "evidence", None, asked=True)
                      if e["what"] == "next:retest" and e["step"]["action"].get("version") == tried["version"]
                      and (e["step"]["action"].get("component") or "") == (tried["component"] or "")), None)
        if entry is None:
            tried = {**tried, "offered": False, "reason": "Retest new version does not offer that version on Evidence now."}
        elif not entry["step"]["can"]:
            tried = {**tried, "offered": False, "reason": entry["step"]["blocked_reason"] or "Retest new version can't be pressed now."}
    # the facts once more as plain lines, for the record that is kept of what was said (a line with nothing to link to
    # links to nothing; a quoted source is named in the line)
    flat = [questions.fact(f"{group['title']}: {line['text']}", line["link"], "See where" if line["link"] else None)
            for group in view["facts"] for line in (group["lines"] or [{"text": group["none"], "link": None}])]
    return out("whatif", view["title"], whatif={**view, "test_copy": tried}, entry=entry, facts=flat, label=WHAT_IF_LABEL, thread="fixing")


def _step_names(facts: Any, key: str, entries: list[dict]) -> dict[str, list[str]]:
    """What each button's card can be called in a sentence: the test, the version, the library or the fix it is for."""
    out: dict[str, list[str]] = {}
    distinct = _test_names(facts.plan()) if key == "run" else {}
    tests = {f"test-{t['id']}": distinct[t["id"]] for t in (facts.plan().get("tests") or [])} if key == "run" else {}
    for e in entries:
        action = e["step"]["action"]
        if key == "run":
            out[e["id"]] = [tests.get(f"test-{action.get('item_id')}", e.get("text") or e["title"])]
        elif key == "retest":
            version = " ".join(str(x) for x in (action.get("component"), action.get("version")) if x)
            out[e["id"]] = [version or e["title"], e.get("text") or ""]
        elif key == "run_picked_tests":         # (a change is called by its title or its branch)
            change = next((c for c in facts.change_watch().get("changes") or [] if c["id"] == action.get("change")), None)
            out[e["id"]] = [change["title"], change["branch"]] if change else [e.get("text") or e["title"]]
        else:
            out[e["id"]] = [e.get("text") or e["title"], e["title"]]
    return out


def _say_again(line: dict, name: str) -> str:
    """A sentence that names exactly this one, for "Which one?"."""
    key, name = line["key"], commands.sayable(name)
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
    return commands.names_of(p)


def _test_names(plan: dict) -> dict[int, str]:
    """A name for each test of the plan that no other test has (where two share a title: with its target)."""
    headings = {g["key"]: g["heading"] for g in plan.get("groups") or []}
    return commands.distinct([(t["id"], t["title"], headings.get(t.get("group"))) for t in plan.get("tests") or []])


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
