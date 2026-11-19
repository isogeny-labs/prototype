// The 5c fixes end to end (19 November 2026), on a copy of the app of its own (own data folder and ports), in demo
// mode, on the Acme Pay demo, with the answers recorded during the build:
//
//   1 and 2  Checks: Encryption tests in four labelled parts. The test plan as two lists (Standard tests, Advisory
//            checks); Retests by version with Retest new version on the page; Fix proofs; nothing shown twice.
//   3        Open in new tab on every side panel: the item on a page of its own, at an address that can be opened
//            again; Back returns to the list with the panel open; an item that is not there says so.
//   4 and 5  No sentence says what Otto did. The tag "From Otto" stays.
//   6        Every time on screen is in the viewer's own time zone (this browser is in New York); the evidence file
//            and the report keep UTC.
//   7        The tag "New" on an advisory that arrived with the newest installed test pack.
//
// (Fix 8, a new Codespace, is proven by its own backend test and by a check in a real Codespace: docs/HANDOFF-overnight.md.)
// Skipped with a message when Otto is not installed on this computer. A copy of the app is started without any API
// key, so nothing here can reach Claude. Main-screen buttons only. Pictures, dark and light: docs/screenshots/phase5c-fixes/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { continueToChecks, enterApp, layoutProblems, openFreshAssessment, screenshotFolder, startCopy, stepLink, stopCopy, type Copy } from "./shared";

const SHOTS = screenshotFolder("phase5c-fixes");
const RANGE = "Missing ECDSA signature range check";
const RANGE_CHECK = `Advisory check: ${RANGE} (CVE-2022-21449)`;
// A time as the screens write it, for a viewer in New York: "18 November 2026, 7:46 pm EST".
const LOCAL_TIME = /\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d, \d{1,2}:\d\d [ap]m E[SD]T/;
// What no sentence may say (the phrases Kevin listed, and the same verbs in another tense).
const BANNED = ["Otto wrote", "Otto writes", "Otto proposes", "Otto proposed", "in Otto's words", "In Otto's words", "Why Otto proposes it", "Otto found",
                "Otto finds", "Otto has ", "Otto's proposal", "Otto asked", "Otto asks", "Otto no longer"];

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

/** A picture in the dark and the light look (`view`: only what the window shows). */
async function shots(page: Page, name: string, how: { view?: boolean } = {}): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await settled(page);
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
  const box = page.getByTestId("otto-install-dialog");
  const installed = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/otto/packs/install" && r.request().method() === "POST");
  await box.getByTestId("otto-install-confirm").click();
  expect((await installed).status()).toBe(200);
  await expect(packs.locator(`[data-testid="otto-pack-card"][data-version="${version}"]`)).toBeVisible();
}

const part = (page: Page, key: string): Locator => page.locator(`[data-testid="part-section"][data-part="${key}"]`);
const advisoryRow = (page: Page, id: string): Locator => page.locator(`[data-testid="advisory-row"][data-advisory="${id}"]`);

async function cardStatuses(page: Page): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

/** Everything a person can read on the page right now. */
async function words(page: Page): Promise<string> {
  await settled(page);
  return page.evaluate(() => document.body.innerText);
}

async function expectNoBannedWords(page: Page, where: string): Promise<void> {
  const text = await words(page);
  for (const phrase of BANNED) expect(text.includes(phrase), `${where} says “${phrase}”`).toBe(false);
}

/** The open panel's "Open in new tab": its address is opened in a new browser tab, where the item has the page to
 * itself. Returns that tab. */
