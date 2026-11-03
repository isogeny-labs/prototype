import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "@/store";

export type QueryState<T> = { status: "loading" | "ready" | "failed"; data: T | null; error: string | null; retry: () => void };

/** Runs an async service call; re-runs when the store version changes (after any mutation) or deps change. */
export function useQuery<T>(fn: () => Promise<T>, deps: unknown[]): QueryState<T> {
  const version = useAppStore((s) => s.version);
  const [state, setState] = useState<{ status: "loading" | "ready" | "failed"; data: T | null; error: string | null }>({ status: "loading", data: null, error: null });
  const [tick, setTick] = useState(0);
  const latest = useRef(0);
  useEffect(() => {
    const my = ++latest.current;
    setState((s) => ({ ...s, status: s.data ? s.status : "loading", error: null }));
    fn().then((data) => { if (my === latest.current) setState({ status: "ready", data, error: null }); })
        .catch((e: unknown) => { if (my === latest.current) setState({ status: "failed", data: null, error: e instanceof Error ? e.message : String(e) }); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, tick]);
  const retry = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, retry };
}
