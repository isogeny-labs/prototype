# The research engine socket and the records behind every result

Everything that thinks about tests goes through one interface, `ResearchEngine`. A real research
engine (the autoresearcher) is meant to plug in here later without any screen changing.

**Read this first.** In this version nothing "thinks":

- **Both engines are plain rule-based code from the same build.** There is no AI model and no
  outside service. The engine that proposes tests is `isogeny.rule-engine/1`
  (`backend/app/engine/research.py`). The engine that reviews runs is `isogeny.rule-reviewer/1`
  (`backend/app/engine/reviewer.py`).
- They are two separate modules with two separate ids, and the reviewer imports nothing from the
  proposer (a test checks this). That keeps the *shape* right: the engine that proposed a test
  never reviews its own result. It is **not** an independent second opinion: the same people
  wrote both, at the same time. The reviewer imports only `engine/vectors.py`, `engine/pq_vectors.py`,
  `canonical.py` and `checks/tls_names.py`; `tests/test_engine.py` checks this with the full module names.
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
```

| Call | Used by | What the rule-based version does |
|---|---|---|
| `propose_tests` | opening the Tests step, and every look at Tests and Evidence Lab ("Not tested, and why") | Since phase 3a-fixes: every server in the file gets each server test that applies (`tls_versions` if the file says which TLS versions it accepts, `certificate` if it names its certificate) and every signing program each signing test, servers first in file order, then programs. Five for the demo file. `not_suggested` lists, per target, each suggested test it does not get and the reason: `{"kind", "target_kind": "server" \| "software", "target": address or claim ref, "reason"}`. |
| `design_test` | **+ Add test** | Returns one test for one target (`target`: a server address or a program's claim ref; the first that fits when not given). **+ Add test** asks once for every target that fits and has no such test yet; a removed test comes back instead of a new one. Raises `CannotDesign` if the test does not fit. |
| `review` | after every run, and again every time a result is read | Only `RuleReviewer` does this. `RuleEngine.review` always refuses (`ReviewNotAllowed`), and the reviewer refuses a test it proposed itself. |
| `dig_deeper` | **Dig deeper** | Writes down the finding and one question. Looks into nothing. |
| `propose_change` | **Connect demo code**; the Fixes list before the code is connected; and, once it is connected, every look at the fixes (the same question again, to see whether a failing test that joined the plan later is answered by the same change; the answer is never stored and nothing is run) | Applies the one fix template (below), or returns `None`. No AI model writes anything. `RuleReviewer.propose_change` always refuses. |

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
  `pq_readiness`, `mldsa_compare`, and since phase 4c `mlkem_vectors` and `mldsa_vectors`
  (see "Phase 4c" below).
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
  `backend/app/lab/hub.py`) holds one proposer (`self.engine`) and one reviewer (`self.reviewer`).
- A proposer must return tests in the locked-test shape above, with a machine-readable `rule` and
  `control.must` that the reviewer knows how to apply. A new kind of rule needs reviewer code too.
- A real reviewer must keep working from the stored run record alone, and must stay a different
  engine from the proposer.
- To answer research requests, an engine would read `research_requests` rows with status
  `waiting for research engine`. The table and screens for showing an answer do not exist yet.

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
