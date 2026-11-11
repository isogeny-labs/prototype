"""The job runner inside the backend: an async worker pool with a maximum number of tests at once.

One asyncio loop runs in its own thread. A job waits for a free place (status "waiting"), then its work
runs on a worker thread (status "running"), then it is "done". Job state lives in memory only; what a job
found is written to the database by the work itself (a run record and a review).

ExclusiveGate lets a timing measurement have the computer to itself: ordinary test work holds the gate
"shared", a measurement holds it "exclusive". A waiting measurement stops new shared work from starting,
so it is never kept waiting for ever."""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ExclusiveGate:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._shared = 0
        self._exclusive = False
        self._exclusive_waiting = 0
        self.shared_seen_during_exclusive = 0  # stays 0 if the gate works (checked by tests)

    @contextmanager
    def shared(self):
        with self._cond:
            while self._exclusive or self._exclusive_waiting:
                self._cond.wait()
            self._shared += 1
        try:
            yield
        finally:
            with self._cond:
                self._shared -= 1
                self._cond.notify_all()

    @contextmanager
    def exclusive(self):
        with self._cond:
            self._exclusive_waiting += 1
            try:
                while self._exclusive or self._shared:
                    self._cond.wait()
            finally:
                self._exclusive_waiting -= 1
            self._exclusive = True
        try:
            yield
        finally:
            with self._cond:
                self.shared_seen_during_exclusive += self._shared
                self._exclusive = False
                self._cond.notify_all()

    @property
    def shared_now(self) -> int:
        return self._shared

    @property
    def exclusive_now(self) -> bool:
        return self._exclusive


class Job:
    def __init__(self, key: tuple, group: object = None):
        self.key = key
        self.group = group
        self.status = "waiting"            # waiting | running | done
        self.progress_text: str | None = None
        self.progress_percent: int | None = None
        self.queued_at = _now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.logs: list[str] = []
        self.run_id: int | None = None
        self.error: str | None = None      # only if the work itself raised (it should not)

    def progress(self, text: str, percent: int | None = None) -> None:
        self.progress_text, self.progress_percent = text, percent

    def log(self, text: str) -> None:
        if len(self.logs) < 500:
            self.logs.append(f"{_now()} {str(text)[:500]}")


class JobRunner:
    def __init__(self, max_parallel: int = 4):
        self.max_parallel = max(1, int(max_parallel))
        self.gate = ExclusiveGate()
        self._jobs: dict[tuple, Job] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pool: ThreadPoolExecutor | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self.running_now = 0
        self.most_at_once = 0              # the largest number of jobs that ran at the same moment

    # ---------------------------------------------------------------- start / stop

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            ready = threading.Event()

            def loop_main() -> None:
                loop = self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._semaphore = asyncio.Semaphore(self.max_parallel)
                ready.set()
                loop.run_forever()
                loop.close()

            self._pool = ThreadPoolExecutor(max_workers=self.max_parallel, thread_name_prefix="evidence-lab-job")
            self._thread = threading.Thread(target=loop_main, name="evidence-lab-jobs", daemon=True)
            self._thread.start()
            ready.wait(5)

    def stop(self) -> None:
        with self._lock:
            loop, thread, pool = self._loop, self._thread, self._pool
            self._loop = self._thread = self._pool = None
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    # ---------------------------------------------------------------- jobs

    def submit(self, key: tuple, fn: Callable[[Job], None], group: object = None) -> Job:
        """Queue one job. Refuses (ValueError) a second live job for the same key."""
        self.start()
        with self._lock:
            old = self._jobs.get(key)
            if old is not None and old.status != "done":
                raise ValueError("this test is already waiting or running")
            job = Job(key, group)
            self._jobs[key] = job
            loop = self._loop
        asyncio.run_coroutine_threadsafe(self._run(job, fn), loop)
        return job

    async def _run(self, job: Job, fn: Callable[[Job], None]) -> None:
        loop = asyncio.get_running_loop()
        try:
            async with self._semaphore:
                job.status, job.started_at = "running", _now()
                self.running_now += 1
                self.most_at_once = max(self.most_at_once, self.running_now)
                try:
                    await loop.run_in_executor(self._pool, fn, job)
                finally:
                    self.running_now -= 1
        except BaseException as exc:  # the work is written never to raise; if it does, the job still ends
            job.error = exc.__class__.__name__
        finally:
            job.finished_at = _now()
            job.status = "done"

    def get(self, key: tuple) -> Job | None:
        with self._lock:
            return self._jobs.get(key)

    def live(self, group: object) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.group == group and j.status != "done"]

    def busy(self, group: object) -> bool:
        return bool(self.live(group))

    def wait_idle(self, timeout: float, group: object = None) -> bool:
        """Wait until no job is waiting or running (for one plan, or at all). False if the time ran out."""
        import time
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                live = [j for j in self._jobs.values() if j.status != "done" and (group is None or j.group == group)]
            if not live:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
