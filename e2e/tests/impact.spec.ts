// Change impact (phase 4e, first half): "What breaks if I make this change?", on a copy of the app of its own (own data
// folder and ports: app 8036, demo server 8469; the migration demo's test servers on 8451 to 8455), in demo mode,
// with the demo projects loaded. Main-screen buttons only.
//
//   Flow 1, a fix: on Acme Pay, after Run all and with the demo dependency list in (acme-pay-server tied to the demo
//   server), each fix in Fixes says what it touches: the acme-sign fix reaches acme-sign here and in the two other
//   demo projects that name it ("Re-check these 3"), with "Not known" for whether the parts that use it take the new
//   version and no client check; the OpenSSL update traces through python 3.12.3 to the server. A library on
//   Dependencies says where it is used, with the other assessment that names it. A link opens the other assessment.
//
//   Flow 2, a change on the wire: the Acme Pay server's TLS fix (TLS 1.3 only) is tried on a test copy from Fixes, and
//   "Who can still connect" shows the old firmware breaking; on the migration demo, Hybrid on 8452 breaks none (two fall
//   back), and Full post-quantum on 8451 breaks three. A Breaks holds nothing off: approval is asked and given, and
//   Apply is on. The stand-ins' run is on Checks and in the signed evidence, which the verify command confirms.
//
// Every table page is measured at 1440 pixels wide with the panel open. Pictures, dark and light: docs/screenshots/impact/.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  BACKEND,
  PYTHON,
  REPO,
  enterApp,
  layoutProblems,
  openGroupTab,
  screenshotFolder,
  startCopy,
  stepLink,
  stopCopy,
  type Copy,
} from "./shared";

const SHOTS = screenshotFolder("impact");
const LIST = path.join(REPO, "demo/dependencies-demo.cdx.json");
const BANNED = [/\bsecure\b/i, /\bscore\b/i, /\bseverity\b/i];

let copy: Copy | null = null;
let page: Page;

const detail = (): Locator => page.getByTestId("detail-panel");
const impact = (): Locator => detail().getByTestId("impact");
const box = (): Locator =>
  detail().getByTestId("change-box").or(page.getByTestId("migration-system").getByTestId("change-box")).first();
const clients = (): Locator => box().getByTestId("change-clients");

/** One picture of the window in the dark look and one in the light look, with the top of `focus` just under the
 * panel's own header. The pictures are taken in a window 1800 pixels high (1440 wide, as every walk), so a whole block
 * fits; every layout check of this walk is made in the usual 900-pixel-high window. */
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
        // then back down by what is needed to see its top under the top bar and the panel's header: whichever of its
        // ancestors (or the page) scrolled gives the room back
        let short = 260 - el.getBoundingClientRect().top;
        for (let box: Element | null = el.parentElement; box && short > 0; box = box.parentElement) {
          const back = Math.min(short, box.scrollTop);
          if (back > 0) {
            box.scrollTop -= back;
            short -= back;
          }
        }
        if (short > 0) window.scrollBy(0, -short);
      });
    }
    await page.screenshot({ path: path.join(SHOTS, `${name}-${theme}.png`), fullPage: false, animations: "disabled" });
  }
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await page.setViewportSize({ width: 1440, height: 900 });
}

function projectRow(name: string): Locator {
  return page.getByTestId("project-row").filter({ has: page.locator("p").getByText(name, { exact: true }) });
}

async function openProject(name: string): Promise<void> {
  await page.goto("/#/projects");
  await projectRow(name).click();
  await expect(page.getByTestId("project-overview")).toBeVisible();
  await page.getByTestId("assessment-row").first().click();
  await expect(page.getByTestId("overview-page")).toBeVisible();
}

async function pickFix(title: string): Promise<void> {
  await page
    .getByRole("navigation", { name: /^Open findings with a fix/ })
    .getByRole("button")
    .filter({ hasText: title })
    .click();
  await expect(detail().getByRole("heading", { name: title, level: 2 })).toBeVisible();
}

async function openSystem(name: string): Promise<void> {
  await page.getByRole("button", { name: /^Systems/ }).click();
  await page.getByTestId("system-card").filter({ hasText: name }).click();
  await expect(page.getByTestId("migration-system").getByRole("heading", { name, level: 2 })).toBeVisible();
}

