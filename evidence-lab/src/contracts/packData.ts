import type { Id, PackId } from "./common";

/**
 * Pack-specific fields live here, discriminated by packId, so the core records stay domain-neutral.
 * Phase 1 fills the crypto variants; engineering and legal variants are sketched and completed in Phase 2.
 */

/** Crypto attack assessments. Backend AttackAssessment categories A|B|C|D map onto the first four kinds;
 *  "no_defensible_estimate" is the explicit absence of a category (backendCategory: null). */
export type AttackAssessmentCategory = "reproduced_weakness" | "measured_experiment" | "estimate_with_assumptions" | "published_estimate" | "no_defensible_estimate";

export interface AttackAssessment {
  id: Id;
  projectId: Id;
  packId: "crypto";
  category: AttackAssessmentCategory;
  backendCategory: "A" | "B" | "C" | "D" | null;
  attackModel: "classical" | "quantum";
  target: string;
  objective: string;
  method: string;
  source: string;
  assumptions: string[];
  expectedWork: string;     // text; "No defensible estimate available" where applicable
  uncertainty: string;
  linkedRunId: Id | null;
  reviewDate: string;
}

export type ProjectPackData =
  | { packId: "crypto"; algorithm: string; curveOrScheme: string; tokenFormat: string }
  | { packId: "engineering"; material: { name: string; yieldMpa: number }; loadCase: string; solverLabel: string; assumptions: string[] }
  | { packId: "legal"; matterType: string; jurisdictionLabel: string; privileged: boolean };

export type ArtifactPackData =
  | { packId: "crypto"; buildIdentity?: string; sourceRevision?: string; configuration?: Record<string, string> }
  | { packId: "engineering"; units?: string; meshLevel?: number }
  | { packId: "legal"; documentType: string; pageCount?: number; privileged?: boolean };

export type RunPackData =
  | { packId: "crypto"; vectorSource?: string }
  | { packId: "engineering"; solver: string; meshElements?: number; converged?: boolean }
  | { packId: "legal"; documentLocations?: Array<{ documentId: Id; page: number; line?: number }> };

export type FindingPackData =
  | { packId: "crypto"; attackAssessmentId?: Id }
  | { packId: "engineering"; locationOnPart?: string }
  | { packId: "legal"; disputedFact?: string; documentLocation?: { documentId: Id; page: number; line?: number } };

export type PackDataFor<P extends PackId, T> = Extract<T, { packId: P }>;
