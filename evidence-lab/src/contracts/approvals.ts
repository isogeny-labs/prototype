import type { Id, ISODate } from "./common";
import type { ApprovalSubjectType } from "./packs";

export type ApprovalDecision = "approved" | "rejected" | "changes_requested" | "pending";

export interface Approval {
  id: Id;
  projectId: Id;
  subjectType: ApprovalSubjectType;
  subjectId: Id;
  subjectLabel: string;
  requestedBy: Id;
  requestedAt: ISODate;
  decision: ApprovalDecision;
  reviewerId: Id | null;
  note: string;
  decidedAt: ISODate | null;
  rationale: string;           // why this needs a human
}
