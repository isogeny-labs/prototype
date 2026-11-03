import type { Id, ISODate } from "./common";

export type IntegrityLevel = "imported" | "hashed" | "signed" | "cairn_verified";

export interface EvidenceRecord {
  id: Id;
  projectId: Id;
  runId: Id | null;
  integrity: IntegrityLevel;
  artifactRefs: Array<{ name: string; sha256: string; sizeBytes: number }>;
  manifestSha256: string;
  signer: { keyId: string; name: string } | null;
  verification: { verifiedAt: ISODate | null; result: "passed" | "failed" | "not_run"; checker: string | null; notes: string };
  createdAt: ISODate;
}
