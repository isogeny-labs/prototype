"""Phase 6b: what a person typed to Otto and what it answered, kept with the assessment.

The answer itself is worked out by the assistant's engine, which only reads (`app/assistant/answers.py`). This file is
outside that package on purpose: it is the one place that writes for the assistant, and it writes only what was said.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import AssistantMessageRow, iso
from app.errors import NotFound

MAX_KEPT_SHOWN = 200


class SaidMixin:
    db: Any
    copilot: Any

    def assistant_answer(self, assessment_id: int, page: str, item: str | None, text: str) -> dict:
        """Otto's answer to one typed sentence. A read: nothing is decided, started or stored (a closed assessment's
        text box uses this, and so does the open one before its exchange is kept)."""
        return self.copilot.command(self, assessment_id, page, item, text)

    def assistant_say(self, plan_id: int, page: str, item: str | None, text: str) -> dict:
        """The same answer, and the exchange kept with the assessment (its words, the one line of the answer and where
        it led). Keeping it changes nothing else: a decision or a start still needs Confirm in the browser."""
        a = self.assessment_for(plan_id=plan_id)             # type: ignore[attr-defined]
        if a is None:
            raise NotFound("That assessment does not exist.")
        reply = self.copilot.command(self, a.id, page, item, text)
        with self.db() as db:
            db.add(AssistantMessageRow(plan_id=plan_id, at=iso(datetime.now(timezone.utc)), by=self.decision_name(),      # type: ignore[attr-defined]
                                       page=page, item=(item or None) and str(item)[:200], thread=reply.get("thread"),
                                       said=" ".join(str(text).split())[:500], kind=reply["kind"], reply=reply["text"], go=reply.get("go")))
            db.commit()
        return reply

    def assistant_messages(self, plan_id: int | None) -> list[dict]:
        """Everything said to Otto in this assessment, oldest first. A read."""
        if plan_id is None:
            return []
        with self.db() as db:
            rows = db.scalars(select(AssistantMessageRow).where(AssistantMessageRow.plan_id == plan_id).order_by(AssistantMessageRow.id)).all()
            return [{"id": r.id, "at": r.at, "by": r.by, "page": r.page, "thread": r.thread, "said": r.said, "kind": r.kind, "reply": r.reply,
                     "go": r.go} for r in rows[-MAX_KEPT_SHOWN:]]
