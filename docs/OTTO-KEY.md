# The fifth answer key: Otto's loop (phase 5c)

This note is for whoever writes `demo/expected-otto.json`, the answer key for Otto's loop. It lists the questions
the accuracy check asks, the values an answer can take, and the exact test cases each shipped advisory check uses.
It holds **no measured result**: nothing here says what any program or library answered. The key must be worked
out independently, from the publishers' advisories and from the published right answers of the test cases, not
from what the app prints.

One part of this note is the app's own output all the same: the table of cases near the end. Which cases a check
uses is Otto's design, and the table therefore also shows which advisories have a test at all, which is what the
questions `pack.<pack>.<advisory>.test` ask. Write your answers to those questions first, from the advisories and
from what the one building block can show (it hands a program a published ECDSA P-256 signature and reads accept or
reject), and read the table after that.

The build never writes or edits this key. Until the file is in the repository, the check below shows the app's
answers and grades nothing.

## How it is graded

```bash
cd backend && .venv/bin/python -m app.accuracy --only otto --mode demo
```

```bash
cd backend && .venv/bin/python -m app.accuracy --only otto --mode isolated
```

The check walks Otto's loop through the same path as the buttons, on a scratch database, and writes down what the
app answers as a flat list of named questions. Then it compares that list with the key.

- A plain run of `python -m app.accuracy` grades the four older keys as before, and this one too once it exists.
- Exit code 0 only if the key is there, every question in it matches, and the walk ran to its end.
- A question that is in the key and that the app did not answer is a mismatch, never silence.
- The key decides what is asked. An answer the key does not ask about is not graded.
- Questions that apply in one mode only (see below) are listed as "not graded" in the other mode.
- With `--only otto`: exit code 2 when the key is missing, 3 when Otto is not installed on this computer (an advisory
  check can't be added without the pinned harness, so there is nothing to grade).

## The form of the key

One JSON object with one member, `answers`, that maps each question to its expected value:

```json
{
  "answers": {
    "packs.order": ["...", "..."],
    "acme.first.CVE-2022-21449.result": "..."
  }
}
```

Values are compared exactly: text with text, numbers with numbers, true or false, and lists item by item in order.
A result is the label the screen shows, word for word, for example `Passed`, `Failed` or
`Couldn't run (needs isolated mode)`.

## The questions

`<advisory>` is an advisory id such as `CVE-2022-21449`. `<pack>` is a pack version such as `2026.11.1`.

### The packs (both modes)

| Question | What it asks | Values |
| --- | --- | --- |
| `packs.order` | The shipped packs, in the order they install | a list of versions |
| `pack.<pack>.<advisory>.test` | Whether the pack ships a test for this advisory | `ready`, `none` (no test yet) or `not_offered` (a design was tried on public copies and did not hold) |
| `pack.<pack>.<advisory>.fix` | Whether the pack's fix for a library is proven on public copies | `proven`, `not_proven` or `none` |
| `pack.refused.one_byte_changed` | A pack file with one byte changed | `refused` or `accepted` |
| `pack.refused.unknown_key` | A pack signed by a key this installation does not trust | `refused` or `accepted` |
| `pack.refused.out_of_order` | The second pack installed before the first | `refused` or `accepted` |

### The trials on public copies, as the packs carry them (both modes)

For every advisory whose test is `ready`:

| Question | What it asks | Values |
| --- | --- | --- |
| `trial.<advisory>.outcome` | How Otto's harness judged the test's trial | `supported`, `refuted` or another outcome word of the harness |
| `trial.<advisory>.replayed` | Whether a second author replayed the trial | true or false |
| `trial.<advisory>.affected_wrong` | How many of the test's cases the affected public version got wrong | a number |
| `trial.<advisory>.fixed_wrong` | How many the publisher's fixed version got wrong | a number |
| `trial.<advisory>.control_wrong_on_every_case` | Whether the control (a checker that accepts every signature) got every case wrong | true or false |

For every advisory with a fix trial:

| Question | What it asks | Values |
| --- | --- | --- |
| `fixtrial.<advisory>.outcome` | How Otto's harness judged the fix's trial | as above |
| `fixtrial.<advisory>.failing_before` | How many pass-or-fail tests failed on the affected public version | a number |
| `fixtrial.<advisory>.failing_after` | How many still failed on the publisher's fixed version | a number |

The pass-or-fail tests of a fix trial are the Independent exam, Attacker tricks and every advisory check whose own
trial held. Speed is not part of it. The rule is strict: a fix is `proven` only if none of them fails on the fixed
version.

### The Acme Pay demo file (both modes)

The walk, since 18 November 2026 (Otto proposes, a person decides; every decision below is one click on one
proposal, and there is no button for several at once):

1. Use demo file, Verify, Check for updates, Install the first pack.
2. Otto's proposed checks, in the order Advisories lists them. The first is accepted. The second is rejected with
   the reason `Not this quarter`. The accept of the first is undone, and it is accepted again. The second is
   reconsidered and then accepted. Every other proposed check is accepted. Nothing has run so far. Then Run all.
3. Otto's proposed fix for the program's own code: Connect demo code is tried before the proposal is accepted; then
   the proposal is accepted, the code is connected, and the fix takes its path (the proof, Open pull request, two
   approvals, Merge, Retest now). Otto's proposed change to the migration plan is accepted before the retest.
4. The second pack is installed; the check it proposes is accepted; Run all.
5. The demo dependency list (`demo/dependencies-demo.cdx.json`) is added. Of Otto's proposed updates, taken in
   alphabetical order of their titles, the first is accepted and the second is rejected with the reason
   `Moves with the platform team`.
6. Download evidence.

The two reasons above are inputs of the walk, not results.

A proposal's status is the word the screen shows: `Proposed`; `Added` (an accepted check) or `Accepted` (an accepted
fix, plan change or dependency update); `Not added (<reason>)`, or `Not added (no reason given)`.

