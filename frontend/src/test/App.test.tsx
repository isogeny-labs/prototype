import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { checksView } from "./checksFixtures";
import { CODE_FIX, TLS_FIX, fixesViews, withCodeFix } from "./fixesFixtures";
import { address, beforeAfter, calls, demoImport, lab, mockApi, notFound, plan, run, session, text } from "./fixtures";
import { HYBRID_FIX, measuringView, migrationView } from "./migrationFixtures";
import { assessmentView, emptyAssessment, workspace } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/projects");
});

/** Where the app is opened (a refresh keeps the address, so this is also "come back after a refresh"). */
const at = (page: string, id = 101) => window.history.replaceState(null, "", `#/a/${id}/${page}`);
const withWorkspace = { "GET /api/workspace": { body: workspace } };

describe("first run and login", () => {
  it("shows the create-password screen the first time", async () => {
    mockApi({ "GET /api/session": { body: { ...session, setup_required: true, logged_in: false } } });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Create your password" })).not.toBeNull();
    expect(screen.getByText("Isogeny Labs")).not.toBeNull();
    expect(screen.getByLabelText("Password")).not.toBeNull();
    expect(screen.getByLabelText("Repeat password")).not.toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Create password"]);
  });

  it("gives friendly validation and does not call the server for a bad password", async () => {
    const fetchMock = mockApi({ "GET /api/session": { body: { ...session, setup_required: true, logged_in: false } } });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    expect(text(screen.getByRole("alert"))).toContain("at least 8 characters");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long-enough-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    expect(text(screen.getByRole("alert"))).toContain("don't match");
    expect(calls(fetchMock)).toEqual(["GET /api/session"]);
  });

  it("creates the password and opens the app", async () => {
    let created = false;
    const fetchMock = mockApi({
      "GET /api/session": () => ({ body: { ...session, setup_required: !created, logged_in: created } }),
      "POST /api/setup": () => {
        created = true;
        return { body: { ok: true } };
      },
      "GET /api/workspace": { body: workspace },
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "test-password-1" } });
    fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "test-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    // The app opens on the Projects page, which is home.
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).not.toBeNull();
    const setupCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/setup");
    expect(JSON.parse(String(setupCall?.[1]?.body))).toEqual({ password: "test-password-1" });
  });

  it("shows the normal login screen on later visits and reports a wrong password", async () => {
    mockApi({
      "GET /api/session": { body: { ...session, logged_in: false } },
      "POST /api/login": { status: 401, body: { error: { message: "Wrong password", line: null, field: null } } },
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Log in" })).not.toBeNull();
    expect(screen.queryByText("Create your password")).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Log in"]);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "not-the-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(text(await screen.findByRole("alert"))).toContain("That password isn't right");
  });

  it("offers Log in with GitHub beside the password when the GitHub App is set up", async () => {
    const fetchMock = mockApi({
      "GET /api/session": {
        body: { ...session, logged_in: false, login: { password: true, github: true, github_install_url: null } },
      },
    });
    render(<App />);
    const link = await screen.findByRole("link", { name: "Log in with GitHub" });
    // A plain link to the server, which sends the browser on to GitHub: nothing is sent before the click.
    expect(link.getAttribute("href")).toBe("/api/auth/github/start");
    expect(screen.getByLabelText("Password")).not.toBeNull();
    expect(calls(fetchMock)).toEqual(["GET /api/session"]);
  });

  it("shows only Log in with GitHub when the password login is off", async () => {
    mockApi({
      "GET /api/session": {
        body: { ...session, logged_in: false, login: { password: false, github: true, github_install_url: null } },
      },
    });
    render(<App />);
    expect(await screen.findByRole("link", { name: "Log in with GitHub" })).not.toBeNull();
    expect(screen.queryByLabelText("Password")).toBeNull();
    expect(screen.queryAllByRole("button")).toEqual([]);
  });
});

// ---- helpers for the screens inside an assessment ----
const nav = () => within(screen.getByRole("navigation", { name: "Assessment" }));
const sideLink = (name: string) => nav().getByRole("link", { name });
const isOff = (name: string) => sideLink(name).getAttribute("aria-disabled") === "true";
const currentPages = () =>
  nav()
    .getAllByRole("link")
    .filter((a) => a.getAttribute("aria-current") === "page")
    .map((a) => text(a));
