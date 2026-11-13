import type { FixDetail } from "../../api";
import { StatusChip } from "./parts";

interface Props {
  title: string;
  fixes: FixDetail[];
  selectedId: string;
  onSelect: (fixId: string) => void;
}

/** The findings that have a fix, each with its status and where the fix came from. */
export function FixList({ title, fixes, selectedId, onSelect }: Props) {
  return (
    <nav aria-labelledby="fix-list-title">
      <h2 id="fix-list-title" className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        {title}
      </h2>
      <ul className="flex flex-col gap-2">
        {fixes.map((fix) => {
          const selected = fix.id === selectedId;
          return (
            <li key={fix.id}>
              <button
                type="button"
                aria-current={selected ? "true" : undefined}
                onClick={() => onSelect(fix.id)}
                className={`w-full rounded-xl border p-3 text-left ${
                  selected ? "border-sky-400/70 bg-sky-400/10" : "border-slate-800 bg-slate-900/40 hover:border-slate-600"
                }`}
              >
                <span className="block text-sm font-semibold text-slate-100">{fix.title}</span>
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
