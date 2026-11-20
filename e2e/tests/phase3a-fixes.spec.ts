// Phase 3a-fixes end to end: a file with several targets (demo/multi-target-demo.csv: the Acme server, three
// local test servers on 8444-8446, acme-sign 1.4.2 and acme-sign 9.9). Every target is tested, the screens
// group by target and say what wasn't tested and why, every result starts with one plain sentence, and the
// certificate check of the server that accepts TLS 1.0 and 1.1 shows an "Also noticed" note. No internet:
// every server is on this computer. Main-screen buttons only. Screenshots go to docs/screenshots/phase3a-fixes/.
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DISCLAIMER, enterApp, REPO, stepLink, openFreshAssessment, openGroupTab, resultPanel, toggleResult } from "./shared";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(REPO, "docs/screenshots/phase3a-fixes");
fs.mkdirSync(SHOTS, { recursive: true });
const FILE = path.resolve(here, "../../demo/multi-target-demo.csv");
const NOTE = "This server also accepts TLS 1.0 and TLS 1.1, both retired in 2021. The file didn't ask about this, so it doesn't change the result.";
const SERVERS = ["localhost:8443", "localhost:8444", "localhost:8445", "localhost:8446"];
// acme-sign 9.9 can't run (it is not one of ours), so since phase 4a it has no group: only its line under "Not tested, and why".
const GROUPS = [...SERVERS.map((s) => `Server: ${s}`), "Signing program: acme-sign 1.4.2"];

let context: BrowserContext;
let page: Page;

async function shot(name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

function group(testId: "test-group" | "lab-group", heading: string): Locator {
  return page.getByTestId(testId).filter({ has: page.getByRole("heading", { name: heading, exact: true }) });
}

function verifyRow(claim: string): Locator {
  return page.getByTestId("result-row").filter({ hasText: claim });
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext();
  page = await context.newPage();
  await enterApp(page);
  await openFreshAssessment(page, "Multi-target walk");
});

test.afterAll(async () => {
  await context.close();
});

test("upload the multi-target demo file: its three test servers start, and the seven claims are listed", async () => {
  await stepLink(page, "1. Import").click();
  const uploaded = page.waitForResponse((r) => r.url().includes("/api/import/file") && r.request().method() === "POST");
  await page.getByLabel("Choose a file to import").setInputFiles(FILE);
  expect((await uploaded).status()).toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(7);
  await expect(page.getByTestId("import-notice")).toHaveText([
    "Demo data: started the three demo test servers for this file on this computer (ports 8444, 8445, 8446).",
  ]);
  const ticks = page.getByTestId("address-confirm");
  await expect(ticks).toHaveCount(4);
  for (let i = 0; i < 4; i += 1) await ticks.nth(i).click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
});

test("Verify: one plain sentence on top of every row, the Also noticed note, the technical text folded", async () => {
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(
    ["False", "True", "True", "True", "False", "True", "Couldn't check"]);
  await expect(page.getByTestId("verify-summary")).toHaveCount(7);
  await expect(verifyRow("localhost:8443 accepts TLS 1.3 only").getByTestId("verify-summary"))
    .toHaveText("The server accepts TLS 1.2, so ‘TLS 1.3 only’ is not true.");
  await expect(verifyRow("localhost:8443 certificate").getByTestId("verify-summary"))
    .toHaveText("The server's ID card (its certificate) uses ECDSA P-256, which matches the claim.");
  await expect(verifyRow("localhost:8446 certificate").getByTestId("verify-summary"))
    .toHaveText("The server's ID card (its certificate) uses RSA with a 1024-bit key, not RSA 2048 as the file claims.");
  await expect(verifyRow("acme-sign 9.9").getByTestId("verify-summary"))
    .toHaveText("We couldn't run acme-sign 9.9: only our own demo components can run in this version, so there is no answer either way.");
  // The note shows on the one row whose handshakes saw TLS 1.0 and 1.1, and that row is still True.
  await expect(page.getByTestId("also-noticed")).toHaveCount(1);
  const noticed = verifyRow("localhost:8445 certificate");
  await expect(noticed.getByTestId("also-noticed")).toContainText(NOTE);
  await expect(noticed.getByTestId("result-badge")).toHaveText("True");
  // The technical text is folded until asked for.
  // (phase 5a: "Details and evidence" opens them in the right-side detail panel)
  const tls = verifyRow("localhost:8443 accepts TLS 1.3 only");
  await expect(page.getByText("Accepts TLS 1.3 and TLS 1.2", { exact: false })).toHaveCount(0);
  await tls.getByTestId("verify-details-toggle").click();
  await expect(page.getByTestId("detail-panel").getByText("Accepts TLS 1.3 and TLS 1.2", { exact: false })).toBeVisible();
  await expect(page.getByText(/\bsecure\b/i).filter({ hasNotText: DISCLAIMER })).toHaveCount(0);
  await shot("01-verify-multi-target.png");
});

