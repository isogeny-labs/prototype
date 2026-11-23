import type {
  AssessmentBrief,
  AssessmentCounts,
  AssessmentStatus,
  AssessmentView,
  OverviewBlocks,
  DemoProjectsLoaded,
  ProjectView,
  Workspace,
  WorkspaceFolder,
  WorkspaceProject,
} from "../api";
import { demoImport, plan, run } from "./fixtures";

/** Phase 5a: the workspace, assessment and project payloads the shell screens are drawn from. */

export const ORG = "Acme Security";
export const NO_COUNTS: AssessmentCounts = { claims: null, tests: null, fixes: null, systems: null };
export const FULL_COUNTS: AssessmentCounts = {
  claims: { checked: 12, false: 3, true: 8, couldnt_check: 1 },
  tests: { run: 5, failed: 2, passed: 3 },
  fixes: { total: 4, open: 2 },
  systems: { total: 6, classical: 3, hybrid: 2, pq_only: 0, couldnt_check: 1, not_measured: 0 },
};

export const CLOSED_LINE =
  "It was closed because a newer assessment was started. This assessment is closed. Start a new one to continue.";

const OPEN: AssessmentStatus = { key: "open", label: "Open", closed_line: null, signoff: null };
const CLOSED: AssessmentStatus = { key: "closed", label: "Closed", closed_line: CLOSED_LINE, signoff: null };

function brief(id: number, number: number, closed: boolean, file = true): AssessmentBrief {
  return {
    id,
    number,
    title: `Assessment ${number}`,
    name: null,
    status: closed ? CLOSED : OPEN,
    archived: false,
    created_at: "2026-11-10T09:00:00Z",
    closed_at: closed ? "2026-11-11T09:00:00Z" : null,
    purpose: { key: "full_review", label: "Full review" },
    reference: null,
    file: file
      ? {
          import_id: 7,
          filename: "acme-pay-cbom.json",
          format: "cyclonedx-cbom",
          is_demo: true,
          imported_at: "2026-11-10T09:05:00Z",
        }
      : null,
  };
}

export const folders: WorkspaceFolder[] = [
  { id: 1, name: "Payments", parent_id: null, archived: false, path: [] },
  { id: 2, name: "EU", parent_id: 1, archived: false, path: [{ id: 1, name: "Payments" }] },
  { id: 3, name: "Old stuff", parent_id: null, archived: true, path: [] },
];

function project(over: Partial<WorkspaceProject> & Pick<WorkspaceProject, "id" | "name">): WorkspaceProject {
  return {
    folder_id: null,
    archived: false,
    is_demo: false,
    created_at: "2026-11-10T08:00:00Z",
    path: [],
    assessments: 1,
    latest: null,
    counts: NO_COUNTS,
    ...over,
    open_count: over.open_count ?? (over.latest && over.latest.status.key === "open" ? 1 : 0),
    closed_count:
      over.closed_count ??
      Math.max(0, (over.assessments ?? 1) - (over.latest && over.latest.status.key === "open" ? 1 : 0)),
  };
}

/** Acme Pay sits two folders deep (Payments / EU), Ledger at the top, Legacy is archived, and Retired is in an archived folder. */
export const acmePay = project({
  id: 10,
  name: "Acme Pay",
  folder_id: 2,
  path: [
    { id: 1, name: "Payments" },
    { id: 2, name: "EU" },
  ],
  is_demo: true,
  assessments: 2,
  latest: brief(101, 2, false),
  counts: FULL_COUNTS,
});
export const ledger = project({ id: 11, name: "Ledger", latest: brief(111, 1, false, false), counts: NO_COUNTS });
export const legacy = project({ id: 12, name: "Legacy", archived: true, latest: brief(121, 1, true) });
export const retired = project({
  id: 13,
  name: "Retired",
  folder_id: 3,
  path: [{ id: 3, name: "Old stuff" }],
  latest: brief(131, 1, true),
});

export const PURPOSES = [
  { key: "full_review", label: "Full review" },
  { key: "compliance_review", label: "Compliance review" },
  { key: "migration_wave", label: "Migration wave" },
  { key: "release_check", label: "Release check" },
  { key: "advisory_response", label: "Advisory response" },
  { key: "other", label: "Other" },
];
export const ONE_LOGIN_LINE =
  "This app has one login, so whoever is at the keyboard records the name. It is kept with the time, in the assessment and in its evidence.";
const WORKSPACE_EXTRAS = { purposes: PURPOSES, one_login_line: ONE_LOGIN_LINE, algorithm_names: [] };

export const workspace: Workspace = {
  organization: ORG,
  folders,
  projects: [acmePay, ledger, legacy, retired],
  ...WORKSPACE_EXTRAS,
};
export const emptyWorkspace: Workspace = { organization: ORG, folders: [], projects: [], ...WORKSPACE_EXTRAS };

export const withImport = { ...demoImport, assessment_id: 101 };

