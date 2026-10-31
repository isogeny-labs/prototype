"""Standalone worker process: `cd backend && python -m app.worker`."""
import logging
import time
from .db import init_db
from . import jobs
from . import services  # noqa: F401  (registers job handlers)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("worker started")
    while True:
        if jobs.process_pending(10) == 0:
            time.sleep(1.0)
