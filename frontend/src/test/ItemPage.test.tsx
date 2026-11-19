import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { DetailPanel, ItemPageContext, PanelHeaderSlotContext, TableWithPanel, type ItemPage } from "../components/layout";
import { CLOSED_SENTENCE } from "../readOnly";
import { itemPageHref, parseRoute, routeHref } from "../router";
import { checksView, newestBlock, retestDetail } from "./checksFixtures";
import { CODE_FIX, TLS_FIX, fixesViews } from "./fixesFixtures";
import { calls, lab, mockApi, plan, run, session, text } from "./fixtures";
import { assessmentView, closedAssessment, workspace } from "./shellFixtures";

// The 5c fixes: every side panel has "Open in new tab". It opens the item on a page of its own, at an address that
// can be bookmarked and opened again: the sidebar and the top bar stay, "← Back to Checks" returns to the list with
// that panel open, the content fills the width with every button working, and the browser tab is named after the item.

type Routes = Parameters<typeof mockApi>[0];
const ROW = newestBlock.rows[0]!; // "retest-1-on-2", Official test vectors
const withWorkspace = { "GET /api/workspace": { body: workspace } };
const routes = (extra: Record<string, unknown> = {}, assessment = assessmentView()): Routes =>
  ({
    "GET /api/session": { body: session },
    ...withWorkspace,
    "GET /api/assessments/101": { body: assessment },
    "GET /api/import/7/verify": { body: run },
    "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
    "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    "GET /api/plans/1/lab": { body: lab },
    "GET /api/plans/1/checks": { body: checksView },
    [`GET /api/plans/1/checks/${ROW.id}`]: { body: { ...retestDetail, check: ROW } },
    ...extra,
  }) as Routes;
const at = (address: string) => window.history.replaceState(null, "", `#/a/101/${address}`);
const goToAddress = (href: string) => {
  window.location.hash = href.replace(/^#/, "");
  fireEvent(window, new HashChangeEvent("hashchange"));
};

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/projects");
  document.title = "Isogeny Labs";
});

describe("the address of an item on a page of its own", () => {
  it("names the assessment, the page, the item and the view, and reads back the same", () => {
    expect(itemPageHref(12, "checks", "test-5")).toBe("#/a/12/checks?item=test-5&view=page");
    expect(parseRoute("#/a/12/checks?item=test-5&view=page")).toEqual({ kind: "assessment", id: 12, page: "checks", item: "test-5", group: null, section: null, view: "page" });
    const system = itemPageHref(3, "migration/systems", "server:localhost:8443");
    expect(parseRoute(system)).toMatchObject({ page: "migration/systems", item: "server:localhost:8443", view: "page" });
    expect(routeHref(parseRoute(system))).toBe(system);
  });

  it("is the list itself when no item is named, when the view is anything else, and on the Overview", () => {
    expect(parseRoute("#/a/12/checks?view=page")).toMatchObject({ page: "checks", item: null, view: null });
    expect(parseRoute("#/a/12/checks?item=test-5&view=wide")).toMatchObject({ item: "test-5", view: null });
    expect(parseRoute("#/a/12/overview?item=x&view=page")).toMatchObject({ page: "overview", view: null });
    expect(routeHref({ kind: "assessment", id: 12, page: "checks", item: null, view: "page" })).toBe("#/a/12/checks");
  });
});

