import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MigrationView, OttoProposal, OttoRoadmapMark } from "../api";
import { MigrationScreen, type MigrationTab } from "../components/MigrationScreen";
import { ReadOnlyProvider } from "../readOnly";
import { calls, mockApi, text } from "./fixtures";
import { migrationView4b, withSystem } from "./migrationFixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

/** Phase 5c: Otto's proposed changes to the migration plan, on the system each is about (Systems) and as a mark on its
 * roadmap rows (Roadmap). Otto proposes; a person decides. Every word below stands in for the backend's. */

const GET = "GET /api/import/7/migration";
const SIGN = "software:acme-sign-1.4.2";
const ID = "plan-cf5bb2394033";
const decide = (decision: string) => `POST /api/plans/1/otto/proposals/${ID}/${decision}`;
const ERROR = (message: string, status = 409) => ({ status, body: { error: { message, line: null, field: null } } });

const BLOCK = {
  title: "From Otto: proposed changes to this system's plan",
  note:
    "Otto proposes these from results. Accept adds one to the plan as something to fix first; Reject keeps the plan as it was, with " +
    "your reason. Neither changes a status or a measurement.",
};
const TITLE = "Fix acme-sign 1.4.2 before its signatures move to post-quantum";
const EFFECT = "On the plan: something to fix first, on the Signatures track.";
const PLAN: Partial<OttoProposal> = {
  id: ID,
  kind: "plan",
  kind_label: "plan change",
  title: TITLE,
  why:
    "acme-sign 1.4.2 gave the wrong answer on 3 published cases of the kind CVE-2022-21449 describes (Missing ECDSA signature range " +
    "check). Moving a program that checks signatures wrongly carries the fault along.",
  why_label: "Why Otto proposes it",
  lines: [
    "Otto proposes to add this to the migration plan, on the Signatures track, as something to fix first.",
    "Accepting changes nothing on any system and runs nothing. It is taken off again when a newer result of this check passes.",
  ],
  link: { page: "migration/systems", item: SIGN },
};
const proposed = proposal({
  ...PLAN,
  note: "Accept adds this to the migration plan as something to fix first. It runs nothing and changes nothing on any system.",
});
const accepted = acceptedProposal({
  ...PLAN,
  status: { key: "accepted", word: "Accepted", tone: "pass" },
  effect: EFFECT,
  note: "Undo takes it off the plan again.",
});
const rejected = rejectedProposal("Not before the audit", PLAN);

const WAITING: OttoRoadmapMark = { label: "From Otto", text: "1 proposal waiting for your decision", tone: "warn", waiting: 1 };
const ON_PLAN: OttoRoadmapMark = { label: "From Otto", text: EFFECT, tone: "neutral", waiting: 0 };
const NOT_ADDED: OttoRoadmapMark = { label: "From Otto", text: "Not added (Not before the audit)", tone: "neutral", waiting: 0 };

/** The 4b demo view with one proposal of Otto's for acme-sign 1.4.2: in its panel and as the mark on its roadmap row. */
function withOtto(p: OttoProposal, mark: OttoRoadmapMark): MigrationView {
  const view = withSystem(migrationView4b, SIGN, { otto: { ...BLOCK, proposals: [p] } });
  return {
    ...view,
    roadmap: {
      ...view.roadmap,
      bands: view.roadmap.bands.map((band) => ({ ...band, rows: band.rows.map((row) => (row.system_key === SIGN ? { ...row, otto: mark } : row)) })),
    },
  };
}

afterEach(() => vi.restoreAllMocks());

/** Opens the Migration step. `views` are the answers of the page's own GET, in order (the last one repeats). */
async function open(views: MigrationView[], routes: Parameters<typeof mockApi>[0] = {}, opts: { tab?: MigrationTab; readOnly?: boolean } = {}) {
  let n = 0;
  const fetchMock = mockApi({ [GET]: () => ({ body: views[Math.min(n++, views.length - 1)] }), ...routes });
  const props = { onViewFix: vi.fn(), onPlanChanged: vi.fn() };
  render(
    <ReadOnlyProvider readOnly={opts.readOnly ?? false}>
      <MigrationScreen importId={7} tab={opts.tab} {...props} />
    </ReadOnlyProvider>,
  );
  await screen.findByRole("heading", { level: 1, name: views[0]!.title });
  return { fetchMock, ...props };
}

