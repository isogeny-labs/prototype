import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdvisoriesView, AdvisoryRow, RelatedView } from "../api";
import App from "../App";
import { AdvisoriesScreen } from "../components/AdvisoriesScreen";
import { LinkProvider, RelatedBlock } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { DISCLAIMER, calls, mockApi, session, text } from "./fixtures";
import {
  NOT_INSTALLED_LINE,
  STANDING_LINE,
  advisoriesAddedNotRun,
  advisoriesClosed,
  advisoriesFailed,
  advisoriesNoPack,
  advisoriesNotAdded,
  advisoriesOttoMissing,
  advisoriesTwoPacks,
  blankFailed,
  blankNotAdded,
  blankNotRun,
  looseNotOffered,
  ottoInstalledTwo,
  relatedOfAdvisory,
  relatedOfAdvisoryCheck,
  stopsNoTest,
  zeroNotAdded,
} from "./ottoFixtures";
import { acmeRoutes, closedAssessment } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

const ADVISORIES = "GET /api/plans/1/advisories";
const ADD = "POST /api/plans/1/advisories/add";
const BLANK = blankFailed.id;
const STOPS = stopsNoTest.id;
const ZERO = zeroNotAdded.id;
const LOOSE = looseNotOffered.id;

/** The Related block an advisory's panel asks for. */
const relatedRoute = (id: string, lines: RelatedView["related"] = []): Routes => ({
  [`GET /api/plans/1/related?key=${encodeURIComponent(`advisory:${id}`)}`]: { body: { key: `advisory:${id}`, related: lines } },
});
const RELATED: Routes = { ...relatedRoute(BLANK, relatedOfAdvisory.related), ...relatedRoute(STOPS), ...relatedRoute(ZERO), ...relatedRoute(LOOSE) };

/** How often Add new checks told the app that the test plan changed. */
let planChanged = 0;
beforeEach(() => {
  planChanged = 0;
});

function Harness({ item = null, readOnly = false }: { item?: string | null; readOnly?: boolean }) {
  return (
    <ReadOnlyProvider readOnly={readOnly}>
      <LinkProvider assessmentId={101} planId={1}>
        <AdvisoriesScreen planId={1} openItem={item} onPlanChanged={() => (planChanged += 1)} />
      </LinkProvider>
    </ReadOnlyProvider>
  );
}

async function open(view: AdvisoriesView = advisoriesTwoPacks, routes: Routes = {}, props: Parameters<typeof Harness>[0] = {}) {
  const fetchMock = mockApi({ [ADVISORIES]: { body: view }, ...RELATED, ...routes });
  render(<Harness {...props} />);
  await screen.findByTestId("advisories-standing");
  return fetchMock;
}

const rows = () => screen.queryAllByTestId("advisory-row");
const ids = () => rows().map((r) => r.getAttribute("data-advisory"));
const rowOf = (id: string) => rows().find((r) => r.getAttribute("data-advisory") === id)!;
const addButton = () => screen.getByTestId("add-new-checks") as HTMLButtonElement;
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c.startsWith("POST"));
const panel = () => screen.getByTestId("advisory-panel");
/** Clicks an advisory's row and returns its panel. */
async function openRow(id: string) {
  fireEvent.click(rowOf(id));
  await waitFor(() => expect(screen.getByTestId("advisory-panel").getAttribute("data-advisory")).toBe(id));
  return within(panel());
}
/** A view whose first row is changed. */
const withFirstRow = (view: AdvisoriesView, change: (row: AdvisoryRow) => AdvisoryRow): AdvisoriesView => ({
  ...view,
  rows: view.rows.map((r, i) => (i === 0 ? change(r) : r)),
});

// The parts of an advisory's panel, in the order they must come.
const PARTS = [
  "advisory-sentence",
  "advisory-publisher",
  "advisory-sources",
  "advisory-affected",
  "advisory-test-block",
  "advisory-no-test",
  "advisory-here",
  "advisory-fix",
  "advisory-claude",
  "advisory-related",
];
const partsInOrder = () =>
  Array.from(panel().querySelectorAll("[data-testid]"))
    .map((el) => el.getAttribute("data-testid")!)
    .filter((id) => PARTS.includes(id));

