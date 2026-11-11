# Bad-signature cases (fixed test data)

`cases.json` is the fixed list used by the "Bad signatures" test: 16 cases for ECDSA P-256
with SHA-256. Each case has a public key, a message, a signature and the right answer.
Two are genuine signatures that must be **accepted**; fourteen are bad and must be **rejected**.

It was built **once** by `backend/tools/build_bad_signature_cases.py` with the reference
library (pyca `cryptography`) from a throwaway test key. The private key was never stored,
printed or logged, and no longer exists; only the public key is in the file. Do not rebuild
the file: a rebuild uses a new key, and the app refuses a file whose SHA-256 differs from the
value pinned in `backend/app/vectors.py`.

SHA-256 of `cases.json`: `d429e98c4618defad5761fad0129998a281943a3eec1092bfb9b7c7eac4dc216`

| Case id | What it is | Right answer |
|---|---|---|
| `good-1` | a genuine signature | accept |
| `good-2` | a second genuine signature, on another message | accept |
| `changed-message` | genuine signature, message changed afterwards | reject |
| `changed-signature` | genuine signature with one bit changed | reject |
| `cut-short` | last byte cut off (wrong length) | reject |
| `extra-byte` | one extra byte on the end (wrong length) | reject |
| `empty` | an empty signature | reject |
| `r0-s0` | r = 0, s = 0 (the bytes `3006020100020100`) | reject |
| `r0` | r = 0 with a genuine s | reject |
| `s0` | s = 0 with a genuine r | reject |
| `r-equals-n` | r equal to the curve order n | reject |
| `s-equals-n` | s equal to the curve order n | reject |
| `s-plus-n` | genuine signature with n added to s | reject |
| `r-plus-n` | genuine signature with n added to r | reject |
| `extra-zero-padding` | needless extra zero byte in front of r (broken encoding) | reject |
| `wrong-tag` | wrong type marker at the start (broken encoding) | reject |

Measured answers (asserted by `backend/tests/test_vectors.py`):

- Reference library: 16 of 16 right.
- `acme-sign` 1.4.3: 16 of 16 right.
- `acme-sign` 1.4.2: wrong on exactly **`r0-s0`** and **`s-plus-n`**. It accepts both. Both are
  values outside the allowed range 1 to n-1, which is the one planted bug (no range check).
  The other out-of-range cases (`r0`, `s0`, `r-equals-n`, `s-equals-n`, `r-plus-n`) happen to be
  rejected by 1.4.2's arithmetic even without the check.
