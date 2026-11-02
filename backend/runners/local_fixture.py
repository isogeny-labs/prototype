"""Platform sandbox runner (process-isolated).

Runs an allowlisted fixture in a fresh Python subprocess with:
* a new network namespace (`unshare -rn`) when the host allows it, otherwise an interpreter-level socket block;
  the isolation actually used is recorded on the run,
* wall-clock timeout, CPU-seconds, address-space and process-count rlimits,
* `python -I` (isolated interpreter), an empty environment, a read-only staging directory for the source snapshot,
* stdin = JSON params, stdout = JSON result. Dependencies come from the platform's pinned environment only; nothing
  is installed at run time and networking is never enabled for a run.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Runner, RunRequest, RunResult, parse_output, validate_fixture_output, register

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
ALLOWED_FIXTURES = {"signature_library", "malformed_input_sweep", "toy_factoring"}
NET_BLOCK = ("import socket\n"
             "def _blocked(*a, **k): raise OSError('network disabled in sandbox')\n"
             "socket.socket = _blocked; socket.create_connection = _blocked; socket.getaddrinfo = _blocked\n"
             "import runpy, sys; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')\n")


def _limits(mem_mb: int, cpu_s: int):
    def pre():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass
    return pre


def _unshare_available() -> bool:
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


class LocalFixtureRunner(Runner):
    kind = "platform_sandbox"
    version = "2.0.0"
    provenance = "measured"
    fixtures = tuple(sorted(ALLOWED_FIXTURES))
    description = ("Supported: executes an allowlisted test fixture in an isolated subprocess (network namespace or socket block, "
                   "CPU/memory/process rlimits, empty environment, read-only snapshot). Process isolation, not a container.")

    def run(self, req: RunRequest) -> RunResult:
        if req.fixture not in ALLOWED_FIXTURES:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                             failures=[f"fixture '{req.fixture}' is not allowlisted"])
        script = FIXTURE_DIR / f"{req.fixture}.py"
        timeout = int(req.limits.get("timeout_s", 300))
        mem_mb = int(req.limits.get("memory_mb", 1024))
        cpu_s = int(req.limits.get("cpu_s", 240))
        params = dict(req.params)
        stage = None
        try:
            snapshot = req.params.get("source_snapshot")  # {"files": {name: bytes}} staged read-only
            if snapshot:
                stage = Path(tempfile.mkdtemp(prefix="iel-snap-"))
                for name, data in snapshot["files"].items():
                    dest = stage / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data if isinstance(data, bytes) else bytes(data))
                    dest.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                params["adapter"] = {"kind": "module", "path": str(stage / snapshot.get("entry", "adapter.py"))}
                params.pop("source_snapshot", None)
            use_ns = _unshare_available()
            cmd = (["unshare", "-rn"] if use_ns else []) + [sys.executable, "-I"]
            cmd += [str(script)] if use_ns else ["-c", NET_BLOCK, str(script)]
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
            if "PYTHONPATH" in os.environ:
                env["PYTHONPATH"] = os.environ["PYTHONPATH"]
            stdin = json.dumps(params, sort_keys=True)
            isolation = ("unshare(net)+rlimit+python-I" if use_ns else "socket-block+rlimit+python-I")
            commands = [{"argv": [c if c != NET_BLOCK else "<network-block preamble>" for c in cmd], "stdin_sha256": hashlib.sha256(stdin.encode()).hexdigest(),
                         "limits": {"timeout_s": timeout, "memory_mb": mem_mb, "cpu_s": cpu_s}, "isolation": isolation}]
            try:
                proc = subprocess.run(cmd, input=stdin.encode(), capture_output=True, timeout=timeout, env=env, cwd=str(FIXTURE_DIR),
                                      preexec_fn=_limits(mem_mb, cpu_s))
            except subprocess.TimeoutExpired:
                return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                                 commands=commands, failures=[f"fixture exceeded wall-clock timeout of {timeout}s"])
            raw, stderr_tail = proc.stdout, proc.stderr.decode("utf-8", errors="replace")[-2000:]
            try:
                data = parse_output(raw)
            except ValueError as e:
                return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                                 commands=commands, raw_output=raw + proc.stderr, failures=[str(e), f"exit={proc.returncode}", stderr_tail])
            problems = validate_fixture_output(data)
            failures = list(data.get("failures", [])) + problems
            return RunResult(
                status="completed" if data.get("status") == "completed" and not problems else "failed",
                provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                fixture_version=data.get("fixture_version", ""),
                environment={**data.get("environment", {}), "runner_host": os.uname().nodename, "isolation": isolation, "network": "disabled"},
                commands=commands, repeat_count=int(data.get("repeat_count", 0)), metrics=data.get("metrics", {}),
                metric_definitions=data.get("metric_definitions", {}), scenarios=data.get("scenarios", []), raw_output=raw,
                failures=failures, exclusions=data.get("exclusions", []), limitations=data.get("limitations", []),
                extra={k: data[k] for k in ("probability_model", "adapter", "test_id", "parameters") if k in data})
        finally:
            if stage:
                shutil.rmtree(stage, ignore_errors=True)


register(LocalFixtureRunner())
