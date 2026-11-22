/** Phase 5a: plain names first on screen, the technical name under them. Only the words on screen change: every id,
 * answer-key field and evidence field keeps its technical name.
 * Phase 5b: the backend sends the pairs (the workspace's algorithm_names); these are the same pairs until it has. Longer
 * names come first, so "X25519MLKEM768" is found before "X25519". */
let PAIRS: { technical: string; plain: string }[] = [
  { technical: "X25519MLKEM768", plain: "Hybrid connection" },
  { technical: "ML-KEM-768", plain: "Quantum-safe key exchange" },
  { technical: "ML-DSA-65", plain: "Quantum-safe signatures" },
  { technical: "ECDSA P-256", plain: "Classical signatures" },
  { technical: "Ed25519", plain: "Classical signatures" },
  { technical: "RSA", plain: "Classical signatures" },
  { technical: "X25519", plain: "Classical key exchange" },
];

export function setAlgorithmNames(pairs: { technical: string; plain: string }[]): void {
  if (pairs.length > 0) PAIRS = [...pairs].sort((a, b) => b.technical.length - a.technical.length);
}

/** The plain name for a technical name or for a label that contains one ("ML-KEM-768 key exchange"), or null. */
export function plainNameFor(text: string): { plain: string; technical: string } | null {
  for (const pair of PAIRS) {
    const at = text.indexOf(pair.technical);
    if (at < 0) continue;
    // A whole word only: "RSA" in "RSA 2048", never inside another word.
    const before = at === 0 ? " " : text.charAt(at - 1);
    const after = text.charAt(at + pair.technical.length) || " ";
    if (/[A-Za-z0-9]/.test(before) || /[A-Za-z]/.test(after)) continue;
    return { plain: pair.plain, technical: pair.technical };
  }
  return null;
}

/** "Quantum-safe key exchange (ML-KEM-768)", or the text as it was when it has no plain name. */
export function withPlainName(text: string): string {
  const found = plainNameFor(text);
  return found ? `${found.plain} (${found.technical})` : text;
}
