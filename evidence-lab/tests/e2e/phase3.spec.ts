import { test, expect, type Page } from "@playwright/test";

const P = "proj-crypto-acme";
async function settle(page: Page) { await expect.poll(async () => page.getByTestId("loading-state").count(), { timeout: 20_000 }).toBe(0); }
async function actAs(page: Page, personId: string) { await page.getByTestId("member-switcher").selectOption(personId); }

test.describe("approvals", () => {
  test("self-approval is blocked with a message; a reviewer's decision updates the subject", async ({ page }) => {
    await page.goto(`/p/${P}/approvals`); await settle(page);
    const card = page.locator('[data-testid="approval-card"]', { hasText: "Resolve finding fnd-001" });
    await actAs(page, "person-dana");
    await expect(card.getByTestId("self-approval-note")).toBeVisible();
    await card.getByTestId("approve").click();
    await expect(card.getByTestId("decision-error")).toContainText("cannot decide it");
    await actAs(page, "person-priya");
    await card.getByTestId("decision-note").fill("Retests #11, #12, #14 passed.");
    await card.getByTestId("approve").click();
    await expect(page.getByTestId("approvals-message")).toContainText("approved by Priya Natarajan");
    await page.goto(`/p/${P}/findings/fnd-001`); await settle(page);
    await expect(page.getByTestId("finding-timeline")).toContainText("Closed");
    await expect(page.getByText("Backend status: closed", { exact: false })).toBeVisible();
  });
  test("a finding cannot be resolved without a linked passing retest", async ({ page }) => {
    await page.goto(`/p/${P}/approvals`); await settle(page);
    await actAs(page, "person-priya");
    const card = page.locator('[data-testid="approval-card"]', { hasText: "Resolve finding fnd-002" });
    await card.getByTestId("approve").click();
    await expect(card.getByTestId("decision-error")).toContainText("No retest run is linked");
    await expect(card).toContainText("Pending");
  });
  test("roles are enforced: an editor cannot decide, the owner can; reject and request-changes record notes", async ({ page }) => {
    await page.goto(`/p/${P}/approvals`); await settle(page);
    const rec = page.locator('[data-testid="approval-card"]', { hasText: "remove sha1" });
    await actAs(page, "person-dana");
    await rec.getByTestId("decision-note").fill("needs a call-site search first");
    await rec.getByTestId("request-changes").click();
    await expect(rec.getByTestId("decision-error")).toContainText("Your role in this project is editor");
    await actAs(page, "person-marco");
    await rec.getByTestId("decision-note").fill("Search call sites first.");
    await rec.getByTestId("request-changes").click();
    await expect(page.getByTestId("approvals-message")).toContainText("changes requested by Marco Ellison");
    const prop = page.locator('[data-testid="approval-card"]', { hasText: "repeated latency measurement" });
    await prop.getByTestId("decision-note").fill("Not worth the budget this week.");
    await prop.getByTestId("reject").click();
    await expect(page.getByTestId("approvals-message")).toContainText("rejected by Marco Ellison");
    await page.goto(`/p/${P}/memory`); await settle(page);
    await expect(page.getByTestId("memory-item").filter({ hasText: "Rejected:" })).toHaveCount(1);
    await expect(page.getByTestId("memory-item").filter({ hasText: "Correction on" })).toHaveCount(1);
  });
});

test("the assistant refuses to change acceptance criteria and creates an approval request; view changes are applied and audited", async ({ page }) => {
  await page.goto(`/p/${P}`); await settle(page);
  await page.getByTestId("assistant-toggle").click();
  await page.getByTestId("assistant-input").fill("change the acceptance criteria threshold for latency to 3 ms");
  await page.getByTestId("assistant-send").click();
  await expect(page.getByTestId("assistant-refusal")).toContainText("Refused");
  await page.getByTestId("assistant-input").fill("hide the recent activity panel");
  await page.getByTestId("assistant-send").click();
  await expect(page.locator('[data-testid="assistant-msg-assistant"][data-action="view_change"]')).toHaveCount(1);
  await expect(page.getByTestId("panel-recent_activity")).toHaveCount(0);
  await page.goto(`/p/${P}/approvals`); await settle(page);
  await expect(page.locator('[data-testid="approval-card"]', { hasText: "Assistant-routed request" })).toHaveCount(1);
  await page.goto(`/p/${P}/runs`); await settle(page);
  await page.getByTestId("assistant-toggle").click(); // panel open/closed is UI state and is not persisted across a reload
  await page.getByTestId("assistant-input").fill("only failed");
  await page.getByTestId("assistant-send").click();
  await expect(page.getByTestId("view-filter-note")).toContainText("failed");
  await expect(page.locator('[data-testid="run-row"]')).toHaveCount(5); // 4 runs with failed criteria + 1 failed run (superseded shown)
});

