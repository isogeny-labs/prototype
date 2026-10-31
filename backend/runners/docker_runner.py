"""Container runner (OPTIONAL). Runs the same fixture scripts inside a Docker container.

Status: implemented, NOT validated in the development environment used to build this MVP (no Docker
daemon was available). It is registered but reports `available=False` when the daemon is unreachable,
and the UI labels it accordingly. Do not describe this as a tested capability until a run has succeeded.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .base import Runner, RunRequest, RunResult, parse_output, validate_fixture_output, register

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
IMAGE = os.environ.get("IEL_DOCKER_IMAGE", "python:3.13-slim")
ALLOWED_FIXTURES = {"firmware_signing", "app_service_crypto", "toy_factoring"}


class DockerFixtureRunner(Runner):
    kind = "docker_fixture"
    version = "0.1.0"
    provenance = "measured"
    implemented = True
    tested_here = False
    description = ("Optional: runs the fixture in a Docker container (--network none, memory/cpu/pids limits, "
                   "read-only fixture mount). Requires a reachable Docker daemon; untested in the build environment.")

    def available(self):
        if not shutil.which("docker"):
            return False, "docker CLI not installed"
        try:
            r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=10)
            if r.returncode != 0:
                return False, "docker daemon unreachable"
        except Exception as e:
            return False, f"docker check failed: {type(e).__name__}"
        return True, ""

    def run(self, req: RunRequest) -> RunResult:
        ok, why = self.available()
        if not ok:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, failures=[f"runner unavailable: {why}"])
        if req.fixture not in ALLOWED_FIXTURES:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, failures=["fixture not allowlisted"])
        mem_mb = int(req.limits.get("memory_mb", 1024))
        timeout = int(req.limits.get("timeout_s", 300))
        cmd = ["docker", "run", "--rm", "-i", "--network", "none", f"--memory={mem_mb}m", "--cpus=1",
               "--pids-limit=64", "--read-only", "--tmpfs", "/tmp", "-v", f"{FIXTURE_DIR}:/fixtures:ro",
               IMAGE, "sh", "-c",
               "pip install -q cryptography dilithium-py >/dev/null 2>&1; python -I /fixtures/%s.py" % req.fixture]
        params = json.dumps(req.params, sort_keys=True)
        commands = [{"argv": cmd, "stdin_sha256": hashlib.sha256(params.encode()).hexdigest(), "image": IMAGE}]
        try:
            proc = subprocess.run(cmd, input=params.encode(), capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, failures=["container timeout"])
        try:
            data = parse_output(proc.stdout)
        except ValueError as e:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, raw_output=proc.stdout + proc.stderr,
                             failures=[str(e)])
        problems = validate_fixture_output(data)
        image_digest = subprocess.run(["docker", "inspect", "--format", "{{index .RepoDigests 0}}", IMAGE],
                                      capture_output=True, text=True).stdout.strip()
        return RunResult(
            status="completed" if data.get("status") == "completed" and not problems else "failed",
            provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
            fixture_version=data.get("fixture_version", ""),
            environment={**data.get("environment", {}), "container_image": IMAGE, "image_digest": image_digest,
                         "isolation": "docker --network none"},
            commands=commands, repeat_count=int(data.get("repeat_count", 0)), metrics=data.get("metrics", {}),
            metric_definitions=data.get("metric_definitions", {}), scenarios=data.get("scenarios", []),
            raw_output=proc.stdout, failures=list(data.get("failures", [])) + problems,
            limitations=data.get("limitations", []))


register(DockerFixtureRunner())
