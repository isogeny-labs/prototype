import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  errorMessage,
  setUnauthorizedHandler,
  type Address,
  type AssessmentView,
  type DemoProjectsLoaded,
  type Import,
  type PlanView,
  type Session,
  type VerifyRun,
  type Workspace,
  type WorkspaceProject,
} from "./api";
import { LoginScreen, SetupScreen } from "./components/AuthScreens";
import { CopilotPanel } from "./components/CopilotPanel";
import { EvidenceLabScreen } from "./components/EvidenceLabScreen";
import { FixesScreen } from "./components/FixesScreen";
import { ImportScreen } from "./components/ImportScreen";
import { MigrationScreen, type MigrationTab } from "./components/MigrationScreen";
import { OverviewPage } from "./components/pages/OverviewPage";
import { ProjectsPage } from "./components/pages/ProjectsPage";
import { SettingsPage } from "./components/pages/SettingsPage";
import { GuidedBar } from "./components/shell/GuidedBar";
import { Sidebar, type PageAccess } from "./components/shell/Sidebar";
import { TopBar } from "./components/shell/TopBar";
import { TestsScreen } from "./components/TestsScreen";
import { ErrorBox, SecondaryButton } from "./components/ui";
import { VerifyScreen } from "./components/VerifyScreen";
import { applyTheme, prefs, type Theme } from "./prefs";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "./readOnly";
import { useRoute, type Page } from "./router";

