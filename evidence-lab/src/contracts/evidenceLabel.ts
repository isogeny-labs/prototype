import type { Check, EvidenceLabel } from "./findings";

/**
 * The evidence label is computed, never hand-set.
 * Only a deterministic (or independently reproduced) check, or a named human reviewer, can raise it.
 * Agreement between agents never does: a finding backed only by agent claims is an Estimate.
 */
export function computeEvidenceLabel(checks: Check[], opts: { hasImportedEvidence?: boolean } = {}): EvidenceLabel {
  const kinds = new Set(checks.map((c) => c.kind));
  const namedHuman = checks.some((c) => c.kind === "human_decision" && c.reviewer && c.reviewer.name.trim().length > 0);
  if (namedHuman) return "Expert-reviewed";
  if (kinds.has("deterministic") || kinds.has("reproduced")) return "Machine-checked";
  if (kinds.has("model_judgment")) return "Model-reviewed";
  if (opts.hasImportedEvidence) return "Imported";
  return "Estimate";
}

export function labelExplanation(label: EvidenceLabel): string {
  switch (label) {
    case "Expert-reviewed": return "A named human reviewer recorded a decision on this finding.";
    case "Machine-checked": return "A deterministic check or an independent reproduction supports this finding.";
    case "Model-reviewed": return "Only model judgments support this finding; nothing deterministic or human yet.";
    case "Imported": return "Supported only by evidence imported from outside; not checked here.";
    case "Estimate": return "Backed only by agent claims. Agreement between agents does not raise this label.";
  }
}
