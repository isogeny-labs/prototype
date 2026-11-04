# Backend hook-up checklist

Status key: **Frontend complete** (UI done, needs real data) · **Mocked** (behaviour exists in the mock and must be
reproduced by the backend) · **Backend integration needed** (backend has it; wire it) · **New capability needed**
(nothing exists yet). "Owner must" says what the backend owner should connect, confirm or build.

## EvidenceLabService

| Method | Status | Owner must |
|---|---|---|
| `listProjects`, `getProject` | Backend integration needed | Map Project + ProjectMember; add `packId`, `templateId/Version`, `isSample`, `budget`, `executionMode`, `intakeQuestions`, `packData`. |
| `listCriteria`, `proposeCriteriaVersion` | Mocked | Store criteria as versions with `approvalId`; runs record `criteriaVersion`. Backend `Requirement` becomes an item of a version. |
| `listArtifacts`, `importArtifactVersion` | Backend integration needed | Map Implementation (baseline/candidate, parent_id, source_revision, configuration, build_identity) to Artifact + ArtifactVersion; add `kind`, `provenance`, `preview`. |
| `listTests` | Backend integration needed | Map Experiment (definition, acceptance_criteria) to TestDefinition; add `kind`, `runnable`, `unsupportedReason`, `resourceLimits`. Confirm the allowlisted fixture set. |
| `listRuns`, `getRun` | Backend integration needed | Append-only Run with provenance, environment, commands, metrics + definitions, failures, limitations, requirement_results → `criteriaResults`, supersedes/correction. Add `executionMode`, `status: awaiting_approval`. |
| `requestRun` | Mocked | Create a run in `awaiting_approval` with an `Approval(run_execution)`; execute only after approval. Confirm which tests need the gate (template `approvalGates`). |
| `retryRun` | Mocked | New run with `supersedesRunId` and `correctionNote`; never edit the failed run. |
| `listFindings`, `getFinding`, `listChecks` | Backend integration needed | Finding (origin, claims, status + history, evidence_run_ids); claims become `Check` records with kind, method, model/version or reviewer. Drop any hand-set confidence. |
| `listEvidence` | Backend integration needed | Artifact hashes + manifest → EvidenceRecord with `integrity` (hashed today), `signer: null`, verify-step result. |
| `listComparisons` | New capability needed | Baseline vs candidate run comparison: per-metric deltas, previously failing cases, regressions, remaining uncertainty. |
| `listRecommendations` | Backend integration needed | Map Recommendation; add `type` (supported_by_this_project / general_guidance / hypothesis), evidence links, limits, verification steps. |
| `listExternalChanges`, `reportExternalChange` | New capability needed | Record customer-reported changes with the new artifact version; set finding `externalChangeReported` / `revisedArtifactVersionId`. |
| `listAttackAssessments` | Backend integration needed | AttackAssessment categories A–D → the five panel kinds (`no_defensible_estimate` = no category). Crypto pack only. |
| `exportHandoff`, `exportEvidenceBundle` | Backend integration needed | Existing export is a SHA-256 manifest with verify step (unsigned). Return format, hash, size; signing is pending. |
| `listAudit` | Backend integration needed | AuditEvent (actor, action, subject, timestamp). Include assistant view changes, refusals and confirmed actions. |

## ApprovalService

| Method | Status | Owner must |
|---|---|---|
| `list` | Backend integration needed | Approval (subject_type, subject_id, decision, reviewer_id, note); add `requestedBy`, `requestedAt`, `decidedAt`, `rationale`. |
| `decide` | Mocked | Enforce: requester ≠ reviewer; gate role from the template (owner any, reviewer reviewer-gated); decisions never overwritten; `finding_resolution` requires a passing linked retest; apply subject consequences (criteria current version, protocol version, run queued, finding action_approved/closed, task checkpoint, agent config). Write memory records (accepted finding, rejected hypothesis, expert correction). |
| `request` | Mocked | Create pending approvals from the UI (finding resolution, settings change) and from the assistant on confirmation. |

## AutoresearcherService

| Method | Status | Owner must |
|---|---|---|
| `list`, `get` | Backend integration needed | SandboxExperiment (proposed/approved/rejected/executed/verified) → ExperimentProposal with the full protocol fields, `protocolVersion`, `protocolHistory`; `verified ↔ reviewed`. |
| `create` | Mocked (simulated proposal) | Autoresearcher has only run on cryptography. Generating proposals for engineering and legal packs is a **new capability**. |
| `review` | Mocked | Same rules as `ApprovalService.decide`; approval freezes a numbered protocol; amendments append. |
| `followUps` | Mocked | Return follow-up suggestions as text; each becomes a new proposal only when a human confirms. |

## ConductorService

| Method | Status | Owner must |
|---|---|---|
| `listTasks` | Backend integration needed | Conductor (Go) is in a separate repo and not connected. Map tasks with owner `{type: agent|tool|human, model?}`, dependencies, budget, checkpoint approval. |
| `pause`, `resume`, `cancel` | Mocked | Connect to Conductor controls; audit who did it. |

## PackRegistry

| Method | Status | Owner must |
|---|---|---|
| `listPacks`, `listTemplates`, `getTemplate` | Frontend complete (templates are versioned data in `src/fixtures/packs/`) | Serve templates from the backend or keep them as versioned data in the repo. Confirm versioning policy. |
| `checkCompatibility` | Mocked | Decide runnable / import_results / adapter_needed for a test and artifact version. |

## CairnService

| Method | Status | Owner must |
|---|---|---|
| `verify` | Mocked (never fabricates) | Cairn (Rust) is in a separate repo and not connected. Return `hashed` for manifest-only checks; return `cairn_verified` only from a real Cairn checker result; `signed` once signing exists. |

## AssistantService

| Method | Status | Owner must |
|---|---|---|
| `send` | Mocked (rule-based) | A connected assistant must keep: no project mutation; view-config changes audited; every action returned as a draft `AssistantSuggestedAction`; criteria / permissions / test definitions never changed directly (draft a version, a settings request, a proposal). Page context (`AssistantContext`) is sent with every message. |
| `confirm` | Mocked | Execute exactly one suggested action as the confirming user through the ordinary services; audit `assistant.action_confirmed` with the human actor. Never execute without a human confirmation. |

## LearningService

| Method | Status | Owner must |
|---|---|---|
| `listMemory` | New capability needed | Customer-scoped memory items written by decisions; never cross customers. |
| `listAgentConfigChanges` | New capability needed | Proposed changes to instructions / tools / routing with evaluation status and approval. |
| `listModelTraining` | Frontend complete | Always "not in MVP"; nothing retrains a model. |

## Cross-cutting

| Capability | Status | Owner must |
|---|---|---|
| Sign-in and roles | New capability needed | Replace the sample-mode acting-user switch with real identity; roles per project. |
| Session persistence | Frontend complete (per-tab convenience) | Replaced by backend state; remove or keep as cache. |
| Developer state switcher, latency and failure injection | Frontend complete (sample mode only) | Not for production; keep behind the sample-mode flag. |
| Customer-side runner, Docker runner | New capability needed / unvalidated | Both execution modes are shown as integration pending. |
| Engineering solver, legal document and citation code | New capability needed | Engineering and legal runs are `simulated` until these exist. |
| Signed evidence, Cairn checkpoints | New capability needed | Integrity levels above `hashed` are reserved. |
