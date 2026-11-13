# The research engine socket and the records behind every result

Everything that thinks about tests goes through one interface, `ResearchEngine`. A real research
engine (the autoresearcher) is meant to plug in here later without any screen changing.

**Read this first.** In this version nothing "thinks":

- **Both engines are plain rule-based code from the same build.** There is no AI model and no
  outside service. The engine that proposes tests is `isogeny.rule-engine/1`
  (`backend/app/research.py`). The engine that reviews runs is `isogeny.rule-reviewer/1`
  (`backend/app/reviewer.py`).
- They are two separate modules with two separate ids, and the reviewer imports nothing from the
  proposer (a test checks this). That keeps the *shape* right: the engine that proposed a test
  never reviews its own result. It is **not** an independent second opinion: the same people
  wrote both, at the same time.
- **Dig deeper answers nothing.** It saves a request with status `waiting for research engine`.
  No engine picks it up in this version.

## The interface

```python
class ResearchEngine(Protocol):          # backend/app/research.py
    engine_id: str
    def propose_tests(self, claims: list[dict]) -> dict   # {"tests": [TestSpec, ...], "notes": [str]}
    def design_test(self, request: dict) -> dict          # {"catalog_id": str, "claims": [...]} -> TestSpec
    def review(self, result: dict) -> dict                # {"spec", "spec_hash", "proposed_by", "run": RunRecord} -> Review
    def dig_deeper(self, finding: dict) -> dict           # {"run_id", "spec", "review", "view"} -> research request
    def propose_change(self, request: dict) -> dict | None  # failed results + the code as text -> a code change, or None
```

| Call | Used by | What the rule-based version does |
|---|---|---|
| `propose_tests` | opening the Tests step | Returns the suggested tests that fit the claims (five for the demo file; fewer if the file names no server or no signing component). |
| `design_test` | **+ Add test** | Returns one test from the catalog: `pq_readiness`, `mldsa_compare`, or a suggested test that was removed. Raises `CannotDesign` if the test does not fit the file. |
| `review` | after every run, and again every time a result is read | Only `RuleReviewer` does this. `RuleEngine.review` always refuses (`ReviewNotAllowed`), and the reviewer refuses a test it proposed itself. |
| `dig_deeper` | **Dig deeper** | Writes down the finding and one question. Looks into nothing. |
| `propose_change` | **Connect demo code**; the Fixes list before the code is connected; and, once it is connected, every look at the fixes (the same question again, to see whether a failing test that joined the plan later is answered by the same change; the answer is never stored and nothing is run) | Applies the one fix template (below), or returns `None`. No AI model writes anything. `RuleReviewer.propose_change` always refuses. |

`RuleReviewer` is the only module with pass/fail logic. The code that runs tests
(`backend/app/execute/`) returns raw outcomes only, and the code that words results
(`backend/app/present.py`) reads the verdict from the stored review.

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
is rerun on it), and the separate reviewer decides (`RuleReviewer.review_proof`, below).

### `review_proof`: may a change be offered?

`RuleReviewer.review_proof(record)` decides from the proof record alone; it reads no file and runs nothing. It
refuses (`ReviewNotAllowed`) a change it proposed itself. The record (`schema: "isogeny.proof/1"`):

```python
{"schema": "isogeny.proof/1",
 "change": {"fix_key", "template_id", "branch", "base_commit", "head_commit", "files": [...]},
 "built": {"file", "sha256", "matches": {"name", "version"} | None},   # the byte-for-byte check, made by the caller
 "baseline_version": "1.4.2", "version": "1.4.3", "proposed_by": "isogeny.rule-engine/1",
 "answers": [{"item_id", "kind"}],          # the failed tests the change was made for (from `changes.source`)
 "tests": [{"item_id", "kind", "spec_hash", "target": "software" | "server",
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

Every one of these conditions is decided here, from the record. `changes.py` only passes stored facts, and
`present_fixes.py` only words the answer (for example "This proof did not run the failed tests the change is
for: Official test vectors and Bad signatures. Add them back in Tests and run the proof again.").

The same read gate as for results applies: whenever a proof's answer is shown or used, the record is rebuilt
from the stored rows (each run through its own read gate) and reviewed again. If that does not give exactly the
stored answer, the proof counts as not offered: "The stored proof no longer matches its fingerprint." The same
holds for a stored change that names a fix template this app does not have (`research.TEMPLATE_IDS`).

## The path every test takes

The buttons, the tests of our own code and the accuracy command all use this one path
(`backend/app/testlab.py`):

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
{"schema": "isogeny.test-spec/1", "kind": "official_vectors", "title": "Official test vectors",
 "card": {"description": "...", "why": "..."},
 "question": "Does acme-sign give the right answer on every official ECDSA P-256 test case?",
 "method": "Run the verify command once per case and compare its answer with the published one.",
 "target": {"kind": "software", "component": "acme-sign", "algorithm": "ECDSA P-256"},
 "inputs": {"files": [{"set": "ecdsa_p256", "file": "ecdsa_secp256r1_sha256_test.json", "sha256": "182db4f3...", "cases": 484, "used_on": "component"},
                      {"set": "ed25519", "file": "ed25519_test.json", "sha256": "ea80ffeb...", "cases": 210, "used_on": "reference"}],
            "commit": "dab4ea2ed021eb633874959ca601004f3457d911", "source_url": "..."},
 "inputs_text": ["...plain-language lines shown on screen..."],
 "control": {"kind": "accept_all_verifier", "text": "...", "must": {"wrong_on": "every invalid case"}},
 "rule": {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
 "rule_text": "Passed only if all 484 answers are right. Any wrong answer means Failed."}
```

