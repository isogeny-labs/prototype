import type { Check, CheckKind, CheckResult } from "@/contracts";
import { fmtDateTime } from "@/lib/format";

const KIND: Record<CheckKind, { label: string; glyph: string; cls: string }> = {
  agent_claim: { label: "Agent claim", glyph: "◌", cls: "border-warn/60 text-warn" },
  deterministic: { label: "Deterministic check", glyph: "⚙", cls: "border-ok/60 text-ok" },
  model_judgment: { label: "Model judgment", glyph: "◐", cls: "border-info/60 text-info" },
  human_decision: { label: "Human decision", glyph: "✓", cls: "border-accent/60 text-accent" },
  reproduced: { label: "Reproduced", glyph: "⟲", cls: "border-ok/60 text-ok" },
};
const RESULT: Record<CheckResult, { label: string; glyph: string; cls: string }> = {
  supports: { label: "supports", glyph: "▲", cls: "text-ok" },
  refutes: { label: "refutes", glyph: "▼", cls: "text-bad" },
  inconclusive: { label: "inconclusive", glyph: "●", cls: "text-warn" },
};

export function CheckKindBadge({ kind }: { kind: CheckKind }) {
  const k = KIND[kind];
  return <span className={`tag ${k.cls}`} data-testid="check-kind"><span aria-hidden="true">{k.glyph}</span> {k.label}</span>;
}

/** One check, with who/what produced it. The "by" line names the model or the reviewer explicitly. */
export function CheckBadge({ check }: { check: Check }) {
  const r = RESULT[check.result];
  const by = check.kind === "human_decision" && check.reviewer ? `Reviewer: ${check.reviewer.name}`
    : check.kind === "model_judgment" && check.model ? `Model: ${check.model.name} (${check.model.version})`
    : check.agent ? `Agent: ${check.agent.name}` : "Runner";
  return (
    <div className="panel-2 text-sm" data-testid="check">
      <div className="flex flex-wrap items-center gap-2">
        <CheckKindBadge kind={check.kind} />
        <span className={`text-xs font-semibold ${r.cls}`}><span aria-hidden="true">{r.glyph}</span> {r.label}</span>
        <span className="ml-auto text-xs text-faint">{fmtDateTime(check.timestamp)}</span>
      </div>
      <div className="mt-1.5">{check.method}</div>
      {check.detail ? <div className="mt-1 text-muted">{check.detail}</div> : null}
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{by}</span>
        {check.evidenceLinks.map((l) => <span key={`${l.kind}-${l.id}`} className="tag">{l.label}</span>)}
      </div>
    </div>
  );
}
