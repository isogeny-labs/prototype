// Phase 5b end to end: every page with a table, at 1440 pixels wide, with its side panel closed and open. On each:
// the page never scrolls sideways, no table scrolls sideways, and no name in a table is broken between letters (a name
// may break only at a space or a dot, dash or slash). It also takes the phase 5b screenshots of every changed page, dark
// and light, with and without the panel, into docs/screenshots/phase5b/.
// It runs on a copy of the app of its own (own data folder and ports), so the main app is never touched.
// Main-screen buttons only.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { REPO, enterApp, layoutProblems, openFreshAssessment, screenshotFolder, startCopy, stepLink, stopCopy, type Copy } from "./shared";

const SHOTS = screenshotFolder("phase5b");
const LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
let copy: Copy | null = null;
let page: Page;

async function shots(name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: true, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** Measures the page with its panel closed, then opens a row's panel and measures again; takes both screenshots. */
async function measure(name: string, open?: () => Promise<void>): Promise<void> {
  const panel = page.getByTestId("detail-panel").or(page.getByTestId("claim-panel"));
  if ((await panel.count()) > 0) {
    await panel.first().getByRole("button", { name: "Close details" }).click();
    await expect(panel).toHaveCount(0);
  }
  expect(await layoutProblems(page), `${name}, panel closed`).toEqual([]);
  await shots(`${name}-panel-closed`);
  if (!open) return;
  await open();
  await expect(panel.first()).toBeVisible();
  // The panel asks for its own part (a check's every run, the Related block): wait for it before measuring and the picture.
  await page.waitForLoadState("networkidle");
  const checkPanel = page.getByTestId("check-panel");
  if ((await checkPanel.count()) > 0) await expect(checkPanel.getByTestId("earlier-runs")).toBeVisible();
  // The table (or the Roadmap's plan) beside the panel is in its compact form.
  await expect(page.locator('main [data-compact="true"]').first()).toBeVisible();
  expect(await layoutProblems(page), `${name}, panel open`).toEqual([]);
  await shots(`${name}-panel-open`);
}

test.describe.configure({ mode: "serial", timeout: 900_000 });

test.afterAll(async () => {
  await stopCopy(copy);
});

test("every table page at 1440 pixels wide, its panel closed and open: no sideways scrolling, no name broken between letters", async ({ browser }) => {
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
  await stepLink(page, "Systems").click();
  await page.getByTestId("page-content").getByRole("button", { name: /^Measure status/ }).click();
  await expect(page.getByTestId("page-content").getByRole("button", { name: /^Measure again/ })).toBeEnabled({ timeout: 120_000 });
  await stepLink(page, "Dependencies").click();
  await page.getByLabel("Choose a dependency list").setInputFiles(LIST);
  await expect(page.getByTestId("dependency-row").first()).toBeVisible({ timeout: 30_000 });

  // ---- Checks
  await stepLink(page, "Checks").click();
  await expect(page.getByTestId("group-section")).toHaveCount(4);
  await measure("06-checks", () => page.getByTestId("check-row").first().click());

  // ---- Evidence: a result, a claim's check, a library
  await stepLink(page, "Evidence").click();
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  await measure("07-evidence", () => page.getByTestId("evidence-row").first().click());
  await measure("07-evidence-claim", () => page.getByTestId("check-row").first().click());
  await measure("07-evidence-library", () => page.getByTestId("library-row").first().click());

  // ---- Fixes
  await stepLink(page, "Fixes").click();
  await expect(page.getByTestId("fix-row").first()).toBeVisible();
  await measure("08-fixes", () => page.getByTestId("fix-row").first().click());

  // ---- Migration: Systems, Roadmap, Dependencies
  await stepLink(page, "Systems").click();
  await expect(page.getByTestId("system-card").first()).toBeVisible();
  await measure("09-migration-systems", () => page.getByTestId("system-card").first().click());
  await stepLink(page, "Roadmap").click();
  await expect(page.getByTestId("roadmap-row").first()).toBeVisible();
  await measure("10-migration-roadmap", () => page.getByTestId("roadmap-row").first().getByRole("button").first().click());
  await stepLink(page, "Dependencies").click();
  await expect(page.getByTestId("dependency-row").first()).toBeVisible();
  await measure("11-migration-dependencies", () => page.getByTestId("dependency-row").filter({ hasText: "openssl 3.0.22" }).first().locator("p.font-mono").click());

  // ---- The Overview, then a second pass of the same file (Rerun as new assessment), for the Project overview
  await stepLink(page, "Overview").click();
  await expect(page.getByTestId("overview-groups")).toBeVisible();
  // The Overview repeats what the pages say now: every test has run, the systems are measured, the list is in.
  const group = (name: string) => page.getByTestId("overview-group").filter({ has: page.getByRole("heading", { name }) });
  await expect(group("Encryption tests")).toContainText("Checks: Open 0");
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
