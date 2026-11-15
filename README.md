# Isogeny Evidence Lab (crypto MVP)

You bring in a file from a scanning tool that *claims* how a system's encryption is set up.
Evidence Lab checks each claim against the real system, runs tests on it, and shows the evidence
behind every answer. After a fix, it reruns the same tests and shows before and after.

Passing these tests doesn't prove a system secure. It shows these specific checks passed.

## Status: phase 4c (real code), on top of phases 1 to 4b

| Part | Status |
| --- | --- |
| Log in (you create your own password the first time) | Built |
| 1. Import (demo file, CycloneDX 1.6 CBOM `.json`, CSV template `.csv`) | Built |
| 2. Verify (True / False / Couldn't check, one plain sentence on top, Also noticed notes, with evidence) | Built |
| 3. Tests (five suggested tests for the demo, every server and signing program in a file tested, grouped by target, with what isn't tested and why; add from a short catalog, reorder, remove, run one or all at once) | Built |
| 4. Evidence Lab (results, controls, one line pointing to each fix, Mark reviewed, Dig deeper, Retest new version, Download evidence) | Built |
| 5. Fixes (a suggested code change for the signing bug with its proof, a pull request inside the app, approvals, a merge that a person confirms, Retest now; the server's TLS fix and each migration change as a change box: try on a test copy, approve, apply, roll back) | Built (phase 4b for the change boxes) |
| 6. Migration (where each system stands on post-quantum cryptography, measured on two tracks, key exchange and authentication; the target is post-quantum; what each option costs; a recommendation from fixed rules; your own choice; a roadmap by track; a change ready to apply, tried on a test copy, then applied with approval and rolled back if needed, on our own servers only) | Built (phase 4a, made real in phase 4b) |
| Demo mode and isolated mode (Docker) | Built |
| Real crypto libraries written by others (phase 4c): Java (OpenJDK), python-ecdsa, elliptic (npm), OpenSSL | Built, isolated mode (Docker) only |
| Uploading outside software | Not in this version: only our own demo components and the pinned real libraries run |
| Connecting real code hosts (GitHub and others) | Not in this version: only the small demo repository that comes with the app |
| Server setting change with proof (SPEC section 7c) | Built (phase 4b), on the Acme Pay demo server only |
| Changing a server that isn't ours (connectors) | Not built (a later phase); Download change still works |
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
   the certificate claim is **True**, the signing component claim is **True**. Each row starts with one plain sentence; open **Details and evidence**
   on any row to see the technical text and the raw output.
5. Open **3. Tests**. Five tests are suggested. You can drag them into another order, remove one with ×, or use
   **+ Add test** to add *Post-quantum readiness*. Click **Run all** (or **Run** on one card).
   Expected on the demo: Old TLS versions **Failed**, Certificate strength **Passed**, Independent exam (Wycheproof)
   **Failed** (3 of 484 cases wrong), Attacker tricks (our short list) **Failed** (it accepts r = 0, s = 0), Speed and size **Measured**,
   Post-quantum readiness **Not offered**. Run all takes about half a minute to a minute.
6. Open **4. Evidence Lab**. Open any row to see what happened, what it shows and what it doesn't, the evidence
   and the control. **Mark reviewed** records that you looked at it. **Dig deeper** saves a research request,
   shown as queued (no research engine is connected, so there is no answer). Each failed result has one line
   about its fix, for example "Fix available, code not connected", with a **View in Fixes** button.
7. Open **5. Fixes**. Two findings are listed.
   - *Server accepts TLS 1.2* has a **change box** (since phase 4b): the setting that turns TLS 1.2 off, with the
     lines for nginx, Apache and an application. Click **Try on a test copy**: the app starts a copy of the demo
     server with TLS 1.2 off on a spare port and runs the server protocol check on it. When the try passes, pick
     who must approve, click **Ask for approval**, **Approve** for each picked reviewer, then **Apply to** the
     demo server. The app reruns the server tests by itself: the server protocol check now reads **Passed**. Press
     **Verify claims** again (step 1) and "TLS 1.3 only" reads **True**. **Roll back** puts TLS 1.2 back. Apply works only on our own demo server; there is
     no confirm box, so a click is a change. **Download change** gives the same lines as a file.
   - *acme-sign accepts out-of-range signatures* starts as **Code not connected**. Click **Connect demo code**.
     The app copies the small demo repository that comes with it, writes the change on a branch (3 lines added,
     1 removed) and proves it by itself: every test in your plan runs again on the changed code. This takes
     about half a minute (about a minute in isolated mode). Expected: **Ready for review**, with "Proof passed".
     Open **The change** and **Proof** to see the lines and the results.
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

### A file with several servers and programs

`demo/multi-target-demo.csv` (Demo data) names the Acme server, three local test servers (8444, 8445, 8446)
and two signing programs (`acme-sign 1.4.2` and `acme-sign 9.9`). Upload it with the drop zone on **1. Import**:
the app then starts the three test servers on your computer, and says so (or says which port was already taken).
Tick the four boxes, verify, and run the tests. Expected: every server and program gets its tests, grouped by
target; "Not tested, and why" lists what is left out; `acme-sign 9.9` can't run (only our own demo components
run); the certificate row for 8445 carries an "Also noticed" note (that server also accepts TLS 1.0 and 1.1).

### The migration plan (step 6)

`demo/migration-demo.csv` (Demo data) names five local test servers (8451 to 8455) and the two signing programs.
Upload it on **1. Import**: the app starts the five test servers on your computer and says so. Tick the five
boxes, press **Verify claims**, then open **6. Migration** and press **Measure status**. It works without Docker.

- Expected key exchange statuses: 8451 Hybrid, 8452 Classical (the file wrongly says Hybrid, so Verify marks that claim
  False), 8453 Classical, 8454 Classical with no TLS 1.3, 8455 Post-quantum only, `acme-sign 1.4.2` Classical,
  `acme-sign 9.9` Couldn't check.
- Each system shows what was measured, the three settings the recommendation uses (from the file, set by you, or
  "assumed"), what each step would cost with the source of every number, a recommendation from fixed rules (no AI
  model), and four options. **Choose this option** records your own choice with your reason and the time; the app
  never overwrites it. **Roadmap** shows the phases; **View in Fixes** opens the how-to or the blocker.
- `demo/migration-real-servers.csv` is not demo data: it names three public test servers on the internet. Upload
  it yourself, tick the boxes to confirm you may test them, and compare what the app measures with what
  Cloudflare Radar says. The automated tests never use the internet, and the build machine could not reach these
  servers, so this file has not been run by the build.

Each system shows two tracks for a server, **Key exchange** (Classical, Hybrid (interim), Post-quantum only) and
**Authentication** (Classical or Post-quantum), and one track, **Signatures**, for a signing program. The target is
post-quantum on every track; hybrid is a step on the way, never the end. Every track has a **Next step** and a
**Why**. **Measure again** is needed if you measured in phase 4a: the rule changed, so the old numbers keep their
old words and are not reused.

Since phase 4b, choosing an option builds a **change**: the settings before and after, and the exact lines for
nginx and Apache (marked with what they were checked on) and for an application ("Not checked on real software").
The same change box sits in Fixes.

- **Try on a test copy** starts a copy of the server with the change on a spare port on your computer and runs the
  same locked measurement on it. Before and after show side by side. In isolated mode the same change also runs on
  real nginx; in demo mode that column says real nginx needs isolated mode.
- **Ask for approval**, then **Approve** for each reviewer you picked (you, Demo reviewer A, Demo reviewer B; one
  login, and the demo reviewers are demo data). **Apply to** the server is off until the latest try passed and every
  picked reviewer approved. It is one click, with no confirm box.
- After Apply the app measures again by itself. If the result doesn't match the try it says so and offers **Roll
  back**; it never rolls back by itself. Roll back is one click and measures again.
- Apply works only on our own servers: the five migration demo servers, the lab nginx and the Acme Pay demo server.
  For any other server Try and Apply are off and say a connector comes in a later phase; **Download change** stays.
  Changes for Keep classical, Wrap and signing programs are text for a person to act on.
- `demo/lab-nginx.csv` (Demo data) names the lab nginx on localhost:8461. It runs only in isolated mode, from the
  pinned nginx image that `cd backend && .venv/bin/python -m app.prepare` pulls (nothing else pulls it).
- Every step (try, approvals, Apply, the measurement after, Roll back) is in the evidence download and the report.

### Real libraries (phase 4c)

Besides its own demo program, the app can test **real crypto libraries written by others**, in exact versions:
Java (OpenJDK, Temurin build) 17.0.2 and 17.0.3, python-ecdsa 0.13.2 and 0.13.3, elliptic (npm) 6.5.6 and 6.5.7,
and OpenSSL 3.5.9. They run **only in isolated mode** (Docker), each family in its own locked-down container image
with no network. In demo mode the app says "needs isolated mode" and runs nothing of theirs. The library's own
files are not stored in this repository: `python -m app.prepare` downloads them once and checks each by its
fingerprint (see [demo/real-libraries/README.md](demo/real-libraries/README.md); the pins are in
`backend/app/real_libraries.py`).

- The first `./run-demo.sh` with Docker running now also downloads what the real-library images are built from
  (a few hundred MB for each Java image; about 3 GB of disk in all) and builds the images. It can take several
  minutes. Later starts reuse them.
- The Java images are built for Intel/AMD processors only. On an Apple Silicon Mac, Docker runs them through
  emulation, which is slower.
- To try it: on **1. Import**, upload `demo/real-libraries.csv` (it is not Demo data) with the drop zone, tick the
  box, **Verify claims**, then open **3. Tests** and run them. The signature tests (Independent exam, Attacker tricks,
  Speed and size) run on each library. For OpenSSL there are two more: **Key exchange exam (ML-KEM-768)** and
  **Signature exam (ML-DSA-65)**, which put the library through official cases from NIST and Project Wycheproof.
  They compare answers only; they say nothing about timing attacks.
- A result on a real library shows the publisher's advisories for that version as information, never as a result,
  and may carry an **Also noticed** note. A failed test gets a text-only fix, "Update <name> to the fixed version",
  or says no fixed version is known.
- **Retest new version** can move one library of the file to another version (for example Java 17.0.2 to 17.0.3).
- Three more commands:
  - `cd backend && .venv/bin/python -m app.accuracy --only real` runs the real libraries through the same path as the
    buttons and compares with the third answer key, `demo/expected-real-libraries.json`.
  - `cd backend && .venv/bin/python tools/try_real_library.py <name> <version>` tries one library by hand, for
    example `openjdk 17.0.2` (isolated mode).
  - `cd backend && .venv/bin/python -m app.blind seal|run|reveal` is the blind test: a cryptographer's expected
    findings are sealed before a library is added, and revealed after the run. See
    [docs/BLIND-TEST.md](docs/BLIND-TEST.md).

### Demo mode and isolated mode

The line under the step bar says which mode the app is in.

- **Demo mode** (no Docker needed): our demo software runs as normal local programs with a time limit. Not isolated.
- **Isolated mode** (Docker running): the same demo software runs in a locked-down container with no network and
  no access to your files. `./run-demo.sh` prepares the two small images it needs once, the first time Docker is
  running and you are online (since phase 4c it also prepares the real-library images, above). If Docker is missing, not running, or you are offline, the app simply starts in
  demo mode and says why. The app itself never downloads anything.
- The post-quantum readiness test needs OpenSSL 3.5 or newer on your computer, or Docker with the prepared
  image. Without either it shows **Couldn't run (needs OpenSSL 3.5 or newer)**. On Docker Desktop (Mac, Windows)
  it may show **Couldn't run (the checker could not reach the server)**; see docs/LIMITS.md.
- To check what is prepared without changing anything: `cd backend && .venv/bin/python -m app.prepare --check`.
- To force a mode for one start: `EVIDENCE_LAB_MODE=demo ./run-demo.sh` (or `isolated`).

Things to know:

- The app only listens on your own computer (127.0.0.1). The demo TLS server uses `localhost:8443`; the multi-target demo file's test servers use 8444 to 8446, only after that file is imported.
- Your data lives in the `data/` folder, which is never committed: a small database, the demo test certificate
  and the app's evidence signing key (a local key, made on first start, readable only by you).
- Only our own demo software and the pinned real libraries can be run. There is nowhere to upload other software in this version.
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
`demo/expected.json`: V1 to V3, T1 to T5, R1 to R5, the controls, A1 and (since phase 4b) S1 to S3, the server TLS fix. It prints one line per answer and ends
with, for example, `Demo accuracy: 18 of 18 match`. It takes about one minute in demo mode and about a minute and
a half in isolated mode. Any mismatch is shown, not hidden, and makes the command exit with an error code.
Add `--mode demo` or `--mode isolated` to choose the mode. The build never edits the answer key.

The accuracy command also runs the migration demo and compares it with `demo/expected-migration.json`
(`--only acme` or `--only migration` runs one of the two), ending with, for example,
`Migration demo accuracy: 47 of 47 match`. Since phase 4c it also runs the real libraries against
`demo/expected-real-libraries.json` (`--only real` runs just those; they need isolated mode and the prepared
images). The build never edits any answer key.

The backend tests take about 15 minutes and the end-to-end test about 7. Tests that need real containers are
skipped, with a message, when Docker is not running or the images are not prepared
(`cd backend && .venv/bin/python -m app.prepare`).

## Where things are

- `backend/` – Python 3.12, FastAPI, SQLite. `app/` is the code, `tests/` the tests, `evidence/` the small
  command that checks a downloaded evidence file.
- `frontend/` – React, TypeScript, Vite, Tailwind.
- `e2e/` – the Playwright end-to-end test.
- `demo/` – the demo file (`acme-pay-cbom.json`), the CSV template (`claims-template.csv`), the demo signing
  components (`components/acme-sign-1.4.2/`, deliberately flawed, and `components/acme-sign-1.4.3/`, corrected),
  the small demo repository holding acme-sign 1.4.2 (`repos/acme-sign.git/`), the deliberately broken controls,
  the official test vectors (`vectors/wycheproof/`, Project Wycheproof, Apache-2.0, and `vectors/acvp/`, NIST ACVP),
  the real-library wrappers (`real-libraries/`) and their demo file (`real-libraries.csv`), our bad-signature cases
  (`vectors/bad-signatures/`), the answer key (`expected.json`), and the two migration files
  (`migration-demo.csv`, `migration-real-servers.csv`) and `lab-nginx.csv` (the lab nginx, isolated mode).
  - The code of acme-sign 1.4.2 no longer has comments pointing at its bug. The bug is still there on purpose.
  - The demo repository is made from the 1.4.2 file by `cd backend && .venv/bin/python -m app.demo_repo`. Run
    that again only if the 1.4.2 file ever changes; a test fails until you do.
- `docs/` – the spec, the limits, the engine and adapter notes, screenshots.
