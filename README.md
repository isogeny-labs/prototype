# Isogeny Evidence Lab (crypto MVP)

You bring in a file from a scanning tool that *claims* how a system's encryption is set up.
Evidence Lab checks each claim against the real system, runs tests on it, and shows the evidence
behind every answer. After a fix, it reruns the same tests and shows before and after.

Passing these tests doesn't prove a system secure. It shows these specific checks passed.

## Status: phase 3a (the first of the four steps of phase 3)

| Part | Status |
| --- | --- |
| Log in (you create your own password the first time) | Built |
| 1. Import (demo file, CycloneDX 1.6 CBOM `.json`, CSV template `.csv`) | Built |
| 2. Verify (True / False / Couldn't check, with evidence) | Built |
| 3. Tests (five suggested tests, add from a short catalog, reorder, remove, run one or all at once) | Built |
| 4. Evidence Lab (results, controls, one line pointing to each fix, Mark reviewed, Dig deeper, Retest new version, Download evidence) | Built |
| 5. Fixes (a suggested code change for the signing bug with its proof, a pull request inside the app, approvals, a merge that a person confirms, Retest now; a text-only suggestion for the server finding) | Built |
| Demo mode and isolated mode (Docker) | Built |
| Uploading outside software | Not in this version: only our own demo components run |
| Connecting real code hosts (GitHub and others) | Not in this version: only the small demo repository that comes with the app |
| Server setting change with proof (SPEC section 7c) | Not built (next step) |
| Change watch | Not built (phase 3c) |
| Assistant panel | Empty panel only; the assistant is phase 3b. No AI model is connected |
| Accuracy panel in the app | Not built (phase 3b); the accuracy check is a command for now |

What is real, what is demo and what is missing is listed honestly in [docs/LIMITS.md](docs/LIMITS.md).
The full spec is [docs/SPEC.md](docs/SPEC.md). How tests, runs and reviews are recorded is in
[docs/ENGINE.md](docs/ENGINE.md); how software under test is run is in [docs/ADAPTER.md](docs/ADAPTER.md).
Screenshots are in [docs/screenshots/](docs/screenshots/).

## Run the demo (one command)

You need Python 3.12 and Node.js 20 or newer installed. Docker is optional. No internet is needed after the first run.

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
5. Open **3. Tests**. Five tests are suggested. You can drag them into another order, remove one with ×, or use
   **+ Add test** to add *Post-quantum readiness*. Click **Run all** (or **Run** on one card).
   Expected on the demo: Old TLS versions **Failed**, Certificate strength **Passed**, Official test vectors **Failed**
   (3 of 484 cases wrong), Bad signatures **Failed** (it accepts r = 0, s = 0), Speed and size **Measured**,
   Post-quantum readiness **Not offered**. Run all takes about half a minute to a minute.
6. Open **4. Evidence Lab**. Open any row to see what happened, what it shows and what it doesn't, the evidence
   and the control. **Mark reviewed** records that you looked at it. **Dig deeper** saves a research request,
   shown as queued (no research engine is connected, so there is no answer). Each failed result has one line
   about its fix, for example "Fix available, code not connected", with a **View in Fixes** button.
7. Open **5. Fixes**. Two findings are listed.
   - *Server accepts TLS 1.2* is **Text only**: a written suggestion for the server's settings. The app does not
     apply it or test it.
   - *acme-sign accepts out-of-range signatures* starts as **Code not connected**. Click **Connect demo code**.
     The app copies the small demo repository that comes with it, writes the change on a branch (3 lines added,
     1 removed) and proves it by itself: every test in your plan runs again on the changed code. This takes
     about half a minute. Expected: **Ready for review**, with "Proof passed". Open **The change** and
     **Proof** to see the lines and the results.
8. Choose who must approve (you are ticked already; you can also tick **Demo reviewer A** and **Demo reviewer B**,
   which are demo data, not people) and click **Open pull request**. Click **Approve** for each reviewer you
   picked. This version has one login, so whoever is at the keyboard records each approval, under the name
   shown. Then click **Merge pull request** and **Confirm merge**. Nothing is merged until you confirm, and the
   pull request lives inside the app only: nothing is sent anywhere.
9. Click **Retest now**. The same locked tests run again on the merged code and Evidence Lab shows before and
   after. Expected: the two signature tests now **Passed**, speed **No slowdown beyond measured noise**, the
   server tests unchanged (the server was not fixed). Without the Fixes step you can get the same comparison
   with **Retest new version** in Evidence Lab, picking **acme-sign 1.4.3**.
10. Click **Download evidence**. Two files arrive: the evidence (JSON, the record) and a readable report (HTML).
   To check the JSON file, in a terminal:

   ```
   cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>
   ```

   It prints `Evidence verified`. Change any one character in a copy of the file and it fails.

To stop the app, press Ctrl+C in the window where it is running.

### Demo mode and isolated mode

The line under the step bar says which mode the app is in.

- **Demo mode** (no Docker needed): our demo software runs as normal local programs with a time limit. Not isolated.
- **Isolated mode** (Docker running): the same demo software runs in a locked-down container with no network and
  no access to your files. `./run-demo.sh` prepares the two small images it needs once, the first time Docker is
  running and you are online. If Docker is missing, not running, or you are offline, the app simply starts in
  demo mode and says why. The app itself never downloads anything.
- The post-quantum readiness test needs OpenSSL 3.5 or newer on your computer, or Docker with the prepared
  image. Without either it shows **Couldn't run (needs OpenSSL 3.5 or newer)**. On Docker Desktop (Mac, Windows)
  it may show **Couldn't run (the checker could not reach the server)**; see docs/LIMITS.md.
- To check what is prepared without changing anything: `cd backend && .venv/bin/python -m app.prepare --check`.
- To force a mode for one start: `EVIDENCE_LAB_MODE=demo ./run-demo.sh` (or `isolated`).

Things to know:

- The app only listens on your own computer (127.0.0.1). The demo TLS server uses `localhost:8443`.
- Your data lives in the `data/` folder, which is never committed: a small database, the demo test certificate
  and the app's evidence signing key (a local key, made on first start, readable only by you).
- Only our own demo software can be run. There is nowhere to upload other software in this version.
- The suggested code change is proved before it is offered: the app first checks that the changed file is, byte
  for byte, one of our own demo components, and then runs that component. Nothing else is ever run.
- Each imported file gets its own fresh copy of the demo repository, in `data/repos/`. So importing the demo file
  again starts clean.
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

The **accuracy check** runs the whole demo through the same path as the buttons (import, verify, propose and lock
the tests, add the post-quantum test, Run all, Retest on 1.4.3) and compares every answer with the answer key in
`demo/expected.json`: V1 to V3, T1 to T5, R1 to R5, the controls and A1. It prints one line per answer and ends
with, for example, `Demo accuracy: 15 of 15 match`. It takes about one minute in demo mode and about a minute and
a half in isolated mode. Any mismatch is shown, not hidden, and makes the command exit with an error code.
Add `--mode demo` or `--mode isolated` to choose the mode. The build never edits the answer key.

The backend tests take about ten minutes. Tests that need real containers are skipped, with a message, when
Docker is not running or the images are not prepared (`cd backend && .venv/bin/python -m app.prepare`).

## Where things are

- `backend/` – Python 3.12, FastAPI, SQLite. `app/` is the code, `tests/` the tests, `evidence/` the small
  command that checks a downloaded evidence file.
- `frontend/` – React, TypeScript, Vite, Tailwind.
- `e2e/` – the Playwright end-to-end test.
- `demo/` – the demo file (`acme-pay-cbom.json`), the CSV template (`claims-template.csv`), the demo signing
  components (`components/acme-sign-1.4.2/`, deliberately flawed, and `components/acme-sign-1.4.3/`, corrected),
  the small demo repository holding acme-sign 1.4.2 (`repos/acme-sign.git/`), the deliberately broken controls,
  the official test vectors (`vectors/wycheproof/`, Project Wycheproof, Apache-2.0), our bad-signature cases
  (`vectors/bad-signatures/`) and the answer key (`expected.json`).
  - The code of acme-sign 1.4.2 no longer has comments pointing at its bug. The bug is still there on purpose.
  - The demo repository is made from the 1.4.2 file by `cd backend && .venv/bin/python -m app.demo_repo`. Run
    that again only if the 1.4.2 file ever changes; a test fails until you do.
- `docs/` – the spec, the limits, the engine and adapter notes, screenshots.
