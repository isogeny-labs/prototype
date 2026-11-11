// Typed client for the backend API. Everything the screens know about the
// server goes through here.

export type ClaimKind =
  | "protocol_versions"
  | "cipher_suites"
  | "key_exchange"
  | "certificate"
  | "signature_algorithm";

export type LocationKind = "server" | "software" | "unknown";

export type ResultValue = "True" | "False" | "Couldn't check";

export interface DemoServer {
  address: string;
  running: boolean;
  error: string | null;
}

export type Mode = "demo" | "isolated";

export interface Session {
  setup_required: boolean;
  logged_in: boolean;
  mode: Mode;
  /** The sentence under the header saying how software is run, written by the backend. */
  mode_line: string;
  demo_server: DemoServer;
}

export interface Claim {
  id: number;
  ref: string;
  location: string;
  location_kind: LocationKind;
  kind: ClaimKind;
  claimed_value: string;
  text: string;
  source: string;
}

export interface Address {
  address: string;
  host: string;
  port: number;
  resolved_ip: string | null;
  is_loopback: boolean;
  confirmed: boolean;
  error: string | null;
}

/** Something in the file that this version doesn't check (for example a hash algorithm). */
export interface SkippedItem {
  name: string;
  what: string;
  source: string;
  reason: string;
}

export interface Import {
  id: number;
  filename: string;
  format: "cyclonedx-cbom" | "csv";
  is_demo: boolean;
  claims: Claim[];
  addresses: Address[];
  /** Always sent by the current backend; optional so an older reply doesn't break the screen. */
  skipped?: SkippedItem[];
}

export interface Evidence {
  title: string;
  command: string;
  output: string;
  started_at: string;
  duration_ms: number;
  tool: string;
  tool_version: string;
}

export interface Result {
  claim_id: number;
  claim: Claim;
  result: ResultValue;
  found: string;
  reason: string | null;
  evidence: Evidence[];
}

export interface VerifyRun {
  id: number;
  import_id: number;
  started_at: string;
  finished_at: string;
  results: Result[];
}

// ---- Phase 2: test plan and Evidence Lab. All wording comes from the backend. ----

export type TestKind =
  | "tls_versions"
  | "certificate"
  | "official_vectors"
  | "bad_signatures"
  | "speed_size"
  | "pq_readiness"
  | "mldsa_compare";

export type ResultCode =
  | "passed"
  | "failed"
  | "couldnt_run"
  | "couldnt_trust"
  | "measured"
  | "no_slowdown"
  | "slowdown"
  | "offered"
  | "not_offered";

export type Tone = "pass" | "fail" | "neutral" | "warn";
export type JobStatus = "not_run" | "waiting" | "running" | "done";
export type RichPart = { t: "text" | "mono" | "tag" | "time"; v: string };
export type RichText = RichPart[];

export interface Progress {
  text: string;
  percent: number | null;
}

export interface Badge {
  code: ResultCode;
  label: string;
  tone: Tone;
}

export interface TestCard {
  id: number;
  kind: TestKind;
  title: string;
  origin: "suggested" | "added";
  tag: string | null;
  description: string;
  why: string;
  status: JobStatus;
  status_text: string;
  progress: Progress | null;
  result: Badge | null;
  can_run: boolean;
  can_remove: boolean;
}

export interface CatalogItem {
  catalog_id: TestKind;
  title: string;
  tag: string | null;
  description: string;
}

export interface PlanView {
  id: number;
  import_id: number;
  is_demo: boolean;
  intro: string;
  subject: RichText;
  running: boolean;
  can_run_all: boolean;
  has_results: boolean;
  max_parallel: number;
  tests: TestCard[];
  catalog_title: string;
  catalog: CatalogItem[];
  catalog_note: string;
}

export interface MetaItem {
  label: string | null;
  value: string;
  tag: string | null;
  time?: string;
  href?: string;
}

export interface TableColumn {
  label: string;
  align: "left" | "right";
  mono?: boolean;
}

export type EvidenceBlock =
  | {
      type: "table";
      title: string;
      tag: string | null;
      columns: TableColumn[];
      rows: string[][];
      meta: MetaItem[];
      note: string | null;
    }
  | { type: "text"; title: string; tag: string | null; text: string };

export interface RunRecordView {
  title: string;
  command: string;
  outputs: { title: string; text: string }[];
  meta: MetaItem[];
}

export interface LockedTestView {
  title: string;
  fields: { label: string; lines: string[] }[];
  locked_at: string;
  locked_text: string;
  fingerprint_label: string;
  fingerprint: string;
  note: string;
}

export interface ResearchView {
  id: number;
  title: string;
  badge: string;
  status: string;
  status_line: string;
  fields: { label: string; value: string }[];
  saved_at: string;
  note: string;
}

export interface LabResult extends Badge {
  run_id: number;
  component: string | null;
  mode: Mode;
  finished_at: string;
  duration_ms: number;
  summary: string;
  short: string;
  control: { outcome: "as_expected" | "not_as_expected" | "errored" | "not_run"; line: string; text: string };
  what_happened: string[];
  shows_title: string;
  shows: string[];
  evidence: EvidenceBlock[];
  run_record: RunRecordView;
  locked_test: LockedTestView;
  fix_title: string;
  suggested_fix: string | null;
  reviewed: { at: string; text: string } | null;
  research: ResearchView | null;
}

export interface RowStatus {
  status: JobStatus;
  status_text: string;
  progress: Progress | null;
}

