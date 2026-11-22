"""Bounded adapter for the crypto crate's dynamic constant-time audit (`ct_dynamic_audit`, isogeny-labs/crypto #3296).

One allowlisted fixture, ``sidechannel_ct_audit``. For one allowlisted target it runs:

* ``valgrind --tool=memcheck --xml=yes ... ct_dynamic_audit taint TARGET`` (secret bytes marked undefined), and/or
* ``valgrind --tool=callgrind --collect-atstart=no ... ct_dynamic_audit ir TARGET`` (one dump per call, four classes),

then the binary's own ``analyze`` step, and maps that target's summary into metrics and scenarios. The target and
instrument are fixed choices; the runner constructs every argv, uses a fresh temporary directory, passes no
inherited environment, and shares one wall-clock budget across the processes. Nothing secret is produced: the audit
plants its own synthetic secrets from a fixed seed.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .base import Runner, RunRequest, RunResult, register
from .suite_tools import TOOLS, ParamError

FIXTURE = "sidechannel_ct_audit"
ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "RUST_BACKTRACE": "0"}
HARNESS_FILE = "ct_dynamic_audit_20261102/src/main.rs"


def is_harness_site(site: str) -> bool:
    """A site in the harness's own glue (its BigUint conversion of the secret in `call`), not in the code under test.

    The control functions `ct_dynamic_audit::ctrl_*` also live in the harness file, but they *are* the code under test
    for the controls, so they count as library sites.
    """
    return HARNESS_FILE in site and "ct_dynamic_audit::ctrl_" not in site


def _resolve(env_var: str, name: str) -> tuple[Path | None, str]:
    configured = os.environ.get(env_var)
    if configured:
        p = Path(configured)
        if not p.is_absolute():
            return None, f"{env_var} must be an absolute path"
        if not (p.is_file() and os.access(p, os.X_OK)):
            return None, f"{env_var} is not an executable file: {p}"
        return p.resolve(), ""
    found = shutil.which(name)
    return (Path(found).resolve(), "") if found else (None, f"{name} not found; set {env_var}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _limits(cpu_s: int):
    def pre():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))
            resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
            # No RLIMIT_AS: Valgrind reserves a large address space up front; memory is bounded by the host.
        except Exception:
            pass
    return pre


class CtAuditRunner(Runner):
    kind = "ct_audit"
    version = "1.0.0"
    provenance = "measured"
    fixtures = (FIXTURE,)
    description = ("Runs the crypto crate's dynamic constant-time audit (ct_dynamic_audit) under Valgrind for one allowlisted "
                   "target: Memcheck taint tracking of the secret and Callgrind instruction counts per call. Fixed argv, "
                   "fresh temporary directory, no inherited environment, shared wall-clock budget.")

    def available(self) -> tuple[bool, str]:
        b, why = _resolve("IEL_CT_AUDIT_BIN", "ct_dynamic_audit")
        if b is None:
            return False, why
        v, why = _resolve("IEL_VALGRIND_BIN", "valgrind")
        return (v is not None, why)

    def _fail(self, msg, **kw) -> RunResult:
        return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind, runner_version=self.version,
                         failures=[msg] if isinstance(msg, str) else msg, **kw)

    def run(self, req: RunRequest) -> RunResult:
        if req.fixture != FIXTURE:
            return self._fail(f"fixture '{req.fixture}' is not allowlisted for {self.kind}")
        binary, why = _resolve("IEL_CT_AUDIT_BIN", "ct_dynamic_audit")
        valgrind, why2 = _resolve("IEL_VALGRIND_BIN", "valgrind")
        if binary is None or valgrind is None:
            return self._fail(f"runner unavailable: {why or why2}")
        tool = TOOLS[FIXTURE]
        try:
            p = tool.validate(req.params)
        except ParamError as exc:
            return self._fail(str(exc))
        target, instrument, expect = p["target"], p.get("instrument", "both"), p.get("expect", "clean")

        timeout = max(30, min(int(req.limits.get("timeout_s", 900)), 3600))
        cpu_s = max(30, min(int(req.limits.get("cpu_s", 900)), 3600))
        digest = _sha256(binary)
        work = Path(tempfile.mkdtemp(prefix="iel-ct-"))
        raw, out = work / "raw", work / "out"
        raw.mkdir()
        argvs = []
        if instrument in ("both", "taint"):
            argvs.append([str(valgrind), "--tool=memcheck", "--xml=yes", f"--xml-file={raw}/memcheck-{target}.xml",
                          "--leak-check=no", "--track-origins=no", "--num-callers=40", "--error-limit=no",
                          str(binary), "taint", target])
        if instrument in ("both", "ir"):
            argvs.append([str(valgrind), "--tool=callgrind", "--collect-atstart=no",
                          f"--callgrind-out-file={raw}/callgrind.{target}.%p", str(binary), "ir", target])
        argvs.append([str(binary), "analyze", str(raw), str(out)])
        commands = [{"argv": [a.replace(str(work), "$WORKDIR") for a in argv], "binary_sha256": digest,
                     "limits": {"timeout_s": timeout, "cpu_s": cpu_s, "shared_wall_clock": True}} for argv in argvs]
        deadline = time.monotonic() + timeout
        try:
            for argv in argvs:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._fail(f"audit exceeded its wall-clock budget of {timeout}s", commands=commands)
                proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=remaining, env=ENV,
                                      cwd=str(work), preexec_fn=_limits(cpu_s))
                if proc.returncode != 0:
                    return self._fail([f"`{Path(argv[0]).name} {' '.join(argv[1:2])}` exited {proc.returncode}",
                                       proc.stderr.decode("utf-8", "replace")[-1500:]], commands=commands)
            summary = json.loads((out / "summary.json").read_text())
        except subprocess.TimeoutExpired:
            return self._fail(f"audit exceeded its wall-clock budget of {timeout}s", commands=commands)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"audit did not produce a summary: {type(exc).__name__}: {exc}", commands=commands)
        finally:
            vg_version = subprocess.run([str(valgrind), "--version"], capture_output=True, text=True, env=ENV).stdout.strip()
            shutil.rmtree(work, ignore_errors=True)

        entry = next((e for e in summary if e.get("target") == target), None)
        if entry is None:
            return self._fail(f"analyzer summary has no entry for {target}", commands=commands)
        result = map_entry(entry, instrument, expect)
        return RunResult(
            status="completed" if not result["failures"] else "failed", provenance=self.provenance,
            runner_kind=self.kind, runner_version=f"adapter/{self.version} {vg_version}"[:64],
            fixture_version=f"{FIXTURE}/ct_dynamic_audit-{digest[:12]}",
            environment={"ct_dynamic_audit_sha256": digest, "valgrind": vg_version,
                         "isolation": "subprocess + rlimit (CPU, processes); fresh temporary directory; no inherited variables"},
            commands=commands, repeat_count=1, metrics=result["metrics"], metric_definitions=METRIC_DEFINITIONS,
            scenarios=result["scenarios"], raw_output=json.dumps({"target": target, "instrument": instrument, "summary": entry}, indent=1).encode(),
            failures=result["failures"], limitations=list(tool.limitations),
            extra={"suite_tool": FIXTURE, "target": target, "instrument": instrument})


METRIC_DEFINITIONS = {
    "taint_sites_library": "Distinct secret-dependent sites (first in-crate frame and line) reported by Memcheck inside the library under test.",
    "taint_sites_harness": "Secret-dependent sites inside the audit harness itself (its BigUint conversion of the secret): an API-boundary effect, not a library line.",
    "taint_errors": "Total Memcheck reports (conditional jump/move or address depending on the undefined secret) over the 4 calls.",
    "ir_deterministic": "1 when repeating one fixed secret gives the same instruction count every time (the A/A arm); otherwise the per-call Ir test is not applicable.",
    "ir_secret_dependent": "1 when the instruction count differs between secrets with a deterministic A/A arm (an exact witness); 0 when no variation was observed; absent when not applicable.",
    "ir_min": "Smallest per-call instruction count across the random, short and low-weight classes.",
    "ir_max": "Largest per-call instruction count across the random, short and low-weight classes.",
    "ir_aa_spread": "max - min instruction count when one fixed secret is repeated (the noise floor of this instrument for this target).",
}


def map_entry(entry: dict, instrument: str, expect: str) -> dict:
    """Map one analyzer summary entry (ct_dynamic_audit `analyze`) to metrics, scenarios and failures."""
    sites = list(entry.get("taint_sites") or [])
    lib = [s for s in sites if not is_harness_site(s)]
    harness = [s for s in sites if is_harness_site(s)]
    ir = entry.get("ir") or {}
    metrics: dict = {}
    scenarios, failures = [], []
    if instrument in ("both", "taint"):
        if entry.get("taint_verdict") == "missing":
            failures.append("no Memcheck output for this target")
        metrics.update({"taint_sites_library": len(lib), "taint_sites_harness": len(harness), "taint_errors": entry.get("taint_errors", 0)})
        leak = len(lib) > 0
        scenarios.append({"id": "taint", "name": "Secret-dependent branch or address (Memcheck taint)",
                          "expected": "none" if expect == "clean" else "≥ 1 site", "observed": f"{len(lib)} library site(s)",
                          "pass": (not leak) if expect == "clean" else leak,
                          "detail": "; ".join(lib[:12]) + (f"; … +{len(lib) - 12}" if len(lib) > 12 else "")})
    if instrument in ("both", "ir"):
        aa = ir.get("aa")
        others = [ir[c] for c in ("random", "short", "lowhw") if ir.get(c)]
        if not aa or not others:
            failures.append("no Callgrind output for this target")
        else:
            det = aa["min"] == aa["max"]
            lo, hi = min(o["min"] for o in others), max(o["max"] for o in others)
            metrics.update({"ir_deterministic": 1 if det else 0, "ir_min": lo, "ir_max": hi, "ir_aa_spread": aa["max"] - aa["min"]})
            if det:
                dep = hi != lo
                metrics["ir_secret_dependent"] = 1 if dep else 0
                scenarios.append({"id": "ir", "name": "Instruction count depends on the secret (Callgrind)",
                                  "expected": "no variation" if expect == "clean" else "variation",
                                  "observed": f"{lo}–{hi} instructions" if dep else f"constant {lo}",
                                  "pass": (not dep) if expect == "clean" else dep, "detail": entry.get("ir_verdict", "")})
            else:
                scenarios.append({"id": "ir", "name": "Instruction count depends on the secret (Callgrind)",
                                  "expected": "deterministic A/A arm", "observed": f"A/A spread {aa['max'] - aa['min']}",
                                  "pass": None, "detail": "Not applicable: repeating one secret already varies the count (randomness or allocator state)."})
    return {"metrics": metrics, "scenarios": scenarios, "failures": failures}


register(CtAuditRunner())
