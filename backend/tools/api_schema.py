"""Writes the backend's API description to frontend/src/api-schema.json: every route, and the shape of the data each
screen receives (the shapes live in app/web/models.py; each route names its shape in `responses=`). The frontend's
types are generated from this file (cd frontend && npm run gen:api), so the shapes are written once.

    .venv/bin/python tools/api_schema.py           write it
    .venv/bin/python tools/api_schema.py --check   only compare; exit code 1 if it is out of date

Development-only. The running app does not serve this description (FastAPI's openapi_url is off) and the routes do
not use the shapes at runtime: they return exactly the data they returned before.
"""
from __future__ import annotations

import json
import sys
import tempfile
import typing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import TypeAdapter  # noqa: E402

from app.config import REPO_ROOT, Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.web import models  # noqa: E402

OUT = REPO_ROOT / "frontend" / "src" / "api-schema.json"
REF = "#/components/schemas/{model}"


def named_aliases() -> dict[str, object]:
    """The shapes that are a plain name for a list of words, a choice of shapes or a list (ClaimKind, EvidenceBlock,
    RichText, ...).
    A field uses them written out; they are listed by name too, so the screens can name them."""
    out = {}
    for name, value in vars(models).items():
        if name.startswith("_"):
            continue
        origin = typing.get_origin(value)
        if origin is typing.Annotated:
            origin = typing.get_origin(typing.get_args(value)[0])
        if origin in (typing.Literal, typing.Union, list):
            out[name] = value
    return out


def description() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp) / "data", demo_tls_port=1, force_mode="demo"))
        schema = app.openapi()
    shapes = schema.setdefault("components", {}).setdefault("schemas", {})
    # FastAPI would describe a refused request as its own default error shape; this app answers every refusal with
    # {"error": {"message", "line", "field"}} instead (app/main.py), so that default would be wrong here.
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            operation.get("responses", {}).pop("422", None)
    for name in ("HTTPValidationError", "ValidationError"):
        shapes.pop(name, None)
    for name, alias in named_aliases().items():
        adapter = TypeAdapter(alias)
        one = adapter.json_schema(ref_template=REF, mode="serialization")
        for extra_name, extra in one.pop("$defs", {}).items():
            shapes.setdefault(extra_name, extra)
        one["title"] = name
        shapes.setdefault(name, one)
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = description()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(REPO_ROOT)} is out of date. Run: .venv/bin/python tools/api_schema.py, "
                  "then in frontend/: npm run gen:api")
            return 1
        print(f"{OUT.relative_to(REPO_ROOT)} is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO_ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
