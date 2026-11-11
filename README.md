# Isogeny Evidence Lab (crypto MVP)

You bring in a file from a scanning tool that *claims* how a system's encryption is set up.
Evidence Lab checks each claim against the real system and marks it **True**, **False** or
**Couldn't check**, and shows the raw evidence behind every answer.

Passing these checks doesn't prove a system secure. It shows these specific checks passed.

## Status: phase 1 of 3

| Part | Status |
| --- | --- |
| Log in (you create your own password the first time) | Built |
| 1. Import (demo file, CycloneDX 1.6 CBOM `.json`, CSV template `.csv`) | Built |
| 2. Verify (True / False / Couldn't check, with evidence) | Built |
| Demo TLS server and demo file ("Acme Pay") | Built |
| Assistant panel | Empty panel only; the assistant is phase 3 |
| 3. Tests, 4. Evidence Lab | Not built (phase 2) |

What is real, what is demo and what is missing is listed honestly in [docs/LIMITS.md](docs/LIMITS.md).
The full spec is [docs/SPEC.md](docs/SPEC.md). Screenshots of every phase 1 screen are in
[docs/screenshots/phase1/](docs/screenshots/phase1/).

## Run the demo (one command)

You need Python 3.12 and Node.js 20 or newer installed. No internet is needed after the first run, and no Docker.

```
./run-demo.sh
```

The first run takes a minute or two (it installs what it needs). When it says it is starting,
open **http://127.0.0.1:8000** in your browser.

1. The first time, the app asks you to **create a password**. After that it asks you to log in with it.
2. Click **Use demo file**. You see three claims, labelled *Demo data*.
3. Tick **I own this system or am allowed to test it** (the address is the app's own demo server on your computer).
4. Click **Verify claims**. Expected: "TLS 1.3 only" is **False** (the demo server also accepts TLS 1.2),
   the certificate claim is **True**, the signing component claim is **True**. Open **Evidence** on any row to see the raw output.

To stop the app, press Ctrl+C in the window where it is running.

Things to know:

- The app only listens on your own computer (127.0.0.1). The demo TLS server uses `localhost:8443`.
- Your data (a small database and the demo test certificate) lives in the `data/` folder, which is never committed.
- Forgot the password? There is no reset button yet. Stop the app, delete `data/evidence-lab.sqlite3`, start again
  and create a new password. This also deletes your imports and results.

## Run the tests

Stop the app first (the end-to-end test needs port 8443 for its own demo server).

```
# Backend tests and the accuracy check
cd backend
.venv/bin/python -m pytest -q tests
.venv/bin/python -m app.accuracy

# Frontend tests
cd frontend
npm run typecheck
npm test

# End-to-end test in a real browser (starts its own copy of the app with an empty, throwaway data folder)
cd e2e
npm install          # first time only
npm test
```

`./run-demo.sh` creates `backend/.venv` and `frontend/node_modules` for you, so run it once before the tests.
On a new computer the end-to-end test also needs Playwright's browser once: `cd e2e && npx playwright install chromium`.

The **accuracy check** compares the app's Verify results on the demo with the answer key in
`demo/expected.json` (V1 to V3 in phase 1) and prints, for example, `Demo accuracy: 3 of 3 match`.
Any mismatch is shown, not hidden. The build never edits the answer key.

## Where things are

- `backend/` – Python 3.12, FastAPI, SQLite. `app/` is the code, `tests/` the tests.
- `frontend/` – React, TypeScript, Vite, Tailwind.
- `e2e/` – the Playwright end-to-end test.
- `demo/` – the demo file (`acme-pay-cbom.json`), the CSV template (`claims-template.csv`), the demo signing
  component (`components/acme-sign-1.4.2/`, deliberately flawed demo software) and the answer key (`expected.json`).
- `docs/` – the spec, the limits, screenshots.
