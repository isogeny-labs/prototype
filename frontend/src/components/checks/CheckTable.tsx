import type { CheckRow } from "../../api";
import { DataTable, type Column } from "../layout";
import { FromOttoTag } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { formatTime, ResultBadge, StatusView } from "../ui";

/** Phase 5c: an advisory check came from one of Otto's proposals that a person accepted. Its row carries the tag and
 * the advisory as a link, both in the view's words. The link opens the advisory; it does not open the row's panel. */
export function FromOttoMark({ row }: { row: CheckRow }) {
  const from = row.from_otto;
  if (!from) return null;
  return (
    <span data-testid="check-from-otto-mark" className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs" onClick={(e) => e.stopPropagation()}>
      <FromOttoTag label={from.label} />
      <ItemLinkView link={from.link} testId="check-from-otto">
        {from.advisory}
      </ItemLinkView>
    </span>
  );
}

/** `wrap`: beside an open panel the column is narrow, so a long result ("No slowdown beyond measured noise") may take
 * two lines, breaking between words only. */
function Result({ row, wrap = false }: { row: CheckRow; wrap?: boolean }) {
  if (row.status) return <StatusView status={row.status} />;
  if (row.result) return <ResultBadge label={row.result.label} tone={row.result.tone} wrap={wrap} />;
  return <span className="text-xs text-slate-500">Not run yet</span>;
}

const columns: Column<CheckRow>[] = [
  {
    key: "check",
    header: "Check",
    minWidth: 200,
    render: (r) => (
      <>
        <span className="block font-medium text-slate-100">{r.name}</span>
        <span className="block text-xs text-slate-400">{r.ran_on}</span>
        <FromOttoMark row={r} />
        {(r.same_as ?? []).length > 0 ? (
          <span data-testid="same-measurement-marker" className="mt-0.5 block text-xs text-slate-500">
            The same measurement as {(r.same_as ?? []).map((o) => o.name).join(", ")}
          </span>
        ) : null}
      </>
    ),
  },
  { key: "from", header: "Came from", minWidth: 120, render: (r) => <span className="text-xs text-slate-300">{r.came_from.label}</span> },
  { key: "result", header: "Result", minWidth: 120, render: (r) => <Result row={r} /> },
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
const compactColumns: Column<CheckRow>[] = [
  {
    key: "check",
    header: "Check",
    minWidth: 150,
    render: (r) => (
      <>
        <span className="block font-medium text-slate-100">{r.name}</span>
        <span className="block text-xs text-slate-500">
          {r.ran_on} · {r.came_from.label}
        </span>
        <FromOttoMark row={r} />
      </>
    ),
  },
  { key: "result", header: "Result", minWidth: 96, render: (r) => <Result row={r} wrap /> },
];

/** Phase 5b: a group's checks (Checks and Evidence draw the same table). */
export function CheckTable({
  label,
  rows,
  selectedId,
  onOpen,
}: {
  label: string;
  rows: CheckRow[];
  selectedId: string | null;
  onOpen: (row: CheckRow) => void;
}) {
  return (
    <DataTable
      label={label}
      columns={columns}
      compactColumns={compactColumns}
      rows={rows}
      rowKey={(r) => r.id}
      rowTestId="check-row"
      rowAttrs={(r) => ({ "data-check": r.id, "data-group": r.group, "data-came-from": r.came_from.key })}
      selectedKey={selectedId}
      onRowClick={onOpen}
      empty="No check matches this search."
    />
  );
}