| Question | What it asks | Values |
| --- | --- | --- |
| `acme.update_found` | The pack that Check for updates offers first | a version |
| `acme.import.checks_that_may_apply` | The number in Import's line "Otto found N checks that may apply", once the first pack is installed | a number |
| `acme.proposals.checks_proposed_from_first_pack` | How many checks Otto proposes from the first pack | a number |
| `acme.proposals.every_check_says_why_it_applies` | Whether every proposed check says why it applies to its program | true or false |
| `acme.waiting_for_you.before_any_decision` | The count of the Overview's "Waiting for you", before any decision | a number |
| `acme.decision.accept.status` | The first proposed check's status after Accept | a status |
| `acme.decision.reject.status` | The second proposed check's status after Reject with the walk's reason | a status |
| `acme.decision.reject.kept_on_record` | Whether the rejected proposal is still listed | true or false |
| `acme.decision.undo.status` | The first check's status after Undo | a status |
| `acme.decision.undo.check_left_the_plan` | Whether Undo took the check out of the test plan | true or false |
| `acme.decision.reconsider.status` | The second check's status after Reconsider | a status |
| `acme.checks_added_from_first_pack` | How many advisory checks from the first pack are in the test plan once every proposal is accepted | a number |
| `acme.decision.accepting_ran_nothing` | Whether no test had run when all of them were accepted | true or false |
| `acme.checks.marked_from_otto` | How many cards of the test plan are marked "From Otto" then | a number |
| `acme.decision.undo_after_a_run` | Whether Undo is still possible on an accepted check once it has run | `refused` or `allowed` |
| `acme.first.<advisory>.result` | The first result of that advisory's check | a result label |
| `acme.first.<advisory>.program` | The program it ran on | for example `acme-sign 1.4.2` |
| `acme.first.<advisory>.wrong_cases` | The case numbers it got wrong, in the reviewer's order | a list of case numbers as text |
| `acme.wording.no_banned_words` | No result uses "secure", "score", "severity", "critical" or "time to hack" | true or false |
| `acme.fix.ottos_own_change` | Whether the change Otto wrote for the program's own code is offered | `offered`, `not offered: the program it gives is not one of our registered demo programs`, `not offered: no recorded answer`, `not offered: the answer was not a clean change`, `not asked` or `no code fix` |
| `acme.fix.written_by_before_connect` | Who the listed code fix is by, before the code is connected | `otto` or `fix_template` |
| `acme.fix.proposal.status_before_a_decision` | The status of Otto's proposed fix before anyone decided | a status |
| `acme.fix.connect_before_accept` | What Connect demo code does while the proposal is not accepted | `refused` or `connected` |
| `acme.fix.proposal.status_after_accept` | Its status after Accept | a status |
| `acme.plan.proposal.made_before_the_status_is_measured` | Whether Otto proposes a change to the migration plan after the check has failed but before Measure status has run (the system has no place on the plan yet) | true or false |
| `acme.plan.proposal.made_after_the_failed_check` | Whether Otto proposes a change to the migration plan once an advisory check has failed on the signing program and its status has been measured | true or false |
| `acme.plan.proposal.status_after_accept` | That proposal's status after Accept | a status |
| `acme.fix.written_by` | Who the connected change is by | `otto` or `fix_template` |
| `acme.fix.label` | The label on the fix | a list with one label, `Written by Otto` or `From a fix template` |
| `acme.fix.ottos_step_kept_as` | How each Claude step taken at the click was kept in the assessment's ledger | a list of `used` or `refused` |
| `acme.fix.changed_code_is` | The registered version the changed code is, byte for byte | a version |
| `acme.fix.status` | The fix's status once the proof has ended | `ready` when the fix may be offered |
| `acme.fix.offered_after_proof` | Whether the reviewer let the fix be offered | true or false |
| `acme.fix.proof_reran_advisory_checks` | How many advisory checks the proof ran again on the changed code | a number |
| `acme.fix.proof_advisory_checks_ok` | Whether each of them held in the proof | true or false |
| `acme.after_merge.<advisory>.result` | The check's result after Merge and Retest now | a result label |
| `acme.after_merge.<advisory>.program` | The program that result is for | for example `acme-sign 1.4.3` |
| `acme.after_merge.<advisory>.same_locked_test` | Whether it is the same locked test (same fingerprint) as before the fix | true or false |
| `acme.plan.proposal.done_after_the_retest` | Whether the accepted plan change reads as done once the check has a newer, passing result | true or false |
| `acme.second_pack.next_step_page` | Where the Overview's next step points once the second pack is installed | a page such as `advisories` |
| `acme.second_pack.checks_ready_to_add` | How many proposed checks it says wait for a decision | a number |
| `acme.checks_added_from_second_pack` | How many checks join the test plan when the second pack's proposals are accepted | a number |
| `acme.second_pack.<advisory>.result` | The result of each check the second pack added | a result label |
| `acme.second_pack.<advisory>.program` | The program it ran on (a new check runs first on the version the scanner file names) | for example `acme-sign 1.4.2` |

