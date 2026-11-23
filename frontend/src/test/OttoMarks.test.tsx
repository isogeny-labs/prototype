import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { CheckDetail, CheckRow, ChecksView, FixLine, PlanView, TestCard } from "../api";
import { ChecksScreen } from "../components/ChecksScreen";
import { ResultDetail } from "../components/lab/ResultDetail";
import { LinkProvider } from "../components/related";
import { TestsScreen } from "../components/TestsScreen";
import {
  checkGroups,
  checksView,
  encryptionParts,
  newestBlock,
  planRows,
  retestDetail,
  retestRow,
} from "./checksFixtures";
import { hereNotYet, publicPassed } from "./fixProposalFixtures";
import { calls, cards, fixLines, mockApi, plan, text, vectorsResult } from "./fixtures";

/** Phase 5c, second part: the marks Otto's work carries outside its own pages. On Evidence, the fix line of a library's
 * fix says the same two proof rows as Fixes. On Checks and on the test plan's cards, an advisory check that came from an
 * accepted proposal says "From Otto", with the way to its advisory. Every word is the view's. */

const ADVISORY = "CVE-2022-21449";
const TITLE = "Advisory check: Missing ECDSA signature range check (CVE-2022-21449)";
const FROM_OTTO = {
  label: "From Otto",
  advisory: `Advisory ${ADVISORY}`,
  link: { page: "advisories", item: ADVISORY },
};
const REMOVE_BLOCKED =
  "This check came from an accepted proposal. Until it has run, Undo on Advisories takes it out of the test plan. Once it has run, it stays.";

describe("Evidence, the fix line of a library's fix from Otto", () => {
  const line: FixLine = {
    fix_id: "fix-advisory-cases-23",
    lead: "From Otto:",
    rest: "update elliptic to 6.5.7",
    look: "dashed",
    busy: false,
    button: "View in Fixes",
    rows: [publicPassed.line, hereNotYet.line],
  };

  function open(fixLine: FixLine) {
    const viewed: string[] = [];
    render(
      <ResultDetail
        result={{ ...vectorsResult, fix_line: fixLine }}
        busy={false}
        onViewFix={(id) => viewed.push(id)}
      />,
    );
    return viewed;
  }

  it("draws the fix's two proof rows under the line, word for word, and still opens the fix", () => {
    const viewed = open(line);
    const shown = within(screen.getByTestId("fix-line"));
    expect(text(screen.getByTestId("fix-line"))).toContain("From Otto: update elliptic to 6.5.7");
    expect(shown.getAllByTestId("fix-line-row").map((row) => row.textContent)).toEqual([
      "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
      "Proven in this assessment: Not yet. Update the library, then press Retest.",
    ]);
    expect(screen.getByTestId("fix-line").getAttribute("data-look")).toBe("dashed");
    fireEvent.click(shown.getByRole("button", { name: "View in Fixes" }));
    expect(viewed).toEqual(["fix-advisory-cases-23"]);
  });

  it("a fix line without rows is exactly as it was", () => {
    open(fixLines.text_only);
    // the words, the arrow and the button, and nothing after them
    expect(text(screen.getByTestId("fix-line"))).toBe("Text-only suggestion: a server setting→View in Fixes");
    expect(Array.from(screen.getByTestId("fix-line").children).map((el) => el.tagName)).toEqual([
      "P",
      "SPAN",
      "BUTTON",
    ]);
    expect(screen.queryByTestId("fix-line-rows")).toBeNull();
    expect(screen.queryAllByTestId("fix-line-row")).toHaveLength(0);
  });

  it("an empty list of rows draws none", () => {
    open({ ...line, rows: [] });
    expect(screen.queryByTestId("fix-line-rows")).toBeNull();
  });
});

