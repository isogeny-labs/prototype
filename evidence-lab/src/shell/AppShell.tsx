import { useCallback, useEffect, useMemo } from "react";
import { Link, NavLink, Outlet, useLocation, useMatch, useNavigate } from "react-router-dom";
import { services } from "@/services";
import { useQuery } from "@/hooks/useQuery";
import { useAppStore, DEFAULT_USER_BY_PROJECT } from "@/store";
import { Logo } from "./Logo";
import { AssistantPanel } from "./AssistantPanel";
import { ProjectContext, type ProjectCtx } from "./ProjectContext";
import { PROJECT_NAV } from "./nav";
import { PackBadge, SampleBanner } from "@/components";

export function AppShell() {
  const match = useMatch("/p/:id/*");
  const projectId = match?.params.id ?? null;
  const navigate = useNavigate();
  const location = useLocation();
  const assistantOpen = useAppStore((s) => s.assistantOpen);
  const setAssistantOpen = useAppStore((s) => s.setAssistantOpen);
  const user = useAppStore((s) => s.user);
  const setUser = useAppStore((s) => s.setUser);

  const projectsQ = useQuery(() => services.evidenceLab.listProjects(), []);
  const projectQ = useQuery(async () => {
    if (!projectId) return null;
    const project = await services.evidenceLab.getProject(projectId);
    const template = await services.packs.getTemplate(project.templateId, project.templateVersion);
    return { project, template };
  }, [projectId]);

  const ctx: ProjectCtx = useMemo(() => ({
    projectId,
    project: projectQ.data?.project ?? null,
    template: projectQ.data?.template ?? null,
    status: projectId ? projectQ.status : "idle",
    error: projectQ.error,
    retry: projectQ.retry,
  }), [projectId, projectQ.data, projectQ.status, projectQ.error, projectQ.retry]);

  // Sample mode: when the acting user is not a member of the opened project, act as that project's default editor.
  const project = projectQ.data?.project;
  useEffect(() => {
    if (!project) return;
    if (project.permissions.members.some((m) => m.personId === user.id)) return;
    const next = DEFAULT_USER_BY_PROJECT[project.id];
    if (next) setUser(next);
  }, [project, user.id, setUser]);

  const switchProject = useCallback((nextId: string) => {
    if (!nextId) { navigate("/"); return; }
    const rest = match?.params["*"] ?? "";
    navigate(`/p/${nextId}${rest ? `/${rest.split("/")[0]}` : ""}`);
  }, [match, navigate]);

  const anySample = (projectsQ.data ?? []).some((p) => p.isSample) || ctx.project?.isSample;

  return (
    <ProjectContext.Provider value={ctx}>
      <div className="flex h-full min-h-screen flex-col">
        <header className="flex items-center gap-4 border-b border-line bg-header px-4 py-2">
          <Link to="/" className="flex items-center gap-2 no-underline" aria-label="Isogeny Labs Evidence Lab home"><Logo height={28} /></Link>
          <span className="hidden text-xs uppercase tracking-widest text-faint lg:inline">Evidence Lab</span>
          <div className="ml-4 flex items-center gap-2">
            <label htmlFor="project-switcher" className="text-xs text-muted">Project</label>
            <select id="project-switcher" data-testid="project-switcher" className="input w-auto max-w-xs" value={projectId ?? ""} onChange={(e) => switchProject(e.target.value)}>
              <option value="">— none (home) —</option>
              {(projectsQ.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}{p.isSample ? " (sample)" : ""}</option>)}
            </select>
            {ctx.project ? <PackBadge packId={ctx.project.packId} templateName={ctx.template ? `${ctx.template.name} v${ctx.template.version}` : undefined} /> : null}
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span data-testid="current-user" title={user.role}>Acting as <strong className="text-ink">{user.name}</strong></span>
            <button type="button" className="btn-ghost btn-sm" aria-pressed={assistantOpen} onClick={() => setAssistantOpen(!assistantOpen)} data-testid="assistant-toggle">Assistant</button>
          </div>
        </header>
        {anySample ? <SampleBanner projectName={ctx.project?.name} /> : null}
        <div className="flex min-h-0 flex-1">
          <nav aria-label="Primary" className="w-52 shrink-0 border-r border-line bg-panel px-2 py-3 text-sm">
            <NavLink to="/" end className={({ isActive }) => `block rounded px-2 py-1.5 no-underline ${isActive ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"}`}>Home</NavLink>
            {projectId ? (
              <>
                <div className="h3 mt-4 px-2">Project</div>
                {PROJECT_NAV.map((n) => (
                  <NavLink key={n.path} to={`/p/${projectId}${n.path ? `/${n.path}` : ""}`} end={n.end} className={({ isActive }) => `block rounded px-2 py-1.5 no-underline ${isActive ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"}`}>{n.label}</NavLink>
                ))}
              </>
            ) : <div className="mt-4 px-2 text-xs text-faint">Pick a project to see its workspace.</div>}
            <div className="h3 mt-4 px-2">Developer</div>
            <NavLink to="/settings/sample-data" className={({ isActive }) => `block rounded px-2 py-1.5 no-underline ${isActive ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"}`}>Sample data</NavLink>
          </nav>
          <main id="main" className="min-w-0 flex-1 overflow-y-auto px-6 py-5" key={location.pathname}>
            <Outlet />
          </main>
          {assistantOpen ? <AssistantPanel onClose={() => setAssistantOpen(false)} /> : null}
        </div>
      </div>
    </ProjectContext.Provider>
  );
}
