import { useRef, useState } from "react";
import type { AssessmentBrief, AssessmentView, Workspace, WorkspaceProject } from "../../api";
import { pageHref, type Page, type Route } from "../../router";
import { StatusChip, useDismiss, Wordmark } from "../ui";
import { Icon } from "./icons";
import { ProjectSwitcher } from "./ProjectSwitcher";

export type PageAccess = Record<Page, { open: boolean; reason?: string }>;

interface Item {
  page: Page;
  label: string;
  icon: string;
  /** The views of a page that has several (Migration plan): listed under it while one of them is open. */
  views?: { page: Page; label: string; icon: string }[];
}

interface Step {
  /** The step's number on the path, 1 to 6. Evidence has none: it is kept all along. */
  n?: number;
  /** What the step is called. The Overview stands alone, above the path, and has none. */
  label?: string;
  items: Item[];
}

// The design refactor (26 November 2026): the pages of an open assessment as a path of six steps, in the order the
// work goes, and then Evidence, the record kept all along, with its four views. A page is listed once. The four work
// groups are tabs on their pages and are not repeated here; "Migration plan" is the page (its three views are listed
// under it while it is open), and "Migration" is the work group.
export const ASSESSMENT_STEPS: Step[] = [
  { items: [{ page: "overview", label: "Overview", icon: "overview" }] },
  { n: 1, label: "Bring in", items: [{ page: "inventory/import", label: "Import", icon: "import" }] },
  {
    n: 2,
    label: "Observe",
    items: [
      { page: "observatory", label: "Observatory", icon: "map" },
      { page: "inventory/verify", label: "Verify", icon: "verify" },
    ],
  },
  {
    n: 3,
    label: "Test",
    items: [
      { page: "advisories", label: "Advisories", icon: "advisories" },
      { page: "checks", label: "Checks", icon: "tests" },
    ],
  },
  { n: 4, label: "Fix", items: [{ page: "fixes", label: "Fixes", icon: "fixes" }] },
  {
    n: 5,
    label: "Plan the move",
    items: [
      {
        page: "migration/systems",
        label: "Migration plan",
        icon: "migration",
        views: [
          { page: "migration/systems", label: "Systems", icon: "systems" },
          { page: "migration/roadmap", label: "Roadmap", icon: "roadmap" },
          { page: "migration/dependencies", label: "Dependencies", icon: "dependencies" },
        ],
      },
    ],
  },
  // Phase 6d: a developer's change in the connected demo repository, and the tests picked for it.
  { n: 6, label: "Keep watching", items: [{ page: "change-watch", label: "Change watch", icon: "watch" }] },
  {
    label: "Evidence",
    items: [
      { page: "evidence/timeline", label: "Timeline", icon: "clock" },
      { page: "evidence", label: "Results", icon: "evidence" },
      { page: "evidence/decisions", label: "Approvals and decisions", icon: "person" },
      { page: "evidence/files", label: "Evidence files", icon: "file" },
    ],
  },
];

/** Every page of an assessment as the sidebar lists it, in order (a page with views counts once, with its views). */
export const ASSESSMENT_ITEMS: Item[] = ASSESSMENT_STEPS.flatMap((step) => step.items);

function NavLink({
  href,
  label,
  icon,
  current,
  disabled,
  reason,
  collapsed,
  nested,
  onNavigate,
  ariaLabel,
  currentKind = "page",
  dense = false,
}: {
  href: string;
  label: string;
  icon: string;
  current: boolean;
  disabled?: boolean;
  reason?: string;
  collapsed: boolean;
  nested?: boolean;
  onNavigate?: () => void;
  /** The name a screen reader says, when the label alone would be said twice in the sidebar. */
  ariaLabel?: string;
  /** What `current` means: the page (the default), or the open tab of a page. */
  currentKind?: "page" | "true";
  dense?: boolean;
}) {
  // (`dense`: the assessment's pages, which are many: a row is a little lower, so the whole path and Evidence under it
  // fit a laptop screen without scrolling)
  const base = `flex items-center gap-2.5 rounded-md text-sm transition-colors ${collapsed ? (dense ? "justify-center p-1.5" : "justify-center p-2") : nested ? (dense ? "py-1 pl-9 pr-2" : "py-1.5 pl-9 pr-2") : dense ? "px-2.5 py-1" : "px-2.5 py-1.5"}`;
  if (disabled) {
    return (
      <a
        role="link"
        aria-disabled="true"
        title={reason ?? label}
        className={`${base} cursor-not-allowed text-slate-600`}
      >
        {nested && !collapsed ? null : <Icon name={icon} />}
        {collapsed ? <span className="sr-only">{label}</span> : <span className="truncate">{label}</span>}
      </a>
    );
  }
  return (
    <a
      href={href}
      onClick={onNavigate}
      aria-current={current ? currentKind : undefined}
      aria-label={ariaLabel}
      title={collapsed ? label : undefined}
      className={`${base} ${
        current
          ? "bg-slate-800/80 font-medium text-slate-50"
          : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-100"
      }`}
    >
      {nested && !collapsed ? null : <Icon name={icon} className={`h-4 w-4 ${current ? "text-sky-300" : ""}`} />}
      {collapsed ? <span className="sr-only">{label}</span> : <span className="truncate">{label}</span>}
    </a>
  );
}

