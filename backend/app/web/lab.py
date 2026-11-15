"""The Evidence Lab step: results, marking reviewed, Dig deeper, retest and the evidence file."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.web import models
from app.web.common import RetestBody, download, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    @router.get("/api/plans/{plan_id}/lab", dependencies=[Depends(require_login)], responses=shows(models.LabView))
    def lab_view(plan_id: int):
        return lab.lab_view(plan_id)

    @router.post("/api/runs/{run_id}/mark-reviewed", dependencies=[Depends(require_login)], responses=shows(models.LabView))
    def mark_reviewed(run_id: int):
        return lab.mark_reviewed(run_id)

    @router.post("/api/runs/{run_id}/dig-deeper", dependencies=[Depends(require_login)], responses=shows(models.LabView))
    def dig_deeper(run_id: int):
        return lab.dig_deeper(run_id)

    @router.post("/api/plans/{plan_id}/retest", dependencies=[Depends(require_login)], responses=shows(models.LabView))
    def retest(plan_id: int, body: RetestBody):
        return lab.start_retest(plan_id, body.version, body.component)

    @router.post("/api/plans/{plan_id}/evidence", dependencies=[Depends(require_login)], responses=shows(models.EvidenceExport))
    def export_evidence(plan_id: int):
        return lab.export_evidence(plan_id)

    @router.get("/api/evidence/{export_id}/{which}", dependencies=[Depends(require_login)])
    def evidence_file(export_id: int, which: str):
        return download(*lab.evidence_file(export_id, which))

    return router
