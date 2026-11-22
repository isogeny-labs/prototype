"""Phase 5b: the Checks page, one check's detail, and the Related block of any item."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.web import models
from app.web.common import shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/plans/{plan_id}/checks", dependencies=login, responses=shows(models.ChecksView))
    def checks(plan_id: int):
        return lab.checks_view(plan_id)

    @router.get("/api/plans/{plan_id}/checks/{check_id}", dependencies=login, responses=shows(models.CheckDetail))
    def check(plan_id: int, check_id: str):
        return lab.check_detail(plan_id, check_id)

    @router.get("/api/plans/{plan_id}/related", dependencies=login, responses=shows(models.RelatedView))
    def related(plan_id: int, key: str):
        return {"key": key, "related": lab.related(plan_id, key)}

    return router
