import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FixStatusKey, FixesView } from "../api";
import { FixesScreen } from "../components/FixesScreen";
import { StatusChip } from "../components/fixes/parts";
import {
  CODE_FIX,
  ONE_LOGIN,
  PROOF_FINGERPRINT,
  SERVER_LINE,
  SERVER_LINE_UNPROVEN,
  TLS_FIX,
  fixesViews,
  noFixes,
  tlsSuggestion,
  withCodeFix,
} from "./fixesFixtures";
import { DISCLAIMER, calls, lab, mockApi, text } from "./fixtures";

type Routes = Parameters<typeof mockApi>[0];

const FIXES = "/api/plans/1/fixes";
const FIX = `${FIXES}/${CODE_FIX}`;
const refusal = (message: string) => ({ status: 409, body: { error: { message, line: null, field: null } } });

/** How often "Retest now" told the app that the retest has started. */
let handedOver = 0;
beforeEach(() => {
  handedOver = 0;
});

/** Holds the selected fix, as the app does. */
function Harness({ start }: { start: string | null }) {
  const [selected, setSelected] = useState(start);
  return <FixesScreen planId={1} selectedId={selected} onSelect={setSelected} onRetestStarted={() => (handedOver += 1)} />;
}

async function open(view: FixesView, routes: Routes = {}, start: string | null = null) {
  const fetchMock = mockApi({ [`GET ${FIXES}`]: { body: view }, ...routes });
  render(<Harness start={start} />);
  await screen.findByTestId("fix-summary");
  return fetchMock;
}

/** The JSON bodies of the POSTs to one address, in order. */
function sent(fetchMock: ReturnType<typeof mockApi>, path: string): unknown[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url) === path && init?.method === "POST")
    .map(([, init]) => (init?.body === undefined ? undefined : JSON.parse(String(init.body))));
}

