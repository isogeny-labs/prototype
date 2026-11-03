# Evidence attestation format, keys and the standalone verifier

## Format
Every run that produces evidence is wrapped as an **in-toto Statement v1** inside a **DSSE envelope**, signed with **Ed25519**
through the `cryptography` library (no primitives are implemented by this project). Module: `iel_tools/attest.py`.

```
Statement   {"_type": "https://in-toto.io/Statement/v1",
             "subject": [{"name": "raw_output.json", "digest": {"sha256": "…"}},
                         {"name": "test-definition:signature-library-core@1", "digest": {"sha256": "…"}},
                         {"name": "source-snapshot:adapter.py" | "adapter-source:adapter.py", "digest": {"sha256": "…"}}],
             "predicateType": "https://isogeny-labs.example/evidence/run/v1",
             "predicate": {project_id, run_id, execution_mode, implementation{name,version,source_digest,source_revision},
                           test{test_id,version,fixture,fixture_version}, runner{kind,version}, environment, commands, inputs,
                           resource_limits, results{classification,metrics,scenarios,requirement_results,failures,limitations},
                           executed_at}}
Envelope    {"payloadType": "application/vnd.in-toto+json", "payload": base64(statement),
             "signatures": [{"keyid": sha256(raw Ed25519 public key), "sig": base64(Ed25519(PAE))}]}
PAE         "DSSEv1" SP len(payloadType) SP payloadType SP len(payload) SP payload
Bundle      {"format": "iel-evidence-bundle/1", "envelope": {…}, "artifacts": {"raw_output.json": base64(bytes)}}
```
Subjects may be **attached** (present in `artifacts`, hash-checked) or **referenced by digest only** (e.g. the customer's
adapter source, which never leaves their machine). The verifier reports which is which.

## Signing identities
* **Platform** bundles (platform sandbox runs) are signed with the platform key at `IEL_PLATFORM_KEY_PATH`
  (default `data/keys/platform_ed25519.pem`, mode 0600, created on first start, gitignored). Its public key is shown at
  Evidence → Trusted keys and `GET /api/platform-key`.
* **Customer-runner** bundles are signed with the runner's key (`python -m iel_tools.runner keygen`). The customer registers
  the PUBLIC key in the project (owner role). Private keys are never uploaded; uploads containing private-key formats are rejected.
* When the platform imports a customer bundle it **countersigns an ingestion receipt** (predicateType
  `…/evidence/ingestion-receipt/v1`) over the digest of the customer envelope. The receipt says the platform received and
  stored the envelope and what it verified. It is **not** an independent endorsement; the original envelope is preserved unchanged.

## Trust policy
Verification succeeds only for a signature by a key in the **explicitly supplied** trust set: the project's active
`customer_runner` keys plus the platform-wide platform key. A key included inside a bundle is never trusted.
What a valid signature establishes: integrity of the statement and attached artifacts, and attribution to the key holder.
What it does not establish: that the reported environment or execution was genuine, or that the implementation is secure.

## Distribution, rotation, revocation
* Distribute public keys out-of-band (copy the PEM from the UI or from `runner_key.pem.pub` into your verifier trust file).
* Rotate a runner key: `keygen` a new key, register the new public key, then **revoke** the old one in Evidence → Trusted keys.
  Revoked keys are kept as records; bundles previously imported under them stay imported with their history.
* Rotate the platform key: point `IEL_PLATFORM_KEY_PATH` at a new key file and restart; the new public key is auto-registered.
  Revoke the old `TrustedKey` record. Verifiers must be given the new public key.
* Revocation is a trust-policy change; it does not retroactively alter stored bundles.

## Standalone verifier
```
python -m iel_tools.verify bundle.json --trusted-key platform.pub --trusted-key runner_key.pem.pub [--json]
```
Checks structure, signature + expected signer, attached-artifact digests, and reports missing artifacts, unsupported
formats and failed checks; exit 0 only when every check passes. It runs without a platform account.

## Evidence labels (separate, composable; none means "secure" or "compliant")
| label | meaning |
|---|---|
| imported | provenance: the evidence came from outside the platform sandbox |
| hash_checked | attached artifact digests matched the statement subjects |
| signature_verified | DSSE signature verified against the expected signer under the trust policy |
| cairn_verified | an identified Cairn checker accepted a specified claim — never applied unless a Cairn endpoint is configured (none here) |
| independently_replayed | a separate platform execution reproduced the specified result (scenario outcomes) |
