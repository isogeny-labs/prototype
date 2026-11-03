import type { ReactNode } from "react";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" data-testid="loading-state" className="panel flex items-center gap-3 text-sm text-muted">
      <span aria-hidden="true" className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}…
    </div>
  );
}

export function ErrorState({ message, onRetry, title = "Couldn't load this" }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" data-testid="error-state" className="callout-bad flex flex-wrap items-start gap-3">
      <span aria-hidden="true" className="font-bold">✕</span>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{title}</div>
        <div className="text-muted break-words">{message}</div>
      </div>
      {onRetry ? <button type="button" className="btn-ghost btn-sm" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div data-testid="empty-state" className="panel border-dashed text-sm text-muted">
      <div className="font-semibold text-ink">{title}</div>
      {hint ? <div className="mt-1">{hint}</div> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
