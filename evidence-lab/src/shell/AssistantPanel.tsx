import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useAppStore } from "@/store";
import { useProjectCtx } from "./ProjectContext";

const NO_MESSAGES: never[] = [];
const SUGGESTIONS = ["hide the recent activity panel", "move next actions to the top", "only failed", "show tests matching latency", "reset the view", "change the acceptance criteria threshold to 1.5"];

/** Simulated assistant. It may only change view configuration; everything else is refused and routed to an approval request. */
export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const { project, projectId } = useProjectCtx();
  const user = useAppStore((s) => s.user);
  const viewConfig = useAppStore((s) => (projectId ? s.viewConfig[projectId] : undefined));
  const setViewConfig = useAppStore((s) => s.setViewConfig);
  const messagesRaw = useAppStore((s) => (projectId ? s.assistantMessages[projectId] : undefined));
  const messages = messagesRaw ?? NO_MESSAGES;
  const append = useAppStore((s) => s.appendAssistantMessages);
  const clear = useAppStore((s) => s.clearAssistant);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages.length, busy]);

  async function send(input: string) {
    if (!projectId || !input.trim() || busy) return;
    setBusy(true); setError(null); setText("");
    const at = new Date().toISOString();
    append(projectId, [{ id: `u-${Date.now()}`, role: "user", text: input, at }]);
    try {
      const vc = viewConfig ?? { panelOrder: [], hiddenPanels: [], filters: {}, chosenTestIds: [] };
      const { reply, viewConfig: next } = await services.assistant.send(projectId, vc, input, { id: user.id, name: user.name });
      if (reply.action?.kind === "view_change") setViewConfig(projectId, next);
      append(projectId, [{ id: reply.id, role: "assistant", text: reply.text, at: reply.at, action: reply.action }]);
    } catch (e) { setError(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <aside aria-label="Assistant" data-testid="assistant-panel" className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span className="h2">Assistant</span>
        <span className="tag border-sample/60 text-sample">Simulated</span>
        <button type="button" className="btn-ghost btn-sm ml-auto" onClick={onClose} aria-label="Close assistant panel">Close</button>
      </div>
      <div className="border-b border-line px-3 py-2 text-xs text-muted">
        Changes how views are configured{project ? ` for ${project.name}` : ""}: panels, order, filters, which supported tests are shown. Cannot change acceptance criteria, permissions or test definitions; such requests are refused and sent to Approvals. Every change is audited.
      </div>
      {!projectId ? <div className="p-3 text-sm text-muted">Open a project to use the assistant.</div> : (
        <>
          <div className="flex-1 overflow-y-auto p-3 text-sm" data-testid="assistant-transcript">
            {messages.length === 0 ? <div className="text-faint">No messages yet. Try one of the suggestions below.</div> : null}
            {messages.map((m) => (
              <div key={m.id} className={`mb-2 rounded-md px-2.5 py-2 ${m.role === "user" ? "ml-6 bg-panel-2" : "mr-2 border border-line"}`} data-testid={`assistant-msg-${m.role}`} data-action={m.action?.kind ?? "none"}>
                <div className="text-2xs uppercase tracking-wide text-faint">{m.role === "user" ? user.name : "Assistant (simulated)"}</div>
                <div className="mt-0.5 whitespace-pre-wrap">{m.text}</div>
                {m.action?.kind === "refused" ? <div className="callout-bad mt-2 text-xs" role="alert" data-testid="assistant-refusal"><strong>Refused.</strong> {m.action.reason}. {m.action.approvalRequestId ? <>An approval request was created: <Link to={`/p/${projectId}/approvals`}>open Approvals</Link>.</> : null}</div> : null}
                {m.action?.kind === "view_change" ? <div className="mt-1 text-2xs text-ok">▲ View configuration changed · logged to audit</div> : null}
              </div>
            ))}
            {busy ? <div className="text-xs text-faint">Assistant is thinking…</div> : null}
            {error ? <div className="callout-bad text-xs" role="alert">{error}</div> : null}
            <div ref={endRef} />
          </div>
          <div className="border-t border-line p-2">
            <div className="mb-2 flex flex-wrap gap-1">{SUGGESTIONS.map((s) => <button key={s} type="button" className="tag hover:border-accent hover:text-accent" onClick={() => send(s)} disabled={busy}>{s}</button>)}</div>
            <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); send(text); }}>
              <input className="input" placeholder="Ask the assistant to change the view…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Message to the assistant" data-testid="assistant-input" />
              <button type="submit" className="btn btn-sm" disabled={busy || !text.trim()} data-testid="assistant-send">Send</button>
            </form>
            <div className="mt-1 flex justify-between text-2xs text-faint"><span>Acting as {user.name}</span><button type="button" className="underline" onClick={() => clear(projectId)}>Clear transcript</button></div>
          </div>
        </>
      )}
    </aside>
  );
}
