# Library knowledge base

This folder holds what the official release notes and docs of a library say about three questions: does it offer
ML-KEM-768 key exchange, X25519MLKEM768 hybrid TLS, and ML-DSA-65 signatures.

- One file per library: `libraries/<library>.json`. The `library` field equals the file name.
- `schema.json` is the exact shape of a file (written from `backend/app/knowledge/model.py`).

## The rule for a yes and a no
- A "yes" needs an official source that names the version that added the capability: `{"from": "<version>"}`, with the
  source link and the line quoted word for word.
- A "no" is allowed only as the mirror of that "yes": `{"before": "<same version>"}`, same source.
- If no official source names the version, write no claim. The app then says "Not in our knowledge base yet".
- A library that every product builds and ships on its own (BoringSSL) has no claims; it carries
  `needs_your_environment` instead, because only a test on your copy can answer.
- Never fill anything in from memory. Open the official page, copy the line exactly, and note the date you checked.

## Add a library
1. Copy a similar file in `libraries/` and rename it.
2. Edit the name, label, roles, packages (package addresses without a version) and claims.
3. Run the fast tests: `cd backend && .venv/bin/python -m pytest -q tests`.

## What this folder does not do
The app never runs anything because of this folder. What may run is fixed in `backend/app/real_libraries.py`.
