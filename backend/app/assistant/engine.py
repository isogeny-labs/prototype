"""The rule-based engine behind the Otto panel (phase 6a): one read, for one assessment, one page and one open item.

The answer holds the open tabs, what fits this page, what waits elsewhere and the status line. It is worked out again
on every read from records the pages already show, through the same views the pages draw from, so a button in the
panel can be pressed exactly when its page's button can, and reads the same reason when it cannot. Nothing is stored
for it, nothing is started, and no model is asked.

Three kinds of entry:
    a suggestion   one of Otto's proposals, marked "From Otto": the same proposal its page shows, with the same words
    a next step    a button of the page that is worth pressing now, under that button's own name
    what this means   a result's own plain sentence, with the way to its evidence

The engine presses nothing. For a decision or a start it only describes the request the page's own button sends; the
browser sends that request on Confirm.
"""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.assistant import words
from app.assistant.threads import ENTRY_KINDS, FITS, KIND_THREAD, PAGE_LABELS, PAGE_THREAD, PAGES, THREAD_LABELS, THREADS, thread_of
from app.errors import BadRequest, NotFound
from app.otto import harness
from app.otto.proposals import CLOSED, HOME, accept_stands
from app.present import otto as present_otto

MAX_STEPS = 3          # at most this many next steps of one kind under "On this page" (the open item's come first)
MAX_MEANINGS = 6


class CopilotEngine(Protocol):
    """What the panel asks. There is one question, and it only reads."""

    def read(self, lab: Any, assessment_id: int, page: str, item: str | None = None) -> dict: ...


def _entry(what: str, entry_id: str, *, mark: str, title: str, page: str | None = None, **more: Any) -> dict:
    """One entry of the panel. `what` must be a line of the table of kinds: there is no other way to make an entry."""
    if what not in ENTRY_KINDS:
        raise ValueError(f"not a kind of entry: {what}")
    return {"id": entry_id, "kind": what.split(":")[0], "what": what, "thread": thread_of(what, page), "mark": mark, "title": title,
            "text": more.pop("text", None), "at": more.pop("at", None), "badge": more.pop("badge", None), "where": more.pop("where", None),
            "links": more.pop("links", []), "proposal": more.pop("proposal", None), "decisions": more.pop("decisions", []),
            "step": more.pop("step", None), "open_item": bool(more.pop("open_item", False)), **more}


def _link(page: str, item: object = None, group: str | None = None) -> dict:
    return {"page": page, "item": str(item) if item is not None else None, "group": group}


def _step(action: dict, *, can: bool, reason: str | None, confirm: dict | None, needs: str = "confirm", running: bool = False,
          progress: str | None = None) -> dict:
    base = {"type": None, "plan_id": None, "import_id": None, "item_id": None, "fix_id": None, "change": None, "row": None, "version": None,
            "component": None, "reviewers": None, "link": None}
    return {"needs": needs, "action": {**base, **action}, "can": bool(can), "blocked_reason": None if can else reason,
            "running": bool(running), "progress": progress, "confirm": confirm if can else None}


def settled(proposal: dict) -> bool:
    """True when no decision can be made on this proposal any more, whoever asks: it is no longer made, its accept
    stands (what it led to has run or been applied), or it was added before decisions were recorded."""
    if not proposal.get("current", True):
        return True
    if proposal["state"] == "accepted":
        return bool(proposal.get("legacy")) or accept_stands(proposal) is not None
    if proposal["state"] == "rejected":
        return bool((proposal.get("facts") or {}).get("done"))
    return False


def waits(proposal: dict) -> bool:
    return proposal["state"] == "proposed" and bool(proposal.get("current", True))


def _about(proposal: dict, item: str | None) -> bool:
    """Is this proposal about the item that is open on the page?"""
    if not item:
        return False
    facts = proposal.get("facts") or {}
    names = {str((proposal.get("link") or {}).get("item"))}
    if facts.get("item_id") is not None:
        names.add(f"test-{facts['item_id']}")
    if facts.get("fix_id"):
        names.add(str(facts["fix_id"]))
    names |= {str(r) for r in facts.get("rows") or []}
    return item in names


def _proposal_at(proposal: dict) -> str | None:
    decisions = proposal.get("decisions") or []
    return (decisions[-1]["at"] if decisions else None) or proposal.get("proposed_at")


