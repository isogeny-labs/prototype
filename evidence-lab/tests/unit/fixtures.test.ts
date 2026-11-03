import { describe, it, expect } from "vitest";
import { emptyDb } from "@/store/db";
import { loadFixtures } from "@/fixtures";
import { computeEvidenceLabel, toUserFacingStatus, canResolve } from "@/contracts";

const db = loadFixtures(emptyDb());
const ids = <T extends { id: string }>(xs: T[]) => new Set(xs.map((x) => x.id));
const versionIds = new Set(db.artifacts.flatMap((a) => a.versions.map((v) => v.id)));
const runIds = ids(db.runs); const testIds = ids(db.tests); const checkIds = ids(db.checks); const approvalIds = ids(db.approvals);
const runsById = Object.fromEntries(db.runs.map((r) => [r.id, r]));

describe("fixture consistency", () => {
  it("every project references an existing template at the stated version", () => {
    for (const p of db.projects) {
      const t = db.templates.find((x) => x.id === p.templateId && x.version === p.templateVersion);
      expect(t, `${p.id} template`).toBeDefined();
      expect(t?.packId).toBe(p.packId);
      expect(p.isSample).toBe(true);
      for (const m of p.permissions.members) expect(p.people.some((x) => x.id === m.personId), `${m.personId} in people`).toBe(true);
      expect(db.criteria.some((c) => c.projectId === p.id && c.version === p.currentCriteriaVersion && c.approvalId), "current criteria approved").toBe(true);
    }
  });
  it("every run points at a real artifact version, test definition and criteria version", () => {
    for (const r of db.runs) {
      expect(versionIds.has(r.artifactVersionId), `${r.id} artifact version`).toBe(true);
      expect(testIds.has(r.testDefinitionId), `${r.id} test`).toBe(true);
      expect(db.criteria.some((c) => c.projectId === r.projectId && c.version === r.criteriaVersion), `${r.id} criteria v${r.criteriaVersion}`).toBe(true);
      if (r.supersedesRunId) expect(runIds.has(r.supersedesRunId), `${r.id} supersedes`).toBe(true);
      if (r.supersedesRunId) expect(r.correctionNote.length, `${r.id} correction note`).toBeGreaterThan(0);
      if (r.evidenceRecordId) expect(db.evidence.some((e) => e.id === r.evidenceRecordId && e.runId === r.id), `${r.id} evidence`).toBe(true);
      if (r.approvalId) expect(approvalIds.has(r.approvalId), `${r.id} approval`).toBe(true);
      for (const m of r.metrics) expect(m.definition.length, `${r.id} metric ${m.key} has a definition`).toBeGreaterThan(0);
      if (r.status === "completed") expect(r.evidenceRecordId, `${r.id} completed runs carry evidence`).not.toBeNull();
    }
    const seqs = db.runs.map((r) => r.sequence);
    expect(new Set(seqs).size).toBe(seqs.length);
  });
  it("unsupported tests are never runnable and say why", () => {
    for (const t of db.tests) {
      if (t.kind === "imported") expect(t.runnable).toBe(false);
      if (!t.runnable) expect(t.unsupportedReason?.length ?? 0).toBeGreaterThan(0);
    }
  });
  it("findings reference real checks, runs and artifact versions", () => {
    for (const f of db.findings) {
      for (const c of f.checkIds) expect(checkIds.has(c), `${f.id} check ${c}`).toBe(true);
      for (const r of [...f.evidenceRunIds, ...f.retestRunIds]) expect(runIds.has(r), `${f.id} run ${r}`).toBe(true);
      for (const v of f.artifactVersionIds) expect(versionIds.has(v), `${f.id} version ${v}`).toBe(true);
      if (f.recommendationId) expect(db.recommendations.some((x) => x.id === f.recommendationId)).toBe(true);
      if (f.revisedArtifactVersionId) expect(versionIds.has(f.revisedArtifactVersionId)).toBe(true);
      expect(f.statusHistory.at(-1)?.status).toBe(f.status);
    }
  });
  it("checks carry the identity their kind requires", () => {
    for (const c of db.checks) {
      if (c.kind === "model_judgment") expect(c.model, `${c.id} model`).toBeDefined();
      if (c.kind === "human_decision") expect(c.reviewer?.name.length ?? 0, `${c.id} reviewer`).toBeGreaterThan(0);
      if (c.runId) expect(runIds.has(c.runId)).toBe(true);
    }
  });
  it("approvals reference real subjects and decided ones name a different reviewer", () => {
    for (const a of db.approvals) {
      const exists = { acceptance_criteria: db.criteria, experiment_proposal: db.proposals, run_execution: db.runs, recommendation: db.recommendations, finding_resolution: db.findings, task_checkpoint: db.tasks, agent_config_change: db.agentConfigChanges, artifact_import: [], settings_change: [] }[a.subjectType] as Array<{ id: string }>;
      expect(exists.some((x) => x.id === a.subjectId), `${a.id} subject ${a.subjectId}`).toBe(true);
      if (a.decision !== "pending") { expect(a.reviewerId).not.toBeNull(); expect(a.reviewerId).not.toBe(a.requestedBy); expect(a.decidedAt).not.toBeNull(); }
    }
  });
  it("proposals, tasks, comparisons, changes and evidence resolve their references", () => {
    for (const p of db.proposals) { expect(versionIds.has(p.affectedArtifactVersionId)).toBe(true); for (const r of p.resultRunIds) expect(runIds.has(r)).toBe(true); for (const h of p.protocolHistory) expect(approvalIds.has(h.approvalId)).toBe(true); if (p.protocolVersion > 0) expect(p.protocolHistory.length).toBeGreaterThan(0); }
    const taskIds = ids(db.tasks);
    for (const t of db.tasks) { for (const d of t.dependsOn) expect(taskIds.has(d), `${t.id} depends ${d}`).toBe(true); if (t.checkpoint) expect(approvalIds.has(t.checkpoint.approvalId)).toBe(true); if (t.producesRunId) expect(runIds.has(t.producesRunId)).toBe(true); }
    for (const c of db.comparisons) { expect(runIds.has(c.baselineRunId)).toBe(true); expect(runIds.has(c.candidateRunId)).toBe(true); }
    for (const c of db.externalChanges) expect(versionIds.has(c.newArtifactVersionId)).toBe(true);
    for (const e of db.evidence) { expect(e.integrity).not.toBe("cairn_verified"); if (e.runId) expect(runIds.has(e.runId)).toBe(true); }
    for (const a of db.attackAssessments) {
      if (a.linkedRunId) expect(runIds.has(a.linkedRunId)).toBe(true);
      expect(a.packId).toBe("crypto");
      expect(a.backendCategory === null).toBe(a.category === "no_defensible_estimate");
      if (a.category === "no_defensible_estimate") expect(a.expectedWork).toMatch(/No defensible estimate/);
    }
    for (const p of db.projects) expect(p.packData.packId).toBe(p.packId);
  });
  it("sample model labels never claim a real model", () => {
    const labels = [...db.checks.map((c) => c.model?.name), ...db.proposals.map((p) => p.proposedBy.model), ...db.tasks.map((t) => t.owner.model)].filter(Boolean) as string[];
    for (const l of labels) expect(l).toMatch(/sample-model/);
    expect(db.modelTraining.every((m) => m.status === "not_in_mvp")).toBe(true);
  });
});

