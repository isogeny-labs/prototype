"""Bounded adapter for the Isogeny Labs cryptanalysis suite (`crax`).

The adapter exposes the allowlisted tools in :mod:`runners.suite_tools` (curve audits, weak-curve analysis, ECDSA
transcript and RSA key audits, lattice estimates, and bounded research demos). Each tool validates typed parameters
and constructs its own fixed argv; callers never supply an executable, subcommand, flag, or arbitrary argv. Every
suite process receives no inherited credentials and is bounded by wall-clock/CPU/address-space/process limits, with
one wall-clock budget shared across a tool's invocations.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from pathlib import Path

from .base import Runner, RunRequest, RunResult, register
from .suite_tools import TOOLS, ParamError

SUITE_FIXTURES = tuple(TOOLS)
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ARGV_BYTES = 512 * 1024
ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "RUST_BACKTRACE": "0", "NO_COLOR": "1"}


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
        proc = subprocess.run([str(path), "--version"], capture_output=True, timeout=5, env=ENV, cwd=str(path.parent))
        text = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and text:
            return text[:80]
    except Exception:
        pass
    return "crax version unavailable"


def suite_identity() -> dict:
    """Binary path availability, SHA-256 and version (for the toolkit catalog and System screen)."""
    path, why = _binary()
    if path is None:
        return {"available": False, "reason": why}
    return {"available": True, "sha256": _sha256(path), "version": _version(path)}


class CryptanalysisSuiteRunner(Runner):
    kind = "cryptanalysis_suite"
    version = "2.0.0"
    provenance = "measured"
    fixtures = SUITE_FIXTURES
    description = (
        "Runs allowlisted, bounded crax JSON tools (curve audits, weak-curve analysis, ECDSA transcript and RSA key audits, "
        "ML-KEM/ML-DSA lattice estimates, bounded research demos) with typed parameters, a minimal replacement environment "
        "and wall-clock/CPU/memory limits. Arbitrary suite commands are not accepted."
    )

    def available(self) -> tuple[bool, str]:
        path, why = _binary()
        return (path is not None, why)

    def _fail(self, msg, **kw) -> RunResult:
        return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                         failures=[msg] if isinstance(msg, str) else msg, **kw)

    def run(self, req: RunRequest) -> RunResult:
        path, why = _binary()
        if path is None:
            return self._fail(f"runner unavailable: {why}")
        tool = TOOLS.get(req.fixture)
        if tool is None:
            return self._fail(f"fixture '{req.fixture}' is not allowlisted for {self.kind}")
        try:
            params = tool.validate(req.params)
            argvs = tool.build(params)
        except ParamError as exc:
            return self._fail(str(exc))
        if sum(len(a) for argv in argvs for a in argv) > MAX_ARGV_BYTES:
            return self._fail("tool input exceeds the argv size bound")

        timeout = max(1, min(int(req.limits.get("timeout_s", 120)), 900))
        mem_mb = max(128, min(int(req.limits.get("memory_mb", 1024)), 8192))
        cpu_s = max(1, min(int(req.limits.get("cpu_s", 90)), 900))
        digest = _sha256(path)
        limits = {"timeout_s": timeout, "memory_mb": mem_mb, "cpu_s": cpu_s, "shared_wall_clock": True}
        commands, results, raws = [], [], []
        deadline = time.monotonic() + timeout
        for tail in argvs:
            argv = [str(path), "--json", *tail]
            shown = argv if len(argv) <= 24 else argv[:24] + [f"… {len(argv) - 24} more arguments; full inputs are in the experiment definition"]
            commands.append({"argv": shown, "binary_sha256": digest, "limits": limits})
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._fail(f"tool exceeded its shared wall-clock budget of {timeout}s", commands=commands)
            try:
                proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=remaining,
                                      env=ENV, cwd=str(path.parent), preexec_fn=_limits(mem_mb, cpu_s))
            except subprocess.TimeoutExpired:
                return self._fail(f"suite operation exceeded the wall-clock budget of {timeout}s", commands=commands)
            except Exception as exc:
                return self._fail(f"could not start suite binary: {type(exc).__name__}: {exc}", commands=commands)
            raw = proc.stdout
            if len(raw) > MAX_OUTPUT_BYTES:
                return self._fail(f"suite JSON exceeded {MAX_OUTPUT_BYTES} bytes", commands=commands)
            try:
                rep = json.loads(raw.decode("utf-8", errors="strict"))
            except Exception as exc:
                tail_err = proc.stderr.decode("utf-8", errors="replace")[-2000:]
                return self._fail([f"suite stdout is not one JSON object: {type(exc).__name__}: {exc}", f"exit={proc.returncode}"]
                                  + ([tail_err] if tail_err else []), commands=commands, raw_output=(raw or proc.stderr)[:MAX_OUTPUT_BYTES])
            if not isinstance(rep, (dict, list)):
                return self._fail("suite JSON root is not an object", commands=commands, raw_output=raw)
            results.append((proc.returncode, rep))
            raws.append(raw)

        parsed = tool.parse(params, results)
        failures = list(parsed.failures)
        for (code, rep), tail in zip(results, argvs):
            if code != 0 and not (tool.nonzero_exit_ok and code == 1 and isinstance(rep, dict) and "error" not in rep):
                failures.append(f"suite exited with status {code} for `{' '.join(tail[:3])}`")
        if parsed.raw is not None and len(results) == 1 and parsed.raw is results[0][1] and not parsed.exclusions:
            raw_output = raws[0]          # unchanged suite stdout
        else:
            raw_output = json.dumps(parsed.raw if parsed.raw is not None else [r for _, r in results], indent=1).encode()

        software = {}
        first = results[0][1] if results else {}
        if isinstance(first, dict) and isinstance(first.get("software"), dict):
            software = first["software"]
        suite_version = str(software.get("version") or _version(path).removeprefix("crax "))
        return RunResult(
            status="completed" if not failures else "failed",
            provenance=self.provenance,
            runner_kind=self.kind,
            runner_version=f"adapter/{self.version} crax/{suite_version}"[:64],
            fixture_version=f"{tool.id}/crax-{suite_version}",
            environment={**software, "suite_version": suite_version, "suite_binary_sha256": digest,
                         "isolation": "subprocess+rlimit; minimal replacement environment; no inherited variables"},
            commands=commands,
            repeat_count=1,
            metrics={k: v for k, v in parsed.metrics.items() if v is not None},
            metric_definitions=parsed.definitions,
            scenarios=parsed.scenarios,
            raw_output=raw_output,
            failures=failures,
            exclusions=parsed.exclusions,
            limitations=list(tool.limitations),
            extra={"suite_tool": tool.id, "suite_operation": tool.operation,
                   "params": {k: (v if not isinstance(v, list) or len(v) <= 4 else f"{len(v)} items") for k, v in params.items()}},
        )


register(CryptanalysisSuiteRunner())
