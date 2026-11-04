import { create } from "zustand";
import { emptyDb, type Db } from "./db";
import { loadFixtures } from "@/fixtures";

export interface MockConfig {
  latencyMs: number;          // simulated latency for every service call
  failureRate: number;        // 0..1 probability a call fails
  failNext: string | null;    // force the next call to a named method to fail
}

export type SessionUser = { id: string; name: string; role: string };

/** Developer state switcher (sample mode only): forces every key view into one state. null = live sample data. */
export type DevState = null | "empty" | "loading" | "failed" | "awaiting_approval" | "completed";
export const DEV_STATES: Array<{ value: DevState; label: string }> = [
  { value: null, label: "live sample data" }, { value: "empty", label: "empty" }, { value: "loading", label: "loading" },
  { value: "failed", label: "failed" }, { value: "awaiting_approval", label: "awaiting approval" }, { value: "completed", label: "completed" },
];
export type AssistantTranscriptMessage = import("@/contracts").AssistantMessage & { dismissed?: string[] };

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
  devState: DevState;
  assistantMessages: Record<string, AssistantTranscriptMessage[]>;
  setDevState: (s: DevState) => void;
  appendAssistantMessages: (projectId: string, msgs: AssistantTranscriptMessage[]) => void;
  clearAssistant: (projectId: string) => void;
  mutate: (fn: (db: Db) => void) => void;
  setMock: (patch: Partial<MockConfig>) => void;
  setUser: (u: SessionUser) => void;
  setAssistantOpen: (open: boolean) => void;
  setViewConfig: (projectId: string, patch: Partial<AppState["viewConfig"][string]>) => void;
  resetToSampleData: () => void;
}

const DEFAULT_USER: SessionUser = { id: "person-dana", name: "Dana Whitfield", role: "Customer engineer (Acme Pay)" };

/**
 * Session persistence (convenience only, per spec): the mutable sample state survives a refresh or deep link within
 * one browser tab. sessionStorage is per tab, every access is guarded, and "Reset to sample data" clears it.
 * A fingerprint of the fixtures discards stale sessions after a deploy changes the sample data.
 */
const SESSION_KEY = "iel.session";
type Persisted = { fingerprint: number; db: Db; viewConfig: AppState["viewConfig"]; user: SessionUser; assistantMessages: Record<string, AssistantTranscriptMessage[]>; failNext: string | null };
function fixtureFingerprint(): number { const s = JSON.stringify(loadFixtures(emptyDb())); let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; }
const FINGERPRINT = fixtureFingerprint();
function readSession(): Persisted | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Persisted;
    return p.fingerprint === FINGERPRINT && p.db && Array.isArray(p.db.projects) ? p : null;
  } catch { return null; }
}
let persistTimer: ReturnType<typeof setTimeout> | null = null;
function writeSession(s: AppState) {
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    try { const p: Persisted = { fingerprint: FINGERPRINT, db: s.db, viewConfig: s.viewConfig, user: s.user, assistantMessages: s.assistantMessages, failNext: s.mock.failNext }; sessionStorage.setItem(SESSION_KEY, JSON.stringify(p)); } catch { /* storage unavailable or full: run in memory only */ }
  }, 0);
}
function clearSession() { try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ } }
const restored = readSession();

function readMockConfig(): MockConfig {
  const base: MockConfig = { latencyMs: 250, failureRate: 0, failNext: null };
  try {
    const raw = localStorage.getItem("iel.mockConfig");
    if (raw) return { ...base, ...(JSON.parse(raw) as Partial<MockConfig>), failNext: null };
  } catch { /* storage unavailable: run with defaults */ }
  return base;
}

export const useAppStore = create<AppState>((set) => ({
  db: restored?.db ?? loadFixtures(emptyDb()),
  version: 0,
  mock: { ...readMockConfig(), failNext: restored?.failNext ?? null },
  user: restored?.user ?? DEFAULT_USER,
  assistantOpen: false,
  viewConfig: restored?.viewConfig ?? {},
  devState: null,
  assistantMessages: restored?.assistantMessages ?? {},
  setDevState: (devState) => set((s) => ({ devState, version: s.version + 1 })),
  appendAssistantMessages: (projectId, msgs) => set((s) => ({ assistantMessages: { ...s.assistantMessages, [projectId]: [...(s.assistantMessages[projectId] ?? []), ...msgs] } })),
  clearAssistant: (projectId) => set((s) => ({ assistantMessages: { ...s.assistantMessages, [projectId]: [] } })),
  mutate: (fn) => set((s) => { const db = structuredClone(s.db); fn(db); return { db, version: s.version + 1 }; }),
  setMock: (patch) => set((s) => {
    const mock = { ...s.mock, ...patch };
    try { localStorage.setItem("iel.mockConfig", JSON.stringify({ latencyMs: mock.latencyMs, failureRate: mock.failureRate })); } catch { /* ignore */ }
    return { mock };
  }),
  setUser: (user) => set({ user }),
  setAssistantOpen: (assistantOpen) => set({ assistantOpen }),
  setViewConfig: (projectId, patch) => set((s) => ({ viewConfig: { ...s.viewConfig, [projectId]: { panelOrder: [], hiddenPanels: [], filters: {}, chosenTestIds: [], ...s.viewConfig[projectId], ...patch } } })),
  resetToSampleData: () => { clearSession(); set((s) => ({ db: loadFixtures(emptyDb()), version: s.version + 1, viewConfig: {}, user: DEFAULT_USER, devState: null, assistantMessages: {}, mock: { ...s.mock, failNext: null } })); },
}));

useAppStore.subscribe((s, prev) => {
  if (s.db !== prev.db || s.viewConfig !== prev.viewConfig || s.user !== prev.user || s.assistantMessages !== prev.assistantMessages || s.mock.failNext !== prev.mock.failNext) writeSession(s);
});

/** Non-React access for services. */
export const store = {
  get: () => useAppStore.getState(),
  db: () => useAppStore.getState().db,
  mutate: (fn: (db: Db) => void) => useAppStore.getState().mutate(fn),
};
