import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FixLine, LabView, LibraryEvidenceRow } from "../api";
import { checksView, retestDetail } from "./checksFixtures";
import { advisoryCheckRow } from "./ottoFixtures";
import { EvidenceLabScreen } from "../components/EvidenceLabScreen";
import {
  DISCLAIMER,
  FINGERPRINT,
  beforeAfter,
  groupedLab,
  calls,
  evidenceExport,
  fixLines,
  advisories,
  lab,
  mockApi,
  multiLibraryLab,
  research,
  result,
  retestRunning,
  text,
  withResult,
} from "./fixtures";
import { published } from "./sourceFixtures";

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
  await screen.findAllByTestId("evidence-row");
  return fetchMock;
}

const rows = () => screen.getAllByTestId("evidence-row");
const rowOf = (title: string) => rows().find((r) => within(r).queryAllByText(title).length > 0)!;
/** The right-side panel that holds one opened result. */
const panel = () => screen.getByTestId("detail-panel");
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const expand = (title: string) => fireEvent.click(rowOf(title));
/** Make sure the panel shows this row (opens it unless it is already the one open) and return the panel. */
const show = (title: string) => {
  const open = screen.queryByTestId("detail-panel");
  if (!open || within(open).queryByRole("heading", { level: 2, name: title }) === null) expand(title);
  return panel();
};
const label = (el: HTMLElement) => el.lastElementChild?.textContent;

/** The calls of the Evidence page itself. Since phase 5b it also asks for the checks (the other groups) once the lab's
 * answer is in and whenever it changes; those are counted by their own test. */
const labCalls = (fetchMock: Parameters<typeof calls>[0]) =>
  calls(fetchMock).filter((c) => !c.startsWith("GET /api/plans/1/checks"));

