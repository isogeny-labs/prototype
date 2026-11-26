"""Who did what (design refactor, decision I, 26 November 2026): the one place that writes the `actions` table.

Every button that decides or changes something in an assessment ends in one method of the `Lab`. `recorded`, put on the
`Lab` class, wraps exactly the methods listed in `PRESSES` below, and nothing else is recorded here. A wrapped method
is a *press*:

- **when and who are taken at the press.** The time and the name are read before the method runs, in the request that
  pressed the button (`Lab.actor()`). The row is written when the method has returned: a press that was refused
  leaves no row. A run it started finishes later, in a job thread, and never looks the name up again.
- **the name comes from one source** (`Lab.actor()`): the account that is logged in, where the app has one (the hosted
  app logs in with GitHub); otherwise the name typed once in Settings (Who decides); otherwise "You". The app does not
  check who is at the keyboard beyond its login, and the reads say so.
- **a press knows what it made.** While a press is on, the ids of the records it adds in its own request are noted (a
  retest, a proof, an approval, a merge, a try, an Apply ...), and for the two things that are overwritten in place
  (the "I own this system" tick and the order of the test plan) what they were before. So the row can name them.
- **a run is tied to its press without touching the run.** A job queued during a press carries that press; when the
  job stores a run, one `action_runs` row is added beside it. `test_runs`, `reviews`, their fingerprints and the runner
  are not changed, and nothing reads this table to decide or to word a result.
- **a press inside a press is part of it.** "Retest now" calls the retest, "Rerun as new assessment" brings the file in:
  one button, one row.

Nothing is ever filled in afterwards. What happened before this table existed has no row, and the reads then say
"Not recorded (before names were kept)". Records that already keep a name are left as they are and get no row here:
Otto's decisions, advisory looks, research runs and Watch list marks (`by` on their own rows), and the name typed at
sign-off.

The web middleware `WhoIsAsking` (app/web/who.py) makes the session of the request known here; a call that comes from
no request (a script, the accuracy check, the Watch list's clock) has no account, and reads the typed name or "You".
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, select
from sqlalchemy import inspect as sa_inspect

from app import auth
from app.db import (
    ActionRow,
    ActionRunRow,
    AssessmentRow,
    DependencyListRow,
    PlanRow,
    TestRunRow,
    WatchRunRow,
    iso,
    now_utc,
)

ACCOUNT, TYPED, DEFAULT = "account", "typed", "default"
SOURCES = (ACCOUNT, TYPED, DEFAULT)
YOU = "You"

# The session token of the request that is being answered (None outside a request). Only ever read to look the logged-in
# account up; it is never stored, shown or logged.
_asking: ContextVar[str | None] = ContextVar("evidence_lab_asking", default=None)
# The press that is on in this request (None in a job thread: a job runs in a thread of its own, with no press).
_press: ContextVar["Press | None"] = ContextVar("evidence_lab_press", default=None)

# The tables whose new rows a press names in its detail.
NOTED = frozenset(
    {
        "imports",
        "verify_runs",
        "plan_items",
        "retests",
        "review_marks",
        "research_requests",
        "code_connections",
        "changes",
        "proofs",
        "pull_requests",
        "approvals",
        "merges",
        "change_tries",
        "apply_requests",
        "apply_approvals",
        "applies",
        "rollbacks",
        "migration_choices",
        "system_settings",
        "dependency_lists",
        "dependency_ties",
        "watch_runs",
        "evidence_exports",
        "assessment_details",
        "assessment_signoffs",
    }
)
# The two things a press overwrites in place: what they were is kept with the press, because nothing else keeps it.
WATCHED = {"plan_items": ("position", "removed"), "addresses": ("confirmed",)}


@contextmanager
def asking(token: str | None) -> Iterator[None]:
    """Within this block, a press is made by the session this token belongs to."""
    mark = _asking.set(token or None)
    try:
        yield
    finally:
        _asking.reset(mark)


class Press:
    """One press of a button, from the moment it was pressed until its row is written."""

    def __init__(self, at: str, who: dict) -> None:
        self.at, self.who = at, who
        self.made: dict[str, list] = {}  # table -> the ids of the rows this press added, in order
        self.changed: dict[str, list[dict]] = {}  # table -> [{"id", <column>: [before, after]}]
        self.queued: list[tuple] = []  # the jobs it queued: (plan item id, phase)
        self._lock = threading.Lock()
        self._closed = False
        self._action_id: int | None = None
        self._early: list[int] = []

    def ran(self, run_id: int) -> int | None:
        """A job of this press stored a run. The action's id when its row is written already; None when the run came
        first (it is kept and tied when the row is written) or when the press left no row."""
        with self._lock:
            if not self._closed:
                self._early.append(run_id)
                return None
            return self._action_id

    def close(self, action_id: int | None) -> list[int]:
        """The press is over: its row has this id (None: it left no row). Returns the runs that finished before."""
        with self._lock:
            self._closed, self._action_id = True, action_id
            early, self._early = self._early, []
        return early if action_id is not None else []


def _note_flush(session, _context) -> None:
    """While a press is on: note the rows it adds, and what the two overwritten things were before."""
    press = _press.get()
    if press is None:
        return
    for obj in session.new:
        table = getattr(obj, "__tablename__", None)
        if table in NOTED:
            key = sa_inspect(obj).mapper.primary_key_from_instance(obj)
            if key and key[0] is not None:
                press.made.setdefault(table, []).append(key[0])
    for obj in session.dirty:
        table = getattr(obj, "__tablename__", None)
        columns = WATCHED.get(str(table))
        if not columns:
            continue
        state, was = sa_inspect(obj), {}
        for name in columns:
            history = state.attrs[name].history
            if history.has_changes() and history.deleted:
                was[name] = [history.deleted[0], history.added[0] if history.added else getattr(obj, name)]
        if was:
            press.changed.setdefault(str(table), []).append({"id": obj.id, **was})


# ---------------------------------------------------------------- what each press writes down


class Told:
    """What a press's row is made from: the method's arguments by name, what it returned, and what the press noted."""

    def __init__(self, lab: Any, db: Any, press: Press, args: dict, result: Any) -> None:
        self.lab, self.db, self.press, self.args, self.result = lab, db, press, args, result

    def first(self, table: str):
        made = self.press.made.get(table) or []
        return made[0] if made else None

    def items(self) -> list[int]:
        """The tests of the plan this press queued, once each, in the order they were queued."""
        return list(dict.fromkeys(key[0] for key in self.press.queued))


@dataclass(frozen=True)
class What:
    """One recorded button. `kind`: its name in the record (or a function of what was told, None for "no row").
    `where`: the assessment it belongs to, as one of plan_id, import_id, assessment_id or run_id. `item`: what it was
    on. `detail`: its few facts. `needs`: tables of which the press must have written a row (a press that changed
    nothing, like Mark reviewed on a result that is marked already, leaves no row). `runs`: it leaves a row only if it
    queued a run."""

    kind: str | Callable[[Told], str | None]
    where: Callable[[Told], dict]
    item: Callable[[Told], str | None] | None = None
    detail: Callable[[Told], dict] | None = None
    needs: tuple[str, ...] = ()
    runs: bool = False


def _plan(t: Told) -> dict:
    return {"plan_id": t.args["plan_id"]}


def _import(t: Told) -> dict:
    return {"import_id": t.args["import_id"]}


def _run(t: Told) -> dict:
    return {"run_id": t.args["run_id"]}


def _fix(t: Told) -> str:
    return f"fix:{t.args['fix_id']}"


def _change(t: Told) -> str:
    return f"change:{t.args['key']}"


def _queued(t: Told) -> dict:
    return {"items": t.items()}


def _assessment_kind(t: Told) -> str | None:
    changes = t.args.get("changes") or {}
    if changes.get("close"):
        return "closed"
    return "assessment_changed" if _assessment_changes(changes) else None


def _assessment_changes(changes: dict) -> dict:
    """The fields of an assessment a person changed, as they asked for them (the sign-off keeps its own name and note)."""
    return {k: changes[k] for k in ("name", "project_id", "archived", "purpose", "reference") if k in changes}


def _before_now(t: Told, phase: str) -> bool:
    """Was a run of this phase started for this plan before this press? (Then the button read "... again".)"""
    return (
        t.db.scalar(
            select(TestRunRow.id)
            .where(TestRunRow.plan_id == t.args["plan_id"], TestRunRow.phase == phase, TestRunRow.started_at < t.press.at)
            .limit(1)
        )
        is not None
    )


def _connected(t: Told) -> str | None:
    """The fix whose code a Connect demo code connected: the code fix of the plan, once its change is on record."""
    return next((f"fix:{f['id']}" for f in t.result or [] if f.get("kind") == "code" and f.get("change")), None)


def _list_added(t: Told) -> dict:
    row = t.db.get(DependencyListRow, t.first("dependency_lists"))
    return {"list_id": row.id, "filename": row.filename, "format": row.format, "sha256": row.sha256}


def _plan_change(t: Told) -> dict:
    """What a press did to the test plan: the tests it added, the ones it put back or took out, and what moved."""
    changed = t.press.changed.get("plan_items") or []
    return {
        "added": list(t.press.made.get("plan_items") or []),
        "back": [c["id"] for c in changed if c.get("removed") == [True, False]],
        "removed": [c["id"] for c in changed if c.get("removed") == [False, True]],
        "moved": [{"item": c["id"], "from": c["position"][0], "to": c["position"][1]} for c in changed if "position" in c],
    }


def _demo_change(t: Told) -> dict | None:
    """The developer's change a Bring in a demo change wrote, as the Change watch view names it."""
    from app.changewatch import demo_changes

    found = demo_changes.find(t.args["key"])
    branch = found.branch if found is not None else None
    return next((c for c in (t.result or {}).get("changes") or [] if c.get("branch") == branch), None)


