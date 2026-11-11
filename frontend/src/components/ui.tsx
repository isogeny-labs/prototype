import type { ReactNode } from "react";

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
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-100 transition-colors hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
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
