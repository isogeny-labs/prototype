// Phase 4d end to end: the Dependencies view of the Migration step, on the Acme Pay demo file and the demo dependency
// list (demo/dependencies-demo.cdx.json). Each part starts its own copy of the app, with its own throwaway data folder
// and ports, so the main app of this run (which the phase walks share) is never touched:
//
//  1. Demo mode: Add dependency list, the lookups and their sources, Part of, the named blocker on the roadmap and its
//     text-only Fixes entry, a broken file refused in one sentence, Download evidence. Measuring is off, with the reason.
//  2. Isolated mode (skipped with a message when Docker or the images are not ready): Measure all, the answers measured
//     on a public copy with their controls, the blocker now measured, Download evidence.
//
// Main-screen buttons only. Screenshots go to docs/screenshots/phase4d/.
import { expect, test, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND,
  enterApp,
  exactText,
  importVerifyAndOpenTests,
  PYTHON,
  REPO,
  screenshotFolder,
  startCopy,
  stepLink,
  stopCopy,
  openFreshAssessment,
  type Copy,
} from "./shared";

const SHOTS = screenshotFolder("phase4d");
fs.mkdirSync(SHOTS, { recursive: true });
const LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
const BROKEN = path.join(REPO, "demo/dependencies-broken/not-a-dependency-list.json");
const READ = "Evidence Lab reads dependency lists in CycloneDX JSON (1.5 or 1.6) or SPDX JSON (2.3).";

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

