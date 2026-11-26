// Phase 4c end to end: "real code". The file demo/real-libraries.csv names real libraries from outside (openjdk,
// python-ecdsa, elliptic, openssl). They run only in isolated mode (Docker), each family in its own locked-down image.
//
//  1. Demo mode (the main app of this run): the file imports, nothing of it can run, and every screen says so.
//  2. Isolated mode (a second copy of the app on its own ports and data folder, left to choose its mode itself;
//     skipped with a message when isolated mode is not available): Verify, Run all, Evidence Lab results with their
//     advisories, Fixes, Migration, Retest openjdk 17.0.3 with before and after.
//
// Main-screen buttons only. Screenshots go to docs/screenshots/phase4c/.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  BACKEND,
  DISCLAIMER,
  enterApp,
  PYTHON,
  screenshotFolder,
  stepLink,
  openFreshAssessment,
  closeResult,
  evidenceRow,
  resultPanel,
  stepNav,
  stepName,
  openGroupTab,
  openMigrationView,
  openProofFold,
} from "./shared";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = screenshotFolder("phase4c");
fs.mkdirSync(SHOTS, { recursive: true });
const FILE = path.resolve(here, "../../demo/real-libraries.csv");

const GROUPS = [
  "Signing program: openjdk 17.0.2",
  "Signing program: python-ecdsa 0.13.2",
  "Signing program: elliptic 6.5.6",
  "Signing program: openssl 3.5.9 (ECDSA P-256)",
  "Signing program: openssl 3.5.9 (ML-DSA-65)",
  "Key exchange program: openssl 3.5.9 (ML-KEM-768)",
];
const EXAM = "Independent exam (Wycheproof)";
const TRICKS = "Attacker tricks (our short list)";

