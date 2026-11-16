import type { AssessmentBrief, AssessmentCounts, AssessmentView, DemoProjectsLoaded, ProjectView, Workspace, WorkspaceFolder, WorkspaceProject } from "../api";
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

export const CLOSED_LINE = "It was closed because a newer assessment was started. This assessment is closed. Start a new one to continue.";

const OPEN = { key: "open", label: "Open", closed_line: null } as const;
const CLOSED = { key: "closed", label: "Closed", closed_line: CLOSED_LINE } as const;

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
    file: file ? { import_id: 7, filename: "acme-pay-cbom.json", format: "cyclonedx-cbom", is_demo: true, imported_at: "2026-11-10T09:05:00Z" } : null,
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
  };
}

/** Acme Pay sits two folders deep (Payments / EU), Ledger at the top, Legacy is archived, and Retired is in an archived folder. */
export const acmePay = project({
  id: 10,
  name: "Acme Pay",
  folder_id: 2,
  path: [{ id: 1, name: "Payments" }, { id: 2, name: "EU" }],
  is_demo: true,
  assessments: 2,
  latest: brief(101, 2, false),
  counts: FULL_COUNTS,
});
export const ledger = project({ id: 11, name: "Ledger", latest: brief(111, 1, false, false), counts: NO_COUNTS });
export const legacy = project({ id: 12, name: "Legacy", archived: true, latest: brief(121, 1, true) });
export const retired = project({ id: 13, name: "Retired", folder_id: 3, path: [{ id: 3, name: "Old stuff" }], latest: brief(131, 1, true) });

export const workspace: Workspace = { organization: ORG, folders, projects: [acmePay, ledger, legacy, retired] };
export const emptyWorkspace: Workspace = { organization: ORG, folders: [], projects: [] };

export const withImport = { ...demoImport, assessment_id: 101 };

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
    file: brief(101, 2, false).file,
    organization: ORG,
    project: { id: 10, name: "Acme Pay", is_demo: true, archived: false },
    path: [{ id: 1, name: "Payments" }, { id: 2, name: "EU" }],
    import: { ...demoImport, assessment_id: 101 },
    plan_id: 1,
    has_verify: true,
    has_results: true,
    has_migration: false,
    counts: FULL_COUNTS,
    next_step: { page: "tests", label: "Go to Tests", text: "Run the suggested tests on the claims you verified." },
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
  next_step: { page: "overview", label: "New assessment", text: "This assessment is closed. Start a new one to continue." },
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
};

export const demoLoaded: DemoProjectsLoaded = {
  added: ["Acme Pay", "Migration demo"],
  summary: "Added 2 demo projects.",
  notices: [],
  open_assessment_id: 101,
};

export const demoWorkspace: Workspace = {
  organization: ORG,
  folders: [{ id: 5, name: "Demo", parent_id: null, archived: false, path: [] }],
  projects: [
    project({ id: 20, name: "Acme Pay", folder_id: 5, path: [{ id: 5, name: "Demo" }], is_demo: true, latest: brief(201, 1, false), counts: NO_COUNTS }),
    project({ id: 21, name: "Migration demo", folder_id: 5, path: [{ id: 5, name: "Demo" }], is_demo: true, latest: brief(211, 1, false), counts: NO_COUNTS }),
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
