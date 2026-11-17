import type { Page } from "../../router";
import type { PageAccess } from "./Sidebar";
import { PAGE_TITLES } from "./TopBar";

// Today's step-by-step order, for investor demos.
export const GUIDED_ORDER: Page[] = ["inventory/import", "inventory/verify", "checks", "evidence", "fixes", "migration/systems"];

const STEP_WORDS: Record<string, string> = {
  "inventory/import": "Import",
  "inventory/verify": "Verify",
  checks: "Checks",
  evidence: "Evidence",
  fixes: "Fixes",
  "migration/systems": "Migration",
};

/** Guided demo: Back and Next through the pages in today's order. Next is off, with the reason, until that page opens. */
export function GuidedBar({ page, access, onGo }: { page: Page; access: PageAccess; onGo: (p: Page) => void }) {
  const base: Page = page.startsWith("migration/") ? "migration/systems" : page;
  const i = GUIDED_ORDER.indexOf(base);
  const prev = i > 0 ? GUIDED_ORDER[i - 1] : null;
  const next = i >= 0 && i < GUIDED_ORDER.length - 1 ? GUIDED_ORDER[i + 1] : null;
  const btn =
    "inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3.5 py-2 text-sm font-medium text-slate-100 hover:border-slate-500 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50";
  return (
    <nav aria-label="Guided demo" data-testid="guided-bar" className="mt-10 flex items-center justify-between gap-3 border-t border-slate-800 pt-5">
      {prev ? (
        <button type="button" className={btn} onClick={() => onGo(prev)}>
          ← Back: {STEP_WORDS[prev]}
        </button>
      ) : (
        <span />
      )}
      <span className="hidden text-xs text-slate-500 sm:block">
        Guided demo · step {i + 1} of {GUIDED_ORDER.length}: {PAGE_TITLES[base] && STEP_WORDS[base]}
      </span>
      {next ? (
        <button type="button" className={btn} disabled={!access[next].open} title={access[next].open ? undefined : access[next].reason} onClick={() => onGo(next)}>
          Next: {STEP_WORDS[next]} →
        </button>
      ) : (
        <span />
      )}
    </nav>
  );
}
