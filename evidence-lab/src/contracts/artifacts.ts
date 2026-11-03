import type { Id, ISODate, Provenance } from "./common";
import type { ArtifactPackData } from "./packData";

export type ArtifactKind =
  | "library" | "source_snapshot" | "configuration" | "test_vectors" | "test_results"
  | "geometry" | "material" | "load_case" | "measurement" | "solver_input"
  | "document" | "email_thread" | "brief" | "authority" | "other";

export interface Artifact {
  id: Id;
  projectId: Id;
  kind: ArtifactKind;
  name: string;
  description: string;
  versions: ArtifactVersion[];
}

export interface ArtifactVersion {
  id: Id;
  artifactId: Id;
  version: string;          // human version label, e.g. "1.4.2"
  parentVersionId: Id | null;
  sha256: string;
  provenance: Provenance;
  sizeBytes: number;
  preview: string;          // short text preview or description of contents
  importedAt: ISODate;
  importedBy: Id;
  notes?: string;
  seededDefect?: string;    // present only on sample artifacts carrying a planted, labelled defect
  packData?: ArtifactPackData;
}
