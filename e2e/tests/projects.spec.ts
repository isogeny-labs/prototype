// Phase 5a end to end: projects and assessments, and the new app shell. Load demo projects, open Acme Pay, run it,
// switch to Migration demo, switch back and see Acme Pay exactly as left, start a new assessment, and see the old one
// read-only. Main-screen buttons only. Screenshots of every page, dark and light, go to docs/screenshots/phase5a/.
// Phase 5b: picking a project opens its Project overview; New assessment opens a box and closes nothing (both stay
// open); Close assessment is a sign-off with a name, and only then is the old one read-only.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { DISCLAIMER, REPO, enterApp, stepLink } from "./shared";

const SHOTS = path.join(REPO, "docs/screenshots/phase5a");
const DEPENDENCY_LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
const CLOSED = "This assessment is closed. Start a new one to continue.";

let context: BrowserContext;
let page: Page;
let acmePay: string;          // the address of Acme Pay's first assessment (#/a/<id>/...)
let evidenceRows: string[];   // Evidence as left, before switching away

/** One picture in the dark look and one in the light look (the same page, the same moment). */
async function shots(name: string, opts: { fullPage?: boolean } = {}): Promise<void> {
  const fullPage = opts.fullPage ?? true;
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** One row of the Projects table, by the project's exact name (other walks' projects are listed too). */
function projectRow(name: string) {
  return page.getByTestId("project-row").filter({ has: page.locator("p").getByText(name, { exact: true }) });
}

/** Phase 5b: the switcher opens the project's overview; its newest assessment's row opens that assessment. */
async function switchTo(project: string): Promise<void> {
  await page.getByRole("button", { name: /^Switch project/ }).click();
  const switcher = page.getByTestId("project-switcher");
  await switcher.getByRole("searchbox", { name: "Search projects" }).fill(project);
  await switcher.getByRole("option", { name: project, exact: true }).click();
  await expect(page.getByTestId("project-overview")).toBeVisible();
  await expect(page.getByRole("heading", { name: project, level: 1 })).toBeVisible();
  await page.getByTestId("assessment-row").first().click();
  await expect(page.getByTestId("overview-page")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(project);
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  context = await browser.newContext({ acceptDownloads: true });
  page = await context.newPage();
});

test.afterAll(async () => {
  await context.close();
});

test("Load demo projects: a Demo folder with one project per demo file, each with its file imported", async () => {
  await enterApp(page);
  await page.goto("/#/settings");
  await expect(page.getByTestId("settings-page")).toBeVisible();
  await shots("12-settings");
  await page.getByRole("button", { name: "Load demo projects" }).click();
  await expect(page.getByRole("status").filter({ hasText: /demo projects/ })).toBeVisible({ timeout: 60_000 });
  await page.goto("/#/projects");
  const rows = page.getByTestId("project-row");
  for (const name of ["Acme Pay", "Migration demo", "Multi-target", "Lab nginx (isolated mode)", "Real libraries (isolated mode)", "Real public servers (needs internet)"]) {
    await expect(projectRow(name)).toHaveCount(1);
  }
  // Real public servers were not contacted: nothing is verified there.
  await expect(projectRow("Real public servers (needs internet)")).toContainText("Not yet");
  // Running it twice adds nothing.
  await page.goto("/#/settings");
  await page.getByRole("button", { name: "Load demo projects" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The demo projects are already here. Nothing was added." })).toBeVisible();
  await page.goto("/#/projects");
  await expect(projectRow("Acme Pay")).toHaveCount(1);
  await shots("01-projects-home");
});

test("open Acme Pay from Projects: Overview with its file and the next step", async () => {
  // Phase 5b: the row opens the Project overview; the assessment's row opens its Overview.
  await projectRow("Acme Pay").click();
  await expect(page.getByTestId("project-overview")).toBeVisible();
  await expect(page.getByTestId("assessment-row")).toHaveCount(1);
  await page.getByTestId("assessment-row").first().click();
  await expect(page.getByTestId("overview-page")).toBeVisible();
  acmePay = page.url().replace(/\/overview$/, "");
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs).toContainText("Demo");
  await expect(crumbs).toContainText("Acme Pay");
  await expect(crumbs).toContainText("Assessment 1");
  await expect(page.getByTestId("assessment-status")).toHaveText(/Open/);
  await expect(page.getByTestId("next-step")).toContainText("Verify claims");
  await shots("02-overview-before");
});

test("run Acme Pay: Verify claims, then every suggested test", async () => {
  await stepLink(page, "Import").click();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await shots("03-inventory-import");
  // Phase 5a follow-up (approved by Kevin on 17 November 2026): a claim's row opens its details in the side panel.
  const claim = page.getByTestId("claim-row").first();
  const where = (await claim.locator("td").first().locator("div").first().innerText()).trim();
  await claim.click();
  const claimPanel = page.getByTestId("claim-panel");
  await expect(claimPanel).toBeVisible();
  await expect(claim).toHaveAttribute("aria-selected", "true");
  await expect(claimPanel.getByRole("heading", { level: 2 })).toHaveText(where);
  await expect(claimPanel.getByTestId("claim-details")).toContainText("Claimed value");
  await expect(claimPanel.getByTestId("claim-details")).toContainText("from the file");
  await expect(claimPanel.getByTestId("claim-details")).toContainText("Source in the file");
  await shots("03-inventory-import-panel");
  await claimPanel.getByRole("button", { name: "Close details" }).click();
  await expect(claimPanel).toHaveCount(0);
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
  await shots("04-inventory-verify");
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });
  await shots("05-tests");
});

