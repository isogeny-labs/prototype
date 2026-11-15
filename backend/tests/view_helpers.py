"""Small helpers for the tests that read the screens' views, and `problems`, which says where a view does not have
exactly the shape the screens receive. The shapes are the ones in app/web/models.py, the same ones the frontend's
types are generated from (phase 4c+; before, this file held a hand-written copy of the frontend's types)."""
from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError


def problems(value, shape: type[BaseModel], path: str = "view") -> list[str]:
    """Every place where `value` does not fit `shape` exactly, read as the screens read it (as JSON, strictly: no key
    too many or too few, no number for a word, no true or false for a number). An empty list means it fits."""
    try:
        shape.model_validate_json(json.dumps(value), strict=True)
    except ValidationError as exc:
        return [f"{path}.{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors(include_url=False)]
    return []


def texts(value) -> list[str]:
    """Every piece of text in a view, in order (the keys are not included): what a test of the wording reads."""
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in texts(item)]
    return [value] if isinstance(value, str) else []


def plain(rich: list[dict]) -> str:
    """A rich text as one plain sentence (a time is left as its ISO text, the Demo data label as its words)."""
    return "".join(part["v"] for part in rich)


def fix(view: dict, fix_id: str) -> dict:
    return next(f for f in view["fixes"] if f["id"] == fix_id)


def section(detail: dict, key: str) -> dict:
    return next(s for s in detail["sections"] if s["key"] == key)
