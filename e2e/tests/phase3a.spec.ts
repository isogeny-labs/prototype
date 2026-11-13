// Phase 3a end to end, on the demo, with no internet and with main-screen buttons only (the assistant
// panel is never used): the Fixes step. A failed result's one line in Evidence Lab, View in Fixes, the
// text-only server fix, Connect demo code, the proof that starts and ends by itself, the change, the
// proof tables and the technical details, a pull request with two reviewers, Approve, Merge with its
// confirm box, Download patch, Retest now with before and after against the answer key, Download
// evidence with the `evidence verify` command, and two states the main flow never reaches (a proof
// that failed, a proof that is out of date).
//
// It starts from its own fresh import (Use demo file again), so it works after phase1 and phase2 in
// the same run, on the same app and data folder, and also alone.
import { expect, test, type APIResponse, type BrowserContext, type Download, type Locator, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { BACKEND, DISCLAIMER, PYTHON, REPO, enterApp, importVerifyAndOpenTests, password, screenshotFolder } from "./shared";

const SHOTS = screenshotFolder("phase3a");
const PQ_TOO_OLD = "Couldn't run (needs OpenSSL 3.5 or newer)";
const STEPS = ["1. Import", "2. Verify", "3. Tests", "4. Evidence Lab", "5. Fixes"];
const SUGGESTED = ["Old TLS versions", "Certificate strength", "Official test vectors", "Bad signatures", "Speed and size"];
const ALL_SIX = [...SUGGESTED, "Post-quantum readiness"];

const CODE_FIX = "fix-ecdsa-range-check";
const CODE_FIX_TITLE = "acme-sign accepts out-of-range signatures";
const TLS_FIX = "fix-tls-versions";
const TLS_FIX_TITLE = "Server accepts TLS 1.2";
const SIZE = "3 lines added and 1 removed";
const PATCH_NAME = "acme-sign-pull-request-1.patch";
const ONE_LOGIN =
  "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown.";
// What the summary says about the server finding: before a proof has passed it must not say the change fixes anything.
const SERVER_LINE_UNPROVEN = "This change is for the signing program only. The server finding is separate and still open.";
const SERVER_LINE_PROVEN = "This fixes the signing program. The server finding is separate and still open.";
const PROOF_PASSED =
  "All 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before.";
const PROOF_RUNNING_BLOCKS = "A proof is running in Fixes. Wait until it has finished.";
const TLS_LINE = "Text-only suggestion: a server setting";

// The answer key. It is read here and never edited: the right result of every demo test on 1.4.2 and on 1.4.3.
const KEY = JSON.parse(fs.readFileSync(path.join(REPO, "demo/expected.json"), "utf8"));
// Which row of Evidence Lab answers which entry of the key (the same pairing as backend/app/accuracy.py).
const KEY_ROWS: Record<string, string> = {
  T1: "tls_versions", T2: "certificate", T3: "official_vectors", T4: "bad_signatures", T5: "speed_size",
  R1: "tls_versions", R2: "certificate", R3: "official_vectors", R4: "bad_signatures", R5: "speed_size",
};

let context: BrowserContext;
let page: Page;
let downloads: string;
let proofFingerprint = ""; // the evidence fingerprint of the proof, as Technical details shows it
let mergeCommit = ""; // the short id of the merge commit, as Technical details shows it
let patchText = "";
let evidenceJson = "";
let evidenceHtml = "";

async function shot(name: string, fullPage = true): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage, animations: "disabled" });
}