describe("Evidence Lab, results view", () => {
  it("shows the heading, Demo data, subline, the disclaimer line and the two buttons", async () => {
    const fetchMock = await open();
    expect(labCalls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);
    // The Results view of the Evidence section (26 November 2026): the section's name stands over the page's own.
    expect(screen.getByRole("heading", { level: 1, name: "Results" })).not.toBeNull();
    expect(text(screen.getByTestId("page-header"))).toMatch(/^Evidence Demo data\s*Results/);
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(text(screen.getByTestId("lab-subline"))).toMatch(
      /^Results by test for server localhost:8443 and signing component acme-sign 1\.4\.2\. Run finished .+\.$/,
    );
    expect(screen.getByTestId("lab-subline").querySelector("time")?.getAttribute("datetime")).toBe(
      "2026-11-11T01:42:16.000Z",
    );
    expect(screen.getByTestId("disclaimer").textContent).toBe(DISCLAIMER);
    expect(
      screen
        .getAllByRole("button")
        .map((b) => b.textContent)
        .slice(0, 2),
    ).toEqual(["Retest new version", "Download evidence"]);
  });

  it("uses the word 'secure' exactly once, has no score, no upload control and no mockup marker", async () => {
    await open();
    for (const r of rows()) fireEvent.click(r);
    fireEvent.click(button("Retest new version"));
    const all = document.body.textContent ?? "";
    expect(all.match(/secure/gi)).toHaveLength(1);
    expect(all).not.toMatch(/score|time.to.hack|upload|mockup/i);
    // The search box and the result filter are the only controls; nothing takes a file.
    expect(document.querySelector("input[type=file], textarea, form")).toBeNull();
  });

  it("lists collapsed rows with the plain sentence, control line and a badge for every label", async () => {
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
    expect(
      vectors.getByText("acme-sign 1.4.2 accepted 3 forged signatures out of 484 official cases, so it failed."),
    ).not.toBeNull();
    // The technical summary waits inside the opened result.
    expect(vectors.queryByText(/^3 of 484 official cases wrong\. Headline: case 168/)).toBeNull();
    expect(screen.queryByTestId("technical-summary")).toBeNull();
    expect(screen.queryByTestId("also-noticed")).toBeNull();
    expect(screen.queryByTestId("lab-group")).toBeNull();
    expect(screen.queryByTestId("not-tested")).toBeNull();
    expect(vectors.getByText("Control: a deliberately broken signer failed this test, as expected.")).not.toBeNull();
    expect(screen.queryByTestId("result-detail")).toBeNull();
    // The locked test and its fingerprint are not on the collapsed list.
    expect(document.body.textContent).not.toContain(FINGERPRINT);
    expect(screen.queryByText("Test details, locked before the run")).toBeNull();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
  });

  it("gives Couldn't trust this run the same badge look as Couldn't run", async () => {
    const view = {
      ...lab,
      rows: lab.rows.map((r, i) =>
        i === 0
          ? { ...r, result: result(5, "couldnt_trust", "Couldn't trust this run", "warn", "The control did not fail.") }
          : r,
      ),
    };
    await open(view);
    const badges = screen.getAllByTestId("result-badge");
    expect(label(badges[0]!)).toBe("Couldn't trust this run");
    expect(badges[0]!.className).toBe(badges[4]!.className);
    fireEvent.click(rows()[0]!);
    // No fix is suggested for a run that can't be trusted.
    expect(within(panel()).queryByTestId("suggested-fix")).toBeNull();
  });

  it("opens a result with every section in order, with tags, and closes it again", async () => {
    await open();
    const toggle = rowOf("Official test vectors");
    expect(toggle.getAttribute("aria-selected")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-selected")).toBe("true");

    const detail = within(panel()).getByTestId("result-detail");
    const d = within(detail);
    // The design refactor (26 November 2026): three layers, in this order. The answer card, what it shows and what it
    // doesn't, and one fold that holds every record whole.
    expect(Array.from(detail.children).map((el) => el.getAttribute("data-testid"))).toEqual([
      "result-glance",
      "result-shows",
      "proof-fold",
    ]);

    // Layer 1, the answer: the reviewer's word and what it rests on, the row's plain sentence (word for word: beside
    // the open panel the table is drawn narrow, without it), where it ran, the control in one line, the next step.
    const glance = within(d.getByTestId("result-glance"));
    expect(label(glance.getByTestId("result-badge"))).toBe("Failed");
    expect(text(glance.getByTestId("source-tag"))).toBe("Proven in the lab");
    const plain = glance.getByTestId("result-plain");
    expect(text(plain)).toBe(lab.rows.find((r) => r.title === "Official test vectors")!.result!.plain);
    expect(text(plain).length).toBeGreaterThan(20);
    expect(text(glance.getByTestId("source-line"))).toBe(
      "Run on a copy of acme-sign 1.4.2 on this computer, in demo mode (a plain process on this computer, not isolated). Your live system was not touched.",
    );
    expect(text(glance.getByTestId("control-line"))).toBe(
      "Control: a deliberately broken signer failed this test, as expected.",
    );
    expect(within(toggle).queryByText(text(plain))).toBeNull(); // (the narrow row no longer shows it)
    expect(text(glance.getByTestId("fix-line").querySelector("p"))).toBe("Fix available, code not connected");
    expect(glance.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "View in Fixes",
      "Mark reviewed",
      "Dig deeper",
    ]);
    // Nothing technical is in the answer card.
    expect(glance.queryByTestId("technical-summary")).toBeNull();
    expect(glance.queryByRole("table")).toBeNull();
    expect(glance.queryByTestId("locked-test")).toBeNull();

    // Layer 2, in the open: what this shows, and what it doesn't.
    const shows = within(d.getByTestId("result-shows"));
    expect(shows.getByRole("heading", { level: 4 }).textContent).toBe("What this shows, and what it doesn't");
    expect(shows.getByText(/^It doesn't show whether anyone has used this/)).not.toBeNull();

    // Layer 3, the fold: shut until it is opened, named for a result proven on a copy, and saying what is inside.
    const fold = d.getByTestId("proof-fold") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(fold.getAttribute("data-kind")).toBe("proof");
    expect(text(d.getByTestId("proof-fold-name"))).toBe("Cryptanalysis proof");
    expect(text(d.getByTestId("proof-fold-inside"))).toBe(
      "What happened · The control · The locked test · The run record",
    );
    const opener = d.getByTestId("proof-fold-toggle");
    expect(opener.textContent).toContain("Show");
    fireEvent.click(opener);
    expect(fold.open).toBe(true);
    expect(opener.textContent).toContain("Hide");
    expect(opener.getAttribute("aria-expanded")).toBe("true");
    // Its numbered parts, in order: every record whole.
    const body = within(d.getByTestId("proof-fold-body"));
    expect(body.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual([
      "1What happened",
      "2The control",
      "3Test details, locked before the run",
      "4Run record",
    ]);
    expect(text(body.getByTestId("technical-summary"))).toBe(
      "Technical summary 3 of 484 official cases wrong. Headline: case 168, a signature made of zeros (r=0 and s=0) was accepted.",
    );
    expect(body.getByTestId("proof-part-happened").contains(body.getByRole("table"))).toBe(true);
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
    expect(
      table
        .getAllByRole("row")
        .slice(1)
        .map((r) => within(r).getAllByRole("cell")[0]!.textContent),
    ).toEqual(["168", "171", "364"]);
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
    for (const term of [
      "Question",
      "Method",
      "Inputs",
      "Control",
      "Pass/fail rule",
      "Locked",
      "Fingerprint of these details (SHA-256)",
    ]) {
      expect(lockedBox.getByText(term)).not.toBeNull();
    }
    expect(lockedBox.getByText(/before the run started/)).not.toBeNull();
    expect(d.getByTestId("spec-fingerprint").textContent).toBe(FINGERPRINT);

    // The control's own paragraph is a part of the fold; the one line that points to the fix is in the answer card.
    expect(d.getByTestId("control-outcome").getAttribute("data-outcome")).toBe("as_expected");
    expect(d.getByText(/^The deliberately broken signer got all 310 invalid cases wrong/)).not.toBeNull();
    expect(d.queryByTestId("suggested-fix")).toBeNull();
    expect(d.queryByTestId("research-request")).toBeNull();

    // Opening it again shuts it.
    fireEvent.click(opener);
    expect(fold.open).toBe(false);

    fireEvent.click(toggle);
    expect(screen.queryByTestId("result-detail")).toBeNull();
  });

  it("calls the fold a Technical record for a result observed live, and for one with no tag", async () => {
    await open();
    // The server test was observed on the live server.
    const live = within(show("Old TLS versions")).getByTestId("result-detail");
    expect(text(within(live).getByTestId("source-tag"))).toBe("Observed live");
    expect(within(live).getByTestId("proof-fold").getAttribute("data-kind")).toBe("record");
    expect(text(within(live).getByTestId("proof-fold-name"))).toBe("Technical record");
    // A test that couldn't run has no tag: its fold is a record too, never a proof.
    const none = lab.rows.find((r) => r.result && !r.result.source_tag);
    if (none) {
      const d = within(show(none.title)).getByTestId("result-detail");
      expect(within(d).queryByTestId("source-tag")).toBeNull();
      expect(text(within(d).getByTestId("proof-fold-name"))).toBe("Technical record");
    }
    // No fold is ever named a proof unless its result rests on a run on a copy.
    for (const r of lab.rows.filter((row) => row.result)) {
      const d = within(show(r.title)).getByTestId("result-detail");
      const proven = r.result!.source_tag?.key === "lab";
      expect(text(within(d).getByTestId("proof-fold-name"))).toBe(proven ? "Cryptanalysis proof" : "Technical record");
    }
  });

  it("does not turn a non-https source into a link", async () => {
    const meta = [{ label: "Vectors", value: "somewhere", tag: null, href: "javascript:alert(1)" }];
    await open(withResult(lab, 13, { run_record: { ...lab.rows[2]!.result!.run_record, meta } }));
    expand("Official test vectors");
    expect(screen.getByText("somewhere")).not.toBeNull();
    // (the one link in the panel is the app's own way to the result's place on the map; the source is none)
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("data-testid"))).toEqual(["show-on-the-map"]);
    expect(within(screen.getByTestId("proof-fold")).queryByRole("link")).toBeNull();
  });

  it("puts Mark reviewed and Dig deeper on every opened result", async () => {
    await open();
    // One result opens at a time, in the panel; every one of the five has both buttons.
    for (const r of rows()) {
      fireEvent.click(r);
      expect(screen.getAllByTestId("result-detail")).toHaveLength(1);
      expect(screen.getAllByRole("button", { name: "Mark reviewed" })).toHaveLength(1);
      expect(screen.getAllByRole("button", { name: "Dig deeper" })).toHaveLength(1);
      expect(screen.getAllByText("What this shows, and what it doesn't")).toHaveLength(1);
    }
  });

  it("Mark reviewed calls the API and then shows its recorded state", async () => {
    const reviewed = withResult(lab, 13, {
      reviewed: { at: "2026-11-11T01:46:02.000Z", text: "You marked this result as reviewed." },
    });
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
    for (const term of ["Finding", "Question", "Evidence attached", "Saved"])
      expect(box.getByText(term)).not.toBeNull();
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
        i === 1
          ? {
              ...r,
              control_line: "",
              result: null,
              result_status: { status: "not_run", status_text: "Not run yet", progress: null },
            }
          : r,
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
    expect(labCalls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);

    fireEvent.click(items[0]!);
    await screen.findByTestId("lab-columns");
    const call = fetchMock.mock.calls.find(([url]) => String(url) === "/api/plans/1/retest");
    // the backend names each version's library (phase 4c), and the screen sends it back
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ version: "1.4.3", component: "acme-sign" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("lists every library's versions in the order sent and sends the chosen library with the version", async () => {
    const fetchMock = await open(multiLibraryLab, { "POST /api/plans/1/retest": { body: beforeAfter } });
    fireEvent.click(button("Retest new version"));
    const items = within(screen.getByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.querySelector("span")?.textContent)).toEqual([
      "python-ecdsa 0.13.3",
      "python-ecdsa 0.13.2",
      "elliptic 6.5.7",
      "elliptic 6.5.6",
    ]);
    fireEvent.click(items[0]!);
    await screen.findByTestId("lab-columns");
    const call = fetchMock.mock.calls.find(([url]) => String(url) === "/api/plans/1/retest");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ version: "0.13.3", component: "python-ecdsa" });
  });

  it("shows before and after side by side, with rows still expandable", async () => {
    await open(beforeAfter);
    expect(
      Array.from(screen.getByTestId("lab-columns").children).map(
        (c) => c.firstElementChild?.firstChild?.textContent ?? c.firstChild?.textContent ?? "",
      ),
    ).toEqual(["Test", "Before: acme-sign 1.4.2", "After: acme-sign 1.4.3"]);
    expect(text(screen.getByTestId("lab-subline"))).toMatch(
      /^Before and after: the same five locked tests, run on acme-sign 1\.4\.2 and then on acme-sign 1\.4\.3\./,
    );

    const vectors = within(rowOf("Official test vectors"));
    expect(vectors.getByText("Control failed as expected in both runs.")).not.toBeNull();
    const before = within(vectors.getByTestId("lab-cell-before"));
    const after = within(vectors.getByTestId("lab-cell-after"));
    expect(label(before.getByTestId("result-badge"))).toBe("Failed");
    expect(
      before.getByText("acme-sign 1.4.2 accepted 3 forged signatures out of 484 official cases, so it failed."),
    ).not.toBeNull();
    expect(
      before.queryByText("3 of 484 official cases wrong (168, 171, 364), all from one missing range check."),
    ).toBeNull();
    expect(label(after.getByTestId("result-badge"))).toBe("Passed");
    expect(after.getByText("484 of 484 official cases right.")).not.toBeNull();

    const speed = within(rowOf("Speed and size"));
    expect(label(within(speed.getByTestId("lab-cell-before")).getByTestId("result-badge"))).toBe("Measured");
    expect(label(within(speed.getByTestId("lab-cell-after")).getByTestId("result-badge"))).toBe(
      "No slowdown beyond measured noise",
    );

    expand("Official test vectors");
    const details = within(panel()).getAllByTestId("result-detail");
    expect(details.map((d) => within(d).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "After: acme-sign 1.4.3, the merged fix (commit c41f0d2)",
      "Before: acme-sign 1.4.2, the bundled demo version",
    ]);
    expect(details.map((d) => d.getAttribute("data-run-id"))).toEqual(["23", "7"]);
    expect(within(panel()).getAllByRole("button", { name: "Mark reviewed" })).toHaveLength(2);
    expect(within(panel()).getAllByRole("button", { name: "Dig deeper" })).toHaveLength(2);
  });

  it("shows the speed table with both versions, the noise band and the for-scale-only note", async () => {
    await open(beforeAfter);
    expand("Speed and size");
    const after = within(within(panel()).getAllByTestId("result-detail")[0]!);
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
    await screen.findAllByTestId("evidence-row");
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
    expect(labCalls(fetchMock)).toHaveLength(3);
  }, 12000);
});

