"""Isolated runner interface.

A Runner executes one fixture (or ingests one externally produced result) and returns a RunResult.
Runners never touch the database; the job worker persists results as append-only Run records.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

RESULT_SCHEMA_VERSION = "1"
REQUIRED_RESULT_KEYS = {"fixture", "fixture_version", "status", "metrics", "scenarios"}
EXECUTION_MODES = ("platform_sandbox", "customer_runner", "imported_results")


class RunnerUnavailable(RuntimeError):
    pass


@dataclass
class RunRequest:
    fixture: str                      # fixture id, e.g. firmware_signing
    params: dict[str, Any]            # fixture parameters (JSON-serialisable)
    implementation: dict[str, Any]    # snapshot of the implementation record (for provenance)
    experiment: dict[str, Any]        # snapshot of the experiment definition
    limits: dict[str, Any] = field(default_factory=dict)  # timeout_s, memory_mb, cpu_s


@dataclass
class RunResult:
    status: str                        # completed | failed
    provenance: str                    # measured | imported | illustrative
    runner_kind: str
    runner_version: str
    fixture_version: str = ""
    environment: dict = field(default_factory=dict)
    commands: list = field(default_factory=list)
    repeat_count: int = 0
    metrics: dict = field(default_factory=dict)
    metric_definitions: dict = field(default_factory=dict)
    scenarios: list = field(default_factory=list)
    raw_output: bytes = b""
    failures: list = field(default_factory=list)
    exclusions: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def validate_fixture_output(data: dict) -> list[str]:
    """Return a list of schema problems (empty when valid)."""
    problems = []
    if not isinstance(data, dict):
        return ["output is not a JSON object"]
    missing = REQUIRED_RESULT_KEYS - set(data)
    if missing and data.get("status") != "failed":
        problems.append(f"missing keys: {sorted(missing)}")
    if data.get("status") not in ("completed", "failed"):
        problems.append("status must be completed|failed")
    if "metrics" in data and not isinstance(data["metrics"], dict):
        problems.append("metrics must be an object")
    for s in data.get("scenarios", []) or []:
        if not {"id", "expected", "observed", "pass"} <= set(s):
            problems.append(f"scenario missing keys: {s}")
            break
    return problems


class Runner:
    kind: str = "abstract"
    version: str = "0"
    provenance: str = "measured"
    description: str = ""
    implemented: bool = True
    tested_here: bool = True

    def available(self) -> tuple[bool, str]:
        return True, ""

    def run(self, req: RunRequest) -> RunResult:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        ok, why = self.available()
        return {"kind": self.kind, "version": self.version, "provenance": self.provenance,
                "description": self.description, "available": ok, "unavailable_reason": why,
                "implemented": self.implemented, "tested_in_this_environment": self.tested_here}


_REGISTRY: dict[str, Runner] = {}


def register(runner: Runner):
    _REGISTRY[runner.kind] = runner
    return runner


def get_runner(kind: str) -> Runner:
    if kind not in _REGISTRY:
        raise RunnerUnavailable(f"no runner registered for kind '{kind}'")
    return _REGISTRY[kind]


def list_runners() -> list[dict]:
    return [r.describe() for r in _REGISTRY.values()]


def parse_output(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        raise ValueError(f"fixture output is not JSON: {e}")
