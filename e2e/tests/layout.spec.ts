// Phase 5b end to end: every page with a table, at 1440 pixels wide, with its side panel closed and open. On each:
// the page never scrolls sideways, no table scrolls sideways, and no name in a table is broken between letters (a name
// may break only at a space or a dot, dash or slash). It also takes the phase 5b screenshots of every changed page, dark
// and light, with and without the panel, into docs/screenshots/phase5b/.
// Since 20 November 2026 Checks, Evidence and Fixes show the four work groups as tabs, one group's table at a time: every
// tab of the three pages is measured the same way, its panel closed and open (where the tab has a row to open), and its
// pictures, dark and light, go to docs/screenshots/group-tabs/.
// The design refactor (26 November 2026): the page that was Evidence is the Results view of Evidence (its pictures keep
// their names, "evidence-..."), and a panel keeps its records behind one fold. A panel is measured as it opens, with
// the fold shut (that is the picture), and once more with the fold open, so the tables inside it are measured too.
// The three new pages that have a side panel are measured the same way: the Observatory (its Map and its List, each
// with a box's panel open), Evidence's Timeline (an entry's panel open) and Approvals and decisions (a row's panel
// open). Their pictures go to docs/screenshots/design-refactor/.
// It runs on a copy of the app of its own (own data folder and ports), so the main app is never touched.
// Main-screen buttons only.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {
  REPO,
  enterApp,
  layoutProblems,
  openFreshAssessment,
  openGroupTab,
  openMigrationView,
  screenshotFolder,
  startCopy,
  stepLink,
  stopCopy,
  type Copy,
} from "./shared";

const SHOTS = screenshotFolder("phase5b");
const TAB_SHOTS = screenshotFolder("group-tabs");
const NEW_PAGE_SHOTS = screenshotFolder("design-refactor");
const GROUPS = [
  { key: "verification", label: "Verification" },
  { key: "encryption", label: "Crypto tests" },
  { key: "migration", label: "Migration" },
  { key: "dependencies", label: "Dependencies" },
] as const;
const LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
let copy: Copy | null = null;
let page: Page;

