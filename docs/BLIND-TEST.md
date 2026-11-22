# The blind test: how it works

**Status: designed and rehearsed on our own demo program. It has not been run on a real case yet.**
The first real case is Adam's: a real library version with a bug he found, which the build is not told about.

## What it is for

The other real libraries in this app were chosen by the build, which knew their published bugs in advance.
A blind test removes that advantage. A cryptographer brings a library version whose bug only they know, writes
down beforehand what the tests should show, and seals that. The app is then run on the library. Afterwards the
sealed answer is opened and compared. If the tests miss the bug, that is written down as a miss.

Three things have to hold for the result to mean anything:

1. **The expected result is fixed before the run.** Only its fingerprint (SHA-256) is committed; the file stays
   with the cryptographer.
2. **Nobody on the build side can read it.** A fingerprint can't be turned back into the file, and the file
   carries a long random text so that it can't be guessed either.
3. **Nothing in the tests changes between the seal and the run.** The seal holds one fingerprint over every code
   file of the app (the code that designs, runs, carries, judges and words a result), the test harness and its
   controls, the controls of the post-quantum exams, and every test-set file. The run refuses to start if any of
   them is different. Only two things may change: `backend/app/real_libraries.py`, where the new library's
   version and fingerprints go, and the library's own wrapper folder.

## The steps

### 1. The cryptographer writes the expected result, privately

One small JSON file, kept off the repository. Copy `demo/blind/expected-template.json` and fill it in:

| Field | What goes in it |
|---|---|
| `case` | A short name for the case: letters, digits and hyphens. It becomes the folder name. |
| `library` | `name`, `version` and `algorithm` (`ECDSA P-256`, `ML-DSA-65` or `ML-KEM-768`), as the app will know the library. |
| `expect` | One entry for each test you have an expectation for: `test` (the test's id, below), `result` (`Passed` or `Failed`) and, if you can, `wrong_cases`: the case ids you expect it to get wrong. |
| `bug` | One or two sentences on the bug, for the record. Shown only after the reveal. |
| `salt` | At least 32 random characters. Any will do; it only makes the file impossible to guess. |

The test ids: `official_vectors` (Independent exam, Wycheproof), `bad_signatures` (Attacker tricks),
`speed_size`, `mldsa_vectors` (Signature exam, ML-DSA-65), `mlkem_vectors` (Key exchange exam, ML-KEM-768).
Case ids are the ones the app shows: a Wycheproof `tcId` such as `168`, a short-list name such as `r0-s0`,
or an exam case such as `wycheproof-verify-135`.

### 2. Seal it

```
cd backend && .venv/bin/python -m app.blind seal /path/to/your-file.json
```

This writes `demo/blind/<case>/seal.json`: the SHA-256 of your file, the date, the library's name and version,
the app's commit, and the fingerprints of the tests as they stand. **Commit that file now.** Its commit date
is the proof that the expectation came first. A seal is never replaced: a second attempt needs a new case name.

### 3. The build adds the library, without being told the bug

Exactly as for any real library (see "Writing a wrapper for a real library" in `docs/ADAPTER.md`): its version,
source and fingerprint go into `backend/app/real_libraries.py`, and a short wrapper goes into
`demo/real-libraries/`. The build has to know the library's name and version to do this.

**It may not add or change a test, a rule, the test harness, a test-set file or any other code file of the app.**
Those are frozen by the seal; the only app file it may touch is `real_libraries.py`. (So a library that needs a
change elsewhere in the app can't be a blind case without a new seal, and the outcome would say so.)
A new container image or package is a new dependency and needs Kevin's OK, as always.

### 4. Run it

```
cd backend && .venv/bin/python -m app.blind run <case>
```

The run first checks the frozen fingerprints against the seal and refuses if anything differs. Then it does
what the buttons do: upload a one-line file naming the library, Verify, Run all. It saves `run.json` (each
test's result, taken from the reviewer's own verdict and not from the words on the screen, and the cases it got wrong) and `evidence.json` (the signed evidence file, checkable with
`python -m evidence verify`) beside the seal. Commit both.

### 5. Reveal and compare

The cryptographer hands over the file.

```
cd backend && .venv/bin/python -m app.blind reveal <case> /path/to/your-file.json
```

It checks that the file's SHA-256 is the sealed one (if not, nothing is compared), and that the run on record
was made with the tests as sealed. Then, test by test, it says one of:

| Outcome | Meaning |
|---|---|
| **caught** | Expected Failed, the app says Failed, and every case listed was among the app's wrong cases. |
| **caught in part** | Expected Failed and the app says Failed, but some listed cases were not found. They are named. |
| **missed** | Expected Failed and the app says Passed, or the test gave no result. |
| **agreed** | Both say Passed. |
| **found something not listed** | The app says Failed where Passed was expected, or on a test that was not listed. |

The outcome is saved as `outcome.json` beside the seal, misses included.

## What this does not prevent

- **Looking the library up.** Knowing its name and version, anyone can read its published bug reports. The seal
  stops the tests being tuned to the case. It can't stop someone reading the news. For a bug that is not
  public, this doesn't matter; for a published one, the test is only as blind as the people involved.
- **A wrapper written to hide a bug.** The wrapper is short and only translates, so it can be read in a few
  minutes. The cryptographer should read it before the reveal.
- **Tests added later.** A test written after a reveal says nothing about the blind result. The outcome file
  keeps the date and the fingerprints, so later changes can be told apart.

## The rehearsal

The three commands were tried on our own demo program, `acme-sign` 1.4.2, whose bug we planted ourselves.
That shows the mechanics work (seal, refusal when a test changes, run, reveal, a wrong file being turned
away). It is not a blind test and is not presented as one: `backend/tests/test_blind.py`.
