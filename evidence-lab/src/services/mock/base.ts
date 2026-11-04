import { store } from "@/store";
import { ServiceError } from "../types";

/** Methods the developer state switcher leaves alone, so the shell itself stays usable while a view is forced. */
const SHELL_METHODS = new Set(["listProjects", "getProject", "packs.getTemplate", "packs.list", "packs.templates"]);
/** Methods that mutate: never transformed, so decisions made while a state is forced still apply to the live data. */
const isRead = (method: string) => /^(list|get|packs\.|cairn\.|learning\.|autoresearcher\.(list|get|followUps)|conductor\.listTasks|approvals\.list)/.test(method);

/**
 * Developer state switcher: reshape read results so every key view shows the requested state.
 * - empty: lists become empty; single records keep their identity but lose their lists.
 * - awaiting_approval / completed: runs, approvals, proposals, tasks and recommendations are shown in that state.
 * Applied to copies only; the store is never changed.
 */
export function forceState<T>(value: T, state: "empty" | "awaiting_approval" | "completed"): T {
  const visit = (v: unknown): unknown => {
    if (Array.isArray(v)) return state === "empty" ? [] : v.map(visit);
    if (!v || typeof v !== "object") return v;
    const o = { ...(v as Record<string, unknown>) };
    if (state === "empty") {
      for (const k of Object.keys(o)) if (Array.isArray(o[k])) o[k] = [];
      return o;
    }
    const awaiting = state === "awaiting_approval";
    if ("sequence" in o && "overallPass" in o) { // Run
      o.status = awaiting ? "awaiting_approval" : "completed";
      if (awaiting) { o.overallPass = null; o.finishedAt = null; o.startedAt = null; o.metrics = []; o.cases = []; o.failures = []; o.evidenceRecordId = null; o.logs = [{ t: new Date().toISOString(), level: "info", text: "Awaiting execution approval (developer state switcher)." }]; }
    } else if ("subjectType" in o && "decision" in o) { // Approval
      if (awaiting) { o.decision = "pending"; o.reviewerId = null; o.decidedAt = null; o.note = ""; } else if (o.decision === "pending") { o.decision = "approved"; o.reviewerId = o.reviewerId ?? "person-switcher"; o.decidedAt = new Date().toISOString(); o.note = "Shown as completed by the developer state switcher."; }
    } else if ("protocolVersion" in o && "hypothesis" in o) { // Proposal
      if (awaiting) { o.status = "proposed"; o.protocolVersion = 0; o.protocolHistory = []; o.resultRunIds = []; o.resultSummary = ""; } else { o.status = "reviewed"; }
    } else if ("dependsOn" in o && "owner" in o) { // Task
      o.status = awaiting ? "awaiting_checkpoint" : "done";
    } else if ("proposedChange" in o && "applicabilityLimits" in o) { // Recommendation
      o.status = awaiting ? "under_review" : "approved";
    } else {
      for (const k of Object.keys(o)) o[k] = visit(o[k]);
    }
    return o;
  };
  return visit(value) as T;
}

/** Shared behaviour of every mock: configurable latency, failure injection and the developer state switcher. */
export async function simulate<T>(method: string, fn: () => T | Promise<T>): Promise<T> {
  const { mock } = store.get();
  const latency = mock.latencyMs;
  if (latency > 0) await new Promise((r) => setTimeout(r, latency));
  const { mock: m2, devState } = store.get();
  if (m2.failNext === method) {
    store.get().setMock({ failNext: null });
    throw new ServiceError(`Injected failure for ${method}`, "injected");
  }
  if (m2.failureRate > 0 && Math.random() < m2.failureRate) {
    throw new ServiceError(`Simulated network failure calling ${method} (failure injection is on)`, "network");
  }
  const forced = devState && !SHELL_METHODS.has(method) && isRead(method);
  if (forced && devState === "failed") throw new ServiceError(`Forced failure for ${method} (developer state switcher)`, "injected");
  const result = await fn();
  if (forced && (devState === "empty" || devState === "awaiting_approval" || devState === "completed")) return forceState(structuredClone(result), devState);
  return result;
}

export function nowIso(): string { return new Date().toISOString(); }
export function newId(prefix: string): string { return `${prefix}-${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-4)}`; }

export function notFound(what: string, id: string): never {
  throw new ServiceError(`${what} ${id} was not found`, "not_found");
}

export function audit(projectId: string | null, actor: { type: "human" | "agent" | "tool" | "system"; name: string }, action: string, subject: { type: string; id: string | null; label: string }, detail?: string) {
  store.mutate((db) => { db.audit.unshift({ id: newId("aud"), projectId, actor, action, subject, timestamp: nowIso(), detail }); });
}
