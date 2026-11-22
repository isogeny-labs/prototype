"""Phase 6b: what a person typed to Otto and what it answered, kept with the assessment.

The answer itself is worked out by the assistant's engine, which only reads (`app/assistant/answers.py`). This file is
outside that package on purpose: it is the one place that writes for the assistant, and it writes only what was said.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import AssistantMessageRow, iso
from app.errors import Conflict, NotFound
from app.present import times

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
        a = self.assessment_for(plan_id=plan_id)  # type: ignore[attr-defined]
        if a is None:
            raise NotFound("That assessment does not exist.")
        if a.closed_at is not None:  # (the route refuses this too; a closed assessment keeps nothing)
            raise Conflict("This assessment is closed. What you type is not kept.")
        reply = self.copilot.command(self, a.id, page, item, text)
        # What is stored keeps UTC words, like every file: a time mark is only ever written into an answer to a browser
        # (app/present/times.py). Where this answer holds a mark, the same answer is worded once more for a file.
        # An answer with facts is worded twice: for a file (what is stored) and for a screen (to learn which of its
        # times the app itself wrote: only those are shown in the viewer's zone later; a time inside a person's own
        # typed words, such as a reason, is never touched).
        kept, facts = reply, None
        if reply.get("facts"):
            if times.marked():  # (asked by a browser: the answer is the screen's wording)
                shown = reply
                with times.for_files():
                    kept = self.copilot.command(self, a.id, page, item, text)
            else:  # (asked by a script: the answer is the file's wording)
                with times.for_screen():
                    shown = self.copilot.command(self, a.id, page, item, text)
            if len(shown.get("facts") or []) == len(kept.get("facts") or []):
                facts = [
                    {**f, "times": times.moments(s["text"])} for f, s in zip(kept["facts"], shown["facts"], strict=True)
                ]
            else:  # (the records changed between the two readings: no time is marked later)
                facts = [{**f, "times": []} for f in kept.get("facts") or []]
        elif times.marked() and times.OPEN in reply["text"]:
            with times.for_files():
                kept = self.copilot.command(self, a.id, page, item, text)
        with self.db() as db:
            db.add(
                AssistantMessageRow(
                    plan_id=plan_id,
                    at=iso(datetime.now(timezone.utc)),
                    by=self.decision_name(),  # type: ignore[attr-defined]
                    page=page,
                    item=(item or None) and str(item)[:200],
                    thread=reply.get("thread"),
                    said=" ".join(str(text).split())[:500],
                    kind=reply["kind"],
                    reply=kept["text"],
                    go=reply.get("go"),
                    facts=facts,
                )
            )
            db.commit()
        return reply

    def assistant_messages(self, plan_id: int | None) -> list[dict]:
        """Everything said to Otto in this assessment, oldest first. A read."""
        if plan_id is None:
            return []
        with self.db() as db:
            rows = db.scalars(
                select(AssistantMessageRow)
                .where(AssistantMessageRow.plan_id == plan_id)
                .order_by(AssistantMessageRow.id)
            ).all()
            # (the answer's own sentences were stored in UTC words; a browser gets the times the app itself wrote in them
            #  marked again, so that it writes them in the viewer's own zone. What a person typed is returned as typed.)
            return [
                {
                    "id": r.id,
                    "at": r.at,
                    "by": r.by,
                    "page": r.page,
                    "thread": r.thread,
                    "said": r.said,
                    "kind": r.kind,
                    "reply": r.reply,
                    "go": r.go,
                    "facts": [
                        {
                            "text": times.remarked(str(f.get("text") or ""), f.get("times")),
                            "link": f.get("link"),
                            "label": f.get("label"),
                        }
                        for f in r.facts or []
                    ],
                }
                for r in rows[-MAX_KEPT_SHOWN:]
            ]
