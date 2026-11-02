# Runner interface

A runner executes one fixture (or ingests one external result) and returns a `RunResult`. Runners never touch the
database; the job worker (`app/services.py`) persists results as append-only `Run` records and evaluates requirements.

```python
from runners import get_runner, RunRequest
r = get_runner("local_fixture").run(RunRequest(
    fixture="firmware_signing",
    params={"scheme": "ml_dsa_44", "image_bytes": 262144, "repeat_count": 30},
    implementation={...snapshot...}, experiment={...snapshot...},
    limits={"timeout_s": 300, "memory_mb": 1024, "cpu_s": 240}))
```

| Runner kind | Provenance | Status |
|---|---|---|
| `local_fixture` | measured | Supported. `python -I <fixture>` in a subprocess with empty env, RLIMIT_CPU/AS/NPROC and wall-clock timeout. Fixture allowlist: `firmware_signing`, `app_service_crypto`, `toy_factoring`. |
| `cryptanalysis_suite` | measured | Supported when `IEL_CRAX_BIN` or `PATH` resolves an executable `crax`. Fixed allowlist: `suite_curve_audit` (`crax --json icx inspect`) and `suite_curve_estimate` (`crax --json icx estimate`). Minimal replacement env (no inherited variables), fixed argv, validated inputs, RLIMIT_CPU/AS/NPROC and wall-clock timeout. |
| `import` | imported / illustrative | Supported. Validates the result document against the schema below, stores it as the raw artifact, records who imported it. |
| `docker_fixture` | measured | Implemented, **untested** (no daemon in the build environment). `docker run --network none --memory --cpus --pids-limit --read-only`. |
| `hardware` | measured | Interface only. A future device-lab agent produces documents in the schema below and submits them through `/runs/import` (or a signed channel later). |

`GET /api/runners` reports `available`, `implemented` and `tested_in_this_environment` for each runner; the UI shows the same.

## Fixture protocol

A fixture is a standalone script: JSON parameters on stdin, one JSON result document on stdout, exit 0. It must not
import the application. The same scripts run locally, in a container, or (later) on a device-lab host.

## Result document schema (version 1)

```json
{
  "fixture": "firmware_signing",            // required
  "fixture_version": "1.0.0",               // required
  "status": "completed" | "failed",         // required
  "environment": {"python": "...", "board": "...", "toolchain": "...", "measured_by": "..."},
  "repeat_count": 30,
  "scenarios": [ {"id": "tampered_image", "name": "...", "expected": "reject", "observed": "reject", "pass": true, "detail": ""} ],
  "metrics": {"verify_time_ms_median": 9.8, "signature_bytes": 2420, "functional_pass": 1, "rejection_scenarios_all_pass": 1},
  "metric_definitions": {"verify_time_ms_median": "how it was measured"},
  "raw": {...},                              // anything useful for reproduction (timing samples, hashes)
  "failures": [], "exclusions": [], "limitations": [],
  "illustrative": false                      // set true for demonstration data; the run is labelled accordingly
}
```

Metric keys are matched by name against project requirements (`Requirement.metric`). Memory and timing metrics must
state their definition in `metric_definitions`; the UI displays it next to the value.

## Cryptanalysis-suite result mapping

The suite already owns its scientific JSON contract. The adapter stores that stdout unchanged as the raw artifact and
maps only stable fields into the common run summary:

| Fixture | Suite operation | Summary evidence |
|---|---|---|
| `suite_curve_audit` | `icx inspect CURVE` | one scenario per parameter check; `suite_verified`, check counts, field/order bits, cofactor and the suite's generic-rho security estimate |
| `suite_curve_estimate` | `icx estimate CURVE --envelope N` | completion scenario; field/order bits, generic-rho operation/security estimates and index-calculus relevance classification |

The adapter does not accept raw commands, flags or paths. `CURVE` must match the suite identifier grammar and `N` is
bounded to 8–512. An estimate is explicitly an operation-count model, not a wall-clock prediction or demonstrated break.
See `SUITE_INTEGRATION.md` for the reviewed source contract and threat boundary.

## Adding a fixture

1. Put `backend/fixtures/<name>.py` next to the others (use `_common.py` helpers).
2. Add `<name>` to `ALLOWED_FIXTURES` in `runners/local_fixture.py` (and the Docker runner).
3. Add `<name>` to `FIXTURES` in `app/routers/experiments.py` and, if it is a research-only experiment, to the sandbox
   `ALLOWLIST` with parameter bounds.
4. Reference it from a catalog profile (`fixture` + `fixture_params`) so implementations using that profile run it.

Suite operations are not Python fixtures. Additions require an explicit adapter branch, input bounds, JSON mapping,
tests for command construction and failure handling, and a corresponding update to `SUITE_INTEGRATION.md`; never add a
generic "command" parameter.
