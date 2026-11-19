// Phase 6, Otto's research loop, end to end: "Look for new advisories", then "Design and prove tests". Two parts, each
// on a copy of the app of its own (own data folder and ports):
//
//  1. Isolated mode (skipped with a message when Docker or the test images are not ready, or Otto is not installed):
//     a file that names one real library, elliptic 6.5.6. No test pack is installed. A person looks, then presses
//     Design and prove tests. The research command reads the three advisories, designs a test and tries it on public
//     copies in containers; what it proves is signed into a test pack made on this computer, which the same click
//     installs. One check is then proposed (From Otto), accepted, and run by the runner and decided by the reviewer.
//     Two advisories read "No test yet", each with its reason. The evidence file verifies, with the look, the run
//     and the pack in it.
//  2. Demo mode (runs wherever Otto is installed): looking works, and Design and prove tests is off with its reason.
//
// The advisory source is a folder of recorded answers (the three elliptic advisories of the dated snapshot, as
// backend/tools/research_demo.py prepares them), and the answers of the research steps are the ones recorded during
// the build: a copy is started without any API key, so nothing here reaches the network or Claude.
// Screenshots (dark and light) go to docs/screenshots/phase6-research/.
import { expect, test, type Locator, type Page, type Request } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BACKEND, DISCLAIMER, PYTHON, REPO, enterApp, layoutProblems, openFreshAssessment, startCopy, stopCopy, type Copy } from "./shared";

const SHOTS = path.join(REPO, "docs/screenshots/phase6-research");
const PROVEN = "CVE-2024-42460";
const NOT_PROVEN = ["CVE-2024-42459", "CVE-2024-42461"];
const LOCAL_TIME = /\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d, \d{1,2}:\d\d [ap]m E[SD]T/;
const NEVER = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i, /Otto (found|proposes|proposed|wrote|has|asked|designed|proved)\b/];

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

/** A picture of the whole page in the dark and the light look. */
async function shots(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SHOTS, { recursive: true });
  await settled(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: true, animations: "disabled", scale: "css" });
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

/** A folder as backend/tools/research_demo.py prepares it: only the first built-in pack, and the three elliptic
 * advisories of the dated snapshot as a recorded advisory source. Nothing in it is new data. */
function prepareFolder(): { updates: string; source: string } {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-research-"));
  const made = spawnSync(PYTHON, ["tools/research_demo.py", folder], { cwd: BACKEND, encoding: "utf-8" });
  expect(made.status, `preparing the folder: ${made.stdout} ${made.stderr}`).toBe(0);
  return { updates: path.join(folder, "updates"), source: path.join(folder, "source") };
}

/** A scanner file that names one real library (data; nothing in it runs). */
function oneLibraryFile(): string {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-research-file-"));
  const file = path.join(folder, "one-library.csv");
  fs.writeFileSync(file, "location,type,claim,value\nelliptic 6.5.6,software,signature_algorithm,ECDSA P-256\n");
  return file;
}

async function importFile(page: Page, file: string): Promise<void> {
  const uploaded = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/import/file" && r.request().method() === "POST");
  await page.getByLabel("Choose a file to import").setInputFiles(file);
  expect((await uploaded).status(), "the upload of the one-library file was accepted").toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(1);
}

async function openAdvisories(page: Page, assessment: string): Promise<Locator> {
  await page.goto(`/#/a/${assessment}/advisories`);
  const advisories = page.getByTestId("advisories-page");
  await expect(advisories.getByTestId("advisories-standing")).toHaveText(DISCLAIMER);
  return advisories;
}

const block = (page: Page): Locator => page.getByTestId("new-advisories");
const found = (page: Page, id: string): Locator => block(page).locator(`[data-testid="found-advisory"][data-advisory="${id}"]`);
const advisoryRow = (page: Page, id: string): Locator => page.locator(`[data-testid="advisory-row"][data-advisory="${id}"]`);

