import type { PackPanelProps } from "../types";
import { DocLink } from "./docLink";
import { EmptyState } from "@/components";

export function ChronologyPanel({ project, data }: PackPanelProps) {
  if (project.packData.packId !== "legal") return null;
  const events = [...project.packData.chronology].sort((a, b) => (a.date < b.date ? -1 : 1));
  if (events.length === 0) return <EmptyState title="No chronology yet" />;
  return (
    <ol className="relative ml-2 border-l border-line pl-4 text-sm" data-testid="chronology">
      {events.map((e) => (
        <li key={e.id} className="relative pb-3 last:pb-0">
          <span aria-hidden="true" className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border ${e.disputed ? "border-warn bg-warn" : "border-muted bg-panel"}`} />
          <div className="flex flex-wrap items-baseline gap-x-2"><span className="font-mono text-xs text-faint">{e.date}</span><span className="font-semibold">{e.title}</span>{e.disputed ? <span className="tag border-warn/60 text-warn">disputed / checked</span> : null}</div>
          <div className="text-muted">{e.detail}</div>
          <div className="text-xs">Source: <DocLink projectId={project.id} artifacts={data.artifacts} loc={e.source} /></div>
        </li>
      ))}
    </ol>
  );
}
