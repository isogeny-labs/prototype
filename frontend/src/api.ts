// Typed client for the backend API. Everything the screens know about the
// server goes through here.
//
// The data types are generated from the backend's API description (src/api.gen.ts, made by
// `npm run gen:api` from src/api-schema.json); they are written once, in backend/app/web/models.py.

export type {
  TryClients,
  TryClientRow,
  Impact,
  ImpactLine,
  ImpactPart,
  AssistantFact,
  AssistantReply,
  WhatIf,
  WhatIfGroup,
  WhatIfLine,
  AssistantGo,
  AssistantBox,
  AssistantView,
  AssistantTab,
  AssistantEntry,
  AssistantDecision,
  AssistantConfirm,
  AssistantStep,
  AssistantAction,
  AssistantThread,
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
  ClaimCounts,
  TestCounts,
  FixCounts,
  SystemCounts,
  AssessmentCounts,
  AssessmentStatus,
  AssessmentFile,
  AssessmentBrief,
  PathStep,
  WorkspaceFolder,
  WorkspaceProject,
  Workspace,
  Created,
  ProjectView,
  AssessmentProject,
  NextStep,
  AssessmentView,
  DemoProjectsLoaded,
  // Phase 5b
  GroupKey,
  ItemState,
  ItemLink,
  StateCounts,
  CameFrom,
  CheckResult,
  CheckRow,
  SameMeasurement,
  CheckGroup,
  LibraryEvidenceRow,
  ChecksView,
  CheckRun,
  RelatedItem,
  RelatedLine,
  CheckDetail,
  RelatedView,
  FixCameFrom,
  FixGroup,
  FixGroupAlso,
  Purpose,
  Signoff,
  AlgorithmName,
  OverviewFact,
  OverviewGroup,
  OverviewBlocks,
  ProjectOverview,
  ProjectOverviewRow,
  Compare,
  CompareList,
  CompareItem,
  SharedSystem,
  // Phase 5c
  OttoSettingsView,
  OttoPacksSection,
  OttoPackCard,
  OttoRefusedPack,
  OttoUpdate,
  OttoUpdateDialog,
  OttoHarnessLine,
  OttoAnswersLine,
  OttoLiveSection,
  OttoLiveSwitch,
  OttoLiveLimit,
  AdvisoriesView,
  AdvisoryWaiting,
  ChangeWatchView,
  ChangeRow,
  ChangePanel,
  ChangeFile,
  ChangeTest,
  ChangeResult,
  ChangeResultSide,
  ChangeFlag,
  DemoChangeItem,
  AdvisoryProposalCell,
  OttoProposal,
  OttoProposalButton,
  OttoProposalStatus,
  OttoProposalHistory,
  OttoDecisionLine,
  OttoRejectDialog,
  OttoProposalsView,
  OttoResultBlock,
  OttoWaiting,
  OttoWaitingItem,
  OttoPlanBlock,
  OttoRoadmapMark,
  OttoProjectBlock,
  OttoProjectRow,
  ImportOtto,
  CheckFromOtto,
  DependencyAdvisory,
  DependencyAdvisoryState,
  DependencyOttoStatus,
  FixProofRow,
  LabeledLink,
  AdvisoryFilterOption,
  AdvisoryRow,
  AdvisoryTestCell,
  AdvisoryResultCell,
  AdvisoryPanel,
  AdvisoryQuote,
  AdvisorySource,
  AdvisoryAffected,
  AdvisoryTestBlock,
  AdvisoryTrial,
  AdvisoryLedger,
  AdvisoryLedgerEntry,
  AdvisoryNoTest,
  AdvisoryHere,
  AdvisoryHereRow,
  AdvisoryHereResult,
  AdvisoryFix,
  AdvisoryFixHere,
  AdvisoryClaude,
  AdvisoryStep,
} from "./api.gen";
import { notifyChanged } from "./changes";
import { TIMES_ASK, TIMES_HEADER, withLocalTimes } from "./time";
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
  Workspace,
  Created,
  ProjectView,
  AssessmentView,
  DemoProjectsLoaded,
  ChecksView,
  CheckDetail,
  RelatedView,
  ProjectOverview,
  OttoSettingsView,
  AdvisoriesView,
  ChangeWatchView,
  OttoProposal,
  OttoProposalsView,
  AssistantView,
  AssistantReply,
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

