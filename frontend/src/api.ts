// Typed client for the backend API. Everything the screens know about the
// server goes through here.
//
// The data types are generated from the backend's API description (src/api.gen.ts, made by
// `npm run gen:api` from src/api-schema.json); they are written once, in backend/app/web/models.py.

export type {
  ClaimKind,
  MeasurementResult,
  LocationKind,
  ResultValue,
  DemoServer,
  Mode,
  Session,
  Claim,
  Address,
  SkippedItem,
  Import,
  ImportSetting,
  Evidence,
  Result,
  VerifyRun,
  TestKind,
  ResultCode,
  Tone,
  JobStatus,
  RichPart,
  RichText,
  Progress,
  Badge,
  TestCard,
  PlanGroup,
  NotTested,
  CatalogItem,
  PlanView,
  MetaItem,
  TableColumn,
  EvidenceBlock,
  RunRecordView,
  LockedTestView,
  ResearchView,
  Advisories,
  LabResult,
  RowStatus,
  LabRow,
  RetestVersion,
  LabView,
  EvidenceExport,
  FixLine,
  FixStatusKey,
  FixStatus,
  StrongLabel,
  DiffLine,
  ChangePart,
  ProofCell,
  ProofWaiting,
  ProofRow,
  ProofTable,
  ProofVerdict,
  DetailFact,
  RanOn,
  TextSuggestion,
  FixSection,
  ReviewerOption,
  ApprovalRowView,
  FixApprovers,
  FixAction,
  FixButton,
  FixDetail,
  FixesView,
  MigrationStatusCode,
  TrackStatusCode,
  MigrationOptionKey,
  MigrationStatus,
  MigrationLine,
  MigrationSettingField,
  MigrationCostTable,
  MigrationChooseBox,
  MigrationOption,
  MigrationSystem,
  TrackKey,
  MigrationTrack,
  ChangeAction,
  ChangeButton,
  ChangeStep,
  ChangeSection,
  ChangeBadge,
  TryView,
  ApprovalsView,
  ApplyView,
  ChangeView,
  MigrationRoadmapRow,
  MigrationRoadmapBand,
  MigrationView,
  DependencyQuestionKey,
  DependencyAnswer,
  DependencyLabel,
  DependencyState,
  DependencyCell,
  DependencyBlock,
  DependencyLookup,
  DependencyMeasurement,
  DependencyRow,
  DependencyGroup,
  DependencySystem,
  DependenciesView,
} from "./api.gen";
import type {
  Session,
  Address,
  Import,
  VerifyRun,
  TestKind,
  PlanView,
  LabView,
  EvidenceExport,
  FixesView,
  MigrationOptionKey,
  MigrationSettingField,
  MigrationView,
  DependenciesView,
} from "./api.gen";

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
      // A form's refusal can name its field too: {detail, field}.
      return new ApiError(status, body["detail"], null, typeof body["field"] === "string" ? body["field"] : null);
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
/** Dependency lists (phase 4d) can be larger than a claims file: up to 16 MB. */
export const MAX_DEPENDENCY_LIST_BYTES = 16 * 1024 * 1024;

function fixPath(planId: number, fixId: string): string {
  return `/api/plans/${planId}/fixes/${encodeURIComponent(fixId)}`;
}

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
  retest: (planId: number, version: string, component?: string) =>
    request<LabView>(`/api/plans/${planId}/retest`, {
      method: "POST",
      json: component !== undefined ? { version, component } : { version },
    }),

  exportEvidence: (planId: number) => request<EvidenceExport>(`/api/plans/${planId}/evidence`, { method: "POST" }),

  // The Fixes step. Every call answers with the whole view as it now stands. Nothing here sends code.
  getFixes: (planId: number) => request<FixesView>(`/api/plans/${planId}/fixes`),

  connectCode: (planId: number) => request<FixesView>(`/api/plans/${planId}/fixes/connect`, { method: "POST" }),

  runProofAgain: (planId: number, fixId: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/proof`, { method: "POST" }),

  openPullRequest: (planId: number, fixId: string, reviewers: string[]) =>
    request<FixesView>(`${fixPath(planId, fixId)}/pull-request`, { method: "POST", json: { reviewers } }),

  approve: (planId: number, fixId: string, reviewer: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/approve`, { method: "POST", json: { reviewer } }),

  /** Only the "Confirm merge" button calls this. */
  mergePullRequest: (planId: number, fixId: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/merge`, { method: "POST" }),

  /** The same retest as "Retest new version", on the merged version. Answers with the Evidence Lab view. */
  retestNow: (planId: number, fixId: string) =>
    request<LabView>(`${fixPath(planId, fixId)}/retest`, { method: "POST" }),

  // The Dependencies view of the Migration step (phase 4d). Every call answers with the whole view as it now stands.
  getDependencies: (importId: number) => request<DependenciesView>(`/api/import/${importId}/dependencies`),

  /** Sends the list's raw bytes. The server only reads it as data; nothing in it is run. */
  addDependencyList: (planId: number, file: File) =>
    request<DependenciesView>(`/api/plans/${planId}/dependencies?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      raw: file,
    }),

  /** "Part of": the system of the file a top entry of the list belongs to; "" is "None of these". */
  tieDependency: (planId: number, top: string, system: string) =>
    request<DependenciesView>(`/api/plans/${planId}/dependencies/tie`, { method: "POST", json: { top, system } }),

  /** One library (row id), or every library that can be measured (null). Isolated mode only. */
  measureDependencies: (planId: number, row: string | null) =>
    request<DependenciesView>(`/api/plans/${planId}/dependencies/measure`, { method: "POST", json: row ? { row } : {} }),

  // The Migration step. Every call answers with the whole view as it now stands. The GET makes the test plan if there is none.
  getMigration: (importId: number) => request<MigrationView>(`/api/import/${importId}/migration`),

  measureMigration: (planId: number) =>
    request<MigrationView>(`/api/plans/${planId}/migration/measure`, { method: "POST", json: {} }),

  saveMigrationSetting: (planId: number, system: string, field: MigrationSettingField["field"], value: string) =>
    request<MigrationView>(`/api/plans/${planId}/migration/settings`, { method: "POST", json: { system, field, value } }),

  /** Only "Save choice" calls this. */
  saveMigrationChoice: (
    planId: number,
    system: string,
    option: MigrationOptionKey,
    reason: string,
    reviewDate: string | null,
  ) =>
    request<MigrationView>(`/api/plans/${planId}/migration/choice`, {
      method: "POST",
      json: { system, option, reason, review_date: reviewDate },
    }),

  // Phase 4b: the change box. Each POST answers { ok: true }; the screen then loads its own view again.
  changeTry: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/try`, { method: "POST", json: { change } }),

  changeAskApproval: (planId: number, change: string, reviewers: string[]) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/ask-approval`, { method: "POST", json: { change, reviewers } }),

  changeApprove: (planId: number, change: string, reviewer: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/approve`, { method: "POST", json: { change, reviewer } }),

  changeApply: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/apply`, { method: "POST", json: { change } }),

  changeRollback: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/rollback`, { method: "POST", json: { change } }),

  /** The address of the change file; the page saves it like the evidence files. */
  changeDownloadUrl: (planId: number, change: string) =>
    `/api/plans/${planId}/changes/download?change=${encodeURIComponent(change)}`,
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}
