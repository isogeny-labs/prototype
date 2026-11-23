// Phase 4a end to end: the migration plan, on demo/migration-demo.csv (five local test servers on 8451-8455,
// acme-sign 1.4.2 and acme-sign 9.9). Demo mode: no Docker and no internet, every server is on this computer.
// Main-screen buttons only. Screenshots go to docs/screenshots/phase4a/.
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DISCLAIMER, enterApp, REPO, stepLink, openFreshAssessment, expectPageOpen } from "./shared";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(REPO, "docs/screenshots/phase4a");
fs.mkdirSync(SHOTS, { recursive: true });
const FILE = path.resolve(here, "../../demo/migration-demo.csv");
const SERVERS = ["localhost:8451", "localhost:8452", "localhost:8453", "localhost:8454", "localhost:8455"];

let context: BrowserContext;
let page: Page;

async function shot(name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: true, animations: "disabled" });
}

function card(name: string): Locator {
  return page.getByTestId("system-card").filter({ hasText: name });
}

function option(title: string): Locator {
  return page.getByTestId("option-card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

function band(title: string): Locator {
  return page.getByTestId("roadmap-band").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
}

// The cost table (its first column heading says "(today)"); the change box has tables of its own since phase 4b.
// One track of the open system: "kex", "auth" or "signatures".
function track(detail: Locator, key: "kex" | "auth" | "signatures"): Locator {
  return detail.locator(`[data-testid="migration-track"][data-track="${key}"]`);
}

function costTable(detail: Locator): Locator {
  return detail.getByRole("table").filter({ has: page.getByRole("columnheader", { name: /\(today\)/ }) });
}

function bandRow(title: string, system: string): Locator {
  return band(title).getByTestId("roadmap-row").filter({ hasText: system });
}

// A band holds exactly these rows, each with the track it is about (in any order).
async function expectBand(title: string, rows: [string, string][]): Promise<void> {
  await expect(band(title).getByTestId("roadmap-row")).toHaveCount(rows.length);
  for (const [system, trackName] of rows) {
    const row = trackName
      ? bandRow(title, system).filter({ has: page.getByTestId("roadmap-track").getByText(trackName, { exact: true }) })
      : bandRow(title, system); // a system that wasn't measured has no track to name
    await expect(row).toHaveCount(1);
  }
}

async function open(name: string): Promise<Locator> {
  await card(name).click();
  const detail = page.getByTestId("migration-system");
  await expect(detail.getByRole("heading", { name, level: 2 })).toBeVisible();
  return detail;
}

test.describe.configure({ mode: "serial", timeout: 300_000 });

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext();
  page = await context.newPage();
  await enterApp(page);
  await openFreshAssessment(page, "Migration walk");
});

test.afterAll(async () => {
  await context.close();
});

test("Import: the file's claims, its five test servers start, and its system settings are listed", async () => {
  await stepLink(page, "1. Import").click();
  const uploaded = page.waitForResponse((r) => r.url().includes("/api/import/file") && r.request().method() === "POST");
  await page.getByLabel("Choose a file to import").setInputFiles(FILE);
  expect((await uploaded).status()).toBe(200);
  await expect(page.getByTestId("claim-row")).toHaveCount(7);
  await expect(page.getByTestId("import-notice")).toHaveText([
    "Demo data: started the five demo test servers for this file on this computer (ports 8451, 8452, 8453, 8454, 8455).",
  ]);
  const settings = page.getByTestId("import-setting");
  await expect(settings).toHaveCount(6);
  await expect(settings.filter({ hasText: "localhost:8454" })).toContainText(
    "Exposure: internal. Data lifespan: long-lived. Can it be changed: no.",
  );
  await expect(stepLink(page, "6. Migration")).toBeEnabled();
  await expectPageOpen(page, "5. Fixes");
  const ticks = page.getByTestId("address-confirm");
  await expect(ticks).toHaveCount(5);
  for (let i = 0; i < 5; i += 1) await ticks.nth(i).click();
  await shot("01-import-migration-file.png");
  await page.getByRole("button", { name: "Verify claims" }).click();
  await expect(page.getByRole("heading", { name: "Verify", level: 1 })).toBeVisible();
});

