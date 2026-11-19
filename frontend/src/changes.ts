import { useEffect, useState } from "react";

/** Phase 6a: how the pages and the Otto panel hear that something changed the assessment.
 *
 * Every request that is not a read ends here (src/api.ts calls `notifyChanged` after its answer). The panel reads
 * again on every change, whoever sent it. A page reads again when the change was sent from the panel, so the page and
 * the panel always show the same status word. Nothing is decided here: this only says "read again". */
export type ChangeSource = "page" | "panel";
type Listener = (source: ChangeSource) => void;

const listeners = new Set<Listener>();
let sending: ChangeSource = "page";

export function notifyChanged(): void {
  for (const listener of Array.from(listeners)) listener(sending);
}

/** Marks the requests made while `send` runs as the panel's own, so the open page reads its view again. */
export async function fromPanel<T>(send: () => Promise<T>): Promise<T> {
  const before = sending;
  sending = "panel";
  try {
    return await send();
  } finally {
    sending = before;
  }
}

export function onChanged(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** A number that goes up each time the panel changed the assessment. A page puts it among the things its own read
 * depends on, and so reads again. */
export function usePanelStamp(): number {
  const [stamp, setStamp] = useState(0);
  useEffect(() => onChanged((source) => (source === "panel" ? setStamp((n) => n + 1) : undefined)), []);
  return stamp;
}

/** For the panel: goes up on every change, whoever sent it. */
export function useChangeStamp(): number {
  const [stamp, setStamp] = useState(0);
  useEffect(() => onChanged(() => setStamp((n) => n + 1)), []);
  return stamp;
}
