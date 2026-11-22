"""Importing a scanner file (or the demo file), confirming addresses, and Verify."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.config import MAX_UPLOAD_BYTES
from app.importer.common import ImportFileError
from app.web import models
from app.web.common import ConfirmBody, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    @router.post("/api/import/demo", dependencies=[Depends(require_login)], responses=shows(models.Import))
    def import_demo(assessment_id: int | None = None):
        # Phase 5a: the screens always name the assessment; without one the file goes to "Imported without a project".
        return lab.import_demo(assessment_id=assessment_id)

    @router.post("/api/import/file", dependencies=[Depends(require_login)], responses=shows(models.Import))
    async def import_file(request: Request, filename: str = "", assessment_id: int | None = None):
        try:
            return await read_upload(request, filename, assessment_id)
        except ImportFileError:
            # A failed upload leaves nothing imported: the previous file's claims must not come back on a refresh.
            await run_in_threadpool(lab.clear_current_import)
            raise

    async def read_upload(request: Request, filename: str, assessment_id: int | None):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
            raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
        return await run_in_threadpool(lab.import_file, filename[:300], bytes(data), assessment_id)

    @router.get("/api/import/current", dependencies=[Depends(require_login)], responses=shows(models.Import))
    def current_import():
        return lab.current_import()

    @router.post("/api/import/{import_id}/confirm-address", dependencies=[Depends(require_login)], responses=shows(models.Address))
    def confirm_address(import_id: int, body: ConfirmBody):
        return lab.confirm_address(import_id, body.address, body.confirmed)

    @router.post("/api/import/{import_id}/verify", dependencies=[Depends(require_login)], responses=shows(models.VerifyRun))
    def run_verify(import_id: int):
        return lab.verify(import_id)

    @router.get("/api/import/{import_id}/verify", dependencies=[Depends(require_login)], responses=shows(models.VerifyRun))
    def latest_verify(import_id: int):
        return lab.latest_verify(import_id)

    return router
