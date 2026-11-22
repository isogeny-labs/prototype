# Plan: Otto writes, proves and proposes its own tests, and a Watch list for weaknesses with no fix yet

**Status: a plan only. Nothing is built, and nothing in the repository was changed except this file.**
Written on 22 November 2026 against `mvp/crypto-simple` at `8dfbd55`. Waiting for Kevin's OK.

Scope, as the brief sets it: a prototype that runs only in Isogeny's own sandbox, behind an on/off switch. No customer system is touched. The answer keys, `docs/wireframes/` and the separate reviewer (`backend/app/engine/reviewer.py`) are not edited by anything in this plan.

How to read it:

- **Part 1** is the short version: what you would get, the one thing to know before you approve, and what I need from you.
- **Part 2** is the groundwork all three capabilities share: the switch, where things run, what leaves the computer, the spending limits.
- **Parts 3, 4 and 5** are the three capabilities, each under the same eight headings the brief asks for.
- **Part 6** takes the three hard points one by one and says what risk is left.
- **Part 7** is the build order. **Part 8** lists the project rules that would get a prototype clause. **Part 9** is the decisions for you. **Part 10** is what is not in the plan. **Part 11** is how it would be shown to work.

Words used here: a **public copy** is one exact published version of a library, fetched from its public package registry. The **asking code** is the small program that puts a test's questions to one library and writes down what the library answered (developers call it a wrapper or an adapter). The **separate reviewer** is `backend/app/engine/reviewer.py`, the only code that decides a result.

---

## Part 1. The short version

### 1.1 What you would get

One line of work with three stations. With the switch on, the looking runs by itself. With its second tick set, the designing and proving does too. The last step is always a person's.

```
   the public source (OSV)                                                        you
          |
          |  looked at by itself, once a day (free: no Claude, no container)
          v
   +---------------------------+     no fix yet      +--------------------------------------+
   | a published weakness in a | ------------------> | 3. WATCH LIST                        |
   | library your files name   |                     |    you are told; it is looked at     |
   +---------------------------+                     |    again every day; history is kept  |
          |                                          +--------------------------------------+
          | it has a fix                                   |  the day a fix is published
          v                                                v
   +-----------------------------------------------------------------------+
   | 2. GET THE PUBLIC COPIES                                              |
   |    the affected version and the fixed version, from the public        |
   |    package registry, fingerprints checked; can a test be made at all? |
   +-----------------------------------------------------------------------+
          |
          v
   +-----------------------------------------------------------------------+      +------------------+
   | 1. WRITE, REGISTER, RUN, REVIEW                                       |      | Accept or Reject |
   |    Otto picks the published cases and writes the asking code;         | ---> | each proposal by |
   |    the test is registered in advance, run in locked containers,       |      | itself, with its |
   |    and every run is decided by the separate reviewer                  |      | proof attached   |
   +-----------------------------------------------------------------------+      +------------------+
        fails on the affected version, passes on the fixed version, and the control fails:
        only then is it proposed. Anything else is listed with its reason and never proposed.
```

- **Watch list (capability 3).** Every published weakness in a library your files name that has **no fix yet** is listed on the Change watch page, so you know about it. The app looks again by itself, keeps the history, and marks the item on the day its publisher names a fixed version.
- **A fix appears (capability 2).** The app gets public copies of an affected version and of the fixed version, checks their fingerprints against the registry's own, and works out by fixed rules whether a test can be made.
- **Otto writes and proves the test (capability 1).** Otto picks the published test cases that show the weakness and writes the asking code for that library. The test is registered in advance in Otto's harness, run in locked containers with no network, and every run is decided by the separate reviewer.
- **You decide.** Only a test that held is proposed, with its proof attached: the runs, the code, the copies, what was registered and when. Accept or Reject, each by itself, as today. Accepting runs nothing.

### 1.2 The one thing to know before you approve: what "its own test" can mean while the reviewer stays untouched

You set two conditions that pull against each other, and the plan has to say how it squares them:

- Otto may write and run its own test code.
- Every proposed test must be confirmed by the separate reviewer, and the reviewer must not change.

A test has three parts: **the questions with their right answers**, **the code that asks** a library those questions, and **the verdict**. I read the reviewer rule by rule (`reviewer.py`, read only). It decides a result in one way: it compares what a program answered with right answers **that it loads itself from pinned files of a publisher**. It never takes a right answer from the test in front of it. For an advisory check it has exactly one rule (`_advisory_cases`, line 652): a selection of the 484 published ECDSA P-256 signature cases of the pinned Wycheproof file. A kind of test it has no rule for ends as "This kind of test has no review rule." (line 398).

That is the property that stops a test from grading its own homework, and it is also the limit. So, with the reviewer unchanged:

| Part of a test | Who supplies it in this plan | Can it be code? |
|---|---|---|
| The questions and their right answers | A publisher, in a pinned file (as today) | No. Data. |
| Which of those questions show this weakness | Otto, as a design note (as today) | No. Data. |
| **The code that asks the library** | **Otto writes it (new)** | **Yes. This is the test code Otto writes and runs.** |
| The verdict on every run | The separate reviewer, unchanged | — |
| Whether the trial held | Otto's harness, against thresholds frozen before the first run (as today) | — |

What this buys: today a test can be proven for two libraries in two pinned versions each. With this plan it can be proven for **any public library we can get a copy of that checks ECDSA P-256 signatures, in whatever versions the advisory names**, because Otto writes the asking code and the app fetches the copies.

What it does not buy: a test whose questions Otto invents, with right answers Otto supplies. The reviewer holds no answers for such a test, so it cannot confirm it. In this plan such a weakness is listed honestly as **"No test yet"**, with the reason, stays on the record, and is counted by kind so you can see what is being missed. Two examples from the shipped pack 2026.11.2, both about elliptic and both with a fix: CVE-2024-42459 is in EdDSA (the app even holds the published Ed25519 cases, but the reviewer has no rule that uses them on a library under test), and CVE-2024-42461 can't be shown by any published P-256 case (`backend/app/real_libraries.py` gives the reason: "The loose length form it allows needs a signature longer than 127 bytes, and a P-256 signature is at most 72."). Both read "No test yet" today, and still would.

If you want more than this later, the way is **one added review rule** ("published cases from any pinned set"), which would open the other published case sets (other curves, EdDSA, RSA signatures and more). That is a change to the reviewer, which you ruled out for this work, so the plan does not make it. It is decision 1 in part 9, and the plan is built so the rule would slot in without rework.

I did not treat your two prototype exceptions as blockers. Both are used: Otto writes and runs code (the asking code, in containers), and public copies beyond the pinned set are fetched and run.

### 1.3 What already exists, and what the plan does with it

| What | Where | The plan |
|---|---|---|
| **Look for new advisories** and **Design and prove tests** on Advisories (phase 6): one public source (OSV), asked by a click; a test proven on public copies before it is proposed | `backend/app/otto/discover.py`, `lookup.py`; `backend/ottolab/` | Builds on it. The same source, the same research command, the same pack and proposal path. |
| The trial registered in advance: a baseline, the affected and the fixed version, a control that must fail, a numeric prediction, a kill line, replay by a second author | `backend/ottolab/research.py` (`propose_test`, line 277), `backend/ottolab/pinned/trial.py`, Otto's harness at its pinned commit | Kept as the backbone. Extended for written code and for more versions (part 3.6). |
| Public copies: only the versions pinned in the app (python-ecdsa 0.13.2 and 0.13.3, elliptic 6.5.6 and 6.5.7, Java 17.0.2 and 17.0.3, OpenSSL 3.5.9) | `backend/app/real_libraries.py`; `research.public_copies` (line 221) | The pinned set stays as it is. A second, separate store of **sandbox copies** is added, used only with the switch on (part 4). |
| "No test yet: the source names no fixed version, so there is nothing to prove a test against." | `backend/app/present/lookup.py` (`NO_FIXED_VERSION`) | Today this line is a dead end. It becomes the entry to the Watch list (part 5). |
| Change watch, the change-driven half: a developer's change, the tests picked for it, **Run the picked tests** | `backend/app/changewatch/`, `frontend/src/components/ChangeWatchScreen.tsx` (phase 6d, first half, merged) | **Not touched.** The brief says no Change watch code exists; this half does, and it stays as it is. The Watch list is a second view on the same page. |
| The design file `docs/design/change-watch.md` | Named in `docs/HANDOFF.md` and `docs/LIMITS.md`; never on any branch | Designed fresh here (part 5), as the brief says. |
| Claude through one client: recorded answers or live, a spending limit per run, every step kept with its prompt, answer, tokens and cost | `backend/app/otto/model.py`, `state.py` | Reused. One job is added (write the asking code) and a limit per day (part 2.4). |
| Locked containers: no network, read-only, no rights, memory and time limits; only the prepare step may download or build | `backend/app/run/runner.py`, `backend/app/prepare.py` | Reused unchanged for every run. Fetching copies is added to the research command, never to the app (part 2.2). |
| Proposals "From Otto" with Accept, Reject with a reason, Undo, Reconsider, recorded in the database, the ledger and the evidence | `backend/app/otto/proposals.py`, `frontend/src/components/otto/ProposalCard.tsx` | Reused. The card gains a proof part (part 3.4). |

### 1.4 What I need from you

Your OK on the plan, and the decisions in part 9. The three that shape the work most:

1. **The reviewer limit (1.2).** Go ahead on "published cases, asked by code Otto writes", with the reviewer untouched? I recommend yes; it is what you asked for.
2. **By itself, or on a click.** With the switch on, looking is free and I propose it runs by itself. Designing and proving costs money (Claude) and I propose it runs by itself only when a second tick is set, within a limit per day.
3. **Which registries first.** I propose npm and PyPI first, then Maven; others later.

