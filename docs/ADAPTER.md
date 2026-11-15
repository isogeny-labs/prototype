# The adapter: how Evidence Lab talks to software under test

Software that signs things is tested through one tiny command-line contract. The program is
started once per call with a command word, reads one JSON object on standard input, writes
one JSON object on standard output and exits.

Two kinds of program speak it. Our own demo components (`acme-sign` 1.4.2 and 1.4.3, and the
deliberately broken controls) speak it directly. Since phase 4c, short wrappers also speak it
for real crypto libraries written by others: Java (OpenJDK), python-ecdsa, elliptic (npm) and
OpenSSL. A wrapper only translates; the library does the crypto (see "Writing a wrapper for a
real library" below). Real libraries run only in isolated mode (Docker). Uploading your own
software is not part of this version.

Start with the acme-sign description: it is the simple case. The later sections add what a
wrapper for a real library can also do.

## The contract

```
python acme_sign.py <command>          # command: keygen | sign | verify | info | bench
python openssl_adapter.py <command>    # a real library's wrapper also knows: encaps | decaps
```

- Input: one JSON object on standard input. Empty input means `{}`.
- Output: one JSON object on standard output, then exit code 0.
- Byte strings (keys, messages, signatures) are lowercase hex text.
- On a problem the program prints `{"error": "<short text>"}` and exits with code 1 (bad
  input) or 2 (unknown command). It never repeats its input in an error, because the input
  may hold a test private key.
- Since phase 4c, every call may carry an optional `"algorithm"` field. When it is left out the
  answer is ECDSA P-256, so everything above works unchanged. Only OpenSSL offers more:
  `"ML-DSA-65"` (signatures) and `"ML-KEM-768"` (key exchange).
- When the library itself says no to an input (a bad key, a wrong length), a wrapper that can
  tell answers `{"refused": true, "note": "<the library's reason>"}` with exit code 0. That is
  an answer, not a mistake in the call (see "How a library says no").
- Keys are throwaway **test keys**. Never give it a real private key.

| Command | Input | Output |
|---|---|---|
| `info` | `{}` | name, version, algorithm, hash, signature format, public key format, the commands it supports |
| `keygen` | `{}` | `{"private_key": "<64 hex>", "public_key": "04<128 hex>"}` |
| `sign` | `{"private_key": "<hex>", "message": "<hex>"}` | `{"signature": "<hex>"}` |
| `verify` | `{"public_key": "<hex>", "message": "<hex>", "signature": "<hex>"}` | `{"valid": true}` or `{"valid": false}` |
| `bench` | `{"repeats": 20, "message": "<hex>", "private_key": "<hex, optional>", "public_key": "<hex, optional>"}` | its own timings and sizes (below) |
| `encaps` | `{"algorithm": "ML-KEM-768", "public_key": "<hex>"}` | `{"ciphertext": "<hex>", "shared_secret": "<hex>"}` (key exchange; OpenSSL only) |
| `decaps` | `{"algorithm": "ML-KEM-768", "private_key": "<hex>", "ciphertext": "<hex>"}` | `{"shared_secret": "<hex>"}` (key exchange; OpenSSL only) |

Every command also takes `"algorithm"` (above). Optional inputs that replay an official test
case exactly are listed in "Key exchange (ML-KEM-768)" and "ML-DSA-65 inputs" below. A verify
answer may carry an optional `"note"` beside `{"valid": false}`.

For `acme-sign` the algorithm is ECDSA on P-256 with SHA-256. The message is the raw
message (the program hashes it itself). The signature is DER. The public key is the
uncompressed point, `04 || X || Y` (65 bytes).

### bench

`bench` makes the program sign and verify many times **inside one run** and report how long
each took, measured with its own clock. That way the time to start the program is not
counted, only the signing and verifying.

- `repeats`: 1 to 1000 (default 100).
- `private_key`: optional. Without it the program makes its own test key.
- It first does 2 untimed warm-up rounds. Then, `repeats` times: time one `sign`, then time
  one `verify` of that signature.
- `sign_ms` and `verify_ms` each hold exactly `repeats` numbers, in milliseconds.
- The private key is never part of the output.
- A wrapper that cannot work out a public key from a private one (Java) uses the `public_key`
  it is handed, when both halves come together, so two versions are timed on the same key.
  The batch driver always sends both.

## A complete example

Run from the repository root. `PY` is the app's Python.

```
PY=backend/.venv/bin/python
ACME=demo/components/acme-sign-1.4.3/acme_sign.py
```

**1. Ask what it is**

```
$ echo '{}' | $PY $ACME info
{"name": "acme-sign", "version": "1.4.3", "algorithm": "ECDSA P-256", "hash": "SHA-256", "signature_format": "DER", "public_key_format": "uncompressed point, hex (04 || X || Y)", "commands": ["keygen", "sign", "verify", "info", "bench"]}
```

**2. Make a throwaway test key**

```
$ echo '{}' | $PY $ACME keygen
{"private_key": "<64 hex characters: a throwaway test key, not shown here>", "public_key": "0406f44a164b0df0b087faa32d51193f0cc234c385ecf5be922cf12b7d9ae8f1de05285dae0f954361e936dd64f672a817162e873917172def3346532eaecb89e1"}
```

**3. Sign a message** (the message here is the text "Acme Pay demo token 0001: pay 10.00 to account 12345" as hex)

```
$ echo '{"private_key": "<the test key from step 2>", "message": "41636d65205061792064656d6f20746f6b656e20303030313a207061792031302e303020746f206163636f756e74203132333435"}' | $PY $ACME sign
{"signature": "304402201d53ce9c9b6946f0b87eeca3dff8bcf743daf2adae5d33b99fa2c78d530cb71e02203b55f88ba566e93ff378a51569cdb1cc16f4a459f47bf5f064515472b4b72f8d"}
```

**4. Verify it** (this one can be pasted as it is: it needs no private key)

```
$ echo '{"public_key": "0406f44a164b0df0b087faa32d51193f0cc234c385ecf5be922cf12b7d9ae8f1de05285dae0f954361e936dd64f672a817162e873917172def3346532eaecb89e1", "message": "41636d65205061792064656d6f20746f6b656e20303030313a207061792031302e303020746f206163636f756e74203132333435", "signature": "304402201d53ce9c9b6946f0b87eeca3dff8bcf743daf2adae5d33b99fa2c78d530cb71e02203b55f88ba566e93ff378a51569cdb1cc16f4a459f47bf5f064515472b4b72f8d"}' | $PY $ACME verify
{"valid": true}
```

**5. A signature that must be rejected: r = 0, s = 0**

```
$ echo '{"public_key": "0406f44a164b0df0b087faa32d51193f0cc234c385ecf5be922cf12b7d9ae8f1de05285dae0f954361e936dd64f672a817162e873917172def3346532eaecb89e1", "message": "41636d65205061792064656d6f20746f6b656e20303030313a207061792031302e303020746f206163636f756e74203132333435", "signature": "3006020100020100"}' | $PY $ACME verify
{"valid": false}
```

The same call on `demo/components/acme-sign-1.4.2/acme_sign.py` answers `{"valid": true}`.
That is the one planted bug of the demo (no check that r and s are between 1 and n-1), and
it is what the "Bad signatures" and "Official test vectors" tests catch.

**6. Measure its own speed**

```
$ echo '{"repeats": 3, "message": "616263"}' | $PY $ACME bench
{"repeats": 3, "warmups": 2, "clock": "time.perf_counter", "sign_ms": [6.9532, 6.5688, 7.0051], "verify_ms": [13.1785, 13.5351, 12.5939], "signature_bytes": 71, "public_key_bytes": 65, "all_verified": true}
```

(The timings are examples from one computer; yours will differ.) `signature_bytes` is the length of the
signature made with this key and message; an ECDSA P-256 signature in this format is 70 to 72
bytes long depending on the individual signature.

**7. A mistake**

```
$ echo '{"private_key": "not hex", "message": "00"}' | $PY $ACME sign
{"error": "bad input: ValueError"}          (exit code 1)
$ echo '{}' | $PY $ACME explode
{"error": "usage: acme_sign.py keygen|sign|verify|info|bench  (JSON on stdin, JSON on stdout)"}          (exit code 2)
```

## Key exchange (ML-KEM-768)

Only the OpenSSL wrapper offers this. Every call carries `"algorithm": "ML-KEM-768"`. The
sizes are the ones in the standard (FIPS 203) and in the wrapper: public key 1184 bytes,
ciphertext 1088 bytes, shared secret 32 bytes, private key 64 bytes as a seed or 2400 bytes
expanded (`decaps` accepts either form).

**This section shows the shape of each answer, not a recorded run.** Long values are written as
`<N hex characters>`, where N is twice the byte count. Private keys and shared secrets are never
shown, here or anywhere in the app. All of these run inside the OpenSSL image, which has no
network:

```
IMG=<the image tag that  python -m app.prepare  prints for "Real library, OpenSSL">
RUN="docker run --rm -i --network none $IMG /usr/local/bin/python -I /opt/evidence-lab/real/openssl_adapter.py"
```

**1. Ask what it is**

```
$ echo '{"algorithm": "ML-KEM-768"}' | $RUN info
{"name": "openssl", "version": "3.5.9", "algorithm": "ML-KEM-768", "algorithms": ["ECDSA P-256", "ML-DSA-65", "ML-KEM-768"], "hash": "built in (SHA-3)", "signature_format": "none: a key exchange", "public_key_format": "FIPS 203 encapsulation key, 1184 bytes", "commands": ["keygen", "sign", "verify", "info", "bench", "encaps", "decaps"], "library": "<OpenSSL's own version line>"}
```

**2. Make a throwaway test key pair**

```
$ echo '{"algorithm": "ML-KEM-768"}' | $RUN keygen
{"public_key": "<2368 hex characters>", "private_key": "<hex characters: a throwaway test key, not shown here>"}
```

To replay an official case, add `"seed": "<128 hex characters>"` (the 64-byte seed). The same
seed always gives the same key pair.

**3. Encapsulate: make a shared secret and the ciphertext that carries it**

```
$ echo '{"algorithm": "ML-KEM-768", "public_key": "<the public key from step 2>"}' | $RUN encaps
{"ciphertext": "<2176 hex characters>", "shared_secret": "<64 hex characters: not shown here>"}
```

To replay an official case, add `"randomness": "<64 hex characters>"` (the 32 random bytes the
standard feeds in). The same public key and randomness always give the same answer.

**4. Decapsulate: the other side recovers the same secret**

```
$ echo '{"algorithm": "ML-KEM-768", "private_key": "<the test key from step 2>", "ciphertext": "<the ciphertext from step 3>"}' | $RUN decaps
{"shared_secret": "<64 hex characters: the same as in step 3>"}
```

`private_key` may be the 64-byte seed (128 hex characters) or the 2400-byte expanded key.

**5. An input the library must refuse** (a public key of the wrong length)

```
$ echo '{"algorithm": "ML-KEM-768", "public_key": "00"}' | $RUN encaps
{"refused": true, "note": "OpenSSL did not accept the public key: <OpenSSL's own reason>"}          (exit code 0)
```

The standard also requires a refusal for a public key that holds a number that is too large,
and for an expanded private key whose built-in fingerprint is wrong. The Key exchange exam
puts each of these to the library, and its deliberately broken control skips exactly these two
checks.

## ML-DSA-65 inputs

`sign` and `verify` with `"algorithm": "ML-DSA-65"` (OpenSSL only; FIPS 204, public key 1952
bytes, signature 3309 bytes) take these optional inputs. They exist so that official test cases
can be replayed exactly. All are left out for an ordinary call.

| Input | What it is for |
|---|---|
| `seed` (on `keygen`) | 32 bytes (64 hex characters) that fix the key pair, so the key is the published one. Without it the library picks its own. |
| `context` (`sign`, `verify`) | The short context text (hex) that the standard lets a signer bind into a signature. Sign and verify must use the same one. |
| `deterministic` (`sign`) | `true` asks for the standard's no-randomness signing mode. |
| `randomness` (`sign`) | The 32 random bytes (64 hex characters) the standard feeds into signing. With it, the same key and message always give the same signature. It takes the place of `deterministic`. |
| `interface` (`sign`, `verify`) | `external` (the default: the library prepares the message itself), `internal` (the message is handed over in the standard's internal form) or `mu` (a value already worked out from the message is handed over). |

`private_key` for ML-DSA-65 may be the 32-byte seed or the 4032-byte expanded key.

## How a library says no

A wrapper answers a bad signature or a bad input in one of these ways. The rule for a signature
check (the owner's decision): **an error raised by the library while it checks a signature
counts as "not accepted"**, so the wrapper answers `{"valid": false}`. The app asks only
whether a library accepted a signature, and a crash is not an acceptance.

| What the library did | What the wrapper answers | Note |
|---|---|---|
| Said "bad signature" in its own words (Java `SignatureException`, python-ecdsa's own bad-signature errors, elliptic's own plain `Error`) | `{"valid": false}` | none |
| Stopped with a general error that is not its "bad signature" answer (a crash) | `{"valid": false, "note": "general error: <ClassName>"}` | The app shows this under **Also noticed**. It never sets a result. |
| Refused the input itself (OpenSSL: a bad key, a wrong length) | `{"refused": true, "note": "<the library's reason>"}`; a `verify` with a bad public key answers `{"valid": false, "note": "<the library's reason>"}` | The reason is cut to 120 characters. |

Notes are plain text and never repeat the input. A call that is itself wrong (not hex, a
missing field) still answers `{"error": "bad input: <ClassName>"}`.

## Writing a wrapper for a real library

A wrapper is one small file that turns the adapter's JSON into the library's own calls and back.
It holds **no crypto of its own**: every key, signature and check is made by the library. If a
wrapper had to compute something itself, the test would be testing our code, not the library.

The four wrappers that exist are the pattern. Each family has its own folder under
`demo/real-libraries/` and its own container image:

| Folder | Wrapper |
|---|---|
| `demo/real-libraries/openssl/` | `openssl_adapter.py` (also `pq_controls.py`, the broken copies of the post-quantum exams) |
| `demo/real-libraries/java/` | `EcdsaAdapter.java` |
| `demo/real-libraries/python-ecdsa/` | `ecdsa_adapter.py` |
| `demo/real-libraries/elliptic/` | `elliptic_adapter.js` |

Each folder holds the wrapper, a `Dockerfile` and a `subjects.json`.

**`subjects.json`** is the image's own fixed table. It maps a subject key to the whole command
line that comes before the command word, with absolute paths inside the image, for example
`"openssl-3.5.9": ["/usr/local/bin/python", "-I", "-X", "pycache_prefix=/scratch/pyc", "/opt/evidence-lab/real/openssl_adapter.py"]`.
There is one entry per version. There is also one `control-slow:<subject>` entry per version:
the same command line with `--slow` added, which adds 6 ms to every timed step of `bench`, so
the speed test has a control that must be flagged as slower. The batch driver reads this table
only when it is started with `--real`.

**The `Dockerfile`** follows these rules:

- The last stage starts from the pinned Python base image (`PYTHON_BASE`, set by the build).
- No step needs the network. The build runs with `--network none`.
- The library's own files are copied in from a pinned source: another pinned image (OpenSSL's
  `libcrypto`, the two Temurin JDKs, Node), or files that the prepare step downloaded and
  checked by fingerprint (the python-ecdsa wheels, the elliptic npm files). They are never
  fetched during the build.
- Our harness (`components/`) and the family's folder (`real/`) are copied to
  `/opt/evidence-lab/components/` and `/opt/evidence-lab/real/`.
- It ends with `USER 65534:65534`, so nothing runs as root.

**Registering it.** The library, its versions, the pins of its files and its public advisories are
listed in `backend/app/real_libraries.py` (`FAMILIES`, `ADVISORIES`, `LIBRARIES`). Nothing in an
uploaded file can add to those tables. Only `cd backend && .venv/bin/python -m app.prepare`
downloads and builds the images; the app itself never does.

**Trying it by hand**, in isolated mode:

```
cd backend && .venv/bin/python tools/try_real_library.py openjdk 17.0.2
```

It goes through the same runner and batch driver as the app: it asks the wrapper what it is,
does one keygen, sign and verify round trip (checked by the app's reference library), counts how
many of the 484 Wycheproof ECDSA P-256 cases and of our 16 bad-signature cases the library gets
wrong, prints the notes the wrapper passed on, and runs a short speed test next to its slowed
control. It decides nothing and stores nothing.

## The demo components

| File (under `demo/components/`) | What it is |
|---|---|
| `acme-sign-1.4.2/acme_sign.py` | The demo component with one planted bug: `verify` never checks that r and s are in the range 1 to n-1. Everything else is strict, including the signature format. |
| `acme-sign-1.4.3/acme_sign.py` | The same file plus the range check. Nothing else differs except the version number it reports. |
| `controls/accept_all.py` | A deliberately broken control: `verify` answers `{"valid": true}` to anything. Every signature test also runs it, and it must fail. |
| `controls/slow.py` | A deliberately slowed control: `slow.py <component file> <command>` is that component with 6 ms added to every sign and every verify. The speed test must flag it as slower. |
| `harness/driver.py` | Our batch driver (below). |

All of them use the Python standard library only.

The real-library wrappers are not under `demo/components/`. They are in
`demo/real-libraries/<family>/` (see "Writing a wrapper for a real library") and exist only
inside their own images, which only isolated mode can run.

## The batch driver (how the app runs many calls)

A test needs hundreds of calls. The app starts **one** program per test run: our own driver,
`demo/components/harness/driver.py`. The driver reads one JSON job on standard input, runs
the component command line once per case (each call is still its own separate process,
exactly as above), and writes one JSON line per answer. Its last line is always
`{"done": true, "lines": <count>}`; without that line the app treats the run as failed.

- In **demo mode** the driver is a local process with a time limit.
- In **isolated mode** the driver is the one process of a locked-down container: no network,
  read-only files, a small scratch folder, not root, limited memory, CPU and processes, and
  nothing from this computer mounted into it. The container is killed and removed at the time limit.

What the driver can run is a fixed table inside it. A job only names an entry of that table
and carries test data; nothing in a job is ever used as a file path or a program name.
A job that does not fit is refused with one line `{"refused": "<why>"}` (exit code 2) before
anything runs.

**`--real`.** In a real-library image the driver is started with the one extra word `--real`.
Only then does it also read that image's own fixed table, `/opt/evidence-lab/real/subjects.json`
(the `subjects.json` of the family, written into the image when it was built). A job names a
subject key from that table, such as `openssl-3.5.9`, the same way it names `acme-sign-1.4.2`.
If the table cannot be read the driver answers `{"refused": ...}` and stops.

Subject names: `acme-sign-1.4.2`, `acme-sign-1.4.3`, `control-accept-all`,
`control-slow:acme-sign-1.4.2`, `control-slow:acme-sign-1.4.3`. In a real-library image: the
keys of its `subjects.json`, for example `openjdk-17.0.2`, `python-ecdsa-0.13.3`,
`elliptic-6.5.7`, `openssl-3.5.9`, their `control-slow:` versions, and for OpenSSL also
`control-pq-wrong-answer` and `control-pq-skip-key-check`.

| Job | Lines written |
|---|---|
| `{"op": "call", "subject": S, "command": "info", "input": {}}` (a plain `call` may ask only `keygen`, `sign`, `verify`, `info` or `bench`) | `{"subject": S, "command": "info", "rc": 0, "out": {...}, "error": null, "ms": 21.4}`. A `keygen` answer has its private key replaced by `"[test private key withheld]"`. |
| `{"op": "verify_batch", "subjects": [S1, S2], "cases": [{"id": "168", "public_key": "..", "message": "..", "signature": ".."}]}` | For each subject, for each case in order: `{"subject": S, "id": "168", "rc": 0, "valid": true, "error": null, "ms": 30.9}`. `valid` is `true` or `false` only when the component gave a clear yes or no; otherwise it is `null` and `error` says why (`"timeout"`, `"bad output"`, or the component's own error text). Takes an optional `"algorithm"`. When the wrapper passes on a note, the line also has `"note"` (cut to 120 characters). |
| `{"op": "bench_rounds", "keygen_with": S, "subjects": [S1, S2, S3], "rounds": 10, "repeats": 20, "message": "<hex>"}` | First `{"keygen": S, "rc": 0, "public_key_bytes": 65}`. Then, per round and per subject: `{"round": 0, "subject": S, "rc": 0, "out": {the bench answer}, "error": null}`. Even rounds go S1, S2, S3; odd rounds go S3, S2, S1, so no subject always runs first. Takes an optional `"algorithm"`. The public key goes to each `bench` call along with the private key. |
| `{"op": "roundtrip", "subject": S, "message": "<hex>"}` | One line per step, stopping at the first step that fails: `{"subject": S, "step": "keygen", "rc": 0, "out": {"public_key": "..", "private_key": "[test private key withheld]"}, "error": null, "ms": 25.1}`, then `"step": "sign"` with `{"signature": ".."}`, then `"step": "verify"` with `{"valid": true}`. Used by the Verify step in isolated mode. Takes an optional `"algorithm"`. |
| `{"op": "kat_batch", "subject": S, "cases": [{"id": "nist-encaps-26", "command": "encaps", "input": {...}}]}` | "Known answer" cases, for the two post-quantum exams. `command` is one of `keygen`, `encaps`, `decaps`, `sign`, `verify`. For each case, in order: `{"subject": S, "id": "nist-encaps-26", "rc": 0, "error": null, "declined": false, "valid": null, "answer_sha256": "<64 hex>", "ms": 40.2}`. See below. |
| `{"op": "kem_roundtrip", "subject": S, "algorithm": "ML-KEM-768", "peer_public_key": "<hex>"}` | One ordinary key exchange, for the Verify step. One line per step, stopping at the first that fails: `"keygen"` (`public_key_bytes`, private key withheld), `"encaps"` (`ciphertext_bytes`, `shared_secret_bytes`), `"decaps"` (`same_secret`: true or false), then `"encaps_to_app"`: it encapsulates to a public key the app made with its own reference library and writes the `ciphertext` and the SHA-256 of the shared secret, so the app can confirm it independently. No key or shared secret is written out. |

Limits: 10 seconds per call (60 for `bench`), at most 5000 cases, at most 4 subjects, 50
rounds, 1000 repeats, and hex text of at most 40000 characters per value (`MAX_HEX`; a
post-quantum key or signature is long). In `verify_batch` a few calls run at the same time to keep a 484-case
run short; `bench_rounds` always runs one call at a time, because it measures time.

**`kat_batch` never writes out an answer.** A key, a shared secret or a signature that a library
makes is not put on any line. For each case the line says only:

- `declined`: `true` when the library itself refused the input (a bad key, a wrong length), else
  `false`. It is not called `refused` on purpose: a line that has `refused` on it means the
  driver refused the whole job (`{"refused": "<why>"}`), and the two must never be mixed up.
- `valid`: for `verify`, `true` or `false` (yes or no); otherwise `null`.
- `answer_sha256`: for `keygen`, `encaps`, `decaps` and `sign`, the SHA-256 of the answer. It is
  taken over the answer's fields in a fixed order, each written as `name=<lowercase hex>` and
  joined by newlines (`keygen`: `public_key`, `private_key`; `encaps`: `ciphertext`,
  `shared_secret`; `decaps`: `shared_secret`; `sign`: `signature`). The app holds the same
  fingerprint for each published answer and compares the two. If the library declined, it is `null`.
- `note`, when the wrapper passed one on.

A case input may hold only hex text for `seed`, `public_key`, `private_key`, `message`,
`signature`, `ciphertext`, `randomness` and `context`, an `algorithm` from the fixed list, an
`interface` of `external`, `internal` or `mu`, and `deterministic` as true or false. Anything
else refuses the whole job.

The test key for `bench_rounds` is made once inside the driver, handed to each `bench` call
on its standard input, and never written to any line. The same holds for `roundtrip`: its test
key goes only to the `sign` call's standard input.

Example:

```
$ echo '{"op": "verify_batch", "subjects": ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all"], "cases": [{"id": "r0-s0", "public_key": "0406f44a164b0df0b087faa32d51193f0cc234c385ecf5be922cf12b7d9ae8f1de05285dae0f954361e936dd64f672a817162e873917172def3346532eaecb89e1", "message": "00", "signature": "3006020100020100"}]}' | $PY demo/components/harness/driver.py
{"subject": "acme-sign-1.4.2", "id": "r0-s0", "rc": 0, "valid": true, "error": null, "ms": 31.2}
{"subject": "acme-sign-1.4.3", "id": "r0-s0", "rc": 0, "valid": false, "error": null, "ms": 28.7}
{"subject": "control-accept-all", "id": "r0-s0", "rc": 0, "valid": true, "error": null, "ms": 17.9}
{"done": true, "lines": 3}
```
