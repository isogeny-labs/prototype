// What-if (phase 6e, first half), on a copy of the app of its own (own data folder and ports), in demo mode, on the
// Acme Pay demo with both shipped test packs installed and the demo dependency list in:
//
//   - a what-if typed to the Otto panel ("If I update elliptic to 6.5.7, how does that affect my libraries and
//     dependencies?") is answered from what the app knows, in four parts: the seven kinds of fact, each with where it
//     comes from; the try on a test copy, off with its reason because the scanner file does not name elliptic; one
//     sentence in place of an explanation; and what the facts do not show, under Hypothesis;
//   - asking sent one request, the kept exchange, and started nothing;
//   - where the page offers the retest (the file names acme-sign), the try is Evidence's own Retest new version as its
//     card: what a retest changes is said first, nothing is sent before Confirm, and Confirm sends the page's request.
//     The retest then runs, and the same question shows its results as this assessment's own;
//   - a library the app knows nothing about gets the four parts too, and says so.
//
// Skipped with a message where Otto is not installed (the test packs can't be installed there). Pictures, dark and
// light: docs/screenshots/phase6e/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { REPO, enterApp, layoutProblems, openFreshAssessment, openPageGroup, screenshotFolder, startCopy, stepLink, stopCopy, type Copy } from "./shared";

const SHOTS = screenshotFolder("phase6e");
const DEPENDENCIES_FILE = path.join(REPO, "demo/dependencies-demo.cdx.json");
const ASK = "If I update elliptic to 6.5.7, how does that affect my libraries and dependencies?";
const BANNED = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i];

let copy: Copy | null = null;
let page: Page;
const sent: string[] = [];

function watch(p: Page): void {
  p.on("request", (r: Request) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith("/api/") && r.method() !== "GET") sent.push(`${r.method()} ${url.pathname}`);
  });
}

const panel = (): Locator => page.getByTestId("otto-panel");
const reply = (): Locator => panel().getByTestId("otto-reply");
const group = (key: string): Locator => reply().locator(`[data-testid="whatif-group"][data-group="${key}"]`);
const content = (): Locator => page.getByTestId("page-content");

/** A picture of the window with `focus` at the top of the Otto panel (the panel scrolls by itself, beside the page). */
async function shots(name: string, focus: Locator): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.waitForLoadState("networkidle");
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.evaluate(() => window.scrollTo(0, 0));
    await focus.evaluate((el) => {
      const box = el.closest('[data-testid="otto-panel"]');
      if (box) box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - 12;
    });
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: false, animations: "disabled", scale: "css" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

