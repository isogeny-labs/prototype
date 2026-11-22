"""The Sandbox research switch (prototype, 22 November 2026). Mixed into Lab.

One switch, off by default. It can be turned on only where all three hold:
  - this computer is marked as Isogeny's own sandbox where the app starts (EVIDENCE_LAB_SANDBOX_RESEARCH);
  - isolated mode is ready (public copies of a library run only in locked containers);
  - Otto's harness is installed (a test is proven through it, registered in advance).
A switch that was turned on stops counting the moment one of the three no longer holds: `sandbox_on()` is what every
other module asks, never the stored value.

A second tick, "Design and prove tests by itself", counts only while the switch is on and Live Otto is ready. Two
spending limits belong to a research run started with the switch on: the most for one run, and the most for a day
(the last 24 hours, added up from the runs' own records). Turning the switch off ends a research run that is going.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.db import AppSettingRow, OttoResearchRow
from app.errors import BadRequest, Conflict
from app.otto import harness, model
from app.present import sandbox as present_sandbox

ON_KEY, BY_ITSELF_KEY = "sandbox_on", "sandbox_by_itself"
RUN_LIMIT_KEY, DAY_LIMIT_KEY = "sandbox_run_limit_nano", "sandbox_day_limit_nano"
DEFAULT_RUN_LIMIT_NANO = 5 * model.NANO          # Kevin's decision 4: 5 US dollars for one sandbox research run
DEFAULT_DAY_LIMIT_NANO = 10 * model.NANO         # ... and 10 for a day
MAX_LIMIT_NANO = 1000 * model.NANO
DAY = timedelta(hours=24)


class SandboxMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    settings: Any
    mode: Any
    otto_live_ready: Callable[[], bool]
    otto_view: Callable[..., dict]
    stop_research: Callable[..., Any]

    # ---------------------------------------------------------------- may it be on here?

    def sandbox_blocked(self) -> list[str]:
        """Every plain reason the switch can't be on here; empty when it can."""
        reasons = []
        if not self.settings.sandbox_research:
            reasons.append(present_sandbox.NOT_MARKED)
        if self.mode.name != "isolated":
            why = (self.mode.reason or "Isolated mode is not available").rstrip(".")
            reasons.append(f"{present_sandbox.NEEDS_ISOLATED}. {why[0].upper() + why[1:]}.")
        if not harness.public_status()["installed"]:
            reasons.append(present_sandbox.NEEDS_OTTO)
        return reasons

    def sandbox_on(self) -> bool:
        """Is Sandbox research on, and may it be? The one question every other module asks."""
        if not self.settings.sandbox_research:          # a quick no before the database is read
            return False
        with self.db() as db:
            stored = _get(db, ON_KEY) == "on"
        return stored and not self.sandbox_blocked()

    def sandbox_by_itself(self) -> bool:
        """May a research run be started with no click? Only with the switch on, the tick set and Live Otto ready."""
        if not self.sandbox_on():
            return False
        with self.db() as db:
            ticked = _get(db, BY_ITSELF_KEY) == "on"
        return ticked and self.otto_live_ready()

    # ---------------------------------------------------------------- the limits

    def sandbox_limits(self) -> tuple[int, int]:
        """(the most for one sandbox research run, the most for a day), in billionths of a US dollar."""
        with self.db() as db:
            return _limit(db, RUN_LIMIT_KEY, DEFAULT_RUN_LIMIT_NANO), _limit(db, DAY_LIMIT_KEY, DEFAULT_DAY_LIMIT_NANO)

    def sandbox_spent_today(self, now: datetime | None = None) -> int:
        """What the research runs of the last 24 hours spent on Claude, from their own end records. A run that is still
        going counts with its whole limit, so two runs can't pass the day's limit together."""
        since = (now or datetime.now(timezone.utc)) - DAY
        with self.db() as db:
            rows = db.scalars(select(OttoResearchRow).order_by(OttoResearchRow.id)).all()
        ended = {r.run_key: r for r in rows if r.kind == "finished"}
        total = 0
        for row in rows:
            if row.kind != "started" or not row.live or _when(row.at) < since:
                continue
            end = ended.get(row.run_key)
            total += int(end.spent_nano or 0) if end is not None else int(row.limit_nano or 0)
        return total

    def sandbox_run_limit(self, now: datetime | None = None) -> int:
        """What a research run that starts now may spend: the limit for one run, or what is left of the day's limit if
        that is less. Zero means the day's limit is reached."""
        run_limit, day_limit = self.sandbox_limits()
        return max(0, min(run_limit, day_limit - self.sandbox_spent_today(now)))

    # ---------------------------------------------------------------- Settings

    def sandbox_section(self) -> dict:
        blocked = self.sandbox_blocked()
        on = self.sandbox_on()
        with self.db() as db:
            ticked = _get(db, BY_ITSELF_KEY) == "on"
        live_ready = self.otto_live_ready()
        run_limit, day_limit = self.sandbox_limits()
        return present_sandbox.section(on=on, by_itself=bool(on and ticked and live_ready), blocked=blocked, live_ready=live_ready,
                                       run_limit_nano=run_limit, day_limit_nano=day_limit,
                                       spent_nano=self.sandbox_spent_today() if on else 0)

    def set_sandbox(self, on: bool | None = None, by_itself: bool | None = None, run_limit: str | None = None,
                    day_limit: str | None = None) -> dict:
        """Turn the switch or its tick, and/or save a spending limit (US dollars). Turning the switch on is refused
        with the plain reasons where it can't be on; turning it off ends a research run that is going."""
        if on:
            blocked = self.sandbox_blocked()
            if blocked:
                raise Conflict(" ".join(["Sandbox research can't be turned on here."] + blocked))
        if by_itself:
            will_be_on = on if on is not None else self.sandbox_on()
            if not will_be_on:
                raise Conflict(present_sandbox.BY_ITSELF_NEEDS_SWITCH)
            if not self.otto_live_ready():
                raise Conflict(present_sandbox.BY_ITSELF_NEEDS_LIVE)
        with self.db() as db:
            if run_limit is not None:
                _set(db, RUN_LIMIT_KEY, str(_dollars(run_limit)))
            if day_limit is not None:
                _set(db, DAY_LIMIT_KEY, str(_dollars(day_limit)))
            if on is not None:
                _set(db, ON_KEY, "on" if on else "off")
                if not on:
                    _set(db, BY_ITSELF_KEY, "off")           # the tick never outlives the switch
            if by_itself is not None:
                _set(db, BY_ITSELF_KEY, "on" if by_itself else "off")
            db.commit()
        if on is False:
            self.stop_research()                             # nothing of the sandbox goes on with the switch off
        return self.otto_view()


