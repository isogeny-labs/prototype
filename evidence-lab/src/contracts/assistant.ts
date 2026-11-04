import type { Id, ISODate } from "./common";

/** View configuration: the only thing the assistant may change without a human confirming. */
export interface ViewConfig {
  panelOrder: string[];
  hiddenPanels: string[];
  filters: Record<string, string>;
  chosenTestIds: Id[];
}

/** Where the user is; the assistant tailors summaries and suggestions to the page. */
export type AssistantPage = "home" | "overview" | "intake" | "artifacts" | "tests" | "research" | "conductor" | "runs" | "run" | "findings" | "finding" | "approvals" | "changes" | "reports" | "settings" | "memory" | "other";
export interface AssistantContext { page: AssistantPage; entityId?: Id }

/**
 * An action the assistant proposes. It is a draft: nothing happens until a human confirms it in the UI,
 * and the confirmed action runs as that human (requestedBy / reviewerId is the acting user). Actions with
 * an approval gate still go through Approvals afterwards.
 */
export type AssistantActionKind =
  | "request_run" | "retry_run" | "create_proposal" | "review_proposal" | "decide_approval" | "request_resolution"
  | "propose_criteria" | "request_settings_change" | "pause_task" | "resume_task" | "cancel_task" | "navigate";

export interface AssistantSuggestedAction {
  id: Id;
  kind: AssistantActionKind;
  label: string;                      // button text, imperative
  why: string;                        // the evidence behind the suggestion, in one or two sentences
  params: Record<string, string | number | boolean | null | string[] | Array<Record<string, unknown>>>;
  gate: string | null;                // approval gate that follows, if any ("execution approval", "owner approval", …)
  href?: string;                      // for navigate
}

export interface AssistantMessage {
  id: Id;
  role: "user" | "assistant";
  text: string;
  at: ISODate;
  action?: { kind: "view_change"; summary: string } | { kind: "refused"; reason: string; approvalRequestId: Id | null } | { kind: "confirmed"; summary: string };
  suggestions?: AssistantSuggestedAction[];
  context?: AssistantContext;
}
