import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdvisoriesView, AdvisoryRow, OttoProposal, RelatedView } from "../api";
import App from "../App";
import { AdvisoriesScreen } from "../components/AdvisoriesScreen";
import { LinkProvider, RelatedBlock } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { DISCLAIMER, calls, mockApi, session, text } from "./fixtures";
import { proof } from "./proofFixtures";
import {
  CLOSED_REASON,
  NOT_INSTALLED_LINE,
  NO_OTTO_REASON,
  STANDING_LINE,
  advisoriesAddedNotRun,
  advisoriesAfterReconsider,
  advisoriesAfterUndo,
  advisoriesClosed,
  advisoriesFailed,
  advisoriesNoPack,
  advisoriesNotAdded,
  advisoriesOttoMissing,
  advisoriesRejected,
  advisoriesTwoPacks,
  blankFailed,
  blankNotAdded,
  blankNotRun,
  blankProposal,
  blankProposalAccepted,
  blankProposalReconsidered,
  blankProposalRejected,
  blankProposalUndone,
  blankRejected,
  looseNotOffered,
  ottoInstalledTwo,
  relatedOfAdvisory,
  relatedOfAdvisoryCheck,
  stopsNoTest,
  zeroNotAdded,
  zeroProposal,
} from "./ottoFixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";
import { acmeRoutes, closedAssessment } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];
type Decision = "accept" | "reject" | "undo" | "reconsider";

const ADVISORIES = "GET /api/plans/1/advisories";
/** The one way a decision is recorded: one proposal, one decision, one request. */
const decide = (id: string, decision: Decision) => `POST /api/plans/1/otto/proposals/${id}/${decision}`;
const BLANK = blankFailed.id;
const STOPS = stopsNoTest.id;
const ZERO = zeroNotAdded.id;
const LOOSE = looseNotOffered.id;
/** The one signing program of the demo file. */
const ACME = "acme-sign 1.4.2";

/** The Related block an advisory's panel asks for. */
const relatedRoute = (id: string, lines: RelatedView["related"] = []): Routes => ({
  [`GET /api/plans/1/related?key=${encodeURIComponent(`advisory:${id}`)}`]: {
    body: { key: `advisory:${id}`, related: lines },
  },
});
const RELATED: Routes = {
  ...relatedRoute(BLANK, relatedOfAdvisory.related),
  ...relatedRoute(STOPS),
  ...relatedRoute(ZERO),
  ...relatedRoute(LOOSE),
};

/** How often the page told the app that a decision was recorded, so that it reads the test plan again. */
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

async function open(
  view: AdvisoriesView = advisoriesTwoPacks,
  routes: Routes = {},
  props: Parameters<typeof Harness>[0] = {},
) {
  const fetchMock = mockApi({ [ADVISORIES]: { body: view }, ...RELATED, ...routes });
  render(<Harness {...props} />);
  await screen.findByTestId("advisories-standing");
  return fetchMock;
}

/** One decision as the backend answers it: the proposal as it then stands, and the page as it reads from then on. */
type Step = { route: string; answer: OttoProposal; then: AdvisoriesView };

/** A backend that moves on with each decision: every read of the page answers with the view as it stands by then. */
function deciding(start: AdvisoriesView, steps: Step[]): Routes {
  let now = start;
  const routes: Routes = { [ADVISORIES]: () => ({ body: now }) };
  for (const step of steps) {
    routes[step.route] = () => {
      now = step.then;
      return { body: step.answer };
    };
  }
  return routes;
}

/** Opens the page on a backend that moves on with each decision. */
const openDeciding = (start: AdvisoriesView, ...steps: Step[]) => open(start, deciding(start, steps));

const rows = () => screen.queryAllByTestId("advisory-row");
const ids = () => rows().map((r) => r.getAttribute("data-advisory"));
const rowOf = (id: string) => rows().find((r) => r.getAttribute("data-advisory") === id)!;
/** One of the three chips of an advisory's row. */
const chipOf = (id: string, name: "advisory-test" | "advisory-proposal" | "advisory-result") =>
  within(rowOf(id)).getByTestId(name);
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c.startsWith("POST"));
/** How often the page's view was read. */
const reads = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c === ADVISORIES).length;
/** What a request sent as its JSON body. */
function sent(fetchMock: ReturnType<typeof mockApi>, key: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => `${init?.method ?? "GET"} ${String(input)}` === key);
  const body = call?.[1]?.body;
  return body ? JSON.parse(String(body)) : null;
}
const waiting = () => screen.getByTestId("advisories-waiting");
const panel = () => screen.getByTestId("advisory-panel");
/** Clicks an advisory's row and returns its panel. */
async function openRow(id: string) {
  fireEvent.click(rowOf(id));
  await waitFor(() => expect(screen.getByTestId("advisory-panel").getAttribute("data-advisory")).toBe(id));
  return within(panel());
}
/** In the open panel: one program's row of the "here" block, Otto's proposal in it, and a button of that proposal. */
const hereRow = (program = ACME) =>
  within(panel())
    .getAllByTestId("advisory-here-row")
    .find((r) => r.getAttribute("data-program") === program)!;
const card = (program = ACME) => within(hereRow(program)).getByTestId("otto-proposal");
const button = (name: Decision, program = ACME) =>
  within(card(program)).getByTestId(`proposal-${name}`) as HTMLButtonElement;
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
  "advisory-proof-fold",
  "advisory-fix",
  "advisory-related",
];
/** Opens "Where this page's facts come from" (26 November 2026: the packs, the answers and the harness are one folded
 * line under the numbers, so the list starts on the first screen). */
const openFacts = () => {
  const toggle = within(screen.getByTestId("advisories-facts")).getAllByRole("button")[0]!;
  if (toggle.getAttribute("aria-expanded") !== "true") fireEvent.click(toggle);
};

const partsInOrder = () =>
  Array.from(panel().querySelectorAll("[data-testid]"))
    .map((el) => el.getAttribute("data-testid")!)
    .filter((id) => PARTS.includes(id));

// ---- An advisory whose test fits two signing programs of the assessment. The demo file lists one, so this state is not
// among the backend's recorded answers: it is built from them, with the backend's own words for the cell's counts.
const SECOND = "acme-verify 2.0.1";
const secondProposal: OttoProposal = proposal({
  ...blankProposal,
  id: "check-cve-2022-21449-0c1d2e3f4a5b",
  title: `Advisory check: ${blankNotAdded.name} (${BLANK}) on ${SECOND}`,
});
const TWO_WAIT: AdvisoriesView["waiting"] = {
  ...advisoriesNotAdded.waiting,
  count: 2,
  line: "2 proposed checks wait for your decision. Open an advisory to accept or reject its check.",
};
/** Otto proposes the check for both programs; nobody has decided either. */
const twoProposed: AdvisoriesView = {
  ...withFirstRow(advisoriesNotAdded, (r) => ({
    ...r,
    fits: [ACME, SECOND],
    fits_text: `${ACME}, ${SECOND}`,
    proposal: { key: "proposed", label: "Proposed", tone: "warn", text: "2 proposed", keys: ["proposed"] },
    panel: {
      ...r.panel,
      here: {
        ...r.panel.here,
        rows: [r.panel.here.rows[0]!, { ...r.panel.here.rows[0]!, program: SECOND, proposal: secondProposal }],
      },
    },
  })),
  waiting: TWO_WAIT,
};
/** The first program's check was accepted; the second still waits. The two states are counted side by side. */
const oneOfTwoAccepted: AdvisoriesView = {
  ...withFirstRow(twoProposed, (r) => ({
    ...r,
    proposal: {
      key: "mixed",
      label: "Mixed",
      tone: "warn",
      text: "1 proposed, 1 added",
      keys: ["proposed", "accepted"],
    },
    result: blankNotRun.result,
    panel: { ...r.panel, here: { ...r.panel.here, rows: [blankNotRun.panel.here.rows[0]!, r.panel.here.rows[1]!] } },
  })),
  waiting: advisoriesNotAdded.waiting,
};

/** A panel's heading by the advisory's name. (The 5c fixes: a new advisory's heading also holds the tag "New".) */
const named = (name: string) => (accessible: string) => accessible === name || accessible.startsWith(`${name} New`);

