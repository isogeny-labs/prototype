import type { IntegrityLevel } from "@/contracts";

const META: Record<IntegrityLevel, { label: string; glyph: string; cls: string; help: string }> = {
  imported: { label: "Imported", glyph: "⇩", cls: "border-ivory/60 text-ivory", help: "Received from outside; hash recorded, nothing verified about how it was produced." },
  hashed: { label: "Hashed", glyph: "#", cls: "border-muted/60 text-muted", help: "SHA-256 manifest recorded and re-checkable. Not signed." },
  signed: { label: "Signed", glyph: "✎", cls: "border-info/60 text-info", help: "Manifest signed by a named key." },
  cairn_verified: { label: "Cairn-verified", glyph: "⛰", cls: "border-ok/60 text-ok", help: "Independently verified by Cairn. Only present when a record is explicitly marked so." },
};

export function IntegrityBadge({ level }: { level: IntegrityLevel }) {
  const m = META[level];
  return <span className={`tag ${m.cls}`} title={m.help} data-testid="integrity-badge" data-level={level}><span aria-hidden="true">{m.glyph}</span> {m.label}</span>;
}
