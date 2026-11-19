"""What the Change watch page draws (phase 6d): `change_watch_state` in the words of `app/present/changewatch.py`,
with the reviewer's own word for each run before and now. It only reads."""
from __future__ import annotations

from typing import Any, Callable

from app.db import PlanRow, TestRunRow
from app.engine import research
from app.lab.testlab import BUSY
from app.present import changewatch as words

BEFORE_FROM = {"first": "This assessment's own run of the test.", "retest": "From a retest of this assessment.",
               "proof": "From the proof of a fix.", "watch": "From an earlier run of a change's picked tests.",
               "watch_base": "From an earlier run of a change's picked tests."}
MADE_HERE = "No reviewed result on the code before was there, so the test also ran on that code in this run."


class ChangeWatchViewMixin:
    """Mixed into Lab. Needs: db and, from the other mixins: change_watch_state, _plan, _running, _result."""

    # Declared for the type check only (nothing is assigned): from Lab and its other mixins.
    db: Callable[..., Any]
    change_watch_state: Callable[[int], dict]
    _plan: Callable[..., PlanRow]
    _running: Callable[[int], str | None]
    _result: Callable[..., dict | None]

    def _watch_side(self, db, side: dict | None, link: dict | None) -> dict | None:
        """One side of before and now: the reviewer's word for that run, its plain sentence, and where its evidence is."""
        if side is None:
            return None
        run = db.get(TestRunRow, side["run_id"])
        result = self._result(db, run) if run is not None else None
        if result is None:
            return None
        on = f"{run.component_name} {run.component_version}" if run.component_name and run.component_version else None
        return {"run_id": run.id, "label": result["label"], "tone": result["tone"], "plain": result["plain"], "ran_on": on, "link": link}

    @staticmethod
    def _run_link(run: TestRunRow | None) -> dict | None:
        """Where a run's evidence is shown. The test's own first run is its row on Evidence. A run of one retest, one
        proof or one watch run is a row of that block on Checks, where exactly that run opens with its record (Evidence
        lists such a test once, by its newest run of the kind)."""
        if run is None:
            return None
        if run.phase == "first":
            return {"page": "evidence", "item": f"test-{run.plan_item_id}", "group": None}
        if run.phase == "retest" and run.retest_id is not None:
            return {"page": "checks", "item": f"retest-{run.plan_item_id}-on-{run.retest_id}", "group": None}
        if run.phase == "proof" and run.retest_id is not None:
            return {"page": "checks", "item": f"proof-{run.plan_item_id}-in-{run.retest_id}", "group": None}
        if run.phase in ("watch", "watch_base") and run.retest_id is not None:
            kind = "watch" if run.phase == "watch" else "watchbase"
            return {"page": "checks", "item": f"{kind}-{run.plan_item_id}-in-{run.retest_id}", "group": None}
        return None

    def _change_view(self, db, change: dict, program: dict, blocked: str | None) -> dict:
        titles = {t["item_id"]: t["title"] for t in change["picked"] + change["not_picked"]}
        run = change.get("run")
        results = []
        for row in (run or {}).get("tests") or []:
            before_run = db.get(TestRunRow, row["before"]["run_id"]) if row["before"] is not None else None
            results.append({
                # (a test that has left the plan since is still named by what it is)
                "item_id": row["item_id"], "title": titles.get(row["item_id"]) or research.title_of(row["kind"]),
                "before": self._watch_side(db, row["before"], self._run_link(before_run)),
                "before_note": (words_or_none(row, before_run)),
                "now": self._watch_side(db, row["now"], self._run_link(db.get(TestRunRow, row["now"]["run_id"]) if row["now"] is not None else None)),
                "job": row["job"], "differs": words.OUTCOME_WORDS.get(row["outcome"]) if row["outcome"] else None,
                "outcome": row["outcome"]})
        status = words.status_view(change, program)
        files = [words.file_view(f) for f in change["files"]]
        touched = ", ".join(f"{f['name']} ({f['what'].lower()})" for f in files) or None
        flags = [words.flag_view(f) for f in change["flags"]]
        picked_titles = [t["title"] for t in change["picked"]]
        starts = None
        if change["base"] is not None:
            on = f" ({program['name']} {change['starts_from']['version']})" if change.get("starts_from") else ""
            starts = f"Starts from commit {words.short_commit(change['base'])}{on}, {words._count(change['commits'], 'commit')} on the branch."
        gives = (f"Its code is, byte for byte, {program['name']} {change['gives']['version']}, one of our registered demo programs."
                 if change.get("gives") else (words.NOT_OURS if change["touches_program"] and not change.get("problem") else None))
        return {
            "id": change["id"], "title": change["title"], "branch": change["branch"], "commit": words.short_commit(change["head"]),
            "author": change["author"], "is_demo": change["is_demo"], "when": words.when_words(change["when"]),
            "files_line": touched, "picked_line": f"{len(change['picked'])} of {words._count(len(change['picked']) + len(change['not_picked']), 'test')} picked",
            "status": status, "flags_count": len(flags) + change["more_flags"],
            "panel": {
                "message": change["message"], "starts_from": starts, "gives": gives, "files": files,
                "picked": [{"item_id": t["item_id"], "title": t["title"], "reason": words.pick_reason(t, program),
                            "link": {"page": "checks", "item": f"test-{t['item_id']}", "group": None}} for t in change["picked"]],
                "not_picked": [{"item_id": t["item_id"], "title": t["title"], "reason": words.pick_reason(t, program),
                                "link": {"page": "checks", "item": f"test-{t['item_id']}", "group": None}} for t in change["not_picked"]],
                "picked_empty": words.nothing_picked(change, program) if not change["picked"] and not change.get("problem") else None,
                "run": words.run_view(change, program, picked_titles, blocked),
                "last_run": (words.when_words(run["started_at"]) if run is not None else None),
                "results": results,
                "flags": flags, "flags_note": words.FLAGS_NOTE if flags else None,
                "more_flags": (f"{words._count(change['more_flags'], 'more flag')} of the same kind are not listed." if change["more_flags"] else None),
            }}

    def change_watch_view(self, plan_id: int) -> dict:
        """The Change watch page: the Changes view. It reads the connected repository each time it is asked."""
        state = self.change_watch_state(plan_id)
        code, program = state["code"], state["code"]["program"]
        running = self._running(plan_id)
        blocked = BUSY[running] if running else None
        line = {"not_connected": words.NOT_CONNECTED, "no_code": words.NO_CODE, "unreadable": words.UNREADABLE}.get(code["state"])
        with self.db() as db:
            changes = [self._change_view(db, c, program, blocked) for c in state["changes"]] if program is not None else []
        return {
            "plan_id": plan_id, "title": words.TITLE, "subline": words.SUBLINE,
            "code": {"state": code["state"], "line": line,
                     "link": {"page": "fixes", "item": None, "group": None} if code["state"] == "not_connected" else None,
                     "connected_line": (f"Connected: the demo repository {code['repository']}, branch {code['branch']}." if code["state"] == "connected" else None)},
            "menu": {"button": words.MENU_BUTTON, "note": words.MENU_NOTE,
                     "items": [{"key": m["key"], "title": m["title"], "what_it_does": m["what_it_does"], "can": m["blocked"] is None,
                                "blocked_reason": words.MENU_BLOCKED.get(m["blocked"]) if m["blocked"] else None} for m in state["menu"]]},
            "changes": changes,
            "empty": words.EMPTY if code["state"] == "connected" and not changes else None,
            # (the page asks again while anything runs for this plan: until it has finished, Run is off with the reason)
            "busy": any(c["status"]["busy"] for c in changes) or (running is not None and bool(changes)),
        }


def words_or_none(row: dict, before_run: TestRunRow | None) -> str | None:
    """One line about where the "before" of a test comes from."""
    if row["before_made_here"]:
        return MADE_HERE
    return BEFORE_FROM.get(before_run.phase) if before_run is not None else None


__all__ = ["ChangeWatchViewMixin"]
