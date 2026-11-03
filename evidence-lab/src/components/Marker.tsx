/** Visible "Sample" / "Simulated" marker. Every illustrative or simulated value carries one. */
export function Marker({ kind = "sample", className = "" }: { kind?: "sample" | "simulated" | "illustrative" | "imported" | "fictional"; className?: string }) {
  const text = kind === "sample" ? "Sample" : kind === "simulated" ? "Simulated" : kind === "illustrative" ? "Sample value" : kind === "imported" ? "Imported" : "Fictional";
  return (
    <span className={`tag border-sample/60 text-sample ${className}`} title={`${text}: not a real measurement or record.`} data-testid={`marker-${kind}`}>
      <span aria-hidden="true">◇</span> {text}
    </span>
  );
}