const summary = () => screen.getByTestId("fix-summary");
const inSummary = () => within(summary());
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const summaryButtons = () => inSummary().queryAllByRole("button") as HTMLButtonElement[];
const listItems = () => within(screen.getByRole("navigation", { name: /^Open findings with a fix/ })).getAllByRole("button");
const selectedTitles = () => listItems().filter((b) => b.getAttribute("aria-current") === "true").map((b) => b.firstElementChild?.textContent);
const sections = () => screen.queryAllByTestId("fix-section");
const section = (key: string) => sections().find((s) => s.getAttribute("data-section") === key)!;
const fold = (key: string) => within(section(key)).getAllByRole("button")[0]!;
const isOpen = (key: string) => fold(key).getAttribute("aria-expanded") === "true";
const status = () => inSummary().getByTestId("fix-status");
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("Fixes, the page", () => {
  it("shows the heading, Demo data, the subline, the disclaimer line and the findings on the left", async () => {
    const fetchMock = await open(fixesViews.ready);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
    const heading = screen.getByRole("heading", { level: 1, name: "Fixes" });
    expect(within(heading.parentElement!).getByText("Demo data")).not.toBeNull();
    expect(screen.getByTestId("fixes-subline").textContent).toBe(
      "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed.",
    );
    expect(screen.getByTestId("disclaimer").textContent).toBe(DISCLAIMER);

    expect(screen.getByRole("navigation", { name: "Open findings with a fix (2)" })).not.toBeNull();
    expect(listItems().map((b) => Array.from(b.children).map((part) => part.textContent))).toEqual([
      ["acme-sign accepts out-of-range signatures", "Ready for review", "Came from 2 failed tests: Official test vectors, Bad signatures"],
      ["Server accepts TLS 1.2", "Text only", "Came from 1 failed test: Old TLS versions"],
    ]);
    expect(listItems().map((b) => b.getAttribute("aria-current"))).toEqual(["true", null]);

    expect(summary().getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(inSummary().getByRole("heading", { level: 2, name: "acme-sign accepts out-of-range signatures" })).not.toBeNull();
    expect(text(inSummary().getByTestId("fix-source"))).toBe(
      "Came from 2 failed tests on signing component acme-sign 1.4.2: Official test vectors and Bad signatures.",
    );
    expect(inSummary().getByText("acme-sign 1.4.2").className).toContain("font-mono");
    // Where the change came from, and that it is demo data, sit beside the status.
    expect(Array.from(status().parentElement!.children).map((chip) => chip.textContent)).toEqual([
      "Ready for review",
      "From a fix template",
      "Demo data",
    ]);
  });

  it("uses the word 'secure' exactly once, and has no score, no upload and nothing to type into", async () => {
    await open(fixesViews.ready);
    for (const key of ["proof", "details"]) fireEvent.click(fold(key));
    const all = document.body.textContent ?? "";
    expect(all.match(/secure/gi)).toHaveLength(1);
    expect(all).not.toMatch(/score|time.to.hack|upload|mockup/i);
    expect(document.querySelector('input:not([type="checkbox"]), textarea, select, form')).toBeNull();
  });

  it("opens on the fix it was asked for, and on the first one when that fix is not in the list", async () => {
    await open(fixesViews.ready, {}, TLS_FIX);
    expect(summary().getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(selectedTitles()).toEqual(["Server accepts TLS 1.2"]);
  });

  it("falls back to the first fix for an id it does not know", async () => {
    await open(fixesViews.ready, {}, "fix-that-is-gone");
    expect(summary().getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(selectedTitles()).toEqual(["acme-sign accepts out-of-range signatures"]);
  });

  it("switches fix on a click in the list, calling nothing", async () => {
    const fetchMock = await open(fixesViews.ready);
    fireEvent.click(listItems()[1]!);
    expect(summary().getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(selectedTitles()).toEqual(["Server accepts TLS 1.2"]);
    expect(sections().map((s) => s.getAttribute("data-section"))).toEqual(["suggestion"]);
    fireEvent.click(listItems()[0]!);
    expect(summary().getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(sections().map((s) => s.getAttribute("data-section"))).toEqual(["change", "proof", "details"]);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("shows one plain sentence, and no list or buttons, when no failed test has a fix", async () => {
    mockApi({ [`GET ${FIXES}`]: { body: noFixes } });
    render(<Harness start={null} />);
    expect((await screen.findByTestId("fixes-empty")).textContent).toBe("No failed test has a fix. Fixes for failed tests show here.");
    expect(screen.getByTestId("disclaimer").textContent).toBe(DISCLAIMER);
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByTestId("fix-summary")).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("says so when the fixes can't be loaded", async () => {
    mockApi({ [`GET ${FIXES}`]: refusal("That plan does not exist.") });
    render(<Harness start={null} />);
    expect(text(await screen.findByRole("alert"))).toBe("The fixes couldn't be loadedThat plan does not exist.");
    expect(screen.getByRole("heading", { level: 1, name: "Fixes" })).not.toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

interface Expected {
  view: FixesView;
  key: FixStatusKey;
  word: string;
  whatLabel: string;
  what: RegExp;
  serverLine: string;
  proofState: string;
  proofBadge: [label: string, tone: string] | null;
  proof: string;
  pullRequest: RegExp | null;
  who: RegExp;
  /** Every button of the summary, in order. */
  buttons: string[];
  /** The ones drawn switched off. */
  off: string[];
  /** The ones with the main-button look. */
  primary: string[];
  note: RegExp | null;
  /** The folded sections: title, the line under it, and whether it starts open. */
  sections: [title: string, line: string, open: boolean][];
}

const PASSED =
  "All 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before.";
const CHANGE: Expected["sections"][number] = ["The change", "3 lines added and 1 removed, in 1 file (acme_sign.py)", true];
const DETAILS: Expected["sections"][number] = ["Technical details", "Repository, branches, commits, fingerprints and mode", false];
const PROOF_PASSED_FOLD: Expected["sections"][number] = [
  "Proof",
  "Passed: all 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before.",
  false,
];
const proven = { whatLabel: "What it fixes", what: /^Adds the missing range check to acme-sign's signature check, so it now rejects/, serverLine: SERVER_LINE };
const unproven = {
  whatLabel: "What it changes",
  what: /^Adds a range check on the two signature numbers \(r and s\) to acme-sign's signature check/,
  serverLine: SERVER_LINE_UNPROVEN,
};
const passed = { proofState: "passed", proofBadge: ["Proof passed", "pass"] as [string, string], proof: PASSED };

const STATUSES: Expected[] = [
  {
    view: fixesViews.not_connected,
    key: "not_connected",
    word: "Code not connected",
    whatLabel: "What it changes",
    what: /^A fix template exists for this failure: .* Connect the code to prepare the change and prove it\.$/,
    serverLine: SERVER_LINE_UNPROVEN,
    proofState: "not_started",
    proofBadge: null,
    proof: "Not started. It starts by itself once the code is connected: every locked test in your plan is rerun on the changed code. This takes about a minute.",
    pullRequest: null,
    who: /^You pick the reviewers once the proof has passed\.$/,
    buttons: ["Connect demo code"],
    off: [],
    primary: ["Connect demo code"],
    note: /^Connects a fresh copy of the small demo repository of acme-sign 1\.4\.2 .* The proof then starts by itself\.$/,
    sections: [],
  },
  {
    view: fixesViews.proving,
    key: "proving",
    word: "Proving",
    ...unproven,
    proofState: "running",
    proofBadge: null,
    proof: "Running: 2 of 6 tests finished. Not offered yet.",
    pullRequest: null,
    who: /^You pick the reviewers once the proof has passed\.$/,
    buttons: [],
    off: [],
    primary: [],
    note: null,
    sections: [CHANGE, ["Proof", "Running: 2 of 6 tests finished.", false], DETAILS],
  },
  {
    view: fixesViews.ready,
    key: "ready",
    word: "Ready for review",
    ...proven,
    ...passed,
    pullRequest: null,
    who: /^You\(the person logged in\)Demo reviewer ADemo dataDemo reviewer BDemo dataThis version has one login/,
    buttons: ["Open pull request"],
    off: [],
    primary: ["Open pull request"],
    note: /^Nothing goes into the main copy of the code until the reviewers you pick approve and you confirm the merge\.$/,
    sections: [CHANGE, PROOF_PASSED_FOLD, DETAILS],
  },
  {
    view: fixesViews.failed,
    key: "failed",
    word: "Proof failed",
    ...unproven,
    proofState: "failed",
    proofBadge: ["Proof did not pass", "fail"],
    proof:
      "1 of the 3 tests that run the changed code did not pass: Official test vectors, Couldn't run (it took too long). The change is not offered.",
    pullRequest: null,
    who: /^Nobody yet: a change that is not offered can't get a pull request\.$/,
    buttons: ["Run proof again"],
    off: [],
    primary: [],
    note: /^Reruns all 6 tests in your plan\. The change is offered only if the proof passes\.$/,
    sections: [CHANGE, ["Proof", "Did not pass: 1 of the 3 tests that run the changed code did not pass.", false], DETAILS],
  },
  {
    view: fixesViews.waiting,
    key: "waiting",
    word: "Waiting for approval",
    ...proven,
    ...passed,
    pullRequest: /^#1 Reject signatures whose r or s is out of range\. Open since .+\. It stays inside the app; nothing is sent anywhere else\.$/,
    who: /^You\(the person logged in\)✓ Approved .+Demo reviewer ADemo dataApprove as Demo reviewer AThis version has one login/,
    buttons: ["Approve as Demo reviewer A", "Merge pull request", "Download patch"],
    off: ["Merge pull request"],
    primary: ["Merge pull request"],
    note: /^"Merge pull request" unlocks when every reviewer has approved: waiting for Demo reviewer A\. The app never merges on its own/,
    sections: [CHANGE, PROOF_PASSED_FOLD, DETAILS],
  },
  {
    view: fixesViews.ready_to_merge,
    key: "ready_to_merge",
    word: "Ready to merge",
    ...proven,
    ...passed,
    pullRequest: /nothing is sent anywhere else\. Every reviewer has approved\. Not merged yet\.$/,
    who: /^You\(the person logged in\)✓ Approved .+Demo reviewer ADemo data✓ Approved .+This version has one login/,
    buttons: ["Merge pull request", "Download patch"],
    off: [],
    primary: ["Merge pull request"],
    note: /^Every reviewer has approved\. The app never merges on its own: you press the button and confirm\.$/,
    sections: [CHANGE, PROOF_PASSED_FOLD, DETAILS],
  },
  {
    view: fixesViews.merged,
    key: "merged",
    word: "Merged",
    ...proven,
    ...passed,
    pullRequest:
      /^#1 Reject signatures whose r or s is out of range\. Merged .+ by the person logged in, after confirming\. The demo repository's main branch now holds acme-sign 1\.4\.3\. Nothing was deployed\.$/,
    who: /^You\(the person logged in\)✓ Approved .+Demo reviewer ADemo data✓ Approved .+This version has one login/,
    buttons: ["Retest now", "Download patch"],
    off: [],
    primary: ["Retest now"],
    note: /^Reruns the same locked tests on acme-sign 1\.4\.3, the code now on main, and shows before and after in Evidence Lab\./,
    sections: [CHANGE, PROOF_PASSED_FOLD, DETAILS],
  },
];

describe("Fixes, the code fix in each status", () => {
  it.each(STATUSES.map((expected) => [expected.key, expected] as const))("%s: its words and exactly its buttons", async (_key, expected) => {
    await open(expected.view);

    // The status, in the summary and in the list, in the backend's word.
    expect(status().getAttribute("data-status")).toBe(expected.key);
    expect(status().textContent).toBe(expected.word);
    expect(within(listItems()[0]!).getByTestId("fix-status").textContent).toBe(expected.word);

    // What it does. Until the proof has passed, the screen must not say that it fixes anything.
    const rowLabels = Array.from(summary().querySelectorAll("dt")).map((dt) => dt.textContent);
    expect(rowLabels).toEqual(
      expected.pullRequest
        ? [expected.whatLabel, "Proof", "Pull request", "Who approves"]
        : [expected.whatLabel, "Proof", "Who approves"],
    );
    expect(text(inSummary().getByTestId("fix-what").firstElementChild)).toMatch(expected.what);
    expect(inSummary().getByTestId("server-line").textContent).toBe(expected.serverLine);

    // The proof row.
    const proof = inSummary().getByTestId("fix-proof");
    expect(proof.getAttribute("data-state")).toBe(expected.proofState);
    const badge = within(proof).queryByTestId("result-badge");
    expect(badge ? [badge.lastElementChild?.textContent, badge.getAttribute("data-tone")] : null).toEqual(expected.proofBadge);
    expect(text(proof.querySelector("p"))).toBe(expected.proof);
    // A spinner only while the proof runs, always beside words.
    expect(proof.querySelector(".animate-spin") !== null).toBe(expected.key === "proving");
    expect(status().querySelector(".animate-spin") !== null).toBe(expected.key === "proving");

    const pullRequest = inSummary().queryByTestId("fix-pull-request");
    if (expected.pullRequest) expect(text(pullRequest)).toMatch(expected.pullRequest);
    else expect(pullRequest).toBeNull();

    expect(text(inSummary().getByTestId("fix-approvers"))).toMatch(expected.who);

    // The buttons: the ones the view sent, in its order, and no other.
    expect(summaryButtons().map((b) => b.textContent)).toEqual(expected.buttons);
    expect(summaryButtons().filter((b) => b.disabled).map((b) => b.textContent)).toEqual(expected.off);
    expect(summaryButtons().filter((b) => b.className.includes("bg-sky-500")).map((b) => b.textContent)).toEqual(expected.primary);
    const actions = inSummary().queryByTestId("fix-actions");
    if (expected.note) expect(text(actions?.querySelector("p"))).toMatch(expected.note);
    else expect(actions).toBeNull();

    // The folded sections, or the sentence that stands in for them.
    expect(
      sections().map((s) => {
        const key = s.getAttribute("data-section")!;
        const words = fold(key).lastElementChild!;
        return [words.firstElementChild!.textContent, words.lastElementChild!.textContent, isOpen(key)];
      }),
    ).toEqual(expected.sections);
    const standIn = screen.queryByTestId("fix-sections-note");
    if (expected.sections.length === 0) {
      expect(standIn?.textContent).toBe("The change, its proof and the technical details appear below once the code is connected.");
    } else {
      expect(standIn).toBeNull();
    }
  });

  it.each(["not_connected", "proving", "failed"] as const)("%s: nothing on the screen calls the change ready or says it fixes anything", async (key) => {
    await open(fixesViews[key]);
    if (key !== "not_connected") fireEvent.click(fold("proof"));
    // The subline's own rule ("ready for review only after its proof has passed") is the one place the word may stand.
    const all = (document.body.textContent ?? "").replace(screen.getByTestId("fixes-subline").textContent ?? "", "");
    expect(all).not.toMatch(/ready for review|ready to merge|fix ready|what it fixes|this fixes|proof passed|\bpassed:/i);
    expect(all).toContain(SERVER_LINE_UNPROVEN);
  });

  it.each([
    ["not_connected", "border-slate-500 text-slate-200"],
    ["proving", "border-slate-500 text-slate-100"],
    ["ready", "border-sky-400/60 bg-sky-400/10 text-sky-100"],
    ["failed", "border-amber-400/70 bg-amber-400/15 text-amber-100"],
    ["waiting", "border-slate-400 bg-slate-700/40 text-slate-100"],
    ["ready_to_merge", "border-sky-400/60 bg-sky-400/10 text-sky-100"],
    ["merged", "border-slate-400 bg-slate-700/40 text-slate-100"],
    ["text_only", "border-dashed border-slate-400 text-slate-200"],
  ] as const)("gives the %s chip its own look, always with its word", (key, look) => {
    const { unmount } = render(<StatusChip status={{ key, word: "The word", busy: false }} />);
    const chip = screen.getByTestId("fix-status");
    expect(chip.getAttribute("data-status")).toBe(key);
    expect(chip.textContent).toBe("The word");
    expect(chip.className).toContain(look);
    expect(chip.querySelector(".animate-spin")).toBeNull();
    unmount();

    render(<StatusChip status={{ key, word: "The word", busy: true }} />);
    const busy = screen.getByTestId("fix-status");
    expect(busy.textContent).toBe("The word");
    expect(busy.querySelector(".animate-spin")?.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("Fixes, the buttons", () => {
  it("Connect demo code calls its route once, and the proof then shows as running", async () => {
    const fetchMock = await open(fixesViews.not_connected, { [`POST ${FIXES}/connect`]: { body: fixesViews.proving } });
    expect(sections()).toHaveLength(0);
    fireEvent.click(button("Connect demo code"));
    // While the call is on its way the button waits, so a second click does nothing.
    expect(button("Connect demo code").disabled).toBe(true);
    fireEvent.click(button("Connect demo code"));

    await waitFor(() => expect(status().textContent).toBe("Proving"));
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `POST ${FIXES}/connect`]);
    expect(sent(fetchMock, `${FIXES}/connect`)).toEqual([undefined]);
    expect(text(inSummary().getByRole("status"))).toBe("Running: 2 of 6 tests finished. Not offered yet.");
    expect(summaryButtons()).toHaveLength(0);
    expect(sections().map((s) => s.getAttribute("data-section"))).toEqual(["change", "proof", "details"]);
    expect(screen.queryByTestId("fix-sections-note")).toBeNull();
  });

  it("draws a button the view switched off as switched off, and it calls nothing", async () => {
    const note = "Run every test in the plan first. Then the demo code can be connected.";
    const view = withCodeFix(fixesViews.not_connected, {
      actions: { buttons: [{ action: "connect", label: "Connect demo code", primary: true, enabled: false }], note },
    });
    const fetchMock = await open(view);
    expect(button("Connect demo code").disabled).toBe(true);
    fireEvent.click(button("Connect demo code"));
    expect(text(inSummary().getByTestId("fix-actions").querySelector("p"))).toBe(note);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("Run proof again calls its route for this fix", async () => {
    const fetchMock = await open(fixesViews.failed, { [`POST ${FIX}/proof`]: { body: fixesViews.proving } });
    fireEvent.click(button("Run proof again"));
    await waitFor(() => expect(status().textContent).toBe("Proving"));
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `POST ${FIX}/proof`]);
    expect(sent(fetchMock, `${FIX}/proof`)).toEqual([undefined]);
  });

  it("offers the reviewers as a tick list, You ticked, and Open pull request sends the ticked ones", async () => {
    const fetchMock = await open(fixesViews.ready, { [`POST ${FIX}/pull-request`]: { body: fixesViews.opened } });
    const group = within(screen.getByRole("group", { name: "Who approves" }));
    const boxes = group.getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes.map((box) => [text(box.closest("label")), box.checked])).toEqual([
      ["You(the person logged in)", true],
      ["Demo reviewer ADemo data", false],
      ["Demo reviewer BDemo data", false],
    ]);
    expect(inSummary().getByText(ONE_LOGIN)).not.toBeNull();

    fireEvent.click(group.getByRole("checkbox", { name: /Demo reviewer A/ }));
    expect(boxes.map((box) => box.checked)).toEqual([true, true, false]);
    fireEvent.click(button("Open pull request"));
    await waitFor(() => expect(status().textContent).toBe("Waiting for approval"));
    expect(sent(fetchMock, `${FIX}/pull-request`)).toEqual([{ reviewers: ["you", "a"] }]);
    // The tick list has made way for one row for each picked reviewer.
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getAllByTestId("approval-row").map((row) => row.getAttribute("data-reviewer"))).toEqual(["you", "a"]);
  });

  it("sends exactly the boxes that are ticked, in the list's order", async () => {
    const fetchMock = await open(fixesViews.ready, { [`POST ${FIX}/pull-request`]: { body: fixesViews.opened } });
    const group = within(screen.getByRole("group", { name: "Who approves" }));
    fireEvent.click(group.getByRole("checkbox", { name: /Demo reviewer B/ }));
    fireEvent.click(group.getByRole("checkbox", { name: /Demo reviewer A/ }));
    fireEvent.click(group.getByRole("checkbox", { name: /^You/ }));
    fireEvent.click(button("Open pull request"));
    await waitFor(() => expect(status().textContent).toBe("Waiting for approval"));
    expect(sent(fetchMock, `${FIX}/pull-request`)).toEqual([{ reviewers: ["a", "b"] }]);
  });

  it("has one Approve button for each reviewer still to approve, and sends that row's reviewer", async () => {
    const fetchMock = await open(fixesViews.opened, {
      [`POST ${FIX}/approve`]: (init) => ({
        body: JSON.parse(String(init?.body)).reviewer === "you" ? fixesViews.waiting : fixesViews.ready_to_merge,
      }),
    });
    const rows = () => screen.getAllByTestId("approval-row");
    expect(rows().map((row) => within(row).getByRole("button").textContent)).toEqual(["Approve", "Approve as Demo reviewer A"]);
    // Your own approval is the main button; a demo reviewer's is the quieter one.
    expect(button("Approve").className).toContain("bg-sky-500");
    expect(button("Approve as Demo reviewer A").className).not.toContain("bg-sky-500");
    expect(button("Merge pull request").disabled).toBe(true);

    fireEvent.click(button("Approve"));
    await waitFor(() => expect(within(rows()[0]!).queryByRole("button")).toBeNull());
    expect(sent(fetchMock, `${FIX}/approve`)).toEqual([{ reviewer: "you" }]);
    // Recorded with the name and the time.
    expect(text(rows()[0])).toMatch(/^You\(the person logged in\)✓ Approved .+$/);
    expect(rows()[0]!.querySelector("time")?.getAttribute("datetime")).toBe("2026-11-11T15:22:31.000Z");
    expect(button("Merge pull request").disabled).toBe(true);

    fireEvent.click(button("Approve as Demo reviewer A"));
    await waitFor(() => expect(status().textContent).toBe("Ready to merge"));
    expect(sent(fetchMock, `${FIX}/approve`)).toEqual([{ reviewer: "you" }, { reviewer: "a" }]);
    expect(rows().flatMap((row) => within(row).queryAllByRole("button"))).toHaveLength(0);
    expect(button("Merge pull request").disabled).toBe(false);
  });

  it("Download patch saves the patch file by its own address, with no call and no new window", async () => {
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(`${this.getAttribute("href")} -> ${this.download}`);
    });
    const newWindow = vi.spyOn(window, "open").mockImplementation(() => null);
    const fetchMock = await open(fixesViews.waiting);
    fireEvent.click(button("Download patch"));
    expect(saved).toEqual([`${FIX}/patch -> acme-sign-pull-request-1.patch`]);
    expect(newWindow).not.toHaveBeenCalled();
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
    expect(document.querySelector("a[download]")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("switches off a button that could do nothing: a merge without its confirm box, a patch without its file", async () => {
    await open(withCodeFix(fixesViews.ready_to_merge, { merge_dialog: null, patch: null }));
    expect(button("Merge pull request").disabled).toBe(true);
    expect(button("Download patch").disabled).toBe(true);
    fireEvent.click(button("Merge pull request"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Retest now starts the retest and then hands over to Evidence Lab", async () => {
    const fetchMock = await open(fixesViews.merged, { [`POST ${FIX}/retest`]: { body: lab } });
    fireEvent.click(button("Retest now"));
    expect(handedOver).toBe(0);
    await waitFor(() => expect(handedOver).toBe(1));
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `POST ${FIX}/retest`]);
    expect(sent(fetchMock, `${FIX}/retest`)).toEqual([undefined]);
  });

  it("stays on Fixes and shows the reason when the retest is refused", async () => {
    await open(fixesViews.merged, { [`POST ${FIX}/retest`]: refusal("A retest is running. Wait until it has finished.") });
    fireEvent.click(button("Retest now"));
    expect(text(await screen.findByRole("alert"))).toBe("A retest is running. Wait until it has finished.");
    expect(handedOver).toBe(0);
    expect(status().textContent).toBe("Merged");
    expect(button("Retest now").disabled).toBe(false);
  });

  it("shows a refused action's reason in the usual box and changes nothing else", async () => {
    const fetchMock = await open(fixesViews.ready, {
      [`POST ${FIX}/pull-request`]: refusal("The proof no longer covers the tests in your plan."),
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Demo reviewer B/ }));
    fireEvent.click(button("Open pull request"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("The proof no longer covers the tests in your plan.");
    // The same box the other steps use.
    expect(alert.className).toContain("border-amber-500/50");
    expect(status().textContent).toBe("Ready for review");
    expect((screen.getAllByRole("checkbox") as HTMLInputElement[]).map((box) => box.checked)).toEqual([true, false, true]);
    expect(button("Open pull request").disabled).toBe(false);
    expect(sections().map((s) => s.getAttribute("data-section"))).toEqual(["change", "proof", "details"]);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `POST ${FIX}/pull-request`]);
  });
});

describe("Fixes, the confirm box before a merge", () => {
  const dialog = () => screen.queryByRole("dialog");

  it("opens with the view's words, on Cancel, and Cancel, Escape and a click outside close it without a call", async () => {
    const fetchMock = await open(fixesViews.ready_to_merge, { [`POST ${FIX}/merge`]: { body: fixesViews.merged } });
    expect(dialog()).toBeNull();
    const merge = button("Merge pull request");
    merge.focus();
    fireEvent.click(merge);

    const box = screen.getByRole("dialog", { name: "Merge pull request #1?" });
    expect(box.getAttribute("aria-modal")).toBe("true");
    expect(Array.from(box.querySelectorAll("p")).map((p) => text(p))).toEqual([
      "This puts the change on the main branch of the app's own copy of the demo repository acme-sign. After the merge, that branch holds acme-sign 1.4.3.",
      "Every reviewer has approved. The app deploys nothing, and a merge can't be undone here.",
    ]);
    expect(within(box).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cancel", "Confirm merge"]);
    // The keyboard starts on Cancel, and Tab stays inside the box.
    const cancel = within(box).getByRole("button", { name: "Cancel" });
    const confirm = within(box).getByRole("button", { name: "Confirm merge" });
    expect(document.activeElement).toBe(cancel);
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm);
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(document.activeElement).toBe(cancel);

    fireEvent.click(cancel);
    expect(dialog()).toBeNull();
    // The keyboard goes back to the button that opened the box.
    expect(document.activeElement).toBe(merge);

    fireEvent.click(merge);
    expect(dialog()).not.toBeNull();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(dialog()).toBeNull();

    fireEvent.click(merge);
    fireEvent.mouseDown(dialog()!.parentElement!);
    expect(dialog()).toBeNull();

    // A click inside the box, on its words, does not close it.
    fireEvent.click(merge);
    fireEvent.mouseDown(within(dialog()!).getByRole("heading", { name: "Merge pull request #1?" }));
    expect(dialog()).not.toBeNull();
    fireEvent.click(within(dialog()!).getByRole("button", { name: "Cancel" }));

    await pause(50);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
    expect(status().textContent).toBe("Ready to merge");
  });

  it("merges only on Confirm merge, with one call", async () => {
    const fetchMock = await open(fixesViews.ready_to_merge, { [`POST ${FIX}/merge`]: { body: fixesViews.merged } });
    fireEvent.click(button("Merge pull request"));
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
    fireEvent.click(button("Confirm merge"));
    expect(dialog()).toBeNull();
    await waitFor(() => expect(status().textContent).toBe("Merged"));
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `POST ${FIX}/merge`]);
    expect(sent(fetchMock, `${FIX}/merge`)).toEqual([undefined]);
    expect(summaryButtons().map((b) => b.textContent)).toEqual(["Retest now", "Download patch"]);
  });

  it("does not open while an approval is missing: the button is switched off", async () => {
    const fetchMock = await open(fixesViews.waiting);
    expect(button("Merge pull request").disabled).toBe(true);
    fireEvent.click(button("Merge pull request"));
    expect(dialog()).toBeNull();
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("shows the reason when the merge is refused, and stays unmerged", async () => {
    await open(fixesViews.ready_to_merge, { [`POST ${FIX}/merge`]: refusal("The main branch has moved since this change was made.") });
    fireEvent.click(button("Merge pull request"));
    fireEvent.click(button("Confirm merge"));
    expect(text(await screen.findByRole("alert"))).toBe("The main branch has moved since this change was made.");
    expect(dialog()).toBeNull();
    expect(status().textContent).toBe("Ready to merge");
  });
});

describe("Fixes, the folded sections", () => {
  it("starts with the change open and the others closed; a click opens and closes each", async () => {
    const fetchMock = await open(fixesViews.ready);
    // Each section's title is a heading, and the heading is the button that folds it.
    for (const s of sections()) expect(within(s).getByRole("heading", { level: 3 }).firstElementChild?.tagName).toBe("BUTTON");
    expect(["change", "proof", "details"].map(isOpen)).toEqual([true, false, false]);
    expect(within(section("proof")).queryByTestId("proof-table")).toBeNull();
    expect(within(section("details")).queryByTestId("detail-fact")).toBeNull();

    fireEvent.click(fold("proof"));
    fireEvent.click(fold("details"));
    fireEvent.click(fold("change"));
    expect(["change", "proof", "details"].map(isOpen)).toEqual([false, true, true]);
    expect(within(section("change")).queryByTestId("change-part")).toBeNull();
    expect(within(section("proof")).getAllByTestId("proof-table")).toHaveLength(2);
    // The one line stays on a section whether it is open or not.
    expect(within(section("proof")).getByTestId("fix-section-line").textContent).toMatch(/^Passed: all 3 tests that run the changed code passed/);

    fireEvent.click(fold("proof"));
    expect(isOpen("proof")).toBe(false);
    expect(within(section("proof")).queryByTestId("proof-table")).toBeNull();
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("The change: the template sentence, then each part with its before and after lines and marks", async () => {
    await open(fixesViews.ready);
    const change = within(section("change"));
    expect(change.getByText(/^Written from a fix template: .* It was not written by an AI model/)).not.toBeNull();
    const parts = change.getAllByTestId("change-part");
    expect(parts.map((part) => Array.from(part.querySelectorAll(":scope > p")).map((p) => text(p)))).toEqual([
      [
        "1. The check: reject a signature whose numbers are out of range",
        "acme_sign.py, in the verify command. r and s must each be at least 1 and below n, a fixed upper limit set by the P-256 standard.",
        "Before: acme-sign 1.4.2, nothing removed here",
        "After: this change, 2 lines added (marked +)",
      ],
      [
        "2. The version number",
        "So the changed program reports itself as 1.4.3 and can be told apart from 1.4.2.",
        "Before: acme-sign 1.4.2, 1 line removed (marked −)",
        "After: this change, 1 line added (marked +)",
      ],
    ]);

    // Line number, mark and the line itself. A changed line has its mark as a character, not only a tint.
    const lines = (part: HTMLElement, mark: string) =>
      within(part)
        .getAllByTestId("code-line")
        .filter((line) => line.getAttribute("data-mark") === mark)
        .map((line) => Array.from(line.children).map((piece) => piece.textContent));
    expect(lines(parts[0]!, "+")).toEqual([
      ["169", "+", "    if not (1 <= r < N and 1 <= s < N):"],
      ["170", "+", '        return {"valid": False}'],
    ]);
    expect(lines(parts[0]!, "-")).toEqual([]);
    expect(lines(parts[0]!, " ")).toHaveLength(10);
    expect(lines(parts[0]!, " ")[0]).toEqual(["165", "", "    try:"]);
    expect(lines(parts[1]!, "-")).toEqual([["20", "−", 'VERSION = "1.4.2"']]);
    expect(lines(parts[1]!, "+")).toEqual([["20", "+", 'VERSION = "1.4.3"']]);
    // Code is shown as text: nothing in it is a link, a button or a field.
    expect(section("change").querySelector("a, input, textarea")).toBeNull();
    expect(within(section("change")).getAllByRole("button")).toHaveLength(1);
  });

  it("Proof, passed: both tables with before, proof result, control and rule check, then why it is ready", async () => {
    await open(fixesViews.ready);
    fireEvent.click(fold("proof"));
    const proof = within(section("proof"));
    expect(proof.getByText(/^The app applied this change on a new branch of its own copy of the code/)).not.toBeNull();
    const tables = proof.getAllByTestId("proof-table");
    expect(tables.map((table) => text(table.firstElementChild))).toEqual([
      "Tests that run the changed code measured",
      "Tests that don't run this code (they test the server) measured",
    ]);
    expect(tables.map((table) => Array.from(within(table).getByTestId("proof-columns").children).map((c) => c.textContent))).toEqual([
      ["Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"],
      ["Test", "Before", "Rerun for this proof", "Rule check"],
    ]);
    expect(tables.map((table) => within(table).getAllByTestId("proof-row").map((row) => row.getAttribute("data-kind")))).toEqual([
      ["official_vectors", "bad_signatures", "speed_size"],
      ["tls_versions", "certificate", "pq_readiness"],
    ]);

    const row = (kind: string) => proof.getAllByTestId("proof-row").find((r) => r.getAttribute("data-kind") === kind)!;
    const badge = (cell: HTMLElement) => {
      const b = within(cell).getByTestId("result-badge");
      return [b.lastElementChild?.textContent, b.getAttribute("data-tone")];
    };
    const vectors = within(row("official_vectors"));
    expect(vectors.getByText("Official test vectors")).not.toBeNull();
    expect(badge(vectors.getByTestId("proof-cell-before"))).toEqual(["Failed", "fail"]);
    expect(badge(vectors.getByTestId("proof-cell-proof"))).toEqual(["Passed", "pass"]);
    expect(within(vectors.getByTestId("proof-cell-proof")).getByText("484 of 484 official cases right.")).not.toBeNull();
    expect(within(vectors.getByTestId("proof-cell-proof")).getByText("Control: a deliberately broken signer failed this test, as expected.")).not.toBeNull();
    expect(within(vectors.getByTestId("proof-cell-before")).queryByText(/^Control/)).toBeNull();

    // A server test that failed before and fails again counts as "same as before": the code change can't touch it.
    const tls = within(row("tls_versions"));
    expect(badge(tls.getByTestId("proof-cell-before"))).toEqual(["Failed", "fail"]);
    expect(badge(tls.getByTestId("proof-cell-proof"))).toEqual(["Failed", "fail"]);
    expect(tls.getByText("Server still accepts TLS 1.2. This change doesn't touch the server.")).not.toBeNull();

    const checks = (el: HTMLElement) => within(el).getAllByTestId("proof-check").map((c) => [c.getAttribute("data-ok"), text(c)]);
    expect(proof.getAllByTestId("proof-row").map((r) => checks(r)[0])).toEqual([
      ["true", "✓Passed"],
      ["true", "✓Passed"],
      ["true", "✓No slowdown"],
      ["true", "✓Same as before"],
      ["true", "✓Same as before"],
      ["true", "✓Same as before"],
    ]);

    const verdict = proof.getByTestId("proof-verdict");
    expect(verdict.getAttribute("data-tone")).toBe("pass");
    expect(verdict.className).toContain("border-sky-400/35");
    expect(within(verdict).getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual([
      "Why it is ready for review",
      "What this proof shows, and what it doesn't",
    ]);
    expect(checks(verdict)).toEqual([
      ["true", "✓All 3 tests that run the changed code passed."],
      ["true", "✓Every control behaved as expected."],
      ["true", "✓The 3 server tests came out the same as before."],
    ]);
    expect(within(verdict).getByText(/^It doesn't show that the change is free of other faults/)).not.toBeNull();
  });

  it("Proof, failed: shows the test that did not pass and why the change is not offered, in the failure look", async () => {
    await open(fixesViews.failed);
    fireEvent.click(fold("proof"));
    const proof = within(section("proof"));
    const vectors = within(proof.getAllByTestId("proof-row")[0]!);
    const failedBadge = within(vectors.getByTestId("proof-cell-proof")).getByTestId("result-badge");
    expect([failedBadge.lastElementChild?.textContent, failedBadge.getAttribute("data-tone")]).toEqual([
      "Couldn't run (it took too long)",
      "warn",
    ]);
    expect(vectors.getByText("Control: not run, because the test couldn't run.")).not.toBeNull();
    const check = vectors.getByTestId("proof-check");
    expect([check.getAttribute("data-ok"), text(check)]).toEqual(["false", "✕Did not pass"]);

    const verdict = proof.getByTestId("proof-verdict");
    expect(verdict.getAttribute("data-tone")).toBe("fail");
    expect(verdict.className).toContain("border-amber-400/50");
    expect(verdict.className).not.toContain("sky");
    expect(within(verdict).getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Why this change is not offered"]);
    expect(within(verdict).getAllByTestId("proof-check").map((c) => [c.getAttribute("data-ok"), text(c)])).toEqual([
      ["false", "✕1 of the 3 tests that run the changed code did not pass: Official test vectors, Couldn't run (it took too long)."],
      ["true", "✓Every control behaved as expected in the tests that ran."],
      ["true", "✓The 3 server tests came out the same as before."],
    ]);
  });

  it("Proof, still running: a test without a result shows as waiting or running, never as a result", async () => {
    await open(fixesViews.proving);
    fireEvent.click(fold("proof"));
    const proof = within(section("proof"));
    const rows = proof.getAllByTestId("proof-row");
    const cell = (i: number) => within(rows[i]!).getByTestId("proof-cell-proof");

    expect(text(within(cell(0)).getByTestId("proof-waiting"))).toBe("Running212 of 484 cases");
    const bar = within(cell(0)).getByRole("progressbar", { name: "Official test vectors: Running" });
    expect(bar.getAttribute("aria-valuenow")).toBe("44");
    expect(text(within(cell(1)).getByTestId("proof-waiting"))).toBe("Waiting");
    expect(within(cell(1)).queryByRole("progressbar")).toBeNull();
    for (const i of [0, 1, 2, 5]) {
      expect(within(cell(i)).queryByTestId("result-badge")).toBeNull();
      expect(within(rows[i]!).queryByText(/^Control/)).toBeNull();
      const check = within(rows[i]!).getByTestId("proof-check");
      expect([check.getAttribute("data-ok"), text(check)]).toEqual(["null", "•Not finished yet"]);
      // The first result it will be compared with is already there.
      expect(within(within(rows[i]!).getByTestId("proof-cell-before")).getByTestId("result-badge")).not.toBeNull();
    }
    // The two tests that have finished show their results.
    for (const i of [3, 4]) expect(within(cell(i)).getByTestId("result-badge")).not.toBeNull();
    // No verdict before the proof has ended.
    expect(proof.queryByTestId("proof-verdict")).toBeNull();
  });

  it("Technical details: the facts in the view's order, fingerprints able to break, and what the tests ran on", async () => {
    await open(fixesViews.merged);
    fireEvent.click(fold("details"));
    const details = within(section("details"));
    const facts = details.getAllByTestId("detail-fact");
    expect(facts.map((fact) => fact.firstElementChild?.textContent)).toEqual([
      "Repository",
      "Starting point",
      "Change branch",
      "File changed",
      "Pull request",
      "Proof finished",
      "Mode",
      "Evidence fingerprint of the proof (SHA-256)",
    ]);
    const value = (label: string) => facts.find((fact) => fact.firstElementChild?.textContent === label)!.lastElementChild as HTMLElement;
    expect(text(value("Repository"))).toBe("acme-sign Demo data, the app's own copy. Nothing is sent anywhere else.");
    expect(within(value("Repository")).getByText("Demo data").className).toContain("violet");
    expect(text(value("Starting point"))).toBe("branch main, commit 3f9c2ab (acme-sign 1.4.2)");
    expect(within(value("Change branch")).getByText("fix/ecdsa-range-check").className).toContain("font-mono");
    expect(text(value("Pull request"))).toMatch(/^#1, opened .+; merged .+ \(merge commit c41f0d2\)$/);
    expect(Array.from(value("Pull request").querySelectorAll("time")).map((t) => t.getAttribute("datetime"))).toEqual([
      "2026-11-11T15:22:10.000Z",
      "2026-11-11T15:23:40.000Z",
    ]);
    expect(text(value("Proof finished"))).toMatch(/, after 42\.0 s measured$/);
    expect(text(value("Mode"))).toBe("Demo mode, not isolated");
    const fingerprint = value("Evidence fingerprint of the proof (SHA-256)");
    expect(fingerprint.textContent).toBe(PROOF_FINGERPRINT);
    expect(fingerprint.className).toContain("break-all");
    expect(fingerprint.className).toContain("font-mono");
    expect(fingerprint.querySelector(".whitespace-nowrap")).toBeNull();
    expect(details.getByText(/^A branch is a separate line of work inside the repository/)).not.toBeNull();

    const ranOn = within(details.getByTestId("ran-on"));
    expect(ranOn.getByText("What the tests ran on")).not.toBeNull();
    expect(ranOn.getByText(/the app checked that the file built from branch/)).not.toBeNull();
    const pairs = Array.from(details.getByTestId("ran-on").querySelectorAll("dl > div")).map((pair) =>
      Array.from(pair.children).map((part) => text(part)),
    );
    expect(pairs).toEqual([
      ["The built file (SHA-256)", "d49e46ed3121ab0f2220a8b0a7a50f18b684b310e465d5e755062f69be40a378 measured"],
      ["Bundled acme-sign 1.4.3 (SHA-256)", "d49e46ed3121ab0f2220a8b0a7a50f18b684b310e465d5e755062f69be40a378 demo"],
    ]);
    expect(ranOn.getByText(/^This version of Evidence Lab only ever runs our own demo software\./)).not.toBeNull();
  });
});

describe("Fixes, a text-only suggestion", () => {
  it("shows what it suggests, that it has no proof, and no button at all", async () => {
    const fetchMock = await open(fixesViews.ready, {}, TLS_FIX);
    expect(inSummary().getByRole("heading", { level: 2, name: "Server accepts TLS 1.2" })).not.toBeNull();
    expect(text(inSummary().getByTestId("fix-source"))).toBe(
      "Came from 1 failed test on server localhost:8443: Old TLS versions. The file claims TLS 1.3 only.",
    );
    expect(status().getAttribute("data-status")).toBe("text_only");
    expect(status().textContent).toBe("Text only");
    expect(status().className).toContain("border-dashed");
    // No "From a fix template" label here: the app has not made this change.
    expect(Array.from(status().parentElement!.children).map((chip) => chip.textContent)).toEqual(["Text only", "Demo data"]);

    expect(Array.from(summary().querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(["What it suggests", "Proof", "Who approves"]);
    expect(text(inSummary().getByTestId("fix-what"))).toMatch(/^A server setting, not a code change: /);
    expect(inSummary().queryByTestId("server-line")).toBeNull();
    const proof = inSummary().getByTestId("fix-proof");
    expect(proof.getAttribute("data-state")).toBe("none");
    expect(proof.textContent).toBe("None. This suggestion is text only: the app has not applied it or tested it.");
    expect(proof.querySelector('[data-testid="result-badge"]')).toBeNull();
    expect(inSummary().getByTestId("fix-approvers").textContent).toBe(
      "Your own server team, outside this app. The app never changes your server.",
    );

    expect(summaryButtons()).toHaveLength(0);
    expect(inSummary().queryByTestId("fix-actions")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    // The only buttons left are the two findings and the fold of the suggestion.
    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("opens on the suggestion: the warning, where the setting lives, two ways to fix it and the exact settings", async () => {
    await open(fixesViews.ready, {}, TLS_FIX);
    expect(sections().map((s) => s.getAttribute("data-section"))).toEqual(["suggestion"]);
    expect(isOpen("suggestion")).toBe(true);
    expect(within(section("suggestion")).getByTestId("fix-section-line").textContent).toBe(
      "A warning first, where the setting lives, and two ways to fix it",
    );
    const body = within(within(section("suggestion")).getByTestId("text-suggestion"));

    // Names between backticks are drawn fixed width, without the backticks.
    expect(section("suggestion").textContent).not.toContain("`");
    const suite = body.getAllByText("ECDHE-ECDSA-AES128-SHA")[0]!;
    expect(suite.className).toContain("font-mono");
    expect(suite.className).toContain("whitespace-nowrap");
    expect(text(suite.parentElement)).toBe(
      "This is usually a server setting, not a code change. The server accepted TLS 1.2, with the older cipher suite (the set of algorithms a connection uses) ECDHE-ECDSA-AES128-SHA. The file claims TLS 1.3 only.",
    );

    expect(text(body.getByTestId("suggestion-warning"))).toBe(
      "!Before you switch TLS 1.2 off: older clients and partner systems that can't use TLS 1.3 will no longer be able to connect.",
    );
    expect(body.getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Where the setting lives", "Two ways to fix it"]);

    const table = within(body.getByRole("table"));
    expect(table.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Where TLS is set up",
      "The setting",
      "To accept TLS 1.3 only",
    ]);
    const rows = table.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]!.textContent)).toEqual([
      "nginx",
      "Apache",
      "A cloud load balancer",
      "Your own application",
    ]);
    expect(rows.map((r) => r.querySelector("code")?.textContent)).toEqual([
      "ssl_protocols TLSv1.3;",
      "SSLProtocol -all +TLSv1.3",
      "ELBSecurityPolicy-TLS13-1-3-2021-06",
      "context.minimum_version = ssl.TLSVersion.TLSv1_3",
    ]);
    expect(within(rows[0]!).getByText("ssl_protocols").className).toContain("font-mono");
    expect(within(rows[3]!).getByText("Set the minimum to TLS 1.3. In Python, for example:")).not.toBeNull();
    expect(body.getByText(/^For either option, change every existing line/)).not.toBeNull();

    const options = body.getAllByTestId("suggestion-option");
    expect(options.map((o) => o.firstElementChild?.textContent)).toEqual([
      "Option 1: switch TLS 1.2 off",
      "Option 2: keep TLS 1.2, with strong settings only",
    ]);
    expect(options.map((o) => within(o).getAllByRole("listitem").length)).toEqual([3, 3]);
    expect(within(options[0]!).getByText("%{SSL_PROTOCOL}x").className).toContain("font-mono");
    expect(within(options[1]!).getByText("This test checks TLS versions only. It will not show whether the old cipher suite is gone.")).not.toBeNull();

    // The exact settings: each line of each block is the setting itself, with nothing added for the line breaks.
    const exact = body.getByTestId("suggestion-exact");
    expect(within(exact).getByText("Option 2: the exact settings")).not.toBeNull();
    expect(Array.from(exact.querySelectorAll("pre")).map((pre) => Array.from(pre.children).map((line) => line.textContent))).toEqual(
      tlsSuggestion.exact!.blocks.map((block) => block.code.split("\n")),
    );
    expect(exact.querySelectorAll("wbr").length).toBeGreaterThan(0);
  });

  it("draws only the parts a suggestion has", async () => {
    const short = "Renew the certificate with a key of at least 2048 bits, then run this test again.";
    const view: FixesView = {
      ...fixesViews.ready,
      fixes: fixesViews.ready.fixes.map((fix) =>
        fix.id === TLS_FIX
          ? {
              ...fix,
              sections: [
                {
                  key: "suggestion" as const,
                  title: "The suggestion",
                  line: "One step",
                  open: true,
                  suggestion: { intro: [short], warning: null, where: null, options: null, exact: null },
                },
              ],
            }
          : fix,
      ),
    };
    await open(view, {}, TLS_FIX);
    const body = within(section("suggestion")).getByTestId("text-suggestion");
    expect(text(body)).toBe(short);
    expect(body.querySelector("table, pre, h4, ol")).toBeNull();
  });
});

describe("Fixes, while something runs", () => {
  it("asks again every second, keeps the selected fix and the opened sections, and stops when nothing runs", async () => {
    let polls = 0;
    const fetchMock = mockApi({
      [`GET ${FIXES}`]: () => {
        polls += 1;
        return { body: polls < 3 ? fixesViews.proving : fixesViews.ready };
      },
    });
    render(<Harness start={null} />);
    await screen.findByTestId("fix-summary");
    expect(status().textContent).toBe("Proving");

    // On the code fix: open Proof, close The change. Then look at the other fix and close its suggestion.
    fireEvent.click(fold("proof"));
    fireEvent.click(fold("change"));
    fireEvent.click(listItems()[1]!);
    fireEvent.click(fold("suggestion"));
    expect(isOpen("suggestion")).toBe(false);

    // The next answer (still proving) leaves the other fix selected and its section closed.
    await waitFor(() => expect(polls).toBe(2), { timeout: 3000 });
    await pause(50);
    expect(summary().getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(selectedTitles()).toEqual(["Server accepts TLS 1.2"]);
    expect(isOpen("suggestion")).toBe(false);

    // Back on the code fix, the sections are as they were left.
    fireEvent.click(listItems()[0]!);
    expect(["change", "proof", "details"].map(isOpen)).toEqual([false, true, false]);
    expect(within(section("proof")).queryByTestId("proof-verdict")).toBeNull();

    // The proof ends: the status and the proof change under the same open sections.
    await waitFor(() => expect(status().textContent).toBe("Ready for review"), { timeout: 3000 });
    expect(summary().getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(["change", "proof", "details"].map(isOpen)).toEqual([false, true, false]);
    expect(within(section("proof")).getByTestId("proof-verdict")).not.toBeNull();
    expect(within(listItems()[0]!).getByTestId("fix-status").textContent).toBe("Ready for review");

    // Nothing runs any more, so nothing more is asked.
    await pause(1300);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`, `GET ${FIXES}`, `GET ${FIXES}`]);
  }, 12000);

  it("does not ask again while nothing runs", async () => {
    const fetchMock = await open(fixesViews.ready);
    await pause(1300);
    expect(calls(fetchMock)).toEqual([`GET ${FIXES}`]);
  });

  it("keeps the ticked reviewers through a new answer for the same fix", async () => {
    // Something else in the plan is running, so the view is asked for again while the tick list is on screen.
    let polls = 0;
    mockApi({
      [`GET ${FIXES}`]: () => {
        polls += 1;
        return { body: { ...fixesViews.ready, busy: polls < 2 } };
      },
    });
    render(<Harness start={null} />);
    await screen.findByTestId("fix-summary");
    fireEvent.click(screen.getByRole("checkbox", { name: /Demo reviewer A/ }));
    await waitFor(() => expect(polls).toBe(2), { timeout: 3000 });
    await pause(50);
    expect((screen.getAllByRole("checkbox") as HTMLInputElement[]).map((box) => box.checked)).toEqual([true, true, false]);
  });
});
