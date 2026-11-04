import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "@/store";
import { services, ServiceError } from "@/services";
import { forceState } from "@/services/mock/base";
import { emptyDb } from "@/store/db";
import { loadFixtures } from "@/fixtures";

const P = "proj-crypto-acme";
const fail = async (p: Promise<unknown>) => { try { await p; } catch (e) { return e as ServiceError; } throw new Error("expected rejection"); };

beforeEach(() => { useAppStore.getState().resetToSampleData(); useAppStore.getState().setMock({ latencyMs: 0, failureRate: 0, failNext: null }); });

describe("approval rules in the mock", () => {
  it("blocks self-approval and says why", async () => {
    const e = await fail(services.approvals.decide(P, "apr-fnd-001-resolution", "approved", "person-dana", ""));
    expect(e.code).toBe("forbidden"); expect(e.message).toMatch(/cannot decide it/);
  });
  it("enforces the gate's role: an editor cannot decide, a reviewer can, and the record and subject update", async () => {
    const e = await fail(services.approvals.decide(P, "apr-rec-002", "approved", "person-dana", ""));
    expect(e.code).toBe("forbidden"); expect(e.message).toMatch(/role in this project is editor/);
    const a = await services.approvals.decide(P, "apr-fnd-001-resolution", "approved", "person-priya", "ok");
    expect(a.decision).toBe("approved"); expect(a.reviewerId).toBe("person-priya"); expect(a.decidedAt).not.toBeNull();
    const f = useAppStore.getState().db.findings.find((x) => x.id === "fnd-001")!;
    expect(f.status).toBe("closed"); expect(f.statusHistory.at(-1)?.status).toBe("closed");
  });
  it("never overwrites a decision", async () => {
    await services.approvals.decide(P, "apr-fnd-001-resolution", "approved", "person-priya", "ok");
    const e = await fail(services.approvals.decide(P, "apr-fnd-001-resolution", "rejected", "person-marco", "no"));
    expect(e.code).toBe("conflict");
  });
  it("refuses to resolve a finding without a linked passing retest", async () => {
    const e = await fail(services.approvals.decide(P, "apr-fnd-002-resolution", "approved", "person-priya", ""));
    expect(e.code).toBe("conflict"); expect(e.message).toMatch(/No retest run is linked/);
    expect(useAppStore.getState().db.approvals.find((a) => a.id === "apr-fnd-002-resolution")?.decision).toBe("pending");
  });
  it("writes memory records from decisions and never a model-training record", async () => {
    const before = useAppStore.getState().db.memory.length;
    await services.approvals.decide(P, "apr-rec-002", "changes_requested", "person-marco", "Search call sites first.");
    await services.approvals.decide(P, "apr-prop-latency", "rejected", "person-priya", "Not now.");
    const mem = useAppStore.getState().db.memory;
    expect(mem.length).toBe(before + 2);
    expect(mem.some((m) => m.kind === "expert_correction" && m.customerScope.includes("Acme"))).toBe(true);
    expect(mem.some((m) => m.kind === "rejected_hypothesis")).toBe(true);
    expect(useAppStore.getState().db.modelTraining.every((m) => m.status === "not_in_mvp")).toBe(true);
  });
});

