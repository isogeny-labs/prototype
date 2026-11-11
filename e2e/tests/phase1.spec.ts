// Phase 1 end to end, on the demo, with no internet: create a password, log in,
// import the demo file, verify the claims, look at the evidence, upload a broken file.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.resolve(here, "../../docs/screenshots/phase1");
const DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed.";
const NOT_CONFIRMED = "You haven't confirmed you're allowed to test this address";

// A throwaway password for the throwaway data folder. It is never written anywhere.
const password = crypto.randomBytes(18).toString("base64url");

let context: BrowserContext;
let page: Page;

async function shot(target: Page, name: string, fullPage = true): Promise<void> {
  await target.screenshot({ path: path.join(SHOTS, name), fullPage, animations: "disabled" });
}

function row(target: Page, claimText: string | RegExp) {
  return target.getByTestId("result-row").filter({ hasText: claimText });
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  context = await browser.newContext();
  page = await context.newPage();
});

test.afterAll(async () => {
  await context.close();
});

test("first run: create your password, then you are in the app", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Create your password" })).toBeVisible();
  await shot(page, "01-create-password.png");

  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Repeat password").fill(password);
  await page.getByRole("button", { name: "Create password" }).click();

  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(page.getByText("Demo mode: running our own demo software, not isolated.")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Steps" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use demo file" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify claims" })).toHaveCount(0);
  await shot(page, "03-import-empty.png");
});

