# Project Wycheproof test vectors (vendored copy)

The first two files below are published test cases with known right answers, from Project Wycheproof.
They are copied here byte for byte so the demo runs with no internet. The app reads them as
data only (JSON), never runs anything in them, and refuses to use a file whose SHA-256
differs from the value below (the same values are pinned in `backend/app/engine/vectors.py`).

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

## Six more files (phase 4c): post-quantum

Six more Wycheproof files are stored here, unchanged and byte for byte, for the two
post-quantum exams ("Key exchange exam (ML-KEM-768)" and "Signature exam (ML-DSA-65)"). They are
read as data only, and refused if their SHA-256 differs from the value below (these values are
pinned in `backend/app/engine/pq_vectors.py`, `FILES`).

- Source: https://github.com/C2SP/wycheproof (folder `testvectors_v1/`)
- Commit: `65ca494727a52944c204441c860b039e6786b99b`
- Exact folder: https://github.com/C2SP/wycheproof/tree/65ca494727a52944c204441c860b039e6786b99b/testvectors_v1
- Licence: Apache License 2.0, copyright the Wycheproof authors, as above.

The two files in the first table stay pinned to commit `dab4ea2`, as before.

| File | Used for | Cases | SHA-256 |
|---|---|---|---|
| `mlkem_768_keygen_seed_test.json` | ML-KEM-768 key generation from a published seed | 100 | `fde5abe284396f4cb3c4610b90d680f0b57782e94c3365c97aee59e24881ebe4` |
| `mlkem_768_encaps_test.json` | ML-KEM-768 encapsulate, including public keys that must be refused | 265 | `9d4381f94c40853bba430245b94968b7390d9175aacd9f1ae4e250a71c78b713` |
| `mlkem_768_test.json` | ML-KEM-768 decapsulate, from a private key given as a seed | 201 | `c59c067ae794c343df575dd90f6f7458f51881b11a22d6e9d8677c8d9ee21e90` |
| `mlkem_768_semi_expanded_decaps_test.json` | ML-KEM-768 decapsulate, from an expanded private key, including a wrong built-in fingerprint that must be refused | 9 | `e4438ab7d4dd7b6ace7165e45aeed4403082f981f86300c8369f69d3d071060a` |
| `mldsa_65_sign_seed_test.json` | ML-DSA-65 signing from a published seed | 105 | `e26b2bb9ab8d45ed570ba6828c7e40b6fa3e1545bb8bc2c449c77531760133e0` |
| `mldsa_65_verify_test.json` | ML-DSA-65 verifying: genuine signatures to accept, forged ones to reject | 210 | `1ca235f61928421a173a171780beb00264ae9155dc33c52a11e1766cc7979034` |

The case counts are the number of tests in each file. Each exam also uses NIST ACVP files, kept
in `demo/vectors/acvp/`; NIST's notice for them is in `demo/vectors/acvp/NOTICE.md`. The exams
compare answers only: they say nothing about timing attacks.

Case numbers (`tcId`) are per file: case 168 in the ECDSA file is "r=0 and s=0"; case 168 in
the Ed25519 file is something unrelated.
