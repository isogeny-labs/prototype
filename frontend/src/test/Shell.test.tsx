import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { ItemLinkView } from "../components/related";
import { linkRoute, parseRoute, routeHref } from "../router";
import { lab, mockApi, notFound, session, text } from "./fixtures";
import { checksView } from "./checksFixtures";
import { advisoriesTwoPacks, ottoEmpty } from "./ottoFixtures";
import { ORG, acmeRoutes, closedAssessment, emptyAssessment, workspace } from "./shellFixtures";

function go(hash: string) {
  window.history.replaceState(null, "", hash);
}

beforeEach(() => {
  window.localStorage.clear();
  go("#/projects");
});

// Settings asks for Otto's sections when it opens (phase 5c).
const baseRoutes = { "GET /api/session": { body: session }, ...acmeRoutes, "GET /api/otto": { body: ottoEmpty } };

async function openAcme(page = "overview", extra: Record<string, never | object> = {}) {
  go(`#/a/101/${page}`);
  mockApi({ ...baseRoutes, ...extra } as Parameters<typeof mockApi>[0]);
  render(<App />);
  await screen.findByTestId("top-bar");
  await waitFor(() => expect(screen.getByRole("navigation", { name: "Assessment" }).querySelector("a")).not.toBeNull());
}

const assessmentNav = () => within(screen.getByRole("navigation", { name: "Assessment" }));
const workspaceNav = () => within(screen.getByRole("navigation", { name: "Workspace" }));
const labels = (nav: ReturnType<typeof within>) => nav.getAllByRole("link").map((a: HTMLElement) => text(a));