describe("Evidence Lab, the line that points to a fix", () => {
  const withLine = (line: FixLine) => withResult(lab, 13, { fix_line: line });
  const lineOf = (title: string) => within(show(title)).getByTestId("fix-line");
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
      expect(within(show(title)).queryByTestId("suggested-fix")).toBeNull();
      expect(within(show(title)).queryByText("Suggested fix")).toBeNull();
    }

    fireEvent.click(within(lineOf("Old TLS versions")).getByRole("button", { name: "View in Fixes" }));
    fireEvent.click(within(lineOf("Official test vectors")).getByRole("button", { name: "View in Fixes" }));
    expect(viewed).toEqual(["fix-tls-versions", "fix-ecdsa-range-check"]);
    // The line only links: it calls nothing itself.
    expect(labCalls(fetchMock)).toEqual(["GET /api/plans/1/lab"]);
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
    expect(
      within(el)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["View in Fixes"]);
  });

  it("never calls a fix ready in a line whose proof has not passed", async () => {
    for (const state of ["not_connected", "proving", "failed", "text_only"] as const) {
      expect(`${fixLines[state].lead} ${fixLines[state].rest}`).not.toMatch(/ready/i);
    }
    await open(withLine(fixLines.failed));
    expand("Official test vectors");
    expect(text(panel())).not.toMatch(/ready/i);
  });

  it("keeps the Suggested fix box on a result that has no line", async () => {
    await open();
    expand("Certificate strength");
    const row = within(panel());
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
    await screen.findAllByTestId("evidence-row");
    expand("Official test vectors");
    expect(words(lineOf("Official test vectors"))).toBe("Fix prepared: 3 lines added and 1 removed, proof running");
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Download evidence").disabled).toBe(true);
    expect(screen.getAllByTestId("blocked-reason").map((p) => p.textContent)).toEqual([reason]);
    // A proof is not a retest: the retest progress line stays away.
    expect(screen.queryByTestId("retest-progress")).toBeNull();

    await waitFor(
      () => expect(words(lineOf("Official test vectors"))).toBe("Fix ready: 3 lines added and 1 removed, proof passed"),
      {
        timeout: 5000,
      },
    );
    // The opened row stayed open, and the buttons are back.
    expect(button("Retest new version").disabled).toBe(false);
    expect(button("Download evidence").disabled).toBe(false);
    expect(screen.queryByTestId("blocked-reason")).toBeNull();
    await new Promise((r) => setTimeout(r, 1300));
    expect(labCalls(fetchMock)).toHaveLength(3);
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
    await screen.findAllByTestId("evidence-row");
    expect(provingUnseen.rows.some((r) => r.result?.fix_line?.busy || r.after?.fix_line?.busy)).toBe(false);
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Download evidence").disabled).toBe(true);
    expect(screen.getAllByTestId("blocked-reason").map((p) => p.textContent)).toEqual([reason]);

    await waitFor(() => expect(button("Retest new version").disabled).toBe(false), { timeout: 5000 });
    expect(button("Download evidence").disabled).toBe(false);
    expect(screen.queryByTestId("blocked-reason")).toBeNull();
    await new Promise((r) => setTimeout(r, 1300));
    expect(labCalls(fetchMock)).toHaveLength(3);
  }, 12000);
});

