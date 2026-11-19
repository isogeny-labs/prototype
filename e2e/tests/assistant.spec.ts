// Phase 6a end to end: the Otto assistant, the right-hand panel beside every page of an assessment. Two parts, each
// on a copy of the app of its own (own data folder and ports), on the Acme Pay demo:
//
//   1  demo mode, with the answers recorded during the build: one piece of work followed through the three tabs
//      (Testing, Fixing, Planning). Every decision and every start is made in the panel, behind Confirm; each page
//      then shows the same, in the same word; nothing is sent before Confirm; a tab closes and comes back with a dot;
//      the evidence file is downloaded and the verify command checks it, with the panel's decisions in it.
//   2  without Otto and without an API key: the panel says what Settings says, lists what is proposed with its
//      buttons off and the reason, and its next steps still work.
//
// Skipped with a message (part 1) when Otto is not installed on this computer. A copy of the app is started without
// any API key, so nothing here can reach Claude. Pictures of every page with the panel, dark and light:
// docs/screenshots/phase6a/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BACKEND, PYTHON, REPO, enterApp, layoutProblems, openFreshAssessment, screenshotFolder, startCopy, stepLink, stopCopy, type Copy } from "./shared";

const SHOTS = screenshotFolder("phase6a");
const DEPENDENCIES_FILE = path.join(REPO, "demo/dependencies-demo.cdx.json");
const RANGE_CHECK = "Advisory check: Missing ECDSA signature range check (CVE-2022-21449)";
const ENCODED_CHECK = "Advisory check: Badly encoded signature accepted (CVE-2019-14859)";
const REASON = "Not this quarter";
// The name typed once, at the first Confirm of a decision: every decision of the walk is recorded under it.
const NAME = "A tester";
const PLAN_CHANGE = "Fix acme-sign 1.4.2 before its signatures move to post-quantum";
// A time as the screens write it, for a viewer in New York: "18 November 2026, 7:46 pm EST".
const LOCAL_TIME = /\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d, \d{1,2}:\d\d [ap]m E[SD]T/;
const BANNED = ["Otto wrote", "Otto writes", "Otto proposes", "Otto proposed", "in Otto's words", "In Otto's words", "Why Otto proposes it", "Otto found",
                "Otto finds", "Otto has ", "Otto's proposal", "Otto asked", "Otto asks", "Otto no longer"];
const NEVER = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i];

const unanswered = new WeakMap<Page, number>();
// Every request of this walk that is not a read, in order: what the buttons sent.
const sent = new WeakMap<Page, string[]>();

function watchRequests(page: Page): void {
  unanswered.set(page, 0);
  sent.set(page, []);
  const toApp = (r: Request) => new URL(r.url()).pathname.startsWith("/api/");
  const done = (r: Request) => {
    if (toApp(r)) unanswered.set(page, Math.max(0, (unanswered.get(page) ?? 0) - 1));
  };
  page.on("request", (r) => {
    if (!toApp(r)) return;
    unanswered.set(page, (unanswered.get(page) ?? 0) + 1);
    if (r.method() !== "GET") sent.get(page)?.push(`${r.method()} ${new URL(r.url()).pathname}`);
  });
  page.on("requestfinished", done);
  page.on("requestfailed", done);
}

const changes = (page: Page): string[] => [...(sent.get(page) ?? [])];

/** Waits until the page has what it asked for and has stopped changing. */
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