test("Verify: the post-quantum claims are checked, and the planted false one is found", async () => {
  await expect(page.getByTestId("result-row").getByTestId("result-badge")).toHaveText([
    "True",
    "False",
    "True",
    "True",
    "True",
    "True",
    "Couldn't check",
  ]);
  const wrong = page.getByTestId("result-row").filter({ hasText: "localhost:8452" });
  await expect(wrong.getByTestId("verify-summary")).toHaveText(
    "It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical. The file says Hybrid, so the claim is not true.",
  );
  await expect(
    page.getByTestId("result-row").filter({ hasText: "localhost:8455" }).getByTestId("verify-summary"),
  ).toContainText("so it is Post-quantum only");
  await shot("02-verify-post-quantum-claims.png");
});

test("Tests: a program that can't run has no cards, only its line under Not tested", async () => {
  await page.getByRole("button", { name: "Continue to checks" }).click();
  await expect(page.getByRole("heading", { name: "Checks", level: 1 })).toBeVisible();
  // Phase 4b: eight suggested tests: Post-quantum readiness for each of the five servers, and the three signing tests.
  await expect(page.getByTestId("test-card")).toHaveCount(8);
  await expect(page.getByTestId("test-card").filter({ hasText: "Post-quantum readiness" })).toHaveCount(5);
  await expect(page.getByText("Puts acme-sign through an outside exam", { exact: false })).toBeVisible();
  await expect(page.getByText("Signing program: acme-sign 9.9", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("not-tested")).toContainText(
    "acme-sign 9.9: its tests can't run. Only our own demo components can run in this version.",
  );
  await shot("03-tests-no-cards-for-a-program-that-cannot-run.png");
});

test("Migration: nothing is measured until the button is pressed", async () => {
  await stepLink(page, "6. Migration").click();
  await expect(page.getByRole("heading", { name: "Migration plan", level: 1 })).toBeVisible();
  await expect(page.getByTestId("disclaimer")).toHaveText(DISCLAIMER);
  await expect(page.getByTestId("system-card")).toHaveCount(7);
  await expect(page.getByTestId("system-card").getByTestId("migration-status")).toContainText(
    Array(7).fill("Not measured yet"),
  );
  await expect(page.getByRole("button", { name: "Measure status" })).toBeEnabled();
  await expect(page.getByTestId("migration-options")).toHaveCount(0);
  await shot("04-migration-before-measuring.png");
});

test("Measure status: each system gets its measured status and its plan", async () => {
  await page.getByRole("button", { name: "Measure status" }).click();
  await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 120_000 });
  // Phase 4b: a server shows two tracks (key exchange, authentication), a signing program one.
  await expect(page.getByTestId("system-card").getByTestId("migration-status")).toContainText([
    "Hybrid (interim)",
    "Classical",
    "Classical",
    "Classical",
    "Classical",
    "Classical",
    "Classical",
    "Classical",
    "Post-quantum only",
    "Post-quantum",
    "Classical",
    "Couldn't check",
  ]);
  await expect(card("localhost:8451")).toContainText("Next: authentication · Phase 2");
  await expect(card("localhost:8452")).toContainText("Next: hybrid key exchange · Phase 1");
  await expect(card("localhost:8453")).toContainText("Kept classical · review");
  await expect(card("localhost:8454")).toContainText("Next: wrap the connection");
  await expect(card("localhost:8455")).toContainText("At the target · keep measuring");
  await expect(card("acme-sign 1.4.2")).toContainText("Next: sign with both · Phase 2");
  await expect(card("acme-sign 9.9")).toContainText("No plan yet: couldn't check");
  await expect(page.getByText(/already there/i)).toHaveCount(0);
  await expect(stepLink(page, "5. Fixes")).toBeEnabled(); // without a page refresh
});

