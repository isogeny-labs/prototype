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

Written at 05:45 UTC on 19 November 2026 (machine time), in the middle of the run. The exact next action is
the section before the appendix.

| # | Success step | State |
|---|---|---|
| 1 | A brand-new Codespace starts the app with `./run-demo.sh` alone | **Built** (fix 8). Proven on the build machine as far as it can be; **Kevin's own 30-minute check is still needed**: `docs/CODESPACE-CHECK.md` |
| 2 | Checks: Encryption tests in four labelled parts | **Built** (fixes 1 and 2), reviewed, review findings fixed |
| 3 | "Open in new tab" on every side panel | **Built** (fix 3), reviewed, review findings fixed |
| 4 | No sentence says what Otto did | **Built** (fixes 4 and 5), with a wording test; seven more sentences reworded after the review |
| 5 | Times in the viewer's own time zone; files keep UTC | **Built** (fix 6) |
| 6 | "New" tag on advisories of the newest pack | **Built** (fix 7) |
| 7 | "Look for new advisories" reads a public source and finds what fits | **Built and committed** (step 3, first part). The read from osv.dev itself could not be tried from the build machine |
| 8 | Otto designs a test and proves it on public copies after a click; only then a proposal | **Built and committed**; the real run in containers is a slow test, **running now** in the full suite. Walk, pictures and separate review **still to do** |
| 9, 10, 11 | The assistant: suggestions that fit the page, three tabs, decide in the panel | **Built, committed, reviewed, review findings fixed** (phase 6a). Its walk was reworked after the review and **has to be run to green** |
| 12 | Commands | Not started (6b) |
| 13 | Questions | Not started (6c) |
| 14 | What-if and hypotheses | Not started (6e) |
| 15 | Change watch | Not started (6d) |
| 16 | Nothing without a click and Confirm; works without a key | Built for what 6a and the research loop have, with tests |
| 17 | Keys match in both modes, fast tests under 5 minutes, each step reviewed, committed, pushed | Steps 1 and 2 reviewed, fixed, committed and pushed. **Still open:** the fast set's time, the full set's result (running), the accuracy check in both modes after tonight's changes |
| 18 | This file | Kept current |

Commits on `overnight/fixes-and-phase6` since the 5c merge (`5a6b4e4`), oldest first, all pushed:
`f6ba0f2` fix 6 · `b274428` fix 8 · `d1e6892` fixes 4 and 5 · `6eacbf2` fixes 1, 2 and 3 · `f109d54` fix 7 ·
`8526aac` docs and the new walk · `4d43bab`, `dbbe95a` two things the walks found · `dd21a67` one file put
back (**step 1 as first built**) · `e50d1a7` this file and 24 pictures · `cc96b18` **phase 6a** ·
`a19bb0f`, `ea1329a` **step 1, the review's findings fixed** · `07ad491` **the research loop, first part** ·
`77c001a` **phase 6a, the review's findings fixed**.

## Step 1: the 5c fixes (built, reviewed, findings fixed, committed and pushed)

**Test results on step 1 as first built (`dd21a67`, a frozen copy):**
- Frontend: type check clean, build clean, 704 screen tests passed.
- Every end-to-end walk, one complete run (36.5 minutes): **73 passed, 1 failed, 22 did not run**. The one
  failure was the first test of `phase3a.spec.ts`; the 22 are the rest of that file, which stops at its first
  failure. That file alone, run right after: **23 passed** (5.5 minutes). So every walk has passed on
  `dd21a67`. The failure was real, though rare: see "What the complete run found" below.
- The four walks the fixes touched, each run again after its fix: dependencies 2 of 2, real libraries
  (phase 4c) 2 of 2 including isolated mode, Otto 3 of 3 including isolated mode and "without Otto", the new
  walk `fixes5c.spec.ts` 1 of 1 (24 pictures, dark and light, in `docs/screenshots/phase5c-fixes/`).
- `python -m app.accuracy --only otto --mode demo`: the 114 printed answers are, line for line, the 5c
  build's (the rewording changed none of them).
- Backend fast set after the rewording: 1600 passed in 5 min 7 s on a busy machine. The three oldest shared
  walks were then moved to the slow set (Kevin's answer to open question 1). **Not timed again yet.**

**What the separate reviewer found (5 findings), and what was done** (`a19bb0f`, `ea1329a`):
1. *An item's own page had no standing line and hid the reason when a click was refused.* Fixed: an item on
   a page of its own carries "Passing these tests doesn't prove a system secure. It shows these specific
   checks passed." under the item (every page but Import), and what the hidden list page has to say (the
   reason a click was refused, a page that could not be loaded) is drawn above the item. Four screen tests.
