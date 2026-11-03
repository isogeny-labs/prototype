import type { Id, ISODate } from "./common";

export type RecommendationType = "general_guidance" | "hypothesis" | "supported_by_this_project";
export type RecommendationStatus = "draft" | "under_review" | "approved" | "rejected" | "superseded";

export interface Recommendation {
  id: Id;
  projectId: Id;
  findingId: Id | null;
  title: string;
  type: RecommendationType;
  status: RecommendationStatus;
  observedIssue: string;
  supportingEvidence: Array<{ kind: "run" | "check" | "proposal"; id: Id; label: string }>;
  proposedChange: string;
  guidanceReference: string[];
  expectedBenefit: string;
  tradeOffs: string[];
  applicabilityLimits: string[];
  verificationSteps: string[];
  approvalId: Id | null;
  createdAt: ISODate;
}

export interface ExternalChange {
  id: Id;
  projectId: Id;
  recommendationId: Id | null;
  findingId: Id | null;
  reportedBy: Id;
  reportedAt: ISODate;
  description: string;
  newArtifactVersionId: Id;
}

export interface MetricDelta {
  key: string;
  definition: string;
  baseline: number | string | null;
  candidate: number | string | null;
  delta: number | null;
  deltaPercent: number | null;
  regression: boolean;
}

export interface Comparison {
  id: Id;
  projectId: Id;
  title: string;
  baselineRunId: Id;
  candidateRunId: Id;
  metricDeltas: MetricDelta[];
  previouslyFailingCases: Array<{ caseId: string; name: string; baselinePass: boolean; candidatePass: boolean }>;
  newRegressions: string[];
  remainingUncertainty: string[];
  comparisonLimits: string[];
}
