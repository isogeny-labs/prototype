// Phase 5c end to end: Otto in Evidence Lab. Three parts, each on a copy of the app of its own (own data folder and
// ports), so the main app the phase walks share is never touched:
//
//  1. Demo mode, the Acme Pay demo file, with the two test packs this repository ships: Settings (Test packs and Live
//     Otto), Check for updates, Install update (its box: Cancel, then Install), the Overview's next step, Advisories
//     (the table at 1440 pixels wide with its panel closed and open, the panel's parts, Add new checks, which runs
//     nothing), the advisory checks on Checks and in Evidence (with the Advisory line of Related), the fix on Fixes
//     (the fix template, with why Otto's own change is not offered) and its proof, the second pack, Download evidence
//     and the verify command, and last the assessment closed (nothing can be added to it any more).
//  2. Isolated mode (skipped with a message when Docker or the test images are not ready): the real libraries file.
//     One advisory check fails on a real library, and its fix is the one the test pack carries, labelled "From Otto".
//  3. A copy started without Otto (its harness folder is an empty one): the app says so calmly, nothing can be added,
//     and everything else works. This part runs on every computer.
//
// Parts 1 and 2 are skipped with a message when Otto is not installed on this computer (./run-demo.sh fetches it, or:
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

/** A picture in the dark and the light look. `view`: only what the window shows (for a box that dims the page behind
 * it). `panel`: the window is made tall enough first for the side panel to show everything in it, then put back. */
