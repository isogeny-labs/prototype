import type { FixStatus, FixStatusKey, RichText } from "../../api";
import { RichTextView, Spinner } from "../ui";

export const H = "text-[13px] font-semibold text-slate-100";
export const DT = "text-slate-400";

/** A sentence from the backend, with fixed-width names a little smaller and brighter than the words around them. */
export function Rich({ parts }: { parts: RichText }) {
  return <RichTextView parts={parts} mono="whitespace-nowrap font-mono text-[0.92em] text-slate-200" />;
}

// One look for each status. The chip always carries the backend's word, so nothing depends on colour alone.
const STATUS_LOOKS: Record<FixStatusKey, string> = {
  not_connected: "border-slate-500 text-slate-200",
  proving: "border-slate-500 text-slate-100",
  ready: "border-sky-400/60 bg-sky-400/10 text-sky-100",
  failed: "border-amber-400/70 bg-amber-400/15 text-amber-100",
  waiting: "border-slate-400 bg-slate-700/40 text-slate-100",
  ready_to_merge: "border-sky-400/60 bg-sky-400/10 text-sky-100",
  merged: "border-slate-400 bg-slate-700/40 text-slate-100",
  text_only: "border-dashed border-slate-400 text-slate-200",
};

/** Where a fix stands, exactly as the backend worded it. */
export function StatusChip({ status }: { status: FixStatus }) {
  return (
    <span
      data-testid="fix-status"
      data-status={status.key}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
        STATUS_LOOKS[status.key] ?? STATUS_LOOKS.not_connected
      }`}
    >
      {status.busy ? <Spinner className="h-3 w-3" /> : null}
      {status.word}
    </span>
  );
}