describe("Evidence Lab, which code each result ran on", () => {
  it("says it under each column heading, in one sentence under the subline and above the opened details", async () => {
    await open(beforeAfter);
    const columns = Array.from(screen.getByTestId("lab-columns").children);
    expect(columns.map((c) => text(c))).toEqual([
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
    const details = within(panel()).getAllByTestId("result-detail");
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
    const detail = within(panel()).getByTestId("result-detail");
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
    expect(labCalls(fetchMock)).toEqual(["GET /api/plans/1/lab", "POST /api/plans/1/evidence"]);
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
      "POST /api/plans/1/evidence": {
        status: 409,
        body: { error: { message: "Wait for the tests to finish.", line: null, field: null } },
      },
    });
    fireEvent.click(button("Download evidence"));
    expect(text(await screen.findByRole("alert"))).toContain("Wait for the tests to finish.");
    expect(screen.queryByTestId("download-status")).toBeNull();
  });
});

describe("Evidence Lab, grouped by target", () => {
  it("draws one heading per group, with its note, and each group's rows under it", async () => {
    await open(groupedLab);
    const sections = screen.getAllByTestId("lab-group");
    expect(sections.map((g) => within(g).getByRole("heading", { level: 2 }).textContent)).toEqual([
      "Server: localhost:8444",
      "Server: localhost:8445",
      "Signing program: acme-sign 1.4.2",
    ]);
    expect(screen.getAllByTestId("lab-group-note").map((n) => n.textContent)).toEqual([
      "A local test server started for this file (Demo data).",
    ]);
    expect(within(sections[1]!).getByTestId("lab-group-note")).not.toBeNull();
    expect(
      sections.map((g) => Array.from(g.querySelectorAll("[data-kind]")).map((r) => r.getAttribute("data-kind"))),
    ).toEqual([["tls_versions", "certificate"], ["tls_versions", "certificate"], ["official_vectors"]]);
    expect(
      within(sections[0]!).getByText("localhost:8444 refused every version older than TLS 1.3, so it passed."),
    ).not.toBeNull();
  });

  it("shows the Not tested, and why box with one line per item, calmly and not as an error", async () => {
    await open(groupedLab);
    const box = screen.getByTestId("not-tested");
    expect(within(box).getByRole("heading").textContent).toBe("Not tested, and why");
    expect(
      within(box)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([
      "acme-sign 9.9: its tests can't run. Only our own demo components can run in this version.",
      "localhost:8446: Post-quantum readiness wasn't added to the plan.",
    ]);
    expect(box.getAttribute("role")).toBeNull();
    expect(box.className).not.toMatch(/amber|red/);
  });

  it("shows an Also noticed note under the row header, outside the badge, before anything is opened", async () => {
    await open(groupedLab);
    const notes = screen.getAllByTestId("also-noticed");
    expect(notes).toHaveLength(1);
    const certRow = within(screen.getAllByTestId("lab-group")[1]!).getAllByTestId("evidence-row")[1]!;
    expect(certRow.contains(notes[0]!)).toBe(true);
    expect(text(notes[0])).toBe(
      "Also noticed: The handshakes for this check showed the server also accepts TLS 1.0 and TLS 1.1.",
    );
    expect(within(certRow).getByTestId("lab-row-header").contains(notes[0]!)).toBe(false);
    expect(notes[0]!.className).not.toMatch(/amber|green|red|emerald/);
    expect(within(certRow).getAllByTestId("result-badge").map(label)).toEqual(["Passed"]);
  });

  it("groups the before/after view the same way, with the plain line in each cell and the notes of the newer result", async () => {
    const view: LabView = {
      ...groupedLab,
      view: "before_after",
      columns: beforeAfter.columns,
      rows: groupedLab.rows.map((r) => ({
        ...r,
        after: r.result
          ? { ...r.result, run_id: r.result.run_id + 50, plain: `After: ${r.result.plain}`, also_noticed: [] }
          : null,
      })),
    };
    await open(view);
    const sections = screen.getAllByTestId("lab-group");
    expect(sections).toHaveLength(3);
    expect(screen.getByTestId("lab-columns")).not.toBeNull();
    const row = within(within(sections[1]!).getAllByTestId("evidence-row")[0]!);
    expect(within(row.getByTestId("lab-cell-before")).getByText(/^localhost:8445 accepted TLS 1\.0/)).not.toBeNull();
    expect(
      within(row.getByTestId("lab-cell-after")).getByText(/^After: localhost:8445 accepted TLS 1\.0/),
    ).not.toBeNull();
    // The newer result has no notes, so none is shown.
    expect(screen.queryByTestId("also-noticed")).toBeNull();
    expect(screen.getByTestId("not-tested")).not.toBeNull();
  });
});

describe("Evidence Lab, published advisories", () => {
  const openVectors = async (change: Record<string, unknown> | null) => {
    await open(change ? withResult(lab, 13, change) : lab);
    expand("Official test vectors");
    return within(within(panel()).getByTestId("result-detail"));
  };

  it("draws the title, the tag, the id, the text, a safe link and the covered sentence", async () => {
    const detail = await openVectors({ advisories });
    // It is a numbered part of the fold: the part's heading carries the title and the tag.
    const part = within(detail.getByTestId("proof-part-advisories"));
    expect(part.getByText("Published advisories for this version")).not.toBeNull();
    expect(part.getByText("from the advisory, not a result")).not.toBeNull();
    expect(text(detail.getByTestId("proof-fold-inside"))).toContain("The advisory");
    const box = within(detail.getByTestId("advisories"));
    expect(box.getByText("CVE-2022-21449")).not.toBeNull();
    expect(box.getByText(/Java 15 to 18 accept a blank ECDSA signature/)).not.toBeNull();
    expect(
      box.getByText("The Independent exam and the Attacker tricks test both try a blank signature."),
    ).not.toBeNull();
    const link = box.getByRole("link", { name: "OpenJDK advisory, 19 April 2022" });
    expect(link.getAttribute("href")).toBe("https://openjdk.org/groups/vulnerability/advisories/2022-04-19");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("draws no box when advisories is null or missing", async () => {
    expect((await openVectors({ advisories: null })).queryByTestId("advisories")).toBeNull();
    cleanup();
    expect((await openVectors(null)).queryByTestId("advisories")).toBeNull();
  });

  it("shows the link text without an anchor when the address is not https", async () => {
    const bad = { ...advisories, items: [{ ...advisories.items[0]!, href: "http://example.com/x" }] };
    const detail = await openVectors({ advisories: bad });
    const box = within(detail.getByTestId("advisories"));
    expect(box.getByText(/OpenJDK advisory, 19 April 2022/)).not.toBeNull();
    expect(box.queryByRole("link")).toBeNull();
  });
});

describe("Evidence Lab, an advisory check (phase 5c)", () => {
  const title = advisoryCheckRow.title;
  const withAdvisoryCheck: LabView = { ...lab, rows: [...lab.rows, advisoryCheckRow] };

  it("lists the check like any other test: the reviewer's label, its plain sentence and its control line", async () => {
    await open(withAdvisoryCheck);
    expect(rows()).toHaveLength(6);
    const row = within(rowOf(title));
    expect(label(row.getByTestId("result-badge"))).toBe(advisoryCheckRow.result!.label);
    expect(row.getByText(advisoryCheckRow.result!.plain)).not.toBeNull();
    expect(row.getByText(advisoryCheckRow.control_line)).not.toBeNull();
  });

  it("shows the advisory the check is for in the advisories box: its id, the publisher's words under their tag, a safe link and what the check covers", async () => {
    await open(withAdvisoryCheck);
    expand(title);
    const detail = within(within(panel()).getByTestId("result-detail"));
    const advisories = advisoryCheckRow.result!.advisories!;
    const part = within(detail.getByTestId("proof-part-advisories"));
    expect(part.getByText(advisories.title)).not.toBeNull();
    expect(part.getByText(advisories.tag)).not.toBeNull();
    const box = within(detail.getByTestId("advisories"));
    const items = box.getAllByTestId("advisory-item");
    expect(items).toHaveLength(advisories.items.length);
    const item = advisories.items[0]!;
    expect(within(items[0]!).getByText(item.id).className).toContain("font-mono");
    expect(text(items[0])).toContain(item.text);
    const link = within(items[0]!).getByRole("link", { name: item.link });
    expect(link.getAttribute("href")).toBe(item.href);
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(within(items[0]!).getByText(item.covered)).not.toBeNull();
    // The box is information from the advisory: it carries no result chip of its own.
    expect(detail.getByTestId("advisories").querySelector('[data-testid="result-badge"]')).toBeNull();
    // The result beside it is the reviewer's, from the run: its locked test names the pack and the design it came from.
    expect(text(detail.getByTestId("locked-test"))).toContain("test pack 2026.11.1 (design fingerprint 7b06a70535ac)");
    expect(text(detail.getByTestId("control-outcome"))).toContain(advisoryCheckRow.result!.control.text);
  });

  it("offers the fix the failed check led to, with View in Fixes", async () => {
    await open(withAdvisoryCheck);
    expand(title);
    fireEvent.click(
      within(within(panel()).getByTestId("result-detail")).getByRole("button", {
        name: advisoryCheckRow.result!.fix_line!.button!,
      }),
    );
    expect(viewed).toEqual([advisoryCheckRow.result!.fix_line!.fix_id]);
  });
});

describe("Evidence Lab, table, panel, search and cards", () => {
  it("opens a row in the panel from the keyboard, and Escape or the close button shuts it", async () => {
    await open();
    fireEvent.keyDown(rowOf("Official test vectors"), { key: "Enter" });
    expect(within(panel()).getByTestId("result-detail")).not.toBeNull();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expand("Official test vectors");
    fireEvent.click(within(panel()).getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("counts rows by their badge code in the summary cards, and filters by search and result", async () => {
    await open();
    const card = (key: string) =>
      within(screen.getAllByTestId("summary-card").find((c) => c.getAttribute("data-card") === key)!).getAllByText(
        /^\d+$/,
      )[0]!.textContent;
    expect([card("with-result"), card("failed"), card("passed"), card("couldnt-run")]).toEqual(["5", "2", "1", "1"]);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "speed" } });
    expect(rows()).toHaveLength(1);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "failed" } });
    expect(rows()).toHaveLength(2);
  });
});

