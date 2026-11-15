import type { MigrationLine, TrackStatusCode } from "../../api";
import { RichTextView } from "../ui";

// One look per status code. Each pill carries a symbol and its words, so nothing depends on colour alone.
const LOOKS: Record<TrackStatusCode, { symbol: string; className: string }> = {
  hybrid: { symbol: "◑", className: "border-sky-400/60 bg-sky-400/10 text-sky-100" },
  pq_only: { symbol: "●", className: "border-sky-400/60 bg-sky-400/20 text-sky-50" },
  post_quantum: { symbol: "●", className: "border-sky-400/60 bg-sky-400/20 text-sky-50" },
  classical: { symbol: "○", className: "border-slate-500 bg-slate-700/40 text-slate-100" },
  couldnt_check: { symbol: "?", className: "border-dashed border-amber-300/60 bg-slate-800 text-slate-100" },
  not_measured: { symbol: "–", className: "border-dashed border-slate-500 bg-slate-900 text-slate-300" },
};

/** The status as the backend worded it. `large` is the Today box's version; the list uses the small one. */
export function StatusPill({ status, large }: { status: { code: TrackStatusCode; label: string }; large?: boolean }) {
  const look = LOOKS[status.code] ?? LOOKS.not_measured;
  const shape = large
    ? "items-start gap-1.5 rounded-md px-2.5 py-1 text-sm"
    : "items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs";
  return (
    <span
      data-testid="migration-status"
      data-code={status.code}
      className={`inline-flex border text-left font-semibold ${shape} ${look.className}`}
    >
      <span aria-hidden="true" className="font-mono">
        {look.symbol}
      </span>
      <span>{status.label}</span>
    </span>
  );
}

/** The quiet link-style button after a line that has a suggestion in the Fixes step. */
export function ViewInFixes({ fixId, onViewFix }: { fixId: string; onViewFix: (fixId: string) => void }) {
  return (
    <button
      type="button"
      data-fix-id={fixId}
      onClick={() => onViewFix(fixId)}
      className="whitespace-nowrap rounded font-medium text-sky-300 underline decoration-sky-300/40 underline-offset-2 hover:text-sky-200"
    >
      View in Fixes
    </button>
  );
}

/** A sentence, then "View in Fixes" when it points to a fix. */
export function LineView({ line, onViewFix }: { line: MigrationLine; onViewFix: (fixId: string) => void }) {
  return (
    <>
      <RichTextView parts={line.text} />
      {line.fix_id ? (
        <>
          {" "}
          <ViewInFixes fixId={line.fix_id} onViewFix={onViewFix} />
        </>
      ) : null}
    </>
  );
}

/** A small rounded tag, e.g. "Recommended" or "Your choice" on an option card. */
export function Chip({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded-full border border-slate-500 bg-slate-800 px-2.5 py-0.5 text-xs font-semibold text-slate-100">
      {children}
    </span>
  );
}
