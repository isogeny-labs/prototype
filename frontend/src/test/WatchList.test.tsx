import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChangeWatchView, WatchListView } from "../api";
import { ChangeWatchPage } from "../components/ChangeWatchPage";
import { LinkProvider } from "../components/related";
import { prefs } from "../prefs";
import { calls, mockApi } from "./fixtures";
import { FIXED_ITEM, ITEM, QUOTE_TAG, watchClosed, watchEmpty, watchOff, watchOne, watchStopped, watchTwo } from "./watchFixtures";

type Routes = Parameters<typeof mockApi>[0];
const CHANGES = "GET /api/plans/1/change-watch";
const LIST = "GET /api/plans/1/watch-list";
const LOOK = "POST /api/plans/1/watch-list/look";
const STOP = "POST /api/plans/1/watch-list/stop";
const AGAIN = "POST /api/plans/1/watch-list/watch";

const changes: ChangeWatchView = {
  plan_id: 1,
  title: "Change watch",
  subline: "A developer's change in the connected demo repository, the tests picked for it, and what they show once you run them. Nothing runs by itself.",
  code: { state: "connected", line: null, link: null, connected_line: "Connected: the demo repository acme-sign, branch main." },
  menu: { button: "Bring in a demo change", note: "It runs nothing.", items: [] },
  changes: [],
  empty: "No developer's change is in the connected repository yet.",
  busy: false,
};

function open(list: WatchListView | "fails", routes: Routes = {}, props: { openItem?: string | null; section?: string | null } = {}) {
  const fetchMock = mockApi({
    [CHANGES]: { body: changes },
    ...(list === "fails" ? { [LIST]: { status: 500, body: { error: { message: "Not now.", line: null, field: null } } } } : { [LIST]: { body: list } }),
    ...routes,
  });
  render(
    <LinkProvider assessmentId={101} planId={1}>
      <ChangeWatchPage planId={1} openItem={props.openItem ?? null} section={props.section ?? null} />
    </LinkProvider>,
  );
  return { fetchMock };
}

const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c.startsWith("POST"));
function sent(fetchMock: ReturnType<typeof mockApi>, path: string): unknown[] {
  return fetchMock.mock.calls
    .filter(([input, init]) => String(input) === path && init?.method === "POST")
    .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : null));
}
const tab = (name: string) => screen.getByRole("tab", { name });
const rowsOf = (testId: string) => within(screen.getByTestId(testId)).queryAllByTestId("watch-row");

/** Presses what `find` finds in the very moment it is first in the page: after React has drawn the list for the first
 * time and before the work React leaves for after a drawing. The first drawing is made slow on purpose, because React
 * only leaves that work for a later turn when a drawing took longer than its 5 ms slice. Nobody clicks that fast in a
 * browser; a test on a busy computer does (one run of the GitHub checks did, on 22 November 2026). */
function pressAtFirstSight(find: () => HTMLElement | null | undefined): Promise<void> {
  const real = prefs.panelWidth;
  const slow = vi.spyOn(prefs, "panelWidth").mockImplementation(() => {
    const until = performance.now() + 12;
    while (performance.now() < until);
    return real();
  });
  return new Promise((resolve) => {
    const seen = new MutationObserver(() => {
      const found = find();
      if (!found) return;
      seen.disconnect();
      slow.mockRestore();
      fireEvent.click(found);
      resolve();
    });
    seen.observe(document.body, { childList: true, subtree: true });
  });
}