test("Evidence: a table of results; a row opens the detail panel; Fixes and Migration in the new layout", async () => {
  await stepLink(page, "Evidence").click();
  await expect(page.getByText(DISCLAIMER)).toBeVisible();
  const rows = page.getByTestId("evidence-row");
  await expect(rows).toHaveCount(5);
  evidenceRows = await rows.allInnerTexts();
  await shots("06-evidence");
  await rows.filter({ hasText: "Attacker tricks" }).click();
  const panel = page.getByTestId("detail-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Attacker tricks");
  await shots("07-evidence-detail-panel");
  await panel.getByRole("button", { name: "Close details" }).click();
  await expect(panel).toHaveCount(0);

  await stepLink(page, "Fixes").click();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  await shots("08-fixes");

  await stepLink(page, "Systems").click();
  await page.getByRole("button", { name: /^Measure status/ }).click();
  await expect(page.getByRole("button", { name: /^Measure again/ })).toBeEnabled({ timeout: 120_000 });   // every system measured
  await shots("09-migration-systems");
  await stepLink(page, "Roadmap").click();
  await expect(page.getByTestId("roadmap-band").first()).toBeVisible();
  await expect(page.getByTestId("detail-panel")).toHaveCount(0);   // the Roadmap opens with no panel
  await shots("10-migration-roadmap");
  // Phase 5a follow-up (approved by Kevin on 17 November 2026): a system's name on the Roadmap opens that system's
  // detail panel. Opening it changes nothing: no request but reads goes to the backend.
  const roadmapRow = page.getByTestId("roadmap-row").first();
  const systemKey = await roadmapRow.getAttribute("data-system");
  const rowsBefore = await page.getByTestId("roadmap-row").allInnerTexts();
  const changing: string[] = [];
  const watch = (request: { method(): string; url(): string }) => {
    if (request.method() !== "GET") changing.push(`${request.method()} ${request.url()}`);
  };
  page.on("request", watch);
  await roadmapRow.getByRole("button").first().click();
  const systemPanel = page.getByTestId("detail-panel");
  await expect(systemPanel.getByTestId("migration-system")).toHaveAttribute("data-system", systemKey ?? "");
  await expect(roadmapRow.getByRole("button").first()).toHaveAttribute("aria-current", "true");
  await shots("10-migration-roadmap-panel");
  await page.keyboard.press("Escape");
  await expect(systemPanel).toHaveCount(0);
  page.off("request", watch);
  expect(changing).toEqual([]);
  expect(await page.getByTestId("roadmap-row").allInnerTexts()).toEqual(rowsBefore);
  await stepLink(page, "Dependencies").click();
  await expect(page.getByTestId("dependencies-view")).toBeVisible();
  await page.getByLabel("Choose a dependency list").setInputFiles(DEPENDENCY_LIST);
  await expect(page.getByTestId("dependency-row").first()).toBeVisible({ timeout: 30_000 });
  await shots("11-migration-dependencies");
});

