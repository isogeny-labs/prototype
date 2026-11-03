import type { StatusHistoryEntry } from "@/contracts";
import { fmtDateTime, humanize } from "@/lib/format";

export function FindingTimeline({ history }: { history: StatusHistoryEntry[] }) {
  if (history.length === 0) return <div className="text-sm text-muted">No history recorded.</div>;
  return (
    <ol className="relative ml-2 border-l border-line pl-4 text-sm" data-testid="finding-timeline">
      {history.map((h, i) => (
        <li key={`${h.status}-${h.at}-${i}`} className="relative pb-3 last:pb-0">
          <span aria-hidden="true" className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border ${i === history.length - 1 ? "bg-accent border-accent" : "bg-panel border-muted"}`} />
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold">{humanize(h.status)}</span>
            <span className="text-xs text-faint">{fmtDateTime(h.at)}</span>
            <span className="text-xs text-muted">by {h.by}</span>
          </div>
          <div className="text-muted">{h.note}</div>
        </li>
      ))}
    </ol>
  );
}
