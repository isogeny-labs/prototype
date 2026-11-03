import type { Id, ISODate } from "./common";

/** Organisational memory: scoped to one customer; never implies model training. */
export interface MemoryItem {
  id: Id;
  projectId: Id;
  customerScope: string;      // fictional customer name; memory never crosses customers
  kind: "accepted_finding" | "rejected_hypothesis" | "expert_correction" | "approved_configuration";
  text: string;
  sourceRef: { kind: "finding" | "proposal" | "approval" | "run"; id: Id };
  recordedAt: ISODate;
  recordedBy: string;
}

export interface AgentConfigChange {
  id: Id;
  projectId: Id;
  target: "instructions" | "tools" | "routing";
  agentName: string;
  proposedChange: string;
  rationale: string;
  evaluationStatus: "proposed" | "evaluating" | "evaluated_improved" | "evaluated_no_change" | "rejected" | "applied";
  approvalId: Id | null;
  createdAt: ISODate;
}

export interface ModelTrainingRecord {
  id: Id;
  status: "not_in_mvp";
  note: string;
}