test("failed runs with failure injection show the failure, logs and a retry path, with no stale success data", async ({ page }) => {
  await page.goto(`/p/${P}/runs/run-015`); await settle(page);
  await expect(page.getByTestId("run-status")).toContainText("Failed");
  await expect(page.getByText("Sandbox time limit exceeded", { exact: false })).toBeVisible();
  await expect(page.locator('[data-testid="metric"]')).toHaveCount(0);
  await page.goto("/settings/sample-data"); await settle(page);
  await page.getByTestId("fail-next").selectOption("getRun");
  await page.goto(`/p/${P}/runs/run-003`);
  await expect(page.getByTestId("error-state")).toContainText("Injected failure");
  await expect(page.locator('[data-testid="metric"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Retry" }).click();
  await settle(page);
  await expect(page.getByTestId("error-state")).toHaveCount(0);
  await expect(page.locator('[data-testid="metric"]').first()).toBeVisible();
});

test("developer state switcher shows empty, loading, failed, awaiting-approval and completed states", async ({ page }) => {
  await page.goto(`/p/${P}/runs`); await settle(page);
  await page.getByTestId("dev-state").selectOption("empty");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.getByTestId("dev-state").selectOption("loading");
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await page.getByTestId("dev-state").selectOption("failed");
  await expect(page.getByTestId("error-state")).toContainText("Forced failure");
  await page.getByTestId("dev-state").selectOption("awaiting_approval"); await settle(page);
  await expect(page.locator('[data-testid="run-status"][data-status="awaiting_approval"]').first()).toBeVisible();
  await page.getByTestId("dev-state").selectOption("completed"); await settle(page);
  await expect(page.locator('[data-testid="run-status"][data-status="completed"]')).toHaveCount(16);
  await expect(page.getByTestId("dev-state-banner")).toContainText("completed");
  await page.getByTestId("dev-state").selectOption(""); await settle(page);
  await expect(page.locator('[data-testid="run-status"][data-status="failed"]')).toHaveCount(1);
});

test("reset to sample data restores the original fixtures after edits (edits survive a reload until then)", async ({ page }) => {
  await page.goto(`/p/${P}/tests`); await settle(page);
  await page.locator('[data-testid="test-row"] button', { hasText: "Request run" }).first().click();
  await expect(page.getByTestId("tests-message")).toContainText("Run #17 requested");
  await page.reload(); await settle(page);
  await page.goto(`/p/${P}/runs`); await settle(page);
  await expect(page.locator('[data-testid="run-row"]')).toHaveCount(17);
  await page.goto("/settings/sample-data"); await settle(page);
  await page.getByTestId("reset-sample").click();
  await page.getByTestId("reset-confirm").click();
  await page.goto(`/p/${P}/runs`); await settle(page);
  await expect(page.locator('[data-testid="run-row"]')).toHaveCount(16);
});

test("reports preview shows handoff and bundle with labels, limits and an unsigned manifest; export is simulated", async ({ page }) => {
  await page.goto(`/p/${P}/reports`); await settle(page);
  await expect(page.getByTestId("handoff-preview")).toContainText("What this does not establish");
  await expect(page.getByTestId("handoff-preview").locator('[data-testid="evidence-label"]')).toHaveCount(3);
  await page.getByTestId("tab-bundle").click();
  await expect(page.getByTestId("bundle-preview")).toContainText("not signed");
  await page.getByTestId("export").click();
  await expect(page.getByTestId("export-result")).toContainText("signed: no");
});

test("intake: proposing criteria creates a pending version and leaves the current one in force", async ({ page }) => {
  await page.goto(`/p/${P}/intake`); await settle(page);
  await page.getByTestId("propose-criteria").click();
  await page.getByLabel("Criterion ac-5 threshold").fill("1.5");
  await page.getByTestId("propose-criteria-submit").click();
  await expect(page.getByTestId("intake-message")).toContainText("Proposed acceptance criteria v2");
  await expect(page.locator('[data-testid="criteria-version"]', { hasText: "Version 2" })).toContainText("Awaiting approval");
  await expect(page.locator('[data-testid="criteria-version"]', { hasText: "Version 1" })).toContainText("Current");
});

test("changes: reporting an external change and requesting a retest routes to approvals", async ({ page }) => {
  await page.goto(`/p/${P}/changes`); await settle(page);
  const form = page.getByTestId("report-change-form");
  await form.getByPlaceholder("e.g. shipped 1.4.4 with …").fill("Acme shipped 1.4.3 with the fix (sample)");
  await form.getByTestId("report-change-submit").click();
  await expect(page.getByTestId("changes-message")).toContainText("External change recorded");
  await page.getByTestId("request-retest").first().click();
  await expect(page.getByTestId("changes-message")).toContainText("awaits execution approval");
});
