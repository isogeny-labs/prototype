import { useProjectCtx } from "./ProjectContext";

/** Slot for the assistant. Phase 1: the slot and its boundaries; the conversation UI arrives in Phase 3. */
export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const { project } = useProjectCtx();
  return (
    <aside aria-label="Assistant" data-testid="assistant-panel" className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span className="h2">Assistant</span>
        <span className="tag border-sample/60 text-sample">Simulated</span>
        <button type="button" className="btn-ghost btn-sm ml-auto" onClick={onClose} aria-label="Close assistant panel">Close</button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 text-sm text-muted">
        <p>The assistant can only change how views are configured: panel order, hidden panels, filters and which supported tests are shown{project ? ` for ${project.name}` : ""}.</p>
        <p className="mt-2">It cannot change acceptance criteria, permissions or test definitions. Requests like that are refused with a visible message and routed to an approval request.</p>
        <p className="mt-2 text-faint">Conversation controls are added in Phase 3. Every configuration change will be logged as an audit event.</p>
      </div>
    </aside>
  );
}
