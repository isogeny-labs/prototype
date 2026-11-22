// Where it came from (22 November 2026, Kevin's plan and decisions A, B and C), on a copy of the app of its own (own data
// folder and ports: app 8037, demo server 8470), in demo mode. Main-screen buttons only, the Otto panel hidden.
//
//   Part 1, one finding followed through its tags, on the Acme Pay demo file:
//     the claim on Import [From your file] -> its Verify result [Observed live] -> the server test on Checks and
//     Evidence [Observed live], a program's test [Proven in the lab] -> its fix on Fixes [Observed live] -> the try on a
//     test copy [Proven in the lab, beside "Before" Observed live] -> After Apply [Observed live]. Then Migration (before
//     a measurement [From your file]; after it the server [Observed live] and the signing program [Proven in the lab]),
//     Dependencies (release notes [Published], an answer the app has not got [From your file]), the signing program's
//     fix and its proof [Proven in the lab], Change watch's before and now [Proven in the lab], and the Overview's count
//     of each group's checks by tag. On every table page each row with a result carries exactly one tag; reading the
//     pages runs nothing; the signed evidence file holds no tag (it is words only) and the verify command confirms it.
//   Part 2, an advisory check's result on Advisories [Proven in the lab], in a second assessment with the first built-in
//     test pack (skipped with a message where Otto is not installed).
//
// Every table page is measured at 1440 pixels wide. Pictures, dark and light: docs/screenshots/source-tags/.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND, DISCLAIMER, PYTHON, REPO, continueToChecks, enterApp, layoutProblems, openFreshAssessment, openGroupTab, openPageGroup, openResult,
  screenshotFolder, startCopy, stepLink, stopCopy, type Copy,
} from "./shared";

const SHOTS = screenshotFolder("source-tags");
const LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
const BANNED = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i, /time to hack/i];
const LABELS: Record<string, string> = { live: "Observed live", lab: "Proven in the lab", file: "From your file", published: "Published" };

let copy: Copy | null = null;
let page: Page;
let assessment = "";

const detail = (): Locator => page.getByTestId("detail-panel");
const box = (): Locator => detail().getByTestId("change-box");

/** One picture in the dark look and one in the light, with `focus` (when given) scrolled to just under the top bar, in a
 * window 1800 pixels high so a whole block fits; layout checks are made in the usual 900-pixel window. */
async function shots(name: string, focus?: Locator): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1800 });
  await page.waitForLoadState("networkidle");
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    if (focus) {
      await focus.evaluate((el) => {
        el.scrollIntoView({ block: "start" });
        let short = 240 - el.getBoundingClientRect().top;
        for (let up: Element | null = el.parentElement; up && short > 0; up = up.parentElement) {
          const back = Math.min(short, up.scrollTop);
          if (back > 0) {
            up.scrollTop -= back;
            short -= back;
          }
        }
        if (short > 0) window.scrollBy(0, -short);
      });
    } else {
      await page.evaluate(() => window.scrollTo(0, 0));
    }
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: false, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The words of every tag inside `where`, as [key, words]. */
async function tagsIn(where: Locator): Promise<[string, string][]> {
  return where.getByTestId("source-tag").evaluateAll((all) => all.map((t) => [t.getAttribute("data-source") ?? "", (t.textContent ?? "").trim()] as [string, string]));
}

/** Every tag shows its own words for its key (colour is a help, never the whole message). */
async function wordsMatchKeys(where: Locator): Promise<void> {
  for (const [key, words] of await tagsIn(where)) expect(words, `a ${key} tag`).toBe(LABELS[key]);
}

/** Each row of a table that shows a result carries exactly one tag; a row with no result, or one that couldn't run or
 * couldn't be trusted (nothing was observed or proven), carries none. */
async function oneTagPerResultRow(rows: Locator, what: string): Promise<number> {
  let tagged = 0;
  for (const row of await rows.all()) {
    const badges = await row.getByTestId("result-badge").allInnerTexts();
    const nothing = badges.length === 0 || badges.every((b) => /Couldn't run|Couldn't trust/.test(b));
    const tags = await row.getByTestId("source-tag").count();
    expect(tags, `${what}: ${(await row.innerText()).split("\n")[0]}`).toBe(nothing ? 0 : 1);
    tagged += tags;
  }
  return tagged;
}

