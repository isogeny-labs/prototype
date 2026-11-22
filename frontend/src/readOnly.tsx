import { createContext, useContext, type ReactNode } from "react";

/** Phase 5a: a closed assessment is read-only. Every action button inside this turns off and says why; downloads and
 * navigation opt out. The backend refuses the same requests, so this is the screen's half of one rule. */
export const CLOSED_SENTENCE = "This assessment is closed. Start a new one to continue.";

const ReadOnly = createContext<boolean>(false);

export function ReadOnlyProvider({ readOnly, children }: { readOnly: boolean; children: ReactNode }) {
  return <ReadOnly.Provider value={readOnly}>{children}</ReadOnly.Provider>;
}

export function useReadOnly(): boolean {
  return useContext(ReadOnly);
}
