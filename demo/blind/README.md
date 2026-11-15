# Blind test cases

One folder per case, made by `python -m app.blind` (see `docs/BLIND-TEST.md`):

- `seal.json`: the fingerprint of the cryptographer's expected result, committed before the run.
- `run.json` and `evidence.json`: what the app found, and the signed evidence file.
- `outcome.json`: the comparison after the reveal. A miss stays in it as a miss.

`expected-template.json` is the form to copy for a new case. A filled-in copy is never stored here before
the reveal: only its fingerprint is.

No case has been run yet.
