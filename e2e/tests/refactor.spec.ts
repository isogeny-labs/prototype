// The design refactor (26 November 2026), on a copy of the app of its own (own data folder and ports: app 8040, demo
// server 8473), in demo mode, on the Acme Pay demo. Main-screen buttons only.
//
//   - the sidebar is a path: the Overview, six numbered steps, then Evidence with its four views. The four work groups
//     are tabs on their pages, and Migration plan's three views are listed under it only while one of them is open;
//   - the Observatory, before anything was checked (every place rests on the file) and after Verify and Run all (each
//     check where it belongs, in the word of its own page): the map, a box's panel, the List;
//   - a result reads in three layers: the answer, what it shows, and one fold that is shut until it is clicked. The
//     fold is a Cryptanalysis proof for a result proven on a copy and a Technical record for an observed one;
//   - History of this check, in a result's panel: each run with who started it and that the separate reviewer decided
//     it, and what a person did about it;
//   - Results, By version, after a retest on acme-sign 1.4.3; a fix in three layers;
//   - Evidence's other three views: the Timeline (one entry for one press, its runs counted by the reviewer's words),
//     Approvals and decisions, and Evidence files (a download is listed with its fingerprint and who);
//   - reading the Observatory, the Timeline, the decisions and the files sends nothing but reads;
//   - every page with a result still shows the standing line, and the downloaded evidence file verifies.
//
// Every new page is measured at 1440 pixels wide. Pictures, dark and light: docs/screenshots/design-refactor/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND,
  DISCLAIMER,
  MIGRATION_VIEWS,
  PYTHON,
  SIDEBAR_PAGES,
  closeResult,
  continueToChecks,
  enterApp,
  evidenceRow,
  layoutProblems,
  openFoldLine,
  openFreshAssessment,
  openGroupTab,
  openMigrationView,
  openPageGroup,
  openProofFold,
  openResult,
  screenshotFolder,
  startCopy,
  stepLink,
  stepNav,
  stopCopy,
  type Copy,
} from "./shared";

const SHOTS = screenshotFolder("design-refactor");
const TESTS = [
  "Old TLS versions",
  "Certificate strength",
  "Independent exam (Wycheproof)",
  "Attacker tricks (our short list)",
  "Speed and size",
];
const EXAM = "Independent exam (Wycheproof)";
const TLS_FIX = "Server accepts TLS 1.2";
const BANNED = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i, /time to hack/i];

let copy: Copy | null = null;
let page: Page;
let assessment = "";
// Every request of the page that is not a read, as "POST /api/...".
const sent: string[] = [];
// What the reviewer said about each test on its first run, as the Results page shows it (read once, after Run all).
const reviewed: Record<string, string> = {};

function watch(p: Page): void {
  p.on("request", (r: Request) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith("/api/") && r.method() !== "GET") sent.push(`${r.method()} ${url.pathname}`);
  });
}

const detail = (): Locator => page.getByTestId("detail-panel");
const crumbs = (): Locator => page.getByRole("navigation", { name: "Breadcrumb" });

/** One picture in the dark look and one in the light. `view`: only what the window shows. `panel`: the window is made
 * tall enough for the whole side panel, which otherwise scrolls inside itself. */
async function shots(name: string, how: { view?: boolean; panel?: boolean } = {}): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.waitForLoadState("networkidle");
  const size = page.viewportSize();
  if (how.panel && size) {
    const need = await page.evaluate(() => {
      const side = document.querySelector<HTMLElement>("aside[role='complementary']");
      return side ? side.scrollHeight + 48 : 0;
    });
    await page.setViewportSize({ width: size.width, height: Math.max(size.height, Math.min(need, 6000)) });
  }
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelectorAll('[data-testid="detail-panel"], [data-testid="detail-panel"] *').forEach((el) => {
      if (el.scrollTop > 0) el.scrollTop = 0;
    });
  });
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({
      path: path.join(SHOTS, `${name}-${theme}.png`),
      fullPage: !how.view,
      animations: "disabled",
    });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  if (how.panel && size) await page.setViewportSize(size);
}

/** The words of a result badge, without its symbol. */
async function word(scope: Locator): Promise<string> {
  return (await scope.getByTestId("result-badge").locator("span:last-child").first().innerText()).trim();
}

/** The page's own words never call anything secure (outside the one standing line), score it or rate it. */
async function noBannedWords(where: string): Promise<void> {
  const words = (await page.getByTestId("page-content").innerText()).split(DISCLAIMER).join(" ");
  for (const banned of BANNED) expect(words, `${where}: ${banned}`).not.toMatch(banned);
}

/** One of the four counts over the map: how many checks rest on that. */
function count(source: "live" | "lab" | "file" | "published"): Locator {
  return page.locator(`[data-testid="observatory-count"][data-source="${source}"]`);
}

/** A box of the map, by its name. */
function box(name: string): Locator {
  return page.locator(`[data-testid="map-box"][aria-label="${name}"]`);
}

/** A check on the map (or in the List), by its name: its word is the word of its own page. */
function mapCheck(scope: Locator, name: string): Locator {
  return scope.getByTestId("map-check").filter({ has: page.getByText(name, { exact: true }) });
}

function verifyEvidence(file: string) {
  return spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", copy!.dataDir], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
}

test.describe.configure({ mode: "serial", timeout: 900_000 });

test.beforeAll(async ({ browser }) => {
  copy = await startCopy(browser, 30, "demo");
  page = copy.page;
  await page.setViewportSize({ width: 1440, height: 900 });
  watch(page);
  await enterApp(page);
});

test.afterAll(async () => {
  await stopCopy(copy);
});