async function noBannedWords(where: string): Promise<void> {
  // (the standing disclaimer, which says that passing these tests proves no system secure, is the one sentence left out)
  const words = (await page.getByTestId("page-content").innerText()).split(DISCLAIMER).join(" ");
  for (const banned of BANNED) expect(words, `${where}: ${banned}`).not.toMatch(banned);
}

async function pickFix(title: string): Promise<void> {
  await page.getByRole("navigation", { name: /^Open findings with a fix/ }).getByRole("button").filter({ hasText: title }).click();
  await expect(detail().getByRole("heading", { name: title, level: 2 })).toBeVisible();
}

/** How many runs the assessment's own tests have, as Checks counts them (to show that reading the pages ran nothing). */
async function runCount(): Promise<number> {
  const view = await (await page.request.get(`/api/assessments/${assessment}`)).json();
  const checks = await (await page.request.get(`/api/plans/${view.plan_id}/checks`)).json();
  return (checks.groups as { rows: { runs?: number }[] }[]).flatMap((g) => g.rows).reduce((sum, r) => sum + (r.runs ?? 0), 0);
}

test.describe.configure({ mode: "serial", timeout: 900_000 });

test.beforeAll(async ({ browser }) => {
  copy = await startCopy(browser, 27, "demo");
  page = copy.page;
  await page.setViewportSize({ width: 1440, height: 900 });
  await enterApp(page);
});

test.afterAll(async () => {
  await stopCopy(copy);
});

