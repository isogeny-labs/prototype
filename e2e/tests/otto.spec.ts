// Phase 5c end to end: Otto proposes, a person decides. Three parts, each on a copy of the app of its own (own data
// folder and ports), so the main app the phase walks share is never touched:
//
//  1. Demo mode, the Acme Pay demo file: the success flow of 18 November 2026, start to finish, with a picture of
//     every tab at each stage, in the dark and the light look.
//       1  a test pack is installed, a file is brought in: Import says how many checks may apply, nothing runs
//       2  Otto's proposed checks are decided one by one: one accepted (undone, accepted again), one rejected with a
//          reason; nothing has run
//       3  the accepted check is run with the plan's own tests: the runner and the reviewer decide; one fails
//       4  Otto's proposed fix (its own change): Connect demo code is off until the proposal is accepted; then the
//          proof on a test copy, the pull request, the approval and the merge
//       5  Otto's proposed change to the migration plan is accepted; the dependency list is added, and of Otto's two
//          proposed updates one is accepted and one rejected with a reason
//       6  Retest now: the same locked check passes on the merged code, and the accepted plan change reads done
//       7  a new test pack arrives and proposes a new check and a new update; the rejected check is reconsidered
//       8  Download evidence: the file verifies with every decision in it; then the assessment is closed
//  2. Isolated mode (skipped with a message when Docker or the test images are not ready): a file that names one real
//     library, elliptic 6.5.6. Its advisory check fails; Otto's proposed fix is the pack's update, with the two proof
//     rows; once it is accepted and a retest has run on 6.5.7, the second row reads "Passed" with its date.
//  3. A copy started without Otto (its harness folder is an empty one): the app says so calmly, nothing can be
//     decided, and everything else works (the fix template is offered as before). Runs on every computer.
//
// Parts 1 and 2 are skipped with a message when Otto is not installed on this computer (./run-demo.sh fetches it, or:
// cd backend && .venv/bin/python -m app.prepare --otto). The answers are the ones recorded during the build: a copy
// of the app is started without any API key, so nothing here can reach Claude.
// Main-screen buttons only. Screenshots (dark and light) go to docs/screenshots/phase5c/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND, DISCLAIMER, PYTHON, REPO, continueToChecks, enterApp, evidenceRow, importVerifyAndOpenTests, layoutProblems, openFreshAssessment,
  openResult, screenshotFolder, startCopy, stepLink, stopCopy, type Copy,
} from "./shared";

const SHOTS = screenshotFolder("phase5c");
const DEPENDENCIES_FILE = path.join(REPO, "demo/dependencies-demo.cdx.json");
const RANGE = "Missing ECDSA signature range check";
const RANGE_CHECK = `Advisory check: ${RANGE} (CVE-2022-21449)`;
const ENCODED_CHECK = "Advisory check: Badly encoded signature accepted (CVE-2019-14859)";
const MISSING_ZERO_CHECK = "Advisory check: Wrongly encoded signature accepted (CVE-2024-42460)";
const REASON = "Not this quarter";
const JAVA_REASON = "Java moves with the platform team";
const ONE_LOGIN = "This version has one login";

// How many of the page's own requests to the app are still unanswered (a page reads its data after it is opened).
const unanswered = new WeakMap<Page, number>();

function watchRequests(page: Page): void {
  unanswered.set(page, 0);
  const toApp = (r: Request) => new URL(r.url()).pathname.startsWith("/api/");
  const done = (r: Request) => {
    if (toApp(r)) unanswered.set(page, Math.max(0, (unanswered.get(page) ?? 0) - 1));
  };
  page.on("request", (r) => {
    if (toApp(r)) unanswered.set(page, (unanswered.get(page) ?? 0) + 1);
  });
  page.on("requestfinished", done);
  page.on("requestfailed", done);
}

/** Waits until the page has what it asked for and has stopped changing: no request to the app unanswered, and the
 * same height and the same number of parts on two looks in a row. A picture taken before that would show half a page. */
async function settled(page: Page): Promise<void> {
  let last = "";
  await expect
    .poll(async () => {
      const now = await page.evaluate(() => `${document.documentElement.scrollHeight}/${document.querySelectorAll("main *, aside *").length}`);
      const same = now === last && (unanswered.get(page) ?? 0) === 0;
      last = now;
      return same;
    }, { timeout: 30_000, intervals: [250] })
    .toBe(true);
}

/** A picture in the dark and the light look. `view`: only what the window shows (for a box that dims the page behind
 * it). `panel`: the window is made tall enough first for the side panel to show everything in it, then put back.
 * Every picture has one point for each point of the page (1440 wide): this walk takes some 250 of them, and at the
 * sharper form the other walks use they would weigh four times as much. */
async function shots(page: Page, name: string, how: { view?: boolean; panel?: boolean } = {}): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await settled(page);
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
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: !how.view, animations: "disabled", scale: "css" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  if (how.panel && size) await page.setViewportSize(size);
}

/** Every tab of the app, in the sidebar's order: where it is, and what shows that it has loaded. */
const TABS: Array<{ key: string; url: (assessment: string, project: string) => string; ready: (page: Page) => Locator }> = [
  { key: "overview", url: (a) => `/#/a/${a}/overview`, ready: (p) => p.getByTestId("overview-waiting") },
  { key: "project-overview", url: (_a, project) => `/#/p/${project}`, ready: (p) => p.getByTestId("project-otto") },
  { key: "import", url: (a) => `/#/a/${a}/inventory/import`, ready: (p) => p.getByTestId("import-otto") },
  { key: "verify", url: (a) => `/#/a/${a}/inventory/verify`, ready: (p) => p.getByTestId("result-row").first() },
  { key: "advisories", url: (a) => `/#/a/${a}/advisories`, ready: (p) => p.getByTestId("advisory-row").first() },
  { key: "checks", url: (a) => `/#/a/${a}/checks`, ready: (p) => p.getByTestId("test-card").last() },
  { key: "evidence", url: (a) => `/#/a/${a}/evidence`, ready: (p) => p.getByTestId("evidence-row").first() },
  { key: "fixes", url: (a) => `/#/a/${a}/fixes`, ready: (p) => p.getByTestId("fix-list").or(p.getByTestId("fixes-empty")) },
  { key: "migration-systems", url: (a) => `/#/a/${a}/migration/systems`, ready: (p) => p.getByTestId("system-card").first() },
  { key: "migration-roadmap", url: (a) => `/#/a/${a}/migration/roadmap`, ready: (p) => p.getByTestId("roadmap-row").first() },
  { key: "migration-dependencies", url: (a) => `/#/a/${a}/migration/dependencies`, ready: (p) => p.getByTestId("dependencies-view") },
  { key: "settings", url: () => "/#/settings?section=test-packs", ready: (p) => p.getByTestId("live-otto") },
];

/** One stage of the flow: every tab is opened, measured at 1440 pixels wide, and photographed in both looks. Opening a
 * tab runs nothing: the count of test runs is the same after the tour as before it. */
