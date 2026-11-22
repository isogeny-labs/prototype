"""The Watch list's clock (sandbox research, a prototype; Kevin's plan of 22 November 2026, part 5).

While Sandbox research is on, the app looks for published advisories by itself: about once a day for every open
assessment whose files name a library the source keeps by name, and once shortly after the app starts where the last
look is older than a day. It is the same look a click makes ("Look for new advisories", "Look now"), recorded under the
clock's own name, never a person's. Looking is free: no Claude, no container, nothing proposed.

Rules kept here:
  - The clock exists only on a computer marked as the sandbox, and does something only while the switch is on.
  - One round at a time. In a round a library two assessments name is asked about once.
  - A look that got no answer is not a look: nothing is recorded as found, the page says "Couldn't look", and the next
    try waits longer each time (one hour, two, four ... at most a day).
  - A closed or archived assessment is never looked at.
  - By itself the clock only looks. A research run is started only where the second tick allows it (`start_research_
    by_itself`, behind `sandbox_by_itself()`), within the limit for a day; it accepts nothing and runs no check.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.db import AssessmentRow, OttoLookupRow, PlanRow
from app.errors import Conflict
from app.present import watchlist as words

INTERVAL = timedelta(hours=24)                       # a look by itself is due this long after the last look
RETRY_WAITS = (timedelta(hours=1), timedelta(hours=2), timedelta(hours=4), timedelta(hours=8), timedelta(hours=24))
START_DELAY_SECONDS = 30.0                           # after the app starts, before the first round
TICK_SECONDS = 60.0                                  # how often the clock asks itself whether anything is due


def _when(at: object) -> datetime:
    try:
        when = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class WatchClockMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    settings: Any
    sandbox_on: Callable[[], bool]
    sandbox_by_itself: Callable[[], bool]
    look_for_advisories: Callable[..., dict]
    _advisory_source: Callable[[], Any]
    _named_libraries: Callable[..., list[dict]]
    _askable: Callable[..., tuple]

    def _init_watch_clock(self) -> None:
        self._clock_round = threading.Lock()                       # one round at a time
        self._clock_failed: dict[int, dict] = {}                   # plan id -> {"count", "until", "reason"}: looks that got no answer
        self._clock_stop = threading.Event()
        self._clock_thread: threading.Thread | None = None

    # ---------------------------------------------------------------- the thread (only on a marked computer)

    def watch_clock_start(self) -> None:
        if not self.settings.sandbox_research or not self.settings.watch_clock or self._clock_thread is not None:
            return
        self._clock_stop.clear()

        def run() -> None:
            wait = START_DELAY_SECONDS
            while not self._clock_stop.wait(wait):
                wait = TICK_SECONDS
                try:
                    self.watch_clock_tick()
                except Exception:      # noqa: BLE001  (the clock never takes the app down; the next minute it asks again)
                    pass

        self._clock_thread = threading.Thread(target=run, name="evidence-lab-watch-clock", daemon=True)
        self._clock_thread.start()

    def watch_clock_stop(self) -> None:
        self._clock_stop.set()
        thread, self._clock_thread = self._clock_thread, None
        if thread is not None:
            thread.join(5)

    # ---------------------------------------------------------------- one round

    def _clock_plans(self, db) -> list[int]:
        """The plan of every open assessment that is not archived, oldest first."""
        rows = db.execute(select(PlanRow.id).join(AssessmentRow, AssessmentRow.import_id == PlanRow.import_id)
                          .where(AssessmentRow.closed_at.is_(None), AssessmentRow.archived.is_(False)).order_by(PlanRow.id)).all()
        return [int(r[0]) for r in rows]

    def _clock_due(self, db, plan_id: int, now: datetime) -> bool:
        failed = self._clock_failed.get(plan_id)
        if failed is not None and now < failed["until"]:
            return False
        newest = db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id.desc()).limit(1)).first()
        return newest is None or now - _when(newest.at) >= INTERVAL

    def watch_clock_tick(self, now: datetime | None = None) -> dict:
        """One round, if anything is due: {"did": "off" | "busy" | "nothing" | "looked", "looked": [plan ids],
        "failed": {plan id: reason}, "started": the plan a research run was started for, or None}. `now` is for the
        tests; the clock's own thread passes none."""
        if not self.sandbox_on():
            return {"did": "off", "looked": [], "failed": {}, "started": None}
        if not self._clock_round.acquire(blocking=False):
            return {"did": "busy", "looked": [], "failed": {}, "started": None}
        try:
            now = now or datetime.now(timezone.utc)
            with self.db() as db:
                due = []
                for plan_id in self._clock_plans(db):
                    if not self._clock_due(db, plan_id, now):
                        continue
                    plan = db.get(PlanRow, plan_id)
                    if self._askable(self._named_libraries(db, plan))[0]:     # (nothing to ask about is nothing to look for)
                        due.append(plan_id)
            looked: list[int] = []
            failed: dict[int, str] = {}
            if due:
                source = self._advisory_source()
                asked: dict[str, list[bytes]] = {}
                answers = source.answers

                def once(package, answers=answers, asked=asked):
                    """In one round a library two assessments name is asked about once."""
                    if package.key not in asked:
                        asked[package.key] = answers(package)
                    return asked[package.key]

                source.answers = once
                for plan_id in due:
                    if self._clock_stop.is_set() or not self.sandbox_on():
                        break
                    try:
                        self.look_for_advisories(plan_id, by=words.CLOCK_NAME, source=source)
                    except Conflict as refused:
                        count = self._clock_failed.get(plan_id, {}).get("count", 0) + 1
                        wait = RETRY_WAITS[min(count, len(RETRY_WAITS)) - 1]
                        self._clock_failed[plan_id] = {"count": count, "until": now + wait, "reason": str(refused), "at": now}
                        failed[plan_id] = str(refused)
                    else:
                        self._clock_failed.pop(plan_id, None)
                        looked.append(plan_id)
            started = None
            if self.sandbox_by_itself() and hasattr(self, "start_research_by_itself"):
                started = self.start_research_by_itself(now)
            return {"did": "looked" if (looked or failed) else "nothing", "looked": looked, "failed": failed, "started": started}
        finally:
            self._clock_round.release()

    # ---------------------------------------------------------------- what the page says about it

    def watch_clock_next(self, plan_id: int) -> str | None:
        """One sentence under the Watch list's "Looked on ..." line: when the clock looks next, or that a look by itself
        got no answer and when it is tried again."""
        if not self.sandbox_on():
            return None
        if not self.settings.watch_clock:
            return words.CLOCK_NOT_RUNNING
        failed = self._clock_failed.get(plan_id)
        if failed is not None:
            return words.clock_failed_line(_stamp(failed["at"]), failed["reason"], _stamp(failed["until"]))
        with self.db() as db:
            newest = db.scalars(select(OttoLookupRow).where(OttoLookupRow.plan_id == plan_id).order_by(OttoLookupRow.id.desc()).limit(1)).first()
        if newest is None:
            return words.CLOCK_SOON
        return words.clock_next_line(_stamp(_when(newest.at) + INTERVAL))