### The dependency list on the Acme Pay demo (both modes)

`<library>` is a library and version of the list, such as `elliptic 6.5.6`. A library is "named by an advisory" when
an advisory of the installed packs is about that library and the version in the list is lower than the version the
publisher names as fixed. What was measured is one of `measured affected`, `measured not affected` and
`not yet checked`: "measured" only counts this assessment's own result of that advisory's check on the same library
and version.

| Question | What it asks | Values |
| --- | --- | --- |
| `acme.dependencies.named_by_an_advisory` | The libraries of the list that an advisory names, in alphabetical order | a list of libraries |
| `acme.dependencies.<library>.named` | For each such library, each advisory with what was measured, as `<advisory>: <measured>`, in the order the page lists them | a list |
| `acme.dependencies.updates_proposed` | The titles of the updates Otto proposes, in alphabetical order | a list of titles |
| `acme.dependency.accept.proposal_status` | The accepted proposal's status | a status |
| `acme.dependency.accept.library_status` | The status that library then carries on Dependencies | a label, or none |
| `acme.dependency.reject.proposal_status` | The rejected proposal's status | a status |
| `acme.dependency.reject.library_status` | The status that library then carries | a label, or none |
| `acme.dependency.deciding_changed_no_blocker_and_ran_nothing` | Whether the two decisions left every blocker line as it was and ran nothing | true or false |

### The evidence file (both modes)

Each answer is the exit code of the verify command (`python -m evidence verify`): 0 means verified, 1 not verified.

| Question | The file given to the command |
| --- | --- |
| `evidence.fresh_download` | A fresh download |
| `evidence.one_byte_changed` | The same file with one byte changed inside Otto's part |
| `evidence.ledger_line_changed_and_signed_again` | One line of Otto's ledger changed, and the file signed again with the app's own key |
| `evidence.ledger_line_removed_and_signed_again` | One ledger line removed, signed again |
| `evidence.pack_swapped_and_signed_again` | The test pack in the file swapped for another, signed again |
| `evidence.decision_changed_and_signed_again` | The name on one recorded decision changed, signed again |
| `evidence.decision_removed_and_signed_again` | One proposal's only decision removed and the proposal set back to "proposed", signed again |
| `evidence.previous_later_download` | A later download, with `--previous` naming an earlier one |
| `evidence.previous_with_a_shorter_ledger` | The earlier download, with `--previous` naming the later one |

Three more questions are about the fresh download itself, not about the verify command:

| Question | What it asks | Values |
| --- | --- | --- |
| `evidence.decisions_in_the_file` | How many decisions the file holds, over all of Otto's proposals (the walk above says which were made) | a number |
| `evidence.every_decision_names_who_and_when` | Whether every one of them names who decided and when | true or false |
| `evidence.rejected_proposal_with_its_reason` | Whether the file holds the rejection of step 2 with its reason | true or false |

### Change watch on the Acme Pay demo (both modes; phase 6d)

Asked last, on the same assessment, after everything above: the fix is merged, both packs are installed and every
accepted check has run. The walk presses **Bring in a demo change** for each of the two bundled changes, then **Run
the picked tests** for the one that undoes the merged fix. `<change>` is `revert-range-check` ("Revert the range
check": its code is, byte for byte, acme-sign 1.4.2) or `allow-tls-1-0` ("Allow TLS 1.0 for an old partner": it adds
one settings file and leaves the program alone). What each change holds is in `demo/changes/`.

| Question | What it asks | Values |
| --- | --- | --- |
| `change.<change>.offered` | Whether Bring in a demo change offers it at this point | true or false |
| `change.bringing_in_ran_nothing` | Whether bringing both changes in made no run and started no job | true or false |
| `change.<change>.edits_the_program` | Whether the change edits the program's own file (a change that only adds or edits other files leaves the program alone) | true or false |
| `change.<change>.code_is` | Which registered version of acme-sign everything the change leaves in the repository is, byte for byte | a version; null when it is none, which is also the answer for a change that adds a file beside an unchanged program (read it with `edits_the_program`) |
| `change.<change>.picked` | The tests picked for it, by their titles, in plan order | a list of titles |
| `change.<change>.not_picked` | The tests of the plan that are not picked | a list of titles |
| `change.<change>.status_before_a_run` | Its status word before anything ran | a status word |
| `change.<change>.can_run` | Whether Run the picked tests can be pressed for it | true or false |
| `change.<change>.flags` | Its flags, each as "*file* line *n*: *name*" | a list |
| `change.revert-range-check.status_after_the_run` | Its status word once the picked tests have run and were reviewed | a status word, with its count |
| `change.revert-range-check.<test title>.before` | That test's result on the code the change starts from | a result label |
| `change.revert-range-check.<test title>.on_the_change` | Its result on the change's code | a result label |
| `change.revert-range-check.<test title>.reads` | What the reviewer's rule says of the two | `Passed before, fails now`, `Failed before, passes now`, `No difference found`, `Slower than the code before`, `No slowdown against the code before`, or one of the two "Not compared" sentences |
| `change.revert-range-check.own_results_unchanged` | Whether Evidence and Advisories read exactly what they read before the run | true or false |
| `change.revert-range-check.fixes_entry` | The title of the entry Fixes then lists for the change | a title, or null |
| `change.revert-range-check.fixes_entry_status` | That entry's status word | a status word |
| `evidence.change_watch.fresh_download` | The verify command's exit code for a download made after the run | 0 or 1 |
| `evidence.change_watch.reviewers_word_changed_and_signed_again` | The same, with the reviewer's word for the change altered in the file and the file signed again with the app's own key | 0 or 1 |
| `evidence.change_watch.run_record_changed_and_signed_again` | The same, with one run record of the watch run altered, signed again | 0 or 1 |
| `evidence.change_watch.part_removed_and_signed_again` | The same, with the Change watch part taken out of the file, signed again | 0 or 1 |

The status words of a change are: Not run yet, Running, No difference found, Passed before, fails now (with the
count), Failed before, passes now (with the count), Nothing to run, Can't run, Couldn't trust this run.

### The real libraries file

In both modes:

| Question | What it asks | Values |
| --- | --- | --- |
| `real.proposals.checks_proposed` | How many checks Otto proposes for this file once both packs are installed (one for each ready test and each signing library it fits) | a number |

In demo mode a real library never runs, so one more question applies:

| Question | What it asks | Values |
| --- | --- | --- |
| `real.demo_mode.advisory_check_on_a_real_library` | The result of an advisory check on a real library in demo mode | a result label |

In isolated mode (`<program>` is a library and version from `demo/real-libraries.csv`, such as `elliptic 6.5.6`;
the retests are openjdk 17.0.3, python-ecdsa 0.13.3 and elliptic 6.5.7):

