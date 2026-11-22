import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AdvisoriesView } from "../api";
import { AdvisoriesScreen } from "../components/AdvisoriesScreen";
import { NewAdvisories } from "../components/advisories/NewAdvisories";
import { LinkProvider } from "../components/related";
import { ReadOnlyProvider } from "../readOnly";
import { calls, mockApi, text } from "./fixtures";
import { advisoriesNotAdded } from "./ottoFixtures";

/** Phase 6, Otto's research loop: the block "New advisories" on the Advisories page. Every word here stands in for the
 * backend's. Two buttons, each behind a box that says what it will do; nothing is sent before the box's own button. */

type Lookup = NonNullable<AdvisoriesView["lookup"]>;
type Row = NonNullable<Lookup["last"]>["rows"][number];
const LOOK = "POST /api/plans/7/advisories/look";
const RESEARCH = "POST /api/plans/7/advisories/research";
const NEEDS_ISOLATED = "Trying a test on public copies needs isolated mode (Docker): a real library runs only in its own locked-down container.";

function row(over: Partial<Row> = {}): Row {
  return {
    id: "CVE-2099-0001",
    title: "Written for a test: fixed in a version the app has",
    library: "elliptic",
    published: "2 January 2099",
    fits: "Names elliptic 6.5.6, which your dependency list lists; fixed in 6.5.7.",
    state: { key: "new", label: "New: not tried yet", tone: "warn" },
    reason: null,
    link: null,
    publisher: "GitHub Advisory Database",
    url: "https://osv.dev/vulnerability/GHSA-test-0001-aaaa",
    ...over,
  };
}

function block(over: Partial<Lookup> = {}): Lookup {
  return {
    title: "New advisories",
    intro: "Published advisories about the libraries this assessment names, read from a public source. A check is proposed only after its test was proven on public copies.",
    covers: "What this covers: libraries published on npm, PyPI, Go, Maven, crates.io, NuGet and RubyGems, asked about by name at OSV (osv.dev). Anything else reads “No test yet”, with the reason.",
    libraries_line: "This assessment names: elliptic 6.5.6 and python-ecdsa 0.13.2.",
    look: {
      label: "Look for new advisories",
      can: true,
      blocked_reason: null,
      dialog: {
        title: "Look for new advisories?",
        lines: [
          "Asks OSV (osv.dev), a public database of published advisories, about the libraries this assessment names.",
          "What is sent: these package names, and nothing else: ecdsa (PyPI) and elliptic (npm).",
          "No version, no address and no file leaves this computer. Whether an advisory names a version you have is worked out here.",
          "Reading is free: Claude is not asked, nothing runs, and nothing is proposed by looking.",
        ],
        confirm: "Look",
        cancel: "Cancel",
      },
    },
    last: null,
    research: {
      label: "Design and prove tests",
      can: false,
      blocked_reason: null,
      shown: false,
      dialog: { title: "Design and prove tests for 2 advisories?", lines: ["A test counts as proven only when it fails on the affected version, passes on the fixed version, and the control that must fail does.", "Each proven check then arrives on this page as a proposal. Accepting or rejecting it stays with you: nothing is added to a test plan, and nothing of yours is run."], confirm: "Start", cancel: "Cancel" },
      progress: null,
    },
    busy: false,
    ...over,
  };
}

const looked = (over: Partial<Lookup> = {}): Lookup =>
  block({
    last: {
      line: "Looked on 19 November 2026, 12:10 am EST by You: 3 published advisories about your libraries. 1 is new and can be tried here, 1 has no test yet and 1 is in a test pack already.",
      source_line: "Read from OSV (osv.dev). Sent: ecdsa (PyPI) and elliptic (npm), and nothing else.",
      notes: ["2 records were left out: not in the shape the source documents, or about no version of these libraries."],
      rows: [
        row(),
        row({ id: "CVE-2099-0002", state: { key: "no_test", label: "No test yet", tone: "neutral" }, reason: "No test yet: a test is proven against the fixed version, elliptic 6.6.1, and this version of the app has no public copy of it (it has elliptic 6.5.6 and elliptic 6.5.7), so none was designed." }),
        row({ id: "CVE-2022-21449", state: { key: "in_pack", label: "Proven on public copies (test pack 2026.11.1)", tone: "pass" }, reason: "It is in the list below, with its proposal.", link: { page: "advisories", item: "CVE-2022-21449" } }),
      ],
      empty: null,
    },
    research: { ...block().research, label: "Design and prove tests (1)", shown: true, can: true },
    ...over,
  });

const view = (lookup: Lookup): AdvisoriesView => ({ ...advisoriesNotAdded, lookup });

function Block({ lookup, onView = () => undefined, closed = false }: { lookup: Lookup; onView?: (next: AdvisoriesView) => void; closed?: boolean }) {
  return (
    <ReadOnlyProvider readOnly={closed}>
      <LinkProvider assessmentId={101} planId={7}>
        <NewAdvisories planId={7} lookup={lookup} onView={onView} />
      </LinkProvider>
    </ReadOnlyProvider>
  );
}