describe("Checks, an advisory check that came from Otto", () => {
  const CHECKS = "GET /api/plans/1/checks";
  // The advisory check as the plan lists it (shown as its card), and its retest: a row in the block of the version that
  // retest ran on (the 5c fixes), beside the retest of a test that is not Otto's.
  const planCheck: CheckRow = {
    ...planRows[0]!,
    id: "test-6",
    name: TITLE,
    link: { page: "checks", item: "test-6" },
    evidence_link: { page: "evidence", item: "test-6" },
    from_otto: FROM_OTTO,
  };
  const retest: CheckRow = {
    ...retestRow,
    id: "retest-6-on-2",
    alias: "retest-6",
    mark: null,
    name: TITLE,
    link: { page: "evidence", item: "retest-6" },
    evidence_link: { page: "evidence", item: "retest-6" },
    from_otto: FROM_OTTO,
  };
  const plainRetest: CheckRow = newestBlock.rows[0]!;
  const view: ChecksView = {
    ...checksView,
    groups: checkGroups({
      encryption: [...planRows, planCheck, retestRow, { ...retest, id: "retest-6" }],
      parts: encryptionParts({ tests: 4, retests: [{ ...newestBlock, rows: [plainRetest, retest] }] }),
    }),
  };
  const detail = (check: CheckRow): CheckDetail => ({ ...retestDetail, check, runs: [], related: [] });

  function Harness({ item = null }: { item?: string | null }) {
    const [current, setCurrent] = useState<PlanView | null>(plan);
    return (
      <LinkProvider assessmentId={101} planId={1}>
        {/* (a retest's rows are on the Crypto tests tab; a link that names a check opens the tab it sits in) */}
        <ChecksScreen
          importId={7}
          plan={current}
          onPlan={setCurrent}
          openItem={item}
          group={item ? null : "encryption"}
        />
      </LinkProvider>
    );
  }

  async function open(item: string | null = null) {
    const fetchMock = mockApi({
      [CHECKS]: { body: view },
      "GET /api/import/7/plan": { body: plan },
      [`GET /api/plans/1/checks/${retest.id}`]: { body: detail(retest) },
      "GET /api/plans/1/checks/test-6": { body: detail(planCheck) },
      [`GET /api/plans/1/checks/${plainRetest.id}`]: { body: detail(plainRetest) },
    });
    render(<Harness item={item} />);
    await screen.findAllByTestId("group-section");
    return fetchMock;
  }

  const row = (id: string) => screen.getAllByTestId("check-row").find((r) => r.getAttribute("data-check") === id)!;

  it("its row carries the tag and the advisory as a link; a check that is not Otto's carries neither", async () => {
    const fetchMock = await open();
    const marked = within(row(retest.id));
    expect(marked.getByTestId("from-otto").textContent).toBe("From Otto");
    const link = marked.getByTestId("check-from-otto");
    expect(link.textContent).toBe(`Advisory ${ADVISORY}`);
    expect(link.getAttribute("href")).toBe(`#/a/101/advisories?item=${ADVISORY}`);
    expect(within(row(plainRetest.id)).queryByTestId("check-from-otto-mark")).toBeNull();
    // The link is a link: following it does not open the row's panel, and looking at the page started nothing.
    fireEvent.click(link);
    expect(screen.queryByTestId("check-panel")).toBeNull();
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
    expect(calls(fetchMock).some((c) => c.includes(`/checks/${retest.id}`))).toBe(false);
  });

  it("the open check's panel says the same, and beside it the compact table keeps the mark under the name", async () => {
    await open();
    fireEvent.click(row(retest.id));
    const panel = within(await screen.findByTestId("check-panel"));
    const line = within(panel.getByTestId("check-from-otto-line"));
    expect(line.getByTestId("from-otto").textContent).toBe("From Otto");
    expect(line.getByTestId("check-from-otto").textContent).toBe(`Advisory ${ADVISORY}`);
    expect(line.getByTestId("check-from-otto").getAttribute("href")).toBe(`#/a/101/advisories?item=${ADVISORY}`);
    await waitFor(() =>
      expect(screen.getAllByTestId("data-table").some((table) => table.getAttribute("data-compact") === "true")).toBe(
        true,
      ),
    );
    expect(within(row(retest.id)).getByTestId("check-from-otto").textContent).toBe(`Advisory ${ADVISORY}`);
  });

  it("the plan's own advisory check, opened from a link, says it is from Otto in its panel", async () => {
    await open("test-6");
    const panel = within(await screen.findByTestId("check-panel"));
    expect(screen.getByTestId("check-panel").getAttribute("data-check")).toBe("test-6");
    expect(panel.getByTestId("from-otto").textContent).toBe("From Otto");
    expect(panel.getByTestId("check-from-otto").getAttribute("href")).toBe(`#/a/101/advisories?item=${ADVISORY}`);
  });

  it("a check that is not Otto's has no such line in its panel", async () => {
    const fetchMock = await open();
    fireEvent.click(row(plainRetest.id));
    await screen.findByTestId("check-panel");
    await waitFor(() => expect(calls(fetchMock)).toContain(`GET /api/plans/1/checks/${plainRetest.id}`));
    expect(screen.getByTestId("check-panel").getAttribute("data-check")).toBe(plainRetest.id);
    expect(within(screen.getByTestId("check-panel")).queryByTestId("check-from-otto-line")).toBeNull();
  });
});