const goTo = (name: string) => fireEvent.click(sideLink(name));
/** The four work groups are the tabs of their page (Checks, Results or Fixes). Since the design refactor (26 November
 * 2026) the sidebar does not repeat them: a group is opened by its tab. */
const goToGroup = async (group: string, page?: string) => {
  // (first the page itself, so that the tab clicked is this page's and not the one that was open a moment ago)
  if (page) await waitFor(() => expect(currentPages()).toEqual([page === "Evidence" ? "Results" : page]));
  fireEvent.click(await screen.findByRole("tab", { name: new RegExp(`^${group}`) }));
};

/** What an assessment (101, Acme Pay) with a file, a Verify run and a plan with results asks the server for. */
const withResults = (extra: Record<string, unknown> = {}): Routes =>
  ({
    "GET /api/session": { body: session },
    ...withWorkspace,
    "GET /api/assessments/101": { body: assessmentView() },
    "GET /api/import/7/verify": { body: run },
    "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
    "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    "GET /api/plans/1/lab": { body: lab },
    "GET /api/plans/1/checks": { body: checksView },
    ...extra,
  }) as Routes;

describe("app shell", () => {
  const emptyRoutes = (extra: Record<string, unknown> = {}): Routes =>
    ({
      "GET /api/session": { body: session },
      ...withWorkspace,
      "GET /api/assessments/111": { body: emptyAssessment },
      "GET /api/projects/11": {
        body: { id: 11, name: "Ledger", folder_id: null, archived: false, is_demo: false, path: [], assessments: [] },
      },
      ...extra,
    }) as Routes;

  it("shows the wordmark, the sidebar with its pages, the demo-mode line and the Otto panel", async () => {
    at("inventory/import", 111);
    mockApi(emptyRoutes());
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    expect(screen.getAllByText("Isogeny Labs").length).toBeGreaterThan(0);
    expect(screen.getByTestId("mode-line").textContent).toBe("Demo mode: running our own demo software, not isolated.");

    // The design refactor (26 November 2026): the pages as six steps in the order the work goes, then Evidence.
    expect(
      nav()
        .getAllByRole("link")
        .map((a) => text(a)),
    ).toEqual([
      "Overview",
      "Import",
      "Observatory",
      "Verify",
      "Advisories",
      "Checks",
      "Fixes",
      "Migration plan",
      "Change watch",
      "Timeline",
      "Results",
      "Approvals and decisions",
      "Evidence files",
    ]);
    expect(currentPages()).toEqual(["Import"]);
    // With no file yet, only Overview and Import open; the rest say why not.
    for (const name of [
      "Observatory",
      "Verify",
      "Advisories",
      "Checks",
      "Fixes",
      "Migration plan",
      "Change watch",
      "Timeline",
      "Results",
      "Approvals and decisions",
      "Evidence files",
    ])
      expect(isOff(name), name).toBe(true);
    expect(isOff("Overview")).toBe(false);
    expect(isOff("Import")).toBe(false);
    expect(screen.getByTestId("otto-panel")).not.toBeNull();
    expect(document.body.textContent).not.toMatch(/Coming in phase 2/);
  });

  it("opens on the Projects page when no assessment is named in the address", async () => {
    mockApi({ "GET /api/session": { body: session }, ...withWorkspace });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).not.toBeNull();
    expect(screen.getByTestId("mode-line")).not.toBeNull();
  });

  it("takes the mode line from the backend", async () => {
    const line = "Isolated mode: our demo software runs in a locked-down container with no network.";
    at("inventory/import", 111);
    mockApi(emptyRoutes({ "GET /api/session": { body: { ...session, mode: "isolated", mode_line: line } } }));
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    expect(screen.getByTestId("mode-line").textContent).toBe(line);
    expect(screen.queryByText(/Demo mode/)).toBeNull();
  });

  it("has the Otto panel beside the pages of an assessment: its title, the status line, and one way to hide it", async () => {
    // Phase 6a: the panel is the Otto assistant. The old label and the panel's own Hide button are gone; the top bar's
    // toggle hides and shows it (src/test/Shell.test.tsx).
    at("inventory/verify");
    mockApi(withResults());
    render(<App />);
    const panel = await screen.findByTestId("otto-panel");
    expect(within(panel).getByRole("heading", { level: 2, name: "Otto" })).not.toBeNull();
    expect(text(await within(panel).findByTestId("otto-status"))).toBe("Live Otto is off. Settings");
    expect(within(panel).getByTestId("otto-status-link").getAttribute("href")).toBe("#/settings?section=live-otto");
    expect(text(within(panel).getByTestId("otto-empty"))).toBe("Nothing is suggested on this page.");
    expect(document.body.textContent).not.toMatch(
      /Prototype assistant|no AI model connected|The assistant isn't built yet/,
    );
    expect(within(panel).queryByRole("button", { name: /Hide/ })).toBeNull();
    // Phase 6b: the text box is at the foot of the panel, under its own label, with the page's example chips
    expect(within(panel).getByRole("textbox", { name: "Ask Otto, or tell it what to do" })).not.toBeNull();
    expect(within(panel).getAllByTestId("otto-chip").length).toBeGreaterThan(0);
  });

  it("never uses the word 'secure' as a verdict or shows a score", async () => {
    at("inventory/verify");
    mockApi(withResults());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    const body = document.body.textContent ?? "";
    const withoutDisclaimer = body.replace("Passing these tests doesn't prove a system secure.", "");
    expect(withoutDisclaimer).not.toMatch(/secure|score|safe/i);
  });
});

