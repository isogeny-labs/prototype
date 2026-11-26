import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Source } from "../api";
import { DataTable, GroupTabs, tabTotal, type Column } from "../components/layout";
import { SOURCE_PARTS, sourceParts } from "../components/sourceParts";
import { text } from "./fixtures";

// The design refactor (26 November 2026): a list of results is drawn in labelled parts, by what each row rests on, and
// a tab says how many rows it holds. Both only arrange and count what the page already has; neither decides anything.

const tag = (key: Source["key"], label: string, meaning: string): Source => ({ key, label, meaning, note: null });
const LIVE = tag("live", "Observed live", "Read from a system at an address in your file that you confirmed.");
const LAB = tag("lab", "Proven in the lab", "Run on a copy on this computer, never on your live system.");
const FILE = tag("file", "From your file", "It rests only on your file.");
const PUBLISHED = tag("published", "Published", "Said by the library's maker.");

interface Row {
  id: string;
  tag: Source | null;
}
const rows: Row[] = [
  { id: "vectors", tag: LAB },
  { id: "tls", tag: LIVE },
  { id: "not-run", tag: null },
  { id: "exam", tag: LAB },
  { id: "certificate", tag: LIVE },
  { id: "claim", tag: FILE },
  { id: "library", tag: PUBLISHED },
];
const columns: Column<Row>[] = [{ key: "id", header: "Test", render: (r) => r.id }];

function table(given: Row[]) {
  render(
    <DataTable
      label="Results"
      columns={columns}
      rows={given}
      rowKey={(r) => r.id}
      rowTestId="row"
      parts={(all) => sourceParts(all, (r) => r.tag)}
    />,
  );
  return screen.getAllByTestId("table-part");
}

describe("a table in parts", () => {
  it("draws every row once, under the heading of what it rests on, and keeps the rows' own order inside a part", () => {
    const parts = table(rows);
    expect(
      parts.map((p) => [
        p.getAttribute("data-part"),
        within(p).getByTestId("table-part-title").textContent,
        within(p)
          .getAllByTestId("row")
          .map((r) => r.getAttribute("data-key")),
      ]),
    ).toEqual([
      // The parts come in the order the rows do: the first row's part is first, so a list opens where it always did.
      ["lab", "On copies on this computer", ["vectors", "exam"]],
      ["live", "On your systems", ["tls", "certificate"]],
      ["file", "Only in your file", ["claim"]],
      ["published", "Said by the maker", ["library"]],
      // ...and the rows nothing was observed or proven for come last.
      ["none", "No result yet", ["not-run"]],
    ]);
    // A part is a heading, never a filter: nothing is left out.
    expect(screen.getAllByTestId("row")).toHaveLength(rows.length);
  });

  it("says each part's tag once, at its head, with the tag's own line and how many rows it holds", () => {
    const parts = table(rows);
    const lab = within(parts[0]!);
    expect(lab.getByTestId("table-part-tag").textContent).toBe(LAB.label);
    expect(lab.getByTestId("table-part-tag").getAttribute("data-source")).toBe("lab");
    expect(lab.getByTestId("table-part-meaning").textContent).toBe(LAB.meaning);
    expect(lab.getByTestId("table-part-count").textContent).toBe("2");
    // The heading spans the table and is the header of its group of rows.
    const head = lab.getByTestId("table-part-head");
    expect(head.tagName).toBe("TH");
    expect(head.getAttribute("scope")).toBe("rowgroup");
    expect(parts[0]!.tagName).toBe("TBODY");
  });

  it("puts no tag at the head of the rows with no result yet", () => {
    const parts = table(rows);
    const none = within(parts[parts.length - 1]!);
    expect(none.queryByTestId("table-part-tag")).toBeNull();
    expect(none.queryByTestId("table-part-meaning")).toBeNull();
    expect(text(none.getByTestId("table-part-head"))).toBe("No result yet1");
  });

  it("draws no empty part, and a table without rows says so as before", () => {
    expect(table(rows.filter((r) => r.tag?.key === "live")).map((p) => p.getAttribute("data-part"))).toEqual(["live"]);
    render(
      <DataTable
        label="Empty"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        parts={(all) => sourceParts(all, (r) => r.tag)}
        empty="Nothing here."
      />,
    );
    expect(within(screen.getByRole("table", { name: "Empty" })).queryByTestId("table-part")).toBeNull();
    expect(screen.getByText("Nothing here.")).not.toBeNull();
  });

  it("has a part for each of the four tags and one for no tag, and no other", () => {
    expect(SOURCE_PARTS.map((p) => p.key)).toEqual(["live", "lab", "published", "file", "none"]);
  });
});

describe("the count on a tab", () => {
  it("counts every row, and as findings only the rows whose own result is a failure, under their own word", () => {
    expect(tabTotal([])).toEqual({ n: 0, findings: null });
    expect(
      tabTotal([
        { label: "Passed", tone: "pass" },
        null,
        { label: "Failed", tone: "fail" },
        { label: "Failed", tone: "fail" },
      ]),
    ).toEqual({ n: 4, findings: { n: 2, word: "failed" } });
    expect(tabTotal([{ label: "False", tone: "fail" }])).toEqual({ n: 1, findings: { n: 1, word: "false" } });
    // Two different words are not added up under one of them.
    expect(
      tabTotal([
        { label: "False", tone: "fail" },
        { label: "Failed", tone: "fail" },
      ]),
    ).toEqual({ n: 2, findings: { n: 2, word: "findings" } });
    // A warning or a row with no result is no finding.
    expect(
      tabTotal([
        { label: "Couldn't check", tone: "warn" },
        { label: "Measured", tone: "neutral" },
      ]).findings,
    ).toBeNull();
  });

  it("shows the count beside the tab's name without changing the name, and the matching rows while a search is on", () => {
    const groups = [
      { key: "verification", label: "Verification" },
      { key: "encryption", label: "Crypto tests" },
    ];
    const totals = { verification: { n: 3, findings: { n: 1, word: "false" } }, encryption: { n: 6, findings: null } };
    const { rerender } = render(
      <GroupTabs groups={groups} active="verification" onChoose={() => undefined} idBase="t" totals={totals} />,
    );
    const first = screen.getByRole("tab", { name: "Verification" });
    expect(within(first).getByTestId("group-tab-total").textContent).toBe("3");
    expect(within(first).getByTestId("group-tab-findings").textContent).toBe("✕ 1 false");
    expect(document.getElementById(first.getAttribute("aria-describedby")!)!.textContent).toBe("3 items, 1 false");
    const second = screen.getByRole("tab", { name: "Crypto tests" });
    expect(within(second).queryByTestId("group-tab-findings")).toBeNull();
    expect(document.getElementById(second.getAttribute("aria-describedby")!)!.textContent).toBe("6 items");

    rerender(
      <GroupTabs
        groups={groups}
        active="verification"
        onChoose={() => undefined}
        idBase="t"
        totals={totals}
        matches={{ verification: 1, encryption: 0 }}
      />,
    );
    // While a search or a filter is on, the number is the rows that match, as before.
    expect(screen.queryByTestId("group-tab-total")).toBeNull();
    expect(screen.queryByTestId("group-tab-findings")).toBeNull();
    expect(screen.getAllByTestId("group-tab-matches").map((n) => n.textContent)).toEqual(["1", "0"]);
  });
});
