import type { Id, PackId } from "./common";

export interface WorkspacePanel {
  id: string;            // e.g. "attack_assessment", "key_metrics"
  title: string;
  kind: "metrics" | "activity" | "next_actions" | "untested" | "disclaimer" | "pack_panel";
  packComponent?: string; // name of a pack-specific panel component, if kind === "pack_panel"
}

export interface WorkspaceControl {
  id: string;
  label: string;
  kind: "select" | "toggle" | "readonly";
  options?: string[];
  description?: string;
}

export interface ApprovalGate {
  id: string;
  subjectType: ApprovalSubjectType;
  description: string;
  requiredRole: string;
}

export type ApprovalSubjectType =
  | "acceptance_criteria" | "experiment_proposal" | "run_execution" | "recommendation"
  | "finding_resolution" | "artifact_import" | "agent_config_change" | "task_checkpoint" | "settings_change";

export interface PackTemplate {
  id: Id;
  packId: PackId;
  version: number;
  name: string;
  summary: string;
  supportedArtifactTypes: string[];
  supportedTestDefinitionIds: Id[];
  workspaceLayout: { panels: WorkspacePanel[]; controls: WorkspaceControl[] };
  evidenceRequirements: string[];
  approvalGates: ApprovalGate[];
  disclaimers: string[];   // shown wherever results appear
}

export interface PackInfo {
  id: PackId;
  name: string;
  tagline: string;
  status: "sample_available" | "coming_in_phase_2";
  templateIds: Id[];
}
