import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChangeView, FixesView, MigrationView } from "../api";
import { FixesScreen } from "../components/FixesScreen";
import { MigrationScreen } from "../components/MigrationScreen";
import {
  CHANGE_ID,
  TLS_CHANGE_ID,
  appliedMatches,
  appliedMismatch,
  cantTry,
  readyToApply,
  readyToTry,
  textOnly,
  tlsChange,
  triedPassedPicker,
  trying,
  waitingOneApproval,
} from "./changeFixtures";
import { fixesViews, TLS_FIX } from "./fixesFixtures";
import { calls, mockApi, text } from "./fixtures";
import { S8452, migrationView4b, withChange } from "./migrationFixtures";

const GET = "GET /api/import/7/migration";
const PLAN = "/api/plans/1/changes";
const ERROR = (message: string) => ({ status: 409, body: { error: { message, line: null, field: null } } });

afterEach(() => vi.restoreAllMocks());

async function open(view: MigrationView, routes: Parameters<typeof mockApi>[0] = {}) {
  const fetchMock = mockApi({ [GET]: { body: view }, ...routes });
  const props = { onViewFix: vi.fn(), onPlanChanged: vi.fn() };
  render(<MigrationScreen importId={7} {...props} />);
  await screen.findByRole("heading", { level: 1, name: view.title });
  return { fetchMock, ...props };
}

