import type { EvidenceLabel as Label } from "@/contracts";

const META: Record<Label, { glyph: string; cls: string; help: string }> = {
  "Machine-checked": { glyph: "⚙", cls: "border-ok/60 text-ok", help: "A deterministic check or a reproduced run supports this." },
  "Expert-reviewed": { glyph: "✓", cls: "border-accent/60 text-accent", help: "A named human reviewer recorded a decision." },
  "Model-reviewed": { glyph: "◐", cls: "border-info/60 text-info", help: "Only a model judgment supports this; no deterministic check or reviewer yet." },
  "Imported": { glyph: "⇩", cls: "border-ivory/60 text-ivory", help: "Evidence was imported; it was not produced or reproduced here." },
  "Estimate": { glyph: "~", cls: "border-warn/60 text-warn", help: "Only agent claims or no checks. Agreement between agents never raises this." },
};

/** Computed label; never hand-set. Shape + text, never colour alone. */
export function EvidenceLabel({ label, size = "sm" }: { label: Label; size?: "sm" | "md" }) {
  const m = META[label];
  return (
    <span className={`tag ${m.cls} ${size === "md" ? "text-xs px-2 py-1" : ""}`} title={`${label}: ${m.help}`} data-testid="evidence-label" data-label={label}>
      <span aria-hidden="true">{m.glyph}</span> {label}
    </span>
  );
}