describe("Change watch: the Watch list (sandbox research, a prototype)", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("with Sandbox research off the page is the Changes view exactly as before: no tabs, nothing more", async () => {
    const { fetchMock } = open(watchOff);
    await screen.findByTestId("change-watch-page");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByTestId("watch-list-page")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
  });

  it("is the Changes view too when the list can't be read", async () => {
    open("fails");
    await screen.findByTestId("change-watch-page");
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("with it on the page has two views, opens on Changes, and reading sends nothing", async () => {
    const { fetchMock } = open(watchOne);
    await screen.findByRole("tablist");
    expect(tab("Changes").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("change-watch-page")).not.toBeNull();
    fireEvent.click(tab("Watch list"));
    await screen.findByTestId("watch-list-page");
    expect(tab("Watch list").getAttribute("aria-selected")).toBe("true");
    const [row] = rowsOf("watch-table");
    expect(row?.getAttribute("data-item")).toBe(ITEM);
    expect(row?.getAttribute("data-status")).toBe("no_fix");
    expect(within(row!).getByTestId("watch-status").textContent).toContain("No fix yet");
    expect(within(row!).getByTestId("watch-status-line").textContent).toBe("No fix published for 670 days.");
    expect(within(row!).getByTestId("watch-new").textContent).toBe("New");
    expect(within(row!).getByTestId("source-tag").textContent).toContain("Published");
    expect(screen.getByTestId("watch-count-line").textContent).toBe("1 published weakness in your libraries has no fix yet.");
    expect(screen.getByTestId("watch-looked-line").textContent).toContain("Looked on 22 November 2026, 09:12 UTC by You.");
    expect(screen.getByTestId("watch-next-line").textContent).toBe("It is looked at again by itself, about once a day.");
    expect(screen.getByTestId("watch-note").textContent).toContain("It is not a result.");
    expect(posts(fetchMock)).toEqual([]);
  });

  it("a link that names the Watch list opens it, and one that names an item opens that item's panel", async () => {
    open(watchTwo, {}, { section: "watch-list" });
    await screen.findByTestId("watch-list-page");
    expect(rowsOf("watch-table").map((r) => r.getAttribute("data-item"))).toEqual([FIXED_ITEM, ITEM]);
    expect(screen.queryByTestId("watch-panel")).toBeNull();
  });

  it("opens an item's panel from its key: the quote with its tag, the versions, the history, and where a test stands", async () => {
    open(watchTwo, {}, { openItem: FIXED_ITEM });
    const panel = within(await screen.findByTestId("watch-panel"));
    expect(screen.getByTestId("watch-panel").getAttribute("data-item")).toBe(FIXED_ITEM);
    expect(panel.getByTestId("watch-panel-status").textContent).toContain("Fix published");
    expect(panel.getByTestId("source-note").textContent).toContain("it does not say that the fix works");
    expect(within(panel.getByTestId("watch-versions")).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Every version before 2.0.1. Fixed in 2.0.1.",
      "Your version is named: starkbank-ecdsa 2.0.0, which your file lists. Fixed in 2.0.1.",
    ]);
    expect(within(panel.getByTestId("watch-history")).getAllByRole("listitem")).toHaveLength(2);
    expect(panel.getByTestId("watch-test").textContent).toContain("A test can now be designed and proven");
    expect(panel.getByTestId("watch-test-link").getAttribute("href")).toBe("#/a/101/advisories");
    // the other item has its publisher's words, tagged as a quote
    fireEvent.click(rowsOf("watch-table")[1]!);
    const other = within(await screen.findByTestId("watch-panel"));
    expect(other.getByTestId("watch-quote-tag").textContent).toBe(QUOTE_TAG);
    expect(within(other.getByTestId("watch-quote")).getAllByRole("blockquote", { hidden: true }).length).toBeGreaterThan(0);
    expect(other.queryByTestId("watch-test")).toBeNull();
  });

  it("keeps a click that comes the moment the list is first drawn: the item a link names is opened once, and not set a second time", async () => {
    open(watchTwo, {}, { openItem: FIXED_ITEM });
    await pressAtFirstSight(() => screen.queryAllByTestId("watch-row")[1]);
    await waitFor(() => expect(screen.getByTestId("watch-panel").getAttribute("data-item")).toBe(ITEM));
  });

  it("a link that names another item while the page is open opens that item, and one that names none shuts the panel", async () => {
    mockApi({ [CHANGES]: { body: changes }, [LIST]: { body: watchTwo } });
    const page = (item: string | null) => (
      <LinkProvider assessmentId={101} planId={1}>
        <ChangeWatchPage planId={1} openItem={item} section="watch-list" />
      </LinkProvider>
    );
    const opened = () => screen.queryByTestId("watch-panel")?.getAttribute("data-item") ?? null;
    const { rerender } = render(page(FIXED_ITEM));
    await waitFor(() => expect(opened()).toBe(FIXED_ITEM));
    fireEvent.click(rowsOf("watch-table")[1]!);
    expect(opened()).toBe(ITEM);
    rerender(page(FIXED_ITEM)); // drawn again with the same link: what the person opened stays open
    expect(opened()).toBe(ITEM);
    rerender(page(null));
    expect(opened()).toBeNull();
    rerender(page(FIXED_ITEM));
    expect(opened()).toBe(FIXED_ITEM);
    rerender(page(ITEM));
    expect(opened()).toBe(ITEM);
  });

  it("keeps Stop watching pressed the moment the panel is first drawn: its box opens and asks for the reason", async () => {
    const { fetchMock } = open(watchOne, {}, { openItem: ITEM });
    await pressAtFirstSight(() => screen.queryByTestId("watch-stop"));
    expect(await screen.findByTestId("watch-stop-reason")).not.toBeNull();
    expect(posts(fetchMock)).toEqual([]);
  });

  it("Look now opens a box first: nothing is sent before the click in that box", async () => {
    const { fetchMock } = open(watchEmpty, { [LOOK]: { body: watchOne } }, { section: "watch-list" });
    await screen.findByTestId("watch-list-page");
    expect(screen.getByTestId("watch-empty").textContent).toContain("Nothing is on the Watch list yet.");
    fireEvent.click(screen.getByTestId("watch-look"));
    const box = within(await screen.findByTestId("watch-look-box"));
    expect(box.getAllByRole("listitem").map((li) => li.textContent)).toEqual(watchEmpty.look!.box.lines);
    expect(posts(fetchMock)).toEqual([]);
    fireEvent.click(box.getByTestId("watch-look-cancel"));
    await waitFor(() => expect(screen.queryByTestId("watch-look-box")).toBeNull());
    expect(posts(fetchMock)).toEqual([]);
    fireEvent.click(screen.getByTestId("watch-look"));
    fireEvent.click(within(await screen.findByTestId("watch-look-box")).getByTestId("watch-look-confirm"));
    await waitFor(() => expect(rowsOf("watch-table")).toHaveLength(1));
    expect(screen.queryByTestId("watch-look-box")).toBeNull();
    expect(posts(fetchMock)).toEqual([LOOK]);
    expect(sent(fetchMock, "/api/plans/1/watch-list/look")).toEqual([null]); // no body: nothing typed is sent
  });

  it("a look that is refused closes the box and says why on the page", async () => {
    open(watchEmpty, { [LOOK]: { status: 409, body: { error: { message: "OSV (osv.dev) could not be reached (TimeoutError). Nothing was changed.", line: null, field: null } } } }, { section: "watch-list" });
    await screen.findByTestId("watch-list-page");
    fireEvent.click(screen.getByTestId("watch-look"));
    fireEvent.click(within(await screen.findByTestId("watch-look-box")).getByTestId("watch-look-confirm"));
    expect((await screen.findByTestId("watch-error")).textContent).toContain("could not be reached");
    expect(screen.queryByTestId("watch-look-box")).toBeNull();
  });

  it("Stop watching asks for an optional reason and sends it; the item moves to Not watched; Watch again brings it back", async () => {
    const { fetchMock } = open(watchOne, { [STOP]: { body: watchStopped }, [AGAIN]: { body: watchOne } }, { openItem: ITEM });
    const panel = () => within(screen.getByTestId("watch-panel"));
    await screen.findByTestId("watch-panel");
    fireEvent.click(panel().getByTestId("watch-stop"));
    expect(posts(fetchMock)).toEqual([]); // the first click only asks
    fireEvent.click(panel().getByTestId("watch-stop-cancel"));
    expect(panel().queryByTestId("watch-stop-reason")).toBeNull();
    fireEvent.click(panel().getByTestId("watch-stop"));
    fireEvent.change(panel().getByTestId("watch-stop-reason"), { target: { value: "  We do not sign with it.  " } });
    fireEvent.click(panel().getByTestId("watch-stop-confirm"));
    await waitFor(() => expect(rowsOf("watch-stopped-table")).toHaveLength(1));
    expect(rowsOf("watch-table")).toHaveLength(0);
    expect(sent(fetchMock, "/api/plans/1/watch-list/stop")).toEqual([{ item: ITEM, reason: "We do not sign with it." }]);
    expect(within(rowsOf("watch-stopped-table")[0]!).getByTestId("watch-status").textContent).toContain("Not watched");
    expect(panel().queryByTestId("watch-stop")).toBeNull();
    expect(panel().getByTestId("watch-history").textContent).toContain("You stopped watching it (We do not sign with it.).");
    fireEvent.click(panel().getByTestId("watch-again"));
    await waitFor(() => expect(rowsOf("watch-table")).toHaveLength(1));
    expect(sent(fetchMock, "/api/plans/1/watch-list/watch")).toEqual([{ item: ITEM }]);
    expect(posts(fetchMock)).toEqual([STOP, AGAIN]);
    // watched again, it offers Stop watching as a button: the box with the earlier reason is not open by itself
    expect(panel().getByTestId("watch-stop")).not.toBeNull();
    expect(panel().queryByTestId("watch-stop-reason")).toBeNull();
  });

  it("with no reason typed, Stop watching sends none", async () => {
    const { fetchMock } = open(watchOne, { [STOP]: { body: watchStopped } }, { openItem: ITEM });
    const panel = within(await screen.findByTestId("watch-panel"));
    fireEvent.click(panel.getByTestId("watch-stop"));
    fireEvent.click(panel.getByTestId("watch-stop-confirm"));
    await waitFor(() => expect(rowsOf("watch-stopped-table")).toHaveLength(1));
    expect(sent(fetchMock, "/api/plans/1/watch-list/stop")).toEqual([{ item: ITEM }]);
  });

  it("a closed assessment keeps its list: Look now and Stop watching are off, each with the reason", async () => {
    const { fetchMock } = open(watchClosed, {}, { openItem: ITEM });
    const panel = within(await screen.findByTestId("watch-panel"));
    expect((screen.getByTestId("watch-look") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("watch-look-blocked").textContent).toContain("This assessment is closed.");
    expect((panel.getByTestId("watch-stop") as HTMLButtonElement).disabled).toBe(true);
    expect(panel.getByTestId("watch-stop-blocked").textContent).toContain("This assessment is closed.");
    fireEvent.click(screen.getByTestId("watch-look"));
    fireEvent.click(panel.getByTestId("watch-stop"));
    expect(posts(fetchMock)).toEqual([]);
  });

  it("uses none of the words this app never says about a system, and never says what Otto did", async () => {
    open(watchTwo, {}, { openItem: FIXED_ITEM });
    await screen.findByTestId("watch-panel");
    const words = (screen.getByTestId("watch-list-page").textContent ?? "").toLowerCase();
    for (const word of ["secure", "score", "severity", "critical", "otto wrote", "otto found", "otto proposes"]) expect(words).not.toContain(word);
  });
});
