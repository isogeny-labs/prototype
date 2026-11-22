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


class SandboxBody(BaseModel):
    on: StrictBool | None = None                                       # turn Sandbox research on or off
    by_itself: StrictBool | None = None                                # the tick "Design and prove tests by itself"
    run_limit: StrictStr | None = Field(default=None, max_length=12)   # the most for one research run, in US dollars
    day_limit: StrictStr | None = Field(default=None, max_length=12)   # the most for a day, in US dollars


class NameBody(BaseModel):
    name: StrictStr = Field(max_length=400)                        # a person's name for their decisions (held to 60 after cleaning)


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

    @router.post("/api/otto/sandbox", dependencies=login, responses=shows(models.OttoSettingsView))
    def sandbox_research(body: SandboxBody):
        """Sandbox research (prototype): the switch, its tick and its two spending limits. The switch can be turned on
        only on a computer marked as Isogeny's own sandbox, in isolated mode, with Otto installed."""
        return lab.set_sandbox(body.on, body.by_itself, body.run_limit, body.day_limit)

    @router.post("/api/otto/name", dependencies=login, responses=shows(models.OttoSettingsView))
    def decision_name(body: NameBody):
        """Phase 6a: the name a person types once; their decisions on proposals are recorded under it from then on."""
        return lab.set_decision_name(body.name)

    @router.get("/api/plans/{plan_id}/advisories", dependencies=login, responses=shows(models.AdvisoriesView))
    def advisories(plan_id: int):
        return lab.advisories_view(plan_id)

    @router.post("/api/plans/{plan_id}/advisories/look", dependencies=login, responses=shows(models.AdvisoriesView))
    def look_for_advisories(plan_id: int):
        """Phase 6: Look for new advisories. One read of the public source about this assessment's libraries (package
        names only are sent). It runs nothing and proposes nothing."""
        return lab.look_for_advisories(plan_id)

    @router.post("/api/plans/{plan_id}/advisories/research", dependencies=login, responses=shows(models.AdvisoriesView))
    def design_and_prove(plan_id: int):
        """Phase 6: Design and prove tests, for the new advisories of the newest look, in the background."""
        return lab.start_research(plan_id)

    @router.get("/api/plans/{plan_id}/otto/proposals", dependencies=login, responses=shows(models.OttoProposalsView))
    def proposals(plan_id: int):
        return lab.otto_proposals_view(plan_id)

    @router.post("/api/plans/{plan_id}/otto/proposals/{proposal_id}/{decision}", dependencies=login, responses=shows(models.OttoProposal))
    def decide(plan_id: int, proposal_id: str, decision: str, body: DecisionBody = NO_REASON):
        """Accept, reject (with an optional short reason), undo or reconsider one of Otto's proposals. It runs nothing."""
        return lab.otto_decide_view(plan_id, proposal_id[:200], decision[:20], body.reason)

    return router