const card = (name: string) => screen.getAllByTestId("system-card").find((c) => c.textContent?.includes(name))!;
const block = () => within(screen.getByTestId("system-otto"));
const sent = (fetchMock: ReturnType<typeof mockApi>, key: string) => {
  const found = fetchMock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${String(url)}` === key).at(-1);
  return JSON.parse(String(found?.[1]?.body));
};
/** Is `a` drawn before `b` on the page? */
const before = (a: HTMLElement, b: HTMLElement) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("Migration, Systems: Otto's proposed change to a system's plan", () => {
  it("shows the proposal in the system's panel, under its tracks, and opening the page sends its one GET and nothing else", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING)]);
    fireEvent.click(card("acme-sign 1.4.2"));
    const box = screen.getByTestId("system-otto");
    expect(text(within(box).getByRole("heading", { level: 3 }))).toBe(BLOCK.title);
    expect(text(block().getByTestId("system-otto-note"))).toBe(BLOCK.note);
    expect(text(block().getByTestId("proposal-label"))).toBe("From Otto");
    expect(text(block().getByTestId("proposal-status"))).toBe("Proposed");
    expect(text(block().getByTestId("proposal-title"))).toBe(TITLE);
    expect(text(block().getByTestId("proposal-why"))).toContain("Why Otto proposes it:");
    expect(text(block().getByTestId("proposal-note"))).toContain("It runs nothing and changes nothing on any system.");
    expect((block().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
    expect((block().getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(false);
    // right under the tracks (the Today box), before the settings and everything after them
    expect(before(screen.getByTestId("migration-today"), box)).toBe(true);
    expect(before(box, screen.getByTestId("migration-settings"))).toBe(true);
    // nothing runs without a click: no measurement, no decision, no other request
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("marks the system's row in the Systems table with Otto's tag and where the proposal stands", async () => {
    await open([withOtto(proposed, WAITING)]);
    expect(text(within(card("acme-sign 1.4.2")).getByTestId("system-otto-mark"))).toBe("From OttoProposed");
    expect(screen.getAllByTestId("system-otto-mark")).toHaveLength(1);
    // with the panel closed the full row carries the same mark
    fireEvent.click(within(screen.getByTestId("detail-panel")).getByRole("button", { name: "Close details" }));
    expect(text(within(card("acme-sign 1.4.2")).getByTestId("system-otto-mark"))).toBe("From OttoProposed");
  });

  it("Accept sends one POST to the decide route, then reads the migration view again and tells the app", async () => {
    const { fetchMock, onPlanChanged } = await open([withOtto(proposed, WAITING), withOtto(accepted, ON_PLAN)], { [decide("accept")]: { body: accepted } });
    fireEvent.click(card("acme-sign 1.4.2"));
    expect(onPlanChanged).toHaveBeenCalledTimes(1);
    fireEvent.click(block().getByTestId("proposal-accept"));
    await waitFor(() => expect(text(block().getByTestId("proposal-status"))).toBe("Accepted"));
    expect(calls(fetchMock)).toEqual([GET, decide("accept"), GET]);
    expect(sent(fetchMock, decide("accept"))).toEqual({});
    expect(text(block().getByTestId("proposal-decided"))).toBe("Accepted by You on 18 November 2026, 10:02 UTC.");
    expect(text(block().getByTestId("proposal-effect"))).toBe(EFFECT);
    expect(block().queryByTestId("proposal-accept")).toBeNull();
    expect((block().getByTestId("proposal-undo") as HTMLButtonElement).disabled).toBe(false);
    expect(text(within(card("acme-sign 1.4.2")).getByTestId("system-otto-mark"))).toBe("From OttoAccepted");
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(2));
  });

  it("Reject asks for a reason, sends it, and the proposal stays as Not added with that reason", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING), withOtto(rejected, NOT_ADDED)], { [decide("reject")]: { body: rejected } });
    fireEvent.click(card("acme-sign 1.4.2"));
    fireEvent.click(block().getByTestId("proposal-reject"));
    // the box asks first: until it is confirmed nothing is sent
    expect(calls(fetchMock)).toEqual([GET]);
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "Not before the audit" } });
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(text(block().getByTestId("proposal-status"))).toBe("Not added (Not before the audit)"));
    expect(calls(fetchMock)).toEqual([GET, decide("reject"), GET]);
    expect(sent(fetchMock, decide("reject"))).toEqual({ reason: "Not before the audit" });
    expect(text(block().getByTestId("proposal-decided"))).toContain("Reason: Not before the audit");
    // not deleted: it is still there, and can be taken up again
    expect(text(block().getByTestId("proposal-title"))).toBe(TITLE);
    expect((block().getByTestId("proposal-reconsider") as HTMLButtonElement).disabled).toBe(false);
    expect(block().queryByTestId("proposal-accept")).toBeNull();
  });

  it("Undo of an accept sends one POST and the proposal is open for a decision again", async () => {
    const { fetchMock } = await open([withOtto(accepted, ON_PLAN), withOtto(proposed, WAITING)], { [decide("undo")]: { body: proposed } });
    fireEvent.click(card("acme-sign 1.4.2"));
    fireEvent.click(block().getByTestId("proposal-undo"));
    await waitFor(() => expect(text(block().getByTestId("proposal-status"))).toBe("Proposed"));
    expect(calls(fetchMock)).toEqual([GET, decide("undo"), GET]);
    expect(sent(fetchMock, decide("undo"))).toEqual({});
    expect((block().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
  });

  it("a decision the backend refuses is shown in its words, and the view is not read again", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING)], {
      [decide("accept")]: ERROR("Otto is not installed on this computer. A decision on one of Otto's proposals is recorded in Otto's ledger, so nothing can be decided here."),
    });
    fireEvent.click(card("acme-sign 1.4.2"));
    fireEvent.click(block().getByTestId("proposal-accept"));
    await waitFor(() => expect(text(screen.getByTestId("system-otto"))).toContain("Otto is not installed on this computer."));
    expect(calls(fetchMock)).toEqual([GET, decide("accept")]);
    expect(text(block().getByTestId("proposal-status"))).toBe("Proposed");
  });

  it("says so when the view can't be read again after a decision", async () => {
    let n = 0;
    const fetchMock = mockApi({
      [GET]: () => (n++ === 0 ? { body: withOtto(proposed, WAITING) } : ERROR("The migration plan could not be read.", 500)),
      [decide("accept")]: { body: accepted },
    });
    render(<MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />);
    await screen.findByRole("heading", { level: 1, name: migrationView4b.title });
    fireEvent.click(card("acme-sign 1.4.2"));
    fireEvent.click(block().getByTestId("proposal-accept"));
    await waitFor(() => expect(text(screen.getByTestId("system-otto"))).toContain("The migration plan could not be read."));
    expect(calls(fetchMock)).toEqual([GET, decide("accept"), GET]);
  });

  it("in a closed assessment the decision buttons are off", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING)], {}, { readOnly: true });
    fireEvent.click(card("acme-sign 1.4.2"));
    expect((block().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(true);
    expect((block().getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(block().getByTestId("proposal-accept"));
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("a system with no proposal, and a view without the new fields, draw no Otto block and no mark", async () => {
    await open([withOtto(proposed, WAITING)]);
    // the first system (open by default) has no proposal
    expect(screen.queryByTestId("system-otto")).toBeNull();
    expect(within(card("localhost:8451")).queryByTestId("system-otto-mark")).toBeNull();
  });

  it("the view as it was before this phase renders exactly as before", async () => {
    await open([migrationView4b]);
    fireEvent.click(card("acme-sign 1.4.2"));
    expect(screen.queryByTestId("system-otto")).toBeNull();
    expect(screen.queryAllByTestId("system-otto-mark")).toHaveLength(0);
    expect(screen.queryAllByTestId("otto-proposal")).toHaveLength(0);
    expect(document.body.textContent).not.toContain("From Otto");
  });
});

describe("Migration, Roadmap: the mark of a proposal of Otto's", () => {
  const rowOf = (el: HTMLElement) => el.closest('[data-testid="roadmap-row"]') as HTMLElement;

  it("marks the system's row with Otto's tag and the view's words while a proposal waits, and sends nothing", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING)], {}, { tab: "roadmap" });
    const marks = screen.getAllByTestId("roadmap-otto");
    expect(marks).toHaveLength(1);
    const mark = marks[0]!;
    expect(rowOf(mark).getAttribute("data-system")).toBe(SIGN);
    expect(text(within(mark).getByTestId("roadmap-otto-label"))).toBe("From Otto");
    expect(text(mark)).toBe("From Otto1 proposal waiting for your decision");
    expect(mark.getAttribute("data-waiting")).toBe("1");
    expect(mark.getAttribute("data-tone")).toBe("warn");
    // the mark is not a button and holds none: the decision buttons are in the system's panel
    expect(within(mark).queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryByTestId("otto-proposal")).toBeNull();
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("the row opens the system's panel, where the proposal and its buttons are; the mark stays on the stacked row", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING)], {}, { tab: "roadmap" });
    // the four-column form: the mark spans the row on a line of its own
    expect(screen.getByTestId("roadmap-otto").className).toContain("@2xl:col-span-4");
    fireEvent.click(screen.getByTestId("roadmap-otto"));
    expect(text(block().getByTestId("proposal-title"))).toBe(TITLE);
    expect((block().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
    // beside the open panel the row stacks in two columns, and the mark spans both
    expect(screen.getByTestId("migration-roadmap").getAttribute("data-compact")).toBe("true");
    expect(screen.getByTestId("roadmap-otto").className).toContain("col-span-2");
    expect(text(screen.getByTestId("roadmap-otto"))).toBe("From Otto1 proposal waiting for your decision");
    // opening the panel decided nothing
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("Accept from the roadmap's panel reads the view again, and the mark then says what was accepted", async () => {
    const { fetchMock } = await open([withOtto(proposed, WAITING), withOtto(accepted, ON_PLAN)], { [decide("accept")]: { body: accepted } }, { tab: "roadmap" });
    fireEvent.click(screen.getByTestId("roadmap-otto"));
    fireEvent.click(block().getByTestId("proposal-accept"));
    await waitFor(() => expect(screen.getByTestId("roadmap-otto").getAttribute("data-waiting")).toBe("0"));
    expect(calls(fetchMock)).toEqual([GET, decide("accept"), GET]);
    const mark = screen.getByTestId("roadmap-otto");
    expect(text(mark)).toBe(`From Otto${EFFECT}`);
    expect(mark.getAttribute("data-tone")).toBe("neutral");
    expect(text(block().getByTestId("proposal-status"))).toBe("Accepted");
  });

  it("a rejected proposal's mark repeats the view's words, with its reason", async () => {
    await open([withOtto(rejected, NOT_ADDED)], {}, { tab: "roadmap" });
    expect(text(screen.getByTestId("roadmap-otto"))).toBe("From OttoNot added (Not before the audit)");
  });

  it("rows of other systems, and a roadmap without the new field, carry no mark", async () => {
    await open([withOtto(proposed, WAITING)], {}, { tab: "roadmap" });
    const others = screen.getAllByTestId("roadmap-row").filter((r) => r.getAttribute("data-system") !== SIGN);
    expect(others.length).toBeGreaterThan(0);
    for (const row of others) expect(within(row).queryByTestId("roadmap-otto")).toBeNull();
  });

  it("the roadmap as it was before this phase renders exactly as before", async () => {
    await open([migrationView4b], {}, { tab: "roadmap" });
    expect(screen.queryAllByTestId("roadmap-otto")).toHaveLength(0);
    expect(document.body.textContent).not.toContain("From Otto");
  });
});
