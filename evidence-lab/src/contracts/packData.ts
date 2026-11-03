import type { Id, PackId } from "./common";

/**
 * Pack-specific fields live here, discriminated by packId, so the core records stay domain-neutral.
 * Templates decide which pack panels render them; the panels live in src/packs/<pack>/.
 */

/* ---------------- Cryptography ---------------- */

/** Backend AttackAssessment categories A|B|C|D map onto the first four kinds;
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

/* ---------------- Mechanical engineering ---------------- */

export interface EngineeringModelSetup {
  partName: string;
  material: { name: string; yieldMpa: number; youngsModulusGpa: number; poissonRatio: number; densityKgM3: number; source: string };
  loads: Array<{ id: string; description: string; magnitude: string; location: string }>;
  boundaryConditions: Array<{ id: string; description: string }>;
  solver: { label: string; elementType: string; assumptions: string[] };
  acceptance: { requiredSafetyFactor: number; basis: "yield"; convergenceCriterionPercent: number };
}
export interface ConvergenceLevel { level: number; elementSizeMm: number; elements: number; peakVonMisesMpa: number; changePercent: number | null }
/** Schematic stress regions for the 2D placeholder viewer; not geometry. */
export interface StressRegion { id: "plate" | "bolt_holes" | "fillet" | "arm_root" | "arm_mid" | "arm_tip"; label: string; vonMisesMpa: number }

/* ---------------- Legal ---------------- */

export interface DocumentLocation { artifactVersionId: Id; page: number; line?: number; label?: string }
export interface ChronologyEvent { id: string; date: string; title: string; detail: string; source: DocumentLocation; disputed: boolean }
export interface LegalAuthority {
  name: string;                                   // always obviously fictional
  fictionalLabel: "Sample authority, not a real case";
  court: string; year: number;
  proposition: string;                            // what it stands for, in the sample
  reliedOnInBrief: boolean;
  contrary: boolean;
}
export interface ArgumentNode {
  id: string;
  kind: "claim" | "fact" | "authority" | "counter" | "response";
  text: string;
  supports: string[];                             // ids of nodes this one supports (or answers, for responses)
  status: "supported" | "unsupported" | "disputed" | "revised" | "open";
  source?: DocumentLocation | { authorityArtifactVersionId: Id };
  note?: string;
}
export interface RehearsalItem { id: string; kind: "counterargument" | "question"; text: string; preparedResponse: string; source: { kind: "model_judgment"; model: string } }
export interface LegalCheckRow {
  id: string;
  kind: "fact_assertion" | "quotation" | "contrary_authority";
  assertion: string;
  assertionLocation: DocumentLocation;
  sourceLocation: DocumentLocation | null;
  result: "supported" | "unsupported" | "match" | "mismatch" | "found" | "none";
  detail?: string;
  diff?: { quoted: string; actual: string };
}

/* ---------------- Unions on the core records ---------------- */

export type ProjectPackData =
  | { packId: "crypto"; algorithm: string; curveOrScheme: string; tokenFormat: string }
  | { packId: "engineering"; modelSetup: EngineeringModelSetup }
  | { packId: "legal"; matterType: string; parties: { claimant: string; respondent: string }; jurisdictionLabel: string; privileged: boolean;
      chronology: ChronologyEvent[]; argumentMap: ArgumentNode[]; rehearsal: { disclaimer: string; items: RehearsalItem[] }; documentHandlingNote: string };

export type ArtifactPackData =
  | { packId: "crypto"; buildIdentity?: string; sourceRevision?: string; configuration?: Record<string, string> }
  | { packId: "engineering"; units?: string; filletMm?: number; massGrams?: number; format?: string }
  | { packId: "legal"; documentType: string; privileged?: boolean; pages?: Array<{ page: number; lines: string[] }>; authority?: LegalAuthority };

export type RunPackData =
  | { packId: "crypto"; vectorSource?: string }
  | { packId: "engineering"; solver: string; meshElements?: number; elementSizeMm?: number; peakLocation?: string; converged?: boolean | null;
      convergenceLevels?: ConvergenceLevel[]; convergenceCriterionPercent?: number; stressRegions?: StressRegion[];
      parametric?: Array<{ filletMm: number; peakVonMisesMpa: number; safetyFactor: number }> }
  | { packId: "legal"; rows?: LegalCheckRow[] };

export type FindingPackData =
  | { packId: "crypto"; attackAssessmentId?: Id }
  | { packId: "engineering"; locationOnPart?: string }
  | { packId: "legal"; disputedFact?: string; assertionLocation?: DocumentLocation; sourceLocation?: DocumentLocation; diff?: { quoted: string; actual: string } };

export type PackDataFor<P extends PackId, T> = Extract<T, { packId: P }>;