describe("The test plan's cards, an advisory check that came from Otto", () => {
  const ottoCard: TestCard = {
    ...cards[3]!,
    id: 21,
    kind: "advisory_cases",
    title: TITLE,
    origin: "added",
    can_remove: false,
    advisory: { label: `From advisory ${ADVISORY}`, link: { page: "advisories", item: ADVISORY } },
    from_otto: "From Otto",
    remove_blocked: REMOVE_BLOCKED,
  };

  function Harness() {
    const [current, setCurrent] = useState<PlanView | null>(null);
    return (
      <LinkProvider assessmentId={101} planId={1}>
        <TestsScreen importId={7} plan={current} onPlan={setCurrent} />
      </LinkProvider>
    );
  }

  async function open() {
    const fetchMock = mockApi({ "POST /api/import/7/plan": { body: { ...plan, tests: [...cards, ottoCard] } } });
    render(<Harness />);
    const shown = await screen.findAllByTestId("test-card");
    return { fetchMock, shown, card: shown.at(-1)! };
  }

  it("carries the tag From Otto beside the advisory it came from; no other card does", async () => {
    const { shown, card } = await open();
    const tags = screen.getAllByTestId("card-from-otto");
    expect(tags).toHaveLength(1);
    expect(card.contains(tags[0]!)).toBe(true);
    expect(tags[0]!.textContent).toBe("From Otto");
    // ... in the same line as the way to its advisory.
    const link = within(card).getByTestId("card-advisory");
    expect(link.parentElement).toBe(tags[0]!.parentElement);
    expect(link.getAttribute("href")).toBe(`#/a/101/advisories?item=${ADVISORY}`);
    expect(shown.slice(0, -1).every((other) => within(other).queryByTestId("card-from-otto") === null)).toBe(true);
  });

  it("has its remove switched off and says why, in the backend's words; pressing it sends nothing", async () => {
    const { fetchMock, shown, card } = await open();
    const remove = within(card).getByRole("button", { name: `Remove ${TITLE}` }) as HTMLButtonElement;
    expect(remove.disabled).toBe(true);
    expect(remove.getAttribute("title")).toBe(REMOVE_BLOCKED);
    expect(within(card).getByTestId("remove-blocked").textContent).toBe(REMOVE_BLOCKED);
    fireEvent.click(remove);
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
    // A card that can be removed is as it was: its own title, and no such line.
    const other = within(shown[0]!).getByRole("button", { name: `Remove ${cards[0]!.title}` }) as HTMLButtonElement;
    expect(other.disabled).toBe(false);
    expect(other.getAttribute("title")).toBe("Remove from the plan");
    expect(screen.getAllByTestId("remove-blocked")).toHaveLength(1);
  });
});
