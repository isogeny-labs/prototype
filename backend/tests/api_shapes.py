"""Checks every JSON answer the tests get from the app against the shape its route declares (phase 4c+).

The shapes are written once, in app/web/models.py; each route names its shape with `responses=shows(...)`, and the
frontend's types are generated from the same shapes. So while any test talks to the app through `TestClient`, a
successful JSON answer that does not fit its route's shape exactly (a key too many or too few, a wrong kind of value)
fails that test. This replaces the hand-written copy of the frontend's types the tests used to keep.

Enabled for every test by tests/conftest.py. Options (environment variables):
  API_SHAPES_REPORT=1   at the end, list the routes that were checked and those no test reached
  API_SHAPES_COLLECT=1  record every mismatch and list it at the end instead of failing the test
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

# The routes checked so far, and every route that declares a shape: (method, path template).
CHECKED: set[tuple[str, str]] = set()
DECLARED: set[tuple[str, str]] = set()
# Every distinct mismatch seen with API_SHAPES_COLLECT=1: (route, place in the answer, error kind) -> example.
ERRORS: dict[tuple[str, str, str], str] = {}

_TABLES: dict[int, list] = {}


def _api_routes(routes):
    """Every APIRoute of the app, also those inside the included routers (FastAPI keeps those as groups)."""
    for route in routes:
        inner = getattr(getattr(route, "original_router", None), "routes", None)
        if inner is not None:
            yield from _api_routes(inner)
        elif isinstance(route, APIRoute):
            yield route


def _table(app) -> list:
    if id(app) not in _TABLES:
        rows = []
        for route in _api_routes(app.routes):
            model = (route.responses or {}).get(200, {}).get("model")
            if model is None:
                continue
            pattern = re.compile("^" + re.sub(r"\\\{[^/}]+\\\}", "[^/]+", re.escape(route.path)) + "$")
            for method in route.methods:
                rows.append((method, route.path, pattern, model))
                DECLARED.add((method, route.path))
        _TABLES[id(app)] = rows
    return _TABLES[id(app)]


def check_response(app, method: str, url: str, response) -> None:
    if not 200 <= response.status_code < 300 or "json" not in response.headers.get("content-type", ""):
        return
    path = urlsplit(str(url)).path
    found = next(((t, m) for meth, t, p, m in _table(app) if meth == method.upper() and p.match(path)), None)
    if found is None:
        return
    template, model = found
    try:
        model.model_validate_json(response.text, strict=True)  # as the screens read it: JSON, exactly
    except ValidationError as exc:
        if os.environ.get("API_SHAPES_COLLECT"):
            for err in exc.errors(include_url=False):
                where = ".".join("*" if isinstance(p, int) else str(p) for p in err["loc"])
                ERRORS.setdefault((f"{method.upper()} {template}", where, err["type"]), repr(err.get("input"))[:100])
            return
        raise AssertionError(
            f"{method.upper()} {template} answered something its shape {model.__name__} does not "
            f"accept:\n{exc.errors(include_url=False)}"
        ) from None
    CHECKED.add((method.upper(), template))


@pytest.fixture(autouse=True)
def _check_api_shapes(monkeypatch):
    original = TestClient.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        check_response(self.app, method, url, response)
        return response

    monkeypatch.setattr(TestClient, "request", request)
    yield


def pytest_sessionfinish(session, exitstatus):
    if not os.environ.get("API_SHAPES_REPORT"):
        return
    print("\n--- API shapes ---")
    print("checked:", *sorted(f"{m} {t}" for m, t in CHECKED), sep="\n  ")
    print("never reached by a test:", *sorted(f"{m} {t}" for m, t in DECLARED - CHECKED), sep="\n  ")
    if ERRORS:
        print("mismatches:")
        for (route, where, kind), example in sorted(ERRORS.items()):
            print(f"  {route} | {where} | {kind} | input={example}")
