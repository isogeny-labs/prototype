import { Link } from "react-router-dom";
import type { Task, TaskStatus } from "@/contracts";
import { humanize } from "@/lib/format";
import { Marker } from "./Marker";

const STATUS: Record<TaskStatus, { glyph: string; cls: string }> = {
  queued: { glyph: "◷", cls: "text-muted" }, running: { glyph: "▶", cls: "text-info" }, blocked: { glyph: "⊘", cls: "text-bad" },
  awaiting_checkpoint: { glyph: "⏸", cls: "text-warn" }, paused: { glyph: "⏸", cls: "text-warn" }, cancelled: { glyph: "✕", cls: "text-faint" },
  failed: { glyph: "✕", cls: "text-bad" }, done: { glyph: "■", cls: "text-ok" },
};

/** Lays tasks out by dependency depth (columns), listing dependencies by title. No chart library. */
export function TaskGraph({ tasks, projectId, actions }: { tasks: Task[]; projectId: string; actions?: (t: Task) => React.ReactNode }) {
  const byId = Object.fromEntries(tasks.map((t) => [t.id, t]));
  const depth = (t: Task, seen = new Set<string>()): number => {
    if (t.dependsOn.length === 0 || seen.has(t.id)) return 0;
    seen.add(t.id);
    return 1 + Math.max(...t.dependsOn.map((d) => { const p = byId[d]; return p ? depth(p, seen) : 0; }));
  };
  const levels: Task[][] = [];
  for (const t of tasks) { const d = depth(t); (levels[d] ??= []).push(t); }
  return (
    <div data-testid="task-graph">
      <div className="flex flex-wrap gap-3">
        {levels.map((col, i) => (
          <div key={i} className="flex w-60 flex-col gap-3">
            <div className="h3">Step {i + 1}</div>
            {col.map((t) => {
              const s = STATUS[t.status];
              const pct = t.budget.limit > 0 ? Math.min(100, Math.round((t.budget.used / t.budget.limit) * 100)) : 0;
              return (
                <div key={t.id} className="panel-2 text-sm" data-testid="task" data-status={t.status}>
                  <div className={`text-xs font-semibold ${s.cls}`}><span aria-hidden="true">{s.glyph}</span> {humanize(t.status)}</div>
                  <div className="mt-1 font-medium">{t.title}</div>
                  <div className="mt-1 text-xs text-muted">{t.owner.type === "agent" ? "Agent" : t.owner.type === "tool" ? "Tool" : "Human"}: {t.owner.name}{t.owner.model ? <span className="block text-faint">model: {t.owner.model}</span> : null}</div>
                  {t.owner.type !== "human" ? <div className="mt-1"><Marker kind="simulated" /></div> : null}
                  {t.dependsOn.length > 0 ? <div className="mt-1 text-xs text-faint">after: {t.dependsOn.map((d) => byId[d]?.title ?? d).join("; ")}</div> : null}
                  <div className="mt-2 text-xs text-muted">Budget: {t.budget.used} / {t.budget.limit} {humanize(t.budget.unit).toLowerCase()}</div>
                  {t.budget.limit > 0 ? <div className="mt-1 h-1.5 w-full rounded bg-bg" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Budget used ${pct}%`}><div className={`h-1.5 rounded ${pct >= 90 ? "bg-warn" : "bg-accent"}`} style={{ width: `${pct}%` }} /></div> : null}
                  {t.checkpoint ? <div className="mt-2 text-xs"><span className="tag border-warn/60 text-warn">Checkpoint</span> <span className="text-muted">{t.checkpoint.label}</span> · <Link to={`/p/${projectId}/approvals`}>approval</Link></div> : null}
                  {t.producesRunId ? <div className="mt-1 text-xs"><Link to={`/p/${projectId}/runs/${t.producesRunId}`}>Produced run</Link></div> : null}
                  {t.note ? <div className="mt-1 text-xs text-muted">{t.note}</div> : null}
                  {actions ? <div className="mt-2 flex flex-wrap gap-1">{actions(t)}</div> : null}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