- Kinds: `tls_versions`, `certificate`, `official_vectors`, `bad_signatures`, `speed_size`,
  `pq_readiness`, `mldsa_compare`.
- `target` for a server test is `{"kind": "server", "address": "localhost:8443"}`.
- `inputs`, `control.must` and `rule` are machine-readable and differ per kind. Input files are
  named with their SHA-256, so a changed vector file stops the test.
- Specs hold no decimal numbers: thresholds are whole numbers (for example
  `"noise_factor_milli": 1858, "sigma": 4, "floor_percent": 3` in the speed rule).
- Stored columns: `hash` (the key), `kind`, `canonical` (the exact text), `proposed_by`, `locked_at`.
  A locked test can't be edited; a changed test is a new row with a new fingerprint.

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
| `changes` | one code change: a branch plus the commit it starts from | `fix_key`, `source_kind` and `source` (the failed runs it answers), `written_by` (`fix_template`), `template_id`, `proposed_by`, `title`, `branch`, `base_commit`, `head_commit`, `files` (lines added and removed, blob ids, SHA-256 before and after, and the lines each edit changed), `built` (the byte-for-byte check: the file's SHA-256 and the registered component it is identical to, or null) |
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

1. **State** (`backend/app/changes.py`, `Lab.fix_states`): every fix of a plan as plain data, with
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
2. **Words** (`backend/app/present_fixes.py`): every sentence of the Fixes step and of the one line
   Evidence Lab shows about a fix. It is handed data and decides nothing. Until a proof has
   passed, nothing calls the change ready or says it fixes anything.
3. **Views** (`backend/app/fixes.py`): `Lab.fixes_view(plan_id)` puts the two together for the
   screen, and `Lab.lab_view` gains the Evidence Lab additions. Both are asked about once a second
   while something runs. Each answer says so itself with `busy`, and what is running is read
   first, before the rest of the answer is put together. So if a test or a proof ends in
   between, the answer may still say "running" next to settled results for one second, but the
   screen asks again and the next answer is the settled one. In Evidence Lab the lines about
   the fixes are worked out after the rows, so they cover every result a row shows.

The Fixes view, in short (the frontend's types in `frontend/src/api.ts` are the exact shape, and
`backend/tests/fixes_shapes.py` checks every view against them):

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

The routes (`backend/app/main.py`). Every one needs a login. Each is one action by the person at
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
  Tests removed from the plan, and older runs of a test that was run again, are not in the file.
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
```

It fails (exit code 1) on any change of even one byte: the file must be exactly the canonical
form of its own content, the fingerprint must match the evidence, the signature must be valid,
and the signer must be the key you trust (by default this app's own public key in its data
folder). With no trusted key to compare with, it says "The file is consistent with itself, but
the signer could not be confirmed." and exits with code 2, which is not a pass.

## Plugging in a real engine later

- Implement the five methods and give the engine its own `engine_id`. `Lab` (in
  `backend/app/lab.py`) holds one proposer (`self.engine`) and one reviewer (`self.reviewer`).
- A proposer must return tests in the locked-test shape above, with a machine-readable `rule` and
  `control.must` that the reviewer knows how to apply. A new kind of rule needs reviewer code too.
- A real reviewer must keep working from the stored run record alone, and must stay a different
  engine from the proposer.
- To answer research requests, an engine would read `research_requests` rows with status
  `waiting for research engine`. The table and screens for showing an answer do not exist yet.
