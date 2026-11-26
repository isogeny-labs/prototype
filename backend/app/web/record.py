"""Evidence as the full record (design refactor, section 6): the Timeline, one entry's story, Approvals and decisions,
Evidence files, and the history in an item's panel.

Five reads. None has a body, none changes anything and none starts anything: each puts the records the assessment
already keeps into order and says who did what. They work on a closed assessment as on an open one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.web import models
from app.web.common import shows

AREA = Query(None, max_length=20, description="One of the places (observe, advisories, checks, fixes, ...), or all.")
ZONE = Query(None, max_length=64, description="The viewer's time zone (an IANA name), to sort entries into days.")


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/plans/{plan_id}/timeline", dependencies=login, responses=shows(models.TimelineView))
    def timeline(
        plan_id: int,
        area: str | None = AREA,
        kind: str | None = Query(None, max_length=20, description="runs, people, system or files, or all."),
        q: str | None = Query(None, max_length=100, description="Words to search the entries for."),
        tz: str | None = ZONE,
    ):
        """Everything that happened in the assessment, newest first, by day."""
        return lab.timeline_view(plan_id, area, kind, q, tz)

    @router.get(
        "/api/plans/{plan_id}/timeline/{entry_id}", dependencies=login, responses=shows(models.TimelineEntryDetail)
    )
    def timeline_entry(plan_id: int, entry_id: str):
        """One entry's story: who, what it rested on, what came after, and the facts of its record."""
        return lab.timeline_entry_view(plan_id, entry_id[:80])

    @router.get("/api/plans/{plan_id}/decisions", dependencies=login, responses=shows(models.DecisionsView))
    def decisions(plan_id: int, area: str | None = AREA, tz: str | None = ZONE):
        """Every decision a person made in the assessment, newest first, by day."""
        return lab.decisions_view(plan_id, area, tz)

    @router.get("/api/plans/{plan_id}/evidence-files", dependencies=login, responses=shows(models.EvidenceFilesView))
    def evidence_files(plan_id: int):
        """Every download of the signed evidence file, how to check a file, and what it holds."""
        return lab.evidence_files_view(plan_id)

    @router.get("/api/plans/{plan_id}/history", dependencies=login, responses=shows(models.HistoryView))
    def history(plan_id: int, key: str = Query(..., min_length=3, max_length=720)):
        """The history of one item, keyed as the Related block keys its panel (test:12, fix:..., change:..., system:...)."""
        return lab.history_view(plan_id, key)

    return router
