"""Import runner: ingests externally produced results (hardware lab, customer lab, onsite).

The import document must follow the fixture output schema (see docs/RUNNER_INTERFACE.md). Provenance is
`imported` (or `illustrative` when the submitter flags it as demonstration data). Imported evidence is
shown with its own label everywhere; it is never presented as a measurement taken by this platform.
"""
from __future__ import annotations

import json

from .base import Runner, RunRequest, RunResult, validate_fixture_output, register


class ImportRunner(Runner):
    kind = "imported_results"
    version = "1.0.0"
    provenance = "imported"
    description = ("Ingests existing, unsigned result documents that follow the result schema (e.g. a customer's own benchmark "
                   "export). Records the file hash; executes nothing. Signed runner bundles use the bundle import path instead.")

    def run(self, req: RunRequest) -> RunResult:
        data = req.params.get("document")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception as e:
                return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                                 runner_version=self.version, failures=[f"import document is not JSON: {e}"])
        if not isinstance(data, dict):
            return RunResult(status="failed", provenance=self.provenance, runner_kind=self.kind,
                             runner_version=self.version, failures=["import document missing"])
        problems = validate_fixture_output(data)
        provenance = "illustrative" if (req.params.get("illustrative") or data.get("illustrative")) else "imported"
        raw = json.dumps(data, indent=1, sort_keys=True).encode()
        limitations = list(data.get("limitations", []))
        limitations.append("Imported evidence: measured outside this platform by " +
                           str(data.get("environment", {}).get("measured_by", "an external party")) +
                           "; the platform verified the document schema and hash only.")
        if provenance == "illustrative":
            limitations.append("ILLUSTRATIVE DATA: provided for demonstration; not a real measurement.")
        return RunResult(
            status="completed" if not problems and data.get("status", "completed") == "completed" else "failed",
            provenance=provenance, runner_kind=self.kind, runner_version=self.version,
            fixture_version=str(data.get("fixture_version", "")), environment=data.get("environment", {}),
            commands=data.get("commands", []), repeat_count=int(data.get("repeat_count", 0)),
            metrics=data.get("metrics", {}), metric_definitions=data.get("metric_definitions", {}),
            scenarios=data.get("scenarios", []), raw_output=raw,
            failures=list(data.get("failures", [])) + problems, exclusions=data.get("exclusions", []),
            limitations=limitations)


register(ImportRunner())
