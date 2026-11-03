import { describe, it, expect } from "vitest";
import { emptyDb } from "@/store/db";
import { loadFixtures } from "@/fixtures";
import { computeEvidenceLabel, toUserFacingStatus, canResolve } from "@/contracts";

const db = loadFixtures(emptyDb());
const ids = <T extends { id: string }>(xs: T[]) => new Set(xs.map((x) => x.id));
const versionIds = new Set(db.artifacts.flatMap((a) => a.versions.map((v) => v.id)));
const runIds = ids(db.runs); const testIds = ids(db.tests); const checkIds = ids(db.checks); const approvalIds = ids(db.approvals);
const runsById = Object.fromEntries(db.runs.map((r) => [r.id, r]));
const find = <T extends { id: string }>(xs: T[], id: string): T => { const x = xs.find((y) => y.id === id); if (!x) throw new Error(`missing ${id}`); return x; };

describe("fixture consistency (all three sample projects)", () => {
  it("loads one sample project per pack", () => {
    expect(db.projects.map((p) => p.packId).sort()).toEqual(["crypto", "engineering", "legal"]);
    expect(db.packs.every((p) => p.status === "sample_available")).toBe(true);
  });
  it("every project references an existing template at the stated version and its packData matches", () => {
    for (const p of db.projects) {
      const t = db.templates.find((x) => x.id === p.templateId && x.version === p.templateVersion);
      expect(t, `${p.id} template`).toBeDefined();
      expect(t?.packId).toBe(p.packId);
      expect(p.isSample).toBe(true);
      expect(p.packData.packId).toBe(p.packId);
      for (const m of p.permissions.members) expect(p.people.some((x) => x.id === m.personId), `${m.personId} in people`).toBe(true);
      expect(db.criteria.some((c) => c.projectId === p.id && c.version === p.currentCriteriaVersion && c.approvalId), "current criteria approved").toBe(true);
    }
  });
  it("every run points at a real artifact version, test definition and criteria version in its own project", () => {
    for (const r of db.runs) {
      const art = db.artifacts.find((a) => a.versions.some((v) => v.id === r.artifactVersionId));
      expect(art?.projectId, `${r.id} artifact project`).toBe(r.projectId);
      const t = db.tests.find((x) => x.id === r.testDefinitionId);
      expect(t, `${r.id} test`).toBeDefined();
      expect(t?.packId).toBe(find(db.projects, r.projectId).packId);
      expect(db.criteria.some((c) => c.projectId === r.projectId && c.version === r.criteriaVersion), `${r.id} criteria v${r.criteriaVersion}`).toBe(true);
      if (r.supersedesRunId) { expect(runIds.has(r.supersedesRunId), `${r.id} supersedes`).toBe(true); expect(r.correctionNote.length).toBeGreaterThan(0); }
      if (r.evidenceRecordId) expect(db.evidence.some((e) => e.id === r.evidenceRecordId && e.runId === r.id), `${r.id} evidence`).toBe(true);
      if (r.approvalId) expect(approvalIds.has(r.approvalId), `${r.id} approval`).toBe(true);
      for (const m of r.metrics) expect(m.definition.length, `${r.id} metric ${m.key} has a definition`).toBeGreaterThan(0);
      if (r.status === "completed") expect(r.evidenceRecordId, `${r.id} completed runs carry evidence`).not.toBeNull();
      if (r.packData) expect(r.packData.packId).toBe(find(db.projects, r.projectId).packId);
      if (r.executionMode === "imported") expect(r.provenance).toBe("imported");
    }
    for (const p of db.projects) { const seqs = db.runs.filter((r) => r.projectId === p.id).map((r) => r.sequence); expect(new Set(seqs).size, `${p.id} sequences unique`).toBe(seqs.length); }
  });
  it("unsupported and imported tests are never runnable and say why", () => {
    for (const t of db.tests) {
      if (t.kind === "imported") expect(t.runnable).toBe(false);
      if (!t.runnable) expect(t.unsupportedReason?.length ?? 0).toBeGreaterThan(0);
    }
    expect(testIds.size).toBe(db.tests.length);
  });
  it("findings reference real checks, runs and artifact versions, and history ends in the current status", () => {
    for (const f of db.findings) {
      for (const c of f.checkIds) expect(checkIds.has(c), `${f.id} check ${c}`).toBe(true);
      for (const r of [...f.evidenceRunIds, ...f.retestRunIds]) expect(runsById[r]?.projectId, `${f.id} run ${r}`).toBe(f.projectId);
      for (const v of f.artifactVersionIds) expect(versionIds.has(v), `${f.id} version ${v}`).toBe(true);
      if (f.recommendationId) expect(db.recommendations.some((x) => x.id === f.recommendationId)).toBe(true);
      if (f.revisedArtifactVersionId) expect(versionIds.has(f.revisedArtifactVersionId)).toBe(true);
      expect(f.statusHistory.at(-1)?.status).toBe(f.status);
      if (f.status === "closed" || f.status === "retested") expect(f.retestRunIds.length, `${f.id} has retests`).toBeGreaterThan(0);
    }
  });
  it("checks carry the identity their kind requires", () => {
    for (const c of db.checks) {
      if (c.kind === "model_judgment") expect(c.model, `${c.id} model`).toBeDefined();
      if (c.kind === "human_decision") expect(c.reviewer?.name.length ?? 0, `${c.id} reviewer`).toBeGreaterThan(0);
      if (c.runId) expect(runIds.has(c.runId)).toBe(true);
    }
  });
  it("approvals reference real subjects; decided ones name a different reviewer who is a project member", () => {
    for (const a of db.approvals) {
      const exists = { acceptance_criteria: db.criteria, experiment_proposal: db.proposals, run_execution: db.runs, recommendation: db.recommendations, finding_resolution: db.findings, task_checkpoint: db.tasks, agent_config_change: db.agentConfigChanges, artifact_import: [], settings_change: db.projects }[a.subjectType] as Array<{ id: string }>;
      expect(exists.some((x) => x.id === a.subjectId), `${a.id} subject ${a.subjectId}`).toBe(true);
      if (a.decision !== "pending") {
        expect(a.reviewerId).not.toBeNull(); expect(a.reviewerId).not.toBe(a.requestedBy); expect(a.decidedAt).not.toBeNull();
        const p = find(db.projects, a.projectId);
        expect(p.permissions.members.some((m) => m.personId === a.reviewerId), `${a.id} reviewer is a member`).toBe(true);
      }
    }
  });
  it("proposals, tasks, comparisons, changes, evidence and attack assessments resolve their references", () => {
    for (const p of db.proposals) { expect(versionIds.has(p.affectedArtifactVersionId)).toBe(true); for (const r of p.resultRunIds) expect(runIds.has(r)).toBe(true); for (const h of p.protocolHistory) expect(approvalIds.has(h.approvalId)).toBe(true); if (p.protocolVersion > 0) expect(p.protocolHistory.length).toBeGreaterThan(0); if (p.linkedTestDefinitionId) expect(testIds.has(p.linkedTestDefinitionId)).toBe(true); }
    const taskIds = ids(db.tasks);
    for (const t of db.tasks) { for (const d of t.dependsOn) expect(taskIds.has(d), `${t.id} depends ${d}`).toBe(true); if (t.checkpoint) expect(approvalIds.has(t.checkpoint.approvalId)).toBe(true); if (t.producesRunId) expect(runIds.has(t.producesRunId)).toBe(true); }
    for (const c of db.comparisons) { expect(runsById[c.baselineRunId]?.projectId).toBe(c.projectId); expect(runsById[c.candidateRunId]?.projectId).toBe(c.projectId); }
    for (const c of db.externalChanges) expect(versionIds.has(c.newArtifactVersionId)).toBe(true);
    for (const e of db.evidence) { expect(e.integrity).not.toBe("cairn_verified"); expect(e.integrity).not.toBe("signed"); if (e.runId) expect(runIds.has(e.runId)).toBe(true); }
    for (const a of db.attackAssessments) { if (a.linkedRunId) expect(runIds.has(a.linkedRunId)).toBe(true); expect(a.packId).toBe("crypto"); expect(a.backendCategory === null).toBe(a.category === "no_defensible_estimate"); if (a.category === "no_defensible_estimate") expect(a.expectedWork).toMatch(/No defensible estimate/); }
    for (const m of db.memory) expect(db.projects.some((p) => p.id === m.projectId)).toBe(true);
  });
  it("sample model labels never claim a real model, and nothing trains a model", () => {
    const labels = [...db.checks.map((c) => c.model?.name), ...db.proposals.map((p) => p.proposedBy.model), ...db.tasks.map((t) => t.owner.model)].filter(Boolean) as string[];
    for (const l of labels) expect(l).toMatch(/sample-model/);
    expect(db.modelTraining.every((m) => m.status === "not_in_mvp")).toBe(true);
  });
});

