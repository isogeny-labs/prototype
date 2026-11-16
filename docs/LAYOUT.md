# Where things live

A one-page map for a new engineer. Read `CLAUDE.md` first: its rules win over this page. For records and
shapes see `docs/ENGINE.md`; for how software under test is run see `docs/ADAPTER.md`.

## Top folders

| Folder | What is in it |
|---|---|
| `backend/` | Python 3.12, FastAPI, SQLite. `app/` is the code, `tests/` the tests, `tools/` small commands, `evidence/` the command that checks a downloaded evidence file. |
| `frontend/` | React, TypeScript, Vite, Tailwind. `src/App.tsx` is the shell (phase 5a: sidebar, top bar, hash routes in `src/router.ts`). `src/components/` has one screen file per step; `components/shell/` the sidebar, top bar, project switcher and guided-demo bar; `components/pages/` Projects, Overview and Settings; `components/layout.tsx` the page header, summary cards, table and detail panel. `src/readOnly.tsx` turns action buttons off in a closed assessment; `src/prefs.ts` keeps the look, the collapsed sidebar and the guided-demo switch in the browser; `src/plainNames.ts` puts plain names first. It draws only what the backend sends. |
| `e2e/` | The Playwright end-to-end test. It writes screenshots to `docs/screenshots/`. Each walk starts its own project (`openFreshAssessment` in `tests/shared.ts`); `tests/projects.spec.ts` walks projects and assessments. |
| `demo/` | Demo data: claims files, the demo components, the real-library wrappers, the pinned test sets, the bundled demo repository, the dependency lists (phase 4d), and the four answer keys. |
| `knowledge/` | The library knowledge base (phase 4d): one JSON file per library under `libraries/`, `schema.json`, and `README.md` with the rules. Data only. |
| `docs/` | The spec, limits, handoff, engine and adapter notes, the blind test, screenshots. This page. |
| `.github/workflows/` | `checks.yml` (every push and pull request) and `slow.yml` (nightly and by hand). |

## backend/app, folder by folder

Every import is absolute (`from app.x.y import z`).

At the top (commands and parts shared by everything):
- `main.py` creates the app and includes the routers. `__main__.py` starts it.
- Commands: `accuracy.py` (+ `accuracy_real.py`, and `accuracy_deps.py` since phase 4d), `prepare.py`, `blind.py`, `demo_repo.py`.
- Shared: `config.py`, `db.py`, `errors.py`, `auth.py`, `jobs.py`, `names.py`, `canonical.py`.
- `real_libraries.py` lists the real libraries, their pins and advisories. It stays at the top because a safety rule names it.

