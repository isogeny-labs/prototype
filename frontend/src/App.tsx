import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  errorMessage,
  setUnauthorizedHandler,
  type Address,
  type AssessmentView,
  type DemoProjectsLoaded,
  type Import,
  type PlanView,
  type ProjectView,
  type Session,
  type VerifyRun,
  type Workspace,
  type WorkspaceProject,
} from "./api";
import { AdvisoriesScreen } from "./components/AdvisoriesScreen";
import { ChecksScreen } from "./components/ChecksScreen";
import { CloseBox, NewAssessmentBox } from "./components/pages/AssessmentBoxes";
import { ProjectOverviewPage } from "./components/pages/ProjectOverviewPage";
import { ChangeWatchScreen } from "./components/ChangeWatchScreen";
import { LinkProvider } from "./components/related";
import { LoginScreen, SetupScreen } from "./components/AuthScreens";
import { OttoPanel } from "./components/assistant/OttoPanel";
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
import { ErrorBox, formatTime, SecondaryButton } from "./components/ui";
import { VerifyScreen } from "./components/VerifyScreen";
import { setAlgorithmNames } from "./plainNames";
import { applyTheme, prefs, type Theme } from "./prefs";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "./readOnly";
import { type GroupNav, HiddenPageNotesContext, ItemMissing, ItemPageContext, type ItemPage, OpenItemContext } from "./components/layout";
import { PAGE_NAMES, itemPageHref, pageHref, useRoute, type Page } from "./router";
import { usePanelStamp } from "./changes";

const ANOTHER_FILE =
  "This assessment already has a file. Bringing in another file starts a new assessment in this project; this one stays open, as it is.";

