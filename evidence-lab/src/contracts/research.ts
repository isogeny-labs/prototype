import type { Id, ISODate } from "./common";

export type ProposalStatus = "proposed" | "under_review" | "approved" | "rejected" | "executed" | "reviewed";

export interface ProposalOutcomes { success: string; failure: string; inconclusive: string }
export interface ProposalBudget { computeUnits: number; timeHours: number; moneyUsd: number }

export interface ExperimentProposal {
  id: Id;
  projectId: Id;
  title: string;
  researchQuestion: string;
  motivation: string;
  sourceReferences: Array<{ kind: "finding" | "run" | "document" | "literature"; id: Id; label: string }>;
  affectedArtifactVersionId: Id;
  hypothesis: string;            // falsifiable
  baselineAndControls: string;
  procedure: string;
  outcomes: ProposalOutcomes;
  budget: ProposalBudget;
  requiredArtifacts: string[];
  safetyBoundaries: string;
  wouldEstablish: string;
  wouldNotEstablish: string;
  status: ProposalStatus;
  protocolVersion: number;       // 0 until approved; approvals freeze a numbered version
  protocolHistory: Array<{ version: number; approvalId: Id; note: string; at: ISODate }>;
  proposedBy: { type: "agent" | "human"; name: string; model?: string };
  linkedTestDefinitionId: Id | null;
  resultRunIds: Id[];
  resultSummary: string;
  followUpSuggestions: string[];
  findingId: Id | null;
  createdAt: ISODate;
}
