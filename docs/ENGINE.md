# The research engine socket and the records behind every result

Everything that thinks about tests goes through one interface, `ResearchEngine`. A real research
engine (the autoresearcher) is meant to plug in here later without any screen changing. Since phase 5c
the first part of it has: Otto sits in the socket, around the rule-based engine (see "Phase 5c", at
the end).

**Read this first.** The two engines that propose and decide do not "think":

- **Both engines are plain rule-based code from the same build.** No AI model and no outside
  service is part of either. The engine that proposes tests is `isogeny.rule-engine/1`
  (`backend/app/engine/research.py`). The engine that reviews runs is `isogeny.rule-reviewer/1`
  (`backend/app/engine/reviewer.py`).
- They are two separate modules with two separate ids, and the reviewer imports nothing from the
  proposer (a test checks this). That keeps the *shape* right: the engine that proposed a test
  never reviews its own result. It is **not** an independent second opinion: the same people
  wrote both, at the same time. The reviewer imports only `engine/vectors.py`, `engine/pq_vectors.py`,
  `canonical.py` and `checks/tls_names.py`; `tests/test_engine.py` checks this with the full module names.
- **Since phase 5c Otto uses Claude, and decides nothing.** A test can also come from a signed test
  pack (an advisory check, proposed by `isogeny.otto-pack/1`), which Otto's research side made with
  Claude's help and tried on public copies before it shipped. In the app Claude is asked for one thing
  only: a code change, after an advisory check failed on the assessment's own program. What Claude
  writes is data. Every result still comes from the rule-based reviewer.
- **Dig deeper answers nothing.** It saves a request with status `waiting for research engine`.
  No engine picks it up in this version.

## The interface

```python
class ResearchEngine(Protocol):          # backend/app/engine/research.py
    engine_id: str
    def propose_tests(self, claims: list[dict]) -> dict   # {"tests": [TestSpec, ...], "notes": [str], "not_suggested": [...]}
    def design_test(self, request: dict) -> dict          # {"catalog_id": str, "claims": [...], "target"?: str} -> TestSpec
    def review(self, result: dict) -> dict                # {"spec", "spec_hash", "proposed_by", "run": RunRecord} -> Review
    def dig_deeper(self, finding: dict) -> dict           # {"run_id", "spec", "review", "view"} -> research request
    def propose_change(self, request: dict) -> dict | None  # failed results + the code as text -> a code change, or None
    def design_capability(self, request: dict) -> dict    # phase 4d: one library version's capability check (a TestSpec)
```

