import type { ReactNode } from "react";
import type { QueryState } from "@/hooks/useQuery";
import { LoadingState, ErrorState } from "./States";

/** Renders loading / failed / ready for a query. Keeps pages honest about every state. */
export function QueryBoundary<T>({ q, label, children }: { q: QueryState<T>; label?: string; children: (data: T) => ReactNode }) {
  if (q.status === "loading" && q.data === null) return <LoadingState label={label} />;
  if (q.status === "failed") return <ErrorState message={q.error ?? "Unknown error"} onRetry={q.retry} />;
  if (q.data === null) return <LoadingState label={label} />;
  return <>{children(q.data)}</>;
}
