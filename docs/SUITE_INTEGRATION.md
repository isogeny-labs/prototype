# Cryptanalysis-suite integration

This document records the source review, execution boundary and evidence mapping for the optional Isogeny Labs
cryptanalysis-suite runner. It is an integration note, not a new cryptanalytic result.

The adapter was generalized on 2026-11-02 from two `icx` operations to the ten-tool registry below.

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

## Supported tools

The runner exposes ten allowlisted tools, declared in `backend/runners/suite_tools.py`. Each declares typed, bounded
parameters, builds its own argv, parses the suite JSON into metrics (with definitions), scenarios and failures, and states
its limitations. The UI (Research & Experiments → Cryptanalysis toolkit, per project) renders forms from these declarations. The toolkit and the research portfolio are supporting components of the Evidence Lab, not separate products.

| Fixture | Family | Constructed argv (after `crax --json`) | Question it answers |
|---|---|---|---|
| `suite_curve_audit` | Curves | `icx inspect CURVE` | Are the catalog curve parameters intact and do the group checks hold? |
| `suite_curve_estimate` | Curves | `icx estimate CURVE --envelope N` | What does the suite's rho / index-calculus operation-count model say? |
| `suite_weak_curve` | Curves | `ecdlp --curve NAME --analyze-only --x 1`, or `ecdlp --p --a --b --g --order` (+ `--x S` for planted controls, 2^34 budget) | Does the curve admit a structural shortcut (singular, Smart, Pohlig–Hellman, MOV)? |
| `suite_ecdsa_audit` | Signatures & keys | `ecdsa audit --curve C --q X,Y [--no-prefilter] --sig r,s,z …` or `--demo …` | Do emitted signatures leak the key through biased or reused nonces? |
| `suite_rsa_key_audit` | Signatures & keys | `rsa batch-gcd N…`, then per modulus `rsa fermat N --iterations I` and `rsa wiener N --e E` | Are deployed RSA keys factorable from public data (shared/close primes, small d)? |
| `suite_mlwe_estimate` | Post-quantum | `mlwe estimate --scheme S --model M --color never [--tours]` | How much lattice work separates an ML-KEM / ML-DSA set from key recovery, per model? |
| `suite_generic_rho` | Research demos | `rho --curve TOY --x S --seed K --max-ops 2^28 [--no-negation]` | What does the generic reference attack cost on a toy curve? |
| `suite_factor_toy` | Research demos | `factor N` (N ≤ 128 bits) | How does the factoring pipeline behave on small integers? |
| `suite_aes_reduced` | Symmetric & hash | `aes-attack --technique T --samples N` | Does differential / linear key recovery work on 1–2 round AES? |
| `suite_hash_kat` | Symmetric & hash | `hash --algorithm A --text T` or `--hex H` | Does an independent implementation reproduce our digest? |

Bounds: integers are decimal strings with a per-field bit limit (521 bits for curve fields, 576 for signature values,
4096 for RSA moduli, 128 for toy factoring); names (curves, schemes, models, algorithms, toy registry curves) are fixed
choices; lists are capped (512 signatures, 32 moduli); inputs above 512 KiB of argv are refused. Keys a tool does not
declare, or that do not apply to the selected mode, are dropped before argv is built. Suite tools receive only the
parameters the run recorded: catalog profile parameters and the customer's source snapshot are never merged in, and
no tool executes the customer's adapter.

### Controls

Every tool ships controls so a reviewer can see the detector work before trusting a clean result:

* **Negative controls** run on correctly generated material and must come back clean: P-256 / secp256k1 for the curve
  tools, a fresh 32-signature ES256 transcript from `cryptography`/OpenSSL with a full lattice sweep, six fresh RSA-2048
  keys, a hashlib-computed firmware digest.