def _watch_again(t: Told) -> bool:
    """Is this watch run a second run of the same code of the same change? (Then the button read "Run again".)"""
    watch = t.db.get(WatchRunRow, t.first("watch_runs"))
    return (
        t.db.scalar(
            select(WatchRunRow.id)
            .where(
                WatchRunRow.plan_id == watch.plan_id, WatchRunRow.head_commit == watch.head_commit, WatchRunRow.id < watch.id
            )
            .limit(1)
        )
        is not None
    )


def _reviewer(t: Told) -> dict:
    from app.fixes.changes import REVIEWERS

    return {"reviewer": t.args["reviewer"], "as": REVIEWERS.get(t.args["reviewer"], t.args["reviewer"])}


# Every method of the `Lab` whose press is recorded, by the method's name. (A method that is not here leaves no row.)
PRESSES: dict[str, What] = {
    # ---- the assessment itself, and the files brought in
    "create_project": What(
        "assessment_started", lambda t: {"assessment_id": t.result["assessment_id"]}, detail=lambda t: {"first": True}
    ),
    "new_assessment": What("assessment_started", lambda t: {"assessment_id": t.result["id"]}),
    "rerun_assessment": What(
        "assessment_rerun",
        lambda t: {"assessment_id": t.result["id"]},
        detail=lambda t: {"rerun_of": t.args["assessment_id"], "import_id": t.first("imports")},
    ),
    "update_assessment": What(
        _assessment_kind,
        lambda t: {"assessment_id": t.args["assessment_id"]},
        detail=lambda t: {
            **({"changed": _assessment_changes(t.args["changes"])} if _assessment_changes(t.args["changes"]) else {}),
            **({"signoff_id": t.first("assessment_signoffs")} if t.args["changes"].get("close") else {}),
        },
    ),
    "import_demo": What(
        "file_imported",
        lambda t: {"import_id": t.result["id"]},
        detail=lambda t: {"filename": t.result["filename"], "claims": len(t.result["claims"]), "demo_file": True},
    ),
    "import_file": What(
        "file_imported",
        lambda t: {"import_id": t.result["id"]},
        detail=lambda t: {"filename": t.result["filename"], "claims": len(t.result["claims"]), "demo_file": False},
    ),
    "add_dependency_list": What("dependency_list_added", _plan, detail=_list_added, needs=("dependency_lists",)),
    "export_evidence": What(
        "evidence_downloaded",
        _plan,
        detail=lambda t: {"export_id": t.result["id"], "fingerprint": t.result["fingerprint"]},
        needs=("evidence_exports",),
    ),
    # ---- "I own this system", and Verify
    "confirm_address": What(
        lambda t: "address_confirmed" if t.args["confirmed"] else "address_unconfirmed",
        _import,
        item=lambda t: f"system:server:{t.result['address']}",
        detail=lambda t: {
            "address": t.result["address"],
            "confirmed": bool(t.result["confirmed"]),
            "resolved_ip": t.result["resolved_ip"],
            "was": next((c["confirmed"][0] for c in t.press.changed.get("addresses") or [] if "confirmed" in c), None),
        },
    ),
    "verify": What("verify", _import, detail=lambda t: {"verify_run_id": t.result["id"]}, needs=("verify_runs",)),
    # ---- the test plan and its runs
    "run_test": What("run", _plan, item=lambda t: f"test:{t.args['item_id']}", detail=_queued, runs=True),
    "run_all": What("run_all", _plan, detail=_queued, runs=True),
    "add_test": What(
        "test_added", _plan, detail=lambda t: {"catalog_id": t.args["catalog_id"], **_plan_change(t)}, needs=("plan_items",)
    ),
    "remove_test": What(
        "test_removed", _plan, item=lambda t: f"test:{t.args['item_id']}", detail=_plan_change, needs=("plan_items",)
    ),
    "reorder": What(
        "tests_reordered", _plan, detail=lambda t: {"order": list(t.args["order"]), **_plan_change(t)}, needs=("plan_items",)
    ),
    "start_retest": What(
        "retest",
        _plan,
        detail=lambda t: {
            "retest_id": t.first("retests"),
            "version": t.args["version"],
            "component": t.args.get("component"),
            **_queued(t),
        },
        needs=("retests",),
    ),
    "retest_now": What(
        "retest_now", _plan, item=_fix, detail=lambda t: {"retest_id": t.first("retests"), **_queued(t)}, needs=("retests",)
    ),
    "measure_migration": What(
        "measure_status", _plan, detail=lambda t: {"again": _before_now(t, "migration"), **_queued(t)}, runs=True
    ),
    "measure_dependencies": What(
        "measure_dependencies", _plan, detail=lambda t: {"row": t.args.get("row_id"), **_queued(t)}, runs=True
    ),
    "mark_reviewed": What("marked_reviewed", _run, item=lambda t: f"run:{t.args['run_id']}", needs=("review_marks",)),
    "dig_deeper": What(
        "dig_deeper",
        _run,
        item=lambda t: f"run:{t.args['run_id']}",
        detail=lambda t: {"request_id": t.first("research_requests")},
        needs=("research_requests",),
    ),
    # ---- Fixes: a code change, from Connect demo code to the merge
    "connect_code": What(
        "code_connected",
        _plan,
        item=_connected,
        detail=lambda t: {
            "connection_id": t.first("code_connections"),
            "change_id": t.first("changes"),
            "proof_id": t.first("proofs"),
        },
        needs=("code_connections",),
    ),
    "run_proof_again": What(
        "proof_started", _plan, item=_fix, detail=lambda t: {"proof_id": t.first("proofs")}, needs=("proofs",)
    ),
    "open_pull_request": What(
        "pull_request_opened",
        _plan,
        item=_fix,
        detail=lambda t: {"pull_request_id": t.first("pull_requests"), "reviewers": list(t.args["reviewers"])},
        needs=("pull_requests",),
    ),
    "approve": What(
        "approved",
        _plan,
        item=_fix,
        detail=lambda t: {"approval_id": t.first("approvals"), **_reviewer(t)},
        needs=("approvals",),
    ),
    "merge": What("merged", _plan, item=_fix, detail=lambda t: {"merge_id": t.first("merges")}, needs=("merges",)),
    # ---- a change to a system: try, approvals, Apply, Roll back
    "try_change": What(
        "change_tried", _plan, item=_change, detail=lambda t: {"try_id": t.first("change_tries")}, needs=("change_tries",)
    ),
    "ask_approval": What(
        "approval_asked",
        _plan,
        item=_change,
        detail=lambda t: {"request_id": t.first("apply_requests"), "reviewers": list(t.args["reviewers"])},
        needs=("apply_requests",),
    ),
    "approve_change": What(
        "change_approved",
        _plan,
        item=_change,
        detail=lambda t: {"approval_id": t.first("apply_approvals"), **_reviewer(t)},
        needs=("apply_approvals",),
    ),
    "apply_change": What(
        "applied", _plan, item=_change, detail=lambda t: {"apply_id": t.first("applies"), **_queued(t)}, needs=("applies",)
    ),
    "rollback_change": What(
        "rolled_back",
        _plan,
        item=_change,
        detail=lambda t: {"rollback_id": t.first("rollbacks"), **_queued(t)},
        needs=("rollbacks",),
    ),
    # ---- the migration plan and the dependency list
    "choose_migration_option": What(
        "option_chosen",
        _plan,
        item=lambda t: f"system:{t.args['system_key']}",
        detail=lambda t: {"choice_id": t.first("migration_choices"), "option": t.args["option"]},
        needs=("migration_choices",),
    ),
    "set_migration_setting": What(
        "setting_changed",
        _plan,
        item=lambda t: f"system:{t.args['system_key']}",
        detail=lambda t: {"setting_id": t.first("system_settings"), "field": t.args["field"], "value": t.args["value"]},
        needs=("system_settings",),
    ),
    "tie_dependency": What(
        "library_tied",
        _plan,
        detail=lambda t: {
            "tie_id": t.first("dependency_ties"),
            "top": t.args["top_key"],
            "system": t.args.get("system_key") or "",
        },
        needs=("dependency_ties",),
    ),
    # ---- Change watch
    "bring_in_demo_change": What(
        "demo_change_brought_in",
        _plan,
        item=lambda t: f"developer-change:{_demo_change(t)['id']}" if _demo_change(t) else None,
        detail=lambda t: {
            "name": t.args["key"],
            "branch": (_demo_change(t) or {}).get("branch"),
            "commit": (_demo_change(t) or {}).get("head"),
        },
    ),
    "run_picked_tests": What(
        "picked_tests_run",
        _plan,
        item=lambda t: f"developer-change:{t.args['change']}",
        detail=lambda t: {"watch_run_id": t.first("watch_runs"), "again": _watch_again(t), **_queued(t)},
        needs=("watch_runs",),
    ),
}
KINDS = (
    "assessment_started",
    "assessment_rerun",
    "assessment_changed",
    "closed",
    "file_imported",
    "dependency_list_added",
    "evidence_downloaded",
    "address_confirmed",
    "address_unconfirmed",
    "verify",
    "run",
    "run_all",
    "test_added",
    "test_removed",
    "tests_reordered",
    "retest",
    "retest_now",
    "measure_status",
    "measure_dependencies",
    "marked_reviewed",
    "dig_deeper",
    "code_connected",
    "proof_started",
    "pull_request_opened",
    "approved",
    "merged",
    "change_tried",
    "approval_asked",
    "change_approved",
    "applied",
    "rolled_back",
    "option_chosen",
    "setting_changed",
    "library_tied",
    "demo_change_brought_in",
    "picked_tests_run",
)