/** Phase 5b: which box is open (New assessment, Rerun as new assessment, Close assessment). */
type BoxState =
  | { kind: "new"; projectId: number; then: Page }
  | { kind: "rerun"; assessment: AssessmentView }
  | { kind: "close"; assessment: AssessmentView };

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
  // 20 November 2026: the tab Checks, Evidence or Fixes shows, and its groups, for the sidebar (the page says them).
  const [groupNav, setGroupNav] = useState<{ page: Page; nav: GroupNav } | null>(null);
  const [theme, setTheme] = useState<Theme>(prefs.theme);
  const [collapsed, setCollapsed] = useState(prefs.sidebarCollapsed);
  const [copilotShown, setCopilotShown] = useState(prefs.copilotShown);
  const [guided, setGuided] = useState(prefs.guidedDemo);
  const [menuOpen, setMenuOpen] = useState(false);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoResult, setDemoResult] = useState<DemoProjectsLoaded | null>(null);
  // Phase 5b: the open project's assessments (for the assessment picker and the boxes), and the box on screen.
  const [projectView, setProjectView] = useState<ProjectView | null>(null);
  const [box, setBox] = useState<BoxState | null>(null);
  const [boxBusy, setBoxBusy] = useState(false);
  const [boxError, setBoxError] = useState<string | null>(null);
  // The assessment a file upload started (so a failed upload still lands on it, empty, with its error).
  const pendingTarget = useRef<number | null>(null);

  useEffect(() => applyTheme(theme), [theme]);

  const loadWorkspace = useCallback(async () => {
    try {
      const next = await api.getWorkspace();
      setAlgorithmNames(next.algorithm_names ?? []);
      setWorkspace(next);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  /** Fetches one assessment and what its pages need (its import, latest Verify, plan summary). */
  const fetchAssessment = useCallback(async (id: number) => {
    const view = await api.getAssessment(id);
    const current = view.import ?? null;
    const latest = current ? await api.getLatestVerify(current.id) : null;
    let existingPlan = current ? await api.getPlan(current.id) : null;
    // Phase 5b: once a file is in, every page opens, so the plan is made at once (opening Tests always made it; it
    // decides nothing, and it is allowed in a closed assessment).
    if (current && !existingPlan) existingPlan = await api.ensurePlan(current.id);
    return { view, imp: current, run: latest, plan: existingPlan };
  }, []);

  /** Shows a fetched assessment. Called in the same moment as a route change, so the page never blanks in between. */
  // How many times a whole read of the assessment has been put on the screen. The Overview's own quiet re-read (below)
  // is used only if none was since it was asked: its answer can arrive after an action's fresh read (Close and sign
  // off pressed right after the page opened) and must not put the earlier state back.
  const appliedReads = useRef(0);
  const applyAssessment = useCallback((data: Awaited<ReturnType<typeof fetchAssessment>>) => {
    appliedReads.current += 1;
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
  // (the fix an address names stays open: a link to one fix, or its own page, opened in a new browser tab)
  const namedFix = route.kind === "assessment" && route.page === "fixes" && route.item ? route.item : null;
  useEffect(() => {
    if (!loggedIn || routeId === null) return;
    if (assessment?.id === routeId) return;
    setFixId(namedFix);
    void loadAssessment(routeId);
    // (only another assessment starts this; the fix the address names is read at that moment)
  }, [loggedIn, routeId, assessment?.id, loadAssessment]);

  const projectId = route.kind === "project" ? route.id : route.kind === "assessment" && assessment?.id === route.id ? assessment.project.id : null;
  const loadProject = useCallback(async (id: number) => {
    try {
      setProjectView(await api.getProject(id));
    } catch {
      setProjectView(null);
    }
  }, []);
  useEffect(() => {
    if (!loggedIn || projectId === null) return;
    void loadProject(projectId);
  }, [loggedIn, projectId, assessment?.status.key, assessment?.title, loadProject]);

  // Phase 5b: a link that names a fix opens it in Fixes.
  const routeItem = route.kind === "assessment" ? (route.item ?? null) : null;
  const routePage = route.kind === "assessment" ? route.page : null;
  // The 5c fixes: "Open in new tab" in a side panel opens that item on a page of its own (…&view=page).
  const asItemPage = route.kind === "assessment" && route.view === "page" && Boolean(route.item);
  const [itemRoot, setItemRoot] = useState<HTMLElement | null>(null);
  // (above the item: what the hidden list page has to say, such as the reason a click was refused)
  const [itemNotes, setItemNotes] = useState<HTMLElement | null>(null);
  const itemPageId = route.kind === "assessment" ? route.id : null;
  // (a page that never draws the item, because it has no list to look in, says so after a few seconds)
  const [itemLate, setItemLate] = useState(false);
  useEffect(() => {
    setItemLate(false);
    if (!asItemPage) return;
    const timer = setTimeout(() => setItemLate(true), 4000);
    return () => clearTimeout(timer);
  }, [asItemPage, itemPageId, routePage, routeItem]);
  const itemPage = useMemo<ItemPage | null>(
    () =>
      itemPageId !== null && routePage !== null
        ? {
            asPage: asItemPage,
            root: asItemPage ? itemRoot : null,
            standing: routePage !== "inventory/import",
            backHref: (item) => pageHref(itemPageId, routePage, item ?? routeItem),
            listHref: pageHref(itemPageId, routePage),
            backLabel: PAGE_NAMES[routePage],
            hrefFor: (item) => itemPageHref(itemPageId, routePage, item),
          }
        : null,
    [itemPageId, routePage, routeItem, asItemPage, itemRoot],
  );
  // The Overview repeats what every page says now (tests run, systems measured, a list added since it was loaded), so
  // it asks for the assessment again each time it opens. It only reads.
  const loadedId = assessment?.id ?? null;
  useEffect(() => {
    if (!loggedIn || routePage !== "overview" || routeId === null || loadedId !== routeId) return;
    let live = true;
    const asked = appliedReads.current;
    api
      .getAssessment(routeId)
      .then((next) => {
        // (dropped when a fresh read was shown meanwhile: this answer is then the older one)
        if (live && appliedReads.current === asked) setAssessment(next);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [loggedIn, routePage, routeId, loadedId]);
  // Phase 5c: Import's line about Otto counts the checks of the test packs installed now, and a pack can be installed
  // after the file came in. So that one line is asked for again each time Import opens. It only reads.
  useEffect(() => {
    if (!loggedIn || routePage !== "inventory/import" || routeId === null || loadedId !== routeId) return;
    let live = true;
    api
      .getAssessment(routeId)
      .then((next) => {
        const fresh = next.import ?? null;
        // (only that line, and only when it differs: nothing else on the page is replaced by this read)
        if (live && fresh)
          setImp((c) => (c && c.id === fresh.id && JSON.stringify(c.otto) !== JSON.stringify(fresh.otto) ? { ...c, otto: fresh.otto } : c));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [loggedIn, routePage, routeId, loadedId]);
  useEffect(() => {
    if (routePage === "fixes" && routeItem) setFixId(routeItem);
  }, [routePage, routeItem]);
  // Phase 6a: a decision or a start sent from the Otto panel changed the assessment: what the app itself keeps of it
  // (its summary, the latest Verify, the test plan) is read again, and so is the sidebar's list. Each page reads its
  // own view again by the same signal (src/changes.ts).
  // (the item open in the page's own side panel, as the panel itself reports it: by its address or by a click on a row)
  // Until a panel has reported on this page, the item the address names stands in (the page is still loading).
  // A report counts only for the visit it was made on (one arrival at a page of an assessment). So on the first
  // drawing of the next page the item that was open on the page before is already forgotten, and the Otto panel never
  // asks about a page with another page's item (it used to, and every change of page cost a second read). Coming
  // back to a page later is a new visit: what its panel reported last time (that it closed) does not hide the item
  // the address names now. A panel that stays open across a change of tab (a system, on Migration) reports again
  // under the new tab, because the function it reports with is a new one.
  const visit = useMemo(() => ({}), [routePage, routeId]);
  const [reported, setReported] = useState<{ visit: object; item: string | null } | null>(null);
  const setOpenItem = useCallback((item: string | null) => setReported({ visit, item }), [visit]);
  const openItem = reported && reported.visit === visit ? reported.item : routeItem;
  const panelStamp = usePanelStamp();
  useEffect(() => {
    if (panelStamp === 0 || !loggedIn || routeId === null) return;
    void loadAssessment(routeId);
    void loadWorkspace();
    // (only the panel's signal starts this read; the other values are the newest at that moment)
  }, [panelStamp]);

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
    if (assessment) await loadProject(assessment.project.id);
  }, [assessment, loadAssessment, loadWorkspace, loadProject]);

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
  if (!session.logged_in) return <LoginScreen onDone={() => void refresh()} methods={session.login} />;

  const current = route.kind === "assessment" && assessment?.id === route.id ? assessment : null;
  const closed = current?.status.key === "closed";

  // Which pages of the assessment can open now, and why not. Phase 5b: before a file is in, only Overview and Import;
  // once a file is in, every page opens, and a page with nothing yet says what fills it. Phase 5c: Advisories opens by
  // the same rule as Checks.
  const noFile = "Bring in a scanner file first (Inventory, Import).";
  const withFile = { open: imp !== null, reason: noFile };
  const access: PageAccess = {
    overview: { open: true },
    "inventory/import": { open: true },
    "inventory/verify": withFile,
    advisories: withFile,
    checks: withFile,
    evidence: withFile,
    fixes: withFile,
    "change-watch": withFile,
    "migration/systems": withFile,
    "migration/roadmap": withFile,
    "migration/dependencies": withFile,
  };
  // A page whose data is not there (yet) falls back to Import, as the step bar did.
  const page: Page | null = current && route.kind === "assessment" ? (access[route.page].open ? route.page : "inventory/import") : null;

  function go(next: Page, item?: string | null, group?: string | null) {
    if (!current) return;
    navigate({ kind: "assessment", id: current.id, page: next, item: item ?? null, group: group ?? null });
  }

  // Phase 6b: the Result, Came from and Decision filters of a page's table are part of its address. A filter changed
  // on the page goes into the address (so Back returns to what was listed before); one named by the address, by a
  // link or by a command to Otto, is the one the page starts with.
  const filters = {
    result: route.kind === "assessment" ? (route.result ?? null) : null,
    from: route.kind === "assessment" ? (route.from ?? null) : null,
    decision: route.kind === "assessment" ? (route.decision ?? null) : null,
  };
  function setFilters(change: { result?: string | null; from?: string | null; decision?: string | null; group?: string | null }) {
    if (route.kind !== "assessment") return;
    navigate({ ...route, ...change });
  }
  // 20 November 2026: a tab chosen on Checks, Evidence or Fixes goes into the address, so Back returns to the tab before
  // and the sidebar's link names it. The item the address named belonged to the tab before, so it goes.
  function setGroup(group: string) {
    if (route.kind !== "assessment") return;
    navigate({ ...route, group, item: null, view: null });
  }
  const showGroups = (shownOn: Page) => (nav: GroupNav) => setGroupNav({ page: shownOn, nav });

  /** Where an answer of Otto's leads (phase 6b): a page, one item on it, and the filters of its table; or Settings. */
  function goTo(where: { page: string; item: string | null; group: string | null; result: string | null; came_from: string | null; decision: string | null }) {
    if (where.page === "settings") {
      navigate({ kind: "settings" });
      return;
    }
    if (!current) return;
    navigate({ kind: "assessment", id: current.id, page: where.page as Page, item: where.item, group: where.group, result: where.result,
               from: where.came_from, decision: where.decision });
  }

  function openAssessment(id: number, next: Page = "overview") {
    navigate({ kind: "assessment", id, page: next });
  }

  function pickProject(p: WorkspaceProject) {
    // Phase 5b: picking a project opens its Project overview (several assessments can be open).
    navigate({ kind: "project", id: p.id });
  }

  function viewFix(id: string) {
    setFixId(id);
    go("fixes", id);
  }

  /** `then`: the page the new assessment opens on (the closed banner's button opens it on Import, as in phase 5a). */
  function openNewBox(projectIdForBox: number, then: Page = "overview") {
    setBoxError(null);
    setBox({ kind: "new", projectId: projectIdForBox, then });
  }

  async function startFromBox(fields: { name: string; purpose: string; reference: string }) {
    if (!box) return;
    setBoxBusy(true);
    setBoxError(null);
    try {
      const made =
        box.kind === "rerun" ? await api.rerunAssessment(box.assessment.id, fields) : box.kind === "new" ? await api.newAssessment(box.projectId, fields) : null;
      setBox(null);
      await loadWorkspace();
      if (made) openAssessment(made.id, box.kind === "rerun" ? "inventory/import" : box.kind === "new" ? box.then : "overview");
    } catch (e) {
      setBoxError(errorMessage(e));
    } finally {
      setBoxBusy(false);
    }
  }

  async function closeFromBox(fields: { signed_off_by: string; note: string }) {
    if (!box || box.kind !== "close") return;
    setBoxBusy(true);
    setBoxError(null);
    try {
      const now = await api.changeAssessment(box.assessment.id, { close: true, signed_off_by: fields.signed_off_by, note: fields.note });
      setBox(null);
      // The answer is the assessment as it stands now: it is shown at once, so the page reads Closed without waiting
      // for everything else to be read again (on a large assessment that takes a few seconds more).
      appliedReads.current += 1;
      setAssessment(now);
      await reloadAssessment();
    } catch (e) {
      setBoxError(errorMessage(e));
    } finally {
      setBoxBusy(false);
    }
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
      groups={page !== null && groupNav?.page === page ? groupNav.nav : null}
      projectId={projectId}
      assessments={projectView?.id === projectId ? projectView.assessments : []}
      onNewAssessment={() => {
        setMenuOpen(false);
        if (projectId !== null) openNewBox(projectId);
      }}
    />
  );

  let content: React.ReactNode = null;
  if (route.kind === "projects") {
    content = workspace ? (
      <ProjectsPage
        workspace={workspace}
        onChanged={loadWorkspace}
        onOpenAssessment={(id, next) => openAssessment(id, next ?? "overview")}
        onOpenProject={(id) => navigate({ kind: "project", id })}
        onLoadDemo={() => void loadDemo()}
        loadingDemo={loadingDemo}
      />
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  } else if (route.kind === "project") {
    content = (
      <ProjectOverviewPage
        projectId={route.id}
        workspace={workspace}
        onNewAssessment={() => openNewBox(route.id)}
        onChanged={async () => {
          await loadWorkspace();
          await loadProject(route.id);
        }}
      />
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
        section={route.section ?? null}
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
        // (the next step that opens Checks is "Run the suggested tests": like Continue to checks, it opens Crypto tests,
        // where the test plan is)
        onGo={(next) => go(next, null, next === "checks" ? "encryption" : null)}
        onOpenAssessment={(id) => {
          void loadWorkspace();
          openAssessment(id);
        }}
        onChanged={reloadAssessment}
        onNewAssessment={() => openNewBox(current.project.id)}
        onRerun={() => {
          setBoxError(null);
          setBox({ kind: "rerun", assessment: current });
        }}
        onClose={() => {
          setBoxError(null);
          setBox({ kind: "close", assessment: current });
        }}
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
        openItem={routeItem}
        onVerified={(next) => {
          setRun(next);
          void loadWorkspace();
          void api.getAssessment(current.id).then(setAssessment).catch(() => undefined);
          go("inventory/verify");
        }}
      />
    );
  } else if (page === "inventory/verify" && imp) {
    // (Continue to checks opens Crypto tests, where the test plan and Run all are: Kevin's decision of 20 November 2026)
    content = <VerifyScreen imp={imp} run={run} onContinue={() => go("checks", null, "encryption")} openItem={routeItem} />;
  } else if (page === "advisories" && plan) {
    // Phase 5c: accepting one of Otto's proposed checks puts a test in the plan (and Undo takes it out), so the app's
    // copy of the plan is read again after every decision.
    content = (
      <AdvisoriesScreen planId={plan.id} openItem={routeItem} onPlanChanged={() => void reloadPlan()} decision={filters.decision} onFilters={setFilters} />
    );
  } else if (page === "checks" && imp) {
    content = (
      <ChecksScreen
        importId={imp.id}
        plan={plan}
        onPlan={setPlan}
        openItem={routeItem}
        group={route.kind === "assessment" ? (route.group ?? null) : null}
        result={filters.result}
        from={filters.from}
        onFilters={setFilters}
        onGroup={setGroup}
        onGroupShown={showGroups("checks")}
      />
    );
  } else if (page === "evidence" && plan) {
    content = (
      <EvidenceLabScreen
        planId={plan.id}
        onViewFix={viewFix}
        openItem={routeItem}
        group={route.kind === "assessment" ? (route.group ?? null) : null}
        result={filters.result}
        onFilters={setFilters}
        onGroup={setGroup}
        onGroupShown={showGroups("evidence")}
      />
    );
  } else if (page === "fixes" && plan) {
    content = (
      <FixesScreen
        planId={plan.id}
        selectedId={fixId}
        onSelect={setFixId}
        onRetestStarted={(item) => go("evidence", item ?? null)}
        onPlanChanged={() => void reloadPlan()}
        group={route.kind === "assessment" ? (route.group ?? null) : null}
        onGroup={setGroup}
        onGroupShown={showGroups("fixes")}
      />
    );
  } else if (page === "change-watch" && plan) {
    // Phase 6d: a developer's change in the connected demo repository; its picked tests run only on a click.
    content = <ChangeWatchScreen planId={plan.id} openItem={routeItem} />;
  } else if (migrationTab && imp) {
    content = (
      <MigrationScreen
        key={imp.id}
        importId={imp.id}
        tab={migrationTab}
        openItem={routeItem}
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
          projectName={projectView?.name ?? null}
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
                    <span className="text-slate-400">
                      {current.status.closed_line?.replace(CLOSED_SENTENCE, "").trim()}
                      {current.status.signoff ? ` ${formatTime(current.status.signoff.at)}.` : ""}
                      {current.status.signoff?.note ? ` Note: ${current.status.signoff.note}` : ""}
                    </span>
                  </span>
                  <SecondaryButton allowWhenClosed onClick={() => openNewBox(current.project.id, "inventory/import")}>
                    New assessment
                  </SecondaryButton>
                </div>
              ) : null}
              <ReadOnlyProvider readOnly={closed}>
                {current ? (
                  <LinkProvider assessmentId={current.id} planId={plan?.id ?? null}>
                    <ItemPageContext.Provider value={itemPage}>
                     <OpenItemContext.Provider value={setOpenItem}>
                      {/* The 5c fixes: an item on a page of its own ("Open in new tab"). The open panel draws itself in
                          this place, and the list it belongs to is kept, hidden, so every button works as in the panel. */}
                      {asItemPage ? (
                        <>
                          <div ref={setItemNotes} data-testid="item-page-notes" className="peer/notes" />
                          <div ref={setItemRoot} data-testid="item-page-root" className="peer/root" />
                          {/* Shown only while nothing is drawn above: the page is still loading, or (when it has no list
                              to look in, or stays empty) the address names nothing that is here. Not shown under a reason
                              the page gave, such as a page that could not be loaded. */}
                          <div className="hidden peer-empty/root:peer-empty/notes:block">
                            {itemPage && (content === null || itemLate) ? (
                              <ItemMissing page={itemPage} named={false} />
                            ) : (
                              <p role="status" className="text-sm text-slate-400">
                                Loading…
                              </p>
                            )}
                          </div>
                        </>
                      ) : null}
                      <div hidden={asItemPage || undefined} data-testid="page-content">
                        <HiddenPageNotesContext.Provider value={asItemPage ? itemNotes : undefined}>{content}</HiddenPageNotesContext.Provider>
                      </div>
                     </OpenItemContext.Provider>
                    </ItemPageContext.Provider>
                  </LinkProvider>
                ) : (
                  content
                )}
              </ReadOnlyProvider>
              {guided && current && page && page !== "overview" && !asItemPage ? <GuidedBar page={page} access={access} onGo={go} /> : null}
            </div>
          </main>
          {/* Phase 6a: the Otto assistant sits beside the pages of an assessment (it is about the page on screen), not
              beside Projects or Settings. The top bar's toggle hides and shows it. */}
          {copilotShown && current && page ? (
            <ReadOnlyProvider readOnly={closed}>
              <LinkProvider assessmentId={current.id} planId={plan?.id ?? null}>
                <OttoPanel assessmentId={current.id} page={page} item={openItem} onGo={(next, item) => go(next, item ?? null)} onGoTo={goTo} />
              </LinkProvider>
            </ReadOnlyProvider>
          ) : null}
        </div>
      </div>
      {box && box.kind !== "close" ? (
        <NewAssessmentBox
          title={box.kind === "rerun" ? "Rerun as new assessment" : "New assessment"}
          defaultName={
            box.kind === "rerun" ? `${box.assessment.title} (again)` : projectView?.id === box.projectId ? projectView.next_name : ""
          }
          defaultPurpose={box.kind === "rerun" ? (box.assessment.purpose?.key ?? "full_review") : "full_review"}
          defaultReference={box.kind === "rerun" ? (box.assessment.reference ?? "") : ""}
          purposes={workspace?.purposes ?? []}
          note={
            box.kind === "rerun"
              ? `Brings ${box.assessment.file?.filename ?? "the same file"} in again in a new assessment of this project: the file only, no results or choices. Each address must be confirmed again.`
              : "Starts a fresh, empty assessment in this project. Every other assessment stays as it is."
          }
          busy={boxBusy}
          error={boxError}
          onStart={(fields) => void startFromBox(fields)}
          onCancel={() => setBox(null)}
        />
      ) : null}
      {box?.kind === "close" ? (
        <CloseBox
          oneLoginLine={workspace?.one_login_line ?? ""}
          busy={boxBusy}
          error={boxError}
          onClose={(fields) => void closeFromBox(fields)}
          onCancel={() => setBox(null)}
        />
      ) : null}
    </div>
  );
}