/** Types one sentence to Otto and waits for its answer. Returns the one request it sent. */
async function say(words: string): Promise<string[]> {
  const before = sent.length;
  const answered = page.waitForResponse((r) => /\/api\/plans\/\d+\/assistant\/messages$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await panel().getByTestId("otto-box-text").fill(words);
  await panel().getByTestId("otto-box-text").press("Enter");
  expect((await answered).status()).toBe(200);
  await expect(reply().getByTestId("otto-reply-said")).toHaveText(`You said: ${words}`);
  return sent.slice(before);
}

async function installPack(version: string): Promise<void> {
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

test.describe.configure({ mode: "serial", timeout: 600_000 });
test.use({ actionTimeout: 60_000 });

test.afterAll(async () => {
  await stopCopy(copy);
});

test("a what-if is answered from what the app knows; the try is the page's own retest behind Confirm; the rest is Hypothesis", async ({ browser }) => {
  copy = await startCopy(browser, 25, "demo");
  page = copy.page;
  await page.setViewportSize({ width: 1440, height: 900 });
  watch(page);
  await enterApp(page, { ottoPanel: true });
  const otto = await (await page.request.get("/api/otto")).json();
  test.skip(!otto.harness.installed, `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);

  await installPack("2026.11.1");
  await installPack("2026.11.2");
  await openFreshAssessment(page, "What-if walk");

  // ---- the demo file, Verify, every test (the page's own buttons; the panel repeats some of them by name)
  await content().getByRole("button", { name: "Use demo file" }).click();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await page.getByTestId("address-confirm").click();
  await content().getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await content().getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByTestId("test-card").first()).toBeVisible();
  await content().getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });

  // ---- the demo dependency list
  await stepLink(page, "Dependencies").click();
  await page.getByLabel("Choose a dependency list").setInputFiles(DEPENDENCIES_FILE);
  await expect(page.getByTestId("dependency-row").first()).toBeVisible({ timeout: 60_000 });
  await page.waitForLoadState("networkidle");

  // ================================================================ the what-if about elliptic
  expect(await say(ASK)).toEqual([expect.stringMatching(/^POST \/api\/plans\/\d+\/assistant\/messages$/)]);      // one request: the kept exchange
  await expect(reply()).toHaveAttribute("data-kind", "whatif");
  await expect(reply().getByTestId("otto-reply-text")).toHaveText("What if elliptic is updated to 6.5.7?");
  await expect(reply().getByTestId("otto-reply-label")).toHaveText("From what the app knows");
  // part 1: the seven kinds of fact, in order
  await expect(reply().getByTestId("whatif-group")).toHaveCount(7);
  await expect(group("used").getByTestId("whatif-line")).toContainText("elliptic 6.5.6 is in your dependency list, under acme-ledger 5.1.0 (direct).");
  await expect(group("used").getByTestId("whatif-label")).toHaveText("From your file");
  await expect(group("needs").getByTestId("whatif-line").first()).toContainText(
    "elliptic 6.5.7 declares the same 7 packages as 6.5.6: nothing added, nothing removed, no range changed.");
  await expect(group("needs").getByTestId("whatif-label").first()).toHaveText("Package file says");
  await expect(group("needs").getByTestId("whatif-source-link").first()).toHaveAttribute("href", "https://registry.npmjs.org/elliptic/-/elliptic-6.5.7.tgz");
  await expect(group("needs").getByTestId("whatif-source").first()).toContainText("read on 2026-11-19");
  await expect(group("needs").getByTestId("whatif-quote").first()).toContainText('"bn.js": "^4.11.9"');
  await expect(group("advisories").getByTestId("whatif-line")).toHaveCount(3);
  await expect(group("advisories").getByTestId("whatif-line").first()).toContainText(
    "its publisher names 6.5.7 as the fixed version, so updating to 6.5.7 answers this advisory by the publisher's own statement");
  await expect(group("advisories").getByTestId("whatif-label").first()).toHaveText("Test pack 2026.11.2");
  await expect(group("trial").getByTestId("whatif-line")).toContainText("Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.");
  await expect(group("post_quantum").getByTestId("whatif-line")).toHaveCount(3);
  await expect(group("post_quantum").getByTestId("whatif-line").first()).toContainText("elliptic 6.5.6: Not in our knowledge base yet; elliptic 6.5.7: Not in our knowledge base yet.");
  await expect(group("blocks").getByTestId("whatif-none")).toContainText("elliptic blocks no migration track today");
  await expect(group("own_results").getByTestId("whatif-none")).toHaveText("Your scanner file does not name elliptic, so this assessment has no result of its own on it.");
  // part 2: the try is off, with the reason, and has no button
  const tried = reply().getByTestId("whatif-try");
  await expect(tried).toHaveAttribute("data-offered", "no");
  await expect(tried.getByTestId("whatif-try-reason")).toHaveText(
    "Retest new version is not offered for this. Your scanner file does not name elliptic, so there is no locked test of this assessment to rerun on it.");
  await expect(tried.getByRole("button")).toHaveCount(0);
  // part 3 and part 4
  await expect(reply().getByTestId("whatif-explanation")).toHaveText("Live Otto is off. This is what the app knows.");
  await expect(reply().getByTestId("whatif-hypothesis")).toHaveText([
    "Whether your system really loads this library needs your environment.",
    "The app has tested the library's public copy, not the programs of yours that use it.",
  ]);
  const words = await reply().innerText();
  for (const banned of BANNED) expect(words, `the what-if card: ${banned}`).not.toMatch(banned);
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Dependencies beside the panel with a what-if in it").toEqual([]);
  await shots("01-what-the-app-knows", reply().getByTestId("otto-reply-said"));
  await shots("02-the-try-off-and-the-hypotheses", reply().getByTestId("whatif-hypotheses"));
  // "See where" leads to the page that shows the fact
  await group("used").getByTestId("whatif-link").click();
  await expect(page).toHaveURL(/#\/a\/\d+\/migration\/dependencies\?item=row-\d+$/);

  // ================================================================ where the page offers the retest: its own card
  await openPageGroup(page, "Evidence", "Crypto tests");     // (the results are Evidence's Crypto tests tab)
  await expect(page.getByTestId("evidence-row").first()).toBeVisible();
  await say("What if we update acme-sign to 1.4.3?");
  await expect(reply().getByTestId("otto-reply-text")).toHaveText("What if acme-sign is updated to 1.4.3?");
  await expect(group("own_results").getByTestId("whatif-line").first()).toContainText("on acme-sign 1.4.2:");
  const offered = reply().getByTestId("whatif-try");
  await expect(offered).toHaveAttribute("data-offered", "yes");
  await expect(offered.getByTestId("whatif-try-changes")).toContainText("“Proven in this assessment” then reads this run.");
  const card = offered.getByTestId("otto-entry");
  await expect(card.getByTestId("otto-entry-title")).toHaveText("Retest new version");
  const before = sent.length;
  await card.getByRole("button", { name: "Retest new version", exact: true }).click();
  await expect(card.getByTestId("otto-confirm-names")).toHaveText("This is the Retest new version button on Evidence.");
  expect(sent.slice(before)).toEqual([]);                                  // nothing is sent before Confirm
  await shots("03-the-try-behind-confirm", card.getByTestId("otto-confirm"));
  const started = page.waitForResponse((r) => /\/api\/plans\/\d+\/retest$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await card.getByTestId("otto-confirm-button").click();
  expect((await started).status()).toBe(200);
  expect(sent.slice(before)).toEqual([expect.stringMatching(/^POST \/api\/plans\/\d+\/retest$/)]);      // the page button's own request, and only it
  // the retest runs as the page's own does; when it has finished, the same question shows its results as this assessment's own
  const plan = /\/api\/plans\/(\d+)\//.exec(sent[sent.length - 1])![1];
  await expect
    .poll(async () => {
      const lab = await (await page.request.get(`/api/plans/${plan}/lab`)).json();
      return lab.retest?.running === false && (lab.rows ?? []).some((r: { after: unknown }) => r.after);
    }, { timeout: 300_000, intervals: [1000] })
    .toBe(true);
  await say("what if we update acme-sign to 1.4.3?");
  await expect(group("own_results").getByTestId("whatif-line").filter({ hasText: "on acme-sign 1.4.3:" }).first()).toBeVisible();

  // ================================================================ a library the app knows nothing about
  await say("What if I update left-pad to 1.3.0?");
  await expect(reply().getByTestId("whatif-card")).toHaveAttribute("data-known", "no");
  // five kinds have nothing; the other two say "Not in our knowledge base yet" for what was asked
  await expect(reply().getByTestId("whatif-none")).toHaveCount(5);
  await expect(group("needs").getByTestId("whatif-line")).toHaveText("Not in our knowledge base yet. This library has no file in our knowledge base yet.");
  await expect(reply().getByTestId("whatif-hypothesis")).toHaveText(["The app holds nothing about this library, so everything about the update is open."]);
  // two updates in one sentence are not answered for the first alone
  await say("what if I update elliptic to 6.5.7 and python-ecdsa to 0.13.3?");
  await expect(reply()).toHaveAttribute("data-kind", "cannot");
  await expect(reply().getByTestId("otto-reply-text")).toContainText("A what-if is about one library and one version at a time.");

  // In the whole walk, asking sent only the kept exchanges; the one start was the retest behind Confirm.
  const asked = sent.filter((s) => /\/assistant\/messages$/.test(s)).length;
  expect(asked).toBe(5);
  expect(sent.filter((s) => /\/retest$/.test(s))).toHaveLength(1);
});
