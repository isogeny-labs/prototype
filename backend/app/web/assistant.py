"""Phase 6a: the Otto panel's one read. It only reads: no route here changes anything, and none asks Claude."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.web import models
from app.web.common import shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/assessments/{assessment_id}/assistant", dependencies=login, responses=shows(models.AssistantView))
    def assistant(assessment_id: int, page: str = Query("overview", max_length=60), item: str | None = Query(None, max_length=200)):
        """What the panel shows beside this page of this assessment, with this item open: the open tabs, what fits the
        page, what waits elsewhere and the status line."""
        return lab.assistant_view(assessment_id, page, item)

    return router
