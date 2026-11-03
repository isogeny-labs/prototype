import type { EvidenceLabService } from "../types";
import { ServiceError } from "../types";
import { store } from "@/store";
import { simulate, nowIso, newId, notFound, audit } from "./base";
import type { Run } from "@/contracts";

const sha = () => Array.from({ length: 64 }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join("");
const personName = (projectId: string, id: string) => store.db().projects.find((p) => p.id === projectId)?.people.find((p) => p.id === id)?.name ?? id;

export const mockEvidenceLab: EvidenceLabService = {
  listProjects: () => simulate("listProjects", () => store.db().projects),
  getProject: (id) => simulate("getProject", () => store.db().projects.find((p) => p.id === id) ?? notFound("project", id)),
  listCriteria: (projectId) => simulate("listCriteria", () => store.db().criteria.filter((c) => c.projectId === projectId)),
  proposeCriteriaVersion: (projectId, items, requestedBy) => simulate("proposeCriteriaVersion", () => {
    const existing = store.db().criteria.filter((c) => c.projectId === projectId);
    const version = Math.max(0, ...existing.map((c) => c.version)) + 1;
    const approval = { id: newId("apr"), projectId, subjectType: "acceptance_criteria" as const, subjectId: "", subjectLabel: `Acceptance criteria v${version}`,
      requestedBy, requestedAt: nowIso(), decision: "pending" as const, reviewerId: null, note: "", decidedAt: null,
      rationale: "Changing acceptance criteria changes what every future run is judged against; a reviewer must approve the new version." };
    const criteria = { id: newId("crit"), projectId, version, items, approvalId: null, createdAt: nowIso(), createdBy: requestedBy, supersedesVersion: version - 1 };
    approval.subjectId = criteria.id;
    store.mutate((db) => { db.criteria.push(criteria); db.approvals.unshift(approval); });
    audit(projectId, { type: "human", name: personName(projectId, requestedBy) }, "criteria.version_proposed", { type: "acceptance_criteria", id: criteria.id, label: `v${version}` });
    return { criteria, approval };
  }),
  listArtifacts: (projectId) => simulate("listArtifacts", () => store.db().artifacts.filter((a) => a.projectId === projectId)),
  importArtifactVersion: (projectId, artifactId, version) => simulate("importArtifactVersion", () => {
    const v = { ...version, id: newId("artv"), artifactId };
    store.mutate((db) => { const a = db.artifacts.find((x) => x.id === artifactId && x.projectId === projectId); if (!a) notFound("artifact", artifactId); a.versions.push(v); });
    audit(projectId, { type: "human", name: personName(projectId, version.importedBy) }, "artifact.version_imported", { type: "artifact_version", id: v.id, label: `${artifactId} ${v.version}` });
    return v;
  }),
  listTests: (projectId) => simulate("listTests", () => {
    const p = store.db().projects.find((x) => x.id === projectId);
    return store.db().tests.filter((t) => t.packId === p?.packId);
  }),
  listRuns: (projectId) => simulate("listRuns", () => store.db().runs.filter((r) => r.projectId === projectId).sort((a, b) => a.sequence - b.sequence)),
  getRun: (projectId, runId) => simulate("getRun", () => store.db().runs.find((r) => r.id === runId && r.projectId === projectId) ?? notFound("run", runId)),
  requestRun: (projectId, input) => simulate("requestRun", () => {
    const db = store.db();
    const test = db.tests.find((t) => t.id === input.testDefinitionId) ?? notFound("test definition", input.testDefinitionId);
    if (!test.runnable) throw new ServiceError(`${test.name} is not runnable here: ${test.unsupportedReason ?? "unsupported"}`, "validation");
    const project = db.projects.find((p) => p.id === projectId) ?? notFound("project", projectId);
    const seq = Math.max(0, ...db.runs.filter((r) => r.projectId === projectId).map((r) => r.sequence)) + 1;
    const run: Run = { id: newId("run"), projectId, sequence: seq, artifactVersionId: input.artifactVersionId, testDefinitionId: test.id,
      criteriaVersion: project.currentCriteriaVersion, executionMode: "simulated", provenance: "illustrative", status: "awaiting_approval",
      environment: { note: "Simulated: no runner is connected. Execution approval is required before anything would run." },
      toolVersions: { runner: test.runner, runnerVersion: test.runnerVersion }, commands: [], parameters: {}, seeds: {}, repeatCount: 0, logs: [{ t: nowIso(), level: "info", text: "Run requested (simulated). Awaiting execution approval." }],
      metrics: [], cases: [], failures: [], limitations: ["Simulated request: no execution happened."], criteriaResults: [], overallPass: null, supersedesRunId: null, correctionNote: "",
      evidenceRecordId: null, requestedBy: input.requestedBy, approvalId: null, startedAt: null, finishedAt: null, createdAt: nowIso() };
    const approval = { id: newId("apr"), projectId, subjectType: "run_execution" as const, subjectId: run.id, subjectLabel: `Run #${seq}: ${test.name}`, requestedBy: input.requestedBy,
      requestedAt: nowIso(), decision: "pending" as const, reviewerId: null, note: "", decidedAt: null, rationale: "Execution of a test consumes budget and runs code in the sandbox; the pack template requires approval." };
    run.approvalId = approval.id;
    store.mutate((d) => { d.runs.push(run); d.approvals.unshift(approval); });
    audit(projectId, { type: "human", name: personName(projectId, input.requestedBy) }, "run.requested", { type: "run", id: run.id, label: `#${seq}` });
    return run;
  }),
  retryRun: (projectId, runId, requestedBy) => simulate("retryRun", () => {
    const prev = store.db().runs.find((r) => r.id === runId && r.projectId === projectId) ?? notFound("run", runId);
    const seq = Math.max(0, ...store.db().runs.filter((r) => r.projectId === projectId).map((r) => r.sequence)) + 1;
    const run: Run = { ...structuredClone(prev), id: newId("run"), sequence: seq, status: "queued", supersedesRunId: prev.id, correctionNote: `Retry of run #${prev.sequence} after failure`,
      logs: [{ t: nowIso(), level: "info", text: `Queued as a new append-only record (retry of #${prev.sequence}). Simulated.` }], failures: [], metrics: [], cases: [], overallPass: null,
      startedAt: null, finishedAt: null, createdAt: nowIso(), requestedBy, evidenceRecordId: null };
    store.mutate((d) => { d.runs.push(run); });
    audit(projectId, { type: "human", name: personName(projectId, requestedBy) }, "run.retried", { type: "run", id: run.id, label: `#${seq} retries #${prev.sequence}` });
    return run;
  }),
  listFindings: (projectId) => simulate("listFindings", () => store.db().findings.filter((f) => f.projectId === projectId)),
  getFinding: (projectId, findingId) => simulate("getFinding", () => {
    const finding = store.db().findings.find((f) => f.id === findingId && f.projectId === projectId) ?? notFound("finding", findingId);
    const checks = store.db().checks.filter((c) => finding.checkIds.includes(c.id));
    return { finding, checks };
  }),
  listChecks: (projectId) => simulate("listChecks", () => { const ids = new Set(store.db().findings.filter((f) => f.projectId === projectId).flatMap((f) => f.checkIds)); const runIds = new Set(store.db().runs.filter((r) => r.projectId === projectId).map((r) => r.id)); return store.db().checks.filter((c) => ids.has(c.id) || (c.runId && runIds.has(c.runId))); }),
  listEvidence: (projectId) => simulate("listEvidence", () => store.db().evidence.filter((e) => e.projectId === projectId)),
  listComparisons: (projectId) => simulate("listComparisons", () => store.db().comparisons.filter((c) => c.projectId === projectId)),
  listRecommendations: (projectId) => simulate("listRecommendations", () => store.db().recommendations.filter((r) => r.projectId === projectId)),
  listExternalChanges: (projectId) => simulate("listExternalChanges", () => store.db().externalChanges.filter((c) => c.projectId === projectId)),
  reportExternalChange: (projectId, change) => simulate("reportExternalChange", () => {
    const rec = { ...change, id: newId("chg"), reportedAt: nowIso() };
    store.mutate((db) => {
      db.externalChanges.push(rec);
      const f = change.findingId ? db.findings.find((x) => x.id === change.findingId) : undefined;
      if (f) { f.externalChangeReported = true; f.revisedArtifactVersionId = change.newArtifactVersionId; f.statusHistory.push({ status: f.status, at: nowIso(), by: personName(projectId, change.reportedBy), note: `External change reported: ${change.description}` }); }
    });
    audit(projectId, { type: "human", name: personName(projectId, change.reportedBy) }, "change.reported", { type: "external_change", id: rec.id, label: change.description.slice(0, 60) });
    return rec;
  }),
  listAttackAssessments: (projectId) => simulate("listAttackAssessments", () => store.db().attackAssessments.filter((a) => a.projectId === projectId)),
  exportHandoff: (projectId) => simulate("exportHandoff", () => ({ format: "engineering-handoff/1 (preview)", generatedAt: nowIso(), sha256: sha(), sizeBytes: 48_112, note: `Simulated export for ${projectId}: no file is produced in the mock.` })),
  exportEvidenceBundle: (projectId) => simulate("exportEvidenceBundle", () => ({ format: "evidence-package/2 (SHA-256 manifest, preview)", generatedAt: nowIso(), manifestSha256: sha(), members: store.db().runs.filter((r) => r.projectId === projectId).length + 6, signed: false as const, note: "Simulated. The existing backend export is a hashed manifest with a verify step; signing is integration pending." })),
  listAudit: (projectId) => simulate("listAudit", () => store.db().audit.filter((a) => a.projectId === projectId || a.projectId === null)),
};