describe("Advisories, the page", () => {
  it("shows the title, the subline, the standing line, the packs line as a link to Settings, the answers line and Otto's line", async () => {
    const view = advisoriesTwoPacks;
    const fetchMock = await open(view);
    expect(screen.getByRole("heading", { level: 1, name: view.title })).not.toBeNull();
    expect(text(screen.getByTestId("page-header"))).toContain(view.subline);
    expect(screen.getByTestId("advisories-standing").textContent).toBe(view.standing_line);
    // It is the one fixed line every result screen carries (Evidence and Fixes show the same sentence).
    expect(view.standing_line).toBe(DISCLAIMER);
    const packs = screen.getByTestId("advisories-packs-line");
    expect(text(packs)).toBe(view.packs_line);
    // The link goes where the view says: Settings, on its Test packs section.
    expect(within(packs).getByRole("link").getAttribute("href")).toBe("#/settings?section=test-packs");
    expect(screen.getByTestId("advisories-answers-line").textContent).toBe(view.answers_line);
    expect(screen.getByTestId("advisories-otto-line").textContent).toBe(view.otto.line);
    expect(screen.getByTestId("add-new-checks-note").textContent).toBe(view.add.note);
    // Opening the page only reads: it adds nothing and runs nothing.
    expect(calls(fetchMock)).toEqual([ADVISORIES]);
  });

  it.each([
    ["no pack installed", advisoriesNoPack, false],
    ["a check to add", advisoriesNotAdded, false],
    ["a failed check", advisoriesFailed, false],
    ["a closed assessment", advisoriesClosed, true],
    ["Otto not installed", advisoriesOttoMissing, false],
  ] as const)("keeps the standing line on the page with %s", async (_name, view, readOnly) => {
    await open(view, {}, { readOnly });
    expect(screen.getByTestId("advisories-standing").textContent).toBe(STANDING_LINE);
    // It stays when a panel is open and when the filters hide every row.
    if (view.rows.length > 0) {
      fireEvent.click(rows()[0]!);
      await screen.findByTestId("advisory-panel");
      fireEvent.change(screen.getByTestId("advisories-search"), { target: { value: "no advisory is called this" } });
      expect(rows()).toHaveLength(0);
    }
    expect(screen.getByTestId("advisories-standing").textContent).toBe(STANDING_LINE);
  });

  it.each([
    ["no pack installed", advisoriesNoPack],
    ["two packs", advisoriesTwoPacks],
    ["a closed assessment", advisoriesClosed],
    ["Otto not installed", advisoriesOttoMissing],
  ] as const)("never says score, and says 'secure' only inside the backend's standing line, with %s", async (_name, view) => {
    await open(view);
    // Every advisory's panel in turn, with everything in it (a folded part is in the page too).
    for (const id of ids()) {
      await openRow(id!);
      const all = document.body.textContent ?? "";
      expect(all.match(/secure/gi), id!).toHaveLength(1);
      expect(all, id!).not.toMatch(/\bscore|\bgrade\b|time.to.hack|\brisk level/i);
    }
    const all = document.body.textContent ?? "";
    expect(all.match(/secure/gi)).toHaveLength(1);
    expect(screen.getByTestId("advisories-standing").textContent).toMatch(/secure/);
    expect(all).not.toMatch(/\bscore|\bgrade\b|time.to.hack|\brisk level/i);
    // Nothing on the page takes a file or anything typed but the search: a pack comes from Settings, never from here.
    expect(document.querySelector('input[type="file"], textarea, form')).toBeNull();
    expect(Array.from(document.querySelectorAll("input")).map((i) => i.getAttribute("data-testid"))).toEqual(["advisories-search"]);
    expect(all).not.toMatch(/upload|drop a file|choose a file/i);
  });

  it("says so, in a plain error box, when the advisories can't be loaded", async () => {
    mockApi({ [ADVISORIES]: { status: 500, body: { error: { message: "The advisories could not be read.", line: null, field: null } } } });
    render(<Harness />);
    expect(text(await screen.findByRole("alert"))).toContain("The advisories could not be read.");
    expect(screen.queryByTestId("add-new-checks")).toBeNull();
  });
});

describe("Advisories, the table", () => {
  it("takes its column names from the view and shows one row per advisory: name and id, published, fits, the Test chip and the Result chip", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const table = within(screen.getByTestId("advisories-table"));
    expect(table.getAllByRole("columnheader").map((th) => text(th))).toEqual(view.columns);
    expect(ids()).toEqual(view.rows.map((r) => r.id));
    for (const row of view.rows) {
      const tr = rowOf(row.id);
      const cells = Array.from(tr.children);
      expect(cells, row.id).toHaveLength(5);
      // The plain name, with the id under it in a fixed-width font.
      const [name, id] = Array.from(cells[0]!.querySelectorAll("span"));
      expect(name!.textContent, row.id).toBe(row.name);
      expect(id!.textContent, row.id).toBe(row.id);
      expect(id!.className, row.id).toContain("font-mono");
      expect(text(cells[1]), row.id).toBe(row.published_text);
      expect(text(cells[2]), row.id).toBe(row.fits_text);
      // Both chips carry the view's words and the view's tone: the page colours nothing by itself.
      const test = within(tr).getByTestId("advisory-test");
      expect(test.textContent, row.id).toBe(row.test.label);
      expect(test.getAttribute("data-tone"), row.id).toBe(row.test.tone);
      const result = within(tr).getByTestId("advisory-result");
      expect(result.textContent, row.id).toBe(row.result.label);
      expect(result.getAttribute("data-tone"), row.id).toBe(row.result.tone);
      expect(text(cells[4]), row.id).toBe(row.result.label);
    }
  });

  it("gives every Test chip a label and a reason: the reason on hover, and readable in the panel", async () => {
    await open(advisoriesTwoPacks);
    for (const row of advisoriesTwoPacks.rows) {
      const chip = within(rowOf(row.id)).getByTestId("advisory-test");
      expect(chip.textContent!.trim().length, row.id).toBeGreaterThan(0);
      expect(chip.getAttribute("title"), row.id).toBe(row.test.reason);
      expect(row.test.reason.length, row.id).toBeGreaterThan(10);
      const inPanel = await openRow(row.id);
      expect(inPanel.getByTestId("advisory-test-reason").textContent, row.id).toBe(row.test.reason);
    }
  });

  it("shows the line under a Result chip when the view sends one", async () => {
    // With more than one signing program, the backend adds how many of them read the same ("1 of 2 programs").
    const view = withFirstRow(advisoriesFailed, (r) => ({ ...r, result: { ...r.result, text: "1 of 2 programs" } }));
    await open(view);
    const cell = rowOf(BLANK).children[4]!;
    expect(within(cell as HTMLElement).getByTestId("advisory-result").textContent).toBe(blankFailed.result.label);
    expect(text(cell)).toBe(`${blankFailed.result.label}1 of 2 programs`);
    // A row without one shows the chip alone.
    expect(text(rowOf(STOPS).children[4])).toBe(stopsNoTest.result.label);
  });

  it("searches in the view's own search text, whatever the case", async () => {
    await open(advisoriesTwoPacks);
    const search = screen.getByTestId("advisories-search");
    expect(search.getAttribute("type")).toBe("search");
    fireEvent.change(search, { target: { value: "ELLIPTIC" } });
    expect(ids()).toEqual(advisoriesTwoPacks.rows.filter((r) => r.search.includes("elliptic")).map((r) => r.id));
    expect(ids()).toEqual([ZERO, LOOSE]);
    fireEvent.change(search, { target: { value: "  cve-2019 " } });
    expect(ids()).toEqual([STOPS]);
    fireEvent.change(search, { target: { value: "" } });
    expect(ids()).toHaveLength(4);
  });

  it("filters by Test with the view's options, against each row's test key", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const select = screen.getByTestId("advisories-filter-test") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(view.filters.test.map((o) => [o.key, o.label]));
    expect(select.value).toBe("all");
    for (const option of view.filters.test) {
      fireEvent.change(select, { target: { value: option.key } });
      expect(ids(), option.key).toEqual(view.rows.filter((r) => option.key === "all" || r.test.key === option.key).map((r) => r.id));
    }
    fireEvent.change(select, { target: { value: "not_offered" } });
    expect(ids()).toEqual([LOOSE]);
    fireEvent.change(select, { target: { value: "none" } });
    expect(ids()).toEqual([STOPS]);
  });

  it("filters by Result with the view's options, against each row's result key, and the filters work together", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const select = screen.getByTestId("advisories-filter-result") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(view.filters.result.map((o) => [o.key, o.label]));
    for (const option of view.filters.result) {
      fireEvent.change(select, { target: { value: option.key } });
      expect(ids(), option.key).toEqual(view.rows.filter((r) => option.key === "all" || r.result.key === option.key).map((r) => r.id));
    }
    fireEvent.change(select, { target: { value: "fail" } });
    expect(ids()).toEqual([BLANK]);
    fireEvent.change(select, { target: { value: "none" } });
    expect(ids()).toEqual([STOPS, LOOSE]);
    // Together: no check, and its test is not offered.
    fireEvent.change(screen.getByTestId("advisories-filter-test"), { target: { value: "not_offered" } });
    expect(ids()).toEqual([LOOSE]);
    fireEvent.change(screen.getByTestId("advisories-search"), { target: { value: "blank" } });
    expect(ids()).toEqual([]);
  });

  it("says that nothing matches when the filters hide every row, and keeps the view's empty line for a page with no advisory", async () => {
    await open(advisoriesTwoPacks);
    expect(screen.queryByTestId("advisories-empty")).toBeNull();
    fireEvent.change(screen.getByTestId("advisories-filter-result"), { target: { value: "pass" } });
    expect(rows()).toHaveLength(0);
    expect(text(screen.getByTestId("advisories-no-match"))).toMatch(/nothing matches/i);
    expect(screen.queryByTestId("advisories-empty")).toBeNull();
    // "Any result" shows everything again.
    fireEvent.change(screen.getByTestId("advisories-filter-result"), { target: { value: "all" } });
    expect(rows()).toHaveLength(4);
    expect(screen.queryByTestId("advisories-no-match")).toBeNull();
  });

  it("shows the view's empty line when no pack is installed", async () => {
    await open(advisoriesNoPack);
    expect(rows()).toHaveLength(0);
    expect(screen.getByTestId("advisories-empty").textContent).toBe(advisoriesNoPack.empty);
    expect(screen.queryByTestId("advisories-no-match")).toBeNull();
    expect(text(screen.getByTestId("advisories-packs-line"))).toBe(advisoriesNoPack.packs_line);
  });
});

