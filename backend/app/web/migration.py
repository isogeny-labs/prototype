"""The Migration step (phase 4a)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.web import models
from app.web.common import MigrationChoiceBody, MigrationSettingBody, shows


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()

    # ---- the Migration step (phase 4a)
    @router.get(
        "/api/import/{import_id}/migration",
        dependencies=[Depends(require_login)],
        responses=shows(models.MigrationView),
    )
    def migration_view(import_id: int):
        return lab.migration_view_for_import(import_id)

    @router.post(
        "/api/plans/{plan_id}/migration/measure",
        dependencies=[Depends(require_login)],
        responses=shows(models.MigrationView),
    )
    def migration_measure(plan_id: int):
        return lab.measure_migration(plan_id)

    @router.post(
        "/api/plans/{plan_id}/migration/settings",
        dependencies=[Depends(require_login)],
        responses=shows(models.MigrationView),
    )
    def migration_setting(plan_id: int, body: MigrationSettingBody):
        return lab.set_migration_setting(plan_id, body.system, body.field, body.value)

    @router.post(
        "/api/plans/{plan_id}/migration/choice",
        dependencies=[Depends(require_login)],
        responses=shows(models.MigrationView),
    )
    def migration_choice(plan_id: int, body: MigrationChoiceBody):
        return lab.choose_migration_option(plan_id, body.system, body.option, body.reason, body.review_date)

    return router