const ANOTHER_FILE =
  "This assessment already has a file. Bringing in another file starts a new assessment in this project; this one is then closed and kept, read-only.";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [route, navigate] = useRoute();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [assessment, setAssessment] = useState<AssessmentView | null>(null);
  const [imp, setImp] = useState<Import | null>(null);
  const [run, setRun] = useState<VerifyRun | null>(null);
  const [plan, setPlan] = useState<PlanView | null>(null);
  // The fix that is open in Fixes. "View in Fixes" in Evidence or Migration sets it.
  const [fixId, setFixId] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(prefs.theme);
  const [collapsed, setCollapsed] = useState(prefs.sidebarCollapsed);
  const [copilotShown, setCopilotShown] = useState(prefs.copilotShown);
  const [guided, setGuided] = useState(prefs.guidedDemo);
  const [menuOpen, setMenuOpen] = useState(false);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoResult, setDemoResult] = useState<DemoProjectsLoaded | null>(null);
  // The assessment a file upload started (so a failed upload still lands on it, empty, with its error).
  const pendingTarget = useRef<number | null>(null);

  useEffect(() => applyTheme(theme), [theme]);

  const loadWorkspace = useCallback(async () => {
    try {
      setWorkspace(await api.getWorkspace());
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  /** Fetches one assessment and what its pages need (its import, latest Verify, plan summary). */
  const fetchAssessment = useCallback(async (id: number) => {
    const view = await api.getAssessment(id);
    const current = view.import ?? null;
    const latest = current ? await api.getLatestVerify(current.id) : null;
    const existingPlan = current ? await api.getPlan(current.id) : null;
    return { view, imp: current, run: latest, plan: existingPlan };
  }, []);

  /** Shows a fetched assessment. Called in the same moment as a route change, so the page never blanks in between. */
  const applyAssessment = useCallback((data: Awaited<ReturnType<typeof fetchAssessment>>) => {
    setAssessment(data.view);
    setImp(data.imp);
    setRun(data.run);
    setPlan(data.plan);
    setLoadError(null);
  }, []);

  const loadAssessment = useCallback(
    async (id: number) => {
      try {
        const data = await fetchAssessment(id);
        applyAssessment(data);
        return data.view;
      } catch (e) {
        setLoadError(errorMessage(e));
        return null;
      }
    },
    [fetchAssessment, applyAssessment],
  );

  const refresh = useCallback(async () => {
    try {
      const s = await api.getSession();
      setLoadError(null);
      setSession(s);
      if (s.logged_in) await loadWorkspace();
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, [loadWorkspace]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => setSession((s) => (s ? { ...s, logged_in: false } : s)));
    return () => setUnauthorizedHandler(null);
  }, []);

  // Opening an assessment (from the address bar, the switcher, the Projects table) loads it; each one is shown
  // exactly as it was left, because everything it holds is its own.
  const routeId = route.kind === "assessment" ? route.id : null;
  const loggedIn = session?.logged_in === true;
  useEffect(() => {
    if (!loggedIn || routeId === null) return;
    if (assessment?.id === routeId) return;
    setFixId(null);
    void loadAssessment(routeId);
  }, [loggedIn, routeId, assessment?.id, loadAssessment]);

  const importId = imp?.id ?? null;
  const reloadPlan = useCallback(async () => {
    if (importId === null) return null;
    try {
      const next = await api.getPlan(importId);
      setPlan(next);
      return next;
    } catch (e) {
      setLoadError(errorMessage(e));
      return null;
    }
  }, [importId]);

  /** After something changed the assessment (a file, a close, a rename): its view and the workspace again. */
  const reloadAssessment = useCallback(async () => {
    if (assessment) await loadAssessment(assessment.id);
    await loadWorkspace();
  }, [assessment, loadAssessment, loadWorkspace]);

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        {loadError ? (
          <div className="max-w-md">
            <ErrorBox title="The app couldn't start">{loadError}</ErrorBox>
          </div>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </main>
    );
  }
  if (session.setup_required) return <SetupScreen onDone={() => void refresh()} />;
  if (!session.logged_in) return <LoginScreen onDone={() => void refresh()} />;

  const current = route.kind === "assessment" && assessment?.id === route.id ? assessment : null;
  const closed = current?.status.key === "closed";

  // Which pages of the assessment can open now (today's rules), and why not.
  const hasResults = plan?.has_results === true;
  const fixesOpen = hasResults || plan?.has_migration === true;
  const noFile = "Bring in a scanner file first (Inventory, Import).";
  const access: PageAccess = {
    overview: { open: true },
    "inventory/import": { open: true },
    "inventory/verify": { open: run !== null, reason: "Verify the claims first (Inventory, Import)." },
    tests: { open: imp !== null, reason: noFile },
    evidence: { open: hasResults, reason: "Evidence opens once a test has a result." },
    fixes: { open: fixesOpen, reason: "Fixes opens once a test has a result or the migration plan has something for it." },
    "migration/systems": { open: imp !== null, reason: noFile },
    "migration/roadmap": { open: imp !== null, reason: noFile },
    "migration/dependencies": { open: imp !== null, reason: noFile },
  };
  // A page whose data is not there (yet) falls back to Import, as the step bar did.
  const page: Page | null = current && route.kind === "assessment" ? (access[route.page].open ? route.page : "inventory/import") : null;

  function go(next: Page) {
    if (!current) return;
    navigate({ kind: "assessment", id: current.id, page: next });
  }

  function openAssessment(id: number, next: Page = "overview") {
    navigate({ kind: "assessment", id, page: next });
  }

  function pickProject(p: WorkspaceProject) {
    if (p.latest) openAssessment(p.latest.id);
  }

  function viewFix(id: string) {
    setFixId(id);
    go("fixes");
  }

  async function loadDemo() {
    setLoadingDemo(true);
    try {
      const result = await api.loadDemoProjects();
      setDemoResult(result);
      await loadWorkspace();
    } catch (e) {
      setLoadError(errorMessage(e));
    } finally {
      setLoadingDemo(false);
    }
  }

  /** The assessment the next file goes into: this one if it has no file yet, else a new one in the same project. */
  async function importTarget(): Promise<number | undefined> {
    if (!current) return undefined;
    pendingTarget.current = null;
    if (!current.file && !closed) return current.id;
    const made = await api.newAssessment(current.project.id);
    pendingTarget.current = made.id;
    return made.id;
  }

  // The Import page stays on screen while the app moves to the assessment the file went into: the fetched assessment
  // and the new address are applied in the same moment, so the page keeps its own messages (an upload error).
  async function onImported(next: Import) {
    const target = next.assessment_id ?? current?.id ?? null;
    pendingTarget.current = null;
    setFixId(null);
    if (target !== null) {
      try {
        const data = await fetchAssessment(target);
        // Keep the upload reply's notices on screen (they come only with the upload).
        applyAssessment({ ...data, imp: data.imp ? { ...data.imp, notices: next.notices } : next });
        if (target !== current?.id) navigate({ kind: "assessment", id: target, page: "inventory/import" });
      } catch (e) {
        setLoadError(errorMessage(e));
      }
    } else {
      setImp(next);
    }
    void loadWorkspace();
  }

  function onImportFailed() {
    const target = pendingTarget.current;
    pendingTarget.current = null;
    setImp(null);
    setRun(null);
    setPlan(null);
    setFixId(null);
    if (target !== null) {
      void fetchAssessment(target)
        .then((data) => {
          applyAssessment(data);
          navigate({ kind: "assessment", id: target, page: "inventory/import" });
        })
        .catch((e: unknown) => setLoadError(errorMessage(e)));
      void loadWorkspace();
    }
  }

  function onAddressChanged(address: Address) {
    setImp((c) => (c ? { ...c, addresses: c.addresses.map((a) => (a.address === address.address ? address : a)) } : c));
  }

  const migrationTab: MigrationTab | undefined =
    page === "migration/roadmap" ? "roadmap" : page === "migration/dependencies" ? "dependencies" : page === "migration/systems" ? "systems" : undefined;

  const sidebar = (
    <Sidebar
      workspace={workspace}
      assessment={current}
      route={route}
      access={access}
      collapsed={collapsed && !menuOpen}
      onToggleCollapsed={() => {
        setCollapsed((v) => {
          prefs.setSidebarCollapsed(!v);
          return !v;
        });
      }}
      onPickProject={(p) => {
        setMenuOpen(false);
        pickProject(p);
      }}
      onNavigate={() => setMenuOpen(false)}
    />
  );

  let content: React.ReactNode = null;
  if (route.kind === "projects") {
    content = workspace ? (
      <ProjectsPage
        workspace={workspace}
        onChanged={loadWorkspace}
        onOpenAssessment={(id, next) => openAssessment(id, next ?? "overview")}
        onLoadDemo={() => void loadDemo()}
        loadingDemo={loadingDemo}
      />
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  } else if (route.kind === "settings") {
    content = (
      <SettingsPage
        session={session}
        workspace={workspace}
        theme={theme}
        onTheme={(t) => {
          prefs.setTheme(t);
          setTheme(t);
        }}
        onChanged={loadWorkspace}
        onLoadDemo={() => void loadDemo()}
        loadingDemo={loadingDemo}
        demoResult={demoResult}
      />
    );
  } else if (!current) {
    content = (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  } else if (page === "overview") {
    content = (
      <OverviewPage
        assessment={current}
        workspace={workspace}
        guided={guided}
        onGuided={(on) => {
          prefs.setGuidedDemo(on);
          setGuided(on);
        }}
        onGo={go}
        onOpenAssessment={(id) => {
          void loadWorkspace();
          openAssessment(id);
        }}
        onChanged={reloadAssessment}
      />
    );
  } else if (page === "inventory/import") {
    content = (
      <ImportScreen
        demoServer={session.demo_server}
        imp={imp}
        target={importTarget}
        targetNote={current.file && !closed ? ANOTHER_FILE : null}
        onImported={(next) => void onImported(next)}
        onImportFailed={onImportFailed}
        onAddressChanged={onAddressChanged}
        onVerified={(next) => {
          setRun(next);
          void loadWorkspace();
          void api.getAssessment(current.id).then(setAssessment).catch(() => undefined);
          go("inventory/verify");
        }}
      />
    );
  } else if (page === "inventory/verify" && imp && run) {
    content = <VerifyScreen imp={imp} run={run} onContinue={() => go("tests")} />;
  } else if (page === "tests" && imp) {
    content = <TestsScreen importId={imp.id} plan={plan} onPlan={setPlan} />;
  } else if (page === "evidence" && plan) {
    content = <EvidenceLabScreen planId={plan.id} onViewFix={viewFix} />;
  } else if (page === "fixes" && plan) {
    content = (
      <FixesScreen planId={plan.id} selectedId={fixId} onSelect={setFixId} onRetestStarted={() => go("evidence")} onPlanChanged={() => void reloadPlan()} />
    );
  } else if (migrationTab && imp) {
    content = (
      <MigrationScreen
        key={imp.id}
        importId={imp.id}
        tab={migrationTab}
        onTab={(t) => go(`migration/${t}` as Page)}
        onPlanChanged={() => void reloadPlan()}
        onViewFix={(id) => {
          // The plan summary may not know yet that the migration made fixes: load it first, then open Fixes.
          void reloadPlan().then(() => viewFix(id));
        }}
      />
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside aria-label="Sidebar" className="sticky top-0 hidden h-screen shrink-0 border-r border-slate-800 bg-slate-950 lg:block">
        {sidebar}
      </aside>
      {menuOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div aria-hidden="true" onClick={() => setMenuOpen(false)} className="absolute inset-0 bg-slate-950/70" />
          <div
            role="dialog"
            aria-label="Menu"
            className="absolute inset-y-0 left-0 border-r border-slate-800 bg-slate-950 shadow-2xl"
            onKeyDown={(e) => e.key === "Escape" && setMenuOpen(false)}
          >
            {sidebar}
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          session={session}
          route={route}
          assessment={current}
          copilotShown={copilotShown}
          onToggleCopilot={() => {
            setCopilotShown((v) => {
              prefs.setCopilotShown(!v);
              return !v;
            });
          }}
          onOpenMenu={() => setMenuOpen(true)}
        />
        <div className="flex flex-1 flex-col xl:flex-row">
          <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
            <div className="mx-auto max-w-6xl">
              {loadError ? (
                <div className="mb-4">
                  <ErrorBox>{loadError}</ErrorBox>
                </div>
              ) : null}
              {closed && current ? (
                <div
                  data-testid="closed-banner"
                  role="status"
                  className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-200"
                >
                  <span>
                    <strong className="font-semibold">{CLOSED_SENTENCE}</strong>{" "}
                    <span className="text-slate-400">{current.status.closed_line?.replace(CLOSED_SENTENCE, "").trim()}</span>
                  </span>
                  <SecondaryButton
                    allowWhenClosed
                    onClick={() =>
                      void api.newAssessment(current.project.id).then((made) => {
                        void loadWorkspace();
                        openAssessment(made.id, "inventory/import");
                      })
                    }
                  >
                    New assessment
                  </SecondaryButton>
                </div>
              ) : null}
              <ReadOnlyProvider readOnly={closed}>{content}</ReadOnlyProvider>
              {guided && current && page && page !== "overview" ? <GuidedBar page={page} access={access} onGo={go} /> : null}
            </div>
          </main>
          {/* The assistant sits beside the steps of an assessment (it is about the step on screen), not beside Projects or Settings. */}
          {copilotShown && current ? <CopilotPanel /> : null}
        </div>
      </div>
    </div>
  );
}
