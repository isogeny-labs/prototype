# iel_tools — customer-side runner and standalone verifier

Portable, dependency-light tools. Requirements: Python 3.11+ and `pip install cryptography` (the runner also needs
`dilithium-py` only if your adapter uses the ML-DSA reference profile).

## Customer-side runner (execution mode `customer_runner`)
```
python -m iel_tools.runner keygen --out runner_key.pem        # private key stays local (mode 600); register runner_key.pem.pub in the project
python -m iel_tools.runner run --project <project_id> --impl-name acme-signer --impl-version 1.0.0 \
    --adapter ./adapter.py --test signature-library-core --test-version 1 --key runner_key.pem --out bundle.json
```
Upload `bundle.json` in Tests & Benchmarks → Customer-side runner. The platform verifies the DSSE signature against the
project's trusted runner keys, checks artifact digests, schema and project/implementation binding, flags duplicates
(same run_id) and stale submissions, and records receipt time separately from the runner-reported execution time.
The adapter source is referenced by digest; it is not uploaded.

Container harness (untested in the build environment): `docker build -f iel_tools/Dockerfile -t iel-runner .` then
`docker run --rm --network none -v $PWD:/work iel-runner run --project ... --adapter /work/adapter.py --key /work/runner_key.pem --out /work/bundle.json`.

## Standalone verifier
```
python -m iel_tools.verify bundle.json --trusted-key platform.pub --trusted-key runner_key.pem.pub
```
Trust comes only from the keys you pass. The platform public key is shown in Evidence → Trusted keys (distribute it
out-of-band). See docs/ATTESTATION.md for the format, key distribution, rotation and revocation.
