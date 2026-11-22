import { useState } from "react";
import type { FixDetail, FixGroup } from "../../api";
import { DataTable, FilterSelect, GroupSection, GroupTabs, SearchInput, Toolbar, type Column } from "../layout";
import { FromOttoTag, ProposalStatusChip } from "../otto/ProposalCard";
import { ItemLinkView } from "../related";
import { StatusChip } from "./parts";
import { WhereFromTag } from "../ui";

interface Props {
  title: string;
  fixes: FixDetail[];
  /** Phase 5b: the four work groups, in order, with their counts. */
  groups: FixGroup[];
  selectedId: string | null;
  onSelect: (fixId: string) => void;
  /** 20 November 2026: the groups are tabs. The tab that is open (the page picks it), how another is chosen, and the id
   * that ties the tabs to their panel. */
  active: string | null;
  onChoose: (group: string) => void;
  idBase: string;
}

/** The findings that have a fix, in the four work groups, one group's tab at a time: each with where it came from (as
 * links) and its status, with a search box and a status filter. Phase 6d: a suggestion for a developer's change is listed
 * in its group under a heading of its own (`group.apart`); the group's counts are the backend's and leave it out. */
export function FixTable({ title, fixes, groups, selectedId, onSelect, active, onChoose, idBase }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const needle = search.trim().toLowerCase();

  // One option for each status word the backend sent (several change-box statuses share one key, each its own word).
  const words = Array.from(new Set(fixes.map((fix) => fix.status.word)));
  const options = [{ value: "all", label: "All statuses" }, ...words.map((w) => ({ value: w, label: w }))];

  const fits = (fix: FixDetail) =>
    (statusFilter === "all" || fix.status.word === statusFilter) &&
    (!needle ||
      [fix.title, fix.list_source, fix.status.word, fix.proposal?.status.word ?? ""].some((t) =>
        t.toLowerCase().includes(needle),
      ));
  // The open fix stays listed whatever the search, as before the panel.
  const keep = (fix: FixDetail) => fix.id === selectedId || fits(fix);

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
          {/* 22 November 2026: where that finding came from, right under the sentence that names it (and above its links) */}
          {fix.source_tag ? (
            <span className="mt-1 block">
              <WhereFromTag tag={fix.source_tag} />
            </span>
          ) : null}
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
    {
      ...columns[2]!,
      minWidth: 112,
      // (beside an open panel "Came from" is not drawn: the tag of where the fix came from sits under its status)
      render: (fix) => (
        <span className="flex flex-col items-start gap-1">
          <StatusChip status={fix.status} />
          <WhereFromTag tag={fix.source_tag} />
        </span>
      ),
    },
  ];

  const byId = new Map(fixes.map((f) => [f.id, f]));
  const shownGroups = groups.length > 0 ? groups : [];
  const entries = (ids: string[]) => ids.map((id) => byId.get(id)).filter((f): f is FixDetail => f !== undefined);
  // While a search or the status filter is on, each tab says how many of its fixes match. An entry listed apart (a
  // developer's change) is counted nowhere (CLAUDE.md), so not here either; the search still lists it under its heading.
  const matches =
    needle || statusFilter !== "all"
      ? Object.fromEntries(shownGroups.map((g) => [g.key, entries(g.fix_ids).filter(fits).length]))
      : null;
  const holderOf = (fixId: string) =>
    shownGroups.find((g) => g.fix_ids.includes(fixId) || (g.apart?.fix_ids ?? []).includes(fixId))?.key;
  return (
    <nav aria-labelledby="fix-list-title" className="min-w-0">
      <h2 id="fix-list-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      {active !== null && shownGroups.length > 0 ? (
        <GroupTabs groups={shownGroups} active={active} onChoose={onChoose} idBase={idBase} matches={matches} />
      ) : null}
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search fixes" placeholder="Search fixes" />
        <FilterSelect label="Status" value={statusFilter} options={options} onChange={setStatusFilter} />
      </Toolbar>
      <div data-testid="fix-list">
        {shownGroups
          .filter((g) => g.key === active)
          .map((g) => {
            const rows = entries(g.fix_ids).filter(keep);
            const apartAll = entries(g.apart?.fix_ids ?? []);
            const apartRows = apartAll.filter(keep);
            return (
              <GroupSection
                key={g.key}
                group={g}
                counts={g.counts}
                tabbed={{ idBase }}
                emptyText={g.fix_ids.length === 0 && apartAll.length === 0 ? g.empty_text : null}
                also={
                  g.also.length > 0 ? (
                    <span>
                      Also relates to this group:{" "}
                      {g.also.map((a, i) => (
                        <span key={a.fix_id}>
                          {i > 0 ? ", " : ""}
                          <button
                            type="button"
                            onClick={() => {
                              // the fix sits in its own group: its tab opens, with the fix
                              const holder = holderOf(a.fix_id);
                              if (holder) onChoose(holder);
                              onSelect(a.fix_id);
                            }}
                            className="text-sky-300 hover:underline"
                          >
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
                    <h3
                      data-testid="fix-apart-title"
                      className="px-1 text-xs font-medium uppercase tracking-wider text-slate-500"
                    >
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
