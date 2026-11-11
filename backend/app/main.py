"""Web API (FastAPI). Everything is under /api and, apart from session/setup/login, needs a login.

Start it with:  python -m app      (from the backend folder; listens on 127.0.0.1:8000 only)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import auth
from .config import FRONTEND_DIST, MAX_UPLOAD_BYTES, Settings, load_settings
from .importers import ImportFileError
from .lab import BadRequest, Conflict, Lab, NotFound


class PasswordBody(BaseModel):
    password: str = Field(max_length=auth.MAX_PASSWORD_LENGTH)


class ConfirmBody(BaseModel):
    address: str = Field(max_length=300)
    confirmed: StrictBool


class OrderBody(BaseModel):
    order: list[StrictInt] = Field(max_length=50)


class AddTestBody(BaseModel):
    catalog_id: str = Field(max_length=40)


class RetestBody(BaseModel):
    version: str = Field(max_length=50)


def error_response(status: int, message: str, line: int | None = None, field: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "line": line, "field": field}})


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

    # ---------------------------------------------------------------- open endpoints

    @app.get("/api/session")
    def get_session(request: Request):
        return lab.session_json(request.cookies.get(auth.COOKIE_NAME))

    @app.post("/api/setup")
    def setup(body: PasswordBody, response: Response):
        with lab.db() as db:
            if not auth.setup_required(db):
                return error_response(409, "A password has already been created. Log in with it.")
            if len(body.password) < auth.MIN_PASSWORD_LENGTH:
                return error_response(422, f"Choose a password of at least {auth.MIN_PASSWORD_LENGTH} characters.",
                                      field="password")
            auth.create_password(db, body.password)
            set_cookie(response, auth.new_session(db))
        return {"ok": True}

    @app.post("/api/login")
    def login(body: PasswordBody, response: Response):
        with lab.db() as db:
            if not auth.password_matches(db, body.password):
                return error_response(401, "That password is not right.", field="password")
            set_cookie(response, auth.new_session(db))
        return {"ok": True}

    # ---------------------------------------------------------------- needs login

    @app.post("/api/import/demo", dependencies=[Depends(require_login)])
    def import_demo():
        return lab.import_demo()

    @app.post("/api/import/file", dependencies=[Depends(require_login)])
    async def import_file(request: Request, filename: str = ""):
        try:
            return await read_upload(request, filename)
        except ImportFileError:
            # A failed upload leaves nothing imported: the previous file's claims must not come back on a refresh.
            await run_in_threadpool(lab.clear_current_import)
            raise

    async def read_upload(request: Request, filename: str):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
            raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
        return await run_in_threadpool(lab.import_file, filename[:300], bytes(data))

    @app.get("/api/import/current", dependencies=[Depends(require_login)])
    def current_import():
        return lab.current_import()

    @app.post("/api/import/{import_id}/confirm-address", dependencies=[Depends(require_login)])
    def confirm_address(import_id: int, body: ConfirmBody):
        return lab.confirm_address(import_id, body.address, body.confirmed)

    @app.post("/api/import/{import_id}/verify", dependencies=[Depends(require_login)])
    def run_verify(import_id: int):
        return lab.verify(import_id)

    @app.get("/api/import/{import_id}/verify", dependencies=[Depends(require_login)])
    def latest_verify(import_id: int):
        return lab.latest_verify(import_id)

    # ---------------------------------------------------------------- tests and Evidence Lab (all need login)
    # There is no route here that accepts software, or any file: bodies are the small JSON objects above.

    @app.get("/api/import/{import_id}/plan", dependencies=[Depends(require_login)])
    def get_plan_for_import(import_id: int):
        return lab.get_plan_for_import(import_id)

    @app.post("/api/import/{import_id}/plan", dependencies=[Depends(require_login)])
    def ensure_plan(import_id: int):
        return lab.ensure_plan(import_id)

    @app.get("/api/plans/{plan_id}", dependencies=[Depends(require_login)])
    def get_plan(plan_id: int):
        return lab.plan_view(plan_id)

    @app.post("/api/plans/{plan_id}/order", dependencies=[Depends(require_login)])
    def reorder(plan_id: int, body: OrderBody):
        return lab.reorder(plan_id, list(body.order))

    @app.post("/api/plans/{plan_id}/tests", dependencies=[Depends(require_login)])
    def add_test(plan_id: int, body: AddTestBody):
        return lab.add_test(plan_id, body.catalog_id)

    @app.post("/api/plans/{plan_id}/tests/{item_id}/remove", dependencies=[Depends(require_login)])
    def remove_test(plan_id: int, item_id: int):
        return lab.remove_test(plan_id, item_id)

    @app.post("/api/plans/{plan_id}/tests/{item_id}/run", dependencies=[Depends(require_login)])
    def run_test(plan_id: int, item_id: int):
        return lab.run_test(plan_id, item_id)

    @app.post("/api/plans/{plan_id}/run-all", dependencies=[Depends(require_login)])
    def run_all(plan_id: int):
        return lab.run_all(plan_id)

    @app.get("/api/plans/{plan_id}/lab", dependencies=[Depends(require_login)])
    def lab_view(plan_id: int):
        return lab.lab_view(plan_id)

    @app.post("/api/runs/{run_id}/mark-reviewed", dependencies=[Depends(require_login)])
    def mark_reviewed(run_id: int):
        return lab.mark_reviewed(run_id)

    @app.post("/api/runs/{run_id}/dig-deeper", dependencies=[Depends(require_login)])
    def dig_deeper(run_id: int):
        return lab.dig_deeper(run_id)

    @app.post("/api/plans/{plan_id}/retest", dependencies=[Depends(require_login)])
    def retest(plan_id: int, body: RetestBody):
        return lab.start_retest(plan_id, body.version)

    @app.post("/api/plans/{plan_id}/evidence", dependencies=[Depends(require_login)])
    def export_evidence(plan_id: int):
        return lab.export_evidence(plan_id)

    @app.get("/api/evidence/{export_id}/{which}", dependencies=[Depends(require_login)])
    def evidence_file(export_id: int, which: str):
        filename, data, media_type = lab.evidence_file(export_id, which)
        # Always a download, never a page of this app: the report is opened from disk, where it can reach nothing.
        return Response(content=data, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "Cache-Control": "no-store"})

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
