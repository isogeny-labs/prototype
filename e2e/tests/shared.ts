// Things the test files share: the throwaway password, the one fixed line every result screen carries,
// and "get me into the app" (create the password on a brand-new data folder, or log in).
import { expect, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const REPO = path.resolve(here, "../..");
export const BACKEND = path.join(REPO, "backend");
export const PYTHON = path.join(BACKEND, ".venv/bin/python");

export const DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed.";

/** A pattern that matches exactly this text and nothing else. Every character a pattern could read as its own is
 * escaped, the backslash too (escaping only the dots was flagged by GitHub's code scanning on 18 November 2026). */
export function exactText(text: string): RegExp {
  return new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
}

// Made once per run by playwright.config.ts, for the throwaway data folder. It is never written anywhere.
export const password: string = process.env.E2E_PASSWORD ?? "";
if (!password) throw new Error("E2E_PASSWORD is not set; run the tests with `npm test` from the e2e folder.");

export function screenshotFolder(
  phase:
    | "phase1"
    | "phase2"
    | "phase3a"
    | "phase3a-fixes"
    | "phase4a"
    | "phase4b"
    | "phase4c"
    | "phase4d"
    | "phase5a"
    | "phase5b"
    | "phase5c"
    | "phase5c-fixes"
    | "phase6a"
    | "phase6d"
    | "phase6e"
    | "group-tabs"
    | "impact"
    | "source-tags"
    | "design-refactor",
): string {
  return path.join(REPO, "docs/screenshots", phase);
}

/** Opens the app and gets past the password screen, whichever one this data folder shows. */
/** Opens the app and logs in. `ottoPanel`: is the Otto panel shown beside the pages (the app's default)?
 *
 * Since phase 6 the panel repeats, under the same names, things a page shows: a next step is the page's own button
 * ("Verify claims", "Run all"), an example chip says the same words, and a suggestion has the proposal's own Accept and
 * Reject. A walk that is about the pages would find two of each. So a walk is given the panel only when it asks for it:
 * the panel's own walk, the research loop's walk and the walk that measures the pages' widths beside it. The others
 * start with the panel hidden, by the same setting the top bar's toggle keeps in the browser; a walk that presses the
 * toggle itself keeps what it chose. */
export async function enterApp(page: Page, options: { ottoPanel?: boolean } = {}): Promise<void> {
  await page.addInitScript((shown: boolean) => {
    try {
      if (window.localStorage.getItem("evidence-lab-copilot") === null)
        window.localStorage.setItem("evidence-lab-copilot", shown ? "shown" : "hidden");
    } catch {
      /* (no storage: the app's default stands) */
    }
  }, options.ottoPanel ?? false);
  await page.goto("/");
  const create = page.getByRole("heading", { name: "Create your password" });
  const login = page.getByRole("heading", { name: "Log in" });
  // Phase 5a: the app shell is the sidebar (the step bar is gone; its steps are the sidebar's assessment pages).
  const steps = page.getByTestId("sidebar").first();
  await expect(create.or(login).or(steps)).toBeVisible();
  if (await create.isVisible()) {
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Repeat password").fill(password);
    await page.getByRole("button", { name: "Create password" }).click();
  } else if (await login.isVisible()) {
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
  }
  await expect(steps).toBeVisible();
}

// Phase 5a: the six steps of the old step bar are now pages of the open assessment, in the sidebar. Phase 5b: Tests is
// now Checks (every check of the assessment; the test plan is in it, under Crypto tests). The design refactor (26
// November 2026): Evidence is a section of four views, and the page of the results is its Results view; the page of
// the migration is "Migration plan" ("Migration" is the work group).
const STEP_PAGES: Record<string, string> = {
  "1. Import": "Import",
  "2. Verify": "Verify",
  "3. Tests": "Checks",
  "4. Evidence Lab": "Results",
  "5. Fixes": "Fixes",
  "6. Migration": "Migration plan",
};

/** The sidebar's assessment pages, in order, once a file is in: the Overview, the six steps (Bring in, Observe, Test,
 * Fix, Plan the move, Keep watching) and then Evidence with its four views. */
// Phase 5c: Advisories. Phase 6d: Change watch. The design refactor (26 November 2026): no "Inventory" link; the
// Observatory before Verify; "Migration plan" (its three views are listed under it only while one of them is open);
// the four work groups are tabs on their pages and are not listed here.
export const SIDEBAR_PAGES = [
  "Overview",
  "Import",
  "Observatory",
  "Verify",
  "Advisories",
  "Checks",
  "Fixes",
  "Migration plan",
  "Change watch",
  "Timeline",
  "Results",
  "Approvals and decisions",
  "Evidence files",
];

/** Migration plan's three views, as the sidebar lists them under it while one of them is open. */
export const MIGRATION_VIEWS = ["Systems", "Roadmap", "Dependencies"] as const;

/** The sidebar's links, in order, with `open` the open page. The design refactor (26 November 2026): the four work
 * groups are no longer listed under Checks, Results or Fixes (a group is opened by its tab on the page); only Migration
 * plan lists something under it, its three views, while one of them is open. */
export function sidebarLinksOn(open: string): string[] {
  if (!(MIGRATION_VIEWS as readonly string[]).includes(open) && open !== "Migration plan") return [...SIDEBAR_PAGES];
  const at = SIDEBAR_PAGES.indexOf("Migration plan");
  return [...SIDEBAR_PAGES.slice(0, at + 1), ...MIGRATION_VIEWS, ...SIDEBAR_PAGES.slice(at + 1)];
}

/** The page an old step lands on, as the sidebar marks it current ("4. Evidence Lab" -> "Results"; "6. Migration"
 * opens Migration plan's first view, "Systems"). */
export function stepName(step: string): string {
  const name = STEP_PAGES[step] ?? step;
  return name === "Migration plan" ? "Systems" : name;
}

/** The sidebar's assessment pages (what the step bar was). */
export function stepNav(page: Page): Locator {
  return page.getByRole("navigation", { name: "Assessment" });
}

/** The sidebar link for one of the old steps ("4. Evidence Lab") or a page name ("Results", "Timeline"). A view of
 * Migration plan ("Roadmap") has its link only while Migration plan is open: see `openMigrationView`. */
export function stepLink(page: Page, step: string): Locator {
  return stepNav(page).getByRole("link", { name: STEP_PAGES[step] ?? step, exact: true });
}

/** Opens one of Migration plan's three views from anywhere in the assessment. The page has no switch of its own any
 * more: its views are the sidebar's links under "Migration plan", listed only while one of them is open. */
export async function openMigrationView(page: Page, view: (typeof MIGRATION_VIEWS)[number]): Promise<void> {
  const link = stepLink(page, view);
  if ((await link.count()) === 0) await stepLink(page, "Migration plan").click();
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "page");
}

