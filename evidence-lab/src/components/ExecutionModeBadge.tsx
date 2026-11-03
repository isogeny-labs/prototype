import type { RunExecutionMode, RunProvenance } from "@/contracts";

const MODE: Record<RunExecutionMode, { label: string; glyph: string; cls: string; help: string }> = {
  platform_sandbox: { label: "Platform sandbox", glyph: "▣", cls: "border-accent/60 text-accent", help: "Ran in the lab's sandbox (sample)." },
  customer_side: { label: "Customer-side", glyph: "⌂", cls: "border-ivory/60 text-ivory", help: "Ran on the customer's infrastructure with the customer-side runner." },
  imported: { label: "Imported results", glyph: "⇩", cls: "border-muted/60 text-muted", help: "Results imported; nothing executed here." },
  simulated: { label: "Simulated", glyph: "◇", cls: "border-sample/60 text-sample", help: "Simulated execution: illustrative numbers, no runner connected." },
};
const PROV: Record<RunProvenance, { label: string; help: string }> = {
  measured: { label: "Measured", help: "Measured by a connected runner." },
  imported: { label: "Imported", help: "Taken from imported results." },
  illustrative: { label: "Illustrative", help: "Sample value for demonstration; not a measurement." },
};

export function ExecutionModeBadge({ mode }: { mode: RunExecutionMode }) {
  const m = MODE[mode];
  return <span className={`tag ${m.cls}`} title={m.help} data-testid="execution-mode" data-mode={mode}><span aria-hidden="true">{m.glyph}</span> {m.label}</span>;
}
export function ProvenanceBadge({ provenance }: { provenance: RunProvenance }) {
  const p = PROV[provenance];
  const cls = provenance === "illustrative" ? "border-sample/60 text-sample" : provenance === "imported" ? "border-ivory/60 text-ivory" : "border-ok/60 text-ok";
  return <span className={`tag ${cls}`} title={p.help} data-testid="provenance" data-provenance={provenance}>{p.label}</span>;
}