/** How many requests that are not reads have been answered (or have failed) so far. */
let changesAnswered = 0;
/** A read is asked again at most this often (see `request`). */
const MAX_ASKED_AGAIN = 2;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // The 5c fixes: every request asks the server to mark the times in its sentences, and every answer has them written
  // in the viewer's own time zone below, in this one place (src/time.ts). Downloads are plain links: they keep UTC.
  const asksForTimes = { [TIMES_HEADER]: TIMES_ASK };
  const isRead = (options.method ?? "GET") === "GET";
  const init: RequestInit = { method: options.method ?? "GET", credentials: "same-origin", headers: asksForTimes };
  if (options.json !== undefined) {
    init.headers = { "Content-Type": "application/json", ...asksForTimes };
    init.body = JSON.stringify(options.json);
  } else if (options.raw !== undefined) {
    init.headers = { "Content-Type": "application/octet-stream", ...asksForTimes };
    init.body = options.raw;
  }

  let response: Response;
  let body: unknown = null;
  // A read that was on its way while a change was answered may hold what was there before the change, and it would
  // land after the change's own answer and put the old state back on the page (19 November 2026: a test plan that
  // showed six tests after a seventh was added; the reads take turns on the server, so one can be on its way for a
  // while). Such a read is asked again, so what it gives is never older than a change this browser already has the
  // answer to. Nothing else is ever sent twice: a request that is not a read is sent once.
  for (let askedAgain = 0; ; askedAgain += 1) {
    const before = changesAnswered;
    try {
      response = await fetch(path, init);
    } catch {
      if (!isRead) changesAnswered += 1;
      throw new ApiError(0, "Can't reach the app. Check that it is still running, then try again.");
    }
    if (!isRead) changesAnswered += 1;
    try {
      body = withLocalTimes(await response.json());
    } catch {
      body = null;
    }
    if (!isRead || before === changesAnswered || askedAgain >= MAX_ASKED_AGAIN) break;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.quiet401 && onUnauthorized) {
      onUnauthorized();
    }
    throw toApiError(response.status, body);
  }
  // Phase 6a: anything that is not a read may have changed the assessment, so the Otto panel (and, when the panel sent
  // it, the open page) reads again. See src/changes.ts.
  if ((options.method ?? "GET") !== "GET") notifyChanged();
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

  /** Phase 5a: the screens always say which assessment the file goes into. */
  importDemo: (assessmentId?: number) =>
    request<Import>(`/api/import/demo${assessmentId ? `?assessment_id=${assessmentId}` : ""}`, { method: "POST" }),

  /** Sends the file's raw bytes. The server only reads it as data. */
  importFile: (file: File, assessmentId?: number) =>
    request<Import>(
      `/api/import/file?filename=${encodeURIComponent(file.name)}${assessmentId ? `&assessment_id=${assessmentId}` : ""}`,
      { method: "POST", raw: file },
    ),

  // Phase 5a: the organization, folders, projects and assessments.
  getWorkspace: () => request<Workspace>("/api/workspace"),
  setOrganization: (name: string) => request<Workspace>("/api/organization", { method: "POST", json: { name } }),
  createFolder: (name: string, parentId: number | null) =>
    request<Created>("/api/folders", { method: "POST", json: { name, parent_id: parentId } }),
  changeFolder: (id: number, change: { name?: string; parent_id?: number | null; move?: boolean; archived?: boolean }) =>
    request<Created>(`/api/folders/${id}`, { method: "POST", json: change }),
  createProject: (name: string, folderId: number | null) =>
    request<Created>("/api/projects", { method: "POST", json: { name, folder_id: folderId } }),
  getProject: (id: number) => request<ProjectView>(`/api/projects/${id}`),
  changeProject: (id: number, change: { name?: string; folder_id?: number | null; move?: boolean; archived?: boolean }) =>
    request<Created>(`/api/projects/${id}`, { method: "POST", json: change }),
  /** Phase 5b: the New assessment box (every field may be left out). It closes nothing. */
  newAssessment: (projectId: number, box: { name?: string; purpose?: string; reference?: string } = {}) =>
    request<Created>(`/api/projects/${projectId}/assessments`, { method: "POST", json: box }),
  /** Phase 5b: Rerun as new assessment: the same scanner file in a fresh assessment of the same project. */
  rerunAssessment: (id: number, box: { name?: string; purpose?: string; reference?: string } = {}) =>
    request<Created>(`/api/assessments/${id}/rerun`, { method: "POST", json: box }),
  getAssessment: (id: number) => request<AssessmentView>(`/api/assessments/${id}`),
  changeAssessment: (
    id: number,
    change: {
      name?: string;
      project_id?: number;
      archived?: boolean;
      close?: boolean;
      signed_off_by?: string;
      note?: string;
      purpose?: string;
      reference?: string;
    },
  ) => request<AssessmentView>(`/api/assessments/${id}`, { method: "POST", json: change }),
  getProjectOverview: (id: number, pick: { from?: number; to?: number; archived?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (pick.from) q.set("from_id", String(pick.from));
    if (pick.to) q.set("to_id", String(pick.to));
    if (pick.archived) q.set("archived", "true");
    const query = q.toString();
    return request<ProjectOverview>(`/api/projects/${id}/overview${query ? `?${query}` : ""}`);
  },
  // Phase 5b: every check of an assessment, one check's detail, and the Related block of any item.
  getChecks: (planId: number) => request<ChecksView>(`/api/plans/${planId}/checks`),
  getCheck: (planId: number, checkId: string) => request<CheckDetail>(`/api/plans/${planId}/checks/${encodeURIComponent(checkId)}`),
  getRelated: (planId: number, key: string) => request<RelatedView>(`/api/plans/${planId}/related?key=${encodeURIComponent(key)}`),
  loadDemoProjects: () => request<DemoProjectsLoaded>("/api/demo-projects", { method: "POST" }),

  // Phase 5c: Otto. Settings (Test packs, Live Otto) belong to the installation; Advisories and Otto's proposals to one
  // assessment. Every call answers with the whole view as it now stands. No key is ever sent or shown.
  getOtto: () => request<OttoSettingsView>("/api/otto"),
  /** Looks in the updates folder on this computer; nothing is downloaded. */
  checkPackUpdates: () => request<OttoSettingsView>("/api/otto/packs/check", { method: "POST" }),
  /** Only the Install button of the Install update box calls this. */
  installPack: (version: string) => request<OttoSettingsView>("/api/otto/packs/install", { method: "POST", json: { version } }),
  /** Use live Claude on or off, and/or the spending limit per run (US dollars, as typed). */
  setLiveOtto: (change: { on?: boolean; limit?: string }) => request<OttoSettingsView>("/api/otto/live", { method: "POST", json: change }),
  /** Phase 6a: the name a person types once; their decisions on proposals are recorded under it from then on. */
  setDecisionName: (name: string) => request<OttoSettingsView>("/api/otto/name", { method: "POST", json: { name } }),
  getAdvisories: (planId: number) => request<AdvisoriesView>(`/api/plans/${planId}/advisories`),
  /** Phase 6, Otto's research loop: one read of the public source about this assessment's libraries (package names
   * only are sent). It runs nothing and proposes nothing. Answers with the page's view as it now stands. */
  lookForAdvisories: (planId: number) => request<AdvisoriesView>(`/api/plans/${planId}/advisories/look`, { method: "POST" }),
  /** Design and prove tests for the new advisories of the newest look, in the background. */
  startResearch: (planId: number) => request<AdvisoriesView>(`/api/plans/${planId}/advisories/research`, { method: "POST" }),
  /** Every proposal of Otto's in this assessment, with the "Waiting for you" counts. */
  /** Phase 6a: what the Otto panel shows beside this page of this assessment, with this item open. A read: it runs
   * nothing and asks Claude nothing. */
  getAssistant: (assessmentId: number, page: string, item?: string | null) => {
    const params = new URLSearchParams({ page });
    if (item) params.set("item", item);
    return request<AssistantView>(`/api/assessments/${assessmentId}/assistant?${params.toString()}`);
  },
  /** Phase 6b: Otto's answer to one typed sentence, and nothing kept (a read: a closed assessment's text box, and an
   * assessment with no file yet). It decides and starts nothing. */
  getAnswer: (assessmentId: number, page: string, item: string | null, text: string) => {
    const params = new URLSearchParams({ text, page });
    if (item) params.set("item", item);
    return request<AssistantReply>(`/api/assessments/${assessmentId}/assistant/answer?${params.toString()}`);
  },
  /** Phase 6b: the same answer, and the exchange kept with the assessment (what was typed and the one line of the
   * answer). It decides and starts nothing: a card in the answer still waits for Confirm. */
  say: (planId: number, page: string, item: string | null, text: string) =>
    request<AssistantReply>(`/api/plans/${planId}/assistant/messages`, { method: "POST", json: { text, page, item } }),
  getProposals: (planId: number) => request<OttoProposalsView>(`/api/plans/${planId}/otto/proposals`),
  /** Otto proposes; a person decides: accept, reject (with an optional short reason), undo or reconsider one proposal.
   * It runs nothing. The answer is the proposal as it now stands. */
  decideProposal: (planId: number, proposalId: string, decision: "accept" | "reject" | "undo" | "reconsider", reason?: string) =>
    request<OttoProposal>(`/api/plans/${planId}/otto/proposals/${encodeURIComponent(proposalId)}/${decision}`, {
      method: "POST",
      json: reason ? { reason } : {},
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

  // Change watch (phase 6d). The read, and its two actions; neither action sends anything but its own address.
  getChangeWatch: (planId: number) => request<ChangeWatchView>(`/api/plans/${planId}/change-watch`),

  bringInDemoChange: (planId: number, key: string) =>
    request<ChangeWatchView>(`/api/plans/${planId}/change-watch/demo/${encodeURIComponent(key)}`, { method: "POST" }),

  runPickedTests: (planId: number, changeId: string) =>
    request<ChangeWatchView>(`/api/plans/${planId}/change-watch/${encodeURIComponent(changeId)}/run`, { method: "POST" }),

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
