import type { PackId } from "@/contracts";
const META: Record<PackId, { label: string; glyph: string }> = {
  crypto: { label: "Cryptography", glyph: "⚿" }, engineering: { label: "Mechanical Engineering", glyph: "⚙" }, legal: { label: "Legal", glyph: "§" },
};
export function PackBadge({ packId, templateName }: { packId: PackId; templateName?: string }) {
  const m = META[packId];
  return <span className="tag border-ivory/60 text-ivory" data-testid="pack-badge" title={templateName ? `Pack: ${m.label} · Template: ${templateName}` : `Pack: ${m.label}`}><span aria-hidden="true">{m.glyph}</span> {m.label}{templateName ? <span className="text-faint normal-case tracking-normal"> · {templateName}</span> : null}</span>;
}