test("switch to Migration demo, then back: Acme Pay is exactly as it was left", async () => {
  await switchTo("Migration demo");
  await expect(page.getByTestId("overview-page")).toContainText("migration-demo.csv");
  await stepLink(page, "Import").click();
  await expect(page.getByTestId("claim-row").first()).toContainText("localhost:845");
  await switchTo("Acme Pay");
  expect(page.url()).toContain(acmePay);
  // The Overview's counts are Acme Pay's own: 3 claims checked, 1 false (expected.json), tests run.
  const verification = page.getByTestId("overview-group").filter({ has: page.getByRole("heading", { name: "Verification" }) });
  await expect(verification.getByTestId("overview-fact")).toHaveText(["True 2", "False 1", "Couldn't check 0"]);
  await expect(page.getByTestId("finding-count").filter({ hasText: "False claims" })).toHaveText("False claims 1");
  await shots("02-overview-after");
  await stepLink(page, "Evidence").click();
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  expect(await page.getByTestId("evidence-row").allInnerTexts()).toEqual(evidenceRows);
  await stepLink(page, "Verify").click();
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
});

test("the project switcher (search and folder tree), the collapsed sidebar and the narrow-screen menu", async () => {
  await page.getByRole("button", { name: /^Switch project/ }).click();
  await expect(page.getByTestId("project-switcher")).toContainText("Demo");
  await shots("13-project-switcher", { fullPage: false });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.getByTestId("sidebar").first()).toHaveAttribute("data-collapsed", "true");
  await shots("14-sidebar-collapsed", { fullPage: false });
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await page.setViewportSize({ width: 420, height: 860 });
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeVisible();
  await shots("15-narrow-menu", { fullPage: false });
  await page.getByRole("dialog", { name: "Menu" }).getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Menu" })).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("New assessment: a fresh pass in Acme Pay; the old one stays open until it is signed off, then it is kept read-only", async () => {
  await stepLink(page, "Overview").click();
  await page.getByRole("button", { name: "New assessment" }).first().click();
  // Phase 5b: a box with the name filled in, a purpose and a reference; Start makes it and closes nothing.
  const box = page.getByTestId("new-assessment-box");
  await expect(box.getByLabel("Name")).toHaveValue("Assessment 2");
  await box.getByLabel("Purpose").selectOption({ label: "Release check" });
  await box.getByLabel("Reference (optional)").fill("Release 2.1");
  await box.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Assessment 2");
  await expect(page.getByTestId("assessment-status")).toHaveText(/Open/);
  await expect(page.getByTestId("assessment-purpose")).toHaveText("Release check");
  await expect(page.getByTestId("next-step")).toContainText("Bring in a scanner file");
  // The Project overview lists both; both are open.
  await page.getByTestId("to-project-overview").click();
  const rows = page.getByTestId("assessment-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Assessment 1" })).toContainText("Open");
  await expect(rows.filter({ hasText: "Assessment 2" })).toContainText("Open");
  await rows.filter({ hasText: "Assessment 1" }).click();
  await expect(page.getByTestId("overview-page")).toBeVisible();
  // Close assessment is a sign-off: a name is needed, and it can't be undone.
  await page.getByRole("button", { name: "Close assessment" }).click();
  const close = page.getByTestId("close-box");
  await expect(close.getByRole("button", { name: "Close and sign off" })).toBeDisabled();
  await close.getByLabel("Signed off by").fill("Demo reviewer");
  await close.getByRole("button", { name: "Close and sign off" }).click();
  await expect(page.getByTestId("closed-banner")).toContainText(CLOSED);
  await expect(page.getByTestId("assessment-status")).toHaveText(/Closed/);
  await expect(page.getByTestId("signoff-line")).toContainText("Signed off by Demo reviewer");
  await expect(page.getByRole("button", { name: "Close assessment" })).toHaveCount(0);
  await shots("16-closed-assessment");
  // Every action button is off, with the reason; downloads stay on.
  await stepLink(page, "Checks").click();
  const runAll = page.getByRole("button", { name: "Run all" });
  await expect(runAll).toBeDisabled();
  await expect(runAll).toHaveAttribute("title", CLOSED);
  await stepLink(page, "Evidence").click();
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  expect(await page.getByTestId("evidence-row").allInnerTexts()).toEqual(evidenceRows);   // kept exactly as it was
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeDisabled();
  // The backend refuses it too: a changing request on a closed assessment answers with the same sentence.
  const planId = await page.evaluate(async (url) => {
    const id = Number(/#\/a\/(\d+)/.exec(url)?.[1]);
    const a = await (await fetch(`/api/assessments/${id}`)).json();
    return a.plan_id as number;
  }, acmePay);
  const refused = await page.request.post(`/api/plans/${planId}/run-all`);
  expect(refused.status()).toBe(409);
  expect((await refused.json()).error.message).toBe(CLOSED);
  await shots("17-closed-evidence");
});
