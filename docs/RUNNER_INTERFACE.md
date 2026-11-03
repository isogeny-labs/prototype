# Test fixtures, execution modes and the result schema

## Fixture protocol
A fixture is a standalone script in `backend/fixtures/`: JSON params on stdin, one JSON result document on stdout.
The same scripts run in the platform sandbox, in the customer-side runner and (untested) in the container harness.

| fixture | purpose | allowlisted for experiments |
|---|---|---|
| `signature_library` | core signature test (correctness, malformed input, vectors, timing, sizes, memory) | no (core test) |
| `malformed_input_sweep` | characterise accepted malformed signature encodings | yes (needs adapter) |
| `toy_factoring` | Pollard rho on synthetic ≤64-bit semiprimes (workflow demonstration) | yes (synthetic) |

Adapter interface for customer snapshots (`adapter.py`): `ADAPTER` metadata, `keygen()`, `sign(sk, msg)`, `verify(pk, msg, sig)`,
`public_key_bytes(pk)`, optional `public_key_from_bytes`, `private_key_from_bytes` (needed for official vectors).
Allowed imports: cryptography, hashlib, hmac, secrets, struct, typing, dataclasses, base64, json, math, dilithium_py, os.urandom.

## Execution modes (same test definitions, same result schema)
| mode | provenance | who runs | labels |
|---|---|---|---|
| `platform_sandbox` | measured | platform, isolated subprocess | (platform-signed bundle) |
| `customer_runner` | measured | customer, locally, signed bundle | imported, hash_checked, signature_verified (+ independently_replayed after a matching platform replay) |
| `imported_results` | imported / illustrative | nobody (document import) | imported |
| `platform_sandbox` with runner `cryptanalysis_suite` | measured | platform, bounded `crax` subprocess (typed parameters, fixed argv, minimal env, rlimits) | (platform-signed bundle) |

The cryptanalysis-suite tools (`suite_*` fixtures, `backend/runners/suite_tools.py`) are not Python fixtures; they are
bounded adapters around the suite's JSON interface. See `SUITE_INTEGRATION.md`. They never load the customer adapter.

## Result document (schema version 1)
```json
{"fixture": "signature_library", "fixture_version": "2.0.0", "test_id": "signature-library-core", "status": "completed|failed",
 "adapter": {"kind": "module", "name": "acme-signer", "version": "1.0.0", "algorithm": "Ed25519", "library": "…"},
 "environment": {...}, "repeat_count": 100, "parameters": {...},
 "scenarios": [{"id": "trailing_byte", "name": "…", "expected": "reject", "observed": "accept", "pass": false, "class": "rejection"}],
 "metrics": {"verify_time_ms_median": 0.03, "signature_bytes": 64, "functional_pass": 0, "official_vectors": "pass"},
 "metric_definitions": {"verify_peak_alloc_kb": "…"}, "raw": {...}, "failures": [], "exclusions": [], "limitations": []}
```
Classification derived by the platform: `passed_defined_checks` (all scenarios and applicable requirements pass), `failed`,
`inconclusive` (did not complete), `unsupported` (adapter cannot execute), `awaiting_review`, `not_tested`.
