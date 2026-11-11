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
```

| Call | Used by | What the rule-based version does |
|---|---|---|
| `propose_tests` | opening the Tests step | Returns the suggested tests that fit the claims (five for the demo file; fewer if the file names no server or no signing component). |
| `design_test` | **+ Add test** | Returns one test from the catalog: `pq_readiness`, `mldsa_compare`, or a suggested test that was removed. Raises `CannotDesign` if the test does not fit the file. |
| `review` | after every run, and again every time a result is read | Only `RuleReviewer` does this. `RuleEngine.review` always refuses (`ReviewNotAllowed`), and the reviewer refuses a test it proposed itself. |
| `dig_deeper` | **Dig deeper** | Writes down the finding and one question. Looks into nothing. |

`RuleReviewer` is the only module with pass/fail logic. The code that runs tests
(`backend/app/execute/`) returns raw outcomes only, and the code that words results
(`backend/app/present.py`) reads the verdict from the stored review.

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

- `phase` is `first` or `retest`. `baseline_version` is set on a retest of a software test.
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

### What the database enforces

SQLite triggers refuse any `UPDATE` or `DELETE` on `test_specs`, `test_runs` and `reviews`,
whatever code asks. Someone with direct access to the database file could still remove the
triggers; the fingerprints, and the review being redone on every read, are what would show the
change.

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
  Verify results with their evidence), `component`, `tests`, `retest`, `signer_key_fingerprint`.
- Each entry of `tests` has the locked test (`spec`, `spec_hash`, `locked_at`, `proposed_by`) and,
  for each run shown in Evidence Lab (`first`, and `retest` if there was one): the run `record`,
  its `run_sha256`, the `review`, the worded `result` as shown on screen, `reviewed_at` and the
  `research_request`. Tests removed from the plan, and older runs of a test that was run again,
  are not in the file.

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

- Implement the four methods and give the engine its own `engine_id`. `Lab` (in
  `backend/app/lab.py`) holds one proposer (`self.engine`) and one reviewer (`self.reviewer`).
- A proposer must return tests in the locked-test shape above, with a machine-readable `rule` and
  `control.must` that the reviewer knows how to apply. A new kind of rule needs reviewer code too.
- A real reviewer must keep working from the stored run record alone, and must stay a different
  engine from the proposer.
- To answer research requests, an engine would read `research_requests` rows with status
  `waiting for research engine`. The table and screens for showing an answer do not exist yet.
