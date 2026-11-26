// Sandbox research (a prototype, off by default), end to end. Two parts, each on a copy of the app of its own:
//
//  1. Isolated mode, on a computer marked as Isogeny's own sandbox (skipped with a message when Docker or the test
//     images are not ready, Otto is not installed, or the six public package files of the demo could not be had).
//     One story, from a weakness with no fix to a proven check a person accepts:
//       Settings: the switch is off; its box says what it will do; it is turned on.
//       Change watch has two views now. On the Watch list, Look now finds a published weakness in starkbank-ecdsa with
//       no fix yet (the record with its fixed version taken out: Demo data). Advisories reads "No test yet" for it and
//       links to the Watch list.
//       The next day at the source: the record as it was published, with its fixed version. Look now marks the item
//       "Fix published", with its history. Stop watching and Watch again are recorded.
//       Advisories: the weakness can now be tried on public copies from PyPI, and the box of Design and prove tests
//       lists what will be fetched. The research run reads the advisory, designs a test, has the asking code written
//       twice (recorded answers), checks it, and tries the test in locked containers. The pack it signs is installed.
//       The proposal carries How this test was proven: the counts, the registration, the code as text, the
//       public copies. A person accepts it; the check is run by the runner and decided by the separate reviewer.
//       The evidence file is downloaded and verified.
//  2. Demo mode: the switch can't be turned on and says why; Change watch has its one view; Advisories reads as before.
//
// Nothing here reaches the network or Claude: the advisory source and the registry are folders of recorded answers
// (backend/tools/research_demo.py --sandbox prepares them), the answers of the Claude steps are the ones recorded during
// the build, and a copy is started without any API key. The Watch list's clock is off in these copies, so every look in
// the walk is the walk's own click (the clock has its backend tests).
// Screenshots (dark and light) go to docs/screenshots/sandbox/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND,
  DISCLAIMER,
  PYTHON,
  REPO,
  enterApp,
  layoutProblems,
  openFreshAssessment,
  openProofFold,
  startCopy,
  stopCopy,
  type Copy,
} from "./shared";

const SHOTS = path.join(REPO, "docs/screenshots/sandbox");
const ID = "CVE-2021-43572";
const ITEM = `${ID}~starkbank-ecdsa`;
const FILE = path.join(REPO, "demo/sandbox/starkbank-file.csv");
const LOCAL_TIME =
  /\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d, \d{1,2}:\d\d [ap]m E[SD]T/;
// Words this app never says about a system, and sentences that say what Otto did (the tags "From Otto" and "Written by Otto" stay).
const NEVER = [
  /\bsecure\b/i,
  /\bscore\b/i,
  /\bseverity\b/i,
  /Otto (found|proposes|proposed|wrote|has|asked|designed|proved|fetched|looked)\b/,
];

const unanswered = new WeakMap<Page, number>();
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

async function settled(page: Page): Promise<void> {
  let last = "";
  await expect
    .poll(
      async () => {
        const now = await page.evaluate(
          () => `${document.documentElement.scrollHeight}/${document.querySelectorAll("main *, aside *").length}`,
        );
        const same = now === last && (unanswered.get(page) ?? 0) === 0;
        last = now;
        return same;
      },
      { timeout: 30_000, intervals: [250] },
    )
    .toBe(true);
}