def place(db, plan_id=None, import_id=None, assessment_id=None, run_id=None) -> tuple[int | None, int | None, int | None]:
    """(assessment, import, plan) of a press, from whichever of them it names. A file brought in before its test plan
    was made has no plan yet, and an assessment that was just started has no file."""
    if run_id is not None:
        run = db.get(TestRunRow, run_id)
        plan_id = run.plan_id if run is not None else None
    if plan_id is not None:
        plan = db.get(PlanRow, plan_id)
        import_id = plan.import_id if plan is not None else import_id
    if import_id is None and assessment_id is not None:
        assessment = db.get(AssessmentRow, assessment_id)
        import_id = assessment.import_id if assessment is not None else None
    if import_id is not None:
        if plan_id is None:
            plan_id = db.scalar(select(PlanRow.id).where(PlanRow.import_id == import_id))
        if assessment_id is None:
            assessment_id = db.scalar(select(AssessmentRow.id).where(AssessmentRow.import_id == import_id))
    return assessment_id, import_id, plan_id


def _pressed(fn: Callable, what: What) -> Callable:
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def press_of(self, *args, **kwargs):
        if _press.get() is not None:
            return fn(self, *args, **kwargs)  # a press inside a press is part of it: one button, one row
        press = Press(iso(now_utc()), self.actor())
        mark = _press.set(press)
        try:
            result = fn(self, *args, **kwargs)
        except BaseException:
            press.close(None)  # refused, or it failed: no row, and its runs (there are none) are tied to nothing
            raise
        finally:
            _press.reset(mark)
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        told = dict(bound.arguments)
        told.pop("self", None)
        self._write_press(press, what, told, result)
        return result

    press_of.records = what  # type: ignore[attr-defined]
    return press_of


