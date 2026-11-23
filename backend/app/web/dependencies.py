"""The Dependencies view (phase 4d): add a dependency list, say which system a top entry is part of, and measure."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.importer.common import ImportFileError
from app.importer.sbom import MAX_LIST_BYTES
from app.web import models
from app.web.common import DependencyMeasureBody, DependencyTieBody, shows

TOO_LARGE = "This file is larger than 16 MB. Evidence Lab reads dependency lists up to 16 MB."


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/import/{import_id}/dependencies",
        dependencies=[Depends(require_login)],
        responses=shows(models.DependenciesView),
    )
    def dependencies_view(import_id: int):
        return lab.dependencies_view_for_import(import_id)

    @router.post(
        "/api/plans/{plan_id}/dependencies",
        dependencies=[Depends(require_login)],
        responses=shows(models.DependenciesView),
    )
    async def add_list(plan_id: int, request: Request, filename: str = ""):
        # Read as data, in pieces, and stop at the limit: nothing in the file is run, and a refused file changes nothing.
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_LIST_BYTES:
            raise ImportFileError(TOO_LARGE)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_LIST_BYTES:
                raise ImportFileError(TOO_LARGE)
        return await run_in_threadpool(lab.add_dependency_list, plan_id, filename[:300], bytes(data))

    @router.post(
        "/api/plans/{plan_id}/dependencies/tie",
        dependencies=[Depends(require_login)],
        responses=shows(models.DependenciesView),
    )
    def tie(plan_id: int, body: DependencyTieBody):
        return lab.tie_dependency(plan_id, body.top, body.system or None)

    @router.post(
        "/api/plans/{plan_id}/dependencies/measure",
        dependencies=[Depends(require_login)],
        responses=shows(models.DependenciesView),
    )
    def measure(plan_id: int, body: DependencyMeasureBody):
        return lab.measure_dependencies(plan_id, body.row)

    return router
