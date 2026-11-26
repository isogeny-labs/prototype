"""The Observatory's routes (design refactor, section 5): the map of the systems as the files describe them, one box
of it opened, and where a result sits on it.

All three only read. Nothing here runs a check, decides a result, writes a row or asks Claude: the map is worked out
from the files and the pages' own views on every ask (app/observatory)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.observatory import build
from app.web import models
from app.web.common import shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/plans/{plan_id}/observatory", dependencies=login, responses=shows(models.ObservatoryView))
    def observatory(plan_id: int):
        """The map: the boxes, where the cryptography is in each with its checks by name, the lines, the four counts by
        tag and what the files don't say."""
        return build.view_of_plan(lab, plan_id)

    @router.get(
        "/api/assessments/{assessment_id}/observatory", dependencies=login, responses=shows(models.ObservatoryView)
    )
    def observatory_of_assessment(assessment_id: int):
        """The same map by the assessment. It also answers before the assessment has a file (state "empty", with the
        way to Import) and before its test plan was made."""
        return build.view_of_assessment(lab, assessment_id)

    # (declared before the route of one box: "place" is not a box)
    @router.get("/api/plans/{plan_id}/observatory/place", dependencies=login, responses=shows(models.ObservatoryPlace))
    def place(plan_id: int, key: str = Query(..., min_length=1, max_length=700)):
        """Where the item a side panel is about sits on the map, by the key its Related block uses; `place` is null
        when the item is not on the map."""
        return build.place_of_plan(lab, plan_id, key)

    @router.get(
        "/api/plans/{plan_id}/observatory/{box:path}", dependencies=login, responses=shows(models.ObservatoryPanel)
    )
    def box(plan_id: int, box: str):
        """The panel of one box of the map (its key may hold colons and slashes: it is the rest of the address)."""
        return build.panel_of_plan(lab, plan_id, box)

    return router