describe("Advisories, the page", () => {
  it("shows the title, the subline, the standing line, the packs line as a link to Settings, the answers line and Otto's line", async () => {
    const view = advisoriesTwoPacks;
    const fetchMock = await open(view);
    expect(screen.getByRole("heading", { level: 1, name: view.title })).not.toBeNull();
    expect(text(screen.getByTestId("page-header"))).toContain(view.subline);
    expect(screen.getByTestId("advisories-standing").textContent).toBe(view.standing_line);
    // It is the one fixed line every result screen carries (Evidence and Fixes show the same sentence).
    expect(view.standing_line).toBe(DISCLAIMER);
    // Four numbers first, counted from the rows of the table (26 November 2026): how many advisories, how many have a
    // test, how many proposed checks wait for a decision, and how many advisory checks have a result here.
    expect(
      within(screen.getByRole("list", { name: "Advisories summary" }))
        .getAllByTestId("summary-card")
        .map((card) => [card.getAttribute("data-card"), card.children[1]!.textContent]),
    ).toEqual([
      ["advisories", String(view.rows.length)],
      ["ready", String(view.rows.filter((r) => r.test.key === "ready").length)],
      ["waiting", String(view.waiting.count)],
      ["results", String(view.rows.filter((r) => ["fail", "pass", "warn"].includes(r.result.key)).length)],
    ]);
    // The numbers and the list come before the page's background; the standing line is the last thing on the page.
    const page = screen.getByTestId("advisories-page");
    expect(page.lastElementChild).toBe(screen.getByTestId("advisories-standing"));
    // Where the page's facts come from is one folded line; its hint is the packs line, so that much shows unopened.
    const facts = screen.getByTestId("advisories-facts");
    expect(within(facts).getAllByRole("button")[0]!.getAttribute("aria-expanded")).toBe("false");
    expect(text(within(facts).getAllByRole("button")[0]!)).toBe(`Where this page's facts come from${view.packs_line}`);
    openFacts();
    const packs = screen.getByTestId("advisories-packs-line");
    expect(text(packs)).toBe(view.packs_line);
    // The link goes where the view says: Settings, on its Test packs section.
    expect(within(packs).getByRole("link").getAttribute("href")).toBe("#/settings?section=test-packs");
    expect(screen.getByTestId("advisories-answers-line").textContent).toBe(view.answers_line);
    expect(screen.getByTestId("advisories-otto-line").textContent).toBe(view.otto.line);
    expect(screen.getByTestId("advisories-waiting-note").textContent).toBe(view.waiting.note);
    // Opening the page only reads: it decides nothing, adds nothing and runs nothing.
    expect(calls(fetchMock)).toEqual([ADVISORIES]);
  });

  it.each([
    ["a check waits for a decision", advisoriesNotAdded],
    ["nothing waits", advisoriesAddedNotRun],
    ["a check was rejected", advisoriesRejected],
    ["no pack is installed", advisoriesNoPack],
    ["the assessment is closed", advisoriesClosed],
    ["Otto is not installed", advisoriesOttoMissing],
  ] as const)(
    "says what waits for a decision when %s: the view's count, line, reason and note, and no button",
    async (_name, view) => {
      const fetchMock = await open(view);
      const block = waiting();
      expect(block.getAttribute("data-count")).toBe(String(view.waiting.count));
      expect(screen.getByTestId("advisories-waiting-line").textContent).toBe(view.waiting.line);
      expect(screen.getByTestId("advisories-waiting-note").textContent).toBe(view.waiting.note);
      // Why nothing can be decided is said once: not a second time when the line itself already is that reason.
      const reason =
        view.waiting.blocked_reason && view.waiting.blocked_reason !== view.waiting.line
          ? view.waiting.blocked_reason
          : null;
      const shown = screen.queryByTestId("advisories-waiting-reason");
      if (reason) expect(shown!.textContent).toBe(reason);
      else expect(shown).toBeNull();
      // The block holds the view's words and nothing else.
      expect(block.textContent).toBe(`${view.waiting.line}${reason ?? ""}${view.waiting.note}`);
      // There is no button that decides several at once: the block has none, and with no panel open nothing on the page decides.
      expect(within(block).queryAllByRole("button")).toEqual([]);
      expect(document.querySelectorAll('[data-testid^="proposal-"], [data-testid="otto-proposal"]')).toHaveLength(0);
      expect(screen.queryByTestId("add-new-checks")).toBeNull();
      expect(posts(fetchMock)).toEqual([]);
    },
  );

  it("gives each state of the waiting block its own words: a count, nothing waiting, and the three reasons nothing can be decided", () => {
    // The fixtures are the backend's answers; this pins what the tests above compared the page with.
    expect(advisoriesNotAdded.waiting.count).toBe(1);
    expect(advisoriesNotAdded.waiting.blocked_reason).toBeNull();
    expect(advisoriesAddedNotRun.waiting.count).toBe(0);
    expect(advisoriesAddedNotRun.waiting.line).not.toBe(advisoriesNotAdded.waiting.line);
    // With no pack the line is the reason, so the page says it once.
    expect(advisoriesNoPack.waiting.blocked_reason).toBe(advisoriesNoPack.waiting.line);
    for (const view of [advisoriesClosed, advisoriesOttoMissing]) {
      expect(view.waiting.blocked_reason!.length).toBeGreaterThan(10);
      expect(view.waiting.blocked_reason).not.toBe(view.waiting.line);
    }
    expect(advisoriesClosed.waiting.blocked_reason).not.toBe(advisoriesOttoMissing.waiting.blocked_reason);
    // Where nothing can be decided the line does not ask for a decision (second review, 18 November 2026): it read
    // "wait for your decision ... accept or reject" right above "nothing can be decided".
    for (const view of [advisoriesClosed, advisoriesOttoMissing]) {
      expect(view.waiting.line).toBe("1 proposed check has no decision.");
      expect(view.waiting.line).not.toMatch(/accept or reject|your decision/);
    }
  });

  it("after a retest says which version the result is of: in the table's row, and first in the panel's row", async () => {
    // The row is named for the version the file lists; after a retest its newest result is of another version.
    const RAN_ON = "This is the retest, on acme-sign 1.4.3-otto. The first run, on acme-sign 1.4.2, read Failed.";
    const SHORT = "Retest on acme-sign 1.4.3-otto. First run on acme-sign 1.4.2: Failed.";
    const retested = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      result: { ...r.result, key: "pass", label: "Passed", tone: "pass", text: SHORT },
      panel: {
        ...r.panel,
        here: {
          ...r.panel.here,
          rows: r.panel.here.rows.map((h) => ({
            ...h,
            result: h.result
              ? {
                  ...h.result,
                  label: "Passed",
                  tone: "pass" as const,
                  component: "acme-sign 1.4.3-otto",
                  ran_on: RAN_ON,
                }
              : null,
          })),
        },
      },
    }));
    await open(retested);
    expect(chipOf(BLANK, "advisory-result").textContent).toBe("Passed");
    expect(text(rowOf(BLANK))).toContain(SHORT);
    await openRow(BLANK);
    const row = within(hereRow());
    const line = row.getByTestId("advisory-here-ran-on");
    expect(line.textContent).toBe(RAN_ON);
    // It comes right after the chip and before the reviewer's sentence, so "Passed" is never read as the named version's.
    const chip = row.getByTestId("advisory-here-result");
    expect(chip.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const plain = row.getByText(retested.rows[0]!.panel.here.rows[0]!.result!.plain);
    expect(line.compareDocumentPosition(plain) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // A first run is of the version the row names: no such line.
    cleanup();
    await open(advisoriesFailed);
    await openRow(BLANK);
    expect(within(hereRow()).queryByTestId("advisory-here-ran-on")).toBeNull();
  });

  it.each([
    ["no pack installed", advisoriesNoPack, false],
    ["a proposed check", advisoriesNotAdded, false],
    ["a rejected check", advisoriesRejected, false],
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
    ["a rejected check", advisoriesRejected],
    ["a closed assessment", advisoriesClosed],
    ["Otto not installed", advisoriesOttoMissing],
  ] as const)(
    "never says score, and says 'secure' only inside the backend's standing line, with %s",
    async (_name, view) => {
      await open(view);
      // Every advisory's panel in turn, with everything in it (a folded part is in the page too).
      for (const id of ids()) {
        await openRow(id!);
        const all = document.body.textContent ?? "";
        expect(all.match(/secure/gi), id!).toHaveLength(1);
        expect(all, id!).not.toMatch(/\bscore|\bgrade\b|time.to.hack|\brisk level|\bseverity|\bcritical\b/i);
      }
      const all = document.body.textContent ?? "";
      expect(all.match(/secure/gi)).toHaveLength(1);
      expect(screen.getByTestId("advisories-standing").textContent).toMatch(/secure/);
      expect(all).not.toMatch(/\bscore|\bgrade\b|time.to.hack|\brisk level|\bseverity|\bcritical\b/i);
      // Nothing on the page takes a file, and the only thing typed is the search (a reason is typed in the Reject dialog,
      // which is there only once Reject was clicked): a pack comes from Settings, never from here.
      expect(document.querySelector('input[type="file"], textarea, form')).toBeNull();
      expect(Array.from(document.querySelectorAll("input")).map((i) => i.getAttribute("data-testid"))).toEqual([
        "advisories-search",
      ]);
      expect(all).not.toMatch(/upload|drop a file|choose a file/i);
    },
  );

  it("says so, in a plain error box, when the advisories can't be loaded", async () => {
    mockApi({
      [ADVISORIES]: {
        status: 500,
        body: { error: { message: "The advisories could not be read.", line: null, field: null } },
      },
    });
    render(<Harness />);
    expect(text(await screen.findByRole("alert"))).toContain("The advisories could not be read.");
    expect(screen.queryByTestId("advisories-waiting")).toBeNull();
    expect(screen.queryByTestId("advisories-table")).toBeNull();
  });
});

