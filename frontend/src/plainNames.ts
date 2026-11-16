/** Phase 5a: plain names first on screen, the technical name under them. Only the words on screen change: every id,
 * answer-key field and evidence field keeps its technical name. */
const PLAIN: Record<string, { plain: string; technical: string }> = {
  "ML-KEM-768": { plain: "Quantum-safe key exchange", technical: "ML-KEM-768" },
  X25519MLKEM768: { plain: "Hybrid connection", technical: "X25519MLKEM768" },
  "ML-DSA-65": { plain: "Quantum-safe signatures", technical: "ML-DSA-65" },
};

/** The plain name for a technical name or for a label that contains one ("ML-KEM-768 key exchange"), or null. */
export function plainNameFor(text: string): { plain: string; technical: string } | null {
  for (const key of Object.keys(PLAIN)) {
    if (text.includes(key)) return PLAIN[key] ?? null;
  }
  return null;
}

/** "Quantum-safe key exchange (ML-KEM-768)", or the text as it was when it has no plain name. */
export function withPlainName(text: string): string {
  const found = plainNameFor(text);
  return found ? `${found.plain} (${found.technical})` : text;
}
