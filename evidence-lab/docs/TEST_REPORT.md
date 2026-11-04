# Test report

Run on 2026-11-04 on the development container (Chromium headless shell, Playwright 1.63.0) and reproduced by the GitHub Pages workflow on every push (see `.github/workflows/pages.yml`).

| Suite | Result |
|---|---|
| `npm run typecheck` (TypeScript strict) | pass |
| `npm test` (Vitest) | 44 passed (44) |
| `npm run test:e2e` (Playwright) | 63 passed (1.8m) |

## Spec section 10 coverage

| Acceptance item | Where | Result |
|---|---|---|
| Every route loads directly by URL for every sample project, no console errors | `tests/e2e/routes.spec.ts` (13 routes × 3 projects + run and finding detail) | pass |
| Navigation needs no prerequisites | `tests/e2e/acceptance.spec.ts` (fresh context opens Findings first) | pass |
| Sample consistency (unit): every referenced ID exists; runs reference valid artifact and criteria versions; engineering safety factors equal yield / stress to two decimals | `tests/unit/fixtures.test.ts` | pass |
| Approvals: approve, reject, request changes update status and history; self-approval blocked with a message; no 'Resolved' without a passing retest | `tests/e2e/phase3.spec.ts`, `tests/unit/mocks.test.ts` | pass |
| Failed runs: with failure injection the run detail shows the failure, logs and a retry path, no stale success data | `tests/e2e/phase3.spec.ts` | pass |
| Evidence comparison: crypto and engineering comparisons show the previously failing case, deltas and regressions | `tests/e2e/acceptance.spec.ts` | pass |
| Labels: a finding backed only by agreeing agent claims shows no Machine-checked or Expert-reviewed label | `tests/e2e/acceptance.spec.ts`, `tests/unit/fixtures.test.ts` | pass |
| The assistant refuses to change acceptance criteria and creates an approval request | `tests/e2e/phase3.spec.ts`, `tests/unit/mocks.test.ts`. **Note:** per the Phase 4 scope change the assistant now *drafts* a new criteria version as a card; nothing is created until the human confirms, after which the owner-approval request exists. Direct change is still refused. | pass (with that reading) |
| Reset-to-sample-data restores the original fixtures after edits | `tests/e2e/phase3.spec.ts`, `tests/unit/mocks.test.ts` | pass |
| Disclaimers appear on the engineering results, the legal rehearsal and the crypto results views | `tests/e2e/acceptance.spec.ts` | pass |
| No universal security score, secure badge, certified stamp or win probability | `tests/e2e/acceptance.spec.ts` (text scan of workspace, findings, reports, changes for all three projects) | pass |

## Known limitations of the tests

- The e2e suite runs against the production build served by `vite preview`, with mock latency 250 ms; it does not exercise a real backend.
- Layout checks run at 1280×900 and 1024×800 in Chromium only. CI fonts are wider than local ones; two earlier deployment runs failed on that until the header and engineering panels were made robust.
- The assistant is rule-based; tests cover its contract (no mutation on `send`, execution only on `confirm`, drafts for guarded requests), not natural-language breadth.
- Visual appearance is not snapshot-tested.

## Unit tests

- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > loads one sample project per pack 2ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > every project references an existing template at the stated version and its packData matches 1ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > every run points at a real artifact version, test definition and criteria version in its own project 5ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > unsupported and imported tests are never runnable and say why 0ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > findings reference real checks, runs and artifact versions, and history ends in the current status 1ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > checks carry the identity their kind requires 0ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > approvals reference real subjects; decided ones name a different reviewer who is a project member 2ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > proposals, tasks, comparisons, changes, evidence and attack assessments resolve their references 3ms
- ✓ tests/unit/fixtures.test.ts > fixture consistency (all three sample projects) > sample model labels never claim a real model, and nothing trains a model 1ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > uses 276 MPa yield 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #1: 276 / 162 = 1.7 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #2: 276 / 171 = 1.61 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #2: convergence changes are computed from the levels 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #3: 276 / 171 = 1.61 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #4: parametric sweep rows are consistent 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #5: 276 / 118 = 2.34 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #6: 276 / 118 = 2.34 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > run #6: convergence changes are computed from the levels 0ms
- ✓ tests/unit/fixtures.test.ts > engineering sample: safety factors equal yield divided by stress, to two decimals > the story numbers hold: 162 → 1.70, 171 → 1.61, 118 → 2.34 0ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > has authorities 0ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > Example Co. v. Sample Corp. (fictional authority) is labelled fictional 0ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > Placeholder Industries v. Specimen Logistics (fictional authority) is labelled fictional 0ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > Model Builders v. Illustrative Materials (fictional authority) is labelled fictional 0ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > every chronology event and argument node source resolves to a document page 1ms
- ✓ tests/unit/fixtures.test.ts > legal sample: authorities are obviously fictional and labelled > the planted date contradiction is at the referenced lines 0ms
- ✓ tests/unit/fixtures.test.ts > evidence label and status rules > labels across the three samples 0ms
- ✓ tests/unit/fixtures.test.ts > evidence label and status rules > two agreeing agent claims still yield Estimate 0ms
- ✓ tests/unit/fixtures.test.ts > evidence label and status rules > a model judgment alone is Model-reviewed; imported-only is Imported; nothing is Estimate 0ms
- ✓ tests/unit/fixtures.test.ts > evidence label and status rules > user-facing statuses follow the single mapping 0ms
- ✓ tests/unit/mocks.test.ts > approval rules in the mock > blocks self-approval and says why 2ms
- ✓ tests/unit/mocks.test.ts > approval rules in the mock > enforces the gate's role: an editor cannot decide, a reviewer can, and the record and subject update 8ms
- ✓ tests/unit/mocks.test.ts > approval rules in the mock > never overwrites a decision 6ms
- ✓ tests/unit/mocks.test.ts > approval rules in the mock > refuses to resolve a finding without a linked passing retest 3ms
- ✓ tests/unit/mocks.test.ts > approval rules in the mock > writes memory records from decisions and never a model-training record 21ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > never changes criteria, permissions or tests directly: it drafts, and nothing changes until confirmed 12ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > confirming the criteria draft proposes a new version for owner approval; the current version stays in force 9ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > summarises evidence and proposes next experiments and runs without executing anything 3ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > a confirmed run request creates a run awaiting approval, as the confirming user 7ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > orchestration and pending-approval advice respects roles: an editor gets 'open', a reviewer gets 'approve' 14ms
- ✓ tests/unit/mocks.test.ts > assistant rules in the mock > changes view configuration only, and audits it 5ms
- ✓ tests/unit/mocks.test.ts > developer state switcher > forceState reshapes copies without touching the store 2ms
- ✓ tests/unit/mocks.test.ts > developer state switcher > reads are forced, writes still apply to live data 7ms
- ✓ tests/unit/mocks.test.ts > failure injection and reset > fails the next named call once, then recovers 0ms
- ✓ tests/unit/mocks.test.ts > failure injection and reset > retry appends a new run that supersedes the failed one; reset restores the fixtures 4ms

## End-to-end tests

### tests/e2e/acceptance.spec.ts

- ✓ evidence comparison: the crypto and engineering comparisons show the previously failing case, the deltas and any regression
- ✓ navigation needs no prerequisites: opening Findings first works without visiting Intake
- ✓ labels: a finding backed only by agreeing agent claims shows no Machine-checked or Expert-reviewed label
- ✓ disclaimers appear on the engineering results, the legal rehearsal and the crypto results views
- ✓ no universal security score, secure badge, certified stamp or win probability anywhere in the three samples

### tests/e2e/phase3.spec.ts

- ✓ approvals › self-approval is blocked with a message; a reviewer's decision updates the subject
- ✓ approvals › a finding cannot be resolved without a linked passing retest
- ✓ approvals › roles are enforced: an editor cannot decide, the owner can; reject and request-changes record notes
- ✓ failed runs with failure injection show the failure, logs and a retry path, with no stale success data
- ✓ the assistant drafts instead of changing criteria, applies view changes, and executes only what a human confirms
- ✓ developer state switcher shows empty, loading, failed, awaiting-approval and completed states
- ✓ reports preview shows handoff and bundle with labels, limits and an unsigned manifest; export is simulated
- ✓ reset to sample data restores the original fixtures after edits (edits survive a reload until then)
- ✓ intake: proposing criteria creates a pending version and leaves the current one in force
- ✓ changes: reporting an external change and requesting a retest routes to approvals

### tests/e2e/routes.spec.ts

- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/artifacts
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/intake
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/tests
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/research
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/conductor
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/runs
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/findings
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/approvals
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/changes
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/reports
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/settings
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/memory
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200
- ✓ Acme Pay signing service: every route renders directly by URL › /p/proj-crypto-acme/runs/run-003 and /findings/fnd-001
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/intake
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/artifacts
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/tests
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/research
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/conductor
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/runs
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/findings
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/approvals
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/changes
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/reports
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/settings
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/memory
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind
- ✓ Mounting bracket MB-200: every route renders directly by URL › /p/proj-eng-mb200/runs/run-E-001 and /findings/fnd-E-001
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/intake
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/artifacts
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/tests
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/research
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/conductor
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/runs
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/findings
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/approvals
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/changes
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/reports
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/settings
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/memory
- ✓ home and sample-data settings render
- ✓ Northwind Supply v. Harbor Fabrication (fictional): every route renders directly by URL › /p/proj-legal-northwind/runs/run-L-001 and /findings/fnd-L-001
- ✓ the crypto story is visible end to end
- ✓ the engineering story is visible end to end
- ✓ the legal story is visible end to end, with fictional labels and no prediction
- ✓ logo or wordmark is present and the project switcher lists all sample projects
- ✓ nothing scrolls horizontally at 1024px wide

