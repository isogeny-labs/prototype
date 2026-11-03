import type {
  AgentConfigChange, Approval, ApprovalDecision, Artifact, ArtifactVersion, AssistantMessage, AuditEvent, Check, Comparison,
  CompatibilityResult, EvidenceRecord, ExperimentProposal, ExternalChange, Finding, Id, IntegrityLevel, MemoryItem, ModelTrainingRecord,
  PackInfo, PackTemplate, Project, Recommendation, Run, Task, TestDefinition, ViewConfig, AcceptanceCriteria, AttackAssessment,
} from "@/contracts";

/** Every service call can fail; UI must render loading and failed states. */
export class ServiceError extends Error {
  constructor(message: string, public readonly code: "network" | "not_found" | "forbidden" | "conflict" | "validation" | "injected") {
    super(message);
  }
}

export interface EvidenceLabService {
  listProjects(): Promise<Project[]>;
  getProject(id: Id): Promise<Project>;
  listCriteria(projectId: Id): Promise<AcceptanceCriteria[]>;
  proposeCriteriaVersion(projectId: Id, items: AcceptanceCriteria["items"], requestedBy: Id): Promise<{ criteria: AcceptanceCriteria; approval: Approval }>;
  listArtifacts(projectId: Id): Promise<Artifact[]>;
  importArtifactVersion(projectId: Id, artifactId: Id, version: Omit<ArtifactVersion, "id" | "artifactId">): Promise<ArtifactVersion>;
  listTests(projectId: Id): Promise<TestDefinition[]>;
  listRuns(projectId: Id): Promise<Run[]>;
  getRun(projectId: Id, runId: Id): Promise<Run>;
  requestRun(projectId: Id, input: { artifactVersionId: Id; testDefinitionId: Id; requestedBy: Id }): Promise<Run>;
  retryRun(projectId: Id, runId: Id, requestedBy: Id): Promise<Run>;
  listFindings(projectId: Id): Promise<Finding[]>;
  getFinding(projectId: Id, findingId: Id): Promise<{ finding: Finding; checks: Check[] }>;
  listChecks(projectId: Id): Promise<Check[]>;
  listEvidence(projectId: Id): Promise<EvidenceRecord[]>;
  listComparisons(projectId: Id): Promise<Comparison[]>;
  listRecommendations(projectId: Id): Promise<Recommendation[]>;
  listExternalChanges(projectId: Id): Promise<ExternalChange[]>;
  reportExternalChange(projectId: Id, change: Omit<ExternalChange, "id" | "reportedAt">): Promise<ExternalChange>;
  listAttackAssessments(projectId: Id): Promise<AttackAssessment[]>;
  exportHandoff(projectId: Id): Promise<{ format: string; generatedAt: string; sha256: string; sizeBytes: number; note: string }>;
  exportEvidenceBundle(projectId: Id): Promise<{ format: string; generatedAt: string; manifestSha256: string; members: number; signed: false; note: string }>;
  listAudit(projectId: Id): Promise<AuditEvent[]>;
}

export interface ApprovalService {
  list(projectId: Id): Promise<Approval[]>;
  decide(projectId: Id, approvalId: Id, decision: Exclude<ApprovalDecision, "pending">, reviewerId: Id, note: string): Promise<Approval>;
  request(projectId: Id, input: Omit<Approval, "id" | "requestedAt" | "decision" | "reviewerId" | "decidedAt" | "note">): Promise<Approval>;
}

export interface AutoresearcherService {
  list(projectId: Id): Promise<ExperimentProposal[]>;
  get(projectId: Id, proposalId: Id): Promise<ExperimentProposal>;
  create(projectId: Id, input: { findingId: Id | null; affectedArtifactVersionId: Id; prompt: string }): Promise<ExperimentProposal>; // simulated
  review(projectId: Id, proposalId: Id, decision: "approved" | "rejected" | "changes_requested", reviewerId: Id, note: string): Promise<ExperimentProposal>;
  followUps(projectId: Id, proposalId: Id): Promise<string[]>;
}

export interface ConductorService {
  listTasks(projectId: Id): Promise<Task[]>;
  pause(projectId: Id, taskId: Id): Promise<Task>;
  resume(projectId: Id, taskId: Id): Promise<Task>;
  cancel(projectId: Id, taskId: Id): Promise<Task>;
}

export interface PackRegistry {
  listPacks(): Promise<PackInfo[]>;
  listTemplates(packId?: Id): Promise<PackTemplate[]>;
  getTemplate(templateId: Id, version?: number): Promise<PackTemplate>;
  checkCompatibility(projectId: Id, testDefinitionId: Id, artifactVersionId: Id): Promise<CompatibilityResult>;
}

export interface CairnService {
  verify(projectId: Id, evidenceRecordId: Id): Promise<{ integrity: IntegrityLevel; result: "passed" | "failed" | "not_run"; checker: string | null; notes: string }>;
}

export interface AssistantService {
  send(projectId: Id, viewConfig: ViewConfig, text: string, user: { id: Id; name: string }): Promise<{ reply: AssistantMessage; viewConfig: ViewConfig }>;
}

export interface LearningService {
  listMemory(projectId: Id): Promise<MemoryItem[]>;
  listAgentConfigChanges(projectId: Id): Promise<AgentConfigChange[]>;
  listModelTraining(): Promise<ModelTrainingRecord[]>;
}

export interface Services {
  evidenceLab: EvidenceLabService;
  approvals: ApprovalService;
  autoresearcher: AutoresearcherService;
  conductor: ConductorService;
  packs: PackRegistry;
  cairn: CairnService;
  assistant: AssistantService;
  learning: LearningService;
}