describe("engineering sample: safety factors equal yield divided by stress, to two decimals", () => {
  const eng = find(db.projects, "proj-eng-mb200");
  const yieldMpa = eng.packData.packId === "engineering" ? eng.packData.modelSetup.material.yieldMpa : NaN;
  it("uses 276 MPa yield", () => { expect(yieldMpa).toBe(276); });
  for (const r of db.runs.filter((x) => x.projectId === "proj-eng-mb200")) {
    const sf = r.metrics.find((m) => m.key === "safety_factor");
    const peak = r.metrics.find((m) => m.key === "peak_von_mises_mpa" || m.key === "peak_von_mises_refined_mpa");
    if (sf && peak) it(`run #${r.sequence}: ${yieldMpa} / ${String(peak.value)} = ${String(sf.value)}`, () => {
      expect(Number(sf.value)).toBe(Number((yieldMpa / Number(peak.value)).toFixed(2)));
    });
    if (r.packData?.packId === "engineering" && r.packData.parametric) it(`run #${r.sequence}: parametric sweep rows are consistent`, () => {
      for (const row of r.packData!.packId === "engineering" ? r.packData!.parametric ?? [] : []) expect(row.safetyFactor).toBe(Number((yieldMpa / row.peakVonMisesMpa).toFixed(2)));
    });
    if (r.packData?.packId === "engineering" && r.packData.convergenceLevels) it(`run #${r.sequence}: convergence changes are computed from the levels`, () => {
      const lv = r.packData!.packId === "engineering" ? r.packData!.convergenceLevels ?? [] : [];
      for (let i = 1; i < lv.length; i++) expect(lv[i]!.changePercent).toBe(Number((((lv[i]!.peakVonMisesMpa - lv[i - 1]!.peakVonMisesMpa) / lv[i - 1]!.peakVonMisesMpa) * 100).toFixed(1)));
      const last = lv.at(-1)!; expect(r.packData!.packId === "engineering" && r.packData!.converged).toBe((last.changePercent ?? 0) < (r.packData!.packId === "engineering" ? r.packData!.convergenceCriterionPercent ?? 5 : 5));
    });
  }
  it("the story numbers hold: 162 → 1.70, 171 → 1.61, 118 → 2.34", () => {
    expect(Number((276 / 162).toFixed(2))).toBe(1.7); expect(Number((276 / 171).toFixed(2))).toBe(1.61); expect(Number((276 / 118).toFixed(2))).toBe(2.34);
  });
});

