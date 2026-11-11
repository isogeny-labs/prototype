// Phase 2 end to end, on the demo, with no internet and with main-screen buttons only (the assistant
// panel is never used): the five suggested tests, reorder, add a test, run one, Run all in parallel,
// Evidence Lab, Mark reviewed, Dig deeper, Retest on 1.4.3 with before and after, Download evidence
// and the `evidence verify` command. Runs after phase1.spec.ts, on the same app and data folder.
import { expect, test, type BrowserContext, type Download, type Locator, type Page } from "@playwright/test";
import { execFileSync, spawn, spawnSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BACKEND, DISCLAIMER, PYTHON, enterApp, importVerifyAndOpenTests, password, screenshotFolder } from "./shared";

const SHOTS = screenshotFolder("phase2");
const PQ_TOO_OLD = "Couldn't run (needs OpenSSL 3.5 or newer)";
const SUGGESTED = ["Old TLS versions", "Certificate strength", "Official test vectors", "Bad signatures", "Speed and size"];
const ALL_SIX = [...SUGGESTED, "Post-quantum readiness"];

let context: BrowserContext;
let page: Page;
let downloads: string;
let evidenceJson = "";
let evidenceHtml = "";

async function shot(target: Page, name: string): Promise<void> {
  await target.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

function card(title: string): Locator {
  return page.getByTestId("test-card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

function labRow(title: string): Locator {
  return page.getByTestId("lab-row").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

async function cardTitles(): Promise<string[]> {
  return page.getByTestId("test-card").getByRole("heading").evaluateAll((all) =>
    // The heading may carry a small tag after the title; the title is its first text.
    all.map((h) => (h.firstChild?.textContent ?? "").trim()),
  );
}

async function cardStatuses(): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

/** This version has no way to bring in outside software: no file picker, no drop zone, no upload wording. */
async function expectNoSoftwareUpload(): Promise<void> {
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  expect(await page.locator("body").innerText()).not.toMatch(/upload|drop (a|your) file|choose a file|browse/i);
}

/** The app never calls anything secure (outside the one fixed line), never scores, never estimates time to hack. */
async function expectCarefulWording(): Promise<void> {
  const text = (await page.locator("body").innerText()).replaceAll(DISCLAIMER, "");
  expect(text).not.toMatch(/\bsecure\b|security score|\bscore\b|time[- ]to[- ]hack/i);
}

function verifyEvidence(file: string): { code: number; output: string } {
  const run = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", process.env.E2E_DATA_DIR ?? ""], {
    cwd: BACKEND,
    encoding: "utf8",
    timeout: 60_000,
  });
  return { code: run.status ?? -1, output: `${run.stdout}${run.stderr}` };
}

test.describe.configure({ mode: "serial", timeout: 240_000 });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  downloads = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-downloads-"));
  context = await browser.newContext({ acceptDownloads: true });
  page = await context.newPage();
});

test.afterAll(async () => {
  await context.close();
  fs.rmSync(downloads, { recursive: true, force: true });
});

test("log in, Use demo file, Verify claims, Continue to tests: five tests are suggested", async () => {
  await enterApp(page);
  await importVerifyAndOpenTests(page);

  const cards = page.getByTestId("test-card");
  await expect(cards).toHaveCount(5);
  expect(await cardTitles()).toEqual(SUGGESTED);
  await expect(cards.getByTestId("test-status")).toHaveText(Array(5).fill("Not run yet"));
  for (const c of await cards.all()) {
    await expect(c).toContainText("Why it matters:");
    await expect(c.getByRole("button", { name: /^Run / })).toBeEnabled();
  }
  await expect(page.getByTestId("plan-subject")).toContainText("localhost:8443");
  await expect(page.getByTestId("plan-subject")).toContainText("acme-sign 1.4.2");
  await expect(page.getByTestId("plan-subject").getByText("from the file", { exact: true })).toBeVisible();
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(page.getByTestId("mode-line")).toHaveText("Demo mode: running our own demo software, not isolated. Isolated mode is switched off for this run.");
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
  // Evidence Lab opens only once there is a result.
  await expect(page.getByRole("button", { name: "4. Evidence Lab" })).toBeDisabled();
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot(page, "01-tests-before-running.png");
});

