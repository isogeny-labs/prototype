import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FixLine, LabView } from "../api";
import { EvidenceLabScreen } from "../components/EvidenceLabScreen";
import {
  DISCLAIMER,
  FINGERPRINT,
  beforeAfter,
  calls,
  evidenceExport,
  fixLines,
  lab,
  mockApi,
  research,
  result,
  retestRunning,
  text,
  withResult,
} from "./fixtures";

type Routes = Parameters<typeof mockApi>[0];

/** The fixes "View in Fixes" asked the app to open, in order. */
const viewed: string[] = [];
beforeEach(() => {
  viewed.length = 0;
});

const screenUnderTest = () => <EvidenceLabScreen planId={1} onViewFix={(fixId) => viewed.push(fixId)} />;

async function open(view: LabView = lab, routes: Routes = {}) {
  const fetchMock = mockApi({ "GET /api/plans/1/lab": { body: view }, ...routes });
  render(screenUnderTest());
  await screen.findAllByTestId("lab-row");
  return fetchMock;
}

const rows = () => screen.getAllByTestId("lab-row");
const rowOf = (title: string) => rows().find((r) => within(r).queryByRole("heading", { name: title }))!;
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const expand = (title: string) => fireEvent.click(within(rowOf(title)).getByRole("button", { name: title }));
const label = (el: HTMLElement) => el.lastElementChild?.textContent;

