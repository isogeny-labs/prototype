import { EmptyState, Marker } from "@/components";
import type { PackPanelProps } from "../types";

export function RehearsalPanel({ project }: PackPanelProps) {
  if (project.packData.packId !== "legal") return null;
  const r = project.packData.rehearsal;
  if (r.items.length === 0) return <EmptyState title="No rehearsal items yet" />;
  return (
    <div data-testid="rehearsal">
      <div className="callout mb-3 font-semibold" data-testid="rehearsal-disclaimer">{r.disclaimer}</div>
      <div className="grid gap-3 md:grid-cols-2">
        {(["counterargument", "question"] as const).map((kind) => (
          <div key={kind}>
            <div className="h3 mb-1">{kind === "counterargument" ? "Likely counterarguments" : "Likely questions"}</div>
            <ul className="space-y-2 text-sm">{r.items.filter((i) => i.kind === kind).map((i) => (
              <li key={i.id} className="panel-2">
                <div className="flex items-start gap-2"><span aria-hidden="true" className="text-warn">{kind === "counterargument" ? "⚔" : "?"}</span><span>{i.text}</span></div>
                <div className="mt-1 text-muted"><span className="font-semibold text-ink">Prepared response:</span> {i.preparedResponse}</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-faint"><span className="tag border-info/60 text-info">◐ Model judgment</span>{i.source.model}<Marker kind="simulated" /></div>
              </li>
            ))}</ul>
          </div>
        ))}
      </div>
      <div className="mt-2 text-xs text-faint">No probability of success is computed or shown anywhere in this pack.</div>
    </div>
  );
}
