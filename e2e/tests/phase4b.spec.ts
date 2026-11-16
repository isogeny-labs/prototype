// Phase 4b end to end: "make it real". On the migration demo file (five local test servers on 8451-8455):
// two tracks per server, the change box (try on a test copy, approvals, Apply, Roll back, Download change) and
// the roadmap by track. Then on the main Acme Pay demo: the server TLS fix with its change box.
// Demo mode: no Docker and no internet, every server is on this computer. Main-screen buttons only.
// Screenshots go to docs/screenshots/phase4b/.
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { enterApp, importVerifyAndOpenTests, screenshotFolder, stepLink, stepNav, openFreshAssessment, stepName, evidenceRow } from "./shared";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = screenshotFolder("phase4b");
fs.mkdirSync(SHOTS, { recursive: true });
const FILE = path.resolve(here, "../../demo/migration-demo.csv");

let context: BrowserContext;
let page: Page;

async function shot(name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

// ---- small helpers

function card(name: string): Locator {
  return page.getByTestId("system-card").filter({ hasText: name });
}

function band(title: string): Locator {
  return page.getByTestId("roadmap-band").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

/** One track of the open system: "kex", "auth" or "signatures". */
function track(key: "kex" | "auth" | "signatures"): Locator {
  return page.locator(`[data-testid="migration-track"][data-track="${key}"]`);
}

async function openSystem(name: string): Promise<void> {
  await page.getByRole("button", { name: /^Systems/ }).click();
  await card(name).click();
  await expect(page.getByTestId("migration-system").getByRole("heading", { name, level: 2 })).toBeVisible();
}

function box(): Locator {
  return page.getByTestId("change-box");
}

/** The badge words of the change box (the small round symbol in front is not text we compare). */
function badgeIs(words: string): Promise<void> {
  return expect(box().getByTestId("change-badge")).toContainText(words, { timeout: 90_000 });
}

function tryRow(label: string): Locator {
  return box().getByTestId("change-try").getByRole("row").filter({ has: page.getByRole("rowheader", { name: label, exact: true }) });
}

async function goTo(step: string): Promise<void> {
  await stepLink(page, step).click();
  await expect(stepNav(page).locator('[aria-current="page"]')).toHaveText(stepName(step));
}

async function pickFix(title: string): Promise<void> {
  await page.getByRole("navigation", { name: /^Open findings with a fix/ }).getByRole("button").filter({ hasText: title }).click();
  await expect(page.getByTestId("fix-summary").getByRole("heading", { name: title, level: 2 })).toBeVisible();
}

function cardStatuses(): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ acceptDownloads: true });
  page = await context.newPage();
  await enterApp(page);
  await openFreshAssessment(page, "Make it real walk");
});

test.afterAll(async () => {
  await context.close();
});

// ---------------------------------------------------------------- the migration demo file