2. *The Test plan heading named one program when the file names several.* Fixed: "First runs, on the
   versions the file names: openjdk 17.0.2, python-ecdsa 0.13.2, elliptic 6.5.6 and openssl 3.5.9." Three
   backend test cases.
3. *"No sentence says what Otto did" held only for the listed phrases; one listed phrase survived in the
   pack builder.* Fixed: three reasons the pack builder writes into a new pack ("Otto has no ..."), and seven
   more sentences that named Otto as acting (the Live Otto status lines, the spending limit's note, "An
   advisory Otto could not read", "Otto's own change is not offered here", the evidence file's note). Each
   is listed before and after in `docs/LIMITS.md` ("Limits of the 5c fixes", Wording). The wording test now
   reads the pack builder and holds these too. The two shipped packs hold none of them and were not rebuilt.
4. *The step's record was not in its commit.* It was committed right after (`e50d1a7`: this file with the
   Codespace proof, and the 24 pictures).
5. *Smaller:* after Retest new version on Checks the plan is now read again (Run all turns off at once);
   "Came from: After Apply" finds a retest's run in its block, and a block with no match is left out instead
   of saying nothing has finished; an item's own page no longer says "This item is not here" while Evidence
   still waits for the list it looks the item up in. Screen tests for each.
- The reviewer confirmed as met: fix 8 (all four fingerprints exist in the registries), fix 6, fixes 1 and 2,
  fix 3 (all nine panels), fixes 4 and 5 for the listed phrases, fix 7, and that the answer keys, the
  wireframes, both pinned checkers, `research/` and the lock files are untouched.

**What the complete run found** (fixed in `ea1329a`): on a slow computer the test plan on Checks is drawn
before the rest of the page has been read, and was then drawn again when the rest arrived. A "+ Add test"
menu opened in between closed. (This was so before tonight too; the busier Checks page made it show.) The
plan is now drawn once and moved into its part. Two screen tests.

**Found and not fixed (older than tonight, rare):** one server error in the complete run's log. While a
migration setting is being changed, a page read at that very moment can fail once
(`present/migration.py`, `change_fix_view`: the change it describes is gone between two reads). The next
read is fine and no walk failed on it. For a later fix: read the migration state once for a whole Fixes view.

**Three slow tests** still expected the old wording and were updated (`tests/otto/test_otto_fix.py`,
`tests/otto/test_otto_evidence.py`). They run only in the full set, which is running now on a frozen copy
of the work as it stood at 05:17 (see "The exact next action").

**Still open for step 1:**
1. The backend full set (`pytest -q tests --full`): **running now** on a frozen copy
   (`<scratchpad>/snap1`, output in `<scratchpad>/full-snap1.txt`). Fix what fails.
