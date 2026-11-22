"""Change watch (phase 6d): the page's one read and its two actions. Each action is one click by the person at the
keyboard. Neither has a body: nothing here accepts software, a file or text. A demo change is named by one of our own
names, a change by the id the view gave it."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from app.changewatch.demo_changes import ORDER as DEMO_NAMES
from app.errors import NotFound
from app.web import models
from app.web.common import shows

# A change's id as the view writes it: "change-" and twelve characters of its commit. (A demo change is named by one of
# our own names, and only those are let through: the address is never matched against a pattern that could run long.)
_CHANGE_ID = re.compile(r"change-[0-9a-f]{12}")


def routes(lab, require_login) -> APIRouter:
    router = APIRouter()
    login = [Depends(require_login)]

    @router.get("/api/plans/{plan_id}/change-watch", dependencies=login, responses=shows(models.ChangeWatchView))
    def change_watch(plan_id: int):
        """The Changes view: every developer's change in the connected demo repository, read now. It only reads."""
        return lab.change_watch_view(plan_id)

    @router.post("/api/plans/{plan_id}/change-watch/demo/{name}", dependencies=login, responses=shows(models.ChangeWatchView))
    def bring_in_demo_change(plan_id: int, name: str):
        """Bring in a demo change (Demo data): one branch with one commit, written into this assessment's own copy of
        the repository. It runs nothing. `name` is one of our own names for a bundled change, and nothing else."""
        if name not in DEMO_NAMES:
            raise NotFound("That demo change does not exist.")
        lab.bring_in_demo_change(plan_id, name)
        return lab.change_watch_view(plan_id)

    @router.post("/api/plans/{plan_id}/change-watch/{change_id}/run", dependencies=login, responses=shows(models.ChangeWatchView))
    def run_picked_tests(plan_id: int, change_id: str):
        """Run the picked tests (then: Run again). Sent by that button, or by its Confirm in the Otto panel."""
        if len(change_id) != 19 or not _CHANGE_ID.fullmatch(change_id):
            raise NotFound("That change is not in the connected repository.")
        lab.run_picked_tests(plan_id, change_id)
        return lab.change_watch_view(plan_id)

    return router
