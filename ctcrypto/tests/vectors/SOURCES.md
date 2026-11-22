# Test vector sources

SHA-256 values are of the original download unless noted. The committed files are filtered subsets.

| File | Origin | SHA-256 of original |
|---|---|---|
| `mlkem_acvp.json` | usnistgov/ACVP-Server `gen-val/json-files/ML-KEM-keyGen-FIPS203/internalProjection.json` | `d7a62a2c3476957f56dd8d24f9004ea6776ccfe995ffe71a65bb9506dc9c7b1b` |
| | `ML-KEM-encapDecap-FIPS203/internalProjection.json` | `a556952ce869bb89c3a3196a701dad89647c193a34c86eafb61a9d710d5b810f` |
| `mlkem_diff_rustcrypto.json` | generated with RustCrypto `ml-kem` 0.2.3 | generated |
| `mldsa_acvp.json` | `ML-DSA-keyGen-FIPS204/internalProjection.json` | `e67ee6540d40e11506c3c4e3b1f79fc1cefcd49820db99fc61f87cc8ba463baf` |
| | `ML-DSA-sigGen-FIPS204/internalProjection.json` | `72dcaf5f69853ca267ccd16af9cb40949786aca0fcfbf05d1ebeba132b93af22` |
| | `ML-DSA-sigVer-FIPS204/internalProjection.json` | `47cdd6314c7f746d02421ffcba89d4dbc7bb875ac49e07a029fdfc26fba55437` |
| `aes_acvp.json` | `ACVP-AES-ECB-1.0/internalProjection.json` | `a804bbe1b4efbb775ec5a365245739ffaedad50f43d91b07ede26733e0f3b256` |
| `aes_gcm_wycheproof.json` | C2SP/wycheproof `testvectors_v1/aes_gcm_test.json` (key 256, nonce 96, tag 128) | `985e5ecc172e181eaf49e89508b9470dcf478002eb7e8559c707eb42dc97dfe7` |
| `aes_gcm_diff.json` | generated with Python `cryptography` 50.0.1 | generated |
| `lms_rfc8554.json` | RFC 8554 Appendix F | `d5bfdbd457dfe7bc5f67cc1f62482999c2f55bf8033f2af56da323f2ffc2c055` (RFC text) |
| `lms_rfc9858.json` | RFC 9858 Appendix A | not re-verified by the lead session |
| `lms_acvp.json` | `LMS-sigVer-1.0` and `LMS-sigVer-SP800-208` (hashes recorded inside the file) | see file |
| `lms_pyhsslms.json` | generated with `pyhsslms` 2.0.0 | generated |
| `xmss_reference.json` | generated with XMSS/xmss-reference, commit `171ccbd26f098542a67eb5d2b128281c80bd71a6` | generated |
| `hashes.json` | generated with CPython `hashlib` | generated |

ML-DSA: to run every case of the three full ACVP files, download them as `keyGen.json`, `sigGen.json`,
`sigVer.json` into a directory and set `MLDSA_ACVP_DIR` to it.

The generated files are not reproduced by the crate's tests; the generator scripts were not committed.