| Call | Used by | What the rule-based version does |
|---|---|---|
| `propose_tests` | opening the Tests step, and every look at Tests and Evidence Lab ("Not tested, and why") | Since phase 3a-fixes: every server in the file gets each server test that applies (`tls_versions` if the file says which TLS versions it accepts, `certificate` if it names its certificate) and every signing program each signing test, servers first in file order, then programs. Five for the demo file. `not_suggested` lists, per target, each suggested test it does not get and the reason: `{"kind", "target_kind": "server" \| "software", "target": address or claim ref, "reason"}`. |
| `design_test` | **+ Add test** | Returns one test for one target (`target`: a server address or a program's claim ref; the first that fits when not given). **+ Add test** asks once for every target that fits and has no such test yet; a removed test comes back instead of a new one. Raises `CannotDesign` if the test does not fit. |
| `review` | after every run, and again every time a result is read | Only `RuleReviewer` does this. `RuleEngine.review` always refuses (`ReviewNotAllowed`), and the reviewer refuses a test it proposed itself. |
| `dig_deeper` | **Dig deeper** | Writes down the finding and one question. Looks into nothing. |
| `propose_change` | **Connect demo code**; the Fixes list before the code is connected; and, once it is connected, every look at the fixes (the same question again, to see whether a failing test that joined the plan later is answered by the same change; the answer is never stored and nothing is run) | Applies the one fix template (below), or returns `None`. No AI model writes anything. `RuleReviewer.propose_change` always refuses. Since phase 5c the engine in the socket is `OttoEngine`: when an advisory check has failed, it asks Otto first and falls back to this ("Phase 5c", below). |

`RuleReviewer` is the only module with pass/fail logic. The code that runs tests
(`backend/app/run/execute/`) returns raw outcomes only, and the code that words results
(`backend/app/present/results.py`) reads the verdict from the stored review.

### `propose_change`: a code change from a fix template

Everything in the request is data. The code is given as text and is never run by the engine:

```python
{"component": {"name": "acme-sign", "version": "1.4.2"},
 "failed": [{"kind": "bad_signatures", "reason_code": None, "detail": {...the review's detail...}}, ...],
 "files": {"acme_sign.py": "<the whole file as text>"}}
```

The rule-based engine holds **one** template, `ecdsa-range-check`, for the component `acme-sign`. It answers a
failed `official_vectors` or `bad_signatures` result whose wrong cases all come from values outside the allowed
range. The template is a list of exact-line edits; it applies only if every one of its anchors is found in the
file exactly once. Otherwise the answer is `None`. The reply:

```python
{"template_id": "ecdsa-range-check", "title": "Reject signatures whose r or s is out of range",
 "branch": "fix/ecdsa-range-check", "label": "From a fix template",
 "answers": [1],                           # which entries of request["failed"] this change answers
 "files": {"acme_sign.py": "<new text>"},  # every file that was given, the changed one replaced
 "edits": [{"file", "title", "why", "context_before", "context_after",      # what the screen shows for each edit,
            "old_start", "old_end", "new_start", "new_end"}, ...]}          # and the lines it changed (from 0, end not included)
```

A proposed change is never offered because the engine proposed it. It is proved first (every test in the plan
is rerun on it), and the separate reviewer decides (`RuleReviewer.review_proof`, below). The same holds for a
change Otto wrote (phase 5c): its reply has the same shape, with `written_by` `"otto"` and the label "Written
by Otto".

### `review_proof`: may a change be offered?

`RuleReviewer.review_proof(record)` decides from the proof record alone; it reads no file and runs nothing. It
refuses (`ReviewNotAllowed`) a change it proposed itself. The record (`schema: "isogeny.proof/1"`):

```python
{"schema": "isogeny.proof/1",
 "change": {"fix_key", "template_id", "branch", "base_commit", "head_commit", "files": [...]},
 "built": {"file", "sha256", "matches": {"name", "version"} | None},   # the byte-for-byte check, made by the caller
 "baseline_version": "1.4.2", "version": "1.4.3", "proposed_by": "isogeny.rule-engine/1",
 "answers": [{"item_id", "kind"}],          # the failed tests the change was made for (from `changes.source`)
 "tests": [{"item_id", "kind", "spec_hash", "target": "software" | "server" | "other_program",   # other_program: another program in the file (phase 3a-fixes), judged like a server test
            "first": {"run_sha256", "code", "reason_code"} | None,                      # the result it is compared with
            "proof": {"run_sha256", "code", "reason_code", "control_outcome"} | None}]}  # its run on the changed code
```

The change is offered only if all of these hold:

1. the changed code is byte for byte one of our registered demo components, and that version is what ran;
2. every test in the proof has a run;
3. every test with a pass or fail that runs the changed code passed on it: `official_vectors` and
   `bad_signatures` Passed, `speed_size` No slowdown beyond measured noise. There must be at least one such
   test. A report-only test (`mldsa_compare`) has no pass or fail: it only has to run, it is not counted among
   the tests that passed, and alone it is not enough;
4. the control behaved in every proof run that reached a result;
5. every server test came out the same as before: the same result and the same reason. A test that could not
   run before, for the same reason, counts as unchanged;
6. every failed test the change was made for (the record's `answers`) is in this proof, runs the changed code
   and passed on it, and the record names at least one. So if those tests are taken out of the plan and the
   proof is run again, the change is not offered: no test in that proof showed that the failure is gone;
7. the speed comparison was made (SPEC 7b item 3): the proof holds a `speed_size` test that ran on the changed
   code and came out No slowdown beyond measured noise. A plan with no Speed and size test can't be offered.

The answer (`schema: "isogeny.proof-review/1"`): `reviewer`, `record_sha256` (the SHA-256 of the record: the
fingerprint of the proof), `offered`, and:

- `checks`: `code_is_ours`, `changed_code_passed`, `report_only_ran`, `controls_behaved`, `server_unchanged`,
  `answered_tests_passed`, `speed_compared`. `offered` is true only when every one of them is;
- `counts`: `tests`, `code` and `code_ok` (the tests with a pass or fail that run the changed code),
  `report_only` and `report_only_ok`, `server` and `server_ok`;
- `tests`: for each test its `group` (`code` or `server`), `report_only`, `ok` and a `reason` (`passed`,
  `no_slowdown`, `ran`, `same_as_before`, `did_not_pass`, `control_misbehaved`, `changed`, `no_run`,
  `nothing_to_compare`);
- `answers`: for each failed test the change is for, `ok` and a `reason` (`passed`, `did_not_pass`, or
  `not_in_proof` when this proof did not run it);
- `speed`: `{"ok", "reason"}` with the reason `no_slowdown`, `did_not_pass`, or `not_in_proof` when the proof
  holds no speed test.

Every one of these conditions is decided here, from the record. `fixes/changes.py` only passes stored facts, and
`present/fixes.py` only words the answer (for example "This proof did not run the failed tests the change is
for: Official test vectors and Bad signatures. Add them back in Tests and run the proof again.").

The same read gate as for results applies: whenever a proof's answer is shown or used, the record is rebuilt
from the stored rows (each run through its own read gate) and reviewed again. If that does not give exactly the
stored answer, the proof counts as not offered: "The stored proof no longer matches its fingerprint." The same
holds for a stored change that names a fix template this app does not have (`research.TEMPLATE_IDS`).

## The path every test takes

The buttons, the tests of our own code and the accuracy command all use this one path
(`backend/app/lab/testlab.py`):

1. **Propose and lock.** The test is written down in full and stored under the SHA-256 of its
   exact bytes, before anything runs.
2. **Run.** A job in the job runner (at most 4 at once by default) runs the locked test and its
   control and stores a run record with the raw outputs. A job that crashes still stores a run. (Only a test cut short because the app is closing stores nothing.)
3. **Review.** The reviewer recomputes the test's fingerprint, works out from the raw outputs
   whether the control behaved, then applies the pass/fail rule. It stores a review.
4. **Show.** A result label is only ever shown from a review. On every read the review is done
   again from the stored record; if the outcome differs from the stored review, or a fingerprint
   no longer matches, the result is shown as **Couldn't trust this run**.

Order of the reviewer's decisions, the same for every test:

1. The locked test no longer matches its fingerprint: Couldn't trust this run.
2. The run recorded a problem: Couldn't run (with the reason). The control counts as not run.
3. The control did not fail for the stated reason (it passed, crashed, timed out, or failed for
   another reason): Couldn't trust this run.
4. Where a reference library is required (official vectors, bad signatures) and it did not get
   every case right: Couldn't trust this run.
5. Otherwise the pass/fail rule decides.

## Record shapes

All records are JSON written in one exact form (`backend/app/canonical.py`): keys sorted, no
spaces, UTF-8, no NaN. A fingerprint is the SHA-256 of those bytes.

### Locked test (`test_specs`)

The component version, the mode, the baseline and all times are deliberately **not** in it, so the
same test with the same fingerprint is rerun on a new version.

```json
{"schema": "isogeny.test-spec/1", "kind": "official_vectors", "title": "Independent exam (Wycheproof)",
 "card": {"description": "...", "why": "..."},
 "question": "Does acme-sign give the right answer on every official ECDSA P-256 test case?",
 "method": "Run the verify command once per case and compare its answer with the published one.",
 "target": {"kind": "software", "component": "acme-sign", "algorithm": "ECDSA P-256", "claim": "bom-ref-of-the-claim"},
 "inputs": {"files": [{"set": "ecdsa_p256", "file": "ecdsa_secp256r1_sha256_test.json", "sha256": "182db4f3...", "cases": 484, "used_on": "component"},
                      {"set": "ed25519", "file": "ed25519_test.json", "sha256": "ea80ffeb...", "cases": 210, "used_on": "reference"}],
            "commit": "dab4ea2ed021eb633874959ca601004f3457d911", "source_url": "..."},
 "inputs_text": ["...plain-language lines shown on screen..."],
 "control": {"kind": "accept_all_verifier", "text": "...", "must": {"wrong_on": "every invalid case"}},
 "rule": {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
 "rule_text": "Passed only if all 484 answers are right. Any wrong answer means Failed."}
```

- Kinds: `tls_versions`, `certificate`, `official_vectors`, `bad_signatures`, `speed_size`,
  `pq_readiness`, `mldsa_compare`, since phase 4c `mlkem_vectors` and `mldsa_vectors`
  (see "Phase 4c" below), and since phase 5c `advisory_cases` (see "Phase 5c" below).
- `target` for a server test is `{"kind": "server", "address": "localhost:8443"}`.
- `target.claim` (phase 3a-fixes) is the ref of the file's claim that names the program, so two versions of one
  program (`acme-sign 1.4.2` and `acme-sign 9.9`) are two targets. It names no version: the version a test runs
  comes from that claim, except that the plan's **own program** (the first program in the file that is one of
  our demo components) runs on the version a retest or a proof names. Every other server and program is tested
  again as it is. A test written before phase 3a-fixes has no `claim` and is for the plan's own program.
- Titles on screen since phase 3a-fixes: `official_vectors` is "Independent exam (Wycheproof)" and
  `bad_signatures` "Attacker tricks (our short list)". The ids and the answer key are unchanged.
- `inputs`, `control.must` and `rule` are machine-readable and differ per kind. Input files are
  named with their SHA-256, so a changed vector file stops the test.
- Specs hold no decimal numbers: thresholds are whole numbers (for example
  `"noise_factor_milli": 1858, "sigma": 4, "floor_percent": 3` in the speed rule).
- Stored columns: `hash` (the key), `kind`, `canonical` (the exact text), `proposed_by`, `locked_at`.
  A locked test can't be edited; a changed test is a new row with a new fingerprint. `proposed_by` is
  the rule-based engine's id, or since phase 5c `isogeny.otto-pack/1` for a test from a test pack.

### Run record (`test_runs`)

```json
{"schema": "isogeny.run/1", "spec_hash": "<64 hex>", "phase": "first",
 "component": {"name": "acme-sign", "version": "1.4.2"}, "baseline_version": null, "mode": "demo",
 "started_at": "2026-11-11T01:42:07.120Z", "finished_at": "2026-11-11T01:42:16.520Z", "duration_ms": 9400,
 "raw": {"subject": {"...": "raw outcome"}, "control": {"...": "raw outcome"}, "reference": {"...": "..."}},
 "logs": "", "runner": "isogeny.runner/1"}
```

- `phase` is `first`, `retest` or `proof` (a run made for the proof of a change, in the Fixes step).
  `baseline_version` is set on a retest or a proof run of a software test.
- Which code a run ran on is stored beside the run, in `run_code` (below), not inside the fingerprinted record.
- `component` is `{"name": null, "version": null}` for server tests (TLS versions, certificate,
  post-quantum readiness): they test the server, not the signing component.
- `mode` is `demo` or `isolated`, recorded in every run.
- `raw` holds what the subject, the control and the reference actually answered, never a verdict.
  If the test could not run it holds `{"problem": {"code": "...", "text": "..."}}`.
- `raw` and `logs` pass through redaction before they are stored (any field whose name contains
  "private", and any PEM private-key block, is replaced).
- `started_at` and `duration_ms` count from when the test's own work began, not from when it
  joined the queue.
- Runs are inserted once and never edited or deleted, including failed ones.

### Review (`reviews`)

```json
{"schema": "isogeny.review/1", "reviewer": "isogeny.rule-reviewer/1", "proposed_by": "isogeny.rule-engine/1",
 "spec_hash": "<64 hex>", "spec_hash_ok": true, "run_sha256": "<SHA-256 of the run record>",
 "control": {"outcome": "as_expected", "reason": "accepted_every_invalid_case"}, "reference_ok": true,
 "verdict": {"code": "failed", "reason_code": null, "reason": null},
 "detail": {"total": 484, "right": 481, "wrong": [{"id": "168", "comment": "...", "expected": "invalid", "got": "accept"}]}}
```

- Verdict codes: `passed`, `failed`, `couldnt_run`, `couldnt_trust`, `measured`, `no_slowdown`,
  `slowdown`, `offered`, `not_offered`.
- Control outcomes: `as_expected`, `not_as_expected`, `errored`, `not_run`.
- `reason_code` is set for `couldnt_run`: `checker_too_old`, `checker_cannot_reach`,
  `address_not_confirmed`, `server_unreachable`, `not_a_demo_component`, `component_no_answer`,
  `timeout`, `vector_file_changed`, `spec_changed`, `isolated_unavailable`, `unreadable_answer`,
  `harness_error`.
- `detail` is everything the reviewer worked out from the raw outputs (counts, wrong cases,
  medians, the noise band). The screens word their text from it.

### The user's own records

| Table | What it holds |
|---|---|
| `review_marks` | **Mark reviewed**: the run and the time. It is the user's decision and changes no result. |
| `research_requests` | **Dig deeper**: `finding`, `question`, `evidence` (`{"run_id", "spec_hash", "review_id"}`), `status` (`waiting for research engine`), `engine`, time. No answer field exists. |
| `plans`, `plan_items`, `retests` | The user's arrangement of the plan (order, removed or not) and each Retest click. |
| `evidence_exports` | Each **Download evidence**: the exact bytes of the JSON file and the HTML report. |

### The records of the Fixes step

Eight tables, all append-only. No table stores a status: where a fix stands ("Proving", "Ready for
review", ...) is worked out from these rows every time it is shown.

| Table | One row is | What it holds |
|---|---|---|
| `code_connections` | the code connected for one imported file (**Connect demo code**) | `repository`, `folder` (the app's own copy, under the data folder), `branch`, `base_commit`, the component name and version, `is_demo` |
| `changes` | one code change: a branch plus the commit it starts from | `fix_key`, `source_kind` and `source` (the failed runs it answers), `written_by` (`fix_template`, or `otto` since phase 5c), `template_id`, `proposed_by`, `title`, `branch`, `base_commit`, `head_commit`, `files` (lines added and removed, blob ids, SHA-256 before and after, and the lines each edit changed), `built` (the byte-for-byte check: the file's SHA-256 and the registered component it is identical to, or null) |
| `proofs` | one proof of a change | `baseline_version`, `version` (the registered version that runs), `items` (the plan's tests when it started, each with the first run it is compared with). Its runs are `test_runs` rows with phase `proof` and this row's id in `retest_id`. |
| `proof_reviews` | the reviewer's answer for one proof | `reviewer`, `record_sha256` (the evidence fingerprint of the proof), `offered`, `detail` (`checks`, `counts`, each test's `group`, `report_only`, `ok` and `reason`, and `answers` and `speed`) |
| `pull_requests` | a pull request inside the app, opened on one passed proof | `number`, `title`, `reviewers` (ids from the fixed list `you`, `a`, `b`), `proof_id` (the proof it was opened on; if the plan changes later, the change's latest proof is the one that counts) |
| `approvals` | one reviewer's approval | `reviewer`, `name`, the time |
| `merges` | the merge of a pull request (a person's confirmed action) | `merge_commit`, the time |
| `run_code` | which code one run ran on (only for runs in which a component of ours ran) | `source` (`bundled`, or `repository` when the connected repository held exactly that code), the component name and version, `file_sha256` of the registered file that ran, and for `repository`: `branch`, `commit`, `change_id`, `pull_request_number` |

Only our registered demo components ever run. Code read from a repository is data: it is compared
byte for byte with a registered component, and then the registered component runs.

### What the database enforces

SQLite triggers refuse any `UPDATE` or `DELETE` on `test_specs`, `test_runs`, `reviews` and the
eight tables of the Fixes step, whatever code asks. Someone with direct access to the database
file could still remove the triggers; the fingerprints, and the review being redone on every read,
are what would show the change.

## The Fixes step: state, views and routes

Three layers, each with one job:

1. **State** (`backend/app/fixes/changes.py`, `Lab.fix_states`): every fix of a plan as plain data, with
   no wording. Failed signing tests that the fix template answers share one code fix
   (`fix-ecdsa-range-check`), which stays listed once its change is on record. A failing test
   that joins the plan after the code was connected is answered by the same code fix when the
   change's own fix template answers it (the engine is asked again, about the same starting
   code); the stored change is not touched, and since the plan changed the proof has to be run
   again. Every other failed test gets a text-only fix (`fix-<kind>`, for example
   `fix-tls-versions`). It is listed while, among the results Evidence Lab shows now for that
   test (its newest first result and its newest result in the latest retest), the newest one
   that says pass or fail is a failure. Results that say neither are passed over: "Couldn't
   run", "Couldn't trust this run", and results that only report ("Measured", "Not offered").
   So a retest that could not reach the server does not close a finding that comes from a
   first result, and a new "Measured" does not close a "Slowdown found". "Newest" is by when
   the run was made, whichever column shows it: a first result that is run again after a retest
   is newer than that retest's result. Only the results shown now count. So a finding that a
   passing retest closed reads as open again while the next retest is running, and stays open
   if that retest could not run the test; and a finding that only a retest found (its failed
   result stands in the After column) leaves the list as soon as the next retest starts, and
   stays off it if that retest could not run the test. Each
   fix has a `status` (`not_connected`, `proving`, `ready`, `failed`, `waiting`, `ready_to_merge`,
   `merged`, `text_only`) and, for each action, the sentence it would be refused with right now
   (or null). Every proof verdict in it has passed the read gate.

   The latest proof of a change leads, with or without a pull request. Only a proof that has
   passed, is still what the stored records give, and covers the plan as it is now makes a fix
   `ready`, `waiting` or `ready_to_merge`. If the plan changes while a pull request is open, the
   status goes back to `failed`; Approve, Merge and Download patch are refused ("The test plan has
   changed since the proof ran. Run the proof again first."), and Run proof again is allowed. The
   approvals already recorded stay, and count again once a new proof has passed. After the merge
   nothing changes: `merged` is a fact. Download patch is allowed only while the change is offered
   in this sense (after the merge: while the proof it was merged on is still believed).
2. **Words** (`backend/app/present/fixes.py`): every sentence of the Fixes step and of the one line
   Evidence Lab shows about a fix. It is handed data and decides nothing. Until a proof has
   passed, nothing calls the change ready or says it fixes anything.
3. **Views** (`backend/app/fixes/views.py`): `Lab.fixes_view(plan_id)` puts the two together for the
   screen, and `Lab.lab_view` gains the Evidence Lab additions. Both are asked about once a second
   while something runs. Each answer says so itself with `busy`, and what is running is read
   first, before the rest of the answer is put together. So if a test or a proof ends in
   between, the answer may still say "running" next to settled results for one second, but the
   screen asks again and the next answer is the settled one. In Evidence Lab the lines about
   the fixes are worked out after the rows, so they cover every result a row shows.

The Fixes view, in short (the exact shape is `FixesView` in `backend/app/web/models.py` (the frontend's copy is `frontend/src/api.gen.ts`), and
`backend/tests/api_shapes.py` checks every answer a test gets against that shape):

```python
{"plan_id", "is_demo", "title", "subline", "disclaimer", "list_title", "empty_text", "busy",
 "fixes": [{"id", "kind": "code" | "text", "title", "list_source", "source", "labels", "is_demo",
            "status": {"key", "word", "busy"},
            "what": {"label", "paragraphs", "server_line"},     # "What it changes" until the proof has passed
            "proof": {"state", "badge", "text", "muted"},
            "pull_request", "approvers", "patch", "merge_dialog",
            "actions": {"buttons": [{"action", "label", "primary", "enabled"}], "note"},
            "sections": [...],            # "change", "proof", "details"; or "suggestion" for a text-only fix
            "sections_note"}]}
```

The frontend draws only the buttons that are sent, and works out no status, count or sentence.

Evidence Lab additions: the view has `busy` (tests, a retest or a proof are running for this
file; the screen asks again while it is true, also when no row shows the proof's line); each
result has `fix_line` (`{"fix_id", "lead", "rest", "look", "busy",
"button"}`, or null; when it is set, `suggested_fix` is null); a result of a test that runs the
signing component has a "Code" item in its run record, right after "Component"; and the before
and after view has `code_line` and, in `columns`, `before_note`, `after_note`, `before_heading`
and `after_heading`, which say which code each side ran on.

The routes (`backend/app/web/`, one file per step; `main.py` only includes them). Every one needs a login. Each is one action by the person at
the keyboard; the only thing that starts by itself is the proof, when the code is connected.
Nothing here accepts a file or software.

| Method and path (after `/api/plans/{plan_id}`) | Button | Body | Answer |
|---|---|---|---|
| GET `/fixes` | (opening the step) | | the Fixes view |
| POST `/fixes/connect` | Connect demo code | | the Fixes view |
| POST `/fixes/{fix_id}/proof` | Run proof again | | the Fixes view |
| POST `/fixes/{fix_id}/pull-request` | Open pull request | `{"reviewers": ["you", "a"]}` | the Fixes view |
| POST `/fixes/{fix_id}/approve` | Approve | `{"reviewer": "a"}` | the Fixes view |
| POST `/fixes/{fix_id}/merge` | Confirm merge | | the Fixes view |
| POST `/fixes/{fix_id}/retest` | Retest now | | the Evidence Lab view |
| GET `/fixes/{fix_id}/patch` | Download patch | | the patch, as a file to save |

A `fix_id` is lower-case letters, digits and hyphens, at most 48. Any other id, and an id the plan
has no fix for, answers 404 "That fix does not exist." A refused action answers 409 with a plain
sentence (422 for a body that is not a pick from the fixed reviewer list) and changes nothing. The
sentence is the one the Fixes view gives for the switched-off button; the patch route refuses in
the same way while the change is not offered.

## The shape of what each screen receives (phase 4c+)

The shape of the data each screen gets is written once, in `backend/app/web/models.py` (pydantic). Nothing
else describes it by hand.

- **Routes name their shape.** Each route in `backend/app/web/` has `responses=shows(models.X)`
  (`web/common.py`). This is documentation only. The route returns exactly the data it returned before;
  nothing is converted or checked while the app runs.
- **Tests check every answer.** While a backend test talks to the app through `TestClient`, every JSON answer is
  checked strictly against its route's shape (`backend/tests/api_shapes.py`, switched on in `tests/conftest.py`).
  A key too many or too few, or a wrong kind of value, fails that test. `tests/test_api_shapes_routes.py` calls the
  routes no other test calls through the web. Small helpers for tests are in `tests/view_helpers.py`, including
  `problems(value, models.X)`.
- **Two generators write the frontend's types.** `cd backend && .venv/bin/python tools/api_schema.py` writes the
  API description to `frontend/src/api-schema.json` (add `--check` to only compare). `cd frontend && npm run gen:api`
  turns it into `frontend/src/api.gen.ts` (dev-only; add `-- --check` to only compare). `frontend/src/api.ts` keeps
  the request functions and re-exports the generated types.
- **To change a view:** change the backend, then the model, then run the two generators, then the frontend.
  GitHub's "Checks" fail if either generated file is out of date.

## The evidence file

**Download evidence** writes one JSON file (the record) and a readable HTML copy.

```json
{"evidence": {"schema": "isogeny.evidence/1", "...": "..."},
 "fingerprint": "<SHA-256 of the evidence part, 64 hex>",
 "public_key": "<the app's Ed25519 public key, 64 hex>",
 "signature": "<Ed25519 signature, 128 hex>"}
```

- The file is the canonical form of that object, with no newline at the end.
- The signature is over the bytes `isogeny-evidence-lab/evidence/v1\n` followed by the fingerprint text.
- The evidence part is built field by field from a fixed list: `schema`, `generated_at`, `app`,
  `mode_line`, `disclaimer`, `import` (file name, format, claims, addresses), `verify` (latest
  Verify results with their evidence), `component`, `tests`, `retest`, `code`, `fixes`,
  `signer_key_fingerprint`.
- Each entry of `tests` has the locked test (`spec`, `spec_hash`, `locked_at`, `proposed_by`) and,
  for each run shown in Evidence Lab (`first`, and `retest` if there was one): the run `record`,
  its `run_sha256`, the `review`, the `code` it ran on (the `run_code` values, or null for a
  server test), the worded `result` as shown on screen, `reviewed_at` and the `research_request`.
  Tests removed from the plan are not in the file. Since phase 5b each entry also has `earlier_runs`: the older
  reviewed runs of that test (a first result or a retest no longer shown), in full, in the same shape as `runs`.
- `retest` also holds the column headings and the sentence that say which code each side ran on.
- `code` is the connected code: `repository`, `branch`, `base_commit`, `component`, `is_demo`,
  `connected_at`. It is null before **Connect demo code**.
- `fixes` has one entry for each fix, as the Fixes step showed it:

```python
{"id", "kind", "title", "status",                    # the status word, for example "Ready for review"
 "proof_summary": {"state", "label", "text"},        # what the summary said about the proof under that status: the
                                                     # badge's words and the sentence (the reason that goes with the status)
 "source": {"kind": "failed_tests", "text", "results": [{"item_id", "kind", "run_id", "phase"}]},
 "suggestion": {...} | None,                         # a text-only fix: its whole suggestion, word for word
 "change": {"template_id", "label", "title", "branch", "base_commit", "head_commit", "size",
            "patch",                                 # the ready-to-apply patch, or null (see below)
            "files": [{"name", "added", "removed", "old_sha256", "new_sha256", "old_blob", "new_blob"}],
            "built": {"file", "sha256", "matches"},  # the code check
            "fix_key", "source_kind", "written_by", "proposed_by", "created_at"} | None,
 "proofs": [{"id", "started_at", "baseline_version", "version",
             "record",                               # the proof record (above), as it is fingerprinted
             "record_sha256",                        # its SHA-256: the evidence fingerprint of the proof
             "review": {"reviewer", "reviewed_at", "believed", "offered", "problem", "record_sha256", "checks", "counts",
                        "answers", "speed"} | None,
             "outcome",                              # one sentence, for example "The proof passed."
             "tests": [{"item_id", "kind", "title", "target",
                        "first": {"run_id", "run_sha256", "code", "reason_code", "label", "short"},
                        "run": {...},                # the proof run in full, exported like every other run
                        "shown": {"label", "tone", "short"}, "check": {"group", "report_only", "ok", "reason", "text"}}]}],
 "pull_request": {"number", "title", "proof_id", "reviewers", "opened_at",
                  "approvals_note"} | None,           # the sentence shown with the approvals: one login records them all
 "approvals": [{"reviewer", "name", "label",          # label is "Demo data" for a demo reviewer, else null
                "approved_at"}],                      # approved_at is null for a reviewer who has not approved
 "merge": {"merge_commit", "merged_at"} | None}
```

  `change.patch` is the patch that **Download patch** saves. It is in the file only while that
  button is allowed: a pull request is open on a proof that has passed and still stands. Otherwise
  it is null, and the file keeps what describes the change (file names, counts, blob ids,
  SHA-256s). A change that is not offered is never handed out in a form to apply.

  Every proof of a change is in the file, not only the latest. To check the evidence fingerprint
  shown on a pull request: take a proof's `record`, write it in the canonical form and hash it;
  the result must be its `record_sha256`. Each proof run the record names is in the same entry in
  full (`tests[].run`), so its fingerprint can be worked out the same way. The first result each
  test was compared with is named by its run id and fingerprint; its full record is under `tests`
  for as long as it is still the result Evidence Lab shows. When the stored records of a proof no
  longer give the stored review, `review.believed` is false and the file says "The stored proof
  no longer matches its fingerprint."
- Commit ids are in full in the file; the screens show their first seven characters.
- The HTML report has the same as a readable part, "4. Fixes", and each result's "Code" item.
  Under each code fix's status it prints the summary's own sentence about the proof, so a status
  such as "Proof failed" never stands beside a proof that passed without the reason. Under the
  approvals it prints the one-login sentence, and a demo reviewer's name is followed by
  "(Demo data)".

Check a file:

```
cd backend && .venv/bin/python -m evidence verify <file.json> [--public-key HEX_OR_FILE] [--data-dir DIR]
                                                              [--previous OLDER.json] [--pack-key HEX_OR_FILE]
```

It fails (exit code 1) on any change of even one byte: the file must be exactly the canonical
form of its own content, the fingerprint must match the evidence, the signature must be valid,
and the signer must be the key you trust (by default this app's own public key in its data
folder). With no trusted key to compare with, it says "The file is consistent with itself, but
the signer could not be confirmed." and exits with code 2, which is not a pass. Since phase 5c it
also checks a file's Otto part, and `--previous` and `--pack-key` belong to that ("Phase 5c", below).

## Plugging in a real engine later

- Implement the five methods and give the engine its own `engine_id`. `Lab` (in
  `backend/app/lab/hub.py`) holds one proposer (`self.engine`) and one reviewer (`self.reviewer`).
- A proposer must return tests in the locked-test shape above, with a machine-readable `rule` and
  `control.must` that the reviewer knows how to apply. A new kind of rule needs reviewer code too.
- A real reviewer must keep working from the stored run record alone, and must stay a different
  engine from the proposer.
- To answer research requests, an engine would read `research_requests` rows with status
  `waiting for research engine`. The table and screens for showing an answer do not exist yet.
- Since phase 5c the socket shows one way to do it: `Lab.engine` is `OttoEngine`, a wrapper that
  keeps the rule-based engine's id, passes its calls through and adds to one of them. Otto answers
  no research request and proposes no test of its own inside the app: its tests arrive in signed
  test packs.

## Phase 4a: the migration measurements

A migration measurement takes the same path as a test: it is written down in full and locked (`test_specs`), kept
as a plan item, run through the job runner, stored as a run record and reviewed by the separate reviewer. Three
things mark it out:

- **Kinds.** `pq_status` (a server) and `signing_status` (a signing program), designed by
  `RuleEngine.design_measurement`. They are not in the catalog.
- **Hidden plan items.** Their `plan_items.origin` is `"migration"` and their runs' `phase` is `"migration"`.
  `TestLabMixin._items` leaves them out, so they are never among the tests, a retest or a proof, and
  `run_test` / `remove_test` refuse them. Their jobs run in their own group, `("migration", plan_id)`.
- **Verdict codes.** `hybrid`, `pq_only`, `classical`, or `couldnt_run` with reason `unclear_answer`,
  `pq_engine_unavailable`, `claim_not_confirmed` or one of the existing reasons. As for every test, a control
  that did not behave gives `couldnt_trust`.

The raw outcome of `pq_status` (`run/execute/pqstatus.measure_server`):

```
{"engine": {"available": true, "text": "..."},
 "subject": {"address", "ip",
             "probes": {"hybrid" | "pure" | "classical": {"state": "offered" | "refused" | "unclear", "group", "alert", "detail", ...}},
             "versions": {...},                       # the TLS version handshakes, as in the other server tests
             "classical_client": {handshake}, "hybrid_handshake": {handshake}, "pure_handshake": {handshake} | null,
             "certificate": {...} | null, "container": {...} | null, "timing": {"classical_ms": [...], "hybrid_ms": [...] | null} | null,
             "evidence": [...]},
 "control": {"hybrid": {"port", "probes", "evidence"}, "classical": {...},
             "reference": {"classical": {handshake}, "hybrid": {handshake}, "timing": {...} | null}} | {"error": "..."}}
```

The rule is one function, `reviewer.pq_status_of(raw)`, used by the reviewer (`_pq_status`, and `_pq_readiness`
for a test whose rule type is `pq_status_offered`) and by Verify's `post_quantum` claim check, so the Migration
step, the Post-quantum readiness test and Verify cannot disagree. A Post-quantum readiness test locked before
phase 4a has rule type `pq_group_offered` and keeps its own executor, rule and words.

Not records: the recommendation, the blockers, the roadmap and the Fixes entries are worked out on every read
from the newest reviewed measurement (through the read gate), the settings and the choices
(`MigrationMixin._migration_states`, rules in `migration/rules.py`). What is stored, in tables that only accept
new rows: `system_settings` (import, system, field, value, source `file` or `user`) and `migration_choices`
(plan, system, option, reason, review date, and the status, recommendation and settings on screen at the time).

Routes: `GET /api/import/{id}/migration`, `POST /api/plans/{id}/migration/measure`,
`POST /api/plans/{id}/migration/settings` `{system, field, value}`,
`POST /api/plans/{id}/migration/choice` `{system, option, reason, review_date}`.

The evidence file gains `migration`: `systems` (status, settings with their source, cost table, recommendation
with its reasons, the user's choice and earlier choices, the plan and its roadmap phase), `roadmap`, and
`measurements` (for each system the locked measurement, its run record and its review, like any test).

## Phase 4b: tracks, changes, tries, Apply and Roll back

Same path as before: written down and locked, run, stored, reviewed by the separate reviewer. Words only in the
`present/` files.

**The rule type `pq_status_tracks`** (`research.PQ_TRACKS_RULE_TEXT`; inputs `tracks: true`) is a new locked-spec
fingerprint. A migration measured in phase 4a keeps its `pq_status` rule and words and must be measured again.
`reviewer.pq_status_of(raw, ..., tracks=True)` decides:

- `code`: hybrid, pq_only, classical or couldnt_run, exactly as in phase 4a. This is the **key exchange** track.
- `detail.auth`: the **authentication** track. `classical` when the certificate key and the handshake signature are
  both classical, `post_quantum` when both are post-quantum (ML-DSA), otherwise `couldnt_check` with a reason
  (`no_certificate`, `no_signature`, `mixed`). The signature is read from the first completed handshake that reports it
  (CertificateVerify in TLS 1.3, ServerKeyExchange in TLS 1.2).
- `detail.default_choice`: what the server picked when one hello offered a hybrid and a classical key share, hybrid
  listed first and classical listed first. Information, not a status.
- `detail.also_noticed`: `old_tls` (TLS 1.0 or 1.1 accepted) and `pure_too` (ML-KEM by itself also accepted). Never changes
  a status.
- the control: besides the old reading, the hybrid control server must pick hybrid and the classical one classical on the
  both-keys hello. If not, the control reads not as expected and the run can't be trusted.

**A change** (`migration/change_builder.py`) is pure: the same plan and settings give the same change and fingerprint. It is worked
out on every read and stored only when acted on. It carries the settings before and after, the lines for nginx, Apache and
an application, and the **promise**: the facts a try, and the measurement after Apply, are held to (`kex`, `auth`,
`classical_client`, or `tls` for the Acme Pay server protocol check).

**Four pure outcome functions in `engine/reviewer.py`** (the only place that decides these; `_facts_of` reads a reviewed
measurement):

- `meets_promise(promise, measured)`: (True/False/None, one check per promised fact). None when the measurement gave no
  answer or a promised fact is missing. A promise of None for a fact (authentication stays as it was, with nothing earlier
  to compare) is skipped.
- `change_try_outcome(promise, copies)`: one entry per copy (the lab server copy, and real nginx in isolated mode).
  `passed` only when every copy that was tried meets the promise and at least one was tried. A copy that couldn't be tried
  (for example "needs isolated mode") is listed and decides nothing. A copy that was tried but gave no answer makes the try
  `couldnt_run`. No copy tried: `not_run`. Otherwise `failed`.
- `apply_outcome(promise, tried, after)`: `matches` when the first measurement after Apply meets the promise and shows no
  difference from the try on `kex`, `auth`, `classical_client`, `tls`; `differs` otherwise, with the differences listed by
  fact; `no_answer` when it gave no answer.
- `rollback_outcome(before, after)`: `as_before` when the same four facts equal the ones measured before the change;
  `differs` with the differences; `no_answer` when either side has no answer.

**The copy measurement runs through the same executor** as the system's own measurement, with the address replaced by the
copy's port. Real nginx (`servers/lab_nginx.py`) is a second copy, run in a locked-down container from the pinned image.

**Records and flow** (`migration/system_changes.py`): add-only tables `change_tries`, `apply_requests`, `apply_approvals`, `applies`,
`rollbacks`. Routes `POST /api/plans/{id}/changes/try`, `.../ask-approval`, `.../approve`, `.../apply`, `.../rollback` and
`GET .../changes/download`. Apply is refused unless the latest try passed, every picked reviewer approved and the server is
one of ours. The settings in force are worked out by replaying applies and roll backs. After Apply and after Roll back the
app runs the system's measurement again by itself, and the verdict comes from `apply_outcome` or `rollback_outcome`.

The evidence file gains `changes` (every try with its runs, approval request and approvals, Apply, the measurement after,
Roll back and its measurement) and the report gains part 6, "Changes: tried, approved, applied, rolled back".

## Phase 3a-fixes: targets, plain sentences and notes in the views

- **Plan view and Evidence Lab view** carry `grouped` (true when the file names more than one server or more
  than one signing program), `groups` (`{"key": "server:<address>" | "software:<claim ref>" | "reference",
  "kind", "heading", "note"}`, in file order) and `not_tested` (`{"title": "Not tested, and why", "items": [str]}`
  or null). Each card and row carries `group`. When grouped, cards and rows come group by group.
  "Not tested, and why" lists: a suggested test a target doesn't get (the engine's reason), a program that is not
  one of our components, a server not confirmed yet, and a claim no test covers. A test the user removed is
  not listed (it is back in the catalog).
- **Every worded result** (`present.lab_result`) carries `plain`: one sentence on top, saying what was found and
  why that gives this result; and `also_noticed` (a list, often empty). `summary` and `short` stay as the
  technical text. The words are made from the stored review and run record only.
- **Every Verify row** carries `summary` (one plain sentence, from `present/plain.py`) and `also_noticed`. A row stored
  before phase 3a-fixes gets a plain fallback when it is read.
- **Also noticed** is words only: something a check saw that the file didn't ask about. The one case so far: a
  certificate check (in Verify, and the `certificate` test, whose raw record now also keeps the TLS versions
  its handshakes saw) on a server that accepts TLS 1.0 or 1.1. The reviewer never reads it, so it never
  changes a result.
- **Text-only fixes** are one per failed test, so each server has its own. The id is `fix-<test>` while the
  plan holds one test of that kind, else `fix-<test>-<item id>`. In a file with several targets the list line
  names the server or program.
- **The multi-target demo file's test servers** (`servers/extra_servers.py`, ports 8444-8446, `Settings.extra_ports`)
  start only when that exact file is imported, or when that import is verified or tested after a restart.

## Phase 4c: real libraries and the two post-quantum exams

Same path as before: written down and locked, run, stored, reviewed by the separate reviewer. Words only in the
`present/` files (the real-library words are in `present/real.py`). A real library (`real_libraries.py`, top of `backend/app/`) runs only
in isolated mode, in its own image; in demo mode its tests come out as Couldn't run ("needs isolated mode"). A real
library is a target like any other signing program: `target.component` and `target.claim` name it.

**Two new test kinds**, designed in `engine/research.py` (`_pq_exam`), run in `run/execute/pqvectors.py`, judged in
`engine/reviewer.py` (`_pq_exam`, `_pq_right`). The cases are in `engine/pq_vectors.py` (`FILES` with their SHA-256 pins, `EXAMS`).

- `mlkem_vectors`, titled "Key exchange exam (ML-KEM-768)": parts `keygen` (125 cases), `encaps` (300), `decaps` (230).
- `mldsa_vectors`, titled "Signature exam (ML-DSA-65)": parts `keygen` (25), `sign` (195), `verify` (255), and
  `left_out` 45 (NIST cases for the pre-hash variant, which the adapter does not cover).

The locked spec's own fields:

```json
{"kind": "mlkem_vectors",
 "inputs": {"algorithm": "ML-KEM-768",
            "files": [{"file": "ML-KEM-keyGen-FIPS203.json", "sha256": "d7a62a2c...", "source": "NIST ACVP"}],
            "parts": [{"id": "keygen", "title": "Key generation", "cases": 125}],
            "cases": 655, "left_out": 0,
            "sources": {"nist": "<ACVP url>", "wycheproof": "<Wycheproof url>"}},
 "control": {"kind": "pq_broken_copies", "text": "...",
             "must": {"keygen": {"control": "wrong_answer", "wrong_on": "every case"},
                      "encaps": {"control": "skip_key_check", "accepts_flag": "KeyOutOfRange", "count": 117},
                      "decaps": {"control": "skip_key_check", "accepts_flag": "KeyHashWrong", "count": 6}}},
 "rule": {"type": "pq_known_answers", "answer": "the published answer, by fingerprint", "refuse": "refused",
          "accept": "not refused", "reject": "said not genuine"}}
```

- `inputs.files` lists every file the exam reads with its SHA-256 and source (`NIST ACVP` or `Wycheproof`); a changed
  file stops the exam (`vector_file_changed`). `inputs.parts` has each part's `id`, `title` and `cases`.
- `control.must` has one entry per part, and each says which broken copy is that part's control: `wrong_answer`
  (changes a byte of every answer), `skip_key_check` (skips the two key checks FIPS 203 requires; judged on the cases
  carrying the flag `accepts_flag`, which must number `count`) or `accept_all` (the accept-everything signer; for
  ML-DSA `verify`, with `wrong_on` "every signature that must be rejected"). The ML-DSA exam's `must` is `keygen` and
  `sign` with `wrong_answer`, and `verify` with `accept_all`.
- `rule.type` is `pq_known_answers`: a case passes when the library gave the published answer (compared by SHA-256),
  refused an input that must be refused, did not refuse a good key, or said the right yes or no on a signature.
  Any wrong answer is Failed. Timing is not looked at.

**Raw run record of an exam** (`raw`; the harness job is `kat_batch`, see docs/ADAPTER.md; no key, secret or
signature is ever in it, only fingerprints):

```
{"subject": {"key": "openssl-3.5.9",
             "answers": {"<case id>": {"refused": false, "valid": null, "sha256": "<64 hex>" | null}},
             "no_answer": {"<case id>": "<why>"}},
 "controls": {"<part id>": {"control": "wrong_answer", "answers": {...as above...}, "no_answer": {...}}
                         | {"control": "...", "problem": "<text>"}},
 "files": {"<file name>": "<SHA-256 the loader just checked>"},
 "batch": {...}}
```

**Review detail** of an exam (`reviewer._pq_exam`): `total`, `right`, `wrong`, `no_answer`, `parts`, `left_out`.

- `wrong`: one entry per wrong case: `id`, `part`, `source`, `comment`, `flags`, `expected` (`answer`, `refuse`,
  `accept` or `reject`) and `got` (`the published answer`, `a different answer`, `refused`, `not refused`,
  `accepted`, `rejected`).
- `parts`: for each part `id`, `title`, `cases`, `right`, `nist`, `wycheproof` (how many cases came from each source)
  and `control` (`{"control", "caught", "of"}`, or `caught` and `of` null if that control did not answer every case).
- The review's `control` is `as_expected` (reason `every_broken_copy_failed_as_it_must`) only if every part's broken
  copy was caught; `not_as_expected` (reason `a_broken_copy_was_not_caught`) if one was not; `errored` if one did not
  answer every case. If the run recorded a problem, the verdict is Couldn't run; a case with no answer gives
  `couldnt_run` with `component_no_answer`.

**`general_errors`** (the owner's decision 1: an error raised by a library while it checks a signature counts as
"not accepted"). The batch driver passes on the wrapper's note `general error: <ClassName>` and the signing test
records it in `raw.subject.general_errors` (`{"<case id>": "<ClassName>"}`). In the review of `official_vectors` and
`bad_signatures`, those cases are scored like any other (as not accepted), and `detail.general_errors` lists them as
`[{"id", "error", "comment", "expected"}]`. It is written **only when there are any**, so the record and the review
of a run on our own demo components stay exactly what they were. It is shown under "Also noticed", never as a result.

**`can_make_pq`**: the review of a `signing_status` measurement on a real library carries `detail.can_make_pq`
(true, false or null) and `detail.pq_algorithm`. It is read from `raw.capability`: true when the check of that
capability (the library making an ML-DSA-65 signature today) said True, false when it said False, null otherwise. It is written only when a capability was
measured. `migration/state.py` reads it as the "post-quantum signatures" setting of that program.

**Retest of one library.** `POST /api/plans/{plan_id}/retest` takes `{"version": "...", "component": "..." | null}`.
`component` names which program of the file moves to the other version, when the file names more than one. It is
chosen from `_retest_choices` (each registered program with more than one version: our demo components and, since
phase 4c, the real libraries), shown by `_retest_menu`, and stored in the add-only table `retest_programs`
(`retest_id`, `component_name`). Without it the plan's own program is swapped, as before. The code that runs is
`TestLabMixin.start_retest(plan_id, version, component)`.

**Result view.** Each worded result gains `real` (true when its component is a real library, not one of our demo
components) and `advisories`: `null`, or `{"title", "tag", "items": [{"id", "text", "link", "href", "covered"}]}`,
the published advisories for that exact version (from `real_libraries.ADVISORIES`). Advisories are information from
the publisher. They only appear on `official_vectors` and `bad_signatures` results that are not Couldn't run or
Couldn't trust, and they never set a result. `covered` says whether and how these tests look at the problem. A
failed test on a real library gets a text-only fix ("Update <name> to the fixed version (<version>)", or "no fixed
version is known"); it is only text.

## Phase 4d: the capability check (dependency readiness)

Same path as every test: written down and locked, run by the job runner, stored, reviewed by the separate reviewer,
and read back through the read gate. It is a hidden plan item (origin `dependencies`, job group `("dependencies", plan_id)`),
like the Migration measurements; the Tests step never shows it. Rules in SPEC 7e.

- **Design:** `RuleEngine.design_capability({"name", "version", "label", "target_kind", "tls", "capable", "incapable"})`.
  The spec's own fields: `target` `{"kind": "library", "target_kind": "public_copy", "name", "version", "label"}`;
  `inputs.questions` (`ml_kem_768`, `x25519mlkem768` only when the copy has a TLS client, `ml_dsa_65`);
  `control` `{"kind": "capability_copies", "capable": "OpenSSL 3.5.9 …", "incapable": "OpenSSL 3.0.22 (Debian's build)", "must": {...}}`;
  `rule` `{"type": "capability"}`. The reviewer never reads `target_kind` (one test, swappable target).
- **Run** (`run/execute/capability.py`, isolated mode only; `needs_isolated_mode` in demo mode): every question is asked of
  the library and of both control copies. Per question and copy: `{"state": "made", "confirmed": bool}` (ML-KEM-768: a key
  exchange, and the app's reference library decapsulates the library's message to it; ML-DSA-65: a signature the
  reference library checks; hybrid: a handshake with the app's own server that accepts only X25519MLKEM768, plus one
  classical handshake), `{"state": "refused", "note": "<the library's own words>"}`, or `{"state": "no_answer", "why": …}`.
  No private key, secret or signature is kept.
- **Review** (`RuleReviewer._capability`): yes only when made and confirmed; no only when refused; anything else
  `couldnt_check` with its reason. The capable copy must say yes to every question and the incapable copy no to every
  question (and still complete its classical handshake), or the run is Couldn't trust. The detail holds `answers`,
  `library_says`, `why`, `controls`, `control_misses`, `same_copy_as_control` and `questions`; the code is `measured`.
- **Records:** `dependency_lists` (the list as read: components, edges, format, file name, SHA-256 and size; never the
  file itself) and `dependency_ties` (a top entry and a system key, `""` for none of these). Both add-only.
- **Labels:** `release_notes` (a lookup), `public_copy` (a reviewed measurement), `your_environment` (defined for Level 3,
  never produced; `dependencies/target.label_of`).
- **Evidence:** the `dependencies` part: `list`, `described`, `tops` (with their tie), `rows` (each answer with its
  label, first version, state, agreement and the lookup with its source), `systems` (blockers, libraries without an
  answer), `not_libraries`, and `measurements` (each copy's locked spec and its run, like any other result).

## Phase 5b: one connected assessment (every check, the work groups, links, the evidence)

Nothing here decides a result. Every number and word is read from the page that already shows it (`Lab._result` words
every run, the same function every page uses), so Checks, Evidence, the two overviews and the Related block repeat what
the checks and tests decided.

- **Every check** (`backend/app/ledger/checks.py`, `LedgerMixin.ledger(plan_id)`): one row per check of every kind,
  built on each read from records that already exist: each claim of the newest Verify run (kind `verify`), and each
  reviewed run of a test by its phase: `first` (came from the test plan), `retest`, `proof` (a fix's proof),
  `try` and `try_nginx` (a try on a test copy), `migration` (Measure status; a run right after an Apply or a Roll back
  reads "After Apply" or "After Roll back", found by the apply's or roll back's `runs_before`) and `dependencies`
  (Measure on a public copy). Each row has what ran (`name`), on what (`ran_on`), where it came from (`came_from`, with
  a link back to where it was started), the newest result in its home page's words, when it last ran, how many runs,
  and every run (`history`, newest first, each with its run record's SHA-256; a Verify run has no locked test, so no
  fingerprint). Hidden plan items (`HIDDEN_ORIGINS`) stay hidden.
- **The four work groups** (`ledger/groups.py`): Verification, Encryption tests, Migration, Dependencies, in that order
  everywhere. An item sits in the group of the work it came from; one that relates to another group is named in that
  group's foot line ("Also relates to this group"), never shown or counted twice. Each group counts Open, In progress
  and Done; a fix's status word is sorted by `FIX_STATE_BY_WORD` (an unknown word counts as open). An empty group says
  why (`EMPTY_CHECKS`, `EMPTY_FIXES`).
- **Related** (`ledger/relations.py`): a graph of recorded links only (the claim a test targets, the results a fix came
  from, a system's address or program, a migration system's fixes, a library's tie and blockers). `related(plan_id,
  key)` gives up to five lines (Claim, Checks, Fix, System and track, Library); with no recorded link there is no line.
- **Views and routes:** `GET /api/plans/{id}/checks` (the groups, the libraries for Evidence, the counts),
  `GET /api/plans/{id}/checks/{check_id}` (one check with every run and its Related lines),
  `GET /api/plans/{id}/related?key=` (any item's Related block), `GET /api/projects/{id}/overview` (every assessment
  side by side, What changed between two, shared systems; `projects/overview.py`), and the Overview's blocks on
  `GET /api/assessments/{id}` (`blocks`). The Fixes view carries `groups`.
- **Assessments** (`projects/store.py`): add-only tables `assessment_details` (purpose and reference),
  `assessment_signoffs` (who closed it, a note, when) and `import_files` (a copy of each scanner file, at most 1 MB,
  data that is never run; it is what Rerun as new assessment brings in again). A phase 5a database opens unchanged.
- **The evidence file** gains, inside the signed part: `verify_runs` (every Verify run, newest first; `verify` is the
  first of them), `checks` (every check of every kind: `check`, `group`, `name`, `ran_on`, `came_from`, and `runs` with
  `run_id` or `verify_run_id`, `at`, `came_from`, `result` and `run_sha256`), and each test's `earlier_runs` (above).
  The `assessment` part also has the purpose, the reference and the sign-off. Download evidence works from the first
  Verify result. The report has an "Every check" table near the top and Purpose and Signed off by lines under its
  title. Signing is unchanged.

## Phase 5c: Otto (advisory checks, test packs, the two ledgers, Otto's use of Claude)

Same path as every test: written down and locked, run by the job runner, stored, reviewed by the separate reviewer, and
read back through the read gate. Nothing in `backend/app/otto/` decides a result. The rules are in SPEC 7f.

**The engine in the socket** (`backend/app/otto/engine.py`). `Lab.engine` is `OttoEngine(RuleEngine(...), lab)`. Its
`engine_id` is the rule-based engine's, and every call but one is passed straight through, so the tests of the
rule-based engine keep their stamp and their fingerprints. The one call it looks at is `propose_change`. Since this
phase the request says, beside the question, who is asking:

```python
{"component": {...}, "failed": [...], "files": {...},                               # the question, as before
 "asking": {"plan_id": 12, "mode": "view" | "connect", "template_only": False}}     # new: who asks
```

A failed `advisory_cases` entry of `failed` also carries `advisory` (what its locked test says about where it came
from) and `title`. The rule-based engine is always given the question without `asking`. Otto is asked only when a
failed advisory check is among the failures of the program itself, and then:

- **Looking at a page (`view`) never asks Claude and writes nothing.** The view uses the answer already stored for
  this assessment or, while Live Otto is off, the recorded answer for exactly this prompt. With Live Otto on, a key
  present and no stored answer, the recorded answer is not used: the fix is listed as not written yet
  (`otto.pending`, with the label "Not written yet", never "Written by Otto"), and its card says what the click
  sends and that an answer which is not a registered program is refused although the request was made.
- **A person's click (`connect`, Connect demo code) is the only thing that makes a live call:** once, within the
  spending limit of that one request. The step is then stored (`otto_steps`, and in full in the assessment's Otto
  ledger), marked used or refused, and never asked for again.
- **An answer is used only if it is a clean change that gives a registered program.** `otto/fixes.check_change` reads
  the answer (`{"title", "summary", "answers": [1, ...], "edits": [{"file", "title", "why", "find": [lines], "put":
  [lines]}]}`) and refuses one that is not exactly that shape, names a file that is not in the code, does not apply
  (the lines of each `find` must stand in the file exactly once), changes nothing, holds more than 8 edits or 80
  changed lines, or uses a word this app never says about a system. Then `run/components.registered_version` must
  name one of our demo components for the changed file, byte for byte. Nothing is run to find out.
- **The reply** for a change Otto may offer has the fix template's shape, with `template_id` `otto-<advisory id>`
  (the id in lower case), `branch` `fix/otto-<advisory id>`, `label` "Written by Otto", `written_by` `"otto"`,
  `proposed_by` `isogeny.otto/1` and `otto` (the advisory, the pack, the SHA-256 of the prompt and of the answer,
  where the answer came from, and the step's ledger entry). When Otto has no change it may offer, the reply is the
  rule-based engine's own with `otto_note`, the plain reason, which Fixes shows ("Otto's own change is not offered
  here. ... The fix template is offered in its place."). When the click itself asked Claude and the answer can't be
  used, `OttoCouldNot` is raised and nothing is connected.

From there a change Otto wrote takes the path of every code fix: the byte-for-byte check, the proof, `review_proof`,
the pull request, the approvals and the merge are unchanged.

**The advisory check** (`advisory_cases`, titled "Advisory check: *plain name* (*id*)"). It is made from a pack's
design by `otto/designs.spec_for`, locked by `otto/checks.add_design_item` with `proposed_by` `isogeny.otto-pack/1`
and added to the plan with origin `added`, like a test from **+ Add test**. It is run by
`run/execute/signing.run_advisory_cases`, judged by `RuleReviewer._advisory_cases` and worded in
`present/advisory.py`. The locked spec's own fields:

```json
{"kind": "advisory_cases", "title": "Advisory check: Missing ECDSA signature range check (CVE-2022-21449)",
 "target": {"kind": "software", "component": "acme-sign", "algorithm": "ECDSA P-256", "claim": "<claim ref>"},
 "inputs": {"advisory": {"id": "CVE-2022-21449", "plain_name": "...", "quote": "<the publisher's own line>",
                         "source": {"title": "...", "url": "...", "published": "...", "checked": "..."},
                         "pack": "2026.11.1", "pack_fingerprint": "<64 hex>", "design_sha256": "<64 hex>"},
            "files": [{"set": "ecdsa_p256", "file": "ecdsa_secp256r1_sha256_test.json", "sha256": "182db4f3...",
                       "cases": 77, "used_on": "component"}],
            "cases": ["109", "151", "..."], "must_reject": 77, "must_accept": 0, "commit": "...", "source_url": "..."},
 "control": {"kind": "accept_all_verifier", "text": "...", "must": {"wrong_on": "every invalid case"}},
 "rule": {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"}}
```

- The reviewer takes only the cases the locked test names, each of which must be in the pinned file, and judges them
  as it judges the Independent exam: the control must get every invalid case wrong, the reference library every case
  right, and the program passes only if every answer is right. The review's detail is the exam's (`total`, `right`,
  `wrong`, and so on).
- In a proof it is a test that runs the changed code and must pass on it (`PROOF_PASS_CODES`).
- One new reason for Couldn't run, `otto_not_installed`: a check added from a pack does not run where the pinned Otto
  is missing, because its run could not be recorded.
- The result carries `advisories`: the box "The advisory this check is for" (`present/advisory.box`), tagged "quoted
  from the named source, not a result" (a quote may come from the publisher's source file, not the advisory page).
  The link is the address the quoted text was read from (`read_from` in the pack). A link from a pack is sent to the
  screen or the report only when it is an https address of a known publisher (`present/advisory.LINK_HOSTS`);
  anything else is shown as text. The Suggested fix line repeats
  what the installed pack says about a fix (`Lab.otto_result_fix`): words only.

**A design** (`isogeny.advisory-design/1`, `otto/designs.py`) is what a pack carries for one test. It is data and can't
carry code: `advisory`, `block` (`signature_cases`, the one building block), `plain_name`, `question` (naming the
program once as `{program}`), `why`, `cases` (`set`, `file`, `sha256`, `commit`, `source_url`, `select` with `flags`
and `ids`, `ids`, `must_reject`, `must_accept`), `control` (`accept_all_verifier`), `rule` (`all_cases_match`) and
`model_step` (the SHA-256 of the prompt and of the answer it was made from). `check_design` runs every time a design is
used: the case list must be exactly what its own selection picks from the pinned file, and a selection with no
must-reject case is refused.

**A test pack** (`otto/packs.py`; `research/packs/<version>.json`):

```json
{"pack": {"schema": "isogeny.test-pack/1", "version": "2026.11.1", "built_at": "...", "previous": null, "signer": "...",
          "research": {"snapshot": "2026-11-17", "snapshot_sha256": "...", "answers": "recorded",
                       "answers_note": "..."},
          "otto": {"repository": "...", "commit": "...", "version": "...",
                   "ledger": {"height": 82, "head": "...", "root": "..."}, "scripts": {"<name>": "<SHA-256>"}},
          "advisories": [{"id": "...", "aliases": [], "package": {}, "published": "...", "sources": [],
                          "reading": {}, "reading_refused": null,
                          "test": {"state": "ready", "reason": "...", "design_sha256": "...", "trial": {}},
                          "fix": {"state": "proven", "reason": "...", "kind": "update", "library": "...",
                                  "version": "...", "quote": {}, "summary": "...", "trial": {}},
                          "steps": [], "ledger": []}],
          "tests": [{"design": {}, "design_sha256": "<64 hex>"}]},
 "fingerprint": "<SHA-256 of the pack part>", "public_key": "<64 hex>", "signature": "<128 hex>"}
```

- The file is the canonical form of that object. The signature is Ed25519 over the bytes
  `isogeny-evidence-lab/test-pack/v1\n` followed by the fingerprint text. `previous` is the fingerprint of the pack
  before it, or null for the first. `research.answers` is `recorded`, `live` or `mixed`.
- A test's `state` is `ready`, `not_offered` or `none` (on screen: Test ready, Not offered, No test yet). A fix's is
  `proven`, `not_proven` or `none`; its `kind` is `update` or null.
- `read_envelope` takes a pack only when the file is exactly canonical, the fingerprint matches, the signature holds,
  the signer is a trusted key (`otto/trusted-pack-keys.json`, shipped with the app, plus this computer's own public key
  in the data folder for a pack built here) and `check_pack` passes: the exact shape, every design runnable by this
  version, a `ready` test only with a trial that was supported and replayed, a `proven` fix only with a ready test and
  such a trial of its own, and every step's answer matching its SHA-256. `follows` says why a pack can't be installed
  next. A file is at most 4 MB and holds at most 60 advisories. Every refusal is one plain sentence.
- `trial` is `{"hypothesis", "decision", "outcome", "replayed", "arms"}`; the first two are record ids of the research
  ledger. A test's arms are `reference`, `affected`, `fixed` and `accept-all`, each with `right`, `wrong` and `total`;
  a fix's are `affected`, `fixed` and `affected-again`, each with `failing` and `tests`.
- Each of an advisory's `sources` is `{"label", "title", "publisher", "url", "read_from", "fetched"}`: `url` is the
  page a person would look at, `read_from` the address the quoted text was downloaded from on the day in `fetched`
  (for a file in a repository, the raw file at its pinned commit). The screens link to `read_from`.
- `steps` are the advisory's Claude steps (`step`, `source`, `model`, `prompt_sha256`, `answer`, `answer_sha256`, the
  tokens and the cost, `at`, `how`, `outcome` `used` or `refused`, `refusal`, and `claim`, its entry in the research
  ledger). `ledger` lists that advisory's entries of the research ledger (`seq`, `kind`, `id`, `at`, `what`).
- An installed pack is a row of `otto_packs`: the file as it was read, never removed. **Check for updates** reads the
  updates folder (`research/packs/`, or the folder `EVIDENCE_LAB_OTTO_UPDATES` names) and the data folder's
  `otto-updates/`, where a pack built on this computer goes. Nothing is downloaded.

**Otto's use of Claude** (`otto/model.py`). One client, two sources:

- *Recorded:* `research/recorded/<step>-<first 16 hex of the prompt's SHA-256>.json` (`isogeny.recorded-answer/1`:
  `step`, `prompt_sha256`, `prompt`, `answer`, `answer_sha256`, `recorded` with `at` and `how`). A file whose prompt or
  answer no longer matches its SHA-256 is no answer. `EVIDENCE_LAB_OTTO_RECORDED` names another folder.
- *Live:* one request to Claude's Messages API, made with Python's standard library, only when live calls are allowed
  (the Live Otto switch, or `--live` on the research command) and `ANTHROPIC_API_KEY` is set. One model answers every
  step, `claude-opus-5-5` (`DEFAULT_MODEL`; `EVIDENCE_LAB_OTTO_MODEL` names another, which must have a price in the
  list), with an effort level for each step. A busy API is tried again, at most twice. If the API answers a declined
  request with another model it offers in its place, the step names the model that answered. A declined, cut-off or
  empty answer is not used, and nothing is made up in its place.
- *The spending limit* (`Budget`): before every request (the first, and each one sent again after a busy answer or
  a time-out), its worst case is added to what the run has spent; if that passes the limit, the request is not
  sent. The worst case is every byte of the prompt counted as a token and a full-length answer, at the dearest price
  that could apply, for every attempt that could be billed (two where a declined request may be passed to another
  model). A request that got no answer at all may have been billed, so its worst case stays counted against the
  limit (`unanswered_nano`); so does an answer cut off part-way and an answer that can't be read. In the research
  command each step is its own process, and the file `OTTOLAB_SPENT_FILE` names carries what was spent, the calls
  and that amount from step to step. After an answer the cost is worked out from the tokens the API reports, every
  attempt counted. Prices are whole numbers of a billionth of a dollar per token (`PRICES_NANO_PER_TOKEN`, with its source and
  date in `PRICE_SOURCE`), so every sum is exact.
- *The key* is read from the environment at the moment of a call, sent only as that request's header, and removed
  from every text that leaves the module (`redact`). A value that is not in the form of a key (a space or a line
  break inside it) is never sent, and a request that can't be made is reported by the kind of its error only, never
  in the error's own words, because an HTTP library can name a header's value there. It is in no step, log, error
  or file.
- A step is `{"step", "source": "recorded" | "live", "model", "prompt", "answer", "prompt_sha256", "answer_sha256",
  "input_tokens", "output_tokens", "cost_nano_usd", "at", "how"}`; `model` is null for a recorded answer. The steps are
  `read_advisory`, `design_test` and `propose_fix` (the research side; prompts and answer checks in
  `ottolab/prompts.py`) and `write_fix` (in the app; `otto/fixes.py`).

**The research ledger** (`research/lab/`; written only by Otto's harness, driven by `backend/ottolab/`). In Otto's own
records:

- a `question` for each advisory's test and, once that test held its trial, one for its fix;
- a design that selects exactly the published cases of the check of another advisory about the same library is
  refused before any trial (`ottolab/research.same_check_as`): its step is kept as refused, no hypothesis is
  registered, and the pack reads "No test yet" with that reason. Only a check that exists counts: a design of this
  build whose own trial held, or a test of an earlier pack (the build command lists those for the run in the file
  `OTTOLAB_EARLIER_FILE` names, so a lab that never saw the earlier packs knows them too). The same cases for
  another library are another check. `ottolab/build.same_check_twice` looks once more before a pack is signed;
- for each Claude step an `objective`, a `claim` that holds the step in full (with what the answer came to, or why it
  was refused) and the `verdict` of the pinned checker `check_model_step.py`: the hashes match, the answer has its
  shape, and every quoted line stands in the prompt that was sent;
- a `hypothesis` for each trial, registered before any run, with its arms, baseline, prediction, kill line, controls,
  claim ceiling and the SHA-256 of the files it runs (`trial.py`, the design or the fix file). A test's trial has the
  arms `reference` (the baseline: the app's reference library on the same cases), `affected`, `fixed` and `accept-all`;
  the metric is `right`; the prediction is that the affected version gets at least one case fewer right than the
  reference; the negative control is the fixed version (no difference from the reference) and the positive control the
  accept-everything program (wrong on every must-reject case). A fix's trial has the arms `affected` (the baseline),
  `fixed` and `affected-again`; the metric is `failing`, how many pass-or-fail tests did not read Passed; the
  prediction is that it falls to none on the fixed version;
- a `run` for each arm: `ottolab/pinned/trial.py` locks the check, runs it through `Lab` and reads the review, so a
  real library runs only in its container. A test that could not run, or a run that can't be trusted, is not a number:
  the script stops, and the harness records an infrastructure failure, never a result;
- the harness's `decision` (`supported`, `refuted` and so on), an `audit` for the replay under a second author's
  name (a second role of the same build on the same computer, and worded so on screen), and a `fact` that states
  what the trial showed (a dead end when it was refuted).

`ottolab/build.py` turns that ledger into a pack: a test is `ready` only when its trial was supported and replayed, a
fix `proven` only when its own trial was. The agent command (`ottolab/agent.py`) reads the loop's prompt as data: only
its action line and its target line are used. The model judge of Otto's loop is never used.

**The assessment's Otto ledger** (`otto/assurance.py`): one Otto lab for each assessment, at
`<data>/otto/assessment-<id>/`, with the pinned checker `otto/checker/recheck.py` copied in.

| Entry | When | What it holds |
|---|---|---|
| lock entry (an `objective`) | **Add new checks**, before the check can run | the locked test's fingerprint, the design's SHA-256, the pack's fingerprint and version, the advisory and the program |
| run entry (a `claim`, then the checker's `verdict`) | after each reviewed run of that check: `first`, `retest` or `proof` | the test's fingerprint, the run's id, the SHA-256 of its run record and of its review, `proposed_by`, `reviewer`, the phase and what it ran on; never a result |
| step entry (an `objective`, a `claim`, a `verdict`) | a Claude step taken in the app | the step in full, and `used` or `refused` with the reason |

The checker accepts a run entry only when it names the test its lock entry locked, carries both SHA-256, was proposed
by the pack and reviewed by someone else, and holds no result. "accept" means bound and consistent; it is never shown
as a result. The review's SHA-256 is taken over the review as the evidence file holds it, without its time
(`otto/state.review_fingerprint`), so anyone can work it out again from the file. If a ledger entry can't be written,
the run and its review are already stored and stay.

**Records:** three more add-only tables: `otto_packs` (the installed packs), `otto_checks` (the plan item, the pack and
the design it came from, and its lock entry) and `otto_steps` (every Claude step taken in the app, in full). The Live
Otto switch and the spending limit are two rows of `app_settings`.

**What the Advisories view says and does not say** (`present/otto.py`). A row's Result cell counts only the programs
that have a result ("1 of 1 run so far; 3 with no result yet"). The panel's `notes` is `{"title", "kind_line",
"text", "caption"}`: Claude's reading notes, labelled as Claude's words, with the kind of weakness the reading
recorded. The line about a change for your own code is shown only when a program of the assessment that is one of our
demo components (`run/components.lookup`; never a real library) has this check in its plan and no fix answers it yet.
A trial's replay is worded as a step of the same build on the same computer.

**Views and routes** (`otto/state.py`, words in `present/otto.py`, routes in `web/otto.py`): `GET /api/otto` (Settings:
Test packs, the two status lines and Live Otto), `POST /api/otto/packs/check`, `POST /api/otto/packs/install`
`{version}`, `POST /api/otto/live` `{on, limit}`, `GET /api/plans/{id}/advisories` and
`POST /api/plans/{id}/advisories/add` (refused on a closed assessment). The Related graph gains `advisory:<id>` nodes
(the sixth line), the Overview's next step can point to Advisories, and a failed advisory check on a real library gets
a text-only fix with `otto_fix`: the pack's fix, labelled "From Otto", when the advisory is about that library, and
otherwise one sentence that says the pack holds no fix for this program (no label).

**The evidence file** gains `otto`, inside the signed part, only when the assessment has an advisory check or a Claude
step: `schema` (`isogeny.otto-evidence/1`), `harness` (repository, commit, version, installed), `packs` (the signed
pack files its checks came from, whole), `checks` (for each advisory check: `item_id`, `title`, `advisory`,
`spec_hash`, `spec`, `design_sha256`, `pack`, `pack_fingerprint`, `lock_entry`, `added_at`, `in_plan`), `ledger`
(`height`, `head`, `root` and its `lines`, exactly as written), `runs` (every run the ledger binds: `ledger_entry`,
`lock_entry`, `run_id`, `phase`, the run `record` and its `review`), `steps` (every Claude step taken in the app, in
full) and a `note`. `app.note` then says that advisory checks come from Otto's packs. The report gains part 8, "Otto:
test packs, the ledger and Claude's steps".

**The verify command** (`backend/evidence/otto.py`) checks the Otto part after the file's own signature held, in this
order:

1. every pack in the file is whole, its signature holds, and its signer is a pack key you trust (the keys shipped
   with the app, this computer's own, or one given with `--pack-key`);
2. every advisory check's design is in its pack, its locked test matches its fingerprint and names that design and
   that pack, and its lock entry is in the ledger with the same fingerprints;
3. the ledger is one unbroken hash chain, and its latest entry is the one the signed evidence names;
4. every run the ledger binds is in the file with a record and a review that match the SHA-256 the ledger holds, and
   every Claude step matches its SHA-256 and has its entry in the ledger;
5. with `--previous OLDER.json`, the older file's latest ledger entry is still in this chain, at the same place
   (entries added since are not covered by that comparison);
6. Otto's own audit of the chain and the records, and the pinned checker run again on every checked entry. A
   ledger read from a file is data, and nothing it names is ever run. Asked to check entries again
   (`audit(reverify=True)`), Otto's harness starts the verifier an entry names, and it looks that entry up by its
   id whatever its kind; a verifier can name a command. So the harness is never asked to. Instead:
   - `otto/assurance.only_our_checker` holds every entry to the exact form this app writes: one of the three kinds
     (`ENTRY_KINDS`) with exactly the fields of its kind (`ENTRY_FIELDS`); an objective whose verifier is our own
     pinned checker with nothing added; a claim that points at an earlier objective; a verdict that points at an
     earlier claim and at that claim's own objective. Anything else fails the check, and nothing is run;
   - the harness audits the chain and the records with `audit(reverify=False)`, which runs no verifier;
   - `otto/assurance.check_again` runs this app's own checker (`run_checker`: the file that ships with the app, a
     fixed command, an empty folder, a bare environment) on every entry it once accepted or rejected, and compares.
     A different answer, or an entry that could not be checked again, fails the check.

   The app's own audit of an assessment's ledger (`Ledger.audit`) goes the same way. A run in the file that the
   ledger does not bind fails too, and so does a run in the file's own list of tests whose record or review does not
   match the SHA-256 the ledger holds under its number. A file with an advisory check and no Otto part fails
   (`needs_otto_part`). `MAX_ENTRIES` and `CHECK_AGAIN_SECONDS` bound a ledger made to be slow, and a claim may be
   settled only once. What is printed of the file's own text holds printable characters only.

   The pinned checker itself (`otto/checker/recheck.py`) takes a run entry only with exactly its fields (fingerprints
   and names; no place for a result) and what it ran on with exactly four. `Ledger._lab` makes the checker file in an
   assessment's folder the app's own before every use (a regular file with the bytes of `CHECKER_SOURCE`; a link is
   removed, never followed), and the lock names that checker's SHA-256.

   The research side's audit (`ottolab/build.audit_problems`) follows the same pattern for a research lab folder:
   folders and regular files only (`only_regular_files`), `names_only_our_checker`, the harness's audit without
   re-verification, and `run_pinned_checker` (ottolab/pinned/check_model_step.py, started by the command itself).

Step 6 needs the pinned harness on the computer that runs the command. Without it the first five checks are still
made, the command says that Otto's audit was not run, and it exits with code 2. A pack signed by a key you do not
trust also gives code 2. Neither is a pass. Any check that fails gives code 1.