test("A classical server: today, measured; the cost with every number's source; the recommendation and its reasons", async () => {
  const detail = await open("localhost:8452");
  // Phase 4b: two tracks, each with its status, its facts, its Next step and its Why.
  const kex = track(detail, "kex");
  await expect(kex.getByTestId("track-sentence")).toHaveText(
    "It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical.",
  );
  await expect(kex).toContainText("Refused: X25519MLKEM768 and two others");
  await expect(detail.getByTestId("file-note")).toHaveText(
    "The file says: this server is Hybrid. Verify marked that claim False.",
  );
  await expect(detail.getByTestId("today-facts")).toContainText("1.3 and 1.2");
  await expect(detail.getByTestId("today-control")).toContainText("as expected");
  const sources = detail.getByTestId("setting-source");
  await expect(sources).toHaveText(["from the file", "from the file", "assumed"]);
  const cost = costTable(detail);
  await expect(cost).toContainText("Classical (today)");
  await expect(cost.getByRole("row").filter({ hasText: "Key share, client to server" })).toContainText("32 bytes");
  await expect(cost.getByRole("row").filter({ hasText: "Key share, client to server" })).toContainText(
    "published: FIPS 203 + X25519",
  );
  await expect(cost.getByRole("row").filter({ hasText: "First handshake message" })).toContainText(
    "measured on our test server",
  );
  await expect(detail.getByRole("heading", { name: "Recommended: Hybrid", exact: true })).toBeVisible();
  await expect(detail.getByText("from fixed rules, no AI model")).toBeVisible();
  const reasons = detail.getByTestId("recommendation-reason");
  await expect(reasons).toHaveCount(4);
  await expect(reasons.nth(0)).toContainText("Long-lived data");
  await expect(reasons.nth(3)).toContainText("deprecated after 2030 and disallowed after 2035");
  await shot("05-migration-classical-server-today-and-cost.png");
  // the evidence behind the status is one press away
  await detail.getByRole("button", { name: "See the evidence" }).click();
  await expect(detail.getByTestId("result-detail")).toContainText("Test details, locked before the run");
  await detail.getByRole("button", { name: "Details and evidence" }).click();
});

test("The four options: hybrid is the change itself, with no blocker; every option says cost, blockers and what to manage", async () => {
  const detail = page.getByTestId("migration-system");
  await expect(detail.getByTestId("option-card")).toHaveCount(4);
  await expect(detail.getByTestId("option-card").getByRole("heading", { level: 4 })).toHaveText([
    "Keep classical for now",
    "Hybrid",
    "Full post-quantum",
    "Wrap the connection",
  ]);
  const hybrid = option("Hybrid");
  await expect(hybrid).toContainText("Recommended");
  await expect(hybrid.getByTestId("option-section").filter({ hasText: "Blockers" })).toContainText("None measured.");
  await expect(hybrid.getByTestId("option-section").filter({ hasText: "To do" })).toContainText(
    "Turn on hybrid key exchange. This is the change itself, not a blocker.",
  );
  await expect(hybrid.getByTestId("option-section").filter({ hasText: "To manage" })).toContainText("Algorithms 3");
  await expect(option("Keep classical for now")).toContainText("never “forever”");
  await expect(option("Full post-quantum").getByTestId("option-section").filter({ hasText: "To do" })).toContainText(
    "Check that every client supports it. This app can't see your clients",
  );
  await expect(option("Full post-quantum").getByTestId("option-section").filter({ hasText: "Blockers" })).toContainText(
    "None measured.",
  );
  await expect(option("Wrap the connection")).toContainText("It protects the connection only");
  await hybrid.scrollIntoViewIfNeeded();
  await shot("06-migration-four-options.png");
});