// ---- Phase 5b: Evidence in the four work groups ----

const opensslRow: LibraryEvidenceRow = {
  id: "library-row-openssl",
  row_id: "row-openssl",
  name: "OpenSSL 3.0.22",
  via_words: "Used by nginx 1.24 (localhost:8461)",
  answers_short: "No to all three",
  blocks: [
    {
      system: "localhost:8461",
      track: "kex",
      track_words: "key exchange",
      fix_id: "dependency-openssl",
      system_key: "server:localhost:8461",
      words: "Blocks key exchange on localhost:8461",
    },
  ],
  measured: false,
  state: "done",
  lookups: [
    {
      question: "ml_kem_768",
      question_words: "ML-KEM-768",
      title: "OpenSSL 3.5 release notes",
      url: "https://openssl-library.org/news/openssl-3.5-notes/",
      quote: "Added ML-KEM.",
      checked: "2026-10-01",
      repeat: false,
    },
  ],
  cells: [
    {
      question: "ml_kem_768",
      answer: "no",
      answer_words: "No",
      tone: "fail",
      label: "release_notes",
      label_words: "Release notes say",
      reason: "OpenSSL added ML-KEM in 3.5.0.",
      first_version: "3.5.0",
      first_version_words: "First version that can: 3.5.0",
      state: "not_measured",
      state_words: "Not measured",
      agreement: null,
      agreement_words: null,
      no_reason: "OpenSSL added this in 3.5.0; you have 3.0.22.",
    },
  ],
};

