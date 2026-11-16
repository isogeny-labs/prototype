// Things the test files share: the throwaway password, the one fixed line every result screen carries,
// and "get me into the app" (create the password on a brand-new data folder, or log in).
import { expect, type Locator, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const REPO = path.resolve(here, "../..");
export const BACKEND = path.join(REPO, "backend");
export const PYTHON = path.join(BACKEND, ".venv/bin/python");

export const DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed.";

// Made once per run by playwright.config.ts, for the throwaway data folder. It is never written anywhere.
export const password: string = process.env.E2E_PASSWORD ?? "";
if (!password) throw new Error("E2E_PASSWORD is not set; run the tests with `npm test` from the e2e folder.");

export function screenshotFolder(
  phase: "phase1" | "phase2" | "phase3a" | "phase3a-fixes" | "phase4a" | "phase4b" | "phase4c" | "phase4d" | "phase5a",
): string {
  return path.join(REPO, "docs/screenshots", phase);
}

/** Opens the app and gets past the password screen, whichever one this data folder shows. */
export async function enterApp(page: Page): Promise<void> {
  await page.goto("/");
  const create = page.getByRole("heading", { name: "Create your password" });
  const login = page.getByRole("heading", { name: "Log in" });
  // Phase 5a: the app shell is the sidebar (the step bar is gone; its steps are the sidebar's assessment pages).
  const steps = page.getByTestId("sidebar").first();
  await expect(create.or(login).or(steps)).toBeVisible();
  if (await create.isVisible()) {
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Repeat password").fill(password);
    await page.getByRole("button", { name: "Create password" }).click();
  } else if (await login.isVisible()) {
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
  }
  await expect(steps).toBeVisible();
}

// Phase 5a: the six steps of the old step bar are now pages of the open assessment, in the sidebar.
const STEP_PAGES: Record<string, string> = {
  "1. Import": "Import",
  "2. Verify": "Verify",
  "3. Tests": "Tests",
  "4. Evidence Lab": "Evidence",
  "5. Fixes": "Fixes",
  "6. Migration": "Migration",
};

/** The sidebar's assessment pages, in order, once a file is in (Migration's three views open with it). */
export const SIDEBAR_PAGES = ["Overview", "Inventory", "Import", "Verify", "Tests", "Evidence", "Fixes", "Migration", "Systems", "Roadmap", "Dependencies"];

/** The page an old step lands on, as the sidebar marks it current ("4. Evidence Lab" -> "Evidence"; "6. Migration"
 * opens Migration's first view, "Systems"). */
export function stepName(step: string): string {
  const name = STEP_PAGES[step] ?? step;
  return name === "Migration" ? "Systems" : name;
}

/** The sidebar's assessment pages (what the step bar was). */
export function stepNav(page: Page): Locator {
  return page.getByRole("navigation", { name: "Assessment" });
}

/** The sidebar link for one of the old steps ("4. Evidence Lab") or a page name ("Evidence", "Roadmap"). */
export function stepLink(page: Page, step: string): Locator {
  return stepNav(page).getByRole("link", { name: STEP_PAGES[step] ?? step, exact: true });
}

/** Phase 5a: every walk works in its own project. New project (from Projects) opens its first assessment on Import. */
export async function openFreshAssessment(page: Page, name: string): Promise<void> {
  await page.goto("/#/projects");
  await expect(page.getByTestId("projects-page")).toBeVisible();
  await page.getByRole("button", { name: "New project", exact: true }).first().click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(stepLink(page, "Import")).toHaveAttribute("aria-current", "page");
}

/** Use demo file, tick "I own this system", Verify claims, Continue to tests. Main-screen buttons only. */
export async function importVerifyAndOpenTests(page: Page): Promise<void> {
  await stepLink(page, "1. Import").click();
  // Wait for the import itself to be answered: until then the screen may still show an earlier import
  // (with its box already ticked), and the new file's box must be the one that gets ticked.
  const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST");
  await page.getByRole("button", { name: "Use demo file" }).click();
  expect((await imported).status()).toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  const tick = page.getByTestId("address-confirm");
  await expect(tick).toHaveCount(1);
  // A new import always starts with the box unticked.
  await expect(tick).not.toBeChecked();
  await tick.click();
  await expect(tick).toBeChecked();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  const badges = page.getByTestId("result-row").getByTestId("result-badge");
  await expect(badges).toHaveText(["False", "True", "True"]);
  await page.getByRole("button", { name: "Continue to tests" }).click();
  await expect(page.getByRole("heading", { name: "Tests", level: 1 })).toBeVisible();
}

/** Phase 3a-fixes: a picture of a demo screen this work changed, taken where the earlier runs already show it. */
export async function shotFixes(page: Page, name: string): Promise<void> {
  const fs = await import("node:fs");
  const folder = screenshotFolder("phase3a-fixes");
  fs.mkdirSync(folder, { recursive: true });
  await page.screenshot({ path: path.join(folder, name), fullPage: true, animations: "disabled" });
}

/** Phase 5a: one picture of the page in the dark look and one in the light look, in docs/screenshots/phase5a/. */
export async function shotBothThemes(page: Page, name: string, fullPage = true): Promise<void> {
  const fs = await import("node:fs");
  const folder = screenshotFolder("phase5a");
  fs.mkdirSync(folder, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(folder, `${name}-${theme}.png`), fullPage, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

// Phase 5a: Evidence is a table of results; a row opens the right-side detail panel, which holds what the opened row
// held before (the "lab-row" wrapper with "result-detail", the fix line, Mark reviewed, Dig deeper...).

/** The table row of one result, by its test title (inside a group's section when `within` is given). */
export function evidenceRow(page: Page, title: string, within?: Locator): Locator {
  return (within ?? page).getByTestId("evidence-row").filter({ has: page.getByTestId("lab-row-header").getByText(title, { exact: true }) });
}

/** What the detail panel shows for the open result (the old opened row). */
export function resultPanel(page: Page): Locator {
  return page.getByTestId("detail-panel").getByTestId("lab-row");
}

/** Opens one result in the detail panel (or keeps it open) and returns what the panel shows for it. */
export async function openResult(page: Page, title: string, within?: Locator): Promise<Locator> {
  const heading = page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: title, exact: true });
  if ((await heading.count()) === 0) await evidenceRow(page, title, within).click();
  await expect(heading).toBeVisible();
  return resultPanel(page);
}

/** Closes the detail panel. */
export async function closeResult(page: Page): Promise<void> {
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  await expect(page.getByTestId("detail-panel")).toHaveCount(0);
}

/** Clicking a result's row used to open and shut it in place; now it opens the detail panel, or shuts it if that result
 * is the one already open. Same behaviour, so the walks keep their steps. */
export async function toggleResult(page: Page, title: string, within?: Locator): Promise<void> {
  const heading = page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: title, exact: true });
  if ((await heading.count()) > 0) await closeResult(page);
  else await openResult(page, title, within);
}
