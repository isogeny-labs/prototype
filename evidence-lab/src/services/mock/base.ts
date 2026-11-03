import { store } from "@/store";
import { ServiceError } from "../types";

/** Shared behaviour of every mock: configurable latency and failure injection. */
export async function simulate<T>(method: string, fn: () => T): Promise<T> {
  const { mock } = store.get();
  const latency = mock.latencyMs;
  if (latency > 0) await new Promise((r) => setTimeout(r, latency));
  const { mock: m2 } = store.get();
  if (m2.failNext === method) {
    store.get().setMock({ failNext: null });
    throw new ServiceError(`Injected failure for ${method}`, "injected");
  }
  if (m2.failureRate > 0 && Math.random() < m2.failureRate) {
    throw new ServiceError(`Simulated network failure calling ${method} (failure injection is on)`, "network");
  }
  return fn();
}

export function nowIso(): string { return new Date().toISOString(); }
export function newId(prefix: string): string { return `${prefix}-${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-4)}`; }

export function notFound(what: string, id: string): never {
  throw new ServiceError(`${what} ${id} was not found`, "not_found");
}

export function audit(projectId: string | null, actor: { type: "human" | "agent" | "tool" | "system"; name: string }, action: string, subject: { type: string; id: string | null; label: string }, detail?: string) {
  store.mutate((db) => { db.audit.unshift({ id: newId("aud"), projectId, actor, action, subject, timestamp: nowIso(), detail }); });
}