test("part 1: one finding followed through its tags, from the claim on Import to After Apply", async () => {
  const server = copy!.server;
  await openFreshAssessment(page, "Where it came from walk");
  assessment = /#\/a\/(\d+)/.exec(page.url())![1]!;

  // ---- Import: each claim is there because the file says so
  await page.getByRole("button", { name: "Use demo file" }).click();
  const claims = page.getByTestId("claim-row");
  await expect(claims).toHaveCount(3);
  for (const claim of await claims.all()) expect(await tagsIn(claim)).toEqual([["file", "From your file"]]);
  await expect(claims.first().getByTestId("source-tag")).toHaveAttribute("title", /rests only on your file/);
  await shots("01-import-claims-from-your-file");
  expect(await layoutProblems(page), "Import").toEqual([]);

  // ---- Verify: a server claim is read from the server; the signing program's claim by running a copy of it here
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  const results = page.getByTestId("result-row");
  await expect(results.getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
  expect(await Promise.all((await results.all()).map((r) => tagsIn(r).then((t) => t.map(([k]) => k))))).toEqual([["live"], ["live"], ["lab"]]);
  await results.first().getByRole("button", { name: "Details and evidence" }).click();
  await expect(detail().getByTestId("source-line")).toHaveText(
    `Observed live Read from ${server}, an address in your file that you confirmed, with handshakes only.`);
  await shots("02-verify-observed-live", detail().getByTestId("source-line"));
  expect(await layoutProblems(page), "Verify").toEqual([]);

  // ---- the test plan: a server test is read live, every other test runs a copy here
  await detail().getByRole("button", { name: "Close details" }).click();
  await continueToChecks(page);
  await page.getByRole("button", { name: "Run all" }).click();
  const cards = page.getByTestId("test-card");
  await expect(cards.getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });
  const cardTag = (title: string) => cards.filter({ has: page.getByRole("heading", { name: title, exact: true }) }).getByTestId("source-tag");
  await expect(cardTag("Old TLS versions")).toHaveText("Observed live");
  await expect(cardTag("Independent exam (Wycheproof)")).toHaveText("Proven in the lab");
  await wordsMatchKeys(page.getByTestId("page-content"));
  await shots("03-test-plan-live-and-lab");

  // ---- Checks: every row with a result carries one tag, in each group's own tab
  await openGroupTab(page, "Verification");
  const verification = page.locator('[data-testid="group-section"][data-group="verification"]').getByTestId("check-row");
  expect(await oneTagPerResultRow(verification, "Checks, Verification")).toBe(3);
  await verification.first().click();
  await expect(detail().getByTestId("source-line")).toContainText("Observed live");
  await shots("04-checks-verification-with-its-panel");
  expect(await layoutProblems(page), "Checks, Verification, panel open").toEqual([]);
  await detail().getByRole("button", { name: "Close details" }).click();
  expect(await layoutProblems(page), "Checks, Verification, panel closed").toEqual([]);

  // ---- Evidence: the result's panel says in one sentence what its tag means for it
  await openPageGroup(page, "Evidence", "Crypto tests");
  expect(await oneTagPerResultRow(page.getByTestId("evidence-row"), "Evidence, Crypto tests")).toBe(5);
  const vectors = await openResult(page, "Independent exam (Wycheproof)");
  await expect(vectors.getByTestId("source-line")).toContainText("Proven in the lab");
  await expect(vectors.getByTestId("source-note")).toContainText("Run on a copy of acme-sign 1.4.2 on this computer");
  await expect(vectors.getByTestId("source-note")).toContainText("Your live system was not touched.");
  await shots("05-evidence-result-proven-in-the-lab", vectors.getByTestId("source-line"));
  expect(await layoutProblems(page), "Evidence, panel open").toEqual([]);
  await noBannedWords("Evidence");

  // ---- Fixes: the server's fix carries the tag of its finding; the try is a test copy; After Apply reads the server again
  await stepLink(page, "Fixes").click();
  await openGroupTab(page, "Crypto tests", "Fixes");
  await pickFix("Server accepts TLS 1.2");
  await expect(page.getByTestId("fix-row").filter({ hasText: "Server accepts TLS 1.2" }).getByTestId("source-tag")).toHaveText("Observed live");
  await expect(detail().getByTestId("fix-summary").getByTestId("source-line")).toContainText(`Observed live Read from ${server}`);
  await box().getByRole("button", { name: "Try on a test copy" }).click();
  await expect(box().getByTestId("change-verdict")).toContainText("Try passed.", { timeout: 120_000 });
  await expect(box()).toHaveAttribute("data-busy", "false", { timeout: 60_000 });
  const tried = box().getByTestId("change-try");
  await expect(tried.getByTestId("column-source-tag")).toHaveText(["Observed live", "Proven in the lab"]);
  await expect(box().getByTestId("change-verdict").getByTestId("source-tag")).toHaveText("Proven in the lab");
  await expect(box().getByTestId("change-verdict").getByTestId("source-note")).toContainText("Your live server was not changed.");
  await shots("06-fix-try-on-a-test-copy", tried);
  expect(await layoutProblems(page), "Fixes, the try").toEqual([]);
  await box().getByRole("button", { name: "Ask for approval" }).click();
  await box().getByRole("button", { name: "Approve for You" }).click();
  await box().getByRole("button", { name: `Apply to ${server}` }).click();
  const applied = box().getByTestId("change-applied");
  await expect(applied.getByTestId("source-tag")).toHaveText("Observed live", { timeout: 90_000 });
  await expect(applied.getByTestId("source-tag")).toHaveAttribute("title", /handshakes only/);
  await shots("07-after-apply-observed-live", applied);
  await noBannedWords("Fixes, after Apply");
});

