"""Bounded adapter for the Isogeny Labs cryptanalysis suite (`crax`).

The adapter intentionally exposes two read-only, machine-readable operations:

* ``suite_curve_audit`` -> ``crax --json icx inspect CURVE``
* ``suite_curve_estimate`` -> ``crax --json icx estimate CURVE``

Callers never supply an executable, subcommand, flag, or arbitrary argv. The
curve identifier and estimate envelope are validated before the fixed argv is
constructed. The suite process receives no inherited credentials and is
bounded by the same wall-clock/CPU/address-space limits as local fixtures.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base import Runner, RunRequest, RunResult, register

SUITE_FIXTURES = ("suite_curve_audit", "suite_curve_estimate")
CURVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}\Z")
MAX_OUTPUT_BYTES = 8 * 1024 * 1024


def _limits(mem_mb: int, cpu_s: int):
    def pre():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass

    return pre


def _binary() -> tuple[Path | None, str]:
    configured = os.environ.get("IEL_CRAX_BIN")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            return None, "IEL_CRAX_BIN must be an absolute path"
        if not path.is_file():
            return None, f"IEL_CRAX_BIN does not name a file: {path}"
        if not os.access(path, os.X_OK):
            return None, f"IEL_CRAX_BIN is not executable: {path}"
        return path.resolve(), ""
    found = shutil.which("crax")
    if found:
        return Path(found).resolve(), ""
    return None, "crax not found; set IEL_CRAX_BIN to the built suite binary"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _version(path: Path) -> str:
    try:
        proc = subprocess.run(
            [str(path), "--version"], capture_output=True, timeout=5,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, cwd=str(path.parent),
        )
        text = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and text:
            return text[:80]
    except Exception:
        pass
    return "crax version unavailable"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _input_int(value: Any) -> int | None:
    """Accept a JSON integer without coercing strings, booleans, or fractions."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _common_limitations(operation: str) -> list[str]:
    limits = [
        "The cryptanalysis suite is an attack and research toolkit; it is not constant-time, audited, or a production cryptographic implementation.",
        "This run records only the named suite operation. It is not proof that the target implementation is secure.",
    ]
    if operation == "inspect":
        limits.append("Curve inspection verifies catalog parameters and group checks; it does not inspect application code, key generation, protocol use, side channels, or fault resistance.")
    else:
        limits.append("The attack-cost result is a named operation-count model, not a wall-clock prediction, exploit demonstration, or claim of practical breakability.")
    return limits


