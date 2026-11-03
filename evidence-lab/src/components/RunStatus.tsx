import type { Run, RunStatus as Status } from "@/contracts";

const META: Record<Status, { label: string; glyph: string; cls: string }> = {
  queued: { label: "Queued", glyph: "◷", cls: "text-muted" },
  running: { label: "Running", glyph: "▶", cls: "text-info" },
  awaiting_approval: { label: "Awaiting approval", glyph: "⏸", cls: "text-warn" },
  completed: { label: "Completed", glyph: "■", cls: "text-ink" },
  failed: { label: "Failed", glyph: "✕", cls: "text-bad" },
};

/** Status plus pass/fail plus superseded marker. Text always accompanies the glyph. */
export function RunStatus({ run, superseded = false }: { run: Run; superseded?: boolean }) {
  const m = META[run.status];
  const pass = run.status !== "completed" ? null : run.overallPass;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs" data-testid="run-status" data-status={run.status}>
      <span className={`font-semibold ${m.cls}`}><span aria-hidden="true">{m.glyph}</span> {m.label}</span>
      {pass === true ? <span className="tag border-ok/60 text-ok">Pass</span> : null}
      {pass === false ? <span className="tag border-bad/60 text-bad">Fail</span> : null}
      {pass === null && run.status === "completed" ? <span className="tag">No criteria</span> : null}
      {superseded ? <span className="tag border-warn/60 text-warn" title="A later run corrects this one. It stays in the record.">Superseded</span> : null}
    </span>
  );
}
