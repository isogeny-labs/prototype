# Cryptanalysis-suite integration

This document records the source review, execution boundary and evidence mapping for the optional Isogeny Labs
cryptanalysis-suite runner. It is an integration note, not a new cryptanalytic result.

## Source review (2026-11-01)

Primary sources checked before selecting the adapter design:

* The suite overview, supported Rust version and explicit non-production warning:
  [`suite/README.md` at the pinned suite revision](https://github.com/isogeny-labs/cryptanalysis/blob/c273e62140071fe4370fbe6946dcb898c95b4eb2/suite/README.md).
* The unified CLI contract—every command accepts `--json`, emits one JSON object, and independently checks reported
  answers where applicable:
  [`docs/CRAX.md`](https://github.com/isogeny-labs/cryptanalysis/blob/c273e62140071fe4370fbe6946dcb898c95b4eb2/docs/CRAX.md) and
  [`suite/src/cli/output.rs`](https://github.com/isogeny-labs/cryptanalysis/blob/c273e62140071fe4370fbe6946dcb898c95b4eb2/suite/src/cli/output.rs).
* The exact `icx inspect` / `icx estimate` schema, status semantics, provenance block and scope language:
  [`suite/src/cli/tools/icx.rs`](https://github.com/isogeny-labs/cryptanalysis/blob/c273e62140071fe4370fbe6946dcb898c95b4eb2/suite/src/cli/tools/icx.rs).
* This prototype's persistence and provenance contract: [`RUNNER_INTERFACE.md`](RUNNER_INTERFACE.md),
  [`DATA_MODEL.md`](DATA_MODEL.md), and `backend/runners/base.py`.
* Python 3.13's official [`subprocess`](https://docs.python.org/3.13/library/subprocess.html) guidance: pass argv as a
  sequence, prefer a fully qualified executable, use an explicit replacement environment, capture output, and enforce a
  timeout; and the official [`resource`](https://docs.python.org/3.13/library/resource.html) definitions for
  `RLIMIT_CPU` and `RLIMIT_AS`.
* The official `actions/checkout` v4
  [nested multiple-repository checkout pattern](https://github.com/actions/checkout/blob/v4/README.md#checkout-multiple-repos-nested),
  used by the Pages build to fetch the exact pinned suite revision.

These sources support a narrow subprocess adapter around the suite's existing JSON interface. They do not support
reimplementing attacks in Python, parsing Markdown reports, or treating a catalog estimate as measured exploit cost.

## Supported operations

| Prototype fixture | Constructed argv | Accepted success status |
|---|---|---|
| `suite_curve_audit` | `crax --json icx inspect CURVE` | `checks_passed` and `verified: true` |
| `suite_curve_estimate` | `crax --json icx estimate CURVE --envelope N` | `complete` |

`CURVE` is 1–64 characters, starts with an ASCII letter/digit and contains only letters, digits, `.`, `_`, `+` or `-`.
`N` is an integer from 8 through 512. Neither value is interpreted by a shell. The runner has no parameter for an
executable, subcommand, flag, working directory, environment variable or output path.

## Process and evidence boundary

1. Resolve `crax` from the explicit `IEL_CRAX_BIN` path, or from `PATH` when no path is configured. An invalid explicit
   path is an error and never falls back silently.
2. Hash the executable with SHA-256 and record the digest beside the exact argv and limits.
3. Launch the absolute executable directly (no shell) with a replacement environment containing locale settings and
   `RUST_BACKTRACE=0`; no application credentials are inherited.
4. Apply wall-clock timeout, CPU seconds, address-space and process-count limits.
5. Require a single UTF-8 JSON object no larger than 8 MiB, schema version 1, the expected operation and success status.
6. Store stdout unchanged as the run's content-addressed raw artifact. Map a small stable subset into metrics/scenarios;
   retain suite software/backend provenance and the binary hash in `environment`.

The adapter's provenance is `measured` because the platform actually executes the named suite operation. For `estimate`,
that means the platform measured that the model was executed—it does **not** turn the model's operation count into a
wall-clock measurement. The metric definitions and run limitations preserve that distinction.

## Hosted snapshot and reproducibility

The Pages workflow checks out `isogeny-labs/cryptanalysis` at
`c273e62140071fe4370fbe6946dcb898c95b4eb2`, builds only the `crax` binary with the locked dependency graph, and exposes
its absolute path through `IEL_CRAX_BIN`. Seeding then executes a P-256 parameter audit and estimate for the design-stage
ES256 candidate. The static site contains those real build-time outputs and evidence downloads, but cannot execute a new
run in a visitor's browser.

Updating the pinned suite revision is a deliberate source change. Review the JSON contract, rerun the adapter tests and
inspect the resulting raw evidence before changing the pin.

## Explicit non-claims

* A passing curve audit does not review a library implementation, application protocol, key lifecycle, entropy source,
  side channels or fault resistance.
* The generic-rho and index-calculus fields are model outputs in the units stated by the suite. They are not a calendar
  forecast, monetary estimate, wall-clock benchmark or claim that a deployed curve is practically broken.
* The suite itself states that its primitives and attacks are not constant-time or audited and must not protect data.
* Heavy attack runs, arbitrary commands, GPU workers, distributed rho, file-producing workflows and repository scanning
  remain outside this adapter.
