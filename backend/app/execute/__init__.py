"""Running a locked test. Everything in this package returns RAW outcomes only: what was asked, what
came back, how long it took. No result label is decided here; that is the reviewer's job (reviewer.py).

Expected failures never raise: they come back as raw["problem"] = {"code", "text"}."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import runner as runner_module


@dataclass
class RunContext:
    settings: object
    mode: runner_module.ModeInfo
    runner: runner_module.ComponentRunner
    gate: object                                   # jobs.ExclusiveGate
    progress: Callable[[str, int | None], None]
    log: Callable[[str], None]
    address_check: Callable[[str], object]         # address text -> verify.AddressCheck (or None if not in the import)
    component: tuple[str, str] | None              # (name, version) to run; None if the plan has no signing component
    baseline_version: str | None = None            # set on a retest: the version the first results were for
    timing: dict | None = None                     # filled by begin(): when the work itself started

    def begin(self) -> None:
        """The test's own work starts now (any wait for the measuring gate is over)."""
        import time
        from datetime import datetime, timezone
        self.timing = {"started_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                       "t0": time.perf_counter()}


def problem(code: str, text: str) -> dict:
    return {"problem": {"code": code, "text": str(text)[:500]}}


def batch_problem(result: runner_module.BatchResult) -> dict:
    """Why the harness run gave nothing usable, as a problem code."""
    if result.problem == runner_module.PROBLEM_TIMEOUT:
        code = "timeout"
    elif result.problem == runner_module.PROBLEM_ISOLATED:
        code = "isolated_unavailable"
    else:
        code = "harness_error"
    out = problem(code, result.problem or "the test harness gave no result")
    out["batch"] = batch_info(result)
    return out


def batch_info(result: runner_module.BatchResult) -> dict:
    return {"command": result.command, "duration_ms": result.duration_ms, "mode": result.mode,
            "started_at": result.started_at, "stderr_tail": result.stderr_tail}


EXCLUSIVE_KINDS = ("speed_size", "mldsa_compare")   # these take the gate exclusively themselves, while they measure


def execute(spec: dict, ctx: RunContext) -> dict:
    from . import pq, server, signing, speed
    table = {"tls_versions": server.run_tls_versions, "certificate": server.run_certificate,
             "official_vectors": signing.run_official_vectors, "bad_signatures": signing.run_bad_signatures,
             "speed_size": speed.run_speed_size, "pq_readiness": pq.run_pq_readiness, "mldsa_compare": speed.run_mldsa_compare}
    run = table.get(spec.get("kind"))
    if run is None:
        return problem("harness_error", "This kind of test is not known to this version.")
    try:
        if spec["kind"] in EXCLUSIVE_KINDS:
            return run(spec, ctx)
        ctx.progress("waiting for a timing measurement to finish", None)
        with ctx.gate.shared():
            ctx.begin()
            return run(spec, ctx)
    except Exception as exc:  # never let a surprise lose the run: it is recorded, and reviewed as "couldn't run"
        ctx.log(f"the test stopped unexpectedly ({exc.__class__.__name__})")
        return problem("harness_error", f"The test stopped unexpectedly ({exc.__class__.__name__}).")
