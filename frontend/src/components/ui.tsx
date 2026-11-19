import { useEffect, type ReactNode, type RefObject } from "react";
import type { RichText, RowStatus, Tone } from "../api";
import { CLOSED_SENTENCE, useReadOnly } from "../readOnly";
import { formatTime } from "../time";

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
  allowWhenClosed,
  testId,
}: {
  children: ReactNode;
  disabled?: boolean;
  busy?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  /** Phase 5a: a download or a way forward that stays on in a closed assessment. */
  allowWhenClosed?: boolean;
  testId?: string;
}) {
  const closed = useReadOnly() && !allowWhenClosed;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || busy || closed}
      aria-busy={busy || undefined}
      title={closed ? CLOSED_SENTENCE : undefined}
      data-closed={closed || undefined}
      data-testid={testId}
      className="inline-flex items-center justify-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-sm transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500 disabled:shadow-none"
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
  allowWhenClosed,
  testId,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  /** For a button that opens a list. */
  expanded?: boolean;
  /** For a button that records a choice. */
  pressed?: boolean;
  /** Phase 5a: a download or a way forward that stays on in a closed assessment. */
  allowWhenClosed?: boolean;
  testId?: string;
}) {
  const closed = useReadOnly() && !allowWhenClosed;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || closed}
      aria-expanded={expanded}
      aria-haspopup={expanded === undefined ? undefined : "menu"}
      aria-pressed={pressed}
      title={closed ? CLOSED_SENTENCE : undefined}
      data-closed={closed || undefined}
      data-testid={testId}
      className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-sm font-medium text-slate-100 shadow-sm transition-colors hover:border-slate-500 hover:bg-slate-800 aria-expanded:border-slate-500 aria-expanded:bg-slate-800 aria-pressed:border-slate-500 aria-pressed:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function Wordmark({ large }: { large?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight text-slate-50 ${large ? "text-2xl" : "text-base"}`}>
      <span
        aria-hidden="true"
        className={`grid place-items-center rounded-md bg-sky-500 font-bold text-slate-950 ${large ? "h-8 w-8 text-base" : "h-6 w-6 text-xs"}`}
      >
        IL
      </span>
      <span>Isogeny Labs</span>
    </span>
  );
}

// The one way a time is written on screen, in the viewer's own time zone (the 5c fixes): src/time.ts.
export { formatTime };

/** Saves one file the app made, by its own address. Nothing is sent anywhere. */
export function saveFile(url: string, filename: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

// One look per tone, used for every status chip on every screen (phase 5a: one set everywhere). Each chip carries its
// words and a symbol, so nothing depends on colour alone. "pass" is styled as a calm match, never as "safe".
const TONES: Record<Tone, { symbol: string; className: string }> = {
  pass: { symbol: "✓", className: "border-sky-400/50 bg-sky-400/10 text-sky-100" },
  fail: { symbol: "✕", className: "border-amber-400/60 bg-amber-400/15 text-amber-100" },
  neutral: { symbol: "•", className: "border-slate-600 bg-slate-800/60 text-slate-100" },
  warn: { symbol: "?", className: "border-dashed border-slate-500 bg-slate-900 text-slate-100" },
};

/** The chip shape and tone every status chip shares (phase 5a: one set everywhere). Screens with their own symbols
 * (the migration status, the fix status) draw them inside this same chip. */
export function chipClass(tone: Tone, size: "sm" | "md" = "md", wrap = false): string {
  const look = TONES[tone] ?? TONES.neutral;
  const sizing = size === "sm" ? "gap-1 px-1.5 py-0.5 text-xs" : "gap-1.5 px-2 py-0.5 text-[13px]";
  // Phase 5b: a long chip in a narrow table cell ("Not in our knowledge base yet") may wrap between words.
  const lines = wrap ? "rounded-xl text-left leading-snug" : "rounded-full whitespace-nowrap";
  return `inline-flex items-center border font-semibold ${lines} ${sizing} ${look.className}`;
}

/** The one status chip: True / False / Couldn't check, Passed / Failed / Couldn't run / Couldn't trust this run /
 * Measured, Classical / Hybrid / Post-quantum only, Open / Closed. The words are always the backend's. */
export function StatusChip({
  label,
  tone,
  size = "md",
  testId,
  wrap = false,
  title,
}: {
  label: string;
  tone: Tone;
  size?: "sm" | "md";
  testId?: string;
  wrap?: boolean;
  /** Phase 5c: the reason behind the label, in the backend's words, shown on hover (an advisory's Test chip). */
  title?: string;
}) {
  const look = TONES[tone] ?? TONES.neutral;
  return (
    <span data-testid={testId} data-tone={tone} title={title} className={chipClass(tone, size, wrap)}>
      {/* The symbol is drawn by CSS, so the chip's text is exactly the backend's word. */}
      <span aria-hidden="true" data-symbol={look.symbol} className="font-mono text-[0.85em] before:content-[attr(data-symbol)]" />
      <span>{label}</span>
    </span>
  );
}

/** How a result was proven, as a quiet outlined chip: "Release notes say", "Measured on a public copy", "Measured". */
export function ProofChip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded-full border border-slate-600 px-2 py-0.5 text-[11px] font-medium leading-none text-slate-300">
      {children}
    </span>
  );
}

/** A result label exactly as the backend worded it. */
export function ResultBadge({ label, tone, wrap = false }: { label: string; tone: Tone; wrap?: boolean }) {
  return <StatusChip label={label} tone={tone} testId="result-badge" wrap={wrap} />;
}

/** A sentence made of plain words, fixed-width names, source tags, times and the Demo data label. */
export function RichTextView({
  parts,
  mono = "whitespace-nowrap font-mono",
}: {
  parts: RichText;
  /** The look of a fixed-width name, for a screen that draws names its own way. */
  mono?: string;
}) {
  return (
    <>
      {parts.map((part, i) => {
        if (part.t === "mono") {
          return (
            <span key={i} className={mono}>
              {part.v}
            </span>
          );
        }
        if (part.t === "tag") return <SourceTag key={i}>{part.v}</SourceTag>;
        if (part.t === "demo") return <DemoDataLabel key={i} />;
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

/** The small turning ring shown while something runs. It always sits next to words that say what is running. */
export function Spinner({ className }: { className: string }) {
  return (
    <span
      aria-hidden="true"
      className={`${className} inline-block shrink-0 animate-spin rounded-full border-2 border-slate-700 border-r-sky-400 border-t-sky-400 motion-reduce:animate-none`}
    />
  );
}

/** The thin bar under a running job's progress text. */
export function ProgressBar({ label, percent }: { label: string; percent: number }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      className="mt-1.5 h-1 w-36 rounded bg-slate-800"
    >
      <div className="h-1 rounded bg-sky-400" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

/** Not run yet / Waiting / Running, with the progress text and bar the backend sent. */
export function StatusView({ status }: { status: RowStatus }) {
  const progress = status.progress;
  return (
    <div data-testid="job-status" data-status={status.status} className="flex items-start gap-2 text-[13px] text-slate-300">
      {status.status === "running" ? (
        <Spinner className="mt-0.5 h-3.5 w-3.5" />
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
          <ProgressBar label={`${status.status_text}: ${progress.text}`} percent={progress.percent} />
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

/**
 * One "Also noticed" side note: something a check saw that the file didn't ask about. It is never a result,
 * so it is drawn as a quiet note with a thin left rule, never as a badge and never in a result colour.
 */
export function AlsoNoticedNote({ title, text }: { title: string; text: string }) {
  return (
    <p
      data-testid="also-noticed"
      className="rounded-md border border-slate-700 border-l-2 border-l-sky-400/50 bg-slate-900/60 px-3 py-2 text-[13px] text-slate-300"
    >
      <span className="text-xs font-medium text-sky-200/80">{title}:</span> {text}
    </p>
  );
}

/** Every "Also noticed" note of one result, one per line. Draws nothing when there are none. */
export function AlsoNoticedList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item, i) => (
        <AlsoNoticedNote key={i} title={title} text={item} />
      ))}
    </div>
  );
}

/** The calm "Not tested, and why" box: every target or test the plan leaves out, with its reason. */
export function NotTestedBox({ title, items }: { title: string; items: string[] }) {
  return (
    <div data-testid="not-tested" className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3 text-sm">
      <h2 className="font-semibold text-slate-100">{title}</h2>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-slate-300 marker:text-slate-500">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/** Splits items into their groups, in the order of `groups`. Items whose group isn't listed go last, in their own group. */
export function splitByGroup<T>(
  groups: { key: string }[],
  items: T[],
  groupOf: (item: T) => string | null,
): { key: string | null; items: T[] }[] {
  const out: { key: string | null; items: T[] }[] = groups.map((g) => ({ key: g.key, items: [] }));
  const byKey = new Map<string | null, { key: string | null; items: T[] }>(out.map((g) => [g.key, g]));
  for (const item of items) {
    const key = groupOf(item);
    let bucket = byKey.get(key);
    if (!bucket) {
      bucket = { key, items: [] };
      byKey.set(key, bucket);
      out.push(bucket);
    }
    bucket.items.push(item);
  }
  return out.filter((g) => g.items.length > 0);
}

/** Phase 5b: a name in a table cell. A name breaks only at a space or a dot, never between letters; a name with one
 * very long unbroken part (a 40-character commit id) is cut short with "…" in the cell instead, its full text kept in
 * the page and shown on hover, and in full in the detail panel. */
export function NameText({ text, className = "" }: { text: string; className?: string }) {
  const long = text.split(/\s+/).some((part) => part.length > 24);
  return (
    <span title={long ? text : undefined} className={`${long ? "block max-w-[10rem] truncate" : "[overflow-wrap:normal]"} ${className}`}>
      {text}
    </span>
  );
}
