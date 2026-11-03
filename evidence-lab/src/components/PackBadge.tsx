import type { PackId } from "@/contracts";
const META: Record<PackId, { label: string; glyph: string }> = {
  crypto: { label: "Cryptography", glyph: "⚿" }, engineering: { label: "Mechanical Engineering", glyph: "⚙" }, legal: { label: "Legal", glyph: "§" },
};
/** Pack badge. In compact mode (the header) the template name shows only when there is room (xl and up); the title always carries it. */
export function PackBadge({ packId, templateName, compact = false }: { packId: PackId; templateName?: string; compact?: boolean }) {
  const m = META[packId];
  return (
    <span className={`tag min-w-0 max-w-full border-ivory/60 text-ivory ${compact ? "truncate" : ""}`} data-testid="pack-badge" title={templateName ? `Pack: ${m.label} · Template: ${templateName}` : `Pack: ${m.label}`}>
      <span aria-hidden="true">{m.glyph}</span> {m.label}
      {templateName ? <span className={`text-faint normal-case tracking-normal ${compact ? "hidden xl:inline" : ""}`}> · {templateName}</span> : null}
    </span>
  );
}
