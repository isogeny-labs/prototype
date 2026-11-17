// Phase 5b end to end: one finding followed from its claim to the Project overview, by the links between pages only:
// the claim on Import -> its Verify result -> its check on Checks -> the test's result on Evidence -> its fix on Fixes
// -> the system's migration track -> the Project overview. Every link opens exactly that item, and Back returns.
// It runs on a copy of the app of its own (own data folder and ports), so the main app is never touched.
// Main-screen buttons and links only. Screenshots, dark and light at 1440 pixels wide, go to docs/screenshots/phase5b/.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { enterApp, openFreshAssessment, screenshotFolder, startCopy, stepLink, stopCopy, type Copy } from "./shared";

const SHOTS = screenshotFolder("phase5b");
let copy: Copy | null = null;

async function shots(page: Page, name: string): Promise<void> {
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

/** The Related block's link of one kind ("claim", "test", "fix", "system", "library") with this label. */
function related(page: Page, kind: string, label: string | RegExp) {
  return page
    .getByTestId("detail-panel")
    .locator(`[data-testid="related-line"][data-kind="${kind}"] [data-testid="related-link"]`)
    .filter({ hasText: label });
}

test.describe.configure({ mode: "serial", timeout: 600_000 });

test.afterAll(async () => {
  await stopCopy(copy);
});

test("one finding, end to end: claim, check, evidence, fix, migration track and the Project overview", async ({ browser }) => {
  copy = await startCopy(browser, 5, "demo");
  const page = copy.page;
  const claim = `${copy.server} accepts TLS 1.3 only`;
  await enterApp(page);
  await openFreshAssessment(page, "Finding walk");

  // Bring the demo file in and verify it (main-screen buttons only).
  await page.getByRole("button", { name: "Use demo file" }).click();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
  // The tests have results before the walk starts following links.
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });

  // ---- 1. The claim, as the file states it, on Import; its panel links to its Verify result.
  await stepLink(page, "Import").click();
  await page.getByTestId("claim-row").filter({ hasText: claim }).click();
  const claimPanel = page.getByTestId("claim-panel");
  await expect(claimPanel).toBeVisible();
  await shots(page, "finding-01-claim-on-import");
  await claimPanel.getByTestId("claim-to-verify").click();
  await expect(page).toHaveURL(/\/inventory\/verify\?item=claim-\d+$/);
  await expect(page.getByTestId("result-row").filter({ hasText: claim })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("detail-panel")).toContainText("What we found");
  await shots(page, "finding-02-verify-result");
  // Back returns to Import.
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();

  // ---- 2. The same claim on Checks, in Verification, with the test that checks it in Related.
  await stepLink(page, "Checks").click();
  const verification = page.getByTestId("group-section").filter({ has: page.getByRole("heading", { name: "Verification" }) });
  await verification.getByTestId("check-row").filter({ hasText: claim }).click();
  const checkPanel = page.getByTestId("check-panel");
  await expect(checkPanel).toBeVisible();
  await expect(checkPanel.getByTestId("result-badge").first()).toHaveText("False");
  await expect(checkPanel.getByTestId("open-where-started")).toHaveAttribute("href", /\/inventory\/verify\?item=claim-\d+$/);
  const toTest = related(page, "test", "Old TLS versions");
  await expect(toTest).toHaveCount(1);
  await shots(page, "finding-03-check-on-checks");

  // ---- 3. The test's result on Evidence: it failed, and its fix line opens the fix.
  await toTest.click();
  await expect(page).toHaveURL(/\/evidence\?item=test-\d+$/);
  const evidencePanel = page.getByTestId("detail-panel");
  await expect(evidencePanel.getByRole("heading", { level: 2, name: "Old TLS versions", exact: true })).toBeVisible();
  await expect(evidencePanel.getByTestId("result-badge").first()).toHaveText("Failed");
  await expect(related(page, "claim", claim)).toHaveCount(1);
  await shots(page, "finding-04-result-on-evidence");
  await evidencePanel.getByRole("button", { name: "View in Fixes" }).click();

  // ---- 4. The fix on Fixes, in Encryption tests (it came from a failed test), with the system it is about.
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  const fixPanel = page.getByTestId("detail-panel");
  await expect(fixPanel.getByRole("heading", { level: 2, name: "Server accepts TLS 1.2" })).toBeVisible();
  const encryption = page.getByTestId("group-section").filter({ has: page.getByRole("heading", { name: "Encryption tests" }) });
  await expect(encryption.getByTestId("fix-row").filter({ hasText: "Server accepts TLS 1.2" })).toHaveAttribute("aria-selected", "true");
  await expect(related(page, "test", "Old TLS versions")).toHaveCount(1);
  const toSystem = related(page, "system", copy.server);
  await expect(toSystem).toHaveCount(1);
  await shots(page, "finding-05-fix-on-fixes");

  // ---- 5. The system's migration track, on the Roadmap, with the fix in its Related block.
  await toSystem.click();
  await expect(page).toHaveURL(/\/migration\/roadmap\?item=server%3Alocalhost%3A\d+$/);
  await expect(page.getByTestId("detail-panel").getByTestId("migration-system")).toHaveAttribute("data-system", `server:${copy.server}`);
  await expect(related(page, "fix", "Server accepts TLS 1.2")).toHaveCount(1);
  await shots(page, "finding-06-system-on-roadmap");
  // Back returns to the fix.
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  await expect(page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: "Server accepts TLS 1.2" })).toBeVisible();

  // ---- 6. The Project overview: the assessment with its counts, as its pages count them.
  await page.getByTestId("sidebar").first().getByRole("link", { name: "Project overview" }).click();
  await expect(page.getByTestId("project-overview")).toBeVisible();
  const row = page.getByTestId("assessment-row");
  await expect(row).toHaveCount(1);
  for (const words of ["3 checked", "1 false", "failed", "of 5 run"]) await expect(row).toContainText(words);
  await expect(page.getByTestId("project-overview")).not.toContainText(/\bscore\b|\bgrade\b|secure|time to hack/i);
  await shots(page, "finding-07-project-overview");
  // The assessment's own Overview holds the same finding, in its group.
  await row.click();
  await expect(page.getByTestId("overview-page")).toBeVisible();
  await expect(page.getByTestId("finding-count").filter({ hasText: "False claims" })).toHaveText("False claims 1");
});
