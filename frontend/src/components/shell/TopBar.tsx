import type { AssessmentView, Session } from "../../api";
import { PAGE_NAMES, type Route } from "../../router";
import { StatusChip } from "../ui";
import { Icon } from "./icons";

/** What each page is called (one list, in router.ts: the breadcrumb and "← Back to Checks" use the same names). */
export const PAGE_TITLES: Record<string, string> = PAGE_NAMES;

/** Folder / Project / Assessment / Page. Only the project and the assessment are links. */
function Breadcrumbs({
  route,
  assessment,
  projectName,
}: {
  route: Route;
  assessment: AssessmentView | null;
  projectName?: string | null;
}) {
  const crumbs: { label: string; href?: string }[] = [];
  if (route.kind === "projects") crumbs.push({ label: "Projects" });
  else if (route.kind === "settings") crumbs.push({ label: "Settings" });
  else if (route.kind === "project") crumbs.push({ label: projectName ?? "Project" }, { label: "Project overview" });
  else if (assessment) {
    for (const f of assessment.path) crumbs.push({ label: f.name });
    crumbs.push({ label: assessment.project.name, href: `#/p/${assessment.project.id}` });
    crumbs.push({ label: assessment.title, href: `#/a/${assessment.id}/overview` });
    const section = route.page.startsWith("inventory/")
      ? "Inventory"
      : route.page.startsWith("migration/")
        ? "Migration"
        : null;
    if (section) crumbs.push({ label: section });
    crumbs.push({ label: PAGE_TITLES[route.page] ?? "" });
  }
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={i} className={`flex min-w-0 items-center gap-1.5 ${last ? "" : "hidden sm:flex"}`}>
              {i > 0 ? (
                <span aria-hidden="true" className="text-slate-600">
                  /
                </span>
              ) : null}
              {last ? (
                <span aria-current="page" className="truncate font-medium text-slate-100">
                  {c.label}
                </span>
              ) : c.href ? (
                <a href={c.href} className="truncate text-slate-400 hover:text-slate-100">
                  {c.label}
                </a>
              ) : (
                <span className="truncate text-slate-500">{c.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** "Demo mode" or "Isolated mode", with the backend's own sentence as the reason (on hover or focus, and for screen
 * readers always). */
function ModeBadge({ session }: { session: Session }) {
  const isolated = session.mode === "isolated";
  return (
    <span className="group relative">
      <button
        type="button"
        data-testid="mode-badge"
        aria-describedby="mode-line"
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
          isolated ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-slate-700 bg-slate-900 text-slate-300"
        }`}
      >
        <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${isolated ? "bg-sky-400" : "bg-slate-400"}`} />
        {isolated ? "Isolated mode" : "Demo mode"}
      </button>
      <span id="mode-line" data-testid="mode-line" className="sr-only">
        {session.mode_line}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-0 top-full z-50 mt-2 hidden w-80 rounded-lg border border-slate-700 bg-slate-950 p-3 text-xs leading-relaxed text-slate-300 shadow-xl group-focus-within:block group-hover:block"
      >
        {session.mode_line}
      </span>
    </span>
  );
}

export function TopBar({
  session,
  route,
  assessment,
  copilotShown,
  onToggleCopilot,
  onOpenMenu,
  projectName,
}: {
  session: Session;
  route: Route;
  assessment: AssessmentView | null;
  /** Phase 5b: the open project's name, for the Project overview's breadcrumbs. */
  projectName?: string | null;
  copilotShown: boolean;
  onToggleCopilot: () => void;
  onOpenMenu: () => void;
}) {
  return (
    <header
      data-testid="top-bar"
      className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-4 backdrop-blur sm:px-6"
    >
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open menu"
        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 lg:hidden"
      >
        <Icon name="menu" className="h-5 w-5" />
      </button>
      <div className="min-w-0 flex-1">
        <Breadcrumbs
          route={route}
          assessment={route.kind === "assessment" ? assessment : null}
          projectName={projectName}
        />
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {route.kind === "assessment" && assessment ? (
          <span data-testid="assessment-status" title={assessment.status.closed_line ?? undefined}>
            <StatusChip
              size="sm"
              label={assessment.status.label}
              tone={assessment.status.key === "open" ? "pass" : "neutral"}
            />
          </span>
        ) : null}
        <ModeBadge session={session} />
        <button
          type="button"
          onClick={onToggleCopilot}
          aria-pressed={copilotShown}
          aria-label={copilotShown ? "Hide the assistant" : "Show the assistant"}
          title="Assistant"
          className="rounded-md border border-slate-800 p-1.5 text-slate-400 hover:border-slate-600 hover:text-slate-100 aria-pressed:border-slate-600 aria-pressed:bg-slate-800 aria-pressed:text-slate-100"
        >
          <Icon name="assistant" className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