async function tryOnACopy(): Promise<void> {
  await box().getByRole("button", { name: "Try on a test copy" }).click();
  await expect(box().getByTestId("change-verdict")).toContainText("Try passed.", { timeout: 120_000 });
  await expect(clients().getByTestId("clients-summary")).toBeVisible({ timeout: 60_000 });
  await expect(box()).toHaveAttribute("data-busy", "false", { timeout: 60_000 }); // the try's job has ended
}

async function words(): Promise<Record<string, string>> {
  const rows = clients().getByTestId("clients-row");
  const out: Record<string, string> = {};
  for (const row of await rows.all())
    out[(await row.getAttribute("data-client")) ?? ""] = (await row.getByTestId("clients-word").innerText()).trim();
  return out;
}

async function noBannedWords(where: Locator): Promise<void> {
  const text = await where.innerText();
  for (const word of BANNED) expect(text, `"${word}" must not be said`).not.toMatch(word);
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  copy = await startCopy(browser, 26, "demo");
  page = copy.page;
  await enterApp(page);
});

test.afterAll(async () => {
  await stopCopy(copy);
});

test("setup: Load demo projects; Acme Pay verified, Run all, the demo dependency list with acme-pay-server tied to the demo server", async () => {
  await page.goto("/#/settings");
  await page.getByRole("button", { name: "Load demo projects" }).click();
  await expect(page.getByRole("status").filter({ hasText: /demo projects/ })).toBeVisible({ timeout: 60_000 });
  await openProject("Acme Pay");
  await stepLink(page, "Import").click();
  await page.getByTestId("address-confirm").click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText(["False", "True", "True"]);
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await page.getByRole("button", { name: "Run all" }).click();
  await expect(page.getByTestId("test-card").getByTestId("result-badge")).toHaveCount(5, { timeout: 180_000 });
  await stepLink(page, "6. Migration").click();
  await page.getByRole("button", { name: "Dependencies", exact: true }).click();
  const added = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/dependencies\?/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByLabel("Choose a dependency list").setInputFiles(LIST);
  expect((await added).status()).toBe(200);
  await page.getByLabel("Part of: acme-pay-server 1.0.0").selectOption({ label: `Server: ${copy!.server}` });
  await expect(page.getByTestId("tie-words").nth(1)).toHaveText(`Part of ${copy!.server}, set by you.`);
});

test("flow 1: the acme-sign fix says every system it touches, and that whether its users take 1.4.3 is not known", async () => {
  await stepLink(page, "5. Fixes").click();
  await openGroupTab(page, "Crypto tests", "Fixes");
  await pickFix("acme-sign accepts out-of-range signatures");
  await expect(impact().getByRole("heading", { name: "What this change touches" })).toBeVisible();
  await expect(impact().getByTestId("impact-count")).toHaveText("Re-check these 3 after the change.");
  const here = impact().getByTestId("impact-here").getByTestId("impact-line");
  await expect(here.first()).toContainText("acme-sign 1.4.2");
  await expect(here.first()).toContainText("A signing program in your scanner file.");
  await expect(impact().getByTestId("impact-here")).toContainText(
    "The thing your dependency list describes. Uses it directly.",
  );
  const elsewhere = impact().getByTestId("impact-elsewhere").getByTestId("impact-line");
  await expect(elsewhere).toHaveCount(2);
  await expect(elsewhere.filter({ hasText: "Migration demo › Assessment 1" })).toContainText(
    "Names acme-sign 1.4.2 as a signing program (the same name and version).",
  );
  await expect(elsewhere.filter({ hasText: "Multi-target › Assessment 1" })).toContainText("Open");
  await expect(impact().getByTestId("impact-compatible")).toHaveText(
    "Not known. Your dependency list names the exact version installed, not the versions each part that uses it accepts.",
  );
  await expect(impact().getByTestId("impact-connect")).toContainText(
    "No client check: this fix changes a signing program",
  );
  await expect(impact().getByRole("button")).toHaveCount(0);
  await noBannedWords(impact());
  await shots("01-fix-what-it-touches", impact());
  expect(await layoutProblems(page)).toEqual([]);
  // a place elsewhere opens that assessment, on its system; Back returns
  await elsewhere.filter({ hasText: "Multi-target › Assessment 1" }).getByTestId("impact-link").click();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Multi-target");
  await expect(
    page.getByTestId("migration-system").getByRole("heading", { name: "acme-sign 1.4.2", level: 2 }),
  ).toBeVisible();
  await page.goBack();
  await expect(impact().getByTestId("impact-count")).toHaveText("Re-check these 3 after the change.");
});