async function shot(target: Page, name: string): Promise<void> {
  await target.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

async function goTo(target: Page, step: string): Promise<void> {
  // Phase 5a: the steps are the sidebar's pages of the open assessment.
  await stepLink(target, step).click();
  await expect(stepNav(target).locator('[aria-current="page"]'), `expected the step "${step}" to open`).toHaveText(
    stepName(step),
  );
  // (the old steps Tests and Evidence Lab are the test plan and the results: since 20 November 2026 they are the
  // Crypto tests tab of Checks and of Results, the page that was Evidence)
  if (["3. Tests", "Checks", "4. Evidence Lab", "Results"].includes(step))
    await openGroupTab(target, "Crypto tests", stepName(step) as "Checks" | "Results");
}

/** Upload demo/real-libraries.csv on Import (the drop zone's file input) and wait for the answer. */
async function importRealFile(target: Page): Promise<void> {
  await stepLink(target, "1. Import").click();
  const uploaded = target.waitForResponse(
    (r) => r.url().includes("/api/import/file") && r.request().method() === "POST",
  );
  await target.getByLabel("Choose a file to import").setInputFiles(FILE);
  expect((await uploaded).status(), "expected the upload of demo/real-libraries.csv to be accepted").toBe(200);
  await expect(
    target.getByTestId("claim-row"),
    "expected six claim rows (one per library claim in the file)",
  ).toHaveCount(6);
  await expect(
    target.getByText("Demo data", { exact: true }),
    "a file of real libraries must not carry the Demo data label",
  ).toHaveCount(0);
}

async function verifyClaims(target: Page): Promise<void> {
  await target.getByRole("button", { name: "Verify claims" }).click();
  await expect(target.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible({ timeout: 300_000 });
  await expect(target.getByTestId("result-row")).toHaveCount(6);
}

async function openTests(target: Page): Promise<void> {
  await target.getByRole("button", { name: "Continue to checks" }).click();
  await expect(target.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
}

function group(target: Page, heading: string): Locator {
  return target
    .getByTestId("lab-group")
    .filter({ has: target.getByRole("heading", { level: 2, name: heading, exact: true }) });
}

function labRow(target: Page, heading: string, title: string): Locator {
  return evidenceRow(target, title, group(target, heading)); // phase 5a: the table row of that group
}

/** Opens (or closes) the result behind a row of Evidence (phase 5a: in the right-side detail panel). */
async function toggleRow(row: Locator, title: string): Promise<void> {
  const target = row.page();
  const panel = target.getByTestId("detail-panel");
  if ((await panel.count()) > 0) {
    await closeResult(target);
    return;
  }
  await row.click();
  await expect(panel.getByRole("heading", { level: 2, name: title, exact: true })).toBeVisible();
}

async function cardStatuses(target: Page): Promise<string[]> {
  return target.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

// ---------------------------------------------------------------- 1. demo mode (the main app of this run)

test("demo mode: the real libraries import, but nothing of them can run, and every screen says so", async ({
  page,
}) => {
  await enterApp(page);
  await openFreshAssessment(page, "Real libraries walk");
  await importRealFile(page);
  const notices = page.getByTestId("import-notice");
  await expect(notices, "expected one notice about the real software").toHaveCount(1);
  await expect(notices.first()).toContainText(/^Real software: /);
  await expect(notices.first(), "the notice should say real software needs isolated mode").toContainText(
    "isolated mode",
  );
  await shot(page, "01-import-demo-mode.png");

  await verifyClaims(page);
  const badges = page.getByTestId("result-row").getByTestId("result-badge");
  await expect(badges, "expected six Couldn't check badges in demo mode").toHaveText(Array(6).fill("Couldn't check"));
  await openTests(page);

  await expect(page.getByTestId("test-card"), "expected 15 suggested tests").toHaveCount(15);
  const groups = page.getByTestId("test-group");
  await expect(groups).toHaveCount(6);
  for (const heading of GROUPS) {
    // (since the 5c fixes the test plan is a part of Checks, "Test plan", so a group's heading is two levels further in)
    const one = groups.filter({ has: page.getByRole("heading", { level: 4, name: heading, exact: true }) });
    await expect(one, `expected a group "${heading}"`).toHaveCount(1);
    await expect(
      one.getByTestId("test-group-note"),
      `expected the isolated-mode note under "${heading}"`,
    ).toContainText("isolated mode");
  }
  const notTested = page.getByTestId("not-tested");
  await expect(notTested.getByRole("heading", { name: "Not tested, and why" })).toBeVisible();
  await expect(notTested.getByRole("listitem"), "expected a line for each of the six programs").toHaveCount(6);
  await expect(page.getByText("Demo data", { exact: true })).toHaveCount(0);
  await shot(page, "02-tests-demo-mode-needs-isolated.png");
});

// ---------------------------------------------------------------- 2. isolated mode (a second copy of the app)

test("isolated mode: the real libraries are verified, tested, fixed, measured and retested in their own containers", async ({
  browser,
}) => {
  test.setTimeout(25 * 60_000);
  // A second copy of the app, with its own throwaway data folder and ports, left to choose its mode itself.
  const port = Number(process.env.E2E_APP_PORT ?? "8010") + 1;
  const tlsPort = Number(process.env.E2E_DEMO_TLS_PORT ?? "8443") + 1;
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-real-"));
  let app: ChildProcess | null = null;
  const second = await browser.newContext({ baseURL: `http://127.0.0.1:${port}` });
  try {
    const env: Record<string, string> = {
      PATH: process.env.PATH ?? "",
      HOME: process.env.HOME ?? "",
      EVIDENCE_LAB_DATA_DIR: dataDir,
      EVIDENCE_LAB_DEMO_TLS_PORT: String(tlsPort),
    };
    for (const key of ["DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR"])
      if (process.env[key]) env[key] = process.env[key] as string;
    app = spawn(
      PYTHON,
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port), "--log-level", "warning"],
      {
        cwd: BACKEND,
        stdio: "ignore",
        env,
      },
    );
    let session: any = null;
    await expect
      .poll(
        async () => {
          try {
            session = await (await second.request.get("/api/session")).json();
            return true;
          } catch {
            return false;
          }
        },
        { timeout: 30_000 },
      )
      .toBe(true);
    test.skip(
      session.mode !== "isolated",
      "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).",
    );

    const view = await second.newPage();
    await enterApp(view);
    await openFreshAssessment(view, "Real libraries walk");

    // ---- Import
    await importRealFile(view);
    const notice = view.getByTestId("import-notice");
    await expect(notice, "expected one notice about the real software").toHaveCount(1);
    await expect(
      notice.first(),
      "the notice should say each library runs in its own locked-down container",
    ).toContainText("Each runs in its own locked-down container");
    await expect(notice.first()).toContainText(/^Real software: /);
    await shot(view, "03-import-real-libraries.png");

    // ---- Verify
    await verifyClaims(view);
    await expect(view.getByTestId("result-row").getByTestId("result-badge"), "expected six True badges").toHaveText(
      Array(6).fill("True"),
      { timeout: 60_000 },
    );
    await shot(view, "04-verify-real-libraries.png");

    // ---- Tests, Run all
    await openTests(view);
    await expect(view.getByTestId("test-card"), "expected 15 suggested tests").toHaveCount(15);
    await expect(view.getByTestId("test-group"), "expected six groups").toHaveCount(6);
    for (const heading of GROUPS) {
      await expect(
        view.getByRole("heading", { level: 4, name: heading, exact: true }),
        `expected a group "${heading}"`,
      ).toBeVisible();
    }
    await expect(
      view.getByTestId("test-group-note"),
      "in isolated mode no group should carry a can't-run note",
    ).toHaveCount(0);
    await shot(view, "05-tests-real-libraries.png");
    await view.getByRole("button", { name: "Run all" }).click();
    await expect
      .poll(() => cardStatuses(view), {
        timeout: 10 * 60_000,
        intervals: [2_000],
        message: "expected all 15 tests to finish within 10 minutes",
      })
      .toEqual(Array(15).fill("done"));

    // ---- Evidence Lab: the results
    await goTo(view, "4. Evidence Lab");
    await expect(view.getByTestId("evidence-row")).toHaveCount(15);
    await expect(
      view.getByTestId("disclaimer"),
      "the Evidence Lab screen should carry the fixed disclaimer line",
    ).toHaveText(DISCLAIMER);
    await shot(view, "06-evidence-lab-results.png");

    // openjdk 17.0.2: the exam fails, with its advisory and the text-only fix line
    const javaExam = labRow(view, "Signing program: openjdk 17.0.2", EXAM);
    await expect(
      javaExam.getByTestId("result-badge"),
      "openjdk 17.0.2 Independent exam should read Failed",
    ).toContainText("Failed");
    await toggleRow(javaExam, EXAM);
    const javaDetail = resultPanel(view).getByTestId("result-detail");
    await expect(javaDetail).toBeVisible();
    // The design refactor (26 November 2026): the advisory is one of the records behind the result's fold; it is a
    // numbered part there, under its own title.
    await openProofFold(javaDetail);
    const advisories = javaDetail.getByTestId("advisories");
    await expect(javaDetail.getByTestId("proof-part-advisories")).toContainText(
      "Published advisories for this version",
    );
    await expect(advisories).toBeVisible();
    await expect(advisories, "expected the openjdk advisory CVE-2022-21449").toContainText("CVE-2022-21449");
    await expect(advisories.getByRole("link").first(), "expected a link to the OpenJDK advisory").toHaveAttribute(
      "href",
      /^https:\/\/openjdk\.org\//,
    );
    const fixLine = javaDetail.getByTestId("fix-line");
    await expect(fixLine).toContainText("Text-only suggestion: update to the fixed version");
    await expect(fixLine.getByRole("button", { name: "View in Fixes" })).toBeVisible();
    await shot(view, "07-java-result-with-advisory.png");
    await toggleRow(javaExam, EXAM);

    // The two post-quantum exams of OpenSSL 3.5.9
    const kemTitle = "Key exchange exam (ML-KEM-768)";
    const kem = labRow(view, "Key exchange program: openssl 3.5.9 (ML-KEM-768)", kemTitle);
    await expect(kem.getByTestId("result-badge"), "the ML-KEM-768 exam should read Passed").toContainText("Passed");
    await toggleRow(kem, kemTitle);
    await openProofFold(resultPanel(view)); // (the parts table is inside the fold)
    for (const cell of ["125 of 125", "300 of 300", "230 of 230"]) {
      await expect(
        resultPanel(view).getByTestId("result-detail").getByRole("cell", { name: cell, exact: true }),
        `expected "${cell}" in the ML-KEM-768 parts table`,
      ).toBeVisible();
    }
    await shot(view, "08-mlkem-exam-result.png");
    await toggleRow(kem, kemTitle);

    const dsaTitle = "Signature exam (ML-DSA-65)";
    const dsa = labRow(view, "Signing program: openssl 3.5.9 (ML-DSA-65)", dsaTitle);
    await expect(dsa.getByTestId("result-badge"), "the ML-DSA-65 exam should read Passed").toContainText("Passed");
    await toggleRow(dsa, dsaTitle);
    await openProofFold(resultPanel(view)); // (the parts table is inside the fold)
    for (const cell of ["25 of 25", "195 of 195", "255 of 255"]) {
      await expect(
        resultPanel(view).getByTestId("result-detail").getByRole("cell", { name: cell, exact: true }),
        `expected "${cell}" in the ML-DSA-65 parts table`,
      ).toBeVisible();
    }
    await shot(view, "09-mldsa-exam-result.png");
    await toggleRow(dsa, dsaTitle);

    // python-ecdsa: stops with a general program error on some cases: a note, never a result
    const pyExam = labRow(view, "Signing program: python-ecdsa 0.13.2", EXAM);
    await expect(
      pyExam.getByTestId("also-noticed"),
      "expected an Also noticed note about general program errors",
    ).toContainText("general program error");
    await shot(view, "10-python-ecdsa-also-noticed.png");

    // ---- Fixes
    await goTo(view, "5. Fixes");
    const list = view.getByRole("navigation", { name: /^Open findings with a fix/ });
    const javaFix = "Update openjdk to the fixed version (17.0.3)";
    await expect(
      list.getByRole("button").filter({ hasText: javaFix }).first(),
      `expected the Fixes list to hold "${javaFix}"`,
    ).toBeVisible();
    await list.getByRole("button").filter({ hasText: javaFix }).first().click();
    const summary = view.getByTestId("fix-summary");
    await expect(view.getByTestId("detail-panel").getByRole("heading", { name: javaFix, level: 2 })).toBeVisible(); // the panel's heading
    await expect(summary.getByTestId("fix-status")).toHaveText("Text only");
    // (the suggestion, with the advisory it answers, is inside the fix's one fold)
    await openProofFold(view.getByTestId("detail-panel"), "fix-proof-fold");
    await expect(view.getByTestId("advisories"), "expected the advisories box with its link in the fix").toBeVisible();
    await expect(view.getByTestId("advisories").getByRole("link").first()).toHaveAttribute(
      "href",
      /^https:\/\/openjdk\.org\//,
    );
    await expect(
      view.getByRole("button", { name: /pull request/i }),
      "a real library gets no pull request",
    ).toHaveCount(0);
    await shot(view, "11-fixes-update-to-fixed-version.png");

    // ---- Migration
    await goTo(view, "6. Migration");
    await view.getByRole("button", { name: "Measure status" }).click();
    await expect(view.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 10 * 60_000 });
    const openSystem = async (name: string) => {
      await openMigrationView(view, "Systems");
      await view.getByTestId("system-card").filter({ hasText: name }).first().click();
      await expect(view.getByTestId("migration-system").getByRole("heading", { name, level: 2 })).toBeVisible();
    };
    await openSystem("openssl 3.5.9 (ECDSA P-256)");
    const signatures = view.locator('[data-testid="migration-track"][data-track="signatures"]');
    await expect(
      signatures.getByTestId("track-next"),
      "expected openssl's Signatures track to say it is not blocked",
    ).toContainText("Not blocked");
    await shot(view, "12-migration-openssl-not-blocked.png");
    await openSystem("openjdk 17.0.2");
    await expect(view.getByTestId("migration-system"), "expected the blocker for openjdk").toContainText(
      "can't make post-quantum signatures",
    );
    await shot(view, "13-migration-openjdk-blocked.png");
    await openMigrationView(view, "Roadmap");
    const target = view
      .getByTestId("roadmap-band")
      .filter({ has: view.getByRole("heading", { name: "At the target", exact: true }) });
    await expect(
      target.getByTestId("roadmap-row").filter({ hasText: "openssl 3.5.9 (ML-DSA-65)" }),
      "expected openssl 3.5.9 (ML-DSA-65) in the band At the target",
    ).toHaveCount(1);
    await shot(view, "14-roadmap.png");

    // ---- Retest: openjdk 17.0.3
    await goTo(view, "4. Evidence Lab");
    await view.getByRole("button", { name: "Retest new version" }).click();
    const menu = view.getByRole("menu");
    await expect(
      menu.getByRole("menuitem"),
      "expected six versions in the retest menu (three libraries, two each)",
    ).toHaveCount(6);
    await shot(view, "15-retest-menu.png");
    await menu.getByRole("menuitem", { name: /^openjdk 17\.0\.3/ }).click();
    await expect(
      view.getByTestId("lab-cell-after").getByTestId("result-badge"),
      "expected every test to have an After result within 10 minutes",
    ).toHaveCount(15, { timeout: 10 * 60_000 });
    await expect(view.getByTestId("retest-progress")).toHaveCount(0);
    const columns = view.getByTestId("lab-columns");
    await expect(columns).toContainText("Before: openjdk 17.0.2");
    await expect(columns).toContainText("After: openjdk 17.0.3");
    const heading = "Signing program: openjdk 17.0.2";
    // (the group heading may now name the new version, so the group is found by the library's name)
    const javaGroup = view
      .getByTestId("lab-group")
      .filter({ has: view.getByRole("heading", { level: 2, name: /^Signing program: openjdk / }) });
    await expect(javaGroup, `expected one openjdk group (it was "${heading}")`).toHaveCount(1);
    const javaExamRow = evidenceRow(view, EXAM, javaGroup);
    const javaTricksRow = evidenceRow(view, TRICKS, javaGroup);
    await expect(
      javaExamRow.getByTestId("lab-cell-before").getByTestId("result-badge"),
      "exam before: Failed",
    ).toContainText("Failed");
    await expect(
      javaExamRow.getByTestId("lab-cell-after").getByTestId("result-badge"),
      "exam after: still Failed (three cases remain)",
    ).toContainText("Failed");
    await expect(
      javaTricksRow.getByTestId("lab-cell-before").getByTestId("result-badge"),
      "tricks before: Failed",
    ).toContainText("Failed");
    await expect(
      javaTricksRow.getByTestId("lab-cell-after").getByTestId("result-badge"),
      "tricks after: Passed",
    ).toContainText("Passed");
    await shot(view, "16-before-after-java.png");

    await toggleRow(javaExamRow, EXAM);
    const after = resultPanel(view).getByTestId("result-detail").first();
    await expect(after, "the first detail of a before/after row is the After one").toHaveAttribute(
      "aria-label",
      /^After: openjdk 17\.0\.3/,
    );
    await openProofFold(after); // (the technical summary is inside the fold)
    await expect(
      after.getByTestId("technical-summary"),
      "expected openjdk 17.0.3 to still get three of the 484 official cases wrong",
    ).toContainText("3 of 484 official cases wrong");
    await shot(view, "17-java-17.0.3-still-three-wrong.png");

    await expect(view.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  } finally {
    await second.close();
    if (app) {
      app.kill("SIGTERM");
      await new Promise((resolve) => setTimeout(resolve, 1500));
      if (app.exitCode === null) app.kill("SIGKILL");
    }
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