2. The backend fast set, timed on a quiet machine (must be under 5 minutes).
3. The accuracy check, four keys, demo mode and isolated mode, on the branch as it is now.
4. `--only otto --mode isolated`, compared with the same run on the 5c build (worktree `base-5c` at
   `5a6b4e4`; run it with the main checkout's Python and `EVIDENCE_LAB_OTTO_HOME=/home/user/prototype/backend/.otto`).

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

## Step 2: phase 6a, the Otto assistant (built, committed, reviewed, findings fixed; the walk must still run green)

Commits: `cc96b18` (the phase), `77c001a` (the review's findings).

What is built:
- **Backend** `backend/app/assistant/` (`threads.py`, `words.py`, `engine.py`) behind `CopilotEngine`; one
  read, `GET /api/assessments/{id}/assistant?page=&item=` (`web/assistant.py`, shape `AssistantView` in
  `web/models.py`). It only reads. Small reads were added for it: `assessment_core` and `next_step_from`
  (`projects/store.py`), `migration_measure_view` (`migration/state.py`), `accept_stands`
  (`otto/proposals.py`), `otto_limit_words` (`otto/state.py`).
- **The panel** `frontend/src/components/assistant/OttoPanel.tsx` (title Otto, status line, up to three
  tabs, On this page, Elsewhere, This thread so far, the Confirm step), `send.ts` (a next step is sent
  through the page button's own call), `frontend/src/changes.ts` (after a change sent from the panel the
  open page reads its view again; after any change the panel reads again). `CopilotPanel.tsx` is removed.
- **A typed name, asked once** (Kevin's answer to open question 4): `POST /api/otto/name`, Settings section
  "Who decides", and a field in the panel's first Confirm of a decision.
- **Docs**: SPEC sections 1, 2, 3, 9, 10, 12; CLAUDE.md; README; LAYOUT; LIMITS ("Limits of phase 6a").

Test results: `backend/tests/assistant/`: **45 passed** (the folder, with its slow ones). Frontend:
**791 screen tests passed** (65 for the panel). Lint and type check clean; generated files up to date.

**What the separate reviewer found (7 findings and 3 smaller points), and what was done** (`77c001a`). The
reviewer found no path that breaks the panel's rules: the read only reads, nothing is sent before Confirm,
and each Confirm request equals the page's.
1. *Measure status: the Confirm step said less than what is sent* ("one handshake to each server"). Fixed:
   it lists what the two locked measurements do, in their own method's words. Backend test.
2. *The end-to-end proof was missing, and Planning was not in it.* The walk is reworked (see below). **It
   has not been run since: this is the next thing to do for 6a.**
3. *Retest now went to Evidence with nothing open.* Fixed: it lands on the result the fix came from, as the
   page's button does. Screen test.
4. *The Fixing tab's "something new" mark missed a server change's steps, and a returned tab could vanish.*
   Fixed, with a backend test and a screen test.
5. *The Confirm step:* it now shows only on the card that was pressed, its fields have ids of their own,
   the keyboard's place moves into it and back to the button on Cancel, and it closes when a new read turns
   its button off. Four screen tests.
6. *A reason that was not the page's* (tests running, when a proof was). Fixed: the server's own sentence.
7. *The panel stopped asking again after one failed read.* Fixed. Screen test.
- Smaller: a Run card now stays while its test runs and says so; Connect demo code with Live Otto on names
  the most the click can spend; **not done:** eleven of the thirteen next-step screen tests compare with a
  typed request, not with the real page component (the two that do are Run and Run all).

**The walk** `e2e/tests/assistant.spec.ts`, as reworked (uncommitted until it is green): the name is typed
at the first Confirm ("A tester") and every decision is recorded under it; Measure status is pressed from
the panel right after Run all, the Planning tab opens with a plan change, it is accepted in the panel and
the Systems page and the Roadmap say the same; Retest now lands on the result; after the retest the plan
change reads done; the evidence holds nine decisions. Pictures `01` to `18`, dark and light, go to
`docs/screenshots/phase6a/` (delete that folder first: it holds pictures of the earlier walk).
Run it with `cd frontend && npm run build`, then
`cd e2e && npx playwright test tests/assistant.spec.ts --trace off` (nothing else may use ports 8010/8443).
Expect a few expectations of the walk itself to need a correction on its first run.

**Still open for 6a:** the walk green and its pictures committed; the fast set timed with the panel's tests
in it (their shared walk takes about 25 to 35 seconds); the accuracy check in both modes.

## Step 3: Otto's research loop (first part built and committed; walk, review and pictures still to do)

Commit: `07ad491`. Its documents are written but **not committed yet** (SPEC sections 2, 3, 7f point 14 and
9; CLAUDE.md; LIMITS "Limits of Otto's research loop"; README; LAYOUT), together with a one-line change
(the request to the source names its client as plain "advisory-reader").

What is built:
- **Look for new advisories** (Advisories, block "New advisories"). `backend/app/otto/lookup.py` asks OSV
  (`https://api.osv.dev/v1/query`) with a package's name and ecosystem and nothing else, takes an answer
  only in OSV's documented shape, reads no severity, and works out on this computer whether an advisory
  names a version the assessment has. A folder of recorded answers can stand in for the source
  (`EVIDENCE_LAB_ADVISORY_SOURCE`). `tests/conftest.py` keeps every test off the network.
- **Design and prove tests.** `backend/app/otto/discover.py` starts the research command
  (`python -m ottolab.build next`) as a process of its own for the new advisories that can be tried here,
  then installs the pack it made (after any built-in pack not installed yet). A proven check is then a
  proposal on Advisories like any other; an advisory with no proven test says why. Off, with the reason, in
  demo mode, without Otto, in a closed assessment, while a run goes on, and when nothing can be tried.
- **The record.** Two add-only tables (`otto_lookups`, `otto_research`); a `lookups` part in the signed
  evidence; the verify command checks it and prints one line about it.
- **The screen.** `frontend/src/components/advisories/NewAdvisories.tsx`: the two buttons, each behind a box
  that says what it will do; the list of what was found, each with where it stands and why; the run's
  progress.
- **A way to see it** with no internet and no key: `backend/tools/research_demo.py DIR` (README, "Looking
  for new advisories").

Test results: `tests/otto/test_lookup.py` 15 passed (with a seeded fuzz test); `tests/otto/test_discover.py`
10 passed; `NewAdvisories.test.tsx` and `Advisories.test.tsx` 93 passed; lint and type check clean. The
real run in containers, `tests/otto/test_discover_real.py`, is in the full set that is **running now**.

**Still to do for step 3:**
1. Read the real run's result in the full set; fix what it shows.
2. An end-to-end walk `e2e/tests/research.spec.ts` with pictures: in isolated mode, on a folder prepared
   like `research_demo.py` does (a copy of the app started with `EVIDENCE_LAB_OTTO_UPDATES` and
   `EVIDENCE_LAB_ADVISORY_SOURCE`): Look, Design and prove tests, the proposal, Accept, Run, the result, the
   evidence verified. In demo mode: Look, and the second button off with its reason.
3. The separate reviewer against SPEC, CLAUDE.md and the plan; fix what it finds.
4. Check that the Otto panel still reads Advisories correctly (the view got a new part), and that the four
   answer keys still match.
5. Commit the documents, the walk and the pictures; push.

What Kevin must know about step 3 (also in "Decisions for Kevin"):
- **The read from osv.dev could not be tried from the build machine** (that address is not reachable from
  it). The reader is tested against answers in OSV's documented shape, written for the tests. The first real
  look is one click for Kevin on a computer with internet.
- **With the versions pinned today, real new advisories will mostly read "No test yet".** A test is proven
  against a public copy of the fixed version, and the app has only elliptic 6.5.6 and 6.5.7, python-ecdsa
  0.13.2 and 0.13.3, and Java 17.0.2 and 17.0.3. Newer elliptic advisories are fixed in 6.6.0 and 6.6.1.
- Java, OpenSSL and BoringSSL are not asked about: OSV keeps them nowhere by name.
- With Live Otto off only the advisories of the dated snapshot have recorded answers; any other advisory
  needs Live Otto (a key, and up to the spending limit per run). No live run was made during the build.

## Decisions for Kevin (collected so far)

1. Run the Codespace check (`docs/CODESPACE-CHECK.md`, about 30 minutes): it is the part of fix 8 that
   could not be proven on the build machine.
2. Two panel sentences differ from the plan's wording: "Nothing is suggested on this page." and "Bring in a
   scanner file to start. Nothing is suggested yet." (the plan had "Otto has nothing to suggest ...", which
   the 5c fixes rule out). Keep them, or word them another way?
3. Wording: seven sentences that were not on your list also named Otto as acting, and were reworded after
   the review (the list, before and after, is in `docs/LIMITS.md`, "Limits of the 5c fixes"). Say so if any
   should go back. Three titles kept their words ("Otto's notes on reading it", "Otto's proposed check, in
   this assessment", "Have Otto write a change for ..."). Dates without a time of day stay as written. The
   ledger's own statement about a proposal's decisions was left unchanged.
4. The typed name (open question 4) is built: asked once in the panel, changeable in Settings. Approvals of
   a pull request or of a server change still use "You" and the two demo reviewers. Should they use the
   typed name too?
5. A next step in the panel sends Open pull request and Ask for approval with the reviewers the page ticks
   by default. Is that right, or should the panel only open the page for these two?
6. Research loop: pin more public copies (for example elliptic 6.6.0 and 6.6.1) so that newer advisories
   can be proven? Each is a new pinned download.
7. Research loop: the pack made by "Design and prove tests" is installed by that same click (your brief:
   "Nobody installs a test pack to get new checks"). CLAUDE.md said "A person installs it"; it now has one
   more rule that says this is the one case, and that the box says so before the run starts. Please read
   the two new CLAUDE.md lines (one under Product rules, one under Safety) and the changed Live Otto line.
8. Research loop: the app now makes one kind of request to a public service (osv.dev, package names only,
   on a click). This is new for the app; your brief asked for it. Please make the first real look yourself.
9. An item's own page ("Open in new tab") now carries the standing line also for an item of Checks, whose
   list page has none. Should the Checks list carry it too? (SPEC section 11 says every result screen.)
10. The fast test set: three shared walks moved to the slow set, as decided. If it is over five minutes
    again with tonight's tests, more has to move, or tests run in parallel (a new developer-only package).

## The exact next action

1. Read the full backend set's result (`<scratchpad>/full-snap1.txt`; it ran on the work as of 05:17).
   Fix what fails on the branch, with the real research run first (`tests/otto/test_discover_real.py`).
2. Build the frontend and run `e2e/tests/assistant.spec.ts` until it passes (the command is under step 2);
   commit the walk and its pictures (`docs/screenshots/phase6a/`; restore other picture folders the run
   rewrote with `git checkout -- docs/screenshots/<folder>`).
3. Commit step 3's documents. Write the walk for step 3 and run it; pictures to
   `docs/screenshots/phase6-research/`. Start the separate reviewer for step 3; fix its findings; commit; push.
4. The long checks on the branch as it is then, one at a time on a quiet machine: the fast set (timed), the
   accuracy check in demo and in isolated mode, `--only otto --mode isolated` against the 5c build.
5. Then 6b, 6c, 6d and 6e, each at least its shorter first half; the 15-minute live check list
   (`docs/LIVE-CHECK.md`, not written yet) with the first real look at osv.dev as its first item.
6. Keep pull request #7 a draft. Never merge. Leave the line in `docs/ACTIVE.md` unticked until the run ends.

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