test("the sidebar is six steps and then Evidence; the Observatory before anything was checked rests on the file", async () => {
  await openFreshAssessment(page, "Design refactor walk");
  assessment = /#\/a\/(\d+)/.exec(page.url())![1]!;
  const imported = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Use demo file" }).click();
  expect((await imported).status()).toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(3);

  // ---- the sidebar: the Overview, six numbered steps in the order the work goes, then Evidence with its four views
  await expect(stepNav(page).getByRole("link")).toHaveText(SIDEBAR_PAGES);
  await expect(stepNav(page).getByTestId("sidebar-step-name")).toHaveText([
    /Step 1: Bring in$/,
    /Step 2: Observe$/,
    /Step 3: Test$/,
    /Step 4: Fix$/,
    /Step 5: Plan the move$/,
    /Step 6: Keep watching$/,
    /^Evidence$/,
  ]);
  const step = (n: number) => stepNav(page).locator(`[data-testid="sidebar-step"][data-step="${n}"]`);
  await expect(step(1).getByRole("link")).toHaveText(["Import"]);
  await expect(step(2).getByRole("link")).toHaveText(["Observatory", "Verify"]);
  await expect(step(3).getByRole("link")).toHaveText(["Advisories", "Checks"]);
  await expect(step(4).getByRole("link")).toHaveText(["Fixes"]);
  await expect(step(5).getByRole("link")).toHaveText(["Migration plan"]);
  await expect(step(6).getByRole("link")).toHaveText(["Change watch"]);
  // (the list of a step is named by the step, for a screen reader)
  await expect(stepNav(page).getByRole("list", { name: "Step 2: Observe" }).getByRole("link")).toHaveCount(2);
  await expect(stepNav(page).getByRole("list", { name: "Evidence" }).getByRole("link")).toHaveText([
    "Timeline",
    "Results",
    "Approvals and decisions",
    "Evidence files",
  ]);
  // Results keeps the address Evidence always had, so every link ever made to a result still opens it
  await expect(stepLink(page, "Results")).toHaveAttribute("href", `#/a/${assessment}/evidence`);
  await expect(stepLink(page, "Timeline")).toHaveAttribute("href", `#/a/${assessment}/evidence/timeline`);
  await expect(stepNav(page).getByRole("link", { name: "Inventory", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("sidebar-groups")).toHaveCount(0);
  await shots("01-sidebar-six-steps-then-evidence", { view: true });

  // Migration plan's three views are listed under it only while one of them is open; the page has no switch of its own
  await expect(page.getByTestId("sidebar-views")).toHaveCount(0);
  await stepLink(page, "Migration plan").click();
  await expect(page.getByRole("heading", { name: "Migration plan", level: 1 })).toBeVisible();
  await expect(page.getByTestId("sidebar-views").getByRole("link")).toHaveText([...MIGRATION_VIEWS]);
  await expect(stepLink(page, "Systems")).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("group", { name: "Migration views" })).toHaveCount(0);
  await expect(crumbs()).toContainText("Migration plan");
  await expect(crumbs()).toContainText("Systems");
  // a work group is opened by its tab on the page, which says how many items it holds; the sidebar does not list it
  await stepLink(page, "Checks").click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  await expect(page.getByTestId("sidebar-views")).toHaveCount(0);
  const tabs = page.getByRole("tablist", { name: "Work groups" });
  for (const group of ["Verification", "Crypto tests", "Migration", "Dependencies"])
    await expect(tabs.getByRole("tab", { name: group, exact: true })).toBeVisible();
  await expect(tabs.getByTestId("group-tab-total")).toHaveCount(4);
  await expect(page.getByTestId("history-of-page")).toHaveText("History of Checks");

  // ---- the Observatory, right after the file came in: what the file says, and nothing checked yet
  const before = sent.length;
  await stepLink(page, "Observatory").click();
  const observatory = page.getByTestId("observatory-page");
  await expect(page.getByRole("heading", { name: "Observatory", level: 1 })).toBeVisible();
  await expect(stepLink(page, "Observatory")).toHaveAttribute("aria-current", "page");
  await expect(observatory).toHaveAttribute("data-state", "file_only");
  await expect(page.getByTestId("observatory-banner")).toContainText("Nothing has been checked yet.");
  await expect(page.getByTestId("observatory-banner-link")).toHaveText("Open Verify");
  await expect(page.getByTestId("observatory-banner-link")).toHaveAttribute("href", /\/inventory\/verify$/);
  await expect(count("live")).toHaveAttribute("data-count", "0");
  await expect(count("lab")).toHaveAttribute("data-count", "0");
  await expect(count("published")).toHaveAttribute("data-count", "0");
  expect(Number(await count("file").getAttribute("data-count"))).toBeGreaterThan(0);
  // the two parts the scanner file names, each resting on the file; no check has a result
  await expect(page.getByTestId("map-box")).toHaveCount(2);
  await expect(page.getByTestId("map-box").getByTestId("map-box-tag")).toHaveText(["From your file", "From your file"]);
  await expect(box("acme-sign 1.4.2")).toBeVisible();
  const words = await page.getByTestId("map-check-word").allInnerTexts();
  expect(words.length).toBeGreaterThan(0);
  expect(
    words.every((w) => /^Not (checked|measured) yet$/.test(w.trim())),
    `before any check, every place says so: ${words.join(", ")}`,
  ).toBe(true);
  await expect(page.getByTestId("observatory-gaps").getByTestId("observatory-gap").first()).toBeVisible();
  // it is no start button: the only buttons are the two views and the boxes' own names
  const buttons = (await observatory.getByRole("button").allInnerTexts()).map((b) => b.trim());
  expect(buttons.slice(0, 2)).toEqual(["Map", "List"]);
  for (const name of buttons) expect(name).not.toMatch(/^(Run|Verify|Measure|Retest|Apply|Start|Try)/);
  expect(await layoutProblems(page), "the Observatory before any check").toEqual([]);
  await noBannedWords("the Observatory before any check");
  await shots("02-observatory-before-anything-was-checked");
  expect(sent.slice(before), "opening the Observatory sent nothing but reads").toEqual([]);
});

test("the Observatory after Verify and Run all: each check where it belongs, in the word of its own page", async () => {
  // Verify the claims and run every test, with the pages' own buttons
  await stepLink(page, "Import").click();
  await page.getByTestId("address-confirm").click();
  await expect(page.getByTestId("address-confirm")).toBeChecked();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
  await continueToChecks(page);
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 240_000 });
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled({ timeout: 60_000 });

  // what the reviewer said about each test, as Results shows it: the map and the Timeline must repeat exactly this
  await openPageGroup(page, "Results", "Crypto tests");
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  for (const title of TESTS) reviewed[title] = await word(evidenceRow(page, title));
  expect(reviewed[EXAM]).toBe("Failed");

  const before = sent.length;
  await stepLink(page, "Observatory").click();
  const observatory = page.getByTestId("observatory-page");
  await expect(observatory).toHaveAttribute("data-state", "checked");
  await expect(page.getByTestId("observatory-banner")).toHaveCount(0);
  // the four counts: two claims and two tests were observed on the server, one claim and three tests ran on a copy
  await expect(count("live")).toHaveAttribute("data-count", "4");
  await expect(count("lab")).toHaveAttribute("data-count", "4");
  // a box whose results all rest on the same thing says its tag once
  const server = box("Acme Pay token-signing endpoint");
  const program = box("acme-sign 1.4.2");
  await expect(server).toContainText(copy!.server);
  await expect(server.getByTestId("map-box-tag")).toHaveText("Observed live");
  await expect(program.getByTestId("map-box-tag")).toHaveText("Proven in the lab");
  // every test of the plan is on the map under its own name, with the reviewer's word, and is a link to its result
  const map = page.getByTestId("observatory-map");
  for (const title of TESTS) {
    await expect(mapCheck(map, title).getByTestId("map-check-word"), title).toHaveText(reviewed[title]!);
    await expect(mapCheck(map, title).getByTestId("map-check-link"), title).toHaveAttribute(
      "href",
      /\/evidence\?item=test-\d+$/,
    );
  }
  await expect(mapCheck(server, "Old TLS versions")).toHaveCount(1); // a server test sits on the server
  await expect(mapCheck(program, EXAM)).toHaveCount(1); // a test of the program sits on the program
  // Verify's own word for the claim the file got wrong
  const tlsSpot = server.getByTestId("map-spot").filter({ hasText: "The file says TLS 1.3 only" });
  await expect(mapCheck(tlsSpot, "The claim").getByTestId("map-check-word")).toHaveText("False");
  // what was not measured says so (Measure status was not pressed), and has no look of a result
  await expect(mapCheck(program, "Post-quantum status").getByTestId("map-check-word")).toHaveText("Not measured yet");
  // the connection the app made is drawn from this computer, with what it saw; the legend says what a line means
  await expect(map).toContainText("TLS · 1.3 and 1.2 accepted");
  await expect(page.getByTestId("map-legend")).toContainText("A connection we made from this computer");
  expect(await layoutProblems(page), "the Observatory, the map").toEqual([]);
  await noBannedWords("the Observatory");
  await shots("03-observatory-after-verify-and-run-all");

  // ---- a box's name opens its panel: its checks in their own words, its fixes, and the file's lines behind one fold
  await server.getByTestId("map-box-open").click();
  const panel = page.getByTestId("box-panel");
  await expect(detail().getByRole("heading", { level: 2 })).toHaveText("Acme Pay token-signing endpoint");
  await expect(detail().getByTestId("panel-kicker")).toContainText("Observatory");
  await expect(panel.getByTestId("source-line")).toContainText("Observed live");
  await expect(panel.getByTestId("box-summary")).toHaveText(
    "2 claims: 1 False, 1 True. 2 server tests: 1 Failed, 1 Passed. Post-quantum status: Not measured yet.",
  );
  const boxCheck = panel.getByTestId("box-check").filter({ hasText: "Old TLS versions" });
  await expect(boxCheck.getByTestId("box-check-word")).toHaveText(reviewed["Old TLS versions"]!);
  await expect(boxCheck.getByTestId("box-check-fix-link")).toBeVisible();
  await expect(panel.getByTestId("box-fixes")).toContainText(TLS_FIX);
  const record = panel.getByTestId("box-record");
  await expect(record.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(record.getByTestId("proof-fold-name")).toHaveText("Technical record"); // a box was observed, not tested
  await expect(panel.getByTestId("box-file-lines").first()).toBeHidden();
  await expect(panel.getByRole("button", { name: /^(Run|Verify|Measure|Retest|Apply|Try)/ })).toHaveCount(0);
  expect(await layoutProblems(page), "the Observatory, a box open").toEqual([]);
  await shots("04-observatory-a-box-open", { panel: true });
  await openProofFold(panel, "box-record");
  await expect(panel.getByTestId("box-file-lines").first()).toContainText(
    "Read from the file as data. Nothing in it is run.",
  );
  await detail().getByRole("button", { name: "Close details" }).click();
  await expect(detail()).toHaveCount(0);

  // ---- Map and List show the same thing; the List is a table
  const views = page.getByRole("group", { name: "Observatory view" });
  await views.getByRole("button", { name: "List" }).click();
  await expect(views.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
  const list = page.getByTestId("observatory-list");
  await expect(list.getByRole("table", { name: "Your systems, as a list" })).toBeVisible();
  await expect(page.getByTestId("observatory-map")).toHaveCount(0);
  for (const title of TESTS)
    await expect(mapCheck(list, title).getByTestId("map-check-word"), `the List: ${title}`).toHaveText(
      reviewed[title]!,
    );
  await expect(list.getByTestId("list-lines")).toContainText(
    "A connection we made from this computer (handshakes only)",
  );
  expect(await layoutProblems(page), "the Observatory, the List").toEqual([]);
  await shots("05-observatory-list");
  await views.getByRole("button", { name: "Map" }).click();
  await expect(page.getByTestId("observatory-map")).toBeVisible();
  expect(sent.slice(before), "looking at the Observatory, a box and the List sent nothing but reads").toEqual([]);
});

test("a result reads in three layers; its fold is shut until clicked and named by what the result rests on", async () => {
  await openPageGroup(page, "Results", "Crypto tests");
  // the page that was Evidence is the Results view of the Evidence section
  await expect(page.getByRole("heading", { name: "Results", level: 1 })).toBeVisible();
  await expect(stepLink(page, "Results")).toHaveAttribute("aria-current", "page");
  await expect(crumbs()).toContainText("Evidence");
  await expect(crumbs()).toContainText("Results");
  await expect(page.getByTestId("page-header")).toContainText("Evidence");
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);

  // ---- a result that was proven on a copy
  const exam = await openResult(page, EXAM);
  // the slim tool row: what the item is, and the panel's buttons; the title has the next line to itself
  const tools = detail().getByTestId("panel-tools");
  await expect(tools.getByTestId("panel-kicker")).toHaveText("Result · Crypto tests");
  await expect(tools.getByTestId("open-in-new-tab")).toBeVisible();
  for (const name of ["Wider", "Narrower", "Close details"])
    await expect(tools.getByRole("button", { name })).toBeVisible();
  await expect(tools.getByRole("heading")).toHaveCount(0);
  // the trail on top: where the result sits between its claim and its fix
  await expect(exam.getByTestId("trail").getByTestId("trail-here")).toContainText("Result");
  await expect(exam.getByTestId("trail").getByTestId("trail-here")).toContainText("Failed");
  expect(
    await exam.getByTestId("trail-step").evaluateAll((all) => all.map((step) => step.getAttribute("data-kind"))),
  ).toEqual(["claim", "fix"]);
  // layer 1, the answer: the reviewer's word, what it rests on, one plain sentence, where it ran, the control, the next step
  const glance = exam.getByTestId("result-glance");
  expect(await word(glance)).toBe("Failed");
  await expect(glance.getByTestId("source-tag")).toHaveText("Proven in the lab");
  await expect(glance.getByTestId("result-plain")).toContainText("got 3 of the 484 exam cases wrong");
  await expect(glance.getByTestId("source-note")).toContainText("Your live system was not touched.");
  await expect(glance.getByTestId("control-line")).toHaveText(
    "Control: a deliberately broken signer failed this test, as expected.",
  );
  await expect(glance.getByTestId("show-on-the-map")).toBeVisible();
  await expect(glance.getByTestId("fix-line").getByRole("button", { name: "View in Fixes" })).toBeEnabled();
  // layer 2, always in the open
  await expect(exam.getByTestId("result-shows")).toContainText("What this shows, and what it doesn't");
  await expect(exam.getByTestId("result-shows")).toBeVisible();
  // layer 3, one fold, shut until it is clicked: its name fits a result that was tested, and its header says what is inside
  const fold = exam.getByTestId("proof-fold");
  await expect(fold).toHaveCount(1);
  await expect(fold.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(fold.getByTestId("proof-fold-name")).toHaveText("Cryptanalysis proof");
  await expect(fold.getByTestId("proof-fold-inside")).toHaveText(
    "What happened · The control · The locked test · The run record",
  );
  for (const inside of ["technical-summary", "what-happened", "control-outcome", "locked-test", "spec-fingerprint"])
    await expect(exam.getByTestId(inside), `${inside} is behind the fold`).toBeHidden();
  // the foot of the panel: three quiet folded lines
  for (const line of ["runs-fold", "history-fold", "related-fold"])
    await expect(exam.getByTestId(line).getByRole("button").first(), line).toHaveAttribute("aria-expanded", "false");
  expect(await layoutProblems(page), "Results, a result open, its fold shut").toEqual([]);
  await shots("06-a-result-folded", { panel: true });

  // one click opens it: every record, whole, in numbered parts
  await openProofFold(exam);
  for (const inside of ["technical-summary", "what-happened", "control-outcome", "locked-test", "spec-fingerprint"])
    await expect(exam.getByTestId(inside), `${inside} shows once the fold is open`).toBeVisible();
  expect(
    await fold
      .locator('[data-testid^="proof-part-"]')
      .evaluateAll((all) => all.map((p) => p.getAttribute("data-part"))),
  ).toEqual(["1", "2", "3", "4"]);
  await expect(exam.getByTestId("technical-summary")).toContainText("3 of 484 official cases wrong");
  await expect(exam.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  await expect(exam.getByTestId("spec-fingerprint")).toHaveText(/^[0-9a-f]{64}$/);
  expect(await layoutProblems(page), "Results, a result open, its fold open").toEqual([]);
  await shots("07-a-result-with-its-cryptanalysis-proof-open", { panel: true });
  // ... and one more click shuts it again
  await fold.getByTestId("proof-fold-toggle").click();
  await expect(fold.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(exam.getByTestId("locked-test")).toBeHidden();

  // ---- History of this check: each run with who started it and who decided it, and what a person did about it
  await exam.getByRole("button", { name: "Mark reviewed" }).click();
  await expect(exam.getByTestId("reviewed-note")).toContainText("You marked this result as reviewed.");
  const read = sent.length;
  const history = await openFoldLine(exam, "history-fold");
  await expect(history.getByTestId("history-decides")).toContainText(
    "Who decides a result: the separate reviewer, by fixed rules, on every run. No person approves a result.",
  );
  const run = history.getByTestId("history-line").filter({ hasText: "First run on acme-sign 1.4.2" });
  await expect(run).toHaveCount(1);
  await expect(run.getByTestId("history-result")).toHaveText("Failed");
  await expect(run.getByTestId("history-said")).toHaveText("started by You, with Run all");
  await expect(run.getByTestId("history-decided-by")).toHaveText("decided by the separate reviewer");
  const marked = history.getByTestId("history-line").filter({ hasText: "Marked reviewed" });
  await expect(marked.getByTestId("history-said")).toHaveText("by You");
  await expect(marked.getByTestId("history-decided-by")).toHaveCount(0); // a person's decision is no result
  await expect(history.getByTestId("history-line").filter({ hasText: "Test details locked" })).toHaveCount(1);
  await expect(history.getByTestId("history-timeline")).toHaveAttribute("href", /\/evidence\/timeline\?group=checks$/);
  expect(sent.slice(read), "reading a check's history sent nothing but reads").toEqual([]);
  await shots("08-history-of-this-check", { panel: true });

  // ---- Show on the map: the Observatory opens on the box this result sits in; Back returns to Results
  await glance.getByTestId("show-on-the-map").click();
  await expect(page.getByTestId("observatory-page")).toBeVisible();
  await expect(page.getByTestId("box-panel")).toBeVisible();
  await expect(detail().getByRole("heading", { level: 2 })).toHaveText("acme-sign 1.4.2");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Results", level: 1 })).toBeVisible();
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);

  // ---- a result that was observed on the live server: the same three layers, and the fold is a Technical record
  const tls = await openResult(page, "Old TLS versions");
  await expect(tls.getByTestId("result-glance").getByTestId("source-tag")).toHaveText("Observed live");
  await expect(tls.getByTestId("result-glance").getByTestId("source-note")).toContainText("with handshakes only");
  await expect(tls.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(tls.getByTestId("proof-fold-name")).toHaveText("Technical record");
  await expect(tls.getByTestId("locked-test")).toBeHidden();
  await openProofFold(tls);
  await expect(tls.getByTestId("locked-test")).toBeVisible();
  await expect(tls.getByTestId("technical-summary")).toBeVisible();
  expect(await layoutProblems(page), "Results, an observed result open, its fold open").toEqual([]);
  await shots("09-an-observed-result-with-its-technical-record", { panel: true });
  await closeResult(page);
});

test("Results by version after a retest on acme-sign 1.4.3; a fix reads in three layers", async () => {
  // ---- Retest new version: acme-sign 1.4.3 (the page's own button)
  await openPageGroup(page, "Results", "Crypto tests");
  await page.getByRole("button", { name: "Retest new version" }).click();
  await page.getByRole("menu").getByRole("menuitem").filter({ hasText: "acme-sign 1.4.3" }).click();
  await expect(page.getByTestId("lab-columns")).toContainText("After: acme-sign 1.4.3");
  await expect(page.getByTestId("lab-subline")).toContainText("Retest finished", { timeout: 300_000 });
  await expect(page.getByTestId("retest-progress")).toHaveCount(0);

  // Now: before and after, as the page always showed a retest
  const view = page.getByRole("group", { name: "Results view" });
  await expect(view.getByRole("button", { name: "Now" })).toHaveAttribute("aria-pressed", "true");
  const now: Record<string, string[]> = {};
  for (const title of TESTS) {
    const row = evidenceRow(page, title);
    now[title] = [await word(row.getByTestId("lab-cell-before")), await word(row.getByTestId("lab-cell-after"))];
    expect(now[title]![0], `${title}: the first run reads as it did`).toBe(reviewed[title]);
  }
  expect(now[EXAM]).toEqual(["Failed", "Passed"]);

  // By version: every test of the plan on every version it ran on, side by side, in the same words
  await view.getByRole("button", { name: "By version" }).click();
  await expect(view.getByRole("button", { name: "By version" })).toHaveAttribute("aria-pressed", "true");
  const versions = page.getByTestId("by-version");
  await expect(versions.getByRole("table", { name: "Results by version" })).toBeVisible();
  await expect(versions.getByTestId("version-column")).toHaveCount(2);
  await expect(versions.getByTestId("version-column").nth(0)).toContainText("First run");
  await expect(versions.getByTestId("version-column").nth(1)).toContainText("acme-sign 1.4.3");
  await expect(versions.getByTestId("version-row")).toHaveCount(5);
  for (const title of TESTS) {
    const cells = versions
      .getByTestId("version-row")
      .filter({ has: page.getByText(title, { exact: true }) })
      .getByTestId("version-cell");
    await expect(cells, title).toHaveCount(2);
    expect([await word(cells.nth(0)), await word(cells.nth(1))], `${title}, by version`).toEqual(now[title]);
  }
  // a server test that ran again on an unchanged server says so
  const serverTest = versions.getByTestId("version-row").filter({ has: page.getByText("Old TLS versions") });
  await expect(serverTest.getByTestId("version-cell").nth(1).getByTestId("version-mark")).toHaveText(
    "tested again as it is",
  );
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  expect(await layoutProblems(page), "Results, By version").toEqual([]);
  await noBannedWords("Results, By version");
  await shots("10-results-by-version-after-a-retest");
  await view.getByRole("button", { name: "Now" }).click();
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);

  // ---- a fix: the trail, what it does and its change box in the open; its records behind one fold
  await stepLink(page, "Fixes").click();
  await openGroupTab(page, "Crypto tests", "Fixes");
  await expect(page.getByTestId("history-of-page")).toHaveText("History of Fixes");
  await page
    .getByRole("navigation", { name: /^Open findings with a fix/ })
    .getByRole("button")
    .filter({ hasText: TLS_FIX })
    .click();
  await expect(detail().getByRole("heading", { level: 2, name: TLS_FIX })).toBeVisible();
  await expect(detail().getByTestId("panel-kicker")).toHaveText("Fix · Crypto tests");
  await expect(detail().getByTestId("trail").getByTestId("trail-here")).toContainText("Fix");
  expect(
    await detail()
      .getByTestId("trail-step")
      .evaluateAll((all) => all.map((step) => step.getAttribute("data-kind"))),
  ).toEqual(["claim", "test"]);
  const summary = detail().getByTestId("fix-summary");
  await expect(summary.getByTestId("fix-status")).toHaveText("Ready to try");
  await expect(summary.getByTestId("source-line")).toContainText("Observed live");
  await expect(detail().getByTestId("change-box").getByRole("button", { name: "Try on a test copy" })).toBeEnabled();
  // the fold: shut, and a Technical record, because this finding was observed on the server
  const fixFold = detail().getByTestId("fix-proof-fold");
  await expect(fixFold.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(fixFold.getByTestId("proof-fold-name")).toHaveText("Technical record");
  await expect(fixFold.getByTestId("proof-fold-inside")).toHaveText("The suggestion");
  await expect(detail().getByTestId("text-suggestion")).toBeHidden();
  const touches = detail().getByTestId("impact-fold").getByRole("button").first();
  await expect(touches).toHaveAttribute("aria-expanded", "false");
  await expect(touches).toContainText("What this change touches");
  for (const line of ["history-fold", "related-fold"])
    await expect(detail().getByTestId(line).getByRole("button").first(), line).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  expect(await layoutProblems(page), "Fixes, a fix open, its fold shut").toEqual([]);
  await shots("11-a-fix-folded", { panel: true });
  await openProofFold(detail(), "fix-proof-fold");
  await expect(detail().locator('[data-testid="fix-section"][data-section="suggestion"]')).toBeVisible();
  await expect(detail().getByTestId("text-suggestion")).toContainText("Before you switch TLS 1.2 off:");
  await openFoldLine(detail(), "impact-fold");
  await expect(detail().getByTestId("impact").getByTestId("impact-count")).toBeVisible();
  expect(await layoutProblems(page), "Fixes, a fix open, its fold open").toEqual([]);
  await shots("12-a-fix-with-its-fold-open", { panel: true });
  // a fix whose code is not connected has no record yet, so it has no fold: the page says what will appear
  await page
    .getByRole("navigation", { name: /^Open findings with a fix/ })
    .getByRole("button")
    .filter({ hasText: "acme-sign accepts out-of-range signatures" })
    .click();
  await expect(detail().getByTestId("fix-summary").getByTestId("fix-status")).toHaveText("Code not connected");
  await expect(detail().getByTestId("fix-proof-fold")).toHaveCount(0);
  await expect(detail().getByTestId("fix-sections-note")).toContainText("once the code is connected");
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
});

test("Evidence is the full record: the Timeline, Approvals and decisions, Evidence files; reading sends nothing; the file verifies", async () => {
  const before = sent.length;

  // ---- the Timeline: everything that happened, newest first, one entry for one press
  await stepLink(page, "Timeline").click();
  const timeline = page.getByTestId("timeline-page");
  await expect(page.getByRole("heading", { name: "Timeline", level: 1 })).toBeVisible();
  await expect(crumbs()).toContainText("Evidence");
  await expect(crumbs()).toContainText("Timeline");
  await expect(timeline.getByTestId("timeline-subline")).toContainText("Reading it runs nothing.");
  await expect(timeline.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  const where = page.getByRole("group", { name: "Where" });
  const what = page.getByRole("group", { name: "What" });
  await expect(where.getByRole("button", { name: /^All/ })).toHaveAttribute("aria-pressed", "true");
  await expect(what.getByRole("button", { name: /^Everything/ })).toHaveAttribute("aria-pressed", "true");
  const entries = timeline.getByTestId("timeline-entry");
  // newest first: the retest, the mark, Run all, Verify, the tick, the file, the start of the assessment
  await expect(entries.getByTestId("timeline-sentence")).toHaveText([
    "Retest on acme-sign 1.4.3: the 5 tests in the plan.",
    /^Marked reviewed: /,
    "Run all: the 5 tests in the plan.",
    "Verify: the 3 claims of your file, checked against what was found.",
    /^Confirmed “I own this system” for /,
    /^Brought in acme-pay-cbom\.json: 3 claims, 1 server and 1 program\.$/,
    /^Assessment 1 started/,
  ]);
  // Run all is one entry for its five runs, counted by the reviewer's own words; no person decided a result
  const runAll = entries.filter({ hasText: "Run all: the 5 tests in the plan." });
  const counted: Record<string, number> = {};
  for (const text of await runAll.getByTestId("timeline-count").allInnerTexts()) {
    const found = /^(.+?)\s+(\d+)$/.exec(text.replace(/\s+/g, " ").trim());
    expect(found, `a count reads as a word and a number: ${text}`).not.toBeNull();
    counted[found![1]!] = Number(found![2]);
  }
  const expected: Record<string, number> = {};
  for (const title of TESTS) expected[reviewed[title]!] = (expected[reviewed[title]!] ?? 0) + 1;
  expect(counted, "the entry counts its runs by the words Results shows").toEqual(expected);
  await expect(runAll.getByTestId("timeline-decided-by")).toContainText("decided by the separate reviewer");
  await expect(runAll.getByTestId("record-who")).toContainText("You");
  await expect(runAll.getByTestId("record-button")).toHaveText("with Run all");
  await expect(runAll.getByTestId("timeline-area")).toHaveText("Checks");
  // a claim on Verify is decided by fixed rules, and the page says that
  await expect(entries.filter({ hasText: "Verify: the 3 claims" }).getByTestId("timeline-decided-by")).toContainText(
    "decided by fixed rules",
  );
  // what a person did carries no "decided by": it is no result
  await expect(entries.filter({ hasText: "Marked reviewed" }).getByTestId("timeline-decided-by")).toHaveCount(0);
  expect(await layoutProblems(page), "the Timeline").toEqual([]);
  await noBannedWords("the Timeline");
  await shots("13-timeline");
  // the two rows of filters narrow by place and by kind, never by what a result rests on
  await where.getByRole("button", { name: /^Checks/ }).click();
  await expect(where.getByRole("button", { name: /^Checks/ })).toHaveAttribute("aria-pressed", "true");
  await expect(entries).toHaveCount(3);
  expect(await entries.evaluateAll((all) => all.map((e) => e.getAttribute("data-area")))).toEqual(
    Array(3).fill("checks"),
  );
  await what.getByRole("button", { name: /^Runs and results/ }).click();
  await expect(entries).toHaveCount(2);
  await what.getByRole("button", { name: /^Everything/ }).click();
  await where.getByRole("button", { name: /^All/ }).click();
  await expect(entries).toHaveCount(7);

  // ---- an entry opens its story: who, each run it started with the reviewer's own word, the record folded
  await runAll.getByRole("button").first().click();
  const story = page.getByTestId("entry-panel");
  await expect(detail().getByRole("heading", { level: 2 })).toHaveText("Run all");
  await expect(detail().getByTestId("panel-kicker")).toHaveText("Checks · Runs and results");
  await expect(story.getByTestId("entry-summary")).toHaveText("Run all: the 5 tests in the plan.");
  await expect(story.getByTestId("entry-who")).toContainText("Started by");
  await expect(story.getByTestId("entry-who").getByTestId("record-who")).toContainText("You");
  await expect(story.getByTestId("entry-decided-by")).toHaveText(
    "Each result here was decided by the separate reviewer.",
  );
  const runs = story.getByTestId("entry-run");
  await expect(runs).toHaveCount(5);
  for (const title of TESTS)
    await expect(
      runs.filter({ has: page.getByText(title, { exact: true }) }).getByTestId("entry-run-result"),
      title,
    ).toHaveText(reviewed[title]!);
  const ids = story.getByTestId("entry-record");
  await expect(ids.getByTestId("proof-fold-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(ids.getByTestId("proof-fold-name")).toHaveText("Technical record");
  await expect(story.getByRole("button", { name: /^(Run|Verify|Measure|Retest|Apply|Try)/ })).toHaveCount(0);
  expect(await layoutProblems(page), "the Timeline, an entry open").toEqual([]);
  await shots("14-timeline-an-entry-open", { panel: true });
  await openProofFold(story, "entry-record");
  await expect(story.getByTestId("entry-fact").first()).toBeVisible();
  await detail().getByRole("button", { name: "Close details" }).click();
  await expect(detail()).toHaveCount(0);

  // "History of Checks", in a page's header, opens the Timeline with that page already chosen
  await stepLink(page, "Checks").click();
  await page.getByTestId("history-of-page").click();
  await expect(page).toHaveURL(/\/evidence\/timeline\?group=checks$/);
  await expect(where.getByRole("button", { name: /^Checks/ })).toHaveAttribute("aria-pressed", "true");
  await expect(entries).toHaveCount(3);

  // ---- Approvals and decisions: what people decided, one row each; no result is in the list, and the page says why
  await stepLink(page, "Approvals and decisions").click();
  const decisions = page.getByTestId("decisions-page");
  await expect(page.getByRole("heading", { name: "Approvals and decisions", level: 1 })).toBeVisible();
  await expect(decisions.getByTestId("decisions-results-note")).toContainText(
    "Results are not in this list: no person decides one.",
  );
  await expect(decisions.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(decisions.getByTestId("summary-card")).toHaveCount(4);
  await expect(decisions.locator('[data-testid="summary-card"]').last()).toContainText("Not yet"); // no sign-off yet
  const rows = decisions.getByTestId("decision-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.getByTestId("decision-word")).toHaveText(["Marked reviewed", "Confirmed “I own this system”"]);
  for (const row of await rows.all()) await expect(row.getByTestId("decision-who")).toContainText("You");
  await expect(rows.filter({ hasText: /Failed|Passed|Measured/ }).getByTestId("decision-word")).toHaveText([
    "Marked reviewed", // (the row names the result it is about; the decision itself is the person's)
  ]);
  expect(await layoutProblems(page), "Approvals and decisions").toEqual([]);
  await noBannedWords("Approvals and decisions");
  await shots("15-approvals-and-decisions");
  // a row opens the same story the Timeline shows
  await rows.first().click();
  await expect(page.getByTestId("entry-panel").getByTestId("entry-who")).toContainText("You");
  expect(await layoutProblems(page), "Approvals and decisions, a decision open").toEqual([]);
  await detail().getByRole("button", { name: "Close details" }).click();

  // ---- Evidence files, before any download
  await stepLink(page, "Evidence files").click();
  const files = page.getByTestId("evidence-files-page");
  await expect(page.getByRole("heading", { name: "Evidence files", level: 1 })).toBeVisible();
  await expect(files.getByTestId("evidence-files-empty")).toHaveText("The evidence file has not been downloaded yet.");
  await expect(files.getByTestId("evidence-file-row")).toHaveCount(0);
  await expect(files.getByTestId("verify-command")).toContainText("-m evidence verify");
  await expect(files.getByTestId("evidence-files-holds")).toContainText("Who did what");
  expect(await layoutProblems(page), "Evidence files").toEqual([]);
  await noBannedWords("Evidence files");
  await shots("16-evidence-files-before-a-download");

  // Reading the record ran nothing and changed nothing: the Timeline with its filters and an entry, History of Checks,
  // the decisions with one open, the files, and the Observatory once more. Not one request but reads.
  await stepLink(page, "Observatory").click();
  await expect(page.getByTestId("observatory-map")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(sent.slice(before), "reading the Timeline, the decisions, the files and the Observatory").toEqual([]);

  // ---- Download evidence: the file is listed with its time, its fingerprint and who downloaded it
  await stepLink(page, "Evidence files").click();
  const created = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
  );
  await files.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const listed = files.getByTestId("evidence-file-row");
  await expect(listed).toHaveCount(1);
  await expect(listed.getByTestId("file-fingerprint")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(listed.getByTestId("file-who")).toContainText("You");
  await expect(listed.locator("time")).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}T/);
  await expect(files.getByTestId("evidence-files-empty")).toHaveCount(0);
  const shown = (await listed.getByTestId("file-fingerprint").innerText()).trim();
  await shots("17-evidence-files-after-a-download");

  // the file itself: the fingerprint the page lists, who did what in a part of its own, and the verify command passes
  const raw = await (await page.request.get(info.json.url)).body();
  const envelope = JSON.parse(raw.toString("utf-8"));
  expect(envelope.fingerprint).toBe(shown);
  expect(envelope.evidence.disclaimer).toBe(DISCLAIMER);
  expect(JSON.stringify(envelope.evidence.actions), "the presses are in the signed file").toContain("Run all");
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-refactor-")), "evidence.json");
  fs.writeFileSync(file, raw);
  const checked = verifyEvidence(file);
  expect(checked.status, `the evidence file should check: ${checked.stdout} ${checked.stderr}`).toBe(0);
  expect(checked.stdout).toContain("Evidence verified");
  expect(checked.stdout).toContain(shown);
  // the download is itself an entry of the record
  await stepLink(page, "Timeline").click();
  await expect(timeline.getByTestId("timeline-entry").first().getByTestId("timeline-sentence")).toHaveText(
    `Evidence file downloaded. Fingerprint ${shown.slice(0, 12)}.`,
  );
});

test("Advisories opens on four numbers and its list; every page with a result keeps the standing line", async () => {
  // a test pack, so that Advisories has something to list (a pack is data: installing it runs nothing)
  await page.goto("/#/settings?section=test-packs");
  const packs = page.getByTestId("test-packs");
  await packs.getByTestId("otto-check-updates").click();
  await expect(packs.getByTestId("otto-update-line")).toContainText("2026.11.1");
  await packs.getByTestId("otto-install-update").click();
  const installed = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/otto/packs/install" && r.request().method() === "POST",
  );
  await page.getByTestId("otto-install-dialog").getByTestId("otto-install-confirm").click();
  expect((await installed).status()).toBe(200);

  await page.goto(`/#/a/${assessment}/advisories`);
  const advisories = page.getByTestId("advisories-page");
  const rows = advisories.getByTestId("advisory-row");
  await expect(rows).toHaveCount(3);
  // four numbers first, counted from the rows below
  const card = (key: string) => advisories.locator(`[data-testid="summary-card"][data-card="${key}"]`);
  await expect(advisories.getByTestId("summary-card")).toHaveCount(4);
  await expect(card("advisories")).toContainText("3");
  await expect(card("ready")).toContainText("Test ready");
  await expect(card("ready")).toContainText(String(await rows.filter({ hasText: "Test ready" }).count()));
  await expect(card("results")).toContainText("0"); // no advisory check has run
  await expect(advisories.getByTestId("history-of-page")).toHaveText("History of Advisories");
  // where the page's facts come from is one folded line: it names the packs, and opens to the three lines
  const facts = advisories.getByTestId("advisories-facts");
  await expect(facts.getByRole("button").first()).toHaveAttribute("aria-expanded", "false");
  await expect(facts).toContainText("Where this page's facts come from");
  await expect(advisories.getByTestId("advisories-packs-line")).toBeHidden();
  // what the research loop covers is one click away
  await expect(advisories.getByTestId("new-advisories-covers")).toBeHidden();
  // the standing line is on the page once, as a quiet line at its foot, under the list
  const standing = advisories.getByTestId("advisories-standing");
  await expect(standing).toHaveText(DISCLAIMER);
  const list = await advisories.getByTestId("advisories-table").boundingBox();
  const foot = await standing.boundingBox();
  expect(foot!.y, "the standing line is under the list").toBeGreaterThan(list!.y + list!.height - 1);
  expect(await layoutProblems(page), "Advisories").toEqual([]);
  await shots("18-advisories-top", { view: true });
  await openFoldLine(advisories, "advisories-facts");
  await expect(advisories.getByTestId("advisories-packs-line")).toContainText("2026.11.1");
  await advisories.getByTestId("new-advisories-covers-fold").locator("summary").click();
  await expect(advisories.getByTestId("new-advisories-covers")).toContainText("What this covers:");
  // an advisory's panel reads in the same three layers: a test tried on public copies gets a Cryptanalysis proof,
  // an advisory with no test a Technical record; both shut until clicked
  await page.locator('[data-testid="advisory-row"][data-advisory="CVE-2022-21449"]').click();
  let panel = page.locator('[data-testid="advisory-panel"][data-advisory="CVE-2022-21449"]');
  await expect(panel.getByTestId("panel-kicker")).toHaveText("Advisory");
  await expect(panel.getByTestId("advisory-test-block")).toContainText("Test ready");
  await expect(panel.getByTestId("advisory-proof-fold").getByTestId("proof-fold-toggle")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await expect(panel.getByTestId("advisory-proof-fold").getByTestId("proof-fold-name")).toHaveText(
    "Cryptanalysis proof",
  );
  await expect(panel.getByTestId("advisory-test-details")).toBeHidden();
  await openProofFold(panel, "advisory-proof-fold");
  await expect(panel.getByTestId("advisory-test-details")).toBeVisible();
  await detail().getByRole("button", { name: "Close details" }).click();
  await page.locator('[data-testid="advisory-row"][data-advisory="CVE-2019-14853"]').click();
  panel = page.locator('[data-testid="advisory-panel"][data-advisory="CVE-2019-14853"]');
  await expect(panel.getByTestId("advisory-no-test")).toBeVisible();
  await expect(panel.getByTestId("advisory-proof-fold").getByTestId("proof-fold-name")).toHaveText("Technical record");
  await detail().getByRole("button", { name: "Close details" }).click();

  // ---- every page that shows a result carries the one standing line
  const withResults: [string, string][] = [
    ["Verify", "Verify"],
    ["Advisories", "Advisories"],
    ["Checks", "Checks"],
    ["Fixes", "Fixes"],
    ["Timeline", "Timeline"],
    ["Results", "Results"],
    ["Approvals and decisions", "Approvals and decisions"],
  ];
  for (const [link, title] of withResults) {
    await stepLink(page, link).click();
    await expect(page.getByRole("heading", { name: title, level: 1, exact: true })).toBeVisible();
    if (link === "Checks") await openGroupTab(page, "Crypto tests", "Checks");
    await expect(page.getByTestId("page-content").getByText(DISCLAIMER).first(), `${title}`).toBeVisible();
  }
  await openMigrationView(page, "Systems");
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  // (The Observatory repeats the checks' own words and carries no standing line of its own: the SPEC calls the map "no
  // result". It is not asserted either way here.)
});
