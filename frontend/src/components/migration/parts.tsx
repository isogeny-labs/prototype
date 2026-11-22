import type { MigrationLine, Tone, TrackStatusCode } from "../../api";
import { chipClass, RichTextView } from "../ui";

// One symbol and one tone per status code, drawn in the shared status chip (phase 5a). The symbol and the words carry
// the meaning, so nothing depends on colour alone.
const LOOKS: Record<TrackStatusCode, { symbol: string; tone: Tone }> = {
  hybrid: { symbol: "◑", tone: "pass" },
  pq_only: { symbol: "●", tone: "pass" },
  post_quantum: { symbol: "●", tone: "pass" },
  classical: { symbol: "○", tone: "neutral" },
  couldnt_check: { symbol: "?", tone: "warn" },
  not_measured: { symbol: "–", tone: "warn" },
};

/** The status as the backend worded it. `large` is the Today box's version; the list uses the small one. */
export function StatusPill({ status, large }: { status: { code: TrackStatusCode; label: string }; large?: boolean }) {
  const look = LOOKS[status.code] ?? LOOKS.not_measured;
  return (
    <span
      data-testid="migration-status"
      data-code={status.code}
      className={`${chipClass(look.tone, large ? "md" : "sm")} text-left`}
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