async function openDependencies(page: Page): Promise<void> {
  await stepLink(page, "6. Migration").click();
  await expect(page.getByRole("heading", { name: "Migration", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Dependencies", exact: true }).click();
  await expect(page.getByTestId("dependencies-view")).toBeVisible();
}

async function addList(page: Page, file: string): Promise<number> {
  const answered = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/dependencies\?/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByLabel("Choose a dependency list").setInputFiles(file);
  return (await answered).status();
}

function row(page: Page, label: string) {
  return page.getByTestId("dependency-row").filter({ has: page.locator("p.font-mono", { hasText: exactText(label) }) });
}

/** Phase 5a: a library's row opens its details (answers, reasons, first version, blocks, sources, measurements) in the
 * right-side detail panel; this opens it (or keeps it open) and hands back what the panel shows. */
async function details(page: Page, label: string) {
  const heading = page.getByTestId("detail-panel").getByRole("heading", { level: 2, name: label, exact: true });
  // Phase 5b: a row holds a link too (its "Blocks ..." marker opens the Roadmap), so open the row by its name.
  if ((await heading.count()) === 0) await row(page, label).locator("p.font-mono").click();
  await expect(heading).toBeVisible();
  return page.getByTestId("detail-panel").getByTestId("dependency-detail");
}

/** "Part of": acme-pay-server 1.0.0 is this copy's demo server. */
async function tiePayServer(page: Page, server: string): Promise<void> {
  await page.getByLabel("Part of: acme-pay-server 1.0.0").selectOption({ label: `Server: ${server}` });
  await expect(page.getByTestId("tie-words").nth(1)).toHaveText(`Part of ${server}, set by you.`);
}

async function downloadEvidence(page: Page): Promise<{ json: any; report: string; file: string }> {
  await page.getByRole("button", { name: "Roadmap", exact: true }).click();
  const created = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const raw = await (await page.request.get(info.json.url)).body();
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-deps-file-")), "evidence.json");
  fs.writeFileSync(file, raw);
  return {
    json: JSON.parse(raw.toString("utf-8")),
    report: await (await page.request.get(info.html.url)).text(),
    file,
  };
}

function verifies(file: string, dataDir: string): void {
  const run = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", dataDir], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
  expect(run.status, `the evidence file should check: ${run.stdout} ${run.stderr}`).toBe(0);
}

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------- 1. demo mode

test("demo mode: add the list, the lookups and their sources, Part of, the blocker on the roadmap and in Fixes", async ({
  browser,
}) => {
  test.setTimeout(5 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 3, "demo");
    const page = copy.page;
    await enterApp(page);
    await openFreshAssessment(page, "Dependencies walk");
    await importVerifyAndOpenTests(page);

    // ---- the Dependencies view, before a list
    await openDependencies(page);
    await expect(page.getByTestId("dependencies-empty")).toHaveText("No dependency list added yet.");
    await shot(page, "01-dependencies-empty.png");

    // ---- Add dependency list
    expect(await addList(page, LIST)).toBe(200);
    await expect(page.getByTestId("dependencies-subline")).toContainText(
      "From your file dependencies-demo.cdx.json (CycloneDX 1.6)",
    );
    await expect(page.getByTestId("dependency-group")).toHaveCount(3);
    await expect(page.getByTestId("dependency-row")).toHaveCount(10);
    await expect(page.getByTestId("tie-words").first()).toHaveText(
      "Part of acme-sign 1.4.2, tied by name and version.",
    );
    // every yes or no is "Release notes say"; measuring needs isolated mode and says so
    const openssl30 = row(page, "openssl 3.0.22");
    await expect((await details(page, "openssl 3.0.22")).getByTestId("dependency-cell")).toHaveCount(3);
    for (const cell of await (await details(page, "openssl 3.0.22")).getByTestId("dependency-cell").all()) {
      await expect(cell).toContainText("No");
      await expect(cell).toContainText("Release notes say");
      await expect(cell.getByTestId("first-version")).toHaveText("3.5.0 or later can.");
      await expect(cell.getByTestId("measure-state")).toHaveText("Couldn't check (needs isolated mode)");
    }
    await expect(page.getByTestId("measure-all-blocked")).toHaveText(
      "Measuring needs isolated mode (Docker). Lookups work as they are.",
    );
    await expect(page.getByRole("button", { name: "Measure all" })).toBeDisabled();
    await expect(
      (await details(page, "boringssl 4c8b1d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c"))
        .getByTestId("dependency-cell")
        .first(),
    ).toContainText("Needs your environment");
    await expect(
      (await details(page, "Go standard library devel")).getByTestId("dependency-cell").first(),
    ).toContainText("Couldn't tell the version");
    await expect((await details(page, "wolfssl 5.7.2")).getByTestId("dependency-cell").first()).toContainText(
      "Not in our knowledge base yet",
    );
    await expect(page.getByText("Measured in your environment")).toHaveCount(0);
    await shot(page, "02-dependencies-looked-up.png");

    // ---- Details and evidence: the official source, quoted, with the date it was checked
    await (await details(page, "openssl 3.0.22")).getByText("Details and evidence").click();
    await expect((await details(page, "openssl 3.0.22")).getByTestId("lookup-source").first()).toContainText(
      "OpenSSL 3.5 NEWS",
    );
    await expect((await details(page, "openssl 3.0.22")).getByTestId("lookup-source").first()).toContainText(
      "Support for PQC algorithms (ML-KEM, ML-DSA and SLH-DSA)",
    );
    await expect(
      (await details(page, "openssl 3.0.22")).getByRole("link", { name: /github\.com\/openssl\/openssl/ }).first(),
    ).toHaveAttribute("href", /^https:\/\//);
    await (
      await details(page, "openssl 3.0.22")
    ).screenshot({ path: path.join(SHOTS, "03-openssl-3.0-sources.png"), animations: "disabled" });

    // ---- Part of: acme-pay-server 1.0.0 is the demo server
    await tiePayServer(page, copy.server);
    const server = page.getByTestId("dependency-system").filter({ hasText: "Server" });
    await expect(server.getByTestId("blocker-line")).toHaveCount(2);
    await expect(server.getByTestId("blocker-line").first()).toContainText(
      "Blocks its key exchange track: openssl 3.0.22 (through python 3.12.3), release notes say. 3.5.0 or later can.",
    );
    await expect(server).toContainText("1 of its libraries has no answer yet: a thing to check, not a blocker.");
    await expect((await details(page, "openssl 3.0.22")).getByTestId("row-blocks")).toContainText(
      "Blocks the key exchange track of",
    );
    await shot(page, "04-dependencies-tied-blocker.png");

    // ---- the blocker on the roadmap, after Measure status
    await page.getByRole("button", { name: "Measure status" }).click();
    await expect(page.getByRole("button", { name: "Measure again", exact: true })).toBeEnabled({ timeout: 120_000 });
    await page.getByRole("button", { name: "Roadmap", exact: true }).click();
    const notes = page.getByTestId("roadmap-row").filter({ hasText: "localhost:" }).getByTestId("roadmap-note");
    await expect(notes.filter({ hasText: "Blocker: it relies on openssl 3.0.22 (through python 3.12.3)" })).toHaveCount(
      2,
    );
    await shot(page, "05-roadmap-names-the-blocker.png");

    // ---- its Fixes entry: text only, with the official source
    await page.getByRole("button", { name: "Dependencies", exact: true }).click();
    await server.getByTestId("blocker-line").first().getByRole("button", { name: "View in Fixes" }).click();
    await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
    const summary = page.getByTestId("fix-summary").filter({ hasText: "Update OpenSSL to 3.5.0 or later" });
    await expect(summary).toBeVisible();
    await expect(page.getByText("Text only", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("This is about other people's software", { exact: false })).toBeVisible();
    await shot(page, "06-fixes-update-openssl.png");

    // ---- a broken file is refused in one sentence; the list stays
    await openDependencies(page);
    expect(await addList(page, BROKEN)).toBe(422);
    await expect(page.getByRole("alert")).toContainText(`This JSON file is neither CycloneDX nor SPDX. ${READ}`);
    await expect(page.getByTestId("dependency-row")).toHaveCount(10);
    await shot(page, "07-broken-file-refused.png");

    // ---- Download evidence: the dependency part is in the signed file and the report
    const evidence = await downloadEvidence(page);
    const part = evidence.json.evidence.dependencies;
    expect(part.rows).toHaveLength(10);
    expect(part.measurements).toEqual([]);
    expect(evidence.report).toContain("7. Dependencies");
    expect(evidence.report).toContain("Support for PQC algorithms (ML-KEM, ML-DSA and SLH-DSA)");
    expect(evidence.report).not.toContain("<script");
    verifies(evidence.file, copy.dataDir);
  } finally {
    await stopCopy(copy);
  }
});

// ---------------------------------------------------------------- 2. isolated mode

test("isolated mode: Measure all, answers measured on a public copy with their controls, the blocker now measured", async ({
  browser,
}) => {
  test.setTimeout(15 * 60_000);
  let copy: Copy | null = null;
  try {
    copy = await startCopy(browser, 4, "auto");
    test.skip(
      copy.mode !== "isolated",
      "Skipped: Docker is not running or the test images are not prepared (run: cd backend && .venv/bin/python -m app.prepare).",
    );
    const page = copy.page;
    await enterApp(page);
    await openFreshAssessment(page, "Dependencies walk");
    await importVerifyAndOpenTests(page);
    await openDependencies(page);
    expect(await addList(page, LIST)).toBe(200);
    await tiePayServer(page, copy.server);

    // ---- Measure all
    await expect(page.getByRole("button", { name: "Measure all" })).toBeEnabled();
    await page.getByRole("button", { name: "Measure all" }).click();
    const openssl30 = row(page, "openssl 3.0.22");
    await expect((await details(page, "openssl 3.0.22")).getByTestId("measure-state").first()).toHaveText("Measured", {
      timeout: 10 * 60_000,
    });
    for (const label of [
      "openssl 3.0.22",
      "python-ecdsa 0.13.2",
      "openjdk 17.0.2",
      "elliptic 6.5.6",
      "openssl 3.5.9",
    ]) {
      await expect(
        (await details(page, label)).getByTestId("measure-state").first(),
        `${label} should be measured`,
      ).toHaveText("Measured", { timeout: 10 * 60_000 });
      await expect((await details(page, label)).getByTestId("dependency-cell").first()).toContainText(
        "Measured on a public copy",
      );
    }
    await expect((await details(page, "openssl 3.5.9")).getByTestId("dependency-cell").first()).toContainText("Yes");
    await expect((await details(page, "openssl 3.0.22")).getByTestId("agreement").first()).toHaveText(
      "The release notes say the same.",
    );
    await expect((await details(page, "openjdk 17.0.2")).getByTestId("dependency-cell").first()).toContainText(
      "The library itself said no",
    );
    await expect(page.getByText("Measured in your environment")).toHaveCount(0);
    const server = page.getByTestId("dependency-system").filter({ hasText: "Server" });
    await expect(server.getByTestId("blocker-line").first()).toContainText("measured on a public copy");
    await shot(page, "08-isolated-measured.png");
    // Phase 5b (Kevin's note: a red dot beside the acme-sign 1.4.2 heading): that system's box, close up.
    const signing = page.getByTestId("dependency-system").filter({ hasText: "acme-sign 1.4.2" });
    await signing.scrollIntoViewIfNeeded();
    await signing.screenshot({
      path: path.join(screenshotFolder("phase5b"), "red-dot-check-acme-sign-heading.png"),
      animations: "disabled",
    });

    // ---- the measurement behind it: both controls, the locked test, the raw record and the review
    await (await details(page, "openssl 3.0.22")).getByText("Details and evidence").click();
    await expect((await details(page, "openssl 3.0.22")).getByTestId("measurement")).toContainText(
      "Both control copies answered as they must.",
    );
    await expect((await details(page, "openssl 3.0.22")).getByTestId("measurement")).toContainText(
      "This copy is also the incapable control",
    );
    await (
      await details(page, "openssl 3.0.22")
    ).screenshot({ path: path.join(SHOTS, "09-openssl-3.0-measured-details.png"), animations: "disabled" });
    // Phase 5b (Kevin's note: a red dot at the left edge of this line): the measurement, scrolled into view, close up.
    // The panel scrolls inside itself, so the picture is the panel as the screen shows it, the line scrolled into view.
    const controlLine = (await details(page, "openssl 3.0.22"))
      .getByTestId("measurement")
      .getByText("Both control copies answered as they must.");
    await controlLine.evaluate((el) => el.scrollIntoView({ block: "center" }));
    const box = await page.getByTestId("detail-panel").boundingBox();
    if (box)
      await page.screenshot({
        path: path.join(screenshotFolder("phase5b"), "red-dot-check-control-line.png"),
        clip: box,
        animations: "disabled",
      });

    // ---- Measure status, then Download evidence: the measurements are in the signed file, with their runs
    await page.getByRole("button", { name: "Measure status" }).click();
    await expect(page.getByRole("button", { name: "Measure again", exact: true })).toBeEnabled({ timeout: 300_000 });
    const notes = page.getByTestId("roadmap-row").filter({ hasText: "localhost:" }).getByTestId("roadmap-note");
    await page.getByRole("button", { name: "Roadmap", exact: true }).click();
    await expect(notes.filter({ hasText: "measured on a public copy" })).toHaveCount(2);
    const evidence = await downloadEvidence(page);
    const part = evidence.json.evidence.dependencies;
    expect(part.measurements.length).toBe(5);
    expect(part.measurements.every((m: { runs: unknown[] }) => m.runs.length === 1)).toBe(true);
    expect(evidence.report).toContain("Measured on a public copy: ");
    verifies(evidence.file, copy.dataDir);
  } finally {
    await stopCopy(copy);
  }
});