/** A picture in the dark and the light look (what the window shows: the panel beside the page). */
async function shots(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await settled(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: false, animations: "disabled", scale: "css" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

function assessmentOf(page: Page): string {
  const found = /#\/a\/(\d+)/.exec(page.url());
  if (!found) throw new Error(`no assessment is open: ${page.url()}`);
  return found[1];
}

async function installPack(page: Page, version: string): Promise<void> {
  await page.goto("/#/settings?section=test-packs");
  const packs = page.getByTestId("test-packs");
  await expect(packs.getByTestId("otto-harness-line")).toBeVisible();
  await packs.getByTestId("otto-check-updates").click();
  await expect(packs.getByTestId("otto-update-line")).toContainText(version);
  await packs.getByTestId("otto-install-update").click();
  const installed = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/otto/packs/install" && r.request().method() === "POST");
  await page.getByTestId("otto-install-dialog").getByTestId("otto-install-confirm").click();
  expect((await installed).status()).toBe(200);
  await expect(packs.locator(`[data-testid="otto-pack-card"][data-version="${version}"]`)).toBeVisible();
}

// ---- the panel
const panelOf = (page: Page): Locator => page.getByTestId("otto-panel");
const onPage = (page: Page): Locator => panelOf(page).getByTestId("otto-on-page");
const tab = (page: Page, thread: string): Locator => panelOf(page).locator(`[data-testid="otto-tab"][data-thread="${thread}"]`);
const entries = (page: Page, what: string): Locator => onPage(page).locator(`[data-testid="otto-entry"][data-what="${what}"]`);
const entryTitled = (page: Page, what: string, title: string | RegExp): Locator =>
  entries(page, what).filter({ has: page.getByTestId("otto-entry-title").filter({ hasText: title }) });

/** Every tab that is open, in order. */
async function openTabs(page: Page): Promise<string[]> {
  return panelOf(page).getByTestId("otto-tab").evaluateAll((all) => all.map((t) => t.getAttribute("data-thread") ?? ""));
}

/** Presses one button of one entry and reads its Confirm step. Nothing is sent by this. */
async function ask(page: Page, entry: Locator, button: string): Promise<Locator> {
  const before = changes(page);
  await entry.getByRole("button", { name: button, exact: true }).click();
  const step = entry.getByTestId("otto-confirm");
  await expect(step).toBeVisible();
  await expect(step.getByTestId("otto-confirm-names")).toContainText(`This is the ${button} button on `);
  expect(changes(page), `pressing ${button} in the panel sent nothing; only Confirm does`).toEqual(before);
  return step;
}

/** Confirm: the one request it sends is awaited, and that it is the only one. Returns that request's address. */
async function confirm(page: Page, step: Locator, expected: RegExp): Promise<string> {
  const before = changes(page).length;
  const answered = page.waitForResponse((r) => r.request().method() === "POST" && expected.test(new URL(r.url()).pathname));
  await step.getByTestId("otto-confirm-button").click();
  const answer = await answered;
  expect(answer.status(), `Confirm was answered with ${answer.status()}`).toBe(200);
  const made = changes(page).slice(before);
  expect(made, "Confirm sent one request: the page button's own").toHaveLength(1);
  return made[0];
}

async function words(page: Page): Promise<string> {
  await settled(page);
  return page.evaluate(() => document.body.innerText);
}

async function expectPlainWords(page: Page, where: string): Promise<void> {
  const text = await words(page);
  for (const phrase of BANNED) expect(text.includes(phrase), `${where} says “${phrase}”`).toBe(false);
  const said = await panelOf(page).innerText();
  for (const word of NEVER) expect(word.test(said), `the panel on ${where} says ${word}`).toBe(false);
}

async function cardStatuses(page: Page): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

function verify(file: string, dataDir: string) {
  return spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", dataDir], { cwd: BACKEND, encoding: "utf-8" });
}

test.describe.configure({ mode: "serial" });
test.use({ actionTimeout: 60_000 });

// ---------------------------------------------------------------- 1. one piece of work, followed through the three tabs

test("demo mode: one piece of work through Testing, Fixing and Planning, decided in the panel behind Confirm; the pages show the same; the evidence verifies", async ({ browser }) => {
  test.setTimeout(30 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 15, "demo");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    test.skip(!otto.harness.installed, `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
    expect(otto.live.key_present, "a copy of the app is started without an API key").toBe(false);

    await installPack(page, "2026.11.1");
    // the panel sits beside the pages of an assessment, not beside Settings or Projects
    await expect(panelOf(page)).toHaveCount(0);
    await openFreshAssessment(page, "Otto panel walk");

    // ================================================================ no file yet
    const panel = panelOf(page);
    await expect(panel.getByRole("heading", { name: "Otto", level: 2 })).toBeVisible();
    await expect(panel.getByTestId("otto-status")).toHaveText("Live Otto is off. Settings");
    await expect(panel.getByTestId("otto-status-link")).toHaveAttribute("href", "#/settings?section=live-otto");
    await expect(panel.getByTestId("otto-empty")).toContainText("Bring in a scanner file to start. Nothing is suggested yet.");
    await expect(panel.getByTestId("otto-tabs")).toHaveCount(0);
    await expect(page.getByText("Prototype assistant")).toHaveCount(0);
    await shots(page, "01-import-no-file-yet");

    // ================================================================ Import: the file is in
    const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST");
    await page.getByRole("button", { name: "Use demo file" }).click();
    expect((await imported).status()).toBe(200);
    const assessment = assessmentOf(page);
    // the Testing tab is there (two checks are proposed), with how many wait
    await expect(tab(page, "testing")).toBeVisible();
    await expect(tab(page, "testing").getByTestId("otto-tab-count")).toContainText("2");
    expect(await openTabs(page)).toEqual(["testing"]);
    // what this means: the page's own line about the checks that may apply
    await expect(entries(page, "meaning:found").getByTestId("otto-entry-title")).toHaveText("2 checks may apply: 2 published weaknesses with a test, for acme-sign 1.4.2.");
    // the next step is the page's own button, off for the page's own reason until the address is ticked
    const verifyStep = entries(page, "next:verify");
    await expect(verifyStep.getByTestId("otto-entry-mark")).toHaveText("Next step");
    await expect(verifyStep.getByRole("button", { name: "Verify claims" })).toBeDisabled();
    await expect(verifyStep.getByTestId("otto-blocked")).toHaveText("Tick the box for each address on Import first.");
    // elsewhere: what waits, and where it lives
    const elsewhere = panel.getByTestId("otto-elsewhere");
    await expect(elsewhere.getByRole("heading")).toHaveText("Elsewhere: 2 more");
    await expect(elsewhere.getByTestId("otto-elsewhere-line")).toHaveText(/^Advisories: 2 proposed checks, Advisory check: .+ and 1 more$/);
    await shots(page, "02-import-file-in");

    // the tick stays on the page ("I own this system" is never pressed from the panel); then Verify claims, from the panel
    await page.getByTestId("address-confirm").click();
    await expect(verifyStep.getByRole("button", { name: "Verify claims" })).toBeEnabled();
    let step = await ask(page, verifyStep, "Verify claims");
    await expect(step).toContainText("It contacts only the addresses ticked on Import, with handshakes only.");
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Verify claims button on Import.");
    // Cancel leaves everything as it was
    const beforeCancel = changes(page);
    await step.getByTestId("otto-cancel-button").click();
    await expect(verifyStep.getByTestId("otto-confirm")).toHaveCount(0);
    expect(changes(page)).toEqual(beforeCancel);
    step = await ask(page, verifyStep, "Verify claims");
    expect(await confirm(page, step, /\/api\/import\/\d+\/verify$/)).toMatch(/^POST \/api\/import\/\d+\/verify$/);
    // ... and the app goes where the page's own button goes: Verify, with the results on the page
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
    await expect(page.getByTestId("result-row").first()).toBeVisible();
    // Verify: the next step only opens a page, so it is a link and needs no Confirm
    const toChecks = entries(page, "next:open").getByTestId("otto-step-open");
    await expect(toChecks).toHaveText("Continue to checks");
    await shots(page, "03-verify");
    const beforeOpen = changes(page);
    await toChecks.click();
    await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
    expect(changes(page), "opening a page sent nothing").toEqual(beforeOpen);

    // ================================================================ Checks: the Testing tab, the proposed checks, Run all
    await expect(page.getByTestId("test-card")).toHaveCount(5);
    await expect(tab(page, "testing")).toHaveAttribute("data-selected", "true");
    await expect(entries(page, "suggestion:check")).toHaveCount(2);
    const range = entryTitled(page, "suggestion:check", RANGE_CHECK);
    const encoded = entryTitled(page, "suggestion:check", ENCODED_CHECK);
    await expect(range.getByTestId("otto-entry-mark")).toHaveText("From Otto");
    await expect(range.getByTestId("otto-entry-badge")).toHaveText("Proposed");
    await expect(range.getByTestId("otto-entry-where")).toHaveText("On Advisories");          // it lives on Advisories, and fits Checks too
    await expect(range.getByTestId("otto-entry-where")).toHaveAttribute("href", `#/a/${assessment}/advisories?item=CVE-2022-21449`);
    await expect(entries(page, "next:run_all").getByTestId("otto-entry-text")).toHaveText("5 of the 5 tests in the plan have not run yet.");
    expect(await layoutProblems(page), "Checks with the panel full of cards").toEqual([]);
    await expectPlainWords(page, "Checks");
    await shots(page, "04-checks-two-proposed-checks");

    // ---- Accept, in the panel: first what will happen, then Confirm
    step = await ask(page, range, "Accept");
    await expect(step.getByTestId("otto-confirm-lines").getByRole("listitem")).toHaveText([
      "Adds this check to the test plan, as “+ Add test” would.", "Runs nothing.", "You can undo it until the check has run."]);
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Accept button on Advisories.");
    // the first Confirm of a decision asks, once, who decides: the name is kept in Settings, and the app says it has
    // one login and does not check who is at the keyboard
    await expect(step.getByLabel("Your name (asked once; kept in Settings)")).toBeVisible();
    await expect(step.getByTestId("otto-name-note")).toContainText("one login");
    await step.getByTestId("otto-name").fill(NAME);
    await shots(page, "05-checks-accept-waits-for-confirm");
    // Confirm keeps the name first, then sends the page's own accept: the decision is recorded under that name
    const beforeFirst = changes(page).length;
    const firstAnswer = page.waitForResponse((r) => r.request().method() === "POST" && /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname));
    await step.getByTestId("otto-confirm-button").click();
    expect((await firstAnswer).status()).toBe(200);
    const firstSent = changes(page).slice(beforeFirst);
    expect(firstSent).toHaveLength(2);
    expect(firstSent[0]).toBe("POST /api/otto/name");
    expect(firstSent[1]).toMatch(/^POST \/api\/plans\/\d+\/otto\/proposals\/check-cve-2022-21449-[0-9a-f]+\/accept$/);
    // the card reads as the page does: "Added", who and when (in the viewer's own time zone), and Undo
    await expect(range.getByTestId("otto-entry-badge")).toHaveText("Added");
    await expect(range.getByTestId("otto-entry-decided")).toHaveText(new RegExp(`^Accepted by ${NAME} on ${LOCAL_TIME.source}\\.$`));
    await expect(range.getByRole("button")).toHaveText(["Undo"]);
    // the page read its own view again, with no reload: the check is in the test plan, marked From Otto
    await expect(page.getByTestId("test-card")).toHaveCount(6);
    const added = page.getByTestId("test-card").filter({ hasText: RANGE_CHECK });
    await expect(added.getByTestId("card-from-otto")).toHaveText("From Otto");
    await expect.poll(() => cardStatuses(page)).toEqual(Array(6).fill("not_run"));       // accepting ran nothing
    // the card now offers the next step: Run, for the check that was just added
    await expect(entryTitled(page, "next:run", "Run").getByTestId("otto-entry-text")).toHaveText(`${RANGE_CHECK} has not run yet.`);
    await expect(tab(page, "testing").getByTestId("otto-tab-count")).toContainText("1");
    await shots(page, "06-checks-accepted-in-the-panel");

    // ---- Reject, with a reason; then the same proposal on its own page reads the same
    step = await ask(page, encoded, "Reject");
    await expect(step).toContainText("It is not deleted");
    await expect(step.getByTestId("otto-name")).toHaveCount(0);                       // asked once only
    await expect(step.getByTestId("otto-recorded-as")).toHaveText(`Recorded as ${NAME}, with the time.`);
    await step.getByTestId("otto-reason").fill(REASON);
    expect(await confirm(page, step, /\/otto\/proposals\/[^/]+\/reject$/)).toMatch(/\/reject$/);
    await expect(encoded.getByTestId("otto-entry-badge")).toHaveText(`Not added (${REASON})`);
    await expect(encoded.getByRole("button")).toHaveText(["Reconsider"]);
    await expect(panel.getByTestId("otto-nothing-waiting")).toHaveText("Nothing from Otto is waiting for a decision.");
    await stepLink(page, "Advisories").click();
    await expect(page.locator('[data-testid="advisory-row"][data-advisory="CVE-2022-21449"]').getByTestId("advisory-proposal")).toHaveText("Added");
    await expect(page.locator('[data-testid="advisory-row"][data-advisory="CVE-2019-14859"]').getByTestId("advisory-proposal")).toHaveText(`Not added (${REASON})`);
    // either place can be used: the same cards are in the panel beside Advisories, with the same words
    await expect(entryTitled(page, "suggestion:check", RANGE_CHECK).getByTestId("otto-entry-badge")).toHaveText("Added");
    await expect(entryTitled(page, "suggestion:check", ENCODED_CHECK).getByTestId("otto-entry-badge")).toHaveText(`Not added (${REASON})`);
    await shots(page, "07-advisories-the-same-words");
    // Undo and Reconsider work from the panel too, each behind Confirm (the first check is accepted again right after)
    step = await ask(page, entryTitled(page, "suggestion:check", RANGE_CHECK), "Undo");
    expect(await confirm(page, step, /\/otto\/proposals\/[^/]+\/undo$/)).toMatch(/\/undo$/);
    await expect(page.locator('[data-testid="advisory-row"][data-advisory="CVE-2022-21449"]').getByTestId("advisory-proposal")).toHaveText("Proposed");
    step = await ask(page, entryTitled(page, "suggestion:check", RANGE_CHECK), "Accept");
    await confirm(page, step, /\/otto\/proposals\/[^/]+\/accept$/);
    await expect(page.locator('[data-testid="advisory-row"][data-advisory="CVE-2022-21449"]').getByTestId("advisory-proposal")).toHaveText("Added");
    step = await ask(page, entryTitled(page, "suggestion:check", ENCODED_CHECK), "Reconsider");
    expect(await confirm(page, step, /\/otto\/proposals\/[^/]+\/reconsider$/)).toMatch(/\/reconsider$/);
    step = await ask(page, entryTitled(page, "suggestion:check", ENCODED_CHECK), "Reject");
    await step.getByTestId("otto-reason").fill(REASON);
    await confirm(page, step, /\/otto\/proposals\/[^/]+\/reject$/);

    // ---- Run all, from the panel: the page's own button, behind Confirm
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(6);
    const runAll = entries(page, "next:run_all");
    step = await ask(page, runAll, "Run all");
    await expect(step.getByTestId("otto-confirm-lines").getByRole("listitem").first()).toHaveText("Runs every test in the plan (6), on this computer.");
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Run all button on Checks.");
    expect(await confirm(page, step, /\/api\/plans\/\d+\/run-all$/)).toMatch(/^POST \/api\/plans\/\d+\/run-all$/);
    // the page shows the tests running, with no reload, and the panel says so too
    await expect.poll(async () => (await cardStatuses(page)).some((s) => s !== "not_run"), { timeout: 30_000 }).toBe(true);
    await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(6).fill("done"));
    await expect(added.getByTestId("result-badge")).toHaveText("Failed");
    // once every test has a result, running is not the next step any more; the accepted check's accept now stands
    await expect(entries(page, "next:run_all")).toHaveCount(0);
    await expect(entries(page, "next:run")).toHaveCount(0);
    const soFar = panel.getByTestId("otto-so-far");
    await expect(soFar.getByRole("heading")).toHaveText("This thread so far: Testing");
    // (the newest entries show; the decisions came before the results, so they are behind "Show all")
    await expect(soFar.getByTestId("otto-entry")).toHaveCount(6);
    await soFar.getByTestId("otto-so-far-all").click();
    await expect(soFar.getByTestId("otto-entry")).toHaveCount(8);                 // two decided checks, six results
    const told = soFar.locator('[data-testid="otto-entry"][data-kind="suggestion"]').filter({ hasText: RANGE_CHECK });
    await expect(told.getByTestId("otto-entry-badge")).toHaveText("Added");
    await expect(told.getByRole("button", { name: "Undo" })).toBeDisabled();
    await expect(told.getByTestId("otto-blocked")).toHaveText("This check has run, so it stays in the test plan.");
    await shots(page, "08-checks-after-run-all");

    // ================================================================ phase 6b: a typed sentence that moves around
    // "show me failed checks" opens Checks with only the failed checks listed. Nothing else happens.
    const box = panel.getByTestId("otto-box-text");
    await expect(panel.getByLabel("Ask Otto, or tell it what to do")).toBeVisible();
    await expect(panel.getByTestId("otto-chip")).toHaveText(["Show failed checks", "Run all", "What can you do?"]);
    const beforeSaid = changes(page).length;
    await box.fill("show me failed checks");
    expect(changes(page).length, "typing sends nothing").toBe(beforeSaid);
    await box.press("Enter");
    await expect(panel.getByTestId("otto-reply-text")).toHaveText(/^Opened Checks, filtered to Failed: \d+ checks\.$/);
    expect(page.url()).toMatch(new RegExp(`#/a/${assessment}/checks\\?result=Failed$`));
    await expect(page.getByRole("combobox", { name: "Result" })).toHaveValue("Failed");
    // only the failed checks are listed: fewer cards of the plan than before, and each reads Failed
    const failedCards = page.getByTestId("test-card");
    await expect.poll(() => failedCards.count()).toBeLessThan(6);
    const badges = await failedCards.getByTestId("result-badge").allInnerTexts();
    expect(badges.length).toBeGreaterThan(0);
    expect(badges.every((b) => b.trim() === "Failed"), `every listed test reads Failed: ${badges.join(", ")}`).toBe(true);
    for (const row of await page.getByTestId("check-row").all()) await expect(row).toContainText("Failed");
    // the one request it made is the sentence itself, kept with the assessment; nothing ran and nothing was decided
    expect(changes(page).slice(beforeSaid)).toEqual([expect.stringMatching(/^POST \/api\/plans\/\d+\/assistant\/messages$/)]);
    await expect.poll(() => cardStatuses(page)).not.toContain("running");
    expect(await layoutProblems(page), "Checks, filtered by a command, with the text box").toEqual([]);
    await shots(page, "08b-checks-show-me-failed-checks");
    // Back returns to the whole list
    await page.goBack();
    await expect(page.getByRole("combobox", { name: "Result" })).toHaveValue("all");
    await expect(page.getByTestId("test-card")).toHaveCount(6);
    // what was said is in the thread so far, as "You said"
    const saidLine = panel.getByTestId("otto-so-far").locator('[data-testid="otto-entry"][data-kind="said"]');
    await panel.getByTestId("otto-so-far-all").click().catch(() => undefined);
    await expect(saidLine.last().getByTestId("otto-entry-title")).toHaveText("show me failed checks");
    // a sentence the rules can't read: it says so, and lists what can be said here
    await box.fill("make me a sandwich");
    await box.press("Enter");
    await expect(panel.getByTestId("otto-reply-text")).toHaveText("I can't do that.");
    await expect(panel.getByTestId("otto-reply-example").first()).toBeVisible();

    // ================================================================ phase 6c: a fixed question, answered from the records
    // On Evidence the question that fits is "Why did this check fail?". Several checks failed and none is open, so it
    // asks which one, and the option asks about that one. The answer is a list of facts with links: nothing to press.
    await page.goto(`/#/a/${assessment}/evidence`);
    await expect(page.getByRole("heading", { name: "Evidence", level: 1 })).toBeVisible();
    await settled(page);
    await expect(panel.getByTestId("otto-question").first()).toHaveText("Why did this check fail?");
    const beforeAsked = changes(page).length;
    await panel.getByTestId("otto-question").first().click();
    await expect(panel.getByTestId("otto-reply-text")).toHaveText("Which one?");
    await panel.getByTestId("otto-reply-option").filter({ hasText: RANGE_CHECK }).click();
    const whyAnswer = panel.getByTestId("otto-reply");
    await expect(whyAnswer).toHaveAttribute("data-kind", "answer");
    await expect(whyAnswer.getByTestId("otto-reply-label")).toHaveText("From this assessment's records");
    const whyFacts = whyAnswer.getByTestId("otto-fact");
    await expect(whyFacts.first()).toContainText(`“${RANGE_CHECK}” reads Failed on acme-sign 1.4.2.`);
    expect(await whyFacts.count()).toBeGreaterThanOrEqual(5);
    await expect(whyAnswer.getByRole("button")).toHaveCount(0);                    // facts and links only
    await expect(panel.getByTestId("otto-confirm")).toHaveCount(0);
    // asking sent the two sentences, to be kept with the assessment, and nothing else: nothing ran, nothing was decided
    const keptSentence = expect.stringMatching(/^POST \/api\/plans\/\d+\/assistant\/messages$/);
    expect(changes(page).slice(beforeAsked)).toEqual([keptSentence, keptSentence]);
    // the facts are the result's own sentences: the second one is word for word the plain sentence Evidence shows for it
    const plainSentence = ((await whyFacts.nth(1).innerText()).replace(/\s*See the evidence\s*$/, "")).trim();
    await whyAnswer.getByRole("link", { name: "See the evidence" }).first().click();
    await expect(page).toHaveURL(new RegExp(`#/a/${assessment}/evidence\\?item=test-\\d+$`));
    await expect(page.getByTestId("page-content")).toContainText(plainSentence);
    expect(await layoutProblems(page), "Evidence with an answer in the panel").toEqual([]);
    await shots(page, "08c-evidence-why-did-this-check-fail");
    // with the result open, "this check" is that one: the same question is answered at once
    await panel.getByTestId("otto-question").first().click();
    await expect(panel.getByTestId("otto-reply").getByTestId("otto-fact").first()).toContainText(`“${RANGE_CHECK}” reads Failed`);
    // where the check came from opens its advisory
    await panel.getByTestId("otto-reply").getByRole("link", { name: "Open the advisory" }).click();
    await expect(page).toHaveURL(new RegExp(`#/a/${assessment}/advisories\\?item=CVE-2022-21449$`));
    // the answers are kept in the Testing thread, as "You said", with their facts
    const keptAnswer = panel.getByTestId("otto-so-far").locator('[data-testid="otto-entry"][data-kind="said"]').last();
    await panel.getByTestId("otto-so-far-all").click().catch(() => undefined);
    await expect(keptAnswer.getByTestId("otto-fact").first()).toContainText("reads Failed");

    // ================================================================ Migration: Measure status, from the panel; then the Planning tab
    await page.goto(`/#/a/${assessment}/migration/systems`);
    await expect(page.getByRole("heading", { name: "Migration", level: 1 })).toBeVisible();
    // before the status is measured there is the next step, and no Planning tab yet
    await expect(tab(page, "planning")).toHaveCount(0);
    const measure = entries(page, "next:measure_status");
    await expect(measure.getByTestId("otto-entry-title")).toHaveText("Measure status");
    await shots(page, "09-systems-measure-status-as-the-next-step");
    step = await ask(page, measure, "Measure status");
    // the Confirm step lists what the measurement does: it is more than one handshake
    await expect(step).toContainText("three first messages (TLS hellos)");
    await expect(step).toContainText("10 classical and 10 hybrid handshakes taken in turn");
    await expect(step).toContainText("Handshakes only; no data is sent.");
    await expect(step).toContainText("It changes nothing on any system.");
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Measure status button on Systems.");
    expect(await confirm(page, step, /\/migration\/measure$/)).toMatch(/\/migration\/measure$/);
    // (while it measures, the panel's card stays and says so; the page's own button is the one watched here)
    await expect(page.getByTestId("page-content").getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 240_000 });
    await expect(entries(page, "next:measure_status")).toHaveCount(0);
    // the advisory check failed on the program, so a change to its plan is proposed: the Planning tab opens, selected
    // (this page is its own), and the Systems page marks the same system
    await expect(tab(page, "planning")).toBeVisible();
    expect(await openTabs(page)).toEqual(["testing", "fixing", "planning"]);
    await expect(tab(page, "planning")).toHaveAttribute("data-selected", "true");
    await expect(tab(page, "planning").getByTestId("otto-tab-count")).toContainText("1");
    const planChange = entries(page, "suggestion:plan");
    await expect(planChange).toHaveCount(1);
    await expect(planChange.getByTestId("otto-entry-mark")).toHaveText("From Otto");
    await expect(planChange.getByTestId("otto-entry-title")).toHaveText(PLAN_CHANGE);
    await expect(planChange.getByTestId("otto-entry-where")).toHaveText("On Systems");
    const systemRow = page.getByTestId("system-card").filter({ hasText: "acme-sign 1.4.2" });
    await expect(systemRow.getByTestId("system-otto-mark")).toContainText("Proposed");
    expect(await layoutProblems(page), "Systems with the panel").toEqual([]);
    await expectPlainWords(page, "Systems");
    await shots(page, "10-systems-a-plan-change-proposed");
    // ---- Accept, in the panel, behind Confirm
    const tracksBefore = await systemRow.getByTestId("card-track").allInnerTexts();
    step = await ask(page, planChange, "Accept");
    await expect(step.getByTestId("otto-confirm-lines").getByRole("listitem")).toHaveText([
      "Adds this to the migration plan as something to fix first.", "Runs nothing and changes nothing on any system.",
      "You can undo it until a newer result of the check passes."]);
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Accept button on Systems.");
    expect(await confirm(page, step, /\/otto\/proposals\/[^/]+\/accept$/)).toMatch(/\/accept$/);
    await expect(planChange.getByTestId("otto-entry-badge")).toHaveText("Accepted");
    await expect(planChange.getByTestId("otto-entry-decided")).toHaveText(new RegExp(`^Accepted by ${NAME} on ${LOCAL_TIME.source}\\.$`));
    // the Systems page says the same, with no reload: the card's mark, and in the system's own panel the proposal
    // with what the accept did. No track's status moved.
    await expect(systemRow.getByTestId("system-otto-mark")).toContainText("Accepted");
    expect(await systemRow.getByTestId("card-track").allInnerTexts(), "accepting changed no track's status").toEqual(tracksBefore);
    await systemRow.click();
    const onSystem = page.getByTestId("system-otto").getByTestId("otto-proposal");
    await expect(onSystem.getByTestId("proposal-title")).toHaveText(PLAN_CHANGE);
    await expect(onSystem.getByTestId("proposal-status")).toHaveText("Accepted");
    await expect(onSystem.getByTestId("proposal-effect")).toHaveText("On the plan: something to fix first, on the Signatures track.");
    expect(await layoutProblems(page), "Systems with a system open and the panel").toEqual([]);
    await shots(page, "11-systems-accepted-in-the-panel");
    // the Roadmap fits the same thread, and marks the same system
    await page.goto(`/#/a/${assessment}/migration/roadmap`);
    await expect(page.getByTestId("roadmap-otto").first()).toContainText("On the plan: something to fix first, on the Signatures track.");
    await expect(tab(page, "planning")).toHaveAttribute("data-selected", "true");
    await expect(entries(page, "suggestion:plan").getByTestId("otto-entry-badge")).toHaveText("Accepted");

    // ================================================================ Evidence: what each result means; the Fixing tab has opened
    await stepLink(page, "Evidence").click();
    await expect(page.getByTestId("evidence-row").first()).toBeVisible();
    const meaning = entryTitled(page, "meaning:result", RANGE_CHECK);
    await expect(meaning.getByTestId("otto-entry-mark")).toHaveText("What this means");
    await expect(meaning.getByTestId("otto-entry-badge")).toHaveText("Failed");
    await expect(meaning.getByTestId("otto-entry-text")).toContainText("A fix is suggested: see Fixing.");
    await expect(meaning.getByTestId("otto-entry-link")).toHaveText(["See the evidence", "View in Fixes"]);
    await expect(meaning.getByRole("button")).toHaveCount(0);                 // links, and nothing else
    await expect(entries(page, "next:retest").first().getByTestId("otto-entry-title")).toHaveText("Retest new version");
    expect(await openTabs(page)).toEqual(["testing", "fixing", "planning"]);
    await expect(tab(page, "fixing")).toHaveAttribute("data-dot", "true");    // something new there, not seen yet
    await expect(tab(page, "fixing").getByTestId("otto-tab-count")).toContainText("1");
    await expect(panel.getByTestId("otto-elsewhere").getByTestId("otto-elsewhere-line")).toHaveText(/^Fixes: 1 proposed fix, /);
    expect(await layoutProblems(page), "Evidence with the panel").toEqual([]);
    await shots(page, "12-evidence-what-the-results-mean");
    // with a result open in the page's own side panel, its meaning comes first in Otto's panel
    await page.getByTestId("evidence-row").filter({ hasText: RANGE_CHECK }).first().click();
    await expect(page.getByTestId("detail-panel")).toBeVisible();
    await expect(onPage(page).locator('[data-testid="otto-entry"][data-open-item="true"]').first().getByTestId("otto-entry-title")).toHaveText(RANGE_CHECK);
    expect(await layoutProblems(page), "Evidence with a result open and the panel").toEqual([]);
    await shots(page, "13-evidence-a-result-open");

    // ================================================================ Fixes: the Fixing tab; the change is accepted in the panel
    await meaning.getByTestId("otto-entry-link").filter({ hasText: "View in Fixes" }).click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    await expect(tab(page, "fixing")).toHaveAttribute("data-selected", "true");
    await expect(tab(page, "fixing")).toHaveAttribute("data-dot", "false");
    const fix = page.getByTestId("fix-summary");
    await expect(fix).toContainText("Written by Otto");
    await expect(fix.getByRole("button", { name: "Connect demo code" })).toBeDisabled();       // off until the proposal is accepted
    const change = entries(page, "suggestion:fix");
    await expect(change).toHaveCount(1);
    await expect(change.getByTestId("otto-entry-where")).toHaveText("On Fixes");
    // the page's button is off, so the panel lists it off, with the page's own reason, for the fix that is open
    const connect = entries(page, "next:connect");
    await expect(connect.getByRole("button", { name: "Connect demo code" })).toBeDisabled();
    await expect(connect.getByTestId("otto-blocked")).toContainText("Accept it first");
    await shots(page, "14-fixes-a-change-proposed");
    step = await ask(page, change, "Accept");
    await expect(step.getByTestId("otto-confirm-lines").getByRole("listitem")).toHaveText([
      "Records your decision to take this fix.", "Runs nothing and changes nothing on any system.", "You can undo it until the fix has run or been applied."]);
    expect(await confirm(page, step, /\/otto\/proposals\/fix-code-[^/]+\/accept$/)).toMatch(/\/accept$/);
    await expect(change.getByTestId("otto-entry-badge")).toHaveText("Accepted");
    await expect(fix.getByTestId("fix-proposal").getByTestId("proposal-status")).toHaveText("Accepted");       // the page says the same
    await expect(fix.getByRole("button", { name: "Connect demo code" })).toBeEnabled();
    // ---- Connect demo code, from the panel
    step = await ask(page, connect, "Connect demo code");
    await expect(step).toContainText("It merges nothing.");
    expect(await confirm(page, step, /\/api\/plans\/\d+\/fixes\/connect$/)).toMatch(/\/fixes\/connect$/);
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });
    // ---- Open pull request, from the panel, with the reviewers the page ticks by default
    const pull = entries(page, "next:open_pull_request");
    step = await ask(page, pull, "Open pull request");
    await expect(step).toContainText("It merges nothing: a merge needs every approval and your own click on Fixes.");
    expect(await confirm(page, step, /\/pull-request$/)).toMatch(/\/pull-request$/);
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "waiting");
    // Approve and Merge pull request are never offered by the panel: they stay on their page
    await expect(onPage(page).getByRole("button", { name: /Approve|Merge/ })).toHaveCount(0);
    await shots(page, "15-fixes-pull-request-opened-from-the-panel");
    // (the reviewer the page ticks by default is "You": the panel asked exactly that one, as the page's button would)
    await expect(fix.locator('[data-testid="approval-row"]')).toHaveCount(1);
    await fix.locator('[data-testid="approval-row"][data-reviewer="you"]').getByRole("button", { name: "Approve", exact: true }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready_to_merge");
    await fix.getByRole("button", { name: "Merge pull request" }).click();
    await page.getByRole("button", { name: "Confirm merge" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "merged");
    // ---- Retest now, from the panel: the app goes to Evidence, as the page's own button does
    const retest = entries(page, "next:retest_now");
    step = await ask(page, retest, "Retest now");
    expect(await confirm(page, step, /\/fixes\/[^/]+\/retest$/)).toMatch(/\/retest$/);
    await expect(page.getByRole("heading", { name: "Evidence", level: 1 })).toBeVisible();
    // ... on the result this fix came from, open in the page's own side panel, exactly where Retest now on Fixes lands
    expect(page.url()).toMatch(new RegExp(`#/a/${assessment}/evidence\\?item=test-\\d+$`));
    await expect(page.getByTestId("detail-panel")).toBeVisible();
    await expect(page.getByTestId("evidence-row").filter({ hasText: RANGE_CHECK }).first()).toContainText("Passed", { timeout: 240_000 });
    await shots(page, "16-evidence-after-retest-now");

    // ================================================================ Migration again: the accepted plan change reads done
    await page.goto(`/#/a/${assessment}/migration/systems`);
    await expect(page.getByRole("heading", { name: "Migration", level: 1 })).toBeVisible();
    await expect(tab(page, "planning")).toHaveAttribute("data-selected", "true");
    // the check passed on the merged code since, so the accept stands: it can no longer be undone, here or on the page
    const planned = panel.getByTestId("otto-so-far").locator('[data-testid="otto-entry"][data-kind="suggestion"]').filter({ hasText: PLAN_CHANGE });
    await expect(planned.getByTestId("otto-entry-badge")).toHaveText("Accepted");
    await expect(planned.getByRole("button", { name: "Undo" })).toBeDisabled();
    await page.getByTestId("system-card").filter({ hasText: "acme-sign" }).first().click();
    await expect(page.getByTestId("system-otto").getByTestId("otto-proposal").getByTestId("proposal-effect")).toContainText("Done: the check for CVE-2022-21449 passed");
    await expect(page.getByTestId("system-otto").getByTestId("otto-proposal").getByTestId("proposal-undo")).toBeDisabled();

    // ================================================================ Dependencies: a library an advisory names; a tab closes and returns
    await page.goto(`/#/a/${assessment}/migration/dependencies`);
    // close the Fixing tab: it sends nothing, and it stays closed after a reload
    const beforeClose = changes(page);
    await tab(page, "fixing").getByTestId("otto-tab-close").click();
    expect(await openTabs(page)).toEqual(["testing", "planning"]);
    expect(changes(page), "closing a tab sent nothing").toEqual(beforeClose);
    await page.reload();
    // (after a reload the app signs in again and reads the assessment before the panel has its tabs; a request that the
    // reload cut off is never answered, so the count of unanswered requests starts again)
    await expect(tab(page, "testing")).toBeVisible({ timeout: 30_000 });
    await page.waitForLoadState("networkidle");
    unanswered.set(page, 0);
    expect(await openTabs(page)).toEqual(["testing", "planning"]);
    // how long the panel's one read takes at this late stage of the walk (kept in the run's output, for the record)
    const readStarted = Date.now();
    expect((await page.request.get(`/api/assessments/${assessment}/assistant?page=migration%2Fdependencies`)).status()).toBe(200);
    console.log(`The panel's read took ${Date.now() - readStarted} ms late in the walk.`);
    // a dependency list is added on the page: an update is proposed for a library an advisory names, so the Fixing
    // thread has something new, and its tab comes back by itself
    await page.getByLabel("Choose a dependency list").setInputFiles(DEPENDENCIES_FILE);
    await expect(page.getByTestId("dependency-row").first()).toBeVisible({ timeout: 60_000 });
    await expect(tab(page, "fixing")).toBeVisible();
    const update = entries(page, "suggestion:dependency");
    await expect(update.first().getByTestId("otto-entry-where")).toHaveText("On Dependencies");
    await expect(tab(page, "fixing")).toHaveAttribute("data-selected", "true");
    expect(await layoutProblems(page), "Dependencies with the panel").toEqual([]);
    await shots(page, "17-dependencies-an-update-proposed");
    // ---- phase 6b: "accept the Java fix" shows a card that names the proposal, its page and exactly what will happen;
    // the decision is recorded only after Confirm, as from the page
    const javaFix = /^Update openjdk 17\.0\.2 to 17\.0\.3 before the move$/;
    const beforeTyped = changes(page).length;
    await panel.getByTestId("otto-box-text").fill("accept the Java fix");
    await panel.getByTestId("otto-box-text").press("Enter");
    const answered = panel.getByTestId("otto-reply");
    await expect(answered.getByTestId("otto-reply-text")).toHaveText(/^Accept “Update openjdk 17\.0\.2 to 17\.0\.3 before the move”, on Dependencies\. Nothing happens until you press Confirm\.$/);
    const answerCard = answered.getByTestId("otto-entry");
    await expect(answerCard.getByTestId("otto-entry-mark")).toHaveText("From Otto");
    await expect(answerCard.getByTestId("otto-entry-title")).toHaveText(javaFix);
    await expect(answerCard.getByTestId("otto-entry-where")).toHaveText("On Dependencies");
    step = answerCard.getByTestId("otto-confirm");
    await expect(step.getByTestId("otto-confirm-lines").getByRole("listitem").first()).toHaveText("Marks this library “update first”.");
    await expect(step.getByTestId("otto-confirm-names")).toHaveText("This is the Accept button on Dependencies.");
    // typing decided nothing: the only request so far is the kept sentence, and the proposal still reads Proposed
    expect(changes(page).slice(beforeTyped)).toEqual([expect.stringMatching(/^POST \/api\/plans\/\d+\/assistant\/messages$/)]);
    await expect(entryTitled(page, "suggestion:dependency", javaFix).getByTestId("otto-entry-badge")).toHaveText("Proposed");
    await shots(page, "17b-dependencies-accept-the-java-fix-waits-for-confirm");
    expect(await confirm(page, step, /\/otto\/proposals\/dep-[^/]+\/accept$/)).toMatch(/\/accept$/);
    await expect(answered.getByTestId("otto-reply-confirmed")).toContainText("Confirmed.");
    await expect(entryTitled(page, "suggestion:dependency", javaFix).getByTestId("otto-entry-badge")).toHaveText("Accepted");
    // the Dependencies page shows the same, with no reload
    await expect(page.getByTestId("dependency-row").filter({ hasText: "openjdk" }).first()).toContainText("Accepted");
    await expectPlainWords(page, "Dependencies");

    // ================================================================ the Overview: its own next step, and what waits elsewhere
    await page.goto(`/#/a/${assessment}/overview`);
    await expect(page.getByTestId("overview-page")).toBeVisible();
    const waiting = Number(await page.getByTestId("overview-waiting").getAttribute("data-total"));
    const listed = await panel.getByTestId("otto-elsewhere").getAttribute("data-count");
    expect(Number(listed ?? "0"), "Elsewhere lists what the Overview counts as waiting").toBe(waiting);
    const next = (await page.getByTestId("next-step").getByRole("button").first().innerText()).trim();
    await expect(entries(page, "next:open").getByTestId("otto-step-open")).toHaveText(next);
    await shots(page, "18-overview");

    // ================================================================ the evidence: signed, with the panel's decisions in it
    await stepLink(page, "Evidence").click();
    const created = page.waitForResponse((r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Download evidence" }).click();
    const info = await (await created).json();
    const raw = await (await page.request.get(info.json.url)).body();
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-panel-file-")), "evidence.json");
    fs.writeFileSync(file, raw);
    const part = JSON.parse(raw.toString("utf-8")).evidence.otto;
    const decisions = (part.proposals as any[]).flatMap((p) => (p.decisions as any[]).map((d) => `${p.kind}: ${d.decision}`)).sort();
    expect(decisions).toEqual(["check: accept", "check: accept", "check: reconsider", "check: reject", "check: reject", "check: undo",
                               "dependency: accept", "fix: accept", "plan: accept"]);
    // a decision made in the panel is recorded as the page's: who, when, its entry in the ledger; nothing says "panel"
    const every = (part.proposals as any[]).flatMap((p) => p.decisions as any[]);
    expect(every.every((d) => d.by === NAME && /^20\d\d-\d\d-\d\dT/.test(d.at) && d.ledger_entry && d.proposal_sha256)).toBe(true);
    expect(raw.toString("utf-8")).not.toMatch(/otto-panel|from the panel|assistant/i);
    const good = verify(file, copy.dataDir);
    expect(good.status, `the evidence file should check: ${good.stdout} ${good.stderr}`).toBe(0);
    expect(good.stdout).toMatch(/^Evidence verified/);
    expect(good.stdout).toMatch(/Decisions: 9 on \d+ of the \d+ proposals, each in the ledger with who and when/);

    // ================================================================ after the review of 6b: a tab closed by a sentence stays closed
    // "close the Fixing tab" is kept with the assessment under that very thread. The tab must not come back for it.
    await expect(tab(page, "fixing")).toHaveCount(1);
    await panel.getByTestId("otto-box-text").fill("close the fixing tab");
    await panel.getByTestId("otto-box-text").press("Enter");
    await expect(panel.getByTestId("otto-reply-text")).toHaveText("Closed the Fixing tab.");
    await settled(page);
    await expect(tab(page, "fixing")).toHaveCount(0);
    await page.reload();
    await page.waitForLoadState("networkidle");
    unanswered.set(page, 0);
    await expect(panelOf(page).getByTestId("otto-status")).toBeVisible();
    await expect(tab(page, "testing")).toHaveCount(1, { timeout: 30_000 });
    await expect(tab(page, "fixing")).toHaveCount(0);                             // still closed after the page was loaded again
    // on Checks, narrowed by the earlier command's filter, the plan says how many of its tests are listed and what Run all does
    await page.goto(`/#/a/${assessment}/checks?result=Failed`);
    await expect(page.getByTestId("plan-narrowed")).toHaveText(/^\d+ of the plan's \d+ tests are listed \(Result: Failed\)\. Run all runs all \d+\.$/);
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. without Otto and without a key

test("without Otto and without a key: the panel says so, lists what is proposed with its buttons off, and its next steps still work", async ({ browser }) => {
  test.setTimeout(15 * 60_000);
  let copy: Copy | null = null;
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-no-otto-"));
  try {
    copy = await startCopy(browser, 16, "demo", { EVIDENCE_LAB_OTTO_HOME: empty });
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    expect(otto.harness.installed, "this copy is started with an empty harness folder").toBe(false);
    expect(otto.live.key_present).toBe(false);
    await installPack(page, "2026.11.1");                      // a pack is data: it installs without Otto
    await openFreshAssessment(page, "Otto panel walk, no Otto");
    const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST");
    await page.getByRole("button", { name: "Use demo file" }).click();
    expect((await imported).status()).toBe(200);
    const panel = panelOf(page);
    await expect(panel.getByTestId("otto-status")).toHaveText("Live Otto is off. Settings");
    await expect(panel.getByTestId("otto-notice")).toContainText("Otto is not installed on this computer");
    // the next steps are the pages' own buttons, and work as before
    await page.getByTestId("address-confirm").click();
    let step = await ask(page, entries(page, "next:verify"), "Verify claims");
    await confirm(page, step, /\/api\/import\/\d+\/verify$/);
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
    await entries(page, "next:open").getByTestId("otto-step-open").click();
    await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
    // what is proposed is listed, and nothing can be decided: the page's own reason
    const proposed = entries(page, "suggestion:check");
    await expect(proposed).toHaveCount(2);
    for (const card of await proposed.all()) {
      await expect(card.getByRole("button", { name: "Accept" })).toBeDisabled();
      await expect(card.getByRole("button", { name: "Reject" })).toBeDisabled();
      await expect(card.getByTestId("otto-blocked")).toContainText("Otto is not installed on this computer");
    }
    await shots(page, "19-checks-without-otto");
    step = await ask(page, entries(page, "next:run_all"), "Run all");
    await confirm(page, step, /\/api\/plans\/\d+\/run-all$/);
    await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(5).fill("done"));
    await expectPlainWords(page, "Checks, without Otto");
  } finally {
    await stopCopy(copy);
    fs.rmSync(empty, { recursive: true, force: true });
  }
});
