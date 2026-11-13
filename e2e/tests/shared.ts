// Things the test files share: the throwaway password, the one fixed line every result screen carries,
// and "get me into the app" (create the password on a brand-new data folder, or log in).
import { expect, type Page } from "@playwright/test";
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

export function screenshotFolder(phase: "phase1" | "phase2" | "phase3a"): string {
  return path.join(REPO, "docs/screenshots", phase);
}

/** Opens the app and gets past the password screen, whichever one this data folder shows. */
export async function enterApp(page: Page): Promise<void> {
  await page.goto("/");
  const create = page.getByRole("heading", { name: "Create your password" });
  const login = page.getByRole("heading", { name: "Log in" });
  const steps = page.getByRole("navigation", { name: "Steps" });
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

/** Use demo file, tick "I own this system", Verify claims, Continue to tests. Main-screen buttons only. */
export async function importVerifyAndOpenTests(page: Page): Promise<void> {
  await page.getByRole("button", { name: "1. Import" }).click();
  // Wait for the import itself to be answered: until then the screen may still show an earlier import
  // (with its box already ticked), and the new file's box must be the one that gets ticked.
  const imported = page.waitForResponse((r) => r.url().endsWith("/api/import/demo") && r.request().method() === "POST");
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
