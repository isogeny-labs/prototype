import { useCallback, useRef, useState } from "react";
import type { LabView, RetestVersion } from "../../api";
import { SecondaryButton, SourceTag, useDismiss } from "../ui";

/** Retest new version: the one button and its menu, the same on Evidence and on Checks (the 5c fixes). The versions it
 * lists, its notes, and whether it can be pressed (with the reason when it can't) all come from the backend's view of
 * the assessment's results, so both pages offer exactly the same thing. Choosing a version is the page's to send. */
export function RetestMenu({
  retest,
  disabled = false,
  onChoose,
}: {
  retest: LabView["retest"];
  /** The page is busy with a request of its own. */
  disabled?: boolean;
  onChoose: (version: RetestVersion) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, ref, close);
  return (
    <div ref={ref} className="relative">
      <SecondaryButton expanded={open} disabled={disabled || !retest.can_start} onClick={() => setOpen((v) => !v)}>
        Retest new version
      </SecondaryButton>
      {open ? (
        <div
          role="menu"
          aria-label={retest.menu_title}
          className="absolute right-0 top-[46px] z-20 w-[420px] max-w-[calc(100vw-2rem)] rounded-[10px] border border-slate-600 bg-slate-900 p-1.5 shadow-2xl shadow-black/60"
        >
          <p className="px-2.5 pb-1.5 pt-2 text-xs text-slate-400">{retest.menu_title}</p>
          {retest.versions.map((v) => (
            <button
              key={`${v.component ?? ""}/${v.version}`}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onChoose(v);
              }}
              className="block w-full rounded-md p-2.5 text-left hover:bg-slate-800 focus-visible:bg-slate-800"
            >
              <span className="text-sm font-semibold text-slate-100">{v.label}</span>
              {v.tag ? (
                <>
                  {" "}
                  <SourceTag>{v.tag}</SourceTag>
                </>
              ) : null}
              <span className="mt-0.5 block text-[13px] text-slate-400">{v.note}</span>
            </button>
          ))}
          <p className="mt-1.5 border-t border-slate-800 px-2.5 pb-1 pt-2 text-xs text-slate-400">{retest.menu_note}</p>
        </div>
      ) : null}
    </div>
  );
}

/** Under the button, on both pages: how far a running retest is, and why the button is off when it is. */
export function RetestStatus({ retest }: { retest: LabView["retest"] }) {
  return (
    <>
      {retest.running && retest.progress_text ? (
        <p role="status" data-testid="retest-progress" className="mb-3 text-sm text-slate-300">
          {retest.progress_text}
        </p>
      ) : null}
      {!retest.can_start && !retest.running && retest.blocked_reason ? (
        <p data-testid="retest-blocked" className="mb-3 text-xs text-slate-400">
          {retest.blocked_reason}
        </p>
      ) : null}
    </>
  );
}
