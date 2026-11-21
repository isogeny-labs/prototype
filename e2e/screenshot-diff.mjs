// Compare two sets of end-to-end screenshots, "before" (the pull request's base) and "after" (the pull request),
// and write a gallery of what changed. Used by the GitHub check "Screenshots of the change"; it can also be run by
// hand after two runs of `npm test`:
//
//   node screenshot-diff.mjs BEFORE_DIR AFTER_DIR OUT_DIR
//
// Pictures are matched by their path under the two folders. A picture whose file is byte for byte the same is
// unchanged. Otherwise the pixels are compared in the Playwright browser this folder already installs (no new
// package): a pixel counts as changed when one of its colour channels moves by more than THRESHOLD (out of 255).
// OUT_DIR gets index.html (before, after and a diff picture with the changed pixels in red, side by side), the
// pictures it shows, and summary.md (also appended to the GitHub job summary when GITHUB_STEP_SUMMARY is set).
// The comparison never fails the check: it only shows what a change does to the pages.
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const THRESHOLD = 24;
const [beforeDir, afterDir, outDir] = process.argv.slice(2);
if (!beforeDir || !afterDir || !outDir) {
  console.error("usage: node screenshot-diff.mjs BEFORE_DIR AFTER_DIR OUT_DIR");
  process.exit(2);
}

function pngs(dir) {
  const found = [];
  const walk = (sub) => {
    const here = path.join(dir, sub);
    if (!fs.existsSync(here)) return;
    for (const entry of fs.readdirSync(here, { withFileTypes: true })) {
      const rel = path.posix.join(sub, entry.name);
      if (entry.isDirectory()) walk(rel);
      else if (entry.isFile() && entry.name.endsWith(".png")) found.push(rel);
    }
  };
  walk("");
  return new Set(found);
}

const before = pngs(beforeDir);
const after = pngs(afterDir);
const added = [...after].filter((p) => !before.has(p)).sort();
const removed = [...before].filter((p) => !after.has(p)).sort();
const both = [...after].filter((p) => before.has(p)).sort();
const candidates = both.filter(
  (p) => !fs.readFileSync(path.join(beforeDir, p)).equals(fs.readFileSync(path.join(afterDir, p))),
);

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

// Pixel comparison in the browser. Files are served from a made-up origin so the canvas may read them back.
const changed = [];
if (candidates.length > 0) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.route("http://shots.invalid/**", async (route) => {
    const url = new URL(route.request().url());
    const [side, ...rest] = url.pathname.slice(1).split("/");
    if (!url.pathname.endsWith(".png")) {
      await route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>diff</title>" });
      return;
    }
    const file = path.join(side === "before" ? beforeDir : afterDir, decodeURIComponent(rest.join("/")));
    await route.fulfill({ status: 200, contentType: "image/png", body: fs.readFileSync(file) });
  });
  await page.goto("http://shots.invalid/before/");
  for (const rel of candidates) {
    const result = await page.evaluate(
      async ({ rel, threshold }) => {
        const load = (side) =>
          new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error(`could not load ${side}/${rel}`));
            img.src = `/${side}/${rel.split("/").map(encodeURIComponent).join("/")}`;
          });
        const [a, b] = await Promise.all([load("before"), load("after")]);
        const width = Math.max(a.naturalWidth, b.naturalWidth);
        const height = Math.max(a.naturalHeight, b.naturalHeight);
        const pixels = (img) => {
          const canvas = new OffscreenCanvas(width, height);
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0);
          return ctx.getImageData(0, 0, width, height).data;
        };
        const pa = pixels(a);
        const pb = pixels(b);
        const out = new OffscreenCanvas(width, height);
        const octx = out.getContext("2d");
        const diff = octx.createImageData(width, height);
        const d = diff.data;
        let count = 0;
        for (let i = 0; i < pa.length; i += 4) {
          const moved =
            Math.abs(pa[i] - pb[i]) > threshold ||
            Math.abs(pa[i + 1] - pb[i + 1]) > threshold ||
            Math.abs(pa[i + 2] - pb[i + 2]) > threshold ||
            Math.abs(pa[i + 3] - pb[i + 3]) > threshold;
          if (moved) {
            count++;
            d[i] = 230;
            d[i + 1] = 20;
            d[i + 2] = 20;
            d[i + 3] = 255;
          } else {
            // The "after" picture, faded to grey, so the red stands out.
            const grey = (pb[i] + pb[i + 1] + pb[i + 2]) / 3;
            d[i] = d[i + 1] = d[i + 2] = 255 - (255 - grey) * 0.25;
            d[i + 3] = 255;
          }
        }
        if (count === 0) return { count, total: width * height };
        octx.putImageData(diff, 0, 0);
        const blob = await out.convertToBlob({ type: "image/png" });
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let binary = "";
        for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        return {
          count,
          total: width * height,
          sizes: [a.naturalWidth, a.naturalHeight, b.naturalWidth, b.naturalHeight],
          png: btoa(binary),
        };
      },
      { rel, threshold: THRESHOLD },
    );
    if (result.count === 0) continue;
    const diffPath = path.join(outDir, "diff", rel);
    fs.mkdirSync(path.dirname(diffPath), { recursive: true });
    fs.writeFileSync(diffPath, Buffer.from(result.png, "base64"));
    changed.push({ rel, share: result.count / result.total, sizes: result.sizes });
  }
  await browser.close();
}
changed.sort((x, y) => y.share - x.share);

