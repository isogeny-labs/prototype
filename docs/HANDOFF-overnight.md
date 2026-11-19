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

Written at 06:35 UTC on 19 November 2026 (machine time), in the middle of the run. The exact next action is
the section before the appendix.

| # | Success step | State |
|---|---|---|
| 1 | A brand-new Codespace starts the app with `./run-demo.sh` alone | **Built** (fix 8). Proven on the build machine as far as it can be; **Kevin's own 30-minute check is still needed**: `docs/CODESPACE-CHECK.md` |
| 2 | Checks: Encryption tests in four labelled parts | **Built** (fixes 1 and 2), reviewed, review findings fixed |
| 3 | "Open in new tab" on every side panel | **Built** (fix 3), reviewed, review findings fixed |
| 4 | No sentence says what Otto did | **Built** (fixes 4 and 5), with a wording test; seven more sentences reworded after the review |
| 5 | Times in the viewer's own time zone; files keep UTC | **Built** (fix 6) |
| 6 | "New" tag on advisories of the newest pack | **Built** (fix 7) |
| 7 | "Look for new advisories" reads a public source and finds what fits | **Built and committed** (step 3). The read from osv.dev itself could not be tried from the build machine: `docs/LIVE-CHECK.md`, Part 1, is Kevin's first real look |
| 8 | Otto designs a test and proves it on public copies after a click; only then a proposal | **Built and committed.** The real run in containers passes (9 min 40 s). Its walk reached the proposal and its Accept on the first try and is **running again now**; pictures and the separate review (started) are still open |
| 9, 10, 11 | The assistant: suggestions that fit the page, three tabs, decide in the panel | **Done** (phase 6a): built, reviewed, findings fixed, walk green (2 of 2), 38 pictures, committed and pushed |
| 12 | Commands | **First half built, tested, committed and pushed** (6b, fixed rules only). Its documents are written (not committed yet), its two commands are in the walk (**running now**), and its separate review has started. The second half (free wording through Claude) is not built |
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
`77c001a` **phase 6a, the review's findings fixed** · `255ec6f` the research loop's documents and this file ·
`23d577e` the research loop: evidence fix · `f20042a` **phase 6a: the walk green, with its pictures** ·
`ec1d061` the research loop: a run is ended with the app · `7a0898f` **phase 6b, first half**.

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

**The backend full set** (`pytest -q tests --full`), run once on a frozen copy of the work as of 05:17 while
other test runs were going on at the same time: **1933 passed, 15 failed, 7 errors, in 36 min 45 s.** What they
were:
- Two tests that keep lists up to date (the add-only tables; the routes that take a JSON body) had not heard of
  tonight's additions. Fixed (`ec1d061`, and again for 6b in `7a0898f`).
- The real research run (`tests/otto/test_discover_real.py`) and, after it, 17 tests of `tests/otto/`
  (`test_shipped.py`, `test_proposal_rules.py`, one of `test_otto_fix.py`) and one Docker test
  (`tests/test_isolated_flow.py`). **Run by themselves on the same frozen copy, the real research run and
  `test_shipped.py` pass: 11 passed in 9 min 40 s.** The saved output of the full run holds only its last 80
  lines, so the reason those tests failed in it is not on record. The likely cause is the other test runs on the
  machine at that time (one harness copy and Docker were shared). **This must be settled by one more full run on
  a quiet machine, with its whole output kept.**
- Found on the way and fixed (`ec1d061`): a research run that was still going when the app stopped was left
  behind and went on working. Stopping the app now ends it.

**Still open for step 1:**
1. The backend full set once more, on a quiet machine, with the whole output kept
   (`cd backend && .venv/bin/python -m pytest -q tests --full > FILE 2>&1`): about 45 minutes with the real
   research run in it. Nothing else may run tests or Docker meanwhile.
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

## Step 2: phase 6a, the Otto assistant (built, reviewed, findings fixed, walk green, committed and pushed)