describe("sidebar", () => {
  it("lists the assessment's pages as a path of six numbered steps and then Evidence, each page once, with Projects and Settings at the bottom", async () => {
    await openAcme();
    // The design refactor (26 November 2026): the pages in the order the work goes. Observing (the map, the claims)
    // and testing are two steps; Evidence, the record kept all along, comes last with its four views.
    expect(labels(assessmentNav())).toEqual([
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
    // The steps, with their numbers (a step's name is a heading of the list under it, not a link).
    const steps = screen.getAllByTestId("sidebar-step");
    expect(
      steps.map((li) => [li.getAttribute("data-step"), text(within(li).queryByTestId("sidebar-step-name"))]),
    ).toEqual([
      [null, ""],
      ["1", "1Step 1: Bring in"],
      ["2", "2Step 2: Observe"],
      ["3", "3Step 3: Test"],
      ["4", "4Step 4: Fix"],
      ["5", "5Step 5: Plan the move"],
      ["6", "6Step 6: Keep watching"],
      [null, "Evidence"],
    ]);
    expect(
      steps.map((li) =>
        within(li)
          .getAllByRole("link")
          .map((a) => text(a)),
      ),
    ).toEqual([
      ["Overview"],
      ["Import"],
      ["Observatory", "Verify"],
      ["Advisories", "Checks"],
      ["Fixes"],
      ["Migration plan"],
      ["Change watch"],
      ["Timeline", "Results", "Approvals and decisions", "Evidence files"],
    ]);
    // Each step's pages are a list named by the step.
    expect(screen.getByRole("list", { name: /^Step 2:\s*Observe$/ })).not.toBeNull();
    expect(screen.getByRole("list", { name: /^Evidence$/ })).not.toBeNull();
    expect(labels(workspaceNav())).toEqual(["Projects", "Settings"]);
    expect(screen.getByTestId("organization-name").textContent).toBe(ORG);
    expect(screen.getAllByText("Isogeny Labs").length).toBeGreaterThan(0);
  });

  it("marks the page that is open as current and links every open page to its address", async () => {
    await openAcme("checks");
    expect(assessmentNav().getByRole("link", { name: "Checks" }).getAttribute("aria-current")).toBe("page");
    expect(
      assessmentNav()
        .getAllByRole("link")
        .filter((a) => a.getAttribute("aria-current") === "page"),
    ).toHaveLength(1);
    // Results keeps the address Evidence always had, so every link ever made to a result still opens it.
    expect(assessmentNav().getByRole("link", { name: "Results" }).getAttribute("href")).toBe("#/a/101/evidence");
    expect(
      ["Observatory", "Timeline", "Approvals and decisions", "Evidence files", "Migration plan"].map((name) =>
        assessmentNav().getByRole("link", { name }).getAttribute("href"),
      ),
    ).toEqual([
      "#/a/101/observatory",
      "#/a/101/evidence/timeline",
      "#/a/101/evidence/decisions",
      "#/a/101/evidence/files",
      "#/a/101/migration/systems",
    ]);
    expect(workspaceNav().getByRole("link", { name: "Settings" }).getAttribute("href")).toBe("#/settings");
  });

  it("turns off pages that cannot open yet, each with aria-disabled and a reason, and no address", async () => {
    go("#/a/111/overview");
    mockApi({
      ...baseRoutes,
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
    } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByRole("heading", { name: "Assessment 1" });
    const nav = assessmentNav();
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
    ]) {
      const link = nav.getByRole("link", { name });
      expect(link.getAttribute("aria-disabled"), name).toBe("true");
      expect(link.getAttribute("href"), name).toBeNull();
      expect((link.getAttribute("title") ?? "").length, name).toBeGreaterThan(10);
    }
    expect(nav.getByRole("link", { name: "Overview" }).getAttribute("aria-disabled")).toBeNull();
    expect(nav.getByRole("link", { name: "Import" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("shows the project and the organization, and a hint instead of pages when no assessment is open", async () => {
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(screen.queryByRole("navigation", { name: "Assessment" })?.querySelector("a")).toBeNull();
    expect(workspaceNav().getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe("page");
  });

  it("does not repeat the four work groups: they are the tabs of their page, and a page's own views are listed only while it is open", async () => {
    await openAcme("evidence", {
      "GET /api/plans/1/lab": { body: lab },
      "GET /api/plans/1/checks": { body: checksView },
    });
    await screen.findByRole("tab", { name: /^Crypto tests/ });
    // One way to move between groups, not two: no group is a link in the sidebar, so "Migration" and "Dependencies"
    // are never there twice.
    expect(screen.queryByTestId("sidebar-groups")).toBeNull();
    expect(
      assessmentNav().queryByRole("link", { name: /^Verification|^Crypto tests|^Migration$|^Dependencies$/ }),
    ).toBeNull();
    expect(assessmentNav().getByRole("link", { name: "Results" }).getAttribute("aria-current")).toBe("page");
    // Migration plan's three views are not listed while another page is open...
    expect(screen.queryByTestId("sidebar-views")).toBeNull();
  });

  it("lists Migration plan's three views under it while one of them is open, and marks the open one", async () => {
    await openAcme("migration/roadmap");
    const views = await screen.findByTestId("sidebar-views");
    expect(views.getAttribute("aria-label")).toBe("Migration plan views");
    expect(
      within(views)
        .getAllByRole("link")
        .map((a) => [text(a), a.getAttribute("href"), a.getAttribute("aria-current")]),
    ).toEqual([
      ["Systems", "#/a/101/migration/systems", null],
      ["Roadmap", "#/a/101/migration/roadmap", "page"],
      ["Dependencies", "#/a/101/migration/dependencies", null],
    ]);
    // Collapsed to icons the views go, and the page's own icon is the one marked.
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.queryByTestId("sidebar-views")).toBeNull();
    expect(assessmentNav().getByRole("link", { name: "Migration plan" }).getAttribute("aria-current")).toBe("page");
  });

  it("collapses to icons, keeps every accessible name, and remembers it for the next visit", async () => {
    await openAcme();
    const collapse = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(collapse.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(collapse);
    expect(screen.getByTestId("sidebar").getAttribute("data-collapsed")).toBe("true");
    expect(screen.getByRole("button", { name: "Expand sidebar" }).getAttribute("aria-pressed")).toBe("true");
    // Names stay available to screen readers; the long organization line is gone.
    for (const name of [
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
    ]) {
      expect(assessmentNav().getByRole("link", { name }), name).not.toBeNull();
    }
    expect(workspaceNav().getByRole("link", { name: "Projects" })).not.toBeNull();
    expect(workspaceNav().getByRole("link", { name: "Settings" })).not.toBeNull();
    expect(screen.queryByTestId("organization-name")).toBeNull();
    expect(screen.getByRole("button", { name: /^Switch project/ })).not.toBeNull();
  });

  it("starts collapsed when it was left collapsed, and expands again", async () => {
    window.localStorage.setItem("evidence-lab-sidebar", "collapsed");
    await openAcme();
    expect(screen.getByTestId("sidebar").getAttribute("data-collapsed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(screen.getByTestId("sidebar").getAttribute("data-collapsed")).toBeNull();
    expect(window.localStorage.getItem("evidence-lab-sidebar")).toBe("open");
    expect(screen.getByTestId("organization-name")).not.toBeNull();
  });

  it("opens as a menu from the Open menu button on a narrow screen, and Escape closes it", async () => {
    await openAcme();
    expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const menu = screen.getByRole("dialog", { name: "Menu" });
    expect(within(menu).getByRole("link", { name: "Results" })).not.toBeNull();
    expect(within(menu).getByRole("link", { name: "Settings" })).not.toBeNull();
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull();
  });

  it("closes the menu when a link in it is followed", async () => {
    await openAcme();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Menu" })).getByRole("link", { name: "Settings" }));
    expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull();
    await waitFor(() => expect(window.location.hash).toBe("#/settings"));
  });
});

describe("top bar", () => {
  const crumbs = () => within(screen.getByRole("navigation", { name: "Breadcrumb" }));

  it("shows Folder / Project / Assessment / Page as breadcrumbs, folders nested", async () => {
    await openAcme();
    expect(
      crumbs()
        .getAllByRole("listitem")
        .map((li) => text(li).replace(/^\/\s*/, "")),
    ).toEqual(["Payments", "EU", "Acme Pay", "Assessment 2", "Overview"]);
    expect(crumbs().getByText("Overview").getAttribute("aria-current")).toBe("page");
    // The project's crumb opens its Project overview.
    expect(crumbs().getByRole("link", { name: "Acme Pay" }).getAttribute("href")).toBe("#/p/10");
  });

  it("adds the section for a view of Migration plan or of Evidence, and none for a page that stands alone", async () => {
    const last = (n: number) =>
      crumbs()
        .getAllByRole("listitem")
        .map((li) => text(li).replace(/^\/\s*/, ""))
        .slice(-n);
    await openAcme("inventory/verify");
    expect(last(2)).toEqual(["Assessment 2", "Verify"]);
    cleanup();
    await openAcme("migration/roadmap");
    expect(last(3)).toEqual(["Assessment 2", "Migration plan", "Roadmap"]);
    cleanup();
    await openAcme("evidence", { "GET /api/plans/1/lab": { body: lab } });
    expect(last(3)).toEqual(["Assessment 2", "Evidence", "Results"]);
  });

  it("names Advisories as a page of its own, with no section before it (phase 5c)", async () => {
    await openAcme("advisories", { "GET /api/plans/1/advisories": { body: advisoriesTwoPacks } });
    expect(
      crumbs()
        .getAllByRole("listitem")
        .map((li) => text(li).replace(/^\/\s*/, ""))
        .slice(-2),
    ).toEqual(["Assessment 2", "Advisories"]);
    expect(assessmentNav().getByRole("link", { name: "Advisories" }).getAttribute("aria-current")).toBe("page");
    expect(
      assessmentNav()
        .getAllByRole("link")
        .filter((a) => a.getAttribute("aria-current") === "page"),
    ).toHaveLength(1);
    expect(assessmentNav().getByRole("link", { name: "Advisories" }).getAttribute("href")).toBe("#/a/101/advisories");
  });

  it("names the screen on Projects and Settings", async () => {
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(
      crumbs()
        .getAllByRole("listitem")
        .map((li) => text(li)),
    ).toEqual(["Projects"]);
  });

  it("shows Open for an open assessment", async () => {
    await openAcme();
    expect(text(screen.getByTestId("assessment-status"))).toContain("Open");
    expect(text(screen.getByTestId("assessment-status"))).not.toContain("Closed");
  });

  it("shows Closed for a closed assessment", async () => {
    go("#/a/100/overview");
    mockApi({
      ...baseRoutes,
      "GET /api/assessments/100": { body: closedAssessment },
      "GET /api/projects/10": {
        body: { id: 10, name: "Acme Pay", folder_id: 2, archived: false, is_demo: true, path: [], assessments: [] },
      },
    } as Parameters<typeof mockApi>[0]);
    render(<App />);
    const chip = await screen.findByTestId("assessment-status");
    expect(text(chip)).toContain("Closed");
    expect(chip.getAttribute("title")).toContain("closed");
  });

  it("has no assessment status on the Projects page", async () => {
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(screen.queryByTestId("assessment-status")).toBeNull();
  });

  it("shows the mode badge with the backend's sentence as its reason", async () => {
    const line = "Isolated mode: our demo software runs in a locked-down container with no network.";
    go("#/projects");
    mockApi({
      ...baseRoutes,
      "GET /api/session": { body: { ...session, mode: "isolated", mode_line: line } },
    } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(text(screen.getByTestId("mode-badge"))).toBe("Isolated mode");
    expect(screen.getByTestId("mode-line").textContent).toBe(line);
    expect(screen.getByTestId("mode-badge").getAttribute("aria-describedby")).toBe(screen.getByTestId("mode-line").id);
  });

  it("says Demo mode in demo mode", async () => {
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(text(screen.getByTestId("mode-badge"))).toBe("Demo mode");
    expect(screen.getByTestId("mode-line").textContent).toBe(session.mode_line);
  });

  it("shows and hides the Otto panel from the top bar's toggle, and remembers the choice", async () => {
    // Phase 5a: the panel sits beside the pages of an assessment, not beside Projects or Settings.
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(screen.queryByTestId("otto-panel")).toBeNull();
    window.history.replaceState(null, "", "#/a/101/overview");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await screen.findByTestId("overview-page");
    expect(screen.getByTestId("otto-panel")).not.toBeNull();
    const toggle = screen.getByRole("button", { name: "Hide the assistant" });
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(toggle);
    expect(screen.queryByTestId("otto-panel")).toBeNull();
    expect(screen.getByRole("button", { name: "Show the assistant" }).getAttribute("aria-pressed")).toBe("false");
    expect(window.localStorage.getItem("evidence-lab-copilot")).toBe("hidden");
    fireEvent.click(screen.getByRole("button", { name: "Show the assistant" }));
    expect(screen.getByTestId("otto-panel")).not.toBeNull();
  });

  it("starts with the panel hidden when it was left hidden", async () => {
    window.localStorage.setItem("evidence-lab-copilot", "hidden");
    window.history.replaceState(null, "", "#/a/101/overview");
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("overview-page");
    expect(screen.queryByTestId("otto-panel")).toBeNull();
  });
});

describe("project switcher", () => {
  const open = async () => {
    mockApi({ ...baseRoutes } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.click(screen.getByRole("button", { name: /^Switch project/ }));
    return screen.getByTestId("project-switcher");
  };
  const options = () =>
    within(screen.getByRole("listbox", { name: "Projects" }))
      .queryAllByRole("option")
      .map((o) => text(o));

  it("shows the folder tree with nested folders, and hides archived projects and folders", async () => {
    const box = await open();
    expect(options()).toEqual(["Acme Pay", "Ledger"]);
    const tree = within(box).getByRole("listbox");
    const payments = within(tree).getByText("Payments").closest("li")!;
    const eu = within(tree).getByText("EU").closest("li")!;
    expect(parseInt(eu.style.paddingLeft)).toBeGreaterThan(parseInt(payments.style.paddingLeft));
    expect(within(tree).queryByText("Old stuff")).toBeNull();
    expect(within(tree).queryByText("Legacy")).toBeNull();
    expect(within(tree).queryByText("Retired")).toBeNull();
  });

  it("filters with the search box by project name or folder name", async () => {
    await open();
    const search = within(screen.getByTestId("project-switcher")).getByRole("searchbox", { name: "Search projects" });
    fireEvent.change(search, { target: { value: "ledg" } });
    expect(options()).toEqual(["Ledger"]);
    fireEvent.change(search, { target: { value: "eu" } });
    expect(options()).toEqual(["Acme Pay"]);
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(options()).toEqual([]);
    expect(screen.getByText("No project matches.")).not.toBeNull();
  });

  it("opens the project's overview by changing the address", async () => {
    await open();
    fireEvent.click(screen.getByRole("option", { name: "Acme Pay" }));
    await waitFor(() => expect(window.location.hash).toBe("#/p/10"));
    expect(screen.queryByTestId("project-switcher")).toBeNull();
  });

  it("opens the overview of a project that has no file yet", async () => {
    await open();
    fireEvent.click(screen.getByRole("option", { name: "Ledger" }));
    await waitFor(() => expect(window.location.hash).toBe("#/p/11"));
  });

  it("closes on Escape", async () => {
    await open();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("project-switcher")).toBeNull();
  });

  it("names the current project on its button", async () => {
    await openAcme();
    expect(screen.getByRole("button", { name: "Switch project: Acme Pay" })).not.toBeNull();
  });
});

describe("shell routes", () => {
  it("shows a loading note, not a crash, when the assessment is not found", async () => {
    go("#/a/999/overview");
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/workspace": { body: workspace },
      "GET /api/assessments/999": notFound,
    });
    render(<App />);
    expect(text(await screen.findByRole("alert"))).toContain("Not found");
  });
});

describe("addresses, phase 5c", () => {
  it("reads and writes the Advisories page of an assessment, with the advisory to open", () => {
    expect(parseRoute("#/a/101/advisories")).toMatchObject({
      kind: "assessment",
      id: 101,
      page: "advisories",
      item: null,
    });
    expect(parseRoute("#/a/101/advisories?item=CVE-2022-21449")).toMatchObject({
      kind: "assessment",
      id: 101,
      page: "advisories",
      item: "CVE-2022-21449",
    });
    // A link the backend sends to an advisory opens it in the open assessment.
    expect(routeHref(linkRoute({ page: "advisories", item: "CVE-2022-21449" }, 101))).toBe(
      "#/a/101/advisories?item=CVE-2022-21449",
    );
  });

  it("reads and writes Settings with and without a section, and sends a backend link to Settings there", () => {
    expect(parseRoute("#/settings")).toEqual({ kind: "settings" });
    expect(parseRoute("#/settings?section=test-packs")).toEqual({ kind: "settings", section: "test-packs" });
    expect(routeHref({ kind: "settings" })).toBe("#/settings");
    expect(routeHref({ kind: "settings", section: "test-packs" })).toBe("#/settings?section=test-packs");
    expect(linkRoute({ page: "settings", item: null, section: "test-packs" }, 101)).toEqual({
      kind: "settings",
      section: "test-packs",
    });
    expect(linkRoute({ page: "settings", item: null }, 101)).toEqual({ kind: "settings" });
  });

  it("a link to Settings works where no assessment is open; any other link needs one", () => {
    render(
      <>
        <ItemLinkView link={{ page: "settings", item: null, section: "test-packs" }}>Test packs</ItemLinkView>
        <ItemLinkView link={{ page: "checks", item: "test-6" }}>A check</ItemLinkView>
      </>,
    );
    expect(screen.getByRole("link", { name: "Test packs" }).getAttribute("href")).toBe("#/settings?section=test-packs");
    expect(screen.getByRole("link", { name: "A check" }).getAttribute("href")).toBe("#");
  });
});

describe("sidebar, phase 5b", () => {
  it("links the open project's overview, and its assessment picker lists the project's assessments and New assessment", async () => {
    await openAcme();
    // In the sidebar (the Overview page has its own link too).
    expect(
      within(screen.getByTestId("sidebar")).getByRole("link", { name: "Project overview" }).getAttribute("href"),
    ).toBe("#/p/10");
    const picker = screen.getByTestId("assessment-picker");
    expect(picker.getAttribute("aria-label")).toBe("Assessment: Assessment 2, Open");
    fireEvent.click(picker);
    // The project's assessments come in a request of their own, after the assessment's. The open menu fills in when
    // they arrive, so the list is waited for (read at once, it can hold only New assessment on a slow computer).
    const menu = () => within(screen.getByRole("menu", { name: "Assessments" }));
    await waitFor(() =>
      expect(
        menu()
          .getAllByRole("menuitem")
          .map((m) => text(m)),
      ).toEqual(["Assessment 2Open", "Assessment 1Closed", "New assessment"]),
    );
    expect(menu().getAllByRole("menuitem")[1]!.getAttribute("href")).toBe("#/a/100/overview");
    expect(menu().getAllByRole("menuitem")[0]!.getAttribute("aria-current")).toBe("true");
    fireEvent.click(menu().getByRole("menuitem", { name: "New assessment" }));
    expect(await screen.findByTestId("new-assessment-box")).not.toBeNull();
    expect(screen.queryByRole("menu", { name: "Assessments" })).toBeNull();
  });
});

describe("sidebar on the Project overview (phase 5b)", () => {
  it("says to open an assessment, not a project, when a project is open", async () => {
    go("#/p/10");
    mockApi({
      ...baseRoutes,
      "GET /api/projects/10/overview": { body: { id: 10, rows: [], compare: null, shared: [], choices: [] } },
    } as Parameters<typeof mockApi>[0]);
    render(<App />);
    await screen.findByTestId("project-overview");
    expect(within(screen.getByTestId("sidebar")).getByText("Open an assessment to see its pages here.")).not.toBeNull();
  });
});