const card = (name: string) => screen.getAllByTestId("system-card").find((c) => c.textContent?.includes(name))!;
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const box = () => within(screen.getByTestId("change-box"));
const body = (fetchMock: ReturnType<typeof mockApi>, key: string) => {
  const found = fetchMock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${String(url)}` === key).at(-1);
  return JSON.parse(String(found?.[1]?.body));
};

/** The 8452 system selected, showing the given change. */
async function openWith(change: ChangeView | null, routes: Parameters<typeof mockApi>[0] = {}) {
  const view = withChange(migrationView4b, S8452, change);
  const opened = await open(view, routes);
  fireEvent.click(card("localhost:8452"));
  return { ...opened, view };
}

describe("Migration 4b, two tracks", () => {
  it("draws one line per track on the list card, then the plan line", async () => {
    await open(migrationView4b);
    const first = card("localhost:8451");
    expect(within(first).getAllByTestId("card-track").map((r) => text(r))).toEqual(["Key exchange◑Hybrid (interim)", "Authentication○Classical"]);
    expect(text(first)).toBe("Serverlocalhost:8451Key exchange◑Hybrid (interim)Authentication○ClassicalNext: authentication · Phase 2");
    expect(text(within(card("localhost:8455")).getAllByTestId("card-track")[1])).toBe("Authentication●Post-quantum (ML-DSA-65)");
    expect(text(within(card("acme-sign 1.4.2")).getByTestId("card-track"))).toBe("Signatures○Classical");
    expect(text(within(card("acme-sign 9.9")).getByTestId("card-track"))).toBe("Signatures?Couldn't check");
    expect(document.body.textContent).not.toMatch(/score/i);
  });

  it("falls back to one pill when a system has no tracks yet", async () => {
    await open({ ...migrationView4b, systems: migrationView4b.systems.map((s) => ({ ...s, tracks: [], tracks_brief: [] })) });
    expect(within(card("localhost:8451")).queryAllByTestId("card-track")).toHaveLength(0);
    expect(within(card("localhost:8451")).getAllByTestId("migration-status")).toHaveLength(1);
  });

  it("draws the target line, then one box per track with its facts, Next and Why", async () => {
    await open(migrationView4b);
    const today = within(screen.getByTestId("migration-today"));
    expect(screen.getByTestId("target-line").textContent).toMatch(/^Target: post-quantum on both tracks/);
    expect(screen.queryByTestId("today-sentence")).toBeNull();
    const tracks = today.getAllByTestId("migration-track");
    expect(tracks.map((x) => x.getAttribute("data-track"))).toEqual(["kex", "auth"]);
    expect(text(tracks[0]!)).toContain("Track 1 · Key exchange");
    expect(within(tracks[0]!).getByTestId("migration-status").getAttribute("data-code")).toBe("hybrid");
    expect(text(within(tracks[0]!).getByTestId("track-sentence"))).toMatch(/^It asked for a hybrid key/);
    expect(within(tracks[0]!).getAllByRole("term").map((d) => d.textContent)).toEqual(["Chosen by default?", "ML-KEM by itself"]);
    expect(text(within(tracks[0]!).getByTestId("track-next"))).toBe("Next: post-quantum only (ML-KEM by itself), once every client supports it.");
    expect(text(within(tracks[0]!).getByTestId("track-why"))).toMatch(/^Why: Hybrid is the interim step/);
    expect(text(within(tracks[0]!).getByTestId("track-why"))).toContain("reference: NIST IR 8547");
    expect(within(tracks[1]!).getByTestId("migration-status").getAttribute("data-code")).toBe("classical");
  });

  it("gives each pill its own shape as well as its words, including post-quantum and not measured", async () => {
    await open(migrationView4b);
    const shapes = (name: string) => within(card(name)).getAllByTestId("migration-status").map((p) => text(p).charAt(0));
    expect(shapes("localhost:8451")).toEqual(["◑", "○"]);
    expect(shapes("localhost:8455")).toEqual(["●", "●"]);
  });

  it("draws Also noticed only when something was noticed", async () => {
    await open(migrationView4b);
    expect(screen.queryByTestId("also-noticed")).toBeNull();
    fireEvent.click(card("localhost:8452"));
    const notes = screen.getAllByTestId("also-noticed");
    expect(notes).toHaveLength(1);
    expect(text(notes[0])).toBe("Also noticed: It also accepts TLS 1.0 and TLS 1.1, both retired in 2021. This doesn't change a status.");
  });

  it("keeps the file note and the general facts of 4a above the tracks", async () => {
    await open(migrationView4b);
    fireEvent.click(card("localhost:8452"));
    const today = screen.getByTestId("migration-today");
    const note = within(today).getByTestId("file-note");
    const facts = within(today).getByTestId("today-facts");
    const firstTrack = within(today).getAllByTestId("migration-track")[0]!;
    expect(note.compareDocumentPosition(firstTrack) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(facts.compareDocumentPosition(firstTrack) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("draws the change box between the recommendation and the four options, and nothing when there is no change", async () => {
    const { view } = await openWith(readyToTry);
    const rec = screen.getByTestId("migration-recommendation");
    const changeBox = screen.getByTestId("change-box");
    const options = screen.getByTestId("migration-options");
    expect(rec.compareDocumentPosition(changeBox) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(changeBox.compareDocumentPosition(options) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(view.systems.find((s) => s.key === S8452)!.change).not.toBeNull();
    fireEvent.click(card("localhost:8451"));
    expect(screen.queryByTestId("change-box")).toBeNull();
  });
});

describe("Migration 4b, the change box in each state", () => {
  it("ready to try: title, badge, intro, steps, the three kinds of section, buttons with their reason and the note", async () => {
    await openWith(readyToTry);
    expect(box().getByRole("heading", { level: 3, name: readyToTry.title })).not.toBeNull();
    expect(box().getByTestId("change-badge").textContent).toContain("Ready to try");
    expect(box().getByTestId("change-steps").textContent).toContain("Tried on a test copy");
    const steps = box().getAllByTestId("change-step");
    expect(steps.map((s) => s.getAttribute("data-state"))).toEqual(["done", "now", "off", "off", "off"]);
    expect(text(steps[0])).toBe("✓Built5:08 PM");
    expect(text(steps[2])).toBe("3Approvals");

    const sections = box().getAllByTestId("change-section");
    expect(sections.map((s) => s.getAttribute("data-kind"))).toEqual(["table", "lines", "text"]);
    const table = within(sections[0]!);
    expect(table.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["", "Today", "After the change"]);
    expect(table.getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["Key exchange", "Certificate"]);
    expect(text(sections[1])).toContain("ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;");
    expect(text(sections[1])).toContain("Nothing is sent to your server by this app.");
    // The code wraps only after a colon: the pieces between colons are never broken.
    expect(sections[1]!.querySelectorAll("wbr").length).toBe(2);
    expect(text(sections[2])).toContain("bigger first messages");

    expect(box().queryByTestId("change-try")).toBeNull();
    expect(box().getAllByRole("button").map((b) => b.textContent)).toEqual(["Try on a test copy", "Apply to localhost:8452", "Download change"]);
    expect((box().getByRole("button", { name: "Apply to localhost:8452" }) as HTMLButtonElement).disabled).toBe(true);
    expect((box().getByRole("button", { name: "Try on a test copy" }) as HTMLButtonElement).disabled).toBe(false);
    expect(box().getByTestId("change-reason").textContent).toBe("Try it on a test copy first.");
    expect(box().getByTestId("change-note").textContent).toBe(readyToTry.note);
  });

  it("while it runs: the status instead of the table", async () => {
    await openWith(trying);
    expect(within(screen.getByTestId("change-try")).getByTestId("job-status").getAttribute("data-status")).toBe("running");
    expect(screen.getByRole("heading", { level: 4, name: "Try on a test copy: running" })).not.toBeNull();
    expect(screen.queryByTestId("change-verdict")).toBeNull();
    expect((box().getByRole("button", { name: "Try on a test copy" }) as HTMLButtonElement).disabled).toBe(true);
    expect(box().getByTestId("change-reason").textContent).toBe("A try is running.");
  });

  it("tried and passed: the before and after table, the verdict, the notes and a closed evidence disclosure, and the picker", async () => {
    await openWith(triedPassedPicker);
    const tried = within(screen.getByTestId("change-try"));
    expect(tried.getByRole("heading", { level: 4, name: "Try on a test copy: passed" })).not.toBeNull();
    expect(tried.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(triedPassedPicker.try!.columns);
    expect(tried.getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["Key exchange", "Classical-only clients", "First message"]);
    // Cells keep their source tags.
    expect(tried.getAllByText("measured on the copy")).toHaveLength(3);
    const verdict = tried.getByTestId("change-verdict");
    expect(verdict.getAttribute("data-look")).toBe("pass");
    expect(text(verdict)).toBe("Try passed. The copy measures what Hybrid promises, and the control was read correctly.");
    expect(tried.getByTestId("change-try-note").textContent).toBe("Real nginx was not tried: that needs isolated mode (Docker).");

    const disclosure = tried.getByRole("button", { name: "Details and evidence: the test copy" });
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("result-detail")).toBeNull();
    fireEvent.click(disclosure);
    expect(screen.getByTestId("result-detail").getAttribute("data-run-id")).toBe("61");
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Dig deeper" })).toBeNull();

    const approvals = within(screen.getByTestId("change-approvals"));
    expect(approvals.getByRole("heading", { level: 4, name: "Who must approve before Apply" })).not.toBeNull();
    expect((approvals.getByLabelText("You") as HTMLInputElement).checked).toBe(true);
    expect((approvals.getByLabelText(/Demo reviewer A/) as HTMLInputElement).checked).toBe(true);
    expect((approvals.getByLabelText(/Demo reviewer B/) as HTMLInputElement).checked).toBe(false);
    expect(approvals.getAllByText("Demo data")).toHaveLength(2);
    expect((approvals.getByRole("button", { name: "Ask for approval" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText("This version has one login and no separate accounts. Each approval is recorded by name only.")).not.toBeNull();
    expect(box().getByTestId("change-reason").textContent).toBe("Apply stays off until everyone you asked has approved.");
  });

  it("a verdict that did not pass or could not be told keeps its own look", async () => {
    const failed: ChangeView = {
      ...triedPassedPicker,
      try: { ...triedPassedPicker.try!, title: "Try on a test copy: did not pass", verdict: { label: "Try did not pass.", look: "fail", text: "The copy is still Classical." } },
    };
    await openWith(failed);
    expect(screen.getByTestId("change-verdict").getAttribute("data-look")).toBe("fail");
    expect(screen.getByRole("heading", { level: 4, name: "Try on a test copy: did not pass" })).not.toBeNull();
  });

  it("waiting for one approval: a tick and a status for the one who approved, an Approve button for the other, Apply off", async () => {
    await openWith(waitingOneApproval);
    expect(box().queryByRole("checkbox")).toBeNull();
    const rows = box().getAllByTestId("change-approval-row");
    expect(text(rows[0])).toBe("You✓ approved, 5:20 PM");
    expect(within(rows[1]!).getByRole("button", { name: "Approve as Demo reviewer A" })).not.toBeNull();
    expect(within(rows[1]!).getByText("Demo data")).not.toBeNull();
    expect((box().getByRole("button", { name: "Apply to localhost:8452" }) as HTMLButtonElement).disabled).toBe(true);
    expect(box().getByTestId("change-reason").textContent).toBe("Apply stays off until 1 more approval is in.");
  });

  it("ready to apply: Apply is on", async () => {
    await openWith(readyToApply);
    expect((box().getByRole("button", { name: "Apply to localhost:8452" }) as HTMLButtonElement).disabled).toBe(false);
    expect(box().queryByTestId("change-reason")).toBeNull();
    expect(box().getAllByTestId("change-approval-row").every((r) => within(r).queryByRole("button") === null)).toBe(true);
  });

  it("applied and matching: the After Apply part with its badge, paragraphs and history, and Roll back", async () => {
    await openWith(appliedMatches);
    const applied = within(screen.getByTestId("change-applied"));
    expect(applied.getByRole("heading", { level: 4, name: "After Apply" })).not.toBeNull();
    expect(applied.getByTestId("change-applied-badge").textContent).toContain("Applied · matches the try");
    expect(applied.queryByTestId("change-differences")).toBeNull();
    expect(applied.getAllByTestId("change-history").map((h) => h.textContent)).toEqual([
      "Applied 14 Nov 2026, 5:30 PM, by You.",
      "Rolled back 13 Nov 2026, 9:02 AM, by You.",
    ]);
    expect(box().getAllByRole("button").map((b) => b.textContent)).toEqual(["▸Details and evidence: the test copy", "Roll back", "Download change"]);
  });

  it("applied and not matching: the differences are listed and the failed step is marked", async () => {
    await openWith(appliedMismatch);
    const applied = within(screen.getByTestId("change-applied"));
    expect(applied.getByTestId("change-applied-badge").getAttribute("data-look")).toBe("fail");
    expect(within(applied.getByTestId("change-differences")).getAllByRole("listitem").map((li) => li.textContent)).toEqual(appliedMismatch.applied!.differences);
    const last = box().getAllByTestId("change-step").at(-1)!;
    expect(last.getAttribute("data-state")).toBe("failed");
    expect(text(last)).toBe("✗Measured afterdoes not match the try");
    expect(box().getByRole("button", { name: "Roll back" })).not.toBeNull();
  });

  it("a change that can't be tried: no step row, Try off with its reason, Download on", async () => {
    await openWith(cantTry);
    expect(box().queryByTestId("change-steps")).toBeNull();
    expect((box().getByRole("button", { name: "Try on a test copy" }) as HTMLButtonElement).disabled).toBe(true);
    expect(box().getByTestId("change-reason").textContent).toMatch(/^This change can't be tried here/);
    expect((box().getByRole("button", { name: "Download change" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("a text-only change: no steps, no buttons, just words", async () => {
    await openWith(textOnly);
    expect(box().queryByTestId("change-steps")).toBeNull();
    expect(box().queryAllByRole("button")).toHaveLength(0);
    expect(box().getByTestId("change-badge").textContent).toContain("Text only");
    expect(box().getByText("The server stays Classical until 14 Nov 2027, then you review it.")).not.toBeNull();
  });
});

describe("Migration 4b, the change box's buttons", () => {
  const after = { body: { ok: true } };

  it.each([
    ["Try on a test copy", readyToTry, "try"],
    ["Apply to localhost:8452", readyToApply, "apply"],
    ["Roll back", appliedMatches, "rollback"],
  ] as const)("%s calls its route with the change id, loads the view again and tells the app", async (label, change, route) => {
    const { fetchMock, onPlanChanged } = await openWith(change, { [`POST ${PLAN}/${route}`]: after });
    const before = onPlanChanged.mock.calls.length;
    fireEvent.click(box().getByRole("button", { name: label }));
    await waitFor(() => expect(calls(fetchMock).filter((c) => c === GET)).toHaveLength(2));
    expect(body(fetchMock, `POST ${PLAN}/${route}`)).toEqual({ change: CHANGE_ID });
    expect(onPlanChanged.mock.calls.length).toBe(before + 1);
  });

  it("the picker button sends the ticked reviewers, nobody else", async () => {
    const { fetchMock } = await openWith(triedPassedPicker, { [`POST ${PLAN}/ask-approval`]: after });
    // Start: you and A are ticked. Untick you, tick B.
    fireEvent.click(box().getByLabelText("You"));
    fireEvent.click(box().getByLabelText(/Demo reviewer B/));
    fireEvent.click(box().getByRole("button", { name: "Ask for approval" }));
    await waitFor(() => expect(calls(fetchMock)).toContain(`POST ${PLAN}/ask-approval`));
    expect(body(fetchMock, `POST ${PLAN}/ask-approval`)).toEqual({ change: CHANGE_ID, reviewers: ["reviewer-a", "reviewer-b"] });
  });

  it("the picker button is off with its reason when it is not enabled", async () => {
    const off: ChangeView = {
      ...triedPassedPicker,
      approvals: { ...triedPassedPicker.approvals!, picker: { ...triedPassedPicker.approvals!.picker!, enabled: false, reason: "Tick at least one reviewer." } },
    };
    await openWith(off);
    expect((box().getByRole("button", { name: "Ask for approval" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("change-picker-reason").textContent).toBe("Tick at least one reviewer.");
  });

  it("Approve sends the change and that reviewer", async () => {
    const { fetchMock } = await openWith(waitingOneApproval, { [`POST ${PLAN}/approve`]: after });
    fireEvent.click(box().getByRole("button", { name: "Approve as Demo reviewer A" }));
    await waitFor(() => expect(calls(fetchMock)).toContain(`POST ${PLAN}/approve`));
    expect(body(fetchMock, `POST ${PLAN}/approve`)).toEqual({ change: CHANGE_ID, reviewer: "reviewer-a" });
  });

  it("Download saves the change file from its own address and makes no POST", async () => {
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(String(this.getAttribute("href")));
    });
    const { fetchMock } = await openWith(readyToTry);
    fireEvent.click(box().getByRole("button", { name: "Download change" }));
    expect(saved).toEqual([`${PLAN}/download?change=${encodeURIComponent(CHANGE_ID)}`]);
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("shows the error in the box when a call fails, and does not reload", async () => {
    const { fetchMock, onPlanChanged } = await openWith(readyToTry, { [`POST ${PLAN}/try`]: ERROR("A try is already running.") });
    const before = onPlanChanged.mock.calls.length;
    fireEvent.click(box().getByRole("button", { name: "Try on a test copy" }));
    expect((await box().findByRole("alert")).textContent).toBe("A try is already running.");
    expect(calls(fetchMock)).toEqual([GET, `POST ${PLAN}/try`]);
    expect(onPlanChanged.mock.calls.length).toBe(before);
  });
});

describe("Migration 4b, polling", () => {
  it("asks again every second while a change is busy, and stops when it is not", async () => {
    let n = 0;
    const fetchMock = mockApi({
      [GET]: () => {
        n += 1;
        return { body: withChange(migrationView4b, S8452, n < 3 ? trying : readyToApply) };
      },
    });
    render(<MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />);
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    fireEvent.click(card("localhost:8452"));
    expect(screen.getByTestId("change-box").getAttribute("data-busy")).toBe("true");
    await waitFor(() => expect(screen.getByTestId("change-box").getAttribute("data-busy")).toBe("false"), { timeout: 4000 });
    expect(calls(fetchMock)).toEqual([GET, GET, GET]);
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(calls(fetchMock)).toHaveLength(3);
  });
});

describe("Migration 4b, Roadmap view", () => {
  it("draws the track between the name and the option, and keeps names as plain text", async () => {
    await open(migrationView4b);
    fireEvent.click(button("Roadmap"));
    const bands = screen.getAllByTestId("roadmap-band");
    expect(bands.map((b) => b.getAttribute("data-band"))).toEqual(["done_for_now", "phase1", "phase2", "not_placed"]);
    expect(bands.map((b) => b.getAttribute("data-look"))).toEqual(["plain", "highlight", "plain", "dashed"]);
    const phase1 = within(bands[1]!).getByTestId("roadmap-row");
    expect(text(phase1)).toBe("Serverlocalhost:8452Key exchangeHybrid recommended, not yet chosen by youTo do: turn on hybrid key exchange. View in Fixes");
    const done = within(bands[0]!).getAllByTestId("roadmap-row");
    expect(done.map((r) => text(within(r).getByTestId("roadmap-track")))).toEqual(["Key exchange", "Both tracks"]);
    // The same system can stand in two bands, once for each track.
    const phase2 = within(bands[2]!).getAllByTestId("roadmap-row");
    expect(phase2.map((r) => text(within(r).getByTestId("roadmap-track")))).toEqual(["Authentication", "Signatures"]);
    expect(within(screen.getByTestId("migration-roadmap")).queryByRole("button", { name: "localhost:8451" })).toBeNull();
  });

  it("an older answer without tracks draws an empty track cell", async () => {
    const old = { ...migrationView4b, roadmap: { ...migrationView4b.roadmap, bands: migrationView4b.roadmap.bands.map((b) => ({ ...b, rows: b.rows.map(({ track: _t, ...r }) => r) })) } };
    await open(old);
    fireEvent.click(button("Roadmap"));
    expect(screen.getAllByTestId("roadmap-track").every((c) => c.textContent === "")).toBe(true);
  });
});

describe("Fixes 4b, the change box in an entry", () => {
  function fixesWithChange(change: ChangeView | null): FixesView {
    const base = fixesViews.ready;
    return { ...base, fixes: base.fixes.map((f) => (f.id === TLS_FIX ? { ...f, change_box: change } : f)) };
  }

  async function openFixes(view: FixesView, routes: Parameters<typeof mockApi>[0] = {}, onPlanChanged = vi.fn()) {
    const fetchMock = mockApi({ "GET /api/plans/1/fixes": { body: view }, ...routes });
    render(<FixesScreen planId={1} selectedId={TLS_FIX} onSelect={vi.fn()} onRetestStarted={vi.fn()} onPlanChanged={onPlanChanged} />);
    await screen.findByTestId("fix-summary");
    return { fetchMock, onPlanChanged };
  }

  it("draws the change box above the fix's sections, and nothing without one", async () => {
    await openFixes(fixesWithChange(tlsChange));
    const changeBox = screen.getByTestId("change-box");
    expect(changeBox.getAttribute("data-change")).toBe(TLS_CHANGE_ID);
    const firstSection = screen.getAllByTestId("fix-section")[0]!;
    expect(changeBox.compareDocumentPosition(firstSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: tlsChange.title })).not.toBeNull();
  });

  it("draws no change box for a fix without one, or an old answer lacking the field", async () => {
    await openFixes(fixesWithChange(null));
    expect(screen.queryByTestId("change-box")).toBeNull();
  });

  it("its Try button calls the change route, loads the fixes again and tells the app", async () => {
    const { fetchMock, onPlanChanged } = await openFixes(fixesWithChange(tlsChange), { [`POST ${PLAN}/try`]: { body: { ok: true } } });
    fireEvent.click(box().getByRole("button", { name: "Try on a test copy" }));
    await waitFor(() => expect(calls(fetchMock).filter((c) => c === "GET /api/plans/1/fixes")).toHaveLength(2));
    expect(body(fetchMock, `POST ${PLAN}/try`)).toEqual({ change: TLS_CHANGE_ID });
    expect(onPlanChanged).toHaveBeenCalledTimes(1);
  });

  it("asks again every second while a change is busy", async () => {
    let n = 0;
    const fetchMock = mockApi({
      "GET /api/plans/1/fixes": () => {
        n += 1;
        return { body: fixesWithChange(n < 2 ? { ...tlsChange, busy: true } : tlsChange) };
      },
    });
    render(<FixesScreen planId={1} selectedId={TLS_FIX} onSelect={vi.fn()} onRetestStarted={vi.fn()} />);
    await screen.findByTestId("change-box");
    await waitFor(() => expect(screen.getByTestId("change-box").getAttribute("data-busy")).toBe("false"), { timeout: 3000 });
    expect(calls(fetchMock)).toHaveLength(2);
  });
});
