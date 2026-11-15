# ctcrypto: constant-time CNSA 2.0 algorithm suite

A new Rust library for the algorithms CNSA 2.0 names, written to be constant time in its secrets.
`no_std`, no allocation, no dependencies, no `unsafe` in the library.

Status: research prototype, written 2026-11-15. **Not validated**: no CAVP certificate, no FIPS 140-3
validation, no third-party review. Do not deploy it on that basis.

## What is in it

| Module | Algorithm | Interface | Checked against |
|---|---|---|---|
| `mlkem` | ML-KEM-1024 (FIPS 203) | `keygen_internal`, `encaps_internal`, `decaps` | NIST ACVP: 80 of 80 ML-KEM-1024 cases; 300 cases from RustCrypto `ml-kem` |
| `mldsa` | ML-DSA-87 (FIPS 204) | `keygen_internal`, `sign`, `sign_internal`, `sign_mu`, `verify`, `verify_internal`, `verify_mu` | NIST ACVP full files: 25 keyGen, 90 sigGen, 45 sigVer (committed subset: 25, 60, 45) |
| `aes` | AES-256, AES-256-GCM (96-bit nonce) | `Aes256`, `gcm::seal`, `gcm::open` | NIST ACVP AES-ECB-256: 830 cases and the Monte Carlo tests; Wycheproof AES-256-GCM: 66 cases; 220 cases from Python `cryptography` |
| `lms` | LMS / HSS verification (RFC 8554, SP 800-208) | `verify_lms`, `verify_hss` | RFC 8554 and RFC 9858 vectors; NIST ACVP: 78 cases; 86 cases from `pyhsslms` |
| `xmss` | XMSS / XMSS^MT verification (RFC 8391, SP 800-208) | `verify`, `verify_mt` | 128 signatures from the XMSS reference C code |
| `sha2` | SHA-256, SHA-384, SHA-512 | incremental and one-shot | CPython `hashlib`, 30 boundary lengths |
| `sha3` | SHA3-256, SHA3-512, SHAKE128, SHAKE256 | sponge | CPython `hashlib`, 30 boundary lengths |

Vector origins and hashes: [`tests/vectors/SOURCES.md`](tests/vectors/SOURCES.md).

```bash
cargo test --release            # all known-answer, differential and negative tests
ctcheck/run.sh                  # constant-time check (needs valgrind and its headers)
```

## Constant-time evidence

The rules are in `src/lib.rs`: no secret-dependent branch, index, loop bound or division; no tables indexed by
secrets (the AES S-box is computed, not looked up); every point where a secret-derived value becomes public is a
`ct::declassify` call with its reason.

The check is made on the compiled release binary, not on the source. `ctcheck` marks secret inputs as undefined
and runs each operation under valgrind memcheck, which then reports every branch and memory address that depends
on a secret. A disassembly scan looks for division instructions in library code.

Result of the last run (`evidence/ctcheck-report.json`, x86-64, rustc 1.97.0, valgrind 3.22.0, 12 inputs per case):

| Case | Secret inputs | Result |
|---|---|---|
| three leaky controls (secret loop bound, secret table index, `==` on secrets) | | flagged, as required |
| SHA-256/384/512, SHAKE256, `ct::eq` / `ct::cmov` | message, both operands | clean |
| AES-256 block encrypt and decrypt | key, block | clean |
| GCM seal; GCM open (valid and forged tag) | key, plaintext | clean |
| ML-KEM keygen, encaps, decaps (valid and modified ciphertext) | d, z, m, decryption key, z | clean |
| ML-DSA keygen, sign (deterministic and hedged) | xi, K, s1, s2, t0, rnd | clean |
| division instructions in library code | | none |

What this does **not** show:

- Only this compiler, these flags and x86-64 were checked. Another compiler version or target can compile the
  same source differently; rerun `ctcheck/run.sh` for each.
- Valgrind sees branches and addresses. It does not see instructions whose duration depends on operand values;
  only division is covered, by the scan. The code assumes integer multiplication is constant time.
- No statistical timing measurement (dudect-style) and no power or EM side-channel work. Nothing is masked.
- Secrets left in registers or dead stack slots are not wiped; safe Rust cannot guarantee that.
- LMS and XMSS verification handle only public data, so they are tested for robustness, not for timing.

### Where secrets are declassified

- **ML-KEM**: the matrix seed rho; the finished encapsulation key and ciphertext; the outcome of the two input
  checks. The re-encryption comparison and the choice between the real and the implicit-rejection key are never
  declassified.
- **ML-DSA**: rho and t1 (the public key); the accept/reject bit of each ExpandS candidate; the challenge
  `c_tilde` of every attempt; the one-bit outcome of each of the four signing rejection checks, each computed
  over the whole vector; z and the hint once an attempt is accepted.
- **AES-GCM**: the accept/reject bit of the tag comparison.

## Limits

- No random number generator. The caller supplies all randomness (FIPS 203/204 `*_internal` interfaces), so key
  generation and encapsulation are only as good as the caller's DRBG.
- Not implemented: HashML-DSA (pre-hash), other ML-KEM/ML-DSA parameter sets, GCM nonces other than 96 bits,
  LMS/XMSS key generation and signing, the SHA-512 and SHAKE128 XMSS sets (not in SP 800-208).
- Implemented but without an independent vector: XMSS h=20; XMSS^MT 40/2 and 60/3; LMS H25, and LMS H20 except
  SHA-256/192; signatures at the last leaf index. They share code with tested sets and differ in table entries.
- NIST publishes no ACVP sample vectors for AES-256-GCM or for XMSS; those rest on Wycheproof, Python
  `cryptography` and the XMSS reference code.
- Speed was not a goal. AES-256-GCM seal measured about 10.7 MiB/s on one cloud VM, a single uncontrolled run.
  There is no AES-NI path, because the library forbids `unsafe`.
- Stack: ML-DSA signing needs roughly 123 KiB in a release build (about 231 KiB in debug).
- The modules were written by AI agents in one session. The lead session reran every test, read the ML-KEM
  decapsulation and ML-DSA signing paths, and ran the harness; it did not line-by-line review all 4,100 lines.
