# Isogeny Evidence Lab — MVP

A cryptographic implementation, benchmarking and continuous-research platform. The product is one traceable loop:

**Understand → Recommend → Implement → Benchmark & test → Record evidence → Research changes → Recommend remediation → Approve → Reimplement → Retest.**

Two workflows share one model: firmware signing / update verification for IoT devices, and library/configuration
changes in a containerised application service. Read `docs/SCOPE.md` first: it states what runs for real, what is
imported or illustrative, and what is out of scope.

## Run it

```bash
pip install -r requirements.txt
./scripts/dev_server.sh start          # seeds three demo projects on first start; http://127.0.0.1:8008
./scripts/dev_server.sh stop
```

Or by hand: `cd backend && python3 -m uvicorn app.main:app --port 8008`. The background worker runs as a thread by
default; set `IEL_WORKER=external` and run `python -m app.worker` to run it as a separate process.

Demo accounts (seeded): `engineer@customer.local` / `engineer-demo-password` (editor), `reviewer@isogeny.local` /
`reviewer-demo-password` (reviewer), `admin@isogeny.local` / `admin-demo-password` (admin). Passwords are PBKDF2-hashed;
sessions are bearer tokens stored hashed; logs redact tokens/keys.

Configuration (environment): `IEL_DATA_DIR`, `IEL_DATABASE_URL`, `IEL_ARTIFACT_DIR`, `IEL_WORKER`, `IEL_RUNNER_TIMEOUT`,
`IEL_RUNNER_MEMORY_MB`, `IEL_RUNNER_CPU_SECONDS`, `IEL_SKIP_SEED=1`, `ANTHROPIC_API_KEY` (optional AI adapter for
research extraction; absent ⇒ rule-based extraction, shown in the UI), and `IEL_CRAX_BIN` (optional absolute path to
the Isogeny Labs cryptanalysis suite's `crax` binary). When `IEL_CRAX_BIN` is absent, the suite runner also checks
`PATH`; if no binary is found, the runner is shown as unavailable rather than silently simulated.

## Cryptanalysis toolkit and research portfolio

The Isogeny Labs cryptanalysis suite (`crax`) is connected as ten bounded tools, each answering one engineering
question and leaving an append-only evidence record:

| Family | Tools |
|---|---|
| Curves & parameters | curve parameter audit · attack-cost model (rho / index calculus) · structural weak-curve analysis (singular, Smart, Pohlig–Hellman, MOV) |
| Signatures & keys | ECDSA signature-transcript audit (biased / reused nonces, lattice key recovery) · RSA public-key hygiene audit (batch GCD, Fermat, Wiener) |
| Post-quantum | ML-KEM / ML-DSA lattice-attack estimate under named cost models |
| Symmetric & hash | reduced-round AES key recovery · digest known-answer cross-check |
| Research demos | Pollard rho on toy curves · toy integer factoring |

Every tool ships **controls**: negative controls must come back clean on correctly generated material (a real ES256
transcript, fresh RSA-2048 keys, P-256); positive controls plant the weakness the tool claims to find (an anomalous
curve, a biased nonce, a shared prime, a small private exponent). Screens: **Toolkit** (catalog, top bar), per-project
**Toolkit** (forms rendered from each tool's typed parameters, controls, run history) and **Research** — a read-only,
hash-pinned snapshot of the index-calculus leaderboard showing each row's distance remaining to the matched Pollard rho
and its validation-gate status. Refresh it with `python3 scripts/import_research_portfolio.py /path/to/crypto`.

Build `crax` (Rust ≥ 1.87) from the cryptanalysis repository and point the app at it:

```bash
cargo build --release --locked --manifest-path /path/to/cryptanalysis/suite/Cargo.toml --bin crax
export IEL_CRAX_BIN=/path/to/cryptanalysis/suite/target/release/crax
```

Seeding then runs 26 suite tool runs across three demo projects (about 35 s, most of it the full ECDSA lattice sweep).
Details, bounds and the redaction rule: [`docs/SUITE_INTEGRATION.md`](docs/SUITE_INTEGRATION.md).

## Hosted demo (GitHub Pages)

GitHub Pages serves static files only, so the backend (API, fixtures, job queue) is **not** hosted there. The workflow
`.github/workflows/pages.yml` runs the tests, checks out the cryptanalysis repository at the pinned revision recorded in
that workflow, builds `crax`, then runs `scripts/build_static_site.py`. The builder boots the real app against a throw-away
database, executes the seeded fixtures and every suite tool's controls, snapshots every API response the UI uses, and
publishes a **read-only** copy of the UI. Browsing, drill-downs, comparisons and evidence downloads work; every write is
disabled with an explanation. One-time setup: repository Settings → Pages → Source: **GitHub Actions**. Local preview:
`python3 scripts/build_static_site.py site && python3 -m http.server -d site`.

The suite boundary and source review are documented in [`docs/SUITE_INTEGRATION.md`](docs/SUITE_INTEGRATION.md).

## Tests

```bash
cd backend && python3 -m pytest tests -q
```

`test_feedback_loop_iot.py` walks the required 10-step demonstration through the HTTP API: create IoT project, import
inventory, record baseline/candidate, run the fixture + import illustrative hardware results, detect the failed
signature-slot requirement, add a research finding, generate/review a remediation, approve a new candidate (ML-DSA-44),
rerun/import (including a failed retest that keeps the finding open and an append-only correction), compare, close,
export and verify the evidence package. `test_feedback_loop_app.py` does the same on the containerised service with a
real fixture run. `test_components.py` covers fixtures, runners, attack-cost rules, sandbox gating, auth and redaction.
`test_toolkit.py` covers suite-tool parameter bounds, argv construction, secret redaction and the toolkit API with a fake
suite; with `IEL_CRAX_BIN` set it also runs every tool's controls against the real binary (skipped otherwise).

## Layout

```
backend/app        FastAPI app: models, auth, audit, jobs, catalog, recommend, evaluate, research, attackcost, export, seed, routers/
backend/runners    Runner interface + local/import/docker/hardware + cryptanalysis-suite adapter and tool registry (suite_tools.py)
backend/fixtures   Standalone fixtures: firmware_signing, app_service_crypto, toy_factoring (stdin JSON → stdout JSON)
backend/tests      Feedback-loop and component tests
frontend/          Vanilla-JS single-page UI served by the backend
seeds/             Inventories, illustrative hardware results, demonstration research documents, research_portfolio.json
docs/              SCOPE.md, RUNNER_INTERFACE.md, DATA_MODEL.md
```

## Screens

Portfolio · Project overview (what changed / what we tested / what we learned / what to do next) · Inventory &
requirements · Recommendation workspace & detail · Implementation workspace & detail · Evidence (runs, raw output,
artifacts) · Toolkit (catalog + per-project workspace) · Research portfolio · Baseline-vs-candidate comparison · Research inbox & finding detail · Attack-cost research view ·
Cryptanalysis sandbox · Version-to-version revalidation history · Audit · System (runners, catalog, jobs).

## Principles enforced in code

* Every inventory fact and every run carries a provenance label; identifying an algorithm never implies its
  implementation is secure; passing tests is not proof of security; hashes are for integrity, not validity.
* Runs are append-only; corrections are new records.
* Recommendations never cross purposes (signatures vs KEMs vs ciphers); "no immediate migration" is a valid outcome;
  nothing is described as unconditionally secure or quantum-proof; no calendar date for quantum attacks is asserted.
* Human approval records are required before a research finding changes a recommendation, before a candidate is
  approved, and before a sandbox experiment runs. Authors cannot approve their own items.
* A failed retest keeps a finding open. Nothing is deployed, rotated or replaced automatically.
* Research documents are untrusted data: stored, hashed, pattern-matched, never executed.