describe("full flow", () => {
  it("imports the demo file, ticks the address, verifies and continues to the five suggested tests", async () => {
    let imported = false;
    const importedView = assessmentView({
      id: 111,
      number: 1,
      title: "Assessment 1",
      project: { id: 11, name: "Ledger", is_demo: false, archived: false },
      path: [],
      import: { ...demoImport, assessment_id: 111 },
    });
    at("inventory/import", 111);
    const fetchMock = mockApi({
      "GET /api/session": { body: session },
      ...withWorkspace,
      "GET /api/assessments/111": () => ({ body: imported ? importedView : emptyAssessment }),
      "POST /api/import/demo?assessment_id=111": () => {
        imported = true;
        return { body: { ...demoImport, assessment_id: 111 } };
      },
      "GET /api/import/7/verify": notFound,
      "GET /api/import/7/plan": notFound,
      "POST /api/import/7/confirm-address": { body: { ...address, confirmed: true } },
      "POST /api/import/7/verify": { body: run },
      "POST /api/import/7/plan": { body: plan },
      "GET /api/plans/1/checks": { body: checksView },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    expect(await screen.findAllByTestId("claim-row")).toHaveLength(3);

    // Phase 5b: once a file is in, every page opens (a page with nothing yet says what fills it).
    await waitFor(() => expect(isOff("Checks")).toBe(false));
    for (const name of ["Observatory", "Verify", "Results", "Fixes", "Migration plan", "Timeline"])
      expect(isOff(name), name).toBe(false);

    const verify = screen.getByRole("button", { name: "Verify claims" });
    expect((verify as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I own this system or am allowed to test it/));
    await waitFor(() => expect((verify as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(verify);

    expect(await screen.findByRole("heading", { name: "Verify" })).not.toBeNull();
    expect(screen.getAllByTestId("result-row")).toHaveLength(3);
    // The test plan is made as soon as the file is in (it proposes and locks tests; it decides nothing).
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([
      "POST /api/import/demo?assessment_id=111",
      "POST /api/import/7/plan",
      "POST /api/import/7/confirm-address",
      "POST /api/import/7/verify",
    ]);
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/confirm-address"));
    expect(JSON.parse(String(confirmCall?.[1]?.body))).toEqual({ address: "localhost:8443", confirmed: true });

    fireEvent.click(screen.getByRole("button", { name: "Continue to checks" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Checks" })).not.toBeNull();
    // Continue to checks opens Crypto tests, where the test plan and Run all are (20 November 2026).
    expect(await screen.findAllByTestId("test-card")).toHaveLength(5);
    expect(window.location.hash).toBe("#/a/111/checks?group=encryption");
    expect((await screen.findByRole("tab", { name: "Crypto tests" })).getAttribute("aria-selected")).toBe("true");
    expect(calls(fetchMock).filter((c) => c === "POST /api/import/7/plan")).toHaveLength(1);

    expect(currentPages()).toEqual(["Checks"]);
    expect(sideLink("Results").getAttribute("aria-current")).toBeNull();
    // No "continue" button on Checks: the sidebar is the way forward.
    expect(screen.queryByRole("button", { name: /continue/i })).toBeNull();
  });

  it("opens Evidence from the sidebar once the plan has results", async () => {
    at("inventory/verify");
    mockApi(withResults());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    expect(isOff("Results")).toBe(false);
    goTo("Results");
    // It opens on the first group with something in it (claims were verified). The four groups are the page's tabs,
    // with the open one marked; the sidebar does not repeat them.
    await screen.findAllByTestId("group-section");
    const tabs = () => screen.getAllByRole("tab");
    const tabNames = () => tabs().map((t) => t.getAttribute("data-group"));
    await waitFor(() => expect(tabNames()).toEqual(["verification", "encryption", "migration", "dependencies"]));
    expect(tabs().map((t) => t.getAttribute("aria-selected"))).toEqual(["true", "false", "false", "false"]);
    expect(screen.queryByTestId("sidebar-groups")).toBeNull();
    await goToGroup("Crypto tests", "Evidence");
    expect(await screen.findAllByTestId("evidence-row")).toHaveLength(5);
    // a tab chosen on the page goes into the address, so Back returns to the tab before
    expect(window.location.hash).toBe("#/a/101/evidence?group=encryption");
    expect(currentPages()).toEqual(["Results"]);
    await waitFor(() =>
      expect(tabs().map((t) => t.getAttribute("aria-selected"))).toEqual(["false", "true", "false", "false"]),
    );
    await goToGroup("Migration", "Evidence");
    expect(window.location.hash).toBe("#/a/101/evidence?group=migration");
    expect(screen.getByTestId("otto-panel")).not.toBeNull();

    goTo("Checks");
    await screen.findAllByTestId("group-section");
    await goToGroup("Crypto tests", "Checks");
    expect(await screen.findAllByTestId("test-card")).toHaveLength(5);
  });

  // Everything the Fixes tests below need: a plan with results, its Evidence and its fixes.
  const withFixes = (fixes = fixesViews.ready) => withResults({ "GET /api/plans/1/fixes": { body: fixes } });
  // Evidence is a table; a row opens its detail in the right-hand panel.
  const expandRow = (title: string) =>
    fireEvent.click(screen.getAllByTestId("evidence-row").find((r) => within(r).queryAllByText(title).length > 0)!);
  // Fixes is a table; with no fix asked for, it opens on the first fix, as before the panel.
  const openFirstFix = async () => screen.findByTestId("fix-summary");
  const viewInFixes = (title: string) => {
    const panel = screen.getByTestId("detail-panel");
    expect(within(panel).getByRole("heading", { level: 2, name: title })).not.toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "View in Fixes" }));
  };

  it("opens Fixes from the sidebar whenever Evidence can be opened", async () => {
    at("inventory/verify");
    const fetchMock = mockApi(withFixes());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    expect(isOff("Results")).toBe(false);
    expect(isOff("Fixes")).toBe(false);
    expect(calls(fetchMock)).not.toContain("GET /api/plans/1/fixes");

    goTo("Fixes");
    const summary = await openFirstFix();
    expect(screen.getByRole("heading", { level: 1, name: "Fixes" })).not.toBeNull();
    expect(currentPages()).toEqual(["Fixes"]);
    // With nothing asked for, the page opens on the first fix.
    expect(summary.getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(screen.getByTestId("otto-panel")).not.toBeNull();
    expect(screen.getByTestId("mode-line")).not.toBeNull();

    goTo("Results");
    await goToGroup("Crypto tests", "Evidence");
    expect(await screen.findAllByTestId("evidence-row")).toHaveLength(5);
    expect(currentPages()).toEqual(["Results"]);
  });

  it("View in Fixes on an Evidence line opens Fixes with that fix selected", async () => {
    at("evidence?group=encryption");
    mockApi(withFixes());
    render(<App />);
    await screen.findAllByTestId("evidence-row");

    // The server finding's line opens the second fix in the list, not the first.
    expandRow("Old TLS versions");
    viewInFixes("Old TLS versions");
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(currentPages()).toEqual(["Fixes"]);
    expect(screen.getByRole("heading", { level: 2, name: "Server accepts TLS 1.2" })).not.toBeNull();
    const selected = () =>
      within(screen.getByRole("navigation", { name: /^Open findings with a fix/ }))
        .getAllByTestId("fix-row")
        .map((row) => within(row).getAllByRole("button")[0]!.getAttribute("aria-current"));
    expect(selected()).toEqual([null, "true"]);

    // And the signing finding's line opens its own fix.
    goTo("Results");
    await goToGroup("Crypto tests", "Evidence");
    await screen.findAllByTestId("evidence-row");
    expandRow("Official test vectors");
    viewInFixes("Official test vectors");
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(selected()).toEqual(["true", null]);
  });

  it("keeps the fix that was picked in Fixes while the user looks at another page", async () => {
    at("fixes");
    mockApi(withFixes());
    render(<App />);
    await openFirstFix();
    fireEvent.click(screen.getByRole("button", { name: /^Server accepts TLS 1\.2/ }));
    expect(screen.getByTestId("fix-summary").getAttribute("data-fix-id")).toBe(TLS_FIX);

    goTo("Results");
    await screen.findAllByTestId("group-section");
    goTo("Fixes");
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(TLS_FIX);
  });

  it("starts a newly imported file from its first fix, not from the fix picked for the file before", async () => {
    // A second file goes into a new assessment of the same project. Its plan and fixes have the same ids as the first
    // file's in the demo, and the old assessment stays as it was.
    const second = assessmentView({
      id: 102,
      number: 3,
      title: "Assessment 3",
      import: { ...demoImport, id: 8, assessment_id: 102 },
      plan_id: null,
      has_results: false,
    });
    at("fixes");
    mockApi({
      ...withFixes(),
      "POST /api/projects/10/assessments": { body: { id: 102 } },
      "POST /api/import/demo?assessment_id=102": { body: { ...demoImport, id: 8, assessment_id: 102 } },
      "GET /api/assessments/102": { body: second },
      "GET /api/import/8/verify": notFound,
      "GET /api/import/8/plan": notFound,
      "POST /api/import/8/plan": { body: { ...plan, id: 2, import_id: 8, has_results: true } },
      "GET /api/plans/2/fixes": { body: { ...fixesViews.ready, plan_id: 2 } },
    } as Routes);
    render(<App />);
    await openFirstFix();
    fireEvent.click(screen.getByRole("button", { name: /^Server accepts TLS 1\.2/ }));
    expect(screen.getByTestId("fix-summary").getAttribute("data-fix-id")).toBe(TLS_FIX);

    goTo("Import");
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/inventory/import"));
    // The new file's plan is made as soon as it is in, so Fixes opens at once, on the new plan's first fix.
    await waitFor(() => expect(isOff("Fixes")).toBe(false));
    goTo("Fixes");
    expect((await openFirstFix()).getAttribute("data-fix-id")).toBe(CODE_FIX);
  });

  it("Retest now calls its route and then opens Evidence, where before and after show", async () => {
    const retest = `POST /api/plans/1/fixes/${CODE_FIX}/retest`;
    let retested = false;
    at("fixes");
    const fetchMock = mockApi(
      withResults({
        // The code fix came from the official vectors' result (Evidence row test-3).
        "GET /api/plans/1/fixes": {
          body: withCodeFix(fixesViews.merged, {
            came_from_links: [{ label: "Official test vectors", link: { page: "evidence", item: "test-3" } }],
          }),
        },
        "GET /api/plans/1/lab": () => ({ body: retested ? beforeAfter : lab }),
        [retest]: () => {
          retested = true;
          return { body: beforeAfter };
        },
      }),
    );
    render(<App />);
    await openFirstFix();

    fireEvent.click(screen.getByRole("button", { name: "Retest now" }));
    expect(await screen.findByTestId("lab-columns")).not.toBeNull();
    expect(currentPages()).toEqual(["Results"]);
    // It lands on the result it retests, its before and after, not only on the page.
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/evidence?item=test-3"));
    expect(screen.queryByTestId("fix-summary")).toBeNull();
    // (Evidence also asks for the checks once its own answer is in; that call is not part of the retest.)
    // (The Related block of the open fix, and Evidence's own list of checks, are asked for on their own; they are not
    // part of the retest.)
    const own = calls(fetchMock).filter((c) => /^(GET \/api\/plans\/1\/(fixes|lab)|POST )/.test(c));
    expect(own.slice(-3)).toEqual(["GET /api/plans/1/fixes", retest, "GET /api/plans/1/lab"]);
    expect(calls(fetchMock).filter((c) => c === retest)).toHaveLength(1);
  });

  it("stays on Fixes when Retest now is refused", async () => {
    at("fixes");
    mockApi(
      withResults({
        "GET /api/plans/1/fixes": { body: fixesViews.merged },
        [`POST /api/plans/1/fixes/${CODE_FIX}/retest`]: {
          status: 409,
          body: { error: { message: "A retest is running. Wait until it has finished.", line: null, field: null } },
        },
      }),
    );
    render(<App />);
    await openFirstFix();
    fireEvent.click(screen.getByRole("button", { name: "Retest now" }));
    expect(text(await screen.findByRole("alert"))).toBe("A retest is running. Wait until it has finished.");
    expect(currentPages()).toEqual(["Fixes"]);
  });

  it("comes back to Fixes after a refresh", async () => {
    at("evidence");
    mockApi(withFixes());
    const first = render(<App />);
    await screen.findAllByTestId("group-section");
    goTo("Fixes");
    await openFirstFix();
    first.unmount();

    render(<App />);
    expect(await openFirstFix()).not.toBeNull();
    expect(currentPages()).toEqual(["Fixes"]);
  });

  it("stays on Fixes after a refresh once a file is in, even when the plan has no results", async () => {
    at("fixes");
    mockApi({ ...withFixes(), "GET /api/import/7/plan": { body: plan } } as Routes);
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Fixes" })).not.toBeNull();
    expect(isOff("Fixes")).toBe(false);
    expect(currentPages()).toEqual(["Fixes"]);
  });

  it("falls back to Import after a refresh when the assessment has no file", async () => {
    at("fixes", 111);
    mockApi({
      "GET /api/session": { body: session },
      ...withWorkspace,
      "GET /api/assessments/111": { body: emptyAssessment },
      "GET /api/projects/11": {
        body: {
          id: 11,
          name: "Ledger",
          folder_id: null,
          archived: false,
          is_demo: false,
          path: [],
          assessments: [],
          next_name: "Assessment 2",
        },
      },
    } as Routes);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Import" })).not.toBeNull();
    expect(isOff("Fixes")).toBe(true);
    expect(screen.queryByTestId("fix-summary")).toBeNull();
  });

  it("comes back to the page that was open after a refresh", async () => {
    at("inventory/verify");
    mockApi(withResults());
    const first = render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    goTo("Results");
    await goToGroup("Crypto tests", "Evidence");
    await screen.findAllByTestId("evidence-row");
    first.unmount();

    // the tab is in the address, so the refresh comes back to it
    render(<App />);
    expect(await screen.findAllByTestId("evidence-row")).toHaveLength(5);
    expect(screen.getByRole("tab", { name: "Crypto tests" }).getAttribute("aria-selected")).toBe("true");
  });

  it("offers no upload of software on any page after Import", async () => {
    at("inventory/verify");
    mockApi(withFixes());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    for (const [name, testId] of [
      ["Checks", "test-card"],
      ["Results", "evidence-row"],
      ["Fixes", "fix-summary"],
    ] as const) {
      goTo(name);
      await screen.findAllByTestId("group-section");
      if (name !== "Fixes") await goToGroup("Crypto tests", name);
      await screen.findAllByTestId(testId);
      expect(document.querySelector('input[type="file"]')).toBeNull();
      expect(screen.getByRole("main").textContent).not.toMatch(/upload|drop a file|choose a file/i);
    }
  });

  it("clears the previous file's claims and results when an upload fails, leaving only the error", async () => {
    // A new file goes into a new assessment; if the file is refused, that new assessment is empty and shows the error.
    at("inventory/import");
    mockApi({
      ...withResults(),
      "GET /api/import/7/plan": notFound,
      "POST /api/projects/10/assessments": { body: { id: 102 } },
      "GET /api/assessments/102": {
        body: assessmentView({
          id: 102,
          number: 3,
          title: "Assessment 3",
          file: null,
          import: null,
          plan_id: null,
          has_verify: false,
          has_results: false,
        }),
      },
      "POST /api/import/file?filename=broken.csv&assessment_id=102": {
        status: 422,
        body: { error: { message: "The value column is empty.", line: 3, field: "value" } },
      },
    } as Routes);
    render(<App />);
    await screen.findAllByTestId("claim-row");

    fireEvent.change(screen.getByLabelText("Choose a file to import"), {
      target: { files: [new File(["x"], "broken.csv")] },
    });
    expect(text(await screen.findByRole("alert"))).toContain("The value column is empty.");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryAllByTestId("claim-row")).toHaveLength(0);
    expect(screen.queryByTestId("address-confirm")).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify claims" })).toBeNull();
    expect(isOff("Verify")).toBe(true);
  });

  it("keeps the import and the latest results after a refresh", async () => {
    at("inventory/import");
    const fetchMock = mockApi({
      ...withResults(),
      "GET /api/assessments/101": {
        body: assessmentView({
          import: { ...demoImport, addresses: [{ ...address, confirmed: true }], assessment_id: 101 },
        }),
      },
      "GET /api/import/7/plan": notFound,
    } as Routes);
    render(<App />);
    expect(await screen.findAllByTestId("claim-row")).toHaveLength(3);
    expect((screen.getByTestId("address-confirm") as HTMLInputElement).checked).toBe(true);
    // With no plan yet, the app makes it (it proposes and locks tests; it decides nothing).
    expect(calls(fetchMock).slice(0, 6)).toEqual([
      "GET /api/session",
      "GET /api/workspace",
      "GET /api/assessments/101",
      "GET /api/import/7/verify",
      "GET /api/import/7/plan",
      "POST /api/import/7/plan",
    ]);

    expect(isOff("Verify")).toBe(false);
    goTo("Verify");
    expect(await screen.findAllByTestId("result-row")).toHaveLength(3);
  });

  it("returns to the login screen if the session has ended", async () => {
    at("inventory/import", 111);
    mockApi({
      "GET /api/session": { body: session },
      ...withWorkspace,
      "GET /api/assessments/111": { body: emptyAssessment },
      "POST /api/import/demo?assessment_id=111": {
        status: 401,
        body: { error: { message: "Please log in", line: null, field: null } },
      },
    } as Routes);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    expect(await screen.findByRole("heading", { name: "Log in" })).not.toBeNull();
  });
});

describe("Migration pages", () => {
  const base = (extra: Record<string, unknown> = {}): Routes =>
    ({
      "GET /api/session": { body: session },
      ...withWorkspace,
      "GET /api/assessments/101": { body: assessmentView({ has_results: false }) },
      "GET /api/import/7/verify": notFound,
      "POST /api/import/7/plan": { body: plan },
      ...extra,
    }) as Routes;

  it("opens as soon as a file is imported, before any test has run", async () => {
    at("inventory/import");
    const fetchMock = mockApi(
      base({ "GET /api/import/7/plan": notFound, "GET /api/import/7/migration": { body: migrationView } }),
    );
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    for (const name of ["Migration plan", "Results", "Fixes"]) expect(isOff(name), name).toBe(false);
    goTo("Migration plan");
    expect(await screen.findByRole("heading", { level: 1, name: "Migration plan" })).not.toBeNull();
    expect(currentPages()).toEqual(["Systems"]);
    // The page tells the app the plan may have changed, so the app asks for the plan summary again.
    await waitFor(() => expect(calls(fetchMock).filter((c) => c === "GET /api/import/7/plan")).toHaveLength(2));
  });

  it("opens Fixes as soon as a file is in, even with no test results", async () => {
    at("inventory/import");
    mockApi(
      base({
        "GET /api/import/7/plan": { body: { ...plan, has_migration: true } },
        "GET /api/plans/1/fixes": { body: fixesViews.ready },
      }),
    );
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    await waitFor(() => expect(isOff("Fixes")).toBe(false));
    expect(isOff("Results")).toBe(false);
    goTo("Fixes");
    expect(await screen.findByTestId("fix-summary")).not.toBeNull();
  });

  it("asks for the plan summary again, without a page refresh, when a measurement finishes", async () => {
    let measured = false;
    let polls = 0;
    at("inventory/import");
    const fetchMock = mockApi(
      base({
        "GET /api/import/7/plan": () => ({ body: { ...plan, has_migration: measured } }),
        "GET /api/import/7/migration": () => {
          polls += 1;
          if (polls >= 2) measured = true;
          return { body: polls >= 2 ? migrationView : measuringView };
        },
      }),
    );
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    goTo("Migration plan");
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    expect(isOff("Fixes")).toBe(false);
    const asked = () => calls(fetchMock).filter((c) => c === "GET /api/import/7/plan").length;
    const before = asked();
    await waitFor(() => expect(measured).toBe(true), { timeout: 4000 });
    await waitFor(() => expect(asked()).toBeGreaterThan(before), { timeout: 4000 });
  });

  it("View in Fixes opens the Fixes page with that fix selected", async () => {
    at("migration/systems");
    mockApi(
      base({
        "GET /api/import/7/plan": { body: { ...plan, has_migration: true } },
        "GET /api/import/7/migration": { body: migrationView },
        "GET /api/plans/1/fixes": {
          body: {
            ...fixesViews.ready,
            fixes: [
              ...fixesViews.ready.fixes,
              { ...fixesViews.ready.fixes[1]!, id: HYBRID_FIX, title: "Turn on hybrid on localhost:8452" },
            ],
          },
        },
      }),
    );
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    goTo("Roadmap");
    const phase1 = (await screen.findAllByTestId("roadmap-band")).find(
      (b) => b.getAttribute("data-band") === "phase1",
    )!;
    fireEvent.click(within(phase1).getByRole("button", { name: "View in Fixes" }));
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(HYBRID_FIX);
    expect(currentPages()).toEqual(["Fixes"]);
  });

  it("comes back to Migration after a refresh", async () => {
    at("inventory/import");
    mockApi(base({ "GET /api/import/7/plan": { body: plan }, "GET /api/import/7/migration": { body: migrationView } }));
    const first = render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    goTo("Migration plan");
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    first.unmount();

    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Migration plan" })).not.toBeNull();
    expect(currentPages()).toEqual(["Systems"]);
  });

  it("comes back to Fixes after a refresh when only the migration plan opens it", async () => {
    at("fixes");
    mockApi(
      base({
        "GET /api/import/7/plan": { body: { ...plan, has_migration: true } },
        "GET /api/plans/1/fixes": { body: fixesViews.ready },
      }),
    );
    render(<App />);
    expect(await screen.findByTestId("fix-summary")).not.toBeNull();
    expect(currentPages()).toEqual(["Fixes"]);
  });

  it("shows the three Migration views as sub-items and moves between them", async () => {
    at("migration/systems");
    mockApi(base({ "GET /api/import/7/plan": { body: plan }, "GET /api/import/7/migration": { body: migrationView } }));
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    for (const name of ["Systems", "Roadmap", "Dependencies"]) expect(isOff(name), name).toBe(false);
    goTo("Roadmap");
    await waitFor(() => expect(currentPages()).toEqual(["Roadmap"]));
    expect(window.location.hash).toBe("#/a/101/migration/roadmap");
  });

  it("asks again for Import's line about Otto each time Import opens, so a pack installed since is counted", async () => {
    // Second review, 18 November 2026: after a new test pack the Advisories page listed three checks while Import
    // still said "Otto found 2 checks", because the line had been read once, when the assessment was opened.
    const found = (count: number) => ({
      count,
      label: "From Otto",
      text: `${count} checks may apply: ${count} published weaknesses with a test, for acme-sign 1.4.2.`,
      note: "Nothing runs on import. You accept or reject each proposed check on Advisories.",
      link: { page: "advisories", item: null },
      link_label: "Open Advisories",
    });
    let reads = 0;
    at("inventory/import");
    const fetchMock = mockApi(
      withResults({
        // the first two reads are from before the pack (opening the assessment, then opening Import); later ones after it
        "GET /api/assessments/101": () => {
          reads += 1;
          return {
            body: assessmentView({ import: { ...demoImport, assessment_id: 101, otto: found(reads <= 2 ? 2 : 3) } }),
          };
        },
      }),
    );
    render(<App />);
    expect(text(await screen.findByTestId("import-otto-text"))).toContain("2 checks may apply");
    await waitFor(() => expect(reads).toBe(2));
    // Leave Import and come back: the line is read again and now counts three. Only reads were made.
    window.location.hash = "#/a/101/checks";
    await waitFor(() => expect(screen.queryByTestId("import-otto")).toBeNull());
    window.location.hash = "#/a/101/inventory/import";
    await waitFor(() => expect(text(screen.getByTestId("import-otto-text"))).toContain("3 checks may apply"));
    expect(calls(fetchMock).filter((c) => !c.startsWith("GET"))).toEqual([]);
  });
});