| Question | What it asks | Values |
| --- | --- | --- |
| `real.first.<program>.<advisory>.result` | The first result of that advisory's check on that library | a result label |
| `real.first.<program>.<advisory>.wrong_cases` | The case numbers it got wrong | a list of case numbers as text |
| `real.fixes_from_otto` | The titles of the fixes labelled "From Otto", in alphabetical order (a title reads "Update *library* to *version*") | a list of titles |
| `real.fix.<title>` | The labels of each such fix | a list of labels |
| `real.fix.<title>.proven_on_public_copies` | The word of its first proof row | `Passed` or `Not proven` |
| `real.fix.<title>.proven_on_your_system_before_a_retest` | The word of its second proof row before any retest | `Not yet`, `Passed` or `Not proven` |
| `real.fix.proposals_waiting` | How many of Otto's fixes wait for a decision (the walk then accepts each one) | a number |
| `real.fix.<title>.proven_on_your_system_after_the_retest` | The word of the second row after the retest on that fix's version. It is `Passed` only if the advisory check and every other pass-or-fail test of that library passed in that retest | `Passed` or `Not proven` |
| `real.failed_checks_with_no_fix_from_otto` | The failed advisory checks for which the pack holds no fix, because the program is not the library the advisory is about; each as Fixes lists it | a list, in alphabetical order |
| `real.retest.<library version>.<advisory>.result` | The check's result after Retest new version | a result label |
| `real.retest.<library version>.<advisory>.wrong_cases` | The case numbers it got wrong then | a list |

## The cases each shipped advisory check uses

This table is Otto's design, not a result of any run (see the note at the top: answer the `pack.*.test` questions
before reading it). Every advisory check hands the program published test cases and compares its accept or reject
with the published right answer. The cases are from Project Wycheproof, file `ecdsa_secp256r1_sha256_test.json`, at commit
`dab4ea2ed021eb633874959ca601004f3457d911` (SHA-256 of the file
`182db4f3e230f6f9fa9f800d2a614dede30284b8e8438bbfe1171905402e9332`). The numbers below are the `tcId` values in that
file. A check passes only if every answer is right.

| Advisory | Pack | Cases | Published right answer |
| --- | --- | --- | --- |
| CVE-2022-21449 | 2026.11.1 | 77 cases: every case flagged `InvalidSignature` or `RangeCheck`, and cases 109, 151, 351, 363, 364, 376 and 477. In full: 109, 151 to 154, 160 to 162, 168 to 231, 351, 363, 364, 376, 477 | all must be rejected |
| CVE-2019-14859 | 2026.11.1 | 9 cases: every case flagged `BerEncodedSignature`, and cases 84 and 128. In full: 8, 9, 48, 67, 68, 84, 114, 115, 128 | all must be rejected |
| CVE-2019-14853 | 2026.11.1 | No test in this pack | |
| CVE-2024-42460 | 2026.11.2 | 1 case: the case flagged `MissingZero`, case 6 | must be rejected |
| CVE-2024-42461 | 2026.11.2 | No test in this pack | |
| CVE-2024-42459 | 2026.11.2 | No test in this pack | |

The control of every check is a deliberately broken checker that accepts every signature. It must get every
must-reject case wrong; a run whose control does not is not trusted.

## Where the expected answers can come from

Work the key out from sources that do not depend on this build's own results for phase 5c:

- Which version a publisher names as affected and as fixed: the publishers' own pages. The snapshot the packs were
  built from is in `research/snapshot/2026-11-17/`, with each source's address and the date it was read.
- What a program does with one of the cases above: the full exam (Independent exam) already runs every case of the
  same file. What it measured for each program and version in phase 4c is in `docs/LIMITS.md` (the phase 4c
  section) and `docs/SPEC.md` section 8 (the real libraries). An advisory check reruns a part of that exam, so its
  wrong cases are the exam's wrong cases that fall inside its list.
- What the verify command must say about a changed file: the rules in `docs/SPEC.md` (section 7f, point 11).
- What a decision does and what a status reads: the rules in `docs/SPEC.md` (section 7f, point 9, and section 2).
  The decisions themselves are the walk's, listed above.
- Which tests a developer's change picks, and what its status reads: the rules in `docs/SPEC.md`, section 2
  ("Change watch"). A change that touches the program's file picks every test of the plan that runs that program;
  the two bundled changes are in `demo/changes/`. What each picked test answers on the change's code follows from
  what it answers on acme-sign 1.4.2, which the questions `acme.first.*` already ask; what it answers on the code
  before follows from `acme.after_merge.*`.

`docs/SPEC.md`, `docs/LIMITS.md` and `docs/HANDOFF.md` also describe what this build measured for phase 5c (the
packs' trial figures, the results on the Acme Pay demo). Those passages repeat the app's own answers: a key copied
from them would grade the app against itself. Use them to check your key afterwards, not to write it.
