"""The open routes: who is logged in, first-time password setup, and login."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app import auth
from app.web import models
from app.web.common import PasswordBody, error_response, shows


def routes(lab, set_cookie) -> APIRouter:
    router = APIRouter()

    @router.get("/api/session", responses=shows(models.Session))
    def get_session(request: Request):
        return lab.session_json(request.cookies.get(auth.COOKIE_NAME))

    @router.post("/api/setup", responses=shows(models.Ok))
    def setup(body: PasswordBody, response: Response):
        if not lab.settings.password_login:
            return error_response(404, "This app is set up for logging in with GitHub only.")
        with lab.db() as db:
            if not auth.setup_required(db):
                return error_response(409, "A password has already been created. Log in with it.")
            if len(body.password) < auth.MIN_PASSWORD_LENGTH:
                return error_response(
                    422, f"Choose a password of at least {auth.MIN_PASSWORD_LENGTH} characters.", field="password"
                )
            auth.create_password(db, body.password)
            set_cookie(response, auth.new_session(db))
        return {"ok": True}

    @router.post("/api/login", responses=shows(models.Ok))
    def login(body: PasswordBody, response: Response):
        if not lab.settings.password_login:
            return error_response(404, "This app is set up for logging in with GitHub only.")
        with lab.db() as db:
            if not auth.password_matches(db, body.password):
                return error_response(401, "That password is not right.", field="password")
            set_cookie(response, auth.new_session(db))
        return {"ok": True}

    return router
