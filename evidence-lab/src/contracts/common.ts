/** Shared primitives. All timestamps are ISO-8601 strings in UTC. */
export type ISODate = string;
export type Id = string;

export type PackId = "crypto" | "engineering" | "legal";

export interface Person {
  id: Id;
  name: string;
  role: string;          // e.g. "Customer engineer", "Isogeny reviewer"
  org: string;           // fictional organisation
}

/** Who owns a task or produced a check. */
export interface Owner {
  type: "agent" | "tool" | "human";
  id: Id;
  name: string;
  model?: string;        // only for agents; a sample label, never a real deployment claim
}

export type Provenance = "user_reported" | "imported" | "detected" | "independently_tested";