test("a later visit shows Log in; a wrong password is refused, the right one works", async ({ browser }) => {
  const later = await browser.newContext();
  const visit = await later.newPage();
  try {
    await visit.goto("/");
    await expect(visit.getByRole("heading", { name: "Log in" })).toBeVisible();
    await expect(visit.getByRole("heading", { name: "Create your password" })).toHaveCount(0);
    await shot(visit, "02-login.png");

    // Nothing in the app answers without logging in.
    expect((await visit.request.get("/api/import/current")).status()).toBe(401);

    await visit.getByLabel("Password", { exact: true }).fill(`${password}-wrong`);
    await visit.getByRole("button", { name: "Log in" }).click();
    await expect(visit.getByRole("alert")).toContainText("That password isn't right");

    await visit.getByLabel("Password", { exact: true }).fill(password);
    await visit.getByRole("button", { name: "Log in" }).click();
    await expect(visit.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  } finally {
    await later.close();
  }
});

test("Use demo file shows the three claims, labelled Demo data", async () => {
  await page.getByRole("button", { name: "Use demo file" }).click();

  const claims = page.getByTestId("claim-row");
  await expect(claims).toHaveCount(3);
  await expect(claims.nth(0)).toContainText("localhost:8443 accepts TLS 1.3 only");
  await expect(claims.nth(1)).toContainText("localhost:8443 certificate is ECDSA P-256");
  await expect(claims.nth(2)).toContainText("signing component is acme-sign 1.4.2 implementing ECDSA P-256");
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(claims.nth(0).getByText("from the file", { exact: true })).toBeVisible();

  // The demo server must really be up, or the results below would mean nothing.
  await expect(page.getByText("isn't running")).toHaveCount(0);

  const tick = page.getByTestId("address-confirm");
  await expect(tick).toHaveCount(1);
  await expect(tick).not.toBeChecked();
  await expect(page.getByText("I own this system or am allowed to test it")).toBeVisible();
  await expect(page.getByRole("button", { name: "Verify claims" })).toBeDisabled();
  await shot(page, "04-import-demo-claims.png");
});

test("without the tick, the server is not contacted: server claims are Couldn't check", async () => {
  // The Verify button is switched off until the box is ticked, so ask the app directly.
  const current = await (await page.request.get("/api/import/current")).json();
  const response = await page.request.post(`/api/import/${current.id}/verify`);
  expect(response.status()).toBe(200);
  const run = await response.json();
  const byKind = Object.fromEntries(run.results.map((r: any) => [r.claim.kind, r]));
  for (const kind of ["protocol_versions", "certificate"]) {
    expect(byKind[kind].result).toBe("Couldn't check");
    expect(byKind[kind].reason).toBe(NOT_CONFIRMED);
    // The only evidence is the app's own note that it did not connect.
    expect(JSON.stringify(byKind[kind].evidence)).toContain("no connection was attempted");
    expect(JSON.stringify(byKind[kind].evidence)).not.toContain("TLSv1");
  }
  expect(byKind["signature_algorithm"].result).toBe("True");

  // The screen shows the same thing after a refresh.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  const tls = row(page, "accepts TLS 1.3 only");
  await expect(tls.getByTestId("result-badge")).toHaveText("Couldn't check");
  await expect(tls).toContainText(NOT_CONFIRMED);
  await expect(row(page, "certificate is ECDSA P-256").getByTestId("result-badge")).toHaveText("Couldn't check");
});

test("tick the box and Verify claims: False, True, True, with evidence", async () => {
  await page.getByRole("button", { name: "1. Import" }).click();
  // The tick is saved by the app before the box shows as ticked, so click and then wait.
  await page.getByTestId("address-confirm").click();
  await expect(page.getByTestId("address-confirm")).toBeChecked();
  await page.getByRole("button", { name: "Verify claims" }).click();

  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await expect(page.getByTestId("result-row")).toHaveCount(3);

  const tls = row(page, "localhost:8443 accepts TLS 1.3 only");
  await expect(tls.getByTestId("result-badge")).toHaveText("False");
  await expect(tls).toContainText(/Accepts TLS 1\.3 and TLS 1\.2/);

  const cert = row(page, "localhost:8443 certificate is ECDSA P-256");
  await expect(cert.getByTestId("result-badge")).toHaveText("True");
  await expect(cert).toContainText("P-256");

  const sign = row(page, "signing component is acme-sign 1.4.2 implementing ECDSA P-256");
  await expect(sign.getByTestId("result-badge")).toHaveText("True");

  await expect(page.getByText(DISCLAIMER)).toBeVisible();
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(page.getByText("Demo mode: running our own demo software, not isolated.")).toBeVisible();
  await expect(tls.getByText("from the file", { exact: true })).toBeVisible();
  await expect(tls.getByText("measured", { exact: true })).toBeVisible();

  // The app never calls anything secure and never gives a score.
  const text = (await page.locator("body").innerText()).replace(DISCLAIMER, "");
  expect(text).not.toMatch(/\bsecure\b|security score|time[- ]to[- ]hack/i);
  await shot(page, "05-verify-results.png");
});

test("evidence opens and shows raw output, with no private key in it", async () => {
  const tls = row(page, "localhost:8443 accepts TLS 1.3 only");
  const toggle = tls.getByRole("button", { name: "Evidence" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(tls.getByText("Raw output").first()).toBeVisible();
  const raw = tls.locator("pre").first();
  await expect(raw).toBeVisible();
  expect(((await raw.innerText()) ?? "").trim().length).toBeGreaterThan(20);
  await expect(tls.locator("pre").filter({ hasText: "TLSv1.2" }).first()).toBeVisible();
  await expect(tls.getByText("Command").first()).toBeVisible();
  await expect(tls.getByText(/Tool:/).first()).toBeVisible();
  await shot(page, "06-verify-evidence-open.png");

  for (const claim of ["certificate is ECDSA P-256", "signing component is acme-sign"]) {
    await row(page, claim).getByRole("button", { name: "Evidence" }).click();
    await expect(row(page, claim).locator("pre").first()).toBeVisible();
  }

  // Check everything on screen and everything the app stored for this run.
  const onScreen = await page.locator("body").innerText();
  const current = await (await page.request.get("/api/import/current")).json();
  const stored = JSON.stringify(await (await page.request.get(`/api/import/${current.id}/verify`)).json());
  const keyFile = path.join(process.env.E2E_DATA_DIR ?? "", "demo-tls-test-key.pem");
  const keyLines = fs
    .readFileSync(keyFile, "utf8")
    .split("\n")
    .filter((line) => line.length >= 20 && !line.startsWith("-----"));
  expect(keyLines.length).toBeGreaterThan(0);
  // All comparisons are true/false only, so a key could never end up in a test report.
  for (const haystack of [onScreen, stored]) {
    expect(/BEGIN [A-Z ]*PRIVATE KEY/.test(haystack)).toBe(false);
    expect(keyLines.some((line) => haystack.includes(line))).toBe(false);
  }
  // The demo component's own test key is replaced by a placeholder wherever its commands are shown.
  const shownKeys = [...stored.matchAll(/private_key\\+":\s*\\+"([^"\\]*)/g)].map((m) => m[1]);
  expect(shownKeys.length).toBeGreaterThan(0);
  expect(shownKeys.every((value) => value === "[test private key withheld]")).toBe(true);
});

test("the assistant panel has its title and can be collapsed", async () => {
  const panel = page.getByTestId("copilot-panel");
  const title = panel.getByRole("heading", { name: "Prototype assistant (no AI model connected)" });
  await expect(title).toBeVisible();
  await expect(panel.getByRole("textbox")).toHaveCount(0);

  await page.getByTestId("copilot-toggle").click();
  await expect(page.getByTestId("copilot-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(panel.getByText("The assistant isn't built yet")).toHaveCount(0);
  await shot(page, "07-copilot-collapsed.png", false);

  await page.getByTestId("copilot-toggle").click();
  await expect(panel.getByText("The assistant isn't built yet")).toBeVisible();
});

test("Continue to tests shows the phase 2 placeholder", async () => {
  await page.getByRole("button", { name: "Continue to tests" }).click();
  await expect(page.getByRole("heading", { name: "Tests", level: 1 })).toBeVisible();
  await expect(page.getByText("The Tests step arrives in phase 2.")).toBeVisible();
  await expect(page.getByTestId("result-badge")).toHaveCount(0);
  // The step bar highlights where you are: Tests, and only Tests.
  const steps = page.getByRole("navigation", { name: "Steps" });
  await expect(steps.getByRole("button", { name: /3\. Tests/ })).toHaveAttribute("aria-current", "step");
  await expect(steps.locator('[aria-current="step"]')).toHaveCount(1);
  await shot(page, "09-tests-placeholder.png");
});

test("a broken CSV upload gives an error that names the line, and the previous file's claims are gone", async () => {
  await page.getByRole("button", { name: "1. Import" }).click();
  // The demo import from earlier is on screen before the broken upload.
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  const broken = [
    "location,type,claim,value",
    "localhost:8443,tls,protocol_versions,TLS1.3",
    "localhost:8443,tls,protocol_versions,TLS9.9",
    "",
  ].join("\n");
  await page
    .getByLabel("Choose a file to import")
    .setInputFiles({ name: "broken-claims.csv", mimeType: "text/csv", buffer: Buffer.from(broken) });

  const error = page.getByRole("alert").filter({ hasText: "We couldn't read that file" });
  await expect(error).toBeVisible();
  await expect(error).toContainText("Line 3");
  await expect(error).toContainText("TLS9.9");

  // Only the error shows: the previous file's claims, tick box and Verify claims button are gone.
  await expect(page.getByTestId("claim-row")).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByTestId("address-confirm")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Verify claims" })).toHaveCount(0);
  await shot(page, "08-upload-error.png");

  // The app itself holds no import any more, so a refresh does not bring the old claims back.
  expect((await page.request.get("/api/import/current")).status()).toBe(404);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use demo file" })).toBeVisible();
  await expect(page.getByTestId("claim-row")).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Verify claims" })).toHaveCount(0);
});

test("uploading demo/claims-template.csv imports the three claims and shows the Demo data label", async () => {
  // The template points at the app's own demo server and demo component, so it is demo data
  // even when it arrives as an upload rather than through Use demo file.
  // Wait for the upload itself to be answered.
  const uploaded = page.waitForResponse((r) => r.url().includes("/api/import/file") && r.request().method() === "POST");
  await page
    .getByLabel("Choose a file to import")
    .setInputFiles(path.resolve(here, "../../demo/claims-template.csv"));
  expect((await uploaded).status()).toBe(200);
  await expect(page.getByRole("alert").filter({ hasText: "We couldn't read that file" })).toHaveCount(0);
  await expect(page.getByText("claims-template.csv · CSV template")).toBeVisible();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  const current = await (await page.request.get("/api/import/current")).json();
  expect(current.filename).toBe("claims-template.csv");
  expect(current.is_demo).toBe(true);
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible();
});

test("items this version doesn't check are listed in a note, not skipped silently", async () => {
  const uploaded = page.waitForResponse((r) => r.url().includes("/api/import/file") && r.request().method() === "POST");
  await page
    .getByLabel("Choose a file to import")
    .setInputFiles(path.resolve(here, "../fixtures/cbom-with-skipped-items.json"));
  expect((await uploaded).status()).toBe(200);

  const claims = page.getByTestId("claim-row");
  await expect(claims).toHaveCount(1);
  await expect(claims.first()).toContainText("localhost:8443");

  const note = page.getByTestId("skipped-note");
  await expect(note).toBeVisible();
  const summary = note.locator("summary");
  await expect(summary).toHaveText("2 items skipped: not checked in this version");
  // Closed to start with; opening it lists both items.
  await expect(note.getByTestId("skipped-item").first()).toBeHidden();
  await summary.click();
  const items = note.getByTestId("skipped-item");
  await expect(items).toHaveCount(2);
  await expect(items.filter({ hasText: "SHA-256" })).toBeVisible();
  await expect(items.filter({ hasText: "SHA-256" })).toContainText("Hash algorithm");
  await expect(items.filter({ hasText: "AES-256-GCM" })).toBeVisible();
  await expect(items.filter({ hasText: "AES-256-GCM" })).toContainText("not checked in this version");
  await shot(page, "10-skipped-items.png");
});
