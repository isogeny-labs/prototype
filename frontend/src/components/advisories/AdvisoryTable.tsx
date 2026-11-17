import type { ReactNode } from "react";
import type { AdvisoryRow } from "../../api";
import { DataTable, type Column } from "../layout";
import { StatusChip } from "../ui";

/** The advisory's plain name with its id under it. A name breaks only at a space, an id only at a dash. */
function Name({ row }: { row: AdvisoryRow }) {
  return (
    <>
      <span className="block font-medium text-slate-100">{row.name}</span>
      <span className="block font-mono text-xs text-slate-400">{row.id}</span>
    </>
  );
}

/** Whether the advisory has a test: the view's label and tone, with the view's reason on hover (and in the panel). */
function TestChip({ row }: { row: AdvisoryRow }) {
  return <StatusChip label={row.test.label} tone={row.test.tone} size="sm" wrap testId="advisory-test" title={row.test.reason} />;
}

/** The latest result of the advisory's check here, exactly as the view words and tones it. */
function ResultCell({ row }: { row: AdvisoryRow }) {
  return (
    <>
      <StatusChip label={row.result.label} tone={row.result.tone} size="sm" wrap testId="advisory-result" />
      {row.result.text ? <span className="mt-1 block text-xs text-slate-400">{row.result.text}</span> : null}
    </>
  );
}

/** Phase 5c: the advisories of the installed test packs, one row each. The column names are the view's. Beside an open
 * panel the table shows the name and, in one column, the two chips; the other columns are in the panel. */
export function AdvisoryTable({
  label,
  names,
  rows,
  selectedId,
  onOpen,
  empty,
}: {
  label: string;
  /** The view's column names, in order: the advisory, when it was published, what it fits, its test, its result here. */
  names: string[];
  rows: AdvisoryRow[];
  selectedId: string | null;
  onOpen: (row: AdvisoryRow) => void;
  /** What the table says when it has no row to show. */
  empty: ReactNode;
}) {
  const name = (i: number) => names[i] ?? "";
  const columns: Column<AdvisoryRow>[] = [
    { key: "advisory", header: name(0), minWidth: 200, render: (r) => <Name row={r} /> },
    { key: "published", header: name(1), minWidth: 132, render: (r) => <span className="whitespace-nowrap text-xs text-slate-300">{r.published_text}</span> },
    { key: "fits", header: name(2), minWidth: 132, render: (r) => <span className="text-xs text-slate-300">{r.fits_text}</span> },
    { key: "test", header: name(3), minWidth: 124, render: (r) => <TestChip row={r} /> },
    { key: "result", header: name(4), minWidth: 132, render: (r) => <ResultCell row={r} /> },
  ];
  const compactColumns: Column<AdvisoryRow>[] = [
    { key: "advisory", header: name(0), minWidth: 150, render: (r) => <Name row={r} /> },
    {
      key: "status",
      header: (
        <>
          <span className="block">{name(3)}</span>
          <span className="block">{name(4)}</span>
        </>
      ),
      minWidth: 140,
      render: (r) => (
        <div className="flex flex-col items-start gap-1.5">
          <TestChip row={r} />
          <div>
            <ResultCell row={r} />
          </div>
        </div>
      ),
    },
  ];
  return (
    <div data-testid="advisories-table">
      <DataTable
        label={label}
        columns={columns}
        compactColumns={compactColumns}
        rows={rows}
        rowKey={(r) => r.id}
        rowTestId="advisory-row"
        rowAttrs={(r) => ({ "data-advisory": r.id })}
        selectedKey={selectedId}
        onRowClick={onOpen}
        empty={empty}
      />
    </div>
  );
}