def _audit_result(report: dict) -> tuple[dict, dict, list]:
    curve = report.get("curve") if isinstance(report.get("curve"), dict) else {}
    field = curve.get("field") if isinstance(curve.get("field"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    scenarios = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            continue
        observed = str(check.get("status", "unknown"))
        name = str(check.get("name", f"check_{index + 1}"))
        scenarios.append({
            "id": "suite_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
            "name": name,
            "expected": "pass",
            "observed": observed,
            "pass": observed == "pass",
            "detail": str(check.get("detail", "")),
        })
    verified = report.get("verified") is True
    metrics = {
        "suite_verified": 1 if verified else 0,
        "suite_checks_passed": sum(1 for s in scenarios if s["pass"]),
        "suite_checks_total": len(scenarios),
        "field_bits": _as_int(field.get("bits")),
        "subgroup_order_bits": _as_int(curve.get("order_bits")),
        "rho_security_bits": _as_float(curve.get("rho_security_bits")),
    }
    cofactor = _as_int(curve.get("cofactor"))
    if cofactor is not None:
        metrics["cofactor"] = cofactor
    definitions = {
        "suite_verified": "1 only when every parameter check in the suite's icx inspect report passed.",
        "suite_checks_passed": "Count of icx parameter checks whose reported status is pass.",
        "suite_checks_total": "Total parameter checks returned by icx inspect.",
        "field_bits": "Bit length of the catalog field reported by icx inspect.",
        "subgroup_order_bits": "Bit length of the catalog subgroup order reported by icx inspect.",
        "rho_security_bits": "Suite estimate of generic Pollard-rho security in bits for the named subgroup; an operation-count model, not elapsed time.",
        "cofactor": "Catalog curve group cofactor parsed from the suite report.",
    }
    return metrics, definitions, scenarios


def _estimate_result(report: dict) -> tuple[dict, dict, list]:
    generic = report.get("generic_attack") if isinstance(report.get("generic_attack"), dict) else {}
    ic = report.get("index_calculus") if isinstance(report.get("index_calculus"), dict) else {}
    status = str(report.get("status", "unknown"))
    metrics = {
        "field_bits": _as_int(report.get("field_bits")),
        "subgroup_order_bits": _as_int(report.get("order_bits")),
        "rho_security_bits": _as_float(generic.get("security_bits")),
        "rho_log2_operations": _as_float(generic.get("log2_operations")),
        "index_calculus_relevant": 1 if ic.get("relevant") is True else 0,
    }
    definitions = {
        "field_bits": "Bit length of the catalog field used by the suite estimate.",
        "subgroup_order_bits": "Bit length of the catalog subgroup order used by the suite estimate.",
        "rho_security_bits": "Generic Pollard-rho security estimate in bits from icx; not a wall-clock prediction.",
        "rho_log2_operations": "Base-2 logarithm of the suite's generic Pollard-rho operation-count estimate.",
        "index_calculus_relevant": "1 when the suite classifies index calculus as relevant for the named curve family and configured envelope; 0 otherwise.",
    }
    scenarios = [{
        "id": "suite_estimate_generated",
        "name": "Machine-readable suite estimate generated",
        "expected": "complete",
        "observed": status,
        "pass": status == "complete",
        "detail": "This validates report completion only; it does not validate practical attack feasibility.",
    }]
    return metrics, definitions, scenarios


class CryptanalysisSuiteRunner(Runner):
    kind = "cryptanalysis_suite"
    version = "1.0.0"
    provenance = "measured"
    fixtures = SUITE_FIXTURES
    description = (
        "Runs bounded, allowlisted crax JSON operations with a minimal replacement environment and wall-clock/CPU/memory limits. "
        "Supports standardized-curve parameter audits and attack-cost estimates; arbitrary suite commands are not accepted."
    )

    def available(self) -> tuple[bool, str]:
        path, why = _binary()
        return (path is not None, why)

    def run(self, req: RunRequest) -> RunResult:
        path, why = _binary()
        if path is None:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, failures=[f"runner unavailable: {why}"])
        if not self.supports(req.fixture):
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version,
                             failures=[f"fixture '{req.fixture}' is not allowlisted for {self.kind}"])

        curve = str(req.params.get("curve", "")).strip()
        if not CURVE_ID.fullmatch(curve):
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version,
                             failures=["curve must be a 1-64 character suite identifier beginning with a letter or digit"])

        operation = "inspect" if req.fixture == "suite_curve_audit" else "estimate"
        argv = [str(path), "--json", "icx", operation, curve]
        if operation == "estimate":
            envelope = _input_int(req.params.get("envelope_bits", 64))
            if envelope is None or not 8 <= envelope <= 512:
                return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                                 runner_version=self.version,
                                 failures=["envelope_bits must be an integer from 8 through 512"])
            argv.extend(["--envelope", str(envelope)])

        timeout = max(1, min(int(req.limits.get("timeout_s", 120)), 900))
        mem_mb = max(128, min(int(req.limits.get("memory_mb", 1024)), 8192))
        cpu_s = max(1, min(int(req.limits.get("cpu_s", 90)), 900))
        digest = _sha256(path)
        commands = [{
            "argv": argv,
            "binary_sha256": digest,
            "limits": {"timeout_s": timeout, "memory_mb": mem_mb, "cpu_s": cpu_s},
        }]
        env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "RUST_BACKTRACE": "0"}
        try:
            proc = subprocess.run(
                argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                env=env, cwd=str(path.parent), preexec_fn=_limits(mem_mb, cpu_s),
            )
        except subprocess.TimeoutExpired as exc:
            raw = (exc.stdout or b"")[:MAX_OUTPUT_BYTES]
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, raw_output=raw,
                             failures=[f"suite operation exceeded wall-clock timeout of {timeout}s"])
        except Exception as exc:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands,
                             failures=[f"could not start suite binary: {type(exc).__name__}: {exc}"])

        raw = proc.stdout
        stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        if len(raw) > MAX_OUTPUT_BYTES:
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, raw_output=raw[:MAX_OUTPUT_BYTES],
                             failures=[f"suite JSON exceeded {MAX_OUTPUT_BYTES} bytes"])
        try:
            report = json.loads(raw.decode("utf-8", errors="strict"))
        except Exception as exc:
            failures = [f"suite stdout is not one JSON object: {type(exc).__name__}: {exc}",
                        f"exit={proc.returncode}"]
            if stderr_tail:
                failures.append(stderr_tail)
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands,
                             raw_output=raw or proc.stderr[:MAX_OUTPUT_BYTES], failures=failures)
        if not isinstance(report, dict):
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, commands=commands, raw_output=raw,
                             failures=["suite JSON root is not an object"])

        failures = []
        if report.get("schema_version") != 1:
            failures.append(f"unsupported suite schema_version: {report.get('schema_version')!r}")
        if report.get("operation") != operation:
            failures.append(f"suite returned operation {report.get('operation')!r}; expected {operation!r}")
        expected_status = "checks_passed" if operation == "inspect" else "complete"
        if report.get("status") != expected_status:
            failures.append(str(report.get("message") or f"suite status was {report.get('status')!r}"))
        if proc.returncode != 0:
            failures.append(f"suite exited with status {proc.returncode}")
        if operation == "inspect":
            metrics, definitions, scenarios = _audit_result(report)
            if report.get("verified") is not True:
                failures.append("suite did not verify every curve parameter check")
        else:
            metrics, definitions, scenarios = _estimate_result(report)

        software = report.get("software") if isinstance(report.get("software"), dict) else {}
        suite_version = str(software.get("version") or _version(path).removeprefix("crax "))
        runner_version = f"adapter/{self.version} crax/{suite_version}"[:64]
        return RunResult(
            status="completed" if not failures else "failed",
            provenance=self.provenance,
            runner_kind=self.kind,
            runner_version=runner_version,
            fixture_version=f"crax-icx/schema-{report.get('schema_version', 'unknown')}",
            environment={
                **software,
                "suite_binary_sha256": digest,
                "isolation": "subprocess+rlimit; minimal replacement environment; no inherited variables",
            },
            commands=commands,
            repeat_count=1,
            metrics={k: v for k, v in metrics.items() if v is not None},
            metric_definitions=definitions,
            scenarios=scenarios,
            raw_output=raw,
            failures=failures,
            limitations=_common_limitations(operation),
            extra={"suite_operation": operation, "curve": curve},
        )


register(CryptanalysisSuiteRunner())