test("reorder two tests (keyboard, then drag); the order is kept after a refresh", async () => {
  // Keyboard: the handle of Speed and size, one place up.
  await card("Speed and size").getByTestId("drag-handle").focus();
  await page.keyboard.press("ArrowUp");
  const swapped = ["Old TLS versions", "Certificate strength", "Official test vectors", "Speed and size", "Bad signatures"];
  await expect.poll(cardTitles).toEqual(swapped);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Tests", level: 1 })).toBeVisible();
  await expect.poll(cardTitles).toEqual(swapped);
  const stored = await (await page.request.get(page.url().replace(/\/?$/, "/") + "api/import/current")).json();
  const plan = await (await page.request.get(`/api/import/${stored.id}/plan`)).json();
  expect(plan.tests.map((t: any) => t.title)).toEqual(swapped);

  // Mouse: drag Bad signatures back above Speed and size.
  await card("Bad signatures").getByTestId("drag-handle").dragTo(card("Speed and size"));
  await expect.poll(cardTitles).toEqual(SUGGESTED);
  await page.reload();
  await expect.poll(cardTitles).toEqual(SUGGESTED);
});

test("+ Add test opens the short catalog; adding Post-quantum readiness puts it last", async () => {
  await page.getByRole("button", { name: "+ Add test" }).click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  const items = menu.getByRole("menuitem");
  await expect(items).toHaveCount(2);
  await expect(items.filter({ hasText: "Post-quantum readiness" })).toContainText("X25519MLKEM768");
  await expect(items.filter({ hasText: "ML-DSA-65 comparison" })).toContainText("reference, not production");
  await expectNoSoftwareUpload();
  await shot(page, "02-tests-add-test-open.png");

  await items.filter({ hasText: "Post-quantum readiness" }).click();
  await expect(menu).toHaveCount(0);
  await expect(page.getByTestId("test-card")).toHaveCount(6);
  expect(await cardTitles()).toEqual(ALL_SIX);
  await expect(card("Post-quantum readiness").getByTestId("test-status")).toHaveText("Not run yet");
  await expect(page.getByText(/^Six tests in the plan: five suggested from the claims, one added by you\./)).toBeVisible();
});

test("run one test by itself: Certificate strength passes, the others stay not run", async () => {
  await card("Certificate strength").getByRole("button", { name: "Run Certificate strength" }).click();
  await expect(card("Certificate strength").getByTestId("result-badge").locator("span:last-child")).toHaveText("Passed", { timeout: 60_000 });
  await expect(page.getByTestId("result-badge").locator("span:last-child")).toHaveCount(1);
  for (const title of ALL_SIX.filter((t) => t !== "Certificate strength")) {
    await expect(card(title).getByTestId("test-status")).toHaveText("Not run yet");
  }
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
});

