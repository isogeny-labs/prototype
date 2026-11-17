// Phase 5c end to end: Otto in Evidence Lab. Two parts, each on a copy of the app of its own (own data folder and
// ports), so the main app the phase walks share is never touched:
//
//  1. Demo mode, the Acme Pay demo file, with the two test packs this repository ships: Settings (Test packs and Live
//     Otto), Check for updates, Install update (its box: Cancel, then Install), Advisories (the table at 1440 pixels
//     wide with its panel closed and open, the panel's parts, Add new checks, which runs nothing), the advisory checks
//     on Checks and in Evidence, the fix on Fixes (the fix template, with why Otto's own change is not offered) and
//     its proof, the second pack, Download evidence and the verify command.
//  2. Isolated mode (skipped with a message when Docker or the test images are not ready): the real libraries file.
//     One advisory check fails on a real library, and its fix is the one the test pack carries, labelled "From Otto".
//
// Both parts are skipped with a message when Otto is not installed on this computer (./run-demo.sh fetches it, or:
// cd backend && .venv/bin/python -m app.prepare --otto). The answers are the ones recorded during the build: a copy
// of the app is started without any API key, so nothing here can reach Claude.
// Main-screen buttons only. Screenshots (dark and light) go to docs/screenshots/phase5c/.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND, DISCLAIMER, PYTHON, REPO, enterApp, evidenceRow, importVerifyAndOpenTests, layoutProblems, openFreshAssessment, openResult,
  screenshotFolder, startCopy, stepLink, stopCopy, type Copy,
} from "./shared";

const SHOTS = screenshotFolder("phase5c");
const REAL_FILE = path.join(REPO, "demo/real-libraries.csv");
const RANGE = "Missing ECDSA signature range check";
const RANGE_CHECK = `Advisory check: ${RANGE} (CVE-2022-21449)`;
const MISSING_ZERO_CHECK = "Advisory check: Wrongly encoded signature accepted (CVE-2024-42460)";
const NOT_OFFERED = "Otto's own change is not offered here.";