const link = (page: string, group: string | null = null) => ({ page, item: null, group, assessment_id: null });
const none = { open: 0, in_progress: 0, done: 0 };
/** The Overview's blocks for the open Acme Pay assessment, as the backend reads them from each page. */
export const OVERVIEW_BLOCKS: OverviewBlocks = {
  groups: [
    {
      key: "verification",
      label: "Verification",
      question: "Is the scanner file true?",
      checks: { open: 0, in_progress: 0, done: 12 },
      fixes: null,
      facts: [
        { label: "True", value: 7, link: link("inventory/verify", "verification") },
        { label: "False", value: 3, link: link("inventory/verify", "verification") },
        { label: "Couldn't check", value: 2, link: link("inventory/verify", "verification") },
      ],
      // 22 November 2026: how many of the group's checks rest on each source, in the backend's order and words
      source_counts: [
        {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          count: 8,
        },
        {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          count: 2,
        },
        {
          key: "file",
          label: "From your file",
          meaning: "Nothing has been observed or run for it yet: it rests only on your file.",
          count: 2,
        },
      ],
      empty_text: null,
    },
    {
      key: "encryption",
      label: "Crypto tests",
      question: "Is the cryptography built right?",
      checks: { open: 0, in_progress: 0, done: 5 },
      fixes: { open: 1, in_progress: 1, done: 0 },
      facts: [
        { label: "Passed", value: 3, link: link("evidence", "encryption") },
        { label: "Failed", value: 2, link: link("evidence", "encryption") },
      ],
      empty_text: null,
    },
    {
      key: "migration",
      label: "Migration",
      question: "Where does each system stand on the move to post-quantum, and what must change?",
      checks: none,
      fixes: none,
      facts: [],
      empty_text: "Nothing measured yet. Measure status is on Migration.",
    },
    {
      key: "dependencies",
      label: "Dependencies",
      question: "What can your libraries do?",
      checks: none,
      fixes: none,
      facts: [],
      empty_text: "No dependency list yet. Add one on Dependencies.",
    },
  ],
  findings: [
    { label: "False claims", value: 3, link: link("inventory/verify", "verification") },
    { label: "Failed tests", value: 2, link: link("evidence", "encryption") },
    { label: "Dependency blockers", value: 0, link: link("migration/dependencies", "dependencies") },
  ],
  evidence: { runs: 6, last_download: null },
};

export function assessmentView(over: Partial<AssessmentView> = {}): AssessmentView {
  return {
    id: 101,
    number: 2,
    title: "Assessment 2",
    name: null,
    status: OPEN,
    archived: false,
    created_at: "2026-11-10T09:00:00Z",
    closed_at: null,
    purpose: { key: "full_review", label: "Full review" },
    reference: null,
    file: brief(101, 2, false).file,
    organization: ORG,
    project: { id: 10, name: "Acme Pay", is_demo: true, archived: false },
    path: [
      { id: 1, name: "Payments" },
      { id: 2, name: "EU" },
    ],
    import: { ...demoImport, assessment_id: 101 },
    plan_id: 1,
    has_verify: true,
    has_results: true,
    has_migration: false,
    counts: FULL_COUNTS,
    blocks: OVERVIEW_BLOCKS,
    next_step: {
      page: "checks",
      label: "Open checks",
      text: "Run the suggested tests on what the file names. The test plan is on Checks.",
    },
    ...over,
  };
}

export const openAssessment: AssessmentView = assessmentView();
export const closedAssessment: AssessmentView = assessmentView({
  id: 100,
  number: 1,
  title: "Assessment 1",
  status: CLOSED,
  closed_at: "2026-11-11T09:00:00Z",
  file: brief(100, 1, true).file,
  next_step: {
    page: "overview",
    label: "New assessment",
    text: "This assessment is closed. Start a new one to continue.",
  },
});
export const emptyAssessment: AssessmentView = assessmentView({
  id: 111,
  number: 1,
  title: "Assessment 1",
  project: { id: 11, name: "Ledger", is_demo: false, archived: false },
  path: [],
  file: null,
  import: null,
  plan_id: null,
  has_verify: false,
  has_results: false,
  counts: NO_COUNTS,
  blocks: null,
  next_step: { page: "inventory/import", label: "Import a file", text: "Bring in a scanner file to start." },
});

export const acmePayView: ProjectView = {
  id: 10,
  name: "Acme Pay",
  folder_id: 2,
  archived: false,
  is_demo: true,
  path: acmePay.path,
  assessments: [brief(101, 2, false), brief(100, 1, true)],
  next_name: "Assessment 3",
};

export const demoLoaded: DemoProjectsLoaded = {
  added: ["Acme Pay", "Migration demo"],
  summary: "Added 2 demo projects.",
  notices: [],
  open_assessment_id: 101,
};

export const demoWorkspace: Workspace = {
  organization: ORG,
  ...WORKSPACE_EXTRAS,
  folders: [{ id: 5, name: "Demo", parent_id: null, archived: false, path: [] }],
  projects: [
    project({
      id: 20,
      name: "Acme Pay",
      folder_id: 5,
      path: [{ id: 5, name: "Demo" }],
      is_demo: true,
      latest: brief(201, 1, false),
      counts: NO_COUNTS,
    }),
    project({
      id: 21,
      name: "Migration demo",
      folder_id: 5,
      path: [{ id: 5, name: "Demo" }],
      is_demo: true,
      latest: brief(211, 1, false),
      counts: NO_COUNTS,
    }),
  ],
};

/** The calls an open Acme Pay assessment makes when the shell loads it. */
export const acmeRoutes = {
  "GET /api/workspace": { body: workspace },
  "GET /api/assessments/101": { body: openAssessment },
  "GET /api/import/7/verify": { body: run },
  "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
  "GET /api/projects/10": { body: acmePayView },
};