test("part 1: Migration, Dependencies, the signing program's fix and Change watch carry their tags", async () => {
  // ---- Migration: before a measurement a system rests on the file; after it, the server is read and the program run here
  await stepLink(page, "6. Migration").click();
  await page.getByRole("button", { name: /^Systems/ }).click();
  const systems = page.getByTestId("system-card");
  await expect(systems).toHaveCount(2);
  for (const system of await systems.all()) expect(await tagsIn(system)).toEqual([["file", "From your file"]]);
  await page.getByRole("button", { name: "Measure status" }).click();
  await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 120_000 });
  await expect(systems.filter({ hasText: copy!.server }).getByTestId("source-tag")).toHaveText("Observed live");
  await expect(systems.filter({ hasText: "acme-sign 1.4.2" }).getByTestId("source-tag")).toHaveText("Proven in the lab");
  await systems.filter({ hasText: "acme-sign 1.4.2" }).click();
  const today = page.getByTestId("migration-today");
  await expect(today.getByTestId("source-line")).toHaveText(
    "Proven in the lab Measured by running a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.");
  await shots("08-migration-live-and-lab");
  expect(await layoutProblems(page), "Migration, Systems").toEqual([]);

  // ---- Dependencies: what the maker's release notes say is Published; what the app has not got rests on the list
  await page.getByRole("button", { name: "Dependencies", exact: true }).click();
  const added = page.waitForResponse((r) => /\/api\/plans\/\d+\/dependencies\?/.test(r.url()) && r.request().method() === "POST");
  await page.getByLabel("Choose a dependency list").setInputFiles(LIST);
  expect((await added).status()).toBe(200);
  const libraries = page.getByTestId("dependency-row");
  await expect(libraries.first()).toBeVisible();
  const openssl = libraries.filter({ has: page.locator("p.font-mono", { hasText: /^openssl 3\.0/ }) });
  expect((await tagsIn(openssl)).map(([k]) => k)).toEqual(["file", "published", "published", "published"]);
  const python = libraries.filter({ has: page.locator("p.font-mono", { hasText: /^python / }) });
  expect((await tagsIn(python)).map(([k]) => k)).toEqual(["file", "file", "file", "file"]);
  await wordsMatchKeys(page.getByTestId("page-content"));
  await openssl.locator("p.font-mono").click();
  await expect(detail().getByTestId("source-line").first()).toContainText("From your file Listed in your dependency list.");
  await shots("09-dependencies-published-and-from-your-file");
  expect(await layoutProblems(page), "Dependencies, panel open").toEqual([]);

  // ---- the signing program's fix: from tests that failed on a copy here; its proof runs the changed code here
  await stepLink(page, "Fixes").click();
  await openGroupTab(page, "Crypto tests", "Fixes");
  await pickFix("acme-sign accepts out-of-range signatures");
  const fix = page.getByTestId("fix-summary");
  await expect(fix.getByTestId("source-line")).toContainText("From tests that failed on a copy of acme-sign 1.4.2 on this computer.");
  await fix.getByRole("button", { name: "Connect demo code" }).click();
  await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });
  await expect(fix.getByTestId("fix-proof").getByTestId("source-tag")).toHaveText("Proven in the lab");
  await shots("10-fix-proof-proven-in-the-lab");
  await fix.getByRole("button", { name: "Open pull request" }).click();
  await fix.getByRole("button", { name: "Approve", exact: true }).click();
  await fix.getByRole("button", { name: "Merge pull request" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm merge" }).click();
  await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "merged", { timeout: 60_000 });

  // ---- Change watch: before and now are each a run of a copy of the code on this computer
  await stepLink(page, "Change watch").click();
  await page.getByTestId("demo-change-button").click();
  await page.getByTestId("demo-change-item").filter({ hasText: "Revert the range check" }).click();
  const panel = page.getByTestId("change-panel");
  await panel.getByTestId("change-run-button").click();
  await expect(panel.getByTestId("change-panel-status")).toHaveText(/^Passed before, fails now/, { timeout: 300_000 });
  for (const side of await panel.locator('[data-testid="change-result-before"], [data-testid="change-result-now"]').all()) {
    expect(await tagsIn(side)).toEqual([["lab", "Proven in the lab"]]);
  }
  await expect(panel.getByTestId("change-result-now").first().getByTestId("source-note")).toContainText("on this computer");
  await shots("11-change-watch-before-and-now", panel.getByTestId("change-results"));
  expect(await layoutProblems(page), "Change watch, panel open").toEqual([]);
  await noBannedWords("Change watch");
});