const copy = (side, rel) => {
  const dest = path.join(outDir, side, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(path.join(side === "before" ? beforeDir : afterDir, rel), dest);
};
for (const { rel } of changed) {
  copy("before", rel);
  copy("after", rel);
}
for (const rel of added) copy("after", rel);
for (const rel of removed) copy("before", rel);

const pct = (share) => (share >= 0.001 ? `${(share * 100).toFixed(1)}%` : "under 0.1%");
const sizeNote = ({ sizes }) =>
  sizes && (sizes[0] !== sizes[2] || sizes[1] !== sizes[3])
    ? ` (size ${sizes[0] / 2}×${sizes[1] / 2} → ${sizes[2] / 2}×${sizes[3] / 2})`
    : "";

const lines = [
  "## Screenshots of the change",
  "",
  `${both.length + added.length} pictures taken by the end-to-end walks; compared with the same walks on the base.`,
  "",
  `- **Changed:** ${changed.length}`,
  `- **New:** ${added.length}`,
  `- **No longer taken:** ${removed.length}`,
  `- **Unchanged:** ${both.length - changed.length}`,
  "",
];
if (changed.length > 0) {
  lines.push("| Changed picture | Pixels changed |", "| --- | --- |");
  for (const c of changed) lines.push(`| \`${c.rel}\` | ${pct(c.share)}${sizeNote(c)} |`);
  lines.push("");
}
if (added.length > 0) lines.push("New pictures: " + added.map((p) => `\`${p}\``).join(", "), "");
if (removed.length > 0) lines.push("No longer taken: " + removed.map((p) => `\`${p}\``).join(", "), "");
lines.push(
  "Before, after and diff side by side: download the **screenshots-of-the-change** artifact of this run and open `index.html`.",
  "A walk that failed on either side takes fewer pictures, so its pictures show as new or no longer taken.",
  "",
);
const summary = lines.join("\n");
fs.writeFileSync(path.join(outDir, "summary.md"), summary);
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary + "\n");

const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const src = (side, rel) => esc(`${side}/${rel}`);
const figure = (label, side, rel) =>
  `<figure><figcaption>${label}</figcaption><a href="${src(side, rel)}"><img loading="lazy" src="${src(side, rel)}" alt="${label}: ${esc(rel)}"></a></figure>`;
const sections = [
  ...changed.map(
    (c) =>
      `<section><h2>${esc(c.rel)} <small>${pct(c.share)} of pixels changed${esc(sizeNote(c))}</small></h2><div class="row">` +
      figure("Before", "before", c.rel) +
      figure("After", "after", c.rel) +
      figure("Changed pixels in red", "diff", c.rel) +
      `</div></section>`,
  ),
  ...added.map(
    (rel) =>
      `<section><h2>${esc(rel)} <small>new</small></h2><div class="row">${figure("After", "after", rel)}</div></section>`,
  ),
  ...removed.map(
    (rel) =>
      `<section><h2>${esc(rel)} <small>no longer taken</small></h2><div class="row">${figure("Before", "before", rel)}</div></section>`,
  ),
];
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screenshots of the change</title>
<style>
  :root { color-scheme: light dark; --bg: #fafafa; --fg: #1a1a1a; --muted: #666; --line: #ddd; }
  @media (prefers-color-scheme: dark) { :root { --bg: #16181c; --fg: #e8e8e8; --muted: #9a9a9a; --line: #333; } }
  body { margin: 0; padding: 16px 24px; background: var(--bg); color: var(--fg); font: 14px/1.5 system-ui, sans-serif; }
  h1 { font-size: 20px; } h2 { font-size: 15px; font-family: ui-monospace, monospace; margin: 32px 0 8px; }
  h2 small { font-family: system-ui, sans-serif; color: var(--muted); font-weight: normal; margin-left: 8px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; align-items: start; }
  figure { margin: 0; } figcaption { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
  img { width: 100%; border: 1px solid var(--line); display: block; }
  p.none { color: var(--muted); }
</style></head><body>
<h1>Screenshots of the change</h1>
<p>${changed.length} changed, ${added.length} new, ${removed.length} no longer taken, ${both.length - changed.length} unchanged. Click a picture for full size.</p>
${sections.join("\n") || '<p class="none">No picture changed.</p>'}
</body></html>
`;
fs.writeFileSync(path.join(outDir, "index.html"), html);
console.log(summary);