describe("New advisories: before a look", () => {
  it("says what it is, which libraries the assessment names and what it covers, and sends nothing by being shown", () => {
    const fetchMock = mockApi({});
    render(<Block lookup={block()} />);
    const box = screen.getByTestId("new-advisories");
    expect(within(box).getByRole("heading", { level: 2, name: "New advisories" })).not.toBeNull();
    expect(text(within(box).getByTestId("new-advisories-libraries"))).toBe("This assessment names: elliptic 6.5.6 and python-ecdsa 0.13.2.");
    expect(text(within(box).getByTestId("new-advisories-covers"))).toContain("Anything else reads “No test yet”, with the reason.");
    expect(within(box).getByRole("button", { name: "Look for new advisories" })).not.toBeNull();
    expect(within(box).queryByTestId("design-and-prove")).toBeNull(); // not before a look
    expect(calls(fetchMock)).toEqual([]);
  });

  it("Look for new advisories first says exactly what will be sent; Cancel sends nothing; Look sends one request", async () => {
    const fetchMock = mockApi({ [LOOK]: { body: view(looked()) } });
    const seen = vi.fn();
    render(<Block lookup={block()} onView={seen} />);
    fireEvent.click(screen.getByTestId("look-for-advisories"));
    const box = screen.getByTestId("look-dialog");
    expect(within(box).getAllByRole("listitem").map((li) => text(li))).toEqual(block().look.dialog.lines);
    expect(text(box)).toContain("What is sent: these package names, and nothing else: ecdsa (PyPI) and elliptic (npm).");
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(within(box).getByTestId("lookup-cancel"));
    expect(screen.queryByTestId("look-dialog")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);

    fireEvent.click(screen.getByTestId("look-for-advisories"));
    fireEvent.click(screen.getByTestId("lookup-confirm"));
    await waitFor(() => expect(seen).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([LOOK]);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeUndefined(); // the request names the plan in its address and carries nothing else
    expect(screen.queryByTestId("look-dialog")).toBeNull();
  });

  it("is off with the backend's reason where a look can't be made", () => {
    const why = "This assessment names no library the source keeps by name.";
    const fetchMock = mockApi({});
    render(<Block lookup={block({ look: { ...block().look, can: false, blocked_reason: why } })} />);
    expect((screen.getByTestId("look-for-advisories") as HTMLButtonElement).disabled).toBe(true);
    expect(text(screen.getByTestId("look-blocked"))).toBe(why);
    fireEvent.click(screen.getByTestId("look-for-advisories"));
    expect(screen.queryByTestId("look-dialog")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("shows the server's own sentence when the source could not be read", async () => {
    mockApi({ [LOOK]: { status: 409, body: { error: { message: "OSV (osv.dev) could not be reached (OSError). Nothing was changed.", line: null, field: null } } } });
    render(<Block lookup={block()} />);
    fireEvent.click(screen.getByTestId("look-for-advisories"));
    fireEvent.click(screen.getByTestId("lookup-confirm"));
    expect(text(await screen.findByTestId("new-advisories-error"))).toContain("OSV (osv.dev) could not be reached (OSError). Nothing was changed.");
  });
});

describe("New advisories: after a look", () => {
  it("lists what was found, each with where it stands and why there is no test yet", () => {
    render(<Block lookup={looked()} />);
    expect(text(screen.getByTestId("look-line"))).toContain("3 published advisories about your libraries.");
    expect(text(screen.getByTestId("look-source"))).toBe("Read from OSV (osv.dev). Sent: ecdsa (PyPI) and elliptic (npm), and nothing else.");
    expect(screen.getAllByTestId("look-note")).toHaveLength(1);
    const rows = screen.getAllByTestId("found-advisory");
    expect(rows.map((r) => [r.getAttribute("data-advisory"), r.getAttribute("data-state"), text(within(r).getByTestId("found-state"))])).toEqual([
      ["CVE-2099-0001", "new", "New: not tried yet"],
      ["CVE-2099-0002", "no_test", "No test yet"],
      ["CVE-2022-21449", "in_pack", "Proven on public copies (test pack 2026.11.1)"],
    ]);
    expect(text(within(rows[0] as HTMLElement).getByTestId("found-fits"))).toBe("Names elliptic 6.5.6, which your dependency list lists; fixed in 6.5.7.");
    expect(within(rows[0] as HTMLElement).queryByTestId("found-reason")).toBeNull();
    expect(text(within(rows[1] as HTMLElement).getByTestId("found-reason"))).toContain("this version of the app has no public copy of it");
    // one already in a test pack opens its row in the list below; every row links to its publisher's page
    expect(within(rows[2] as HTMLElement).getByTestId("found-link").getAttribute("href")).toBe("#/a/101/advisories?item=CVE-2022-21449");
    const source = within(rows[0] as HTMLElement).getByTestId("found-source");
    expect(source.getAttribute("href")).toBe("https://osv.dev/vulnerability/GHSA-test-0001-aaaa");
    expect(source.getAttribute("rel")).toBe("noopener noreferrer");
    // nothing about how serious an advisory is
    expect(text(screen.getByTestId("new-advisories"))).not.toMatch(/severity|critical|score|CVSS/i);
  });

  it("Design and prove tests first says what it will do; Cancel starts nothing; Start sends one request", async () => {
    const running = looked({ busy: true, research: { ...looked().research, can: false, blocked_reason: "A research run is going on. Wait for it to finish.", progress: { line: "A research run is going on, started on 19 November 2026, 12:12 am EST.", running: true, title: "What the research run said", lines: [] } } });
    const fetchMock = mockApi({ [RESEARCH]: { body: view(running) } });
    const seen = vi.fn();
    render(<Block lookup={looked()} onView={seen} />);
    expect(text(screen.getByTestId("design-and-prove"))).toBe("Design and prove tests (1)");
    fireEvent.click(screen.getByTestId("design-and-prove"));
    const box = screen.getByTestId("research-dialog");
    expect(text(box)).toContain("it fails on the affected version, passes on the fixed version, and the control that must fail does");
    expect(text(box)).toContain("Accepting or rejecting it stays with you");
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(within(box).getByTestId("lookup-cancel"));
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(screen.getByTestId("design-and-prove"));
    fireEvent.click(screen.getByTestId("lookup-confirm"));
    await waitFor(() => expect(seen).toHaveBeenCalledTimes(1));
    expect(calls(fetchMock)).toEqual([RESEARCH]);
  });

  it("is off with the backend's reason in demo mode, and in a closed assessment both buttons are off", () => {
    const fetchMock = mockApi({});
    const first = render(<Block lookup={looked({ research: { ...looked().research, can: false, blocked_reason: NEEDS_ISOLATED } })} />);
    expect((screen.getByTestId("design-and-prove") as HTMLButtonElement).disabled).toBe(true);
    expect(text(screen.getByTestId("research-blocked"))).toBe(NEEDS_ISOLATED);
    first.unmount();
    const closedWhy = "This assessment is closed. Start a new one to continue.";
    render(<Block closed lookup={looked({ look: { ...block().look, can: false, blocked_reason: closedWhy }, research: { ...looked().research, can: false, blocked_reason: closedWhy } })} />);
    expect((screen.getByTestId("look-for-advisories") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("design-and-prove") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByTestId("found-advisory")).toHaveLength(3); // what was found before closing is still shown
    expect(calls(fetchMock)).toEqual([]);
  });

  it("shows how a research run is going, and what it said", () => {
    const lines = ["Reading CVE-2099-0001", "CVE-2099-0001: the trial of its design is registered (elliptic 6.5.6 against 6.5.7, 12 cases)."];
    render(<Block lookup={looked({ busy: true, research: { ...looked().research, can: false, blocked_reason: "A research run is going on. Wait for it to finish.", progress: { line: "A research run is going on, started on 19 November 2026, 12:12 am EST.", running: true, title: "What the research run said", lines } } })} />);
    const progress = screen.getByTestId("research-progress");
    expect(progress.getAttribute("data-running")).toBe("true");
    expect(text(within(progress).getByTestId("research-line"))).toContain("A research run is going on");
    expect(within(progress).getAllByRole("listitem").map((li) => text(li))).toEqual(lines);
    expect(text(screen.getByTestId("research-blocked"))).toBe("A research run is going on. Wait for it to finish.");
  });
});

describe("the Advisories page with the block", () => {
  it("draws the block above the list, and asks again while a research run goes on", async () => {
    let reads = 0;
    const running = looked({ busy: true, research: { ...looked().research, can: false, blocked_reason: "A research run is going on. Wait for it to finish.", progress: { line: "A research run is going on, started on 19 November 2026, 12:12 am EST.", running: true, title: "What the research run said", lines: [] } } });
    const done = looked({ research: { ...looked().research, progress: { line: "The research run that started on 19 November 2026, 12:12 am EST finished on 19 November 2026, 12:20 am EST. Test pack 2026.11.3, made on this computer, was installed.", running: false, title: "What the research run said", lines: ["done"] } } });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockApi({
      "GET /api/plans/7/advisories": () => {
        reads += 1;
        return { body: view(reads < 2 ? running : done) };
      },
    });
    render(
      <LinkProvider assessmentId={101} planId={7}>
        <AdvisoriesScreen planId={7} />
      </LinkProvider>,
    );
    expect(text(await screen.findByTestId("research-line"))).toContain("A research run is going on");
    expect(screen.getByTestId("advisories-table")).not.toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3200);
    });
    await waitFor(() => expect(text(screen.getByTestId("research-line"))).toContain("Test pack 2026.11.3, made on this computer, was installed."));
    expect(reads).toBe(2);
    // once the run has ended the page stops asking
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(reads).toBe(2);
  });

  it("an older answer of the server without the block still draws the page", async () => {
    mockApi({ "GET /api/plans/7/advisories": { body: advisoriesNotAdded } });
    render(
      <LinkProvider assessmentId={101} planId={7}>
        <AdvisoriesScreen planId={7} />
      </LinkProvider>,
    );
    await screen.findByTestId("advisories-table");
    expect(screen.queryByTestId("new-advisories")).toBeNull();
  });
});
