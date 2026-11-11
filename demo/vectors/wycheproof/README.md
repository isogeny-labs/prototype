# Project Wycheproof test vectors (vendored copy)

These two files are published test cases with known right answers, from Project Wycheproof.
They are copied here byte for byte so the demo runs with no internet. The app reads them as
data only (JSON), never runs anything in them, and refuses to use a file whose SHA-256
differs from the value below (the same values are pinned in `backend/app/vectors.py`).

- Source: https://github.com/C2SP/wycheproof (folder `testvectors_v1/`)
- Commit: `dab4ea2ed021eb633874959ca601004f3457d911`
- Exact folder: https://github.com/C2SP/wycheproof/tree/dab4ea2ed021eb633874959ca601004f3457d911/testvectors_v1
- Licence: Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0). Copyright the Wycheproof authors. The files are unchanged.

| File | Cases | SHA-256 |
|---|---|---|
| `ecdsa_secp256r1_sha256_test.json` | 484 (174 valid, 310 invalid) | `182db4f3e230f6f9fa9f800d2a614dede30284b8e8438bbfe1171905402e9332` |
| `ed25519_test.json` | 210 (117 valid, 64 invalid, 29 acceptable) | `ea80ffebac085e21cb9d3e903e7fa2b448d96702da5b31f061d0b83b430b74b3` |

How they are used:

- `ecdsa_secp256r1_sha256_test.json` is run against the signing component under test
  (`acme-sign`), against the deliberately broken control, and against the reference library.
- `ed25519_test.json` is **not** run against `acme-sign`, because `acme-sign` only does
  ECDSA P-256. It is run against the reference library (pyca `cryptography`) only, and the
  result says so. Its 29 "acceptable" cases may be answered either way and are not counted.

Case numbers (`tcId`) are per file: case 168 in the ECDSA file is "r=0 and s=0"; case 168 in
the Ed25519 file is something unrelated.
