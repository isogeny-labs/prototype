// Throwaway: takes the pictures of mockups.html for docs/plans/design-refactor.md. Not a test, not part of the app,
// and not run by any check. It uses the repo's Playwright (the version e2e/ pins) with the settings of
// e2e/playwright.config.ts: Chromium, a window 1440 pixels wide, a viewer in New York. The pictures are 1440 pixels
// wide (one picture pixel per screen pixel). Afterwards each picture is reduced to 256 colours, which a flat screen
// does not show and which makes the files about a third the size, small enough to keep outside Git LFS:
//
//   node docs/plans/design-refactor/mockups/shoot.mjs
//   python3 -c "import glob,sys;from PIL import Image;[Image.open(f).convert('RGB').quantize(256,dither=Image.Dither.NONE).save(f,optimize=True) for f in glob.glob(sys.argv[1]+'/*.png')]" docs/plans/design-refactor/mockups
//
// It reads nothing but mockups.html and, for the before/after pictures, three existing pictures under
// docs/screenshots/ (fetch those first: git lfs pull --include="docs/screenshots/sandbox/15-*,docs/screenshots/phase5c/3-00-*,docs/screenshots/group-tabs/evidence-2-encryption-panel-closed-*").
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../..");
const require = createRequire(import.meta.url);

function loadChromium() {
  for (const from of [path.join(repo, "e2e/node_modules/@playwright/test"), "@playwright/test", "playwright"]) {
    try {
      return require(from).chromium;
    } catch {
      /* try the next place */
    }
  }
  throw new Error("Playwright is not installed. Run: npm --prefix e2e ci");
}

const SHOTS = [
  ["01-overview", "overview", "closed"],
  ["02-checks-tabs", "checks", "closed"],
  ["03-evidence-tabs", "evidence", "closed"],
  ["04-result-proof-collapsed", "result", "closed"],
  ["05-result-proof-expanded", "result", "open"],
  ["06-test-proof-collapsed", "advisory", "closed"],
  ["07-test-proof-expanded", "advisory", "open"],
  ["08-fix-two-proof-rows", "fix", "closed"],
  ["09-fix-proof-expanded", "fix", "open"],
  ["10-observatory-just-brought-in", "observatorynew", "closed"],
  ["11-observatory-map", "observatory", "closed"],
  ["12-observatory-a-system-open", "system", "closed"],
  ["13-observed-result-record-collapsed", "observed", "closed"],
  ["14-observed-result-record-expanded", "observed", "open"],
];

// [name, the picture of today's screen, the mockup it is set beside, what each side is called]
const COMPARE = [
  [
    "compare-tabs",
    "docs/screenshots/group-tabs/evidence-2-encryption-panel-closed",
    "03-evidence-tabs",
    "Today: Evidence, Crypto tests",
    "Proposed: Evidence, Crypto tests",
  ],
  [
    "compare-result-proof",
    "docs/screenshots/phase5c/3-00-evidence-result-where-the-check-came-from",
    "04-result-proof-collapsed",
    "Today: one result, as it opens",
    "Proposed: the same result, as it opens",
  ],
  [
    "compare-test-proof",
    "docs/screenshots/sandbox/15-the-proposal-with-its-whole-proof",
    "07-test-proof-expanded",
    "Today: one proposed check, opened to read its proof",
    "Proposed: the same proposal, opened the same way",
  ],
];

const isPicture = (file) => fs.existsSync(file) && fs.readFileSync(file).subarray(1, 4).toString() === "PNG";

const browser = await loadChromium().launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  timezoneId: "America/New_York",
});
const page = await context.newPage();
const mock = pathToFileURL(path.join(here, "mockups.html")).href;

for (const theme of ["dark", "light"]) {
  for (const [name, screen, proof] of SHOTS) {
    await page.goto(`${mock}?shot=1&screen=${screen}&theme=${theme}&proof=${proof}`);
    await page.screenshot({ path: path.join(here, `${name}-${theme}.png`), fullPage: true });
    console.log(`${name}-${theme}.png`);
  }
  for (const [name, before, after, beforeTitle, afterTitle] of COMPARE) {
    const beforeFile = path.join(repo, `${before}-${theme}.png`);
    if (!isPicture(beforeFile)) {
      console.log(`${name}-${theme}.png left out: ${before}-${theme}.png is not fetched (git lfs pull).`);
      continue;
    }
    const dark = theme === "dark";
    // A small page of its own, written beside the pictures and removed again, so both file pictures load.
    const sheet = path.join(here, `.compare-${name}-${theme}.html`);
    fs.writeFileSync(
      sheet,
      `<!doctype html><meta charset="utf-8"><style>
      body{margin:0;padding:24px;background:${dark ? "#0b1020" : "#eef1f6"};color:${dark ? "#e2e8f0" : "#0f172a"};font:14px/1.4 Inter,system-ui,sans-serif}
      .cols{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}
      h2{margin:0 0 4px;font-size:17px} p{margin:0 0 12px;font-size:13px;opacity:.7}
      img{display:block;width:100%;border:1px solid ${dark ? "#334155" : "#cbd5e1"};border-radius:8px}
    </style><div class="cols">
      <div><h2>${beforeTitle}</h2><p id="b"></p><img id="bi" src="${pathToFileURL(beforeFile).href}"></div>
      <div><h2>${afterTitle}</h2><p id="a"></p><img id="ai" src="${after}-${theme}.png"></div>
    </div>`,
    );
    await page.setViewportSize({ width: 1440, height: 300 }); // (so a short comparison is not padded to a full window)
    await page.goto(pathToFileURL(sheet).href);
    fs.rmSync(sheet);
    await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
    // How tall each screen is at the width it was drawn for (1440), so the two lengths can be compared.
    await page.evaluate(() => {
      const tall = (img) => Math.round((img.naturalHeight * 1440) / img.naturalWidth);
      document.getElementById("b").textContent = `The whole screen is ${tall(document.getElementById("bi"))} pixels tall at 1440 wide.`;
      document.getElementById("a").textContent = `The whole screen is ${tall(document.getElementById("ai"))} pixels tall at 1440 wide (mockup).`;
    });
    await page.screenshot({ path: path.join(here, `${name}-${theme}.png`), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    console.log(`${name}-${theme}.png`);
  }
}
await browser.close();