---

## Part 2. Shared groundwork: the switch, where things run, what leaves the computer, the limits

### 2.1 The switch

One new switch in Settings, in the Otto block, under Live Otto: **Sandbox research (prototype)**. Off by default.

It can be turned on only when all of these hold; otherwise it is greyed and says which one is missing:

1. The computer is marked as Isogeny's sandbox: an environment variable set when the app starts (proposed name `EVIDENCE_LAB_SANDBOX_RESEARCH`). A customer install never has it, so the switch can't be turned on there. This is the same idea as Live Otto, which can be turned on only when a key is in the environment.
2. Isolated mode is ready (Docker is running and the test images are prepared).
3. Otto's harness is installed at its pinned commit.

Turning it on opens a box first, which says what will happen while it is on, in plain sentences, and nothing starts before the click in that box:

- "The app looks for published weaknesses in the libraries your files name by itself, once a day. This sends each library's name and where it is published, and nothing else."
- "For a weakness with a fix, public copies of the library are fetched from its public package registry and run in locked containers on this computer."
- "Nothing is added to an assessment without your Accept."

Under the switch, one tick and one field:

- **Design and prove tests by itself.** Off by default. It can be ticked only while Live Otto is on. Its line says: "Uses Claude, within the limit per run and the limit per day. A proven test is proposed; you accept or reject it."
- **Most to spend in a day** (US dollars). The limit per run that Live Otto already has stays.

With the switch off the app behaves exactly as it does today. That is checked, not assumed: the four answer keys must match in both modes and the whole fast test set must pass with the switch off (part 11).

Turning the switch off stops the clock, ends a research run that is going, and stops sandbox copies from running. Nothing is deleted: packs, proposals, decisions and records stay.

### 2.2 Where things run

Three places, with a hard line between them. This keeps the rule the project already has ("only the prepare step may pull or build; the app never does") true in spirit: the web app still never downloads, never builds, and never runs anything Otto wrote in its own process.

| Place | What it may do | What it never does |
|---|---|---|
| **The app** (the web process) | Look at the advisory source (as today; now also by the clock). Start the research command as a separate process (as today). Run a prepared container image through the runner (as today). | Download a library. Build an image. Import or run the asking code. Import the research side. |
| **The research command** (`python -m ottolab.build next`, a separate process, as today) | Fetch public copies from the listed registries. Build their images with no network. Ask Claude. Drive the trial through Otto's harness. Sign the pack. | Touch an assessment. Decide a result. |
| **A container** (isolated mode) | Run one public copy with its asking code, for one run. | Reach the network. Write outside its scratch space. See the right answers (they never enter a container: the runner sends only the questions, and the reviewer compares outside). |

Every run of a sandbox copy uses the runner's existing lock-down, unchanged: no network, read-only files, a small scratch space, no rights (user 65534, every capability dropped, no new privileges), 256 MB of memory, 2 processors, 64 processes, no shared memory, no logs kept by Docker, and never a pull (`backend/app/run/runner.py`). Images are built the way real-library images are built today: from a base image pinned by its fingerprint, with `--network none`, from files already fetched and checked (`prepare.build_real`).

### 2.3 What leaves the computer

| To | What is sent | When | New? |
|---|---|---|---|
| The advisory source, `https://api.osv.dev/v1/query` | A package's name and the place it is published (its ecosystem). Never a version, an address, a file or a key. | On a click (today), and by the clock while the switch is on. | The request and the names are today's. New: the clock. (More names only with decision 6.) |
| A public package registry: `registry.npmjs.org`; `pypi.org` and `files.pythonhosted.org`; later `repo1.maven.org` | The name and version of a public package, as part of the address of a public file. | Only by the research command, only for a version an advisory names. | New. |
| Claude's API | The advisory's published text (as today). For the asking code: the rules a piece of asking code must follow, and parts of the **public library's own files** (its read-me and the list of what it offers). The error lines of our own checker when a draft did not work. | Only in a research run, within the limits. | One new job. |

Never sent anywhere: an assessment's file, an address, a key, a result. A version an assessment has is never sent to the advisory source or to Claude. It can reach a registry in one way only: as the version of a public copy that is fetched, when the advisory's own range covers it (in the sandbox the files are our own demo files). The prompt for the asking code names no version at all: the same asking code must work on every version of the library.

### 2.4 Spending limits

- **Per run** (exists): 2 US dollars by default; decision 4 proposes 5 for a sandbox run. Before each call the worst case of that call is checked against what is left (`Budget.check` in `backend/app/otto/model.py`); a call that could go over is not made.
- **Per day** (new): a second limit, checked the same way when a run starts. A run gets the smaller of the two. When the day's limit is reached, the Watch list and Advisories say so: "Today's spending limit is reached. The next run can start after 09:12."
- A limit reached, a refusal, a timeout or no answer is a **stop**, never a result. The advisory stays open and a later run can take it up (as today).
- What a run costs is on its record, step by step (as today).

An estimate, not a measurement: with today's default model and its prices in `model.py` (4 and 20 US dollars per million tokens in and out), one advisory taken all the way would cost roughly half a dollar to two dollars, most of it the two drafts of the asking code. The first live run will show the real figure; the limits hold whatever it is.

### 2.5 Records

Everything new is kept add-only, like the looks and research runs of phase 6: every look by the clock, every copy fetched (where from, when, its fingerprint), every Claude step (prompt, answer, model, tokens, cost), every draft of asking code and why it was refused, every run and its review. All of it goes into the signed evidence, and the verify command checks it (parts 3.3 and 5.3).

### 2.6 Files for the shared groundwork

| File | New or changed | What |
|---|---|---|
| `backend/app/sandbox/__init__.py`, `backend/app/sandbox/state.py` | New | The switch: is this computer marked as the sandbox, is the switch on, the tick, the limit per day, and the plain reason when it can't be turned on. Settings are kept where Live Otto's are (`AppSettingRow`). |
| `backend/app/otto/state.py` | Changed | `otto_view` shows the new block. The limit per day is worked out from the run records. |
| `backend/app/otto/model.py` | Changed | One new job in `STEPS` and `EFFORT` (`write_wrapper`); a limit per day beside `Budget`. The client itself (standard library, no new package) stays. |
| `backend/app/web/otto.py`, `backend/app/web/models.py` | Changed | One route to turn the switch, the tick and the limit; the screen data types. Then `tools/api_schema.py` and `npm run gen:api`, as always. |
| `frontend/src/components/pages/OttoSettings.tsx` | Changed | The block, its box, the greyed states with their reasons. |
| `frontend/src/test/OttoSettings.test.tsx` | Changed | Screen tests: off by default; can't be turned on without each of the three conditions; nothing is sent before the click in the box. |
| `backend/tests/conftest.py` | Changed | The switch is off in every test unless a test turns it on for its own lab. The registries are blocked like the advisory source and Claude's API are today. |
| `backend/tests/sandbox/test_switch.py` | New | The switch's rules; that with it off no new code path is reached (a test that reads the code, like the assistant's read-only test). |
| `docs/SPEC.md` (sections 2, 3, 7f, 9), `CLAUDE.md`, `docs/LIMITS.md`, `docs/LAYOUT.md`, `README.md` | Changed | The new block, the prototype clauses of part 8, the limits said plainly, the map of the code, the environment variable. |

---

## Part 3. Capability 1: Otto writes and proposes its own tests, with proof

### 3.1 How it works today

- **A test is a design note, and a design note is data.** It picks published test cases and gives its reason. The file says so itself: "A design is DATA. It can't carry code" (`backend/app/otto/designs.py`). There is one building block: "run these published signature cases", on the pinned Wycheproof file for ECDSA P-256 (484 cases).
- **The asking code is written by hand, by us, for four library families** and kept in the repository: `demo/real-libraries/elliptic/elliptic_adapter.js`, `python-ecdsa/ecdsa_adapter.py`, `java/EcdsaAdapter.java`, `openssl/openssl_adapter.py`. A library without one can't be tested at all. `docs/ADAPTER.md` gives the rules such code follows (it has no cryptography of its own; it only passes the question to the library).
- **The trial on public copies exists.** Before a test is proposed it is registered in Otto's harness with four parts: the app's reference library as the baseline, the affected version, the fixed version, and a control that accepts everything and must fail. A numeric prediction and a kill line are frozen before the first run; every run goes through the app's own lock, run and review path; a second author replays it (`backend/ottolab/research.py`, `backend/ottolab/pinned/trial.py`).
- **The proposal exists.** A proven test arrives on Advisories as a proposal "From Otto" with Accept and Reject; the trial's counts are shown in the advisory's panel.
- **The research engine socket** (`backend/app/engine/research.py`) is rule-based. Its `review` refuses on purpose (whoever proposes never reviews), and its `dig_deeper` only files a request that waits ("waiting for research engine").

What is missing: Otto can't write code. No library beyond the four families can be asked anything. Nothing guards a proof against the ways written code could bend it. The proof is not shown as one piece with the code and the copies. Nothing comes from the lab's own research: `dig_deeper` waits for an engine that is not there.

### 3.2 The approach

Otto's new job is to **write the asking code**, and the rest of the line is built so that this code can't decide anything.

The steps for one candidate, in order. Steps 1, 3 and 9 exist today; the others are new or extended.