/** Look for new advisories: the box first, then its own button. Returns what the box said. */
async function look(page: Page): Promise<string[]> {
  const before = changes(page);
  await block(page).getByTestId("look-for-advisories").click();
  const box = page.getByTestId("look-dialog");
  await expect(box).toBeVisible();
  const lines = await box.getByRole("listitem").allInnerTexts();
  expect(changes(page), "opening the box sent nothing").toEqual(before);
  const answered = page.waitForResponse((r) => /\/api\/plans\/\d+\/advisories\/look$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await box.getByTestId("lookup-confirm").click();
  expect((await answered).status()).toBe(200);
  await expect(block(page).getByTestId("look-result")).toBeVisible();
  return lines.map((l) => l.trim());
}

async function expectPlainWords(page: Page, where: string): Promise<void> {
  await settled(page);
  const said = await block(page).innerText();
  for (const word of NEVER) expect(word.test(said), `the block on ${where} says ${word}`).toBe(false);
}

function verify(file: string, dataDir: string) {
  return spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", dataDir], { cwd: BACKEND, encoding: "utf-8" });
}

test.describe.configure({ mode: "serial" });
test.use({ actionTimeout: 60_000 });

// ---------------------------------------------------------------- 1. isolated mode: the whole loop

test("isolated mode: look, design and prove on public copies, the proven check is proposed, accepted and run; the evidence verifies", async ({ browser }) => {
  test.setTimeout(60 * 60_000);
  let copy: Copy | null = null;
  const prepared = prepareFolder();
  try {
    copy = await startCopy(browser, 22, "auto", { EVIDENCE_LAB_OTTO_UPDATES: prepared.updates, EVIDENCE_LAB_ADVISORY_SOURCE: prepared.source });
    test.skip(copy.mode !== "isolated",
              "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).");
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    test.skip(!otto.harness.installed, `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
    expect(otto.live.key_present, "a copy of the app is started without an API key").toBe(false);
    expect(otto.packs.installed, "no test pack is installed: nobody installs one in this walk").toEqual([]);

    await openFreshAssessment(page, "Research loop walk");
    await importFile(page, oneLibraryFile());
    // Verify runs the library in its own container, so it takes a while before the Verify page opens
    await page.getByRole("button", { name: "Verify claims" }).click();
    await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible({ timeout: 300_000 });
    const assessment = assessmentOf(page);

    // ================================================================ Advisories, before any look
    const advisories = await openAdvisories(page, assessment);
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(0);          // no pack is installed: nothing is listed yet
    await expect(block(page).getByRole("heading", { name: "New advisories" })).toBeVisible();
    await expect(block(page).getByTestId("new-advisories-libraries")).toHaveText("This assessment names: elliptic 6.5.6.");
    await expect(block(page).getByTestId("new-advisories-covers")).toContainText("What this covers:");
    await expect(block(page).getByTestId("look-for-advisories")).toBeEnabled();
    await expect(block(page).getByTestId("design-and-prove")).toHaveCount(0);     // there is nothing to try before a look
    expect(await layoutProblems(page), "Advisories with the block, before a look").toEqual([]);
    await shots(page, "01-advisories-before-a-look");

    // ================================================================ Look for new advisories: the box, then the list
    // Cancel sends nothing
    await block(page).getByTestId("look-for-advisories").click();
    await expect(page.getByTestId("look-dialog")).toContainText("Reading is free: Claude is not asked, nothing runs, and nothing is proposed by looking.");
    await shots(page, "02-the-box-before-a-look");
    const beforeCancel = changes(page);
    await page.getByTestId("look-dialog").getByTestId("lookup-cancel").click();
    await expect(page.getByTestId("look-dialog")).toHaveCount(0);
    expect(changes(page)).toEqual(beforeCancel);
    const said = await look(page);
    // (this copy reads a folder of recorded answers; with the public source the box names the package names it sends)
    expect(said[0]).toBe("Reads the recorded answers in a folder on this computer about the libraries this assessment names.");
    expect(said).toContain("Nothing is sent anywhere.");
    await expect(block(page).getByTestId("look-line")).toHaveText(
      new RegExp(`^Looked on ${LOCAL_TIME.source} by You: 3 published advisories about your libraries\\. 3 are new and can be tried here\\.$`));
    await expect(block(page).getByTestId("look-source")).toHaveText("Read from recorded answers in a folder on this computer. Nothing was sent.");
    await expect(block(page).getByTestId("found-advisory")).toHaveCount(3);
    for (const id of [PROVEN, ...NOT_PROVEN]) {
      await expect(found(page, id)).toHaveAttribute("data-state", "new");
      await expect(found(page, id).getByTestId("found-state")).toHaveText("New: not tried yet");
      await expect(found(page, id).getByTestId("found-fits")).toContainText("elliptic 6.5.6");
    }
    // looking proposed nothing, installed nothing and ran nothing
    await expect(advisories.getByTestId("advisory-row")).toHaveCount(0);
    expect((await (await page.request.get("/api/otto")).json()).packs.installed).toEqual([]);
    expect(await layoutProblems(page), "Advisories after a look").toEqual([]);
    await expectPlainWords(page, "Advisories after a look");
    await shots(page, "03-after-a-look-three-new");

    // ================================================================ Design and prove tests: the box, then the run
    const prove = block(page).getByTestId("design-and-prove");
    await expect(prove).toHaveText("Design and prove tests (3)");
    await prove.click();
    const box = page.getByTestId("research-dialog");
    await expect(box).toContainText("A test counts as proven only when it fails on the affected version, passes on the fixed version, and the control that must fail does.");
    await expect(box).toContainText("Live Otto is off: only answers recorded during the build are used.");
    await expect(box).toContainText("that pack is installed by this click, after the built-in test pack not installed yet (2026.11.1), in order.");
    await expect(box).toContainText("Accepting or rejecting it stays with you");
    await shots(page, "04-the-box-before-a-research-run");
    const beforeStart = changes(page).length;
    const started = page.waitForResponse((r) => /\/api\/plans\/\d+\/advisories\/research$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await box.getByTestId("lookup-confirm").click();
    expect((await started).status()).toBe(200);
    expect(changes(page).slice(beforeStart)).toHaveLength(1);
    // while it runs the block says so, the button is off with the reason, and the page reads again by itself
    await expect(block(page).getByTestId("research-line")).toContainText("A research run is going on");
    await expect(block(page).getByTestId("design-and-prove")).toBeDisabled();
    await expect(block(page).getByTestId("research-blocked")).toHaveText("A research run is going on. Wait for it to finish.");
    await page.screenshot({ path: path.join(SHOTS, "05-a-research-run-going-on-dark.png"), fullPage: true, animations: "disabled", scale: "css" });
    // ... until it has finished: the pack it made was installed by that same click
    const finished = /^The research run that started on .+ finished on .+\. Test pack (\d{4}\.\d{1,2}\.\d+), made on this computer, was installed\.$/;
    await expect(block(page).getByTestId("research-line")).toHaveText(finished, { timeout: 45 * 60_000 });
    // (a pack made here is named by the month it is made in: 2026.11.2 in November 2026, 2026.12.1 a month later)
    const made = finished.exec((await block(page).getByTestId("research-line").innerText()).trim())![1]!;
    expect(made).not.toBe("2026.11.1");
    const installed = (await (await page.request.get("/api/otto")).json()).packs.installed;
    expect(installed.map((p: any) => p.version)).toEqual(["2026.11.1", made]);
    expect(installed[1].made_here).toBe(true);

    // ================================================================ what was proven is proposed; what was not says why
    await expect(found(page, PROVEN).getByTestId("found-state")).toHaveText(`Proven on public copies (test pack ${made})`);
    for (const id of NOT_PROVEN) {
      await expect(found(page, id).getByTestId("found-state")).toHaveText(`No test yet (test pack ${made})`);
      await expect(found(page, id).getByTestId("found-reason")).not.toBeEmpty();
    }
    await expect(block(page).getByTestId("design-and-prove")).toBeDisabled();     // nothing new is left to try
    // the list below now holds the advisories of both packs; the proven one is a proposal, tagged New
    await expect(advisoryRow(page, PROVEN).getByTestId("advisory-proposal")).toHaveText("Proposed");
    await expect(advisoryRow(page, PROVEN)).toContainText("New");
    expect(await layoutProblems(page), "Advisories after the research run").toEqual([]);
    await expectPlainWords(page, "Advisories after the research run");
    await shots(page, "06-after-the-run-one-proven-two-not");
    // nothing was added to the test plan: no advisory check is in it before a person accepts one
    await page.goto(`/#/a/${assessment}/checks`);
    await expect(page.getByTestId("test-card").first()).toBeVisible();
    await expect(page.getByTestId("test-card").filter({ hasText: "Advisory check" })).toHaveCount(0);
    await openAdvisories(page, assessment);
    await expect(found(page, PROVEN).getByTestId("found-link")).toBeVisible();

    // ---- the proposal, in the advisory's own panel: how the test did on public copies; then Accept
    await found(page, PROVEN).getByTestId("found-link").click();
    const panel = page.locator(`[data-testid="advisory-panel"][data-advisory="${PROVEN}"]`);
    await expect(panel.getByTestId("advisory-sentence")).toBeVisible();
    const proposal = panel.getByTestId("otto-proposal");
    await expect(proposal).toContainText("From Otto");
    await expect(proposal).toContainText("Tried on public copies before the pack was signed");
    await expect(proposal).toContainText("elliptic 6.5.7 got 0 wrong");
    await expect(proposal.getByRole("button")).toHaveText(["Accept", "Reject"]);
    await shots(page, "07-the-proven-check-proposed");
    const accepted = page.waitForResponse((r) => /\/otto\/proposals\/[^/]+\/accept$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
    await proposal.getByTestId("proposal-accept").click();
    expect((await accepted).status()).toBe(200);
    await expect(proposal.getByTestId("proposal-status")).toHaveText("Added");

    // ================================================================ Checks: the accepted check is run by the runner, decided by the reviewer
    await page.goto(`/#/a/${assessment}/checks`);
    const card = page.getByTestId("test-card").filter({ hasText: PROVEN });
    await expect(card).toHaveCount(1);
    await expect(card.getByTestId("card-from-otto")).toHaveText("From Otto");
    await expect(card).toHaveAttribute("data-status", "not_run");                  // accepting ran nothing
    await card.getByRole("button", { name: /^Run / }).click();        // (the card's button is named "Run" and, for a screen reader, the test)
    await expect(card).toHaveAttribute("data-status", "done", { timeout: 600_000 });
    // elliptic 6.5.6 is the affected version: the reviewer's word, on your own system
    await expect(card.getByTestId("result-badge")).toHaveText("Failed");
    await shots(page, "08-checks-the-check-ran");
    // Advisories repeats the reviewer's word for it
    await openAdvisories(page, assessment);
    await expect(advisoryRow(page, PROVEN)).toContainText("Failed");
    await shots(page, "09-advisories-with-the-result");

    // ================================================================ the evidence: the look, the run and the pack it made
    await page.goto(`/#/a/${assessment}/evidence`);
    const created = page.waitForResponse((r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Download evidence" }).click();
    const info = await (await created).json();
    const raw = await (await page.request.get(info.json.url)).body();
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-research-evidence-")), "evidence.json");
    fs.writeFileSync(file, raw);
    const part = JSON.parse(raw.toString("utf-8")).evidence.otto;
    expect(part.lookups.looks).toHaveLength(1);
    expect(part.lookups.looks[0].source).toBe("recorded");
    expect(part.lookups.looks[0].sent).toEqual([]);
    expect((part.lookups.looks[0].found as any[]).map((f) => f.id).sort()).toEqual([PROVEN, ...NOT_PROVEN].sort());
    expect((part.lookups.research as any[]).map((r) => [r.what, r.pack_version])).toEqual([["started", null], ["finished", made]]);
    expect((part.packs as any[]).map((p) => p.pack.version)).toContain(made);
    const good = verify(file, copy.dataDir);
    expect(good.status, `the evidence file should check: ${good.stdout} ${good.stderr}`).toBe(0);
    expect(good.stdout).toMatch(/^Evidence verified/);
    expect(good.stdout).toMatch(/Looks for new advisories: 1, each with what was asked and the fingerprint of each answer; research runs: 1 finished, each pack they made is in the file\./);
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. demo mode: looking works; proving says why it can't

test("demo mode: looking works, and Design and prove tests is off with its reason", async ({ browser }) => {
  test.setTimeout(10 * 60_000);
  let copy: Copy | null = null;
  const prepared = prepareFolder();
  try {
    copy = await startCopy(browser, 23, "demo", { EVIDENCE_LAB_OTTO_UPDATES: prepared.updates, EVIDENCE_LAB_ADVISORY_SOURCE: prepared.source });
    const page = copy.page;
    await page.setViewportSize({ width: 1440, height: 900 });
    watchRequests(page);
    await enterApp(page);
    const otto = await (await page.request.get("/api/otto")).json();
    test.skip(!otto.harness.installed, `Skipped: ${otto.harness.line} Run ./run-demo.sh once (or: cd backend && .venv/bin/python -m app.prepare --otto).`);
    await openFreshAssessment(page, "Research loop walk, demo mode");
    await importFile(page, oneLibraryFile());
    const assessment = assessmentOf(page);
    await openAdvisories(page, assessment);
    await look(page);
    await expect(block(page).getByTestId("found-advisory")).toHaveCount(3);
    const prove = block(page).getByTestId("design-and-prove");
    await expect(prove).toBeDisabled();
    await expect(block(page).getByTestId("research-blocked")).toHaveText(
      "Trying a test on public copies needs isolated mode (Docker): a real library runs only in its own locked-down container.");
    const before = changes(page);
    await prove.click({ force: true });
    await expect(page.getByTestId("research-dialog")).toHaveCount(0);
    expect(changes(page), "a button that is off sends nothing").toEqual(before);
    expect(await layoutProblems(page), "Advisories in demo mode after a look").toEqual([]);
    await shots(page, "10-demo-mode-proving-is-off-with-its-reason");
  } finally {
    await stopCopy(copy);
  }
});
