"""A change: try on a test copy, approvals, Apply and Roll back (phase 4b)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.present import times
from app.web import models
from app.web.common import ApproveChangeBody, AskApprovalBody, ChangeBody, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    # ---- a change: try on a test copy, approvals, Apply and Roll back (phase 4b)
    @router.post("/api/plans/{plan_id}/changes/try", dependencies=[Depends(require_login)], responses=shows(models.Ok))
    def change_try(plan_id: int, body: ChangeBody):
        return lab.try_change(plan_id, body.change)

    @router.post("/api/plans/{plan_id}/changes/ask-approval", dependencies=[Depends(require_login)], responses=shows(models.Ok))
    def change_ask(plan_id: int, body: AskApprovalBody):
        return lab.ask_approval(plan_id, body.change, list(body.reviewers))

    @router.post("/api/plans/{plan_id}/changes/approve", dependencies=[Depends(require_login)], responses=shows(models.Ok))
    def change_approve(plan_id: int, body: ApproveChangeBody):
        return lab.approve_change(plan_id, body.change, body.reviewer)

    @router.post("/api/plans/{plan_id}/changes/apply", dependencies=[Depends(require_login)], responses=shows(models.Ok))
    def change_apply(plan_id: int, body: ChangeBody):
        return lab.apply_change(plan_id, body.change)

    @router.post("/api/plans/{plan_id}/changes/rollback", dependencies=[Depends(require_login)], responses=shows(models.Ok))
    def change_rollback(plan_id: int, body: ChangeBody):
        return lab.rollback_change(plan_id, body.change)

    @router.get("/api/plans/{plan_id}/changes/download", dependencies=[Depends(require_login)])
    def change_download(plan_id: int, change: str = Query(max_length=700)):
        with times.for_files():      # a download keeps UTC, whoever asks
            filename, data = lab.change_download(plan_id, change)
        return Response(content=data, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

    return router
