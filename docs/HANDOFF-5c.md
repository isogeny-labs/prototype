# Handoff for phase 5c: Otto in Evidence Lab

Written on 18 November 2026, for a fresh session. Read `CLAUDE.md` and `docs/SPEC.md` first; they win over this
page. `docs/HANDOFF.md` has the detail of what is built (its part "Phase 5c: Otto in Evidence Lab").

**In one paragraph.** Phase 5c was built, checked and reviewed against the plan as it stood on 17 November. On
18 November Kevin reviewed the Fixes screen and then set new acceptance criteria for the whole phase (section 2,
his words in full). **Nothing of that new work has been started.** This branch holds the finished first build and
this page. The phase is not done until section 2 is met.

## 0. Where things are

- **This branch:** `wip/5c-otto`. It is the same code as `claude/trusting-goodall-m2i9g6` at commit `4920e5c`, plus
  this page and one line in `docs/ACTIVE.md`. The working folder was clean when the branch was made: there was no
  uncommitted work.
- **The default branch** `mvp/crypto-simple` is at `7acfcd5` (phase 5b with Adam's PR #4). It was not touched.
- **Pull request #6** (`claude/trusting-goodall-m2i9g6` into `mvp/crypto-simple`) was marked ready for review before
  the new criteria arrived. **It should not be merged as "5c done".** First step for the next session: ask Kevin, or
  set it back to draft, and keep the line in `docs/ACTIVE.md` unticked until section 2 is met.
- **Kevin's two docs** (Claude Docs, private to him):
  - the approved plan: "Phase 5c plan: Otto inside Evidence Lab", https://claude.ai/artifact/QGTn7StViH6MpLtcfHCK4n
    (its section "What the build found" has the first build's findings);
  - the report on the first build: "Phase 5c report: Otto in Evidence Lab",
    https://claude.ai/artifact/15rY6GHWCqNtgqLCeFsNaE (results, 12 pictures, what to click in a Codespace). It
    describes the build **before** the new criteria. Update it, don't write a second one.

## 1. The plan, and every change Kevin added since

1. **The plan** (link above), approved on 17 November 2026: all 17 decisions, with three changes of his own.
2. **Change: Claude in Otto.** "Lift 'No AI model' for Otto." Otto uses Claude, with the key read from the
   `ANTHROPIC_API_KEY` environment variable only ("never in code, logs, evidence or screenshots"), to read a newly
   published advisory, design a test for it with a control that must fail, write a fix for our own code, and for a
   library propose the publisher's fixed version with its quoted source. "Every Claude-made test and fix goes
   through the same path as everything else: tried on public copies before it ships, locked (SHA-256) before it
   runs, decided only by the existing runner and reviewer, proven on a copy of the code, and approved and merged by
   a person. Claude never sets a result and never touches a live system. Record every Claude step in Otto's ledger:
   the prompt, the answer, the model, and the hashes." Tests, screenshots and the answer key use recorded answers.
   A "Live Otto" setting uses real Claude when a key is present, with a spending limit per run.
3. **Change: Otto proposes the fix, not only the test.** "Each pack ships a fix with each advisory's test. A fix
   ships only if, on public copies, the advisory check passes after it and every other locked test still passes. On
   screen, the fix says it came from Otto."
4. **Change: the Codespace setting** that asks for read access to `isogeny-labs/otto` (`.devcontainer/`).
5. **"Build on 7acfcd5"** (phase 5b on `mvp/crypto-simple`). Done.
6. **18 November 2026: two changes from his review of Fixes, and the acceptance criteria for the whole phase.**
   This is the new work. His message, word for word:

> Two changes from my review of the Fixes screen (Update elliptic to 6.5.7):
>
> 1. The panel says "proven on public copies" in the title but "Proof: None" below it. A reader sees a
>    contradiction. Split the Proof row into two plain rows:
>    - "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes." (link to the Otto ledger
>      entries)
>    - "Proven on your system: Not yet. Update the library, then press Retest." When a retest on the updated version
>      passes, this row changes to "Passed" with its date and links to the run.
>    Keep "Text only" and the rule that the app offers no code change for other people's code. Use the same two-row
>    wording everywhere a library fix appears (Fixes, Evidence, the report and the signed evidence).
>
> 2. The flow I want: Otto proposes tests, and the user accepts or rejects each one. Check whether Advisories lets a
>    person reject a proposed check with a short reason, kept on the record (nothing deleted). If it doesn't, add
>    it, with the SPEC section 2 wording, and show rejected checks as "Not added (reason)" on Advisories.
>
> Update the screen tests, the end-to-end walk, screenshots, and docs. Then run the full checks and the accuracy
> check in both modes, all keys unchanged, and send me the results.
> This defines what success looks like for phase 5c. Treat it as the acceptance criteria for the whole phase. Where
> something below is already built, keep it and confirm it in the report; where it's missing or different, build
> it. Update docs/SPEC.md section 2 with the wording for anything new (I approve SPEC section 2 changes needed for
> this flow), and the CLAUDE.md product rules where they change.
>
> THE CORE RULE: THE USER IS IN CONTROL AT EVERY STEP
> - Otto proposes; a person decides. Everything Otto produces (a test, a fix, a migration change, a dependency
>   note, a next step) arrives as a proposal labelled "From Otto", with Accept and Reject.
> - Reject asks for an optional short reason. A rejected proposal is never deleted: it stays on the record as "Not
>   added (reason)" and can be reconsidered later.
> - An accepted proposal can be undone until it has run or been applied.
> - Nothing runs, is applied, merged or changed on a system without a person's click, and every accept, reject and
>   undo is recorded in the evidence and in Otto's ledger, with who and when.
> - Results still come only from the runner and the reviewer. Otto never sets a result.
> - A person can switch Live Otto off at any time; the app then works on the recorded snapshot and says so.
>
> THE SUCCESS FLOW, START TO FINISH
> 1. Bring in an inventory: upload a scanner file (CycloneDX/CBOM etc.), or later from our own pqscan. Inventory
>    shows what came in.
> 2. Otto reads the inventory and proposes checks: which published weaknesses (from the installed test packs) apply
>    to which systems and libraries, each with its test, its control that must fail, and why it applies. The user
>    accepts or rejects each one.
> 3. Accepted checks join the test plan on Checks. The user runs them. The runner and reviewer decide each result.
> 4. Otto proposes fixes for anything that fails: a code change for our own code, or a library update for other
>    people's code, each with its two proof rows ("Proven on public copies" and "Proven on your system"). The user
>    accepts or rejects. An accepted code change is proven on a test copy, then a person approves and merges; a
>    library update is done by whoever owns the software, then Retest proves it here.
> 5. Otto proposes what the results mean for the migration plan and dependencies. The user accepts or rejects.
> 6. Evidence records all of it, signed: the proposals, the decisions, the runs, the fixes, the retests, and the
>    Otto ledger entries behind each.
> 7. When a new test pack arrives (new research), Otto proposes the new checks it brings for this inventory, and
>    the loop starts again from step 2.
>
> HOW OTTO SHOWS UP ON EVERY TAB
> - Overview: a "Waiting for you" line counting Otto proposals not yet decided, each linking to where it lives,
>   plus the next step.
> - Project overview: Otto proposals waiting per assessment, and what changed since the last pack.
> - Inventory / Import: after a file comes in, "Otto found N checks that may apply" with a link to Advisories.
>   Nothing runs on import.
> - Verify: unchanged in 5c (its trust gap is phase 5d); no Otto proposals here yet, and say so.
> - Advisories: the home of Otto's test proposals. For each published weakness that fits this inventory: what it is
>   (plain words plus the publisher's quote and link), which systems it fits, Otto's proposed test and how it did
>   on public copies, and Accept / Reject (reason). Shows Proposed, Added, Not added (reason), and results once run.
> - Checks: accepted Otto checks in the test plan, marked "From Otto", with the advisory link. Run, results and
>   retests as today.
> - Evidence: each result from an Otto check shows the advisory, the test design, the trial on public copies, the
>   ledger entries, and the accept/reject decisions with who and when. The signed download includes them.
> - Fixes: Otto's proposed fixes marked "From Otto", with Accept / Reject (reason), the two proof rows, and the
>   existing approve/merge or Retest steps.
> - Migration > Systems and Roadmap: when results change, Otto proposes plan changes (for example "update this
>   library before moving to post-quantum", or a new blocker). Accept updates the plan; Reject keeps it as it was,
>   with the reason.
> - Migration > Dependencies: libraries named by an advisory show it ("Named by advisory X: measured affected / not
>   affected / not yet checked") and link to the proposed fix. Proposals to change a dependency's status are
>   accepted or rejected like everything else.
> - Settings: test packs, Check for updates, Live Otto on/off and its status.
>
> HOW I'LL KNOW IT WORKS
> - One end-to-end walk (e2e) that follows the success flow above on the demo: import, Otto proposes, the user
>   accepts some and rejects one with a reason, runs, a fix is proposed and accepted, proven, merged, retested, the
>   migration plan and a dependency update after accepting Otto's proposal, a new pack arrives and proposes new
>   checks, and the evidence download verifies with every decision in it. Screenshots of every tab at each stage,
>   dark and light.
> - Screen tests for accept, reject with reason, undo, and "nothing runs without a click" on every tab that shows
>   proposals.
> - The four existing answer keys unchanged; the fifth (Otto) key proposal updated to include accept/reject
>   decisions.
> - Full backend suite, frontend checks, all e2e walks, accuracy in both modes, independent review against SPEC and
>   CLAUDE.md. Then commit and push, and send me a short plain-English report: what the user sees on each tab, the
>   walk's screenshots, and the test results.

## 2. What is done and proven (the first build, commit `4920e5c`)

Built, and kept by the new criteria:

- **Adam's Otto harness, pinned** (`backend/otto.lock.json`, commit `aa4a6fd`), fetched by the prepare step, never
  copied into this repository. Without it the app works and says "Otto is not installed on this computer".
- **Otto's research side** (`backend/ottolab/`): reads an advisory, designs a test, tries it on public copies in a
  trial registered in Otto's harness, proposes the publisher's fix and tries that too, then signs a pack.
- **Two signed test packs** in `research/packs/` from six real advisories. Test ready: CVE-2022-21449 (77 cases),
  CVE-2019-14859 (9 cases), CVE-2024-42460 (1 case). "No test yet", each with its reason: CVE-2019-14853,
  CVE-2024-42461, CVE-2024-42459. Fixes: python-ecdsa 0.13.3 proven, elliptic 6.5.7 proven, openjdk 17.0.3 not
  proven (another locked test still fails on 17.0.3).
- **In the app:** Settings (Test packs, Check for updates, Install update, Live Otto with a spending limit);
  the Advisories page with one button, **Add new checks**; advisory checks as ordinary locked tests on Checks; the
  advisory box on results; a library's fix labelled "From Otto"; the Overview's next step; a Related line.
- **Otto's Claude client** (`backend/app/otto/model.py`): recorded answers, live calls with the standard library,
  the spending limit, the key never stored or shown. No test can reach the API (`backend/tests/conftest.py`).
- **Evidence:** the `otto` part inside the signed file, and the verify command's checks of it.
- **The Codespace setting** (`.devcontainer/devcontainer.json`).

Results, all on 17 and 18 November 2026 with Docker running and Otto installed:

| Check | Result |
| --- | --- |
| Backend, full suite | 1748 passed, none skipped, 26 minutes (on `2cf01f9`) |
| Backend fast set, final commit | 1512 passed in 3 min 45 s (238 slow tests left out) |
| Every Otto test (`tests/otto --full`), final commit | 276 passed |
| With Otto absent, final commit | fast set 1444 passed, 68 skipped and counted; accuracy matches all four keys; `--only otto` exits 3 |
| Frontend, final commit | type check clean, 530 passed, build fine |
| End-to-end | 95 passed, none skipped, 21 minutes (on `2cf01f9`); Otto's walk again on the final commit, 3 passed |
| Accuracy, demo mode, final commit | 18/18, 47/47, 1/1 (32 need isolated mode), 186/186 |
| Accuracy, isolated mode | 18/18, 47/47, 33/33 (trial counts 6 of 6 unchanged), 220/220 (on `2394496`) |
| Otto's loop through the buttons' path | 78 answers in demo mode, 124 in isolated mode, no problem; not graded (no fifth key) |
| GitHub's checks on `4920e5c` | all 8 passed |
| The four answer keys and the wireframes | unchanged since `7acfcd5` |

Four independent reviews were run and their findings fixed (list in `docs/HANDOFF.md` and in the report). The one
that matters most: the verify command could be made to start a program an evidence file names. It is closed. The
rule that came out of it is in `CLAUDE.md` (Safety): never call the harness's `audit(reverify=True)` on a ledger
that came from a file.

## 3. What is in progress, and exactly where it stopped

**The second part is being built on this branch (started 18 November 2026).** Kevin answered the five questions of
section 6 that day; his answers are in section 6. Pull request #6 is a draft again. Progress, newest last; a line is
added at every push:

- **Checkpoint 1 (backend core, not yet green).** Built: the second pinned checker for decision entries
  (`backend/app/otto/checker/decisions.py`, beside `recheck.py`, which is unchanged, so older ledgers and evidence
  files read as before); `assurance.py` knows both checkers (`CHECKERS`), `record_decision`, `about_proposal`; the
  append-only table `otto_decisions`; `backend/app/otto/proposals.py` (`ProposalsMixin`: what Otto proposes, worked
  out on every read, for the four kinds check, fix, plan and dependency; `otto_decide` records accept, reject with a
  reason, undo and reconsider in the database and in the assessment's Otto ledger); the routes
  `GET /api/plans/{id}/otto/proposals` and `POST /api/plans/{id}/otto/proposals/{proposal}/{decision}`; the bulk
  **Add new checks** is gone (`add_new_checks` and its route removed); the Advisories view carries each program's
  proposal; a library fix carries its two proof rows (`present/otto.public_copies_row`, `your_system_row`;
  `OttoMixin._proven_here`) and stays listed once a retest on the fixed version has a result; Otto's change is a
  proposal that must be accepted before **Connect demo code** (`fixes/changes.py`); Otto's recorded `acme-sign`
  program is registered as `acme-sign 1.4.3-otto` (`demo/components/acme-sign-1.4.3-otto/`, the harness driver,
  `run/components.py` `CHANGE_VERSIONS`), and a retest may choose it once its change is merged. **The test images
  were rebuilt** (`python -m app.prepare`): a new file under `demo/components/` changes every image's tag.
  A smoke walk in demo mode passes: propose, accept, reject with a reason, undo, reconsider, run, Otto's change
  accepted, connected, proven on `1.4.3-otto`, merged, retested (every signing test passes after).
  **Not done yet at this checkpoint:** `web/models.py` and the generated types; the tests that used
  `add_new_checks`; the frontend; the Fixes view's words for a proposal; Overview, Project overview, Import, Verify
  and Checks lines; Dependencies and Migration; the evidence part and the verify command's check of decisions; docs.
- **Checkpoint 2 (backend whole, screens in, not yet checked as a whole).** Built since checkpoint 1: the screen
  data types for everything above (`web/models.py`, `api-schema.json`, `api.gen.ts`); the words for a proposal
  (`present/otto.py`: `proposal_view`, the two proof rows, `waiting_view`, `project_block`, `found_line`,
  `plan_block`, `roadmap_mark`, `named_line`, `dependency_status`, `result_block`); the Overview's "Waiting for you"
  and next step, the Project overview's "Otto in this project", Import's "Otto found N checks that may apply",
  Verify's one sentence, "From Otto" on Checks and on the plan's cards (an accepted Otto check has no ×: Undo on
  Advisories takes it out until it has run); Migration (a failed advisory check on a signing program proposes
  "Fix *program* before its signatures move to post-quantum" on its Signatures track) and Dependencies (a library
  named by an advisory reads "Named by advisory X: measured affected / measured not affected / not yet checked",
  and where the pack carries an update, Otto proposes it; accepted reads "Update first"); on Evidence, a result of
  an advisory check now carries "Where this check came from" (the advisory, the design's fingerprint, the trial on
  public copies, every decision with who and when, the ledger entries); the evidence file's `otto.proposals` and the
  report's table of decisions; the verify command checks every decision against the ledger
  (`backend/evidence/otto.py`, step 4b); the Otto accuracy walk accepts each check by itself and has new answers for
  decisions. Screens: `frontend/src/components/otto/ProposalCard.tsx` (one card used on Advisories, Fixes,
  Migration and Dependencies) and `ResultOttoBlock.tsx`; Fixes, Evidence, Checks, Overview, Project overview,
  Import, Verify, Migration and Dependencies are done with their screen tests; **Advisories was still being
  finished at this push.** Backend tests: `tests/otto/test_proposals.py` and `test_proposal_rules.py` are new and
  pass; the nine failures the fast set had after checkpoint 1 are fixed (not yet rerun as a whole).
  **Not done yet at this checkpoint:** the whole frontend suite and build; the docs (SPEC 2, 7f, 8 and 12,
  `CLAUDE.md`, LIMITS, HANDOFF, OTTO-KEY, ENGINE, LAYOUT, README); the end-to-end walk (`e2e/tests/otto.spec.ts`
  still presses the old **Add new checks**) and its pictures; the full checks in both modes; the independent
  review.
- **Checkpoint 3 (screens whole, docs written, fast checks green).** Advisories is finished: each proposed check is
  decided by itself in the panel (the shared card), the table has the column "Otto's proposal" and the **Decision**
  filter, and the bulk button is gone. Three things its builder flagged are fixed: a typed reason with one long
  unbroken run stays inside its chip (`ProposalStatusChip`), Escape in the Reject box closes the box and not the
  panel behind it (`layout.tsx`), and one test's missing prop. A line under "Proven on your system" now says what a
  retest runs on (a public copy of the updated version; the app does not connect to the system you run). The Otto
  accuracy walk also adds the demo dependency list and decides two of Otto's proposed updates. A seeded fuzz test
  covers the verify command's reading of proposals and decisions. Docs written: SPEC 2, 3, 7, 7b, 7f (points 6, 7,
  9, 10, 11), 8, 9 and 12 (item 10), `CLAUDE.md` (product rules, safety, tests), `docs/LIMITS.md` (a new section for
  this part), `docs/HANDOFF.md`, `docs/OTTO-KEY.md`, `docs/ENGINE.md`, `docs/LAYOUT.md`, `README.md`.
  **Checked at this checkpoint:** every Otto backend test, slow ones included (`tests/otto --full`, all passed);
  the fast backend set (1575 passed, 242 slow left out, 4 minutes 13 seconds); lint clean; generated files up to
  date; frontend type check clean, 658 tests passed, build fine.
  **Not done yet:** the end-to-end walk (`e2e/tests/otto.spec.ts` still presses the old **Add new checks**) and its
  pictures; the layout walk at 1440 pixels with the new columns; the full backend suite; the accuracy check in both
  modes; the run with Otto absent; the type-check baseline (one old finding whose hint text changed); the
  independent review; the merge and the report.

## 4. The new criteria against the build: what is there, what is missing

Not checked line by line in the code after the message arrived; "to confirm" marks what the next session should
look at first.

| Where | Built today | Missing |
| --- | --- | --- |
| Core rule | Nothing runs without a click. Results only from the runner and reviewer. Live Otto can be switched off and the app says it works on the recorded answers. | A proposal with **Accept** and **Reject** for each thing Otto produces. A reject reason. "Not added (reason)". Reconsider. Undo. Each decision in the evidence and in Otto's ledger with who and when. |
| Advisories | What each advisory is, the publisher's quote and link, which programs it fits, the test, how it did on public copies, results once run, ledger entries. | One bulk button (**Add new checks**) instead of Accept / Reject per proposal. No Proposed / Added / Not added (reason). No "why it applies" sentence (to confirm). |
| Fixes | A library's fix labelled "From Otto", text only, with the publisher's version and quote. | **The two proof rows** (change 1): today the title says "proven on public copies" and the row says "Proof: None". Accept / Reject on a fix. |
| Fixes, our own code | The fix template's change, proven and merged as before. Otto's own change is **not offered** (its program is one line different from the registered 1.4.3). | A code change that is Otto's on the demo: see the open questions in section 6. |
| Checks | Advisory checks in the test plan, titled "Advisory check: name (id)", with the advisory box on the result. | The mark "From Otto" and the advisory link on the card (to confirm what the card shows today). |
| Evidence | The advisory box, the design, the trial, the ledger entries (on the Advisories panel and in the signed file). | The accept / reject decisions with who and when, on screen and in the signed file. The two proof rows for a library fix. |
| Overview | The next step can point to Advisories. | The "Waiting for you" line with a count and links. |
| Project overview | Nothing about Otto. | Proposals waiting per assessment; what changed since the last pack. |
| Import | Nothing about Otto. | "Otto found N checks that may apply", with a link. |
| Verify | Unchanged. | One sentence that says there are no Otto proposals here yet. |
| Migration, Systems and Roadmap | Nothing about Otto. | Otto's plan proposals with Accept / Reject. The largest new piece. |
| Migration, Dependencies | Phase 4d shows published advisories for a library version, as information. | "Named by advisory X: measured affected / not affected / not yet checked", the link to the proposed fix, and status proposals. |
| Settings | Test packs, Check for updates, Live Otto and its status. | Nothing. |
| A new pack | After a second pack, Advisories offers its new check and the Overview points there. | As proposals, like everything else. |
| End-to-end | `e2e/tests/otto.spec.ts`, three parts, 22 pictures in two looks. | One walk of the whole success flow, with every tab at each stage. |
| Fifth key proposal | `docs/OTTO-KEY.md` lists the questions; `backend/app/accuracy_otto.py` walks them. | Questions and the walk for accept, reject and undo. |

## 5. What is left, in order (a suggestion)

1. **Housekeeping.** Pull request #6 back to draft (or Kevin's word on it). Read this page, `CLAUDE.md`, SPEC 2 and
   7f. Start Docker and check the images (section 7).
2. **One record for proposals and decisions.** Append-only, like every other record in the app: what Otto proposed
   (a check, a fix, a plan change, a dependency note), and each accept, reject (with its reason) and undo, with who
   and when. A new entry kind in the assessment's Otto ledger, a new part in the signed evidence, and the verify
   command's check of it. Mind section 8, "the app's own checker".
3. **Advisories:** Accept / Reject (reason) / undo for each proposed check, in place of the bulk button. Proposed,
   Added, Not added (reason).
4. **Change 1, the two proof rows** for a library fix, the same words on Fixes, on Evidence, in the report and in
   the signed evidence. The second row turns to "Passed" with its date and run links after a passing retest.
5. **Fixes:** Otto's fixes as proposals with Accept / Reject (reason).
6. **The small lines:** Overview "Waiting for you", Project overview, Import, Verify, the "From Otto" mark on Checks.
7. **Dependencies:** "Named by advisory X: ..." and its link; status proposals.
8. **Migration:** Otto's plan proposals on Systems and Roadmap. The migration and dependencies answer keys must not
   change, so a proposal can only add to the plan the keys already grade.
9. **Words and rules:** SPEC section 2 (approved for this flow), SPEC 7f, the product rules in `CLAUDE.md`,
   `docs/LIMITS.md`, `docs/HANDOFF.md`, `docs/OTTO-KEY.md` and the Otto accuracy walk.
10. **Tests:** screen tests for accept, reject with a reason, undo and "nothing runs without a click" on every tab
    with proposals; a seeded fuzz test for every new file reader; every table measured at 1440 pixels wide.
11. **The one end-to-end walk** of the success flow, with screenshots of every tab at each stage, dark and light.
12. **The full checks** in both modes, an independent review against SPEC and `CLAUDE.md`, the fixes, commit, push,
    and the short report for Kevin (update the report doc).

## 6. Decisions made without Kevin, and what waits for him

**Made during the first build so that it could go on; each is his to change** (all in the report, "Yours to decide"):

1. Otto's own change for `acme-sign` is not offered: the recorded answer's program is one line different from the
   registered 1.4.3, and only registered demo programs may run. The fix template is offered in its place.
2. The strict reading of "every other locked test still passes", so "update Java to 17.0.3" reads "not proven".
3. A starting spending limit of 2 US dollars per run.
4. The live call uses Python's standard library, not Anthropic's package (which would be a new dependency).
5. Some information-only lines on Advisories and Settings beyond the approved wording (SPEC 2 lists them).
6. The packs were built three times before the merge ("a shipped pack is never rebuilt" was read as "once
   merged"). After a merge they stay as they are.

Smaller ones: one model answers every Claude step; live research is a command, not a button; Live Otto is off by
default even with a key; a trial's baseline is the app's reference library; a design with the same library and the
same cases as another check is refused; six frontend tests were made to wait for their data; the report for Kevin
is a doc of its own; the picture gallery "Evidence Lab Screens" was not updated; pull request #6 was marked ready
for review (before the new criteria).

**Waiting for Kevin:**

- **The fifth answer key** (`demo/expected-otto.json`): who writes it and when. Never written by the build.
- **Questions the new criteria raise.** If there is no answer, take the default named and say so in the report:
  1. *A code change that is Otto's, on the demo.* The walk wants "a fix is proposed and accepted, proven, merged".
     Today the change that can be proven is the fix template's, not Otto's. Either register Otto's recorded program
     as one of our demo programs (his decision 1; it adds a demo component), or the walk accepts the template's
     change with the sentence that says why Otto's is not offered. Default: the second.
  2. *The first proof row when a fix is not proven* (Java). His wording covers "Passed". Suggested: "Proven on
     public copies: Not proven. 17.0.2 fails the advisory check and 17.0.3 passes it, but another locked test still
     fails on 17.0.3."
  3. *Who "who" is.* The app has one login. Default: the name the app already records for approvals and sign-offs.
  4. *Where plan and dependency proposals come from.* `CLAUDE.md` gives Claude four jobs only. Default: rules over
     the results, no fifth job for Claude.
  5. *One button to accept everything.* Default: none; each proposal is decided by itself.
- **For Adam** (unchanged): how his code may be fetched without a secret, so GitHub's checks can run Otto's tests.

## 7. The exact commands

After every machine restart, Docker first (the images, `backend/.venv`, `backend/.otto` and `node_modules` survive
a restart of this build machine; background jobs do not):

```sh
rm -f /var/run/docker.pid /var/run/docker.sock; (nohup dockerd > /tmp/dockerd.log 2>&1 &); until docker info >/dev/null 2>&1; do sleep 2; done
cd backend && .venv/bin/python -m app.prepare --check        # the test images
cd backend && .venv/bin/python -m app.prepare --otto --check # Otto's harness at its pin
```

The checks, one long run at a time (two at once can make the speed test read "Couldn't trust this run"):

```sh
cd backend && .venv/bin/ruff check app tests tools evidence ottolab
cd backend && .venv/bin/python tools/typecheck.py
cd backend && .venv/bin/python tools/api_schema.py --check && (cd ../frontend && npm run gen:api -- --check)
cd backend && .venv/bin/python -m pytest -q tests                  # fast set, under 5 minutes
cd backend && .venv/bin/python -m pytest -q tests --full           # everything, about 26 minutes
cd backend && .venv/bin/python -m pytest -q tests/otto --full      # every Otto test, about 4 minutes
cd backend && EVIDENCE_LAB_OTTO_HOME=$(mktemp -d) .venv/bin/python -m pytest -q tests   # as if Otto were absent
cd frontend && npm run typecheck && npm test && npm run build
cd e2e && npm test -- --trace off                                  # all walks, about 21 minutes
cd e2e && npx playwright test tests/otto.spec.ts --trace off       # Otto's walk alone, about 2 minutes
cd backend && .venv/bin/python -m app.accuracy --mode demo         # four keys, about 2 minutes
cd backend && .venv/bin/python -m app.accuracy --mode isolated     # four keys, about 30 minutes
cd backend && .venv/bin/python -m app.accuracy --only otto --mode demo      # exit 2 until the fifth key exists
cd backend && .venv/bin/python -m app.accuracy --only otto --mode isolated  # about 20 minutes
cd backend && .venv/bin/python -m ottolab.build audit              # Otto's own audit of the research ledger
git diff --stat 7acfcd5 HEAD -- demo/expected.json demo/expected-migration.json demo/expected-real-libraries.json demo/expected-dependencies.json docs/wireframes   # must print nothing
```

After an end-to-end run, commit only the pictures of this phase and restore the others
(`git checkout -- docs/screenshots/<folder>`). GitHub's checks are read on the pull request; they skip the tests
that need Otto and say how many.

## 8. What a fresh session must not get wrong

- **The research scripts are named in the packs by fingerprint:** `backend/ottolab/research.py`, `agent.py`,
  `prompts.py`, `pinned/trial.py`, `pinned/check_model_step.py`. Don't change them: a test fails, and it would need
  a fourth build of the packs. `ottolab/build.py` is not fingerprinted. Never rebuild a shipped pack, never record
  an answer again to get a different one, never edit `research/lab/ledger.jsonl` or `research/lab/runs/`.
- **The new work is on the app's side** (the assessment's own Otto ledger, `backend/app/otto/assurance.py`), so the
  packs need no rebuild for it.
- **The app's own checker** (`backend/app/otto/checker/recheck.py`) is pinned by fingerprint in every assessment's
  ledger, and `assurance.only_our_checker` holds every entry to the exact form the app writes. A new kind of entry
  (a decision) changes both. Keep older ledgers and older evidence files readable: decide how before changing the
  file (for example a second checker file beside the first).
- **A ledger from a file is data.** Never `audit(reverify=True)` on it (`CLAUDE.md`, Safety).
- **Never edit the four answer keys or `docs/wireframes/`.** The fifth key is never written by the build.
- **No test may reach Claude's API,** and no key goes into a file, a log, a command line or a reply.
- **Every new button, screen or setting must be in SPEC section 2.** Kevin approved the changes to section 2 that
  this flow needs; anything beyond the flow is still "ask first".
- **Timing in frontend tests:** to find a test that reads the screen before its data has come, make `mockApi` in
  `frontend/src/test/fixtures.ts` answer a few milliseconds late and run `npm test`. Don't commit the delay.
- **The report for Kevin** is the Claude Doc named above. He is not a developer: plain words, and exactly what to
  click.