test("part 1: the Overview counts each group's checks by tag; reading the pages ran nothing; the evidence file holds no tag", async () => {
  const before = await runCount();
  await page.goto(`/#/a/${assessment}/overview`);
  const verification = page.locator('[data-testid="overview-group"][data-group="verification"]');
  await expect(verification.getByTestId("overview-source-counts")).toHaveText("Where these came from: 2 Observed live · 1 Proven in the lab");
  const crypto = page.locator('[data-testid="overview-group"][data-group="encryption"]').getByTestId("overview-source-counts");
  await expect(crypto).toContainText("Observed live");
  await expect(crypto).toContainText("Proven in the lab");
  await shots("12-overview-where-these-came-from");
  await noBannedWords("Overview");

  // every page with results, every group tab: one tag per row with a result, and the words of its key
  for (const [step, on] of [["Checks", "Checks"], ["Evidence", "Evidence"]] as const) {
    await stepLink(page, step).click();
    for (const group of ["Verification", "Crypto tests", "Migration", "Dependencies"]) {
      await openGroupTab(page, group, on);
      const rows = page.getByTestId("page-content").locator('[data-testid="check-row"], [data-testid="evidence-row"]');
      await oneTagPerResultRow(rows, `${step}, ${group}`);
      await wordsMatchKeys(page.getByTestId("page-content"));
      expect(await layoutProblems(page), `${step}, ${group}`).toEqual([]);
    }
  }
  expect(await runCount(), "looking at every page ran nothing").toBe(before);

  // the signed evidence file: the tag is words on the pages only; the file holds none, and the verify command confirms it
  await stepLink(page, "Roadmap").click();
  const created = page.waitForResponse((r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const raw = await (await page.request.get((await made.json()).json.url)).body();
  expect(raw.toString("utf-8")).not.toContain("source_tag");
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-source-")), "evidence.json");
  fs.writeFileSync(file, raw);
  const run = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", copy!.dataDir], { cwd: BACKEND, encoding: "utf-8" });
  expect(run.status, `the evidence file should check: ${run.stdout} ${run.stderr}`).toBe(0);
});

test("part 2: an advisory check's result on Advisories is Proven in the lab", async () => {
  const otto = await (await page.request.get("/api/otto")).json();
  test.skip(!otto.harness.installed,
            `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
  // the first built-in test pack, from Settings
  await page.goto("/#/settings?section=test-packs");
  const packs = page.getByTestId("test-packs");
  await packs.getByTestId("otto-check-updates").click();
  await expect(packs.getByTestId("otto-update-line")).toContainText("2026.11.1");
  await packs.getByTestId("otto-install-update").click();
  const installed = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/otto/packs/install" && r.request().method() === "POST");
  await page.getByTestId("otto-install-dialog").getByTestId("otto-install-confirm").click();
  expect((await installed).status()).toBe(200);

  await openFreshAssessment(page, "Where it came from, Advisories");
  await page.getByRole("button", { name: "Use demo file" }).click();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  const id = /#\/a\/(\d+)/.exec(page.url())![1]!;
  await page.goto(`/#/a/${id}/advisories`);
  const row = page.locator('[data-testid="advisory-row"][data-advisory="CVE-2022-21449"]');
  await row.click();
  const proposal = page.locator('[data-testid="advisory-panel"][data-advisory="CVE-2022-21449"]')
    .locator('[data-testid="advisory-here-row"][data-program="acme-sign 1.4.2"]').getByTestId("otto-proposal");
  const accepted = page.waitForResponse((r) => /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await proposal.getByTestId("proposal-accept").click();
  expect((await accepted).status()).toBe(200);
  // before it has run, the result has no tag
  await expect(row.getByTestId("source-tag")).toHaveCount(0);

  await openPageGroup(page, "Checks", "Crypto tests");
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(6, { timeout: 240_000 });
  await page.goto(`/#/a/${id}/advisories`);
  await expect(row.getByTestId("advisory-result")).toContainText("Failed");
  expect(await tagsIn(row)).toEqual([["lab", "Proven in the lab"]]);
  for (const other of await page.getByTestId("advisory-row").all()) {
    if ((await other.getAttribute("data-advisory")) !== "CVE-2022-21449") expect(await tagsIn(other)).toEqual([]);
  }
  await row.click();
  const here = page.locator('[data-testid="advisory-here-row"][data-program="acme-sign 1.4.2"]');
  await expect(here.getByTestId("source-line")).toContainText("Proven in the lab Run on a copy of acme-sign 1.4.2 on this computer");
  await shots("13-advisories-result-proven-in-the-lab", here);
  expect(await layoutProblems(page), "Advisories, panel open").toEqual([]);
  await noBannedWords("Advisories");
});
