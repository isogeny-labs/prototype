"""Phase 5c: Otto's routes. Settings (Test packs, Live Otto) belong to the installation; the Advisories page and
Add new checks belong to one assessment (the closed guard refuses the add on a closed one)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StrictBool, StrictStr

from app.web import models
from app.web.common import shows


class PackInstallBody(BaseModel):
    version: StrictStr = Field(max_length=20)


class LiveOttoBody(BaseModel):
    on: StrictBool | None = None                                   # turn Use live Claude on or off
    limit: StrictStr | None = Field(default=None, max_length=12)   # the spending limit per run, in US dollars


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

    @router.post("/api/plans/{plan_id}/advisories/add", dependencies=login, responses=shows(models.AdvisoriesView))
    def add_new_checks(plan_id: int):
        return lab.add_new_checks(plan_id)

    return router