describe("Advisories, an advisory's panel", () => {
  it("opens on a click with its parts in order, and starts nothing", async () => {
    const fetchMock = await open(advisoriesTwoPacks);
    expect(screen.queryByTestId("advisory-panel")).toBeNull();
    const inPanel = await openRow(BLANK);
    await inPanel.findByTestId("advisory-related");
    // The plain name and the id head the panel.
    const heading = inPanel.getByRole("heading", { level: 2, name: blankFailed.name });
    expect(text(heading.parentElement)).toBe(`${blankFailed.name}${blankFailed.id}`);
    expect(heading.compareDocumentPosition(inPanel.getByTestId("advisory-sentence")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(partsInOrder()).toEqual([
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-test-block",
      "advisory-here",
      "advisory-fix",
      "advisory-claude",
      "advisory-related",
    ]);
    expect(inPanel.getByTestId("advisory-sentence").textContent).toBe(blankFailed.panel.sentence);
    expect(posts(fetchMock)).toEqual([]);
    // The table beside the open panel is compact, and a row still carries both chips.
    expect(within(screen.getByTestId("advisories-table")).getByTestId("data-table").getAttribute("data-compact")).toBe("true");
    expect(within(rowOf(BLANK)).getByTestId("advisory-test").textContent).toBe(blankFailed.test.label);
    expect(within(rowOf(BLANK)).getByTestId("advisory-result").textContent).toBe(blankFailed.result.label);
    expect(rowOf(BLANK).getAttribute("aria-selected")).toBe("true");
  });

  it("shows the publisher's own line as a quote under its tag, with the source as a link and the day it was read, and the sources folded under it", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const quote = blankFailed.panel.publisher!;
    const publisher = inPanel.getByTestId("advisory-publisher");
    expect(publisher.querySelector("q")!.textContent).toBe(quote.text);
    expect(within(publisher).getByText(quote.tag)).not.toBeNull();
    const link = within(publisher).getByRole("link", { name: quote.source });
    expect(link.getAttribute("href")).toBe(quote.href);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(text(publisher)).toContain(quote.publisher);
    expect(text(publisher)).toContain(quote.read_on);
    // A quote is information from the advisory: it has no result chip.
    expect(publisher.querySelector("[data-tone]")).toBeNull();

    const sources = inPanel.getByTestId("advisory-sources") as HTMLDetailsElement;
    expect(sources.tagName).toBe("DETAILS");
    expect(sources.open).toBe(false);
    const listed = within(sources).getAllByTestId("advisory-source");
    expect(listed).toHaveLength(blankFailed.panel.sources.length);
    blankFailed.panel.sources.forEach((s, i) => {
      const item = listed[i]!;
      expect(text(item)).toContain(s.label);
      expect(within(item).getByRole("link", { name: s.title }).getAttribute("href")).toBe(s.href);
      expect(text(item)).toContain(s.publisher);
      expect(text(item)).toContain(s.read_on);
    });

    const affected = inPanel.getByTestId("advisory-affected");
    expect(text(affected)).toContain(blankFailed.panel.affected!.line);
    expect(affected.querySelector("q")!.textContent).toBe(blankFailed.panel.affected!.quote.text);
  });

  it("shows a source whose address is not https as text, never as a link", async () => {
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      panel: {
        ...r.panel,
        publisher: { ...r.panel.publisher!, href: "" },
        sources: r.panel.sources.map((s) => ({ ...s, href: "http://example.com/advisory" })),
      },
    }));
    await open(view);
    const inPanel = await openRow(BLANK);
    const publisher = inPanel.getByTestId("advisory-publisher");
    expect(text(publisher)).toContain(blankFailed.panel.publisher!.source);
    expect(within(publisher).queryByRole("link")).toBeNull();
    const sources = inPanel.getByTestId("advisory-sources");
    expect(text(sources)).toContain(blankFailed.panel.sources[0]!.title);
    expect(within(sources).queryByRole("link")).toBeNull();
  });

  it("shows a ready test: its question, cases, control, rule and short fingerprint, how it did on public copies, and Otto's ledger entries folded", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const test = blankFailed.panel.test!;
    const block = inPanel.getByTestId("advisory-test-block");
    const inBlock = within(block);
    expect(inBlock.getByRole("heading", { level: 3, name: test.title })).not.toBeNull();
    for (const words of [test.question, test.cases_line, test.control, test.rule]) expect(inBlock.getByText(words), words).not.toBeNull();
    // The fingerprint is cut short; the whole value shows on hover.
    const fingerprint = inBlock.getByTitle(test.design_fingerprint);
    expect(fingerprint.textContent).toBe(test.design_fingerprint.slice(0, 12));
    expect(text(block)).not.toContain(test.design_fingerprint);
    // Its label and reason are the view's.
    expect(within(block).getByText(blankFailed.test.label).parentElement!.getAttribute("data-tone")).toBe(blankFailed.test.tone);
    expect(inBlock.getByTestId("advisory-test-reason").textContent).toBe(blankFailed.test.reason);

    const trial = within(inBlock.getByTestId("advisory-trial"));
    expect(trial.getByRole("heading", { name: test.trial.title })).not.toBeNull();
    expect(trial.getAllByRole("listitem").map((li) => li.textContent)).toEqual(test.trial.lines);

    const ledger = inBlock.getByTestId("advisory-ledger") as HTMLDetailsElement;
    expect(ledger.tagName).toBe("DETAILS");
    expect(ledger.open).toBe(false);
    expect(text(ledger.querySelector("summary"))).toBe(`${test.ledger.title} (${test.ledger.count})`);
    const entries = within(ledger).getAllByTestId("advisory-ledger-entry");
    expect(entries).toHaveLength(test.ledger.entries.length);
    test.ledger.entries.forEach((e, i) => {
      const entry = entries[i]!;
      expect(text(entry), e.id).toContain(String(e.seq));
      expect(text(entry), e.id).toContain(e.kind);
      expect(text(entry), e.id).toContain(e.what);
      expect(text(entry), e.id).toContain(e.id);
      expect(entry.querySelector("time")!.getAttribute("datetime"), e.id).toBe(e.at);
    });
    expect(text(ledger)).toContain(test.ledger.note);
    // The ledger is listed as what it is: no entry is drawn as a result.
    expect(ledger.querySelector("[data-tone]")).toBeNull();
    expect(inPanel.queryByTestId("advisory-no-test")).toBeNull();
  });

  it("shows the check in this assessment: the reviewer's result with its plain sentence, the way to Checks and to the evidence, and its ledger folded", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const here = blankFailed.panel.here;
    const block = within(inPanel.getByTestId("advisory-here"));
    expect(block.getByRole("heading", { level: 3, name: here.title })).not.toBeNull();
    const shown = block.getAllByTestId("advisory-here-row");
    expect(shown).toHaveLength(here.rows.length);
    const row = here.rows[0]!;
    const result = row.result!;
    const inRow = within(shown[0]!);
    expect(text(shown[0])).toContain(row.program);
    // The result chip is the view's label and tone, and its reason is the reviewer's one plain sentence.
    const chip = inRow.getByTestId("advisory-here-result");
    expect(chip.textContent).toBe(result.label);
    expect(chip.getAttribute("data-tone")).toBe(result.tone);
    expect(inRow.getByText(result.plain)).not.toBeNull();
    expect(text(shown[0])).toContain(result.component!);
    expect(shown[0]!.querySelector("time")!.getAttribute("datetime")).toBe(result.finished_at);
    expect(inRow.getByRole("link", { name: "Open in Checks" }).getAttribute("href")).toBe("#/a/101/checks?item=test-6");
    expect(inRow.getByRole("link", { name: "See the evidence" }).getAttribute("href")).toBe("#/a/101/evidence?item=test-6");
    const ledger = inRow.getByTestId("advisory-ledger") as HTMLDetailsElement;
    expect(ledger.open).toBe(false);
    expect(text(ledger.querySelector("summary"))).toBe(`${row.ledger!.title} (${row.ledger!.count})`);
    expect(within(ledger).getAllByTestId("advisory-ledger-entry").map((li) => li.querySelector("time")!.getAttribute("datetime"))).toEqual(
      row.ledger!.entries.map((e) => e.at),
    );
    expect(text(ledger)).toContain(row.ledger!.note);
    expect(inPanel.queryByTestId("advisory-here-status")).toBeNull();
  });

  it("says where a check stands before it has a result: not added (no links), then not run (Open in Checks only)", async () => {
    await open(advisoriesNotAdded);
    let inPanel = await openRow(BLANK);
    let row = within(inPanel.getByTestId("advisory-here-row"));
    expect(row.getByTestId("advisory-here-status").textContent).toBe(blankNotAdded.panel.here.rows[0]!.status);
    expect(row.queryByRole("link")).toBeNull();
    expect(row.queryByTestId("advisory-here-result")).toBeNull();
    expect(row.queryByTestId("advisory-ledger")).toBeNull();

    // The same advisory once Add new checks put its test in the plan.
    cleanup();
    await open(advisoriesAddedNotRun);
    inPanel = await openRow(BLANK);
    row = within(inPanel.getByTestId("advisory-here-row"));
    expect(row.getByTestId("advisory-here-status").textContent).toBe(blankNotRun.panel.here.rows[0]!.status);
    expect(row.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([["Open in Checks", "#/a/101/checks?item=test-6"]]);
    const ledger = blankNotRun.panel.here.rows[0]!.ledger!;
    expect(text(row.getByTestId("advisory-ledger").querySelector("summary"))).toBe(`${ledger.title} (${ledger.count})`);
  });

  it("shows the fix: the From Otto label when the view gives one, its lines, the publisher's line, and the way to it in Fixes", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const fix = blankFailed.panel.fix;
    const block = inPanel.getByTestId("advisory-fix");
    expect(within(block).getByRole("heading", { level: 3, name: fix.title })).not.toBeNull();
    expect(within(block).getByTestId("advisory-fix-label").textContent).toBe(fix.label);
    for (const line of fix.lines) expect(within(block).getByText(line), line).not.toBeNull();
    expect(block.querySelector("q")!.textContent).toBe(fix.quote!.text);
    const here = within(block).getByTestId("advisory-fix-here");
    expect(text(here)).toBe(`${fix.here!.line} ${fix.here!.label}`);
    expect(within(here).getByRole("link", { name: fix.here!.label }).getAttribute("href")).toBe("#/a/101/fixes?item=fix-ecdsa-range-check");
  });

  it("folds what Otto asked Claude: each step's line with its two fingerprints cut short, then the note", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const claude = blankFailed.panel.claude;
    const block = inPanel.getByTestId("advisory-claude") as HTMLDetailsElement;
    expect(block.tagName).toBe("DETAILS");
    expect(block.open).toBe(false);
    expect(block.querySelector("summary")!.textContent).toBe(claude.title);
    const steps = within(block).getAllByTestId("advisory-step");
    expect(steps).toHaveLength(claude.steps.length);
    claude.steps.forEach((s, i) => {
      const step = steps[i]!;
      expect(text(step), s.step).toContain(s.line);
      expect(step.getAttribute("data-source"), s.step).toBe(s.source);
      expect(within(step).getByTitle(s.prompt_sha256).textContent, s.step).toBe(s.prompt_sha256.slice(0, 12));
      expect(within(step).getByTitle(s.answer_sha256).textContent, s.step).toBe(s.answer_sha256.slice(0, 12));
      expect(text(step), s.step).not.toContain(s.answer_sha256);
    });
    expect(text(block)).toContain(claude.note);
  });

  it("ends with Related, asked by the key the view gives, each entry a link to its own page", async () => {
    const fetchMock = await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const related = within(await inPanel.findByTestId("advisory-related"));
    expect(calls(fetchMock)).toContain(`GET /api/plans/1/related?key=${encodeURIComponent(blankFailed.panel.related_key)}`);
    expect(related.getAllByTestId("related-line").map((l) => l.getAttribute("data-kind"))).toEqual(relatedOfAdvisory.related.map((l) => l.kind));
    // Each entry carries the backend's label and goes where the backend says: the check's evidence, the fix in Fixes.
    const [check, fix] = relatedOfAdvisory.related.map((l) => l.items[0]!);
    expect(related.getAllByTestId("related-link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      [check!.label, "#/a/101/evidence?item=test-6"],
      [fix!.label, "#/a/101/fixes?item=fix-ecdsa-range-check"],
    ]);
    expect(partsInOrder().at(-1)).toBe("advisory-related");
    // An advisory nothing relates to yet has no Related block.
    const other = await openRow(STOPS);
    await waitFor(() => expect(calls(fetchMock)).toContain(`GET /api/plans/1/related?key=${encodeURIComponent(stopsNoTest.panel.related_key)}`));
    expect(other.queryByTestId("advisory-related")).toBeNull();
  });

  it("shows an advisory with no test yet: its label and reason, nothing to run here, and no fix label", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(STOPS);
    const noTest = stopsNoTest.panel.no_test!;
    expect(inPanel.queryByTestId("advisory-test-block")).toBeNull();
    const block = inPanel.getByTestId("advisory-no-test");
    // The chip has the view's label and tone, and its reason beside it.
    const chip = block.querySelector("[data-tone]")!;
    expect(chip.textContent).toBe(noTest.label);
    expect(chip.getAttribute("data-tone")).toBe(stopsNoTest.test.tone);
    expect(within(block).getByTestId("advisory-test-reason").textContent).toBe(noTest.reason);
    // No trial was run for it; Otto's ledger entries are there, folded.
    expect(within(block).queryByTestId("advisory-trial")).toBeNull();
    expect(text(within(block).getByTestId("advisory-ledger").querySelector("summary"))).toBe(`${noTest.ledger!.title} (${noTest.ledger!.count})`);

    const here = inPanel.getByTestId("advisory-here");
    expect(within(here).queryAllByTestId("advisory-here-row")).toHaveLength(0);
    expect(within(here).getByTestId("advisory-here-empty").textContent).toBe(stopsNoTest.panel.here.empty);
    const fix = inPanel.getByTestId("advisory-fix");
    expect(within(fix).queryByTestId("advisory-fix-label")).toBeNull();
    for (const line of stopsNoTest.panel.fix.lines) expect(within(fix).getByText(line), line).not.toBeNull();
    expect(within(fix).queryByTestId("advisory-fix-here")).toBeNull();
    expect(within(inPanel.getByTestId("advisory-claude")).getAllByTestId("advisory-step")).toHaveLength(stopsNoTest.panel.claude.steps.length);
    expect(partsInOrder()).toEqual([
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-no-test",
      "advisory-here",
      "advisory-fix",
      "advisory-claude",
    ]);
  });

  it("shows an advisory whose test is not offered: its label and reason, and how its design did when it was tried", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(LOOSE);
    const noTest = looseNotOffered.panel.no_test!;
    expect(inPanel.queryByTestId("advisory-test-block")).toBeNull();
    const block = inPanel.getByTestId("advisory-no-test");
    const chip = block.querySelector("[data-tone]")!;
    expect(chip.textContent).toBe(noTest.label);
    expect(chip.getAttribute("data-tone")).toBe(looseNotOffered.test.tone);
    expect(within(block).getByTestId("advisory-test-reason").textContent).toBe(noTest.reason);
    const trial = within(within(block).getByTestId("advisory-trial"));
    expect(trial.getByRole("heading", { name: noTest.trial!.title })).not.toBeNull();
    expect(trial.getAllByRole("listitem").map((li) => li.textContent)).toEqual(noTest.trial!.lines);
    expect(within(block).getByTestId("advisory-ledger")).not.toBeNull();
    expect(within(inPanel.getByTestId("advisory-here")).getByTestId("advisory-here-empty").textContent).toBe(looseNotOffered.panel.here.empty);
  });

  it("shows the notes and the other names of an advisory when the view has them, between what is affected and the test", async () => {
    // Not in the samples (their advisories have neither): the fields are filled in here to see them drawn.
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      panel: { ...r.panel, notes: "The publisher lists Java 15 to 18 as affected.", also_known_as: ["GHSA-4w7w-66w2-5vf9", "JDK-8277233"] },
    }));
    await open(view);
    let inPanel = await openRow(BLANK);
    expect(inPanel.getByTestId("advisory-notes").textContent).toBe("The publisher lists Java 15 to 18 as affected.");
    expect(text(inPanel.getByTestId("advisory-also-known-as"))).toContain("GHSA-4w7w-66w2-5vf9, JDK-8277233");
    expect(partsInOrder().slice(0, 5)).toEqual(["advisory-sentence", "advisory-publisher", "advisory-sources", "advisory-affected", "advisory-test-block"]);
    const notes = inPanel.getByTestId("advisory-notes");
    expect(inPanel.getByTestId("advisory-affected").compareDocumentPosition(notes) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(notes.compareDocumentPosition(inPanel.getByTestId("advisory-test-block")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // The second row has neither.
    inPanel = await openRow(STOPS);
    expect(inPanel.queryByTestId("advisory-notes")).toBeNull();
    expect(inPanel.queryByTestId("advisory-also-known-as")).toBeNull();
  });

  it("draws no publisher's line for an advisory Otto could not read, and still lists its sources", async () => {
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      name: "An advisory Otto could not read",
      panel: { ...r.panel, sentence: "The advisory's text could not be matched to its publisher's page.", publisher: null, affected: null },
    }));
    await open(view);
    const inPanel = await openRow(BLANK);
    expect(inPanel.getByTestId("advisory-sentence").textContent).toBe("The advisory's text could not be matched to its publisher's page.");
    expect(inPanel.queryByTestId("advisory-publisher")).toBeNull();
    expect(inPanel.queryByTestId("advisory-affected")).toBeNull();
    expect(inPanel.getByTestId("advisory-sources")).not.toBeNull();
  });

  it("opens the advisory a link names, switches on a click on another row, and closes from its button or Escape", async () => {
    await open(advisoriesTwoPacks, {}, { item: LOOSE });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(LOOSE));
    expect(within(panel()).getByRole("heading", { level: 2, name: looseNotOffered.name })).not.toBeNull();
    // The shared panel of every table page, with its close button, is inside.
    expect(within(panel()).getByTestId("detail-panel")).not.toBeNull();
    await openRow(ZERO);
    expect(within(panel()).getByRole("heading", { level: 2, name: zeroNotAdded.name })).not.toBeNull();
    fireEvent.click(within(panel()).getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("advisory-panel")).toBeNull();
    expect(within(screen.getByTestId("advisories-table")).getByTestId("data-table").getAttribute("data-compact")).toBeNull();
    // A row opens from the keyboard too; Escape closes it.
    fireEvent.keyDown(rowOf(STOPS), { key: "Enter" });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(STOPS));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("advisory-panel")).toBeNull();
  });

  it("keeps the panel open when the filters hide its row, and lists exactly what the filters match", async () => {
    await open(advisoriesTwoPacks);
    await openRow(BLANK);
    fireEvent.change(screen.getByTestId("advisories-filter-test"), { target: { value: "not_offered" } });
    expect(ids()).toEqual([LOOSE]);
    expect(panel().getAttribute("data-advisory")).toBe(BLANK);
  });
});