async function tour(page: Page, stage: string, assessment: string, project: string): Promise<void> {
  const before = await runCount(page, assessment);
  for (const [n, tab] of TABS.entries()) {
    await page.goto(tab.url(assessment, project));
    await expect(tab.ready(page).first(), `${stage}: ${tab.key}`).toBeVisible({ timeout: 30_000 });
    await settled(page);
    expect(await layoutProblems(page), `${stage}: ${tab.key}`).toEqual([]);
    await shots(page, `${stage}-${String(n + 1).padStart(2, "0")}-${tab.key}`);
  }
  expect(await runCount(page, assessment), `${stage}: looking at every tab ran nothing`).toBe(before);
  // back in the assessment (the last tab was Settings, which belongs to none)
  await page.goto(`/#/a/${assessment}/overview`);
  await expect(page.getByTestId("overview-waiting")).toBeVisible();
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

/** The project the open assessment belongs to. */
async function projectOf(page: Page, assessment: string): Promise<string> {
  const view = await (await page.request.get(`/api/assessments/${assessment}`)).json();
  if (typeof view.project?.id !== "number") throw new Error(`no project for assessment ${assessment}`);
  return String(view.project.id);
}

/** How many runs the assessment's tests have (the test plan, its retests and its fix proofs), as Checks counts them:
 * read from the app, to show that a step ran nothing. */
async function runCount(page: Page, assessment: string): Promise<number> {
  const view = await (await page.request.get(`/api/assessments/${assessment}`)).json();
  if (typeof view.plan_id !== "number") return 0;
  const checks = await (await page.request.get(`/api/plans/${view.plan_id}/checks`)).json();
  return (checks.groups as any[]).filter((g) => g.key === "encryption").flatMap((g) => g.rows as any[])
    .reduce((sum, row) => sum + (row.runs ?? 0), 0);
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

async function closePanel(page: Page): Promise<void> {
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  await expect(page.getByTestId("detail-panel")).toHaveCount(0);
}

/** One decision on one of Otto's proposals: the one button is pressed, and the one request it sends is awaited. */
async function decide(page: Page, card: Locator, decision: "accept" | "undo" | "reconsider"): Promise<void> {
  const sent = page.waitForResponse((r) => new RegExp(`/api/plans/\\d+/otto/proposals/[^/]+/${decision}$`).test(new URL(r.url()).pathname)
                                           && r.request().method() === "POST");
  await card.getByTestId(`proposal-${decision}`).click();
  expect((await sent).status(), `the ${decision} was recorded`).toBe(200);
}

/** Reject, in its small box, with a short reason. */
async function reject(page: Page, card: Locator, reason: string): Promise<void> {
  await card.getByTestId("proposal-reject").click();
  const box = page.getByTestId("proposal-reject-dialog");
  await expect(box).toContainText("It is not deleted");
  await box.getByTestId("proposal-reject-reason").fill(reason);
  const sent = page.waitForResponse((r) => /\/api\/plans\/\d+\/otto\/proposals\/[^/]+\/reject$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await box.getByTestId("proposal-reject-confirm").click();
  expect((await sent).status(), "the rejection was recorded").toBe(200);
  await expect(page.getByTestId("proposal-reject-dialog")).toHaveCount(0);
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

async function runOne(page: Page, title: string, timeout = 120_000): Promise<void> {
  await stepLink(page, "Checks").click();
  await card(page, title).getByRole("button", { name: `Run ${title}`, exact: true }).click();
  await expect(card(page, title)).toHaveAttribute("data-status", "done", { timeout });
}

/** Fixes, with the fix that carries one of Otto's proposals open in the panel. */
async function openOttosFix(page: Page, assessment: string): Promise<Locator> {
  await page.goto(`/#/a/${assessment}/fixes`);
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  const row = page.getByTestId("fix-row").filter({ has: page.getByTestId("fix-proposal-mark") }).first();
  await expect(row).toBeVisible();
  const summary = page.getByTestId("fix-summary");
  if ((await summary.getByTestId("fix-proposal").count()) === 0) await row.click();
  await expect(summary.getByTestId("fix-proposal")).toBeVisible();
  return summary;
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

// ---------------------------------------------------------------- 1. demo mode: the success flow on the Acme Pay demo

test("demo mode, the success flow: Otto proposes, a person decides; run, fix, plan, dependencies, a new pack, evidence", async ({ browser }) => {
  test.setTimeout(40 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 7, "demo");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await ottoOrSkip(page);
    expect(otto.live.key_present, "a copy of the app is started without an API key").toBe(false);

    // ================================================================ before anything: Settings, with no pack and no key
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
    await shots(page, "0-01-settings-no-pack");

    // ---- Check for updates (the folder on this computer), then Install update: Cancel installs nothing
    await packs.getByTestId("otto-check-updates").click();
    await expect(packs.getByTestId("otto-update-line")).toContainText("2026.11.1");
    await packs.getByTestId("otto-install-update").click();
    const box = page.getByTestId("otto-install-dialog");
    await expect(box).toContainText("2026.11.1");
    await expect(box).toContainText("Nothing in a pack runs");
    await expect(box).toContainText("Otto proposes its checks on the Advisories page, and you accept or reject each one.");
    await expect(box.getByTestId("otto-install-confirm")).toHaveText("Install");
    await expect(box.getByTestId("otto-install-cancel")).toHaveText("Cancel");
    await shots(page, "0-02-install-update-box", { view: true });
    await box.getByTestId("otto-install-cancel").click();
    await expect(page.getByTestId("otto-install-dialog")).toHaveCount(0);
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(0);
    await installPack(page, "2026.11.1");
    packs = page.getByTestId("test-packs");
    await expect(packs.getByTestId("otto-pack-card")).toHaveCount(1);
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Pack 2026.11.1");
    await expect(packs.getByTestId("otto-pack-card")).toContainText("Isogeny Labs demo pack key");

    // ================================================================ 1. bring in an inventory: Otto reads it and proposes
    await openFreshAssessment(page, "Otto walk");
    // Import, as soon as the file is in: how many checks may apply, with the way to Advisories. Nothing has run.
    const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST");
    await page.getByRole("button", { name: "Use demo file" }).click();
    expect((await imported).status()).toBe(200);
    const found = page.getByTestId("import-otto");
    await expect(found).toHaveAttribute("data-count", "2");
    await expect(found.getByTestId("import-otto-text")).toHaveText("Otto found 2 checks that may apply: 2 published weaknesses with a test, for acme-sign 1.4.2.");
    await expect(found.getByTestId("import-otto-note")).toContainText("Nothing runs on import.");
    await expect(found).toContainText("From Otto");
    await expect(found.getByRole("link", { name: "Open Advisories" })).toHaveAttribute("href", /#\/a\/\d+\/advisories$/);
    await shots(page, "1-00-import-otto-found-checks");
    // Verify the claims as before (this file names our own demo server, so "I own this system" is ticked first)
    await expect(page.getByTestId("claim-row")).toHaveCount(3);
    await page.getByTestId("address-confirm").click();
    await page.getByRole("button", { name: "Verify claims" }).click();
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
    await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
    // Verify: one sentence says that Otto proposes nothing here yet
    await expect(page.getByTestId("verify-otto-note")).toContainText("Otto has no proposals here yet.");
    await continueToChecks(page);
    const assessment = assessmentOf(page);
    const project = await projectOf(page, assessment);
    expect(await runCount(page, assessment), "bringing a file in and reading Otto's proposals ran no test").toBe(0);

    // ---- Migration: where each system stands is measured (Measure status), as before this phase. It is a person's
    // click. A measured status gives each system its place on the plan, which a plan change of Otto's needs later.
    await page.goto(`/#/a/${assessment}/migration/systems`);
    await page.getByRole("button", { name: "Measure status" }).click();
    await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 180_000 });
    await expect(page.getByTestId("system-otto-mark")).toHaveCount(0);        // nothing has failed: no plan change is proposed
    expect(await runCount(page, assessment), "measuring the migration status ran no test of the test plan").toBe(0);

    // the Overview: "Waiting for you" counts the two proposed checks, with the way to where they are decided
    await page.goto(`/#/a/${assessment}/overview`);
    let waiting = page.getByTestId("overview-waiting");
    await expect(waiting).toHaveAttribute("data-total", "2");
    await expect(waiting.getByTestId("waiting-line")).toHaveText("2 proposals from Otto wait for your decision.");
    // the next step names them before the first run: a check accepted now runs with the suggested tests
    await expect(page.getByTestId("next-step")).toContainText("Otto proposes 2 advisory checks from the installed test packs.");
    await expect(waiting.locator('[data-testid="waiting-item"][data-kind="check"]')).toHaveText("2 proposed checks");
    await expect(waiting.getByTestId("waiting-link")).toHaveAttribute("href", /#\/a\/\d+\/advisories$/);
    await expect(waiting.getByTestId("waiting-note")).toContainText("Otto proposes; a person decides.");

    // Advisories: the three advisories of the pack; two have a test, and each of those is a proposal waiting
    let advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await expect(advisories.getByTestId("advisories-packs-line")).toContainText("2026.11.1");
    await expect(advisories.getByTestId("advisory-test")).toHaveText(["Test ready", "Test ready", "No test yet"]);
    await expect(advisories.getByTestId("advisory-proposal")).toHaveText(["Proposed", "Proposed", "Nothing proposed"]);
    await expect(advisories.getByTestId("advisories-waiting")).toHaveAttribute("data-count", "2");
    await expect(page.getByRole("button", { name: /Add new checks/ })).toHaveCount(0);       // no button decides several at once
    expect(await layoutProblems(page), "Advisories, panel closed").toEqual([]);

    // ---- the panel: what it is (plain words, the publisher's own line and link), the test, the trial, the proposal
    let panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByRole("heading", { level: 2, name: RANGE })).toBeVisible();
    await expect(panel.getByTestId("advisory-published")).toContainText(/Published \d{1,2} \w+ 20\d\d/);
    await expect(panel.getByTestId("advisory-publisher")).toContainText("rb.signum() == 0");
    await expect(panel.getByTestId("advisory-publisher")).toContainText("quoted from the named source, not a result");
    await expect(panel.getByTestId("advisory-publisher").getByRole("link").first()).toHaveAttribute("href", /^https:\/\/raw\.githubusercontent\.com\/openjdk\/jdk17u\//);
    await expect(panel.getByTestId("advisory-notes")).not.toHaveAttribute("open", "");
    const block = panel.getByTestId("advisory-test-block");
    await expect(block).toContainText("77 published cases");
    await expect(block).toContainText("accepts every signature");                 // the control that must fail
    await expect(block).toContainText("Passed only if every answer is right");    // the pass rule
    await expect(panel.getByTestId("advisory-trial").first()).toContainText("openjdk 17.0.2");
    await expect(panel.getByTestId("advisory-fix-label")).toHaveText("From Otto");
    await expect(panel.getByTestId("advisory-fix")).toContainText("The test pack carries a fix for openjdk, the library this advisory is about: update it to 17.0.3 or later.");
    await expect(panel.getByTestId("advisory-fix")).toContainText(
      "Proven on public copies: Not proven. 17.0.2 fails the advisory check and 17.0.3 passes it, but another locked test still fails on 17.0.3.");
    await expect(panel.getByTestId("advisory-fix")).toContainText("it is a proposal, with Accept and Reject, only where it applies");
    await expect(panel.getByTestId("advisory-fix")).not.toContainText("Otto proposes:");
    await expect(panel.getByTestId("advisory-claude")).toContainText("Recorded during the build");
    let proposal = panel.locator('[data-testid="advisory-here-row"][data-program="acme-sign 1.4.2"]').getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-label")).toHaveText("From Otto");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await expect(proposal.getByTestId("proposal-why")).toContainText("Why it applies");
    await expect(proposal.getByTestId("proposal-why")).toContainText("acme-sign 1.4.2 checks ECDSA P-256 signatures");
    await expect(proposal.getByTestId("proposal-lines")).toContainText("Control that must fail");
    await expect(proposal.getByTestId("proposal-decided")).toHaveText("Nobody has decided this yet.");
    await expect(proposal.getByTestId("proposal-note")).toContainText("It runs nothing.");
    await expect(proposal.getByRole("button")).toHaveText(["Accept", "Reject"]);
    expect(await layoutProblems(page), "Advisories, panel open on a proposal").toEqual([]);
    await shots(page, "1-00-advisory-proposal-waiting", { panel: true });
    // the ledger entries of the research are folded under the test
    await panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger").locator("summary").click();
    await expect(panel.getByTestId("advisory-test-block").getByTestId("advisory-ledger-entry").first()).toBeVisible();
    await closePanel(page);
    await tour(page, "1-inventory", assessment, project);

    // ================================================================ 2. each proposed check is decided by itself
    advisories = await openAdvisories(page, assessment);
    panel = await openAdvisory(page, "CVE-2022-21449");
    proposal = panel.getByTestId("otto-proposal");
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");
    await expect(proposal.getByTestId("proposal-decided")).toContainText(/^Accepted by You on \d{1,2} \w+ 20\d\d, \d\d:\d\d UTC\.$/);
    await expect(proposal.getByTestId("proposal-effect")).toHaveText("It is in the test plan, on Checks. It has not run yet.");
    await expect(proposal.getByRole("button")).toHaveText(["Undo"]);
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-proposal")).toHaveText("Added");
    // Undo, until it has run: the check leaves the test plan again, and the decision stays on the record
    await decide(page, proposal, "undo");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await expect(proposal.getByTestId("proposal-decided")).toContainText("Accept undone by You on");
    await expect(proposal.getByTestId("proposal-decided")).toContainText("It is open for a decision again.");
    await expect(proposal.getByRole("button")).toHaveText(["Accept", "Reject"]);
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");
    await proposal.getByTestId("proposal-history").locator("summary").first().click();
    await expect(proposal.getByTestId("proposal-decision")).toHaveText([
      /^1\. Accepted by You on .+ UTC\.$/, /^2\. Accept undone by You on .+ UTC\.$/, /^3\. Accepted by You on .+ UTC\.$/]);
    await expect(proposal.getByTestId("proposal-history")).toContainText(ONE_LOGIN);
    await shots(page, "2-00-advisory-accepted-with-its-decisions", { panel: true });
    await closePanel(page);

    // Reject, with a short reason: nothing is deleted; the proposal reads "Not added (reason)"
    panel = await openAdvisory(page, "CVE-2019-14859");
    proposal = panel.getByTestId("otto-proposal");
    await proposal.getByTestId("proposal-reject").click();
    const rejectBox = page.getByTestId("proposal-reject-dialog");
    await expect(rejectBox).toContainText("Reject this proposal?");
    await expect(rejectBox).toContainText("It is not deleted");
    await expect(rejectBox.getByTestId("proposal-reject-confirm")).toHaveText("Reject");
    await expect(rejectBox.getByTestId("proposal-reject-cancel")).toHaveText("Cancel");
    await rejectBox.getByTestId("proposal-reject-reason").fill(REASON);
    await shots(page, "2-00-reject-box-with-a-reason", { view: true });
    // Cancel records nothing
    await rejectBox.getByTestId("proposal-reject-cancel").click();
    await expect(page.getByTestId("proposal-reject-dialog")).toHaveCount(0);
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await reject(page, proposal, REASON);
    await expect(proposal.getByTestId("proposal-status")).toHaveText(`Not added (${REASON})`);
    await expect(proposal.getByTestId("proposal-decided")).toContainText(`Reason: ${REASON}`);
    await expect(proposal.getByRole("button")).toHaveText(["Reconsider"]);
    await expect(advisoryRow(page, "CVE-2019-14859").getByTestId("advisory-proposal")).toHaveText(`Not added (${REASON})`);
    await shots(page, "2-00-advisory-rejected-not-added-with-reason", { panel: true });
    await closePanel(page);
    await expect(advisories.getByTestId("advisory-proposal")).toHaveText(["Added", `Not added (${REASON})`, "Nothing proposed"]);
    await expect(advisories.getByTestId("advisory-result")).toHaveText(["Not run yet", "Not in the test plan", "No check"]);
    await expect(advisories.getByTestId("advisories-waiting")).toHaveAttribute("data-count", "0");
    // the Decision filter
    await advisories.getByTestId("advisories-filter-decision").selectOption({ label: "Not added" });
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(1);
    await expect(advisoryRow(page, "CVE-2019-14859")).toBeVisible();
    await advisories.getByTestId("advisories-filter-decision").selectOption({ index: 0 });
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    expect(await layoutProblems(page), "Advisories with decisions, panel closed").toEqual([]);

    // Checks: the accepted check is in the test plan, marked "From Otto", with its advisory; and nothing has run
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(6);
    await expect(card(page, RANGE_CHECK)).toHaveAttribute("data-status", "not_run");
    await expect(card(page, RANGE_CHECK).getByTestId("card-from-otto")).toHaveText("From Otto");
    await expect(card(page, RANGE_CHECK).getByTestId("card-advisory")).toContainText("CVE-2022-21449");
    await expect(card(page, RANGE_CHECK).getByTestId("card-advisory")).toHaveAttribute("href", /#\/a\/\d+\/advisories\?item=CVE-2022-21449$/);
    await expect(page.getByTestId("card-from-otto")).toHaveCount(1);
    await expect(card(page, ENCODED_CHECK)).toHaveCount(0);                      // the rejected one is not in the plan
    // it has no × of its own: Undo on Advisories takes it out, until it has run
    await expect(card(page, RANGE_CHECK).getByTestId("remove-blocked")).toContainText("Undo on Advisories");
    expect((await cardStatuses(page)).filter((s) => s === "done")).toEqual([]);
    expect(await runCount(page, assessment), "five decisions were recorded and no test ran").toBe(0);
    await tour(page, "2-decided", assessment, project);

    // ================================================================ 3. run: the runner and the reviewer decide
    await runAllAndWait(page, 6);
    await stepLink(page, "Evidence").click();
    let result = await openResult(page, RANGE_CHECK);
    await expect(result.getByTestId("result-badge").first()).toContainText("Failed");
    await expect(result.getByTestId("advisories")).toContainText("CVE-2022-21449");
    await expect(result.getByTestId("advisories")).toContainText("quoted from the named source, not a result");
    await expect(result).toContainText("3 of 77 advisory cases wrong");
    await expect(result).toContainText("control (broken signer): wrong on 77 of 77");
    await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
    // where the check came from: the advisory, the design, the trial on public copies, every decision, the ledger
    const origin = result.getByTestId("result-otto");
    await expect(origin.getByTestId("result-otto-label")).toHaveText("From Otto");
    await expect(origin.getByTestId("result-otto-line")).toContainText("in test pack 2026.11.1.");
    await expect(origin.getByTestId("result-otto-advisory")).toHaveAttribute("href", /#\/a\/\d+\/advisories\?item=CVE-2022-21449$/);
    await expect(origin.getByTestId("result-otto-design")).toContainText(/Design fingerprint \(SHA-256\): [0-9a-f]{64}/);
    await expect(origin.getByTestId("result-otto-trial")).toContainText("openjdk 17.0.2 (affected): 10 of 77 cases wrong.");
    await expect(origin.getByTestId("result-otto-decision")).toHaveText([
      /^1\. Accepted by You on .+ UTC\.$/, /^2\. Accept undone by You on .+ UTC\.$/, /^3\. Accepted by You on .+ UTC\.$/]);
    await expect(origin.getByTestId("result-otto-decisions")).toContainText(ONE_LOGIN);
    await expect(origin.getByTestId("advisory-ledger")).toContainText("Otto ledger entries for this check and its decisions");
    await expect(origin.getByTestId("result-otto-note")).toContainText("The result comes only from the test.");
    await expect(origin.getByRole("button")).toHaveCount(0);
    // the result's Related block has the Advisory line, and it leads to the advisory
    const toAdvisory = page.getByTestId("detail-panel").locator('[data-testid="related-line"][data-kind="advisory"] [data-testid="related-link"]');
    await expect(toAdvisory).toHaveCount(1);
    expect(await layoutProblems(page), "Evidence, an advisory check's result open").toEqual([]);
    await shots(page, "3-00-evidence-result-where-the-check-came-from", { panel: true });

    // an accepted check that has run can no longer be undone, and Advisories shows the reviewer's result
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-result")).toHaveText("Failed");
    panel = await openAdvisory(page, "CVE-2022-21449");
    proposal = panel.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-undo")).toBeDisabled();
    await expect(proposal.getByTestId("proposal-blocked")).toHaveText("This check has run, so it stays in the test plan.");
    await expect(panel.getByTestId("advisory-here-result")).toHaveText("Failed");
    await expect(panel.getByTestId("open-in-checks")).toHaveAttribute("href", /#\/a\/\d+\/checks\?/);
    await expect(panel.getByTestId("see-the-evidence")).toHaveAttribute("href", /#\/a\/\d+\/evidence\?/);
    await shots(page, "3-00-advisory-result-and-undo-off", { panel: true });
    await closePanel(page);

    // the failed result brings two new proposals: a fix (Fixes) and a change to the migration plan (Migration)
    await page.goto(`/#/a/${assessment}/overview`);
    waiting = page.getByTestId("overview-waiting");
    await expect(waiting).toHaveAttribute("data-total", "2");
    await expect(waiting.locator('[data-testid="waiting-item"][data-kind="fix"]')).toHaveText("1 proposed fix");
    await expect(waiting.locator('[data-testid="waiting-item"][data-kind="plan"]')).toHaveText("1 proposed change to the migration plan");
    await expect(page.getByTestId("next-step")).toContainText("Otto proposes a fix for a failed advisory check.");
    await tour(page, "3-run", assessment, project);

    // ================================================================ 4. Otto's proposed fix: accepted, proven, approved, merged
    let fix = await openOttosFix(page, assessment);
    await expect(fix).toContainText("Written by Otto");
    proposal = fix.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await expect(proposal.getByRole("button")).toHaveText(["Accept", "Reject"]);
    // nothing can be connected before a person accepts the proposal
    await expect(fix.getByRole("button", { name: "Connect demo code" })).toBeDisabled();
    await expect(fix).toContainText("Otto proposes this change. Accept the proposal first; accepting runs nothing.");
    await expect(proposal.getByTestId("proposal-lines")).toContainText("What the change does, in Otto's words:");
    await expect(proposal.getByTestId("proposal-lines")).toContainText("Accepting it runs nothing and changes nothing");
    await expect(fix).toContainText("Nothing is changed until you accept it and connect the code");
    await expect(page.getByTestId("fix-row").filter({ has: page.getByTestId("fix-proposal-mark") }).getByTestId("fix-proposal-status")).toHaveText("Proposed");
    expect(await layoutProblems(page), "Fixes, Otto's proposed change").toEqual([]);
    await shots(page, "4-00-fixes-ottos-change-proposed", { panel: true });
    const runsBefore = await runCount(page, assessment);
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Accepted");
    await expect(proposal.getByTestId("proposal-effect")).toContainText("Next: Connect demo code.");
    expect(await runCount(page, assessment), "accepting the fix ran nothing").toBe(runsBefore);
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "not_connected");
    await expect(fix.getByRole("button", { name: "Connect demo code" })).toBeEnabled();
    await shots(page, "4-00-fixes-ottos-change-accepted", { panel: true });

    // ---- Connect demo code: the proof on a test copy reruns every locked test, the advisory check among them
    await fix.getByRole("button", { name: "Connect demo code" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });
    await expect(proposal.getByTestId("proposal-undo")).toBeDisabled();           // the code is connected: the accept stands
    const proof = page.locator('[data-testid="fix-section"][data-section="proof"]');
    if ((await proof.getByRole("button").first().getAttribute("aria-expanded")) !== "true") await proof.getByRole("button").first().click();
    await expect(page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="proof-row"][data-kind="advisory_cases"]').getByTestId("proof-check")).toHaveAttribute("data-ok", "true");
    // what the proof showed, in its own two groups: the server test is rerun, still reads Failed, and "came out the same"
    await expect(fix).toContainText(
      "every locked test that runs the changed code did what the proof asks of it (each pass-or-fail test passed), and every test that does not run it came out the same as before");
    await expect(fix).not.toContainText("Nothing is changed");            // the change is connected: no line says otherwise
    await expect(fix).not.toContainText("every locked test passed on the changed code");
    await expect(fix).toContainText("byte for byte one of the app's registered demo programs, acme-sign 1.4.3-otto");
    await expect(fix).not.toContainText("reports version 1.4.3-otto");
    expect(await layoutProblems(page), "Fixes, the proof open in the panel").toEqual([]);
    await shots(page, "4-00-fixes-proof-passed-on-ottos-change", { panel: true });
    // the changed code is, byte for byte, the registered program Otto's change gives
    const technical = page.locator('[data-testid="fix-section"][data-section="details"]');
    if ((await technical.getByRole("button").first().getAttribute("aria-expanded")) !== "true") await technical.getByRole("button").first().click();
    await expect(technical).toContainText("acme-sign 1.4.3-otto");

    // ---- a person opens the pull request, approves and merges
    await fix.getByRole("button", { name: "Open pull request" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "waiting");
    await fix.locator('[data-testid="approval-row"][data-reviewer="you"]').getByRole("button", { name: "Approve", exact: true }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready_to_merge");
    await fix.getByRole("button", { name: "Merge pull request" }).click();
    await page.getByRole("button", { name: "Confirm merge" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "merged");
    await expect(fix.getByRole("button", { name: "Retest now" })).toBeEnabled();
    await shots(page, "4-00-fixes-ottos-change-merged", { panel: true });
    await tour(page, "4-fix-proven-and-merged", assessment, project);

    // ================================================================ 5. what the results mean for the plan and the dependencies
    // ---- Migration, Systems (measured at stage 1): Otto proposes something to fix first on the program's Signatures track
    await page.goto(`/#/a/${assessment}/migration/systems`);
    await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled();
    const systemRow = page.getByTestId("system-card").filter({ hasText: "acme-sign 1.4.2" });
    await expect(systemRow.getByTestId("system-otto-mark")).toContainText("Proposed");
    await systemRow.click();
    const plan = page.getByTestId("system-otto");
    await expect(plan).toContainText("From Otto: proposed changes to this system's plan");
    await expect(plan.getByTestId("system-otto-note")).toContainText("Neither changes a status or a measurement.");
    proposal = plan.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-title")).toHaveText("Fix acme-sign 1.4.2 before its signatures move to post-quantum");
    await expect(proposal.getByTestId("proposal-why")).toContainText("acme-sign 1.4.2 gave the wrong answer on 3 published cases");
    await expect(proposal.getByRole("button")).toHaveText(["Accept", "Reject"]);
    expect(await layoutProblems(page), "Migration, Systems, Otto's proposal").toEqual([]);
    await shots(page, "5-00-migration-plan-change-proposed", { panel: true });
    const statusBefore = await systemRow.getByTestId("card-track").allInnerTexts();
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Accepted");
    await expect(proposal.getByTestId("proposal-effect")).toHaveText("On the plan: something to fix first, on the Signatures track.");
    expect(await systemRow.getByTestId("card-track").allInnerTexts(), "accepting changed no track's status").toEqual(statusBefore);
    await shots(page, "5-00-migration-plan-change-accepted", { panel: true });
    // the Roadmap marks the same system
    await page.goto(`/#/a/${assessment}/migration/roadmap`);
    await expect(page.getByTestId("roadmap-otto").first()).toContainText("From Otto");
    await expect(page.getByTestId("roadmap-otto").first()).toContainText("On the plan: something to fix first, on the Signatures track.");
    expect(await layoutProblems(page), "Migration, Roadmap, with Otto's mark, panel closed").toEqual([]);
    // the row's name opens the same panel, where the proposal and its buttons are
    await page.getByTestId("roadmap-row").filter({ hasText: "acme-sign 1.4.2" }).first().getByRole("button").first().click();
    await expect(page.getByTestId("detail-panel").getByTestId("system-otto")).toBeVisible();
    expect(await layoutProblems(page), "Migration, Roadmap, the system's panel open").toEqual([]);
    await shots(page, "5-00-roadmap-with-ottos-mark", { panel: true });
    await closePanel(page);

    // ---- Dependencies: the libraries an advisory names, and Otto's proposed updates
    await page.goto(`/#/a/${assessment}/migration/dependencies`);
    await page.getByLabel("Choose a dependency list").setInputFiles(DEPENDENCIES_FILE);
    await expect(page.getByTestId("dependency-row")).toHaveCount(10);
    const library = (label: string) =>
      page.getByTestId("dependency-row").filter({ has: page.locator("p.font-mono", { hasText: new RegExp(`^${label.replace(/\./g, "\\.")}$`) }) });
    await expect(library("python-ecdsa 0.13.2").getByTestId("advisory-marker").first()).toContainText("Named by advisory CVE-2019-14859: not yet checked");
    await expect(library("openjdk 17.0.2").getByTestId("advisory-marker")).toContainText("Named by advisory CVE-2022-21449: not yet checked");
    await expect(library("elliptic 6.5.6").getByTestId("advisory-marker")).toHaveCount(0);      // its advisories come with the next pack
    // "Part of": the person says which system acme-ledger belongs to, so what is decided here shows on that system too
    await page.getByLabel("Part of: acme-ledger 5.1.0").selectOption({ label: "Signing program: acme-sign 1.4.2" });
    await expect(page.getByTestId("tie-words").nth(2)).toHaveText("Part of acme-sign 1.4.2, set by you.");
    expect(await layoutProblems(page), "Dependencies, named by an advisory, panel closed").toEqual([]);
    await library("python-ecdsa 0.13.2").click();
    let detail = page.getByTestId("detail-panel");
    await expect(detail.getByTestId("dependency-advisory").first()).toContainText("No check has run on python-ecdsa 0.13.2 here");
    await expect(detail.getByTestId("dependency-advisory-fixed").first()).toHaveText("Its publisher names 0.13.3 as the fixed version; your list has 0.13.2.");
    proposal = detail.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-title")).toHaveText("Update python-ecdsa 0.13.2 to 0.13.3 before the move");
    await expect(proposal.getByTestId("proposal-lines")).toContainText("Proven on public copies: Passed. 0.13.2 fails the advisory check; 0.13.3 passes.");
    expect(await layoutProblems(page), "Dependencies, a library's panel with Otto's proposal").toEqual([]);
    await shots(page, "5-00-dependencies-update-proposed", { panel: true });
    const blockers = await page.getByTestId("blocker-line").allInnerTexts();
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Accepted");
    await expect(detail.getByTestId("dependency-otto-status")).toContainText("Update first");
    await expect(detail.getByTestId("dependency-otto-status")).toContainText("Marked “update first”: python-ecdsa 0.13.2 to 0.13.3. Accepted by You on");
    await shots(page, "5-00-dependencies-update-accepted", { panel: true });
    await closePanel(page);
    await library("openjdk 17.0.2").click();
    detail = page.getByTestId("detail-panel");
    proposal = detail.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-lines")).toContainText("Proven on public copies: Not proven. 17.0.2 fails the advisory check and 17.0.3 passes it");
    // two version numbers on one row are two questions: the advisory's fix, and what post-quantum needs
    await expect(proposal.getByTestId("proposal-lines")).toContainText("This answers the advisory only. For post-quantum, this row's own answers name later versions");
    await reject(page, proposal, JAVA_REASON);
    await expect(proposal.getByTestId("proposal-status")).toHaveText(`Not added (${JAVA_REASON})`);
    await expect(detail.getByTestId("dependency-otto-status")).toHaveCount(0);
    await shots(page, "5-00-dependencies-update-rejected", { panel: true });
    await closePanel(page);
    expect(await page.getByTestId("blocker-line").allInnerTexts(), "no decision changed a blocker").toEqual(blockers);
    // the system the entry is part of says what was accepted, under its blockers and never among them
    const ottoLines = page.getByTestId("system-otto-lines");
    await expect(ottoLines.getByTestId("system-otto-line")).toHaveCount(1);
    await expect(ottoLines).toContainText("Marked “update first”: python-ecdsa 0.13.2 to 0.13.3.");
    await page.evaluate(() => window.scrollTo(0, 0));
    await shots(page, "5-00-dependencies-system-box-says-update-first");
    await tour(page, "5-plan-and-dependencies", assessment, project);

    // ================================================================ 6. Retest now: the same locked check on the merged code
    fix = await openOttosFix(page, assessment);
    await fix.getByRole("button", { name: "Retest now" }).click();
    // straight to Evidence, on the retested result; the table's before and after columns are read with the panel closed
    await expect(page.getByRole("heading", { name: "Evidence", level: 1 })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("detail-panel").getByTestId("lab-row")).toBeVisible();
    await closePanel(page);
    await expect(page.getByTestId("lab-columns")).toContainText("Before: acme-sign 1.4.2");
    await expect(page.getByTestId("lab-columns")).toContainText("After: acme-sign 1.4.3");
    await expect(page.getByTestId("retest-progress")).toHaveCount(0, { timeout: 300_000 });
    await expect(evidenceRow(page, RANGE_CHECK).getByTestId("lab-cell-before").getByTestId("result-badge")).toContainText("Failed");
    await expect(evidenceRow(page, RANGE_CHECK).getByTestId("lab-cell-after").getByTestId("result-badge")).toContainText("Passed");
    expect(await layoutProblems(page), "Evidence, before and after, panel closed").toEqual([]);
    await shots(page, "6-00-evidence-before-and-after-the-merge");
    // the retested result, open beside the table (which is then in its compact form)
    await openResult(page, RANGE_CHECK);
    expect(await layoutProblems(page), "Evidence, before and after, a result open").toEqual([]);
    await closePanel(page);
    // Checks: the fix proof and the retest of the advisory check are rows of their own, each marked "From Otto" with
    // its advisory, and the row's panel says so too
    await page.goto(`/#/a/${assessment}/checks`);
    const ottoRows = page.getByTestId("check-row").filter({ has: page.getByTestId("check-from-otto-mark") });
    await expect(ottoRows.first()).toBeVisible();
    await expect(ottoRows.first().getByTestId("check-from-otto-mark")).toContainText("From Otto");
    expect(await layoutProblems(page), "Checks, rows from Otto, panel closed").toEqual([]);
    await ottoRows.first().click();
    await expect(page.getByTestId("detail-panel").getByTestId("check-from-otto-line")).toContainText("From Otto");
    expect(await layoutProblems(page), "Checks, a row from Otto, panel open").toEqual([]);
    await shots(page, "6-00-checks-row-from-otto", { panel: true });
    await closePanel(page);
    // the accepted plan change reads done, from the newer result
    await page.goto(`/#/a/${assessment}/migration/systems`);
    await page.getByTestId("system-card").filter({ hasText: "acme-sign" }).first().click();
    proposal = page.getByTestId("system-otto").getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-effect")).toContainText("Done: the check for CVE-2022-21449 passed on acme-sign 1.4.3-otto");
    await expect(proposal.getByTestId("proposal-undo")).toBeDisabled();
    await shots(page, "6-00-migration-plan-change-done", { panel: true });
    // Advisories: the row is named for acme-sign 1.4.2 and its newest result is the retest's. It says which version.
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-result")).toHaveText("Passed");
    await expect(advisoryRow(page, "CVE-2022-21449")).toContainText("Retest on acme-sign 1.4.3-otto. First run on acme-sign 1.4.2: Failed.");
    expect(await layoutProblems(page), "Advisories after the retest, panel closed").toEqual([]);
    panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByTestId("advisory-here-ran-on")).toHaveText("This is the retest, on acme-sign 1.4.3-otto. The first run, on acme-sign 1.4.2, read Failed.");
    expect(await layoutProblems(page), "Advisories after the retest, panel open").toEqual([]);
    await shots(page, "6-00-advisory-result-after-the-retest", { panel: true });
    await closePanel(page);
    await tour(page, "6-retested", assessment, project);

    // ================================================================ 7. a new test pack arrives: the loop starts again
    await installPack(page, "2026.11.2");
    await expect(page.getByTestId("test-packs").getByTestId("otto-pack-card")).toHaveCount(2);
    await expect(page.getByTestId("test-packs").getByTestId("otto-counts-line")).toContainText("6 advisories and 3 tests");
    // the Overview: the new pack's check and the update it brings for elliptic wait for a decision
    await page.goto(`/#/a/${assessment}/overview`);
    waiting = page.getByTestId("overview-waiting");
    await expect(waiting).toHaveAttribute("data-total", "2");
    await expect(waiting.locator('[data-testid="waiting-item"][data-kind="check"]')).toHaveText("1 proposed check");
    await expect(waiting.locator('[data-testid="waiting-item"][data-kind="dependency"]')).toHaveText("1 proposed dependency update");
    const next = page.getByTestId("next-step");
    await expect(next).toContainText("Otto proposes 1 advisory check from the installed test packs.");
    await expect(next).toContainText("accepting runs nothing");
    await shots(page, "7-00-overview-a-new-pack-proposes");
    // Import's line is read again when Import opens: it counts the new pack's check too
    await page.goto(`/#/a/${assessment}/inventory/import`);
    await expect(page.getByTestId("import-otto").getByTestId("import-otto-text")).toHaveText(
      "Otto found 3 checks that may apply: 3 published weaknesses with a test, for acme-sign 1.4.2.");
    // the Project overview: what changed since that pack
    await page.goto(`/#/p/${project}`);
    const inProject = page.getByTestId("project-otto");
    await expect(inProject.getByTestId("project-otto-pack")).toContainText("Newest test pack: 2026.11.2");
    const mine = inProject.locator(`[data-testid="project-otto-row"][data-assessment="${assessment}"]`);
    await expect(mine).toHaveAttribute("data-waiting", "2");
    await expect(mine.getByTestId("project-otto-since")).toContainText("It brought 1 proposed check for this assessment: 1 waiting.");
    await shots(page, "7-00-project-overview-since-the-new-pack");
    await next.page().goto(`/#/a/${assessment}/overview`);
    await page.getByTestId("next-step").getByRole("button", { name: "Open advisories" }).click();
    await expect(page).toHaveURL(/#\/a\/\d+\/advisories$/);
    advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    await expect(advisoryRow(page, "CVE-2024-42461").getByTestId("advisory-test")).toHaveText("No test yet");
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "No test yet" });
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    // one of them has no test because its design only repeated another advisory's check, and the page says so
    const twin = await openAdvisory(page, "CVE-2019-14853");
    await expect(twin.getByTestId("advisory-no-test")).toContainText("the same check under a second name");
    await expect(twin.getByTestId("advisory-fix")).toContainText("No fix is offered");
    await closePanel(page);
    await advisories.getByTestId("advisories-filter-test").selectOption({ label: "Any test" });
    await advisories.getByTestId("advisories-search").fill("elliptic");
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await advisories.getByTestId("advisories-search").fill("");
    // the new check is accepted and run by itself; nothing else is rerun
    panel = await openAdvisory(page, "CVE-2024-42460");
    proposal = panel.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");
    await closePanel(page);
    // the check that was rejected earlier is taken up again, and accepted this time: every decision stays on the record
    panel = await openAdvisory(page, "CVE-2019-14859");
    proposal = panel.getByTestId("otto-proposal");
    await decide(page, proposal, "reconsider");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await expect(proposal.getByTestId("proposal-decided")).toContainText("Taken up again by You on");
    await decide(page, proposal, "accept");
    await proposal.getByTestId("proposal-history").locator("summary").first().click();
    await expect(proposal.getByTestId("proposal-decision")).toHaveText([
      new RegExp(`^1\\. Rejected by You on .+ UTC: ${REASON}\\.$`), /^2\. Taken up again by You on .+ UTC\.$/, /^3\. Accepted by You on .+ UTC\.$/]);
    await shots(page, "7-00-advisory-reconsidered-and-accepted", { panel: true });
    await closePanel(page);
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(8);
    await runOne(page, MISSING_ZERO_CHECK);
    await runOne(page, ENCODED_CHECK);
    advisories = await openAdvisories(page, assessment);
    await expect(advisoryRow(page, "CVE-2024-42460").getByTestId("advisory-result")).toHaveText("Passed");
    await expect(advisoryRow(page, "CVE-2019-14859").getByTestId("advisory-result")).toHaveText("Passed");
    expect(await layoutProblems(page), "Advisories with two packs, panel closed").toEqual([]);
    // Evidence: the two checks added since the retest ran on the version the file names. The page says how many of
    // the tests have a result after, and never that all eight ran on the retested version.
    await stepLink(page, "Evidence").click();
    await expect(page.getByTestId("lab-subline")).toContainText("six of the eight locked tests were run on acme-sign 1.4.2 and then on acme-sign 1.4.3-otto");
    await expect(page.getByTestId("lab-subline")).toContainText("The other two have no result after yet: retest again to run every test in the plan on acme-sign 1.4.3-otto.");
    await shots(page, "7-00-evidence-two-checks-added-since-the-retest");
    // Dependencies: elliptic is now named by its advisories, and Otto's proposed update for it is accepted
    await page.goto(`/#/a/${assessment}/migration/dependencies`);
    await expect(library("elliptic 6.5.6").getByTestId("advisory-marker").first()).toContainText("Named by advisory CVE-2024-42460: not yet checked");
    await library("elliptic 6.5.6").click();
    detail = page.getByTestId("detail-panel");
    proposal = detail.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-title")).toHaveText("Update elliptic 6.5.6 to 6.5.7 before the move");
    await decide(page, proposal, "accept");
    await expect(detail.getByTestId("dependency-otto-status")).toContainText("Update first");
    await closePanel(page);
    await page.goto(`/#/a/${assessment}/overview`);
    await expect(page.getByTestId("overview-waiting")).toHaveAttribute("data-total", "0");
    await expect(page.getByTestId("overview-waiting").getByTestId("waiting-line")).toHaveText("Nothing from Otto is waiting for a decision.");
    await tour(page, "7-new-pack", assessment, project);

    // ================================================================ 8. evidence: all of it, signed, and one command checks it
    const { json, report, file } = await downloadEvidence(page);
    const part = json.evidence.otto;
    expect(part.schema).toBe("isogeny.otto-evidence/1");
    expect(part.packs.map((p: any) => p.pack.version)).toEqual(["2026.11.1", "2026.11.2"]);
    expect(part.checks).toHaveLength(3);
    expect(part.ledger.height).toBe(part.ledger.lines.length);
    // Otto's own change was used: the one Claude step, from the recorded answers, with no model named
    expect(part.steps.map((s: any) => [s.step, s.source, s.outcome, s.model])).toEqual([["write_fix", "recorded", "used", null]]);
    // every proposal is in the file, decided or not, and every decision with who and when
    const decisions = (part.proposals as any[]).flatMap((p) => (p.decisions as any[]).map((d) => ({ ...d, kind: p.kind, title: p.title })));
    expect(decisions.map((d) => `${d.kind}: ${d.decision}`).sort()).toEqual([
      "check: accept", "check: accept", "check: accept", "check: accept", "check: reconsider", "check: reject", "check: undo",
      "dependency: accept", "dependency: accept", "dependency: reject", "fix: accept", "plan: accept"]);
    expect(decisions.every((d) => d.by === "You" && /^20\d\d-\d\d-\d\dT/.test(d.at) && d.ledger_entry && d.proposal_sha256)).toBe(true);
    expect(decisions.filter((d) => d.decision === "reject").map((d) => d.reason).sort()).toEqual([JAVA_REASON, REASON]);
    const states = Object.fromEntries((part.proposals as any[]).map((p) => [p.title, p.status]));
    expect(states["Update openjdk 17.0.2 to 17.0.3 before the move"]).toBe(`Not added (${JAVA_REASON})`);
    expect(report).toContain("Otto: test packs, the ledger and Claude");
    expect(report).toContain("Otto&#x27;s proposals, and the decisions on them");
    expect(report).toContain(JAVA_REASON);
    expect(JSON.stringify(json)).not.toMatch(/sk-ant-|api[_-]?key"\s*:/i);
    // the report as a person reads it: every proposal with where it stands and each decision on it, who and when
    const reportPage = await page.context().newPage();
    await reportPage.setViewportSize({ width: 1440, height: 900 });
    await reportPage.setContent(report, { waitUntil: "load" });
    const table = reportPage.locator("h3", { hasText: "Otto's proposals, and the decisions on them" }).locator("xpath=following-sibling::table[1]");
    await expect(table.locator("tbody tr")).toHaveCount((part.proposals as any[]).length);
    await expect(table).toContainText(`Not added (${JAVA_REASON})`);
    await expect(table).toContainText("Accepted by You");
    await reportPage.locator("h3", { hasText: "Otto's proposals, and the decisions on them" }).scrollIntoViewIfNeeded();
    fs.mkdirSync(SHOTS, { recursive: true });
    await table.screenshot({ path: path.join(SHOTS, "8-00-report-ottos-proposals-and-decisions.png"), animations: "disabled", scale: "css" });
    await reportPage.close();
    const good = verify(file, copy.dataDir);
    expect(good.status, `the evidence file should check: ${good.stdout} ${good.stderr}`).toBe(0);
    expect(good.stdout).toMatch(/^Evidence verified/);
    expect(good.stdout).toContain("Test packs: 2 in the file");
    expect(good.stdout).toMatch(/Decisions: 12 on \d+ of Otto's \d+ proposals, each in the ledger with who and when/);
    // what the verify command printed, kept outside the repository for the phase report (plain text: no key, no secret)
    fs.writeFileSync(path.join(os.tmpdir(), "evidence-lab-e2e-otto-verify-output.txt"), good.stdout);
    // one changed byte inside Otto's part is caught
    const raw = fs.readFileSync(file);
    const at = raw.indexOf(Buffer.from('"otto"')) + 60;
    raw[at] = raw[at] ^ 0x01;
    const changed = path.join(path.dirname(file), "changed.json");
    fs.writeFileSync(changed, raw);
    const bad = verify(changed, copy.dataDir);
    expect(bad.status).toBe(1);
    expect(bad.stdout).toMatch(/^Evidence NOT verified/);
    await tour(page, "8-evidence", assessment, project);

    // ---- Close the assessment (a sign-off with a name): everything stays readable, and nothing more can be decided
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
    await expect(advisoryRow(page, "CVE-2022-21449").getByTestId("advisory-result")).toHaveText("Passed");   // as it was signed off
    panel = await openAdvisory(page, "CVE-2022-21449");
    await expect(panel.getByTestId("otto-proposal").getByTestId("proposal-undo")).toBeDisabled();
    await shots(page, "8-99-advisories-closed-assessment", { panel: true });
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. isolated mode: a real library

test("isolated mode: a real library's fix from Otto has two proof rows, and a retest on the fixed version fills the second", async ({ browser }) => {
  test.setTimeout(30 * 60_000);
  let copy: Copy | null = null;
  // a scanner file that names one real library (data; nothing in it runs)
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-one-library-"));
  const oneLibrary = path.join(folder, "one-library.csv");
  fs.writeFileSync(oneLibrary, "location,type,claim,value\nelliptic 6.5.6,software,signature_algorithm,ECDSA P-256\n");
  try {
    copy = await startCopy(browser, 13, "auto");
    test.skip(copy.mode !== "isolated",
              "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    await ottoOrSkip(page);
    await installPack(page, "2026.11.1");
    await installPack(page, "2026.11.2");
    await openFreshAssessment(page, "Otto walk, a real library");
    const uploaded = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/file" && r.request().method() === "POST");
    await page.getByLabel("Choose a file to import").setInputFiles(oneLibrary);
    expect((await uploaded).status(), "expected the upload of the one-library file to be accepted").toBe(200);
    await expect(page.getByTestId("claim-row")).toHaveCount(1);
    // three published weaknesses have a test, and each fits this one library
    await expect(page.getByTestId("import-otto")).toHaveAttribute("data-count", "3");
    // Verify runs the library in its own container, so it takes a while before the Verify page opens
    await page.getByRole("button", { name: "Verify claims" }).click();
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible({ timeout: 300_000 });
    await page.getByRole("button", { name: "Continue to checks" }).click();
    await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
    await expect(page.getByTestId("test-card").first()).toBeVisible();
    const assessment = assessmentOf(page);
    const before = await page.getByTestId("test-card").count();

    // ---- Advisories: the proposal for the advisory that names this library says so, and is accepted by itself
    const advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(6);
    await expect(advisoryRow(page, "CVE-2024-42460").locator("td").nth(2)).toContainText("elliptic 6.5.6");
    let panel = await openAdvisory(page, "CVE-2024-42460");
    let proposal = panel.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-why")).toContainText("The advisory is about elliptic, and your file lists elliptic 6.5.6.");
    await expect(proposal.getByTestId("proposal-why")).toContainText("Its publisher names 6.5.7 as the fixed version.");
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");
    await closePanel(page);
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(before + 1);

    // ---- Run all on elliptic 6.5.6 (in its own locked-down container): the advisory check fails
    await page.getByRole("button", { name: "Run all" }).click();
    await expect.poll(() => cardStatuses(page), { timeout: 900_000 }).toEqual(Array(before + 1).fill("done"));
    await expect(card(page, MISSING_ZERO_CHECK).getByTestId("result-badge").first()).toContainText("Failed");

    // ---- Fixes: Otto's proposed fix is the pack's update, text only, with the two proof rows
    await openAdvisories(page, assessment);
    panel = await openAdvisory(page, "CVE-2024-42460");
    await expect(panel.getByTestId("advisory-here-result")).toHaveText("Failed");
    await expect(panel.getByTestId("advisory-fix-label")).toHaveText("From Otto");
    await expect(panel.getByTestId("advisory-fix")).toContainText("The test pack carries a fix for elliptic, the library this advisory is about: update it to 6.5.7 or later.");
    await expect(panel.getByTestId("advisory-fix")).toContainText("Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.");
    // a file of real libraries has no code of the customer's own, so the panel says nothing about a change for it
    await expect(panel.getByTestId("advisory-fix")).not.toContainText("your own code");
    await panel.getByTestId("advisory-fix-link").first().click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const fix = page.getByTestId("fix-summary");
    await expect(fix).toContainText("Update elliptic to 6.5.7");
    await expect(fix.getByTestId("fix-status")).toContainText("Text only");
    const rows = fix.getByTestId("proof-row");
    await expect(rows).toHaveCount(2);
    const onPublic = fix.locator('[data-testid="proof-row"][data-key="public"]');
    const here = fix.locator('[data-testid="proof-row"][data-key="here"]');
    await expect(onPublic.getByTestId("proof-row-badge")).toHaveText("Passed");
    await expect(onPublic.getByTestId("proof-row-text")).toHaveText("6.5.6 fails the advisory check; 6.5.7 passes.");
    await expect(onPublic.getByTestId("proof-row-link")).toHaveAttribute("href", /#\/a\/\d+\/advisories\?item=CVE-2024-42460$/);
    await expect(onPublic.getByTestId("advisory-ledger")).toContainText("Otto ledger entries");
    await expect(here.getByTestId("proof-row-badge")).toHaveText("Not yet");
    await expect(here.getByTestId("proof-row-text")).toHaveText("Update the library, then press Retest.");
    // what the row is about, right under its sentence: a public copy, not the system the reader runs
    await expect(here.getByTestId("proof-row-note")).toContainText("This row is about a public copy, not the system you run.");
    await expect(here.getByTestId("proof-row-note")).toContainText("The app has not checked that your own system was updated");
    // "then press Retest": the button is on Evidence, and the row links there
    await expect(here.getByTestId("proof-row-link")).toHaveText("Retest new version is on Evidence");
    await expect(here.getByTestId("proof-row-link")).toHaveAttribute("href", /#\/a\/\d+\/evidence\?item=test-\d+$/);
    // the entry for this library's other failed tests recommends the same update: each names the other
    await expect(fix).toContainText("It is one update, not two.");
    await expect(fix).not.toContainText("None. This suggestion is text only");
    await expect(fix.getByRole("button", { name: /Connect demo code|Apply|Merge/ })).toHaveCount(0);   // no code change for other people's code
    proposal = fix.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    expect(await layoutProblems(page), "Fixes, a library's fix from Otto, panel open").toEqual([]);
    await shots(page, "9-01-real-library-fix-two-proof-rows", { panel: true });
    await decide(page, proposal, "accept");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Accepted");
    await expect(proposal.getByTestId("proposal-effect")).toContainText("then press Retest");

    // ---- the result in Evidence repeats the same two rows on its fix line
    await stepLink(page, "Evidence").click();
    const result = await openResult(page, MISSING_ZERO_CHECK);
    await expect(result.getByTestId("fix-line-row")).toHaveText([
      "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
      "Proven on your system: Not yet. Update the library, then press Retest."]);
    await shots(page, "9-02-real-library-evidence-fix-line", { panel: true });
    await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();

    // ---- Retest new version: elliptic 6.5.7. The same locked tests run again on the updated version.
    await page.getByRole("button", { name: "Retest new version" }).click();
    await page.getByRole("menu").getByRole("menuitem", { name: /^elliptic 6\.5\.7/ }).click();
    await expect(page.getByTestId("lab-columns")).toContainText("After: elliptic 6.5.7", { timeout: 60_000 });
    await expect(page.getByTestId("retest-progress")).toHaveCount(0, { timeout: 900_000 });
    await expect(evidenceRow(page, MISSING_ZERO_CHECK).getByTestId("lab-cell-before").getByTestId("result-badge")).toContainText("Failed");
    await expect(evidenceRow(page, MISSING_ZERO_CHECK).getByTestId("lab-cell-after").getByTestId("result-badge")).toContainText("Passed");

    // ---- Fixes again: the second row now reads Passed, with its date and the way to the run; the fix stays listed
    await page.goto(`/#/a/${assessment}/fixes`);
    await page.getByTestId("fix-row").filter({ has: page.getByTestId("fix-proposal-mark") }).first().click();
    await expect(here.getByTestId("proof-row-badge")).toHaveText("Passed");
    await expect(here.getByTestId("proof-row-text")).toHaveText(
      /^On \d{1,2} \w+ 20\d\d, \d\d:\d\d UTC the retest on elliptic 6\.5\.7 passed: the advisory check and every other locked pass-or-fail test\.$/);
    await expect(here.getByTestId("proof-row-link")).toHaveText("See the retest's result");
    await expect(here.getByTestId("proof-row-link")).toHaveAttribute("href", /#\/a\/\d+\/evidence\?/);
    await expect(here.getByTestId("proof-row-note")).toContainText("This row is about a public copy, not the system you run.");
    await expect(onPublic.getByTestId("proof-row-badge")).toHaveText("Passed");
    await expect(fix.getByTestId("otto-proposal").getByTestId("proposal-undo")).toBeDisabled();    // a retest has run: the accept stands
    expect(await layoutProblems(page), "Fixes, the second row passed, panel open").toEqual([]);
    await shots(page, "9-03-real-library-fix-proven-on-your-system", { panel: true });
  } finally {
    await stopCopy(copy);
    fs.rmSync(folder, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------- 3. a computer without Otto

test("without Otto: the app says so, nothing can be decided, and the rest works as before", async ({ browser }) => {
  test.setTimeout(15 * 60_000);
  let copy: Copy | null = null;
  // an empty folder in the harness's place: on this copy of the app, Otto has not been fetched
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-no-otto-"));
  try {
    copy = await startCopy(browser, 14, "demo", { EVIDENCE_LAB_OTTO_HOME: empty });
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
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
    await shots(page, "9-11-settings-otto-not-installed");

    // ---- Advisories lists the pack's advisories and Otto's proposals to read; no decision can be recorded
    const advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(3);
    await expect(advisories.getByTestId("advisories-otto-line")).toContainText("Otto is not installed on this computer");
    await expect(advisories.getByTestId("advisories-waiting")).toContainText("nothing can be decided");
    await expect(advisories.getByTestId("advisories-waiting-line")).toHaveText("2 proposed checks have no decision.");
    await expect(advisories.getByTestId("advisories-waiting-line")).not.toContainText("accept or reject");
    const panel = await openAdvisory(page, "CVE-2022-21449");
    const proposal = panel.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Proposed");
    await expect(proposal.getByTestId("proposal-accept")).toBeDisabled();
    await expect(proposal.getByTestId("proposal-reject")).toBeDisabled();
    await expect(proposal.getByTestId("proposal-blocked")).toContainText("Otto is not installed on this computer");
    expect(await layoutProblems(page), "Advisories without Otto, panel open").toEqual([]);
    await shots(page, "9-12-advisories-otto-not-installed", { panel: true });
    await closePanel(page);
    // the Overview sends no one to proposals that can't be decided
    await page.goto(`/#/a/${assessment}/overview`);
    await expect(page.getByTestId("next-step")).not.toContainText("advisory check");
    await expect(page.getByTestId("overview-waiting")).toHaveAttribute("data-total", "0");

    // ---- everything else works as before: the plan's own tests run, and the fix template is offered as before
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(5);
    await page.getByRole("button", { name: "Run all" }).click();
    await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(5).fill("done"));
    await page.goto(`/#/a/${assessment}/fixes`);
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    await page.getByTestId("fix-row").filter({ hasText: "acme-sign" }).first().click();
    const fix = page.getByTestId("fix-summary");
    await expect(fix).toContainText("From a fix template");
    await expect(fix).not.toContainText("Written by Otto");
    await expect(fix.getByTestId("fix-proposal")).toHaveCount(0);
    await expect(fix.getByRole("button", { name: "Connect demo code" })).toBeEnabled();
    expect(empty && fs.readdirSync(empty), "looking at the app fetched nothing").toEqual([]);
  } finally {
    await stopCopy(copy);
    fs.rmSync(empty, { recursive: true, force: true });
  }
});
