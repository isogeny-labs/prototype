"""Who is asking (design refactor, decision I): the session of an /api request, made known to the `Lab` for the time of
that request, so a press is recorded under the account that pressed it (app/lab/actions.py).

Only the session cookie is read, and only its value is passed on, in memory, for this one request: it is never stored,
shown or logged here. Whether it is a valid session, and whose, is looked up at the moment of a press (`Lab.actor()`).
A request with no valid session never reaches a button: every route that changes something needs the login."""

from __future__ import annotations

from starlette.requests import HTTPConnection

from app import auth
from app.lab import actions


class WhoIsAsking:
    """Web middleware: for an /api request, the `Lab` can read which session is asking."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and str(scope.get("path") or "").startswith("/api/"):
            with actions.asking(HTTPConnection(scope).cookies.get(auth.COOKIE_NAME)):
                await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)


__all__ = ["WhoIsAsking"]
