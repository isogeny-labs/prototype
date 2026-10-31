"""Database-backed background job queue with an in-process worker thread.

Jobs: run_fixture (execute a runner and persist an append-only Run), research_review (auto-researcher).
The worker can also run in a separate process: `python -m app.worker`. Tests call `process_pending()`.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Job, utcnow

log = logging.getLogger("iel.jobs")
_HANDLERS = {}
_stop = threading.Event()


def handler(kind):
    def deco(fn):
        _HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(db: Session, kind: str, payload: dict) -> Job:
    job = Job(kind=kind, payload=payload)
    db.add(job)
    db.flush()
    return job


def _claim(db: Session) -> Job | None:
    job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1))
    if job:
        job.status = "running"
        job.attempts += 1
        job.started_at = utcnow()
        db.commit()
    return job


def run_job(db: Session, job: Job):
    fn = _HANDLERS.get(job.kind)
    try:
        if not fn:
            raise RuntimeError(f"no handler for job kind {job.kind}")
        job.result = fn(db, job.payload) or {}
        job.status = "done"
    except Exception as e:  # noqa: BLE001
        db.rollback()
        job = db.get(Job, job.id)
        job.status = "failed"
        job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        log.error("job %s failed: %s", job.id, type(e).__name__)
    job.finished_at = utcnow()
    db.commit()


def process_pending(max_jobs: int = 100) -> int:
    """Synchronously process queued jobs (used by tests and the external worker)."""
    n = 0
    with SessionLocal() as db:
        while n < max_jobs:
            job = _claim(db)
            if not job:
                break
            run_job(db, job)
            n += 1
    return n


def _loop(poll_s: float):
    while not _stop.is_set():
        try:
            if process_pending(10) == 0:
                _stop.wait(poll_s)
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
            _stop.wait(poll_s)


_thread: threading.Thread | None = None


def start_worker_thread(poll_s: float = 1.0):
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(poll_s,), name="iel-worker", daemon=True)
    _thread.start()


def stop_worker_thread():
    _stop.set()
