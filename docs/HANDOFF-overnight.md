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

Written at 11:05 UTC on 19 November 2026 (machine time). The exact next action is the section before the
appendix. In one line: **steps 1 to 3 and the first halves of 6b and 6c are built, reviewed, fixed and pushed, and
every walk passed on them (100 of 100); 6d is started (two backend checkpoints, nothing of it on a page yet); 6e is
not started; the long checks are running once more on the newest code.**

| # | Success step | State |
|---|---|---|
| 1 | A brand-new Codespace starts the app with `./run-demo.sh` alone | **Built** (fix 8). Proven on the build machine as far as it can be; **Kevin's own 30-minute check is still needed**: `docs/CODESPACE-CHECK.md` |
| 2 | Checks: Encryption tests in four labelled parts | **Done** (fixes 1 and 2): built, reviewed, review findings fixed |
| 3 | "Open in new tab" on every side panel | **Done** (fix 3): built, reviewed, review findings fixed |
| 4 | No sentence says what Otto did | **Done** (fixes 4 and 5), with a wording test; seven more sentences reworded after the review |
| 5 | Times in the viewer's own time zone; files keep UTC | **Done** (fix 6). Since phase 6c a kept answer of the panel follows the same rule (stored in UTC words, shown in the viewer's time) |
| 6 | "New" tag on advisories of the newest pack | **Done** (fix 7) |
| 7 | "Look for new advisories" reads a public source and finds what fits | **Done as far as this machine can show**: built, reviewed, review findings fixed, pushed (step 3). The read from osv.dev itself could not be tried from the build machine (it is not reachable from here): `docs/LIVE-CHECK.md`, Part 1, is Kevin's first real look |
| 8 | Otto designs a test and proves it on public copies after a click; only then a proposal | **Done**: built, reviewed, review findings fixed, pushed. On the fixed code the real run in containers passed (9 min 36 s) and the walk passed (2 passed, 10.7 min) |
| 9, 10, 11 | The assistant: suggestions that fit the page, three tabs, decide in the panel | **Done** (phase 6a): built, reviewed, findings fixed, walk green, pictures, pushed |
| 12 | Commands | **First half done** (6b, fixed rules only): built, tested, documented, reviewed, the review's findings fixed with tests, walked on the final code. Two small leftovers are listed in step 4 below. **The second half (free wording through Claude) is not built** |
| 13 | Questions | **First half done** (6c, the six fixed questions by rules): built, tested, documented, reviewed ("not ready as committed": 13 findings), all 13 fixed with tests, walked on the final code. **The second half (answers in free words by Claude, with "Hypothesis") is not built**, so an unproven answer labelled Hypothesis does not exist yet |
| 14 | What-if and hypotheses | **Not started** (6e) |
| 15 | Change watch | **Started, not usable yet** (6d, the shorter first half: Changes without the Watch list). Two backend checkpoints are in, with tests, and **nothing of it is on a page**: no route, no button. See "Step 6" below for what is built and what is left |
| 16 | Nothing without a click and Confirm; works without a key | **Holds for everything built**: 6a, the research loop, 6b and 6c work with no key (no part of the panel asks Claude in this version), with tests |
| 17 | Keys match in both modes, fast tests under 5 minutes, each step reviewed, committed, pushed | **Keys: match in both modes** (isolated: exit code 0 on a frozen copy; demo: green in the GitHub checks on every push). **Fast tests: 5 min 52 s on the build machine with Otto, 4 min 35 s without; 4 min 59 s on GitHub's runner. Not safely under five minutes: decision 10.** Each step reviewed, fixed, committed, pushed. The complete run of every walk found two failures; both are fixed, the fix was reviewed (five findings, fixed), and **every walk then passed (100 of 100)**. The full backend set has not run on the newest code yet: **it is running now**, after the fast set and one more complete run of the walks |
| 18 | This file | Kept current |

Commits on `overnight/fixes-and-phase6` since the 5c merge (`5a6b4e4`), oldest first, all pushed:
`f6ba0f2` fix 6 · `b274428` fix 8 · `d1e6892` fixes 4 and 5 · `6eacbf2` fixes 1, 2 and 3 · `f109d54` fix 7 ·
`8526aac` docs and the new walk · `4d43bab`, `dbbe95a` two things the walks found · `dd21a67` one file put
back (**step 1 as first built**) · `e50d1a7` this file and 24 pictures · `cc96b18` **phase 6a** ·
`a19bb0f`, `ea1329a` **step 1, the review's findings fixed** · `07ad491` **the research loop, first part** ·
`77c001a` **phase 6a, the review's findings fixed** · `255ec6f` the research loop's documents and this file ·
`23d577e` the research loop: evidence fix · `f20042a` **phase 6a: the walk green, with its pictures** ·
`ec1d061` the research loop: a run is ended with the app · `7a0898f` **phase 6b, first half** · `664c083` this
file · `874f9ad` **the research loop's walk, its pictures, and the live check list** · `c7472a4` **phase 6c,
first half, with 6b's documents and walk** · `c819aa9` **the research loop: the review's findings fixed** ·
`12ea5d8` this file · `7017bda` **6b: the review's findings fixed** · `0697a62`, `3bac01c` the walks get the
Otto panel only where they ask for it · `27bd7f3` two failures the GitHub checks found · `5699057` the research
walk green on the fixed code, with its pictures · `bc8f5e2` **6b and 6c: the reviews' findings fixed, with
tests** · `187258d` a test on the real multi-target file · `b3b6376` this file · `4fe52ec`, `a378bac` the panel
walk green on the final code, with its pictures · `634e360` the panel's shared test walk no longer leaves its
patches in place · `2849a9c` the panel's walk-reading tests go to the slow set · `ec10c0a` this file ·
`e16786f` **what the complete run of every walk found: reads take turns, the panel asks once on a change of
page, and a fact's link opens where its sentence stands** · `44faeba` this file · `043c5ac` **the review of
that commit: five findings fixed** · `3322971` **6d, checkpoint 1** (a developer's change is read, its tests are
picked; backend only) · `2aa07a2` **6d, checkpoint 2** (the watch run and the reviewer's rule for it; backend
only).

