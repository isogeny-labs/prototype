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

The walk: Use demo file, Verify, Check for updates, Install the first pack, Add new checks, Run all; the fix
(Connect demo code, the proof, Open pull request, two approvals, Merge, Retest now); the second pack (Install, Add
new checks, Run all); Download evidence.

| Question | What it asks | Values |
| --- | --- | --- |
| `acme.update_found` | The pack that Check for updates offers first | a version |
| `acme.checks_added_from_first_pack` | How many advisory checks Add new checks adds from the first pack | a number |
| `acme.first.<advisory>.result` | The first result of that advisory's check | a result label |
| `acme.first.<advisory>.program` | The program it ran on | for example `acme-sign 1.4.2` |
| `acme.first.<advisory>.wrong_cases` | The case numbers it got wrong, in the reviewer's order | a list of case numbers as text |
| `acme.wording.no_banned_words` | No result uses "secure", "score", "severity", "critical" or "time to hack" | true or false |
| `acme.fix.ottos_own_change` | Whether the change Otto wrote for the program's own code is offered | `offered`, `not offered: the program it gives is not one of our registered demo programs`, `not offered: no recorded answer`, `not offered: the answer was not a clean change`, `not asked` or `no code fix` |
| `acme.fix.written_by_before_connect` | Who the listed code fix is by, before the code is connected | `otto` or `fix_template` |
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
| `acme.second_pack.next_step_page` | Where the Overview's next step points once the second pack is installed | a page such as `advisories` |
| `acme.second_pack.checks_ready_to_add` | How many new checks it says are ready | a number |
| `acme.checks_added_from_second_pack` | How many checks Add new checks adds from the second pack | a number |
| `acme.second_pack.<advisory>.result` | The result of each check the second pack added | a result label |
| `acme.second_pack.<advisory>.program` | The program it ran on (a new check runs first on the version the scanner file names) | for example `acme-sign 1.4.2` |

### The evidence file (both modes)

Each answer is the exit code of the verify command (`python -m evidence verify`): 0 means verified, 1 not verified.

| Question | The file given to the command |
| --- | --- |
| `evidence.fresh_download` | A fresh download |
| `evidence.one_byte_changed` | The same file with one byte changed inside Otto's part |
| `evidence.ledger_line_changed_and_signed_again` | One line of Otto's ledger changed, and the file signed again with the app's own key |
| `evidence.ledger_line_removed_and_signed_again` | One ledger line removed, signed again |
| `evidence.pack_swapped_and_signed_again` | The test pack in the file swapped for another, signed again |
| `evidence.previous_later_download` | A later download, with `--previous` naming an earlier one |
| `evidence.previous_with_a_shorter_ledger` | The earlier download, with `--previous` naming the later one |

### The real libraries file

In demo mode a real library never runs, so one question applies:

| Question | What it asks | Values |
| --- | --- | --- |
| `real.demo_mode.advisory_check_on_a_real_library` | The result of an advisory check on a real library in demo mode | a result label |

In isolated mode (`<program>` is a library and version from `demo/real-libraries.csv`, such as `elliptic 6.5.6`;
the retests are openjdk 17.0.3, python-ecdsa 0.13.3 and elliptic 6.5.7):

| Question | What it asks | Values |
| --- | --- | --- |
| `real.first.<program>.<advisory>.result` | The first result of that advisory's check on that library | a result label |
| `real.first.<program>.<advisory>.wrong_cases` | The case numbers it got wrong | a list of case numbers as text |
| `real.fixes_from_otto` | The titles of the fixes labelled "From Otto", in alphabetical order | a list of titles |
| `real.fix.<title>` | The labels of each such fix | a list of labels |
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

`docs/SPEC.md`, `docs/LIMITS.md` and `docs/HANDOFF.md` also describe what this build measured for phase 5c (the
packs' trial figures, the results on the Acme Pay demo). Those passages repeat the app's own answers: a key copied
from them would grade the app against itself. Use them to check your key afterwards, not to write it.
