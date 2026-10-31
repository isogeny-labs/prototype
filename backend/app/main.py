"""Isogeny Evidence Lab — FastAPI application entry point."""
from __future__ import annotations

import logging
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from .config import FRONTEND_DIR, WORKER_MODE  # noqa: E402
from .db import init_db  # noqa: E402
from . import jobs, services  # noqa: E402,F401
from .routers import auth_routes, projects, implementations, experiments, recommendations, research, attack, sandbox, misc  # noqa: E402


class RedactFilter(logging.Filter):
    """Redact bearer tokens, passwords and API keys from any log line."""
    PATTERNS = [re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]+"), re.compile(r"(?i)(password[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+"),
                re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+")]

    def filter(self, record):
        msg = str(record.getMessage())
        for p in self.PATTERNS:
            msg = p.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", msg)
        record.msg, record.args = msg, ()
        return True


for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "iel", ""):
    logging.getLogger(name).addFilter(RedactFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .seed import ensure_seed
    ensure_seed()
    if WORKER_MODE == "thread":
        jobs.start_worker_thread()
    yield
    jobs.stop_worker_thread()


app = FastAPI(title="Isogeny Evidence Lab", version="0.1.0", lifespan=lifespan)
for r in (auth_routes, projects, implementations, experiments, recommendations, research, attack, sandbox, misc):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "isogeny-evidence-lab", "version": app.version}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