describe("assistant rules in the mock", () => {
  const vc = { panelOrder: [], hiddenPanels: [], filters: {}, chosenTestIds: [] };
  const dana = { id: "person-dana", name: "Dana Whitfield" }; const priya = { id: "person-priya", name: "Priya Natarajan" };
  const ctx = { page: "overview" as const };
  it("never changes criteria, permissions or tests directly: it drafts, and nothing changes until confirmed", async () => {
    const before = structuredClone(useAppStore.getState().db);
    const r1 = await services.assistant.send(P, vc, "set the latency threshold to 3 ms", dana, ctx);
    expect(r1.reply.action?.kind).toBe("refused");
    expect(r1.reply.suggestions?.[0]?.kind).toBe("propose_criteria");
    const r2 = await services.assistant.send(P, vc, "give Lee owner permissions", dana, ctx);
    expect(r2.reply.suggestions?.[0]?.kind).toBe("request_settings_change");
    const r3 = await services.assistant.send(P, vc, "edit the test definition for latency to 2000 iterations", dana, ctx);
    expect(r3.reply.suggestions?.[0]?.kind).toBe("create_proposal");
    const after = useAppStore.getState().db;
    expect(after.criteria).toEqual(before.criteria); expect(after.approvals.length).toBe(before.approvals.length); expect(after.proposals.length).toBe(before.proposals.length);
    expect(after.projects.find((p) => p.id === P)?.permissions).toEqual(before.projects.find((p) => p.id === P)?.permissions);
    expect(after.tests).toEqual(before.tests);
  });
  it("confirming the criteria draft proposes a new version for owner approval; the current version stays in force", async () => {
    const r = await services.assistant.send(P, vc, "set the latency threshold to 3 ms", dana, ctx);
    const a = r.reply.suggestions![0]!;
    const c = await services.assistant.confirm(P, a, dana);
    expect(c.reply.action?.kind).toBe("confirmed");
    const db = useAppStore.getState().db;
    const v2 = db.criteria.find((x) => x.projectId === P && x.version === 2)!;
    expect(v2.approvalId).toBeNull(); expect(v2.items.find((i) => i.id === "ac-5")?.threshold).toBe(3);
    expect(db.projects.find((p) => p.id === P)?.currentCriteriaVersion).toBe(1);
    expect(db.audit[0]?.action).toBe("assistant.action_confirmed"); expect(db.audit[0]?.actor.type).toBe("human");
  });
  it("summarises evidence and proposes next experiments and runs without executing anything", async () => {
    const before = useAppStore.getState().db.runs.length;
    const r = await services.assistant.send(P, vc, "what should we test next?", dana, ctx);
    expect(r.reply.text).toMatch(/Nothing runs until you confirm/);
    expect(r.reply.suggestions?.some((a) => a.kind === "create_proposal" || a.kind === "request_run")).toBe(true);
    expect(useAppStore.getState().db.runs.length).toBe(before);
    const s = await services.assistant.send(P, vc, "summarize the evidence", dana, ctx);
    expect(s.reply.text).toMatch(/Evidence so far/); expect(s.reply.text).toMatch(/Estimate/);
  });
  it("a confirmed run request creates a run awaiting approval, as the confirming user", async () => {
    const r = await services.assistant.send(P, vc, "what should we test next?", dana, ctx);
    const a = r.reply.suggestions!.find((x) => x.kind === "request_run")!;
    const c = await services.assistant.confirm(P, a, dana);
    expect(c.reply.text).toMatch(/awaits execution approval/);
    const run = useAppStore.getState().db.runs.filter((x) => x.projectId === P).at(-1)!;
    expect(run.status).toBe("awaiting_approval"); expect(run.requestedBy).toBe("person-dana");
  });
  it("orchestration and pending-approval advice respects roles: an editor gets 'open', a reviewer gets 'approve'", async () => {
    const o = await services.assistant.send(P, vc, "review the orchestration", dana, { page: "conductor" });
    expect(o.reply.text).toMatch(/at a checkpoint/);
    expect(o.reply.suggestions?.some((a) => a.kind === "navigate")).toBe(true);
    const p = await services.assistant.send(P, vc, "what's waiting on me?", priya, { page: "approvals" });
    expect(p.reply.suggestions?.some((a) => a.kind === "decide_approval")).toBe(true);
    const bad = p.reply.suggestions!.find((a) => a.kind === "decide_approval")!;
    const c = await services.assistant.confirm(P, bad, priya);
    expect(c.reply.action?.kind).toBe("confirmed");
    const self = await fail(services.assistant.confirm(P, { ...bad, params: { approvalId: "apr-rec-002", decision: "approved", note: "" } }, dana));
    expect(self.code).toBe("forbidden");
  });
  it("changes view configuration only, and audits it", async () => {
    const n = useAppStore.getState().db.audit.length;
    const { reply, viewConfig } = await services.assistant.send(P, vc, "hide the recent activity panel", dana, ctx);
    expect(reply.action?.kind).toBe("view_change"); expect(viewConfig.hiddenPanels).toEqual(["recent_activity"]);
    expect(useAppStore.getState().db.audit.length).toBe(n + 1); expect(useAppStore.getState().db.audit[0]?.action).toBe("view.configured");
    const r2 = await services.assistant.send(P, viewConfig, "show tests matching latency", dana, ctx);
    expect(r2.viewConfig.chosenTestIds).toEqual(["test-latency"]);
    expect(useAppStore.getState().db.criteria.filter((c) => c.projectId === P).length).toBe(1);
  });
});

describe("developer state switcher", () => {
  it("forceState reshapes copies without touching the store", () => {
    const db = loadFixtures(emptyDb());
    const runs = forceState(structuredClone(db.runs), "awaiting_approval");
    expect(runs.every((r) => r.status === "awaiting_approval" && r.overallPass === null)).toBe(true);
    expect(db.runs.some((r) => r.status === "completed")).toBe(true);
    expect(forceState(structuredClone(db.approvals), "completed").every((a) => a.decision !== "pending")).toBe(true);
    expect(forceState({ finding: db.findings[0], checks: db.checks }, "empty").checks).toEqual([]);
  });
  it("reads are forced, writes still apply to live data", async () => {
    useAppStore.getState().setDevState("empty");
    expect(await services.evidenceLab.listRuns(P)).toEqual([]);
    expect((await services.evidenceLab.getProject(P)).id).toBe(P);
    useAppStore.getState().setDevState("failed");
    const e = await fail(services.evidenceLab.listFindings(P)); expect(e.message).toMatch(/Forced failure/);
    const a = await services.approvals.decide(P, "apr-fnd-001-resolution", "approved", "person-priya", "ok");
    expect(a.decision).toBe("approved");
    useAppStore.getState().setDevState(null);
    expect((await services.evidenceLab.listRuns(P)).length).toBe(16);
  });
});

describe("failure injection and reset", () => {
  it("fails the next named call once, then recovers", async () => {
    useAppStore.getState().setMock({ failNext: "getRun" });
    const e = await fail(services.evidenceLab.getRun(P, "run-003")); expect(e.code).toBe("injected");
    expect((await services.evidenceLab.getRun(P, "run-003")).id).toBe("run-003");
  });
  it("retry appends a new run that supersedes the failed one; reset restores the fixtures", async () => {
    const r = await services.evidenceLab.retryRun(P, "run-015", "person-dana");
    expect(r.supersedesRunId).toBe("run-015"); expect(r.sequence).toBe(17);
    expect(useAppStore.getState().db.runs.filter((x) => x.projectId === P).length).toBe(17);
    useAppStore.getState().resetToSampleData();
    expect(useAppStore.getState().db.runs.filter((x) => x.projectId === P).length).toBe(16);
  });
});