async function shots(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: true, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** Skips the test, with the reason, when Otto is not on this computer. Returns what Settings shows about Otto. */
async function ottoOrSkip(page: Page): Promise<any> {
  const otto = await (await page.request.get("/api/otto")).json();
  test.skip(!otto.harness.installed,
            `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
  return otto;
}

function assessmentOf(page: Page): string {
  const found = /#\/a\/(\d+)/.exec(page.url());
  if (!found) throw new Error(`no assessment is open: ${page.url()}`);
  return found[1];
}

async function openSettings(page: Page): Promise<Locator> {
  await page.goto("/#/settings?section=test-packs");
  const packs = page.getByTestId("test-packs");
  await expect(packs.getByTestId("otto-harness-line")).toBeVisible();
  return packs;
}

/** Settings, Test packs: Check for updates, Install update, Install. */
async function installPack(page: Page, version: string): Promise<void> {
  const packs = await openSettings(page);
  await packs.getByTestId("otto-check-updates").click();
  await expect(packs.getByTestId("otto-update-line")).toHaveText(`Test pack ${version} is in the updates folder.`);
  await packs.getByTestId("otto-install-update").click();
  const box = page.getByTestId("otto-install-dialog");
  await expect(box).toContainText(`Install test pack ${version}?`);
  const installed = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/otto/packs/install" && r.request().method() === "POST");
  await box.getByTestId("otto-install-confirm").click();
  expect((await installed).status()).toBe(200);
  await expect(page.getByTestId("otto-install-dialog")).toHaveCount(0);
  await expect(packs.locator(`[data-testid="otto-pack-card"][data-version="${version}"]`)).toBeVisible();
}

async function openAdvisories(page: Page, assessment: string): Promise<Locator> {
  await page.goto(`/#/a/${assessment}/advisories`);
  const advisories = page.getByTestId("advisories-page");
  await expect(advisories.getByTestId("advisories-standing")).toHaveText(DISCLAIMER);
  return advisories;
}

function advisoryRow(page: Page, id: string): Locator {
  return page.locator(`[data-testid="advisory-row"][data-advisory="${id}"]`);
}

async function openAdvisory(page: Page, id: string): Promise<Locator> {
  const panel = page.locator(`[data-testid="advisory-panel"][data-advisory="${id}"]`);
  if ((await panel.count()) === 0) await advisoryRow(page, id).click();
  await expect(panel.getByTestId("advisory-sentence")).toBeVisible();
  await page.waitForLoadState("networkidle");   // the panel asks for its Related block
  return panel;
}

function card(page: Page, title: string): Locator {
  return page.getByTestId("test-card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

async function cardStatuses(page: Page): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

async function runAllAndWait(page: Page, count: number): Promise<void> {
  await stepLink(page, "Checks").click();
  await expect(page.getByTestId("test-card")).toHaveCount(count);
  await page.getByRole("button", { name: "Run all" }).click();
  await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(count).fill("done"));
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
}

function codeFix(page: Page): Locator {
  return page.getByTestId("fix-summary");
}

async function downloadEvidence(page: Page): Promise<{ json: any; report: string; file: string }> {
  await stepLink(page, "Evidence").click();
  const created = page.waitForResponse((r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const raw = await (await page.request.get(info.json.url)).body();
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-otto-file-")), "evidence.json");
  fs.writeFileSync(file, raw);
  return { json: JSON.parse(raw.toString("utf-8")), report: await (await page.request.get(info.html.url)).text(), file };
}

function verify(file: string, dataDir: string) {
  return spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", dataDir], { cwd: BACKEND, encoding: "utf-8" });
}

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------- 1. demo mode: the Acme Pay demo file

test("demo mode: a test pack is installed, its checks are added and run, the fix is proven, the evidence verifies", async ({ browser }) => {
  test.setTimeout(15 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 7, "demo");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    await enterApp(page);
    const otto = await ottoOrSkip(page);
    expect(otto.live.key_present, "a copy of the app is started without an API key").toBe(false);
    await openFreshAssessment(page, "Otto walk");
    await importVerifyAndOpenTests(page);
    const assessment = assessmentOf(page);

    // ---- Advisories before any pack: it says so, and nothing can be added
    let advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(0);
    await expect(advisories.getByTestId("advisories-empty")).toBeVisible();
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await expect(advisories.getByTestId("add-new-checks-reason")).toBeVisible();
    await shots(page, "01-advisories-no-pack");

    // ---- Settings: Test packs and Live Otto, with nothing installed and no key
    let packs = await openSettings(page);
    await expect(packs.getByTestId("otto-installed-line")).toHaveText("No test pack is installed yet.");
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(0);
    await expect(packs.getByTestId("otto-harness-line")).toContainText(/^Otto harness: version \S+, commit [0-9a-f]{7} \(pinned\)\.$/);
    await expect(packs.getByTestId("otto-answers-line")).toContainText("recorded during the build");
    await expect(packs.getByTestId("otto-order-note")).toHaveText("Packs install in order and are never removed.");
    const live = page.getByTestId("live-otto");
    await expect(live.getByTestId("live-otto-key-line")).toContainText("No API key is set on this computer");
    await expect(live.getByTestId("live-otto-switch")).toBeDisabled();
    await expect(live.getByTestId("live-otto-switch-reason")).toHaveText("This can be turned on only when an API key is present.");
    await expect(live.getByTestId("live-otto-limit")).toHaveValue("2.00");
    await expect(live.getByTestId("live-otto-status-line")).toContainText("Live Otto is off");
    await expect(live.getByTestId("live-otto-sent-line")).toContainText("What is sent to Claude");
    // no field anywhere takes a key
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await shots(page, "02-settings-no-pack");

    // ---- Check for updates (the folder on this computer), then Install update: Cancel installs nothing
    await packs.getByTestId("otto-check-updates").click();
    await expect(packs.getByTestId("otto-update-line")).toHaveText("Test pack 2026.11.1 is in the updates folder.");
    await packs.getByTestId("otto-install-update").click();
    const box = page.getByTestId("otto-install-dialog");
    await expect(box).toContainText("Install test pack 2026.11.1?");
    await expect(box.getByTestId("otto-install-confirm")).toHaveText("Install");
    await expect(box.getByTestId("otto-install-cancel")).toHaveText("Cancel");
    await shots(page, "03-install-update-box");
    await box.getByTestId("otto-install-cancel").click();
    await expect(page.getByTestId("otto-install-dialog")).toHaveCount(0);
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(0);
    await installPack(page, "2026.11.1");
    packs = page.getByTestId("test-packs");
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(1);
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Pack 2026.11.1");
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Isogeny Labs demo pack key");
    await shots(page, "04-settings-pack-installed");

    // ---- Advisories: the three advisories of the pack, each with a test; nothing is in the plan yet
    advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await expect(advisories.getByTestId("advisories-packs-line")).toContainText("2026.11.1");
    await expect(advisories.getByTestId("advisory-test")).toHaveText(["Test ready", "Test ready", "Test ready"]);
    await expect(advisories.getByTestId("add-new-checks")).toHaveText("Add new checks (3)");
    await expect(advisories.getByTestId("add-new-checks-note")).toContainText("It runs nothing.");
    expect(await layoutProblems(page), "Advisories, panel closed").toEqual([]);
    await shots(page, "05-advisories-panel-closed");

    // ---- the panel: the publisher's own line with its link, the test and how it did on public copies, the fix
    let panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByRole("heading", { level: 2, name: RANGE })).toBeVisible();
    await expect(panel.getByTestId("advisory-publisher")).toContainText("rb.signum() == 0");
    await expect(panel.getByTestId("advisory-publisher").getByRole("link").first()).toHaveAttribute("href", /^https:\/\/github\.com\/openjdk\//);
    const block = panel.getByTestId("advisory-test-block");
    await expect(block).toContainText("77 published cases");
    await expect(block).toContainText("accepts every signature");                 // the control that must fail
    await expect(block).toContainText("Passed only if every answer is right");    // the pass rule
    await expect(panel.getByTestId("advisory-trial").first()).toContainText("openjdk 17.0.2");
    await expect(panel.getByTestId("advisory-here")).toContainText("Not added yet");
    await expect(panel.getByTestId("advisory-fix-label")).toHaveText("From Otto");
    await expect(panel.getByTestId("advisory-fix")).toContainText("update openjdk to 17.0.3");
    await expect(panel.getByTestId("advisory-fix")).toContainText("Not proven");
    await expect(panel.getByTestId("advisory-claude")).toContainText("Recorded during the build");
    await expect(page.locator('main [data-compact="true"]').first()).toBeVisible();
    expect(await layoutProblems(page), "Advisories, panel open").toEqual([]);
    await shots(page, "06-advisories-panel-open");
    // the ledger entries of the research are folded under the test
    await panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger").locator("summary").click();
    await expect(panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger-entry").first()).toBeVisible();
    await shots(page, "07-advisory-ledger-open");
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();

    // ---- Add new checks: three tests join the plan, and nothing runs
    const added = page.waitForResponse((r) => /\/api\/plans\/\d+\/advisories\/add$/.test(r.url()) && r.request().method() === "POST");
    await advisories.getByTestId("add-new-checks").click();
    expect((await added).status()).toBe(200);
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await expect(advisories.getByTestId("add-new-checks-reason")).toContainText("already in the test plan");
    await expect(advisories.getByTestId("advisory-result")).toHaveText(["Not run yet", "Not run yet", "Not run yet"]);
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(8);
    await expect(card(page, RANGE_CHECK)).toHaveAttribute("data-status", "not_run");
    expect((await cardStatuses(page)).filter((s) => s === "done")).toEqual([]);
    await shots(page, "08-checks-advisory-checks-added");

    // ---- Run all: the check for the range advisory fails on acme-sign 1.4.2, the other two pass
    await runAllAndWait(page, 8);
    await stepLink(page, "Evidence").click();
    let result = await openResult(page, RANGE_CHECK);
    await expect(result.getByTestId("result-badge").first()).toContainText("Failed");
    await expect(result.getByTestId("advisories")).toContainText("CVE-2022-21449");
    await expect(result.getByTestId("advisories")).toContainText("from the advisory, not a result");
    await expect(result.getByTestId("advisories").getByRole("link").first()).toHaveAttribute("href", /^https:\/\/github\.com\/openjdk\//);
    await expect(result).toContainText("3 of 77 advisory cases wrong");
    await expect(result).toContainText("control (broken signer): wrong on 77 of 77");
    await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
    await shots(page, "09-evidence-advisory-check-failed");
    for (const title of ["Advisory check: Badly encoded signature accepted (CVE-2019-14859)",
                         "Advisory check: Malformed signature raises unexpected error (CVE-2019-14853)"]) {
      await expect(evidenceRow(page, title).getByTestId("result-badge").first()).toContainText("Passed");
    }

    // ---- Advisories again: the reviewer's results, with the way to the check and to its evidence
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-result")).toHaveText("Failed");
    await expect(advisoryRow(page, "CVE-2019-14859").getByTestId("advisory-result")).toHaveText("Passed");
    panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByTestId("advisory-here-result")).toHaveText("Failed");
    await expect(panel.getByTestId("advisory-here-row")).toContainText("acme-sign 1.4.2");
    await expect(panel.getByTestId("open-in-checks")).toHaveAttribute("href", /#\/a\/\d+\/checks\?/);
    await expect(panel.getByTestId("see-the-evidence")).toHaveAttribute("href", /#\/a\/\d+\/evidence\?/);
    await expect(panel.getByTestId("advisory-fix-link")).toHaveAttribute("href", /#\/a\/\d+\/fixes\?/);
    await expect(panel.getByTestId("advisory-related")).toContainText("Checks");
    expect(await layoutProblems(page), "Advisories with results, panel open").toEqual([]);
    await shots(page, "10-advisories-results-panel-open");

    // ---- Fixes: the fix template, and why Otto's own change is not offered
    await panel.getByTestId("advisory-fix-link").click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const fix = codeFix(page);
    await expect(fix).toContainText("From a fix template");
    await expect(fix.getByTestId("fix-what")).toContainText(NOT_OFFERED);
    await expect(fix.getByTestId("fix-what")).toContainText("byte for byte");
    await expect(fix.getByTestId("fix-what")).toContainText("The fix template is offered in its place.");
    await expect(fix).not.toContainText("Written by Otto");
    await shots(page, "11-fixes-template-in-ottos-place");

    // ---- Connect demo code: the proof reruns every locked test, the three advisory checks among them
    await fix.getByRole("button", { name: "Connect demo code" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });
    // (the Proof section is folded until it is opened)
    const proof = page.locator('[data-testid="fix-section"][data-section="proof"]');
    if ((await proof.getByRole("button").first().getAttribute("aria-expanded")) !== "true") await proof.getByRole("button").first().click();
    await expect(page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]')).toHaveCount(3);
    for (const row of await page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]').all()) {
      await expect(row.getByTestId("proof-check")).toHaveAttribute("data-ok", "true");
    }
    await shots(page, "12-fixes-proof-with-advisory-checks");

    // ---- The second pack: one more test, and two advisories that have none yet, each with its reason
    await installPack(page, "2026.11.2");
    await expect(page.getByTestId("test-packs").getByTestId("otto-pack-card")).toHaveCount(2);
    await expect(page.getByTestId("test-packs").getByTestId("otto-counts-line")).toContainText("6 advisories and 4 tests");
    await shots(page, "13-settings-two-packs");
    advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    await expect(advisories.getByTestId("add-new-checks")).toHaveText("Add new checks (1)");
    await expect(advisoryRow(page, "CVE-2024-42461").getByTestId("advisory-test")).toHaveText("No test yet");
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "No test yet" });
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(2);
    panel = await openAdvisory(page, "CVE-2024-42461");
    await expect(panel.getByTestId("advisory-no-test")).toContainText("No test yet");
    await expect(panel.getByTestId("advisory-test-block")).toHaveCount(0);
    await expect(panel.getByTestId("advisory-fix")).toContainText("No fix is offered");
    await shots(page, "14-advisory-with-no-test-yet");
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "Any test" });
    await advisories.getByTestId("advisories-search").fill("elliptic");
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await advisories.getByTestId("advisories-search").fill("");
    await advisories.getByTestId("add-new-checks").click();
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(9);
    await card(page, MISSING_ZERO_CHECK).getByRole("button", { name: `Run ${MISSING_ZERO_CHECK}`, exact: true }).click();
    await expect(card(page, MISSING_ZERO_CHECK)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2024-42460").getByTestId("advisory-result")).toHaveText("Passed");
    expect(await layoutProblems(page), "Advisories with two packs, panel closed").toEqual([]);
    await shots(page, "15-advisories-two-packs");

    // ---- Download evidence: Otto's part is inside the signed file, the report shows it, the command checks it
    const { json, report, file } = await downloadEvidence(page);
    const part = json.evidence.otto;
    expect(part.schema).toBe("isogeny.otto-evidence/1");
    expect(part.packs.map((p: any) => p.pack.version)).toEqual(["2026.11.1", "2026.11.2"]);
    expect(part.checks).toHaveLength(4);
    expect(part.ledger.height).toBe(part.ledger.lines.length);
    expect(part.steps.map((s: any) => [s.step, s.source, s.outcome, s.model])).toEqual([["write_fix", "recorded", "refused", null]]);
    expect(report).toContain("Otto: test packs, the ledger and Claude");
    expect(JSON.stringify(json)).not.toMatch(/sk-ant-|api[_-]?key"\s*:/i);
    const good = verify(file, copy.dataDir);
    expect(good.status, `the evidence file should check: ${good.stdout} ${good.stderr}`).toBe(0);
    expect(good.stdout).toMatch(/^Evidence verified/);
    expect(good.stdout).toContain("Test packs: 2 in the file");
    // one changed byte inside Otto's part is caught
    const raw = fs.readFileSync(file);
    const at = raw.indexOf(Buffer.from('"otto"')) + 60;
    raw[at] = raw[at] ^ 0x01;
    const changed = path.join(path.dirname(file), "changed.json");
    fs.writeFileSync(changed, raw);
    const bad = verify(changed, copy.dataDir);
    expect(bad.status).toBe(1);
    expect(bad.stdout).toMatch(/^Evidence NOT verified/);
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. isolated mode: a real library

test("isolated mode: an advisory check fails on a real library, and its fix is the pack's, labelled From Otto", async ({ browser }) => {
  test.setTimeout(20 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 13, "auto");
    test.skip(copy.mode !== "isolated",
              "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    await enterApp(page);
    await ottoOrSkip(page);
    await openFreshAssessment(page, "Otto walk, real libraries");
    const uploaded = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/file" && r.request().method() === "POST");
    await page.getByLabel("Choose a file to import").setInputFiles(REAL_FILE);
    expect((await uploaded).status(), "expected the upload of demo/real-libraries.csv to be accepted").toBe(200);
    await expect(page.getByTestId("claim-row")).toHaveCount(6);
    // Verify runs each library in its own container, so it takes a while before the Verify page opens
    await page.getByRole("button", { name: "Verify claims" }).click();
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible({ timeout: 300_000 });
    await page.getByRole("button", { name: "Continue to checks" }).click();
    await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
    await expect(page.getByTestId("test-card").first()).toBeVisible();
    const assessment = assessmentOf(page);
    const before = await page.getByTestId("test-card").count();

    await installPack(page, "2026.11.1");
    await installPack(page, "2026.11.2");
    const advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    // four tests, each for every signing program in the file that checks ECDSA P-256 signatures
    await expect(advisoryRow(page, "CVE-2024-42460").locator("td").nth(2)).toContainText("elliptic 6.5.6");
    await advisories.getByTestId("add-new-checks").click();
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await stepLink(page, "Checks").click();
    const cards = page.getByTestId("test-card");
    await expect.poll(async () => cards.count()).toBeGreaterThan(before);

    // ---- run the one check on elliptic 6.5.6 (in its own locked-down container)
    const group = page.getByTestId("test-group").filter({ has: page.getByRole("heading", { name: /elliptic 6\.5\.6/ }) });
    const check = group.getByTestId("test-card").filter({ has: page.getByRole("heading", { name: MISSING_ZERO_CHECK, exact: true }) });
    await check.getByRole("button", { name: `Run ${MISSING_ZERO_CHECK}`, exact: true }).click();
    await expect(check).toHaveAttribute("data-status", "done", { timeout: 600_000 });
    await expect(check.getByTestId("result-badge").first()).toContainText("Failed");

    // ---- Advisories: the result here, and the fix the pack carries
    await openAdvisories(page, assessment);
    const panel = await openAdvisory(page, "CVE-2024-42460");
    await expect(panel.getByTestId("advisory-here-row").filter({ hasText: "elliptic 6.5.6" }).getByTestId("advisory-here-result")).toHaveText("Failed");
    await expect(panel.getByTestId("advisory-fix-label")).toHaveText("From Otto");
    await expect(panel.getByTestId("advisory-fix")).toContainText("update elliptic to 6.5.7");
    await shots(page, "16-real-library-advisory-failed");

    // ---- Fixes: Otto's proposed fix for the library, with how it did on public copies. Nothing can be applied here.
    await panel.getByTestId("advisory-fix-link").first().click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const detail = page.getByTestId("detail-panel");
    await expect(detail).toContainText("From Otto");
    await expect(detail).toContainText("update elliptic to 6.5.7 or later");
    await expect(detail.getByRole("button", { name: /Connect demo code|Apply|Merge/ })).toHaveCount(0);
    await shots(page, "17-fixes-from-otto");
  } finally {
    await stopCopy(copy);
  }
});