test("flow 1: the OpenSSL update traces to the server; a library on Dependencies says where it is used", async () => {
  await openGroupTab(page, "Dependencies", "Fixes");
  await pickFix("Update OpenSSL to 3.5.0 or later");
  await expect(impact().getByTestId("impact-count")).toHaveText("Re-check this one after the change.");
  await expect(impact().getByTestId("impact-here")).toContainText(
    `Your own software, from your dependency list. Uses it, through python 3.12.3. Part of ${copy!.server} (set by you).`,
  );
  await expect(impact().getByTestId("impact-compatible")).toContainText("Not known.");
  await expect(impact().getByTestId("impact-connect")).toContainText("This updates a TLS library");
  await shots("02-fix-openssl-update", impact());

  await stepLink(page, "6. Migration").click();
  await page.getByRole("button", { name: "Dependencies", exact: true }).click();
  await page
    .getByTestId("dependency-row")
    .filter({ has: page.locator("p.font-mono", { hasText: /^elliptic 6\.5\.6$/ }) })
    .locator("p.font-mono")
    .click();
  await expect(impact().getByRole("heading", { name: "Where it is used" })).toBeVisible();
  await expect(impact().getByTestId("impact-here")).toContainText("acme-ledger 5.1.0");
  await expect(impact().getByTestId("impact-here")).toContainText(
    "Not tied to a system of your file: choose one with Part of on Dependencies.",
  );
  await expect(impact().getByTestId("impact-elsewhere")).toContainText("Real libraries (isolated mode) › Assessment 1");
  await expect(impact().getByTestId("impact-elsewhere")).toContainText(
    "the knowledge base recognises it as elliptic, at the same version",
  );
  await expect(impact().getByTestId("impact-count")).toHaveText("Re-check this one if you change it.");
  await noBannedWords(impact());
  await shots("03-library-where-it-is-used", impact());
  expect(await layoutProblems(page)).toEqual([]);
});

test("flow 2: the Acme Pay server's TLS fix, tried on a test copy: the old firmware breaks, and Apply is not held off", async () => {
  await stepLink(page, "5. Fixes").click();
  await openGroupTab(page, "Crypto tests", "Fixes");
  await pickFix("Server accepts TLS 1.2");
  await expect(impact().getByTestId("impact-count")).toHaveText("Re-check these 2 after the change.");
  await expect(impact().getByTestId("impact-note").first()).toHaveText(
    "Apply changes this one server for every assessment that names it.",
  );
  await expect(impact().getByTestId("impact-connect")).toContainText("also connects four demo client stand-ins");
  await tryOnACopy();
  expect(await words()).toEqual({
    "old-terminal": "Breaks",
    "partner-classical": "Connects",
    "new-terminal": "Connects",
    "pq-only": "Didn't connect before either",
  });
  await expect(clients().getByTestId("clients-summary")).toHaveText(
    "1 breaks, 2 connect, 1 didn't connect before either.",
  );
  await expect(clients().getByTestId("clients-warning")).toHaveText(
    "Sort out the 1 that breaks before you apply this change.",
  );
  await expect(clients().getByTestId("clients-row").first()).toContainText("Refused (protocol version)");
  await expect(clients().getByRole("button")).toHaveCount(0);
  await noBannedWords(clients());
  await shots("04-tls-fix-who-can-still-connect", clients());
  expect(await layoutProblems(page)).toEqual([]);
  // the warning holds nothing off: approval is asked and given, then Apply is on (not pressed here)
  await box().getByRole("button", { name: "Ask for approval" }).click();
  await box().getByRole("button", { name: "Approve for You" }).click();
  await expect(box().getByRole("button", { name: `Apply to ${copy!.server}` })).toBeEnabled();
});