* **Positive controls** plant the weakness the tool claims to find: an anomalous curve (#E = p, Smart) and a k = 2
  pairing-friendly curve (MOV / Pohlig–Hellman) with planted secrets, a planted 192-bit ECDSA nonce bias, an RSA batch
  with a shared prime and a close-prime modulus, and a modulus with a ~500-bit private exponent (Wiener); all synthetic RSA controls are 2048-bit moduli.

Static presets live beside each tool; controls that need fresh key material are generated server-side by
`backend/app/controls.py` and record their source and what was planted in the run's `inputs.control`.

### Redaction of recovered secrets

When an audit recovers a secret from a target that is not a declared synthetic control (an ECDSA private scalar, RSA
factors or private exponent), the stored raw output and metrics carry `[redacted sha256:<prefix>]` instead, and the run
records the redaction as an exclusion. The finding is retained; the key is not.

## Side-channel tool (separate runner)

`sidechannel_ct_audit` lives in the same tool registry but is executed by its own runner, `ct_audit`
(`backend/runners/ct_audit_runner.py`), not by `crax`. Each tool declares its runner; the toolkit dispatches on it and
reports availability per tool. Inputs are fixed choices: `target` (the 11 entry points of isogeny-labs/crypto #3296,
including the two controls), `instrument` (`taint`, `ir`, `both`) and `expect`. The runner resolves
`IEL_CT_AUDIT_BIN` and `IEL_VALGRIND_BIN` (or `PATH`), builds every argv, works in a fresh temporary directory
(recorded as `$WORKDIR`), passes no inherited environment, and shares one wall-clock budget across Memcheck, Callgrind
and the binary's `analyze` step. It sets no address-space limit because Valgrind reserves a large address space up
front. Sites in the harness's own glue (its BigUint conversion of the secret) are counted separately from library
sites; the `ctrl_*` control functions count as code under test. An instruction-count verdict whose A/A arm varies is
recorded as not applicable (`pass: null`), never as a pass or a failure.

`scripts/import_ct_audit.py /path/to/crypto` refreshes `seeds/ct_audit_snapshot.json` (source commit, summary and
receipt SHA-256). The seed always imports those 11 results; it also runs the controls and two targets live when the
binary and Valgrind are present.

## Process and evidence boundary

1. Resolve `crax` from the explicit `IEL_CRAX_BIN` path, or from `PATH` when no path is configured. An invalid explicit
   path is an error and never falls back silently.
2. Hash the executable with SHA-256 and record the digest beside the exact argv and limits.
3. Launch the absolute executable directly (no shell) with a replacement environment containing locale settings and
   `RUST_BACKTRACE=0`; no application credentials are inherited.
4. Apply wall-clock timeout, CPU seconds, address-space and process-count limits.
5. Apply one wall-clock budget across all of a tool's invocations (the RSA audit runs batch GCD plus two attacks per
   modulus).
6. Require one UTF-8 JSON value per invocation, no larger than 8 MiB. A non-zero exit is a failure, except where the
   tool declares exit 1 with a JSON report as a negative result (RSA attacks that found no factor).
7. Store stdout unchanged as the run's content-addressed raw artifact for single-invocation tools; multi-invocation
   tools and redacted reports store the combined (redacted) JSON. Map a stable subset into metrics/scenarios; retain
   suite software provenance and the binary hash in `environment`.

The adapter's provenance is `measured` because the platform actually executes the named suite operation. For `estimate`,
that means the platform measured that the model was executed—it does **not** turn the model's operation count into a
wall-clock measurement. The metric definitions and run limitations preserve that distinction.

## Hosted snapshot and reproducibility

The Pages workflow checks out `isogeny-labs/cryptanalysis` at
`318b27bf3427ff9e349f5850c742fde703fcf6a8` (bumped 2026-11-02 from `c273e62`; the newer revision carries the `ecdsa`,
`rsa`, `ecdlp`, `mlwe`, `rho`, `factor`, `aes-attack` and `hash` JSON reports the toolkit parses), builds only the
`crax` binary with the locked dependency graph, and exposes its absolute path through `IEL_CRAX_BIN`. Seeding then
executes the toolkit controls on the sample project and in the toolkit-controls demonstration project. The static site contains those real build-time outputs and evidence downloads, but cannot execute a new
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
* An ECDSA `no_bias` verdict or a clean RSA audit covers only those attacks on the submitted samples; side channels,
  padding parsers, entropy sources and key storage are not examined.
* ML-KEM / ML-DSA numbers are closed-form estimates under a named model; they are quoted with the model and are not a
  FIPS 203/204 conformance result. The ML-DSA-44 margin, for example, depends on whether BKZ tours are charged.
* The AES, rho and factoring tools run on toy or reduced-round instances and say nothing about deployed parameters.

## Where toolkit runs live in the revised model

Each tool has one versioned test definition per project (`test_id` = tool id, fixture = tool id). A tool run is an
append-only platform run with runner `cryptanalysis_suite`, execution mode `platform_sandbox`, provenance `measured`,
a platform-signed evidence bundle like every other sandbox run, and the typed parameters and control note in
`Run.inputs`. Operational requirements (latency, sizes) are not evaluated against tool runs. A failed non-control run
opens an `implementation_defect` finding for the implementation the evidence was filed under; recovered secrets are
redacted and recorded as exclusions.