async function shots(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await settled(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({
      path: path.join(SHOTS, `${name}-${theme}.png`),
      fullPage: true,
      animations: "disabled",
      scale: "css",
    });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** No word the app never says about a system, and no sentence that says what Otto did. (Advisories carries the app's one
 * standing line, "Passing these tests doesn't prove a system secure.", so there the block itself is read.) */
async function expectPlainWords(page: Page, where: string, part?: Locator): Promise<void> {
  await settled(page);
  const said = await (part ?? page.getByTestId("page-content")).innerText();
  for (const word of NEVER) expect(word.test(said), `${where} says ${word}`).toBe(false);
}

function assessmentOf(page: Page): string {
  const found = /#\/a\/(\d+)/.exec(page.url());
  if (!found) throw new Error(`no assessment is open: ${page.url()}`);
  return found[1];
}

/** The folder of recorded answers for one day at the source (1: no fix yet, Demo data; 2: the record as published). On
 * day 1 it also holds the recorded registry with the six public package files. Null when a file could not be had. */
function prepare(folder: string, day: 1 | 2): { source: string; registry: string } | null {
  const made = spawnSync(PYTHON, ["tools/research_demo.py", "--sandbox", "--day", String(day), folder], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
  expect(made.status, `preparing the folder: ${made.stdout} ${made.stderr}`).toBe(0);
  if (made.stdout.includes("could not be fetched")) return null;
  return { source: path.join(folder, "source"), registry: path.join(folder, "registry") };
}

function verify(file: string, dataDir: string) {
  return spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", dataDir], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
}

async function openSettings(page: Page): Promise<Locator> {
  await page.goto("/#/settings");
  const block = page.getByTestId("sandbox-research");
  await expect(block).toBeVisible();
  await block.scrollIntoViewIfNeeded();
  return block;
}

async function openWatchList(page: Page, assessment: string): Promise<Locator> {
  await page.goto(`/#/a/${assessment}/change-watch`);
  await page.getByRole("tab", { name: "Watch list" }).click();
  const list = page.getByTestId("watch-list-page");
  await expect(list).toBeVisible();
  return list;
}

const watchRow = (page: Page): Locator => page.locator(`[data-testid="watch-row"][data-item="${ITEM}"]`);

/** Look now: the box first, then its own button. */
async function lookNow(page: Page): Promise<void> {
  const before = changes(page);
  await page.getByTestId("watch-look").click();
  const box = page.getByTestId("watch-look-box");
  await expect(box).toBeVisible();
  expect(changes(page), "opening the box sent nothing").toEqual(before);
  const answered = page.waitForResponse(
    (r) => /\/watch-list\/look$/.test(new URL(r.url()).pathname) && r.request().method() === "POST",
  );
  await box.getByTestId("watch-look-confirm").click();
  expect((await answered).status()).toBe(200);
  await expect(box).toHaveCount(0);
}

async function openAdvisories(page: Page, assessment: string): Promise<Locator> {
  await page.goto(`/#/a/${assessment}/advisories`);
  const advisories = page.getByTestId("advisories-page");
  await expect(advisories.getByTestId("advisories-standing")).toHaveText(DISCLAIMER);
  return advisories;
}

const block = (page: Page): Locator => page.getByTestId("new-advisories");
const found = (page: Page): Locator => block(page).locator(`[data-testid="found-advisory"][data-advisory="${ID}"]`);
const advisoryRow = (page: Page): Locator => page.locator(`[data-testid="advisory-row"][data-advisory="${ID}"]`);

test.describe.configure({ mode: "serial" });
test.use({ actionTimeout: 60_000 });

// ---------------------------------------------------------------- 1. the whole line, in isolated mode

test("sandbox research: no fix yet, the fix is published, a test is proven on public copies and proposed with its proof; a person accepts, the reviewer decides, the evidence verifies", async ({
  browser,
}) => {
  test.setTimeout(60 * 60_000);
  let copy: Copy | null = null;
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-sandbox-"));
  const prepared = prepare(folder, 1);
  test.skip(
    prepared === null,
    "Skipped: the public package files of the sandbox demo could not be fetched (files.pythonhosted.org is needed once).",
  );
  try {
    copy = await startCopy(browser, 28, "auto", {
      EVIDENCE_LAB_SANDBOX_RESEARCH: "1",
      EVIDENCE_LAB_ADVISORY_SOURCE: prepared!.source,
      EVIDENCE_LAB_REGISTRY_SOURCE: prepared!.registry,
      EVIDENCE_LAB_WATCH_CLOCK: "off",
    });
    test.skip(
      copy.mode !== "isolated",
      "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).",
    );
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    test.skip(
      !otto.harness.installed,
      `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`,
    );
    expect(otto.live.key_present, "a copy of the app is started without an API key").toBe(false);
    expect(otto.sandbox.switch.on, "Sandbox research is off until a person turns it on").toBe(false);

    // ================================================================ Settings: off by default; the box; turned on
    let settings = await openSettings(page);
    await expect(settings.getByTestId("sandbox-switch")).not.toBeChecked();
    await expect(settings.getByTestId("sandbox-status-line")).toContainText("Sandbox research is off.");
    await expect(settings.getByTestId("sandbox-by-itself")).toBeDisabled();
    await expect(settings.getByTestId("sandbox-by-itself-reason")).toHaveText(
      "This can be ticked only while Sandbox research is on.",
    );
    await shots(page, "01-settings-the-switch-is-off");
    const beforeBox = changes(page);
    await settings.getByTestId("sandbox-switch").click();
    const sandboxBox = page.getByTestId("sandbox-box");
    await expect(sandboxBox).toContainText("Nothing is added to an assessment without your Accept.");
    await expect(sandboxBox).toContainText("run in locked containers on this computer, with no network");
    expect(changes(page), "opening the box sent nothing").toEqual(beforeBox);
    await shots(page, "02-settings-the-box-before-it-is-turned-on");
    await sandboxBox.getByTestId("sandbox-box-cancel").click();
    expect(changes(page), "Cancel sent nothing").toEqual(beforeBox);
    await expect(settings.getByTestId("sandbox-switch")).not.toBeChecked();
    await settings.getByTestId("sandbox-switch").click();
    const turned = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/otto/sandbox" && r.request().method() === "POST",
    );
    await page.getByTestId("sandbox-box").getByTestId("sandbox-box-confirm").click();
    expect((await turned).status()).toBe(200);
    await expect(settings.getByTestId("sandbox-switch")).toBeChecked();
    await expect(settings.getByTestId("sandbox-status-line")).toContainText(
      "Designing and proving a test starts on a click",
    );
    // the second tick needs Live Otto, which needs a key: it stays off here, and says why
    await expect(settings.getByTestId("sandbox-by-itself")).toBeDisabled();
    await expect(settings.getByTestId("sandbox-by-itself-reason")).toHaveText(
      "This can be ticked only while Live Otto is on.",
    );
    await expect(settings.getByTestId("sandbox-run-limit")).toHaveValue("5.00");
    await expect(settings.getByTestId("sandbox-day-limit")).toHaveValue("10.00");
    await shots(page, "03-settings-the-switch-is-on");

    // ================================================================ an assessment that names starkbank-ecdsa 2.0.0
    await openFreshAssessment(page, "Sandbox research walk");
    const uploaded = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/import/file" && r.request().method() === "POST",
    );
    await page.getByLabel("Choose a file to import").setInputFiles(FILE);
    expect((await uploaded).status()).toBe(200);
    await expect(page.getByTestId("claim-row")).toHaveCount(1);
    const assessment = assessmentOf(page);

    // ================================================================ day 1: the Watch list, a weakness with no fix yet
    await page.goto(`/#/a/${assessment}/change-watch`);
    await expect(page.getByRole("tab", { name: "Changes" })).toBeVisible(); // two views now: the first is the one it always was
    let list = await openWatchList(page, assessment);
    await expect(list.getByTestId("watch-empty")).toBeVisible();
    await shots(page, "04-watch-list-before-a-look");
    await lookNow(page);
    await expect(watchRow(page)).toHaveAttribute("data-status", "no_fix");
    await expect(watchRow(page).getByTestId("watch-status")).toHaveText("No fix yet");
    await expect(watchRow(page).getByTestId("watch-new")).toBeVisible();
    await expect(list.getByTestId("watch-looked-line")).toContainText(/^Looked on .+ by You\./);
    expect(await layoutProblems(page), "the Watch list, panel closed").toEqual([]);
    await expectPlainWords(page, "the Watch list");
    await shots(page, "05-watch-list-no-fix-yet");
    await watchRow(page).click();
    const panel = page.getByTestId("watch-panel");
    await expect(panel.getByTestId("watch-panel-status")).toHaveText("No fix yet");
    await expect(panel).toContainText("Demo data"); // day 1's record is the made-up "before a fix" form, and says so
    await expect(panel.getByTestId("watch-quote")).toContainText("fails to check that the signature is non-zero"); // the publisher's own words
    await expect(panel.getByTestId("watch-yours")).toContainText("starkbank-ecdsa 2.0.0");
    await expect(panel.getByTestId("watch-history")).toContainText("no fixed version");
    expect(await layoutProblems(page), "the Watch list, panel open").toEqual([]);
    await shots(page, "06-watch-list-the-item-open");

    // Advisories says "No test yet" for it, and links to its row on the Watch list
    await openAdvisories(page, assessment);
    await expect(found(page)).toHaveAttribute("data-state", "no_test");
    await expect(found(page).getByTestId("found-reason")).toHaveText(
      "No test yet: the source names no fixed version, so there is nothing to prove a test against.",
    );
    await expect(found(page).getByTestId("found-sandbox")).toHaveCount(0);
    await expect(block(page).getByTestId("new-advisories-sandbox")).toContainText(
      "Sandbox research is on. A research run starts on a click",
    );
    await expect(block(page).getByTestId("design-and-prove")).toBeDisabled();
    await shots(page, "07-advisories-no-test-yet-on-the-watch-list");
    await found(page).getByTestId("found-watch-link").click();
    await expect(page.getByTestId("watch-panel")).toBeVisible(); // the link opens the item on the Watch list

    // ================================================================ day 2: the source names a fixed version
    expect(prepare(folder, 2), "day 2: the record as it was published").not.toBeNull();
    list = await openWatchList(page, assessment);
    await lookNow(page);
    await expect(watchRow(page)).toHaveAttribute("data-status", "fix_published");
    await expect(watchRow(page).getByTestId("watch-status")).toHaveText("Fix published");
    await watchRow(page).click();
    await expect(page.getByTestId("watch-panel").getByTestId("watch-history")).toContainText("2.0.1");
    await expect(page.getByTestId("watch-panel").getByTestId("watch-test")).toContainText(
      "A test can now be designed and proven (Design and prove tests, on Advisories).",
    );
    await expectPlainWords(page, "the Watch list after the fix was published");
    await shots(page, "08-watch-list-fix-published");
    // Stop watching, with a reason; then Watch again. Both are recorded; nothing about the weakness changes.
    await page.getByTestId("watch-panel").getByTestId("watch-stop").click();
    await page.getByTestId("watch-stop-reason").fill("We do not use it in production");
    const stopped = page.waitForResponse(
      (r) => /\/watch-list\/stop$/.test(new URL(r.url()).pathname) && r.request().method() === "POST",
    );
    await page.getByTestId("watch-stop-confirm").click();
    expect((await stopped).status()).toBe(200);
    await expect(watchRow(page)).toHaveAttribute("data-status", "not_watched");
    // the item's history names who stopped it and why. The panel is taller than the window, so the picture shows the item
    // on a page of its own (the panel's Open in new tab): everything about it in one view, with Watch again
    const stoppedPanel = page.getByTestId("watch-panel");
    await expect(stoppedPanel.getByTestId("watch-history")).toContainText("We do not use it in production");
    await expect(stoppedPanel.getByTestId("watch-stop")).toHaveCount(0); // not watched: nothing to stop
    const own = await stoppedPanel.getByTestId("open-in-new-tab").getAttribute("href");
    expect(own, "the address names the page, the item and the view").toMatch(
      /^#\/a\/\d+\/change-watch\?item=[^&]+&view=page$/,
    );
    await page.goto(`/${own}`);
    const ownPage = page.getByTestId("item-page");
    await expect(ownPage.getByTestId("watch-history")).toContainText("We do not use it in production");
    await expect(ownPage.getByTestId("watch-again")).toBeVisible();
    await expect(ownPage.getByTestId("item-page-back")).toHaveText("← Back to Change watch");
    await shots(page, "09-watch-list-stopped-with-a-reason");
    await ownPage.getByTestId("item-page-back").click(); // back: the list, with this item open
    await expect(page.getByTestId("watch-list-page")).toBeVisible();
    await expect(page.getByTestId("watch-panel")).toBeVisible(); // the address still names the item
    const again = page.waitForResponse(
      (r) => /\/watch-list\/watch$/.test(new URL(r.url()).pathname) && r.request().method() === "POST",
    );
    await page.getByTestId("watch-panel").getByTestId("watch-again").click();
    expect((await again).status()).toBe(200);
    await expect(watchRow(page)).toHaveAttribute("data-status", "fix_published");
    // watched again, it offers Stop watching as a button: the box with the earlier reason is not open by itself
    await expect(page.getByTestId("watch-panel").getByTestId("watch-stop")).toBeVisible();
    await expect(page.getByTestId("watch-stop-reason")).toHaveCount(0);

    // ================================================================ Advisories: it can be tried on public copies from PyPI
    const advisories = await openAdvisories(page, assessment);
    await expect(found(page)).toHaveAttribute("data-state", "new");
    await expect(found(page).getByTestId("found-sandbox")).toHaveText("Sandbox copy");
    await expect(found(page).getByTestId("found-reason")).toHaveText(
      "A test can be tried on public copies from PyPI: starkbank-ecdsa 2.0.1, the fixed version, and the release before it.",
    );
    const prove = block(page).getByTestId("design-and-prove");
    await expect(prove).toHaveText("Design and prove tests (1)");
    await expectPlainWords(page, "Advisories before the research run", block(page));
    await shots(page, "10-advisories-it-can-be-tried-on-public-copies");
    await prove.click();
    const box = page.getByTestId("research-dialog");
    await expect(box).toContainText("What will be fetched, from the public package registry and nowhere else:");
    await expect(box).toContainText("From PyPI: starkbank-ecdsa 2.0.1 (the fixed version) and the release before it");
    await expect(box).toContainText("a copy runs only in a locked container on this computer, with no network");
    await expect(box).toContainText("the separate reviewer decides every run");
    await expect(box).toContainText("Live Otto is off: only answers recorded during the build are used.");
    await shots(page, "11-the-box-before-the-research-run");
    const beforeStart = changes(page).length;
    const started = page.waitForResponse(
      (r) =>
        /\/api\/plans\/\d+\/advisories\/research$/.test(new URL(r.url()).pathname) && r.request().method() === "POST",
    );
    await box.getByTestId("lookup-confirm").click();
    expect((await started).status()).toBe(200);
    expect(changes(page).slice(beforeStart)).toHaveLength(1);
    await expect(block(page).getByTestId("research-line")).toContainText("A research run is going on");
    const finished =
      /^The research run that started on .+ finished on .+\. Test pack (\d{4}\.\d{1,2}\.\d+), made on this computer, was installed\.$/;
    await expect(block(page).getByTestId("research-line")).toHaveText(finished, { timeout: 45 * 60_000 });
    const made = finished.exec((await block(page).getByTestId("research-line").innerText()).trim())![1]!;
    await expect(found(page).getByTestId("found-state")).toHaveText(`Proven on public copies (test pack ${made})`);
    await expect(advisoryRow(page).getByTestId("advisory-proposal")).toHaveText("Proposed");
    expect(await layoutProblems(page), "Advisories after the research run").toEqual([]);
    await shots(page, "12-advisories-after-the-run-proven-and-proposed");

    // ================================================================ the proposal, with How this test was proven
    await found(page).getByTestId("found-link").click();
    const advisoryPanel = page.locator(`[data-testid="advisory-panel"][data-advisory="${ID}"]`);
    await expect(advisoryPanel.getByTestId("advisory-sandbox-label")).toHaveText("Sandbox copy");
    const proposal = advisoryPanel.getByTestId("otto-proposal");
    await expect(proposal.getByRole("button", { name: "Accept" })).toBeEnabled();
    // The design refactor (26 November 2026): how the test was proven reads in three layers. In the open, in the test's
    // own block: the three counts that say whether the test tells the affected version from the fixed one, and what
    // they do not show. Behind the panel's one fold, whole: the trial part by part, what was frozen, the code that
    // asked the library, the public copies and the replay. The proposal's card no longer carries a copy of the proof.
    await expect(proposal.getByTestId("proof-block")).toHaveCount(0);
    const glance = advisoryPanel.getByTestId("advisory-proof-glance");
    const tile = (part: string) => glance.locator(`[data-testid="proof-tile"][data-part="${part}"]`);
    await expect(glance.getByTestId("proof-tile")).toHaveCount(3);
    await expect(tile("affected")).toContainText("starkbank-ecdsa 2.0.0");
    await expect(tile("affected").getByTestId("proof-tile-count")).toHaveText("1 of 64 cases wrong");
    await expect(tile("fixed").getByTestId("proof-tile-count")).toHaveText("All 64 cases right");
    await expect(tile("control").getByTestId("proof-tile-count")).toHaveText("64 of 64 cases wrong");
    await expect(glance.getByTestId("proof-not-shown")).toContainText("It does not say how serious the weakness is");
    const proof = advisoryPanel.getByTestId("advisory-proof-fold");
    await expect(proof.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(proof.getByTestId("proof-fold-name")).toHaveText("Cryptanalysis proof");
    await expect(proof.getByTestId("proof-rows")).toBeHidden();
    const beforeProof = changes(page);
    await openProofFold(advisoryPanel, "advisory-proof-fold");
    const rows = proof.getByTestId("proof-rows").getByTestId("proof-row");
    await expect(rows).toHaveCount(6);
    const row = (part: string) => proof.locator(`[data-testid="proof-row"][data-part="${part}"]`);
    await expect(row("affected")).toContainText("starkbank-ecdsa 2.0.0");
    await expect(row("affected").getByTestId("proof-count")).toHaveText("1 of 64 cases wrong");
    await expect(row("fixed").getByTestId("proof-count")).toHaveText("All 64 cases right");
    await expect(row("control").getByTestId("proof-count")).toHaveText("64 of 64 cases wrong");
    await expect(proof.getByTestId("proof-registered")).toHaveText(
      new RegExp(`^Registered in Otto's harness on ${LOCAL_TIME.source}, before the first run`),
    );
    await expect(proof.getByTestId("asking-code-label")).toHaveText("Written by Otto");
    // who wrote it is said as it was: this walk replays answers recorded during the build, and a recorded answer names no model
    await expect(proof.getByTestId("asking-code-line")).toContainText(
      "written for this library during the build and recorded, not written through the API",
    );
    await expect(proof.getByTestId("asking-code-line")).toContainText(
      "The screen is a filter for mistakes and plain tricks, not a proof",
    );
    await expect(proof.getByTestId("asking-code-agree")).toContainText("gave the same answer on every case: 64 of 64");
    await expect(proof.getByTestId("asking-code-agree")).toContainText("counted by the pinned trial script");
    await expect(proof.getByTestId("asking-code-known")).toContainText(
      "Each answered every question its one way, and the check refused both",
    );
    await expect(proof.getByTestId("proof-copy")).toHaveCount(4);
    await expect(proof.getByTestId("proof-left-out")).toContainText("was left out before the trial was registered");
    // counts only: neither the counts in the open nor any part of the proof says Passed or Failed (the test's own
    // pass rule, which the fold also holds under "The test", is the one place those words belong)
    for (const part of [
      glance,
      ...["trial", "frozen", "code", "copies", "replay"].map((key) => proof.getByTestId(`proof-part-${key}`)),
    ]) {
      await expect(part).toBeVisible();
      for (const word of ["Passed", "Failed"])
        expect(await part.innerText(), `the proof says ${word}`).not.toContain(word);
    }
    await shots(page, "13-the-proposal-how-this-test-was-proven");
    await proof.getByTestId("asking-code-toggle").click();
    await expect(proof.getByTestId("asking-code-source")).toContainText(
      "def check_signature(public_key, message, signature):",
    );
    await expect(proof.getByTestId("asking-code-second-source")).toContainText("parsed = Signature.fromDer(signature)");
    // the code holds code only: no description and no comment that a person could take for a result
    for (const part of ["asking-code-source", "asking-code-second-source"]) {
      expect(await proof.getByTestId(part).innerText(), `${part} holds a comment or a description`).not.toMatch(
        /#|"""/,
      );
    }
    expect(changes(page), "reading the proof and the code sent nothing").toEqual(beforeProof);
    expect(await layoutProblems(page), "Advisories with the proof and the code open").toEqual([]);
    await shots(page, "14-the-code-that-asked-the-library");
    // the same advisory on a page of its own (Open in new tab): the proposal with its whole proof in one view
    await page.goto(`/#/a/${assessment}/advisories?item=${ID}&view=page`);
    const whole = page.getByTestId("otto-proposal");
    await expect(whole.getByRole("button", { name: "Accept" })).toBeEnabled();
    const wholePage = page.getByTestId("item-page");
    await openProofFold(wholePage, "advisory-proof-fold");
    await wholePage.getByTestId("proof-pins").locator("summary").click();
    await wholePage.getByTestId("asking-code-toggle").click();
    await expect(wholePage.getByTestId("asking-code-second-source")).toBeVisible();
    expect(changes(page), "opening the item and reading its proof sent nothing").toEqual(beforeProof);
    await shots(page, "15-the-proposal-with-its-whole-proof");
    // a person decides: Accept. It adds the check to the test plan and runs nothing.
    const accepted = page.waitForResponse(
      (r) => /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname) && r.request().method() === "POST",
    );
    await whole.getByTestId("proposal-accept").click();
    expect((await accepted).status()).toBe(200);
    await expect(whole.getByTestId("proposal-status")).toHaveText("Added");

    // ================================================================ Checks: run by the runner, decided by the separate reviewer
    await page.goto(`/#/a/${assessment}/checks?group=encryption`);
    const card = page.getByTestId("test-card").filter({ hasText: ID });
    await expect(card).toHaveCount(1);
    await expect(card).toHaveAttribute("data-status", "not_run"); // accepting ran nothing
    await card.getByRole("button", { name: /^Run / }).click();
    await expect(card).toHaveAttribute("data-status", "done", { timeout: 600_000 });
    await expect(card.getByTestId("result-badge")).toHaveText("Failed"); // starkbank-ecdsa 2.0.0 is the affected version: the reviewer's word
    // the plan was made before the library's public copy existed: the page gives that reason for the tests it lacks
    const lacks = page.getByTestId("not-tested");
    await expect(lacks).toContainText(
      "starkbank-ecdsa 2.0.0: no Independent exam (Wycheproof) test. This test plan was made before a public copy of this library could be run here. Import the file again to test it.",
    );
    await expect(lacks).not.toContainText("earlier version");
    await shots(page, "16-checks-the-accepted-check-ran");
    await openAdvisories(page, assessment);
    await expect(advisoryRow(page)).toContainText("Failed");
    await advisoryRow(page).click();
    await expect(advisoryPanel.getByTestId("advisory-here-sandbox")).toHaveText("Sandbox copy");
    await expect(advisoryPanel.getByTestId("advisory-here-result")).toHaveText("Failed");
    await shots(page, "17-advisories-the-result-on-a-sandbox-copy");
    list = await openWatchList(page, assessment);
    await expect(watchRow(page)).toHaveAttribute("data-status", "test_proposed");
    await shots(page, "18-watch-list-test-proposed");

    // ================================================================ the evidence, checked by the verify command
    await page.goto(`/#/a/${assessment}/evidence`);
    const created = page.waitForResponse(
      (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
    );
    await page.getByTestId("page-content").getByRole("button", { name: "Download evidence" }).click();
    const info = await (await created).json();
    const raw = await (await page.request.get(info.json.url)).body();
    const file = path.join(
      fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-sandbox-evidence-")),
      "evidence.json",
    );
    fs.writeFileSync(file, raw);
    const evidence = JSON.parse(raw.toString("utf-8")).evidence;
    const pack = (evidence.otto.packs as any[]).find((p) => p.pack.version === made);
    expect(pack.pack.schema).toBe("isogeny.test-pack/2");
    expect(evidence.watch_list.items.map((i: any) => i.key)).toContain(ITEM);
    const good = verify(file, copy.dataDir);
    expect(good.status, `the evidence file should check: ${good.stdout} ${good.stderr}`).toBe(0);
    expect(good.stdout).toMatch(/^Evidence verified/);
    expect(good.stdout).toMatch(
      /Sandbox research: 1 test pack made on the computer that used it, with 1 test tried on sandbox copies/,
    );
    expect(good.stdout).toMatch(
      /on a sandbox copy, each in an image named after a copy set that a test pack in the file describes/,
    );
    expect(good.stdout).toMatch(/Watch list: 1 item worked out again/);

    // ================================================================ the switch off again: nothing by itself, no second view
    settings = await openSettings(page);
    const off = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/otto/sandbox" && r.request().method() === "POST",
    );
    await settings.getByTestId("sandbox-switch").click();
    expect((await off).status()).toBe(200);
    await expect(settings.getByTestId("sandbox-switch")).not.toBeChecked();
    await page.goto(`/#/a/${assessment}/change-watch`);
    await expect(page.getByTestId("change-watch-page")).toBeVisible();
    await expect(page.getByRole("tab", { name: "Watch list" })).toHaveCount(0);
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. where it can't be turned on

test("demo mode: Sandbox research can't be turned on and says why; the pages read as they did before", async ({
  browser,
}) => {
  test.setTimeout(10 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 29, "demo", {
      EVIDENCE_LAB_SANDBOX_RESEARCH: "1",
      EVIDENCE_LAB_WATCH_CLOCK: "off",
    });
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const settings = await openSettings(page);
    await expect(settings.getByTestId("sandbox-switch")).toBeDisabled();
    await expect(settings.getByTestId("sandbox-switch-reasons")).toContainText("It needs isolated mode");
    await expect(settings.getByTestId("sandbox-status-line")).toHaveText(
      "Sandbox research is off, and can't be turned on here.",
    );
    await shots(page, "19-settings-it-cant-be-turned-on-in-demo-mode");
    const refused = await page.request.post("/api/otto/sandbox", { data: { on: true } });
    expect(refused.status(), "the backend refuses it too, whatever the page shows").toBe(409);
    await openFreshAssessment(page, "Sandbox research is off");
    await page.getByLabel("Choose a file to import").setInputFiles(FILE);
    await expect(page.getByTestId("claim-row")).toHaveCount(1);
    const assessment = assessmentOf(page);
    await page.goto(`/#/a/${assessment}/change-watch`);
    await expect(page.getByTestId("page-content")).toBeVisible();
    await expect(page.getByRole("tab", { name: "Watch list" })).toHaveCount(0); // one view, as before
    await page.goto(`/#/a/${assessment}/advisories`);
    await expect(block(page)).toBeVisible();
    await expect(block(page).getByTestId("new-advisories-sandbox")).toHaveCount(0);
    // (what the loop covers is folded under its own name since the design refactor: opened, then read)
    await block(page).getByTestId("new-advisories-covers-fold").locator("summary").click();
    await expect(block(page).getByTestId("new-advisories-covers")).toBeVisible();
    await expect(block(page).getByTestId("new-advisories-covers")).not.toContainText("Sandbox research");
  } finally {
    await stopCopy(copy);
  }
});
