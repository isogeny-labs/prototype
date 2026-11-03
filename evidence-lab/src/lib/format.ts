export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "2-digit", timeZone: "UTC" });
}
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}
export function shortSha(sha: string, n = 12): string { return sha.length > n ? `${sha.slice(0, n)}…` : sha; }
export function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(2)} MB`;
}
export function fmtValue(v: number | string | boolean | null, unit?: string): string {
  if (v === null) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  const s = typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : v;
  return unit ? `${s} ${unit}` : s;
}
export function humanize(s: string): string { return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()); }