describe("Evidence Lab, results view", () => {
  it("shows the heading, Demo data, subline, the disclaimer line and the two buttons", async () => {
    const fetchMock = await open();
    expect(calls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);
    expect(screen.getByRole("heading", { name: "Evidence Lab" })).not.toBeNull();
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(text(screen.getByTestId("lab-subline"))).toMatch(
      /^Results by test for server localhost:8443 and signing component acme-sign 1\.4\.2\. Run finished .+\.$/,
    );
    expect(screen.getByTestId("lab-subline").querySelector("time")?.getAttribute("datetime")).toBe("2026-11-11T01:42:16.000Z");
    expect(screen.getByTestId("disclaimer").textContent).toBe(DISCLAIMER);
    expect(screen.getAllByRole("button").map((b) => b.textContent).slice(0, 2)).toEqual(["Retest new version", "Download evidence"]);
  });

  it("uses the word 'secure' exactly once, has no score, no upload control and no mockup marker", async () => {
    await open();
    for (const r of rows()) fireEvent.click(within(r).getAllByRole("button")[0]!);
    fireEvent.click(button("Retest new version"));
    const all = document.body.textContent ?? "";
    expect(all.match(/secure/gi)).toHaveLength(1);
    expect(all).not.toMatch(/score|time.to.hack|upload|mockup/i);
    expect(document.querySelector("input, textarea, select, form")).toBeNull();
  });

  it("lists collapsed rows with the summary, control line and a badge for every label", async () => {
    await open();
    expect(rows()).toHaveLength(5);
    expect(screen.getAllByTestId("result-badge").map(label)).toEqual([
      "Failed",
      "Passed",
      "Failed",
      "Measured",
      "Couldn't run (needs OpenSSL 3.5 or newer)",
    ]);
    const vectors = within(rowOf("Official test vectors"));
    expect(vectors.getByText(/^3 of 484 official cases wrong\. Headline: case 168/)).not.toBeNull();
    expect(vectors.getByText("Control: a deliberately broken signer failed this test, as expected.")).not.toBeNull();
    expect(screen.queryByTestId("result-detail")).toBeNull();
    // The locked test and its fingerprint are not on the collapsed list.
    expect(document.body.textContent).not.toContain(FINGERPRINT);
    expect(screen.queryByText("Test details, locked before the run")).toBeNull();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
  });

  it("gives Couldn't trust this run the same badge look as Couldn't run", async () => {
    const view = { ...lab, rows: lab.rows.map((r, i) => (i === 0 ? { ...r, result: result(5, "couldnt_trust", "Couldn't trust this run", "warn", "The control did not fail.") } : r)) };
    await open(view);
    const badges = screen.getAllByTestId("result-badge");
    expect(label(badges[0]!)).toBe("Couldn't trust this run");
    expect(badges[0]!.className).toBe(badges[4]!.className);
    fireEvent.click(within(rows()[0]!).getByRole("button"));
    // No fix is suggested for a run that can't be trusted.
    expect(within(rows()[0]!).queryByTestId("suggested-fix")).toBeNull();
  });

  it("opens a result with every section in order, with tags, and closes it again", async () => {
    await open();
    const toggle = within(rowOf("Official test vectors")).getByRole("button", { name: "Official test vectors" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    const detail = within(rowOf("Official test vectors")).getByTestId("result-detail");
    const d = within(detail);
    expect(d.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual([
      "What happened",
      "What this shows, and what it doesn't",
      "Evidence",
      "Control",
    ]);
    expect(d.getByText(/^The clearest is case 168/)).not.toBeNull();
    expect(d.getByText(/^It doesn't show whether anyone has used this/)).not.toBeNull();

    // Cases table.
    const table = within(d.getByRole("table"));
    expect(table.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Official case",
      "What the case is",
      "Right answer",
      "acme-sign 1.4.2 said",
    ]);
    expect(table.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]!.textContent)).toEqual(["168", "171", "364"]);
    expect(table.getByText("168").className).toContain("font-mono");

    // Run record with provenance tags and our own source link.
    expect(d.getByText("Run record")).not.toBeNull();
    expect(d.getByText(/^acme-sign verify \(once per case/)).not.toBeNull();
    expect(d.getByText(/cases run: 484/).tagName).toBe("PRE");
    for (const tag of ["measured", "demo", "reference"]) expect(d.getAllByText(tag).length).toBeGreaterThan(0);
    expect(d.getByText("Demo mode, not isolated")).not.toBeNull();
    const link = d.getByRole("link", { name: "Project Wycheproof, C2SP/wycheproof commit dab4ea2" });
    expect(link.getAttribute("href")).toMatch(/^https:\/\/github\.com\/C2SP\/wycheproof\/tree\/dab4ea2/);

    // Locked test details and fingerprint.
    const lockedBox = within(d.getByTestId("locked-test"));
    expect(d.getByText("Test details, locked before the run")).not.toBeNull();
    for (const term of ["Question", "Method", "Inputs", "Control", "Pass/fail rule", "Locked", "Fingerprint of these details (SHA-256)"]) {
      expect(lockedBox.getByText(term)).not.toBeNull();
    }
    expect(lockedBox.getByText(/before the run started/)).not.toBeNull();
    expect(d.getByTestId("spec-fingerprint").textContent).toBe(FINGERPRINT);

    // Control outcome, then the one line that points to the fix (this failure has one in Fixes).
    expect(d.getByTestId("control-outcome").getAttribute("data-outcome")).toBe("as_expected");
    expect(d.getByText(/^The deliberately broken signer got all 310 invalid cases wrong/)).not.toBeNull();
    expect(text(d.getByTestId("fix-line").querySelector("p"))).toBe("Fix available, code not connected");
    expect(d.queryByTestId("suggested-fix")).toBeNull();

    // The three buttons, and nothing else.
    expect(d.getAllByRole("button").map((b) => b.textContent)).toEqual(["View in Fixes", "Mark reviewed", "Dig deeper"]);
    expect(d.queryByTestId("research-request")).toBeNull();

    fireEvent.click(toggle);
    expect(screen.queryByTestId("result-detail")).toBeNull();
  });

  it("does not turn a non-https source into a link", async () => {
    const meta = [{ label: "Vectors", value: "somewhere", tag: null, href: "javascript:alert(1)" }];
    await open(withResult(lab, 13, { run_record: { ...lab.rows[2]!.result!.run_record, meta } }));
    expand("Official test vectors");
    expect(screen.getByText("somewhere")).not.toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("puts Mark reviewed and Dig deeper on every opened result", async () => {
    await open();
    for (const r of rows()) fireEvent.click(within(r).getAllByRole("button")[0]!);
    expect(screen.getAllByTestId("result-detail")).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: "Mark reviewed" })).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: "Dig deeper" })).toHaveLength(5);
    expect(screen.getAllByText("What this shows, and what it doesn't")).toHaveLength(5);
  });

  it("Mark reviewed calls the API and then shows its recorded state", async () => {
    const reviewed = withResult(lab, 13, { reviewed: { at: "2026-11-11T01:46:02.000Z", text: "You marked this result as reviewed." } });
    const fetchMock = await open(lab, { "POST /api/runs/7/mark-reviewed": { body: reviewed } });
    expand("Official test vectors");
    fireEvent.click(button("Mark reviewed"));
    const done = await screen.findByRole("button", { name: "Reviewed" });
    expect(calls(fetchMock)).toContain("POST /api/runs/7/mark-reviewed");
    expect((done as HTMLButtonElement).disabled).toBe(true);
    expect(done.getAttribute("aria-pressed")).toBe("true");
    expect(text(screen.getByTestId("reviewed-note"))).toContain("You marked this result as reviewed.");
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
    // The result itself is unchanged.
    expect(label(within(rowOf("Official test vectors")).getAllByTestId("result-badge")[0]!)).toBe("Failed");
  });

  it("Dig deeper calls the API and then shows the queued research request, with no answer", async () => {
    const fetchMock = await open(lab, { "POST /api/runs/7/dig-deeper": { body: withResult(lab, 13, { research }) } });
    expand("Official test vectors");
    fireEvent.click(button("Dig deeper"));
    const box = within(await screen.findByTestId("research-request"));
    expect(calls(fetchMock)).toContain("POST /api/runs/7/dig-deeper");
    expect(box.getByText("Research request saved")).not.toBeNull();
    expect(box.getByText("Queued")).not.toBeNull();
    expect(box.getByText("Status: waiting for research engine")).not.toBeNull();
    for (const term of ["Finding", "Question", "Evidence attached", "Saved"]) expect(box.getByText(term)).not.toBeNull();
    expect(box.getByText(/^No answer yet\./)).not.toBeNull();
    const queued = button("Dig deeper: queued");
    expect(queued.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Dig deeper" })).toBeNull();
    expect(button("Mark reviewed").disabled).toBe(false);
  });

  it("shows a row that has no reviewed result as a status, never as a result", async () => {
    const view: LabView = {
      ...lab,
      rows: lab.rows.map((r, i) =>
        i === 1 ? { ...r, control_line: "", result: null, result_status: { status: "not_run", status_text: "Not run yet", progress: null } } : r,
      ),
      retest: { ...lab.retest, can_start: false, blocked_reason: "Run every test in the plan first." },
    };
    await open(view);
    const row = within(rowOf("Certificate strength"));
    expect(row.getByText("Not run yet")).not.toBeNull();
    expect(row.queryByTestId("result-badge")).toBeNull();
    expect(row.queryByRole("button")).toBeNull();
    expect(button("Retest new version").disabled).toBe(true);
    expect(screen.getByTestId("blocked-reason").textContent).toBe("Run every test in the plan first.");
  });
});

