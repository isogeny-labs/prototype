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

## What a version declares it needs (phase 6e)
- `declared` holds, for single released versions, what that version itself lists as needed when it runs, read from
  the publisher's own package file: `package.json` for an npm package, the `METADATA` file of a wheel for a Python
  package. Each entry names the file as it is called inside the package, the file's SHA-256 as it was read, the
  lines quoted word for word, the link to the publisher's package and the date it was read.
- It says what the package file lists. It says nothing about what a system really loads, and nothing about a
  version that has no entry: the app then says "Not in our knowledge base yet". Nothing is worked out from a
  neighbouring version.
- Where a file lists no need, `needs` is empty and `note` says what the quoted lines cannot show (for example that
  the file has no `Requires-Dist` line).
- A library that is not a package with such a file (a JDK, OpenSSL) carries `no_package_file` with one sentence,
  and the app says "Doesn't apply".
- The four entries of 19 November 2026 (elliptic 6.5.6 and 6.5.7, ecdsa 0.13.2 and 0.13.3) were read from the
  pinned downloads in `backend/app/real_libraries.py`, each first checked against its pinned fingerprint.

## Add a library
1. Copy a similar file in `libraries/` and rename it.
2. Edit the name, label, roles, packages (package addresses without a version) and claims.
3. Run the fast tests: `cd backend && .venv/bin/python -m pytest -q tests`.

## What this folder does not do
The app never runs anything because of this folder. What may run is fixed in `backend/app/real_libraries.py`.