/** Phase 5a: every walk works in its own project. New project (from Projects) opens its first assessment on Import. */
export async function openFreshAssessment(page: Page, name: string): Promise<void> {
  await page.goto("/#/projects");
  await expect(page.getByTestId("projects-page")).toBeVisible();
  await page.getByRole("button", { name: "New project", exact: true }).first().click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "Import", level: 1 })).toBeVisible();
  await expect(stepLink(page, "Import")).toHaveAttribute("aria-current", "page");
}

/** Use demo file, tick "I own this system", Verify claims, Continue to checks. Main-screen buttons only. */
export async function importVerifyAndOpenTests(page: Page): Promise<void> {
  await stepLink(page, "1. Import").click();
  // Wait for the import itself to be answered: until then the screen may still show an earlier import
  // (with its box already ticked), and the new file's box must be the one that gets ticked.
  const imported = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/import/demo" && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Use demo file" }).click();
  expect((await imported).status()).toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(3);
  const tick = page.getByTestId("address-confirm");
  await expect(tick).toHaveCount(1);
  // A new import always starts with the box unticked.
  await expect(tick).not.toBeChecked();
  await tick.click();
  await expect(tick).toBeChecked();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  const badges = page.getByTestId("result-row").getByTestId("result-badge");
  await expect(badges).toHaveText(["False", "True", "True"]);
  await continueToChecks(page);
}

