"""Web API (FastAPI). Everything is under /api and, apart from session/setup/login, needs a login.

Start it with:  python -m app      (from the backend folder; listens on 127.0.0.1:8000 only)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Receive, Scope, Send

from app import auth
from app.config import FRONTEND_DIST, Settings, load_settings
from app.importer.common import ImportFileError
from app.lab.hub import BadRequest, Conflict, Lab, NotFound
from app.present.times import MarkTimes
from app.web import assistant as assistant_routes
from app.web import changewatch as changewatch_routes
from app.web import changes, checks, dependencies, fixes, hosting, importing, migration, projects, session
from app.web import lab as lab_routes
from app.web import observatory as observatory_routes
from app.web import otto as otto_routes
from app.web import record as record_routes
from app.web import tests as test_routes
from app.web.turns import OneReadAtATime
from app.web.who import WhoIsAsking
from app.web.common import error_response


class HostCheckButHealth(TrustedHostMiddleware):
    """The host check, as before, except for GET /api/health (hosting): a load balancer's probe names the machine's own
    address as the host, and the health check shows no data."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/api/health" and scope.get("method") == "GET":
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


def allowed_hosts(settings: Settings) -> list[str]:
    hosts = ["localhost", "127.0.0.1", "testserver", *settings.allowed_hosts]
    if settings.public_url:
        host = urlparse(settings.public_url).hostname
        if host:
            hosts.append(host)
    return hosts


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
    # Hosting: EVIDENCE_LAB_ALLOWED_HOSTS and the host of EVIDENCE_LAB_PUBLIC_URL are added to that list.
    app.add_middleware(HostCheckButHealth, allowed_hosts=allowed_hosts(settings))
    # The 5c fixes: a browser asks for marked times with one header, and writes each in the viewer's own time zone.
    # Without the header every sentence keeps its UTC words (scripts, the accuracy check, downloads).
    app.add_middleware(MarkTimes)
    # Who did what: the session of a request is known to the Lab while it is answered, so a press is recorded under
    # the account that pressed it (app/web/who.py, app/lab/actions.py).
    app.add_middleware(WhoIsAsking)
    # Reads take turns, first come, first served: several views worked out side by side are much slower than one after
    # another (app/web/turns.py). Anything that changes something does not wait.
    app.add_middleware(OneReadAtATime)

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
            if not auth.session_valid(db, request.cookies.get(auth.COOKIE_NAME), settings.login_methods):
                raise HTTPException(401, "Please log in.")

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            auth.COOKIE_NAME,
            token,
            httponly=True,
            samesite="strict",
            path="/",
            secure=settings.secure_cookies,
            max_age=int(auth.SESSION_LIFETIME.total_seconds()),
        )

    app.include_router(session.routes(lab, set_cookie))
    app.include_router(hosting.routes(lab, set_cookie))  # hosting: log in with GitHub, log out, health
    app.include_router(projects.routes(lab, require_login))
    # Phase 5a: a changing request on a closed assessment is refused (see web/projects.py for the two exceptions).
    guarded = [Depends(projects.closed_guard(lab, require_login))]
    app.include_router(importing.routes(lab, require_login), dependencies=guarded)
    app.include_router(test_routes.routes(lab, require_login), dependencies=guarded)
    app.include_router(lab_routes.routes(lab, require_login), dependencies=guarded)
    app.include_router(migration.routes(lab, require_login), dependencies=guarded)
    app.include_router(dependencies.routes(lab, require_login), dependencies=guarded)
    app.include_router(changes.routes(lab, require_login), dependencies=guarded)
    app.include_router(fixes.routes(lab, require_login), dependencies=guarded)
    app.include_router(checks.routes(lab, require_login), dependencies=guarded)  # phase 5b
    app.include_router(otto_routes.routes(lab, require_login), dependencies=guarded)  # phase 5c
    app.include_router(
        assistant_routes.routes(lab, require_login), dependencies=guarded
    )  # phase 6a: the panel's read; 6b: a typed sentence
    app.include_router(changewatch_routes.routes(lab, require_login), dependencies=guarded)  # phase 6d: Change watch
    # Evidence as the full record: the timeline, the decisions, the evidence files, an item's history (reads only)
    app.include_router(record_routes.routes(lab, require_login), dependencies=guarded)
    # The Observatory (design refactor): the map of the systems as the files describe them. Reads only.
    app.include_router(observatory_routes.routes(lab, require_login), dependencies=guarded)

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