1. **Read the advisory** (Claude, as today): the weakness in plain words, the affected versions and the fixed version, each tied to a line quoted word for word from the publisher. New: the versions Claude read must agree with the version list the source gives in its own fields, which fixed code reads (`lookup.names_version`). Where they disagree, the candidate stops: "No test yet: the publisher's text and the source's version list disagree."
2. **Get the public copies** (part 4): the affected version, the fixed version, and where the advisory names more, up to two further versions on each side.
3. **Design the test** (Claude, as today): pick the published cases that show this weakness, with the reason, or say that no published case fits. The design is frozen in the ledger. No run on the affected copy has happened at this point, and the design step never sees a run.
4. **Write the asking code** (Claude, new), twice, by two authors that never see each other's work:
   - Otto does not write a whole program. We keep a fixed **template** for each language (the part that reads a question and writes an answer, and the build recipe). Otto fills in two or three small functions: load the library, check one signature with the library's own function, say the library's name and version. Typically 10 to 40 lines.
   - What Claude is given: the rules of `docs/ADAPTER.md`, the template, and parts of the library's own public files (its read-me, the list of what it offers), taken from the **fixed** copy and marked as data. No version is named: the same code must work on every version.
   - Each draft is checked by fixed rules before it is used (3.6): a screen of the text, a build with no network, and a known-answer check on the fixed copy with fresh questions the author never saw. A draft that fails gets the checker's error lines back, at most three times. It never gets a trial result back.
   - The second author's draft is written in a separate call with a different fixed brief. It is the answer to a limit Otto's harness states about itself (`docs/harness.md` in Adam's repository, under "Limits"): an instrument that reports the same wrong number every time replays perfectly, and that needs "an independent second implementation or a positive control with a known answer". The plan uses both: the second author's code, and the known-answer check.
5. **Register the trial** in Otto's harness before the first run, with everything frozen by fingerprint: the design, both pieces of asking code, every copy, the images, the trial script, the case file, the prediction, the kill line and the controls (3.6).
6. **Run** each part of the trial once, in locked containers, through the app's own lock, run and review path. **The separate reviewer decides every run.**
7. **Judge**: Otto's harness compares the reviewer's numbers with the frozen thresholds. Nothing is rerun to get a better draw.
8. **Replay** by the second author role, as today.
9. **Try the fix** (as today): the publisher's fixed version must pass the advisory check and every other locked test, read strictly.
10. **Sign and propose.** What held goes into a test pack signed on this computer, and its check is proposed with the proof attached. What did not hold goes into the pack too, with its reason, and is never proposed (as today).
11. **A person accepts or rejects** (as today). Accepting runs nothing. An accepted check is an ordinary locked test in Crypto tests: the runner runs it on a click and the reviewer decides it.

**A candidate from the lab's own research** (the brief's "from the lab's research") is a later step (part 7, step 6). The idea: for a library on the inventory, run the published exam across its public versions; where an answer changes from one version to the next, there is a candidate with a broken side and a fixed side, even with no advisory. The rule that keeps it honest: such a candidate is found on some versions and must be **proven on versions the search never ran**, registered before they are run. Found and proven on the same versions would be a circle.

### 3.3 Files

Research side (the app never imports it):

| File | New or changed | What |
|---|---|---|
| `backend/ottolab/wrappers.py` | New | The write step: asks for the two drafts, runs the checks on each, keeps every draft and every refusal in the ledger. |
| `backend/ottolab/screens.py` | New | The screen of a draft by fixed rules, one set for each language (3.6). |
| `backend/ottolab/prompts.py` | Changed | `write_wrapper_prompt` and the check of its answer, beside the three prompts that are there. |
| `backend/ottolab/pinned/qualify.py` | New, pinned | The known-answer check of a piece of asking code. An instrument check, never a result. |
| `backend/ottolab/pinned/trial_sandbox.py` | New, pinned | The trial script for sandbox copies. The existing `pinned/trial.py` is **not edited**: the two shipped packs and the research ledger name it by fingerprint, and frozen means frozen. |
| `backend/ottolab/research.py` | Changed | `propose_sandbox_test` beside `propose_test` (which stays as it is), with the extended registration. |
| `backend/ottolab/agent.py`, `backend/ottolab/build.py` | Changed | The new step in the loop; `next --sandbox`; the pack in its second format. |
| `demo/sandbox/templates/python/`, `node/`, `java/` | New | Our fixed template and build recipe for each language. |
| `research/recorded/write_wrapper-*.json` | New | Recorded answers for the walk and the tests, labelled "Recorded during the build, not through the API", as the others are. |

App side:

| File | New or changed | What |
|---|---|---|
| `backend/app/otto/packs.py` | Changed | Reads a second pack format, `isogeny.test-pack/2`: the asking code as text with its fingerprints, the record of each copy, the extra parts of the trial. Format 1 reads exactly as before. A format 2 pack is taken only when it is signed by **this computer's own key** and the switch is on (3.7). |
| `backend/app/otto/designs.py` | Changed | `spec_for` for a sandbox copy. The kind stays `advisory_cases` and the inputs stay published case ids, so the reviewer's rule is the same one. The locked test also names the fingerprints of the copy and of the asking code. |
| `backend/app/otto/checks.py`, `backend/app/otto/proposals.py` | Changed | A proposed check for a sandbox library, and its proof for the card. |
| `backend/app/present/advisory.py`, `backend/app/present/otto.py` | Changed | The proof's sentences. |
| `backend/app/engine/research.py` | Changed, small | A library that is a sandbox copy counts as a signing program for the tests its asking code can answer: the Independent exam, Attacker tricks and advisory checks. Speed and size is left out, with its reason (the asking code only checks signatures). The socket (`ResearchEngine`) does not change. |
| `backend/app/engine/guidance.py` | Not changed here | Its one possible addition is in part 5.3, and only with decision 6. |
| `backend/app/engine/reviewer.py` | **Not changed** | A new test fails if the file differs from what it is at `8dfbd55` (`backend/tests/sandbox/test_reviewer_untouched.py`). |
| `backend/app/evidence/export.py`, `backend/evidence/otto.py` | Changed | The evidence part and the verify command for a format 2 pack: the code's fingerprints, each copy's record, both authors' answers equal case by case, and the registration earlier in the ledger than the first run. |
| `frontend/src/components/otto/ProposalCard.tsx` | Changed | A proof part on the card. |
| `frontend/src/components/otto/ProofBlock.tsx`, `AskingCode.tsx` | New | The proof, and the code shown as text. |
| `frontend/src/components/advisories/AdvisoryPanel.tsx`, `AdvisoryTable.tsx`, `parts.tsx` | Changed | The label "Sandbox copy", the new "No test yet" reasons. |

Tests and documents:

| File | New or changed | What |
|---|---|---|
| `backend/tests/sandbox/test_wrappers.py`, `test_screens.py`, `test_qualify.py`, `test_trial_sandbox.py`, `test_pack_v2.py` | New | Each new piece. Seeded fuzz tests for the two new readers (a draft's answer, a format 2 pack). |
| `backend/tests/sandbox/test_drills.py` | New | The cheating drills of part 11: each way to bend a proof, tried on purpose, must be caught. |
| `backend/tests/sandbox/test_sandbox_real.py` | New, slow set | The whole of capability 1 in real containers, on recorded answers. |
| `frontend/src/test/ProofBlock.test.tsx`; the `ProposalCard` tests | New, changed | Accept, reject with a reason, undo, nothing runs without a click, with the proof shown. |
| `e2e/tests/sandbox.spec.ts` | New | The walk (part 11). Pictures in `docs/screenshots/sandbox/`, dark and light. |
| `docs/ADAPTER.md`, `docs/OTTO-KEY.md`, `docs/LIMITS.md` | Changed | Asking code written by Otto; the new questions for the fifth key (questions only, never the key); the limits said plainly. |

### 3.4 What you see on screen

Nothing new to press. The proposal you already know gains one part, **How this test was proven**, folded under the card's summary on Advisories. Opened, it reads like this (letters stand for numbers; this is a sketch of the layout, not a result):

> **Advisory check: *plain name* (*id*)** · From Otto · Sandbox copy
>
> **How this test was proven**
>
> | On public copies | The reviewer's result |
> |---|---|
> | Our reference library | *N* of *N* cases right |
> | *library* *affected version* (the version the advisory names as affected) | **Failed**: *K* of *N* cases wrong |
> | *library* *fixed version* (the publisher's fixed version) | **Passed**: *N* of *N* right |
> | The control, a signer that accepts everything | Failed as it must: wrong on every case that must be refused |
> | More versions the advisory names: *older affected version* / *later fixed version* | **Failed** / **Passed** |
>
> Each line opens its run, with the reviewer's own words.
>
> **Registered before the first run** on *date and time*: the cases, the code, the copies, and what had to happen ("the affected version gets at least one of these cases wrong; the fixed version gets as many right as our reference library; the control gets every must-refuse case wrong").
>
> **The code that asked the library** · Written by Otto · *L* lines · Show
> Two versions were written apart. They gave the same answer on every case.
>
> **The public copies** · *library* *version*, from *registry*, fetched on *date*, fingerprint *…*, the same as the registry's own.
>
> **Replayed** by a second author role of the same build on this computer, not by an outside party.
>
> **What this does not show.** It shows which published cases get a wrong answer. It does not say how serious the weakness is.
>
> [ Accept ]  [ Reject ]

Where no test could be made, the advisory's row says why in one of a short list of fixed sentences, for example:

- "No test yet: the separate reviewer holds published right answers only for ECDSA P-256 signature checks, and this weakness is in EdDSA."
- "No test yet: a public copy of *library* *version* could not be put together (*reason*)."
- "No test yet: the code that asks the library could not be made to work on *library*."
- "Not offered: the two versions of the asking code gave different answers on *n* cases."
- "Not offered: the affected version got every selected case right." (as today)

One information line on Advisories counts what the reviewer limit leaves out, so you can judge decision 1 on facts: "3 weaknesses can't be tested because the reviewer has no rule for their kind: 2 in EdDSA, 1 in RSA signatures."

Wording follows the project's rules: no sentence says what Otto did (the tags "From Otto" and "Written by Otto" stay), no "secure", no score, nothing about how serious a weakness is.

### 3.5 Data sources, and the copies

- **The questions and their right answers:** the pinned Wycheproof file for ECDSA P-256, which the reviewer loads itself and checks by fingerprint (`backend/app/engine/vectors.py`). Not changed.
- **The weakness:** the advisory's published text and its version list, from the source (part 4.5).
- **What the asking code is written from:** the library's own public files, read from the fixed copy that was already fetched. No further request is made for this.
- **The copies:** part 4.

### 3.6 The proof harness in detail

**What is frozen, and when.** The order is what makes the proof worth something, and Otto's ledger is add-only and chained, so the order can be checked afterwards.

| Step | What happens | What is frozen by fingerprint from here on |
|---|---|---|
| 1 | The advisory is read; its versions come from the source's own fields | The advisory record |
| 2 | The copies are fetched and their images built | Every file of every copy; every image |
| 3 | The design is written | The selected cases, the control, the pass rule |
| 4 | Both pieces of asking code are written and checked, on the **fixed** copy only | Both pieces of code |
| 5 | **The trial is registered** | All of the above, the trial script, the case file, the prediction, the kill line, the controls, the budget |
| 6 | The runs. One completed run for each part | Every run and its review |
| 7, 8 | The harness judges; the second author replays | The decision |

A file that changed after step 5 stops the trial: Otto's harness does not run when a pinned file differs. A second design for the same advisory is a new registration that names the first as its parent; there are at most two for an advisory in one run, and every attempt stays on the record and is shown.

**The parts of the trial** (today's four, plus the new ones):

| Part | What runs | What must happen |
|---|---|---|
| reference | Our reference library, on the selected cases | Every case right (the baseline) |
| affected | The affected copy, asked by code A | At least one selected case wrong. Kill line: none wrong. |
| fixed | The fixed copy, asked by code A | As many right as the reference: no difference at all |
| accept-all | The control: a signer that accepts everything | Wrong on every case that must be refused |
| affected-b, fixed-b (new) | The same two copies, asked by code B | The same answer as code A on every single case. Any difference stops the trial. |
| more affected, more fixed (new, where the advisory names more versions) | Up to two further versions on each side | Each further affected version fails; each further fixed version passes |

**Who decides what.** This is the answer to "Otto can't grade its own homework":

| Who | Does | Cannot |
|---|---|---|
| Claude, as Otto's reader, designer and code author | Reads the advisory, picks published cases, writes the asking code. All three are data until checked. | Decide anything. Supply a right answer. See a run before the design and the code are frozen. |
| Our fixed code | Screens and checks the asking code, fetches and builds, runs. | Decide a result. |
| **The separate reviewer, unchanged** | Says right or wrong for every case, from the publisher's answers it loads itself; checks the control and the reference; gives each run its result. | Be told the answer by the test. |
| Otto's harness (Adam's, at its pinned commit) | Checks that the thresholds were frozen first, holds the reviewer's numbers against them, has a second author replay. | Change a threshold after the fact. |
| A person | Accepts or rejects the proposal. | — |

**How the reviewer stays the only authority, point by point:**

1. The asking code never returns "pass" or "fail". It returns one raw answer for one question: accepted, refused, or the library's error.
2. The right answers never enter a container. The runner sends only the questions: for each case its public key, its message and its signature (`backend/app/run/execute/signing.py`). The reviewer compares outside (`_signing` in `reviewer.py`, line 506).
3. The only numbers the harness judges are read from the reviewer's review of each run, by a pinned script of ours that runs outside the container. Nothing Otto wrote can write those numbers.
4. A sandbox check is the kind `advisory_cases`, the kind the reviewer already has a rule for. No new kind is added, so no new rule is needed.
5. The reviewer's own guards still apply to every run: the locked test's fingerprint, the control, the reference library (`review`, line 366).
6. The proposal shows the reviewer's words. The verdict in Otto's ledger is never shown as a result (as today).

**The ways a proof could be bent, and what stops each:**

| What could go wrong | What stops it |
|---|---|
| The asking code is simply wrong (it calls the library the wrong way) | The known-answer check on the fixed copy: fresh signatures made by our reference library must be accepted, and the same ones with one byte of the message changed must be refused. The questions are made from a random seed drawn **after** the code is frozen, so they can't be anticipated. |
| The asking code always says yes, or always says no | The same check. And as a control of the check itself, two dummy pieces of code of ours (always yes, always no) go through it every time and must be refused. If they pass, the check is broken and the run stops. |
| The asking code "knows" which copy is affected and bends its answers | It can't see the right answers. It names no version. The screen refuses code that reads a version, a path, the clock or the environment, or that treats particular inputs specially. And code B, written apart, must agree case by case on every copy. |
| The asking code does the cryptography itself instead of passing the question on | The screen (no arithmetic on large numbers, only the library's own functions), the small size, and code B. The code is shown in the proof for a person to read. |
| The cases were picked because they happen to split the two copies | The design is frozen before anything runs on the affected copy, and must give its reason from the publisher's text. And a wrong answer to a published question is wrong whoever picked the question: the result itself can't be inflated this way, only the link to the advisory, which is why the further versions are in the trial. |
| Something else changed between the two versions, and that is what the test picks up | The further affected and fixed versions. The helper libraries are pinned to the same versions for every copy. The registration lists this as a named confounder. What is left of this risk is said in part 6. |
| The test was tuned until it passed | One run for each part. Drafts of the asking code never touch the affected copy and never see a trial result. A new design is a new registration with the old one as its parent, counted and shown. |
| The control is hollow | The control is ours, not Otto's, and the reviewer requires that it gets every must-refuse case wrong. A design with no must-refuse case is refused before it is tried (as today). |
| The copies are not what they claim to be | Part 4.6. |
| The replay repeats the same mistake | The replay is not the only second look: code B is a second implementation, and the known-answer check has answers nobody had to trust. |
| Claude misreads the advisory | Every claim must quote the publisher word for word (as today), and the versions must agree with the source's own fields (new). |
| Text in the advisory or in the library's read-me tries to give instructions | It is passed as data. Whatever comes back is screened, runs only in a locked container, and decides nothing. |
| Claude declines, or no answer comes | A stop, never a result. The advisory stays open (as today). |

**The screen of a draft, by fixed rules.** One list for each language: only the library under test and a short list of standard helpers may be loaded; no files, network, processes, clock, randomness or environment; no code built from text at run time; no reading of a version or a path outside the one function that reports the library's name; no input compared with a long fixed value; a size limit. For Python the rules are checked on the parsed program. For JavaScript and Java the standard library has no parser, so the rules are checked on the words of the text, which is weaker. The screen is a filter for honest mistakes and plain tricks. It is not a proof. The weight is carried by the locked container, by the fact that the code can't see the answers, and by the second author's code.

### 3.7 Containment

- **The asking code runs only inside a locked container**, on a public copy, for one run. It is never imported or run by the app or by the research command itself.
- **It is built by our recipe, not by its own.** Otto supplies a few functions; the template, the build file and the list of what runs are ours. The image is built with no network.
- **A pack that carries asking code is taken only from this computer.** Today a test pack is data and nothing in it runs. A format 2 pack carries code as text, so it is accepted only when signed by this computer's own key, with the switch on. A format 2 pack from anywhere else is refused with one plain sentence. No outside party can ship code into the app this way.
- **The app runs an image; it does not build one.** The research command builds the images for the copies a proven test needs, including the versions the open assessments name. If an image is missing later, the test reads "Couldn't run" with the plain reason, and the research command or the prepare step makes it again.
- **Costs:** part 2.4. **The switch:** part 2.1.

### 3.8 Edge cases, risks and choices

- **The limit of 1.2 is real.** With the reviewer as it is, a proposable test means ECDSA P-256 signature checks. Many weaknesses will end as "No test yet". The count by kind (3.4) makes this visible.
- **A weakness where a good signature is refused.** The reviewer's control is a signer that accepts everything, and it needs at least one must-refuse case to be wrong on. A design for this kind of weakness adds a few standard must-refuse cases so the control has something to fail on. The proof says plainly that the control shows the run can catch a signer that accepts everything, and that the affected copy itself shows the weakness.
- **The asking code can't be made to work.** A library may read signatures in another form than the published cases use, or change how it is called between versions. That is a stop with its reason, not a result.
- **A library whose own code does not read the published form.** If the library offers no function that reads a signature in the form the cases use, the asking code may not convert it itself (that would be cryptography of its own). "No test yet", with that reason.
- **The further versions disagree with the advisory.** If a version the advisory names as affected gets every case right, the registered prediction did not hold and the test is not offered, with what the trial showed. Strict on purpose; advisories are sometimes wrong at the edges, and you may want to relax this later.
- **The same check under a second name** is still refused (as today): a design that selects exactly the cases of another advisory's check for the same library.
- **A fix that is changed later.** A shipped pack is never rebuilt. If the publisher later names another fixed version, the Watch list marks it (part 5.8) and a later run may register a new test.
- **Two authors, one model.** Both drafts come from Claude. A second model for author B (cheaper, and with different habits) is decision 7.
- **Honest wording about the replay.** The second author is a second role of the same build on the same computer, and the screens say so (as today).
- **Recorded and live.** Tests, walks and pictures use recorded answers only, as today. A prompt with no recorded answer gets "No recorded answer: this needs Live Otto."

---

## Part 4. Capability 2: Otto looks for published weaknesses that have a fix, and proposes proven tests

This is the feed for capability 1: it finds the weakness, gets the two versions as public copies, and says early whether a test can be made.

### 4.1 How it works today

- **Look for new advisories** (Advisories, one click) asks one public source, OSV, once for each library the assessment names that the app's knowledge base knows and the source keeps by name. It sends the package's name and where it is published, nothing else. Whether an advisory names a version you have is worked out on this computer (`backend/app/otto/lookup.py`, `discover.py`).
- **Design and prove tests** (one click) starts the research command as a separate process. It tries an advisory only when the app has **pinned** public copies of an affected and of the fixed version, and only in isolated mode. In practice that is python-ecdsa and elliptic in the two versions each that are pinned in `backend/app/real_libraries.py`. The specification says it plainly: "With today's pinned versions most newly published advisories read 'No test yet'."
- **The copies** are downloaded only by the prepare step, from addresses and with fingerprints written into the code (`backend/app/prepare.py`).
- **The versions for a trial** are picked from the pinned list only (`research.public_copies`: "the newest registered version older than the fixed one").

What is missing: a way to get a public copy of any other version or library. Any looking without a click. An early, free answer to "can a test be made for this one, and if not, why not".

### 4.2 The approach

1. **Looking** stays what it is: the same source, the same request. New: with the switch on, the clock of part 5 also looks, so a weakness with a fix is found without a click.
2. **Sorting, by fixed rules, before any money is spent.** For each advisory found:
   - Does it name a version you have? (as today)
   - Does it name a fixed version? If not, it goes to the Watch list (part 5).
   - Is the record about a package that was published to do harm (the source marks these with ids that start with `MAL-`)? Then no copy is ever fetched, and the row says so.
   - Is the library published on a registry the copy maker can read (npm and PyPI first)? If not: "No test yet", with that reason.
3. **Choosing the versions**, by fixed rules, from the source's own version fields and the registry's own list of releases:
   - *Fixed:* the version the source names as fixed, on the release line your version is on.
   - *Affected:* the last release before the fixed one. It is the closest pair, with the least other change between the two. Your own version too, when it is another one.
   - *Further versions:* up to two more on each side (an older affected one; the release after the fix and the newest one).
4. **The copy maker** (new; part of the research command, never of the app): fetch, check the fingerprint, unpack, write the copy's record, build its image with no network.
   - **Nothing of a package runs while it is fetched or unpacked.** No install script, no set-up program. The files are unpacked as data.
   - **Helper libraries** (what the library needs to run) are picked by fixed rules: the newest version that fits what the library states it needs, as of the day the fixed version was published. **Every copy in one trial gets the same helper versions**, so the library itself is the only thing that differs between them. Where that can't be worked out by fixed rules, the candidate stops with the reason.
   - First: npm packages, and PyPI packages that are plain Python. Then Maven packages that need nothing further.
5. **The asking code.** For a library of the four families we wrote by hand, ours is used. That is build step 3 of part 7: public copies beyond the pinned set, with no code written by Otto at all. For any other library, capability 1 writes it.
6. **The research run, the pack and the proposals** are today's.

### 4.3 Files

| File | New or changed | What |
|---|---|---|
| `backend/app/sandbox/copies.py` | New | The store of sandbox copies, in the data folder. One folder for each copy, named by its fingerprint, with its record: name, version, registry, the addresses read, when, the SHA-256 of every file, the registry's own fingerprint value, the helper libraries, the image. The record is read strictly, as data. An add-only index. |
| `backend/app/sandbox/registries.py` | New | One reader for each registry's documented answer, held to its shape. A folder of recorded answers can stand in (`EVIDENCE_LAB_REGISTRY_SOURCE`), as one does for the advisory source. |
| `backend/app/sandbox/versions.py` | New | The order of versions and "does this version fit this range", for npm and PyPI, by fixed rules. Picks the versions of a trial. |
| `backend/app/sandbox/fetch.py` | New | The downloads: listed hosts only, a size limit, the fingerprint checks of 4.6. |
| `backend/app/sandbox/images.py` | New | Unpacks a copy and builds its image from a pinned base image with no network. Reuses `prepare.build_real`. |
| `backend/app/prepare.py` | Changed | `--sandbox`: reports what the store holds and makes a missing image again from the store. Shares its download code. |
| `backend/app/run/components.py`, `backend/app/run/runner.py` | Changed | With the switch on, a sandbox copy can be what a test runs: name and exact version to image, with the label "Sandbox copy". The lock-down of a container is not touched. |
| `backend/app/real_libraries.py` | Not changed | The pinned set stays the pinned set. Nothing here adds to it. |
| `backend/app/otto/discover.py` | Changed | The sorting of 4.2; an advisory can be tried with the switch on where a copy can be made; the research command is started with `--sandbox`; the run's record says so. |
| `backend/app/otto/lookup.py` | Changed, small | Keeps which records the source marks as withdrawn, and each record's own "last changed" time (both needed by part 5). The request does not change. |
| `backend/app/present/lookup.py` | Changed | The new states and reasons, as fixed sentences. |
| `backend/ottolab/research.py`, `backend/ottolab/build.py` | Changed | The copies for a trial: the pinned ones first, sandbox copies with `--sandbox`. The fetch step of a run. |
| `backend/tools/research_demo.py` | Changed | Also prepares a folder of recorded registry answers, so the whole line can be seen with no internet. |
| `knowledge/libraries/*.json` | Changed (data) | One entry for each library a walk uses beyond today's six. |
| `frontend/src/components/advisories/NewAdvisories.tsx`, `AdvisoryTable.tsx`, `AdvisoryPanel.tsx` | Changed | The states, the box of **Design and prove tests** (what will be fetched), the label "Sandbox copy". |
| `backend/tests/sandbox/test_copies.py`, `test_registries.py`, `test_versions.py`, `test_fetch.py`, `test_triage.py` | New | Each piece; seeded fuzz tests for the three new readers (a registry's answer, a copy's record, a version range). The download tests use a stand-in server on this computer: a wrong host, a wrong fingerprint, a file that is too large and a file that changed are each refused. |
| `backend/tests/sandbox/test_copies_real.py` | New, slow set | A copy made, built and run in a real container, from recorded registry answers. |

### 4.4 What you see on screen

On Advisories, in the block that lists what a look found. No new button.

- A row that reads "No test yet" today because the app has no pinned copy can now read: "A test can be tried on public copies: *library* *affected version* and *fixed version*, from npm."
- The box that **Design and prove tests** already opens also lists, before the click, what will be fetched: each library, version and registry, and that it runs only in locked containers on this computer.
- A result that came from a sandbox copy carries the label **Sandbox copy** wherever it shows (Advisories, Checks, Evidence, the report), so it is never mistaken for one of the pinned libraries.
- With the tick "Design and prove tests by itself" set, the block's first line says what happened without you: "Looked today at 09:12, by itself. 1 research run today. 0.84 of 10.00 US dollars spent today." (example figures)

### 4.5 Data sources, and how the public copies are obtained

**Where weaknesses come from.** One source, OSV, as today. Its records give what this plan needs: the ids a weakness is known under, the packages it affects, and for each package the version ranges (first affected, fixed, last affected), the text, the dates, and whether the record was withdrawn. No rating of how serious a weakness is read from it (as today).

Why one source: it already gathers GitHub's advisory database and the registries' own. A second source means more requests and more shapes to hold to. Where one would plug in later: `lookup.py` already has the place (the recorded source stands in for the live one there). Libraries the source does not keep by name (OpenSSL, OpenJDK, BoringSSL) stay on the dated snapshot the shipped packs use.

**Where "known broken" and "known fixed" come from.** From the publisher's own statement, as the source gives it in its version fields, read by fixed code. Not from Claude, and not from a guess of ours. Claude's reading of the text must agree with it (3.2, step 1).

**Where the copies come from.**

| Registry | What is read | The registry's own fingerprint |
|---|---|---|
| npm (`registry.npmjs.org`) | The package's document (its releases, their dates, what each needs) and the release's `.tgz` file | A SHA-512 value in the package's document |
| PyPI (`pypi.org`, `files.pythonhosted.org`) | The release's document and its file (a plain-Python wheel, or the source package) | A SHA-256 value in the release's document |
| Maven Central (`repo1.maven.org`), later | The release's `.jar` and its description file | The checksum files beside the `.jar` |

Nothing that is fetched is put into the repository or into a pack. A pack holds a copy's fingerprints and where it came from, not the copy.

### 4.6 The proof harness: that a copy is what it claims to be

The trial itself is part 3.6. What capability 2 adds is the proof of the copies, because a trial on the wrong files proves nothing.

1. **Exact version, by fixed rules.** The versions come from the source's fields and the registry's list. Never from Claude's wording.
2. **Two fingerprints must agree.** The bytes that were downloaded are hashed here and compared with the registry's own value for that file. A difference refuses the copy.
3. **Trust on first use, and never replaced.** The first fetch of a name and version writes its fingerprints into the add-only index. A later fetch that differs is refused: "This version's file is not the one fetched on *date*." The honest limit: the first fetch trusts the registry.
4. **The same helper libraries for every copy of a trial** (4.2), all fingerprinted.
5. **Nothing of the package ran before the trial.**
6. **The copies are part of the registration.** Their fingerprints are frozen with the trial (3.6), and the runner refuses to run a copy whose image no longer matches its record.
7. **The fix** keeps its two proof rows, in today's words: "Proven on public copies" (the pack's trial) and "Proven on your system" (the assessment's own retest).

### 4.7 Containment

- Only the research command fetches, only from the listed hosts, and only a version an advisory names.
- Limits on size: for one file, for one copy with its helper libraries, and for the whole store. Past a limit is a stop with its reason.
- A fetched package is data until it runs, and it runs only inside a locked container with no network (part 2.2).
- A record about a harmful package is never fetched.
- An affected version is, by definition, software with a known weakness. It is never run anywhere but in a locked container, and never against anything but our own test questions.
- A plain limit, said in `docs/LIMITS.md`: a container is not a separate machine. The lock-down is strong, and it shares the computer's core with everything else. That is acceptable for a prototype in our own sandbox and is one more reason this stays off customer installs.
- Cleaning: a prepare command removes copies that no pack and no open trial names. A copy a proof names can always be fetched again and checked against its fingerprint.

### 4.8 Edge cases, risks and choices

- **The version is gone from the registry.** A stop with its reason: "the affected version is no longer published."
- **The file changed at the registry** since it was first fetched. Refused (4.6).
- **A package with compiled parts.** Left out at first: plain-Python and plain-JavaScript packages only. "No test yet", with that reason.
- **A package that only passes work on to another library** (many do, to OpenSSL). The weakness then lives in the other library. Left out at first, with that reason.
- **Several release lines with a fix each** (say 1.x and 2.x). The pair on your version's line is tried; the other line is among the further versions.
- **The source names a last affected version and no fixed one.** The fixed side is then the next release after it, taken from the registry's list, and the proof says so in those words.
- **A fixed version that is a pre-release.** Treated like any version: it is what the publisher named.
- **Helper libraries that can't be pinned by fixed rules,** or too many of them. A stop.
- **The registry does not answer.** "Couldn't fetch", a stop. Never "no copy exists".
- **Choice: our own code for versions and ranges** (a few hundred lines for each registry, with fuzz tests) and no new package. The other way is each registry's own tool run in a container with network, which is closer to what a user installs and is a bigger hole in the lock-down. I recommend our own code first, and a stop where it can't decide.

---

## Part 5. Capability 3: the Watch list — weaknesses with no fix yet, kept up to date by itself

This is the world-driven half of Change watch: something changed in the world, not in your code. The change-driven half (a developer's change comes in and tests are run again) exists and is out of scope; nothing here touches it.

### 5.1 How it works today

- When a look finds a weakness with no fixed version, its row on Advisories reads: "No test yet: the source names no fixed version, so there is nothing to prove a test against." (`NO_FIXED_VERSION` in `backend/app/present/lookup.py`). The code already recognises the case: a version range with a start and no end named reads as "affected, no fixed version" (`lookup.names_version`).
- And that is all. It is not kept as a list of its own. It is looked at again only if someone clicks **Look for new advisories** again. Nobody is told when a fix appears. Each look is kept (the `otto_lookups` table), but nothing compares one look with the next.
- The page called Change watch shows developers' changes only. The specification lists "the Watch list" as not built, and the design file it names was never written.
- The app has no clock. The specification says so: "there is no timer" (section 7f, point 9).

### 5.2 The approach

**A watch item** is one published weakness in one package. The list is kept once for the installation, because what the world knows is the same for every assessment. Each assessment's page shows the items that are about the libraries its own files name, and whether an item names the version it has is worked out each time the page is read, never stored (the same way proposals are).

**Where an item stands** is worked out from its history, and the history only ever grows:

| Status | Means | How it gets there |
|---|---|---|
| **No fix yet** | The publisher has named no fixed version. | A look found it so. |
| **Fix published** | The source now names a fixed version. | A later look found a fixed version where there was none. The item is marked, with the version and the day it was first seen here. |
| **Being tested** | A research run has taken it up (capabilities 2 and 1). | The run started. |
| **Test proposed** | A proven test is in a pack and waits for your decision on Advisories. | The run ended with a proven test. |
| **No test possible** | A test could not be made, with the reason. | The run ended with "No test yet" or "Not offered". |
| **Withdrawn by its publisher** | The source marks the record as withdrawn. | A look found it so. The item is kept. |
| **No longer names your version** | The record was changed and your version is now outside it. | Worked out for the assessment on each read. |

A run that could not settle an item (no answer came, a limit was reached, a trial did not finish) leaves it at **Fix published**, with a line that says what stopped. A stop is never a result, and a later run takes it up.

**The clock** (new, and only while the switch is on). Once a day, and once shortly after the app starts if the last look is older than a day, the app asks the source again about every watched library. It is the same request a click makes today, and it costs nothing: no Claude, no container. One look at a time. If the source does not answer, the app waits longer before each further try, and the page says "Couldn't look", never "nothing found". **Look now** does the same on a click.

**How a published fix is detected.** This is the mechanism the brief asks about, so precisely:

1. Each look's answer is reduced, for each item, to the plain facts that matter: for each package, each version range with its start, its fixed version and its last affected version; and whether the record is withdrawn.
2. Those facts are compared with the facts of the look before. The record's own "last changed" time is only a hint; the comparison of the facts decides, because sources sometimes touch a record without changing it.
3. **"Fix published" means exactly one thing: the source now names a fixed version (or a last affected version) for that package where it named none.** It is the publisher's statement, shown with its date, never our inference.
4. A newer release of the library that the source says nothing about is **not** a fix. (Asking the registries about new releases during a look is left out of the first build; it would be a hint only, and it is listed in part 10.)
5. Any other change is recorded as what it is: the fixed version changed, the range changed, the record was withdrawn, the record came back.

**The hand-over to capability 2.** An item that reads **Fix published** and names a version an open assessment has is ready for a research run.

- With the tick "Design and prove tests by itself" set, Live Otto on and money left in the day's limit, the app starts the research run by itself, the oldest item first, one run at a time. It is the same research command a click starts today.
- Otherwise the item waits, marked, and **Design and prove tests** on Advisories takes it on a click.

Either way nothing is skipped: the fix having been published proves nothing about a test. The test still has to be written, registered, run and reviewed, and you still decide.

**What a person can do on an item:** **Stop watching**, with an optional short reason, and **Watch again**. Both are recorded with the name and the time, and a stopped item is never deleted. There is no Accept on an item: watching runs nothing, changes nothing and costs nothing, and the point is that you are told. An item carries the tag **New** until its panel has been opened (the tag the app already uses).

### 5.3 Files

| File | New or changed | What |
|---|---|---|
| `backend/app/db.py` | Changed | Three add-only tables. `watchlist_items`: one row for a weakness in a package (its ids, the package, when it was first seen here). `watchlist_events`: an item's history (what changed, in which look, the facts as read, the fingerprint of the record's bytes; or a person's stop or watch again, with the name and the reason). `watchlist_looks`: every look, by the clock or by a click (when, by whom, the names sent, what came back, or that the source did not answer). |
| `backend/app/changewatch/watchlist.py` | New | The rules: what a look's answer means for each item, where an item stands given its history, which items are ready for a research run. No network and no Claude in this file. |
| `backend/app/changewatch/clock.py` | New | The clock: when a look is due, one at a time, the longer waits after a failure, off with the switch. It only starts a look, or a research run where the tick allows it. |
| `backend/app/changewatch/watchlist_views.py` | New | What the page draws. The existing `views.py` and `state.py` of the Changes view are not edited. |
| `backend/app/present/watchlist.py` | New | The status words and sentences. |
| `backend/app/web/changewatch.py`, `backend/app/web/models.py` | Changed | Routes for the list, **Look now**, **Stop watching** and **Watch again**; the screen data types. |
| `backend/app/otto/discover.py` | Changed | A look made by a click feeds the list too. A finished research run writes where its items now stand. |
| `backend/app/main.py` | Changed | Starts and stops the clock with the app. |
| `backend/app/evidence/export.py`; `backend/evidence/watchlist.py` (new) | Changed, new | The Watch list's part of the signed evidence, and its check in the verify command: every item's history in order, every event's look in the file, the status word the one its history gives, every hand-over pointing to a research run that is in the file. |
| `backend/app/engine/guidance.py` | Changed only with decision 6 | A fixed list, with its sources, of the kinds of weakness that count as "about cryptography", kept as a config value the way `OLD_CRYPTOGRAPHY` is. |
| `frontend/src/components/ChangeWatchScreen.tsx` | Changed | Two views on the page: **Changes** (as today) and **Watch list**. |
| `frontend/src/components/changewatch/WatchListTable.tsx`, `WatchItemPanel.tsx` | New | The table and its side panel. |
| `frontend/src/components/pages/OverviewPage.tsx` | Changed | One line with a count that opens the Watch list. |
| `backend/tests/watchlist/test_rules.py`, `test_clock.py`, `test_views.py`, `test_evidence.py`, `test_reads_only.py` | New | Every change of status. The clock on a stand-in time: one look at a time, the waits, off with the switch, and that it never asks Claude and never starts a container without the tick. That reading the page writes nothing. |
| `frontend/src/test/WatchList.test.tsx` | New | Stop watching with a reason, watch again, the New tag, nothing sent on opening the page. The table measured at 1440 pixels wide, panel open and closed. |
| `e2e/tests/watchlist.spec.ts`; `e2e/tests/layout.spec.ts` | New, changed | The walk (part 11), on recorded answers; the new table in the layout walk. Pictures in `docs/screenshots/watchlist/`. |

The Otto panel is not changed in this plan. A test confirms it still only reads.

### 5.4 What you see on screen

The **Change watch** page gets two views, chosen at its top: **Changes** (what the page shows today) and **Watch list**.

The Watch list opens with one line that says where things stand, and one button:

> Published weaknesses in the libraries your files name that have no fix yet. Looked today at 09:12, by itself. Next look tomorrow at about 09:12.  [ Look now ]

Then a table. A sketch (names and numbers are placeholders):

| Weakness | Library | Status | Since |
|---|---|---|---|
| **New** · *plain name* (*id*) | *library* *your version* · names your version | No fix yet · no fix published for 212 days | first seen here on 3 Nov 2026 |
| *plain name* (*id*) | *library* *your version* | **Fix published** in *version*, seen here on 21 Nov 2026 · a test can now be designed and proven | first seen here on 2 Oct 2026 |
| *plain name* (*id*) | *library* *your version* | Test proposed · On Advisories | first seen here on 14 Sep 2026 |
| *plain name* (*id*) | *library* *your version* | No test possible: the separate reviewer has no rule for this kind of check | first seen here on 14 Sep 2026 |

A row opens a side panel:

- **What the publisher says**, quoted, with its source, its publisher and the day it was read (drawn as Advisories draws a quote today).
- **The versions it names**, and the line "Your version *x* is named." or "Your version *x* is not named."
- **History**, oldest first: "First seen here on 2 October 2026, with no fixed version." · "Looked at 49 times since; nothing changed." · "21 November 2026: the source names a fixed version, *version*." · "21 November 2026: a research run took it up." · "22 November 2026: a proven test is proposed. On Advisories."
- **Stop watching** (asks for an optional reason), or **Watch again**.

Elsewhere:

- The Overview gets one line: "2 published weaknesses in your libraries have no fix yet." It opens the Watch list.
- On Advisories, the row that reads "No test yet: the source names no fixed version…" gains a link, "On the Watch list".
- A closed assessment shows the list as it stood when it was signed off, and says so. An archived assessment is not watched.

The wording rules hold here too: an item says how long there has been no fix, and never how serious the weakness is.

### 5.5 Data sources

- **The same source and the same request as today.** The package's name and where it is published. Never a version.
- **Which libraries are watched:** as today's looks, the libraries your files name that the app's knowledge base knows and the source keeps by name. Widening this to every row of a dependency list would send more names, and would need a rule for which weaknesses are about cryptography so that the list does not turn into a general scanner. That is decision 6, and it is not in the first build.
- **How "no fix yet" is read:** a version range with a start and no fixed and no last affected version (already in `lookup.names_version`).
- **No registry is asked by a look.** Registries are asked only when copies are made (part 4).

### 5.6 The proof harness: what has to be right when nothing is tested

The Watch list proposes no test and words no result, so there is no trial to register. What has to be right is the record: what the source said, and when we saw it.

1. **Every look is kept**, with the names sent, the time, and the fingerprint of what the source answered. A look that got no answer is kept as that.
2. **An item's status is worked out from its history by fixed rules.** Nothing sets a status directly, and the history is add-only.
3. **"Fix published" is the publisher's statement,** as the source gives it, shown with its date. It is never worded as a result, and it never says the fix works.
4. **The hand-over enters capabilities 2 and 1 at the start.** Nothing is skipped because a fix exists.
5. **The verify command checks the part** (5.3): the history's order, each event's look, the status word, each hand-over's research run.
6. **A person's stop and watch again** are recorded like decisions: who, when, the reason.

### 5.7 Containment

- **The clock runs only while the switch is on**, and stops with it.
- **By itself, the clock only looks.** It starts a research run only where the second tick is set, Live Otto is on and the day's limit has money left. It never accepts, runs a check, applies or merges anything.
- **One look at a time, at most about once a day**, with longer waits after a failure, so the source is not hammered.
- **No test reaches the source.** Tests and walks use recorded answers and a stand-in clock, as the advisory tests do today (`backend/tests/conftest.py`).
- **The app must be running for the clock to run.** After a week switched off it looks once at the start, and the history says there was a gap.

### 5.8 Edge cases, risks and choices

- **The record is withdrawn.** Kept, marked, and any hand-over is stopped.
- **The record is edited.** A changed range or a changed fixed version is recorded as that. If a test was already proven against the earlier fixed version, the item says so and a later run may register a new test; a shipped pack is never rebuilt.
- **One weakness, several ids.** A weakness is often listed under more than one id (a CVE and a GitHub id). Items are merged by the ids a record says it shares, with the rule the looks already use.
- **A fix that never comes** (an abandoned library, or a publisher who will not fix it). The item stays at "No fix yet" and says for how long. The app does not guess why.
- **The fix is another package** (the publisher says to move to a renamed library). No fixed version is named for this package, so it stays "No fix yet", with the publisher's line quoted.
- **The version can't be read.** The item says so and guesses nothing (as the looks do today).
- **Two assessments, one library.** One item, shown in both.
- **Many items.** The table gets a filter by status.
- **The source is down.** "Couldn't look", with the time of the last look that worked.
- **A name clash to settle.** The specification already uses "Watch list" for an idea from the earlier plan: items that say which tests to run again when code changes. That idea is the change-driven half and stays out of scope. I propose the new view takes the name **Watch list**, and the earlier idea is renamed when its time comes. The other candidate name is **No fix yet**. Decision 9.
- **A rule this changes.** Today nothing in the app happens by itself. With the switch on, a look does. Part 8 has the exact clauses.

---

## Part 6. The three hard points: the answer in short, and the risk that is left

### 6.1 Independence of the proof for a test Otto derived itself

**The answer in short.** Otto supplies neither a right answer nor a verdict. The questions and their right answers are a publisher's, in a pinned file the reviewer loads itself. Otto picks which questions and writes the code that asks them. Everything is frozen in Otto's harness before the first run. Each run is decided by the unchanged reviewer; the harness holds the reviewer's numbers against thresholds frozen in advance; the code is checked against answers nobody had to trust, and against a second version written apart. Part 3.6 has the detail and the table of what stops each way of bending a proof.

**What is left, said plainly:**

1. **The scope.** Only what the reviewer holds published answers for can be proposed (1.2).
2. **The link to the advisory.** That a version gets published case *n* wrong is a fact the reviewer establishes. That case *n* is *this advisory's* weakness rests on Otto's reading, on the publisher's quoted line and on the further versions behaving as the advisory says. The proposal words it that way and no stronger.
3. **Two versions differ in more than the fix.** The further versions and the equal helper libraries narrow this; they do not close it. A stronger design exists: the fixed version with only the fix taken out again, as a third copy. It needs the publisher's exact change and a way to apply it, so it is listed as a later step (part 7), not promised here.
4. **Both authors of the asking code are Claude,** and the replay is a second role on the same computer. The known-answer check does not depend on either. An outside replay would be stronger and is not in this plan.
5. **The screen of the code is weaker for JavaScript and Java** than for Python (3.6). The container, the unseen answers and the second author's code carry the weight there.

### 6.2 Getting a known-broken and a known-fixed public copy

**The answer in short.** Which version is broken and which is fixed is the publisher's statement, read by fixed code from the source's own fields. The copies come from the library's public registry, by exact version. Their bytes are checked against the registry's own fingerprint, recorded on first use and never replaced. Every copy of one trial runs with the same helper libraries. Nothing of a package runs before the trial, and then only in a locked container. Part 4 has the detail.

**What is left:**

1. **The first fetch trusts the registry.** A registry that served a wrong file the first time would not be noticed here.
2. **Coverage at first.** Plain-JavaScript and plain-Python packages whose helper libraries can be pinned by fixed rules. Packages with compiled parts, and other registries, come later or read "No test yet".
3. **Registries change.** A version can be removed. That is a stop with its reason.
4. **A container is not a separate machine** (4.7).

### 6.3 The data model for "known, no fix yet", and noticing the fix

**The answer in short.** One item for a weakness in a package, with a history that only grows. Where it stands is worked out from the history by fixed rules. Each look's answer is reduced to plain facts and compared with the look before; "Fix published" means only that the source now names a fixed version where it named none. The item is then marked and handed to capability 2, by itself where the tick allows it and otherwise on a click. Part 5 has the detail.

**What is left:**

1. **The list knows what the source knows.** A fix can be released some days before the source's record says so. In that gap the list still reads "No fix yet". It says what the source says and when it last looked, and no more.
2. **The clock runs only while the app runs.**
3. **One source.** A weakness the source does not list is not on the list.

---

## Part 7. Build order

Six steps. Each is small enough to review by itself, leaves the app working, and can be stopped after. Each runs the way `CLAUDE.md` says a phase runs: the detailed plan for your OK, the build, a separate reviewer against the specification, then test output, pictures and the accuracy result for you, and a commit after your OK.

The order follows risk, not the numbering of the capabilities: first what is cheap and can't hurt (being told), then the copies, and the code Otto writes last.

| Step | What is built | What you can see at the end | Size |
|---|---|---|---|
| **0. Groundwork** | The tracking line and the draft pull request the project's rules ask for. The prototype clauses of part 8 in `docs/SPEC.md` and `CLAUDE.md`. The switch, with nothing behind it yet. | The new block in Settings, greyed or on, with its reasons. With the switch off, everything as today. | Small |
| **1. The Watch list, looked at on a click** (capability 3, first half) | The three tables, the rules, the view on Change watch, **Look now**, **Stop watching**, the Overview line, the evidence part and its check. No clock. | Weaknesses with no fix yet, listed, with their history. | Medium |
| **2. The clock** (capability 3, second half) | Looks by itself; "Fix published"; the hand-over on a click. | An item turning to "Fix published" by itself, on recorded answers. | Small to medium |
| **3. Public copies beyond the pinned set** (capability 2) | The copy maker for npm and PyPI, the store, the images, the sorting, the label "Sandbox copy". Asking code: only our own, for the four families. No code written by Otto yet. | A test proven and proposed for a version of elliptic or python-ecdsa that is not pinned in the app. | Large |
| **4. Otto writes the asking code** (capability 1) | The write step, the screen, the known-answer check, the two authors, the extended registration, the second pack format, the proof on the proposal, the drills. | A test proven and proposed for a library the app had no asking code for, with its proof. | Large |
| **5. The whole line by itself** | The tick and the limit per day; a research run started by the clock; the walk of the whole line; the last review. | A weakness with no fix; a fix appears; a proven test is proposed; you accept; all without a click before the Accept. | Medium |

Later, each with its own OK: Maven, then other registries (each needs a new pinned base image). The whole published exam as a second building block, for libraries with ML-KEM and ML-DSA (the reviewer already has those two rules). Candidates from the lab's own research (3.2). The "fix taken out again" copy (6.1). Registry hints about new releases. The wider list of watched libraries (decision 6). Entries in the Otto panel for the new things. And, only if you decide it, the added review rule of decision 1.

---

## Part 8. Project rules that would get a prototype clause

Approving the plan approves these clauses. Each is added in step 0, in the words below or close to them, and each says "with Sandbox research on", so the rule for a customer install does not change.

| The rule today (`CLAUDE.md` or `docs/SPEC.md`) | The clause |
|---|---|
| "Only our own demo components …, the pinned lab images and the real libraries fixed in `backend/app/real_libraries.py` run" | With Sandbox research on, also a **sandbox copy**: one exact public version of a library, fetched by the research command, checked by fingerprint, run in isolated mode only. |
| "Otto (phase 5c) uses Claude for four jobs only" | A fifth, with Sandbox research on: to write the code that asks a library a test's questions. What Claude writes is data until it is checked, and it never decides. |
| "a design can only pick published test cases (no code)" | **Stays as it is.** The design is still data. Your exception is used for the asking code and for running it. |
| "A test pack is data: nothing in it runs." | A pack made by sandbox research carries asking code as text. It is taken only when signed by this computer's own key, and that code runs only in a locked container. |
| "Only that step may pull or build; the app never does." | The research command may fetch a sandbox copy and build its image. The app still never does. |
| "**Look for new advisories** makes the app's one request to a public service … by a person's click" | With Sandbox research on, the Watch list's clock makes the same request by itself, about once a day. |
| "A live call is made only by a person's click … or by the research command with `--live` on the command line" | Or by the clock, where "Design and prove tests by itself" is ticked, within the limit per run and the limit per day. |
| "there is no timer" (SPEC 7f, point 9) | One: the Watch list's clock, with Sandbox research on. It looks. It decides nothing, accepts nothing and runs no check. |
| A research run's pack is installed by the click that started the run | For a run the clock started, the tick stands for that click, and the tick's box says so. |
| "Change watch never starts by itself" | Stays true for the Changes view and its tests. The Watch list's look is a separate thing and is named as one. |
| "Every new button, screen or setting must be in `docs/SPEC.md` section 2" | The list below goes into section 2. |

Everything new on screen, in one list:

- **Settings:** the block **Sandbox research (prototype)**: the switch, the tick **Design and prove tests by itself**, the field **Most to spend in a day**.
- **Change watch:** the two views **Changes** and **Watch list**; **Look now**; in an item's panel **Stop watching** and **Watch again**.
- **Advisories:** the part **How this test was proven** on a proposal; the label **Sandbox copy**; the line that counts what can't be tested by kind; the link "On the Watch list".
- **Overview:** one line with the count of weaknesses with no fix yet.

No new package is added. The Claude client stays the standard-library one.

---

## Part 9. Decisions for Kevin

Each with what I recommend. The plan is written on the recommended answers.

1. **The reviewer limit (1.2).** Build on "published cases, asked by code Otto writes", with the reviewer untouched? **Recommended: yes.** If you later want tests for other kinds of weakness, the way is one added review rule ("published cases from any pinned set"). That needs your explicit OK to change the reviewer and is not in this plan. The count by kind on Advisories will show how much it would open.
2. **By itself, or on a click.** With the switch on: looking by itself (free). **Recommended: yes.** Designing and proving by itself (costs money): only with a second tick, off by default. **Recommended: yes, as a separate tick.**
3. **A pack from a run the clock started is installed without a click of its own,** as the pack of a click-started run is today. Its proposals still wait for your Accept. **Recommended: yes**, covered by the tick's box.
4. **The limits.** Per run 5 US dollars for a sandbox run (today's 2 stays for everything else), per day 10. Both can be changed in Settings. **Recommended**, to be corrected after the first live run shows the real cost.
5. **Which registries first.** npm and PyPI, then Maven. **Recommended.** Others later; each needs a new pinned base image, which I would ask about first.
6. **Which libraries are watched.** At first the ones the knowledge base knows, as today's looks. **Recommended.** Widening to every row of a dependency list sends more names and needs the "about cryptography" rule; later, if you want it.
7. **A second model for the second author** of the asking code (different habits, lower cost). **Recommended: the same model at first**, and decide after the first live runs.
8. **The strict rule on further versions.** A version the advisory names as affected that gets every case right means the test is not offered. **Recommended: strict.**
9. **The names on screen:** "Sandbox research (prototype)", "Sandbox copy", "Watch list", "Look now", "Stop watching", "Watch again", "How this test was proven". And the name clash of 5.8.
10. **Demo data for the walk.** To show a fix appearing with no internet, the walk needs one real advisory recorded twice, the first time with its fixed version taken out, labelled "Demo data" on screen. **Recommended**, since nothing else can show the step.
11. **The fifth answer key** stays unwritten by the build. I add the new questions to `docs/OTTO-KEY.md` and nothing to the key.
12. **Anthropic's official package.** Not added; the standard-library client stays. This is the earlier open question and nothing here changes it.

---

## Part 10. Not in this plan

- The change-driven half of Change watch, and the earlier idea of a list of what to run again when code changes. Untouched.
- Any customer system. Any connector.
- A change to the reviewer, the answer keys or `docs/wireframes/`.
- A test whose right answers Otto supplies (1.2).
- Anything that accepts, runs a check, applies or merges by itself. A person's Accept stays the gate.
- A rating of how serious a weakness is, a score, or the word "secure".
- Weaknesses in servers (the specification places servers in a later phase).
- More sources than the one. Asking registries about new releases during a look.
- Packages with compiled parts; Go, Rust, .NET and Ruby packages.
- Entries in the Otto panel for the new things.
- The second halves of phases 6b to 6e.

---

## Part 11. How it would be shown to work

**With the switch off, nothing changed.** The accuracy check matches all four answer keys in both modes. The whole fast test set passes with Otto's harness and without it, and stays under five minutes. A test reads the code and fails if a new code path can be reached with the switch off.

**The cheating drills.** A plain proof you can read without being a developer: each way to bend a proof is tried on purpose in the test set, and each must be caught.

| # | The drill | What must happen |
|---|---|---|
| 1 | Asking code that says yes to everything | Refused by the known-answer check |
| 2 | Asking code that says no to everything | Refused by the known-answer check |
| 3 | Asking code that reads the version and bends its answers | Refused by the screen; and with the screen switched off for the drill, caught because the second author's code disagrees |
| 4 | Asking code that does the checking itself for one kind of input | The same two catches |
| 5 | The design changed after registration | The harness does not run |
| 6 | A copy changed after registration | The runner does not run it |
| 7 | A trial in which the affected version gets everything right | "Not offered" |
| 8 | A design with no case that must be refused | Refused before it is tried |
| 9 | A second run to get a better draw | Refused: one completed run for each part |
| 10 | Claude declines, or no answer comes | A stop. Nothing is proposed |
| 11 | A replay by the author who made the runs | Does not count |
| 12 | Text in an advisory or a read-me that gives instructions | Nothing changes: what comes back is screened, and the reviewer decides |
| 13 | A format 2 pack signed by another key | Refused |
| 14 | The reviewer file edited | A test fails |

**The usual tests** for each feature, as the project's rules ask: one folder for each feature (`backend/tests/sandbox/`, `backend/tests/watchlist/`), screen tests, a seeded fuzz test for every new reader, every new table measured at 1440 pixels wide with its panel open and closed, and a test that reading a page writes nothing. Every proposal screen has its tests for accept, reject with a reason, undo, and that nothing runs without a click.

**Two walks, on recorded answers, with no internet and no key.**

- `e2e/tests/watchlist.spec.ts` (demo mode): a weakness with no fix is on the Watch list with the New tag; a look finds the fix; the item reads "Fix published" with its history; stop watching and watch again; the evidence file is downloaded and verified.
- `e2e/tests/sandbox.spec.ts` (isolated mode; skipped with a message where Docker, the images or Otto are not ready): from that item, **Design and prove tests**; the copies come from the recorded registry; the asking code comes from the recorded answers; the trial runs in real containers; the proposal shows its proof; Accept; the check runs and the reviewer decides it; the evidence is verified. A second, short part does the same with the tick set and a stand-in clock, with no click before the Accept.

**One real run by hand,** in the sandbox, with the internet and a key, written up the way `docs/LIVE-CHECK.md` is: one advisory end to end, with what it cost.

**A separate reviewer** after each step, against the specification and `CLAUDE.md`, as always.

**The accuracy check for Otto** (`--only otto`) gets the new questions. While the fifth key is unwritten it prints the app's answers ungraded, as it does today.

---

*After your OK, the first thing done is the project's usual first step: a line in `docs/ACTIVE.md`, committed alone, and a draft pull request. Neither was made for this plan, because the brief asked for the plan file and nothing else.*