async function shots(page: Page, name: string, how: { view?: boolean; panel?: boolean } = {}): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  const size = page.viewportSize();
  if (how.panel && size) {
    const need = await page.evaluate(() => {
      const side = document.querySelector<HTMLElement>("aside[role='complementary']");
      return side ? side.scrollHeight + 48 : 0;
    });
    await page.setViewportSize({ width: size.width, height: Math.max(size.height, Math.min(need, 6000)) });
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: !how.view, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  if (how.panel && size) await page.setViewportSize(size);
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
  await expect(packs.getByTestId("otto-update-line")).toContainText(version);
  await packs.getByTestId("otto-install-update").click();
  const box = page.getByTestId("otto-install-dialog");
  await expect(box).toContainText(version);
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
// A click on something that is not there fails within a minute, not at the end of the whole walk's time.
test.use({ actionTimeout: 60_000 });

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
    await expect(packs.getByTestId("otto-installed-line")).toContainText("No test pack");
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(0);
    await expect(packs.getByTestId("otto-harness-line")).toContainText(/version \S+, commit [0-9a-f]{7}/);
    // where Otto's answers come from, with the day they were recorded, also before any pack is installed
    await expect(packs.getByTestId("otto-answers-line")).toContainText(/recorded during the build, \d{1,2} \w+ 20\d\d/);
    await expect(packs.getByTestId("otto-order-note")).toContainText("never removed");
    const live = page.getByTestId("live-otto");
    await expect(live.getByTestId("live-otto-key-line")).toContainText("No API key");
    await expect(live.getByTestId("live-otto-switch")).toBeDisabled();
    await expect(live.getByTestId("live-otto-switch-reason")).toContainText("only when an API key is present");
    await expect(live.getByTestId("live-otto-limit")).toHaveValue("2.00");
    await expect(live.getByTestId("live-otto-status-line")).toContainText("Live Otto is off");
    await expect(live.getByTestId("live-otto-sent-line")).toContainText("What is sent to Claude");
    // no field anywhere takes a key
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await shots(page, "02-settings-no-pack");

    // ---- Check for updates (the folder on this computer), then Install update: Cancel installs nothing
    await packs.getByTestId("otto-check-updates").click();
    await expect(packs.getByTestId("otto-update-line")).toContainText("2026.11.1");
    await packs.getByTestId("otto-install-update").click();
    const box = page.getByTestId("otto-install-dialog");
    await expect(box).toContainText("2026.11.1");
    await expect(box).toContainText("Nothing in a pack runs");
    await expect(box.getByTestId("otto-install-confirm")).toHaveText("Install");
    await expect(box.getByTestId("otto-install-cancel")).toHaveText("Cancel");
    await shots(page, "03-install-update-box", { view: true });
    await box.getByTestId("otto-install-cancel").click();
    await expect(page.getByTestId("otto-install-dialog")).toHaveCount(0);
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(0);
    await installPack(page, "2026.11.1");
    packs = page.getByTestId("test-packs");
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(1);
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Pack 2026.11.1");
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Isogeny Labs demo pack key");
    await shots(page, "04-settings-pack-installed");

    // ---- Advisories: the three advisories of the pack, two with a test and one without; nothing is in the plan yet
    advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await expect(advisories.getByTestId("advisories-packs-line")).toContainText("2026.11.1");
    await expect(advisories.getByTestId("advisory-test")).toHaveText(["Test ready", "Test ready", "No test yet"]);
    await expect(advisories.getByTestId("add-new-checks")).toHaveText("Add new checks (2)");
    await expect(advisories.getByTestId("add-new-checks-note")).toContainText("It runs nothing.");
    expect(await layoutProblems(page), "Advisories, panel closed").toEqual([]);
    await shots(page, "05-advisories-panel-closed");

    // ---- the panel: the publisher's own line with its link, the test and how it did on public copies, the fix
    let panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByRole("heading", { level: 2, name: RANGE })).toBeVisible();
    // the table drops its Published column beside the panel, so the panel says the day itself
    await expect(panel.getByTestId("advisory-published")).toContainText(/Published \d{1,2} \w+ 20\d\d/);
    await expect(panel.getByTestId("advisory-publisher")).toContainText("rb.signum() == 0");
    await expect(panel.getByTestId("advisory-publisher")).toContainText("quoted from the named source, not a result");
    // Claude's own notes are there, folded, and say what they are
    await expect(panel.getByTestId("advisory-notes")).not.toHaveAttribute("open", "");
    await expect(panel.getByTestId("advisory-notes").locator("summary")).toContainText("notes");
    await expect(panel.getByTestId("advisory-publisher").getByRole("link").first()).toHaveAttribute("href", /^https:\/\/raw\.githubusercontent\.com\/openjdk\/jdk17u\//);
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
    await shots(page, "06-advisories-panel-open", { panel: true });
    // the ledger entries of the research are folded under the test
    await panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger").locator("summary").click();
    await expect(panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger-entry").first()).toBeVisible();
    await shots(page, "07-advisory-ledger-open", { panel: true });
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();

    // ---- Add new checks: two tests join the plan, and nothing runs
    const added = page.waitForResponse((r) => /\/api\/plans\/\d+\/advisories\/add$/.test(r.url()) && r.request().method() === "POST");
    await advisories.getByTestId("add-new-checks").click();
    expect((await added).status()).toBe(200);
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await expect(advisories.getByTestId("add-new-checks-reason")).toContainText("already in the test plan");
    await expect(advisories.getByTestId("advisory-result")).toHaveText(["Not run yet", "Not run yet", "No check"]);
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(7);
    await expect(card(page, RANGE_CHECK)).toHaveAttribute("data-status", "not_run");
    // the card says which advisory it came from, with the way to it
    await expect(card(page, RANGE_CHECK).getByTestId("card-advisory")).toContainText("CVE-2022-21449");
    await expect(card(page, RANGE_CHECK).getByTestId("card-advisory")).toHaveAttribute("href", /#\/a\/\d+\/advisories\?item=CVE-2022-21449$/);
    await expect(page.getByTestId("card-advisory")).toHaveCount(2);
    expect((await cardStatuses(page)).filter((s) => s === "done")).toEqual([]);
    await shots(page, "08-checks-advisory-checks-added");

    // ---- Run all: the check for the range advisory fails on acme-sign 1.4.2, the other one passes
    await runAllAndWait(page, 7);

    await stepLink(page, "Evidence").click();
    let result = await openResult(page, RANGE_CHECK);
    await expect(result.getByTestId("result-badge").first()).toContainText("Failed");
    await expect(result.getByTestId("advisories")).toContainText("CVE-2022-21449");
    await expect(result.getByTestId("advisories")).toContainText("quoted from the named source, not a result");
    await expect(result.getByTestId("advisories").getByRole("link").first()).toHaveAttribute("href", /^https:\/\/raw\.githubusercontent\.com\/openjdk\/jdk17u\//);
    await expect(result).toContainText("3 of 77 advisory cases wrong");
    await expect(result).toContainText("control (broken signer): wrong on 77 of 77");
    await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
    // the result's Related block has the Advisory line, and it leads to the advisory
    const toAdvisory = page.getByTestId("detail-panel")
      .locator('[data-testid="related-line"][data-kind="advisory"] [data-testid="related-link"]');
    await expect(toAdvisory).toHaveCount(1);
    await expect(toAdvisory).toHaveAttribute("href", /#\/a\/\d+\/advisories\?item=CVE-2022-21449$/);
    expect(await layoutProblems(page), "Evidence, an advisory check's result open").toEqual([]);
    await shots(page, "09-evidence-advisory-check-failed", { panel: true });
    await expect(evidenceRow(page, "Advisory check: Badly encoded signature accepted (CVE-2019-14859)").getByTestId("result-badge").first())
      .toContainText("Passed");

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
    await shots(page, "10-advisories-results-panel-open", { panel: true });

    // ---- Fixes: the fix template, and why Otto's own change is not offered
    await panel.getByTestId("advisory-fix-link").click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const fix = codeFix(page);
    await expect(fix).toContainText("From a fix template");
    await expect(fix.getByTestId("fix-what")).toContainText(NOT_OFFERED);
    await expect(fix.getByTestId("fix-what")).toContainText("byte for byte");
    await expect(fix.getByTestId("fix-what")).toContainText("The fix template is offered in its place.");
    await expect(fix).not.toContainText("Written by Otto");
    await shots(page, "11-fixes-template-in-ottos-place", { panel: true });

    // ---- Connect demo code: the proof reruns every locked test, the two advisory checks among them
    await fix.getByRole("button", { name: "Connect demo code" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });
    // (the Proof section is folded until it is opened)
    const proof = page.locator('[data-testid="fix-section"][data-section="proof"]');
    if ((await proof.getByRole("button").first().getAttribute("aria-expanded")) !== "true") await proof.getByRole("button").first().click();
    await expect(page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]')).toHaveCount(2);
    for (const row of await page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]').all()) {
      await expect(row.getByTestId("proof-check")).toHaveAttribute("data-ok", "true");
    }
    // in the side panel the proof's four columns have no room side by side: each cell sits under the last, none over another
    const cells = await page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]').first()
      .locator('[data-testid="proof-cell-before"], [data-testid="proof-cell-proof"]').evaluateAll((all) =>
        all.map((c) => c.getBoundingClientRect()).map((r) => ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom })));
    expect(cells).toHaveLength(2);
    expect(cells[0].right <= cells[1].left + 1 || cells[0].bottom <= cells[1].top + 1, "the two result cells do not overlap").toBe(true);
    expect(await layoutProblems(page), "Fixes, the proof open in the panel").toEqual([]);
    await shots(page, "12-fixes-proof-with-advisory-checks", { panel: true });

    // ---- The second pack: one more test, and two more advisories that have none yet, each with its reason
    await installPack(page, "2026.11.2");
    await expect(page.getByTestId("test-packs").getByTestId("otto-pack-card")).toHaveCount(2);
    await expect(page.getByTestId("test-packs").getByTestId("otto-counts-line")).toContainText("6 advisories and 3 tests");
    await shots(page, "13-settings-two-packs");

    // ---- the Overview's next step: a new check is ready to add, and its button only opens Advisories
    await page.goto(`/#/a/${assessment}/overview`);
    const next = page.getByTestId("next-step");
    await expect(next).toContainText("1 new advisory check");
    await expect(next).toContainText("runs nothing");
    await shots(page, "14-overview-next-step");
    await next.getByRole("button", { name: "Open advisories" }).click();
    await expect(page).toHaveURL(/#\/a\/\d+\/advisories$/);
    advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    await expect(advisories.getByTestId("add-new-checks")).toHaveText("Add new checks (1)");
    await expect(advisoryRow(page, "CVE-2024-42461").getByTestId("advisory-test")).toHaveText("No test yet");
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "No test yet" });
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    // one of them has no test because its design only repeated another advisory's check, and the page says so
    const twin = await openAdvisory(page, "CVE-2019-14853");
    await expect(twin.getByTestId("advisory-no-test")).toContainText("the same check under a second name");
    await expect(twin.getByTestId("advisory-fix")).toContainText("No fix is offered");
    await shots(page, "15-advisory-no-test-same-check", { panel: true });
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
    panel = await openAdvisory(page, "CVE-2024-42461");
    await expect(panel.getByTestId("advisory-no-test")).toContainText("No test yet");
    await expect(panel.getByTestId("advisory-test-block")).toHaveCount(0);
    await expect(panel.getByTestId("advisory-fix")).toContainText("No fix is offered");
    await shots(page, "16-advisory-with-no-test-yet", { panel: true });
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "Any test" });
    await advisories.getByTestId("advisories-search").fill("elliptic");
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await advisories.getByTestId("advisories-search").fill("");
    await advisories.getByTestId("add-new-checks").click();
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(8);
    await card(page, MISSING_ZERO_CHECK).getByRole("button", { name: `Run ${MISSING_ZERO_CHECK}`, exact: true }).click();
    await expect(card(page, MISSING_ZERO_CHECK)).toHaveAttribute("data-status", "done", { timeout: 120_000 });
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2024-42460").getByTestId("advisory-result")).toHaveText("Passed");
    expect(await layoutProblems(page), "Advisories with two packs, panel closed").toEqual([]);
    await shots(page, "17-advisories-two-packs");

    // ---- Download evidence: Otto's part is inside the signed file, the report shows it, the command checks it
    const { json, report, file } = await downloadEvidence(page);
    const part = json.evidence.otto;
    expect(part.schema).toBe("isogeny.otto-evidence/1");
    expect(part.packs.map((p: any) => p.pack.version)).toEqual(["2026.11.1", "2026.11.2"]);
    expect(part.checks).toHaveLength(3);
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

    // ---- Close the assessment (a sign-off with a name): Advisories stays readable, and nothing can be added to it
    await page.goto(`/#/a/${assessment}/overview`);
    await page.getByRole("button", { name: "Close assessment" }).click();
    const close = page.getByTestId("close-box");
    await close.getByLabel("Signed off by").fill("Demo reviewer");
    await close.getByRole("button", { name: "Close and sign off" }).click();
    await expect(page.getByTestId("assessment-status")).toHaveText(/Closed/);
    advisories = await openAdvisories(page, assessment);
    await expect(page.getByTestId("closed-banner")).toBeVisible();
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    await expect(advisories.getByTestId("advisories-packs-line")).toContainText("when this assessment was closed");
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await expect(advisories.getByTestId("add-new-checks-reason")).toContainText("closed");
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-result")).toHaveText("Failed");   // as it was signed off
    await shots(page, "18-advisories-closed-assessment");
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
    // three tests, each for every signing program in the file that checks ECDSA P-256 signatures
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
    // the other three libraries have not run this check: the row says so, and does not count them as results
    await expect(advisoryRow(page, "CVE-2024-42460")).toContainText("with no result yet");
    // a file of real libraries has no code of the customer's own, so the panel says nothing about a change for it
    await expect(panel.getByTestId("advisory-fix")).not.toContainText("your own code");
    expect(await layoutProblems(page), "Advisories on the real libraries file, panel open").toEqual([]);
    await shots(page, "19-real-library-advisory-failed", { panel: true });

    // ---- Fixes: Otto's proposed fix for the library, with how it did on public copies. Nothing can be applied here.
    await panel.getByTestId("advisory-fix-link").first().click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const detail = page.getByTestId("detail-panel");
    await expect(detail).toContainText("From Otto");
    await expect(detail).toContainText("update elliptic to 6.5.7 or later");
    await expect(detail.getByRole("button", { name: /Connect demo code|Apply|Merge/ })).toHaveCount(0);
    expect(await layoutProblems(page), "Fixes on the real libraries file, panel open").toEqual([]);
    await shots(page, "20-fixes-from-otto", { panel: true });
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 3. a computer without Otto

