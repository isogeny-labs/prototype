# Integration contracts

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

## Services: methods, types, errors, mock behaviour

Types are the ones in `src/contracts/`. Every method returns a Promise and may reject with `ServiceError`.
Lists are unpaginated in the mock; a paginated backend can page behind the same signature (the UI never assumes a
maximum). Errors shown in the UI: `not_found` (empty state with a message), `forbidden` and `conflict` (inline
message next to the control that caused it), `network` / `injected` (ErrorState with retry), `validation` (inline).

### EvidenceLabService

| Method | Request | Response | Errors | Mock behaviour |
|---|---|---|---|---|
| `listProjects()` | — | `Project[]` | network | Sample projects. |
| `getProject(id)` | `Id` | `Project` | not_found | |
| `listCriteria(projectId)` | `Id` | `AcceptanceCriteria[]` (all versions) | | |
| `proposeCriteriaVersion(projectId, items, requestedBy)` | items: `AcceptanceCriteriaItem[]` | `{ criteria, approval }` | validation | Creates version N+1 with `approvalId: null` and a pending `acceptance_criteria` approval; the current version is untouched. |
| `listArtifacts(projectId)` | | `Artifact[]` with versions | | |
| `importArtifactVersion(projectId, artifactId, version)` | version without id | `ArtifactVersion` | not_found | Appends; never replaces. |
| `listTests(projectId)` | | `TestDefinition[]` for the project's pack | | |
| `listRuns(projectId)` / `getRun(projectId, runId)` | | `Run[]` ordered by sequence / `Run` | not_found | |
| `requestRun(projectId, { artifactVersionId, testDefinitionId, requestedBy })` | | `Run` with `status: awaiting_approval` | validation (test not runnable), not_found | Creates a pending `run_execution` approval; nothing executes. |
| `retryRun(projectId, runId, requestedBy)` | | new `Run` (`queued`, `supersedesRunId`) | not_found | |
| `listFindings` / `getFinding(projectId, findingId)` | | `Finding[]` / `{ finding, checks }` | not_found | |
| `listChecks(projectId)` | | `Check[]` referenced by findings or runs | | |
| `listEvidence(projectId)` | | `EvidenceRecord[]` | | Never `signed` or `cairn_verified` in sample data. |
| `listComparisons(projectId)` | | `Comparison[]` | | |
| `listRecommendations(projectId)` | | `Recommendation[]` | | |
| `listExternalChanges` / `reportExternalChange(projectId, change)` | change without id/reportedAt | `ExternalChange` | | Sets finding `externalChangeReported`, `revisedArtifactVersionId`, appends history. |
| `listAttackAssessments(projectId)` | | `AttackAssessment[]` (crypto pack data) | | |
| `exportHandoff` / `exportEvidenceBundle(projectId)` | | metadata (format, hash, size / members, `signed: false`) | | Simulated; no file. |
| `listAudit(projectId)` | | `AuditEvent[]` newest first | | |

### ApprovalService

| Method | Request | Response | Errors | Mock behaviour |
|---|---|---|---|---|
| `list(projectId)` | | `Approval[]` | | |
| `decide(projectId, approvalId, decision, reviewerId, note)` | decision ∈ approved / rejected / changes_requested | `Approval` | conflict (already decided; resolution without passing retest), forbidden (self-approval; role below the gate; not a member), not_found | Applies subject consequences and writes memory records. |
| `request(projectId, input)` | subjectType, subjectId, subjectLabel, requestedBy, rationale | `Approval` (pending) | | |

### AutoresearcherService

| Method | Request | Response | Errors | Mock behaviour |
|---|---|---|---|---|
| `list` / `get` | | `ExperimentProposal[]` / `ExperimentProposal` | not_found | |
| `create(projectId, { findingId, affectedArtifactVersionId, prompt })` | | `ExperimentProposal` (`proposed`, protocol v0) + pending `experiment_proposal` approval | | Simulated template text; proposer "Autoresearcher (simulated)", model "sample-model (no real model connected)". |
| `review(projectId, proposalId, decision, reviewerId, note)` | | `ExperimentProposal` | conflict (no pending approval), forbidden | Approval increments `protocolVersion` and appends `protocolHistory`. |
| `followUps(projectId, proposalId)` | | `string[]` | | |

### ConductorService

| Method | Response | Errors | Mock behaviour |
|---|---|---|---|
| `listTasks(projectId)` | `Task[]` | | |
| `pause` / `resume` / `cancel(projectId, taskId)` | `Task` | not_found | Sets status paused / queued / cancelled; audited. |

### PackRegistry

| Method | Response | Mock behaviour |
|---|---|---|
| `listPacks()` / `listTemplates(packId?)` / `getTemplate(id, version?)` | `PackInfo[]` / `PackTemplate[]` / `PackTemplate` | From `src/fixtures/packs/`. |
| `checkCompatibility(projectId, testId, artifactVersionId)` | `CompatibilityResult { compatible, reasons, path }` | imported → `import_results`; not runnable → `adapter_needed`; else `run`. |

### CairnService

| Method | Response | Mock behaviour |
|---|---|---|
| `verify(projectId, evidenceRecordId)` | `{ integrity, result, checker, notes }` | Returns `hashed` (or `imported`) unless the record is already `cairn_verified`; never fabricates. |

### AssistantService

| Method | Request | Response | Mock behaviour |
|---|---|---|---|
| `send(projectId, viewConfig, text, user, context)` | `AssistantContext { page, entityId? }` | `{ reply: AssistantMessage, viewConfig }`; reply may carry `suggestions: AssistantSuggestedAction[]` and `action: view_change | refused` | Rule-based: evidence summary, next experiments, orchestration, executions, research, pending approvals, findings; view commands; guarded requests become drafts. No project mutation. |
| `confirm(projectId, action, user)` | one `AssistantSuggestedAction` | `{ reply }` with `action: confirmed` | Executes through the ordinary services as the confirming user; audited as a human action. Errors from the underlying service (for example forbidden on self-approval) propagate. |

### LearningService

| Method | Response | Mock behaviour |
|---|---|---|
| `listMemory(projectId)` | `MemoryItem[]` | Customer-scoped; written by decisions. |
| `listAgentConfigChanges(projectId)` | `AgentConfigChange[]` | |
| `listModelTraining()` | `ModelTrainingRecord[]` | Always `not_in_mvp`. |
