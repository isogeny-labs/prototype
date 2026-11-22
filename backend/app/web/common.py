"""What the route modules share: the request bodies, the fix-id check, downloads and the error answer."""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from app import auth
from app.lab.hub import NotFound


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
    component: str | None = Field(default=None, max_length=100)   # phase 4c: which program to swap, when the file names several


class MigrationSettingBody(BaseModel):
    system: StrictStr = Field(max_length=600)
    field: StrictStr = Field(max_length=16)
    value: StrictStr = Field(max_length=16)


class MigrationChoiceBody(BaseModel):
    system: StrictStr = Field(max_length=600)
    option: StrictStr = Field(max_length=16)
    reason: StrictStr = Field(default="", max_length=2000)
    review_date: StrictStr | None = Field(default=None, max_length=10)


class DependencyTieBody(BaseModel):
    top: StrictStr = Field(max_length=600)
    system: StrictStr = Field(default="", max_length=600)    # "" is "None of these"


class DependencyMeasureBody(BaseModel):
    row: StrictStr | None = Field(default=None, max_length=20)   # one library, or every one that can be measured


class ChangeBody(BaseModel):
    change: StrictStr = Field(max_length=700)


class AskApprovalBody(BaseModel):
    change: StrictStr = Field(max_length=700)
    reviewers: list[Annotated[StrictStr, Field(max_length=16)]] = Field(max_length=8)


class ApproveChangeBody(BaseModel):
    change: StrictStr = Field(max_length=700)
    reviewer: StrictStr = Field(max_length=16)


class PullRequestBody(BaseModel):
    # The picked reviewers, as ids from the fixed list (Lab checks each one against it).
    reviewers: list[Annotated[StrictStr, Field(max_length=16)]] = Field(max_length=8)


class ApproveBody(BaseModel):
    reviewer: StrictStr = Field(max_length=16)


FIX_ID = re.compile(r"[a-z0-9-]{1,48}")


def known_shape(fix_id: str) -> str:
    """A fix id as the app itself makes them, or 404. Whether the plan has that fix is checked in Lab."""
    if not FIX_ID.fullmatch(fix_id):
        raise NotFound("That fix does not exist.")
    return fix_id


def download(filename: str, data: bytes, media_type: str) -> Response:
    """A file to save, never a page of this app: a saved report or patch is opened from disk, where it can reach nothing."""
    return Response(content=data, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "Cache-Control": "no-store"})


def shows(model: type[BaseModel]) -> dict:
    """The shape of a route's answer, for the API description only (see app/web/models.py). It does not check or
    change the answer: the route returns exactly what it returned before."""
    return {200: {"model": model}}


def error_response(status: int, message: str, line: int | None = None, field: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "line": line, "field": field}})
