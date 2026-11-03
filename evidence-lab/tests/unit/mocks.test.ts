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
  it("refuses criteria, permission and test-definition changes and routes them to an approval request", async () => {
    for (const text of ["lower the acceptance criteria to 1.5", "give Lee owner permissions", "edit the test definition for latency"]) {
      const n = useAppStore.getState().db.approvals.length;
      const { reply, viewConfig } = await services.assistant.send(P, vc, text, { id: "person-dana", name: "Dana Whitfield" });
      expect(reply.action?.kind).toBe("refused");
      expect(useAppStore.getState().db.approvals.length).toBe(n + 1);
      expect(viewConfig).toEqual(vc);
    }
  });
  it("changes view configuration only, and audits it", async () => {
    const n = useAppStore.getState().db.audit.length;
    const { reply, viewConfig } = await services.assistant.send(P, vc, "hide the recent activity panel", { id: "person-dana", name: "Dana Whitfield" });
    expect(reply.action?.kind).toBe("view_change"); expect(viewConfig.hiddenPanels).toEqual(["recent_activity"]);
    expect(useAppStore.getState().db.audit.length).toBe(n + 1); expect(useAppStore.getState().db.audit[0]?.action).toBe("view.configured");
    const r2 = await services.assistant.send(P, viewConfig, "show tests matching latency", { id: "person-dana", name: "Dana Whitfield" });
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
