import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { DataTable, DetailPanel, GroupSection, PANEL_MAX, PANEL_MIN, TableWithPanel, type Column } from "../components/layout";

describe("DetailPanel", () => {
  it("is not there while closed", () => {
    render(
      <DetailPanel open={false} title="Old TLS versions" onClose={() => undefined}>
        <p>Detail text</p>
      </DetailPanel>,
    );
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expect(screen.queryByText("Detail text")).toBeNull();
  });

  it("opens with its title, subtitle and content, named by its title", () => {
    render(
      <DetailPanel open title="Old TLS versions" subtitle="localhost:8443" onClose={() => undefined}>
        <p>Detail text</p>
      </DetailPanel>,
    );
    const panel = screen.getByRole("complementary", { name: "Old TLS versions" });
    expect(within(panel).getByRole("heading", { level: 2, name: "Old TLS versions" })).not.toBeNull();
    expect(within(panel).getByText("localhost:8443")).not.toBeNull();
    expect(within(panel).getByText("Detail text")).not.toBeNull();
    expect(panel.getAttribute("data-testid")).toBe("detail-panel");
  });

  it("calls onClose from the close button", () => {
    const onClose = vi.fn();
    render(
      <DetailPanel open title="T" onClose={onClose}>
        x
      </DetailPanel>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on Escape, and only on Escape", () => {
    const onClose = vi.fn();
    render(
      <DetailPanel open title="T" onClose={onClose}>
        x
      </DetailPanel>,
    );
    fireEvent.keyDown(document, { key: "a" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close on Escape while the person types in a field (a reason, a date), so the draft is kept", () => {
    const onClose = vi.fn();
    render(
      <DetailPanel open title="T" onClose={onClose}>
        <label>
          Your reason
          <textarea />
        </label>
        <input aria-label="Review date" />
      </DetailPanel>,
    );
    fireEvent.keyDown(screen.getByLabelText("Your reason"), { key: "Escape" });
    fireEvent.keyDown(screen.getByLabelText("Review date"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stops listening for Escape once it is closed", () => {
    const onClose = vi.fn();
    const view = render(
      <DetailPanel open title="T" onClose={onClose}>
        x
      </DetailPanel>,
    );
    view.rerender(
      <DetailPanel open={false} title="T" onClose={onClose}>
        x
      </DetailPanel>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("moves focus into the panel when it opens, and back to where it was when it closes", () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open it</button>
          <DetailPanel open={open} title="T" onClose={() => setOpen(false)}>
            <p>x</p>
          </DetailPanel>
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open it" });
    opener.focus();
    fireEvent.click(opener);
    const panel = screen.getByTestId("detail-panel");
    expect(panel.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});

interface Row {
  id: string;
  name: string;
  state: string;
}
const ROWS: Row[] = [
  { id: "a", name: "Old TLS versions", state: "Failed" },
  { id: "b", name: "Certificate strength", state: "Passed" },
];
const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Test", render: (r) => r.name },
  { key: "state", header: "State", render: (r) => r.state },
];

function Table() {
  const [open, setOpen] = useState<Row | null>(null);
  return (
    <>
      <DataTable label="Tests" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} rowTestId="row" selectedKey={open?.id ?? null} onRowClick={setOpen} />
      <DetailPanel open={open !== null} title={open?.name ?? ""} onClose={() => setOpen(null)}>
        <p>Detail of {open?.name}</p>
      </DetailPanel>
    </>
  );
}

describe("DataTable rows opening a DetailPanel", () => {
  it("shows a header row and one row per item", () => {
    render(<Table />);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Test", "State"]);
    expect(screen.getAllByTestId("row")).toHaveLength(2);
  });

  it("opens the panel with a click, and marks the row as selected", () => {
    render(<Table />);
    fireEvent.click(screen.getAllByTestId("row")[1]!);
    expect(screen.getByRole("heading", { level: 2, name: "Certificate strength" })).not.toBeNull();
    expect(screen.getByText("Detail of Certificate strength")).not.toBeNull();
    expect(screen.getAllByTestId("row").map((r) => r.getAttribute("aria-selected"))).toEqual(["false", "true"]);
  });

  it("opens the panel with Enter", () => {
    render(<Table />);
    fireEvent.keyDown(screen.getAllByTestId("row")[0]!, { key: "Enter" });
    expect(screen.getByText("Detail of Old TLS versions")).not.toBeNull();
  });

  it("opens the panel with Space", () => {
    render(<Table />);
    fireEvent.keyDown(screen.getAllByTestId("row")[0]!, { key: " " });
    expect(screen.getByText("Detail of Old TLS versions")).not.toBeNull();
  });

  it("makes every row reachable with the keyboard, and leaves other keys alone", () => {
    render(<Table />);
    for (const row of screen.getAllByTestId("row")) expect(row.getAttribute("tabindex")).toBe("0");
    fireEvent.keyDown(screen.getAllByTestId("row")[0]!, { key: "a" });
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("closes with Escape and unselects the row", () => {
    render(<Table />);
    fireEvent.click(screen.getAllByTestId("row")[0]!);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expect(screen.getAllByTestId("row").map((r) => r.getAttribute("aria-selected"))).toEqual(["false", "false"]);
  });

  it("does not make rows clickable when nothing opens from them", () => {
    render(<DataTable label="Plain" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} rowTestId="row" />);
    expect(screen.getAllByTestId("row")[0]!.getAttribute("tabindex")).toBeNull();
  });

  it("says so when there is nothing to show", () => {
    render(<DataTable label="Plain" columns={COLUMNS} rows={[]} rowKey={(r: Row) => r.id} empty="No test matches." />);
    expect(screen.getByText("No test matches.")).not.toBeNull();
  });
});

// ---- Phase 5b: the compact table beside an open panel, the panel's width, and the work-group headings ----

const FULL: Column<Row>[] = [
  { key: "name", header: "Test", render: (r) => r.name },
  { key: "state", header: "State", render: (r) => r.state },
  { key: "note", header: "Came from", render: () => "Test plan" },
];
const COMPACT: Column<Row>[] = [FULL[0]!, FULL[1]!];

function Paired() {
  const [open, setOpen] = useState<Row | null>(null);
  return (
    <TableWithPanel
      panelOpen={open !== null}
      table={
        <DataTable
          label="Tests"
          columns={FULL}
          compactColumns={COMPACT}
          rows={ROWS}
          rowKey={(r) => r.id}
          rowTestId="row"
          selectedKey={open?.id ?? null}
          onRowClick={setOpen}
        />
      }
      panel={
        <DetailPanel open={open !== null} title={open?.name ?? ""} onClose={() => setOpen(null)}>
          <p>Detail of {open?.name}</p>
        </DetailPanel>
      }
    />
  );
}

describe("phase 5b: a table beside its panel", () => {
  const headers = () => screen.getAllByRole("columnheader").map((h) => h.textContent);

  it("switches to its compact columns while the panel is open, and back when it closes", () => {
    window.localStorage.clear();
    render(<Paired />);
    expect(headers()).toEqual(["Test", "State", "Came from"]);
    expect(screen.getByTestId("data-table").getAttribute("data-compact")).toBeNull();
    fireEvent.click(screen.getAllByTestId("row")[0]!);
    expect(headers()).toEqual(["Test", "State"]);
    expect(screen.getByTestId("data-table").getAttribute("data-compact")).toBe("true");
    // The open row stays the selected one in the compact form.
    expect(screen.getAllByTestId("row")[0]!.getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(headers()).toEqual(["Test", "State", "Came from"]);
  });

  it("makes the panel wider and narrower within its limits, and remembers the width for every page", () => {
    window.localStorage.clear();
    const first = render(<Paired />);
    fireEvent.click(screen.getAllByTestId("row")[0]!);
    const width = () => Number(screen.getByTestId("panel-edge").getAttribute("aria-valuenow"));
    expect(width()).toBe(440);
    fireEvent.click(screen.getByRole("button", { name: "Wider" }));
    expect(width()).toBe(520);
    expect(screen.getByTestId("table-with-panel").style.getPropertyValue("--panel-w")).toBe("520px");
    // The arrow keys on the edge move it too.
    fireEvent.keyDown(screen.getByTestId("panel-edge"), { key: "ArrowLeft" });
    expect(width()).toBe(560);
    fireEvent.keyDown(screen.getByTestId("panel-edge"), { key: "ArrowRight" });
    expect(width()).toBe(520);
    for (let i = 0; i < 10; i += 1) fireEvent.click(screen.getByRole("button", { name: "Narrower" }));
    expect(width()).toBe(PANEL_MIN);
    expect((screen.getByRole("button", { name: "Narrower" }) as HTMLButtonElement).disabled).toBe(true);
    for (let i = 0; i < 10; i += 1) fireEvent.click(screen.getByRole("button", { name: "Wider" }));
    expect(width()).toBe(PANEL_MAX);
    expect((screen.getByRole("button", { name: "Wider" }) as HTMLButtonElement).disabled).toBe(true);
    first.unmount();

    // Another page (another table with a panel) opens at the width chosen last.
    render(<Paired />);
    fireEvent.click(screen.getAllByTestId("row")[1]!);
    expect(width()).toBe(PANEL_MAX);
  });
});

describe("phase 5b: a work group's heading", () => {
  function Group({ empty = false }: { empty?: boolean }) {
    const [open, setOpen] = useState(true);
    return (
      <GroupSection
        group={{ key: "migration", label: "Migration" }}
        counts={{ open: 2, in_progress: 1, done: 4 }}
        emptyText={empty ? "Nothing measured yet. Measure status is on Migration." : null}
        startedOn={<a href="#/a/1/migration/systems">Started on Migration</a>}
        also={<span>Also relates to this group: a test</span>}
        open={open}
        onToggle={() => setOpen((o) => !o)}
      >
        <p>The rows</p>
      </GroupSection>
    );
  }

  it("shows its three counts, links to where its checks start, folds its rows, and keeps the foot line with them", () => {
    render(<Group />);
    const section = screen.getByRole("region", { name: "Migration" });
    expect(within(section).getByTestId("group-counts").textContent).toBe("Open 2 · In progress 1 · Done 4");
    expect(within(section).getByRole("link", { name: "Started on Migration" })).not.toBeNull();
    expect(within(section).getByText("The rows")).not.toBeNull();
    expect(within(section).getByTestId("group-also").textContent).toBe("Also relates to this group: a test");
    const fold = within(section).getByRole("button", { name: "Migration" });
    fireEvent.click(fold);
    expect(fold.getAttribute("aria-expanded")).toBe("false");
    expect(within(section).queryByText("The rows")).toBeNull();
    // Folded, the heading and its counts stay.
    expect(within(section).getByTestId("group-counts")).not.toBeNull();
  });

  it("stays when it is empty and says why, instead of its rows", () => {
    render(<Group empty />);
    const section = screen.getByRole("region", { name: "Migration" });
    expect(within(section).getByTestId("group-empty").textContent).toBe("Nothing measured yet. Measure status is on Migration.");
    expect(within(section).queryByText("The rows")).toBeNull();
  });
});