describe("legal sample: authorities are obviously fictional and labelled", () => {
  const auths = db.artifacts.filter((a) => a.projectId === "proj-legal-northwind" && a.kind === "authority");
  it("has authorities", () => { expect(auths.length).toBeGreaterThan(0); });
  for (const a of auths) it(`${a.name} is labelled fictional`, () => {
    expect(a.name).toMatch(/fictional/i);
    for (const v of a.versions) { const pd = v.packData; expect(pd?.packId).toBe("legal"); if (pd?.packId === "legal") { expect(pd.authority?.fictionalLabel).toBe("Sample authority, not a real case"); expect(pd.authority?.name).toMatch(/fictional/i); } }
  });
  it("every chronology event and argument node source resolves to a document page", () => {
    const legal = find(db.projects, "proj-legal-northwind");
    if (legal.packData.packId !== "legal") throw new Error("legal packData");
    const pageOf = (vid: string, page: number) => db.artifacts.flatMap((a) => a.versions).find((v) => v.id === vid)?.packData?.packId === "legal" ? (db.artifacts.flatMap((a) => a.versions).find((v) => v.id === vid)!.packData as { pages?: Array<{ page: number; lines: string[] }> }).pages?.find((p) => p.page === page) : undefined;
    for (const e of legal.packData.chronology) { const pg = pageOf(e.source.artifactVersionId, e.source.page); expect(pg, `${e.id} page`).toBeDefined(); if (e.source.line) expect(pg!.lines.length).toBeGreaterThanOrEqual(e.source.line); }
    for (const n of legal.packData.argumentMap) { if (n.source && "artifactVersionId" in n.source) { const pg = pageOf(n.source.artifactVersionId, n.source.page); expect(pg, `${n.id} page`).toBeDefined(); if (n.source.line) expect(pg!.lines.length).toBeGreaterThanOrEqual(n.source.line); } for (const s of n.supports) expect(legal.packData.argumentMap.some((x) => x.id === s), `${n.id} supports ${s}`).toBe(true); }
    expect(legal.packData.rehearsal.disclaimer).toBe("Preparation exercise, not a prediction of the outcome.");
    expect(legal.permissions.confidentiality).toBe("confidential");
  });
  it("the planted date contradiction is at the referenced lines", () => {
    const vs = db.artifacts.flatMap((a) => a.versions);
    const brief = vs.find((v) => v.id === "artv-L-brief-v1")!; const receipt = vs.find((v) => v.id === "artv-L-receipt")!;
    const line = (v: typeof brief, page: number, n: number) => (v.packData as { pages: Array<{ page: number; lines: string[] }> }).pages.find((p) => p.page === page)!.lines[n - 1];
    expect(line(brief, 4, 12)).toMatch(/3 March 2026/); expect(line(receipt, 1, 8)).toMatch(/10 March 2026/);
    const v2 = vs.find((v) => v.id === "artv-L-brief-v2")!; expect(line(v2, 4, 12)).toMatch(/10 March 2026/);
  });
});