def _tying(fn: Callable) -> Callable:
    """Around the one function that stores a run: a run stored by a job of a press is tied to that press, beside the
    run. The function itself, the run and its review are as they were."""

    @functools.wraps(fn)
    def run_one(self, job, a):
        before = job.run_id
        out = fn(self, job, a)
        press = getattr(job, "press", None)
        if press is not None and job.run_id is not None and job.run_id != before:
            try:
                action_id = press.ran(job.run_id)
                if action_id is not None:
                    self._tie_runs(action_id, [job.run_id])
            except Exception as exc:  # the run and its review are stored: a problem here never loses them
                job.log(f"this run could not be tied to the press that started it ({exc.__class__.__name__})")
        return out

    return run_one


def recorded(cls):
    """Put on the `Lab` class: every method in `PRESSES` records its press. A name that is not a method of the class
    fails here, at import, so a renamed button can't silently stop being recorded."""
    for name, what in PRESSES.items():
        setattr(cls, name, _pressed(getattr(cls, name), what))
    cls._run_one = _tying(cls._run_one)
    return cls


class ActionsMixin:
    """Mixed into `Lab`: the one name source, and the writing of a press."""

    db: Callable[..., Any]
    jobs: Any
    settings: Any
    _typed_name: Callable[[], str | None]  # from OttoMixin: the name typed once in Settings (Who decides)

    def _init_actions(self) -> None:
        """A job queued while a press is on carries that press, and the rows a press adds are noted."""
        submit = self.jobs.submit

        def submit_for_press(key: tuple, fn: Callable, group: object = None):
            press = _press.get()
            if press is None:
                return submit(key, fn, group=group)

            def work(job):
                job.press = press  # set in the job's own thread, before its work starts
                return fn(job)

            job = submit(key, work, group=group)
            press.queued.append(tuple(key))
            return job

        self.jobs.submit = submit_for_press
        event.listen(self.db, "after_flush", _note_flush)

    def actor(self) -> dict:
        """Who is pressing, from the one source: {"name", "source", "account"}. The logged-in account where the app has
        one, else the name typed once in Settings (Who decides), else "You". Asked at the moment of a press."""
        token = _asking.get()
        if token:
            with self.db() as db:
                user = auth.session_user(db, token, self.settings.login_methods)
                if user is not None:
                    return {"name": user.login, "source": ACCOUNT, "account": f"github:{user.github_id}"}
        typed = self._typed_name()
        if typed:
            return {"name": typed, "source": TYPED, "account": None}
        return {"name": YOU, "source": DEFAULT, "account": None}

    def _write_press(self, press: Press, what: What, args: dict, result: Any) -> None:
        action_id = None
        try:
            if what.needs and not any(press.made.get(t) or press.changed.get(t) for t in what.needs):
                return  # it changed nothing (the result was marked already, the order is the same): no row
            if what.runs and not press.queued:
                return
            with self.db() as db:
                told = Told(self, db, press, args, result)
                kind = what.kind(told) if callable(what.kind) else what.kind
                if kind is None:
                    return
                assessment_id, import_id, plan_id = place(db, **what.where(told))
                row = ActionRow(
                    assessment_id=assessment_id,
                    import_id=import_id,
                    plan_id=plan_id,
                    at=press.at,
                    by=str(press.who["name"])[:100],
                    by_source=press.who["source"],
                    by_account=press.who.get("account"),
                    kind=kind,
                    item=(what.item(told) if what.item is not None else None),
                    detail=(what.detail(told) if what.detail is not None else {}),
                )
                db.add(row)
                db.commit()
                action_id = row.id
        finally:
            early = press.close(action_id)
        if action_id is not None and early:
            self._tie_runs(action_id, early)

    def _tie_runs(self, action_id: int, run_ids: list[int]) -> None:
        with self.db() as db:
            for run_id in run_ids:
                db.add(ActionRunRow(action_id=action_id, run_id=run_id))
            db.commit()


__all__ = ["ACCOUNT", "DEFAULT", "KINDS", "PRESSES", "SOURCES", "TYPED", "YOU", "ActionsMixin", "asking", "place", "recorded"]
