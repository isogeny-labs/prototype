import type { ReactNode } from "react";
import type { AdvisoryRow } from "../../api";
import { DataTable, type Column } from "../layout";
import { StatusChip } from "../ui";

/** The 5c fixes: the tag "New" beside an advisory that first arrived with the most recently installed test pack. Which
 * pack that was is said on hover, and to a screen reader in place of the bare word ("New: arrived with test pack
 * 2026.11.2"). The words are the view's. */
export function NewTag({ tag }: { tag: AdvisoryRow["new"] }) {
  if (!tag) return null;
  return (
    <span
      data-testid="advisory-new"
      data-title-skip=""
      title={tag.title}
      className="ml-0.5 inline-block whitespace-nowrap rounded border border-sky-400/50 bg-sky-400/10 px-1.5 py-px align-middle text-[11px] font-semibold leading-tight text-sky-100"
    >
      <span aria-hidden="true">{tag.label}</span>
      <span className="sr-only">
        {tag.label}: {tag.title.charAt(0).toLowerCase() + tag.title.slice(1)}
      </span>
    </span>
  );
}

/** The advisory's plain name with its id under it. A name breaks only at a space, an id only at a dash. */
function Name({ row }: { row: AdvisoryRow }) {
  return (
    <>
      <span className="block font-medium text-slate-100">
        {row.name}
        {row.new ? " " : null}
        <NewTag tag={row.new} />
      </span>
      <span className="block font-mono text-xs text-slate-400">{row.id}</span>
    </>
  );
}

/** Whether the advisory has a test: the view's label and tone, with the view's reason on hover (and in the panel). */
function TestChip({ row }: { row: AdvisoryRow }) {
  return <StatusChip label={row.test.label} tone={row.test.tone} size="sm" wrap testId="advisory-test" title={row.test.reason} />;
}

/** Where Otto's proposed check stands, exactly as the view words and tones it: "Proposed", "Added" or
 * "Not added (reason)", and under it the counts when the check fits several programs. A reason is a person's own words
 * and can be long: the chip wraps between words inside a box with a widest size, so a long reason makes its row taller
 * and never the table wider. Words of up to about 15 letters stay whole; only a longer run without a space (an address,
 * a ticket path) is broken, at the box's edge. */
function ProposalCell({ row }: { row: AdvisoryRow }) {
  return (
    <>
      <span data-testid="advisory-proposal-box" className="block max-w-[7.75rem] break-words [&>span]:max-w-full [&>span>span:last-child]:min-w-0">
        <StatusChip label={row.proposal.label} tone={row.proposal.tone} size="sm" wrap testId="advisory-proposal" />
      </span>
      {row.proposal.text ? (
        <span data-testid="advisory-proposal-text" className="mt-1 block text-xs text-slate-400">
          {row.proposal.text}
        </span>
      ) : null}
    </>
  );
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
 * panel the table shows the name and, in one column, the three chips (its test, Otto's proposal, its result here); the
 * other columns are in the panel. The widths are floors, kept modest: at 1440 pixels wide, with the sidebar and the
 * co-pilot showing, the table has 797 pixels, and the six columns fit in it without sideways scrolling even with the
 * longest date, a long program name and a long reason at once (measured in a browser; the end-to-end layout walk
 * measures it again). */
export function AdvisoryTable({
  label,
  names,
  rows,
  selectedId,
  onOpen,
  empty,
}: {
  label: string;
  /** The view's column names, in order: the advisory, when it was published, what it fits, its test, Otto's proposal,
   * its result here. */
  names: string[];
  rows: AdvisoryRow[];
  selectedId: string | null;
  onOpen: (row: AdvisoryRow) => void;
  /** What the table says when it has no row to show. */
  empty: ReactNode;
}) {
  const name = (i: number) => names[i] ?? "";
  const columns: Column<AdvisoryRow>[] = [
    { key: "advisory", header: name(0), minWidth: 150, render: (r) => <Name row={r} /> },
    { key: "published", header: name(1), minWidth: 120, render: (r) => <span className="whitespace-nowrap text-xs text-slate-300">{r.published_text}</span> },
    { key: "fits", header: name(2), minWidth: 112, render: (r) => <span className="text-xs text-slate-300">{r.fits_text}</span> },
    { key: "test", header: name(3), minWidth: 108, render: (r) => <TestChip row={r} /> },
    { key: "proposal", header: name(4), minWidth: 128, render: (r) => <ProposalCell row={r} /> },
    { key: "result", header: name(5), minWidth: 120, render: (r) => <ResultCell row={r} /> },
  ];
  const compactColumns: Column<AdvisoryRow>[] = [
    { key: "advisory", header: name(0), minWidth: 150, render: (r) => <Name row={r} /> },
    {
      key: "status",
      header: (
        <>
          <span className="block">{name(3)}</span>
          <span className="block">{name(4)}</span>
          <span className="block">{name(5)}</span>
        </>
      ),
      minWidth: 140,
      render: (r) => (
        <div className="flex flex-col items-start gap-1.5">
          <TestChip row={r} />
          <div>
            <ProposalCell row={r} />
          </div>
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
