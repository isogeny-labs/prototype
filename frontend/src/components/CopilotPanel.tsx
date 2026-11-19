import { useState } from "react";

/** Phase 1: the panel exists but the assistant isn't built. No input box, no actions. */
export function CopilotPanel() {
  const [open, setOpen] = useState(true);

  return (
    <aside
      data-testid="copilot-panel"
      aria-labelledby="copilot-title"
      className={`shrink-0 border-t border-slate-800 bg-slate-900/60 lg:border-l lg:border-t-0 ${
        open ? "lg:w-80" : "lg:w-20"
      }`}
    >
      <div className={`flex items-start gap-3 ${open ? "justify-between p-4" : "p-4 lg:justify-center lg:px-2"}`}>
        <h2 id="copilot-title" className={open ? "text-sm font-semibold text-slate-100" : "sr-only"}>
          Prototype assistant (no AI model connected)
        </h2>
        <button
          type="button"
          data-testid="copilot-toggle"
          aria-expanded={open}
          aria-controls="copilot-body"
          aria-label={open ? "Hide assistant panel" : "Show assistant panel"}
          onClick={() => setOpen((v) => !v)}
          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500 hover:bg-slate-800"
        >
          {open ? "Hide" : "Show"}
        </button>
      </div>
      {open ? (
        <div id="copilot-body" className="px-4 pb-6 text-sm text-slate-400">
          <p>The assistant isn't built yet. Everything can be done with the buttons on the main screen.</p>
        </div>
      ) : null}
    </aside>
  );
}