describe("evidence label and status rules", () => {
  const checksOf = (id: string) => { const f = find(db.findings, id); return db.checks.filter((c) => f.checkIds.includes(c.id)); };
  it("labels across the three samples", () => {
    expect(computeEvidenceLabel(checksOf("fnd-001"))).toBe("Expert-reviewed");
    expect(computeEvidenceLabel(checksOf("fnd-002"))).toBe("Estimate");
    expect(computeEvidenceLabel(checksOf("fnd-003"))).toBe("Machine-checked");
    expect(computeEvidenceLabel(checksOf("fnd-E-001"))).toBe("Expert-reviewed");
    expect(computeEvidenceLabel(checksOf("fnd-E-002"))).toBe("Machine-checked");
    expect(computeEvidenceLabel(checksOf("fnd-L-001"))).toBe("Expert-reviewed");
    expect(computeEvidenceLabel(checksOf("fnd-L-002"))).toBe("Machine-checked");
    expect(computeEvidenceLabel(checksOf("fnd-L-003"))).toBe("Model-reviewed");
  });
  it("two agreeing agent claims still yield Estimate", () => {
    const agree = checksOf("fnd-002").map((c) => ({ ...c, result: "supports" as const }));
    expect(computeEvidenceLabel(agree)).toBe("Estimate");
  });
  it("a model judgment alone is Model-reviewed; imported-only is Imported; nothing is Estimate", () => {
    const mj = db.checks.find((c) => c.kind === "model_judgment")!;
    expect(computeEvidenceLabel([mj])).toBe("Model-reviewed");
    expect(computeEvidenceLabel([], { hasImportedEvidence: true })).toBe("Imported");
    expect(computeEvidenceLabel([])).toBe("Estimate");
  });
  it("user-facing statuses follow the single mapping", () => {
    expect(toUserFacingStatus(find(db.findings, "fnd-001"), runsById)).toBe("Resolved within tested scope");
    expect(toUserFacingStatus(find(db.findings, "fnd-002"), runsById)).toBe("Open");
    expect(toUserFacingStatus(find(db.findings, "fnd-003"), runsById)).toBe("Recommendation proposed");
    expect(toUserFacingStatus(find(db.findings, "fnd-E-001"), runsById)).toBe("Resolved within tested scope");
    expect(toUserFacingStatus(find(db.findings, "fnd-E-002"), runsById)).toBe("Resolved within tested scope");
    expect(toUserFacingStatus(find(db.findings, "fnd-L-003"), runsById)).toBe("Open");
    expect(canResolve(find(db.findings, "fnd-001"), runsById).ok).toBe(true);
    expect(canResolve(find(db.findings, "fnd-002"), runsById).ok).toBe(false);
    expect(canResolve(find(db.findings, "fnd-L-003"), runsById).ok).toBe(false);
  });
});
