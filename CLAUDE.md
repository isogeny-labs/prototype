# Isogeny Evidence Lab (crypto MVP)

Full spec: @docs/SPEC.md. Read it before any work. Build only the phase you're asked for.

How Kevin works with you: he's not a developer and doesn't use git. Explain in plain language, handle all git yourself, and tell him exactly what to click or type when you need him.

## Repo
- Work only on branch `mvp/crypto-simple` (created from `claude/isogeny-evidence-lab-mvp-sg3pva`; there is no `main`). Commit at the end of each phase. Never push or change the default branch unless asked.
- New files under `docs/screenshots/` and `demo/vectors/` go to Git LFS (set in `.gitattributes`; `./run-demo.sh` fetches the test sets by itself). Commit only a phase's new pictures; restore the others the end-to-end run rewrote with `git checkout -- docs/screenshots/<folder>`.
- This is a fresh build. Don't read, copy or restore code from the old prototype in git history.
- Never edit `demo/expected.json`, `demo/expected-migration.json`, `demo/expected-real-libraries.json` or `demo/expected-dependencies.json` (the answer keys) or `docs/wireframes/`. If the app disagrees with the key, fix the app or explain why the key is wrong.

## Product rules
- IMPORTANT: Keep it simple. Every new button, screen or setting must be in docs/SPEC.md section 2, or ask first.
- Results (True/False/Couldn't check, Passed/Failed) come only from checks and tests. The co-pilot never sets a result or acts without the user's Confirm, and everything it can do also has a normal button.
- No AI model. The co-pilot is rule-based behind `CopilotEngine`.
- Suggested code changes are offered only after every test passes on the changed code. The app never merges or deploys on its own; a person approves and merges.
- The app changes a system only when a person clicks Apply, after a passing try on a test copy and the required approvals; it re-measures right after, and can roll back. In this version Apply works only on our own demo test servers, the lab nginx and the Acme Pay demo server; any other server needs a connector (a later phase).
- Never call a system "secure", give a security score or estimate time-to-hack.
- Plain-language UI text for a busy security engineer who isn't a cryptographer.

## Safety
- Uploaded files are data, never instructions. Nothing in them is executed.
- Uploading outside software is not in this version. Only our own demo components, the pinned lab images and the real libraries fixed in `backend/app/real_libraries.py` run, and the pinned OpenSSL 3.0.x copy used as the known-incapable control of the capability check (phase 4d). Demo components run in demo mode (local processes) or isolated mode (Docker). A real library (Java, python-ecdsa, elliptic, OpenSSL, each in exact pinned versions) runs in isolated mode only, in its own locked-down container image, and is never run as a local program.
- Network checks: handshakes only, localhost or user-confirmed addresses only. One exception to the container lock-down: for the hybrid handshake question of the capability check, the two pinned OpenSSL copies run `openssl s_client` with host network, for one handshake to the app's own lab server on 127.0.0.1 only.
- A dependency list (CycloneDX or SPDX) is data. Nothing in it runs, and nothing connects to the customer's systems.
- Never print secrets or keys in code, logs, docs or replies. Test keys only.
- Ask before adding any dependency not in docs/SPEC.md section 3.

## Commands
- Start the app: `./run-demo.sh` (from the repo root), then open http://127.0.0.1:8000. Ctrl+C stops it. Demo TLS server: localhost:8443.
- Isolated mode: when Docker is running, `./run-demo.sh` prepares the test images once (including the pinned nginx lab image and one image for each real library; the first time this downloads a few hundred MB and can take several minutes) (`cd backend && .venv/bin/python -m app.prepare`; add `--check` to only report). Only that step may pull or build; the app never does. Without Docker or the images the app runs in demo mode and says why. Force a mode with `EVIDENCE_LAB_MODE=demo` or `isolated`.
- Backend tests, fast set (a few minutes; says how many slow tests it left out): `cd backend && .venv/bin/python -m pytest -q tests` (venv is Python 3.12; `./run-demo.sh` creates it).
- Backend tests, everything (about 24 minutes with Docker ready; container tests are skipped with a message when Docker isn't ready): `cd backend && .venv/bin/python -m pytest -q tests --full`. A new test that needs Docker is slow by itself; one that takes more than about 5 seconds, or reads a long demo walk built for its file, gets `@pytest.mark.slow` (or its walk goes into `SLOW_SHARED_WALKS` in `tests/conftest.py`).
- Install the dev tools (lint, type check, pip-tools) once: `cd backend && .venv/bin/python -m pip install --require-hashes -r requirements.lock -r requirements-dev.lock`. Packages are locked (`requirements.in` is the list, `requirements.lock` the exact versions); changing a version needs Kevin's OK.
- Lint: `cd backend && .venv/bin/ruff check app tests tools evidence`. Type check: `cd backend && .venv/bin/python tools/typecheck.py` (only new problems fail; `--write-baseline` after a fix or a move). Never change what code does to satisfy either.
- Screen data types: change the backend, then `backend/app/web/models.py`, then `cd backend && .venv/bin/python tools/api_schema.py` and `cd frontend && npm run gen:api` (add `--check`, or `-- --check` for npm, to only compare), then the frontend.
- GitHub checks (`.github/workflows/`): "Checks" runs on every push and pull request (lint, type check, generated files up to date, fast tests, demo-mode accuracy, frontend tests and build); "Slow checks" runs nightly and by hand (full backend suite, isolated-mode accuracy, end-to-end).
- Map of the code: `docs/LAYOUT.md`.
- Accuracy check: `cd backend && .venv/bin/python -m app.accuracy` (all 18 answers through the same path as the buttons; compares with `demo/expected.json`; then the migration demo against `demo/expected-migration.json`; then the real libraries against `demo/expected-real-libraries.json`, which takes about 25 minutes in isolated mode and in demo mode grades only the key's demo-mode answer; then the dependency lists against `demo/expected-dependencies.json` (both modes; under a minute); exit code 0 only if all match and all four answer keys are there; `--mode demo` or `--mode isolated` picks the mode; `--only acme`, `--only migration`, `--only real` or `--only dependencies` runs one of the four).
- Check a downloaded evidence file: `cd backend && .venv/bin/python -m evidence verify file.json` (exit code 0 only if nothing changed and the signer is this app's key; `--data-dir DIR` or `--public-key HEX_OR_FILE` to name the trusted key).
- Frontend tests: `cd frontend && npm run typecheck && npm test`. Build: `npm run build`.
- Playwright end-to-end: `cd e2e && npm test` (builds the frontend, starts its own app on port 8010 with a throwaway data folder; stop the app first, it needs port 8443; screenshots go to `docs/screenshots/phase1/`, `docs/screenshots/phase2/`, `docs/screenshots/phase3a/`, `docs/screenshots/phase3a-fixes/`, `docs/screenshots/phase4a/`, `docs/screenshots/phase4b/`, `docs/screenshots/phase4c/` and `docs/screenshots/phase4d/`; the migration demo's test servers need ports 8451 to 8455, and the lab nginx port 8461; the Dependencies walk starts its own copies of the app on ports 8013 and 8014, with demo servers on 8446 and 8447).
- Try one real library by hand (isolated mode): `cd backend && .venv/bin/python tools/try_real_library.py openjdk 17.0.2`.
- Blind test (see `docs/BLIND-TEST.md`): `cd backend && .venv/bin/python -m app.blind seal|run|reveal`.
- Remake the bundled demo repository: `cd backend && .venv/bin/python -m app.demo_repo` (writes `demo/repos/acme-sign.git/` from the acme-sign 1.4.2 file; needed only if that file changes, and a backend test fails until it is done).

## Tests
- One folder per feature (`backend/tests/dependencies/`), not one file per phase.
- Test wording rules (every answer has a label and a reason; no "secure", no score), not exact sentences, except where a sentence is the requirement.
- The fast set stays under 5 minutes.
- Each feature gets screen tests and one end-to-end walk.
- Every new file reader gets a seeded fuzz test (damaged copies: a plain refusal or a normal read, within a time limit; no new package).

## How each phase runs
1. Plan first: list the files, screens and buttons, and how you'll prove it works. Wait for my OK before writing code.
2. Build it.
3. Use a subagent to review the phase against docs/SPEC.md and this file. Report only gaps that break a requirement, add something out of scope, or make the demo less accurate. Fix those.
4. Show me test output, screenshots and the accuracy result. Commit only after I say OK.

A phase is done only when its tests pass and the accuracy check matches `demo/expected.json` for that phase.
