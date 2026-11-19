# A 15-minute check with the real internet and a real key (for Kevin)

Everything the tests prove, they prove with recorded advisories and recorded answers. Two things could not be tried
on the build machine at all: reading the public advisory source (that machine cannot reach it), and asking Claude
for real (no test may, and the build machine has no key). This list is the short check of both. It should cost
well under the two-dollar spending limit, and the first part costs nothing.

Do it in your Codespace or on your own computer, with the app started by `./run-demo.sh`.

Written on 19 November 2026, during the overnight run. It covers what is built today: the research loop and
phase 5c's live fix. The assistant's own live steps (free wording in 6b, questions in 6c, what-if in 6e) are not
built yet, so there is nothing of them to check.

## Part 1: the first real look at the public source (2 minutes, free, no key needed)

1. On **Projects**, press **Load demo projects** (if you have not), and open the project **Real libraries (isolated mode)**.
   Open its assessment, then **Advisories**.
2. In the block **New advisories**, press **Look for new advisories**. A box opens.
   - You should see: "Asks OSV (osv.dev) ..." and "What is sent: these package names, and nothing else: ecdsa (PyPI)
     and elliptic (npm)." (openjdk and openssl are listed as not asked about.)
3. Press **Look**.
   - You should see, within a few seconds: "Looked on *today* by You: *N* published advisories about your
     libraries ...", the line "Read from OSV (osv.dev). Sent: ecdsa (PyPI) and elliptic (npm), and nothing else.", and
     a list.
     Each advisory says where it stands: "In a test pack", "Not about a version you have", "No test yet" with a
     reason, or "New: not tried yet".
   - If it says the answer "is not in the shape it documents", or lists nothing at all for elliptic: please copy
     that sentence for me. The reader was written from OSV's documentation and has never seen a real answer.
   - If it says the source could not be reached: check that the computer has internet, and try once more.
4. Nothing else should have changed: no new test in the test plan, nothing running, no new test pack in Settings.

## Part 2: Live Otto on (1 minute)

1. Make sure the key is set before the app starts: in a Codespace it is the secret `ANTHROPIC_API_KEY`; on your
   own computer, set that environment variable in the terminal that runs `./run-demo.sh`.
2. Open **Settings**, section **Live Otto**.
   - You should see that a key is present (never the key itself), the switch **Use live Claude**, and the
     spending limit per run (2.00 US dollars unless you changed it).
3. Turn the switch on. The status line should read: "Live Otto is on: when an answer is needed, Claude is asked
   through your key, within the spending limit."

## Part 3: a research run with Claude (about 10 minutes; costs money, at most the limit; needs Docker)

Only if Part 1 listed an advisory as **New: not tried yet**. With the versions pinned today that is unlikely for
anything newer than the built-in packs: most will read "No test yet", and then there is nothing to do here.

1. Press **Design and prove tests**. Read the box: it should say that Live Otto is on, that the advisory's
   published text is sent to Claude, and the most the run can cost. Press **Start**.
2. Wait. The block shows what the research run says, and reads the page again by itself.
   - At the end you should see either "Test pack *version*, made on this computer, was installed." or why there
     is no pack.
   - A proven check then shows in the list below as a proposal marked **From Otto**, with **Accept** and
     **Reject**. One that was not proven says "No test yet (test pack *version*)" with the reason.
3. Whatever the outcome, nothing of your assessment should have run, and nothing should be in the test plan that
   you did not accept.

## Part 4: a change written live for your own code (3 minutes; costs a few cents)

This is phase 5c's live step. It has never made a real call either.

1. Open the project **Acme Pay** and its assessment. If it has no results yet: **Verify claims**, then on
   **Advisories** accept the proposed check for CVE-2022-21449, then on **Checks** press **Run all**.
2. Open **Fixes** and the fix for the failed advisory check. With Live Otto on and nothing recorded for your exact
   program, the proposal reads "Not written yet" and says what a click will send.
   - Note: on the demo file a recorded answer exists, so the proposal may already read "Written by Otto". Then
     this part has nothing live to show, and that is fine.
3. If it reads "Not written yet": accept the proposal, then press **Connect demo code**.
   - You should see either the change offered as "Written by Otto" (then the proof starts by itself), or a plain
     refusal that says the answer could not be used and that the fix template is offered in its place. A refusal
     is a correct outcome: only a change that gives one of our registered demo programs, byte for byte, may run.

## Afterwards (1 minute)

1. **Settings**, **Live Otto**: turn the switch off again if you do not want it on.
2. On **Advisories** (or in the fix's panel), unfold **Otto ledger entries** for a step that was asked live: it
   should name the model, the tokens and the cost. The key is shown nowhere.
3. Download the evidence of the assessment and check it:
   `cd backend && .venv/bin/python -m evidence verify PATH-TO-FILE.json`. It should say "Evidence verified", with a
   line about the looks for new advisories and, after Part 3, the research run.

## What to send me if something is off

The sentence the app showed, which part and step it was, and (for Part 1) the two lines under the **Look** button.
No screenshot of Settings is needed, and please never send the key.