describe("Advisories, the table", () => {
  it("takes its column names from the view and shows one row per advisory: name and id, published, fits, and the three chips (test, Otto's proposal, result)", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const table = within(screen.getByTestId("advisories-table"));
    expect(table.getAllByRole("columnheader").map((th) => text(th))).toEqual(view.columns);
    expect(view.columns).toHaveLength(6);
    expect(ids()).toEqual(view.rows.map((r) => r.id));
    for (const row of view.rows) {
      const tr = rowOf(row.id);
      const cells = Array.from(tr.children);
      expect(cells, row.id).toHaveLength(6);
      // The plain name, with the id under it in a fixed-width font.
      // (The 5c fixes: an advisory that arrived with the newest pack has the tag "New" after its name.)
      const name = cells[0]!.querySelector("span");
      const id = cells[0]!.querySelector("span.font-mono");
      expect(name!.firstChild!.textContent, row.id).toBe(row.name);
      expect(within(cells[0] as HTMLElement).queryAllByTestId("advisory-new"), row.id).toHaveLength(row.new ? 1 : 0);
      expect(id!.textContent, row.id).toBe(row.id);
      expect(id!.className, row.id).toContain("font-mono");
      expect(text(cells[1]), row.id).toBe(row.published_text);
      expect(text(cells[2]), row.id).toBe(row.fits_text);
      // The three chips carry the view's words and the view's tone: the page colours nothing by itself.
      const test = within(tr).getByTestId("advisory-test");
      expect(test.textContent, row.id).toBe(row.test.label);
      expect(test.getAttribute("data-tone"), row.id).toBe(row.test.tone);
      expect(cells[3]!.contains(test), row.id).toBe(true);
      // Where Otto's proposed check stands, under the fifth column's name.
      const proposed = within(tr).getByTestId("advisory-proposal");
      expect(proposed.textContent, row.id).toBe(row.proposal.label);
      expect(proposed.getAttribute("data-tone"), row.id).toBe(row.proposal.tone);
      expect(cells[4]!.contains(proposed), row.id).toBe(true);
      expect(text(cells[4]), row.id).toBe(row.proposal.label);
      const result = within(tr).getByTestId("advisory-result");
      expect(result.textContent, row.id).toBe(row.result.label);
      expect(result.getAttribute("data-tone"), row.id).toBe(row.result.tone);
      expect(cells[5]!.contains(result), row.id).toBe(true);
      // with where it came from beside it, where the result has a tag (22 November 2026)
      expect(text(cells[5]), row.id).toBe([row.result.label, row.result.source_tag?.label].filter(Boolean).join(" "));
    }
    // The four rows of the two packs between them show every word the proposal column has for one program.
    expect(view.rows.map((r) => r.proposal.label)).toEqual([
      "Added",
      "Nothing proposed",
      "Proposed",
      "Nothing proposed",
    ]);
    expect(screen.queryByTestId("advisory-proposal-text")).toBeNull();
  });

  it("gives every Test chip a label and a reason: the reason on hover, and readable in the panel", async () => {
    await open(advisoriesTwoPacks);
    for (const row of advisoriesTwoPacks.rows) {
      const chip = chipOf(row.id, "advisory-test");
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
    const cell = rowOf(BLANK).children[5]!;
    expect(within(cell as HTMLElement).getByTestId("advisory-result").textContent).toBe(blankFailed.result.label);
    expect(text(cell)).toBe(`${blankFailed.result.label} Proven in the lab1 of 2 programs`);
    // A row without one shows the chip alone.
    expect(text(rowOf(STOPS).children[5])).toBe(stopsNoTest.result.label);
  });

  it("shows the counts under the proposal chip when the check fits several programs, never merged into one word", async () => {
    await open(oneOfTwoAccepted);
    const cell = rowOf(BLANK).children[4] as HTMLElement;
    const cellView = oneOfTwoAccepted.rows[0]!.proposal;
    const chip = within(cell).getByTestId("advisory-proposal");
    expect(chip.textContent).toBe("Mixed");
    expect(chip.getAttribute("data-tone")).toBe(cellView.tone);
    // Each state is counted by itself, in the view's words.
    expect(within(cell).getByTestId("advisory-proposal-text").textContent).toBe("1 proposed, 1 added");
    expect(text(cell)).toBe("Mixed1 proposed, 1 added");
    expect(text(rowOf(BLANK).children[2])).toBe(`${ACME}, ${SECOND}`);
    // A row with one program, or with nothing proposed, shows the chip alone.
    expect(within(rowOf(STOPS)).queryByTestId("advisory-proposal-text")).toBeNull();
    expect(text(rowOf(STOPS).children[4])).toBe(stopsNoTest.proposal.label);
  });

  it("lets a long “Not added (reason)” chip wrap inside its cell, and the panel shows the whole reason", async () => {
    const reason =
      "We will look at this again after the spring audit, once the signing service has moved to the new build pipeline";
    const long = rejectedProposal(reason, { id: blankProposal.id });
    const view = withFirstRow(advisoriesRejected, (r) => ({
      ...r,
      proposal: { ...r.proposal, label: long.status.word },
      panel: {
        ...r.panel,
        here: { ...r.panel.here, rows: [{ ...r.panel.here.rows[0]!, status: long.status.word, proposal: long }] },
      },
    }));
    await open(view);
    const chip = chipOf(BLANK, "advisory-proposal");
    expect(chip.textContent).toBe(`Not added (${reason})`);
    // The chip may break between words (its one-line look is the one that would push the table sideways), inside a
    // box with a widest size, so a reason however long makes its row taller and never the table wider.
    expect(chip.className).not.toContain("whitespace-nowrap");
    const box = within(rowOf(BLANK)).getByTestId("advisory-proposal-box");
    expect(box.contains(chip)).toBe(true);
    expect(box.className).toMatch(/\bmax-w-\[/);
    // In the panel the proposal says the reason in full, once.
    await openRow(BLANK);
    expect(within(card()).getByTestId("proposal-status").textContent).toBe(`Not added (${reason})`);
    expect(within(panel()).queryByTestId("advisory-here-status")).toBeNull();
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
    expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(
      view.filters.test.map((o) => [o.key, o.label]),
    );
    expect(select.value).toBe("all");
    for (const option of view.filters.test) {
      fireEvent.change(select, { target: { value: option.key } });
      expect(ids(), option.key).toEqual(
        view.rows.filter((r) => option.key === "all" || r.test.key === option.key).map((r) => r.id),
      );
    }
    fireEvent.change(select, { target: { value: "not_offered" } });
    expect(ids()).toEqual([LOOSE]);
    fireEvent.change(select, { target: { value: "none" } });
    expect(ids()).toEqual([STOPS]);
  });

  it("filters by Decision with the view's options, against where each row's proposal stands", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const select = screen.getByTestId("advisories-filter-decision") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(
      view.filters.decision.map((o) => [o.key, o.label]),
    );
    expect(select.value).toBe("all");
    // It sits between the Test and the Result filter, under its own name.
    const filters = Array.from(document.querySelectorAll("select")).map((s) => s.getAttribute("data-testid"));
    expect(filters).toEqual(["advisories-filter-test", "advisories-filter-decision", "advisories-filter-result"]);
    expect(screen.getByLabelText("Decision")).toBe(select);
    for (const option of view.filters.decision) {
      fireEvent.change(select, { target: { value: option.key } });
      expect(ids(), option.key).toEqual(
        view.rows.filter((r) => option.key === "all" || r.proposal.key === option.key).map((r) => r.id),
      );
    }
    fireEvent.change(select, { target: { value: "proposed" } });
    expect(ids()).toEqual([ZERO]);
    fireEvent.change(select, { target: { value: "accepted" } });
    expect(ids()).toEqual([BLANK]);
    // Nothing here was rejected, and a row Otto proposes nothing for matches no decision.
    fireEvent.change(select, { target: { value: "rejected" } });
    expect(ids()).toEqual([]);
    expect(text(screen.getByTestId("advisories-no-match"))).toMatch(/nothing matches/i);
    fireEvent.change(select, { target: { value: "all" } });
    expect(ids()).toHaveLength(4);
    // It works together with the other filters and the search.
    fireEvent.change(select, { target: { value: "accepted" } });
    fireEvent.change(screen.getByTestId("advisories-filter-result"), { target: { value: "fail" } });
    expect(ids()).toEqual([BLANK]);
    fireEvent.change(screen.getByTestId("advisories-search"), { target: { value: "elliptic" } });
    expect(ids()).toEqual([]);
  });

  it("finds a rejected check under Not added, whatever its reason", async () => {
    await open(advisoriesRejected);
    const select = screen.getByTestId("advisories-filter-decision");
    fireEvent.change(select, { target: { value: "rejected" } });
    expect(ids()).toEqual([BLANK]);
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe(blankRejected.proposal.label);
    fireEvent.change(select, { target: { value: "proposed" } });
    expect(ids()).toEqual([]);
  });

  it("matches a row whose check fits several programs under every state among them", async () => {
    await open(oneOfTwoAccepted);
    const select = screen.getByTestId("advisories-filter-decision");
    // One program's check is proposed and the other's is added: the row is "mixed", and both filters find it.
    expect(oneOfTwoAccepted.rows[0]!.proposal.key).toBe("mixed");
    fireEvent.change(select, { target: { value: "proposed" } });
    expect(ids()).toEqual([BLANK]);
    fireEvent.change(select, { target: { value: "accepted" } });
    expect(ids()).toEqual([BLANK]);
    fireEvent.change(select, { target: { value: "rejected" } });
    expect(ids()).toEqual([]);
  });

  it("filters by Result with the view's options, against each row's result key, and the filters work together", async () => {
    const view = advisoriesTwoPacks;
    await open(view);
    const select = screen.getByTestId("advisories-filter-result") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(
      view.filters.result.map((o) => [o.key, o.label]),
    );
    for (const option of view.filters.result) {
      fireEvent.change(select, { target: { value: option.key } });
      expect(ids(), option.key).toEqual(
        view.rows.filter((r) => option.key === "all" || r.result.key === option.key).map((r) => r.id),
      );
    }
    fireEvent.change(select, { target: { value: "fail" } });
    expect(ids()).toEqual([BLANK]);
    // A proposed check is not in the test plan; that is its own option.
    fireEvent.change(select, { target: { value: "not_added" } });
    expect(ids()).toEqual([ZERO]);
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
  it("says when the advisory was published under its id, because the table drops that column while the panel is open", async () => {
    await open(advisoriesFailed);
    const inPanel = await openRow(BLANK);
    const row = advisoriesFailed.rows.find((r) => r.id === BLANK)!;
    expect(inPanel.getByTestId("advisory-published").textContent).toBe(`Published ${row.published_text}`);
  });

  it("opens on a click with its parts in order, and starts nothing", async () => {
    const fetchMock = await open(advisoriesTwoPacks);
    expect(screen.queryByTestId("advisory-panel")).toBeNull();
    const inPanel = await openRow(BLANK);
    await inPanel.findByTestId("advisory-related");
    // The plain name, the id and the day it was published head the panel.
    const heading = inPanel.getByRole("heading", { level: 2, name: named(blankFailed.name) });
    // (26 November 2026: a slim tool row says what this is, then the title on a line of its own, then its id and day)
    expect(text(inPanel.getByTestId("panel-kicker"))).toBe("Advisory");
    expect(text(heading)).toBe(blankFailed.name);
    expect(text(heading.nextElementSibling)).toBe(`${blankFailed.id}Published ${blankFailed.published_text}`);
    expect(
      heading.compareDocumentPosition(inPanel.getByTestId("advisory-sentence")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // In the open: what it says, the test's status, the proposed check and the fix. Behind one fold: every record.
    expect(partsInOrder()).toEqual([
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-test-block",
      "advisory-here",
      "advisory-proof-fold",
      "advisory-fix",
      "advisory-related",
    ]);
    const fold = inPanel.getByTestId("advisory-proof-fold") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(text(within(fold).getByTestId("proof-fold-name"))).toBe("Cryptanalysis proof");
    expect(text(within(fold).getByTestId("proof-fold-inside"))).toBe("The test · The trial · The records");
    expect(fold.contains(inPanel.getByTestId("advisory-claude"))).toBe(true);
    expect(inPanel.getByTestId("advisory-sentence").textContent).toBe(blankFailed.panel.sentence);
    expect(posts(fetchMock)).toEqual([]);
    // The table beside the open panel is compact: the name, and one column that still carries the three chips.
    expect(within(screen.getByTestId("advisories-table")).getByTestId("data-table").getAttribute("data-compact")).toBe(
      "true",
    );
    expect(Array.from(rowOf(BLANK).children)).toHaveLength(2);
    const status = rowOf(BLANK).children[1] as HTMLElement;
    expect(
      Array.from(status.querySelectorAll("[data-tone]")).map((c) => [c.getAttribute("data-testid"), c.textContent]),
    ).toEqual([
      ["advisory-test", blankFailed.test.label],
      ["advisory-proposal", blankFailed.proposal.label],
      ["advisory-result", blankFailed.result.label],
    ]);
    // Its heading names the three, in the view's words.
    const headers = within(screen.getByTestId("advisories-table")).getAllByRole("columnheader");
    expect(headers).toHaveLength(2);
    expect(Array.from(headers[1]!.children).map((s) => s.textContent)).toEqual(advisoriesTwoPacks.columns.slice(3));
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

  it("shows a quote that is a raw field of a record as it stands, without a second pair of quotation marks", async () => {
    const raw = '"fixed": "6.5.7"';
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      panel: { ...r.panel, publisher: { ...r.panel.publisher!, text: raw } },
    }));
    await open(view);
    const publisher = (await openRow(BLANK)).getByTestId("advisory-publisher");
    expect(within(publisher).getByTestId("quote-raw").textContent).toBe(raw);
    expect(within(publisher).getByTestId("quote-raw").tagName).toBe("CODE");
    expect(publisher.querySelector("q")).toBeNull();
    // it is still a quote under its tag, from its named source
    expect(within(publisher).getByText(view.rows[0]!.panel.publisher!.tag)).not.toBeNull();
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
    // In the open: its label and reason, the view's.
    expect(within(block).getByText(blankFailed.test.label).parentElement!.getAttribute("data-tone")).toBe(
      blankFailed.test.tone,
    );
    expect(inBlock.getByTestId("advisory-test-reason").textContent).toBe(blankFailed.test.reason);

    // Behind the one fold, whole and in order: the test, its trial, the records.
    const fold = inPanel.getByTestId("advisory-proof-fold") as HTMLDetailsElement;
    expect(fold.tagName).toBe("DETAILS");
    expect(fold.open).toBe(false);
    const inFold = within(fold);
    expect(inFold.getByTestId("proof-fold-name").textContent).toBe("Cryptanalysis proof");
    expect(
      Array.from(fold.querySelectorAll("[data-part]")).map((el) => [
        el.getAttribute("data-testid"),
        el.querySelector("h4")!.textContent,
      ]),
    ).toEqual([
      ["proof-part-test", `1${test.title}`],
      ["proof-part-trial", `2${test.trial.title}`],
      ["proof-part-records", "3The records"],
    ]);
    const details = within(inFold.getByTestId("advisory-test-details"));
    for (const words of [test.question, test.cases_line, test.control, test.rule])
      expect(details.getByText(words), words).not.toBeNull();
    // The fingerprint is cut short; the whole value shows on hover.
    const fingerprint = details.getByTitle(test.design_fingerprint);
    expect(fingerprint.textContent).toBe(test.design_fingerprint.slice(0, 12));
    expect(text(fold)).not.toContain(test.design_fingerprint);

    const trial = within(inFold.getByTestId("advisory-trial"));
    expect(trial.getAllByRole("listitem").map((li) => li.textContent)).toEqual(test.trial.lines);

    const ledger = within(inFold.getByTestId("proof-part-records")).getByTestId(
      "advisory-ledger",
    ) as HTMLDetailsElement;
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

  it("shows the check in this assessment: Otto's proposal as it stands, then the reviewer's result with its plain sentence, the way to Checks and to the evidence, and its ledger folded", async () => {
    await open(advisoriesTwoPacks);
    const inPanel = await openRow(BLANK);
    const here = blankFailed.panel.here;
    const block = within(inPanel.getByTestId("advisory-here"));
    const heading = block.getByRole("heading", { level: 3, name: here.title });
    // Under the heading, the view's one line on who decides.
    const note = block.getByTestId("advisory-here-note");
    expect(note.textContent).toBe(here.note);
    expect(heading.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const shown = block.getAllByTestId("advisory-here-row");
    expect(shown).toHaveLength(here.rows.length);
    expect(note.compareDocumentPosition(shown[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const row = here.rows[0]!;
    const result = row.result!;
    const inRow = within(shown[0]!);
    // The program's name heads its row; the proposal comes next, then the result.
    expect(shown[0]!.getAttribute("data-program")).toBe(row.program);
    expect(shown[0]!.firstElementChild!.textContent).toBe(row.program);
    const proposed = inRow.getByTestId("otto-proposal");
    expect(proposed.getAttribute("data-proposal")).toBe(row.proposal!.id);
    // The result chip is the view's label and tone, and its reason is the reviewer's one plain sentence.
    const chip = inRow.getByTestId("advisory-here-result");
    expect(proposed.compareDocumentPosition(chip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(proposed.contains(chip)).toBe(false);
    expect(chip.textContent).toBe(result.label);
    expect(chip.getAttribute("data-tone")).toBe(result.tone);
    expect(inRow.getByText(result.plain)).not.toBeNull();
    expect(text(shown[0])).toContain(result.component!);
    // When it finished: the one time in the row that is not an entry of a folded ledger.
    const finished = Array.from(shown[0]!.querySelectorAll("time")).filter((t) => !t.closest("details"));
    expect(finished.map((t) => t.getAttribute("datetime"))).toEqual([result.finished_at]);
    expect(proposed.contains(finished[0]!)).toBe(false);
    expect(inRow.getByRole("link", { name: "Open in Checks" }).getAttribute("href")).toBe("#/a/101/checks?item=test-6");
    expect(inRow.getByRole("link", { name: "See the evidence" }).getAttribute("href")).toBe(
      "#/a/101/evidence?item=test-6",
    );
    // Two folded lists of ledger entries, each under its own name: the decisions on the proposal (inside it), then
    // the runs of the check.
    const [decisions, runs] = inRow.getAllByTestId("advisory-ledger") as HTMLDetailsElement[];
    expect(inRow.getAllByTestId("advisory-ledger")).toHaveLength(2);
    expect(proposed.contains(decisions!)).toBe(true);
    expect(text(decisions!.querySelector("summary"))).toBe(
      `${row.proposal!.history.ledger!.title} (${row.proposal!.history.ledger!.count})`,
    );
    expect(proposed.contains(runs!)).toBe(false);
    expect(runs!.open).toBe(false);
    expect(text(runs!.querySelector("summary"))).toBe(`${row.ledger!.title} (${row.ledger!.count})`);
    expect(
      within(runs!)
        .getAllByTestId("advisory-ledger-entry")
        .map((li) => li.querySelector("time")!.getAttribute("datetime")),
    ).toEqual(row.ledger!.entries.map((e) => e.at));
    expect(text(runs!)).toContain(row.ledger!.note);
    // Neither ledger is drawn as a result.
    expect(decisions!.querySelector("[data-tone]")).toBeNull();
    expect(runs!.querySelector("[data-tone]")).toBeNull();
    expect(inPanel.queryByTestId("advisory-here-status")).toBeNull();
  });

  it("says where a check stands before it has a result: proposed (no links), then added and not run (Open in Checks only)", async () => {
    await open(advisoriesNotAdded);
    await openRow(BLANK);
    let row = within(hereRow());
    // Nobody has decided: the proposal says "Proposed" itself, so the row does not say it a second time.
    expect(blankNotAdded.panel.here.rows[0]!.status).toBe("Proposed");
    expect(within(card()).getByTestId("proposal-status").textContent).toBe("Proposed");
    expect(row.queryByTestId("advisory-here-status")).toBeNull();
    expect(text(hereRow()).match(/Proposed/g)).toHaveLength(1);
    expect(row.queryByRole("link")).toBeNull();
    expect(row.queryByTestId("advisory-here-result")).toBeNull();
    expect(row.queryByTestId("advisory-ledger")).toBeNull();

    // The same advisory once its proposal was accepted: the check is in the plan and has not run.
    cleanup();
    await open(advisoriesAddedNotRun);
    await openRow(BLANK);
    row = within(hereRow());
    expect(within(card()).getByTestId("proposal-status").textContent).toBe("Added");
    expect(row.getByTestId("advisory-here-status").textContent).toBe(blankNotRun.panel.here.rows[0]!.status);
    expect(row.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Open in Checks", "#/a/101/checks?item=test-6"],
    ]);
    const ledger = blankNotRun.panel.here.rows[0]!.ledger!;
    const ledgers = row.getAllByTestId("advisory-ledger");
    expect(text(ledgers.at(-1)!.querySelector("summary"))).toBe(`${ledger.title} (${ledger.count})`);
    expect(card().contains(ledgers.at(-1)!)).toBe(false);
  });

  it("shows a program's row that has no proposal with the view's own word for where it stands", async () => {
    // Not among the recorded answers: a check with nothing proposed for it reads as the backend words it.
    const view = withFirstRow(advisoriesNotAdded, (r) => ({
      ...r,
      panel: {
        ...r.panel,
        here: { ...r.panel.here, rows: [{ ...r.panel.here.rows[0]!, status: "Not in the test plan", proposal: null }] },
      },
    }));
    await open(view);
    await openRow(BLANK);
    expect(within(hereRow()).queryByTestId("otto-proposal")).toBeNull();
    expect(within(hereRow()).getByTestId("advisory-here-status").textContent).toBe("Not in the test plan");
    expect(within(hereRow()).queryByRole("button")).toBeNull();
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
    expect(within(here).getByRole("link", { name: fix.here!.label }).getAttribute("href")).toBe(
      "#/a/101/fixes?item=fix-ecdsa-range-check",
    );
    // The fix is decided on Fixes: this block has no button.
    expect(within(block).queryByRole("button")).toBeNull();
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
    expect(calls(fetchMock)).toContain(
      `GET /api/plans/1/related?key=${encodeURIComponent(blankFailed.panel.related_key)}`,
    );
    expect(related.getAllByTestId("related-line").map((l) => l.getAttribute("data-kind"))).toEqual(
      relatedOfAdvisory.related.map((l) => l.kind),
    );
    // Each entry carries the backend's label and goes where the backend says: the check's evidence, the fix in Fixes.
    const [check, fix] = relatedOfAdvisory.related.map((l) => l.items[0]!);
    expect(related.getAllByTestId("related-link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      [check!.label, "#/a/101/evidence?item=test-6"],
      [fix!.label, "#/a/101/fixes?item=fix-ecdsa-range-check"],
    ]);
    expect(partsInOrder().at(-1)).toBe("advisory-related");
    // An advisory nothing relates to yet has no Related block.
    const other = await openRow(STOPS);
    await waitFor(() =>
      expect(calls(fetchMock)).toContain(
        `GET /api/plans/1/related?key=${encodeURIComponent(stopsNoTest.panel.related_key)}`,
      ),
    );
    expect(other.queryByTestId("advisory-related")).toBeNull();
  });

  it("shows an advisory with no test yet: its label and reason, nothing proposed and nothing to run here, and no fix label", async () => {
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
    // No trial was run for it; Otto's ledger entries are in the fold, which is a record here and no proof.
    const fold = inPanel.getByTestId("advisory-proof-fold");
    expect(within(fold).getByTestId("proof-fold-name").textContent).toBe("Technical record");
    expect(fold.getAttribute("data-kind")).toBe("record");
    expect(within(fold).queryByTestId("advisory-trial")).toBeNull();
    expect(text(within(fold).getByTestId("advisory-ledger").querySelector("summary"))).toBe(
      `${noTest.ledger!.title} (${noTest.ledger!.count})`,
    );

    // Otto proposes nothing for it: no row, no proposal, no button and no line on deciding.
    const here = inPanel.getByTestId("advisory-here");
    expect(within(here).queryAllByTestId("advisory-here-row")).toHaveLength(0);
    expect(within(here).getByTestId("advisory-here-empty").textContent).toBe(stopsNoTest.panel.here.empty);
    expect(within(here).queryByTestId("advisory-here-note")).toBeNull();
    expect(inPanel.queryByTestId("otto-proposal")).toBeNull();
    expect(within(here).queryByRole("button")).toBeNull();
    const fix = inPanel.getByTestId("advisory-fix");
    expect(within(fix).queryByTestId("advisory-fix-label")).toBeNull();
    for (const line of stopsNoTest.panel.fix.lines) expect(within(fix).getByText(line), line).not.toBeNull();
    expect(within(fix).queryByTestId("advisory-fix-here")).toBeNull();
    expect(within(inPanel.getByTestId("advisory-claude")).getAllByTestId("advisory-step")).toHaveLength(
      stopsNoTest.panel.claude.steps.length,
    );
    expect(partsInOrder()).toEqual([
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-no-test",
      "advisory-here",
      "advisory-proof-fold",
      "advisory-fix",
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
    // How its design did is kept whole in the fold: a record, since no test came of it.
    const fold = inPanel.getByTestId("advisory-proof-fold");
    expect(within(fold).getByTestId("proof-fold-name").textContent).toBe("Technical record");
    const part = within(fold).getByTestId("proof-part-trial");
    expect(within(part).getByRole("heading", { level: 4 }).textContent).toBe(`1${noTest.trial!.title}`);
    const trial = within(within(part).getByTestId("advisory-trial"));
    expect(trial.getAllByRole("listitem").map((li) => li.textContent)).toEqual(noTest.trial!.lines);
    expect(within(fold).getByTestId("advisory-ledger")).not.toBeNull();
    expect(within(inPanel.getByTestId("advisory-here")).getByTestId("advisory-here-empty").textContent).toBe(
      looseNotOffered.panel.here.empty,
    );
    expect(inPanel.queryByTestId("otto-proposal")).toBeNull();
  });

  it("shows the notes and the other names of an advisory when the view has them, between what is affected and the test", async () => {
    // Not in the samples (their advisories have neither): the fields are filled in here to see them drawn.
    const said = {
      title: "Otto's notes on reading it",
      kind_line:
        "Kind of weakness, as recorded: the affected software accepts a signature it must reject, when checking ECDSA signatures.",
      text: "The publisher lists Java 15 to 18 as affected.",
      caption:
        "Claude's words from reading the advisory (Recorded during the build, not through the API). Information, not a result.",
    };
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      panel: { ...r.panel, notes: said, also_known_as: ["GHSA-4w7w-66w2-5vf9", "JDK-8277233"] },
    }));
    await open(view);
    let inPanel = await openRow(BLANK);
    // Claude's own words are long and are not a result: they stay folded under their name, with where they came from.
    const fold = inPanel.getByTestId("advisory-notes") as HTMLDetailsElement;
    expect(fold.tagName).toBe("DETAILS");
    expect(fold.open).toBe(false);
    expect(within(fold).getByText(said.title).tagName).toBe("SUMMARY");
    expect(inPanel.getByTestId("advisory-notes-kind").textContent).toBe(said.kind_line);
    expect(inPanel.getByTestId("advisory-notes-text").textContent).toBe(said.text);
    expect(text(fold)).toContain(said.caption);
    expect(text(inPanel.getByTestId("advisory-also-known-as"))).toContain("GHSA-4w7w-66w2-5vf9, JDK-8277233");
    expect(partsInOrder().slice(0, 5)).toEqual([
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-test-block",
    ]);
    const notes = inPanel.getByTestId("advisory-notes");
    expect(
      inPanel.getByTestId("advisory-affected").compareDocumentPosition(notes) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      notes.compareDocumentPosition(inPanel.getByTestId("advisory-test-block")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    // The second row has neither.
    inPanel = await openRow(STOPS);
    expect(inPanel.queryByTestId("advisory-notes")).toBeNull();
    expect(inPanel.queryByTestId("advisory-also-known-as")).toBeNull();
  });

  it("draws no publisher's line for an advisory that could not be read, and still lists its sources", async () => {
    const view = withFirstRow(advisoriesFailed, (r) => ({
      ...r,
      name: "An advisory that could not be read",
      panel: {
        ...r.panel,
        sentence: "The advisory's text could not be matched to its publisher's page.",
        publisher: null,
        affected: null,
      },
    }));
    await open(view);
    const inPanel = await openRow(BLANK);
    expect(inPanel.getByTestId("advisory-sentence").textContent).toBe(
      "The advisory's text could not be matched to its publisher's page.",
    );
    expect(inPanel.queryByTestId("advisory-publisher")).toBeNull();
    expect(inPanel.queryByTestId("advisory-affected")).toBeNull();
    expect(inPanel.getByTestId("advisory-sources")).not.toBeNull();
  });

  it("opens the advisory a link names, switches on a click on another row, and closes from its button or Escape", async () => {
    await open(advisoriesTwoPacks, {}, { item: LOOSE });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(LOOSE));
    expect(within(panel()).getByRole("heading", { level: 2, name: named(looseNotOffered.name) })).not.toBeNull();
    // The shared panel of every table page, with its close button, is inside.
    expect(within(panel()).getByTestId("detail-panel")).not.toBeNull();
    await openRow(ZERO);
    expect(within(panel()).getByRole("heading", { level: 2, name: named(zeroNotAdded.name) })).not.toBeNull();
    fireEvent.click(within(panel()).getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("advisory-panel")).toBeNull();
    expect(
      within(screen.getByTestId("advisories-table")).getByTestId("data-table").getAttribute("data-compact"),
    ).toBeNull();
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
    // The Decision filter hides its row the same way, and the panel stays.
    fireEvent.change(screen.getByTestId("advisories-filter-test"), { target: { value: "all" } });
    fireEvent.change(screen.getByTestId("advisories-filter-decision"), { target: { value: "proposed" } });
    expect(ids()).toEqual([ZERO]);
    expect(panel().getAttribute("data-advisory")).toBe(BLANK);
  });
});

describe("Advisories, a test that was tried on sandbox copies", () => {
  const withProofOnCard: AdvisoryRow = {
    ...blankNotAdded,
    panel: {
      ...blankNotAdded.panel,
      test: { ...blankNotAdded.panel.test!, proof: proof() },
      here: {
        ...blankNotAdded.panel.here,
        rows: blankNotAdded.panel.here.rows.map((h) => ({
          ...h,
          proposal: h.proposal ? { ...h.proposal, proof: proof() } : null,
        })),
      },
    },
  };

  it("shows the proof once, with the proposal, and labels the test block Sandbox copy", async () => {
    const fetchMock = await open({ ...advisoriesNotAdded, rows: [withProofOnCard, stopsNoTest] });
    const inPanel = await openRow(BLANK);
    expect(inPanel.getByTestId("advisory-sandbox-label").textContent).toBe("Sandbox copy");
    // Once: the three counts and what they do not show stand with the test, and every part of the proof is in the
    // one fold. The proposal's card repeats neither.
    const block = inPanel.getByTestId("advisory-test-block");
    expect(inPanel.getAllByTestId("proof-tiles")).toHaveLength(1);
    expect(within(block).getAllByTestId("proof-tile")).toHaveLength(3);
    expect(within(block).getByTestId("proof-not-shown").textContent).toBe(proof().not_shown);
    expect(within(card()).queryByTestId("proof-block")).toBeNull();
    expect(within(card()).queryByTestId("proof-tiles")).toBeNull();
    const fold = inPanel.getByTestId("advisory-proof-fold");
    expect(inPanel.getAllByTestId("proof-rows")).toHaveLength(1);
    expect(
      Array.from(fold.querySelectorAll('[data-testid^="proof-part-"]')).map((el) => el.getAttribute("data-testid")),
    ).toEqual([
      "proof-part-test",
      "proof-part-trial",
      "proof-part-frozen",
      "proof-part-code",
      "proof-part-copies",
      "proof-part-replay",
      "proof-part-records",
    ]);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]); // (showing the proof sent nothing)
  });

  it("shows the proof with the test where no program has a proposal for it", async () => {
    const alone: AdvisoryRow = {
      ...withProofOnCard,
      panel: { ...withProofOnCard.panel, here: { ...withProofOnCard.panel.here, rows: [] } },
    };
    await open({ ...advisoriesNotAdded, rows: [alone, stopsNoTest] });
    const inPanel = await openRow(BLANK);
    const block = inPanel.getByTestId("advisory-test-block");
    expect(within(block).getAllByTestId("proof-tiles")).toHaveLength(1);
    expect(within(inPanel.getByTestId("advisory-proof-fold")).getAllByTestId("proof-rows")).toHaveLength(1);
  });

  it("shows what a trial on sandbox copies showed for a test that is not offered", async () => {
    const refused: AdvisoryRow = {
      ...looseNotOffered,
      panel: { ...looseNotOffered.panel, no_test: { ...looseNotOffered.panel.no_test!, proof: proof() } },
    };
    await open({ ...advisoriesTwoPacks, rows: [refused] });
    const inPanel = await openRow(refused.id);
    // No test came of it, so no counts are held up as a proof: what the trial does not show is said in the open, and
    // the trial itself is kept part by part in the fold, a Technical record.
    expect(within(inPanel.getByTestId("advisory-no-test")).getByTestId("proof-not-shown").textContent).toBe(
      proof().not_shown,
    );
    expect(inPanel.queryByTestId("proof-tiles")).toBeNull();
    const fold = inPanel.getByTestId("advisory-proof-fold");
    expect(within(fold).getByTestId("proof-fold-name").textContent).toBe("Technical record");
    expect(within(fold).getAllByTestId("proof-rows")).toHaveLength(1);
  });

  it("labels a result that came from a sandbox copy, and no other", async () => {
    const onCopy: AdvisoryRow = {
      ...blankFailed,
      panel: {
        ...blankFailed.panel,
        here: {
          ...blankFailed.panel.here,
          rows: blankFailed.panel.here.rows.map((h) => ({
            ...h,
            result: h.result ? { ...h.result, sandbox_copy: true } : null,
          })),
        },
      },
    };
    await open({ ...advisoriesFailed, rows: [onCopy, stopsNoTest] });
    expect((await openRow(BLANK)).getByTestId("advisory-here-sandbox").textContent).toBe("Sandbox copy");
    cleanup();
    await open(advisoriesFailed);
    expect((await openRow(BLANK)).queryByTestId("advisory-here-sandbox")).toBeNull();
  });
});

describe("Advisories, Otto proposes and a person decides", () => {
  it("shows each proposed check in its advisory's panel: From Otto, why it applies, that nobody has decided, with Accept and Reject", async () => {
    const fetchMock = await open(advisoriesNotAdded);
    const inPanel = await openRow(BLANK);
    const shown = blankProposal;
    // One program: that accepting runs nothing is said once, under the card's own buttons, and not above them too.
    expect(inPanel.queryByTestId("advisory-here-note")).toBeNull();
    expect(inPanel.getAllByTestId("otto-proposal")).toHaveLength(1);
    const it = card();
    expect(it.getAttribute("data-proposal")).toBe(shown.id);
    expect(it.getAttribute("data-kind")).toBe("check");
    expect(it.getAttribute("data-state")).toBe("proposed");
    const inCard = within(it);
    // Every word is the view's.
    expect(inCard.getByTestId("proposal-label").textContent).toBe(shown.label);
    expect(inCard.getByTestId("proposal-status").textContent).toBe(shown.status.word);
    expect(inCard.getByTestId("proposal-status").getAttribute("data-tone")).toBe(shown.status.tone);
    expect(text(inCard.getByTestId("proposal-why"))).toBe(`${shown.why_label}: ${shown.why}`);
    // The test stands above the card and its question, cases, control and trial are in the fold below: the card does
    // not say them a second time here (it does wherever it stands alone).
    expect(inCard.queryByTestId("proposal-lines")).toBeNull();
    expect(inCard.getByTestId("proposal-decided").textContent).toBe(shown.decided_line);
    expect(inCard.getByTestId("proposal-note").textContent).toBe(shown.note);
    // The program's name heads the row, so the proposal's own title is not said a second time.
    expect(hereRow().firstElementChild!.textContent).toBe(ACME);
    expect(inCard.queryByTestId("proposal-title")).toBeNull();
    expect(text(panel())).not.toContain(shown.title);
    // Two buttons, in the view's words, and nothing decided yet: no history, and nothing was sent.
    expect(
      Array.from(it.querySelectorAll("button")).map((b) => [b.getAttribute("data-testid"), b.textContent, b.disabled]),
    ).toEqual([
      ["proposal-accept", "Accept", false],
      ["proposal-reject", "Reject", false],
    ]);
    expect(inCard.queryByTestId("proposal-history")).toBeNull();
    expect(inCard.queryByTestId("proposal-blocked")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
    expect(planChanged).toBe(0);
  });

  it("Accept records one decision on one proposal, then the page is read again and the app is told the test plan changed", async () => {
    const accept = decide(blankProposal.id, "accept");
    const fetchMock = await openDeciding(advisoriesNotAdded, {
      route: accept,
      answer: blankProposalAccepted,
      then: advisoriesAddedNotRun,
    });
    expect(waiting().getAttribute("data-count")).toBe("1");
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed");
    expect(chipOf(BLANK, "advisory-result").textContent).toBe(blankNotAdded.result.label);
    await openRow(BLANK);
    expect(reads(fetchMock)).toBe(1);

    fireEvent.click(button("accept"));
    await waitFor(() => expect(waiting().getAttribute("data-count")).toBe("0"));
    // One request decided it: this proposal, accept, and nothing else sent with it.
    expect(posts(fetchMock)).toEqual([accept]);
    expect(sent(fetchMock, accept)).toEqual({});
    // Then the whole page was read again: the decision moved the waiting line, the row's chips and the panel.
    const all = calls(fetchMock);
    expect(reads(fetchMock)).toBe(2);
    expect(all.lastIndexOf(ADVISORIES)).toBeGreaterThan(all.indexOf(accept));
    expect(screen.getByTestId("advisories-waiting-line").textContent).toBe(advisoriesAddedNotRun.waiting.line);
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Added");
    expect(chipOf(BLANK, "advisory-proposal").getAttribute("data-tone")).toBe(blankNotRun.proposal.tone);
    expect(chipOf(BLANK, "advisory-result").textContent).toBe(blankNotRun.result.label);
    // The panel stays open on the same advisory. Its proposal says who decided and when, and offers Undo.
    expect(panel().getAttribute("data-advisory")).toBe(BLANK);
    expect(card().getAttribute("data-state")).toBe("accepted");
    expect(within(card()).getByTestId("proposal-status").textContent).toBe("Added");
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(blankProposalAccepted.decided_line);
    expect(within(card()).getByTestId("proposal-effect").textContent).toBe(blankProposalAccepted.effect);
    expect(
      within(card())
        .getAllByTestId("proposal-decision")
        .map((li) => li.textContent),
    ).toEqual(blankProposalAccepted.history.rows.map((r) => r.line));
    expect(within(card()).queryByTestId("proposal-accept")).toBeNull();
    expect(within(card()).queryByTestId("proposal-reject")).toBeNull();
    expect(button("undo").disabled).toBe(false);
    // The check is in the plan and has not run: nothing ran by accepting it.
    expect(within(hereRow()).getByTestId("advisory-here-status").textContent).toBe("Not run yet");
    expect(within(hereRow()).queryByTestId("advisory-here-result")).toBeNull();
    expect(within(hereRow()).getByRole("link", { name: "Open in Checks" }).getAttribute("href")).toBe(
      "#/a/101/checks?item=test-6",
    );
    expect(all.filter((c) => !c.startsWith("GET "))).toEqual([accept]);
    // The app is told once that the test plan changed.
    expect(planChanged).toBe(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Reject asks for an optional short reason, sends it, and the proposal stays on the page as “Not added (reason)”", async () => {
    const reject = decide(blankProposal.id, "reject");
    const fetchMock = await openDeciding(advisoriesNotAdded, {
      route: reject,
      answer: blankProposalRejected,
      then: advisoriesRejected,
    });
    await openRow(BLANK);

    // Reject opens a dialog in the view's words. Opening it records nothing, and neither does Cancel.
    fireEvent.click(button("reject"));
    const dialog = blankProposal.reject_dialog!;
    const box = screen.getByTestId("proposal-reject-dialog");
    expect(within(box).getByRole("heading", { name: dialog.title })).not.toBeNull();
    expect(text(box)).toContain(dialog.line);
    expect(text(box)).toContain(dialog.reason_label);
    fireEvent.change(within(box).getByTestId("proposal-reject-reason"), {
      target: { value: "A reason that is thrown away" },
    });
    fireEvent.click(within(box).getByTestId("proposal-reject-cancel"));
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
    expect(card().getAttribute("data-state")).toBe("proposed");

    fireEvent.click(button("reject"));
    const field = screen.getByTestId("proposal-reject-reason") as HTMLInputElement;
    expect(field.maxLength).toBe(dialog.max);
    fireEvent.change(field, { target: { value: "  Not this quarter " } });
    expect(screen.getByTestId("proposal-reject-confirm").textContent).toBe(dialog.confirm);
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Not added (Not this quarter)"));
    // One request, with the reason as it was typed (without the spaces around it).
    expect(posts(fetchMock)).toEqual([reject]);
    expect(sent(fetchMock, reject)).toEqual({ reason: "Not this quarter" });
    expect(reads(fetchMock)).toBe(2);
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    // Nothing is deleted: the row and its proposal stay, with the reason, who rejected it and when, and Reconsider.
    expect(ids()).toEqual(advisoriesRejected.rows.map((r) => r.id));
    expect(chipOf(BLANK, "advisory-proposal").getAttribute("data-tone")).toBe(blankRejected.proposal.tone);
    expect(card().getAttribute("data-state")).toBe("rejected");
    expect(within(card()).getByTestId("proposal-status").textContent).toBe("Not added (Not this quarter)");
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(blankProposalRejected.decided_line);
    expect(
      within(card())
        .getAllByTestId("proposal-decision")
        .map((li) => li.textContent),
    ).toEqual(blankProposalRejected.history.rows.map((r) => r.line));
    expect(within(card()).queryByTestId("proposal-accept")).toBeNull();
    expect(button("reconsider").disabled).toBe(false);
    // The row says it once (the proposal does), and the check is not in the test plan.
    expect(within(panel()).queryByTestId("advisory-here-status")).toBeNull();
    expect(chipOf(BLANK, "advisory-result").textContent).toBe(blankRejected.result.label);
    expect(within(hereRow()).queryByRole("link")).toBeNull();
    expect(waiting().getAttribute("data-count")).toBe("0");
    // The app is told after every decision, once.
    expect(planChanged).toBe(1);
  });

  it("Reject with no reason sends none", async () => {
    const reject = decide(blankProposal.id, "reject");
    const noReason = rejectedProposal("", {
      id: blankProposal.id,
      status: { key: "rejected", word: "Not added", tone: "neutral" },
    });
    const after = withFirstRow(advisoriesRejected, (r) => ({
      ...r,
      proposal: { ...r.proposal, label: "Not added" },
      panel: {
        ...r.panel,
        here: { ...r.panel.here, rows: [{ ...r.panel.here.rows[0]!, status: "Not added", proposal: noReason }] },
      },
    }));
    const fetchMock = await openDeciding(advisoriesNotAdded, { route: reject, answer: noReason, then: after });
    await openRow(BLANK);
    fireEvent.click(button("reject"));
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Not added"));
    expect(posts(fetchMock)).toEqual([reject]);
    expect(sent(fetchMock, reject)).toEqual({});
    expect(card().getAttribute("data-state")).toBe("rejected");
  });

  it("Undo takes an accepted check out of the test plan again: one request, the page read again, and the app told", async () => {
    const undo = decide(blankProposal.id, "undo");
    const fetchMock = await openDeciding(advisoriesAddedNotRun, {
      route: undo,
      answer: blankProposalUndone,
      then: advisoriesAfterUndo,
    });
    await openRow(BLANK);
    expect(card().getAttribute("data-state")).toBe("accepted");
    expect(within(card()).getByTestId("proposal-note").textContent).toBe(blankProposalAccepted.note);
    expect(Array.from(card().querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Undo"]);

    fireEvent.click(button("undo"));
    await waitFor(() => expect(waiting().getAttribute("data-count")).toBe("1"));
    expect(posts(fetchMock)).toEqual([undo]);
    expect(sent(fetchMock, undo)).toEqual({});
    expect(reads(fetchMock)).toBe(2);
    // It is open for a decision again, and the check is out of the plan: no link to Checks any more.
    expect(card().getAttribute("data-state")).toBe("proposed");
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(blankProposalUndone.decided_line);
    expect(button("accept").disabled).toBe(false);
    expect(button("reject").disabled).toBe(false);
    expect(within(card()).queryByTestId("proposal-undo")).toBeNull();
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed");
    expect(chipOf(BLANK, "advisory-result").textContent).toBe(blankNotAdded.result.label);
    expect(within(hereRow()).queryByRole("link")).toBeNull();
    expect(within(hereRow()).queryByTestId("advisory-here-status")).toBeNull();
    // Both decisions stay on the record.
    expect(
      within(card())
        .getAllByTestId("proposal-decision")
        .map((li) => li.textContent),
    ).toEqual(blankProposalUndone.history.rows.map((r) => r.line));
    expect(blankProposalUndone.history.rows).toHaveLength(2);
    // The test plan changed again, so the app is told.
    expect(planChanged).toBe(1);
  });

  it("Reconsider takes a rejected proposal up again: one request, then the page is read again and the app is told", async () => {
    const reconsider = decide(blankProposal.id, "reconsider");
    const fetchMock = await openDeciding(advisoriesRejected, {
      route: reconsider,
      answer: blankProposalReconsidered,
      then: advisoriesAfterReconsider,
    });
    expect(waiting().getAttribute("data-count")).toBe("0");
    await openRow(BLANK);
    expect(card().getAttribute("data-state")).toBe("rejected");
    expect(Array.from(card().querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Reconsider"]);

    fireEvent.click(button("reconsider"));
    await waitFor(() => expect(waiting().getAttribute("data-count")).toBe("1"));
    expect(posts(fetchMock)).toEqual([reconsider]);
    expect(sent(fetchMock, reconsider)).toEqual({});
    expect(reads(fetchMock)).toBe(2);
    expect(card().getAttribute("data-state")).toBe("proposed");
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(blankProposalReconsidered.decided_line);
    expect(button("accept").disabled).toBe(false);
    expect(button("reject").disabled).toBe(false);
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed");
    // The reject and its reason stay on the record.
    expect(
      within(card())
        .getAllByTestId("proposal-decision")
        .map((li) => li.textContent),
    ).toEqual(blankProposalReconsidered.history.rows.map((r) => r.line));
    expect(text(within(card()).getByTestId("proposal-history"))).toContain("Not this quarter");
    expect(planChanged).toBe(1);
  });

  it("walks one proposal through accept, undo, reject and reconsider, one request each, and reads the page after each", async () => {
    const id = blankProposal.id;
    const fetchMock = await openDeciding(
      advisoriesNotAdded,
      { route: decide(id, "accept"), answer: blankProposalAccepted, then: advisoriesAddedNotRun },
      { route: decide(id, "undo"), answer: blankProposalUndone, then: advisoriesAfterUndo },
      { route: decide(id, "reject"), answer: blankProposalRejected, then: advisoriesRejected },
      { route: decide(id, "reconsider"), answer: blankProposalReconsidered, then: advisoriesAfterReconsider },
    );
    await openRow(BLANK);
    fireEvent.click(button("accept"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Added"));
    fireEvent.click(button("undo"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed"));
    fireEvent.click(button("reject"));
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "Not this quarter" } });
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Not added (Not this quarter)"));
    fireEvent.click(button("reconsider"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed"));
    expect(posts(fetchMock)).toEqual((["accept", "undo", "reject", "reconsider"] as const).map((d) => decide(id, d)));
    expect(reads(fetchMock)).toBe(5);
    // The app was told once for each decision.
    expect(planChanged).toBe(4);
    expect(waiting().getAttribute("data-count")).toBe("1");
  });

  it("sends nothing but reads until a decision button is pressed: not on opening the page, a panel or the Reject dialog", async () => {
    const fetchMock = await open(advisoriesTwoPacks);
    for (const id of ids()) {
      await openRow(id!);
      // every fold of the panel, opened
      for (const fold of Array.from(panel().querySelectorAll("details")))
        fireEvent.click(fold.querySelector("summary")!);
    }
    await openRow(ZERO);
    fireEvent.click(button("reject"));
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "Thinking about it" } });
    fireEvent.keyDown(screen.getByTestId("proposal-reject-reason"), { key: "Escape" });
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    // Escape in the reason field closed the dialog only: the panel is still there.
    expect(panel().getAttribute("data-advisory")).toBe(ZERO);
    await waitFor(() =>
      expect(calls(fetchMock)).toContain(
        `GET /api/plans/1/related?key=${encodeURIComponent(looseNotOffered.panel.related_key)}`,
      ),
    );
    const all = calls(fetchMock);
    expect(all.every((c) => c.startsWith("GET "))).toBe(true);
    // The page was read once, and each panel asked only for its Related block.
    expect(reads(fetchMock)).toBe(1);
    expect(Array.from(new Set(all)).sort()).toEqual([ADVISORIES, ...Object.keys(RELATED)].sort());
    expect(planChanged).toBe(0);
  });

  it("records one decision when Accept is pressed twice in a row, and every button of the proposal waits meanwhile", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const accept = decide(blankProposal.id, "accept");
    let now = advisoriesNotAdded;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(input)}`;
      let body: unknown;
      if (key === accept) {
        await gate;
        now = advisoriesAddedNotRun;
        body = blankProposalAccepted;
      } else if (key === ADVISORIES) body = now;
      else if (key.startsWith("GET /api/plans/1/related?")) body = { key: `advisory:${BLANK}`, related: [] };
      else throw new Error(`Unexpected request: ${key}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<Harness />);
    await screen.findByTestId("advisories-standing");
    await openRow(BLANK);

    fireEvent.click(button("accept"));
    await waitFor(() => expect(button("accept").getAttribute("aria-busy")).toBe("true"));
    expect(button("accept").disabled).toBe(true);
    expect(button("reject").disabled).toBe(true);
    // The button keeps the view's word while it waits.
    expect(button("accept").textContent).toBe("Accept");
    fireEvent.click(button("accept"));
    fireEvent.click(button("reject"));
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    release();
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Added"));
    expect(card().getAttribute("data-state")).toBe("accepted");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(planChanged).toBe(1);
  });

  it("shows a refusal in the proposal, in the backend's words, and leaves the page as it was", async () => {
    const accept = decide(blankProposal.id, "accept");
    const refusal = "This proposal was decided in the meantime. Read the page again.";
    const fetchMock = await open(advisoriesNotAdded, {
      [accept]: { status: 409, body: { error: { message: refusal, line: null, field: null } } },
    });
    await openRow(BLANK);
    fireEvent.click(button("accept"));
    const alert = await within(card()).findByRole("alert");
    expect(text(alert)).toBe(refusal);
    expect(posts(fetchMock)).toEqual([accept]);
    // Nothing was decided: the page is not read again, the plan is not, and the proposal can still be decided.
    expect(reads(fetchMock)).toBe(1);
    expect(planChanged).toBe(0);
    expect(card().getAttribute("data-state")).toBe("proposed");
    expect(button("accept").disabled).toBe(false);
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed");
    expect(waiting().getAttribute("data-count")).toBe("1");
  });

  it("keeps the recorded decision on screen and says so plainly when the page can't be read again after it", async () => {
    const accept = decide(blankProposal.id, "accept");
    const trouble = "The advisories could not be read.";
    let asked = 0;
    const fetchMock = await open(advisoriesNotAdded, {
      // The first read answers; the read after the decision fails.
      [ADVISORIES]: () =>
        (asked += 1) === 1
          ? { body: advisoriesNotAdded }
          : { status: 500, body: { error: { message: trouble, line: null, field: null } } },
      [accept]: { body: blankProposalAccepted },
    });
    await openRow(BLANK);
    fireEvent.click(button("accept"));
    const alert = await within(waiting()).findByRole("alert");
    expect(text(alert)).toBe(trouble);
    expect(posts(fetchMock)).toEqual([accept]);
    expect(reads(fetchMock)).toBe(2);
    // The decision was recorded, and the proposal shows the backend's own answer for it.
    expect(card().getAttribute("data-state")).toBe("accepted");
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(blankProposalAccepted.decided_line);
    expect(button("undo").disabled).toBe(false);
    expect(planChanged).toBe(1);
    // The page is still there, as it was last read.
    expect(ids()).toEqual(advisoriesNotAdded.rows.map((r) => r.id));
  });

  it("decides each program's check by itself when the test fits several programs", async () => {
    const accept = decide(blankProposal.id, "accept");
    const fetchMock = await openDeciding(twoProposed, {
      route: accept,
      answer: blankProposalAccepted,
      then: oneOfTwoAccepted,
    });
    // Before: both wait. The cell counts them, and the waiting line says two.
    expect(waiting().getAttribute("data-count")).toBe("2");
    expect(screen.getByTestId("advisories-waiting-line").textContent).toBe(TWO_WAIT.line);
    expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Proposed");
    expect(within(rowOf(BLANK)).getByTestId("advisory-proposal-text").textContent).toBe("2 proposed");
    const inPanel = await openRow(BLANK);
    // With several programs the block's own line stays: it says that each is decided by itself.
    expect(inPanel.getByTestId("advisory-here-note").textContent).toBe(twoProposed.rows[0]!.panel.here.note);
    // One row and one proposal per program, each with its own buttons.
    expect(inPanel.getAllByTestId("advisory-here-row").map((r) => r.getAttribute("data-program"))).toEqual([
      ACME,
      SECOND,
    ]);
    expect(inPanel.getAllByTestId("otto-proposal").map((c) => c.getAttribute("data-proposal"))).toEqual([
      blankProposal.id,
      secondProposal.id,
    ]);
    expect(inPanel.getAllByTestId("proposal-accept")).toHaveLength(2);
    expect(card(SECOND).contains(button("accept"))).toBe(false);

    fireEvent.click(button("accept", ACME));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Mixed"));
    // One request, for the first program's proposal only.
    expect(posts(fetchMock)).toEqual([accept]);
    expect(within(rowOf(BLANK)).getByTestId("advisory-proposal-text").textContent).toBe("1 proposed, 1 added");
    expect(waiting().getAttribute("data-count")).toBe("1");
    expect(card(ACME).getAttribute("data-state")).toBe("accepted");
    expect(button("undo", ACME).disabled).toBe(false);
    // The other program's proposal is untouched and still waits.
    expect(card(SECOND).getAttribute("data-state")).toBe("proposed");
    expect(button("accept", SECOND).disabled).toBe(false);
    expect(button("reject", SECOND).disabled).toBe(false);
    expect(within(card(SECOND)).queryByTestId("proposal-history")).toBeNull();
    expect(planChanged).toBe(1);
  });

  it("decides nothing in a closed assessment: the reason shows, and every button of every proposal is off", async () => {
    const view = advisoriesClosed;
    const fetchMock = await open(view, {}, { readOnly: true });
    expect(screen.getByTestId("advisories-waiting-reason").textContent).toBe(view.waiting.blocked_reason);
    // A proposal nobody decided: Accept and Reject are off, with the closed sentence on each...
    await openRow(ZERO);
    for (const name of ["accept", "reject"] as const) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBe(CLOSED_SENTENCE);
      fireEvent.click(button(name));
    }
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    // ...and the backend's reason under them, said once for the two.
    expect(within(card()).getByTestId("proposal-blocked").textContent).toBe(CLOSED_REASON);
    // An accepted one: Undo is off.
    const inPanel = await openRow(BLANK);
    expect(button("undo").disabled).toBe(true);
    expect(within(card()).getByTestId("proposal-blocked").textContent).toBe(CLOSED_REASON);
    fireEvent.click(button("undo"));
    expect(posts(fetchMock)).toEqual([]);
    expect(planChanged).toBe(0);
    // Looking is still allowed: the result, the decisions on record and the links.
    expect(inPanel.getByTestId("advisory-here-result").textContent).toBe(view.rows[0]!.result.label);
    expect(within(card()).getByTestId("proposal-decided").textContent).toBe(
      view.rows[0]!.panel.here.rows[0]!.proposal!.decided_line,
    );
    expect(inPanel.getByRole("link", { name: "See the evidence" }).getAttribute("href")).toBe(
      "#/a/101/evidence?item=test-6",
    );
    openFacts();
    expect(within(screen.getByTestId("advisories-packs-line")).getByRole("link").getAttribute("href")).toBe(
      "#/settings?section=test-packs",
    );
  });

  it("is off in a closed assessment by the page's own rule too, with the closed sentence", async () => {
    // Even if a view said a proposal could be decided: the page is read-only once the assessment is closed.
    const fetchMock = await open(advisoriesTwoPacks, {}, { readOnly: true });
    await openRow(ZERO);
    expect(zeroProposal.buttons.every((b) => b.can)).toBe(true);
    for (const name of ["accept", "reject"] as const) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBe(CLOSED_SENTENCE);
      fireEvent.click(button(name));
    }
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
    // Looking is still allowed: rows open, links work.
    await openRow(BLANK);
    openFacts();
    expect(within(screen.getByTestId("advisories-packs-line")).getByRole("link").getAttribute("href")).toBe(
      "#/settings?section=test-packs",
    );
  });

  it("decides nothing when Otto is not installed: the backend turns every button off and says why, calmly", async () => {
    const view = advisoriesOttoMissing;
    const fetchMock = await open(view);
    // Why Otto is missing is said once, in the Otto line: a calm notice, not an error.
    const notice = screen.getByTestId("advisories-otto-line");
    expect(notice.textContent).toBe(view.otto.line);
    expect(view.otto.line).toBe(NOT_INSTALLED_LINE);
    expect(notice.getAttribute("data-installed")).toBe("false");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(notice.className).not.toMatch(/amber/);
    // The waiting block says, in a short line of its own, that nothing can be decided.
    expect(screen.getByTestId("advisories-waiting-reason").textContent).toBe(view.waiting.blocked_reason);
    expect(view.waiting.blocked_reason).not.toBe(view.otto.line);
    expect(waiting().getAttribute("data-count")).toBe("1");

    // The page is not read-only here: the buttons are off because the view says so (a decision could not be recorded).
    await openRow(ZERO);
    for (const name of ["accept", "reject"] as const) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBeNull();
      fireEvent.click(button(name));
    }
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    expect(within(card()).getByTestId("proposal-blocked").textContent).toBe(NO_OTTO_REASON);
    expect(posts(fetchMock)).toEqual([]);
    expect(screen.queryByRole("alert")).toBeNull();

    // What is already here stays: the result of the check that ran, in the reviewer's words, and who accepted it.
    expect(chipOf(BLANK, "advisory-result").textContent).toBe(view.rows[0]!.result.label);
    const inPanel = await openRow(BLANK);
    expect(inPanel.getByTestId("advisory-here-result").textContent).toBe(
      view.rows[0]!.panel.here.rows[0]!.result!.label,
    );
    expect(button("undo").disabled).toBe(true);
    expect(within(card()).getByTestId("proposal-blocked").textContent).toBe(NO_OTTO_REASON);
    expect(within(card()).getAllByTestId("proposal-decision")).toHaveLength(1);
    // The assessment's Otto ledger can't be read without the harness: only the pack's own entries are listed.
    expect(inPanel.getAllByTestId("advisory-ledger")).toHaveLength(1);
    expect(inPanel.getByTestId("proof-part-records").contains(inPanel.getByTestId("advisory-ledger"))).toBe(true);
    fireEvent.click(button("undo"));
    expect(posts(fetchMock)).toEqual([]);
    expect(planChanged).toBe(0);
  });
});

describe("Advisories, the names the end-to-end walk looks for", () => {
  const present = (ids: string[], root: HTMLElement = document.body) =>
    ids.filter((id) => within(root).queryAllByTestId(id).length > 0);
  // The bulk "Add new checks" button is gone: each proposal is decided by itself.
  const GONE = ["advisories-add", "add-new-checks", "add-new-checks-reason", "add-new-checks-note"];

  it("has every test id of the page and of a decided check's panel, and the panel holds its own parts", async () => {
    await open(advisoriesClosed, {}, { item: BLANK });
    await screen.findByTestId("advisory-related");
    // Everything of the page, the panel too, is inside the page's root.
    const onPage = [
      "advisories-standing",
      "advisories-packs-line",
      "advisories-answers-line",
      "advisories-otto-line",
      "advisories-waiting",
      "advisories-waiting-line",
      "advisories-waiting-reason",
      "advisories-waiting-note",
      "advisories-search",
      "advisories-filter-test",
      "advisories-filter-decision",
      "advisories-filter-result",
      "advisories-table",
      "advisory-row",
      "advisory-test",
      "advisory-proposal",
      "advisory-result",
      "advisory-panel",
    ];
    expect(present(onPage, screen.getByTestId("advisories-page"))).toEqual(onPage);
    expect(present(GONE)).toEqual([]);
    expect(waiting().getAttribute("data-count")).toBe(String(advisoriesClosed.waiting.count));
    expect(screen.getAllByTestId("advisory-row").map((r) => r.getAttribute("data-advisory"))).toEqual(
      advisoriesClosed.rows.map((r) => r.id),
    );
    for (const row of screen.getAllByTestId("advisory-row"))
      expect(present(["advisory-test", "advisory-proposal", "advisory-result"], row)).toHaveLength(3);
    const inPanel = [
      "advisory-sentence",
      "advisory-publisher",
      "advisory-sources",
      "advisory-affected",
      "advisory-test-block",
      "advisory-test-reason",
      "advisory-here",
      "advisory-here-note",
      "advisory-here-row",
      "otto-proposal",
      "proposal-label",
      "proposal-status",
      "proposal-why",
      "proposal-decided",
      "proposal-effect",
      "proposal-undo",
      "proposal-blocked",
      "proposal-history",
      "proposal-decision",
      "advisory-here-result",
      "open-in-checks",
      "see-the-evidence",
      "advisory-proof-fold",
      "proof-fold-toggle",
      "proof-fold-name",
      "proof-fold-inside",
      "proof-fold-body",
      "proof-part-test",
      "advisory-test-details",
      "proof-part-trial",
      "advisory-trial",
      "proof-part-records",
      "advisory-ledger",
      "advisory-claude",
      "advisory-fix",
      "advisory-fix-label",
      "advisory-related",
    ];
    expect(present(inPanel, panel())).toEqual(inPanel);
    expect(panel().getAttribute("data-advisory")).toBe(BLANK);
    // A program's row and its proposal say what they are about.
    expect(hereRow().getAttribute("data-program")).toBe(ACME);
    expect(card().getAttribute("data-proposal")).toBe(blankProposal.id);
    expect(card().getAttribute("data-kind")).toBe("check");
    expect(card().getAttribute("data-state")).toBe("accepted");
    // Each ledger is its own folded list: the decisions on the proposal and the check's in this assessment (with the
    // check), then the test's (in the fold).
    const here = blankFailed.panel.here.rows[0]!;
    const ledgers = within(panel()).getAllByTestId("advisory-ledger");
    expect(ledgers.map((d) => d.tagName)).toEqual(["DETAILS", "DETAILS", "DETAILS"]);
    expect(ledgers.map((d) => text(d.querySelector("summary")))).toEqual(
      [here.proposal!.history.ledger!, here.ledger!, blankFailed.panel.test!.ledger].map(
        (l) => `${l.title} (${l.count})`,
      ),
    );
    for (const folded of ["advisory-sources", "advisory-claude", "proposal-history"])
      expect(within(panel()).getByTestId(folded).tagName, folded).toBe("DETAILS");
  });

  it("has the ids of a proposal nobody decided, of its Reject dialog, and of the cell's counts", async () => {
    await open(twoProposed, {}, { item: BLANK });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(BLANK));
    expect(present(["advisory-here-row", "otto-proposal"], panel())).toHaveLength(2);
    const proposed = [
      "proposal-label",
      "proposal-status",
      "proposal-why",
      "proposal-decided",
      "proposal-accept",
      "proposal-reject",
      "proposal-note",
    ];
    expect(present(proposed, card())).toEqual(proposed);
    expect(card().getAttribute("data-state")).toBe("proposed");
    expect(present(["advisory-proposal-box", "advisory-proposal-text"], rowOf(BLANK))).toHaveLength(2);
    fireEvent.click(button("reject"));
    const dialog = [
      "proposal-reject-dialog",
      "proposal-reject-reason",
      "proposal-reject-cancel",
      "proposal-reject-confirm",
    ];
    expect(present(dialog)).toEqual(dialog);
    expect(screen.getByTestId("proposal-reject-dialog").getAttribute("role")).toBe("dialog");
    expect(present(GONE)).toEqual([]);
  });

  it("has the ids of a row without a test and of a page with no advisory", async () => {
    await open(advisoriesTwoPacks, {}, { item: STOPS });
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(STOPS));
    expect(
      present(
        [
          "advisory-no-test",
          "advisory-ledger",
          "advisory-here",
          "advisory-here-empty",
          "advisory-fix",
          "advisory-claude",
        ],
        panel(),
      ),
    ).toHaveLength(6);
    cleanup();
    await open(advisoriesNoPack);
    expect(
      present([
        "advisories-empty",
        "advisories-table",
        "advisories-waiting",
        "advisories-waiting-line",
        "advisories-waiting-note",
      ]),
    ).toHaveLength(5);
    expect(waiting().getAttribute("data-count")).toBe("0");
    expect(present(GONE)).toEqual([]);
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
    expect(names.slice(names.indexOf("Verify"), names.indexOf("Checks") + 1)).toEqual([
      "Verify",
      "Advisories",
      "Checks",
    ]);
    fireEvent.click(link);
    await screen.findByTestId("advisories-standing");
    expect(window.location.hash).toBe("#/a/101/advisories");
    expect(nav().getByRole("link", { name: "Advisories" }).getAttribute("aria-current")).toBe("page");
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getByText("Advisories")
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(rows()).toHaveLength(4);
  });

  it("opens the panel of the advisory the address names", async () => {
    go(`#/a/101/advisories?item=${LOOSE}`);
    mockApi(appRoutes());
    render(<App />);
    await waitFor(() => expect(panel().getAttribute("data-advisory")).toBe(LOOSE));
    expect(within(panel()).getByRole("heading", { level: 2, name: named(looseNotOffered.name) })).not.toBeNull();
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
      openFacts();
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

  it("is read-only in a closed assessment: the banner shows, the page says nothing more can be decided, and Accept is off with the closed sentence", async () => {
    go("#/a/100/advisories");
    const fetchMock = mockApi(
      appRoutes({ "GET /api/assessments/100": { body: closedAssessment }, [ADVISORIES]: { body: advisoriesClosed } }),
    );
    render(<App />);
    await screen.findByTestId("advisories-standing");
    expect(screen.getByTestId("closed-banner")).not.toBeNull();
    expect(screen.getByTestId("advisories-waiting-reason").textContent).toBe(advisoriesClosed.waiting.blocked_reason);
    expect(text(screen.getByTestId("advisories-packs-line"))).toBe(advisoriesClosed.packs_line);
    await openRow(ZERO);
    for (const name of ["accept", "reject"] as const) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBe(CLOSED_SENTENCE);
      fireEvent.click(button(name));
    }
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
  });

  it("has no Guided demo bar, and after Accept the app reads the test plan again", async () => {
    window.localStorage.setItem("evidence-lab-guided", "on");
    go("#/a/101/advisories");
    const accept = decide(blankProposal.id, "accept");
    const fetchMock = mockApi(
      appRoutes(
        deciding(advisoriesNotAdded, [{ route: accept, answer: blankProposalAccepted, then: advisoriesAddedNotRun }]),
      ),
    );
    render(<App />);
    await screen.findByTestId("advisories-standing");
    expect(screen.queryByTestId("guided-bar")).toBeNull();
    const plans = () => calls(fetchMock).filter((c) => c === "GET /api/import/7/plan").length;
    await openRow(BLANK);
    const before = plans();
    fireEvent.click(button("accept"));
    await waitFor(() => expect(plans()).toBe(before + 1));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe("Added"));
    expect(posts(fetchMock)).toEqual([accept]);
    expect(reads(fetchMock)).toBe(2);
  });

  it("reads the test plan again after a reject too: the app is told of every decision", async () => {
    go("#/a/101/advisories");
    const reject = decide(blankProposal.id, "reject");
    const fetchMock = mockApi(
      appRoutes(
        deciding(advisoriesNotAdded, [{ route: reject, answer: blankProposalRejected, then: advisoriesRejected }]),
      ),
    );
    render(<App />);
    await screen.findByTestId("advisories-standing");
    const plans = () => calls(fetchMock).filter((c) => c === "GET /api/import/7/plan").length;
    await openRow(BLANK);
    const before = plans();
    fireEvent.click(button("reject"));
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(chipOf(BLANK, "advisory-proposal").textContent).toBe(blankRejected.proposal.label));
    await waitFor(() => expect(plans()).toBe(before + 1));
    expect(posts(fetchMock)).toEqual([reject]);
    expect(reads(fetchMock)).toBe(2);
  });
});

// A check on the fixtures the tests above are built from: the accepted proposal of `proposalFixtures` and the page's own
// agree on the decision they describe, so a test that mixes them compares like with like.
describe("Advisories, the fixtures", () => {
  it("builds each state of the check's proposal from the shared proposal fixtures", () => {
    expect(blankProposal.status).toEqual(proposal().status);
    expect(blankProposalAccepted.status).toEqual(acceptedProposal().status);
    expect(blankProposalAccepted.decided_line).toBe(acceptedProposal().decided_line);
    expect(blankProposalRejected.status).toEqual(rejectedProposal("Not this quarter").status);
    // One proposal throughout: every state carries the same id, and it is the one the decision route names.
    for (const state of [blankProposalAccepted, blankProposalRejected, blankProposalUndone, blankProposalReconsidered])
      expect(state.id).toBe(blankProposal.id);
    expect(blankProposal.id).not.toBe(zeroProposal.id);
    expect(blankProposal.id).not.toBe(secondProposal.id);
  });
});

// The 5c fixes: an advisory whose first arrival came with the most recently installed test pack carries the tag "New"
// beside its name, in the table and in its panel's title. The pack is named on hover and to a screen reader.
describe("Advisories, the New tag", () => {
  const tagIn = (el: HTMLElement) => within(el).queryByTestId("advisory-new");
  const row = (id: string) =>
    screen.getAllByTestId("advisory-row").find((r) => r.getAttribute("data-advisory") === id)!;

  async function show(view: AdvisoriesView, item: string | null = null) {
    mockApi({
      "GET /api/plans/1/advisories": { body: view },
      "GET /api/plans/1/related?key=advisory%3ACVE-2024-42460": { body: { key: "", related: [] } },
    });
    render(
      <LinkProvider assessmentId={101} planId={1}>
        <AdvisoriesScreen planId={1} openItem={item} />
      </LinkProvider>,
    );
    await screen.findAllByTestId("advisory-row");
  }

  it("with one pack installed, every advisory is new, and the tag names that pack", async () => {
    await show(advisoriesNotAdded);
    for (const shown of advisoriesNotAdded.rows) {
      const tag = tagIn(row(shown.id))!;
      expect(tag, shown.id).not.toBeNull();
      expect(tag.getAttribute("title")).toBe("Arrived with test pack 2026.11.1");
      // what is seen is the one word; a screen reader is told which pack
      expect(tag.querySelector("[aria-hidden='true']")!.textContent).toBe("New");
      expect(tag.querySelector(".sr-only")!.textContent).toBe("New: arrived with test pack 2026.11.1");
    }
  });

  it("with a second pack installed, only the advisories it brought are new", async () => {
    await show(advisoriesTwoPacks);
    const tagged = advisoriesTwoPacks.rows.filter((r) => tagIn(row(r.id)) !== null).map((r) => r.id);
    expect(tagged).toEqual(advisoriesTwoPacks.rows.filter((r) => r.pack === "2026.11.2").map((r) => r.id));
    expect(tagged).toHaveLength(2);
    for (const id of tagged) expect(tagIn(row(id))!.getAttribute("title")).toBe("Arrived with test pack 2026.11.2");
    // an advisory of the first pack is listed as before, with no tag
    expect(tagIn(row(advisoriesTwoPacks.rows[0]!.id))).toBeNull();
  });

  it("the open advisory's panel carries the tag in its title too", async () => {
    await show(advisoriesTwoPacks, zeroNotAdded.id);
    const heading = within(await screen.findByTestId("detail-panel")).getByRole("heading", { level: 2 });
    expect(heading.firstChild!.textContent).toBe(zeroNotAdded.name);
    const tag = tagIn(heading)!;
    expect(tag.getAttribute("title")).toBe("Arrived with test pack 2026.11.2");
    expect(text(heading)).toBe(`${zeroNotAdded.name} NewNew: arrived with test pack 2026.11.2`);
  });

  it("an older advisory's panel has no tag", async () => {
    await show(advisoriesTwoPacks, advisoriesTwoPacks.rows[0]!.id);
    const heading = within(await screen.findByTestId("detail-panel")).getByRole("heading", { level: 2 });
    expect(tagIn(heading)).toBeNull();
    expect(text(heading)).toBe(advisoriesTwoPacks.rows[0]!.name);
  });
});

// 22 November 2026 (Kevin: "so every result is true"): an advisory check's result is a run of a copy of the program on
// this computer, so it is tagged Proven in the lab, beside the reviewer's own word, in the table and in the panel. A check
// that has not run, or no check, has no tag.
describe("Advisories, where a check's result came from", () => {
  it("tags the result here beside its word, once per row, and says in the panel what that means for this program", async () => {
    const fetchMock = await open(advisoriesFailed);
    const cell = chipOf("CVE-2022-21449", "advisory-result").parentElement!;
    expect(
      within(cell)
        .getAllByTestId("source-tag")
        .map((t) => [t.textContent, t.getAttribute("data-source")]),
    ).toEqual([["Proven in the lab", "lab"]]);
    // a row with no result yet has no tag
    for (const row of rows().filter((r) => r.getAttribute("data-advisory") !== "CVE-2022-21449"))
      expect(within(row).queryAllByTestId("source-tag")).toEqual([]);
    await openRow("CVE-2022-21449");
    const line = within(hereRow()).getByTestId("source-line");
    expect(within(line).getByTestId("source-tag").textContent).toBe("Proven in the lab");
    expect(within(line).getByTestId("source-note").textContent).toBe(
      "Run on a copy of acme-sign 1.4.2 on this computer, in demo mode (a plain process on this computer, not isolated). Your live system was not touched.",
    );
    expect(posts(fetchMock)).toEqual([]);
  });
});
