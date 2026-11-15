"""Web API (FastAPI). Everything is under /api and, apart from session/setup/login, needs a login.

Start it with:  python -m app      (from the backend folder; listens on 127.0.0.1:8000 only)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import auth
from app.config import FRONTEND_DIST, Settings, load_settings
from app.importer.common import ImportFileError
from app.lab.hub import BadRequest, Conflict, Lab, NotFound
from app.web import changes, fixes, importing, migration, session
from app.web import lab as lab_routes
from app.web import tests as test_routes
from app.web.common import error_response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    lab = Lab(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        lab.start()
        try:
            yield
        finally:
            lab.stop()

    app = FastAPI(title="Isogeny Evidence Lab", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lab = lab
    # Only answer requests addressed to this computer (stops other web pages reaching the app by a trick name).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = [str(p) for p in first.get("loc", []) if p != "body"]
        field = ".".join(loc) or None
        return error_response(422, f"The request is not valid{f' ({field})' if field else ''}.", field=field)

    @app.exception_handler(ImportFileError)
    async def _import_error(_request: Request, exc: ImportFileError):
        return error_response(422, exc.message, exc.line, exc.field)

    @app.exception_handler(NotFound)
    async def _not_found(_request: Request, exc: NotFound):
        return error_response(404, str(exc))

    @app.exception_handler(BadRequest)
    async def _bad_request(_request: Request, exc: BadRequest):
        return error_response(422, exc.message, field=exc.field)

    @app.exception_handler(Conflict)
    async def _conflict(_request: Request, exc: Conflict):
        return error_response(409, str(exc))

    def require_login(request: Request) -> None:
        with lab.db() as db:
            if not auth.session_valid(db, request.cookies.get(auth.COOKIE_NAME)):
                raise HTTPException(401, "Please log in.")

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="strict", path="/",
                            max_age=int(auth.SESSION_LIFETIME.total_seconds()))

    app.include_router(session.routes(lab, set_cookie))
    app.include_router(importing.routes(lab, require_login))
    app.include_router(test_routes.routes(lab, require_login))
    app.include_router(lab_routes.routes(lab, require_login))
    app.include_router(migration.routes(lab, require_login))
    app.include_router(changes.routes(lab, require_login))
    app.include_router(fixes.routes(lab, require_login))

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def no_such_api(rest: str):
        return error_response(404, "There is no such address in this app.")

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


def __getattr__(name: str):
    """`uvicorn app.main:app` works, without creating the app (and its data folder) on a plain import."""
    if name == "app":
        global _app
        try:
            return _app
        except NameError:
            _app = create_app()
            return _app
    raise AttributeError(name)
