import type { Id, ISODate, Owner } from "./common";

export type TaskStatus = "queued" | "running" | "blocked" | "awaiting_checkpoint" | "paused" | "cancelled" | "failed" | "done";

export interface Task {
  id: Id;
  projectId: Id;
  title: string;
  owner: Owner;
  dependsOn: Id[];
  status: TaskStatus;
  budget: { used: number; limit: number; unit: "compute_units" | "minutes" | "usd" };
  checkpoint: { approvalId: Id; label: string } | null;
  producesRunId?: Id;
  startedAt: ISODate | null;
  finishedAt: ISODate | null;
  note?: string;
}