async function shots(name: string, folder = SHOTS): Promise<void> {
  fs.mkdirSync(folder, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(folder, `${name}-${theme}.png`), fullPage: true, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** Measures the page with its panel closed, then opens a row's panel and measures again; takes both screenshots.
 * `compact`: beside its open panel a table shows its compact form, and that is waited for; a page that is no such
 * table (the Observatory's map and its List, the Timeline's list) is drawn as it is beside its panel.
 * `also`: one more measurement of the page's own, made in both states (the Observatory's map has one). */
async function measure(
  name: string,
  open?: () => Promise<void>,
  folder = SHOTS,
  how: { compact?: boolean; also?: (state: string) => Promise<void> } = {},
): Promise<void> {
  const compact = how.compact ?? true;
  const panel = page.getByTestId("detail-panel").or(page.getByTestId("claim-panel"));
  if ((await panel.count()) > 0) {
    // The panel can close by itself just now: a check belongs to its tab, so when another tab opens the page closes the
    // panel of the old tab's check (ChecksScreen). Click only while it is still there. A plain click raced with that
    // close once on GitHub (21 November 2026): the button was removed mid-click and the click waited for it until the
    // walk's 15 minutes ran out.
    const close = panel.first().getByRole("button", { name: "Close details" });
    await close.click({ timeout: 10_000 }).catch(async (error: unknown) => {
      if ((await panel.count()) > 0) throw error;
    });
    await expect(panel).toHaveCount(0);
  }
  expect(await layoutProblems(page), `${name}, panel closed`).toEqual([]);
  await how.also?.(`${name}, panel closed`);
  await shots(`${name}-panel-closed`, folder);
  if (!open) return;
  await open();
  await expect(panel.first()).toBeVisible();
  // The panel asks for its own part (a check's every run, the Related block): wait for it before measuring and the picture.
  await page.waitForLoadState("networkidle");
  const checkPanel = page.getByTestId("check-panel");
  if ((await checkPanel.count()) > 0) await expect(checkPanel.getByTestId("earlier-runs")).toBeVisible();
  // The table (or the Roadmap's plan) beside the panel is in its compact form.
  if (compact) await expect(page.locator('main [data-compact="true"]').first()).toBeVisible();
  expect(await layoutProblems(page), `${name}, panel open`).toEqual([]);
  await how.also?.(`${name}, panel open`);
  await shots(`${name}-panel-open`, folder);
  // The panel's records are behind one fold, shut until it is opened (a result's, a fix's): with it open the tables in
  // it (the cases, a proof's tests) are on screen, as they always were before the fold, and are measured as well. Only a
  // fold that can be seen is opened: one that sits inside another closed part of the panel (a run's record on Results,
  // a library's "Details and evidence") stays as the panel opens it.
  const shut = panel
    .first()
    .locator('[data-testid="proof-fold-toggle"][aria-expanded="false"]')
    .filter({ visible: true });
  let opened = 0;
  while (opened < 6 && (await shut.count()) > 0) {
    await shut.first().click();
    opened += 1;
  }
  if (opened > 0) expect(await layoutProblems(page), `${name}, panel open, its fold open`).toEqual([]);
}

/** What is wrong with the Observatory's map right now. The map lays itself out by its own width, which is small when
 * the Otto panel and a box's panel are both open: no box may stand past the map's frame, no two boxes over each other,
 * no result chip past its box, and no label of a line past the frame or over a service's name. Empty when all is well. */
async function mapProblems(): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const map = document.querySelector('[data-testid="observatory-map"]');
    if (!map) return ["the map is not drawn"];
    const place = (r: DOMRect) => ({
      left: Math.round(r.left),
      right: Math.round(r.right),
      top: Math.round(r.top),
      bottom: Math.round(r.bottom),
    });
    const at = (el: Element) => place(el.getBoundingClientRect());
    const all = (...ids: string[]) =>
      Array.from(map.querySelectorAll(ids.map((id) => `[data-testid="${id}"]`).join(", ")));
    const named = (el: Element) =>
      `${el.getAttribute("data-testid")} "${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40)}"`;
    const over = (a: ReturnType<typeof place>, b: ReturnType<typeof place>) => {
      const wide = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const high = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      return wide > 1 && high > 1 ? `${wide} x ${high} px` : null;
    };
    const frame = at(map);
    const past = (el: Element, inside: ReturnType<typeof place>, what: string) => {
      const b = at(el);
      if (b.right > inside.right + 1 || b.left < inside.left - 1)
        problems.push(
          `${named(el)} stands past ${what}: ${b.left} to ${b.right}, against ${inside.left} to ${inside.right}`,
        );
    };
    // no box past the map's frame
    for (const box of all(
      "map-outside",
      "map-service",
      "map-box",
      "map-algorithm",
      "map-libraries",
      "map-libraries-note",
    ))
      past(box, frame, "the map's frame");
    // no two boxes over each other
    const boxes = all("map-outside", "map-box", "map-algorithm", "map-libraries");
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const by = over(at(boxes[i]!), at(boxes[j]!));
        if (by) problems.push(`${named(boxes[i]!)} and ${named(boxes[j]!)} stand over each other by ${by}`);
      }
    }
    // no result chip past its box
    for (const chip of all("map-check-word")) {
      const box = chip.closest('[data-testid="map-box"]');
      if (box) past(chip, at(box), `its box ${named(box)}`);
    }
    // no label of a line past the map's frame, or over the words of a service's name
    const titles = Array.from(map.querySelectorAll('[data-testid="map-service"] h3')).flatMap((title) => {
      const words = document.createRange();
      words.selectNodeContents(title);
      return Array.from(words.getClientRects()).map((r) => ({ title, words: place(r) }));
    });
    for (const label of all("map-line-label")) {
      const b = at(label);
      if (b.right - b.left < 1 || b.bottom - b.top < 1) continue; // (a label that is not drawn)
      past(label, frame, "the map's frame");
      for (const { title, words } of titles) {
        const by = over(b, words);
        if (by) problems.push(`${named(label)} stands over the service's name "${title.textContent}" by ${by}`);
      }
    }
    return problems;
  });
}

/** The Observatory's map, measured once it has settled (its lines are drawn again after its width changes). */
async function expectMapFits(state: string): Promise<void> {
  await expect.poll(mapProblems, { message: `the Observatory's map, ${state}`, timeout: 10_000 }).toEqual([]);
}

