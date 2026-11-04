/**
 * Spec section 10 acceptance tests, one block per item. Items already covered elsewhere are cross-referenced:
 *  - "Every route loads directly by URL for every sample project, with no console errors"  → routes.spec.ts
 *  - "Sample consistency" (unit)                                                            → tests/unit/fixtures.test.ts
 *  - "Approvals: approve, reject, request-changes; self-approval; resolution needs retest"   → phase3.spec.ts
 *  - "Failed runs with failure injection"                                                    → phase3.spec.ts
 *  - "The assistant refuses a request to change acceptance criteria"                         → phase3.spec.ts (drafts instead; creates nothing until confirmed)
 *  - "Reset-to-sample-data restores the original fixtures after edits"                       → phase3.spec.ts
 */
import { test, expect, type Page } from "@playwright/test";

async function settle(page: Page) { await expect.poll(async () => page.getByTestId("loading-state").count(), { timeout: 20_000 }).toBe(0); }

test("navigation needs no prerequisites: opening Findings first works without visiting Intake", async ({ browser }) => {
  const ctx = await browser.newContext(); // fresh session, nothing visited before
  const page = await ctx.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/p/proj-legal-northwind/findings"); await settle(page);
  await expect(page.getByTestId("finding-row")).toHaveCount(3);
  await page.getByTestId("finding-row").first().click(); await settle(page);
  await expect(page.getByTestId("finding-statement")).toBeVisible();
  expect(errors).toEqual([]);
  await ctx.close();
});

test("evidence comparison: the crypto and engineering comparisons show the previously failing case, the deltas and any regression", async ({ page }) => {
  await page.goto("/p/proj-crypto-acme/changes"); await settle(page);
  const crypto = page.getByTestId("comparison").filter({ hasText: "Malformed-signature rejection" });
  await expect(crypto).toContainText("r = 0, s = 0");
  await expect(crypto).toContainText("+12.5");
  await expect(crypto).toContainText("No regression");
  const latency = page.getByTestId("comparison").filter({ hasText: "Verification latency" });
  await expect(latency).toContainText("+0.03");
  await expect(latency).toContainText("None observed in the compared runs");
  await page.goto("/p/proj-eng-mb200/changes"); await settle(page);
  const eng = page.getByTestId("comparison").filter({ hasText: "Static result" });
  await expect(eng).toContainText("Safety factor >= 2.0");
  await expect(eng).toContainText("-53");
  await expect(eng).toContainText("2.34");
  await expect(eng.locator("text=▼ Regression")).toHaveCount(0);
});

test("labels: a finding backed only by agreeing agent claims shows no Machine-checked or Expert-reviewed label", async ({ page }) => {
  await page.goto("/p/proj-crypto-acme/findings/fnd-002"); await settle(page);
  const labels = page.locator('[data-testid="evidence-label"]');
  await expect(labels.first()).toHaveAttribute("data-label", "Estimate");
  await expect(page.locator('[data-testid="evidence-label"][data-label="Machine-checked"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="evidence-label"][data-label="Expert-reviewed"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="check-kind"]')).toHaveCount(2);
  await expect(page.getByText("agreement between agents does not raise the label", { exact: false })).toBeVisible();
});

test("disclaimers appear on the engineering results, the legal rehearsal and the crypto results views", async ({ page }) => {
  await page.goto("/p/proj-eng-mb200"); await settle(page);
  await expect(page.getByTestId("disclaimers")).toContainText("not physical certification");
  await page.goto("/p/proj-eng-mb200/runs/run-E-005"); await settle(page);
  await expect(page.getByText("not physical certification", { exact: false })).toBeVisible();
  await page.goto("/p/proj-legal-northwind"); await settle(page);
  await expect(page.getByTestId("rehearsal-disclaimer")).toHaveText("Preparation exercise, not a prediction of the outcome.");
  await expect(page.getByTestId("disclaimers")).toContainText("Not legal advice");
  await page.goto("/p/proj-crypto-acme/findings"); await settle(page);
  await expect(page.getByText("does not prove a cryptographic implementation secure", { exact: false })).toBeVisible();
  await page.goto("/p/proj-crypto-acme/runs/run-003"); await settle(page);
  await expect(page.getByText("does not prove a cryptographic implementation secure", { exact: false })).toBeVisible();
});

test("no universal security score, secure badge, certified stamp or win probability anywhere in the three samples", async ({ page }) => {
  // Disclaimers may *mention* these words to deny them ("no win probability is shown"); a value or a stamp may not appear.
  const banned = [/security score\s*[:=]?\s*\d/i, /\bcertified\b/i, /\bsecure\b\s*badge/i, /(win probability|probability of success|chance of winning|likelihood of success)\s*[:=]?\s*\d/i, /\d+\s*%\s*(chance|probability|likelihood)/i];
  for (const p of ["proj-crypto-acme", "proj-eng-mb200", "proj-legal-northwind"]) {
    for (const sub of ["", "/findings", "/reports", "/changes"]) {
      await page.goto(`/p/${p}${sub}`); await settle(page);
      const text = await page.locator("main").innerText();
      // the home-page sentence "Nothing on these pages is a security score…" lives outside /p routes; results views must not say it at all
      for (const re of banned) expect(text, `${p}${sub} matches ${re}`).not.toMatch(re);
    }
  }
});
