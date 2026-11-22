"""The plan of tests: ordering, adding, removing and running them."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.web import models
from app.web.common import AddTestBody, OrderBody, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    # ---------------------------------------------------------------- tests and Evidence Lab (all need login)
    # There is no route here that accepts software, or any file: bodies are the small JSON objects above.

    @router.get("/api/import/{import_id}/plan", dependencies=[Depends(require_login)], responses=shows(models.PlanView))
    def get_plan_for_import(import_id: int):
        return lab.get_plan_for_import(import_id)

    @router.post(
        "/api/import/{import_id}/plan", dependencies=[Depends(require_login)], responses=shows(models.PlanView)
    )
    def ensure_plan(import_id: int):
        return lab.ensure_plan(import_id)

    @router.get("/api/plans/{plan_id}", dependencies=[Depends(require_login)], responses=shows(models.PlanView))
    def get_plan(plan_id: int):
        return lab.plan_view(plan_id)

    @router.post("/api/plans/{plan_id}/order", dependencies=[Depends(require_login)], responses=shows(models.PlanView))
    def reorder(plan_id: int, body: OrderBody):
        return lab.reorder(plan_id, list(body.order))

    @router.post("/api/plans/{plan_id}/tests", dependencies=[Depends(require_login)], responses=shows(models.PlanView))
    def add_test(plan_id: int, body: AddTestBody):
        return lab.add_test(plan_id, body.catalog_id)

    @router.post(
        "/api/plans/{plan_id}/tests/{item_id}/remove",
        dependencies=[Depends(require_login)],
        responses=shows(models.PlanView),
    )
    def remove_test(plan_id: int, item_id: int):
        return lab.remove_test(plan_id, item_id)

    @router.post(
        "/api/plans/{plan_id}/tests/{item_id}/run",
        dependencies=[Depends(require_login)],
        responses=shows(models.PlanView),
    )
    def run_test(plan_id: int, item_id: int):
        return lab.run_test(plan_id, item_id)

    @router.post(
        "/api/plans/{plan_id}/run-all", dependencies=[Depends(require_login)], responses=shows(models.PlanView)
    )
    def run_all(plan_id: int):
        return lab.run_all(plan_id)

    return router