## The GitHub checks, and what they caught (07:45 UTC)

The repository's own checks on GitHub ("Checks": lint, type check, generated files, the fast backend set
**without the Otto harness**, demo-mode accuracy, frontend tests and build) run on every push to this branch.
Looked at for the first time at 07:42 UTC, they showed the Backend job failing on the last feature commits
(`c7472a4`, `c819aa9`) with **2 failed, 1631 passed, 146 skipped** (4 min 52 s); the Frontend job passed.
Both failures were real and came from tonight's work; my local runs had been of single test folders, so the
whole fast set had not run locally since phase 6a:
- `tests/test_prepare.py::test_only_prepare_can_build_or_pull` scans the app's source for the words of a
  container command. Phase 6b's command table held the page word "import" as a quoted key. Fixed in `27bd7f3`
  by working the pages' own last words out of their addresses (the scan itself is unchanged).
- `tests/otto/test_discover.py::test_design_and_prove_is_off_with_the_reason_until_it_can_work` assumed Otto is
  installed. Fixed in `27bd7f3`: it expects the sentence that holds on the computer it runs on.
Because the Backend job stopped at its tests, its later step (demo-mode accuracy) did not run on those commits.
**Whoever picks this up: read the newest run of "Checks" on pull request #7 first.** The long checks below
include the whole fast set, run locally with Otto installed.