describe("Advisories, Add new checks", () => {
  it("is on when the view says so, calls the API once and shows the view it answers with", async () => {
    const fetchMock = await open(advisoriesNotAdded, { [ADD]: { body: advisoriesAddedNotRun } });
    const button = addButton();
    expect(button.textContent).toBe(advisoriesNotAdded.add.button);
    expect(button.disabled).toBe(false);
    expect(screen.queryByTestId("add-new-checks-reason")).toBeNull();
    expect(within(rowOf(BLANK)).getByTestId("advisory-result").textContent).toBe(blankNotAdded.result.label);

    fireEvent.click(button);
    await waitFor(() => expect(addButton().textContent).toBe(advisoriesAddedNotRun.add.button));
    expect(posts(fetchMock)).toEqual([ADD]);
    // The new view: nothing left to add, with the reason; the row's check is in the plan and has not run.
    expect(addButton().disabled).toBe(true);
    expect(screen.getByTestId("add-new-checks-reason").textContent).toBe(advisoriesAddedNotRun.add.blocked_reason);
    expect(within(rowOf(BLANK)).getByTestId("advisory-result").textContent).toBe(blankNotRun.result.label);
    expect(screen.getByTestId("add-new-checks-note").textContent).toBe(advisoriesAddedNotRun.add.note);
    // The app is told the plan changed, once. Nothing was run.
    expect(planChanged).toBe(1);
    expect(calls(fetchMock).filter((c) => c !== ADVISORIES && c !== ADD)).toEqual([]);
  });

  it("shows a busy state while it runs and can't be started twice", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(input)}`;
      if (key === ADD) await gate;
      const body = key === ADD ? advisoriesAddedNotRun : key === ADVISORIES ? advisoriesNotAdded : null;
      if (body === null) throw new Error(`Unexpected request: ${key}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<Harness />);
    await screen.findByTestId("advisories-standing");

    fireEvent.click(addButton());
    await waitFor(() => expect(addButton().getAttribute("aria-busy")).toBe("true"));
    expect(addButton().disabled).toBe(true);
    // The button keeps the view's words while it waits.
    expect(addButton().textContent).toBe(advisoriesNotAdded.add.button);
    fireEvent.click(addButton());
    release();
    await waitFor(() => expect(addButton().textContent).toBe(advisoriesAddedNotRun.add.button));
    expect(addButton().getAttribute("aria-busy")).toBeNull();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("shows the reason in a plain error box when it fails, and keeps the page as it was", async () => {
    const refusal = "Otto is not installed on this computer, so advisory checks can't be added.";
    const fetchMock = await open(advisoriesNotAdded, { [ADD]: { status: 409, body: { error: { message: refusal, line: null, field: null } } } });
    fireEvent.click(addButton());
    expect(text(await screen.findByRole("alert"))).toBe(refusal);
    expect(posts(fetchMock)).toEqual([ADD]);
    expect(addButton().disabled).toBe(false);
    expect(addButton().textContent).toBe(advisoriesNotAdded.add.button);
    expect(within(rowOf(BLANK)).getByTestId("advisory-result").textContent).toBe(blankNotAdded.result.label);
    expect(planChanged).toBe(0);
  });

  it.each([
    ["nothing is left to add", advisoriesAddedNotRun],
    ["no pack is installed", advisoriesNoPack],
    ["the assessment is closed", advisoriesClosed],
  ] as const)("is off, with the view's reason beside it, when %s", async (_name, view) => {
    const fetchMock = await open(view);
    expect(view.add.can).toBe(false);
    expect(addButton().disabled).toBe(true);
    expect(addButton().textContent).toBe(view.add.button);
    expect(screen.getByTestId("add-new-checks-reason").textContent).toBe(view.add.blocked_reason);
    expect(view.add.blocked_reason!.length).toBeGreaterThan(10);
    fireEvent.click(addButton());
    expect(posts(fetchMock)).toEqual([]);
  });

  it("is off in a closed assessment by the page's own rule too, with the closed sentence", async () => {
    // Even if a view said it could be added: the page is read-only once the assessment is closed.
    const fetchMock = await open(advisoriesTwoPacks, {}, { readOnly: true });
    expect(advisoriesTwoPacks.add.can).toBe(true);
    expect(addButton().disabled).toBe(true);
    expect(addButton().getAttribute("title")).toBe(CLOSED_SENTENCE);
    fireEvent.click(addButton());
    expect(posts(fetchMock)).toEqual([]);
    // Looking is still allowed: rows open, links work.
    await openRow(BLANK);
    expect(within(screen.getByTestId("advisories-packs-line")).getByRole("link").getAttribute("href")).toBe("#/settings?section=test-packs");
  });

  it("is off when Otto is not installed, and the page says so calmly in the backend's words", async () => {
    const view = advisoriesOttoMissing;
    const fetchMock = await open(view);
    expect(addButton().disabled).toBe(true);
    expect(screen.getByTestId("add-new-checks-reason").textContent).toBe(NOT_INSTALLED_LINE);
    const notice = screen.getByTestId("advisories-otto-line");
    expect(notice.textContent).toBe(view.otto.line);
    expect(notice.getAttribute("data-installed")).toBe("false");
    // A calm notice, not an error: no alert, and not the error box's look.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(notice.className).not.toMatch(/amber/);
    fireEvent.click(addButton());
    expect(posts(fetchMock)).toEqual([]);
    // What is already here stays: the result of the check that ran, in the reviewer's words.
    expect(within(rowOf(BLANK)).getByTestId("advisory-result").textContent).toBe(view.rows[0]!.result.label);
  });
});

