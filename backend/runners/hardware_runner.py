"""Hardware runner INTERFACE (future integration).

Defines the contract a device-lab agent must satisfy to push on-device measurements into the platform.
No hardware is supported in this MVP; this runner is registered so the UI can show the integration point,
and it refuses to run. Externally produced device results are ingested via the `import` runner instead.

Contract for a future local agent (see docs/RUNNER_INTERFACE.md):
  1. Receive RunRequest JSON (fixture, params, implementation snapshot, limits).
  2. Flash/configure the device, execute scenarios, collect timing with the device's own clock.
  3. Produce a result document in the fixture output schema, including `environment.board`,
     `environment.toolchain`, `environment.measured_by`, and per-metric definitions.
  4. Sign or hash the document; the platform stores it as provenance=measured with runner_kind=hardware.
"""
from .base import Runner, RunRequest, RunResult, register


class HardwareRunner(Runner):
    kind = "hardware"
    version = "0.0.0-interface"
    provenance = "measured"
    implemented = False
    tested_here = False
    description = "Interface only. Future device-lab agent for on-device measurements. Not implemented."

    def available(self):
        return False, "no hardware agent connected (interface only)"

    def run(self, req: RunRequest) -> RunResult:
        return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                         runner_version=self.version, failures=["hardware runner is an interface only; import results instead"])


register(HardwareRunner())