Commits: `cc96b18` (the phase), `77c001a` (the review's findings), `f20042a` (the walk and its pictures).

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
2. *The end-to-end proof was missing, and Planning was not in it.* Fixed: the walk is reworked and green
   (see below).
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

**The walk** `e2e/tests/assistant.spec.ts`, reworked after the review, is green (`f20042a`): **2 passed in 3.5
minutes.** A name is typed at the first Confirm ("A tester") and every decision is recorded under it; Measure
status is pressed from the panel right after Run all, the Planning tab opens with a plan change, it is accepted in
the panel, and Systems and the Roadmap say the same; Retest now lands on the result the fix came from; after the
retest the plan change reads done; the evidence verifies with nine decisions in it. The panel's one read took
under 400 ms late in the walk. **38 pictures**, dark and light, in `docs/screenshots/phase6a/` (`01` to `19`).
The same walk now also types phase 6b's two commands (see step 4 below); that version is running now.

**Still open for 6a:** the fast set timed with the panel's tests in it; the accuracy check in both modes.

## Step 3: Otto's research loop (built, documented, walk green with pictures, reviewed; the review's findings are being fixed)

Commits: `07ad491` (the loop), `255ec6f` (its documents: SPEC sections 2, 3, 7f point 14 and 9; CLAUDE.md;
LIMITS "Limits of Otto's research loop"; README; LAYOUT), `23d577e` (a run's pack, and a look by itself, are
in the signed evidence: found while preparing the walk), `ec1d061` (a run is ended with the app).
`874f9ad` (the walk `e2e/tests/research.spec.ts`, its 19 pictures in `docs/screenshots/phase6-research/`, and
`docs/LIVE-CHECK.md`, Kevin's 15-minute check with the real internet and a real key).

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
15 passed; `NewAdvisories.test.tsx` and `Advisories.test.tsx` 93 passed; lint and type check clean. **The real
run in containers, `tests/otto/test_discover_real.py`, passes: with only the first built-in pack present and the
three elliptic advisories of the dated snapshot as a recorded source, a look finds three new advisories; the
research run installs pack 2026.11.1, proves the test for CVE-2024-42460 on elliptic 6.5.6 and 6.5.7, signs
pack 2026.11.2 on this computer and installs it; the check is then proposed (nothing added, nothing of the
assessment run), and the other two read "No test yet" with the pack's reason.** 9 min 40 s.

The walk `e2e/tests/research.spec.ts` (ports 8032/8465 in isolated mode, 8033/8466 in demo mode): **2 passed
(10.4 minutes)**. In isolated mode: a look (from a folder of recorded advisories), Design and prove tests, pack
2026.11.2 made on this computer and installed by that click, CVE-2024-42460 "Proven on public copies" and proposed,
CVE-2024-42459 and CVE-2024-42461 "No test yet" with the reason, the proven check accepted, run and Failed on
elliptic 6.5.6, the evidence verified. In demo mode: looking works and Design and prove tests is off with its
reason. Its pictures were taken before the panel had its text box; they are taken again with the next run.

**What the separate reviewer found (report of 07:00 UTC; it ran the tests of the step and probes of its own).**
State of each finding is kept current here.
1. **High. A run that gets no answer still installs a pack, and that advisory can never be tried again.** With
   Live Otto off and a truly new advisory (no recorded answer), the run ended with a pack in which the advisory
   reads "No test yet: There is no answer for this advisory yet."; the research command then leaves it out for
   good, also with Live Otto on later. The promised sentence "No recorded answer: this needs Live Otto." showed
   only in the folded output. The same path, by reading: a failed live call, a refusal or the spending limit; a
   trial that did not finish is signed as "Not offered". *State: **fixed.** An advisory a run cannot settle (no
   answer, or a trial that did not finish) is left out of the pack, nothing is signed about it, it reads "Still
   open" with the reason and can be tried again; a run that settles nothing makes no pack. Proven with the real
   research command (`test_with_the_real_command_an_advisory_with_no_answer_stays_open_and_a_later_run_takes_it_up`,
   3 seconds): left open twice, then settled once an answer exists.*
2. **Medium. After a research run made a pack, no later built-in pack can be installed** (the packs are one chain,
   and the pack made here is its newest link). Nothing said so. *State: **said plainly** in the box before the
   run starts, in LIMITS and in the README. Changing it (a built-in pack follows the last built-in one; packs made
   here get names of their own) is decision 14 for Kevin.*
3. **Medium. Two clicks at once start two runs** (two browser tabs; the lock was created and never used).
   *State: **fixed** (the lock is held from the check to the registration; a run's key carries its number; a test
   starts four clicks at one moment and gets one run).*
4. **Medium. A pack made here that waits uninstalled is mishandled**: the run installs the older one and records
   it as its own, or the run's own pack stays waiting with no word. *State: **fixed.** The click installs only the
   pack its own run made (and only if it holds nothing but that run's advisories). A pack made here that waits
   turns the button off with "Test pack ..., made on this computer, is waiting to be installed. Install it first:
   Settings, Test packs, Check for updates.", and its advisories say where they are.*
5. **Medium. Without Otto installed, one look turns that assessment's evidence from "verified" to "not
   confirmed"** (the verify command wants the harness for an audit of an empty ledger). *State: **fixed** (an Otto
   ledger with no entries has nothing to audit; the file verifies with exit code 0, tested with the verifier run
   without Otto). The readable report now lists looks and runs too.*
6. **Medium-low. The limits of a look can hide the advisory that fits**: the 40 kept are the newest across all
   libraries, cut before fit is worked out; a first page of 200 records is not the newest; two sentences about
   the cut are untrue. *State: **fixed.** Every record of up to three pages is read; what names a version you have
   is ranked first and the cut to 40 comes after; the notes say which cut happened. (Go's standard library, which
   the Acme Pay dependency list names, has many advisories: without this the first real look could have hidden
   the ones that fit.)*
7. **Medium-low. A damaged file in the folder of recorded advisories breaks the page and the evidence**, and
   that reader has no fuzz test. *State: **fixed** (each advisory of such a file is held to the snapshot's exact
   shape and used byte for byte, or left out; a seeded fuzz test).*
8. **Low. Eight sentences that can be untrue** (an unreadable version; "Nothing was installed." after a built-in
   pack was; "with its proposal" where nothing is proposed; Java named among what a look covers; the box with
   Live Otto on; the signer label of a pack made with Live Otto off; the command's last line; one SPEC example).
   *State: **all eight reworded**, with a test of the block's sentences.*
9. **Low. The real-run test and the walk expect pack 2026.11.2 and fail from 1 December 2026** (a pack made here
   is named by today's month). *State: **fixed** (both read the version from the run).*
10. **Low. Hardening**: a redirect of the request is followed; any number of ranges is kept; a text of blanks is
    kept; a publisher's title could carry a rating; the 4-hour limit never ends a run that hangs. *State: **fixed**
    (a redirect is not followed, tested against a local server; at most 200 ranges of a record; no blank piece;
    a summary that rates is not shown as a title; a timer ends a run after four hours, with what it started).*

Checked by the reviewer and found met: only the package name and ecosystem are sent; the answer is treated as
data (wrong shape, oversize, deep nesting and HTTP errors get one sentence and nothing is kept; no severity is
read); a check is proposed only from an installed pack whose test has a supported, replayed trial; looking
proposes nothing and neither click adds to a plan or runs a test of the assessment; closed, demo mode and
without Otto are refused with the reason; looks, runs and the run's pack are in the signed file and five kinds
of change to them fail verify; both tables are add-only; no test reaches the network or Claude; answer keys,
wireframes, `research/`, the checkers and the pinned scripts are untouched; nothing on screen goes beyond SPEC
section 2. Could not be checked by anyone here: a real answer from OSV, and a live Claude run.

Tests after the fixes: `tests/otto` fast set **361 passed** (83 seconds; `test_lookup.py` 23 with 8 new,
`test_discover.py` 24 with 9 new); lint, type check and generated files clean.

**Still to do for step 3:**
1. Run the real run in containers (`tests/otto/test_discover_real.py`) and the walk (`e2e/tests/research.spec.ts`)
   again on the fixed code, and take the walk's pictures again (the panel has its text box now).
2. Check that the four answer keys still match (the accuracy check, both modes).

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

## Step 4: phase 6b, commands (first half built, tested, committed and pushed; documents, walk and review open)

Commit: `7a0898f`. The plan's "shorter first half": fixed rules only, without the Claude step for free wording.

What is built:
- **The one list of commands** as data, and the fixed rules that read a sentence
  (`backend/app/assistant/commands.py`); what is answered (`answers.py`): where to go, or a card of phase 6a
  with its Confirm step, "Which one?", or "I can't do that." with what can be said on the page. Both only read.
- **Two routes**: `GET /api/assessments/{id}/assistant/answer` (a read; a closed assessment uses it) and
  `POST /api/plans/{plan_id}/assistant/messages` (the same answer, and the exchange kept in
  `assistant_messages`, add-only, written by `backend/app/lab/said.py`).
- **The text box** at the foot of the panel with up to three chips, the answer area, the card with its Confirm
  step, "Which one?" options and examples (`OttoPanel.tsx`).
- **Filters in the address**: Result (Checks, Evidence), Came from (Checks), Decision (Advisories). On Checks the
  Result filter also narrows the test plan's cards.
- Documents (in the working tree, **not committed yet**): SPEC section 2 "Commands in the Otto panel", sections
  3 and 9; CLAUDE.md (the rule-based rule, what is kept, the Tests rule); LIMITS "Limits of phase 6b, first
  half"; README "Telling Otto what to do"; LAYOUT.

Test results: `backend/tests/assistant/`: **119 passed** (74 for commands: every line of the list from several
wordings, the answers at each stage of the shared walk, a seeded fuzz of the reader, asking changes nothing,
what is kept, the routes). Frontend: **808 screen tests passed** (12 for the text box, 5 for the address
filters). Lint, type check and generated files clean.

**Still to do for 6b's first half:**
1. The walk: `e2e/tests/assistant.spec.ts` now types "show me failed checks" (after Run all) and "accept the
   Java fix" (on Dependencies), in the working tree. **Running now** (`<scratchpad>/e2e-6a-8.txt`). Two new
   pictures: `08b-...` and `17b-...`.
2. The separate reviewer's report (started): fix what it finds.
3. Commit the documents and the walk; push.
- **Not built (the second half):** passing a sentence the rules can't read to Claude with Live Otto on, its
  check, its recorded answers and its ledger record. The CLAUDE.md rule changes 3, 4 and 8 of the plan (Claude's
  jobs, what a run is, when a live call is made) are therefore **not** applied yet.

**What the separate reviewer of 6b found (report of 07:20 UTC, on commit `7a0898f`; it asked the committed code
about 4,500 made-up sentences at nine stages of a demo assessment).** State of each finding is kept current here.
1. **High. A "Which one?" option did not lead to the thing it names** (a title with a colon looped or showed
   another suggestion's card; a reject could carry the rest of the title as its reason). *State: (a), (b) and (d)
   fixed in `c7472a4` (titles are said without their colons, an exact title wins, and the walk now says every
   option of every "Which one?"). Still open: (c) a title that holds a kind word ("Fix acme-sign 1.4.2 before
   ..." is a plan change, and "fix" narrows the search to fixes), and (e) the list holds things the button is not
   offered for and is cut at 8 without saying so.*
2. **High. "Close the Fixing tab" does not close the tab in an open assessment**: the kept sentence is filed
   under that thread and changes the tab's mark, so the tab is back at once with a dot. For the same reason any
   typed sentence brings a closed tab back. *State: open.*
3. **Medium. "approve it" counts every reviewer as missing** (it reads fields the rows do not have). *State: open.*
4. **Medium. In a closed assessment a page-only command says a button is ready**, and "What can you do?" still
   lists decisions and starts. *State: open.*
5. **Medium. The card that comes back for a sentence goes stale** (it is not replaced by later reads; the server
   refuses a stale Confirm, so nothing wrong is recorded). *State: open.*
6. **Medium. Checks filtered by a command can be misread**: with a Result value no row has, the control shows
   "All results" and the Test plan part is gone with no word; "Run all" still runs all tests while only some
   are listed; on Evidence the Result filter narrows only the Encryption tests table. *State: open.*
7. **Medium to low. A sentence with no thread is kept and shown nowhere** (typed beside the Overview, or "open
   settings"). *State: open.*
8. **Low to medium. "Opened Checks." with no file in, while the app shows Import.** *State: open.*
9. **Low. Sentences read into something else** (all only move): "show open checks", "tick Dana as reviewer",
   "apply the filter", "Otto: run all", "open the plan". *State: open.*
10. **Low. Wording**: "filtered to Accepted" where the control says "Added"; "no check reads Retest now";
    "There is One suggestion"; "Open where it led" drops the filter. *State: open.*
11. **Low. Documents**: SPEC section 3 still says nothing is stored for the panel; LIMITS on short names; what is
    kept with each sentence (name, time, open item); `assistant_say` has no closed check of its own; no
    `docs/screenshots/phase6b/` folder (the two pictures are in `phase6a/`). *State: open.*
12. **Tests the plan names that are thin**: Approve with some approvals given, a page-only answer in a closed
    assessment, the reply card after its entry changed, a tab command where the read after it differs; 8 of the
    32 lines are never asked against an assessment; 19 lines have one wording. *State: open.*

Checked by the reviewer and found met: nothing happens before Confirm but moving around (all eight kinds of
answer traced through the panel); a card for a command is the panel's own card; a button that is off gives the
page's reason and no Confirm step; typed text is data (fixed patterns, 500 characters, stored and drawn as text);
the table is add-only; the package only reads and no model is asked; address filters; counts in answers follow
the pages' own rule; no "secure", score, severity or sentence about what Otto did; the documents say plainly
that the Claude step is not built.

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
11. Phase 6b: on Checks the Result filter now also narrows the test plan's own cards (so that "show me failed
    checks" lists only failed checks). Before, it filtered only the rows under the plan. Is that right?
12. Phase 6b: everyday names for libraries are a small fixed table (Java for openjdk, Python and ecdsa for
    python-ecdsa). More names can be added; tell me which you use.
13. `docs/LIVE-CHECK.md` is your 15-minute check with the real internet and a real key. Part 1 (the first real
    look at osv.dev) is free and needs no key.
14. Research loop: test packs install in one order. Once a research run has made a pack on a computer, a built-in
    pack that is published later can't be installed in that data folder, and a pack made here takes the next
    number of its month (2026.11.3), which a later built-in pack could also carry. The box, LIMITS and the README
    say so. Should a built-in pack be allowed to follow the last built-in one, and should packs made here get
    names of their own (for example "2026.11.2-here.1")? That changes how packs chain, and what the verify
    command checks, so I did not do it without you.
15. Research loop: a pack made here that was never installed (made by hand, or by a run cut off after signing) is
    not installed by a later click; the button is off until a person installs it in Settings. The other way
    (the click installs it too, and the box says so) is possible. Which do you want?
16. Phase 6c: the panel's status line stays "Live Otto is off." / "Live Otto is on.". The plan's longer line
    ("Otto answers the fixed questions from this assessment's records. Free-form answers need Live Otto.") says
    what Otto does, which your wording rule of 19 November rules out, and promises free-form answers that are not
    built. How should it read once they are?
17. Phase 6c: one sentence about each page ("What is this page for?") is new wording of mine, ten sentences in
    `backend/app/assistant/words.py` (`PAGE_FOR`). Please read them.

## The exact next action

1. Read the two walks' results (`<scratchpad>/e2e-research-2.txt`, then `<scratchpad>/e2e-6a-8.txt`). Correct
   what fails (so far each failure was an expectation of the walk itself) and run that walk again:
   `cd frontend && npm run build`, then `cd e2e && npx playwright test tests/research.spec.ts --trace off`
   (about 15 minutes, Docker) or `tests/assistant.spec.ts` (about 4 minutes).
2. Commit: the research walk with its pictures (`docs/screenshots/phase6-research/`), `docs/LIVE-CHECK.md` and
   CLAUDE.md's walk line; then the 6b documents and the assistant walk with its two new pictures. Restore other
   picture folders a run rewrote with `git checkout -- docs/screenshots/<folder>`. Push.
3. Read the two reviewers' reports (step 3, and 6b's first half) when they arrive; fix what breaks a
   requirement; commit; push.
4. The long checks on the branch as it is then, **one at a time and with nothing else running**: the full
   backend set with its whole output kept; the fast set (timed); the accuracy check in demo and in isolated
   mode; `--only otto --mode isolated` against the 5c build; one complete run of every walk (`cd e2e && npm test`).
5. Then 6c, 6d and 6e, each at least its shorter first half (6c: the six fixed questions; 6d: Changes without
   the Watch list; 6e: the what-if facts and the try), and 6b's second half.
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