/** Phase 5b: the open assessment's name with its Open or Closed chip. It lists the project's assessments (each opens)
 * and holds New assessment. */
function AssessmentPicker({
  assessment,
  assessments,
  onNewAssessment,
  onNavigate,
}: {
  assessment: AssessmentView;
  assessments: AssessmentBrief[];
  onNewAssessment: () => void;
  onNavigate?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(open, ref, () => setOpen(false));
  return (
    <div ref={ref} className="relative mb-2">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Assessment: ${assessment.title}, ${assessment.status.label}`}
        data-testid="assessment-picker"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-1.5 text-left text-sm text-slate-100 hover:border-slate-600"
      >
        <span className="truncate">{assessment.title}</span>
        <StatusChip
          label={assessment.status.label}
          tone={assessment.status.key === "open" ? "pass" : "neutral"}
          size="sm"
        />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Assessments"
          className="absolute left-0 right-0 top-10 z-30 rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-xl"
        >
          {assessments.map((a) => (
            <a
              key={a.id}
              role="menuitem"
              href={pageHref(a.id, "overview")}
              onClick={() => {
                setOpen(false);
                onNavigate?.();
              }}
              aria-current={a.id === assessment.id ? "true" : undefined}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              <span className="truncate">{a.title}</span>
              <span className="text-xs text-slate-500">{a.status.label}</span>
            </a>
          ))}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onNewAssessment();
            }}
            className="mt-1 block w-full rounded-md border-t border-slate-800 px-2 py-1.5 text-left text-sm font-medium text-sky-300 hover:bg-slate-800"
          >
            New assessment
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** The left sidebar: organization and project switcher on top, the project's overview and the assessment picker, the
 * open assessment's pages as six numbered steps and then Evidence, Projects and Settings at the bottom. Collapses to icons; on a narrow screen it is shown as a
 * menu by the top bar's Menu button. */
export function Sidebar({
  workspace,
  assessment,
  route,
  access,
  collapsed,
  onToggleCollapsed,
  onPickProject,
  onNavigate,
  projectId,
  assessments,
  onNewAssessment,
}: {
  workspace: Workspace | null;
  assessment: AssessmentView | null;
  route: Route;
  access: PageAccess;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onPickProject: (p: WorkspaceProject) => void;
  /** Phase 5b: the open project (an assessment's, or the Project overview's), its assessments, and New assessment. */
  projectId: number | null;
  assessments: AssessmentBrief[];
  onNewAssessment: () => void;
  /** Called after a link is followed (the narrow-screen menu closes itself). */
  onNavigate?: () => void;
}) {
  const page = route.kind === "assessment" ? route.page : null;
  const id = assessment?.id ?? null;
  return (
    <div
      data-testid="sidebar"
      data-collapsed={collapsed || undefined}
      className={`flex h-full flex-col gap-3 ${collapsed ? "w-16 px-2" : "w-64 px-3"} py-3.5`}
    >
      <div className={`flex items-center ${collapsed ? "justify-center" : "justify-between"} gap-2`}>
        {collapsed ? (
          <span
            aria-label="Isogeny Labs"
            className="grid h-7 w-7 place-items-center rounded-md bg-sky-500 text-xs font-bold text-slate-950"
          >
            IL
          </span>
        ) : (
          <Wordmark />
        )}
      </div>
      <div>
        {collapsed ? null : (
          <p data-testid="organization-name" className="mb-1.5 truncate px-1 text-xs font-medium text-slate-500">
            {workspace?.organization ?? ""}
          </p>
        )}
        <ProjectSwitcher
          workspace={workspace}
          currentProjectId={projectId}
          collapsed={collapsed}
          onPick={onPickProject}
        />
        {projectId !== null ? (
          <div className="mt-2">
            <NavLink
              href={`#/p/${projectId}`}
              label="Project overview"
              icon="projects"
              current={route.kind === "project"}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          </div>
        ) : null}
      </div>

      <nav aria-label="Assessment" className="quiet-scroll min-h-0 flex-1 overflow-y-auto">
        {assessment && id !== null ? (
          <>
            {collapsed ? null : (
              <AssessmentPicker
                assessment={assessment}
                assessments={assessments}
                onNewAssessment={onNewAssessment}
                onNavigate={onNavigate}
              />
            )}
            <ol data-testid="sidebar-steps" className="space-y-0.5">
              {ASSESSMENT_STEPS.map((step, at) => {
                const headingId = step.label ? `sidebar-step-${at}` : undefined;
                return (
                  <li key={step.label ?? "overview"} data-testid="sidebar-step" data-step={step.n ?? undefined}>
                    {step.label && !collapsed ? (
                      <p
                        data-testid="sidebar-step-name"
                        className="flex items-center gap-2 px-2.5 pb-0.5 pt-2 text-[10.5px] font-semibold uppercase tracking-wide text-slate-500"
                      >
                        {step.n ? (
                          <span
                            aria-hidden="true"
                            className="grid h-4 w-4 place-items-center rounded-full border border-slate-700 text-[10px] tabular-nums text-slate-400"
                          >
                            {step.n}
                          </span>
                        ) : (
                          <Icon name="evidence" className="h-3.5 w-3.5 text-slate-500" />
                        )}
                        {/* (read out as "Step 2: Observe"; the list under it takes this as its name) */}
                        <span id={headingId}>
                          {step.n ? <span className="sr-only">Step {step.n}: </span> : null}
                          {step.label}
                        </span>
                      </p>
                    ) : step.label && collapsed ? (
                      <div aria-hidden="true" className="mx-2 my-1.5 border-t border-slate-800" />
                    ) : null}
                    <ul aria-labelledby={collapsed ? undefined : headingId} className="space-y-0.5">
                      {step.items.map((item) => {
                        const inside = item.views?.some((v) => v.page === page) ?? false;
                        return (
                          <li key={item.label}>
                            <NavLink
                              href={pageHref(id, item.page)}
                              label={item.label}
                              icon={item.icon}
                              current={item.views ? inside && collapsed : page === item.page}
                              disabled={!access[item.page].open}
                              reason={access[item.page].reason}
                              collapsed={collapsed}
                              onNavigate={onNavigate}
                              dense
                            />
                            {/* A page's own views, while one of them is open: the page then has no second strip. */}
                            {item.views && inside && !collapsed && access[item.page].open ? (
                              <ul
                                data-testid="sidebar-views"
                                aria-label={`${item.label} views`}
                                className="mt-0.5 space-y-0.5"
                              >
                                {item.views.map((v) => (
                                  <li key={v.page}>
                                    <NavLink
                                      href={pageHref(id, v.page)}
                                      label={v.label}
                                      icon={v.icon}
                                      current={page === v.page}
                                      disabled={!access[v.page].open}
                                      reason={access[v.page].reason}
                                      collapsed={collapsed}
                                      nested
                                      onNavigate={onNavigate}
                                      dense
                                    />
                                  </li>
                                ))}
                              </ul>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                );
              })}
            </ol>
          </>
        ) : collapsed ? null : (
          <p className="px-2.5 text-xs leading-relaxed text-slate-500">
            {projectId !== null
              ? "Open an assessment to see its pages here."
              : "Open a project to see its assessment here."}
          </p>
        )}
      </nav>

      <nav aria-label="Workspace" className="space-y-0.5 border-t border-slate-800 pt-3">
        <NavLink
          href="#/projects"
          label="Projects"
          icon="projects"
          current={route.kind === "projects"}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <NavLink
          href="#/settings"
          label="Settings"
          icon="settings"
          current={route.kind === "settings"}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={collapsed}
          className={`hidden w-full items-center gap-2.5 rounded-md text-sm text-slate-500 hover:bg-slate-800/50 hover:text-slate-200 lg:flex ${
            collapsed ? "justify-center p-2" : "px-2.5 py-1.5"
          }`}
        >
          <Icon name={collapsed ? "expand" : "collapse"} />
          {collapsed ? null : <span>Collapse</span>}
        </button>
      </nav>
    </div>
  );
}
