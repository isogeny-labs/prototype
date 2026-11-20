"""The Otto panel's routes. Phase 6a: its one read. Phase 6b: a typed sentence, answered.

Nothing here decides or starts anything, and none asks Claude. The two reads change nothing. The one write keeps what a
person typed and the one line Otto answered, with the assessment; it sits under the closed guard like every route that
writes, so a closed assessment keeps nothing (its text box uses the read)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StrictStr

from app.web import models
from app.web.common import shows


class SayBody(BaseModel):
    text: StrictStr = Field(min_length=1, max_length=500)          # the person's own words; they are read by fixed rules, as data
    page: StrictStr = Field(max_length=60)
    item: StrictStr | None = Field(default=None, max_length=200)


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/assessments/{assessment_id}/assistant", dependencies=login, responses=shows(models.AssistantView))
    def assistant(assessment_id: int, page: str = Query("overview", max_length=60), item: str | None = Query(None, max_length=200)):
        """What the panel shows beside this page of this assessment, with this item open: the open tabs, what fits the
        page, what waits elsewhere and the status line."""
        return lab.assistant_view(assessment_id, page, item)

    @router.get("/api/assessments/{assessment_id}/assistant/answer", dependencies=login, responses=shows(models.AssistantReply))
    def answer(assessment_id: int, text: str = Query(..., min_length=1, max_length=500), page: str = Query("overview", max_length=60),
               item: str | None = Query(None, max_length=200)):
        """Otto's answer to one typed sentence, and nothing kept: where to go, or a card with its Confirm step."""
        return lab.assistant_answer(assessment_id, page, item, text)

    @router.post("/api/plans/{plan_id}/assistant/messages", dependencies=login, responses=shows(models.AssistantReply))
    def say(plan_id: int, body: SayBody):
        """The same answer, and the exchange kept with the assessment. It decides and starts nothing."""
        return lab.assistant_say(plan_id, body.page, body.item, body.text)

    return router
