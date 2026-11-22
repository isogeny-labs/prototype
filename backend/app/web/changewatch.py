"""Change watch (phase 6d): the page's one read and its two actions. Each action is one click by the person at the
keyboard. Neither has a body: nothing here accepts software, a file or text. A demo change is named by one of our own
names, a change by the id the view gave it."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StrictStr

from app.changewatch.demo_changes import ORDER as DEMO_NAMES
from app.errors import NotFound
from app.web import models
from app.web.common import shows

# A change's id as the view writes it: "change-" and twelve characters of its commit. (A demo change is named by one of
# our own names, and only those are let through: the address is never matched against a pattern that could run long.)
_CHANGE_ID = re.compile(r"change-[0-9a-f]{12}")


class WatchStopBody(BaseModel):
    item: StrictStr = Field(max_length=200)                              # the item's key, as the view gave it
    reason: StrictStr | None = Field(default=None, max_length=2000)      # optional (held to 300 after cleaning)


class WatchAgainBody(BaseModel):
    item: StrictStr = Field(max_length=200)


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

    # ---- the Watch list (sandbox research, a prototype): the page's second view. With the switch off the read says so
    #      and every action is refused.

    @router.get("/api/plans/{plan_id}/watch-list", dependencies=login, responses=shows(models.WatchListView))
    def watch_list(plan_id: int):
        """Published weaknesses in this assessment's libraries with no fix yet. It only reads: nothing is sent or written."""
        return lab.watch_list_view(plan_id)

    @router.post("/api/plans/{plan_id}/watch-list/look", dependencies=login, responses=shows(models.WatchListView))
    def watch_list_look(plan_id: int):
        """Look now: one click, after the box that says what is sent (package names, nothing else)."""
        return lab.watch_list_look(plan_id)

    @router.post("/api/plans/{plan_id}/watch-list/stop", dependencies=login, responses=shows(models.WatchListView))
    def watch_list_stop(plan_id: int, body: WatchStopBody):
        """Stop watching one weakness, with an optional short reason. Recorded; nothing is deleted."""
        return lab.watch_list_mark(plan_id, body.item, True, body.reason)

    @router.post("/api/plans/{plan_id}/watch-list/watch", dependencies=login, responses=shows(models.WatchListView))
    def watch_list_again(plan_id: int, body: WatchAgainBody):
        """Watch a weakness again."""
        return lab.watch_list_mark(plan_id, body.item, False)

    return router
