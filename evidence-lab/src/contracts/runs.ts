import type { Id, ISODate } from "./common";
import type { RunPackData } from "./packData";

export type RunExecutionMode = "platform_sandbox" | "customer_side" | "imported" | "simulated";
export type RunProvenance = "measured" | "imported" | "illustrative";
export type RunStatus = "queued" | "running" | "failed" | "awaiting_approval" | "completed";

export interface MetricValue {
  key: string;
  value: number | string | boolean | null;
  unit?: string;
  definition: string;         // how it was measured; required so no number is shown without one
}

export interface RunCase {
  id: string;
  name: string;
  expected: string;
  observed: string;
  pass: boolean;
  detail?: string;
}

export interface RunLogLine {
  t: ISODate;
  level: "info" | "warn" | "error";
  text: string;
}

export interface Run {
  id: Id;
  projectId: Id;
  sequence: number;
  artifactVersionId: Id;
  testDefinitionId: Id;
  criteriaVersion: number;
  executionMode: RunExecutionMode;
  provenance: RunProvenance;
  status: RunStatus;
  environment: Record<string, string>;
  toolVersions: Record<string, string>;   // runner, fixture, solver, model versions
  commands: string[];          // exact commands the runner executed (empty for imported / simulated)
  parameters: Record<string, string | number | boolean>;
  seeds: Record<string, number | string>;
  repeatCount: number;
  logs: RunLogLine[];
  metrics: MetricValue[];
  cases: RunCase[];
  failures: string[];
  limitations: string[];
  criteriaResults: Array<{ criteriaItemId: Id; observed: number | string | null; pass: boolean | null; note?: string }>;
  overallPass: boolean | null;
  supersedesRunId: Id | null;
  correctionNote: string;
  evidenceRecordId: Id | null;
  requestedBy: Id;
  approvalId: Id | null;     // execution approval, where the gate applies
  startedAt: ISODate | null;
  finishedAt: ISODate | null;
  createdAt: ISODate;
  packData?: RunPackData;
}