def _get(db, key: str) -> str | None:
    row = db.get(AppSettingRow, key)
    return row.value if row is not None else None


def _set(db, key: str, value: str) -> None:
    row = db.get(AppSettingRow, key)
    if row is None:
        db.add(AppSettingRow(key=key, value=value))
    else:
        row.value = value


def _limit(db, key: str, default: int) -> int:
    try:
        value = int(_get(db, key) or default)
    except ValueError:
        return default
    return value if 0 < value <= MAX_LIMIT_NANO else default


def _dollars(text: str) -> int:
    """A typed amount in US dollars, as billionths. Plain digits with at most two decimals, above zero, at most 1000."""
    raw = str(text).strip()
    whole, _, cents = raw.partition(".")
    if not whole.isdigit() or (cents and not cents.isdigit()) or len(whole) > 4 or len(cents) > 2:
        raise BadRequest("A spending limit is an amount in US dollars, like 5 or 2.50.", field="limit")
    nano = int(whole) * model.NANO + int((cents + "00")[:2]) * (model.NANO // 100)
    if not 0 < nano <= MAX_LIMIT_NANO:
        raise BadRequest("A spending limit is more than 0 and at most 1000 US dollars.", field="limit")
    return nano


def _when(at: str) -> datetime:
    try:
        when = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