describe("Advisories, the names the end-to-end walk looks for", () => {
  const present = (ids: string[], root: HTMLElement = document.body) => ids.filter((id) => within(root).queryAllByTestId(id).length > 0);

  it("has every test id of the page and of a ready test's panel, and the panel holds its own parts", async () => {
    await open(advisoriesClosed, {}, { item: BLANK });
    await screen.findByTestId("advisory-related");
    // Everything of the page, the panel too, is inside the page's root.
    const onPage = [
      "advisories-standing",
      "advisories-packs-line",
      "advisories-answers-line",
      "advisories-otto-line",
      "add-new-checks",
      "add-new-checks-reason",
      "add-new-checks-note",
      "advisories-search",
      "advisories-filter-test",
      "advisories-filter-result",
      "advisories-table",
      "advisory-row",
      "advisory-test",
      "advisory-result",
      "advisory-panel",
    ];
    expect(present(onPage, screen.getByTestId("advisories-page"))).toEqual(onPage);
    expect(screen.getAllByTestId("advisory-row").map((r) => r.getAttribute("data-advisory"))).toEqual(advisoriesClosed.rows.map((r) => r.id));
    for (const row of screen.getAllByTestId("advisory-row")) expect(present(["advisory-test", "advisory-result"], row)).toHaveLength(2);
    const inPanel = [
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-test-block",
      "advisory-trial",
      "advisory-ledger",
      "advisory-here",
      "advisory-here-row",
      "advisory-fix",
      "advisory-fix-label",
      "advisory-claude",
      "advisory-related",
    ];
    expect(present(inPanel, panel())).toEqual(inPanel);
    expect(panel().getAttribute("data-advisory")).toBe(BLANK);
    // Each ledger is its own folded list: the test's, and the check's in this assessment.
    expect(within(panel()).getAllByTestId("advisory-ledger").map((d) => d.tagName)).toEqual(["DETAILS", "DETAILS"]);
    for (const folded of ["advisory-sources", "advisory-claude"]) expect(within(panel()).getByTestId(folded).tagName, folded).toBe("DETAILS");
  });

  it("has the ids of a row without a test and of a page with no advisory", async () => {
    await open(advisoriesTwoPacks, {}, { item: STOPS });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(STOPS));
    expect(present(["advisory-no-test", "advisory-ledger", "advisory-here", "advisory-fix", "advisory-claude"], panel())).toHaveLength(5);
    cleanup();
    await open(advisoriesNoPack);
    expect(present(["advisories-empty", "advisories-table", "add-new-checks-reason"])).toHaveLength(3);
  });
});

