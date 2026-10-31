"""Process-isolated local fixture runner.

Runs a fixture script in a fresh Python subprocess with:
* a wall-clock timeout, CPU-seconds and address-space rlimits (POSIX),
* isolated interpreter flags (-I: ignore env vars and user site, don't add script dir to sys.path cwd),
* an empty environment (no credentials leak into the fixture),
* stdin = JSON params, stdout = JSON result.
This is the supported runner for the MVP. It provides process isolation, not a container boundary.
"""
from __future__ import annotations

import hashlib
import os
import resource
import subprocess
import sys
from pathlib import Path

from .base import Runner, RunRequest, RunResult, parse_output, validate_fixture_output, register
import json

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
ALLOWED_FIXTURES = {"firmware_signing", "app_service_crypto", "toy_factoring"}


def _limits(mem_mb: int, cpu_s: int):
    def pre():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass
    return pre


class LocalFixtureRunner(Runner):
    kind = "local_fixture"
    version = "1.0.0"
    provenance = "measured"
    description = ("Supported runner: executes an allowlisted fixture in an isolated Python subprocess "
                   "with time/CPU/memory limits and an empty environment. Process isolation, not a container.")

    def run(self, req: RunRequest) -> RunResult:
        if req.fixture not in ALLOWED_FIXTURES:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, failures=[f"fixture '{req.fixture}' is not allowlisted"])
        script = FIXTURE_DIR / f"{req.fixture}.py"
        timeout = int(req.limits.get("timeout_s", 300))
        mem_mb = int(req.limits.get("memory_mb", 1024))
        cpu_s = int(req.limits.get("cpu_s", 240))
        cmd = [sys.executable, "-I", str(script)]
        params = json.dumps(req.params, sort_keys=True)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
        # the fixture must be able to import its (pip-installed) dependencies: keep site-packages visible
        if "PYTHONPATH" in os.environ:
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        commands = [{"argv": cmd, "stdin_sha256": hashlib.sha256(params.encode()).hexdigest(),
                     "limits": {"timeout_s": timeout, "memory_mb": mem_mb, "cpu_s": cpu_s}}]
        try:
            proc = subprocess.run(cmd, input=params.encode(), capture_output=True, timeout=timeout, env=env,
                                  cwd=str(FIXTURE_DIR), preexec_fn=_limits(mem_mb, cpu_s))
        except subprocess.TimeoutExpired:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands,
                             failures=[f"fixture exceeded wall-clock timeout of {timeout}s"])
        raw = proc.stdout
        stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        try:
            data = parse_output(raw)
        except ValueError as e:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, raw_output=raw + proc.stderr,
                             failures=[str(e), f"exit={proc.returncode}", stderr_tail])
        problems = validate_fixture_output(data)
        failures = list(data.get("failures", [])) + problems
        status = "completed" if data.get("status") == "completed" and not problems else "failed"
        return RunResult(
            status=status, provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
            fixture_version=data.get("fixture_version", ""), environment={**data.get("environment", {}),
                                                                           "runner_host": os.uname().nodename if hasattr(os, "uname") else "unknown",
                                                                           "isolation": "subprocess+rlimit"},
            commands=commands, repeat_count=int(data.get("repeat_count", 0)), metrics=data.get("metrics", {}),
            metric_definitions=data.get("metric_definitions", {}), scenarios=data.get("scenarios", []),
            raw_output=raw, failures=failures, limitations=data.get("limitations", []),
            extra={k: data[k] for k in ("probability_model", "label", "scheme", "library", "profile", "purpose") if k in data},
        )


register(LocalFixtureRunner())
