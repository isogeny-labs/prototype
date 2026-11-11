import { useEffect, type ReactNode, type RefObject } from "react";
import type { RichText, RowStatus, Tone } from "../api";

/** Small label saying where a value came from (rule: every number says its source). */
export function SourceTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded border border-slate-700 px-1.5 py-0.5 text-[11px] leading-none text-slate-400 whitespace-nowrap">
      {children}
    </span>
  );
}

export function DemoDataLabel() {
  return (
    <span className="inline-block rounded border border-violet-400/50 bg-violet-400/10 px-2 py-0.5 text-xs font-medium text-violet-200">
      Demo data
    </span>
  );
}

export function ErrorBox({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : undefined}>{children}</div>
    </div>
  );
}

export function PrimaryButton({
  children,
  disabled,
  busy,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  disabled?: boolean;
  busy?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className="rounded-lg bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  disabled,
  onClick,
  expanded,
  pressed,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  /** For a button that opens a list. */
  expanded?: boolean;
  /** For a button that records a choice. */
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-expanded={expanded}
      aria-haspopup={expanded === undefined ? undefined : "menu"}
      aria-pressed={pressed}
      className="whitespace-nowrap aria-expanded:border-slate-400 aria-expanded:bg-slate-800 aria-pressed:border-slate-400 aria-pressed:bg-slate-800 rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function Wordmark({ large }: { large?: boolean }) {
  return (
    <span className={`font-semibold tracking-tight text-slate-50 ${large ? "text-2xl" : "text-lg"}`}>
      Isogeny Labs
    </span>
  );
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

// One look per tone, used for every result label on every screen. Each badge
// carries its words and a symbol, so nothing depends on colour alone. "pass"
// is styled as a calm match, never as "safe".
const TONES: Record<Tone, { symbol: string; className: string }> = {
  pass: { symbol: "✓", className: "border-sky-400/60 bg-sky-400/10 text-sky-100" },
  fail: { symbol: "✕", className: "border-amber-400/70 bg-amber-400/15 text-amber-100" },
  neutral: { symbol: "•", className: "border-slate-500 bg-slate-700/40 text-slate-100" },
  warn: { symbol: "?", className: "border-dashed border-slate-400 bg-slate-800 text-slate-100" },
};

/** A result label exactly as the backend worded it. */
export function ResultBadge({ label, tone }: { label: string; tone: Tone }) {
  const look = TONES[tone] ?? TONES.neutral;
  return (
    <span
      data-testid="result-badge"
      data-tone={tone}
      className={`inline-flex items-start gap-1.5 rounded-md border px-2.5 py-1 text-left text-sm font-semibold ${look.className}`}
    >
      <span aria-hidden="true" className="font-mono">
        {look.symbol}
      </span>
      <span>{label}</span>
    </span>
  );
}

/** A sentence made of plain words, fixed-width names, source tags and times. */
export function RichTextView({ parts }: { parts: RichText }) {
  return (
    <>
      {parts.map((part, i) => {
        if (part.t === "mono") {
          return (
            <span key={i} className="whitespace-nowrap font-mono">
              {part.v}
            </span>
          );
        }
        if (part.t === "tag") return <SourceTag key={i}>{part.v}</SourceTag>;
        if (part.t === "time") {
          return (
            <time key={i} dateTime={part.v}>
              {formatTime(part.v)}
            </time>
          );
        }
        return <span key={i}>{part.v}</span>;
      })}
    </>
  );
}

/** Not run yet / Waiting / Running, with the progress text and bar the backend sent. */
export function StatusView({ status }: { status: RowStatus }) {
  const progress = status.progress;
  return (
    <div data-testid="job-status" data-status={status.status} className="flex items-start gap-2 text-[13px] text-slate-300">
      {status.status === "running" ? (
        <span
          aria-hidden="true"
          className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-700 border-r-sky-400 border-t-sky-400 motion-reduce:animate-none"
        />
      ) : (
        <span
          aria-hidden="true"
          className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-slate-500 ${
            status.status === "waiting" ? "border-dashed" : ""
          }`}
        />
      )}
      <div className="min-w-0">
        <p>{status.status_text}</p>
        {progress ? <p className="text-xs text-slate-400">{progress.text}</p> : null}
        {progress && progress.percent !== null ? (
          <div
            role="progressbar"
            aria-label={`${status.status_text}: ${progress.text}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress.percent)}
            className="mt-1.5 h-1 w-36 rounded bg-slate-800"
          >
            <div
              className="h-1 rounded bg-sky-400"
              style={{ width: `${Math.max(0, Math.min(100, progress.percent))}%` }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Closes a pop-up list when the user presses Escape or clicks outside it. */
export function useDismiss(open: boolean, ref: RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    function onDown(e: MouseEvent) {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) close();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open, ref, close]);
}
