import { useState } from "react";
import type { FixDetail } from "../../api";
import { DataTable, FilterSelect, SearchInput, Toolbar, type Column } from "../layout";
import { StatusChip } from "./parts";

interface Props {
  title: string;
  fixes: FixDetail[];
  selectedId: string | null;
  onSelect: (fixId: string) => void;
}

/** The findings that have a fix: each with where it came from and its status, with a search box and a status filter. */
export function FixTable({ title, fixes, selectedId, onSelect }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const needle = search.trim().toLowerCase();

  // One option for each status the backend sent, in its own word.
  const words = new Map<string, string>();
  for (const fix of fixes) if (!words.has(fix.status.key)) words.set(fix.status.key, fix.status.word);
  const options = [{ value: "all", label: "All statuses" }, ...Array.from(words, ([value, label]) => ({ value, label }))];

  // The open fix stays listed whatever the search, as before the panel.
  const shown = fixes.filter(
    (fix) =>
      fix.id === selectedId ||
      (statusFilter === "all" || fix.status.key === statusFilter) &&
      (!needle || [fix.title, fix.list_source, fix.status.word].some((t) => t.toLowerCase().includes(needle))),
  );

  const columns: Column<FixDetail>[] = [
    {
      key: "title",
      header: "Fix",
      render: (fix) => (
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
      ),
    },
    { key: "source", header: "Came from", render: (fix) => <span className="text-xs text-slate-400">{fix.list_source}</span> },
    { key: "status", header: "Status", className: "w-44", render: (fix) => <StatusChip status={fix.status} /> },
  ];

  return (
    <nav aria-labelledby="fix-list-title" className="min-w-0">
      <h2 id="fix-list-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} label="Search fixes" placeholder="Search fixes" />
        <FilterSelect label="Status" value={statusFilter} options={options} onChange={setStatusFilter} />
      </Toolbar>
      <div data-testid="fix-list">
        <DataTable
          label="Fixes"
          columns={columns}
          rows={shown}
          rowKey={(fix) => fix.id}
          rowTestId="fix-row"
          selectedKey={selectedId}
          onRowClick={(fix) => onSelect(fix.id)}
          empty="No fixes match this search."
        />
      </div>
    </nav>
  );
}