test("Run all runs the tests in parallel and every card ends with a result", async () => {
  await page.getByRole("button", { name: "Run all" }).click();

  // Watch the cards until nothing is waiting or running, and note the most seen running at once.
  let mostRunning = 0;
  let sawWaiting = false;
  let shotTaken = false;
  let laterShotTaken = false;
  const seenProgress = new Set<string>();
  const deadline = Date.now() + 200_000;
  for (;;) {
    const statuses = await cardStatuses();
    const running = statuses.filter((s) => s === "running").length;
    mostRunning = Math.max(mostRunning, running);
    sawWaiting ||= statuses.includes("waiting");
    for (const text of await page.getByTestId("job-status").allInnerTexts()) seenProgress.add(text.replace(/\s+/g, " "));
    if (!shotTaken && running >= 3) {
      // While anything runs, nothing can be started or removed.
      await expect(page.getByRole("button", { name: "Run all" })).toBeDisabled();
      await shot(page, "03-tests-running.png");
      shotTaken = true;
    }
    // A better picture a little later, if the moment comes: some tests finished, others part-way, one waiting.
    if (!laterShotTaken && running >= 2 && statuses.includes("done") && (await page.getByText(/^[1-9]\d\d of 484 cases$/).count()) > 0) {
      await shot(page, "03-tests-running.png");
      laterShotTaken = true;
    }
    if (statuses.length === 6 && statuses.every((s) => s === "done")) break;
    expect(Date.now(), `tests still running after 200 s: ${statuses.join(", ")}`).toBeLessThan(deadline);
    await page.waitForTimeout(150);
  }
  expect(mostRunning, "at least two tests were seen running at the same moment").toBeGreaterThanOrEqual(2);
  expect(shotTaken, "three tests were seen running at once (screenshot 03)").toBe(true);
  // Live progress text was shown on running cards.
  expect([...seenProgress].some((t) => /of 484 cases/.test(t)), [...seenProgress].join(" | ")).toBe(true);
  test.info().annotations.push({ type: "parallel", description: `most running at once: ${mostRunning}; waiting seen: ${sawWaiting}` });

  const label = (title: string) => card(title).getByTestId("result-badge").locator("span:last-child");
  await expect(label("Old TLS versions")).toHaveText("Failed");
  await expect(label("Certificate strength")).toHaveText("Passed");
  await expect(label("Official test vectors")).toHaveText("Failed");
  await expect(label("Bad signatures")).toHaveText("Failed");
  await expect(label("Speed and size")).toHaveText("Measured");
  const pq = (await label("Post-quantum readiness").innerText()).trim();
  expect(["Not offered", PQ_TOO_OLD]).toContain(pq);
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
  await expectCarefulWording();
});

test("Evidence Lab lists the six results; every control behaved as expected", async () => {
  await page.getByRole("button", { name: "4. Evidence Lab" }).click();
  await expect(page.getByRole("heading", { name: "Evidence Lab", level: 1 })).toBeVisible();
  const rows = page.getByTestId("lab-row");
  await expect(rows).toHaveCount(6);
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(page.getByTestId("lab-subline")).toContainText("acme-sign 1.4.2");

  await expect(rows.getByTestId("result-badge").locator("span:last-child")).toHaveCount(6);
  await expect(page.getByText("Couldn't trust this run")).toHaveCount(0);
  await expect(labRow("Old TLS versions")).toContainText("The server accepted TLS 1.2. The file claims TLS 1.3 only.");
  await expect(labRow("Certificate strength")).toContainText("NIST plans to retire P-256");
  await expect(labRow("Official test vectors")).toContainText("3 of 484 official cases wrong");
  await expect(labRow("Bad signatures")).toContainText("r=0, s=0");
  for (const title of ALL_SIX) {
    const row = labRow(title);
    const ran = !(await row.getByTestId("result-badge").locator("span:last-child").innerText()).startsWith("Couldn't run");
    if (ran) await expect(row.getByText(/^Control: .* as expected\.$/)).toBeVisible();
  }
  // Locked test details and fingerprints are only inside an opened result.
  await expect(page.getByTestId("locked-test")).toHaveCount(0);
  await expect(page.getByTestId("spec-fingerprint")).toHaveCount(0);
  // Only the two buttons the spec gives this screen (plus the rows themselves).
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot(page, "04-lab-results-collapsed.png");
});