/** The Observatory's List is a table: it must not scroll sideways. */
async function expectListFits(state: string): Promise<void> {
  const list = page.getByTestId("observatory-list");
  await expect(list).toBeVisible();
  const [inside, room] = await list.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(inside, `the Observatory's List, ${state}: it scrolls sideways (${inside} > ${room})`).toBeLessThanOrEqual(
    room! + 1,
  );
}

/** Every tab of Checks, Results or Fixes, one after another: the tab's own table, measured with its panel closed and,
 * where the tab lists a row, open on its first row. Returns how many rows each tab listed. */
async function measureTabs(prefix: string, rowIds: string[]): Promise<Record<string, number>> {
  const listed: Record<string, number> = {};
  for (const [i, g] of GROUPS.entries()) {
    await openGroupTab(page, g.label);
    const shown = page.getByRole("tabpanel", { name: g.label });
    await expect(shown).toHaveAttribute("data-group", g.key);
    // one group's table at a time
    await expect(page.getByTestId("group-section")).toHaveCount(1);
    await page.waitForLoadState("networkidle");
    const rows = shown.locator(rowIds.map((id) => `[data-testid="${id}"]`).join(", "));
    listed[g.key] = await rows.count();
    // (a row opens by a click on its name: a link inside the row, such as a fix's "Came from" link, opens its own page)
    await measure(
      `${prefix}-${i + 1}-${g.key}`,
      listed[g.key] > 0 ? () => rows.first().locator(":scope > *").first().click() : undefined,
      TAB_SHOTS,
    );
  }
  return listed;
}

test.describe.configure({ mode: "serial", timeout: 900_000 });

test.afterAll(async () => {
  await stopCopy(copy);
});

