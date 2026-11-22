"""The open routes of hosting: log in with GitHub, log out, and the health check (21 November 2026)."""
from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Cookie, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import auth, github_login
from app.infra.database import ping as ping_database
from app.web.common import error_response

log = logging.getLogger("evidence_lab.hosting")


def _page(title: str, sentence: str, status: int = 200, go_home: bool = False) -> HTMLResponse:
    """A tiny page. After a login it moves on to the app from this page, so the browser sends the new session cookie
    (SameSite=Strict) on the next request: a redirect that GitHub started would not."""
    refresh = '<meta http-equiv="refresh" content="0;url=/">' if go_home else ""
    body = (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{refresh}</head>"
            f"<body style='font-family:system-ui;background:#020617;color:#e2e8f0;padding:3rem'>"
            f"<p>{html.escape(sentence)}</p><p><a style='color:#93c5fd' href='/'>Back to the app</a></p></body></html>")
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def routes(lab, set_cookie) -> APIRouter:
    router = APIRouter()
    settings = lab.settings

    def redirect_uri(request: Request) -> str:
        base = settings.public_url or str(request.base_url).rstrip("/")
        return base + github_login.CALLBACK_PATH

    @router.get("/api/auth/github/start", include_in_schema=False)
    def github_start(request: Request):
        if settings.github is None:
            return error_response(404, "Logging in with GitHub is not set up for this app.")
        target, state = github_login.start(settings.github, lab.cache, redirect_uri(request))
        response = RedirectResponse(target, status_code=302)
        # Lax: the cookie must come back on GitHub's redirect to the callback (a top-level navigation from github.com).
        response.set_cookie(github_login.STATE_COOKIE, state, httponly=True, samesite="lax",
                            secure=settings.secure_cookies, path=github_login.CALLBACK_PATH,
                            max_age=github_login.STATE_LIFETIME_SECONDS)
        return response

    @router.get(github_login.CALLBACK_PATH, include_in_schema=False)
    def github_callback(request: Request):
        if settings.github is None:
            return _page("Log in", "Logging in with GitHub is not set up for this app.", 404)
        query = request.query_params
        if query.get("error"):
            response = _page("Log in", "The login was cancelled on GitHub.", 400)
        else:
            try:
                with lab.db() as db:
                    token = github_login.finish(settings.github, lab.cache, db, code=query.get("code"),
                                                state=query.get("state"),
                                                cookie_state=request.cookies.get(github_login.STATE_COOKIE))
            except github_login.LoginRefused as exc:
                log.info("GitHub login refused: %s", exc)
                response = _page("Log in", str(exc), 403)
            else:
                response = _page("Logging in", "Logged in. Opening the app...", go_home=True)
                set_cookie(response, token)
        response.delete_cookie(github_login.STATE_COOKIE, path=github_login.CALLBACK_PATH)
        return response

    @router.post("/api/logout", include_in_schema=False)
    def logout(response: Response, session_token: str | None = Cookie(default=None, alias=auth.COOKIE_NAME)):
        # Reads only the session cookie (no body): tests/test_plan_api.py holds every POST to that.
        with lab.db() as db:
            auth.end_session(db, session_token)
        response.delete_cookie(auth.COOKIE_NAME, path="/")
        return {"ok": True}

    @router.get("/api/health", include_in_schema=False)
    def health():
        """Open (for a load balancer): says which kind of database, cache and file store is used and whether each
        answers. No address, name or secret is shown."""
        parts = {}
        for name, kind, check in (
            ("database", lab.db_engine.dialect.name, lambda: ping_database(lab.db_engine)),
            ("cache", lab.cache.kind, lab.cache.ping),
            ("storage", lab.store.kind if lab.store else "none", lab.store.ping if lab.store else (lambda: None)),
        ):
            try:
                check()
                parts[name] = {"kind": kind, "ok": True}
            except Exception as exc:   # noqa: BLE001 - any failure is reported as not ok
                log.warning("health: %s (%s) does not answer: %s", name, kind, exc)
                parts[name] = {"kind": kind, "ok": False}
        ok = all(p["ok"] for p in parts.values())
        return JSONResponse({"ok": ok, **parts}, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})

    return router
