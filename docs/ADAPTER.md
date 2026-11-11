# The adapter: how Evidence Lab talks to software under test

Software that signs things is tested through one tiny command-line contract. The program is
started once per call with a command word, reads one JSON object on standard input, writes
one JSON object on standard output and exits.

In this version only our own demo components speak it: `acme-sign` 1.4.2 and 1.4.3, and the
two deliberately broken controls. Uploading outside software is not part of this version.

## The contract

```
python acme_sign.py <command>          # command: keygen | sign | verify | info | bench
```

- Input: one JSON object on standard input. Empty input means `{}`.
- Output: one JSON object on standard output, then exit code 0.
- Byte strings (keys, messages, signatures) are lowercase hex text.
- On a problem the program prints `{"error": "<short text>"}` and exits with code 1 (bad
  input) or 2 (unknown command). It never repeats its input in an error, because the input
  may hold a test private key.
- Keys are throwaway **test keys**. Never give it a real private key.

| Command | Input | Output |
|---|---|---|
| `info` | `{}` | name, version, algorithm, hash, signature format, public key format, the commands it supports |
| `keygen` | `{}` | `{"private_key": "<64 hex>", "public_key": "04<128 hex>"}` |
| `sign` | `{"private_key": "<hex>", "message": "<hex>"}` | `{"signature": "<hex>"}` |
| `verify` | `{"public_key": "<hex>", "message": "<hex>", "signature": "<hex>"}` | `{"valid": true}` or `{"valid": false}` |
| `bench` | `{"repeats": 20, "message": "<hex>", "private_key": "<hex, optional>"}` | its own timings and sizes (below) |

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

## The demo components

| File (under `demo/components/`) | What it is |
|---|---|
| `acme-sign-1.4.2/acme_sign.py` | The demo component with one planted bug: `verify` never checks that r and s are in the range 1 to n-1. Everything else is strict, including the signature format. |
| `acme-sign-1.4.3/acme_sign.py` | The same file plus the range check. Nothing else differs. |
| `controls/accept_all.py` | A deliberately broken control: `verify` answers `{"valid": true}` to anything. Every signature test also runs it, and it must fail. |
| `controls/slow.py` | A deliberately slowed control: `slow.py <component file> <command>` is that component with 6 ms added to every sign and every verify. The speed test must flag it as slower. |
| `harness/driver.py` | Our batch driver (below). |

All of them use the Python standard library only.

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

Subject names: `acme-sign-1.4.2`, `acme-sign-1.4.3`, `control-accept-all`,
`control-slow:acme-sign-1.4.2`, `control-slow:acme-sign-1.4.3`.

| Job | Lines written |
|---|---|
| `{"op": "call", "subject": S, "command": "info", "input": {}}` | `{"subject": S, "command": "info", "rc": 0, "out": {...}, "error": null, "ms": 21.4}`. A `keygen` answer has its private key replaced by `"[test private key withheld]"`. |
| `{"op": "verify_batch", "subjects": [S1, S2], "cases": [{"id": "168", "public_key": "..", "message": "..", "signature": ".."}]}` | For each subject, for each case in order: `{"subject": S, "id": "168", "rc": 0, "valid": true, "error": null, "ms": 30.9}`. `valid` is `true` or `false` only when the component gave a clear yes or no; otherwise it is `null` and `error` says why (`"timeout"`, `"bad output"`, or the component's own error text). |
| `{"op": "bench_rounds", "keygen_with": S, "subjects": [S1, S2, S3], "rounds": 10, "repeats": 20, "message": "<hex>"}` | First `{"keygen": S, "rc": 0, "public_key_bytes": 65}`. Then, per round and per subject: `{"round": 0, "subject": S, "rc": 0, "out": {the bench answer}, "error": null}`. Even rounds go S1, S2, S3; odd rounds go S3, S2, S1, so no subject always runs first. |
| `{"op": "roundtrip", "subject": S, "message": "<hex>"}` | One line per step, stopping at the first step that fails: `{"subject": S, "step": "keygen", "rc": 0, "out": {"public_key": "..", "private_key": "[test private key withheld]"}, "error": null, "ms": 25.1}`, then `"step": "sign"` with `{"signature": ".."}`, then `"step": "verify"` with `{"valid": true}`. Used by the Verify step in isolated mode. |

Limits: 10 seconds per call (60 for `bench`), at most 5000 cases, at most 4 subjects, 50
rounds, 1000 repeats. In `verify_batch` a few calls run at the same time to keep a 484-case
run short; `bench_rounds` always runs one call at a time, because it measures time.

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
