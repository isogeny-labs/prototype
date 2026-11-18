"""Phase 5c: Otto's routes. Settings (Test packs, Live Otto) belong to the installation; the Advisories page and the
decisions on Otto's proposals belong to one assessment (the closed guard refuses a decision on a closed one)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field, StrictBool, StrictStr

from app.web import models
from app.web.common import shows


class PackInstallBody(BaseModel):
    version: StrictStr = Field(max_length=20)


class LiveOttoBody(BaseModel):
    on: StrictBool | None = None                                   # turn Use live Claude on or off
    limit: StrictStr | None = Field(default=None, max_length=12)   # the spending limit per run, in US dollars


class DecisionBody(BaseModel):
    reason: StrictStr | None = Field(default=None, max_length=2000)     # a reject's optional short reason (held to 300 after cleaning)


NO_REASON = Body(default_factory=DecisionBody)      # a decision may come with no body at all: only a rejection has anything to say


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/otto", dependencies=login, responses=shows(models.OttoSettingsView))
    def otto():
        return lab.otto_view()

    @router.post("/api/otto/packs/check", dependencies=login, responses=shows(models.OttoSettingsView))
    def check_for_updates():
        return lab.check_pack_updates()

    @router.post("/api/otto/packs/install", dependencies=login, responses=shows(models.OttoSettingsView))
    def install_update(body: PackInstallBody):
        return lab.install_pack(body.version)

    @router.post("/api/otto/live", dependencies=login, responses=shows(models.OttoSettingsView))
    def live_otto(body: LiveOttoBody):
        return lab.set_live_otto(body.on, body.limit)

    @router.get("/api/plans/{plan_id}/advisories", dependencies=login, responses=shows(models.AdvisoriesView))
    def advisories(plan_id: int):
        return lab.advisories_view(plan_id)

    @router.get("/api/plans/{plan_id}/otto/proposals", dependencies=login, responses=shows(models.OttoProposalsView))
    def proposals(plan_id: int):
        return lab.otto_proposals_view(plan_id)

    @router.post("/api/plans/{plan_id}/otto/proposals/{proposal_id}/{decision}", dependencies=login, responses=shows(models.OttoProposal))
    def decide(plan_id: int, proposal_id: str, decision: str, body: DecisionBody = NO_REASON):
        """Accept, reject (with an optional short reason), undo or reconsider one of Otto's proposals. It runs nothing."""
        return lab.otto_decide_view(plan_id, proposal_id[:200], decision[:20], body.reason)

    return router