describe("Related, the sixth line (phase 5c)", () => {
  it("draws the Advisory line of a check under the title the backend gives, linking to the advisory on Advisories", () => {
    render(
      <LinkProvider assessmentId={101} planId={1}>
        <RelatedBlock lines={relatedOfAdvisoryCheck.related} />
      </LinkProvider>,
    );
    const lines = screen.getAllByTestId("related-line");
    expect(lines.map((l) => l.getAttribute("data-kind"))).toEqual(["claim", "fix", "system", "advisory"]);
    const sixth = relatedOfAdvisoryCheck.related.at(-1)!;
    const advisory = within(lines.at(-1)!);
    expect(advisory.getByText(sixth.title)).not.toBeNull();
    const link = advisory.getByTestId("related-link");
    expect(link.textContent).toBe(sixth.items[0]!.label);
    expect(link.getAttribute("href")).toBe("#/a/101/advisories?item=CVE-2022-21449");
    expect(text(lines.at(-1)!)).toContain(sixth.items[0]!.sub!);
  });
});

describe("Advisories in the app", () => {
  const appRoutes = (extra: Record<string, unknown> = {}): Routes =>
    ({
      "GET /api/session": { body: session },
      ...acmeRoutes,
      [ADVISORIES]: { body: advisoriesTwoPacks },
      ...RELATED,
      ...extra,
    }) as Routes;
  const go = (hash: string) => window.history.replaceState(null, "", hash);
  const nav = () => within(screen.getByRole("navigation", { name: "Assessment" }));

  beforeEach(() => {
    window.localStorage.clear();
  });

  it("opens from the sidebar, between Inventory and Checks, and the top bar names it", async () => {
    go("#/a/101/overview");
    mockApi(appRoutes());
    render(<App />);
    await screen.findByTestId("overview-page");
    const link = nav().getByRole("link", { name: "Advisories" });
    expect(link.getAttribute("href")).toBe("#/a/101/advisories");
    const names = nav()
      .getAllByRole("link")
      .map((a) => text(a));
    expect(names.slice(names.indexOf("Verify"), names.indexOf("Checks") + 1)).toEqual(["Verify", "Advisories", "Checks"]);
    fireEvent.click(link);
    await screen.findByTestId("advisories-standing");
    expect(window.location.hash).toBe("#/a/101/advisories");
    expect(nav().getByRole("link", { name: "Advisories" }).getAttribute("aria-current")).toBe("page");
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Advisories").getAttribute("aria-current")).toBe("page");
    expect(rows()).toHaveLength(4);
  });

  it("opens the panel of the advisory the address names", async () => {
    go(`#/a/101/advisories?item=${LOOSE}`);
    mockApi(appRoutes());
    render(<App />);
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(LOOSE));
    expect(within(panel()).getByRole("heading", { level: 2, name: looseNotOffered.name })).not.toBeNull();
  });

  it("is off until a file is in, by the same rule as Checks", async () => {
    go("#/a/101/advisories");
    const noFile = { ...acmeRoutes["GET /api/assessments/101"].body, file: null, import: null, plan_id: null };
    mockApi(appRoutes({ "GET /api/assessments/101": { body: noFile } }));
    render(<App />);
    // The page falls back to Import, and the sidebar turns Advisories off with the reason Checks has.
    await screen.findByRole("heading", { level: 1, name: "Import" });
    const off = nav().getByRole("link", { name: "Advisories" });
    expect(off.getAttribute("aria-disabled")).toBe("true");
    expect(off.getAttribute("title")).toBe(nav().getByRole("link", { name: "Checks" }).getAttribute("title"));
    expect(screen.queryByTestId("advisories-page")).toBeNull();
  });

  it("the packs line opens Settings on its Test packs section", async () => {
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(this.id);
    };
    try {
      go("#/a/101/advisories");
      mockApi(appRoutes({ "GET /api/otto": { body: ottoInstalledTwo } }));
      render(<App />);
      const packs = await screen.findByTestId("advisories-packs-line");
      const link = within(packs).getByRole("link");
      expect(link.getAttribute("href")).toBe("#/settings?section=test-packs");
      fireEvent.click(link);
      const section = await screen.findByTestId("test-packs");
      expect(within(screen.getByTestId("settings-page")).getByTestId("test-packs")).toBe(section);
      await within(section).findByTestId("otto-installed-line");
      expect(scrolled).toContain("test-packs");
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("is read-only in a closed assessment: the banner shows and Add new checks is off with the closed sentence", async () => {
    go("#/a/100/advisories");
    const fetchMock = mockApi(appRoutes({ "GET /api/assessments/100": { body: closedAssessment }, [ADVISORIES]: { body: advisoriesClosed } }));
    render(<App />);
    await screen.findByTestId("advisories-standing");
    expect(screen.getByTestId("closed-banner")).not.toBeNull();
    expect(addButton().disabled).toBe(true);
    expect(addButton().getAttribute("title")).toBe(CLOSED_SENTENCE);
    expect(screen.getByTestId("add-new-checks-reason").textContent).toBe(advisoriesClosed.add.blocked_reason);
    expect(text(screen.getByTestId("advisories-packs-line"))).toBe(advisoriesClosed.packs_line);
    fireEvent.click(addButton());
    expect(posts(fetchMock)).toEqual([]);
  });

  it("has no Guided demo bar, and after Add new checks the app reads the test plan again", async () => {
    window.localStorage.setItem("evidence-lab-guided", "on");
    go("#/a/101/advisories");
    const fetchMock = mockApi(appRoutes({ [ADVISORIES]: { body: advisoriesNotAdded }, [ADD]: { body: advisoriesAddedNotRun } }));
    render(<App />);
    await screen.findByTestId("advisories-standing");
    expect(screen.queryByTestId("guided-bar")).toBeNull();
    const plans = () => calls(fetchMock).filter((c) => c === "GET /api/import/7/plan").length;
    const before = plans();
    fireEvent.click(addButton());
    await waitFor(() => expect(plans()).toBe(before + 1));
    expect(posts(fetchMock)).toEqual([ADD]);
  });
});
