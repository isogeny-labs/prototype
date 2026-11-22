// Change watch, the Changes view (phase 6d, first half), on a copy of the app of its own (own data folder and ports),
// in demo mode, on the Acme Pay demo:
//
//   - before the demo code is connected the page says what to do first, and links to Fixes;
//   - the fix is connected, proven, approved and merged with the Fixes page's own buttons;
//   - "Bring in a demo change" adds the change that undoes the merged fix: it is listed with the tests picked for it
//     and why, and the tests left out and why. Nothing has run;
//   - "Run the picked tests" runs them, pressed from the Otto panel's card behind Confirm (the page's own request):
//     the change reads "Passed before, fails now", with each test's result before and on the change in the reviewer's
//     own words. The assessment's own results are as they were;
//   - Fixes has an entry for the change, text only, that names the tests and shows the lines the change takes out;
//   - the second demo change, a settings file that names TLS 1.0, picks nothing, cannot run, and carries one flag;
//   - the table and the panel are measured at 1440 pixels wide, also beside the Otto panel;
//   - the evidence file holds the change and its run, and the verify command checks them.
//
// The Otto panel is hidden, except for the one step that is about it. Pictures, dark and light: docs/screenshots/phase6d/.
import { expect, test, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND,
  PYTHON,
  continueToChecks,
  enterApp,
  layoutProblems,
  openFreshAssessment,
  openPageGroup,
  screenshotFolder,
  startCopy,
  stepLink,
  stopCopy,
  type Copy,
} from "./shared";

const SHOTS = screenshotFolder("phase6d");
const TRICKS = "Attacker tricks (our short list)";
const NOT_CONNECTED = "Connect the demo code first. Connect demo code is on Fixes.";
const NOT_TESTED = "The app has not tested what this line does.";
const BANNED = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i];
// A time as the screens write it, for a viewer in New York: "18 November 2026, 7:46 pm EST".
const LOCAL_TIME =
  /\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d, \d{1,2}:\d\d [ap]m E[SD]T/;

let copy: Copy | null = null;
let page: Page;
const sent: string[] = [];

/** Every request of the page that is not a read, as "POST /api/...". */
function watch(p: Page): void {
  p.on("request", (r: Request) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith("/api/") && r.method() !== "GET") sent.push(`${r.method()} ${url.pathname}`);
  });
}