test("without Otto: the app says so, nothing can be added, and the rest works as before", async ({ browser }) => {
  test.setTimeout(10 * 60_000);
  let copy: Copy | null = null;
  // an empty folder in the harness's place: on this copy of the app, Otto has not been fetched
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-no-otto-"));
  try {
    copy = await startCopy(browser, 14, "demo", { EVIDENCE_LAB_OTTO_HOME: empty });
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    expect(otto.harness.installed, "this copy is started with an empty harness folder").toBe(false);
    await openFreshAssessment(page, "Otto walk, no Otto");
    await importVerifyAndOpenTests(page);
    const assessment = assessmentOf(page);

    // ---- Settings says it with the reason, and a pack can still be installed (a pack is data; nothing in it runs)
    const packs = await openSettings(page);
    await expect(packs.getByTestId("otto-harness-line")).toContainText("Otto is not installed on this computer");
    await expect(packs.getByTestId("otto-harness-line")).toContainText("./run-demo.sh");
    await installPack(page, "2026.11.1");
    await shots(page, "21-settings-otto-not-installed");

    // ---- Advisories lists the pack's advisories to read, and Add new checks is off with the reason
    const advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await expect(advisories.getByTestId("advisories-otto-line")).toContainText("Otto is not installed on this computer");
    await expect(advisories.getByTestId("add-new-checks")).toBeDisabled();
    await expect(advisories.getByTestId("add-new-checks-reason")).toContainText("not installed");
    expect(await layoutProblems(page), "Advisories without Otto").toEqual([]);
    await shots(page, "22-advisories-otto-not-installed");
    // the Overview does not send anyone to checks that can't be added
    await page.goto(`/#/a/${assessment}/overview`);
    await expect(page.getByTestId("next-step")).not.toContainText("advisory check");

    // ---- everything else works as before: the plan's own tests run and get their results
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(5);
    await page.getByRole("button", { name: "Run all" }).click();
    await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(5).fill("done"));
    expect(empty && fs.readdirSync(empty), "looking at the app fetched nothing").toEqual([]);
  } finally {
    await stopCopy(copy);
    fs.rmSync(empty, { recursive: true, force: true });
  }
});