class RuleCopilot:
    """The assistant with no AI model: fixed rules over the assessment's records."""

    # ------------------------------------------------------------------ the read

    def read(self, lab: Any, assessment_id: int, page: str, item: str | None = None) -> dict:
        if page not in PAGES:
            raise BadRequest("That page is not part of an assessment.", field="page")
        item = (item or None) and str(item)[:200]
        core = lab.assessment_core(assessment_id)
        closed = core["status"]["key"] == "closed"
        installed = harness.public_status()
        notices = ([core["status"]["closed_line"] or CLOSED] if closed else []) + \
                  ([installed["sentence"]] if not installed["installed"] else [])
        base = {"assessment_id": assessment_id, "plan_id": core["plan_id"], "title": words.TITLE, "status": words.status(lab.otto_live_ready()),
                "notices": notices, "note": words.LOOKING, "recorded_as": lab.decision_name_view(), "page": page,
                "page_label": PAGE_LABELS[page], "thread": PAGE_THREAD[page]}
        if core["import_id"] is None or core["plan_id"] is None:
            link = None if page == "inventory/import" else {"label": "Open Import", "link": _link("inventory/import")}
            return {**base, "tabs": [], "on_page": {"title": words.ON_PAGE, "entries": [], "empty": words.NO_FILE, "empty_link": link},
                    "elsewhere": {"title": words.elsewhere_title(0), "count": 0, "lines": [], "empty": None}, "waiting": 0, "busy": False}
        facts = _Facts(lab, core, closed)
        proposals = lab.otto_proposals(core["plan_id"])
        # (as on the Overview: where nothing can be decided, nothing counts as waiting for its next step)
        facts.waiting = ({kind: sum(1 for p in proposals if p["kind"] == kind and waits(p)) for kind in KIND_THREAD}
                         if not closed and installed["installed"] else {})
        suggestions = {p["id"]: self._suggestion(p, item) for p in proposals}

        # On this page: the suggestions that fit it and can still be decided, then its next steps, then what its results mean.
        fits = FITS.get(page, ())
        here = [p for p in proposals if p["kind"] in fits and not settled(p)]
        here.sort(key=lambda p: (not _about(p, item), not waits(p)))
        steps = self._next_steps(facts, page, item)
        meanings = self._meanings(facts, page, item)
        on_page = [suggestions[p["id"]] for p in here] + steps + meanings

        # Elsewhere: every suggestion nobody has decided that is not already above, one line for each page it lives on.
        shown = {p["id"] for p in here}
        waiting_elsewhere = [p for p in proposals if waits(p) and p["id"] not in shown]
        lines = []
        for home in PAGES:
            mine = [p for p in waiting_elsewhere if HOME.get(p["kind"]) == home]
            for kind in dict.fromkeys(p["kind"] for p in mine):
                same = [p for p in mine if p["kind"] == kind]
                more = f" and {len(same) - 1} more" if len(same) > 1 else ""
                lines.append({"text": f"{PAGE_LABELS[home]}: {words.counted(len(same), kind)}, {same[0]['title']}{more}", "count": len(same),
                              "link": _link(home, same[0]["link"].get("item") if len(same) == 1 else None), "thread": KIND_THREAD[kind]})
        waiting_here = sum(1 for p in here if waits(p))
        nothing = waiting_here == 0 and not waiting_elsewhere

        tabs = self._tabs(facts, proposals, suggestions)
        return {**base, "tabs": tabs,
                "on_page": {"title": words.ON_PAGE, "entries": on_page, "empty": None if on_page else words.NOTHING_HERE, "empty_link": None},
                "elsewhere": {"title": words.elsewhere_title(len(waiting_elsewhere)), "count": len(waiting_elsewhere), "lines": lines,
                              "empty": words.NOTHING_WAITING if nothing else None},
                "waiting": waiting_here + len(waiting_elsewhere), "busy": facts.busy()}

    # ------------------------------------------------------------------ suggestions

    def _suggestion(self, p: dict, item: str | None) -> dict:
        """One of Otto's proposals as the panel shows it: the page's own card in short, with the Confirm step of each
        button the page offers. The words and the button states are the page's (`present.otto.proposal_view`)."""
        view = present_otto.proposal_view(p)
        home = HOME.get(p["kind"], "overview")
        decisions = [{"key": b["key"], "label": b["label"], "can": b["can"], "blocked_reason": b["blocked_reason"],
                      "confirm": words.decision_confirm(p["kind"], b["key"], view["kind_label"], b["label"], PAGE_LABELS[home]) if b["can"] else None}
                     for b in view["buttons"]]
        return _entry(f"suggestion:{p['kind']}", p["id"], mark=view["label"], title=view["title"], text=view["why"], at=_proposal_at(p),
                      badge={"label": view["status"]["word"], "tone": view["status"]["tone"]},
                      where={"label": f"On {PAGE_LABELS[home]}", "link": view["link"]}, proposal=view, decisions=decisions,
                      open_item=_about(p, item))

    # ------------------------------------------------------------------ next steps: a button of the page, by its own name

    def _next_steps(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        builders = {"overview": self._next_overview, "inventory/import": self._next_import, "inventory/verify": self._next_verify,
                    "checks": self._next_checks, "evidence": self._next_evidence, "fixes": self._next_fixes,
                    "migration/dependencies": self._next_dependencies, "migration/systems": self._next_migration,
                    "migration/roadmap": self._next_migration}
        build = builders.get(page)
        return build(facts, page, item) if build else []

    def _next_overview(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        step = facts.overview_step()
        if not step or step.get("page") in (None, "overview"):
            return []
        return [_entry("next:open", f"next:open:{step['page']}", page=step["page"], mark=words.MARK_NEXT, title=step["label"], text=step["text"],
                       where={"label": f"On {PAGE_LABELS['overview']}", "link": _link("overview")},
                       step=_step({"type": "open", "link": _link(step["page"])}, can=True, reason=None, confirm=None, needs="nothing"))]

    def _next_import(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        if facts.verified():
            return []
        waiting = facts.waiting_for_ticks()
        label = "Verify claims"
        return [_entry("next:verify", "next:verify", mark=words.MARK_NEXT, title=label,
                       text="Check each claim in the file against the real system.",
                       where={"label": "On Import", "link": _link("inventory/import")},
                       step=_step({"type": "verify", "import_id": facts.import_id}, can=not waiting and not facts.closed,
                                  reason=facts.closed_reason() or "Tick the box for each address on Import first.",
                                  confirm=words.step_confirm(
                                      "Verify claims?",
                                      ["Checks each claim in the file against the real system.",
                                       "It contacts only the addresses ticked on Import, with handshakes only.",
                                       "It changes nothing on any system. Then the Verify page opens."], label, "Import")))]

    def _next_verify(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        if not facts.verified() or facts.plan().get("has_results"):
            return []
        return [_entry("next:open", "next:open:checks", page="checks", mark=words.MARK_NEXT, title="Continue to checks",
                       text="The test plan is on Checks. Opening it runs nothing.",
                       where={"label": "On Verify", "link": _link("inventory/verify")},
                       step=_step({"type": "open", "link": _link("checks")}, can=True, reason=None, confirm=None, needs="nothing"))]

    def _next_checks(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        plan = facts.plan()
        tests = plan.get("tests") or []
        out: list[dict] = []
        unrun = [t for t in tests if t.get("result") is None and t.get("status") == "not_run"]
        live = [t for t in tests if t.get("status") in ("waiting", "running")]
        where = {"label": "On Checks", "link": _link("checks", group="encryption")}
        if len(unrun) >= 2 or (live and not unrun):
            n, ran = len(tests), len(tests) - len(unrun)
            out.append(_entry("next:run_all", "next:run_all", mark=words.MARK_NEXT, title="Run all",
                              text=(f"{len(unrun)} of the {n} tests in the plan have not run yet." if unrun else "The tests of the plan are running."),
                              where=where,
                              step=_step({"type": "run_all", "plan_id": facts.plan_id}, can=bool(plan.get("can_run_all")) and not facts.closed,
                                         reason=facts.closed_reason() or "Tests are running. Wait for them to finish.",
                                         running=bool(live), progress=f"{len(live)} still running" if live else None,
                                         confirm=words.step_confirm(
                                             "Run all?",
                                             [f"Runs every test in the plan ({n}), on this computer.",
                                              (f"{ran} of them already {'has' if ran == 1 else 'have'} a result and run again." if ran else ""),
                                              "The runner runs each test and the separate reviewer decides its result."], "Run all", "Checks"))))
        # (a card of its own for an advisory check that has not run, for the test that is open on the page, and for the
        # one test that is left; the other tests of the plan go by Run all)
        own = [t for t in unrun if t.get("kind") == "advisory_cases" or item == f"test-{t['id']}" or len(unrun) == 1]
        for t in sorted(own, key=lambda t: item != f"test-{t['id']}")[:MAX_STEPS]:
            out.append(_entry("next:run", f"next:run:{t['id']}", mark=words.MARK_NEXT, title="Run", text=f"{t['title']} has not run yet.",
                              where={"label": "On Checks", "link": _link("checks", f"test-{t['id']}")}, open_item=item == f"test-{t['id']}",
                              step=_step({"type": "run", "plan_id": facts.plan_id, "item_id": t["id"]}, can=bool(t.get("can_run")) and not facts.closed,
                                         reason=facts.closed_reason() or "Tests are running. Wait for them to finish.",
                                         confirm=words.step_confirm(
                                             "Run this test?",
                                             [f"Runs “{t['title']}” once, on this computer.",
                                              "The runner runs it and the separate reviewer decides its result."], "Run", "Checks"))))
        return out

    def _next_evidence(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        view = facts.lab()
        retest = view.get("retest") or {}
        if not retest or not (view.get("rows") or []):
            return []
        where = {"label": "On Evidence", "link": _link("evidence")}
        label = "Retest new version"
        if retest.get("running"):
            return [_entry("next:retest", "next:retest", mark=words.MARK_NEXT, title=label, text=retest.get("progress_text") or "A retest is running.",
                           where=where, step=_step({"type": "retest", "plan_id": facts.plan_id}, can=False, reason="A retest is running.", confirm=None,
                                                   running=True, progress=retest.get("progress_text")))]
        versions = retest.get("versions") or []
        if not retest.get("can_start") or not versions:
            if not retest.get("blocked_reason"):
                return []
            return [_entry("next:retest", "next:retest", mark=words.MARK_NEXT, title=label, text="Reruns every test in the plan on another version.",
                           where=where, step=_step({"type": "retest", "plan_id": facts.plan_id}, can=False,
                                                   reason=facts.closed_reason() or retest["blocked_reason"], confirm=None))]
        out = []
        for v in versions[:MAX_STEPS]:
            out.append(_entry("next:retest", f"next:retest:{v.get('component') or ''}:{v['version']}", mark=words.MARK_NEXT, title=label,
                              text=f"{v['label']}: {v['note']}", where=where,
                              step=_step({"type": "retest", "plan_id": facts.plan_id, "version": v["version"], "component": v.get("component")},
                                         can=not facts.closed, reason=facts.closed_reason(),
                                         confirm=words.step_confirm(
                                             "Retest this version?",
                                             [f"Reruns every test in the plan on {v['label']}.", str(retest.get("menu_note") or ""),
                                              "The first results stay as they are. The retest's results show beside them, under that version."],
                                             label, "Evidence"))))
        return out

    def _next_fixes(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        out: list[dict] = []
        fixes = facts.fixes().get("fixes") or []
        for fix in sorted(fixes, key=lambda f: f["id"] != item):
            opened = fix["id"] == item
            where = {"label": "On Fixes", "link": _link("fixes", fix["id"])}
            note = (fix.get("actions") or {}).get("note")
            for button in (fix.get("actions") or {}).get("buttons") or []:
                made = self._fix_step(facts, fix, button, note, where, opened)
                if made is not None:
                    out.append(made)
            box = fix.get("change_box") or {}
            for button in box.get("buttons") or []:
                made = self._try_step(facts, fix, box, button, where, opened)
                if made is not None:
                    out.append(made)
            picker = (box.get("approvals") or {}).get("picker")
            if picker:
                made = self._approval_step(facts, fix, box, picker, where, opened)
                if made is not None:
                    out.append(made)
        # (the open fix's steps first, then what can be pressed, a few at most)
        out.sort(key=lambda e: (not e["open_item"], not e["step"]["can"]))
        return out[:MAX_STEPS + 1]

    def _fix_step(self, facts: "_Facts", fix: dict, button: dict, note: str | None, where: dict, opened: bool) -> dict | None:
        action, label, plan_id = button["action"], button["label"], facts.plan_id
        can = bool(button.get("enabled")) and not facts.closed
        if not can and not opened:
            return None             # a button that is off is only listed for the fix that is open
        reason = facts.closed_reason() or note or "This is not available yet. Its page says why."
        title = fix["title"]
        if action == "connect":
            lines = ["Connects the bundled demo repository to this assessment and puts the change on a branch of its own.",
                     "Then the proof runs: every locked test again, on the changed code.", "It merges nothing."]
            pending = [line for line in (fix.get("proposal") or {}).get("lines") or [] if "Claude" in line or line.startswith("What that click sends")]
            return _entry("next:connect", f"next:connect:{fix['id']}", mark=words.MARK_NEXT, title=label, text=title, where=where, open_item=opened,
                          step=_step({"type": "connect", "plan_id": plan_id, "fix_id": fix["id"]}, can=can, reason=reason,
                                     confirm=words.step_confirm("Connect the demo code?", lines + pending, label, "Fixes")))
        if action == "run_proof_again":
            return _entry("next:run_proof_again", f"next:proof:{fix['id']}", mark=words.MARK_NEXT, title=label, text=title, where=where, open_item=opened,
                          step=_step({"type": "run_proof_again", "plan_id": plan_id, "fix_id": fix["id"]}, can=can, reason=reason,
                                     confirm=words.step_confirm("Run the proof again?",
                                                                ["Runs the proof again: every locked test, on the changed code.", "It merges nothing."],
                                                                label, "Fixes")))
        if action == "open_pull_request":
            options = (fix.get("approvers") or {}).get("options") or []
            ticked = [o for o in options if o.get("checked")]
            if not ticked and can:
                can, reason = False, "Tick who should review on Fixes first."
            names = words.join_names([o["name"] for o in ticked])
            return _entry("next:open_pull_request", f"next:pull_request:{fix['id']}", mark=words.MARK_NEXT, title=label, text=title, where=where,
                          open_item=opened,
                          step=_step({"type": "open_pull_request", "plan_id": plan_id, "fix_id": fix["id"], "reviewers": [o["id"] for o in ticked]},
                                     can=can, reason=reason,
                                     confirm=words.step_confirm(
                                         "Open the pull request?",
                                         [f"Opens a pull request for this change inside the app and asks {names} to review it.",
                                          "These are the reviewers ticked by default on Fixes. To pick others, open the fix on its page.",
                                          "It merges nothing: a merge needs every approval and your own click on Fixes."], label, "Fixes")))
        if action == "retest_now":
            return _entry("next:retest_now", f"next:retest_now:{fix['id']}", mark=words.MARK_NEXT, title=label, text=title, where=where, open_item=opened,
                          step=_step({"type": "retest_now", "plan_id": plan_id, "fix_id": fix["id"]}, can=can, reason=reason,
                                     confirm=words.step_confirm(
                                         "Retest now?",
                                         ["Reruns every test in the plan on the version the merged change gives, as Retest new version does.",
                                          "The first results stay as they are. The retest's results show in Evidence."], label, "Fixes")))
        return None                 # Merge pull request, Approve and the patch download stay on their page

    def _try_step(self, facts: "_Facts", fix: dict, box: dict, button: dict, where: dict, opened: bool) -> dict | None:
        """Try on a test copy, from a server change's box. Approve, Apply, Roll back and the download stay on their page."""
        label = button["label"]
        can = bool(button.get("enabled")) and not facts.closed
        if button["action"] != "try" or (not can and not opened):
            return None
        reason = facts.closed_reason() or button.get("reason") or "This is not available yet. Its page says why."
        return _entry("next:try", f"next:try:{box['id']}", mark=words.MARK_NEXT, title=label, text=fix["title"], where=where, open_item=opened,
                      step=_step({"type": "try", "plan_id": facts.plan_id, "fix_id": fix["id"], "change": box["id"]}, can=can, reason=reason,
                                 confirm=words.step_confirm(
                                     "Try this change on a test copy?",
                                     ["Starts a test copy of the server with the change and measures the copy.",
                                      "It changes nothing on the real system: Apply stays on its page."], label, "Fixes")))

    def _approval_step(self, facts: "_Facts", fix: dict, box: dict, picker: dict, where: dict, opened: bool) -> dict | None:
        """Ask for approval, with the reviewers the page ticks by default (to pick others, the page is the place)."""
        label = picker.get("button") or "Ask for approval"
        can = bool(picker.get("enabled")) and not facts.closed
        if not can and not opened:
            return None
        reason = facts.closed_reason() or picker.get("reason") or "This is not available yet. Its page says why."
        ticked = [o for o in picker.get("options") or [] if o.get("checked")]
        if not ticked and can:
            can, reason = False, "Tick who should approve on Fixes first."
        names = words.join_names([o["name"] for o in ticked])
        return _entry("next:ask_approval", f"next:ask_approval:{box['id']}", mark=words.MARK_NEXT, title=label, text=fix["title"], where=where,
                      open_item=opened,
                      step=_step({"type": "ask_approval", "plan_id": facts.plan_id, "fix_id": fix["id"], "change": box["id"],
                                  "reviewers": [o["id"] for o in ticked]}, can=can, reason=reason,
                                 confirm=words.step_confirm(
                                     "Ask for approval?",
                                     [f"Asks {names} to approve this change.",
                                      "These are the reviewers ticked by default on Fixes. To pick others, open the fix on its page.",
                                      "It applies nothing: Approve and Apply stay on their page."], label, "Fixes")))

    def _next_dependencies(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        view = facts.dependencies()
        out: list[dict] = []
        where = {"label": "On Dependencies", "link": _link("migration/dependencies")}
        rows = [r for g in view.get("groups") or [] for r in g.get("rows") or []]
        measurable = [r for r in rows if (r.get("measure") or {}).get("enabled") and not r.get("measurement")]
        every = view.get("measure_all") or {}
        unmeasured = [r for r in rows if not r.get("measurement")]
        off = bool(every) and not every.get("enabled") and not view.get("busy") and bool(unmeasured) and bool(every.get("blocked_reason"))
        if every and (off or ((every.get("enabled") or view.get("busy")) and (len(measurable) >= 2 or view.get("busy")))):
            out.append(_entry("next:measure_all", "next:measure_all", mark=words.MARK_NEXT, title=every["label"],
                              text=("A measurement is running." if view.get("busy") else
                                    "Measures the libraries of the list that have a pinned public copy." if off else
                                    f"{len(measurable)} libraries of the list have a pinned public copy and no measurement yet."), where=where,
                              step=_step({"type": "measure_all", "plan_id": facts.plan_id}, can=bool(every.get("enabled")) and not facts.closed,
                                         reason=facts.closed_reason() or every.get("blocked_reason") or "A measurement is running.",
                                         running=bool(view.get("busy")),
                                         confirm=words.step_confirm(
                                             "Measure all?",
                                             ["Measures every library of the list that has a pinned public copy, each in its own locked-down container.",
                                              "It measures public copies, not your systems, and connects to nothing of yours."],
                                             every["label"], "Dependencies"))))
        seen: set[str] = set()
        for r in sorted(rows, key=lambda r: r["id"] != item):
            measure, opened = r.get("measure") or {}, r["id"] == item
            if r["id"] in seen or not measure or r.get("measurement") or (not measure.get("enabled") and not opened):
                continue
            seen.add(r["id"])
            if len(seen) > MAX_STEPS:
                break
            out.append(_entry("next:measure_library", f"next:measure:{r['id']}", mark=words.MARK_NEXT, title=measure["label"], text=r["label"],
                              where={"label": "On Dependencies", "link": _link("migration/dependencies", r["id"])}, open_item=opened,
                              step=_step({"type": "measure_library", "plan_id": facts.plan_id, "row": r["id"]},
                                         can=bool(measure.get("enabled")) and not facts.closed,
                                         reason=facts.closed_reason() or measure.get("blocked_reason") or "This can't be measured now.",
                                         running=bool(measure.get("busy")),
                                         confirm=words.step_confirm(
                                             "Measure this library?",
                                             [f"Measures {r['label']} on its pinned public copy, in a locked-down container.",
                                              "It measures a public copy, not your system, and connects to nothing of yours."],
                                             measure["label"], "Dependencies"))))
        return out

    def _next_migration(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        view = facts.migration()
        measure = view.get("measure") or {}
        if not measure:
            return []
        measured = measure.get("label") != "Measure status"
        if measured and not view.get("busy"):
            return []               # every system has a status: measuring again is not the next step
        return [_entry("next:measure_status", "next:measure_status", mark=words.MARK_NEXT, title=measure["label"],
                       text=measure.get("progress_text") or "Measure where each system stands on the move to post-quantum cryptography.",
                       where={"label": f"On {PAGE_LABELS[page]}", "link": _link(page)},
                       step=_step({"type": "measure_status", "plan_id": facts.plan_id}, can=bool(measure.get("enabled")) and not facts.closed,
                                  reason=facts.closed_reason() or measure.get("blocked_reason") or "A measurement is running.",
                                  running=bool(view.get("busy")), progress=measure.get("progress_text"),
                                  confirm=words.step_confirm(
                                      "Measure status?",
                                      ["Measures where each system of the file stands: one handshake to each server, and a look at each signing program.",
                                       "It changes nothing on any system."], measure["label"], PAGE_LABELS[page])))]

    # ------------------------------------------------------------------ what this means: a result's own sentence

    def _meanings(self, facts: "_Facts", page: str, item: str | None) -> list[dict]:
        if page in ("inventory/import", "inventory/verify"):
            found = (facts.imported() or {}).get("otto") or {}
            if not found.get("count"):
                return []
            return [_entry("meaning:found", "meaning:found", mark=words.MARK_MEANING, title=found["text"], text=found.get("note"),
                           links=[{"label": found.get("link_label") or "Open Advisories", "link": found["link"]}])]
        if page == "evidence":
            return self._result_meanings(facts, item)[:MAX_MEANINGS]
        if page == "fixes":
            out = []
            for fix in sorted(facts.fixes().get("fixes") or [], key=lambda f: f["id"] != item):
                paragraphs = (fix.get("what") or {}).get("paragraphs") or []
                why = _plain(paragraphs[0]) if paragraphs else None
                if fix.get("kind") != "text" or not why:
                    continue
                out.append(_entry("meaning:text_only", f"meaning:text_only:{fix['id']}", mark=words.MARK_MEANING, title=fix["title"],
                                  text=why, badge={"label": (fix.get("status") or {}).get("word") or "Text only", "tone": "neutral"},
                                  links=[{"label": "Open the fix", "link": _link("fixes", fix["id"])}], open_item=fix["id"] == item))
            return out[:MAX_MEANINGS]
        if page == "migration/dependencies":
            out = []
            rows = [r for g in facts.dependencies().get("groups") or [] for r in g.get("rows") or []]
            seen: set[str] = set()
            for r in sorted(rows, key=lambda r: r["id"] != item):
                blocks = r.get("blocks") or []
                if not blocks or r["id"] in seen:
                    continue
                seen.add(r["id"])
                said = [b.get("words") or f"Blocks {b.get('system')} · {b.get('track_words')}" for b in blocks]
                out.append(_entry("meaning:blocks", f"meaning:blocks:{r['id']}", mark=words.MARK_MEANING, title=r["label"],
                                  text=" ".join(dict.fromkeys(s if s.endswith(".") else s + "." for s in said)),
                                  links=[{"label": "Open the library", "link": _link("migration/dependencies", r["id"])}], open_item=r["id"] == item))
            return out[:MAX_MEANINGS]
        return []

    def _result_meanings(self, facts: "_Facts", item: str | None) -> list[dict]:
        """Evidence: each newest result that is not a pass, in the result's own sentence, with where its fix is."""
        out = []
        order = {"fail": 0, "warn": 1}
        rows = [(row, row.get("after") or row.get("result")) for row in facts.lab().get("rows") or []]
        rows = [(row, result) for row, result in rows if result and result.get("tone") != "pass"]
        rows.sort(key=lambda pair: (item != f"test-{pair[0]['item_id']}", order.get(pair[1].get("tone"), 2)))
        for row, result in rows:
            links = [{"label": "See the evidence", "link": _link("evidence", f"test-{row['item_id']}")}]
            more = None
            if result.get("fix_line"):
                more = "A fix is suggested: see Fixing."
                links.append({"label": "View in Fixes", "link": _link("fixes", result["fix_line"]["fix_id"])})
            out.append(_entry("meaning:result", f"meaning:result:{result['run_id']}", mark=words.MARK_MEANING, title=row["title"],
                              text=" ".join(x for x in (result.get("plain"), more) if x), at=result.get("finished_at"),
                              badge={"label": result["label"], "tone": result["tone"]}, links=links, open_item=item == f"test-{row['item_id']}"))
        return out

    # ------------------------------------------------------------------ the tabs, and each thread so far

    def _tabs(self, facts: "_Facts", proposals: list[dict], suggestions: dict[str, dict]) -> list[dict]:
        """The open tabs, at most three. A tab is there once its thread has a suggestion or a result to explain (and,
        from phase 6c, an answer). A next step alone opens no tab. Worked out from the records on every read."""
        so_far: dict[str, list[dict]] = {t: [] for t in THREADS}
        waiting = {t: 0 for t in THREADS}
        has_suggestion = {t: False for t in THREADS}
        for p in proposals:
            thread = KIND_THREAD[p["kind"]]
            has_suggestion[thread] = True
            if waits(p):
                waiting[thread] += 1
            if p.get("decisions"):
                so_far[thread].append(suggestions[p["id"]])
        results = self._results(facts)
        so_far["testing"] += results
        steps = self._fix_steps(facts)
        so_far["fixing"] += steps
        explain = {"testing": any(e["badge"]["tone"] != "pass" for e in results), "fixing": bool(steps), "planning": False}
        tabs = []
        for thread in THREADS:
            if not (has_suggestion[thread] or explain[thread]):
                continue
            entries = sorted(so_far[thread], key=lambda e: (e.get("at") is None, e.get("at") or "", e["id"]))
            seen = "|".join(sorted([f"{p['id']}#{len(p.get('decisions') or [])}" for p in proposals if KIND_THREAD[p["kind"]] == thread]
                                   + [e["id"] for e in entries if e["kind"] != "suggestion"]))
            tabs.append({"key": thread, "label": THREAD_LABELS[thread], "waiting": waiting[thread],
                         "mark": hashlib.sha256(seen.encode("utf-8")).hexdigest()[:16],
                         "so_far_title": words.SO_FAR, "so_far": entries, "so_far_empty": None if entries else words.SO_FAR_EMPTY})
        return tabs

    def _results(self, facts: "_Facts") -> list[dict]:
        """Testing, so far: every reviewed result the Evidence page shows (the first and, where there is one, the
        retest's), in the reviewer's own word, each opening its evidence."""
        out = []
        for row in facts.lab().get("rows") or []:
            for side in ("result", "after"):
                result = row.get(side)
                if not result:
                    continue
                on = f" on {result['component']}" if result.get("component") else ""
                out.append(_entry("result", f"result:{result['run_id']}", mark=words.MARK_RESULT, title=f"{row['title']}{on}",
                                  text=result.get("short") or result.get("summary"), at=result.get("finished_at"),
                                  badge={"label": result["label"], "tone": result["tone"]},
                                  links=[{"label": "See the evidence", "link": _link("evidence", f"test-{row['item_id']}")}]))
        return out

    def _fix_steps(self, facts: "_Facts") -> list[dict]:
        """Fixing, so far: where each fix stands, in its page's own status word."""
        out = []
        for fix in facts.fixes().get("fixes") or []:
            status = fix.get("status") or {}
            out.append(_entry("fix_step", f"fix:{fix['id']}:{status.get('key')}", mark=words.MARK_FIX, title=fix["title"],
                              text=fix.get("list_source"), badge={"label": status.get("word") or "", "tone": "neutral"},
                              links=[{"label": "Open the fix", "link": _link("fixes", fix["id"])}]))
        return out


def _plain(value: object) -> str | None:
    """A sentence as plain text, whether the page sent it as text or as rich parts."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return "".join(str(part.get("v", "")) if isinstance(part, dict) else str(part) for part in value).strip() or None
    return None


class _Facts:
    """The views the pages draw from, each read at most once for one read of the panel, and only when it is needed."""

    def __init__(self, lab: Any, core: dict, closed: bool) -> None:
        self._lab, self._core, self.closed = lab, core, closed
        self.plan_id, self.import_id = core["plan_id"], core["import_id"]
        self._seen: dict[str, Any] = {}
        self.waiting: dict[str, int] = {}

    def _once(self, name: str, read: Any) -> Any:
        if name not in self._seen:
            self._seen[name] = read()
        return self._seen[name]

    def closed_reason(self) -> str | None:
        return CLOSED if self.closed else None

    def plan(self) -> dict:
        return self._once("plan", lambda: self._lab.plan_view(self.plan_id))

    def lab(self) -> dict:
        return self._once("lab", lambda: self._lab.lab_view(self.plan_id) if self.plan().get("has_results") else {})

    def fixes(self) -> dict:
        plan = self.plan()
        return self._once("fixes", lambda: self._lab.fixes_view(self.plan_id) if plan.get("has_results") or plan.get("has_migration") else {})

    def migration(self) -> dict:
        # (not the Migration page's own read: that one writes each system's measurement down the first time it is asked)
        return self._once("migration", lambda: self._lab.migration_measure_view(self.plan_id))

    def dependencies(self) -> dict:
        return self._once("dependencies", lambda: self._lab.dependencies_view(self.plan_id))

    def imported(self) -> dict:
        return self._once("imported", lambda: self._lab.import_json_for(self.import_id))

    def verified(self) -> bool:
        def read() -> bool:
            try:
                self._lab.latest_verify(self.import_id)
            except NotFound:
                return False
            return True
        return bool(self._once("verified", read))

    def waiting_for_ticks(self) -> bool:
        return any(not a.get("confirmed") and not a.get("error") for a in self.imported().get("addresses") or [])

    def overview_step(self) -> dict | None:
        """The Overview's own next step: the Overview's rule and sentence, from the views read here."""
        def read() -> dict:
            plan = self.plan()
            fixes = self.fixes().get("fixes") if plan.get("has_results") or plan.get("has_migration") else None
            return self._lab.next_step_from(self._core, plan, self.verified(), fixes, self.waiting)
        return self._once("overview", read)

    def busy(self) -> bool:
        """Something is running for this assessment (of the views read so far): the panel then asks again in a second."""
        plan = self._seen.get("plan") or {}
        return bool(plan.get("running") or (self._seen.get("lab") or {}).get("busy") or (self._seen.get("fixes") or {}).get("busy")
                    or (self._seen.get("migration") or {}).get("busy") or (self._seen.get("dependencies") or {}).get("busy"))
