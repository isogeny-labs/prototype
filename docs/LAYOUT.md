# Where things live

A one-page map for a new engineer. Read `CLAUDE.md` first: its rules win over this page. For records and
shapes see `docs/ENGINE.md`; for how software under test is run see `docs/ADAPTER.md`.

## Top folders

| Folder | What is in it |
|---|---|
| `backend/` | Python 3.12, FastAPI, SQLite. `app/` is the code, `tests/` the tests, `tools/` small commands, `evidence/` the command that checks a downloaded evidence file. Since phase 5c also `ottolab/` (Otto's research side; the app never imports it), `otto.lock.json` (the pin of Adam's Otto harness) and `.otto/` (the fetched copy of that harness; ignored by git, never committed). |
| `frontend/` | React, TypeScript, Vite, Tailwind. `src/App.tsx` is the shell (phase 5a: sidebar, top bar, hash routes in `src/router.ts`). `src/components/` has one screen file per step; `components/shell/` the sidebar, top bar, project switcher and guided-demo bar; `components/pages/` Projects, the Project overview, the Overview, the New assessment and Close boxes, and Settings; `components/layout.tsx` the page header, summary cards, table (with its compact form beside an open panel), the resizable detail panel, the work-group heading and the box; `components/checks/` the Checks table, a check's panel and Evidence's library rows; `components/related.tsx` the links between items (`LinkProvider`, `ItemLinkView`) and the Related block; `components/AdvisoriesScreen.tsx` and `components/advisories/` the Advisories page (phase 5c: its table, its panel and their parts); `components/pages/OttoSettings.tsx` the Test packs and Live Otto sections of Settings (phase 5c); `components/otto/` what every page shares for Otto's proposals (phase 5c, second part): `ProposalCard.tsx` (one proposal with Accept, Reject and its small reason box, Undo, Reconsider and the decisions folded under it; used on Advisories, Fixes, Migration and Dependencies) and `ResultOttoBlock.tsx` (on a result of an advisory check: where the check came from). `src/readOnly.tsx` turns action buttons off in a closed assessment; `src/prefs.ts` keeps the look, the collapsed sidebar, the guided-demo switch and the panel's width in the browser; `src/plainNames.ts` and `components/plainName.tsx` put plain names first (the pairs come from the backend's `names.ALGORITHM_NAMES`). It draws only what the backend sends. Since the 5c fixes (19 November 2026): `src/time.ts` is the one way a time is written on screen (the viewer's own time zone; `api.ts` asks the server for marked times and writes them); `components/lab/RetestMenu.tsx` is the Retest new version button and menu that Evidence and Checks share; `components/layout.tsx` also holds the parts of a group (`PartSection`, `BlockSection`), "Open in new tab" in every panel's header and the item's own page (`ItemPageContext`; the address is `…?item=<id>&view=page`, `router.ts`), and a place in the panel header for phase 6 (`PanelHeaderSlotContext`). |
| `e2e/` | The Playwright end-to-end test. It writes screenshots to `docs/screenshots/`. Each walk starts its own project (`openFreshAssessment` in `tests/shared.ts`); `tests/projects.spec.ts` walks projects and assessments; `tests/finding.spec.ts` follows one finding from its claim to the Project overview, and `tests/layout.spec.ts` measures every table page at 1440 pixels wide (both on a copy of the app of their own, `startCopy` in `tests/shared.ts`); `tests/otto.spec.ts` walks Otto's loop (phase 5c), also on copies of the app of its own; its third part starts a copy without Otto (`EVIDENCE_LAB_OTTO_HOME` names an empty folder), so it runs on every computer. |
| `demo/` | Demo data: claims files, the demo components, the real-library wrappers, the pinned test sets, the bundled demo repository, the dependency lists (phase 4d), and the four answer keys. A fifth key, `expected-otto.json` (phase 5c), is written independently and is not in the repository yet. |
| `knowledge/` | The library knowledge base (phase 4d): one JSON file per library under `libraries/`, `schema.json`, and `README.md` with the rules. Data only. |
| `research/` | Otto's research data (phase 5c): `snapshot/2026-11-17/` (six real published advisories, quoted word for word, with a `README.md` of sources and licences), `recorded/` (Claude's answers recorded during the build, one file for each prompt), `lab/` (Otto's research ledger with its pinned scripts, its design and fix files and its run outputs; only Otto's harness writes it) and `packs/` (the two signed test packs). Data only. |
| `docs/` | The spec, limits, handoff, engine and adapter notes, the blind test, the questions of the fifth answer key (`OTTO-KEY.md`), screenshots. This page. |
| `.github/workflows/` | `checks.yml` (every push and pull request) and `slow.yml` (nightly and by hand). |
| `.devcontainer/` | `devcontainer.json`: names what a new Codespace is built from, each part pinned by its fingerprint (the official Python 3.12 image and the features Node.js 22, Docker inside the Codespace and Git LFS), so `./run-demo.sh` works there by itself; and (phase 5c) asks GitHub to let a new Codespace read the private Otto repository, so `./run-demo.sh` can fetch the pinned harness there. `backend/tests/test_devcontainer.py` checks both, and the Python step of `./run-demo.sh`. |