async function openInNewTab(page: Page, panel: Locator, backTo: string): Promise<Page> {
  const link = panel.getByTestId("open-in-new-tab");
  await expect(link).toHaveText(/^Open in new tab\s*↗$/);
  await expect(link).toHaveAttribute("target", "_blank");
  const href = await link.getAttribute("href");
  expect(href, "the address names the item and the view").toMatch(/^#\/a\/\d+\/[a-z/]+\?item=[^&]+&view=page$/);
  const [tab] = await Promise.all([page.context().waitForEvent("page"), link.click()]);
  watchRequests(tab);
  await expect(tab.getByTestId("item-page")).toBeVisible({ timeout: 30_000 });
  expect(new URL(tab.url()).hash).toBe(href);
  // the sidebar and the top bar stay; the list is not shown; the way back names the page
  await expect(tab.getByTestId("sidebar").first()).toBeVisible();
  await expect(tab.getByTestId("page-content")).toBeHidden();
  // (the item's own page; the "not here" notice the app keeps ready behind it is never shown while the item is drawn)
  await expect(tab.getByTestId("item-page").getByTestId("item-page-back")).toHaveText(`← Back to ${backTo}`);
  await expect(tab.getByTestId("item-page-missing")).toBeHidden();
  await expect(tab.getByTestId("item-page").getByRole("button", { name: "Close details" })).toHaveCount(0);
  return tab;
}

test.describe.configure({ mode: "serial" });
test.use({ actionTimeout: 60_000 });

test("the 5c fixes: Checks in four parts, Open in new tab, wording, times in the viewer's zone, and the New tag", async ({ browser }) => {
  test.setTimeout(25 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 21, "demo");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    test.skip(!otto.harness.installed, `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
    // the browser of this walk is a viewer in New York
    expect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)).toBe("America/New_York");

    await installPack(page, "2026.11.1");
    await openFreshAssessment(page, "5c fixes walk");
    const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST");
    await page.getByRole("button", { name: "Use demo file" }).click();
    expect((await imported).status()).toBe(200);
    // fixes 4 and 5: Import's line says what may apply, marked From Otto, and not who found it
    await expect(page.getByTestId("import-otto-text")).toHaveText("2 checks may apply: 2 published weaknesses with a test, for acme-sign 1.4.2.");
    await expect(page.getByTestId("import-otto")).toContainText("From Otto");
    await expectNoBannedWords(page, "Import");
    await page.getByTestId("address-confirm").click();
    await page.getByRole("button", { name: "Verify claims" }).click();
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
    await expect(page.getByTestId("verify-otto-note")).toContainText("Nothing is proposed here yet.");
    await expectNoBannedWords(page, "Verify");
    await continueToChecks(page);
    const assessment = assessmentOf(page);

    // ================================================================ fix 7: with one pack installed, every advisory is new
    await page.goto(`/#/a/${assessment}/advisories`);
    await expect(page.getByTestId("advisory-row")).toHaveCount(3);
    const tags = page.getByTestId("advisory-row").getByTestId("advisory-new");
    await expect(tags).toHaveCount(3);
    await expect(tags.first()).toHaveAttribute("title", "Arrived with test pack 2026.11.1");
    await expect(tags.first().locator(".sr-only")).toHaveText("New: arrived with test pack 2026.11.1");
    // the column is "Proposal" (fix 4)
    await expect(page.getByTestId("advisories-table").getByRole("columnheader")).toHaveText(["Advisory", "Published", "Fits", "Test", "Proposal", "Result here"]);
    expect(await layoutProblems(page), "Advisories with the New tags").toEqual([]);
    await shots(page, "01-advisories-new-with-one-pack");

    // ---- the proposed check for CVE-2022-21449 is accepted (it runs nothing)
    await advisoryRow(page, "CVE-2022-21449").click();
    let panel = page.locator('[data-testid="advisory-panel"][data-advisory="CVE-2022-21449"]');
    await expect(panel.getByRole("heading", { level: 2 })).toContainText(RANGE);
    await expect(panel.getByRole("heading", { level: 2 }).getByTestId("advisory-new")).toHaveAttribute("title", "Arrived with test pack 2026.11.1");
    const proposal = panel.getByTestId("otto-proposal");
    await expect(proposal.getByTestId("proposal-label")).toHaveText("From Otto");
    const accepted = page.waitForResponse((r) => /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await proposal.getByTestId("proposal-accept").click();
    expect((await accepted).status()).toBe(200);
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");
    // fix 6: the time in the server's sentence is written in the viewer's own zone
    await expect(proposal.getByTestId("proposal-decided")).toHaveText(new RegExp(`^Accepted by You on ${LOCAL_TIME.source}\\.$`));
    await expect(panel.getByText("What Claude was asked")).toBeVisible();
    await expectNoBannedWords(page, "Advisories, with a panel open");
    await shots(page, "02-advisory-panel-new-and-local-time");

    // ================================================================ fixes 1 and 2: Checks, Encryption tests in four parts
    await stepLink(page, "Checks").click();
    await expect(page.getByTestId("test-card")).toHaveCount(6);
    await expect(page.getByTestId("part-section")).toHaveCount(3);          // no server change was tried: no fourth part
    await expect(part(page, "plan").getByRole("heading", { level: 3 })).toContainText("Test plan");
    await expect(part(page, "plan").getByTestId("part-count").first()).toHaveText("6 tests");
    await expect(part(page, "plan").getByTestId("part-note")).toHaveText("First runs, on the version the file names: acme-sign 1.4.2.");
    // the plan is two lists; the advisory check is in the second, marked From Otto
    const lists = part(page, "plan").getByTestId("plan-list");
    await expect(lists).toHaveCount(2);
    await expect(lists.nth(0)).toContainText("Standard tests");
    await expect(lists.nth(0).getByTestId("test-card")).toHaveCount(5);
    await expect(lists.nth(1)).toContainText("Advisory checks");
    await expect(lists.nth(1).getByTestId("plan-list-from-otto")).toHaveText("From Otto");
    await expect(lists.nth(1).getByTestId("test-card")).toHaveCount(1);
    await expect(lists.nth(1).getByRole("heading", { name: RANGE_CHECK })).toBeVisible();
    // a card moves only within its own list: the one advisory check has nowhere to go, and nothing is sent
    let reorders = 0;
    page.on("request", (r) => {
      if (/\/api\/plans\/\d+\/order$/.test(new URL(r.url()).pathname)) reorders += 1;
    });
    await lists.nth(1).getByTestId("drag-handle").press("ArrowUp");
    await lists.nth(0).getByTestId("drag-handle").last().press("ArrowDown");
    expect(reorders, "a card can't leave its own list").toBe(0);
    await lists.nth(0).getByTestId("drag-handle").last().press("ArrowUp");
    await expect.poll(() => reorders).toBe(1);
    await expect(lists.nth(1).getByTestId("test-card")).toHaveCount(1);
    // before any retest
    await expect(part(page, "retests").getByTestId("part-count").first()).toHaveText("0 versions");
    await expect(part(page, "retests").getByTestId("part-empty")).toHaveText("No retest yet. Retest new version reruns every test in the plan on another version.");
    await expect(part(page, "retests").getByRole("button", { name: "Retest new version" })).toBeDisabled();   // nothing has run yet
    await expect(part(page, "proofs").getByTestId("part-count").first()).toHaveText("0 proofs");
    // the other three groups have no parts
    await expect(page.locator('[data-testid="group-section"]:not([data-group="encryption"]) [data-testid="part-section"]')).toHaveCount(0);
    expect(await layoutProblems(page), "Checks before anything ran").toEqual([]);
    await expectNoBannedWords(page, "Checks");
    await shots(page, "03-checks-four-parts-before-any-run");

    // ---- Run all: the runner and the reviewer decide; the advisory check fails on acme-sign 1.4.2
    await page.getByRole("button", { name: "Run all" }).click();
    await expect.poll(() => cardStatuses(page), { timeout: 240_000 }).toEqual(Array(6).fill("done"));
    await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
    // a first run shows in the plan only
    await expect(part(page, "retests").getByTestId("check-row")).toHaveCount(0);

    // ---- the fix: the proposed change is accepted, the demo code connected, and the proof reruns every locked test
    await page.goto(`/#/a/${assessment}/fixes`);
    const fixRow = page.getByTestId("fix-row").filter({ has: page.getByTestId("fix-proposal-mark") }).first();
    await expect(fixRow).toBeVisible();
    const fix = page.getByTestId("fix-summary");
    if ((await fix.getByTestId("fix-proposal").count()) === 0) await fixRow.click();
    await expect(fix).toContainText("Written by Otto");
    await expect(fix).toContainText("This change is a proposal. Accept it first; accepting runs nothing.");
    await expect(fix).toContainText(/A change was written for CVE-2022-21449 \(Missing ECDSA signature range check\)\. What it would change: /);
    await expect(fix.getByTestId("proposal-why")).toContainText("Why it is proposed");
    await expectNoBannedWords(page, "Fixes, with the proposed change open");
    await shots(page, "04-fixes-a-change-was-written");
    const fixAccepted = page.waitForResponse((r) => /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await fix.getByTestId("otto-proposal").getByTestId("proposal-accept").click();
    expect((await fixAccepted).status()).toBe(200);
    await fix.getByRole("button", { name: "Connect demo code" }).click();
    await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });

    // ---- Checks: the proof has its own block, with the changed code's version
    await stepLink(page, "Checks").click();
    await expect(part(page, "proofs").getByTestId("part-count").first()).toHaveText("1 proof");
    const proof = part(page, "proofs").getByTestId("block-section");
    await expect(proof).toHaveCount(1);
    await expect(proof.getByRole("heading", { level: 4 })).toContainText("acme-sign 1.4.3-otto (the changed code)");
    await expect(proof.getByTestId("block-line")).toHaveText(new RegExp(`^The proof reran the plan's locked tests on the changed code\\. It started ${LOCAL_TIME.source}\\.$`));
    await expect(proof.getByTestId("check-row")).toHaveCount(6);
    await expect(part(page, "retests").getByTestId("check-row")).toHaveCount(0);       // a proof is not a retest

    // ---- Retest new version, from Checks: the same menu as on Evidence
    const retest = part(page, "retests").getByRole("button", { name: "Retest new version" });
    await expect(retest).toBeEnabled();
    await retest.click();
    const menu = page.getByRole("menu", { name: "Choose the version to retest" });
    await expect(menu.getByRole("menuitem")).toHaveCount(2);
    await expect(menu).toContainText("acme-sign 1.4.3");
    await shots(page, "05-checks-retest-new-version-menu", { view: true });
    const started = page.waitForResponse((r) => /\/api\/plans\/\d+\/retest$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await menu.getByRole("menuitem").filter({ hasText: "acme-sign 1.4.3" }).first().click();
    expect((await started).status()).toBe(200);
    await expect(part(page, "retests").getByTestId("retest-progress")).toContainText("Retest running");
    await expect(part(page, "retests").getByTestId("retest-progress")).toHaveCount(0, { timeout: 300_000 });
    // the retest sits in the block of the version it ran on; a server test was run again as it is
    await expect(part(page, "retests").getByTestId("part-count").first()).toHaveText("1 version");
    const block = part(page, "retests").getByTestId("block-section");
    await expect(block).toHaveCount(1);
    await expect(block.getByRole("heading", { level: 4 })).toContainText("acme-sign 1.4.3");
    await expect(block.getByTestId("block-line")).toHaveText(new RegExp(`^One retest on this version\\. The newest started ${LOCAL_TIME.source}\\.$`));
    await expect(block.getByTestId("check-row")).toHaveCount(6, { timeout: 60_000 });
    await expect(block.getByTestId("check-mark")).toHaveCount(2);                      // the two server tests
    await expect(block.getByTestId("check-mark").first()).toContainText("tested again as it is");
    // nothing shows twice: six cards in the plan, six rows in the proof, six in the retest
    await expect(part(page, "plan").getByTestId("test-card")).toHaveCount(6);
    await expect(page.getByTestId("check-row").filter({ hasText: "Last run" })).toHaveCount(0);
    // fix 6: a time the browser writes from a recorded moment
    await expect(block.getByTestId("check-row").first()).toContainText(LOCAL_TIME);
    expect(await layoutProblems(page), "Checks with a proof and a retest").toEqual([]);
    await shots(page, "06-checks-four-parts-with-a-proof-and-a-retest");
    // the retest started here shows on Evidence as before and after
    await stepLink(page, "Evidence").click();
    await expect(page.getByTestId("lab-subline")).toContainText("acme-sign 1.4.3");
    await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
    await expectNoBannedWords(page, "Evidence");

    // ================================================================ fix 3: Open in new tab, on every kind of panel
    // ---- a check (a row of the retest's block)
    await stepLink(page, "Checks").click();
    await part(page, "retests").getByTestId("check-row").filter({ hasText: RANGE }).click();
    panel = page.getByTestId("detail-panel");
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(RANGE_CHECK);
    await expect(panel.getByRole("button", { name: "Wider" })).toBeVisible();
    expect(await layoutProblems(page), "Checks with a panel open").toEqual([]);
    await shots(page, "07-checks-panel-with-open-in-new-tab");
    let tab = await openInNewTab(page, panel, "Checks");
    await expect(tab.getByTestId("item-page").getByRole("heading", { level: 1 })).toHaveText(RANGE_CHECK);
    await expect.poll(() => tab.title()).toBe(`${RANGE_CHECK} · Isogeny Labs`);
    await expect(tab.getByTestId("item-page").getByTestId("check-panel")).toContainText("From Otto");
    expect(await layoutProblems(tab), "a check on a page of its own").toEqual([]);
    await shots(tab, "08-a-check-on-a-page-of-its-own");
    // the address opens again (a bookmark), and Back returns to the list with that panel open
    const address = tab.url();
    await tab.goto("about:blank");
    await tab.goto(address);
    await expect(tab.getByTestId("item-page").getByRole("heading", { level: 1 })).toHaveText(RANGE_CHECK);
    await tab.getByTestId("item-page").getByTestId("item-page-back").click();
    await expect(tab.getByTestId("item-page")).toHaveCount(0);
    await expect(tab.getByTestId("detail-panel").getByRole("heading", { level: 2 })).toHaveText(RANGE_CHECK);
    await expect(tab.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
    // an item that is not there says so, with the way back
    await tab.goto(`/#/a/${assessment}/checks?item=test-999999&view=page`);
    const missing = tab.getByTestId("item-page-missing").filter({ visible: true });
    await expect(missing).toHaveCount(1);
    await expect(missing).toContainText("This item is not here");
    await expect(missing.getByTestId("item-page-back")).toHaveAttribute("href", `#/a/${assessment}/checks`);
    await shots(tab, "09-an-item-that-is-not-there");
    await tab.close();

    // ---- every other kind of panel: its link is there, and opens that item on a page of its own
    const kinds: Array<{ name: string; back: string; open: () => Promise<Locator>; title: RegExp }> = [
      { name: "a claim on Import", back: "Import", title: /localhost:\d+/,
        open: async () => {
          await page.goto(`/#/a/${assessment}/inventory/import`);
          await page.getByTestId("claim-row").first().click();
          return page.getByTestId("claim-panel");
        } },
      { name: "a claim on Verify", back: "Verify", title: /\S/,
        open: async () => {
          await page.goto(`/#/a/${assessment}/inventory/verify`);
          await page.getByTestId("result-row").first().click();
          return page.getByTestId("detail-panel");
        } },
      { name: "an advisory", back: "Advisories", title: new RegExp(RANGE),
        open: async () => {
          await page.goto(`/#/a/${assessment}/advisories`);
          await advisoryRow(page, "CVE-2022-21449").click();
          return page.getByTestId("detail-panel");
        } },
      { name: "a result on Evidence", back: "Evidence", title: /\S/,
        open: async () => {
          await page.goto(`/#/a/${assessment}/evidence`);
          await page.getByTestId("evidence-row").first().click();
          return page.getByTestId("detail-panel");
        } },
      { name: "a fix", back: "Fixes", title: /\S/,
        open: async () => {
          await page.goto(`/#/a/${assessment}/fixes`);
          await expect(page.getByTestId("fix-summary")).toBeVisible();
          return page.getByTestId("detail-panel");
        } },
      { name: "a system", back: "Systems", title: /\S/,
        open: async () => {
          await page.goto(`/#/a/${assessment}/migration/systems`);
          await expect(page.getByTestId("detail-panel")).toBeVisible();
          return page.getByTestId("detail-panel");
        } },
    ];
    for (const kind of kinds) {
      const opened = await kind.open();
      await expect(opened, kind.name).toBeVisible();
      const heading = (await opened.getByRole("heading", { level: 2 }).first().innerText()).trim();
      expect(heading, kind.name).toMatch(kind.title);
      const other = await openInNewTab(page, opened, kind.back);
      // the same item, with the page to itself (an advisory's heading also holds its tag)
      await expect(other.getByTestId("item-page").getByRole("heading", { level: 1 }), kind.name).toContainText(heading.split("\n")[0]);
      expect(await layoutProblems(other), `${kind.name} on a page of its own`).toEqual([]);
      if (kind.name === "a fix") await shots(other, "10-a-fix-on-a-page-of-its-own");
      if (kind.name === "an advisory") {
        // the browser tab is named after the advisory, without its tag
        await expect.poll(() => other.title()).toBe(`${RANGE} · Isogeny Labs`);
        await shots(other, "11-an-advisory-on-a-page-of-its-own");
      }
      await other.close();
    }

    // ================================================================ fix 6: files keep UTC, whatever the browser's zone
    await stepLink(page, "Evidence").click();
    const created = page.waitForResponse((r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Download evidence" }).click();
    const info = await (await created).json();
    const evidence = (await (await page.request.get(info.json.url)).body()).toString("utf-8");
    const report = await (await page.request.get(info.html.url)).text();
    for (const [name, text] of [["the evidence file", evidence], ["the report", report]] as const) {
      expect(LOCAL_TIME.test(text), `${name} holds a time in the viewer's zone`).toBe(false);
      expect(text.includes("[[time:"), `${name} holds a mark`).toBe(false);
    }
    expect(report).toContain("(UTC)");
    const decision = JSON.parse(evidence).evidence.otto.proposals.flatMap((p: any) => p.decisions)[0];
    expect(decision.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    // the Overview and the other pages: times in the viewer's zone, and no sentence about what Otto did
    for (const where of ["overview", "migration/systems", "migration/roadmap"]) {
      await page.goto(`/#/a/${assessment}/${where}`);
      await expect(page.getByTestId("page-header")).toBeVisible();
      await expectNoBannedWords(page, where);
      expect((await words(page)).match(/\d\d:\d\d UTC/), `${where} shows a time in UTC`).toBeNull();
    }
    await page.goto(`/#/a/${assessment}/overview`);
    await expect(page.getByTestId("page-content")).toContainText(LOCAL_TIME);

    // ================================================================ fix 7: a second pack: only what it brought is new
    await installPack(page, "2026.11.2");
    await page.goto(`/#/a/${assessment}/advisories`);
    await expect(page.getByTestId("advisory-row")).toHaveCount(6);
    for (const id of ["CVE-2022-21449", "CVE-2019-14859", "CVE-2019-14853"]) await expect(advisoryRow(page, id).getByTestId("advisory-new"), id).toHaveCount(0);
    for (const id of ["CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"]) {
      await expect(advisoryRow(page, id).getByTestId("advisory-new"), id).toHaveAttribute("title", "Arrived with test pack 2026.11.2");
    }
    expect(await layoutProblems(page), "Advisories with two packs").toEqual([]);
    await expectNoBannedWords(page, "Advisories with two packs");
    await shots(page, "12-advisories-new-with-two-packs");
    await page.goto("/#/settings?section=test-packs");
    await expect(page.getByTestId("test-packs")).toBeVisible();
    await expectNoBannedWords(page, "Settings");
  } finally {
    await stopCopy(copy);
  }
});
