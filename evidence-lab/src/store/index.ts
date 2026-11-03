import { create } from "zustand";
import { emptyDb, type Db } from "./db";
import { loadFixtures } from "@/fixtures";

export interface MockConfig {
  latencyMs: number;          // simulated latency for every service call
  failureRate: number;        // 0..1 probability a call fails
  failNext: string | null;    // force the next call to a named method to fail
}

export type SessionUser = { id: string; name: string; role: string };

/** Default acting user per sample project: the customer-side editor. */
export const DEFAULT_USER_BY_PROJECT: Record<string, SessionUser> = {
  "proj-crypto-acme": { id: "person-dana", name: "Dana Whitfield", role: "Customer engineer (Acme Pay) · editor" },
  "proj-eng-mb200": { id: "person-rosa", name: "Rosa Lindqvist", role: "Design engineer (Halden) · editor" },
  "proj-legal-northwind": { id: "person-maya", name: "Maya Chen", role: "Associate (Bellweather & Finch) · editor" },
};

interface AppState {
  db: Db;
  version: number;            // bumped on every mutation so queries re-run
  mock: MockConfig;
  user: SessionUser;          // who is acting in the UI (sample mode: switchable)
  assistantOpen: boolean;
  viewConfig: Record<string, { panelOrder: string[]; hiddenPanels: string[]; filters: Record<string, string>; chosenTestIds: string[] }>;
  mutate: (fn: (db: Db) => void) => void;
  setMock: (patch: Partial<MockConfig>) => void;
  setUser: (u: SessionUser) => void;
  setAssistantOpen: (open: boolean) => void;
  setViewConfig: (projectId: string, patch: Partial<AppState["viewConfig"][string]>) => void;
  resetToSampleData: () => void;
}

const DEFAULT_USER: SessionUser = { id: "person-dana", name: "Dana Whitfield", role: "Customer engineer (Acme Pay)" };

function readMockConfig(): MockConfig {
  const base: MockConfig = { latencyMs: 250, failureRate: 0, failNext: null };
  try {
    const raw = localStorage.getItem("iel.mockConfig");
    if (raw) return { ...base, ...(JSON.parse(raw) as Partial<MockConfig>), failNext: null };
  } catch { /* storage unavailable: run with defaults */ }
  return base;
}

export const useAppStore = create<AppState>((set) => ({
  db: loadFixtures(emptyDb()),
  version: 0,
  mock: readMockConfig(),
  user: DEFAULT_USER,
  assistantOpen: false,
  viewConfig: {},
  mutate: (fn) => set((s) => { const db = structuredClone(s.db); fn(db); return { db, version: s.version + 1 }; }),
  setMock: (patch) => set((s) => {
    const mock = { ...s.mock, ...patch };
    try { localStorage.setItem("iel.mockConfig", JSON.stringify({ latencyMs: mock.latencyMs, failureRate: mock.failureRate })); } catch { /* ignore */ }
    return { mock };
  }),
  setUser: (user) => set({ user }),
  setAssistantOpen: (assistantOpen) => set({ assistantOpen }),
  setViewConfig: (projectId, patch) => set((s) => ({ viewConfig: { ...s.viewConfig, [projectId]: { panelOrder: [], hiddenPanels: [], filters: {}, chosenTestIds: [], ...s.viewConfig[projectId], ...patch } } })),
  resetToSampleData: () => set((s) => ({ db: loadFixtures(emptyDb()), version: s.version + 1, viewConfig: {}, user: DEFAULT_USER })),
}));

/** Non-React access for services. */
export const store = {
  get: () => useAppStore.getState(),
  db: () => useAppStore.getState().db,
  mutate: (fn: (db: Db) => void) => useAppStore.getState().mutate(fn),
};
