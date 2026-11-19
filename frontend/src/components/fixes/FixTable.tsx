import { useState } from "react";
import type { FixDetail, FixGroup } from "../../api";
import { DataTable, FilterSelect, GroupSection, SearchInput, Toolbar, type Column } from "../layout";
import { FromOttoTag, ProposalStatusChip } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { StatusChip } from "./parts";

interface Props {
  title: string;
  fixes: FixDetail[];
  /** Phase 5b: the four work groups, in order, with their counts. */
  groups: FixGroup[];
  selectedId: string | null;
  onSelect: (fixId: string) => void;
  /** Phase 5b: a work group to start filtered to. */
  group?: string | null;
}

/** The findings that have a fix, in the four work groups: each with where it came from (as links) and its status, with
 * a search box, a group filter and a status filter. Phase 6d: a suggestion for a developer's change is listed in its
 * group under a heading of its own (`group.apart`); the group's counts are the backend's and leave it out. */
export function FixTable({ title, fixes, groups, selectedId, onSelect, group = null }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [groupFilter, setGroupFilter] = useState(group ?? "all");
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const needle = search.trim().toLowerCase();

  // One option for each status word the backend sent (several change-box statuses share one key, each its own word).
  const words = Array.from(new Set(fixes.map((fix) => fix.status.word)));
  const options = [{ value: "all", label: "All statuses" }, ...words.map((w) => ({ value: w, label: w }))];

  // The open fix stays listed whatever the search, as before the panel.
  const keep = (fix: FixDetail) =>
    fix.id === selectedId ||
    ((statusFilter === "all" || fix.status.word === statusFilter) &&
      (!needle ||
        [fix.title, fix.list_source, fix.status.word, fix.proposal?.status.word ?? ""].some((t) => t.toLowerCase().includes(needle))));

  const columns: Column<FixDetail>[] = [
    {
      key: "title",
      header: "Fix",
      minWidth: 180,
      render: (fix) => (
        <>
          <button
            type="button"
            aria-current={fix.id === selectedId ? "true" : undefined}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(fix.id);
            }}
            className="text-left text-sm font-medium text-slate-100 hover:text-sky-300"
          >
            {fix.title}
          </button>
          {/* Phase 5c: a fix of Otto's is a proposal. Its tag and where a person's decisions on it stand, in the view's
              words, under the name: so the full table and the compact one (beside an open panel) both show them. */}
          {fix.proposal ? (
            <span data-testid="fix-proposal-mark" className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5">
              <FromOttoTag label={fix.proposal.label} testId="fix-proposal-label" />
              <ProposalStatusChip status={fix.proposal.status} testId="fix-proposal-status" />
            </span>
          ) : null}
        </>
      ),
    },
    {
      key: "source",
      header: "Came from",
      minWidth: 160,
      render: (fix) => (
        <span className="text-xs text-slate-400">
          {fix.list_source}
          {(fix.came_from_links ?? []).length > 0 ? (
            <span className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5" onClick={(e) => e.stopPropagation()}>
              {(fix.came_from_links ?? []).map((c, i) => (
                <ItemLinkView key={i} link={c.link} testId="came-from-link">
                  {c.label}
                </ItemLinkView>
              ))}
            </span>
          ) : null}
        </span>
      ),
    },
    { key: "status", header: "Status", minWidth: 140, render: (fix) => <StatusChip status={fix.status} /> },
  ];
  // Phase 5b: beside an open panel, a row is the fix and its status.
  const compactColumns: Column<FixDetail>[] = [
    { ...columns[0]!, minWidth: 150 },
    { ...columns[2]!, minWidth: 112 },
  ];

  const byId = new Map(fixes.map((f) => [f.id, f]));
  const shownGroups = groups.length > 0 ? groups : [];
  return (
    <nav aria-labelledby="fix-list-title" className="min-w-0">
      <h2 id="fix-list-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search fixes" placeholder="Search fixes" />
        <FilterSelect
          label="Group"
          value={groupFilter}
          options={[{ value: "all", label: "All groups" }, ...shownGroups.map((g) => ({ value: g.key, label: g.label }))]}
          onChange={setGroupFilter}
        />
        <FilterSelect label="Status" value={statusFilter} options={options} onChange={setStatusFilter} />
      </Toolbar>
      <div data-testid="fix-list">
        {shownGroups
          .filter((g) => groupFilter === "all" || g.key === groupFilter)
          .map((g) => {
            const rows = g.fix_ids.map((id) => byId.get(id)).filter((f): f is FixDetail => f !== undefined).filter(keep);
            const apartAll = (g.apart?.fix_ids ?? []).map((id) => byId.get(id)).filter((f): f is FixDetail => f !== undefined);
            const apartRows = apartAll.filter(keep);
            return (
              <GroupSection
                key={g.key}
                group={g}
                counts={g.counts}
                open={!folded[g.key]}
                onToggle={() => setFolded((f) => ({ ...f, [g.key]: !f[g.key] }))}
                emptyText={g.fix_ids.length === 0 && apartAll.length === 0 ? g.empty_text : null}
                also={
                  g.also.length > 0 ? (
                    <span>
                      Also relates to this group:{" "}
                      {g.also.map((a, i) => (
                        <span key={a.fix_id}>
                          {i > 0 ? ", " : ""}
                          <button type="button" onClick={() => onSelect(a.fix_id)} className="text-sky-300 hover:underline">
                            {a.title}
                          </button>{" "}
                          (in {a.group_label})
                        </span>
                      ))}
                    </span>
                  ) : null
                }
              >
                {rows.length > 0 ? (
                  <DataTable
                    label={`${g.label} fixes`}
                    columns={columns}
                    compactColumns={compactColumns}
                    rows={rows}
                    rowKey={(fix) => fix.id}
                    rowTestId="fix-row"
                    selectedKey={selectedId}
                    onRowClick={(fix) => onSelect(fix.id)}
                  />
                ) : g.fix_ids.length === 0 ? (
                  // only entries listed apart: the group's own sentence still says that no finding of its own has a fix
                  <p data-testid="group-empty" className="px-1 py-2 text-sm text-slate-400">
                    {g.empty_text}
                  </p>
                ) : (
                  <p className="px-1 py-2 text-sm text-slate-400">No fixes match this search.</p>
                )}
                {g.apart && apartAll.length > 0 ? (
                  <section data-testid="fix-apart" aria-label={g.apart.label} className="mt-4">
                    <h3 data-testid="fix-apart-title" className="px-1 text-xs font-medium uppercase tracking-wider text-slate-500">
                      {g.apart.label} ({apartAll.length})
                    </h3>
                    <p data-testid="fix-apart-note" className="mb-2 mt-1 px-1 text-xs text-slate-400">
                      {g.apart.note}
                    </p>
                    {apartRows.length > 0 ? (
                      <DataTable
                        label={g.apart.label}
                        columns={columns}
                        compactColumns={compactColumns}
                        rows={apartRows}
                        rowKey={(fix) => fix.id}
                        rowTestId="fix-apart-row"
                        selectedKey={selectedId}
                        onRowClick={(fix) => onSelect(fix.id)}
                      />
                    ) : (
                      <p className="px-1 py-2 text-sm text-slate-400">None of these match this search.</p>
                    )}
                  </section>
                ) : null}
              </GroupSection>
            );
          })}
      </div>
    </nav>
  );
}
