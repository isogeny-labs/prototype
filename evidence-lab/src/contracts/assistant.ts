import type { Id, ISODate } from "./common";

/** What the assistant may change: view configuration only. */
export interface ViewConfig {
  panelOrder: string[];
  hiddenPanels: string[];
  filters: Record<string, string>;
  chosenTestIds: Id[];
}

export interface AssistantMessage {
  id: Id;
  role: "user" | "assistant";
  text: string;
  at: ISODate;
  action?: { kind: "view_change"; summary: string } | { kind: "refused"; reason: string; approvalRequestId: Id | null };
}
