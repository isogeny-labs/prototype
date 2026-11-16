import { useState } from "react";
import type { FixDetail } from "../../api";
import { SearchInput } from "../layout";
import { StatusChip } from "./parts";

interface Props {
  title: string;
  fixes: FixDetail[];
  selectedId: string;
  onSelect: (fixId: string) => void;
}

/** The findings that have a fix, each with its status and where the fix came from, with a search box. */
export function FixList({ title, fixes, selectedId, onSelect }: Props) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const shown = needle
    ? fixes.filter((fix) => fix.id === selectedId || [fix.title, fix.list_source, fix.status.word].some((t) => t.toLowerCase().includes(needle)))
    : fixes;
  return (
    <nav aria-labelledby="fix-list-title" className="min-w-0">
      <h2 id="fix-list-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      <div className="mb-3">
        <SearchInput value={search} onChange={setSearch} label="Search fixes" placeholder="Search fixes" />
      </div>
      <ul data-testid="fix-list" className="flex flex-col divide-y divide-slate-800/70 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/30">
        {shown.map((fix) => {
          const selected = fix.id === selectedId;
          return (
            <li key={fix.id} data-testid="fix-row">
              <button
                type="button"
                aria-current={selected ? "true" : undefined}
                onClick={() => onSelect(fix.id)}
                className={`w-full px-4 py-3 text-left transition-colors ${
                  selected ? "bg-sky-400/[0.07] shadow-[inset_2px_0_0_var(--color-sky-400)]" : "hover:bg-slate-800/40"
                }`}
              >
                <span className="block text-sm font-medium text-slate-100">{fix.title}</span>
                <span className="mt-1.5 block">
                  <StatusChip status={fix.status} />
                </span>
                <span className="mt-1.5 block text-xs text-slate-400">{fix.list_source}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