test("flow 2: on the migration demo, Hybrid on 8452 breaks none; Full post-quantum on 8451 breaks three", async () => {
  await openProject("Migration demo");
  await stepLink(page, "Import").click();
  const ticks = page.getByTestId("address-confirm");
  await expect(ticks).toHaveCount(5);
  for (let i = 0; i < 5; i += 1) await ticks.nth(i).click();
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
  await stepLink(page, "6. Migration").click();
  await page.getByRole("button", { name: "Measure status" }).click();
  await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 120_000 });

  await openSystem("localhost:8452");
  await tryOnACopy();
  expect(await words()).toEqual({
    "old-terminal": "Falls back",
    "partner-classical": "Falls back",
    "new-terminal": "Connects",
    "pq-only": "Didn't connect before either",
  });
  await expect(clients().getByTestId("clients-summary")).toHaveText(
    "None break. 1 connects with hybrid or post-quantum key exchange; 2 fall back to classical key exchange; 1 didn't connect before either.",
  );
  await expect(clients().getByTestId("clients-warning")).toHaveCount(0);
  await shots("05-hybrid-8452-none-break", clients());
  expect(await layoutProblems(page)).toEqual([]);

  await openSystem("localhost:8451");
  const full = page
    .getByTestId("option-card")
    .filter({ has: page.getByRole("heading", { name: "Full post-quantum", exact: true }) });
  await full.getByRole("button", { name: "Choose this option" }).click();
  await full
    .getByTestId("choose-box")
    .getByLabel(/Your reason/)
    .fill("To see which clients break before turning it on.");
  await full.getByTestId("choose-box").getByRole("button", { name: "Save choice" }).click();
  await expect(page.getByTestId("migration-choice")).toContainText("Full post-quantum");
  await tryOnACopy();
  expect(await words()).toEqual({
    "old-terminal": "Breaks",
    "partner-classical": "Breaks",
    "new-terminal": "Breaks",
    "pq-only": "Connects",
  });
  await expect(clients().getByTestId("clients-summary")).toHaveText(
    "3 break, 1 connects with hybrid or post-quantum key exchange.",
  );
  await expect(clients().getByTestId("clients-warning")).toHaveText(
    "Sort out the 3 that break before you apply this change.",
  );
  await expect(clients().locator('[data-client="pq-only"]')).toContainText("New: it can't connect today.");
  await shots("06-full-pq-8451-three-break", clients());
});

test("the stand-ins' run is on Checks and Evidence, and in the signed evidence file the verify command confirms", async () => {
  await stepLink(page, "Checks").click();
  await openGroupTab(page, "Migration", "Checks");
  const row = page.getByTestId("page-content").getByText("Who can still connect: localhost:8452", { exact: true });
  await expect(row).toBeVisible();
  await row.click();
  await expect(detail()).toContainText("Try on a test copy");
  await shots("07-checks-who-can-still-connect", detail());
  expect(await layoutProblems(page)).toEqual([]);
  // the evidence: the try of each change carries its stand-ins' words and run
  await stepLink(page, "Roadmap").click();
  const created = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const raw = await (await page.request.get(info.json.url)).body();
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-impact-")), "evidence.json");
  fs.writeFileSync(file, raw);
  const changes = JSON.parse(raw.toString("utf-8")).evidence.changes as {
    change: { system_key: string };
    rounds: { tries: { clients?: { stand_ins: { id: string; word: string }[] } }[] };
  }[];
  const full = changes.find((c) => c.change.system_key === "server:localhost:8451")!;
  expect(full.rounds.tries.at(-1)!.clients!.stand_ins.filter((s) => s.word === "breaks")).toHaveLength(3);
  const report = await (await page.request.get(info.html.url)).text();
  expect(report).toContain("Who can still connect: ");
  const run = spawnSync(PYTHON, ["-m", "evidence", "verify", file, "--data-dir", copy!.dataDir], {
    cwd: BACKEND,
    encoding: "utf-8",
  });
  expect(run.status, `the evidence file should check: ${run.stdout} ${run.stderr}`).toBe(0);
});