test("Official test vectors: the three wrong cases, the locked test and its fingerprint", async () => {
  const row = labRow("Official test vectors");
  await row.getByRole("button", { name: "Official test vectors" }).click();
  const detail = row.getByTestId("result-detail");
  await expect(detail).toHaveCount(1);
  const wrong = detail.getByRole("table").first().locator("tbody tr");
  await expect(wrong).toHaveCount(3);
  await expect(wrong.nth(0)).toContainText("168");
  await expect(wrong.nth(0)).toContainText("r=0 and s=0");
  await expect(wrong.nth(1)).toContainText("171");
  await expect(wrong.nth(2)).toContainText("364");
  await expect(detail.getByText("What happened")).toBeVisible();
  await expect(detail.getByText("What this shows, and what it doesn't")).toBeVisible();
  await expect(detail.getByText("measured", { exact: true }).first()).toBeVisible();
  await expect(detail.getByText("reference", { exact: true }).first()).toBeVisible();
  await expect(detail.getByText("demo", { exact: true }).first()).toBeVisible();

  const locked = detail.getByTestId("locked-test");
  for (const field of ["Question", "Method", "Inputs", "Control", "Pass/fail rule", "Locked"]) {
    await expect(locked.getByText(field, { exact: true })).toBeVisible();
  }
  await expect(detail.getByTestId("spec-fingerprint")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(detail.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  await expect(detail.getByTestId("control-outcome")).toContainText("all 310 invalid cases wrong");
  await expect(detail.getByTestId("suggested-fix")).toContainText("acme-sign 1.4.3");
  await expect(detail.getByRole("button", { name: "Mark reviewed" })).toBeEnabled();
  await expect(detail.getByRole("button", { name: "Dig deeper" })).toBeEnabled();
  // Phase 3's "Suggested change" panel is not in this version.
  await expect(page.getByText("Suggested change")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Review change" })).toHaveCount(0);
  await shot(page, "05-lab-vectors-expanded.png");
});

test("Dig deeper saves a queued research request with no answer; Mark reviewed records the user's decision", async () => {
  const detail = labRow("Official test vectors").getByTestId("result-detail");
  const before = await labRow("Official test vectors").getByTestId("result-badge").locator("span:last-child").first().innerText();

  await detail.getByRole("button", { name: "Dig deeper" }).click();
  const request = detail.getByTestId("research-request");
  await expect(request).toBeVisible();
  await expect(request).toContainText("Research request saved");
  await expect(request).toContainText("Queued");
  await expect(request).toContainText("Status: waiting for research engine");
  await expect(request).toContainText("No answer yet.");
  await expect(detail.getByRole("button", { name: "Dig deeper: queued" })).toBeDisabled();

  await detail.getByRole("button", { name: "Mark reviewed" }).click();
  await expect(detail.getByRole("button", { name: "Reviewed", exact: true })).toBeDisabled();
  await expect(detail.getByTestId("reviewed-note")).toContainText("You marked this result as reviewed.");

  // Neither button changes the result, and both survive a refresh.
  await expect(labRow("Official test vectors").getByTestId("result-badge").locator("span:last-child").first()).toHaveText(before);
  await shot(page, "06-lab-dig-deeper-queued.png");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Evidence Lab", level: 1 })).toBeVisible();
  await labRow("Official test vectors").getByRole("button", { name: "Official test vectors" }).click();
  const again = labRow("Official test vectors").getByTestId("result-detail");
  await expect(again.getByRole("button", { name: "Dig deeper: queued" })).toBeDisabled();
  await expect(again.getByRole("button", { name: "Reviewed", exact: true })).toBeDisabled();
  await expect(again.getByTestId("research-request")).toContainText("waiting for research engine");
});

test("Bad signatures failed on 1.4.2: the r=0, s=0 case is shown, with the suggested fix", async () => {
  // Close the vectors row so the screenshot shows this one result.
  await labRow("Official test vectors").getByRole("button", { name: "Official test vectors" }).click();
  await expect(page.getByTestId("result-detail")).toHaveCount(0);

  const row = labRow("Bad signatures");
  await expect(row.getByTestId("result-badge").locator("span:last-child")).toHaveText("Failed");
  await row.getByRole("button", { name: "Bad signatures" }).click();
  const detail = row.getByTestId("result-detail");
  const zeroCase = detail.getByRole("table").first().locator("tbody tr").filter({ hasText: /r\s?=\s?0.*s\s?=\s?0/ });
  await expect(zeroCase.first()).toBeVisible();
  await expect(zeroCase.first()).toContainText(/accepted/i);
  await expect(detail.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  await expect(detail.getByTestId("suggested-fix")).toContainText("Suggested fix");
  await expect(detail.getByTestId("suggested-fix")).toContainText("acme-sign 1.4.3");
  await expect(detail.getByTestId("spec-fingerprint")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(detail.getByRole("button", { name: "Mark reviewed" })).toBeEnabled();
  await expect(detail.getByRole("button", { name: "Dig deeper" })).toBeEnabled();
  await expectCarefulWording();
  await shot(page, "10-lab-bad-signatures-expanded.png");
  await row.getByRole("button", { name: "Bad signatures" }).click();
});

test("Retest new version offers only our two demo versions; picking 1.4.3 starts it at once", async () => {
  const fingerprintsBefore = await specFingerprints();

  await page.getByRole("button", { name: "Retest new version" }).click();
  const menu = page.getByRole("menu");
  const items = menu.getByRole("menuitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("acme-sign 1.4.3");
  await expect(items.nth(1)).toContainText("acme-sign 1.4.2");
  await expect(menu).toContainText("Only our two demo versions can be chosen here.");
  await expect(menu.locator("button, input, a")).toHaveCount(2); // the two versions: no extra confirm button, no upload
  await expectNoSoftwareUpload();
  await shot(page, "07-lab-retest-chooser.png");

  await items.nth(0).click();
  await expect(menu).toHaveCount(0);
  // The list turns into before and after straight away, and shows that it is running.
  await expect(page.getByTestId("lab-columns")).toContainText("Before: acme-sign 1.4.2");
  await expect(page.getByTestId("lab-columns")).toContainText("After: acme-sign 1.4.3");
  await expect(page.getByTestId("retest-progress")).toContainText("Retest running");
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeDisabled();
  await expect(page.getByTestId("lab-cell-after").getByTestId("job-status").first()).toBeVisible();
  await shot(page, "08a-lab-before-after-running.png");

  await expect(page.getByTestId("retest-progress")).toHaveCount(0, { timeout: 200_000 });
  const cells = async (title: string) => [
    (await labRow(title).getByTestId("lab-cell-before").getByTestId("result-badge").locator("span:last-child").innerText()).trim(),
    (await labRow(title).getByTestId("lab-cell-after").getByTestId("result-badge").locator("span:last-child").innerText()).trim(),
  ];
  expect(await cells("Old TLS versions")).toEqual(["Failed", "Failed"]);
  expect(await cells("Certificate strength")).toEqual(["Passed", "Passed"]);
  expect(await cells("Official test vectors")).toEqual(["Failed", "Passed"]);
  expect(await cells("Bad signatures")).toEqual(["Failed", "Passed"]);
  expect(await cells("Speed and size")).toEqual(["Measured", "No slowdown beyond measured noise"]);
  const [pqBefore, pqAfter] = await cells("Post-quantum readiness");
  expect(["Not offered", PQ_TOO_OLD]).toContain(pqBefore);
  expect(pqAfter).toBe(pqBefore);

  await expect(labRow("Official test vectors").getByTestId("lab-cell-after")).toContainText("484 of 484 official cases right.");
  await expect(labRow("Bad signatures").getByTestId("lab-cell-after")).toContainText("Rejects r=0, s=0");
  await expect(page.getByText("Couldn't trust this run")).toHaveCount(0);
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByTestId("lab-subline")).toContainText("Retest finished");
  await shot(page, "08-lab-before-after.png");

  // The same locked tests were rerun: every fingerprint is the one from before the retest.
  expect(await specFingerprints()).toEqual(fingerprintsBefore);
});

/** The locked-test fingerprint of every test, as the app reports it (first run and, if there is one, the retest). */
async function specFingerprints(): Promise<Record<string, string[]>> {
  const current = await (await page.request.get("/api/import/current")).json();
  const plan = await (await page.request.get(`/api/import/${current.id}/plan`)).json();
  const lab = await (await page.request.get(`/api/plans/${plan.id}/lab`)).json();
  const out: Record<string, string[]> = {};
  for (const row of lab.rows) {
    const prints = [row.result, row.after].filter(Boolean).map((r: any) => r.locked_test.fingerprint as string);
    expect(new Set(prints).size, `${row.title}: before and after carry the same fingerprint`).toBe(1);
    out[row.kind] = [prints[0]];
  }
  return out;
}

test("before and after stays expandable: the bad-signature case now passes, and speed shows the measured noise", async () => {
  const bad = labRow("Bad signatures");
  await bad.getByRole("button", { name: "Bad signatures" }).click();
  const details = bad.getByTestId("result-detail");
  await expect(details).toHaveCount(2);
  const after = details.nth(0);
  const before = details.nth(1);
  await expect(after.getByRole("heading", { name: "After: acme-sign 1.4.3" })).toBeVisible();
  await expect(after.getByTestId("result-badge").locator("span:last-child")).toHaveText("Passed");
  await expect(after).toContainText(/r\s?=\s?0.*s\s?=\s?0/);
  await expect(after.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  await expect(before.getByRole("heading", { name: "Before: acme-sign 1.4.2" })).toBeVisible();
  await expect(before.getByTestId("result-badge").locator("span:last-child")).toHaveText("Failed");
  // Mark reviewed and Dig deeper are on every opened result.
  for (const d of [after, before]) {
    await expect(d.getByRole("button", { name: /^(Mark reviewed|Reviewed)$/ })).toBeVisible();
    await expect(d.getByRole("button", { name: /^Dig deeper/ })).toBeVisible();
  }
  await shot(page, "10a-lab-bad-signatures-after.png");
  await bad.getByRole("button", { name: "Bad signatures" }).click();

  const speed = labRow("Speed and size");
  await speed.getByRole("button", { name: "Speed and size" }).click();
  const result = speed.getByTestId("result-detail").nth(0);
  await expect(result.getByTestId("result-badge").locator("span:last-child")).toHaveText("No slowdown beyond measured noise");
  const table = result.getByRole("table").first();
  await expect(table.locator("thead")).toContainText("acme-sign 1.4.2");
  await expect(table.locator("thead")).toContainText("acme-sign 1.4.3");
  await expect(table.locator("thead")).toContainText("Reference library");
  for (const name of ["Sign, median", "Sign, slowest 1 in 100", "Verify, median", "Verify, slowest 1 in 100", "Signature size, this run", "Public key size"]) {
    await expect(table.locator("tbody tr").filter({ hasText: name })).toHaveCount(1);
  }
  await expect(result).toContainText(/Measured noise: ±\d+(\.\d+)?%/);
  await expect(result).toContainText(/Repeats: \d+ sign and \d+ verify per version/);
  await expect(result).toContainText("for scale only");
  await expect(result.getByText("measured", { exact: true }).first()).toBeVisible();
  await expect(result.getByText("reference", { exact: true }).first()).toBeVisible();
  await expect(result.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  await expectCarefulWording();
  await shot(page, "09-lab-speed-expanded.png");
  await speed.getByRole("button", { name: "Speed and size" }).click();

  // The earlier Mark reviewed and Dig deeper are still on the first run's result.
  const vectors = labRow("Official test vectors");
  await vectors.getByRole("button", { name: "Official test vectors" }).click();
  const first = vectors.getByTestId("result-detail").nth(1);
  await expect(first.getByRole("button", { name: "Reviewed", exact: true })).toBeDisabled();
  await expect(first.getByTestId("research-request")).toContainText("waiting for research engine");
  await vectors.getByRole("button", { name: "Official test vectors" }).click();
});

test("Download evidence gives a JSON file and an HTML report; the verify command passes on the file", async () => {
  const got: Download[] = [];
  page.on("download", (d) => got.push(d));
  await page.getByRole("button", { name: "Download evidence" }).click();
  await expect.poll(() => got.length, { timeout: 30_000 }).toBe(2);

  for (const d of got) {
    const name = d.suggestedFilename();
    const target = path.join(downloads, name);
    await d.saveAs(target);
    if (name.endsWith(".json")) evidenceJson = target;
    if (name.endsWith(".html")) evidenceHtml = target;
  }
  expect(path.basename(evidenceJson)).toMatch(/^evidence-lab-evidence-\d{8}-\d{6}\.json$/);
  expect(path.basename(evidenceHtml)).toMatch(/^evidence-lab-report-\d{8}-\d{6}\.html$/);

  const status = page.getByTestId("download-status");
  await expect(status).toContainText("The JSON file is the record.");
  await expect(status).toContainText("-m evidence verify");
  const shown = (await page.getByTestId("evidence-fingerprint").innerText()).trim();
  expect(shown).toMatch(/^[0-9a-f]{64}$/);
  await shot(page, "11-lab-evidence-downloaded.png");

  const envelope = JSON.parse(fs.readFileSync(evidenceJson, "utf8"));
  expect(Object.keys(envelope).sort()).toEqual(["evidence", "fingerprint", "public_key", "signature"]);
  expect(envelope.fingerprint).toBe(shown);
  expect(envelope.evidence.tests).toHaveLength(6);
  expect(envelope.evidence.disclaimer).toBe(DISCLAIMER);

  const ok = verifyEvidence(evidenceJson);
  expect(ok.output).toContain("Evidence verified");
  expect(ok.output).toContain(shown);
  expect(ok.code).toBe(0);
});

test("changing one byte of the evidence file makes the check fail", async () => {
  const original = fs.readFileSync(evidenceJson);
  const text = original.toString("latin1");
  // One byte each: inside a test result, inside the fingerprint, inside the signature, and one added space.
  const places = [text.indexOf('"Failed"') + 1, text.indexOf('"fingerprint":"') + 20, text.indexOf('"signature":"') + 20, Math.floor(original.length / 2)];
  for (const [i, at] of places.entries()) {
    expect(at).toBeGreaterThan(20);
    const changed = Buffer.from(original);
    changed[at] = changed[at] ^ 0x01;
    expect(changed.equals(original)).toBe(false);
    const copy = path.join(downloads, `changed-${i}.json`);
    fs.writeFileSync(copy, changed);
    const result = verifyEvidence(copy);
    expect(result.code, `byte ${at} changed: ${result.output}`).not.toBe(0);
    expect(result.output).not.toContain("Evidence verified");
  }
  // The untouched file still passes.
  expect(verifyEvidence(evidenceJson).code).toBe(0);
});

test("the HTML report is a static, readable copy that prints the same fingerprint; no key is in either file", async ({ browser }) => {
  const json = fs.readFileSync(evidenceJson, "utf8");
  const html = fs.readFileSync(evidenceHtml, "utf8");
  const fingerprint = JSON.parse(json).fingerprint as string;
  for (const body of [json, html]) {
    expect(body.includes("PRIVATE KEY")).toBe(false);
    expect(body.includes(password)).toBe(false);
  }
  const signingKey = fs.readFileSync(path.join(process.env.E2E_DATA_DIR ?? "", "evidence-signing-key.pem"), "utf8");
  const keyLines = signingKey.split("\n").filter((line) => line.length >= 20 && !line.startsWith("-----"));
  expect(keyLines.length).toBeGreaterThan(0);
  // True/false only, so a key can never end up in a test report.
  expect(keyLines.some((line) => json.includes(line) || html.includes(line))).toBe(false);
  expect(/<script/i.test(html)).toBe(false);
  expect(html).toContain("Content-Security-Policy");
  expect(html).toContain(fingerprint);

  const report = await context.newPage();
  try {
    await report.goto(`file://${evidenceHtml}`);
    await expect(report.getByText("The JSON file is the record.").first()).toBeVisible();
    await expect(report.getByText(fingerprint).first()).toBeVisible();
    await expect(report.getByText(DISCLAIMER).first()).toBeVisible();
    await expect(report.getByText("No slowdown beyond measured noise").first()).toBeVisible();
    const text = (await report.locator("body").innerText()).replaceAll(DISCLAIMER, "");
    expect(text).not.toMatch(/\bsecure\b|security score|time[- ]to[- ]hack/i);
    // The report is long (every run record of both runs). At double size: its first part. Whole page: normal size.
    await report.screenshot({ path: path.join(SHOTS, "12-evidence-report-html.png"), clip: { x: 0, y: 0, width: 1440, height: 2600 } });
  } finally {
    await report.close();
  }
  const plain = await browser.newContext({ deviceScaleFactor: 1, viewport: { width: 1440, height: 900 } });
  try {
    const whole = await plain.newPage();
    await whole.goto(`file://${evidenceHtml}`);
    await whole.screenshot({ path: path.join(SHOTS, "12a-evidence-report-html-whole.png"), fullPage: true });
  } finally {
    await plain.close();
  }
});

test("nothing in the app takes outside software: no upload control on Tests or Evidence Lab, no such address", async () => {
  await expectNoSoftwareUpload();
  await page.getByRole("button", { name: "3. Tests" }).click();
  await expect(page.getByTestId("test-card")).toHaveCount(6);
  await expectNoSoftwareUpload();
  await page.getByRole("button", { name: "+ Add test" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await expectNoSoftwareUpload();
  await page.keyboard.press("Escape");
  // The only file the app takes is the claims file on Import.
  await page.getByRole("button", { name: "1. Import" }).click();
  await expect(page.locator('input[type="file"]')).toHaveCount(1);
  await expect(page.getByLabel("Choose a file to import")).toHaveCount(1);
  for (const address of ["/api/components", "/api/software", "/api/upload", "/api/plans/1/software", "/api/plans/1/component"]) {
    const answer = await page.request.post(address, { multipart: { file: { name: "x.zip", mimeType: "application/zip", buffer: Buffer.from("PK") } } });
    expect([404, 405], `${address} answered ${answer.status()}`).toContain(answer.status());
  }
  // A version that is not one of our two demo versions is refused.
  const current = await (await page.request.get("/api/import/current")).json();
  const plan = await (await page.request.get(`/api/import/${current.id}/plan`)).json();
  const refused = await page.request.post(`/api/plans/${plan.id}/retest`, { data: { version: "9.9.9" } });
  expect(refused.status()).toBe(422);
});

test("isolated mode: the mode line says so and a test really runs in a container", async ({ browser }) => {
  // A second copy of the app, with its own throwaway data folder and ports, left to choose its mode itself.
  const port = Number(process.env.E2E_APP_PORT ?? "8010") + 1;
  const tlsPort = Number(process.env.E2E_DEMO_TLS_PORT ?? "8443") + 1;
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-isolated-"));
  let app: ChildProcess | null = null;
  const second = await browser.newContext({ baseURL: `http://127.0.0.1:${port}` });
  try {
    app = spawn(PYTHON, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port), "--log-level", "warning"], {
      cwd: BACKEND,
      stdio: "ignore",
      env: {
        PATH: process.env.PATH ?? "",
        HOME: process.env.HOME ?? "",
        EVIDENCE_LAB_DATA_DIR: dataDir,
        EVIDENCE_LAB_DEMO_TLS_PORT: String(tlsPort),
      },
    });
    let session: any = null;
    await expect
      .poll(async () => {
        try {
          session = await (await second.request.get("/api/session")).json();
          return true;
        } catch {
          return false;
        }
      }, { timeout: 30_000 })
      .toBe(true);
    test.skip(
      session.mode !== "isolated",
      "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).",
    );

    const view = await second.newPage();
    await enterApp(view);
    await expect(view.getByTestId("mode-line")).toHaveText("Isolated mode: our demo software runs in a locked-down container with no network.");
    await importVerifyAndOpenTests(view);
    const bad = view.getByTestId("test-card").filter({ hasText: "Bad signatures" });
    const vectors = view.getByTestId("test-card").filter({ hasText: "Official test vectors" });
    await bad.getByRole("button", { name: "Run Bad signatures" }).click();
    await expect(bad.getByTestId("result-badge").locator("span:last-child")).toHaveText("Failed", { timeout: 120_000 });
    await vectors.getByRole("button", { name: "Run Official test vectors" }).click();
    await expect(vectors.getByTestId("result-badge").locator("span:last-child")).toHaveText("Failed", { timeout: 120_000 });

    await view.getByRole("button", { name: "4. Evidence Lab" }).click();
    const row = view.getByTestId("lab-row").filter({ hasText: "Bad signatures" });
    await row.getByRole("button", { name: "Bad signatures" }).click();
    const detail = row.getByTestId("result-detail");
    await expect(detail).toContainText(/Mode: Isolated mode/);
    await expect(detail.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
    await expect(view.getByText("Couldn't trust this run")).toHaveCount(0);
    await view.screenshot({ path: path.join(SHOTS, "13-isolated-mode.png"), fullPage: true, animations: "disabled" });

    // No test container is left behind.
    const left = execFileSync("docker", ["ps", "-aq", "--filter", "label=evidence-lab=1"], { encoding: "utf8" }).trim();
    expect(left).toBe("");
  } finally {
    await second.close();
    if (app) {
      app.kill("SIGTERM");
      await new Promise((resolve) => setTimeout(resolve, 1500));
      if (app.exitCode === null) app.kill("SIGKILL");
    }
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