describe("evidence label and status rules on the crypto sample", () => {
  const f1 = db.findings.find((f) => f.id === "fnd-001")!; const f2 = db.findings.find((f) => f.id === "fnd-002")!; const f3 = db.findings.find((f) => f.id === "fnd-003")!;
  const checksOf = (f: typeof f1) => db.checks.filter((c) => f.checkIds.includes(c.id));
  it("fnd-001 is Expert-reviewed, fnd-002 is Estimate, fnd-003 is Machine-checked", () => {
    expect(computeEvidenceLabel(checksOf(f1))).toBe("Expert-reviewed");
    expect(computeEvidenceLabel(checksOf(f2))).toBe("Estimate");
    expect(computeEvidenceLabel(checksOf(f3))).toBe("Machine-checked");
  });
  it("two agreeing agent claims still yield Estimate", () => {
    const agree = checksOf(f2).map((c) => ({ ...c, result: "supports" as const }));
    expect(computeEvidenceLabel(agree)).toBe("Estimate");
  });
  it("a model judgment alone is Model-reviewed; imported-only is Imported; nothing is Estimate", () => {
    const mj = db.checks.find((c) => c.kind === "model_judgment")!;
    expect(computeEvidenceLabel([mj])).toBe("Model-reviewed");
    expect(computeEvidenceLabel([], { hasImportedEvidence: true })).toBe("Imported");
    expect(computeEvidenceLabel([])).toBe("Estimate");
  });
  it("user-facing statuses follow the single mapping", () => {
    expect(toUserFacingStatus(f1, runsById)).toBe("Resolved within tested scope");
    expect(toUserFacingStatus(f2, runsById)).toBe("Open");
    expect(toUserFacingStatus(f3, runsById)).toBe("Recommendation proposed");
    expect(canResolve(f1, runsById).ok).toBe(true);
    expect(canResolve(f2, runsById).ok).toBe(false);
  });
});