Another thing the same look turned up: since phase 6a the Otto panel repeats page buttons under their own names
(a next step is the page's button; since 6b an example chip says the same words). The older walks click such
buttons by name, so with the panel beside the page a click would find two. Only the panel's own walk had been
run after phase 6a. `0697a62` and `3bac01c`: a walk now gets the panel only when it asks for it (the panel's
walk, the research loop's walk, the walk that measures the pages' widths); the others start with it hidden, by
the setting the top bar's toggle keeps in the browser. The first complete run of every walk after that is in
"The long checks" below (97 passed, 2 failed, both fixed).

## The long checks (results as they come in)

| Check | On | Result |
|---|---|---|
| Accuracy, **isolated mode**, all four answer keys (`python -m app.accuracy --mode isolated`) | a frozen copy of `5699057` | **Exit code 0** (23 min 40 s): first key 18 of 18, migration 47 of 47, real libraries 33 of 33 with trial counts 6 of 6 unchanged, dependencies 220 of 220. Otto is not graded (the fifth key is not written, as agreed). After that commit only the assistant's package, its tests and documents changed (`bc8f5e2`, `187258d`), none of which the accuracy check goes through |
| Accuracy, **demo mode** | GitHub checks on `27bd7f3` and again on `187258d` (every review fix is in it) | **Passed** both times (about 2 minutes). It runs again on every push |
| The fast backend set **without Otto**, lint, type check, generated files; frontend type check, tests, build; CodeQL | GitHub checks on `27bd7f3` and again on `187258d` | **All green** both times. The backend job, with the fast set and the accuracy check, takes about 7 to 8 minutes; the fast set alone took 4 min 59 s on `27bd7f3` |
| The research loop's real run in containers | `c819aa9` and later | **1 passed** (9 min 36 s) |
| The research loop's walk | `0697a62` and later | **2 passed** (10.7 min) |
| Backend `tests/assistant` and `tests/times` (with Otto) | `bc8f5e2` | **195 passed** (80 s) |
| Screen tests | `bc8f5e2` | **820 passed** |
| The panel's walk on the final code | `bc8f5e2` and later | **2 passed** (5.9 min), with the new steps from the 6b and 6c review fixes; pictures retaken |
| The multi-target tests with the new panel test (the real multi-target file: every "Which one?" option names one server's test and settles) | `634e360` | **20 passed** (76 s). First run: the new test expected three servers with "Old TLS versions"; the file has two |
| The whole fast backend set **with Otto** | `a378bac`, then `634e360` | First run: **11 failed, 7 errors**, 1801 passed, in 6 min 52 s (see "What the first whole fast set with Otto found" below). After the fix: **1819 passed, none failed**, in **6 min 49 s**: over five minutes. The panel's walk-reading tests (54) then went to the slow set, by the project's rule; timed again, see the next row |
| The whole fast backend set with Otto, after that move, timed | `2849a9c` | **1765 passed, none failed, in 5 min 52 s.** Still over five minutes on the build machine (the same machine took 5 min 4 s for the 5c merge, before tonight). **Not met here; met on GitHub's runner at the limit (4 min 59 s without Otto).** Decision 10 |
| Every walk once (`cd e2e && npm test`), first complete run | `ec10c0a` | **97 passed, 2 failed, 1 did not run** (51.1 min). The two failures are real and are fixed in `e16786f`: see "What the complete run of every walk found" below. The one that did not run is the second part of the panel's walk, which is skipped when its first part fails |
| After `e16786f`: the whole fast set with Otto, and without | `e16786f` | **1772 passed** in 5 min 52 s with Otto; **1674 passed, 98 skipped** in 4 min 35 s without (as the GitHub checks run it). 821 screen tests, lint, both type checks and the generated files are clean. The layout walk alone: **passed** (1.2 min) |
| The GitHub checks on the fix | `e16786f` | **All green** (10:15 UTC): Backend in 7 min 3 s (lint, type check, generated files, the fast set without Otto, demo-mode accuracy against the keys), Frontend, CodeQL |
| Every walk once, again | `e16786f` | **100 passed, none failed** (53.8 min; 11:02 UTC). Its request log shows no read slower than a few seconds in any walk |
| After the review of `e16786f` (five findings, fixed in `043c5ac`) and 6d's two backend checkpoints (`3322971`, `2aa07a2`): the fast set with Otto and without, every walk once more, the full backend set | `2aa07a2` | **running** (started 11:05 UTC, about two hours in all; outputs in the scratch folder as `e-1-fast.txt`, `e-2-fast-no-otto.txt`, `e-3-e2e.txt`, `e-4-full.txt`). If this session ended first: run them again, one at a time (the commands are in "The exact next action") |

### What the first whole fast set with Otto found (08:32 UTC)

Since phase 6a nobody had run the whole fast set on a computer **with** the Otto harness: I ran single test
folders, and the GitHub checks run without Otto. Run whole, it failed 11 tests with 7 errors, all in
`tests/otto/` (`test_shipped.py`, `test_proposal_rules.py` and the new real-command test of
`test_discover.py`), each with "The pack is signed by a key this installation does not trust."

The cause is in a test fixture of phase 6a, not in the app: `assistant_walk` (the shared walk the panel's tests
read) is made once for the whole run, and it left its own list of trusted pack keys in place until the run
ended. Every later test that needs the real shipped key was then refused its packs. `tests/assistant` runs before
`tests/otto`, so the folders passed one by one and failed together. **This is also what failed in the full
backend run on the frozen copy of step 1** (15 failed, 7 errors), which I had put down to other runs going on at
the same time; that explanation was wrong.

Fixed in `backend/tests/conftest.py`: the walk's patches are taken off as soon as the walk is made and put back
only for the one test that reads it. The lesson is in CLAUDE.md's test section (the whole fast set, with and
without Otto, before a step is called done).

**The time.** After the fix the whole fast set passes with Otto (1819 tests) and takes **6 min 49 s** on the
build machine, over the five minutes it must stay under. For comparison, on the same machine the 5c merge took
5 min 4 s before any of tonight's work, and on GitHub's runner tonight's fast set (without Otto) takes 4 min 59 s.
The slowest parts: the shared demo walk every result-reading test uses (47 s, as before tonight), the Otto
panel's shared walk (41 s, new) and one panel test of 15 s. By the project's rule ("a test that reads a long demo
walk built for its files is slow") the panel's 54 walk-reading tests are now in the slow set
(`SLOW_SHARED_WALKS` in `backend/tests/conftest.py`); about 140 panel tests that need no walk stay in the
everyday run. Run the others with `pytest -q tests/assistant --full` (about 80 seconds) whenever the panel is
touched. **After the move the fast set takes 5 min 52 s here** (1765 tests): still over. What is left is
spread over many small tests; the one big piece is the shared demo walk (46 s) that most result-reading tests
use, which was in the fast set before tonight. Nothing more can move by the rule, so this is decision 10.

### What the complete run of every walk found (09:40 UTC), and what was done (`e16786f`)

The first complete run on the branch (100 walks, 51 minutes) ended with 97 passed and two real failures.

**1. With the Otto panel beside the pages, a quick walk through the pages outran the server.** The walk that
measures every table page (`layout.spec.ts`, with the panel shown) opened the Overview and read "Checks: Open 5"
where five checks had results: the Overview's own re-read had not come back within five seconds. Run alone with
the new request log (below) it failed the same way, and the log showed why: reads taking 3 to 9 seconds each,
queued behind one another. Three things added up:
- A page asks for several views at once (its own, the Related block of an open item, the panel's).
- The panel asked **twice** on every change of page: first about the new page with the item that had been open
  on the page before (for example "Checks, with advisory CVE-2022-21449 open"), then again without it.
- Python works several views out side by side far more slowly than one after another. Measured on this
  machine (four cores), in the state the walk had reached: the same twelve views took **3.2 seconds on one
  thread, 4.1 on two, 5.1 on three and 7.4 on six**. One Overview read alone takes about half a second, one
  panel read about a quarter.

Fixed in two places, both small:
- `backend/app/web/turns.py` (new): the reads under `/api` take turns, first come, first served, so the page's
  own reads are answered first and the panel's after them. A turn ends when the answer starts to go out. A
  request that changes something takes no turn and waits for none. Seven tests (`backend/tests/test_turns.py`).
- `frontend/src/App.tsx`: the open item is kept with the page it was reported on, so the panel asks once on a
  change of page. One screen test, which fails on the code before with exactly the stale read.

After both, in the same walk: the slowest read fell **from 8.8 seconds to 1.5**, and the Overview's own read
**from 4.9 seconds to 0.8**. What it costs is said in `docs/LIMITS.md` (6a's limits): while one read is slow,
every other read waits behind it; the app is made for one person on one computer. The reads themselves are no
faster. This is a change to how the server answers every page, made after the steps' own reviews, so a separate
reviewer read that commit; its findings are below.

**2. One fact of "Why did this check fail?" linked to a place that does not show it.** The answer's second fact
is the result's plain sentence, and its link opened the result's panel on Evidence. That sentence stands in the
Evidence table (the Result column); the open panel does not repeat it, and with a panel open the table is drawn
narrow, without it. The walk's check passed twice before by luck of timing. Fixed: that one fact now links to
the table ("See the Evidence table"); what happened, the control and the rest still link to the result. The
backend test holds each kind of fact to its place, and the walk follows both links and reads each sentence where
its link opens.

**The request log.** `E2E_APP_LOG=/some/file` in front of a walk keeps what its copy of the app printed and
every request its page made, with the answer and how long it took (`startCopy` in `e2e/tests/shared.ts`;
CLAUDE.md's test section names it). It works for walks that start their own copy of the app. Without it nothing
is kept, as before.

**What the separate reviewer of `e16786f` found (report of 10:32 UTC; read from the code and the kept request
log, nothing run).** No deadlock, and the turn comes back on every path (an exception, a dropped request, a
second start of an answer, another event loop). Five findings, each with its state:
1. **The new link "See the Evidence table" showed nothing when a result's panel was already open**, which is how
   "this check" is asked about: Evidence keeps its panel open for an address without an item, and beside a panel
   the table is drawn narrow, without the plain sentence. *State: **fixed.** A result's own panel on Evidence now
   starts with the result's plain sentence (the sentence its row shows while no panel is open), and the fact links
   to the result again ("See the evidence"), like every other fact of it. A screen test holds the panel's first
   line to the row's sentence; the walk follows the link with the result closed and with it open.*
2. **One read that waits for a long operation stopped every read.** Some reads wait for an app-wide lock that
   Connect demo code holds while Claude writes a change with Live Otto on (up to ten minutes), and Apply or Roll
   back for up to twenty seconds. With turns, every other page, and even the session read, waited behind such a
   read. *State: **fixed.** A turn ends after five seconds at most; from then until the stuck read has answered,
   nobody waits for a turn (the reads go side by side, as before there were turns). Two tests. The module's
   own description no longer says that nothing can stop the pages from reading.*
3. **Coming back to a page by a link that names an item, the panel first asked without the item**: what the
   page's panel had reported when it closed on the earlier visit stood in for the address. *State: **fixed** (a
   report counts for one visit of a page; the screen test's return leg fails on the code before).*
4. **One of the seven tests would have passed with the middleware not installed.** *State: **fixed** (it now
   checks that the app carries it); the generous time limits in those tests went from 1 to 10 seconds.*
5. **The documents said more than is true**: "the page's own reads first" (it is the order of arrival; on the
   Overview the panel's read is answered before the page's own), "the panel asks once on a change of page" (a page
   that opens an item by itself still gives two reads; what holds is "never with the item of the page before"),
   and the request log works only for walks that start their own copy of the app. *State: **corrected** in
   `docs/LIMITS.md`, `CLAUDE.md`, `docs/LAYOUT.md` and the module's own description.*

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

## Step 3: Otto's research loop (built, documented, walk green with pictures, reviewed, the review's findings fixed and pushed)

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

## Step 4: phase 6b, commands (first half built, tested, documented, walk green, reviewed; the review's findings fixed)

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
- Documents (committed with phase 6c, `c7472a4`): SPEC section 2 "Commands in the Otto panel", sections
  3 and 9; CLAUDE.md (the rule-based rule, what is kept, the Tests rule); LIMITS "Limits of phase 6b, first
  half"; README "Telling Otto what to do"; LAYOUT.

Test results: `backend/tests/assistant/`: **119 passed** (74 for commands: every line of the list from several
wordings, the answers at each stage of the shared walk, a seeded fuzz of the reader, asking changes nothing,
what is kept, the routes). Frontend: **808 screen tests passed** (12 for the text box, 5 for the address
filters). Lint, type check and generated files clean.

The walk: `e2e/tests/assistant.spec.ts` types "show me failed checks" (after Run all: the page is filtered, one
request was sent, Back returns) and "accept the Java fix" (on Dependencies: the card with its Confirm step,
Confirm accepts). **2 passed (5.7 minutes)**, with pictures `08b-...` and `17b-...` in
`docs/screenshots/phase6a/`. Documents and walk were committed with phase 6c (`c7472a4`).
- **Not built (the second half):** passing a sentence the rules can't read to Claude with Live Otto on, its
  check, its recorded answers and its ledger record. The CLAUDE.md rule changes 3, 4 and 8 of the plan (Claude's
  jobs, what a run is, when a live call is made) are therefore **not** applied yet.

**What the separate reviewer of 6b found (report of 07:20 UTC, on commit `7a0898f`; it asked the committed code
about 4,500 made-up sentences at nine stages of a demo assessment).** State of each finding is kept current here.
1. **High. A "Which one?" option did not lead to the thing it names** (a title with a colon looped or showed
   another suggestion's card; a reject could carry the rest of the title as its reason). *State: (a), (b) and (d)
   fixed in `c7472a4` (titles are said without their colons, an exact title wins, and the walk now says every
   option of every "Which one?"). (c) and (e) **fixed** after that: a whole title is looked for word for word
   before any word of it is read as a kind; a decision's list holds only what its button is offered for, and
   says so when more than eight fit.*
2. **High. "Close the Fixing tab" does not close the tab in an open assessment**: the kept sentence is filed
   under that thread and changes the tab's mark, so the tab is back at once with a dot. For the same reason any
   typed sentence brings a closed tab back. *State: **fixed** (what a person typed is not part of a tab's mark;
   a backend test and a screen test whose read after the sentence carries the new entry).*
3. **Medium. "approve it" counts every reviewer as missing** (it reads fields the rows do not have). *State:
   **fixed** (counted from `approved_at`; tested at none, one of two, and all approved).*
4. **Medium. In a closed assessment a page-only command says a button is ready**, and "What can you do?" still
   lists decisions and starts. *State: **fixed** (the page opens with the closed sentence; the list holds only what
   moves; the keeping call itself now refuses a closed assessment too).*
5. **Medium. The card that comes back for a sentence goes stale** (it is not replaced by later reads; the server
   refuses a stale Confirm, so nothing wrong is recorded). *State: **fixed** (once anything changes the assessment
   after the answer, its card is taken away and one line says so; a screen test).*
6. **Medium. Checks filtered by a command can be misread**: with a Result value no row has, the control shows
   "All results" and the Test plan part is gone with no word; "Run all" still runs all tests while only some
   are listed; on Evidence the Result filter narrows only the Encryption tests table. *State: **fixed** (the
   control shows the filter that is on; the plan keeps its part and says in one line how many tests are listed
   and that Run all runs all of them; the Evidence answer says which table is filtered).*
7. **Medium to low. A sentence with no thread is kept and shown nowhere** (typed beside the Overview, or "open
   settings"). *State: **said in SPEC and LIMITS; decision 18 for Kevin** (where should such a sentence be listed?).*
8. **Low to medium. "Opened Checks." with no file in, while the app shows Import.** *State: **fixed.***
9. **Low. Sentences read into something else** (all only move): "show open checks", "tick Dana as reviewer",
   "apply the filter", "Otto: run all", "open the plan". *State: **fixed** (24 sentences in a test), except "open
   the pull request", which still asks to open a new one (LIMITS).*
10. **Low. Wording**: "filtered to Accepted" where the control says "Added"; "no check reads Retest now";
    "There is One suggestion"; "Open where it led" drops the filter. *State: **fixed**, except "Open where it led",
    which still opens the page without the filter (LIMITS); a reason over 300 characters is now refused when it is
    said, not at Confirm.*
11. **Low. Documents**: SPEC section 3 still says nothing is stored for the panel; LIMITS on short names; what is
    kept with each sentence (name, time, open item); `assistant_say` has no closed check of its own; no
    `docs/screenshots/phase6b/` folder (the two pictures are in `phase6a/`). *State: **documents corrected**; the
    pictures stay in `phase6a/` with their walk, and LIMITS says so; a closed assessment's sentence shows in the
    terminal's request log (LIMITS).*
12. **Tests the plan names that are thin**: Approve with some approvals given, a page-only answer in a closed
    assessment, the reply card after its entry changed, a tab command where the read after it differs; 8 of the
    32 lines are never asked against an assessment; 19 lines have one wording. *State: **partly done** (tests for
    Approve, the closed page-only answer, the stale card, the tab and the narrowed plan were added). **Still
    open:** eight lines (reconsider, run proof again, open pull request, retest now, try, ask for approval,
    measure a library, roll back) are read by the rules in a test but never asked against an assessment at the
    stage where their button exists; most lines have one wording in the tests.*

Checked by the reviewer and found met: nothing happens before Confirm but moving around (all eight kinds of
answer traced through the panel); a card for a command is the panel's own card; a button that is off gives the
page's reason and no Confirm step; typed text is data (fixed patterns, 500 characters, stored and drawn as text);
the table is add-only; the package only reads and no model is asked; address filters; counts in answers follow
the pages' own rule; no "secure", score, severity or sentence about what Otto did; the documents say plainly
that the Claude step is not built.

## Step 5: phase 6c, questions (first half built, tested, documented, reviewed; the review's 13 findings fixed, walked on the final code)

Commit: `c7472a4`. The plan's "shorter first half": the six fixed questions alone, answered by rules, with no
Claude step.

What is built:
- **Six fixed questions** ("Why did this check fail?", "What does this result show, and what doesn't it?", "Where
  did this suggestion come from?", "What happens if I accept this?", "What is this page for?", "What should I do
  next?"): the rules that read one in its common wordings, which of them fit a page and an open item (up to three
  chips above the examples), and the rules that pick the facts of an answer
  (`backend/app/assistant/questions.py`).
- **An answer is a list of facts**, headed "From this assessment's records". Each fact is a sentence a page of the
  app already shows for the item, with a link to where it is shown. Nothing in an answer can be pressed but the
  links; it words no result and rates nothing. With several that fit and none open: "Which one?".
- **Kept** with the facts of its answer in an open assessment, and listed in its thread; a closed assessment
  answers and keeps nothing. What is kept holds its times in UTC words, and a browser shows them in the viewer's
  time (`app/present/times.py`, `remarked`).
- The text box now reads "Ask Otto, or tell it what to do" (the plan's wording for 6c).
- Documents: SPEC sections 2, 3 and 9; CLAUDE.md (the rule-based rule, what is kept, the Tests rule); LIMITS
  "Limits of phase 6c, first half"; README "Asking Otto a question"; LAYOUT.

Test results: backend `tests/assistant` and `tests/times` **155 passed** (27 in `test_questions.py`; the shared
walk now also says every option of every "Which one?"); **815 screen tests passed** (7 for the questions); lint,
type check and generated files clean. The walk `e2e/tests/assistant.spec.ts`: **2 passed (5.7 minutes)**: on
Evidence the chip "Why did this check fail?" asks, "Which one?" lists the failed checks, the chosen one answers
with its facts, "See the evidence" opens the result, whose plain sentence is word for word the answer's second
fact, and "Open the advisory" opens the advisory. Picture: `docs/screenshots/phase6a/08c-evidence-why-did-this-
check-fail-dark.png` (and `-light`).

Found while building it and fixed: a kept answer would have stored the browser's time marks (now UTC words, with
a test that walks it with the browser's header on); the panel's read, a command and a question did not count
what waits the same way, so "What should I do next?" named another next step than the Overview.

**Not built (the second half):** answers in free words by Claude from a fact sheet, with "Hypothesis", "Facts
used" and "What was sent", the two labels, recorded answers for the walk, the status line about spending, and
the Settings line on what is sent. The CLAUDE.md rule changes 3, 7, 8 and 9 of the plan are therefore not
applied.

**What the separate reviewer of 6c found (report of 07:46 UTC, on commit `c7472a4`; verdict: "not ready as
committed": the promise that nothing runs or changes holds, but an answer can state something untrue in several
ordinary situations, and "Which one?" can still loop).** State of each finding is kept current here.
1. **A name the rules don't know gets a false "there is none"**: with four checks failed, "why did the moon check
   fail?" answered "No check of this assessment reads Failed now."; the same for a suggestion ("Nothing is
   proposed"), and for question 2 in slightly other words. *State: **fixed** (a name nothing is called gets "I
   can't do that. No test of the plan is called that."; the "none" sentences are said only when true).*
2. **"Did not fail" was said about a failing result** ("Slowdown found" after a retest; also for "Couldn't run"
   and "Couldn't trust this run"): the assistant worded a result of its own. *State: **fixed** (a failure is read
   from the tone the page draws the result in; the answer repeats the result's word and never says "did not
   fail").*
3. **"Accept waits for your Confirm, here and on its page." is untrue of the page**: there, Accept records at the
   click. *State: **fixed** (the answer now says the difference between the panel and the page).*
4. **"This check" is not always the open item**: with an open item that has no result, the answer was about a
   failed check elsewhere; with a fix proof's row open, it answered with the first run's result. *State: **fixed**
   (one rule says what the open item is, for the answers and for the chips; an item with no test result of its
   own gets a sentence that says so).*
5. **Where several tests share a title** (the multi-target demo file: one "Old TLS versions" for each server),
   "Which one?" never settles. *State: **fixed** (such tests are named with their target, for questions and for
   Run and Open; a unit test with two servers). **Not yet walked on the real multi-target demo file.***
6. **"Waits for a decision" where nothing can be decided** (a closed assessment, Otto not installed, a plan change
   that is no longer proposed). *State: **fixed** (counted as the Overview counts).*
7. **Evidence's count was the test plan's only** ("0 results" right after Verify, with three verified claims
   listed). *State: **fixed** (the sentences speak of the tests of the plan).*
8. **Three of the ten page sentences do not match their pages** (Advisories, Fixes, Roadmap). *State: **fixed**
   (all ten follow the pages' own header sentences; a test holds three of them to the backend's wording).*
9. **A data folder made by the 6b build breaks the panel** (its `assistant_messages` table has no `facts`
   column). *State: **fixed** (the column is added when such a folder is opened; a test).*
10. A title that holds a kind word: *fixed in `7017bda`* (the reviewer confirmed it gone).
11. **The exact-title rule looks at every name, not only titles** ("accept yes" brought up the card of the fix
    whose stored value is "written: yes"; decisions still wait for Confirm). *State: **fixed** (only a title counts
    as an exact name; ids, fingerprints and stored flags name nothing).*
12. **What is kept**: a question asked beside the Overview is listed in no tab; a typed reject reason that holds a
    time in UTC words is rewritten into the viewer's zone in a kept answer. *State: **the second is fixed** (only
    the times the app itself wrote are marked again). The first: "What should I do next?" is now filed under the
    thread of the page its next step sends to; "What is this page for?" beside the Overview is still listed in no
    tab (decision 18).*
13. Small things: more than eight fits cut without a word; an advisory with several accepted checks takes the
    first silently; "What is the fix for?" read as "What is Fixes for?"; a line that quotes Evidence as Fixes;
    two facts without a link; "There is no page of that name" without the list; the reply's label for screen
    readers reads "Otto's answer". *State: **all fixed.***

Checked by the reviewer and found met: the reader does not crash (3,000 random strings; 33 hostile inputs of 500
characters took 2 ms at worst) and nothing misread acts; no time mark is stored; a closed assessment keeps
nothing; the table is add-only; the read-only promise holds (480 questions with Live Otto on and a stand-in:
nothing changed, Claude never asked); text is drawn as text; nothing in an answer can be pressed but links; no
"secure", score, severity or sentence about what Otto did; nothing outside SPEC section 2. These states came out
right: a retest after a failed first run, a check that passed in the retest, rejected and undone proposals, no
file, not verified, nothing run.

Tests after these fixes: backend `tests/assistant` and `tests/times` **195 passed** (12 new tests, one or more for
each of findings 1 to 9, 11 and 12); **820 screen tests passed**; lint, type check and generated files clean.
After that: the panel walk on this code, **2 passed** (5.9 minutes), with its pictures retaken; and for finding 5
a test on the real multi-target demo file (`backend/tests/test_multi_target.py`: every "Which one?" option names
one server's test and settles), 20 passed. There is no walk step on the multi-target file: the backend test asks
the same sentences through the same path as the panel. One more thing the complete run of every walk found is in
"What the complete run of every walk found" above (a fact's link, fixed in `e16786f`).

## Step 6: phase 6d, Change watch (started: two backend checkpoints; nothing of it is on a page yet)

The plan's shorter first half: **Changes without the Watch list**. Built in checkpoints, each committed with its
tests, so that a stop between two of them leaves the app as it was: until the page is built (checkpoint 3) there is
no route and no button, and nothing of Change watch can be seen or started in the app.

**Checkpoint 1 (`3322971`): a developer's change is read, and its tests are picked.**
- `demo/changes/`: the two bundled demo changes as data files ("Revert the range check", offered once a fix is
  merged; "Allow TLS 1.0 for an old partner"). A change names its branch, its commit message and the files it
  leaves. A program comes only by the name of one of our registered demo programs: no change holds program text,
  and the reader refuses one that does (`backend/app/changewatch/demo_changes.py`).
- `backend/app/changewatch/state.py`: `change_watch_state` reads the connected repository on every call. Every
  branch that is neither the connected branch nor one of the app's own changes is a developer's change: what it
  touches, the tests picked for it and the rule that placed each one (fixed rules, by file; no Claude step), which
  registered program its code is (the byte-for-byte check), and its flags. `bring_in_demo_change` writes one
  branch with one commit by "Demo developer" and runs nothing.
- Flags: `backend/app/changewatch/flags.py`, and the short list `OLD_CRYPTOGRAPHY` in
  `backend/app/engine/guidance.py` (SSL 3.0, TLS 1.0, TLS 1.1, SHA-1, MD5, RC4, 3DES, each with its source). A
  flag comes only from a line a change adds, and is never a result.
- Tests: `backend/tests/changewatch/` **51 passed** (6 seconds): every state from "not connected" to "a fix
  merged"; bringing a change in writes four repository files and no database row; the picking rules; a change
  that is not a registered program cannot run; several commits; a branch that starts elsewhere; a damaged
  repository; reading writes nothing; seeded fuzz of both new readers.

**Checkpoint 2 (`2aa07a2`): the watch run, and the reviewer's rule for it.**
- `run_picked_tests`: the one way a watch run starts. First the byte-for-byte check (the change's code, and the
  code it starts from, must each be a registered demo program; the registered program is what runs). The picked
  tests then run through the same runner and locked tests as every run. "Before" is each test's newest reviewed
  run on exactly the code the change starts from; where there is none, that test also runs on that code.
- `RuleReviewer.review_watch`: places each test (fails now, passes now, same, not compared, not trusted) and sets
  the change's status word, and nothing else. A test that could not run is not compared. The stored review is
  believed only while reviewing again gives exactly it.
- Kept apart: two add-only tables (`watch_runs`, `watch_reviews`) and two run phases (`watch`, `watch_base`) that
  nothing reading the assessment's own results looks at. A test compares Evidence, the test plan, Fixes, Checks
  and the Overview before and after a watch run: only the Overview's "runs recorded" moves.
- Tests: `test_watch_run.py` **28 passed** (one of them in the slow set), and the tests around the touched core
  (`test_changes.py`, the proof, speed and retest rules, the reviewer, jobs) **194 passed** together.
- **Decided while building, for Kevin to confirm (decision 19):** a watch run of an advisory check is **not**
  bound in the assessment's Otto ledger. The ledger's pinned checker of 5c knows three run phases and must not be
  changed; the plan puts the new pinned checker for watch runs in the Watch list half. Until then such a run is
  kept with its change, in the database (and in the signed evidence, once checkpoint 4 is in).
- **Also decided (decision 20):** the status list of the plan has no word for "a picked test could not run". Such
  a watch run reads **"Can't run"** (a stop is not a result, so it is neither "No difference found" nor a
  difference).

**Still to build for the first half, in this order:**
3. The page and what shows on other pages: routes and shapes (`backend/app/web/`, `models.py`, then
   `tools/api_schema.py` and `npm run gen:api`); the words (`backend/app/present/changewatch.py`); the page
   "Change watch" after Fixes with the Changes view (table, panel: lines before and after, Tests picked and Not
   picked with reasons, Run the picked tests then Run again, results before and after, Flags, Related) and Bring
   in a demo change (Demo data); the page in the assistant's lists (`threads.py` `PAGES`, `PAGE_THREAD`,
   `words.py` `PAGE_FOR`; `router.ts`, the sidebar); the panel's next step for Run the picked tests behind
   Confirm; the label "From a developer's change: branch, commit" in Evidence and "Came from: Change watch" on
   Checks (`ledger/checks.py`: `ORIGINS`, `PHASE_ORIGIN`, `_row_key`); the Text-only entry in Fixes "Came from:
   developer's change" when tests that passed now fail (`ChangesMixin._fix_sources`). Screen tests; the tables at
   1440 pixels.
4. The evidence part `change_watch` (added only when there is something to put in it: the exact list of the
   file's parts is pinned by `tests/test_evidence.py`), the report's part 9, and the verify command
   (`backend/evidence/`: a new check called like `check_otto`).
5. The walk `e2e/tests/changewatch.spec.ts` (ports of its own), pictures in `docs/screenshots/phase6d/`,
   SPEC section 2 (the plan's wording for 6d, without the Watch list), CLAUDE.md (the plan's rules 6 and 10),
   LIMITS, README, LAYOUT, the questions for `docs/OTTO-KEY.md`; one separate review; fixes.
**Not in the first half:** the Watch list (its proposals, rechecks and the new pinned checker).

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
10. The fast test set: three shared walks moved to the slow set, as decided, and tonight the Otto panel's
    shared walk too (its 54 readers). The numbers are in "The long checks". On GitHub's runner the fast set takes
    4 min 59 s without Otto: at the limit. To be safely under five minutes everywhere, either tests run in
    parallel (pytest-xdist, a developer-only package: your OK needed) or the readers of the shared demo walk (a
    large part of the fast set) move to the slow set too. Which do you want?
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
18. Phase 6b: a sentence typed beside the Overview that belongs to no thread (and one that opens Settings) is kept
    with the assessment and listed in no tab. Should it be listed in the tab that is open, in all three, or not be
    kept at all?

19. Phase 6d: a watch run of an advisory check is not bound in the assessment's Otto ledger in the first half
    (the 5c checker of the ledger is pinned and knows three run phases; the plan's new pinned checker for watch
    runs belongs to the Watch list half). Is that right until then?
20. Phase 6d: where a picked test could not run, the change reads "Can't run". The plan's list of statuses has no
    word of its own for it. Should it?

## The exact next action

1. **Read the results of the long checks that were running when this was written** (all on `2aa07a2`, one after
   another): the fast set with Otto, timed (`cd backend && .venv/bin/python -m pytest -q tests`), and without
   (`EVIDENCE_LAB_OTTO_HOME=/some/empty/folder` in front); every walk once (`cd e2e && npm test`, about 50
   minutes; `E2E_APP_LOG=/some/file` in front keeps the request log); the full backend set (`cd backend &&
   .venv/bin/python -m pytest -q tests --full > FILE 2>&1`, about 40 minutes with Docker ready). If this file
   still says "running" for them, run them again, one at a time and with nothing else running, and write the
   results into "The long checks". A complete run of the walks rewrites every picture: keep only folders retaken
   on purpose and put the others back with `git checkout -- docs/screenshots/<folder>`. **`docs/screenshots/
   phase6a/` is to be retaken on purpose from that run**: since `043c5ac` a result's panel starts with its plain
   sentence, and the picture `08c-evidence-why-did-this-check-fail-*.png` shows it.
2. Read the newest run of "Checks" on pull request #7 (GitHub), and correct what it shows.
3. **Go on with 6d at checkpoint 3** ("Step 6" above lists what is left, in order). It is being built in a
   separate working copy while the long checks use the main one; everything committed there is on the branch.
4. After 6d's first half: **6e** at least its shorter first half (the what-if facts and the try), then the second
   halves of 6b and 6c (the Claude steps, with the CLAUDE.md rule changes the plan lists for them). Each: plan,
   build, tests, one walk, pictures, documents, one separate review, fixes, commit, push, this file. Phase 6's
   plan is the Claude Doc "Phase 6 plan: Otto assistant".
5. Two leftovers of 6b's review (step 4 above, finding 12): eight command lines are never asked against an
   assessment at the stage where their button exists, and most lines have one wording in the tests.
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

