import type { Id, ISODate, PackId, Person } from "./common";
import type { ProjectPackData } from "./packData";

export type ExecutionModeSetting = "platform_sandbox" | "customer_side";
export type ProjectStatus = "intake" | "active" | "awaiting_decision" | "paused" | "closed";

export interface Budget {
  timeHours: { used: number; limit: number };
  computeUnits: { used: number; limit: number };   // abstract units; definition shown in UI
  moneyUsd: { used: number; limit: number };
}

export interface Permissions {
  members: Array<{ personId: Id; role: "owner" | "editor" | "reviewer" | "viewer" }>;
  confidentiality: "standard" | "confidential";
  notes?: string;
}

export interface AcceptanceCriteriaItem {
  id: Id;
  text: string;
  metric?: string;         // optional machine-checkable metric key
  operator?: "<=" | ">=" | "==" | "<" | ">";
  threshold?: number;
  unit?: string;
}

export interface AcceptanceCriteria {
  id: Id;
  projectId: Id;
  version: number;
  items: AcceptanceCriteriaItem[];
  approvalId: Id | null;    // null while a new version awaits approval
  createdAt: ISODate;
  createdBy: Id;
  supersedesVersion?: number;
}

export interface IntakeQuestion {
  id: Id;
  question: string;
  status: "open" | "answered" | "assumed";
  answer?: string;
  assumption?: string;     // explicit assumption used while the question is open
}

export interface Project {
  id: Id;
  packId: PackId;
  templateId: Id;
  templateVersion: number;
  name: string;
  goal: string;
  constraints: string[];
  currentCriteriaVersion: number;
  permissions: Permissions;
  budget: Budget;
  executionMode: ExecutionModeSetting;
  status: ProjectStatus;
  isSample: boolean;
  intakeQuestions: IntakeQuestion[];
  summary: string;          // one plain-language paragraph for the home page
  createdAt: ISODate;
  people: Person[];         // fictional people referenced by this project
  packData: ProjectPackData; // pack-specific fields, discriminated by packId
}