describe("Evidence Lab, retest", () => {
  it("opens the chooser with the two demo versions and starts the retest on a click, with no confirm", async () => {
    const fetchMock = await open(lab, { "POST /api/plans/1/retest": { body: beforeAfter } });
    const retest = button("Retest new version");
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(retest);
    expect(retest.getAttribute("aria-expanded")).toBe("true");
    const menu = within(screen.getByRole("menu", { name: "Choose the version to retest" }));
    const items = menu.getAllByRole("menuitem");
    expect(items.map((i) => Array.from(i.querySelectorAll("span")).map((p) => p.textContent))).toEqual([
      ["acme-sign 1.4.3", "demo", "The corrected demo version."],
      ["acme-sign 1.4.2", "demo", "The demo version these results are for."],
    ]);
    expect(menu.getByText(/Only our two demo versions can be chosen here\.$/)).not.toBeNull();
    expect(menu.queryByRole("button", { name: /confirm|start|ok/i })).toBeNull();
    expect(calls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);

    fireEvent.click(items[0]!);
    await screen.findByTestId("lab-columns");
    const call = fetchMock.mock.calls.find(([url]) => String(url) === "/api/plans/1/retest");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ version: "1.4.3" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("shows before and after side by side, with rows still expandable", async () => {
    await open(beforeAfter);
    expect(Array.from(screen.getByTestId("lab-columns").children).map((c) => c.firstChild?.textContent ?? "")).toEqual([
      "",
      "Test",
      "Before: acme-sign 1.4.2",
      "After: acme-sign 1.4.3",
    ]);
    expect(text(screen.getByTestId("lab-subline"))).toMatch(/^Before and after: the same five locked tests, run on acme-sign 1\.4\.2 and then on acme-sign 1\.4\.3\./);

    const vectors = within(rowOf("Official test vectors"));
    expect(vectors.getByText("Control failed as expected in both runs.")).not.toBeNull();
    const before = within(vectors.getByTestId("lab-cell-before"));
    const after = within(vectors.getByTestId("lab-cell-after"));
    expect(label(before.getByTestId("result-badge"))).toBe("Failed");
    expect(before.getByText("3 of 484 official cases wrong (168, 171, 364), all from one missing range check.")).not.toBeNull();
    expect(label(after.getByTestId("result-badge"))).toBe("Passed");
    expect(after.getByText("484 of 484 official cases right.")).not.toBeNull();

    const speed = within(rowOf("Speed and size"));
    expect(label(within(speed.getByTestId("lab-cell-before")).getByTestId("result-badge"))).toBe("Measured");
    expect(label(within(speed.getByTestId("lab-cell-after")).getByTestId("result-badge"))).toBe("No slowdown beyond measured noise");

    expand("Official test vectors");
    const details = vectors.getAllByTestId("result-detail");
    expect(details.map((d) => within(d).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "After: acme-sign 1.4.3, the merged fix (commit c41f0d2)",
      "Before: acme-sign 1.4.2, the bundled demo version",
    ]);
    expect(details.map((d) => d.getAttribute("data-run-id"))).toEqual(["23", "7"]);
    expect(vectors.getAllByRole("button", { name: "Mark reviewed" })).toHaveLength(2);
    expect(vectors.getAllByRole("button", { name: "Dig deeper" })).toHaveLength(2);
  });

  it("shows the speed table with both versions, the noise band and the for-scale-only note", async () => {
    await open(beforeAfter);
    expand("Speed and size");
    const after = within(within(rowOf("Speed and size")).getAllByTestId("result-detail")[0]!);
    expect(after.getByText("Timings and sizes, before and after")).not.toBeNull();
    const headers = after.getAllByRole("columnheader");
    expect(headers.map((h) => text(h))).toEqual([
      "What was measured",
      "acme-sign 1.4.2before",
      "acme-sign 1.4.3after",
      "Change",
      "Reference library(cryptography)",
    ]);
    expect(headers[1]!.className).toContain("text-right");
    expect(after.getByText("-1.4%").className).toContain("text-right");
    expect(after.getByText(/±2\.4% \(from the paired differences in this run\)/)).not.toBeNull();
    expect(after.getByText(/It is shown for scale only/)).not.toBeNull();
    const tableBox = within(after.getByRole("table").parentElement!.parentElement!);
    expect(tableBox.getByText("measured")).not.toBeNull();
    expect(tableBox.getByText("reference")).not.toBeNull();
    expect(after.getByText("Output summary, acme-sign 1.4.2")).not.toBeNull();
    expect(after.getByText("Output summary, acme-sign 1.4.3")).not.toBeNull();
    expect(text(after.getByTestId("suggested-fix"))).toContain("None needed.");
  });

  it("shows live progress while the retest runs, dims the buttons, and polls until it has finished", async () => {
    let polls = 0;
    const fetchMock = mockApi({
      "GET /api/plans/1/lab": () => {
        polls += 1;
        return { body: polls < 3 ? retestRunning : beforeAfter };
      },
    });
    render(screenUnderTest());
    await screen.findAllByTestId("lab-row");
    expect(screen.getByTestId("retest-progress").textContent).toBe("Retest running: 1 of 5 tests finished.");
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Download evidence").disabled).toBe(true);
    const cert = within(within(rowOf("Certificate strength")).getByTestId("lab-cell-after"));
    expect(cert.getByText("Running")).not.toBeNull();
    expect(cert.getByText("reading the certificate")).not.toBeNull();
    expect(cert.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("40");
    expect(cert.queryByTestId("result-badge")).toBeNull();
    expect(within(within(rowOf("Speed and size")).getByTestId("lab-cell-after")).getByText("Waiting")).not.toBeNull();

    await waitFor(() => expect(screen.queryByTestId("retest-progress")).toBeNull(), { timeout: 5000 });
    expect(button("Retest new version").disabled).toBe(false);
    await new Promise((r) => setTimeout(r, 1300));
    expect(calls(fetchMock)).toHaveLength(3);
  }, 12000);
});

describe("Evidence Lab, the line that points to a fix", () => {
  const withLine = (line: FixLine) => withResult(lab, 13, { fix_line: line });
  const lineOf = (title: string) => within(rowOf(title)).getByTestId("fix-line");
  /** The words of a line, without the arrow and the button that follow them. */
  const words = (line: HTMLElement) => text(line.querySelector("p"));

  it("shows one line in place of the Suggested fix box, and View in Fixes asks the app for that fix", async () => {
    const fetchMock = await open();
    expand("Official test vectors");
    expand("Old TLS versions");
    expect(words(lineOf("Official test vectors"))).toBe("Fix available, code not connected");
    expect(words(lineOf("Old TLS versions"))).toBe("Text-only suggestion: a server setting");
    expect(text(lineOf("Old TLS versions"))).toBe("Text-only suggestion: a server setting→View in Fixes");
    for (const title of ["Official test vectors", "Old TLS versions"]) {
      expect(within(rowOf(title)).queryByTestId("suggested-fix")).toBeNull();
      expect(within(rowOf(title)).queryByText("Suggested fix")).toBeNull();
    }

    fireEvent.click(within(lineOf("Old TLS versions")).getByRole("button", { name: "View in Fixes" }));
    fireEvent.click(within(lineOf("Official test vectors")).getByRole("button", { name: "View in Fixes" }));
    expect(viewed).toEqual(["fix-tls-versions", "fix-ecdsa-range-check"]);
    // The line only links: it calls nothing itself.
    expect(calls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);
  });

  it.each([
    ["not_connected", "Fix available,", "code not connected", "border-slate-600 bg-slate-900"],
    ["proving", "Fix prepared:", "3 lines added and 1 removed, proof running", "border-slate-600 bg-slate-900"],
    ["passed", "Fix ready:", "3 lines added and 1 removed, proof passed", "border-sky-400/35 bg-sky-400/5"],
    ["failed", "Fix not offered:", "the proof did not pass", "border-amber-400/50 bg-amber-400/5"],
    ["merged", "Fix merged:", "3 lines added and 1 removed, proof passed", "border-slate-600 bg-slate-900"],
    ["text_only", "Text-only suggestion:", "a server setting", "border-dashed border-slate-500 bg-slate-900"],
  ] as const)("draws the %s line with its own words and look", async (state, lead, rest, look) => {
    const line = fixLines[state];
    // A line that is still busy would start the one-second polling; this test only looks at the first answer.
    await open(withLine(line));
    expand("Official test vectors");
    const el = lineOf("Official test vectors");
    expect(words(el)).toBe(`${lead} ${rest}`);
    expect(within(el).getByText(lead).className).toContain("font-semibold");
    expect(el.getAttribute("data-look")).toBe(line.look);
    expect(el.className).toContain(look);
    // The spinner shows only while the proof runs, and always next to the words.
    expect(el.querySelector(".animate-spin") !== null).toBe(line.busy);
    expect(within(el).getAllByRole("button").map((b) => b.textContent)).toEqual(["View in Fixes"]);
  });

  it("never calls a fix ready in a line whose proof has not passed", async () => {
    for (const state of ["not_connected", "proving", "failed", "text_only"] as const) {
      expect(`${fixLines[state].lead} ${fixLines[state].rest}`).not.toMatch(/ready/i);
    }
    await open(withLine(fixLines.failed));
    expand("Official test vectors");
    expect(text(rowOf("Official test vectors"))).not.toMatch(/ready/i);
  });

  it("keeps the Suggested fix box on a result that has no line", async () => {
    await open();
    expand("Certificate strength");
    const row = within(rowOf("Certificate strength"));
    expect(text(row.getByTestId("suggested-fix"))).toBe("Suggested fixNone needed.");
    expect(row.queryByTestId("fix-line")).toBeNull();
    expect(row.queryByRole("button", { name: "View in Fixes" })).toBeNull();
  });

  it("asks again every second while a fix's proof runs, and stops when it has ended", async () => {
    const reason = "A proof is running in Fixes. Wait until it has finished.";
    const proving: LabView = {
      ...withLine(fixLines.proving),
      retest: { ...lab.retest, can_start: false, blocked_reason: reason },
      download: { can_start: false, blocked_reason: reason },
      busy: true,
    };
    let polls = 0;
    const fetchMock = mockApi({
      "GET /api/plans/1/lab": () => {
        polls += 1;
        return { body: polls < 3 ? proving : withLine(fixLines.passed) };
      },
    });
    render(screenUnderTest());
    await screen.findAllByTestId("lab-row");
    expand("Official test vectors");
    expect(words(lineOf("Official test vectors"))).toBe("Fix prepared: 3 lines added and 1 removed, proof running");
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Download evidence").disabled).toBe(true);
    expect(screen.getAllByTestId("blocked-reason").map((p) => p.textContent)).toEqual([reason]);
    // A proof is not a retest: the retest progress line stays away.
    expect(screen.queryByTestId("retest-progress")).toBeNull();

    await waitFor(() => expect(words(lineOf("Official test vectors"))).toBe("Fix ready: 3 lines added and 1 removed, proof passed"), {
      timeout: 5000,
    });
    // The opened row stayed open, and the buttons are back.
    expect(button("Retest new version").disabled).toBe(false);
    expect(button("Download evidence").disabled).toBe(false);
    expect(screen.queryByTestId("blocked-reason")).toBeNull();
    await new Promise((r) => setTimeout(r, 1300));
    expect(calls(fetchMock)).toHaveLength(3);
  }, 12000);

  it("keeps asking while the answer says busy, also when no row shows the proof's line", async () => {
    // The tests the fix is for were taken out of the plan, so no row carries a line that says "proof running"
    // (none of this answer's lines is busy). The answer is still marked busy; without asking again the screen
    // would say "A proof is running" for ever.
    const reason = "A proof is running in Fixes. Wait until it has finished.";
    const provingUnseen: LabView = {
      ...lab,
      retest: { ...lab.retest, can_start: false, blocked_reason: reason },
      download: { can_start: false, blocked_reason: reason },
      busy: true,
    };
    let polls = 0;
    const fetchMock = mockApi({
      "GET /api/plans/1/lab": () => {
        polls += 1;
        return { body: polls < 3 ? provingUnseen : lab };
      },
    });
    render(screenUnderTest());
    await screen.findAllByTestId("lab-row");
    expect(provingUnseen.rows.some((r) => r.result?.fix_line?.busy || r.after?.fix_line?.busy)).toBe(false);
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Download evidence").disabled).toBe(true);
    expect(screen.getAllByTestId("blocked-reason").map((p) => p.textContent)).toEqual([reason]);

    await waitFor(() => expect(button("Retest new version").disabled).toBe(false), { timeout: 5000 });
    expect(button("Download evidence").disabled).toBe(false);
    expect(screen.queryByTestId("blocked-reason")).toBeNull();
    await new Promise((r) => setTimeout(r, 1300));
    expect(calls(fetchMock)).toHaveLength(3);
  }, 12000);
});

describe("Evidence Lab, which code each result ran on", () => {
  it("says it under each column heading, in one sentence under the subline and above the opened details", async () => {
    await open(beforeAfter);
    const columns = Array.from(screen.getByTestId("lab-columns").children);
    expect(columns.map((c) => text(c))).toEqual([
      "",
      "Test",
      "Before: acme-sign 1.4.2the bundled demo version",
      "After: acme-sign 1.4.3the merged fix, commit c41f0d2",
    ]);
    const notes = screen.getAllByTestId("lab-column-note");
    expect(notes.map((n) => text(n))).toEqual(["the bundled demo version", "the merged fix, commit c41f0d2"]);
    // The note is ordinary small text, not part of the capital-letter heading; the commit id is fixed width.
    expect(notes[1]!.className).toContain("normal-case");
    expect(within(notes[1]!).getByText("c41f0d2").className).toContain("font-mono");

    expect(text(screen.getByTestId("lab-code-line"))).toBe(
      "Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, the merged fix: branch main, commit c41f0d2 (pull request #1), the same byte for byte as our bundled acme-sign 1.4.3.",
    );
    // It comes right after the subline.
    expect(screen.getByTestId("lab-subline").nextElementSibling).toBe(screen.getByTestId("lab-code-line"));

    expand("Official test vectors");
    const details = within(rowOf("Official test vectors")).getAllByTestId("result-detail");
    expect(details.map((d) => d.getAttribute("aria-label"))).toEqual([
      "After: acme-sign 1.4.3, the merged fix (commit c41f0d2)",
      "Before: acme-sign 1.4.2, the bundled demo version",
    ]);
    // After the merge the old failure keeps its line; the new result passed and needs none.
    expect(text(within(details[1]!).getByTestId("fix-line").querySelector("p"))).toBe(
      "Fix merged: 3 lines added and 1 removed, proof passed",
    );
    expect(within(details[0]!).queryByTestId("fix-line")).toBeNull();
  });

  it("shows the Code item of the run record right after Component, with its source tag", async () => {
    await open();
    expand("Official test vectors");
    const detail = within(rowOf("Official test vectors")).getByTestId("result-detail");
    const items = Array.from(detail.querySelectorAll("ul > li")).map((li) => text(li));
    expect(items.slice(2, 5)).toEqual([
      "Component: acme-sign 1.4.2 demo",
      "Code: the bundled demo version of acme-sign 1.4.2 demo",
      "Mode: Demo mode, not isolated",
    ]);
  });

  it("draws no code sentence and no notes when the view sends none", async () => {
    await open();
    expect(screen.queryByTestId("lab-code-line")).toBeNull();
    expect(screen.queryByTestId("lab-column-note")).toBeNull();

    cleanup();
    const plain: LabView = {
      ...beforeAfter,
      code_line: null,
      columns: { ...beforeAfter.columns!, before_note: [], after_note: [] },
    };
    await open(plain);
    expect(Array.from(screen.getByTestId("lab-columns").children).map((c) => text(c))).toEqual([
      "",
      "Test",
      "Before: acme-sign 1.4.2",
      "After: acme-sign 1.4.3",
    ]);
    expect(screen.queryByTestId("lab-column-note")).toBeNull();
    expect(screen.queryByTestId("lab-code-line")).toBeNull();
  });
});

describe("Evidence Lab, download", () => {
  it("asks for the evidence, saves the JSON and the HTML report, and shows the fingerprint and how to check it", async () => {
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(`${this.getAttribute("href")} -> ${this.download}`);
    });
    const fetchMock = await open(lab, { "POST /api/plans/1/evidence": { body: evidenceExport } });
    fireEvent.click(button("Download evidence"));
    const status = within(await screen.findByTestId("download-status", undefined, { timeout: 3000 }));
    expect(calls(fetchMock)).toEqual(["GET /api/plans/1/lab", "POST /api/plans/1/evidence"]);
    expect(saved).toEqual([
      "/api/evidence/3/json -> evidence-lab-evidence-20261111-015810.json",
      "/api/evidence/3/html -> evidence-lab-report-20261111-015810.html",
    ]);
    expect(status.getByText(evidenceExport.message)).not.toBeNull();
    expect(status.getByText("Fingerprint (SHA-256):", { exact: false })).not.toBeNull();
    expect(status.getByTestId("evidence-fingerprint").textContent).toBe(evidenceExport.fingerprint);
    expect(status.getByText(evidenceExport.verify_hint)).not.toBeNull();
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("shows the server's reason if the evidence can't be made", async () => {
    await open(lab, {
      "POST /api/plans/1/evidence": { status: 409, body: { error: { message: "Wait for the tests to finish.", line: null, field: null } } },
    });
    fireEvent.click(button("Download evidence"));
    expect(text(await screen.findByRole("alert"))).toContain("Wait for the tests to finish.");
    expect(screen.queryByTestId("download-status")).toBeNull();
  });
});
