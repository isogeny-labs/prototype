"""Fixes: each route is one action by the person at the keyboard; the app never merges on its own."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.present import times
from app.web import models
from app.web.common import ApproveBody, PullRequestBody, download, known_shape, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    # ---------------------------------------------------------------- Fixes (all need login)
    # Each route is one action by the person at the keyboard; the app never merges on its own. The bodies are
    # two small JSON objects that name reviewers from a fixed list. Nothing here accepts software or a file.

    @router.get("/api/plans/{plan_id}/fixes", dependencies=[Depends(require_login)], responses=shows(models.FixesView))
    def fixes_view(plan_id: int):
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/connect", dependencies=[Depends(require_login)], responses=shows(models.FixesView)
    )
    def connect_code(plan_id: int):
        lab.connect_code(plan_id)
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/{fix_id}/proof",
        dependencies=[Depends(require_login)],
        responses=shows(models.FixesView),
    )
    def run_proof_again(plan_id: int, fix_id: str):
        lab.run_proof_again(plan_id, known_shape(fix_id))
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/{fix_id}/pull-request",
        dependencies=[Depends(require_login)],
        responses=shows(models.FixesView),
    )
    def open_pull_request(plan_id: int, fix_id: str, body: PullRequestBody):
        lab.open_pull_request(plan_id, known_shape(fix_id), list(body.reviewers))
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/{fix_id}/approve",
        dependencies=[Depends(require_login)],
        responses=shows(models.FixesView),
    )
    def approve(plan_id: int, fix_id: str, body: ApproveBody):
        lab.approve(plan_id, known_shape(fix_id), body.reviewer)
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/{fix_id}/merge",
        dependencies=[Depends(require_login)],
        responses=shows(models.FixesView),
    )
    def merge(plan_id: int, fix_id: str):
        lab.merge(plan_id, known_shape(fix_id))  # sent by "Confirm merge" only
        return lab.fixes_view(plan_id)

    @router.post(
        "/api/plans/{plan_id}/fixes/{fix_id}/retest",
        dependencies=[Depends(require_login)],
        responses=shows(models.LabView),
    )
    def retest_now(plan_id: int, fix_id: str):
        return lab.retest_now(plan_id, known_shape(fix_id))

    @router.get("/api/plans/{plan_id}/fixes/{fix_id}/patch", dependencies=[Depends(require_login)])
    def patch_file(plan_id: int, fix_id: str):
        with times.for_files():  # a download keeps UTC, whoever asks
            filename, data = lab.patch_file(plan_id, known_shape(fix_id))
        return download(filename, data, "text/x-patch; charset=utf-8")

    return router