test("Two tracks: 8451 shows Key exchange and Authentication, each with its Next step and its Why", async () => {
  await stepLink(page, "1. Import").click();
  const uploaded = page.waitForResponse((r) => r.url().includes("/api/import/file") && r.request().method() === "POST");
  await page.getByLabel("Choose a file to import").setInputFiles(FILE);
  expect((await uploaded).status()).toBe(200);
  const ticks = page.getByTestId("address-confirm");
  await expect(ticks).toHaveCount(5);
  for (let i = 0; i < 5; i += 1) await ticks.nth(i).click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();

  await stepLink(page, "6. Migration").click();
  await expect(page.getByRole("heading", { name: "Migration plan", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Measure status" }).click();
  await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 120_000 });

  await openSystem("localhost:8451");
  await expect(track("kex").getByTestId("migration-status")).toContainText("Hybrid (interim)");
  await expect(track("auth").getByTestId("migration-status")).toContainText("Classical");
  for (const key of ["kex", "auth"] as const) {
    await expect(track(key).getByTestId("track-next")).toContainText("Next:");
    await expect(track(key).getByTestId("track-why")).toContainText("Why:");
  }
  // The new measurements on the key exchange track.
  for (const fact of ["Chosen by default?", "If the client lists classical first", "Classical-only clients", "Hybrid-only clients"]) {
    await expect(track("kex")).toContainText(fact);
  }
  await expect(page.getByText(/already there/i)).toHaveCount(0);
  await shot("01-two-tracks.png");
});

test("8452: Ready to try, Apply is off with its reason; the try shows before and after, and the nginx column needs isolated mode", async () => {
  await openSystem("localhost:8452");
  await expect(track("kex").getByTestId("migration-status")).toContainText("Classical");
  await badgeIs("Ready to try");
  await expect(box().getByRole("button", { name: "Apply to localhost:8452" })).toBeDisabled();
  await expect(box().getByTestId("change-reason")).toContainText("Apply unlocks after a try on a test copy has passed.");
  await expect(box().getByRole("button", { name: "Ask for approval" })).toBeDisabled();
  await expect(box().getByRole("button", { name: "Try on a test copy" })).toBeEnabled();

  await box().getByRole("button", { name: "Try on a test copy" }).click();
  await expect(box().getByTestId("change-verdict")).toBeVisible({ timeout: 120_000 });
  await expect(box().getByTestId("change-verdict")).toContainText("Try passed.");
  await badgeIs("Try passed");
  // The table: now, on the test copy, and real nginx (not tried in demo mode).
  const table = box().getByTestId("change-try").getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveCount(4);
  const kex = tryRow("Key exchange");
  await expect(kex.getByRole("cell").nth(0)).toContainText("Classical");
  await expect(kex.getByRole("cell").nth(0)).toContainText("measured");
  await expect(kex.getByRole("cell").nth(1)).toContainText("Hybrid (interim)");
  await expect(kex.getByRole("cell").nth(1)).toContainText("measured on the copy");
  await expect(kex.getByRole("cell").nth(2)).toContainText("isolated mode");
  await expect(box().getByRole("button", { name: "Try again on a test copy" })).toBeEnabled();
  await box().getByTestId("change-try").scrollIntoViewIfNeeded();
  await shot("02-try-before-after.png");
});

test("Approvals: Apply stays off until You and Demo reviewer A have both approved; Apply is one click and the app measures again", async () => {
  await box().getByRole("checkbox", { name: /Demo reviewer A/ }).check();
  await expect(box().getByRole("checkbox", { name: "You" })).toBeChecked();
  await expect(box().getByRole("checkbox", { name: /Demo reviewer B/ })).not.toBeChecked();
  await box().getByRole("button", { name: "Ask for approval" }).click();
  await expect(box().getByTestId("change-approval-row")).toHaveCount(2);

  await box().getByRole("button", { name: "Approve for You" }).click();
  await expect(box().getByRole("button", { name: "Apply to localhost:8452" })).toBeDisabled();
  await expect(box().getByTestId("change-reason")).toContainText("Demo reviewer A");

  await box().getByRole("button", { name: "Approve as Demo reviewer A" }).click();
  await expect(box().getByRole("button", { name: "Apply to localhost:8452" })).toBeEnabled();
  await badgeIs("Ready to apply");

  // One click, no confirm dialog.
  await box().getByRole("button", { name: "Apply to localhost:8452" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(box().getByTestId("change-applied-badge")).toContainText("Applied · matches the try", { timeout: 90_000 });
  await expect(track("kex").getByTestId("migration-status")).toContainText("Hybrid (interim)", { timeout: 30_000 });
  await box().getByTestId("change-applied").scrollIntoViewIfNeeded();
  await shot("03-applied.png");
});

test("Roadmap: 8452's key exchange moved to Done for now", async () => {
  await page.getByRole("button", { name: "Roadmap", exact: true }).click();
  await expect(band("Done for now").getByTestId("roadmap-row").filter({ hasText: "localhost:8452" })).toContainText("Key exchange");
  await expect(band("Phase 1").getByTestId("roadmap-row").filter({ hasText: "localhost:8452" })).toHaveCount(0);
  await shot("04-roadmap-tracks.png");
});

test("Fixes: the change reads In place (measured); Roll back (from Migration) puts it back, measures again, and Apply asks for a new try", async () => {
  await goTo("5. Fixes");
  await pickFix("Turn on hybrid key exchange on localhost:8452");
  await expect(page.getByTestId("fix-summary").getByTestId("fix-status")).toHaveText("In place (measured)", { timeout: 60_000 });
  await expect(box().getByTestId("change-badge")).toContainText("In place (measured)");
  await shot("05-fixes-change.png");

  // Roll back from the same change box in the Migration step.
  await goTo("6. Migration");
  await openSystem("localhost:8452");
  await box().getByRole("button", { name: "Roll back" }).click();
  await expect(box().getByTestId("change-applied-badge")).toContainText("Rolled back · measured as before", { timeout: 90_000 });
  await badgeIs("Rolled back");
  await expect(track("kex").getByTestId("migration-status")).toContainText("Classical");
  await expect(track("kex").getByTestId("migration-status")).not.toContainText("Hybrid");
  await expect(box().getByRole("button", { name: "Apply to localhost:8452" })).toBeDisabled();
  await expect(box().getByTestId("change-reason")).toContainText("Try again on a test copy first");
});

test("Download change on 8452: a text file with the nginx line and no key", async () => {
  const downloading = page.waitForEvent("download");
  await box().getByRole("button", { name: "Download change" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(/\.txt$/);
  const file = await download.path();
  const text = fs.readFileSync(file, "utf8");
  expect(text).toContain("ssl_ecdh_curve");
  expect(text).not.toContain("PRIVATE KEY");
});

test("8455 is post-quantum only: both tracks say to keep it there", async () => {
  await openSystem("localhost:8455");
  await expect(track("kex").getByTestId("migration-status")).toContainText("Post-quantum only");
  await expect(track("auth").getByTestId("migration-status")).toContainText("Post-quantum");
  for (const key of ["kex", "auth"] as const) {
    await expect(track(key).getByTestId("track-next")).toContainText("keep it there");
  }
  await expect(card("localhost:8455")).toContainText("At the target · keep measuring");
});

// ---------------------------------------------------------------- the Acme Pay demo: the server TLS fix

test("Acme Pay: Run all, then the TLS fix in Fixes has its change box (Ready to try)", async () => {
  await importVerifyAndOpenTests(page);
  await page.getByRole("button", { name: "Run all" }).click();
  await expect.poll(cardStatuses, { timeout: 200_000 }).toEqual(Array(5).fill("done"));
  await goTo("5. Fixes");
  await pickFix("Server accepts TLS 1.2");
  await expect(page.getByTestId("fix-summary").getByTestId("fix-status")).toHaveText("Ready to try");
  await expect(box()).toHaveAttribute("data-change", "tls:server:localhost:8443");
  await expect(box().getByTestId("change-badge")).toContainText("Ready to try");
  await expect(page.getByTestId("fix-proof")).toHaveText(
    "In the change box below: a try on a test copy of the demo server comes first, then the approvals, then Apply.");
});

test("Acme Pay: the try shows Failed then Passed; approve with You only; Apply; In place (measured)", async () => {
  await box().getByRole("button", { name: "Try on a test copy" }).click();
  await expect(box().getByTestId("change-verdict")).toContainText("Try passed.", { timeout: 120_000 });
  const check = tryRow("Server protocol check");
  await expect(check.getByRole("cell").nth(0)).toContainText("Failed");
  await expect(check.getByRole("cell").nth(0)).toContainText("measured");
  await expect(check.getByRole("cell").nth(1)).toContainText("Passed");
  await expect(check.getByRole("cell").nth(1)).toContainText("measured on the copy");

  // You only: the box ticks You by default.
  await expect(box().getByRole("checkbox", { name: "You" })).toBeChecked();
  await expect(box().getByRole("checkbox", { name: /Demo reviewer A/ })).not.toBeChecked();
  await box().getByRole("button", { name: "Ask for approval" }).click();
  await box().getByRole("button", { name: "Approve for You" }).click();
  await expect(box().getByRole("button", { name: "Apply to localhost:8443" })).toBeEnabled();
  await box().getByRole("button", { name: "Apply to localhost:8443" }).click();
  await badgeIs("In place (measured)");
  await shot("06-acme-tls-change.png");
});

/** Verify claims again from the Import step (the claims are already there and the address is confirmed). */
async function verifyAgain(): Promise<Locator> {
  await goTo("1. Import");
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  return page.getByTestId("result-row").filter({ hasText: "localhost:8443 accepts TLS 1.3 only" }).getByTestId("result-badge");
}

test("Acme Pay: after Apply Evidence Lab's Old TLS versions is Passed and Verify reads True; Roll back puts it back", async () => {
  await goTo("4. Evidence Lab");
  const old = evidenceRow(page, "Old TLS versions");
  await expect(old.getByTestId("result-badge").locator("span:last-child").first()).toHaveText("Passed", { timeout: 60_000 });

  await expect(await verifyAgain()).toHaveText("True");

  // Roll back, so the demo server is left as it started.
  await goTo("5. Fixes");
  await pickFix("Server accepts TLS 1.2");
  await box().getByRole("button", { name: "Roll back" }).click();
  await expect(box().getByTestId("change-applied-badge")).toContainText("Rolled back", { timeout: 90_000 });
  await expect(await verifyAgain()).toHaveText("False");
});