async function shots(name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  // from the top of the page and of the open panel, so a picture shows the page as it opens
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
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: true, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

async function noBannedWords(where: string): Promise<void> {
  const words = await page.getByTestId("page-content").innerText();
  for (const banned of BANNED) expect(words, `${where}: ${banned}`).not.toMatch(banned);
}

const row = (title: string) => page.getByTestId("change-row").filter({ hasText: title });
const panel = () => page.getByTestId("change-panel");

test.describe.configure({ mode: "serial", timeout: 600_000 });

test.afterAll(async () => {
  await stopCopy(copy);
});

test("Change watch: a developer's change comes in, its tests are picked and run on a click, and a line that names old cryptography is flagged", async ({
  browser,
}) => {
  copy = await startCopy(browser, 24, "demo");
  page = copy.page;
  await page.setViewportSize({ width: 1440, height: 900 });
  watch(page);
  await enterApp(page);
  await openFreshAssessment(page, "Change watch walk");

  // ---- the demo file, Verify, every test
  await page.getByRole("button", { name: "Use demo file" }).click();
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await continueToChecks(page);
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });

  // ---- Change watch before the code is connected: what to do first, and the way to Fixes
  await stepLink(page, "Change watch").click();
  await expect(page.getByRole("heading", { name: "Change watch", level: 1 })).toBeVisible();
  await expect(stepLink(page, "Change watch")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("change-watch-code-line")).toContainText(NOT_CONNECTED);
  await expect(page.getByTestId("changes-table")).toHaveCount(0);
  await page.getByTestId("demo-change-button").click();
  await expect(page.getByTestId("demo-change-item")).toHaveCount(2);
  for (const item of await page.getByTestId("demo-change-item").all()) await expect(item).toBeDisabled();
  await expect(page.getByTestId("demo-change-blocked").first()).toHaveText("Connect the demo code first.");
  await shots("01-before-the-code-is-connected");
  await page.keyboard.press("Escape");
  await page.getByTestId("change-watch-code-link").click();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();

  // ---- Fixes: connect the demo code, wait for the proof, open the pull request, approve, merge
  await page.getByTestId("fix-row").filter({ hasText: "range" }).first().click();
  const fix = page.getByTestId("fix-summary");
  await fix.getByRole("button", { name: "Connect demo code" }).click();
  await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "ready", { timeout: 300_000 });

  // ---- connected, nothing merged yet: the change that undoes a fix is not offered; the settings change is
  await stepLink(page, "Change watch").click();
  await expect(page.getByTestId("change-watch-connected")).toHaveText(
    "Connected: the demo repository acme-sign, branch main.",
  );
  await expect(page.getByTestId("changes-empty")).toContainText(
    "No developer's change is in the connected repository yet.",
  );
  await expect(page.getByTestId("change-row")).toHaveCount(0); // the fix's own branch is not a developer's change
  await page.getByTestId("demo-change-button").click();
  const menu = page.getByTestId("demo-change-menu");
  await expect(menu).toContainText("It runs nothing.");
  await expect(menu.getByTestId("demo-change-item").filter({ hasText: "Revert the range check" })).toBeDisabled();
  await expect(menu.getByTestId("demo-change-item").filter({ hasText: "Revert the range check" })).toContainText(
    "Offered once a fix is merged",
  );
  await expect(menu.getByTestId("demo-change-item").filter({ hasText: "Allow TLS 1.0" })).toBeEnabled();
  await page.keyboard.press("Escape");

  await stepLink(page, "Fixes").click();
  await page.getByTestId("fix-row").filter({ hasText: "range" }).first().click();
  await fix.getByRole("button", { name: "Open pull request" }).click();
  await fix.getByRole("button", { name: "Approve", exact: true }).click();
  await fix.getByRole("button", { name: "Merge pull request" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm merge" }).click();
  await expect(fix.getByTestId("fix-status")).toHaveAttribute("data-status", "merged", { timeout: 60_000 });
  // what Fixes counts before any change comes in (compared again once a change has its entry there)
  const encryptionFixes = page.locator('[data-testid="group-section"][data-group="encryption"]');
  const fixesCounted = {
    title: await page.locator("#fix-list-title").innerText(),
    group: await encryptionFixes.getByTestId("group-counts").innerText(),
    rows: await page.getByTestId("fix-row").count(),
  };
  expect(fixesCounted.title).toMatch(/^Open findings with a fix \(\d+\)$/i);
  await expect(page.getByTestId("fix-apart")).toHaveCount(0);

  // what Evidence says before any change comes in (compared again at the end)
  // (the test results are Evidence's Crypto tests tab)
  await openPageGroup(page, "Evidence", "Crypto tests");
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  await expect(page.getByTestId("evidence-row").first()).toBeVisible();
  // (the rows' own text, whatever is drawn at this instant: `innerText` reads as one unbroken line while a row is in
  // the page but not drawn yet, which a busy machine showed on 19 November 2026)
  const evidenceBefore = await page.getByTestId("evidence-row").allTextContents();
  expect(evidenceBefore.join(" ")).toContain("Attacker tricks (our short list)");

  // ---- a developer's change comes in: it is listed with its picked tests, and nothing has run
  await stepLink(page, "Change watch").click();
  const before = sent.length;
  await page.getByTestId("demo-change-button").click();
  await page.getByTestId("demo-change-item").filter({ hasText: "Revert the range check" }).click();
  await expect(row("Revert the range check")).toHaveCount(1);
  expect(sent.slice(before)).toEqual([
    expect.stringMatching(/^POST \/api\/plans\/\d+\/change-watch\/demo\/revert-range-check$/),
  ]);
  await expect(row("Revert the range check")).toHaveAttribute("data-status", "not_run");
  await expect(panel()).toBeVisible(); // the new change is opened
  await expect(panel().getByTestId("change-panel-status")).toHaveText("Not run yet");
  await expect(panel().getByTestId("change-gives")).toHaveText(
    "Its code is, byte for byte, acme-sign 1.4.2, one of our registered demo programs.",
  );
  await expect(panel()).toContainText("Demo developer");
  await expect(panel().getByTestId("change-branch")).toHaveText("Branch dev/revert-range-check");
  await expect(panel()).toContainText(LOCAL_TIME);
  await expect(panel().getByTestId("code-line").first()).toBeVisible();
  expect(await panel().locator('[data-testid="code-line"][data-mark="-"]').count()).toBeGreaterThan(0);
  const picked = panel().getByTestId("change-picked").getByTestId("change-test");
  await expect(picked).toHaveCount(3); // the three tests that run acme-sign
  await expect(picked.first()).toContainText("Runs acme-sign, and this change edits acme_sign.py.");
  await panel().getByTestId("change-not-picked-box").locator("summary").click();
  const left = panel().getByTestId("change-not-picked").getByTestId("change-test");
  await expect(left).toHaveCount(2); // the two server tests
  await expect(left.first()).toContainText("It does not run acme-sign.");
  await expect(panel().getByTestId("change-run-button")).toHaveText("Run the picked tests");
  await expect(panel().getByTestId("change-run-note")).toContainText(
    "never replace a result of this assessment's own tests",
  );
  await expect(panel().getByTestId("change-results")).toHaveCount(0);
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Change watch with a change open").toEqual([]);
  await noBannedWords("a change, not run yet");
  await shots("02-a-change-with-its-picked-tests");

  // ---- Run the picked tests, from the Otto panel: its card is the page's own button, and nothing is sent before Confirm
  await page.getByRole("button", { name: "Show the assistant" }).click();
  const otto = page.getByTestId("otto-panel");
  const card = otto.locator('[data-testid="otto-entry"][data-what="next:run_picked_tests"]');
  await expect(card).toHaveCount(1);
  await expect(card.getByTestId("otto-entry-mark")).toHaveText("Next step");
  await expect(card.getByTestId("otto-entry-title")).toHaveText("Run the picked tests");
  await expect(card).toContainText(
    "The tests picked for “Revert the range check” have not run yet (3 of 5 tests picked).",
  );
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Change watch with a change open, beside the Otto panel").toEqual([]);
  const beforeRun = sent.length;
  await card.getByRole("button", { name: "Run the picked tests", exact: true }).click();
  const step = card.getByTestId("otto-confirm");
  await expect(step.getByTestId("otto-confirm-names")).toHaveText(
    "This is the Run the picked tests button on Change watch.",
  );
  await expect(step).toContainText(
    "These runs are kept apart: they never replace a result of this assessment's own tests.",
  );
  await shots("02b-the-otto-panels-card-with-its-confirm-step");
  expect(sent.slice(beforeRun)).toEqual([]);
  await step.getByTestId("otto-confirm-button").click();
  await expect(panel().getByTestId("change-panel-status")).toHaveText("Running"); // the page read again after the panel's request
  await expect(panel().getByTestId("change-run-button")).toBeDisabled();
  await page.getByRole("button", { name: "Hide the assistant" }).click();
  await expect(otto).toHaveCount(0);
  await expect(panel().getByTestId("change-panel-status")).toHaveText("Passed before, fails now (2 tests)", {
    timeout: 300_000,
  });
  expect(sent.slice(beforeRun)).toEqual([
    expect.stringMatching(/^POST \/api\/plans\/\d+\/change-watch\/change-[0-9a-f]{12}\/run$/),
  ]);
  await expect(panel().getByTestId("change-status-reason")).toHaveText(
    "2 tests passed on the code before and fail on this change.",
  );
  await expect(panel().getByTestId("change-run-button")).toHaveText("Run again");
  const results = panel().getByTestId("change-result");
  await expect(results).toHaveCount(3);
  const tricks = results.filter({ hasText: TRICKS });
  await expect(tricks).toHaveAttribute("data-outcome", "fails_now");
  await expect(tricks.getByTestId("change-result-before").getByTestId("result-badge")).toHaveText("Passed");
  await expect(tricks.getByTestId("change-result-before")).toContainText("acme-sign 1.4.3");
  await expect(tricks.getByTestId("change-result-now").getByTestId("result-badge")).toHaveText("Failed");
  await expect(tricks.getByTestId("change-result-now")).toContainText("acme-sign 1.4.2");
  // (the speed test is placed by its run on the change alone, which timed the change side by side with the code before)
  await expect(results.filter({ hasText: "Speed and size" })).toHaveAttribute("data-outcome", "not_slower");
  await expect(results.filter({ hasText: "Speed and size" }).getByTestId("change-result-differs")).toHaveText(
    "No slowdown against the code before",
  );
  await expect(row("Revert the range check")).toHaveAttribute("data-status", "passed_before_fails_now");
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Change watch after a run").toEqual([]);
  await noBannedWords("a change, after its run");
  await shots("03-passed-before-fails-now");
  // ---- Fixes has an entry for this change: text only, with the tests that fail on it and the lines it takes out
  await expect(panel().getByTestId("change-fix-line")).toContainText(
    "A suggestion for this change is in Fixes. It is text only.",
  );
  await panel().getByTestId("change-fix-link").click();
  await expect(page).toHaveURL(/#\/a\/\d+\/fixes\?item=fix-change-[0-9a-f]{12}$/);
  const entry = page.getByTestId("fix-summary");
  await expect(entry).toHaveAttribute("aria-label", "Revert the range check: 2 tests that passed now fail");
  await expect(page.getByTestId("detail-panel")).toContainText("Revert the range check: 2 tests that passed now fail");
  await expect(entry.getByTestId("fix-status")).toHaveText("Text only");
  await expect(entry.getByTestId("fix-source")).toContainText(
    "Came from the developer's change dev/revert-range-check",
  );
  await expect(entry.getByTestId("fix-proof")).toContainText(
    "This suggestion is text only: the app has not applied it or tested it.",
  );
  await expect(entry.getByTestId("fix-approvers")).toContainText("The app never merges a developer's change.");
  await expect(
    entry.getByRole("button", { name: /Merge|Approve|Open pull request|Download patch|Connect/ }),
  ).toHaveCount(0);
  // It sits in Crypto tests (the tab the link opened: the one that holds it) under a heading of its own and is counted nowhere: the page's count, the group's
  // counts and the rows of the assessment's own findings are what they were before the change came in.
  await expect(encryptionFixes.getByTestId("fix-apart-title")).toHaveText("From a developer's change (1)");
  await expect(encryptionFixes.getByTestId("fix-apart-note")).toContainText(
    "is not counted with the assessment's findings",
  );
  await expect(encryptionFixes.getByTestId("fix-apart-row")).toHaveCount(1);
  await expect(encryptionFixes.getByTestId("fix-apart-row")).toContainText(
    "Revert the range check: 2 tests that passed now fail",
  );
  expect(await page.locator("#fix-list-title").innerText()).toBe(fixesCounted.title);
  expect(await encryptionFixes.getByTestId("group-counts").innerText()).toBe(fixesCounted.group);
  expect(await page.getByTestId("fix-row").count()).toBe(fixesCounted.rows);
  const takenOut = page.locator('[data-section="change"]');
  await expect(takenOut).toContainText("What the change takes out");
  expect(await takenOut.locator('[data-testid="code-line"][data-mark="-"]').count()).toBeGreaterThan(0);
  await expect(page.locator('[data-section="suggestion"]')).toContainText(
    `${TRICKS} passed on the code before (acme-sign 1.4.3) and fails on this change (acme-sign 1.4.2).`,
  );
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Fixes with the entry for a developer's change open").toEqual([]);
  // (the entry's own words: the Fixes page itself carries the app's line that passing tests proves no system secure)
  const entryWords = (await entry.innerText()) + (await page.locator('[data-section="suggestion"]').innerText());
  for (const banned of BANNED) expect(entryWords, `the entry for a developer's change: ${banned}`).not.toMatch(banned);
  await shots("03c-fixes-the-entry-for-the-change");
  await stepLink(page, "Change watch").click();
  await row("Revert the range check").click();
  await expect(panel()).toBeVisible();

  // "See the evidence" of the result on the change opens exactly that run on Checks: a row of its own under Change
  // watch, never the test's own result
  await tricks.getByTestId("change-result-now").getByTestId("change-result-link").click();
  await expect(page).toHaveURL(/#\/a\/\d+\/checks\?item=watch-\d+-in-\d+$/);
  const check = page.getByTestId("check-panel");
  await expect(check).toBeVisible();
  await expect(check).toContainText("Change watch");
  // (where it ran is in the panel's heading: the program, and that it is the change's code)
  await expect(page.getByTestId("detail-panel")).toContainText(
    "acme-sign 1.4.2, the change on dev/revert-range-check (commit ",
  );
  await expect(check.getByTestId("result-badge").first()).toHaveText("Failed");
  // ---- Checks: the run has a part of its own under Crypto tests (the tab the link opened), one block for the change, one row for each picked test
  const part = page.locator('[data-testid="part-section"][data-part="changes"]');
  await expect(part).toBeVisible();
  await expect(part.getByRole("heading", { level: 3 })).toContainText("Change watch");
  await expect(part.getByTestId("part-count").first()).toHaveText("1 run");
  await expect(part.getByTestId("block-section")).toHaveCount(1);
  await expect(part.getByTestId("block-section")).toContainText(
    "From a developer's change: dev/revert-range-check, commit ",
  );
  await expect(part.getByTestId("check-row")).toHaveCount(3);
  await expect(page.locator('[data-testid="part-section"][data-part="plan"]').getByTestId("test-card")).toHaveCount(5); // the plan is as it was
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Checks with a watch run's part and one of its rows open").toEqual([]);
  await shots("03b-checks-the-run-on-the-change");
  // the result before opens the run it came from: the proof of the fix, in its own block on Checks
  await stepLink(page, "Change watch").click();
  await row("Revert the range check").click();
  await expect(panel()).toBeVisible();
  await results
    .filter({ hasText: TRICKS })
    .getByTestId("change-result-before")
    .getByTestId("change-result-link")
    .click();
  await expect(page).toHaveURL(/#\/a\/\d+\/checks\?item=proof-\d+-in-\d+$/);
  await expect(page.getByTestId("check-panel").getByTestId("result-badge").first()).toHaveText("Passed");
  // Evidence lists the change's runs too, under Crypto tests, each saying where it came from
  await openPageGroup(page, "Evidence", "Crypto tests");
  await expect(page.getByTestId("check-row").filter({ hasText: "Change watch" })).toHaveCount(3);

  // ---- these runs are kept apart: Evidence reads exactly what it read before the change came in
  await openPageGroup(page, "Evidence", "Crypto tests");
  await expect(page.getByTestId("evidence-row")).toHaveCount(5);
  await expect.poll(async () => page.getByTestId("evidence-row").allTextContents()).toEqual(evidenceBefore);

  // ---- the settings change: nothing is picked, nothing can run, and its line that names TLS 1.0 is flagged
  await stepLink(page, "Change watch").click();
  await page.getByTestId("demo-change-button").click();
  await page.getByTestId("demo-change-item").filter({ hasText: "Allow TLS 1.0" }).click();
  await expect(page.getByTestId("change-row")).toHaveCount(2);
  await expect(row("Allow TLS 1.0 for an old partner")).toHaveAttribute("data-status", "nothing_to_run");
  await expect(row("Allow TLS 1.0 for an old partner").getByTestId("change-flags-count")).toHaveText("1 flag");
  await expect(panel().getByTestId("change-panel-status")).toHaveText("Nothing to run");
  await expect(panel().getByTestId("change-run-button")).toBeDisabled();
  await expect(panel().getByTestId("change-run-blocked")).toHaveText(
    "This change edits no file of a program under test, so no test is picked.",
  );
  const flag = panel().getByTestId("change-flag");
  await expect(flag).toHaveCount(1);
  await expect(flag).toContainText("partner-gateway.conf, line 4");
  await expect(flag).toContainText("names TLS 1.0");
  await expect(flag.getByTestId("change-flag-note")).toHaveText(NOT_TESTED);
  await expect(flag.getByRole("link", { name: /RFC 8996/ })).toHaveAttribute(
    "href",
    "https://www.rfc-editor.org/rfc/rfc8996",
  );
  await expect(flag.getByTestId("result-badge")).toHaveCount(0); // a flag is no result
  await page.waitForLoadState("networkidle");
  expect(await layoutProblems(page), "Change watch with two changes, the flagged one open").toEqual([]);
  await shots("04-a-flag-and-nothing-to-run");
  // with the panel closed: the table by itself
  await panel().getByRole("button", { name: "Close details" }).click();
  await expect(panel()).toHaveCount(0);
  expect(await layoutProblems(page), "Change watch, the table alone").toEqual([]);
  await shots("05-the-changes-table");
  // both demo changes are in: the menu offers neither again
  await page.getByTestId("demo-change-button").click();
  for (const item of await page.getByTestId("demo-change-item").all()) await expect(item).toBeDisabled();
  await page.keyboard.press("Escape");

  // ---- the evidence file holds both changes and the run, and the verify command checks that part against the runs
  await stepLink(page, "Evidence").click();
  const created = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const raw = await (await page.request.get(info.json.url)).body();
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-changewatch-")), "evidence.json");
  fs.writeFileSync(file, raw);
  const signed = JSON.parse(raw.toString("utf-8")).evidence.change_watch;
  expect(signed.changes.map((c: { branch: string }) => c.branch).sort()).toEqual([
    "dev/allow-tls-1-0-for-partner",
    "dev/revert-range-check",
  ]);
  expect(signed.runs).toHaveLength(1);
  expect(signed.runs[0].review.status).toBe("passed_before_fails_now");
  const checked = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", copy.dataDir], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
  expect(checked.status, checked.stdout + checked.stderr).toBe(0);
  expect(checked.stdout).toContain("Evidence verified");
  expect(checked.stdout).toContain(
    "Change watch: 2 changes, 1 run of the picked tests (6 test runs): each run matches its fingerprint and ran on the change's code.",
  );
  expect(checked.stdout).toContain("the reviewer's word for the change follows from it.");
  const report = await (await page.request.get(info.html.url)).text();
  expect(report).toContain("9. Change watch");
  expect(report).toContain("Revert the range check");

  // ---- an address that names a change opens it
  await stepLink(page, "Change watch").click();
  const id = await row("Revert the range check").getAttribute("data-change");
  const assessment = page.url().match(/#\/a\/(\d+)/)![1];
  await page.goto(`/#/a/${assessment}/overview`);
  await expect(page.getByTestId("overview-groups")).toBeVisible();
  await page.goto(`/#/a/${assessment}/change-watch?item=${id}`);
  await expect(panel()).toHaveAttribute("data-change", id!);
  await expect(panel().getByTestId("change-panel-status")).toHaveText("Passed before, fails now (2 tests)");

  // In the whole walk only these two kinds of request came from Change watch: the two demo changes and the one run.
  expect(sent.filter((s) => s.includes("/change-watch/"))).toEqual([
    expect.stringMatching(/\/change-watch\/demo\/revert-range-check$/),
    expect.stringMatching(/\/change-watch\/change-[0-9a-f]{12}\/run$/),
    expect.stringMatching(/\/change-watch\/demo\/allow-tls-1-0$/),
  ]);
});
