import { test, expect, type Page } from "@playwright/test";

const P = "proj-crypto-acme";
const ROUTES = [
  "/", `/p/${P}`, `/p/${P}/intake`, `/p/${P}/artifacts`, `/p/${P}/tests`, `/p/${P}/research`, `/p/${P}/conductor`,
  `/p/${P}/runs`, `/p/${P}/runs/run-003`, `/p/${P}/findings`, `/p/${P}/findings/fnd-001`, `/p/${P}/approvals`,
  `/p/${P}/changes`, `/p/${P}/reports`, `/p/${P}/settings`, `/p/${P}/memory`, "/settings/sample-data",
];

async function settle(page: Page) {
  // Wait for every loading state to clear (mock latency is 250 ms per call, calls are chained in places).
  await expect.poll(async () => page.getByTestId("loading-state").count(), { timeout: 15_000 }).toBe(0);
}

test.describe("every route renders with sample data", () => {
  for (const route of ROUTES) {
    test(`${route} renders, shows the sample banner and has no console errors`, async ({ page }) => {
      const errors: string[] = [];
      page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(route);
      await settle(page);
      await expect(page.getByTestId("sample-banner")).toBeVisible();
      await expect(page.getByTestId("error-state")).toHaveCount(0);
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }
});

test("nothing scrolls horizontally at 1024px wide", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  for (const route of [`/p/${P}`, `/p/${P}/runs/run-010`, `/p/${P}/findings/fnd-001`, `/p/${P}/changes`, `/p/${P}/conductor`]) {
    await page.goto(route);
    await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, route).toBeLessThanOrEqual(0);
  }
});

test("the crypto story is visible end to end", async ({ page }) => {
  await page.goto(`/p/${P}/findings`);
  await settle(page);
  const rows = page.getByTestId("finding-row");
  await expect(rows).toHaveCount(3);
  await expect(page.locator('[data-testid="evidence-label"][data-label="Expert-reviewed"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="evidence-label"][data-label="Estimate"]')).toHaveCount(1);
  await page.goto(`/p/${P}/findings/fnd-001`);
  await settle(page);
  await expect(page.getByTestId("check")).toHaveCount(6);
  await expect(page.getByTestId("finding-timeline")).toContainText("Retested");
  await page.goto(`/p/${P}/runs`);
  await settle(page);
  await expect(page.locator('[data-testid="run-row"][data-superseded="true"]')).toHaveCount(2);
  await page.goto(`/p/${P}/tests`);
  await settle(page);
  await expect(page.locator('[data-testid="test-row"][data-runnable="false"]')).toHaveCount(2);
  await expect(page.locator('[data-testid="test-row"][data-runnable="false"] button')).toHaveCount(0);
});

test("logo or wordmark is present and the project switcher lists the sample project", async ({ page }) => {
  await page.goto("/");
  await settle(page);
  const logo = page.getByTestId("logo"); const wordmark = page.getByTestId("wordmark");
  expect((await logo.count()) + (await wordmark.count())).toBeGreaterThan(0);
  await expect(page.getByTestId("project-switcher")).toContainText("Acme Pay signing service");
});