/** 20 November 2026: Checks, Results (the page that was Evidence) and Fixes show the four work groups as tabs, one
 * group's table at a time. Opens the tab of one group by its name ("Crypto tests"), or keeps it open; the page's own
 * tabs, never the Otto panel's. `on`: the page it is on, right after that page was opened. For a moment the page before
 * may still be drawn, with tabs of its own (Results and Fixes have a Crypto tests tab too), so the page's own title is
 * waited for first. Since the design refactor (26 November 2026) the sidebar no longer lists the groups: the tab is the
 * one way to a group. A tab also shows how many items it holds, so it is found by its name, not by its whole text. */
export async function openGroupTab(page: Page, label: string, on?: "Checks" | "Results" | "Fixes"): Promise<void> {
  const tab = page.getByRole("tablist", { name: "Work groups" }).getByRole("tab", { name: label, exact: true });
  // (a page reads its groups after it opens, and on a busy machine that read can wait its turn for a few seconds)
  if (on) await expect(page.getByRole("heading", { name: on, level: 1, exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(tab).toBeVisible({ timeout: 20_000 });
  if ((await tab.getAttribute("aria-selected")) !== "true") await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

/** A sidebar link to a page, then the tab of one of its work groups: Checks, Results or Fixes on that group. */
export async function openPageGroup(page: Page, step: string, label: string): Promise<void> {
  await stepLink(page, step).click();
  await openGroupTab(page, label, stepName(step) as "Checks" | "Results" | "Fixes");
}

/** Verify's Continue to checks (was Continue to tests): opens Checks on Crypto tests, where the test plan's cards are. */
export async function continueToChecks(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  await expect(page.getByTestId("test-card").first()).toBeVisible();
  await expect(
    page.getByRole("tablist", { name: "Work groups" }).getByRole("tab", { name: "Crypto tests", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
}

/** Phase 5b: once a file is in, every page of the assessment opens (a page with nothing yet says what fills it). */
export async function expectPageOpen(page: Page, step: string): Promise<void> {
  await expect(stepLink(page, step)).not.toHaveAttribute("aria-disabled", "true");
  await expect(stepLink(page, step)).toHaveAttribute("href", /#\/a\/\d+\//);
}

/** Phase 3a-fixes: a picture of a demo screen this work changed, taken where the earlier runs already show it. */
export async function shotFixes(page: Page, name: string): Promise<void> {
  const fs = await import("node:fs");
  const folder = screenshotFolder("phase3a-fixes");
  fs.mkdirSync(folder, { recursive: true });
  await page.screenshot({ path: path.join(folder, name), fullPage: true, animations: "disabled" });
}

/** Phase 5a: one picture of the page in the dark look and one in the light look, in docs/screenshots/phase5a/. */
export async function shotBothThemes(page: Page, name: string, fullPage = true): Promise<void> {
  const fs = await import("node:fs");
  const folder = screenshotFolder("phase5a");
  fs.mkdirSync(folder, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => {
      document.documentElement.dataset.theme = t;
    }, theme);
    await page.screenshot({ path: path.join(folder, `${name}-${theme}.png`), fullPage, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
}

// Phase 5a: Evidence is a table of results; a row opens the right-side detail panel, which holds what the opened row
// held before (the "lab-row" wrapper with "result-detail", the fix line, Mark reviewed, Dig deeper...). The design
// refactor (26 November 2026): the page is the Results view of Evidence, and a result's panel reads in three layers:
// the answer, what it shows, and one fold, shut until it is opened, with every record (see `openProofFold`).

/** The table row of one result, by its test title (inside a group's section when `within` is given). */
export function evidenceRow(page: Page, title: string, within?: Locator): Locator {
  return (within ?? page)
    .getByTestId("evidence-row")
    .filter({ has: page.getByTestId("lab-row-header").getByText(title, { exact: true }) });
}

/** What the detail panel shows for the open result (the old opened row). */
export function resultPanel(page: Page): Locator {
  return page.getByTestId("detail-panel").getByTestId("lab-row");
}

/** Opens one result in the detail panel (or keeps it open) and returns what the panel shows for it. */
export async function openResult(page: Page, title: string, within?: Locator): Promise<Locator> {
  const heading = page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: title, exact: true });
  // (the test results are Results' Crypto tests table: its tab is opened first, unless a panel is open on it already.
  // The page may still be loading when this is asked, right after its sidebar link was followed: its tabs come with
  // its data, and it opens on the first group with something in it, which is Verification. So the tab is waited for.)
  if ((await heading.count()) === 0) await openGroupTab(page, "Crypto tests", "Results");
  if ((await heading.count()) === 0) await evidenceRow(page, title, within).click();
  await expect(heading).toBeVisible();
  return resultPanel(page);
}

/** Closes the detail panel. */
export async function closeResult(page: Page): Promise<void> {
  await page.getByTestId("detail-panel").getByRole("button", { name: "Close details" }).click();
  await expect(page.getByTestId("detail-panel")).toHaveCount(0);
}

/** Clicking a result's row used to open and shut it in place; now it opens the detail panel, or shuts it if that result
 * is the one already open. Same behaviour, so the walks keep their steps. */
export async function toggleResult(page: Page, title: string, within?: Locator): Promise<void> {
  const heading = page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: title, exact: true });
  if ((await heading.count()) > 0) await closeResult(page);
  else await openResult(page, title, within);
}

// ---- The folds of a panel (the design refactor, 26 November 2026) ----
// A panel shows the answer in the open and keeps every record behind one fold, shut until it is opened: a result's
// "Cryptanalysis proof" or "Technical record" (the technical summary, what happened, the control, the locked test, the
// run record, the advisory, where the check came from), an advisory's (the test's details, the trial, the records) and
// a fix's (its sections and the ledger entries). At the foot of a panel sit quiet folded lines: every run, History of
// this check, Related, What this change touches. A walk opens a fold as a person would before it reads what is in it.

/** Opens the one fold of a panel (or keeps it open) and returns it. `scope`: the panel, or the one result in it;
 * `testId`: "proof-fold" (a result, a proposal's proof), "advisory-proof-fold" or "fix-proof-fold". */
export async function openProofFold(scope: Page | Locator, testId = "proof-fold"): Promise<Locator> {
  const fold = scope.getByTestId(testId).first();
  const toggle = fold.getByTestId("proof-fold-toggle").first();
  await expect(toggle).toBeVisible();
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  return fold;
}

/** Opens a folded line at the foot of a panel (or keeps it open) and returns it: "runs-fold", "history-fold",
 * "related-fold", "impact-fold", or the Advisories page's "advisories-facts". */
export async function openFoldLine(scope: Page | Locator, testId: string): Promise<Locator> {
  const line = scope.getByTestId(testId).first();
  const toggle = line.getByRole("button").first();
  await expect(toggle).toBeVisible();
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  return line;
}

// ---- A copy of the app of its own (phase 4d; shared since phase 5b) ----
// A walk that needs a fresh app (its own data folder and ports) starts one, so the main app the phase walks share is
// never touched, and the order the files run in does not matter.

export interface Copy {
  app: ChildProcess;
  context: BrowserContext;
  page: Page;
  dataDir: string;
  mode: string;
  /** The demo TLS server of this copy: the server the demo file's claims name. */
  server: string;
}

/** A copy of the app on its own ports and data folder. mode "demo" forces demo mode; "auto" lets it choose. `more`
 * adds settings of the copy's own (never a key: a copy is started with a short, fixed environment). */
export async function startCopy(
  browser: Browser,
  offset: number,
  mode: "demo" | "auto",
  more: Record<string, string> = {},
): Promise<Copy> {
  const port = Number(process.env.E2E_APP_PORT ?? "8010") + offset;
  const tlsPort = Number(process.env.E2E_DEMO_TLS_PORT ?? "8443") + offset;
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-copy-"));
  const env: Record<string, string> = {
    PATH: process.env.PATH ?? "",
    HOME: process.env.HOME ?? "",
    EVIDENCE_LAB_DATA_DIR: dataDir,
    EVIDENCE_LAB_DEMO_TLS_PORT: String(tlsPort),
    ...more,
  };
  if (mode === "demo") env.EVIDENCE_LAB_MODE = "demo";
  for (const key of ["DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR"])
    if (process.env[key]) env[key] = process.env[key] as string;
  // To look into a walk that failed: E2E_APP_LOG=/some/file keeps what this copy of the app prints, with one line for
  // every request and its answer. Without it nothing is kept.
  const log = process.env.E2E_APP_LOG ? fs.openSync(process.env.E2E_APP_LOG, "a") : null;
  const app = spawn(
    PYTHON,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--log-level",
      log === null ? "warning" : "info",
    ],
    { cwd: BACKEND, stdio: log === null ? "ignore" : ["ignore", log, log], env },
  );
  const context = await browser.newContext({ baseURL: `http://127.0.0.1:${port}` });
  let session: { mode: string } | null = null;
  await expect
    .poll(
      async () => {
        try {
          session = await (await context.request.get("/api/session")).json();
          return true;
        } catch {
          return false;
        }
      },
      { timeout: 30_000 },
    )
    .toBe(true);
  const page = await context.newPage();
  if (log !== null) {
    // (and, in the same file, each request the page made: when it ended, its answer and how long it took)
    const started = Date.now();
    const note = (line: string) =>
      fs.writeSync(log, `[page +${((Date.now() - started) / 1000).toFixed(2)}s] ${line}\n`);
    page.on("requestfinished", (request) => {
      if (!request.url().includes("/api/")) return;
      void request
        .response()
        .then((response) =>
          note(
            `${request.method()} ${new URL(request.url()).pathname}${new URL(request.url()).search} -> ${response?.status() ?? "no answer"} (${Math.round(request.timing().responseEnd)} ms)`,
          ),
        );
    });
    page.on("requestfailed", (request) =>
      note(`${request.method()} ${request.url()} failed: ${request.failure()?.errorText ?? "unknown"}`),
    );
    page.on("framenavigated", (frame) =>
      frame === page.mainFrame() ? note(`at ${new URL(frame.url()).hash}`) : undefined,
    );
  }
  return {
    app,
    context,
    page,
    dataDir,
    mode: (session as { mode: string } | null)?.mode ?? "demo",
    server: `localhost:${tlsPort}`,
  };
}

export async function stopCopy(copy: Copy | null): Promise<void> {
  if (!copy) return;
  await copy.context.close();
  copy.app.kill("SIGINT");
  await new Promise((done) => setTimeout(done, 1500));
}

// ---- Layout at 1440 pixels wide (phase 5b; shared since phase 5c) ----

/** What is wrong with the page's layout right now: sideways scrolling, and words in table cells broken between
 * letters. Empty when all is well. */
export async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const doc = document.documentElement;
    if (doc.scrollWidth > doc.clientWidth + 1)
      problems.push(`the page scrolls sideways (${doc.scrollWidth} > ${doc.clientWidth})`);
    for (const t of Array.from(document.querySelectorAll<HTMLElement>('[data-testid="data-table"]'))) {
      if (t.offsetParent === null) continue;
      if (t.scrollWidth > t.clientWidth + 1) {
        const label = t.querySelector("table")?.getAttribute("aria-label") ?? "a table";
        problems.push(`"${label}" scrolls sideways (${t.scrollWidth} > ${t.clientWidth})`);
      }
    }
    // A run of letters and digits must sit on one line (a break is allowed only at a space or punctuation).
    const cells = Array.from(
      document.querySelectorAll<HTMLElement>("main td, main th, aside[role='complementary'] h2"),
    );
    for (const cell of cells) {
      const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent ?? "";
        for (const m of text.matchAll(/[A-Za-z0-9]{2,}/g)) {
          const range = document.createRange();
          range.setStart(node, m.index ?? 0);
          range.setEnd(node, (m.index ?? 0) + m[0].length);
          const tops = new Set(
            Array.from(range.getClientRects())
              .filter((r) => r.width > 0)
              .map((r) => Math.round(r.top)),
          );
          if (tops.size > 1) problems.push(`"${m[0]}" is broken between letters in "${text.trim().slice(0, 60)}"`);
        }
      }
    }
    return problems;
  });
}