Folders:
- `web/`: the HTTP routes, split by step: `session.py`, `importing.py` (import and verify), `tests.py`, `lab.py` (Evidence Lab), `migration.py`, `changes.py`, `fixes.py`, `dependencies.py` (phase 4d), `projects.py` (phase 5a: the organization, folders, projects, assessments, Load demo projects, and the closed guard that `main.py` puts on every step router). `common.py` holds request bodies, helpers and `shows()`. `models.py` holds the shape of the data each screen receives.
- `lab/`: `hub.py` is the `Lab` class that owns the database, the mode and the job runner. Mixed into it: `testlab.py` (plans, runs, Evidence Lab), `evidence/export.py`, `fixes/changes.py`, `fixes/views.py`, `migration/state.py`, `migration/system_changes.py`, `dependencies/state.py` and `projects/store.py`.
- `evidence/`: `export.py`, the evidence download (the signed JSON file and the readable report). The command that checks a downloaded file is the separate `backend/evidence/` package.
- `engine/`: `research.py` designs tests. `reviewer.py` is the only place that decides pass or fail. `vectors.py` and `pq_vectors.py` hold the pinned test sets. `guidance.py` holds the NIST wording source. `compare.py` holds the rules that compare a claim with what was found (True, False or Couldn't check).
- `run/`: `runner.py` runs jobs (demo or isolated), `components.py` knows which programs are ours, `reference.py` is the reference library (pyca `cryptography`, our yardstick). `run/execute/` runs one kind of test each and returns raw outcomes only: `controls.py`, `pq.py`, `pqstatus.py`, `pqvectors.py`, `server.py`, `signing.py`, `speed.py`, `capability.py` (phase 4d).
- `checks/`: the Verify step and the network probes: `verify.py`, `tlsprobe.py`, `tls_names.py`, `addresses.py`, `pqprobe.py`, `pqtls.py`.
- `servers/`: our own demo test servers: `demo_server.py`, `extra_servers.py`, `migration_servers.py`, `lab_servers.py`, `lab_nginx.py`.
- `migration/`: `state.py` (the Migration state), `rules.py` (the cost table and placing rules), `change_builder.py`, `system_changes.py` (try, approve, Apply, Roll back).
- `fixes/`: `changes.py` (where every fix stands), `views.py` (the Fixes view), `gitrepo.py` (reads and writes git's format without git).
- `present/`: turns stored verdicts into plain words and decides nothing: `results.py`, `fixes.py`, `migration.py`, `pq.py`, `real.py`, `tracks.py`, `changes.py`, `plain.py`, `dependencies.py`.
- `projects/` (phase 5a): `store.py` (`ProjectsMixin`: the tree, rename, move, archive, New assessment, close, putting an import into its assessment, adopting older imports, the closed check, the names for evidence), `counts.py` (the real counts of an assessment, read from the pages' own views), `demo.py` (Load demo projects).
- `dependencies/` (phase 4d): `state.py` (the Dependencies view: lists, ties, answers, blockers, Fixes entries, evidence part), `tree.py` (top entries and rows), `target.py` (the target interface; only the public pinned copy exists).
- `knowledge/` (phase 4d): `model.py` (the file format and its rules), `base.py` (loading and the lookup), `versions.py` (reading a version).
- `importer/`: reads the scanner file. `common.py` (errors, claim types, helpers), `csv_file.py`, `cbom.py`, `reader.py` (`detect_format`, `parse_file`), and `sbom.py` (phase 4d: a dependency list, CycloneDX or SPDX).

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

- Backend tests are in `backend/tests/`; since phase 4d a new feature gets its own folder (`backend/tests/dependencies/`, `backend/tests/projects/`). Frontend tests are next to the frontend code (`npm test`). End-to-end tests are in `e2e/tests/`.
- Two sets of backend tests. The fast set (`pytest -q tests`, a few minutes) leaves out the slow ones and says how many. `--full` runs everything (about 24 minutes with Docker ready).
- A test that needs Docker is slow by itself (`docker_ready` fixture, see `tests/conftest.py`). A test that takes more than about 5 seconds gets `@pytest.mark.slow`; the tests that read one of the long demo walks listed in `SLOW_SHARED_WALKS` (`tests/conftest.py`) are slow by themselves.
- Every JSON answer a test gets from the app is checked against its route's shape (`tests/api_shapes.py`). Test helpers are in `tests/view_helpers.py`.

## backend/tools

- `api_schema.py` writes the API description to `frontend/src/api-schema.json` (`--check` to compare).
- `typecheck.py` runs mypy against the baseline in `mypy-baseline.txt` (`--write-baseline` after a fix or a move).
- `try_real_library.py` tries one real library by hand (isolated mode).
- `build_bad_signature_cases.py` built the bad-signature cases once.

Lint is `ruff` (config `backend/ruff.toml`). Packages are locked in `requirements.lock` and `requirements-dev.lock`. The exact commands are in `CLAUDE.md`.

## Rules you must not break

- **The reviewer stays isolated.** `engine/reviewer.py` imports only `engine/vectors.py`, `engine/pq_vectors.py`, `canonical.py` and `checks/tls_names.py`. `tests/test_engine.py` checks it.
- **Results come only from checks and tests.** `present/` words them and decides nothing. The co-pilot never sets a result.
- **Only our own components run.** The demo components, the pinned lab images and the real libraries in `real_libraries.py`. Real libraries run in isolated mode only. Nothing in an uploaded file is executed.
- **The answer keys are never edited:** `demo/expected.json`, `demo/expected-migration.json`, `demo/expected-real-libraries.json`, `demo/expected-dependencies.json`. If the app disagrees with a key, fix the app or explain why the key is wrong. Also never edit `docs/wireframes/`.
- **Do not change behaviour to satisfy lint or the type check.**
- **No new dependency** without asking (`docs/SPEC.md` section 3).
- **Git LFS:** new files under `docs/screenshots/` and `demo/vectors/` go to LFS (`.gitattributes`).
