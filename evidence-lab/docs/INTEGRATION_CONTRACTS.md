# Integration contracts (Phase 1 draft; completed in Phase 4)

The frontend talks to the world only through the interfaces in `src/services/types.ts`:
`EvidenceLabService`, `ApprovalService`, `AutoresearcherService`, `ConductorService`, `PackRegistry`,
`CairnService`, `AssistantService`, `LearningService`. Mock implementations live in `src/services/mock/`.
`src/services/index.ts` picks the implementation from `VITE_SERVICES_IMPL` (`mock` today; add `http`).

Every method is async and may reject with `ServiceError(message, code)` where
`code ∈ network | not_found | forbidden | conflict | validation | injected`. The UI renders loading, failed
(with retry) and empty states for every call. Mocks apply configurable latency and failure injection.

Domain types are in `src/contracts/`. Core records are domain-neutral; pack-specific fields sit in a
`packData` field discriminated by `packId` (`src/contracts/packData.ts`). Two rules are pure functions and
must stay in one place:

- `computeEvidenceLabel(checks, { hasImportedEvidence })` → `Expert-reviewed` if any `human_decision` check names a
  reviewer; else `Machine-checked` if any `deterministic` or `reproduced` check; else `Model-reviewed` if any
  `model_judgment`; else `Imported` if imported evidence; else `Estimate`. Agent claims never raise it.
- `toUserFacingStatus(finding, runsById)` maps the backend lifecycle to the user-facing states (table below).

## Mapping notes

How the existing backend records (FastAPI + SQLite prototype, names as given by the backend owner) map onto
the shared contract, and which crypto-specific fields were generalised.

| Backend record / field | Shared contract | Note |
|---|---|---|
| `Project` | `Project` | Adds `packId`, `templateId` + `templateVersion`, `isSample`, `budget`, `executionMode`, `intakeQuestions`, `packData`. |
| `ProjectMember (role)` | `Project.permissions.members[{personId, role}]` | Roles: owner / editor / reviewer / viewer. |
| `Requirement` | `AcceptanceCriteriaItem` inside a versioned `AcceptanceCriteria` | Requirements become items of a criteria *version* with its own `approvalId`; every run records `criteriaVersion`. |
| `Implementation (baseline\|candidate, parent_id, source_revision, configuration, build_identity)` | `Artifact{kind}` + `ArtifactVersion{version, parentVersionId, sha256, provenance}` with `packData{packId:'crypto', buildIdentity, sourceRevision, configuration}` | baseline/candidate is expressed by the version chain (`parentVersionId`) and by which run is the comparison baseline. `kind` covers crypto, engineering and legal inputs. |
| `Experiment (definition, acceptance_criteria)` | `TestDefinition{kind, inputs, acceptanceRule, runner, resourceLimits, runnable, unsupportedReason, version}` | `runnable` and `unsupportedReason` are new; unsupported tests are never shown as runnable. |
| `Run` (append-only) | `Run` (append-only) | Same discipline: `supersedesRunId` + `correctionNote`, never edits. |
| `Run.provenance measured\|imported\|illustrative` | `Run.provenance` (same values) | |
| `Run` runner / fixture versions, `environment`, `commands`, `repeat_count` | `Run.toolVersions`, `Run.environment`, `Run.commands`, `Run.repeatCount` | `parameters` and `seeds` are split out so the UI can show reproducibility fields separately. |
| `Run.metrics` + `Run.metric_definitions` | `Run.metrics: MetricValue[]` with `definition` on each value | No number renders without its definition. |
| `Run.failures`, `Run.limitations` | same | |
| `Run.artifact_hashes` | `EvidenceRecord.artifactRefs[{name, sha256, sizeBytes}]` | Hashes move to the evidence record with the manifest hash. |
| `Run.requirement_results` | `Run.criteriaResults[{criteriaItemId, observed, pass, note}]` | |
| run status `pending/running/done/error` | `queued / running / awaiting_approval / completed / failed` | `awaiting_approval` is new (execution gate). |
| `Artifact (sha256)` (run outputs) | `EvidenceRecord{integrity, artifactRefs, manifestSha256, signer, verification}` | `integrity ∈ imported \| hashed \| signed \| cairn_verified`. Today's export is an unsigned manifest → `hashed`. Never set `cairn_verified` without a Cairn result. |
| `Recommendation` (crypto migration kinds) | `Recommendation{type: general_guidance \| hypothesis \| supported_by_this_project, …}` | Migration kinds generalise to the claim type plus free-text `proposedChange` and `guidanceReference`. |
| `Approval (subject_type, subject_id, decision, reviewer_id, note)` | `Approval` (same fields plus `requestedBy`, `requestedAt`, `decidedAt`, `rationale`) | Subjects reference their decision record by `approvalId`; nothing flips a boolean. Self-approval is refused (`forbidden`). |
| `ResearchSource` (content is untrusted data) | `ExperimentProposal.sourceReferences[{kind, id, label}]` | Only references and labels are carried; source content is never rendered as instructions. |
| `Finding (origin; claims; status + status_history; evidence_run_ids)` | `Finding{origin, checkIds, status, statusHistory, evidenceRunIds, conflicts, …}` | *claims* become `Check` records (`agent_claim \| deterministic \| model_judgment \| human_decision \| reproduced`); any hand-set confidence or label is dropped. |
| finding lifecycle | `FindingBackendStatus` → `FindingUserStatus` | `new/triage/relevant/experiment_proposed → Open`; `reviewed → Recommendation proposed`; `action_approved → External change reported` (or `Awaiting retest` once a change is reported); `retested → Resolved within tested scope / Still failing / Inconclusive` from the latest linked retest; `closed → Resolved within tested scope`; `not_relevant → Not relevant`. Guards: `action_approved` needs an approved recommendation, `retested` a linked run, `closed` a passing latest retest (`canResolve`). |
| `AttackAssessment (categories A\|B\|C\|D)` | `AttackAssessment{category, backendCategory}` as **crypto pack data** | A = reproduced weakness, B = measured experiment, C = estimate with stated assumptions, D = published estimate; `no_defensible_estimate` has `backendCategory: null`. |
| `SandboxExperiment (proposed\|approved\|rejected\|executed\|verified)` | `ExperimentProposal.status (proposed \| under_review \| approved \| rejected \| executed \| reviewed)` + `protocolVersion`, `protocolHistory` | `verified ↔ reviewed`. Approvals freeze a numbered protocol version; amendments append. |
| `Job` | `Task` (Conductor) and `Run.status` | Jobs that execute tests surface as runs; orchestration jobs as tasks with owner, dependencies, budget, checkpoint. |
| `AuditEvent (actor, action, subject, timestamp)` | `AuditEvent` (same) | Assistant view changes and refusals are audited. |
| "cryptographic facts" inventory | not a core type | Pack data for crypto (`ProjectPackData{algorithm, curveOrScheme, tokenFormat}`); engineering/legal variants are sketched in `packData.ts`. |
| execution target (sandbox / customer-side runner) | `Project.executionMode` and `Run.executionMode (platform_sandbox \| customer_side \| imported \| simulated)` | `simulated` exists only in sample data. |

Phase 4 completes this document with request/response shapes per method, error semantics and pagination.
