import type {
  AcceptanceCriteria, AgentConfigChange, Approval, Artifact, AuditEvent, Check, Comparison, EvidenceRecord, ExperimentProposal,
  ExternalChange, Finding, MemoryItem, ModelTrainingRecord, PackInfo, PackTemplate, Project, Recommendation, Run, Task, TestDefinition, AttackAssessment,
} from "@/contracts";

export interface Db {
  packs: PackInfo[];
  templates: PackTemplate[];
  projects: Project[];
  criteria: AcceptanceCriteria[];
  artifacts: Artifact[];
  tests: TestDefinition[];
  runs: Run[];
  checks: Check[];
  findings: Finding[];
  approvals: Approval[];
  proposals: ExperimentProposal[];
  tasks: Task[];
  evidence: EvidenceRecord[];
  recommendations: Recommendation[];
  externalChanges: ExternalChange[];
  comparisons: Comparison[];
  memory: MemoryItem[];
  agentConfigChanges: AgentConfigChange[];
  modelTraining: ModelTrainingRecord[];
  audit: AuditEvent[];
  attackAssessments: AttackAssessment[];
}


export function emptyDb(): Db {
  return { packs: [], templates: [], projects: [], criteria: [], artifacts: [], tests: [], runs: [], checks: [], findings: [], approvals: [],
    proposals: [], tasks: [], evidence: [], recommendations: [], externalChanges: [], comparisons: [], memory: [], agentConfigChanges: [],
    modelTraining: [], audit: [], attackAssessments: [] };
}