describe("a side panel's header", () => {
  const page = (over: Partial<ItemPage> = {}): ItemPage => ({
    asPage: false,
    root: null,
    backHref: (item) => `#/a/101/checks${item ? `?item=${item}` : ""}`,
    listHref: "#/a/101/checks",
    backLabel: "Checks",
    hrefFor: (item) => itemPageHref(101, "checks", item),
    ...over,
  });

  it("has Open in new tab beside Wider, Narrower and ×, and it opens the item's own page in a new browser tab", () => {
    render(
      <ItemPageContext.Provider value={page()}>
        <TableWithPanel
          panelOpen
          table={<p>the list</p>}
          panel={
            <DetailPanel open item="test-5" title="Bad signatures" onClose={() => undefined}>
              <p>the detail</p>
            </DetailPanel>
          }
        />
      </ItemPageContext.Provider>,
    );
    const header = screen.getByTestId("detail-panel").firstElementChild!.nextElementSibling as HTMLElement;
    const link = within(header).getByTestId("open-in-new-tab");
    expect(text(link)).toBe("Open in new tab ↗");
    expect(link.getAttribute("href")).toBe("#/a/101/checks?item=test-5&view=page");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener");
    expect(within(header).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(["Wider", "Narrower", "Close details"]);
    // it comes before them, in the same row
    expect(link.compareDocumentPosition(within(header).getByRole("button", { name: "Wider" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("the list")).not.toBeNull();
  });

  it("has no such link for a panel that names no item, or outside an assessment's pages", () => {
    const { unmount } = render(
      <ItemPageContext.Provider value={page()}>
        <DetailPanel open title="No item" onClose={() => undefined}>
          <p>x</p>
        </DetailPanel>
      </ItemPageContext.Provider>,
    );
    expect(screen.queryByTestId("open-in-new-tab")).toBeNull();
    unmount();
    render(
      <DetailPanel open item="test-5" title="No page" onClose={() => undefined}>
        <p>x</p>
      </DetailPanel>,
    );
    expect(screen.queryByTestId("open-in-new-tab")).toBeNull();
  });

  it("keeps a place in the header for the buttons of a later phase, which are told which item is open", () => {
    render(
      <PanelHeaderSlotContext.Provider value={(item) => <button type="button">Ask about {item}</button>}>
        <ItemPageContext.Provider value={page()}>
          <DetailPanel open item="test-5" title="Bad signatures" onClose={() => undefined}>
            <p>x</p>
          </DetailPanel>
        </ItemPageContext.Provider>
      </PanelHeaderSlotContext.Provider>,
    );
    const slot = screen.getByTestId("panel-header-slot");
    expect(within(slot).getByRole("button", { name: "Ask about test-5" })).not.toBeNull();
    expect(slot.compareDocumentPosition(screen.getByTestId("open-in-new-tab")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("every side panel in the app names its item, so every one of them has the link", () => {
    // (the panels: a claim on Import and on Verify, an advisory, a check, a result and a library on Evidence, a fix, a
    // system, a library on Dependencies)
    const found: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (name.endsWith(".tsx") && name !== "layout.tsx") {
          const source = readFileSync(path, "utf-8");
          for (const match of source.matchAll(/<DetailPanel\b[^>]*?>/gs)) found.push(`${name}: ${/\bitem=\{/.test(match[0]) ? "names its item" : "NO ITEM"}`);
        }
      }
    };
    walk(join(process.cwd(), "src", "components"));
    expect(found).toHaveLength(9);
    expect(found.filter((f) => f.endsWith("NO ITEM"))).toEqual([]);
  });
});

describe("an item on a page of its own", () => {
  it("keeps the sidebar and the top bar, draws the item across the width, and names the browser tab after it", async () => {
    at(`checks?item=${ROW.id}&view=page`);
    const fetchMock = mockApi(routes());
    render(<App />);
    const page = await screen.findByTestId("item-page");
    await waitFor(() => expect(within(page).getByTestId("check-panel")).not.toBeNull());
    // the item is the page: its name is the page's heading, and the content is the panel's own
    expect(within(page).getByRole("heading", { level: 1, name: ROW.name })).not.toBeNull();
    expect(text(page)).toContain(ROW.plain!);
    expect(within(page).getByTestId("check-panel").getAttribute("data-check")).toBe(ROW.id);
    expect(document.title).toBe(`${ROW.name} · Isogeny Labs`);
    // the shell stays: the sidebar with this page marked, and the top bar
    expect(within(screen.getByRole("navigation", { name: "Assessment" })).getByRole("link", { name: "Checks" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getAllByRole("banner").length).toBeGreaterThan(0);
    // the list is not shown, and the panel's own header buttons are not there
    expect(screen.getByTestId("page-content").hidden).toBe(true);
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expect(within(page).queryByRole("button", { name: "Close details" })).toBeNull();
    expect(within(page).queryByTestId("open-in-new-tab")).toBeNull();
    // looking at it started nothing
    expect(calls(fetchMock).filter((c) => c.startsWith("POST") && !c.includes("/plan"))).toEqual([]);
  });

  it("a fix opens on a page of its own in a new browser tab, and a link to one fix opens that fix, not the first", async () => {
    // (the app is opened at the address itself, as a new browser tab does: nothing was open before)
    const fixes = { "GET /api/plans/1/fixes": { body: fixesViews.ready } };
    at(`fixes?item=${TLS_FIX}&view=page`);
    mockApi(routes(fixes));
    const first = render(<App />);
    const page = await screen.findByTestId("item-page");
    await waitFor(() => expect(within(page).getByTestId("fix-summary").getAttribute("data-fix-id")).toBe(TLS_FIX));
    expect(screen.queryByTestId("item-page-missing")).toBeNull();
    first.unmount();

    at(`fixes?item=${TLS_FIX}`);
    mockApi(routes(fixes));
    render(<App />);
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(TLS_FIX).not.toBe(CODE_FIX); // the first fix in the list is the other one
    expect(fixesViews.ready.fixes[0]?.id).toBe(CODE_FIX);
  });

  it("Back returns to the list with that panel open", async () => {
    at(`checks?item=${ROW.id}&view=page`);
    mockApi(routes());
    render(<App />);
    const back = within(await screen.findByTestId("item-page")).getByTestId("item-page-back");
    expect(text(back)).toBe("← Back to Checks");
    expect(back.getAttribute("href")).toBe(`#/a/101/checks?item=${ROW.id}`);
    goToAddress(back.getAttribute("href")!);
    const panel = await screen.findByTestId("detail-panel");
    expect(within(panel).getByRole("heading", { level: 2, name: ROW.name })).not.toBeNull();
    expect(screen.queryByTestId("item-page")).toBeNull();
    expect(screen.getByTestId("page-content").hidden).toBe(false);
    expect(document.title).toBe("Isogeny Labs");
    // and from the panel the way to the item's own page is one click
    expect(within(panel).getByTestId("open-in-new-tab").getAttribute("href")).toBe(`#/a/101/checks?item=${ROW.id}&view=page`);
  });

  it("says so when the address names an item that is not there, with the way back", async () => {
    at("checks?item=test-999&view=page");
    mockApi(routes());
    render(<App />);
    const missing = await screen.findByTestId("item-page-missing");
    expect(within(missing).getByRole("heading", { level: 1 }).textContent).toBe("This item is not here");
    expect(text(missing)).toContain("names an item that is not on Checks in this assessment");
    expect(within(missing).getByTestId("item-page-back").getAttribute("href")).toBe("#/a/101/checks");
    expect(document.title).toBe("Not found · Isogeny Labs");
    expect(screen.queryByTestId("item-page")).toBeNull();
  });

  it("stays read-only in a closed assessment: the same buttons, off, with the reason", async () => {
    const first = lab.rows[0]!;
    at(`evidence?item=test-${first.item_id}&view=page`);
    mockApi(routes({}, { ...assessmentView(), status: closedAssessment.status, closed_at: closedAssessment.closed_at }));
    render(<App />);
    const page = await screen.findByTestId("item-page");
    expect(within(page).getByRole("heading", { level: 1, name: first.title })).not.toBeNull();
    expect(screen.getByTestId("closed-banner")).not.toBeNull();
    const buttons = within(page).getAllByRole("button", { name: /Mark reviewed|Dig deeper/ }) as HTMLButtonElement[];
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button.disabled).toBe(true);
      expect(button.getAttribute("title")).toBe(CLOSED_SENTENCE);
    }
  });
});
