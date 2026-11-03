import { test, expect, type Page } from "@playwright/test";

const PROJECTS = [
  { id: "proj-crypto-acme", run: "run-003", finding: "fnd-001", name: "Acme Pay signing service" },
  { id: "proj-eng-mb200", run: "run-E-001", finding: "fnd-E-001", name: "Mounting bracket MB-200" },
  { id: "proj-legal-northwind", run: "run-L-001", finding: "fnd-L-001", name: "Northwind Supply v. Harbor Fabrication (fictional)" },
];
const SUBROUTES = ["", "/intake", "/artifacts", "/tests", "/research", "/conductor", "/runs", "/findings", "/approvals", "/changes", "/reports", "/settings", "/memory"];

async function settle(page: Page) {
  await expect.poll(async () => page.getByTestId("loading-state").count(), { timeout: 20_000 }).toBe(0);
}
function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

for (const p of PROJECTS) {
  test.describe(`${p.name}: every route renders directly by URL`, () => {
    for (const sub of SUBROUTES) {
      test(`/p/${p.id}${sub}`, async ({ page }) => {
        const errors = collectErrors(page);
        await page.goto(`/p/${p.id}${sub}`);
        await settle(page);
        await expect(page.getByTestId("sample-banner")).toBeVisible();
        await expect(page.getByTestId("error-state")).toHaveCount(0);
        expect(errors, errors.join("\n")).toEqual([]);
      });
    }
    test(`/p/${p.id}/runs/${p.run} and /findings/${p.finding}`, async ({ page }) => {
      const errors = collectErrors(page);
      await page.goto(`/p/${p.id}/runs/${p.run}`); await settle(page);
      await expect(page.getByTestId("run-status")).toHaveCount(1);
      await page.goto(`/p/${p.id}/findings/${p.finding}`); await settle(page);
      await expect(page.getByTestId("finding-statement")).toBeVisible();
      expect(errors, errors.join("\n")).toEqual([]);
    });
  });
}

test("home and sample-data settings render", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/"); await settle(page);
  await expect(page.getByTestId("project-card")).toHaveCount(3);
  await expect(page.getByTestId("pack-card")).toHaveCount(3);
  await expect(page.getByText("Coming in Phase 2")).toHaveCount(0);
  await page.goto("/settings/sample-data"); await settle(page);
  await expect(page.getByTestId("reset-sample")).toBeVisible();
  expect(errors).toEqual([]);
});

test("nothing scrolls horizontally at 1024px wide", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  const routes = PROJECTS.flatMap((p) => [`/p/${p.id}`, `/p/${p.id}/runs/${p.run}`, `/p/${p.id}/findings/${p.finding}`, `/p/${p.id}/changes`, `/p/${p.id}/conductor`]);
  for (const route of routes) {
    await page.goto(route); await settle(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, route).toBeLessThanOrEqual(0);
  }
});

test("the crypto story is visible end to end", async ({ page }) => {
  await page.goto("/p/proj-crypto-acme/findings"); await settle(page);
  await expect(page.getByTestId("finding-row")).toHaveCount(3);
  await expect(page.locator('[data-testid="evidence-label"][data-label="Expert-reviewed"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="evidence-label"][data-label="Estimate"]')).toHaveCount(1);
  await page.goto("/p/proj-crypto-acme/findings/fnd-001"); await settle(page);
  await expect(page.getByTestId("check")).toHaveCount(6);
  await expect(page.getByTestId("finding-timeline")).toContainText("Retested");
  await page.goto("/p/proj-crypto-acme/runs"); await settle(page);
  await expect(page.locator('[data-testid="run-row"][data-superseded="true"]')).toHaveCount(2);
  await page.goto("/p/proj-crypto-acme/tests"); await settle(page);
  await expect(page.locator('[data-testid="test-row"][data-runnable="false"]')).toHaveCount(2);
  await expect(page.locator('[data-testid="test-row"][data-runnable="false"] button')).toHaveCount(0);
  await page.goto("/p/proj-crypto-acme"); await settle(page);
  await expect(page.getByTestId("attack-row")).toHaveCount(5);
  await expect(page.getByTestId("disclaimers")).toContainText("does not prove a cryptographic implementation secure");
});

test("the engineering story is visible end to end", async ({ page }) => {
  await page.goto("/p/proj-eng-mb200"); await settle(page);
  await expect(page.getByTestId("model-setup")).toContainText("276 MPa");
  await expect(page.getByTestId("stress-view")).toContainText("fillet 118 MPa (peak)");
  await expect(page.getByTestId("convergence")).toContainText("Not converged");
  await expect(page.getByTestId("convergence")).toContainText("Converged");
  await expect(page.getByTestId("disclaimers")).toContainText("not physical certification");
  await page.goto("/p/proj-eng-mb200/changes"); await settle(page);
  await expect(page.getByTestId("comparison").first()).toContainText("Safety factor >= 2.0");
  await expect(page.getByTestId("comparison").first()).toContainText("2.34");
  await page.goto("/p/proj-eng-mb200/runs"); await settle(page);
  await expect(page.locator('[data-testid="run-row"] [data-testid="execution-mode"][data-mode="imported"]')).toHaveCount(1);
});

test("the legal story is visible end to end, with fictional labels and no prediction", async ({ page }) => {
  await page.goto("/p/proj-legal-northwind"); await settle(page);
  await expect(page.getByTestId("chronology")).toContainText("Delivery received");
  await expect(page.getByTestId("rehearsal-disclaimer")).toHaveText("Preparation exercise, not a prediction of the outcome.");
  await expect(page.getByTestId("fictional-label")).toHaveCount(3);
  // No numeric win probability anywhere (the disclaimer may mention the phrase; a figure may not appear).
  await expect(page.getByText(/(win|success)\s+(probability|likelihood|chance)s?\s*[:=]?\s*\d/i)).toHaveCount(0);
  await expect(page.getByTestId("rehearsal")).not.toContainText(/\d+\s*%/);
  await expect(page.locator('[data-testid="check-row"][data-result="unsupported"]')).toHaveCount(1);
  await expect(page.getByTestId("disclaimers")).toContainText("Not legal advice");
  // Deep link from a disputed fact into the document viewer at the receipt line.
  await page.locator('[data-testid="check-row"][data-result="unsupported"] [data-testid="doc-link"]').last().click();
  await settle(page);
  await expect(page.getByTestId("document-viewer")).toContainText("Delivered: 10 March 2026");
  await expect(page.locator('[data-testid="document-viewer"] [data-line="8"]')).toHaveClass(/bg-warn/);
  await page.goto("/p/proj-legal-northwind/settings"); await settle(page);
  await expect(page.getByText("Confidential", { exact: true })).toBeVisible();
});

test("logo or wordmark is present and the project switcher lists all sample projects", async ({ page }) => {
  await page.goto("/"); await settle(page);
  expect((await page.getByTestId("logo").count()) + (await page.getByTestId("wordmark").count())).toBeGreaterThan(0);
  for (const p of PROJECTS) await expect(page.getByTestId("project-switcher")).toContainText(p.name);
});