function card(title: string | RegExp): Locator {
  return page.getByTestId("test-card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

function labRow(title: string): Locator {
  return page.getByTestId("lab-row").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

/** The words of a result badge, without its symbol. */
function badge(scope: Locator): Locator {
  return scope.getByTestId("result-badge").locator("span:last-child");
}

async function cardTitles(): Promise<string[]> {
  return page.getByTestId("test-card").getByRole("heading").evaluateAll((all) =>
    // The heading may carry a small tag after the title; the title is its first text.
    all.map((h) => (h.firstChild?.textContent ?? "").trim()),
  );
}

async function cardStatuses(): Promise<string[]> {
  return page.getByTestId("test-card").evaluateAll((all) => all.map((c) => c.getAttribute("data-status") ?? ""));
}

// The next three are the same checks phase2.spec.ts makes, here on the Fixes step too.

/** This version has no way to bring in outside software: no file picker, no drop zone, no upload wording. */
async function expectNoSoftwareUpload(): Promise<void> {
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  expect(await page.locator("body").innerText()).not.toMatch(/upload|drop (a|your) file|choose a file|browse/i);
}

/** The app never calls anything secure (outside the one fixed line), never scores, never estimates time to hack. */
async function expectCarefulWording(): Promise<void> {
  const text = (await page.locator("body").innerText()).replaceAll(DISCLAIMER, "");
  expect(text).not.toMatch(/\bsecure\b|security score|\bscore\b|time[- ]to[- ]hack/i);
}

function verifyEvidence(file: string): { code: number; output: string } {
  const run = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", process.env.E2E_DATA_DIR ?? ""], {
    cwd: BACKEND,
    encoding: "utf8",
    timeout: 60_000,
  });
  return { code: run.status ?? -1, output: `${run.stdout}${run.stderr}` };
}

async function goTo(step: string): Promise<void> {
  await page.getByRole("navigation", { name: "Steps" }).getByRole("button", { name: step }).click();
  await expect(page.getByRole("navigation", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText(step);
}

/** Opens a result in Evidence Lab (if it is closed) and hands back its row. */
async function openLabRow(title: string): Promise<Locator> {
  const row = labRow(title);
  const toggle = row.getByRole("button", { name: title, exact: true });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  return row;
}

async function closeLabRow(title: string): Promise<void> {
  const toggle = labRow(title).getByRole("button", { name: title, exact: true });
  if ((await toggle.getAttribute("aria-expanded")) === "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
}

/** A failed result that has a fix shows one line with View in Fixes, and no "Suggested fix" box. */
async function expectFixLine(detail: Locator, words: string, look: "plain" | "pass" | "fail" | "dashed"): Promise<void> {
  const line = detail.getByTestId("fix-line");
  await expect(line).toHaveCount(1);
  await expect(line.locator("p")).toHaveText(words);
  await expect(line).toHaveAttribute("data-look", look);
  await expect(line.getByRole("button", { name: "View in Fixes" })).toBeEnabled();
  await expect(detail.getByTestId("suggested-fix")).toHaveCount(0);
  await expect(detail.getByText("Suggested fix", { exact: true })).toHaveCount(0);
}

// ---- the Fixes step

function fixList(): Locator {
  return page.getByRole("navigation", { name: /^Open findings with a fix/ });
}

/** The entry of one fix in the list on the left. */
function listed(title: string): Locator {
  return fixList().getByRole("button").filter({ hasText: title });
}

/** The summary card of the selected fix. */
function summary(): Locator {
  return page.getByTestId("fix-summary");
}

function section(key: "change" | "proof" | "details" | "suggestion"): Locator {
  return page.locator(`[data-testid="fix-section"][data-section="${key}"]`);
}

async function setSection(key: "change" | "proof" | "details" | "suggestion", open: boolean): Promise<void> {
  const fold = section(key).getByRole("button").first();
  if ((await fold.getAttribute("aria-expanded")) !== String(open)) await fold.click();
  await expect(fold).toHaveAttribute("aria-expanded", String(open));
}

async function selectFix(title: string, id: string): Promise<void> {
  await listed(title).click();
  await expect(listed(title)).toHaveAttribute("aria-current", "true");
  await expect(summary()).toHaveAttribute("data-fix-id", id);
}

/** The status of the code fix, in the summary and in the list. */
async function expectStatus(key: string, word: string): Promise<void> {
  await expect(summary().getByTestId("fix-status")).toHaveAttribute("data-status", key, { timeout: 15_000 });
  await expect(summary().getByTestId("fix-status")).toHaveText(word);
  await expect(listed(CODE_FIX_TITLE).getByTestId("fix-status")).toHaveText(word);
}

/** Before a proof has passed, the summary never calls the change ready and never says that it fixes anything. */
async function expectUnproven(): Promise<void> {
  expect(await summary().innerText()).not.toMatch(/Ready for review|Ready to merge|Proof passed|Fix ready|This fixes|What it fixes/);
  await expect(summary().getByTestId("server-line")).toHaveText(SERVER_LINE_UNPROVEN);
}

async function planId(): Promise<number> {
  const current = await (await page.request.get("/api/import/current")).json();
  const plan = await (await page.request.get(`/api/import/${current.id}/plan`)).json();
  return plan.id as number;
}

/** Where the code fix stands, straight from the app's records (the same view the screen draws). */
async function codeFixStatus(plan: number): Promise<string> {
  const view = await (await page.request.get(`/api/plans/${plan}/fixes`)).json();
  return view.fixes.find((f: any) => f.id === CODE_FIX).status.key as string;
}

/**
 * Asks the addresses behind Open pull request, Approve, Merge pull request, Download patch and Retest now
 * directly. Before a proof has passed every one of them must refuse, with a plain sentence, and change nothing.
 */
async function expectNothingOffered(plan: number): Promise<void> {
  const base = `/api/plans/${plan}/fixes/${CODE_FIX}`;
  const before = await codeFixStatus(plan);
  const asked: [string, APIResponse][] = [
    ["open pull request", await page.request.post(`${base}/pull-request`, { data: { reviewers: ["you"] } })],
    ["approve", await page.request.post(`${base}/approve`, { data: { reviewer: "you" } })],
    ["merge", await page.request.post(`${base}/merge`)],
    ["download patch", await page.request.get(`${base}/patch`)],
    ["retest now", await page.request.post(`${base}/retest`)],
  ];
  for (const [what, answer] of asked) {
    expect(answer.status(), `${what} answered ${answer.status()}`).toBeGreaterThanOrEqual(400);
    expect(answer.status(), `${what} answered ${answer.status()}`).toBeLessThan(500);
    const message = (await answer.json()).error.message as string;
    expect(message, what).toMatch(/^[A-Z].*\.$/);
  }
  expect(await codeFixStatus(plan)).toBe(before);
}

interface ProofWatch {
  /** Each status the summary showed, in order, without repeats. */
  statuses: string[];
  /** Every different progress sentence seen while it said Proving. */
  progress: string[];
  /** Whether the summary ever showed a button while it said Proving. */
  buttonsWhileProving: string[];
}

/** Watches the summary of the code fix while a proof runs, pressing nothing, until it no longer says Proving. */
async function watchProof(): Promise<ProofWatch> {
  const statuses: string[] = [];
  const progress = new Set<string>();
  const buttonsWhileProving = new Set<string>();
  const deadline = Date.now() + 200_000;
  for (;;) {
    // One look at the screen at a time, so a status and its buttons always belong together.
    const seen = await summary().evaluate((el) => ({
      status: el.querySelector('[data-testid="fix-status"]')?.getAttribute("data-status") ?? "",
      proof: (el.querySelector('[data-testid="fix-proof"]')?.textContent ?? "").replace(/\s+/g, " ").trim(),
      buttons: [...el.querySelectorAll("button")].map((b) => (b.textContent ?? "").trim()),
    }));
    if (statuses[statuses.length - 1] !== seen.status) statuses.push(seen.status);
    if (seen.status !== "proving") break;
    progress.add(seen.proof);
    for (const b of seen.buttons) buttonsWhileProving.add(b);
    expect(Date.now(), `the proof was still running after 200 s: ${seen.proof}`).toBeLessThan(deadline);
    await page.waitForTimeout(200);
  }
  return { statuses, progress: [...progress], buttonsWhileProving: [...buttonsWhileProving] };
}

/** One row of a proof table: the result before, the result of the proof run, and the rule check. */
async function expectProofRow(kind: string, before: string, proof: string, check: string): Promise<void> {
  const row = page.locator(`[data-testid="proof-row"][data-kind="${kind}"]`);
  await expect(row).toHaveCount(1);
  await expect(badge(row.getByTestId("proof-cell-before"))).toHaveText(before);
  await expect(badge(row.getByTestId("proof-cell-proof"))).toHaveText(proof);
  await expect(row.getByTestId("proof-check")).toHaveAttribute("data-ok", "true");
  await expect(row.getByTestId("proof-check").locator("span:last-child")).toHaveText(check);
  if (!proof.startsWith("Couldn't run")) await expect(row.getByTestId("proof-cell-proof")).toContainText(/Control: .* as expected\./);
}

/** One fact of Technical details, by its label. */
function fact(label: string): Locator {
  return section("details").getByTestId("detail-fact").filter({ has: page.getByText(label, { exact: true }) }).locator("dd");
}

/** The "Code" item of an opened result's run record, which must come right after "Component". */
async function codeItem(detail: Locator): Promise<string> {
  return detail.evaluate((el) => {
    const component = [...el.querySelectorAll("li")].find((li) => (li.textContent ?? "").startsWith("Component:"));
    return (component?.nextElementSibling?.textContent ?? "").replace(/\s+/g, " ").trim();
  });
}

async function runAllAndWait(count: number): Promise<void> {
  await page.getByRole("button", { name: "Run all" }).click();
  await expect.poll(cardStatuses, { timeout: 200_000 }).toEqual(Array(count).fill("done"));
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  downloads = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-downloads-"));
  context = await browser.newContext({ acceptDownloads: true });
  page = await context.newPage();
});

test.afterAll(async () => {
  await context.close();
  fs.rmSync(downloads, { recursive: true, force: true });
});

test("a fresh import: Verify, the five suggested tests plus Post-quantum readiness, Run all", async () => {
  await enterApp(page);
  // Use demo file again. A new imported file gets its own plan and its own fresh copy of the demo repository.
  await importVerifyAndOpenTests(page);
  const cards = page.getByTestId("test-card");
  await expect(cards).toHaveCount(5);
  expect(await cardTitles()).toEqual(SUGGESTED);
  await expect(cards.getByTestId("test-status")).toHaveText(Array(5).fill("Not run yet"));

  // Five steps. Fixes, like Evidence Lab, opens once there is a result.
  const steps = page.getByRole("navigation", { name: "Steps" });
  await expect(steps.getByRole("button")).toHaveText(STEPS);
  await expect(steps.getByRole("button", { name: "4. Evidence Lab" })).toBeDisabled();
  await expect(steps.getByRole("button", { name: "5. Fixes" })).toBeDisabled();

  await page.getByRole("button", { name: "+ Add test" }).click();
  await page.getByRole("menu").getByRole("menuitem").filter({ hasText: "Post-quantum readiness" }).click();
  await expect(cards).toHaveCount(6);
  expect(await cardTitles()).toEqual(ALL_SIX);

  await runAllAndWait(6);
  await expect(badge(card("Old TLS versions"))).toHaveText("Failed");
  await expect(badge(card("Certificate strength"))).toHaveText("Passed");
  await expect(badge(card("Official test vectors"))).toHaveText("Failed");
  await expect(badge(card("Bad signatures"))).toHaveText("Failed");
  await expect(badge(card("Speed and size"))).toHaveText("Measured");
  expect(["Not offered", PQ_TOO_OLD]).toContain((await badge(card("Post-quantum readiness")).innerText()).trim());
  await expect(steps.getByRole("button", { name: "4. Evidence Lab" })).toBeEnabled();
  await expect(steps.getByRole("button", { name: "5. Fixes" })).toBeEnabled();
});

test("Evidence Lab: each failed result that has a fix shows one line with View in Fixes; the others keep their advice box", async () => {
  await goTo("4. Evidence Lab");
  await expect(page.getByRole("heading", { name: "Evidence Lab", level: 1 })).toBeVisible();
  await expect(page.getByTestId("lab-row")).toHaveCount(6);
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);

  const lines: Record<string, [string, "plain" | "dashed"]> = {
    "Old TLS versions": [TLS_LINE, "dashed"],
    "Official test vectors": ["Fix available, code not connected", "plain"],
    "Bad signatures": ["Fix available, code not connected", "plain"],
  };
  for (const title of ALL_SIX) {
    const row = await openLabRow(title);
    const detail = row.getByTestId("result-detail");
    await expect(detail).toHaveCount(1);
    const line = lines[title];
    if (line) {
      await expect(badge(row).first()).toHaveText("Failed");
      await expectFixLine(detail, line[0], line[1]);
    } else {
      // Not a failure: no line. Its advice stays in Evidence Lab, in the box it always had.
      await expect(detail.getByTestId("fix-line")).toHaveCount(0);
      await expect(detail.getByRole("button", { name: "View in Fixes" })).toHaveCount(0);
      const label = (await badge(row).first().innerText()).trim();
      if (!label.startsWith("Couldn't run")) {
        await expect(detail.getByTestId("suggested-fix")).toHaveCount(1);
        await expect(detail.getByTestId("suggested-fix").getByRole("heading")).toHaveText("Suggested fix");
      }
    }
    // Mark reviewed and Dig deeper are on every result, as before.
    await expect(detail.getByRole("button", { name: "Mark reviewed" })).toBeEnabled();
    await expect(detail.getByRole("button", { name: "Dig deeper" })).toBeEnabled();
    await closeLabRow(title);
  }
  await expect(labRow("Certificate strength")).toContainText("NIST plans to retire P-256");

  // Evidence Lab itself shows no change, no diff and no pull request: only the line.
  const bad = await openLabRow("Bad signatures");
  await expect(bad.getByTestId("result-detail")).toContainText("r=0, s=0");
  await expect(page.getByTestId("code-line")).toHaveCount(0);
  await expect(page.getByTestId("change-part")).toHaveCount(0);
  for (const name of ["Connect demo code", "Open pull request", "Merge pull request", "Download patch", "Retest now"]) {
    await expect(page.getByRole("button", { name })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("01-lab-fix-line.png");
});

test("View in Fixes opens the right fix; Fixes lists the two findings with their statuses", async () => {
  // From the signing failure: the code fix.
  await labRow("Bad signatures").getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText("5. Fixes");
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);
  await expect(summary().getByRole("heading", { level: 2 })).toHaveText(CODE_FIX_TITLE);
  await expect(page.getByTestId("fixes-subline")).toHaveText(
    "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed.",
  );
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByText("Demo data", { exact: true }).first()).toBeVisible();

  await expect(fixList().getByRole("heading")).toHaveText("Open findings with a fix (2)");
  const items = fixList().getByRole("button");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText(CODE_FIX_TITLE);
  await expect(items.nth(0).getByTestId("fix-status")).toHaveText("Code not connected");
  await expect(items.nth(0)).toContainText("Came from 2 failed tests: Official test vectors, Bad signatures");
  await expect(items.nth(0)).toHaveAttribute("aria-current", "true");
  await expect(items.nth(1)).toContainText(TLS_FIX_TITLE);
  await expect(items.nth(1).getByTestId("fix-status")).toHaveText("Text only");
  await expect(items.nth(1)).toContainText("Came from 1 failed test: Old TLS versions");
  await expect(items.nth(1)).not.toHaveAttribute("aria-current", "true");

  // From the other failed signing test: the same fix (one fix answers both).
  await goTo("4. Evidence Lab");
  const vectors = await openLabRow("Official test vectors");
  await vectors.getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);

  // From the server failure: the server fix.
  await goTo("4. Evidence Lab");
  const tls = await openLabRow("Old TLS versions");
  await tls.getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  await expect(summary()).toHaveAttribute("data-fix-id", TLS_FIX);
  await expect(summary().getByRole("heading", { level: 2 })).toHaveText(TLS_FIX_TITLE);
  await expect(listed(TLS_FIX_TITLE)).toHaveAttribute("aria-current", "true");
  await expect(listed(CODE_FIX_TITLE)).not.toHaveAttribute("aria-current", "true");
});

test("the server fix is Text only: its suggestion, and no button of any kind", async () => {
  const s = summary();
  await expect(s.getByTestId("fix-status")).toHaveText("Text only");
  await expect(s.getByTestId("fix-status")).toHaveAttribute("data-status", "text_only");
  await expect(s.getByTestId("fix-source")).toHaveText(
    "Came from 1 failed test on server localhost:8443: Old TLS versions. The file claims TLS 1.3 only.",
  );
  await expect(s.getByTestId("fix-what")).toContainText("A server setting, not a code change");
  await expect(s.getByTestId("fix-proof")).toHaveText("None. This suggestion is text only: the app has not applied it or tested it.");
  await expect(s.getByTestId("fix-approvers")).toHaveText("Your own server team, outside this app. The app never changes your server.");
  await expect(s).not.toContainText("From a fix template");

  // No button: none in the summary, and none of a code fix's anywhere on the screen.
  await expect(s.getByRole("button")).toHaveCount(0);
  await expect(s.getByTestId("fix-actions")).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  for (const name of ["Connect demo code", "Run proof again", "Open pull request", /^Approve/, "Merge pull request", "Download patch", "Retest now", "Prepare change"]) {
    await expect(page.getByRole("button", { name })).toHaveCount(0);
  }
  await expect(page.getByTestId("code-line")).toHaveCount(0);
  await expect(page.getByTestId("proof-table")).toHaveCount(0);

  // One section, open: the suggestion (section 7c of the spec).
  await expect(page.getByTestId("fix-section")).toHaveCount(1);
  await expect(section("suggestion").getByRole("button").first()).toHaveAttribute("aria-expanded", "true");
  const text = section("suggestion").getByTestId("text-suggestion");
  await expect(text).toContainText("This is usually a server setting, not a code change.");
  await expect(text).toContainText("The server accepted TLS 1.2, with the older cipher suite");
  await expect(text).toContainText("ECDHE-ECDSA-AES128-SHA");
  await expect(text.getByTestId("suggestion-warning")).toContainText("Before you switch TLS 1.2 off:");
  await expect(text.getByTestId("suggestion-warning")).toContainText("older clients and partner systems that can't use TLS 1.3 will no longer be able to connect.");
  await expect(text).toContainText("Where the setting lives");
  for (const place of ["nginx", "Apache", "A cloud load balancer", "Your own application"]) {
    await expect(text.getByText(place, { exact: true }).first()).toBeVisible();
  }
  await expect(text).toContainText("ssl_protocols TLSv1.3;");
  await expect(text).toContainText("SSLProtocol -all +TLSv1.3");
  const options = text.getByTestId("suggestion-option");
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toContainText("Option 1: switch TLS 1.2 off");
  await expect(options.nth(0)).toContainText("Check the access logs");
  await expect(options.nth(1)).toContainText("Option 2: keep TLS 1.2, with strong settings only");
  await expect(options.nth(1)).toContainText("Correct the scanner file so that it says TLS 1.2 and TLS 1.3.");
  await expect(text.getByTestId("suggestion-exact")).toContainText("ssl_protocols TLSv1.2 TLSv1.3;");
  await expectNoSoftwareUpload();
  await expectCarefulWording();
});

test("before the code is connected: Code not connected, one button, and nothing can be opened, approved, merged or downloaded", async () => {
  await selectFix(CODE_FIX_TITLE, CODE_FIX);
  const s = summary();
  await expectStatus("not_connected", "Code not connected");
  await expect(s).toContainText("From a fix template");
  await expect(s.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(s.getByTestId("fix-source")).toHaveText(
    "Came from 2 failed tests on signing component acme-sign 1.4.2: Official test vectors and Bad signatures.",
  );
  await expect(s.getByTestId("fix-what")).toContainText("A fix template exists for this failure");
  await expect(s.getByTestId("fix-proof")).toHaveAttribute("data-state", "not_started");
  await expect(s.getByTestId("fix-proof")).toContainText("Not started. It starts by itself once the code is connected");
  await expect(s.getByTestId("fix-approvers")).toHaveText("You pick the reviewers once the proof has passed.");
  await expectUnproven();

  // One button, switched on because every test in the plan has a result.
  await expect(s.getByRole("button")).toHaveText(["Connect demo code"]);
  await expect(s.getByRole("button", { name: "Connect demo code" })).toBeEnabled();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(page.getByTestId("fix-section")).toHaveCount(0);
  await expect(page.getByTestId("fix-sections-note")).toHaveText(
    "The change, its proof and the technical details appear below once the code is connected.",
  );
  await expectNothingOffered(await planId());
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("02-fixes-code-not-connected.png");
});

test("Connect demo code: the proof starts by itself; while it runs the status is Proving and nothing is offered", async () => {
  const plan = await planId();
  const s = summary();
  await s.getByRole("button", { name: "Connect demo code" }).click();

  await expectStatus("proving", "Proving");
  await expect(s.getByTestId("fix-proof")).toHaveAttribute("data-state", "running");
  await expect(s.getByTestId("fix-proof")).toHaveText(/^Running: \d of 6 tests finished\. Not offered yet\.$/);
  await expect(s.getByTestId("fix-what")).toContainText(`${SIZE}.`);
  await expect(s.getByTestId("fix-approvers")).toHaveText("You pick the reviewers once the proof has passed.");
  await expect(s.getByRole("button")).toHaveCount(0);
  await expectUnproven();

  // The change is on screen at once: 3 lines added and 1 removed. The proof and the details are folded.
  await expect(page.getByTestId("fix-section")).toHaveCount(3);
  await expect(section("change").getByRole("button").first()).toHaveAttribute("aria-expanded", "true");
  await expect(section("proof").getByRole("button").first()).toHaveAttribute("aria-expanded", "false");
  await expect(section("details").getByRole("button").first()).toHaveAttribute("aria-expanded", "false");
  await expect(section("change").getByTestId("fix-section-line")).toHaveText(`${SIZE}, in 1 file (acme_sign.py)`);
  await expect(section("proof").getByTestId("fix-section-line")).toHaveText(/^Running: \d of 6 tests finished\.$/);
  await expect(page.locator('[data-testid="code-line"][data-mark="+"]')).toHaveCount(3);
  await expect(page.locator('[data-testid="code-line"][data-mark="-"]')).toHaveCount(1);
  await expectNothingOffered(plan);
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("03-fixes-proving.png");

  // The Proof section can be opened while the proof runs: every test of the plan is listed, none is judged yet.
  await setSection("proof", true);
  const open = await section("proof").evaluate((el) => ({
    status: document.querySelector('[data-testid="fix-summary"] [data-testid="fix-status"]')?.getAttribute("data-status") ?? "",
    rows: el.querySelectorAll('[data-testid="proof-row"]').length,
    waiting: el.querySelectorAll('[data-testid="proof-waiting"]').length,
    checks: [...el.querySelectorAll('[data-testid="proof-check"]')].map((c) => c.getAttribute("data-ok")),
    verdicts: el.querySelectorAll('[data-testid="proof-verdict"]').length,
  }));
  expect(open.status, "the proof was still running when its section was opened").toBe("proving");
  expect(open.rows).toBe(6);
  expect(open.waiting).toBeGreaterThanOrEqual(1);
  expect(open.checks).toEqual(Array(6).fill("null"));
  expect(open.verdicts).toBe(0);
  await shot("03a-fixes-proving-proof-open.png");
  // The proof was still running when the picture was taken.
  await expect(summary().getByTestId("fix-status")).toHaveAttribute("data-status", "proving");
  await setSection("proof", false);
});

test("while the proof runs, Evidence Lab's line says so, and Retest new version and Download evidence are off with the reason", async () => {
  // Tests: nothing can be started while the proof runs, and the cards keep their first results (a proof replaces none).
  await goTo("3. Tests");
  await expect(page.getByTestId("test-card")).toHaveCount(6);
  await expect(page.getByRole("button", { name: "Run all" })).toBeDisabled();
  for (const title of ALL_SIX) await expect(card(title).getByRole("button", { name: `Run ${title}` })).toBeDisabled();
  expect(await cardStatuses()).toEqual(Array(6).fill("done"));
  await expect(badge(card("Bad signatures"))).toHaveText("Failed");
  // The addresses behind Run all, Retest new version and Download evidence refuse as well, each with the reason.
  const plan = await planId();
  const refused: [string, APIResponse][] = [
    ["run all", await page.request.post(`/api/plans/${plan}/run-all`)],
    ["retest", await page.request.post(`/api/plans/${plan}/retest`, { data: { version: "1.4.3" } })],
    ["download evidence", await page.request.post(`/api/plans/${plan}/evidence`)],
  ];
  for (const [what, answer] of refused) {
    expect(answer.status(), what).toBe(409);
    expect((await answer.json()).error.message, what).toBe(PROOF_RUNNING_BLOCKS);
  }
  expect(await codeFixStatus(plan), "the proof was still running while all of this was asked").toBe("proving");

  await goTo("4. Evidence Lab");
  const vectors = await openLabRow("Official test vectors");
  await expectFixLine(vectors.getByTestId("result-detail"), `Fix prepared: ${SIZE}, proof running`, "plain");
  await closeLabRow("Official test vectors");
  const bad = await openLabRow("Bad signatures");
  await expectFixLine(bad.getByTestId("result-detail"), `Fix prepared: ${SIZE}, proof running`, "plain");

  await expect(page.getByRole("button", { name: "Retest new version" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeDisabled();
  await expect(page.getByTestId("blocked-reason")).toHaveText([PROOF_RUNNING_BLOCKS]);
  // A proof reruns the tests, but these results are not being replaced, so the page must not say tests are running.
  await expect(page.getByTestId("lab-subline")).not.toContainText("Tests are running");
  await expect(page.getByTestId("lab-subline")).toContainText("Run finished");
  await expect(page.getByTestId("lab-row")).toHaveCount(6);
  await shot("04-lab-fix-line-proof-running.png");
});

test("with nobody pressing anything, the status goes from Proving to Ready for review, with Proof passed", async () => {
  // Back to Fixes through the line's own button. From here nothing is pressed until the proof has ended.
  await labRow("Bad signatures").getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);
  const watched = await watchProof();
  test.info().annotations.push({ type: "proof", description: `statuses seen: ${watched.statuses.join(" -> ")}; progress: ${watched.progress.join(" | ")}` });
  // It was still running when we came back, it never read Proof failed on the way, and it ended as Ready for review.
  expect(watched.statuses).toEqual(["proving", "ready"]);
  expect(watched.progress.length).toBeGreaterThanOrEqual(1);
  for (const sentence of watched.progress) expect(sentence).toMatch(/^Running: \d of 6 tests finished\. Not offered yet\.$/);
  expect(watched.buttonsWhileProving).toEqual([]);

  const s = summary();
  await expectStatus("ready", "Ready for review");
  await expect(s.getByTestId("fix-proof")).toHaveAttribute("data-state", "passed");
  await expect(badge(s.getByTestId("fix-proof"))).toHaveText("Proof passed");
  await expect(s.getByTestId("fix-proof").locator("p")).toHaveText(PROOF_PASSED);
  // Only now does the summary say that the change fixes something.
  await expect(s.locator("dt").first()).toHaveText("What it fixes");
  await expect(s.getByTestId("fix-what")).toContainText("Adds the missing range check to acme-sign's signature check");
  await expect(s.getByTestId("fix-what")).toContainText(`${SIZE}.`);
  await expect(s.getByTestId("server-line")).toHaveText(SERVER_LINE_PROVEN);

  // Who approves: a tick list. "You" is ticked; the two demo reviewers are labelled Demo data.
  const who = s.getByRole("group", { name: "Who approves" });
  await expect(who.getByRole("checkbox")).toHaveCount(3);
  await expect(who.getByRole("checkbox", { name: /^You/ })).toBeChecked();
  await expect(who.getByRole("checkbox", { name: /Demo reviewer A/ })).not.toBeChecked();
  await expect(who.getByRole("checkbox", { name: /Demo reviewer B/ })).not.toBeChecked();
  for (const name of ["Demo reviewer A", "Demo reviewer B"]) {
    await expect(who.locator("label").filter({ hasText: name }).getByText("Demo data", { exact: true })).toBeVisible();
  }
  await expect(who.locator("label").filter({ hasText: "You" }).getByText("Demo data", { exact: true })).toHaveCount(0);
  await expect(s.getByTestId("fix-approvers")).toContainText(ONE_LOGIN);

  // One button. Nothing can be approved, merged or downloaded before a pull request is open.
  await expect(s.getByRole("button")).toHaveText(["Open pull request"]);
  await expect(s.getByRole("button", { name: "Open pull request" })).toBeEnabled();
  await expect(s.getByTestId("fix-actions")).toContainText(
    "Nothing goes into the main copy of the code until the reviewers you pick approve and you confirm the merge.",
  );
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("05-fixes-ready-for-review.png");

  // With the proof over, tests can be started again.
  await goTo("3. Tests");
  await expect(page.getByRole("button", { name: "Run all" })).toBeEnabled();
  await expect(card("Bad signatures").getByRole("button", { name: "Run Bad signatures" })).toBeEnabled();
  await goTo("5. Fixes");
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);
  await expectStatus("ready", "Ready for review");
});

test("the change is 3 lines added and 1 removed; the proof tables show every test of the plan; Technical details shows commit ids and fingerprints", async () => {
  // The change: exactly the range check and the version line, labelled as coming from a fix template.
  const change = section("change");
  await expect(change.getByTestId("fix-section-line")).toHaveText(`${SIZE}, in 1 file (acme_sign.py)`);
  await expect(change).toContainText("Written from a fix template");
  await expect(change).toContainText("It was not written by an AI model");
  await expect(summary()).toContainText("From a fix template");
  await expect(change.getByTestId("change-part")).toHaveCount(2);
  const added = change.locator('[data-testid="code-line"][data-mark="+"]');
  const removed = change.locator('[data-testid="code-line"][data-mark="-"]');
  await expect(added.locator("span:nth-child(3)")).toHaveText(['if not (1 <= r < N and 1 <= s < N):', 'return {"valid": False}', 'VERSION = "1.4.3"']);
  await expect(added.locator("span:nth-child(1)")).toHaveText(["169", "170", "20"]);
  await expect(removed.locator("span:nth-child(3)")).toHaveText(['VERSION = "1.4.2"']);
  await expect(removed.locator("span:nth-child(1)")).toHaveText(["20"]);
  await expect(change.getByTestId("change-part").nth(0)).toContainText("nothing removed here");
  await expect(change.getByTestId("change-part").nth(0)).toContainText("2 lines added (marked +)");

  // The proof: every test of the plan, each with its result before and on the changed code.
  await setSection("proof", true);
  const proof = section("proof");
  await expect(proof.getByTestId("fix-section-line")).toHaveText(`Passed: a${PROOF_PASSED.slice(1)}`);
  await expect(proof).toContainText("then reran every locked test in your plan, with the old and the new version timed side by side");
  const tables = proof.getByTestId("proof-table");
  await expect(tables).toHaveCount(2);
  await expect(tables.nth(0)).toContainText("Tests that run the changed code");
  await expect(tables.nth(0).getByTestId("proof-columns").locator("span")).toHaveText(["Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"]);
  await expect(tables.nth(0).getByTestId("proof-row")).toHaveCount(3);
  await expect(tables.nth(1)).toContainText("Tests that don't run this code (they test the server)");
  await expect(tables.nth(1).getByTestId("proof-row")).toHaveCount(3);
  const titles = await proof.getByTestId("proof-row").locator("> p").allInnerTexts();
  expect(titles.map((t) => t.trim()).sort()).toEqual([...ALL_SIX].sort());

  await expectProofRow("official_vectors", "Failed", "Passed", "Passed");
  await expectProofRow("bad_signatures", "Failed", "Passed", "Passed");
  await expectProofRow("speed_size", "Measured", "No slowdown beyond measured noise", "No slowdown");
  await expectProofRow("tls_versions", "Failed", "Failed", "Same as before");
  await expectProofRow("certificate", "Passed", "Passed", "Same as before");
  const pq = (await badge(page.locator('[data-testid="proof-row"][data-kind="pq_readiness"]').getByTestId("proof-cell-before")).innerText()).trim();
  expect(["Not offered", PQ_TOO_OLD]).toContain(pq);
  await expectProofRow("pq_readiness", pq, pq, "Same as before");
  const row = (kind: string) => page.locator(`[data-testid="proof-row"][data-kind="${kind}"]`);
  await expect(row("official_vectors").getByTestId("proof-cell-proof")).toContainText("484 of 484 official cases right.");
  await expect(row("bad_signatures").getByTestId("proof-cell-proof")).toContainText("Rejects r=0, s=0");
  await expect(row("speed_size").getByTestId("proof-cell-proof")).toContainText(/on acme-sign 1\.4\.3, against .* on acme-sign 1\.4\.2, measured side by side/);
  await expect(row("tls_versions").getByTestId("proof-cell-proof")).toContainText("Server still accepts TLS 1.2. This change doesn't touch the server.");
  await expect(page.getByText("Couldn't trust this run")).toHaveCount(0);

  const verdict = proof.getByTestId("proof-verdict");
  await expect(verdict).toHaveAttribute("data-tone", "pass");
  await expect(verdict.getByRole("heading").first()).toHaveText("Why it is ready for review");
  await expect(verdict.getByTestId("proof-check").locator("span:last-child")).toHaveText([
    "All 3 tests that run the changed code passed.",
    "Every control behaved as expected.",
    "The 3 server tests came out the same as before.",
  ]);
  await expect(verdict).toContainText("It doesn't show that the change is free of other faults, and it does nothing about the server finding.");
  // Six rows and three reasons, every one ticked.
  await expect(proof.getByTestId("proof-check")).toHaveCount(9);
  await expect(proof.locator('[data-testid="proof-check"]:not([data-ok="true"])')).toHaveCount(0);

  // Technical details: repository, branches, commit ids, fingerprints, mode.
  await setSection("details", true);
  const details = section("details");
  await expect(fact("Repository")).toHaveText(/^acme-sign\s*Demo data, the app's own copy\. Nothing is sent anywhere else\.$/);
  await expect(fact("Starting point")).toHaveText(/^branch main, commit [0-9a-f]{7} \(acme-sign 1\.4\.2\)$/);
  await expect(fact("Change branch")).toHaveText(/^fix\/ecdsa-range-check, commit [0-9a-f]{7}$/);
  await expect(fact("File changed")).toHaveText(`acme_sign.py: ${SIZE}`);
  await expect(fact("Proof finished")).toHaveText(/, after \d+\.\d s\s*measured$/);
  await expect(fact("Mode")).toHaveText("Demo mode, not isolated");
  proofFingerprint = (await fact("Evidence fingerprint of the proof (SHA-256)").innerText()).trim();
  expect(proofFingerprint).toMatch(/^[0-9a-f]{64}$/);

  // What the tests ran on: our own bundled 1.4.3, after the byte-for-byte check. The two fingerprints match,
  // and they are the fingerprint of the bundled file itself.
  const ranOn = details.getByTestId("ran-on");
  await expect(ranOn).toContainText("What the tests ran on");
  await expect(ranOn).toContainText("Our own bundled demo component, acme-sign 1.4.3.");
  await expect(ranOn).toContainText("is exactly the same as that bundled component, byte for byte");
  await expect(ranOn).toContainText("This version of Evidence Lab only ever runs our own demo software.");
  const prints = (await ranOn.locator("dd").allInnerTexts()).map((t) => t.trim().slice(0, 64));
  expect(prints).toHaveLength(2);
  const bundled = crypto.createHash("sha256").update(fs.readFileSync(path.join(REPO, "demo/components/acme-sign-1.4.3/acme_sign.py"))).digest("hex");
  expect(prints).toEqual([bundled, bundled]);

  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("06-fixes-proof-and-details-open.png");
  await setSection("proof", false);
  await setSection("details", false);
});

test("after the proof Evidence Lab's line reads Fix ready, and the server failure still points to its text-only fix", async () => {
  await goTo("4. Evidence Lab");
  const vectors = await openLabRow("Official test vectors");
  await expectFixLine(vectors.getByTestId("result-detail"), `Fix ready: ${SIZE}, proof passed`, "pass");
  await closeLabRow("Official test vectors");
  const bad = await openLabRow("Bad signatures");
  await expectFixLine(bad.getByTestId("result-detail"), `Fix ready: ${SIZE}, proof passed`, "pass");
  // The two buttons are back on, and the first results are what they were.
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expect(page.getByTestId("blocked-reason")).toHaveCount(0);
  await expect(badge(labRow("Bad signatures")).first()).toHaveText("Failed");
  await expect(page.getByTestId("lab-columns")).toHaveCount(0);
  await shot("07-lab-fix-line-ready.png");
  await closeLabRow("Bad signatures");

  const tls = await openLabRow("Old TLS versions");
  await expectFixLine(tls.getByTestId("result-detail"), TLS_LINE, "dashed");
  await tls.getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(summary()).toHaveAttribute("data-fix-id", TLS_FIX);
  await expect(summary().getByTestId("fix-status")).toHaveText("Text only");
  await expect(summary().getByRole("button")).toHaveCount(0);
  await expect(listed(CODE_FIX_TITLE).getByTestId("fix-status")).toHaveText("Ready for review");
  await expect(section("suggestion").getByTestId("text-suggestion")).toBeVisible();
  await shot("11-fixes-server-tls-text-only.png");
});

test("Open pull request with You and Demo reviewer A; Merge pull request stays off until both have approved", async () => {
  const plan = await planId();
  await selectFix(CODE_FIX_TITLE, CODE_FIX);
  const s = summary();
  const who = s.getByRole("group", { name: "Who approves" });
  await who.getByRole("checkbox", { name: /Demo reviewer A/ }).check();
  await expect(who.getByRole("checkbox", { name: /^You/ })).toBeChecked();
  await expect(who.getByRole("checkbox", { name: /Demo reviewer A/ })).toBeChecked();
  await expect(who.getByRole("checkbox", { name: /Demo reviewer B/ })).not.toBeChecked();
  await s.getByRole("button", { name: "Open pull request" }).click();

  await expectStatus("waiting", "Waiting for approval");
  await expect(s.getByTestId("fix-pull-request")).toContainText("#1 Reject signatures whose r or s is out of range.");
  await expect(s.getByTestId("fix-pull-request")).toContainText("It stays inside the app; nothing is sent anywhere else.");
  await expect(badge(s.getByTestId("fix-proof"))).toHaveText("Proof passed");
  // The two picked reviewers, each with their own Approve button. Demo reviewer B was not picked.
  const rows = s.getByTestId("approval-row");
  await expect(rows).toHaveCount(2);
  expect(await rows.evaluateAll((all) => all.map((r) => r.getAttribute("data-reviewer")))).toEqual(["you", "a"]);
  const you = s.locator('[data-testid="approval-row"][data-reviewer="you"]');
  const reviewerA = s.locator('[data-testid="approval-row"][data-reviewer="a"]');
  await expect(you).toContainText("You");
  await expect(reviewerA).toContainText("Demo reviewer A");
  await expect(reviewerA.getByText("Demo data", { exact: true })).toBeVisible();
  await expect(s).not.toContainText("Demo reviewer B");
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(s.getByRole("button")).toHaveText(["Approve", "Approve as Demo reviewer A", "Merge pull request", "Download patch"]);
  const merge = s.getByRole("button", { name: "Merge pull request" });
  await expect(merge).toBeDisabled();
  await expect(s.getByRole("button", { name: "Download patch" })).toBeEnabled();
  await expect(s.getByTestId("fix-actions")).toContainText(
    '"Merge pull request" unlocks when every reviewer has approved: waiting for You and Demo reviewer A. The app never merges on its own: you press the button and confirm.',
  );
  // The one-login sentence is on screen with the approvals.
  await expect(s.getByTestId("fix-approvers")).toContainText(ONE_LOGIN);
  // The address the confirm button calls refuses too, and nothing changes.
  const early = await page.request.post(`/api/plans/${plan}/fixes/${CODE_FIX}/merge`);
  expect(early.status()).toBeGreaterThanOrEqual(400);
  expect(await codeFixStatus(plan)).toBe("waiting");

  // The patch can be downloaded as soon as the pull request is open.
  const [earlyPatch] = await Promise.all([page.waitForEvent("download"), s.getByRole("button", { name: "Download patch" }).click()]);
  expect(earlyPatch.suggestedFilename()).toBe(PATCH_NAME);
  await earlyPatch.saveAs(path.join(downloads, "before-merge.patch"));

  // Approve (as You). One approval is still missing, so the merge stays off.
  await you.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(you).toContainText("Approved");
  await expect(you.locator("time")).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}T/);
  await expect(you.getByRole("button")).toHaveCount(0);
  await expectStatus("waiting", "Waiting for approval");
  await expect(merge).toBeDisabled();
  await expect(s.getByTestId("fix-actions")).toContainText("waiting for Demo reviewer A.");
  await expect(s.getByRole("button")).toHaveText(["Approve as Demo reviewer A", "Merge pull request", "Download patch"]);
  await expect(s.getByTestId("fix-approvers")).toContainText(ONE_LOGIN);
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("08-fixes-waiting-for-approval.png");

  // Approve as Demo reviewer A. Now every picked reviewer has approved.
  await reviewerA.getByRole("button", { name: "Approve as Demo reviewer A" }).click();
  await expect(reviewerA).toContainText("Approved");
  await expectStatus("ready_to_merge", "Ready to merge");
  await expect(merge).toBeEnabled();
  await expect(s.getByTestId("fix-pull-request")).toContainText("Every reviewer has approved. Not merged yet.");
  await expect(s.getByRole("button")).toHaveText(["Merge pull request", "Download patch"]);
  expect(await codeFixStatus(plan)).toBe("ready_to_merge");
});

test("Merge pull request asks first: Cancel merges nothing, Confirm merge merges", async () => {
  const plan = await planId();
  const s = summary();
  await page.evaluate(() => window.scrollTo(0, 0));
  await s.getByRole("button", { name: "Merge pull request" }).click();
  const dialog = page.getByRole("dialog", { name: "Merge pull request #1?" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(dialog).toContainText(
    "This puts the change on the main branch of the app's own copy of the demo repository acme-sign. After the merge, that branch holds acme-sign 1.4.3.",
  );
  await expect(dialog).toContainText("Every reviewer has approved. The app deploys nothing, and a merge can't be undone here.");
  await expect(dialog.getByRole("button")).toHaveText(["Cancel", "Confirm merge"]);
  // The keyboard starts on Cancel, so Enter pressed straight away merges nothing.
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  // Opening the box has merged nothing.
  expect(await codeFixStatus(plan)).toBe("ready_to_merge");
  await shot("09-fixes-merge-confirm.png", false);

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expectStatus("ready_to_merge", "Ready to merge");
  expect(await codeFixStatus(plan)).toBe("ready_to_merge");
  await expect(s.getByTestId("fix-pull-request")).toContainText("Not merged yet.");

  await s.getByRole("button", { name: "Merge pull request" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Confirm merge" }).click();
  await expect(dialog).toHaveCount(0);
  await expectStatus("merged", "Merged");
  expect(await codeFixStatus(plan)).toBe("merged");
  await expect(s.getByTestId("fix-pull-request")).toHaveText(
    /^#1 Reject signatures whose r or s is out of range\. Merged .+ by the person logged in, after confirming\. The demo repository's main branch now holds acme-sign 1\.4\.3\. Nothing was deployed\.$/,
  );
  // Both approvals stay on record, with the one-login sentence; the summary still carries the server line.
  await expect(s.getByTestId("approval-row")).toHaveCount(2);
  await expect(s.getByTestId("approval-row").locator("time")).toHaveCount(2);
  await expect(s.getByTestId("fix-approvers")).toContainText(ONE_LOGIN);
  await expect(s.getByTestId("server-line")).toHaveText(SERVER_LINE_PROVEN);
  await expect(badge(s.getByTestId("fix-proof"))).toHaveText("Proof passed");
  await expect(s.getByRole("button")).toHaveText(["Retest now", "Download patch"]);
  await expect(s.getByTestId("fix-actions")).toContainText(
    'Reruns the same locked tests on acme-sign 1.4.3, the code now on main, and shows before and after in Evidence Lab. It does the same as "Retest new version" there.',
  );

  await setSection("details", true);
  const merged = (await fact("Pull request").innerText()).replace(/\s+/g, " ").trim();
  expect(merged).toMatch(/^#1, opened .+; merged .+ \(merge commit [0-9a-f]{7}\)$/);
  mergeCommit = /merge commit ([0-9a-f]{7})/.exec(merged)?.[1] ?? "";
  expect(await fact("Evidence fingerprint of the proof (SHA-256)").innerText()).toContain(proofFingerprint);
  await setSection("details", false);
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("10-fixes-merged-retest-now.png");
});

test("Download patch gives acme-sign-pull-request-1.patch: the two added lines and the version line, and git accepts it on 1.4.2", async () => {
  const pagesBefore = context.pages().length;
  const [download] = await Promise.all([page.waitForEvent("download"), summary().getByRole("button", { name: "Download patch" }).click()]);
  expect(download.suggestedFilename()).toBe(PATCH_NAME);
  const file = path.join(downloads, PATCH_NAME);
  await download.saveAs(file);
  // It is saved like the evidence files: no new window.
  expect(context.pages()).toHaveLength(pagesBefore);
  patchText = fs.readFileSync(file, "utf8");
  // The same file before and after the merge.
  expect(fs.readFileSync(path.join(downloads, "before-merge.patch"), "utf8")).toBe(patchText);

  expect(patchText).toContain("Subject: [PATCH] Reject signatures whose r or s is out of range");
  expect(patchText).toContain("From a fix template: ecdsa-range-check");
  expect(patchText).toContain("diff --git a/acme_sign.py b/acme_sign.py");
  expect(patchText).toContain(" 1 file changed, 3 insertions(+), 1 deletion(-)");
  const lines = patchText.split("\n");
  const added = lines.filter((l) => l.startsWith("+") && !l.startsWith("+++"));
  const removed = lines.filter((l) => l.startsWith("-") && !l.startsWith("---") && l !== "-- ");
  expect(added).toEqual(['+VERSION = "1.4.3"', "+    if not (1 <= r < N and 1 <= s < N):", '+        return {"valid": False}']);
  expect(removed).toEqual(['-VERSION = "1.4.2"']);
  expect(patchText.includes("PRIVATE KEY")).toBe(false);

  // With git on this machine: the patch applies to a scratch copy of the bundled 1.4.2 and gives the bundled 1.4.3, byte for byte.
  if (spawnSync("git", ["--version"], { encoding: "utf8" }).status !== 0) {
    test.info().annotations.push({ type: "git", description: "git is not installed here, so `git apply --check` was not tried" });
    return;
  }
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-patch-"));
  try {
    fs.copyFileSync(path.join(REPO, "demo/components/acme-sign-1.4.2/acme_sign.py"), path.join(scratch, "acme_sign.py"));
    // The scratch folder is outside any repository, and git is told not to look for one above it.
    const git = (args: string[]) =>
      spawnSync("git", args, { cwd: scratch, encoding: "utf8", env: { ...process.env, GIT_CEILING_DIRECTORIES: path.dirname(scratch) } });
    const check = git(["apply", "--check", "--verbose", file]);
    expect(check.status, `git apply --check: ${check.stdout}${check.stderr}`).toBe(0);
    const apply = git(["apply", file]);
    expect(apply.status, `git apply: ${apply.stdout}${apply.stderr}`).toBe(0);
    const result = fs.readFileSync(path.join(scratch, "acme_sign.py"));
    expect(result.equals(fs.readFileSync(path.join(REPO, "demo/components/acme-sign-1.4.3/acme_sign.py")))).toBe(true);
    test.info().annotations.push({ type: "git", description: "git apply --check accepted the patch; applied to 1.4.2 it gives 1.4.3 byte for byte" });
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
});

test("Retest now runs the retest and lands on Evidence Lab's before and after, which match the answer key R1 to R5", async () => {
  await summary().getByRole("button", { name: "Retest now" }).click();
  // Straight to Evidence Lab: before and after, running.
  await expect(page.getByRole("heading", { name: "Evidence Lab", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Steps" }).locator('[aria-current="step"]')).toHaveText("4. Evidence Lab");
  await expect(page.getByTestId("lab-columns")).toContainText("Before: acme-sign 1.4.2");
  await expect(page.getByTestId("lab-columns")).toContainText("After: acme-sign 1.4.3");
  await expect(page.getByTestId("retest-progress")).toContainText("Retest running");
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeDisabled();
  await expect(page.getByTestId("retest-progress")).toHaveCount(0, { timeout: 200_000 });
  await expect(page.getByTestId("lab-subline")).toContainText("Retest finished");

  const row = (kind: string) => page.locator(`[data-testid="lab-row"][data-kind="${kind}"]`);
  const before = async (kind: string) => (await badge(row(kind).getByTestId("lab-cell-before")).innerText()).trim();
  const after = async (kind: string) => (await badge(row(kind).getByTestId("lab-cell-after")).innerText()).trim();
  // The answer key, entry by entry: T1 to T5 before, R1 to R5 after.
  expect(KEY.tests_on_1_4_2.map((e: any) => e.id)).toEqual(["T1", "T2", "T3", "T4", "T5"]);
  expect(KEY.tests_on_1_4_3.map((e: any) => e.id)).toEqual(["R1", "R2", "R3", "R4", "R5"]);
  for (const entry of KEY.tests_on_1_4_2) expect(await before(KEY_ROWS[entry.id]), `${entry.id} ${entry.test}`).toBe(entry.expected);
  for (const entry of KEY.tests_on_1_4_3) expect(await after(KEY_ROWS[entry.id]), `${entry.id} ${entry.test}`).toBe(entry.expected);
  // In words: the two signature tests now pass, speed shows no slowdown, the server tests are unchanged.
  expect([await before("official_vectors"), await after("official_vectors")]).toEqual(["Failed", "Passed"]);
  expect([await before("bad_signatures"), await after("bad_signatures")]).toEqual(["Failed", "Passed"]);
  expect([await before("speed_size"), await after("speed_size")]).toEqual(["Measured", "No slowdown beyond measured noise"]);
  expect([await before("tls_versions"), await after("tls_versions")]).toEqual(["Failed", "Failed"]);
  expect([await before("certificate"), await after("certificate")]).toEqual(["Passed", "Passed"]);
  const addOn = KEY.add_on[0];
  expect([addOn.expected, addOn.or_if_checker_too_old]).toContain(await before("pq_readiness"));
  expect(await after("pq_readiness")).toBe(await before("pq_readiness"));
  await expect(row("official_vectors").getByTestId("lab-cell-after")).toContainText("484 of 484 official cases right.");
  await expect(row("bad_signatures").getByTestId("lab-cell-after")).toContainText("Rejects r=0, s=0");
  await expect(row("tls_versions").getByTestId("lab-cell-after")).toContainText("Server still accepts TLS 1.2.");
  await expect(page.getByText("Couldn't trust this run")).toHaveCount(0);
  await expect(page.getByTestId("lab-row")).toHaveCount(6);

  // Which code each side ran on: the bundled 1.4.2 before, the merged fix after, with the merge commit Fixes showed.
  expect(mergeCommit).toMatch(/^[0-9a-f]{7}$/);
  await expect(page.getByTestId("lab-column-note")).toHaveText(["the bundled demo version", `the merged fix, commit ${mergeCommit}`]);
  await expect(page.getByTestId("lab-code-line")).toHaveText(
    `Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, the merged fix: branch main, commit ${mergeCommit} (pull request #1), the same byte for byte as our bundled acme-sign 1.4.3.`,
  );
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("12-lab-before-after-code-notes.png");
});

test("the opened row after the retest: the code each side ran on, the Code item, and the line Fix merged", async () => {
  const bad = await openLabRow("Bad signatures");
  const details = bad.getByTestId("result-detail");
  await expect(details).toHaveCount(2);
  const after = details.nth(0);
  const before = details.nth(1);
  await expect(after.getByRole("heading", { name: `After: acme-sign 1.4.3, the merged fix (commit ${mergeCommit})`, exact: true })).toBeVisible();
  await expect(badge(after).first()).toHaveText("Passed");
  // The case that failed before now passes: the signature r=0, s=0 is rejected.
  const zeroCase = (detail: Locator) => detail.getByRole("table").first().locator("tbody tr").filter({ hasText: /r\s?=\s?0.*s\s?=\s?0/ }).first();
  await expect(zeroCase(after)).toContainText("rejected");
  await expect(zeroCase(after)).not.toContainText("accepted");
  await expect(zeroCase(before)).toContainText("accepted (wrong)");
  await expect(after.getByTestId("control-outcome")).toHaveAttribute("data-outcome", "as_expected");
  // A result that did not fail has no line; its advice box is still there.
  await expect(after.getByTestId("fix-line")).toHaveCount(0);
  await expect(after.getByTestId("suggested-fix")).toContainText("None needed. Every bad signature was rejected.");
  expect(await codeItem(after)).toMatch(
    new RegExp(`^Code: the merged fix: branch main, commit ${mergeCommit} \\(pull request #1\\), the same byte for byte as our bundled acme-sign 1\\.4\\.3 demo$`),
  );

  await expect(before.getByRole("heading", { name: "Before: acme-sign 1.4.2, the bundled demo version", exact: true })).toBeVisible();
  await expect(badge(before).first()).toHaveText("Failed");
  await expectFixLine(before, `Fix merged: ${SIZE}, proof passed`, "plain");
  expect(await codeItem(before)).toBe("Code: the bundled demo version of acme-sign 1.4.2 demo");
  await shot("13-lab-bad-signatures-after-fix-merged.png");
  await closeLabRow("Bad signatures");

  // The server is unchanged, so its failure still points to the text-only fix, before and after.
  const tls = await openLabRow("Old TLS versions");
  const tlsDetails = tls.getByTestId("result-detail");
  await expect(tlsDetails).toHaveCount(2);
  await expectFixLine(tlsDetails.nth(0), TLS_LINE, "dashed");
  await expectFixLine(tlsDetails.nth(1), TLS_LINE, "dashed");
  await closeLabRow("Old TLS versions");

  // View in Fixes on the merged line opens the merged fix, which stays listed after the retest.
  const again = await openLabRow("Official test vectors");
  await expectFixLine(again.getByTestId("result-detail").nth(1), `Fix merged: ${SIZE}, proof passed`, "plain");
  await again.getByTestId("fix-line").getByRole("button", { name: "View in Fixes" }).click();
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);
  await expectStatus("merged", "Merged");
  await expect(fixList().getByRole("button")).toHaveCount(2);
  await expect(listed(TLS_FIX_TITLE).getByTestId("fix-status")).toHaveText("Text only");
  await expect(summary().getByRole("button")).toHaveText(["Retest now", "Download patch"]);
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await goTo("4. Evidence Lab");
});

test("Download evidence: the verify command passes, and the file holds the fix, the proof, the approvals and the merge", async () => {
  const got: Download[] = [];
  const collect = (d: Download) => got.push(d);
  page.on("download", collect);
  await page.getByRole("button", { name: "Download evidence" }).click();
  await expect.poll(() => got.length, { timeout: 30_000 }).toBe(2);
  page.off("download", collect);
  for (const d of got) {
    const name = d.suggestedFilename();
    const target = path.join(downloads, name);
    await d.saveAs(target);
    if (name.endsWith(".json")) evidenceJson = target;
    if (name.endsWith(".html")) evidenceHtml = target;
  }
  expect(path.basename(evidenceJson)).toMatch(/^evidence-lab-evidence-\d{8}-\d{6}\.json$/);
  expect(path.basename(evidenceHtml)).toMatch(/^evidence-lab-report-\d{8}-\d{6}\.html$/);
  const shown = (await page.getByTestId("evidence-fingerprint").innerText()).trim();

  const ok = verifyEvidence(evidenceJson);
  expect(ok.output).toContain("Evidence verified");
  expect(ok.output).toContain(shown);
  expect(ok.code).toBe(0);

  const envelope = JSON.parse(fs.readFileSync(evidenceJson, "utf8"));
  expect(envelope.fingerprint).toBe(shown);
  const evidence = envelope.evidence;
  expect(evidence.disclaimer).toBe(DISCLAIMER);
  expect(evidence.tests).toHaveLength(6);
  // The connected code.
  expect(evidence.code).toMatchObject({ repository: "acme-sign", branch: "main", is_demo: true, component: { name: "acme-sign", version: "1.4.2" } });
  expect(evidence.code.base_commit).toMatch(/^[0-9a-f]{40}$/);

  expect(evidence.fixes.map((f: any) => [f.id, f.kind, f.status])).toEqual([
    [CODE_FIX, "code", "Merged"],
    [TLS_FIX, "text", "Text only"],
  ]);
  const fix = evidence.fixes[0];
  expect(fix.title).toBe(CODE_FIX_TITLE);
  expect(fix.source.text).toBe("Came from 2 failed tests: Official test vectors, Bad signatures");
  expect(fix.proof_summary).toEqual({ state: "passed", label: "Proof passed", text: PROOF_PASSED });
  // The fix: the change, labelled, with exactly the patch that Download patch gave.
  expect(fix.change).toMatchObject({
    label: "From a fix template", written_by: "fix_template", template_id: "ecdsa-range-check", branch: "fix/ecdsa-range-check",
    size: SIZE, title: "Reject signatures whose r or s is out of range", built: { file: "acme_sign.py", matches: { name: "acme-sign", version: "1.4.3" } },
  });
  expect(fix.change.files).toHaveLength(1);
  expect(fix.change.files[0]).toMatchObject({ name: "acme_sign.py", added: 3, removed: 1 });
  expect(fix.change.patch).toBe(patchText);
  expect(fix.change.base_commit).toBe(evidence.code.base_commit);
  // The proof: its record, its fingerprint as Fixes showed it, the review, and a full run record for every test of the plan.
  expect(fix.proofs).toHaveLength(1);
  const proof = fix.proofs[0];
  expect(proof.record_sha256).toBe(proofFingerprint);
  expect(proof.review).toMatchObject({ offered: true, believed: true, problem: null, record_sha256: proofFingerprint });
  expect(Object.values(proof.review.checks).every((v) => v === true)).toBe(true);
  expect(proof.outcome).toBe("The proof passed.");
  expect([proof.baseline_version, proof.version]).toEqual(["1.4.2", "1.4.3"]);
  expect(proof.tests.map((t: any) => t.kind).sort()).toEqual(["bad_signatures", "certificate", "official_vectors", "pq_readiness", "speed_size", "tls_versions"]);
  for (const t of proof.tests) {
    expect(t.check.ok, t.kind).toBe(true);
    expect(t.run.phase, t.kind).toBe("proof");
    expect(t.run.run_sha256, t.kind).toMatch(/^[0-9a-f]{64}$/);
    // Each proof run of the signing program says which code it ran on: the change branch.
    if (t.target === "software") expect(t.run.code).toMatchObject({ source: "repository", branch: "fix/ecdsa-range-check", commit: fix.change.head_commit, component_version: "1.4.3" });
  }
  // The pull request, the approvals with name and time, and the merge.
  expect(fix.pull_request).toMatchObject({ number: 1, reviewers: ["you", "a"], title: "Reject signatures whose r or s is out of range", approvals_note: ONE_LOGIN });
  expect(fix.approvals.map((a: any) => [a.reviewer, a.name, a.label])).toEqual([["you", "You", null], ["a", "Demo reviewer A", "Demo data"]]);
  for (const a of fix.approvals) expect(a.approved_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  expect(fix.merge.merge_commit).toMatch(/^[0-9a-f]{40}$/);
  expect(fix.merge.merge_commit.startsWith(mergeCommit)).toBe(true);
  expect(fix.merge.merged_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  // The text-only fix is in the file with its suggestion and nothing else.
  expect(evidence.fixes[1]).toMatchObject({ change: null, proofs: [], pull_request: null, approvals: [], merge: null });
  expect(evidence.fixes[1].suggestion.warning.title).toBe("Before you switch TLS 1.2 off:");

  // Every run of the signing program says which code it ran on: bundled before, the merged fix after.
  for (const t of evidence.tests.filter((x: any) => ["official_vectors", "bad_signatures", "speed_size"].includes(x.kind))) {
    const first = t.runs.find((r: any) => r.phase === "first");
    const retest = t.runs.find((r: any) => r.phase === "retest");
    expect(first.code, t.kind).toMatchObject({ source: "bundled", component_version: "1.4.2" });
    expect(retest.code, t.kind).toMatchObject({ source: "repository", branch: "main", commit: fix.merge.merge_commit, pull_request_number: 1, component_version: "1.4.3" });
  }
});

test("changing one byte of the evidence file, inside the fix, the proof, an approval or the merge, makes the check fail", async () => {
  const original = fs.readFileSync(evidenceJson);
  const text = original.toString("latin1");
  const places = [
    text.indexOf('"Merged"') + 2, // the status of the fix
    text.indexOf(proofFingerprint) + 10, // the evidence fingerprint of the proof
    text.indexOf('"Demo reviewer A"') + 3, // an approval
    text.indexOf('"merge_commit":"') + 20, // the merge
    text.indexOf("fix/ecdsa-range-check") + 2, // the change
    text.indexOf('"signature":"') + 20,
  ];
  for (const [i, at] of places.entries()) {
    expect(at).toBeGreaterThan(20);
    const changed = Buffer.from(original);
    changed[at] = changed[at] ^ 0x01;
    expect(changed.equals(original)).toBe(false);
    const copy = path.join(downloads, `changed-${i}.json`);
    fs.writeFileSync(copy, changed);
    const result = verifyEvidence(copy);
    expect(result.code, `byte ${at} changed: ${result.output}`).not.toBe(0);
    expect(result.output).not.toContain("Evidence verified");
  }
  // The untouched file still passes.
  expect(verifyEvidence(evidenceJson).code).toBe(0);
});

test("the report shows the Fixes part: the change, the proof, the approvals, the merge and the text-only suggestion", async () => {
  const json = fs.readFileSync(evidenceJson, "utf8");
  const html = fs.readFileSync(evidenceHtml, "utf8");
  for (const body of [json, html]) {
    expect(body.includes("PRIVATE KEY")).toBe(false);
    expect(body.includes(password)).toBe(false);
  }
  const signingKey = fs.readFileSync(path.join(process.env.E2E_DATA_DIR ?? "", "evidence-signing-key.pem"), "utf8");
  const keyLines = signingKey.split("\n").filter((line) => line.length >= 20 && !line.startsWith("-----"));
  expect(keyLines.length).toBeGreaterThan(0);
  // True/false only, so a key can never end up in a test report.
  expect(keyLines.some((line) => json.includes(line) || html.includes(line))).toBe(false);
  expect(/<script/i.test(html)).toBe(false);

  const report = await context.newPage();
  try {
    await report.goto(`file://${evidenceHtml}`);
    const heading = report.getByRole("heading", { name: "4. Fixes", exact: true });
    await expect(heading).toBeVisible();
    const body = report.locator("body");
    await expect(body).toContainText("Code connected: the app's own copy of the repository acme-sign, branch main");
    await expect(report.getByRole("heading", { name: CODE_FIX_TITLE, exact: true })).toBeVisible();
    await expect(body).toContainText("Merged Came from 2 failed tests: Official test vectors, Bad signatures");
    await expect(body).toContainText(`Proof passed: ${PROOF_PASSED}`);
    await expect(body).toContainText("From a fix template");
    await expect(body).toContainText(`Reject signatures whose r or s is out of range. ${SIZE}.`);
    await expect(body).toContainText("is byte for byte the same as our bundled demo component acme-sign 1.4.3, and that component is what the proof ran.");
    // The change itself, as the patch (folded until it is opened).
    await expect(report.locator("details").filter({ hasText: "The change as a patch" })).toContainText("+    if not (1 <= r < N and 1 <= s < N):");
    await expect(body).toContainText("The proof passed.");
    await expect(body).toContainText(proofFingerprint);
    await expect(report.getByRole("heading", { name: "Pull request #1", exact: true })).toBeVisible();
    await expect(body).toContainText("Demo reviewer A (Demo data): approved");
    await expect(body).toContainText(ONE_LOGIN);
    await expect(body).toContainText(/Merged \S+ \(UTC\) by the person logged in, after confirming \(merge commit [0-9a-f]{40}\)\. Nothing was deployed\./);
    await expect(report.getByRole("heading", { name: TLS_FIX_TITLE, exact: true })).toBeVisible();
    await expect(body).toContainText("text only: the app has not applied it or tested it");
    await expect(body).toContainText("Before you switch TLS 1.2 off:");
    // Which code each run ran on is in the report too.
    await expect(body).toContainText("the merged fix: branch main, commit");
    await expect(report.getByText(DISCLAIMER).first()).toBeVisible();
    const text = (await body.innerText()).replaceAll(DISCLAIMER, "");
    expect(text).not.toMatch(/\bsecure\b|security score|time[- ]to[- ]hack/i);

    // In the tables of the Fixes part, the short columns (the test or place, and the rule check) keep their words
    // whole: a cell may wrap between words, never inside one ("Certificat e", "Passe d").
    const tables = await report.evaluate(() => {
      const start = [...document.querySelectorAll("h2")].find((h) => h.textContent === "4. Fixes");
      const broken: string[] = [];
      let cells = 0;
      for (let node = start?.nextElementSibling; node; node = node.nextElementSibling) {
        for (const table of node.querySelectorAll("table")) {
          for (const cell of table.querySelectorAll("tr > :first-child, tr > :nth-child(4)")) {
            cells += 1;
            const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
            for (let text = walker.nextNode(); text; text = walker.nextNode()) {
              // A word may still end a line at its own hyphen ("Post-" / "quantum").
              for (const word of (text.textContent ?? "").matchAll(/[^\s-]+-?/g)) {
                const range = document.createRange();
                range.setStart(text, word.index ?? 0);
                range.setEnd(text, (word.index ?? 0) + word[0].length);
                const lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
                if (lines.size > 1) broken.push(`${cell.textContent}: ${word[0]}`);
              }
            }
          }
        }
      }
      return { cells, broken };
    });
    // The proof table (a heading row and six tests, two short columns) and the table of places (a heading row and four places).
    expect(tables.cells).toBe(19);
    expect(tables.broken).toEqual([]);

    // The picture: the Fixes part of the report, from its heading to the last line of the page.
    // A whole-page capture sets fixed-width text a fraction differently from the window (the browser's capture
    // mode does that), and the page then stays that way. So one tiny capture is made first and thrown away, and
    // the heading is measured after it; otherwise the picture would start and end some 80 pixels too early.
    await report.screenshot({ fullPage: true, clip: { x: 0, y: 0, width: 8, height: 8 } });
    const place = () =>
      heading.evaluate((h) => ({
        top: h.getBoundingClientRect().top + window.scrollY,
        height: document.documentElement.scrollHeight,
        lastLine: (document.querySelector("main")?.lastElementChild?.textContent ?? "").trim(),
      }));
    const at = await place();
    expect(at.lastLine).toBe("End of report. The JSON file is the record. This page is a readable copy and is not signed.");
    const from = Math.max(0, Math.floor(at.top) - 24);
    await report.screenshot({
      path: path.join(SHOTS, "14-evidence-report-fixes-part.png"),
      fullPage: true,
      clip: { x: 0, y: from, width: 1440, height: at.height - from },
    });
    // Nothing moved while the picture was taken, so it shows exactly the part that was measured.
    expect(await place()).toEqual(at);
  } finally {
    await report.close();
  }
});

// ---- Two states the main flow never reaches, on a second fresh import so that the flow above is not disturbed.

test("a second import gets its own fresh copy of the code; with the address not confirmed the proof fails, and Fixes offers nothing", async () => {
  // The fix looked at last for the first file is the server fix. It must not stay picked for the next file.
  await goTo("5. Fixes");
  await selectFix(TLS_FIX_TITLE, TLS_FIX);
  await importVerifyAndOpenTests(page);
  const cards = page.getByTestId("test-card");
  await expect(cards).toHaveCount(5);
  await expect(cards.getByTestId("test-status")).toHaveText(Array(5).fill("Not run yet"));
  await expect(page.getByRole("button", { name: "5. Fixes" })).toBeDisabled();
  await runAllAndWait(5);

  // Untick "I own this system or am allowed to test it" on Import. The server tests then can't run during the proof.
  await goTo("1. Import");
  const tick = page.getByTestId("address-confirm");
  await expect(tick).toBeChecked();
  await tick.click();
  await expect(tick).not.toBeChecked();

  // A new file starts from its own first fix. And the first import's merge has not followed us here: this
  // file's own copy of the code is not connected yet.
  await goTo("5. Fixes");
  await expect(fixList().getByRole("button")).toHaveCount(2);
  await expect(summary()).toHaveAttribute("data-fix-id", CODE_FIX);
  await expect(listed(CODE_FIX_TITLE)).toHaveAttribute("aria-current", "true");
  const plan = await planId();
  await expectStatus("not_connected", "Code not connected");
  const s = summary();
  await expect(s.getByRole("button")).toHaveText(["Connect demo code"]);
  await s.getByRole("button", { name: "Connect demo code" }).click();
  await expectStatus("proving", "Proving");

  const watched = await watchProof();
  test.info().annotations.push({ type: "proof", description: `statuses seen: ${watched.statuses.join(" -> ")}` });
  expect(watched.statuses).toEqual(["proving", "failed"]);
  expect(watched.buttonsWhileProving).toEqual([]);
  await expectStatus("failed", "Proof failed");
  await expect(s.getByTestId("fix-proof")).toHaveAttribute("data-state", "failed");
  await expect(badge(s.getByTestId("fix-proof"))).toHaveText("Proof did not pass");
  await expect(s.getByTestId("fix-proof").locator("p")).toHaveText(
    "The 2 server tests did not come out the same as before: Old TLS versions, Couldn't run (address not confirmed); Certificate strength, Couldn't run (address not confirmed). The change is not offered.",
  );
  // It offers nothing: no reviewers to pick, no pull request, no approval, no merge, no patch. Only the proof can be run again.
  await expectUnproven();
  await expect(s.getByTestId("fix-approvers")).toHaveText("Nobody yet: a change that is not offered can't get a pull request.");
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(s.getByTestId("fix-pull-request")).toHaveCount(0);
  await expect(s.getByRole("button")).toHaveText(["Run proof again"]);
  await expect(s.getByRole("button", { name: "Run proof again" })).toBeEnabled();
  await expect(s.getByTestId("fix-actions")).toContainText("Reruns all 5 tests in your plan. The change is offered only if the proof passes.");
  await expectNothingOffered(plan);

  // The failed proof is shown: which tests did not come out the same, and why the change is not offered.
  await setSection("proof", true);
  const proof = section("proof");
  await expect(proof.getByTestId("fix-section-line")).toHaveText("Did not pass: the 2 server tests did not come out the same as before.");
  for (const kind of ["tls_versions", "certificate"]) {
    const row = proof.locator(`[data-testid="proof-row"][data-kind="${kind}"]`);
    await expect(badge(row.getByTestId("proof-cell-proof"))).toHaveText("Couldn't run (address not confirmed)");
    await expect(row.getByTestId("proof-check")).toHaveAttribute("data-ok", "false");
    await expect(row.getByTestId("proof-check").locator("span:last-child")).toHaveText("Not the same as before");
  }
  for (const kind of ["official_vectors", "bad_signatures", "speed_size"]) {
    await expect(proof.locator(`[data-testid="proof-row"][data-kind="${kind}"]`).getByTestId("proof-check")).toHaveAttribute("data-ok", "true");
  }
  const verdict = proof.getByTestId("proof-verdict");
  await expect(verdict).toHaveAttribute("data-tone", "fail");
  await expect(verdict.getByRole("heading").first()).toHaveText("Why this change is not offered");
  await expect(verdict.locator('[data-testid="proof-check"][data-ok="false"]')).toHaveCount(1);
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("16-fixes-proof-failed.png");
  await setSection("proof", false);

  // Evidence Lab says the fix is not offered, and never calls it ready.
  await goTo("4. Evidence Lab");
  const bad = await openLabRow("Bad signatures");
  await expectFixLine(bad.getByTestId("result-detail"), "Fix not offered: the proof did not pass", "fail");
});

test("with the address confirmed again, Run proof again reaches Ready for review, and Evidence Lab's line follows by itself", async () => {
  await goTo("1. Import");
  const tick = page.getByTestId("address-confirm");
  await expect(tick).not.toBeChecked();
  await tick.click();
  await expect(tick).toBeChecked();

  await goTo("5. Fixes");
  await selectFix(CODE_FIX_TITLE, CODE_FIX);
  await expectStatus("failed", "Proof failed");
  await summary().getByRole("button", { name: "Run proof again" }).click();
  await expectStatus("proving", "Proving");
  await expect(summary().getByRole("button")).toHaveCount(0);

  // Watch it from Evidence Lab this time: the line changes with nobody pressing anything.
  await goTo("4. Evidence Lab");
  const bad = await openLabRow("Bad signatures");
  const line = bad.getByTestId("fix-line");
  await expect(line.locator("p")).toHaveText(`Fix prepared: ${SIZE}, proof running`);
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeDisabled();
  await expect(page.getByTestId("blocked-reason")).toHaveText([PROOF_RUNNING_BLOCKS]);
  await expect(line.locator("p")).toHaveText(`Fix ready: ${SIZE}, proof passed`, { timeout: 200_000 });
  await expect(line).toHaveAttribute("data-look", "pass");
  await expect(page.getByRole("button", { name: "Retest new version" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Download evidence" })).toBeEnabled();
  await expect(page.getByTestId("blocked-reason")).toHaveCount(0);

  await line.getByRole("button", { name: "View in Fixes" }).click();
  await expectStatus("ready", "Ready for review");
  await expect(badge(summary().getByTestId("fix-proof"))).toHaveText("Proof passed");
  await expect(summary().getByTestId("fix-proof").locator("p")).toHaveText(
    "All 3 tests that run the changed code passed, every control behaved as expected, and the 2 server tests came out the same as before.",
  );
  await expect(summary().getByTestId("server-line")).toHaveText(SERVER_LINE_PROVEN);
  await expect(summary().getByRole("button")).toHaveText(["Open pull request"]);
});

test("a test added after the proof passed puts the proof out of date: Proof failed, with Run proof again", async () => {
  // Add a test in Tests. The proof no longer covers exactly the tests in the plan.
  await goTo("3. Tests");
  await page.getByRole("button", { name: "+ Add test" }).click();
  await page.getByRole("menu").getByRole("menuitem").filter({ hasText: "ML-DSA-65 comparison" }).click();
  await expect(page.getByTestId("test-card")).toHaveCount(6);

  await goTo("5. Fixes");
  await selectFix(CODE_FIX_TITLE, CODE_FIX);
  const plan = await planId();
  const s = summary();
  await expectStatus("failed", "Proof failed");
  await expect(s.getByTestId("fix-proof")).toHaveAttribute("data-state", "failed");
  await expect(badge(s.getByTestId("fix-proof"))).toHaveText("Proof out of date");
  await expect(s.getByTestId("fix-proof").locator("p")).toHaveText(
    "The test plan has changed since the proof ran, so the proof no longer covers exactly the tests in your plan. The change is not offered.",
  );
  await expectUnproven();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(s.getByTestId("fix-approvers")).toHaveText("Nobody yet: a change that is not offered can't get a pull request.");
  // Run proof again is there. It is switched off until the added test has a first result to compare with.
  await expect(s.getByRole("button")).toHaveText(["Run proof again"]);
  await expect(s.getByRole("button", { name: "Run proof again" })).toBeDisabled();
  await expect(s.getByTestId("fix-actions")).toContainText("Run every test in the plan first, so there is a result to compare with.");
  await expect(section("proof").getByTestId("fix-section-line")).toHaveText("Out of date: the test plan has changed since the proof ran.");
  await expectNothingOffered(plan);
  await setSection("proof", true);
  await expect(section("proof")).toContainText("then reran every locked test that was in your plan at the time");
  await expect(section("proof").getByTestId("proof-row")).toHaveCount(5);
  await expect(section("proof").getByTestId("proof-verdict")).toHaveAttribute("data-tone", "fail");
  await expect(section("proof").getByTestId("proof-verdict")).toContainText(
    "The test plan has changed since the proof ran, so the proof no longer covers exactly the tests in your plan.",
  );
  await expectNoSoftwareUpload();
  await expectCarefulWording();
  await shot("15-fixes-proof-out-of-date.png");
  await setSection("proof", false);

  await goTo("4. Evidence Lab");
  const bad = await openLabRow("Bad signatures");
  await expectFixLine(bad.getByTestId("result-detail"), "Fix not offered: the test plan changed after the proof", "fail");

  // Run the added test; then Run proof again is switched on, and the new proof covers all six tests.
  await goTo("3. Tests");
  // This card's heading carries a small tag after the title ("reference, not production").
  const addedCard = card(/^ML-DSA-65 comparison/);
  await expect(addedCard).toHaveCount(1);
  await expect(addedCard.getByRole("heading")).toContainText("reference, not production");
  await addedCard.getByRole("button", { name: "Run ML-DSA-65 comparison" }).click();
  await expect(badge(addedCard)).toHaveText("Measured", { timeout: 120_000 });
  await goTo("5. Fixes");
  await selectFix(CODE_FIX_TITLE, CODE_FIX);
  await expectStatus("failed", "Proof failed");
  await expect(s.getByRole("button", { name: "Run proof again" })).toBeEnabled();
  await expect(s.getByTestId("fix-actions")).toContainText("Reruns all 6 tests in your plan. The change is offered only if the proof passes.");
  await s.getByRole("button", { name: "Run proof again" }).click();
  await expectStatus("proving", "Proving");
  const watched = await watchProof();
  expect(watched.statuses).toEqual(["proving", "ready"]);
  await expectStatus("ready", "Ready for review");
  // The added test only reports numbers: it has to run, and it is not counted among the tests that passed.
  await expect(s.getByTestId("fix-proof").locator("p")).toHaveText(
    "All 3 tests that run the changed code passed, the 1 report-only test ran, every control behaved as expected, and the 2 server tests came out the same as before.",
  );
  await setSection("proof", true);
  await expect(section("proof").getByTestId("proof-row")).toHaveCount(6);
  const added = section("proof").locator('[data-testid="proof-row"][data-kind="mldsa_compare"]');
  await expect(badge(added.getByTestId("proof-cell-proof"))).toHaveText("Measured");
  await expect(added.getByTestId("proof-check").locator("span:last-child")).toHaveText("Ran (reports only)");
  await expect(section("proof").getByTestId("proof-verdict")).toContainText("The 1 report-only test ran.");
  await expectNoSoftwareUpload();
  await expectCarefulWording();
});