## backend/app, folder by folder

Every import is absolute (`from app.x.y import z`).

At the top (commands and parts shared by everything):
- `main.py` creates the app and includes the routers. `__main__.py` starts it.
- Commands: `accuracy.py` (+ `accuracy_real.py`, `accuracy_deps.py` since phase 4d and `accuracy_otto.py` since phase 5c), `prepare.py` (since phase 5c it also fetches the pinned Otto harness; `--otto` does only that), `blind.py`, `demo_repo.py`.
- Shared: `config.py`, `db.py`, `errors.py`, `auth.py`, `jobs.py`, `names.py`, `canonical.py`.
- `real_libraries.py` lists the real libraries, their pins and advisories. It stays at the top because a safety rule names it.

Folders:
- `web/`: the HTTP routes, split by step: `session.py`, `importing.py` (import and verify), `tests.py`, `lab.py` (Evidence Lab), `migration.py`, `changes.py`, `fixes.py`, `dependencies.py` (phase 4d), `projects.py` (phase 5a: the organization, folders, projects, assessments, Load demo projects, and the closed guard that `main.py` puts on every step router; phase 5b: the Project overview and Rerun as new assessment), `checks.py` (phase 5b: every check, one check, the Related block), `otto.py` (phase 5c: Settings' Test packs and Live Otto sections, the Advisories page, and Otto's proposals: the list and one decision on one proposal). `common.py` holds request bodies, helpers and `shows()`. `models.py` holds the shape of the data each screen receives.
- `lab/`: `hub.py` is the `Lab` class that owns the database, the mode and the job runner. Mixed into it: `testlab.py` (plans, runs, Evidence Lab), `evidence/export.py`, `fixes/changes.py`, `fixes/views.py`, `migration/state.py`, `migration/system_changes.py`, `dependencies/state.py`, `projects/store.py`, since phase 5b `ledger/checks.py`, `ledger/relations.py` and `projects/overview.py`, and since phase 5c `otto/state.py`. Since phase 5c the engine `Lab` holds is `otto/engine.py`'s `OttoEngine`, around the rule-based engine.
- `evidence/`: `export.py`, the evidence download (the signed JSON file and the readable report; since phase 5c with the `otto` part and report part 8). The command that checks a downloaded file is the separate `backend/evidence/` package (`__main__.py`, and since phase 5c `otto.py`, which checks a file's Otto part).
- `engine/`: `research.py` designs tests. `reviewer.py` is the only place that decides pass or fail. `vectors.py` and `pq_vectors.py` hold the pinned test sets. `guidance.py` holds the NIST wording source. `compare.py` holds the rules that compare a claim with what was found (True, False or Couldn't check). Phase 5c added one kind of test to both, the advisory check (`advisory_cases`).
- `run/`: `runner.py` runs jobs (demo or isolated), `components.py` knows which programs are ours (and holds the byte-for-byte check, `registered_version`), `reference.py` is the reference library (pyca `cryptography`, our yardstick). `run/execute/` runs one kind of test each and returns raw outcomes only: `controls.py`, `pq.py`, `pqstatus.py`, `pqvectors.py`, `server.py`, `signing.py` (since phase 5c it also runs an advisory check), `speed.py`, `capability.py` (phase 4d).
- `checks/`: the Verify step and the network probes: `verify.py`, `tlsprobe.py`, `tls_names.py`, `addresses.py`, `pqprobe.py`, `pqtls.py`.
- `servers/`: our own demo test servers: `demo_server.py`, `extra_servers.py`, `migration_servers.py`, `lab_servers.py`, `lab_nginx.py`.
- `migration/`: `state.py` (the Migration state), `rules.py` (the cost table and placing rules), `change_builder.py`, `system_changes.py` (try, approve, Apply, Roll back).
- `fixes/`: `changes.py` (where every fix stands), `views.py` (the Fixes view), `gitrepo.py` (reads and writes git's format without git).
- `present/`: turns stored verdicts into plain words and decides nothing: `results.py`, `fixes.py`, `migration.py`, `pq.py`, `real.py`, `tracks.py`, `changes.py`, `plain.py`, `dependencies.py`, and since phase 5c `advisory.py` (an advisory check's result and its advisory box) and `otto.py` (the Advisories page and the two Settings sections). Since the 5c fixes: `times.py` (a time inside a sentence: UTC words for a file, a mark for a browser that asks, see the note at its top).
- `projects/` (phase 5a): `store.py` (`ProjectsMixin`: the tree, rename, move, archive, New assessment (with a purpose and a reference; it closes nothing), close as a sign-off, Rerun as new assessment, putting an import into its assessment, adopting older imports, the closed check, the names for evidence), `counts.py` (the real counts of an assessment, read from the pages' own views), `overview.py` (phase 5b: the Overview's blocks and the Project overview), `demo.py` (Load demo projects).
- `ledger/` (phase 5b): `groups.py` (the four work groups, their counts and empty sentences), `checks.py` (every check of every kind, from the records already kept; the Checks view), `relations.py` (the recorded links between items; the Related block), `fixes.py` (the Fixes view's groups). It reads; it decides nothing. Since the 5c fixes `checks.py` also sorts the Encryption tests rows into the four parts Checks shows (`_encryption_parts`: the test plan, retests by version, fix proofs, tries); the ledger's own rows are unchanged.
- `dependencies/` (phase 4d): `state.py` (the Dependencies view: lists, ties, answers, blockers, Fixes entries, evidence part), `tree.py` (top entries and rows), `target.py` (the target interface; only the public pinned copy exists).
- `knowledge/` (phase 4d): `model.py` (the file format and its rules), `base.py` (loading and the lookup), `versions.py` (reading a version).
- `importer/`: reads the scanner file. `common.py` (errors, claim types, helpers), `csv_file.py`, `cbom.py`, `reader.py` (`detect_format`, `parse_file`), and `sbom.py` (phase 4d: a dependency list, CycloneDX or SPDX).
- `otto/` (phase 5c): the adapter between the app and Adam's Otto harness. It decides no result. `harness.py` (finds the pinned copy, checks its fingerprint and loads it by path; says why when it is missing), `designs.py` (a test design is data: the one building block, its control and pass rule, and the locked test made from a design), `packs.py` (the pack format, its signature, the trusted keys, the order) with `trusted-pack-keys.json`, `model.py` (Otto's Claude client: recorded answers, live calls, the spending limit, the key), `state.py` (`OttoMixin`: installed packs, Check for updates and Install update, the Advisories view, the Live Otto setting, the hooks around a run of an advisory check, the evidence part), `proposals.py` (`ProposalsMixin`: what Otto proposes in an assessment, worked out on every read, in four kinds: a check, a fix, a plan change, a dependency update; and a person's decisions on them, the only thing stored), `checks.py` (puts a design into a plan as a locked test), `assurance.py` (the Otto ledger of one assessment) with `checker/recheck.py` and `checker/decisions.py` (the two pinned record checkers the harness runs: runs and Claude steps, and decisions on proposals), `engine.py` (`OttoEngine`, the engine in the socket) and `fixes.py` (the prompt for a change to the customer's own code, and the check on Claude's answer).

## backend/ottolab (phase 5c: Otto's research side)

A build step, run on our own machine. The app never imports this package (a test checks it): only a signed test pack crosses from research to the app.

- `build.py`: the commands `ship`, `next` and `audit` (from the snapshot to signed packs; the exact commands are in `CLAUDE.md`).
- `snapshot.py`: reads the advisory snapshot (data; refused unless it has exactly the known shape).
- `prompts.py`: what Claude is asked for the three research steps (read an advisory, design a test, propose a fix), and the check on each answer.
- `research.py`: the questions, the Claude steps and the registered trials, written in Otto's own records. It judges no trial and decides no result. A design that selects exactly the cases of the check of another advisory about the same library is refused here, before any trial (`same_check_as`).
- `agent.py`: the command Otto's loop starts for each step that needs judgement.
- `pinned/trial.py` (the trial instrument: one arm of one registered experiment, run through Evidence Lab's own lock, run and review path) and `pinned/check_model_step.py` (the checker of a Claude step's record). Both are copied into a lab and pinned there by SHA-256.

## The flow of a request

1. A web route (`web/*.py`) takes the request. Every route needs the login.
2. It calls the `Lab` hub (`lab/hub.py`).
3. The hub asks `engine/` to design the test, `run/` to run it, and `checks/` for measurements.
4. `engine/reviewer.py` judges the raw outcome. Nothing else decides a result.
5. `present/` puts the stored verdict into plain words.
6. The result is a view (a plain dict). The route names its shape with `responses=shows(models.X)`.
7. `web/models.py` is the one place the shape is written. `tools/api_schema.py` and `npm run gen:api` turn it into `frontend/src/api.ts`'s generated types (`api.gen.ts`).
8. A screen in `frontend/src/components/` draws the view.

To change a view: change the backend, then the model, then run the two generators, then the frontend.

## Tests

- Backend tests are in `backend/tests/`; since phase 4d a new feature gets its own folder (`backend/tests/dependencies/`, `backend/tests/projects/`, `backend/tests/otto/`). The 5c fixes added `backend/tests/times/` (a time on screen and in a file), `tests/otto/test_wording.py` (no sentence says what Otto did), `tests/otto/test_new_tag.py`, `tests/ledger/test_checks_parts.py` and `tests/test_devcontainer.py` (the Codespace file and the start script). Frontend tests are next to the frontend code (`npm test`). End-to-end tests are in `e2e/tests/`.
- Two sets of backend tests. The fast set (`pytest -q tests`, a few minutes) leaves out the slow ones and says how many. `--full` runs everything (about 24 minutes with Docker ready).
- A test that needs Docker is slow by itself (`docker_ready` fixture, see `tests/conftest.py`). A test that takes more than about 5 seconds gets `@pytest.mark.slow`; the tests that read one of the long demo walks listed in `SLOW_SHARED_WALKS` (`tests/conftest.py`) are slow by themselves.
- Every JSON answer a test gets from the app is checked against its route's shape (`tests/api_shapes.py`). Test helpers are in `tests/view_helpers.py`.
- A test that needs the Otto harness (phase 5c) is marked `@pytest.mark.needs_otto` (`backend/pytest.ini`). Where the harness is not installed it is skipped, and the run prints one line with the count. GitHub's checks can't fetch the harness (a private repository, no secrets), so those tests are skipped there.
- No test reaches Claude's API: `tests/conftest.py` replaces the client's network function with one that fails the test, and a test of the live path puts its own stand-in there. Tests use the recorded answers in `research/recorded/`, or answers written for the test (`tests/otto/otto_research_fixtures.py`).

## backend/tools

- `api_schema.py` writes the API description to `frontend/src/api-schema.json` (`--check` to compare).
- `typecheck.py` runs mypy against the baseline in `mypy-baseline.txt` (`--write-baseline` after a fix or a move).
- `try_real_library.py` tries one real library by hand (isolated mode).
- `build_bad_signature_cases.py` built the bad-signature cases once.
- `otto_pin.py` shows, checks or moves the pin of the Otto harness (`show`, `check`, `bump COMMIT`; phase 5c). Moving it needs Kevin's OK.

Lint is `ruff` (config `backend/ruff.toml`); since phase 5c it and the type check also cover `ottolab`. Packages are locked in `requirements.lock` and `requirements-dev.lock`. The exact commands are in `CLAUDE.md`.

## Rules you must not break

- **The reviewer stays isolated.** `engine/reviewer.py` imports only `engine/vectors.py`, `engine/pq_vectors.py`, `canonical.py` and `checks/tls_names.py`. `tests/test_engine.py` checks it.
- **Results come only from checks and tests.** `present/` words them and decides nothing. The co-pilot never sets a result.
- **Only our own components run.** The demo components, the pinned lab images and the real libraries in `real_libraries.py`. Real libraries run in isolated mode only. Nothing in an uploaded file is executed.
- **Otto decides nothing (phase 5c).** Nothing in `otto/` or `ottolab/` sets a result. A test pack, the advisory snapshot and a recorded answer are data: nothing in them runs. The Otto harness is one pinned commit (`backend/otto.lock.json`), fetched only by the prepare step and checked by fingerprint; it is not software under test and starts only our own scripts. Only the harness writes `research/lab/ledger.jsonl`, `research/lab/runs/` and an assessment's ledger under the data folder. A ledger read from an evidence file is data too, and nothing it names is ever run: the verify command holds every entry to the exact form this app writes (`otto/assurance.only_our_checker`), lets the harness audit the chain and the records without running any verifier, and runs the app's own pinned checker itself (`otto/assurance.check_again`).
- **The API key for Live Otto** is read only from the environment, at the moment of a call. It is never stored, shown, logged or put in evidence.
- **The answer keys are never edited:** `demo/expected.json`, `demo/expected-migration.json`, `demo/expected-real-libraries.json`, `demo/expected-dependencies.json`, and `demo/expected-otto.json` once it exists. If the app disagrees with a key, fix the app or explain why the key is wrong. Also never edit `docs/wireframes/`.
- **Do not change behaviour to satisfy lint or the type check.**
- **No new dependency** without asking (`docs/SPEC.md` section 3).
- **Git LFS:** new files under `docs/screenshots/` and `demo/vectors/` go to LFS (`.gitattributes`).