const groupedChecks = { ...checksView, libraries: [opensslRow] };
const withGroups = (extra: Routes = {}) => ({ "GET /api/plans/1/checks": { body: groupedChecks }, ...extra });
// 20 November 2026: the groups are tabs, one group's table at a time. A group's section is looked at on its own tab.
const tabOf = (key: string) => screen.getAllByTestId("group-tab").find((t) => t.getAttribute("data-group") === key)!;
const shownGroups = () => screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"));
const groupOf = (key: string) => {
  if (tabOf(key).getAttribute("aria-selected") !== "true") fireEvent.click(tabOf(key));
  return screen.getAllByTestId("group-section").find((g) => g.getAttribute("data-group") === key)!;
};
/** Evidence with the four groups: the lab's results and the checks. */
async function openGrouped(
  routes: Routes = withGroups(),
  props: Partial<Parameters<typeof EvidenceLabScreen>[0]> = {},
) {
  const fetchMock = mockApi({ "GET /api/plans/1/lab": { body: lab }, ...routes });
  render(<EvidenceLabScreen planId={1} onViewFix={(fixId) => viewed.push(fixId)} {...props} />);
  await screen.findAllByTestId("group-section");
  return fetchMock;
}

describe("Evidence, the four work groups", () => {
  it("has the four groups as tabs, opens on the first with something in it, and puts today's results under Crypto tests", async () => {
    await openGrouped();
    const tabs = within(screen.getByRole("tablist", { name: "Work groups" })).getAllByRole("tab");
    // A tab's name is the group's; beside it, how many rows it holds and how many of them are findings, in the rows'
    // own word (26 November 2026). The counts are the page's own, from the rows it draws under that tab.
    expect(tabs.map((t) => t.firstChild!.textContent)).toEqual([
      "Verification",
      "Crypto tests",
      "Migration",
      "Dependencies",
    ]);
    expect(
      tabs.map((t) => [
        within(t).getByTestId("group-tab-total").textContent,
        within(t).queryByTestId("group-tab-findings")?.textContent ?? null,
      ]),
    ).toEqual(
      tabs.map((t) => {
        const key = t.getAttribute("data-group")!;
        const group = groupedChecks.groups.find((g) => g.key === key)!;
        const results =
          key === "encryption"
            ? lab.rows.map((r) => r.result)
            : key === "dependencies"
              ? groupedChecks.libraries.map(() => null)
              : group.rows.map((r) => r.result);
        const failed = results.filter((r) => r?.tone === "fail");
        const words = Array.from(new Set(failed.map((r) => r!.label.toLowerCase())));
        return [
          String(results.length),
          failed.length > 0 ? `✕ ${failed.length} ${words.length === 1 ? words[0] : "findings"}` : null,
        ];
      }),
    );
    // (the counts are not part of a tab's name: a screen reader hears them as its description)
    expect(screen.getByRole("tab", { name: "Verification" }).getAttribute("aria-describedby")).toMatch(/-total$/);
    // One group at a time: the first with something in it.
    expect(shownGroups()).toEqual(["verification"]);
    expect(screen.queryAllByTestId("evidence-row")).toHaveLength(0);
    // Verification: one row per claim checked, with Verify's own word.
    expect(
      within(groupOf("verification"))
        .getAllByTestId("check-row")
        .map((r) => r.getAttribute("data-check")),
    ).toEqual(["claim-1", "claim-2", "claim-3"]);
    // Crypto tests holds the results table as it was, under its question.
    expect(within(groupOf("encryption")).getAllByTestId("evidence-row")).toHaveLength(rows().length);
    expect(shownGroups()).toEqual(["encryption"]);
    expect(within(groupOf("encryption")).getByRole("heading", { level: 2, name: "Crypto tests" })).not.toBeNull();
    expect(within(groupOf("encryption")).getByTestId("group-question").textContent).toBe(
      "Is the cryptography built right?",
    );
    // Dependencies: one row per library with its answers as Dependencies words them, and its Blocks marker.
    const lib = within(groupOf("dependencies")).getByTestId("library-row");
    expect(text(lib)).toContain("OpenSSL 3.0.22");
    expect(text(lib)).toContain("No to all three");
    expect(within(lib).getByTestId("blocks-marker").textContent).toBe("Blocks key exchange on localhost:8461");
    // An empty group says why.
    expect(within(groupOf("migration")).getByTestId("group-empty").textContent).toBe(
      "Nothing measured yet. Measure status is on Migration.",
    );
    expect(screen.queryByRole("combobox", { name: "Group" })).toBeNull();
  });

  it("opens the tab the address names, the tab of the item it names, and Crypto tests for a Result filter (that table's own)", async () => {
    await openGrouped(withGroups(), { group: "dependencies" });
    expect(shownGroups()).toEqual(["dependencies"]);
    cleanup();
    await openGrouped(withGroups(), { openItem: `test-${lab.rows[0]!.item_id}` });
    expect(shownGroups()).toEqual(["encryption"]);
    cleanup();
    await openGrouped(withGroups(), { openItem: opensslRow.id });
    expect(shownGroups()).toEqual(["dependencies"]);
    expect(await screen.findByTestId("library-panel")).not.toBeNull();
    cleanup();
    await openGrouped(withGroups(), { result: "failed" });
    expect(shownGroups()).toEqual(["encryption"]);
  });

  it("a search says on each tab how many rows match; the Result filter counts on Crypto tests only, where it filters", async () => {
    const said: { result?: string | null; group?: string | null }[] = [];
    await openGrouped(withGroups(), { onFilters: (f) => said.push(f) });
    const matches = () =>
      Object.fromEntries(
        screen
          .getAllByTestId("group-tab")
          .map((t) => [t.getAttribute("data-group"), within(t).queryByTestId("group-tab-matches")?.textContent]),
      );
    expect(screen.queryAllByTestId("group-tab-matches")).toHaveLength(0);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search results" }), { target: { value: "openssl" } });
    expect(matches()).toEqual({ verification: "0", encryption: expect.any(String), migration: "0", dependencies: "1" });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search results" }), { target: { value: "" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "failed" } });
    expect(matches()).toEqual({
      verification: undefined,
      encryption: expect.any(String),
      migration: undefined,
      dependencies: undefined,
    });
    // the filter goes to the address with the open tab, so the tab stays where it is
    expect(said.at(-1)).toEqual({ result: "failed", group: "verification" });
    expect(shownGroups()).toEqual(["verification"]);
  });

  it("a claim's panel links to where it started, with its every run; it closes when another tab opens; the test panel is unchanged", async () => {
    const detail = { ...retestDetail, check: groupedChecks.groups[0]!.rows[0]!, runs: [retestDetail.runs[1]!] };
    await openGrouped(withGroups({ "GET /api/plans/1/checks/claim-1": { body: detail } }));
    fireEvent.click(within(groupOf("verification")).getAllByTestId("check-row")[0]!);
    const checkPanel = within(await screen.findByTestId("check-panel"));
    expect((await checkPanel.findByTestId("open-in")).textContent).toBe("Open where it started");
    expect(checkPanel.getByTestId("earlier-runs")).not.toBeNull();
    // Another tab: the claim belongs to Verification, so its panel closes.
    groupOf("encryption");
    expect(screen.queryByTestId("check-panel")).toBeNull();
    // A result row of Crypto tests shows the test panel as before.
    fireEvent.click(rows()[0]!);
    expect(within(panel()).getByRole("button", { name: "Mark reviewed" })).not.toBeNull();
  });

  it("a panel of another tab closes when the tab changes from outside the page (the sidebar's link, Back)", async () => {
    mockApi({ "GET /api/plans/1/lab": { body: lab }, ...withGroups() });
    const { rerender } = render(<EvidenceLabScreen planId={1} onViewFix={() => undefined} />);
    await screen.findAllByTestId("group-section");
    fireEvent.click(within(groupOf("dependencies")).getByTestId("library-row"));
    expect(await screen.findByTestId("library-panel")).not.toBeNull();
    rerender(<EvidenceLabScreen planId={1} onViewFix={() => undefined} group="encryption" />);
    expect(shownGroups()).toEqual(["encryption"]);
    expect(screen.queryByTestId("library-panel")).toBeNull();
    // a result of Crypto tests, then the sidebar's Verification: that panel closes too
    fireEvent.click(rows()[0]!);
    expect(screen.getByTestId("detail-panel")).not.toBeNull();
    rerender(<EvidenceLabScreen planId={1} onViewFix={() => undefined} group="verification" />);
    expect(screen.queryByTestId("lab-row")).toBeNull();
  });

  it("a library's panel shows each answer with its label and reason, its source, and Open in Dependencies", async () => {
    await openGrouped();
    fireEvent.click(within(groupOf("dependencies")).getByTestId("library-row"));
    const lib = within(await screen.findByTestId("library-panel"));
    expect(lib.getByText("OpenSSL added this in 3.5.0; you have 3.0.22.")).not.toBeNull();
    expect(lib.getAllByText("Release notes say").length).toBeGreaterThan(0);
    expect(lib.getByRole("link", { name: "https://openssl-library.org/news/openssl-3.5-notes/" })).not.toBeNull();
    expect(lib.getByTestId("open-in").textContent).toBe("Open in Dependencies");
  });

  it("says it is loading until the checks are in, and shows the test results by themselves if they can't be read", async () => {
    let answer: (r: Response) => void = () => {};
    const late = new Promise<Response>((resolve) => (answer = resolve));
    const fetchMock = mockApi({ "GET /api/plans/1/lab": { body: lab } });
    const answered = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, init) =>
      String(input) === "/api/plans/1/checks" ? late : answered(input, init),
    );
    render(screenUnderTest());
    await screen.findByTestId("page-header");
    await waitFor(() => expect(calls(fetchMock)).toContain("GET /api/plans/1/checks"));
    expect(screen.queryAllByTestId("evidence-row")).toHaveLength(0);
    expect(screen.queryAllByTestId("group-tab")).toHaveLength(0);
    answer(
      new Response(JSON.stringify({ detail: "no" }), { status: 500, headers: { "Content-Type": "application/json" } }),
    );
    expect(await screen.findAllByTestId("evidence-row")).toHaveLength(lab.rows.length);
  });
});

