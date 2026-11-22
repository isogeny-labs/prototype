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

Written at 22:46 UTC on 19 November 2026 (machine time), at the end of a verification session that Kevin asked for:
a fresh separate review of phase 6e, its fixes, and the three long checks on the final code. The exact next action
is the section before the appendix. In one line: **steps 1 to 3 and the first halves of 6b, 6c, 6d and 6e are built,
tested, reviewed with their findings fixed (6d twice, 6e on `0503ede`: 8 findings, all fixed with tests), committed
and pushed. On the final code commit `0503ede`: the full backend set with Otto passed (2435), every walk passed once
(102), the accuracy check in isolated mode passed (exit code 0: all four keys), and all GitHub checks are green. The
second halves (free wording and free answers through Claude, the Watch list, a hypothesis turned into a test) are
not built, as agreed. Pull request #7 is a draft and is not merged.**

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
| 14 | What-if and hypotheses | **First half done; reviewed (8 findings, all fixed with tests)** (6e: the what-if facts and the try): built, tested, documented, walked. "What if I update elliptic to 6.5.7?" typed into the panel gets one card: what the app knows (where the library is used, the dependencies the new version declares against the one you have, the advisories it answers, the pack's trial, post-quantum support of both versions, the track it blocks, your own results), each line with its label and link and an honest "not known" where the app knows nothing; the try on a test copy (Evidence's own Retest new version behind Confirm), proven on a real library in a real container; and what the facts do not show under Hypothesis. **Not built (the second half): the two buttons on a hypothesis (Turn this into a test, Add to Change watch) and Claude's explanation.** So "every unproven point has its two buttons" is not met |
| 15 | Change watch | **First half done** (6d: Changes without the Watch list): built, tested, documented, walked, reviewed once (8 findings, all fixed with tests). A developer's change is listed with the tests picked for it and why; **Run the picked tests** runs them (on the page, or from the Otto panel's card behind Confirm) and the change reads, for the demo, "Passed before, fails now"; the runs show on Checks and Evidence as "Came from: Change watch"; Fixes gets a Text-only entry for the change; a line that names old cryptography is flagged; the signed evidence file and the report hold the changes and their runs, and the verify command checks them. What was built after that review (the evidence part and its verify check, the entry in Fixes, the panel's step) had **a second separate review: 7 findings, all fixed** (`80c27a5`; see "Step 6"). The entry in Fixes is now listed under its own heading and counted nowhere. **Not built: the Watch list** (the second half) |
| 16 | Nothing without a click and Confirm; works without a key | **Holds for everything built**: 6a, the research loop, 6b, 6c and 6d work with no key (no part of the panel asks Claude in this version), with tests. Change watch starts nothing by itself: bringing a change in runs nothing, and the picked tests run only on a click |
| 17 | Keys match in both modes, fast tests under 5 minutes, each step reviewed, committed, pushed | **Keys: match in both modes on the final code commit `0503ede`** (isolated: exit code 0, 18 of 18, 47 of 47, 33 of 33, 220 of 220; demo: green in the GitHub checks on every push). **Fast tests: 4 min 59 s with Otto, measured alone** on `3885e19` (1917 passed): just under five minutes, at the limit (decision 10). **Each step reviewed, fixed, committed, pushed**, 6e included |
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
only) · `b3c3ea4` this file · `ff5f30c` **6d, checkpoint 3a** (the page's read and two actions, shapes, words) ·
`ed05b33` **6d, checkpoint 3b** (the Change watch page) · `7500297` 6d in SPEC, CLAUDE.md, LIMITS, README, LAYOUT ·
`fa1e1b6` **6d: the walk, with its pictures** · `e5725f7` this file · `81e2b11`, `0f972db` two things the GitHub
checks found (a test's own pattern; a route that took a name by a pattern) · `90332ef` **6d: a watch run's rows on
Checks and Evidence** · `12e342b` **a read that crossed a change is asked again** (what the second complete run of
the walks found) · `31eaf59` **6d: the separate review's eight findings fixed** · `2422941` **6d: the evidence part,
the report's part 9 and the verify command's check** · `5a07467` **6d: the Text-only entry in Fixes** · `d1ccc61` a
slow test that still expected "in Otto's words" · `49d1f0d` **6d: the panel's step, and the walk through it, with
its pictures** · `b41f631` 6d in the documents, the questions for the fifth key, this file · `c8c7637` **6e,
checkpoint 1** (what a library version declares it needs) · `1ea9a60` a row never shows a finished job without its
result · `61e2efd` **6e, checkpoint 2** (the what-if facts and the sentence that asks) · `953b109` **6e, checkpoint 3**
(the card in the panel) · `36ed916` **6e: the walk, with its pictures** · `80c27a5` **6d: the second review's seven
findings fixed; 6e in the documents** · `2d49dd8` **6e: the try on a real library in its container, and the what-if
questions for the fifth key** · `e58fba2` this file · `49aa096` a test that the report lists a change's entry in
Fixes under its own heading · `3885e19` **the fast set: the long shared walks go to the slow set** · then the Change
watch walk's pictures, `docs/ACTIVE.md` and this file.

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
| After the review of `e16786f` (five findings, fixed in `043c5ac`) and 6d's two backend checkpoints (`3322971`, `2aa07a2`): the fast set with Otto and without | `2aa07a2` | **1852 passed** with Otto (6 min 25 s) and **1754 passed, 98 skipped** without (5 min 22 s). Both ran while other work ran on the machine, so the times are not a measure |
| Every walk once, third complete run | `2aa07a2` | **98 passed, 1 failed, 1 did not run** (54.8 min). The failure is real and is fixed in `12e342b`: see "What the third complete run of the walks found" below. The one that did not run is the next step of the same serial walk |
| The full backend set (every slow test too) | `2aa07a2` | **Cut off** at the two-hour limit of the background run, 60% through, with one failure it had not named yet |
| The 6d review's fixes: the fast set with Otto and without, the screen tests, the Change watch walk | `31eaf59` | **1903 passed** with Otto; **1805 passed, 98 skipped** without; **843 screen tests**; the walk **1 passed** (2.2 min). (Times of the two fast sets, 8 min 54 s and 6 min 38 s, were taken with three other test runs going: not a measure) |
| The full backend set again, with each test's name | `31eaf59` | **Running when this was written** (output: the scratch folder's `g-full.txt`). So far two failures in about 1,700 tests. (1) `tests/otto/test_otto_fix.py::test_otto_writes_the_change_and_a_view_asks_nothing`: real, and the test's fault: it still split a sentence on "in Otto's words", which step 1 removed on purpose. Fixed in `d1ccc61`; the file then passes in full (23 passed). (2) `tests/test_changes.py::test_connecting_makes_the_plans_own_copy_and_starts_the_proof_by_itself`: passes when run alone (81 s). Its fixture looks at a proof while it is still running, and four other heavy runs were going on the machine. **Read the run's own report for it when it has ended**, and run the set once more with nothing else running |
| The GitHub checks | `90332ef` and before | Backend was **red from `ff5f30c` to `fa1e1b6`** for one reason: a new route named its parameter `{key}`, and a test holds that no route's address contains "key" (it guards the signing key). Renamed in `90332ef`. CodeQL raised one alert ("polynomial regular expression used on uncontrolled data", the same route); the pattern is gone since `0f972db` and CodeQL is neutral. **The checks on `31eaf59` and later have not been read yet** |
| 6d after its review: the evidence part, the Fixes entry, the panel's step | `49d1f0d` | `backend/tests/changewatch` **175 passed** in the fast set (177 in full); with `backend/tests/assistant` in full **375 passed**; the evidence, fixes, ledger, projects and time tests in full **450 passed**; **845 screen tests**; lint, both type checks and the generated files clean; the walk **1 passed** (2.2 min) with the new steps. Otto's accuracy walk in demo mode: 155 answers collected, not compared (the fifth key is not written, as agreed), exit code 2 as designed |
| 6d after its second review, and 6e: lint, both type checks and the generated files; `tests/changewatch`, `tests/assistant` and `tests/whatif` in full; the fast set with Otto; the screen tests | `80c27a5` (the working copy before the commit) | All clean; **463 passed** (2 min 44 s); the fast set **2047 passed** (7 min 0 s, with another run going); **852 screen tests** passed |
| 6e: the try on a real library in real containers (`backend/tests/whatif/test_whatif_real.py`) | `2d49dd8` | **4 passed** (4 min 34 s) |
| Otto's accuracy walk in demo mode (`--only otto`), with the new Change watch and what-if questions | `2d49dd8` | **190 answers collected**, none compared (the fifth key is not written, as agreed); exit code 2, as designed |
| The separate review of 6e | `2d49dd8` | **Stopped before it reported**: the session's usage limit was reached. Nothing of it is used. It is the first next action |
| The Change watch walk after the second review's fixes | `80c27a5`, then `3885e19` | The first run **failed** at one comparison: it read Evidence's rows by their drawn text while the fast set ran beside it, and a row that is in the page but not drawn yet reads as one unbroken line. The walk now compares the rows' own text (`3885e19`). Run again **alone** on `3885e19`: **1 passed (2.1 min)**. Its 16 pictures are retaken and committed; the Fixes picture shows the entry under "From a developer's change (1)" |
| The fast set after the long shared walks moved to the slow set (decision 10) | `3885e19` | **1917 passed, 502 left out as slow, in 4 min 59 s with Otto, alone: just under five minutes, at the limit** |
| The GitHub checks | `3885e19` | **All green**: Backend twice (for the push and for the pull request: 4 min 50 s and 6 min 41 s), Frontend twice, CodeQL and its three analyses |
| 6e after its separate review: lint, both type checks, the generated files; `tests/assistant` and `tests/whatif` in full (the four tests in real containers among them); the screen tests | `0503ede` (before the commit) | All clean; **291 passed**; **852 screen tests** passed. The 14 new test cases and the card's new screen check each fail on the code before the fix |
| **The full backend set, with Otto, every slow test too** | **`0503ede`** | **2435 passed, none failed, none skipped (45 min 15 s), alone, Docker ready** |
| **Every walk once** (`cd e2e && npm test`) | **`0503ede`** | **102 passed, none failed or flaky (48.3 min), alone.** Its pictures were put back except the six of phase 6e (the card's wording changed with the fix) and `phase6a/08c-evidence-why-did-this-check-fail-*.png` (the retake the handoff planned), which are committed |
| **The accuracy check in isolated mode** (`python -m app.accuracy --mode isolated`) | **`0503ede`** | **Exit code 0** (19 min 55 s, alone): first key 18 of 18, migration 47 of 47, real libraries 33 of 33 with trial counts 6 of 6 unchanged, dependencies 220 of 220. Otto is not graded (the fifth key is not written, as agreed). This replaces the last isolated run, on a frozen copy of `5699057` |
| The GitHub checks | `0503ede` | **All green**: Backend twice, Frontend twice, CodeQL and its three analyses |
| A note for the next session on this machine | (environment) | After a restart of the session's worker, Docker was not running and `service docker start` failed (the container may not set a limit the start script asks for). Starting the daemon by hand worked: `setsid nohup /usr/bin/dockerd > some.log 2>&1 < /dev/null &`. Its prepared images were still there |

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

### What the third complete run of the walks found (12:09 UTC), and what was done (`12e342b`)

**98 passed, 1 failed.** In the Fixes walk a seventh test was added to the plan, and the plan went on showing six
cards. The page had the answer to the add; then the read of the plan that it had sent when it opened landed after
it, holding the plan from before the add, and nothing read again.

Why it showed now: since `e16786f` the reads under `/api` take turns on the server, so a read can be on its way
for a while, long enough for a person (or a walk) to click in the meantime. The order "read sent, change sent,
change answered, read answered" was always possible; it has become likely enough to happen.

The fix is in the one place every request of the browser goes through (`frontend/src/api.ts`): a read that was on
its way while a request that changes something was answered (or failed) is asked again, at most twice, before the
page gets it. A request that changes something is never sent twice. Tests: `frontend/src/test/api.test.ts` (four),
and a screen test of the test plan inside Checks with exactly the walk's order of answers; it fails without the
fix. `docs/LIMITS.md` says what this does not cover (a change made in another browser tab).

**Not yet done:** a complete run of every walk on a commit that has this fix. The Change watch walk has run on it
three times (it presses a change and reads right after), green.

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

## Step 6: phase 6d, Change watch (first half built, documented, walked, reviewed twice; both reviews' findings fixed)

The plan's shorter first half: **Changes without the Watch list**. Built in checkpoints, each committed with its
tests, so that a stop between two of them leaves the app in a state that can be shown. Since checkpoint 3b the page
is in the sidebar and works; `docs/SPEC.md` section 2 and `docs/LIMITS.md` ("Limits of phase 6d, first half") say
what is built and what is not.

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

**Checkpoint 3a (`ff5f30c`): the page's backend.** `backend/app/present/changewatch.py` (the words: a status
word with one sentence that says why; a reason for each picking rule; a flag's sentence and note),
`backend/app/changewatch/views.py` (`change_watch_view`: before and now repeat the reviewer's own word and plain
sentence), `backend/app/web/changewatch.py` (one read, and two actions with no body: `POST
.../change-watch/demo/{key}` and `POST .../change-watch/{change}/run`, both under the closed guard), the shapes in
`models.py`, the generated frontend types. Tests: `test_watch_view.py`, 10 (the view at each stage in its shape and
words; marked times for a browser, UTC for a file; login; every refusal; a closed assessment).

**Checkpoint 3b (`ed05b33`): the page.** `frontend/src/components/ChangeWatchScreen.tsx` (the table and **Bring in
a demo change**) and `changewatch/ChangePanelView.tsx` (a change's panel: what changed line by line, Tests picked
and Not picked with reasons, **Run the picked tests** then **Run again**, the results before and on the change,
Flags). The page is in the router, the sidebar (after Fixes) and the assistant's lists (a Testing page; "open
change watch"; its sentence for "What is this page for?"). Tests: 13 screen tests (`ChangeWatch.test.tsx`); the
three tests that pin the list of pages and of side panels name the new one. **834 screen tests pass.**

**Documents (`7500297`):** SPEC section 2 and section 9, CLAUDE.md (one product rule, one safety rule, the test
folder), LIMITS, README ("Change watch"), LAYOUT.

**The walk (`fa1e1b6`):** `e2e/tests/changewatch.spec.ts` on its own copy of the app (port 8034, demo server
8467). **1 passed (2.0 minutes)**, run twice. It goes from "Connect the demo code first" through the merge of the
fix with the Fixes page's own buttons, brings in both demo changes, runs the picked tests ("Passed before, fails
now (2 tests)"), checks that Evidence reads exactly what it read before, reads the flag, and measures the table
and the panel at 1440 pixels wide. Pictures: `docs/screenshots/phase6d/` (ten, dark and light). The first pictures
showed a long branch name broken between letters in the panel's header; corrected.

**Checkpoint 4 (`90332ef`): where a run shows outside its page.** Checks gets a part "Change watch" under
Encryption tests once a run was made: one block for each run ("From a developer's change: branch, commit"), one
row for each picked test, each saying where it ran and leading back to the change; a row opens like every check.
Evidence lists the same tests with "Came from: Change watch". The Change watch panel links each side of a result
to exactly its run.

**The separate review of the first half (after `90332ef`): eight findings, all fixed in `31eaf59`, each with a
test.** The reviewer wrote probes of its own (they are in the scratch folder, `review-6d/`).

| # | What the reviewer found | What was done |
|---|---|---|
| 1 | **A watch run of an advisory check reached Otto's side.** The proposal for the migration plan moved to the watch run, the Project overview counted it as an advisory check "run since", and an accepted check could no longer be undone | Otto's four reads of a check's runs leave the two watch phases out (`backend/app/otto/proposals.py`). New test (`test_watch_otto.py`, needs Otto, slow set): everything Otto shows is the same before and after such a run. It fails on the code before the fix (run to see) |
| 2 | Two tests only passed in November 2026 | They take any date |
| 3 | While one change's picked tests ran, every other change that picked the same tests read "Running" | Only the plan's newest watch run has live jobs; the others keep what their own run found. Test with two changes |
| 4 | The page could stay behind: it stopped asking after one failed read, and did not ask at all while another kind of work kept Run switched off | The view says "busy" while anything runs for the assessment; the page asks again after a failed read and says so on the page. Backend and screen tests |
| 5 | The flag rule matched too much: "ELBSecurityPolicy-TLS-1-2-2017-01" as TLS 1.0, "3 destinations" as 3DES, "tdeadline", "triple description", a commit id after "sha" | The patterns read what follows the name. 24 more lines in the rule's test |
| 6 | The speed test was compared by its word before and now, but a first run only measures and a retest compares with something older | Its run on the change is timed side by side with the code before, so that one run places it: "Slowdown found" counts with the tests that fail now; anything else reads "No slowdown against the code before". **Decision 21** |
| 7 | Smaller: the plan's card offered Remove for a test with a watch job going (the request was refused); a file that names acme-sign 1.4.3 was told to connect the demo code, which Fixes refuses; a change to the program with no test that runs it said no program file was edited; a test that left the plan lost its name; "1 of 1 tests have run" | All five corrected, with tests |
| 8 | Tests that were missing: two changes at once; which run is "before" when several could be; a damaged repository through the page's read; the speed rule's table | Added, with a seeded fuzz of the connected repository (150 copies with one file damaged or gone: read, or said plainly, within a time limit) |

The reviewer also pointed out that the signed evidence file had begun to list a watch run's rows without holding
the run's record. That is what checkpoint 5 builds.

**Checkpoint 5 (`2422941`): the evidence file, the report and the verify command.** Once a developer's change is in
the connected repository the signed file has a part `change_watch`: each change as it was read when the file was
made (branch, commits, the fingerprint of every file before and after, the tests picked and not picked with their
reasons, flags, status), and every watch run that was kept, with both runs of every picked test in full, the record
the reviewer was given, its fingerprint and the stored review. The report has part 9, "Change watch".
`backend/evidence/changewatch.py` checks the part against the runs in the file: each run record against its
fingerprint and its review; that each run ran on the change's code; the record against the runs; the reviewer's word
for the change against the record, by the rule, which is written out a second time there so that a file is not
checked with the code that made it; each change's status against its run; and every Change watch row of the file's
list of checks against the part. A file that lists such a run and has no part fails. Tests
(`test_watch_evidence.py`, 37): what the file holds at each stage; 27 changes inside the part, each signed again
with the app's own key, each caught with its own sentence; the two copies of the rule compared over every
combination; the report; 400 damaged copies of the part (seeded). A file that also has Otto's part verifies with
both parts checked (`test_watch_otto.py`).

**Checkpoint 6 (`5a07467`): the entry in Fixes.** While a change reads "Passed before, fails now", Fixes lists one
entry for it under Encryption tests: "*title*: *N* tests that passed now fail", "Came from: developer's change
*branch*", the tests by name with the code each ran on, and the lines the change takes out, drawn as Fixes draws a
change. **Text only**: no button, no proof, no pull request; the app writes no change for a developer's branch.
The change's panel says so in one line with **View in Fixes**. The entry goes when the change no longer reads so.
The test that holds watch runs apart now holds Fixes entry by entry (every entry that was there is as it was;
exactly one is new). (As first built, the Overview's count of open fixes went up by that one. The second review
objected, rightly: see its finding 6 below. Since then the entry is listed apart and counted nowhere.)

**Checkpoint 7 (`49d1f0d`): the Otto panel, and the walk through it.** Beside Change watch the panel offers the
page's own **Run the picked tests** behind Confirm (the page's request, with the change's id, and nothing else).
Two lines in the fixed list of commands: "Run the picked tests" (a card with its Confirm step; "for *the change*"
where several can run) and "Bring in a demo change", which stays on its page. The entry in Fixes arrives in the
Fixing thread. Tests: `test_watch_panel.py` (8), the list of commands, and the panel's screen test that every kind
of next step sends its page button's request.

**The walk as it now is** (`e2e/tests/changewatch.spec.ts`, port 8034, demo server 8467): **1 passed (2.2
minutes)**. Before the code is connected; the fix merged with the Fixes page's own buttons; "Revert the range
check" brought in; the picked tests and why; **the run started from the Otto panel's card behind Confirm**, with
the page measured beside the panel; "Passed before, fails now (2 tests)"; **View in Fixes** to the Text-only
entry; the run's rows on Checks and Evidence; Evidence reading exactly what it read before; the second change
with its flag; the table alone; **the evidence downloaded and the verify command run on it** (exit code 0, with
its two Change watch lines; the report has part 9). Pictures, dark and light: `docs/screenshots/phase6d/`, 16
files (01, 02, 02b the panel's card with its Confirm step, 03, 03b the run on Checks, 03c the entry in Fixes, 04,
05).

**The fifth answer key.** Otto's accuracy walk (`python -m app.accuracy --only otto`) now also walks Change watch
on the Acme Pay demo, after everything it did before, and `docs/OTTO-KEY.md` lists the new questions (which tests
are picked for each demo change, each result before and on the change, the status words, the entry in Fixes, and
the verify command on a fresh download and on three changed copies). In demo mode it collects 155 answers and
compares none, as before: the key is not written, and it is not mine to write.

**Documents:** SPEC section 2 (Change watch, the panel's lists, the page-only commands) and section 9; CLAUDE.md
(the product rule, the verify command, the walk, the ask-again line); LIMITS ("Limits of phase 6d, first half":
rewritten for what is built, with what the verify command takes as given and that the rule is written twice);
README ("Change watch"); LAYOUT; OTTO-KEY.

**Test results for 6d:** `backend/tests/changewatch/` **175 passed** in the fast set, **177** in full; with
`backend/tests/assistant` in full **375 passed**; the evidence, fixes, ledger, projects and time tests in full
**450 passed**; **845 screen tests**; lint, both type checks and the generated files clean; the walk green.

**The second separate review** (of what was built after the first one: the evidence part and its check in the
verify command, the entry in Fixes, the panel's step, the new questions of the accuracy walk). It read the code at
`b41f631`, made evidence files at eleven stages of the demo and tried to get changed files past the verify
command. It found **seven things; all seven are fixed** (the commit after `36ed916`):

1. *A changed status could get past the verify command.* The command held a change's status to its run only where
   the change's own entry said that the run counts. Someone with the app's key could take the run out of the
   change's entry, say the run was "of other tests", name an older run, or change the count in the status word,
   and the file still verified. **Fixed:** the command now works out by itself which run counts (the newest run of
   exactly the change's code), works out again from the two lists whether that run is of the tests picked now,
   and holds the count in the status word to the reviewer's counts. A picked test now carries the fingerprint of
   its locked plan in the file, so the two lists can be compared.
2. *"Ran on the change's code" was read from a note beside the run, not from the run record.* A run on the code
   before could be put where the run on the change belongs. **Fixed:** the version, the commit, the file's
   fingerprint and the kind of run are read from the run record itself, and the change's own files and versions
   are compared with its run's.
3. *The report said something untrue about the settings change.* For "Allow TLS 1.0 for an old partner", which
   leaves the program alone, part 9 of the report read "Its code is not one of our registered demo programs".
   **Fixed:** the report now says that the change leaves the program alone; a file made when the repository could
   not be read says that; and the accuracy walk gives two answers for each change (`edits_the_program` and
   `code_is`) so that "none" cannot be read as "not ours". `docs/OTTO-KEY.md` words the two questions.
4. *An honestly made file could fail.* Where a stored watch review differed from what the reviewer says now only
   in the reviewer's name, the app wrote "believed" into the file and the verify command then refused it.
   **Fixed:** the app no longer believes such a review, the file says so, and the file verifies.
5. *Two smaller holes in the same check.* A "not trusted" line was accepted with any result code, and the
   command's own summary line counted runs the app had not believed as reviewed. **Fixed** both.
6. *The entry in Fixes was counted as one of the assessment's findings.* "Open findings with a fix (3)", one more
   open fix on the Overview and in the Projects row, and "Open fixes" as the next step, for a change nobody has
   merged. The plan says such an entry is listed under its own heading and never counted. **Fixed:** the entry
   sits in Encryption tests under **From a developer's change (1)**, with one line that says why, and it is
   counted nowhere. The report lists it the same way. The sentence in LIMITS about which figures move was wrong
   and is corrected (two figures move, both counts of runs: "runs recorded" and the checks of Encryption tests
   that are done).
7. *The panel's card said "Its picked tests would run again" for a change that never ran and cannot run.*
   **Fixed:** for such a change the card says the page's status word alone, with the button off and the page's
   own reason.

What the review confirmed as holding: honestly made files verify at all eleven stages; the verify command reads
the part as data only (1,300 hostile values, none run, none crashed it); the evidence part is complete; the
entry in Fixes follows its rules; the panel sends only the page's own request; the accuracy walk's new part
cannot move an earlier answer.

**What the tightened check still takes as given** is written out in `docs/LIMITS.md`: what only the repository
could show (the byte-for-byte comparison, which tests were picked, the files, the flags), a change's title and
author, the times and the sentences beside a status. Those are covered by the file's signature only. **One thing
to know:** an evidence file made by one of tonight's builds between `2422941` and `36ed916` lacks the new
fingerprint and fails the tightened check. No such file was handed out.

**The walk after the second review's fixes** checks two things more: the entry sits under its own heading, and the page's count, the group's counts and the rows are what they were before the change came in. **1 passed (2.1 min)**, alone, on `3885e19`, with its pictures retaken.

**What is left of 6d:**
1. The long checks on the final commit (see "The exact next action").
2. Small things the plan names for the first half that are **not built**: a watch run's results and flags as
   entries of the panel's Testing thread (only the start is offered there); the Related block of a change; a
   "View in Fixes" line on the failing result's own row on Checks.
**Not in the first half:** the Watch list (its proposals, rechecks and the new pinned checker).

## Step 7: phase 6e, what-if (first half built, tested, documented, walked, reviewed; the review's eight findings fixed)

The plan's shorter first half: **the what-if facts and the try**. Built in three checkpoints, each committed with
its tests. `docs/SPEC.md` section 2 ("What-if in the Otto panel") and `docs/LIMITS.md` ("Limits of phase 6e, first
half") say what is built and what is not.

**What you can do now.** On any page of an assessment, type into the Otto panel: "What if I update elliptic to
6.5.7?" The answer is one card in the Fixing tab, in four parts. No AI model is asked.
1. **What the app knows**: seven kinds of fact, each line with where it comes from and a link: where the library
   is used (your dependency list), what the new version declares it needs against the version you have (the
   publisher's own package file, quoted), which published advisories the update answers and which still name it
   (the installed test packs, with the publisher's line), what the pack's own trial showed on public copies,
   post-quantum support of both versions, the migration track it blocks today, and this assessment's own results.
   Where the app knows nothing on a point, the line says so. Nothing is guessed.
2. **A try on a test copy**: Evidence's own **Retest new version**, pointed at that version, as a card with its
   Confirm step. The card says first what a retest changes. Where the page could not run that retest, the part
   says why and has no button.
3. One sentence: "Live Otto is off. This is what the app knows."
4. **Hypothesis**: what the facts do not show, in the app's own sentences.

**Checkpoint 1 (`c8c7637`): what a version declares it needs.** A new kind of knowledge-base entry (`declared`),
filled for elliptic 6.5.6 and 6.5.7 and python-ecdsa 0.13.2 and 0.13.3: the publisher's own package file, the
lines quoted, the link, the day it was read and the file's fingerprint. Java and OpenSSL read "Doesn't apply".
`backend/app/knowledge/needs.py` compares two lists (added, removed, changed). Data only; nothing runs because of
it. **I read those four entries myself**, from the pinned downloads the app already holds, each first checked
against its pinned fingerprint (decision 26).

**Checkpoint 2 (`61e2efd`): the facts and the sentence that asks.** `backend/app/whatif/facts.py`
(`whatif_view`): the seven groups, the try, the sentence, the hypotheses. It reads and writes nothing. The fixed
rule that reads the question (`_WHAT_IF` in `backend/app/assistant/commands.py`) needs a lead-in ("what if",
"if", "suppose"), one library and one version that starts with a digit; two updates in one sentence get "I can't
do that."

**Checkpoint 3 (`953b109`, then the walk in `36ed916`): the card.** `frontend/src/components/assistant/
WhatIfCard.tsx`. The try's button is the reply's own entry card: the same Confirm step and the same request as
Retest new version on Evidence.

**After that (this commit and the one before):** the documents; the what-if questions for the fifth answer key
(`docs/OTTO-KEY.md`, "What-if on the real libraries file": dependencies added, removed and changed, advisories
answered and still named, the three post-quantum answers for both versions, and in isolated mode whether the try
is offered), with the accuracy walk asking them; and the try on a real library in a real container.

**Test results for 6e:**
- `backend/tests/whatif/`: **73 passed** in the fast set (the knowledge-base entry and its rules with 400 damaged
  copies, the comparison of two lists, every kind of fact on the demo, the honest "not known" lines, the try and
  its reasons, the typed sentence, that asking starts nothing and writes nothing, that the plain values the
  accuracy check reads say what the card's lines say).
- **In real containers** (`backend/tests/whatif/test_whatif_real.py`, slow set): **4 passed (4 min 34 s)**. A file
  that names elliptic 6.5.6: before any test the try is off with the page's reason; after the first run it is
  offered and the what-if shows the failed result on 6.5.6 as the assessment's own; the panel's card carries
  exactly Retest new version's request and asking started nothing; that request sent, the retest runs on the
  public copy of 6.5.7, and the same question then also shows its results (the official cases and the tricks
  pass on 6.5.7).
- Screen tests: `WhatIfCard.test.tsx` and the panel's tests, in the **852** that pass.
- The walk (`e2e/tests/whatif.spec.ts`, port 8035, demo server 8468): **1 passed (1.2 minutes)**. Pictures, dark
  and light: `docs/screenshots/phase6e/` (01 what the app knows, 02 the try off and the hypotheses, 03 the try
  behind Confirm).

**What is not built of 6e (the second half), plainly:**
- A hypothesis is a sentence with nothing to press. **Turn this into a test** and **Add to Change watch** do not
  exist, nor do hypothesis records, the Open hypotheses block, the block "Proposed from your questions" on Checks,
  or the registration of a hypothesis test in Otto's ledger. So success step 14 is met for "what the app knows"
  and "the try", and **not** for "every unproven point has its two buttons".
- Claude's explanation of the facts (part 3). With Live Otto on, the part says it is not part of this version.
- The plan's walk part in isolated mode. The backend test above runs that path instead.

**The separate review** (a fresh reviewer that did not build the what-if, on `581f3da`, after a first attempt on
`2d49dd8` stopped before it reported). It read the facts module, the try and the tests in real containers, ran 8
probe scripts, and checked the four knowledge-base entries against the real files inside the prepared images (the
fingerprints and the quoted lines match). It found **8 things and 3 test gaps; all 8 are fixed, each with a test that
fails on the code before the fix** (14 new test cases, plus the card's screen test):

1. *In demo mode the try was offered for a real library*, once Run all had finished, although such a retest could
   only read "Couldn't run". **Fixed:** the try is off there, with the page's own sentence ("This is real software
   from outside. It runs only in isolated mode (Docker) ...").
2. *A version with a suffix was cut to its upstream number*: asked about acme-sign 1.4.3-otto, the card named and
   offered a retest of 1.4.3, another program. **Fixed:** the card names and offers exactly the version asked about;
   for one of our own demo programs it says which versions Retest new version offers.
3. *"Answers this advisory by the publisher's own statement" could say the opposite of the publisher*: it compared
   with the fixed version only, so OpenJDK 18 read as fixed although the publisher lists 18 as affected, and
   elliptic 1.0.0 read as named although its flaws came later. **Fixed:** that sentence is said only for the exact
   version the publisher names as fixed. For any other version the line quotes the test pack's reading of the
   affected versions and says that whether the version is among them is not worked out (a pack holds them as words).
   The demo's three updates are each that exact version, so their lines still read "answers".
4. *Two updates joined by "then", "or", "&", "/" or "with" were answered for the first one alone*, and "the move to
   2027 plans" was refused as a second update. **Fixed** both ways.
5. *Asked by a package's own name or an everyday name, the card said nothing was known*: "ecdsa" (PyPI's name for
   python-ecdsa) got "No advisory ... is about ecdsa", and "Java" got "The app holds nothing about this library".
   **Fixed:** the library is found by its package names and by the dependency list's package address, and the panel
   reads its own everyday names ("Java" for openjdk). "Python" is not read as python-ecdsa (it is also the language).
6. *A sentence in LIMITS was not true*: a version the dependency list already holds read as the knowledge base's
   answer, not as Dependencies shows it. **Fixed** in the code: that entry's answer is used, and the line says so.
7. *Once Confirm was pressed, the card said the try "is not offered"* beside "Confirmed. ... was sent". **Fixed:** it
   keeps what a retest changes and no longer says that.
8. *The plain values for the accuracy check said the try was offered in a closed assessment.* **Fixed:** the try is
   off there with the closed sentence, in the card and in the plain values alike.

Test gaps: the lines "blocks the ... track" had no test (now they have one, from the reviewer's own probe); a real
library in demo mode after Run all, and an affected range that does not follow the fixed version, are now tested
(findings 1 and 3). **Deferred, with the reason:** (a) the test in real containers sends the card's action to
`start_retest` directly rather than through the browser's request; the screen test checks that Confirm sends exactly
that request, and the route's own tests check where it leads, so each link of the chain is tested; (b) the lines on
what a version declares it needs link the publisher's package file, not a page of the app, because no page of the
app shows declared needs; (c) a "not known" line carries no label, because the line itself says what is not known.

Documents changed with the fixes: `docs/LIMITS.md` (the 6e section, so that every sentence is true again) and
`docs/OTTO-KEY.md` (the question `advisories_still_named` is now `advisories_not_worked_out`). **Not changed, for
Kevin's OK (decision 33):** one phrase of `docs/SPEC.md`.

**What is left of 6e's first half:** nothing but the long checks on the final commit.

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
10. The fast test set. Three shared walks moved to the slow set, as you decided, then the Otto panel's shared walk
    (its 54 readers). With phases 6a to 6e the set had reached seven minutes on the build machine, so I moved more by
    the same rule and with no new package: the 41 readers of the whole demo walk (`demo_flow`, about 49 seconds to
    make; `SLOW_SESSION_WALKS` in `backend/tests/conftest.py`), three Change watch walks, and about twenty tests that
    start a real process and wait on it or make a proof of their own. The scan for private keys keeps a short form in
    the fast set; the accuracy check still grades the whole demo on every push; everything moved still runs with
    `--full` and in the nightly checks. Now: 4 min 59 s with Otto, alone (just under five minutes, at the limit). If you would rather run the tests
    in parallel (pytest-xdist, a developer-only package: your OK needed) and keep them in the fast set, the move is
    undone in `conftest.py` and the markers.
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
21. Phase 6d: in a watch run the speed test is placed by its run on the change alone (that run times the change
    side by side with the code before). "Slowdown found" then counts with the tests that fail now, and the change
    reads "Passed before, fails now"; anything else reads "No slowdown against the code before". The reviewer of
    6d asked for this; the plan did not say. Is that the reading you want, or should a slowdown have a status word
    of its own?
22. Phase 6d: the entry in Fixes for a developer's change. Please read it (the picture
    `docs/screenshots/phase6d/03c-fixes-the-entry-for-the-change-light.png`). Its title is "*the change's title*:
    *N* tests that passed now fail". It says which tests fail on the change and shows the lines the change takes
    out; it does not say those lines are the cause (the app has not tried the change with them put back). It goes
    as soon as the change no longer reads "Passed before, fails now", also when only the test plan changed. Is
    that right, or should it stay until someone runs the picked tests again?
23. Phase 6d: the verify command holds the rule for a watch run a second time, apart from the app's reviewer, so
    that a file is not checked with the code that made it. The two must be changed together; a test compares
    them over every combination. Is that what you want, or should the verify command use the app's own rule?
24. Phase 6d: Otto's accuracy walk now asks about Change watch too, and `docs/OTTO-KEY.md` lists those questions.
    Whoever writes the fifth key should answer them as well.
25. For your information, because it changes how every page reads: since the reads take turns on the server, the
    browser asks a read again (at most twice) when a change was answered while that read was on its way. Without
    it a page could show what was there before your own click (the walks found a test plan with six tests after a
    seventh was added). Nothing that changes anything is ever sent twice.

26. Phase 6e: the four new knowledge-base entries (what elliptic 6.5.6 and 6.5.7 and python-ecdsa 0.13.2 and
    0.13.3 declare they need) were read by the build, on 19 November 2026, from the pinned downloads the app
    already holds, each checked against its pinned fingerprint first. Nobody has compared them with the
    publisher's files by eye. Please have someone do that once (`knowledge/libraries/elliptic.json` and
    `python-ecdsa.json`, the part `declared`; each entry quotes the lines and links the publisher's package).
27. Phase 6e: a hypothesis in the what-if card is a sentence with nothing to press. The brief's success step 14
    ("every unproven point has Turn this into a test and Add to Change watch") belongs to the second half, which
    is not built. The card says so in one line under the heading. Is that line wanted, or should the heading
    stand alone until the buttons exist?
28. Phase 6e: with Live Otto on, part 3 of the card reads "This is what the app knows. An explanation in plain
    sentences is not part of this version yet." (with it off: "Live Otto is off. This is what the app knows.", as
    the plan words it). The first sentence is mine. Is it right?
29. Phase 6e: since the review, "the update answers this advisory by the publisher's own statement" is said only
    for the exact version the publisher names as fixed; for any other version the line quotes the test pack's
    reading of the affected versions and works nothing out. Is that careful enough, or should even the exact
    version only name the fixed version and leave the conclusion to the reader?
30. Phase 6e: "What if ...?" is one line of the fixed list of commands, of the kind that moves nowhere and starts
    nothing (it answers). Typed without a lead-in ("update elliptic to 6.5.7") it is not read, because that
    sentence names no button of the app. Should a bare "update X to Y" be read as the same question?
31. Phase 6d, after its second review: the entry in Fixes for a developer's change is now listed under its own
    heading, "From a developer's change (1)", with the line "A developer's change is not the system until someone
    merges it. A suggestion listed here is not counted with the assessment's findings." Both the heading and the
    line are my wording of the plan's rule. Please read them (the picture
    `docs/screenshots/phase6d/03c-fixes-the-entry-for-the-change-light.png`, retaken).
32. Phase 6d, after its second review: an evidence file made by one of tonight's builds between `2422941` and
    `36ed916` fails the tightened verify check (it lacks a fingerprint the check now needs). No such file was
    handed out, so nothing reads the older form. If you kept a download from a run of your own during the night,
    make a new one.
33. Phase 6e, after its review: `docs/SPEC.md` (section 2, "What-if in the Otto panel", part 1) still says the card
    tells "which the update answers by the publisher's own statement and which still name it". Since the fix it
    says which it answers, and for the others quotes the test pack's reading of the affected versions instead of
    a conclusion. I did not change the SPEC without your OK. The words I propose: "(the installed test packs: which
    the update answers by the publisher's own statement, and for the others the pack's reading of the affected
    versions, with the publisher's quoted line)". Shall I put them in?

## The exact next action

1. *(Done on 19 November 2026: the separate review of phase 6e and its eight fixes, `0503ede`; see "Step 7".)*
2. *(Done on 19 November 2026, on `0503ede`: the full backend set with Otto, every walk once, the accuracy check in
   isolated mode. See "The long checks".)*
3. **Kevin's part, before anything else is built:** read pull request #7 (a draft), make the 30-minute check in a
   fresh Codespace (`docs/CODESPACE-CHECK.md`) and the 15-minute check with the real internet and his own key
   (`docs/LIVE-CHECK.md`), answer the decisions under "Decisions for Kevin" (33 of them), and merge the pull
   request himself if he is content. The session never merges it.
4. Only once Kevin says so: the second halves, each with the CLAUDE.md rule changes the plan lists for it: 6b (free
   wording through Claude), 6c (an answer in free words, with "Hypothesis"), 6d (the Watch list and its pinned
   checker), 6e (hypothesis records, Turn this into a test, Add to Change watch, Claude's explanation). Each: plan,
   build, tests, one walk, pictures, documents, one separate review, fixes, commit, push, this file.
5. Two leftovers of 6b's review (step 4 above, finding 12): eight command lines are never asked against an
   assessment at the stage where their button exists, and most lines have one wording in the tests.
6. Keep pull request #7 a draft until Kevin decides. Never merge it from a session.

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

