# Handoff: the overnight run of 19 November 2026 (the 5c fixes, then phase 6)

Kevin approved this run in advance and reviews it the next day. A new session must be able to pick up from
this file alone. `CLAUDE.md` and `docs/SPEC.md` still win over this page. The plan for phase 6 is the Claude
Doc "Phase 6 plan: Otto assistant".

- **Branch:** `overnight/fixes-and-phase6`, made from `mvp/crypto-simple` at `5a6b4e4` (the 5c merge).
  Draft pull request: #7. **Never merge it into `mvp/crypto-simple`, and never change the default branch**
  (Kevin's ground rule for this run). Commit after each step that passes its tests; push at least every hour.
- **For this run only**, Kevin lifted "commit only after I say OK".
- **The machine:** after a restart, Docker first (the command is in `docs/HANDOFF-5c.md`, section 7). The
  test images, `backend/.venv`, `backend/.otto` and `node_modules` were all ready when the run started.

## Where the run stands (updated after every step)

Written at 04:50 UTC on 19 November 2026 (machine time), in the middle of the run. The exact next action is
the last section of this file.

| # | Success step | State |
|---|---|---|
| 1 | A brand-new Codespace starts the app with `./run-demo.sh` alone | **Built** (fix 8). Proven on the build machine as far as it can be; **Kevin's own 30-minute check is still needed**: `docs/CODESPACE-CHECK.md` |
| 2 | Checks: Encryption tests in four labelled parts | **Built** (fixes 1 and 2) |
| 3 | "Open in new tab" on every side panel | **Built** (fix 3) |
| 4 | No sentence says what Otto did | **Built** (fixes 4 and 5), with a wording test |
| 5 | Times in the viewer's own time zone; files keep UTC | **Built** (fix 6) |
| 6 | "New" tag on advisories of the newest pack | **Built** (fix 7) |
| 7, 8 | Otto researches by itself ("Look for new advisories") | **Started, not wired in** (step 3): see "Step 3" below |
| 9, 10, 11 | The assistant: suggestions that fit the page, three tabs, decide in the panel | **Built, not committed yet** (phase 6a): see "Step 2" below |
| 12 | Commands | Not started (6b) |
| 13 | Questions | Not started (6c) |
| 14 | What-if and hypotheses | Not started (6e) |
| 15 | Change watch | Not started (6d) |
| 16 | Nothing without a click and Confirm; works without a key | Built for what 6a has (tests in `backend/tests/assistant/`, `frontend/src/test/OttoPanel.test.tsx`) |
| 17 | Keys match in both modes, fast tests under 5 minutes, each step reviewed, committed, pushed | Step 1: committed and pushed; **its long checks and its review are still running** (see step 1) |
| 18 | This file | Kept current |

## Step 1: the 5c fixes (built, committed and pushed; long checks and review still open)

Commits on `overnight/fixes-and-phase6`, oldest first: `f6ba0f2` fix 6 (times), `b274428` fix 8 (Codespace),
`d1e6892` fixes 4 and 5 (wording), `6eacbf2` fixes 1, 2 and 3 (Checks in four parts, Open in new tab),
`f109d54` fix 7 (New tag), `8526aac` the docs and the new walk, `4d43bab` and `dbbe95a` two things the walks
found, `dd21a67` one file put back. **Step 1's final commit is `dd21a67`.**

What the walks found, and what was fixed:
- A real fault in fix 3: a fix opened on a page of its own in a new browser tab said "This item is not
  here", and a plain link to one fix opened in a new tab showed the first fix of the list. The app forgot,
  while logging in, which fix the address named. Fixed in `dbbe95a` (`frontend/src/App.tsx`), with a screen
  test that opens both addresses the way a new tab does.
- The Otto walk and the real-libraries walk expected the earlier wording and the earlier heading level of a
  test-plan group; they now follow the fixes (`8526aac`, `4d43bab`).
- **My slip:** `4d43bab` took the deletion of `frontend/src/components/CopilotPanel.tsx` with it (that
  deletion belongs to phase 6a). So `4d43bab` and `dbbe95a` do not build on their own. `dd21a67` puts the
  file back; from `dd21a67` on the branch builds. Nothing else was affected.

Checked so far on step 1 (the frozen copy at `dd21a67`, in a git worktree under the session's scratchpad):
- Frontend: type check clean, build clean, **704 screen tests passed**.
- The four walks the fixes touched, run again after the fixes: **dependencies 2 of 2, real libraries
  (phase 4c) 2 of 2 including isolated mode, Otto 3 of 3 including isolated mode and "without Otto", the new
  walk `fixes5c.spec.ts` 1 of 1** (24 pictures, dark and light, in `docs/screenshots/phase5c-fixes/`).
- The first complete run of every walk (before those fixes): 89 passed, 4 failed (the three above, and one
  measurement in isolated mode that read "Couldn't check (timeout)" while the machine was busy; it passed
  when run again), 2 did not run because their walk had stopped.
- `python -m app.accuracy --only otto --mode demo`: the 114 printed answers are, line for line, the 5c
  build's (the rewording changed none of them).
- Backend fast set after the rewording: 1600 passed in 5 min 7 s on a busy machine. The three oldest shared
  walks were then moved to the slow set (Kevin's answer to open question 1); **not timed again yet**.

**Still to do for step 1** (each in the frozen copy, one at a time, results go here):
1. One complete run of every walk on `dd21a67` (`cd e2e && npm test`): **running now**.
2. Backend fast set, timed on a quiet machine (must be under 5 minutes).
3. Backend full set (`pytest -q tests --full`, about 24 minutes).
4. The accuracy check, four keys, demo mode and isolated mode.
5. `--only otto --mode isolated`, compared with the same run on the 5c build (worktree `base-5c` at `5a6b4e4`).
6. The separate reviewer's report (started; reads the frozen copy): findings and fixes go here.
7. Commit the 24 new pictures (they are in the main folder, not committed yet) with this file.

Fix 8 (a new Codespace), what was proven and what was not:
- Proven: today's failure reproduced in an Ubuntu 24.04 container and gone with the new `run-demo.sh`
  (also under bash 3.2); the Dev Containers command-line tool (0.90.0, run once with npx, not added to the
  repository) reads `.devcontainer/devcontainer.json` and resolves the image and the three add-ons by their
  fingerprints; a container made from the pinned image runs `./run-demo.sh` until the app answers on port
  8000 (Python 3.12.16, the environment made by the script, Otto ready from a local copy).
- **Not proven here** (the build machine cannot download the add-ons' packages, and has no GitHub
  Codespaces): the three add-ons installing (Node.js 22, Docker inside the Codespace, Git LFS), isolated mode
  inside a Codespace, Otto fetched with GitHub's permission, GitHub's port forwarding. That is what
  `docs/CODESPACE-CHECK.md` (12 steps, about 30 minutes) is for.
- If GitHub refuses add-ons named by fingerprint: name them by version (`node:2`, `docker-in-docker:4`,
  `git-lfs:1`) and commit the lock file GitHub writes; `backend/tests/test_devcontainer.py` then needs its
  pattern changed.

## Step 2: phase 6a, the Otto assistant (built and tested; NOT committed yet)

Everything of 6a is in the working tree of `/home/user/prototype`, uncommitted, on top of `dd21a67`.

What is built:
- **Backend** `backend/app/assistant/` (`threads.py`, `words.py`, `engine.py`) behind `CopilotEngine`; one
  read, `GET /api/assessments/{id}/assistant?page=&item=` (`web/assistant.py`, shape `AssistantView` in
  `web/models.py`). It only reads. Three small reads were added for it: `assessment_core` and
  `next_step_from` (`projects/store.py`), `migration_measure_view` (`migration/state.py`; the Migration
  page's own read writes each system's measurement down the first time, so the panel has a read that
  writes nothing), and `accept_stands` (`otto/proposals.py`).
- **The panel** `frontend/src/components/assistant/OttoPanel.tsx` (title Otto, status line, up to three
  tabs, On this page, Elsewhere, This thread so far, the Confirm step), `send.ts` (a next step is sent
  through the page button's own call), `frontend/src/changes.ts` (after a change sent from the panel the
  open page reads its view again; after any change the panel reads again). `CopilotPanel.tsx` is removed.
  Every open side panel now tells the app which item it shows (`OpenItemContext` in `layout.tsx`).
- **A typed name, asked once** (Kevin's answer to open question 4): `POST /api/otto/name`, Settings section
  "Who decides", and a field in the panel's first Confirm of a decision. Decisions are recorded under the
  name (`otto/state.py` `decision_name`, used by `otto_decide`); "You" until one is typed.
- **Docs**: SPEC sections 1, 2, 3, 9, 10, 12; CLAUDE.md (the two approved rule changes for 6a, a line about
  the name, the Tests rule, the walk in Commands); README; LAYOUT; LIMITS ("Limits of phase 6a").
- **Two sentences differ from the plan**: "Nothing is suggested on this page." and "Bring in a scanner file
  to start. Nothing is suggested yet." (the plan had "Otto has nothing to suggest…", which the 5c fixes
  rule out). For Kevin to confirm.

Tests so far (all in the working tree):
- `backend/tests/assistant/`: **46 passed** (the table of threads; what fits each page at seven stages of
  one walk; on this page plus elsewhere equals "Waiting for you"; tabs and their marks; the Confirm steps;
  closed, and without Otto; the code only reads, and a read leaves every table row and every file as it
  was, also on an assessment whose pages nobody has opened; a read never asks Claude with Live Otto on; a
  decision from the panel compared field for field with the same decision on its page; the typed name).
  Lint and type check clean; the generated files are up to date.
- Frontend: **766 screen tests passed** (60 new for the panel in `OttoPanel.test.tsx`, 2 for Settings, 1 for
  the open item; the tests that pinned the old empty panel were rewritten).
- The walk `e2e/tests/assistant.spec.ts`: **not passed yet**. On its last try it got through Import, Verify,
  Checks, Evidence and Fixes up to the pull request; one expectation of the walk itself was wrong (it
  pressed Approve for a reviewer who was not asked) and is corrected. It has to be run again
  (`cd e2e && E2E_APP_PORT=8110 E2E_DEMO_TLS_PORT=8543 npx playwright test tests/assistant.spec.ts --trace off`
  while another run uses the usual ports; `npm --prefix ../frontend run build` first). Its pictures go to
  `docs/screenshots/phase6a/`.
- The separate reviewer for 6a is started (reads the working tree); its findings go here.

**Still to do for 6a:** the walk green; the reviewer's findings fixed; the backend fast set timed with the
new tests in it (the shared walk of the panel's tests takes about 25 to 35 seconds; if the fast set goes
over five minutes, mark `tests/assistant/assistant_walk.py`'s readers slow or shorten the walk); the
accuracy check in both modes; then commit (with pictures) and push.

## Step 3: Otto's research loop, "Look for new advisories" (started)

Kevin's priority. The design is in the plan doc (section "New step: Otto's research loop"). What exists in
the working tree, **not wired into the app yet**:
- `backend/app/otto/lookup.py` (done, with `backend/tests/otto/test_lookup.py`, 15 tests): the reader of a
  public source. It asks OSV (`https://api.osv.dev/v1/query`) with a package's name and ecosystem and
  nothing else; takes an answer only in OSV's documented shape; drops any score or severity; works out on
  this computer whether an advisory names a version the assessment has; and reads a "recorded source" (a
  folder of recorded answers, for tests and walks). `tests/conftest.py` keeps every test off the network.
- `backend/app/otto/discover.py` (drafted, not imported anywhere yet): `DiscoverMixin` for the `Lab`:
  `look_for_advisories(plan_id)`, `start_research(plan_id)` (runs `python -m ottolab.build next …` as a
  process of its own, then installs the pack it made), `lookup_view`, `lookups_evidence`.
- `backend/app/present/lookup.py` (drafted): every sentence of the block "New advisories".

How it is meant to work: a click on **Look for new advisories** (Advisories page) reads the source and lists
what it found; a click on **Design and prove tests** runs the research command for the new advisories that
can be tried here; what it proves is signed into a test pack made on this computer and installed by the
same click (after any built-in pack not installed yet); a proven check then shows on Advisories as a
proposal like any other; an advisory with no proven test says why.

**Still to do for step 3:** two add-only tables in `db.py` (`otto_lookups`, `otto_research`) and their rows
(`OttoLookupRow`, `OttoResearchRow`: the fields are the ones `discover.py` writes); a setting
`advisory_source_dir` (`EVIDENCE_LAB_ADVISORY_SOURCE`) in `config.py`; `DiscoverMixin` into `Lab`
(`lab/hub.py`, and `_init_discover()`); the block in the Advisories view (`otto/state.py`,
`present/otto.py`, `web/models.py`); two routes in `web/otto.py` (`POST /api/plans/{id}/advisories/look` and
`…/research`, under the closed guard); the `lookups` part of the evidence file and one line of the verify
command; the block and its two boxes on `AdvisoriesScreen.tsx`; tests (fast: recorded source, states,
reasons, shapes; slow, Docker: a real research run on the three elliptic advisories with only pack
2026.11.1 installed, which the recorded answers cover); a walk; SPEC section 2, CLAUDE.md (new safety
lines: the one network read, and "installed by the same click"), LIMITS, README.

What Kevin must know about step 3 (also in "Decisions for Kevin"):
- **The read from osv.dev could not be tried from the build machine** (that address is not reachable from
  it). The reader is tested against answers in OSV's documented shape, written for the tests.
- **With the versions pinned today, real new advisories will mostly read "No test yet".** A test is proven
  against a public copy of the fixed version, and the app has only elliptic 6.5.6 and 6.5.7, python-ecdsa
  0.13.2 and 0.13.3, and Java 17.0.2 and 17.0.3. Newer elliptic advisories are fixed in 6.6.0 and 6.6.1.
  Pinning more versions is a dependency change that needs Kevin's OK.
- Java and OpenSSL are not asked about: OSV keeps them nowhere by name.

## Decisions for Kevin (collected so far)

1. Run the Codespace check (`docs/CODESPACE-CHECK.md`, about 30 minutes): it is the part of fix 8 that
   could not be proven on the build machine.
2. Two panel sentences differ from the plan's wording (see step 2). Keep them, or word them another way?
3. Sentences outside the phrases Kevin listed that still name Otto as acting were left as they are (for
   example "Otto proposes; a person decides" in code comments and docs only; no screen sentence).
   Dates without a time of day (a pack's build date, an advisory's publication date) stay as written.
   The ledger's own statement about a proposal's decisions was left unchanged, so a ledger written today
   reads like one written by the 5c build.
4. The typed name (open question 4) is built: asked once in the panel, changeable in Settings. Approvals of
   a pull request or of a server change still use "You" and the two demo reviewers. Should they use the
   typed name too?
5. A next step in the panel sends Open pull request and Ask for approval with the reviewers the page ticks
   by default. Is that right, or should the panel only open the page for these two?
6. Research loop: pin more public copies (for example elliptic 6.6.0 and 6.6.1) so that newer advisories
   can be proven? Each is a new pinned download.
7. Research loop: the pack made by "Design and prove tests" is installed by that same click (Kevin: "nobody
   installs a test pack to get new checks"). CLAUDE.md said "A person installs it"; the rule gets one more
   sentence. Please confirm the wording when it is written.
8. The fast test set: three shared walks moved to the slow set, as decided. If the panel's tests push it
   over five minutes again, more has to move, or tests run in parallel (a new developer-only package).

## The exact next action

1. Wait for the complete run of every walk on step 1 (`dd21a67`, in the frozen copy
   `<scratchpad>/step1`); read its result; if a walk fails, fix it on the branch and run that walk again.
2. Run `e2e/tests/assistant.spec.ts` (the command is under step 2) until it passes; keep its pictures.
3. Read the two reviewers' reports (step 1 and phase 6a); fix what breaks a requirement.
4. Run step 1's remaining long checks in the frozen copy, one at a time: the fast set (timed), the full
   set, the accuracy check in both modes, `--only otto` in isolated mode against the 5c build.
5. Commit phase 6a (code, tests, docs, pictures) and push. Tick nothing in `docs/ACTIVE.md` yet.
6. Wire step 3 (the list under "Still to do for step 3"), test it, review it, commit and push.
7. Then 6b, 6c, 6d and 6e, each at least its shorter first half.

## Appendix: the plan for step 1 as written before it was built

Build order, as Kevin set it: 8, then 6, then 4 and 5, then 1 and 2, then 3, then 7. One commit for each
fix (or pair), each after its own tests pass; the full checks and the separate review at the end of the step.

**Fix 8. A fresh Codespace.** Files: `.devcontainer/devcontainer.json` (the official Python 3.12 image
and the features Node.js 22, Docker inside the Codespace and Git LFS, each pinned by fingerprint; the
Otto read permission kept as it is), `run-demo.sh` (step 1 and step 3: the first Python 3.12 that can
make the environment; a half-made `backend/.venv` is remade; otherwise one plain sentence), `README.md`
("In a Codespace"), `backend/tests/test_devcontainer.py`, one line each in `CLAUDE.md` and
`docs/LAYOUT.md`. Proof: today's failure reproduced in an Ubuntu 24.04 container, a rehearsal with the
Dev Containers command-line tool (run once with npx, not added to the repository), and the steps for
Kevin's own 30-minute check (below, when written).

**Fix 6. Times.** One shared formatter in the browser, `frontend/src/time.ts`: "18 November 2026,
7:46 pm EST", in the viewer's own zone. Two kinds of time reach the screen:
- a time the browser writes from a recorded instant (every `formatTime` call; the second copy in
  `VerifyScreen.tsx` goes);
- a time inside a sentence the server words (`present/otto.py` `stamp`, `present/changes.py` `when`,
  one line of `present/migration.py`). The browser asks for marked times with a request header; the
  server then writes `[[time:<instant>]]` in the sentence in place of the UTC words, and the one
  place in the browser that reads every answer (`frontend/src/api.ts`) writes the local time there.
  Without that header (scripts, the accuracy check, the tests, a download) every sentence is, byte
  for byte, what it was. The evidence file, the report, the downloads and both ledgers never carry a
  mark: a backend test walks the demo with the header on and then reads the database, the ledgers and
  the evidence file for one.
- Dates with no time of day (a pack's build date, an advisory's publication date, a review date) stay
  as they are written.
Files: `backend/app/present/times.py` (new), `present/otto.py`, `present/changes.py`,
`present/migration.py`, `web/common.py` or `main.py` (the header), `evidence/export.py` (never
marked), `backend/tests/test_times.py`; `frontend/src/time.ts`, `api.ts`, `components/ui.tsx`,
`VerifyScreen.tsx`, `src/test/time.test.ts`, the test setup (New York time);
`e2e/playwright.config.ts` (the browser runs in New York time).

**Fixes 4 and 5. Wording.** Every sentence that says what Otto did is reworded to say what is proposed
or written, in short sentences. Kept as they are: "From Otto", "Written by Otto", "Not written yet",
"Live Otto", "Otto in this project", the harness and "Otto is not installed" lines, "Otto ledger
entries", "No recorded answer: this needs Live Otto.", "Otto has no say in any result.", the statuses
and titles. Files: `backend/app/present/otto.py`, `present/fixes.py`, `present/advisory.py`,
`present/dependencies.py`, `otto/proposals.py`, `otto/state.py`, `otto/engine.py`, `otto/fixes.py`,
`fixes/changes.py`, `projects/store.py`, `ledger/checks.py`, `lab/testlab.py`, the frontend
components that hold such a sentence, and a wording test on both sides that fails on the phrases.
A decision already recorded keeps the copy and the fingerprint it was made on (a test makes a
decision on the old wording and reads it back); the printed `--only otto` answers must match the 5c
build's.

**Fixes 1 and 2. Checks.** Only the Encryption tests group changes. Four labelled, foldable parts,
each with a count: Test plan (Standard tests, and Advisory checks marked From Otto; a card moves only
within its own list), Retests by version (one block per version, newest open; Retest new version with
the same menu, rules and reasons as on Evidence, from one shared component), Fix proofs (one block per
proof, with the changed code's version) and Tries on a test copy (only when a server change was
tried). Files: `backend/app/ledger/checks.py` and `web/models.py` (each row says its part, its
version and its retest), `frontend/src/components/ChecksScreen.tsx`, `TestsScreen.tsx`,
`EvidenceLabScreen.tsx`, a new `components/lab/RetestMenu.tsx`, `components/checks/`, their tests,
and `e2e/tests/layout.spec.ts`.

**Fix 3. Open in new tab.** `components/layout.tsx` (the panel header gets "Open in new tab ↗" beside
Wider, Narrower and ×, and a slot for phase 6's own buttons), `router.ts` (`view=page`), `App.tsx`
and each page with a panel (the item on its own page, "← Back to *page*", the browser tab named after
the item, "not found" with the Back link, a closed assessment read-only), their tests and the layout
walk.

**Fix 7. New tag.** `backend/app/otto/state.py` and `present/otto.py` (an advisory whose first arrival
came with the most recently installed pack; a closed assessment uses the packs installed when it was
closed), `web/models.py`, `components/advisories/`, their tests.

**Docs at the end of the step:** SPEC section 2 (and 3, 7f, 12 where these touch), README, LAYOUT,
LIMITS, HANDOFF, ACTIVE, one Codespace line in CLAUDE.md. Screenshots in
`docs/screenshots/phase5c-fixes/` (dark and light).