export interface LabRow {
  item_id: number;
  kind: TestKind;
  title: string;
  control_line: string;
  result: LabResult | null;
  result_status: RowStatus | null;
  after: LabResult | null;
  after_status: RowStatus | null;
}

export interface RetestVersion {
  version: string;
  label: string;
  tag: string;
  note: string;
}

export interface LabView {
  plan_id: number;
  is_demo: boolean;
  view: "results" | "before_after";
  subline: RichText;
  disclaimer: string;
  columns: { test: string; before: string; after: string } | null;
  rows: LabRow[];
  retest: {
    can_start: boolean;
    blocked_reason: string | null;
    running: boolean;
    progress_text: string | null;
    menu_title: string;
    versions: RetestVersion[];
    menu_note: string;
  };
  download: { can_start: boolean; blocked_reason: string | null };
}

export interface EvidenceExport {
  id: number;
  created_at: string;
  fingerprint: string;
  fingerprint_label: string;
  json: { url: string; filename: string };
  html: { url: string; filename: string };
  message: string;
  verify_hint: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly line: number | null;
  readonly field: string | null;

  constructor(status: number, message: string, line: number | null = null, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.line = line;
    this.field = field;
  }
}

let onUnauthorized: (() => void) | null = null;

/** The app registers this so it can show the login screen when the session ends. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toApiError(status: number, body: unknown): ApiError {
  if (isRecord(body)) {
    const err = body["error"];
    if (isRecord(err) && typeof err["message"] === "string") {
      return new ApiError(
        status,
        err["message"],
        typeof err["line"] === "number" ? err["line"] : null,
        typeof err["field"] === "string" ? err["field"] : null,
      );
    }
    if (typeof body["detail"] === "string") {
      return new ApiError(status, body["detail"]);
    }
  }
  return new ApiError(status, `Something went wrong (the server answered ${status}).`);
}

interface RequestOptions {
  method?: "GET" | "POST";
  json?: unknown;
  raw?: Blob;
  /** Don't treat 401 as "session ended" (used by the login call itself). */
  quiet401?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = { method: options.method ?? "GET", credentials: "same-origin" };
  if (options.json !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.json);
  } else if (options.raw !== undefined) {
    init.headers = { "Content-Type": "application/octet-stream" };
    init.body = options.raw;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Can't reach the app. Check that it is still running, then try again.");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.quiet401 && onUnauthorized) {
      onUnauthorized();
    }
    throw toApiError(response.status, body);
  }
  return body as T;
}

async function orNullOn404<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const MAX_UPLOAD_BYTES = 1024 * 1024;

export const api = {
  getSession: () => request<Session>("/api/session"),

  setup: (password: string) =>
    request<{ ok: true }>("/api/setup", { method: "POST", json: { password }, quiet401: true }),

  login: (password: string) =>
    request<{ ok: true }>("/api/login", { method: "POST", json: { password }, quiet401: true }),

  importDemo: () => request<Import>("/api/import/demo", { method: "POST" }),

  /** Sends the file's raw bytes. The server only reads it as data. */
  importFile: (file: File) =>
    request<Import>(`/api/import/file?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      raw: file,
    }),

  getCurrentImport: () => orNullOn404(request<Import>("/api/import/current")),

  confirmAddress: (importId: number, address: string, confirmed: boolean) =>
    request<Address>(`/api/import/${importId}/confirm-address`, {
      method: "POST",
      json: { address, confirmed },
    }),

  verify: (importId: number) => request<VerifyRun>(`/api/import/${importId}/verify`, { method: "POST" }),

  getLatestVerify: (importId: number) => orNullOn404(request<VerifyRun>(`/api/import/${importId}/verify`)),

  // The test plan. Every call answers with the whole plan as it now stands.
  getPlan: (importId: number) => orNullOn404(request<PlanView>(`/api/import/${importId}/plan`)),

  ensurePlan: (importId: number) => request<PlanView>(`/api/import/${importId}/plan`, { method: "POST" }),

  pollPlan: (planId: number) => request<PlanView>(`/api/plans/${planId}`),

  reorder: (planId: number, order: number[]) =>
    request<PlanView>(`/api/plans/${planId}/order`, { method: "POST", json: { order } }),

  addTest: (planId: number, catalogId: TestKind) =>
    request<PlanView>(`/api/plans/${planId}/tests`, { method: "POST", json: { catalog_id: catalogId } }),

  removeTest: (planId: number, itemId: number) =>
    request<PlanView>(`/api/plans/${planId}/tests/${itemId}/remove`, { method: "POST" }),

  runTest: (planId: number, itemId: number) =>
    request<PlanView>(`/api/plans/${planId}/tests/${itemId}/run`, { method: "POST" }),

  runAll: (planId: number) => request<PlanView>(`/api/plans/${planId}/run-all`, { method: "POST" }),

  // Evidence Lab. Results are only ever read from here; nothing in the screens sets one.
  getLab: (planId: number) => request<LabView>(`/api/plans/${planId}/lab`),

  markReviewed: (runId: number) => request<LabView>(`/api/runs/${runId}/mark-reviewed`, { method: "POST" }),

  digDeeper: (runId: number) => request<LabView>(`/api/runs/${runId}/dig-deeper`, { method: "POST" }),

  /** The version is one of the demo versions the backend listed. No software is sent. */
  retest: (planId: number, version: string) =>
    request<LabView>(`/api/plans/${planId}/retest`, { method: "POST", json: { version } }),

  exportEvidence: (planId: number) => request<EvidenceExport>(`/api/plans/${planId}/evidence`, { method: "POST" }),
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}
