import type { Id, ISODate } from "./common";
import type { FindingPackData } from "./packData";

export type CheckKind = "agent_claim" | "deterministic" | "model_judgment" | "human_decision" | "reproduced";
export type CheckResult = "supports" | "refutes" | "inconclusive";

export interface Check {
  id: Id;
  runId?: Id;
  findingId?: Id;
  kind: CheckKind;
  method: string;              // what was done, in one sentence
  result: CheckResult;
  detail?: string;
  model?: { name: string; version: string };   // required when kind === "model_judgment"
  reviewer?: { personId: Id; name: string };    // required when kind === "human_decision"
  agent?: { id: Id; name: string };             // for agent_claim
  timestamp: ISODate;
  evidenceLinks: Array<{ kind: "run" | "artifact_version" | "document_location"; id: Id; label: string }>;
}

/** Backend lifecycle (existing prototype). */
export type FindingBackendStatus =
  | "new" | "triage" | "relevant" | "experiment_proposed" | "reviewed"
  | "action_approved" | "retested" | "closed" | "not_relevant";

/** User-facing states. */
export type FindingUserStatus =
  | "Open" | "Recommendation proposed" | "External change reported" | "Awaiting retest"
  | "Resolved within tested scope" | "Still failing" | "Inconclusive" | "Not relevant";

export interface FindingConflict {
  id: Id;
  between: Array<{ owner: string; claim: string; checkId?: Id }>;
  summary: string;
  resolved: boolean;
  investigationProposalId?: Id;
}

export interface StatusHistoryEntry {
  status: FindingBackendStatus;
  at: ISODate;
  by: string;
  note: string;
}

export interface Finding {
  id: Id;
  projectId: Id;
  statement: string;            // plain-language conclusion
  origin: "test_run" | "research" | "manual" | "deterministic_check";
  status: FindingBackendStatus;
  statusHistory: StatusHistoryEntry[];
  checkIds: Id[];
  evidenceRunIds: Id[];
  artifactVersionIds: Id[];
  assumptions: string[];
  limitations: string[];
  conflicts: FindingConflict[];
  recommendationId: Id | null;
  externalChangeReported: boolean;
  revisedArtifactVersionId: Id | null;
  retestRunIds: Id[];
  technicalDetail: string;      // one click below the plain conclusion
  isSeeded: boolean;            // planted sample defect
  packData?: FindingPackData;
}

export type EvidenceLabel = "Machine-checked" | "Model-reviewed" | "Expert-reviewed" | "Imported" | "Estimate";