test("every table page at 1440 pixels wide, its panel closed and open: no sideways scrolling, no name broken between letters", async ({
  browser,
}) => {
  copy = await startCopy(browser, 6, "demo");
  page = copy.page;
  await page.setViewportSize({ width: 1440, height: 900 });
  await enterApp(page, { ottoPanel: true });
  await openFreshAssessment(page, "Layout walk");

  // Fill every page: the demo file, Verify, every test, Measure status, the demo dependency list.
  await page.getByRole("button", { name: "Use demo file" }).click();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await measure("04-import", () => page.getByTestId("claim-row").first().click());
  await page.getByTestId("claim-panel").getByRole("button", { name: "Close details" }).click();
  await page.getByTestId("address-confirm").click();
  await page.getByTestId("page-content").getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await measure("05-verify", () => page.getByTestId("result-row").first().getByTestId("verify-details-toggle").click());
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  await page.getByTestId("page-content").getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });
  // (Migration plan's three views are the sidebar's links under it, listed while one of them is open)
  await openMigrationView(page, "Systems");
  await page
    .getByTestId("page-content")
    .getByRole("button", { name: /^Measure status/ })
    .click();
  await expect(page.getByTestId("page-content").getByRole("button", { name: /^Measure again/ })).toBeEnabled({
    timeout: 120_000,
  });
  await openMigrationView(page, "Dependencies");
  await page.getByLabel("Choose a dependency list").setInputFiles(LIST);
  await expect(page.getByTestId("dependency-row").first()).toBeVisible({ timeout: 30_000 });

  // ---- Checks: each of its four tabs. It opens on the first group with something in it (claims were verified).
  await stepLink(page, "Checks").click();
  await expect(page.getByRole("tab", { name: "Verification", exact: true })).toHaveAttribute("aria-selected", "true");
  const checks = await measureTabs("checks", ["check-row"]);
  expect(checks.verification).toBe(3);
  // (Crypto tests: the test plan's cards; its first runs show there, and no retest has run yet)
  await openGroupTab(page, "Crypto tests");
  await expect(page.getByRole("tabpanel", { name: "Crypto tests" }).getByTestId("test-card")).toHaveCount(5);
  // A link to a test of the plan (Advisories' Open in Checks, a Related line, Otto's On Checks) opens its panel beside
  // the plan's cards: Crypto tests measured with its panel open too.
  const firstTest = await page.getByTestId("test-card").first().getAttribute("data-test");
  const assessmentId = /#\/a\/(\d+)\//.exec(new URL(page.url()).hash)![1];
  await page.goto(`/#/a/${assessmentId}/checks?item=test-${firstTest}`);
  await expect(page.getByRole("tab", { name: "Crypto tests", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("check-panel")).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("check-panel").getByTestId("earlier-runs")).toBeVisible();
  expect(await layoutProblems(page), "checks, Crypto tests, panel open").toEqual([]);
  await shots("checks-2-encryption-panel-open", TAB_SHOTS);
  expect(checks.migration).toBeGreaterThan(0);

  // ---- Results (the page that was Evidence): each tab (a claim's check, the results, a system's measurement, a library)
  await stepLink(page, "Results").click();
  await expect(page.getByRole("heading", { name: "Results", level: 1 })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Verification", exact: true })).toHaveAttribute("aria-selected", "true");
  const evidence = await measureTabs("evidence", ["check-row", "evidence-row", "library-row"]);
  expect(evidence).toMatchObject({ verification: 3, encryption: 5 });
  expect(evidence.dependencies).toBeGreaterThan(0);

  // ---- Fixes: each tab. It opens on the first group with a fix (Verification has none of its own).
  await stepLink(page, "Fixes").click();
  await expect(page.getByRole("tab", { name: "Crypto tests", exact: true })).toHaveAttribute("aria-selected", "true");
  const fixes = await measureTabs("fixes", ["fix-row", "fix-apart-row"]);
  expect(fixes.verification).toBe(0);
  expect(fixes.encryption).toBeGreaterThan(0);
  // A search says on each tab how many fixes match, and the tab strip still fits.
  await page.getByRole("searchbox", { name: "Search fixes" }).fill("TLS");
  await expect(page.getByTestId("group-tab-matches")).toHaveCount(4);
  expect(await layoutProblems(page), "fixes, a search on").toEqual([]);
  await page.getByRole("searchbox", { name: "Search fixes" }).fill("");

  // ---- Migration: Systems, Roadmap, Dependencies
  await openMigrationView(page, "Systems");
  await expect(page.getByTestId("system-card").first()).toBeVisible();
  await measure("09-migration-systems", () => page.getByTestId("system-card").first().click());
  await openMigrationView(page, "Roadmap");
  await expect(page.getByTestId("roadmap-row").first()).toBeVisible();
  await measure("10-migration-roadmap", () =>
    page.getByTestId("roadmap-row").first().getByRole("button").first().click(),
  );
  await openMigrationView(page, "Dependencies");
  await expect(page.getByTestId("dependency-row").first()).toBeVisible();
  await measure("11-migration-dependencies", () =>
    page.getByTestId("dependency-row").filter({ hasText: "openssl 3.0.22" }).first().locator("p.font-mono").click(),
  );

  // ---- The design refactor (26 November 2026): the three new pages that have a side panel
  // (each panel reads its own content after it opens, and beside the Otto panel that read waits its turn: the page is
  // measured once the panel shows it)
  const shows = async (panelContent: string) =>
    expect(page.getByTestId("detail-panel").getByTestId(panelContent)).toBeVisible({ timeout: 30_000 });
  const openABox = async () => {
    await page.getByTestId("map-box-open").first().click();
    await shows("box-panel");
  };
  // The Observatory, its map. The map lays itself out by its own width, so it is measured in four states: the Otto
  // panel hidden or shown, a box's panel closed or open. First with the Otto panel hidden (the top bar's toggle) ...
  await stepLink(page, "Observatory").click();
  await expect(page.getByTestId("observatory-map")).toBeVisible();
  await page.getByRole("button", { name: "Hide the assistant" }).click();
  await expect(page.getByTestId("otto-panel")).toHaveCount(0);
  expect(await layoutProblems(page), "the Observatory's map, the Otto panel hidden, no box open").toEqual([]);
  await expectMapFits("the Otto panel hidden, no box open");
  await openABox();
  expect(await layoutProblems(page), "the Observatory's map, the Otto panel hidden, a box open").toEqual([]);
  await expectMapFits("the Otto panel hidden, a box open");
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  await expect(page.getByTestId("detail-panel")).toHaveCount(0);
  // ... then beside the Otto panel, as every other page of this walk: with both panels open the map is at its narrowest
  await page.getByRole("button", { name: "Show the assistant" }).click();
  await expect(page.getByTestId("otto-panel")).toBeVisible();
  await measure("layout-observatory-map", openABox, NEW_PAGE_SHOTS, { compact: false, also: expectMapFits });
  // Its List (a table) shows the same thing, and does not scroll sideways, with a box's panel closed and open
  await page.getByRole("group", { name: "Observatory view" }).getByRole("button", { name: "List" }).click();
  await expect(page.getByTestId("observatory-list")).toBeVisible();
  await measure(
    "layout-observatory-list",
    async () => {
      await page.getByTestId("observatory-list").getByTestId("list-row").first().getByRole("button").first().click();
      await shows("box-panel");
    },
    NEW_PAGE_SHOTS,
    { compact: false, also: expectListFits },
  );
  // Evidence, the Timeline: an entry's panel (Run all, with the runs it started)
  await stepLink(page, "Timeline").click();
  const ranAll = page.getByTestId("timeline-entry").filter({ hasText: "Run all" }).first();
  await expect(ranAll).toBeVisible();
  await measure(
    "layout-timeline",
    async () => {
      await ranAll.getByRole("button").first().click();
      await shows("entry-panel");
    },
    NEW_PAGE_SHOTS,
    { compact: false },
  );
  // Evidence, Approvals and decisions: a table, compact beside the panel of one of its rows
  await stepLink(page, "Approvals and decisions").click();
  await expect(page.getByTestId("decision-row").first()).toBeVisible();
  await measure(
    "layout-decisions",
    async () => {
      await page.getByTestId("decision-row").first().locator(":scope > *").first().click();
      await shows("entry-panel");
    },
    NEW_PAGE_SHOTS,
  );

  // ---- The Overview, then a second pass of the same file (Rerun as new assessment), for the Project overview
  await stepLink(page, "Overview").click();
  await expect(page.getByTestId("overview-groups")).toBeVisible();
  // The Overview repeats what the pages say now: every test has run, the systems are measured, the list is in.
  const group = (name: string) =>
    page.getByTestId("overview-group").filter({ has: page.getByRole("heading", { name }) });
  await expect(group("Crypto tests")).toContainText("Checks: Open 0");
  await expect(group("Migration")).not.toContainText("Nothing measured yet.");
  await expect(group("Dependencies").getByTestId("overview-fact").first()).toContainText("Libraries");
  await expect(page.getByTestId("brought-in")).toContainText("3 claims, 1 server named");
  await expect(page.getByTestId("brought-in")).toContainText("Dependency list: added");
  await measure("03-overview");
  await page.getByRole("button", { name: "Rerun as new assessment" }).click();
  const box = page.getByTestId("new-assessment-box");
  await expect(box.getByLabel("Name")).toHaveValue("Assessment 1 (again)");
  await shots("12-rerun-box");
  await box.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await page.getByTestId("address-confirm").click();
  await page.getByTestId("page-content").getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();

  // ---- The Project overview: both assessments side by side, What changed between them, the shared systems
  await page.getByTestId("sidebar").first().getByRole("link", { name: "Project overview" }).click();
  await expect(page.getByTestId("assessment-row")).toHaveCount(2);
  await expect(page.getByTestId("what-changed")).toBeVisible();
  await expect(page.getByTestId("shared-systems")).toContainText(copy.server);
  await measure("02-project-overview");

  // ---- New assessment and Close assessment (a sign-off), then the closed assessment
  await page.getByTestId("project-overview").getByRole("button", { name: "New assessment" }).click();
  await expect(page.getByTestId("new-assessment-box").getByLabel("Name")).toHaveValue("Assessment 3");
  await shots("13-new-assessment-box");
  await page.getByTestId("new-assessment-box").getByRole("button", { name: "Cancel" }).click();
  await page.getByTestId("assessment-row").filter({ hasText: "Assessment 1 (again)" }).click();
  await page.getByRole("button", { name: "Close assessment" }).click();
  await page.getByTestId("close-box").getByLabel("Signed off by").fill("Demo reviewer");
  await shots("14-close-box");
  await page.getByTestId("close-box").getByRole("button", { name: "Close and sign off" }).click();
  await expect(page.getByTestId("closed-banner")).toBeVisible();
  await shots("15-closed-assessment");

  // ---- Projects (one row per project, with its open and closed counts)
  await page.goto("/#/projects");
  await expect(page.getByTestId("project-row").filter({ hasText: "Layout walk" })).toContainText("1 open · 1 closed");
  await measure("01-projects");
});
