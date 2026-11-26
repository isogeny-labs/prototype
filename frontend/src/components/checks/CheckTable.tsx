import type { CheckRow } from "../../api";
import { DataTable, type Column } from "../layout";
import { FromOttoTag } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { sourceParts } from "../sourceParts";
import { formatTime, ResultBadge, StatusView, WhereFromTag } from "../ui";

/** Phase 5c: an advisory check came from one of Otto's proposals that a person accepted. Its row carries the tag and
 * the advisory as a link, both in the view's words. The link opens the advisory; it does not open the row's panel. */
export function FromOttoMark({ row }: { row: CheckRow }) {
  const from = row.from_otto;
  if (!from) return null;
  return (
    <span
      data-testid="check-from-otto-mark"
      className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs"
      onClick={(e) => e.stopPropagation()}
    >
      <FromOttoTag label={from.label} />
      <ItemLinkView link={from.link} testId="check-from-otto">
        {from.advisory}
      </ItemLinkView>
    </span>
  );
}

/** `wrap`: beside an open panel the column is narrow, so a long result ("No slowdown beyond measured noise") may take
 * two lines, breaking between words only. */
function Result({ row, wrap = false, quiet = false }: { row: CheckRow; wrap?: boolean; quiet?: boolean }) {
  if (row.status) return <StatusView status={row.status} />;
  if (row.result)
    return (
      // (22 November 2026: where it came from, right under its own word)
      <span className="flex flex-col items-start gap-1">
        <ResultBadge label={row.result.label} tone={row.result.tone} wrap={wrap} />
        <WhereFromTag tag={row.source_tag} quiet={quiet} />
      </span>
    );
  return <span className="text-xs text-slate-500">Not run yet</span>;
}

/** `quiet`: the table is drawn in parts, whose headings say what each row rests on; a row then keeps its tag for a
 * screen reader only. */
const columnsFor = (quiet: boolean): Column<CheckRow>[] => [
  {
    key: "check",
    header: "Check",
    minWidth: 200,
    render: (r) => (
      <>
        <span className="block font-medium text-slate-100">{r.name}</span>
        <span className="block text-xs text-slate-400">
          {r.ran_on}
          {/* The 5c fixes: in a retest's block, a server (or a program the retest did not move) was run again unchanged. */}
          {r.mark ? <span data-testid="check-mark"> · {r.mark}</span> : null}
        </span>
        <FromOttoMark row={r} />
        {(r.same_as ?? []).length > 0 ? (
          <span data-testid="same-measurement-marker" className="mt-0.5 block text-xs text-slate-500">
            The same measurement as {(r.same_as ?? []).map((o) => o.name).join(", ")}
          </span>
        ) : null}
      </>
    ),
  },
  {
    key: "from",
    header: "Came from",
    minWidth: 120,
    render: (r) => <span className="text-xs text-slate-300">{r.came_from.label}</span>,
  },
  { key: "result", header: "Result", minWidth: 120, render: (r) => <Result row={r} quiet={quiet} /> },
  {
    key: "when",
    header: "Last run",
    minWidth: 120,
    render: (r) =>
      r.last_run_at ? (
        <span className="text-xs text-slate-400">
          {formatTime(r.last_run_at)}
          <span className="block">
            {r.runs} {r.runs === 1 ? "run" : "runs"}
          </span>
        </span>
      ) : null,
  },
];

// Beside an open panel: the name, one summary status and its key marker (where it came from).
const compactColumnsFor = (quiet: boolean): Column<CheckRow>[] => [
  {
    key: "check",
    header: "Check",
    minWidth: 150,
    render: (r) => (
      <>
        <span className="block font-medium text-slate-100">{r.name}</span>
        <span className="block text-xs text-slate-500">
          {r.ran_on} · {r.mark ?? r.came_from.label}
        </span>
        <FromOttoMark row={r} />
      </>
    ),
  },
  { key: "result", header: "Result", minWidth: 96, render: (r) => <Result row={r} wrap quiet={quiet} /> },
];
const COLUMNS = { plain: columnsFor(false), quiet: columnsFor(true) };
const COMPACT = { plain: compactColumnsFor(false), quiet: compactColumnsFor(true) };

/** Phase 5b: a group's checks (Checks and Evidence draw the same table). The design refactor (26 November 2026): on
 * Evidence the rows come in labelled parts, by what each result rests on (`inParts`). */
export function CheckTable({
  label,
  rows,
  selectedId,
  onOpen,
  inParts = false,
}: {
  label: string;
  rows: CheckRow[];
  selectedId: string | null;
  onOpen: (row: CheckRow) => void;
  inParts?: boolean;
}) {
  const look = inParts ? "quiet" : "plain";
  return (
    <DataTable
      label={label}
      columns={COLUMNS[look]}
      compactColumns={COMPACT[look]}
      parts={inParts ? (all) => sourceParts(all, (r) => (r.status ? null : r.source_tag)) : undefined}
      rows={rows}
      rowKey={(r) => r.id}
      rowTestId="check-row"
      rowAttrs={(r) => ({ "data-check": r.id, "data-group": r.group, "data-came-from": r.came_from.key })}
      selectedKey={
        rows.find((r) => r.id === selectedId || (r.alias != null && r.alias === selectedId))?.id ?? selectedId
      }
      onRowClick={onOpen}
      empty="No check matches this search."
    />
  );
}
