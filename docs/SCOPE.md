# Scope: real, imported, simulated, unavailable, out of scope

## Real (executed and tested in this repository)
| Area | What runs |
|---|---|
| Import | JSON manifest + source snapshot (.py or .zip). Static AST compatibility check against the adapter interface and import allowlist; private-key formats rejected; nothing executes on import. |
| Core test | `signature_library` fixture: valid signatures accepted; modified message, wrong key, random/corrupted/truncated/trailing/empty/zero signatures rejected; RFC 8032 §7.1 Ed25519 test vector verified and reproduced; sign/verify latency distributions, throughput, signature and key sizes, tracemalloc peak (definition stated). Works with catalog profiles (Ed25519, ECDSA P-256, RSA via `cryptography`/OpenSSL; ML-DSA via pure-Python reference) and customer adapter modules. |
| Platform sandbox | Subprocess with `unshare -rn` network namespace (or interpreter socket block when unavailable, recorded on the run), CPU/memory/process rlimits, `python -I`, empty environment, read-only staged snapshot, pinned platform dependencies only. |
| Customer-side runner | `iel_tools/runner.py`: runs the same versioned fixtures locally and emits a DSSE-wrapped in-toto bundle signed with a local Ed25519 key. |
| Bundle import | Signature + expected signer (trust policy), artifact digests, schema, project/implementation/test binding, duplicate (`run_id`) and stale flags, receipt time vs runner-reported time, ingestion-receipt countersignature, original envelope preserved. |
| Standalone verifier | `iel_tools/verify.py` with only `cryptography` as dependency. |
| Labels | imported / hash_checked / signature_verified / independently_replayed (platform replay of an imported run). |
| Autoresearcher | Rule-based extraction from submitted documents (treated as data), inventory matching, "Propose experiments" producing complete proposals; reviewer approval freezes versioned protocols; amendments create new versions. |
| Allowlisted experiments | `malformed_input_sweep` (against the customer adapter) and `toy_factoring` (synthetic ≤64-bit moduli). Nothing else executes; AI-generated code never runs. |
| Recommendations & handoff | Rule-built recommendation with evidence refs, authoritative guidance, retest plan; JSON/HTML engineering handoff; compliance evidence template (PCI DSS v4.0.1 12.3.3, EU 2024/1774 Art. 6(4)-(5)) with not_mapped / not_applicable / insufficient_evidence statuses and the required disclaimer. |
| Versioned retest | Import revised version linked to a recommendation → awaiting_retest → retest evaluation (resolved within tested scope / still failing / inconclusive), comparison with limits. |
| Platform | Auth, project roles, audit with secret scrubbing, append-only runs, job queue, evidence package export with SHA-256 manifest. |

## Imported
Customer-runner bundles and unsigned existing-result documents are imported evidence. The sample project's customer bundle is
produced by the real runner at seed time with a demo key stored under `data/keys/`.

## Simulated / demonstration (labelled)
The sample project, its seeded defect (`acme-signer 1.0.0` keeps only the first 64 signature bytes), the paraphrased research
document, the published attack-cost entries and the compliance control summaries. Control mappings are provisional.

## Unavailable here
Cairn checker (no endpoint; the `cairn_verified` label is never applied), AI provider (rule-based unless `ANTHROPIC_API_KEY`
is set), Docker sandbox and the runner container image (no daemon in the build environment; untested).

## Out of scope
Repository integrations, continuous monitoring, IoT/application adapters beyond placeholders, compliance management,
automatic patching/deployment/key rotation, production readiness or tenant isolation claims, side-channel measurement.
