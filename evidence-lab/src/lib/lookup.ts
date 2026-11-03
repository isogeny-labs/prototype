import type { Project, Run, TestDefinition, Artifact, ArtifactVersion, Check, EvidenceLabel } from "@/contracts";
import { computeEvidenceLabel } from "@/contracts";

const AGENT_NAMES: Record<string, string> = {
  "agent-autoresearcher": "Autoresearcher (simulated)",
  "agent-triage": "Triage agent (simulated)",
  "agent-conductor": "Conductor (simulated)",
  "agent-assistant": "Assistant (simulated)",
};

/** Name for a person id, agent id or free-text actor. */
export function actorName(project: Project | null | undefined, id: string): string {
  if (!id) return "—";
  const p = project?.people.find((x) => x.id === id);
  if (p) return p.name;
  return AGENT_NAMES[id] ?? id;
}
export function isAgentId(id: string): boolean { return id.startsWith("agent-"); }

export function byId<T extends { id: string }>(items: T[]): Record<string, T> {
  return Object.fromEntries(items.map((i) => [i.id, i]));
}

export function allVersions(artifacts: Artifact[]): Array<ArtifactVersion & { artifactName: string }> {
  return artifacts.flatMap((a) => a.versions.map((v) => ({ ...v, artifactName: a.name })));
}
export function versionLabel(artifacts: Artifact[], versionId: string): string {
  const v = allVersions(artifacts).find((x) => x.id === versionId);
  return v ? `${v.artifactName} ${v.version}` : versionId;
}
export function testName(tests: TestDefinition[], id: string): string { return tests.find((t) => t.id === id)?.name ?? id; }
export function runLabel(run: Run): string { return `Run #${run.sequence}`; }

/**
 * Label for a run. Checks that reference the run take precedence. Without any, a completed run on a
 * deterministic runner is itself a deterministic check (Machine-checked); imported results are Imported;
 * a simulated run proves nothing (Estimate); a run with no result yet has no label (null).
 */
export function runEvidenceLabel(run: Run, checks: Check[]): EvidenceLabel | null {
  const own = checks.filter((c) => c.runId === run.id);
  if (own.length > 0) return computeEvidenceLabel(own, { hasImportedEvidence: run.provenance === "imported" });
  if (run.status !== "completed") return null;
  if (run.executionMode === "imported" || run.provenance === "imported") return "Imported";
  if (run.executionMode === "simulated") return "Estimate";
  return "Machine-checked";
}

/** A run is superseded if any later run names it. */
export function supersededIds(runs: Run[]): Set<string> {
  return new Set(runs.map((r) => r.supersedesRunId).filter((x): x is string => Boolean(x)));
}
