import type { FixStatus, FixStatusKey, RichText, Tone } from "../../api";
import { chipClass, RichTextView, Spinner } from "../ui";

export const H = "text-[13px] font-semibold text-slate-100";
export const DT = "text-slate-400";

/** A sentence from the backend, with fixed-width names a little smaller and brighter than the words around them. */
export function Rich({ parts }: { parts: RichText }) {
  return <RichTextView parts={parts} mono="whitespace-nowrap font-mono text-[0.92em] text-slate-200" />;
}

// One tone for each status, in the shared status chip (phase 5a). The chip always carries the backend's word, so
// nothing depends on colour alone.
const STATUS_TONES: Record<FixStatusKey, Tone> = {
  not_connected: "neutral",
  proving: "neutral",
  ready: "pass",
  failed: "fail",
  waiting: "neutral",
  ready_to_merge: "pass",
  merged: "neutral",
  text_only: "warn",
};

/** Where a fix stands, exactly as the backend worded it. */
export function StatusChip({ status }: { status: FixStatus }) {
  return (
    <span
      data-testid="fix-status"
      data-status={status.key}
      className={chipClass(STATUS_TONES[status.key] ?? "neutral", "sm")}
    >
      {status.busy ? <Spinner className="h-3 w-3" /> : null}
      {status.word}
    </span>
  );
}