describe("Evidence, the compact row (phase 5b)", () => {
  it("beside the open panel, a row keeps its test's name and its whole fix line, never half of it", async () => {
    await open(withResult(lab, 13, { fix_line: fixLines.not_connected }));
    fireEvent.click(rows()[1]!);
    expect(screen.getAllByTestId("data-table")[0]!.getAttribute("data-compact")).toBe("true");
    const lines = screen.getAllByTestId("compact-fix-line").map((l) => l.textContent);
    expect(lines).toContain("Fix available, code not connected");
    expect(lines.every((l) => !/[,:]$/.test((l ?? "").trim()))).toBe(true);
  });
});

// 22 November 2026: where each result came from. One tag per row beside the reviewer's word: a server test is read
// live, a program's test is run on a copy here, and a test that couldn't run has none.
describe("Evidence, where each result came from", () => {
  it("draws one tag beside each row's result, and none for a test that couldn't run", async () => {
    const fetchMock = await open();
    const tagOf = (title: string) =>
      within(rowOf(title))
        .queryAllByTestId("source-tag")
        .map((t) => t.getAttribute("data-source"));
    expect(tagOf("Old TLS versions")).toEqual(["live"]);
    expect(tagOf("Certificate strength")).toEqual(["live"]);
    expect(tagOf("Official test vectors")).toEqual(["lab"]);
    expect(tagOf("Speed and size")).toEqual(["lab"]);
    expect(tagOf("Post-quantum readiness")).toEqual([]);
    expect(within(rowOf("Old TLS versions")).getByTestId("source-tag").textContent).toBe("Observed live");
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("lists the results in parts, by what each rests on: the tag is said once at the head of its part, and every row is still there", async () => {
    await open();
    const parts = screen.getAllByTestId("table-part");
    const titles = (part: HTMLElement) =>
      within(part)
        .getAllByTestId("evidence-row")
        .map((r) => within(r).getByTestId("lab-row-header").firstChild!.textContent);
    const byKey = Object.fromEntries(parts.map((p) => [p.getAttribute("data-part"), p]));
    // Observed on the server, and tested on a copy: two parts, each named, with its tag and the tag's own line.
    expect(within(byKey.live!).getByTestId("table-part-title").textContent).toBe("On your systems");
    expect(within(byKey.live!).getByTestId("table-part-tag").textContent).toBe("Observed live");
    expect(titles(byKey.live!)).toEqual(["Old TLS versions", "Certificate strength"]);
    expect(within(byKey.lab!).getByTestId("table-part-title").textContent).toBe("On copies on this computer");
    expect(within(byKey.lab!).getByTestId("table-part-tag").textContent).toBe("Proven in the lab");
    expect(titles(byKey.lab!)).toContain("Official test vectors");
    // A test that couldn't run rests on nothing: it sits in the last part, which has no tag at its head.
    expect(parts[parts.length - 1]!.getAttribute("data-part")).toBe("none");
    expect(within(byKey.none!).getByTestId("table-part-title").textContent).toBe("No result yet");
    expect(within(byKey.none!).queryByTestId("table-part-tag")).toBeNull();
    expect(titles(byKey.none!)).toEqual(["Post-quantum readiness"]);
    // The parts are headings, not a filter: every row of the plan is on the page, once.
    expect(parts.flatMap(titles)).toHaveLength(lab.rows.length);
    // On a row the tag is kept for a screen reader, which reads a row by itself; the eye reads it at the head.
    expect(within(rowOf("Old TLS versions")).getByTestId("source-tag").className).toBe("sr-only");
  });
});

// 22 November 2026: a library on Evidence's Dependencies tab. Its answers taken together give its one tag (release notes:
// Published), and each answer in its panel has the tag of its own label, which keeps its words in that tag's look.
describe("Evidence, where a library's answers came from", () => {
  const tagged: LibraryEvidenceRow = {
    ...opensslRow,
    source_tag: published(),
    cells: (opensslRow.cells ?? []).map((c) => ({ ...c, source_tag: published() })),
  };

  it("tags the library's row once, and each answer in its panel by its own label", async () => {
    await openGrouped(
      { "GET /api/plans/1/checks": { body: { ...checksView, libraries: [tagged] } } },
      { openItem: tagged.id },
    );
    const libraryPanel = await screen.findByTestId("library-panel");
    const row = within(groupOf("dependencies"))
      .getAllByTestId("source-tag")
      .filter((t) => !libraryPanel.contains(t));
    expect(row.map((t) => t.textContent)).toEqual(["Published"]);
    const inPanel = within(libraryPanel).getAllByTestId("source-tag");
    expect(inPanel.map((t) => t.getAttribute("data-source"))).toEqual(["published"]);
    // the source the release notes are quoted from keeps its words and takes Published's look
    const sources = within(within(libraryPanel).getByRole("region", { name: "Sources" })).getAllByText(
      "Release notes say",
    );
    expect(sources.map((t) => t.getAttribute("data-source"))).toEqual(["published"]);
  });
});