test("The other statuses: Hybrid and Post-quantum only in place, a signing program, and Couldn't check", async () => {
  let detail = await open("localhost:8451");
  await expect(track(detail, "kex").getByTestId("track-sentence")).toContainText(
    "so it is Hybrid. A classical-only client still connects.",
  );
  await expect(detail.getByRole("heading", { name: "Recommended: Hybrid (in place today)" })).toBeVisible();
  await expect(costTable(detail)).toContainText("Hybrid (today)");
  await expect(option("Hybrid")).toContainText("In place today");
  await expect(option("Keep classical for now").getByTestId("not-offered")).toHaveText(
    "Doesn't apply: this server is already Hybrid.",
  );
  await shot("07-migration-hybrid-server.png");

  detail = await open("localhost:8454");
  await expect(track(detail, "kex").getByTestId("track-sentence")).toContainText(
    "It doesn't accept TLS 1.3, which post-quantum key exchange needs.",
  );
  await expect(detail.getByRole("heading", { name: "Recommended: Wrap the connection" })).toBeVisible();
  await expect(option("Hybrid").getByTestId("option-section").filter({ hasText: "Blockers" })).toContainText(
    "It doesn't accept TLS 1.3",
  );

  detail = await open("localhost:8455");
  await expect(track(detail, "kex").getByTestId("track-sentence")).toContainText(
    "so it is Post-quantum only. A classical-only client can't connect.",
  );
  await expect(track(detail, "auth")).toContainText("ML-DSA-65");
  await shot("08-migration-post-quantum-only-server.png");

  detail = await open("acme-sign 1.4.2");
  await expect(track(detail, "signatures").getByTestId("track-sentence")).toContainText(
    "ECDSA P-256 is a classical algorithm, so it is Classical.",
  );
  await expect(detail.getByRole("heading", { name: "Recommended: Hybrid: sign with both" })).toBeVisible();
  await expect(
    option("Hybrid: sign with both").getByTestId("option-section").filter({ hasText: "Blockers" }),
  ).toContainText("it can't make post-quantum signatures");
  await expect(option("Wrap the connection").getByTestId("not-offered")).toContainText(
    "wrapping protects a connection, not signatures",
  );
  await shot("09-migration-signing-program.png");

  detail = await open("acme-sign 9.9");
  const unknown = track(detail, "signatures");
  await expect(unknown.getByTestId("migration-status")).toHaveText(/Couldn't check/);
  await expect(unknown.getByTestId("track-next")).toContainText("nothing until it can be measured.");
  await expect(unknown.getByTestId("track-why")).toContainText("nothing is planned from a guess.");
  await expect(detail.getByTestId("recommendation-none")).toContainText("Nothing is recommended from a guess.");
  await expect(detail.getByTestId("migration-options")).toHaveCount(0);
  await shot("10-migration-could-not-check.png");
});

test("The roadmap: built from the recommendations, each system in its phase", async () => {
  await page.getByRole("button", { name: "Roadmap", exact: true }).click();
  // Phase 5b: with a system's panel open the plan shows its compact form; this step reads the full rows.
  const open = page.getByTestId("detail-panel");
  if ((await open.count()) > 0) await open.getByRole("button", { name: "Close details" }).click();
  await expect(page.getByTestId("migration-roadmap")).not.toHaveAttribute("data-compact", "true");
  await expect(page.getByTestId("roadmap-intro")).toContainText("0 of 7 chosen, so the rest use the recommendation");
  // Phase 4b: every track has its own row, so a server can sit in two bands.
  await expect(page.getByTestId("roadmap-band").getByRole("heading", { level: 2 })).toHaveText([
    "At the target",
    "Done for now",
    "Phase 1",
    "Phase 2",
    "Later",
    "Wrapped",
    "Not placed yet",
  ]);
  await expectBand("At the target", [
    ["localhost:8455", "Key exchange"],
    ["localhost:8455", "Authentication"],
  ]);
  await expectBand("Done for now", [["localhost:8451", "Key exchange"]]);
  await expectBand("Phase 1", [["localhost:8452", "Key exchange"]]);
  await expectBand("Phase 2", [
    ["localhost:8451", "Authentication"],
    ["localhost:8452", "Authentication"],
    ["acme-sign 1.4.2", "Signatures"],
  ]);
  await expectBand("Later", [["localhost:8453", "Both tracks"]]);
  await expectBand("Wrapped", [["localhost:8454", "Both tracks"]]);
  await expectBand("Not placed yet", [["acme-sign 9.9", ""]]);
  await expect(band("Phase 1").getByTestId("roadmap-note")).toContainText("To do: turn on hybrid key exchange.");
  await expect(bandRow("Phase 2", "acme-sign 1.4.2").getByTestId("roadmap-note")).toContainText(
    "Blocker: it signs with ECDSA P-256 only",
  );
  await expect(band("Later").getByTestId("roadmap-note")).toContainText("assumed: 12 months");
  await expect(page.getByText("recommended, not yet chosen by you")).toHaveCount(7);
  await expect(page.getByText(/\bsecure\b/i).filter({ hasNotText: DISCLAIMER })).toHaveCount(0);
  await expect(page.getByText(/\bscore\b/i)).toHaveCount(0);
  await shot("11-migration-roadmap.png");
});

test("Fixes: the change for Phase 1 has its change box (Ready to try); the blocker for Phase 2 stays text only", async () => {
  await band("Phase 1").getByRole("button", { name: "View in Fixes" }).click();
  await expect(page.getByRole("heading", { name: "Fixes", level: 1 })).toBeVisible();
  // (phase 5b: the list is in the four work groups, whose headings are buttons too: count the fixes' rows)
  const list = page.getByRole("navigation", { name: /^Open findings with a fix/ }).getByTestId("fix-row");
  await expect(list).toHaveCount(2);
  const fix = page.getByTestId("fix-summary");
  // (phase 5a follow-up: the open fix's title is the detail panel's heading)
  await expect(
    page
      .getByTestId("detail-panel")
      .getByRole("heading", { name: "Turn on hybrid key exchange on localhost:8452", level: 2 }),
  ).toBeVisible();
  // Since phase 4b the status word is the change box's badge.
  await expect(fix.getByTestId("fix-status")).toHaveText("Ready to try");
  await expect(fix.getByTestId("fix-proof")).toContainText(
    "The change box below shows its try on a test copy, its approvals, and Apply.",
  );
  const box = page.getByTestId("change-box");
  await expect(box.getByTestId("change-badge")).toContainText("Ready to try");
  await expect(box).toContainText("It adds the hybrid key exchange next to the classical ones");
  await expect(box).toContainText("Checked on nginx 1.31.8 with OpenSSL 3.5.9:");
  await expect(box).toContainText("ssl_ecdh_curve X25519MLKEM768:X25519;");
  await expect(box).toContainText("Not checked on real software");
  await expect(box.getByRole("button", { name: "Try on a test copy" })).toBeEnabled();
  await expect(box.getByRole("button", { name: "Download change" })).toBeEnabled();
  await shot("12-fixes-how-to-turn-on-hybrid.png");
  await list.filter({ hasText: "acme-sign 1.4.2 can't make post-quantum signatures" }).click();
  const blocker = page.getByTestId("change-box");
  await expect(page.getByTestId("fix-summary").getByTestId("fix-status")).toHaveText("Text only");
  await expect(blocker.getByTestId("change-badge")).toContainText("Text only");
  await expect(blocker).toContainText("It can't be tried or applied in the lab in this version");
  // Only Download change: nothing here can be tried or applied.
  await expect(blocker.getByRole("button")).toHaveText(["Download change"]);
  await shot("13-fixes-blocker-signing-program.png");
});

test("Your own choice: a reason is needed when it differs, the review date is never forever, and the roadmap follows", async () => {
  await stepLink(page, "6. Migration").click();
  await page.getByRole("button", { name: /^Systems/ }).click();
  const detail = await open("localhost:8452");
  const keep = option("Keep classical for now");
  await keep.getByRole("button", { name: "Choose this option" }).click();
  const box = keep.getByTestId("choose-box");
  await expect(box.getByRole("button", { name: "Save choice" })).toBeDisabled(); // differs from the recommendation: say why
  await expect(box.getByLabel("Review date")).toHaveAttribute("max", "2030-12-31");
  await box.getByLabel(/Your reason/).fill("Server is replaced in Q2 2027; upgrading it first isn't worth it.");
  await box.getByLabel("Review date").fill("2027-06-30");
  await shot("14-migration-choose-with-reason-and-review-date.png");
  await box.getByRole("button", { name: "Save choice" }).click();
  await expect(detail.getByTestId("migration-choice")).toContainText("Your choice: Keep classical for now");
  await expect(detail.getByTestId("migration-choice")).toContainText("Review date: 30 Jun 2027.");
  await expect(card("localhost:8452")).toContainText("Kept classical · review 30 Jun 2027");
  await expect(detail.getByRole("heading", { name: "Recommended: Hybrid", exact: true })).toBeVisible(); // the recommendation is not rewritten
  await expect(option("Keep classical for now")).toContainText("Your choice");
  await page.getByRole("button", { name: "Roadmap", exact: true }).click();
  await expect(page.getByTestId("roadmap-intro")).toContainText("1 of 7 chosen");
  await expect(band("Later").getByTestId("roadmap-row")).toHaveCount(2);
  await expect(band("Later").getByTestId("roadmap-row").filter({ hasText: "localhost:8452" })).toContainText(
    "chosen by you",
  );
  await expect(band("Phase 1")).toHaveCount(0);
  await shot("15-migration-roadmap-follows-your-choice.png");
});

test("A setting changes the recommendation at once; measuring again never changes your choice", async () => {
  await page.getByRole("button", { name: /^Systems/ }).click();
  let detail = await open("localhost:8453");
  await expect(detail.getByRole("heading", { name: "Recommended: Keep classical for now" })).toBeVisible();
  await detail.getByLabel("Data lifespan").selectOption("long");
  await expect(detail.getByRole("heading", { name: "Recommended: Hybrid", exact: true })).toBeVisible();
  await expect(detail.getByTestId("setting-source").first()).toHaveText("set by you");
  await expect(card("localhost:8453")).toContainText("Next: hybrid key exchange · Phase 2");
  await detail.getByLabel("Data lifespan").selectOption("short");
  await expect(detail.getByRole("heading", { name: "Recommended: Keep classical for now" })).toBeVisible();
  await page.getByRole("button", { name: "Measure again" }).click();
  await expect(page.getByRole("button", { name: "Measure again" })).toBeEnabled({ timeout: 120_000 });
  await expect(card("localhost:8452")).toContainText("Kept classical · review 30 Jun 2027");
  detail = await open("localhost:8452");
  await expect(detail.getByTestId("migration-choice")).toContainText("Server is replaced in Q2 2027");
});

test("Download evidence from the roadmap: the plan is in the signed file and the report", async () => {
  await page.getByRole("button", { name: "Roadmap", exact: true }).click();
  const created = page.waitForResponse(
    (r) => /\/api\/plans\/\d+\/evidence$/.test(r.url()) && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Download evidence" }).click();
  const made = await created;
  expect(made.status()).toBe(200);
  const info = await made.json();
  const json = await (await page.request.get(info.json.url)).json();
  const migration = json.evidence.migration;
  expect(migration.systems.map((s: { status: string }) => s.status)).toEqual([
    "Hybrid",
    "Classical",
    "Classical",
    "Classical",
    "Post-quantum only",
    "Classical",
    "Couldn't check",
  ]);
  const chosen = migration.systems.find((s: { system: string }) => s.system === "localhost:8452");
  expect(chosen.your_choice.option).toBe("Keep classical for now");
  expect(chosen.your_choice.review_date).toBe("2027-06-30");
  expect(chosen.recommendation.option).toBe("Hybrid");
  expect(migration.measurements).toHaveLength(7);
  const report = await (await page.request.get(info.html.url)).text();
  expect(report).toContain("5. Migration plan");
  expect(report).toContain("Server is replaced in Q2 2027");
  expect(report).not.toContain("<script");
  for (const server of SERVERS) expect(report).toContain(server);
});
