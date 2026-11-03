/** Single source for the left-nav route list; docs/ROUTES.md mirrors it. */
export const PROJECT_NAV: Array<{ path: string; label: string; end?: boolean }> = [
  { path: "", label: "Overview", end: true },
  { path: "intake", label: "Intake" },
  { path: "artifacts", label: "Artifacts" },
  { path: "tests", label: "Tests" },
  { path: "research", label: "Research" },
  { path: "conductor", label: "Conductor" },
  { path: "runs", label: "Runs" },
  { path: "findings", label: "Findings" },
  { path: "approvals", label: "Approvals" },
  { path: "changes", label: "Changes" },
  { path: "reports", label: "Reports" },
  { path: "memory", label: "Memory" },
  { path: "settings", label: "Settings" },
];
