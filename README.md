# Isogeny Labs — Evidence Lab (MVP)

Test your cryptographic implementation. Understand the evidence. Improve with confidence.

Customers import their existing signature implementation, run reproducible tests, investigate findings through proposed
experiments, and receive evidence-backed guidance. The loop:

**Import implementation → Establish baseline → Run tests → Review findings → Autoresearcher proposes experiments →
Human approves → Execute experiment → Recommend improvements → Customer implements changes externally → Import revised
version → Retest.**

Read `docs/SCOPE.md` first: it states what is real, imported, simulated, unavailable and out of scope.

## Run it
```bash
pip install -r requirements.txt
./scripts/dev_server.sh start        # seeds the sample project on first start (real sandbox runs); http://127.0.0.1:8008
./scripts/dev_server.sh stop
cd backend && python3 -m pytest tests -q
```
Demo accounts: `engineer@customer.local` / `engineer-demo-password` (editor), `reviewer@isogeny.local` / `reviewer-demo-password`
(reviewer), `admin@isogeny.local` / `admin-demo-password` (admin, owner). Reviewers and owners approve; editors import and run.

Environment: `IEL_DATA_DIR`, `IEL_DATABASE_URL`, `IEL_ARTIFACT_DIR`, `IEL_PLATFORM_KEY_PATH`, `IEL_WORKER` (`thread` | `external`,
then `python -m app.worker`), `IEL_RUNNER_TIMEOUT|MEMORY_MB|CPU_SECONDS`, `IEL_SKIP_SEED=1`, `ANTHROPIC_API_KEY` (optional AI
adapter for research extraction; absent ⇒ rule-based, labelled in the UI).

## What the sample project shows (all produced at seed time, all labelled demonstration)
1. `acme-signer 1.0.0` imported with a source snapshot; static compatibility check passes; **seeded defect**: `verify()` keeps only
   the first 64 signature bytes, so signatures with trailing data verify.
2. Platform-sandbox run of `signature-library-core@1`: valid signatures and the RFC 8032 vector pass; `trailing_byte` and
   `trailing_garbage` fail → finding opened (reproduced).
3. Customer-side runner bundle for 1.0.0 imported and verified (imported · hash-checked · signature-verified).
4. Research source submitted; autoresearcher proposes a malformed-input sweep; reviewer approves protocol v1; the sandbox
   executes it; result reviewed.
5. Evidence-backed, project-specific recommendation (input validation) approved.
6. `acme-signer 1.1.0` imported as the externally corrected version linked to the recommendation → awaiting retest.
7. Retest passes → finding **resolved within tested scope**; comparison shows the fixed cases and no regressions.
8. Exports: engineering handoff, signed evidence bundles (verify with `iel_tools/verify.py`), evidence package, optional
   compliance template with missing evidence identified.

## Layout
```
backend/app       FastAPI app: models, auth, audit, jobs, compat (static snapshot checks), services (runs, bundles, import,
                  replay, findings, retest), research (autoresearcher), recommend, attackcost, export, signing, seed, routers/
backend/runners   platform_sandbox (unshare net ns + rlimits), imported_results, docker_sandbox (untested), cryptanalysis_suite + suite_tools
backend/fixtures  signature_library (core), malformed_input_sweep (experiment), toy_factoring (experiment), adapters, vectors
iel_tools         attest.py (DSSE + in-toto), runner.py (customer-side), verify.py (standalone), Dockerfile (untested)
frontend          dark-mode single-page UI; assets/ holds the supplied logos (trimmed crops only)
seeds             sample manifests, sample adapters (1.0.0 defect, 1.1.0 fix), demonstration research document, research_portfolio.json
docs              SCOPE.md, ATTESTATION.md, RUNNER_INTERFACE.md, DATA_MODEL.md, SUITE_INTEGRATION.md
scripts           dev_server.sh, build_static_site.py (read-only demo for GitHub Pages / single file), package_runner.sh
```

## Cryptanalysis toolkit and research portfolio (supporting components)
Under Research & Experiments: the Isogeny Labs cryptanalysis suite (`crax`) connected as ten bounded tools (curve audits,
weak-curve analysis, ECDSA transcript and RSA key audits, ML-KEM/ML-DSA lattice estimates, toy demos), each with negative
and positive controls, and a read-only, hash-pinned snapshot of the index-calculus research leaderboard. Build `crax`
and point the app at it with `IEL_CRAX_BIN` (the Pages workflow does this); without it the runner reports itself
unavailable and nothing is simulated. Details and bounds: `docs/SUITE_INTEGRATION.md`.

A **side-channel** tool (`ct_audit` runner) runs the `crypto` crate's dynamic constant-time harness under Valgrind for one
allowlisted target: Memcheck taint of the secret (secret-dependent branches and addresses, split into library and harness
sites) and Callgrind instruction counts across secret classes, with positive and negative controls. Build
`ct_dynamic_audit` in the crypto repository (`cargo build --release --bin ct_dynamic_audit`), install Valgrind and set
`IEL_CT_AUDIT_BIN`. Without it, the frozen run of isogeny-labs/crypto #3296 is shown as hash-pinned imported evidence in
the "Side-channel audit: crypto crate" project (`scripts/import_ct_audit.py` refreshes `seeds/ct_audit_snapshot.json`).

## Customer-side runner and verifier
See `iel_tools/README.md` and `docs/ATTESTATION.md`. Bundles are in-toto Statements in DSSE envelopes signed with Ed25519
(`cryptography`). The platform accepts a bundle only after checking signature, expected signer, artifact digests, schema and
project/implementation binding; duplicates and stale submissions are flagged, not counted.

## Hosted read-only demo
`.github/workflows/pages.yml` runs the tests, builds the sample project with real executions, snapshots the UI's API responses
and publishes a read-only copy (writes disabled). `demo/iel-demo.html` is the same demo as a single file.

## Principles enforced in code
* Importing code never executes it; execution happens only in the isolated sandbox or on the customer's machine.
* No production keys: private-key formats are rejected on upload; fixtures generate synthetic keys.
* Runs are append-only; corrections are new records. Evidence labels are separate and composable; none means "secure" or "compliant".
* Human approval before any experiment executes; only allowlisted fixtures run; protocol versions are never overwritten.
* A reported fix never resolves a finding; only a valid retest of the revised version does. Nothing is deployed, patched or rotated by the platform.
* Attack assessments never derive breaking time from signing/verification speed, never extrapolate toy results, never date quantum attacks.