test("Tests: grouped by target, with what isn't tested and why; eight tests in all", async () => {
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  const groups = page.getByTestId("test-group");
  await expect(groups).toHaveCount(5);
  for (const heading of GROUPS) await expect(group("test-group", heading)).toBeVisible();
  await expect(page.getByTestId("test-card")).toHaveCount(8);
  await expect(group("test-group", "Server: localhost:8443").getByTestId("test-card")).toHaveCount(2);
  // A program that can't run gets no test cards: only its line in the box below.
  await expect(page.getByRole("heading", { name: "Signing program: acme-sign 9.9", exact: true })).toHaveCount(0);
  const box = page.getByTestId("not-tested");
  await expect(box).toContainText("Not tested, and why");
  await expect(box).toContainText("localhost:8444: no Certificate strength test. The file makes no claim about this server's certificate.");
  await expect(box).toContainText("localhost:8445: no Old TLS versions test. The file makes no claim about which TLS versions this server accepts.");
  await expect(box).toContainText("acme-sign 9.9: its tests can't run. Only our own demo components can run in this version.");
  await shot("02-tests-multi-target.png");
});

test("Run all tests every target, in parallel, within the job limit", async () => {
  await page.getByRole("button", { name: "Run all" }).click();
  let most = 0;
  const deadline = Date.now() + 240_000;
  for (;;) {
    const statuses = await page.getByTestId("test-card").evaluateAll((cards) => cards.map((c) => c.getAttribute("data-status")));
    most = Math.max(most, statuses.filter((s) => s === "running").length);
    if (statuses.length === 8 && statuses.every((s) => s === "done")) break;
    expect(Date.now(), `still running: ${statuses.join(", ")}`).toBeLessThan(deadline);
    await page.waitForTimeout(200);
  }
  expect(most).toBeGreaterThanOrEqual(2);
  expect(most).toBeLessThanOrEqual(4);
});

test("Evidence Lab: grouped results, each with its plain line; 9.9 is only under Not tested; the note on 8445", async () => {
  await stepLink(page, "4. Evidence Lab").click();
  await expect(page.getByRole("heading", { name: "Evidence", level: 1 })).toBeVisible();
  await openGroupTab(page, "Crypto tests");      // (the results are Evidence's Crypto tests tab)
  await expect(page.getByTestId("lab-group")).toHaveCount(5);
  await expect(page.getByTestId("evidence-row")).toHaveCount(8);
  await expect(page.getByTestId("not-tested")).toContainText("acme-sign 9.9: its tests can't run. Only our own demo components can run in this version.");
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  const g = (heading: string) => group("lab-group", heading);
  await expect(g("Server: localhost:8443").getByTestId("evidence-row").first()).toContainText(
    "The server accepts TLS 1.2, so ‘TLS 1.3 only’ is not true.");
  await expect(g("Server: localhost:8444").getByTestId("result-badge").locator("span:last-child")).toHaveText(["Passed"]);
  await expect(g("Server: localhost:8445").getByTestId("also-noticed")).toContainText(NOTE);
  await expect(g("Server: localhost:8445").getByTestId("result-badge").locator("span:last-child")).toHaveText(["Passed"]);
  await expect(g("Server: localhost:8446").getByTestId("result-badge").locator("span:last-child")).toHaveText(["Failed"]);
  await expect(g("Signing program: acme-sign 1.4.2").getByTestId("result-badge").locator("span:last-child"))
    .toHaveText(["Failed", "Failed", "Measured"]);
  await expect(page.getByRole("heading", { name: "Signing program: acme-sign 9.9", exact: true })).toHaveCount(0);
  // The technical text is inside the opened result.
  const program = g("Signing program: acme-sign 1.4.2");
  await toggleResult(page, "Independent exam (Wycheproof)", program);
  await expect(resultPanel(page).getByTestId("technical-summary")).toContainText("3 of 484 official cases wrong");
  await toggleResult(page, "Independent exam (Wycheproof)", program);
  await shot("03-evidence-lab-multi-target.png");
});

test("Fixes: the code fix for our program, and one text suggestion for each failing server", async () => {
  await stepLink(page, "5. Fixes").click();
  // (phase 5b: the list is in the four work groups; each group heading is a button too, so count the fixes' rows)
  const list = page.getByRole("navigation", { name: /^Open findings with a fix/ }).getByTestId("fix-row");
  await expect(list).toHaveCount(3);
  // (phase 5a follow-up: where a fix came from is in its row, beside the title button; phase 5b: in the full row, so
  // with the panel closed; beside an open panel a row is the fix and its status)
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  const rows = page.getByRole("navigation", { name: /^Open findings with a fix/ }).getByTestId("fix-row");
  await expect(rows.nth(1)).toContainText("Old TLS versions on localhost:8443");
  await expect(rows.nth(2)).toContainText("Certificate strength on localhost:8446");
  await shot("04-fixes-multi-target.png");
});
