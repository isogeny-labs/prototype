import type { AcceptanceCriteria, Approval, Artifact, AttackAssessment, AuditEvent, Check, Finding, PackTemplate, Project, Run, Task, TestDefinition } from "@/contracts";

/** Everything the workspace loads once; pack panels pick what they need. */
export interface WorkspaceData {
  criteria: AcceptanceCriteria[];
  runs: Run[];
  tests: TestDefinition[];
  artifacts: Artifact[];
  approvals: Approval[];
  tasks: Task[];
  audit: AuditEvent[];
  attacks: AttackAssessment[];
  findings: Finding[];
  checks: Check[];
}

export interface PackPanelProps {
  project: Project;
  template: PackTemplate;
  data: WorkspaceData;
}
