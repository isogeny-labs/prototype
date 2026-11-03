import type { Id, ISODate } from "./common";

export interface AuditEvent {
  id: Id;
  projectId: Id | null;
  actor: { type: "human" | "agent" | "tool" | "system"; name: string };
  action: string;
  subject: { type: string; id: Id | null; label: string };
  timestamp: ISODate;
  detail?: string;
}
